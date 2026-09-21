"""The return path.

A reply that reaches the wrong case is worse than a reply that reaches no case at all:
a recovery case that reads a stranger's answer as its own outcome will go on to claim
credit for a recovery that never happened. So most of what is asserted here is the
refusal to guess -- the cases where matching is ambiguous and the message is parked for
a human instead of being placed.
"""

import asyncio
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import conversations as cv
import email_inbound as inbound

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT = "ten_inb_a"
OTHER_TENANT = "ten_inb_b"

_LOOP = None


def run(coro):
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


@pytest.fixture()
def db():
    db_name = f"cv_inb_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[db_name]
    run(cv.ensure_indexes(database))
    run(inbound.ensure_indexes(database))
    yield database
    run(client.drop_database(db_name))
    client.close()


def gmail_message(*, message_id=None, thread_id=None, sender="buyer@client.test",
                  subject="Re: Your quote", in_reply_to=None, references=None,
                  snippet="Yes, let's proceed.", content_type="text/plain",
                  failed_recipients=None, internal_date="1789000000000"):
    headers = [{"name": "From", "value": sender},
               {"name": "To", "value": "sales@acme.test"},
               {"name": "Subject", "value": subject},
               {"name": "Content-Type", "value": content_type}]
    if in_reply_to:
        headers.append({"name": "In-Reply-To", "value": f"<{in_reply_to}>"})
    if references:
        headers.append({"name": "References", "value": " ".join(f"<{r}>" for r in references)})
    if failed_recipients:
        headers.append({"name": "X-Failed-Recipients", "value": failed_recipients})
    return {"id": message_id or f"gm_{uuid.uuid4().hex[:10]}",
            "threadId": thread_id or f"thr_{uuid.uuid4().hex[:8]}",
            "snippet": snippet, "internalDate": internal_date,
            "labelIds": ["INBOX"], "payload": {"headers": headers}}


def make_conversation(db, *, tenant_id=TENANT, contact_id="ct_1", **kwargs):
    return run(cv.create_conversation(
        db, tenant_id=tenant_id, channel=cv.CHANNEL_EMAIL, actor="user@example.com",
        subject="Renewal follow-up",
        contact_id=contact_id,
        participants=[{"kind": cv.PARTICIPANT_CONTACT, "id": contact_id,
                       "address": "buyer@client.test"}],
        **kwargs))


def make_sent_message(db, conversation, *, wire_id, provider_message_id="gmail-out-1"):
    """An outbound message already recorded as sent under a known wire id."""
    doc = {"id": f"msg_{uuid.uuid4().hex[:10]}", "tenant_id": TENANT,
           "conversation_id": conversation["id"], "channel": cv.CHANNEL_EMAIL,
           "direction": cv.OUTBOUND, "status": cv.SENT, "body": "Following up",
           "subject": "Your quote", "provider": "gmail",
           "provider_message_id": provider_message_id, "rfc822_message_id": wire_id,
           "history": [], "created_at": "2026-09-01T00:00:00+00:00"}
    run(db[cv.MESSAGES].insert_one(dict(doc)))
    return doc


# --------------------------------------------------------------------- normalisation

def test_normalisation_extracts_everything_matching_depends_on():
    record = inbound.normalize(gmail_message(
        message_id="gm-1", thread_id="thr-1", in_reply_to="cv-abc@clientverse.app",
        references=["cv-old@clientverse.app", "cv-abc@clientverse.app"]))
    assert record["provider_message_id"] == "gm-1"
    assert record["thread_id"] == "thr-1"
    assert record["from_address"] == "buyer@client.test"
    assert "cv-abc@clientverse.app" in record["in_reply_to"]
    assert record["received_at"].startswith("20")


def test_a_message_with_no_headers_at_all_still_normalises():
    record = inbound.normalize({"id": "gm-x", "threadId": "thr-x"})
    assert record["from_address"] is None
    assert record["subject"] == "(no subject)"


# ------------------------------------------------------------------ classification

