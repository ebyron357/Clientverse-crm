"""Recovery Case tests — the CRM-origin assumption, removed.

The point of this slice is that a revenue opportunity no longer has to begin life as an
internal CRM record. So the tests that matter most are the ones that drive a synthetic
missed call — no opportunity, no workspace, no contact, only a phone number — all the way
to the planner, and prove it is not treated as a lesser citizen than a dormant deal.
"""

import asyncio
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import recovery_case as rc
import recovery_strategy as rs
import second_chance
from work_queue import WorkQueue

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT = "ten_rc_a"
OTHER_TENANT = "ten_rc_b"

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
    db_name = f"cv_rc_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[db_name]
    queue = WorkQueue(db)
    run(queue.ensure_indexes())
    run(rc.ensure_indexes(db))
    run(rs.ensure_indexes(db))
    run(db.tenants.insert_many([{"tenant_id": TENANT, "name": "A"},
                                {"tenant_id": OTHER_TENANT, "name": "B"}]))
    yield db, queue
    run(client.drop_database(db_name))
    client.close()


def missed_call_event(**overrides):
    """A missed call: a tenant, a number, a time. Nothing else."""
    payload = dict(
        tenant_id=TENANT,
        source=rc.SOURCE_MISSED_CALL,
        source_event_id=f"call_{uuid.uuid4().hex[:8]}",
        reason="Inbound call rang out after 30 seconds and nobody called back.",
        external_identity={"kind": rc.IDENTITY_PHONE, "value": "+441632960001"},
    )
    payload.update(overrides)
    return rc.normalize_event(**payload)


# ------------------------------------------------- the normalized event contract

def test_a_missed_call_needs_no_crm_record(env):
    """The assumption this slice exists to remove."""
    db, _ = env
    case = run(rc.open_case(db, missed_call_event()))
    assert case["state"] == rc.DETECTED
    assert case["opportunity_id"] is None
    assert case["contact_id"] is None
    assert case["workspace_id"] is None
    assert case["external_identity"] == {"kind": "phone", "value": "+441632960001"}
    assert case["source_is_internal"] is False


def test_the_event_contract_requires_what_it_cannot_infer(env):
    for missing in ("tenant_id", "source_event_id", "reason"):
        with pytest.raises(rc.RecoveryCaseError):
            missed_call_event(**{missing: ""})
    with pytest.raises(rc.RecoveryCaseError):
        missed_call_event(source="carrier_pigeon")


def test_external_identity_is_validated(env):
    with pytest.raises(rc.RecoveryCaseError):
        missed_call_event(external_identity={"kind": "telepathy", "value": "x"})
    with pytest.raises(rc.RecoveryCaseError):
        missed_call_event(external_identity={"kind": rc.IDENTITY_PHONE, "value": "  "})


def test_every_declared_source_is_accepted(env):
    """All ten sources in the vocabulary enter the same pipeline."""
    db, _ = env
    for source in rc.SOURCES:
        case = run(rc.open_case(db, rc.normalize_event(
            tenant_id=TENANT, source=source, source_event_id=f"{source}_1",
            reason=f"Synthetic {source} event.")))
        assert case["source"] == source
        assert case["state"] == rc.DETECTED


# --------------------------------------------------------------- deduplication

def test_the_same_source_event_creates_one_case(env):
    db, _ = env
    event = missed_call_event()
    first = run(rc.open_case(db, event))
    second = run(rc.open_case(db, event))
    assert second["deduplicated"] is True
    assert second["id"] == first["id"]
    assert len(run(rc.list_cases(db, TENANT))) == 1


def test_concurrent_workers_create_one_case(env):
    """Deduplication is enforced by the database, not by an application check."""
    db, _ = env
    event = missed_call_event()

    async def race():
        return await asyncio.gather(*[rc.open_case(db, event) for _ in range(6)],
                                    return_exceptions=True)

    results = run(race())
    assert all(not isinstance(r, Exception) for r in results), results
    ids = {r["id"] for r in results}
    assert len(ids) == 1, f"expected one case, got {ids}"
    assert len([r for r in results if not r["deduplicated"]]) == 1
    assert len(run(rc.list_cases(db, TENANT))) == 1


def test_the_same_event_id_in_two_tenants_is_two_cases(env):
    """Identity is scoped by tenant: one tenant's event id cannot collide with another's."""
    db, _ = env
    shared_id = "call_shared_0001"
    a = run(rc.open_case(db, missed_call_event(source_event_id=shared_id)))
    b = run(rc.open_case(db, missed_call_event(tenant_id=OTHER_TENANT,
                                               source_event_id=shared_id)))
    assert a["id"] != b["id"]
    assert len(run(rc.list_cases(db, TENANT))) == 1
    assert len(run(rc.list_cases(db, OTHER_TENANT))) == 1


