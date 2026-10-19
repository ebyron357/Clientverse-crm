"""Automations: triggers from real events, steps that act inside the CRM, stop rules, and a
receipt for every run.

Leads arrive through the public form door and deals are won through the API, exactly as in
production, so each test exercises the real event path into the engine. Wait steps are
resumed by calling `resume_due` with a time in the future, the way the watcher would.
"""

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ["LEAD_SLA_WATCHER"] = "0"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_automations_unit")
os.environ.setdefault("JWT_SECRET", "automations-unit-jwt-secret-long-enough-12345678")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "admin@automations.example")
os.environ.setdefault("ADMIN_PASSWORD", "Automations-Admin-Passw0rd-1!")

from fastapi.testclient import TestClient

import automations
import detectors
import server

SITE = "https://www.example-agency.example"
UTC = timezone.utc


@pytest.fixture(scope="module")
def client():
    registered = server.lead_pipeline.db
    server.db = registered
    server.mclient = getattr(registered, "client", server.mclient)
    server.automation_engine.db = registered
    with TestClient(server.app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _no_providers():
    server.lead_pipeline.registry = None
    yield
    server.lead_pipeline.registry = None


def call(client, fn, *args, **kwargs):
    async def _run():
        return await fn(*args, **kwargs)
    return client.portal.call(_run)


def find_all(client, collection, query):
    async def _run():
        return await server.db[collection].find(query, {"_id": 0}).to_list(1000)
    return client.portal.call(_run)


def settle(client):
    """Let automations started by the request's events finish their immediate steps."""
    call(client, server.automation_engine.idle)


def resume(client, **ahead):
    call(client, server.automation_engine.resume_due, now=datetime.now(UTC) + timedelta(**ahead))


def register(client):
    email = f"owner-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post("/api/auth/register",
                           json={"email": email, "password": "Str0ng-Passw0rd!", "name": "Taylor Owner"})
    assert response.status_code == 200, response.text
    client.cookies.clear()
    body = response.json()
    return {"email": email, "tenant_id": body["user"]["tenant_id"],
            "headers": {"Authorization": f"Bearer {body['token']}"}}


def add_member(client, owner):
    email = f"member-{uuid.uuid4().hex[:8]}@example.com"
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    call(client, server.db.users.insert_one,
         {"user_id": user_id, "email": email, "name": "Morgan Member", "role": "member",
          "tenant_id": owner["tenant_id"], "password_hash": server.hash_password("Str0ng-Passw0rd!"),
          "created_at": server.now_iso()})
    call(client, server.db.memberships.insert_one,
         {"id": f"mem_{uuid.uuid4().hex[:8]}", "tenant_id": owner["tenant_id"], "user_id": user_id,
          "email": email, "role": "member", "status": "active"})
    return {"email": email, "headers": {"Authorization": f"Bearer {server.create_access_token(user_id, email)}"}}


def contact_form(client, owner):
    fields = [{"key": "first_name", "required": True}, {"key": "last_name", "required": True},
              {"key": "email", "required": True}, {"key": "phone"}, {"key": "message"}]
    response = client.post("/api/website-forms", headers=owner["headers"],
                           json={"name": "Contact us", "preset": "custom", "fields": fields})
    assert response.status_code == 200, response.text
    return response.json()


def submit(client, form, **data):
    payload = {"first_name": "Jordan", "last_name": "Lee", "email": f"{uuid.uuid4().hex[:6]}@brightline.example",
               "phone": "555-410-2201", "message": "We need a new website.", "_sid": uuid.uuid4().hex,
               "_elapsed_ms": 9000, **data}
    response = client.post(f"/api/public/forms/{form['public_key']}/submit", content=json.dumps(payload),
                           headers={"Content-Type": "text/plain;charset=UTF-8", "Origin": SITE})
    assert response.status_code == 200, response.text
    settle(client)
    return call(client, server.db[detectors.WEB_ENQUIRIES].find_one, {"id": response.json()["id"]}, {"_id": 0})


def recipe(client, owner, key, on=True):
    response = client.post("/api/automations/from-recipe", headers=owner["headers"], json={"recipe": key})
    assert response.status_code == 200, response.text
    automation = response.json()
    assert automation["status"] == "draft"
    if on:
        assert client.post(f"/api/automations/{automation['id']}/status", headers=owner["headers"],
                           json={"status": "on"}).status_code == 200
    return automation


