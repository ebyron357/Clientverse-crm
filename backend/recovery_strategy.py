"""Recovery strategy composer — Second Chance steps 2 to 4 (§8 #8).

The detectors in `second_chance.py` answer "which relationships went quiet". This
module answers the next question: "given only what we are authorised to know, what is
the recommended way back in, and why". It is the step the canonical governing document
places between detection and any outbound motion (§1.2 north star steps 2–4).

Three properties are load-bearing, because each one is a mistake this programme has
already made once:

1. **Authorised context only.** The composer reads the tenant's own CRM records and
   nothing else. No enrichment, no external lookup, no third-party source. OSINT
   enrichment (E-13) is a separate capability behind the §6 dual gate, and this module
   must not become a back door into it.

2. **No fabricated confidence.** Strategy selection is a fixed, ordered playbook of
   named lanes with explicit entry conditions. The output cites the facts that matched
   and names the rule. There is no score, no percentage, no model judgement, and no
   claim the system cannot support from a record it can point at.

3. **It composes; it does not send.** Every step declares the channel it needs, and a
   step whose channel is not authorised for this tenant is marked `blocked` with the
   reason. The strategy is raised as an approval request (M-07) carrying those blocks,
   so approving a strategy can never quietly turn into an outbound message: the block
   is re-checked when the approval is consumed.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Optional

import approval_queue
import recovery_case
import second_chance

COLLECTION = "recovery_strategies"

# Channels a step can require. `internal` never leaves the CRM, so it is always
# available; every other channel must be proven authorised before use.
CHANNEL_INTERNAL = "internal"
CHANNEL_EMAIL = "email"
CHANNEL_SMS = "sms"
CHANNEL_PHONE = "phone"

# A channel is authorised only when the tenant has a live connection for its provider
# *and* the catalogue entry for that provider is past configuration. Both halves are
# required: a connected account whose integration is still `REQUIRES_CONFIGURATION` has
# not been certified for outbound use.
CHANNEL_PROVIDERS = {
    CHANNEL_EMAIL: ("gmail",),
    CHANNEL_SMS: (),      # no SMS provider exists in the registry yet (M-03)
    CHANNEL_PHONE: (),    # telephony is an unmade owner decision (O-06, E-08)
}
# `active` is the only live state in the integration connection lifecycle
# (see CONN_STATUSES in server.py). `degraded` deliberately does not count: a
# connection that is already struggling is not a foundation for new outbound work.
CONNECTED_STATUSES = ("active",)
# Authorisation fails closed: a provider counts as configured only when the tenant has a
# catalogue row for it in one of these states. A *missing* row is not permission — a newly
# registered tenant has no `integrations` rows at all (only the seeded demo tenant does),
# so treating "not explicitly unconfigured" as configured would let a freshly connected
# account send before any configuration or certification record existed.
CONFIGURED_INTEGRATION_STATUSES = ("CONNECTED", "ACTIVE", "CERTIFIED", "ENABLED", "AVAILABLE")

# Value bands are configuration so the playbook can be tuned without a code change.
HIGH_VALUE_THRESHOLD = float(os.environ.get("RECOVERY_HIGH_VALUE_THRESHOLD", "25000"))
LOW_VALUE_THRESHOLD = float(os.environ.get("RECOVERY_LOW_VALUE_THRESHOLD", "2500"))
# The two thresholds above are amounts *in this currency*. A bare 25,000 compared with a
# value in yen or in pounds is not a threshold, it is a coincidence, so a value in any
# other currency is only banded if that currency has thresholds of its own -- given as
# JSON, e.g. RECOVERY_VALUE_THRESHOLDS='{"GBP": {"high": 20000, "low": 2000}}'. A value
# in a currency with no thresholds is treated as unbanded: neither high nor low.
THRESHOLD_CURRENCY = (recovery_case.normalize_currency(
    os.environ.get("RECOVERY_THRESHOLD_CURRENCY", recovery_case.DEFAULT_CURRENCY))
    or recovery_case.DEFAULT_CURRENCY)


def _load_thresholds() -> dict[str, dict[str, float]]:
    bands = {THRESHOLD_CURRENCY: {"high": HIGH_VALUE_THRESHOLD, "low": LOW_VALUE_THRESHOLD}}
    try:
        extra = json.loads(os.environ.get("RECOVERY_VALUE_THRESHOLDS") or "{}")
    except ValueError:
        return bands
    for code, band in (extra.items() if isinstance(extra, dict) else []):
        currency = recovery_case.normalize_currency(code)
        try:
            if currency and isinstance(band, dict):
                bands[currency] = {"high": float(band["high"]), "low": float(band["low"])}
        except (KeyError, TypeError, ValueError):
            continue
    return bands


VALUE_THRESHOLDS = _load_thresholds()
DORMANT_DAYS = int(os.environ.get("RECOVERY_DORMANT_DAYS", "60"))
LATE_STAGES = ("proposal", "negotiation")
COMPOSE_LIMIT = int(os.environ.get("RECOVERY_COMPOSE_LIMIT", "100"))

STATE_PROPOSED = "proposed"
STATE_APPROVED = "approved"
STATE_REJECTED = "rejected"
STATE_SUPERSEDED = "superseded"
STATE_WITHDRAWN = "withdrawn"


class RecoveryStrategyError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _fact(label: str, value, source: Optional[str] = None) -> dict:
    """A cited fact. `source` is the record it came from, so every claim is traceable."""
    return {"label": label, "value": value, "source": source}


async def ensure_indexes(db) -> None:
    collection = db[COLLECTION]
    await collection.create_index([("tenant_id", 1), ("state", 1), ("created_at", -1)])
    await collection.create_index([("tenant_id", 1), ("candidate_id", 1)])
    # One live strategy per candidate. A second compose pass over the same candidate
    # updates the existing proposal rather than stacking duplicates in the queue.
    await collection.create_index(
        [("tenant_id", 1), ("active_candidate_key", 1)],
        unique=True,
        partialFilterExpression={"active_candidate_key": {"$type": "string"}},
    )


# --------------------------------------------------------------- channel authority

async def authorized_channels(db, tenant_id: str) -> dict[str, dict]:
    """Which channels this tenant may actually use, derived from its own records.

    Returns one entry per channel with `authorized` and a human-readable reason. The
    reason matters as much as the verdict: an operator looking at a blocked strategy
    needs to know what to go and fix.
    """
    connections = await db.integration_connections.find(
        {"tenant_id": tenant_id}, {"_id": 0, "provider": 1, "status": 1}).to_list(100)
    connected = {c.get("provider") for c in connections
                 if str(c.get("status") or "").lower() in CONNECTED_STATUSES}

    catalogue = await db.integrations.find(
        {"tenant_id": tenant_id}, {"_id": 0, "name": 1, "provider": 1, "status": 1}).to_list(100)
    configured = {str(row.get("name") or "").lower() for row in catalogue
                  if str(row.get("status") or "").upper() in CONFIGURED_INTEGRATION_STATUSES}

    result: dict[str, dict] = {
        CHANNEL_INTERNAL: {"authorized": True,
                           "reason": "Internal actions stay inside the CRM."},
    }
    for channel, providers in CHANNEL_PROVIDERS.items():
        if not providers:
            result[channel] = {
                "authorized": False,
                "reason": f"No {channel} provider is registered for this tenant.",
            }
            continue
        live = [p for p in providers if p in connected]
        if not live:
            result[channel] = {
                "authorized": False,
                "reason": (f"No connected {channel} provider "
                           f"({', '.join(providers)} is not connected)."),
            }
            continue
        certified = [p for p in live if p in configured]
        if not certified:
            result[channel] = {
                "authorized": False,
                "reason": (f"{', '.join(live)} is connected, but no integration record marks it "
                           f"configured for this tenant, so outbound {channel} is not certified."),
            }
            continue
        result[channel] = {"authorized": True,
                           "reason": f"Connected and configured provider: {', '.join(certified)}."}
    return result


# ------------------------------------------------------------- context gathering

async def gather_context(db, tenant_id: str, candidate: dict) -> dict:
    """Assemble the authorised account and history context for one candidate.

    Every value returned here comes from a tenant-scoped collection this CRM already
    owns, and carries the id of the record it came from.
    """
    payload = candidate.get("payload") or {}
    evidence = candidate.get("evidence") or {}
    record_id = payload.get("record_id") or evidence.get("record_id")
    record_kind = payload.get("record_kind") or "opportunity"

    context: dict[str, Any] = {
        "record_kind": record_kind,
        "record_id": record_id,
        "facts": [],
        "workspace_id": candidate.get("workspace_id") or evidence.get("workspace_id"),
        "company_id": evidence.get("company_id"),
        "contact_id": evidence.get("contact_id"),
    }
    facts: list[dict] = context["facts"]

    if evidence.get("idle_days") is not None:
        facts.append(_fact("Days idle", evidence["idle_days"], f"{record_kind}:{record_id}"))
    if evidence.get("overdue_days") is not None:
        facts.append(_fact("Days overdue", evidence["overdue_days"], f"{record_kind}:{record_id}"))
    if evidence.get("stage"):
        facts.append(_fact("Stage", evidence["stage"], f"{record_kind}:{record_id}"))
    if evidence.get("value") is not None:
        facts.append(_fact("Value", evidence["value"], f"{record_kind}:{record_id}"))
        currency = _value_currency(evidence)
        if currency not in VALUE_THRESHOLDS:
            # Said out loud, because otherwise an operator would reasonably assume a large
            # figure was weighed as large.
            facts.append(_fact("Value not banded",
                               f"in {currency}; value thresholds are configured for "
                               f"{', '.join(sorted(VALUE_THRESHOLDS))}",
                               f"{record_kind}:{record_id}"))

    # Load the source record. Detector candidates carry a `record_id` and little else:
    # the owner, company and value live on the opportunity, and the workspace is reached
    # through its company. Without this the main stalled-lead lane could never find an
    # owner and every real candidate fell through to triage.
    if record_kind == "opportunity" and record_id:
        opportunity = await db.opportunities.find_one(
            {"tenant_id": tenant_id, "id": record_id}, {"_id": 0})
        if opportunity:
            context["company_id"] = context["company_id"] or opportunity.get("company_id")
            context["contact_id"] = context["contact_id"] or opportunity.get("contact_id")
            context["owner"] = opportunity.get("owner") or opportunity.get("assignee")
            if context["owner"]:
                facts.append(_fact("Opportunity owner", context["owner"],
                                   f"opportunity:{record_id}"))
    if not context.get("workspace_id") and context.get("company_id"):
        workspace_row = await db.workspaces.find_one(
            {"tenant_id": tenant_id, "company_id": context["company_id"]}, {"_id": 0, "id": 1})
        if workspace_row:
            context["workspace_id"] = workspace_row["id"]

    company = None
    if context["company_id"]:
        company = await db.companies.find_one(
            {"tenant_id": tenant_id, "id": context["company_id"]}, {"_id": 0})
        if company:
            context["company_name"] = company.get("name")
            facts.append(_fact("Account", company.get("name"), f"company:{company.get('id')}"))

    contact = None
    if context["contact_id"]:
        contact = await db.contacts.find_one(
            {"tenant_id": tenant_id, "id": context["contact_id"]}, {"_id": 0})
        if contact:
            context["contact_name"] = contact.get("name")
            context["contact_has_email"] = bool(contact.get("email"))
            facts.append(_fact("Known contact", contact.get("name"), f"contact:{contact.get('id')}"))

    workspace = None
    if context["workspace_id"]:
        workspace = await db.workspaces.find_one(
            {"tenant_id": tenant_id, "id": context["workspace_id"]}, {"_id": 0})
        if workspace:
            context["workspace_name"] = workspace.get("name")
            context["owner"] = (context.get("owner") or workspace.get("owner")
                                or workspace.get("account_manager"))
            if context["owner"]:
                facts.append(_fact("Relationship owner", context["owner"],
                                   f"workspace:{workspace.get('id')}"))

    if context["workspace_id"]:
        snapshot = await db.health_snapshots.find(
            {"tenant_id": tenant_id, "workspace_id": context["workspace_id"]}, {"_id": 0}
        ).sort("at", -1).to_list(1)
        if snapshot:
            context["health_score"] = snapshot[0].get("score")
            context["health_band"] = snapshot[0].get("band")
            facts.append(_fact("Client health", snapshot[0].get("band"),
                               f"health_snapshot:{snapshot[0].get('id')}"))

    # Open commitments on the same relationship: a quiet account with unmet promises
    # needs repair before re-engagement, and the playbook branches on exactly that.
    if context["workspace_id"]:
        open_commitments = await db.commitments.count_documents({
            "tenant_id": tenant_id, "workspace_id": context["workspace_id"],
            "status": {"$nin": list(second_chance.RESOLVED_COMMITMENT_STATUSES)},
        })
        context["open_commitments"] = open_commitments
        if open_commitments:
            facts.append(_fact("Open commitments", open_commitments,
                               f"workspace:{context['workspace_id']}"))

    # Prior recovery history on this same record — did we already try, and what happened?
    prior = await db[COLLECTION].find(
        {"tenant_id": tenant_id, "record_id": record_id,
         "state": {"$in": [STATE_APPROVED, STATE_REJECTED, STATE_SUPERSEDED]}},
        {"_id": 0, "id": 1, "lane": 1, "state": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(5)
    context["prior_attempts"] = prior
    if prior:
        facts.append(_fact("Prior recovery attempts", len(prior), f"{record_kind}:{record_id}"))

    return context


# ------------------------------------------------------------------- the playbook

def _step(action: str, channel: str, detail: str) -> dict:
    return {"action": action, "channel": channel, "detail": detail}


def _value_currency(evidence: dict) -> str:
    """The currency a candidate's value is in. A candidate written before values carried
    a currency predates multi-currency cases and was always in the default."""
    return (recovery_case.normalize_currency(evidence.get("currency"))
            or recovery_case.DEFAULT_CURRENCY)


def value_band(value: Optional[float], currency: str) -> Optional[str]:
    """"high", "low", "mid", or None when there is no value or no thresholds for it."""
    band = VALUE_THRESHOLDS.get(currency)
    if value is None or band is None:
        return None
    if value >= band["high"]:
        return "high"
    if value < band["low"]:
        return "low"
    return "mid"


def select_lane(candidate: dict, context: dict) -> dict:
    """Pick a recovery lane from the ordered playbook.

    The first lane whose entry condition holds wins, and the returned `rule` names it.
    Every branch is a statement about a record we can cite; nothing here is a guess.
    """
    evidence = candidate.get("evidence") or {}
    item_type = candidate.get("type") or ""
    idle_days = evidence.get("idle_days")
    overdue_days = evidence.get("overdue_days")
    stage = str(evidence.get("stage") or "").lower()
    record_kind = context.get("record_kind") or "opportunity"

    try:
        value = float(evidence.get("value")) if evidence.get("value") is not None else None
    except (TypeError, ValueError):
        value = None
    currency = _value_currency(evidence)
    band = value_band(value, currency)
    thresholds = VALUE_THRESHOLDS.get(currency) or VALUE_THRESHOLDS[THRESHOLD_CURRENCY]

    owner = context.get("owner")
    has_contact = bool(context.get("contact_id"))

    # --- missed follow-up lanes ------------------------------------------------
    if item_type == second_chance.TYPE_MISSED_FOLLOWUP:
        if record_kind == "commitment":
            return {
                "lane": "commitment_repair",
                "rule": "missed_followup.commitment",
                "rationale": (
                    f"A commitment to this client is {overdue_days if overdue_days is not None else 'now'} "
                    f"day(s) overdue. Recovery starts by repairing the broken promise, not by "
                    f"opening a new sales motion."),
                "steps": [
                    _step("brief_owner", CHANNEL_INTERNAL,
                          "Brief the relationship owner on the overdue commitment and its history."),
                    _step("acknowledge_and_recommit", CHANNEL_EMAIL,
                          "Acknowledge the missed commitment and propose a specific new date."),
                    _step("set_new_commitment", CHANNEL_INTERNAL,
                          "Record the replacement commitment with an explicit due date and owner."),
                ],
            }
        return {
            "lane": "delivery_recovery",
            "rule": "missed_followup.task",
            "rationale": (
                f"A delivery task is {overdue_days if overdue_days is not None else 'now'} day(s) "
                f"overdue. The first move is internal: unblock or reassign the work before "
                f"anything is said to the client."),
            "steps": [
                _step("triage_task", CHANNEL_INTERNAL,
                      "Confirm whether the task is blocked, unassigned, or simply late."),
                _step("reassign_or_expedite", CHANNEL_INTERNAL,
                      "Reassign or expedite the task and record the new expectation."),
                _step("notify_client_if_visible", CHANNEL_EMAIL,
                      "If the delay is client-visible, send a short status update with a new date."),
            ],
        }

    # --- stalled lead lanes ----------------------------------------------------
    if context.get("open_commitments"):
        return {
            "lane": "commitment_repair_first",
            "rule": "stalled_lead.open_commitments",
            "rationale": (
                f"The relationship has {context['open_commitments']} open commitment(s). "
                f"Re-engaging on revenue while our own promises are outstanding is the wrong "
                f"order; clear those first."),
            "steps": [
                _step("review_open_commitments", CHANNEL_INTERNAL,
                      "Review every open commitment on the relationship and close or re-date it."),
                _step("brief_owner", CHANNEL_INTERNAL,
                      "Brief the owner before any re-engagement on the opportunity."),
            ],
        }

    # No value at all is treated as low, as it always was. A value in a currency with no
    # thresholds is *unbanded*: it is not assumed small, so it does not route a large
    # foreign-currency deal into nurture, and it is not assumed large either.
    if idle_days is not None and idle_days >= DORMANT_DAYS and (
            value is None or band == "low"):
        return {
            "lane": "dormant_nurture",
            "rule": "stalled_lead.dormant_low_value",
            "rationale": (
                f"Idle {idle_days} days with a value below {thresholds['low']:,.0f}. This does "
                f"not justify owner time; it belongs in a low-touch nurture motion until the "
                f"client signals interest."),
            "steps": [
                _step("mark_dormant", CHANNEL_INTERNAL,
                      "Move the opportunity to a dormant lane so it stops consuming pipeline attention."),
                _step("nurture_touch", CHANNEL_EMAIL,
                      "Add to a low-frequency nurture sequence with a single useful, non-pushy touch."),
            ],
        }

    if owner and (band == "high" or stage in LATE_STAGES):
        trigger = (f"Value at or above {thresholds['high']:,.0f}"
                   if band == "high"
                   else f"Late-stage opportunity ({stage or 'unknown'})")
        return {
            "lane": "owner_led_reengagement",
            "rule": "stalled_lead.high_value_or_late_stage",
            "rationale": (
                f"{trigger}, with a named relationship owner ({owner}). A deal this far along "
                f"is recovered by the person who owns the relationship, not by an automated "
                f"touch."),
            "steps": [
                _step("prepare_owner_brief", CHANNEL_INTERNAL,
                      "Assemble the account history, last contact, and open questions for the owner."),
                _step("owner_direct_outreach", CHANNEL_EMAIL,
                      "Owner sends a direct, personal message referencing the last real conversation."),
                _step("schedule_followup", CHANNEL_INTERNAL,
                      "Book a dated follow-up so this cannot stall silently a second time."),
            ],
        }

    if has_contact:
        return {
            "lane": "written_followup",
            "rule": "stalled_lead.known_contact",
            "rationale": (
                f"Idle {idle_days if idle_days is not None else 'an extended period'} day(s) at "
                f"stage '{stage or 'unknown'}' with a known contact. A short written follow-up "
                f"that asks a direct question is the proportionate next step."),
            "steps": [
                _step("draft_followup", CHANNEL_INTERNAL,
                      "Draft a short follow-up referencing the last recorded interaction."),
                _step("send_followup", CHANNEL_EMAIL,
                      "Send the follow-up and record the send against the opportunity."),
                _step("schedule_followup", CHANNEL_INTERNAL,
                      "Set a dated checkpoint for a reply."),
            ],
        }

    return {
        "lane": "needs_human_triage",
        "rule": "insufficient_context",
        "rationale": (
            "There is no relationship owner and no known contact on this record, so the system "
            "cannot propose a specific recovery motion. A person needs to establish who the "
            "counterparty is before any outreach is designed."),
        "steps": [
            _step("identify_counterparty", CHANNEL_INTERNAL,
                  "Identify the contact and owner for this opportunity, or close it as unworkable."),
        ],
    }


def _apply_channel_authority(steps: list[dict], channels: dict[str, dict]) -> list[dict]:
    """Mark each step ready or blocked. Blocking is a fact about the tenant's
    configuration, not a policy opinion, so the reason is copied verbatim."""
    resolved: list[dict] = []
    for step in steps:
        verdict = channels.get(step["channel"], {"authorized": False,
                                                 "reason": f"Unknown channel '{step['channel']}'."})
        resolved.append({**step,
                         "status": "ready" if verdict["authorized"] else "blocked",
                         "blocked_reason": None if verdict["authorized"] else verdict["reason"]})
    return resolved


# -------------------------------------------------------------------- composition

def candidate_from_case(case: dict) -> dict:
    """Express a Recovery Case in the shape the planner already understands.

    The planner was written against a work-queue candidate, and it works. Rather than
    rewrite 700 lines, a case is translated into that shape at the boundary. What this
    makes possible is the point of the whole slice: a case with no opportunity, no
    workspace and no contact — a missed call, say — can be planned for, because the
    translation carries whatever the case *does* have and omits what it does not.
    """
    evidence = dict(case.get("evidence") or {})
    if case.get("potential_value") is not None:
        evidence.setdefault("value", case["potential_value"])
        # The value thresholds downstream compare bare numbers, so the unit has to travel
        # with the number or a high-value lane is chosen on an amount whose currency the
        # planner never saw.
        evidence.setdefault("currency", case.get("currency")
                            or recovery_case.DEFAULT_CURRENCY)
    if case.get("external_identity"):
        evidence.setdefault("external_identity", case["external_identity"])
    # References the case has resolved override whatever the original detection evidence
    # carried. Without this, identity resolved after detection — the whole point of an
    # external case — never reaches the planner, and a known caller is still triaged as
    # an unknown one.
    for field in ("contact_id", "company_id"):
        if case.get(field):
            evidence[field] = case[field]

    # Sources map back onto the detector item types the playbook branches on. A source
    # with no established lane is left unmapped, so `select_lane` falls through to its
    # explicit human-triage branch rather than guessing a motion for it.
    item_type = {
        recovery_case.SOURCE_DORMANT_DEAL: second_chance.TYPE_STALLED_LEAD,
        recovery_case.SOURCE_MISSED_FOLLOWUP: second_chance.TYPE_MISSED_FOLLOWUP,
    }.get(case.get("source"))

    return {
        "id": case["id"],
        "tenant_id": case["tenant_id"],
        "type": item_type or f"recovery_case.{case.get('source')}",
        "payload": {
            # The detector's own record id where it has one, so a case-composed plan cites
            # the same record a queue-composed one did ("cmt_1", not "commitment:cmt_1").
            "record_id": (case.get("opportunity_id") or evidence.get("record_id")
                          or case.get("source_event_id")),
            "record_kind": evidence.get("record_kind") or (
                "opportunity" if case.get("opportunity_id") else case.get("source")),
            "title": case.get("title"),
            "reason": case.get("reason"),
        },
        "evidence": evidence,
        "workspace_id": case.get("workspace_id"),
        "recovery_case_id": case["id"],
    }


async def compose_for_case(db, tenant_id: str, case: dict, *,
                           actor: str = "recovery-composer",
                           channels: Optional[dict] = None) -> dict:
    """Plan for a Recovery Case, whatever it originated as.

    Returns the composed strategy and links it back onto the case, moving the case to
    `planned` (or `awaiting_approval` once its approval request exists) so the two records
    never disagree about how far the recovery has got.
    """
    if case.get("tenant_id") != tenant_id:
        raise recovery_case.CrossTenantReference(
            "Recovery case does not belong to this tenant")

    # Read the case's state from the database, not from the caller's copy, and refuse a
    # terminal one before anything is written. Composing first and letting the transition
    # fail afterwards still left a recovered or closed case holding a fresh plan and a
    # live approval for work nobody is going to do.
    current_case = await recovery_case.get_case(db, tenant_id, case["id"]) or {}
    current = current_case.get("state")
    if current in recovery_case.TERMINAL_STATES:
        raise recovery_case.InvalidCaseTransition(
            f"Cannot compose a strategy for a '{current}' recovery case")

    await _adopt_case_strategies(db, tenant_id, current_case or case, actor=actor)
    strategy = await compose_for_candidate(db, tenant_id, candidate_from_case(case),
                                           actor=actor, channels=channels)
    await recovery_case.attach(db, tenant_id=tenant_id, case_id=case["id"], actor=actor,
                               plan_reference=strategy["id"],
                               approval_reference=strategy.get("approval_id"))

    if strategy.get("state") == STATE_APPROVED:
        # The plan was already approved -- before this fix, approving a strategy never
        # moved its case, so cases sat in `awaiting_approval` behind an approved plan
        # forever. Bring the case up to the decision that was actually made.
        await sync_case_with_strategy(db, tenant_id, strategy, actor=actor)
        return strategy

    state_now = (await recovery_case.get_case(db, tenant_id, case["id"]) or {}).get("state")
    target = (recovery_case.AWAITING_APPROVAL if strategy.get("approval_id")
              else recovery_case.PLANNED)
    if state_now != target:
        try:
            await recovery_case.set_state(db, tenant_id=tenant_id, case_id=case["id"],
                                          state=target, actor=actor,
                                          detail={"lane": strategy["lane"],
                                                  "rule": strategy["rule"]})
        except recovery_case.InvalidCaseTransition:
            # A case already past planning is not dragged backwards by a recompose. Only
            # that is suppressed — a terminal case was refused above, before any write.
            pass
    return strategy


async def _adopt_case_strategies(db, tenant_id: str, case: dict, *, actor: str) -> None:
    """Make sure a case has at most one live strategy, keyed on the case itself.

    Strategies used to be keyed on whichever *work item* was being composed. A case's work
    item is resolved and replaced over its life, and a case with no work item was composed
    under the case's own id -- so one deal could hold two live strategies and two pending
    approvals for the same recovery. Strategies are now keyed on the case. A live one left
    over from the old keying (found by the case's id or its current work item) is re-keyed
    onto the case if the case has none, and every further one is superseded, its approval
    withdrawn.
    """
    keys = [key for key in (case.get("work_item_reference"),) if key]
    live = await db[COLLECTION].find(
        {"tenant_id": tenant_id, "active_candidate_key": {"$type": "string"},
         "$or": [{"recovery_case_id": case["id"]}, {"active_candidate_key": case["id"]},
                 *([{"active_candidate_key": {"$in": keys}}] if keys else [])]},
    ).sort("updated_at", -1).to_list(20)
    if not live:
        return
    keeper = next((s for s in live if s.get("active_candidate_key") == case["id"]), None)
    if keeper is None:
        # Prefer an approved plan -- an operator's decision is not discarded by a re-key.
        keeper = next((s for s in live if s.get("state") == STATE_APPROVED), live[0])
        await db[COLLECTION].update_one(
            {"_id": keeper["_id"]},
            {"$set": {"active_candidate_key": case["id"], "recovery_case_id": case["id"]}})
    for extra in live:
        if extra["_id"] == keeper["_id"]:
            continue
        if extra.get("approval_id"):
            try:
                await approval_queue.cancel(
                    db, tenant_id=tenant_id, approval_id=extra["approval_id"], actor=actor,
                    reason="Superseded: this recovery case already has a strategy.")
            except approval_queue.ApprovalError:
                pass
        await set_state(db, tenant_id, extra["id"], state=STATE_SUPERSEDED, actor=actor)


async def _case_for_strategy(db, tenant_id: str, strategy: dict) -> Optional[dict]:
    """The Recovery Case a strategy was composed for, however it was keyed."""
    if strategy.get("recovery_case_id"):
        case = await recovery_case.get_case(db, tenant_id, strategy["recovery_case_id"])
        if case:
            return case
    for criteria in ({"plan_reference": strategy["id"]},
                     {"work_item_reference": strategy.get("candidate_id")},
                     {"id": strategy.get("candidate_id")}):
        if not next(iter(criteria.values())):
            continue
        doc = await db[recovery_case.COLLECTION].find_one(
            {"tenant_id": tenant_id, **criteria}, {"_id": 0})
        if doc:
            return doc
    return None


async def sync_case_with_strategy(db, tenant_id: str, strategy: dict, *,
                                  actor: str = "recovery-composer",
                                  rationale: Optional[str] = None,
                                  audit: Optional[Callable[..., Awaitable[Any]]] = None,
                                  closer: Optional[Callable[..., Awaitable[dict]]] = None
                                  ) -> Optional[dict]:
    """Move a strategy's Recovery Case to match the decision taken on the strategy.

    Before this, approving a strategy changed the strategy and nothing else: the case
    stayed `awaiting_approval`, the runner only picks `approved` cases, and the pipeline
    stopped there. Now:

    * **approved** -> the case is `approved` (walked through `awaiting_approval` if it
      never got there), and its plan and approval are recorded on it;
    * **rejected** -> the case is closed as `strategy_rejected`. The playbook is
      deterministic, so re-planning would propose the same motion and ask the same
      question again; an operator who rejects the plan has declined this recovery;
    * **withdrawn** -> the case returns to `planned`, and the next composer sweep
      proposes afresh (a withdrawn request is "not this one", not "never").

    A decision on a strategy that is no longer the case's live plan does not move the
    case. Returns the case as it now stands, or None when no case is linked.
    """
    case = await _case_for_strategy(db, tenant_id, strategy)
    if not case or case.get("state") in recovery_case.TERMINAL_STATES:
        return case
    if case.get("plan_reference") not in (None, strategy["id"]):
        return case
    detail = {"strategy_id": strategy["id"], "approval_id": strategy.get("approval_id")}
    state = strategy.get("state")

    if state == STATE_APPROVED:
        approval = (await approval_queue.get(db, tenant_id, strategy["approval_id"])
                    if strategy.get("approval_id") else None)
        if not approval or approval.get("status") != approval_queue.APPROVED:
            return case
        if case.get("plan_reference") != strategy["id"] or \
                case.get("approval_reference") != strategy["approval_id"]:
            case = await recovery_case.attach(
                db, tenant_id=tenant_id, case_id=case["id"], actor=actor,
                plan_reference=strategy["id"], approval_reference=strategy["approval_id"])
        path = {recovery_case.DETECTED: [recovery_case.AWAITING_APPROVAL, recovery_case.APPROVED],
                recovery_case.PLANNED: [recovery_case.AWAITING_APPROVAL, recovery_case.APPROVED],
                recovery_case.AWAITING_APPROVAL: [recovery_case.APPROVED]}.get(case["state"], [])
        for target in path:
            case = await recovery_case.set_state(db, tenant_id=tenant_id, case_id=case["id"],
                                                 state=target, actor=actor, detail=detail,
                                                 audit=audit)
        return case

    if state == STATE_REJECTED:
        # `closer` is injected (the application passes the lifecycle's close, which also
        # resolves the case's work item) because the lifecycle module imports this one.
        close = closer or recovery_case.close_case
        return await close(db, tenant_id=tenant_id, case_id=case["id"],
                           reason="strategy_rejected", actor=actor, note=rationale,
                           detail=detail, audit=audit)

    if state == STATE_WITHDRAWN and case["state"] == recovery_case.AWAITING_APPROVAL:
        return await recovery_case.set_state(
            db, tenant_id=tenant_id, case_id=case["id"], state=recovery_case.PLANNED,
            actor=actor, detail={**detail, "note": "approval withdrawn; will be re-proposed"},
            audit=audit)
    return case


async def compose_for_candidate(db, tenant_id: str, candidate: dict, *,
                                actor: str = "recovery-composer",
                                channels: Optional[dict] = None) -> dict:
    """Compose one strategy, persist it, and raise its approval request.

    Returns the stored strategy. Nothing is executed and nothing is sent.
    """
    context = await gather_context(db, tenant_id, candidate)
    # Channel authority is tenant-wide, so a sweep computes it once and passes it in
    # rather than re-reading two collections for every candidate.
    channels = channels if channels is not None else await authorized_channels(db, tenant_id)
    lane = select_lane(candidate, context)
    steps = _apply_channel_authority(lane["steps"], channels)

    blocked_reasons = sorted({s["blocked_reason"] for s in steps if s["blocked_reason"]})
    candidate_id = candidate.get("id")
    now = _now()

    strategy = {
        "id": f"rcv_{uuid.uuid4().hex[:12]}",
        "tenant_id": tenant_id,
        "candidate_id": candidate_id,
        "candidate_type": candidate.get("type"),
        "record_id": context.get("record_id"),
        "record_kind": context.get("record_kind"),
        "workspace_id": context.get("workspace_id"),
        "title": (candidate.get("payload") or {}).get("title") or "Recovery candidate",
        "lane": lane["lane"],
        "rule": lane["rule"],
        "rationale": lane["rationale"],
        "steps": steps,
        "facts": context["facts"],
        "context": {k: v for k, v in context.items() if k != "facts"},
        "channel_authority": channels,
        "blocked_reasons": blocked_reasons,
        "executable": not blocked_reasons,
        "state": STATE_PROPOSED,
        "composed_by": actor,
        "created_at": _iso(now),
        "updated_at": _iso(now),
        "active_candidate_key": candidate_id,
        # The case this plan is for, when there is one. Proof reads the plan through it,
        # and it is how a decision on the strategy finds the case to move.
        "recovery_case_id": (candidate.get("recovery_case_id")
                             or (candidate.get("payload") or {}).get("recovery_case_id")),
        "approval_id": None,
    }

    existing = await db[COLLECTION].find_one(
        {"tenant_id": tenant_id, "active_candidate_key": candidate_id}) if candidate_id else None

    if existing and existing.get("state") == STATE_APPROVED:
        # An approved plan is not re-proposed. Nothing executes it yet, so a sweep that
        # recomposed here would reset an operator's decision to `proposed` and ask again
        # every hour. It stands until it is executed or withdrawn.
        await db[COLLECTION].update_one({"_id": existing["_id"]},
                                        {"$set": {"updated_at": _iso(now)}})
        return _public_strategy({**existing, "updated_at": _iso(now)})

    if existing and not _materially_changed(existing, strategy) and \
            await _approval_is_live(db, tenant_id, existing.get("approval_id")):
        # Same candidate, same recommendation, and its approval is still decidable: touch
        # the timestamp and leave the operator's pending decision alone. Re-raising would nag.
        await db[COLLECTION].update_one({"_id": existing["_id"]},
                                        {"$set": {"updated_at": _iso(now)}})
        return _public_strategy({**existing, "updated_at": _iso(now)})

    if existing:
        # The recommendation moved, so the old approval authorises an action we no
        # longer propose. An approval binds to a specific action; it cannot be inherited
        # by a different one. Withdraw it and ask again.
        strategy["id"] = existing["id"]
        strategy["created_at"] = existing.get("created_at", strategy["created_at"])
        strategy["superseded_at"] = _iso(now)
        if existing.get("approval_id"):
            try:
                await approval_queue.cancel(
                    db, tenant_id=tenant_id, approval_id=existing["approval_id"], actor=actor,
                    reason="Superseded: the composed recovery strategy changed.")
            except approval_queue.ApprovalError:
                # Already decided, expired or gone — nothing to withdraw.
                pass
        await db[COLLECTION].replace_one({"_id": existing["_id"]}, dict(strategy))
    else:
        await db[COLLECTION].insert_one(dict(strategy))

    approval = await approval_queue.request(
        db, tenant_id=tenant_id,
        title=f"Recovery strategy: {strategy['title']}",
        kind="recovery_strategy",
        actor=actor,
        requester_kind=approval_queue.REQUESTER_AGENT,
        summary=lane["rationale"],
        risk=_risk_for(strategy),
        action={"type": "recovery_strategy.execute", "strategy_id": strategy["id"],
                "lane": lane["lane"], "steps": steps},
        subject_type="recovery_strategy", subject_id=strategy["id"],
        workspace_id=strategy["workspace_id"],
        facts=context["facts"],
        blocked_reasons=blocked_reasons,
        dedupe_key=f"recovery_strategy:{strategy['id']}:{_fingerprint(strategy)}",
    )
    strategy["approval_id"] = approval["id"]
    await db[COLLECTION].update_one(
        {"id": strategy["id"], "tenant_id": tenant_id},
        {"$set": {"approval_id": approval["id"]}})

    return _public_strategy(strategy)


def _public_strategy(strategy: dict) -> dict:
    return {k: v for k, v in strategy.items() if k not in ("_id", "active_candidate_key")}


def _fingerprint(strategy: dict) -> str:
    """Identity of the *recommendation*, so a changed proposal cannot reuse an approval.

    The cited facts and the rationale are part of that identity, not decoration: an
    operator decides on the evidence shown, so evidence that moved within the same lane —
    idle days, value, open commitments — still makes this a different proposal. Leaving
    them out let a strategy keep displaying stale record-backed facts.
    """
    parts = [strategy.get("lane") or "", strategy.get("rule") or "",
             strategy.get("rationale") or ""]
    for step in strategy.get("steps") or []:
        parts.append(f"{step.get('action')}|{step.get('channel')}|{step.get('status')}")
    for fact in strategy.get("facts") or []:
        parts.append(f"{fact.get('label')}={fact.get('value')}@{fact.get('source')}")
    return uuid.uuid5(uuid.NAMESPACE_URL, "::".join(parts)).hex[:12]


async def _approval_is_live(db, tenant_id: str, approval_id: Optional[str]) -> bool:
    """Is this strategy's approval still something an operator can decide?

    If it lapsed — nobody decided it before `approval-expiry` swept it — the strategy would
    otherwise sit `proposed` forever behind a request that can never be approved, and its
    candidate would never be proposed again. A closed approval means recompose and re-ask.
    """
    if not approval_id:
        return False
    approval = await approval_queue.get(db, tenant_id, approval_id)
    return bool(approval) and approval.get("status") in (approval_queue.REQUESTED,
                                                         approval_queue.APPROVED)


def _materially_changed(existing: dict, composed: dict) -> bool:
    """True when the recommendation itself differs — not merely its timestamps."""
    if existing.get("state") != STATE_PROPOSED:
        return True
    if not existing.get("approval_id"):
        return True
    return _fingerprint(existing) != _fingerprint(composed) or \
        sorted(existing.get("blocked_reasons") or []) != sorted(composed.get("blocked_reasons") or [])


def _risk_for(strategy: dict) -> str:
    """Risk follows what the strategy would actually do, not how it feels.

    Anything that would reach the client is at least medium; a strategy that stays
    inside the CRM is low.
    """
    channels = {s["channel"] for s in strategy["steps"]}
    if channels - {CHANNEL_INTERNAL}:
        return approval_queue.RISK_HIGH if CHANNEL_PHONE in channels else approval_queue.RISK_MEDIUM
    return approval_queue.RISK_LOW


async def compose_for_tenant(db, queue, tenant_id: str, *, actor: str = "recovery-composer",
                             limit: int = COMPOSE_LIMIT) -> dict:
    """Compose a strategy for every open candidate without one.

    Two populations, because they arrive by two routes. Second Chance detections sit on
    the durable queue; a case from a source that was never a CRM record — a missed call, a
    web enquiry — has no queue item, and sweeping only the queue would leave exactly the
    sources this slice exists to serve permanently unplanned.
    """
    candidates = await queue.list_items(tenant_id=tenant_id, status="open",
                                        queue=second_chance.QUEUE_NAME, limit=limit)
    channels = await authorized_channels(db, tenant_id)
    composed, errors = [], []
    planned_case_ids: set[str] = set()
    skipped: dict[str, int] = {"terminal_case": 0, "already_past_approval": 0}
    for candidate in candidates:
        case_id = (candidate.get("payload") or {}).get("recovery_case_id")
        try:
            case = await recovery_case.get_case(db, tenant_id, case_id) if case_id else None
            if case is None:
                # A queue item that never had a case (created by a caller with no
                # database handle) is planned as it always was.
                composed.append(await compose_for_candidate(
                    db, tenant_id, candidate, actor=actor, channels=channels))
                continue
            planned_case_ids.add(case["id"])
            if case["state"] in recovery_case.TERMINAL_STATES:
                skipped["terminal_case"] += 1
                continue
            if case["state"] not in PLANNABLE_CASE_STATES:
                skipped["already_past_approval"] += 1
                continue
            # Planned *through its case*, so the plan is keyed on the case and attached
            # to it. Composing the queue item directly left the case unplanned, and the
            # next sweep composed it again under the case's id -- two live strategies and
            # two approval requests for one recovery.
            composed.append(await compose_for_case(db, tenant_id, case, actor=actor,
                                                   channels=channels))
        except Exception as exc:  # one bad candidate must not stop the sweep
            errors.append({"candidate_id": candidate.get("id"), "error": str(exc)[:300]})

    remaining = max(0, limit - len(candidates))
    cases = (await recovery_case.list_unplanned(db, tenant_id, limit=remaining)
             if remaining else [])
    # A case whose approval lapsed or was withdrawn is waiting on a request nobody can
    # decide any more. It is re-proposed here, or it would wait for ever.
    stale = await _cases_awaiting_a_dead_approval(
        db, tenant_id, limit=max(0, remaining - len(cases)))
    for case in cases + stale:
        if case["id"] in planned_case_ids:
            continue
        planned_case_ids.add(case["id"])
        approval_status = case.pop("_approval_status", None)
        try:
            if approval_status == approval_queue.REJECTED:
                # Rejected before a rejection closed the case: apply it now rather than
                # proposing the same plan again.
                plan = (await get_strategy(db, tenant_id, case["plan_reference"])
                        if case.get("plan_reference") else None)
                if plan:
                    await sync_case_with_strategy(db, tenant_id,
                                                  {**plan, "state": STATE_REJECTED},
                                                  actor=actor)
                    continue
            composed.append(await compose_for_case(db, tenant_id, case, actor=actor,
                                                   channels=channels))
        except Exception as exc:  # one bad case must not stop the sweep
            errors.append({"candidate_id": case.get("id"), "error": str(exc)[:300]})

    blocked = [s for s in composed if s["blocked_reasons"]]
    lanes: dict[str, int] = {}
    for strategy in composed:
        lanes[strategy["lane"]] = lanes.get(strategy["lane"], 0) + 1
    return {
        "tenant_id": tenant_id,
        "candidates_examined": len(candidates) + len(cases) + len(stale),
        "queue_candidates_examined": len(candidates),
        "recovery_cases_examined": len(cases),
        "stale_approvals_reproposed": len(stale),
        "skipped": skipped,
        "strategies_composed": len(composed),
        "strategies_blocked": len(blocked),
        "lanes": lanes,
        "errors": errors,
    }


# A case in one of these states may be (re)planned. Past them the plan is approved and in
# execution, and recomposing would only re-ask a question that has been answered.
PLANNABLE_CASE_STATES = (recovery_case.DETECTED, recovery_case.PLANNED,
                         recovery_case.AWAITING_APPROVAL)


async def _cases_awaiting_a_dead_approval(db, tenant_id: str, *, limit: int) -> list[dict]:
    """Planned or awaiting-approval cases whose approval is no longer pending.

    Three ways a case gets here, all of them a case nothing would otherwise move: its
    approval lapsed or was withdrawn (re-propose), or it was approved or rejected before
    a decision moved the case (bring the case up to that decision).
    """
    if limit <= 0:
        return []
    rows = await db[recovery_case.COLLECTION].find(
        {"tenant_id": tenant_id,
         "state": {"$in": [recovery_case.PLANNED, recovery_case.AWAITING_APPROVAL]}},
        {"_id": 0}).sort("updated_at", 1).to_list(int(limit) * 4)
    stale = []
    for row in rows:
        approval = (await approval_queue.get(db, tenant_id, row["approval_reference"])
                    if row.get("approval_reference") else None)
        if approval and approval.get("status") == approval_queue.REQUESTED:
            continue
        stale.append({**row, "_approval_status": (approval or {}).get("status")})
        if len(stale) >= limit:
            break
    return stale


async def compose_all_tenants(db, queue, *, actor: str = "cron") -> dict:
    tenant_ids = await db.tenants.distinct("tenant_id")
    summaries = []
    for tenant_id in tenant_ids:
        try:
            summaries.append(await compose_for_tenant(db, queue, tenant_id, actor=actor))
        except Exception as exc:
            summaries.append({"tenant_id": tenant_id, "error": str(exc)[:300]})
    return {"tenants": len(tenant_ids), "summaries": summaries}


async def list_strategies(db, tenant_id: str, *, state: Optional[str] = None,
                          lane: Optional[str] = None, limit: int = 100) -> list[dict]:
    criteria: dict[str, Any] = {"tenant_id": tenant_id}
    if state and state != "all":
        criteria["state"] = state
    if lane:
        criteria["lane"] = lane
    docs = await db[COLLECTION].find(
        criteria, {"_id": 0, "active_candidate_key": 0}
    ).sort("created_at", -1).to_list(int(limit))
    return docs


async def get_strategy(db, tenant_id: str, strategy_id: str) -> Optional[dict]:
    return await db[COLLECTION].find_one(
        {"id": strategy_id, "tenant_id": tenant_id}, {"_id": 0, "active_candidate_key": 0})


async def set_state(db, tenant_id: str, strategy_id: str, *, state: str, actor: str) -> dict:
    """Record the outcome of the approval decision on the strategy itself."""
    if state not in (STATE_APPROVED, STATE_REJECTED, STATE_WITHDRAWN, STATE_SUPERSEDED):
        raise RecoveryStrategyError(f"Unsupported strategy state '{state}'")
    update: dict[str, Any] = {"state": state, "updated_at": _iso(_now()),
                              "state_set_by": actor}
    unset: dict[str, Any] = {}
    if state != STATE_APPROVED:
        # A closed strategy releases its candidate so a later sweep may propose afresh.
        unset["active_candidate_key"] = ""
    updated = await db[COLLECTION].find_one_and_update(
        {"id": strategy_id, "tenant_id": tenant_id},
        {"$set": update, **({"$unset": unset} if unset else {})},
        return_document=True,
    )
    if not updated:
        raise RecoveryStrategyError("Strategy not found")
    return {k: v for k, v in updated.items() if k not in ("_id", "active_candidate_key")}


async def summary(db, tenant_id: str) -> dict:
    by_state: dict[str, int] = {}
    async for row in db[COLLECTION].aggregate([
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {"_id": "$state", "count": {"$sum": 1}}},
    ]):
        by_state[row["_id"] or STATE_PROPOSED] = row["count"]

    by_lane: dict[str, int] = {}
    async for row in db[COLLECTION].aggregate([
        {"$match": {"tenant_id": tenant_id, "state": STATE_PROPOSED}},
        {"$group": {"_id": "$lane", "count": {"$sum": 1}}},
    ]):
        by_lane[row["_id"] or "unknown"] = row["count"]

    blocked = await db[COLLECTION].count_documents(
        {"tenant_id": tenant_id, "state": STATE_PROPOSED, "blocked_reasons.0": {"$exists": True}})
    return {
        "tenant_id": tenant_id,
        "proposed": by_state.get(STATE_PROPOSED, 0),
        "proposed_blocked": blocked,
        "by_state": by_state,
        "by_lane": by_lane,
    }
