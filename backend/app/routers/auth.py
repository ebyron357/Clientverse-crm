"""Authentication routes: register, login, Google session, me, logout."""
import requests
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel, EmailStr

from app.shared import (db, new_id, now_iso, hash_password, verify_password,
                        create_access_token, set_auth_cookie, get_current_user)

router = APIRouter(prefix="/api")

class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    name: str

class LoginInput(BaseModel):
    email: EmailStr
    password: str

@router.post("/auth/register")
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
    token = create_access_token(uid, email)
    set_auth_cookie(response, token)
    u = await db.users.find_one({"user_id": uid}, {"_id": 0, "password_hash": 0})
    return {"user": u, "token": token}

@router.post("/auth/login")
async def login(inp: LoginInput, response: Response):
    email = inp.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("password_hash") or not verify_password(inp.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["user_id"], email)
    set_auth_cookie(response, token)
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password_hash": 0})
    return {"user": u, "token": token}

@router.post("/auth/google/session")
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
    return {"user": user, "token": session_token}

@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user

@router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}
