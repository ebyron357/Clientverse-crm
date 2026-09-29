"""Second Chance detection — stalled leads and missed follow-ups.

Implements the two recovery lanes the canonical governing document (E-03, E-04)
marks as runnable today, because both read only data the CRM already owns. Each
detection is a deterministic rule with an explainable reason and a reference to the
record it came from; nothing is inferred, scored by a model, or fabricated.

Detections land on the durable work queue so they survive restarts, deduplicate
against an existing open item, and carry acknowledgement/resolution.

Deliberately NOT here: outbound communication. Detection produces internal work
items only — no channel is activated until an approved provider exists (E-08/E-09).
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from contextlib import aclosing
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import crm_core
import recovery_case

QUEUE_NAME = "second_chance"
TYPE_STALLED_LEAD = "second_chance.stalled_lead"
TYPE_MISSED_FOLLOWUP = "second_chance.missed_followup"

# Detector types map onto the normalized source vocabulary, so a dormant deal and a future
# missed call differ only in this value rather than in which pipeline they travel.
SOURCE_FOR_TYPE = {
    TYPE_STALLED_LEAD: recovery_case.SOURCE_DORMANT_DEAL,
    TYPE_MISSED_FOLLOWUP: recovery_case.SOURCE_MISSED_FOLLOWUP,
}

# Thresholds are configuration, not magic numbers, so an operator can tune the
# definition of "stalled" without a code change.
STALLED_LEAD_DAYS = int(os.environ.get("SECOND_CHANCE_STALLED_LEAD_DAYS", "14"))
MISSED_FOLLOWUP_GRACE_HOURS = int(os.environ.get("SECOND_CHANCE_FOLLOWUP_GRACE_HOURS", "24"))
DETECTION_LIMIT = int(os.environ.get("SECOND_CHANCE_DETECTION_LIMIT", "200"))
# How many candidate records one lane reads per tenant per sweep. Detections are capped by
# DETECTION_LIMIT; this caps the reading, so a tenant with a huge history costs a bounded
# amount while its stalest records -- read first -- are still the ones examined.
SCAN_LIMIT = int(os.environ.get("SECOND_CHANCE_SCAN_LIMIT", "5000"))
SCAN_BATCH = 500

# Closed stages are out of scope for the stalled-lead lane (a lost deal is a different,
# later recovery motion). These names are always closed; a tenant's own pipeline adds its
# won and closed stages to them (`crm_core.stage_outcomes`).
CLOSED_STAGES = ("closed_won", "closed_lost", "won", "lost")

RESOLVED_COMMITMENT_STATUSES = ("met", "resolved", "closed", "cancelled", "done", "complete", "completed")
DONE_TASK_STATUSES = ("done", "complete", "completed", "cancelled")


def _any_case(values) -> list[str]:
    """The spellings a status is stored in, for a query that must exclude all of them."""
    return sorted({form for v in values for form in (v, v.upper(), v.capitalize())})


async def closed_stages(db, tenant_id: str) -> set[str]:
    """Every stage at which a deal is no longer live revenue, for this tenant.

    The hard-coded names alone missed a tenant's own won and closed stages ("signed",
    "churned"), so deals the client had already bought or left were chased as stalled.
    """
    _, closed = await crm_core.stage_outcomes(db, tenant_id)
    return {s.lower() for s in closed} | set(CLOSED_STAGES)


async def deal_contact(db, tenant_id: str, opportunity: dict) -> Optional[str]:
    """The contact a deal's outreach should go to, from the contacts the deal names.

    A deal stores `contact_ids`, a list; reading a singular `contact_id` (which only a
    few older records carry) left every dormant-deal case with nobody to write to. The
    first listed contact with an email address wins, preferring one at the deal's own
    company, since that is who can be reached about this deal.
    """
    if opportunity.get("contact_id"):
        return opportunity["contact_id"]
    ids = [c for c in (opportunity.get("contact_ids") or []) if isinstance(c, str)][:100]
    if not ids:
        return None
    rows = await db.contacts.find(
        {"tenant_id": tenant_id, "id": {"$in": ids}, "archived_at": None},
        {"_id": 0, "id": 1, "email": 1, "company_id": 1}).to_list(len(ids))
    by_id = {row["id"]: row for row in rows}
    ordered = [by_id[c] for c in ids if c in by_id]
    company = opportunity.get("company_id")
    for prefer_company in (True, False):
        for row in ordered:
            if row.get("email") and (not prefer_company or row.get("company_id") == company):
                return row["id"]
    return ordered[0]["id"] if ordered else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _days_since(value, reference: datetime) -> Optional[int]:
    parsed = _parse(value)
    if parsed is None:
        return None
    return max(0, (reference - parsed).days)


async def _latest_activity_by_resource(db, tenant_id: str,
                                       resource_ids: list[str]) -> dict[str, datetime]:
    """Most recent event timestamp per record, in one aggregation.

    Querying per opportunity turned a sweep into an N+1 scan, and the existing
    `domain_events` index is (tenant, workspace, timestamp) — not keyed by resource — so
    every one of those queries was unindexed. One grouped pass over the tenant's events
    for the ids we care about replaces all of them.
    """
    if not resource_ids:
        return {}
    pipeline = [
        {"$match": {"tenant_id": tenant_id, "resource_id": {"$in": resource_ids}}},
        {"$group": {"_id": "$resource_id", "latest": {"$max": "$timestamp"}}},
    ]
    latest: dict[str, datetime] = {}
    async for row in db.domain_events.aggregate(pipeline):
        parsed = _parse(row.get("latest"))
        if parsed:
            latest[row["_id"]] = parsed
    return latest


async def ensure_indexes(db) -> None:
    """Index the lookup the detector actually performs."""
    await db.domain_events.create_index([("tenant_id", 1), ("resource_id", 1), ("timestamp", -1)])


def _last_activity(opp: dict, activity: dict[str, datetime]) -> Optional[datetime]:
    candidates = [
        _parse(opp.get("stage_changed_at")),
        _parse(opp.get("updated_at")),
        _parse(opp.get("created_at")),
        activity.get(opp.get("id")),
    ]
    return max([c for c in candidates if c], default=None)


async def _scan(cursor, limit: int):
    """Yield a cursor's documents in batches, reading at most `limit` of them."""
    batch: list[dict] = []
    read = 0
    try:
        async for doc in cursor:
            batch.append(doc)
            read += 1
            if len(batch) >= SCAN_BATCH:
                yield batch
                batch = []
            if read >= limit:
                break
        if batch:
            yield batch
    finally:
        await cursor.close()