# ------------------------------------------------------------ tenant isolation

def test_another_tenants_case_is_invisible(env):
    db, _ = env
    case = run(rc.open_case(db, missed_call_event()))
    assert run(rc.get_case(db, OTHER_TENANT, case["id"])) is None
    assert run(rc.list_cases(db, OTHER_TENANT)) == []


def test_another_tenants_case_cannot_be_modified(env):
    db, _ = env
    case = run(rc.open_case(db, missed_call_event()))
    with pytest.raises(rc.RecoveryCaseNotFound):
        run(rc.set_state(db, tenant_id=OTHER_TENANT, case_id=case["id"],
                         state=rc.PLANNED))
    with pytest.raises(rc.RecoveryCaseNotFound):
        run(rc.attach(db, tenant_id=OTHER_TENANT, case_id=case["id"],
                      contact_id="whatever"))
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.DETECTED


def test_another_tenants_contact_cannot_be_attached(env):
    db, _ = env
    run(db.contacts.insert_one({"tenant_id": OTHER_TENANT, "id": "con_theirs",
                                "name": "Theirs"}))
    case = run(rc.open_case(db, missed_call_event()))
    with pytest.raises(rc.CrossTenantReference):
        run(rc.attach(db, tenant_id=TENANT, case_id=case["id"], contact_id="con_theirs"))
    assert run(rc.get_case(db, TENANT, case["id"]))["contact_id"] is None


def test_another_tenants_opportunity_cannot_be_attached(env):
    db, _ = env
    run(db.opportunities.insert_one({"tenant_id": OTHER_TENANT, "id": "opp_theirs",
                                     "name": "Theirs", "value": 999}))
    case = run(rc.open_case(db, missed_call_event()))
    with pytest.raises(rc.CrossTenantReference):
        run(rc.attach(db, tenant_id=TENANT, case_id=case["id"],
                      opportunity_id="opp_theirs"))


def test_a_case_cannot_be_opened_against_another_tenants_record(env):
    """The check is at creation too, not only at attach."""
    db, _ = env
    run(db.opportunities.insert_one({"tenant_id": OTHER_TENANT, "id": "opp_theirs2",
                                     "name": "Theirs"}))
    with pytest.raises(rc.CrossTenantReference):
        run(rc.open_case(db, rc.normalize_event(
            tenant_id=TENANT, source=rc.SOURCE_EXTERNAL_CRM_EVENT,
            source_event_id="ext_1", reason="Injected reference",
            opportunity_id="opp_theirs2")))


def test_identity_resolution_attaches_an_owned_contact(env):
    db, _ = env
    run(db.contacts.insert_one({"tenant_id": TENANT, "id": "con_ours", "name": "Ours"}))
    case = run(rc.open_case(db, missed_call_event()))
    resolved = run(rc.attach(db, tenant_id=TENANT, case_id=case["id"],
                             contact_id="con_ours", actor="resolver"))
    assert resolved["contact_id"] == "con_ours"
    assert any(h["action"] == "attached" for h in resolved["history"])


# ------------------------------------------------------------------- states

def test_state_transitions_follow_the_matrix(env):
    db, _ = env
    case = run(rc.open_case(db, missed_call_event()))
    for state in (rc.PLANNED, rc.AWAITING_APPROVAL, rc.APPROVED, rc.EXECUTING,
                  rc.ENGAGED):
        case = run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=state))
        assert case["state"] == state


def test_an_invalid_transition_is_refused(env):
    db, _ = env
    case = run(rc.open_case(db, missed_call_event()))
    with pytest.raises(rc.InvalidCaseTransition):
        run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=rc.ENGAGED))
    with pytest.raises(rc.InvalidCaseTransition):
        run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=rc.RECOVERED))


def test_a_closed_case_is_terminal(env):
    db, _ = env
    case = run(rc.open_case(db, missed_call_event()))
    run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=rc.CLOSED))
    with pytest.raises(rc.InvalidCaseTransition):
        run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=rc.PLANNED))


# -------------------------------------------------------------- value integrity

def test_potential_value_is_never_confirmed_revenue(env):
    """The distinction this product's credibility rests on."""
    db, _ = env
    case = run(rc.open_case(db, missed_call_event(potential_value=40000)))
    assert case["potential_value"] == 40000
    assert case["confirmed_value"] is None
    assert case["potential_value_source"], "an estimate must carry its provenance"

    summary = run(rc.summary(db, TENANT))
    assert summary["potential_value_open"] == 40000
    assert summary["confirmed_recovered_value"] == 0


