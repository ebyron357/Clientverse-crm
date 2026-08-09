"""Alert notification dispatch, preferences, escalation and daily digest engine.
Email via the Emergent managed proxy. AI summary is bounded and never blocks."""
import os
import asyncio
import httpx
from datetime import datetime, timezone

from app.shared import db, new_id, now_iso, record_event, HEALTH_CRITICAL, _age_hours

from zoneinfo import ZoneInfo

EMAIL_BASE_URL = "https://integrations.emergentagent.com"
DEFAULT_PREFS = {"channels": {"email": True, "in_app": True}, "critical": True, "commitments": True,
                 "billing": True, "integrations": True, "daily_digest": True, "digest_time": "08:00",
                 "timezone": "UTC", "escalation_minutes": 60, "escalation_max_level": 3}
ALERT_EVENT_MAP = {"health_critical": "client.health_critical", "commitment_breach": "commitment.breached",
                   "integration_degraded": "integration.degraded", "integration_expired": "integration.degraded",
                   "integration_revoked": "integration.degraded", "overdue_invoice": "billing.invoice_overdue"}

def email_configured():
    return bool(os.environ.get("EMERGENT_EMAIL_KEY"))

async def send_email(to, subject, html):
    if not email_configured():
        raise RuntimeError("email_not_configured")
    payload = {"to": [to], "subject": subject, "html": html, "from_name": os.environ.get("EMAIL_FROM_NAME", "ClientVerse")}
    last = None
    for attempt in range(1, 4):
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(f"{EMAIL_BASE_URL}/api/v1/email/send", headers={"X-Email-Key": os.environ["EMERGENT_EMAIL_KEY"]}, json=payload)
            if r.status_code == 429:
                last = "rate_limited"; await asyncio.sleep(min(2 ** attempt, 5)); continue
            if r.status_code in (400, 422):
                raise RuntimeError("invalid_recipient")
            r.raise_for_status()
            return (r.json() or {}).get("id") or "sent"
        except RuntimeError:
            raise
        except httpx.HTTPStatusError as e:
            last = f"provider_error:{e.response.status_code}"
            if attempt == 3:
                raise RuntimeError(last)
            await asyncio.sleep(min(0.5 * attempt, 2))
        except Exception:
            last = "timeout"
            if attempt == 3:
                raise RuntimeError(last)
            await asyncio.sleep(0.5 * attempt)
    raise RuntimeError(last or "unknown")

def _pick(d):
    return {k: v for k, v in (d or {}).items() if k in DEFAULT_PREFS}

async def get_prefs(tenant_id, user_id=None):
    merged = dict(DEFAULT_PREFS)
    merged.update(_pick(await db.notification_prefs.find_one({"tenant_id": tenant_id, "user_id": None}, {"_id": 0})))
    if user_id:
        merged.update(_pick(await db.notification_prefs.find_one({"tenant_id": tenant_id, "user_id": user_id}, {"_id": 0})))
    return merged

def _category(atype):
    if "commitment" in atype: return "commitments"
    if "invoice" in atype or "billing" in atype: return "billing"
    if "integration" in atype or "sync" in atype or "webhook" in atype: return "integrations"
    return "critical"

async def _admin_emails(tenant_id):
    return [m["email"] for m in await db.memberships.find({"tenant_id": tenant_id, "role": "admin", "status": "active"}, {"_id": 0}).to_list(50)]

