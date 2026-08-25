"""Deterministic provider lifecycle tests that require no live credentials or network.

Credential-backed production certification remains a separate manual gate. These tests
cover the adapter behavior that must remain reliable in CI: OAuth construction, refresh,
re-auth failure state, retries, idempotent upserts, disconnect behavior, and redaction.
"""

import asyncio
import os
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_provider_unit")
os.environ.setdefault("JWT_SECRET", "provider-unit-jwt-secret-that-is-long-enough")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

import server  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return deepcopy(self._payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http_status:{self.status_code}")


class FakeAsyncClient:
    def __init__(self, get_responses=None, post_responses=None):
        self.get_responses = list(get_responses or [])
        self.post_responses = list(post_responses or [])
        self.get_calls = []
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, **kwargs):
        self.get_calls.append((url, deepcopy(kwargs)))
        return self.get_responses.pop(0)

    async def post(self, url, **kwargs):
        self.post_calls.append((url, deepcopy(kwargs)))
        return self.post_responses.pop(0)


class FakeRequest:
    def __init__(self, body, headers=None):
        self._body = body
        self.headers = headers or {}

    async def body(self):
        return self._body


class CaptureCollection:
    def __init__(self, find_one_results=None):
        self.find_one_results = list(find_one_results or [])
        self.inserted = []
        self.updated = []
        self.deleted = []

    async def find_one(self, *args, **kwargs):
        if self.find_one_results:
            return deepcopy(self.find_one_results.pop(0))
        return None

    async def insert_one(self, document):
        self.inserted.append(deepcopy(document))
        return SimpleNamespace(inserted_id="fake")

    async def update_one(self, query, update, **kwargs):
        self.updated.append((deepcopy(query), deepcopy(update), deepcopy(kwargs)))
        return SimpleNamespace(
            matched_count=1,
            modified_count=1,
            upserted_id="fake-upsert" if kwargs.get("upsert") else None,
        )

    async def delete_one(self, query):
        self.deleted.append(deepcopy(query))
        return SimpleNamespace(deleted_count=1)


def run(coro):
    return asyncio.run(coro)


