"""Governed MCP tool catalog, tool implementations and execution engine."""
import asyncio
import time
from datetime import datetime, timezone, timedelta

from app.shared import db, new_id, now_iso, record_event, compute_health, STAGES

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
