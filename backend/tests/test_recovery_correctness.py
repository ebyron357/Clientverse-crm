"""Revenue-recovery correctness: the numbers are right, nothing counts twice, nothing sticks.

Each test here pins one of the defects a read-only audit found in the recovery engine,
and almost every one asserts money end to end -- open potential, attributed recovered
value and unattributed outcome value as a buyer would read them -- rather than a flag on
one record. The failures being guarded against all looked like success:

* one buyer reaching the business four ways counted as four opportunities;
* one deal pinned to five cases booked five times, and once more as its invoice;
* an outcome leaving its case's potential in "open" while the same money sat in an
  outcome bucket;
* a claim the case never confirmed still counted as attributed;
* cases that could never be approved, never closed, and so only ever accumulated.
"""

import asyncio
import json
import math
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_recovery_correctness_unit")
os.environ.setdefault("JWT_SECRET", "recovery-correctness-unit-jwt-secret-long-enough")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

from cryptography.fernet import Fernet

os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

import approval_queue as aq
import attribution
import conversations as cv
import detectors
import recovery_case as rc
import recovery_lifecycle
import recovery_proof
import recovery_reconcile
import recovery_runner
import recovery_strategy as rs
import second_chance
from work_queue import WorkQueue

MONGO_URL = os.environ["MONGO_URL"]
TENANT = "ten_rcc_a"
OTHER_TENANT = "ten_rcc_b"
ADMIN = {"email": "admin@acme.test", "tenant_id": TENANT, "role": "admin"}

_LOOP = None


def run(coro):
    """One loop for the module, so a real Motor client stays bound to it."""
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


def ago(**delta):
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat()


def now():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture()
def env():
    name = f"cv_rcc_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[name]
    queue = WorkQueue(db)
    run(queue.ensure_indexes())
    for module in (aq, rs, cv, rc, attribution, detectors, second_chance):
        run(module.ensure_indexes(db))
    run(db.tenants.insert_many([{"tenant_id": TENANT, "name": "A"},
                                {"tenant_id": OTHER_TENANT, "name": "B"}]))
    yield db, queue
    run(client.drop_database(name))
    client.close()


def insert(db, collection, doc, *, tenant_id=TENANT):
    doc = {"id": f"{collection[:3]}_{uuid.uuid4().hex[:10]}", "tenant_id": tenant_id, **doc}
    run(db[collection].insert_one(dict(doc)))
    return doc


def seed_buyer(db, *, value=40000.0, currency="GBP", stage="proposal", owner=None):
    """A contact and their dormant deal -- the buyer every multi-source test is about."""
    contact = insert(db, "contacts", {"name": "Sam Buyer", "email": "sam@buyer.test"})
    deal = insert(db, "opportunities", {
        "name": "Fit-out", "stage": stage, "value": value, "currency": currency,
        "contact_ids": [contact["id"]], "owner": owner,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        "stage_history": [{"from": None, "to": stage, "at": "2026-01-01T00:00:00+00:00"}]})
    return contact, deal


def money(db, tenant_id=TENANT):
    """The three revenue figures as the proof page reads them."""
    revenue = run(recovery_proof.portfolio(db, tenant_id))["revenue"]
    return (revenue["potential_value_open_by_currency"],
            revenue["attributed_recovered_value_by_currency"],
            revenue["unattributed_outcome_value_by_currency"])


def walk_to_engaged(db, case, *, sent_days_ago=2):
    """A case worked the way the pipeline works one, with a message that reached the client."""
    for state in (rc.PLANNED, rc.AWAITING_APPROVAL, rc.APPROVED, rc.EXECUTING):
        run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=state))
    conversation = run(cv.create_conversation(
        db, tenant_id=TENANT, channel=cv.CHANNEL_EMAIL, actor="agent", subject="Recovery",
        recovery_case_id=case["id"]))
    run(db[cv.MESSAGES].insert_one({
        "id": f"msg_{uuid.uuid4().hex[:10]}", "tenant_id": TENANT,
        "conversation_id": conversation["id"], "channel": cv.CHANNEL_EMAIL,
        "direction": cv.OUTBOUND, "status": cv.SENT, "body": "Following up",
        "created_at": ago(days=sent_days_ago), "sent_at": ago(days=sent_days_ago),
        "provider_message_id": "prov_1", "history": []}))
    return run(recovery_lifecycle.sync_engagement(db, tenant_id=TENANT, case_id=case["id"]))


def win(db, deal, *, at=None, stage="closed_won"):
    run(db.opportunities.update_one(
        {"id": deal["id"]},
        {"$set": {"stage": stage, "updated_at": at or now()},
         "$push": {"stage_history": {"from": "proposal", "to": stage, "at": at or now()}}}))


def case_for(db, source, tenant_id=TENANT):
    cases = run(db[rc.COLLECTION].find({"tenant_id": tenant_id, "source": source},
                                       {"_id": 0}).to_list(50))
    assert len(cases) == 1, cases
    return cases[0]


# ======================================================= 5. one buyer, many sources

def test_one_buyer_across_sources_counts_once_in_open_potential(env):
    """A dormant deal, two enquiries about it, an older enquiry and a missed call from the
    same person: one £40,000 opportunity, not £135,000 -- and the collapse is reported."""
    db, queue = env
    contact, deal = seed_buyer(db)
    for value in (40000.0, 35000.0):
        insert(db, detectors.WEB_ENQUIRIES, {
            "email": "sam@buyer.test", "status": "new", "received_at": ago(days=2),
            "contact_id": contact["id"], "opportunity_id": deal["id"],
            "estimated_value": value, "currency": "GBP"})
    # Older enquiry, before the website pipeline linked enquiries to deals.
    insert(db, detectors.WEB_ENQUIRIES, {
        "email": "sam@buyer.test", "status": "new", "received_at": ago(days=5),
        "contact_id": contact["id"], "estimated_value": 20000.0, "currency": "GBP"})
    insert(db, detectors.CALL_LOGS, {"direction": "inbound", "from_number": "+44 1632 970001",
                                     "outcome": "missed", "occurred_at": ago(hours=8),
                                     "contact_id": contact["id"]})
    # A separate priced offer to a different client: its own opportunity.
    workspace = insert(db, "workspaces", {"name": "Other client"})
    insert(db, "estimates", {"title": "Other job", "status": "sent", "total": 5000.0,
                             "currency": "GBP", "workspace_id": workspace["id"],
                             "created_at": ago(days=14)})

    run(second_chance.run_detection(db, queue, TENANT))
    run(detectors.run_detection(db, queue, TENANT))
    assert run(db[rc.COLLECTION].count_documents({"tenant_id": TENANT})) == 6

    potential, attributed, unattributed = money(db)
    assert potential == {"GBP": 45000.0}, "one deal's value once, plus the separate estimate"
    summary = run(rc.summary(db, TENANT))
    assert summary["potential_value_open_by_currency"] == {"GBP": 45000.0}
    assert summary["open_cases_collapsed"] == 3
    assert summary["open_cases_without_value"] == 1, "the missed call is visible, not dropped"
    assert summary["open_opportunity_groups"] == 2
    assert attributed == {} and unattributed == {}


def test_two_different_deals_of_one_contact_are_not_collapsed(env):
    db, _ = env
    contact = insert(db, "contacts", {"name": "Sam"})
    for value in (1000.0, 2500.0):
        deal = insert(db, "opportunities", {"name": "Deal", "stage": "proposal", "value": value})
        run(rc.open_case(db, rc.normalize_event(
            tenant_id=TENANT, source=rc.SOURCE_WEB_ENQUIRY, source_event_id=f"e:{deal['id']}",
            reason="r", opportunity_id=deal["id"], contact_id=contact["id"],
            potential_value=value, currency="USD")))
    # A contact-only case cannot be pinned to either deal, so it stands alone.
    run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_MISSED_CALL, source_event_id="call:x",
        reason="r", contact_id=contact["id"], potential_value=300.0, currency="USD")))
    summary = run(rc.summary(db, TENANT))
    assert summary["potential_value_open_by_currency"] == {"USD": 3800.0}
    assert summary["open_cases_collapsed"] == 0


# ============================================= 3. an outcome leaves open potential

def test_an_unattributed_outcome_takes_the_case_out_of_open_potential(env):
    db, queue = env
    _, deal = seed_buyer(db, value=10000.0, currency="USD")
    run(second_chance.run_detection(db, queue, TENANT))
    case = case_for(db, rc.SOURCE_DORMANT_DEAL)
    assert money(db)[0] == {"USD": 10000.0}

    win(db, deal)
    entry = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"],
                                           kind=attribution.OUTCOME_DEAL_WON,
                                           record_id=deal["id"], actor="ops"))
    assert entry["claim"] == attribution.CLAIM_UNATTRIBUTED
    assert entry["case_closed"] is True

    potential, attributed, unattributed = money(db)
    assert potential == {}, "the same money must not sit in open potential and in an outcome"
    assert attributed == {}
    assert unattributed == {"USD": 10000.0}
    closed = run(rc.get_case(db, TENANT, case["id"]))
    assert closed["state"] == rc.CLOSED and closed["close_reason"] == "outcome_recorded"


