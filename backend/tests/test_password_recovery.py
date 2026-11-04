"""Exercise anonymous recovery through the real API and database (MongoDB in CI).

Only the email transport is replaced. Never send email or reset a production user.
"""

import asyncio
import os
import re
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_recovery_tests")
os.environ.setdefault("JWT_SECRET", "recovery-test-jwt-key-at-least-32-characters")
os.environ.setdefault("ADMIN_EMAIL", "recovery-owner@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "Initial-test-password!")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ["APP_ENV"] = "test"
os.environ["LEAD_SLA_WATCHER"] = "0"

import password_recovery as recovery
import server

OLD = "Initial-test-password!"
NEW = "My-chosen-new-password!"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://crm.clientverse.io")
    monkeypatch.setenv("PASSWORD_RECOVERY_RESEND_API_KEY", "test-only-not-a-provider-key")
    monkeypatch.setenv("PASSWORD_RECOVERY_FROM", "ClientVerse <security@example.com>")
    monkeypatch.setenv("SEED_DEMO_DATA", "false")
    monkeypatch.setenv("ADMIN_PASSWORD", OLD)
    motor = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
    database = motor[f"recovery_test_{uuid.uuid4().hex}"]
    monkeypatch.setattr(server, "db", database)
    monkeypatch.setattr(server, "mclient", motor)
    sent = []

    async def mail(to, subject, text, message_id):
        sent.append({"to": to, "subject": subject, "text": text, "id": message_id})

    async def idle(self):
        await asyncio.Event().wait()

    monkeypatch.setattr(recovery, "send_mail", mail)
    monkeypatch.setattr(recovery.PasswordRecovery, "run", idle)
    with TestClient(server.app) as client:
        yield client, database, sent
        client.portal.call(motor.drop_database, database.name)


def account(env):
    client, _, _ = env
    email = f"recover_{uuid.uuid4().hex}@example.com"
    response = client.post("/api/auth/register", json={"email": email, "password": OLD, "name": "Recovery test"})
    assert response.status_code == 200
    client.cookies.clear()
    return email, response.json()["token"], response.json()["user"]


def request(env, email):
    return env[0].post("/api/auth/forgot-password", json={"email": email})


def deliver(env):
    env[0].portal.call(recovery.PasswordRecovery(env[1]).deliver_one)


def link(env, email):
    assert request(env, email).status_code == 202
    deliver(env)
    return re.search(r"#token=([A-Za-z0-9_-]+)", env[2][-1]["text"])[1]


def reset(env, token, password=NEW):
    return env[0].post("/api/auth/reset-password", json={"token": token, "new_password": password})


def test_signed_out_owner_recovers_and_restart_does_not_restore_bootstrap(env):
    client, db, sent = env
    email = os.environ["ADMIN_EMAIL"].lower()
    old = client.post("/api/auth/login", json={"email": email, "password": OLD}).json()["token"]
    client.cookies.clear()
    token = link(env, email.upper())
    assert reset(env, token).status_code == 200
    assert not client.cookies.get("access_token")  # no automatic sign-in
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {old}"}).status_code == 401
    client.portal.call(server.seed)
    assert client.post("/api/auth/login", json={"email": email, "password": OLD}).status_code == 401
    success = client.post("/api/auth/login", json={"email": email, "password": NEW})
    assert success.status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    deliver(env)
    assert sent[-1]["subject"] == "Your ClientVerse password was changed"
    assert token not in sent[-1]["text"] and NEW not in sent[-1]["text"]
    event = client.portal.call(db.password_recovery_events.find_one, {"outcome": "reset_completed"})
    assert event


def test_unknown_and_known_have_identical_responses_and_no_request_time_lookup(env, monkeypatch):
    email, _, _ = account(env)
    original = type(env[1].users).find_one
    async def forbidden(collection, *args, **kwargs):
        if collection.name == "users":
            raise AssertionError("Request path must not look up account or send mail")
        return await original(collection, *args, **kwargs)
    monkeypatch.setattr(type(env[1].users), "find_one", forbidden)
    known = request(env, email)
    unknown = request(env, "unknown@example.com")
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json() == {"message": recovery.GENERIC_MESSAGE}
    assert not env[2]


def test_delivery_unknown_accounts_never_creates_users(env):
    request(env, "unknown@example.com")
    deliver(env)
    assert not env[2]
    assert env[0].portal.call(env[1].users.find_one, {"email": "unknown@example.com"}) is None


def test_link_hashes_and_mail_jobs_do_not_store_plaintext_capabilities(env):
    email, _, _ = account(env)
    request(env, email)
    job = env[0].portal.call(env[1].password_recovery_jobs.find_one, {"state": "queued"})
    assert email not in str(job)
    deliver(env)
    token = re.search(r"#token=([A-Za-z0-9_-]+)", env[2][-1]["text"])[1]
    grant = env[0].portal.call(env[1].password_recovery_grants.find_one, {})
    assert grant["_id"] == recovery.digest(token) and token not in str(grant)
    assert len(token) == 43
    job = env[0].portal.call(env[1].password_recovery_jobs.find_one, {"_id": job["_id"]})
    assert "recipient" not in job
    assert "/reset-password#token=" in env[2][-1]["text"]


def test_expired_token_is_refused_even_before_ttl_deletion(env):
    email, _, _ = account(env)
    token = link(env, email)
    env[0].portal.call(env[1].password_recovery_grants.update_one, {"_id": recovery.digest(token)},
                       {"$set": {"expires_at": recovery.utcnow() - timedelta(seconds=1)}})
    assert reset(env, token).status_code == 400


def test_two_links_single_use_and_concurrent_resets(env):
    email, _, _ = account(env)
    first, second = link(env, email), link(env, email)
    async def race():
        service = recovery.PasswordRecovery(env[1])
        return await asyncio.gather(*[
            service.reset(token, NEW, "test-peer", server.hash_password, server._new_password_problem)
            for token in (first, first, second)], return_exceptions=True)
    results = env[0].portal.call(race)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert reset(env, first).status_code == reset(env, second).status_code == 400


@pytest.mark.parametrize("bad", ["short", " " * 12, "é" * 37])
def test_password_policy_keeps_token_usable_after_validation_failure(env, bad):
    email, _, _ = account(env)
    token = link(env, email)
    assert reset(env, token, bad).status_code == 422
    assert reset(env, token).status_code == 200


def test_change_password_invalidates_pending_links(env):
    email, session, _ = account(env)
    token = link(env, email)
    assert env[0].post("/api/auth/change-password", headers={"Authorization": f"Bearer {session}"},
                       json={"current_password": OLD, "new_password": NEW}).status_code == 200
    assert reset(env, token).status_code == 400


def test_queued_request_does_not_issue_link_after_password_changed(env):
    email, session, _ = account(env)
    request(env, email)
    env[0].post("/api/auth/change-password", headers={"Authorization": f"Bearer {session}"},
                json={"current_password": OLD, "new_password": NEW})
    deliver(env)
    assert not env[2]


def test_disabled_membership_stays_disabled(env):
    email, _, user = account(env)
    token = link(env, email)
    env[0].portal.call(env[1].memberships.update_many, {"user_id": user["user_id"]}, {"$set": {"status": "disabled"}})
    assert reset(env, token).status_code == 400
    request(env, email)
    deliver(env)
    assert len(env[2]) == 1


def test_lockout_cleared_only_after_proof_and_legacy_sessions_revoked(env):
    email, session, user = account(env)
    env[0].portal.call(env[1].login_lockouts.insert_one, {"email": email, "failed_count": 99,
        "locked_until": (recovery.utcnow() + timedelta(minutes=15)).isoformat()})
    env[0].portal.call(env[1].user_sessions.insert_one, {"user_id": user["user_id"], "session_token": "legacy-test"})
    token = link(env, email)
    assert env[0].portal.call(server._login_is_locked, email)
    assert reset(env, token).status_code == 200
    assert not env[0].portal.call(server._login_is_locked, email)
    assert env[0].portal.call(env[1].user_sessions.count_documents, {"user_id": user["user_id"]}) == 0
    assert env[0].get("/api/auth/me", headers={"Authorization": f"Bearer {session}"}).status_code == 401


def test_account_limits_shared_across_instances_and_unknowns(env):
    email, _, _ = account(env)
    for address in (email, "unknown@example.com"):
        for _ in range(5):
            assert request(env, address).status_code == 202
    assert env[0].portal.call(env[1].password_recovery_jobs.count_documents, {}) == 6


def test_ip_limits_ignore_spoofed_forwarded_headers(env):
    for i in range(22):
        result = env[0].post("/api/auth/forgot-password", json={"email": f"person{i}@example.com"},
                            headers={"X-Forwarded-For": f"192.0.2.{i}"})
        assert result.status_code == 202
    assert env[0].portal.call(env[1].password_recovery_jobs.count_documents, {}) == 20


def test_invalid_reset_is_rate_limited_without_locking_accounts(env):
    for _ in range(30):
        assert reset(env, "invalid").status_code == 400
    assert reset(env, "invalid").status_code == 429


def test_missing_config_is_generic_and_audited(env, monkeypatch):
    monkeypatch.delenv("PASSWORD_RECOVERY_RESEND_API_KEY")
    assert request(env, os.environ["ADMIN_EMAIL"]).json() == {"message": recovery.GENERIC_MESSAGE}
    assert env[0].portal.call(env[1].password_recovery_events.find_one, {"outcome": "configuration_unavailable"})


def test_provider_failure_invalidates_grant_and_does_not_leak(env, monkeypatch, caplog):
    email, _, _ = account(env)
    async def fail(*args):
        raise RuntimeError("sensitive-provider-body")
    monkeypatch.setattr(recovery, "send_mail", fail)
    request(env, email)
    deliver(env)
    assert env[0].portal.call(env[1].password_recovery_grants.count_documents, {}) == 0
    assert "sensitive-provider-body" not in caplog.text and email not in caplog.text
    assert env[0].portal.call(env[1].password_recovery_events.find_one, {"outcome": "delivery_failed"})


def test_recovery_origin_and_response_headers(env, monkeypatch):
    for origin in ("http://crm.clientverse.io", "https://evil.test@crm.clientverse.io", "https://crm.clientverse.io/path"):
        monkeypatch.setenv("FRONTEND_URL", origin)
        with pytest.raises(ValueError):
            recovery.configuration()
    assert env[0].post("/api/auth/forgot-password", json={"email": "any@example.com"},
                       headers={"Origin": "https://evil.test"}).status_code == 403
    response = reset(env, "invalid")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_millisecond_and_login_race_sessions_are_revoked(env):
    email, _, user = account(env)
    token = link(env, email)
    assert reset(env, token).status_code == 200
    # Even a token issued later by an in-flight login using the old credential has
    # no new session_version, so timestamps cannot let it back in.
    stale = server.create_access_token(user["user_id"], email)
    assert env[0].get("/api/auth/me", headers={"Authorization": f"Bearer {stale}"}).status_code == 401


def test_failed_password_write_does_not_consume_link(env, monkeypatch):
    email, _, _ = account(env)
    token = link(env, email)
    original = type(env[1].users).update_one
    async def fail(collection, *args, **kwargs):
        if collection.name == "users":
            raise RuntimeError("simulated database outage")
        return await original(collection, *args, **kwargs)
    monkeypatch.setattr(type(env[1].users), "update_one", fail)
    with pytest.raises(RuntimeError, match="simulated database outage"):
        reset(env, token)
    monkeypatch.setattr(type(env[1].users), "update_one", original)
    assert reset(env, token).status_code == 200


def test_request_host_cannot_change_email_link_and_only_recipient_can_reset(env):
    email, _, user = account(env)
    other_email, _, other = account(env)
    result = env[0].post("/api/auth/forgot-password", headers={"Host": "evil.test"}, json={"email": email})
    assert result.status_code == 202
    deliver(env)
    assert "https://crm.clientverse.io/reset-password#token=" in env[2][-1]["text"]
    assert "evil.test" not in env[2][-1]["text"]
    token = re.search(r"#token=([A-Za-z0-9_-]+)", env[2][-1]["text"])[1]
    assert env[0].post("/api/auth/reset-password", json={"token": token, "new_password": NEW,
                        "email": other_email, "user_id": other["user_id"]}).status_code == 200
    assert env[0].post("/api/auth/login", json={"email": other_email, "password": OLD}).status_code == 200


def test_old_mailbox_link_is_invalid_after_identity_email_changes(env):
    email, _, user = account(env)
    token = link(env, email)
    env[0].portal.call(env[1].users.update_one, {"user_id": user["user_id"]},
                       {"$set": {"email": "changed-mailbox@example.com"}})
    assert reset(env, token).status_code == 400


def test_resend_transport_contract_and_failure_redaction(monkeypatch):
    import httpx
    monkeypatch.setenv("FRONTEND_URL", "https://crm.clientverse.io")
    monkeypatch.setenv("PASSWORD_RECOVERY_RESEND_API_KEY", "test-only-key")
    monkeypatch.setenv("PASSWORD_RECOVERY_FROM", "ClientVerse <security@example.com>")
    captured = []
    status = 200
    def handler(req):
        captured.append(req)
        return httpx.Response(status, json={"id": "test-message"})
    original = httpx.AsyncClient
    monkeypatch.setattr(recovery.httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(handler), **kwargs))
    asyncio.run(recovery.send_mail("recipient@example.com", "Reset", "test-only-body", "test-id"))
    assert str(captured[0].url) == "https://api.resend.com/emails"
    assert captured[0].headers["Idempotency-Key"] == "test-id"
    assert captured[0].headers["Authorization"] == "Bearer test-only-key"
    for status in (302, 401, 429, 500):
        assert status != 200
        with pytest.raises(RuntimeError, match=r"^recovery_delivery_failed$"):
            asyncio.run(recovery.send_mail("recipient@example.com", "Reset", "test-only-body", "test-id"))