def _open_deals_query(tenant_id: str, closed: set[str]) -> dict:
    return {"tenant_id": tenant_id, "archived_at": None,
            "stage": {"$nin": _any_case(closed)}}


async def detect_stalled_leads(db, queue, tenant_id: str, *, actor: str = "second-chance",
                               threshold_days: int = STALLED_LEAD_DAYS) -> list[dict]:
    """An open opportunity with no qualifying progression or activity for N days.

    Qualifying activity is the most recent of: a domain event for the opportunity,
    an explicit stage change, or the record's own update/create timestamp.

    Closed and archived deals are excluded in the query, and deals are read stalest
    first. Cutting the newest 200 deals of any stage and filtering afterwards meant a
    tenant with 200 recent wins never had its one genuinely stalled deal examined.
    """
    now = _now()
    cutoff_days = max(1, int(threshold_days))
    closed = await closed_stages(db, tenant_id)
    detections: list[dict] = []
    cursor = db.opportunities.find(_open_deals_query(tenant_id, closed),
                                   {"_id": 0}).sort("updated_at", 1)
    async with aclosing(_scan(cursor, SCAN_LIMIT)) as batches:
        async for batch in batches:
            activity = await _latest_activity_by_resource(
                db, tenant_id, [o.get("id") for o in batch if o.get("id")])
            for opp in batch:
                stage = str(opp.get("stage") or "").lower()
                if stage in closed:
                    continue
                last_activity = _last_activity(opp, activity)
                if last_activity is None:
                    continue
                idle_days = (now - last_activity).days
                if idle_days < cutoff_days:
                    continue
                detections.append({
                    "tenant_id": tenant_id,
                    "type": TYPE_STALLED_LEAD,
                    "record_id": opp.get("id"),
                    "title": opp.get("title") or opp.get("name") or "Untitled opportunity",
                    "reason": (
                        f"No qualifying activity for {idle_days} days while the opportunity is "
                        f"open at stage '{stage or 'unknown'}' (threshold {cutoff_days} days)."
                    ),
                    "idle_days": idle_days,
                    "stage": stage,
                    "value": opp.get("value") or opp.get("amount"),
                    "currency": opp.get("currency"),
                    "company_id": opp.get("company_id"),
                    "contact_id": await deal_contact(db, tenant_id, opp),
                    "last_activity_at": last_activity.isoformat(),
                })
                if len(detections) >= DETECTION_LIMIT:
                    return detections
    return detections