def runs(client, owner, automation):
    response = client.get(f"/api/automations/{automation['id']}/runs", headers=owner["headers"])
    assert response.status_code == 200, response.text
    return response.json()["items"]


def automation_tasks(client, owner):
    return [t for t in find_all(client, "tasks", {"tenant_id": owner["tenant_id"]})
            if (t.get("source") or {}).get("kind") == "automation"]


# ----------------------------------------------------------------------------- tests

def test_a_new_lead_gets_a_call_task_and_an_alert_if_nobody_replies(client):
    owner = register(client)
    automation = recipe(client, owner, "speed_to_lead")
    lead = submit(client, contact_form(client, owner), first_name="Amara", last_name="Osei")
    [run] = runs(client, owner, automation)
    assert run["status"] == "waiting" and run["contact_id"] == lead["contact_id"]
    assert run["trigger_label"] == "A website lead arrives"
    first, wait = run["receipt"]
    assert first["status"] == "done" and first["detail"].startswith("Created “Call Amara now”")
    [task] = automation_tasks(client, owner)
    assert task["title"] == "Call Amara now" and task["priority"] == "high"
    assert task["related_type"] == "contact" and task["related_id"] == lead["contact_id"]
    assert first["links"] == {"task_id": task["id"]}
    assert wait["status"] == "waiting" and wait["label"] == "Wait 5 minutes"
    # Not yet: the wait is not over.
    resume(client, minutes=1)
    assert runs(client, owner, automation)[0]["status"] == "waiting"
    resume(client, minutes=6)
    [run] = runs(client, owner, automation)
    assert run["status"] == "completed"
    assert [step["status"] for step in run["receipt"]] == ["done", "done", "done"]
    assert run["receipt"][1]["detail"] == "Waited 5 minutes"
    notes = find_all(client, "notifications", {"tenant_id": owner["tenant_id"], "category": "automation"})
    assert any(n["title"] == "Amara Osei has waited 5 minutes and nobody has replied yet." for n in notes)


def test_the_run_stops_as_soon_as_someone_calls_them(client):
    owner = register(client)
    automation = recipe(client, owner, "speed_to_lead")
    lead = submit(client, contact_form(client, owner), first_name="Ben", last_name="Carter")
    response = client.post("/api/activities", headers=owner["headers"],
                           json={"type": "call", "related_type": "contact", "related_id": lead["contact_id"],
                                 "body": "Talked about the website.", "outcome": "talked"})
    assert response.status_code == 200, response.text
    resume(client, minutes=6)
    [run] = runs(client, owner, automation)
    assert run["status"] == "stopped"
    assert run["stop_reason"] == "They were contacted (a call, text, email or meeting was logged)"
    assert not [n for n in find_all(client, "notifications", {"tenant_id": owner["tenant_id"], "category": "automation"})
                if "has waited" in n["title"]]


def test_one_event_one_run_and_one_active_run_per_person(client):
    owner = register(client)
    automation = recipe(client, owner, "speed_to_lead")
    form = contact_form(client, owner)
    lead = submit(client, form, email="same.person@example.com")
    event = call(client, server.db.domain_events.find_one,
                 {"tenant_id": owner["tenant_id"], "event_type": "lead.received", "resource_id": lead["id"]}, {"_id": 0})
    # The same event handled again (a retry, a second instance) starts nothing new.
    assert call(client, server.automation_engine.handle, event) == []
    # The same person writing again while their first run is waiting starts nothing new.
    submit(client, form, email="same.person@example.com", message="Following up on my message.")
    assert len(runs(client, owner, automation)) == 1
    assert len(automation_tasks(client, owner)) == 1


def test_what_an_automation_does_never_starts_another_automation(client):
    owner = register(client)
    recipe(client, owner, "speed_to_lead")
    contact = client.post("/api/contacts", headers=owner["headers"], json={"name": "Loop Check"}).json()
    created = server.automation_engine
    before = len(created._pending)
    created.on_event({"id": "evt_x", "tenant_id": owner["tenant_id"], "event_type": "lead.received",
                      "resource_id": contact["id"], "source": automations.SOURCE, "payload": {}})
    assert len(created._pending) == before


