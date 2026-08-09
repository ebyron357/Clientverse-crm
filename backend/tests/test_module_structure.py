"""Structural reliability guards for the modular backend.

Fails when: server.py becomes syntactically invalid, business logic creeps back
into the bootstrap, a router is registered twice, duplicate (method, path) routes
appear, or a circular import prevents the app from importing.
"""
import ast
import glob
import os

import pytest

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _py_files():
    files = [os.path.join(BACKEND, "server.py")]
    files += glob.glob(os.path.join(BACKEND, "app", "**", "*.py"), recursive=True)
    return files


def test_all_modules_parse():
    for path in _py_files():
        with open(path) as f:
            ast.parse(f.read(), filename=path)  # raises SyntaxError on corruption


def test_app_imports_without_circular_error():
    import importlib
    server = importlib.import_module("server")
    assert server.app is not None


def test_server_is_a_thin_bootstrap():
    """server.py must not grow back into a monolith: no route handlers, no models,
    small line count."""
    src = open(os.path.join(BACKEND, "server.py")).read()
    tree = ast.parse(src)
    # No @router.<verb> / @api.<verb> decorated business routes in bootstrap
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                target = dec.func if isinstance(dec, ast.Call) else dec
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                    assert target.value.id != "api", "business route left in server.py"
    # No Pydantic models defined in the bootstrap
    assert "BaseModel" not in src, "models must live in routers, not server.py"
    assert len(src.splitlines()) < 90, "server.py is no longer a thin bootstrap"


def test_no_duplicate_routes_and_single_registration():
    import importlib
    server = importlib.import_module("server")
    seen = {}
    for r in server.app.routes:
        for method in getattr(r, "methods", []) or []:
            if method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                key = (method, r.path)
                seen[key] = seen.get(key, 0) + 1
    dups = {k: v for k, v in seen.items() if v > 1}
    assert not dups, f"duplicate route registrations: {dups}"


def test_no_leftover_build_artifacts():
    for name in ("server.py.orig", "_build_modules.py"):
        assert not os.path.exists(os.path.join(BACKEND, name)), f"{name} should be removed"
