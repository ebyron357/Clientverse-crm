"""Attribution ledger tests — mostly attempts to make it claim credit it has not earned.

The interesting tests here are adversarial. A ledger that records recovered revenue is
easy; a ledger that refuses to say *we* recovered it, when nothing we did ever reached the
client, is the thing worth having. So most of what follows drives a case to `recovered`
through some plausible-looking path and asserts the attributed figure stays at zero.
"""

import asyncio
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import attribution
import conversations
import recovery_case as rc
import recovery_strategy as rs

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT = "ten_att_a"
OTHER_TENANT = "ten_att_b"

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
    db_name = f"cv_att_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[db_name]
    run(rc.ensure_indexes(db))
    run(rs.ensure_indexes(db))
    run(conversations.ensure_indexes(db))
    run(attribution.ensure_indexes(db))
    run(db.tenants.insert_many([{"tenant_id": TENANT, "name": "A"},
                                {"tenant_id": OTHER_TENANT, "name": "B"}]))
    yield db
    run(client.drop_database(db_name))
    client.close()


def a_case(db, *, tenant_id=TENANT, value=40000, currency="USD"):
    event = rc.normalize_event(
        tenant_id=tenant_id, source=rc.SOURCE_MISSED_CALL,
        source_event_id=f"call_{uuid.uuid4().hex[:8]}",
        reason="Inbound call rang out and nobody called back.",
        external_identity={"kind": rc.IDENTITY_PHONE, "value": "+441632960001"},
        potential_value=value, currency=currency)
    return run(rc.open_case(db, event))


def drive_to(db, case_id, state, *, tenant_id=TENANT):
    """Walk a case forward through the legal path to the state asked for."""
    path = [rc.PLANNED, rc.AWAITING_APPROVAL, rc.APPROVED, rc.EXECUTING, rc.ENGAGED]
    for step in path:
        run(rc.set_state(db, tenant_id=tenant_id, case_id=case_id, state=step))
        if step == state:
            return
    run(rc.set_state(db, tenant_id=tenant_id, case_id=case_id, state=state))


def recover(db, case_id, amount=12000, *, tenant_id=TENANT):
    drive_to(db, case_id, rc.ENGAGED, tenant_id=tenant_id)
    return run(rc.confirm_recovery(db, tenant_id=tenant_id, case_id=case_id,
                                   amount=amount, evidence={"invoice": "INV-1"}))


# ------------------------------------------------- the claim we may not make

def test_a_recovered_case_with_no_outreach_is_not_attributed_to_us(env):
    """The central rule. Money came back; we cannot show we caused it."""
    db = env
    case = a_case(db)
    recover(db, case["id"])
    entry = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"]))

    assert entry["outcome"] == attribution.OUTCOME_RECOVERED
    assert entry["confirmed_value"] == 12000
    # The outcome is recorded. The credit is not.
    assert entry["basis"] == attribution.BASIS_NONE
    summary = run(attribution.summary(db, TENANT))
    assert summary["confirmed_recovered_by_currency"] == {"USD": 12000}
    assert summary["attributable_to_outreach_by_currency"] == {}


def test_a_blocked_outbound_message_earns_no_credit(env):
    """A message refused at the provider boundary is a message nobody received."""
    db = env
    case = a_case(db)
    conversation = run(conversations.create_conversation(
        db, tenant_id=TENANT, channel=conversations.CHANNEL_EMAIL,
        subject="Recovery outreach", actor="runner"))
    message = run(conversations.draft_message(
        db, tenant_id=TENANT, conversation_id=conversation["id"],
        body="We noticed we missed your call.", actor="agent",
        requester_kind=conversations.HANDLED_BY_AGENT))
    run(db[conversations.MESSAGES].update_one(
        {"id": message["id"]},
        {"$set": {"status": conversations.BLOCKED,
                  "blocked_reason": conversations.REFUSAL_PROVIDER}}))
    run(rc.attach(db, tenant_id=TENANT, case_id=case["id"],
                  conversation_reference=conversation["id"]))
    recover(db, case["id"])

    entry = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"]))
    assert entry["evidence"]["outbound_blocked"] == 1
    assert entry["evidence"]["outbound_delivered"] == 0
    assert entry["basis"] == attribution.BASIS_NONE


