"""Website forms, driven the way an agent's website actually drives them.

The intake door these replace had no test that posted from another origin, as an HTML
form, or with a real-estate field -- which is exactly how it shipped refusing browsers,
refusing HTML forms and dropping every field a form sent. So every test here goes in
through the public HTTP door, with the headers a browser sends, and then reads back what
the CRM did: the contact, the owner, the deal and its value, the call-back task, the
alert, the event a webhook would carry, and what happens when nobody responds.

Runs in-process against the real `app` (and its lifespan), like the security-header
tests, so no separate server or network is needed.
"""

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
os.environ["LEAD_SLA_WATCHER"] = "0"  # the sweep is driven explicitly below
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_website_forms_unit")
os.environ.setdefault("JWT_SECRET", "website-forms-unit-jwt-secret-long-enough-123")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "admin@website-forms.example")
os.environ.setdefault("ADMIN_PASSWORD", "Website-Forms-Admin-1!")

from fastapi.testclient import TestClient

import approval_queue
import conversations as cv
import detectors
import server
import website_forms as wf

SITE = "https://www.agent-homes.example"
OTHER_SITE = "https://copycat.example"


@pytest.fixture(scope="module")
def client():
    # Route modules (crm_core, recovery_intake, website_forms, ...) hold the database
    # object they were registered with. Other in-process tests swap `server.db` for a
    # fresh client, so point the globals back at that registered object: then every
    # route in this test sees one database. One TestClient for the module keeps it on
    # one event loop, which a real MongoDB (motor binds to its first loop) requires.
    registered = server.lead_pipeline.db
    server.db = registered
    server.mclient = getattr(registered, "client", server.mclient)
    with TestClient(server.app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _no_fake_provider():
    server.lead_pipeline.registry = None
    yield
    server.lead_pipeline.registry = None


def call(client, fn, *args, **kwargs):
    """Run a coroutine on the app's own event loop (motor is bound to it)."""
    async def _run():
        return await fn(*args, **kwargs)
    return client.portal.call(_run)


def find_one(client, collection, query):
    return call(client, server.db[collection].find_one, query, {"_id": 0})


def find_all(client, collection, query):
    async def _run():
        return await server.db[collection].find(query, {"_id": 0}).to_list(1000)
    return client.portal.call(_run)


def wait_for(client, probe, seconds=5.0):
    """Poll for something a background task does; fail loudly if it never happens."""
    import time
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = probe()
        if result:
            return result
        time.sleep(0.05)
    raise AssertionError("timed out waiting for background work")


def register(client, name="Agent"):
    email = f"agent-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post("/api/auth/register",
                           json={"email": email, "password": "Str0ng-Passw0rd!", "name": name})
    assert response.status_code == 200, response.text
    client.cookies.clear()
    body = response.json()
    return {"email": email, "tenant_id": body["user"]["tenant_id"],
            "headers": {"Authorization": f"Bearer {body['token']}"}}


def add_member(client, tenant_id, email=None, role="member"):
    email = email or f"member-{uuid.uuid4().hex[:8]}@example.com"
    call(client, server.db.memberships.insert_one,
         {"id": f"mem_{uuid.uuid4().hex[:8]}", "tenant_id": tenant_id,
          "user_id": f"user_{uuid.uuid4().hex[:8]}", "email": email, "role": role,
          "status": "active"})
    return email


def create_form(client, owner, preset="showing_request", settings=None, name="Showing form"):
    response = client.post("/api/website-forms", headers=owner["headers"],
                           json={"name": name, "preset": preset, "settings": settings or {}})
    assert response.status_code == 200, response.text
    return response.json()


def browser_submit(client, form, data, origin=SITE):
    """What the embed script sends: JSON as text/plain, so the browser skips preflight."""
    import json
    return client.post(f"/api/public/forms/{form['public_key']}/submit",
                       content=json.dumps(data),
                       headers={"Content-Type": "text/plain;charset=UTF-8", "Origin": origin})


def lead(**overrides):
    data = {"first_name": "Jane", "last_name": "Buyer", "email": "jane.buyer@example.com",
            "phone": "(555) 010-0100", "property_address": "12 Oak St",
            "listing_id": "MLS123", "preferred_date": "2030-05-01",
            "preferred_time": "Morning", "pre_approved": "Yes",
            "message": "Can I see it Saturday?", "consent_sms": True,
            "utm_source": "google", "utm_campaign": "spring", "page_url": f"{SITE}/listings/12-oak",
            "_sid": uuid.uuid4().hex, "_elapsed_ms": 9000}
    data.update(overrides)
    return data


# ------------------------------------------------------------- the door itself

def test_a_website_on_another_domain_passes_the_browser_preflight(client):
    response = client.options("/api/public/forms/f_anything/submit",
                              headers={"Origin": SITE, "Access-Control-Request-Method": "POST",
                                       "Access-Control-Request-Headers": "content-type"})
    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == SITE
    # Never credentials: the CRM session cookie must not ride along.
    assert "access-control-allow-credentials" not in response.headers


def test_the_private_api_stays_closed_to_other_origins(client):
    response = client.options("/api/contacts",
                              headers={"Origin": SITE, "Access-Control-Request-Method": "GET"})
    assert response.status_code == 400
    assert response.headers.get("access-control-allow-origin") != SITE


