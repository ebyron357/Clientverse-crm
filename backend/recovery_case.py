"""Recovery Case — one identifiable revenue opportunity ClientVerse is trying to recover.

This module removes the assumption that a recovery opportunity must begin life as an
internal ClientVerse CRM record. Before it, detection read `db.opportunities`,
`db.commitments` and `db.tasks` directly, and the planner reached for a workspace and a
company to find an owner. A missed call has none of those. It has a tenant, a phone
number and a timestamp.

So there are two pieces here:

* **A normalized recovery event** — the smallest contract every source can be expressed
  in. A dormant deal and a missed call arrive in the same shape, differing only in which
  optional references they happen to carry.
* **The Recovery Case** — what that event becomes. It is not a second CRM deal, not a
  task, not a conversation and not an approval; those attach to it. It is the opportunity
  itself, tracked from detection through to recovered revenue.

Three properties are load-bearing:

1. **Unresolved references are legitimate.** `contact_id`, `company_id`, `opportunity_id`
   and `workspace_id` are all optional. A case may know only that *someone* on this number
   called and nobody called back. Identity resolution happens later, and `attach()` is
   where it lands — refusing, every time, to attach a record belonging to another tenant.

2. **Deduplication is enforced by the database.** The identity of a case is
   (tenant, source, source event). Two workers racing the same event produce one case;
   the loser is told it deduplicated rather than being handed a second case.

3. **Potential value is never confirmed revenue.** They are separate fields with separate
   provenance, and `confirm_recovery()` refuses to record a confirmed amount without
   evidence. An opportunity worth £40,000 that we are trying to recover has recovered
   nothing until something says it did.

This module deliberately does **not** execute, send, or attribute. It carries the states
those stages will use, and a state existing here is not a claim that the behaviour behind
it is built — §11 of the readiness report lists what is still missing.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Optional

COLLECTION = "recovery_cases"

# ------------------------------------------------------------------- sources

# The normalized event vocabulary. Only the first two have detectors today; the rest are
# declared so that a source added later enters the same pipeline rather than growing a
# parallel one.
SOURCE_DORMANT_DEAL = "dormant_deal"
SOURCE_MISSED_FOLLOWUP = "missed_followup"
SOURCE_MISSED_CALL = "missed_call"
SOURCE_WEB_ENQUIRY = "web_enquiry"
SOURCE_UNANSWERED_QUOTE = "unanswered_quote"
SOURCE_UNANSWERED_ESTIMATE = "unanswered_estimate"
SOURCE_NO_RESPONSE = "no_response"
SOURCE_APPOINTMENT_CANCELLED = "appointment_cancelled"
SOURCE_APPOINTMENT_NO_SHOW = "appointment_no_show"
SOURCE_EXTERNAL_CRM_EVENT = "external_crm_event"

SOURCES = (
    SOURCE_DORMANT_DEAL, SOURCE_MISSED_FOLLOWUP, SOURCE_MISSED_CALL, SOURCE_WEB_ENQUIRY,
    SOURCE_UNANSWERED_QUOTE, SOURCE_UNANSWERED_ESTIMATE, SOURCE_NO_RESPONSE,
    SOURCE_APPOINTMENT_CANCELLED, SOURCE_APPOINTMENT_NO_SHOW, SOURCE_EXTERNAL_CRM_EVENT,
)

# Sources that originate inside this CRM. The distinction matters because an internal
# source can be trusted to reference tenant-owned records, while an external one arrives
# with identifiers this system has not verified.
INTERNAL_SOURCES = (SOURCE_DORMANT_DEAL, SOURCE_MISSED_FOLLOWUP)

# External identity kinds — how a counterparty is known before a contact record exists.
IDENTITY_PHONE = "phone"
IDENTITY_EMAIL = "email"
IDENTITY_EXTERNAL_ID = "external_id"
IDENTITY_KINDS = (IDENTITY_PHONE, IDENTITY_EMAIL, IDENTITY_EXTERNAL_ID)

DEFAULT_CURRENCY = "USD"

# -------------------------------------------------------------------- states

DETECTED = "detected"
PLANNED = "planned"
AWAITING_APPROVAL = "awaiting_approval"
APPROVED = "approved"
EXECUTING = "executing"
ENGAGED = "engaged"
RECOVERED = "recovered"
CLOSED = "closed"
FAILED = "failed"

STATES = (DETECTED, PLANNED, AWAITING_APPROVAL, APPROVED, EXECUTING, ENGAGED,
          RECOVERED, CLOSED, FAILED)
OPEN_STATES = (DETECTED, PLANNED, AWAITING_APPROVAL, APPROVED, EXECUTING, ENGAGED)
TERMINAL_STATES = (RECOVERED, CLOSED, FAILED)

# Explicit matrix. Anything not listed is refused, so an invalid move fails loudly rather
# than quietly corrupting a case. Every open state may be closed or fail, because an
# operator can always abandon a recovery and a stage can always break.
_ALWAYS = {CLOSED, FAILED}
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    DETECTED: {PLANNED, AWAITING_APPROVAL} | _ALWAYS,
    # planned -> planned is a recomposition: the plan changed while the case stood still.
    PLANNED: {PLANNED, AWAITING_APPROVAL} | _ALWAYS,
    AWAITING_APPROVAL: {APPROVED, PLANNED} | _ALWAYS,
    APPROVED: {EXECUTING, PLANNED} | _ALWAYS,
    EXECUTING: {ENGAGED, APPROVED} | _ALWAYS,
    ENGAGED: {RECOVERED, EXECUTING} | _ALWAYS,
    RECOVERED: {CLOSED},
    CLOSED: set(),
    FAILED: {DETECTED},
}

# CRM records a normalized event may already point at, and the collection each lives in.
# These are the references an event can arrive carrying, so `open_case()` verifies them.
REFERENCE_COLLECTIONS = {
    "contact_id": "contacts",
    "company_id": "companies",
    "opportunity_id": "opportunities",
    "workspace_id": "workspaces",
}

# Records this system creates *for* a case and later staples back onto it. They are as
# tenant-scoped as the CRM records above, so attaching one is verified the same way —
# otherwise a caller could point a case at another tenant's plan, approval, conversation
# or queue item and the cross-tenant guarantee would hold only for half the fields.
ATTACHED_RECORD_COLLECTIONS = {
    "plan_reference": "recovery_strategies",
    "approval_reference": "approvals",
    "conversation_reference": "conversations",
    "work_item_reference": "work_queue",
}

# Everything `attach()` accepts, and where each one is checked.
ATTACHABLE_REFERENCES = {**REFERENCE_COLLECTIONS, **ATTACHED_RECORD_COLLECTIONS}

# An identity is looked up by its exact stored value and deduplicated on it, so it cannot
# be silently shortened. Descriptive text (a reason, a title) is trimmed instead, because
# nothing matches on it.
MAX_IDENTITY_LENGTH = 200


class RecoveryCaseError(Exception):
    """Raised for invalid recovery-case operations."""


class RecoveryCaseNotFound(RecoveryCaseError):
    pass


class InvalidCaseTransition(RecoveryCaseError):
    pass


class CrossTenantReference(RecoveryCaseError):
    """Raised when a case is asked to reference a record another tenant owns."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _amount(value: Any, label: str) -> float:
    """Convert to a usable amount, refusing the values that quietly poison a total.

    `float()` accepts `nan` and the infinities, and none of them are negative, so a bare
    `< 0` check lets them through. One of either in a case makes every aggregate that
    touches it non-finite, which is exactly the financial-integrity failure the separate
    potential/confirmed fields exist to prevent.
    """
    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise RecoveryCaseError(f"{label} must be a number")
    if not math.isfinite(amount):
        raise RecoveryCaseError(f"{label} must be a finite number")
    if amount < 0:
        raise RecoveryCaseError(f"{label} cannot be negative")
    return amount


