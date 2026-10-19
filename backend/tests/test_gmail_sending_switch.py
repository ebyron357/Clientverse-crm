"""The email sending switch.

Outbound email needs a connected Gmail *and* a Gmail catalogue record past configuration.
The switch is the only thing that moves that record, so these tests pin down what it
promises: sending turns on only after Gmail accepts a test message to the connected
mailbox itself, every change is recorded, and anything that invalidates the test --
disconnecting, or reconnecting without send permission or with another mailbox -- turns
sending off again. They also cover the disconnect fix that came with it: Gmail and
Calendar share one Google grant, which is revoked only with the last of the two, and
never through a URL.
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_sending_switch")
os.environ.setdefault("JWT_SECRET", "gmail-sending-switch-jwt-secret-long-enough")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

import conversations as cv
import gmail_provider
import recovery_strategy as rs
import server

TENANT = "ten_switch_a"
OWNER = {"tenant_id": TENANT, "email": "owner@acme.test", "role": "admin"}
MAILBOX = "owner@acme.test"

_LOOP = None


def loop():
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP


def run(coro):
    return loop().run_until_complete(coro)


class FakeGmail:
    channel = cv.CHANNEL_EMAIL
    name = "gmail"

    def __init__(self, error=None, during=None):
        self.error = error
        self.during = during  # runs while the test email is "in flight"
        self.calls = []

    async def send_test(self, *, tenant_id):
        self.calls.append(tenant_id)
        if self.during:
            await self.during()
        if self.error:
            raise self.error
        return {"provider_message_id": "gm_test_1", "mailbox": MAILBOX}


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return dict(self._payload)


class RecordingClient:
    """Stands in for httpx.AsyncClient and records every request."""

    def __init__(self, posts=(), gets=()):
        self.posts, self.gets, self.calls = list(posts), list(gets), []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.posts.pop(0) if self.posts else FakeResponse(200)

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.gets.pop(0)


@pytest.fixture()
def db(monkeypatch):
    name = f"cv_switch_{uuid.uuid4().hex[:10]}"
    loop()  # the client binds to the current loop, so it must exist first
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    database = client[name]
    monkeypatch.setattr(server, "db", database)
    previous = cv.REGISTRY.get(cv.CHANNEL_EMAIL)
    yield database
    if previous:
        cv.REGISTRY.register(previous)
    else:
        cv.REGISTRY.unregister(cv.CHANNEL_EMAIL)
    run(client.drop_database(name))
    client.close()


def seed(db, *, catalogue_status="REQUIRES_CONFIGURATION", gmail="active", calendar="active",
         scopes=(gmail_provider.GMAIL_READ_SCOPE, gmail_provider.GMAIL_SEND_SCOPE),
         certified_mailbox=None):
    run(db.integration_connections.insert_many([
        {"tenant_id": TENANT, "provider": "gmail", "status": gmail,
         "account_identity": MAILBOX, "scopes": list(scopes)},
        {"tenant_id": TENANT, "provider": "google_calendar", "status": calendar,
         "account_identity": MAILBOX, "scopes": list(scopes)},
    ]))
    if catalogue_status:
        run(db.integrations.insert_one({
            "id": "intg_gmail", "tenant_id": TENANT, "name": "Gmail", "provider": "Google",
            "status": catalogue_status,
            "certification": {"mailbox": certified_mailbox} if certified_mailbox else None}))
    run(db.google_credentials.insert_one({"tenant_id": TENANT, "enc": server.enc_secret(
        {"access_token": "live-access", "refresh_token": "live-refresh", "scopes": list(scopes)})}))


def email_channel(db):
    return run(rs.authorized_channels(db, TENANT))[rs.CHANNEL_EMAIL]


def events(db, event_type):
    return run(db.domain_events.find({"tenant_id": TENANT, "event_type": event_type}, {"_id": 0}).to_list(50))


# ----------------------------------------------------------------- turning it on

def test_sending_turns_on_only_after_gmail_accepts_a_test_message_to_itself(db):
    seed(db)
    fake = FakeGmail()
    cv.REGISTRY.register(fake)
    assert email_channel(db)["authorized"] is False

    state = run(server.enable_gmail_sending(user=OWNER))

    assert fake.calls == [TENANT]
    assert state["enabled"] is True and state["authorized"] is True
    assert state["mailbox"] == MAILBOX and state["test_message_id"] == "gm_test_1"
    assert state["enabled_by"] == OWNER["email"]
    record = run(db.integrations.find_one({"id": "intg_gmail"}))
    assert record["status"] == "CERTIFIED"
    assert record["certification"]["method"] == "test_message_to_self"
    [event] = events(db, "integration.sending_enabled")
    assert event["actor"] == OWNER["email"] and event["payload"]["test_message_id"] == "gm_test_1"


def test_a_refused_test_message_leaves_sending_off_and_records_nothing(db):
    seed(db)
    cv.REGISTRY.register(FakeGmail(error=gmail_provider.GmailNotAuthorized(
        "The Gmail connection for this tenant is read-only.")))

    with pytest.raises(HTTPException) as excinfo:
        run(server.enable_gmail_sending(user=OWNER))

    assert excinfo.value.status_code == 409
    assert "Sending stays off" in excinfo.value.detail and "read-only" in excinfo.value.detail
    assert run(db.integrations.find_one({"id": "intg_gmail"}))["status"] == "REQUIRES_CONFIGURATION"
    assert email_channel(db)["authorized"] is False
    assert events(db, "integration.sending_enabled") == []


def test_without_a_gmail_adapter_there_is_nothing_to_turn_on(db):
    seed(db)
    cv.REGISTRY.unregister(cv.CHANNEL_EMAIL)

    with pytest.raises(HTTPException) as excinfo:
        run(server.enable_gmail_sending(user=OWNER))

    assert excinfo.value.status_code == 409
    assert email_channel(db)["authorized"] is False


def test_a_tenant_without_a_catalogue_record_gets_one_when_sending_is_proven(db):
    seed(db, catalogue_status=None)
    cv.REGISTRY.register(FakeGmail())

    state = run(server.enable_gmail_sending(user=OWNER))

    assert state["enabled"] is True and state["authorized"] is True
    [record] = run(db.integrations.find({"tenant_id": TENANT}, {"_id": 0}).to_list(5))
    assert record["name"] == "Gmail" and record["status"] == "CERTIFIED"


def test_a_test_overtaken_by_turning_sending_off_does_not_turn_it_on(db):
    seed(db)

    async def admin_turns_it_off():
        await server.disable_gmail_sending(user=OWNER)

    cv.REGISTRY.register(FakeGmail(during=admin_turns_it_off))
    with pytest.raises(HTTPException) as excinfo:
        run(server.enable_gmail_sending(user=OWNER))

    assert excinfo.value.status_code == 409 and "changed" in excinfo.value.detail
    assert run(db.integrations.find_one({"id": "intg_gmail"}))["status"] == "REQUIRES_CONFIGURATION"
    assert email_channel(db)["authorized"] is False


def test_a_test_overtaken_by_a_reconnect_to_another_mailbox_does_not_count(db):
    seed(db)

    async def google_reconnects_as_someone_else():
        await db.integration_connections.update_one(
            {"tenant_id": TENANT, "provider": "gmail"},
            {"$set": {"account_identity": "someone.else@acme.test"}})

    cv.REGISTRY.register(FakeGmail(during=google_reconnects_as_someone_else))
    with pytest.raises(HTTPException) as excinfo:
        run(server.enable_gmail_sending(user=OWNER))

    assert excinfo.value.status_code == 409
    assert email_channel(db)["authorized"] is False
    assert events(db, "integration.sending_enabled") == []


# ---------------------------------------------------------------- turning it off

def test_an_admin_can_turn_sending_off_and_the_change_is_recorded(db):
    seed(db, catalogue_status="CERTIFIED", certified_mailbox=MAILBOX)
    assert email_channel(db)["authorized"] is True

    state = run(server.disable_gmail_sending(user=OWNER))

    assert state["enabled"] is False and state["authorized"] is False
    record = run(db.integrations.find_one({"id": "intg_gmail"}))
    assert record["status"] == "REQUIRES_CONFIGURATION" and record["certification"] is None
    [event] = events(db, "integration.sending_disabled")
    assert event["payload"]["reason"] == "Turned off by an admin"


def test_turning_off_clears_every_certified_gmail_record_not_just_the_first(db):
    seed(db, catalogue_status="CERTIFIED", certified_mailbox=MAILBOX)
    run(db.integrations.insert_one({"id": "intg_gmail_dup", "tenant_id": TENANT, "name": "gmail",
                                    "status": "CERTIFIED", "certification": {"mailbox": MAILBOX}}))

    state = run(server.disable_gmail_sending(user=OWNER))

    assert state["enabled"] is False and email_channel(db)["authorized"] is False
    statuses = {r["status"] for r in run(db.integrations.find({"tenant_id": TENANT}).to_list(5))}
    assert statuses == {"REQUIRES_CONFIGURATION"}


def test_turning_off_sending_that_is_already_off_records_nothing(db):
    seed(db)
    run(server.disable_gmail_sending(user=OWNER))
    assert events(db, "integration.sending_disabled") == []


# -------------------------------------------------------------------- disconnect

def test_disconnecting_calendar_leaves_the_shared_grant_and_gmail_sending_alone(db, monkeypatch):
    seed(db, catalogue_status="CERTIFIED", certified_mailbox=MAILBOX)
    client = RecordingClient()
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kwargs: client)

    run(server.disconnect_provider("google_calendar", user=OWNER))

    assert client.calls == []  # nothing revoked at Google
    assert run(db.google_credentials.find_one({"tenant_id": TENANT})) is not None
    assert email_channel(db)["authorized"] is True


@pytest.mark.parametrize("gmail_state", ["connecting", "degraded"])
def test_disconnecting_calendar_keeps_the_grant_while_gmail_is_syncing_or_degraded(db, monkeypatch, gmail_state):
    seed(db, gmail=gmail_state)
    client = RecordingClient()
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kwargs: client)

    run(server.disconnect_provider("google_calendar", user=OWNER))

    assert client.calls == []
    assert run(db.google_credentials.find_one({"tenant_id": TENANT})) is not None


def test_disconnecting_both_rows_at_once_still_revokes_the_grant(db, monkeypatch):
    seed(db)
    client = RecordingClient()
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kwargs: client)

    async def both():
        await asyncio.gather(server.disconnect_provider("gmail", user=OWNER),
                             server.disconnect_provider("google_calendar", user=OWNER))

    run(both())

    assert any(url == "https://oauth2.googleapis.com/revoke" for _, url, _ in client.calls)
    assert run(db.google_credentials.find_one({"tenant_id": TENANT})) is None


def test_disconnecting_gmail_turns_sending_off_but_keeps_calendar_working(db, monkeypatch):
    seed(db, catalogue_status="CERTIFIED", certified_mailbox=MAILBOX)
    client = RecordingClient()
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kwargs: client)

    run(server.disconnect_provider("gmail", user=OWNER))

    assert client.calls == []
    assert run(db.google_credentials.find_one({"tenant_id": TENANT})) is not None
    assert run(db.integrations.find_one({"id": "intg_gmail"}))["status"] == "REQUIRES_CONFIGURATION"
    [event] = events(db, "integration.sending_disabled")
    assert event["payload"]["reason"] == "Gmail was disconnected"


def test_the_last_google_disconnect_revokes_the_grant_with_the_token_in_the_body(db, monkeypatch):
    seed(db, calendar="disconnected")
    client = RecordingClient()
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kwargs: client)

    run(server.disconnect_provider("gmail", user=OWNER))

    [(method, url, kwargs)] = client.calls
    assert (method, url) == ("POST", "https://oauth2.googleapis.com/revoke")
    assert kwargs["data"] == {"token": "live-refresh"}
    assert "params" not in kwargs and "live-refresh" not in url
    assert run(db.google_credentials.find_one({"tenant_id": TENANT})) is None


# --------------------------------------------------------------------- reconnect

def reconnect(db, monkeypatch, *, scope, mailbox):
    run(db.oauth_states.insert_one({
        "state": "state_r", "tenant_id": TENANT, "actor": OWNER["email"],
        "code_verifier": "verifier", "expires_at": "2099-01-01T00:00:00+00:00"}))
    client = RecordingClient(
        posts=[FakeResponse(200, {"access_token": "new-access", "expires_in": 3600, "scope": scope})],
        gets=[FakeResponse(200, {"email": mailbox})])
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kwargs: client)
    response = run(server.google_callback(state="state_r", code="code_r", error=None))
    assert response.headers["location"].endswith("oauth=connected")


FULL_GRANT = f"openid {gmail_provider.GMAIL_READ_SCOPE} {gmail_provider.GMAIL_SEND_SCOPE}"


def test_reconnecting_the_same_mailbox_with_send_permission_keeps_sending_on(db, monkeypatch):
    seed(db, catalogue_status="CERTIFIED", certified_mailbox=MAILBOX)
    reconnect(db, monkeypatch, scope=FULL_GRANT, mailbox=MAILBOX)
    assert email_channel(db)["authorized"] is True
    assert events(db, "integration.sending_disabled") == []


def test_reconnecting_without_send_permission_turns_sending_off(db, monkeypatch):
    seed(db, catalogue_status="CERTIFIED", certified_mailbox=MAILBOX)
    reconnect(db, monkeypatch, scope=f"openid {gmail_provider.GMAIL_READ_SCOPE}", mailbox=MAILBOX)
    assert email_channel(db)["authorized"] is False
    [event] = events(db, "integration.sending_disabled")
    assert "without permission to send" in event["payload"]["reason"]


def test_reconnecting_a_different_mailbox_turns_sending_off(db, monkeypatch):
    seed(db, catalogue_status="CERTIFIED", certified_mailbox=MAILBOX)
    reconnect(db, monkeypatch, scope=FULL_GRANT, mailbox="someone.else@acme.test")
    assert email_channel(db)["authorized"] is False
    [event] = events(db, "integration.sending_disabled")
    assert "different mailbox" in event["payload"]["reason"]
