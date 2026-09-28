#!/usr/bin/env python3
"""Run mypy over the backend, blocking only on the modules that are clean today.

The backend predates any type checking, so a single `mypy .` reports ~120 findings
that are almost all the same shape: a value read from Mongo is `Optional[dict]` and
the code knows it is not None. Fixing them is a refactor, and gating on them would
mean either doing that refactor first or never turning the checker on at all.

So the gate is a ratchet instead. The modules listed under `[[tool.mypy.overrides]]`
in `backend/pyproject.toml` pass cleanly and are blocking: nothing can make them
dirty again. Everything else is reported for visibility and does not fail the build.
A module joins the blocking set by being clean, so the checked surface only grows.

Usage: python scripts/typecheck.py [backend_dir]
Exit code 1 if any blocking module has a finding.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path


def blocking_modules(pyproject: Path) -> list[str]:
    config = tomllib.loads(pyproject.read_text())
    for override in config.get("tool", {}).get("mypy", {}).get("overrides", []):
        modules = override.get("module", [])
        # The strict override is the one that tightens rules rather than loosening
        # them for a third-party package.
        if override.get("disallow_incomplete_defs"):
            return [m for m in modules if not m.endswith("*")]
    return []


def main() -> int:
    backend = Path(sys.argv[1] if len(sys.argv) > 1 else "backend").resolve()
    pyproject = backend / "pyproject.toml"
    if not pyproject.exists():
        print(f"No pyproject.toml at {pyproject}", file=sys.stderr)
        return 2

    modules = blocking_modules(pyproject)
    if not modules:
        print("No blocking modules configured; nothing to enforce.", file=sys.stderr)
        return 2

    result = subprocess.run([sys.executable, "-m", "mypy", "."], cwd=backend,
                            capture_output=True, text=True)
    output = result.stdout + result.stderr
    print(output)

    pattern = re.compile(rf"^({'|'.join(re.escape(m) for m in modules)})\.py:")
    blocking = [line for line in output.splitlines()
                if pattern.match(line) and ": error:" in line]
    reported = [line for line in output.splitlines() if ": error:" in line]

    print(f"\nType checking: {len(reported)} finding(s) total, "
          f"{len(blocking)} in the {len(modules)} blocking module(s).")
    if blocking:
        print("\nBlocking findings:")
        for line in blocking:
            print(f"  {line}")
        return 1
    print("Blocking modules are clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
