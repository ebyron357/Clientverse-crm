"""The proof surface.

A buyer reading this report is deciding whether to believe the product. So what is
asserted here is mostly about what the numbers are *not* allowed to do: potential value
must never be added to confirmed value, drafted must never be counted as sent, and an
outcome this system did not cause must still appear -- as an unattributed one -- rather
than being quietly left out of the denominator.
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import attribution
import conversations as cv
import recovery_case as rc
import recovery_proof

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT = "ten_proof_a"
OTHER_TENANT = "ten_proof_b"

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
    db_name = f"cv_proof_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[db_name]
    run(cv.ensure_indexes(database))
    run(rc.ensure_indexes(database))
    run(attribution.ensure_indexes(database))
    yield database
    run(client.drop_database(db_name))
    client.close()


def make_case(db, *, tenant_id=TENANT, potential=4000.0, currency="USD",
              detected_days_ago=30):
    return run(rc.open_case(db, rc.normalize_event(
        tenant_id=tenant_id, source=rc.SOURCE_DORMANT_DEAL,
        source_event_id=f"ev_{uuid.uuid4().hex[:10]}", occurred_at=iso(detected_days_ago),
        reason="No contact for 45 days", potential_value=potential, currency=currency,
        title="Renewal at risk"), actor="detector"))


def engage(db, case, *, tenant_id=TENANT):
    for state in (rc.PLANNED, rc.AWAITING_APPROVAL, rc.APPROVED, rc.EXECUTING, rc.ENGAGED):
        run(rc.set_state(db, tenant_id=tenant_id, case_id=case["id"], state=state,
                         actor="recovery-runner"))


def conversation_for(db, case, *, tenant_id=TENANT):
    return run(cv.create_conversation(
        db, tenant_id=tenant_id, channel=cv.CHANNEL_EMAIL, actor="agent:composer",
        subject="Recovery", recovery_case_id=case["id"], contact_id="ct_1",
        participants=[{"kind": cv.PARTICIPANT_CONTACT, "id": "ct_1",
                       "address": "buyer@client.test"}]))


def message(db, conversation, *, direction, status, days_ago=10, tenant_id=TENANT):
    doc = {"id": f"msg_{uuid.uuid4().hex[:10]}", "tenant_id": tenant_id,
           "conversation_id": conversation["id"], "channel": cv.CHANNEL_EMAIL,
           "direction": direction, "status": status, "body": "Following up",
           "provider": "gmail", "created_at": iso(days_ago),
           "sent_at": iso(days_ago) if status in (cv.SENT, cv.DELIVERED) else None,
           "history": []}
    if status in (cv.SENT, cv.DELIVERED):
        doc["provider_message_id"] = f"prov_{uuid.uuid4().hex[:8]}"
    run(db[cv.MESSAGES].insert_one(dict(doc)))
    return doc


def paid_invoice(db, *, total=4000.0, currency="USD", days_ago=1, tenant_id=TENANT):
    invoice = {"id": f"inv_{uuid.uuid4().hex[:10]}", "tenant_id": tenant_id,
               "total": total, "currency": currency, "status": "paid",
               "payment_status": "paid", "paid_at": iso(days_ago),
               "created_at": iso(days_ago + 5)}
    run(db.invoices.insert_one(dict(invoice)))
    return invoice


# --------------------------------------------------------------------- case proof

def test_case_proof_shows_the_whole_chain_from_detection_to_attribution(db):
    case = make_case(db)
    conversation = conversation_for(db, case)
    message(db, conversation, direction=cv.OUTBOUND, status=cv.SENT, days_ago=10)
    message(db, conversation, direction=cv.OUTBOUND, status=cv.DRAFT, days_ago=9)
    message(db, conversation, direction=cv.INBOUND, status=cv.RECEIVED, days_ago=5)
    engage(db, case)
    invoice = paid_invoice(db, total=4000.0)
    run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"],
                                   kind=attribution.OUTCOME_INVOICE_PAID,
                                   record_id=invoice["id"], actor="ops@acme.test"))

    proof = run(recovery_proof.case_proof(db, TENANT, case["id"]))

    assert proof["case"]["source"] == rc.SOURCE_DORMANT_DEAL
    assert proof["case"]["reason_detected"] == "No contact for 45 days"
    assert proof["case"]["detected_at"]
    assert proof["value"]["potential_value"] == 4000.0
    assert proof["value"]["confirmed_recovered_value"] == 4000.0
    assert proof["communications"]["messages_drafted"] == 2
    assert proof["communications"]["messages_actually_sent"] == 1
    assert proof["communications"]["replies_received"] == 1
    assert proof["outcome"]["recovered"] is True
    assert proof["attribution"]["claimed"] is True
    assert proof["attribution"]["basis"] == attribution.BASIS_REPLY
    assert proof["attribution"]["evidence"], "a claim with no evidence is not proof"
    assert proof["history"], "the case's own history must be readable from the proof"


def test_a_case_that_recovered_nothing_says_so_plainly(db):
    case = make_case(db)
    conversation = conversation_for(db, case)
    message(db, conversation, direction=cv.OUTBOUND, status=cv.DRAFT)
    proof = run(recovery_proof.case_proof(db, TENANT, case["id"]))

    assert proof["value"]["confirmed_recovered_value"] is None
    assert proof["communications"]["messages_drafted"] == 1
    assert proof["communications"]["messages_actually_sent"] == 0
    assert proof["attribution"]["claimed"] is False
    assert proof["outcome"]["recovered"] is False


def test_potential_and_confirmed_are_separate_named_figures(db):
    case = make_case(db, potential=9000.0)
    proof = run(recovery_proof.case_proof(db, TENANT, case["id"]))
    value = proof["value"]
    assert "potential_value" in value and "confirmed_recovered_value" in value
    assert "value" not in value, (
        "a single figure called 'value' would be read as whichever number flatters")
    assert value["potential_value"] == 9000.0
    assert value["confirmed_recovered_value"] is None


def test_a_case_in_another_tenant_has_no_proof_here(db):
    other = make_case(db, tenant_id=OTHER_TENANT)
    assert run(recovery_proof.case_proof(db, TENANT, other["id"])) is None


def test_proof_never_reaches_into_another_tenants_messages(db):
    case = make_case(db)
    other_case = make_case(db, tenant_id=OTHER_TENANT)
    other_conversation = conversation_for(db, other_case, tenant_id=OTHER_TENANT)
    message(db, other_conversation, direction=cv.OUTBOUND, status=cv.SENT,
            tenant_id=OTHER_TENANT)
    proof = run(recovery_proof.case_proof(db, TENANT, case["id"]))
    assert proof["communications"]["messages_drafted"] == 0


# ---------------------------------------------------------------------- portfolio

def test_portfolio_separates_detected_from_worked(db):
    make_case(db)                     # detected only
    worked = make_case(db)
    run(rc.set_state(db, tenant_id=TENANT, case_id=worked["id"], state=rc.PLANNED,
                     actor="composer"))

    report = run(recovery_proof.portfolio(db, TENANT))
    assert report["cases"]["detected"] == 2
    assert report["cases"]["worked"] == 1
    assert report["cases"]["not_yet_worked"] == 1


def test_portfolio_never_counts_a_draft_as_a_send(db):
    case = make_case(db)
    conversation = conversation_for(db, case)
    for status in (cv.DRAFT, cv.PENDING_APPROVAL, cv.APPROVED, cv.BLOCKED, cv.FAILED,
                   cv.OUTCOME_UNKNOWN):
        message(db, conversation, direction=cv.OUTBOUND, status=status)
    message(db, conversation, direction=cv.OUTBOUND, status=cv.SENT)

    report = run(recovery_proof.portfolio(db, TENANT))
    assert report["messages"]["drafted"] == 7
    assert report["messages"]["actually_sent"] == 1
    assert report["messages"]["blocked_or_failed"] == 2
    assert report["messages"]["outcome_unknown"] == 1


def test_portfolio_reports_unattributed_outcomes_alongside_claimed_revenue(db):
    claimed = make_case(db)
    conversation = conversation_for(db, claimed)
    message(db, conversation, direction=cv.OUTBOUND, status=cv.SENT, days_ago=10)
    engage(db, claimed)
    run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=claimed["id"],
        kind=attribution.OUTCOME_INVOICE_PAID,
        record_id=paid_invoice(db, total=1000.0)["id"], actor="ops@acme.test"))

    unclaimed = make_case(db)
    run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=unclaimed["id"],
        kind=attribution.OUTCOME_INVOICE_PAID,
        record_id=paid_invoice(db, total=25000.0)["id"], actor="ops@acme.test"))

    report = run(recovery_proof.portfolio(db, TENANT))
    revenue = report["revenue"]
    assert revenue["attributed_recovered_value_by_currency"]["USD"] == 1000.0
    assert revenue["unattributed_outcome_value_by_currency"]["USD"] == 25000.0
    assert report["attribution"]["attributed"] == 1
    assert report["attribution"]["unattributed"] == 1


def test_open_potential_is_never_folded_into_recovered_revenue(db):
    open_case = make_case(db, potential=50000.0)
    recovered = make_case(db, potential=1000.0)
    conversation = conversation_for(db, recovered)
    message(db, conversation, direction=cv.OUTBOUND, status=cv.SENT, days_ago=10)
    engage(db, recovered)
    run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=recovered["id"],
        kind=attribution.OUTCOME_INVOICE_PAID,
        record_id=paid_invoice(db, total=1000.0)["id"], actor="ops@acme.test"))

    revenue = run(recovery_proof.portfolio(db, TENANT))["revenue"]
    assert revenue["potential_value_open_by_currency"]["USD"] == 50000.0
    assert revenue["attributed_recovered_value_by_currency"]["USD"] == 1000.0
    assert "total" not in revenue, "there is no honest single total across these"
    assert open_case["id"]


def test_money_is_reported_per_currency_not_added_together(db):
    make_case(db, potential=1000.0, currency="USD")
    make_case(db, potential=2000.0, currency="GBP")
    revenue = run(recovery_proof.portfolio(db, TENANT))["revenue"]
    assert revenue["potential_value_open_by_currency"] == {"USD": 1000.0, "GBP": 2000.0}
    assert sorted(revenue["currencies"]) == ["GBP", "USD"]


def test_a_portfolio_for_an_empty_tenant_reports_zero_rather_than_nothing(db):
    report = run(recovery_proof.portfolio(db, "ten_empty"))
    assert report["cases"]["detected"] == 0
    assert report["messages"]["actually_sent"] == 0
    assert report["revenue"]["attributed_recovered_value_by_currency"] == {}


def test_every_portfolio_figure_names_where_it_comes_from(db):
    report = run(recovery_proof.portfolio(db, TENANT))
    trace = run(recovery_proof.traceability(db, TENANT))

    expected = {"cases.detected", "cases.worked", "approvals.pending",
                "messages.drafted", "messages.actually_sent",
                "messages.replies_received",
                "revenue.potential_value_open_by_currency",
                "revenue.attributed_recovered_value_by_currency",
                "revenue.unattributed_outcome_value_by_currency",
                "time_to_recovery"}
    assert expected <= set(trace), "a metric nobody can resolve to a query is not proof"
    for key in expected:
        section, _, field = key.partition(".")
        assert section in report
        if field:
            assert field in report[section]
