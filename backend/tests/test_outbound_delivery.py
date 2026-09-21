"""The real email adapter driven through the real delivery choke point.

`test_conversations` proves the choke point refuses correctly using a stand-in
provider, and `test_gmail_provider` proves the adapter classifies every answer Gmail
can give. This file is the join: the actual `GmailChannelProvider` behind
`attempt_delivery`, so the guarantees hold end to end rather than one layer at a time.

The scenario that matters most is the one in the middle -- a dispatch whose outcome was
never observed, followed by the operator doing the only safe thing: asking the provider
what happened, rather than sending again.
"""

import asyncio
import os
import uuid

import pytest
from cryptography.fernet import Fernet
from motor.motor_asyncio import AsyncIOMotorClient

import approval_queue as aq
import conversations as cv
import gmail_provider

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
TENANT = "ten_out_a"

_LOOP = None


def run(coro):
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


@pytest.fixture()
def db():
    db_name = f"cv_out_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[db_name]
    run(cv.ensure_indexes(database))
    run(aq.ensure_indexes(database))
    run(database.integration_connections.insert_one(
        {"tenant_id": TENANT, "provider": "gmail", "status": "active"}))
    run(database.integrations.insert_one(
        {"tenant_id": TENANT, "name": "Gmail", "status": "CONNECTED"}))
    yield database
    run(client.drop_database(db_name))
    client.close()


class FakeGmail:
    """A Gmail that records what it was asked to do and answers however a test needs.

    `held` is Gmail's own view of which wire ids it already has, so the adapter's
    duplicate check is exercised against something that behaves like the real thing.
    """

    def __init__(self):
        self.held: dict[str, str] = {}
        self.sends = 0
        self.send_behaviour = "ok"
        self.lookup_behaviour = "ok"
        self.last_raw = None

    def client(self):
        gmail = self

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, url, params=None, headers=None):
                if gmail.lookup_behaviour == "error":
                    return _Response(500, text="lookup unavailable")
                wire_id = (params or {}).get("q", "").replace("rfc822msgid:", "")
                found = gmail.held.get(wire_id)
                return _Response(200, {"messages": [{"id": found}] if found else []})

            async def post(self, url, json=None, headers=None):
                gmail.last_raw = (json or {}).get("raw")
                if gmail.send_behaviour == "rejected":
                    return _Response(400, text="invalid recipient")
                if gmail.send_behaviour == "lost":
                    # Accepted, then the acknowledgement never came back.
                    gmail.sends += 1
                    gmail._remember(json)
                    raise TimeoutError("connection dropped after dispatch")
                gmail.sends += 1
                provider_id = gmail._remember(json)
                return _Response(200, {"id": provider_id, "threadId": "thr-1"})

        return _Client()

    def _remember(self, payload):
        import base64
        from email import message_from_bytes
        mail = message_from_bytes(base64.urlsafe_b64decode(payload["raw"]))
        wire_id = (mail["Message-ID"] or "").strip("<>")
        provider_id = f"gmail-{self.sends}"
        self.held[wire_id] = provider_id
        return provider_id


class _Response:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


@pytest.fixture()
def gmail():
    return FakeGmail()


@pytest.fixture()
def registry(gmail):
    async def access_token(tenant_id, force_refresh=False):
        return "token"

    async def connection(tenant_id):
        return {"status": "active", "account_identity": "sales@acme.test",
                "scopes": [gmail_provider.GMAIL_SEND_SCOPE]}

    registry = cv.ProviderRegistry()
    registry.register(gmail_provider.GmailChannelProvider(
        access_token=access_token, connection=connection,
        http_client=gmail.client))
    return registry


def approved_message(db, body="Your quote from March is still open."):
    conversation = run(cv.create_conversation(
        db, tenant_id=TENANT, channel=cv.CHANNEL_EMAIL, actor="user@acme.test",
        subject="Your quote", contact_id="ct_1", recovery_case_id="rc_1",
        participants=[{"kind": cv.PARTICIPANT_CONTACT, "id": "ct_1",
                       "address": "buyer@client.test"}]))
    run(cv.record_consent(db, tenant_id=TENANT, conversation_id=conversation["id"],
                          state=cv.CONSENT_GRANTED, actor="admin@acme.test",
                          basis="Client asked us to email them."))
    message = run(cv.draft_message(db, tenant_id=TENANT, conversation_id=conversation["id"],
                                   body=body, actor="agent:composer",
                                   requester_kind=aq.REQUESTER_AGENT,
                                   to_address="buyer@client.test"))
    message = run(cv.request_approval(db, tenant_id=TENANT, message_id=message["id"],
                                      actor="agent:composer"))
    run(aq.decide(db, tenant_id=TENANT, approval_id=message["approval_id"],
                  decision=aq.APPROVED, actor="admin@acme.test"))
    message = run(cv.mark_approved(db, tenant_id=TENANT, message_id=message["id"],
                                   actor="admin@acme.test"))
    return conversation, message


