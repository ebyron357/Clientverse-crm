"""Scheduled recovery follow-up (E-06; north-star step 9, "continue permitted follow-up").

The runner drafts a case's first outreach and stops. If that message reaches the client
and nothing comes back, the recovery should not simply end there -- a single unanswered
email is the most common way a recoverable opportunity is lost. This module is the
second and later touch: on a cadence, it drafts the next follow-up on the same thread.

It **drafts; it never sends.** Each follow-up is a new message with its own M-07
approval carrying the exact text, exactly like the runner's first draft, and it leaves
the CRM only through the same delivery choke point (channel authority, consent,
approval, provider). Automation here decides *when to ask a person*, not what reaches a
client.

WHEN A FOLLOW-UP IS DUE, AND EVERY REASON IT IS NOT

A case is judged on its email thread's own records, and the verdict names why:

* ``replied``                 -- the client wrote back after we reached them. A reply is
                                 a person's to handle; automation stops.
* ``handed_to_human``         -- someone took the thread over (the E-10 boundary).
* ``conversation_closed``     -- someone closed the thread.
* ``consent_not_granted``     -- consent is not (or no longer) granted.
* ``previous_followup_pending`` -- an earlier follow-up is still waiting on a decision
                                 or a send; stacking a second on it would nag.
* ``limit_reached``           -- the tenant's maximum number of follow-ups was drafted.
* ``followups_disabled``      -- the tenant set the maximum to zero.
* ``case_not_active``         -- the case is not executing or engaged.
* ``no_contact_yet``          -- nothing on the case has reached the client, so there is
                                 nothing to follow up.
* ``not_due``                 -- contact happened, but the cadence has not elapsed.
* ``due``                     -- all of the above clear; a follow-up is drafted.

The cadence is measured from the most recent message that actually reached the client
(provider-accepted), never from a draft or an approval.

IDEMPOTENCY

Follow-up *n* on a case is drafted under the key ``recovery:<case>:followup:<n>``, so a
sweep that runs twice, or a queue that redelivers, adopts the draft already written
instead of producing a second one.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import approval_queue
import conversations
import recovery_case

logger = logging.getLogger("clientverse.recovery_followup")

SETTINGS_COLLECTION = "recovery_followup_settings"

DEFAULT_CADENCE_DAYS = 3
DEFAULT_MAX_FOLLOWUPS = 2
MAX_CADENCE_DAYS = 30
MAX_FOLLOWUPS_LIMIT = 5

DUE = "due"
DRAFTED = "drafted"
NOT_DUE = "not_due"
REPLIED = "replied"
HANDED_TO_HUMAN = "handed_to_human"
CONVERSATION_CLOSED = "conversation_closed"
CONSENT_NOT_GRANTED = "consent_not_granted"
PREVIOUS_PENDING = "previous_followup_pending"
LIMIT_REACHED = "limit_reached"
DISABLED = "followups_disabled"
CASE_NOT_ACTIVE = "case_not_active"
NO_CONTACT_YET = "no_contact_yet"
OUTCOME_RECORDED = "outcome_recorded"
KEY_CONFLICT = "followup_key_conflict"

# The ledger collection, named here rather than imported: attribution imports this
# module's neighbours, and the follow-up only needs to know whether an outcome exists.
ATTRIBUTION_COLLECTION = "attribution_entries"

ACTIVE_CASE_STATES = (recovery_case.EXECUTING, recovery_case.ENGAGED)
REACHED_STATES = (conversations.SENT, conversations.DELIVERED)
# A follow-up in any of these has not finished its course; a new one must not stack.
UNFINISHED_STATES = (conversations.DRAFT, conversations.PENDING_APPROVAL,
                     conversations.APPROVED, conversations.SENDING,
                     conversations.BLOCKED, conversations.OUTCOME_UNKNOWN)


class FollowupPolicyError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def followup_key(case_id: str, sequence: int) -> str:
    return f"recovery:{case_id}:followup:{sequence}"


def _followup_prefix(case_id: str) -> str:
    return f"recovery:{case_id}:followup:"


def case_thread_key(case_id: str) -> str:
    """The key the runner opens a case's email thread under (see recovery_runner)."""
    return f"recovery_case:{case_id}:{conversations.CHANNEL_EMAIL}"


async def ensure_indexes(db: Any) -> None:
    await db[SETTINGS_COLLECTION].create_index("tenant_id", unique=True)


# ------------------------------------------------------------------------ policy

