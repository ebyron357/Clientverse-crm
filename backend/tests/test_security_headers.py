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

import server  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def test_response_includes_a_content_security_policy_header():
    with TestClient(server.app) as client:
        r = client.get("/api/health")
    assert r.status_code == 200
    csp = r.headers.get("content-security-policy")
    assert csp, "expected a Content-Security-Policy header on every response"
    assert "default-src 'self'" in csp


def test_existing_security_headers_are_unchanged_by_the_csp_addition():
    with TestClient(server.app) as client:
        r = client.get("/api/health")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "SAMEORIGIN"
    assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
