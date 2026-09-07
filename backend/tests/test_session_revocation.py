"""Server-side session/token revocation tests (pilot-readiness security pass, Phase 3).

Background: /auth/logout previously only cleared the client-side cookie. A bearer JWT
(also duplicated into the SPA's localStorage) or a Google session_token stayed valid for
its full lifetime after "logout" -- a stolen token survived logout entirely. These tests
call the async endpoint functions directly against the real server.db.
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_session_revocation_unit")
os.environ.setdefault("JWT_SECRET", "session-revocation-unit-jwt-secret-long-enough")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

import server  # noqa: E402


def run(coro):
    return asyncio.run(coro)


class FakeResponse:
    def __init__(self):
        self.cookies = []
        self.deleted_cookies = []

    def set_cookie(self, *args, **kwargs):
        self.cookies.append((args, kwargs))

    def delete_cookie(self, *args, **kwargs):
        self.deleted_cookies.append((args, kwargs))


class FakeRequest:
    """Minimal stand-in for a FastAPI Request carrying a bearer token."""

    def __init__(self, token=None, cookie=None):
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.cookies = {"access_token": cookie} if cookie else {}


def _unique_email():
    return f"revoke_{uuid.uuid4().hex[:10]}@example.com"


async def _register_and_login():
    email = _unique_email()
    await server.register(
        server.RegisterInput(email=email, password="CorrectHorseBattery1!", name="Revocation Test"),
        FakeResponse(),
    )
    result = await server.login(
        server.LoginInput(email=email, password="CorrectHorseBattery1!"), FakeResponse()
    )
    return result["token"]


def test_authenticated_request_succeeds_before_logout():
    token = run(_register_and_login())
    user = run(server.get_current_user(FakeRequest(token=token)))
    assert user["email"]


def test_token_replay_after_logout_is_rejected():
    token = run(_register_and_login())
    run(server.get_current_user(FakeRequest(token=token)))  # sanity: works before logout

    run(server.logout(FakeRequest(token=token), FakeResponse()))

    try:
        run(server.get_current_user(FakeRequest(token=token)))
        raise AssertionError("expected the revoked token to be rejected")
    except server.HTTPException as exc:
        assert exc.status_code == 401


def test_fresh_login_after_logout_issues_a_working_new_token():
    email = _unique_email()
    run(server.register(
        server.RegisterInput(email=email, password="CorrectHorseBattery1!", name="Revocation Test 2"),
        FakeResponse(),
    ))
    first_login = run(server.login(server.LoginInput(email=email, password="CorrectHorseBattery1!"), FakeResponse()))
    first_token = first_login["token"]
    run(server.logout(FakeRequest(token=first_token), FakeResponse()))

    second_login = run(server.login(server.LoginInput(email=email, password="CorrectHorseBattery1!"), FakeResponse()))
    second_token = second_login["token"]

    user = run(server.get_current_user(FakeRequest(token=second_token)))
    assert user["email"] == email.lower()

    try:
        run(server.get_current_user(FakeRequest(token=first_token)))
        raise AssertionError("expected the old, logged-out token to remain rejected")
    except server.HTTPException:
        pass


def test_revocation_does_not_affect_a_different_users_still_valid_token():
    token_a = run(_register_and_login())
    token_b = run(_register_and_login())

    run(server.logout(FakeRequest(token=token_a), FakeResponse()))

    try:
        run(server.get_current_user(FakeRequest(token=token_a)))
        raise AssertionError("token A should be revoked")
    except server.HTTPException:
        pass

    # Token B belongs to a different user/tenant and must be unaffected.
    user_b = run(server.get_current_user(FakeRequest(token=token_b)))
    assert user_b["email"]