def test_a_browser_submission_becomes_worked_crm_business(client):
    owner = register(client)
    form = create_form(client, owner, settings={
        "opportunity": {"value_mode": "commission", "commission_rate": 3, "fixed_value": 5000},
        "assignment": {"mode": "specific", "users": [owner["email"]]}})
    data = lead(price_max="$450,000", custom_unknown_field="kept anyway")
    response = browser_submit(client, form, data)
    assert response.status_code == 200, response.text
    assert response.headers["access-control-allow-origin"] == SITE
    body = response.json()
    assert body["accepted"] is True

    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": body["id"]})
    # Nothing the form sent is lost.
    assert stored["property_address"] == "12 Oak St" and stored["listing_id"] == "MLS123"
    assert stored["fields"]["pre_approved"] == "Yes"
    assert stored["fields"]["preferred_date"] == "2030-05-01"
    assert stored["fields"]["price_max"] == 450000.0
    assert stored["extra"]["custom_unknown_field"] == "kept anyway"
    assert stored["attribution"]["utm_source"] == "google"
    assert stored["consent"]["sms"] is True and stored["consent"]["sms_text"]

    contact = find_one(client, "contacts", {"id": stored["contact_id"]})
    assert contact["email"] == "jane.buyer@example.com" and contact["phone"] == "(555) 010-0100"
    assert contact["owner"] == owner["email"] and contact["lead_source"] == "website"
    assert "website-lead" in contact["tags"]

    deal = find_one(client, "opportunities", {"id": stored["opportunity_id"]})
    assert deal["value"] == 13500.0  # 3% of 450,000: expected commission
    assert deal["contact_ids"] == [contact["id"]] and deal["stage"] == "lead"
    assert stored["estimated_value"] == 13500.0

    task = find_one(client, "tasks", {"id": stored["task_id"]})
    assert task["assignee"] == owner["email"] and task["priority"] == "high"
    assert task["related_type"] == "contact" and task["related_id"] == contact["id"]
    due = datetime.fromisoformat(task["due_date"])
    assert due - datetime.fromisoformat(stored["received_at"]) == timedelta(minutes=5)

    alerts = find_all(client, "notifications", {"tenant_id": owner["tenant_id"], "type": "lead.new"})
    assert len(alerts) == 1 and alerts[0]["recipient"] == owner["email"]
    event = find_one(client, "domain_events", {"tenant_id": owner["tenant_id"],
                                               "event_type": "lead.received"})
    assert event["payload"]["email"] == "jane.buyer@example.com"
    assert event["payload"]["property_address"] == "12 Oak St"
    assert event["payload"]["attribution"]["utm_campaign"] == "spring"


