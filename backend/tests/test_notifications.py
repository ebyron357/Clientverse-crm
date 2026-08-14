import os
import uuid

import requests

from conftest import API, ADMIN_CREDS, MEMBER_CREDS, login, auth_header


def _tok(c):
    return login(c)


def _h(t):
    return auth_header(t)


def _register():
    email = f"ntf_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Pw2026!!", "name": "N"}, timeout=15)
    return r.json()["token"]


def test_alerts_generate_in_app_notifications():
    h = _h(_tok(ADMIN_CREDS))
    ws = requests.get(f"{API}/workspaces", headers=h, timeout=15).json()
    assert ws
    wid = ws[0]["id"]
    from datetime import datetime, timezone, timedelta
    past = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    c = requests.post(f"{API}/commitments", headers=h, json={
        "workspace_id": wid, "title": f"notif-breach-{uuid.uuid4().hex[:6]}",
        "owner": "ops", "due_date": past, "status": "open",
    }, timeout=15)
    assert c.status_code == 200, c.text
    requests.post(f"{API}/commitments/evaluate-risk", headers=h, timeout=30)
    requests.post(f"{API}/alerts/evaluate", headers=h, timeout=30)
    openq = requests.get(f"{API}/alerts?status=open", headers=h, timeout=15).json()
    assert openq["counts"]["open"] >= 1, "expected at least one open alert to drive a notification"
    target = openq["alerts"][0]
    requests.post(f"{API}/alerts/{target['id']}/acknowledge", headers=h, timeout=15)
    d = requests.get(f"{API}/notifications", headers=h, timeout=15).json()
    assert "notifications" in d and "unread" in d
    assert len(d["notifications"]) >= 1
    n = d["notifications"][0]
    for k in ("id", "title", "severity", "read", "created_at"):
        assert k in n
    assert n["severity"] in ("info", "warning", "critical")


def test_mark_read_and_read_all():
    h = _h(_tok(ADMIN_CREDS))
    requests.post(f"{API}/alerts/evaluate", headers=h, timeout=30)
    d = requests.get(f"{API}/notifications", headers=h, timeout=15).json()
    if d["unread"]:
        unread = next(n for n in d["notifications"] if not n["read"])
        assert requests.post(f"{API}/notifications/{unread['id']}/read", headers=h, timeout=15).status_code == 200
    assert requests.post(f"{API}/notifications/read-all", headers=h, timeout=15).status_code == 200
    after = requests.get(f"{API}/notifications", headers=h, timeout=15).json()
    assert after["unread"] == 0


def test_mark_read_not_found():
    h = _h(_tok(ADMIN_CREDS))
    assert requests.post(f"{API}/notifications/does-not-exist/read", headers=h, timeout=15).status_code == 404


def test_notifications_tenant_isolation():
    other = _h(_register())
    d = requests.get(f"{API}/notifications", headers=other, timeout=15).json()
    assert d["unread"] == 0 and d["notifications"] == []


def test_get_preferences_shape():
    h = _h(_tok(ADMIN_CREDS))
    d = requests.get(f"{API}/notifications/preferences", headers=h, timeout=15).json()
    for k in ("tenant_default", "mine", "effective", "email_configured", "is_admin"):
        assert k in d
    eff = d["effective"]
    assert "channels" in eff and "digest_time" in eff and "timezone" in eff
    assert d["is_admin"] is True


def test_user_can_set_own_preferences():
    h = _h(_tok(ADMIN_CREDS))
    r = requests.put(f"{API}/notifications/preferences/me",
                     json={"prefs": {"digest_time": "09:30", "timezone": "America/New_York", "billing": False}},
                     headers=h, timeout=15)
    assert r.status_code == 200, r.text
    eff = r.json()["effective"]
    assert eff["digest_time"] == "09:30" and eff["timezone"] == "America/New_York" and eff["billing"] is False
    requests.put(f"{API}/notifications/preferences/me",
                 json={"prefs": {"digest_time": "08:00", "timezone": "UTC", "billing": True}}, headers=h, timeout=15)


def test_member_cannot_set_tenant_defaults():
    m = _h(_tok(MEMBER_CREDS))
    r = requests.put(f"{API}/notifications/preferences/tenant", json={"prefs": {"digest_time": "07:00"}}, headers=m, timeout=15)
    assert r.status_code == 403


def test_admin_can_set_tenant_defaults():
    h = _h(_tok(ADMIN_CREDS))
    r = requests.put(f"{API}/notifications/preferences/tenant", json={"prefs": {"escalation_minutes": 45}}, headers=h, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["tenant_default"]["escalation_minutes"] == 45
    requests.put(f"{API}/notifications/preferences/tenant", json={"prefs": {"escalation_minutes": 60}}, headers=h, timeout=15)


def test_digest_preview_is_deterministic_from_data():
    h = _h(_tok(ADMIN_CREDS))
    r = requests.get(f"{API}/digest/preview", headers=h, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "counts" in d and "generated_at" in d
    for k in ("attention", "breached", "at_risk", "overdue", "approvals", "alerts", "integration_failures"):
        assert k in d["counts"] and isinstance(d["counts"][k], int)


def test_digest_preview_member_forbidden():
    m = _h(_tok(MEMBER_CREDS))
    assert requests.get(f"{API}/digest/preview", headers=m, timeout=15).status_code == 403


def test_digest_run_admin_only_and_returns_status():
    m = _h(_tok(MEMBER_CREDS))
    assert requests.post(f"{API}/digest/run", headers=m, timeout=20).status_code == 403
    h = _h(_tok(ADMIN_CREDS))
    r = requests.post(f"{API}/digest/run", headers=h, timeout=40)
    assert r.status_code == 200, r.text
    assert r.json()["status"] in ("delivered", "partial", "not_configured", "failed", "skipped")


def test_escalation_admin_only():
    m = _h(_tok(MEMBER_CREDS))
    assert requests.post(f"{API}/alerts/escalate", headers=m, timeout=15).status_code == 403
    h = _h(_tok(ADMIN_CREDS))
    r = requests.post(f"{API}/alerts/escalate", headers=h, timeout=20)
    assert r.status_code == 200 and "escalated" in r.json()


def test_no_secret_leakage_in_notifications():
    h = _h(_tok(ADMIN_CREDS))
    for url in [f"{API}/notifications", f"{API}/notifications/preferences", f"{API}/digest/preview"]:
        body = requests.get(url, headers=h, timeout=20).text
        for bad in ("EMERGENT_EMAIL_KEY", "ek_", "X-Email-Key", "sk_test_", "sk_live_"):
            assert bad not in body, f"{bad} leaked at {url}"