async def get_policy(db: Any, tenant_id: str) -> dict:
    doc = await db[SETTINGS_COLLECTION].find_one({"tenant_id": tenant_id}, {"_id": 0})
    doc = doc or {}
    cadence = doc.get("cadence_days")
    maximum = doc.get("max_followups")
    return {
        "cadence_days": int(cadence) if cadence is not None else DEFAULT_CADENCE_DAYS,
        "max_followups": int(maximum) if maximum is not None else DEFAULT_MAX_FOLLOWUPS,
        "defaults": {"cadence_days": DEFAULT_CADENCE_DAYS,
                     "max_followups": DEFAULT_MAX_FOLLOWUPS},
        "updated_by": doc.get("updated_by"),
        "updated_at": doc.get("updated_at"),
    }


async def set_policy(db: Any, *, tenant_id: str, cadence_days: int, max_followups: int,
                     actor: str) -> dict:
    """Tenant configuration, not a per-call argument, for the same reason as the
    attribution window: a cadence a caller could set per request is a dial for
    contacting a client more often than the tenant decided."""
    if not (1 <= int(cadence_days) <= MAX_CADENCE_DAYS):
        raise FollowupPolicyError(f"cadence_days must be between 1 and {MAX_CADENCE_DAYS}")
    if not (0 <= int(max_followups) <= MAX_FOLLOWUPS_LIMIT):
        raise FollowupPolicyError(
            f"max_followups must be between 0 and {MAX_FOLLOWUPS_LIMIT} (0 disables)")
    await db[SETTINGS_COLLECTION].update_one(
        {"tenant_id": tenant_id},
        {"$set": {"cadence_days": int(cadence_days), "max_followups": int(max_followups),
                  "updated_by": actor, "updated_at": _iso(_now())},
         "$setOnInsert": {"tenant_id": tenant_id}},
        upsert=True)
    return await get_policy(db, tenant_id)


# ---------------------------------------------------------------------- verdicts

def _verdict(case: dict, status: str, reason: str, **extra: Any) -> dict:
    return {"case_id": case["id"], "status": status, "reason": reason,
            "title": case.get("title"), "workspace_id": case.get("workspace_id"),
            **extra}


def _reached_at(message: dict) -> Optional[datetime]:
    return _parse(message.get("delivered_at") or message.get("sent_at"))


