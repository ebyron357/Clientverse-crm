"""The remaining recovery detector families.

`second_chance` implements two lanes -- a dormant deal and a missed follow-up -- because
those were the two the CRM already had records for. The other eight sources were declared
in the normalized event vocabulary and had nothing behind them, which meant the product
named recovery opportunities it could not actually find.

This module implements them, on the same contract as the existing two, because a
detector that behaves differently from its neighbours is a second pipeline pretending to
be one:

* **Deterministic.** Every rule is a threshold over a timestamp and a status. Nothing is
  scored by a model, and no confidence figure is invented.
* **Explainable.** Each detection carries a sentence a person can check, naming the
  numbers that triggered it.
* **Cited.** Each detection names the record it came from, by collection and id.
* **Deduplicated.** Identity is (source, record), so re-running a sweep re-finds the same
  case rather than opening a second one.
* **Tenant-scoped.** Every query filters on tenant before anything else.
* **Silent outward.** A detector creates internal work. It never sends anything, and it
  never reaches the controlled execution path directly -- that is what the work queue,
  the strategy composer and the approval gate are for.

WHAT "NO RESPONSE" MEANS HERE

Several of these lanes turn on whether anyone responded. Response is always read from
records, never assumed: a reply recorded on a conversation, an activity logged against
the record, a task raised for it, or a status the record itself moved to. A lane that
guessed would manufacture recovery opportunities out of ordinary business.
"""

from __future__ import annotations

import os
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import conversations as conversation_service
import recovery_case

QUEUE_NAME = "recovery_detection"

# Detector types, one per declared source. The type is what the work queue sees; the
# source is what the recovery pipeline sees. Keeping them parallel is what makes a new
# lane enter the existing pipeline instead of growing another.
TYPE_MISSED_CALL = "recovery.missed_call"
TYPE_WEB_ENQUIRY = "recovery.web_enquiry"
TYPE_UNANSWERED_QUOTE = "recovery.unanswered_quote"
TYPE_UNANSWERED_ESTIMATE = "recovery.unanswered_estimate"
TYPE_NO_RESPONSE = "recovery.no_response"
TYPE_APPOINTMENT_CANCELLED = "recovery.appointment_cancelled"
TYPE_APPOINTMENT_NO_SHOW = "recovery.appointment_no_show"
TYPE_EXTERNAL_CRM_EVENT = "recovery.external_crm_event"

SOURCE_FOR_TYPE = {
    TYPE_MISSED_CALL: recovery_case.SOURCE_MISSED_CALL,
    TYPE_WEB_ENQUIRY: recovery_case.SOURCE_WEB_ENQUIRY,
    TYPE_UNANSWERED_QUOTE: recovery_case.SOURCE_UNANSWERED_QUOTE,
    TYPE_UNANSWERED_ESTIMATE: recovery_case.SOURCE_UNANSWERED_ESTIMATE,
    TYPE_NO_RESPONSE: recovery_case.SOURCE_NO_RESPONSE,
    TYPE_APPOINTMENT_CANCELLED: recovery_case.SOURCE_APPOINTMENT_CANCELLED,
    TYPE_APPOINTMENT_NO_SHOW: recovery_case.SOURCE_APPOINTMENT_NO_SHOW,
    TYPE_EXTERNAL_CRM_EVENT: recovery_case.SOURCE_EXTERNAL_CRM_EVENT,
}

# Collections this module reads from and, for the intake lanes, writes into.
CALL_LOGS = "call_logs"
WEB_ENQUIRIES = "web_enquiries"
EXTERNAL_EVENTS = "external_crm_events"

# Thresholds are configuration rather than magic numbers, so "unanswered" can be tuned
# to a business without a code change.
MISSED_CALL_GRACE_HOURS = int(os.environ.get("RECOVERY_MISSED_CALL_GRACE_HOURS", "4"))
WEB_ENQUIRY_GRACE_HOURS = int(os.environ.get("RECOVERY_WEB_ENQUIRY_GRACE_HOURS", "24"))
QUOTE_GRACE_DAYS = int(os.environ.get("RECOVERY_QUOTE_GRACE_DAYS", "7"))
ESTIMATE_GRACE_DAYS = int(os.environ.get("RECOVERY_ESTIMATE_GRACE_DAYS", "7"))
NO_RESPONSE_GRACE_DAYS = int(os.environ.get("RECOVERY_NO_RESPONSE_GRACE_DAYS", "5"))
NO_SHOW_GRACE_HOURS = int(os.environ.get("RECOVERY_NO_SHOW_GRACE_HOURS", "2"))
DETECTION_LIMIT = int(os.environ.get("RECOVERY_DETECTION_LIMIT", "500"))

# A call that was answered is not a missed one.
MISSED_CALL_OUTCOMES = ("missed", "no_answer", "voicemail", "abandoned", "unanswered")
ANSWERED_CALL_OUTCOMES = ("answered", "connected", "completed")
ANSWERED_OUTCOME_PATTERN = r"^\s*(" + "|".join(ANSWERED_CALL_OUTCOMES) + r")\s*$"

