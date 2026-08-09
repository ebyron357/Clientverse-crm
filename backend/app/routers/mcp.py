"""MCP console routes: server state, tools, invoke, invocations, undo."""
import asyncio
import time
from typing import Optional
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from app.shared import (db, new_id, now_iso, record_event, get_current_user, require_role)
from app.services.mcp import (MCP_TOOLS, MCP_TOOL_CATALOG, MCP_SERVER_ID, TOOL_IMPL,
                              TOOL_IMPL_L2, get_mcp_server, execute_pending_mcp)

router = APIRouter(prefix="/api")

@router.get("/mcp/server")
async def mcp_server(user=Depends(get_current_user)):
    return await get_mcp_server(user["tenant_id"])

@router.get("/mcp/tools")
async def mcp_tools(user=Depends(get_current_user)):
    server = await get_mcp_server(user["tenant_id"])
    return {"server": server, "tools": MCP_TOOL_CATALOG}

class KillInput(BaseModel):
    enabled: bool

@router.patch("/mcp/server/kill")
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

@router.post("/mcp/invoke")
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

@router.get("/mcp/invocations")
async def mcp_invocations(limit: int = Query(100), user=Depends(get_current_user)):
    docs = await db.mcp_tool_invocations.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return docs

UNDO_WINDOW_MINUTES = 60

class UndoInput(BaseModel):
    reason: str = ""

@router.post("/mcp/invocations/{inv_id}/undo")
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

@router.patch("/workspaces/{ws_id}/undo-window")
async def set_undo_window(ws_id: str, inp: UndoWindowInput, user=Depends(require_role("admin"))):
    ws = await db.workspaces.find_one({"id": ws_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=404, detail="Not found")
    m = max(1, min(1440, inp.minutes))
    await db.workspaces.update_one({"id": ws_id}, {"$set": {"undo_window_minutes": m}})
    return {"ok": True, "undo_window_minutes": m}
