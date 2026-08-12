import os
import uuid

import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"
API = f"{BASE}/api"
ADMIN = {"email": os.environ.get("ADMIN_EMAIL", "admin@example.com"),
         "password": os.environ.get("ADMIN_PASSWORD", "AdminPass123!")}
MEMBER = {"email": os.environ.get("DEMO_MEMBER_EMAIL", "demo.member@clientverse.io"),
          "password": os.environ.get("DEMO_MEMBER_PASSWORD", "Member2026!")}


def _tok(c):
    r = requests.post(f"{API}/auth/login", json=c, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _admin_workspace_id():
    """Discover a real workspace for the seeded admin tenant (never hard-code IDs)."""
    h = _h(_tok(ADMIN))
    ws = requests.get(f"{API}/workspaces", headers=h, timeout=15)
    assert ws.status_code == 200 and ws.json(), "seeded admin tenant must have at least one workspace"
    return ws.json()[0]["id"]


def _register():
    email = f"ins_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Pw2026!!", "name": "I"}, timeout=15)
    return r.json()["token"]


REQUIRED = {"id", "tenant_id", "workspace_id", "source", "event_type", "title", "summary",
            "occurred_at", "actor", "severity", "ref", "external_ref", "stale", "failure"}


def test_timeline_shape_and_normalization():
    h = _h(_tok(ADMIN))
    ws_id = _admin_workspace_id()
    d = requests.get(f"{API}/workspaces/{ws_id}/timeline?limit=10", headers=h, timeout=20).json()
    assert d["total"] >= 1 and len(d["items"]) <= 10
    for it in d["items"]:
        assert REQUIRED.issubset(it.keys())
        assert it["severity"] in ("info", "warning", "critical")
    # newest-first
    ts = [i["occurred_at"] or "" for i in d["items"]]
    assert ts == sorted(ts, reverse=True)


def test_timeline_filter_and_pagination():
    h = _h(_tok(ADMIN))
    ws_id = _admin_workspace_id()
    full = requests.get(f"{API}/workspaces/{ws_id}/timeline?limit=100", headers=h, timeout=20).json()
    total = full["total"]
    p1 = requests.get(f"{API}/workspaces/{ws_id}/timeline?limit=3&offset=0", headers=h, timeout=20).json()
    p2 = requests.get(f"{API}/workspaces/{ws_id}/timeline?limit=3&offset=3", headers=h, timeout=20).json()
    assert p1["total"] == total == p2["total"]
    ids1 = {i["id"] for i in p1["items"]}
    ids2 = {i["id"] for i in p2["items"]}
    assert not (ids1 & ids2)  # no overlap across pages
    st = requests.get(f"{API}/workspaces/{ws_id}/timeline?sources=stripe&limit=50", headers=h, timeout=20).json()
    assert all(i["source"] == "stripe" for i in st["items"])
    sev = requests.get(f"{API}/workspaces/{ws_id}/timeline?severity=critical&limit=50", headers=h, timeout=20).json()
    assert all(i["severity"] == "critical" for i in sev["items"])


def test_timeline_tenant_isolation():
    other = _h(_register())
    ws_id = _admin_workspace_id()
    r = requests.get(f"{API}/workspaces/{ws_id}/timeline", headers=other, timeout=15)
    assert r.status_code == 404


def test_alert_creation_dedupe_and_lifecycle():
    h = _h(_tok(ADMIN))
    requests.post(f"{API}/alerts/evaluate", headers=h, timeout=30)
    first = requests.get(f"{API}/alerts?status=open", headers=h, timeout=15).json()
    open_count = first["counts"]["open"]
    assert open_count >= 1
    target = first["alerts"][0]
    prev_occ = target["occurrence_count"]
    # re-evaluate -> persistent conditions dedupe (increment occurrence, not duplicate rows)
    requests.post(f"{API}/alerts/evaluate", headers=h, timeout=30)
    again = requests.get(f"{API}/alerts?status=open", headers=h, timeout=15).json()
    assert again["counts"]["open"] == open_count  # no duplicate alerts
    same = next(a for a in again["alerts"] if a["id"] == target["id"])
    assert same["occurrence_count"] >= prev_occ + 1
    # acknowledge then resolve
    assert requests.post(f"{API}/alerts/{target['id']}/acknowledge", headers=h, timeout=15).status_code == 200
    ackd = next(a for a in requests.get(f"{API}/alerts", headers=h, timeout=15).json()["alerts"] if a["id"] == target["id"])
    assert ackd["status"] == "acknowledged" and ackd["acknowledged_by"]
    assert requests.post(f"{API}/alerts/{target['id']}/resolve", headers=h, timeout=15).status_code == 200
    res = next(a for a in requests.get(f"{API}/alerts?status=resolved", headers=h, timeout=15).json()["alerts"] if a["id"] == target["id"])
    assert res["status"] == "resolved" and res["resolved_at"]


def test_alerts_tenant_isolation():
    other = _h(_register())
    d = requests.get(f"{API}/alerts", headers=other, timeout=15).json()
    assert d["counts"]["open"] == 0 and d["alerts"] == []


def test_health_signals_have_source_references():
    h = _h(_tok(ADMIN))
    ws_id = _admin_workspace_id()
    d = requests.get(f"{API}/workspaces/{ws_id}/health-signals", headers=h, timeout=15).json()
    for s in d["signals"]:
        assert s["source_ref"] and "signal" in s and s["severity"] in ("info", "warning", "critical")
        assert "freshness" in s


def test_permissions_connection_health_admin_only():
    m = _h(_tok(MEMBER))
    assert requests.get(f"{API}/integrations/health", headers=m, timeout=15).status_code == 403
    # members may still view timeline + alerts
    ws_id = _admin_workspace_id()
    assert requests.get(f"{API}/workspaces/{ws_id}/timeline", headers=m, timeout=15).status_code == 200
    assert requests.get(f"{API}/alerts", headers=m, timeout=15).status_code == 200


def test_connection_health_fields_and_thresholds():
    h = _h(_tok(ADMIN))
    d = requests.get(f"{API}/integrations/health", headers=h, timeout=15).json()
    for p in d["providers"]:
        for k in ("provider", "status", "sync_age_hours", "stale", "reconnect_required", "failure_count"):
            assert k in p
        assert p["reconnect_required"] == (p["status"] in ("expired", "revoked", "error"))


def test_no_secret_leakage_in_insights():
    h = _h(_tok(ADMIN))
    ws_id = _admin_workspace_id()
    for url in [f"{API}/workspaces/{ws_id}/timeline?limit=100", f"{API}/alerts", f"{API}/integrations/health",
                f"{API}/workspaces/{ws_id}/health-signals"]:
        body = requests.get(url, headers=h, timeout=20).text
        for bad in ('"enc"', '"oauth_state"', '"code_verifier"', '"access_token"', '"refresh_token"', "sk_test_", "sk_live_", "ya29."):
            assert bad not in body, f"{bad} leaked at {url}"


def test_existing_crm_unaffected():
    h = _h(_tok(MEMBER))
    for p in ["/companies", "/workspaces", "/dashboard"]:
        assert requests.get(f"{API}{p}", headers=h, timeout=15).status_code == 200
