"""Content-Security-Policy header test (pilot-readiness security pass, Phase 4).

Uses FastAPI's TestClient against the real `app` object in-process (starts/stops the
real lifespan against server.db), so no separately-running server or network is needed
-- consistent with how the other in-process tests in this suite import `server` directly.
"""

import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_security_headers_unit")
os.environ.setdefault("JWT_SECRET", "security-headers-unit-jwt-secret-long-enough-12")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

from fastapi.testclient import TestClient

import server


def _reset_motor_client():
    # Each `with TestClient(...)` block runs the ASGI lifespan on its own anyio-managed
    # event loop. Motor's AsyncIOMotorClient binds to whatever loop is running the first
    # time it performs an operation, so reusing the same client object across two
    # separate TestClient blocks (each with their own loop) breaks it with "Event loop is
    # closed" against a real MongoDB (a mongomock substitute has no such binding, which is
    # why this only surfaced against real CI). Give each block its own fresh client.
    server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
    server.db = server.mclient[os.environ["DB_NAME"]]


def test_response_includes_a_content_security_policy_header():
    _reset_motor_client()
    with TestClient(server.app) as client:
        r = client.get("/api/health")
    assert r.status_code == 200
    csp = r.headers.get("content-security-policy")
    assert csp, "expected a Content-Security-Policy header on every response"
    assert "default-src 'self'" in csp


def test_existing_security_headers_are_unchanged_by_the_csp_addition():
    _reset_motor_client()
    with TestClient(server.app) as client:
        r = client.get("/api/health")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "SAMEORIGIN"
    assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