def test_confirming_recovery_requires_evidence(env):
    db, _ = env
    case = run(rc.open_case(db, missed_call_event(potential_value=40000)))
    for state in (rc.PLANNED, rc.AWAITING_APPROVAL, rc.APPROVED, rc.EXECUTING, rc.ENGAGED):
        run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=state))

    with pytest.raises(rc.RecoveryCaseError):
        run(rc.confirm_recovery(db, tenant_id=TENANT, case_id=case["id"], amount=40000,
                                evidence={}))

    confirmed = run(rc.confirm_recovery(
        db, tenant_id=TENANT, case_id=case["id"], amount=1200,
        evidence={"kind": "invoice", "reference": "inv_001"}))
    assert confirmed["state"] == rc.RECOVERED
    assert confirmed["confirmed_value"] == 1200
    # The estimate is preserved and untouched; it did not become the recovered figure.
    assert confirmed["potential_value"] == 40000

    summary = run(rc.summary(db, TENANT))
    assert summary["confirmed_recovered_value"] == 1200
    assert summary["potential_value_open"] == 0, "a recovered case is no longer open pipeline"


def test_a_negative_or_non_numeric_value_is_refused(env):
    db, _ = env
    with pytest.raises(rc.RecoveryCaseError):
        missed_call_event(potential_value=-1)
    with pytest.raises(rc.RecoveryCaseError):
        missed_call_event(potential_value="lots")


# -------------------------------------------------- CRM detector integration

def seed_dormant_opportunity(db):
    run(db.companies.insert_one({"tenant_id": TENANT, "id": "co_1", "name": "Acme"}))
    run(db.workspaces.insert_one({"tenant_id": TENANT, "id": "ws_1", "company_id": "co_1",
                                  "name": "Acme", "owner": "owner@example.com"}))
    run(db.opportunities.insert_one({
        "tenant_id": TENANT, "id": "opp_1", "name": "Acme renewal", "stage": "proposal",
        "value": 40000, "company_id": "co_1",
        "created_at": "2026-01-01T00:00:00+00:00"}))


def test_a_dormant_crm_deal_still_detects_and_now_opens_a_case(env):
    """Existing behaviour preserved, plus the case."""
    db, queue = env
    seed_dormant_opportunity(db)
    summary = run(second_chance.run_detection(db, queue, TENANT))

    assert summary["stalled_leads_detected"] == 1
    assert summary["work_items_created"] == 1, "the durable work item must still be created"
    assert summary["recovery_cases_linked"] == 1

    cases = run(rc.list_cases(db, TENANT))
    assert len(cases) == 1
    case = cases[0]
    assert case["source"] == rc.SOURCE_DORMANT_DEAL
    assert case["source_is_internal"] is True
    assert case["opportunity_id"] == "opp_1"
    assert case["potential_value"] == 40000
    assert case["confirmed_value"] is None
    assert case["work_item_reference"], "case and work item must reference each other"

    items = run(queue.list_items(tenant_id=TENANT, status="open",
                                 queue=second_chance.QUEUE_NAME))
    assert items[0]["payload"]["recovery_case_id"] == case["id"]


def test_re_detection_does_not_create_a_second_case(env):
    db, queue = env
    seed_dormant_opportunity(db)
    run(second_chance.run_detection(db, queue, TENANT))
    second = run(second_chance.run_detection(db, queue, TENANT))
    assert second["work_items_created"] == 0
    assert len(run(rc.list_cases(db, TENANT))) == 1


def test_detection_without_a_db_handle_still_works(env):
    """Backward compatibility: the pre-existing call shape must not break."""
    db, queue = env
    seed_dormant_opportunity(db)
    detections = run(second_chance.detect_stalled_leads(db, queue, TENANT))
    items = run(second_chance.enqueue_detections(queue, detections))
    assert len(items) == 1
    assert items[0]["payload"]["recovery_case_id"] is None
    assert run(rc.list_cases(db, TENANT)) == []


# ------------------------------------------------------- planner integration

def test_a_crm_case_reaches_the_planner(env):
    db, queue = env
    seed_dormant_opportunity(db)
    run(second_chance.run_detection(db, queue, TENANT))
    case = run(rc.list_cases(db, TENANT))[0]

    strategy = run(rs.compose_for_case(db, TENANT, case))
    assert strategy["lane"] == "owner_led_reengagement"
    assert strategy["facts"], "the planner must still cite its evidence"

    linked = run(rc.get_case(db, TENANT, case["id"]))
    assert linked["plan_reference"] == strategy["id"]
    assert linked["approval_reference"] == strategy["approval_id"]
    assert linked["state"] == rc.AWAITING_APPROVAL


