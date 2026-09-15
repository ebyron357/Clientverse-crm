"""Dual security gate for external agent capability.

Nothing external becomes trusted because it was discovered, recommended, or named in
an approved document. Every external skill, MCP server, MCP tool, agent plugin or
package must complete two independent gates and carry an explicit decision bound to
an exact source and version.

    EXTERNAL SOURCE
          |
    GATE A  supply-chain intake     (source identity, pin, licence, deps, secrets,
          |                          install scripts, network/filesystem declarations,
          |                          provenance, known vulnerabilities, integrity)
          v
    GATE B  capability / execution  (what it can read, write, reach; credentials;
          |                          destructive actions; approval + sandbox needs;
          |                          tenant impact; rollback)
          v
    DECISION → APPROVED | APPROVED_LIMITED | REJECTED | QUARANTINED | REVOKED

Honest boundary: this module implements the intake registry, both gate evaluations,
the state machine and enforcement. The external scanners themselves (NVIDIA
SkillSpector, Cisco Skill Scanner, Cisco MCP Scanner) are not reachable from this
environment and are not authorised yet — `scanner_status` records `not_configured`
and a component can never reach APPROVED on unrun scanners. That boundary is owner
blocker O-13 in the canonical governing document; it is surfaced, never simulated.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

COLLECTION = "external_components"

# Lifecycle states, exactly as the governing document requires.
DISCOVERED = "DISCOVERED"
UNDER_REVIEW = "UNDER_REVIEW"
REJECTED = "REJECTED"
QUARANTINED = "QUARANTINED"
APPROVED_LIMITED = "APPROVED_LIMITED"
APPROVED = "APPROVED"
REVOKED = "REVOKED"

STATES = (DISCOVERED, UNDER_REVIEW, REJECTED, QUARANTINED, APPROVED_LIMITED, APPROVED, REVOKED)
EXECUTABLE_STATES = (APPROVED, APPROVED_LIMITED)

ALLOWED_TRANSITIONS = {
    DISCOVERED: {UNDER_REVIEW, REJECTED, QUARANTINED},
    UNDER_REVIEW: {APPROVED, APPROVED_LIMITED, REJECTED, QUARANTINED, UNDER_REVIEW},
    APPROVED: {REVOKED, QUARANTINED, UNDER_REVIEW},
    APPROVED_LIMITED: {APPROVED, REVOKED, QUARANTINED, UNDER_REVIEW},
    QUARANTINED: {UNDER_REVIEW, REJECTED, REVOKED},
    REJECTED: {UNDER_REVIEW},
    REVOKED: {UNDER_REVIEW},
}

KIND_SKILL = "skill"
KIND_MCP_SERVER = "mcp_server"
KIND_MCP_TOOL = "mcp_tool"
KIND_PLUGIN = "plugin"
KIND_PACKAGE = "package"
KINDS = (KIND_SKILL, KIND_MCP_SERVER, KIND_MCP_TOOL, KIND_PLUGIN, KIND_PACKAGE)

# Gate A — supply-chain intake. Every check must be answered before Gate A passes.
GATE_A_CHECKS = (
    "source_identity",
    "repository_identity",
    "version_pin",
    "license",
    "maintenance_status",
    "dependency_inventory",
    "secret_scanning",
    "malicious_patterns",
    "install_build_scripts",
    "network_behavior_declared",
    "filesystem_access_declared",
    "permissions",
    "provenance",
    "known_vulnerabilities",
    "suspicious_binaries",
    "package_integrity",
)

# Gate B — capability and execution review.
GATE_B_CHECKS = (
    "capabilities",
    "data_read",
    "data_write",
    "network_destinations",
    "filesystem_access",
    "shell_process_access",
    "credentials_required",
    "destructive_actions",
    "approval_requirements",
    "tenant_impact",
    "allowed_use",
    "prohibited_use",
    "sandbox_requirements",
    "rollback_removal",
)

CHECK_PASS = "pass"
CHECK_FAIL = "fail"
CHECK_CONCERN = "concern"
CHECK_NOT_RUN = "not_run"
CHECK_RESULTS = (CHECK_PASS, CHECK_FAIL, CHECK_CONCERN, CHECK_NOT_RUN)

# Scanner registry. Gate A routes to NVIDIA SkillSpector; Gate B routes to the Cisco
# scanner matching the component kind. Both layers are required — the pipeline is
# never collapsed to a single scanner.
SCANNER_NVIDIA = "nvidia_skillspector"
SCANNER_CISCO_SKILL = "cisco_skill_scanner"
SCANNER_CISCO_MCP = "cisco_mcp_scanner"

SCANNER_ENV = {
    SCANNER_NVIDIA: "SECURITY_GATE_NVIDIA_SKILLSPECTOR_URL",
    SCANNER_CISCO_SKILL: "SECURITY_GATE_CISCO_SKILL_SCANNER_URL",
    SCANNER_CISCO_MCP: "SECURITY_GATE_CISCO_MCP_SCANNER_URL",
}

DEFAULT_APPROVAL_DAYS = int(os.environ.get("SECURITY_GATE_APPROVAL_DAYS", "90"))


class SecurityGateError(Exception):
    pass


class InvalidGateTransition(SecurityGateError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _parse(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def required_scanners(kind: str) -> list[str]:
    """Gate 1 is always NVIDIA; Gate 2 routes by kind. A component that is both a
    skill and an MCP surface is scanned by both Cisco scanners."""
    scanners = [SCANNER_NVIDIA]
    if kind in (KIND_MCP_SERVER, KIND_MCP_TOOL):
        scanners.append(SCANNER_CISCO_MCP)
    if kind in (KIND_SKILL, KIND_PLUGIN, KIND_PACKAGE):
        scanners.append(SCANNER_CISCO_SKILL)
    return scanners


def scanner_status(name: str) -> dict:
    """Report whether a scanner is actually wired up.

    Returns `not_configured` when no endpoint is configured. This is what keeps the
    gate honest: an unconfigured scanner is never reported as a pass.
    """
    env_var = SCANNER_ENV.get(name)
    endpoint = os.environ.get(env_var or "", "")
    return {
        "scanner": name,
        "configured": bool(endpoint),
        "status": "configured" if endpoint else "not_configured",
        "config_env": env_var,
    }


def scanner_readiness(kind: str) -> dict:
    statuses = [scanner_status(name) for name in required_scanners(kind)]
    return {
        "required": [s["scanner"] for s in statuses],
        "statuses": statuses,
        "all_configured": all(s["configured"] for s in statuses),
    }


def _blank_gate(checks: tuple[str, ...]) -> dict:
    return {
        "status": "not_run",
        "completed_at": None,
        "reviewer": None,
        "checks": {name: {"result": CHECK_NOT_RUN, "detail": None} for name in checks},
        "scanner_results": [],
        "findings": [],
    }


def _evaluate_gate(checks: dict, required: tuple[str, ...]) -> str:
    results = [checks.get(name, {}).get("result", CHECK_NOT_RUN) for name in required]
    if any(r == CHECK_FAIL for r in results):
        return "failed"
    if any(r == CHECK_NOT_RUN for r in results):
        return "incomplete"
    if any(r == CHECK_CONCERN for r in results):
        return "passed_with_concerns"
    return "passed"


async def ensure_indexes(db) -> None:
    await db[COLLECTION].create_index(
        [("tenant_id", 1), ("source_url", 1), ("version", 1)], unique=True
    )
    await db[COLLECTION].create_index([("tenant_id", 1), ("state", 1)])
    await db[COLLECTION].create_index([("tenant_id", 1), ("kind", 1)])


async def register_component(db, *, tenant_id: str, name: str, kind: str, source_url: str,
                             version: str, digest: Optional[str] = None,
                             description: Optional[str] = None, actor: str = "system") -> dict:
    """Record an external component as DISCOVERED. Registration grants nothing."""
    if kind not in KINDS:
        raise SecurityGateError(f"Unsupported component kind '{kind}'")
    if not source_url or not version:
        raise SecurityGateError("source_url and version are required — approval binds to an exact version")

    existing = await db[COLLECTION].find_one(
        {"tenant_id": tenant_id, "source_url": source_url, "version": version}, {"_id": 0}
    )
    if existing:
        return existing

    now = _iso(_now())
    doc = {
        "id": f"extc_{uuid.uuid4().hex[:12]}",
        "tenant_id": tenant_id,
        "name": name,
        "kind": kind,
        "source_url": source_url,
        "version": version,
        "digest": digest,
        "description": description,
        "state": DISCOVERED,
        "gate_a": _blank_gate(GATE_A_CHECKS),
        "gate_b": _blank_gate(GATE_B_CHECKS),
        "decision": None,
        "decided_by": None,
        "decided_at": None,
        "expires_at": None,
        "limitations": [],
        "scanner_readiness": scanner_readiness(kind),
        "created_at": now,
        "updated_at": now,
        "history": [{"action": "registered", "actor": actor, "at": now,
                     "detail": {"source_url": source_url, "version": version}}],
    }
    await db[COLLECTION].insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def record_gate(db, *, tenant_id: str, component_id: str, gate: str, checks: dict,
                      reviewer: str, findings: Optional[list] = None,
                      scanner_results: Optional[list] = None) -> dict:
    """Record a Gate A or Gate B evaluation.

    `scanner_results` are attached verbatim. A result for a scanner that is not
    configured is stored but does not count towards the gate passing.
    """
    if gate not in ("gate_a", "gate_b"):
        raise SecurityGateError("gate must be 'gate_a' or 'gate_b'")
    component = await db[COLLECTION].find_one({"tenant_id": tenant_id, "id": component_id}, {"_id": 0})
    if not component:
        raise SecurityGateError("Component not found")

    required = GATE_A_CHECKS if gate == "gate_a" else GATE_B_CHECKS
    current = component.get(gate) or _blank_gate(required)
    merged = dict(current["checks"])
    for name, value in (checks or {}).items():
        if name not in required:
            raise SecurityGateError(f"Unknown {gate} check '{name}'")
        result = value.get("result") if isinstance(value, dict) else value
        if result not in CHECK_RESULTS:
            raise SecurityGateError(f"Invalid result '{result}' for check '{name}'")
        detail = value.get("detail") if isinstance(value, dict) else None
        merged[name] = {"result": result, "detail": detail}

    status = _evaluate_gate(merged, required)
    now = _iso(_now())
    gate_doc = {
        "status": status,
        "completed_at": now if status != "incomplete" else None,
        "reviewer": reviewer,
        "checks": merged,
        "scanner_results": scanner_results or current.get("scanner_results", []),
        "findings": findings if findings is not None else current.get("findings", []),
    }
    updates = {gate: gate_doc, "updated_at": now}
    if component.get("state") == DISCOVERED:
        updates["state"] = UNDER_REVIEW

    doc = await db[COLLECTION].find_one_and_update(
        {"tenant_id": tenant_id, "id": component_id},
        {"$set": updates,
         "$push": {"history": {"action": f"{gate}_recorded", "actor": reviewer, "at": now,
                               "detail": {"status": status}}}},
        projection={"_id": 0},
        return_document=True,
    )
    return doc


def eligibility(component: dict) -> dict:
    """Can this component be approved right now? Explains every blocking reason."""
    reasons: list[str] = []
    gate_a = (component.get("gate_a") or {}).get("status", "not_run")
    gate_b = (component.get("gate_b") or {}).get("status", "not_run")
    if gate_a not in ("passed", "passed_with_concerns"):
        reasons.append(f"Gate A (supply-chain intake) is '{gate_a}'")
    if gate_b not in ("passed", "passed_with_concerns"):
        reasons.append(f"Gate B (capability/execution review) is '{gate_b}'")

    readiness = scanner_readiness(component.get("kind", KIND_SKILL))
    ran = {r.get("scanner") for gate in ("gate_a", "gate_b")
           for r in ((component.get(gate) or {}).get("scanner_results") or [])
           if r.get("status") == "completed"}
    missing_scans = [s for s in readiness["required"] if s not in ran]
    if missing_scans:
        reasons.append("Required scanners have not produced a completed result: "
                       + ", ".join(missing_scans))
    unconfigured = [s["scanner"] for s in readiness["statuses"] if not s["configured"]]
    if unconfigured:
        reasons.append("Scanner endpoints are not configured: " + ", ".join(unconfigured))

    return {"eligible": not reasons, "blocking_reasons": reasons,
            "gate_a": gate_a, "gate_b": gate_b, "scanner_readiness": readiness}


async def decide(db, *, tenant_id: str, component_id: str, decision: str, actor: str,
                 rationale: str, limitations: Optional[list] = None,
                 expires_in_days: int = DEFAULT_APPROVAL_DAYS) -> dict:
    """Move a component to a terminal decision state.

    APPROVED and APPROVED_LIMITED require both gates to have passed and every required
    scanner to have produced a completed result. REJECTED, QUARANTINED and REVOKED are
    always available — restricting a component never needs a passing gate.
    """
    if decision not in STATES:
        raise SecurityGateError(f"Unsupported decision '{decision}'")
    component = await db[COLLECTION].find_one({"tenant_id": tenant_id, "id": component_id}, {"_id": 0})
    if not component:
        raise SecurityGateError("Component not found")

    current_state = component.get("state", DISCOVERED)

    # Eligibility is checked before the transition so an operator is told the real
    # blocker ("Gate B has not passed") rather than the less useful state-machine
    # complaint that the component is still DISCOVERED.
    if decision in EXECUTABLE_STATES:
        verdict = eligibility(component)
        if not verdict["eligible"]:
            raise SecurityGateError(
                "Component cannot be approved: " + "; ".join(verdict["blocking_reasons"])
            )

    if decision not in ALLOWED_TRANSITIONS.get(current_state, set()):
        raise InvalidGateTransition(f"Cannot move component from '{current_state}' to '{decision}'")

    now = _now()
    updates: dict[str, Any] = {
        "state": decision,
        "decision": {"decision": decision, "rationale": rationale, "actor": actor,
                     "at": _iso(now)},
        "decided_by": actor,
        "decided_at": _iso(now),
        "limitations": limitations or [],
        "updated_at": _iso(now),
    }
    # Approval binds to an exact source and version and expires, so a stale pass never
    # keeps a component trusted forever.
    updates["expires_at"] = (_iso(now + timedelta(days=max(1, int(expires_in_days))))
                             if decision in EXECUTABLE_STATES else None)

    return await db[COLLECTION].find_one_and_update(
        {"tenant_id": tenant_id, "id": component_id},
        {"$set": updates,
         "$push": {"history": {"action": "decision", "actor": actor, "at": _iso(now),
                               "detail": {"decision": decision, "rationale": rationale}}}},
        projection={"_id": 0},
        return_document=True,
    )


async def assert_executable(db, *, tenant_id: str, source_url: str, version: str) -> dict:
    """Enforcement hook: raise unless this exact source+version is currently trusted."""
    component = await db[COLLECTION].find_one(
        {"tenant_id": tenant_id, "source_url": source_url, "version": version}, {"_id": 0}
    )
    if not component:
        raise SecurityGateError(
            "External component is not registered with the security gate and cannot execute"
        )
    if component.get("state") not in EXECUTABLE_STATES:
        raise SecurityGateError(
            f"External component state is '{component.get('state')}' and is not eligible to execute"
        )
    expires_at = _parse(component.get("expires_at"))
    if expires_at and expires_at < _now():
        raise SecurityGateError("Security gate approval has expired and must be re-run for this version")
    return component


async def list_components(db, tenant_id: str, *, state: Optional[str] = None,
                          kind: Optional[str] = None, limit: int = 100) -> list[dict]:
    criteria: dict[str, Any] = {"tenant_id": tenant_id}
    if state:
        criteria["state"] = state
    if kind:
        criteria["kind"] = kind
    limit = max(1, min(int(limit), 500))
    return await db[COLLECTION].find(criteria, {"_id": 0}).sort("created_at", -1).to_list(limit)


async def get_component(db, tenant_id: str, component_id: str) -> Optional[dict]:
    doc = await db[COLLECTION].find_one({"tenant_id": tenant_id, "id": component_id}, {"_id": 0})
    if doc:
        doc["eligibility"] = eligibility(doc)
    return doc


def pipeline_status() -> dict:
    """Operator-facing view of whether the gate can currently approve anything."""
    statuses = [scanner_status(name) for name in
                (SCANNER_NVIDIA, SCANNER_CISCO_SKILL, SCANNER_CISCO_MCP)]
    return {
        "gates": ["gate_a_supply_chain_intake", "gate_b_capability_execution_review"],
        "scanners": statuses,
        "operational": all(s["configured"] for s in statuses),
        "note": (
            "Both gates are enforced. Approval additionally requires completed results "
            "from every required scanner; unconfigured scanners block approval rather "
            "than being treated as a pass."
        ),
    }
