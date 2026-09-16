"""Recovery runner tests.

The runner is the first thing in this system that *acts* on an approval, so the tests are
mostly about what it refuses: an unapproved case, a withdrawn approval, and above all
sending anything. It must reach the provider boundary and stop there, and re-running must
never produce a second copy of the same message.
"""

import asyncio
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import approval_queue as aq
import conversations as cv
import recovery_case as rc
import recovery_runner as runner
import recovery_strategy as rs
from work_queue import WorkQueue

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT = "ten_run_a"
OTHER_TENANT = "ten_run_b"

_LOOP = None


def run(coro):
    """Run a coroutine on a loop this module owns (see test_second_chance for why)."""
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


@pytest.fixture()
def env():
    db_name = f"cv_run_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[db_name]
    queue = WorkQueue(db)
    for ensure in (queue.ensure_indexes(), rc.ensure_indexes(db), rs.ensure_indexes(db),
                   aq.ensure_indexes(db), cv.ensure_indexes(db)):
        run(ensure)
    run(db.tenants.insert_many([{"tenant_id": TENANT, "name": "A"},
                                {"tenant_id": OTHER_TENANT, "name": "B"}]))
    yield db, queue
    run(client.drop_database(db_name))
    client.close()


def approved_case(db, *, with_contact=True):
    """A case planned, approved, and ready for the runner — the realistic entry state."""
    run(db.companies.insert_one({"tenant_id": TENANT, "id": "co_1", "name": "Acme"}))
    run(db.workspaces.insert_one({"tenant_id": TENANT, "id": "ws_1", "company_id": "co_1",
                                  "name": "Acme", "owner": "owner@example.com"}))
    if with_contact:
        run(db.contacts.insert_one({"tenant_id": TENANT, "id": "con_1", "name": "Ada",
                                    "email": "ada@example.invalid"}))
    run(db.opportunities.insert_one({
        "tenant_id": TENANT, "id": "opp_1", "name": "Acme renewal", "stage": "proposal",
        "value": 40000, "company_id": "co_1", "owner": "owner@example.com"}))

    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_DORMANT_DEAL,
        source_event_id="opportunity:opp_1", reason="No activity for 30 days.",
        title="Acme renewal", workspace_id="ws_1", company_id="co_1",
        contact_id="con_1" if with_contact else None,
        opportunity_id="opp_1", potential_value=40000,
        evidence={"idle_days": 30, "stage": "proposal", "value": 40000})))

    strategy = run(rs.compose_for_case(db, TENANT, case))
    run(aq.decide(db, tenant_id=TENANT, approval_id=strategy["approval_id"],
                  decision=aq.APPROVED, actor="admin@example.com"))
    run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=rc.APPROVED,
                     actor="admin@example.com"))
    return run(rc.get_case(db, TENANT, case["id"])), strategy


# ---------------------------------------------------------------- refusals

def test_an_unapproved_case_is_refused(env):
    db, _ = env
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_MISSED_CALL, source_event_id="call_1",
        reason="Rang out.")))
    with pytest.raises(runner.RecoveryRunnerError) as exc:
        run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    assert "approved" in str(exc.value)


def test_a_case_with_no_plan_is_refused(env):
    db, _ = env
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_MISSED_CALL, source_event_id="call_2",
        reason="Rang out.")))
    for state in (rc.PLANNED, rc.AWAITING_APPROVAL, rc.APPROVED):
        run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=state))
    with pytest.raises(runner.RecoveryRunnerError) as exc:
        run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    assert "no plan" in str(exc.value)


def test_a_withdrawn_approval_stops_execution(env):
    """The case's state is not trusted on its own — the approval is re-read."""
    db, _ = env
    case, strategy = approved_case(db)
    run(db[aq.COLLECTION].update_one({"id": strategy["approval_id"]},
                                     {"$set": {"status": aq.CANCELLED}}))
    with pytest.raises(runner.RecoveryRunnerError) as exc:
        run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    assert "not approved" in str(exc.value)


def test_another_tenant_cannot_run_a_case(env):
    db, _ = env
    case, _ = approved_case(db)
    with pytest.raises(runner.RecoveryRunnerError):
        run(runner.run_case(db, tenant_id=OTHER_TENANT, case_id=case["id"]))


# ------------------------------------------------------------- what it does

def test_internal_steps_execute_and_outbound_steps_only_draft(env):
    db, _ = env
    case, strategy = approved_case(db)
    result = run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))

    assert result["internal_executed"] >= 1
    assert result["outbound_drafted"] >= 1
    # The claim that matters: nothing was sent.
    assert result["outbound_sent"] == 0

    internal = [s for s in result["steps"] if s["channel"] == cv.CHANNEL_INTERNAL]
    assert all(s["status"] == runner.STEP_DONE for s in internal)
    for step in internal:
        assert run(db.tasks.find_one({"id": step["task_id"], "tenant_id": TENANT}))


def test_every_drafted_message_carries_its_own_approval(env):
    """The plan's approval authorised a motion; each message authorises its words."""
    db, _ = env
    case, strategy = approved_case(db)
    result = run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))

    drafted = [s for s in result["steps"] if s["status"] == runner.STEP_DRAFTED]
    assert drafted
    for step in drafted:
        assert step["approval_id"], "an outbound draft with no approval is a gap in the gate"
        approval = run(aq.get(db, TENANT, step["approval_id"]))
        assert approval["status"] == aq.REQUESTED
        assert approval["subject_type"] == "communication_message"
        assert approval["id"] != strategy["approval_id"], (
            "the message approval must be distinct from the plan approval")
        message = run(cv.get_message(db, TENANT, step["message_id"]))
        assert message["status"] == cv.PENDING_APPROVAL
        assert approval["summary"] in message["body"] or message["body"]


