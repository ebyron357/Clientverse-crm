"""Delivery routes: tasks, deliverables, client requests, approvals, commitments."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.shared import (db, new_id, now_iso, record_event, get_current_user, require_role)
from app.services.mcp import execute_pending_mcp
from app.services.commitments import evaluate_commitment_risk

router = APIRouter(prefix="/api")

class TaskInput(BaseModel):
    workspace_id: str
    title: str
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    status: str = "todo"

@router.post("/tasks")
async def create_task(inp: TaskInput, user=Depends(get_current_user)):
    doc = {"id": new_id("task"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.tasks.insert_one(doc)
    await record_event("task.created", "task", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"title": inp.title})
    return {k: v for k, v in doc.items() if k != "_id"}

class TaskStatus(BaseModel):
    status: str

@router.patch("/tasks/{task_id}")
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

@router.post("/deliverables")
async def create_deliverable(inp: DeliverableInput, user=Depends(get_current_user)):
    doc = {"id": new_id("dlv"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.deliverables.insert_one(doc)
    await record_event("deliverable.created", "deliverable", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"title": inp.title})
    return {k: v for k, v in doc.items() if k != "_id"}

@router.patch("/deliverables/{dlv_id}")
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

@router.post("/client-requests")
async def create_request(inp: RequestInput, user=Depends(get_current_user)):
    doc = {"id": new_id("req"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.client_requests.insert_one(doc)
    await record_event("client_request.created", "client_request", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"title": inp.title})
    return {k: v for k, v in doc.items() if k != "_id"}

@router.patch("/client-requests/{req_id}")
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

@router.post("/approvals")
async def create_approval(inp: ApprovalInput, user=Depends(get_current_user)):
    doc = {"id": new_id("apr"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.approvals.insert_one(doc)
    await record_event("approval.requested", "approval", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"title": inp.title})
    return {k: v for k, v in doc.items() if k != "_id"}

@router.patch("/approvals/{apr_id}")
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

@router.post("/commitments")
async def create_commitment(inp: CommitmentInput, user=Depends(get_current_user)):
    doc = {"id": new_id("cmt"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.commitments.insert_one(doc)
    await record_event("commitment.created", "commitment", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"title": inp.title})
    return {k: v for k, v in doc.items() if k != "_id"}

class CommitmentPatch(BaseModel):
    status: Optional[str] = None
    due_date: Optional[str] = None

@router.patch("/commitments/{cmt_id}")
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

@router.post("/commitments/evaluate-risk")
async def commitments_evaluate_risk(user=Depends(get_current_user)):
    return await evaluate_commitment_risk(tenant_id=user["tenant_id"], actor=user["email"])