def test_an_attributed_claim_needs_a_worked_case_and_a_successful_confirmation(env):
    db, queue = env
    _, deal = seed_buyer(db, value=12000.0, currency="USD")
    run(second_chance.run_detection(db, queue, TENANT))
    case = case_for(db, rc.SOURCE_DORMANT_DEAL)
    engaged = walk_to_engaged(db, case)
    assert engaged["state"] == rc.ENGAGED

    win(db, deal)
    entry = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"],
                                           kind=attribution.OUTCOME_DEAL_WON,
                                           record_id=deal["id"], actor="ops"))
    assert entry["claim"] == attribution.CLAIM_ATTRIBUTED and entry["case_updated"] is True
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.RECOVERED
    assert money(db) == ({}, {"USD": 12000.0}, {})
    summary = run(rc.summary(db, TENANT))
    assert summary["recovered_cases"] == 1
    assert summary["confirmed_recovered_value_by_currency"] == {"USD": 12000.0}

    # A recovered case that is later closed still counts as recovered.
    run(rc.close_case(db, tenant_id=TENANT, case_id=case["id"], reason="resolved"))
    assert run(rc.summary(db, TENANT))["recovered_cases"] == 1


def test_a_legacy_attributed_but_unconfirmed_entry_is_not_counted_as_attributed(env):
    db, _ = env
    run(db[attribution.COLLECTION].insert_one({
        "id": "attr_legacy", "tenant_id": TENANT, "case_id": "rc_x",
        "outcome": {"kind": "invoice_paid", "record_id": "inv_1", "amount": 900.0},
        "claim": attribution.CLAIM_ATTRIBUTED, "basis": attribution.BASIS_DELIVERED,
        "currency": "USD", "case_updated": False, "recorded_at": now()}))
    totals = run(attribution.totals(db, TENANT))
    assert totals["attributed_recovered_value_by_currency"] == {}
    assert totals["unattributed_outcome_value_by_currency"] == {"USD": 900.0}
    assert totals["attributed_but_unconfirmed_entries"] == 1


# ============================================== 4. one sale counts once, tenant-wide

def test_one_deal_on_five_cases_is_booked_once(env):
    db, _ = env
    _, deal = seed_buyer(db, value=40000.0, currency="GBP", stage="closed_won")
    cases = [run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_WEB_ENQUIRY, source_event_id=f"web_enquiry:{i}",
        reason="r", opportunity_id=deal["id"], potential_value=40000.0, currency="GBP")))
        for i in range(5)]
    first = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=cases[0]["id"],
                                           kind=attribution.OUTCOME_DEAL_WON,
                                           record_id=deal["id"], actor="ops"))
    for case in cases[1:]:
        with pytest.raises(attribution.DuplicateSale) as refused:
            run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"],
                                           kind=attribution.OUTCOME_DEAL_WON,
                                           record_id=deal["id"], actor="ops"))
        assert refused.value.entry["id"] == first["id"]
    totals = run(attribution.totals(db, TENANT))
    assert totals["unattributed_outcome_value_by_currency"] == {"GBP": 40000.0}, (
        "was GBP 200,000 before: one deal booked once per case")
    assert totals["entries"] == 1


def test_a_deal_and_the_invoice_raised_for_it_are_one_sale(env):
    db, _ = env
    _, deal = seed_buyer(db, value=40000.0, currency="GBP", stage="closed_won")
    # A won deal's workspace, an estimate in it, and the invoice converted from it.
    workspace = insert(db, "workspaces", {"name": "Fit-out", "opportunity_id": deal["id"]})
    estimate = insert(db, "estimates", {"title": "Fit-out", "status": "approved",
                                        "total": 40000.0, "currency": "GBP",
                                        "workspace_id": workspace["id"]})
    invoice = insert(db, "invoices", {"title": "Fit-out", "total": 40000.0, "currency": "GBP",
                                      "estimate_id": estimate["id"],
                                      "workspace_id": workspace["id"],
                                      "status": "paid", "paid_at": now()})
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_DORMANT_DEAL, source_event_id=f"opportunity:{deal['id']}",
        reason="r", opportunity_id=deal["id"], potential_value=40000.0, currency="GBP")))
    run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"],
                                   kind=attribution.OUTCOME_DEAL_WON, record_id=deal["id"],
                                   actor="ops"))
    again = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"],
                                           kind=attribution.OUTCOME_INVOICE_PAID,
                                           record_id=invoice["id"], actor="ops"))
    assert again["deduplicated"] is True, "deal_won + invoice_paid for one sale used to double"
    totals = run(attribution.totals(db, TENANT))
    assert totals["unattributed_outcome_value_by_currency"] == {"GBP": 40000.0}


def test_an_outcome_that_does_not_relate_to_the_case_is_refused(env):
    db, _ = env
    _, deal = seed_buyer(db, stage="closed_won")
    _, unrelated = seed_buyer(db, stage="closed_won")
    stranger_invoice = insert(db, "invoices", {"total": 50.0, "status": "paid"})
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_DORMANT_DEAL, source_event_id="opportunity:1",
        reason="r", opportunity_id=deal["id"])))
    for kind, record_id in ((attribution.OUTCOME_DEAL_WON, unrelated["id"]),
                            (attribution.OUTCOME_INVOICE_PAID, stranger_invoice["id"])):
        with pytest.raises(attribution.AttributionError) as refused:
            run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"],
                                           kind=kind, record_id=record_id, actor="ops"))
        assert "not related" in str(refused.value)
    assert run(attribution.totals(db, TENANT))["entries"] == 0


def test_a_contact_only_case_relates_to_a_deal_its_contact_is_on(env):
    db, _ = env
    contact, deal = seed_buyer(db, stage="closed_won", currency="USD", value=700.0)
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_MISSED_CALL, source_event_id="call:1", reason="r",
        contact_id=contact["id"])))
    entry = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"],
                                           kind=attribution.OUTCOME_DEAL_WON,
                                           record_id=deal["id"], actor="ops"))
    assert entry["sale_key"] == f"deal:{deal['id']}"


def test_a_legacy_outcome_left_on_an_open_case_is_taken_out_of_open_potential(env):
    """Before the fix an outcome left its case open: the money counted twice."""
    db, _ = env
    _, deal = seed_buyer(db, value=6000.0, currency="USD", stage="closed_won")
    replayed = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_DORMANT_DEAL, source_event_id="opportunity:a",
        reason="r", opportunity_id=deal["id"], potential_value=6000.0)))
    swept = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_MISSED_CALL, source_event_id="call:legacy",
        reason="r", potential_value=300.0)))
    for case, kind, record_id, amount in ((replayed, "deal_won", deal["id"], 6000.0),
                                          (swept, "operator_confirmed", "cash-1", 300.0)):
        run(db[attribution.COLLECTION].insert_one({
            "id": f"attr_{case['id']}", "tenant_id": TENANT, "case_id": case["id"],
            "outcome": {"kind": kind, "record_id": record_id, "amount": amount},
            "claim": attribution.CLAIM_UNATTRIBUTED, "currency": "USD",
            "recorded_at": now()}))
    assert money(db)[0] == {"USD": 6300.0} and money(db)[2] == {"USD": 6300.0}

    again = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=replayed["id"],
                                           kind=attribution.OUTCOME_DEAL_WON,
                                           record_id=deal["id"], actor="ops"))
    assert again["deduplicated"] is True
    run(recovery_reconcile.reconcile_tenant(db, TENANT))
    assert money(db) == ({}, {}, {"USD": 6300.0})


def test_legacy_duplicate_entries_are_counted_once(env):
    db, _ = env
    for i in range(3):
        run(db[attribution.COLLECTION].insert_one({
            "id": f"attr_{i}", "tenant_id": TENANT, "case_id": f"rc_{i}",
            "outcome": {"kind": "deal_won", "record_id": "opp_same", "amount": 40000.0},
            "claim": attribution.CLAIM_UNATTRIBUTED, "currency": "GBP",
            "recorded_at": ago(minutes=10 - i)}))
    totals = run(attribution.totals(db, TENANT))
    assert totals["unattributed_outcome_value_by_currency"] == {"GBP": 40000.0}
    assert totals["duplicate_entries_excluded"] == 2


# ===================================================== 11. an invoice paid by hand

def test_an_invoice_marked_paid_by_hand_is_paid(env):
    db, _ = env
    workspace = insert(db, "workspaces", {"name": "W"})
    estimate = insert(db, "estimates", {"title": "E", "status": "sent", "total": 800.0,
                                        "currency": "USD", "workspace_id": workspace["id"]})
    invoice = insert(db, "invoices", {"total": 800.0, "currency": "USD",
                                      "estimate_id": estimate["id"], "status": "paid",
                                      "payment_status": "requires_stripe_configuration"})
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_UNANSWERED_ESTIMATE,
        source_event_id=f"estimate:{estimate['id']}", reason="r", potential_value=800.0)))
    entry = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"],
                                           kind=attribution.OUTCOME_INVOICE_PAID,
                                           record_id=invoice["id"], actor="ops"))
    assert entry["outcome"]["amount"] == 800.0
    assert entry["sale_key"] == f"estimate:{estimate['id']}"