@pytest.mark.parametrize("message", [
    gmail_message(sender="mailer-daemon@googlemail.com",
                  subject="Delivery Status Notification (Failure)"),
    gmail_message(sender="postmaster@client.test", subject="Undelivered Mail Returned"),
    gmail_message(failed_recipients="buyer@client.test"),
    gmail_message(content_type="multipart/report; report-type=delivery-status"),
])
def test_a_delivery_report_is_not_mistaken_for_a_reply(message):
    assert inbound.is_bounce(inbound.normalize(message)) is True


def test_an_ordinary_reply_is_not_mistaken_for_a_bounce():
    assert inbound.is_bounce(inbound.normalize(gmail_message())) is False


# ----------------------------------------------------------------------- matching

def test_a_reply_on_a_tracked_provider_thread_matches_on_the_thread(db):
    conversation = make_conversation(db, provider_thread_id="thr-known")
    record = inbound.normalize(gmail_message(thread_id="thr-known"))
    match = run(inbound.match_conversation(db, TENANT, record))
    assert match["conversation"]["id"] == conversation["id"]
    assert match["basis"] == inbound.MATCH_THREAD


def test_a_reply_to_a_message_this_system_sent_matches_on_that_message(db):
    conversation = make_conversation(db)
    make_sent_message(db, conversation, wire_id="cv-known@clientverse.app")
    record = inbound.normalize(gmail_message(in_reply_to="cv-known@clientverse.app"))
    match = run(inbound.match_conversation(db, TENANT, record))
    assert match["conversation"]["id"] == conversation["id"]
    assert match["basis"] == inbound.MATCH_REPLY_HEADER


def test_a_sender_with_exactly_one_open_conversation_matches_on_the_address(db):
    run(db.contacts.insert_one({"tenant_id": TENANT, "id": "ct_1",
                                "email": "buyer@client.test"}))
    conversation = make_conversation(db)
    record = inbound.normalize(gmail_message())
    match = run(inbound.match_conversation(db, TENANT, record))
    assert match["conversation"]["id"] == conversation["id"]
    assert match["basis"] == inbound.MATCH_CONTACT


def test_a_sender_with_two_open_conversations_is_not_guessed_at(db):
    run(db.contacts.insert_one({"tenant_id": TENANT, "id": "ct_1",
                                "email": "buyer@client.test"}))
    make_conversation(db)
    make_conversation(db)
    match = run(inbound.match_conversation(db, TENANT, inbound.normalize(gmail_message())))
    assert match["conversation"] is None
    assert match["basis"] == inbound.MATCH_NONE
    assert "cannot be determined" in match["reason"]


def test_an_address_shared_by_two_contacts_is_not_guessed_at(db):
    run(db.contacts.insert_many([
        {"tenant_id": TENANT, "id": "ct_1", "email": "buyer@client.test"},
        {"tenant_id": TENANT, "id": "ct_2", "email": "buyer@client.test"}]))
    make_conversation(db)
    match = run(inbound.match_conversation(db, TENANT, inbound.normalize(gmail_message())))
    assert match["conversation"] is None
    assert "share the address" in match["reason"]


def test_matching_never_reaches_into_another_tenant(db):
    make_conversation(db, tenant_id=OTHER_TENANT, provider_thread_id="thr-other")
    record = inbound.normalize(gmail_message(thread_id="thr-other"))
    match = run(inbound.match_conversation(db, TENANT, record))
    assert match["conversation"] is None, (
        "a thread owned by another tenant must be invisible, not merely unpreferred")


def test_a_reply_header_from_another_tenants_message_does_not_match(db):
    other = make_conversation(db, tenant_id=OTHER_TENANT)
    run(db[cv.MESSAGES].insert_one({
        "id": "msg_other", "tenant_id": OTHER_TENANT, "conversation_id": other["id"],
        "channel": cv.CHANNEL_EMAIL, "direction": cv.OUTBOUND, "status": cv.SENT,
        "rfc822_message_id": "cv-other@clientverse.app", "history": []}))
    record = inbound.normalize(gmail_message(in_reply_to="cv-other@clientverse.app"))
    match = run(inbound.match_conversation(db, TENANT, record))
    assert match["conversation"] is None


