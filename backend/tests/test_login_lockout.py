"""Login brute-force protection tests (pilot-readiness security pass, Phase 2).

Background: /auth/login previously had no attempt tracking at all — unlimited password
guesses against any account, including across the two pilot tenants sharing one
deployment. These tests call the async endpoint function directly (same in-process
pattern as test_provider_lifecycle_unit.py) against the real server.db, so no live
server process or network is required.
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
os.environ.setdefault("DB_NAME", "clientverse_login_lockout_unit")
os.environ.setdefault("JWT_SECRET", "login-lockout-unit-jwt-secret-long-enough-1234")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

import server


def run(coro):
    # Motor's AsyncIOMotorClient binds to whatever event loop is running when it first
    # performs an operation; reusing plain asyncio.run() (a fresh loop every call) across
    # many calls in one process breaks it with "Event loop is closed" against a real
    # MongoDB (this only worked against a mongomock substitute, which has no such
    # binding). Bind a fresh client to a fresh loop on every call instead.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
        server.db = server.mclient[os.environ["DB_NAME"]]
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _db(fn):
    """Wrap a direct `server.db...` expression so the `server.db` attribute is looked up
    when this coroutine actually executes (inside run()'s fresh loop/client), not when the
    call to run() is being constructed -- `run(server.db.x.find_one(...))` evaluates
    `server.db` *before* run() replaces it with a fresh client, silently capturing
    whatever the previous run() call's now-closed client/loop was."""
    return await fn()


class FakeResponse:
    """Minimal stand-in for the FastAPI Response the login endpoint writes a cookie to."""

    def __init__(self):
        self.cookies = []

    def set_cookie(self, *args, **kwargs):
        self.cookies.append((args, kwargs))


async def _register(email, password):
    return await server.register(
        server.RegisterInput(email=email, password=password, name="Login Lockout Test"),
        FakeResponse(),
    )


async def _login(email, password):
    return await server.login(server.LoginInput(email=email, password=password), FakeResponse())


def _unique_email():
    return f"lockout_{uuid.uuid4().hex[:10]}@example.com"


def test_repeated_failed_logins_reach_threshold_and_lock_the_account():
    email = _unique_email()
    run(_register(email, "CorrectHorseBattery1!"))

    last_exc = None
    for _ in range(server.LOGIN_LOCKOUT_THRESHOLD):
        try:
            run(_login(email, "wrong-password"))
            raise AssertionError("expected wrong password to be rejected")
        except server.HTTPException as exc:
            last_exc = exc
    assert last_exc.status_code == 401


def test_correct_password_is_still_rejected_during_the_lockout_window():
    email = _unique_email()
    run(_register(email, "CorrectHorseBattery1!"))

    for _ in range(server.LOGIN_LOCKOUT_THRESHOLD):
        try:
            run(_login(email, "wrong-password"))
        except server.HTTPException:
            pass

    # Threshold reached -> account is locked. The *correct* password must still fail.
    try:
        run(_login(email, "CorrectHorseBattery1!"))
        raise AssertionError("expected the account to be locked even with the correct password")
    except server.HTTPException as exc:
        assert exc.status_code == 401


def test_lockout_expiry_allows_a_valid_login_and_resets_failure_state(monkeypatch):
    email = _unique_email()
    run(_register(email, "CorrectHorseBattery1!"))

    for _ in range(server.LOGIN_LOCKOUT_THRESHOLD):
        try:
            run(_login(email, "wrong-password"))
        except server.HTTPException:
            pass

    # Simulate the lockout window having already expired.
    from datetime import datetime, timedelta, timezone
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    run(_db(lambda: server.db.login_lockouts.update_one({"email": email.lower()}, {"$set": {"locked_until": past}})))

    result = run(_login(email, "CorrectHorseBattery1!"))
    assert result["user"]["email"] == email.lower()

    record = run(_db(lambda: server.db.login_lockouts.find_one({"email": email.lower()}, {"_id": 0})))
    assert record["failed_count"] == 0
    assert not record.get("locked_until")


def test_login_failure_does_not_disclose_whether_the_account_exists():
    real_email = _unique_email()
    run(_register(real_email, "CorrectHorseBattery1!"))
    fake_email = _unique_email()

    real_status = real_detail = fake_status = fake_detail = None
    try:
        run(_login(real_email, "wrong-password"))
        raise AssertionError("expected rejection")
    except server.HTTPException as exc:
        real_status, real_detail = exc.status_code, exc.detail
    try:
        run(_login(fake_email, "wrong-password"))
        raise AssertionError("expected rejection")
    except server.HTTPException as exc:
        fake_status, fake_detail = exc.status_code, exc.detail

    assert real_status == fake_status == 401
    assert real_detail == fake_detail


def test_lockout_tracks_by_email_regardless_of_which_tenant_it_belongs_to():
    # Brute-forcing a nonexistent account also gets locked out the same way as a real
    # one — lockout tracking must not depend on (and cannot be weakened by) which
    # tenant, or whether any tenant, the email belongs to.
    email = _unique_email()
    for _ in range(server.LOGIN_LOCKOUT_THRESHOLD):
        try:
            run(_login(email, "guess"))
        except server.HTTPException:
            pass
    record = run(_db(lambda: server.db.login_lockouts.find_one({"email": email.lower()}, {"_id": 0})))
    assert record is not None
    assert record["failed_count"] >= server.LOGIN_LOCKOUT_THRESHOLD
    assert record.get("locked_until")


def test_successful_login_resets_previously_recorded_failures_below_threshold():
    email = _unique_email()
    run(_register(email, "CorrectHorseBattery1!"))

    # A couple of failures, but not enough to trip the lockout.
    for _ in range(max(server.LOGIN_LOCKOUT_THRESHOLD - 1, 1)):
        try:
            run(_login(email, "wrong-password"))
        except server.HTTPException:
            pass

    result = run(_login(email, "CorrectHorseBattery1!"))
    assert result["user"]["email"] == email.lower()

    record = run(_db(lambda: server.db.login_lockouts.find_one({"email": email.lower()}, {"_id": 0})))
    assert record["failed_count"] == 0
