"""Client Outcome Graph routes."""
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.shared import (db, new_id, now_iso, record_event, get_current_user, compute_health)

router = APIRouter(prefix="/api")

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

@router.patch("/outcomes/{oid}")
async def update_outcome(oid: str, inp: OutcomePatch, user=Depends(get_current_user)):
    o = await db.outcomes.find_one({"id": oid, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not o:
        raise HTTPException(status_code=404, detail="Not found")
    upd = {k: v for k, v in inp.model_dump().items() if v is not None}
    if upd:
        await db.outcomes.update_one({"id": oid}, {"$set": upd})
        await record_event("health.factor_changed", "outcome", oid, user["tenant_id"], user["email"], workspace_id=o["workspace_id"], payload={"updated": list(upd.keys())})
    return {"ok": True, **upd}

@router.post("/outcomes")
async def create_outcome(inp: OutcomeInput, user=Depends(get_current_user)):
    doc = {"id": new_id("out"), "tenant_id": user["tenant_id"], "created_at": now_iso(), **inp.model_dump()}
    await db.outcomes.insert_one(dict(doc))
    await snapshot_outcome(doc)
    await record_event("health.factor_changed", "outcome", doc["id"], user["tenant_id"], user["email"],
                       workspace_id=inp.workspace_id, payload={"title": inp.title})
    return {k: v for k, v in doc.items() if k != "_id"}

@router.get("/workspaces/{ws_id}/outcome-graph")
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
