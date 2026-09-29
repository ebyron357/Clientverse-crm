"""The ops review, as tests: sweeps one tenant could starve, auth that raced, and mail
that could carry a stranger's HTML. Each used to succeed."""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("JWT_SECRET", "ops-hardening-unit-jwt-secret-long-enough-12345")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

import approval_queue as aq
import conversations as cv
import server

API = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/") + "/api"


def ago(**kwargs):
    return (datetime.now(timezone.utc) - timedelta(**kwargs)).isoformat()


def isolated(body):
    """Run `body()` with `server.db` pointed at a throwaway database."""
    name = f"clientverse_ops_{uuid.uuid4().hex[:10]}"

    async def wrapped():
        server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
        previous, server.db = server.db, server.mclient[name]
        try:
            await server.db.login_lockouts.create_index("email", unique=True)
            await server.db.alerts.create_index(
                [("tenant_id", 1), ("open_key", 1)], unique=True,
                partialFilterExpression={"open_key": {"$type": "string"}})
            return await body()
        finally:
            await server.mclient.drop_database(name)
            server.db = previous

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(wrapped())
    finally:
        loop.close()


# ------------------------------------------------------------------ sweeps

def test_one_tenant_cannot_switch_off_the_commitment_sweep_for_others():
    async def body():
        db = server.db
        await db.commitments.insert_many([
            {"id": f"junk_{n}", "tenant_id": "ten_attacker", "status": "open",
             "due_date": "not-a-date", "title": "x"} for n in range(5000)])
        await db.commitments.insert_one({"id": "victim", "tenant_id": "ten_victim",
                                         "status": "open", "due_date": ago(days=3),
                                         "title": "Due"})
        await server.evaluate_commitment_risk(tenant_id=None, actor="cron")
        return (await db.commitments.find_one({"id": "victim"}))["status"]

    assert isolated(body) == "breached"


def test_one_tenants_live_approvals_cannot_starve_anothers_lapsed_one():
    async def body():
        db = server.db
        await db[cv.MESSAGES].insert_many([
            {"id": f"busy_{n}", "tenant_id": "ten_busy", "status": cv.PENDING_APPROVAL,
             "approval_id": f"apr_busy_{n}", "history": []} for n in range(600)])
        await db[aq.COLLECTION].insert_many([
            {"id": f"apr_busy_{n}", "tenant_id": "ten_busy", "status": aq.REQUESTED,
             "subject_type": "communication_message", "subject_id": f"busy_{n}"}
            for n in range(600)])
        await db[cv.MESSAGES].insert_one({
            "id": "victim_msg", "tenant_id": "ten_victim", "status": cv.PENDING_APPROVAL,
            "approval_id": "apr_victim", "history": []})
        await db[aq.COLLECTION].insert_one({
            "id": "apr_victim", "tenant_id": "ten_victim", "status": aq.EXPIRED,
            "subject_type": "communication_message", "subject_id": "victim_msg"})
        await cv.release_lapsed_approvals(db)
        return (await db[cv.MESSAGES].find_one({"id": "victim_msg"}))["status"]

    assert isolated(body) == cv.BLOCKED


def test_reconciliation_moves_on_from_messages_it_cannot_resolve():
    async def body():
        db = server.db
        await db[cv.MESSAGES].insert_many([
            {"id": f"stuck_{n}", "tenant_id": "ten_a", "status": cv.OUTCOME_UNKNOWN,
             "channel": "carrier-pigeon", "history": []} for n in range(250)])
        await db[cv.MESSAGES].insert_one({
            "id": "later", "tenant_id": "ten_b", "status": cv.OUTCOME_UNKNOWN,
            "channel": "carrier-pigeon", "history": []})
        await server.run_reconcile_unknown_sweep(actor="test")
        await server.run_reconcile_unknown_sweep(actor="test")
        return await db[cv.MESSAGES].find_one({"id": "later"})

    assert isolated(body).get("reconcile_checked_at")


def test_health_alerts_read_the_newest_snapshot():
    async def body():
        db = server.db
        await db.workspaces.insert_one({"id": "ws_h", "tenant_id": "ten_h", "name": "Acme"})
        await db.health_snapshots.insert_many([
            {"id": "hs_1", "tenant_id": "ten_h", "workspace_id": "ws_h", "score": 80,
             "band": "healthy", "at": ago(days=3)},
            {"id": "hs_2", "tenant_id": "ten_h", "workspace_id": "ws_h", "score": 30,
             "band": "critical", "at": ago(hours=1)}])
        await server.evaluate_alerts("ten_h")
        return await db.alerts.find({"tenant_id": "ten_h", "type": "health_critical"}).to_list(5)

    assert len(isolated(body)) == 1


def test_racing_evaluations_raise_one_alert_not_many():
    async def body():
        await asyncio.gather(*(server._upsert_alert(
            "ten_r", "ws", "commitment_breach", "critical", "commitment", "Breached",
            "commitment:c1") for _ in range(10)))
        return await server.db.alerts.count_documents({"tenant_id": "ten_r"})

    assert isolated(body) == 1


# ------------------------------------------------------------------ mail