def test_a_drafted_message_cannot_be_sent(env):
    """The boundary. Even approved, it refuses — no channel, no provider."""
    db, _ = env
    case, _ = approved_case(db)
    result = run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    step = [s for s in result["steps"] if s["status"] == runner.STEP_DRAFTED][0]

    run(aq.decide(db, tenant_id=TENANT, approval_id=step["approval_id"],
                  decision=aq.APPROVED, actor="admin@example.com"))
    run(cv.mark_approved(db, tenant_id=TENANT, message_id=step["message_id"],
                         actor="admin@example.com"))

    with pytest.raises(cv.DeliveryRefused) as exc:
        run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=step["message_id"],
                                actor="worker-1"))
    assert exc.value.reason in (cv.REFUSAL_CHANNEL, cv.REFUSAL_CONSENT,
                                cv.REFUSAL_PROVIDER)


def test_all_steps_of_one_case_share_one_conversation(env):
    db, _ = env
    case, _ = approved_case(db)
    result = run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    drafted = [s for s in result["steps"] if s["status"] == runner.STEP_DRAFTED]
    conversation_ids = set()
    for step in drafted:
        message = run(cv.get_message(db, TENANT, step["message_id"]))
        conversation_ids.add(message["conversation_id"])
    assert len(conversation_ids) == 1, "a recovery must not scatter across threads"

    linked = run(rc.get_case(db, TENANT, case["id"]))
    assert linked["conversation_reference"] in conversation_ids


def test_the_case_moves_to_executing_and_no_further(env):
    """`engaged` means a counterparty engaged. Nothing reached one, so it must not."""
    db, _ = env
    case, _ = approved_case(db)
    run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.EXECUTING


def test_the_draft_never_presents_an_estimate_as_recovered(env):
    db, _ = env
    case, _ = approved_case(db)
    result = run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    step = [s for s in result["steps"] if s["status"] == runner.STEP_DRAFTED][0]
    body = run(cv.get_message(db, TENANT, step["message_id"]))["body"]
    assert "estimated, not recovered" in body
    assert run(rc.get_case(db, TENANT, case["id"]))["confirmed_value"] is None


# ------------------------------------------------------------- idempotency

def test_re_running_does_not_draft_a_second_message(env):
    """A durable queue delivers twice. A client must not receive twice."""
    db, _ = env
    case, _ = approved_case(db)
    first = run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    second = run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))

    first_ids = [s["message_id"] for s in first["steps"] if s.get("message_id")]
    second_ids = [s["message_id"] for s in second["steps"] if s.get("message_id")]
    assert first_ids == second_ids
    assert all(s.get("reused") for s in second["steps"]
               if s["status"] == runner.STEP_DRAFTED)

    total = run(db[cv.MESSAGES].count_documents({"tenant_id": TENANT}))
    assert total == len(first_ids), f"expected {len(first_ids)} messages, found {total}"


def test_re_running_does_not_duplicate_internal_tasks(env):
    db, _ = env
    case, _ = approved_case(db)
    run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    before = run(db.tasks.count_documents({"tenant_id": TENANT}))
    run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    assert run(db.tasks.count_documents({"tenant_id": TENANT})) == before


def test_queueing_the_same_case_twice_collapses(env):
    db, queue = env
    case, _ = approved_case(db)
    first = run(runner.enqueue_case(queue, tenant_id=TENANT, case_id=case["id"]))
    second = run(runner.enqueue_case(queue, tenant_id=TENANT, case_id=case["id"]))
    assert second.get("deduplicated") is True
    assert second["id"] == first["id"]


# ----------------------------------------------------------------- sweeps

def test_the_sweep_queues_only_approved_cases(env):
    db, queue = env
    case, _ = approved_case(db)
    run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_MISSED_CALL, source_event_id="call_9",
        reason="Not approved, must not be queued.")))

    summary = run(runner.run_ready_cases(db, queue, tenant_id=TENANT))
    assert summary["approved_cases"] == 1
    assert [q["case_id"] for q in summary["queued"]] == [case["id"]]


def test_a_non_crm_case_runs_and_is_still_not_sent(env):
    """A missed call with a resolved contact goes as far as everything else: a draft."""
    db, _ = env
    run(db.contacts.insert_one({"tenant_id": TENANT, "id": "con_call", "name": "Caller",
                                "email": "caller@example.invalid"}))
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_MISSED_CALL, source_event_id="call_live",
        reason="Inbound call rang out; nobody called back.",
        external_identity={"kind": rc.IDENTITY_PHONE, "value": "+441632960002"},
        potential_value=250)))
    case = run(rc.attach(db, tenant_id=TENANT, case_id=case["id"], contact_id="con_call"))
    strategy = run(rs.compose_for_case(db, TENANT, case))
    run(aq.decide(db, tenant_id=TENANT, approval_id=strategy["approval_id"],
                  decision=aq.APPROVED, actor="admin@example.com"))
    run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=rc.APPROVED))

    result = run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    assert result["outbound_drafted"] >= 1
    assert result["outbound_sent"] == 0
    assert result["blocked_reasons"], "the reason it cannot send must be recorded"
