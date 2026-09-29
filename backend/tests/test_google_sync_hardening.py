"""The fourth review round's Google findings, as tests against a real database.

A read-only sync used to decide whether a mailbox could send; a cancelled consent left
both connections stuck; a sync finishing after a disconnect turned the mailbox back on;
the one-mailbox guard only counted healthy connections; disconnecting Calendar revoked
the grant Gmail was still using. Each of these used to happen.
"""

import asyncio
import os
import sys
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("JWT_SECRET", "google-sync-hardening-jwt-secret-long-enough-1")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

import server

TENANT = "ten_gs_a"
OTHER = "ten_gs_b"
ADMIN = {"tenant_id": TENANT, "email": "admin@example.com", "role": "admin"}


def ago(**kwargs):
    return (datetime.now(timezone.utc) - timedelta(**kwargs)).isoformat()


def ahead(**kwargs):
    return (datetime.now(timezone.utc) + timedelta(**kwargs)).isoformat()


def isolated(body):
    name = f"clientverse_gs_{uuid.uuid4().hex[:10]}"

    async def wrapped():
        server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
        previous, server.db = server.db, server.mclient[name]
        try:
            await server.db.alerts.create_index(
                [("tenant_id", 1), ("open_key", 1)], unique=True,
                partialFilterExpression={"open_key": {"$type": "string"}})
            return await body(server.db)
        finally:
            await server.mclient.drop_database(name)
            server.db = previous

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(wrapped())
    finally:
        loop.close()


async def _connect(db, tenant=TENANT, *, status="active", email="owner@example.com"):
    await server.ensure_connections(tenant)
    await db.google_credentials.update_one(
        {"tenant_id": tenant},
        {"$set": {"enc": server.enc_secret({"access_token": "at", "refresh_token": "rt",
                                            "expires_at": 9e9, "scopes": server.GOOGLE_SCOPES}),
                  "account_email": email, "credential_version": 1}}, upsert=True)
    for provider in ("gmail", "google_calendar"):
        await server.set_conn(tenant, provider, status=status, account_identity=email,
                              scopes=list(server.GOOGLE_SCOPES), credential_version=1)


async def _status(db, provider="gmail", tenant=TENANT):
    return (await db.integration_connections.find_one(
        {"tenant_id": tenant, "provider": provider}))["status"]


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return deepcopy(self._payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http_status:{self.status_code}")


class FakeClient:
    def __init__(self, gets=None, posts=None):
        self.gets, self.posts = list(gets or []), list(posts or [])
        self.get_calls, self.post_calls = [], []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        self.get_calls.append((url, deepcopy(kwargs)))
        return self.gets.pop(0) if self.gets else FakeResponse(404)

    async def post(self, url, **kwargs):
        self.post_calls.append((url, deepcopy(kwargs)))
        return self.posts.pop(0) if self.posts else FakeResponse(200)


def _quiet(monkeypatch):
    async def no_sleep(_seconds):
        return None
    monkeypatch.setattr(server.asyncio, "sleep", no_sleep)


# ------------------------------------------------------------ sync vs. authority

def test_a_failed_read_does_not_switch_off_sending(monkeypatch):
    _quiet(monkeypatch)
    seen = []

    async def failing_sync(tenant_id, actor):
        seen.append(await _status(server.db))
        raise RuntimeError("http_status:503")

    monkeypatch.setitem(server.SYNC_FUNCS, "gmail", failing_sync)

    async def body(db):
        await _connect(db)
        await server.run_sync(TENANT, "gmail", "cron")
        return await db.integration_connections.find_one({"tenant_id": TENANT,
                                                          "provider": "gmail"})

    conn = isolated(body)
    assert set(seen) == {"active"}, "a running sync must not take the mailbox offline"
    assert conn["status"] == "active"
    assert conn["sync_status"] == "failed" and conn["consecutive_failures"] == 1


def test_a_sync_that_finishes_after_a_disconnect_does_not_reconnect(monkeypatch):
    _quiet(monkeypatch)

    async def body(db):
        await _connect(db)

        async def disconnected_meanwhile(tenant_id, actor):
            await server.disconnect_provider("gmail", user=ADMIN)
            return {"scanned": 0, "matched": 0}

        monkeypatch.setitem(server.SYNC_FUNCS, "gmail", disconnected_meanwhile)
        monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: FakeClient())
        await server.run_sync(TENANT, "gmail", "cron")
        return await _status(db)

    assert isolated(body) == "disconnected"


