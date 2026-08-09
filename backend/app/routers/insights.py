"""Integration insights: unified timeline, alerts, connection health, signals."""
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from app.shared import (db, new_id, now_iso, record_event, get_current_user,
                        require_role, _age_hours, STALE_SYNC_HOURS)
from app.services.integrations import SAFE_CONN_FIELDS
from app.services.alerts import evaluate_alerts
from app.services.notifications import notify_alert

router = APIRouter(prefix="/api")

def _severity_for(event_type):
    et = event_type or ""
    if any(k in et for k in ("breached", "failed", "revoked", "expired", "denied", "dead")):
        return "critical"
    if any(k in et for k in ("at_risk", "degraded", "rejected", "requested", "overdue")):
        return "warning"
    return "info"

def _source_for(event_type, resource_type):
    for pre, src in (("commitment.", "commitment"), ("task.", "task"), ("deliverable.", "deliverable"),
                     ("approval.", "approval"), ("mcp.", "mcp"), ("webhook.", "webhook"),
                     ("integration.", "integration"), ("outcome.", "outcome"), ("goal.", "outcome"),
                     ("health.", "health"), ("authz.", "governance")):
        if (event_type or "").startswith(pre):
            return src
    return {"commitment": "commitment", "task": "task", "deliverable": "deliverable", "approval": "approval",
            "webhook": "webhook", "integration": "integration"}.get(resource_type, "crm")

def _event_to_timeline(ev):
    et = ev["event_type"]; payload = ev.get("payload") or {}
    return {"id": ev["id"], "tenant_id": ev["tenant_id"], "workspace_id": ev.get("workspace_id"),
            "source": _source_for(et, ev.get("resource_type")), "event_type": et,
            "title": payload.get("title") or et.replace(".", " ").replace("_", " ").title(),
            "summary": payload.get("summary") or payload.get("error") or payload.get("reason") or "",
            "occurred_at": ev.get("timestamp"), "actor": ev.get("actor"), "severity": _severity_for(et),
            "ref": {"type": ev.get("resource_type"), "id": ev.get("resource_id")},
            "external_ref": None, "stale": False, "failure": "fail" in et or "dead" in et}

def _integration_items(comms, meetings, billing, stale_providers):
    out = []
    for c in comms:
        out.append({"id": c["id"], "tenant_id": c["tenant_id"], "workspace_id": c.get("workspace_id"),
                    "source": "gmail", "event_type": "gmail.message", "title": c.get("subject") or "(email)",
                    "summary": c.get("snippet") or "", "occurred_at": c.get("ts"), "actor": c.get("from_email"),
                    "severity": "info", "ref": {"type": "communication", "id": c["id"]},
                    "external_ref": c.get("external_id"), "stale": "gmail" in stale_providers, "failure": False})
    for m in meetings:
        out.append({"id": m["id"], "tenant_id": m["tenant_id"], "workspace_id": m.get("workspace_id"),
                    "source": "calendar", "event_type": "calendar.event", "title": m.get("title") or "(meeting)",
                    "summary": f"{len(m.get('attendees') or [])} attendee(s)", "occurred_at": m.get("start"),
                    "actor": m.get("organizer"), "severity": "info", "ref": {"type": "meeting", "id": m["id"]},
                    "external_ref": m.get("external_id"), "stale": "google_calendar" in stale_providers, "failure": False})
    for b in billing:
        sev = "warning" if (b.get("type") == "invoice" and (b.get("payment_status") or b.get("status")) in ("open", "past_due", "uncollectible")) else "info"
        out.append({"id": b["id"], "tenant_id": b["tenant_id"], "workspace_id": b.get("workspace_id"),
                    "source": "stripe", "event_type": f"stripe.{b.get('type')}", "title": f"{b.get('type','record').title()} {b.get('external_id','')}",
                    "summary": f"{(b.get('currency') or '').upper()} {b.get('amount')}" if b.get("amount") is not None else (b.get("status") or ""),
                    "occurred_at": b.get("ts"), "actor": "stripe", "severity": sev,
                    "ref": {"type": "billing", "id": b["id"]}, "external_ref": b.get("external_id"),
                    "stale": "stripe" in stale_providers, "failure": False})
    return out