def test_an_unknown_outcome_message_is_not_evidence_of_delivery(env):
    """`outcome_unknown` exists because nobody knows. A maybe is not a yes."""
    db = env
    case = a_case(db)
    conversation = run(conversations.create_conversation(
        db, tenant_id=TENANT, channel=conversations.CHANNEL_EMAIL,
        subject="Recovery outreach", actor="runner"))
    message = run(conversations.draft_message(
        db, tenant_id=TENANT, conversation_id=conversation["id"],
        body="Following up.", actor="agent",
        requester_kind=conversations.HANDLED_BY_AGENT))
    run(db[conversations.MESSAGES].update_one(
        {"id": message["id"]}, {"$set": {"status": conversations.OUTCOME_UNKNOWN}}))
    run(rc.attach(db, tenant_id=TENANT, case_id=case["id"],
                  conversation_reference=conversation["id"]))

    evidence = run(attribution.gather_evidence(
        db, TENANT, run(rc.get_case(db, TENANT, case["id"]))))
    assert evidence["outbound_delivered"] == 0
    with pytest.raises(attribution.UnsupportedBasis):
        attribution.assert_basis_supported(attribution.BASIS_OUTREACH_DELIVERED, evidence)


def test_an_inbound_message_predating_our_outreach_is_not_a_reply(env):
    """A client contacting us first is the opposite of us recovering them."""
    db = env
    case = a_case(db)
    conversation = run(conversations.create_conversation(
        db, tenant_id=TENANT, channel=conversations.CHANNEL_EMAIL,
        subject="Recovery outreach", actor="runner"))

    # Their message arrives first, ours second.
    run(db[conversations.MESSAGES].insert_one({
        "id": "msg_early_inbound", "tenant_id": TENANT,
        "conversation_id": conversation["id"], "direction": conversations.INBOUND,
        "status": conversations.RECEIVED, "created_at": "2026-01-01T00:00:00+00:00"}))
    run(db[conversations.MESSAGES].insert_one({
        "id": "msg_later_outbound", "tenant_id": TENANT,
        "conversation_id": conversation["id"], "direction": conversations.OUTBOUND,
        "status": conversations.SENT, "created_at": "2026-02-01T00:00:00+00:00",
        "sent_at": "2026-02-01T00:00:00+00:00"}))
    run(rc.attach(db, tenant_id=TENANT, case_id=case["id"],
                  conversation_reference=conversation["id"]))

    entry = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"]))
    assert entry["evidence"]["inbound_replies_after_outreach"] == 0
    # Our message was sent, so delivery is claimable; a reply is not.
    assert entry["basis"] == attribution.BASIS_OUTREACH_DELIVERED


def test_a_reply_after_our_outreach_is_the_strongest_derived_basis(env):
    """Proves the rule will return the strong bases once a provider exists."""
    db = env
    case = a_case(db)
    conversation = run(conversations.create_conversation(
        db, tenant_id=TENANT, channel=conversations.CHANNEL_EMAIL,
        subject="Recovery outreach", actor="runner"))
    run(db[conversations.MESSAGES].insert_one({
        "id": "msg_out", "tenant_id": TENANT, "conversation_id": conversation["id"],
        "direction": conversations.OUTBOUND, "status": conversations.DELIVERED,
        "created_at": "2026-02-01T00:00:00+00:00",
        "sent_at": "2026-02-01T00:00:00+00:00"}))
    run(db[conversations.MESSAGES].insert_one({
        "id": "msg_in", "tenant_id": TENANT, "conversation_id": conversation["id"],
        "direction": conversations.INBOUND, "status": conversations.RECEIVED,
        "created_at": "2026-02-03T00:00:00+00:00"}))
    run(rc.attach(db, tenant_id=TENANT, case_id=case["id"],
                  conversation_reference=conversation["id"]))
    recover(db, case["id"])

    entry = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"]))
    assert entry["basis"] == attribution.BASIS_COUNTERPARTY_REPLIED
    summary = run(attribution.summary(db, TENANT))
    assert summary["attributable_to_outreach_by_currency"] == {"USD": 12000}


def test_internal_work_is_a_weaker_claim_than_outreach_and_says_so(env):
    db = env
    case = a_case(db)
    run(db.tasks.insert_one({"id": "task_1", "tenant_id": TENANT,
                             "recovery_case_id": case["id"], "status": "todo"}))
    recover(db, case["id"])

    entry = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"]))
    assert entry["basis"] == attribution.BASIS_INTERNAL_ONLY
    assert "no message was sent" in entry["basis_explanation"]
    # Internal prompting is real work, but it is not outreach and is not counted as it.
    summary = run(attribution.summary(db, TENANT))
    assert summary["attributable_to_outreach_by_currency"] == {}
    assert summary["confirmed_recovered_by_basis"] == {
        attribution.BASIS_INTERNAL_ONLY: {"USD": 12000}}


