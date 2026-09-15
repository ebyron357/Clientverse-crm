"""Dual security gate tests.

The property under test is refusal: an external component must not become executable
because it was registered, because one gate passed, or because a scanner was never
run. Approval requires both gates AND completed results from every required scanner,
bound to an exact source and version.
"""

import asyncio
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import security_gate as gate

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT = "ten_gate_a"
OTHER_TENANT = "ten_gate_b"


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture()
def db_env(monkeypatch):
    db_name = f"cv_gate_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[db_name]
    run(gate.ensure_indexes(db))
    yield db
    run(client.drop_database(db_name))
    client.close()


@pytest.fixture()
def scanners_configured(monkeypatch):
    """Simulate operator-configured scanner endpoints (configuration only)."""
    monkeypatch.setenv("SECURITY_GATE_NVIDIA_SKILLSPECTOR_URL", "https://scanner.internal/nvidia")
    monkeypatch.setenv("SECURITY_GATE_CISCO_SKILL_SCANNER_URL", "https://scanner.internal/cisco-skill")
    monkeypatch.setenv("SECURITY_GATE_CISCO_MCP_SCANNER_URL", "https://scanner.internal/cisco-mcp")


def _register(db, kind=gate.KIND_SKILL, version="1.0.0"):
    return run(gate.register_component(
        db, tenant_id=TENANT, name="example-skill", kind=kind,
        source_url="https://github.com/example/skill", version=version,
        digest="sha256:abc", actor="admin@example.com"))


def _pass_checks(names):
    return {name: {"result": gate.CHECK_PASS, "detail": "reviewed"} for name in names}


def _completed_scans(kind):
    return [{"scanner": s, "status": "completed", "findings": []}
            for s in gate.required_scanners(kind)]


# ------------------------------------------------------------ registration

def test_registration_alone_grants_nothing(db_env):
    component = _register(db_env)
    assert component["state"] == gate.DISCOVERED
    assert component["gate_a"]["status"] == "not_run"
    assert component["gate_b"]["status"] == "not_run"
    with pytest.raises(gate.SecurityGateError):
        run(gate.assert_executable(db_env, tenant_id=TENANT,
                                   source_url=component["source_url"],
                                   version=component["version"]))


def test_registration_requires_an_exact_version(db_env):
    with pytest.raises(gate.SecurityGateError):
        run(gate.register_component(db_env, tenant_id=TENANT, name="x", kind=gate.KIND_SKILL,
                                    source_url="https://example.invalid/x", version=""))


def test_registration_is_idempotent_per_source_and_version(db_env):
    first = _register(db_env)
    second = _register(db_env)
    assert first["id"] == second["id"]
    assert run(db_env[gate.COLLECTION].count_documents({"tenant_id": TENANT})) == 1


def test_unsupported_kind_is_rejected(db_env):
    with pytest.raises(gate.SecurityGateError):
        run(gate.register_component(db_env, tenant_id=TENANT, name="x", kind="wetware",
                                    source_url="https://example.invalid/x", version="1"))


# -------------------------------------------------------------- gate logic

def test_scanner_routing_covers_both_layers(db_env):
    assert gate.required_scanners(gate.KIND_SKILL) == [gate.SCANNER_NVIDIA, gate.SCANNER_CISCO_SKILL]
    assert gate.required_scanners(gate.KIND_MCP_SERVER) == [gate.SCANNER_NVIDIA, gate.SCANNER_CISCO_MCP]
    # The pipeline is never a single scanner.
    for kind in gate.KINDS:
        assert len(gate.required_scanners(kind)) >= 2


def test_incomplete_gate_a_blocks_approval(db_env, scanners_configured):
    component = _register(db_env)
    partial = {"license": {"result": gate.CHECK_PASS}}
    updated = run(gate.record_gate(db_env, tenant_id=TENANT, component_id=component["id"],
                                   gate="gate_a", checks=partial, reviewer="admin@example.com"))
    assert updated["gate_a"]["status"] == "incomplete"
    assert updated["state"] == gate.UNDER_REVIEW
    with pytest.raises(gate.SecurityGateError):
        run(gate.decide(db_env, tenant_id=TENANT, component_id=component["id"],
                        decision=gate.APPROVED, actor="admin@example.com", rationale="looks fine"))


def test_gate_a_pass_alone_is_not_enough(db_env, scanners_configured):
    component = _register(db_env)
    run(gate.record_gate(db_env, tenant_id=TENANT, component_id=component["id"], gate="gate_a",
                         checks=_pass_checks(gate.GATE_A_CHECKS), reviewer="admin@example.com",
                         scanner_results=_completed_scans(gate.KIND_SKILL)))
    with pytest.raises(gate.SecurityGateError) as exc:
        run(gate.decide(db_env, tenant_id=TENANT, component_id=component["id"],
                        decision=gate.APPROVED, actor="admin@example.com", rationale="one gate"))
    assert "Gate B" in str(exc.value)