# ======================================================== 2. reconciliation closes

def test_a_deal_won_after_the_case_is_recorded_once_on_the_case_that_worked_it(env):
    db, queue = env
    contact, deal = seed_buyer(db, value=40000.0, currency="GBP")
    insert(db, detectors.WEB_ENQUIRIES, {
        "email": "sam@buyer.test", "status": "new", "received_at": ago(days=2),
        "contact_id": contact["id"], "opportunity_id": deal["id"],
        "estimated_value": 40000.0, "currency": "GBP"})
    run(second_chance.run_detection(db, queue, TENANT))
    run(detectors.run_detection(db, queue, TENANT))
    dormant = case_for(db, rc.SOURCE_DORMANT_DEAL)
    enquiry = case_for(db, rc.SOURCE_WEB_ENQUIRY)
    walk_to_engaged(db, enquiry)

    win(db, deal)
    first = run(recovery_reconcile.reconcile_tenant(db, TENANT))
    second = run(recovery_reconcile.reconcile_tenant(db, TENANT))

    assert len(first["outcomes"]) == 1 and first["outcomes"][0]["case_id"] == enquiry["id"]
    assert first["closed"] == {"sale_recorded_on_another_case": 1}
    assert second["outcomes"] == [] and second["examined"] == 0
    assert run(rc.get_case(db, TENANT, enquiry["id"]))["state"] == rc.RECOVERED
    assert run(rc.get_case(db, TENANT, dormant["id"]))["close_reason"] == \
        "sale_recorded_on_another_case"
    assert money(db) == ({}, {"GBP": 40000.0}, {})
    assert run(attribution.totals(db, TENANT))["entries"] == 1


def test_a_deal_won_with_no_outreach_is_recorded_once_as_unattributed(env):
    db, queue = env
    _, deal = seed_buyer(db, value=9000.0, currency="USD")
    run(second_chance.run_detection(db, queue, TENANT))
    win(db, deal)
    run(second_chance.run_detection(db, queue, TENANT))   # reconciliation runs first
    run(second_chance.run_detection(db, queue, TENANT))
    assert money(db) == ({}, {}, {"USD": 9000.0})
    assert run(attribution.totals(db, TENANT))["entries"] == 1


def test_a_deal_already_won_before_the_case_opened_is_not_a_recovery(env):
    db, _ = env
    _, deal = seed_buyer(db, value=9000.0, currency="USD")
    win(db, deal, at=ago(days=3))
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_WEB_ENQUIRY, source_event_id="web_enquiry:late",
        reason="r", opportunity_id=deal["id"], potential_value=9000.0)))
    run(recovery_reconcile.reconcile_tenant(db, TENANT))
    assert run(rc.get_case(db, TENANT, case["id"]))["close_reason"] == "deal_won_before_case"
    assert money(db) == ({}, {}, {})


@pytest.mark.parametrize("change, reason", [
    ({"stage": "closed_lost"}, "deal_lost"),
    ({"archived_at": "2026-10-01T00:00:00+00:00"}, "deal_archived"),
])
def test_a_lost_or_archived_deal_closes_its_cases(env, change, reason):
    db, queue = env
    _, deal = seed_buyer(db)
    run(second_chance.run_detection(db, queue, TENANT))
    run(db.opportunities.update_one({"id": deal["id"]}, {"$set": change}))
    run(second_chance.run_detection(db, queue, TENANT))
    assert case_for(db, rc.SOURCE_DORMANT_DEAL)["close_reason"] == reason
    assert money(db)[0] == {}


def test_closed_and_won_follow_the_tenants_own_pipeline(env):
    db, queue = env
    run(db.pipelines.insert_one({"tenant_id": TENANT, "id": "default", "stages": [
        {"key": "talking", "label": "Talking", "probability": 30, "is_closed": False, "is_won": False},
        {"key": "signed", "label": "Signed", "probability": 100, "is_closed": True, "is_won": True},
        {"key": "gone", "label": "Gone", "probability": 0, "is_closed": True, "is_won": False},
    ]}))
    _, signed = seed_buyer(db, stage="signed", value=5000.0, currency="USD")
    _, talking = seed_buyer(db, stage="talking")
    stalled = run(second_chance.detect_stalled_leads(db, queue, TENANT))
    assert [d["record_id"] for d in stalled] == [talking["id"]], "a 'signed' deal is not stalled"

    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_DORMANT_DEAL, source_event_id="opportunity:s",
        reason="r", opportunity_id=signed["id"])))
    entry = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"],
                                           kind=attribution.OUTCOME_DEAL_WON,
                                           record_id=signed["id"], actor="ops"))
    assert entry["outcome"]["amount"] == 5000.0


def test_resolved_sources_close_their_cases(env):
    db, queue = env
    contact = insert(db, "contacts", {"name": "Lee"})
    enquiry = insert(db, detectors.WEB_ENQUIRIES, {"email": "a@b.test", "status": "new",
                                                   "received_at": ago(days=2),
                                                   "estimated_value": 100.0})
    test_lead = insert(db, detectors.WEB_ENQUIRIES, {"email": "t@b.test", "status": "new",
                                                     "received_at": ago(days=2)})
    call = insert(db, detectors.CALL_LOGS, {"direction": "inbound",
                                            "from_number": "+1 (555) 010-0199",
                                            "outcome": "missed", "occurred_at": ago(hours=8),
                                            "contact_id": contact["id"]})
    workspace = insert(db, "workspaces", {"name": "W"})
    estimate = insert(db, "estimates", {"title": "E", "status": "sent", "total": 300.0,
                                        "currency": "USD", "workspace_id": workspace["id"],
                                        "created_at": ago(days=14)})
    run(detectors.run_detection(db, queue, TENANT))
    assert run(db[rc.COLLECTION].count_documents({"tenant_id": TENANT})) == 4
    assert money(db)[0] == {"USD": 400.0}

    run(db[detectors.WEB_ENQUIRIES].update_one({"id": enquiry["id"]},
                                               {"$set": {"status": "responded"}}))
    run(db[detectors.WEB_ENQUIRIES].update_one({"id": test_lead["id"]},
                                               {"$set": {"is_test": True}}))
    # Called back from a differently formatted number: the same caller.
    insert(db, detectors.CALL_LOGS, {"direction": "outbound", "to_number": "15550100199",
                                     "outcome": "completed", "occurred_at": ago(hours=1)})
    run(db.estimates.update_one({"id": estimate["id"]}, {"$set": {"status": "declined"}}))
    summary = run(detectors.run_detection(db, queue, TENANT))

    assert summary["reconciliation"]["closed"] == {"source_resolved": 3, "test_record": 1}
    assert money(db) == ({}, {}, {})
    assert run(rc.summary(db, TENANT))["open_cases"] == 0
    closed = {c["source_event_id"]: c for c in run(db[rc.COLLECTION].find(
        {"tenant_id": TENANT}, {"_id": 0}).to_list(10))}
    assert closed[f"call:{call['id']}"]["close_reason"] == "source_resolved"
    # The closed work no longer sits in the operator's queue.
    assert run(queue.list_items(tenant_id=TENANT, status="open",
                                queue=detectors.QUEUE_NAME)) == []


def test_an_engaged_case_waits_for_its_outcome_instead_of_closing_on_a_reply(env):
    db, queue = env
    insert(db, detectors.WEB_ENQUIRIES, {"email": "a@b.test", "status": "new",
                                         "received_at": ago(days=2)})
    run(detectors.run_detection(db, queue, TENANT))
    case = case_for(db, rc.SOURCE_WEB_ENQUIRY)
    walk_to_engaged(db, case)
    run(db[detectors.WEB_ENQUIRIES].update_many({}, {"$set": {"status": "responded"}}))
    summary = run(recovery_reconcile.reconcile_tenant(db, TENANT))
    assert summary["kept_open_engaged"] == 1
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.ENGAGED


def test_an_engaged_case_with_nothing_to_show_closes_after_the_window(env):
    db, _ = env
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_EXTERNAL_CRM_EVENT, source_event_id="external_event:1",
        reason="r")))
    insert(db, detectors.EXTERNAL_EVENTS, {"id": "1", "provider": "x", "kind": "deal_lost",
                                           "external_id": "1", "status": "new",
                                           "occurred_at": ago(days=200)})
    walk_to_engaged(db, case, sent_days_ago=120)
    run(recovery_reconcile.reconcile_tenant(db, TENANT))
    assert run(rc.get_case(db, TENANT, case["id"]))["close_reason"] == \
        "attribution_window_elapsed"


