"""Deduplicated alert evaluation engine (integration/commitment/health/billing)."""
from app.shared import (db, new_id, now_iso, record_event, STALE_SYNC_HOURS,
                        DLQ_ALERT_THRESHOLD, SYNC_FAIL_THRESHOLD, HEALTH_CRITICAL, _age_hours)
from app.services.notifications import notify_alert

async def _upsert_alert(tenant_id, workspace_id, atype, severity, source, summary, source_ref):
    existing = await db.alerts.find_one({"tenant_id": tenant_id, "type": atype, "source_ref": source_ref,
                                         "status": {"$in": ["open", "acknowledged"]}}, {"_id": 0})
    if existing:
        await db.alerts.update_one({"id": existing["id"]},
            {"$set": {"last_seen_at": now_iso(), "severity": severity, "summary": summary, "workspace_id": workspace_id},
             "$inc": {"occurrence_count": 1}})
        return False
    doc = {"id": new_id("alert"), "tenant_id": tenant_id, "workspace_id": workspace_id,
        "type": atype, "severity": severity, "source": source, "summary": summary, "source_ref": source_ref,
        "first_seen_at": now_iso(), "last_seen_at": now_iso(), "occurrence_count": 1, "status": "open",
        "escalation_level": 0, "last_escalated_at": None,
        "acknowledged_by": None, "acknowledged_at": None, "resolved_at": None, "created_at": now_iso()}
    await db.alerts.insert_one(dict(doc))
    await notify_alert(doc, "critical" if severity == "critical" else "created")
    return True

async def _resolve_alerts(tenant_id, atype, source_ref):
    res = await db.alerts.update_many({"tenant_id": tenant_id, "type": atype, "source_ref": source_ref,
                                       "status": {"$in": ["open", "acknowledged"]}},
                                      {"$set": {"status": "resolved", "resolved_at": now_iso()}})
    if res.modified_count and atype.startswith("integration_"):
        await record_event("integration.recovered", "integration", source_ref.split(":")[-1], tenant_id, "system",
                           payload={"source_ref": source_ref})

async def evaluate_alerts(tenant_id):
    created = 0
    conns = await db.integration_connections.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(50)
    for c in conns:
        ref = f"integration:{c['provider']}"
        if c["status"] in ("degraded", "expired", "revoked", "error"):
            sev = "critical" if c["status"] in ("revoked", "expired", "error") else "warning"
            created += await _upsert_alert(tenant_id, None, f"integration_{c['status']}", sev, "integration",
                                           f"{c['provider']} connection is {c['status']} — reconnect required", ref)
        elif c["status"] == "active":
            age = _age_hours(c.get("last_success_at"))
            if age is not None and age > STALE_SYNC_HOURS:
                created += await _upsert_alert(tenant_id, None, "integration_stale", "warning", "integration",
                                               f"{c['provider']} has not synced in {int(age)}h", ref)
            else:
                await _resolve_alerts(tenant_id, "integration_stale", ref)
            fails = await db.integration_sync_logs.count_documents({"tenant_id": tenant_id, "provider": c["provider"], "status": "failed"})
            if fails >= SYNC_FAIL_THRESHOLD:
                created += await _upsert_alert(tenant_id, None, "sync_failures", "warning", "integration",
                                               f"{c['provider']} sync failed {fails} time(s)", ref)
            for st in ("degraded", "expired", "revoked", "error"):
                await _resolve_alerts(tenant_id, f"integration_{st}", ref)
    dlq = await db.webhook_deliveries.count_documents({"tenant_id": tenant_id, "status": "dead"})
    if dlq >= DLQ_ALERT_THRESHOLD:
        created += await _upsert_alert(tenant_id, None, "webhook_dlq", "critical", "webhook",
                                       f"{dlq} webhook deliveries in the dead-letter queue", "webhook:dlq")
    for cm in await db.commitments.find({"tenant_id": tenant_id, "status": "breached"}, {"_id": 0}).to_list(200):
        created += await _upsert_alert(tenant_id, cm.get("workspace_id"), "commitment_breach", "critical", "commitment",
                                       f"Commitment breached: {cm.get('title')}", f"commitment:{cm['id']}")
    for ws in await db.workspaces.find({"tenant_id": tenant_id, "status": {"$ne": "archived"}}, {"_id": 0}).to_list(500):
        snap = await db.health_snapshots.find_one({"workspace_id": ws["id"]}, {"_id": 0}, sort=[("timestamp", -1)])
        score = (snap or {}).get("score", ws.get("health_score"))
        if score is not None and score < HEALTH_CRITICAL:
            created += await _upsert_alert(tenant_id, ws["id"], "health_critical", "critical", "health",
                                           f"Client health critical ({score}) for {ws.get('name')}", f"workspace:{ws['id']}")
        else:
            await _resolve_alerts(tenant_id, "health_critical", f"workspace:{ws['id']}")
    for b in await db.crm_billing.find({"tenant_id": tenant_id, "type": "invoice"}, {"_id": 0}).to_list(300):
        if (b.get("payment_status") or b.get("status")) in ("past_due", "uncollectible"):
            created += await _upsert_alert(tenant_id, b.get("workspace_id"), "overdue_invoice", "warning", "stripe",
                                           f"Overdue invoice {b.get('external_id')}", f"billing:{b['id']}")
    return {"created": created}
