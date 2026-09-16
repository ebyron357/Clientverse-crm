"""Recovery strategy composer tests (§8 #8).

The composer's value depends on three claims being true, so each gets direct coverage:
the lane follows a stated rule over cited facts, no outbound step is ever marked ready
while its channel is unauthorised, and a changed recommendation cannot inherit the
approval given to the previous one.
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import approval_queue as aq
import recovery_strategy as rs
import second_chance
from work_queue import WorkQueue

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT = "ten_rcv_a"
OTHER_TENANT = "ten_rcv_b"

_LOOP = None


def run(coro):
    """Run a coroutine on a loop this module owns (see test_second_chance for why)."""
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


def iso(delta_days=0):
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).isoformat()


@pytest.fixture()
def env():
    db_name = f"cv_rcv_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[db_name]
    queue = WorkQueue(db)
    run(queue.ensure_indexes())
    run(aq.ensure_indexes(db))
    run(rs.ensure_indexes(db))
    run(db.tenants.insert_many([{"tenant_id": TENANT, "name": "A"},
                                {"tenant_id": OTHER_TENANT, "name": "B"}]))
    yield db, queue
    run(client.drop_database(db_name))
    client.close()


def candidate(**overrides):
    """A Second Chance work item in the shape the detectors actually produce."""
    item = {
        "id": f"wq_{uuid.uuid4().hex[:10]}",
        "tenant_id": TENANT,
        "type": second_chance.TYPE_STALLED_LEAD,
        "payload": {"record_id": "opp_1", "record_kind": "opportunity",
                    "title": "Acme renewal"},
        "evidence": {"idle_days": 21, "stage": "proposal", "value": 40000,
                     "company_id": None, "contact_id": None},
        "workspace_id": None,
    }
    for key, value in overrides.items():
        if key in ("payload", "evidence"):
            item[key] = {**item[key], **value}
        else:
            item[key] = value
    return item


def seed_owner_workspace(db, workspace_id="ws_1", owner="owner@example.com"):
    run(db.workspaces.insert_one({"tenant_id": TENANT, "id": workspace_id,
                                  "name": "Acme", "owner": owner}))
    return workspace_id


# ------------------------------------------------------------ channel authority

def test_no_channel_is_authorised_without_a_connection(env):
    db, _ = env
    channels = run(rs.authorized_channels(db, TENANT))
    assert channels[rs.CHANNEL_INTERNAL]["authorized"] is True
    assert channels[rs.CHANNEL_EMAIL]["authorized"] is False
    assert channels[rs.CHANNEL_SMS]["authorized"] is False
    assert channels[rs.CHANNEL_PHONE]["authorized"] is False


def test_a_connected_but_unconfigured_provider_is_not_authorised(env):
    db, _ = env
    run(db.integration_connections.insert_one(
        {"tenant_id": TENANT, "provider": "gmail", "status": "active"}))
    run(db.integrations.insert_one(
        {"tenant_id": TENANT, "name": "Gmail", "status": "REQUIRES_CONFIGURATION"}))
    email = run(rs.authorized_channels(db, TENANT))[rs.CHANNEL_EMAIL]
    assert email["authorized"] is False
    assert "not past configuration" in email["reason"]


def test_a_connected_and_configured_provider_is_authorised(env):
    db, _ = env
    run(db.integration_connections.insert_one(
        {"tenant_id": TENANT, "provider": "gmail", "status": "active"}))
    run(db.integrations.insert_one({"tenant_id": TENANT, "name": "Gmail", "status": "CONNECTED"}))
    assert run(rs.authorized_channels(db, TENANT))[rs.CHANNEL_EMAIL]["authorized"] is True


def test_a_disconnected_provider_is_not_authorised(env):
    db, _ = env
    run(db.integration_connections.insert_one(
        {"tenant_id": TENANT, "provider": "gmail", "status": "disconnected"}))
    run(db.integrations.insert_one({"tenant_id": TENANT, "name": "Gmail", "status": "CONNECTED"}))
    assert run(rs.authorized_channels(db, TENANT))[rs.CHANNEL_EMAIL]["authorized"] is False


def test_channel_authority_is_tenant_scoped(env):
    db, _ = env
    run(db.integration_connections.insert_one(
        {"tenant_id": OTHER_TENANT, "provider": "gmail", "status": "active"}))
    run(db.integrations.insert_one({"tenant_id": OTHER_TENANT, "name": "Gmail",
                                    "status": "CONNECTED"}))
    assert run(rs.authorized_channels(db, TENANT))[rs.CHANNEL_EMAIL]["authorized"] is False


# ------------------------------------------------------------- lane selection

def test_high_value_with_an_owner_goes_to_the_owner(env):
    db, _ = env
    ws = seed_owner_workspace(db)
    lane = rs.select_lane(candidate(), {"owner": "owner@example.com", "workspace_id": ws,
                                        "record_kind": "opportunity"})
    assert lane["lane"] == "owner_led_reengagement"
    assert lane["rule"] == "stalled_lead.high_value_or_late_stage"


def test_open_commitments_are_repaired_before_re_engagement(env):
    db, _ = env
    lane = rs.select_lane(candidate(), {"owner": "owner@example.com", "open_commitments": 2,
                                        "record_kind": "opportunity"})
    assert lane["lane"] == "commitment_repair_first"
    assert "open commitment" in lane["rationale"]


def test_dormant_low_value_goes_to_nurture(env):
    db, _ = env
    item = candidate(evidence={"idle_days": rs.DORMANT_DAYS + 5, "value": 500, "stage": "new"})
    lane = rs.select_lane(item, {"owner": "owner@example.com", "record_kind": "opportunity"})
    assert lane["lane"] == "dormant_nurture"


def test_a_known_contact_without_an_owner_gets_a_written_followup(env):
    db, _ = env
    item = candidate(evidence={"value": 5000, "stage": "qualified"})
    lane = rs.select_lane(item, {"contact_id": "con_1", "record_kind": "opportunity"})
    assert lane["lane"] == "written_followup"


def test_no_owner_and_no_contact_asks_a_human(env):
    db, _ = env
    item = candidate(evidence={"value": 5000, "stage": "qualified"})
    lane = rs.select_lane(item, {"record_kind": "opportunity"})
    assert lane["lane"] == "needs_human_triage"
    assert lane["rule"] == "insufficient_context"


def test_missed_commitment_repairs_the_promise(env):
    db, _ = env
    item = candidate(type=second_chance.TYPE_MISSED_FOLLOWUP,
                     evidence={"overdue_days": 4, "idle_days": None})
    lane = rs.select_lane(item, {"record_kind": "commitment"})
    assert lane["lane"] == "commitment_repair"


def test_missed_delivery_task_is_triaged_internally_first(env):
    db, _ = env
    item = candidate(type=second_chance.TYPE_MISSED_FOLLOWUP,
                     evidence={"overdue_days": 2, "idle_days": None})
    lane = rs.select_lane(item, {"record_kind": "task"})
    assert lane["lane"] == "delivery_recovery"
    assert lane["steps"][0]["channel"] == rs.CHANNEL_INTERNAL


def test_no_lane_carries_a_score_or_confidence(env):
    db, _ = env
    for context in ({"owner": "o@example.com"}, {"contact_id": "c"}, {}):
        lane = rs.select_lane(candidate(), {**context, "record_kind": "opportunity"})
        assert not any(k in lane for k in ("score", "confidence", "probability"))
        assert lane["rationale"] and lane["rule"]


# --------------------------------------------------------------- composition

def test_composed_strategy_blocks_every_unauthorised_step(env):
    db, queue = env
    seed_owner_workspace(db)
    item = candidate(workspace_id="ws_1")
    strategy = run(rs.compose_for_candidate(db, TENANT, item))

    assert strategy["lane"] == "owner_led_reengagement"
    assert strategy["executable"] is False
    outbound = [s for s in strategy["steps"] if s["channel"] != rs.CHANNEL_INTERNAL]
    assert outbound, "this lane is expected to contain an outbound step"
    assert all(s["status"] == "blocked" and s["blocked_reason"] for s in outbound)
    assert all(s["status"] == "ready"
               for s in strategy["steps"] if s["channel"] == rs.CHANNEL_INTERNAL)


def test_composition_raises_an_approval_request_and_sends_nothing(env):
    db, queue = env
    seed_owner_workspace(db)
    strategy = run(rs.compose_for_candidate(db, TENANT, candidate(workspace_id="ws_1")))

    approval = run(aq.get(db, TENANT, strategy["approval_id"]))
    assert approval["status"] == aq.REQUESTED
    assert approval["kind"] == "recovery_strategy"
    assert approval["requester_kind"] == aq.REQUESTER_AGENT
    assert approval["action"]["strategy_id"] == strategy["id"]
    assert approval["blocked_reasons"] == strategy["blocked_reasons"]
    # Nothing outbound was recorded anywhere.
    assert run(db.crm_communications.count_documents({})) == 0


def test_an_approved_but_blocked_strategy_still_cannot_execute(env):
    db, queue = env
    seed_owner_workspace(db)
    strategy = run(rs.compose_for_candidate(db, TENANT, candidate(workspace_id="ws_1")))
    run(aq.decide(db, tenant_id=TENANT, approval_id=strategy["approval_id"],
                  decision=aq.APPROVED, actor="admin@example.com"))
    with pytest.raises(aq.InvalidApprovalTransition):
        run(aq.consume(db, tenant_id=TENANT, approval_id=strategy["approval_id"],
                       actor="worker-1"))


def test_recomposing_an_unchanged_candidate_does_not_re_ask(env):
    db, queue = env
    seed_owner_workspace(db)
    item = candidate(workspace_id="ws_1")
    first = run(rs.compose_for_candidate(db, TENANT, item))
    second = run(rs.compose_for_candidate(db, TENANT, item))

    assert second["id"] == first["id"]
    assert second["approval_id"] == first["approval_id"]
    assert len(run(aq.list_requests(db, TENANT, status="all"))) == 1


def test_a_changed_recommendation_cannot_inherit_the_old_approval(env):
    db, queue = env
    seed_owner_workspace(db)
    item = candidate(workspace_id="ws_1")
    first = run(rs.compose_for_candidate(db, TENANT, item))

    # The account moves: an open commitment appears, so the lane must change.
    run(db.commitments.insert_one({"tenant_id": TENANT, "id": "cmt_1", "workspace_id": "ws_1",
                                   "status": "open", "title": "Send the revised scope"}))
    second = run(rs.compose_for_candidate(db, TENANT, item))

    assert second["lane"] == "commitment_repair_first"
    assert second["approval_id"] != first["approval_id"]
    old = run(aq.get(db, TENANT, first["approval_id"]))
    assert old["status"] == aq.CANCELLED


def test_facts_are_cited_to_a_record(env):
    db, queue = env
    ws = seed_owner_workspace(db)
    run(db.companies.insert_one({"tenant_id": TENANT, "id": "co_1", "name": "Acme Ltd"}))
    item = candidate(workspace_id=ws, evidence={"company_id": "co_1"})
    strategy = run(rs.compose_for_candidate(db, TENANT, item))

    assert strategy["facts"], "a strategy with no cited facts explains nothing"
    assert all("source" in fact for fact in strategy["facts"])
    assert any(fact["source"] == "company:co_1" for fact in strategy["facts"])


def test_context_gathering_stays_inside_the_tenant(env):
    db, queue = env
    run(db.companies.insert_one({"tenant_id": OTHER_TENANT, "id": "co_x", "name": "Other Co"}))
    item = candidate(evidence={"company_id": "co_x"})
    context = run(rs.gather_context(db, TENANT, item))
    assert "company_name" not in context


def test_sweep_composes_for_open_candidates_only(env):
    db, queue = env
    seed_owner_workspace(db)
    run(queue.enqueue(tenant_id=TENANT, queue=second_chance.QUEUE_NAME,
                      item_type=second_chance.TYPE_STALLED_LEAD,
                      payload={"record_id": "opp_1", "record_kind": "opportunity",
                               "title": "Acme renewal"},
                      evidence={"idle_days": 30, "stage": "proposal", "value": 40000},
                      dedupe_key="sc:opp_1", workspace_id="ws_1"))
    summary = run(rs.compose_for_tenant(db, queue, TENANT))
    assert summary["candidates_examined"] == 1
    assert summary["strategies_composed"] == 1
    assert summary["strategies_blocked"] == 1
    assert summary["errors"] == []


def test_strategy_state_follows_the_decision(env):
    db, queue = env
    seed_owner_workspace(db)
    strategy = run(rs.compose_for_candidate(db, TENANT, candidate(workspace_id="ws_1")))
    updated = run(rs.set_state(db, TENANT, strategy["id"], state=rs.STATE_REJECTED,
                               actor="admin@example.com"))
    assert updated["state"] == rs.STATE_REJECTED
    # A closed strategy releases its candidate so a later sweep may propose afresh.
    fresh = run(rs.compose_for_candidate(db, TENANT, candidate(workspace_id="ws_1")))
    assert fresh["id"] != strategy["id"]


def test_summary_reports_blocked_proposals(env):
    db, queue = env
    seed_owner_workspace(db)
    run(rs.compose_for_candidate(db, TENANT, candidate(workspace_id="ws_1")))
    summary = run(rs.summary(db, TENANT))
    assert summary["proposed"] == 1
    assert summary["proposed_blocked"] == 1
    assert summary["by_lane"]["owner_led_reengagement"] == 1


def test_listing_is_tenant_scoped(env):
    db, queue = env
    seed_owner_workspace(db)
    run(rs.compose_for_candidate(db, TENANT, candidate(workspace_id="ws_1")))
    assert run(rs.list_strategies(db, OTHER_TENANT)) == []
    assert len(run(rs.list_strategies(db, TENANT))) == 1


def test_an_approved_strategy_is_not_re_proposed_by_the_next_sweep(env):
    db, queue = env
    seed_owner_workspace(db)
    item = candidate(workspace_id="ws_1")
    strategy = run(rs.compose_for_candidate(db, TENANT, item))
    run(aq.decide(db, tenant_id=TENANT, approval_id=strategy["approval_id"],
                  decision=aq.APPROVED, actor="admin@example.com"))
    run(rs.set_state(db, TENANT, strategy["id"], state=rs.STATE_APPROVED,
                     actor="admin@example.com"))

    # Even if the account moves, an approved plan is not silently reset and re-asked.
    run(db.commitments.insert_one({"tenant_id": TENANT, "id": "cmt_2", "workspace_id": "ws_1",
                                   "status": "open", "title": "Something new"}))
    again = run(rs.compose_for_candidate(db, TENANT, item))
    assert again["id"] == strategy["id"]
    assert again["state"] == rs.STATE_APPROVED
    assert again["approval_id"] == strategy["approval_id"]
    assert run(aq.get(db, TENANT, strategy["approval_id"]))["status"] == aq.APPROVED