def test_a_paid_invoice_from_an_estimate_case_is_recorded_as_its_outcome(env):
    db, queue = env
    workspace = insert(db, "workspaces", {"name": "W"})
    estimate = insert(db, "estimates", {"title": "E", "status": "sent", "total": 2500.0,
                                        "currency": "EUR", "workspace_id": workspace["id"],
                                        "created_at": ago(days=14)})
    run(detectors.run_detection(db, queue, TENANT))
    case = case_for(db, rc.SOURCE_UNANSWERED_ESTIMATE)
    assert case["currency"] == "EUR"
    walk_to_engaged(db, case)
    insert(db, "invoices", {"total": 2500.0, "currency": "EUR", "estimate_id": estimate["id"],
                            "status": "paid", "paid_at": now()})
    run(detectors.run_detection(db, queue, TENANT))
    assert money(db) == ({}, {"EUR": 2500.0}, {})


# ===================================================== 10. invoiced estimates

def test_an_estimate_with_an_invoice_is_not_detected_as_lost(env):
    db, _ = env
    workspace = insert(db, "workspaces", {"name": "W"})
    raised = insert(db, "estimates", {"title": "Raised", "status": "sent", "total": 100.0,
                                      "workspace_id": workspace["id"], "created_at": ago(days=14)})
    marked = insert(db, "estimates", {"title": "Marked", "status": "sent", "total": 100.0,
                                      "invoice_id": "inv_x", "workspace_id": workspace["id"],
                                      "created_at": ago(days=14)})
    insert(db, "invoices", {"estimate_id": raised["id"], "status": "draft"})
    assert run(detectors.detect_unanswered_estimates(db, TENANT)) == []
    assert marked["invoice_id"]


# ==================================================== 1. the lifecycle moves

def _planned_case(db, queue):
    _, deal = seed_buyer(db, value=40000.0, currency="GBP", owner="owner@acme.test")
    run(second_chance.run_detection(db, queue, TENANT))
    case = case_for(db, rc.SOURCE_DORMANT_DEAL)
    strategy = run(rs.compose_for_case(db, TENANT, case))
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.AWAITING_APPROVAL
    return deal, case, strategy


@pytest.fixture()
def app_server(env):
    """The application module, pointed at this test's database for the duration."""
    import server
    db, queue = env
    saved = (server.db, server.work_queue)
    server.db, server.work_queue = db, queue
    yield server
    server.db, server.work_queue = saved


def test_approving_the_strategy_advances_the_case_through_to_recovered(env, app_server):
    db, queue = env
    deal, case, strategy = _planned_case(db, queue)

    approval = run(aq.decide(db, tenant_id=TENANT, approval_id=strategy["approval_id"],
                             decision=aq.APPROVED, actor=ADMIN["email"]))
    effects = run(app_server._apply_approval_side_effects(approval, ADMIN))
    assert effects["recovery_case"]["state"] == rc.APPROVED, "approval used to change nothing"
    jobs = run(queue.list_items(tenant_id=TENANT, item_type=recovery_runner.JOB_RUN_RECOVERY_CASE))
    assert [job["payload"]["case_id"] for job in jobs] == [case["id"]]

    result = run(recovery_runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    assert result["outbound_drafted"] >= 1 and result["case_state"] == rc.EXECUTING
    # The drafted message goes out (as a provider would accept it) ...
    message = run(cv.get_message(db, TENANT, result["steps"][1]["message_id"]))
    run(db[cv.MESSAGES].update_one({"id": message["id"]},
                                   {"$set": {"status": cv.SENT, "sent_at": ago(hours=1)}}))
    # ... and only then is the case engaged.
    assert run(recovery_reconcile.reconcile_tenant(db, TENANT))["engaged"] == 1
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.ENGAGED

    win(db, deal)
    run(recovery_reconcile.reconcile_tenant(db, TENANT))
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.RECOVERED
    assert money(db) == ({}, {"GBP": 40000.0}, {})


def test_rejecting_the_strategy_closes_the_case_and_its_work(env, app_server):
    db, queue = env
    _, case, strategy = _planned_case(db, queue)
    approval = run(aq.decide(db, tenant_id=TENANT, approval_id=strategy["approval_id"],
                             decision=aq.REJECTED, actor=ADMIN["email"],
                             rationale="Client asked us to stop"))
    run(app_server._apply_approval_side_effects(approval, ADMIN))
    closed = run(rc.get_case(db, TENANT, case["id"]))
    assert closed["state"] == rc.CLOSED and closed["close_reason"] == "strategy_rejected"
    assert closed["close_note"] == "Client asked us to stop"
    assert run(queue.list_items(tenant_id=TENANT, status="open",
                                queue=second_chance.QUEUE_NAME)) == []
    assert money(db)[0] == {}


def test_a_withdrawn_approval_is_re_proposed_not_stranded(env, app_server):
    db, queue = env
    _, case, strategy = _planned_case(db, queue)
    cancelled = run(aq.cancel(db, tenant_id=TENANT, approval_id=strategy["approval_id"],
                              actor=ADMIN["email"]))
    run(app_server._apply_approval_side_effects(cancelled, ADMIN))
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.PLANNED

    run(rs.compose_for_tenant(db, queue, TENANT))
    again = run(rc.get_case(db, TENANT, case["id"]))
    assert again["state"] == rc.AWAITING_APPROVAL
    assert again["approval_reference"] != strategy["approval_id"]
    assert run(aq.get(db, TENANT, again["approval_reference"]))["status"] == aq.REQUESTED


def test_a_case_stalled_behind_an_already_approved_plan_is_moved_on(env):
    """Production data from before the fix: plan approved, case left awaiting approval."""
    db, queue = env
    _, case, strategy = _planned_case(db, queue)
    run(aq.decide(db, tenant_id=TENANT, approval_id=strategy["approval_id"],
                  decision=aq.APPROVED, actor=ADMIN["email"]))
    run(rs.set_state(db, TENANT, strategy["id"], state=rs.STATE_APPROVED, actor="admin"))
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.AWAITING_APPROVAL
    run(rs.compose_for_tenant(db, queue, TENANT))
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.APPROVED


# ==================================================== 18. one live strategy per case

def test_a_case_gets_one_strategy_even_after_its_work_item_is_resolved(env):
    db, queue = env
    seed_buyer(db, owner="owner@acme.test")
    run(second_chance.run_detection(db, queue, TENANT))
    run(rs.compose_for_tenant(db, queue, TENANT))
    case = case_for(db, rc.SOURCE_DORMANT_DEAL)
    strategies = run(rs.list_strategies(db, TENANT))
    assert len(strategies) == 1 and strategies[0]["recovery_case_id"] == case["id"]
    assert case["plan_reference"] == strategies[0]["id"], "the plan is attached to the case"

    run(queue.resolve(case["work_item_reference"], tenant_id=TENANT, actor="ops"))
    run(rs.compose_for_tenant(db, queue, TENANT))
    run(rs.compose_for_tenant(db, queue, TENANT))
    assert len(run(rs.list_strategies(db, TENANT))) == 1
    assert len(run(aq.list_requests(db, TENANT, status="open"))) == 1


def test_a_legacy_work_item_strategy_is_adopted_not_duplicated(env):
    db, queue = env
    seed_buyer(db, owner="owner@acme.test")
    run(second_chance.run_detection(db, queue, TENANT))
    item = run(queue.list_items(tenant_id=TENANT, status="open",
                                queue=second_chance.QUEUE_NAME))[0]
    legacy = run(rs.compose_for_candidate(db, TENANT, item))
    run(db[rs.COLLECTION].update_one({"id": legacy["id"]}, {"$unset": {"recovery_case_id": ""}}))

    run(rs.compose_for_tenant(db, queue, TENANT))
    live = run(db[rs.COLLECTION].count_documents(
        {"tenant_id": TENANT, "active_candidate_key": {"$type": "string"}}))
    assert live == 1
    assert len(run(aq.list_requests(db, TENANT, status="open"))) == 1


# ========================================================== 6. currency

def test_each_source_carries_its_own_currency(env):
    db, queue = env
    seed_buyer(db, value=40000.0, currency="GBP")
    insert(db, detectors.WEB_ENQUIRIES, {"email": "e@x.test", "status": "new",
                                         "received_at": ago(days=2),
                                         "estimated_value": 900.0, "currency": "eur"})
    insert(db, detectors.WEB_ENQUIRIES, {"email": "old@x.test", "status": "new",
                                         "received_at": ago(days=2), "estimated_value": 50.0})
    insert(db, detectors.WEB_ENQUIRIES, {"email": "bad@x.test", "status": "new",
                                         "received_at": ago(days=2), "estimated_value": 70.0,
                                         "currency": "us dollars"})
    run(second_chance.run_detection(db, queue, TENANT))
    run(detectors.run_detection(db, queue, TENANT))
    potential = money(db)[0]
    assert potential == {"GBP": 40000.0, "EUR": 900.0, "USD": 50.0}, (
        "a dormant GBP deal used to be USD; an enquiry's own currency used to be ignored")
    cases = {(c.get("external_identity") or {}).get("value") or c["source"]: c for c in run(
        db[rc.COLLECTION].find({"tenant_id": TENANT}, {"_id": 0}).to_list(20))}
    assert cases[rc.SOURCE_DORMANT_DEAL]["potential_value_basis"] == "opportunity value on record"
    assert cases["old@x.test"]["evidence"]["currency_assumed"] is True
    assert cases["bad@x.test"]["potential_value"] is None
    assert "ISO 4217" in cases["bad@x.test"]["evidence"]["value_rejected"]


def test_value_thresholds_only_band_amounts_in_their_own_currency(env):
    assert rs.value_band(30000.0, "USD") == "high"
    assert rs.value_band(30000.0, "JPY") is None, "30,000 yen is not a high-value deal"
    candidate = {"type": second_chance.TYPE_STALLED_LEAD,
                 "evidence": {"idle_days": 90, "stage": "qualified", "value": 500000.0,
                              "currency": "JPY"}}
    lane = rs.select_lane(candidate, {"owner": "o@x", "record_kind": "opportunity"})
    assert lane["lane"] != "dormant_nurture", "an unbanded value is not assumed to be small"


# ============================================ 7. absurd values never break anything

@pytest.mark.parametrize("value", [float("inf"), float("nan"), -5.0, 1e11])
def test_an_unusable_value_is_dropped_not_stored_and_nothing_fails_to_serialise(env, value):
    db, queue = env
    insert(db, detectors.WEB_ENQUIRIES, {"email": "x@y.test", "status": "new",
                                         "received_at": ago(days=2), "estimated_value": value})
    summary = run(detectors.run_detection(db, queue, TENANT))
    assert summary["work_items_created"] == 1, "the lead is still detected"
    case = case_for(db, rc.SOURCE_WEB_ENQUIRY)
    assert case["potential_value"] is None
    assert case["evidence"]["value_rejected"]
    items = run(queue.list_items(tenant_id=TENANT, status="open", queue=detectors.QUEUE_NAME))
    for payload in (case, items, run(rc.summary(db, TENANT)),
                    run(recovery_proof.portfolio(db, TENANT)),
                    run(recovery_proof.case_proof(db, TENANT, case["id"]))):
        json.dumps(payload, allow_nan=False)     # what the API's JSON response does


def test_an_operator_cannot_confirm_a_non_finite_amount(env):
    db, _ = env
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_MISSED_CALL, source_event_id="call:1", reason="r")))
    for amount in (math.nan, math.inf):
        with pytest.raises(attribution.AttributionError):
            run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"],
                                           kind=attribution.OUTCOME_OPERATOR_CONFIRMED,
                                           record_id=f"x{amount}", amount=amount, actor="ops"))


