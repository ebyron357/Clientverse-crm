"""An approved MCP write re-checks the security gate when it runs, not only when asked.

A pending write can wait hours for approval. A component revoked, re-scanned or expired in
that time must not run on the strength of the check made when the write was requested.
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_mcp_gate_unit")
os.environ.setdefault("JWT_SECRET", "mcp-gate-unit-jwt-secret-long-enough-123456")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

import server

TENANT = "ten_mcp_gate"
USER = {"tenant_id": TENANT, "email": "admin@example.com", "role": "admin"}
TOOL = {"name": "ext_write", "level": 2, "external": True, "timeout_seconds": 5,
        "source_url": "https://github.com/example/ext", "version": "1.0.0",
        "digest": "sha256:abc", "scopes": [], "approval_required": True}


def run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_an_unapproved_external_write_is_blocked_at_execution(monkeypatch):
    ran = []

    async def implementation(user, args):
        ran.append(args)
        return {"ok": True}

    monkeypatch.setitem(server.MCP_TOOLS, "ext_write", TOOL)
    monkeypatch.setitem(server.TOOL_IMPL_L2, "ext_write", implementation)
    name = f"clientverse_mcp_gate_{uuid.uuid4().hex[:10]}"

    async def body():
        previous = server.db
        server.db = server.mclient[name]
        try:
            db = server.db
            await db.mcp_pending_actions.insert_one({
                "id": "pa_1", "tenant_id": TENANT, "tool": "ext_write", "args": {"x": 1},
                "status": "pending_approval", "invocation_id": "inv_1"})
            await db.mcp_tool_invocations.insert_one({
                "id": "inv_1", "tenant_id": TENANT, "tool": "ext_write",
                "status": "pending_approval"})
            outcome = await server.execute_pending_mcp("pa_1", USER)
            pending = await db.mcp_pending_actions.find_one({"id": "pa_1"})
            invocation = await db.mcp_tool_invocations.find_one({"id": "inv_1"})
            return outcome, pending["status"], invocation["status"]
        finally:
            await server.mclient.drop_database(name)
            server.db = previous

    outcome, pending, invocation = run(body())
    assert outcome["status"] == "blocked"
    assert pending == "blocked" and invocation == "blocked"
    assert ran == [], "the external tool must not run"


def test_a_write_queued_before_the_kill_switch_does_not_run_after_it(monkeypatch):
    ran = []

    async def implementation(user, args):
        ran.append(args)
        return {"ok": True}

    monkeypatch.setitem(server.TOOL_IMPL_L2, "create_task", implementation)
    name = f"clientverse_mcp_kill_{uuid.uuid4().hex[:10]}"

    async def body():
        previous = server.db
        server.db = server.mclient[name]
        try:
            db = server.db
            await server.get_mcp_server(TENANT)
            await db.mcp_server_state.update_one({"tenant_id": TENANT},
                                                 {"$set": {"kill_switch": True}})
            await db.mcp_pending_actions.insert_one({
                "id": "pa_k", "tenant_id": TENANT, "tool": "create_task",
                "args": {"workspace_id": "ws", "title": "t"},
                "status": "pending_approval", "invocation_id": "inv_k"})
            await db.mcp_tool_invocations.insert_one({
                "id": "inv_k", "tenant_id": TENANT, "tool": "create_task",
                "status": "pending_approval"})
            return await server.execute_pending_mcp("pa_k", USER)
        finally:
            await server.mclient.drop_database(name)
            server.db = previous

    outcome = run(body())
    assert outcome["status"] == "blocked" and "kill switch" in outcome["error"]
    assert ran == []