def _due_of(record: dict) -> Optional[datetime]:
    return _parse(record.get("due_date") or record.get("due_at"))


async def _overdue(collection, tenant_id: str, done: tuple, now: datetime,
                   grace: timedelta):
    """Open records of one collection whose due time has passed, oldest due first.

    The finished statuses are excluded in the query rather than after a capped read, so
    a history of completed work can no longer crowd an overdue item out of the sweep.
    """
    cursor = collection.find(
        {"tenant_id": tenant_id, "archived_at": None, "status": {"$nin": _any_case(done)},
         "$or": [{"due_date": {"$nin": [None, ""]}}, {"due_at": {"$nin": [None, ""]}}]},
        {"_id": 0}).sort([("due_date", 1), ("due_at", 1)])
    async with aclosing(_scan(cursor, SCAN_LIMIT)) as batches:
        async for batch in batches:
            for record in batch:
                if str(record.get("status") or "").lower() in done:
                    continue
                due = _due_of(record)
                if due is None or now < due + grace:
                    continue
                yield record, due


async def _collect_overdue(collection, tenant_id: str, done: tuple, now: datetime,
                           grace: timedelta, build) -> list[dict]:
    found: list[dict] = []
    async with aclosing(_overdue(collection, tenant_id, done, now, grace)) as overdue:
        async for record, due in overdue:
            found.append(build(record, due, str(record.get("status") or "").lower(),
                               max(0, (now - due).days)))
            if len(found) >= DETECTION_LIMIT:
                break
    return found


async def detect_missed_followups(db, queue, tenant_id: str, *,
                                  grace_hours: int = MISSED_FOLLOWUP_GRACE_HOURS) -> list[dict]:
    """A commitment or task that was due and has no qualifying completion."""
    now = _now()
    grace = timedelta(hours=max(0, int(grace_hours)))

    def commitment(cmt: dict, due: datetime, status: str, overdue_days: int) -> dict:
        return {
            "tenant_id": tenant_id,
            "type": TYPE_MISSED_FOLLOWUP,
            "record_kind": "commitment",
            "record_id": cmt.get("id"),
            "title": cmt.get("title") or "Untitled commitment",
            "reason": (
                f"Commitment was due {overdue_days} day(s) ago and is still '{status or 'open'}' "
                f"with no qualifying completion."
            ),
            "overdue_days": overdue_days,
            "owner": cmt.get("owner"),
            "workspace_id": cmt.get("workspace_id"),
            "due_at": due.isoformat(),
        }

    def task(task: dict, due: datetime, status: str, overdue_days: int) -> dict:
        return {
            "tenant_id": tenant_id,
            "type": TYPE_MISSED_FOLLOWUP,
            "record_kind": "task",
            "record_id": task.get("id"),
            "title": task.get("title") or "Untitled task",
            "reason": (
                f"Delivery task was due {overdue_days} day(s) ago and remains "
                f"'{status or 'open'}'."
            ),
            "overdue_days": overdue_days,
            "owner": task.get("assignee"),
            "workspace_id": task.get("workspace_id"),
            "due_at": due.isoformat(),
        }

    return (await _collect_overdue(db.commitments, tenant_id, RESOLVED_COMMITMENT_STATUSES,
                                   now, grace, commitment)
            + await _collect_overdue(db.tasks, tenant_id, DONE_TASK_STATUSES, now, grace,
                                     task))