# ========================================== 8. web enquiries, 14. timestamps, 15. calls

def test_test_responded_and_answered_enquiries_are_never_detected(env):
    db, _ = env
    insert(db, detectors.WEB_ENQUIRIES, {"email": "t@x.test", "status": "new", "is_test": True,
                                         "received_at": ago(days=2)})
    insert(db, detectors.WEB_ENQUIRIES, {"email": "r@x.test", "status": "responded",
                                         "received_at": ago(days=2)})
    insert(db, detectors.WEB_ENQUIRIES, {"email": "s@x.test", "status": "new",
                                         "received_at": ago(days=2),
                                         "sla": {"first_response_at": ago(days=1)}})
    live = insert(db, detectors.WEB_ENQUIRIES, {"email": "l@x.test", "status": "new",
                                                "received_at": ago(days=2)})
    found = run(detectors.detect_web_enquiries(db, TENANT))
    assert [d["record_id"] for d in found] == [live["id"]]


def test_a_time_recorded_without_a_timezone_is_read_as_utc_and_says_so(env):
    db, queue = env
    naive = (datetime.now(timezone.utc) - timedelta(hours=8)).replace(tzinfo=None).isoformat()
    insert(db, detectors.CALL_LOGS, {"direction": "inbound", "from_number": "+15550100100",
                                     "outcome": "missed", "occurred_at": naive})
    run(detectors.run_detection(db, queue, TENANT))
    case = case_for(db, rc.SOURCE_MISSED_CALL)
    assert case["evidence"]["timestamp_timezone_assumed"] == "UTC"
    assert "read as UTC" in case["reason"]


def test_a_callback_from_a_differently_formatted_number_resolves_the_missed_call(env):
    db, _ = env
    insert(db, detectors.CALL_LOGS, {"direction": "inbound", "from_number": "+1 (555) 010-0199",
                                     "outcome": "missed", "occurred_at": ago(hours=8)})
    # A busy line: many unrelated outbound calls, the callback among the most recent.
    for i in range(30):
        insert(db, detectors.CALL_LOGS, {"direction": "outbound", "to_number": f"+1555000{i:04d}",
                                         "outcome": "completed", "occurred_at": ago(days=2)})
    insert(db, detectors.CALL_LOGS, {"direction": "outbound", "to_number": "555.010.0199",
                                     "outcome": "completed", "occurred_at": ago(hours=2)})
    assert run(detectors.detect_missed_calls(db, TENANT)) == []


# ============================================ 12, 13, 16. detection hygiene

def test_an_archived_deal_is_not_a_stalled_lead(env):
    db, queue = env
    _, deal = seed_buyer(db)
    run(db.opportunities.update_one({"id": deal["id"]},
                                    {"$set": {"archived_at": "2026-09-01T00:00:00+00:00"}}))
    assert run(second_chance.detect_stalled_leads(db, queue, TENANT)) == []


def test_re_detection_refreshes_the_value_and_records_the_change(env):
    db, queue = env
    _, deal = seed_buyer(db, value=40000.0, currency="GBP")
    run(second_chance.run_detection(db, queue, TENANT))
    run(db.opportunities.update_one({"id": deal["id"]}, {"$set": {"value": 4000.0}}))
    run(second_chance.run_detection(db, queue, TENANT))
    case = case_for(db, rc.SOURCE_DORMANT_DEAL)
    assert case["potential_value"] == 4000.0
    refreshed = [h for h in case["history"] if h["action"] == "potential_value_refreshed"]
    assert refreshed and refreshed[-1]["detail"]["potential_value"] == {"from": 40000.0,
                                                                         "to": 4000.0}
    assert money(db)[0] == {"GBP": 4000.0}


def test_one_bad_detection_does_not_abort_the_tenants_sweep(env):
    db, queue = env
    seed_buyer(db)
    bad = insert(db, "opportunities", {"name": "Dangling", "stage": "proposal", "value": 10.0,
                                       "contact_id": "ct_does_not_exist",
                                       "created_at": "2026-01-01T00:00:00+00:00"})
    summary = run(second_chance.run_detection(db, queue, TENANT))
    assert summary["work_items_created"] == 1
    assert [r["record_id"] for r in summary["rejected"]] == [bad["id"]]


def test_a_closed_case_is_not_given_new_work_when_re_detected(env):
    db, queue = env
    seed_buyer(db)
    run(second_chance.run_detection(db, queue, TENANT))
    case = case_for(db, rc.SOURCE_DORMANT_DEAL)
    run(recovery_lifecycle.close_case(db, tenant_id=TENANT, case_id=case["id"],
                                      reason="not_recoverable"))
    summary = run(second_chance.run_detection(db, queue, TENANT))
    assert summary["work_items_created"] == 0 and summary["skipped_closed_cases"] == 1
    assert run(queue.list_items(tenant_id=TENANT, status="open",
                                queue=second_chance.QUEUE_NAME)) == []


# ================================================= operator close, and isolation

def test_closing_a_case_withdraws_everything_still_pending_on_it(env):
    db, queue = env
    _, case, strategy = _planned_case(db, queue)
    with pytest.raises(rc.RecoveryCaseError):
        run(recovery_lifecycle.close_case(db, tenant_id=TENANT, case_id=case["id"],
                                          reason="because"))
    with pytest.raises(rc.RecoveryCaseNotFound):
        run(recovery_lifecycle.close_case(db, tenant_id=OTHER_TENANT, case_id=case["id"],
                                          reason="duplicate"))
    closed = run(recovery_lifecycle.close_case(db, tenant_id=TENANT, case_id=case["id"],
                                               reason="duplicate", note="Same as rc_1"))
    assert closed["close_reason"] == "duplicate" and closed["close_note"] == "Same as rc_1"
    assert strategy["approval_id"] in closed["withdrawn"]["approvals_cancelled"]
    assert run(aq.get(db, TENANT, strategy["approval_id"]))["status"] == aq.CANCELLED
    assert closed["withdrawn"]["work_item_resolved"] == case["work_item_reference"]
    with pytest.raises(rc.InvalidCaseTransition):
        run(recovery_lifecycle.close_case(db, tenant_id=TENANT, case_id=case["id"],
                                          reason="duplicate"))
    proof = run(recovery_proof.case_proof(db, TENANT, case["id"]))
    assert proof["case"]["close_reason"] == "duplicate"
    assert run(recovery_proof.portfolio(db, TENANT))["cases"]["closed_by_reason"] == \
        {"duplicate": 1}


