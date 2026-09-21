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

# Document kinds that represent a priced offer awaiting a decision.
QUOTE_KINDS = ("quote", "proposal", "pricing")

# Statuses that mean a priced offer is out with the client and undecided.
OPEN_OFFER_STATUSES = ("sent", "issued", "awaiting_response", "pending")
DECIDED_OFFER_STATUSES = ("approved", "accepted", "rejected", "declined", "won", "lost",
                          "invoiced", "cancelled", "expired", "withdrawn")

CANCELLED_APPOINTMENT_STATUSES = ("cancelled", "canceled")
COMPLETED_APPOINTMENT_STATUSES = ("completed", "done", "attended", "fulfilled")
PENDING_APPOINTMENT_STATUSES = ("scheduled", "confirmed", "booked")

# External events worth recovering. An event kind nobody declared is ignored rather than
# guessed at: an unknown event is not an opportunity, it is an unknown.
RECOVERABLE_EXTERNAL_KINDS = ("lead_lost", "deal_lost", "opportunity_stalled",
                              "quote_expired", "subscription_cancelled",
                              "enquiry_unanswered", "appointment_cancelled")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


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

    # A later call with the same number, in either direction, means contact was made.
    reached: dict[str, datetime] = {}
    for call in calls:
        if _status(call.get("outcome")) in ANSWERED_CALL_OUTCOMES:
            occurred = _parse(call.get("occurred_at"))
            number = str(call.get("from_number") or "").strip()
            if occurred and number:
                reached[number] = max(reached.get(number, occurred), occurred)
    callbacks = await db[CALL_LOGS].find(
        {"tenant_id": tenant_id, "direction": "outbound"}, {"_id": 0}).to_list(DETECTION_LIMIT)
    for call in callbacks:
        occurred = _parse(call.get("occurred_at"))
        number = str(call.get("to_number") or "").strip()
        if occurred and number:
            reached[number] = max(reached.get(number, occurred), occurred)

    detections = []
    for call in calls:
        if _status(call.get("outcome")) not in MISSED_CALL_OUTCOMES:
            continue
        occurred = _parse(call.get("occurred_at"))
        if not occurred or occurred > cutoff:
            continue
        number = str(call.get("from_number") or "").strip()
        if number and reached.get(number) and reached[number] >= occurred:
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
        })
    return detections


async def detect_web_enquiries(db: Any, tenant_id: str, *,
                               grace_hours: int = WEB_ENQUIRY_GRACE_HOURS) -> list[dict]:
    """A website enquiry nobody answered."""
    now = _now()
    cutoff = now - timedelta(hours=max(0, int(grace_hours)))
    enquiries = await db[WEB_ENQUIRIES].find(
        {"tenant_id": tenant_id, "status": {"$nin": ["responded", "closed", "spam"]}},
        {"_id": 0}).sort("received_at", -1).to_list(DETECTION_LIMIT)
    responded = await _responded_records(db, tenant_id, "web_enquiry",
                                         [e["id"] for e in enquiries])

    detections = []
    for enquiry in enquiries:
        if enquiry["id"] in responded:
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
            "value": enquiry.get("estimated_value"),
            "waited_hours": waited,
        })
    return detections


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

    detections = []
    for row in rows:
        status = _status(row.get("status"))
        if status in DECIDED_OFFER_STATUSES:
            continue
        if OPEN_OFFER_STATUSES and status not in OPEN_OFFER_STATUSES:
            # A draft was never sent to anybody, so there is nothing to chase.
            continue
        if row["id"] in responded:
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
            "waited_days": waited,
        })
    return detections


