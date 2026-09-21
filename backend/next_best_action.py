"""Next Best Action — server-side recommendation service.

The canonical governing document records that Next Best Action was previously
overstated: a client-side strip in one workspace page is not the capability. This
module is the real thing — tenant-scoped recommendation records with deterministic
rules, explicit evidence, priority, lifecycle state and operator feedback.

Deliberate constraints:
  * Rules only. No model scoring, no fabricated confidence value.
  * Every recommendation cites the records it was derived from, so a user can check
    the reasoning rather than trust it.
  * Feedback (accept / dismiss / complete / snooze + outcome) is persisted, which is
    what later makes prioritisation improvable without guessing today.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

COLLECTION = "next_best_actions"

STATE_NEW = "new"
STATE_ACCEPTED = "accepted"
STATE_DISMISSED = "dismissed"
STATE_COMPLETED = "completed"
STATE_SNOOZED = "snoozed"
STATES = (STATE_NEW, STATE_ACCEPTED, STATE_DISMISSED, STATE_COMPLETED, STATE_SNOOZED)
OPEN_STATES = (STATE_NEW, STATE_ACCEPTED, STATE_SNOOZED)

# Lower number = more urgent. Fixed bands keep ordering explainable: a user can be
# told why one item outranks another without reading code.
PRIORITY_CRITICAL = 10
PRIORITY_HIGH = 30
PRIORITY_MEDIUM = 50
PRIORITY_LOW = 70

ACTION_RESOLVE_COMMITMENT = "resolve_commitment"
ACTION_DECIDE_APPROVAL = "decide_approval"
ACTION_ADVANCE_TASK = "advance_task"
ACTION_RECOVER_STALLED_LEAD = "recover_stalled_lead"
ACTION_RECOVER_MISSED_FOLLOWUP = "recover_missed_followup"
ACTION_REPAIR_INTEGRATION = "repair_integration"
ACTION_REVIEW_CLIENT_HEALTH = "review_client_health"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


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


def _recommendation(*, tenant_id: str, action_type: str, title: str, reason: str,
                    priority: int, source_refs: list[str], evidence: dict,
                    workspace_id: Optional[str] = None, dedupe_key: str) -> dict:
    now = _iso(_now())
    return {
        "id": f"nba_{uuid.uuid4().hex[:12]}",
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "action_type": action_type,
        "title": title,
        "reason": reason,
        "priority": priority,
        "source_refs": source_refs,
        "evidence": evidence,
        "dedupe_key": dedupe_key,
        "state": STATE_NEW,
        "snooze_until": None,
        "outcome": None,
        "feedback_note": None,
        "created_at": now,
        "updated_at": now,
        "state_changed_at": now,
        "state_changed_by": None,
        "history": [{"action": "generated", "actor": "system", "at": now}],
    }


async def ensure_indexes(db) -> None:
    await db[COLLECTION].create_index([("tenant_id", 1), ("state", 1), ("priority", 1)])
    await db[COLLECTION].create_index([("tenant_id", 1), ("workspace_id", 1), ("state", 1)])
    await db[COLLECTION].create_index([("tenant_id", 1), ("dedupe_key", 1)], unique=True)


# ------------------------------------------------------------------ rules

async def _from_commitments(db, tenant_id: str) -> list[dict]:
    out = []
    commitments = await db.commitments.find(
        {"tenant_id": tenant_id, "status": {"$in": ["breached", "at_risk", "open"]}}, {"_id": 0}
    ).to_list(200)
    now = _now()
    for cmt in commitments:
        status = str(cmt.get("status") or "").lower()
        due = _parse(cmt.get("due_date") or cmt.get("due_at"))
        overdue = due is not None and due < now
        if status == "breached":
            priority, verb = PRIORITY_CRITICAL, "Resolve breached commitment"
        elif status == "at_risk":
            priority, verb = PRIORITY_HIGH, "Stabilise at-risk commitment"
        elif overdue:
            priority, verb = PRIORITY_HIGH, "Close overdue commitment"
        else:
            continue
        out.append(_recommendation(
            tenant_id=tenant_id,
            action_type=ACTION_RESOLVE_COMMITMENT,
            title=f"{verb}: {cmt.get('title') or 'Untitled commitment'}",
            reason=(f"Commitment status is '{status}'"
                    + (f" and it was due {due.date().isoformat()}" if due else "")
                    + (f"; owner {cmt['owner']}" if cmt.get("owner") else "; no owner assigned")),
            priority=priority,
            source_refs=[f"commitment:{cmt.get('id')}"],
            evidence={"status": status, "due_at": due.isoformat() if due else None,
                      "owner": cmt.get("owner"), "workspace_id": cmt.get("workspace_id")},
            workspace_id=cmt.get("workspace_id"),
            dedupe_key=f"{ACTION_RESOLVE_COMMITMENT}:{cmt.get('id')}",
        ))
    return out


async def _from_approvals(db, tenant_id: str) -> list[dict]:
    out = []
    approvals = await db.approvals.find(
        {"tenant_id": tenant_id, "status": "requested"}, {"_id": 0}
    ).to_list(200)
    for apr in approvals:
        out.append(_recommendation(
            tenant_id=tenant_id,
            action_type=ACTION_DECIDE_APPROVAL,
            title=f"Decide approval: {apr.get('title') or 'Untitled approval'}",
            reason="An approval is requested and is blocking client-visible progress until it is decided.",
            priority=PRIORITY_HIGH,
            source_refs=[f"approval:{apr.get('id')}"],
            evidence={"requested_at": apr.get("created_at"), "workspace_id": apr.get("workspace_id")},
            workspace_id=apr.get("workspace_id"),
            dedupe_key=f"{ACTION_DECIDE_APPROVAL}:{apr.get('id')}",
        ))
    return out


async def _from_tasks(db, tenant_id: str) -> list[dict]:
    out = []
    now = _now()
    tasks = await db.tasks.find(
        {"tenant_id": tenant_id, "status": {"$nin": ["done", "complete", "completed", "cancelled"]}},
        {"_id": 0},
    ).to_list(200)
    for task in tasks:
        due = _parse(task.get("due_date") or task.get("due_at"))
        if due is None or due >= now:
            continue
        overdue_days = max(0, (now - due).days)
        out.append(_recommendation(
            tenant_id=tenant_id,
            action_type=ACTION_ADVANCE_TASK,
            title=f"Advance overdue task: {task.get('title') or 'Untitled task'}",
            reason=(f"Task is {overdue_days} day(s) past its due date and still "
                    f"'{task.get('status') or 'open'}'."),
            priority=PRIORITY_MEDIUM,
            source_refs=[f"task:{task.get('id')}"],
            evidence={"due_at": due.isoformat(), "overdue_days": overdue_days,
                      "assignee": task.get("assignee")},
            workspace_id=task.get("workspace_id"),
            dedupe_key=f"{ACTION_ADVANCE_TASK}:{task.get('id')}",
        ))
    return out


async def _from_work_queue(db, tenant_id: str) -> list[dict]:
    """Second Chance detections become recommendations, keeping one queue of truth."""
    out = []
    items = await db.work_queue.find(
        {"tenant_id": tenant_id, "queue": "second_chance",
         "status": {"$in": ["queued", "claimed", "processing", "retry_scheduled", "completed"]},
         "resolved_at": None},
        {"_id": 0},
    ).to_list(200)
    for item in items:
        payload = item.get("payload") or {}
        if item.get("type") == "second_chance.stalled_lead":
            action_type = ACTION_RECOVER_STALLED_LEAD
            title = f"Re-engage stalled lead: {payload.get('title') or 'Untitled opportunity'}"
            priority = PRIORITY_MEDIUM
        elif item.get("type") == "second_chance.missed_followup":
            action_type = ACTION_RECOVER_MISSED_FOLLOWUP
            title = f"Recover missed follow-up: {payload.get('title') or 'Untitled item'}"
            priority = PRIORITY_HIGH
        else:
            continue
        out.append(_recommendation(
            tenant_id=tenant_id,
            action_type=action_type,
            title=title,
            reason=payload.get("reason") or "Detected by Second Chance recovery rules.",
            priority=priority,
            source_refs=[item.get("source_ref") or f"work_item:{item.get('id')}",
                         f"work_item:{item.get('id')}"],
            evidence=item.get("evidence") or {},
            workspace_id=item.get("workspace_id"),
            dedupe_key=f"{action_type}:{payload.get('record_id') or item.get('id')}",
        ))
    return out


async def _from_integrations(db, tenant_id: str) -> list[dict]:
    out = []
    connections = await db.integration_connections.find(
        {"tenant_id": tenant_id, "status": {"$in": ["degraded", "expired", "revoked", "error"]}},
        {"_id": 0, "provider": 1, "status": 1, "last_sync_at": 1, "id": 1},
    ).to_list(50)
    for conn in connections:
        status = conn.get("status")
        out.append(_recommendation(
            tenant_id=tenant_id,
            action_type=ACTION_REPAIR_INTEGRATION,
            title=f"Repair {conn.get('provider')} connection",
            reason=(f"Connection state is '{status}', so data from this provider is no longer "
                    f"reaching the CRM."),
            priority=PRIORITY_HIGH if status in ("expired", "revoked") else PRIORITY_MEDIUM,
            source_refs=[f"integration:{conn.get('provider')}"],
            evidence={"status": status, "last_sync_at": conn.get("last_sync_at")},
            dedupe_key=f"{ACTION_REPAIR_INTEGRATION}:{conn.get('provider')}",
        ))
    return out


async def _from_client_health(db, tenant_id: str) -> list[dict]:
    """Use the health the application actually computes.

    Workspace documents do not carry a health field: `record_health_snapshot` writes the
    canonical score and band to `health_snapshots`. Reading a non-existent `ws["health"]`
    meant this rule could never fire for a real unhealthy workspace.
    """
    out = []
    workspaces = await db.workspaces.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(200)
    for ws in workspaces:
        snapshot = await db.health_snapshots.find_one(
            {"tenant_id": tenant_id, "workspace_id": ws.get("id")},
            {"_id": 0, "score": 1, "band": 1},
            sort=[("at", -1)],
        ) or {}
        health = ws.get("health") if isinstance(ws.get("health"), dict) else {}
        band = str(snapshot.get("band") or health.get("band") or ws.get("health_band") or "").lower()
        if band in ("", "healthy", "good"):
            continue
        score = snapshot.get("score", health.get("score", ws.get("health_score")))
        out.append(_recommendation(
            tenant_id=tenant_id,
            action_type=ACTION_REVIEW_CLIENT_HEALTH,
            title=f"Review client health: {ws.get('name') or 'Untitled workspace'}",
            reason=(f"Workspace health band is '{band.replace('_', ' ')}'"
                    + (f" with score {score}" if score is not None else "")
                    + "; review the contributing factors before the next client moment."),
            priority=PRIORITY_CRITICAL if band in ("critical", "at_risk") else PRIORITY_LOW,
            source_refs=[f"workspace:{ws.get('id')}"],
            evidence={"band": band, "score": score},
            workspace_id=ws.get("id"),
            dedupe_key=f"{ACTION_REVIEW_CLIENT_HEALTH}:{ws.get('id')}",
        ))
    return out


RULES = (_from_commitments, _from_approvals, _from_tasks, _from_work_queue,
         _from_integrations, _from_client_health)


# ------------------------------------------------------------- generation

async def generate(db, tenant_id: str, *, actor: str = "system") -> dict:
    """Recompute recommendations for a tenant.

    Upsert semantics by `dedupe_key`: an unchanged recommendation keeps its id, state
    and feedback, so a user's dismissal is not undone by the next generation run.
    Open recommendations whose underlying condition has cleared are retired.
    """
    candidates: list[dict] = []
    failed_rules: list[str] = []
    for rule in RULES:
        try:
            candidates.extend(await rule(db, tenant_id))
        except Exception as exc:
            # A single failing rule must not void the whole queue — and, critically,
            # must not let the retirement pass below conclude that the conditions it
            # would have reported have cleared.
            failed_rules.append(f"{rule.__name__}: {str(exc)[:200]}")

    seen: dict[str, dict] = {}
    for candidate in candidates:
        seen.setdefault(candidate["dedupe_key"], candidate)

    created, refreshed = 0, 0
    now = _iso(_now())
    for key, candidate in seen.items():
        # `dedupe_key` is uniquely indexed, so a find-then-insert races a concurrent
        # generation (a user refresh alongside the cron sweep) into a duplicate-key
        # error. An upsert that only sets the explainable fields is atomic and never
        # touches the user's state or feedback.
        result = await db[COLLECTION].update_one(
            {"tenant_id": tenant_id, "dedupe_key": key},
            {"$set": {"title": candidate["title"], "reason": candidate["reason"],
                      "priority": candidate["priority"], "evidence": candidate["evidence"],
                      "source_refs": candidate["source_refs"], "updated_at": now},
             "$setOnInsert": {k: v for k, v in candidate.items()
                              if k not in ("title", "reason", "priority", "evidence",
                                           "source_refs", "updated_at")}},
            upsert=True,
        )
        if getattr(result, "upserted_id", None) is not None:
            created += 1
        else:
            refreshed += 1

    # Retire open recommendations whose source condition no longer holds — but only
    # when every rule actually ran. If a rule failed, its conditions are unknown, not
    # cleared, and retiring them would silently erase real work.
    retired = 0
    if failed_rules:
        return {"tenant_id": tenant_id, "created": created, "refreshed": refreshed,
                "retired": 0, "evaluated": len(seen), "failed_rules": failed_rules,
                "retirement_skipped": True}
    open_docs = await db[COLLECTION].find(
        {"tenant_id": tenant_id, "state": {"$in": list(OPEN_STATES)}}, {"_id": 0}
    ).to_list(1000)
    for doc in open_docs:
        if doc["dedupe_key"] in seen:
            continue
        await db[COLLECTION].update_one(
            {"tenant_id": tenant_id, "id": doc["id"]},
            {"$set": {"state": STATE_COMPLETED, "outcome": "condition_cleared",
                      "state_changed_at": now, "state_changed_by": actor, "updated_at": now},
             "$push": {"history": {"action": "retired", "actor": actor, "at": now,
                                   "detail": {"reason": "source condition no longer present"}}}},
        )
        retired += 1

    return {"tenant_id": tenant_id, "created": created, "refreshed": refreshed,
            "retired": retired, "evaluated": len(seen), "failed_rules": []}


async def generate_all_tenants(db, *, actor: str = "cron") -> dict:
    tenant_ids = await db.tenants.distinct("tenant_id")
    summaries = []
    for tenant_id in tenant_ids:
        try:
            summaries.append(await generate(db, tenant_id, actor=actor))
        except Exception as exc:
            summaries.append({"tenant_id": tenant_id, "error": str(exc)[:300]})
    return {"tenants": len(tenant_ids), "summaries": summaries}


# ------------------------------------------------------------------ query

async def list_recommendations(db, tenant_id: str, *, workspace_id: Optional[str] = None,
                               state: Optional[str] = None, limit: int = 50) -> list[dict]:
    criteria: dict[str, Any] = {"tenant_id": tenant_id}
    if workspace_id:
        criteria["workspace_id"] = workspace_id
    if state == "open":
        criteria["state"] = {"$in": list(OPEN_STATES)}
    elif state:
        criteria["state"] = state
    limit = max(1, min(int(limit), 200))
    docs = await db[COLLECTION].find(criteria, {"_id": 0}).sort(
        [("priority", 1), ("created_at", 1)]
    ).to_list(limit)
    now = _now()
    visible = []
    for doc in docs:
        snooze_until = _parse(doc.get("snooze_until"))
        if doc.get("state") == STATE_SNOOZED and snooze_until and snooze_until > now:
            if state in (None, "open"):
                continue  # hidden until the snooze elapses
        visible.append(doc)
    return visible


async def set_state(db, tenant_id: str, recommendation_id: str, *, state: str, actor: str,
                    outcome: Optional[str] = None, note: Optional[str] = None,
                    snooze_minutes: Optional[int] = None) -> Optional[dict]:
    if state not in STATES:
        raise ValueError(f"Unsupported recommendation state '{state}'")
    now = _iso(_now())
    updates: dict[str, Any] = {"state": state, "state_changed_at": now,
                               "state_changed_by": actor, "updated_at": now}
    if outcome is not None:
        updates["outcome"] = outcome
    if note is not None:
        updates["feedback_note"] = note
    if state == STATE_SNOOZED:
        minutes = max(1, int(snooze_minutes or 1440))
        updates["snooze_until"] = _iso(_now() + timedelta(minutes=minutes))
    else:
        updates["snooze_until"] = None
    return await db[COLLECTION].find_one_and_update(
        {"tenant_id": tenant_id, "id": recommendation_id},
        {"$set": updates,
         "$push": {"history": {"action": state, "actor": actor, "at": now,
                               "detail": {"outcome": outcome, "note": note}}}},
        projection={"_id": 0},
        return_document=True,
    )


async def summary(db, tenant_id: str) -> dict:
    counts = dict.fromkeys(STATES, 0)
    pipeline = [{"$match": {"tenant_id": tenant_id}},
                {"$group": {"_id": "$state", "count": {"$sum": 1}}}]
    async for row in db[COLLECTION].aggregate(pipeline):
        if row["_id"] in counts:
            counts[row["_id"]] = row["count"]
    counts["open"] = sum(counts[s] for s in OPEN_STATES)
    by_priority = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    open_docs = await db[COLLECTION].find(
        {"tenant_id": tenant_id, "state": {"$in": list(OPEN_STATES)}}, {"_id": 0, "priority": 1}
    ).to_list(1000)
    for doc in open_docs:
        priority = doc.get("priority", PRIORITY_LOW)
        if priority <= PRIORITY_CRITICAL:
            by_priority["critical"] += 1
        elif priority <= PRIORITY_HIGH:
            by_priority["high"] += 1
        elif priority <= PRIORITY_MEDIUM:
            by_priority["medium"] += 1
        else:
            by_priority["low"] += 1
    return {"states": counts, "open_by_priority": by_priority}
