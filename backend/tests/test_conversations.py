"""Conversation and CommunicationMessage tests (§8 #1, #2).

The module's whole value is that nothing leaves the CRM unless four separate conditions
hold at once. So the tests are mostly about refusal: each precondition is removed in turn
and the send must be refused with that precondition named, and the approval must survive
a refusal rather than being burned by it.
"""

import asyncio
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import approval_queue as aq
import conversations as cv

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT = "ten_cnv_a"
OTHER_TENANT = "ten_cnv_b"

_LOOP = None


def run(coro):
    """Run a coroutine on a loop this module owns (see test_second_chance for why)."""
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


@pytest.fixture()
def db():
    db_name = f"cv_cnv_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[db_name]
    run(cv.ensure_indexes(database))
    run(aq.ensure_indexes(database))
    yield database
    run(client.drop_database(db_name))
    client.close()


class RecordingProvider:
    """A stand-in for the email adapter that does not exist yet."""

    channel = cv.CHANNEL_EMAIL
    name = "recording-test-provider"

    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    async def send(self, *, message, conversation):
        if self.fail:
            raise RuntimeError("provider rejected the message")
        self.sent.append(message["id"])
        return cv.DeliveryResult(provider_message_id=f"prov_{len(self.sent)}",
                                 detail={"accepted": True})


@pytest.fixture()
def registry():
    return cv.ProviderRegistry()


def make_conversation(db, channel=cv.CHANNEL_EMAIL, **kwargs):
    return run(cv.create_conversation(db, tenant_id=kwargs.pop("tenant_id", TENANT),
                                      channel=channel, actor="user@example.com",
                                      subject="Renewal follow-up", **kwargs))


def authorize_email(db, tenant_id=TENANT):
    """Make the email channel genuinely authorised for a tenant, via its own records."""
    run(db.integration_connections.insert_one(
        {"tenant_id": tenant_id, "provider": "gmail", "status": "active"}))
    run(db.integrations.insert_one(
        {"tenant_id": tenant_id, "name": "Gmail", "status": "CONNECTED"}))


def grant_consent(db, conversation_id, tenant_id=TENANT):
    return run(cv.record_consent(db, tenant_id=tenant_id, conversation_id=conversation_id,
                                 state=cv.CONSENT_GRANTED, actor="admin@example.com",
                                 basis="Client asked us to email them (recorded on the call)."))


def approved_message(db, conversation_id, tenant_id=TENANT):
    message = run(cv.draft_message(db, tenant_id=tenant_id, conversation_id=conversation_id,
                                   body="Following up on the proposal.",
                                   actor="agent:composer",
                                   requester_kind=aq.REQUESTER_AGENT))
    message = run(cv.request_approval(db, tenant_id=tenant_id, message_id=message["id"],
                                      actor="agent:composer"))
    run(aq.decide(db, tenant_id=tenant_id, approval_id=message["approval_id"],
                  decision=aq.APPROVED, actor="admin@example.com"))
    return run(cv.mark_approved(db, tenant_id=tenant_id, message_id=message["id"],
                                actor="admin@example.com"))


# ------------------------------------------------------------- conversations

def test_a_conversation_starts_open_with_no_consent(db):
    conversation = make_conversation(db)
    assert conversation["status"] == cv.STATUS_OPEN
    assert conversation["handled_by"] == cv.HANDLED_BY_HUMAN
    # No record means no permission, never assumed permission.
    assert conversation["consent"]["state"] == cv.CONSENT_UNKNOWN


def test_an_unknown_channel_is_rejected(db):
    with pytest.raises(cv.ConversationError):
        make_conversation(db, channel="carrier_pigeon")


def test_participants_are_validated(db):
    with pytest.raises(cv.ConversationError):
        make_conversation(db, participants=[{"kind": "alien", "id": "x"}])
    conversation = make_conversation(
        db, participants=[{"kind": cv.PARTICIPANT_CONTACT, "id": "con_1",
                           "address": "a@example.com", "display_name": "A"}])
    assert conversation["participants"][0]["kind"] == cv.PARTICIPANT_CONTACT


def test_an_external_thread_cannot_fork_a_conversation(db):
    first = make_conversation(db, external_thread_id="thread-1")
    second = make_conversation(db, external_thread_id="thread-1")
    assert second["deduplicated"] is True
    assert second["id"] == first["id"]


