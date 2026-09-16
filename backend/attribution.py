"""Recovery attribution ledger — what was recovered, and whether we may claim credit.

Attribution is a *causal claim*, and this module exists because that claim is the easiest
thing in the product to get wrong in our own favour. A case that reaches `recovered` says
money came back. It does not say ClientVerse brought it back. A client who was going to
call anyway, a deal an account manager closed without ever opening the queue, a recovery
that happened while every outbound step sat blocked at the provider boundary — all three
land in exactly the same case state.

So the ledger records two things separately and never lets one imply the other:

1. **The outcome** — recovered, lost, or still pending, with the money kept in the shape
   `recovery_case` already enforces: confirmed value is evidence-backed actual revenue,
   potential value is an estimate and nothing more. They are never added together, and
   neither is ever summed across currencies.

2. **The basis** — what we can actually show about our own involvement. The basis is
   *derived from the record*, never taken from the caller, with one deliberate exception:
   an operator may assert a recovery was ours, and that assertion is stored as a human
   claim, labelled as one, and never silently promoted to machine-verified.

The rule that does the real work is `_derive_basis`: a basis that depends on outreach
having reached somebody is refused unless a message exists in a state that means it
actually left the building. No provider adapter exists yet (§8 #26), so no message can
reach `sent` or `delivered`, so `outreach_delivered` and `counterparty_replied` are
unreachable today **by construction**. That is the correct answer, not a gap to paper
over: the ledger reports zero outreach-attributed recovery because there has been zero
outreach. When an adapter lands, the same rule starts returning those bases on the same
evidence, and nothing here needs rewriting.

This module does not decide that a recovery happened — `recovery_case.confirm_recovery`
does, and it already demands evidence. This reads that decision and asks what we are
entitled to say about it.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

import conversations
import recovery_case

COLLECTION = "recovery_attributions"

# ------------------------------------------------------------------- outcomes

OUTCOME_PENDING = "pending"
OUTCOME_RECOVERED = "recovered"
OUTCOME_LOST = "lost"
OUTCOMES = (OUTCOME_PENDING, OUTCOME_RECOVERED, OUTCOME_LOST)

# Which case states mean which outcome. Derived from the case, so the ledger cannot drift
# from the state machine that owns the truth.
_OUTCOME_FOR_CASE_STATE = {
    recovery_case.RECOVERED: OUTCOME_RECOVERED,
    recovery_case.CLOSED: OUTCOME_LOST,
    recovery_case.FAILED: OUTCOME_LOST,
}

# --------------------------------------------------------------------- bases

# Ordered weakest to strongest. Order matters: `_derive_basis` returns the strongest one
# the evidence supports, and nothing else may promote a record up this list.
BASIS_NONE = "none"
BASIS_INTERNAL_ONLY = "internal_only"
BASIS_OUTREACH_DELIVERED = "outreach_delivered"
BASIS_COUNTERPARTY_REPLIED = "counterparty_replied"
BASIS_OPERATOR_ASSERTED = "operator_asserted"

BASES = (BASIS_NONE, BASIS_INTERNAL_ONLY, BASIS_OUTREACH_DELIVERED,
         BASIS_COUNTERPARTY_REPLIED, BASIS_OPERATOR_ASSERTED)

# Bases that require an outbound message to have actually left the system. Kept as a set
# so the delivery check has one definition rather than a condition repeated per branch.
_REQUIRES_DELIVERY = {BASIS_OUTREACH_DELIVERED, BASIS_COUNTERPARTY_REPLIED}

# Message states that mean a message genuinely reached the provider or beyond. `sending`
# is not here: it means we are mid-dispatch. `outcome_unknown` is not here either — it
# exists precisely because nobody knows, and a maybe-sent message is not evidence.
DELIVERED_STATES = (conversations.SENT, conversations.DELIVERED)

# Human-readable why, so an operator reading the ledger is told what the claim rests on
# rather than having to infer it from a slug.
BASIS_EXPLANATION = {
    BASIS_NONE: "No ClientVerse intervention reached anyone for this case.",
    BASIS_INTERNAL_ONLY:
        "Only internal steps ran. ClientVerse put the work in front of a person; "
        "no message was sent to the counterparty.",
    BASIS_OUTREACH_DELIVERED:
        "An outbound message for this case reached the provider.",
    BASIS_COUNTERPARTY_REPLIED:
        "The counterparty replied after an outbound message for this case was sent.",
    BASIS_OPERATOR_ASSERTED:
        "A person asserted this recovery was ours. Recorded as a human claim, "
        "not as machine-verified attribution.",
}


class AttributionError(Exception):
    """Raised for invalid attribution-ledger operations."""


class UnsupportedBasis(AttributionError):
    """Raised when a claimed basis is not supported by the evidence on record."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _public(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    return {k: v for k, v in doc.items() if k != "_id"}


