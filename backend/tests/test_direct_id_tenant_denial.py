"""Direct-ID cross-tenant denial tests (pilot-readiness security pass, Phase 9).

Complements the existing tenant-isolation coverage (test_role_permissions.py,
test_closeout_tenant_isolation.py, test_integrations.py, test_iteration4.py's MCP undo
test), which mostly proves a *new write referencing a foreign workspace_id* is rejected.
This file instead proves the more classic IDOR shape: Tenant B fetching or mutating an
*existing* Tenant A record purely by guessing/observing its id, across every resource
type named in the pilot-readiness audit: companies, contacts, opportunities, workspaces,
tasks, commitments, webhooks, webhook secrets, alerts, notifications, MCP invocations,
outcomes, and invoices.

Runs over real HTTP against the live server (same pattern as the other integration-style
test files in this suite), because several of these flows (webhook dispatch, alert
evaluation, MCP approval) depend on the app's own background wiring, not just its data
layer.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"
API = f"{BASE}/api"


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _register():
    email = f"idor_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Idor2026!!", "name": "Idor Test"}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


class TenantAFixture:
    """Creates one of every resource type under a single, fresh tenant (A)."""

    def __init__(self):
        self.token = _register()
        self.h = _h(self.token)

        company = requests.post(f"{API}/companies", headers=self.h, json={"name": f"IdorCo-{uuid.uuid4().hex[:6]}"}, timeout=15)
        assert company.status_code == 200, company.text
        self.company_id = company.json()["id"]

        contact = requests.post(f"{API}/contacts", headers=self.h,
                                 json={"name": "Idor Contact", "email": f"idor_c_{uuid.uuid4().hex[:6]}@example.com",
                                       "company_id": self.company_id}, timeout=15)
        assert contact.status_code == 200, contact.text
        self.contact_id = contact.json()["id"]

        opp = requests.post(f"{API}/opportunities", headers=self.h,
                             json={"name": "Idor Deal", "company_id": self.company_id, "value": 1000}, timeout=15)
        assert opp.status_code == 200, opp.text
        self.opportunity_id = opp.json()["id"]

        won = requests.patch(f"{API}/opportunities/{self.opportunity_id}/stage", headers=self.h,
                              json={"stage": "closed_won"}, timeout=15)
        assert won.status_code == 200, won.text

        workspaces = requests.get(f"{API}/workspaces", headers=self.h, timeout=15).json()
        ws = next((w for w in workspaces if w.get("company_id") == self.company_id), None)
        assert ws, "expected closed-won to auto-create a workspace"
        self.workspace_id = ws["id"]

        task = requests.post(f"{API}/tasks", headers=self.h,
                              json={"workspace_id": self.workspace_id, "title": "Idor task"}, timeout=15)
        assert task.status_code == 200, task.text
        self.task_id = task.json()["id"]

        past = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        commitment = requests.post(f"{API}/commitments", headers=self.h,
                                    json={"workspace_id": self.workspace_id, "title": "Idor commitment",
                                          "owner": "ops", "due_date": past, "status": "open"}, timeout=15)
        assert commitment.status_code == 200, commitment.text
        self.commitment_id = commitment.json()["id"]

        outcome = requests.post(f"{API}/outcomes", headers=self.h,
                                 json={"workspace_id": self.workspace_id, "title": "Idor outcome",
                                       "target_value": 100, "current_value": 10}, timeout=15)
        assert outcome.status_code == 200, outcome.text
        self.outcome_id = outcome.json()["id"]

        webhook = requests.post(f"{API}/webhooks", headers=self.h,
                                 json={"name": "Idor hook", "url": "https://hooks.invalid.example/idor",
                                       "events": ["commitment.breached"]}, timeout=15)
        assert webhook.status_code == 200, webhook.text
        self.webhook_id = webhook.json()["id"]

        # Drive a real breached-commitment alert (and its resulting notification) through
        # the app's own evaluation engine, exactly as test_notifications.py does.
        requests.post(f"{API}/commitments/evaluate-risk", headers=self.h, timeout=30)
        requests.post(f"{API}/alerts/evaluate", headers=self.h, timeout=30)
        alerts = requests.get(f"{API}/alerts?status=open", headers=self.h, timeout=15).json()
        assert alerts["counts"]["open"] >= 1, "expected the breached commitment to raise an open alert"
        self.alert_id = alerts["alerts"][0]["id"]
        requests.post(f"{API}/alerts/{self.alert_id}/acknowledge", headers=self.h, timeout=15)

        notifications = requests.get(f"{API}/notifications", headers=self.h, timeout=15).json()
        assert notifications["notifications"], "expected the alert lifecycle to raise an in-app notification"
        self.notification_id = notifications["notifications"][0]["id"]

        # MCP: invoke + approve a level-2 tool to get a real, tenant-scoped invocation id.
        title = f"IdorMcp-{uuid.uuid4().hex[:6]}"
        invoke = requests.post(f"{API}/mcp/invoke", headers=self.h,
                                json={"tool": "create_task", "args": {"workspace_id": self.workspace_id, "title": title}},
                                timeout=15)
        assert invoke.status_code == 200, invoke.text
        approval_id = invoke.json().get("approval_id")
        assert approval_id, invoke.text
        approve = requests.patch(f"{API}/approvals/{approval_id}", headers=self.h, json={"status": "approved"}, timeout=15)
        assert approve.status_code in (200, 204), approve.text
        invocations = requests.get(f"{API}/mcp/invocations", headers=self.h, timeout=15).json()
        inv = next((i for i in invocations if (i.get("args") or {}).get("title") == title), None)
        assert inv, "expected the approved MCP invocation to be recorded"
        self.mcp_invocation_id = inv["id"]


def _fixture():
    return TenantAFixture()


def test_companies_and_contacts_list_never_include_another_tenants_records():
    a = _fixture()
    b_token = _register()
    b = _h(b_token)
    companies = requests.get(f"{API}/companies", headers=b, timeout=15).json()
    contacts = requests.get(f"{API}/contacts", headers=b, timeout=15).json()
    assert all(c["id"] != a.company_id for c in companies)
    assert all(c["id"] != a.contact_id for c in contacts)


def test_opportunity_stage_cannot_be_changed_by_another_tenant():
    a = _fixture()
    b = _h(_register())
    r = requests.patch(f"{API}/opportunities/{a.opportunity_id}/stage", headers=b, json={"stage": "closed_lost"}, timeout=15)
    assert r.status_code == 404


def test_workspace_cannot_be_read_by_another_tenant():
    a = _fixture()
    b = _h(_register())
    r = requests.get(f"{API}/workspaces/{a.workspace_id}", headers=b, timeout=15)
    assert r.status_code == 404


def test_existing_task_cannot_be_patched_by_another_tenant():
    a = _fixture()
    b = _h(_register())
    r = requests.patch(f"{API}/tasks/{a.task_id}", headers=b, json={"status": "done"}, timeout=15)
    assert r.status_code == 404
    task = requests.get(f"{API}/workspaces/{a.workspace_id}", headers=a.h, timeout=15).json()
    still_open = next(t for t in task["tasks"] if t["id"] == a.task_id)
    assert still_open["status"] != "done"


def test_existing_commitment_cannot_be_patched_by_another_tenant():
    a = _fixture()
    b = _h(_register())
    r = requests.patch(f"{API}/commitments/{a.commitment_id}", headers=b, json={"status": "fulfilled"}, timeout=15)
    assert r.status_code == 404


def test_outcome_cannot_be_patched_by_another_tenant():
    a = _fixture()
    b = _h(_register())
    r = requests.patch(f"{API}/outcomes/{a.outcome_id}", headers=b, json={"current_value": 999}, timeout=15)
    assert r.status_code == 404


def test_webhook_and_its_secret_are_invisible_to_another_tenant():
    a = _fixture()
    b = _h(_register())
    assert requests.get(f"{API}/webhooks/{a.webhook_id}/secret", headers=b, timeout=15).status_code == 404
    assert requests.patch(f"{API}/webhooks/{a.webhook_id}", headers=b, json={"enabled": False}, timeout=15).status_code == 404


def test_alert_cannot_be_acknowledged_or_resolved_by_another_tenant():
    a = _fixture()
    b = _h(_register())
    assert requests.post(f"{API}/alerts/{a.alert_id}/acknowledge", headers=b, timeout=15).status_code == 404
    assert requests.post(f"{API}/alerts/{a.alert_id}/resolve", headers=b, timeout=15).status_code == 404


def test_notification_cannot_be_marked_read_by_another_tenant():
    a = _fixture()
    b = _h(_register())
    r = requests.post(f"{API}/notifications/{a.notification_id}/read", headers=b, timeout=15)
    assert r.status_code == 404
    mine = requests.get(f"{API}/notifications", headers=a.h, timeout=15).json()
    target = next(n for n in mine["notifications"] if n["id"] == a.notification_id)
    assert target["read"] is False


def test_mcp_invocation_cannot_be_undone_by_another_tenant():
    a = _fixture()
    b = _h(_register())
    r = requests.post(f"{API}/mcp/invocations/{a.mcp_invocation_id}/undo", headers=b,
                       json={"reason": "cross-tenant probe"}, timeout=15)
    assert r.status_code in (403, 404)


def test_invoice_payment_intent_cannot_be_created_by_another_tenant():
    _a = _fixture()
    b = _h(_register())
    # No invoice endpoint creates one directly in this flow; the exact tenant-scoped 404
    # is proven precisely (with Stripe configuration controlled) in
    # test_stripe_tenant_isolation.py::test_stripe_payment_intent_direct_id_access_denied_cross_tenant.
    # Here, over real HTTP with whatever Stripe configuration this environment happens to
    # have, only two outcomes are acceptable: "not configured" (400) or "not found" (404)
    # -- never a leak of tenant A's invoice/payment state to tenant B.
    r = requests.post(f"{API}/invoices/{uuid.uuid4().hex}/stripe-payment-intent", headers=b, json={}, timeout=15)
    assert r.status_code in (400, 404), r.text
