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
import os
import re
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

# An ISO 4217 code is three uppercase letters. Anything else -- "$", "us dollars", "" --
# cannot be grouped with anything, so it never becomes the currency of a case.
CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")

# No single recovery opportunity is worth ten billion of anything. A larger figure is a
# data-entry or form-configuration error, and one of those in a total silently dwarfs
# every real case beside it.
MAX_POTENTIAL_VALUE = 1e10

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
#
# Who moves a case along it, so no state is one nothing ever leaves:
#   detected -> planned / awaiting_approval   the strategy composer
#   awaiting_approval -> approved             the strategy's approval being approved
#   awaiting_approval -> planned              that approval being withdrawn (re-proposed)
#   approved -> executing                     the runner, on entry
#   executing -> engaged                      a message on the case actually being sent
#   engaged -> recovered                      an attributed, confirmed outcome
#   any open state -> closed                  reconciliation (the source resolved), an
#                                             unattributed outcome, a rejected strategy,
#                                             or an operator closing it with a reason
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

# Why a case closed. A closed case leaves open potential, so the reason is what lets a
# reader tell "the client was answered" from "we gave up" from "it was a test lead".
# Operators may choose from the first group; the rest are written only by the system,
# each by the one code path that establishes it.
OPERATOR_CLOSE_REASONS = ("not_recoverable", "duplicate", "resolved", "spam",
                          "no_longer_relevant")
SYSTEM_CLOSE_REASONS = (
    "source_resolved",                 # the record the case was opened on was dealt with
    "source_missing",                  # that record no longer exists
    "test_record",                     # it was a test lead; it never counted
    "deal_lost",                       # the linked deal closed lost
    "deal_archived",                   # the linked deal was archived
    "deal_won_before_case",            # the deal was already won when the case opened
    "outcome_recorded",                # an outcome was recorded that is not attributed
    "sale_recorded_on_another_case",   # the same sale already counts on another case
    "outcome_refused",                 # the outcome's record cannot be booked (bad value)
    "strategy_rejected",              # an operator rejected the recovery strategy
    "attribution_window_elapsed",      # contact made, nothing followed within the window
)
CLOSE_REASONS = OPERATOR_CLOSE_REASONS + SYSTEM_CLOSE_REASONS

# How many open cases the open-potential figure reads. A tenant with more than this is
# reported as truncated rather than silently undercounted.
OPEN_POTENTIAL_SCAN_LIMIT = int(os.environ.get("RECOVERY_OPEN_POTENTIAL_SCAN_LIMIT", "20000"))

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
    if amount > MAX_POTENTIAL_VALUE:
        raise RecoveryCaseError(f"{label} exceeds {MAX_POTENTIAL_VALUE:,.0f}")
    return amount


def normalize_currency(value: Any) -> Optional[str]:
    """The ISO 4217 code in `value`, uppercased, or None when it is not one."""
    code = str(value or "").strip().upper()
    return code if CURRENCY_CODE.match(code) else None


def sanitize_value(value: Any, currency: Any) -> dict:
    """Make a source's (value, currency) safe to store on a case, or say why it is not.

    Detectors read values out of records other systems wrote -- a website form, an
    external CRM, a deal someone typed in. `normalize_event` refuses a bad value outright,
    which is right for a direct caller and wrong for a sweep: refusing would throw away a
    real missed lead because its *estimate* was nonsense. So at the detector boundary a
    bad value is dropped (the case opens with no value) and the reason travels with it.

    Returns {"value", "currency", "rejected", "currency_assumed"}. `currency_assumed` is
    true when a value arrived with no currency at all and the default was applied --
    stated, not silent.
    """
    result: dict[str, Any] = {"value": None, "currency": DEFAULT_CURRENCY,
                              "rejected": None, "currency_assumed": False}
    code = normalize_currency(currency) if currency not in (None, "") else None
    if currency not in (None, "") and code is None:
        if value is not None:
            result["rejected"] = (f"currency {str(currency)[:20]!r} is not a 3-letter "
                                  "ISO 4217 code, so the value's unit is unknown")
        return result
    if value is None:
        result["currency"] = code or DEFAULT_CURRENCY
        return result
    if isinstance(value, bool):
        result["rejected"] = "value is a boolean, not an amount"
        return result
    try:
        result["value"] = _amount(value, "value")
    except RecoveryCaseError as exc:
        result["rejected"] = str(exc)
        return result
    result["currency"] = code or DEFAULT_CURRENCY
    result["currency_assumed"] = code is None
    return result


