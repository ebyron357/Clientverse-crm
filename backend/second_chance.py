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
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

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

# Opportunity stages that represent live revenue. Closed stages are out of scope for
# the stalled-lead lane (a lost deal is a different, later recovery motion).
OPEN_OPPORTUNITY_STAGES = ("new", "qualified", "discovery", "proposal", "negotiation")
CLOSED_STAGES = ("closed_won", "closed_lost", "won", "lost")

RESOLVED_COMMITMENT_STATUSES = ("met", "resolved", "closed", "cancelled", "done", "complete", "completed")
DONE_TASK_STATUSES = ("done", "complete", "completed", "cancelled")


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


async def detect_stalled_leads(db, queue, tenant_id: str, *, actor: str = "second-chance",
                               threshold_days: int = STALLED_LEAD_DAYS) -> list[dict]:
    """An open opportunity with no qualifying progression or activity for N days.

    Qualifying activity is the most recent of: a domain event for the opportunity,
    an explicit stage change, or the record's own update/create timestamp.
    """
    now = _now()
    cutoff_days = max(1, int(threshold_days))
    detections: list[dict] = []
    opportunities = await db.opportunities.find(
        {"tenant_id": tenant_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(DETECTION_LIMIT)
    activity = await _latest_activity_by_resource(
        db, tenant_id, [o.get("id") for o in opportunities if o.get("id")])

    for opp in opportunities:
        stage = str(opp.get("stage") or "").lower()
        if stage in CLOSED_STAGES:
            continue
        if OPEN_OPPORTUNITY_STAGES and stage and stage not in OPEN_OPPORTUNITY_STAGES:
            # Unknown stage names are still treated as open revenue rather than skipped,
            # but the reason records which stage triggered the detection.
            pass

        candidates = [
            _parse(opp.get("stage_changed_at")),
            _parse(opp.get("updated_at")),
            _parse(opp.get("created_at")),
            activity.get(opp.get("id")),
        ]
        last_activity = max([c for c in candidates if c], default=None)
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
            "company_id": opp.get("company_id"),
            "contact_id": opp.get("contact_id"),
            "last_activity_at": last_activity.isoformat(),
        })
    return detections


async def detect_missed_followups(db, queue, tenant_id: str, *,
                                  grace_hours: int = MISSED_FOLLOWUP_GRACE_HOURS) -> list[dict]:
    """A commitment or task that was due and has no qualifying completion."""
    now = _now()
    grace = timedelta(hours=max(0, int(grace_hours)))
    detections: list[dict] = []

    commitments = await db.commitments.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(DETECTION_LIMIT)
    for cmt in commitments:
        status = str(cmt.get("status") or "").lower()
        if status in RESOLVED_COMMITMENT_STATUSES:
            continue
        due = _parse(cmt.get("due_date") or cmt.get("due_at"))
        if due is None or now < due + grace:
            continue
        overdue_days = max(0, (now - due).days)
        detections.append({
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
        })

    tasks = await db.tasks.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(DETECTION_LIMIT)
    for task in tasks:
        status = str(task.get("status") or "").lower()
        if status in DONE_TASK_STATUSES:
            continue
        due = _parse(task.get("due_date") or task.get("due_at"))
        if due is None or now < due + grace:
            continue
        overdue_days = max(0, (now - due).days)
        detections.append({
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
        })
    return detections


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
    stalled = await detect_stalled_leads(db, queue, tenant_id, actor=actor)
    missed = await detect_missed_followups(db, queue, tenant_id)
    items = await enqueue_detections(queue, stalled + missed, actor=actor, db=db, audit=audit)
    created = [i for i in items if not i.get("deduplicated")]
    return {
        "tenant_id": tenant_id,
        "stalled_leads_detected": len(stalled),
        "missed_followups_detected": len(missed),
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
