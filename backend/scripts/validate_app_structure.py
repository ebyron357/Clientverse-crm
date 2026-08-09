#!/usr/bin/env python3
"""Structural validation for the modular ClientVerse backend.

Exits non-zero on any structural failure. Run manually or in CI:

    python backend/scripts/validate_app_structure.py

Checks:
  1. Every module under backend/ (server.py + app/**) parses (AST) — catches
     the tail-corruption that repeatedly hit the old monolith.
  2. The app imports without a circular-import / startup error.
  3. A FastAPI app instance is created.
  4. Each router is registered exactly once (no duplicate include_router).
  5. No duplicate (method, path) route registrations.
  6. All expected routers are present (no accidental disappearance).
  7. server.py stays a thin bootstrap (no route handlers, no models, small).
"""
import ast
import glob
import os
import sys

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

EXPECTED_ROUTERS = {
    "auth", "team", "crm", "delivery", "dashboard", "ai", "mcp", "webhooks",
    "outcomes", "integrations", "insights", "notifications", "cron",
}

errors = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        errors.append(name)


# 1. AST parse of every backend module
py_files = [os.path.join(BACKEND, "server.py")]
py_files += glob.glob(os.path.join(BACKEND, "app", "**", "*.py"), recursive=True)
parse_bad = []
for path in py_files:
    try:
        ast.parse(open(path).read(), filename=path)
    except SyntaxError as e:
        parse_bad.append(f"{path}: {e}")
check("ast_parse_all_modules", not parse_bad, "; ".join(parse_bad) or f"{len(py_files)} files")

# 2 & 3. Import app + FastAPI instance
app = None
routers = []
try:
    import server
    from fastapi import FastAPI
    app = server.app
    routers = list(server.ROUTERS)
    check("app_imports_no_circular", True)
    check("fastapi_app_created", isinstance(app, FastAPI))
except Exception as e:  # noqa: BLE001
    check("app_imports_no_circular", False, repr(e))
    check("fastapi_app_created", False)

if app is not None:
    # 4. Each router registered exactly once
    ids = [id(r) for r in routers]
    check("no_duplicate_router_inclusion", len(ids) == len(set(ids)),
          f"{len(routers)} routers")

    # 5. No duplicate (method, path)
    seen = {}
    for r in app.routes:
        for method in getattr(r, "methods", []) or []:
            if method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                seen[(method, r.path)] = seen.get((method, r.path), 0) + 1
    dups = {k: v for k, v in seen.items() if v > 1}
    check("no_duplicate_routes", not dups, str(dups) if dups else f"{len(seen)} unique routes")

    # 6. Expected routers present
    present = {r.__name__.rsplit(".", 1)[-1] for r in routers}
    missing = EXPECTED_ROUTERS - present
    check("all_expected_routers_present", not missing, f"missing={missing}" if missing else f"{len(present)} routers")

    print(f"\nBUSINESS_ROUTE_COUNT={len(seen)}")

# 7. server.py stays thin
src = open(os.path.join(BACKEND, "server.py")).read()
thin_issues = []
if "BaseModel" in src:
    thin_issues.append("Pydantic model in server.py")
if len(src.splitlines()) >= 90:
    thin_issues.append(f"{len(src.splitlines())} lines (>=90)")
tree = ast.parse(src)
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for dec in node.decorator_list:
            tgt = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name) and tgt.value.id == "api":
                thin_issues.append(f"business route '{node.name}' in server.py")
check("server_is_thin_bootstrap", not thin_issues, "; ".join(thin_issues))

print()
if errors:
    print(f"STRUCTURAL VALIDATION FAILED: {errors}")
    sys.exit(1)
print("STRUCTURAL VALIDATION PASSED")
sys.exit(0)
