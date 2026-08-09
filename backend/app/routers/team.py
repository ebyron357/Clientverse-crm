"""Team routes: invitations and membership management."""
import hashlib
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, EmailStr

from app.shared import (db, new_id, now_iso, record_event, require_role,
                        get_current_user, FRONTEND_URL)

router = APIRouter(prefix="/api")

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

@router.get("/team/members")
async def team_members(user=Depends(require_role("admin"))):
    mems = await db.memberships.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("created_at", 1).to_list(500)
    out = []
    for m in mems:
        u = await db.users.find_one({"user_id": m["user_id"]}, {"_id": 0, "password_hash": 0})
        out.append({**m, "name": (u or {}).get("name"), "picture": (u or {}).get("picture"), "auth": (u or {}).get("auth")})
    return out

@router.get("/team/invitations")
async def list_invitations(user=Depends(require_role("admin"))):
    invs = await db.invitations.find({"tenant_id": user["tenant_id"]}, {"_id": 0, "token_hash": 0}).sort("created_at", -1).to_list(500)
    return [_invite_public(await _expire_if_needed(inv)) for inv in invs]

@router.post("/team/invitations")
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

@router.post("/team/invitations/{inv_id}/resend")
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

@router.post("/team/invitations/{inv_id}/revoke")
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

@router.get("/team/invitations/lookup")
async def lookup_invitation(token: str = Query(...)):
    inv = await db.invitations.find_one({"token_hash": hash_token(token)}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found")
    inv = await _expire_if_needed(inv)
    tenant = await db.tenants.find_one({"tenant_id": inv["tenant_id"]}, {"_id": 0})
    return _invite_public(inv, tenant_name=(tenant or {}).get("name"))

@router.post("/team/invitations/accept")
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

@router.patch("/team/members/{target_user_id}/role")
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

@router.patch("/team/members/{target_user_id}/status")
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
