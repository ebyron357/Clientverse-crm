"""Centralised test configuration for ClientVerse backend tests.

Every test file imports credentials and base URL from here.
No test file may contain a hard-coded password or a fallback to an
external preview/production URL.

Required environment variables (set in CI or your local shell):
    ADMIN_EMAIL          — seeded admin email
    ADMIN_PASSWORD       — seeded admin password
    DEMO_MEMBER_EMAIL    — seeded member email
    DEMO_MEMBER_PASSWORD — seeded member password

Optional:
    REACT_APP_BACKEND_URL — backend base URL (default: http://localhost:8001)
    MONGO_URL             — MongoDB connection (default: mongodb://localhost:27017)
    DB_NAME               — database name (default: test_database)
"""

import os
import sys

import requests

_MISSING: list[str] = []


def _require(var: str) -> str:
    """Return an env-var value or record it as missing."""
    val = os.environ.get(var)
    if not val:
        _MISSING.append(var)
        return ""
    return val


# -- Credentials (no defaults) ------------------------------------------------
ADMIN_EMAIL = _require("ADMIN_EMAIL")
ADMIN_PASSWORD = _require("ADMIN_PASSWORD")
DEMO_MEMBER_EMAIL = _require("DEMO_MEMBER_EMAIL")
DEMO_MEMBER_PASSWORD = _require("DEMO_MEMBER_PASSWORD")

if _MISSING:
    msg = (
        "Test configuration incomplete — the following environment variables "
        f"are required but not set: {', '.join(_MISSING)}.\n"
        "Set them in your shell or CI environment before running the test suite."
    )
    print(f"\n\033[91mERROR: {msg}\033[0m\n", file=sys.stderr)
    raise SystemExit(msg)

# -- Convenience dicts ---------------------------------------------------------
ADMIN_CREDS = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
MEMBER_CREDS = {"email": DEMO_MEMBER_EMAIL, "password": DEMO_MEMBER_PASSWORD}

# -- URLs (safe localhost default, never an external host) ---------------------
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

# -- MongoDB (direct access for tests that need it) ---------------------------
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


# -- Shared helpers ------------------------------------------------------------

def login(creds: dict) -> str:
    """Log in and return the bearer token; fails the test on error."""
    r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.text}"
    return r.json()["token"]


def auth_header(token: str) -> dict:
    """Return an Authorization header dict."""
    return {"Authorization": f"Bearer {token}"}