def test_an_approved_message_is_actually_sent_and_records_provider_evidence(db, registry, gmail):
    _, message = approved_message(db)
    sent = run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                   actor="worker-1", registry=registry))
    assert sent["status"] == cv.SENT
    assert sent["provider"] == "gmail"
    assert sent["provider_message_id"] == "gmail-1"
    assert sent["rfc822_message_id"].startswith("cv-")
    assert sent["sent_at"]
    assert gmail.sends == 1


def test_nothing_is_sent_while_any_precondition_is_unmet(db, registry, gmail):
    """Consent withdrawn between approval and dispatch must stop the send."""
    conversation, message = approved_message(db)
    run(cv.record_consent(db, tenant_id=TENANT, conversation_id=conversation["id"],
                          state=cv.CONSENT_WITHDRAWN, actor="admin@acme.test"))
    with pytest.raises(cv.DeliveryRefused) as exc:
        run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                actor="worker-1", registry=registry))
    assert exc.value.reason == cv.REFUSAL_CONSENT
    assert gmail.sends == 0


def test_a_proven_provider_rejection_leaves_the_message_retryable(db, registry, gmail):
    _, message = approved_message(db)
    gmail.send_behaviour = "rejected"
    failed = run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                     actor="worker-1", registry=registry))
    assert failed["status"] == cv.FAILED
    assert gmail.sends == 0, "a rejected send must not have delivered anything"
    # Failed is a state a fresh approval can move out of.
    assert cv.PENDING_APPROVAL in cv.MESSAGE_TRANSITIONS[cv.FAILED]


def test_a_lost_acknowledgement_is_unknown_and_cannot_be_resent(db, registry, gmail):
    _, message = approved_message(db)
    gmail.send_behaviour = "lost"
    unknown = run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                      actor="worker-1", registry=registry))
    assert unknown["status"] == cv.OUTCOME_UNKNOWN
    assert gmail.sends == 1, "the message did in fact reach Gmail"

    # The client already has it. Nothing may send it again.
    with pytest.raises(cv.DeliveryRefused) as exc:
        run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                actor="worker-2", registry=registry))
    assert exc.value.reason == cv.REFUSAL_NOT_DISPATCHABLE
    assert gmail.sends == 1


def test_reconciliation_finds_the_lost_dispatch_and_records_it_as_sent_once(db, registry, gmail):
    _, message = approved_message(db)
    gmail.send_behaviour = "lost"
    run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                            actor="worker-1", registry=registry))

    provider = registry.get(cv.CHANNEL_EMAIL)
    stranded = run(cv.get_message(db, TENANT, message["id"]))
    key = cv.dispatch_key(stranded)
    found = run(provider.locate(tenant_id=TENANT, idempotency_key=key))
    assert found == "gmail-1", "the provider holds the message it never acknowledged"

    resolved = run(cv.reconcile_unknown(
        db, tenant_id=TENANT, message_id=message["id"], actor="ops@acme.test",
        found=True, provider_message_id=found,
        detail={"rfc822_message_id": gmail_provider.message_id_for(TENANT, key)}))
    assert resolved["status"] == cv.SENT
    assert resolved["provider_message_id"] == "gmail-1"
    assert resolved["rfc822_message_id"], (
        "the wire id must be recorded so the client's reply can be matched to it")
    assert gmail.sends == 1, "reconciliation asks a question; it never sends"


def test_a_dispatch_gmail_already_holds_is_not_delivered_twice(db, registry, gmail):
    """The adapter's own idempotency, exercised through the choke point.

    Gmail offers no idempotency key, so a retried dispatch would otherwise put a second
    copy in a client's inbox. Pre-seeding Gmail with the wire id this dispatch will use
    simulates exactly that: the first attempt got through, the acknowledgement did not.
    """
    _, message = approved_message(db)
    approved = run(cv.get_message(db, TENANT, message["id"]))
    wire_id = gmail_provider.message_id_for(TENANT, cv.dispatch_key(approved))
    gmail.held[wire_id] = "gmail-already-there"

    sent = run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                   actor="worker-1", registry=registry))
    assert sent["status"] == cv.SENT
    assert sent["provider_message_id"] == "gmail-already-there"
    assert gmail.sends == 0, "no second copy may be sent"


def test_an_inconclusive_duplicate_check_leaves_the_outcome_unknown(db, registry, gmail):
    _, message = approved_message(db)
    gmail.lookup_behaviour = "error"
    result = run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                     actor="worker-1", registry=registry))
    assert result["status"] == cv.OUTCOME_UNKNOWN, (
        "an unanswerable 'did I already send this?' is not a licence to send")
    assert gmail.sends == 0


def test_the_words_that_go_out_are_the_words_that_were_approved(db, registry, gmail):
    import base64
    from email import message_from_bytes

    body = "Hi Sam,\n\nYour March quote is still open. Shall we go ahead?\n"
    _, message = approved_message(db, body=body)
    run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                            actor="worker-1", registry=registry))
    mail = message_from_bytes(base64.urlsafe_b64decode(gmail.last_raw))
    assert mail.get_payload(decode=True).decode() == body