def test_a_plain_html_form_post_redirects_to_the_thank_you_page(client):
    owner = register(client)
    form = create_form(client, owner, preset="contact",
                       settings={"redirect_url": f"{SITE}/thank-you"})
    response = client.post(f"/api/public/forms/{form['public_key']}/submit",
                           data={"first_name": "Sam", "email": "sam@example.com",
                                 "message": "Hello", "_hp": ""},
                           headers={"Origin": SITE, "Accept": "text/html"},
                           follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"{SITE}/thank-you"
    assert find_one(client, detectors.WEB_ENQUIRIES,
                    {"tenant_id": owner["tenant_id"], "email": "sam@example.com"})


def test_a_plain_html_form_without_redirect_gets_a_thank_you_page(client):
    owner = register(client)
    form = create_form(client, owner, preset="contact")
    response = client.post(f"/api/public/forms/{form['public_key']}/submit",
                           data={"first_name": "Sam", "email": "sam2@example.com"},
                           headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Thank you" in response.text


def test_missing_required_fields_are_named(client):
    owner = register(client)
    form = create_form(client, owner)
    response = browser_submit(client, form, {"first_name": "", "email": "not-an-email",
                                             "_elapsed_ms": 9000})
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert "first_name" in errors and "email" in errors and "phone" in errors
    assert not find_all(client, detectors.WEB_ENQUIRIES, {"tenant_id": owner["tenant_id"]})


def test_a_visitor_cannot_set_the_money_value_of_their_own_lead(client):
    owner = register(client)
    form = create_form(client, owner, settings={"opportunity": {"fixed_value": 8000}})
    response = browser_submit(client, form, lead(estimated_value="1e300"))
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": response.json()["id"]})
    assert stored["estimated_value"] == 8000.0
    assert stored["extra"]["estimated_value"] == "1e300"


def test_an_absurd_price_falls_back_to_the_configured_value(client):
    owner = register(client)
    form = create_form(client, owner, settings={
        "opportunity": {"value_mode": "commission", "commission_rate": 3, "fixed_value": 6000}})
    response = browser_submit(client, form, lead(price_max="750m"))  # a typo, not a home
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": response.json()["id"]})
    assert stored["estimated_value"] == 6000.0


# ------------------------------------------------------------------- abuse

def test_a_bot_filling_the_honeypot_is_answered_like_a_person_and_dropped(client):
    owner = register(client)
    form = create_form(client, owner)
    response = browser_submit(client, form, lead(_hp="http://spam.example"))
    assert response.status_code == 200 and response.json()["accepted"] is True
    assert not find_all(client, detectors.WEB_ENQUIRIES, {"tenant_id": owner["tenant_id"]})
    assert not find_all(client, "contacts", {"tenant_id": owner["tenant_id"], "lead_source": "website"})
    saved = find_one(client, wf.FORMS, {"id": form["id"]})
    assert saved["stats"]["spam_blocked"] == 1


def test_an_instant_submission_is_treated_as_a_bot(client):
    owner = register(client)
    form = create_form(client, owner)
    browser_submit(client, form, lead(_elapsed_ms=150))
    assert not find_all(client, detectors.WEB_ENQUIRIES, {"tenant_id": owner["tenant_id"]})


def test_a_flood_from_one_visitor_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(wf, "RATE_PER_VISITOR_PER_HOUR", 3)
    owner = register(client)
    form = create_form(client, owner)
    codes = [browser_submit(client, form, lead(email=f"v{i}@example.com", phone=f"555010{i:04d}")).status_code
             for i in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]
    assert len(find_all(client, detectors.WEB_ENQUIRIES, {"tenant_id": owner["tenant_id"]})) == 3


def test_a_retry_or_double_click_is_filed_once(client):
    owner = register(client)
    form = create_form(client, owner)
    data = lead()
    first = browser_submit(client, form, data).json()
    again = browser_submit(client, form, data).json()  # same _sid: a network retry
    resent = browser_submit(client, form, {**data, "_sid": uuid.uuid4().hex}).json()  # double click
    assert first["id"] == again["id"] == resent["id"]
    assert len(find_all(client, detectors.WEB_ENQUIRIES, {"tenant_id": owner["tenant_id"]})) == 1
    assert len(find_all(client, "tasks", {"tenant_id": owner["tenant_id"]})) == 1


def test_a_form_limited_to_its_websites_refuses_others(client):
    owner = register(client)
    form = create_form(client, owner, settings={"allowed_origins": [SITE]})
    assert browser_submit(client, form, lead(), origin=OTHER_SITE).status_code == 403
    assert browser_submit(client, form, lead(), origin=SITE).status_code == 200
    # A server-side integration (Zapier, a WordPress plugin) sends no Origin at all.
    import json
    response = client.post(f"/api/public/forms/{form['public_key']}/submit",
                           content=json.dumps(lead(email="zap@example.com", phone="5550100999")),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 200


# ---------------------------------------------------------- contacts & owners

def test_a_returning_lead_is_matched_not_duplicated(client):
    owner = register(client)
    form = create_form(client, owner)
    first = browser_submit(client, form, lead()).json()
    second = browser_submit(client, form, lead(email="JANE.BUYER@example.com",
                                               phone="555.010.0100",
                                               listing_id="MLS999",
                                               message="Another one")).json()
    assert first["id"] != second["id"]
    contacts = find_all(client, "contacts", {"tenant_id": owner["tenant_id"],
                                             "lead_source": "website"})
    assert len(contacts) == 1
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": second["id"]})
    assert stored["contact_id"] == contacts[0]["id"] and stored["created_contact"] is False
    # The open deal from the first enquiry is reused, not doubled.
    assert len(find_all(client, "opportunities", {"tenant_id": owner["tenant_id"]})) == 1


def test_a_lead_matches_a_contact_entered_by_hand_by_phone(client):
    owner = register(client)
    created = client.post("/api/contacts", headers=owner["headers"],
                          json={"name": "Pat Seller"}).json()
    client.patch(f"/api/contacts/{created['id']}", headers=owner["headers"],
                 json={"phone": "+1 555-010-0177"})
    form = create_form(client, owner)
    response = browser_submit(client, form, lead(email="pat.new@example.com", phone="5550100177"))
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": response.json()["id"]})
    assert stored["contact_id"] == created["id"]


def test_round_robin_spreads_leads_across_agents(client):
    owner = register(client)
    alice = add_member(client, owner["tenant_id"])
    bob = add_member(client, owner["tenant_id"])
    form = create_form(client, owner, settings={
        "assignment": {"mode": "round_robin", "users": [alice, bob]}})
    owners = []
    for i in range(4):
        response = browser_submit(client, form, lead(email=f"rr{i}@example.com",
                                                     phone=f"555020{i:04d}"))
        owners.append(find_one(client, detectors.WEB_ENQUIRIES,
                               {"id": response.json()["id"]})["assigned_to"])
    assert owners == [alice, bob, alice, bob]


# ------------------------------------------------------- the response clock

def test_completing_the_call_back_task_records_the_response(client):
    owner = register(client)
    form = create_form(client, owner)
    lead_id = browser_submit(client, form, lead()).json()["id"]
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead_id})
    client.patch(f"/api/crm/tasks/{stored['task_id']}", headers=owner["headers"],
                 json={"status": "done"})
    call(client, server.lead_pipeline.sweep, owner["tenant_id"])
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead_id})
    assert stored["status"] == "responded"
    assert stored["sla"]["responded_via"] == "task_completed"
    assert stored["sla"]["response_minutes"] == 0
    # A responded lead is not a lost lead.
    found = call(client, detectors.detect_web_enquiries, server.db, owner["tenant_id"], grace_hours=0)
    assert lead_id not in {d["record_id"] for d in found}


def test_a_logged_call_counts_as_a_response(client):
    owner = register(client)
    form = create_form(client, owner)
    lead_id = browser_submit(client, form, lead()).json()["id"]
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead_id})
    client.post("/api/activities", headers=owner["headers"],
                json={"type": "call", "related_type": "contact", "related_id": stored["contact_id"],
                      "subject": "Called back"})
    call(client, server.lead_pipeline.sweep, owner["tenant_id"])
    assert find_one(client, detectors.WEB_ENQUIRIES, {"id": lead_id})["status"] == "responded"