# ------------------------------------------------------- the human's claim

def test_an_operator_assertion_is_recorded_as_a_claim_not_as_proof(env):
    db = env
    case = a_case(db)
    recover(db, case["id"])
    entry = run(attribution.assert_operator_attribution(
        db, tenant_id=TENANT, case_id=case["id"], actor="ops@example.com",
        reason="Client told me on the phone that our follow-up prompted the reorder."))

    assert entry["operator_assertion"]["asserted_by"] == "ops@example.com"
    # The derived basis is untouched by the assertion — a person's word does not
    # manufacture a delivered message.
    assert entry["basis"] == attribution.BASIS_NONE
    summary = run(attribution.summary(db, TENANT))
    assert summary["operator_asserted_by_currency"] == {"USD": 12000}
    assert summary["attributable_to_outreach_by_currency"] == {}


def test_an_assertion_without_a_reason_is_refused(env):
    db = env
    case = a_case(db)
    recover(db, case["id"])
    for empty in ("", "   "):
        with pytest.raises(attribution.AttributionError):
            run(attribution.assert_operator_attribution(
                db, tenant_id=TENANT, case_id=case["id"], actor="ops@example.com",
                reason=empty))


# --------------------------------------------------------------- the money

def test_potential_value_never_becomes_recovered_revenue(env):
    """A £40,000 estimate on an open case is not £40,000 of anything recovered."""
    db = env
    case = a_case(db, value=40000, currency="GBP")
    entry = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"]))

    assert entry["outcome"] == attribution.OUTCOME_PENDING
    assert entry["potential_value"] == 40000
    assert entry["confirmed_value"] is None

    summary = run(attribution.summary(db, TENANT))
    assert summary["potential_open_by_currency"] == {"GBP": 40000}
    assert summary["confirmed_recovered_by_currency"] == {}


def test_a_lost_case_reports_its_estimate_as_lost_not_as_recovered(env):
    db = env
    case = a_case(db, value=5000)
    run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=rc.CLOSED,
                     actor="operator"))
    entry = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"]))

    assert entry["outcome"] == attribution.OUTCOME_LOST
    assert entry["confirmed_value"] is None
    summary = run(attribution.summary(db, TENANT))
    assert summary["potential_lost_by_currency"] == {"USD": 5000}
    assert summary["confirmed_recovered_by_currency"] == {}


def test_money_is_never_summed_across_currencies(env):
    db = env
    for currency in ("GBP", "USD"):
        case = a_case(db, currency=currency)
        recover(db, case["id"], amount=40000)
        run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"]))

    summary = run(attribution.summary(db, TENANT))
    assert summary["confirmed_recovered_by_currency"] == {"GBP": 40000, "USD": 40000}
    # No field anywhere offers 80000.
    assert 80000 not in [v for row in summary.values() if isinstance(row, dict)
                         for v in row.values() if not isinstance(v, dict)]


def test_a_stale_confirmed_value_on_a_non_recovered_case_is_ignored(env):
    """Confirmed value is read only from a recovered case, whatever the field holds."""
    db = env
    case = a_case(db)
    run(db[rc.COLLECTION].update_one({"id": case["id"]},
                                     {"$set": {"confirmed_value": 99999}}))
    entry = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"]))
    assert entry["outcome"] == attribution.OUTCOME_PENDING
    assert entry["confirmed_value"] is None


# ---------------------------------------------------- shape of the ledger

def test_one_entry_per_case_however_many_times_it_is_recorded(env):
    db = env
    case = a_case(db)
    first = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"]))
    recover(db, case["id"])
    second = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"]))

    assert first["id"] == second["id"]
    assert first["outcome"] == attribution.OUTCOME_PENDING
    assert second["outcome"] == attribution.OUTCOME_RECOVERED
    assert run(db[attribution.COLLECTION].count_documents({"tenant_id": TENANT})) == 1
    assert [h["action"] for h in second["history"]] == ["recorded", "refreshed"]


