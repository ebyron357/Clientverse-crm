import os
import uuid
import jwt
import bcrypt
import logging
import requests
import asyncio
import time
import hmac
import hashlib
import secrets
import json as _json
import base64
from urllib.parse import urlencode
from fastapi.responses import RedirectResponse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from dotenv import load_dotenv
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr
from client_value import register_client_value_routes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("clientverse")

mongo_url = os.environ['MONGO_URL']
mclient = AsyncIOMotorClient(mongo_url)
db = mclient[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
_UNSAFE_JWT_DEFAULTS = {
    "", "changeme", "secret", "jwt_secret", "replace-with-a-long-random-hex-string",
}
if len(JWT_SECRET) < 32 or JWT_SECRET.strip().lower() in _UNSAFE_JWT_DEFAULTS:
    if os.environ.get("ALLOW_INSECURE_JWT", "").lower() not in ("1", "true", "yes"):
        raise RuntimeError(
            "JWT_SECRET must be a strong secret (>=32 chars). "
            "Generate with: openssl rand -hex 32. "
            "Set ALLOW_INSECURE_JWT=1 only for disposable local/dev environments."
        )
JWT_ALG = "HS256"
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')
_cors_raw = os.environ.get("CORS_ORIGINS") or FRONTEND_URL
CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()]

app = FastAPI(title="ClientVerse API", version="v1")
api = APIRouter(prefix="/api")

# ----------------------------- helpers -----------------------------

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
    # Secure cookies only on HTTPS; localhost HTTP needs Secure=False or browsers drop the cookie.
    secure = FRONTEND_URL.startswith("https://")
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=secure,
        samesite="none" if secure else "lax",
        max_age=604800,
        path="/",
    )

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

# ----------------------------- auth -----------------------------

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

class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    name: str

class LoginInput(BaseModel):
    email: EmailStr
    password: str

@api.post("/auth/register")
async def register(inp: RegisterInput, response: Response):
    email = inp.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    tenant_id = new_id("ten")
    await db.tenants.insert_one({"tenant_id": tenant_id, "name": f"{inp.name}'s Org", "created_at": now_iso()})
    uid = new_id("user")
    await db.users.insert_one({
        "user_id": uid, "email": email, "name": inp.name, "role": "admin",
        "tenant_id": tenant_id, "password_hash": hash_password(inp.password),
        "picture": None, "created_at": now_iso(), "auth": "password",
    })
    await db.memberships.insert_one({
        "id": new_id("mem"), "tenant_id": tenant_id, "user_id": uid, "email": email,
        "role": "admin", "status": "active", "invited_by": None, "invited_at": None,
        "accepted_at": now_iso(), "disabled_at": None, "created_at": now_iso(),
    })
    token = create_access_token(uid, email)
    set_auth_cookie(response, token)
    u = await db.users.find_one({"user_id": uid}, {"_id": 0, "password_hash": 0})
    u = await resolve_membership(u)
    return {"user": u, "token": token}

@api.post("/auth/login")
async def login(inp: LoginInput, response: Response):
    email = inp.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("password_hash") or not verify_password(inp.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["user_id"], email)
    set_auth_cookie(response, token)
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password_hash": 0})
    u = await resolve_membership(u)
    return {"user": u, "token": token}

@api.post("/auth/google/session")
async def google_session(request: Request, response: Response):
    body = await request.json()
    session_id = body.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id")
    r = requests.get("https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                     headers={"X-Session-ID": session_id}, timeout=15)
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session_id")
    data = r.json()
    email = data["email"].lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        tenant_id = new_id("ten")
        await db.tenants.insert_one({"tenant_id": tenant_id, "name": f"{data.get('name','')}'s Org", "created_at": now_iso()})
        uid = new_id("user")
        await db.users.insert_one({
            "user_id": uid, "email": email, "name": data.get("name", email),
            "role": "admin", "tenant_id": tenant_id, "picture": data.get("picture"),
            "created_at": now_iso(), "auth": "google",
        })
        user = await db.users.find_one({"user_id": uid}, {"_id": 0})
    session_token = data["session_token"]
    await db.user_sessions.insert_one({
        "user_id": user["user_id"], "session_token": session_token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": now_iso(),
    })
    set_auth_cookie(response, session_token)
    user.pop("password_hash", None)
    # Ensure Google-auth users also get a membership row and effective role
    if not await db.memberships.find_one({"tenant_id": user["tenant_id"], "user_id": user["user_id"]}):
        await db.memberships.insert_one({
            "id": new_id("mem"), "tenant_id": user["tenant_id"], "user_id": user["user_id"],
            "email": user.get("email"), "role": user.get("role", "admin"), "status": "active",
            "invited_by": None, "invited_at": None, "accepted_at": now_iso(),
            "disabled_at": None, "created_at": now_iso(),
        })
    user = await resolve_membership(user)
    return {"user": user, "token": session_token}

@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user

@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}

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