def log_activity(client, owner, contact_id, **body):
    response = client.post("/api/activities", headers=owner["headers"],
                           json={"related_type": "contact", "related_id": contact_id, **body})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_call_logged_on_the_contact_marks_its_lead_contacted_at_once(client):
    owner = register(client)
    form = create_form(client, owner)
    lead_id = browser_submit(client, form, lead()).json()["id"]
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead_id})
    log_activity(client, owner, stored["contact_id"], type="call", outcome="left_voicemail",
                 body="Left a message about Saturday")
    # No sweep: the contact record's "Log a call" must move the lead straight away,
    # exactly as "Mark contacted" in the inbox does.
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead_id})
    assert stored["status"] == "responded"
    assert stored["sla"]["responded_via"] == "activity_call"
    assert stored["responded_by"] == owner["email"]
    assert find_one(client, "tasks", {"id": stored["task_id"]})["status"] == "done"
    shown = client.get(f"/api/leads/{lead_id}", headers=owner["headers"]).json()
    assert shown["status"] == "responded"


def test_a_logged_text_counts_as_a_response(client):
    owner = register(client)
    form = create_form(client, owner)
    lead_id = browser_submit(client, form, lead()).json()["id"]
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead_id})
    log_activity(client, owner, stored["contact_id"], type="text", body="Texted a time")
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead_id})
    assert stored["status"] == "responded" and stored["sla"]["responded_via"] == "activity_text"


def test_a_note_is_not_a_response(client):
    owner = register(client)
    form = create_form(client, owner)
    lead_id = browser_submit(client, form, lead()).json()["id"]
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead_id})
    log_activity(client, owner, stored["contact_id"], type="note", body="Looks keen")
    call(client, server.lead_pipeline.sweep, owner["tenant_id"])
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead_id})
    assert stored["status"] == "new"
    assert find_one(client, "tasks", {"id": stored["task_id"]})["status"] == "todo"


def test_the_leads_own_email_reply_does_not_stop_its_clock(client):
    owner = register(client)
    form = create_form(client, owner)
    lead_id = browser_submit(client, form, lead()).json()["id"]
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead_id})
    # What an inbound reply writes on the contact (server._on_inbound_reply).
    call(client, server.db.crm_activities.insert_one, {
        "id": f"act_{uuid.uuid4().hex[:8]}", "tenant_id": owner["tenant_id"], "type": "email",
        "related_type": "contact", "related_id": stored["contact_id"],
        "subject": "Re: Thanks for reaching out", "body": "Is Saturday ok?",
        "occurred_at": datetime.now(timezone.utc).isoformat(), "direction": "inbound",
        "outcome": "reply_received", "actor": "jane.buyer@example.com"})
    call(client, server.lead_pipeline.sweep, owner["tenant_id"])
    assert find_one(client, detectors.WEB_ENQUIRIES, {"id": lead_id})["status"] == "new"


def test_a_fault_after_logging_never_loses_the_logged_call(client, monkeypatch):
    owner = register(client)
    form = create_form(client, owner)
    lead_id = browser_submit(client, form, lead()).json()["id"]
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead_id})

    async def broken(activity):
        raise RuntimeError("lead store unavailable")

    monkeypatch.setattr(server.lead_pipeline, "recognise_activity", broken)
    logged = log_activity(client, owner, stored["contact_id"], type="call")
    assert find_one(client, "crm_activities", {"id": logged["id"]})
    monkeypatch.undo()
    # The watcher still recognises it on its next pass.
    call(client, server.lead_pipeline.sweep, owner["tenant_id"])
    assert find_one(client, detectors.WEB_ENQUIRIES, {"id": lead_id})["status"] == "responded"


def test_a_contacts_website_requests_can_be_listed_inside_the_tenant(client):
    owner = register(client)
    other = register(client, name="Other")
    form = create_form(client, owner)
    jane = browser_submit(client, form, lead()).json()["id"]
    sam = browser_submit(client, form, lead(email="sam.seller@example.com",
                                            phone="555-010-0222")).json()["id"]
    jane_contact = find_one(client, detectors.WEB_ENQUIRIES, {"id": jane})["contact_id"]
    mine = client.get("/api/leads", headers=owner["headers"],
                      params={"contact_id": jane_contact}).json()
    assert [item["id"] for item in mine["items"]] == [jane] and mine["total"] == 1
    assert sam not in {item["id"] for item in mine["items"]}
    # Another tenant naming this contact's id sees nothing of it.
    theirs = client.get("/api/leads", headers=other["headers"],
                        params={"contact_id": jane_contact}).json()
    assert theirs["items"] == [] and theirs["total"] == 0


def test_leads_name_their_agent_and_only_from_inside_the_tenant(client):
    owner = register(client, name="Dana Agent")
    outsider = register(client, name="Outside Agent")
    form = create_form(client, owner, settings={
        "assignment": {"mode": "specific", "users": [owner["email"]]}})
    lead_id = browser_submit(client, form, lead()).json()["id"]
    listed = client.get("/api/leads", headers=owner["headers"]).json()["items"][0]
    assert listed["assigned_to"] == owner["email"] and listed["assigned_name"] == "Dana Agent"
    assert client.get(f"/api/leads/{lead_id}",
                      headers=owner["headers"]).json()["assigned_name"] == "Dana Agent"
    patched = client.patch(f"/api/leads/{lead_id}", headers=owner["headers"],
                           json={"status": "closed"}).json()
    assert patched["assigned_name"] == "Dana Agent"
    # An address that belongs to a user in another tenant is never resolved to a name.
    call(client, server.db[detectors.WEB_ENQUIRIES].update_one,
         {"id": lead_id}, {"$set": {"assigned_to": outsider["email"]}})
    shown = client.get(f"/api/leads/{lead_id}", headers=owner["headers"]).json()
    assert shown["assigned_to"] == outsider["email"] and shown["assigned_name"] is None