@router.get("/workspaces/{ws_id}/timeline")
async def workspace_timeline(ws_id: str, sources: str = Query(None), severity: str = Query(None),
                             q: str = Query(None), date_from: str = Query(None), date_to: str = Query(None),
                             limit: int = Query(25, le=100), offset: int = Query(0), user=Depends(get_current_user)):
    ws = await db.workspaces.find_one({"id": ws_id, "tenant_id": user["tenant_id"]}, {"_id": 0, "id": 1})
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    tid = user["tenant_id"]
    evs = await db.domain_events.find({"tenant_id": tid, "workspace_id": ws_id}, {"_id": 0}).sort("timestamp", -1).limit(500).to_list(500)
    conns = await db.integration_connections.find({"tenant_id": tid}, {"_id": 0}).to_list(50)
    stale_providers = {c["provider"] for c in conns if c["status"] != "active" or (_age_hours(c.get("last_success_at")) or 0) > STALE_SYNC_HOURS}
    comms = await db.crm_communications.find({"tenant_id": tid, "workspace_id": ws_id}, {"_id": 0}).limit(100).to_list(100)
    meetings = await db.crm_meetings.find({"tenant_id": tid, "workspace_id": ws_id}, {"_id": 0}).limit(100).to_list(100)
    billing = await db.crm_billing.find({"tenant_id": tid, "workspace_id": ws_id}, {"_id": 0}).limit(100).to_list(100)
    items = [_event_to_timeline(e) for e in evs] + _integration_items(comms, meetings, billing, stale_providers)
    src_f = set((sources or "").split(",")) if sources else None
    sev_f = set((severity or "").split(",")) if severity else None
    ql = (q or "").lower().strip()
    def keep(it):
        if src_f and it["source"] not in src_f: return False
        if sev_f and it["severity"] not in sev_f: return False
        if date_from and (it["occurred_at"] or "") < date_from: return False
        if date_to and (it["occurred_at"] or "") > date_to: return False
        if ql and ql not in (str(it.get("title", "")) + str(it.get("summary", ""))).lower(): return False
        return True
    items = [i for i in items if keep(i)]
    items.sort(key=lambda x: x.get("occurred_at") or "", reverse=True)
    total = len(items)
    page = items[offset:offset + limit]
    return {"items": page, "total": total, "limit": limit, "offset": offset,
            "sources": sorted({i["source"] for i in items})}

@router.post("/alerts/evaluate")
async def alerts_evaluate(user=Depends(get_current_user)):
    return await evaluate_alerts(user["tenant_id"])

@router.get("/alerts")
async def list_alerts(status: str = Query(None), workspace_id: str = Query(None), user=Depends(get_current_user)):
    qy = {"tenant_id": user["tenant_id"]}
    if status:
        qy["status"] = status
    if workspace_id:
        qy["workspace_id"] = workspace_id
    rows = await db.alerts.find(qy, {"_id": 0}).sort("last_seen_at", -1).to_list(200)
    counts = {s: await db.alerts.count_documents({"tenant_id": user["tenant_id"], "status": s}) for s in ("open", "acknowledged", "resolved")}
    return {"alerts": rows, "counts": counts}

class AlertActionInput(BaseModel):
    note: Optional[str] = None

