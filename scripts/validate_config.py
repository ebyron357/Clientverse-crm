#!/usr/bin/env python3
"""Validate configuration that would otherwise only fail at boot or at 3am.

Three classes of mistake this catches, all of which have happened to this project:

1. **A workflow that parses but does not do what it says.** The scheduler workflow
   once exited 0 with no production request made. Its contract now includes failing
   when unconfigured, so that is asserted here rather than trusted.
2. **A cron path in the scheduler that the application does not serve.** A typo would
   send every tick to a 404 and the only symptom would be a red build days later.
3. **Deployment configuration drifting from what the application needs** -- the
   healthcheck path in `railway.json` pointing somewhere that is not the health
   endpoint.

Exit code 1 on any finding, with the file and the reason.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINDINGS: list[str] = []


def fail(where: str, reason: str) -> None:
    FINDINGS.append(f"{where}: {reason}")


def check_scheduler_contract() -> set[str]:
    """The scheduler must fail loudly when it is not configured, and must verify."""
    path = ROOT / ".github/workflows/scheduled-jobs.yml"
    if not path.exists():
        fail(str(path), "scheduler workflow is missing")
        return set()
    text = path.read_text()

    guard = text.split("Require the scheduler to be configured")[-1].split(
        "Select endpoints")[0]
    if "exit 1" not in guard:
        fail(str(path),
             "the unconfigured path does not fail the run; a scheduler that reports "
             "success without calling production is the defect this check exists for")
    for required in ("Require the scheduler to be configured",
                     "No request reached production",
                     "Verify production recorded this run"):
        if required not in text:
            fail(str(path), f"missing the '{required}' guard")
    return set()


def check_cron_paths() -> None:
    """Every path the scheduler calls must be a route the application serves."""
    workflow = (ROOT / ".github/workflows/scheduled-jobs.yml")
    server = (ROOT / "backend/server.py")
    if not workflow.exists() or not server.exists():
        return
    scheduled: set[str] = set()
    for group in re.findall(r"paths='([^']+)'", workflow.read_text()):
        scheduled.update(part.strip() for part in group.split(",") if part.strip())
    served = set(re.findall(r'@api\.post\("/cron/([a-z\-]+)"\)', server.read_text()))
    missing = sorted(scheduled - served)
    if missing:
        fail(str(workflow),
             f"schedules {', '.join(missing)}, which the application does not serve")
    unscheduled = sorted(served - scheduled)
    if unscheduled:
        # Not a failure: an endpoint may be driven by something other than this
        # workflow. Worth saying out loud, because "why did that never run?" is the
        # question this project has already had to answer once.
        print(f"note: /api/cron/{{{','.join(unscheduled)}}} is served but not scheduled "
              f"by this workflow")


def check_deployment_config() -> None:
    path = ROOT / "railway.json"
    if not path.exists():
        return
    try:
        config = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        fail(str(path), f"is not valid JSON: {exc}")
        return
    healthcheck = (config.get("deploy") or {}).get("healthcheckPath")
    if healthcheck and healthcheck != "/api/health":
        fail(str(path),
             f"healthcheckPath is '{healthcheck}'; the application serves /api/health")


def check_ci_gates() -> None:
    """The release gates must actually be in the workflow that gates the release."""
    path = ROOT / ".github/workflows/ci.yml"
    text = path.read_text()
    for required, why in (
            ("crm_release_smoke.mjs", "the CRM release gate"),
            ("ruff check", "the lint gate"),
            ("typecheck.py", "the type gate"),
            ("pip-audit", "the dependency vulnerability gate")):
        if required not in text:
            fail(str(path), f"does not run {why}")


def main() -> int:
    check_scheduler_contract()
    check_cron_paths()
    check_deployment_config()
    check_ci_gates()
    if FINDINGS:
        print("Configuration validation failed:")
        for finding in FINDINGS:
            print(f"  {finding}")
        return 1
    print("Configuration validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