def _history(action: str, actor: str, detail: Optional[dict] = None) -> dict:
    return {"action": action, "actor": actor, "at": _iso(_now()), "detail": detail or {}}


def _public(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    return {k: v for k, v in doc.items() if k != "_id"}


def _is_duplicate_key(exc: Exception) -> bool:
    return getattr(exc, "code", None) == 11000 or "E11000" in str(exc)


async def ensure_indexes(db) -> None:
    collection = db[COLLECTION]
    # Case identity is the source event. Enforced by the database so two workers racing
    # the same event cannot both create a case — an application-side check would not
    # survive concurrency.
    await collection.create_index(
        [("tenant_id", 1), ("source", 1), ("source_event_id", 1)], unique=True)
    await collection.create_index([("tenant_id", 1), ("state", 1), ("created_at", -1)])
    await collection.create_index([("tenant_id", 1), ("workspace_id", 1)])
    await collection.create_index([("tenant_id", 1), ("contact_id", 1)])
    await collection.create_index(
        [("tenant_id", 1), ("external_identity.kind", 1), ("external_identity.value", 1)])


# ------------------------------------------------------------ normalized event

def normalize_event(*, tenant_id: str, source: str, source_event_id: str, reason: str,
                    occurred_at: Optional[str] = None, workspace_id: Optional[str] = None,
                    contact_id: Optional[str] = None, company_id: Optional[str] = None,
                    opportunity_id: Optional[str] = None,
                    external_identity: Optional[dict] = None,
                    potential_value: Optional[float] = None,
                    currency: str = DEFAULT_CURRENCY,
                    evidence: Optional[dict] = None, title: Optional[str] = None) -> dict:
    """Put any source into the one shape the recovery pipeline accepts.

    Everything past `reason` is optional, and that is the point: a missed call carries a
    phone number and nothing else, while a dormant deal carries an opportunity, a company
    and a value. Both are valid events.
    """
    if not tenant_id:
        raise RecoveryCaseError("tenant_id is required")
    if source not in SOURCES:
        raise RecoveryCaseError(f"source must be one of {SOURCES}")
    if not str(source_event_id or "").strip():
        raise RecoveryCaseError("source_event_id is required")
    if not str(reason or "").strip():
        raise RecoveryCaseError("reason is required")

    identity = None
    if external_identity:
        kind = external_identity.get("kind")
        value = str(external_identity.get("value") or "").strip()
        if kind not in IDENTITY_KINDS:
            raise RecoveryCaseError(f"external identity kind must be one of {IDENTITY_KINDS}")
        if not value:
            raise RecoveryCaseError("external identity requires a value")
        if len(value) > MAX_IDENTITY_LENGTH:
            raise RecoveryCaseError(
                f"external identity value exceeds {MAX_IDENTITY_LENGTH} characters")
        identity = {"kind": kind, "value": value}

    if potential_value is not None:
        potential_value = _amount(potential_value, "potential_value")

    event_id = str(source_event_id).strip()
    if len(event_id) > MAX_IDENTITY_LENGTH:
        # Truncating here would change the case's identity. Two distinct events sharing a
        # long prefix would collapse into one case under the unique index, and
        # `find_by_source_event()` would then fail to find the case when handed the real
        # id. Refusing is the only option that keeps identity meaning what it says.
        raise RecoveryCaseError(
            f"source_event_id exceeds {MAX_IDENTITY_LENGTH} characters")

    return {
        "tenant_id": tenant_id,
        "source": source,
        "source_event_id": event_id,
        "reason": str(reason).strip()[:1000],
        "title": (str(title).strip()[:300] if title else None),
        "occurred_at": occurred_at or _iso(_now()),
        "workspace_id": workspace_id,
        "contact_id": contact_id,
        "company_id": company_id,
        "opportunity_id": opportunity_id,
        "external_identity": identity,
        "potential_value": potential_value,
        "currency": currency,
        "evidence": evidence or {},
    }


async def _assert_owned(db, tenant_id: str, field: str, value: Optional[str]) -> None:
    """Refuse a reference to a record this tenant does not own.

    Detectors pass ids they read from the tenant's own collections, but an external event
    carries identifiers this system has not verified. Checking here means no caller can
    staple another tenant's contact onto a case, however the id reached them.
    """
    if not value:
        return
    collection = ATTACHABLE_REFERENCES.get(field)
    if not collection:
        return
    if not await db[collection].find_one({"id": value, "tenant_id": tenant_id}, {"_id": 1}):
        raise CrossTenantReference(
            f"{field} '{value}' does not belong to tenant '{tenant_id}'")


async def open_case(db, event: dict, *, actor: str = "system",
                    audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    """Create the Recovery Case for a normalized event, or return the one that exists.

    `audit` is the application's own `record_event`; it is injected rather than imported
    so this module stays free of the FastAPI app, matching how the other domain modules
    are wired. Nothing here writes a parallel audit trail.
    """
    tenant_id = event["tenant_id"]
    # Four independent point lookups. Running them concurrently keeps a detection sweep
    # over hundreds of records from paying four serial round trips each.
    await asyncio.gather(*(
        _assert_owned(db, tenant_id, field, event.get(field))
        for field in REFERENCE_COLLECTIONS))

    now = _now()
    doc = {
        "id": f"rc_{uuid.uuid4().hex[:12]}",
        "tenant_id": tenant_id,
        "source": event["source"],
        "source_event_id": event["source_event_id"],
        "source_is_internal": event["source"] in INTERNAL_SOURCES,
        "reason": event["reason"],
        "title": event.get("title") or event["reason"][:120],
        "occurred_at": event.get("occurred_at") or _iso(now),
        "workspace_id": event.get("workspace_id"),
        "contact_id": event.get("contact_id"),
        "company_id": event.get("company_id"),
        "opportunity_id": event.get("opportunity_id"),
        "external_identity": event.get("external_identity"),
        # Two separate amounts that must never collapse into one. `potential_value` is
        # what might be recovered and carries the provenance of that estimate;
        # `confirmed_value` stays None until evidence of actual recovery arrives.
        "potential_value": event.get("potential_value"),
        "potential_value_source": (
            f"{event['source']}:{event['source_event_id']}"
            if event.get("potential_value") is not None else None),
        "confirmed_value": None,
        "confirmed_value_evidence": None,
        "currency": event.get("currency") or DEFAULT_CURRENCY,
        "state": DETECTED,
        "evidence": event.get("evidence") or {},
        "plan_reference": None,
        "approval_reference": None,
        "conversation_reference": None,
        "work_item_reference": None,
        "outcome": None,
        "created_at": _iso(now),
        "updated_at": _iso(now),
        "history": [_history("detected", actor, {"source": event["source"],
                                                 "source_event_id": event["source_event_id"]})],
    }

    try:
        await db[COLLECTION].insert_one(dict(doc))
    except Exception as exc:
        if not _is_duplicate_key(exc):
            raise
        # Another worker got there first. Hand back its case rather than a second one.
        existing = await db[COLLECTION].find_one(
            {"tenant_id": tenant_id, "source": event["source"],
             "source_event_id": event["source_event_id"]})
        if existing:
            result = _public(existing)
            result["deduplicated"] = True
            return result
        raise

    if audit:
        await audit("recovery_case.detected", "recovery_case", doc["id"], tenant_id, actor,
                    workspace_id=doc.get("workspace_id"),
                    payload={"source": doc["source"], "source_event_id": doc["source_event_id"],
                             "reason": doc["reason"]})
    result = _public(doc)
    result["deduplicated"] = False
    return result


async def get_case(db, tenant_id: str, case_id: str) -> Optional[dict]:
    return _public(await db[COLLECTION].find_one({"id": case_id, "tenant_id": tenant_id}))


async def find_by_source_event(db, tenant_id: str, source: str,
                               source_event_id: str) -> Optional[dict]:
    return _public(await db[COLLECTION].find_one(
        {"tenant_id": tenant_id, "source": source, "source_event_id": source_event_id}))


async def list_cases(db, tenant_id: str, *, state: Optional[str] = "open",
                     source: Optional[str] = None, workspace_id: Optional[str] = None,
                     limit: int = 100) -> list[dict]:
    criteria: dict[str, Any] = {"tenant_id": tenant_id}
    if state == "open":
        criteria["state"] = {"$in": list(OPEN_STATES)}
    elif state and state != "all":
        criteria["state"] = state
    if source:
        criteria["source"] = source
    if workspace_id:
        criteria["workspace_id"] = workspace_id
    docs = await db[COLLECTION].find(criteria).sort("created_at", -1).to_list(int(limit))
    return [_public(d) for d in docs]


async def list_unplanned(db, tenant_id: str, *, limit: int = 200) -> list[dict]:
    """Open cases that have never been planned for.

    A case created from a work item is reached by the composer through that item. A case
    with no work item — a missed call, a web enquiry, anything that never was a CRM record
    — has no such route, so the sweep needs to be able to ask for them directly.
    """
    docs = await db[COLLECTION].find({
        "tenant_id": tenant_id,
        "state": {"$in": [DETECTED]},
        "plan_reference": None,
    }).sort("created_at", 1).to_list(int(limit))
    return [_public(d) for d in docs]


async def attach(db, *, tenant_id: str, case_id: str, actor: str = "system",
                 audit: Optional[Callable[..., Awaitable[Any]]] = None,
                 **references) -> dict:
    """Resolve identity onto an existing case.

    This is where a missed call stops being a phone number and becomes a known contact.
    Every tenant-owned reference is verified before it is written, so resolution cannot be
    used to reach across a tenant boundary.
    """
    case = await get_case(db, tenant_id, case_id)
    if not case:
        raise RecoveryCaseNotFound("Recovery case not found")

    update: dict[str, Any] = {}
    for field, value in references.items():
        if field not in ATTACHABLE_REFERENCES:
            raise RecoveryCaseError(f"'{field}' is not an attachable reference")
        if value is None:
            continue
        await _assert_owned(db, tenant_id, field, value)
        update[field] = value

    if not update:
        return case

    update["updated_at"] = _iso(_now())
    updated = await db[COLLECTION].find_one_and_update(
        {"id": case_id, "tenant_id": tenant_id},
        {"$set": update, "$push": {"history": _history("attached", actor, dict(references))}},
        return_document=True)
    if not updated:
        raise RecoveryCaseNotFound("Recovery case not found")
    if audit:
        await audit("recovery_case.attached", "recovery_case", case_id, tenant_id, actor,
                    workspace_id=updated.get("workspace_id"),
                    payload={k: v for k, v in update.items() if k != "updated_at"})
    return _public(updated)


async def _transition(db, *, tenant_id: str, case_id: str, state: str, actor: str,
                      detail: Optional[dict],
                      audit: Optional[Callable[..., Awaitable[Any]]],
                      extra_set: Optional[dict] = None) -> dict:
    """Move a case and, in the same write, set whatever belongs to that move.

    `extra_set` exists so a caller that must record data *with* a transition — a confirmed
    amount, say — cannot end up having done one and not the other. The state change and
    its data land in a single conditional update or neither does.
    """
    if state not in STATES:
        raise RecoveryCaseError(f"state must be one of {STATES}")
    case = await get_case(db, tenant_id, case_id)
    if not case:
        raise RecoveryCaseNotFound("Recovery case not found")

    current = case.get("state", DETECTED)
    if state not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidCaseTransition(f"Cannot move recovery case from '{current}' to '{state}'")

    updated = await db[COLLECTION].find_one_and_update(
        {"id": case_id, "tenant_id": tenant_id, "state": current},
        {"$set": {**(extra_set or {}), "state": state, "updated_at": _iso(_now())},
         "$push": {"history": _history(state, actor, detail)}},
        return_document=True)
    if not updated:
        # Someone moved it between the read and the write.
        raise InvalidCaseTransition("Recovery case changed concurrently")
    if audit:
        await audit(f"recovery_case.{state}", "recovery_case", case_id, tenant_id, actor,
                    workspace_id=updated.get("workspace_id"),
                    payload={"from": current, "to": state, **(detail or {})})
    return _public(updated)


async def set_state(db, *, tenant_id: str, case_id: str, state: str, actor: str = "system",
                    detail: Optional[dict] = None,
                    audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    """Move a case, refusing any transition the matrix does not allow."""
    return await _transition(db, tenant_id=tenant_id, case_id=case_id, state=state,
                             actor=actor, detail=detail, audit=audit)


async def confirm_recovery(db, *, tenant_id: str, case_id: str, amount: float,
                           evidence: dict, actor: str = "system",
                           audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    """Record revenue actually recovered, with the evidence that says so.

    Confirmed value is a separate field from potential value and can never be derived from
    it. An estimate is not a recovery, and this refuses to record one without something to
    point at.
    """
    amount = _amount(amount, "Confirmed amount")
    if not evidence:
        raise RecoveryCaseError(
            "Confirming recovered revenue requires evidence of the recovery")

    # One write. Splitting this would let the case reach `recovered` with no confirmed
    # value and no way back — `recovered -> recovered` is not an allowed transition, so a
    # retry could not repair it.
    return await _transition(
        db, tenant_id=tenant_id, case_id=case_id, state=RECOVERED, actor=actor,
        detail={"confirmed_value": amount}, audit=audit,
        extra_set={"confirmed_value": amount, "confirmed_value_evidence": evidence})


async def summary(db, tenant_id: str) -> dict:
    """Counts and value, with potential and confirmed kept strictly apart."""
    by_state: dict[str, int] = {}
    async for row in db[COLLECTION].aggregate([
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {"_id": "$state", "count": {"$sum": 1}}},
    ]):
        by_state[row["_id"] or DETECTED] = row["count"]

    by_source: dict[str, int] = {}
    async for row in db[COLLECTION].aggregate([
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
    ]):
        by_source[row["_id"] or "unknown"] = row["count"]

    # Money is grouped by currency, never summed across it. £40,000 plus $40,000 is not
    # 80,000 of anything, and a single figure would be read as though it were.
    potential_by_currency: dict[str, float] = {}
    async for row in db[COLLECTION].aggregate([
        {"$match": {"tenant_id": tenant_id, "state": {"$in": list(OPEN_STATES)},
                    "potential_value": {"$type": "number"}}},
        {"$group": {"_id": "$currency", "total": {"$sum": "$potential_value"}}},
    ]):
        potential_by_currency[row["_id"] or DEFAULT_CURRENCY] = row["total"]

    confirmed_by_currency: dict[str, float] = {}
    async for row in db[COLLECTION].aggregate([
        {"$match": {"tenant_id": tenant_id, "confirmed_value": {"$type": "number"}}},
        {"$group": {"_id": "$currency", "total": {"$sum": "$confirmed_value"}}},
    ]):
        confirmed_by_currency[row["_id"] or DEFAULT_CURRENCY] = row["total"]

    currencies = sorted(set(potential_by_currency) | set(confirmed_by_currency))
    # The scalar figures stay, because one currency is the ordinary case and callers read
    # them — but they are only a truthful total while there *is* one currency. With more
    # than one they are None, so a mixed tenant reads as "look at the breakdown" rather
    # than as a number that silently means nothing.
    single = currencies[0] if len(currencies) == 1 else None

    return {
        "tenant_id": tenant_id,
        "open_cases": sum(by_state.get(s, 0) for s in OPEN_STATES),
        "recovered_cases": by_state.get(RECOVERED, 0),
        "by_state": by_state,
        "by_source": by_source,
        "currencies": currencies,
        # Named so the two can never be read as the same number.
        "potential_value_open_by_currency": potential_by_currency,
        "confirmed_recovered_value_by_currency": confirmed_by_currency,
        "potential_value_open": (
            potential_by_currency.get(single, 0.0) if single is not None
            else (0.0 if not currencies else None)),
        "confirmed_recovered_value": (
            confirmed_by_currency.get(single, 0.0) if single is not None
            else (0.0 if not currencies else None)),
        "value_currency": single,
    }