def test_an_expired_grant_still_takes_the_mailbox_offline(monkeypatch):
    _quiet(monkeypatch)

    async def revoked(tenant_id, actor):
        raise RuntimeError("token_refresh_failed:401")

    monkeypatch.setitem(server.SYNC_FUNCS, "gmail", revoked)

    async def body(db):
        await _connect(db)
        await server.run_sync(TENANT, "gmail", "cron")
        return await _status(db)

    assert isolated(body) == "expired"


# ------------------------------------------------------------ consent

def _configure_google(monkeypatch):
    monkeypatch.setattr(server, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(server, "GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(server, "GOOGLE_REDIRECT_URI",
                        "https://crm.example/api/integrations/google/callback")


def test_a_cancelled_reconsent_leaves_the_connection_as_it_was(monkeypatch):
    _configure_google(monkeypatch)

    async def body(db):
        await _connect(db)
        await server.google_connect(server.Response(), user=ADMIN)
        state = (await db.oauth_states.find_one({"tenant_id": TENANT}))["state"]
        await server.google_callback(SimpleNamespace(cookies={}, headers={}), state=state,
                                     code=None, error="access_denied")
        return await _status(db, "gmail"), await _status(db, "google_calendar")

    assert isolated(body) == ("active", "active")


def test_a_mailbox_held_by_a_struggling_workspace_is_still_refused(monkeypatch):
    _configure_google(monkeypatch)

    async def body(db):
        await _connect(db, OTHER, status="degraded", email="shared@example.com")
        await server.ensure_connections(TENANT)
        await db.oauth_states.insert_one({
            "state": "st_1", "tenant_id": TENANT, "actor": "admin@example.com",
            "code_verifier": "v", "binding_hash": server.hashlib.sha256(b"b").hexdigest(),
            "expires_at": ahead(minutes=5)})
        client = FakeClient(posts=[FakeResponse(200, {"access_token": "at",
                                                      "refresh_token": "rt",
                                                      "expires_in": 3600,
                                                      "scope": " ".join(server.GOOGLE_SCOPES)})],
                            gets=[FakeResponse(200, {"email": "shared@example.com"})])
        monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: client)
        response = await server.google_callback(
            SimpleNamespace(cookies={server.OAUTH_BINDING_COOKIE: "b"}, headers={}),
            state="st_1", code="code", error=None)
        return response.headers["location"], await _status(db)

    location, status = isolated(body)
    assert location.endswith("oauth=account_in_use")
    assert status != "active"


# ------------------------------------------------------------ disconnect

def test_disconnecting_calendar_does_not_revoke_the_grant_gmail_uses(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: client)

    async def body(db):
        await _connect(db)
        await server.disconnect_provider("google_calendar", user=ADMIN)
        revoked_after_calendar = [c for c in client.post_calls if "revoke" in c[0]]
        gmail = await _status(db, "gmail")
        creds_kept = await db.google_credentials.count_documents({"tenant_id": TENANT})
        await server.disconnect_provider("gmail", user=ADMIN)
        revoked_after_gmail = [c for c in client.post_calls if "revoke" in c[0]]
        creds_left = await db.google_credentials.count_documents({"tenant_id": TENANT})
        return revoked_after_calendar, gmail, creds_kept, revoked_after_gmail, creds_left

    after_calendar, gmail, kept, after_gmail, left = isolated(body)
    assert after_calendar == [] and gmail == "active" and kept == 1
    assert len(after_gmail) == 1 and left == 0


# ------------------------------------------------------------ alerts

def test_old_sync_failures_do_not_keep_alerting_a_healthy_connection():
    async def body(db):
        await _connect(db)
        await server.set_conn(TENANT, "gmail", last_success_at=ago(minutes=5),
                              consecutive_failures=0)
        await db.integration_sync_logs.insert_many([
            {"id": f"log_{n}", "tenant_id": TENANT, "provider": "gmail", "status": "failed",
             "started_at": ago(days=120 + n)} for n in range(5)])
        await server.evaluate_alerts(TENANT)
        return await db.alerts.count_documents({"tenant_id": TENANT,
                                                "type": "sync_failures"})

    assert isolated(body) == 0