def test_the_composer_sweep_links_a_second_chance_plan_to_its_case(env):
    """The sweep is how production composes, and it composes a Second Chance detection
    from its work item. It used to leave the case unplanned -- `detected`, no plan, no
    approval -- so no stalled-lead or missed-follow-up recovery could ever be approved
    or run. The test above calls `compose_for_case` directly, which is why it missed it."""
    db, queue = env
    seed_dormant_opportunity(db)
    run(second_chance.run_detection(db, queue, TENANT))
    summary = run(rs.compose_for_tenant(db, queue, TENANT))
    assert summary["strategies_composed"] == 1, "one plan per recovery, not one per route"

    case = run(rc.list_cases(db, TENANT))[0]
    strategy = run(rs.list_strategies(db, TENANT))[0]
    assert case["plan_reference"] == strategy["id"]
    assert case["approval_reference"] == strategy["approval_id"]
    assert case["state"] == rc.AWAITING_APPROVAL


def test_re_sweeping_keeps_the_case_on_one_plan(env):
    db, queue = env
    seed_dormant_opportunity(db)
    run(second_chance.run_detection(db, queue, TENANT))
    run(rs.compose_for_tenant(db, queue, TENANT))
    first = run(rc.list_cases(db, TENANT))[0]["plan_reference"]
    run(rs.compose_for_tenant(db, queue, TENANT))
    assert run(rc.list_cases(db, TENANT))[0]["plan_reference"] == first
    assert len(run(rs.list_strategies(db, TENANT))) == 1


def test_the_sweep_does_not_plan_a_recovery_that_already_ended(env):
    db, queue = env
    seed_dormant_opportunity(db)
    run(second_chance.run_detection(db, queue, TENANT))
    case = run(rc.list_cases(db, TENANT))[0]
    run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=rc.CLOSED))
    summary = run(rs.compose_for_tenant(db, queue, TENANT))
    assert summary["strategies_composed"] == 0
    assert run(rs.list_strategies(db, TENANT)) == []


def test_a_non_crm_case_reaches_the_planner_safely(env):
    """The success condition: a missed call plans without any CRM record behind it."""
    db, queue = env
    case = run(rc.open_case(db, missed_call_event(potential_value=250)))

    strategy = run(rs.compose_for_case(db, TENANT, case))
    assert strategy["lane"] == "needs_human_triage", (
        "with no owner and no contact the planner must say so, not invent a motion")
    assert strategy["rule"] == "inbound_demand.no_email_route"
    assert strategy["blocked_reasons"] == [] or all(strategy["steps"])

    linked = run(rc.get_case(db, TENANT, case["id"]))
    assert linked["plan_reference"] == strategy["id"]
    assert linked["state"] == rc.AWAITING_APPROVAL
    # The external identity survived planning — it is all we know about the counterparty.
    assert linked["external_identity"]["value"] == "+441632960001"


def test_a_resolved_non_crm_case_can_reach_a_real_lane(env):
    """Once identity resolves, an external case is planned like any other."""
    db, queue = env
    run(db.contacts.insert_one({"tenant_id": TENANT, "id": "con_ours", "name": "Ours",
                                "email": "caller@example.invalid"}))
    case = run(rc.open_case(db, missed_call_event(potential_value=5000)))
    case = run(rc.attach(db, tenant_id=TENANT, case_id=case["id"], contact_id="con_ours"))

    strategy = run(rs.compose_for_case(db, TENANT, case))
    # A real, executable lane that says what is actually waiting -- not the stalled-deal
    # reasoning ("idle N days at stage 'unknown'") a missed call used to receive.
    assert strategy["lane"] == "respond_to_waiting_contact"
    assert "missed call" in strategy["rationale"]
    assert any(step["channel"] == "email" for step in strategy["steps"])


def test_the_planner_refuses_a_case_from_another_tenant(env):
    db, _ = env
    case = run(rc.open_case(db, missed_call_event()))
    with pytest.raises(rc.CrossTenantReference):
        run(rs.compose_for_case(db, OTHER_TENANT, case))


# ------------------------------------------------------------------- audit

def test_case_transitions_reach_the_existing_audit_trail(env):
    """Reuse of the domain-event log, not a parallel one."""
    db, _ = env
    recorded = []

    async def fake_audit(event_type, resource_type, resource_id, tenant_id, actor,
                         workspace_id=None, payload=None, **kwargs):
        recorded.append({"event_type": event_type, "resource_type": resource_type,
                         "resource_id": resource_id, "tenant_id": tenant_id})

    case = run(rc.open_case(db, missed_call_event(), actor="detector", audit=fake_audit))
    run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=rc.PLANNED,
                     actor="planner", audit=fake_audit))

    assert [r["event_type"] for r in recorded] == ["recovery_case.detected",
                                                   "recovery_case.planned"]
    assert all(r["resource_type"] == "recovery_case" for r in recorded)
    assert all(r["tenant_id"] == TENANT for r in recorded)
    assert all(r["resource_id"] == case["id"] for r in recorded)


