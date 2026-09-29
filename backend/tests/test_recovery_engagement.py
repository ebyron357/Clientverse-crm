"""A recovery case must be able to finish.

Every stage of the north-star loop had its own tests, and each passed. What had never
been tested was the join -- the runner's draft actually leaving through the delivery
choke point, and the attribution ledger then confirming the recovery on that same case.
Run end to end, the loop broke in two places:

* The runner opened a contact-backed case's thread with the contact's id and no address,
  so the email adapter -- correctly refusing to guess -- rejected every automated
  recovery email.
* Nothing in the running system moved a case from `executing` to `engaged` when its
  counterparty was reached. `engaged` is the only state a recovery can be confirmed from,
  so an outcome the ledger rightly attributed still failed to mark the case recovered.
  The existing tests walked cases to `engaged` by hand, which is why none noticed.

These tests drive the real modules in order, with only the provider's network replaced.
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import approval_queue as aq
import attribution
import conversations as cv
import recovery_case as rc
import recovery_runner as runner
import recovery_strategy as rs
from work_queue import WorkQueue

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT = "ten_engage_a"
CLIENT_EMAIL = "ada@client.example"

_LOOP = None


def run(coro):
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


@pytest.fixture()
def db():
    db_name = f"cv_engage_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[db_name]
    for ensure in (WorkQueue(database).ensure_indexes(), rc.ensure_indexes(database),
                   rs.ensure_indexes(database), aq.ensure_indexes(database),
                   cv.ensure_indexes(database), attribution.ensure_indexes(database)):
        run(ensure)
    run(database.tenants.insert_one({"tenant_id": TENANT, "name": "A"}))
    # An authorised email channel: connected and marked configured, as in production
    # once the owner grants `gmail.send`.
    run(database.integration_connections.insert_one(
        {"tenant_id": TENANT, "provider": "gmail", "status": "active"}))
    run(database.integrations.insert_one(
        {"tenant_id": TENANT, "name": "Gmail", "status": "CONNECTED"}))
    yield database
    run(client.drop_database(db_name))
    client.close()


class AcceptingProvider:
    """The email adapter's contract with the network removed: it accepts, and says so."""

    channel = cv.CHANNEL_EMAIL
    name = "gmail"

    def __init__(self):
        self.sent = []

    async def send(self, *, message, conversation, idempotency_key):
        # The real adapter refuses to guess a recipient. So does this one.
        recipient = message.get("to_address") or next(
            (p.get("address") for p in conversation.get("participants") or []
             if p.get("kind") == cv.PARTICIPANT_CONTACT and p.get("address")), None)
        if not recipient:
            raise cv.DeliveryRejected("This conversation has no email address to send to.")
        self.sent.append((message["id"], recipient))
        return cv.DeliveryResult(provider_message_id=f"gmail-{len(self.sent)}",
                                 detail={"thread_id": "thr-1",
                                         "rfc822_message_id": f"cv-{uuid.uuid4().hex}@x"})


@pytest.fixture()
def registry():
    registry = cv.ProviderRegistry()
    provider = AcceptingProvider()
    registry.register(provider)
    registry.provider = provider
    return registry


def executing_case(db):
    """A contact-backed case, planned, approved and run -- the state production reaches."""
    run(db.companies.insert_one({"tenant_id": TENANT, "id": "co_1", "name": "Acme"}))
    run(db.workspaces.insert_one({"tenant_id": TENANT, "id": "ws_1", "company_id": "co_1",
                                  "name": "Acme", "owner": "owner@example.com"}))
    run(db.contacts.insert_one({"tenant_id": TENANT, "id": "con_1", "name": "Ada",
                                "email": CLIENT_EMAIL}))
    run(db.opportunities.insert_one({
        "tenant_id": TENANT, "id": "opp_1", "name": "Acme renewal", "stage": "proposal",
        "value": 40000, "company_id": "co_1", "owner": "owner@example.com"}))
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_DORMANT_DEAL,
        source_event_id="opportunity:opp_1", reason="No activity for 30 days.",
        title="Acme renewal", workspace_id="ws_1", company_id="co_1", contact_id="con_1",
        opportunity_id="opp_1", potential_value=40000,
        evidence={"idle_days": 30, "stage": "proposal", "value": 40000})))
    strategy = run(rs.compose_for_case(db, TENANT, case))
    run(aq.decide(db, tenant_id=TENANT, approval_id=strategy["approval_id"],
                  decision=aq.APPROVED, actor="admin@example.com"))
    run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=rc.APPROVED,
                     actor="admin@example.com"))
    result = run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    drafted = [s for s in result["steps"] if s["status"] == runner.STEP_DRAFTED
               and s["channel"] == cv.CHANNEL_EMAIL]
    assert drafted, "the plan for a contact with an email address must include email"
    return run(rc.get_case(db, TENANT, case["id"])), drafted[0]["message_id"]


