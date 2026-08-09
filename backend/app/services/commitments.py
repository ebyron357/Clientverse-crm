"""Commitment SLA risk evaluation engine."""
from datetime import datetime, timezone, timedelta

from app.shared import db, record_event

COMMITMENT_AT_RISK_HOURS = 48

async def evaluate_commitment_risk(tenant_id=None, actor="system"):
    """Flag open commitments as at_risk when their due date is near and breached when overdue.
    Emits commitment.at_risk / commitment.breached domain events (audit + webhooks)."""
    q = {"status": {"$in": ["open", "at_risk"]}, "due_date": {"$nin": [None, ""]}}
    if tenant_id:
        q["tenant_id"] = tenant_id
    rows = await db.commitments.find(q, {"_id": 0}).to_list(5000)
    now = datetime.now(timezone.utc)
    at_risk_ids, breached_ids = [], []
    for c in rows:
        due = c.get("due_date")
        try:
            due_dt = datetime.fromisoformat(due)
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if due_dt < now:
            if c.get("status") != "breached":
                await db.commitments.update_one({"id": c["id"]}, {"$set": {"status": "breached"}})
                await record_event("commitment.breached", "commitment", c["id"], c["tenant_id"], actor,
                                   workspace_id=c.get("workspace_id"), payload={"title": c.get("title"), "due_date": due, "auto": True})
                breached_ids.append(c["id"])
        elif due_dt - now <= timedelta(hours=COMMITMENT_AT_RISK_HOURS):
            if c.get("status") == "open":
                await db.commitments.update_one({"id": c["id"]}, {"$set": {"status": "at_risk"}})
                await record_event("commitment.at_risk", "commitment", c["id"], c["tenant_id"], actor,
                                   workspace_id=c.get("workspace_id"), payload={"title": c.get("title"), "due_date": due, "auto": True})
                at_risk_ids.append(c["id"])
    return {"scanned": len(rows), "flagged_at_risk": len(at_risk_ids), "flagged_breached": len(breached_ids),
            "at_risk_ids": at_risk_ids, "breached_ids": breached_ids, "threshold_hours": COMMITMENT_AT_RISK_HOURS}