def test_a_won_deal_starts_onboarding_and_turning_it_off_stops_the_wait(client):
    owner = register(client)
    headers = owner["headers"]
    automation = recipe(client, owner, "deal_won_onboarding")
    contact = client.post("/api/contacts", headers=headers, json={"name": "Lena Fischer", "lifecycle": "qualified"}).json()
    deal = client.post("/api/opportunities", headers=headers,
                       json={"name": "Content retainer", "value": 3000, "contact_ids": [contact["id"]]}).json()
    assert client.patch(f"/api/opportunities/{deal['id']}/stage", headers=headers, json={"stage": "closed_won"}).status_code == 200
    settle(client)
    [run] = runs(client, owner, automation)
    assert run["status"] == "waiting" and run["deal_id"] == deal["id"]
    titles = sorted(t["title"] for t in automation_tasks(client, owner))
    assert titles == ["Kickoff call with Lena Fischer (Content retainer)", "Send the welcome pack to Lena Fischer"]
    lifecycle = call(client, server.db.contacts.find_one, {"id": contact["id"]}, {"_id": 0, "lifecycle": 1})
    assert lifecycle == {"lifecycle": "customer"}
    response = client.post(f"/api/automations/{automation['id']}/status", headers=headers, json={"status": "off"})
    assert response.json() == {"status": "off", "stopped_runs": 1}
    [run] = runs(client, owner, automation)
    assert run["status"] == "stopped" and run["stop_reason"] == "The automation was turned off"
    resume(client, days=31)
    assert len(automation_tasks(client, owner)) == 2


def test_conditions_and_trigger_filters_choose_who_it_runs_for(client):
    owner = register(client)
    headers = owner["headers"]
    budget = client.post("/api/custom-fields", headers=headers, json={"object": "contacts", "label": "Budget", "type": "number"}).json()
    response = client.post("/api/automations", headers=headers, json={
        "name": "Big deals to proposal", "trigger": {"event": "opportunity.stage_changed", "stage": "proposal"},
        "conditions": [{"field": f"custom_fields.{budget['key']}", "op": "gt", "value": 10000}],
        "steps": [{"type": "create_task", "title": "Senior review of {{deal.name}}", "due_in_minutes": 60, "assign": "unassigned"}]})
    assert response.status_code == 200, response.text
    automation = response.json()
    client.post(f"/api/automations/{automation['id']}/status", headers=headers, json={"status": "on"})
    for name, amount, stage in (("Big", 50000, "proposal"), ("Small", 2000, "proposal"), ("Big but qualified", 50000, "qualified")):
        contact = client.post("/api/contacts", headers=headers, json={"name": name}).json()
        client.patch(f"/api/contacts/{contact['id']}", headers=headers, json={"custom_fields": {budget["key"]: amount}})
        deal = client.post("/api/opportunities", headers=headers, json={"name": f"{name} deal", "value": 1, "contact_ids": [contact["id"]]}).json()
        client.patch(f"/api/opportunities/{deal['id']}/stage", headers=headers, json={"stage": stage})
    settle(client)
    assert [t["title"] for t in automation_tasks(client, owner)] == ["Senior review of Big deal"]
    assert [t["assignee"] for t in automation_tasks(client, owner)] == [None]


def test_steps_are_checked_before_they_are_saved(client):
    owner = register(client)
    member = add_member(client, owner)
    headers = owner["headers"]
    base = {"name": "Check", "trigger": {"event": "lead.received"}}
    bad_steps = [
        [{"type": "send_sms", "message": "hi"}],
        [{"type": "wait", "minutes": 0}],
        [{"type": "wait", "minutes": 200000}],
        [{"type": "create_task", "title": ""}],
        [{"type": "set_field", "object": "contact", "field": "lifecycle", "value": "vip"}],
        [{"type": "set_field", "object": "contact", "field": "password_hash", "value": "x"}],
        [{"type": "create_task", "title": "x", "assign": "specific", "email": "stranger@example.com"}],
        [{"type": "notify", "audience": "the internet", "message": "hi"}],
    ]
    for steps in bad_steps:
        assert client.post("/api/automations", headers=headers, json={**base, "steps": steps}).status_code == 422, steps
    assert client.post("/api/automations", headers=headers, json={**base, "trigger": {"event": "user.logged_in"}}).status_code == 422
    assert client.post("/api/automations", headers=headers, json={**base, "stop_rules": ["moon_phase"]}).status_code == 422
    assert client.post("/api/automations", headers=headers,
                       json={**base, "conditions": [{"field": "password_hash", "op": "is_empty"}]}).status_code == 422
    empty = client.post("/api/automations", headers=headers, json=base).json()
    assert client.post(f"/api/automations/{empty['id']}/status", headers=headers, json={"status": "on"}).status_code == 422
    # Members can read automations and their receipts; only an admin changes them.
    assert client.get("/api/automations", headers=member["headers"]).status_code == 200
    assert client.post("/api/automations", headers=member["headers"], json=base).status_code == 403
    assert client.post(f"/api/automations/{empty['id']}/status", headers=member["headers"], json={"status": "on"}).status_code == 403