def approve_and_consent(db, message_id):
    message = run(cv.get_message(db, TENANT, message_id))
    run(cv.record_consent(db, tenant_id=TENANT, conversation_id=message["conversation_id"],
                          state=cv.CONSENT_GRANTED, actor="admin@example.com",
                          basis="Client asked to be kept informed by email."))
    run(aq.decide(db, tenant_id=TENANT, approval_id=message["approval_id"],
                  decision=aq.APPROVED, actor="admin@example.com"))
    return run(cv.mark_approved(db, tenant_id=TENANT, message_id=message_id,
                                actor="admin@example.com"))


# ------------------------------------------------------------------ the recipient

def test_the_runner_addresses_a_contact_backed_draft_to_the_contact(db):
    _, message_id = executing_case(db)
    message = run(cv.get_message(db, TENANT, message_id))
    assert message["to_address"] == CLIENT_EMAIL
    conversation = run(cv.get_conversation(db, TENANT, message["conversation_id"]))
    contact = [p for p in conversation["participants"]
               if p["kind"] == cv.PARTICIPANT_CONTACT][0]
    assert contact == {"kind": cv.PARTICIPANT_CONTACT, "id": "con_1",
                       "address": CLIENT_EMAIL, "display_name": None}


def test_the_approver_is_shown_who_the_message_goes_to(db):
    _, message_id = executing_case(db)
    message = run(cv.get_message(db, TENANT, message_id))
    approval = run(aq.get(db, TENANT, message["approval_id"]))
    facts = {fact["label"]: fact["value"] for fact in approval["facts"]}
    assert facts["Recipient"] == CLIENT_EMAIL


def test_the_contact_address_is_read_only_within_the_tenant(db):
    """A contact id that exists only in another tenant must not lend its address."""
    run(db.contacts.insert_one({"tenant_id": "ten_other", "id": "con_x",
                                "email": "stranger@elsewhere.example"}))
    assert run(runner._contact_address(db, TENANT, "con_x")) is None


def test_a_phone_only_counterparty_is_not_addressed_as_email():
    conversation = {"participants": [{"kind": cv.PARTICIPANT_CONTACT, "id": None,
                                      "address": "+15550100"}]}
    assert runner._email_recipient_of(conversation) is None


# ------------------------------------------------------------------ engagement

def test_a_provider_accepted_send_engages_the_case(db, registry):
    case, message_id = executing_case(db)
    assert case["state"] == rc.EXECUTING
    approve_and_consent(db, message_id)

    sent = run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message_id,
                                   actor="admin@example.com", registry=registry))
    assert sent["status"] == cv.SENT
    assert registry.provider.sent == [(message_id, CLIENT_EMAIL)]

    engaged = run(rc.get_case(db, TENANT, case["id"]))
    assert engaged["state"] == rc.ENGAGED
    assert engaged["contact_count"] == 1
    assert engaged["first_contact_at"] == sent["sent_at"]
    assert engaged["history"][-1]["detail"]["message_id"] == message_id


def test_a_refused_or_failed_send_does_not_engage_the_case(db, registry):
    case, message_id = executing_case(db)
    # Approved but no consent: refused at the choke point, nothing reached anyone.
    message = run(cv.get_message(db, TENANT, message_id))
    run(aq.decide(db, tenant_id=TENANT, approval_id=message["approval_id"],
                  decision=aq.APPROVED, actor="admin@example.com"))
    run(cv.mark_approved(db, tenant_id=TENANT, message_id=message_id,
                         actor="admin@example.com"))
    with pytest.raises(cv.DeliveryRefused):
        run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message_id,
                                actor="admin@example.com", registry=registry))
    after = run(rc.get_case(db, TENANT, case["id"]))
    assert after["state"] == rc.EXECUTING
    assert not after.get("contact_count")


