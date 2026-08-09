"""Webhook management, delivery inspection, replay, sink and match-preview."""
import secrets
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Request, Depends, Query
from pydantic import BaseModel

from app.shared import (db, new_id, now_iso, record_event, get_current_user,
                        require_role, _do_delivery, event_matches)

router = APIRouter(prefix="/api")

class WebhookInput(BaseModel):
    name: str
    url: str
    events: List[str] = []

class WebhookPatch(BaseModel):
    enabled: Optional[bool] = None
    rotate_secret: Optional[bool] = None

@router.get("/webhooks")
async def list_webhooks(user=Depends(get_current_user)):
    return await db.webhooks.find({"tenant_id": user["tenant_id"]}, {"_id": 0, "secret": 0}).sort("created_at", -1).to_list(200)

@router.get("/webhooks/{wid}/secret")
async def reveal_webhook_secret(wid: str, user=Depends(require_role("admin"))):
    wh = await db.webhooks.find_one({"id": wid, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not wh:
        raise HTTPException(status_code=404, detail="Not found")
    await record_event("webhook.secret_revealed", "webhook", wid, user["tenant_id"], user["email"], payload={"name": wh.get("name")})
    return {"id": wid, "secret": wh.get("secret")}

@router.post("/webhooks")
async def create_webhook(inp: WebhookInput, user=Depends(require_role("admin"))):
    doc = {"id": new_id("wh"), "tenant_id": user["tenant_id"], "name": inp.name, "url": inp.url,
           "events": inp.events, "status": "AVAILABLE", "signed": True, "enabled": True,
           "secret": "whsec_" + secrets.token_hex(16), "description": "Custom endpoint.", "created_at": now_iso()}
    await db.webhooks.insert_one(dict(doc))
    await record_event("integration.connected", "webhook", doc["id"], user["tenant_id"], user["email"], payload={"name": inp.name})
    return {k: v for k, v in doc.items() if k != "_id"}

@router.patch("/webhooks/{wid}")
async def patch_webhook(wid: str, inp: WebhookPatch, user=Depends(require_role("admin"))):
    wh = await db.webhooks.find_one({"id": wid, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not wh:
        raise HTTPException(status_code=404, detail="Not found")
    upd = {}
    if inp.enabled is not None:
        upd["enabled"] = inp.enabled
    if inp.rotate_secret:
        upd["secret"] = "whsec_" + secrets.token_hex(16)
    if upd:
        await db.webhooks.update_one({"id": wid}, {"$set": upd})
    return {"ok": True, **{k: v for k, v in upd.items() if k != "secret"}}

@router.post("/webhooks/{wid}/test")
async def test_webhook(wid: str, user=Depends(get_current_user)):
    wh = await db.webhooks.find_one({"id": wid, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not wh:
        raise HTTPException(status_code=404, detail="Not found")
    ev = {"id": new_id("evt"), "event_type": "webhook.test", "tenant_id": user["tenant_id"],
          "actor": user["email"], "timestamp": now_iso(), "payload": {"message": "This is a ClientVerse test event"}}
    delivery = {"id": new_id("whd"), "tenant_id": user["tenant_id"], "webhook_id": wid, "webhook_name": wh.get("name"),
                "event_type": "webhook.test", "event_id": ev["id"], "payload": {"event": ev},
                "status": "pending", "attempts": [], "dlq": False, "created_at": now_iso()}
    await db.webhook_deliveries.insert_one(dict(delivery))
    status = await _do_delivery(delivery, wh)
    return {"status": status, "delivery_id": delivery["id"]}

@router.get("/webhook-deliveries")
async def list_deliveries(limit: int = Query(100), user=Depends(get_current_user)):
    return await db.webhook_deliveries.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("created_at", -1).to_list(limit)

@router.post("/webhook-deliveries/{did}/replay")
async def replay_delivery(did: str, user=Depends(get_current_user)):
    d = await db.webhook_deliveries.find_one({"id": did, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    wh = await db.webhooks.find_one({"id": d["webhook_id"], "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await db.webhook_deliveries.update_one({"id": did}, {"$set": {"attempts": [], "status": "pending", "dlq": False}})
    d["attempts"] = []
    status = await _do_delivery(d, wh)
    return {"status": status}

@router.post("/webhooks/sink")
async def webhook_sink(request: Request):
    _ = await request.body()
    return {"received": True}

class PreviewInput(BaseModel):
    patterns: List[str] = []

@router.post("/webhooks/match-preview")
async def webhook_match_preview(inp: PreviewInput, user=Depends(get_current_user)):
    events = await db.domain_events.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("timestamp", -1).to_list(100)
    matched = [e for e in events if event_matches(e["event_type"], inp.patterns)]
    counts = {}
    for e in matched:
        counts[e["event_type"]] = counts.get(e["event_type"], 0) + 1
    by_type = sorted([{"event_type": k, "count": v} for k, v in counts.items()], key=lambda x: -x["count"])
    return {"scanned": len(events), "matched": len(matched), "by_type": by_type,
            "samples": [{"event_type": e["event_type"], "timestamp": e["timestamp"], "actor": e["actor"]} for e in matched[:8]]}