def test_history_records_the_source_and_every_move(env):
    db, _ = env
    case = run(rc.open_case(db, missed_call_event(), actor="detector"))
    case = run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=rc.PLANNED,
                            actor="planner"))
    actions = [h["action"] for h in case["history"]]
    assert actions == ["detected", "planned"]
    assert case["history"][0]["detail"]["source"] == rc.SOURCE_MISSED_CALL


# ------------------------------------------- review findings: identity and money

def test_an_overlong_source_event_id_is_refused_not_truncated(env):
    """Truncating the identity would merge two distinct events into one case.

    The id is what the unique index deduplicates on and what `find_by_source_event()`
    looks up, so shortening it silently is worse than refusing it.
    """
    shared_prefix = "x" * rc.MAX_IDENTITY_LENGTH
    with pytest.raises(rc.RecoveryCaseError):
        missed_call_event(source_event_id=shared_prefix + "-first")
    # At the limit exactly is fine, and stored whole.
    event = missed_call_event(source_event_id=shared_prefix)
    assert event["source_event_id"] == shared_prefix


def test_two_long_ids_sharing_a_prefix_stay_two_cases(env):
    db, _ = env
    prefix = "evt_" + "y" * 150
    first = run(rc.open_case(db, missed_call_event(source_event_id=prefix + "-a")))
    second = run(rc.open_case(db, missed_call_event(source_event_id=prefix + "-b")))
    assert first["id"] != second["id"]
    assert second["deduplicated"] is False
    found = run(rc.find_by_source_event(db, TENANT, rc.SOURCE_MISSED_CALL, prefix + "-b"))
    assert found and found["id"] == second["id"]


def test_an_overlong_external_identity_is_refused(env):
    with pytest.raises(rc.RecoveryCaseError):
        missed_call_event(external_identity={"kind": rc.IDENTITY_PHONE,
                                             "value": "+" + "1" * 250})


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_potential_value_is_refused(env, bad):
    """`nan` and the infinities are not negative, so the sign check alone lets them in."""
    with pytest.raises(rc.RecoveryCaseError):
        missed_call_event(potential_value=bad)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_a_non_finite_confirmed_amount_cannot_become_revenue(env, bad):
    db, _ = env
    case = run(rc.open_case(db, missed_call_event()))
    for state in (rc.PLANNED, rc.AWAITING_APPROVAL, rc.APPROVED, rc.EXECUTING, rc.ENGAGED):
        run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=state))
    with pytest.raises(rc.RecoveryCaseError):
        run(rc.confirm_recovery(db, tenant_id=TENANT, case_id=case["id"], amount=bad,
                                evidence={"invoice": "INV-1"}))
    # And the case is untouched: no terminal state, no confirmed value.
    after = run(rc.get_case(db, TENANT, case["id"]))
    assert after["state"] == rc.ENGAGED
    assert after["confirmed_value"] is None


def test_confirming_recovery_writes_the_state_and_the_amount_together(env):
    """One write. A case cannot end up terminal with nothing recorded against it."""
    db, _ = env
    case = run(rc.open_case(db, missed_call_event()))
    for state in (rc.PLANNED, rc.AWAITING_APPROVAL, rc.APPROVED, rc.EXECUTING, rc.ENGAGED):
        run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=state))
    confirmed = run(rc.confirm_recovery(db, tenant_id=TENANT, case_id=case["id"],
                                        amount=1250.5, evidence={"invoice": "INV-9"}))
    assert confirmed["state"] == rc.RECOVERED
    assert confirmed["confirmed_value"] == 1250.5
    assert confirmed["confirmed_value_evidence"] == {"invoice": "INV-9"}
    # The value arrived on the same history entry as the transition, not after it.
    assert confirmed["history"][-1]["action"] == rc.RECOVERED
    assert confirmed["history"][-1]["detail"]["confirmed_value"] == 1250.5


def test_value_is_never_summed_across_currencies(env):
    """£40,000 plus $40,000 is not 80,000 of anything."""
    db, _ = env
    run(rc.open_case(db, missed_call_event(potential_value=40000, currency="GBP")))
    run(rc.open_case(db, missed_call_event(potential_value=40000, currency="USD")))
    summary = run(rc.summary(db, TENANT))
    assert summary["potential_value_open_by_currency"] == {"GBP": 40000, "USD": 40000}
    assert summary["currencies"] == ["GBP", "USD"]
    # No single figure is offered, because no single figure is true.
    assert summary["potential_value_open"] is None
    assert summary["value_currency"] is None


def test_a_single_currency_tenant_still_gets_a_plain_total(env):
    db, _ = env
    run(rc.open_case(db, missed_call_event(potential_value=1500, currency="GBP")))
    run(rc.open_case(db, missed_call_event(potential_value=500, currency="GBP")))
    summary = run(rc.summary(db, TENANT))
    assert summary["potential_value_open"] == 2000
    assert summary["value_currency"] == "GBP"