def test_marking_a_lead_responded_closes_its_call_back_task(client):
    owner = register(client)
    form = create_form(client, owner)
    lead_id = browser_submit(client, form, lead()).json()["id"]
    response = client.patch(f"/api/leads/{lead_id}", headers=owner["headers"],
                            json={"status": "responded", "note": "Booked Saturday"})
    assert response.status_code == 200 and response.json()["status"] == "responded"
    task = find_one(client, "tasks", {"id": response.json()["task_id"]})
    assert task["status"] == "done"


def test_an_unanswered_lead_is_escalated_once(client):
    owner = register(client)
    form = create_form(client, owner)
    lead_id = browser_submit(client, form, lead()).json()["id"]
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    call(client, server.db[detectors.WEB_ENQUIRIES].update_one,
         {"id": lead_id}, {"$set": {"sla.escalate_at": past}})
    first = call(client, server.lead_pipeline.sweep, owner["tenant_id"])
    second = call(client, server.lead_pipeline.sweep, owner["tenant_id"])
    assert first["escalated"] == 1 and second["escalated"] == 0
    breaches = find_all(client, "notifications", {"tenant_id": owner["tenant_id"],
                                                  "type": "lead.sla_breached"})
    assert len(breaches) == 1 and breaches[0]["severity"] == "critical"


def test_marking_spam_archives_what_the_submission_created(client):
    owner = register(client)
    form = create_form(client, owner)
    lead_id = browser_submit(client, form, lead()).json()["id"]
    stored = client.patch(f"/api/leads/{lead_id}", headers=owner["headers"],
                          json={"status": "spam"}).json()
    assert find_one(client, "contacts", {"id": stored["contact_id"]})["archived_at"]
    assert find_one(client, "opportunities", {"id": stored["opportunity_id"]})["archived_at"]
    assert find_one(client, "tasks", {"id": stored["task_id"]})["status"] == "cancelled"


# ------------------------------------------------------------ automatic reply

class FakeEmail:
    channel = cv.CHANNEL_EMAIL
    name = "fake-email"

    def __init__(self):
        self.sent = []

    async def send(self, *, message, conversation, idempotency_key):
        self.sent.append(message)
        return cv.DeliveryResult(provider_message_id=f"pm_{len(self.sent)}")


def test_the_automatic_reply_waits_for_its_template_to_be_approved(client):
    owner = register(client)
    form = create_form(client, owner, settings={"auto_reply": {"enabled": True}})
    assert form["auto_reply_state"]["state"] == "awaiting_approval"
    lead_id = browser_submit(client, form, lead()).json()["id"]
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead_id})
    contact = find_one(client, "contacts", {"id": stored["contact_id"]})
    saved_form = find_one(client, wf.FORMS, {"id": form["id"]})
    result = call(client, server.lead_pipeline.auto_reply, saved_form, stored, contact, owner["email"])
    assert result["status"] == "awaiting_template_approval"


def test_an_approved_template_replies_to_each_lead_automatically(client):
    owner = register(client)
    form = create_form(client, owner, settings={"auto_reply": {"enabled": True}})
    approval_id = form["auto_reply_state"]["approval_id"]
    decided = client.post(f"/api/approval-queue/{approval_id}/decision", headers=owner["headers"],
                          json={"decision": "approved", "rationale": "Wording approved"})
    assert decided.status_code == 200, decided.text
    # A connected, configured email channel and a provider that records what it sends.
    call(client, server.db.integration_connections.insert_one,
         {"tenant_id": owner["tenant_id"], "provider": "gmail", "status": "active"})
    call(client, server.db.integrations.insert_one,
         {"tenant_id": owner["tenant_id"], "name": "gmail", "provider": "gmail", "status": "CONNECTED"})
    registry = cv.ProviderRegistry()
    fake = FakeEmail()
    registry.register(fake)
    server.lead_pipeline.registry = registry

    lead_id = browser_submit(client, form, lead(email="reply.me@example.com",
                                                phone="5550300001")).json()["id"]
    # The reply goes out on its own, in the background, without anyone touching it.
    stored = wait_for(client, lambda: (lambda doc: doc if doc["auto_reply"]["status"] == "sent"
                                       else None)(find_one(client, detectors.WEB_ENQUIRIES,
                                                           {"id": lead_id})))
    contact = find_one(client, "contacts", {"id": stored["contact_id"]})
    saved_form = find_one(client, wf.FORMS, {"id": form["id"]})
    assert stored["conversation_id"]
    assert len(fake.sent) == 1
    assert fake.sent[0]["to_address"] == "reply.me@example.com"
    assert "Hi Jane," in fake.sent[0]["body"]
    # The per-message approval records the standing approval it rode on.
    message_approval = find_one(client, approval_queue.COLLECTION,
                                {"id": fake.sent[0]["approval_id"]})
    assert message_approval["decided_by"] == f"standing-approval:{approval_id}"
    # The same lead never gets a second reply.
    again = call(client, server.lead_pipeline.auto_reply, saved_form, stored, contact, owner["email"])
    assert again["status"] == "already_handled" and len(fake.sent) == 1


