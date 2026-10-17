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

ONE SALE, ONE ENTRY

A sale is counted once in this tenant, however many cases it could be pinned to and
however many records describe it. A £40,000 deal reachable from five cases is £40,000,
not £200,000; the deal and the invoice raised for it are one sale, not two. Every entry
carries a `sale_key` naming the sale, and the database refuses a second entry for it.
An outcome must also *relate* to the case it is recorded against -- the case's own deal,
its contact's deal, or the estimate it was opened on -- or it is refused outright.

AN ATTRIBUTED CLAIM IS A CONFIRMED ONE

An outcome is only counted as attributed when contact really happened *and* the case
accepted the confirmation. If the case cannot be confirmed, the entry is recorded as
unattributed and says why. Either way, a case that has an outcome recorded against it
leaves open potential: the same money cannot sit in "open" and in an outcome bucket.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import conversations as conversation_service
import crm_core
import recovery_case as recovery_case_service
import recovery_lifecycle

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

# How long after contact an outcome may still be attributed to it. A deal that closes a
# year after one email is not a recovery this system performed, and a window is the
# honest way to say so. Tenant-configurable; not caller-configurable.
DEFAULT_ATTRIBUTION_WINDOW_DAYS = 90
SETTINGS_COLLECTION = "attribution_settings"

# Totals read at most this many entries; a tenant past it is reported as truncated.
TOTALS_SCAN_LIMIT = 10000


class AttributionError(Exception):
    pass


class OutcomeNotFound(AttributionError):
    pass


class CaseNotFound(AttributionError):
    pass


class DuplicateSale(AttributionError):
    """The sale behind this outcome is already recorded against a different case."""

    def __init__(self, message: str, entry: dict) -> None:
        super().__init__(message)
        self.entry = entry


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
    # One entry per *sale*, tenant-wide. The index above stopped a replay on one case; it
    # did not stop the same deal being booked once per case and once per outcome kind.
    # Partial, so entries written before `sale_key` existed do not collide on a missing
    # field -- `totals()` de-duplicates those on read instead.
    await db[COLLECTION].create_index(
        [("tenant_id", 1), ("sale_key", 1)], unique=True,
        partialFilterExpression={"sale_key": {"$type": "string"}})
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
        if not invoice_is_paid(invoice):
            state = invoice.get("payment_status") or invoice.get("status") or "unknown"
            raise AttributionError(
                f"Invoice {record_id} is '{state}', not paid; an unpaid "
                "invoice is not recovered revenue.")
        return {"kind": kind, "record_id": record_id, "collection": "invoices",
                "amount": _record_amount(invoice.get("total") or invoice.get("amount"),
                                         f"Invoice {record_id}"),
                "currency": _record_currency(invoice.get("currency"), f"Invoice {record_id}"),
                "occurred_at": (invoice.get("paid_at") or invoice.get("updated_at")
                                or invoice.get("created_at") or _iso()),
                "amount_source": "invoice record"}

    if kind == OUTCOME_DEAL_WON:
        deal = await db.opportunities.find_one({"tenant_id": tenant_id, "id": record_id},
                                               {"_id": 0})
        if not deal:
            raise OutcomeNotFound("No deal with that id in this tenant")
        classes = await crm_core.stage_classes(db, tenant_id)
        if crm_core.classify_stage(deal.get("stage"), classes) != crm_core.STAGE_WON:
            raise AttributionError(
                f"Deal {record_id} is in stage '{deal.get('stage')}', not a closed-won stage "
                "of this tenant's pipeline; an open deal is pipeline, not revenue.")
        return {"kind": kind, "record_id": record_id, "collection": "opportunities",
                "amount": _record_amount(deal.get("value"), f"Deal {record_id}"),
                "currency": _record_currency(deal.get("currency"), f"Deal {record_id}"),
                "occurred_at": deal_won_at(deal, classes) or deal.get("updated_at")
                or deal.get("created_at") or _iso(),
                "amount_source": "deal record"}

    # Operator confirmation.
    if amount is None:
        raise AttributionError("An operator confirmation must state the amount recovered")
    try:
        value = float(amount)
    except (TypeError, ValueError):
        raise AttributionError("Amount must be a number")
    # `value <= 0` alone let NaN through (every comparison with NaN is false) and let
    # Infinity through, and either one in the ledger makes every total non-finite.
    if not math.isfinite(value) or value <= 0:
        raise AttributionError("A recovered amount must be a finite number greater than zero")
    if value > recovery_case_service.MAX_POTENTIAL_VALUE:
        raise AttributionError("A recovered amount that large is not credible; check the figure")
    code = recovery_case_service.normalize_currency(
        currency or recovery_case_service.DEFAULT_CURRENCY)
    if code is None:
        raise AttributionError("currency must be a 3-letter ISO 4217 code")
    return {"kind": kind, "record_id": record_id, "collection": None,
            "amount": value,
            "currency": code,
            "occurred_at": occurred_at or _iso(),
            "amount_source": "operator statement"}


