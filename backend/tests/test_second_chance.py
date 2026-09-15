"""Second Chance detector tests.

Each lane is exercised against seeded CRM records so the rule, not a mock, decides
the outcome. The detectors must be deterministic, explainable, tenant-scoped, and
must not create outbound communication of any kind.
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import second_chance
from work_queue import WorkQueue

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT = "ten_sc_a"
OTHER_TENANT = "ten_sc_b"


_LOOP = None


def run(coro):
    """Run a coroutine on a loop this module owns.

    The suite runs under xdist with `--dist loadscope`, so several modules share one
    worker process. Relying on the ambient event loop makes these tests fail when an
    earlier module closes it; owning the loop here keeps them independent.
    """
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


def iso(delta_days=0, delta_hours=0):
    return (datetime.now(timezone.utc) + timedelta(days=delta_days, hours=delta_hours)).isoformat()


@pytest.fixture()
def env():
    db_name = f"cv_sc_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[db_name]
    queue = WorkQueue(db)
    run(queue.ensure_indexes())
    run(db.tenants.insert_many([{"tenant_id": TENANT, "name": "A"},
                                {"tenant_id": OTHER_TENANT, "name": "B"}]))
    yield db, queue
    run(client.drop_database(db_name))
    client.close()


# ----------------------------------------------------------- stalled leads

def test_stalled_lead_detected_after_threshold(env):
    db, queue = env
    run(db.opportunities.insert_one({
        "id": "opp_stale", "tenant_id": TENANT, "title": "Renewal — Northwind",
        "stage": "proposal", "value": 12000,
        "created_at": iso(-60), "updated_at": iso(-30),
    }))
    detections = run(second_chance.detect_stalled_leads(db, queue, TENANT))
    assert len(detections) == 1
    detection = detections[0]
    assert detection["record_id"] == "opp_stale"
    assert detection["idle_days"] >= 30
    assert "No qualifying activity" in detection["reason"]
    assert detection["stage"] == "proposal"


def test_recently_active_opportunity_is_not_stalled(env):
    db, queue = env
    run(db.opportunities.insert_one({
        "id": "opp_fresh", "tenant_id": TENANT, "title": "Active deal", "stage": "discovery",
        "created_at": iso(-60), "updated_at": iso(-2),
    }))
    assert run(second_chance.detect_stalled_leads(db, queue, TENANT)) == []


def test_recent_domain_event_counts_as_activity(env):
    db, queue = env
    run(db.opportunities.insert_one({
        "id": "opp_evented", "tenant_id": TENANT, "title": "Deal with activity",
        "stage": "negotiation", "created_at": iso(-90), "updated_at": iso(-45),
    }))
    run(db.domain_events.insert_one({
        "id": "evt_1", "tenant_id": TENANT, "resource_id": "opp_evented",
        "event_type": "opportunity.note_added", "timestamp": iso(-1),
    }))
    assert run(second_chance.detect_stalled_leads(db, queue, TENANT)) == []


def test_closed_opportunities_are_out_of_scope(env):
    db, queue = env
    run(db.opportunities.insert_many([
        {"id": "opp_won", "tenant_id": TENANT, "title": "Won", "stage": "closed_won",
         "created_at": iso(-90), "updated_at": iso(-90)},
        {"id": "opp_lost", "tenant_id": TENANT, "title": "Lost", "stage": "closed_lost",
         "created_at": iso(-90), "updated_at": iso(-90)},
    ]))
    assert run(second_chance.detect_stalled_leads(db, queue, TENANT)) == []


# ------------------------------------------------------- missed follow-ups

def test_overdue_commitment_is_a_missed_followup(env):
    db, queue = env
    run(db.commitments.insert_one({
        "id": "cmt_late", "tenant_id": TENANT, "title": "Send revised scope",
        "status": "open", "owner": "ae@example.com", "workspace_id": "ws_1",
        "due_date": iso(-5),
    }))
    detections = run(second_chance.detect_missed_followups(db, queue, TENANT))
    assert len(detections) == 1
    assert detections[0]["record_kind"] == "commitment"
    assert detections[0]["overdue_days"] >= 5
    assert "due" in detections[0]["reason"]


def test_resolved_commitment_is_not_a_missed_followup(env):
    db, queue = env
    run(db.commitments.insert_one({
        "id": "cmt_done", "tenant_id": TENANT, "title": "Delivered", "status": "met",
        "due_date": iso(-9),
    }))
    assert run(second_chance.detect_missed_followups(db, queue, TENANT)) == []


def test_grace_period_prevents_premature_detection(env):
    db, queue = env
    run(db.commitments.insert_one({
        "id": "cmt_justdue", "tenant_id": TENANT, "title": "Just due", "status": "open",
        "due_date": iso(delta_hours=-1),
    }))
    assert run(second_chance.detect_missed_followups(db, queue, TENANT, grace_hours=24)) == []


def test_overdue_task_is_a_missed_followup(env):
    db, queue = env
    run(db.tasks.insert_one({
        "id": "task_late", "tenant_id": TENANT, "title": "Prepare onboarding pack",
        "status": "open", "assignee": "csm@example.com", "workspace_id": "ws_2",
        "due_date": iso(-3),
    }))
    detections = run(second_chance.detect_missed_followups(db, queue, TENANT))
    assert [d["record_kind"] for d in detections] == ["task"]


# ---------------------------------------------------------- queue behaviour

def test_detections_become_deduplicated_work_items(env):
    db, queue = env
    run(db.opportunities.insert_one({
        "id": "opp_dedupe", "tenant_id": TENANT, "title": "Dormant deal", "stage": "proposal",
        "created_at": iso(-80), "updated_at": iso(-40),
    }))
    first = run(second_chance.run_detection(db, queue, TENANT))
    assert first["stalled_leads_detected"] == 1
    assert first["work_items_created"] == 1

    second = run(second_chance.run_detection(db, queue, TENANT))
    assert second["work_items_created"] == 0
    assert second["work_items_deduplicated"] == 1
    assert run(db.work_queue.count_documents({"tenant_id": TENANT})) == 1


def test_work_item_carries_explainable_evidence_and_source_ref(env):
    db, queue = env
    run(db.commitments.insert_one({
        "id": "cmt_evidence", "tenant_id": TENANT, "title": "Follow up on pricing",
        "status": "open", "due_date": iso(-7),
    }))
    run(second_chance.run_detection(db, queue, TENANT))
    item = run(db.work_queue.find_one({"tenant_id": TENANT}, {"_id": 0}))
    assert item["type"] == second_chance.TYPE_MISSED_FOLLOWUP
    assert item["source_ref"] == "commitment:cmt_evidence"
    assert item["payload"]["reason"]
    assert item["evidence"]["overdue_days"] >= 7


def test_detection_is_tenant_scoped(env):
    db, queue = env
    run(db.opportunities.insert_many([
        {"id": "opp_a", "tenant_id": TENANT, "title": "A", "stage": "proposal",
         "created_at": iso(-80), "updated_at": iso(-40)},
        {"id": "opp_b", "tenant_id": OTHER_TENANT, "title": "B", "stage": "proposal",
         "created_at": iso(-80), "updated_at": iso(-40)},
    ]))
    run(second_chance.run_detection(db, queue, TENANT))
    items = run(db.work_queue.find({}, {"_id": 0}).to_list(50))
    assert {i["tenant_id"] for i in items} == {TENANT}
    assert all(i["payload"]["record_id"] != "opp_b" for i in items)


def test_detection_creates_no_outbound_communication(env):
    """Detection is internal work only until an approved channel exists."""
    db, queue = env
    run(db.opportunities.insert_one({
        "id": "opp_quiet", "tenant_id": TENANT, "title": "Dormant", "stage": "proposal",
        "created_at": iso(-80), "updated_at": iso(-40),
    }))
    run(second_chance.run_detection(db, queue, TENANT))
    assert run(db.crm_communications.count_documents({})) == 0
    assert run(db.notifications.count_documents({})) == 0


def test_sweep_covers_every_tenant(env):
    db, queue = env
    run(db.opportunities.insert_many([
        {"id": "opp_x", "tenant_id": TENANT, "title": "X", "stage": "proposal",
         "created_at": iso(-80), "updated_at": iso(-40)},
        {"id": "opp_y", "tenant_id": OTHER_TENANT, "title": "Y", "stage": "proposal",
         "created_at": iso(-80), "updated_at": iso(-40)},
    ]))
    result = run(second_chance.run_detection_all_tenants(db, queue))
    assert result["tenants"] == 2
    tenants_with_items = run(db.work_queue.distinct("tenant_id"))
    assert set(tenants_with_items) == {TENANT, OTHER_TENANT}