def test_editing_the_template_withdraws_its_approval(client):
    owner = register(client)
    form = create_form(client, owner, settings={"auto_reply": {"enabled": True}})
    client.post(f"/api/approval-queue/{form['auto_reply_state']['approval_id']}/decision",
                headers=owner["headers"], json={"decision": "approved"})
    edited = client.patch(f"/api/website-forms/{form['id']}", headers=owner["headers"],
                          json={"settings": {"auto_reply": {"body": "Different words, {first_name}."}}})
    assert edited.json()["auto_reply_state"]["state"] == "awaiting_approval"


# ------------------------------------------------------------ legacy & public

def test_the_legacy_intake_token_now_accepts_real_website_posts(client):
    owner = register(client)
    minted = client.post("/api/intake/tokens", headers=owner["headers"],
                         json={"label": "Old site"}).json()
    url = f"/api/intake/public/{minted['secret']}/web-enquiries"
    preflight = client.options(url, headers={"Origin": SITE, "Access-Control-Request-Method": "POST"})
    assert preflight.status_code == 204
    response = client.post(url, data={"name": "Lee Legacy", "email": "lee@example.com",
                                      "property_address": "9 Elm Rd", "mls_number": "A55"},
                           headers={"Origin": SITE, "Accept": "application/json"})
    assert response.status_code == 200, response.text
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": response.json()["id"]})
    assert stored["property_address"] == "9 Elm Rd" and stored["listing_id"] == "A55"
    assert stored["contact_id"] and stored["task_id"]


def test_the_hosted_page_can_be_framed_and_the_app_still_cannot(client):
    owner = register(client)
    form = create_form(client, owner)
    page = client.get(f"/api/public/forms/{form['public_key']}/page")
    assert page.status_code == 200 and form["public_key"] in page.text
    assert "frame-ancestors *" in page.headers["content-security-policy"]
    assert "x-frame-options" not in page.headers
    assert client.get("/api/health").headers["x-frame-options"] == "SAMEORIGIN"
    script = client.get("/api/public/forms/embed.js")
    assert script.status_code == 200 and "javascript" in script.headers["content-type"]
    config = client.get(f"/api/public/forms/{form['public_key']}/config").json()
    assert [f["key"] for f in config["fields"]][:3] == ["first_name", "last_name", "email"]
    assert "tenant_id" not in config
    # Each render fetches the config once: that is the form's view count.
    assert find_one(client, wf.FORMS, {"id": form["id"]})["stats"]["views"] == 1
    assert 'data-layout="slide-in"' in form["embed"]["slide_in"]


def test_a_paused_form_stops_accepting(client):
    owner = register(client)
    form = create_form(client, owner)
    client.patch(f"/api/website-forms/{form['id']}", headers=owner["headers"],
                 json={"status": "paused"})
    assert browser_submit(client, form, lead()).status_code == 404
    assert client.get(f"/api/public/forms/{form['public_key']}/config").status_code == 404


def test_forms_and_leads_are_tenant_scoped(client):
    owner = register(client)
    other = register(client, name="Other")
    form = create_form(client, owner)
    browser_submit(client, form, lead())
    assert client.get(f"/api/website-forms/{form['id']}", headers=other["headers"]).status_code == 404
    assert client.get("/api/leads", headers=other["headers"]).json()["total"] == 0
    assert client.get("/api/leads", headers=owner["headers"]).json()["total"] == 1


def test_members_cannot_create_forms(client):
    owner = register(client)
    member_email = add_member(client, owner["tenant_id"])
    token = server.create_access_token(
        find_one(client, "memberships", {"email": member_email})["user_id"], member_email)
    call(client, server.db.users.insert_one,
         {"user_id": find_one(client, "memberships", {"email": member_email})["user_id"],
          "email": member_email, "name": "Member", "role": "member",
          "tenant_id": owner["tenant_id"]})
    response = client.post("/api/website-forms", headers={"Authorization": f"Bearer {token}"},
                           json={"name": "Nope", "preset": "contact"})
    assert response.status_code == 403


def test_the_test_button_runs_the_real_pipeline(client):
    owner = register(client)
    form = create_form(client, owner, preset="home_valuation")
    response = client.post(f"/api/website-forms/{form['id']}/test", headers=owner["headers"], json={})
    assert response.status_code == 200, response.text
    stored = response.json()["lead"]
    assert stored["is_test"] is True and stored["contact_id"] and stored["task_id"]
    summary = client.get("/api/leads/summary", headers=owner["headers"]).json()
    assert summary["total"] == 0  # tests never count in reporting


# ------------------------------------------------- form-builder parity options

def test_a_conditional_field_is_required_only_when_it_shows(client):
    owner = register(client)
    response = client.post("/api/website-forms", headers=owner["headers"], json={
        "name": "Buy or sell", "preset": "custom",
        "fields": [{"key": "first_name", "required": True}, {"key": "email", "required": True},
                   {"key": "lead_type", "required": True},
                   {"key": "property_address", "required": True,
                    "show_if": {"field": "lead_type", "values": ["Selling", "Buying and selling"]}}]})
    assert response.status_code == 200, response.text
    form = response.json()
    buyer = browser_submit(client, form, lead(lead_type="Buying", property_address="stale answer"))
    assert buyer.status_code == 200
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": buyer.json()["id"]})
    assert "property_address" not in stored["fields"]  # hidden answers are not kept
    seller = browser_submit(client, form, lead(email="seller@example.com", phone="5550400001",
                                               lead_type="Selling", property_address=""))
    assert seller.status_code == 422 and "property_address" in seller.json()["errors"]