async def detect_unanswered_quotes(db: Any, tenant_id: str, *,
                                   grace_days: int = QUOTE_GRACE_DAYS) -> list[dict]:
    return await _detect_open_offers(
        db, tenant_id, collection="documents", detector_type=TYPE_UNANSWERED_QUOTE,
        grace_days=grace_days, kinds=QUOTE_KINDS, label="quote")


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

    # A later booking for the same company is a rebooking, so there is nothing to recover.
    rebooked: dict[str, datetime] = {}
    for appointment in appointments:
        if _status(appointment.get("status")) in CANCELLED_APPOINTMENT_STATUSES:
            continue
        start = _parse(appointment.get("start_at"))
        company = appointment.get("company_id")
        if start and company:
            rebooked[company] = max(rebooked.get(company, start), start)

    detections = []
    for appointment in appointments:
        if _status(appointment.get("status")) not in CANCELLED_APPOINTMENT_STATUSES:
            continue
        if appointment["id"] in responded:
            continue
        start = _parse(appointment.get("start_at"))
        if not start:
            continue
        company = appointment.get("company_id")
        if company and rebooked.get(company) and rebooked[company] >= start:
            continue
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
        })
    return detections


async def detect_no_shows(db: Any, tenant_id: str, *,
                          grace_hours: int = NO_SHOW_GRACE_HOURS) -> list[dict]:
    """A booking whose time passed while it was still merely scheduled.

    Grace exists because "nobody marked it complete yet" and "nobody turned up" look the
    same for the first hour or two, and only one of them is a recovery opportunity.
    """
    now = _now()
    cutoff = now - timedelta(hours=max(0, int(grace_hours)))
    appointments = await db.appointments.find(
        {"tenant_id": tenant_id,
         "status": {"$in": list(PENDING_APPOINTMENT_STATUSES)}},
        {"_id": 0}).sort("start_at", -1).to_list(DETECTION_LIMIT)
    responded = await _responded_records(db, tenant_id, "appointment",
                                         [a["id"] for a in appointments])

    detections = []
    for appointment in appointments:
        if appointment["id"] in responded:
            continue
        end = _parse(appointment.get("end_at")) or _parse(appointment.get("start_at"))
        if not end or end > cutoff:
            continue
        elapsed = _hours(now - end)
        detections.append({
            "tenant_id": tenant_id,
            "type": TYPE_APPOINTMENT_NO_SHOW,
            "record_kind": "appointment",
            "record_collection": "appointments",
            "record_id": appointment["id"],
            "title": appointment.get("title") or "Appointment with no outcome",
            "reason": (f"The appointment ended {elapsed} hour(s) ago and is still "
                       f"'{_status(appointment.get('status')) or 'scheduled'}' with no "
                       f"recorded outcome (threshold {grace_hours} hour(s))."),
            "occurred_at": end.isoformat(),
            "workspace_id": appointment.get("workspace_id"),
            "company_id": appointment.get("company_id"),
            "contact_id": appointment.get("contact_id"),
            "elapsed_hours": elapsed,
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
            "provider": event.get("provider"),
        })
    return detections


# ------------------------------------------------------------------- event mapping

def to_recovery_event(detection: dict) -> dict:
    """Express a detection in the normalized recovery-event contract.

    `source_event_id` names the record that went quiet, so re-detecting it resolves to
    the case that already exists rather than opening a second one.
    """
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
        external_identity=detection.get("external_identity"),
        # Whatever the source record says it might be worth. Potential, always, with its
        # provenance recorded in the evidence below.
        potential_value=detection.get("value"),
        currency=detection.get("currency") or recovery_case.DEFAULT_CURRENCY,
        evidence={k: v for k, v in detection.items() if k not in ("tenant_id", "type")},
    )


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
    for detection in detections:
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
        item = await queue.enqueue(
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
        items.append({**item, "recovery_case_id": case["id"]})
    return items, rejected


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
    stop the other seven from finding work.
    """
    per_lane: dict[str, Any] = {}
    detections: list[dict] = []
    for name, detector in LANES:
        try:
            found = await detector(db, tenant_id)
        except Exception as exc:
            per_lane[name] = {"error": str(exc)[:300]}
            continue
        per_lane[name] = len(found)
        detections.extend(found)

    items, rejected = await enqueue_detections(db, queue, detections, actor=actor,
                                               audit=audit)
    created = [item for item in items if not item.get("deduplicated")]
    return {
        "tenant_id": tenant_id,
        "detected": len(detections),
        "by_lane": per_lane,
        "work_items_created": len(created),
        "work_items_deduplicated": len(items) - len(created),
        "recovery_cases_linked": len([i for i in items if i.get("recovery_case_id")]),
        "rejected": rejected,
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