def _history(action: str, actor: str, detail: Optional[dict] = None) -> dict:
    return {"action": action, "actor": actor, "at": _iso(_now()), "detail": detail or {}}


def _is_duplicate_key(exc: Exception) -> bool:
    return getattr(exc, "code", None) == 11000 or "E11000" in str(exc)


def _finite(value: Any) -> Optional[float]:
    """A usable amount, or None. Never raises — a malformed amount must not stop a sweep.

    `float()` admits nan and the infinities, and none of them are negative, so a sign
    check alone lets them through into every aggregate that touches them.
    """
    if value is None:
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(amount) or amount < 0:
        return None
    return amount


def period_of(timestamp: Optional[str]) -> Optional[str]:
    """The month a timestamp falls in, as `YYYY-MM`.

    Month, because recovery cycles are measured in weeks and a daily bucket would make
    every period a sample of one. Derived here rather than stored twice.
    """
    if not timestamp:
        return None
    return str(timestamp)[:7] or None


async def ensure_indexes(db) -> None:
    collection = db[COLLECTION]
    # One ledger entry per case. A case's outcome changes over time; it does not become a
    # second recovery. Enforced by the database so a concurrent sweep and a confirmation
    # cannot both create one.
    await collection.create_index([("tenant_id", 1), ("case_id", 1)], unique=True)
    await collection.create_index([("tenant_id", 1), ("outcome", 1), ("period", 1)])
    await collection.create_index([("tenant_id", 1), ("basis", 1)])
    await collection.create_index([("tenant_id", 1), ("lane", 1)])


# ------------------------------------------------------------------- evidence

async def gather_evidence(db, tenant_id: str, case: dict) -> dict:
    """Read what actually happened for a case. Facts only — no judgement, no claim.

    Everything `_derive_basis` is allowed to reason from comes from here, so the two stay
    separable: this can be inspected on its own, and a basis can always be traced back to
    the facts that produced it.
    """
    case_id = case["id"]

    strategy = None
    if case.get("plan_reference"):
        strategy = await db["recovery_strategies"].find_one(
            {"id": case["plan_reference"], "tenant_id": tenant_id}, {"_id": 0})

    # Internal work this system actually performed, as opposed to planned.
    internal_steps_run = await db.tasks.count_documents(
        {"tenant_id": tenant_id, "recovery_case_id": case_id})

    delivered, inbound_replies, blocked_outbound = 0, 0, 0
    conversation_id = case.get("conversation_reference")
    if conversation_id:
        messages = await db[conversations.MESSAGES].find(
            {"tenant_id": tenant_id, "conversation_id": conversation_id},
            {"_id": 0, "direction": 1, "status": 1, "created_at": 1, "sent_at": 1},
        ).to_list(500)

        outbound_sent_at = [
            m.get("sent_at") or m.get("created_at") for m in messages
            if m.get("direction") == conversations.OUTBOUND
            and m.get("status") in DELIVERED_STATES
        ]
        delivered = len(outbound_sent_at)
        blocked_outbound = sum(
            1 for m in messages
            if m.get("direction") == conversations.OUTBOUND
            and m.get("status") == conversations.BLOCKED)

        # A reply only counts if it arrived *after* something of ours went out. An inbound
        # message that predates our first send is the client contacting us on their own,
        # which is the opposite of us recovering them.
        if outbound_sent_at:
            first_send = min(t for t in outbound_sent_at if t)
            inbound_replies = sum(
                1 for m in messages
                if m.get("direction") == conversations.INBOUND
                and (m.get("created_at") or "") > first_send)

    return {
        "case_id": case_id,
        "internal_steps_run": internal_steps_run,
        "outbound_delivered": delivered,
        "outbound_blocked": blocked_outbound,
        "inbound_replies_after_outreach": inbound_replies,
        "lane": (strategy or {}).get("lane"),
        "rule": (strategy or {}).get("rule"),
        "plan_reference": case.get("plan_reference"),
        "conversation_reference": conversation_id,
    }