async def notify_alert(alert, transition):
    """In-app + email on meaningful state transitions. Deduplicated by (alert_id, transition[, level])."""
    tenant = alert["tenant_id"]
    dedupe = f"{alert['id']}:{transition}"
    if transition == "escalated":
        dedupe = f"{alert['id']}:escalated:{alert.get('escalation_level', 0)}"
    if await db.notification_deliveries.find_one({"tenant_id": tenant, "dedupe_key": dedupe}, {"_id": 0}):
        return
    prefs = await get_prefs(tenant)
    cat = _category(alert["type"])
    title = {"created": "New alert", "critical": "Critical alert", "acknowledged": "Alert acknowledged",
             "resolved": "Alert resolved", "escalated": "Alert escalated"}.get(transition, "Alert")
    deep = f"/workspaces/{alert['workspace_id']}" if alert.get("workspace_id") else "/dashboard"
    if prefs["channels"]["in_app"]:
        await db.notifications.insert_one({"id": new_id("ntf"), "tenant_id": tenant, "user_id": None,
            "workspace_id": alert.get("workspace_id"), "type": alert["type"], "severity": alert["severity"],
            "source": alert.get("source"), "title": f"{title}: {alert.get('summary','')}", "body": alert.get("summary", ""),
            "deep_link": deep, "read": False, "alert_id": alert["id"], "transition": transition, "created_at": now_iso()})
    # webhook fan-out (signed/versioned/retryable via record_event)
    await record_event(f"alert.{transition}", "alert", alert["id"], tenant, "system", workspace_id=alert.get("workspace_id"),
                       payload={"type": alert["type"], "severity": alert["severity"], "summary": alert.get("summary")})
    if transition in ("created", "critical") and alert["type"] in ALERT_EVENT_MAP:
        await record_event(ALERT_EVENT_MAP[alert["type"]], "alert", alert["id"], tenant, "system",
                           workspace_id=alert.get("workspace_id"), payload={"summary": alert.get("summary")})
    # email
    want_email = (prefs["channels"]["email"] and prefs.get(cat, True)
                  and transition in ("created", "critical", "escalated") and alert["severity"] in ("warning", "critical"))
    delivery = {"id": new_id("ndl"), "tenant_id": tenant, "alert_id": alert["id"], "channel": "email",
                "recipient": None, "notification_type": transition, "status": "skipped", "attempted_at": now_iso(),
                "delivered_at": None, "failure_reason": None, "provider_message_id": None, "retry_count": 0,
                "dedupe_key": dedupe}
    if want_email:
        if not email_configured():
            delivery.update(status="not_configured", failure_reason="email_not_configured")
            await record_event("notification.failed", "notification", alert["id"], tenant, "system", payload={"reason": "email_not_configured"})
        else:
            recipients = await _admin_emails(tenant)
            ok = 0; err = None
            for rc in recipients:
                try:
                    mid = await send_email(rc, f"[ClientVerse] {title}", f"<p>{alert.get('summary','')}</p><p style='color:#888'>Type: {alert['type']} · Severity: {alert['severity']}</p>")
                    ok += 1; delivery["provider_message_id"] = mid; delivery["recipient"] = rc
                except Exception as e:
                    err = str(e)[:120]
            delivery["retry_count"] = 1
            if ok:
                delivery.update(status=("delivered" if ok == len(recipients) else "partial"), delivered_at=now_iso())
                await record_event("notification.delivered", "notification", alert["id"], tenant, "system", payload={"recipients": ok})
            else:
                delivery.update(status="failed", failure_reason=err or "no_recipients")
                await record_event("notification.failed", "notification", alert["id"], tenant, "system", payload={"reason": err})
    await db.notification_deliveries.insert_one(delivery)

async def run_escalations(tenant_id):
    prefs = await get_prefs(tenant_id)
    delay = int(prefs.get("escalation_minutes", 60)); maxlvl = int(prefs.get("escalation_max_level", 3))
    escalated = 0
    for a in await db.alerts.find({"tenant_id": tenant_id, "status": "open", "severity": "critical"}, {"_id": 0}).to_list(200):
        lvl = a.get("escalation_level", 0)
        if lvl >= maxlvl:
            continue
        anchor = a.get("last_escalated_at") or a.get("first_seen_at")
        age_min = (_age_hours(anchor) or 0) * 60
        if age_min < delay:
            continue
        newlvl = lvl + 1
        await db.alerts.update_one({"id": a["id"]}, {"$set": {"escalation_level": newlvl, "last_escalated_at": now_iso()}})
        await record_event("alert.escalated", "alert", a["id"], tenant_id, "system", workspace_id=a.get("workspace_id"), payload={"level": newlvl, "type": a["type"]})
        await notify_alert({**a, "escalation_level": newlvl}, "escalated")
        escalated += 1
    return escalated

# ---- Digest (deterministic from stored data; AI is optional + bounded) ----