def test_handoff_records_the_agent_human_boundary(db):
    conversation = make_conversation(db, handled_by=cv.HANDLED_BY_AGENT)
    assert conversation["handled_by"] == cv.HANDLED_BY_AGENT
    handed = run(cv.handoff(db, tenant_id=TENANT, conversation_id=conversation["id"],
                            to=cv.HANDLED_BY_HUMAN, actor="agent:support",
                            assignee="rep@example.com", reason="Pricing question"))
    assert handed["handled_by"] == cv.HANDLED_BY_HUMAN
    assert handed["assignee"] == "rep@example.com"
    assert any(h["action"] == "handoff:human" for h in handed["history"])


def test_consent_granted_requires_a_stated_basis(db):
    conversation = make_conversation(db)
    with pytest.raises(cv.ConversationError):
        run(cv.record_consent(db, tenant_id=TENANT, conversation_id=conversation["id"],
                              state=cv.CONSENT_GRANTED, actor="admin@example.com"))
    recorded = grant_consent(db, conversation["id"])
    assert recorded["consent"]["state"] == cv.CONSENT_GRANTED
    assert recorded["consent"]["basis"]
    assert recorded["consent"]["recorded_by"] == "admin@example.com"


def test_snooze_and_close_move_a_conversation_out_of_the_open_list(db):
    conversation = make_conversation(db)
    run(cv.set_status(db, tenant_id=TENANT, conversation_id=conversation["id"],
                      status=cv.STATUS_CLOSED, actor="user@example.com"))
    assert run(cv.list_conversations(db, TENANT, status="open")) == []
    assert len(run(cv.list_conversations(db, TENANT, status="all"))) == 1


def test_conversations_are_tenant_scoped(db):
    make_conversation(db)
    make_conversation(db, tenant_id=OTHER_TENANT)
    assert len(run(cv.list_conversations(db, TENANT))) == 1
    assert run(cv.get_conversation(db, OTHER_TENANT, "nope")) is None


# ------------------------------------------------------------------ drafting

def test_drafting_is_always_allowed(db):
    """Composing is not sending. A draft must not require a channel or consent."""
    conversation = make_conversation(db)
    message = run(cv.draft_message(db, tenant_id=TENANT, conversation_id=conversation["id"],
                                   body="Hello", actor="user@example.com"))
    assert message["status"] == cv.DRAFT
    assert message["direction"] == cv.OUTBOUND


def test_an_empty_body_is_rejected(db):
    conversation = make_conversation(db)
    with pytest.raises(cv.ConversationError):
        run(cv.draft_message(db, tenant_id=TENANT, conversation_id=conversation["id"],
                             body="   ", actor="user@example.com"))


def test_drafting_is_idempotent_on_a_key(db):
    conversation = make_conversation(db)
    first = run(cv.draft_message(db, tenant_id=TENANT, conversation_id=conversation["id"],
                                 body="Hello", actor="user@example.com",
                                 idempotency_key="k1"))
    second = run(cv.draft_message(db, tenant_id=TENANT, conversation_id=conversation["id"],
                                  body="Hello again", actor="user@example.com",
                                  idempotency_key="k1"))
    assert second["deduplicated"] is True
    assert second["id"] == first["id"]


def test_requesting_approval_records_what_would_still_block_it(db):
    conversation = make_conversation(db)
    message = run(cv.draft_message(db, tenant_id=TENANT, conversation_id=conversation["id"],
                                   body="Hello", actor="user@example.com"))
    pending = run(cv.request_approval(db, tenant_id=TENANT, message_id=message["id"],
                                      actor="user@example.com"))
    assert pending["status"] == cv.PENDING_APPROVAL
    approval = run(aq.get(db, TENANT, pending["approval_id"]))
    assert approval["subject_type"] == "communication_message"
    # An operator must be able to see that approving it will not make it send.
    assert len(approval["blocked_reasons"]) == 3


def test_a_message_cannot_be_promoted_without_a_real_approval(db):
    conversation = make_conversation(db)
    message = run(cv.draft_message(db, tenant_id=TENANT, conversation_id=conversation["id"],
                                   body="Hello", actor="user@example.com"))
    run(cv.request_approval(db, tenant_id=TENANT, message_id=message["id"],
                            actor="user@example.com"))
    # The approval exists but was never decided.
    with pytest.raises(cv.ConversationError):
        run(cv.mark_approved(db, tenant_id=TENANT, message_id=message["id"],
                             actor="attacker@example.com"))


# ----------------------------------------------------------------- refusals

