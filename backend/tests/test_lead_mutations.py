"""Real replica-set certification; deliberately never substitutes mongomock sessions."""

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from pymongo.errors import AutoReconnect
from test_website_forms import call, create_form, find_all, find_one, register
from test_website_forms import client as client_fixture

import detectors
import lead_mutations as mutations
import server

client = client_fixture


@pytest.fixture
def case(client, monkeypatch):
    hello = call(client, server.db.command, "hello")
    if not hello.get("setName"):
        pytest.fail("Lead mutation certification requires real MongoDB with a replica set")
    call(client, mutations.prepare, server.db)
    owner = register(client)
    form = create_form(client, owner)
    response = client.post(f"/api/website-forms/{form['id']}/test", headers=owner["headers"], json={})
    assert response.status_code == 200, response.text
    lead = response.json()["lead"]
    monkeypatch.setenv("LEAD_MUTATION_TENANTS", owner["tenant_id"])
    yield owner, lead


def intent(lead, **changes):
    return {"operation_id": uuid.uuid4().hex, "expected_version": lead.get("version", 0),
            "status": "responded", "note": "A deliberate follow-up note", **changes}


def save(client, owner, lead, body):
    return client.post(f"/api/leads/{lead['id']}/mutations", headers=owner["headers"], json=body)


def notes(client, owner):
    return find_all(client, "crm_activities", {"tenant_id": owner["tenant_id"], "type": "note"})


def test_receipt_replay_precedes_version_check(client, case):
    owner, lead = case
    body = intent(lead)
    first = save(client, owner, lead, body)
    assert first.status_code == 200, first.text
    assert first.json()["state"] == "committed"
    assert first.json()["lead"]["version"] == lead["version"] + 1
    assert save(client, owner, lead, body).json() == first.json()
    assert len(notes(client, owner)) == 1
    receipt = client.get(f"/api/leads/{lead['id']}/operations/{body['operation_id']}", headers=owner["headers"])
    assert receipt.json() == first.json()
    task = find_one(client, "tasks", {"id": lead["task_id"]})
    assert task["status"] == "done"
    assert find_all(client, "work_queue", {"tenant_id": owner["tenant_id"], "type": "domain_event.dispatch"})


def test_same_key_different_payload_rejected(client, case):
    owner, lead = case
    body = intent(lead)
    assert save(client, owner, lead, body).status_code == 200
    response = save(client, owner, lead, {**body, "note": "Different intent"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "operation_key_reused"
    assert len(notes(client, owner)) == 1


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_requests_have_one_business_effect(client, case, same_key):
    owner, lead = case
    first = intent(lead)
    second = first if same_key else intent(lead)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda body: save(client, owner, lead, body), [first, second]))
    assert sorted(r.status_code for r in results) == ([200, 200] if same_key else [200, 409])
    assert len(notes(client, owner)) == 1
    assert len(find_all(client, mutations.RECEIPTS, {"tenant_id": owner["tenant_id"]})) == 1


