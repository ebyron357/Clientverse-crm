"""T6: non-secret git_sha on GET /api/health (DoD parity probe)."""

import os
import sys
from unittest.mock import AsyncMock
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_git_sha_health_unit")
os.environ.setdefault("JWT_SECRET", "git-sha-health-unit-jwt-secret-long-enough-12")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

import server  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _reset_motor_client():
    server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
    server.db = server.mclient[os.environ["DB_NAME"]]


def test_resolve_git_sha_prefers_git_sha_then_railway_then_vercel(monkeypatch):
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT", raising=False)
    monkeypatch.delenv("VERCEL_GIT_COMMIT_SHA", raising=False)
    assert server.resolve_git_sha() is None

    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "vercelsha")
    assert server.resolve_git_sha() == "vercelsha"

    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "railwaysha")
    assert server.resolve_git_sha() == "railwaysha"

    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA")
    monkeypatch.setenv("RAILWAY_GIT_COMMIT", "legacyrailwaysha")
    assert server.resolve_git_sha() == "legacyrailwaysha"

    monkeypatch.setenv("GIT_SHA", "explicitsha")
    assert server.resolve_git_sha() == "explicitsha"

    monkeypatch.setenv("GIT_SHA", "  ")
    assert server.resolve_git_sha() == "legacyrailwaysha"


def test_health_includes_null_git_sha_when_unset(monkeypatch):
    for key in ("GIT_SHA", "RAILWAY_GIT_COMMIT_SHA", "RAILWAY_GIT_COMMIT", "VERCEL_GIT_COMMIT_SHA"):
        monkeypatch.delenv(key, raising=False)
    _reset_motor_client()
    with TestClient(server.app) as client:
        r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "ClientVerse"
    assert body["version"] == "v1"
    assert body["status"] == "ok"
    assert body["database"] == "up"
    assert "git_sha" in body
    assert body["git_sha"] is None


def test_health_includes_git_sha_from_env(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc123def456")
    _reset_motor_client()
    with TestClient(server.app) as client:
        r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"
    assert body["git_sha"] == "abc123def456"


def test_degraded_health_includes_git_sha(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "degradedsha123")
    _reset_motor_client()
    with TestClient(server.app) as client:
        monkeypatch.setattr(server.db, "command", AsyncMock(side_effect=RuntimeError("database unavailable")))
        r = client.get("/api/health")
    assert r.status_code == 503
    assert r.json() == {
        "service": "ClientVerse",
        "version": "v1",
        "status": "degraded",
        "database": "down",
        "git_sha": "degradedsha123",
    }