def test_send_is_refused_when_no_channel_is_authorized(db, registry):
    conversation = make_conversation(db)
    grant_consent(db, conversation["id"])
    registry.register(RecordingProvider())
    message = approved_message(db, conversation["id"])

    with pytest.raises(cv.DeliveryRefused) as exc:
        run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                actor="worker-1", registry=registry))
    assert exc.value.reason == cv.REFUSAL_CHANNEL
    assert run(cv.get_message(db, TENANT, message["id"]))["status"] == cv.BLOCKED


def test_send_is_refused_without_consent(db, registry):
    conversation = make_conversation(db)
    authorize_email(db)
    registry.register(RecordingProvider())
    message = approved_message(db, conversation["id"])

    with pytest.raises(cv.DeliveryRefused) as exc:
        run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                actor="worker-1", registry=registry))
    assert exc.value.reason == cv.REFUSAL_CONSENT


def test_send_is_refused_with_no_registered_provider(db, registry):
    conversation = make_conversation(db)
    authorize_email(db)
    grant_consent(db, conversation["id"])
    message = approved_message(db, conversation["id"])

    with pytest.raises(cv.DeliveryRefused) as exc:
        run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                actor="worker-1", registry=registry))
    assert exc.value.reason == cv.REFUSAL_PROVIDER


def test_send_is_refused_without_an_approval(db, registry):
    conversation = make_conversation(db)
    authorize_email(db)
    grant_consent(db, conversation["id"])
    registry.register(RecordingProvider())
    # Force a message to `approved` without ever raising an approval request.
    message = run(cv.draft_message(db, tenant_id=TENANT, conversation_id=conversation["id"],
                                   body="Hello", actor="user@example.com"))
    run(db[cv.MESSAGES].update_one({"id": message["id"]},
                                   {"$set": {"status": cv.APPROVED}}))

    with pytest.raises(cv.DeliveryRefused) as exc:
        run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                actor="worker-1", registry=registry))
    assert exc.value.reason == cv.REFUSAL_APPROVAL


def test_a_draft_cannot_be_sent(db, registry):
    conversation = make_conversation(db)
    message = run(cv.draft_message(db, tenant_id=TENANT, conversation_id=conversation["id"],
                                   body="Hello", actor="user@example.com"))
    with pytest.raises(cv.DeliveryRefused) as exc:
        run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                actor="worker-1", registry=registry))
    assert exc.value.reason == cv.REFUSAL_NOT_DISPATCHABLE


def test_a_refusal_does_not_burn_the_approval(db, registry):
    """A precondition that refuses must leave the approval usable once it is satisfied."""
    conversation = make_conversation(db)
    grant_consent(db, conversation["id"])
    registry.register(RecordingProvider())
    message = approved_message(db, conversation["id"])

    with pytest.raises(cv.DeliveryRefused):
        run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                actor="worker-1", registry=registry))
    approval = run(aq.get(db, TENANT, message["approval_id"]))
    assert approval["execution"]["state"] == aq.EXECUTION_PENDING


# ------------------------------------------------------------ the happy path

def test_a_fully_satisfied_message_is_dispatched_once(db, registry):
    conversation = make_conversation(db)
    authorize_email(db)
    grant_consent(db, conversation["id"])
    provider = RecordingProvider()
    registry.register(provider)
    message = approved_message(db, conversation["id"])

    sent = run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                   actor="worker-1", registry=registry))
    assert sent["status"] == cv.SENT
    assert sent["provider"] == provider.name
    assert sent["provider_message_id"]
    assert provider.sent == [message["id"]]

    # A sent message is no longer dispatchable, so a second attempt reaches no provider
    # and does not corrupt the state of the message that was already sent.
    with pytest.raises(cv.DeliveryRefused) as exc:
        run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                actor="worker-2", registry=registry))
    assert exc.value.reason == cv.REFUSAL_NOT_DISPATCHABLE
    assert provider.sent == [message["id"]]
    assert run(cv.get_message(db, TENANT, message["id"]))["status"] == cv.SENT

    conversation_now = run(cv.get_conversation(db, TENANT, conversation["id"]))
    assert conversation_now["message_count"] == 1
    assert conversation_now["last_direction"] == cv.OUTBOUND


def test_a_provider_failure_becomes_message_state_not_an_exception(db, registry):
    conversation = make_conversation(db)
    authorize_email(db)
    grant_consent(db, conversation["id"])
    registry.register(RecordingProvider(fail=True))
    message = approved_message(db, conversation["id"])

    failed = run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                     actor="worker-1", registry=registry))
    assert failed["status"] == cv.FAILED
    assert "provider rejected" in failed["error"]