@pytest.mark.parametrize("collection,method,status", [
    (detectors.WEB_ENQUIRIES, "update_one", "closed"), ("tasks", "update_one", "responded"),
    ("contacts", "update_one", "spam"), ("opportunities", "update_one", "spam"),
    ("crm_activities", "insert_one", "closed"), ("domain_events", "insert_one", "closed"),
    ("work_queue", "insert_one", "closed"), (mutations.RECEIPTS, "insert_one", "closed"),
])
def test_failure_after_each_write_rolls_back_everything(client, case, monkeypatch, collection, method, status):
    owner, lead = case
    query = {"tenant_id": owner["tenant_id"]}
    collections = [detectors.WEB_ENQUIRIES, "tasks", "contacts", "opportunities", "crm_activities", "domain_events", "work_queue", mutations.RECEIPTS]
    before = {name: find_all(client, name, query) for name in collections}
    cls = type(server.db[collection])
    original = getattr(cls, method)

    async def fail_after_write(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        if self.name == collection and kwargs.get("session"):
            raise RuntimeError("injected write failure")
        return result

    monkeypatch.setattr(cls, method, fail_after_write)
    with pytest.raises(RuntimeError, match="injected write failure"):
        save(client, owner, lead, intent(lead, status=status))
    for name in collections:
        assert find_all(client, name, query) == before[name], name


def test_lost_commit_acknowledgment_reconciles_receipt(client, case, monkeypatch):
    owner, lead = case
    original = mutations.transact

    async def commit_then_disconnect(db, callback):
        await original(db, callback)
        raise AutoReconnect("simulated dropped response")

    monkeypatch.setattr(mutations, "transact", commit_then_disconnect)
    body = intent(lead)
    response = save(client, owner, lead, body)
    assert response.status_code == 200
    assert save(client, owner, lead, body).json() == response.json()
    assert len(notes(client, owner)) == 1


def test_unknown_outcome_is_not_reported_saved(client, case, monkeypatch):
    owner, lead = case

    async def disconnect(db, callback):
        raise AutoReconnect("unavailable")

    monkeypatch.setattr(mutations, "transact", disconnect)
    response = save(client, owner, lead, intent(lead))
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "outcome_unknown"
    assert notes(client, owner) == []


def test_same_status_note_has_no_false_status_event(client, case):
    owner, lead = case
    response = save(client, owner, lead, intent(lead, status=lead["status"]))
    assert response.status_code == 200
    assert len(notes(client, owner)) == 1
    assert not find_all(client, "domain_events", {"tenant_id": owner["tenant_id"], "event_type": "lead.status_changed"})


def test_missing_contact_rejects_entire_intent(client, case):
    owner, lead = case
    call(client, server.db.contacts.delete_one, {"id": lead["contact_id"], "tenant_id": owner["tenant_id"]})
    response = save(client, owner, lead, intent(lead))
    assert response.status_code == 422
    current = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead["id"]})
    assert current["status"] == lead["status"]
    assert current["version"] == lead["version"]


def test_spam_reopen_preserves_archive_history_and_reopens_task(client, case):
    owner, lead = case
    spam = save(client, owner, lead, intent(lead, status="spam", note=""))
    assert spam.status_code == 200
    assert find_one(client, "contacts", {"id": lead["contact_id"]})["archived_reason"] == "spam"
    reopened = save(client, owner, lead, intent(spam.json()["lead"], status="new", note=""))
    assert reopened.status_code == 200
    assert find_one(client, "tasks", {"id": lead["task_id"]})["status"] == "todo"
    assert reopened.json()["lead"]["sla"]["first_response_at"] is None
    # Reopening a lead never silently restores an archived contact/deal.
    assert find_one(client, "contacts", {"id": lead["contact_id"]})["archived_at"]


def test_legacy_version_defaults_without_backfill(client, case):
    owner, lead = case
    call(client, server.db[detectors.WEB_ENQUIRIES].update_one, {"id": lead["id"]}, {"$unset": {"version": ""}})
    response = save(client, owner, lead, intent(lead, expected_version=0))
    assert response.status_code == 200
    assert response.json()["lead"]["version"] == 1


def test_cohort_rejects_obsolete_clients_and_invalid_status(client, case):
    owner, lead = case
    old = client.patch(f"/api/leads/{lead['id']}", headers=owner["headers"], json={"status": "closed"})
    assert old.status_code == 428
    assert save(client, owner, lead, intent(lead, status="invalid")).status_code == 422
    assert save(client, owner, lead, intent(lead, expected_version=True)).status_code == 422


def test_receipt_and_target_are_tenant_isolated_and_auth_required(client, case):
    owner, lead = case
    body = intent(lead)
    assert save(client, owner, lead, body).status_code == 200
    stranger = register(client)
    assert save(client, stranger, lead, body).status_code == 404
    url = f"/api/leads/{lead['id']}/operations/{body['operation_id']}"
    assert client.get(url, headers=stranger["headers"]).status_code == 404
    assert client.get(url).status_code == 401
    call(client, server.db.memberships.update_many, {"tenant_id": owner["tenant_id"]}, {"$set": {"status": "disabled"}})
    assert save(client, owner, lead, body).status_code in (401, 403)


def test_task_completion_and_lead_save_cannot_overwrite_each_other(client, case):
    owner, lead = case
    with ThreadPoolExecutor(max_workers=2) as pool:
        task = pool.submit(client.patch, f"/api/crm/tasks/{lead['task_id']}", headers=owner["headers"], json={"status": "done"})
        update = pool.submit(save, client, owner, lead, intent(lead, status="closed"))
        assert task.result().status_code == 200
        assert update.result().status_code in (200, 409)
    current = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead["id"]})
    assert current["status"] in ("closed", "responded")
    assert current["version"] > lead["version"]