def test_google_connect_builds_pkce_readonly_authorization(monkeypatch):
    oauth_states = CaptureCollection()
    monkeypatch.setattr(server, "db", SimpleNamespace(oauth_states=oauth_states))
    statuses = []

    async def fake_set_conn(tenant_id, provider, **fields):
        statuses.append((tenant_id, provider, fields))

    monkeypatch.setattr(server, "ensure_connections", lambda tenant_id: asyncio.sleep(0))
    monkeypatch.setattr(server, "set_conn", fake_set_conn)
    monkeypatch.setattr(server, "GOOGLE_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setattr(server, "GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(server, "GOOGLE_REDIRECT_URI", "https://crm.example/api/integrations/google/callback")

    result = run(server.google_connect(user={"tenant_id": "ten_a", "email": "admin@example.com"}))
    parsed = urlparse(result["authorization_url"])
    query = parse_qs(parsed.query)

    assert parsed.netloc == "accounts.google.com"
    assert query["redirect_uri"] == ["https://crm.example/api/integrations/google/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert "gmail.readonly" in query["scope"][0]
    assert "calendar.readonly" in query["scope"][0]
    assert "client_secret" not in query
    assert oauth_states.inserted[0]["tenant_id"] == "ten_a"
    assert oauth_states.inserted[0]["state"] == query["state"][0]
    assert oauth_states.inserted[0]["code_verifier"]
    assert {(provider, fields["status"]) for _, provider, fields in statuses} == {
        ("gmail", "connecting"),
        ("google_calendar", "connecting"),
    }


def test_google_refresh_preserves_refresh_token_and_updates_scopes(monkeypatch):
    credential_store = CaptureCollection()
    fake_db = SimpleNamespace(google_credentials=credential_store)
    monkeypatch.setattr(server, "db", fake_db)
    monkeypatch.setattr(server, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(server, "GOOGLE_CLIENT_SECRET", "client-secret")

    async def fake_google_creds(tenant_id):
        assert tenant_id == "ten_a"
        return ({
            "access_token": "expired-access",
            "refresh_token": "preserved-refresh",
            "expires_at": 0,
            "scopes": ["old-scope"],
        }, {"credential_version": 1})

    monkeypatch.setattr(server, "_google_creds", fake_google_creds)
    monkeypatch.setattr(server, "enc_secret", lambda value: deepcopy(value))
    client = FakeAsyncClient(post_responses=[FakeResponse(200, {
        "access_token": "new-access",
        "expires_in": 3600,
        "scope": "scope-a scope-b",
    })])
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kwargs: client)

    token = run(server._google_access_token("ten_a", force_refresh=True))

    assert token == "new-access"
    persisted = credential_store.updated[0][1]["$set"]["enc"]
    assert persisted["refresh_token"] == "preserved-refresh"
    assert persisted["scopes"] == ["scope-a", "scope-b"]
    assert client.post_calls[0][1]["data"]["refresh_token"] == "preserved-refresh"


def test_google_refresh_without_refresh_token_requires_reauth(monkeypatch):
    async def fake_google_creds(_tenant_id):
        return ({"access_token": "expired", "expires_at": 0}, {})

    monkeypatch.setattr(server, "_google_creds", fake_google_creds)

    try:
        run(server._google_access_token("ten_a", force_refresh=True))
        raise AssertionError("expected token refresh failure")
    except RuntimeError as exc:
        assert str(exc) == "token_refresh_failed:missing_refresh_token"


def test_gmail_401_forces_refresh_then_syncs_with_new_token(monkeypatch):
    token_calls = []

    async def fake_access_token(_tenant_id, force_refresh=False):
        token_calls.append(force_refresh)
        return "new-access" if force_refresh else "old-access"

    async def fake_contacts(_tenant_id):
        return {"alice@example.com": {"id": "ct_1", "company_id": "co_1"}}

    upserts = []

    async def fake_upsert(tenant_id, record, contacts, provider):
        upserts.append((tenant_id, record, contacts, provider))
        return True

    client = FakeAsyncClient(get_responses=[
        FakeResponse(401),
        FakeResponse(200, {"messages": [{"id": "m1"}]}),
        FakeResponse(200, {
            "id": "m1",
            "threadId": "t1",
            "snippet": "hello",
            "payload": {"headers": [
                {"name": "From", "value": "Alice <alice@example.com>"},
                {"name": "Subject", "value": "Kickoff"},
            ]},
        }),
    ])
    monkeypatch.setattr(server, "_google_access_token", fake_access_token)
    monkeypatch.setattr(server, "_contacts_by_email", fake_contacts)
    monkeypatch.setattr(server, "_upsert_comm", fake_upsert)
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kwargs: client)

    result = run(server.sync_gmail("ten_a", "admin@example.com"))

    assert result == {"scanned": 1, "matched": 1}
    assert token_calls == [False, True]
    assert client.get_calls[0][1]["headers"]["Authorization"] == "Bearer old-access"
    assert client.get_calls[1][1]["headers"]["Authorization"] == "Bearer new-access"
    assert upserts[0][3] == "gmail"


def test_calendar_duplicate_events_use_same_tenant_scoped_upsert_key(monkeypatch):
    async def fake_access_token(_tenant_id, force_refresh=False):
        return "calendar-access"

    async def fake_contacts(_tenant_id):
        return {"client@example.com": {"id": "ct_1", "company_id": "co_1"}}

    async def fake_workspace(_tenant_id, _company_id):
        return "ws_1"

    meetings = CaptureCollection()
    monkeypatch.setattr(server, "db", SimpleNamespace(crm_meetings=meetings))
    monkeypatch.setattr(server, "_google_access_token", fake_access_token)
    monkeypatch.setattr(server, "_contacts_by_email", fake_contacts)
    monkeypatch.setattr(server, "_workspace_for_company", fake_workspace)
    event = {
        "id": "event_1",
        "summary": "Client review",
        "start": {"dateTime": "2026-09-01T10:00:00Z"},
        "end": {"dateTime": "2026-09-01T11:00:00Z"},
        "attendees": [{"email": "client@example.com"}],
        "status": "confirmed",
    }
    client = FakeAsyncClient(get_responses=[FakeResponse(200, {"items": [event, event]})])
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kwargs: client)

    result = run(server.sync_calendar("ten_a", "admin@example.com"))

    assert result == {"scanned": 2, "matched": 2}
    assert len(meetings.updated) == 2
    first_key = meetings.updated[0][0]
    second_key = meetings.updated[1][0]
    assert first_key == second_key == {"tenant_id": "ten_a", "external_id": "event_1"}
    assert all(call[2]["upsert"] is True for call in meetings.updated)


