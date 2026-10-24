"""Two doors the production closeout found open.

* `POST /api/auth/google/session` trusted a prototype platform's demo sign-in service to
  name the visitor, then signed them in as the matching user -- the owner included -- or
  opened a new organization for them. It is retired: it answers 410 and creates nothing.
* The scheduled-job ledger (`/api/cron/health`, `/api/cron/runs`) is one log for the whole
  platform. Anyone can register an organization and be its admin, so only the platform
  owner's organization (seeded from ADMIN_EMAIL) and the scheduler's secret may read it.

In-process against the real `app`, with a fresh motor client per test for the reason
given in test_security_headers.py.
"""

import os
import sys
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_closeout_security_unit")
os.environ.setdefault("JWT_SECRET", "closeout-security-unit-jwt-secret-long-enough")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "closeout-security-admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "Closeout-Security-Admin-1!")

from fastapi.testclient import TestClient

import server


def _reset_motor_client():
    server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
    server.db = server.mclient[os.environ["DB_NAME"]]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _count(client, collection, query):
    async def run():
        return await server.db[collection].count_documents(query)
    return client.portal.call(run)


def test_the_prototype_google_sign_in_is_retired_and_creates_nothing():
    _reset_motor_client()
    with TestClient(server.app) as client:
        tenants = _count(client, "tenants", {})
        sessions = _count(client, "user_sessions", {})
        response = client.post("/api/auth/google/session", json={"session_id": "anything"})
        assert response.status_code == 410
        assert "email and password" in response.json()["detail"]
        assert _count(client, "tenants", {}) == tenants
        assert _count(client, "user_sessions", {}) == sessions


def test_only_the_platform_owner_reads_the_platform_wide_scheduler_ledger():
    _reset_motor_client()
    with TestClient(server.app) as client:
        owner = client.post("/api/auth/login", json={"email": os.environ["ADMIN_EMAIL"],
                                                      "password": os.environ["ADMIN_PASSWORD"]})
        assert owner.status_code == 200, owner.text
        owner_token = owner.json()["token"]
        stranger = client.post("/api/auth/register", json={
            "email": f"stranger_{uuid.uuid4().hex[:10]}@example.com",
            "password": "Str0ng-Passw0rd!", "name": "Self-registered admin"})
        assert stranger.status_code == 200 and stranger.json()["user"]["role"] == "admin"
        stranger_token = stranger.json()["token"]
        client.cookies.clear()

        for path in ("/api/cron/health", "/api/cron/runs"):
            assert client.get(path, headers=_h(owner_token)).status_code == 200
            assert client.get(path, headers=_h(stranger_token)).status_code == 403