def invoice_is_paid(invoice: dict) -> bool:
    """Paid if *either* field says so.

    A Stripe-settled invoice records it in `payment_status`; an invoice an operator marked
    paid by hand records it in `status` and leaves `payment_status` at whatever the
    provider last said ("requires_stripe_configuration", say). Reading only the first
    non-empty field refused every manually paid invoice.
    """
    return "paid" in (str(invoice.get("payment_status") or "").lower(),
                      str(invoice.get("status") or "").lower())


def deal_won_at(deal: dict, classes: dict[str, set[str]]) -> Optional[str]:
    """When the deal last moved into one of the tenant's won stages, if recorded."""
    for transition in reversed(deal.get("stage_history") or []):
        if crm_core.classify_stage(transition.get("to"), classes) == crm_core.STAGE_WON:
            at = transition.get("at")
            return str(at) if at else None
    return None


def _record_amount(value: Any, label: str) -> float:
    """An amount read from a record, refused when it could not be real money."""
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        raise AttributionError(f"{label} carries no usable amount")
    if not math.isfinite(amount) or amount < 0 or \
            amount > recovery_case_service.MAX_POTENTIAL_VALUE:
        raise AttributionError(f"{label} carries an amount that is not a credible figure")
    return amount


def _record_currency(value: Any, label: str) -> str:
    if value in (None, ""):
        return recovery_case_service.DEFAULT_CURRENCY
    code = recovery_case_service.normalize_currency(value)
    if code is None:
        raise AttributionError(f"{label} carries currency {str(value)[:20]!r}, which is "
                               "not a 3-letter ISO 4217 code")
    return code


# ---------------------------------------------------------------- sale identity

def _case_source_record(case: dict) -> tuple[Optional[str], Optional[str]]:
    """(kind, id) of the record a case was opened on, from its `source_event_id`."""
    kind, _, record_id = str(case.get("source_event_id") or "").partition(":")
    return (kind or None, record_id or None)


async def _deal_for_invoice(db: Any, tenant_id: str, invoice: dict) -> Optional[str]:
    """The deal an invoice was raised for, when the records say so.

    Read in order of directness: the invoice's own `opportunity_id`, then the estimate it
    was converted from, then the client workspace it lives in -- a workspace is created
    from the deal that was won. That last link is the conservative choice: an invoice in
    a won deal's workspace is treated as part of that deal's sale, so a later invoice in
    the same workspace is under-counted rather than the original sale counted twice.
    """
    if invoice.get("opportunity_id"):
        return str(invoice["opportunity_id"])
    if invoice.get("estimate_id"):
        estimate = await db.estimates.find_one(
            {"tenant_id": tenant_id, "id": invoice["estimate_id"]},
            {"_id": 0, "opportunity_id": 1})
        if estimate and estimate.get("opportunity_id"):
            return str(estimate["opportunity_id"])
    if invoice.get("workspace_id"):
        workspace = await db.workspaces.find_one(
            {"tenant_id": tenant_id, "id": invoice["workspace_id"]},
            {"_id": 0, "opportunity_id": 1})
        if workspace and workspace.get("opportunity_id"):
            return str(workspace["opportunity_id"])
    return None


def _deal_contacts(deal: Optional[dict]) -> set[str]:
    if not deal:
        return set()
    contacts = {str(c) for c in (deal.get("contact_ids") or []) if c}
    if deal.get("contact_id"):
        contacts.add(str(deal["contact_id"]))
    return contacts


