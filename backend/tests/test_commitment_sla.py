import os
import requests
from datetime import datetime, timezone, timedelta

from conftest import API, ADMIN_CREDS, login, auth_header


def _token():
    return login(ADMIN_CREDS)


def _headers():
    return auth_header(_token())


def _workspace(h):
    r = requests.get(f"{API}/workspaces", headers=h, timeout=15)
    assert r.status_code == 200
    return r.json()[0]["id"]


def test_sla_flags_overdue_as_breached_and_near_as_at_risk():
    h = _headers()
    ws = _workspace(h)
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    near = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    c1 = requests.post(f"{API}/commitments", headers=h,
                       json={"workspace_id": ws, "title": "pytest-overdue", "due_date": past}, timeout=15).json()
    c2 = requests.post(f"{API}/commitments", headers=h,
                       json={"workspace_id": ws, "title": "pytest-near", "due_date": near}, timeout=15).json()
    assert c1["status"] == "open" and c2["status"] == "open"

    r = requests.post(f"{API}/commitments/evaluate-risk", headers=h, timeout=20)
    assert r.status_code == 200, r.text
    summary = r.json()
    assert c1["id"] in summary["breached_ids"]
    assert c2["id"] in summary["at_risk_ids"]

    detail = requests.get(f"{API}/workspaces/{ws}", headers=h, timeout=15).json()
    by_id = {c["id"]: c for c in detail["commitments"]}
    assert by_id[c1["id"]]["status"] == "breached"
    assert by_id[c2["id"]]["status"] == "at_risk"


def test_commitment_due_date_is_editable():
    h = _headers()
    ws = _workspace(h)
    c = requests.post(f"{API}/commitments", headers=h,
                      json={"workspace_id": ws, "title": "pytest-editable"}, timeout=15).json()
    new_due = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    r = requests.patch(f"{API}/commitments/{c['id']}", headers=h, json={"due_date": new_due}, timeout=15)
    assert r.status_code == 200
    detail = requests.get(f"{API}/workspaces/{ws}", headers=h, timeout=15).json()
    updated = next(x for x in detail["commitments"] if x["id"] == c["id"])
    assert updated["due_date"] == new_due


def test_cron_requires_secret():
    assert requests.post(f"{API}/cron/commitment-risk", timeout=15).status_code == 401
    assert requests.post(f"{API}/cron/commitment-risk",
                         headers={"Authorization": "Bearer wrong"}, timeout=15).status_code == 401


def test_cron_accepts_valid_secret_and_is_idempotent():
    secret = os.environ.get("WEBHOOK_CRON_SECRET")
    if not secret:
        import pytest
        pytest.skip("WEBHOOK_CRON_SECRET not available to test process")
    h = {"Authorization": f"Bearer {secret}", "X-Webhook-Id": "pytest-run-fixed"}
    r1 = requests.post(f"{API}/cron/commitment-risk", headers=h, timeout=15)
    assert r1.status_code == 200 and r1.json().get("accepted") is True
    r2 = requests.post(f"{API}/cron/commitment-risk", headers=h, timeout=15)
    assert r2.status_code == 200 and r2.json().get("duplicate") is True
