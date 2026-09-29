"""The attribution ledger, tested adversarially.

The failure mode this module exists to prevent is not a crash. It is a product that
reports large, confident, unearned recovery numbers and is believed until the first
buyer checks one. So most of what follows is an attempt to make the ledger claim credit
it has not earned, and an assertion that it refuses.

The attacks fall into four groups:

* **Invent the basis.** Pass it in, pass in evidence, pass in a claim -- none of it is
  read, because the basis is derived from records here and nowhere else.
* **Claim without contact.** A deal that closed while every message sat in draft,
  blocked, failed, or unknown. None of those reached anyone, so none of them supports a
  claim.
* **Inflate the amount.** State a bigger number than the invoice says, or point at an
  invoice nobody paid.
* **Book it twice.** Replay the same outcome and see whether the revenue doubles.
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

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT = "ten_attr_a"
OTHER_TENANT = "ten_attr_b"

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
    db_name = f"cv_attr_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[db_name]
    run(cv.ensure_indexes(database))
    run(rc.ensure_indexes(database))
    run(attribution.ensure_indexes(database))
    yield database
    run(client.drop_database(db_name))
    client.close()


def make_case(db, *, tenant_id=TENANT, potential=4000.0, detected_days_ago=30):
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=tenant_id,
        source=rc.SOURCE_DORMANT_DEAL,
        source_event_id=f"ev_{uuid.uuid4().hex[:10]}",
        occurred_at=iso(detected_days_ago),
        reason="No contact for 45 days",
        potential_value=potential,
        currency="USD",
    ), actor="detector"))
    run(db[rc.COLLECTION].update_one({"id": case["id"], "tenant_id": tenant_id},
                                     {"$set": {"created_at": iso(detected_days_ago)}}))
    return case


def engage(db, case, *, tenant_id=TENANT):
    """Walk a case to `engaged`, which is the only state a recovery can be confirmed from.

    The transition matrix is deliberate: revenue cannot be recovered by a case that never
    engaged anyone. Tests that want a confirmable case have to earn it the same way a
    real one does.
    """
    for state in (rc.PLANNED, rc.AWAITING_APPROVAL, rc.APPROVED, rc.EXECUTING, rc.ENGAGED):
        run(rc.set_state(db, tenant_id=tenant_id, case_id=case["id"], state=state,
                         actor="recovery-runner"))
    return run(rc.get_case(db, tenant_id, case["id"]))


def make_conversation(db, case, *, tenant_id=TENANT):
    return run(cv.create_conversation(
        db, tenant_id=tenant_id, channel=cv.CHANNEL_EMAIL, actor="agent:composer",
        subject="Recovery", recovery_case_id=case["id"], contact_id="ct_1",
        participants=[{"kind": cv.PARTICIPANT_CONTACT, "id": "ct_1",
                       "address": "buyer@client.test"}]))


def outbound(db, conversation, *, status, days_ago=10, tenant_id=TENANT):
    """Insert an outbound message in a given state, directly.

    Inserted rather than driven through the state machine so every state -- including
    the ones the machine will not let you linger in -- can be presented to the ledger.
    """
    doc = {"id": f"msg_{uuid.uuid4().hex[:10]}", "tenant_id": tenant_id,
           "conversation_id": conversation["id"], "channel": cv.CHANNEL_EMAIL,
           "direction": cv.OUTBOUND, "status": status, "body": "Following up",
           "provider": "gmail", "created_at": iso(days_ago),
           "sent_at": iso(days_ago) if status in (cv.SENT, cv.DELIVERED) else None,
           "delivered_at": iso(days_ago) if status == cv.DELIVERED else None,
           "history": []}
    if status in (cv.SENT, cv.DELIVERED):
        doc["provider_message_id"] = f"prov_{uuid.uuid4().hex[:8]}"
    run(db[cv.MESSAGES].insert_one(dict(doc)))
    return doc


def inbound_reply(db, conversation, *, days_ago=5, tenant_id=TENANT):
    doc = {"id": f"msg_{uuid.uuid4().hex[:10]}", "tenant_id": tenant_id,
           "conversation_id": conversation["id"], "channel": cv.CHANNEL_EMAIL,
           "direction": cv.INBOUND, "status": cv.RECEIVED, "body": "Yes, let's proceed",
           "from_address": "buyer@client.test", "created_at": iso(days_ago),
           "history": []}
    run(db[cv.MESSAGES].insert_one(dict(doc)))
    return doc


def paid_invoice(db, *, total=4000.0, days_ago=1, tenant_id=TENANT, currency="USD"):
    invoice = {"id": f"inv_{uuid.uuid4().hex[:10]}", "tenant_id": tenant_id,
               "total": total, "currency": currency, "status": "paid",
               "payment_status": "paid", "paid_at": iso(days_ago),
               "created_at": iso(days_ago + 5)}
    run(db.invoices.insert_one(dict(invoice)))
    return invoice


# ---------------------------------------------------------------- honest attribution

def test_a_reply_after_a_sent_message_is_the_strongest_basis(db):
    case = make_case(db)
    conversation = make_conversation(db, case)
    outbound(db, conversation, status=cv.SENT, days_ago=10)
    inbound_reply(db, conversation, days_ago=5)
    engage(db, case)
    invoice = paid_invoice(db, days_ago=1)

    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=invoice["id"],
        actor="ops@acme.test"))

    assert entry["claim"] == attribution.CLAIM_ATTRIBUTED
    assert entry["basis"] == attribution.BASIS_REPLY
    kinds = {item["kind"] for item in entry["evidence"]}
    assert kinds == {"outbound_message", "inbound_reply"}
    assert entry["attributed_amount"] == 4000.0
    assert entry["case_updated"] is True

    case_now = run(rc.get_case(db, TENANT, case["id"]))
    assert case_now["state"] == rc.RECOVERED
    assert case_now["confirmed_value"] == 4000.0
    assert case_now["confirmed_value_evidence"]["attribution_entry_id"] == entry["id"]


def test_contact_without_a_reply_is_a_weaker_basis_and_says_so(db):
    case = make_case(db)
    conversation = make_conversation(db, case)
    outbound(db, conversation, status=cv.DELIVERED, days_ago=10)
    engage(db, case)
    invoice = paid_invoice(db)

    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=invoice["id"],
        actor="ops@acme.test"))
    assert entry["basis"] == attribution.BASIS_DELIVERED
    assert entry["claim"] == attribution.CLAIM_ATTRIBUTED
    assert "no reply" in entry["reason"]


def test_a_case_that_cannot_accept_a_confirmation_does_not_lose_the_ledger_entry(db):
    """A case still in `detected` cannot jump to `recovered`, and must not silently.

    The derivation is still true and is still worth keeping, so the entry stays and says
    plainly that the case was not updated -- rather than the ledger and the case quietly
    disagreeing about what happened.
    """
    case = make_case(db)
    conversation = make_conversation(db, case)
    outbound(db, conversation, status=cv.SENT, days_ago=10)
    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=paid_invoice(db)["id"],
        actor="ops@acme.test"))

    assert entry["claim"] == attribution.CLAIM_ATTRIBUTED
    assert entry["case_updated"] is False
    assert entry["case_update_error"]
    stored = run(attribution.get_entry(db, TENANT, entry["id"]))
    assert stored["case_updated"] is False
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.DETECTED


def test_no_confidence_score_is_fabricated(db):
    case = make_case(db)
    conversation = make_conversation(db, case)
    outbound(db, conversation, status=cv.SENT)
    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=paid_invoice(db)["id"],
        actor="ops@acme.test"))
    assert "confidence" not in entry
    assert "score" not in entry


# ------------------------------------------- claiming credit for outreach never sent

@pytest.mark.parametrize("status", [
    cv.DRAFT, cv.PENDING_APPROVAL, cv.APPROVED, cv.BLOCKED, cv.FAILED,
    cv.OUTCOME_UNKNOWN,
])
def test_a_message_that_did_not_reach_the_client_supports_no_claim(db, status):
    """Drafted is not sent. Approved is not sent. Unknown is not sent.

    `outcome_unknown` is the sharpest of these: the message may well have arrived, but
    nobody knows, and a maybe is not a basis for claiming somebody's revenue.
    """
    case = make_case(db)
    conversation = make_conversation(db, case)
    outbound(db, conversation, status=status, days_ago=10)
    invoice = paid_invoice(db)

    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=invoice["id"],
        actor="ops@acme.test"))

    assert entry["claim"] == attribution.CLAIM_UNATTRIBUTED
    assert entry["basis"] == attribution.BASIS_NONE
    assert entry["attributed_amount"] == 0.0
    assert entry["evidence"] == []
    assert status in entry["reason"]
    # The outcome itself is still recorded, and its own amount is still visible.
    assert entry["outcome"]["amount"] == 4000.0
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] != rc.RECOVERED


def test_a_case_with_no_conversation_at_all_claims_nothing(db):
    case = make_case(db)
    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=paid_invoice(db)["id"],
        actor="ops@acme.test"))
    assert entry["claim"] == attribution.CLAIM_UNATTRIBUTED
    assert "nothing was ever sent" in entry["reason"]


def test_an_outcome_that_predates_the_contact_is_not_attributed(db):
    """The deal closed before we said anything. We did not cause it."""
    case = make_case(db, detected_days_ago=60)
    conversation = make_conversation(db, case)
    outbound(db, conversation, status=cv.SENT, days_ago=2)
    invoice = paid_invoice(db, days_ago=20)

    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=invoice["id"],
        actor="ops@acme.test"))
    assert entry["claim"] == attribution.CLAIM_UNATTRIBUTED


def test_an_outcome_long_after_the_contact_falls_outside_the_window(db):
    case = make_case(db, detected_days_ago=400)
    conversation = make_conversation(db, case)
    outbound(db, conversation, status=cv.SENT, days_ago=300)
    invoice = paid_invoice(db, days_ago=1)

    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=invoice["id"],
        actor="ops@acme.test"))
    assert entry["claim"] == attribution.CLAIM_UNATTRIBUTED
    assert "within" in entry["reason"]


def test_a_reply_that_arrived_before_we_ever_wrote_is_not_our_reply(db):
    case = make_case(db)
    conversation = make_conversation(db, case)
    inbound_reply(db, conversation, days_ago=20)      # they wrote first
    outbound(db, conversation, status=cv.SENT, days_ago=10)
    invoice = paid_invoice(db, days_ago=1)

    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=invoice["id"],
        actor="ops@acme.test"))
    assert entry["basis"] == attribution.BASIS_DELIVERED, (
        "an earlier inbound message is not a reply to something sent after it")


# ------------------------------------------------------- inventing the basis

def test_the_caller_cannot_supply_the_basis_the_evidence_or_the_claim(db):
    """Every one of these is derived. None of them is an input."""
    case = make_case(db)
    conversation = make_conversation(db, case)
    outbound(db, conversation, status=cv.DRAFT)

    with pytest.raises(TypeError):
        run(attribution.record_outcome(
            db, tenant_id=TENANT, case_id=case["id"],
            kind=attribution.OUTCOME_INVOICE_PAID, record_id=paid_invoice(db)["id"],
            actor="attacker", basis=attribution.BASIS_REPLY))

    with pytest.raises(TypeError):
        run(attribution.record_outcome(
            db, tenant_id=TENANT, case_id=case["id"],
            kind=attribution.OUTCOME_INVOICE_PAID, record_id=paid_invoice(db)["id"],
            actor="attacker", evidence=[{"kind": "outbound_message", "record_id": "x"}]))

    with pytest.raises(TypeError):
        run(attribution.record_outcome(
            db, tenant_id=TENANT, case_id=case["id"],
            kind=attribution.OUTCOME_INVOICE_PAID, record_id=paid_invoice(db)["id"],
            actor="attacker", claim=attribution.CLAIM_ATTRIBUTED))


def test_a_note_cannot_smuggle_a_basis_into_the_entry(db):
    case = make_case(db)
    conversation = make_conversation(db, case)
    outbound(db, conversation, status=cv.DRAFT)
    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=paid_invoice(db)["id"],
        actor="attacker", note="basis=reply_after_contact; claim=attributed"))
    assert entry["basis"] == attribution.BASIS_NONE
    assert entry["claim"] == attribution.CLAIM_UNATTRIBUTED
    assert entry["attributed_amount"] == 0.0


# --------------------------------------------------------------- inflating the amount

def test_the_amount_comes_from_the_invoice_not_from_the_caller(db):
    case = make_case(db)
    conversation = make_conversation(db, case)
    outbound(db, conversation, status=cv.SENT, days_ago=10)
    invoice = paid_invoice(db, total=1000.0)

    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=invoice["id"],
        actor="attacker", amount=999999.0))
    assert entry["outcome"]["amount"] == 1000.0
    assert entry["attributed_amount"] == 1000.0
    assert entry["outcome"]["amount_source"] == "invoice record"


def test_an_unpaid_invoice_is_not_recovered_revenue(db):
    case = make_case(db)
    conversation = make_conversation(db, case)
    outbound(db, conversation, status=cv.SENT)
    invoice = {"id": f"inv_{uuid.uuid4().hex[:8]}", "tenant_id": TENANT, "total": 5000.0,
               "currency": "USD", "status": "issued", "payment_status": "open",
               "created_at": iso(2)}
    run(db.invoices.insert_one(dict(invoice)))

    with pytest.raises(attribution.AttributionError) as excinfo:
        run(attribution.record_outcome(
            db, tenant_id=TENANT, case_id=case["id"],
            kind=attribution.OUTCOME_INVOICE_PAID, record_id=invoice["id"],
            actor="attacker"))
    assert "not paid" in str(excinfo.value)


def test_an_open_deal_is_pipeline_not_revenue(db):
    case = make_case(db)
    conversation = make_conversation(db, case)
    outbound(db, conversation, status=cv.SENT)
    deal = {"id": f"opp_{uuid.uuid4().hex[:8]}", "tenant_id": TENANT, "value": 40000.0,
            "stage": "negotiation", "currency": "USD", "created_at": iso(30)}
    run(db.opportunities.insert_one(dict(deal)))

    with pytest.raises(attribution.AttributionError) as excinfo:
        run(attribution.record_outcome(
            db, tenant_id=TENANT, case_id=case["id"],
            kind=attribution.OUTCOME_DEAL_WON, record_id=deal["id"], actor="attacker"))
    assert "pipeline, not revenue" in str(excinfo.value)


def test_a_won_deals_value_comes_from_the_deal(db):
    case = make_case(db)
    conversation = make_conversation(db, case)
    outbound(db, conversation, status=cv.SENT, days_ago=20)
    deal = {"id": f"opp_{uuid.uuid4().hex[:8]}", "tenant_id": TENANT, "value": 12000.0,
            "stage": "closed_won", "currency": "USD", "created_at": iso(30),
            "stage_history": [{"from": "proposal", "to": "closed_won", "at": iso(1)}]}
    run(db.opportunities.insert_one(dict(deal)))

    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_DEAL_WON, record_id=deal["id"], actor="ops@acme.test",
        amount=999999.0))
    assert entry["outcome"]["amount"] == 12000.0


def test_an_operator_confirmation_is_labelled_as_a_statement_not_a_record(db):
    case = make_case(db)
    conversation = make_conversation(db, case)
    outbound(db, conversation, status=cv.SENT, days_ago=10)
    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_OPERATOR_CONFIRMED, record_id="cash-payment-2026-09",
        actor="ops@acme.test", amount=2500.0, currency="GBP", occurred_at=iso(1)))
    assert entry["outcome"]["amount_source"] == "operator statement"
    assert entry["recorded_by"] == "ops@acme.test"
    assert entry["currency"] == "GBP"


def test_a_confirmation_of_nothing_is_refused(db):
    case = make_case(db)
    for amount in (0, -50):
        with pytest.raises(attribution.AttributionError):
            run(attribution.record_outcome(
                db, tenant_id=TENANT, case_id=case["id"],
                kind=attribution.OUTCOME_OPERATOR_CONFIRMED, record_id=f"x{amount}",
                actor="attacker", amount=amount))


# --------------------------------------------------------------------- booking twice

def test_replaying_the_same_outcome_does_not_book_the_revenue_twice(db):
    case = make_case(db)
    conversation = make_conversation(db, case)
    outbound(db, conversation, status=cv.SENT, days_ago=10)
    invoice = paid_invoice(db, total=3000.0)

    first = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=invoice["id"],
        actor="ops@acme.test"))
    second = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=invoice["id"],
        actor="ops@acme.test"))

    assert second["deduplicated"] is True
    assert second["id"] == first["id"]
    totals = run(attribution.totals(db, TENANT))
    assert totals["attributed_recovered_value_by_currency"]["USD"] == 3000.0
    assert totals["entries"] == 1


# ------------------------------------------------------------------ tenant isolation

def test_a_case_in_another_tenant_cannot_be_credited(db):
    other_case = make_case(db, tenant_id=OTHER_TENANT)
    with pytest.raises(attribution.CaseNotFound):
        run(attribution.record_outcome(
            db, tenant_id=TENANT, case_id=other_case["id"],
            kind=attribution.OUTCOME_OPERATOR_CONFIRMED, record_id="x",
            actor="attacker", amount=100.0))


def test_an_invoice_in_another_tenant_cannot_be_claimed(db):
    case = make_case(db)
    other_invoice = paid_invoice(db, tenant_id=OTHER_TENANT)
    with pytest.raises(attribution.OutcomeNotFound):
        run(attribution.record_outcome(
            db, tenant_id=TENANT, case_id=case["id"],
            kind=attribution.OUTCOME_INVOICE_PAID, record_id=other_invoice["id"],
            actor="attacker"))


def test_another_tenants_sent_message_cannot_support_a_claim(db):
    """Contact has to be contact *we* made, on *this* case."""
    case = make_case(db)
    other_case = make_case(db, tenant_id=OTHER_TENANT)
    other_conversation = make_conversation(db, other_case, tenant_id=OTHER_TENANT)
    outbound(db, other_conversation, status=cv.SENT, days_ago=10,
             tenant_id=OTHER_TENANT)

    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=paid_invoice(db)["id"],
        actor="attacker"))
    assert entry["claim"] == attribution.CLAIM_UNATTRIBUTED


def test_a_message_on_another_case_does_not_support_this_one(db):
    case = make_case(db)
    other_case = make_case(db)
    other_conversation = make_conversation(db, other_case)
    outbound(db, other_conversation, status=cv.SENT, days_ago=10)

    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=paid_invoice(db)["id"],
        actor="attacker"))
    assert entry["claim"] == attribution.CLAIM_UNATTRIBUTED


# --------------------------------------------------------------------------- totals

def test_totals_keep_attributed_and_unattributed_side_by_side(db):
    attributed_case = make_case(db)
    conversation = make_conversation(db, attributed_case)
    outbound(db, conversation, status=cv.SENT, days_ago=10)
    run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=attributed_case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID,
        record_id=paid_invoice(db, total=1000.0)["id"], actor="ops@acme.test"))

    unattributed_case = make_case(db)
    run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=unattributed_case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID,
        record_id=paid_invoice(db, total=7000.0)["id"], actor="ops@acme.test"))

    totals = run(attribution.totals(db, TENANT))
    assert totals["attributed_recovered_value_by_currency"]["USD"] == 1000.0
    assert totals["unattributed_outcome_value_by_currency"]["USD"] == 7000.0
    assert totals["attributed_entries"] == 1
    assert totals["unattributed_entries"] == 1


def test_money_is_never_summed_across_currencies(db):
    for currency, amount in (("USD", 1000.0), ("GBP", 2000.0)):
        case = make_case(db)
        conversation = make_conversation(db, case)
        outbound(db, conversation, status=cv.SENT, days_ago=10)
        run(attribution.record_outcome(
            db, tenant_id=TENANT, case_id=case["id"],
            kind=attribution.OUTCOME_INVOICE_PAID,
            record_id=paid_invoice(db, total=amount, currency=currency)["id"],
            actor="ops@acme.test"))

    totals = run(attribution.totals(db, TENANT))
    assert totals["attributed_recovered_value_by_currency"] == {"USD": 1000.0,
                                                                "GBP": 2000.0}
    assert sorted(totals["currencies"]) == ["GBP", "USD"]


def test_time_to_recovery_is_only_reported_where_it_can_be_measured(db):
    empty = run(attribution.time_to_recovery(db, TENANT))
    assert empty["measured_entries"] == 0
    assert empty["median_days"] is None

    case = make_case(db, detected_days_ago=30)
    conversation = make_conversation(db, case)
    outbound(db, conversation, status=cv.SENT, days_ago=20)
    run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID,
        record_id=paid_invoice(db, days_ago=2)["id"], actor="ops@acme.test"))

    measured = run(attribution.time_to_recovery(db, TENANT))
    assert measured["measured_entries"] == 1
    assert 27 <= measured["median_days"] <= 29


def test_the_attribution_window_is_tenant_configuration_not_a_call_argument(db):
    case = make_case(db, detected_days_ago=200)
    conversation = make_conversation(db, case)
    outbound(db, conversation, status=cv.SENT, days_ago=150)
    invoice = paid_invoice(db, days_ago=1)

    outside = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=invoice["id"],
        actor="ops@acme.test"))
    assert outside["claim"] == attribution.CLAIM_UNATTRIBUTED

    run(attribution.set_attribution_window(db, tenant_id=TENANT, days=365,
                                           actor="admin@acme.test"))
    second_case = make_case(db, detected_days_ago=200)
    second_conversation = make_conversation(db, second_case)
    outbound(db, second_conversation, status=cv.SENT, days_ago=150)
    inside = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=second_case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID,
        record_id=paid_invoice(db, days_ago=1)["id"], actor="ops@acme.test"))
    assert inside["claim"] == attribution.CLAIM_ATTRIBUTED
    assert inside["attribution_window_days"] == 365


# ------------------------------------------------------ second review: the same money

def _contacted_case(db, **kwargs):
    case = make_case(db, **kwargs)
    conversation = make_conversation(db, case, tenant_id=kwargs.get("tenant_id", TENANT))
    outbound(db, conversation, status=cv.SENT, days_ago=10,
             tenant_id=kwargs.get("tenant_id", TENANT))
    return case


def test_one_invoice_cannot_be_booked_on_two_cases(db):
    """It used to book once per case, and again under operator_confirmed: 3x the money."""
    first_case, second_case = _contacted_case(db), _contacted_case(db)
    invoice = paid_invoice(db, total=5000.0)
    run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=first_case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=invoice["id"], actor="ops"))
    with pytest.raises(attribution.RecordAlreadyBooked):
        run(attribution.record_outcome(
            db, tenant_id=TENANT, case_id=second_case["id"],
            kind=attribution.OUTCOME_INVOICE_PAID, record_id=invoice["id"], actor="ops"))
    with pytest.raises(attribution.AttributionError, match="is a CRM record"):
        run(attribution.record_outcome(
            db, tenant_id=TENANT, case_id=first_case["id"],
            kind=attribution.OUTCOME_OPERATOR_CONFIRMED, record_id=invoice["id"],
            actor="ops", amount=5000.0, occurred_at=iso(1)))
    totals = run(attribution.totals(db, TENANT))
    assert totals["attributed_recovered_value_by_currency"] == {"USD": 5000.0}


def test_an_invoice_for_another_client_cannot_be_booked_on_this_case(db):
    run(db.workspaces.insert_many([
        {"id": "ws_this", "tenant_id": TENANT, "company_id": "co_this"},
        {"id": "ws_other", "tenant_id": TENANT, "company_id": "co_other"}]))
    case = _contacted_case(db)
    run(db[rc.COLLECTION].update_one({"id": case["id"]},
                                     {"$set": {"company_id": "co_this"}}))
    elsewhere = paid_invoice(db)
    run(db.invoices.update_one({"id": elsewhere["id"]}, {"$set": {"workspace_id": "ws_other"}}))
    with pytest.raises(attribution.AttributionError, match="does not belong"):
        run(attribution.record_outcome(
            db, tenant_id=TENANT, case_id=case["id"],
            kind=attribution.OUTCOME_INVOICE_PAID, record_id=elsewhere["id"], actor="ops"))

    theirs = paid_invoice(db)
    run(db.invoices.update_one({"id": theirs["id"]}, {"$set": {"workspace_id": "ws_this"}}))
    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=theirs["id"], actor="ops"))
    assert entry["record_link"]["linked"] is True
    assert entry["record_link"]["via"] == "the case's company"


def test_a_case_naming_no_crm_record_says_its_link_is_unverified(db):
    case = _contacted_case(db)
    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"],
        kind=attribution.OUTCOME_INVOICE_PAID, record_id=paid_invoice(db)["id"],
        actor="ops"))
    assert entry["record_link"] == {
        "linked": False, "anchored": False,
        "detail": "The case names no CRM record, so this link rests on the recorder's word."}


# ------------------------------------------------ second review: dates a caller can move

def test_an_invoice_with_no_payment_date_is_not_dated_by_its_last_edit(db):
    """`updated_at` resets on any edit, which dated a year-old payment to today."""
    case = _contacted_case(db)
    invoice = paid_invoice(db)
    run(db.invoices.update_one({"id": invoice["id"]},
                               {"$unset": {"paid_at": ""}, "$set": {"updated_at": iso(0)}}))
    with pytest.raises(attribution.AttributionError, match="no payment date"):
        run(attribution.record_outcome(
            db, tenant_id=TENANT, case_id=case["id"],
            kind=attribution.OUTCOME_INVOICE_PAID, record_id=invoice["id"], actor="ops"))


def test_the_first_payment_date_sticks(db):
    from client_value import stamp_paid_at

    invoice = paid_invoice(db)
    first = invoice["paid_at"]
    run(stamp_paid_at(db, tenant_id=TENANT, invoice_id=invoice["id"], at=iso(0),
                      previously_paid=False))
    assert run(db.invoices.find_one({"id": invoice["id"]}))["paid_at"] == first
    unpaid = {"id": "inv_unpaid", "tenant_id": TENANT, "status": "issued"}
    run(db.invoices.insert_one(dict(unpaid)))
    run(stamp_paid_at(db, tenant_id=TENANT, invoice_id="inv_unpaid", at=iso(0),
                      previously_paid=False))
    assert "paid_at" not in run(db.invoices.find_one({"id": "inv_unpaid"}))


def test_re_saving_an_old_paid_invoice_does_not_date_it_today(db):
    """An invoice paid before payment dates were kept has none. Marking it paid again
    used to stamp today, after this week's outreach, and the ledger then credited it."""
    from client_value import stamp_paid_at

    legacy = {"id": "inv_legacy", "tenant_id": TENANT, "status": "paid",
              "payment_status": "paid", "total": 9000.0, "currency": "USD"}
    run(db.invoices.insert_one(dict(legacy)))
    run(stamp_paid_at(db, tenant_id=TENANT, invoice_id="inv_legacy", at=iso(0),
                      previously_paid=True))
    assert "paid_at" not in run(db.invoices.find_one({"id": "inv_legacy"}))
    case = _contacted_case(db)
    with pytest.raises(attribution.AttributionError, match="no payment date"):
        run(attribution.record_outcome(
            db, tenant_id=TENANT, case_id=case["id"],
            kind=attribution.OUTCOME_INVOICE_PAID, record_id="inv_legacy", actor="ops"))


