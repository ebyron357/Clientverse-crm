"""The outbound email adapter.

What matters here is not that Gmail accepts a message -- it is what this adapter does
with every answer Gmail can give, because the expensive failures are the ambiguous
ones. A timeout that gets recorded as `failed` becomes a retry, and a retry becomes a
second copy in a client's inbox. So the cases with the most coverage are the ones where
nobody knows what happened.
"""

import asyncio
import base64
import os
import sys
import uuid
from email import message_from_bytes
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_gmail_unit")
os.environ.setdefault("JWT_SECRET", "gmail-provider-unit-jwt-secret-long-enough-12")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

import conversations as cv
import gmail_provider

TENANT = "ten_gmail_a"
ACTIVE_CONNECTION = {
    "status": "active",
    "account_identity": "sales@acme.test",
    "scopes": [gmail_provider.GMAIL_READ_SCOPE, gmail_provider.GMAIL_SEND_SCOPE],
}


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


class FakeClient:
    """Records every call so a test can assert on what did (and did not) reach Gmail."""

    def __init__(self, get_responses, post_responses, log):
        self._get = list(get_responses)
        self._post = list(post_responses)
        self.log = log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, headers=None):
        self.log.append(("GET", url, params))
        result = self._get.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def post(self, url, json=None, headers=None):
        self.log.append(("POST", url, json))
        result = self._post.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def make_provider(*, connection=ACTIVE_CONNECTION, token="tok",
                  get_responses=(), post_responses=()):
    log = []

    async def access_token(tenant_id, force_refresh=False):
        if isinstance(token, Exception):
            raise token
        return token

    async def get_connection(tenant_id):
        return connection

    provider = gmail_provider.GmailChannelProvider(
        access_token=access_token, connection=get_connection,
        http_client=lambda: FakeClient(get_responses, post_responses, log))
    return provider, log


def make_message(**overrides):
    return {"id": f"msg_{uuid.uuid4().hex[:8]}", "tenant_id": TENANT,
            "conversation_id": "conv_1", "channel": cv.CHANNEL_EMAIL,
            "body": "Hello, following up on your quote.", "subject": "Your quote",
            "to_address": "buyer@client.test", "history": [], **overrides}


def make_conversation(**overrides):
    return {"id": "conv_1", "tenant_id": TENANT, "channel": cv.CHANNEL_EMAIL,
            "subject": "Your quote",
            "participants": [{"kind": cv.PARTICIPANT_CONTACT, "contact_id": "ct_1",
                              "address": "buyer@client.test"}], **overrides}


# ------------------------------------------------------------------- authorisation

def test_a_tenant_without_a_gmail_connection_is_refused_and_nothing_is_dispatched():
    provider, log = make_provider(connection=None)
    with pytest.raises(cv.DeliveryRejected) as excinfo:
        run(provider.send(message=make_message(), conversation=make_conversation(),
                          idempotency_key="k1"))
    assert "not connected" in str(excinfo.value)
    assert log == [], "nothing may reach the provider before authorisation is established"


def test_a_read_only_gmail_connection_cannot_send():
    provider, log = make_provider(connection={**ACTIVE_CONNECTION,
                                              "scopes": [gmail_provider.GMAIL_READ_SCOPE]})
    with pytest.raises(cv.DeliveryRejected) as excinfo:
        run(provider.send(message=make_message(), conversation=make_conversation(),
                          idempotency_key="k1"))
    assert gmail_provider.GMAIL_SEND_SCOPE in str(excinfo.value)
    assert log == []


def test_a_degraded_connection_is_not_a_foundation_for_sending():
    provider, _ = make_provider(connection={**ACTIVE_CONNECTION, "status": "degraded"})
    with pytest.raises(cv.DeliveryRejected):
        run(provider.send(message=make_message(), conversation=make_conversation(),
                          idempotency_key="k1"))


def test_a_refresh_failure_is_a_proven_non_dispatch_not_an_unknown_outcome():
    provider, log = make_provider(token=RuntimeError("token_refresh_failed:400"))
    with pytest.raises(cv.DeliveryRejected):
        run(provider.send(message=make_message(), conversation=make_conversation(),
                          idempotency_key="k1"))
    assert log == []


