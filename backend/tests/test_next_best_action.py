"""Next Best Action service tests.

The capability this replaces was a client-side strip. These tests hold the backend to
what the canonical governing document actually requires: tenant-scoped records,
deterministic rules, cited evidence, priority ordering, lifecycle state, and feedback
that generation does not trample.
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import next_best_action as nba
import second_chance
from work_queue import WorkQueue

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT = "ten_nba_a"
OTHER_TENANT = "ten_nba_b"


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


def iso(delta_days=0):
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).isoformat()


@pytest.fixture()
def db_env():
    db_name = f"cv_nba_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[db_name]
    run(nba.ensure_indexes(db))
    run(db.tenants.insert_many([{"tenant_id": TENANT}, {"tenant_id": OTHER_TENANT}]))
    yield db
    run(client.drop_database(db_name))
    client.close()


def test_breached_commitment_produces_a_critical_recommendation(db_env):
    run(db_env.commitments.insert_one({
        "id": "cmt_1", "tenant_id": TENANT, "title": "Deliver migration plan",
        "status": "breached", "owner": "ae@example.com", "workspace_id": "ws_1",
        "due_date": iso(-2),
    }))
    run(nba.generate(db_env, TENANT))
    items = run(nba.list_recommendations(db_env, TENANT))
    assert len(items) == 1
    assert items[0]["action_type"] == nba.ACTION_RESOLVE_COMMITMENT
    assert items[0]["priority"] == nba.PRIORITY_CRITICAL
    assert items[0]["source_refs"] == ["commitment:cmt_1"]
    assert "breached" in items[0]["reason"]


def test_pending_approval_and_overdue_task_are_recommended(db_env):
    run(db_env.approvals.insert_one({
        "id": "apr_1", "tenant_id": TENANT, "title": "Approve statement of work",
        "status": "requested", "workspace_id": "ws_1", "created_at": iso(-1),
    }))
    run(db_env.tasks.insert_one({
        "id": "task_1", "tenant_id": TENANT, "title": "Send kickoff deck",
        "status": "open", "due_date": iso(-4), "workspace_id": "ws_1",
    }))
    run(nba.generate(db_env, TENANT))
    types = {i["action_type"] for i in run(nba.list_recommendations(db_env, TENANT))}
    assert nba.ACTION_DECIDE_APPROVAL in types
    assert nba.ACTION_ADVANCE_TASK in types


def test_recommendations_are_ordered_by_priority(db_env):
    run(db_env.commitments.insert_one({
        "id": "cmt_crit", "tenant_id": TENANT, "title": "Breached", "status": "breached",
        "due_date": iso(-1),
    }))
    run(db_env.tasks.insert_one({
        "id": "task_med", "tenant_id": TENANT, "title": "Overdue task", "status": "open",
        "due_date": iso(-1),
    }))
    run(nba.generate(db_env, TENANT))
    items = run(nba.list_recommendations(db_env, TENANT))
    priorities = [i["priority"] for i in items]
    assert priorities == sorted(priorities)
    assert items[0]["action_type"] == nba.ACTION_RESOLVE_COMMITMENT


def test_second_chance_work_items_surface_as_recommendations(db_env):
    queue = WorkQueue(db_env)
    run(queue.ensure_indexes())
    run(db_env.opportunities.insert_one({
        "id": "opp_1", "tenant_id": TENANT, "title": "Dormant renewal", "stage": "proposal",
        "created_at": iso(-90), "updated_at": iso(-45),
    }))
    run(second_chance.run_detection(db_env, queue, TENANT))
    run(nba.generate(db_env, TENANT))
    items = run(nba.list_recommendations(db_env, TENANT))
    stalled = [i for i in items if i["action_type"] == nba.ACTION_RECOVER_STALLED_LEAD]
    assert len(stalled) == 1
    assert any(ref.startswith("opportunity:") for ref in stalled[0]["source_refs"])
    assert stalled[0]["reason"]


def test_degraded_integration_and_unhealthy_workspace_are_recommended(db_env):
    run(db_env.integration_connections.insert_one({
        "id": "conn_1", "tenant_id": TENANT, "provider": "gmail", "status": "expired",
        "last_sync_at": iso(-3),
    }))
    run(db_env.workspaces.insert_one({
        "id": "ws_9", "tenant_id": TENANT, "name": "Harbor Logistics",
        "health": {"band": "at_risk", "score": 41},
    }))
    run(nba.generate(db_env, TENANT))
    types = {i["action_type"] for i in run(nba.list_recommendations(db_env, TENANT))}
    assert nba.ACTION_REPAIR_INTEGRATION in types
    assert nba.ACTION_REVIEW_CLIENT_HEALTH in types


def test_generation_is_idempotent_and_preserves_feedback(db_env):
    run(db_env.commitments.insert_one({
        "id": "cmt_keep", "tenant_id": TENANT, "title": "Keep me", "status": "breached",
        "due_date": iso(-1),
    }))
    run(nba.generate(db_env, TENANT))
    item = run(nba.list_recommendations(db_env, TENANT))[0]
    run(nba.set_state(db_env, TENANT, item["id"], state=nba.STATE_DISMISSED,
                      actor="ops@example.com", outcome="not_relevant"))

    second = run(nba.generate(db_env, TENANT))
    assert second["created"] == 0
    assert second["refreshed"] == 1
    refreshed = run(db_env[nba.COLLECTION].find_one({"id": item["id"]}, {"_id": 0}))
    assert refreshed["state"] == nba.STATE_DISMISSED
    assert refreshed["outcome"] == "not_relevant"


def test_cleared_condition_retires_an_open_recommendation(db_env):
    run(db_env.commitments.insert_one({
        "id": "cmt_transient", "tenant_id": TENANT, "title": "Transient", "status": "breached",
        "due_date": iso(-1),
    }))
    run(nba.generate(db_env, TENANT))
    assert len(run(nba.list_recommendations(db_env, TENANT))) == 1

    run(db_env.commitments.update_one({"id": "cmt_transient"}, {"$set": {"status": "met"}}))
    result = run(nba.generate(db_env, TENANT))
    assert result["retired"] == 1
    assert run(nba.list_recommendations(db_env, TENANT, state="open")) == []


def test_feedback_states_are_recorded_with_actor_and_history(db_env):
    run(db_env.approvals.insert_one({
        "id": "apr_fb", "tenant_id": TENANT, "title": "Decide", "status": "requested",
    }))
    run(nba.generate(db_env, TENANT))
    item = run(nba.list_recommendations(db_env, TENANT))[0]

    accepted = run(nba.set_state(db_env, TENANT, item["id"], state=nba.STATE_ACCEPTED,
                                 actor="lead@example.com"))
    assert accepted["state"] == nba.STATE_ACCEPTED
    assert accepted["state_changed_by"] == "lead@example.com"

    completed = run(nba.set_state(db_env, TENANT, item["id"], state=nba.STATE_COMPLETED,
                                  actor="lead@example.com", outcome="approved",
                                  note="Signed off in review"))
    assert completed["outcome"] == "approved"
    assert completed["feedback_note"] == "Signed off in review"
    actions = [h["action"] for h in completed["history"]]
    assert actions == ["generated", nba.STATE_ACCEPTED, nba.STATE_COMPLETED]


def test_snoozed_recommendation_is_hidden_until_it_elapses(db_env):
    run(db_env.approvals.insert_one({
        "id": "apr_snooze", "tenant_id": TENANT, "title": "Later", "status": "requested",
    }))
    run(nba.generate(db_env, TENANT))
    item = run(nba.list_recommendations(db_env, TENANT))[0]
    run(nba.set_state(db_env, TENANT, item["id"], state=nba.STATE_SNOOZED,
                      actor="ops@example.com", snooze_minutes=120))
    assert run(nba.list_recommendations(db_env, TENANT, state="open")) == []

    run(db_env[nba.COLLECTION].update_one({"id": item["id"]},
                                          {"$set": {"snooze_until": iso(-1)}}))
    assert len(run(nba.list_recommendations(db_env, TENANT, state="open"))) == 1


def test_unsupported_state_is_rejected(db_env):
    run(db_env.approvals.insert_one({
        "id": "apr_bad", "tenant_id": TENANT, "title": "X", "status": "requested",
    }))
    run(nba.generate(db_env, TENANT))
    item = run(nba.list_recommendations(db_env, TENANT))[0]
    with pytest.raises(ValueError):
        run(nba.set_state(db_env, TENANT, item["id"], state="teleported",
                          actor="ops@example.com"))


def test_recommendations_are_tenant_isolated(db_env):
    run(db_env.commitments.insert_many([
        {"id": "cmt_a", "tenant_id": TENANT, "title": "Mine", "status": "breached",
         "due_date": iso(-1)},
        {"id": "cmt_b", "tenant_id": OTHER_TENANT, "title": "Theirs", "status": "breached",
         "due_date": iso(-1)},
    ]))
    run(nba.generate(db_env, TENANT))
    run(nba.generate(db_env, OTHER_TENANT))

    mine = run(nba.list_recommendations(db_env, TENANT))
    assert all(i["tenant_id"] == TENANT for i in mine)
    assert all("cmt_b" not in ref for i in mine for ref in i["source_refs"])

    theirs = run(nba.list_recommendations(db_env, OTHER_TENANT))
    theirs_id = theirs[0]["id"]
    # A cross-tenant state change must not find the record at all.
    assert run(nba.set_state(db_env, TENANT, theirs_id, state=nba.STATE_DISMISSED,
                             actor="attacker@example.com")) is None


def test_workspace_scoped_listing(db_env):
    run(db_env.commitments.insert_many([
        {"id": "cmt_ws1", "tenant_id": TENANT, "title": "WS1", "status": "breached",
         "workspace_id": "ws_1", "due_date": iso(-1)},
        {"id": "cmt_ws2", "tenant_id": TENANT, "title": "WS2", "status": "breached",
         "workspace_id": "ws_2", "due_date": iso(-1)},
    ]))
    run(nba.generate(db_env, TENANT))
    scoped = run(nba.list_recommendations(db_env, TENANT, workspace_id="ws_1"))
    assert len(scoped) == 1
    assert scoped[0]["workspace_id"] == "ws_1"


def test_summary_reports_open_counts_by_priority(db_env):
    run(db_env.commitments.insert_one({
        "id": "cmt_sum", "tenant_id": TENANT, "title": "Critical", "status": "breached",
        "due_date": iso(-1),
    }))
    run(db_env.tasks.insert_one({
        "id": "task_sum", "tenant_id": TENANT, "title": "Medium", "status": "open",
        "due_date": iso(-1),
    }))
    run(nba.generate(db_env, TENANT))
    result = run(nba.summary(db_env, TENANT))
    assert result["states"]["open"] == 2
    assert result["open_by_priority"]["critical"] == 1
    assert result["open_by_priority"]["medium"] == 1


def test_no_fabricated_confidence_is_emitted(db_env):
    """Rules are deterministic; a model-style confidence score would be invented."""
    run(db_env.commitments.insert_one({
        "id": "cmt_conf", "tenant_id": TENANT, "title": "X", "status": "breached",
        "due_date": iso(-1),
    }))
    run(nba.generate(db_env, TENANT))
    item = run(nba.list_recommendations(db_env, TENANT))[0]
    assert "confidence" not in item
    assert "score" not in item
