"""Shared infrastructure layer: config, db, helpers, auth/authz, domain event
emission, webhook fan-out, health computation. No dependency on domain services
(record_event's calls to webhook/health helpers all live in THIS module), so this
is the acyclic base every other module imports from."""
import os
import uuid
import jwt
import bcrypt
import logging
import requests
import asyncio
import hmac
import hashlib
import json as _json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

from dotenv import load_dotenv
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import HTTPException, Request, Response, Depends
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("clientverse")

mongo_url = os.environ['MONGO_URL']
mclient = AsyncIOMotorClient(mongo_url)
db = mclient[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALG = "HS256"
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def new_id(prefix="id"):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False

def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email, "type": "access",
               "exp": datetime.now(timezone.utc) + timedelta(days=7)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def set_auth_cookie(response: Response, token: str):
    response.set_cookie("access_token", token, httponly=True, secure=True,
                        samesite="none", max_age=604800, path="/")

async def record_event(event_type: str, resource_type: str, resource_id: str,
                       tenant_id: str, actor: str, workspace_id: Optional[str] = None,
                       payload: Optional[dict] = None, source: str = "system",
                       privacy: str = "internal"):
    ev = {
        "id": new_id("evt"), "event_type": event_type, "event_version": "v1",
        "tenant_id": tenant_id, "workspace_id": workspace_id, "actor": actor,
        "source": source, "resource_type": resource_type, "resource_id": resource_id,
        "timestamp": now_iso(), "correlation_id": new_id("cor"),
        "causation_id": None, "payload": payload or {}, "privacy": privacy,
    }
    await db.domain_events.insert_one(ev)
    clean = {k: v for k, v in ev.items() if k != "_id"}
    try:
        asyncio.create_task(dispatch_webhooks_for_event(clean))
    except Exception:
        pass
    if workspace_id and event_type in HEALTH_AFFECTING:
        try:
            await record_health_snapshot(tenant_id, workspace_id)
        except Exception:
            pass
    return clean

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        h = request.headers.get("Authorization", "")
        if h.startswith("Bearer "):
            token = h[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # JWT path
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        user = await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user.pop("password_hash", None)
        return await resolve_membership(user)
    except jwt.InvalidTokenError:
        pass
    # Google session_token path
    sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=401, detail="Invalid session")
    exp = sess["expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")
    user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    user.pop("password_hash", None)
    return await resolve_membership(user)

# ----------------------------- Authorization layer -----------------------------

ROLE_PERMISSIONS = {
    "admin": {
        "team:manage", "team:invite", "member:role", "member:disable",
        "mcp:approve", "mcp:kill", "mcp:undo", "workspace:undo_window",
        "webhook:reveal_secret", "webhook:rotate_secret", "webhook:manage",
        "integration:admin", "governance:config",
    },
    "member": set(),
}

def has_permission(role, perm):
    return perm in ROLE_PERMISSIONS.get(role, set())

async def resolve_membership(user):
    """Attach effective role from the tenant membership; block disabled members. Self-heals legacy users."""
    m = await db.memberships.find_one({"tenant_id": user.get("tenant_id"), "user_id": user.get("user_id")}, {"_id": 0})
    if m is None:
        m = {"id": new_id("mem"), "tenant_id": user.get("tenant_id"), "user_id": user.get("user_id"),
             "email": user.get("email"), "role": user.get("role", "member"), "status": "active",
             "invited_by": None, "invited_at": None, "accepted_at": now_iso(), "disabled_at": None, "created_at": now_iso()}
        await db.memberships.insert_one(dict(m))
    if m.get("status") == "disabled":
        raise HTTPException(status_code=403, detail="Your access to this workspace has been disabled")
    user["role"] = m.get("role", user.get("role", "member"))
    user["membership_status"] = m.get("status", "active")
    return user

def require_role(*roles):
    async def _dep(request: Request, user=Depends(get_current_user)):
        if user.get("role") not in roles:
            try:
                await record_event("authz.denied", "authz", request.url.path, user["tenant_id"], user["email"],
                                   payload={"required_roles": list(roles), "role": user.get("role"), "path": request.url.path})
            except Exception:
                pass
            raise HTTPException(status_code=403, detail="You do not have permission to perform this action")
        return user
    return _dep

def require_permission(perm):
    async def _dep(request: Request, user=Depends(get_current_user)):
        if not has_permission(user.get("role"), perm):
            try:
                await record_event("authz.denied", "authz", request.url.path, user["tenant_id"], user["email"],
                                   payload={"required_permission": perm, "role": user.get("role")})
            except Exception:
                pass
            raise HTTPException(status_code=403, detail="You do not have permission to perform this action")
        return user
    return _dep

def scope(user):
    return {"tenant_id": user["tenant_id"]}

async def gen_list(coll, user, extra=None, sort_field="created_at"):
    q = scope(user)
    if extra:
        q.update(extra)
    docs = await db[coll].find(q, {"_id": 0}).sort(sort_field, -1).to_list(2000)
    return docs

STAGES = ["lead", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]

def compute_health(commitments, tasks, deliverables, requests_):
    factors = []
    score = 100
    at_risk = [c for c in commitments if c.get("status") == "at_risk"]
    breached = [c for c in commitments if c.get("status") == "breached"]
    if breached:
        pen = min(40, len(breached) * 20); score -= pen
        factors.append({"factor": "Breached commitments", "impact": -pen, "detail": f"{len(breached)} commitment(s) breached", "type": "fact"})
    if at_risk:
        pen = min(20, len(at_risk) * 10); score -= pen
        factors.append({"factor": "At-risk commitments", "impact": -pen, "detail": f"{len(at_risk)} commitment(s) at risk", "type": "fact"})
    open_reqs = [r for r in requests_ if r.get("status") == "open"]
    if open_reqs:
        pen = min(15, len(open_reqs) * 5); score -= pen
        factors.append({"factor": "Open client requests", "impact": -pen, "detail": f"{len(open_reqs)} request(s) awaiting response", "type": "fact"})
    overdue = [t for t in tasks if t.get("status") != "done" and t.get("due_date") and t["due_date"] < now_iso()]
    if overdue:
        pen = min(20, len(overdue) * 7); score -= pen
        factors.append({"factor": "Overdue tasks", "impact": -pen, "detail": f"{len(overdue)} task(s) overdue", "type": "fact"})
    approved_deliv = [d for d in deliverables if d.get("status") == "approved"]
    if approved_deliv:
        boost = min(10, len(approved_deliv) * 3); score = min(100, score + boost)
        factors.append({"factor": "Approved deliverables", "impact": boost, "detail": f"{len(approved_deliv)} deliverable(s) approved", "type": "fact"})
    score = max(0, min(100, score))
    band = "healthy" if score >= 75 else ("at_risk" if score >= 50 else "critical")
    return {"score": score, "band": band, "factors": factors}

WEBHOOK_MAX_ATTEMPTS = 3
HEALTH_AFFECTING = {"commitment.created", "commitment.at_risk", "commitment.breached", "commitment.fulfilled",
                    "task.created", "task.completed", "deliverable.created", "deliverable.approved",
                    "client_request.created"}

def sign_payload(secret: str, body: bytes) -> str:
    return hmac.new((secret or "").encode(), body, hashlib.sha256).hexdigest()

async def _do_delivery(delivery: dict, webhook: dict) -> str:
    body = _json.dumps(delivery["payload"], default=str).encode()
    sig = sign_payload(webhook.get("secret", ""), body)
    headers = {
        "Content-Type": "application/json",
        "X-ClientVerse-Signature": f"sha256={sig}",
        "X-ClientVerse-Delivery": delivery["id"],
        "X-ClientVerse-Event": delivery["event_type"],
        "X-ClientVerse-Timestamp": delivery["created_at"],
    }
    attempts = list(delivery.get("attempts", []))
    for n in range(len(attempts) + 1, WEBHOOK_MAX_ATTEMPTS + 1):
        try:
            resp = await asyncio.to_thread(requests.post, webhook["url"], data=body, headers=headers, timeout=6)
            code = resp.status_code
            attempts.append({"n": n, "status_code": code, "error": None, "at": now_iso()})
            if 200 <= code < 300:
                await db.webhook_deliveries.update_one({"id": delivery["id"]},
                    {"$set": {"status": "delivered", "attempts": attempts, "delivered_at": now_iso(), "dlq": False}})
                return "delivered"
        except Exception as e:
            attempts.append({"n": n, "status_code": None, "error": str(e)[:200], "at": now_iso()})
        await asyncio.sleep(0.25 * n)
    await db.webhook_deliveries.update_one({"id": delivery["id"]},
        {"$set": {"status": "failed", "attempts": attempts, "dlq": True}})
    return "failed"

def event_matches(event_type: str, patterns) -> bool:
    for p in (patterns or []):
        if p == "*" or p == event_type:
            return True
        if p.endswith(".*") and event_type.startswith(p[:-1]):
            return True
    return False

async def dispatch_webhooks_for_event(ev: dict):
    try:
        hooks = await db.webhooks.find({"tenant_id": ev.get("tenant_id"), "enabled": True}, {"_id": 0}).to_list(100)
    except Exception:
        return
    for wh in hooks:
        if not event_matches(ev.get("event_type"), wh.get("events")):
            continue
        delivery = {"id": new_id("whd"), "tenant_id": ev["tenant_id"], "webhook_id": wh["id"],
                    "webhook_name": wh.get("name"), "event_type": ev["event_type"], "event_id": ev.get("id"),
                    "payload": {"event": ev}, "status": "pending", "attempts": [], "dlq": False, "created_at": now_iso()}
        await db.webhook_deliveries.insert_one(dict(delivery))
        asyncio.create_task(_do_delivery(delivery, wh))

async def record_health_snapshot(tenant_id: str, workspace_id: str):
    scoped = {"tenant_id": tenant_id, "workspace_id": workspace_id}
    commitments = await db.commitments.find(scoped, {"_id": 0}).to_list(500)
    tasks = await db.tasks.find(scoped, {"_id": 0}).to_list(500)
    dl = await db.deliverables.find(scoped, {"_id": 0}).to_list(500)
    rq = await db.client_requests.find(scoped, {"_id": 0}).to_list(500)
    h = compute_health(commitments, tasks, dl, rq)
    await db.health_snapshots.insert_one({"id": new_id("hs"), "tenant_id": tenant_id, "workspace_id": workspace_id,
                                          "score": h["score"], "band": h["band"], "at": now_iso()})
    return h

STALE_SYNC_HOURS = 24
DLQ_ALERT_THRESHOLD = 3
SYNC_FAIL_THRESHOLD = 3
HEALTH_CRITICAL = 50

def _age_hours(iso_str):
    if not iso_str:
        return None
    try:
        d = datetime.fromisoformat(iso_str)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).total_seconds() / 3600.0
    except Exception:
        return None