async def assess_case(db: Any, tenant_id: str, case: dict, policy: dict,
                      now: Optional[datetime] = None) -> dict:
    """Decide whether this case is due a follow-up, and say why if it is not.

    Reads only; writes nothing.
    """
    now = now or _now()
    if case.get("state") not in ACTIVE_CASE_STATES:
        return _verdict(case, CASE_NOT_ACTIVE,
                        f"The case is '{case.get('state')}', not executing or engaged.")

    conversation = await conversations.find_conversation_by_external_thread(
        db, tenant_id, conversations.CHANNEL_EMAIL, case_thread_key(case["id"]))
    if not conversation:
        return _verdict(case, NO_CONTACT_YET, "The case has no email thread yet.")
    extra: dict[str, Any] = {"conversation_id": conversation["id"]}

    if conversation.get("status") == conversations.STATUS_CLOSED:
        return _verdict(case, CONVERSATION_CLOSED, "Someone closed the thread.", **extra)
    if conversation.get("handled_by") != conversations.HANDLED_BY_AGENT:
        return _verdict(case, HANDED_TO_HUMAN,
                        "A person has taken this thread over; automation stops here.", **extra)
    consent = (conversation.get("consent") or {}).get("state")
    if consent != conversations.CONSENT_GRANTED:
        return _verdict(case, CONSENT_NOT_GRANTED,
                        f"Consent on this thread is '{consent}', not granted.", **extra)

    if await db[ATTRIBUTION_COLLECTION].find_one({"tenant_id": tenant_id,
                                                  "case_id": case["id"]}, {"_id": 1}):
        # Money arrived (credited to outreach or not): chasing "no reply" is over.
        return _verdict(case, OUTCOME_RECORDED,
                        "An outcome is recorded on this case; follow-ups stop.", **extra)
    if case.get("reply_count") or case.get("last_reply_at"):
        return _verdict(case, REPLIED,
                        "The case has recorded a reply from the client.", **extra)

    messages = await conversations.list_messages(db, tenant_id, conversation["id"])
    reached = [m for m in messages if m.get("direction") == conversations.OUTBOUND
               and m.get("status") in REACHED_STATES and _reached_at(m)]
    if not reached:
        return _verdict(case, NO_CONTACT_YET,
                        "Nothing on this case has reached the client yet.", **extra)
    reached.sort(key=lambda m: _reached_at(m) or now)
    last = reached[-1]
    last_contact = _reached_at(last)
    extra["last_contact_at"] = _iso(last_contact) if last_contact else None
    # A reply counts from when our first message was created, not from when its delivery
    # was confirmed: a message recorded `sent` only after reconciliation, or with a late
    # receipt, carries a later timestamp than the reply it drew.
    first_attempt = min((_parse(m.get("created_at")) or _reached_at(m) or now) for m in reached)

    replies = [m for m in messages if m.get("direction") == conversations.INBOUND
               and (_parse(m.get("created_at")) or now) >= first_attempt]
    if replies:
        return _verdict(case, REPLIED,
                        "The client replied; a person should take it from here.",
                        reply_message_id=replies[-1]["id"], **extra)

    prefix = _followup_prefix(case["id"])
    # Only the automation's own drafts on this thread: a person's message carrying the
    # same key is not a follow-up, and must not count toward (or block) the sequence.
    followups = [m for m in messages if str(m.get("idempotency_key") or "").startswith(prefix)
                 and m.get("author_kind") == approval_queue.REQUESTER_AGENT]
    extra["followups_drafted"] = len(followups)
    pending = [m for m in followups if m.get("status") in UNFINISHED_STATES]
    if pending:
        return _verdict(case, PREVIOUS_PENDING,
                        f"Follow-up {pending[0]['id']} is still '{pending[0]['status']}'.",
                        pending_message_id=pending[0]["id"], **extra)

    maximum = int(policy["max_followups"])
    if maximum == 0:
        return _verdict(case, DISABLED, "This tenant has follow-ups turned off.", **extra)
    if len(followups) >= maximum:
        return _verdict(case, LIMIT_REACHED,
                        f"{len(followups)} of {maximum} follow-ups already drafted.", **extra)

    due_at = (last_contact or now) + timedelta(days=int(policy["cadence_days"]))
    extra["due_at"] = _iso(due_at)
    if now < due_at:
        return _verdict(case, NOT_DUE,
                        f"No reply yet; the next follow-up is due {_iso(due_at)}.", **extra)

    to_address = last.get("to_address") or next(
        (p.get("address") for p in conversation.get("participants") or []
         if p.get("kind") == conversations.PARTICIPANT_CONTACT
         and "@" in str(p.get("address") or "")), None)
    return _verdict(case, DUE,
                    f"No reply {int(policy['cadence_days'])} day(s) after contact.",
                    sequence=len(followups) + 1, max_followups=maximum,
                    to_address=to_address, **extra)


def _draft_body(case: dict, verdict: dict) -> str:
    """The text a person will be asked to approve -- a statement of intent, like the
    runner's first draft, not generated prose presented as finished."""
    lines = [
        f"[DRAFT — follow-up {verdict['sequence']} of {verdict['max_followups']}, "
        "prepared by ClientVerse]",
        "",
        f"Our last message on this recovery reached the client on "
        f"{verdict.get('last_contact_at')} and has had no reply.",
        "",
        f"Recovery reason: {case.get('reason')}",
        "Intended next step: a short, polite follow-up that refers to the previous "
        "message and offers a simple way to respond.",
        "",
        "This text has not been sent. It requires approval, an authorised channel, "
        "and a registered delivery provider before it can leave the CRM.",
    ]
    return "\n".join(lines)


class FollowupKeyConflict(Exception):
    """The follow-up's key already names a message that is not this follow-up."""