async def condition_holds(db, tenant_id: str, record_kind: str, record_id: Optional[str], *,
                          threshold_days: int = STALLED_LEAD_DAYS,
                          grace_hours: int = MISSED_FOLLOWUP_GRACE_HOURS) -> bool:
    """Is the record a detection was raised for still in the condition that raised it?

    Read live, so a detection is withdrawn once its cause has gone -- the deal was won,
    archived or moved; the task was done -- rather than planned from a stale snapshot.
    """
    if not record_id:
        return False
    now = _now()
    if record_kind == "opportunity":
        opp = await db.opportunities.find_one({"tenant_id": tenant_id, "id": record_id},
                                              {"_id": 0})
        if not opp or opp.get("archived_at"):
            return False
        if str(opp.get("stage") or "").lower() in await closed_stages(db, tenant_id):
            return False
        activity = await _latest_activity_by_resource(db, tenant_id, [record_id])
        last = _last_activity(opp, activity)
        return last is not None and (now - last).days >= max(1, int(threshold_days))
    collection, done = {
        "commitment": (db.commitments, RESOLVED_COMMITMENT_STATUSES),
        "task": (db.tasks, DONE_TASK_STATUSES),
    }.get(record_kind, (None, ()))
    if collection is None:
        # Not a record this module detects; nothing here can say it has cleared.
        return True
    record = await collection.find_one({"tenant_id": tenant_id, "id": record_id}, {"_id": 0})
    if not record or record.get("archived_at"):
        return False
    if str(record.get("status") or "").lower() in done:
        return False
    due = _due_of(record)
    return due is not None and now >= due + timedelta(hours=max(0, int(grace_hours)))


def _currency_code(value) -> str:
    code = str(value or "").strip().upper()
    return code if len(code) == 3 and code.isalpha() else recovery_case.DEFAULT_CURRENCY


def to_recovery_event(detection: dict) -> dict:
    """Express a detection in the normalized recovery-event contract.

    The detector's own reason, value and references carry across unchanged; what this adds
    is the shape every other source will arrive in. `source_event_id` is the record that
    went quiet, so re-detecting the same record resolves to the same case.
    """
    kind = detection.get("record_kind") or "opportunity"
    return recovery_case.normalize_event(
        tenant_id=detection["tenant_id"],
        source=SOURCE_FOR_TYPE[detection["type"]],
        source_event_id=f"{kind}:{detection['record_id']}",
        reason=detection["reason"],
        title=detection.get("title"),
        occurred_at=detection.get("last_activity_at") or detection.get("due_at"),
        workspace_id=detection.get("workspace_id"),
        company_id=detection.get("company_id"),
        contact_id=detection.get("contact_id"),
        opportunity_id=detection["record_id"] if kind == "opportunity" else None,
        # The opportunity's own value is what *might* be recovered. It is recorded as
        # potential, with its provenance, and is never confirmed revenue.
        potential_value=detection.get("value"),
        # The deal's own currency, so a 40,000 EUR deal is not recorded as 40,000 USD.
        currency=_currency_code(detection.get("currency")),
        evidence={k: v for k, v in detection.items() if k not in ("tenant_id", "type")},
    )