def test_a_test_run_says_what_would_happen_and_changes_nothing(client):
    owner = register(client)
    automation = recipe(client, owner, "deal_won_onboarding", on=False)
    contact = client.post("/api/contacts", headers=owner["headers"], json={"name": "Dana Reyes", "lifecycle": "lead"}).json()
    response = client.post(f"/api/automations/{automation['id']}/test", headers=owner["headers"],
                           json={"record_type": "contact", "record_id": contact["id"]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["matches"] is True and result["contact"] == "Dana Reyes"
    details = [step["detail"] for step in result["steps"]]
    assert details[0] == "Would set lifecycle to customer (now lead)"
    assert details[1] == f"Would create “Send the welcome pack to Dana Reyes” for {contact.get('owner') or 'nobody yet'}, due in 1 day"
    assert details[4] == "Would wait 30 days, then check the stop rules"
    assert automation_tasks(client, owner) == []
    assert call(client, server.db.contacts.find_one, {"id": contact["id"]}, {"_id": 0, "lifecycle": 1}) == {"lifecycle": "lead"}


def test_editing_an_automation_never_rewrites_a_run_in_progress(client):
    owner = register(client)
    automation = recipe(client, owner, "speed_to_lead")
    submit(client, contact_form(client, owner), first_name="Priya", last_name="Raman")
    response = client.patch(f"/api/automations/{automation['id']}", headers=owner["headers"],
                            json={"steps": [{"type": "notify", "audience": "everyone", "message": "Changed"}]})
    assert response.status_code == 200 and response.json()["version"] == 2
    resume(client, minutes=6)
    [run] = runs(client, owner, automation)
    assert run["automation_version"] == 1 and run["status"] == "completed"
    assert [step["type"] for step in run["receipt"]] == ["create_task", "wait", "notify"]


def test_an_admin_can_stop_one_run_by_hand(client):
    owner = register(client)
    automation = recipe(client, owner, "speed_to_lead")
    submit(client, contact_form(client, owner))
    [run] = runs(client, owner, automation)
    stopped = client.post(f"/api/automation-runs/{run['id']}/stop", headers=owner["headers"]).json()
    assert stopped["status"] == "stopped" and stopped["stop_reason"] == f"Stopped by {owner['email']}"
    assert client.post(f"/api/automation-runs/{run['id']}/stop", headers=owner["headers"]).status_code == 404


def test_automations_and_receipts_never_cross_tenants(client):
    owner = register(client)
    stranger = register(client)
    theirs = recipe(client, stranger, "speed_to_lead")
    submit(client, contact_form(client, owner))
    assert runs(client, stranger, theirs) == []
    assert client.get(f"/api/automations/{theirs['id']}", headers=owner["headers"]).status_code == 404
    assert client.get(f"/api/automations/{theirs['id']}/runs", headers=owner["headers"]).status_code == 404
    assert client.post(f"/api/automations/{theirs['id']}/status", headers=owner["headers"], json={"status": "off"}).status_code == 404
    assert client.get("/api/automations", headers=owner["headers"]).json()["items"] == []


def test_placeholders_and_durations_read_naturally():
    ctx = {"contact": {"name": "Amara Osei"}, "deal": {"name": "Ads"}, "company": None}
    assert automations.render("Call {{contact.first_name}} about {{ deal.name }}", ctx) == "Call Amara about Ads"
    assert automations.render("Hello {{company.name}} team", ctx) == "Hello team"
    assert automations.duration(5) == "5 minutes" and automations.duration(60) == "1 hour"
    assert automations.duration(2 * 24 * 60) == "2 days" and automations.duration(1) == "1 minute"