# ------------------------------------ review findings: cross-tenant attachment

def test_a_plan_from_another_tenant_cannot_be_attached(env):
    """Every attachable reference is tenant-checked, not only the CRM ones."""
    db, _ = env
    case = run(rc.open_case(db, missed_call_event()))
    run(db.recovery_strategies.insert_one({"id": "rcv_foreign", "tenant_id": OTHER_TENANT}))
    with pytest.raises(rc.CrossTenantReference):
        run(rc.attach(db, tenant_id=TENANT, case_id=case["id"],
                      plan_reference="rcv_foreign"))
    assert run(rc.get_case(db, TENANT, case["id"]))["plan_reference"] is None


@pytest.mark.parametrize("field,collection,prefix", [
    ("approval_reference", "approvals", "apr"),
    ("conversation_reference", "conversations", "cnv"),
    ("work_item_reference", "work_queue", "wq"),
])
def test_every_created_record_reference_is_tenant_checked(env, field, collection, prefix):
    db, _ = env
    case = run(rc.open_case(db, missed_call_event()))
    foreign = f"{prefix}_foreign"
    run(db[collection].insert_one({"id": foreign, "tenant_id": OTHER_TENANT}))
    with pytest.raises(rc.CrossTenantReference):
        run(rc.attach(db, tenant_id=TENANT, case_id=case["id"], **{field: foreign}))
    # And the tenant's own record attaches normally.
    own = f"{prefix}_own"
    run(db[collection].insert_one({"id": own, "tenant_id": TENANT}))
    attached = run(rc.attach(db, tenant_id=TENANT, case_id=case["id"], **{field: own}))
    assert attached[field] == own


# ------------------------------- review findings: planning and the queue link

def test_a_terminal_case_cannot_be_given_a_fresh_plan(env):
    """A closed case must not acquire a new strategy and a live approval request."""
    db, _ = env
    case = run(rc.open_case(db, missed_call_event()))
    run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=rc.CLOSED,
                     actor="operator"))
    before = run(rs.list_strategies(db, TENANT))
    with pytest.raises(rc.InvalidCaseTransition):
        run(rs.compose_for_case(db, TENANT, case))
    # Nothing was written: no strategy, and the case still points at no plan.
    assert run(rs.list_strategies(db, TENANT)) == before
    after = run(rc.get_case(db, TENANT, case["id"]))
    assert after["state"] == rc.CLOSED
    assert after["plan_reference"] is None


def test_a_recompose_of_a_live_case_is_still_allowed(env):
    """Only terminal cases are refused; replanning an open one remains normal."""
    db, _ = env
    case = run(rc.open_case(db, missed_call_event()))
    run(rs.compose_for_case(db, TENANT, case))
    second = run(rs.compose_for_case(db, TENANT, run(rc.get_case(db, TENANT, case["id"]))))
    assert second["id"]


def test_the_planner_is_told_which_currency_a_value_is_in(env):
    """A bare number reaching a value threshold without its unit is a silent misread."""
    db, _ = env
    case = run(rc.open_case(db, missed_call_event(potential_value=40000, currency="GBP")))
    candidate = rs.candidate_from_case(run(rc.get_case(db, TENANT, case["id"])))
    assert candidate["evidence"]["value"] == 40000
    assert candidate["evidence"]["currency"] == "GBP"


def test_a_case_with_no_work_item_is_still_reached_by_the_sweep(env):
    """The whole point of the slice: a missed call has no queue item to be found by."""
    db, queue = env
    case = run(rc.open_case(db, missed_call_event()))
    summary = run(rs.compose_for_tenant(db, queue, TENANT))
    assert summary["recovery_cases_examined"] >= 1
    assert summary["strategies_composed"] >= 1
    planned = run(rc.get_case(db, TENANT, case["id"]))
    assert planned["plan_reference"], "a case-only source was never planned for"
    assert planned["state"] in (rc.PLANNED, rc.AWAITING_APPROVAL)


def test_the_sweep_does_not_plan_the_same_case_twice(env):
    """A detection reached through its work item must not also be swept as a case."""
    db, queue = env
    run(db.opportunities.insert_one({
        "id": "opp_sweep", "tenant_id": TENANT, "title": "Dormant deal",
        "stage": "proposal", "value": 5000, "updated_at": "2020-01-01T00:00:00+00:00"}))
    run(second_chance.enqueue_detections(queue, [{
        "tenant_id": TENANT, "type": second_chance.TYPE_STALLED_LEAD,
        "record_id": "opp_sweep", "record_kind": "opportunity",
        "title": "Dormant deal", "reason": "No activity for 45 days.", "value": 5000,
    }], db=db))
    summary = run(rs.compose_for_tenant(db, queue, TENANT))
    assert summary["strategies_composed"] == 1, summary


