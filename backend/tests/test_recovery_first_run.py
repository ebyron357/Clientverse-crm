"""Readiness for the first live Second Chance run.

Two guarantees the owner runbook (manual §6.9) relies on:

* **A recovery draft can never reach a client.** The runner's draft is an internal note
  (recovery reason, estimated value). Even approved, with consent, an authorised channel
  and a provider, it is refused at dispatch -- and its approval is not spent.
* **The dry run writes nothing.** `second_chance.preview` reports what a sweep would find
  without creating a case, a work item or an event, and the admin route adds whether email
  could leave at all.
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

import approval_queue as aq
import conversations as cv
import recovery_case as rc
import recovery_runner as runner
import recovery_strategy as rs
import second_chance as sc
from work_queue import WorkQueue

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT = "ten_first_run"

_LOOP = None


def run(coro):
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


@pytest.fixture()
def env():
    db_name = f"cv_first_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[db_name]
    queue = WorkQueue(db)
    for ensure in (queue.ensure_indexes(), rc.ensure_indexes(db), rs.ensure_indexes(db),
                   aq.ensure_indexes(db), cv.ensure_indexes(db)):
        run(ensure)
    run(db.tenants.insert_one({"tenant_id": TENANT, "name": "First run"}))
    yield db, queue
    run(client.drop_database(db_name))
    client.close()


class RecordingProvider:
    channel = cv.CHANNEL_EMAIL
    name = "recording-test-provider"

    def __init__(self):
        self.sent = []

    async def send(self, *, message, conversation, idempotency_key):
        self.sent.append(message["id"])
        return cv.DeliveryResult(provider_message_id=f"prov_{len(self.sent)}",
                                 detail={"accepted": True})


def email_ready(db):
    """Every channel precondition met: Gmail connected and certified for this tenant."""
    run(db.integration_connections.insert_one(
        {"tenant_id": TENANT, "provider": "gmail", "status": "active"}))
    run(db.integrations.insert_one({"tenant_id": TENANT, "name": "Gmail", "status": "CONNECTED"}))
    registry = cv.ProviderRegistry()
    provider = RecordingProvider()
    registry.register(provider)
    return registry, provider


def drafted_recovery_message(db):
    """An approved case run by the runner: its outbound step is a drafted placeholder."""
    run(db.contacts.insert_one({"tenant_id": TENANT, "id": "con_1", "name": "Ada",
                                "email": "ada@example.invalid"}))
    run(db.opportunities.insert_one({"tenant_id": TENANT, "id": "opp_1", "name": "Renewal",
                                     "stage": "proposal", "value": 40000,
                                     "contact_id": "con_1"}))
    case = run(rc.open_case(db, rc.normalize_event(
        tenant_id=TENANT, source=rc.SOURCE_DORMANT_DEAL, source_event_id="opportunity:opp_1",
        reason="No activity for 30 days.", title="Renewal", contact_id="con_1",
        opportunity_id="opp_1", potential_value=40000,
        evidence={"idle_days": 30, "stage": "proposal", "value": 40000})))
    strategy = run(rs.compose_for_case(db, TENANT, case))
    run(aq.decide(db, tenant_id=TENANT, approval_id=strategy["approval_id"],
                  decision=aq.APPROVED, actor="owner@example.com"))
    run(rc.set_state(db, tenant_id=TENANT, case_id=case["id"], state=rc.APPROVED,
                     actor="owner@example.com"))
    result = run(runner.run_case(db, tenant_id=TENANT, case_id=case["id"]))
    drafted = [s for s in result["steps"] if s["status"] == runner.STEP_DRAFTED]
    assert drafted, "the shipped strategy has an outbound step to draft"
    return run(cv.get_message(db, TENANT, drafted[0]["message_id"]))


def approve_and_consent(db, message):
    run(aq.decide(db, tenant_id=TENANT, approval_id=message["approval_id"],
                  decision=aq.APPROVED, actor="owner@example.com"))
    run(cv.mark_approved(db, tenant_id=TENANT, message_id=message["id"],
                         actor="owner@example.com"))
    run(cv.record_consent(db, tenant_id=TENANT, conversation_id=message["conversation_id"],
                          state=cv.CONSENT_GRANTED, actor="owner@example.com",
                          basis="Existing customer asked to be contacted (test)"))


# ------------------------------------------------------- the placeholder never leaves

def test_the_runner_draft_is_marked_as_a_placeholder(env):
    db, _ = env
    message = drafted_recovery_message(db)
    assert cv.is_placeholder_body(message["body"])
    approval = run(aq.get(db, TENANT, message["approval_id"]))
    assert cv.PLACEHOLDER_BLOCK in approval["blocked_reasons"]


def test_an_approved_placeholder_is_refused_even_when_everything_else_is_ready(env):
    db, _ = env
    message = drafted_recovery_message(db)
    registry, provider = email_ready(db)
    approve_and_consent(db, message)

    with pytest.raises(cv.DeliveryRefused) as exc:
        run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=message["id"],
                                actor="owner@example.com", registry=registry))
    assert exc.value.reason == cv.REFUSAL_PLACEHOLDER
    assert provider.sent == []
    stored = run(cv.get_message(db, TENANT, message["id"]))
    assert stored["status"] == cv.BLOCKED
    assert stored["blocked_reason"] == cv.REFUSAL_PLACEHOLDER
    # The refusal came before the approval was touched, so it was not spent.
    approval = run(aq.get(db, TENANT, message["approval_id"]))
    assert approval["status"] == aq.APPROVED
    assert (approval.get("execution") or {}).get("state") != aq.EXECUTION_CONSUMED


def test_a_message_a_person_wrote_in_the_same_thread_does_send(env):
    """The guard is about the placeholder text, not about recovery conversations."""
    db, _ = env
    placeholder = drafted_recovery_message(db)
    registry, provider = email_ready(db)
    approve_and_consent(db, placeholder)

    written = run(cv.draft_message(db, tenant_id=TENANT,
                                   conversation_id=placeholder["conversation_id"],
                                   body="Hi Ada, shall we pick the renewal back up?",
                                   actor="owner@example.com"))
    written = run(cv.request_approval(db, tenant_id=TENANT, message_id=written["id"],
                                      actor="owner@example.com", registry=registry))
    run(aq.decide(db, tenant_id=TENANT, approval_id=written["approval_id"],
                  decision=aq.APPROVED, actor="owner@example.com"))
    run(cv.mark_approved(db, tenant_id=TENANT, message_id=written["id"],
                         actor="owner@example.com"))
    sent = run(cv.attempt_delivery(db, tenant_id=TENANT, message_id=written["id"],
                                   actor="owner@example.com", registry=registry))
    assert sent["status"] == cv.SENT
    assert provider.sent == [written["id"]]


@pytest.mark.parametrize("body,expected", [
    (f"{cv.PLACEHOLDER_MARKER} for follow up]\n\nRecovery reason: x", True),
    (f"   \n{cv.PLACEHOLDER_MARKER} for follow up]", True),
    ("Hi Ada, quoting: [DRAFT — prepared by ClientVerse for x]", False),
    ("", False),
    (None, False),
])
def test_placeholder_detection(body, expected):
    assert cv.is_placeholder_body(body) is expected


# ---------------------------------------------------------------------- the dry run

def stalled_opportunity(db, opp_id, *, days=30):
    then = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    run(db.opportunities.insert_one({"tenant_id": TENANT, "id": opp_id, "name": opp_id,
                                     "stage": "proposal", "value": 1000,
                                     "created_at": then, "updated_at": then}))


async def _snapshot(db):
    names = sorted(await db.list_collection_names())
    return {name: await db[name].count_documents({}) for name in names}


def test_preview_reports_detections_and_writes_nothing(env):
    db, _ = env
    stalled_opportunity(db, "opp_quiet")
    before = run(_snapshot(db))

    result = run(sc.preview(db, TENANT))

    assert run(_snapshot(db)) == before
    assert result["dry_run"] is True and result["writes"] == 0
    assert result["contacts_anyone"] is False
    assert result["stalled_leads_detected"] == 1
    assert result["would_open_cases"] == 1
    row = result["detections"][0]
    assert row["record_id"] == "opp_quiet"
    assert row["outcome"] == sc.PREVIEW_WOULD_OPEN
    assert row["recovery_case_id"] is None


def test_preview_tells_new_from_already_open_and_closed(env):
    db, queue = env
    stalled_opportunity(db, "opp_open")
    stalled_opportunity(db, "opp_closed")
    run(sc.run_detection(db, queue, TENANT))
    closed = run(rc.find_by_source_event(db, TENANT, rc.SOURCE_DORMANT_DEAL,
                                         "opportunity:opp_closed"))
    run(db[rc.COLLECTION].update_one({"id": closed["id"]}, {"$set": {"state": rc.CLOSED}}))
    stalled_opportunity(db, "opp_new")

    result = run(sc.preview(db, TENANT))
    outcomes = {r["record_id"]: r["outcome"] for r in result["detections"]}
    assert outcomes == {"opp_open": sc.PREVIEW_ALREADY_OPEN,
                        "opp_closed": sc.PREVIEW_CLOSED,
                        "opp_new": sc.PREVIEW_WOULD_OPEN}
    assert (result["would_open_cases"], result["already_open_cases"],
            result["closed_cases_skipped"]) == (1, 1, 1)


def test_preview_limit_truncates_rows_not_counts(env):
    db, _ = env
    for i in range(3):
        stalled_opportunity(db, f"opp_{i}")
    result = run(sc.preview(db, TENANT, limit=2))
    assert len(result["detections"]) == 2
    assert result["truncated"] is True
    assert result["would_open_cases"] == 3


# --------------------------------------------------------------- the admin route

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/")
API = f"{BASE}/api"


def _register():
    email = f"first_run_{uuid.uuid4().hex[:10]}@example.com"
    response = requests.post(f"{API}/auth/register",
                             json={"email": email, "password": "FirstRunHttp2026!",
                                   "name": "First run"}, timeout=30)
    assert response.status_code == 200, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body.get('token') or body.get('access_token')}"}


def test_preview_route_is_a_read_and_reports_email_readiness():
    headers = _register()
    before = requests.get(f"{API}/recovery-cases", headers=headers, timeout=30)
    assert before.status_code == 200, before.text
    response = requests.get(f"{API}/second-chance/preview", headers=headers, timeout=60)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dry_run"] is True and body["contacts_anyone"] is False
    email = body["email"]
    # A new organization has no Gmail connection, so nothing could be sent.
    assert email["channel_authorized"] is False
    assert email["gmail_status"] != "active"
    assert email["gmail_send_permission_recorded"] is False
    assert "an explicit send" in email["still_required_per_message"]
    after = requests.get(f"{API}/recovery-cases", headers=headers, timeout=30)
    assert after.json() == before.json()


def test_preview_route_requires_a_session():
    response = requests.get(f"{API}/second-chance/preview", timeout=30)
    assert response.status_code == 401
