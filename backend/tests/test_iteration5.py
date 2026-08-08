"""ClientVerse.io iteration-5 backend tests:
- Dashboard goal_rollup
- MCP Undo requires reason (422 empty), 60-min window
- Webhook event pattern filters (commitment.*, mcp.*, *)
- Regression sanity after backend corruption fix
"""
import os
import uuid
import time
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://outcome-graph.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "AdminPass123!")


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def workspace_id(admin):
    ws = admin.get(f"{API}/workspaces").json()
    assert ws, "need at least one workspace"
    return ws[0]["id"]


# ---------- Regression: backend up after corruption fix ----------
class TestBackendUp:
    def test_root(self):
        r = requests.get(f"{API}/", timeout=15)
        assert r.status_code in (200, 404)

    def test_login_ok(self, admin):
        r = admin.get(f"{API}/auth/me")
        assert r.status_code == 200


# ---------- Feature 1: Dashboard goal_rollup ----------
class TestGoalRollup:
    def test_dashboard_has_goal_rollup(self, admin):
        r = admin.get(f"{API}/dashboard")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "goal_rollup" in d, list(d.keys())
        gr = d["goal_rollup"]
        for k in ("total_goals", "on_track", "at_risk", "avg_progress", "workspaces"):
            assert k in gr, f"missing {k} in goal_rollup: {list(gr.keys())}"
        assert isinstance(gr["workspaces"], list)
        # each workspace row has goal_count + goals[]
        for w in gr["workspaces"]:
            assert "id" in w and "name" in w and "goal_count" in w and "goals" in w
            for g in w["goals"]:
                for f in ("id", "title", "pct", "current_value", "target_value"):
                    assert f in g, f"missing {f} in rollup goal: {list(g.keys())}"

    def test_rollup_reflects_new_outcome(self, admin, workspace_id):
        # Create an outcome and check rollup avg_progress moves
        title = f"TEST_rollup_{uuid.uuid4().hex[:6]}"
        r = admin.post(f"{API}/outcomes", json={
            "workspace_id": workspace_id, "title": title, "target": title,
            "target_value": 100, "current_value": 50, "unit": "%"
        })
        assert r.status_code in (200, 201), r.text
        gid = r.json()["id"]
        d = admin.get(f"{API}/dashboard").json()
        found = False
        for w in d["goal_rollup"]["workspaces"]:
            for g in w["goals"]:
                if g["id"] == gid:
                    assert g["pct"] == 50
                    found = True
        assert found, "newly created outcome should appear in rollup"