def test_legacy_task_writer_cannot_bypass_cohort_transactions(client, case):
    owner, lead = case
    response = client.patch(f"/api/tasks/{lead['task_id']}", headers=owner["headers"], json={"status": "done"})
    assert response.status_code == 428
    assert find_one(client, "tasks", {"id": lead["task_id"]})["status"] == "todo"


def test_prior_outreach_does_not_reclose_a_deliberately_reopened_lead(client, case):
    owner, lead = case
    call(client, server.db.crm_activities.insert_one, {
        "id": uuid.uuid4().hex, "tenant_id": owner["tenant_id"], "related_type": "contact",
        "related_id": lead["contact_id"], "type": "call", "occurred_at": lead["received_at"]})
    response = save(client, owner, lead, intent(lead))
    reopened = save(client, owner, lead, intent(response.json()["lead"], status="new", note=""))
    assert reopened.status_code == 200
    assert call(client, server.lead_pipeline.sync_responses, owner["tenant_id"]) == 0
    assert find_one(client, detectors.WEB_ENQUIRIES, {"id": lead["id"]})["status"] == "new"


def test_outbox_replay_does_not_create_or_send_a_second_delivery(client, case, monkeypatch):
    owner, lead = case
    assert save(client, owner, lead, intent(lead)).status_code == 200
    call(client, server.db.webhooks.insert_one, {"id": uuid.uuid4().hex, "tenant_id": owner["tenant_id"],
                                               "enabled": True, "events": ["lead.status_changed"]})
    calls = []

    async def deliver(delivery, hook):
        calls.append(delivery["id"])
        await server.db.webhook_deliveries.update_one({"id": delivery["id"]}, {"$set": {"status": "delivered"}})

    monkeypatch.setattr(server, "_do_delivery", deliver)
    event = find_one(client, "domain_events", {"tenant_id": owner["tenant_id"], "event_type": "lead.status_changed"})
    job = find_one(client, "work_queue", {"tenant_id": owner["tenant_id"], "payload.event_id": event["id"]})
    call(client, server._handle_committed_event, job)
    call(client, server._handle_committed_event, job)
    assert len(calls) == 1
    assert len(find_all(client, "webhook_deliveries", {"tenant_id": owner["tenant_id"], "event_id": event["id"]})) == 1


def test_disabling_rollout_preserves_existing_receipts(client, case, monkeypatch):
    owner, lead = case
    body = intent(lead)
    first = save(client, owner, lead, body)
    monkeypatch.setenv("LEAD_MUTATION_TENANTS", "")
    assert save(client, owner, lead, body).json() == first.json()
    assert save(client, owner, lead, intent(first.json()["lead"])).status_code == 503


@pytest.mark.parametrize("missing", ["topology", "index"])
def test_preparation_failure_never_falls_back_to_sequential_writes(client, case, monkeypatch, missing):
    owner, lead = case
    if missing == "topology":
        cls = type(server.db)
        original = cls.command
        async def command(self, name, *args, **kwargs):
            return {} if name == "hello" else await original(self, name, *args, **kwargs)
        monkeypatch.setattr(cls, "command", command)
    else:
        cls = type(server.db[mutations.RECEIPTS])
        original = cls.index_information
        async def indexes(self, *args, **kwargs):
            return {} if self.name == mutations.RECEIPTS else await original(self, *args, **kwargs)
        monkeypatch.setattr(cls, "index_information", indexes)
    assert save(client, owner, lead, intent(lead)).status_code == 503
    assert notes(client, owner) == []
    assert find_one(client, detectors.WEB_ENQUIRIES, {"id": lead["id"]})["version"] == lead["version"]


def test_stale_scheduled_response_cannot_reverse_reopen(client, case):
    owner, lead = case
    response = save(client, owner, lead, intent(lead))
    assert response.status_code == 200
    reopened = save(client, owner, lead, intent(response.json()["lead"], status="new", note=""))
    assert reopened.status_code == 200
    assert call(client, server.lead_pipeline.mark_responded, lead, via="task_completed") is False
    assert find_one(client, detectors.WEB_ENQUIRIES, {"id": lead["id"]})["status"] == "new"