async def build_digest(tenant_id):
    scoped = {"tenant_id": tenant_id}
    workspaces = await db.workspaces.find({**scoped, "status": {"$ne": "archived"}}, {"_id": 0}).to_list(500)
    attention = [{"id": w["id"], "name": w.get("name"), "health": w.get("health_score")} for w in workspaces if (w.get("health_score") or 100) < HEALTH_CRITICAL]
    breached = await db.commitments.find({**scoped, "status": "breached"}, {"_id": 0, "id": 1, "title": 1, "workspace_id": 1}).to_list(200)
    at_risk = await db.commitments.find({**scoped, "status": "at_risk"}, {"_id": 0, "id": 1, "title": 1, "workspace_id": 1}).to_list(200)
    overdue = await db.crm_billing.find({**scoped, "type": "invoice", "payment_status": {"$in": ["past_due", "uncollectible"]}}, {"_id": 0, "id": 1, "external_id": 1}).to_list(200)
    approvals = await db.approvals.find({**scoped, "status": "requested"}, {"_id": 0, "id": 1, "tool": 1}).to_list(200)
    alerts = await db.alerts.find({**scoped, "status": {"$in": ["open", "acknowledged"]}}, {"_id": 0, "id": 1, "type": 1, "severity": 1, "summary": 1}).to_list(200)
    conns = await db.integration_connections.find(scoped, {"_id": 0}).to_list(50)
    integ_fail = [{"provider": c["provider"], "status": c["status"]} for c in conns if c["status"] in ("degraded", "expired", "revoked", "error")]
    meetings = await db.crm_meetings.find(scoped, {"_id": 0, "id": 1, "title": 1, "start": 1}).sort("start", 1).to_list(10)
    goals = await db.outcome_goals.find(scoped, {"_id": 0, "id": 1, "title": 1, "current_value": 1, "target": 1}).to_list(50) if "outcome_goals" in await db.list_collection_names() else []
    return {"generated_at": now_iso(),
            "clients_needing_attention": attention, "health_drops": attention,
            "breached_commitments": breached, "at_risk_commitments": at_risk, "overdue_invoices": overdue,
            "unresolved_approvals": approvals, "critical_alerts": [a for a in alerts if a["severity"] == "critical"],
            "open_alerts": alerts, "integration_failures": integ_fail, "upcoming_meetings": meetings,
            "outcome_progress": goals,
            "counts": {"attention": len(attention), "breached": len(breached), "at_risk": len(at_risk),
                       "overdue": len(overdue), "approvals": len(approvals), "alerts": len(alerts), "integration_failures": len(integ_fail)}}

async def maybe_ai_summary(digest):
    if not os.environ.get("EMERGENT_LLM_KEY"):
        return None
    try:
        async def _call():
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=new_id("digest"),
                           system_message="Summarize this operations digest in under 80 words. Use ONLY the numbers provided; do not invent facts.").with_model("anthropic", "claude-sonnet-4-6")
            return await chat.send_message(UserMessage(text=str(digest["counts"])))
        return await asyncio.wait_for(_call(), timeout=8)
    except Exception:
        return None  # AI never blocks digest delivery

def render_digest_html(digest, ai_summary=None):
    c = digest["counts"]
    rows = "".join(f"<tr><td style='padding:4px 8px;color:#555'>{k.replace('_',' ').title()}</td><td style='padding:4px 8px;font-weight:600'>{v}</td></tr>" for k, v in c.items())
    ai = f"<p style='color:#333'>{ai_summary}</p>" if ai_summary else ""
    return f"<div style='font-family:Arial'><h2>ClientVerse Daily Digest</h2>{ai}<table style='border-collapse:collapse'>{rows}</table><p style='color:#999;font-size:12px'>Generated {digest['generated_at']} — facts sourced from your CRM.</p></div>"

async def deliver_digest(tenant_id, date_str, force=False):
    dedupe = f"{tenant_id}:{date_str}"
    if not force:
        existing = await db.digest_runs.find_one({"dedupe_key": dedupe, "status": "delivered"}, {"_id": 0})
        if existing:
            return {"status": "skipped", "reason": "already_sent"}
    digest = await build_digest(tenant_id)
    ai = await maybe_ai_summary(digest)
    html = render_digest_html(digest, ai)
    await record_event("digest.generated", "digest", dedupe, tenant_id, "system", payload={"counts": digest["counts"], "ai": bool(ai)})
    run = {"id": new_id("digest"), "tenant_id": tenant_id, "date": date_str, "dedupe_key": dedupe,
           "counts": digest["counts"], "ai_used": bool(ai), "created_at": now_iso(), "recipients": [], "error": None}
    if not email_configured():
        run.update(status="not_configured")
        await db.digest_runs.update_one({"dedupe_key": dedupe}, {"$set": run}, upsert=True)
        return {"status": "not_configured", "digest": digest}
    prefs = await get_prefs(tenant_id)
    recipients = await _admin_emails(tenant_id) if prefs.get("daily_digest", True) else []
    ok = 0; err = None
    for rc in recipients:
        try:
            await send_email(rc, "[ClientVerse] Daily client health digest", html); ok += 1
        except Exception as e:
            err = str(e)[:120]
    if ok:
        run.update(status="delivered", recipients=recipients, error=err)
        await record_event("digest.delivered", "digest", dedupe, tenant_id, "system", payload={"recipients": ok})
    else:
        run.update(status="failed", error=err or "no_recipients")
        await record_event("digest.failed", "digest", dedupe, tenant_id, "system", payload={"reason": err})
    await db.digest_runs.update_one({"dedupe_key": dedupe}, {"$set": run}, upsert=True)
    return {"status": run["status"], "digest": digest, "recipients": ok}