def test_repeated_recent_failures_alert_and_a_success_clears_it(monkeypatch):
    _quiet(monkeypatch)
    outcomes = iter([RuntimeError("http_status:503")] * 3 * server.SYNC_FAIL_THRESHOLD)

    async def sync(tenant_id, actor):
        outcome = next(outcomes, None)
        if outcome:
            raise outcome
        return {"scanned": 0, "matched": 0}

    monkeypatch.setitem(server.SYNC_FUNCS, "gmail", sync)

    async def body(db):
        await _connect(db)
        for _ in range(server.SYNC_FAIL_THRESHOLD):
            await server.run_sync(TENANT, "gmail", "cron")
        await server.evaluate_alerts(TENANT)
        raised = await db.alerts.count_documents({"tenant_id": TENANT, "type": "sync_failures",
                                                  "status": "open"})
        await server.run_sync(TENANT, "gmail", "cron")
        await server.evaluate_alerts(TENANT)
        still_open = await db.alerts.count_documents({"tenant_id": TENANT,
                                                      "type": "sync_failures",
                                                      "status": "open"})
        return raised, still_open

    assert isolated(body) == (1, 0)


# ------------------------------------------------------------ what the sync reads

def test_mail_and_meetings_attach_to_the_companys_current_workspace():
    async def body(db):
        await db.workspaces.insert_many([
            {"id": "ws_old", "tenant_id": TENANT, "company_id": "co_1", "name": "Phase 1",
             "status": "archived", "created_at": ago(days=400)},
            {"id": "ws_mid", "tenant_id": TENANT, "company_id": "co_1", "name": "Phase 2",
             "status": "active", "created_at": ago(days=200)},
            {"id": "ws_new", "tenant_id": TENANT, "company_id": "co_1", "name": "Phase 3",
             "status": "active", "created_at": ago(days=10)}])
        return await server._workspace_for_company(TENANT, "co_1")

    assert isolated(body) == "ws_new"


def test_only_future_meetings_are_upcoming():
    async def body(db):
        await db.workspaces.insert_one({"id": "ws_m", "tenant_id": TENANT, "name": "Acme"})
        await db.crm_meetings.insert_many(
            [{"id": f"past_{n}", "tenant_id": TENANT, "workspace_id": "ws_m",
              "title": f"Past {n}", "start": ago(days=n + 1)} for n in range(5)]
            + [{"id": "cancelled", "tenant_id": TENANT, "workspace_id": "ws_m",
                "title": "Cancelled", "start": ahead(days=1), "status": "cancelled"},
               {"id": "next", "tenant_id": TENANT, "workspace_id": "ws_m",
                "title": "Next", "start": ahead(days=2)}])
        signals = await server.workspace_health_signals("ws_m", user=ADMIN)
        activity = await server.workspace_activity("ws_m", user=ADMIN)
        return ([s["detail"] for s in signals["signals"]
                 if s["signal"] == "Upcoming client meeting"],
                [m["title"] for m in activity["meetings"]])

    upcoming, listed = isolated(body)
    assert upcoming == ["Next"]
    assert listed[0] == "Next" and "Cancelled" not in listed


def test_gmail_sync_reads_past_the_first_page(monkeypatch):
    def page(ids, token=None):
        return FakeResponse(200, {"messages": [{"id": i} for i in ids],
                                  **({"nextPageToken": token} if token else {})})

    def message(i):
        return FakeResponse(200, {"id": i, "threadId": f"t{i}", "internalDate": "1700000000000",
                                  "payload": {"headers": [
                                      {"name": "From", "value": "client@acme.example"},
                                      {"name": "To", "value": "owner@example.com"},
                                      {"name": "Subject", "value": f"m{i}"}]}})

    first, second = [f"a{n}" for n in range(25)], [f"b{n}" for n in range(10)]

    class Routed(FakeClient):
        async def get(self, url, **kwargs):
            self.get_calls.append((url, deepcopy(kwargs)))
            if url == server.GMAIL_LIST_URL:
                token = (kwargs.get("params") or {}).get("pageToken")
                return page(second) if token == "p2" else page(first, "p2")
            return message(url.rsplit("/", 1)[-1])

    client = Routed()
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: client)

    async def body(db):
        await _connect(db)
        await db.contacts.insert_one({"id": "ct_1", "tenant_id": TENANT,
                                      "email": "client@acme.example", "name": "Client"})
        return await server.sync_gmail(TENANT, "cron")

    summary = isolated(body)
    assert summary["scanned"] == 35 and not summary.get("truncated")