def test_closing_a_case_in_execution_stops_its_drafted_message(env, app_server):
    db, queue = env
    _, case, strategy = _planned_case(db, queue)
    approval = run(aq.decide(db, tenant_id=TENANT, approval_id=strategy["approval_id"],
                             decision=aq.APPROVED, actor=ADMIN["email"]))
    run(app_server._apply_approval_side_effects(approval, ADMIN))
    result = run(recovery_runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    drafted = run(cv.get_message(db, TENANT, result["steps"][1]["message_id"]))
    assert drafted["status"] == cv.PENDING_APPROVAL

    closed = run(recovery_lifecycle.close_case(db, tenant_id=TENANT, case_id=case["id"],
                                               reason="no_longer_relevant"))
    assert closed["withdrawn"]["messages_refused"] == [drafted["id"]]
    assert run(cv.get_message(db, TENANT, drafted["id"]))["status"] == cv.BLOCKED
    assert run(aq.get(db, TENANT, drafted["approval_id"]))["status"] == aq.CANCELLED, (
        "an operator must not be able to approve -- and send -- outreach for a closed case")
    assert run(rs.get_strategy(db, TENANT, strategy["id"]))["state"] == rs.STATE_APPROVED


def test_a_run_queued_before_the_case_closed_is_a_no_op_not_a_failure(env, app_server):
    db, queue = env
    _, case, strategy = _planned_case(db, queue)
    approval = run(aq.decide(db, tenant_id=TENANT, approval_id=strategy["approval_id"],
                             decision=aq.APPROVED, actor=ADMIN["email"]))
    run(app_server._apply_approval_side_effects(approval, ADMIN))
    run(recovery_lifecycle.close_case(db, tenant_id=TENANT, case_id=case["id"],
                                      reason="resolved"))
    result = run(recovery_runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    assert result["skipped"] is True and result["outbound_drafted"] == 0


def test_closing_a_proposed_case_withdraws_its_strategy(env):
    db, queue = env
    _, case, strategy = _planned_case(db, queue)
    closed = run(recovery_lifecycle.close_case(db, tenant_id=TENANT, case_id=case["id"],
                                               reason="spam"))
    assert closed["withdrawn"]["strategy_withdrawn"] == strategy["id"]
    assert run(rs.summary(db, TENANT))["proposed"] == 0


def test_reconciliation_never_reaches_another_tenant(env):
    db, queue = env
    _, deal = seed_buyer(db)
    run(second_chance.run_detection(db, queue, TENANT))
    run(db.opportunities.update_one({"id": deal["id"]}, {"$set": {"stage": "closed_lost"}}))
    summary = run(recovery_reconcile.reconcile_tenant(db, OTHER_TENANT))
    assert summary["examined"] == 0
    assert case_for(db, rc.SOURCE_DORMANT_DEAL)["state"] == rc.DETECTED


# =============================================================== the dashboard

def test_the_dashboard_never_sums_money_across_currencies(env, app_server):
    db, _ = env
    for value, currency, stage in ((1000.0, "USD", "proposal"), (2000.0, "GBP", "proposal"),
                                   (500.0, "GBP", "closed_won")):
        insert(db, "opportunities", {"name": "d", "value": value, "currency": currency,
                                     "stage": stage})
    data = run(app_server.dashboard(user={"tenant_id": TENANT}))
    assert data["pipeline_value_by_currency"] == {"USD": 1000.0, "GBP": 2000.0}
    assert data["won_value_by_currency"] == {"GBP": 500.0}
    assert data["pipeline_value"] is None, "no single figure is true across two currencies"


def test_the_outcome_route_refuses_a_second_booking_with_409_and_an_unrelated_one_with_422(
        env, app_server):
    from fastapi import HTTPException
    db, _ = env
    _, deal = seed_buyer(db, value=40000.0, currency="GBP", stage="closed_won")
    _, other_deal = seed_buyer(db, stage="closed_won")
    first, second = (run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_WEB_ENQUIRY, source_event_id=f"web_enquiry:{i}",
        reason="r", opportunity_id=deal["id"]))) for i in range(2))

    def post(case, record_id):
        inp = app_server.RecordOutcomeInput(case_id=case["id"], kind="deal_won",
                                            record_id=record_id)
        return run(app_server.record_attribution_outcome(inp, user=ADMIN))

    assert post(first, deal["id"])["claim"] == attribution.CLAIM_UNATTRIBUTED
    with pytest.raises(HTTPException) as duplicate:
        post(second, deal["id"])
    assert duplicate.value.status_code == 409
    assert duplicate.value.detail["case_id"] == first["id"]
    with pytest.raises(HTTPException) as unrelated:
        post(second, other_deal["id"])
    assert unrelated.value.status_code == 422


def test_a_negative_or_infinite_deal_value_is_refused(app_server):
    from pydantic import ValidationError
    for bad in ({"name": "x", "value": -1}, {"name": "x", "value": math.inf},
                {"name": "x", "currency": "$"}):
        with pytest.raises(ValidationError):
            app_server.OppInput(**bad)
    assert app_server.OppInput(name="x", currency="gbp").currency == "GBP"


# ============================================== review round two: the regressions
#
# Each test below reproduces a defect an adversarial review of the first round of fixes
# found, and asserts the money a buyer would read.

@pytest.mark.parametrize("order", [("second_chance", "detectors"),
                                   ("detectors", "second_chance")])
def test_a_shared_deals_win_goes_to_the_same_case_whichever_sweep_runs_first(env, order):
    """The two sweeps reconcile different sources. Choosing the claimant from only the
    running sweep's cases booked the win against the dormant-deal case or the enquiry
    whose outreach actually reached the client, depending on which cron fired first."""
    db, queue = env
    contact, deal = seed_buyer(db)
    insert(db, detectors.WEB_ENQUIRIES, {
        "email": "sam@buyer.test", "status": "new", "received_at": ago(days=3),
        "contact_id": contact["id"], "opportunity_id": deal["id"],
        "estimated_value": 40000.0, "currency": "GBP"})
    run(second_chance.run_detection(db, queue, TENANT))
    run(detectors.run_detection(db, queue, TENANT))
    walk_to_engaged(db, case_for(db, rc.SOURCE_WEB_ENQUIRY))
    win(db, deal)

    sweeps = {"second_chance": second_chance.run_detection,
              "detectors": detectors.run_detection}
    for name in order:
        run(sweeps[name](db, queue, TENANT))
    assert case_for(db, rc.SOURCE_WEB_ENQUIRY)["state"] == rc.RECOVERED
    assert case_for(db, rc.SOURCE_DORMANT_DEAL)["close_reason"] == \
        "sale_recorded_on_another_case"
    assert money(db) == ({}, {"GBP": 40000.0}, {})


def test_a_contact_only_case_groups_with_the_deal_its_contact_is_on(env):
    """A deal stores its people as `contact_ids`; the dormant-deal case for it knows no
    contact, and an older enquiry from the same buyer knows only the contact. One buyer,
    one deal: £40,000 of open potential, not £80,000."""
    db, queue = env
    contact, deal = seed_buyer(db)
    colleague = insert(db, "contacts", {"name": "Alex Colleague"})
    run(db.opportunities.update_one({"id": deal["id"]},
                                    {"$push": {"contact_ids": colleague["id"]}}))
    insert(db, detectors.WEB_ENQUIRIES, {
        "email": "sam@buyer.test", "status": "new", "received_at": ago(days=5),
        "contact_id": contact["id"], "estimated_value": 40000.0, "currency": "GBP"})
    run(second_chance.run_detection(db, queue, TENANT))
    run(detectors.run_detection(db, queue, TENANT))
    assert case_for(db, rc.SOURCE_DORMANT_DEAL).get("contact_id") is None
    assert money(db)[0] == {"GBP": 40000.0}


def test_confirmed_value_is_labelled_in_the_currency_the_money_arrived_in(env):
    """A missed call carries no value, so its case is in the default USD; the deal it led
    to was won in pounds. The confirmed £40,000 was reported as $40,000."""
    db, _ = env
    contact, deal = seed_buyer(db)
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_MISSED_CALL, source_event_id="call:1",
        reason="missed", contact_id=contact["id"])))
    assert case["currency"] == "USD"
    walk_to_engaged(db, case)
    win(db, deal)
    entry = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"],
                                           kind=attribution.OUTCOME_DEAL_WON,
                                           record_id=deal["id"], actor="ops"))
    assert entry["claim"] == attribution.CLAIM_ATTRIBUTED
    stored = run(db[attribution.COLLECTION].find_one({"id": entry["id"]}, {"_id": 0}))
    assert "confirming_since" not in stored, "a finished confirmation is not in flight"

    assert run(rc.get_case(db, TENANT, case["id"]))["confirmed_currency"] == "GBP"
    assert run(rc.summary(db, TENANT))["confirmed_recovered_value_by_currency"] == \
        {"GBP": 40000.0}
    value = run(recovery_proof.case_proof(db, TENANT, case["id"]))["value"]
    assert (value["confirmed_currency"], value["confirmed_recovered_value"]) == \
        ("GBP", 40000.0)
    assert money(db)[1] == {"GBP": 40000.0}
    # A confirmation written before the field existed: the evidence names the currency.
    run(db[rc.COLLECTION].update_one({"id": case["id"]},
                                     {"$unset": {"confirmed_currency": ""}}))
    assert run(rc.summary(db, TENANT))["confirmed_recovered_value_by_currency"] == \
        {"GBP": 40000.0}