# ------------------------------------------------------- the plan's lifecycle
#
# Each of these is a way the composer sweep, which runs every hour, used to undo or
# block work that had already moved on. A review found them by running the sweep twice.

def _approve_plan(db, strategy):
    import approval_queue as aq
    run(aq.decide(db, tenant_id=TENANT, approval_id=strategy["approval_id"],
                  decision=aq.APPROVED, actor="admin@example.com"))
    run(rs.set_state(db, TENANT, strategy["id"], state=rs.STATE_APPROVED,
                     actor="admin@example.com"))


def test_a_later_sweep_never_moves_a_running_case_back(env):
    """A regression this branch introduced and fixed: re-linking the approved plan moved
    an executing case back to `approved` on every sweep, so it re-ran hourly and could
    never be engaged."""
    import recovery_runner as runner

    db, queue = env
    seed_dormant_opportunity(db)
    run(second_chance.run_detection(db, queue, TENANT))
    run(rs.compose_for_tenant(db, queue, TENANT))
    case = run(rc.list_cases(db, TENANT))[0]
    _approve_plan(db, run(rs.get_strategy(db, TENANT, case["plan_reference"])))
    run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.EXECUTING

    run(rs.compose_for_tenant(db, queue, TENANT))
    run(rs.compose_for_tenant(db, queue, TENANT))
    after = run(rc.get_case(db, TENANT, case["id"]))
    assert after["state"] == rc.EXECUTING
    moves = [entry["action"] for entry in after["history"]]
    assert moves.count(rc.APPROVED) == 1, moves


def test_a_full_queue_does_not_starve_the_other_sources(env):
    """With a hundred open Second Chance items, cases from every other source used to get
    a planning budget of zero."""
    db, queue = env
    for index in range(rs.COMPOSE_LIMIT):
        run(queue.enqueue(tenant_id=TENANT, queue=second_chance.QUEUE_NAME,
                          item_type=second_chance.TYPE_STALLED_LEAD,
                          payload={"record_id": f"opp_{index}", "record_kind": "opportunity",
                                   "title": "Idle", "reason": "Idle"},
                          dedupe_key=f"filler:{index}", actor="test"))
    missed = run(rc.open_case(db, missed_call_event()))
    run(rs.compose_for_tenant(db, queue, TENANT))
    assert run(rc.get_case(db, TENANT, missed["id"]))["plan_reference"]


def test_a_lapsed_plan_is_replanned_and_a_rejected_one_is_left_for_a_person(env):
    import approval_queue as aq

    db, queue = env
    lapsed = run(rc.open_case(db, missed_call_event()))
    rejected = run(rc.open_case(db, missed_call_event()))
    run(rs.compose_for_tenant(db, queue, TENANT))
    lapsed_plan = run(rc.get_case(db, TENANT, lapsed["id"]))["plan_reference"]
    rejected_plan = run(rc.get_case(db, TENANT, rejected["id"]))["plan_reference"]

    run(db[aq.COLLECTION].update_one(
        {"id": run(rs.get_strategy(db, TENANT, lapsed_plan))["approval_id"]},
        {"$set": {"expires_at": "2000-01-01T00:00:00+00:00"}}))
    run(aq.expire_due(db, tenant_id=TENANT))
    run(rs.release_lapsed(db, tenant_id=TENANT))
    rejected_strategy = run(rs.get_strategy(db, TENANT, rejected_plan))
    run(aq.decide(db, tenant_id=TENANT, approval_id=rejected_strategy["approval_id"],
                  decision=aq.REJECTED, actor="admin@example.com"))
    run(rs.set_state(db, TENANT, rejected_plan, state=rs.STATE_REJECTED,
                     actor="admin@example.com"))

    released = run(rc.get_case(db, TENANT, lapsed["id"]))
    assert released["state"] == rc.PLANNED and released["plan_reference"] is None

    run(rs.compose_for_tenant(db, queue, TENANT))
    replanned = run(rc.get_case(db, TENANT, lapsed["id"]))
    assert replanned["state"] == rc.AWAITING_APPROVAL
    assert replanned["plan_reference"] and replanned["plan_reference"] != lapsed_plan

    left = run(rc.get_case(db, TENANT, rejected["id"]))
    assert left["state"] == rc.PLANNED and left["plan_reference"] == rejected_plan, \
        "a plan a person rejected is not re-proposed every hour"


