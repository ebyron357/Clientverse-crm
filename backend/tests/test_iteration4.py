"""ClientVerse.io iteration-4 backend tests: Undo, Outcome Targets, Webhook secret exposure."""
import os
import uuid
import time
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "AdminPass123!")


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def workspace_id(admin):
    ws = admin.get(f"{API}/workspaces").json()
    assert ws
    return ws[0]["id"]


# --- Outcome Targets ---
class TestOutcomeTargets:
    def test_outcome_graph_returns_targets(self, admin):
        # Find a workspace with seeded goals (target seed = ClientVerse HQ delivery workspace)
        ws_list = admin.get(f"{API}/workspaces").json()
        found = None
        for w in ws_list:
            g = admin.get(f"{API}/workspaces/{w['id']}/outcome-graph").json()
            if g.get("goals"):
                found = g
                break
        assert found, "no workspace with seeded goals found"
        g = found["goals"][0]
        for f in ("target_value", "current_value", "unit", "title"):
            assert f in g, f"missing {f} in goal: {list(g.keys())}"
        # Verify seeded 'Launch analytics platform' has 65/100
        launch = next((x for x in found["goals"] if "Launch analytics" in x.get("title", "")), None)
        if launch:
            assert launch["current_value"] == 65
            assert launch["target_value"] == 100

    def test_create_outcome_with_target(self, admin, workspace_id):
        title = f"TEST_outcome_{uuid.uuid4().hex[:6]}"
        r = admin.post(f"{API}/outcomes", json={
            "workspace_id": workspace_id, "title": title, "target": title,
            "target_value": 80, "current_value": 10, "unit": "% complete"
        })
        assert r.status_code in (200, 201), r.text
        o = r.json()
        assert o["target_value"] == 80
        assert o["current_value"] == 10
        assert o["unit"] == "% complete"

    def test_patch_outcome_current_value(self, admin, workspace_id):
        c = admin.post(f"{API}/outcomes", json={
            "workspace_id": workspace_id, "title": f"TEST_upd_{uuid.uuid4().hex[:6]}", "target": "x",
            "target_value": 100, "current_value": 20, "unit": "%"
        }).json()
        oid = c["id"]
        r = admin.patch(f"{API}/outcomes/{oid}", json={"current_value": 55})
        assert r.status_code in (200, 204), r.text
        # Verify via graph
        graph = admin.get(f"{API}/workspaces/{workspace_id}/outcome-graph").json()
        goal = next((g for g in graph["goals"] if g["id"] == oid), None)
        assert goal and goal["current_value"] == 55


# --- MCP Undo ---
class TestMcpUndo:
    def _invoke_and_approve_create_task(self, admin, workspace_id):
        title = f"TEST_undo_{uuid.uuid4().hex[:6]}"
        r = admin.post(f"{API}/mcp/invoke", json={
            "tool": "create_task", "args": {"workspace_id": workspace_id, "title": title, "description": "undo test"}
        })
        assert r.status_code == 200, r.text
        d = r.json()
        # Level 2 create_task should be pending_approval
        assert d.get("status") == "pending_approval", d
        approval_id = d.get("approval_id") or d.get("approval", {}).get("id")
        inv_id = d.get("invocation_id") or d.get("id")
        assert approval_id, d
        # Approve
        pr = admin.patch(f"{API}/approvals/{approval_id}", json={"status": "approved"})
        assert pr.status_code in (200, 204), pr.text
        # find invocation
        invs = admin.get(f"{API}/mcp/invocations").json()
        inv = next((i for i in invs if i.get("id") == inv_id or (i.get("tool") == "create_task" and (i.get("args") or {}).get("title") == title and i.get("status") == "success")), None)
        assert inv, f"invocation not found: title={title}"
        assert inv["status"] == "success"
        return inv, title

    def test_undo_removes_task_and_blocks_reuse(self, admin, workspace_id):
        inv, title = self._invoke_and_approve_create_task(admin, workspace_id)
        # Task exists
        ws = admin.get(f"{API}/workspaces/{workspace_id}").json()
        assert any(t["title"] == title for t in ws.get("tasks", [])), "task should exist before undo"

        # Undo (iteration-5: reason required)
        r = admin.post(f"{API}/mcp/invocations/{inv['id']}/undo", json={"reason": "test cleanup"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert "restored" in body

        # Task removed
        ws2 = admin.get(f"{API}/workspaces/{workspace_id}").json()
        assert not any(t["title"] == title for t in ws2.get("tasks", [])), "task should be removed after undo"

        # Invocation marked undone
        invs = admin.get(f"{API}/mcp/invocations").json()
        u = next(i for i in invs if i["id"] == inv["id"])
        assert u.get("undone") is True
        assert u.get("status") == "undone"

        # Second undo blocked
        r2 = admin.post(f"{API}/mcp/invocations/{inv['id']}/undo", json={"reason": "again"})
        assert r2.status_code == 400, r2.text

        # Event emitted
        events = admin.get(f"{API}/events").json()
        assert any(e.get("event_type") == "mcp.tool_undone" and (e.get("payload") or {}).get("invocation_id") == inv["id"] for e in events)

    def test_undo_cross_tenant_isolation(self, admin, workspace_id):
        """New-tenant users become admin of their own tenant so tenant-scoping (404) protects cross-tenant undo."""
        # Create a real invocation in admin tenant
        title = f"TEST_iso_{uuid.uuid4().hex[:6]}"
        r = admin.post(f"{API}/mcp/invoke", json={
            "tool": "create_task", "args": {"workspace_id": workspace_id, "title": title}
        })
        approval_id = r.json().get("approval_id")
        admin.patch(f"{API}/approvals/{approval_id}", json={"status": "approved"})
        invs = admin.get(f"{API}/mcp/invocations").json()
        inv_id = next(i["id"] for i in invs if (i.get("args") or {}).get("title") == title)

        # New tenant user tries to undo admin's invocation
        s = requests.Session()
        email = f"TEST_{uuid.uuid4().hex[:8]}@example.com"
        reg = s.post(f"{API}/auth/register", json={"email": email, "password": "Passw0rd!!", "name": "T"})
        assert reg.status_code in (200, 201)
        tok = reg.json().get("access_token") or reg.json().get("token")
        if tok:
            s.headers.update({"Authorization": f"Bearer {tok}"})
        r = s.post(f"{API}/mcp/invocations/{inv_id}/undo", json={"reason": "cross tenant"})
        assert r.status_code in (403, 404), r.text


# --- Webhook secrets remain redacted from listings and are separately admin-revealed ---
class TestWebhookSecret:
    def test_webhook_list_redacts_secret(self, admin):
        r = admin.get(f"{API}/registry/webhooks")
        assert r.status_code == 200
        items = r.json()
        assert len(items) > 0
        wh = items[0]
        assert "secret" not in wh, f"webhook registry must redact secrets: {list(wh.keys())}"
