"""Notification center, preferences and digest routes."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.shared import (db, new_id, now_iso, record_event, get_current_user, require_role)
from app.services.notifications import (get_prefs, _pick, DEFAULT_PREFS, email_configured,
                                        build_digest, deliver_digest, run_escalations)

router = APIRouter(prefix="/api")

@router.get("/notifications")
async def list_notifications(user=Depends(get_current_user)):
    q = {"tenant_id": user["tenant_id"], "$or": [{"user_id": None}, {"user_id": user["user_id"]}]}
    rows = await db.notifications.find(q, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    unread = await db.notifications.count_documents({**q, "read": False})
    return {"notifications": rows, "unread": unread}

@router.post("/notifications/{nid}/read")
async def mark_notification_read(nid: str, user=Depends(get_current_user)):
    r = await db.notifications.update_one({"id": nid, "tenant_id": user["tenant_id"]}, {"$set": {"read": True}})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}

@router.post("/notifications/read-all")
async def mark_all_read(user=Depends(get_current_user)):
    await db.notifications.update_many({"tenant_id": user["tenant_id"], "$or": [{"user_id": None}, {"user_id": user["user_id"]}], "read": False}, {"$set": {"read": True}})
    return {"ok": True}

@router.get("/notifications/preferences")
async def get_notification_preferences(user=Depends(get_current_user)):
    tenant_default = await db.notification_prefs.find_one({"tenant_id": user["tenant_id"], "user_id": None}, {"_id": 0}) or {}
    mine = await db.notification_prefs.find_one({"tenant_id": user["tenant_id"], "user_id": user["user_id"]}, {"_id": 0}) or {}
    return {"tenant_default": _pick(tenant_default) or DEFAULT_PREFS, "mine": _pick(mine),
            "effective": await get_prefs(user["tenant_id"], user["user_id"]),
            "email_configured": email_configured(), "is_admin": user.get("role") == "admin"}

class PrefsInput(BaseModel):
    prefs: dict

@router.put("/notifications/preferences/me")
async def set_my_preferences(inp: PrefsInput, user=Depends(get_current_user)):
    await db.notification_prefs.update_one({"tenant_id": user["tenant_id"], "user_id": user["user_id"]},
        {"$set": {"tenant_id": user["tenant_id"], "user_id": user["user_id"], **_pick(inp.prefs), "updated_at": now_iso(), "updated_by": user["email"]}}, upsert=True)
    await record_event("notification.pref_changed", "prefs", user["user_id"], user["tenant_id"], user["email"], payload={"scope": "user"})
    return {"ok": True, "effective": await get_prefs(user["tenant_id"], user["user_id"])}

@router.put("/notifications/preferences/tenant")
async def set_tenant_preferences(inp: PrefsInput, user=Depends(require_role("admin"))):
    await db.notification_prefs.update_one({"tenant_id": user["tenant_id"], "user_id": None},
        {"$set": {"tenant_id": user["tenant_id"], "user_id": None, **_pick(inp.prefs), "updated_at": now_iso(), "updated_by": user["email"]}}, upsert=True)
    await record_event("notification.pref_changed", "prefs", user["tenant_id"], user["tenant_id"], user["email"], payload={"scope": "tenant"})
    return {"ok": True, "tenant_default": await get_prefs(user["tenant_id"])}

@router.get("/digest/preview")
async def digest_preview(user=Depends(require_role("admin"))):
    return await build_digest(user["tenant_id"])

@router.post("/digest/run")
async def digest_run(user=Depends(require_role("admin"))):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return await deliver_digest(user["tenant_id"], today, force=True)

@router.post("/alerts/escalate")
async def alerts_escalate(user=Depends(require_role("admin"))):
    return {"escalated": await run_escalations(user["tenant_id"])}
