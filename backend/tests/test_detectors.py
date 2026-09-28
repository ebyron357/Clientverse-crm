"""The remaining recovery detector families.

Each lane is asserted twice: once that it finds the thing it exists to find, and once
that it does *not* fire on the ordinary business that looks superficially similar. The
second half matters more. A detector that raises a case every time someone books an
appointment is not a recovery engine, it is noise, and an operator who learns to ignore
the queue has lost the product entirely.

Three invariants hold across every lane and are asserted for all of them together:
detection creates internal work and never an outbound message; re-running finds the
same case rather than a second one; and no lane can see another tenant's records.
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import conversations as cv
import detectors
import recovery_case as rc
from work_queue import WorkQueue

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT = "ten_det_a"
OTHER_TENANT = "ten_det_b"

_LOOP = None


def run(coro):
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


def ago(hours=0, days=0):
    return (datetime.now(timezone.utc) - timedelta(hours=hours, days=days)).isoformat()


def ahead(hours=0, days=0):
    return (datetime.now(timezone.utc) + timedelta(hours=hours, days=days)).isoformat()


@pytest.fixture()
def env():
    db_name = f"cv_det_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[db_name]
    queue = WorkQueue(database)
    run(queue.ensure_indexes())
    run(rc.ensure_indexes(database))
    run(cv.ensure_indexes(database))
    run(detectors.ensure_indexes(database))
    run(database.tenants.insert_many([{"tenant_id": TENANT, "name": "A"},
                                      {"tenant_id": OTHER_TENANT, "name": "B"}]))
    yield database, queue
    run(client.drop_database(db_name))
    client.close()


def insert(db, collection, doc, *, tenant_id=TENANT):
    doc = {"tenant_id": tenant_id, **doc}
    doc.setdefault("id", f"{collection[:3]}_{uuid.uuid4().hex[:10]}")
    run(db[collection].insert_one(dict(doc)))
    return doc


# ------------------------------------------------------------------- missed calls

def test_an_unanswered_inbound_call_with_no_callback_is_detected(env):
    db, _ = env
    insert(db, detectors.CALL_LOGS, {"direction": "inbound", "from_number": "+441632960001",
                                     "outcome": "missed", "occurred_at": ago(hours=8)})
    found = run(detectors.detect_missed_calls(db, TENANT))
    assert len(found) == 1
    assert found[0]["external_identity"] == {"kind": rc.IDENTITY_PHONE,
                                             "value": "+441632960001"}
    assert "unanswered" in found[0]["reason"]
    assert found[0]["record_collection"] == detectors.CALL_LOGS


def test_an_answered_call_is_not_a_missed_one(env):
    db, _ = env
    insert(db, detectors.CALL_LOGS, {"direction": "inbound", "from_number": "+441632960002",
                                     "outcome": "answered", "occurred_at": ago(hours=8)})
    assert run(detectors.detect_missed_calls(db, TENANT)) == []


def test_a_missed_call_that_was_returned_is_not_a_recovery_opportunity(env):
    db, _ = env
    insert(db, detectors.CALL_LOGS, {"direction": "inbound", "from_number": "+441632960003",
                                     "outcome": "missed", "occurred_at": ago(hours=8)})
    insert(db, detectors.CALL_LOGS, {"direction": "outbound", "to_number": "+441632960003",
                                     "outcome": "answered", "occurred_at": ago(hours=2)})
    assert run(detectors.detect_missed_calls(db, TENANT)) == []


def test_a_call_missed_minutes_ago_is_inside_the_grace_period(env):
    db, _ = env
    insert(db, detectors.CALL_LOGS, {"direction": "inbound", "from_number": "+441632960004",
                                     "outcome": "missed", "occurred_at": ago(hours=1)})
    assert run(detectors.detect_missed_calls(db, TENANT)) == [], (
        "somebody may still be about to call back")


# ------------------------------------------------------------------ web enquiries

def test_an_unanswered_web_enquiry_is_detected(env):
    db, _ = env
    insert(db, detectors.WEB_ENQUIRIES,
           {"name": "Sam", "email": "sam@client.test", "status": "new",
            "received_at": ago(days=2), "estimated_value": 500.0})
    found = run(detectors.detect_web_enquiries(db, TENANT))
    assert len(found) == 1
    assert found[0]["value"] == 500.0
    assert found[0]["external_identity"]["value"] == "sam@client.test"


def test_a_web_enquiry_someone_replied_to_is_not_detected(env):
    db, _ = env
    enquiry = insert(db, detectors.WEB_ENQUIRIES,
                     {"email": "sam@client.test", "status": "new",
                      "received_at": ago(days=2)})
    insert(db, "crm_activities", {"type": "email", "related_type": "web_enquiry",
                                  "related_id": enquiry["id"], "occurred_at": ago(days=1)})
    assert run(detectors.detect_web_enquiries(db, TENANT)) == []


def test_an_enquiry_already_marked_responded_is_not_detected(env):
    db, _ = env
    insert(db, detectors.WEB_ENQUIRIES, {"email": "x@y.test", "status": "responded",
                                         "received_at": ago(days=5)})
    assert run(detectors.detect_web_enquiries(db, TENANT)) == []


# ----------------------------------------------------------- quotes and estimates

def test_an_estimate_sent_and_never_decided_is_detected(env):
    db, _ = env
    insert(db, "estimates", {"title": "Roof repair", "status": "sent", "total": 2400.0,
                             "currency": "GBP", "created_at": ago(days=14),
                             "workspace_id": "ws_1"})
    found = run(detectors.detect_unanswered_estimates(db, TENANT))
    assert len(found) == 1
    assert found[0]["value"] == 2400.0
    assert found[0]["currency"] == "GBP"
    assert found[0]["record_collection"] == "estimates"


@pytest.mark.parametrize("status", ["approved", "rejected", "invoiced", "cancelled"])
def test_a_decided_estimate_is_not_chased(env, status):
    db, _ = env
    insert(db, "estimates", {"title": "Decided", "status": status, "total": 100.0,
                             "created_at": ago(days=30)})
    assert run(detectors.detect_unanswered_estimates(db, TENANT)) == []


def test_a_draft_estimate_nobody_sent_is_not_chased(env):
    db, _ = env
    insert(db, "estimates", {"title": "Draft", "status": "draft", "total": 100.0,
                             "created_at": ago(days=30)})
    assert run(detectors.detect_unanswered_estimates(db, TENANT)) == [], (
        "there is nothing to chase on a document that was never sent")


def test_an_unanswered_quote_is_a_separate_source_from_an_estimate(env):
    db, _ = env
    insert(db, "documents", {"title": "Fit-out quote", "kind": "quote", "status": "sent",
                             "total": 18000.0, "created_at": ago(days=20)})
    found = run(detectors.detect_unanswered_quotes(db, TENANT))
    assert len(found) == 1
    assert found[0]["type"] == detectors.TYPE_UNANSWERED_QUOTE
    assert detectors.SOURCE_FOR_TYPE[found[0]["type"]] == rc.SOURCE_UNANSWERED_QUOTE


def test_an_ordinary_document_is_not_treated_as_a_quote(env):
    db, _ = env
    insert(db, "documents", {"title": "Scope note", "kind": "document", "status": "sent",
                             "created_at": ago(days=30)})
    assert run(detectors.detect_unanswered_quotes(db, TENANT)) == []


# -------------------------------------------------------------------- no response

def _conversation_with(db, *, statuses, reply_days_ago=None, tenant_id=TENANT,
                       recovery_case_id=None):
    conversation = run(cv.create_conversation(
        db, tenant_id=tenant_id, channel=cv.CHANNEL_EMAIL, actor="user@acme.test",
        subject="Following up", contact_id="ct_1", recovery_case_id=recovery_case_id))
    for status, days in statuses:
        run(db[cv.MESSAGES].insert_one({
            "id": f"msg_{uuid.uuid4().hex[:10]}", "tenant_id": tenant_id,
            "conversation_id": conversation["id"], "channel": cv.CHANNEL_EMAIL,
            "direction": cv.OUTBOUND, "status": status, "body": "Hello",
            "created_at": ago(days=days), "sent_at": ago(days=days), "history": []}))
    if reply_days_ago is not None:
        run(db[cv.MESSAGES].insert_one({
            "id": f"msg_{uuid.uuid4().hex[:10]}", "tenant_id": tenant_id,
            "conversation_id": conversation["id"], "channel": cv.CHANNEL_EMAIL,
            "direction": cv.INBOUND, "status": cv.RECEIVED, "body": "Thanks",
            "created_at": ago(days=reply_days_ago), "history": []}))
    return conversation


def test_a_sent_message_that_was_never_answered_is_detected(env):
    db, _ = env
    _conversation_with(db, statuses=[(cv.SENT, 10)])
    found = run(detectors.detect_no_response(db, TENANT))
    assert len(found) == 1
    assert found[0]["messages_sent"] == 1


def test_a_conversation_that_got_a_reply_is_not_silence(env):
    db, _ = env
    _conversation_with(db, statuses=[(cv.SENT, 10)], reply_days_ago=3)
    assert run(detectors.detect_no_response(db, TENANT)) == []


@pytest.mark.parametrize("status", [cv.DRAFT, cv.PENDING_APPROVAL, cv.APPROVED,
                                    cv.BLOCKED, cv.FAILED, cv.OUTCOME_UNKNOWN])
def test_a_message_we_never_actually_sent_is_not_client_silence(env, status):
    """Our own inaction must not be counted as the client ignoring us."""
    db, _ = env
    _conversation_with(db, statuses=[(status, 10)])
    assert run(detectors.detect_no_response(db, TENANT)) == []


def test_a_conversation_already_part_of_a_recovery_is_not_re_detected(env):
    db, _ = env
    _conversation_with(db, statuses=[(cv.SENT, 10)], recovery_case_id="rc_existing")
    assert run(detectors.detect_no_response(db, TENANT)) == [], (
        "the recovery engine must not chase its own outreach")


# ------------------------------------------------------------------- appointments

def test_a_cancelled_appointment_with_no_rebooking_is_detected(env):
    db, _ = env
    insert(db, "appointments", {"title": "Survey", "status": "cancelled",
                                "start_at": ago(days=3), "end_at": ago(days=3),
                                "company_id": "co_1"})
    found = run(detectors.detect_cancelled_appointments(db, TENANT))
    assert len(found) == 1
    assert found[0]["type"] == detectors.TYPE_APPOINTMENT_CANCELLED


def test_a_cancelled_appointment_that_was_rebooked_is_not_detected(env):
    db, _ = env
    insert(db, "appointments", {"title": "Survey", "status": "cancelled",
                                "start_at": ago(days=3), "company_id": "co_1"})
    insert(db, "appointments", {"title": "Survey (moved)", "status": "scheduled",
                                "start_at": ahead(days=2), "company_id": "co_1"})
    assert run(detectors.detect_cancelled_appointments(db, TENANT)) == []


def test_an_appointment_whose_time_passed_without_an_outcome_is_a_no_show(env):
    db, _ = env
    insert(db, "appointments", {"title": "Consultation", "status": "scheduled",
                                "start_at": ago(hours=6), "end_at": ago(hours=5)})
    found = run(detectors.detect_no_shows(db, TENANT))
    assert len(found) == 1
    assert "no recorded outcome" in found[0]["reason"]


def test_an_appointment_marked_completed_is_not_a_no_show(env):
    db, _ = env
    insert(db, "appointments", {"title": "Consultation", "status": "completed",
                                "start_at": ago(hours=6), "end_at": ago(hours=5)})
    assert run(detectors.detect_no_shows(db, TENANT)) == []


def test_an_appointment_that_only_just_ended_is_inside_the_grace_period(env):
    db, _ = env
    insert(db, "appointments", {"title": "Consultation", "status": "scheduled",
                                "start_at": ago(hours=1), "end_at": ago(hours=0)})
    assert run(detectors.detect_no_shows(db, TENANT)) == []


def test_a_future_appointment_is_never_a_no_show(env):
    db, _ = env
    insert(db, "appointments", {"title": "Next week", "status": "scheduled",
                                "start_at": ahead(days=7), "end_at": ahead(days=7)})
    assert run(detectors.detect_no_shows(db, TENANT)) == []


# --------------------------------------------------------------- external events

def test_a_recoverable_external_event_is_detected(env):
    db, _ = env
    insert(db, detectors.EXTERNAL_EVENTS,
           {"provider": "acme-crm", "kind": "deal_lost", "external_id": "d1",
            "occurred_at": ago(days=2), "summary": "Lost on price",
            "contact_email": "buyer@client.test", "value": 9000.0, "status": "new"})
    found = run(detectors.detect_external_crm_events(db, TENANT))
    assert len(found) == 1
    assert found[0]["value"] == 9000.0
    assert found[0]["external_identity"]["kind"] == rc.IDENTITY_EMAIL
    assert "acme-crm" in found[0]["reason"]


def test_an_undeclared_external_event_kind_is_ignored_rather_than_guessed_at(env):
    db, _ = env
    insert(db, detectors.EXTERNAL_EVENTS,
           {"provider": "acme-crm", "kind": "contact_viewed_page", "external_id": "d2",
            "occurred_at": ago(days=2), "status": "new"})
    assert run(detectors.detect_external_crm_events(db, TENANT)) == [], (
        "an unknown event is not an opportunity")


def test_an_already_processed_external_event_is_not_re_detected(env):
    db, _ = env
    insert(db, detectors.EXTERNAL_EVENTS,
           {"provider": "acme-crm", "kind": "deal_lost", "external_id": "d3",
            "occurred_at": ago(days=2), "status": "processed"})
    assert run(detectors.detect_external_crm_events(db, TENANT)) == []


# ------------------------------------------------ invariants across every lane

def _seed_one_of_everything(db, *, tenant_id=TENANT):
    # The conversation lane carries a contact reference, and `open_case` refuses a
    # reference the tenant does not own -- so the contact has to actually exist.
    insert(db, "contacts", {"id": "ct_1", "name": "Sam", "email": "sam@client.test"},
           tenant_id=tenant_id)
    insert(db, "companies", {"id": "co_x", "name": "Client Ltd"}, tenant_id=tenant_id)
    insert(db, detectors.CALL_LOGS, {"direction": "inbound", "from_number": "+441632970001",
                                     "outcome": "missed", "occurred_at": ago(hours=8)},
           tenant_id=tenant_id)
    insert(db, detectors.WEB_ENQUIRIES, {"email": "a@b.test", "status": "new",
                                         "received_at": ago(days=2)}, tenant_id=tenant_id)
    insert(db, "estimates", {"title": "E", "status": "sent", "total": 100.0,
                             "created_at": ago(days=14)}, tenant_id=tenant_id)
    insert(db, "documents", {"title": "Q", "kind": "quote", "status": "sent",
                             "total": 200.0, "created_at": ago(days=14)},
           tenant_id=tenant_id)
    _conversation_with(db, statuses=[(cv.SENT, 10)], tenant_id=tenant_id)
    insert(db, "appointments", {"title": "C", "status": "cancelled",
                                "start_at": ago(days=3), "company_id": "co_x"},
           tenant_id=tenant_id)
    insert(db, "appointments", {"title": "N", "status": "scheduled",
                                "start_at": ago(hours=6), "end_at": ago(hours=5)},
           tenant_id=tenant_id)
    insert(db, detectors.EXTERNAL_EVENTS,
           {"provider": "acme-crm", "kind": "deal_lost", "external_id": f"x{tenant_id}",
            "occurred_at": ago(days=2), "status": "new"}, tenant_id=tenant_id)


def test_every_lane_finds_its_source_in_one_sweep(env):
    db, queue = env
    _seed_one_of_everything(db)
    summary = run(detectors.run_detection(db, queue, TENANT))

    assert summary["detected"] == 8, summary["by_lane"]
    assert all(isinstance(count, int) and count >= 1
               for count in summary["by_lane"].values()), summary["by_lane"]
    assert summary["work_items_created"] == 8
    assert summary["recovery_cases_linked"] == 8


def test_detection_creates_internal_work_and_never_an_outbound_message(env):
    db, queue = env
    _seed_one_of_everything(db)
    before = run(db[cv.MESSAGES].count_documents(
        {"tenant_id": TENANT, "direction": cv.OUTBOUND}))
    run(detectors.run_detection(db, queue, TENANT))
    after = run(db[cv.MESSAGES].count_documents(
        {"tenant_id": TENANT, "direction": cv.OUTBOUND}))
    assert after == before, "a detector that sends has bypassed every governance gate"

    items = run(queue.list_items(tenant_id=TENANT, status="open",
                                 queue=detectors.QUEUE_NAME, limit=50))
    assert len(items) == 8
    assert all(item["payload"]["recovery_case_id"] for item in items)
    assert all(item["evidence"].get("reason") for item in items), (
        "every work item must carry the reason it exists")


def test_re_running_the_sweep_finds_the_same_cases_not_new_ones(env):
    db, queue = env
    _seed_one_of_everything(db)
    first = run(detectors.run_detection(db, queue, TENANT))
    second = run(detectors.run_detection(db, queue, TENANT))

    assert first["work_items_created"] == 8
    assert second["work_items_created"] == 0
    assert second["work_items_deduplicated"] == 8
    assert run(db[rc.COLLECTION].count_documents({"tenant_id": TENANT})) == 8


def test_no_lane_can_see_another_tenants_records(env):
    db, queue = env
    _seed_one_of_everything(db, tenant_id=OTHER_TENANT)
    summary = run(detectors.run_detection(db, queue, TENANT))
    assert summary["detected"] == 0, summary["by_lane"]
    assert run(db[rc.COLLECTION].count_documents({"tenant_id": TENANT})) == 0


def test_a_case_from_every_new_source_carries_its_citation_and_reason(env):
    db, queue = env
    _seed_one_of_everything(db)
    run(detectors.run_detection(db, queue, TENANT))
    cases = run(db[rc.COLLECTION].find({"tenant_id": TENANT}, {"_id": 0}).to_list(50))

    assert {case["source"] for case in cases} == {
        rc.SOURCE_MISSED_CALL, rc.SOURCE_WEB_ENQUIRY, rc.SOURCE_UNANSWERED_QUOTE,
        rc.SOURCE_UNANSWERED_ESTIMATE, rc.SOURCE_NO_RESPONSE,
        rc.SOURCE_APPOINTMENT_CANCELLED, rc.SOURCE_APPOINTMENT_NO_SHOW,
        rc.SOURCE_EXTERNAL_CRM_EVENT}
    for case in cases:
        assert case["reason"], "a case with no stated reason is not explainable"
        assert case["source_event_id"], "a case must cite the record it came from"
        assert case["evidence"].get("record_collection"), (
            "the citation must name the collection, not just an id")
        assert case["confirmed_value"] is None, (
            "detection never confirms revenue; it only ever proposes potential")


def test_a_detection_that_cannot_open_a_case_is_reported_not_dropped(env):
    """A stale reference must not cost the rest of the sweep, or hide itself."""
    db, queue = env
    _conversation_with(db, statuses=[(cv.SENT, 10)])   # contact ct_1 does not exist
    summary = run(detectors.run_detection(db, queue, TENANT))
    assert summary["detected"] == 1
    assert summary["work_items_created"] == 0
    assert summary["rejected"] and "ct_1" in summary["rejected"][0]["error"]


def test_one_broken_lane_does_not_stop_the_others(env, monkeypatch):
    db, queue = env
    _seed_one_of_everything(db)

    async def broken(*args, **kwargs):
        raise RuntimeError("phone system unreachable")

    monkeypatch.setattr(detectors, "LANES",
                        tuple(("missed_calls", broken) if name == "missed_calls"
                              else (name, fn) for name, fn in detectors.LANES))
    summary = run(detectors.run_detection(db, queue, TENANT))
    assert summary["by_lane"]["missed_calls"]["error"]
    assert summary["detected"] == 7