def _derive_basis(evidence: dict) -> str:
    """The strongest claim the evidence supports, and not one step further.

    Read this as the answer to "what are we entitled to say?", evaluated strongest-first.
    Nothing outside this function may raise a record's basis; `record_outcome` takes an
    operator's assertion, but stores it as an assertion rather than routing it through
    here.
    """
    if evidence.get("outbound_delivered"):
        if evidence.get("inbound_replies_after_outreach"):
            return BASIS_COUNTERPARTY_REPLIED
        return BASIS_OUTREACH_DELIVERED
    # No message left the system. Whatever else happened, we cannot claim to have reached
    # the counterparty — a blocked outbound step is a message that was never sent, and
    # counting it would turn the provider boundary into a source of credit.
    if evidence.get("internal_steps_run"):
        return BASIS_INTERNAL_ONLY
    return BASIS_NONE


def assert_basis_supported(basis: str, evidence: dict) -> None:
    """Refuse a claimed basis the evidence cannot carry."""
    if basis not in BASES:
        raise AttributionError(f"basis must be one of {BASES}")
    if basis in _REQUIRES_DELIVERY and not evidence.get("outbound_delivered"):
        raise UnsupportedBasis(
            f"'{basis}' requires an outbound message in {DELIVERED_STATES}; "
            f"this case has none")
    if basis == BASIS_INTERNAL_ONLY and not evidence.get("internal_steps_run"):
        raise UnsupportedBasis(
            "'internal_only' requires at least one internal step to have run")


# --------------------------------------------------------------- the ledger