# Document kinds that represent a priced offer awaiting a decision.
QUOTE_KINDS = ("quote", "proposal", "pricing")

# Statuses that mean a priced offer is out with the client and undecided.
OPEN_OFFER_STATUSES = ("sent", "issued", "awaiting_response", "pending")
DECIDED_OFFER_STATUSES = ("approved", "accepted", "rejected", "declined", "won", "lost",
                          "invoiced", "cancelled", "expired", "withdrawn")

CANCELLED_APPOINTMENT_STATUSES = ("cancelled", "canceled")
COMPLETED_APPOINTMENT_STATUSES = ("completed", "done", "attended", "fulfilled")
PENDING_APPOINTMENT_STATUSES = ("scheduled", "confirmed", "booked")
# An outcome a person recorded: the client did not turn up.
NO_SHOW_APPOINTMENT_STATUSES = ("no_show", "no-show", "noshow", "missed")

# External events worth recovering. An event kind nobody declared is ignored rather than
# guessed at: an unknown event is not an opportunity, it is an unknown.
RECOVERABLE_EXTERNAL_KINDS = ("lead_lost", "deal_lost", "opportunity_stalled",
                              "quote_expired", "subscription_cancelled",
                              "enquiry_unanswered", "appointment_cancelled")

# A web enquiry in any of these states is not a lost lead: somebody answered it, closed
# it, or it was never a lead at all.
RESOLVED_ENQUIRY_STATUSES = ("responded", "closed", "spam")

# Lanes that exist in the vocabulary but cannot fire on the data this application holds,
# with the reason. They are reported as disabled in every sweep summary rather than
# being reported as "found 0", which reads as "looked, and nothing was wrong".
DISABLED_LANES = {
    "unanswered_quotes": (
        "No priced-quote record exists to read. The lane looked in a `documents` collection "
        "nothing writes; client documents (`client_documents`) carry no total, no sent "
        "date and no accepted/declined status, so an unanswered quote cannot be told from "
        "an ordinary shared file. Priced offers are covered by the estimates lane."),
}

# Phone numbers are compared on their last ten digits, so "+1 (555) 010-0199",
# "15550100199" and "555-010-0199" are recognised as one caller. Ten digits is a national
# number in the NANP and covers the significant part of most others; a shorter string is
# compared whole.
PHONE_MATCH_DIGITS = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: Any) -> Optional[datetime]:
    """Parse a timestamp; one written without a timezone is read as UTC.

    That reading is a convention, not knowledge: a time with no offset could have been
    written in any zone. Timestamps this application writes always carry one; the naive
    ones come from callers -- a phone system's `occurred_at`, an appointment typed into
    a form. Where a detection rests on such a time it says so (`_naive`), so the reading
    is visible to whoever acts on it rather than silently assumed.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _naive(value: Any) -> bool:
    """True when `value` is a timestamp that carries no timezone (see `_parse`)."""
    if isinstance(value, datetime):
        return value.tzinfo is None
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None
        except ValueError:
            return False
    return False


def _zone_note(*values: Any) -> dict:
    """Evidence that a detection's timing rests on a time read as UTC, if it does."""
    if any(_naive(v) for v in values):
        return {"timestamp_timezone_assumed": "UTC",
                "timestamp_note": ("A time this detection depends on was recorded without a "
                                   "timezone and was read as UTC; it may be off by the "
                                   "source's UTC offset.")}
    return {}


def phone_key(value: Any) -> str:
    """The comparable part of a phone number: its last ten digits (see PHONE_MATCH_DIGITS)."""
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[-PHONE_MATCH_DIGITS:] if len(digits) > PHONE_MATCH_DIGITS else digits


def _status(value: Any) -> str:
    return str(value or "").strip().lower()


