"""The external Google sign-in cannot open an account that has a password.

`/auth/google/session` takes the email address on the word of an external session
service and signs that account in. For an account created through it that is the only
way in; for an account with a password -- the platform operator's included -- it was a
second way in that bypassed the password entirely.
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("JWT_SECRET", "external-signin-unit-jwt-secret-long-enough-1")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

import server


class _Request:
    def __init__(self, session_id):
        self._body = {"session_id": session_id}

    async def json(self):
        return self._body


def _signin(monkeypatch, email):
    monkeypatch.setattr(server.requests, "get", lambda *a, **k: SimpleNamespace(
        status_code=200, json=lambda: {"email": email, "name": "Someone",
                                       "session_token": f"sess_{uuid.uuid4().hex}"}))
    name = f"clientverse_signin_{uuid.uuid4().hex[:8]}"

    async def body():
        server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
        previous, server.db = server.db, server.mclient[name]
        try:
            await server.db.users.insert_one({
                "user_id": "user_pw", "email": "operator@example.com", "role": "admin",
                "tenant_id": "ten_op", "password_hash": server.hash_password("Secret2026!"),
                "auth": "password"})
            return await server.google_session(_Request("sid"), server.Response())
        finally:
            await server.mclient.drop_database(name)
            server.db = previous

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(body())
    finally:
        loop.close()


def test_an_account_with_a_password_is_not_opened_by_the_external_signin(monkeypatch):
    with pytest.raises(server.HTTPException) as refused:
        _signin(monkeypatch, "operator@example.com")
    assert refused.value.status_code == 403


def test_a_new_person_can_still_sign_up_through_it(monkeypatch):
    result = _signin(monkeypatch, f"new_{uuid.uuid4().hex[:6]}@example.com")
    assert result["user"]["role"] == "admin" and result["token"].startswith("sess_")