# ----------------------------------------------------------------------- ingestion

def test_a_matched_reply_becomes_an_inbound_message_on_its_conversation(db):
    conversation = make_conversation(db, provider_thread_id="thr-known")
    result = run(inbound.ingest(db, tenant_id=TENANT,
                                record=inbound.normalize(gmail_message(thread_id="thr-known",
                                                                       snippet="Yes please"))))
    assert result["outcome"] == "reply"
    messages = run(cv.list_messages(db, TENANT, conversation["id"]))
    assert len(messages) == 1
    assert messages[0]["direction"] == cv.INBOUND
    assert messages[0]["status"] == cv.RECEIVED
    assert messages[0]["body"] == "Yes please"


def test_a_reply_reopens_a_closed_conversation(db):
    conversation = make_conversation(db, provider_thread_id="thr-known")
    run(cv.set_status(db, tenant_id=TENANT, conversation_id=conversation["id"],
                      status=cv.STATUS_CLOSED, actor="user@example.com"))
    run(inbound.ingest(db, tenant_id=TENANT,
                       record=inbound.normalize(gmail_message(thread_id="thr-known"))))
    reopened = run(cv.get_conversation(db, TENANT, conversation["id"]))
    assert reopened["status"] == cv.STATUS_OPEN


def test_replaying_the_same_inbound_message_records_it_once(db):
    make_conversation(db, provider_thread_id="thr-known")
    message = gmail_message(message_id="gm-same", thread_id="thr-known")
    first = run(inbound.ingest(db, tenant_id=TENANT, record=inbound.normalize(message)))
    second = run(inbound.ingest(db, tenant_id=TENANT, record=inbound.normalize(message)))
    assert first["deduplicated"] is False
    assert second["deduplicated"] is True
    assert run(db[cv.MESSAGES].count_documents({"tenant_id": TENANT,
                                                "direction": cv.INBOUND})) == 1


def test_the_first_reply_teaches_the_conversation_its_provider_thread(db):
    conversation = make_conversation(db)
    make_sent_message(db, conversation, wire_id="cv-known@clientverse.app")
    run(inbound.ingest(db, tenant_id=TENANT, record=inbound.normalize(
        gmail_message(thread_id="thr-learned", in_reply_to="cv-known@clientverse.app"))))
    updated = run(cv.get_conversation(db, TENANT, conversation["id"]))
    assert updated["provider_thread_id"] == "thr-learned", (
        "later messages in the thread should then match on the strongest evidence")


def test_an_unplaceable_reply_is_parked_with_its_reason_not_discarded(db):
    result = run(inbound.ingest(db, tenant_id=TENANT,
                                record=inbound.normalize(gmail_message(
                                    sender="stranger@nowhere.test"))))
    assert result["outcome"] == "unmatched"
    parked = run(inbound.list_unmatched(db, TENANT))
    assert len(parked) == 1
    assert parked[0]["from_address"] == "stranger@nowhere.test"
    assert parked[0]["reason"]


def test_a_parked_message_can_be_placed_by_a_person(db):
    conversation = make_conversation(db)
    run(inbound.ingest(db, tenant_id=TENANT,
                       record=inbound.normalize(gmail_message(sender="stranger@nowhere.test"))))
    parked = run(inbound.list_unmatched(db, TENANT))[0]
    result = run(inbound.assign_unmatched(db, tenant_id=TENANT, inbound_id=parked["id"],
                                          conversation_id=conversation["id"],
                                          actor="ops@acme.test"))
    assert result["ok"] is True
    messages = run(cv.list_messages(db, TENANT, conversation["id"]))
    assert len(messages) == 1
    remaining = run(inbound.list_unmatched(db, TENANT))
    assert remaining == []
    placed = run(db[inbound.UNMATCHED].find_one({"id": parked["id"]}, {"_id": 0}))
    assert placed["match_basis"] == "manual", (
        "a human decision must be recorded as a decision, not as evidence")


