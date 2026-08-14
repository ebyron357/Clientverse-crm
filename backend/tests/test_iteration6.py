"""Iteration 6 tests:
- Undo Window Config: PATCH /api/workspaces/{id}/undo-window (admin-only, clamps 1..1440, persists)
- Goal Trend Sparklines: /api/dashboard goal_rollup goals include 'trend' array
- Webhook Pattern Preview: POST /api/webhooks/match-preview -> scanned/matched/by_type
"""
import os
import uuid
import pytest
import requests

from conftest import API, ADMIN_CREDS, login, auth_header


@pytest.fixture(scope="module")
def admin_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN_CREDS)
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def user_client():
    """Non-admin user (new tenant via register)."""
    s = requests.Session()
    email = f"TEST_iter6_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "Testpass123!", "name": "Iter6 User"})
    assert r.status_code in (200, 201), r.text
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def workspace_id(admin_client):
    r = admin_client.get(f"{API}/workspaces")
    assert r.status_code == 200
    ws = r.json()
    assert len(ws) > 0, "no workspaces seeded"
    return ws[0]["id"]


# ---------------- Undo Window Config ----------------
class TestUndoWindowConfig:
    def test_patch_set_and_persist(self, admin_client, workspace_id):
        r = admin_client.patch(f"{API}/workspaces/{workspace_id}/undo-window", json={"minutes": 5})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["undo_window_minutes"] == 5
        r2 = admin_client.get(f"{API}/workspaces/{workspace_id}")
        assert r2.status_code == 200
        assert r2.json().get("workspace", {}).get("undo_window_minutes") == 5

    def test_clamp_low(self, admin_client, workspace_id):
        r = admin_client.patch(f"{API}/workspaces/{workspace_id}/undo-window", json={"minutes": 0})
        assert r.status_code == 200
        assert r.json()["undo_window_minutes"] == 1

    def test_clamp_high(self, admin_client, workspace_id):
        r = admin_client.patch(f"{API}/workspaces/{workspace_id}/undo-window", json={"minutes": 100000})
        assert r.status_code == 200
        assert r.json()["undo_window_minutes"] == 1440
        admin_client.patch(f"{API}/workspaces/{workspace_id}/undo-window", json={"minutes": 60})

    def test_non_admin_forbidden(self, user_client, admin_client, workspace_id):
        r = user_client.get(f"{API}/workspaces")
        r2 = user_client.patch(f"{API}/workspaces/{workspace_id}/undo-window", json={"minutes": 10})
        assert r2.status_code in (403, 404), r2.text


# ---------------- Goal Trend Sparklines ----------------
class TestGoalTrend:
    def test_dashboard_goals_have_trend(self, admin_client):
        r = admin_client.get(f"{API}/dashboard")
        assert r.status_code == 200
        gr = r.json().get("goal_rollup")
        assert gr and "workspaces" in gr
        all_goals = []
        for w in gr["workspaces"]:
            all_goals.extend(w.get("goals", []))
        assert len(all_goals) > 0, "no goals present"
        for g in all_goals:
            assert "trend" in g, f"goal missing trend: {g}"
            assert isinstance(g["trend"], list)
        seeded = [g for g in all_goals if g.get("trend") == [30, 45, 55, 65]]
        assert len(seeded) >= 1, f"seeded trend not found; sample={[g.get('trend') for g in all_goals[:5]]}"


# ---------------- Webhook Pattern Preview ----------------
class TestWebhookPreview:
    def test_preview_returns_schema(self, admin_client):
        r = admin_client.post(f"{API}/webhooks/match-preview", json={"patterns": ["*"]})
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("scanned", "matched", "by_type"):
            assert k in body
        assert body["matched"] <= body["scanned"]
        assert body["matched"] > 0
        assert isinstance(body["by_type"], list)

    def test_preview_commitment_pattern(self, admin_client):
        r = admin_client.post(f"{API}/webhooks/match-preview", json={"patterns": ["commitment.*"]})
        assert r.status_code == 200
        body = r.json()
        for bt in body["by_type"]:
            assert bt["event_type"].startswith("commitment.")

    def test_preview_empty_patterns(self, admin_client):
        r = admin_client.post(f"{API}/webhooks/match-preview", json={"patterns": []})
        assert r.status_code == 200
        assert r.json()["matched"] == 0