def test_a_conversation_with_no_address_is_refused():
    provider, _ = make_provider(get_responses=[FakeResponse(200, {"messages": []})])
    message = make_message(to_address=None)
    conversation = make_conversation(participants=[{"kind": cv.PARTICIPANT_USER}])
    with pytest.raises(cv.DeliveryRejected) as excinfo:
        run(provider.send(message=message, conversation=conversation, idempotency_key="k"))
    assert "no email address" in str(excinfo.value)


# -------------------------------------------------------------------------- sending

def test_a_successful_send_returns_the_provider_id_and_the_id_it_sent_under():
    provider, log = make_provider(
        get_responses=[FakeResponse(200, {"messages": []})],
        post_responses=[FakeResponse(200, {"id": "gmail-123", "threadId": "thr-9"})])
    result = run(provider.send(message=make_message(), conversation=make_conversation(),
                               idempotency_key="k1"))
    assert result.provider_message_id == "gmail-123"
    assert result.detail["deduplicated"] is False
    assert result.detail["rfc822_message_id"].startswith("cv-")
    assert result.detail["thread_id"] == "thr-9"
    assert [entry[0] for entry in log] == ["GET", "POST"], (
        "the duplicate check must happen before the send, not after")


def test_the_message_that_goes_out_is_the_approved_text_verbatim():
    provider, log = make_provider(
        get_responses=[FakeResponse(200, {"messages": []})],
        post_responses=[FakeResponse(200, {"id": "gmail-123"})])
    body = "Hi Sam,\n\nYour quote from March is still open. Shall we proceed?\n"
    run(provider.send(message=make_message(body=body), conversation=make_conversation(),
                      idempotency_key="k1"))
    raw = log[1][2]["raw"]
    mail = message_from_bytes(base64.urlsafe_b64decode(raw))
    assert mail.get_payload(decode=True).decode() == body, (
        "the text a human approved is the text that is sent; nothing is appended")
    assert mail["To"] == "buyer@client.test"
    assert mail["From"] == "sales@acme.test"
    assert mail["Message-ID"].strip("<>").startswith("cv-")


def test_the_internal_thread_key_is_never_sent_to_gmail_as_a_thread_id():
    """`external_thread_id` is this system's own key and is often synthetic.

    A recovery case's thread key looks like `recovery_case:rc_abc:email`. Handing that
    to Gmail as a threadId would be rejected outright, so the adapter reads only the
    provider's own thread id.
    """
    provider, log = make_provider(
        get_responses=[FakeResponse(200, {"messages": []})],
        post_responses=[FakeResponse(200, {"id": "gmail-123"})])
    conversation = make_conversation(external_thread_id="recovery_case:rc_abc:email")
    run(provider.send(message=make_message(), conversation=conversation,
                      idempotency_key="k1"))
    assert "threadId" not in log[1][2]


def test_a_reply_threads_onto_the_message_it_answers():
    provider, log = make_provider(
        get_responses=[FakeResponse(200, {"messages": []})],
        post_responses=[FakeResponse(200, {"id": "gmail-123"})])
    conversation = make_conversation(provider_thread_id="thr-7",
                                     provider_last_message_id="prior@mail.test")
    run(provider.send(message=make_message(), conversation=conversation,
                      idempotency_key="k1"))
    payload = log[1][2]
    assert payload["threadId"] == "thr-7"
    mail = message_from_bytes(base64.urlsafe_b64decode(payload["raw"]))
    assert mail["In-Reply-To"] == "<prior@mail.test>"


# ---------------------------------------------------------------------- idempotency

def test_the_same_dispatch_key_always_produces_the_same_wire_id():
    first = gmail_provider.message_id_for(TENANT, "msg_1:1")
    assert first == gmail_provider.message_id_for(TENANT, "msg_1:1")
    assert first != gmail_provider.message_id_for(TENANT, "msg_1:2")
    assert first != gmail_provider.message_id_for("other_tenant", "msg_1:1")