def test_concurrent_recording_produces_one_entry(env):
    db = env
    case = a_case(db)

    async def race():
        return await asyncio.gather(*(
            attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"])
            for _ in range(6)), return_exceptions=True)

    results = run(race())
    assert not [r for r in results if isinstance(r, Exception)], results
    assert run(db[attribution.COLLECTION].count_documents({"tenant_id": TENANT})) == 1


def test_the_period_is_when_the_outcome_landed(env):
    db = env
    case = a_case(db)
    recovered = recover(db, case["id"])
    entry = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"]))
    assert entry["period"] == recovered["updated_at"][:7]
    assert entry["decided_at"] == recovered["updated_at"]

    summary = run(attribution.summary(db, TENANT, period=entry["period"]))
    assert summary["confirmed_recovered_by_period"] == {entry["period"]: {"USD": 12000}}
    # A different period contains none of it.
    assert run(attribution.summary(db, TENANT, period="1999-01"))["entries"] == 0


def test_an_open_case_has_no_period(env):
    db = env
    case = a_case(db)
    entry = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"]))
    assert entry["decided_at"] is None and entry["period"] is None


def test_the_lane_comes_from_the_plan_the_case_actually_got(env):
    db = env
    case = a_case(db)
    strategy = run(rs.compose_for_case(db, TENANT, case))
    recover(db, case["id"])
    entry = run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"]))

    assert entry["lane"] == strategy["lane"]
    summary = run(attribution.summary(db, TENANT))
    assert summary["confirmed_recovered_by_lane"] == {strategy["lane"]: {"USD": 12000}}


def test_a_case_from_another_tenant_is_not_recordable(env):
    db = env
    case = a_case(db, tenant_id=OTHER_TENANT)
    with pytest.raises(attribution.AttributionError):
        run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"]))


def test_the_ledger_is_tenant_scoped(env):
    db = env
    mine = a_case(db)
    theirs = a_case(db, tenant_id=OTHER_TENANT)
    run(attribution.record_outcome(db, tenant_id=TENANT, case_id=mine["id"]))
    run(attribution.record_outcome(db, tenant_id=OTHER_TENANT, case_id=theirs["id"]))

    assert [e["case_id"] for e in run(attribution.list_entries(db, TENANT))] == [mine["id"]]
    assert run(attribution.get_for_case(db, TENANT, theirs["id"])) is None


def test_the_sweep_covers_open_cases_too(env):
    """Pending entries exist before an outcome lands, so work in flight is visible."""
    db = env
    open_case = a_case(db)
    done_case = a_case(db)
    recover(db, done_case["id"])

    result = run(attribution.reconcile_tenant(db, TENANT))
    assert result["cases_examined"] == 2
    assert result["entries_recorded"] == 2
    assert result["errors"] == []

    outcomes = {e["case_id"]: e["outcome"] for e in run(attribution.list_entries(db, TENANT))}
    assert outcomes[open_case["id"]] == attribution.OUTCOME_PENDING
    assert outcomes[done_case["id"]] == attribution.OUTCOME_RECOVERED


def test_the_sweep_reaches_every_tenant(env):
    db = env
    a_case(db)
    a_case(db, tenant_id=OTHER_TENANT)
    result = run(attribution.reconcile_all_tenants(db))
    assert result["tenants"] == 2
    assert sum(s["entries_recorded"] for s in result["summaries"]) == 2


def test_transitions_reach_the_existing_audit_trail(env):
    """Reuse of the domain-event log, not a parallel one."""
    db = env
    recorded = []

    async def fake_audit(event_type, resource_type, resource_id, tenant_id, actor,
                         workspace_id=None, payload=None, **kwargs):
        recorded.append({"event_type": event_type, "resource_type": resource_type,
                         "tenant_id": tenant_id})

    case = a_case(db)
    run(attribution.record_outcome(db, tenant_id=TENANT, case_id=case["id"],
                                   actor="sweep", audit=fake_audit))
    assert [r["event_type"] for r in recorded] == ["recovery_attribution.recorded"]
    assert recorded[0]["resource_type"] == "recovery_attribution"
    assert recorded[0]["tenant_id"] == TENANT


def test_the_summary_says_out_loud_that_nothing_is_attributed_yet(env):
    """The note is load-bearing: a zero with no explanation reads as a bug."""
    db = env
    summary = run(attribution.summary(db, TENANT))
    assert "no channel provider is registered" in summary["attribution_note"].lower()
