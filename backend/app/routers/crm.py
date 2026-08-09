"""Core CRM routes: companies, contacts, opportunities (pipeline), workspaces."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.shared import (db, new_id, now_iso, record_event, get_current_user,
                        gen_list, compute_health, STAGES)

router = APIRouter(prefix="/api")

class CompanyInput(BaseModel):
    name: str
    industry: Optional[str] = None
    website: Optional[str] = None
    tier: Optional[str] = "standard"

@router.get("/companies")
async def list_companies(user=Depends(get_current_user)):
    return await gen_list("companies", user)

@router.post("/companies")
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

@router.get("/contacts")
async def list_contacts(company_id: Optional[str] = None, user=Depends(get_current_user)):
    extra = {"company_id": company_id} if company_id else None
    return await gen_list("contacts", user, extra)

@router.post("/contacts")
async def create_contact(inp: ContactInput, user=Depends(get_current_user)):
    doc = {"id": new_id("ct"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.contacts.insert_one(doc)
    await record_event("contact.created", "contact", doc["id"], user["tenant_id"], user["email"], payload={"name": inp.name})
    return {k: v for k, v in doc.items() if k != "_id"}

class OppInput(BaseModel):
    name: str
    company_id: Optional[str] = None
    value: float = 0
    stage: str = "lead"
    owner: Optional[str] = None

@router.get("/opportunities")
async def list_opps(user=Depends(get_current_user)):
    return await gen_list("opportunities", user)

@router.post("/opportunities")
async def create_opp(inp: OppInput, user=Depends(get_current_user)):
    doc = {"id": new_id("opp"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.opportunities.insert_one(doc)
    await record_event("opportunity.created", "opportunity", doc["id"], user["tenant_id"], user["email"], payload={"name": inp.name, "value": inp.value})
    return {k: v for k, v in doc.items() if k != "_id"}

class StageInput(BaseModel):
    stage: str

@router.patch("/opportunities/{opp_id}/stage")
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

class WorkspaceInput(BaseModel):
    name: str
    company_id: Optional[str] = None
    stage: str = "onboard"

@router.get("/workspaces")
async def list_workspaces(user=Depends(get_current_user)):
    return await gen_list("workspaces", user)

@router.post("/workspaces")
async def create_workspace(inp: WorkspaceInput, user=Depends(get_current_user)):
    doc = {"id": new_id("ws"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump(), "opportunity_id": None}
    await db.workspaces.insert_one(doc)
    await record_event("client_workspace.created", "workspace", doc["id"], user["tenant_id"], user["email"], workspace_id=doc["id"], payload={"name": inp.name})
    return {k: v for k, v in doc.items() if k != "_id"}

@router.get("/workspaces/{ws_id}")
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