def test_an_operator_confirmation_and_the_deals_later_win_are_one_sale(env):
    """Keyed on the operator's free-text reference, the deal's win booked the same £40,000
    again as unattributed outcome value."""
    db, _ = env
    contact, deal = seed_buyer(db)
    worked = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_DORMANT_DEAL,
        source_event_id=f"opportunity:{deal['id']}", reason="dormant",
        opportunity_id=deal["id"], potential_value=40000.0, currency="GBP")))
    run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_WEB_ENQUIRY, source_event_id="web_enquiry:e1",
        reason="enquiry", opportunity_id=deal["id"], contact_id=contact["id"],
        potential_value=40000.0, currency="GBP")))
    walk_to_engaged(db, worked)
    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=worked["id"],
        kind=attribution.OUTCOME_OPERATOR_CONFIRMED, record_id="signed contract",
        amount=40000.0, currency="GBP", actor="ops"))
    assert entry["sale_key"] == f"deal:{deal['id']}"

    win(db, deal)
    summary = run(recovery_reconcile.reconcile_tenant(db, TENANT))
    assert summary["outcomes"] == [] and summary["errors"] == []
    assert money(db) == ({}, {"GBP": 40000.0}, {})


def test_two_jobs_paid_in_one_client_workspace_are_two_sales(env):
    """A client's workspace was created from the deal they first signed. Inferring that
    deal for every invoice in the workspace folded the second job into the first sale."""
    db, queue = env
    deal = insert(db, "opportunities", {"name": "Original", "stage": "closed_won",
                                        "value": 1000.0, "currency": "USD",
                                        "created_at": ago(days=400)})
    workspace = insert(db, "workspaces", {"name": "Client", "opportunity_id": deal["id"]})
    estimates = [insert(db, "estimates", {
        "title": f"Job {i}", "status": "sent", "total": 7000.0 + i, "currency": "USD",
        "workspace_id": workspace["id"], "created_at": ago(days=20), "sent_at": ago(days=20)})
        for i in (1, 2)]
    run(detectors.run_detection(db, queue, TENANT))
    for estimate in estimates:
        insert(db, "invoices", {"estimate_id": estimate["id"],
                                "workspace_id": workspace["id"], "total": estimate["total"],
                                "currency": "USD", "status": "paid", "paid_at": now()})
    run(recovery_reconcile.reconcile_tenant(db, TENANT))
    assert money(db) == ({}, {}, {"USD": 14003.0})


def test_a_woken_deal_that_is_re_priced_shows_its_current_value(env):
    db, queue = env
    _, deal = seed_buyer(db)
    run(second_chance.run_detection(db, queue, TENANT))
    assert money(db)[0] == {"GBP": 40000.0}
    # The deal wakes up -- so it is no longer detected -- and is re-priced.
    run(db.opportunities.update_one({"id": deal["id"]},
                                    {"$set": {"value": 4000.0, "updated_at": now()}}))
    run(second_chance.run_detection(db, queue, TENANT))
    assert money(db)[0] == {"GBP": 4000.0}
    history = case_for(db, rc.SOURCE_DORMANT_DEAL)["history"]
    assert any(h["action"] == "potential_value_refreshed" for h in history)


def test_a_dormant_deal_case_recorded_in_the_wrong_currency_takes_its_deals(env):
    """Cases opened before they carried the deal's currency said USD on a sterling deal."""
    db, _ = env
    _, deal = seed_buyer(db)
    run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_DORMANT_DEAL,
        source_event_id=f"opportunity:{deal['id']}", reason="dormant",
        opportunity_id=deal["id"], potential_value=40000.0, currency="USD")))
    assert money(db)[0] == {"USD": 40000.0}
    run(recovery_reconcile.reconcile_tenant(db, TENANT))
    assert money(db)[0] == {"GBP": 40000.0}


@pytest.mark.parametrize("stage, expected", [
    ("closed_won", ({}, {}, {"GBP": 40000.0})),
    ("closed_lost", ({}, {}, {})),
])
def test_a_contact_only_case_settles_with_its_contacts_only_deal(env, stage, expected):
    """The enquiry knew only the contact. When the contact's one deal closed, the enquiry
    stayed open: the same £40,000 was open potential and an outcome at once."""
    db, queue = env
    contact, deal = seed_buyer(db)
    insert(db, detectors.WEB_ENQUIRIES, {
        "email": "sam@buyer.test", "status": "new", "received_at": ago(days=5),
        "contact_id": contact["id"], "estimated_value": 40000.0, "currency": "GBP"})
    run(second_chance.run_detection(db, queue, TENANT))
    run(detectors.run_detection(db, queue, TENANT))
    win(db, deal, stage=stage)
    run(detectors.run_detection(db, queue, TENANT))  # the enquiry's own sweep alone
    assert case_for(db, rc.SOURCE_WEB_ENQUIRY)["state"] == rc.CLOSED
    assert case_for(db, rc.SOURCE_DORMANT_DEAL)["state"] == rc.CLOSED
    assert money(db) == expected


def test_recording_a_no_show_confirms_the_case_rather_than_closing_it(env):
    db, queue = env
    contact = insert(db, "contacts", {"name": "Pat"})
    appointment = insert(db, "appointments", {
        "title": "Consult", "status": "scheduled", "contact_id": contact["id"],
        "start_at": ago(hours=30), "end_at": ago(hours=29)})
    run(detectors.run_detection(db, queue, TENANT))
    case = case_for(db, rc.SOURCE_APPOINTMENT_NO_SHOW)
    # The operator records what happened: the client did not turn up.
    run(db.appointments.update_one({"id": appointment["id"]}, {"$set": {"status": "no_show"}}))
    run(detectors.run_detection(db, queue, TENANT))
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.DETECTED

    # The client books again: that resolves it.
    later = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    insert(db, "appointments", {"title": "Consult", "status": "scheduled",
                                "contact_id": contact["id"], "start_at": later})
    run(recovery_reconcile.reconcile_tenant(db, TENANT))
    closed = run(rc.get_case(db, TENANT, case["id"]))
    assert (closed["state"], closed["close_reason"]) == (rc.CLOSED, "source_resolved")


def test_a_legacy_invoice_entry_and_a_new_win_of_its_deal_are_one_sale(env):
    """An entry written before entries carried a sale key was matched only on its own
    kind and record, so the deal's win booked the invoice's money a second time."""
    db, _ = env
    deal = insert(db, "opportunities", {
        "name": "Fit-out", "stage": "closed_won", "value": 5000.0, "currency": "USD",
        "created_at": ago(days=200), "stage_history": [{"to": "closed_won", "at": ago(days=1)}]})
    invoice = insert(db, "invoices", {"total": 5000.0, "currency": "USD", "status": "paid",
                                      "paid_at": ago(days=1), "opportunity_id": deal["id"]})
    run(db[attribution.COLLECTION].insert_one({
        "id": "attr_legacy", "tenant_id": TENANT, "case_id": "rc_old",
        "outcome": {"kind": "invoice_paid", "record_id": invoice["id"], "amount": 5000.0},
        "claim": attribution.CLAIM_UNATTRIBUTED, "basis": "no_contact", "currency": "USD",
        "recorded_at": ago(days=1)}))
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_DORMANT_DEAL,
        source_event_id=f"opportunity:{deal['id']}", reason="dormant",
        opportunity_id=deal["id"], potential_value=5000.0)))
    run(db[rc.COLLECTION].update_one({"id": case["id"]}, {"$set": {"created_at": ago(days=30)}}))

    for _ in range(2):
        assert run(recovery_reconcile.reconcile_tenant(db, TENANT))["outcomes"] == []
    assert run(rc.get_case(db, TENANT, case["id"]))["close_reason"] == \
        "sale_recorded_on_another_case"
    assert money(db) == ({}, {}, {"USD": 5000.0})


