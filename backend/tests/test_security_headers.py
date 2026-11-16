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
    assert r.headers.get("cache-control") == "no-store"
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


# Exercise the production middleware without a database or authentication fixtures.
# Sensitive payloads include signed-out responses (tokens, public portal records),
# so the policy must follow the API boundary, not only the Authorization header.
def _cache_policy_app():
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import RedirectResponse, Response, StreamingResponse

    app = FastAPI()
    app.middleware("http")(server.production_security_headers)

    @app.get("/api/records")
    @app.get("/api")
    def records():
        # A handler must not accidentally opt a tenant's data into shared caching.
        return Response("synthetic record", headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/api/export")
    def export():
        return StreamingResponse(iter([b"synthetic export"]), media_type="text/csv")

    @app.get("/api/denied")
    def denied():
        raise HTTPException(status_code=403, detail="denied")

    @app.get("/api/redirect")
    def redirect():
        return RedirectResponse("/api/records")

    @app.get("/static/js/main.hash.js")
    @app.get("/apiculture")
    def asset():
        return Response("bundle", headers={"Cache-Control": "public, max-age=31536000, immutable"})

    return app


def test_api_responses_cannot_be_stored_even_when_a_handler_enables_caching():
    client = TestClient(_cache_policy_app())
    for path in ("/api", "/api/records", "/api/export", "/api/denied", "/api/redirect", "/api/missing"):
        response = client.get(path, follow_redirects=False)
        assert response.headers.get("cache-control") == "no-store", path
        assert response.headers.get("pragma") == "no-cache", path
        assert response.headers.get("expires") == "0", path
    assert client.get("/api/records").text == "synthetic record"
    assert client.get("/api/export").text == "synthetic export"
    assert client.get("/api/denied").status_code == 403
    assert client.get("/api/missing").status_code == 404
    assert client.get("/api/redirect", follow_redirects=False).status_code == 307


def test_api_cache_policy_preserves_static_asset_caching_and_path_boundaries():
    client = TestClient(_cache_policy_app())
    for path in ("/static/js/main.hash.js", "/apiculture"):
        response = client.get(path)
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert "pragma" not in response.headers
        assert "expires" not in response.headers