def test_a_deal_is_dated_by_its_first_win_not_its_latest(db):
    """Moving a deal won 200 days ago back into closed_won dated the win to today."""
    case = _contacted_case(db)
    deal = {"id": f"opp_{uuid.uuid4().hex[:8]}", "tenant_id": TENANT, "value": 9000.0,
            "currency": "USD", "stage": "closed_won",
            "stage_history": [{"from": "proposal", "to": "closed_won", "at": iso(200)},
                              {"from": "closed_won", "to": "negotiation", "at": iso(2)},
                              {"from": "negotiation", "to": "closed_won", "at": iso(1)}]}
    run(db.opportunities.insert_one(dict(deal)))
    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"], kind=attribution.OUTCOME_DEAL_WON,
        record_id=deal["id"], actor="ops"))
    assert entry["claim"] == attribution.CLAIM_UNATTRIBUTED
    assert entry["outcome"]["occurred_at"][:10] == iso(200)[:10]


def test_a_deal_with_no_recorded_win_is_not_dated_by_its_last_edit(db):
    case = _contacted_case(db)
    deal = {"id": f"opp_{uuid.uuid4().hex[:8]}", "tenant_id": TENANT, "value": 9000.0,
            "currency": "USD", "stage": "closed_won", "updated_at": iso(0)}
    run(db.opportunities.insert_one(dict(deal)))
    with pytest.raises(attribution.AttributionError, match="does not say when it was"):
        run(attribution.record_outcome(
            db, tenant_id=TENANT, case_id=case["id"], kind=attribution.OUTCOME_DEAL_WON,
            record_id=deal["id"], actor="ops"))