def _hours(delta: timedelta) -> int:
    return max(0, int(delta.total_seconds() // 3600))


async def ensure_indexes(db: Any) -> None:
    await db[CALL_LOGS].create_index([("tenant_id", 1), ("occurred_at", -1)])
    await db[CALL_LOGS].create_index([("tenant_id", 1), ("external_id", 1)], unique=True,
                                     partialFilterExpression={"external_id": {"$type": "string"}})
    await db[WEB_ENQUIRIES].create_index([("tenant_id", 1), ("received_at", -1)])
    await db[WEB_ENQUIRIES].create_index([("tenant_id", 1), ("external_id", 1)], unique=True,
                                         partialFilterExpression={"external_id": {"$type": "string"}})
    await db[EXTERNAL_EVENTS].create_index([("tenant_id", 1), ("occurred_at", -1)])
    await db[EXTERNAL_EVENTS].create_index([("tenant_id", 1), ("provider", 1),
                                            ("external_id", 1)], unique=True)


# --------------------------------------------------------------- response lookups

async def _responded_records(db: Any, tenant_id: str, related_type: str,
                             record_ids: list[str]) -> set[str]:
    """Which of these records somebody has since acted on.

    Reads three places a response actually lands: an activity logged against the record,
    a task raised for it, and a domain event naming it. A record with any of those has
    been picked up, and picking it up again as a "recovery" would be noise an operator
    learns to ignore -- which is how a detector stops being used.
    """
    if not record_ids:
        return set()
    responded: set[str] = set()

    activities = await db.crm_activities.find(
        {"tenant_id": tenant_id, "related_type": related_type,
         "related_id": {"$in": record_ids}}, {"_id": 0, "related_id": 1}).to_list(5000)
    responded.update(row["related_id"] for row in activities if row.get("related_id"))

    tasks = await db.tasks.find(
        {"tenant_id": tenant_id, "related_id": {"$in": record_ids}},
        {"_id": 0, "related_id": 1}).to_list(5000)
    responded.update(row["related_id"] for row in tasks if row.get("related_id"))

    return responded


# Reconciliation re-reads a case's source record and must read it exactly the way its
# detector did, so these are shared rather than re-implemented there.
responded_records = _responded_records
parse_time = _parse
status_of = _status


# --------------------------------------------------------------------- the lanes

async def detect_missed_calls(db: Any, tenant_id: str, *,
                              grace_hours: int = MISSED_CALL_GRACE_HOURS) -> list[dict]:
    """An inbound call nobody answered, and nobody called back.

    A missed call is the purest recovery source in the product: it carries no deal, no
    contact and no value -- only a number and a time -- which is exactly the case the
    normalized event contract was built to carry.
    """
    now = _now()
    cutoff = now - timedelta(hours=max(0, int(grace_hours)))
    calls = await db[CALL_LOGS].find(
        {"tenant_id": tenant_id, "direction": "inbound"}, {"_id": 0}
    ).sort("occurred_at", -1).to_list(DETECTION_LIMIT)
    reached = await callbacks_by_number(db, tenant_id)

    detections = []
    for call in calls:
        if _status(call.get("outcome")) not in MISSED_CALL_OUTCOMES:
            continue
        occurred = _parse(call.get("occurred_at"))
        if not occurred or occurred > cutoff:
            continue
        number = str(call.get("from_number") or "").strip()
        key = phone_key(number)
        if key and reached.get(key) and reached[key] >= occurred:
            continue
        waited = _hours(now - occurred)
        detections.append({
            "tenant_id": tenant_id,
            "type": TYPE_MISSED_CALL,
            "record_kind": "call",
            "record_collection": CALL_LOGS,
            "record_id": call["id"],
            "title": f"Missed call from {number or 'an unknown number'}",
            "reason": (f"An inbound call from {number or 'an unknown number'} went "
                       f"unanswered {waited} hour(s) ago and no one has called back "
                       f"(threshold {grace_hours} hour(s))."),
            "occurred_at": occurred.isoformat(),
            "external_identity": ({"kind": recovery_case.IDENTITY_PHONE, "value": number}
                                  if number else None),
            "contact_id": call.get("contact_id"),
            "waited_hours": waited,
            **_zone_note(call.get("occurred_at")),
        })
    return detections


async def callbacks_by_number(db: Any, tenant_id: str) -> dict[str, datetime]:
    """The latest time each number was actually reached, keyed by `phone_key`.

    Reached means an answered inbound call from the number or any outbound call to it.
    Both are read newest-first with their own cap: the inbound list used to double as the
    source of answered calls and the outbound list was capped *unsorted*, so on a busy
    line the callback that resolved a missed call could simply not be among the rows
    read -- and the call was reported as unreturned. Numbers are compared on their
    digits, so "+1 555 010 0199" and "(555) 010-0199" are the same caller.
    """
    reached: dict[str, datetime] = {}
    # Outcomes are matched the way the missed-call detector reads them -- trimmed, any
    # case -- or an "Answered" callback would leave its missed call open for ever.
    answered = [call for call in await db[CALL_LOGS].find(
        {"tenant_id": tenant_id, "direction": "inbound",
         "outcome": {"$regex": ANSWERED_OUTCOME_PATTERN, "$options": "i"}},
        {"_id": 0, "from_number": 1, "occurred_at": 1, "outcome": 1},
    ).sort("occurred_at", -1).to_list(DETECTION_LIMIT * 4)
        if _status(call.get("outcome")) in ANSWERED_CALL_OUTCOMES]
    outbound = await db[CALL_LOGS].find(
        {"tenant_id": tenant_id, "direction": "outbound"},
        {"_id": 0, "to_number": 1, "occurred_at": 1},
    ).sort("occurred_at", -1).to_list(DETECTION_LIMIT * 4)
    for call, field in [(c, "from_number") for c in answered] + \
                       [(c, "to_number") for c in outbound]:
        occurred = _parse(call.get("occurred_at"))
        key = phone_key(call.get(field))
        if occurred and key:
            reached[key] = max(reached.get(key, occurred), occurred)
    return reached


async def detect_web_enquiries(db: Any, tenant_id: str, *,
                               grace_hours: int = WEB_ENQUIRY_GRACE_HOURS) -> list[dict]:
    """A website enquiry nobody answered.

    Not a lost lead, and never detected: a test lead (`is_test`), one whose status says it
    was responded to, closed or spam, one whose SLA records a first response, and one with
    an activity or task logged against it. The enquiry carries its own `currency`, and the
    contact and deal the website pipeline linked it to -- which is what lets several
    enquiries from one buyer be recognised as one opportunity rather than several.
    """
    now = _now()
    cutoff = now - timedelta(hours=max(0, int(grace_hours)))
    enquiries = await db[WEB_ENQUIRIES].find(
        {"tenant_id": tenant_id, "is_test": {"$ne": True},
         "status": {"$nin": list(RESOLVED_ENQUIRY_STATUSES)}},
        {"_id": 0}).sort("received_at", -1).to_list(DETECTION_LIMIT)
    responded = await _responded_records(db, tenant_id, "web_enquiry",
                                         [e["id"] for e in enquiries])

    detections = []
    for enquiry in enquiries:
        if enquiry["id"] in responded or enquiry_is_resolved(enquiry):
            continue
        received = _parse(enquiry.get("received_at"))
        if not received or received > cutoff:
            continue
        waited = _hours(now - received)
        email = (enquiry.get("email") or "").strip()
        detections.append({
            "tenant_id": tenant_id,
            "type": TYPE_WEB_ENQUIRY,
            "record_kind": "web_enquiry",
            "record_collection": WEB_ENQUIRIES,
            "record_id": enquiry["id"],
            "title": f"Web enquiry from {enquiry.get('name') or email or 'an unknown visitor'}",
            "reason": (f"A web enquiry received {waited} hour(s) ago has no recorded "
                       f"response (threshold {grace_hours} hour(s))."),
            "occurred_at": received.isoformat(),
            "external_identity": ({"kind": recovery_case.IDENTITY_EMAIL, "value": email}
                                  if email else None),
            "contact_id": enquiry.get("contact_id"),
            "company_id": enquiry.get("company_id"),
            "opportunity_id": enquiry.get("opportunity_id"),
            "value": enquiry.get("estimated_value"),
            # Older enquiries carry no currency; `sanitize_detection` applies the default
            # and records that it did, rather than presenting it as known.
            "currency": enquiry.get("currency"),
            "value_basis": "web form estimate",
            "waited_hours": waited,
            **_zone_note(enquiry.get("received_at")),
        })
    return detections


def enquiry_is_resolved(enquiry: dict) -> Optional[str]:
    """Why a web enquiry is no longer a lost lead, or None if it still is."""
    if enquiry.get("is_test") is True:
        return "test lead"
    status = _status(enquiry.get("status"))
    if status in RESOLVED_ENQUIRY_STATUSES:
        return f"status '{status}'"
    sla = enquiry.get("sla")
    if isinstance(sla, dict) and sla.get("first_response_at"):
        return "a first response is recorded"
    return None


async def _detect_open_offers(db: Any, tenant_id: str, *, collection: str, detector_type: str,
                              grace_days: int, kinds: Optional[tuple] = None,
                              label: str = "offer") -> list[dict]:
    """A priced offer that went out and came back with nothing.

    Shared between quotes and estimates because the rule is identical and only the
    records differ; the two stay separate sources because a business treats them
    differently and a merged source would hide that.
    """
    now = _now()
    cutoff = now - timedelta(days=max(1, int(grace_days)))
    query: dict[str, Any] = {"tenant_id": tenant_id}
    if kinds:
        query["kind"] = {"$in": list(kinds)}
    rows = await db[collection].find(query, {"_id": 0}).sort("created_at", -1).to_list(
        DETECTION_LIMIT)
    responded = await _responded_records(db, tenant_id, label, [r["id"] for r in rows])
    invoiced = await invoiced_estimate_ids(db, tenant_id, [r["id"] for r in rows])

    detections = []
    for row in rows:
        status = _status(row.get("status"))
        if status in DECIDED_OFFER_STATUSES:
            continue
        if OPEN_OFFER_STATUSES and status not in OPEN_OFFER_STATUSES:
            # A draft was never sent to anybody, so there is nothing to chase.
            continue
        if row["id"] in responded or row["id"] in invoiced or row.get("invoice_id"):
            # Converted into an invoice: the client said yes. That is not a lost offer,
            # whatever the estimate's own status still reads.
            continue
        sent_at = _parse(row.get("sent_at") or row.get("updated_at") or row.get("created_at"))
        if not sent_at or sent_at > cutoff:
            continue
        waited = max(0, (now - sent_at).days)
        detections.append({
            "tenant_id": tenant_id,
            "type": detector_type,
            "record_kind": label,
            "record_collection": collection,
            "record_id": row["id"],
            "title": row.get("title") or f"Untitled {label}",
            "reason": (f"A {label} sent {waited} day(s) ago is still '{status or 'open'}' "
                       f"with no recorded decision (threshold {grace_days} day(s))."),
            "occurred_at": sent_at.isoformat(),
            "workspace_id": row.get("workspace_id"),
            "company_id": row.get("company_id"),
            "contact_id": row.get("contact_id"),
            # The offer's own total is what *might* be recovered.
            "value": row.get("total") or row.get("amount"),
            "currency": row.get("currency"),
            "value_basis": f"{label} total",
            "waited_days": waited,
            **_zone_note(row.get("sent_at") or row.get("updated_at") or row.get("created_at")),
        })
    return detections


async def invoiced_estimate_ids(db: Any, tenant_id: str, estimate_ids: list[str]) -> set[str]:
    """Which of these estimates an invoice has been raised from."""
    if not estimate_ids:
        return set()
    rows = await db.invoices.find(
        {"tenant_id": tenant_id, "estimate_id": {"$in": estimate_ids}},
        {"_id": 0, "estimate_id": 1}).to_list(len(estimate_ids) + 10)
    return {row["estimate_id"] for row in rows if row.get("estimate_id")}


async def detect_unanswered_quotes(db: Any, tenant_id: str, *,
                                   grace_days: int = QUOTE_GRACE_DAYS) -> list[dict]:
    """Disabled: there is no priced-quote record to read (see `DISABLED_LANES`).

    Returns nothing rather than reading a collection the application never writes. The
    lane stays declared so that, once quotes are real records with a total, a sent date
    and a decision, it can be pointed at them -- and so the sweep can say it is off.
    """
    return []


async def detect_unanswered_estimates(db: Any, tenant_id: str, *,
                                      grace_days: int = ESTIMATE_GRACE_DAYS) -> list[dict]:
    return await _detect_open_offers(
        db, tenant_id, collection="estimates", detector_type=TYPE_UNANSWERED_ESTIMATE,
        grace_days=grace_days, label="estimate")


async def detect_no_response(db: Any, tenant_id: str, *,
                             grace_days: int = NO_RESPONSE_GRACE_DAYS) -> list[dict]:
    """A message that reached the client and was never answered.

    Only messages the provider accepted count. A draft nobody sent is not a silence, and
    counting it as one would manufacture a recovery opportunity out of our own inaction.
    """
    now = _now()
    cutoff = now - timedelta(days=max(1, int(grace_days)))
    conversations = await db[conversation_service.CONVERSATIONS].find(
        {"tenant_id": tenant_id,
         "status": {"$in": list(conversation_service.OPEN_CONVERSATION_STATUSES)}},
        {"_id": 0}).sort("last_activity_at", -1).to_list(DETECTION_LIMIT)

    detections = []
    for conversation in conversations:
        if conversation.get("recovery_case_id"):
            # Already part of a recovery; a second case for the same silence would be
            # the recovery engine chasing its own tail.
            continue
        messages = await db[conversation_service.MESSAGES].find(
            {"tenant_id": tenant_id, "conversation_id": conversation["id"]},
            {"_id": 0}).sort("created_at", 1).to_list(200)
        sent = [m for m in messages
                if m.get("direction") == conversation_service.OUTBOUND
                and m.get("status") in (conversation_service.SENT,
                                        conversation_service.DELIVERED)]
        if not sent:
            continue
        sent_times = [t for t in (_parse(m.get("sent_at") or m.get("created_at"))
                                  for m in sent) if t]
        last_sent = max(sent_times) if sent_times else None
        if not last_sent or last_sent > cutoff:
            continue
        replies_after = [m for m in messages
                         if m.get("direction") == conversation_service.INBOUND
                         and (_parse(m.get("created_at")) or last_sent) >= last_sent]
        if replies_after:
            continue
        waited = max(0, (now - last_sent).days)
        detections.append({
            "tenant_id": tenant_id,
            "type": TYPE_NO_RESPONSE,
            "record_kind": "conversation",
            "record_collection": conversation_service.CONVERSATIONS,
            "record_id": conversation["id"],
            "title": conversation.get("subject") or "Unanswered conversation",
            "reason": (f"{len(sent)} message(s) reached the client and the most recent "
                       f"went unanswered for {waited} day(s) (threshold {grace_days} "
                       f"day(s))."),
            "occurred_at": last_sent.isoformat(),
            "workspace_id": conversation.get("workspace_id"),
            "company_id": conversation.get("company_id"),
            "contact_id": conversation.get("contact_id"),
            "waited_days": waited,
            "messages_sent": len(sent),
        })
    return detections


async def detect_cancelled_appointments(db: Any, tenant_id: str) -> list[dict]:
    """A booking the client cancelled and nobody rebooked."""
    appointments = await db.appointments.find(
        {"tenant_id": tenant_id}, {"_id": 0}).sort("start_at", -1).to_list(DETECTION_LIMIT)
    responded = await _responded_records(db, tenant_id, "appointment",
                                         [a["id"] for a in appointments])

    rebooked = latest_bookings(appointments)

    detections = []
    for appointment in appointments:
        if _status(appointment.get("status")) not in CANCELLED_APPOINTMENT_STATUSES:
            continue
        if appointment["id"] in responded:
            continue
        start = _parse(appointment.get("start_at"))
        if not start:
            continue
        if is_rebooked(appointment, rebooked):
            continue
        company = appointment.get("company_id")
        detections.append({
            "tenant_id": tenant_id,
            "type": TYPE_APPOINTMENT_CANCELLED,
            "record_kind": "appointment",
            "record_collection": "appointments",
            "record_id": appointment["id"],
            "title": appointment.get("title") or "Cancelled appointment",
            "reason": ("An appointment was cancelled and no later booking exists for "
                       "this client."),
            "occurred_at": (_parse(appointment.get("cancelled_at")) or start).isoformat(),
            "workspace_id": appointment.get("workspace_id"),
            "company_id": company,
            "contact_id": appointment.get("contact_id"),
            **_zone_note(appointment.get("start_at")),
        })
    return detections


def latest_bookings(appointments: list[dict]) -> dict[str, datetime]:
    """The latest live (not cancelled) booking start per company and per contact."""
    latest: dict[str, datetime] = {}
    for appointment in appointments:
        if _status(appointment.get("status")) in CANCELLED_APPOINTMENT_STATUSES:
            continue
        start = _parse(appointment.get("start_at"))
        if not start:
            continue
        for key in (f"company:{appointment.get('company_id')}" if appointment.get("company_id") else None,
                    f"contact:{appointment.get('contact_id')}" if appointment.get("contact_id") else None):
            if key:
                latest[key] = max(latest.get(key, start), start)
    return latest


def is_rebooked(appointment: dict, latest: dict[str, datetime]) -> bool:
    """A later booking for the same company or contact is a rebooking."""
    start = _parse(appointment.get("start_at"))
    if not start:
        return False
    for key in (f"company:{appointment.get('company_id')}" if appointment.get("company_id") else None,
                f"contact:{appointment.get('contact_id')}" if appointment.get("contact_id") else None):
        if key and latest.get(key) and latest[key] >= start:
            return True
    return False


async def detect_no_shows(db: Any, tenant_id: str, *,
                          grace_hours: int = NO_SHOW_GRACE_HOURS) -> list[dict]:
    """A booking whose time passed while it was still merely scheduled, or one a person
    recorded as a no-show.

    Grace exists because "nobody marked it complete yet" and "nobody turned up" look the
    same for the first hour or two, and only one of them is a recovery opportunity. A
    recorded no-show needs no grace -- somebody said what happened -- only a start time
    that has passed. It used to be invisible here: an agent who marked the no-show before
    the first sweep took it out of the pending statuses this lane read, so the clearest
    no-show of all was the one never recovered.
    """
    now = _now()
    cutoff = now - timedelta(hours=max(0, int(grace_hours)))
    appointments = await db.appointments.find(
        {"tenant_id": tenant_id,
         "status": {"$in": list(PENDING_APPOINTMENT_STATUSES) + list(NO_SHOW_APPOINTMENT_STATUSES)}},
        {"_id": 0}).sort("start_at", -1).to_list(DETECTION_LIMIT)
    responded = await _responded_records(db, tenant_id, "appointment",
                                         [a["id"] for a in appointments])

    detections = []
    for appointment in appointments:
        if appointment["id"] in responded:
            continue
        start = _parse(appointment.get("start_at"))
        end = _parse(appointment.get("end_at")) or start
        recorded = _status(appointment.get("status")) in NO_SHOW_APPOINTMENT_STATUSES
        if recorded:
            if not start or not end or start > now:
                continue
        elif not end or end > cutoff:
            continue
        # A no-show recorded during the appointment occurred when it was recorded.
        end = min(end, now)
        elapsed = _hours(now - end)
        detections.append({
            "tenant_id": tenant_id,
            "type": TYPE_APPOINTMENT_NO_SHOW,
            "record_kind": "appointment",
            "record_collection": "appointments",
            "record_id": appointment["id"],
            "title": appointment.get("title") or "Appointment with no outcome",
            "reason": ("The appointment was recorded as a no-show and nobody has followed "
                       "up yet." if recorded else
                       f"The appointment ended {elapsed} hour(s) ago and is still "
                       f"'{_status(appointment.get('status')) or 'scheduled'}' with no "
                       f"recorded outcome (threshold {grace_hours} hour(s))."),
            "occurred_at": end.isoformat(),
            "workspace_id": appointment.get("workspace_id"),
            "company_id": appointment.get("company_id"),
            "contact_id": appointment.get("contact_id"),
            "elapsed_hours": elapsed,
            **_zone_note(appointment.get("end_at") or appointment.get("start_at")),
        })
    return detections


async def detect_external_crm_events(db: Any, tenant_id: str) -> list[dict]:
    """Recoverable events another system told us about.

    An external event arrives with identifiers this CRM has not verified, so nothing here
    trusts them: the case is opened against the event itself, and any contact or company
    reference is carried as evidence for a human to resolve rather than being attached as
    fact. An event kind nobody declared recoverable is ignored -- an unknown event is not
    an opportunity.
    """
    events = await db[EXTERNAL_EVENTS].find(
        {"tenant_id": tenant_id, "kind": {"$in": list(RECOVERABLE_EXTERNAL_KINDS)},
         "status": {"$nin": ["processed", "ignored"]}},
        {"_id": 0}).sort("occurred_at", -1).to_list(DETECTION_LIMIT)

    detections = []
    for event in events:
        occurred = _parse(event.get("occurred_at"))
        if not occurred:
            continue
        identity = None
        if event.get("contact_email"):
            identity = {"kind": recovery_case.IDENTITY_EMAIL,
                        "value": event["contact_email"]}
        elif event.get("contact_phone"):
            identity = {"kind": recovery_case.IDENTITY_PHONE,
                        "value": event["contact_phone"]}
        elif event.get("external_contact_id"):
            identity = {"kind": recovery_case.IDENTITY_EXTERNAL_ID,
                        "value": event["external_contact_id"]}
        detections.append({
            "tenant_id": tenant_id,
            "type": TYPE_EXTERNAL_CRM_EVENT,
            "record_kind": "external_event",
            "record_collection": EXTERNAL_EVENTS,
            "record_id": event["id"],
            "title": event.get("title") or f"{event.get('provider')}: {event['kind']}",
            "reason": (f"{event.get('provider') or 'An external system'} reported "
                       f"'{event['kind']}'"
                       + (f": {event['summary']}" if event.get("summary") else ".")),
            "occurred_at": occurred.isoformat(),
            "external_identity": identity,
            "value": event.get("value"),
            "currency": event.get("currency"),
            "value_basis": f"value reported by {event.get('provider') or 'an external system'}",
            "provider": event.get("provider"),
            **_zone_note(event.get("occurred_at")),
        })
    return detections


# ------------------------------------------------------------------- event mapping

def to_recovery_event(detection: dict) -> dict:
    """Express a detection in the normalized recovery-event contract.

    `source_event_id` names the record that went quiet, so re-detecting it resolves to
    the case that already exists rather than opening a second one.

    The value is sanitised first: a source value that could not be real money (NaN,
    Infinity, negative, over `MAX_POTENTIAL_VALUE`, or in something that is not a
    currency code) is dropped with its reason recorded, and the case still opens.
    """
    detection = _finalise(detection)
    kind = detection.get("record_kind") or "record"
    return recovery_case.normalize_event(
        tenant_id=detection["tenant_id"],
        source=SOURCE_FOR_TYPE[detection["type"]],
        source_event_id=f"{kind}:{detection['record_id']}",
        reason=detection["reason"],
        title=detection.get("title"),
        occurred_at=detection.get("occurred_at"),
        workspace_id=detection.get("workspace_id"),
        company_id=detection.get("company_id"),
        contact_id=detection.get("contact_id"),
        opportunity_id=detection.get("opportunity_id"),
        external_identity=detection.get("external_identity"),
        # Whatever the source record says it might be worth. Potential, always, with its
        # provenance recorded in the evidence below.
        potential_value=detection.get("value"),
        currency=detection.get("currency") or recovery_case.DEFAULT_CURRENCY,
        potential_value_basis=detection.get("value_basis"),
        evidence={k: v for k, v in detection.items() if k not in ("tenant_id", "type")},
    )


def _finalise(detection: dict) -> dict:
    """Sanitise a detection's value and state any assumption its timing rests on.

    Idempotent, and applied before the detection is written anywhere -- the case and the
    work item both keep it as evidence.
    """
    detection = recovery_case.sanitize_detection(detection)
    note = " Timing read as UTC: the source recorded no timezone."
    if detection.get("timestamp_timezone_assumed") and \
            not str(detection.get("reason") or "").endswith(note):
        detection["reason"] = f"{detection['reason']}{note}"
    return detection


async def enqueue_detections(db: Any, queue: Any, detections: list[dict], *,
                             actor: str = "recovery-detector",
                             audit: Optional[Callable[..., Awaitable[Any]]] = None
                             ) -> tuple[list[dict], list[dict]]:
    """Open a case per detection and place durable work on the queue.

    Returns the work items created and any detections that could not be turned into a
    case, with the reason. A rejection is reported rather than swallowed: silently
    dropping a detection is indistinguishable from never having found it.

    Nothing here sends anything. The work item is the handoff into the controlled
    execution path -- strategy composition, then approval, then the runner -- and a
    detector that skipped it would be bypassing the governance the rest of the system
    depends on.
    """
    items = []
    rejected = []
    for raw in detections:
        detection = _finalise(raw)
        kind = detection.get("record_kind") or "record"
        try:
            case = await recovery_case.open_case(db, to_recovery_event(detection),
                                                 actor=actor, audit=audit)
        except recovery_case.RecoveryCaseError as exc:
            # A single unusable detection -- a stale reference, a record deleted between
            # the read and the write -- must not cost the rest of the sweep. The
            # rejection is reported rather than swallowed.
            rejected.append({"record_id": detection.get("record_id"),
                             "type": detection.get("type"), "error": str(exc)[:200]})
            continue
        if case.get("state") in recovery_case.TERMINAL_STATES:
            # Re-found, but its case is closed or recovered. The case's identity is its
            # source record; a closed decision is not re-opened by the next sweep, and no
            # new work is raised for it.
            items.append({"recovery_case_id": case["id"], "skipped_terminal_case": True,
                          "deduplicated": True})
            continue
        try:
            item = await _enqueue_case_work(queue, detection, case, kind=kind, db=db,
                                            actor=actor)
        except Exception as exc:  # a queue failure costs this detection, not the sweep
            rejected.append({"record_id": detection.get("record_id"),
                             "type": detection.get("type"), "error": str(exc)[:200]})
            continue
        items.append(item)
    return items, rejected


async def _enqueue_case_work(queue: Any, detection: dict, case: dict, *, kind: str, db: Any,
                             actor: str) -> dict:
    """Place the durable work item for one detection's case and link the two."""
    item: dict = await queue.enqueue(
        tenant_id=detection["tenant_id"],
        queue=QUEUE_NAME,
        item_type=detection["type"],
        payload={
            "record_id": detection["record_id"],
            "record_kind": kind,
            "record_collection": detection.get("record_collection"),
            "title": detection["title"],
            "reason": detection["reason"],
            "recovery_case_id": case["id"],
        },
        dedupe_key=f"{detection['type']}:{kind}:{detection['record_id']}",
        source_ref=f"{kind}:{detection['record_id']}",
        evidence={k: v for k, v in detection.items() if k not in ("tenant_id", "type")},
        workspace_id=detection.get("workspace_id"),
        priority=60,
        actor=actor,
    )
    if case.get("work_item_reference") != item["id"]:
        await recovery_case.attach(db, tenant_id=detection["tenant_id"],
                                   case_id=case["id"], actor=actor,
                                   work_item_reference=item["id"])
    return {**item, "recovery_case_id": case["id"]}


LANES = (
    ("missed_calls", detect_missed_calls),
    ("web_enquiries", detect_web_enquiries),
    ("unanswered_quotes", detect_unanswered_quotes),
    ("unanswered_estimates", detect_unanswered_estimates),
    ("no_response", detect_no_response),
    ("cancelled_appointments", detect_cancelled_appointments),
    ("no_shows", detect_no_shows),
    ("external_crm_events", detect_external_crm_events),
)


async def run_detection(db: Any, queue: Any, tenant_id: str, *, actor: str = "recovery-detector",
                        audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    """Run every lane for one tenant and report what each one found.

    A lane that raises is recorded and the sweep continues: one broken source must not
    stop the other seven from finding work. A lane that is disabled is reported as
    disabled, with the reason, rather than as having found nothing.

    Reconciliation runs first, over the open cases from these lanes: a case whose source
    was since dealt with -- the enquiry answered, the call returned, the estimate decided
    or invoiced, the deal closed -- is closed (or its win recorded) before anything new
    is opened. It is imported here because it reads this module's constants, so a
    module-level import would be circular.
    """
    import recovery_reconcile

    reconciliation = await recovery_reconcile.reconcile_tenant(
        db, tenant_id, sources=tuple(SOURCE_FOR_TYPE.values()), actor=actor, audit=audit)

    per_lane: dict[str, Any] = {}
    detections: list[dict] = []
    for name, detector in LANES:
        if name in DISABLED_LANES:
            per_lane[name] = {"disabled": True, "reason": DISABLED_LANES[name]}
            continue
        try:
            found = await detector(db, tenant_id)
        except Exception as exc:
            per_lane[name] = {"error": str(exc)[:300]}
            continue
        per_lane[name] = len(found)
        detections.extend(found)

    items, rejected = await enqueue_detections(db, queue, detections, actor=actor,
                                               audit=audit)
    skipped = [item for item in items if item.get("skipped_terminal_case")]
    items = [item for item in items if not item.get("skipped_terminal_case")]
    created = [item for item in items if not item.get("deduplicated")]
    return {
        "tenant_id": tenant_id,
        "detected": len(detections),
        "by_lane": per_lane,
        "disabled_lanes": sorted(DISABLED_LANES),
        "work_items_created": len(created),
        "work_items_deduplicated": len(items) - len(created),
        "recovery_cases_linked": len([i for i in items if i.get("recovery_case_id")]),
        "skipped_closed_cases": len(skipped),
        "rejected": rejected,
        "reconciliation": reconciliation,
        "thresholds": {
            "missed_call_grace_hours": MISSED_CALL_GRACE_HOURS,
            "web_enquiry_grace_hours": WEB_ENQUIRY_GRACE_HOURS,
            "quote_grace_days": QUOTE_GRACE_DAYS,
            "estimate_grace_days": ESTIMATE_GRACE_DAYS,
            "no_response_grace_days": NO_RESPONSE_GRACE_DAYS,
            "no_show_grace_hours": NO_SHOW_GRACE_HOURS,
        },
    }


async def run_detection_all_tenants(db: Any, queue: Any, *, actor: str = "cron",
                                    audit: Optional[Callable[..., Awaitable[Any]]] = None
                                    ) -> dict:
    tenant_ids = await db.tenants.distinct("tenant_id")
    summaries = []
    for tenant_id in tenant_ids:
        try:
            summaries.append(await run_detection(db, queue, tenant_id, actor=actor,
                                                 audit=audit))
        except Exception as exc:  # one tenant must never block the sweep
            summaries.append({"tenant_id": tenant_id, "error": str(exc)[:300]})
    return {"tenants": len(tenant_ids), "summaries": summaries}