def test_an_internal_message_needs_no_provider_or_channel(db, registry):
    """Internal notes never leave the CRM, so they are not gated on a channel."""
    conversation = make_conversation(db, channel=cv.CHANNEL_INTERNAL)
    message = approved_message(db, conversation["id"])
    sent = run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                   actor="worker-1", registry=registry))
    assert sent["status"] == cv.SENT


# -------------------------------------------------------- receipts and inbound

def test_a_receipt_marks_the_message_delivered(db, registry):
    conversation = make_conversation(db)
    authorize_email(db)
    grant_consent(db, conversation["id"])
    registry.register(RecordingProvider())
    message = approved_message(db, conversation["id"])
    sent = run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                   actor="worker-1", registry=registry))

    delivered = run(cv.record_receipt(db, tenant_id=TENANT, provider=sent["provider"],
                                      provider_message_id=sent["provider_message_id"],
                                      status=cv.DELIVERED))
    assert delivered["status"] == cv.DELIVERED
    assert delivered["delivered_at"]


def test_a_receipt_for_an_unknown_message_is_rejected(db):
    with pytest.raises(cv.MessageNotFound):
        run(cv.record_receipt(db, tenant_id=TENANT, provider="x",
                              provider_message_id="nope", status=cv.DELIVERED))


def test_inbound_reopens_a_closed_conversation(db):
    conversation = make_conversation(db)
    run(cv.set_status(db, tenant_id=TENANT, conversation_id=conversation["id"],
                      status=cv.STATUS_CLOSED, actor="user@example.com"))
    received = run(cv.record_inbound(db, tenant_id=TENANT, conversation_id=conversation["id"],
                                     body="Actually, yes — let's talk.",
                                     from_address="client@example.com", provider="gmail",
                                     provider_message_id="ext-1"))
    assert received["status"] == cv.RECEIVED
    assert received["direction"] == cv.INBOUND
    reopened = run(cv.get_conversation(db, TENANT, conversation["id"]))
    assert reopened["status"] == cv.STATUS_OPEN
    assert reopened["last_direction"] == cv.INBOUND


def test_a_replayed_inbound_delivery_does_not_duplicate(db):
    conversation = make_conversation(db)
    first = run(cv.record_inbound(db, tenant_id=TENANT, conversation_id=conversation["id"],
                                  body="Hi", provider="gmail", provider_message_id="ext-2"))
    second = run(cv.record_inbound(db, tenant_id=TENANT, conversation_id=conversation["id"],
                                   body="Hi", provider="gmail", provider_message_id="ext-2"))
    assert second["deduplicated"] is True
    assert second["id"] == first["id"]
    assert len(run(cv.list_messages(db, TENANT, conversation["id"]))) == 1


# ------------------------------------------------------------------- registry

def test_the_application_registry_is_empty(db):
    """The honest state: no provider adapter has been built or certified."""
    assert all(entry["registered"] is False for entry in cv.REGISTRY.describe())


def test_a_provider_for_an_unknown_channel_is_rejected(registry):
    class Bogus:
        channel = "telepathy"
        name = "bogus"

        async def send(self, *, message, conversation):
            raise AssertionError("must never be called")

    with pytest.raises(cv.ConversationError):
        registry.register(Bogus())


def test_summary_reports_what_is_waiting_and_what_is_blocked(db, registry):
    conversation = make_conversation(db, handled_by=cv.HANDLED_BY_AGENT)
    grant_consent(db, conversation["id"])
    message = approved_message(db, conversation["id"])
    with pytest.raises(cv.DeliveryRefused):
        run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                actor="worker-1", registry=registry))

    other = make_conversation(db)
    pending = run(cv.draft_message(db, tenant_id=TENANT, conversation_id=other["id"],
                                   body="Hello", actor="user@example.com"))
    run(cv.request_approval(db, tenant_id=TENANT, message_id=pending["id"],
                            actor="user@example.com"))

    summary = run(cv.summary(db, TENANT))
    assert summary["open_conversations"] == 2
    assert summary["agent_handled_open"] == 1
    assert summary["messages_awaiting_approval"] == 1
    assert summary["messages_blocked"] == 1
    assert summary["by_channel"][cv.CHANNEL_EMAIL] == 2
