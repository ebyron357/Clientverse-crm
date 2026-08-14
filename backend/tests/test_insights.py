import os
import uuid

import requests

from conftest import API, ADMIN_CREDS, MEMBER_CREDS, login, auth_header


def _tok(c):
    return login(c)


def _h(t):
    return auth_header(t)


def _admin_workspace_id():
    """Discover a real workspace for the seeded admin tenant (never hard-code IDs)."""
    h = _h(_tok(ADMIN_CREDS))
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
    h = _h(_tok(ADMIN_CREDS))
    ws_id = _admin_workspace_id()
    d = requests.get(f"{API}/workspaces/{ws_id}/timeline?limit=10", headers=h, timeout=20).json()
    assert d["total"] >= 1 and len(d["items"]) <= 10
    for it in d["items"]:
        assert REQUIRED.issubset(it.keys())
        assert it["severity"] in ("info", "warning", "critical")
    ts = [i["occurred_at"] or "" for i in d["items"]]
    assert ts == sorted(ts, reverse=True)


def test_timeline_filter_and_pagination():
    h = _h(_tok(ADMIN_CREDS))
    ws_id = _admin_workspace_id()
    full = requests.get(f"{API}/workspaces/{ws_id}/timeline?limit=100", headers=h, timeout=20).json()
    total = full["total"]
    assert total >= 1
    p1 = requests.get(f"{API}/workspaces/{ws_id}/timeline?limit=3&offset=0", headers=h, timeout=20).json()
    p2 = requests.get(f"{API}/workspaces/{ws_id}/timeline?limit=3&offset=3", headers=h, timeout=20).json()
    assert p1["total"] == total == p2["total"]
    ids1 = {i["id"] for i in p1["items"]}
    ids2 = {i["id"] for i in p2["items"]}
    if p1["items"] and p2["items"]:
        assert not (ids1 & ids2)
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
    h = _h(_tok(ADMIN_CREDS))
    from datetime import datetime, timezone, timedelta
    ws = requests.get(f"{API}/workspaces", headers=h, timeout=15).json()
    assert ws
    past = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
    title = f"insight-breach-{uuid.uuid4().hex[:6]}"
    c = requests.post(f"{API}/commitments", headers=h, json={
        "workspace_id": ws[0]["id"], "title": title, "owner": "ops", "due_date": past, "status": "open",
    }, timeout=15)
    assert c.status_code == 200, c.text
    requests.post(f"{API}/commitments/evaluate-risk", headers=h, timeout=30)
    requests.post(f"{API}/alerts/evaluate", headers=h, timeout=30)
    first = requests.get(f"{API}/alerts?status=open", headers=h, timeout=15).json()
    open_count = first["counts"]["open"]
    assert open_count >= 1
    target = next(a for a in first["alerts"] if title in (a.get("summary") or ""))
    prev_occ = target["occurrence_count"]
    requests.post(f"{API}/alerts/evaluate", headers=h, timeout=30)
    again = requests.get(f"{API}/alerts?status=open", headers=h, timeout=15).json()
    same_rows = [a for a in again["alerts"] if a.get("source_ref") == target["source_ref"] and a.get("type") == target["type"]]
    assert len(same_rows) == 1, "dedupe must not create duplicate open rows for the same source_ref"
    same = same_rows[0]
    assert same["id"] == target["id"]
    assert same["occurrence_count"] >= prev_occ + 1
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
    h = _h(_tok(ADMIN_CREDS))
    ws_id = _admin_workspace_id()
    d = requests.get(f"{API}/workspaces/{ws_id}/health-signals", headers=h, timeout=15).json()
    for s in d["signals"]:
        assert s["source_ref"] and "signal" in s and s["severity"] in ("info", "warning", "critical")
        assert "freshness" in s


def test_permissions_connection_health_admin_only():
    m = _h(_tok(MEMBER_CREDS))
    assert requests.get(f"{API}/integrations/health", headers=m, timeout=15).status_code == 403
    ws_id = _admin_workspace_id()
    assert requests.get(f"{API}/workspaces/{ws_id}/timeline", headers=m, timeout=15).status_code == 200
    assert requests.get(f"{API}/alerts", headers=m, timeout=15).status_code == 200


def test_connection_health_fields_and_thresholds():
    h = _h(_tok(ADMIN_CREDS))
    d = requests.get(f"{API}/integrations/health", headers=h, timeout=15).json()
    for p in d["providers"]:
        for k in ("provider", "status", "sync_age_hours", "stale", "reconnect_required", "failure_count"):
            assert k in p
        assert p["reconnect_required"] == (p["status"] in ("expired", "revoked", "error"))


def test_no_secret_leakage_in_insights():
    h = _h(_tok(ADMIN_CREDS))
    ws_id = _admin_workspace_id()
    for url in [f"{API}/workspaces/{ws_id}/timeline?limit=100", f"{API}/alerts", f"{API}/integrations/health",
                f"{API}/workspaces/{ws_id}/health-signals"]:
        body = requests.get(url, headers=h, timeout=20).text
        for bad in ('"enc"', '"oauth_state"', '"code_verifier"', '"access_token"', '"refresh_token"', "sk_test_", "sk_live_", "ya29."):
            assert bad not in body, f"{bad} leaked at {url}"


def test_existing_crm_unaffected():
    h = _h(_tok(MEMBER_CREDS))
    for p in ["/companies", "/workspaces", "/dashboard"]:
        assert requests.get(f"{API}{p}", headers=h, timeout=15).status_code == 200