async def _sale_and_relation(db: Any, tenant_id: str, case: dict, *, kind: str,
                             record_id: str) -> str:
    """Name the sale this outcome is, and refuse it unless it belongs to this case.

    Before this, any paid invoice or won deal in the tenant could be recorded against any
    case -- which is how one deal became five recoveries. An outcome now relates to a case
    only through a record they share:

    * a deal: the case's own deal, or -- for a case that knows no deal -- a deal its
      contact is on;
    * an invoice: one raised from the estimate the case was opened on, or one belonging
      to a deal related to the case as above;
    * an operator confirmation: the operator's own statement, keyed on their reference.

    Returns the sale key; raises `AttributionError` (a 422 at the API) otherwise.
    """
    if kind == OUTCOME_OPERATOR_CONFIRMED:
        return f"operator:{record_id}"

    case_deal = case.get("opportunity_id")
    case_contact = case.get("contact_id")

    async def deal_relates(deal_id: Optional[str]) -> bool:
        if not deal_id:
            return False
        if case_deal:
            return bool(deal_id == case_deal)
        if not case_contact:
            return False
        deal = await db.opportunities.find_one({"tenant_id": tenant_id, "id": deal_id},
                                               {"_id": 0, "contact_ids": 1, "contact_id": 1})
        return case_contact in _deal_contacts(deal)

    if kind == OUTCOME_DEAL_WON:
        if not await deal_relates(record_id):
            raise AttributionError(
                f"Deal {record_id} is not related to recovery case {case['id']}: it is "
                "neither the case's deal nor a deal its contact is on. Record the outcome "
                "against the case it belongs to.")
        return f"deal:{record_id}"

    invoice = await db.invoices.find_one({"tenant_id": tenant_id, "id": record_id},
                                         {"_id": 0}) or {}
    deal_id = await _deal_for_invoice(db, tenant_id, invoice)
    source_kind, source_id = _case_source_record(case)
    estimate_id = invoice.get("estimate_id")
    from_case_estimate = bool(estimate_id) and source_kind == "estimate" and \
        source_id == estimate_id
    if not from_case_estimate and not await deal_relates(deal_id):
        raise AttributionError(
            f"Invoice {record_id} is not related to recovery case {case['id']}: it was not "
            "raised from the case's estimate and does not belong to the case's deal. "
            "Record the outcome against the case it belongs to.")
    if deal_id:
        return f"deal:{deal_id}"
    if estimate_id:
        return f"estimate:{estimate_id}"
    return f"invoice:{record_id}"


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

    The order matters and every step can refuse:

    1. the outcome is read from its own record (paid? won? how much?);
    2. it must relate to this case, and it names a sale (`_sale_and_relation`);
    3. a sale already in the ledger is never booked again -- on this case the existing
       entry is returned, on another case `DuplicateSale` is raised;
    4. the entry is written as *unattributed* first, so no reader can ever see a claim
       that has not been confirmed;
    5. if contact happened, the case is confirmed and only then is the entry upgraded to
       attributed. If the case cannot take the confirmation the entry stays unattributed
       and says why;
    6. a case that is still open is closed, so its potential leaves open potential at
       the moment its money enters an outcome bucket.
    """
    case = await db[recovery_case_service.COLLECTION].find_one(
        {"tenant_id": tenant_id, "id": case_id}, {"_id": 0})
    if not case:
        raise CaseNotFound("No recovery case with that id in this tenant")

    outcome = await _resolve_outcome(db, tenant_id, kind=kind, record_id=record_id,
                                     amount=amount, currency=currency,
                                     occurred_at=occurred_at)
    sale_key = await _sale_and_relation(db, tenant_id, case, kind=kind, record_id=record_id)
    existing = await _existing_for_sale(db, tenant_id, case_id=case_id, sale_key=sale_key,
                                        kind=kind, record_id=record_id)
    if existing:
        # A replay changes nothing -- except that an entry recorded before outcomes closed
        # their case may have left this one open, its money in two places at once.
        await recovery_lifecycle.close_if_open(
            db, tenant_id=tenant_id, case_id=case_id, reason="outcome_recorded",
            actor=actor, detail={"attribution_entry_id": existing.get("id")}, audit=audit)
        return existing

    derived = await derive_basis(db, tenant_id=tenant_id, case_id=case_id,
                                 occurred_at=outcome["occurred_at"])
    contact = derived["basis"] != BASIS_NONE

    entry = {
        "id": f"attr_{uuid.uuid4().hex[:16]}",
        "tenant_id": tenant_id,
        "case_id": case_id,
        "sale_key": sale_key,
        "outcome": outcome,
        # Derived, never supplied.
        "basis": derived["basis"],
        # Provisional until the case accepts the confirmation; see step 4 above.
        "claim": CLAIM_UNATTRIBUTED,
        "evidence": derived["evidence"],
        "reason": derived["reason"],
        # The amount this ledger claims. For an unattributed outcome it is zero, and the
        # outcome's own amount stays visible beside it so the two are never conflated.
        "attributed_amount": 0.0,
        "currency": outcome["currency"],
        "note": (str(note)[:500] if note else None),
        "recorded_by": actor,
        "recorded_at": _iso(),
        "attribution_window_days": await attribution_window_days(db, tenant_id),
        "case_updated": False,
    }
    try:
        await db[COLLECTION].insert_one(dict(entry))
    except Exception as exc:
        if getattr(exc, "code", None) == 11000 or "E11000" in str(exc):
            # A concurrent writer recorded the same sale between our check and insert.
            raced = await _existing_for_sale(db, tenant_id, case_id=case_id,
                                             sale_key=sale_key, kind=kind,
                                             record_id=record_id)
            if raced:
                return raced
        raise

    update: dict[str, Any] = {}
    if contact:
        try:
            # Contact reaching the client is what `engaged` means; a case still marked
            # `executing` is brought up to date before it is asked to confirm.
            await recovery_lifecycle.sync_engagement(db, tenant_id=tenant_id,
                                                     case_id=case_id, actor=actor,
                                                     audit=audit)
            # The case's confirmed value is set from the ledger's own derivation,
            # carrying the evidence with it, so the case and the ledger never disagree.
            await recovery_case_service.confirm_recovery(
                db, tenant_id=tenant_id, case_id=case_id, amount=outcome["amount"],
                evidence={"attribution_entry_id": entry["id"], "basis": derived["basis"],
                          "sale_key": sale_key, "outcome": outcome,
                          "records": derived["evidence"]},
                actor=actor, audit=audit)
            update = {"claim": CLAIM_ATTRIBUTED, "attributed_amount": outcome["amount"],
                      "case_updated": True}
        except recovery_case_service.RecoveryCaseError as exc:
            # Contact happened, but the case could not accept the confirmation (already
            # closed, or never worked through the pipeline). An unconfirmed claim is not
            # a claim: the entry stays unattributed and says exactly why.
            update = {"case_updated": False, "case_update_error": str(exc)[:300],
                      "reason": (f"{derived['reason']} Not counted as attributed: the case "
                                 f"could not be confirmed ({str(exc)[:200]}).")}

    if not update.get("case_updated"):
        # `case_updated` keeps its meaning -- the case's confirmed value was set. An
        # unattributed outcome still takes the case out of open potential; that is
        # recorded separately as `case_closed`.
        closed = await recovery_lifecycle.close_if_open(
            db, tenant_id=tenant_id, case_id=case_id, reason="outcome_recorded",
            actor=actor, detail={"attribution_entry_id": entry["id"],
                                 "sale_key": sale_key},
            audit=audit)
        update["case_closed"] = bool(closed)

    if update:
        await db[COLLECTION].update_one({"id": entry["id"], "tenant_id": tenant_id},
                                        {"$set": update})
        entry.update(update)
    return {**entry, "deduplicated": False}


async def _existing_for_sale(db: Any, tenant_id: str, *, case_id: str, sale_key: str,
                             kind: str, record_id: str) -> Optional[dict]:
    """The entry already recording this sale, returned on this case or refused on another.

    Entries written before `sale_key` existed are matched on their outcome record, so a
    replay of an old outcome is still recognised.
    """
    existing = await db[COLLECTION].find_one({"tenant_id": tenant_id, "sale_key": sale_key},
                                             {"_id": 0})
    if not existing:
        existing = await db[COLLECTION].find_one(
            {"tenant_id": tenant_id, "sale_key": {"$exists": False},
             "outcome.kind": kind, "outcome.record_id": record_id}, {"_id": 0})
    if not existing:
        return None
    if existing.get("case_id") == case_id:
        return {**existing, "deduplicated": True}
    raise DuplicateSale(
        f"This sale is already recorded against recovery case {existing.get('case_id')} "
        f"(entry {existing.get('id')}). One sale is counted once.", existing)


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
    rows = await db[COLLECTION].find({"tenant_id": tenant_id}, {"_id": 0}).sort(
        "recorded_at", 1).to_list(TOTALS_SCAN_LIMIT + 1)
    truncated = len(rows) > TOTALS_SCAN_LIMIT
    entries = _one_per_sale(rows[:TOTALS_SCAN_LIMIT])

    attributed: dict[str, float] = {}
    unattributed: dict[str, float] = {}
    by_basis: dict[str, int] = {}
    attributed_count = unconfirmed = 0
    for entry in entries:
        currency = (recovery_case_service.normalize_currency(entry.get("currency"))
                    or recovery_case_service.DEFAULT_CURRENCY)
        by_basis[entry.get("basis", BASIS_NONE)] = by_basis.get(entry.get("basis", BASIS_NONE), 0) + 1
        amount = _counted_amount(entry)
        if is_counted_as_attributed(entry):
            attributed_count += 1
            attributed[currency] = round(attributed.get(currency, 0.0) + amount, 2)
        else:
            if entry.get("claim") == CLAIM_ATTRIBUTED:
                # Written before a claim had to be confirmed: contact happened but the
                # case never accepted it. Real revenue, not claimed.
                unconfirmed += 1
            unattributed[currency] = round(unattributed.get(currency, 0.0) + amount, 2)

    return {
        "tenant_id": tenant_id,
        "entries": len(entries),
        "attributed_entries": attributed_count,
        "unattributed_entries": len(entries) - attributed_count,
        "attributed_but_unconfirmed_entries": unconfirmed,
        "duplicate_entries_excluded": min(len(rows), TOTALS_SCAN_LIMIT) - len(entries),
        "truncated": truncated,
        "scan_limit": TOTALS_SCAN_LIMIT,
        "by_basis": by_basis,
        # Named at length so neither can be mistaken for the other, or for pipeline.
        "attributed_recovered_value_by_currency": attributed,
        "unattributed_outcome_value_by_currency": unattributed,
        "currencies": sorted(set(attributed) | set(unattributed)),
    }


def is_counted_as_attributed(entry: dict) -> bool:
    """Attributed only when it was claimed *and* the case accepted the confirmation."""
    return entry.get("claim") == CLAIM_ATTRIBUTED and entry.get("case_updated") is not False


def _counted_amount(entry: dict) -> float:
    try:
        amount = float((entry.get("outcome") or {}).get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0
    return amount if math.isfinite(amount) and amount >= 0 else 0.0


def _entry_sale_key(entry: dict) -> str:
    if entry.get("sale_key"):
        return str(entry["sale_key"])
    return (recovery_case_service.sale_key_for_evidence({"outcome": entry.get("outcome")})
            or f"entry:{entry.get('id')}")


def _one_per_sale(entries: list[dict]) -> list[dict]:
    """Keep one entry per sale, preferring a confirmed attributed one.

    New entries are unique per sale by index. Entries recorded before that index existed
    can hold the same deal several times over -- once per case it was pinned to -- and
    are collapsed here so the totals stop counting it more than once.
    """
    chosen: dict[str, dict] = {}
    for entry in entries:
        key = _entry_sale_key(entry)
        current = chosen.get(key)
        if current is None or (is_counted_as_attributed(entry)
                               and not is_counted_as_attributed(current)):
            chosen[key] = entry
    return list(chosen.values())


async def time_to_recovery(db: Any, tenant_id: str) -> dict:
    """How long an attributed recovery took, measured from detection to the outcome.

    Reported only over entries that carry both dates. An average computed over cases
    that are missing one would be a number about the data, not about the business.
    """
    entries = _one_per_sale([
        entry for entry in await db[COLLECTION].find(
            {"tenant_id": tenant_id, "claim": CLAIM_ATTRIBUTED}, {"_id": 0}).to_list(5000)
        if is_counted_as_attributed(entry)])
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