def test_an_estimate_paid_after_it_was_invoiced_is_recorded_once(env):
    """Converting an estimate into an invoice closed its case, so the payment, when it
    came, was recorded against nothing."""
    db, queue = env
    workspace = insert(db, "workspaces", {"name": "Client"})
    estimate = insert(db, "estimates", {
        "title": "Job", "status": "sent", "total": 7000.0, "currency": "USD",
        "workspace_id": workspace["id"], "created_at": ago(days=20), "sent_at": ago(days=20)})
    run(detectors.run_detection(db, queue, TENANT))
    case = case_for(db, rc.SOURCE_UNANSWERED_ESTIMATE)
    invoice = insert(db, "invoices", {"estimate_id": estimate["id"],
                                      "workspace_id": workspace["id"], "total": 7000.0,
                                      "currency": "USD", "status": "draft",
                                      "created_at": now()})
    run(db.estimates.update_one({"id": estimate["id"]},
                                {"$set": {"invoice_id": invoice["id"], "status": "approved"}}))
    run(recovery_reconcile.reconcile_tenant(db, TENANT))
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.DETECTED, \
        "accepted and invoiced, the case waits for the money"
    assert money(db)[0] == {"USD": 7000.0}

    run(db.invoices.update_one({"id": invoice["id"]},
                               {"$set": {"status": "paid", "paid_at": now()}}))
    first = run(recovery_reconcile.reconcile_tenant(db, TENANT))
    second = run(recovery_reconcile.reconcile_tenant(db, TENANT))
    assert [(o["kind"], o["claim"]) for o in first["outcomes"]] == \
        [(attribution.OUTCOME_INVOICE_PAID, attribution.CLAIM_UNATTRIBUTED)]
    assert second["outcomes"] == []
    assert money(db) == ({}, {}, {"USD": 7000.0})


def test_a_win_that_cannot_be_booked_is_refused_once_not_on_every_sweep(env):
    """A deal saved with currency "$" before currencies were validated: its win made the
    ledger raise on every sweep, for ever, while the case stayed open."""
    db, queue = env
    _, deal = seed_buyer(db, currency="$")
    run(second_chance.run_detection(db, queue, TENANT))
    case = case_for(db, rc.SOURCE_DORMANT_DEAL)
    win(db, deal)
    first = run(recovery_reconcile.reconcile_tenant(db, TENANT))
    assert first["errors"] == []
    assert [r["case_id"] for r in first["refused"]] == [case["id"]]
    assert "currency" in first["refused"][0]["reason"]
    assert run(rc.get_case(db, TENANT, case["id"]))["close_reason"] == "outcome_refused"
    second = run(recovery_reconcile.reconcile_tenant(db, TENANT))
    assert second["errors"] == [] and "refused" not in second and second["examined"] == 0


def test_reconciliation_leaves_a_case_alone_while_its_outcome_is_being_confirmed(env):
    """`record_outcome` writes its entry unattributed and then confirms the case. A sweep
    that closed the case in between made the confirmation fail, and attributed revenue
    was booked as unattributed for good."""
    db, queue = env
    _, deal = seed_buyer(db)
    run(second_chance.run_detection(db, queue, TENANT))
    case = case_for(db, rc.SOURCE_DORMANT_DEAL)
    walk_to_engaged(db, case)
    run(db[attribution.COLLECTION].insert_one({
        "id": "attr_in_flight", "tenant_id": TENANT, "case_id": case["id"],
        "sale_key": f"deal:{deal['id']}", "claim": attribution.CLAIM_UNATTRIBUTED,
        "case_updated": False, "currency": "GBP",
        "outcome": {"kind": attribution.OUTCOME_DEAL_WON, "record_id": deal["id"],
                    "amount": 40000.0},
        "recorded_at": now(), "confirming_since": now()}))
    summary = run(recovery_reconcile.reconcile_tenant(db, TENANT))
    assert summary["skipped_in_flight"] == 1
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.ENGAGED

    # A confirmation that never finished does not shield its case for ever.
    run(db[attribution.COLLECTION].update_one({"id": "attr_in_flight"},
                                              {"$set": {"confirming_since": ago(hours=1)}}))
    run(recovery_reconcile.reconcile_tenant(db, TENANT))
    assert run(rc.get_case(db, TENANT, case["id"]))["close_reason"] == "outcome_recorded"


def test_an_answered_callback_is_recognised_however_its_outcome_is_written(env):
    db, queue = env
    insert(db, detectors.CALL_LOGS, {"direction": "inbound", "from_number": "+44 1632 970002",
                                     "outcome": "missed", "occurred_at": ago(hours=8)})
    run(detectors.run_detection(db, queue, TENANT))
    case = case_for(db, rc.SOURCE_MISSED_CALL)
    insert(db, detectors.CALL_LOGS, {"direction": "inbound", "from_number": "01632 970002",
                                     "outcome": " Answered ", "occurred_at": ago(hours=2)})
    run(recovery_reconcile.reconcile_tenant(db, TENANT))
    assert run(rc.get_case(db, TENANT, case["id"]))["close_reason"] == "source_resolved"


def test_an_operator_cannot_close_a_recovered_case(env):
    """Its confirmed value stays counted, so closing it as "not recoverable" would leave
    the report contradicting itself."""
    from fastapi import APIRouter, HTTPException

    import operations_routes
    db, _ = env
    contact, deal = seed_buyer(db)
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_WEB_ENQUIRY, source_event_id="web_enquiry:w1",
        reason="enquiry", opportunity_id=deal["id"], contact_id=contact["id"])))
    walk_to_engaged(db, case)
    win(db, deal)
    run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"],
                                   kind=attribution.OUTCOME_DEAL_WON, record_id=deal["id"],
                                   actor="ops"))
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.RECOVERED

    async def record_event(*args, **kwargs):
        return None

    router = APIRouter()
    operations_routes.register_operations_routes(router, db, record_event, lambda: ADMIN,
                                                 lambda role: (lambda: ADMIN))
    close = next(route.endpoint for route in router.routes
                 if route.path == "/recovery-cases/{case_id}/close")
    with pytest.raises(HTTPException) as refused:
        run(close(case["id"], operations_routes.CaseCloseInput(reason="not_recoverable"),
                  user=ADMIN))
    assert refused.value.status_code == 409
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.RECOVERED


def test_a_case_closed_while_its_run_is_drafting_gets_nothing_more(env, app_server,
                                                                   monkeypatch):
    db, queue = env
    _, case, strategy = _planned_case(db, queue)
    approval = run(aq.decide(db, tenant_id=TENANT, approval_id=strategy["approval_id"],
                             decision=aq.APPROVED, actor=ADMIN["email"]))
    run(app_server._apply_approval_side_effects(approval, ADMIN))

    original = recovery_runner._run_outbound_step

    async def closed_just_before_drafting(*args, **kwargs):
        # Reconciliation closes the case between the run's check and its draft.
        await recovery_lifecycle.close_if_open(db, tenant_id=TENANT, case_id=case["id"],
                                               reason="source_resolved")
        return await original(*args, **kwargs)

    monkeypatch.setattr(recovery_runner, "_run_outbound_step", closed_just_before_drafting)
    result = run(recovery_runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    assert result["skipped"] is True
    drafted = [step for step in result["steps"] if step.get("message_id")]
    assert len(drafted) == 1 and result["steps"][-1] is drafted[0], \
        "the run stopped at the close instead of drafting the rest of the plan"
    message = run(cv.get_message(db, TENANT, drafted[0]["message_id"]))
    assert message["status"] == cv.BLOCKED
    assert run(aq.get(db, TENANT, message["approval_id"]))["status"] == aq.CANCELLED


def test_a_rejected_plan_closes_its_case_through_the_lifecycle_by_default(env):
    """The composer's own rejected path called the sync without the lifecycle's close, so
    the case closed and its pending approval stayed open to be decided."""
    db, queue = env
    _, case, strategy = _planned_case(db, queue)
    closed = run(rs.sync_case_with_strategy(db, TENANT,
                                            {**strategy, "state": rs.STATE_REJECTED}))
    assert closed["close_reason"] == "strategy_rejected"
    assert "withdrawn" in closed
    assert run(aq.get(db, TENANT, strategy["approval_id"]))["status"] == aq.CANCELLED


def test_the_dashboard_leaves_out_archived_and_negative_deals(env, app_server):
    db, _ = env
    insert(db, "opportunities", {"name": "live", "value": 1000.0, "currency": "USD",
                                 "stage": "proposal"})
    insert(db, "opportunities", {"name": "archived", "value": 9000.0, "currency": "USD",
                                 "stage": "proposal", "archived_at": now()})
    insert(db, "opportunities", {"name": "negative", "value": -500.0, "currency": "USD",
                                 "stage": "closed_won"})
    data = run(app_server.dashboard(user={"tenant_id": TENANT}))
    assert data["pipeline_value_by_currency"] == {"USD": 1000.0}
    assert data["won_value_by_currency"] == {}


def test_a_deal_edit_must_carry_real_money(app_server):
    from pydantic import ValidationError

    import crm_core
    for bad in ({"currency": "$"}, {"currency": "pounds"}, {"value": -1},
                {"value": math.inf}, {"value": 2e10}):
        with pytest.raises(ValidationError):
            crm_core.DealPatch(**bad)
    assert crm_core.DealPatch(currency=" gbp ").currency == "GBP"
    with pytest.raises(ValidationError):
        app_server.OppInput(name="x", value=2e10)