def test_one_case_holds_one_plan_even_when_its_work_item_comes_back(env):
    """Resolving the Second Chance item and re-detecting the record used to compose a
    second plan and repoint the approved case at it; the runner then refused the case."""
    import recovery_runner as runner

    db, queue = env
    seed_dormant_opportunity(db)
    run(second_chance.run_detection(db, queue, TENANT))
    run(rs.compose_for_tenant(db, queue, TENANT))
    case = run(rc.list_cases(db, TENANT))[0]
    plan = run(rs.get_strategy(db, TENANT, case["plan_reference"]))
    _approve_plan(db, plan)

    item = run(queue.list_items(tenant_id=TENANT, status="open",
                                queue=second_chance.QUEUE_NAME))[0]
    run(queue.resolve(item["id"], tenant_id=TENANT, actor="owner@example.com",
                      resolution="handled"))
    run(second_chance.run_detection(db, queue, TENANT))
    run(rs.compose_for_tenant(db, queue, TENANT))

    after = run(rc.get_case(db, TENANT, case["id"]))
    assert after["plan_reference"] == plan["id"]
    assert after["approval_reference"] == plan["approval_id"]
    assert len(run(rs.list_strategies(db, TENANT))) == 1
    run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.EXECUTING


# ------------------------------------------------------ linking a case to its client

def test_an_operator_can_name_the_client_a_missed_call_turned_out_to_be(env):
    db, _ = env
    run(db.contacts.insert_one({"tenant_id": TENANT, "id": "con_caller", "name": "Caller"}))
    run(db.companies.insert_one({"tenant_id": TENANT, "id": "co_caller", "name": "Caller Co"}))
    case = run(rc.open_case(db, missed_call_event()))
    linked = run(rc.link_crm_records(db, tenant_id=TENANT, case_id=case["id"],
                                     actor="ops@example.com", contact_id="con_caller",
                                     company_id="co_caller", opportunity_id=None))
    assert (linked["contact_id"], linked["company_id"]) == ("con_caller", "co_caller")
    assert linked["history"][-1]["action"] == "linked"


def test_a_link_is_never_re_pointed_at_another_client(env):
    """Otherwise any payment could be made to belong to the case after the fact."""
    db, _ = env
    run(db.companies.insert_many([{"tenant_id": TENANT, "id": "co_a", "name": "A"},
                                  {"tenant_id": TENANT, "id": "co_b", "name": "B"}]))
    case = run(rc.open_case(db, missed_call_event()))
    run(rc.link_crm_records(db, tenant_id=TENANT, case_id=case["id"], actor="ops",
                            company_id="co_a"))
    with pytest.raises(rc.LinkConflict):
        run(rc.link_crm_records(db, tenant_id=TENANT, case_id=case["id"], actor="ops",
                                company_id="co_b"))
    # Naming the same record again is not a change.
    same = run(rc.link_crm_records(db, tenant_id=TENANT, case_id=case["id"], actor="ops",
                                   company_id="co_a"))
    assert same["company_id"] == "co_a"


def test_a_case_cannot_be_linked_to_another_tenants_record(env):
    db, _ = env
    run(db.contacts.insert_one({"tenant_id": OTHER_TENANT, "id": "con_x", "name": "X"}))
    case = run(rc.open_case(db, missed_call_event()))
    with pytest.raises(rc.CrossTenantReference):
        run(rc.link_crm_records(db, tenant_id=TENANT, case_id=case["id"], actor="ops",
                                contact_id="con_x"))
    with pytest.raises(rc.RecoveryCaseError):
        run(rc.link_crm_records(db, tenant_id=TENANT, case_id=case["id"], actor="ops",
                                plan_reference="rs_anything"))
    assert run(rc.get_case(db, TENANT, case["id"]))["contact_id"] is None


def test_adding_a_link_cannot_move_a_case_to_another_client(env):
    """A case about contact A (of company A) given company B accepted company B's
    invoices "via the case's company" -- a re-point made by addition."""
    db, _ = env
    run(db.companies.insert_many([{"tenant_id": TENANT, "id": "co_a2", "name": "A"},
                                  {"tenant_id": TENANT, "id": "co_b2", "name": "B"}]))
    run(db.contacts.insert_one({"tenant_id": TENANT, "id": "con_a2", "name": "A person",
                                "company_id": "co_a2"}))
    case = run(rc.open_case(db, missed_call_event()))
    run(rc.link_crm_records(db, tenant_id=TENANT, case_id=case["id"], actor="ops",
                            contact_id="con_a2"))
    with pytest.raises(rc.LinkConflict, match="different clients"):
        run(rc.link_crm_records(db, tenant_id=TENANT, case_id=case["id"], actor="ops",
                                company_id="co_b2"))
    agreed = run(rc.link_crm_records(db, tenant_id=TENANT, case_id=case["id"], actor="ops",
                                     company_id="co_a2"))
    assert agreed["company_id"] == "co_a2"
