"""A review of the round-three ledger fixes, as tests.

Each fix closed one way of counting money twice, and each opened a way of counting it
wrongly: an import dated an old win to today, a separate invoice could not be booked at
all, a free-text reference like "cash" became unique across the tenant, a duplicate
stayed in the case totals, and a deal and its invoice booked at the same moment were
both counted. These are the regressions, pinned.
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

import attribution
import conversations as cv
import recovery_case as rc

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
API = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/") + "/api"
TENANT = "ten_ledger_a"

_LOOP = None


def run(coro):
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


def iso(days_ago=0):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


@pytest.fixture()
def db():
    name = f"cv_ledger_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[name]
    run(cv.ensure_indexes(database))
    run(rc.ensure_indexes(database))
    run(attribution.ensure_indexes(database))
    yield database
    run(client.drop_database(name))
    client.close()


def contacted_case(db, **references):
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_DORMANT_DEAL,
        source_event_id=f"ev_{uuid.uuid4().hex[:10]}", occurred_at=iso(30),
        reason="Quiet", potential_value=1000.0, currency="USD"), actor="detector"))
    if references:
        run(db[rc.COLLECTION].update_one({"id": case["id"]}, {"$set": references}))
    for state in (rc.PLANNED, rc.AWAITING_APPROVAL, rc.APPROVED, rc.EXECUTING, rc.ENGAGED):
        run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=state, actor="t"))
    conversation = run(cv.create_conversation(
        db, tenant_id=TENANT, channel=cv.CHANNEL_EMAIL, actor="agent", subject="R",
        recovery_case_id=case["id"],
        participants=[{"kind": cv.PARTICIPANT_CONTACT, "address": "b@client.example"}]))
    run(db[cv.MESSAGES].insert_one({
        "id": f"msg_{uuid.uuid4().hex[:10]}", "tenant_id": TENANT,
        "conversation_id": conversation["id"], "channel": cv.CHANNEL_EMAIL,
        "direction": cv.OUTBOUND, "status": cv.SENT, "body": "Hi", "provider": "gmail",
        "created_at": iso(7), "sent_at": iso(7),
        "provider_message_id": f"p_{uuid.uuid4().hex[:8]}", "history": []}))
    return run(rc.get_case(db, TENANT, case["id"]))


def won_deal(db, deal_id="opp_1", value=10000.0, history=None):
    run(db.workspaces.insert_one({"id": f"ws_{deal_id}", "tenant_id": TENANT,
                                  "opportunity_id": deal_id, "company_id": "co_1"}))
    run(db.opportunities.insert_one({
        "id": deal_id, "tenant_id": TENANT, "value": value, "currency": "USD",
        "stage": "closed_won", "company_id": "co_1",
        "stage_history": history if history is not None else [
            {"from": "proposal", "to": "closed_won", "at": iso(2)}]}))


def paid_invoice(db, *, total, workspace_id=None):
    invoice = {"id": f"inv_{uuid.uuid4().hex[:10]}", "tenant_id": TENANT, "total": total,
               "currency": "USD", "status": "paid", "payment_status": "paid",
               "paid_at": iso(1), "created_at": iso(3), "workspace_id": workspace_id,
               "company_id": "co_1"}
    run(db.invoices.insert_one(dict(invoice)))
    return invoice


def book(db, case, kind, record_id, **kwargs):
    return run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"],
                                          kind=kind, record_id=record_id, actor="ops",
                                          **kwargs))


# ---------------------------------------------------------------- dating a win

def test_a_win_recorded_by_an_import_is_not_dated_by_the_import(db):
    case = contacted_case(db, company_id="co_1")
    won_deal(db, history=[{"from": "lead", "to": "closed_won", "at": iso(0),
                           "via": "import"}])
    with pytest.raises(attribution.AttributionError, match="does not say when it was"):
        book(db, case, attribution.OUTCOME_DEAL_WON, "opp_1")


# ---------------------------------------------------------------- related money

def test_a_separate_invoice_can_be_booked_when_the_operator_says_it_is_separate(db):
    case = contacted_case(db, company_id="co_1")
    won_deal(db)
    book(db, case, attribution.OUTCOME_DEAL_WON, "opp_1")
    extra = paid_invoice(db, total=2500.0, workspace_id="ws_opp_1")
    with pytest.raises(attribution.RecordAlreadyBooked):
        book(db, case, attribution.OUTCOME_INVOICE_PAID, extra["id"])
    entry = book(db, case, attribution.OUTCOME_INVOICE_PAID, extra["id"],
                 separate_engagement=True)
    assert entry["separate_engagement"]["asserted_by"] == "ops"
    totals = run(attribution.totals(db, TENANT))
    assert totals["attributed_recovered_value_by_currency"] == {"USD": 12500.0}


def test_a_deal_and_its_invoice_booked_at_once_are_counted_once(db):
    first, second = contacted_case(db, company_id="co_1"), contacted_case(db, company_id="co_1")
    won_deal(db)
    invoice = paid_invoice(db, total=10000.0, workspace_id="ws_opp_1")

    async def both():
        return await asyncio.gather(
            attribution.record_outcome(db, tenant_id=TENANT, case_id=first["id"],
                                       kind=attribution.OUTCOME_DEAL_WON, record_id="opp_1",
                                       actor="ops"),
            attribution.record_outcome(db, tenant_id=TENANT, case_id=second["id"],
                                       kind=attribution.OUTCOME_INVOICE_PAID,
                                       record_id=invoice["id"], actor="ops"),
            return_exceptions=True)

    results = run(both())
    assert sum(1 for r in results if isinstance(r, attribution.RecordAlreadyBooked)) == 1
    totals = run(attribution.totals(db, TENANT))
    assert totals["attributed_recovered_value_by_currency"] == {"USD": 10000.0}


# ---------------------------------------------------------------- operator references

def test_the_same_free_text_reference_on_two_clients_is_two_payments(db):
    a = contacted_case(db, company_id="co_a")
    b = contacted_case(db, company_id="co_b")
    book(db, a, attribution.OUTCOME_OPERATOR_CONFIRMED, "cash", amount=500.0,
         occurred_at=iso(1))
    book(db, b, attribution.OUTCOME_OPERATOR_CONFIRMED, "Cash", amount=800.0,
         occurred_at=iso(1))
    totals = run(attribution.totals(db, TENANT))
    assert totals["attributed_recovered_value_by_currency"] == {"USD": 1300.0}


def test_legacy_operator_entries_on_different_clients_are_not_marked_duplicates(db):
    for n, (case_id, ref, amount) in enumerate((("rc_a", "cash", 500.0),
                                                ("rc_b", "Cash", 800.0))):
        run(db[attribution.COLLECTION].insert_one({
            "id": f"attr_legacy_{n}", "tenant_id": TENANT, "case_id": case_id,
            "claim": attribution.CLAIM_ATTRIBUTED, "currency": "USD",
            "outcome": {"kind": attribution.OUTCOME_OPERATOR_CONFIRMED, "record_id": ref,
                        "collection": None, "amount": amount},
            "recorded_at": iso(5 - n)}))
    run(attribution.ensure_indexes(db))
    totals = run(attribution.totals(db, TENANT))
    assert totals["attributed_recovered_value_by_currency"] == {"USD": 1300.0}


# ---------------------------------------------------------------- the case totals

def test_a_duplicate_found_by_the_backfill_leaves_the_case_totals_too(db):
    cases = []
    for n in range(2):
        case = run(rc.open_case(db, rc.normalize_event(
            tenant_id=TENANT, source=rc.SOURCE_MISSED_CALL, source_event_id=f"call_{n}",
            reason="Rang out", currency="USD"), actor="t"))
        run(db[rc.COLLECTION].update_one({"id": case["id"]}, {"$set": {
            "state": rc.RECOVERED, "confirmed_value": 1000.0,
            "confirmed_value_evidence": {"attribution_entry_id": f"attr_dup_{n}"}}}))
        run(db[attribution.COLLECTION].insert_one({
            "id": f"attr_dup_{n}", "tenant_id": TENANT, "case_id": case["id"],
            "claim": attribution.CLAIM_ATTRIBUTED, "currency": "USD",
            "outcome": {"kind": attribution.OUTCOME_INVOICE_PAID, "record_id": "inv_twice",
                        "collection": "invoices", "amount": 1000.0},
            "recorded_at": iso(5 - n)}))
        cases.append(case)
    run(attribution.ensure_indexes(db))
    summary = run(rc.summary(db, TENANT))
    assert summary["confirmed_recovered_value_by_currency"] == {"USD": 1000.0}


# ---------------------------------------------------------------- imports

def _admin():
    response = requests.post(f"{API}/auth/register", timeout=30, json={
        "email": f"ledger_{uuid.uuid4().hex[:10]}@example.com",
        "password": "LedgerHardening2026!", "name": "L"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_a_value_only_import_update_leaves_a_won_deal_won():
    headers = _admin()
    name = f"Acme {uuid.uuid4().hex[:6]}"
    created = requests.post(f"{API}/opportunities", headers=headers, timeout=30, json={
        "name": name, "value": 1000, "stage": "closed_won"})
    assert created.status_code == 200, created.text
    imported = requests.post(f"{API}/import/deals", headers=headers, timeout=30, json={
        "csv": f"name,value\n{name},5000\n", "on_duplicate": "update"})
    assert imported.status_code == 200, imported.text
    deal = requests.get(f"{API}/opportunities/{created.json()['id']}", headers=headers,
                        timeout=30).json()["deal"]
    assert deal["stage"] == "closed_won" and deal["value"] == 5000
