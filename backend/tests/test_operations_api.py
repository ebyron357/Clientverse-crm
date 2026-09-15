"""HTTP surface for the work queue, Second Chance, Next Best Action and security gate.

The engine semantics are covered by the unit suites. What matters here is the API
contract: authentication, admin-only routes, tenant isolation on every read and
write, and that no route accepts a caller-supplied tenant.
"""

import os
import uuid

import pytest
import requests

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/")
API = f"{BASE}/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "AdminPass123!")


def _token(email, password):
    response = requests.post(f"{API}/auth/login", json={"email": email, "password": password},
                             timeout=30)
    assert response.status_code == 200, response.text
    body = response.json()
    return body.get("token") or body.get("access_token")


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin_token():
    return _token(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def other_tenant_token():
    email = f"ops_isolation_{uuid.uuid4().hex[:10]}@example.com"
    response = requests.post(f"{API}/auth/register",
                             json={"email": email, "password": "IsolationPass2026!",
                                   "name": "Ops Isolation User"}, timeout=30)
    assert response.status_code == 200, response.text
    body = response.json()
    return body.get("token") or body.get("access_token")


# ------------------------------------------------------------ authentication

@pytest.mark.parametrize("path", [
    "/work-queue", "/work-queue/stats", "/next-best-actions",
    "/next-best-actions/summary", "/security-gate/status", "/security-gate/components",
])
def test_operations_routes_require_authentication(path):
    assert requests.get(f"{API}{path}", timeout=30).status_code == 401


def test_work_queue_and_recommendations_are_readable_by_a_member(admin_token):
    for path in ("/work-queue", "/next-best-actions"):
        response = requests.get(f"{API}{path}", headers=_headers(admin_token), timeout=30)
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# ------------------------------------------------------------- second chance

MEMBER_EMAIL = os.environ.get("DEMO_MEMBER_EMAIL", "")
MEMBER_PASSWORD = os.environ.get("DEMO_MEMBER_PASSWORD", "")


@pytest.fixture(scope="module")
def member_token():
    """A non-admin member of the administrator's tenant.

    A freshly registered user is an admin of their own tenant, so it cannot prove an
    admin-only rule. The seeded demo member can.
    """
    if not MEMBER_EMAIL or not MEMBER_PASSWORD:
        pytest.skip("DEMO_MEMBER_EMAIL/DEMO_MEMBER_PASSWORD are not configured")
    return _token(MEMBER_EMAIL, MEMBER_PASSWORD)


@pytest.mark.parametrize("method,path,body", [
    ("post", "/second-chance/detect", None),
    ("post", "/security-gate/components",
     {"name": "x", "kind": "skill", "source_url": "https://example.invalid/x", "version": "1"}),
])
def test_admin_only_routes_reject_a_member(member_token, method, path, body):
    response = getattr(requests, method)(f"{API}{path}", headers=_headers(member_token),
                                         json=body, timeout=60)
    assert response.status_code == 403, response.text


def test_a_member_can_still_read_operations_surfaces(member_token):
    for path in ("/work-queue", "/next-best-actions", "/security-gate/status"):
        assert requests.get(f"{API}{path}", headers=_headers(member_token),
                            timeout=30).status_code == 200


def test_second_chance_detection_returns_an_explainable_summary(admin_token):
    response = requests.post(f"{API}/second-chance/detect", headers=_headers(admin_token),
                             timeout=120)
    assert response.status_code == 200, response.text
    body = response.json()
    for key in ("stalled_leads_detected", "missed_followups_detected", "work_items_created",
                "work_items_deduplicated", "thresholds"):
        assert key in body
    assert body["thresholds"]["stalled_lead_days"] >= 1


def test_second_chance_candidates_are_tenant_scoped(admin_token, other_tenant_token):
    requests.post(f"{API}/second-chance/detect", headers=_headers(admin_token), timeout=120)
    mine = requests.get(f"{API}/second-chance/candidates", headers=_headers(admin_token),
                        timeout=30)
    theirs = requests.get(f"{API}/second-chance/candidates",
                          headers=_headers(other_tenant_token), timeout=30)
    assert mine.status_code == 200 and theirs.status_code == 200
    mine_ids = {item["id"] for item in mine.json()}
    theirs_ids = {item["id"] for item in theirs.json()}
    assert mine_ids.isdisjoint(theirs_ids)


def test_work_item_from_another_tenant_is_not_readable(admin_token, other_tenant_token):
    requests.post(f"{API}/second-chance/detect", headers=_headers(admin_token), timeout=120)
    items = requests.get(f"{API}/work-queue", headers=_headers(admin_token), timeout=30).json()
    if not items:
        pytest.skip("No work items available in the administrator tenant for this assertion")
    victim = items[0]["id"]
    response = requests.get(f"{API}/work-queue/{victim}", headers=_headers(other_tenant_token),
                            timeout=30)
    assert response.status_code == 404


def test_work_item_acknowledge_and_resolve_round_trip(admin_token):
    requests.post(f"{API}/second-chance/detect", headers=_headers(admin_token), timeout=120)
    items = requests.get(f"{API}/work-queue?status=open", headers=_headers(admin_token),
                         timeout=30).json()
    if not items:
        pytest.skip("No open work items available for this assertion")
    item_id = items[0]["id"]

    acked = requests.post(f"{API}/work-queue/{item_id}/acknowledge",
                          headers=_headers(admin_token), timeout=30)
    assert acked.status_code == 200
    assert acked.json()["acknowledged_by"]

    resolved = requests.post(f"{API}/work-queue/{item_id}/resolve",
                             headers=_headers(admin_token), json={"resolution": "contacted"},
                             timeout=30)
    assert resolved.status_code == 200
    assert resolved.json()["resolution"] == "contacted"


def test_work_queue_stats_shape(admin_token):
    response = requests.get(f"{API}/work-queue/stats", headers=_headers(admin_token), timeout=30)
    assert response.status_code == 200
    body = response.json()
    for key in ("queued", "dead_letter", "open", "total", "needs_operator"):
        assert key in body


# ------------------------------------------------------ next best action API

def test_next_best_action_generate_and_feedback(admin_token):
    generated = requests.post(f"{API}/next-best-actions/generate",
                              headers=_headers(admin_token), timeout=120)
    assert generated.status_code == 200, generated.text
    assert "evaluated" in generated.json()

    items = requests.get(f"{API}/next-best-actions", headers=_headers(admin_token),
                         timeout=30).json()
    if not items:
        pytest.skip("No recommendations generated for the administrator tenant")

    first = items[0]
    assert first["reason"], "every recommendation must carry an explainable reason"
    assert first["source_refs"], "every recommendation must cite its source records"

    patched = requests.patch(f"{API}/next-best-actions/{first['id']}",
                             headers=_headers(admin_token),
                             json={"state": "accepted"}, timeout=30)
    assert patched.status_code == 200
    assert patched.json()["state"] == "accepted"


def test_next_best_action_rejects_an_unsupported_state(admin_token):
    requests.post(f"{API}/next-best-actions/generate", headers=_headers(admin_token), timeout=120)
    items = requests.get(f"{API}/next-best-actions?state=open", headers=_headers(admin_token),
                         timeout=30).json()
    if not items:
        pytest.skip("No recommendations generated for the administrator tenant")
    response = requests.patch(f"{API}/next-best-actions/{items[0]['id']}",
                              headers=_headers(admin_token), json={"state": "teleported"},
                              timeout=30)
    assert response.status_code == 400


def test_next_best_action_cross_tenant_patch_is_denied(admin_token, other_tenant_token):
    requests.post(f"{API}/next-best-actions/generate", headers=_headers(admin_token), timeout=120)
    items = requests.get(f"{API}/next-best-actions", headers=_headers(admin_token),
                         timeout=30).json()
    if not items:
        pytest.skip("No recommendations generated for the administrator tenant")
    response = requests.patch(f"{API}/next-best-actions/{items[0]['id']}",
                              headers=_headers(other_tenant_token),
                              json={"state": "dismissed"}, timeout=30)
    assert response.status_code == 404


def test_next_best_action_summary_shape(admin_token):
    response = requests.get(f"{API}/next-best-actions/summary", headers=_headers(admin_token),
                            timeout=30)
    assert response.status_code == 200
    body = response.json()
    assert "states" in body and "open_by_priority" in body


# -------------------------------------------------------- security gate API

def test_security_gate_status_is_honest_about_scanners(admin_token):
    response = requests.get(f"{API}/security-gate/status", headers=_headers(admin_token),
                            timeout=30)
    assert response.status_code == 200
    body = response.json()
    assert len(body["gates"]) == 2, "the pipeline must not collapse to a single gate"
    scanners = {s["scanner"] for s in body["scanners"]}
    assert {"nvidia_skillspector", "cisco_skill_scanner", "cisco_mcp_scanner"} <= scanners


def test_component_registration_is_admin_only_and_grants_nothing(admin_token):
    payload = {
        "name": "example-external-skill",
        "kind": "skill",
        "source_url": f"https://github.com/example/skill-{uuid.uuid4().hex[:8]}",
        "version": "1.0.0",
    }
    response = requests.post(f"{API}/security-gate/components", headers=_headers(admin_token),
                             json=payload, timeout=30)
    assert response.status_code == 200, response.text
    component = response.json()
    assert component["state"] == "DISCOVERED"

    detail = requests.get(f"{API}/security-gate/components/{component['id']}",
                          headers=_headers(admin_token), timeout=30).json()
    assert detail["eligibility"]["eligible"] is False
    assert detail["eligibility"]["blocking_reasons"]


def test_approval_without_gates_is_refused(admin_token):
    payload = {
        "name": "unvetted-skill",
        "kind": "skill",
        "source_url": f"https://github.com/example/unvetted-{uuid.uuid4().hex[:8]}",
        "version": "2.0.0",
    }
    component = requests.post(f"{API}/security-gate/components", headers=_headers(admin_token),
                              json=payload, timeout=30).json()
    response = requests.post(f"{API}/security-gate/components/{component['id']}/decision",
                             headers=_headers(admin_token),
                             json={"decision": "APPROVED", "rationale": "trusted vendor"},
                             timeout=30)
    assert response.status_code == 400
    assert "Gate A" in response.json()["detail"]


def test_security_gate_components_are_tenant_scoped(admin_token, other_tenant_token):
    payload = {
        "name": "scoped-skill",
        "kind": "mcp_server",
        "source_url": f"https://github.com/example/scoped-{uuid.uuid4().hex[:8]}",
        "version": "1.2.3",
    }
    component = requests.post(f"{API}/security-gate/components", headers=_headers(admin_token),
                              json=payload, timeout=30).json()
    response = requests.get(f"{API}/security-gate/components/{component['id']}",
                            headers=_headers(other_tenant_token), timeout=30)
    assert response.status_code == 404


def test_unknown_gate_check_is_rejected(admin_token):
    payload = {
        "name": "checked-skill",
        "kind": "skill",
        "source_url": f"https://github.com/example/checked-{uuid.uuid4().hex[:8]}",
        "version": "3.0.0",
    }
    component = requests.post(f"{API}/security-gate/components", headers=_headers(admin_token),
                              json=payload, timeout=30).json()
    response = requests.post(f"{API}/security-gate/components/{component['id']}/gate-a",
                             headers=_headers(admin_token),
                             json={"checks": {"vibes": {"result": "pass"}}}, timeout=30)
    assert response.status_code == 400


def test_cron_endpoints_reject_an_unauthenticated_caller():
    for path in ("/cron/work-queue", "/cron/second-chance", "/cron/next-best-actions"):
        assert requests.post(f"{API}{path}", timeout=30).status_code == 401


def test_work_item_replay_is_admin_only(member_token, admin_token):
    items = requests.get(f"{API}/work-queue?status=open", headers=_headers(admin_token),
                         timeout=30).json()
    if not items:
        pytest.skip("No work items available for this assertion")
    response = requests.post(f"{API}/work-queue/{items[0]['id']}/replay",
                             headers=_headers(member_token), timeout=30)
    assert response.status_code == 403
