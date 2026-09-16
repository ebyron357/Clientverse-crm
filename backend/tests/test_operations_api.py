"""HTTP surface for the work queue, Second Chance, the recovery strategy composer,
the approval queue, Next Best Action and the security gate.

The engine semantics are covered by the unit suites. What matters here is the API
contract: authentication, admin-only routes, tenant isolation on every read and
write, and that no route accepts a caller-supplied tenant.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

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


@pytest.fixture(scope="module")
def seeded_tenant():
    """A disposable tenant with a real recovery candidate and recommendations.

    These assertions used to skip when the database happened to be empty, which meant
    that on a fresh CI database the acknowledge/resolve and feedback paths were never
    exercised at all. Seeding here makes the coverage unconditional.
    """
    email = f"ops_seeded_{uuid.uuid4().hex[:10]}@example.com"
    registered = requests.post(f"{API}/auth/register",
                               json={"email": email, "password": "SeededTenant2026!",
                                     "name": "Ops Seeded Tenant"}, timeout=30)
    assert registered.status_code == 200, registered.text
    token = registered.json().get("token") or registered.json().get("access_token")
    headers = _headers(token)

    company = requests.post(f"{API}/companies", headers=headers,
                            json={"name": "OPS-API Recovery Co", "industry": "Testing",
                                  "website": "ops-api.example", "tier": "growth"}, timeout=30)
    assert company.status_code == 200, company.text
    workspace = requests.post(f"{API}/workspaces", headers=headers,
                              json={"name": "OPS-API workspace",
                                    "company_id": company.json()["id"],
                                    "stage": "onboarding"}, timeout=30)
    assert workspace.status_code == 200, workspace.text
    overdue = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()
    commitment = requests.post(f"{API}/commitments", headers=headers,
                               json={"title": "OPS-API overdue follow-up",
                                     "workspace_id": workspace.json()["id"],
                                     "due_date": overdue}, timeout=30)
    assert commitment.status_code == 200, commitment.text

    detected = requests.post(f"{API}/second-chance/detect", headers=headers, timeout=120)
    assert detected.status_code == 200, detected.text
    assert detected.json()["work_items_created"] >= 1, detected.text
    generated = requests.post(f"{API}/next-best-actions/generate", headers=headers, timeout=120)
    assert generated.status_code == 200, generated.text
    return token


# ------------------------------------------------------------ authentication

@pytest.mark.parametrize("path", [
    "/work-queue", "/work-queue/stats", "/next-best-actions",
    "/next-best-actions/summary", "/security-gate/status", "/security-gate/components",
    "/approval-queue", "/approval-queue/summary", "/recovery-strategies",
    "/recovery-strategies/summary", "/recovery-strategies/channel-authority",
    "/conversations", "/conversations/summary",
    "/recovery-cases", "/recovery-cases/summary", "/recovery-cases/rc_nonexistent",
    "/attribution", "/attribution/summary", "/attribution/cases/rc_nonexistent",
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
    ("post", "/recovery-strategies/compose", None),
    ("post", "/recovery-cases/rc_nonexistent/run", None),
    ("post", "/attribution/cases/rc_nonexistent/refresh", None),
    ("post", "/attribution/cases/rc_nonexistent/assert", {"reason": "because"}),
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


def test_work_item_from_another_tenant_is_not_readable(seeded_tenant, other_tenant_token):
    items = requests.get(f"{API}/work-queue", headers=_headers(seeded_tenant), timeout=30).json()
    assert items
    victim = items[0]["id"]
    response = requests.get(f"{API}/work-queue/{victim}", headers=_headers(other_tenant_token),
                            timeout=30)
    assert response.status_code == 404


def test_work_item_acknowledge_and_resolve_round_trip(seeded_tenant):
    headers = _headers(seeded_tenant)
    items = requests.get(f"{API}/work-queue?status=open", headers=headers, timeout=30).json()
    assert items, "the seeded tenant must have an open recovery candidate"
    item_id = items[0]["id"]

    acked = requests.post(f"{API}/work-queue/{item_id}/acknowledge", headers=headers, timeout=30)
    assert acked.status_code == 200, acked.text
    assert acked.json()["acknowledged_by"]

    resolved = requests.post(f"{API}/work-queue/{item_id}/resolve", headers=headers,
                             json={"resolution": "contacted"}, timeout=30)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["resolution"] == "contacted"
    assert resolved.json()["status"] == "completed"


def test_work_queue_stats_shape(admin_token):
    response = requests.get(f"{API}/work-queue/stats", headers=_headers(admin_token), timeout=30)
    assert response.status_code == 200
    body = response.json()
    for key in ("queued", "dead_letter", "open", "total", "needs_operator"):
        assert key in body


# ------------------------------------------------------ next best action API

def test_next_best_action_generate_and_feedback(seeded_tenant):
    headers = _headers(seeded_tenant)
    generated = requests.post(f"{API}/next-best-actions/generate", headers=headers, timeout=120)
    assert generated.status_code == 200, generated.text
    assert "evaluated" in generated.json()
    assert generated.json()["failed_rules"] == [], generated.text

    items = requests.get(f"{API}/next-best-actions", headers=headers, timeout=30).json()
    assert items, "the seeded tenant must have recommendations"

    first = items[0]
    assert first["reason"], "every recommendation must carry an explainable reason"
    assert first["source_refs"], "every recommendation must cite its source records"
    assert "confidence" not in first, "rules are deterministic; no fabricated confidence"

    patched = requests.patch(f"{API}/next-best-actions/{first['id']}", headers=headers,
                             json={"state": "accepted"}, timeout=30)
    assert patched.status_code == 200, patched.text
    assert patched.json()["state"] == "accepted"


def test_next_best_action_rejects_an_unsupported_state(seeded_tenant):
    items = requests.get(f"{API}/next-best-actions?state=open", headers=_headers(seeded_tenant),
                         timeout=30).json()
    assert items
    response = requests.patch(f"{API}/next-best-actions/{items[0]['id']}",
                              headers=_headers(seeded_tenant), json={"state": "teleported"},
                              timeout=30)
    assert response.status_code == 400


def test_next_best_action_cross_tenant_patch_is_denied(seeded_tenant, other_tenant_token):
    items = requests.get(f"{API}/next-best-actions", headers=_headers(seeded_tenant),
                         timeout=30).json()
    assert items
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
    for path in ("/cron/work-queue", "/cron/second-chance", "/cron/next-best-actions",
                 "/cron/recovery-strategies", "/cron/approval-expiry", "/cron/attribution"):
        assert requests.post(f"{API}{path}", timeout=30).status_code == 401


def test_work_item_replay_is_admin_only(member_token, seeded_tenant):
    # Any item will do: an earlier test in this module resolves the open one, so the
    # unfiltered list is what reliably has something to act on.
    items = requests.get(f"{API}/work-queue?status=", headers=_headers(seeded_tenant),
                         timeout=30).json()
    assert items
    response = requests.post(f"{API}/work-queue/{items[0]['id']}/replay",
                             headers=_headers(member_token), timeout=30)
    assert response.status_code in (403, 404)


# ------------------------------------------------------- recovery strategies

@pytest.fixture(scope="module")
def composed_tenant(seeded_tenant):
    """The seeded tenant, with strategies composed for a candidate raised right here.

    It seeds its own overdue commitment rather than reusing the one from
    `seeded_tenant`: earlier tests in this module resolve that work item, and a resolved
    candidate is correctly skipped by the composer. Depending on it would make this
    fixture pass or fail on test ordering rather than on behaviour.
    """
    headers = _headers(seeded_tenant)
    company = requests.post(f"{API}/companies", headers=headers,
                            json={"name": "OPS-API Compose Co", "industry": "Testing",
                                  "website": "ops-compose.example", "tier": "growth"}, timeout=30)
    assert company.status_code == 200, company.text
    workspace = requests.post(f"{API}/workspaces", headers=headers,
                              json={"name": "OPS-API compose workspace",
                                    "company_id": company.json()["id"],
                                    "stage": "onboarding"}, timeout=30)
    assert workspace.status_code == 200, workspace.text
    overdue = (datetime.now(timezone.utc) - timedelta(days=9)).isoformat()
    commitment = requests.post(f"{API}/commitments", headers=headers,
                               json={"title": "OPS-API compose overdue follow-up",
                                     "workspace_id": workspace.json()["id"],
                                     "due_date": overdue}, timeout=30)
    assert commitment.status_code == 200, commitment.text

    detected = requests.post(f"{API}/second-chance/detect", headers=headers, timeout=120)
    assert detected.status_code == 200, detected.text

    response = requests.post(f"{API}/recovery-strategies/compose", headers=headers, timeout=120)
    assert response.status_code == 200, response.text
    assert response.json()["strategies_composed"] >= 1, response.text
    return seeded_tenant


def test_no_outbound_channel_is_authorised_out_of_the_box(admin_token):
    """A fresh tenant has no certified provider, so the composer cannot send anything."""
    response = requests.get(f"{API}/recovery-strategies/channel-authority",
                            headers=_headers(admin_token), timeout=30)
    assert response.status_code == 200, response.text
    channels = response.json()
    assert channels["internal"]["authorized"] is True
    for channel in ("email", "sms", "phone"):
        assert channels[channel]["authorized"] is False, channels[channel]
        assert channels[channel]["reason"]


def test_composed_strategies_cite_facts_and_block_outbound_steps(composed_tenant):
    strategies = requests.get(f"{API}/recovery-strategies",
                              headers=_headers(composed_tenant), timeout=30).json()
    assert strategies, "compose reported success but returned nothing"
    strategy = strategies[0]
    assert strategy["lane"] and strategy["rule"] and strategy["rationale"]
    assert strategy["steps"]
    for step in strategy["steps"]:
        if step["channel"] == "internal":
            assert step["status"] == "ready"
        else:
            assert step["status"] == "blocked"
            assert step["blocked_reason"]
    assert "confidence" not in strategy and "score" not in strategy


def test_a_composed_strategy_is_readable_by_id(composed_tenant):
    strategies = requests.get(f"{API}/recovery-strategies",
                              headers=_headers(composed_tenant), timeout=30).json()
    response = requests.get(f"{API}/recovery-strategies/{strategies[0]['id']}",
                            headers=_headers(composed_tenant), timeout=30)
    assert response.status_code == 200
    assert response.json()["id"] == strategies[0]["id"]


def test_strategies_are_not_visible_to_another_tenant(composed_tenant, other_tenant_token):
    strategies = requests.get(f"{API}/recovery-strategies",
                              headers=_headers(composed_tenant), timeout=30).json()
    response = requests.get(f"{API}/recovery-strategies/{strategies[0]['id']}",
                            headers=_headers(other_tenant_token), timeout=30)
    assert response.status_code == 404
    assert requests.get(f"{API}/recovery-strategies", headers=_headers(other_tenant_token),
                        timeout=30).json() == []


def test_recovery_summary_reports_blocked_proposals(composed_tenant):
    summary = requests.get(f"{API}/recovery-strategies/summary",
                           headers=_headers(composed_tenant), timeout=30).json()
    assert summary["proposed"] >= 1
    assert summary["proposed_blocked"] >= 1


# ------------------------------------------------------------- recovery cases

def test_detection_opens_recovery_cases_readable_over_the_api(composed_tenant):
    """Detection must produce cases the operations surface can actually read."""
    response = requests.get(f"{API}/recovery-cases", headers=_headers(composed_tenant),
                            timeout=30)
    assert response.status_code == 200, response.text
    cases = response.json()
    assert cases, "detection ran but no recovery case is readable"
    case = cases[0]
    assert case["source"] and case["state"]
    # The two amounts are separate fields and a detected case has recovered nothing.
    assert case["confirmed_value"] is None


def test_a_recovery_case_is_readable_by_id(composed_tenant):
    cases = requests.get(f"{API}/recovery-cases", headers=_headers(composed_tenant),
                         timeout=30).json()
    response = requests.get(f"{API}/recovery-cases/{cases[0]['id']}",
                            headers=_headers(composed_tenant), timeout=30)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == cases[0]["id"]


def test_recovery_cases_are_not_visible_to_another_tenant(composed_tenant,
                                                          other_tenant_token):
    cases = requests.get(f"{API}/recovery-cases", headers=_headers(composed_tenant),
                         timeout=30).json()
    response = requests.get(f"{API}/recovery-cases/{cases[0]['id']}",
                            headers=_headers(other_tenant_token), timeout=30)
    assert response.status_code == 404
    assert requests.get(f"{API}/recovery-cases", headers=_headers(other_tenant_token),
                        timeout=30).json() == []


def test_an_unknown_recovery_case_is_a_404(composed_tenant):
    assert requests.get(f"{API}/recovery-cases/rc_doesnotexist",
                        headers=_headers(composed_tenant), timeout=30).status_code == 404


def test_recovery_case_summary_keeps_potential_and_confirmed_apart(composed_tenant):
    summary = requests.get(f"{API}/recovery-cases/summary",
                           headers=_headers(composed_tenant), timeout=30).json()
    assert summary["open_cases"] >= 1
    assert summary["by_state"] and summary["by_source"]
    # Nothing has been recovered, and an estimate must never be reported as revenue.
    assert summary["confirmed_recovered_value"] == 0
    assert summary["confirmed_recovered_value_by_currency"] == {}
    assert "currencies" in summary


def test_running_a_case_that_is_not_approved_is_refused(composed_tenant):
    """Execution is gated on approval, and the API is where that is enforced."""
    cases = requests.get(f"{API}/recovery-cases", headers=_headers(composed_tenant),
                         timeout=30).json()
    unapproved = [c for c in cases if c["state"] != "approved"]
    assert unapproved, "expected at least one case that has not been approved"
    response = requests.post(f"{API}/recovery-cases/{unapproved[0]['id']}/run",
                             headers=_headers(composed_tenant), timeout=30)
    assert response.status_code == 409, response.text


def test_running_another_tenants_case_is_a_404(composed_tenant, other_tenant_token):
    cases = requests.get(f"{API}/recovery-cases", headers=_headers(composed_tenant),
                         timeout=30).json()
    response = requests.post(f"{API}/recovery-cases/{cases[0]['id']}/run",
                             headers=_headers(other_tenant_token), timeout=30)
    assert response.status_code == 404, response.text


# -------------------------------------------------------- attribution ledger

def test_attribution_entries_are_readable_and_tenant_scoped(composed_tenant,
                                                            other_tenant_token):
    cases = requests.get(f"{API}/recovery-cases", headers=_headers(composed_tenant),
                         timeout=30).json()
    assert cases, "expected detection to have opened a case"
    refreshed = requests.post(f"{API}/attribution/cases/{cases[0]['id']}/refresh",
                              headers=_headers(composed_tenant), timeout=30)
    assert refreshed.status_code == 200, refreshed.text
    entry = refreshed.json()
    assert entry["case_id"] == cases[0]["id"]

    listed = requests.get(f"{API}/attribution", headers=_headers(composed_tenant),
                          timeout=30)
    assert listed.status_code == 200
    assert any(e["case_id"] == cases[0]["id"] for e in listed.json())

    # Another tenant sees neither the list nor the entry.
    assert requests.get(f"{API}/attribution", headers=_headers(other_tenant_token),
                        timeout=30).json() == []
    assert requests.get(f"{API}/attribution/cases/{cases[0]['id']}",
                        headers=_headers(other_tenant_token),
                        timeout=30).status_code == 404


def test_attribution_summary_separates_recovered_from_attributed(composed_tenant):
    """The figure the product is tempted to inflate is the one under test."""
    summary = requests.get(f"{API}/attribution/summary",
                           headers=_headers(composed_tenant), timeout=30)
    assert summary.status_code == 200, summary.text
    body = summary.json()
    # No provider adapter exists, so no outreach can have been delivered, so no revenue
    # is attributable to it — whatever else the ledger holds.
    assert body["attributable_to_outreach_by_currency"] == {}
    assert "attribution_note" in body
    # Money is reported per currency; there is no scalar total to misread.
    for field in ("confirmed_recovered_by_currency", "potential_open_by_currency",
                  "potential_lost_by_currency"):
        assert isinstance(body[field], dict), field


def test_an_unknown_case_has_no_attribution_entry(composed_tenant):
    assert requests.get(f"{API}/attribution/cases/rc_doesnotexist",
                        headers=_headers(composed_tenant), timeout=30).status_code == 404
    assert requests.post(f"{API}/attribution/cases/rc_doesnotexist/refresh",
                         headers=_headers(composed_tenant), timeout=30).status_code == 404


def test_an_operator_assertion_requires_a_reason(composed_tenant):
    cases = requests.get(f"{API}/recovery-cases", headers=_headers(composed_tenant),
                         timeout=30).json()
    response = requests.post(f"{API}/attribution/cases/{cases[0]['id']}/assert",
                             headers=_headers(composed_tenant), json={"reason": ""},
                             timeout=30)
    assert response.status_code == 422, response.text


# ------------------------------------------------------------ approval queue

def test_composition_raises_an_agent_approval_request(composed_tenant):
    requests_open = requests.get(f"{API}/approval-queue?kind=recovery_strategy",
                                 headers=_headers(composed_tenant), timeout=30).json()
    assert requests_open, "a composed strategy must raise an approval request"
    approval = requests_open[0]
    assert approval["requester_kind"] == "agent"
    assert approval["status"] == "requested"
    assert approval["subject_type"] == "recovery_strategy"
    assert approval["blocked_reasons"]


def test_approval_summary_counts_what_is_waiting(composed_tenant):
    summary = requests.get(f"{API}/approval-queue/summary",
                           headers=_headers(composed_tenant), timeout=30).json()
    assert summary["awaiting_decision"] >= 1
    assert summary["awaiting_decision_blocked"] >= 1


def test_an_approval_request_can_be_raised_and_decided(admin_token):
    created = requests.post(f"{API}/approval-queue", headers=_headers(admin_token),
                            json={"title": f"OPS-API approval {uuid.uuid4().hex[:6]}",
                                  "kind": "external_effect", "risk": "high",
                                  "summary": "Raised by the API contract test."}, timeout=30)
    assert created.status_code == 200, created.text
    approval = created.json()
    assert approval["requester_kind"] == "human"
    assert approval["risk"] == "high"

    decided = requests.post(f"{API}/approval-queue/{approval['id']}/decision",
                            headers=_headers(admin_token),
                            json={"decision": "approved", "rationale": "Contract test"}, timeout=30)
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approved"
    assert decided.json()["decided_by"]


def test_a_decided_approval_cannot_be_decided_again(admin_token):
    approval = requests.post(f"{API}/approval-queue", headers=_headers(admin_token),
                             json={"title": f"OPS-API once {uuid.uuid4().hex[:6]}"},
                             timeout=30).json()
    first = requests.post(f"{API}/approval-queue/{approval['id']}/decision",
                          headers=_headers(admin_token), json={"decision": "rejected"}, timeout=30)
    assert first.status_code == 200, first.text
    second = requests.post(f"{API}/approval-queue/{approval['id']}/decision",
                           headers=_headers(admin_token), json={"decision": "approved"}, timeout=30)
    assert second.status_code == 409, second.text


def test_approval_decisions_are_admin_only(member_token, admin_token):
    approval = requests.post(f"{API}/approval-queue", headers=_headers(admin_token),
                             json={"title": f"OPS-API rbac {uuid.uuid4().hex[:6]}"},
                             timeout=30).json()
    response = requests.post(f"{API}/approval-queue/{approval['id']}/decision",
                             headers=_headers(member_token), json={"decision": "approved"},
                             timeout=30)
    assert response.status_code == 403, response.text


def test_approvals_are_not_visible_to_another_tenant(admin_token, other_tenant_token):
    approval = requests.post(f"{API}/approval-queue", headers=_headers(admin_token),
                             json={"title": f"OPS-API isolation {uuid.uuid4().hex[:6]}"},
                             timeout=30).json()
    response = requests.get(f"{API}/approval-queue/{approval['id']}",
                            headers=_headers(other_tenant_token), timeout=30)
    assert response.status_code == 404


def test_an_approval_can_be_withdrawn(admin_token):
    approval = requests.post(f"{API}/approval-queue", headers=_headers(admin_token),
                             json={"title": f"OPS-API cancel {uuid.uuid4().hex[:6]}"},
                             timeout=30).json()
    cancelled = requests.post(f"{API}/approval-queue/{approval['id']}/cancel",
                              headers=_headers(admin_token),
                              json={"reason": "Contract test"}, timeout=30)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"


def test_the_legacy_approvals_route_shares_one_state_machine(admin_token, composed_tenant):
    """A request raised on /approvals must be visible and decidable in the queue."""
    workspaces = requests.get(f"{API}/workspaces", headers=_headers(composed_tenant),
                              timeout=30).json()
    assert workspaces
    legacy = requests.post(f"{API}/approvals", headers=_headers(composed_tenant),
                           json={"workspace_id": workspaces[0]["id"],
                                 "title": f"OPS-API legacy {uuid.uuid4().hex[:6]}"}, timeout=30)
    assert legacy.status_code == 200, legacy.text
    approval_id = legacy.json()["id"]

    listed = requests.get(f"{API}/approval-queue", headers=_headers(composed_tenant),
                          timeout=30).json()
    assert approval_id in [a["id"] for a in listed]

    decided = requests.patch(f"{API}/approvals/{approval_id}",
                             headers=_headers(composed_tenant),
                             json={"status": "approved"}, timeout=30)
    assert decided.status_code == 200, decided.text
    assert requests.get(f"{API}/approval-queue/{approval_id}",
                        headers=_headers(composed_tenant), timeout=30).json()["status"] == "approved"


# --------------------------------------------------- conversations and messages

@pytest.fixture(scope="module")
def conversation(seeded_tenant):
    """A conversation owned by the seeded tenant, with one contact participant."""
    response = requests.post(f"{API}/conversations", headers=_headers(seeded_tenant),
                             json={"channel": "email",
                                   "subject": f"OPS-API thread {uuid.uuid4().hex[:6]}",
                                   "participants": [{"kind": "contact", "id": "con_api",
                                                     "address": "client@example.invalid",
                                                     "display_name": "API Client"}]},
                             timeout=30)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_new_conversation_starts_open_with_no_consent(conversation):
    assert conversation["status"] == "open"
    assert conversation["handled_by"] == "human"
    assert conversation["consent"]["state"] == "unknown"


def test_an_unknown_channel_is_rejected(seeded_tenant):
    response = requests.post(f"{API}/conversations", headers=_headers(seeded_tenant),
                             json={"channel": "carrier_pigeon"}, timeout=30)
    assert response.status_code == 400, response.text


def test_no_delivery_provider_is_registered(seeded_tenant):
    """The honest state: no channel adapter has been built or certified."""
    summary = requests.get(f"{API}/conversations/summary", headers=_headers(seeded_tenant),
                           timeout=30).json()
    assert summary["providers"]
    assert all(entry["registered"] is False for entry in summary["providers"]), summary["providers"]


def test_a_message_can_be_drafted_but_not_sent(seeded_tenant, conversation):
    drafted = requests.post(f"{API}/conversations/{conversation['id']}/messages",
                            headers=_headers(seeded_tenant),
                            json={"body": "Following up on the proposal.",
                                  "to_address": "client@example.invalid"}, timeout=30)
    assert drafted.status_code == 200, drafted.text
    message = drafted.json()
    assert message["status"] == "draft"

    # Sending a draft is refused before anything else is considered.
    premature = requests.post(f"{API}/messages/{message['id']}/send",
                              headers=_headers(seeded_tenant), timeout=30)
    assert premature.status_code == 409, premature.text
    assert premature.json()["detail"]["reason"] == "message_not_dispatchable"


def test_an_approved_message_is_still_refused_with_no_channel_or_provider(seeded_tenant,
                                                                         conversation):
    drafted = requests.post(f"{API}/conversations/{conversation['id']}/messages",
                            headers=_headers(seeded_tenant),
                            json={"body": "Second attempt."}, timeout=30).json()
    requested = requests.post(f"{API}/messages/{drafted['id']}/request-approval",
                              headers=_headers(seeded_tenant), json={}, timeout=30)
    assert requested.status_code == 200, requested.text
    approval_id = requested.json()["approval_id"]
    assert approval_id

    approval = requests.get(f"{API}/approval-queue/{approval_id}",
                            headers=_headers(seeded_tenant), timeout=30).json()
    assert approval["subject_type"] == "communication_message"
    assert approval["blocked_reasons"], "the operator must see what still blocks it"

    decided = requests.post(f"{API}/approval-queue/{approval_id}/decision",
                            headers=_headers(seeded_tenant),
                            json={"decision": "approved"}, timeout=30)
    assert decided.status_code == 200, decided.text

    # Approving moved the message to `approved` through the shared decision hook.
    message = requests.get(f"{API}/messages/{drafted['id']}", headers=_headers(seeded_tenant),
                           timeout=30).json()
    assert message["status"] == "approved"

    # And it still cannot be sent, because approving does not authorise a channel.
    refused = requests.post(f"{API}/messages/{drafted['id']}/send",
                            headers=_headers(seeded_tenant), timeout=30)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["reason"] == "channel_not_authorized"
    blocked = requests.get(f"{API}/messages/{drafted['id']}", headers=_headers(seeded_tenant),
                           timeout=30).json()
    assert blocked["status"] == "blocked"
    assert blocked["blocked_reason"] == "channel_not_authorized"


def test_rejecting_an_approval_blocks_its_message(seeded_tenant, conversation):
    drafted = requests.post(f"{API}/conversations/{conversation['id']}/messages",
                            headers=_headers(seeded_tenant),
                            json={"body": "Third attempt."}, timeout=30).json()
    requested = requests.post(f"{API}/messages/{drafted['id']}/request-approval",
                              headers=_headers(seeded_tenant), json={}, timeout=30).json()
    rejected = requests.post(f"{API}/approval-queue/{requested['approval_id']}/decision",
                             headers=_headers(seeded_tenant),
                             json={"decision": "rejected"}, timeout=30)
    assert rejected.status_code == 200, rejected.text
    message = requests.get(f"{API}/messages/{drafted['id']}", headers=_headers(seeded_tenant),
                           timeout=30).json()
    assert message["status"] == "blocked"


def test_consent_granted_requires_a_basis(seeded_tenant, conversation):
    without = requests.post(f"{API}/conversations/{conversation['id']}/consent",
                            headers=_headers(seeded_tenant),
                            json={"state": "granted"}, timeout=30)
    assert without.status_code == 400, without.text
    with_basis = requests.post(f"{API}/conversations/{conversation['id']}/consent",
                               headers=_headers(seeded_tenant),
                               json={"state": "granted",
                                     "basis": "Client asked us to email them."}, timeout=30)
    assert with_basis.status_code == 200, with_basis.text
    assert with_basis.json()["consent"]["basis"]


def test_handoff_records_the_agent_human_boundary(seeded_tenant, conversation):
    handed = requests.post(f"{API}/conversations/{conversation['id']}/handoff",
                           headers=_headers(seeded_tenant),
                           json={"to": "agent", "reason": "Routine follow-up"}, timeout=30)
    assert handed.status_code == 200, handed.text
    assert handed.json()["handled_by"] == "agent"
    back = requests.post(f"{API}/conversations/{conversation['id']}/handoff",
                         headers=_headers(seeded_tenant),
                         json={"to": "human", "assignee": "rep@example.invalid"}, timeout=30)
    assert back.status_code == 200, back.text
    assert back.json()["assignee"] == "rep@example.invalid"


def test_conversations_are_not_visible_to_another_tenant(conversation, other_tenant_token):
    response = requests.get(f"{API}/conversations/{conversation['id']}",
                            headers=_headers(other_tenant_token), timeout=30)
    assert response.status_code == 404
    assert requests.get(f"{API}/conversations", headers=_headers(other_tenant_token),
                        timeout=30).json() == []


def test_recording_consent_is_admin_only(member_token, admin_token):
    created = requests.post(f"{API}/conversations", headers=_headers(admin_token),
                            json={"channel": "email", "subject": "RBAC check"},
                            timeout=30).json()
    response = requests.post(f"{API}/conversations/{created['id']}/consent",
                             headers=_headers(member_token),
                             json={"state": "granted", "basis": "nope"}, timeout=30)
    assert response.status_code == 403, response.text
