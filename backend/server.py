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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("clientverse")

mongo_url = os.environ['MONGO_URL']
mclient = AsyncIOMotorClient(mongo_url)
db = mclient[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALG = "HS256"
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')

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
        return user
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
    return user

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
    token = create_access_token(uid, email)
    set_auth_cookie(response, token)
    u = await db.users.find_one({"user_id": uid}, {"_id": 0, "password_hash": 0})
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
    return {"user": user, "token": session_token}

@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user

@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}

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
    email: Optional[str] = None
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
    doc = {"id": new_id("apr"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.approvals.insert_one(doc)
    await record_event("approval.requested", "approval", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"title": inp.title})
    return {k: v for k, v in doc.items() if k != "_id"}

@api.patch("/approvals/{apr_id}")
async def decide_approval(apr_id: str, inp: TaskStatus, user=Depends(get_current_user)):
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
    doc = {"id": new_id("cmt"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.commitments.insert_one(doc)
    await record_event("commitment.created", "commitment", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"title": inp.title})
    return {k: v for k, v in doc.items() if k != "_id"}

@api.patch("/commitments/{cmt_id}")
async def update_commitment(cmt_id: str, inp: TaskStatus, user=Depends(get_current_user)):
    c = await db.commitments.find_one({"id": cmt_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    await db.commitments.update_one({"id": cmt_id}, {"$set": {"status": inp.status}})
    etmap = {"at_risk": "commitment.at_risk", "fulfilled": "commitment.fulfilled"}
    if inp.status in etmap:
        await record_event(etmap[inp.status], "commitment", cmt_id, user["tenant_id"], user["email"], workspace_id=c["workspace_id"], payload={"title": c["title"]})
    return {"ok": True}

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
    return {
        "pipeline_value": pipeline_value, "won_value": won_value,
        "open_opportunities": len([o for o in opps if o.get("stage") not in ("closed_won", "closed_lost")]),
        "active_workspaces": len(workspaces), "at_risk_commitments": at_risk,
        "funnel": funnel, "portfolio": portfolio,
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
    await db.users.create_index("email", unique=True)

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
    await db.outcomes.insert_many([
        {"id": new_id("out"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Launch analytics platform", "target": "Production go-live", "target_value": 100, "current_value": 65, "unit": "% complete", "status": "on_track", "linked_commitment_ids": [cmt1["id"]], "created_at": now_iso()},
        {"id": new_id("out"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Cut reporting time", "target": "Reduce vs baseline", "target_value": 50, "current_value": 28, "unit": "% reduction", "status": "at_risk", "linked_commitment_ids": [cmt1["id"], cmt2["id"]], "created_at": now_iso()},
    ])
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
        {"id": new_id("wh"), "tenant_id": t, "name": "Local Test Sink", "url": "http://localhost:8001/api/webhooks/sink", "events": ["commitment.at_risk", "approval.requested", "task.created", "mcp.tool_invoked", "webhook.test", "commitment.fulfilled", "deliverable.approved"], "status": "AVAILABLE", "signed": True, "enabled": True, "secret": "whsec_sink_" + secrets.token_hex(8), "description": "Built-in sink returning 200 — shows successful signed delivery.", "created_at": now_iso()},
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
        await db.mcp_tool_invocations.update_one({"id": inv_id}, {"$set": {"status": "success", "result": result, "latency_ms": latency}})
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
async def mcp_kill(inp: KillInput, user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin permission required")
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

@api.post("/mcp/invocations/{inv_id}/undo")
async def mcp_undo(inv_id: str, user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin permission required")
    inv = await db.mcp_tool_invocations.find_one({"id": inv_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Not found")
    if inv.get("level") != 2 or inv.get("status") != "success":
        raise HTTPException(status_code=400, detail="Only successful Level 2 writes can be undone")
    if inv.get("undone"):
        raise HTTPException(status_code=400, detail="Already undone")
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
    await db.mcp_tool_invocations.update_one({"id": inv_id}, {"$set": {"undone": True, "status": "undone", "undone_by": user["email"], "undone_at": now_iso()}})
    await record_event("mcp.tool_undone", "mcp_tool", inv["tool"], user["tenant_id"], user["email"], workspace_id=ws_id, payload={"invocation_id": inv_id, "restored": restored})
    return {"ok": True, "restored": restored}

# ----------------------------- Webhooks (live signed delivery) -----------------------------

WEBHOOK_MAX_ATTEMPTS = 3
HEALTH_AFFECTING = {"commitment.created", "commitment.at_risk", "commitment.fulfilled",
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

async def dispatch_webhooks_for_event(ev: dict):
    try:
        hooks = await db.webhooks.find({"tenant_id": ev.get("tenant_id"), "enabled": True}, {"_id": 0}).to_list(100)
    except Exception:
        return
    for wh in hooks:
        if ev.get("event_type") not in (wh.get("events") or []):
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
    return await db.webhooks.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)

@api.post("/webhooks")
async def create_webhook(inp: WebhookInput, user=Depends(get_current_user)):
    doc = {"id": new_id("wh"), "tenant_id": user["tenant_id"], "name": inp.name, "url": inp.url,
           "events": inp.events, "status": "AVAILABLE", "signed": True, "enabled": True,
           "secret": "whsec_" + secrets.token_hex(16), "description": "Custom endpoint.", "created_at": now_iso()}
    await db.webhooks.insert_one(dict(doc))
    await record_event("integration.connected", "webhook", doc["id"], user["tenant_id"], user["email"], payload={"name": inp.name})
    return {k: v for k, v in doc.items() if k != "_id"}

@api.patch("/webhooks/{wid}")
async def patch_webhook(wid: str, inp: WebhookPatch, user=Depends(get_current_user)):
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
    doc = {"id": new_id("out"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.outcomes.insert_one(dict(doc))
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

@app.on_event("startup")
async def on_startup():
    await seed()

@app.on_event("shutdown")
async def on_shutdown():
    mclient.close()

@api.get("/")
async def root():
    return {"service": "ClientVerse", "version": "v1", "status": "ok"}

app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
