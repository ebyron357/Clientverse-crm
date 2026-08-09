"""Platform cron endpoints (ack 2xx immediately, background the work)."""
import os
import asyncio
import hmac
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request

from app.shared import db, new_id, now_iso
from app.services.commitments import evaluate_commitment_risk
from app.services.integrations import run_sync
from app.services.alerts import evaluate_alerts
from app.services.notifications import get_prefs, run_escalations, deliver_digest

router = APIRouter(prefix="/api")

@router.post("/cron/commitment-risk")
async def cron_commitment_risk(request: Request):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if not secret or not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    run_id = request.headers.get("X-Webhook-Id") or new_id("cron")
    if await db.cron_runs.find_one({"run_id": run_id}):
        return {"accepted": True, "duplicate": True}
    await db.cron_runs.insert_one({"run_id": run_id, "job": "commitment-risk", "at": now_iso()})
    asyncio.create_task(evaluate_commitment_risk(tenant_id=None, actor="cron"))
    return {"accepted": True, "run_id": run_id}

@router.post("/cron/integration-sync")
async def cron_integration_sync(request: Request):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if not secret or not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    run_id = request.headers.get("X-Webhook-Id") or new_id("cron")
    if await db.cron_runs.find_one({"run_id": run_id}):
        return {"accepted": True, "duplicate": True}
    await db.cron_runs.insert_one({"run_id": run_id, "job": "integration-sync", "at": now_iso()})

    async def _sweep():
        actives = await db.integration_connections.find({"status": {"$in": ["active", "degraded"]}}, {"_id": 0}).to_list(500)
        for c in actives[:200]:
            try:
                await run_sync(c["tenant_id"], c["provider"], "cron")
                await evaluate_alerts(c["tenant_id"])
            except Exception:
                pass
    asyncio.create_task(_sweep())
    return {"accepted": True, "run_id": run_id}

@router.post("/cron/daily-digest")
async def cron_daily_digest(request: Request):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if not secret or not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    run_id = request.headers.get("X-Webhook-Id") or new_id("cron")
    if await db.cron_runs.find_one({"run_id": run_id}):
        return {"accepted": True, "duplicate": True}
    await db.cron_runs.insert_one({"run_id": run_id, "job": "daily-digest", "at": now_iso()})

    async def _sweep():
        for t in await db.tenants.find({}, {"_id": 0, "tenant_id": 1}).to_list(500):
            tid = t["tenant_id"]
            try:
                prefs = await get_prefs(tid)
                if not prefs.get("daily_digest", True):
                    continue
                tz = ZoneInfo(prefs.get("timezone", "UTC"))
                local = datetime.now(tz)
                hour = int(str(prefs.get("digest_time", "08:00")).split(":")[0])
                if local.hour == hour:
                    await run_escalations(tid)
                    await deliver_digest(tid, local.strftime("%Y-%m-%d"))
            except Exception:
                pass
    asyncio.create_task(_sweep())
    return {"accepted": True, "run_id": run_id}