def test_a_retried_dispatch_that_gmail_already_holds_is_not_sent_again():
    provider, log = make_provider(
        get_responses=[FakeResponse(200, {"messages": [{"id": "gmail-123"}]})],
        post_responses=[AssertionError("must not send a second copy")])
    result = run(provider.send(message=make_message(), conversation=make_conversation(),
                               idempotency_key="k1"))
    assert result.provider_message_id == "gmail-123"
    assert result.detail["deduplicated"] is True
    assert [entry[0] for entry in log] == ["GET"], "no second send may be attempted"


def test_a_failed_duplicate_check_does_not_fall_through_into_a_send():
    """An unanswerable "did I already send this?" must stop the dispatch.

    Sending anyway would be choosing a possible duplicate over a retry, which is the
    wrong way round.
    """
    provider, log = make_provider(
        get_responses=[FakeResponse(503, text="backend error")],
        post_responses=[AssertionError("must not send when the check was inconclusive")])
    with pytest.raises(RuntimeError):
        run(provider.send(message=make_message(), conversation=make_conversation(),
                          idempotency_key="k1"))
    assert [entry[0] for entry in log] == ["GET"]


# ----------------------------------------------------------- failure classification

@pytest.mark.parametrize("status", sorted(gmail_provider.PROVEN_REJECTION_CODES))
def test_a_definite_provider_rejection_is_raised_as_a_rejection(status):
    provider, _ = make_provider(
        get_responses=[FakeResponse(200, {"messages": []})],
        post_responses=[FakeResponse(status, text="nope")])
    with pytest.raises(cv.DeliveryRejected):
        run(provider.send(message=make_message(), conversation=make_conversation(),
                          idempotency_key="k1"))


@pytest.mark.parametrize("failure", [
    FakeResponse(429, text="rate limited"),
    FakeResponse(500, text="server error"),
    FakeResponse(503, text="unavailable"),
    FakeResponse(200, {}),  # accepted, but told us nothing we can refer to later
])
def test_an_ambiguous_provider_answer_is_never_reported_as_a_rejection(failure):
    """A 429 or a 5xx may mean the message was accepted and the acknowledgement lost.

    These must not raise `DeliveryRejected`: the caller reads that as proof of
    non-delivery and allows a retry, which is how one message becomes two.
    """
    provider, _ = make_provider(
        get_responses=[FakeResponse(200, {"messages": []})],
        post_responses=[failure])
    with pytest.raises(Exception) as excinfo:
        run(provider.send(message=make_message(), conversation=make_conversation(),
                          idempotency_key="k1"))
    assert not isinstance(excinfo.value, cv.DeliveryRejected)


def test_a_dropped_connection_is_an_unknown_outcome_not_a_failure():
    provider, _ = make_provider(
        get_responses=[FakeResponse(200, {"messages": []})],
        post_responses=[ConnectionError("connection reset by peer")])
    with pytest.raises(Exception) as excinfo:
        run(provider.send(message=make_message(), conversation=make_conversation(),
                          idempotency_key="k1"))
    assert not isinstance(excinfo.value, cv.DeliveryRejected)


# -------------------------------------------------------------------- reconciliation

def test_locate_answers_whether_the_provider_holds_a_dispatch():
    provider, _ = make_provider(
        get_responses=[FakeResponse(200, {"messages": [{"id": "gmail-55"}]})])
    assert run(provider.locate(tenant_id=TENANT, idempotency_key="k1")) == "gmail-55"

    provider, _ = make_provider(get_responses=[FakeResponse(200, {"messages": []})])
    assert run(provider.locate(tenant_id=TENANT, idempotency_key="k1")) is None


def test_a_lookup_that_cannot_be_completed_raises_rather_than_answering_no():
    """"I could not check" is not "it was never sent"."""
    provider, _ = make_provider(get_responses=[FakeResponse(500, text="boom")])
    with pytest.raises(RuntimeError):
        run(provider.locate(tenant_id=TENANT, idempotency_key="k1"))