def test_a_failed_check_fails_the_gate(db_env, scanners_configured):
    component = _register(db_env)
    checks = _pass_checks(gate.GATE_A_CHECKS)
    checks["secret_scanning"] = {"result": gate.CHECK_FAIL, "detail": "hardcoded token found"}
    updated = run(gate.record_gate(db_env, tenant_id=TENANT, component_id=component["id"],
                                   gate="gate_a", checks=checks, reviewer="admin@example.com"))
    assert updated["gate_a"]["status"] == "failed"


def test_unknown_check_name_is_rejected(db_env):
    component = _register(db_env)
    with pytest.raises(gate.SecurityGateError):
        run(gate.record_gate(db_env, tenant_id=TENANT, component_id=component["id"],
                             gate="gate_a", checks={"vibes": {"result": gate.CHECK_PASS}},
                             reviewer="admin@example.com"))


def test_invalid_check_result_is_rejected(db_env):
    component = _register(db_env)
    with pytest.raises(gate.SecurityGateError):
        run(gate.record_gate(db_env, tenant_id=TENANT, component_id=component["id"],
                             gate="gate_a", checks={"license": {"result": "probably"}},
                             reviewer="admin@example.com"))


# ------------------------------------------------------------ scanner honesty

def test_unconfigured_scanner_blocks_approval(db_env, monkeypatch):
    """An unrun scanner is never treated as a pass."""
    monkeypatch.delenv("SECURITY_GATE_NVIDIA_SKILLSPECTOR_URL", raising=False)
    monkeypatch.delenv("SECURITY_GATE_CISCO_SKILL_SCANNER_URL", raising=False)
    component = _register(db_env)
    run(gate.record_gate(db_env, tenant_id=TENANT, component_id=component["id"], gate="gate_a",
                         checks=_pass_checks(gate.GATE_A_CHECKS), reviewer="admin@example.com"))
    run(gate.record_gate(db_env, tenant_id=TENANT, component_id=component["id"], gate="gate_b",
                         checks=_pass_checks(gate.GATE_B_CHECKS), reviewer="admin@example.com"))
    with pytest.raises(gate.SecurityGateError) as exc:
        run(gate.decide(db_env, tenant_id=TENANT, component_id=component["id"],
                        decision=gate.APPROVED, actor="admin@example.com", rationale="ship it"))
    assert "not configured" in str(exc.value)


def test_pipeline_status_reports_unconfigured_scanners(monkeypatch):
    monkeypatch.delenv("SECURITY_GATE_NVIDIA_SKILLSPECTOR_URL", raising=False)
    status = gate.pipeline_status()
    assert status["operational"] is False
    assert any(s["status"] == "not_configured" for s in status["scanners"])


def test_missing_scan_result_blocks_approval(db_env, scanners_configured):
    component = _register(db_env)
    only_nvidia = [{"scanner": gate.SCANNER_NVIDIA, "status": "completed", "findings": []}]
    run(gate.record_gate(db_env, tenant_id=TENANT, component_id=component["id"], gate="gate_a",
                         checks=_pass_checks(gate.GATE_A_CHECKS), reviewer="admin@example.com",
                         scanner_results=only_nvidia))
    run(gate.record_gate(db_env, tenant_id=TENANT, component_id=component["id"], gate="gate_b",
                         checks=_pass_checks(gate.GATE_B_CHECKS), reviewer="admin@example.com"))
    with pytest.raises(gate.SecurityGateError) as exc:
        run(gate.decide(db_env, tenant_id=TENANT, component_id=component["id"],
                        decision=gate.APPROVED, actor="admin@example.com", rationale="partial"))
    assert gate.SCANNER_CISCO_SKILL in str(exc.value)


# --------------------------------------------------------------- decisions

def _approve(db_env, kind=gate.KIND_SKILL, version="1.0.0", decision=gate.APPROVED):
    component = _register(db_env, kind=kind, version=version)
    scans = _completed_scans(kind)
    run(gate.record_gate(db_env, tenant_id=TENANT, component_id=component["id"], gate="gate_a",
                         checks=_pass_checks(gate.GATE_A_CHECKS), reviewer="admin@example.com",
                         scanner_results=scans))
    run(gate.record_gate(db_env, tenant_id=TENANT, component_id=component["id"], gate="gate_b",
                         checks=_pass_checks(gate.GATE_B_CHECKS), reviewer="admin@example.com",
                         scanner_results=scans))
    return run(gate.decide(db_env, tenant_id=TENANT, component_id=component["id"],
                           decision=decision, actor="admin@example.com",
                           rationale="Both gates passed with completed scans"))


def test_full_pipeline_approval_makes_a_component_executable(db_env, scanners_configured):
    approved = _approve(db_env)
    assert approved["state"] == gate.APPROVED
    assert approved["expires_at"], "approval must expire so a stale pass cannot persist"
    component = run(gate.assert_executable(db_env, tenant_id=TENANT,
                                           source_url=approved["source_url"],
                                           version=approved["version"]))
    assert component["id"] == approved["id"]