def test_run_sync_retries_rate_limit_then_completes(monkeypatch):
    connections = CaptureCollection(find_one_results=[{"status": "active"}])
    logs = CaptureCollection()
    monkeypatch.setattr(server, "db", SimpleNamespace(
        integration_connections=connections,
        integration_sync_logs=logs,
    ))
    state_updates = []
    events = []

    async def fake_set_conn(tenant_id, provider, **fields):
        state_updates.append((tenant_id, provider, fields))

    async def fake_record_event(*args, **kwargs):
        events.append((args, kwargs))

    async def no_sleep(_seconds):
        return None

    attempts = {"count": 0}

    async def flaky_sync(_tenant_id, _actor):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("rate_limited")
        return {"scanned": 2, "matched": 1}

    monkeypatch.setattr(server, "set_conn", fake_set_conn)
    monkeypatch.setattr(server, "record_event", fake_record_event)
    monkeypatch.setattr(server.asyncio, "sleep", no_sleep)
    monkeypatch.setitem(server.SYNC_FUNCS, "gmail", flaky_sync)

    result = run(server.run_sync("ten_a", "gmail", "admin@example.com"))

    assert result == {"scanned": 2, "matched": 1, "status": "completed"}
    assert attempts["count"] == 2
    assert logs.inserted[0]["attempts"] == 2
    assert logs.inserted[0]["status"] == "completed"
    assert state_updates[-1][2]["status"] == "active"
    assert events[-1][0][0] == "integration.sync_completed"


def test_run_sync_token_failure_stops_retry_and_marks_expired(monkeypatch):
    connections = CaptureCollection(find_one_results=[{"status": "active"}])
    logs = CaptureCollection()
    monkeypatch.setattr(server, "db", SimpleNamespace(
        integration_connections=connections,
        integration_sync_logs=logs,
    ))
    state_updates = []

    async def fake_set_conn(tenant_id, provider, **fields):
        state_updates.append((tenant_id, provider, fields))

    async def fake_record_event(*args, **kwargs):
        return None

    attempts = {"count": 0}

    async def revoked_sync(_tenant_id, _actor):
        attempts["count"] += 1
        raise RuntimeError("token_refresh_failed:401")

    monkeypatch.setattr(server, "set_conn", fake_set_conn)
    monkeypatch.setattr(server, "record_event", fake_record_event)
    monkeypatch.setitem(server.SYNC_FUNCS, "gmail", revoked_sync)

    result = run(server.run_sync("ten_a", "gmail", "admin@example.com"))

    assert result == {"status": "failed", "error": "token_refresh_failed:401"}
    assert attempts["count"] == 1
    assert logs.inserted[0]["attempts"] == 1
    assert state_updates[-1][2]["status"] == "expired"


def test_google_callback_reconnect_preserves_existing_refresh_token(monkeypatch):
    oauth_states = CaptureCollection(find_one_results=[{
        "state": "state_1",
        "tenant_id": "ten_a",
        "actor": "admin@example.com",
        "code_verifier": "verifier",
        "expires_at": "2099-01-01T00:00:00+00:00",
    }])
    credentials = CaptureCollection(find_one_results=[{
        "enc": "encrypted-old-creds",
        "credential_version": 2,
    }])
    monkeypatch.setattr(server, "db", SimpleNamespace(
        oauth_states=oauth_states,
        google_credentials=credentials,
    ))
    monkeypatch.setattr(server, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(server, "GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(server, "GOOGLE_REDIRECT_URI", "https://crm.example/api/integrations/google/callback")
    monkeypatch.setattr(server, "FRONTEND_URL", "https://crm.example")
    monkeypatch.setattr(server, "dec_secret", lambda _value: {"refresh_token": "existing-refresh"})
    monkeypatch.setattr(server, "enc_secret", lambda value: deepcopy(value))

    async def fake_set_conn(*args, **kwargs):
        return None

    async def fake_record_event(*args, **kwargs):
        return None

    monkeypatch.setattr(server, "set_conn", fake_set_conn)
    monkeypatch.setattr(server, "record_event", fake_record_event)
    client = FakeAsyncClient(
        post_responses=[FakeResponse(200, {
            "access_token": "new-access",
            "expires_in": 3600,
            "scope": "scope-a scope-b",
        })],
        get_responses=[FakeResponse(200, {"email": "owner@example.com"})],
    )
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kwargs: client)

    response = run(server.google_callback(state="state_1", code="code_1", error=None))

    assert response.status_code == 307
    assert response.headers["location"].endswith("oauth=connected")
    persisted = credentials.updated[0][1]["$set"]
    assert persisted["credential_version"] == 3
    assert persisted["enc"]["refresh_token"] == "existing-refresh"
    assert oauth_states.deleted == [{"state": "state_1"}]


def test_google_disconnect_keeps_shared_credentials_until_both_providers_inactive(monkeypatch):
    credentials = CaptureCollection(find_one_results=[
        {"enc": "encrypted-creds"},
        {"enc": "encrypted-creds"},
    ])
    other_connections = CaptureCollection(find_one_results=[
        {"status": "active"},
        None,
    ])
    monkeypatch.setattr(server, "db", SimpleNamespace(
        google_credentials=credentials,
        integration_connections=other_connections,
    ))
    monkeypatch.setattr(server, "dec_secret", lambda _value: {
        "refresh_token": "fake-refresh-token",
        "access_token": "fake-access-token",
    })

    async def fake_set_conn(*args, **kwargs):
        return None

    async def fake_record_event(*args, **kwargs):
        return None

    monkeypatch.setattr(server, "set_conn", fake_set_conn)
    monkeypatch.setattr(server, "record_event", fake_record_event)
    revoke_client = FakeAsyncClient(post_responses=[FakeResponse(200), FakeResponse(200)])
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kwargs: revoke_client)
    user = {"tenant_id": "ten_a", "email": "admin@example.com"}

    assert run(server.disconnect_provider("gmail", user=user)) == {"ok": True}
    assert credentials.deleted == []
    assert run(server.disconnect_provider("google_calendar", user=user)) == {"ok": True}
    assert credentials.deleted == [{"tenant_id": "ten_a"}]


