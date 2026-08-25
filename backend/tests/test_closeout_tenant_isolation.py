import os
import uuid
from datetime import datetime, timedelta, timezone

import requests


BASE = os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"
API = f"{BASE}/api"
ADMIN = {
    "email": os.environ.get("ADMIN_EMAIL", "admin@example.com"),
    "password": os.environ.get("ADMIN_PASSWORD", "AdminPass123!"),
}


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _admin_token():
    response = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _tenant_b_token():
    response = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"isolation_b_{uuid.uuid4().hex[:10]}@example.com",
            "password": "IsolationPass2026!",
            "name": "Tenant B Test User",
        },
        timeout=15,
    )
    assert response.status_code == 200, response.text
    return response.json()["token"]


def test_closeout_tenant_isolation_for_client_value_resources():
    tenant_a_headers = _headers(_admin_token())
    tenant_b_headers = _headers(_tenant_b_token())
    workspace_response = requests.get(f"{API}/workspaces", headers=tenant_a_headers, timeout=15)
    assert workspace_response.status_code == 200, workspace_response.text
    workspace_id = workspace_response.json()[0]["id"]
    suffix = uuid.uuid4().hex[:8]

    document = requests.post(
        f"{API}/documents",
        headers=tenant_a_headers,
        json={"workspace_id": workspace_id, "title": f"Isolation document {suffix}"},
        timeout=15,
    )
    assert document.status_code == 200, document.text

    estimate = requests.post(
        f"{API}/estimates",
        headers=tenant_a_headers,
        json={
            "workspace_id": workspace_id,
            "title": f"Isolation estimate {suffix}",
            "lines": [{"label": "Controlled service", "quantity": 1, "unit_price": 100}],
        },
        timeout=15,
    )
    assert estimate.status_code == 200, estimate.text
    estimate_id = estimate.json()["id"]
    assert requests.patch(
        f"{API}/estimates/{estimate_id}",
        headers=tenant_a_headers,
        json={"status": "sent"},
        timeout=15,
    ).status_code == 200
    invoice = requests.post(f"{API}/estimates/{estimate_id}/invoice", headers=tenant_a_headers, timeout=15)
    assert invoice.status_code == 200, invoice.text

    slot = datetime.now(timezone.utc) + timedelta(days=90, minutes=int(uuid.uuid4().hex[:6], 16))
    start = slot.isoformat()
    end = (slot + timedelta(hours=1)).isoformat()
    appointment = requests.post(
        f"{API}/appointments",
        headers=tenant_a_headers,
        json={"workspace_id": workspace_id, "title": f"Isolation appointment {suffix}", "owner": ADMIN["email"], "start_at": start, "end_at": end},
        timeout=15,
    )
    assert appointment.status_code == 200, appointment.text
    checkin = requests.post(
        f"{API}/field/check-ins",
        headers=tenant_a_headers,
        json={"workspace_id": workspace_id, "location_label": "Controlled test location"},
        timeout=15,
    )
    assert checkin.status_code == 200, checkin.text
    portal = requests.post(
        f"{API}/portal-links",
        headers=tenant_a_headers,
        json={"workspace_id": workspace_id, "client_label": f"Isolation portal {suffix}"},
        timeout=15,
    )
    assert portal.status_code == 200, portal.text

    reads = {
        "workspace": requests.get(f"{API}/workspaces/{workspace_id}", headers=tenant_b_headers, timeout=15),
        "documents": requests.get(f"{API}/documents?workspace_id={workspace_id}", headers=tenant_b_headers, timeout=15),
        "estimates": requests.get(f"{API}/estimates?workspace_id={workspace_id}", headers=tenant_b_headers, timeout=15),
        "invoices": requests.get(f"{API}/invoices?workspace_id={workspace_id}", headers=tenant_b_headers, timeout=15),
        "appointments": requests.get(f"{API}/appointments?workspace_id={workspace_id}", headers=tenant_b_headers, timeout=15),
        "checkins": requests.get(f"{API}/field/check-ins?workspace_id={workspace_id}", headers=tenant_b_headers, timeout=15),
        "integration_activity": requests.get(f"{API}/integrations/workspaces/{workspace_id}/activity", headers=tenant_b_headers, timeout=15),
    }
    assert all(response.status_code == 404 for response in reads.values())

    mutations = {
        "document": requests.patch(f"{API}/documents/{document.json()['id']}", headers=tenant_b_headers, json={"status": "shared"}, timeout=15),
        "estimate": requests.patch(f"{API}/estimates/{estimate_id}", headers=tenant_b_headers, json={"status": "approved"}, timeout=15),
        "invoice": requests.patch(f"{API}/invoices/{invoice.json()['invoice']['id']}", headers=tenant_b_headers, json={"status": "paid"}, timeout=15),
        "appointment": requests.patch(f"{API}/appointments/{appointment.json()['id']}", headers=tenant_b_headers, json={"status": "cancelled"}, timeout=15),
        "portal_link": requests.patch(f"{API}/portal-links/{portal.json()['portal_link']['id']}", headers=tenant_b_headers, json={"status": "revoked"}, timeout=15),
    }
    assert all(response.status_code in (403, 404) for response in mutations.values())
    assert requests.get(f"{API}/portal-links", headers=tenant_b_headers, timeout=15).json() == []