def test_conditions_and_steps_must_make_sense(client):
    owner = register(client)
    later = client.post("/api/website-forms", headers=owner["headers"], json={
        "name": "Bad", "preset": "custom",
        "fields": [{"key": "email", "show_if": {"field": "lead_type", "values": ["Selling"]}},
                   {"key": "lead_type"}]})
    assert later.status_code == 422
    gap = client.post("/api/website-forms", headers=owner["headers"], json={
        "name": "Bad", "preset": "custom",
        "fields": [{"key": "email", "step": 1}, {"key": "phone", "step": 3}]})
    assert gap.status_code == 422


def test_a_multi_step_form_tells_the_embed_its_steps(client):
    owner = register(client)
    form = client.post("/api/website-forms", headers=owner["headers"], json={
        "name": "Two steps", "preset": "custom",
        "fields": [{"key": "first_name", "required": True, "step": 1},
                   {"key": "email", "required": True, "step": 1},
                   {"key": "timeline", "step": 2}, {"key": "pre_approved", "step": 2}],
        "settings": {"remember_visitor": True}}).json()
    config = client.get(f"/api/public/forms/{form['public_key']}/config").json()
    assert config["steps"] == 2 and config["remember_visitor"] is True
    assert [f["step"] for f in config["fields"]] == [1, 1, 2, 2]


def test_weighted_round_robin(client):
    owner = register(client)
    alice = add_member(client, owner["tenant_id"])
    bob = add_member(client, owner["tenant_id"])
    form = create_form(client, owner, settings={
        "assignment": {"mode": "round_robin", "users": [alice, bob], "weights": {alice: 2}}})
    owners = []
    for i in range(6):
        response = browser_submit(client, form, lead(email=f"w{i}@example.com", phone=f"555050{i:04d}"))
        owners.append(find_one(client, detectors.WEB_ENQUIRIES, {"id": response.json()["id"]})["assigned_to"])
    assert owners == [alice, alice, bob, alice, alice, bob]


def test_turnstile_captcha_is_enforced_and_its_secret_never_leaves(client, monkeypatch):
    owner = register(client)
    half = client.post("/api/website-forms", headers=owner["headers"], json={
        "name": "Captcha", "preset": "contact",
        "settings": {"captcha": {"provider": "turnstile", "site_key": "0x4AAAAAAAsitekey"}}})
    assert half.status_code == 422  # turning it on needs the secret too
    plain = create_form(client, owner, preset="contact", name="Captcha")
    refused = client.patch(f"/api/website-forms/{plain['id']}", headers=owner["headers"],
                           json={"settings": {"captcha": {"provider": "turnstile",
                                                          "site_key": "0x4AAAAAAAsitekey"}}})
    assert refused.status_code == 422
    saved = client.patch(f"/api/website-forms/{plain['id']}", headers=owner["headers"],
                         json={"settings": {"captcha": {"provider": "turnstile",
                                                        "site_key": "0x4AAAAAAAsitekey",
                                                        "secret": "0x4AAAAAAAsecretkey"}}})
    assert saved.status_code == 200, saved.text
    form = saved.json()
    assert "0x4AAAAAAAsecretkey" not in saved.text and "captcha_secret_enc" not in form
    assert form["settings"]["captcha"]["secret_configured"] is True
    config = client.get(f"/api/public/forms/{form['public_key']}/config").json()
    assert config["captcha"] == {"provider": "turnstile", "site_key": "0x4AAAAAAAsitekey"}

    seen = []

    async def fake_verify(secret, token, ip):
        seen.append(secret)
        return token == "good-token"

    monkeypatch.setattr(server.lead_pipeline, "verify_turnstile", fake_verify)
    assert browser_submit(client, form, lead()).status_code == 422
    assert browser_submit(client, form, lead(**{"cf-turnstile-response": "bad"})).status_code == 422
    ok = browser_submit(client, form, lead(**{"cf-turnstile-response": "good-token"}))
    assert ok.status_code == 200
    assert seen[-1] == "0x4AAAAAAAsecretkey"  # decrypted only to verify


def test_leads_export_as_csv_without_running_formulas(client):
    owner = register(client)
    form = create_form(client, owner)
    browser_submit(client, form, lead(first_name="=HYPERLINK(\"http://x\")", last_name=""))
    response = client.get("/api/leads/export", headers=owner["headers"])
    assert response.status_code == 200 and "text/csv" in response.headers["content-type"]
    lines = response.text.strip().splitlines()
    assert lines[0].startswith("received_at,status,name,email,phone")
    assert "'=HYPERLINK" in response.text and ",=HYPERLINK" not in response.text


# --------------------------------------------- a website's own server forwarding

def server_body(**overrides):
    """Exactly what a website's ClientVerse adapter sends (charlotte-real-estate-system,
    lib/crm/adapter.ts `createClientVerseCrmAdapter`)."""
    body = {"idempotencyKey": f"charlotte-lead-{uuid.uuid4().hex[:6]}",
            "source": "home-value-page", "leadType": "home_value",
            "name": "Mia Seller", "email": "mia.seller@example.com", "phone": "704-555-0142",
            "propertyAddress": "1200 Queens Rd, Charlotte, NC", "message": "What could we list for?",
            "timeframe": "3-6 months", "consultationDate": None, "consultationTime": None,
            "payload": {"propertyType": "Single family", "condition": "Needs minor work"}}
    body.update(overrides)
    return body


def server_post(client, form, body, key):
    return client.post(f"/api/public/forms/{form['public_key']}/submit", json=body,
                       headers={"Authorization": f"Bearer {key}"})