def test_stripe_payment_intent_success_is_test_only_tenant_scoped_and_idempotent(monkeypatch):
    invoices = CaptureCollection(find_one_results=[
        {"id": "inv_1", "tenant_id": "ten_a", "workspace_id": "ws_1", "total": 125.50,
         "currency": "USD", "status": "issued"},
        {"id": "inv_1", "tenant_id": "ten_a", "workspace_id": "ws_1", "total": 125.50,
         "currency": "USD", "status": "issued"},
    ])
    monkeypatch.setattr(server, "db", SimpleNamespace(invoices=invoices))
    monkeypatch.setenv("STRIPE_API_KEY", "rk_test_x")
    calls = []

    def fake_create(**kwargs):
        calls.append(deepcopy(kwargs))
        return {"id": "pi_test_1", "status": "succeeded"}

    events = []

    async def fake_record_event(*args, **kwargs):
        events.append((args, kwargs))

    monkeypatch.setattr(server._stripe.PaymentIntent, "create", fake_create)
    monkeypatch.setattr(server, "record_event", fake_record_event)
    user = {"tenant_id": "ten_a", "email": "admin@example.com"}
    inp = server.StripePaymentIntentInput(payment_method_id="pm_card_visa")

    first = run(server.create_stripe_payment_intent("inv_1", inp, user=user))
    second = run(server.create_stripe_payment_intent("inv_1", inp, user=user))

    assert first == second == {
        "ok": True,
        "payment_intent_id": "pi_test_1",
        "payment_status": "succeeded",
        "invoice_status": "paid",
    }
    assert len(calls) == 2
    assert calls[0]["amount"] == 12550
    assert calls[0]["currency"] == "usd"
    assert calls[0]["payment_method"] == "pm_card_visa"
    assert calls[0]["metadata"] == {
        "clientverse_tenant_id": "ten_a",
        "clientverse_invoice_id": "inv_1",
    }
    assert calls[0]["idempotency_key"] == calls[1]["idempotency_key"]
    assert all(update[0] == {"id": "inv_1", "tenant_id": "ten_a"} for update in invoices.updated)
    assert events[-1][0][0] == "invoice.payment_intent_created"


def test_stripe_payment_intent_rejects_live_key(monkeypatch):
    monkeypatch.setenv("STRIPE_API_KEY", "sk_live_x")

    try:
        run(server.create_stripe_payment_intent(
            "inv_1", server.StripePaymentIntentInput(),
            user={"tenant_id": "ten_a", "email": "admin@example.com"},
        ))
        raise AssertionError("expected live-mode rejection")
    except server.HTTPException as exc:
        assert exc.status_code == 400
        assert "test-mode" in exc.detail


