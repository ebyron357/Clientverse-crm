"""Reconciliation — re-reading every open case's source, and closing what has resolved.

Detection only ever opened cases. Nothing re-read a case's source afterwards, so a web
enquiry that was answered the next morning, a missed call that was returned, a deal that
closed -- each stayed an open case for ever, and "open potential" only grew. This module
is the other half of detection: on every sweep it re-reads the record behind each open
case and asks whether the situation the case exists for is still true.

THE RULES

Deal first, for any case that knows its deal (`opportunity_id`), whatever its source --
and for a case that knows only a contact, when that contact is on exactly one deal and the
case was opened before that deal closed:

* archived -> closed `deal_archived`; lost (by the tenant's own pipeline) -> `deal_lost`;
* **won** -> the win is recorded once, through the attribution ledger, against the one
  case best placed to claim it -- a case whose outreach actually reached the client if
  there is one, otherwise the earliest. The ledger decides attributed or unattributed
  from the messages, refuses to book the same sale twice, and closes or recovers the
  case. Every other open case on the same deal is closed `sale_recorded_on_another_case`.
  A deal already won before a case was opened is not a recovery: `deal_won_before_case`.
  A win whose record cannot be booked (an unusable value or currency) is refused once,
  with the reason, and its cases closed `outcome_refused` -- not retried every sweep.
* every open case on the deal takes part, *whichever sweep is running*: the two sweeps
  reconcile different sources, and choosing the claimant from only one sweep's cases
  made the attribution depend on which cron fired first;
* still open -> a dormant-deal case's value, currency and contact are refreshed from the
  deal, so a re-priced or reawakened deal shows its current figure.

Then the source record, read the way its detector reads it:

* web enquiry: a test lead or spam is closed outright (it never counted); responded,
  closed, a recorded first response, or an activity/task logged against it is resolved;
* missed call: an answered call from, or any call to, the same number afterwards
  (compared on digits) is resolved;
* estimate: invoiced and paid -> an `invoice_paid` outcome through the ledger, so the
  payment is recorded (unattributed unless the case was worked); accepted or invoiced but
  not yet paid -> left open, awaiting the money; declined, expired, cancelled, or every
  invoice voided -> closed outright;
* unanswered conversation: the client replied, or the conversation was closed;
* cancelled appointment: rebooked, or no longer cancelled. No-show: attended, or a later
  booking -- an operator recording `no_show` confirms the case rather than resolving it;
* missed follow-up: the commitment or task was completed;
* external event: processed or ignored by the system that reported it;
* a source record that no longer exists closes the case `source_missing`.

ENGAGED CASES WAIT FOR AN OUTCOME

A case whose outreach reached the client (`engaged`) is not closed by a *soft* signal --
an enquiry marked responded, a call returned -- because that signal may well be the
outreach working, and closing the case would lose the outcome it is waiting for. Only a
hard signal (lost, archived, declined, spam, a recorded win) closes it, or the passing of
the attribution window with no outcome: after that nothing could be attributed to the
contact anyway, so the case is closed `attribution_window_elapsed`.

A DORMANT DEAL THAT WAKES UP IS NOT CLOSED

A dormant-deal case closes only on the deal's outcome. Activity resuming on the deal is
not a resolution of the money -- the deal is still open potential -- and closing on it
would be permanent: a case's identity is its source record, so the deal going quiet a
second time could never open a new case.

A case with an outcome being confirmed right now (a fresh in-flight ledger entry) is left
alone for that sweep: closing it mid-confirmation would turn attributed revenue into
unattributed for good.

Nothing here sends anything. Reconciliation only closes, and records outcomes through the
ledger, which derives everything from records.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import attribution
import conversations as conversation_service
import crm_core
import detectors
import recovery_case
import recovery_lifecycle
import second_chance

RECONCILE_LIMIT = int(os.environ.get("RECOVERY_RECONCILE_LIMIT", "2000"))
ACTOR = "recovery-reconciler"

# Offer statuses that close a case outright. A positive decision (approved, accepted,
# invoiced) does not close it: the case waits for the payment, which is the outcome.
NEGATIVE_OFFER_STATUSES = ("rejected", "declined", "lost", "cancelled", "expired", "withdrawn")
VOID_INVOICE_STATUSES = ("void", "voided", "cancelled", "canceled")

# How long an in-flight ledger entry keeps reconciliation off its case. Long enough to
# cover one confirmation; short enough that a crashed one does not shield a case for ever.
IN_FLIGHT_SECONDS = int(os.environ.get("RECOVERY_IN_FLIGHT_SECONDS", "900"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _source_record_id(case: dict) -> Optional[str]:
    _, _, record_id = str(case.get("source_event_id") or "").partition(":")
    return record_id or None


def _verdict(reason: str, detail: str, *, hard: bool) -> dict:
    return {"reason": reason, "detail": detail, "hard": hard}


async def _by_id(db: Any, collection: str, tenant_id: str, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    rows = await db[collection].find({"tenant_id": tenant_id, "id": {"$in": ids}},
                                     {"_id": 0}).to_list(len(ids) + 10)
    return {row["id"]: row for row in rows}


# ------------------------------------------------------------- source verdicts

async def _web_enquiry_verdicts(db: Any, tenant_id: str, cases: list[dict]) -> dict:
    ids = [rid for rid in (_source_record_id(c) for c in cases) if rid]
    records = await _by_id(db, detectors.WEB_ENQUIRIES, tenant_id, ids)
    responded = await detectors.responded_records(db, tenant_id, "web_enquiry", ids)
    verdicts = {}
    for case in cases:
        record = records.get(_source_record_id(case) or "")
        if record is None:
            verdicts[case["id"]] = _verdict("source_missing", "The web enquiry no longer exists.",
                                            hard=True)
        elif record.get("is_test") is True:
            verdicts[case["id"]] = _verdict("test_record", "The enquiry is a test lead.",
                                            hard=True)
        elif detectors.status_of(record.get("status")) == "spam":
            verdicts[case["id"]] = _verdict("source_resolved", "The enquiry was marked spam.",
                                            hard=True)
        elif detectors.enquiry_is_resolved(record):
            verdicts[case["id"]] = _verdict(
                "source_resolved",
                f"The enquiry is resolved: {detectors.enquiry_is_resolved(record)}.",
                hard=False)
        elif record["id"] in responded:
            verdicts[case["id"]] = _verdict(
                "source_resolved", "An activity or task was logged against the enquiry.",
                hard=False)
    return verdicts


async def _missed_call_verdicts(db: Any, tenant_id: str, cases: list[dict]) -> dict:
    ids = [rid for rid in (_source_record_id(c) for c in cases) if rid]
    records = await _by_id(db, detectors.CALL_LOGS, tenant_id, ids)
    reached = await detectors.callbacks_by_number(db, tenant_id)
    verdicts = {}
    for case in cases:
        record = records.get(_source_record_id(case) or "")
        if record is None:
            verdicts[case["id"]] = _verdict("source_missing", "The call record no longer exists.",
                                            hard=True)
            continue
        occurred = detectors.parse_time(record.get("occurred_at"))
        key = detectors.phone_key(record.get("from_number"))
        if occurred and key and reached.get(key) and reached[key] >= occurred:
            verdicts[case["id"]] = _verdict(
                "source_resolved",
                f"The number was reached afterwards ({reached[key].isoformat()}).", hard=False)
    return verdicts


async def _offer_verdicts(db: Any, tenant_id: str, cases: list[dict], *, collection: str,
                          label: str) -> tuple[dict, list[tuple[dict, dict]]]:
    """Verdicts for estimate/quote cases, plus (case, paid invoice) pairs to record."""
    ids = [rid for rid in (_source_record_id(c) for c in cases) if rid]
    records = await _by_id(db, collection, tenant_id, ids)
    invoices = await db.invoices.find(
        {"tenant_id": tenant_id, "estimate_id": {"$in": ids}}, {"_id": 0}
    ).to_list(len(ids) * 3 + 10) if ids and collection == "estimates" else []
    by_estimate: dict[str, list[dict]] = {}
    for invoice in invoices:
        by_estimate.setdefault(invoice["estimate_id"], []).append(invoice)
    verdicts: dict[str, dict] = {}
    paid: list[tuple[dict, dict]] = []
    for case in cases:
        record = records.get(_source_record_id(case) or "")
        if record is None:
            verdicts[case["id"]] = _verdict("source_missing", f"The {label} no longer exists.",
                                            hard=True)
            continue
        raised = by_estimate.get(record["id"], [])
        settled = [inv for inv in raised if attribution.invoice_is_paid(inv)]
        if settled:
            paid.append((case, settled[0]))
            continue
        status = detectors.status_of(record.get("status"))
        live = [inv for inv in raised
                if detectors.status_of(inv.get("status")) not in VOID_INVOICE_STATUSES]
        if raised and not live:
            verdicts[case["id"]] = _verdict(
                "source_resolved", f"Every invoice raised from the {label} was voided.",
                hard=True)
        elif not raised and status in NEGATIVE_OFFER_STATUSES:
            verdicts[case["id"]] = _verdict(
                "source_resolved", f"The {label} was {status}.", hard=True)
        # Accepted or invoiced but unpaid: no verdict. Closing here ("converted into an
        # invoice") meant the payment, when it came, was never recorded against anything;
        # the case now stays open until the money arrives (recorded above) or is lost.
    return verdicts, paid


async def _no_response_verdicts(db: Any, tenant_id: str, cases: list[dict]) -> dict:
    ids = [rid for rid in (_source_record_id(c) for c in cases) if rid]
    records = await _by_id(db, conversation_service.CONVERSATIONS, tenant_id, ids)
    inbound = await db[conversation_service.MESSAGES].find(
        {"tenant_id": tenant_id, "conversation_id": {"$in": ids},
         "direction": conversation_service.INBOUND},
        {"_id": 0, "conversation_id": 1, "created_at": 1}).to_list(len(ids) * 20 + 50) \
        if ids else []
    latest_reply: dict[str, str] = {}
    for message in inbound:
        at = str(message.get("created_at") or "")
        if at > latest_reply.get(message["conversation_id"], ""):
            latest_reply[message["conversation_id"]] = at
    verdicts = {}
    for case in cases:
        record = records.get(_source_record_id(case) or "")
        if record is None:
            verdicts[case["id"]] = _verdict("source_missing",
                                            "The conversation no longer exists.", hard=True)
            continue
        silent_since = detectors.parse_time(case.get("occurred_at"))
        reply = detectors.parse_time(latest_reply.get(record["id"]))
        if reply and silent_since and reply >= silent_since:
            verdicts[case["id"]] = _verdict("source_resolved", "The client replied.",
                                            hard=False)
        elif record.get("status") == conversation_service.STATUS_CLOSED:
            verdicts[case["id"]] = _verdict("source_resolved", "The conversation was closed.",
                                            hard=False)
    return verdicts


async def _appointment_verdicts(db: Any, tenant_id: str, cases: list[dict]) -> dict:
    ids = [rid for rid in (_source_record_id(c) for c in cases) if rid]
    records = await _by_id(db, "appointments", tenant_id, ids)
    recent = await db.appointments.find({"tenant_id": tenant_id}, {"_id": 0}).sort(
        "start_at", -1).to_list(detectors.DETECTION_LIMIT)
    latest = detectors.latest_bookings(recent + list(records.values()))
    verdicts = {}
    for case in cases:
        record = records.get(_source_record_id(case) or "")
        if record is None:
            verdicts[case["id"]] = _verdict("source_missing",
                                            "The appointment no longer exists.", hard=True)
            continue
        status = detectors.status_of(record.get("status"))
        if case["source"] == recovery_case.SOURCE_APPOINTMENT_CANCELLED:
            if status not in detectors.CANCELLED_APPOINTMENT_STATUSES:
                verdicts[case["id"]] = _verdict(
                    "source_resolved", f"The appointment is now '{status}'.", hard=False)
            elif detectors.is_rebooked(record, latest):
                verdicts[case["id"]] = _verdict(
                    "source_resolved", "The client has a later booking.", hard=False)
        # A no-show is resolved only by the client being seen: the appointment marked
        # attended, or a later booking. Marking it `no_show` (or anything else) is an
        # operator confirming the case, not resolving it.
        elif status in detectors.COMPLETED_APPOINTMENT_STATUSES:
            verdicts[case["id"]] = _verdict("source_resolved", "The appointment was attended.",
                                            hard=False)
        elif _later_booking(record, recent + list(records.values())):
            verdicts[case["id"]] = _verdict(
                "source_resolved", "The client has a later booking.", hard=False)
    return verdicts


def _later_booking(appointment: dict, appointments: list[dict]) -> bool:
    """Another live booking for the same client that starts after this one did."""
    start = detectors.parse_time(appointment.get("start_at"))
    if not start:
        return False
    keys = {(field, appointment.get(field)) for field in ("company_id", "contact_id")
            if appointment.get(field)}
    for other in appointments:
        if other.get("id") == appointment.get("id") or \
                detectors.status_of(other.get("status")) in \
                detectors.CANCELLED_APPOINTMENT_STATUSES:
            continue
        other_start = detectors.parse_time(other.get("start_at"))
        if other_start and other_start > start and \
                any(other.get(field) == value for field, value in keys):
            return True
    return False


async def _followup_verdicts(db: Any, tenant_id: str, cases: list[dict]) -> dict:
    by_kind: dict[str, list[str]] = {}
    for case in cases:
        kind, _, record_id = str(case.get("source_event_id") or "").partition(":")
        by_kind.setdefault(kind, []).append(record_id)
    commitments = await _by_id(db, "commitments", tenant_id, by_kind.get("commitment", []))
    tasks = await _by_id(db, "tasks", tenant_id, by_kind.get("task", []))
    verdicts = {}
    for case in cases:
        kind, _, record_id = str(case.get("source_event_id") or "").partition(":")
        record = (commitments if kind == "commitment" else tasks).get(record_id)
        if record is None:
            verdicts[case["id"]] = _verdict("source_missing", f"The {kind} no longer exists.",
                                            hard=True)
            continue
        status = str(record.get("status") or "").lower()
        done = (second_chance.RESOLVED_COMMITMENT_STATUSES if kind == "commitment"
                else second_chance.DONE_TASK_STATUSES)
        if status in done:
            verdicts[case["id"]] = _verdict("source_resolved", f"The {kind} is '{status}'.",
                                            hard=False)
    return verdicts


async def _external_verdicts(db: Any, tenant_id: str, cases: list[dict]) -> dict:
    ids = [rid for rid in (_source_record_id(c) for c in cases) if rid]
    records = await _by_id(db, detectors.EXTERNAL_EVENTS, tenant_id, ids)
    verdicts = {}
    for case in cases:
        record = records.get(_source_record_id(case) or "")
        if record is None:
            verdicts[case["id"]] = _verdict("source_missing", "The event no longer exists.",
                                            hard=True)
        elif detectors.status_of(record.get("status")) in ("processed", "ignored"):
            verdicts[case["id"]] = _verdict(
                "source_resolved",
                f"The reporting system marked the event '{record.get('status')}'.", hard=False)
    return verdicts


# ---------------------------------------------------------------- the sweep

async def reconcile_tenant(db: Any, tenant_id: str, *, sources: Optional[tuple] = None,
                           actor: str = ACTOR,
                           audit: Optional[Callable[..., Awaitable[Any]]] = None,
                           limit: int = RECONCILE_LIMIT) -> dict:
    """Re-read every open case's source for one tenant and close what has resolved.

    Never raises: a reconciliation failure is reported in the summary and must not cost
    the detection sweep that called it.
    """
    summary: dict[str, Any] = {"examined": 0, "truncated": False, "engaged": 0,
                               "closed": {}, "outcomes": [], "kept_open_engaged": 0,
                               "errors": []}
    try:
        await _reconcile(db, tenant_id, sources=sources, actor=actor, audit=audit,
                         limit=limit, summary=summary)
    except Exception as exc:
        summary["errors"].append(f"reconciliation stopped: {str(exc)[:300]}")
    return summary


async def _in_flight(db: Any, tenant_id: str, case_ids: list[str]) -> set[str]:
    """Cases with an outcome being confirmed right now (see `attribution.record_outcome`)."""
    if not case_ids:
        return set()
    cutoff = (_now() - timedelta(seconds=IN_FLIGHT_SECONDS)).isoformat()
    rows = await db[attribution.COLLECTION].find(
        {"tenant_id": tenant_id, "case_id": {"$in": case_ids},
         "confirming_since": {"$gte": cutoff}},
        {"_id": 0, "case_id": 1}).to_list(len(case_ids) + 10)
    return {row["case_id"] for row in rows}


async def _deals_of_contacts(db: Any, tenant_id: str,
                             contact_ids: set[str]) -> dict[str, set[str]]:
    """contact id -> the live (not archived) deals that name the contact."""
    if not contact_ids:
        return {}
    ids = list(contact_ids)
    deals = await db.opportunities.find(
        {"tenant_id": tenant_id, "archived_at": None,
         "$or": [{"contact_ids": {"$in": ids}}, {"contact_id": {"$in": ids}}]},
        {"_id": 0, "id": 1, "contact_ids": 1, "contact_id": 1}).to_list(len(ids) * 5 + 50)
    result: dict[str, set[str]] = {}
    for deal in deals:
        for contact in set(deal.get("contact_ids") or []) | {deal.get("contact_id")}:
            if contact in contact_ids:
                result.setdefault(contact, set()).add(deal["id"])
    return result


def _closed_at(deal: dict, classes: dict[str, set[str]], outcome: str) -> Optional[datetime]:
    """When the deal last moved into a stage of this outcome, else its last update."""
    for transition in reversed(deal.get("stage_history") or []):
        if crm_core.classify_stage(transition.get("to"), classes) == outcome:
            return detectors.parse_time(transition.get("at"))
    return detectors.parse_time(deal.get("updated_at"))


async def _reconcile(db: Any, tenant_id: str, *, sources: Optional[tuple], actor: str,
                     audit: Optional[Callable[..., Awaitable[Any]]], limit: int,
                     summary: dict) -> None:
    open_query: dict[str, Any] = {"tenant_id": tenant_id,
                                  "state": {"$in": list(recovery_case.OPEN_STATES)}}
    query = {**open_query, **({"source": {"$in": list(sources)}} if sources else {})}
    # Least recently reconciled first, so a tenant with more open cases than one sweep
    # reads still has every case re-checked in rotation rather than the same few.
    cases = await db[recovery_case.COLLECTION].find(query, {"_id": 0}).sort(
        "reconciled_at", 1).to_list(int(limit) + 1)
    summary["truncated"] = len(cases) > limit
    cases = cases[:limit]
    if not cases:
        return
    classes = await crm_core.stage_classes(db, tenant_id)

    # Every open case on a deal that has closed takes part in settling it, whichever
    # sweep is running and whatever its source -- including a contact-only case whose
    # contact is on that deal alone. The claimant for a win must be chosen from all of
    # them, or the result depends on which sweep happened to fire first.
    deal_ids = {c["opportunity_id"] for c in cases if c.get("opportunity_id")}
    contacts = {c["contact_id"] for c in cases
                if c.get("contact_id") and not c.get("opportunity_id")}
    for deal_set in (await _deals_of_contacts(db, tenant_id, contacts)).values():
        if len(deal_set) == 1:
            deal_ids |= deal_set
    deals = await _by_id(db, "opportunities", tenant_id, list(deal_ids))
    settled = [d for d in deal_ids if d not in deals or deals[d].get("archived_at")
               or crm_core.classify_stage(deals[d].get("stage"), classes)
               != crm_core.STAGE_OPEN]
    if settled:
        known = {c["id"] for c in cases}
        settled_contacts = {c for d in settled if d in deals
                            for c in set(deals[d].get("contact_ids") or [])
                            | {deals[d].get("contact_id")} if c}
        single = [c for c, ds in (await _deals_of_contacts(
            db, tenant_id, settled_contacts)).items() if len(ds) == 1 and ds <= set(settled)]
        relatives = await db[recovery_case.COLLECTION].find(
            {**open_query, "id": {"$nin": list(known)},
             "$or": [{"opportunity_id": {"$in": settled}},
                     {"opportunity_id": None, "contact_id": {"$in": single}}]},
            {"_id": 0}).to_list(500)
        cases += relatives
        summary["pulled_in_by_deal"] = len(relatives)

    in_flight = await _in_flight(db, tenant_id, [c["id"] for c in cases])
    if in_flight:
        cases = [c for c in cases if c["id"] not in in_flight]
        summary["skipped_in_flight"] = len(in_flight)
    summary["examined"] = len(cases)
    open_ids = {case["id"] for case in cases}

    async def close(case: dict, reason: str, detail: dict) -> None:
        if case["id"] not in open_ids:
            return
        try:
            closed = await recovery_lifecycle.close_if_open(
                db, tenant_id=tenant_id, case_id=case["id"], reason=reason, actor=actor,
                detail=detail, audit=audit)
        except recovery_case.RecoveryCaseError as exc:
            summary["errors"].append(f"{case['id']}: {str(exc)[:200]}")
            return
        open_ids.discard(case["id"])
        if closed:
            summary["closed"][reason] = summary["closed"].get(reason, 0) + 1

    async def record(case: dict, kind: str, record_id: str, others: list[dict]) -> None:
        """Record an outcome on `case`; close `others` that share the sale."""
        try:
            entry = await attribution.record_outcome(
                db, tenant_id=tenant_id, case_id=case["id"], kind=kind, record_id=record_id,
                actor=actor, note="Recorded by reconciliation from the source record.",
                audit=audit)
        except attribution.DuplicateSale as exc:
            for member in [case, *others]:
                await close(member, "sale_recorded_on_another_case",
                            {"attribution_entry_id": exc.entry.get("id"),
                             "recorded_on_case": exc.entry.get("case_id")})
            return
        except attribution.AttributionError as exc:
            # The record itself cannot be booked -- a won deal priced in "$", say. Refused
            # once, with the reason, and the cases closed: retrying every sweep would
            # report the same error for ever while the money sat in open potential.
            summary.setdefault("refused", []).append(
                {"case_id": case["id"], "kind": kind, "record_id": record_id,
                 "reason": str(exc)[:300]})
            for member in [case, *others]:
                await close(member, "outcome_refused",
                            {"kind": kind, "record_id": record_id, "reason": str(exc)[:300]})
            return
        open_ids.discard(case["id"])
        summary["outcomes"].append({"case_id": case["id"], "kind": kind,
                                    "record_id": record_id, "entry_id": entry.get("id"),
                                    "claim": entry.get("claim"),
                                    "deduplicated": entry.get("deduplicated", False)})
        for member in others:
            await close(member, "sale_recorded_on_another_case",
                        {"attribution_entry_id": entry.get("id"),
                         "recorded_on_case": case["id"]})

    # 0. An open case that already has an outcome in the ledger. Before outcomes closed
    #    their case, recording one left the case open, so the same money was counted in
    #    open potential and in an outcome bucket. Close those first.
    with_outcome = await db[attribution.COLLECTION].find(
        {"tenant_id": tenant_id, "case_id": {"$in": list(open_ids)}},
        {"_id": 0, "id": 1, "case_id": 1}).to_list(len(open_ids) + 10)
    for entry in with_outcome:
        case = next((c for c in cases if c["id"] == entry["case_id"]), None)
        if case:
            await close(case, "outcome_recorded", {"attribution_entry_id": entry["id"]})

    # 1. Engagement: a drafted message that has since been sent makes its case engaged.
    contact = await recovery_lifecycle.last_contact_by_case(db, tenant_id, list(open_ids))
    for case in cases:
        if case["state"] == recovery_case.EXECUTING and case["id"] in contact:
            if await recovery_lifecycle.sync_engagement(db, tenant_id=tenant_id,
                                                        case_id=case["id"], actor=actor,
                                                        audit=audit):
                case["state"] = recovery_case.ENGAGED
                summary["engaged"] += 1

    # 2. The deal: for every case that knows it, and for a contact-only case whose
    #    contact is on exactly one deal.
    single_deal = {contact_id: next(iter(ds)) for contact_id, ds in (await _deals_of_contacts(
        db, tenant_id, {c["contact_id"] for c in cases
                        if c.get("contact_id") and not c.get("opportunity_id")})).items()
                   if len(ds) == 1}
    by_deal: dict[str, list[dict]] = {}
    by_contact_deal: dict[str, list[dict]] = {}
    for case in cases:
        if case.get("opportunity_id"):
            by_deal.setdefault(case["opportunity_id"], []).append(case)
        elif case.get("contact_id") in single_deal:
            by_contact_deal.setdefault(single_deal[case["contact_id"]], []).append(case)
    missing = [d for d in set(by_deal) | set(by_contact_deal) if d not in deals]
    deals.update(await _by_id(db, "opportunities", tenant_id, missing))

    for deal_id in set(by_deal) | set(by_contact_deal):
        linked, by_contact = by_deal.get(deal_id, []), by_contact_deal.get(deal_id, [])
        deal = deals.get(deal_id)
        if deal is None:
            for case in linked:
                if case["source"] == recovery_case.SOURCE_DORMANT_DEAL:
                    await close(case, "source_missing", {"opportunity_id": deal_id})
            continue
        if deal.get("archived_at"):
            for case in linked:
                await close(case, "deal_archived", {"opportunity_id": deal_id})
            continue
        outcome = crm_core.classify_stage(deal.get("stage"), classes)
        if outcome == crm_core.STAGE_OPEN:
            await _refresh_from_deal(db, linked, deal, actor=actor, summary=summary)
            continue
        closed_at = _closed_at(deal, classes, outcome)

        def opened_before_close(case: dict, at: Optional[datetime] = closed_at) -> bool:
            opened = detectors.parse_time(case.get("created_at"))
            return not (at and opened and at < opened)

        # A contact-only case opened after the deal closed is new business from a known
        # client, not this deal: it is left alone.
        by_contact = [c for c in by_contact if opened_before_close(c)]
        if outcome == crm_core.STAGE_LOST:
            for case in linked + by_contact:
                await close(case, "deal_lost", {"opportunity_id": deal_id,
                                                "stage": deal.get("stage")})
            continue
        eligible = list(by_contact)
        for case in linked:
            if opened_before_close(case):
                eligible.append(case)
            else:
                await close(case, "deal_won_before_case",
                            {"opportunity_id": deal_id,
                             "won_at": closed_at.isoformat() if closed_at else None})
        if eligible:
            # The case whose outreach reached the client claims the win if there is one;
            # otherwise the earliest. Either way the sale is booked once.
            eligible.sort(key=lambda c: str(c.get("created_at") or ""))
            eligible.sort(key=lambda c: c["id"] not in contact)
            await record(eligible[0], attribution.OUTCOME_DEAL_WON, deal_id, eligible[1:])

    # 3. The source record.
    remaining = [case for case in cases if case["id"] in open_ids]
    by_source: dict[str, list[dict]] = {}
    for case in remaining:
        by_source.setdefault(case["source"], []).append(case)
    verdicts: dict[str, dict] = {}
    paid: list[tuple[dict, dict]] = []
    checks = {
        recovery_case.SOURCE_WEB_ENQUIRY: _web_enquiry_verdicts,
        recovery_case.SOURCE_MISSED_CALL: _missed_call_verdicts,
        recovery_case.SOURCE_NO_RESPONSE: _no_response_verdicts,
        recovery_case.SOURCE_APPOINTMENT_CANCELLED: _appointment_verdicts,
        recovery_case.SOURCE_APPOINTMENT_NO_SHOW: _appointment_verdicts,
        recovery_case.SOURCE_MISSED_FOLLOWUP: _followup_verdicts,
        recovery_case.SOURCE_EXTERNAL_CRM_EVENT: _external_verdicts,
    }
    for source, members in by_source.items():
        try:
            if source in checks:
                verdicts.update(await checks[source](db, tenant_id, members))
            elif source == recovery_case.SOURCE_UNANSWERED_ESTIMATE:
                found, settled_offers = await _offer_verdicts(
                    db, tenant_id, members, collection="estimates", label="estimate")
                verdicts.update(found)
                paid.extend(settled_offers)
            elif source == recovery_case.SOURCE_UNANSWERED_QUOTE:
                # The lane is disabled, but cases it opened before still deserve closing
                # when their record is decided or gone.
                found, _ = await _offer_verdicts(db, tenant_id, members,
                                                 collection="documents", label="quote")
                verdicts.update(found)
        except Exception as exc:  # one source's records must not stop the others
            summary["errors"].append(f"{source}: {str(exc)[:200]}")

    for case, invoice in paid:
        await record(case, attribution.OUTCOME_INVOICE_PAID, invoice["id"], [])

    for case in remaining:
        verdict = verdicts.get(case["id"])
        if not verdict or case["id"] not in open_ids:
            continue
        if case["state"] == recovery_case.ENGAGED and not verdict["hard"]:
            # Contact reached the client; this signal may be that contact working. The
            # case waits for an outcome (or the window) instead of being closed on it.
            summary["kept_open_engaged"] += 1
            continue
        await close(case, verdict["reason"], {"detail": verdict["detail"]})

    # 4. Engaged with nothing to show for it, past the attribution window.
    window = timedelta(days=await attribution.attribution_window_days(db, tenant_id))
    for case in cases:
        if case["id"] not in open_ids or case["state"] != recovery_case.ENGAGED:
            continue
        last = detectors.parse_time(contact.get(case["id"]))
        if last and _now() - last > window:
            await close(case, "attribution_window_elapsed",
                        {"last_contact_at": last.isoformat(), "window_days": window.days})

    await db[recovery_case.COLLECTION].update_many(
        {"tenant_id": tenant_id, "id": {"$in": [case["id"] for case in cases]}},
        {"$set": {"reconciled_at": _now().isoformat()}})


async def _refresh_from_deal(db: Any, cases: list[dict], deal: dict, *, actor: str,
                             summary: dict) -> None:
    """Keep a dormant-deal case's money current with its still-open deal.

    Re-detection only re-reads a deal while it is still dormant, so a deal that woke up
    and was re-priced kept the figure it was first detected with, and a case recorded
    before cases carried the deal's currency kept "USD" on a sterling deal. Only the
    dormant-deal case takes the deal's value: other cases on the deal carry their own
    source's estimate, and the grouping already lets the deal's value stand for them.
    """
    contacts = sorted({c for c in deal.get("contact_ids") or [] if c}
                      | ({deal["contact_id"]} if deal.get("contact_id") else set()))
    for case in cases:
        if case["source"] != recovery_case.SOURCE_DORMANT_DEAL:
            continue
        refreshed = await recovery_case.refresh_from_source(
            db, case, value=deal.get("value") or deal.get("amount"),
            currency=deal.get("currency"), basis="opportunity value on record",
            references={"contact_id": contacts[0]} if len(contacts) == 1 else None,
            actor=actor)
        if refreshed.get("updated_at") != case.get("updated_at"):
            summary["refreshed"] = summary.get("refreshed", 0) + 1


async def reconcile_all_tenants(db: Any, *, actor: str = "cron",
                                audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    tenant_ids = await db.tenants.distinct("tenant_id")
    summaries = []
    for tenant_id in tenant_ids:
        summaries.append({"tenant_id": tenant_id,
                          **await reconcile_tenant(db, tenant_id, actor=actor, audit=audit)})
    return {"tenants": len(tenant_ids), "summaries": summaries}