def test_an_operator_cannot_date_an_outcome_in_the_future(db):
    case = _contacted_case(db)
    future = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    with pytest.raises(attribution.AttributionError, match="future"):
        run(attribution.record_outcome(
            db, tenant_id=TENANT, case_id=case["id"],
            kind=attribution.OUTCOME_OPERATOR_CONFIRMED, record_id="bank-ref-9",
            actor="ops", amount=100.0, occurred_at=future))


# ------------------------------------------------------ second review: currency labels

def test_a_recovery_keeps_the_currency_the_money_arrived_in(db):
    case = _contacted_case(db)
    engage(db, case)
    invoice = paid_invoice(db, total=8000.0, currency="EUR")
    run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"], kind=attribution.OUTCOME_INVOICE_PAID,
        record_id=invoice["id"], actor="ops"))
    recovered = run(rc.get_case(db, TENANT, case["id"]))
    assert recovered["confirmed_value"] == 8000.0
    assert recovered["confirmed_currency"] == "EUR" and recovered["currency"] == "USD"
    summary = run(rc.summary(db, TENANT))
    assert summary["confirmed_recovered_value_by_currency"] == {"EUR": 8000.0}


def test_linking_a_case_turns_an_unverified_link_into_a_checked_one(db):
    run(db.workspaces.insert_many([
        {"id": "ws_link_a", "tenant_id": TENANT, "company_id": "co_link_a"},
        {"id": "ws_link_b", "tenant_id": TENANT, "company_id": "co_link_b"}]))
    run(db.companies.insert_one({"id": "co_link_a", "tenant_id": TENANT, "name": "A"}))
    case = _contacted_case(db)
    run(rc.link_crm_records(db, tenant_id=TENANT, case_id=case["id"], actor="ops",
                            company_id="co_link_a"))
    elsewhere = paid_invoice(db)
    run(db.invoices.update_one({"id": elsewhere["id"]}, {"$set": {"workspace_id": "ws_link_b"}}))
    with pytest.raises(attribution.AttributionError, match="does not belong"):
        run(attribution.record_outcome(
            db, tenant_id=TENANT, case_id=case["id"],
            kind=attribution.OUTCOME_INVOICE_PAID, record_id=elsewhere["id"], actor="ops"))