def test_stripe_payment_failure_is_sanitized_and_recorded(monkeypatch):
    invoices = CaptureCollection(find_one_results=[{
        "id": "inv_1", "tenant_id": "ten_a", "workspace_id": "ws_1", "total": 50,
        "currency": "usd", "status": "issued",
    }])
    monkeypatch.setattr(server, "db", SimpleNamespace(invoices=invoices))
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_x")

    class FakeStripeFailure(Exception):
        code = "card_declined"

    def fake_create(**_kwargs):
        raise FakeStripeFailure("raw provider detail must not reach the API")

    events = []

    async def fake_record_event(*args, **kwargs):
        events.append((args, kwargs))

    monkeypatch.setattr(server._stripe.PaymentIntent, "create", fake_create)
    monkeypatch.setattr(server, "record_event", fake_record_event)

    try:
        run(server.create_stripe_payment_intent(
            "inv_1", server.StripePaymentIntentInput(payment_method_id="pm_card_visa_chargeDeclined"),
            user={"tenant_id": "ten_a", "email": "admin@example.com"},
        ))
        raise AssertionError("expected payment failure")
    except server.HTTPException as exc:
        assert exc.status_code == 402
        assert exc.detail == "Stripe test payment failed"

    update = invoices.updated[0]
    assert update[0] == {"id": "inv_1", "tenant_id": "ten_a"}
    assert update[1]["$set"]["payment_status"] == "failed"
    assert update[1]["$set"]["payment_error"] == "card_declined"
    assert "raw provider detail" not in str(update)
    assert events[0][1]["payload"] == {"error": "card_declined"}


def test_stripe_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_fake")

    def invalid_event(*_args, **_kwargs):
        raise ValueError("bad signature")

    monkeypatch.setattr(server._stripe.Webhook, "construct_event", invalid_event)
    request = FakeRequest(b"{}", {"Stripe-Signature": "t=1,v1=bad"})

    try:
        run(server.stripe_webhook(request))
        raise AssertionError("expected signature rejection")
    except server.HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "Invalid Stripe signature"


def test_stripe_webhook_is_idempotent_and_tenant_scoped(monkeypatch):
    class WebhookEvents(CaptureCollection):
        async def update_one(self, query, update, **kwargs):
            self.updated.append((deepcopy(query), deepcopy(update), deepcopy(kwargs)))
            if len(self.updated) == 1:
                return SimpleNamespace(matched_count=0, modified_count=0, upserted_id="inserted")
            return SimpleNamespace(matched_count=1, modified_count=0, upserted_id=None)

    webhook_events = WebhookEvents()
    invoices = CaptureCollection()
    monkeypatch.setattr(server, "db", SimpleNamespace(
        stripe_webhook_events=webhook_events,
        invoices=invoices,
    ))
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_fake")
    event = {
        "id": "evt_test_1",
        "type": "payment_intent.succeeded",
        "data": {"object": {
            "id": "pi_test_1",
            "metadata": {
                "clientverse_tenant_id": "ten_a",
                "clientverse_invoice_id": "inv_1",
            },
        }},
    }
    monkeypatch.setattr(server._stripe.Webhook, "construct_event", lambda *_args, **_kwargs: deepcopy(event))
    recorded = []

    async def fake_record_event(*args, **kwargs):
        recorded.append((args, kwargs))

    monkeypatch.setattr(server, "record_event", fake_record_event)
    request = FakeRequest(b"signed-payload", {"Stripe-Signature": "t=1,v1=valid"})

    first = run(server.stripe_webhook(request))
    second = run(server.stripe_webhook(request))

    assert first == {
        "received": True,
        "duplicate": False,
        "handled": True,
        "event_type": "payment_intent.succeeded",
    }
    assert second == {
        "received": True,
        "duplicate": True,
        "event_type": "payment_intent.succeeded",
    }
    assert len(invoices.updated) == 1
    assert invoices.updated[0][0] == {"id": "inv_1", "tenant_id": "ten_a"}
    assert invoices.updated[0][1]["$set"]["payment_status"] == "paid"
    assert recorded[0][0][0] == "invoice.succeeded"
    assert webhook_events.updated[0][0] == {"event_id": "evt_test_1"}


def test_public_connection_redacts_all_credential_material():
    public = server._public_conn({
        "id": "conn_1",
        "tenant_id": "ten_a",
        "provider": "gmail",
        "status": "active",
        "enc": "encrypted",
        "oauth_state": "state",
        "code_verifier": "verifier",
        "access_token": "unexpected-raw-token",
        "refresh_token": "unexpected-refresh-token",
    })

    assert "enc" not in public
    assert "oauth_state" not in public
    assert "code_verifier" not in public
    assert "access_token" not in public
    assert "refresh_token" not in public
    assert {"enc", "access_token", "refresh_token", "client_secret", "api_key", "webhook_secret"}.issubset(
        server.SAFE_CONN_FIELDS
    )
