"""The fourth review round, as tests: what Second Chance detected, and what the runner did
with it. Each of these used to go wrong -- a dormant deal whose outreach had no
recipient, won and archived deals chased as stalled, stale records never examined, a
detection that outlived its cause, and a retry that stranded a draft without approval.
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import approval_queue as aq
import conversations as cv
import crm_core
import recovery_case as rc
import recovery_runner as runner
import recovery_strategy as rs
import second_chance as sc
from work_queue import WorkQueue

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT = "ten_dh_a"

_LOOP = None


def run(coro):
    """Run a coroutine on a loop this module owns (see test_second_chance for why)."""
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


def iso(days=0):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


@pytest.fixture()
def env():
    db_name = f"cv_dh_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[db_name]
    queue = WorkQueue(db)
    for ensure in (queue.ensure_indexes(), rc.ensure_indexes(db), rs.ensure_indexes(db),
                   aq.ensure_indexes(db), cv.ensure_indexes(db)):
        run(ensure)
    run(db.tenants.insert_one({"tenant_id": TENANT, "name": "A"}))
    yield db, queue
    run(client.drop_database(db_name))
    client.close()


def stale_deal(db, deal_id="opp_1", **fields):
    doc = {"tenant_id": TENANT, "id": deal_id, "name": "Acme renewal", "stage": "proposal",
           "value": 40000, "currency": "USD", "created_at": iso(-90), "updated_at": iso(-60),
           "archived_at": None, **fields}
    run(db.opportunities.insert_one(doc))
    return doc


# ------------------------------------------------------------- the deal's contact

def test_a_dormant_deal_carries_the_contact_it_was_created_with(env):
    db, queue = env
    run(db.companies.insert_one({"tenant_id": TENANT, "id": "co_1", "name": "Acme"}))
    run(db.contacts.insert_many([
        {"tenant_id": TENANT, "id": "ct_noemail", "name": "No Mail", "company_id": "co_1"},
        {"tenant_id": TENANT, "id": "ct_elsewhere", "name": "Other", "email": "o@x.example",
         "company_id": "co_other"},
        {"tenant_id": TENANT, "id": "ct_1", "name": "Ada", "email": "ada@x.example",
         "company_id": "co_1"}]))
    stale_deal(db, company_id="co_1", contact_ids=["ct_noemail", "ct_elsewhere", "ct_1"])

    [detection] = run(sc.detect_stalled_leads(db, queue, TENANT))
    assert detection["contact_id"] == "ct_1"

    run(sc.run_detection(db, queue, TENANT))
    case = run(db[rc.COLLECTION].find_one({"tenant_id": TENANT}))
    assert case["contact_id"] == "ct_1"


def test_the_planner_finds_the_deals_contact_when_the_detection_had_none(env):
    db, _ = env
    run(db.contacts.insert_one({"tenant_id": TENANT, "id": "ct_1", "name": "Ada",
                                "email": "ada@x.example"}))
    stale_deal(db, contact_ids=["ct_1"])
    candidate = {"id": "wq_1", "type": sc.TYPE_STALLED_LEAD,
                 "payload": {"record_id": "opp_1", "record_kind": "opportunity"},
                 "evidence": {"record_id": "opp_1", "idle_days": 60}}
    context = run(rs.gather_context(db, TENANT, candidate))
    assert context["contact_id"] == "ct_1" and context["contact_has_email"]


def test_a_deals_currency_travels_to_its_case(env):
    db, queue = env
    stale_deal(db, currency="EUR")
    run(sc.run_detection(db, queue, TENANT))
    case = run(db[rc.COLLECTION].find_one({"tenant_id": TENANT}))
    assert case["currency"] == "EUR"


# ------------------------------------------------------------- what counts as stalled

def test_won_closed_and_archived_deals_are_not_stalled_leads(env):
    db, queue = env
    run(db[crm_core.PIPELINES].insert_one({"tenant_id": TENANT, "id": "default", "stages": [
        {"key": "talking", "label": "Talking", "is_closed": False, "is_won": False},
        {"key": "signed", "label": "Signed", "is_closed": True, "is_won": True},
        {"key": "churned", "label": "Churned", "is_closed": True, "is_won": False}]}))
    stale_deal(db, "opp_signed", stage="signed")
    stale_deal(db, "opp_churned", stage="churned")
    stale_deal(db, "opp_archived", stage="talking", archived_at=iso(-1))
    stale_deal(db, "opp_live", stage="talking")

    detections = run(sc.detect_stalled_leads(db, queue, TENANT))
    assert [d["record_id"] for d in detections] == ["opp_live"]


def test_the_detection_limit_does_not_hide_the_stalest_deal(env):
    db, queue = env
    run(db.opportunities.insert_many([
        {"tenant_id": TENANT, "id": f"won_{n}", "name": "Won", "stage": "closed_won",
         "created_at": iso(-1), "updated_at": iso(-1), "archived_at": None}
        for n in range(sc.DETECTION_LIMIT + 5)]))
    stale_deal(db, "opp_old")
    detections = run(sc.detect_stalled_leads(db, queue, TENANT))
    assert [d["record_id"] for d in detections] == ["opp_old"]


def test_the_detection_limit_does_not_hide_an_overdue_task(env):
    db, queue = env
    run(db.tasks.insert_many([
        {"tenant_id": TENANT, "id": f"done_{n}", "title": "Done", "status": "done",
         "due_date": iso(-5)} for n in range(sc.DETECTION_LIMIT + 5)]))
    run(db.tasks.insert_one({"tenant_id": TENANT, "id": "late", "title": "Late",
                             "status": "todo", "due_date": iso(-5)}))
    detections = run(sc.detect_missed_followups(db, queue, TENANT))
    assert [d["record_id"] for d in detections] == ["late"]


# ------------------------------------------------------------- when the cause goes away

def test_a_detection_is_withdrawn_once_the_deal_is_won(env):
    db, queue = env
    stale_deal(db)
    run(sc.run_detection(db, queue, TENANT))
    run(db.opportunities.update_one({"id": "opp_1"}, {"$set": {"stage": "closed_won",
                                                               "updated_at": iso()}}))
    run(sc.run_detection(db, queue, TENANT))

    items = run(queue.list_items(tenant_id=TENANT, status="open", queue=sc.QUEUE_NAME))
    case = run(db[rc.COLLECTION].find_one({"tenant_id": TENANT}))
    assert items == []
    assert case["state"] == rc.CLOSED


def test_the_composer_does_not_plan_for_a_deal_that_was_won_meanwhile(env):
    db, queue = env
    stale_deal(db)
    run(sc.run_detection(db, queue, TENANT))
    run(db.opportunities.update_one({"id": "opp_1"}, {"$set": {"stage": "closed_won"}}))

    summary = run(rs.compose_for_tenant(db, queue, TENANT))
    assert summary["strategies_composed"] == 0
    assert run(db[aq.COLLECTION].count_documents({"tenant_id": TENANT,
                                                  "status": aq.REQUESTED})) == 0
    case = run(db[rc.COLLECTION].find_one({"tenant_id": TENANT}))
    assert case["state"] == rc.CLOSED


def test_a_pending_plan_is_withdrawn_with_its_detection(env):
    db, queue = env
    stale_deal(db)
    run(sc.run_detection(db, queue, TENANT))
    run(rs.compose_for_tenant(db, queue, TENANT))
    strategy = run(db[rs.COLLECTION].find_one({"tenant_id": TENANT}))
    assert strategy["state"] == rs.STATE_PROPOSED

    run(db.opportunities.update_one({"id": "opp_1"}, {"$set": {"archived_at": iso()}}))
    run(sc.run_detection(db, queue, TENANT))

    strategy = run(db[rs.COLLECTION].find_one({"tenant_id": TENANT}))
    approval = run(db[aq.COLLECTION].find_one({"id": strategy["approval_id"]}))
    assert strategy["state"] == rs.STATE_WITHDRAWN
    assert approval["status"] == aq.CANCELLED


def test_a_withdrawn_case_reopens_when_the_deal_stalls_again(env):
    db, queue = env
    stale_deal(db)
    run(sc.run_detection(db, queue, TENANT))
    run(db.opportunities.update_one({"id": "opp_1"}, {"$set": {"stage": "closed_won"}}))
    run(sc.run_detection(db, queue, TENANT))
    run(db.opportunities.update_one({"id": "opp_1"}, {"$set": {"stage": "negotiation"}}))
    run(sc.run_detection(db, queue, TENANT))

    cases = run(db[rc.COLLECTION].find({"tenant_id": TENANT}).to_list(5))
    assert len(cases) == 1 and cases[0]["state"] == rc.DETECTED
    assert not cases[0].get("withdrawn_at")
    items = run(queue.list_items(tenant_id=TENANT, status="open", queue=sc.QUEUE_NAME))
    assert len(items) == 1


def test_an_approved_case_is_left_for_a_person(env):
    """A person approved the plan; a sweep does not undo that on its own."""
    db, queue = env
    stale_deal(db)
    run(sc.run_detection(db, queue, TENANT))
    case = run(db[rc.COLLECTION].find_one({"tenant_id": TENANT}))
    run(db[rc.COLLECTION].update_one({"id": case["id"]}, {"$set": {"state": rc.APPROVED}}))
    run(db.opportunities.update_one({"id": "opp_1"}, {"$set": {"stage": "closed_won"}}))
    run(sc.run_detection(db, queue, TENANT))
    assert run(db[rc.COLLECTION].find_one({"id": case["id"]}))["state"] == rc.APPROVED


# ------------------------------------------------------------- the runner

def approved_case(db, *, contact_id=None):
    run(db.companies.insert_one({"tenant_id": TENANT, "id": "co_1", "name": "Acme"}))
    run(db.workspaces.insert_one({"tenant_id": TENANT, "id": "ws_1", "company_id": "co_1",
                                  "name": "Acme", "owner": "owner@example.com"}))
    run(db.opportunities.insert_one({
        "tenant_id": TENANT, "id": "opp_r", "name": "Acme renewal", "stage": "proposal",
        "value": 40000, "company_id": "co_1", "owner": "owner@example.com"}))
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_DORMANT_DEAL,
        source_event_id="opportunity:opp_r", reason="No activity for 30 days.",
        title="Acme renewal", workspace_id="ws_1", company_id="co_1",
        contact_id=contact_id, opportunity_id="opp_r", potential_value=40000,
        evidence={"idle_days": 30, "stage": "proposal", "value": 40000})))
    strategy = run(rs.compose_for_case(db, TENANT, case))
    run(aq.decide(db, tenant_id=TENANT, approval_id=strategy["approval_id"],
                  decision=aq.APPROVED, actor="admin@example.com"))
    run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=rc.APPROVED,
                     actor="admin@example.com"))
    return run(rc.get_case(db, TENANT, case["id"]))


def _email_messages(db):
    return run(db[cv.MESSAGES].find({"tenant_id": TENANT, "channel": cv.CHANNEL_EMAIL})
               .to_list(10))


def test_a_retry_raises_the_approval_a_crash_left_unraised(env, monkeypatch):
    db, _ = env
    run(db.contacts.insert_one({"tenant_id": TENANT, "id": "ct_1", "name": "Ada",
                                "email": "ada@x.example"}))
    case = approved_case(db, contact_id="ct_1")
    real = cv.request_approval
    calls = {"n": 0}

    async def dies_once(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("worker killed")
        return await real(*args, **kwargs)

    monkeypatch.setattr(cv, "request_approval", dies_once)
    with pytest.raises(RuntimeError):
        run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    result = run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))

    [message] = _email_messages(db)
    assert message["status"] == cv.PENDING_APPROVAL and message["approval_id"]
    assert message["approval_id"] in result["awaiting"]


def test_a_rerun_addresses_a_draft_once_the_case_has_a_contact(env):
    db, _ = env
    case = approved_case(db)
    run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    [before] = _email_messages(db)
    assert before["to_address"] is None

    run(db.contacts.insert_one({"tenant_id": TENANT, "id": "ct_1", "name": "Ada",
                                "email": "ada@x.example"}))
    run(rc.link_crm_records(db, tenant_id=TENANT, case_id=case["id"], contact_id="ct_1",
                            actor="admin@example.com"))
    run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))

    [after] = _email_messages(db)
    assert after["id"] == before["id"]
    assert after["to_address"] == "ada@x.example"
    assert after["status"] == cv.PENDING_APPROVAL
    # The approval a person reads must name the recipient the message now goes to.
    approval = run(db[aq.COLLECTION].find_one({"id": after["approval_id"]}))
    assert approval["status"] == aq.REQUESTED
    assert any(f["label"] == "Recipient" and f["value"] == "ada@x.example"
               for f in approval["facts"])
    old = run(db[aq.COLLECTION].find_one({"id": before["approval_id"]}))
    assert old["status"] == aq.CANCELLED
    conversation = run(db[cv.CONVERSATIONS].find_one({"id": after["conversation_id"]}))
    assert any(p.get("address") == "ada@x.example" for p in conversation["participants"])
