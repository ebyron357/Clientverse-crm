"""Scheduled recovery follow-up (E-06).

A follow-up is the most consequential thing automation does on its own initiative: it
decides, with nobody asking, that a client should hear from us again. So most of what
follows is the list of situations where it must *not* do that, each asserted to stop
with its reason named -- and the one situation where it should, asserted to produce a
draft that still needs a person's approval to go anywhere.
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import approval_queue as aq
import conversations as cv
import recovery_case as rc
import recovery_followup as fu
import recovery_runner as runner
import recovery_strategy as rs
from work_queue import WorkQueue

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT = "ten_followup_a"
OTHER_TENANT = "ten_followup_b"
CLIENT_EMAIL = "grace@client.example"

_LOOP = None


def run(coro):
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


@pytest.fixture()
def db():
    db_name = f"cv_followup_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[db_name]
    for ensure in (WorkQueue(database).ensure_indexes(), rc.ensure_indexes(database),
                   rs.ensure_indexes(database), aq.ensure_indexes(database),
                   cv.ensure_indexes(database), fu.ensure_indexes(database)):
        run(ensure)
    run(database.tenants.insert_many([{"tenant_id": TENANT, "name": "A"},
                                      {"tenant_id": OTHER_TENANT, "name": "B"}]))
    for tenant in (TENANT, OTHER_TENANT):
        run(database.integration_connections.insert_one(
            {"tenant_id": tenant, "provider": "gmail", "status": "active"}))
        run(database.integrations.insert_one(
            {"tenant_id": tenant, "name": "Gmail", "status": "CONNECTED"}))
    yield database
    run(client.drop_database(db_name))
    client.close()


class AcceptingProvider:
    channel = cv.CHANNEL_EMAIL
    name = "gmail"

    def __init__(self):
        self.sent = []

    async def send(self, *, message, conversation, idempotency_key):
        self.sent.append(message["id"])
        return cv.DeliveryResult(provider_message_id=f"gmail-{uuid.uuid4().hex[:8]}",
                                 detail={"thread_id": "thr-1"})


@pytest.fixture()
def registry():
    registry = cv.ProviderRegistry()
    registry.register(AcceptingProvider())
    return registry


def approve(db, message_id, tenant_id=TENANT):
    message = run(cv.get_message(db, tenant_id, message_id))
    run(aq.decide(db, tenant_id=tenant_id, approval_id=message["approval_id"],
                  decision=aq.APPROVED, actor="admin@example.com"))
    return run(cv.mark_approved(db, tenant_id=tenant_id, message_id=message_id,
                                actor="admin@example.com"))


def send(db, registry, message_id, *, days_ago=0, tenant_id=TENANT):
    """Approve and send, then backdate the send so the cadence can be tested."""
    approve(db, message_id, tenant_id)
    sent = run(cv.attempt_delivery(db, tenant_id=tenant_id, message_id=message_id,
                                   actor="admin@example.com", registry=registry))
    assert sent["status"] == cv.SENT
    when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    run(db[cv.MESSAGES].update_one({"id": message_id}, {"$set": {"sent_at": when}}))
    return sent


def contacted_case(db, registry, *, days_ago=4, tenant_id=TENANT):
    """A case whose first outreach reached the client `days_ago` days ago."""
    suffix = uuid.uuid4().hex[:6]
    run(db.contacts.insert_one({"tenant_id": tenant_id, "id": f"con_{suffix}",
                                "name": "Grace", "email": CLIENT_EMAIL}))
    run(db.opportunities.insert_one({
        "tenant_id": tenant_id, "id": f"opp_{suffix}", "name": "Renewal",
        "stage": "proposal", "value": 20000}))
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=tenant_id, source=rc.SOURCE_DORMANT_DEAL,
        source_event_id=f"opportunity:opp_{suffix}", reason="No activity for 30 days.",
        title="Renewal", contact_id=f"con_{suffix}", opportunity_id=f"opp_{suffix}",
        potential_value=20000, evidence={"idle_days": 30, "stage": "proposal",
                                         "value": 20000})))
    strategy = run(rs.compose_for_case(db, tenant_id, case))
    run(aq.decide(db, tenant_id=tenant_id, approval_id=strategy["approval_id"],
                  decision=aq.APPROVED, actor="admin@example.com"))
    run(rs.set_state(db, tenant_id, strategy["id"], state=rs.STATE_APPROVED,
                     actor="admin@example.com"))
    result = run(runner.run_case(db, tenant_id=tenant_id, case_id=case["id"]))
    first = [s for s in result["steps"] if s["status"] == runner.STEP_DRAFTED
             and s["channel"] == cv.CHANNEL_EMAIL][0]["message_id"]
    message = run(cv.get_message(db, tenant_id, first))
    run(cv.record_consent(db, tenant_id=tenant_id,
                          conversation_id=message["conversation_id"],
                          state=cv.CONSENT_GRANTED, actor="admin@example.com",
                          basis="Client asked to be kept informed by email."))
    send(db, registry, first, days_ago=days_ago, tenant_id=tenant_id)
    return run(rc.get_case(db, tenant_id, case["id"])), message["conversation_id"]


def verdict_for(db, case_id, tenant_id=TENANT):
    preview = run(fu.preview(db, tenant_id))
    return next(v for v in preview["cases"] if v["case_id"] == case_id)


# ------------------------------------------------------------------ the cadence

def test_a_case_contacted_recently_is_not_due_yet(db, registry):
    case, _ = contacted_case(db, registry, days_ago=1)
    verdict = verdict_for(db, case["id"])
    assert verdict["status"] == fu.NOT_DUE
    assert verdict["due_at"] and verdict["last_contact_at"]


def test_no_reply_after_the_cadence_drafts_a_follow_up_that_still_needs_approval(db, registry):
    case, conversation_id = contacted_case(db, registry, days_ago=4)
    assert verdict_for(db, case["id"])["status"] == fu.DUE

    summary = run(fu.run_for_tenant(db, TENANT))
    assert summary["by_status"].get(fu.DRAFTED) == 1
    assert summary["sent"] == 0
    drafted = summary["drafted"][0]
    message = run(cv.get_message(db, TENANT, drafted["message_id"]))
    assert message["conversation_id"] == conversation_id, "the follow-up stays on the thread"
    assert message["status"] == cv.PENDING_APPROVAL
    assert message["to_address"] == CLIENT_EMAIL
    assert message["subject"].startswith("Re: ")
    assert message["idempotency_key"] == fu.followup_key(case["id"], 1)
    assert "follow-up 1 of 2" in message["body"]
    assert "has not been sent" in message["body"]
    approval = run(aq.get(db, TENANT, message["approval_id"]))
    assert approval["requester_kind"] == aq.REQUESTER_AGENT
    assert approval["status"] == aq.REQUESTED


def test_a_second_sweep_does_not_stack_a_second_draft(db, registry):
    case, _ = contacted_case(db, registry, days_ago=4)
    run(fu.run_for_tenant(db, TENANT))
    again = run(fu.run_for_tenant(db, TENANT))
    assert again["drafted"] == []
    assert verdict_for(db, case["id"])["status"] == fu.PREVIOUS_PENDING


def test_drafting_is_idempotent_on_its_key(db, registry):
    case, _ = contacted_case(db, registry, days_ago=4)
    verdict = verdict_for(db, case["id"])
    first = run(fu.draft_followup(db, TENANT, case, verdict))
    second = run(fu.draft_followup(db, TENANT, case, verdict))
    assert second["id"] == first["id"] and second["deduplicated"] is True


def test_the_cadence_restarts_from_the_last_follow_up_that_reached_the_client(db, registry):
    case, _ = contacted_case(db, registry, days_ago=10)
    drafted = run(fu.run_for_tenant(db, TENANT))["drafted"][0]
    send(db, registry, drafted["message_id"], days_ago=1)
    verdict = verdict_for(db, case["id"])
    assert verdict["status"] == fu.NOT_DUE, "one day after follow-up 1, follow-up 2 waits"
    assert verdict["followups_drafted"] == 1


def test_the_limit_stops_follow_ups(db, registry):
    case, _ = contacted_case(db, registry, days_ago=20)
    for _ in range(2):
        drafted = run(fu.run_for_tenant(db, TENANT))["drafted"][0]
        send(db, registry, drafted["message_id"], days_ago=5)
    verdict = verdict_for(db, case["id"])
    assert verdict["status"] == fu.LIMIT_REACHED
    assert run(fu.run_for_tenant(db, TENANT))["drafted"] == []


# ------------------------------------------------------------------ every stop

def test_a_reply_stops_follow_ups(db, registry):
    case, conversation_id = contacted_case(db, registry, days_ago=4)
    run(cv.record_inbound(db, tenant_id=TENANT, conversation_id=conversation_id,
                          body="Thanks, give me a week.", from_address=CLIENT_EMAIL,
                          provider="gmail", provider_message_id="gmail-reply-x"))
    verdict = verdict_for(db, case["id"])
    assert verdict["status"] == fu.REPLIED
    assert run(fu.run_for_tenant(db, TENANT))["drafted"] == []


def test_withdrawn_consent_stops_follow_ups(db, registry):
    case, conversation_id = contacted_case(db, registry, days_ago=4)
    run(cv.record_consent(db, tenant_id=TENANT, conversation_id=conversation_id,
                          state=cv.CONSENT_WITHDRAWN, actor="admin@example.com"))
    assert verdict_for(db, case["id"])["status"] == fu.CONSENT_NOT_GRANTED


def test_a_human_handoff_stops_follow_ups(db, registry):
    case, conversation_id = contacted_case(db, registry, days_ago=4)
    run(cv.handoff(db, tenant_id=TENANT, conversation_id=conversation_id,
                   to=cv.HANDLED_BY_HUMAN, actor="owner@example.com",
                   assignee="owner@example.com", reason="I know this client."))
    assert verdict_for(db, case["id"])["status"] == fu.HANDED_TO_HUMAN


def test_a_closed_thread_stops_follow_ups(db, registry):
    case, conversation_id = contacted_case(db, registry, days_ago=4)
    run(cv.set_status(db, tenant_id=TENANT, conversation_id=conversation_id,
                      status=cv.STATUS_CLOSED, actor="owner@example.com"))
    assert verdict_for(db, case["id"])["status"] == fu.CONVERSATION_CLOSED


def test_a_case_that_ended_is_not_followed_up(db, registry):
    case, _ = contacted_case(db, registry, days_ago=4)
    run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=rc.CLOSED))
    assert run(fu.preview(db, TENANT))["cases"] == [], "only active cases are considered"
    policy = run(fu.get_policy(db, TENANT))
    closed = run(rc.get_case(db, TENANT, case["id"]))
    assert run(fu.assess_case(db, TENANT, closed, policy))["status"] == fu.CASE_NOT_ACTIVE


def test_nothing_that_never_reached_the_client_is_followed_up(db, registry):
    """A case executing with its first message still awaiting approval has had no
    contact; there is nothing to follow up, however long it has been."""
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_DORMANT_DEAL, source_event_id="opportunity:x",
        reason="Idle.", title="Idle deal", potential_value=100,
        evidence={"idle_days": 30})))
    for state in (rc.PLANNED, rc.AWAITING_APPROVAL, rc.APPROVED, rc.EXECUTING):
        run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=state))
    assert verdict_for(db, case["id"])["status"] == fu.NO_CONTACT_YET


def test_a_tenant_can_turn_follow_ups_off(db, registry):
    case, _ = contacted_case(db, registry, days_ago=4)
    run(fu.set_policy(db, tenant_id=TENANT, cadence_days=3, max_followups=0,
                      actor="admin@example.com"))
    assert verdict_for(db, case["id"])["status"] == fu.DISABLED
    assert run(fu.run_for_tenant(db, TENANT))["drafted"] == []


def test_the_cadence_is_the_tenants_own(db, registry):
    case, _ = contacted_case(db, registry, days_ago=4)
    run(fu.set_policy(db, tenant_id=TENANT, cadence_days=7, max_followups=2,
                      actor="admin@example.com"))
    assert verdict_for(db, case["id"])["status"] == fu.NOT_DUE


@pytest.mark.parametrize("cadence, maximum", [(0, 2), (31, 2), (3, -1), (3, 6)])
def test_an_out_of_range_policy_is_refused(db, cadence, maximum):
    with pytest.raises(fu.FollowupPolicyError):
        run(fu.set_policy(db, tenant_id=TENANT, cadence_days=cadence,
                          max_followups=maximum, actor="admin@example.com"))


def test_the_default_policy_is_reported_until_one_is_set(db):
    policy = run(fu.get_policy(db, TENANT))
    assert policy["cadence_days"] == fu.DEFAULT_CADENCE_DAYS
    assert policy["max_followups"] == fu.DEFAULT_MAX_FOLLOWUPS
    assert policy["updated_by"] is None


# ------------------------------------------------------------------ tenancy

def test_a_sweep_never_touches_another_tenants_cases(db, registry):
    case_b, _ = contacted_case(db, registry, days_ago=4, tenant_id=OTHER_TENANT)
    summary = run(fu.run_for_tenant(db, TENANT))
    assert summary["drafted"] == []
    assert verdict_for(db, case_b["id"], tenant_id=OTHER_TENANT)["status"] == fu.DUE
    # And another tenant's policy does not govern this one.
    run(fu.set_policy(db, tenant_id=TENANT, cadence_days=3, max_followups=0,
                      actor="admin@example.com"))
    assert verdict_for(db, case_b["id"], tenant_id=OTHER_TENANT)["status"] == fu.DUE


def test_the_all_tenant_sweep_drafts_for_each_tenant_on_its_own_thread(db, registry):
    case_a, conv_a = contacted_case(db, registry, days_ago=4)
    case_b, conv_b = contacted_case(db, registry, days_ago=4, tenant_id=OTHER_TENANT)
    result = run(fu.run_all_tenants(db))
    assert result["drafted"] == 2
    for tenant_id, conversation_id in ((TENANT, conv_a), (OTHER_TENANT, conv_b)):
        drafts = [m for m in run(cv.list_messages(db, tenant_id, conversation_id))
                  if str(m.get("idempotency_key") or "").endswith(":followup:1")]
        assert len(drafts) == 1


# ------------------------------------------------------------------ the API

def test_the_follow_up_api_is_authenticated_validated_and_tenant_scoped():
    import requests

    base = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/")

    def register(label):
        response = requests.post(f"{base}/api/auth/register", json={
            "email": f"followup_{label}_{uuid.uuid4().hex[:8]}@example.com",
            "password": "FollowupApi2026!", "name": f"Followup {label}"}, timeout=30)
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['token']}"}

    a, b = register("a"), register("b")
    assert requests.get(f"{base}/api/recovery-followups", timeout=30).status_code == 401

    preview = requests.get(f"{base}/api/recovery-followups", headers=a, timeout=30)
    assert preview.status_code == 200
    assert preview.json()["cases"] == []
    assert preview.json()["policy"]["cadence_days"] == fu.DEFAULT_CADENCE_DAYS

    for bad in ({"cadence_days": 0, "max_followups": 1},
                {"cadence_days": 3, "max_followups": 9}):
        refused = requests.put(f"{base}/api/recovery-followups/policy", headers=a,
                               json=bad, timeout=30)
        assert refused.status_code == 422, bad

    saved = requests.put(f"{base}/api/recovery-followups/policy", headers=a,
                         json={"cadence_days": 5, "max_followups": 1}, timeout=30)
    assert saved.status_code == 200
    assert saved.json()["cadence_days"] == 5 and saved.json()["max_followups"] == 1

    other = requests.get(f"{base}/api/recovery-followups/policy", headers=b, timeout=30)
    assert other.json()["cadence_days"] == fu.DEFAULT_CADENCE_DAYS, \
        "one tenant's policy must not govern another"

    ran = requests.post(f"{base}/api/recovery-followups/run", headers=a, timeout=30)
    assert ran.status_code == 200 and ran.json()["sent"] == 0
