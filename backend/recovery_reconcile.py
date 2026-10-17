"""Reconciliation — re-reading every open case's source, and closing what has resolved.

Detection only ever opened cases. Nothing re-read a case's source afterwards, so a web
enquiry that was answered the next morning, a missed call that was returned, a deal that
closed -- each stayed an open case for ever, and "open potential" only grew. This module
is the other half of detection: on every sweep it re-reads the record behind each open
case and asks whether the situation the case exists for is still true.

THE RULES

Deal first, for any case that knows its deal (`opportunity_id`), whatever its source:

* archived -> closed `deal_archived`; lost (by the tenant's own pipeline) -> `deal_lost`;
* **won** -> the win is recorded once, through the attribution ledger, against the one
  case best placed to claim it -- a case whose outreach actually reached the client if
  there is one, otherwise the earliest. The ledger decides attributed or unattributed
  from the messages, refuses to book the same sale twice, and closes or recovers the
  case. Every other open case on the same deal is closed `sale_recorded_on_another_case`.
  A deal already won before a case was opened is not a recovery: `deal_won_before_case`.

Then the source record, read the way its detector reads it:

* web enquiry: a test lead or spam is closed outright (it never counted); responded,
  closed, a recorded first response, or an activity/task logged against it is resolved;
* missed call: an answered call from, or any call to, the same number afterwards
  (compared on digits) is resolved;
* estimate: invoiced and paid -> an `invoice_paid` outcome through the ledger; approved
  or invoiced -> resolved; declined, expired, cancelled -> closed outright;
* unanswered conversation: the client replied, or the conversation was closed;
* appointments: rebooked, attended, or no longer cancelled;
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

# Offer statuses that close a case outright, and those that only resolve it (the client
# said yes; an engaged case keeps waiting for the money).
NEGATIVE_OFFER_STATUSES = ("rejected", "declined", "lost", "cancelled", "expired", "withdrawn")
POSITIVE_OFFER_STATUSES = ("approved", "accepted", "won", "invoiced")


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
        if raised or record.get("invoice_id"):
            verdicts[case["id"]] = _verdict(
                "source_resolved", f"The {label} was converted into an invoice.", hard=False)
        elif status in NEGATIVE_OFFER_STATUSES:
            verdicts[case["id"]] = _verdict(
                "source_resolved", f"The {label} was {status}.", hard=True)
        elif status in POSITIVE_OFFER_STATUSES:
            verdicts[case["id"]] = _verdict(
                "source_resolved", f"The {label} was {status}.", hard=False)
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
        elif status in detectors.COMPLETED_APPOINTMENT_STATUSES:
            verdicts[case["id"]] = _verdict("source_resolved", "The appointment was attended.",
                                            hard=False)
        elif status not in detectors.PENDING_APPOINTMENT_STATUSES:
            verdicts[case["id"]] = _verdict(
                "source_resolved", f"The appointment is now '{status}'.", hard=False)
    return verdicts


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


async def _reconcile(db: Any, tenant_id: str, *, sources: Optional[tuple], actor: str,
                     audit: Optional[Callable[..., Awaitable[Any]]], limit: int,
                     summary: dict) -> None:
    query: dict[str, Any] = {"tenant_id": tenant_id,
                             "state": {"$in": list(recovery_case.OPEN_STATES)}}
    if sources:
        query["source"] = {"$in": list(sources)}
    # Least recently reconciled first, so a tenant with more open cases than one sweep
    # reads still has every case re-checked in rotation rather than the same few.
    cases = await db[recovery_case.COLLECTION].find(query, {"_id": 0}).sort(
        "reconciled_at", 1).to_list(int(limit) + 1)
    summary["truncated"] = len(cases) > limit
    cases = cases[:limit]
    summary["examined"] = len(cases)
    if not cases:
        return

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
            summary["errors"].append(f"{case['id']}: {str(exc)[:200]}")
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

    # 1. Engagement: a drafted message that has since been sent makes its case engaged.
    contact = await recovery_lifecycle.last_contact_by_case(db, tenant_id, list(open_ids))
    for case in cases:
        if case["state"] == recovery_case.EXECUTING and case["id"] in contact:
            if await recovery_lifecycle.sync_engagement(db, tenant_id=tenant_id,
                                                        case_id=case["id"], actor=actor,
                                                        audit=audit):
                case["state"] = recovery_case.ENGAGED
                summary["engaged"] += 1

    # 2. The deal, for every case that knows it.
    classes = await crm_core.stage_classes(db, tenant_id)
    by_deal: dict[str, list[dict]] = {}
    for case in cases:
        if case.get("opportunity_id"):
            by_deal.setdefault(case["opportunity_id"], []).append(case)
    deals = await _by_id(db, "opportunities", tenant_id, list(by_deal))
    for deal_id, members in by_deal.items():
        deal = deals.get(deal_id)
        if deal is None:
            for case in members:
                if case["source"] == recovery_case.SOURCE_DORMANT_DEAL:
                    await close(case, "source_missing", {"opportunity_id": deal_id})
            continue
        if deal.get("archived_at"):
            for case in members:
                await close(case, "deal_archived", {"opportunity_id": deal_id})
            continue
        outcome = crm_core.classify_stage(deal.get("stage"), classes)
        if outcome == crm_core.STAGE_LOST:
            for case in members:
                await close(case, "deal_lost", {"opportunity_id": deal_id,
                                                "stage": deal.get("stage")})
        elif outcome == crm_core.STAGE_WON:
            won_at = detectors.parse_time(attribution.deal_won_at(deal, classes)
                                      or deal.get("updated_at"))
            eligible = []
            for case in members:
                opened = detectors.parse_time(case.get("created_at"))
                if won_at and opened and won_at < opened:
                    await close(case, "deal_won_before_case",
                                {"opportunity_id": deal_id, "won_at": won_at.isoformat()})
                else:
                    eligible.append(case)
            if eligible:
                # The case whose outreach reached the client claims the win if there is
                # one; otherwise the earliest. Either way the sale is booked once.
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
                found, settled = await _offer_verdicts(db, tenant_id, members,
                                                       collection="estimates", label="estimate")
                verdicts.update(found)
                paid.extend(settled)
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


async def reconcile_all_tenants(db: Any, *, actor: str = "cron",
                                audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    tenant_ids = await db.tenants.distinct("tenant_id")
    summaries = []
    for tenant_id in tenant_ids:
        summaries.append({"tenant_id": tenant_id,
                          **await reconcile_tenant(db, tenant_id, actor=actor, audit=audit)})
    return {"tenants": len(tenant_ids), "summaries": summaries}