def sanitize_detection(detection: dict) -> dict:
    """A copy of a detector's output whose `value` and `currency` are safe to store.

    Applied before a detection becomes a case *or* a work item, because both persist the
    detection as evidence -- and an Infinity in evidence breaks every JSON response that
    lists it just as surely as one in `potential_value`. Idempotent.
    """
    clean = sanitize_value(detection.get("value"), detection.get("currency"))
    result = {**detection, "value": clean["value"], "currency": clean["currency"]}
    if clean["rejected"]:
        result["value_rejected"] = clean["rejected"]
    if clean["currency_assumed"]:
        result["currency_assumed"] = True
    if clean["value"] is None:
        result.pop("value_basis", None)
    return result


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
                    currency: Optional[str] = DEFAULT_CURRENCY,
                    potential_value_basis: Optional[str] = None,
                    evidence: Optional[dict] = None, title: Optional[str] = None) -> dict:
    """Put any source into the one shape the recovery pipeline accepts.

    Everything past `reason` is optional, and that is the point: a missed call carries a
    phone number and nothing else, while a dormant deal carries an opportunity, a company
    and a value. Both are valid events.

    `currency` must be an ISO 4217 code; it is normalised to uppercase and refused when
    it is not one, because a case whose currency is "$" can be totalled with nothing.
    `potential_value_basis` says in words where the value came from ("opportunity value
    on record", "web form estimate"), so a reader can judge how much weight it bears.
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
    code = normalize_currency(currency or DEFAULT_CURRENCY)
    if code is None:
        raise RecoveryCaseError("currency must be a 3-letter ISO 4217 code")

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
        "currency": code,
        "potential_value_basis": (str(potential_value_basis).strip()[:200]
                                  if potential_value is not None and potential_value_basis
                                  else None),
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


async def _refresh_from_event(db, case: dict, event: dict, *, actor: str) -> dict:
    """Bring an open case's value and references up to date with its source.

    Without this, potential value was frozen at first detection: a deal re-priced from
    £40,000 to £4,000 kept counting £40,000 in open potential for as long as it stayed
    dormant. The value mirrors the source -- including going to None when the source no
    longer carries a usable one -- and every change is written to the case's history so
    the figure an operator saw last week can still be explained.

    References are only ever *filled*, never overwritten: a contact or deal the source
    has since been linked to is how one buyer's cases come to be recognised as one
    opportunity. They were verified as tenant-owned by `open_case` before this runs.
    A terminal case is a closed record and is returned untouched.
    """
    if case.get("state") in TERMINAL_STATES:
        return case
    update: dict[str, Any] = {}
    changes: dict[str, Any] = {}
    new_value = event.get("potential_value")
    new_currency = event.get("currency") or DEFAULT_CURRENCY
    if new_value != case.get("potential_value") or (
            new_value is not None and new_currency != case.get("currency")):
        changes = {"potential_value": {"from": case.get("potential_value"), "to": new_value},
                   "currency": {"from": case.get("currency"), "to": new_currency}}
        update.update({
            "potential_value": new_value,
            "currency": new_currency,
            "potential_value_basis": event.get("potential_value_basis"),
            "potential_value_source": (f"{event['source']}:{event['source_event_id']}"
                                       if new_value is not None else None),
            "potential_value_updated_at": _iso(_now()),
        })
    filled = {field: event[field] for field in REFERENCE_COLLECTIONS
              if event.get(field) and not case.get(field)}
    update.update(filled)
    if not update:
        return case
    update["updated_at"] = _iso(_now())
    pushes = []
    if changes:
        pushes.append(_history("potential_value_refreshed", actor, changes))
    if filled:
        pushes.append(_history("references_filled", actor, filled))
    updated = await db[COLLECTION].find_one_and_update(
        {"id": case["id"], "tenant_id": case["tenant_id"],
         "state": {"$nin": list(TERMINAL_STATES)}},
        {"$set": update, "$push": {"history": {"$each": pushes}}},
        return_document=True)
    return _public(updated) or case


async def refresh_from_source(db, case: dict, *, value: Any, currency: Any,
                              basis: Optional[str], references: Optional[dict] = None,
                              actor: str = "system") -> dict:
    """Refresh an open case from its source record outside a detection sweep.

    Re-detection only re-reads a record while it still qualifies -- a dormant deal that
    woke up is no longer detected, so its case kept the value it was first seen with. The
    reconciler calls this with the record as it is now. The value is sanitised exactly as
    a detection's is, the change is written to the case's history, and a reference is only
    filled when the record it names exists in this tenant.
    """
    clean = sanitize_value(value, currency)
    filled: dict[str, Any] = {}
    for field, ref in (references or {}).items():
        if field in REFERENCE_COLLECTIONS and ref and not case.get(field):
            try:
                await _assert_owned(db, case["tenant_id"], field, ref)
            except CrossTenantReference:
                continue
            filled[field] = ref
    event = {"source": case["source"], "source_event_id": case["source_event_id"],
             "potential_value": clean["value"], "currency": clean["currency"],
             "potential_value_basis": basis if clean["value"] is not None else None,
             **filled}
    return await _refresh_from_event(db, case, event, actor=actor)


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
        "potential_value_basis": event.get("potential_value_basis"),
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
        # Another worker got there first, or this is a re-detection of a known event.
        # Hand back the existing case rather than a second one -- refreshed, if it is
        # still open and the source has moved since.
        existing = await db[COLLECTION].find_one(
            {"tenant_id": tenant_id, "source": event["source"],
             "source_event_id": event["source_event_id"]})
        if existing:
            result = await _refresh_from_event(db, _public(existing) or {}, event,
                                               actor=actor)
            result["deduplicated"] = True
            return result
        raise

    if audit:
        await audit("recovery_case.detected", "recovery_case", doc["id"], tenant_id, actor,
                    workspace_id=doc.get("workspace_id"),
                    payload={"source": doc["source"], "source_event_id": doc["source_event_id"],
                             "reason": doc["reason"]})
    result = {k: v for k, v in doc.items() if k != "_id"}
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
                           currency: Optional[str] = None,
                           audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    """Record revenue actually recovered, with the evidence that says so.

    Confirmed value is a separate field from potential value and can never be derived from
    it. An estimate is not a recovery, and this refuses to record one without something to
    point at.

    `currency` is the currency the *money that arrived* is in, which need not be the
    case's own: a missed call has no value and so defaults to USD, while the deal it led to
    was won in pounds. It is stored as `confirmed_currency` in the same write; every reader
    of `confirmed_value` labels it with that (see `confirmed_currency_of`).
    """
    amount = _amount(amount, "Confirmed amount")
    if not evidence:
        raise RecoveryCaseError(
            "Confirming recovered revenue requires evidence of the recovery")
    code = normalize_currency(currency) if currency else None
    if currency and code is None:
        raise RecoveryCaseError("currency must be a 3-letter ISO 4217 code")

    # One write. Splitting this would let the case reach `recovered` with no confirmed
    # value and no way back — `recovered -> recovered` is not an allowed transition, so a
    # retry could not repair it.
    return await _transition(
        db, tenant_id=tenant_id, case_id=case_id, state=RECOVERED, actor=actor,
        detail={"confirmed_value": amount, "confirmed_currency": code}, audit=audit,
        extra_set={"confirmed_value": amount, "confirmed_value_evidence": evidence,
                   "confirmed_currency": code})


def confirmed_currency_of(case: dict) -> str:
    """The currency a case's confirmed value is in.

    Its own `confirmed_currency` where recorded; for confirmations written before that
    field existed, the outcome's currency carried in the evidence; only then the case's
    currency.
    """
    outcome = (case.get("confirmed_value_evidence") or {}).get("outcome") or {}
    return (normalize_currency(case.get("confirmed_currency"))
            or normalize_currency(outcome.get("currency"))
            or normalize_currency(case.get("currency")) or DEFAULT_CURRENCY)


async def close_case(db, *, tenant_id: str, case_id: str, reason: str,
                     actor: str = "system", note: Optional[str] = None,
                     detail: Optional[dict] = None,
                     audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    """Close a case and record why, in the same write.

    Closing is what takes a case out of open potential, so it is never done without a
    named reason from `CLOSE_REASONS`. A recovered case may still be closed -- its
    confirmed value stays where it is -- but a closed one cannot be closed again.
    """
    if reason not in CLOSE_REASONS:
        raise RecoveryCaseError(f"reason must be one of {CLOSE_REASONS}")
    now = _iso(_now())
    return await _transition(
        db, tenant_id=tenant_id, case_id=case_id, state=CLOSED, actor=actor,
        detail={"reason": reason, **({"note": str(note)[:500]} if note else {}),
                **(detail or {})},
        audit=audit,
        extra_set={"close_reason": reason, "close_note": (str(note)[:500] if note else None),
                   "closed_at": now, "closed_by": actor})


# -------------------------------------------------------------- open potential

# How much weight a case's potential value bears, best first. A deal's own value is a
# record the business keeps; an estimate's or quote's total is a priced offer; a web-form
# estimate or an external system's figure is somebody's guess.
_VALUE_AUTHORITY = {
    SOURCE_DORMANT_DEAL: 0,
    SOURCE_UNANSWERED_ESTIMATE: 1,
    SOURCE_UNANSWERED_QUOTE: 1,
}


def _usable_value(case: dict) -> Optional[float]:
    value = case.get("potential_value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0 or value > MAX_POTENTIAL_VALUE:
        return None
    return float(value)


def group_open_potential(cases: list[dict],
                         deal_contacts: Optional[dict[str, set[str]]] = None) -> dict:
    """Count each underlying opportunity once, however many cases point at it.

    One buyer reaches a business several ways -- two web enquiries, a missed call, a
    dormant deal -- and each becomes its own case, correctly, because each is its own
    piece of work. Summing their values is not correct: it reports one £40,000 deal as
    £160,000 of potential. So cases are grouped by what they are *about*:

    1. the deal (`opportunity_id`) when the case knows it;
    2. otherwise the contact -- joined to that contact's deal when the contact is on
       exactly one of the deals the open cases are about, and kept separate when it is on
       several, because two genuinely different deals must not be collapsed into one.
       Who is on a deal comes from the case links *and* from the deal records themselves
       (`deal_contacts`: deal id -> its `contact_ids`), because a deal stores its people
       as a list and a dormant-deal case does not always carry one;
    3. otherwise the case alone, which is its own source record. An unresolved phone
       number or email is deliberately *not* a grouping key: until identity resolution
       ties it to a contact, two cases sharing one are not known to be one buyer.

    Each group contributes one value, never a sum: the most authoritative one (a deal's
    own value over a priced offer over an estimate), and among equals the most recently
    detected, which avoids comparing amounts in different currencies. The number of
    cases whose value was set aside this way is reported, so the collapse is visible.
    """
    contact_deals: dict[str, set[str]] = {}
    for case in cases:
        if case.get("contact_id") and case.get("opportunity_id"):
            contact_deals.setdefault(case["contact_id"], set()).add(case["opportunity_id"])
    open_deals = {case["opportunity_id"] for case in cases if case.get("opportunity_id")}
    for deal_id, contacts in (deal_contacts or {}).items():
        if deal_id in open_deals:
            for contact_id in contacts:
                contact_deals.setdefault(contact_id, set()).add(deal_id)

    groups: dict[str, list[dict]] = {}
    for case in cases:
        if case.get("opportunity_id"):
            key = f"opportunity:{case['opportunity_id']}"
        elif case.get("contact_id") and len(contact_deals.get(case["contact_id"], ())) == 1:
            key = f"opportunity:{next(iter(contact_deals[case['contact_id']]))}"
        elif case.get("contact_id"):
            key = f"contact:{case['contact_id']}"
        else:
            key = f"case:{case.get('id')}"
        groups.setdefault(key, []).append(case)

    by_currency: dict[str, float] = {}
    valued_groups = collapsed = without_value = 0
    for members in groups.values():
        valued = [c for c in members if _usable_value(c) is not None]
        without_value += len(members) - len(valued)
        if not valued:
            continue
        valued.sort(key=lambda c: str(c.get("created_at") or ""), reverse=True)
        valued.sort(key=lambda c: _VALUE_AUTHORITY.get(c.get("source") or "", 2))
        best = valued[0]
        currency = normalize_currency(best.get("currency")) or DEFAULT_CURRENCY
        by_currency[currency] = round(by_currency.get(currency, 0.0)
                                      + (_usable_value(best) or 0.0), 2)
        valued_groups += 1
        collapsed += len(valued) - 1

    return {
        "by_currency": by_currency,
        "open_cases": len(cases),
        "opportunity_groups": valued_groups,
        "cases_collapsed": collapsed,
        "cases_without_value": without_value,
    }


async def open_potential(db, tenant_id: str, *,
                         limit: int = OPEN_POTENTIAL_SCAN_LIMIT) -> dict:
    """Open potential for one tenant, each opportunity counted once (see the grouping)."""
    rows = await db[COLLECTION].find(
        {"tenant_id": tenant_id, "state": {"$in": list(OPEN_STATES)}},
        {"_id": 0, "id": 1, "source": 1, "opportunity_id": 1, "contact_id": 1,
         "potential_value": 1, "currency": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(int(limit) + 1)
    truncated = len(rows) > limit
    rows = rows[:limit]
    result = group_open_potential(rows, await deal_contacts_for(
        db, tenant_id, list({r["opportunity_id"] for r in rows if r.get("opportunity_id")})))
    result["truncated"] = truncated
    result["scan_limit"] = int(limit)
    return result


async def deal_contacts_for(db, tenant_id: str, deal_ids: list[str]) -> dict[str, set[str]]:
    """deal id -> the contacts the deal record names (`contact_ids`, and `contact_id`)."""
    if not deal_ids:
        return {}
    deals = await db[REFERENCE_COLLECTIONS["opportunity_id"]].find(
        {"tenant_id": tenant_id, "id": {"$in": deal_ids}},
        {"_id": 0, "id": 1, "contact_ids": 1, "contact_id": 1}).to_list(len(deal_ids) + 10)
    result: dict[str, set[str]] = {}
    for deal in deals:
        contacts = {str(c) for c in (deal.get("contact_ids") or []) if c}
        if deal.get("contact_id"):
            contacts.add(str(deal["contact_id"]))
        result[deal["id"]] = contacts
    return result


def sale_key_for_evidence(evidence: Optional[dict]) -> Optional[str]:
    """The sale a confirmed value rests on, read back from the confirmation's evidence.

    Newer confirmations carry the ledger's own `sale_key`. Older ones carry only the
    outcome, so the key is rebuilt from its kind and record -- enough to stop one deal
    confirmed on five cases from being counted five times.
    """
    if not evidence:
        return None
    if evidence.get("sale_key"):
        return str(evidence["sale_key"])
    outcome = evidence.get("outcome") or {}
    if outcome.get("kind") and outcome.get("record_id"):
        prefix = {"deal_won": "deal", "invoice_paid": "invoice",
                  "operator_confirmed": "operator"}.get(outcome["kind"], str(outcome["kind"]))
        return f"{prefix}:{outcome['record_id']}"
    return None


async def confirmed_totals(db, tenant_id: str, *,
                           limit: int = OPEN_POTENTIAL_SCAN_LIMIT) -> dict:
    """Confirmed recovered value per currency, and how many cases it comes from.

    Counted once per sale, and a case counts as recovered whenever its confirmed value is
    included -- `recovered`, and `recovered` then `closed`, alike. Counting only the
    `recovered` state dropped every recovery an operator later closed out.
    """
    by_currency: dict[str, float] = {}
    recovered_cases = 0
    seen_sales: set[str] = set()
    rows = await db[COLLECTION].find(
        {"tenant_id": tenant_id, "confirmed_value": {"$type": "number"}},
        {"_id": 0, "id": 1, "currency": 1, "confirmed_value": 1, "confirmed_currency": 1,
         "confirmed_value_evidence": 1},
    ).to_list(int(limit) + 1)
    for row in rows[:limit]:
        value = row.get("confirmed_value")
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            continue
        sale = sale_key_for_evidence(row.get("confirmed_value_evidence")) or f"case:{row['id']}"
        if sale in seen_sales:
            continue
        seen_sales.add(sale)
        recovered_cases += 1
        # The money's own currency, not the case's (see `confirmed_currency_of`).
        currency = confirmed_currency_of(row)
        by_currency[currency] = round(by_currency.get(currency, 0.0) + float(value), 2)
    return {"by_currency": by_currency, "recovered_cases": recovered_cases,
            "truncated": len(rows) > limit}


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
    # 80,000 of anything, and a single figure would be read as though it were. Open
    # potential counts each underlying opportunity once -- see `group_open_potential`.
    potential = await open_potential(db, tenant_id)
    potential_by_currency: dict[str, float] = potential["by_currency"]

    confirmed = await confirmed_totals(db, tenant_id)
    confirmed_by_currency: dict[str, float] = confirmed["by_currency"]
    recovered_cases = confirmed["recovered_cases"]

    currencies = sorted(set(potential_by_currency) | set(confirmed_by_currency))
    # The scalar figures stay, because one currency is the ordinary case and callers read
    # them — but they are only a truthful total while there *is* one currency. With more
    # than one they are None, so a mixed tenant reads as "look at the breakdown" rather
    # than as a number that silently means nothing.
    single = currencies[0] if len(currencies) == 1 else None

    return {
        "tenant_id": tenant_id,
        "open_cases": sum(by_state.get(s, 0) for s in OPEN_STATES),
        "recovered_cases": recovered_cases,
        "by_state": by_state,
        "by_source": by_source,
        "currencies": currencies,
        # Named so the two can never be read as the same number.
        "potential_value_open_by_currency": potential_by_currency,
        "open_cases_without_value": potential["cases_without_value"],
        "open_cases_collapsed": potential["cases_collapsed"],
        "open_opportunity_groups": potential["opportunity_groups"],
        "potential_scan_truncated": potential["truncated"],
        "confirmed_scan_truncated": confirmed["truncated"],
        "confirmed_recovered_value_by_currency": confirmed_by_currency,
        "potential_value_open": (
            potential_by_currency.get(single, 0.0) if single is not None
            else (0.0 if not currencies else None)),
        "confirmed_recovered_value": (
            confirmed_by_currency.get(single, 0.0) if single is not None
            else (0.0 if not currencies else None)),
        "value_currency": single,
    }