def test_alert_mail_escapes_what_a_user_typed(monkeypatch):
    sent = []

    async def capture(to, subject, html):
        sent.append(html)
        return "mid"

    monkeypatch.setattr(server, "send_email", capture)
    monkeypatch.setattr(server, "email_configured", lambda: True)

    async def body():
        await server.db.memberships.insert_one({"tenant_id": "ten_m", "user_id": "u1",
                                                "email": "a@x.test", "role": "admin",
                                                "status": "active"})
        alert = {"id": "al_1", "tenant_id": "ten_m", "type": "commitment_breach",
                 "severity": "critical", "workspace_id": None,
                 "summary": 'Commitment breached: <a href="https://evil.example/login">verify</a>'}
        await server.notify_alert(alert, "critical")

    isolated(body)
    assert sent and "<a href" not in sent[0] and "&lt;a href" in sent[0]


def test_an_admin_who_turned_email_off_is_not_emailed(monkeypatch):
    async def body():
        db = server.db
        await db.memberships.insert_many([
            {"tenant_id": "ten_p", "user_id": "u_on", "email": "on@x.test", "role": "admin",
             "status": "active"},
            {"tenant_id": "ten_p", "user_id": "u_off", "email": "off@x.test", "role": "admin",
             "status": "active"}])
        await db.notification_prefs.insert_one({
            "tenant_id": "ten_p", "user_id": "u_off",
            "channels": {"email": False, "in_app": True}, "daily_digest": False})
        return await server._admin_emails(
            "ten_p", wants=lambda p: bool((p.get("channels") or {}).get("email")))

    assert isolated(body) == ["on@x.test"]


# ------------------------------------------------------------------ auth

def test_concurrent_guesses_are_counted_before_the_password_is_checked(monkeypatch):
    checked = []

    def counting_verify(password, hashed):
        checked.append(1)
        return False

    monkeypatch.setattr(server, "verify_password", counting_verify)

    async def body():
        await server.db.users.insert_one({"user_id": "u_l", "email": "lock@example.com",
                                          "password_hash": "x", "tenant_id": "t"})

        async def attempt():
            try:
                await server.login(server.LoginInput(email="lock@example.com", password="guess"),
                                   server.Response())
            except server.HTTPException:
                pass

        await asyncio.gather(*(attempt() for _ in range(40)))

    isolated(body)
    assert len(checked) <= server.LOGIN_LOCKOUT_THRESHOLD


def test_an_expired_lock_does_not_relock_on_one_typo():
    async def body():
        db = server.db
        await db.login_lockouts.insert_one({
            "email": "typo@example.com", "failed_count": server.LOGIN_LOCKOUT_THRESHOLD,
            "locked_until": ago(minutes=1), "last_failure_at": ago(minutes=16)})
        with pytest.raises(server.HTTPException):
            await server.login(server.LoginInput(email="typo@example.com", password="typo"),
                               server.Response())
        return await db.login_lockouts.find_one({"email": "typo@example.com"})

    record = isolated(body)
    assert record["failed_count"] == 1 and not record.get("locked_until")


def test_logout_records_only_tokens_this_server_signed():
    async def body():
        db = server.db
        await server._revoke_token("not-a-jwt-" + uuid.uuid4().hex)
        garbage = await db.revoked_tokens.count_documents({})
        token = server.create_access_token("u1", "a@x.test")
        await server._revoke_token(token)
        return garbage, await db.revoked_tokens.count_documents({})

    assert isolated(body) == (0, 1)


def test_invitation_tokens_never_reach_the_access_log():
    import logging

    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 0, '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "GET", "/api/team/invitations/lookup?token=Inv1te-SECRET", "1.1", 200),
        None)
    for handler_filter in logging.getLogger("uvicorn.access").filters:
        handler_filter.filter(record)
    assert "Inv1te-SECRET" not in record.getMessage()


# ------------------------------------------------------------------ over HTTP

def _tenant():
    response = requests.post(f"{API}/auth/register", timeout=30, json={
        "email": f"ops_{uuid.uuid4().hex[:10]}@example.com",
        "password": "OpsHardening2026!", "name": "Ops"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_a_forced_digest_is_throttled():
    headers = _tenant()
    statuses = [requests.post(f"{API}/digest/run", headers=headers, timeout=30).status_code
                for _ in range(server.DIGEST_FORCED_PER_HOUR + 1)]
    assert statuses[-1] == 429 and 429 not in statuses[:-1]


def test_an_unparseable_commitment_due_date_is_refused():
    headers = _tenant()
    ws = requests.post(f"{API}/workspaces", headers=headers, json={"name": "W"},
                       timeout=30).json()["id"]
    refused = requests.post(f"{API}/commitments", headers=headers, timeout=30, json={
        "workspace_id": ws, "title": "x", "due_date": "not-a-date"})
    assert refused.status_code == 422


def test_an_idempotency_key_is_bound_to_its_tool():
    headers = _tenant()
    first = requests.post(f"{API}/mcp/invoke", headers=headers, timeout=30, json={
        "tool": "get_pipeline_summary", "args": {}, "idempotency_key": "shared-key"}).json()
    second = requests.post(f"{API}/mcp/invoke", headers=headers, timeout=30, json={
        "tool": "list_open_commitments", "args": {}, "idempotency_key": "shared-key"}).json()
    assert first.get("tool") == "get_pipeline_summary"
    assert second.get("tool") == "list_open_commitments"
    assert not second.get("idempotent_replay")

