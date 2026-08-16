import os
import uuid
from datetime import datetime, timedelta, timezone

import requests


BASE = os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"
API = f"{BASE}/api"
ADMIN = {"email": os.environ.get("ADMIN_EMAIL", "admin@example.com"), "password": os.environ.get("ADMIN_PASSWORD", "AdminPass123!")}


def login():
    response = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert response.status_code == 200, response.text
    return response.json()["token"]


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def workspace(token):
    response = requests.get(f"{API}/workspaces", headers=headers(token), timeout=15)
    assert response.status_code == 200, response.text
    return response.json()[0]


def test_client_portal_redaction_request_and_revoke():
    token = login()
    ws = workspace(token)
    label = f"Portal {uuid.uuid4().hex[:8]}"
    created = requests.post(f"{API}/portal-links", headers=headers(token), json={"workspace_id": ws["id"], "client_label": label}, timeout=15)
    assert created.status_code == 200, created.text
    payload = created.json()
    assert payload["portal_token"] and payload["portal_path"]

    portal = requests.get(f"{API}/portal/{payload['portal_token']}", timeout=15)
    assert portal.status_code == 200, portal.text
    assert portal.json()["workspace"]["name"] == ws["name"]

    created_request = requests.post(f"{API}/portal/{payload['portal_token']}/requests", json={"title": "Portal request", "priority": "high"}, timeout=15)
    assert created_request.status_code == 200, created_request.text

    listed = requests.get(f"{API}/portal-links", headers=headers(token), timeout=15)
    assert listed.status_code == 200
    assert "portal_token" not in listed.text and payload["portal_token"] not in listed.text

    revoked = requests.patch(f"{API}/portal-links/{payload['portal_link']['id']}", headers=headers(token), json={"status": "revoked"}, timeout=15)
    assert revoked.status_code == 200, revoked.text
    assert requests.get(f"{API}/portal/{payload['portal_token']}", timeout=15).status_code == 404


def test_client_value_workflows_are_safe_and_tenant_scoped():
    token = login()
    ws = workspace(token)
    h = headers(token)
    prefix = f"CV {uuid.uuid4().hex[:8]}"

    assert requests.get(f"{API}/client-ops/summary", timeout=15).status_code == 401
    document = requests.post(f"{API}/documents", headers=h, json={"workspace_id": ws["id"], "title": f"{prefix} document", "client_visible": True, "requires_approval": True}, timeout=15)
    assert document.status_code == 200, document.text

    estimate = requests.post(f"{API}/estimates", headers=h, json={"workspace_id": ws["id"], "title": f"{prefix} estimate", "lines": [{"label": "Service", "quantity": 1, "unit_price": 1000}]}, timeout=15)
    assert estimate.status_code == 200, estimate.text
    estimate_id = estimate.json()["id"]
    assert requests.patch(f"{API}/estimates/{estimate_id}", headers=h, json={"status": "sent"}, timeout=15).status_code == 200
    invoice = requests.post(f"{API}/estimates/{estimate_id}/invoice", headers=h, timeout=15)
    assert invoice.status_code == 200, invoice.text
    assert invoice.json()["invoice"]["payment_status"] == "requires_stripe_configuration"
    duplicate = requests.post(f"{API}/estimates/{estimate_id}/invoice", headers=h, timeout=15)
    assert duplicate.status_code == 200 and duplicate.json()["duplicate"] is True

    slot = datetime.now(timezone.utc) + timedelta(days=31, minutes=int(uuid.uuid4().hex[:4], 16))
    start = slot.isoformat()
    end = (slot + timedelta(hours=1)).isoformat()
    appointment = requests.post(f"{API}/appointments", headers=h, json={"title": f"{prefix} appointment", "workspace_id": ws["id"], "owner": ADMIN["email"], "start_at": start, "end_at": end}, timeout=15)
    assert appointment.status_code == 200, appointment.text
    conflict = requests.post(f"{API}/appointments", headers=h, json={"title": f"{prefix} conflict", "workspace_id": ws["id"], "owner": ADMIN["email"], "start_at": start, "end_at": end}, timeout=15)
    assert conflict.status_code == 409
    reminder = requests.post(f"{API}/appointments/{appointment.json()['id']}/reminder", headers=h, timeout=15)
    assert reminder.status_code == 200 and reminder.json()["outbound"] == "disabled"

    rule = requests.post(f"{API}/automations/safe-rules", headers=h, json={"template": "appointment_reminder", "workspace_id": ws["id"], "enabled": True}, timeout=15)
    assert rule.status_code == 200, rule.text
    run = requests.post(f"{API}/automations/safe-rules/{rule.json()['id']}/run", headers=h, timeout=15)
    assert run.status_code == 200 and run.json()["run"]["outbound"] == "disabled"

    outsider_email = f"outsider_{uuid.uuid4().hex[:8]}@example.com"
    outsider = requests.post(f"{API}/auth/register", json={"email": outsider_email, "password": "OutsiderPass2026!", "name": "Outsider"}, timeout=15)
    assert outsider.status_code == 200, outsider.text
    outsider_headers = headers(outsider.json()["token"])
    assert requests.get(f"{API}/documents?workspace_id={ws['id']}", headers=outsider_headers, timeout=15).status_code == 404