async def assert_workspace(user, workspace_id: str):
    """Reject client-supplied workspace ids that do not belong to the caller's tenant."""
    ws = await db.workspaces.find_one({"id": workspace_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws

# ----------------------------- Team: invitations & members -----------------------------

INVITE_TTL_DAYS = 7

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

async def count_active_admins(tenant_id):
    return await db.memberships.count_documents({"tenant_id": tenant_id, "role": "admin", "status": "active"})

async def _expire_if_needed(inv):
    if inv.get("status") == "pending":
        try:
            exp_dt = datetime.fromisoformat(inv.get("expires_at"))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt < datetime.now(timezone.utc):
                await db.invitations.update_one({"id": inv["id"]}, {"$set": {"status": "expired"}})
                inv["status"] = "expired"
        except Exception:
            pass
    return inv

def _invite_public(inv, tenant_name=None):
    return {"id": inv["id"], "email": inv["email"], "role": inv["role"], "status": inv["status"],
            "invited_by": inv.get("invited_by"), "invited_at": inv.get("invited_at"),
            "expires_at": inv.get("expires_at"), "accepted_at": inv.get("accepted_at"),
            "revoked_at": inv.get("revoked_at"), "tenant_name": tenant_name}

class InviteInput(BaseModel):
    email: EmailStr
    role: str = "member"

class TokenInput(BaseModel):
    token: str

class RoleInput(BaseModel):
    role: str

class MemberStatusInput(BaseModel):
    status: str

@api.get("/team/members")
async def team_members(user=Depends(require_role("admin"))):
    mems = await db.memberships.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("created_at", 1).to_list(500)
    out = []
    for m in mems:
        u = await db.users.find_one({"user_id": m["user_id"]}, {"_id": 0, "password_hash": 0})
        out.append({**m, "name": (u or {}).get("name"), "picture": (u or {}).get("picture"), "auth": (u or {}).get("auth")})
    return out

@api.get("/team/invitations")
async def list_invitations(user=Depends(require_role("admin"))):
    invs = await db.invitations.find({"tenant_id": user["tenant_id"]}, {"_id": 0, "token_hash": 0}).sort("created_at", -1).to_list(500)
    return [_invite_public(await _expire_if_needed(inv)) for inv in invs]

@api.post("/team/invitations")
async def create_invitation(inp: InviteInput, user=Depends(require_role("admin"))):
    email = inp.email.lower()
    if inp.role not in ("admin", "member"):
        raise HTTPException(status_code=422, detail="Role must be admin or member")
    existing_user = await db.users.find_one({"email": email}, {"_id": 0})
    if existing_user:
        if await db.memberships.find_one({"tenant_id": user["tenant_id"], "user_id": existing_user["user_id"], "status": "active"}):
            raise HTTPException(status_code=400, detail="This person is already an active member of your team")
    dup = await db.invitations.find_one({"tenant_id": user["tenant_id"], "email": email, "status": "pending"}, {"_id": 0})
    if dup:
        dup = await _expire_if_needed(dup)
        if dup["status"] == "pending":
            raise HTTPException(status_code=400, detail="An active invitation already exists for this email")
    token = secrets.token_urlsafe(32)
    inv = {"id": new_id("inv"), "tenant_id": user["tenant_id"], "email": email, "role": inp.role,
           "status": "pending", "token_hash": hash_token(token), "invited_by": user["email"], "invited_at": now_iso(),
           "expires_at": (datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)).isoformat(),
           "accepted_at": None, "revoked_at": None, "created_at": now_iso()}
    await db.invitations.insert_one(dict(inv))
    await record_event("team.invitation_created", "invitation", inv["id"], user["tenant_id"], user["email"], payload={"email": email, "role": inp.role})
    return {"invitation": _invite_public(inv), "invite_token": token, "invite_url": f"{FRONTEND_URL}/invite?token={token}"}

@api.post("/team/invitations/{inv_id}/resend")
async def resend_invitation(inv_id: str, user=Depends(require_role("admin"))):
    inv = await db.invitations.find_one({"id": inv_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Not found")
    inv = await _expire_if_needed(inv)
    if inv["status"] not in ("pending", "expired"):
        raise HTTPException(status_code=400, detail="Only pending or expired invitations can be resent")
    token = secrets.token_urlsafe(32)
    await db.invitations.update_one({"id": inv_id}, {"$set": {
        "status": "pending", "token_hash": hash_token(token), "invited_at": now_iso(), "invited_by": user["email"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)).isoformat()}})
    await record_event("team.invitation_resent", "invitation", inv_id, user["tenant_id"], user["email"], payload={"email": inv["email"]})
    return {"invite_token": token, "invite_url": f"{FRONTEND_URL}/invite?token={token}"}

@api.post("/team/invitations/{inv_id}/revoke")
async def revoke_invitation(inv_id: str, user=Depends(require_role("admin"))):
    inv = await db.invitations.find_one({"id": inv_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Not found")
    inv = await _expire_if_needed(inv)
    if inv["status"] != "pending":
        raise HTTPException(status_code=400, detail="Only pending invitations can be revoked")
    await db.invitations.update_one({"id": inv_id}, {"$set": {"status": "revoked", "revoked_at": now_iso()}})
    await record_event("team.invitation_revoked", "invitation", inv_id, user["tenant_id"], user["email"], payload={"email": inv["email"]})
    return {"ok": True}

@api.get("/team/invitations/lookup")
async def lookup_invitation(token: str = Query(...)):
    inv = await db.invitations.find_one({"token_hash": hash_token(token)}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found")
    inv = await _expire_if_needed(inv)
    tenant = await db.tenants.find_one({"tenant_id": inv["tenant_id"]}, {"_id": 0})
    return _invite_public(inv, tenant_name=(tenant or {}).get("name"))

@api.post("/team/invitations/accept")
async def accept_invitation(inp: TokenInput, user=Depends(get_current_user)):
    inv = await db.invitations.find_one({"token_hash": hash_token(inp.token)}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found")
    inv = await _expire_if_needed(inv)
    if inv["status"] == "expired":
        raise HTTPException(status_code=400, detail="This invitation has expired")
    if inv["status"] == "revoked":
        raise HTTPException(status_code=400, detail="This invitation has been revoked")
    if inv["status"] == "accepted":
        raise HTTPException(status_code=400, detail="This invitation has already been used")
    if user["email"].lower() != inv["email"].lower():
        raise HTTPException(status_code=403, detail=f"This invitation was sent to {inv['email']}. Sign in with that email to accept.")
    tenant_id = inv["tenant_id"]
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"tenant_id": tenant_id, "role": inv["role"]}})
    existing = await db.memberships.find_one({"tenant_id": tenant_id, "user_id": user["user_id"]}, {"_id": 0})
    if existing:
        await db.memberships.update_one({"tenant_id": tenant_id, "user_id": user["user_id"]},
            {"$set": {"role": inv["role"], "status": "active", "accepted_at": now_iso(), "disabled_at": None}})
    else:
        await db.memberships.insert_one({"id": new_id("mem"), "tenant_id": tenant_id, "user_id": user["user_id"], "email": user["email"],
            "role": inv["role"], "status": "active", "invited_by": inv.get("invited_by"), "invited_at": inv.get("invited_at"),
            "accepted_at": now_iso(), "disabled_at": None, "created_at": now_iso()})
    await db.invitations.update_one({"id": inv["id"]}, {"$set": {"status": "accepted", "accepted_at": now_iso(), "token_hash": None}})
    await record_event("team.invitation_accepted", "invitation", inv["id"], tenant_id, user["email"], payload={"email": user["email"], "role": inv["role"]})
    return {"ok": True, "tenant_id": tenant_id, "role": inv["role"]}

@api.patch("/team/members/{target_user_id}/role")
async def change_member_role(target_user_id: str, inp: RoleInput, user=Depends(require_role("admin"))):
    if inp.role not in ("admin", "member"):
        raise HTTPException(status_code=422, detail="Role must be admin or member")
    m = await db.memberships.find_one({"tenant_id": user["tenant_id"], "user_id": target_user_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")
    if m["role"] == "admin" and inp.role != "admin" and m["status"] == "active" and await count_active_admins(user["tenant_id"]) <= 1:
        raise HTTPException(status_code=400, detail="Cannot demote the last active admin. Promote another admin first.")
    await db.memberships.update_one({"tenant_id": user["tenant_id"], "user_id": target_user_id}, {"$set": {"role": inp.role}})
    await db.users.update_one({"user_id": target_user_id, "tenant_id": user["tenant_id"]}, {"$set": {"role": inp.role}})
    await record_event("team.role_changed", "membership", target_user_id, user["tenant_id"], user["email"], payload={"target": m["email"], "from": m["role"], "to": inp.role})
    return {"ok": True, "role": inp.role}

@api.patch("/team/members/{target_user_id}/status")
async def change_member_status(target_user_id: str, inp: MemberStatusInput, user=Depends(require_role("admin"))):
    if inp.status not in ("active", "disabled"):
        raise HTTPException(status_code=422, detail="Status must be active or disabled")
    m = await db.memberships.find_one({"tenant_id": user["tenant_id"], "user_id": target_user_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")
    if inp.status == "disabled" and m["role"] == "admin" and m["status"] == "active" and await count_active_admins(user["tenant_id"]) <= 1:
        raise HTTPException(status_code=400, detail="Cannot disable the last active admin.")
    upd = {"status": inp.status, "disabled_at": now_iso() if inp.status == "disabled" else None}
    await db.memberships.update_one({"tenant_id": user["tenant_id"], "user_id": target_user_id}, {"$set": upd})
    await record_event("team.member_disabled" if inp.status == "disabled" else "team.member_enabled",
                       "membership", target_user_id, user["tenant_id"], user["email"], payload={"target": m["email"]})
    return {"ok": True, "status": inp.status}

# ----------------------------- generic CRUD factory -----------------------------

def scope(user):
    return {"tenant_id": user["tenant_id"]}

async def gen_list(coll, user, extra=None, sort_field="created_at"):
    q = scope(user)
    if extra:
        q.update(extra)
    docs = await db[coll].find(q, {"_id": 0}).sort(sort_field, -1).to_list(2000)
    return docs

# ----------------------------- Companies & Contacts -----------------------------

class CompanyInput(BaseModel):
    name: str
    industry: Optional[str] = None
    website: Optional[str] = None
    tier: Optional[str] = "standard"

@api.get("/companies")
async def list_companies(user=Depends(get_current_user)):
    return await gen_list("companies", user)

@api.post("/companies")
async def create_company(inp: CompanyInput, user=Depends(get_current_user)):
    doc = {"id": new_id("co"), "tenant_id": user["tenant_id"], "created_at": now_iso(),
           **inp.model_dump()}
    await db.companies.insert_one(doc)
    await record_event("company.created", "company", doc["id"], user["tenant_id"], user["email"], payload={"name": inp.name})
    return {k: v for k, v in doc.items() if k != "_id"}

class ContactInput(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    company_id: Optional[str] = None
    influence: Optional[str] = "medium"
    sentiment: Optional[str] = "neutral"

@api.get("/contacts")
async def list_contacts(company_id: Optional[str] = None, user=Depends(get_current_user)):
    extra = {"company_id": company_id} if company_id else None
    return await gen_list("contacts", user, extra)

@api.post("/contacts")
async def create_contact(inp: ContactInput, user=Depends(get_current_user)):
    doc = {"id": new_id("ct"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.contacts.insert_one(doc)
    await record_event("contact.created", "contact", doc["id"], user["tenant_id"], user["email"], payload={"name": inp.name})
    return {k: v for k, v in doc.items() if k != "_id"}

# ----------------------------- Opportunities (Pipeline) -----------------------------

STAGES = ["lead", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]

class OppInput(BaseModel):
    name: str
    company_id: Optional[str] = None
    value: float = 0
    stage: str = "lead"
    owner: Optional[str] = None

@api.get("/opportunities")
async def list_opps(user=Depends(get_current_user)):
    return await gen_list("opportunities", user)

@api.post("/opportunities")
async def create_opp(inp: OppInput, user=Depends(get_current_user)):
    doc = {"id": new_id("opp"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.opportunities.insert_one(doc)
    await record_event("opportunity.created", "opportunity", doc["id"], user["tenant_id"], user["email"], payload={"name": inp.name, "value": inp.value})
    return {k: v for k, v in doc.items() if k != "_id"}

class StageInput(BaseModel):
    stage: str

@api.patch("/opportunities/{opp_id}/stage")
async def move_stage(opp_id: str, inp: StageInput, user=Depends(get_current_user)):
    if inp.stage not in STAGES:
        raise HTTPException(status_code=400, detail="Invalid stage")
    opp = await db.opportunities.find_one({"id": opp_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not opp:
        raise HTTPException(status_code=404, detail="Not found")
    await db.opportunities.update_one({"id": opp_id}, {"$set": {"stage": inp.stage}})
    et = "opportunity.closed_won" if inp.stage == "closed_won" else ("opportunity.closed_lost" if inp.stage == "closed_lost" else "opportunity.stage_changed")
    await record_event(et, "opportunity", opp_id, user["tenant_id"], user["email"], payload={"from": opp["stage"], "to": inp.stage})
    # auto-create workspace on won
    if inp.stage == "closed_won" and opp.get("company_id"):
        exists = await db.workspaces.find_one({"opportunity_id": opp_id, "tenant_id": user["tenant_id"]})
        if not exists:
            wid = new_id("ws")
            await db.workspaces.insert_one({"id": wid, "tenant_id": user["tenant_id"], "name": opp["name"],
                "company_id": opp["company_id"], "opportunity_id": opp_id, "stage": "onboard",
                "created_at": now_iso()})
            await record_event("client_workspace.created", "workspace", wid, user["tenant_id"], user["email"], workspace_id=wid, payload={"from_opportunity": opp_id})
            await record_event("onboarding.started", "workspace", wid, user["tenant_id"], user["email"], workspace_id=wid)
    return {"ok": True, "stage": inp.stage}

# ----------------------------- Workspaces -----------------------------

class WorkspaceInput(BaseModel):
    name: str
    company_id: Optional[str] = None
    stage: str = "onboard"

@api.get("/workspaces")
async def list_workspaces(user=Depends(get_current_user)):
    return await gen_list("workspaces", user)

@api.post("/workspaces")
async def create_workspace(inp: WorkspaceInput, user=Depends(get_current_user)):
    doc = {"id": new_id("ws"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump(), "opportunity_id": None}
    await db.workspaces.insert_one(doc)
    await record_event("client_workspace.created", "workspace", doc["id"], user["tenant_id"], user["email"], workspace_id=doc["id"], payload={"name": inp.name})
    return {k: v for k, v in doc.items() if k != "_id"}

@api.get("/workspaces/{ws_id}")
async def get_workspace(ws_id: str, user=Depends(get_current_user)):
    ws = await db.workspaces.find_one({"id": ws_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=404, detail="Not found")
    company = await db.companies.find_one({"id": ws.get("company_id"), "tenant_id": user["tenant_id"]}, {"_id": 0}) if ws.get("company_id") else None
    scoped = {"tenant_id": user["tenant_id"], "workspace_id": ws_id}
    tasks = await db.tasks.find(scoped, {"_id": 0}).to_list(500)
    deliverables = await db.deliverables.find(scoped, {"_id": 0}).to_list(500)
    requests_ = await db.client_requests.find(scoped, {"_id": 0}).to_list(500)
    approvals = await db.approvals.find(scoped, {"_id": 0}).to_list(500)
    commitments = await db.commitments.find(scoped, {"_id": 0}).to_list(500)
    events = await db.domain_events.find(scoped, {"_id": 0}).sort("timestamp", -1).to_list(200)
    health = compute_health(commitments, tasks, deliverables, requests_)
    return {"workspace": ws, "company": company, "tasks": tasks, "deliverables": deliverables,
            "requests": requests_, "approvals": approvals, "commitments": commitments,
            "events": events, "health": health}

# ----------------------------- Health computation -----------------------------

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

# ----------------------------- Tasks / Deliverables / Requests / Approvals / Commitments -----------------------------

class TaskInput(BaseModel):
    workspace_id: str
    title: str
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    status: str = "todo"

@api.post("/tasks")
async def create_task(inp: TaskInput, user=Depends(get_current_user)):
    await assert_workspace(user, inp.workspace_id)
    doc = {"id": new_id("task"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.tasks.insert_one(doc)
    await record_event("task.created", "task", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"title": inp.title})
    return {k: v for k, v in doc.items() if k != "_id"}

class TaskStatus(BaseModel):
    status: str

@api.patch("/tasks/{task_id}")
async def update_task(task_id: str, inp: TaskStatus, user=Depends(get_current_user)):
    t = await db.tasks.find_one({"id": task_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    await db.tasks.update_one({"id": task_id}, {"$set": {"status": inp.status}})
    if inp.status == "done":
        await record_event("task.completed", "task", task_id, user["tenant_id"], user["email"], workspace_id=t["workspace_id"], payload={"title": t["title"]})
    return {"ok": True}

class DeliverableInput(BaseModel):
    workspace_id: str
    title: str
    description: Optional[str] = None
    status: str = "draft"

@api.post("/deliverables")
async def create_deliverable(inp: DeliverableInput, user=Depends(get_current_user)):
    await assert_workspace(user, inp.workspace_id)
    doc = {"id": new_id("dlv"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.deliverables.insert_one(doc)
    await record_event("deliverable.created", "deliverable", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"title": inp.title})
    return {k: v for k, v in doc.items() if k != "_id"}

@api.patch("/deliverables/{dlv_id}")
async def approve_deliverable(dlv_id: str, inp: TaskStatus, user=Depends(get_current_user)):
    d = await db.deliverables.find_one({"id": dlv_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    await db.deliverables.update_one({"id": dlv_id}, {"$set": {"status": inp.status}})
    if inp.status == "approved":
        await record_event("deliverable.approved", "deliverable", dlv_id, user["tenant_id"], user["email"], workspace_id=d["workspace_id"], payload={"title": d["title"]})
    return {"ok": True}

class RequestInput(BaseModel):
    workspace_id: str
    title: str
    priority: str = "medium"
    status: str = "open"

@api.post("/client-requests")
async def create_request(inp: RequestInput, user=Depends(get_current_user)):
    await assert_workspace(user, inp.workspace_id)
    doc = {"id": new_id("req"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.client_requests.insert_one(doc)
    await record_event("client_request.created", "client_request", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"title": inp.title})
    return {k: v for k, v in doc.items() if k != "_id"}

@api.patch("/client-requests/{req_id}")
async def update_request(req_id: str, inp: TaskStatus, user=Depends(get_current_user)):
    r = await db.client_requests.find_one({"id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    await db.client_requests.update_one({"id": req_id}, {"$set": {"status": inp.status}})
    return {"ok": True}

class ApprovalInput(BaseModel):
    workspace_id: str
    title: str
    kind: str = "external_effect"
    status: str = "requested"

@api.post("/approvals")
async def create_approval(inp: ApprovalInput, user=Depends(get_current_user)):
    await assert_workspace(user, inp.workspace_id)
    doc = {"id": new_id("apr"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.approvals.insert_one(doc)
    await record_event("approval.requested", "approval", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"title": inp.title})
    return {k: v for k, v in doc.items() if k != "_id"}

@api.patch("/approvals/{apr_id}")
async def decide_approval(apr_id: str, inp: TaskStatus, user=Depends(require_role("admin"))):
    a = await db.approvals.find_one({"id": apr_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Not found")
    await db.approvals.update_one({"id": apr_id}, {"$set": {"status": inp.status, "decided_by": user["email"], "decided_at": now_iso()}})
    await record_event("approval.completed", "approval", apr_id, user["tenant_id"], user["email"], workspace_id=a["workspace_id"], payload={"decision": inp.status})
    result = {"ok": True}
    if a.get("kind") == "mcp_write" and a.get("pending_action_id"):
        if inp.status == "approved":
            result["execution"] = await execute_pending_mcp(a["pending_action_id"], user)
        else:
            await db.mcp_pending_actions.update_one({"id": a["pending_action_id"]}, {"$set": {"status": "rejected"}})
            await db.mcp_tool_invocations.update_one({"approval_id": apr_id}, {"$set": {"status": "rejected"}})
    return result

class CommitmentInput(BaseModel):
    workspace_id: str
    title: str
    owner: Optional[str] = None
    due_date: Optional[str] = None
    status: str = "open"

@api.post("/commitments")
async def create_commitment(inp: CommitmentInput, user=Depends(get_current_user)):
    await assert_workspace(user, inp.workspace_id)
    doc = {"id": new_id("cmt"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.commitments.insert_one(doc)
    await record_event("commitment.created", "commitment", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"title": inp.title})
    return {k: v for k, v in doc.items() if k != "_id"}

class CommitmentPatch(BaseModel):
    status: Optional[str] = None
    due_date: Optional[str] = None

@api.patch("/commitments/{cmt_id}")
async def update_commitment(cmt_id: str, inp: CommitmentPatch, user=Depends(get_current_user)):
    c = await db.commitments.find_one({"id": cmt_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    upd = {}
    if inp.status is not None:
        upd["status"] = inp.status
    if inp.due_date is not None:
        upd["due_date"] = inp.due_date or None
    if upd:
        await db.commitments.update_one({"id": cmt_id}, {"$set": upd})
    etmap = {"at_risk": "commitment.at_risk", "breached": "commitment.breached", "fulfilled": "commitment.fulfilled"}
    if inp.status in etmap:
        await record_event(etmap[inp.status], "commitment", cmt_id, user["tenant_id"], user["email"], workspace_id=c["workspace_id"], payload={"title": c["title"]})
    return {"ok": True, **upd}

# ----------------------------- Commitment SLA risk automation -----------------------------

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

@api.post("/commitments/evaluate-risk")
async def commitments_evaluate_risk(user=Depends(get_current_user)):
    return await evaluate_commitment_risk(tenant_id=user["tenant_id"], actor=user["email"])

# ----------------------------- Registries -----------------------------

REGISTRIES = {
    "integrations": "integrations",
    "mcp-servers": "mcp_servers",
    "plugins": "plugins",
    "webhooks": "webhooks",
}

@api.get("/registry/{kind}")
async def list_registry(kind: str, user=Depends(get_current_user)):
    coll = REGISTRIES.get(kind)
    if not coll:
        raise HTTPException(status_code=404, detail="Unknown registry")
    return await gen_list(coll, user)

# ----------------------------- Domain events / Audit -----------------------------

@api.get("/events")
async def list_events(limit: int = Query(200), user=Depends(get_current_user)):
    docs = await db.domain_events.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return docs

# ----------------------------- Dashboard summary -----------------------------

@api.get("/dashboard")
async def dashboard(user=Depends(get_current_user)):
    t = user["tenant_id"]
    opps = await db.opportunities.find({"tenant_id": t}, {"_id": 0}).to_list(2000)
    workspaces = await db.workspaces.find({"tenant_id": t}, {"_id": 0}).to_list(2000)
    commitments = await db.commitments.find({"tenant_id": t}, {"_id": 0}).to_list(2000)
    pipeline_value = sum(o.get("value", 0) for o in opps if o.get("stage") not in ("closed_won", "closed_lost"))
    won_value = sum(o.get("value", 0) for o in opps if o.get("stage") == "closed_won")
    funnel = {s: len([o for o in opps if o.get("stage") == s]) for s in STAGES}
    # health per workspace
    portfolio = []
    for ws in workspaces:
        scoped = {"tenant_id": t, "workspace_id": ws["id"]}
        cm = [c for c in commitments if c.get("workspace_id") == ws["id"]]
        tasks = await db.tasks.find(scoped, {"_id": 0}).to_list(500)
        dl = await db.deliverables.find(scoped, {"_id": 0}).to_list(500)
        rq = await db.client_requests.find(scoped, {"_id": 0}).to_list(500)
        h = compute_health(cm, tasks, dl, rq)
        portfolio.append({"id": ws["id"], "name": ws["name"], "stage": ws.get("stage"), "health": h})
    at_risk = len([c for c in commitments if c.get("status") in ("at_risk", "breached")])
    # Outcome (goal) rollup across portfolio
    outcomes = await db.outcomes.find({"tenant_id": t}, {"_id": 0}).to_list(2000)
    osnaps = await db.outcome_snapshots.find({"tenant_id": t}, {"_id": 0}).sort("at", 1).to_list(5000)
    trend_map = {}
    for s in osnaps:
        trend_map.setdefault(s["outcome_id"], []).append(s["pct"])
    def gpct(g):
        return min(100, round((g.get("current_value", 0) / g["target_value"]) * 100)) if g.get("target_value") else None
    ws_rollup = []
    for ws in workspaces:
        gs = [g for g in outcomes if g.get("workspace_id") == ws["id"]]
        pcts = [gpct(g) for g in gs if gpct(g) is not None]
        ws_rollup.append({
            "id": ws["id"], "name": ws["name"], "goal_count": len(gs),
            "avg_pct": round(sum(pcts) / len(pcts)) if pcts else None,
            "goals": [{"id": g["id"], "title": g["title"], "pct": gpct(g), "status": g.get("status"),
                       "current_value": g.get("current_value"), "target_value": g.get("target_value"), "unit": g.get("unit"), "trend": trend_map.get(g["id"], [])} for g in gs],
        })
    all_pcts = [gpct(g) for g in outcomes if gpct(g) is not None]
    goal_rollup = {
        "total_goals": len(outcomes),
        "on_track": len([g for g in outcomes if g.get("status") == "on_track"]),
        "at_risk": len([g for g in outcomes if g.get("status") == "at_risk"]),
        "avg_progress": round(sum(all_pcts) / len(all_pcts)) if all_pcts else 0,
        "workspaces": [w for w in ws_rollup if w["goal_count"] > 0],
    }
    return {
        "pipeline_value": pipeline_value, "won_value": won_value,
        "open_opportunities": len([o for o in opps if o.get("stage") not in ("closed_won", "closed_lost")]),
        "active_workspaces": len(workspaces), "at_risk_commitments": at_risk,
        "funnel": funnel, "portfolio": portfolio, "goal_rollup": goal_rollup,
    }

# ----------------------------- Evidence-backed AI -----------------------------

class AIInput(BaseModel):
    workspace_id: str
    mode: str = "health_summary"  # or draft_message
    instruction: Optional[str] = None

@api.post("/ai/generate")
async def ai_generate(inp: AIInput, user=Depends(get_current_user)):
    ws = await db.workspaces.find_one({"id": inp.workspace_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    scoped = {"tenant_id": user["tenant_id"], "workspace_id": inp.workspace_id}
    commitments = await db.commitments.find(scoped, {"_id": 0}).to_list(500)
    tasks = await db.tasks.find(scoped, {"_id": 0}).to_list(500)
    deliverables = await db.deliverables.find(scoped, {"_id": 0}).to_list(500)
    requests_ = await db.client_requests.find(scoped, {"_id": 0}).to_list(500)
    health = compute_health(commitments, tasks, deliverables, requests_)

    sources = []
    for c in commitments:
        sources.append({"type": "commitment", "id": c["id"], "label": c["title"], "status": c.get("status")})
    for r in requests_:
        sources.append({"type": "client_request", "id": r["id"], "label": r["title"], "status": r.get("status")})
    for t in tasks:
        sources.append({"type": "task", "id": t["id"], "label": t["title"], "status": t.get("status")})

    facts_text = "\n".join([f"- [{s['type']}] {s['label']} (status: {s['status']})" for s in sources]) or "- No records yet."
    run_id = new_id("airun")
    await record_event("agent.run_started", "ai_run", run_id, user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"mode": inp.mode})

    if inp.mode == "draft_message":
        system = "You are a client operations assistant. Draft a concise, professional client update email based ONLY on the provided facts. Do not invent facts. Clearly separate what is known (fact) from any suggestion (inference)."
        prompt = f"Client workspace: {ws['name']}\nHealth score: {health['score']}/100 ({health['band']}).\nKnown facts:\n{facts_text}\n\nInstruction: {inp.instruction or 'Write a status update to the client.'}"
    else:
        system = "You are a client health analyst. Summarize the client's health based ONLY on the provided facts. Be explicit about what is a fact vs an inference. Keep it under 150 words."
        prompt = f"Client workspace: {ws['name']}\nComputed health score: {health['score']}/100 ({health['band']}).\nContributing factors:\n" + "\n".join([f"- {f['factor']}: {f['impact']} ({f['detail']})" for f in health['factors']]) + f"\n\nKnown facts:\n{facts_text}"

    ai_text = ""
    model_version = "claude-sonnet-4-6"
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=run_id,
                       system_message=system).with_model("anthropic", model_version)
        resp = await chat.send_message(UserMessage(text=prompt))
        ai_text = resp if isinstance(resp, str) else str(resp)
        await record_event("agent.run_completed", "ai_run", run_id, user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"mode": inp.mode})
    except Exception as e:
        logger.exception("AI generation failed")
        await record_event("agent.run_failed", "ai_run", run_id, user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"error": str(e)})
        raise HTTPException(status_code=502, detail="AI generation failed. Please retry.")

    result = {
        "run_id": run_id, "mode": inp.mode, "output": ai_text.strip(),
        "sources": sources, "health": health,
        "confidence": "high" if len(sources) >= 3 else ("medium" if sources else "low"),
        "model_version": model_version, "prompt_version": "v1", "policy_version": "v1",
        "freshness": now_iso(), "classification": {"fact_basis": len(sources)},
    }
    await db.ai_runs.insert_one({"id": run_id, "tenant_id": user["tenant_id"], "workspace_id": inp.workspace_id,
                                 "created_at": now_iso(), **result})
    return {k: v for k, v in result.items()}

# ----------------------------- seed -----------------------------

async def seed():
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    admin_pw = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        tenant_id = new_id("ten")
        await db.tenants.insert_one({"tenant_id": tenant_id, "name": "ClientVerse HQ", "created_at": now_iso()})
        uid = new_id("user")
        await db.users.insert_one({"user_id": uid, "email": admin_email, "name": "TV Pro", "role": "admin",
                                   "tenant_id": tenant_id, "password_hash": hash_password(admin_pw),
                                   "picture": None, "created_at": now_iso(), "auth": "password"})
        await seed_demo(tenant_id, admin_email)
        logger.info("Seeded admin + demo data")
    else:
        if existing.get("password_hash") and not verify_password(admin_pw, existing["password_hash"]):
            await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_pw)}})
    # registries seed (idempotent by name)
    await seed_registries()
    await seed_team()
    await db.users.create_index("email", unique=True)
    await db.memberships.create_index([("tenant_id", 1), ("user_id", 1)])
    await db.invitations.create_index("token_hash")

async def seed_team():
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    au = await db.users.find_one({"email": admin_email}, {"_id": 0})
    if not au:
        return
    t = au["tenant_id"]
    if not await db.memberships.find_one({"tenant_id": t, "user_id": au["user_id"]}):
        await db.memberships.insert_one({"id": new_id("mem"), "tenant_id": t, "user_id": au["user_id"], "email": admin_email,
            "role": "admin", "status": "active", "invited_by": None, "invited_at": None,
            "accepted_at": now_iso(), "disabled_at": None, "created_at": now_iso()})
    mem_email = (os.environ.get("DEMO_MEMBER_EMAIL") or "").lower()
    mem_pw = os.environ.get("DEMO_MEMBER_PASSWORD") or ""
    if not mem_email or not mem_pw:
        # No demo member is seeded unless the operator explicitly configures one.
        # Never fall back to a well-known email/password in a deployed environment.
        return
    existing_member = await db.users.find_one({"email": mem_email})
    if not existing_member:
        muid = new_id("user")
        await db.users.insert_one({"user_id": muid, "email": mem_email, "name": "Demo Member", "role": "member",
            "tenant_id": t, "password_hash": hash_password(mem_pw), "picture": None, "created_at": now_iso(), "auth": "password"})
        await db.memberships.insert_one({"id": new_id("mem"), "tenant_id": t, "user_id": muid, "email": mem_email,
            "role": "member", "status": "active", "invited_by": admin_email, "invited_at": now_iso(),
            "accepted_at": now_iso(), "disabled_at": None, "created_at": now_iso()})
    elif existing_member.get("password_hash") and not verify_password(mem_pw, existing_member["password_hash"]):
        await db.users.update_one({"email": mem_email}, {"$set": {"password_hash": hash_password(mem_pw)}})

async def seed_demo(tenant_id, actor):
    co1 = {"id": new_id("co"), "tenant_id": tenant_id, "name": "Northwind Analytics", "industry": "Data & AI", "website": "northwind.example", "tier": "enterprise", "created_at": now_iso()}
    co2 = {"id": new_id("co"), "tenant_id": tenant_id, "name": "Harbor Logistics", "industry": "Supply Chain", "website": "harbor.example", "tier": "growth", "created_at": now_iso()}
    await db.companies.insert_many([co1, co2])
    await db.contacts.insert_many([
        {"id": new_id("ct"), "tenant_id": tenant_id, "name": "Dana Reyes", "email": "dana@northwind.example", "role": "VP Product", "company_id": co1["id"], "influence": "high", "sentiment": "positive", "created_at": now_iso()},
        {"id": new_id("ct"), "tenant_id": tenant_id, "name": "Marcus Lee", "email": "marcus@harbor.example", "role": "COO", "company_id": co2["id"], "influence": "high", "sentiment": "neutral", "created_at": now_iso()},
    ])
    await db.opportunities.insert_many([
        {"id": new_id("opp"), "tenant_id": tenant_id, "name": "Northwind Platform Expansion", "company_id": co1["id"], "value": 120000, "stage": "negotiation", "owner": actor, "created_at": now_iso()},
        {"id": new_id("opp"), "tenant_id": tenant_id, "name": "Harbor Onboarding Package", "company_id": co2["id"], "value": 45000, "stage": "proposal", "owner": actor, "created_at": now_iso()},
        {"id": new_id("opp"), "tenant_id": tenant_id, "name": "Acme Pilot", "company_id": None, "value": 20000, "stage": "qualified", "owner": actor, "created_at": now_iso()},
    ])
    ws = {"id": new_id("ws"), "tenant_id": tenant_id, "name": "Northwind Delivery", "company_id": co1["id"], "opportunity_id": None, "stage": "serve", "created_at": now_iso()}
    await db.workspaces.insert_one(ws)
    wid = ws["id"]
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    await db.tasks.insert_many([
        {"id": new_id("task"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Kickoff workshop", "assignee": actor, "due_date": past, "status": "done", "created_at": now_iso()},
        {"id": new_id("task"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Data integration setup", "assignee": actor, "due_date": past, "status": "in_progress", "created_at": now_iso()},
        {"id": new_id("task"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Dashboard review", "assignee": actor, "due_date": future, "status": "todo", "created_at": now_iso()},
    ])
    await db.deliverables.insert_many([
        {"id": new_id("dlv"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Onboarding Plan", "description": "30-day onboarding roadmap", "status": "approved", "created_at": now_iso()},
        {"id": new_id("dlv"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Analytics Dashboard v1", "description": "First analytics build", "status": "in_review", "created_at": now_iso()},
    ])
    await db.client_requests.insert_many([
        {"id": new_id("req"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Add revenue forecast widget", "priority": "high", "status": "open", "created_at": now_iso()},
    ])
    cmt1 = {"id": new_id("cmt"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Deliver dashboard by month end", "owner": actor, "due_date": future, "status": "at_risk", "created_at": now_iso()}
    cmt2 = {"id": new_id("cmt"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Weekly status call", "owner": actor, "due_date": future, "status": "open", "created_at": now_iso()}
    await db.commitments.insert_many([cmt1, cmt2])
    out1 = {"id": new_id("out"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Launch analytics platform", "target": "Production go-live", "target_value": 100, "current_value": 65, "unit": "% complete", "status": "on_track", "linked_commitment_ids": [cmt1["id"]], "created_at": now_iso()}
    out2 = {"id": new_id("out"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Cut reporting time", "target": "Reduce vs baseline", "target_value": 50, "current_value": 28, "unit": "% reduction", "status": "at_risk", "linked_commitment_ids": [cmt1["id"], cmt2["id"]], "created_at": now_iso()}
    await db.outcomes.insert_many([out1, out2])
    for i, pct in enumerate([30, 45, 55, 65]):
        await db.outcome_snapshots.insert_one({"id": new_id("os"), "tenant_id": tenant_id, "outcome_id": out1["id"], "pct": pct, "at": (datetime.now(timezone.utc) - timedelta(days=(4 - i))).isoformat()})
    for i, pct in enumerate([20, 36, 44, 56]):
        await db.outcome_snapshots.insert_one({"id": new_id("os"), "tenant_id": tenant_id, "outcome_id": out2["id"], "pct": pct, "at": (datetime.now(timezone.utc) - timedelta(days=(4 - i))).isoformat()})
    for i, sc in enumerate([58, 64, 72, 69, 78]):
        ts = (datetime.now(timezone.utc) - timedelta(days=(5 - i))).isoformat()
        band = "healthy" if sc >= 75 else ("at_risk" if sc >= 50 else "critical")
        await db.health_snapshots.insert_one({"id": new_id("hs"), "tenant_id": tenant_id, "workspace_id": wid, "score": sc, "band": band, "at": ts})
    await db.approvals.insert_one({"id": new_id("apr"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Send Q1 renewal proposal to client", "kind": "external_effect", "status": "requested", "created_at": now_iso()})
    await record_event("client_workspace.created", "workspace", wid, tenant_id, actor, workspace_id=wid, payload={"name": ws["name"]})
    await record_event("commitment.at_risk", "commitment", "seed", tenant_id, actor, workspace_id=wid, payload={"title": "Deliver dashboard by month end"})

async def seed_registries():
    tenant = await db.tenants.find_one({"name": "ClientVerse HQ"})
    if not tenant:
        return
    t = tenant["tenant_id"]
    if await db.integrations.find_one({"tenant_id": t}):
        return
    await db.integrations.insert_many([
        {"id": new_id("intg"), "tenant_id": t, "name": "Gmail", "provider": "Google", "category": "communications", "status": "AVAILABLE", "auth_method": "OAuth", "scopes": ["mail.send", "mail.read"], "description": "Send and read client emails.", "created_at": now_iso()},
        {"id": new_id("intg"), "tenant_id": t, "name": "Stripe", "provider": "Stripe", "category": "billing", "status": "BETA", "auth_method": "API key", "scopes": ["invoices.write"], "description": "Invoicing and payments.", "created_at": now_iso()},
        {"id": new_id("intg"), "tenant_id": t, "name": "Google Calendar", "provider": "Google", "category": "scheduling", "status": "PLANNED", "auth_method": "OAuth", "scopes": ["calendar.events"], "description": "Schedule client meetings.", "created_at": now_iso()},
    ])
    await db.mcp_servers.insert_many([
        {"id": new_id("mcp"), "tenant_id": t, "name": "ClientVerse Read Tools", "version": "1.0.0", "level": 1, "status": "AVAILABLE", "tools": ["search_contacts", "get_client_health", "list_open_commitments"], "description": "Read-only MCP tools.", "created_at": now_iso()},
        {"id": new_id("mcp"), "tenant_id": t, "name": "ClientVerse Write Tools", "version": "0.4.0", "level": 2, "status": "ALPHA", "tools": ["create_task", "add_note", "create_approval_request"], "description": "Reversible internal writes.", "created_at": now_iso()},
        {"id": new_id("mcp"), "tenant_id": t, "name": "ClientVerse External Effects", "version": "0.1.0", "level": 3, "status": "PLANNED", "tools": ["send_message", "schedule_meeting"], "description": "External effects, approval-gated.", "created_at": now_iso()},
    ])
    await db.plugins.insert_many([
        {"id": new_id("plg"), "tenant_id": t, "name": "Health Score Analyzer", "version": "1.2.0", "publisher": "ClientVerse", "type": "analytics provider", "status": "AVAILABLE", "permissions": ["read:workspace"], "description": "Explainable client health scoring.", "created_at": now_iso()},
        {"id": new_id("plg"), "tenant_id": t, "name": "Slack Notifier", "version": "0.9.0", "publisher": "Community", "type": "communications provider", "status": "BETA", "permissions": ["events:consume"], "description": "Post workspace events to Slack.", "created_at": now_iso()},
    ])
    await db.webhooks.insert_many([
        {"id": new_id("wh"), "tenant_id": t, "name": "Ops Alerts (external)", "url": "https://hooks.invalid.example/ops", "events": ["commitment.at_risk", "approval.requested"], "status": "AVAILABLE", "signed": True, "enabled": True, "secret": "whsec_ops_" + secrets.token_hex(8), "description": "External endpoint — unreachable in demo, shows retry + dead-letter.", "created_at": now_iso()},
        {"id": new_id("wh"), "tenant_id": t, "name": "Local Test Sink", "url": "http://localhost:8001/api/webhooks/sink", "events": ["commitment.at_risk", "commitment.breached", "approval.requested", "task.created", "mcp.tool_invoked", "webhook.test", "commitment.fulfilled", "deliverable.approved"], "status": "AVAILABLE", "signed": True, "enabled": True, "secret": "whsec_sink_" + secrets.token_hex(8), "description": "Built-in sink returning 200 — shows successful signed delivery.", "created_at": now_iso()},
    ])

# ----------------------------- MCP: Governed Server (Level 1 read tools, live) -----------------------------

MCP_SERVER_ID = "clientverse-read-tools"
MCP_RATE_LIMIT_PER_MIN = 30

MCP_TOOL_CATALOG = [
    {
        "name": "search_contacts", "level": 1, "version": "1.0.0", "provider": "ClientVerse", "publisher": "ClientVerse",
        "category": "relationships", "description": "Search stakeholder contacts by name, email, or role.",
        "scopes": ["contacts:read"], "records_read": ["contact"], "records_written": [],
        "tenant_scoped": True, "workspace_scoped": False, "approval_required": False,
        "rate_limit_per_min": MCP_RATE_LIMIT_PER_MIN, "cost_behavior": "none", "timeout_seconds": 10,
        "idempotent": True, "input_schema": {"query": {"type": "string", "required": False, "placeholder": "e.g. Dana"}},
    },
    {
        "name": "get_client_health", "level": 1, "version": "1.0.0", "provider": "ClientVerse", "publisher": "ClientVerse",
        "category": "outcomes", "description": "Return explainable client health score + factors for a workspace.",
        "scopes": ["health:read"], "records_read": ["commitment", "task", "deliverable", "client_request"], "records_written": [],
        "tenant_scoped": True, "workspace_scoped": True, "approval_required": False,
        "rate_limit_per_min": MCP_RATE_LIMIT_PER_MIN, "cost_behavior": "none", "timeout_seconds": 10,
        "idempotent": True, "input_schema": {"workspace_id": {"type": "workspace", "required": True}},
    },
    {
        "name": "list_open_commitments", "level": 1, "version": "1.0.0", "provider": "ClientVerse", "publisher": "ClientVerse",
        "category": "outcomes", "description": "List all open / at-risk / breached commitments for the tenant.",
        "scopes": ["commitments:read"], "records_read": ["commitment"], "records_written": [],
        "tenant_scoped": True, "workspace_scoped": False, "approval_required": False,
        "rate_limit_per_min": MCP_RATE_LIMIT_PER_MIN, "cost_behavior": "none", "timeout_seconds": 10,
        "idempotent": True, "input_schema": {},
    },
    {
        "name": "get_pipeline_summary", "level": 1, "version": "1.0.0", "provider": "ClientVerse", "publisher": "ClientVerse",
        "category": "revenue", "description": "Return pipeline funnel counts and open pipeline value.",
        "scopes": ["opportunities:read"], "records_read": ["opportunity"], "records_written": [],
        "tenant_scoped": True, "workspace_scoped": False, "approval_required": False,
        "rate_limit_per_min": MCP_RATE_LIMIT_PER_MIN, "cost_behavior": "none", "timeout_seconds": 10,
        "idempotent": True, "input_schema": {},
    },
    {
        "name": "list_tasks", "level": 1, "version": "1.0.0", "provider": "ClientVerse", "publisher": "ClientVerse",
        "category": "client_operations", "description": "List delivery tasks, optionally scoped to a workspace.",
        "scopes": ["tasks:read"], "records_read": ["task"], "records_written": [],
        "tenant_scoped": True, "workspace_scoped": True, "approval_required": False,
        "rate_limit_per_min": MCP_RATE_LIMIT_PER_MIN, "cost_behavior": "none", "timeout_seconds": 10,
        "idempotent": True, "input_schema": {"workspace_id": {"type": "workspace", "required": False}},
    },
    {
        "name": "create_task", "level": 2, "version": "1.0.0", "provider": "ClientVerse", "publisher": "ClientVerse",
        "category": "client_operations", "description": "Create a delivery task in a workspace (reversible). Requires approval.",
        "scopes": ["tasks:write"], "records_read": [], "records_written": ["task"],
        "tenant_scoped": True, "workspace_scoped": True, "approval_required": True,
        "rate_limit_per_min": MCP_RATE_LIMIT_PER_MIN, "cost_behavior": "none", "timeout_seconds": 10,
        "idempotent": False, "reversible": True,
        "input_schema": {"workspace_id": {"type": "workspace", "required": True}, "title": {"type": "string", "required": True, "placeholder": "Task title"}},
    },
    {
        "name": "add_note", "level": 2, "version": "1.0.0", "provider": "ClientVerse", "publisher": "ClientVerse",
        "category": "client_operations", "description": "Add an internal note to a workspace (reversible). Requires approval.",
        "scopes": ["notes:write"], "records_read": [], "records_written": ["note"],
        "tenant_scoped": True, "workspace_scoped": True, "approval_required": True,
        "rate_limit_per_min": MCP_RATE_LIMIT_PER_MIN, "cost_behavior": "none", "timeout_seconds": 10,
        "idempotent": False, "reversible": True,
        "input_schema": {"workspace_id": {"type": "workspace", "required": True}, "body": {"type": "string", "required": True, "placeholder": "Note text"}},
    },
]
MCP_TOOLS = {t["name"]: t for t in MCP_TOOL_CATALOG}


async def _tool_search_contacts(user, args):
    q = (args.get("query") or "").strip().lower()
    rows = await db.contacts.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).to_list(2000)
    if q:
        rows = [r for r in rows if q in f"{r.get('name','')} {r.get('email','')} {r.get('role','')}".lower()]
    return {"count": len(rows), "contacts": rows[:25]}

async def _tool_get_client_health(user, args):
    wid = args.get("workspace_id")
    ws = await db.workspaces.find_one({"id": wid, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not ws:
        raise ValueError("workspace_id not found in this tenant")
    scoped = {"tenant_id": user["tenant_id"], "workspace_id": wid}
    commitments = await db.commitments.find(scoped, {"_id": 0}).to_list(500)
    tasks = await db.tasks.find(scoped, {"_id": 0}).to_list(500)
    dl = await db.deliverables.find(scoped, {"_id": 0}).to_list(500)
    rq = await db.client_requests.find(scoped, {"_id": 0}).to_list(500)
    return {"workspace": ws["name"], "health": compute_health(commitments, tasks, dl, rq)}

async def _tool_list_open_commitments(user, args):
    rows = await db.commitments.find({"tenant_id": user["tenant_id"], "status": {"$in": ["open", "at_risk", "breached"]}}, {"_id": 0}).to_list(500)
    return {"count": len(rows), "commitments": rows}

async def _tool_get_pipeline_summary(user, args):
    opps = await db.opportunities.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).to_list(2000)
    funnel = {s: len([o for o in opps if o.get("stage") == s]) for s in STAGES}
    return {"funnel": funnel, "open_value": sum(o.get("value", 0) for o in opps if o.get("stage") not in ("closed_won", "closed_lost"))}

async def _tool_list_tasks(user, args):
    q = {"tenant_id": user["tenant_id"]}
    if args.get("workspace_id"):
        q["workspace_id"] = args["workspace_id"]
    rows = await db.tasks.find(q, {"_id": 0}).to_list(500)
    return {"count": len(rows), "tasks": rows}

TOOL_IMPL = {
    "search_contacts": _tool_search_contacts,
    "get_client_health": _tool_get_client_health,
    "list_open_commitments": _tool_list_open_commitments,
    "get_pipeline_summary": _tool_get_pipeline_summary,
    "list_tasks": _tool_list_tasks,
}

# Level 2 — reversible internal writes (executed only after approval)
async def _tool_create_task(user, args):
    tid = new_id("task")
    doc = {"id": tid, "tenant_id": user["tenant_id"], "workspace_id": args["workspace_id"],
           "title": args["title"], "assignee": user["email"], "due_date": None,
           "status": "todo", "created_at": now_iso(), "source": "mcp"}
    await db.tasks.insert_one(dict(doc))
    await record_event("task.created", "task", tid, user["tenant_id"], user["email"],
                       workspace_id=args["workspace_id"], payload={"title": args["title"], "via": "mcp"})
    return {"created": "task", "id": tid, "reversible": True, "undo": f"delete task {tid}"}

async def _tool_add_note(user, args):
    nid = new_id("note")
    doc = {"id": nid, "tenant_id": user["tenant_id"], "workspace_id": args["workspace_id"],
           "body": args["body"], "author": user["email"], "created_at": now_iso(), "source": "mcp"}
    await db.notes.insert_one(dict(doc))
    await record_event("note.created", "note", nid, user["tenant_id"], user["email"],
                       workspace_id=args["workspace_id"], payload={"via": "mcp"})
    return {"created": "note", "id": nid, "reversible": True, "undo": f"delete note {nid}"}

TOOL_IMPL_L2 = {"create_task": _tool_create_task, "add_note": _tool_add_note}

async def execute_pending_mcp(pending_id, user):
    p = await db.mcp_pending_actions.find_one({"id": pending_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not p or p.get("status") != "pending_approval":
        return {"status": "skipped"}
    inv_id = p["invocation_id"]
    tool = MCP_TOOLS.get(p["tool"])
    start = time.perf_counter()
    try:
        result = await asyncio.wait_for(TOOL_IMPL_L2[p["tool"]](user, p["args"]), timeout=tool["timeout_seconds"])
        latency = int((time.perf_counter() - start) * 1000)
        await db.mcp_pending_actions.update_one({"id": pending_id}, {"$set": {"status": "executed"}})
        await db.mcp_tool_invocations.update_one({"id": inv_id}, {"$set": {"status": "success", "result": result, "latency_ms": latency, "executed_at": now_iso()}})
        await record_event("agent.run_completed", "mcp_tool", p["tool"], user["tenant_id"], user["email"],
                           workspace_id=p.get("workspace_id"), payload={"invocation_id": inv_id, "executed_after_approval": True})
        return {"status": "success", "result": result, "invocation_id": inv_id}
    except Exception as e:
        await db.mcp_pending_actions.update_one({"id": pending_id}, {"$set": {"status": "failed"}})
        await db.mcp_tool_invocations.update_one({"id": inv_id}, {"$set": {"status": "failed", "error": str(e)}})
        await record_event("mcp.tool_failed", "mcp_tool", p["tool"], user["tenant_id"], user["email"],
                           workspace_id=p.get("workspace_id"), payload={"invocation_id": inv_id, "error": str(e)})
        return {"status": "failed", "error": str(e)}


async def get_mcp_server(tenant_id):
    doc = await db.mcp_server_state.find_one({"server_id": MCP_SERVER_ID, "tenant_id": tenant_id}, {"_id": 0})
    if not doc:
        doc = {"server_id": MCP_SERVER_ID, "tenant_id": tenant_id, "name": "ClientVerse Read Tools",
               "version": "1.0.0", "level": 1, "status": "AVAILABLE", "kill_switch": False,
               "allowlist": list(MCP_TOOLS.keys()), "created_at": now_iso()}
        await db.mcp_server_state.insert_one(dict(doc))
    return doc

@api.get("/mcp/server")
async def mcp_server(user=Depends(get_current_user)):
    return await get_mcp_server(user["tenant_id"])

@api.get("/mcp/tools")
async def mcp_tools(user=Depends(get_current_user)):
    server = await get_mcp_server(user["tenant_id"])
    return {"server": server, "tools": MCP_TOOL_CATALOG}

class KillInput(BaseModel):
    enabled: bool

@api.patch("/mcp/server/kill")
async def mcp_kill(inp: KillInput, user=Depends(require_role("admin"))):
    await get_mcp_server(user["tenant_id"])
    await db.mcp_server_state.update_one({"server_id": MCP_SERVER_ID, "tenant_id": user["tenant_id"]},
                                         {"$set": {"kill_switch": inp.enabled}})
    await record_event("plugin.disabled" if inp.enabled else "integration.connected", "mcp_server", MCP_SERVER_ID,
                       user["tenant_id"], user["email"], payload={"kill_switch": inp.enabled})
    return {"ok": True, "kill_switch": inp.enabled}

class InvokeInput(BaseModel):
    tool: str
    args: dict = {}
    idempotency_key: Optional[str] = None

@api.post("/mcp/invoke")
async def mcp_invoke(inp: InvokeInput, user=Depends(get_current_user)):
    tenant = user["tenant_id"]
    correlation_id = new_id("cor")
    inv_id = new_id("mcpinv")

    async def fail(status_code, reason, level=None):
        await db.mcp_tool_invocations.insert_one({
            "id": inv_id, "tenant_id": tenant, "tool": inp.tool, "level": level, "args": inp.args,
            "status": "failed", "error": reason, "latency_ms": 0, "correlation_id": correlation_id,
            "actor": user["email"], "timestamp": now_iso(), "idempotency_key": inp.idempotency_key,
        })
        await record_event("mcp.tool_failed", "mcp_tool", inp.tool, tenant, user["email"],
                           payload={"reason": reason, "invocation_id": inv_id})
        raise HTTPException(status_code=status_code, detail=reason)

    tool = MCP_TOOLS.get(inp.tool)
    if not tool:
        await fail(400, f"Tool '{inp.tool}' is not allowlisted on this MCP server")
    if tool["level"] > 2:
        await fail(403, "Level 3+ tools are not enabled for execution", tool["level"])

    server = await get_mcp_server(tenant)
    if server.get("kill_switch"):
        await fail(423, "MCP server is disabled by kill switch", tool["level"])
    if inp.tool not in server.get("allowlist", []):
        await fail(403, "Tool not in tenant allowlist", tool["level"])

    # required arg validation
    for field, spec in tool["input_schema"].items():
        if spec.get("required") and not inp.args.get(field):
            await fail(422, f"Missing required argument: {field}", tool["level"])

    # idempotency
    if inp.idempotency_key:
        prior = await db.mcp_tool_invocations.find_one(
            {"tenant_id": tenant, "idempotency_key": inp.idempotency_key, "status": "success"}, {"_id": 0})
        if prior:
            return {**prior, "idempotent_replay": True}

    # rate limit
    since = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    recent = await db.mcp_tool_invocations.count_documents(
        {"tenant_id": tenant, "tool": inp.tool, "timestamp": {"$gte": since}})
    if recent >= tool["rate_limit_per_min"]:
        await fail(429, "Rate limit exceeded for this tool", tool["level"])

    # Level 2 — reversible write gated behind an approval request
    if tool["level"] == 2:
        pending_id = new_id("mcpp")
        approval_id = new_id("apr")
        ws_id = inp.args.get("workspace_id")
        await db.mcp_pending_actions.insert_one({
            "id": pending_id, "tenant_id": tenant, "tool": inp.tool, "args": inp.args,
            "status": "pending_approval", "approval_id": approval_id, "workspace_id": ws_id,
            "invocation_id": inv_id, "created_by": user["email"], "created_at": now_iso(),
        })
        await db.approvals.insert_one({
            "id": approval_id, "tenant_id": tenant, "workspace_id": ws_id,
            "title": f"MCP write: {inp.tool}", "kind": "mcp_write", "status": "requested",
            "pending_action_id": pending_id, "created_at": now_iso(),
        })
        await db.mcp_tool_invocations.insert_one({
            "id": inv_id, "tenant_id": tenant, "tool": inp.tool, "level": 2, "args": inp.args,
            "status": "pending_approval", "result": None, "error": None, "latency_ms": 0,
            "correlation_id": correlation_id, "actor": user["email"], "timestamp": now_iso(),
            "idempotency_key": inp.idempotency_key, "approval_id": approval_id,
        })
        await record_event("mcp.tool_invoked", "mcp_tool", inp.tool, tenant, user["email"],
                           workspace_id=ws_id, payload={"invocation_id": inv_id, "level": 2, "status": "pending_approval"})
        await record_event("approval.requested", "approval", approval_id, tenant, user["email"],
                           workspace_id=ws_id, payload={"title": f"MCP write: {inp.tool}"})
        return {"id": inv_id, "tool": inp.tool, "level": 2, "status": "pending_approval",
                "approval_id": approval_id, "message": "Approval required — approve in the client workspace to execute."}

    await record_event("mcp.tool_invoked", "mcp_tool", inp.tool, tenant, user["email"],
                       payload={"invocation_id": inv_id, "level": tool["level"]})
    start = time.perf_counter()
    try:
        result = await asyncio.wait_for(TOOL_IMPL[inp.tool](user, inp.args), timeout=tool["timeout_seconds"])
        latency = int((time.perf_counter() - start) * 1000)
        record = {
            "id": inv_id, "tenant_id": tenant, "tool": inp.tool, "level": tool["level"], "args": inp.args,
            "status": "success", "result": result, "error": None, "latency_ms": latency,
            "correlation_id": correlation_id, "actor": user["email"], "timestamp": now_iso(),
            "idempotency_key": inp.idempotency_key,
            "policy": {"scopes": tool["scopes"], "approval_required": tool["approval_required"], "timeout_seconds": tool["timeout_seconds"]},
        }
        await db.mcp_tool_invocations.insert_one(dict(record))
        return record
    except asyncio.TimeoutError:
        await fail(504, "Tool execution timed out", tool["level"])
    except Exception as e:
        await fail(502, f"Tool execution error: {e}", tool["level"])

@api.get("/mcp/invocations")
async def mcp_invocations(limit: int = Query(100), user=Depends(get_current_user)):
    docs = await db.mcp_tool_invocations.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return docs

UNDO_WINDOW_MINUTES = 60

class UndoInput(BaseModel):
    reason: str = ""

@api.post("/mcp/invocations/{inv_id}/undo")
async def mcp_undo(inv_id: str, inp: UndoInput, user=Depends(require_role("admin"))):
    reason = (inp.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A reason is required to reverse an action")
    inv = await db.mcp_tool_invocations.find_one({"id": inv_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Not found")
    if inv.get("level") != 2 or inv.get("status") != "success":
        raise HTTPException(status_code=400, detail="Only successful Level 2 writes can be undone")
    if inv.get("undone"):
        raise HTTPException(status_code=400, detail="Already undone")
    ws_id = (inv.get("args") or {}).get("workspace_id")
    window_min = UNDO_WINDOW_MINUTES
    if ws_id:
        wsd = await db.workspaces.find_one({"id": ws_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if wsd and wsd.get("undo_window_minutes"):
            window_min = wsd["undo_window_minutes"]
    ref = inv.get("executed_at") or inv.get("timestamp")
    try:
        ref_dt = datetime.fromisoformat(ref)
        if ref_dt.tzinfo is None:
            ref_dt = ref_dt.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - ref_dt > timedelta(minutes=window_min):
            raise HTTPException(status_code=400, detail=f"Undo window ({window_min} min) has expired")
    except HTTPException:
        raise
    except Exception:
        pass
    result = inv.get("result") or {}
    created, rid = result.get("created"), result.get("id")
    ws_id = (inv.get("args") or {}).get("workspace_id")
    if created == "task" and rid:
        await db.tasks.delete_one({"id": rid, "tenant_id": user["tenant_id"]})
        restored = f"Removed task {rid}"
    elif created == "note" and rid:
        await db.notes.delete_one({"id": rid, "tenant_id": user["tenant_id"]})
        restored = f"Removed note {rid}"
    else:
        raise HTTPException(status_code=400, detail="This action is not reversible")
    await db.mcp_tool_invocations.update_one({"id": inv_id}, {"$set": {"undone": True, "status": "undone", "undone_by": user["email"], "undone_at": now_iso(), "undo_reason": reason}})
    await record_event("mcp.tool_undone", "mcp_tool", inv["tool"], user["tenant_id"], user["email"], workspace_id=ws_id, payload={"invocation_id": inv_id, "restored": restored, "reason": reason})
    return {"ok": True, "restored": restored, "reason": reason}

class UndoWindowInput(BaseModel):
    minutes: int

@api.patch("/workspaces/{ws_id}/undo-window")
async def set_undo_window(ws_id: str, inp: UndoWindowInput, user=Depends(require_role("admin"))):
    ws = await db.workspaces.find_one({"id": ws_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=404, detail="Not found")
    m = max(1, min(1440, inp.minutes))
    await db.workspaces.update_one({"id": ws_id}, {"$set": {"undo_window_minutes": m}})
    return {"ok": True, "undo_window_minutes": m}

# ----------------------------- Webhooks (live signed delivery) -----------------------------

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

class WebhookInput(BaseModel):
    name: str
    url: str
    events: List[str] = []

class WebhookPatch(BaseModel):
    enabled: Optional[bool] = None
    rotate_secret: Optional[bool] = None

@api.get("/webhooks")
async def list_webhooks(user=Depends(get_current_user)):
    return await db.webhooks.find({"tenant_id": user["tenant_id"]}, {"_id": 0, "secret": 0}).sort("created_at", -1).to_list(200)

@api.get("/webhooks/{wid}/secret")
async def reveal_webhook_secret(wid: str, user=Depends(require_role("admin"))):
    wh = await db.webhooks.find_one({"id": wid, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not wh:
        raise HTTPException(status_code=404, detail="Not found")
    await record_event("webhook.secret_revealed", "webhook", wid, user["tenant_id"], user["email"], payload={"name": wh.get("name")})
    return {"id": wid, "secret": wh.get("secret")}

@api.post("/webhooks")
async def create_webhook(inp: WebhookInput, user=Depends(require_role("admin"))):
    doc = {"id": new_id("wh"), "tenant_id": user["tenant_id"], "name": inp.name, "url": inp.url,
           "events": inp.events, "status": "AVAILABLE", "signed": True, "enabled": True,
           "secret": "whsec_" + secrets.token_hex(16), "description": "Custom endpoint.", "created_at": now_iso()}
    await db.webhooks.insert_one(dict(doc))
    await record_event("integration.connected", "webhook", doc["id"], user["tenant_id"], user["email"], payload={"name": inp.name})
    return {k: v for k, v in doc.items() if k != "_id"}

@api.patch("/webhooks/{wid}")
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

@api.post("/webhooks/{wid}/test")
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

@api.get("/webhook-deliveries")
async def list_deliveries(limit: int = Query(100), user=Depends(get_current_user)):
    return await db.webhook_deliveries.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("created_at", -1).to_list(limit)

@api.post("/webhook-deliveries/{did}/replay")
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

@api.post("/webhooks/sink")
async def webhook_sink(request: Request):
    _ = await request.body()
    return {"received": True}

class PreviewInput(BaseModel):
    patterns: List[str] = []

@api.post("/webhooks/match-preview")
async def webhook_match_preview(inp: PreviewInput, user=Depends(get_current_user)):
    events = await db.domain_events.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("timestamp", -1).to_list(100)
    matched = [e for e in events if event_matches(e["event_type"], inp.patterns)]
    counts = {}
    for e in matched:
        counts[e["event_type"]] = counts.get(e["event_type"], 0) + 1
    by_type = sorted([{"event_type": k, "count": v} for k, v in counts.items()], key=lambda x: -x["count"])
    return {"scanned": len(events), "matched": len(matched), "by_type": by_type,
            "samples": [{"event_type": e["event_type"], "timestamp": e["timestamp"], "actor": e["actor"]} for e in matched[:8]]}

# ----------------------------- Client Outcome Graph -----------------------------

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

async def snapshot_outcome(o):
    if not o.get("target_value"):
        return
    pct = min(100, round((o.get("current_value", 0) / o["target_value"]) * 100))
    await db.outcome_snapshots.insert_one({"id": new_id("os"), "tenant_id": o["tenant_id"], "outcome_id": o["id"], "pct": pct, "at": now_iso()})

class OutcomeInput(BaseModel):
    workspace_id: str
    title: str
    target: Optional[str] = None
    target_value: Optional[float] = None
    current_value: float = 0
    unit: Optional[str] = None
    status: str = "on_track"
    linked_commitment_ids: List[str] = []

class OutcomePatch(BaseModel):
    current_value: Optional[float] = None
    target_value: Optional[float] = None
    status: Optional[str] = None
    title: Optional[str] = None

@api.patch("/outcomes/{oid}")
async def update_outcome(oid: str, inp: OutcomePatch, user=Depends(get_current_user)):
    o = await db.outcomes.find_one({"id": oid, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not o:
        raise HTTPException(status_code=404, detail="Not found")
    upd = {k: v for k, v in inp.model_dump().items() if v is not None}
    if upd:
        await db.outcomes.update_one({"id": oid}, {"$set": upd})
        await record_event("health.factor_changed", "outcome", oid, user["tenant_id"], user["email"], workspace_id=o["workspace_id"], payload={"updated": list(upd.keys())})
    return {"ok": True, **upd}

@api.post("/outcomes")
async def create_outcome(inp: OutcomeInput, user=Depends(get_current_user)):
    await assert_workspace(user, inp.workspace_id)
    doc = {"id": new_id("out"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.outcomes.insert_one(dict(doc))
    await snapshot_outcome(doc)
    await record_event("health.factor_changed", "outcome", doc["id"], user["tenant_id"], user["email"],
                       workspace_id=inp.workspace_id, payload={"title": inp.title})
    return {k: v for k, v in doc.items() if k != "_id"}

@api.get("/workspaces/{ws_id}/outcome-graph")
async def outcome_graph(ws_id: str, user=Depends(get_current_user)):
    ws = await db.workspaces.find_one({"id": ws_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=404, detail="Not found")
    scoped = {"tenant_id": user["tenant_id"], "workspace_id": ws_id}
    goals = await db.outcomes.find(scoped, {"_id": 0}).to_list(200)
    commitments = await db.commitments.find(scoped, {"_id": 0}).to_list(500)
    tasks = await db.tasks.find(scoped, {"_id": 0}).to_list(500)
    dl = await db.deliverables.find(scoped, {"_id": 0}).to_list(500)
    rq = await db.client_requests.find(scoped, {"_id": 0}).to_list(500)
    health = compute_health(commitments, tasks, dl, rq)
    history = await db.health_snapshots.find(scoped, {"_id": 0}).sort("at", 1).to_list(200)
    return {"workspace": ws, "goals": goals, "commitments": commitments, "health": health, "health_history": history}

@api.post("/cron/commitment-risk")
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

# ============================================================================
#  LIVE INTEGRATIONS V1 — providers, secure credential storage, sync engine
# ============================================================================
import json as _json
import httpx
import stripe as _stripe
from cryptography.fernet import Fernet

PROVIDERS = ["gmail", "google_calendar", "stripe"]
ADAPTER_VERSION = "1.0"
CONN_STATUSES = ["disconnected", "connecting", "active", "degraded", "expired", "revoked", "error"]
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
# Prefer an explicit redirect URI; otherwise derive from the public backend URL (not the frontend).
_PUBLIC_BACKEND = (os.environ.get("PUBLIC_BACKEND_URL") or "").rstrip("/")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI") or (
    f"{_PUBLIC_BACKEND}/api/integrations/google/callback" if _PUBLIC_BACKEND else None
)
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

_FERNET = None
def _fernet():
    global _FERNET
    if _FERNET is None:
        key = os.environ.get("INTEGRATION_ENC_KEY")
        if not key:
            raise HTTPException(status_code=500, detail="Secure credential storage not configured (INTEGRATION_ENC_KEY)")
        _FERNET = Fernet(key.encode())
    return _FERNET

def enc_secret(d: dict) -> str:
    return _fernet().encrypt(_json.dumps(d).encode()).decode()

def dec_secret(s: str) -> dict:
    return _json.loads(_fernet().decrypt(s.encode()).decode())

SAFE_CONN_FIELDS = {"_id": 0, "enc": 0, "oauth_state": 0, "code_verifier": 0}

def _public_conn(c: dict) -> dict:
    return {k: v for k, v in c.items() if k not in ("_id", "enc", "oauth_state", "code_verifier")}

async def ensure_connections(tenant_id: str):
    for p in PROVIDERS:
        if not await db.integration_connections.find_one({"tenant_id": tenant_id, "provider": p}):
            await db.integration_connections.insert_one({
                "id": new_id("conn"), "tenant_id": tenant_id, "provider": p, "status": "disconnected",
                "account_identity": None, "scopes": [], "connected_by": None, "connected_at": None,
                "last_sync_at": None, "last_success_at": None, "last_error": None, "revoked_at": None,
                "credential_version": 0, "adapter_version": ADAPTER_VERSION, "created_at": now_iso(),
            })

async def set_conn(tenant_id, provider, **fields):
    await db.integration_connections.update_one({"tenant_id": tenant_id, "provider": provider}, {"$set": fields})

async def _contacts_by_email(tenant_id):
    rows = await db.contacts.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(5000)
    return {(r.get("email") or "").lower(): r for r in rows if r.get("email")}

async def _workspace_for_company(tenant_id, company_id):
    if not company_id:
        return None
    ws = await db.workspaces.find_one({"tenant_id": tenant_id, "company_id": company_id}, {"_id": 0, "id": 1})
    return ws["id"] if ws else None

# ---- Pure normalizers (unit-testable, no network) ----

def normalize_gmail_message(msg: dict) -> dict:
    headers = {h.get("name", "").lower(): h.get("value", "") for h in (msg.get("payload", {}).get("headers") or [])}
    ts = None
    if msg.get("internalDate"):
        try:
            ts = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc).isoformat()
        except Exception:
            ts = None
    def _emails(v):
        import re
        return [e.lower() for e in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", v or "")]
    return {
        "external_id": msg.get("id"), "thread_id": msg.get("threadId"),
        "subject": headers.get("subject", "(no subject)"),
        "from_email": (_emails(headers.get("from")) or [None])[0], "from_raw": headers.get("from"),
        "to": _emails(headers.get("to")) + _emails(headers.get("cc")),
        "labels": msg.get("labelIds") or [], "snippet": msg.get("snippet", ""), "ts": ts,
    }

def normalize_calendar_event(ev: dict) -> dict:
    start = (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date")
    end = (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date")
    org = (ev.get("organizer") or {}).get("email")
    attendees = [(a.get("email") or "").lower() for a in (ev.get("attendees") or []) if a.get("email")]
    conf = None
    ep = (ev.get("conferenceData") or {}).get("entryPoints") or []
    for e in ep:
        if e.get("uri"):
            conf = e["uri"]; break
    conf = conf or ev.get("hangoutLink")
    return {
        "external_id": ev.get("id"), "title": ev.get("summary", "(untitled)"),
        "start": start, "end": end, "organizer": (org or "").lower() or None,
        "attendees": attendees, "conference_link": conf, "status": ev.get("status"),
    }

def normalize_stripe_customer(c) -> dict:
    return {"external_id": c.get("id"), "type": "customer", "email": (c.get("email") or "").lower() or None,
            "name": c.get("name"), "status": "active", "amount": None, "currency": c.get("currency"),
            "ts": datetime.fromtimestamp(c.get("created", 0), tz=timezone.utc).isoformat() if c.get("created") else None}

def normalize_stripe_invoice(inv) -> dict:
    return {"external_id": inv.get("id"), "type": "invoice", "email": (inv.get("customer_email") or "").lower() or None,
            "status": inv.get("status"), "amount": (inv.get("amount_due") or 0) / 100.0, "currency": inv.get("currency"),
            "payment_status": "paid" if inv.get("paid") else (inv.get("status") or "open"),
            "ts": datetime.fromtimestamp(inv.get("created", 0), tz=timezone.utc).isoformat() if inv.get("created") else None}

def normalize_stripe_subscription(sub) -> dict:
    return {"external_id": sub.get("id"), "type": "subscription", "email": None,
            "status": sub.get("status"), "amount": None,
            "currency": (sub.get("items", {}).get("data", [{}])[0].get("price", {}) or {}).get("currency"),
            "customer": sub.get("customer"),
            "ts": datetime.fromtimestamp(sub.get("created", 0), tz=timezone.utc).isoformat() if sub.get("created") else None}

# ---- Google token helpers ----

async def _google_creds(tenant_id):
    doc = await db.google_credentials.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if not doc:
        return None
    return dec_secret(doc["enc"]), doc

async def _google_access_token(tenant_id):
    creds, doc = (await _google_creds(tenant_id)) or (None, None)
    if not creds:
        return None
    exp = creds.get("expires_at", 0)
    if datetime.now(timezone.utc).timestamp() < exp - 60:
        return creds["access_token"]
    # refresh
    if not creds.get("refresh_token"):
        return None
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": creds["refresh_token"], "grant_type": "refresh_token"})
    if r.status_code != 200:
        raise RuntimeError(f"token_refresh_failed:{r.status_code}")
    tok = r.json()
    creds["access_token"] = tok["access_token"]
    creds["expires_at"] = datetime.now(timezone.utc).timestamp() + tok.get("expires_in", 3600)
    await db.google_credentials.update_one({"tenant_id": tenant_id},
        {"$set": {"enc": enc_secret(creds), "updated_at": now_iso()}})
    return creds["access_token"]

# ---- Adapters (sync returns a normalized summary; bounded, idempotent upserts) ----

async def _upsert_comm(tenant_id, rec, contacts, actor_provider="gmail"):
    matched = [contacts[e] for e in ([rec.get("from_email")] + rec.get("to", [])) if e and e in contacts]
    contact_ids = list({m["id"] for m in matched})
    if not contact_ids:
        return False
    company_id = next((m.get("company_id") for m in matched if m.get("company_id")), None)
    ws_id = await _workspace_for_company(tenant_id, company_id)
    doc = {"tenant_id": tenant_id, "provider": actor_provider, "external_id": rec["external_id"],
           "thread_id": rec.get("thread_id"), "subject": rec["subject"], "from_email": rec.get("from_email"),
           "to": rec.get("to"), "snippet": rec.get("snippet"), "labels": rec.get("labels"), "ts": rec.get("ts"),
           "contact_ids": contact_ids, "company_id": company_id, "workspace_id": ws_id, "source": "external",
           "synced_at": now_iso()}
    await db.crm_communications.update_one(
        {"tenant_id": tenant_id, "provider": actor_provider, "external_id": rec["external_id"]},
        {"$set": doc, "$setOnInsert": {"id": new_id("comm")}}, upsert=True)
    return True

async def sync_gmail(tenant_id, actor):
    token = await _google_access_token(tenant_id)
    if not token:
        raise RuntimeError("not_connected")
    contacts = await _contacts_by_email(tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    matched = 0
    async with httpx.AsyncClient(timeout=25) as client:
        lst = await client.get("https://gmail.googleapis.com/gmail/v1/users/me/messages",
                               params={"maxResults": 25}, headers=headers)
        if lst.status_code == 429:
            raise RuntimeError("rate_limited")
        lst.raise_for_status()
        for m in (lst.json().get("messages") or [])[:25]:
            gm = await client.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}",
                                  params={"format": "metadata", "metadataHeaders": ["From", "To", "Cc", "Subject"]},
                                  headers=headers)
            if gm.status_code != 200:
                continue
            if await _upsert_comm(tenant_id, normalize_gmail_message(gm.json()), contacts, "gmail"):
                matched += 1
    return {"scanned": 25, "matched": matched}

async def sync_calendar(tenant_id, actor):
    token = await _google_access_token(tenant_id)
    if not token:
        raise RuntimeError("not_connected")
    contacts = await _contacts_by_email(tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    matched = 0
    now = datetime.now(timezone.utc).isoformat()
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.get("https://www.googleapis.com/calendar/v3/calendars/primary/events",
                             params={"timeMin": now, "maxResults": 25, "singleEvents": "true", "orderBy": "startTime"},
                             headers=headers)
        if r.status_code == 429:
            raise RuntimeError("rate_limited")
        r.raise_for_status()
        for ev in (r.json().get("items") or [])[:25]:
            rec = normalize_calendar_event(ev)
            emails = rec["attendees"] + ([rec["organizer"]] if rec["organizer"] else [])
            mm = [contacts[e] for e in emails if e in contacts]
            if not mm:
                continue
            company_id = next((m.get("company_id") for m in mm if m.get("company_id")), None)
            ws_id = await _workspace_for_company(tenant_id, company_id)
            doc = {"tenant_id": tenant_id, "provider": "google_calendar", **rec,
                   "contact_ids": list({m["id"] for m in mm}), "company_id": company_id,
                   "workspace_id": ws_id, "source": "external", "synced_at": now_iso()}
            await db.crm_meetings.update_one(
                {"tenant_id": tenant_id, "external_id": rec["external_id"]},
                {"$set": doc, "$setOnInsert": {"id": new_id("mtg")}}, upsert=True)
            matched += 1
    return {"scanned": 25, "matched": matched}

async def sync_stripe(tenant_id, actor):
    key = os.environ.get("STRIPE_API_KEY")
    if not key:
        raise RuntimeError("not_connected")
    _stripe.api_key = key
    contacts = await _contacts_by_email(tenant_id)
    companies = {c["id"]: c for c in await db.companies.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(5000)}
    count = 0
    def match(email):
        c = contacts.get((email or "").lower())
        return (c["id"] if c else None, c.get("company_id") if c else None)
    for norm, items in [
        (normalize_stripe_customer, _stripe.Customer.list(limit=50).data),
        (normalize_stripe_invoice, _stripe.Invoice.list(limit=50).data),
        (normalize_stripe_subscription, _stripe.Subscription.list(limit=50).data),
    ]:
        for it in items:
            rec = norm(it)
            contact_id, company_id = match(rec.get("email"))
            ws_id = await _workspace_for_company(tenant_id, company_id)
            doc = {"tenant_id": tenant_id, "provider": "stripe", **rec, "contact_id": contact_id,
                   "company_id": company_id, "workspace_id": ws_id, "source": "external", "synced_at": now_iso()}
            await db.crm_billing.update_one(
                {"tenant_id": tenant_id, "type": rec["type"], "external_id": rec["external_id"]},
                {"$set": doc, "$setOnInsert": {"id": new_id("bill")}}, upsert=True)
            count += 1
    return {"scanned": count, "matched": count}

SYNC_FUNCS = {"gmail": sync_gmail, "google_calendar": sync_calendar, "stripe": sync_stripe}

async def run_sync(tenant_id, provider, actor):
    conn = await db.integration_connections.find_one({"tenant_id": tenant_id, "provider": provider}, {"_id": 0})
    if not conn or conn["status"] in ("disconnected", "revoked"):
        raise HTTPException(status_code=400, detail="Provider is not connected")
    await set_conn(tenant_id, provider, status="connecting")
    await record_event("integration.sync_started", "integration", provider, tenant_id, actor, payload={"provider": provider})
    log = {"id": new_id("synclog"), "tenant_id": tenant_id, "provider": provider, "started_at": now_iso(),
           "actor": actor, "attempts": 0, "status": "running", "result": None, "error": None}
    last_err = None
    for attempt in range(1, 4):  # bounded retries with backoff
        log["attempts"] = attempt
        try:
            summary = await SYNC_FUNCS[provider](tenant_id, actor)
            log.update({"status": "completed", "result": summary, "finished_at": now_iso()})
            await db.integration_sync_logs.insert_one(dict(log))
            await set_conn(tenant_id, provider, status="active", last_sync_at=now_iso(),
                           last_success_at=now_iso(), last_error=None)
            await record_event("integration.sync_completed", "integration", provider, tenant_id, actor, payload=summary)
            return {**summary, "status": "completed"}
        except HTTPException:
            raise
        except Exception as e:
            last_err = str(e)[:300]
            if "rate_limited" in last_err:
                await asyncio.sleep(min(2 ** attempt, 5))
                continue
            if "not_connected" in last_err:
                break
            await asyncio.sleep(min(0.5 * attempt, 2))
    log.update({"status": "failed", "error": last_err, "finished_at": now_iso()})
    await db.integration_sync_logs.insert_one(dict(log))
    status = "expired" if last_err and "token_refresh_failed" in last_err else "degraded"
    await set_conn(tenant_id, provider, status=status, last_sync_at=now_iso(), last_error=last_err)
    await record_event("integration.sync_failed", "integration", provider, tenant_id, actor,
                       payload={"provider": provider, "error": last_err})
    return {"status": "failed", "error": last_err}

# ---- Endpoints ----

@api.get("/integrations/connections")
async def list_connections(user=Depends(get_current_user)):
    await ensure_connections(user["tenant_id"])
    rows = await db.integration_connections.find({"tenant_id": user["tenant_id"]}, SAFE_CONN_FIELDS).to_list(50)
    return rows

@api.post("/integrations/google/connect")
async def google_connect(user=Depends(require_role("admin"))):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.")
    if not GOOGLE_REDIRECT_URI:
        raise HTTPException(
            status_code=400,
            detail="Google OAuth redirect is not configured. Set GOOGLE_REDIRECT_URI or PUBLIC_BACKEND_URL.",
        )
    await ensure_connections(user["tenant_id"])
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    await db.oauth_states.insert_one({"state": state, "tenant_id": user["tenant_id"], "actor": user["email"],
        "code_verifier": verifier, "created_at": now_iso(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()})
    for p in ("gmail", "google_calendar"):
        await set_conn(user["tenant_id"], p, status="connecting")
    params = {"client_id": GOOGLE_CLIENT_ID, "redirect_uri": GOOGLE_REDIRECT_URI, "response_type": "code",
              "scope": " ".join(GOOGLE_SCOPES), "access_type": "offline", "prompt": "consent",
              "include_granted_scopes": "true", "state": state,
              "code_challenge": challenge, "code_challenge_method": "S256"}
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return {"authorization_url": url}

@api.get("/integrations/google/callback")
async def google_callback(state: str = Query(None), code: str = Query(None), error: str = Query(None)):
    dest = f"{FRONTEND_URL}/registries?tab=integrations"
    st = await db.oauth_states.find_one({"state": state}, {"_id": 0}) if state else None
    if error or not st or not code:
        return RedirectResponse(url=f"{dest}&oauth=error")
    try:
        exp_dt = datetime.fromisoformat(st["expires_at"])
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        if exp_dt < datetime.now(timezone.utc):
            return RedirectResponse(url=f"{dest}&oauth=expired")
    except Exception:
        pass
    await db.oauth_states.delete_one({"state": state})
    tenant_id, actor = st["tenant_id"], st["actor"]
    async with httpx.AsyncClient(timeout=20) as client:
        tr = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET, "code": code,
            "grant_type": "authorization_code", "redirect_uri": GOOGLE_REDIRECT_URI,
            "code_verifier": st["code_verifier"]})
        if tr.status_code != 200:
            for p in ("gmail", "google_calendar"):
                await set_conn(tenant_id, p, status="error", last_error="token_exchange_failed")
            return RedirectResponse(url=f"{dest}&oauth=error")
        tok = tr.json()
        ui = await client.get("https://www.googleapis.com/oauth2/v2/userinfo",
                              headers={"Authorization": f"Bearer {tok['access_token']}"})
    email = ui.json().get("email") if ui.status_code == 200 else None
    creds = {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token"),
             "expires_at": datetime.now(timezone.utc).timestamp() + tok.get("expires_in", 3600),
             "scopes": tok.get("scope", "").split()}
    ver_doc = await db.google_credentials.find_one({"tenant_id": tenant_id}, {"_id": 0, "credential_version": 1})
    version = ((ver_doc or {}).get("credential_version") or 0) + 1
    await db.google_credentials.update_one({"tenant_id": tenant_id},
        {"$set": {"enc": enc_secret(creds), "account_email": email, "credential_version": version, "updated_at": now_iso()}}, upsert=True)
    for p in ("gmail", "google_calendar"):
        await set_conn(tenant_id, p, status="active", account_identity=email, scopes=GOOGLE_SCOPES,
                       connected_by=actor, connected_at=now_iso(), revoked_at=None, last_error=None, credential_version=version)
        await record_event("integration.connected", "integration", p, tenant_id, actor, payload={"provider": p, "account": email})
    return RedirectResponse(url=f"{dest}&oauth=connected")

@api.post("/integrations/stripe/connect")
async def stripe_connect(user=Depends(require_role("admin"))):
    key = os.environ.get("STRIPE_API_KEY")
    if not key:
        raise HTTPException(status_code=400, detail="Stripe is not configured (STRIPE_API_KEY).")
    await ensure_connections(user["tenant_id"])
    _stripe.api_key = key
    try:
        acct = _stripe.Account.retrieve()
        identity = acct.get("email") or acct.get("id")
    except Exception as e:
        await set_conn(user["tenant_id"], "stripe", status="error", last_error=str(e)[:200])
        raise HTTPException(status_code=400, detail="Could not verify Stripe account")
    version = 1
    await set_conn(user["tenant_id"], "stripe", status="active", account_identity=identity,
                   scopes=["read:customers", "read:invoices", "read:subscriptions"], connected_by=user["email"],
                   connected_at=now_iso(), revoked_at=None, last_error=None, credential_version=version)
    await record_event("integration.connected", "integration", "stripe", user["tenant_id"], user["email"], payload={"account": identity})
    return {"ok": True, "account": identity}

@api.post("/integrations/{provider}/disconnect")
async def disconnect_provider(provider: str, user=Depends(require_role("admin"))):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")
    if provider in ("gmail", "google_calendar"):
        creds = await db.google_credentials.find_one({"tenant_id": user["tenant_id"]}, {"_id": 0})
        if creds:
            try:
                tok = dec_secret(creds["enc"]).get("refresh_token") or dec_secret(creds["enc"]).get("access_token")
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post("https://oauth2.googleapis.com/revoke", params={"token": tok})
            except Exception:
                pass
        if not await db.integration_connections.find_one({"tenant_id": user["tenant_id"], "provider": ("google_calendar" if provider == "gmail" else "gmail"), "status": "active"}):
            await db.google_credentials.delete_one({"tenant_id": user["tenant_id"]})
    await set_conn(user["tenant_id"], provider, status="disconnected", account_identity=None, scopes=[],
                   revoked_at=now_iso())
    await record_event("integration.disconnected", "integration", provider, user["tenant_id"], user["email"], payload={"provider": provider})
    return {"ok": True}

@api.post("/integrations/{provider}/sync")
async def sync_provider(provider: str, user=Depends(require_role("admin"))):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")
    return await run_sync(user["tenant_id"], provider, user["email"])

@api.get("/integrations/sync-logs")
async def integration_sync_logs(user=Depends(require_role("admin"))):
    return await db.integration_sync_logs.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("started_at", -1).to_list(50)

@api.get("/integrations/workspaces/{ws_id}/activity")
async def workspace_activity(ws_id: str, user=Depends(get_current_user)):
    ws = await db.workspaces.find_one({"id": ws_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    comms = await db.crm_communications.find({"tenant_id": user["tenant_id"], "workspace_id": ws_id}, {"_id": 0}).sort("ts", -1).to_list(25)
    meetings = await db.crm_meetings.find({"tenant_id": user["tenant_id"], "workspace_id": ws_id}, {"_id": 0}).sort("start", 1).to_list(25)
    billing = await db.crm_billing.find({"tenant_id": user["tenant_id"], "workspace_id": ws_id}, {"_id": 0}).sort("ts", -1).to_list(50)
    conns = await db.integration_connections.find({"tenant_id": user["tenant_id"]}, SAFE_CONN_FIELDS).to_list(50)
    return {"communications": comms, "meetings": meetings, "billing": billing, "connections": conns}

@api.post("/cron/integration-sync")
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

# ============================================================================
#  INTEGRATION INSIGHTS — unified timeline, alert engine, connection health
# ============================================================================

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

@api.get("/workspaces/{ws_id}/timeline")
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

# ---- Alert engine (deduplicated) ----

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

@api.post("/alerts/evaluate")
async def alerts_evaluate(user=Depends(get_current_user)):
    return await evaluate_alerts(user["tenant_id"])

@api.get("/alerts")
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

@api.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, user=Depends(get_current_user)):
    a = await db.alerts.find_one({"id": alert_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.alerts.update_one({"id": alert_id}, {"$set": {"status": "acknowledged", "acknowledged_by": user["email"], "acknowledged_at": now_iso()}})
    await record_event("alert.acknowledged", "alert", alert_id, user["tenant_id"], user["email"], workspace_id=a.get("workspace_id"), payload={"type": a["type"]})
    await notify_alert({**a, "status": "acknowledged"}, "acknowledged")
    return {"ok": True}

@api.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, user=Depends(get_current_user)):
    a = await db.alerts.find_one({"id": alert_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.alerts.update_one({"id": alert_id}, {"$set": {"status": "resolved", "resolved_at": now_iso()}})
    await record_event("alert.resolved", "alert", alert_id, user["tenant_id"], user["email"], workspace_id=a.get("workspace_id"), payload={"type": a["type"]})
    await notify_alert({**a, "status": "resolved"}, "resolved")
    return {"ok": True}

@api.get("/integrations/health")
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

@api.get("/workspaces/{ws_id}/health-signals")
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

# ============================================================================
#  ALERT NOTIFICATIONS, PREFERENCES, DIGEST & ESCALATION
# ============================================================================
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

# ---- Endpoints ----

@api.get("/notifications")
async def list_notifications(user=Depends(get_current_user)):
    q = {"tenant_id": user["tenant_id"], "$or": [{"user_id": None}, {"user_id": user["user_id"]}]}
    rows = await db.notifications.find(q, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    unread = await db.notifications.count_documents({**q, "read": False})
    return {"notifications": rows, "unread": unread}

@api.post("/notifications/{nid}/read")
async def mark_notification_read(nid: str, user=Depends(get_current_user)):
    r = await db.notifications.update_one({"id": nid, "tenant_id": user["tenant_id"]}, {"$set": {"read": True}})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}

@api.post("/notifications/read-all")
async def mark_all_read(user=Depends(get_current_user)):
    await db.notifications.update_many({"tenant_id": user["tenant_id"], "$or": [{"user_id": None}, {"user_id": user["user_id"]}], "read": False}, {"$set": {"read": True}})
    return {"ok": True}

@api.get("/notifications/preferences")
async def get_notification_preferences(user=Depends(get_current_user)):
    tenant_default = await db.notification_prefs.find_one({"tenant_id": user["tenant_id"], "user_id": None}, {"_id": 0}) or {}
    mine = await db.notification_prefs.find_one({"tenant_id": user["tenant_id"], "user_id": user["user_id"]}, {"_id": 0}) or {}
    return {"tenant_default": _pick(tenant_default) or DEFAULT_PREFS, "mine": _pick(mine),
            "effective": await get_prefs(user["tenant_id"], user["user_id"]),
            "email_configured": email_configured(), "is_admin": user.get("role") == "admin"}

class PrefsInput(BaseModel):
    prefs: dict

@api.put("/notifications/preferences/me")
async def set_my_preferences(inp: PrefsInput, user=Depends(get_current_user)):
    await db.notification_prefs.update_one({"tenant_id": user["tenant_id"], "user_id": user["user_id"]},
        {"$set": {"tenant_id": user["tenant_id"], "user_id": user["user_id"], **_pick(inp.prefs), "updated_at": now_iso(), "updated_by": user["email"]}}, upsert=True)
    await record_event("notification.pref_changed", "prefs", user["user_id"], user["tenant_id"], user["email"], payload={"scope": "user"})
    return {"ok": True, "effective": await get_prefs(user["tenant_id"], user["user_id"])}

@api.put("/notifications/preferences/tenant")
async def set_tenant_preferences(inp: PrefsInput, user=Depends(require_role("admin"))):
    await db.notification_prefs.update_one({"tenant_id": user["tenant_id"], "user_id": None},
        {"$set": {"tenant_id": user["tenant_id"], "user_id": None, **_pick(inp.prefs), "updated_at": now_iso(), "updated_by": user["email"]}}, upsert=True)
    await record_event("notification.pref_changed", "prefs", user["tenant_id"], user["tenant_id"], user["email"], payload={"scope": "tenant"})
    return {"ok": True, "tenant_default": await get_prefs(user["tenant_id"])}

@api.get("/digest/preview")
async def digest_preview(user=Depends(require_role("admin"))):
    return await build_digest(user["tenant_id"])

@api.post("/digest/run")
async def digest_run(user=Depends(require_role("admin"))):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return await deliver_digest(user["tenant_id"], today, force=True)

@api.post("/alerts/escalate")
async def alerts_escalate(user=Depends(require_role("admin"))):
    return {"escalated": await run_escalations(user["tenant_id"])}

@api.post("/cron/daily-digest")
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


# Client portal, field operations, commercial coordination, and safe automation
# are registered here so they inherit the existing tenant, event, and permission helpers.
register_client_value_routes(api, db, new_id, now_iso, record_event, assert_workspace, get_current_user, require_role)

@app.on_event("startup")
async def on_startup():
    await seed()
    try:
        await db.domain_events.create_index([("tenant_id", 1), ("workspace_id", 1), ("timestamp", -1)])
        await db.alerts.create_index([("tenant_id", 1), ("status", 1)])
        await db.alerts.create_index([("tenant_id", 1), ("type", 1), ("source_ref", 1)])
        await db.crm_communications.create_index([("tenant_id", 1), ("workspace_id", 1)])
        await db.crm_meetings.create_index([("tenant_id", 1), ("workspace_id", 1)])
        await db.crm_billing.create_index([("tenant_id", 1), ("workspace_id", 1)])
    except Exception:
        pass

@app.on_event("shutdown")
async def on_shutdown():
    mclient.close()

@api.get("/")
async def root():
    return {"service": "ClientVerse", "version": "v1", "status": "ok"}

@api.get("/health")
async def health():
    """Liveness/readiness probe for hosting platforms. Does not expose secrets."""
    from fastapi.responses import JSONResponse
    try:
        await db.command("ping")
        return {"service": "ClientVerse", "version": "v1", "status": "ok", "database": "up"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"service": "ClientVerse", "version": "v1", "status": "degraded", "database": "down"},
        )

app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
