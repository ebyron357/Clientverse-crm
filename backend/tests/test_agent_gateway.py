"""Agent security gateway (blueprint §6, P0), behind AGENT_GATEWAY_V2.

* With the flag off, nothing changes: the emergency-stop routes answer 404 and an MCP
  write executes on approval exactly as before.
* An approval covers the exact arguments: change the stored arguments after approval and
  the write does not run.
* The kill switch is re-checked when an approved write executes, not only when it was
  requested.
* The emergency stop refuses new tool calls, withdraws agent approvals, cancels pending
  writes, takes queued work out of service, stops workers claiming for that tenant, and
  leaves other tenants alone. Release ends it; the kill switch stays on.

In-process against the real `app`, with a fresh motor client per test for the reason
given in test_security_headers.py.
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_agent_gateway_unit")
os.environ.setdefault("JWT_SECRET", "agent-gateway-unit-jwt-secret-long-enough")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "agent-gateway-admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "Agent-Gateway-Admin-1!")

from fastapi.testclient import TestClient

import agent_gateway
import server
from work_queue import DEAD_LETTER, QUEUED, WorkQueue


def _reset_motor_client():
    server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
    server.db = server.mclient[os.environ["DB_NAME"]]


@pytest.fixture
def gateway_on(monkeypatch):
    monkeypatch.setenv(agent_gateway.FLAG, "1")


@pytest.fixture
def gateway_off(monkeypatch):
    monkeypatch.delenv(agent_gateway.FLAG, raising=False)


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client):
    response = client.post("/api/auth/register", json={
        "email": f"gw_{uuid.uuid4().hex[:10]}@example.com",
        "password": "Str0ng-Passw0rd!", "name": "Gateway admin"})
    assert response.status_code == 200, response.text
    client.cookies.clear()
    body = response.json()
    return _h(body["token"]), body["user"]["tenant_id"]


def _workspace(client, headers):
    response = client.post("/api/workspaces", json={"name": "Gateway test"}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _request_task(client, headers, workspace_id, title="Gateway task"):
    response = client.post("/api/mcp/invoke", headers=headers, json={
        "tool": "create_task", "args": {"workspace_id": workspace_id, "title": title}})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending_approval"
    return response.json()


def _db(client, fn):
    async def run():
        return await fn(server.db)
    return client.portal.call(run)


def _tasks_titled(client, tenant_id, title):
    return _db(client, lambda db: db.tasks.count_documents({"tenant_id": tenant_id, "title": title}))


def test_args_digest_is_canonical():
    assert agent_gateway.args_digest({"a": 1, "b": "x"}) == agent_gateway.args_digest({"b": "x", "a": 1})
    assert agent_gateway.args_digest({"a": 1}) != agent_gateway.args_digest({"a": 2})


def test_flag_off_changes_nothing(gateway_off):
    _reset_motor_client()
    with TestClient(server.app) as client:
        headers, tenant_id = _admin(client)
        assert client.post("/api/agents/emergency-stop", headers=headers,
                           json={"reason": "test"}).status_code == 404
        workspace_id = _workspace(client, headers)
        invoked = _request_task(client, headers, workspace_id, "Flag off task")
        decided = client.patch(f"/api/approvals/{invoked['approval_id']}", headers=headers,
                               json={"status": "approved"})
        assert decided.status_code == 200, decided.text
        assert decided.json()["execution"]["status"] == "success"
        assert _tasks_titled(client, tenant_id, "Flag off task") == 1


def test_an_approval_covers_the_exact_arguments(gateway_on):
    _reset_motor_client()
    with TestClient(server.app) as client:
        headers, tenant_id = _admin(client)
        workspace_id = _workspace(client, headers)
        invoked = _request_task(client, headers, workspace_id, "Approved title")
        approval = _db(client, lambda db: db.approvals.find_one({"id": invoked["approval_id"]}))
        assert approval["action"]["args_sha256"] == agent_gateway.args_digest(
            {"workspace_id": workspace_id, "title": "Approved title"})

        # Someone changes what the pending write would do after the approval was asked for.
        _db(client, lambda db: db.mcp_pending_actions.update_one(
            {"approval_id": invoked["approval_id"]}, {"$set": {"args.title": "Swapped title"}}))
        decided = client.patch(f"/api/approvals/{invoked['approval_id']}", headers=headers,
                               json={"status": "approved"})
        assert decided.status_code == 409, decided.text
        assert "different action" in decided.json()["detail"]
        assert _tasks_titled(client, tenant_id, "Swapped title") == 0
        assert _tasks_titled(client, tenant_id, "Approved title") == 0


def test_unchanged_arguments_still_execute(gateway_on):
    _reset_motor_client()
    with TestClient(server.app) as client:
        headers, tenant_id = _admin(client)
        workspace_id = _workspace(client, headers)
        invoked = _request_task(client, headers, workspace_id, "Bound task")
        decided = client.patch(f"/api/approvals/{invoked['approval_id']}", headers=headers,
                               json={"status": "approved"})
        assert decided.status_code == 200, decided.text
        assert decided.json()["execution"]["status"] == "success"
        assert _tasks_titled(client, tenant_id, "Bound task") == 1


def test_the_kill_switch_is_rechecked_when_an_approved_write_executes(gateway_on):
    _reset_motor_client()
    with TestClient(server.app) as client:
        headers, tenant_id = _admin(client)
        workspace_id = _workspace(client, headers)
        invoked = _request_task(client, headers, workspace_id, "Late task")
        assert client.patch("/api/mcp/server/kill", headers=headers,
                            json={"enabled": True}).status_code == 200
        decided = client.patch(f"/api/approvals/{invoked['approval_id']}", headers=headers,
                               json={"status": "approved"})
        assert decided.status_code == 200, decided.text
        assert decided.json()["execution"]["status"] == "refused"
        assert _tasks_titled(client, tenant_id, "Late task") == 0


def test_emergency_stop_stops_one_tenant_and_release_ends_it(gateway_on):
    _reset_motor_client()
    with TestClient(server.app) as client:
        headers, tenant_id = _admin(client)
        other_headers, other_tenant = _admin(client)
        workspace_id = _workspace(client, headers)
        invoked = _request_task(client, headers, workspace_id, "Waiting task")

        async def enqueue(db):
            queue = WorkQueue(db)
            mine = await queue.enqueue(tenant_id=tenant_id, queue="gw", item_type="test", payload={})
            theirs = await queue.enqueue(tenant_id=other_tenant, queue="gw", item_type="test", payload={})
            return mine["id"], theirs["id"]
        mine, theirs = _db(client, enqueue)

        stopped = client.post("/api/agents/emergency-stop", headers=headers,
                              json={"reason": "Drill"})
        assert stopped.status_code == 200, stopped.text
        receipt = stopped.json()
        assert receipt["approvals_cancelled"] == 1
        assert receipt["pending_actions_cancelled"] == 1
        assert receipt["work_items_stopped"] == 1

        approval = _db(client, lambda db: db.approvals.find_one({"id": invoked["approval_id"]}))
        assert approval["status"] == "cancelled"
        item = _db(client, lambda db: db.work_queue.find_one({"id": mine}))
        assert item["status"] == DEAD_LETTER
        other_item = _db(client, lambda db: db.work_queue.find_one({"id": theirs}))
        assert other_item["status"] == QUEUED

        # New tool calls are refused; the other tenant is unaffected.
        refused = client.post("/api/mcp/invoke", headers=headers,
                              json={"tool": "list_open_commitments", "args": {}})
        assert refused.status_code == 423
        assert client.post("/api/mcp/invoke", headers=other_headers,
                           json={"tool": "list_open_commitments", "args": {}}).status_code == 200

        # Workers take nothing for the stopped tenant, even work queued after the stop.
        async def claim_after_stop(db):
            queue = WorkQueue(db)
            await queue.enqueue(tenant_id=tenant_id, queue="gw", item_type="test", payload={})
            return await queue.claim(worker_id="w1", queue="gw", limit=10)
        claimed = _db(client, claim_after_stop)
        assert {c["tenant_id"] for c in claimed} == {other_tenant}

        state = client.get("/api/agents/emergency-stop", headers=headers).json()
        assert state["active"] is True and state["stop"]["reason"] == "Drill"

        released = client.post("/api/agents/emergency-stop/release", headers=headers)
        assert released.status_code == 200 and released.json()["released"] is True
        assert client.get("/api/agents/emergency-stop", headers=headers).json()["active"] is False
        # The kill switch stays on until an admin turns it off.
        assert client.post("/api/mcp/invoke", headers=headers,
                           json={"tool": "list_open_commitments", "args": {}}).status_code == 423


def test_only_admins_may_stop(gateway_on):
    _reset_motor_client()
    with TestClient(server.app) as client:
        assert client.post("/api/agents/emergency-stop", json={"reason": "x" * 5}).status_code == 401


def test_is_stopped_is_false_when_the_flag_is_off(gateway_off):
    _reset_motor_client()

    async def run():
        await server.db[agent_gateway.STOPS].insert_one({"tenant_id": "t-off", "active": True})
        return await agent_gateway.is_stopped(server.db, "t-off")
    assert asyncio.run(run()) is False