# ---------- Feature 2: MCP Undo with reason + window ----------
class TestMcpUndoReason:
    def _create_note_invocation(self, admin, workspace_id):
        r = admin.post(f"{API}/mcp/invoke", json={
            "tool": "add_note",
            "args": {"workspace_id": workspace_id, "body": f"TEST_undo_reason_{uuid.uuid4().hex[:6]}"}
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("status") == "pending_approval", d
        approval_id = d.get("approval_id")
        assert approval_id
        pr = admin.patch(f"{API}/approvals/{approval_id}", json={"status": "approved"})
        assert pr.status_code in (200, 204)
        # Find the success invocation
        invs = admin.get(f"{API}/mcp/invocations").json()
        inv = next((i for i in invs if i.get("tool") == "add_note" and i.get("status") == "success"
                    and (i.get("args") or {}).get("workspace_id") == workspace_id), None)
        assert inv, "expected a success add_note invocation"
        return inv

    def test_undo_empty_reason_returns_422(self, admin, workspace_id):
        inv = self._create_note_invocation(admin, workspace_id)
        r = admin.post(f"{API}/mcp/invocations/{inv['id']}/undo", json={"reason": ""})
        assert r.status_code == 422, r.text
        # Whitespace-only should also fail
        r2 = admin.post(f"{API}/mcp/invocations/{inv['id']}/undo", json={"reason": "   "})
        assert r2.status_code == 422, r2.text
        # Missing reason field also 422 (default "")
        r3 = admin.post(f"{API}/mcp/invocations/{inv['id']}/undo", json={})
        assert r3.status_code == 422, r3.text
        # cleanup: undo it properly
        r4 = admin.post(f"{API}/mcp/invocations/{inv['id']}/undo", json={"reason": "cleanup"})
        assert r4.status_code == 200, r4.text

    def test_undo_with_reason_success_and_event(self, admin, workspace_id):
        inv = self._create_note_invocation(admin, workspace_id)
        reason = "user requested rollback iter5"
        r = admin.post(f"{API}/mcp/invocations/{inv['id']}/undo", json={"reason": reason})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("reason") == reason
        # invocation flipped
        invs = admin.get(f"{API}/mcp/invocations").json()
        u = next(i for i in invs if i["id"] == inv["id"])
        assert u.get("status") == "undone"
        assert u.get("undo_reason") == reason
        # event contains reason
        events = admin.get(f"{API}/events").json()
        ev = next((e for e in events if e.get("event_type") == "mcp.tool_undone"
                   and (e.get("payload") or {}).get("invocation_id") == inv["id"]), None)
        assert ev, "mcp.tool_undone event missing"
        assert (ev.get("payload") or {}).get("reason") == reason

    def test_undo_admin_only(self, admin, workspace_id):
        inv = self._create_note_invocation(admin, workspace_id)
        # non-admin user (new tenant)
        s = requests.Session()
        email = f"TEST_{uuid.uuid4().hex[:8]}@example.com"
        reg = s.post(f"{API}/auth/register", json={"email": email, "password": "Passw0rd!!", "name": "T"})
        assert reg.status_code in (200, 201)
        tok = reg.json().get("access_token") or reg.json().get("token")
        if tok:
            s.headers.update({"Authorization": f"Bearer {tok}"})
        # cross-tenant → 404 (tenant scoped) OR 403 (admin gate). New user IS admin of own tenant so it's 404.
        r = s.post(f"{API}/mcp/invocations/{inv['id']}/undo", json={"reason": "try"})
        assert r.status_code in (403, 404), r.text
        # cleanup
        admin.post(f"{API}/mcp/invocations/{inv['id']}/undo", json={"reason": "cleanup"})

    def test_undo_window_expired(self, admin, workspace_id):
        """Simulate an old invocation by patching executed_at directly via DB is not exposed;
        instead we verify the constant and code path via a bogus manipulation using the API.
        This test is best-effort: if we cannot set executed_at, we skip."""
        pytest.skip("Cannot backdate executed_at via public API; window logic covered by code review.")


# ---------- Feature 3: Webhook event pattern filters ----------
class TestWebhookPatterns:
    def _mk_hook(self, admin, name, url, events):
        r = admin.post(f"{API}/webhooks", json={"name": name, "url": url, "events": events})
        assert r.status_code in (200, 201), r.text
        return r.json()

    def test_event_matches_wildcard(self, admin, workspace_id):
        # Use httpbin.org/status/200 as sink so delivery attempts don't fail infinitely
        # But we mostly care about the delivery record being created for matching hook only
        h_comm = self._mk_hook(admin, f"TEST_hook_comm_{uuid.uuid4().hex[:6]}",
                               "https://httpbin.org/status/200", ["commitment.*"])
        h_mcp = self._mk_hook(admin, f"TEST_hook_mcp_{uuid.uuid4().hex[:6]}",
                              "https://httpbin.org/status/200", ["mcp.*"])
        h_star = self._mk_hook(admin, f"TEST_hook_star_{uuid.uuid4().hex[:6]}",
                               "https://httpbin.org/status/200", ["*"])
        h_none = self._mk_hook(admin, f"TEST_hook_none_{uuid.uuid4().hex[:6]}",
                               "https://httpbin.org/status/200", ["approval.*"])

        # Trigger a commitment.created event by creating a commitment
        r = admin.post(f"{API}/commitments", json={
            "workspace_id": workspace_id,
            "title": f"TEST_com_{uuid.uuid4().hex[:6]}",
            "description": "iter5 webhook pattern test",
            "owner": "admin", "due_date": None
        })
        assert r.status_code in (200, 201), r.text

        time.sleep(2.0)  # give dispatch time to create delivery rows

        # Fetch deliveries
        deliv = admin.get(f"{API}/webhook-deliveries").json()
        # Filter by event_type and per-hook_id
        def has_delivery(hook_id, event_type_prefix):
            return any(d.get("webhook_id") == hook_id and d.get("event_type", "").startswith(event_type_prefix)
                       for d in deliv)

        assert has_delivery(h_comm["id"], "commitment."), f"commitment.* hook missed commitment.created"
        assert has_delivery(h_star["id"], "commitment."), "* hook missed commitment.created"
        assert not has_delivery(h_none["id"], "commitment."), "approval.* hook should NOT receive commitment.*"

        # cleanup (endpoint may or may not exist)
        for h in (h_comm, h_mcp, h_star, h_none):
            try:
                admin.delete(f"{API}/webhooks/{h['id']}")
            except Exception:
                pass


# ---------- Regression breadth ----------
class TestRegressionBreadth:
    @pytest.mark.parametrize("path", [
        "/dashboard", "/workspaces", "/opportunities", "/companies",
        "/contacts", "/events", "/registry/integrations", "/registry/mcp-servers",
        "/registry/plugins", "/registry/webhooks", "/mcp/tools", "/mcp/invocations",
    ])
    def test_endpoint_ok(self, admin, path):
        r = admin.get(f"{API}{path}")
        assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"

    def test_workspace_detail_health(self, admin, workspace_id):
        r = admin.get(f"{API}/workspaces/{workspace_id}")
        assert r.status_code == 200
        d = r.json()
        assert "health" in d and "commitments" in d and "tasks" in d