async def record_outcome(db, *, tenant_id: str, case_id: str, actor: str = "system",
                         operator_assertion: Optional[str] = None,
                         audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    """Write or refresh this case's ledger entry from the case and its evidence.

    `operator_assertion` is a person saying "this one was ours" and must carry their
    reasoning. It is recorded alongside the derived basis, never instead of it, so the
    ledger can always report how much of its attributed revenue rests on a human's word.
    """
    case = await recovery_case.get_case(db, tenant_id, case_id)
    if not case:
        raise AttributionError(f"Recovery case '{case_id}' not found for this tenant")

    if operator_assertion is not None and not str(operator_assertion).strip():
        raise AttributionError(
            "An operator assertion must say why the recovery is attributable")

    evidence = await gather_evidence(db, tenant_id, case)
    derived = _derive_basis(evidence)
    outcome = _OUTCOME_FOR_CASE_STATE.get(case.get("state"), OUTCOME_PENDING)

    # Money, in the two shapes the case keeps strictly apart. Confirmed value is only ever
    # read from a recovered case: a pending or lost case has recovered nothing, whatever
    # may be sitting in the field.
    confirmed = _finite(case.get("confirmed_value")) if outcome == OUTCOME_RECOVERED else None
    potential = _finite(case.get("potential_value"))

    now = _now()
    # The period is when the outcome landed, not when the ledger noticed it — otherwise a
    # backfill would silently move last quarter's revenue into this one.
    decided_at = case.get("updated_at") if outcome != OUTCOME_PENDING else None

    fields = {
        "tenant_id": tenant_id,
        "case_id": case_id,
        "source": case.get("source"),
        "workspace_id": case.get("workspace_id"),
        "contact_id": case.get("contact_id"),
        "opportunity_id": case.get("opportunity_id"),
        "lane": evidence.get("lane"),
        "rule": evidence.get("rule"),
        "outcome": outcome,
        "case_state": case.get("state"),
        "basis": derived,
        "basis_explanation": BASIS_EXPLANATION[derived],
        # Kept apart, and never added to one another anywhere in this module.
        "confirmed_value": confirmed,
        "potential_value": potential,
        "currency": case.get("currency") or recovery_case.DEFAULT_CURRENCY,
        "confirmed_value_evidence": (
            case.get("confirmed_value_evidence") if outcome == OUTCOME_RECOVERED else None),
        "evidence": evidence,
        "decided_at": decided_at,
        "period": period_of(decided_at),
        "updated_at": _iso(now),
    }

    if operator_assertion is not None:
        fields["operator_assertion"] = {
            "asserted_by": actor,
            "reason": str(operator_assertion).strip()[:1000],
            "at": _iso(now),
        }

    existing = await db[COLLECTION].find_one({"tenant_id": tenant_id, "case_id": case_id})
    if existing:
        updated = await db[COLLECTION].find_one_and_update(
            {"tenant_id": tenant_id, "case_id": case_id},
            {"$set": fields,
             "$push": {"history": _history("refreshed", actor,
                                           {"outcome": outcome, "basis": derived})}},
            return_document=True)
        record = _public(updated)
    else:
        doc = {
            "id": f"att_{uuid.uuid4().hex[:12]}",
            **fields,
            "created_at": _iso(now),
            "history": [_history("recorded", actor,
                                 {"outcome": outcome, "basis": derived})],
        }
        try:
            await db[COLLECTION].insert_one(dict(doc))
            record = _public(doc)
        except Exception as exc:
            if not _is_duplicate_key(exc):
                raise
            # A concurrent writer got there first; its entry is as valid as ours.
            record = _public(await db[COLLECTION].find_one(
                {"tenant_id": tenant_id, "case_id": case_id}))

    if audit:
        await audit("recovery_attribution.recorded", "recovery_attribution",
                    record["id"], tenant_id, actor,
                    workspace_id=record.get("workspace_id"),
                    payload={"case_id": case_id, "outcome": outcome, "basis": derived})
    return record


async def assert_operator_attribution(db, *, tenant_id: str, case_id: str, actor: str,
                                      reason: str,
                                      audit: Optional[Callable[..., Awaitable[Any]]] = None
                                      ) -> dict:
    """Record a person's claim that a recovery was ours.

    Deliberately a separate entry point from `record_outcome`. A human assertion is a
    different kind of thing from a derived basis, and making the caller say so keeps it
    from being slipped in as though the system had verified it.
    """
    if not str(reason or "").strip():
        raise AttributionError(
            "An operator assertion must say why the recovery is attributable")
    return await record_outcome(db, tenant_id=tenant_id, case_id=case_id, actor=actor,
                                operator_assertion=reason, audit=audit)


async def get_for_case(db, tenant_id: str, case_id: str) -> Optional[dict]:
    return _public(await db[COLLECTION].find_one(
        {"tenant_id": tenant_id, "case_id": case_id}))


async def list_entries(db, tenant_id: str, *, outcome: Optional[str] = None,
                       basis: Optional[str] = None, lane: Optional[str] = None,
                       period: Optional[str] = None, limit: int = 100) -> list[dict]:
    criteria: dict[str, Any] = {"tenant_id": tenant_id}
    if outcome and outcome != "all":
        criteria["outcome"] = outcome
    if basis:
        criteria["basis"] = basis
    if lane:
        criteria["lane"] = lane
    if period:
        criteria["period"] = period
    docs = await db[COLLECTION].find(criteria, {"_id": 0}).sort(
        "updated_at", -1).to_list(max(1, min(int(limit), 500)))
    return docs


async def reconcile_tenant(db, tenant_id: str, *, actor: str = "attribution",
                           limit: int = 500,
                           audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    """Refresh the ledger for every case this tenant has.

    Runs over open cases too, so `pending` entries exist before an outcome lands and the
    ledger shows work in flight rather than only finished business.
    """
    cases = await recovery_case.list_cases(db, tenant_id, state="all", limit=limit)
    recorded, errors = 0, []
    for case in cases:
        try:
            await record_outcome(db, tenant_id=tenant_id, case_id=case["id"], actor=actor,
                                 audit=audit)
            recorded += 1
        except Exception as exc:  # one bad case must not stop the sweep
            errors.append({"case_id": case.get("id"), "error": str(exc)[:300]})
    return {"tenant_id": tenant_id, "cases_examined": len(cases),
            "entries_recorded": recorded, "errors": errors}


async def reconcile_all_tenants(db, *, actor: str = "cron") -> dict:
    tenant_ids = await db.tenants.distinct("tenant_id")
    summaries = []
    for tenant_id in tenant_ids:
        try:
            summaries.append(await reconcile_tenant(db, tenant_id, actor=actor))
        except Exception as exc:
            summaries.append({"tenant_id": tenant_id, "error": str(exc)[:300]})
    return {"tenants": len(tenant_ids), "summaries": summaries}


# ------------------------------------------------------------------ reporting

def _bucket(store: dict, key: Any, currency: str, amount: Optional[float]) -> None:
    """Add an amount to a (key, currency) bucket, creating it as needed."""
    if amount is None:
        return
    row = store.setdefault(key or "unknown", {})
    row[currency] = row.get(currency, 0.0) + amount


async def summary(db, tenant_id: str, *, period: Optional[str] = None) -> dict:
    """Recovered / lost / pending, per lane and per period, with the claim made explicit.

    Every money figure is a map keyed by currency. There is no grand total anywhere in
    this response, because across currencies there is no such number.
    """
    criteria: dict[str, Any] = {"tenant_id": tenant_id}
    if period:
        criteria["period"] = period
    entries = await db[COLLECTION].find(criteria, {"_id": 0}).to_list(10000)

    counts = {o: 0 for o in OUTCOMES}
    by_basis = {b: 0 for b in BASES}
    confirmed_by_currency: dict[str, float] = {}
    potential_open_by_currency: dict[str, float] = {}
    potential_lost_by_currency: dict[str, float] = {}
    confirmed_by_lane: dict[str, dict] = {}
    confirmed_by_period: dict[str, dict] = {}
    confirmed_by_basis: dict[str, dict] = {}
    attributed_confirmed: dict[str, float] = {}
    operator_asserted_confirmed: dict[str, float] = {}

    for entry in entries:
        outcome = entry.get("outcome") or OUTCOME_PENDING
        basis = entry.get("basis") or BASIS_NONE
        currency = entry.get("currency") or recovery_case.DEFAULT_CURRENCY
        counts[outcome] = counts.get(outcome, 0) + 1
        by_basis[basis] = by_basis.get(basis, 0) + 1

        confirmed = _finite(entry.get("confirmed_value"))
        potential = _finite(entry.get("potential_value"))

        if outcome == OUTCOME_RECOVERED and confirmed is not None:
            confirmed_by_currency[currency] = confirmed_by_currency.get(currency, 0.0) + confirmed
            _bucket(confirmed_by_lane, entry.get("lane"), currency, confirmed)
            _bucket(confirmed_by_period, entry.get("period"), currency, confirmed)
            _bucket(confirmed_by_basis, basis, currency, confirmed)
            # Revenue we may actually claim credit for: recovered AND with a basis that
            # says we did something that reached the client. This is the number the
            # product is tempted to inflate, so it is computed from the basis and nothing
            # else.
            if basis in _REQUIRES_DELIVERY:
                attributed_confirmed[currency] = (
                    attributed_confirmed.get(currency, 0.0) + confirmed)
            if entry.get("operator_assertion"):
                operator_asserted_confirmed[currency] = (
                    operator_asserted_confirmed.get(currency, 0.0) + confirmed)
        elif outcome == OUTCOME_LOST and potential is not None:
            potential_lost_by_currency[currency] = (
                potential_lost_by_currency.get(currency, 0.0) + potential)
        elif outcome == OUTCOME_PENDING and potential is not None:
            potential_open_by_currency[currency] = (
                potential_open_by_currency.get(currency, 0.0) + potential)

    return {
        "tenant_id": tenant_id,
        "period": period,
        "entries": len(entries),
        "counts": counts,
        "by_basis": by_basis,
        # Actual money, evidence-backed, per currency.
        "confirmed_recovered_by_currency": confirmed_by_currency,
        "confirmed_recovered_by_lane": confirmed_by_lane,
        "confirmed_recovered_by_period": confirmed_by_period,
        "confirmed_recovered_by_basis": confirmed_by_basis,
        # Estimates. Named so neither can be read as revenue.
        "potential_open_by_currency": potential_open_by_currency,
        "potential_lost_by_currency": potential_lost_by_currency,
        # The honest headline: recovered revenue we can show our own outreach caused.
        "attributable_to_outreach_by_currency": attributed_confirmed,
        "operator_asserted_by_currency": operator_asserted_confirmed,
        "attribution_note": (
            "'confirmed_recovered_*' is money recovered while a case was open; it is not a "
            "claim that ClientVerse caused it. Only "
            "'attributable_to_outreach_by_currency' is attributed revenue, and it requires "
            "an outbound message that actually reached the provider. No channel provider "
            "is registered (§8 #26), so that figure is zero by construction today."
        ),
    }