def test_approval_binds_to_an_exact_version(db_env, scanners_configured):
    approved = _approve(db_env, version="1.0.0")
    with pytest.raises(gate.SecurityGateError):
        run(gate.assert_executable(db_env, tenant_id=TENANT,
                                   source_url=approved["source_url"], version="1.0.1"))


def test_expired_approval_stops_execution(db_env, scanners_configured):
    approved = _approve(db_env)
    run(db_env[gate.COLLECTION].update_one(
        {"id": approved["id"]}, {"$set": {"expires_at": "2000-01-01T00:00:00+00:00"}}))
    with pytest.raises(gate.SecurityGateError) as exc:
        run(gate.assert_executable(db_env, tenant_id=TENANT,
                                   source_url=approved["source_url"],
                                   version=approved["version"]))
    assert "expired" in str(exc.value)


def test_revoked_component_cannot_execute(db_env, scanners_configured):
    approved = _approve(db_env)
    run(gate.decide(db_env, tenant_id=TENANT, component_id=approved["id"], decision=gate.REVOKED,
                    actor="admin@example.com", rationale="Upstream maintainer compromised"))
    with pytest.raises(gate.SecurityGateError):
        run(gate.assert_executable(db_env, tenant_id=TENANT,
                                   source_url=approved["source_url"],
                                   version=approved["version"]))


def test_approved_limited_is_executable_and_records_limitations(db_env, scanners_configured):
    approved = _approve(db_env, decision=gate.APPROVED_LIMITED)
    assert approved["state"] == gate.APPROVED_LIMITED
    run(gate.assert_executable(db_env, tenant_id=TENANT, source_url=approved["source_url"],
                               version=approved["version"]))


def test_restricting_decisions_never_require_a_passing_gate(db_env):
    component = _register(db_env)
    quarantined = run(gate.decide(db_env, tenant_id=TENANT, component_id=component["id"],
                                  decision=gate.QUARANTINED, actor="admin@example.com",
                                  rationale="Suspicious install script"))
    assert quarantined["state"] == gate.QUARANTINED
    assert quarantined["expires_at"] is None


def test_invalid_state_transition_is_rejected(db_env):
    """A rejected component may only be reopened for review, nothing else."""
    component = _register(db_env)
    run(gate.decide(db_env, tenant_id=TENANT, component_id=component["id"],
                    decision=gate.REJECTED, actor="admin@example.com", rationale="no"))
    with pytest.raises(gate.InvalidGateTransition):
        run(gate.decide(db_env, tenant_id=TENANT, component_id=component["id"],
                        decision=gate.QUARANTINED, actor="admin@example.com",
                        rationale="second thoughts"))


def test_rejected_component_cannot_jump_straight_to_approved(db_env, scanners_configured):
    """Even with both gates recorded, a decision still has to follow the state machine."""
    component = _register(db_env)
    scans = _completed_scans(gate.KIND_SKILL)
    run(gate.record_gate(db_env, tenant_id=TENANT, component_id=component["id"], gate="gate_a",
                         checks=_pass_checks(gate.GATE_A_CHECKS), reviewer="admin@example.com",
                         scanner_results=scans))
    run(gate.record_gate(db_env, tenant_id=TENANT, component_id=component["id"], gate="gate_b",
                         checks=_pass_checks(gate.GATE_B_CHECKS), reviewer="admin@example.com",
                         scanner_results=scans))
    run(gate.decide(db_env, tenant_id=TENANT, component_id=component["id"],
                    decision=gate.REJECTED, actor="admin@example.com", rationale="policy"))
    with pytest.raises(gate.InvalidGateTransition):
        run(gate.decide(db_env, tenant_id=TENANT, component_id=component["id"],
                        decision=gate.APPROVED, actor="admin@example.com",
                        rationale="changed mind"))


def test_gate_records_are_tenant_isolated(db_env, scanners_configured):
    approved = _approve(db_env)
    with pytest.raises(gate.SecurityGateError):
        run(gate.assert_executable(db_env, tenant_id=OTHER_TENANT,
                                   source_url=approved["source_url"],
                                   version=approved["version"]))
    assert run(gate.get_component(db_env, OTHER_TENANT, approved["id"])) is None


def test_eligibility_explains_every_blocking_reason(db_env, monkeypatch):
    monkeypatch.delenv("SECURITY_GATE_NVIDIA_SKILLSPECTOR_URL", raising=False)
    monkeypatch.delenv("SECURITY_GATE_CISCO_SKILL_SCANNER_URL", raising=False)
    component = _register(db_env)
    verdict = gate.eligibility(component)
    assert verdict["eligible"] is False
    joined = " ".join(verdict["blocking_reasons"])
    assert "Gate A" in joined and "Gate B" in joined and "not configured" in joined


def test_history_records_every_action(db_env, scanners_configured):
    approved = _approve(db_env)
    actions = [h["action"] for h in approved["history"]]
    assert actions == ["registered", "gate_a_recorded", "gate_b_recorded", "decision"]