def test_a_website_server_forwards_leads_with_its_key(client):
    owner = register(client)
    form = create_form(client, owner, preset="contact", settings={
        "opportunity": {"value_mode": "commission", "commission_rate": 3, "fixed_value": 7000}})
    minted = client.post(f"/api/website-forms/{form['id']}/server-key", headers=owner["headers"])
    assert minted.status_code == 200 and minted.json()["key"].startswith("cvsk_")
    key = minted.json()["key"]
    listed = client.get(f"/api/website-forms/{form['id']}", headers=owner["headers"]).json()
    assert listed["server_key"]["configured"] is True and key not in str(listed)

    body = server_body()
    response = server_post(client, form, body, key)
    assert response.status_code == 200, response.text
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": response.json()["id"]})
    assert stored["received_via"] == "server"
    assert stored["property_address"] == "1200 Queens Rd, Charlotte, NC"
    assert stored["fields"]["timeline"] == "3-6 months"
    assert stored["fields"]["lead_type"] == "Selling"  # "home_value" mapped, original kept
    assert stored["extra"]["site_leadtype"] == "home_value"
    assert stored["fields"]["property_condition"] == "Needs minor work"  # lifted from payload
    assert stored["extra"]["propertyType"] == "Single family"
    assert stored["extra"]["source"] == "home-value-page"
    assert stored["contact_id"] and stored["task_id"] and stored["opportunity_id"]
    # The website's outbox retries with the same idempotency key: filed once.
    again = server_post(client, form, body, key)
    assert again.json()["id"] == response.json()["id"]


def test_server_leads_skip_browser_rules_but_still_need_a_way_to_reach_them(client, monkeypatch):
    monkeypatch.setattr(wf, "RATE_PER_VISITOR_PER_HOUR", 1)
    owner = register(client)
    form = create_form(client, owner, preset="contact", settings={"allowed_origins": [SITE]})
    key = client.post(f"/api/website-forms/{form['id']}/server-key", headers=owner["headers"]).json()["key"]
    # Every lead comes from the same server address: no per-visitor limit applies.
    codes = [server_post(client, form, server_body(email=f"s{i}@example.com", phone=f"70455501{i:02d}"),
                         key).status_code for i in range(3)]
    assert codes == [200, 200, 200]
    # The visual form requires an email; a phone-only lead the site already accepted is
    # still filed rather than lost over a display setting.
    phone_only = server_post(client, form, server_body(email=None, phone="704-555-0199"), key)
    assert phone_only.status_code == 200
    nothing = server_post(client, form, server_body(email=None, phone=None, message="hi"), key)
    assert nothing.status_code == 422


def test_a_wrong_or_revoked_server_key_is_refused(client):
    owner = register(client)
    form = create_form(client, owner, preset="contact")
    key = client.post(f"/api/website-forms/{form['id']}/server-key", headers=owner["headers"]).json()["key"]
    assert server_post(client, form, server_body(), "cvsk_wrong").status_code == 401
    rotated = client.post(f"/api/website-forms/{form['id']}/server-key", headers=owner["headers"]).json()["key"]
    assert server_post(client, form, server_body(), key).status_code == 401  # old key dead
    assert server_post(client, form, server_body(), rotated).status_code == 200
    client.delete(f"/api/website-forms/{form['id']}/server-key", headers=owner["headers"])
    assert server_post(client, form, server_body(idempotencyKey="x2"), rotated).status_code == 401


def test_a_buyer_guide_price_range_becomes_a_commission_value(client):
    owner = register(client)
    form = create_form(client, owner, preset="contact", settings={
        "opportunity": {"value_mode": "commission", "commission_rate": 2.5, "fixed_value": 5000}})
    key = client.post(f"/api/website-forms/{form['id']}/server-key", headers=owner["headers"]).json()["key"]
    body = server_body(leadType="buyer", source="buyer-guide", propertyAddress=None,
                       payload={"kind": "buyer_guide", "priceRange": "$400k\u2013$500k",
                                "preapproval": "Yes", "firstName": "Ben", "lastName": "Buyer"})
    stored = find_one(client, detectors.WEB_ENQUIRIES,
                      {"id": server_post(client, form, body, key).json()["id"]})
    assert stored["fields"]["price_min"] == 400000.0 and stored["fields"]["price_max"] == 500000.0
    assert stored["fields"]["pre_approved"] == "Yes" and stored["fields"]["lead_type"] == "Buying"
    assert stored["estimated_value"] == 12500.0  # 2.5% of the top of the range


def test_one_intake_address_for_every_website_server(client):
    owner = register(client)
    form = create_form(client, owner, preset="contact")
    minted = client.post(f"/api/website-forms/{form['id']}/server-key", headers=owner["headers"]).json()
    assert minted["intake_url"].endswith("/api/intake/leads")
    response = client.post("/api/intake/leads", json=server_body(),
                           headers={"Authorization": f"Bearer {minted['key']}"})
    assert response.status_code == 200, response.text
    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": response.json()["id"]})
    assert stored["form_id"] == form["id"] and stored["tenant_id"] == owner["tenant_id"]
    assert client.post("/api/intake/leads", json=server_body()).status_code == 401
    assert client.post("/api/intake/leads", json=server_body(),
                       headers={"Authorization": "Bearer cvsk_nope"}).status_code == 401
    client.patch(f"/api/website-forms/{form['id']}", headers=owner["headers"], json={"status": "paused"})
    assert client.post("/api/intake/leads", json=server_body(idempotencyKey="p1"),
                       headers={"Authorization": f"Bearer {minted['key']}"}).status_code == 401
