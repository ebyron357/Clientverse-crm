"""The attribution ledger: which recovered revenue this system may claim, and why.

This is the part of a revenue-recovery product that is easiest to get wrong in a way
that looks like success. A system that counts every deal that closed after it drafted a
message will report spectacular numbers and be lying. A buyer who later checks one
entry and finds the "recovery" was a deal their own salesperson closed, against a
message that was never sent, will not believe anything else the product says either.

So the ledger is built around one idea: **the caller does not get to state the basis.**
A caller may say "this outcome happened, and it may relate to this case". Everything
after that -- whether a claim is permitted at all, what evidence supports it, and which
records that evidence points at -- is derived here from what actually happened.

WHAT COUNTS AS CONTACT

Only a message the provider accepted. `sent` and `delivered` count. Everything else
does not, and the exclusions are the point:

* `draft`, `pending_approval`, `approved` -- composed, maybe approved, never dispatched.
  Drafted is not sent.
* `blocked`, `failed` -- proven not to have gone out.
* `outcome_unknown` -- nobody knows whether it went out. An unknown is not a yes. If it
  turns out it was sent, reconciliation moves it to `sent` and a later derivation will
  see it; until then it supports nothing.

If no message on a case reached the client before the outcome, the ledger records the
outcome as **unattributed**. Not a weak claim, not a partial one: no claim. Revenue is
never attributed to outreach that did not reach anyone.

BASIS, NOT CONFIDENCE

There is no confidence score here, because there is no honest way to compute one and a
fabricated number would be worse than nothing. What there is instead is a named basis
and the records it rests on, so a buyer can follow any figure back to the message, the
reply and the invoice behind it.

* `reply_after_contact` -- the client replied to a message this system sent, and the
  outcome followed the reply. The strongest thing this system can honestly assert.
* `delivered_contact` -- a message reached the client before the outcome, but there was
  no reply. Contact happened; the causal link is weaker, and is labelled as such.
* `no_contact` -- nothing reached anyone in time. No claim.

POTENTIAL IS NOT CONFIRMED

Potential value is what a case might be worth. Confirmed value is money a record says
arrived. They live in different fields, are totalled separately, and are never added
together or reported as one figure. Totals are grouped by currency and never summed
across currencies.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import conversations as conversation_service
import recovery_case as recovery_case_service

COLLECTION = "attribution_entries"

# --------------------------------------------------------------------------- bases

BASIS_REPLY = "reply_after_contact"
BASIS_DELIVERED = "delivered_contact"
BASIS_NONE = "no_contact"
BASES = (BASIS_REPLY, BASIS_DELIVERED, BASIS_NONE)

CLAIM_ATTRIBUTED = "attributed"
CLAIM_UNATTRIBUTED = "unattributed"

# Only these message states mean the provider accepted the message. See the module
# docstring for why each of the others is excluded.
CONTACT_STATES = (conversation_service.SENT, conversation_service.DELIVERED)

# Outcome kinds. Each names where its money comes from, because an amount a caller made
# up is not evidence of anything.
OUTCOME_INVOICE_PAID = "invoice_paid"
OUTCOME_DEAL_WON = "deal_won"
OUTCOME_OPERATOR_CONFIRMED = "operator_confirmed"
OUTCOME_KINDS = (OUTCOME_INVOICE_PAID, OUTCOME_DEAL_WON, OUTCOME_OPERATOR_CONFIRMED)

# Outcomes backed by a CRM record, and where that record lives. One invoice is one
# payment and one deal is one win: each may be booked once in a tenant's ledger, on one
# case, under one kind -- never once per case that happened to touch the client.
RECORD_BACKED = {OUTCOME_INVOICE_PAID: "invoices", OUTCOME_DEAL_WON: "opportunities"}

# How far past the present an operator may date an outcome: clock skew, not the future.
FUTURE_TOLERANCE = timedelta(minutes=5)

# How long after contact an outcome may still be attributed to it. A deal that closes a
# year after one email is not a recovery this system performed, and a window is the
# honest way to say so. Tenant-configurable; not caller-configurable.
DEFAULT_ATTRIBUTION_WINDOW_DAYS = 90
SETTINGS_COLLECTION = "attribution_settings"


class AttributionError(Exception):
    pass


class OutcomeNotFound(AttributionError):
    pass


class CaseNotFound(AttributionError):
    pass


class RecordAlreadyBooked(AttributionError):
    """This invoice or deal is already in the ledger, on another case or kind."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime] = None) -> str:
    return (value or _now()).astimezone(timezone.utc).isoformat()


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _public(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    return {k: v for k, v in doc.items() if k != "_id"}


async def ensure_indexes(db: Any) -> None:
    # One entry per outcome per case. Replaying the same confirmation -- a webhook
    # redelivered, a sweep run twice -- must not book the revenue twice.
    await db[COLLECTION].create_index(
        [("tenant_id", 1), ("case_id", 1), ("outcome.kind", 1), ("outcome.record_id", 1)],
        unique=True)
    # And one entry per invoice or deal across the whole tenant. Partial, so entries
    # written before this field existed do not stop the index being built.
    await db[COLLECTION].create_index(
        [("tenant_id", 1), ("booked_record", 1)], unique=True,
        partialFilterExpression={"booked_record": {"$type": "string"}},
        name="one_entry_per_record")
    await db[COLLECTION].create_index([("tenant_id", 1), ("claim", 1), ("recorded_at", -1)])
    await db[COLLECTION].create_index([("tenant_id", 1), ("basis", 1)])
    await db[SETTINGS_COLLECTION].create_index("tenant_id", unique=True)


async def attribution_window_days(db: Any, tenant_id: str) -> int:
    doc = await db[SETTINGS_COLLECTION].find_one({"tenant_id": tenant_id}, {"_id": 0})
    try:
        days = int((doc or {}).get("window_days") or DEFAULT_ATTRIBUTION_WINDOW_DAYS)
    except (TypeError, ValueError):
        return DEFAULT_ATTRIBUTION_WINDOW_DAYS
    return max(1, min(days, 365))


async def set_attribution_window(db: Any, *, tenant_id: str, days: int, actor: str) -> dict:
    days = max(1, min(int(days), 365))
    await db[SETTINGS_COLLECTION].update_one(
        {"tenant_id": tenant_id},
        {"$set": {"window_days": days, "updated_by": actor, "updated_at": _iso()}},
        upsert=True)
    return {"tenant_id": tenant_id, "window_days": days}


# ------------------------------------------------------------------ basis derivation

async def _case_conversation_ids(db: Any, tenant_id: str, case_id: str) -> list[str]:
    rows = await db[conversation_service.CONVERSATIONS].find(
        {"tenant_id": tenant_id, "recovery_case_id": case_id}, {"_id": 0, "id": 1}
    ).to_list(200)
    return [row["id"] for row in rows]


async def derive_basis(db: Any, *, tenant_id: str, case_id: str,
                       occurred_at: str) -> dict:
    """Work out what, if anything, this system may claim for an outcome on this case.

    Reads only records. Takes no assertion from any caller. Returns the basis, the
    evidence behind it, and -- when there is no basis -- the reason there is none, which
    is the thing an operator actually needs to see.
    """
    outcome_at = _parse(occurred_at)
    if not outcome_at:
        return {"basis": BASIS_NONE, "evidence": [],
                "reason": "The outcome carries no usable date, so nothing can be tied to it."}

    window = timedelta(days=await attribution_window_days(db, tenant_id))
    conversation_ids = await _case_conversation_ids(db, tenant_id, case_id)
    if not conversation_ids:
        return {"basis": BASIS_NONE, "evidence": [],
                "reason": "No conversation on this case, so nothing was ever sent."}

    messages = await db[conversation_service.MESSAGES].find(
        {"tenant_id": tenant_id, "conversation_id": {"$in": conversation_ids}},
        {"_id": 0}).sort("created_at", 1).to_list(1000)

    contacts = []
    for message in messages:
        if message.get("direction") != conversation_service.OUTBOUND:
            continue
        if message.get("status") not in CONTACT_STATES:
            continue
        reached_at = _parse(message.get("delivered_at") or message.get("sent_at"))
        if not reached_at or reached_at > outcome_at:
            continue
        if outcome_at - reached_at > window:
            continue
        contacts.append((reached_at, message))

    if not contacts:
        # Say which of the two reasons applies: never sent, or sent too long ago. They
        # look the same in a total and mean completely different things.
        dispatched = [m for m in messages
                      if m.get("direction") == conversation_service.OUTBOUND
                      and m.get("status") in CONTACT_STATES]
        if dispatched:
            reason = (f"{len(dispatched)} message(s) reached the client, but none within "
                      f"{window.days} days before this outcome.")
        else:
            unsent = [m.get("status") for m in messages
                      if m.get("direction") == conversation_service.OUTBOUND]
            reason = ("No message on this case ever reached the client"
                      + (f" (outbound messages are in state(s): "
                         f"{', '.join(sorted({s for s in unsent if s}))})." if unsent
                         else "; nothing outbound was ever created."))
        return {"basis": BASIS_NONE, "evidence": [], "reason": reason}

    first_contact_at, _ = contacts[0]
    evidence = [{"kind": "outbound_message", "record_id": message["id"],
                 "at": _iso(reached_at), "status": message.get("status"),
                 "provider_message_id": message.get("provider_message_id"),
                 "detail": "A message this system sent that the provider accepted."}
                for reached_at, message in contacts]

    replies = [message for message in messages
               if message.get("direction") == conversation_service.INBOUND
               and (_parse(message.get("created_at")) or outcome_at) >= first_contact_at
               and (_parse(message.get("created_at")) or outcome_at) <= outcome_at]
    if replies:
        evidence += [{"kind": "inbound_reply", "record_id": reply["id"],
                      "at": reply.get("created_at"),
                      "from": reply.get("from_address"),
                      "detail": "The client replied after being contacted."}
                     for reply in replies]
        return {"basis": BASIS_REPLY, "evidence": evidence,
                "reason": (f"The client replied after {len(contacts)} message(s) this "
                           f"system sent, and the outcome followed the reply.")}

    return {"basis": BASIS_DELIVERED, "evidence": evidence,
            "reason": (f"{len(contacts)} message(s) reached the client before the outcome, "
                       "but there was no reply, so contact is all that can be asserted.")}


# ---------------------------------------------------------------- outcome resolution

async def _resolve_outcome(db: Any, tenant_id: str, *, kind: str, record_id: str,
                           amount: Optional[float], currency: Optional[str],
                           occurred_at: Optional[str]) -> dict:
    """Read the money out of the record, not out of the request.

    For an invoice or a deal the amount and the date come from the record itself, so a
    caller cannot inflate a recovery by asserting a larger number. An operator
    confirmation is the one kind whose amount a person supplies, and it is recorded as
    exactly that -- with the person's name on it.
    """
    if kind not in OUTCOME_KINDS:
        raise AttributionError(f"outcome kind must be one of {', '.join(OUTCOME_KINDS)}")

    if kind == OUTCOME_INVOICE_PAID:
        invoice = await db.invoices.find_one({"tenant_id": tenant_id, "id": record_id},
                                             {"_id": 0})
        if not invoice:
            raise OutcomeNotFound("No invoice with that id in this tenant")
        paid = str(invoice.get("payment_status") or invoice.get("status") or "").lower()
        if paid != "paid":
            raise AttributionError(
                f"Invoice {record_id} is '{paid or 'unknown'}', not paid; an unpaid "
                "invoice is not recovered revenue.")
        # The date the payment was recorded, set once when the invoice first became
        # paid. Not `updated_at`: any later edit resets that to today, which would date a
        # payment from last year after this week's outreach.
        if not _parse(invoice.get("paid_at")):
            raise AttributionError(
                f"Invoice {record_id} is paid but carries no payment date, so nothing can "
                "say whether it was paid before or after outreach. Record it as an "
                "operator confirmation with the date the money arrived.")
        return {"kind": kind, "record_id": record_id, "collection": "invoices",
                "amount": float(invoice.get("total") or invoice.get("amount") or 0),
                "currency": (invoice.get("currency") or recovery_case_service.DEFAULT_CURRENCY).upper(),
                "occurred_at": invoice["paid_at"],
                "amount_source": "invoice record",
                "record": invoice}

    if kind == OUTCOME_DEAL_WON:
        deal = await db.opportunities.find_one({"tenant_id": tenant_id, "id": record_id},
                                               {"_id": 0})
        if not deal:
            raise OutcomeNotFound("No deal with that id in this tenant")
        if deal.get("stage") != "closed_won":
            raise AttributionError(
                f"Deal {record_id} is in stage '{deal.get('stage')}', not closed_won; "
                "an open deal is pipeline, not revenue.")
        # The first time the deal was won. A later move back into closed_won -- or a
        # repeated one -- must not re-date a win that happened before any outreach.
        won_at = sorted(
            parsed for parsed in (_parse(t.get("at")) for t in (deal.get("stage_history") or [])
                                  if t.get("to") == "closed_won") if parsed)
        if not won_at:
            raise AttributionError(
                f"Deal {record_id} is closed_won but its history does not say when it was "
                "won (an imported deal, say), so nothing can say whether it was won before "
                "or after outreach. Record it as an operator confirmation with the date.")
        return {"kind": kind, "record_id": record_id, "collection": "opportunities",
                "amount": float(deal.get("value") or 0),
                "currency": (deal.get("currency") or recovery_case_service.DEFAULT_CURRENCY).upper(),
                "occurred_at": _iso(won_at[0]),
                "amount_source": "deal record",
                "record": deal}

    # Operator confirmation.
    for collection, record_kind in (("invoices", OUTCOME_INVOICE_PAID),
                                    ("opportunities", OUTCOME_DEAL_WON)):
        if await db[collection].find_one({"tenant_id": tenant_id, "id": record_id},
                                         {"_id": 1}):
            # The record exists, so its own amount and date are the evidence. Restating
            # them by hand would also book the same money a second time.
            raise AttributionError(
                f"{record_id} is a CRM record; record it as '{record_kind}' so its own "
                "amount and date are used.")
    if amount is None:
        raise AttributionError("An operator confirmation must state the amount recovered")
    try:
        value = float(amount)
    except (TypeError, ValueError):
        raise AttributionError("Amount must be a number")
    if value <= 0:
        raise AttributionError("A recovered amount must be greater than zero")
    code = (currency or recovery_case_service.DEFAULT_CURRENCY).strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise AttributionError("Currency must be a three-letter code, such as USD")
    when = _now()
    if occurred_at:
        stated = _parse(occurred_at)
        if not stated:
            raise AttributionError("occurred_at must be an ISO-8601 date")
        if stated > _now() + FUTURE_TOLERANCE:
            # A future date would sit after every message ever sent and could never be
            # contradicted by one.
            raise AttributionError("An outcome cannot be dated in the future")
        when = stated
    return {"kind": kind, "record_id": record_id, "collection": None,
            "amount": value,
            "currency": code,
            "occurred_at": _iso(when),
            "amount_source": "operator statement"}


def _source_record_id(case: dict) -> Optional[str]:
    """The record a detector opened this case for (`kind:record_id`), if any."""
    source_event_id = str(case.get("source_event_id") or "")
    return source_event_id.split(":", 1)[1] if ":" in source_event_id else None


async def _record_link(db: Any, tenant_id: str, case: dict, collection: str,
                       record: dict) -> dict:
    """Does this invoice or deal belong to the client this case is about?

    A paid invoice is only evidence for the case it relates to. Without this check any
    payment in the tenant could be booked against whichever case had the best outreach.
    Returns how the record links, `anchored: False` when the case names no CRM record at
    all (so there is nothing to check against), or `linked: False` when it names some and
    the record matches none of them.
    """
    anchors = {field: case.get(field) for field in
               ("opportunity_id", "company_id", "workspace_id", "contact_id")}
    source_id = _source_record_id(case)
    if not any(anchors.values()) and not source_id:
        return {"linked": False, "anchored": False,
                "detail": "The case names no CRM record, so this link rests on the "
                          "recorder's word."}

    record_id = record.get("id")
    company_ids = {record.get("company_id")} - {None}
    opportunity_ids = {record.get("opportunity_id"), record_id if collection == "opportunities"
                       else None} - {None}
    workspace = None
    if record.get("workspace_id"):
        workspace = await db.workspaces.find_one(
            {"tenant_id": tenant_id, "id": record["workspace_id"]}, {"_id": 0})
    if workspace:
        company_ids |= {workspace.get("company_id")} - {None}
        opportunity_ids |= {workspace.get("opportunity_id")} - {None}
    contact_ids = ({record.get("contact_id")} | set(record.get("contact_ids") or [])) - {None}

    case_company = anchors["company_id"]
    if not case_company and anchors["contact_id"]:
        contact = await db.contacts.find_one(
            {"tenant_id": tenant_id, "id": anchors["contact_id"]}, {"_id": 0, "company_id": 1})
        case_company = (contact or {}).get("company_id")

    checks = (
        ("the record the case was opened for", source_id and source_id == record_id),
        ("the case's deal", anchors["opportunity_id"]
         and anchors["opportunity_id"] in opportunity_ids),
        ("the case's workspace", anchors["workspace_id"]
         and anchors["workspace_id"] == record.get("workspace_id")),
        ("the case's company", case_company and case_company in company_ids),
        ("the case's contact", anchors["contact_id"] and anchors["contact_id"] in contact_ids),
    )
    for via, matched in checks:
        if matched:
            return {"linked": True, "anchored": True, "via": via}
    return {"linked": False, "anchored": True,
            "detail": "The record belongs to none of the deal, company, workspace or "
                      "contact this case is about."}


# --------------------------------------------------------------------- the ledger

async def record_outcome(db: Any, *, tenant_id: str, case_id: str, kind: str,
                         record_id: str, actor: str,
                         amount: Optional[float] = None,
                         currency: Optional[str] = None,
                         occurred_at: Optional[str] = None,
                         note: Optional[str] = None,
                         audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    """Record that something happened, and derive what -- if anything -- may be claimed.

    The caller contributes an outcome and a case. It does not contribute the basis, the
    evidence, or the decision about whether a claim is permitted. When no outreach
    reached the client, the outcome is still recorded -- as unattributed, with the reason
    -- because an outcome this system did not cause is a real fact worth keeping, and
    hiding it would make the attributed figures look better than they are.
    """
    case = await db[recovery_case_service.COLLECTION].find_one(
        {"tenant_id": tenant_id, "id": case_id}, {"_id": 0})
    if not case:
        raise CaseNotFound("No recovery case with that id in this tenant")

    outcome = await _resolve_outcome(db, tenant_id, kind=kind, record_id=record_id,
                                     amount=amount, currency=currency,
                                     occurred_at=occurred_at)
    record = outcome.pop("record", None)
    record_link = None
    if record is not None:
        record_link = await _record_link(db, tenant_id, case, outcome["collection"], record)
        if record_link["anchored"] and not record_link["linked"]:
            raise AttributionError(
                f"{record_id} does not belong to this case's client: "
                + record_link["detail"])
    derived = await derive_basis(db, tenant_id=tenant_id, case_id=case_id,
                                 occurred_at=outcome["occurred_at"])
    attributed = derived["basis"] != BASIS_NONE

    entry = {
        "id": f"attr_{uuid.uuid4().hex[:16]}",
        "tenant_id": tenant_id,
        "case_id": case_id,
        "outcome": outcome,
        # Derived, never supplied.
        "basis": derived["basis"],
        "claim": CLAIM_ATTRIBUTED if attributed else CLAIM_UNATTRIBUTED,
        "evidence": derived["evidence"],
        "reason": derived["reason"],
        # The amount this ledger claims. For an unattributed outcome it is zero, and the
        # outcome's own amount stays visible beside it so the two are never conflated.
        "attributed_amount": outcome["amount"] if attributed else 0.0,
        "currency": outcome["currency"],
        "note": (str(note)[:500] if note else None),
        "recorded_by": actor,
        "recorded_at": _iso(),
        "attribution_window_days": await attribution_window_days(db, tenant_id),
        # How the invoice or deal was tied to this case. Unverified when the case names
        # no CRM record to check it against, and said so rather than hidden.
        "record_link": record_link,
    }
    if outcome["collection"]:
        entry["booked_record"] = f"{outcome['collection']}:{record_id}"
    try:
        await db[COLLECTION].insert_one(dict(entry))
    except Exception as exc:
        if getattr(exc, "code", None) == 11000 or "E11000" in str(exc):
            existing = await db[COLLECTION].find_one(
                {"tenant_id": tenant_id, "case_id": case_id, "outcome.kind": kind,
                 "outcome.record_id": record_id}, {"_id": 0})
            if existing:
                return {**existing, "deduplicated": True}
            booked = await db[COLLECTION].find_one(
                {"tenant_id": tenant_id, "booked_record": entry.get("booked_record")},
                {"_id": 0, "case_id": 1, "id": 1})
            if booked:
                raise RecordAlreadyBooked(
                    f"{record_id} is already in the ledger (entry {booked['id']}, case "
                    f"{booked['case_id']}); one payment or win is booked once.") from exc
        raise

    if attributed:
        # The case's confirmed value is set from the ledger's own derivation, carrying
        # the evidence with it, so the case and the ledger can never disagree.
        try:
            await recovery_case_service.confirm_recovery(
                db, tenant_id=tenant_id, case_id=case_id, amount=outcome["amount"],
                currency=outcome["currency"],
                evidence={"attribution_entry_id": entry["id"], "basis": derived["basis"],
                          "outcome": outcome, "records": derived["evidence"]},
                actor=actor, audit=audit)
        except recovery_case_service.RecoveryCaseError as exc:
            # The case could not accept the confirmation (already terminal, or an
            # illegal transition). The ledger entry stays -- it is a true record of what
            # was derived -- and says plainly that the case was not updated.
            await db[COLLECTION].update_one(
                {"id": entry["id"], "tenant_id": tenant_id},
                {"$set": {"case_updated": False, "case_update_error": str(exc)[:300]}})
            return {**entry, "deduplicated": False, "case_updated": False,
                    "case_update_error": str(exc)[:300]}
        await db[COLLECTION].update_one({"id": entry["id"], "tenant_id": tenant_id},
                                        {"$set": {"case_updated": True}})
        return {**entry, "deduplicated": False, "case_updated": True}

    return {**entry, "deduplicated": False, "case_updated": False}


async def get_entry(db: Any, tenant_id: str, entry_id: str) -> Optional[dict]:
    return _public(await db[COLLECTION].find_one(
        {"tenant_id": tenant_id, "id": entry_id}, {"_id": 0}))


async def list_entries(db: Any, tenant_id: str, *, case_id: Optional[str] = None,
                       claim: Optional[str] = None, basis: Optional[str] = None,
                       limit: int = 100) -> list[dict]:
    query: dict[str, Any] = {"tenant_id": tenant_id}
    if case_id:
        query["case_id"] = case_id
    if claim:
        query["claim"] = claim
    if basis:
        query["basis"] = basis
    rows: list[dict] = await db[COLLECTION].find(query, {"_id": 0}).sort(
        "recorded_at", -1).to_list(max(1, min(int(limit or 100), 500)))
    return rows


async def totals(db: Any, tenant_id: str) -> dict:
    """What this system may claim, what it may not, and the difference between them.

    Every figure is grouped by currency and none is summed across currencies. The
    attributed and unattributed totals are reported side by side on purpose: a product
    that only shows what it can claim is showing a number with no denominator.
    """
    entries = await db[COLLECTION].find({"tenant_id": tenant_id}, {"_id": 0}).to_list(10000)

    attributed: dict[str, float] = {}
    unattributed: dict[str, float] = {}
    by_basis: dict[str, int] = {}
    for entry in entries:
        currency = entry.get("currency") or recovery_case_service.DEFAULT_CURRENCY
        by_basis[entry.get("basis", BASIS_NONE)] = by_basis.get(entry.get("basis", BASIS_NONE), 0) + 1
        amount = float(entry.get("outcome", {}).get("amount") or 0)
        if entry.get("claim") == CLAIM_ATTRIBUTED:
            attributed[currency] = round(attributed.get(currency, 0.0) + amount, 2)
        else:
            unattributed[currency] = round(unattributed.get(currency, 0.0) + amount, 2)

    return {
        "tenant_id": tenant_id,
        "entries": len(entries),
        "attributed_entries": sum(1 for e in entries if e.get("claim") == CLAIM_ATTRIBUTED),
        "unattributed_entries": sum(1 for e in entries
                                    if e.get("claim") == CLAIM_UNATTRIBUTED),
        "by_basis": by_basis,
        # Named at length so neither can be mistaken for the other, or for pipeline.
        "attributed_recovered_value_by_currency": attributed,
        "unattributed_outcome_value_by_currency": unattributed,
        "currencies": sorted(set(attributed) | set(unattributed)),
    }


async def time_to_recovery(db: Any, tenant_id: str) -> dict:
    """How long an attributed recovery took, measured from detection to the outcome.

    Reported only over entries that carry both dates. An average computed over cases
    that are missing one would be a number about the data, not about the business.
    """
    entries = await db[COLLECTION].find(
        {"tenant_id": tenant_id, "claim": CLAIM_ATTRIBUTED}, {"_id": 0}).to_list(5000)
    durations: list[float] = []
    for entry in entries:
        case = await db[recovery_case_service.COLLECTION].find_one(
            {"tenant_id": tenant_id, "id": entry["case_id"]},
            {"_id": 0, "detected_at": 1, "created_at": 1})
        detected = _parse((case or {}).get("detected_at") or (case or {}).get("created_at"))
        outcome_at = _parse(entry.get("outcome", {}).get("occurred_at"))
        if detected and outcome_at and outcome_at >= detected:
            durations.append((outcome_at - detected).total_seconds() / 86400.0)
    if not durations:
        return {"measured_entries": 0, "median_days": None, "mean_days": None,
                "note": "No attributed recovery carries both a detection date and an "
                        "outcome date yet."}
    ordered = sorted(durations)
    middle = len(ordered) // 2
    median = (ordered[middle] if len(ordered) % 2
              else (ordered[middle - 1] + ordered[middle]) / 2)
    return {"measured_entries": len(ordered),
            "median_days": round(median, 1),
            "mean_days": round(sum(ordered) / len(ordered), 1)}