@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, user=Depends(get_current_user)):
    a = await db.alerts.find_one({"id": alert_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.alerts.update_one({"id": alert_id}, {"$set": {"status": "acknowledged", "acknowledged_by": user["email"], "acknowledged_at": now_iso()}})
    await record_event("alert.acknowledged", "alert", alert_id, user["tenant_id"], user["email"], workspace_id=a.get("workspace_id"), payload={"type": a["type"]})
    await notify_alert({**a, "status": "acknowledged"}, "acknowledged")
    return {"ok": True}

@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, user=Depends(get_current_user)):
    a = await db.alerts.find_one({"id": alert_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.alerts.update_one({"id": alert_id}, {"$set": {"status": "resolved", "resolved_at": now_iso()}})
    await record_event("alert.resolved", "alert", alert_id, user["tenant_id"], user["email"], workspace_id=a.get("workspace_id"), payload={"type": a["type"]})
    await notify_alert({**a, "status": "resolved"}, "resolved")
    return {"ok": True}

@router.get("/integrations/health")
async def integration_health(user=Depends(require_role("admin"))):
    conns = await db.integration_connections.find({"tenant_id": user["tenant_id"]}, SAFE_CONN_FIELDS).to_list(50)
    out = []
    for c in conns:
        age = _age_hours(c.get("last_success_at"))
        fails = await db.integration_sync_logs.count_documents({"tenant_id": user["tenant_id"], "provider": c["provider"], "status": "failed"})
        out.append({**c, "sync_age_hours": round(age, 1) if age is not None else None,
                    "stale": c["status"] == "active" and age is not None and age > STALE_SYNC_HOURS,
                    "reconnect_required": c["status"] in ("expired", "revoked", "error"), "failure_count": fails})
    return {"providers": out}

@router.get("/workspaces/{ws_id}/health-signals")
async def workspace_health_signals(ws_id: str, user=Depends(get_current_user)):
    tid = user["tenant_id"]
    ws = await db.workspaces.find_one({"id": ws_id, "tenant_id": tid}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    signals = []
    breached = await db.commitments.find({"tenant_id": tid, "workspace_id": ws_id, "status": "breached"}, {"_id": 0}).to_list(100)
    for c in breached:
        signals.append({"signal": "Breached commitment", "severity": "critical", "impact": -20, "type": "fact",
                        "detail": c.get("title"), "source_ref": f"commitment:{c['id']}", "freshness": c.get("created_at")})
    open_apr = await db.approvals.find({"tenant_id": tid, "workspace_id": ws_id, "status": "requested"}, {"_id": 0}).to_list(100)
    for a in open_apr:
        signals.append({"signal": "Unresolved approval", "severity": "warning", "impact": -10, "type": "fact",
                        "detail": a.get("summary") or a.get("tool"), "source_ref": f"approval:{a['id']}", "freshness": a.get("created_at")})
    overdue = await db.crm_billing.find({"tenant_id": tid, "workspace_id": ws_id, "type": "invoice",
                                         "payment_status": {"$in": ["past_due", "uncollectible"]}}, {"_id": 0}).to_list(100)
    for b in overdue:
        signals.append({"signal": "Overdue invoice", "severity": "warning", "impact": -10, "type": "fact",
                        "detail": b.get("external_id"), "source_ref": f"billing:{b['id']}", "freshness": b.get("synced_at")})
    conns = await db.integration_connections.find({"tenant_id": tid}, {"_id": 0}).to_list(50)
    gmail = next((c for c in conns if c["provider"] == "gmail"), None)
    if gmail and gmail["status"] == "active":
        latest = await db.crm_communications.find_one({"tenant_id": tid, "workspace_id": ws_id}, {"_id": 0}, sort=[("ts", -1)])
        age = _age_hours(latest.get("ts")) if latest else None
        if age is None or age > 24 * 14:
            signals.append({"signal": "Stale client communication", "severity": "warning", "impact": -5, "type": "inference",
                            "detail": "No recent email in 14+ days" if latest else "No matched client email", "source_ref": "gmail:workspace", "freshness": (latest or {}).get("ts")})
    up = await db.crm_meetings.find({"tenant_id": tid, "workspace_id": ws_id}, {"_id": 0}).sort("start", 1).to_list(5)
    for m in up:
        signals.append({"signal": "Upcoming client meeting", "severity": "info", "impact": 0, "type": "fact",
                        "detail": m.get("title"), "source_ref": f"meeting:{m['id']}", "freshness": m.get("start")})
    crit = await db.alerts.count_documents({"tenant_id": tid, "workspace_id": ws_id, "severity": "critical", "status": {"$in": ["open", "acknowledged"]}})
    if crit:
        signals.append({"signal": "Critical alerts", "severity": "critical", "impact": -15, "type": "fact",
                        "detail": f"{crit} open critical alert(s)", "source_ref": f"alerts:{ws_id}", "freshness": now_iso()})
    return {"workspace_id": ws_id, "signals": signals}