async def enqueue_detections(queue, detections: list[dict], *, actor: str = "second-chance",
                             db=None,
                             audit: Optional[Callable[..., Awaitable[Any]]] = None) -> list[dict]:
    """Place detections on the durable queue, deduplicated per source record.

    When `db` is supplied each detection also opens its Recovery Case and the two are
    cross-referenced. `db` stays optional so an existing caller that only wants queue
    items keeps working unchanged.
    """
    items: list[dict] = []
    for detection in detections:
        kind = detection.get("record_kind") or "opportunity"
        dedupe_key = f"{detection['type']}:{kind}:{detection['record_id']}"

        case = None
        if db is not None:
            case = await recovery_case.open_case(
                db, to_recovery_event(detection), actor=actor, audit=audit)

        item = await queue.enqueue(
            tenant_id=detection["tenant_id"],
            queue=QUEUE_NAME,
            item_type=detection["type"],
            payload={
                "record_id": detection["record_id"],
                "record_kind": kind,
                "title": detection["title"],
                "reason": detection["reason"],
                "recovery_case_id": (case or {}).get("id"),
            },
            dedupe_key=dedupe_key,
            source_ref=f"{kind}:{detection['record_id']}",
            evidence={k: v for k, v in detection.items() if k not in ("tenant_id", "type")},
            workspace_id=detection.get("workspace_id"),
            priority=50 if detection["type"] == TYPE_MISSED_FOLLOWUP else 70,
            actor=actor,
        )
        if case and db is not None:
            # Point the case at whichever work item is live now. Checking only that the
            # field was empty left a case pointing at a resolved item: `resolve()` clears
            # `active_dedupe_key`, so the next detection of the same record creates a new
            # item, and the case would keep the old one forever.
            if case.get("work_item_reference") != item["id"]:
                await recovery_case.attach(db, tenant_id=detection["tenant_id"],
                                           case_id=case["id"], actor=actor,
                                           work_item_reference=item["id"])
            # A folded item was created before this call shape existed, or by a caller
            # that passed no `db`, so its stored payload carries no case id. Merging it
            # only into the local copy left the link one-directional and invisible to
            # anything reading the queue.
            if item.get("payload", {}).get("recovery_case_id") != case["id"]:
                persisted = await queue.set_payload_fields(
                    item["id"], tenant_id=detection["tenant_id"],
                    fields={"recovery_case_id": case["id"]})
                if persisted:
                    item = {**persisted, "deduplicated": item.get("deduplicated", False)}
        if case:
            item = {**item, "recovery_case_id": case["id"]}
        items.append(item)
    return items


async def run_detection(db, queue, tenant_id: str, *, actor: str = "second-chance",
                        audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    """Run both lanes for one tenant and return an explainable summary."""
    # Imported here: the planner imports this module, and withdrawing a detection means
    # withdrawing the plan composed for it.
    import recovery_strategy

    withdrawn = await recovery_strategy.withdraw_cleared(db, queue, tenant_id, actor=actor)
    stalled = await detect_stalled_leads(db, queue, tenant_id, actor=actor)
    missed = await detect_missed_followups(db, queue, tenant_id)
    items = await enqueue_detections(queue, stalled + missed, actor=actor, db=db, audit=audit)
    created = [i for i in items if not i.get("deduplicated")]
    return {
        "tenant_id": tenant_id,
        "stalled_leads_detected": len(stalled),
        "missed_followups_detected": len(missed),
        "detections_withdrawn": withdrawn,
        "work_items_created": len(created),
        "work_items_deduplicated": len(items) - len(created),
        "recovery_cases_linked": len([i for i in items if i.get("recovery_case_id")]),
        "thresholds": {
            "stalled_lead_days": STALLED_LEAD_DAYS,
            "missed_followup_grace_hours": MISSED_FOLLOWUP_GRACE_HOURS,
        },
    }


async def run_detection_all_tenants(db, queue, *, actor: str = "cron",
                                    audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    tenant_ids = await db.tenants.distinct("tenant_id")
    summaries = []
    for tenant_id in tenant_ids:
        try:
            summaries.append(await run_detection(db, queue, tenant_id, actor=actor, audit=audit))
        except Exception as exc:  # one tenant must never block the sweep
            summaries.append({"tenant_id": tenant_id, "error": str(exc)[:300]})
    return {"tenants": len(tenant_ids), "summaries": summaries}
