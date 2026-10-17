"""HTTP contract for the revenue-recovery correctness fixes.

The engine is covered in-process by `test_recovery_correctness.py`. What is asserted here
is what only the running API can show: validation on the way in, the operator's close
route (reasons, 409 on a closed case, 404 -- never 403 -- for another tenant's case), an
estimate marked invoiced by the route that invoices it, and the dashboard's per-currency
money.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/")
API = f"{BASE}/api"


def _register(label):
    email = f"rcv_http_{label}_{uuid.uuid4().hex[:10]}@example.com"
    response = requests.post(f"{API}/auth/register",
                             json={"email": email, "password": "RecoveryHttp2026!",
                                   "name": f"Recovery HTTP {label}"}, timeout=30)
    assert response.status_code == 200, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body.get('token') or body.get('access_token')}"}


@pytest.fixture(scope="module")
def tenant():
    """A tenant with one open recovery case (an overdue commitment)."""
    headers = _register("a")
    workspace = requests.post(f"{API}/workspaces", headers=headers,
                              json={"name": "Recovery HTTP workspace"}, timeout=30)
    assert workspace.status_code == 200, workspace.text
    overdue = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()
    commitment = requests.post(f"{API}/commitments", headers=headers,
                               json={"title": "Overdue follow-up",
                                     "workspace_id": workspace.json()["id"],
                                     "due_date": overdue}, timeout=30)
    assert commitment.status_code == 200, commitment.text
    detected = requests.post(f"{API}/second-chance/detect", headers=headers, timeout=120)
    assert detected.status_code == 200, detected.text
    return {"headers": headers, "workspace_id": workspace.json()["id"]}


@pytest.fixture(scope="module")
def other_tenant():
    return _register("b")


def test_a_deal_with_a_negative_value_or_a_non_currency_is_refused(tenant):
    headers = tenant["headers"]
    for bad in ({"name": "Neg", "value": -100}, {"name": "Cur", "value": 10, "currency": "$"}):
        response = requests.post(f"{API}/opportunities", headers=headers, json=bad, timeout=30)
        assert response.status_code == 422, response.text
    ok = requests.post(f"{API}/opportunities", headers=headers,
                       json={"name": "Fine", "value": 10, "currency": "gbp"}, timeout=30)
    assert ok.status_code == 200, ok.text
    assert ok.json()["currency"] == "GBP"


def test_an_operator_closes_a_case_with_a_reason(tenant, other_tenant):
    headers = tenant["headers"]
    cases = requests.get(f"{API}/recovery-cases", headers=headers, timeout=30).json()
    assert cases, "the seeded overdue commitment must have opened a case"
    case_id = cases[0]["id"]

    reasons = requests.get(f"{API}/recovery-cases/close-reasons", headers=headers, timeout=30)
    assert "duplicate" in reasons.json()["operator"]
    assert "outcome_recorded" in reasons.json()["system"]

    bad = requests.post(f"{API}/recovery-cases/{case_id}/close", headers=headers,
                        json={"reason": "outcome_recorded"}, timeout=30)
    assert bad.status_code == 422, "a system-only reason is not the operator's to give"
    foreign = requests.post(f"{API}/recovery-cases/{case_id}/close", headers=other_tenant,
                            json={"reason": "duplicate"}, timeout=30)
    assert foreign.status_code == 404, foreign.text

    closed = requests.post(f"{API}/recovery-cases/{case_id}/close", headers=headers,
                           json={"reason": "not_recoverable", "note": "Client moved away"},
                           timeout=30)
    assert closed.status_code == 200, closed.text
    assert closed.json()["state"] == "closed"
    assert closed.json()["close_reason"] == "not_recoverable"
    again = requests.post(f"{API}/recovery-cases/{case_id}/close", headers=headers,
                          json={"reason": "duplicate"}, timeout=30)
    assert again.status_code == 409

    proof = requests.get(f"{API}/proof/cases/{case_id}", headers=headers, timeout=30).json()
    assert proof["case"]["close_reason"] == "not_recoverable"
    portfolio = requests.get(f"{API}/proof/portfolio", headers=headers, timeout=30).json()
    assert portfolio["cases"]["closed_by_reason"].get("not_recoverable") == 1
    assert "open_cases_without_value" in portfolio["revenue"]


def test_reconciliation_can_be_run_on_demand(tenant):
    response = requests.post(f"{API}/recovery-cases/reconcile", headers=tenant["headers"],
                             timeout=60)
    assert response.status_code == 200, response.text
    assert {"examined", "closed", "outcomes", "errors"} <= set(response.json())


def test_invoicing_an_estimate_marks_it_invoiced(tenant):
    headers = tenant["headers"]
    estimate = requests.post(f"{API}/estimates", headers=headers,
                             json={"workspace_id": tenant["workspace_id"], "title": "Job",
                                   "currency": "USD",
                                   "lines": [{"label": "Work", "quantity": 1,
                                              "unit_price": 500}]}, timeout=30)
    assert estimate.status_code == 200, estimate.text
    estimate_id = estimate.json()["id"]
    sent = requests.patch(f"{API}/estimates/{estimate_id}", headers=headers,
                          json={"status": "sent"}, timeout=30)
    assert sent.status_code == 200, sent.text
    invoiced = requests.post(f"{API}/estimates/{estimate_id}/invoice", headers=headers,
                             timeout=30)
    assert invoiced.status_code == 200, invoiced.text
    listed = requests.get(f"{API}/estimates", headers=headers, timeout=30).json()
    marked = next(row for row in listed if row["id"] == estimate_id)
    assert marked["invoice_id"] == invoiced.json()["invoice"]["id"]
    assert marked["status"] == "sent", "the portal reads status; it is deliberately unchanged"


def test_the_dashboard_reports_money_per_currency(tenant):
    created = requests.post(f"{API}/opportunities", headers=tenant["headers"],
                            json={"name": "Swiss", "value": 7, "currency": "CHF"}, timeout=30)
    assert created.status_code == 200, created.text
    data = requests.get(f"{API}/dashboard", headers=tenant["headers"], timeout=30).json()
    assert "pipeline_value_by_currency" in data and "won_value_by_currency" in data
    assert data["pipeline_value_by_currency"].get("CHF") == 7.0