def test_a_person_cannot_place_a_parked_message_into_another_tenants_conversation(db):
    other = make_conversation(db, tenant_id=OTHER_TENANT)
    run(inbound.ingest(db, tenant_id=TENANT,
                       record=inbound.normalize(gmail_message(sender="stranger@nowhere.test"))))
    parked = run(inbound.list_unmatched(db, TENANT))[0]
    with pytest.raises(cv.ConversationNotFound):
        run(inbound.assign_unmatched(db, tenant_id=TENANT, inbound_id=parked["id"],
                                     conversation_id=other["id"], actor="ops@acme.test"))


# ------------------------------------------------------------------------- bounces

def test_a_bounce_marks_the_message_it_refers_to_as_failed(db):
    conversation = make_conversation(db)
    sent = make_sent_message(db, conversation, wire_id="cv-bounced@clientverse.app")
    result = run(inbound.ingest(db, tenant_id=TENANT, record=inbound.normalize(
        gmail_message(sender="mailer-daemon@googlemail.com",
                      subject="Delivery Status Notification (Failure)",
                      in_reply_to="cv-bounced@clientverse.app"))))
    assert result["outcome"] == "bounce" and result["applied"] is True
    updated = run(cv.get_message(db, TENANT, sent["id"]))
    assert updated["status"] == cv.FAILED
    assert updated["error"]


def test_a_bounce_is_never_recorded_as_a_reply(db):
    make_conversation(db, provider_thread_id="thr-known")
    run(inbound.ingest(db, tenant_id=TENANT, record=inbound.normalize(
        gmail_message(thread_id="thr-known", sender="mailer-daemon@googlemail.com",
                      subject="Delivery Status Notification (Failure)"))))
    inbound_messages = run(db[cv.MESSAGES].count_documents(
        {"tenant_id": TENANT, "direction": cv.INBOUND}))
    assert inbound_messages == 0, (
        "a bounce read as engagement would tell a case the client answered")


def test_a_bounce_that_names_nothing_we_sent_is_parked_not_applied(db):
    conversation = make_conversation(db)
    sent = make_sent_message(db, conversation, wire_id="cv-ours@clientverse.app")
    result = run(inbound.ingest(db, tenant_id=TENANT, record=inbound.normalize(
        gmail_message(sender="mailer-daemon@googlemail.com",
                      subject="Delivery Status Notification (Failure)",
                      in_reply_to="cv-someone-elses@clientverse.app"))))
    assert result["outcome"] == "unmatched"
    assert run(cv.get_message(db, TENANT, sent["id"]))["status"] == cv.SENT


# -------------------------------------------------------------------------- polling

def test_a_poll_counts_what_it_did_and_keeps_going_past_a_bad_message(db):
    make_conversation(db, provider_thread_id="thr-known")
    sent_conversation = make_conversation(db)
    make_sent_message(db, sent_conversation, wire_id="cv-b@clientverse.app",
                      provider_message_id="gmail-out-2")

    async def fetch(tenant_id, limit):
        return [
            gmail_message(thread_id="thr-known"),
            gmail_message(sender="mailer-daemon@googlemail.com",
                          subject="Delivery Status Notification (Failure)",
                          in_reply_to="cv-b@clientverse.app"),
            gmail_message(sender="stranger@nowhere.test"),
            {"id": None},  # unusable; must not abandon the rest of the batch
        ]

    summary = run(inbound.poll_tenant(db, tenant_id=TENANT, fetch_messages=fetch))
    assert summary["fetched"] == 4
    assert summary["replies"] == 1
    assert summary["bounces"] == 1
    assert summary["unmatched"] == 1


def test_a_poll_that_cannot_reach_the_provider_reports_it_rather_than_claiming_zero(db):
    async def fetch(tenant_id, limit):
        raise RuntimeError("not_connected")

    summary = run(inbound.poll_tenant(db, tenant_id=TENANT, fetch_messages=fetch))
    assert summary["errors"] == 1
    assert "not_connected" in summary["error"]
    assert summary["replies"] == 0