def test_a_reconciled_dispatch_engages_the_case(db):
    """A send whose acknowledgement was lost, later found at the provider, did reach
    the client -- at the time it was sent."""

    class LosingProvider(AcceptingProvider):
        async def send(self, *, message, conversation, idempotency_key):
            raise TimeoutError("connection dropped after dispatch")

    registry = cv.ProviderRegistry()
    registry.register(LosingProvider())
    case, message_id = executing_case(db)
    approve_and_consent(db, message_id)
    unknown = run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message_id,
                                      actor="worker", registry=registry))
    assert unknown["status"] == cv.OUTCOME_UNKNOWN
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.EXECUTING

    run(cv.reconcile_unknown(db, tenant_id=TENANT, message_id=message_id, actor="ops",
                             found=True, provider_message_id="gmail-found"))
    assert run(rc.get_case(db, TENANT, case["id"]))["state"] == rc.ENGAGED


def test_contact_is_recorded_but_does_not_skip_states_the_plan_has_not_reached(db):
    """A message sent by hand on a case that is still being planned is contact, not
    execution. It is recorded; the state machine is not bypassed."""
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_MISSED_CALL, source_event_id="call_9",
        reason="Rang out.")))
    run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=rc.PLANNED))
    noted = run(rc.record_contact(db, tenant_id=TENANT, case_id=case["id"],
                                  kind=rc.CONTACT_OUTBOUND, message_id="msg_1"))
    assert noted["state"] == rc.PLANNED
    assert noted["contact_count"] == 1


def test_contact_on_an_engaged_or_terminal_case_changes_no_state(db):
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_MISSED_CALL, source_event_id="call_10",
        reason="Rang out.")))
    for state in (rc.PLANNED, rc.AWAITING_APPROVAL, rc.APPROVED, rc.EXECUTING):
        run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=state))
    first = run(rc.record_contact(db, tenant_id=TENANT, case_id=case["id"],
                                  kind=rc.CONTACT_REPLY, message_id="msg_r1"))
    assert first["state"] == rc.ENGAGED
    again = run(rc.record_contact(db, tenant_id=TENANT, case_id=case["id"],
                                  kind=rc.CONTACT_REPLY, message_id="msg_r2"))
    assert again["state"] == rc.ENGAGED and again["reply_count"] == 2
    run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=rc.CLOSED))
    closed = run(rc.record_contact(db, tenant_id=TENANT, case_id=case["id"],
                                   kind=rc.CONTACT_OUTBOUND, message_id="msg_o"))
    assert closed["state"] == rc.CLOSED


def test_contact_is_tenant_scoped_and_validates_its_kind(db):
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_MISSED_CALL, source_event_id="call_11",
        reason="Rang out.")))
    assert run(rc.record_contact(db, tenant_id="ten_other", case_id=case["id"],
                                 kind=rc.CONTACT_OUTBOUND, message_id="m")) is None
    assert not run(rc.get_case(db, TENANT, case["id"])).get("contact_count")
    with pytest.raises(rc.RecoveryCaseError):
        run(rc.record_contact(db, tenant_id=TENANT, case_id=case["id"], kind="guess",
                              message_id="m"))


# ------------------------------------------------------------------ the whole loop

def test_a_recovery_can_run_from_approval_to_confirmed_revenue(db, registry):
    """Run, approve, send, pay, attribute -- and the case ends recovered."""
    case, message_id = executing_case(db)
    approve_and_consent(db, message_id)
    run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message_id,
                            actor="admin@example.com", registry=registry))

    paid_at = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    run(db.invoices.insert_one({"tenant_id": TENANT, "id": "inv_1", "total": 12500.0,
                                "currency": "USD", "status": "paid",
                                "paid_at": paid_at}))
    entry = run(attribution.record_outcome(
        db, tenant_id=TENANT, case_id=case["id"], kind=attribution.OUTCOME_INVOICE_PAID,
        record_id="inv_1", actor="admin@example.com"))

    assert entry["claim"] == attribution.CLAIM_ATTRIBUTED
    assert entry["case_updated"] is True, entry.get("case_update_error")
    recovered = run(rc.get_case(db, TENANT, case["id"]))
    assert recovered["state"] == rc.RECOVERED
    assert recovered["confirmed_value"] == 12500.0
    # Potential and confirmed stay separate figures.
    assert recovered["potential_value"] == 40000