async def draft_followup(db: Any, tenant_id: str, case: dict, verdict: dict, *,
                         actor: str = "recovery-followup",
                         audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    """Draft the follow-up a DUE verdict describes, and raise its approval."""
    if verdict.get("status") != DUE:
        raise ValueError("only a due verdict can be drafted")
    key = followup_key(case["id"], int(verdict["sequence"]))
    conversation = await conversations.get_conversation(db, tenant_id,
                                                        verdict["conversation_id"])
    subject = (conversation or {}).get("subject") or "Recovery"
    message = await conversations.draft_message(
        db, tenant_id=tenant_id, conversation_id=verdict["conversation_id"],
        body=_draft_body(case, verdict), actor=actor,
        subject=subject if subject.lower().startswith("re:") else f"Re: {subject}",
        to_address=verdict.get("to_address"), idempotency_key=key,
        requester_kind=approval_queue.REQUESTER_AGENT)
    if message.get("conversation_id") != verdict["conversation_id"] or \
            message.get("author_kind") != approval_queue.REQUESTER_AGENT:
        # The key was taken by someone else's message (another thread, or a person's
        # draft). Adopting it would raise that text for approval under this name.
        raise FollowupKeyConflict(
            f"Key {key} already belongs to message {message.get('id')}, which is not this "
            "case's follow-up")
    if message.get("status") == conversations.DRAFT:
        message = await conversations.request_approval(
            db, tenant_id=tenant_id, message_id=message["id"], actor=actor)
    if audit and not message.get("deduplicated"):
        await audit("recovery_case.followup_drafted", "recovery_case", case["id"], tenant_id,
                    actor, workspace_id=case.get("workspace_id"),
                    payload={"message_id": message["id"],
                             "approval_id": message.get("approval_id"),
                             "sequence": verdict["sequence"]})
    return message


# ------------------------------------------------------------------------ sweeps

async def _active_cases(db: Any, tenant_id: str, limit: int) -> list[dict]:
    # Least recently checked first, so each sweep moves on. Ordering by `updated_at`
    # re-read the same oldest cases every run -- drafting does not touch the case -- and
    # a tenant with more finished cases than the limit never reached a due one.
    rows: list[dict] = await db[recovery_case.COLLECTION].find(
        {"tenant_id": tenant_id, "state": {"$in": list(ACTIVE_CASE_STATES)}},
        {"_id": 0}).sort([("followup_checked_at", 1), ("updated_at", 1)]).to_list(
            max(1, int(limit)))
    return rows


async def preview(db: Any, tenant_id: str, *, now: Optional[datetime] = None,
                  limit: int = 200) -> dict:
    """Every active case's verdict, without drafting anything."""
    policy = await get_policy(db, tenant_id)
    verdicts = [await assess_case(db, tenant_id, case, policy, now)
                for case in await _active_cases(db, tenant_id, limit)]
    by_status: dict[str, int] = {}
    for verdict in verdicts:
        by_status[verdict["status"]] = by_status.get(verdict["status"], 0) + 1
    return {"tenant_id": tenant_id, "policy": policy, "by_status": by_status,
            "cases": verdicts}


async def run_for_tenant(db: Any, tenant_id: str, *, actor: str = "recovery-followup",
                         now: Optional[datetime] = None, limit: int = 200,
                         audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    """Draft every due follow-up for one tenant. Drafting only: nothing is sent."""
    policy = await get_policy(db, tenant_id)
    drafted: list[dict] = []
    errors: list[dict] = []
    by_status: dict[str, int] = {}
    for case in await _active_cases(db, tenant_id, limit):
        verdict = await assess_case(db, tenant_id, case, policy, now)
        await db[recovery_case.COLLECTION].update_one(
            {"id": case["id"], "tenant_id": tenant_id},
            {"$set": {"followup_checked_at": _iso(_now())}})
        status = verdict["status"]
        if status == DUE:
            try:
                message = await draft_followup(db, tenant_id, case, verdict, actor=actor,
                                               audit=audit)
                drafted.append({"case_id": case["id"], "message_id": message["id"],
                                "approval_id": message.get("approval_id"),
                                "sequence": verdict["sequence"]})
                status = DRAFTED
            except FollowupKeyConflict as exc:
                logger.warning("Follow-up key conflict on case %s: %s", case["id"], exc)
                errors.append({"case_id": case["id"], "error": str(exc)[:300]})
                status = KEY_CONFLICT
            except Exception as exc:  # one case must not stop the sweep
                logger.exception("Could not draft a follow-up for case %s", case["id"])
                errors.append({"case_id": case["id"], "error": str(exc)[:300]})
                status = "error"
        by_status[status] = by_status.get(status, 0) + 1
    return {"tenant_id": tenant_id, "policy": {k: policy[k] for k in
                                               ("cadence_days", "max_followups")},
            "by_status": by_status, "drafted": drafted, "errors": errors,
            # Stated plainly, as the runner does: drafting reaches no one.
            "sent": 0}


async def run_all_tenants(db: Any, *, actor: str = "cron",
                          audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    tenant_ids = await db.tenants.distinct("tenant_id")
    summaries = []
    drafted = 0
    for tenant_id in tenant_ids:
        try:
            summary = await run_for_tenant(db, tenant_id, actor=actor, audit=audit)
            drafted += len(summary["drafted"])
            summaries.append(summary)
        except Exception as exc:  # one tenant must never block the sweep
            summaries.append({"tenant_id": tenant_id, "error": str(exc)[:300]})
    return {"tenants": len(tenant_ids), "drafted": drafted, "summaries": summaries}
