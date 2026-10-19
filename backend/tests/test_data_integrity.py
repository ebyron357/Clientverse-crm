"""One record per real thing: one deal per person, companies that exist, no twins.

Loading real data through the public form and booking doors showed three ways the CRM
multiplied records. A form fill followed by a booking opened two deals for one person.
An existing client booking a check-in became a new lead with a new $0 deal. A company
typed into a form stayed a loose text field, so the company list never filled. These
tests go in through the same doors and read back what the CRM did, and they cover the
tools that tidy what is already there: clean-up suggestions and merging two contacts.

Runs in-process against the real `app`, like the website-forms and booking tests.
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
os.environ.setdefault("DB_NAME", "clientverse_data_integrity_unit")
os.environ.setdefault("JWT_SECRET", "data-integrity-unit-jwt-secret-long-enough-123")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "admin@data-integrity.example")
os.environ.setdefault("ADMIN_PASSWORD", "Data-Integrity-Admin-1!")

from fastapi.testclient import TestClient

import booking
import detectors
import server

SITE = "https://www.example-agency.example"
UTC = timezone.utc
ALWAYS = {d: [{"start": "00:00", "end": "24:00"}] for d in booking.WEEKDAYS}


@pytest.fixture(scope="module")
def client():
    registered = server.lead_pipeline.db
    server.db = registered
    server.mclient = getattr(registered, "client", server.mclient)
    with TestClient(server.app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _no_providers():
    server.lead_pipeline.registry = None
    server.booking_service.registry = None
    yield
    server.lead_pipeline.registry = None
    server.booking_service.registry = None


def call(client, fn, *args, **kwargs):
    async def _run():
        return await fn(*args, **kwargs)
    return client.portal.call(_run)


def find_one(client, collection, query):
    return call(client, server.db[collection].find_one, query, {"_id": 0})


def find_all(client, collection, query):
    async def _run():
        return await server.db[collection].find(query, {"_id": 0}).to_list(1000)
    return client.portal.call(_run)


def register(client):
    email = f"owner-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post("/api/auth/register",
                           json={"email": email, "password": "Str0ng-Passw0rd!", "name": "Taylor Owner"})
    assert response.status_code == 200, response.text
    client.cookies.clear()
    body = response.json()
    return {"email": email, "tenant_id": body["user"]["tenant_id"],
            "headers": {"Authorization": f"Bearer {body['token']}"}}


def contact_form(client, owner, **settings):
    fields = [{"key": "first_name", "required": True}, {"key": "last_name", "required": True},
              {"key": "email", "required": True}, {"key": "phone"}, {"key": "company"},
              {"key": "message"}]
    response = client.post("/api/website-forms", headers=owner["headers"],
                           json={"name": "Contact us", "preset": "custom", "fields": fields,
                                 "settings": settings})
    assert response.status_code == 200, response.text
    return response.json()


def submit(client, form, **data):
    payload = {"first_name": "Jordan", "last_name": "Lee", "email": "jordan@brightline.example",
               "phone": "555-410-2201", "company": "Brightline Dental",
               "message": "We need a new website and local SEO.", "_sid": uuid.uuid4().hex,
               "_elapsed_ms": 9000, **data}
    response = client.post(f"/api/public/forms/{form['public_key']}/submit",
                           content=json.dumps(payload),
                           headers={"Content-Type": "text/plain;charset=UTF-8", "Origin": SITE})
    assert response.status_code == 200, response.text
    return find_one(client, detectors.WEB_ENQUIRIES, {"id": response.json()["id"]})


def booking_page(client, owner, **body):
    response = client.put(f"/api/booking/availability/{owner['email']}", headers=owner["headers"],
                          json={"timezone": "UTC", "weekly": ALWAYS, "overrides": []})
    assert response.status_code == 200, response.text
    payload = {"name": "Discovery call", "min_notice_hours": 0, "buffer_before_minutes": 0,
               "buffer_after_minutes": 0, **body}
    response = client.post("/api/booking/event-types", headers=owner["headers"], json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def book(client, page, **person):
    first = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
    response = client.get(f"/api/public/booking/{page['public_key']}/slots",
                          params={"start": first, "end": first, "tz": "UTC"}, headers={"Origin": SITE})
    assert response.status_code == 200, response.text
    start = [s for d in response.json()["days"] for s in d["slots"]][0]
    payload = {"start": start, "timezone": "UTC", "first_name": "Jordan", "last_name": "Lee",
               "email": "jordan@brightline.example", "phone": "555-410-2201",
               "_sid": uuid.uuid4().hex, "_elapsed_ms": 8000, **person}
    response = client.post(f"/api/public/booking/{page['public_key']}/book", content=json.dumps(payload),
                           headers={"Content-Type": "text/plain;charset=UTF-8", "Origin": SITE})
    assert response.status_code == 200, response.text
    return find_one(client, "appointments", {"tenant_id": page["tenant_id"], "start_at": start})


# ------------------------------------------------------------- one deal per person

def test_a_form_fill_then_a_booking_is_one_deal_not_two(client):
    owner = register(client)
    form = contact_form(client, owner)
    page = booking_page(client, owner)
    lead = submit(client, form)
    appointment = book(client, page)
    deals = find_all(client, "opportunities", {"tenant_id": owner["tenant_id"]})
    assert len(deals) == 1
    assert appointment["opportunity_id"] == lead["opportunity_id"] == deals[0]["id"]
    later = find_one(client, detectors.WEB_ENQUIRIES, {"id": appointment["enquiry_id"]})
    assert any(step["step"] == "opportunity" and step["result"] == "linked" for step in later["automation"])


def test_a_form_may_keep_each_submission_as_its_own_deal(client):
    owner = register(client)
    first = contact_form(client, owner)
    second = contact_form(client, owner, opportunity={"reuse_open_deal": False})
    submit(client, first)
    submit(client, second)
    assert len(find_all(client, "opportunities", {"tenant_id": owner["tenant_id"]})) == 2


def test_an_opted_out_form_keeps_every_submission_as_its_own_deal(client):
    owner = register(client)
    form = contact_form(client, owner, opportunity={"reuse_open_deal": False})
    first = submit(client, form, message="First project.")
    second = submit(client, form, message="A separate second project.")
    assert first["opportunity_id"] != second["opportunity_id"]
    assert len(find_all(client, "opportunities", {"tenant_id": owner["tenant_id"]})) == 2


def test_a_reused_deal_keeps_its_currency_and_gains_a_company_named_later(client):
    owner = register(client)
    euro = contact_form(client, owner, opportunity={"currency": "EUR"})
    dollar = contact_form(client, owner, opportunity={"currency": "USD"})
    first = submit(client, euro, company="")
    deal = find_one(client, "opportunities", {"id": first["opportunity_id"]})
    assert deal["currency"] == "EUR" and deal["company_id"] is None
    later = submit(client, dollar, company="Brightline Dental")
    assert later["opportunity_id"] == deal["id"]
    # The enquiry reports the deal it joined in that deal's currency, not the second form's.
    assert later["currency"] == "EUR"
    reused = find_one(client, "opportunities", {"id": deal["id"]})
    contact = find_one(client, "contacts", {"id": later["contact_id"]})
    assert contact["company_id"] and reused["company_id"] == contact["company_id"]


def test_everyone_who_ends_up_on_a_won_deal_becomes_a_customer(client):
    owner = register(client)
    headers = owner["headers"]
    ana = client.post("/api/contacts", headers=headers, json={"name": "Ana", "lifecycle": "lead"}).json()
    ben = client.post("/api/contacts", headers=headers, json={"name": "Ben", "lifecycle": "qualified"}).json()
    pat = client.post("/api/contacts", headers=headers, json={"name": "Pat", "lifecycle": "partner"}).json()
    won = client.post("/api/opportunities", headers=headers,
                      json={"name": "Signed already", "value": 10, "stage": "closed_won", "contact_ids": [ana["id"]]})
    assert won.status_code == 200, won.text
    assert find_one(client, "contacts", {"id": ana["id"]})["lifecycle"] == "customer"
    response = client.patch(f"/api/opportunities/{won.json()['id']}", headers=headers,
                            json={"contact_ids": [ana["id"], ben["id"], pat["id"]]})
    assert response.status_code == 200, response.text
    assert find_one(client, "contacts", {"id": ben["id"]})["lifecycle"] == "customer"
    assert find_one(client, "contacts", {"id": pat["id"]})["lifecycle"] == "partner"
    # An open deal does not make anyone a customer.
    carl = client.post("/api/contacts", headers=headers, json={"name": "Carl", "lifecycle": "lead"}).json()
    client.post("/api/opportunities", headers=headers, json={"name": "Open", "value": 1, "contact_ids": [carl["id"]]})
    assert find_one(client, "contacts", {"id": carl["id"]})["lifecycle"] == "lead"


def test_the_reuse_setting_must_be_true_or_false(client):
    owner = register(client)
    response = client.post("/api/website-forms", headers=owner["headers"],
                           json={"name": "Bad", "preset": "contact",
                                 "settings": {"opportunity": {"reuse_open_deal": "sometimes"}}})
    assert response.status_code == 422


def test_an_existing_client_booking_a_check_in_opens_no_lead_deal(client):
    owner = register(client)
    company = client.post("/api/companies", headers=owner["headers"],
                          json={"name": "Northwind Analytics"}).json()
    contact = client.post("/api/contacts", headers=owner["headers"],
                          json={"name": "Dana Reyes", "email": "dana@northwind.example",
                                "company_id": company["id"]}).json()
    call(client, server.db.workspaces.insert_one,
         {"id": f"ws_{uuid.uuid4().hex[:8]}", "tenant_id": owner["tenant_id"], "name": "Northwind Delivery",
          "company_id": company["id"], "created_at": server.now_iso()})
    page = booking_page(client, owner, name="Client check-in")
    appointment = book(client, page, first_name="Dana", last_name="Reyes", email="dana@northwind.example")
    assert appointment["contact_id"] == contact["id"]
    assert appointment["opportunity_id"] is None
    assert find_all(client, "opportunities", {"tenant_id": owner["tenant_id"]}) == []
    enquiry = find_one(client, detectors.WEB_ENQUIRIES, {"id": appointment["enquiry_id"]})
    assert enquiry["existing_client"] is True
    assert any(s["step"] == "opportunity" and s["result"] == "skipped" for s in enquiry["automation"])


def test_a_won_customer_writing_in_gets_a_client_reply_task(client):
    owner = register(client)
    contact = client.post("/api/contacts", headers=owner["headers"],
                          json={"name": "Jordan Lee", "email": "jordan@brightline.example"}).json()
    deal = client.post("/api/opportunities", headers=owner["headers"],
                       json={"name": "Brightline website", "value": 18000, "stage": "closed_won",
                             "contact_ids": [contact["id"]]})
    assert deal.status_code == 200, deal.text
    lead = submit(client, contact_form(client, owner), message="Can we add a fourth clinic?")
    assert lead["existing_client"] is True and lead["opportunity_id"] is None
    task = find_one(client, "tasks", {"id": lead["task_id"]})
    assert task["title"].startswith("Reply to client: Jordan Lee")


# ------------------------------------------------------------------- companies

def test_a_company_typed_into_a_form_becomes_a_linked_company(client):
    owner = register(client)
    form = contact_form(client, owner)
    lead = submit(client, form)
    company = find_one(client, "companies", {"tenant_id": owner["tenant_id"]})
    assert company["name"] == "Brightline Dental" and company["domain"] == "brightline.example"
    contact = find_one(client, "contacts", {"id": lead["contact_id"]})
    assert contact["company_id"] == company["id"] and "company" not in (contact.get("custom_fields") or {})
    assert find_one(client, "opportunities", {"id": lead["opportunity_id"]})["company_id"] == company["id"]
    assert lead["company_id"] == company["id"]
    # A colleague from the same company joins it, by name or by work email domain.
    colleague = submit(client, form, first_name="Sam", email="sam@brightline.example", company="")
    assert find_one(client, "contacts", {"id": colleague["contact_id"]})["company_id"] == company["id"]
    assert len(find_all(client, "companies", {"tenant_id": owner["tenant_id"]})) == 1


def test_a_personal_email_never_names_or_joins_a_company(client):
    owner = register(client)
    client.post("/api/companies", headers=owner["headers"], json={"name": "Gmail", "domain": "gmail.com"})
    lead = submit(client, contact_form(client, owner), email="pat.person@gmail.com", company="")
    contact = find_one(client, "contacts", {"id": lead["contact_id"]})
    assert contact.get("company_id") is None


def test_company_is_a_question_a_booking_page_can_ask(client):
    owner = register(client)
    page = booking_page(client, owner, questions=[{"key": "phone"}, {"key": "company"}])
    appointment = book(client, page, email="lena@fischerlegal.example", first_name="Lena",
                       last_name="Fischer", company="Fischer Legal")
    contact = find_one(client, "contacts", {"id": appointment["contact_id"]})
    company = find_one(client, "companies", {"id": contact["company_id"]})
    assert company["name"] == "Fischer Legal"


# ------------------------------------------------------------- neutral booking

def test_a_new_booking_page_is_a_neutral_meeting_not_a_home_showing(client):
    owner = register(client)
    page = booking_page(client, owner)
    assert page["preset"] == "meeting"
    stored = find_one(client, booking.EVENT_TYPES, {"id": page["id"]})
    assert stored["opportunity"]["value_mode"] == "fixed"
    appointment = book(client, page, first_name="Ben", last_name="Carter", email="ben@carter.example")
    task = find_one(client, "tasks", {"source.appointment_id": appointment["id"]})
    assert task["title"] == "Prepare for the discovery call with Ben Carter"
    assert "showing" not in task["title"].lower() and "property" not in task["title"].lower()
    catalog = client.get("/api/booking/catalog", headers=owner["headers"]).json()
    assert catalog["presets"][0]["key"] == "meeting"
    assert "company" in [q["key"] for q in catalog["questions"]]


def test_real_estate_pages_still_value_deals_at_commission(client):
    owner = register(client)
    page = booking_page(client, owner, preset="home_showing", name="Home showing")
    assert find_one(client, booking.EVENT_TYPES, {"id": page["id"]})["opportunity"]["value_mode"] == "commission"


# --------------------------------------------------------------- clean-up

def test_clean_up_finds_typed_companies_domain_matches_and_twins(client):
    owner = register(client)
    headers = owner["headers"]
    harbor = client.post("/api/companies", headers=headers,
                         json={"name": "Harbor Logistics", "website": "https://www.harborlogistics.example"}).json()
    olivia = client.post("/api/contacts", headers=headers,
                         json={"name": "Olivia Bennett", "email": "olivia@harborlogistics.example"}).json()
    marcus_a = client.post("/api/contacts", headers=headers,
                           json={"name": "Marcus Lee", "email": "marcus@harbor.example"}).json()
    marcus_b = client.post("/api/contacts", headers=headers,
                           json={"name": "Marcus  Lee", "email": "marcus.lee@example.com"}).json()
    typed = client.post("/api/contacts", headers=headers, json={"name": "Amara Osei"}).json()
    call(client, server.db.contacts.update_one, {"id": typed["id"]},
         {"$set": {"custom_fields.custom_company": "Osei Fitness"}})

    scan = client.get("/api/contacts/cleanup", headers=headers)
    assert scan.status_code == 200, scan.text
    body = scan.json()
    assert [g["name"] for g in body["typed_companies"]] == ["Osei Fitness"]
    assert body["domain_matches"] == [{"contact_id": olivia["id"], "contact_name": "Olivia Bennett",
                                       "company_id": harbor["id"], "company_name": "Harbor Logistics",
                                       "domain": "harborlogistics.example"}]
    twins = [g for g in body["duplicates"] if g["reason"] == "same name"]
    assert {c["id"] for c in twins[0]["contacts"]} == {marcus_a["id"], marcus_b["id"]}

    linked = client.post("/api/contacts/cleanup/apply", headers=headers, json={"action": "link_by_domain"})
    assert linked.json()["linked"] == 1
    assert find_one(client, "contacts", {"id": olivia["id"]})["company_id"] == harbor["id"]
    created = client.post("/api/contacts/cleanup/apply", headers=headers,
                          json={"action": "create_typed_companies"}).json()
    assert created == {"action": "create_typed_companies", "linked": 1, "created_companies": 1}
    osei = find_one(client, "companies", {"tenant_id": owner["tenant_id"], "name": "Osei Fitness"})
    assert find_one(client, "contacts", {"id": typed["id"]})["company_id"] == osei["id"]
    after = client.get("/api/contacts/cleanup", headers=headers).json()
    assert after["typed_companies"] == [] and after["domain_matches"] == []


def test_clean_up_refuses_an_unknown_action(client):
    owner = register(client)
    response = client.post("/api/contacts/cleanup/apply", headers=owner["headers"], json={"action": "delete_all"})
    assert response.status_code == 422


# --------------------------------------------------------------------- merge

def test_merging_moves_everything_to_the_kept_contact(client):
    owner = register(client)
    headers = owner["headers"]
    form = contact_form(client, owner)
    lead = submit(client, form, email="marcus.lee@example.com", first_name="Marcus", last_name="Lee",
                  company="", phone="555-777-0101")
    duplicate_id = lead["contact_id"]
    kept = client.post("/api/contacts", headers=headers,
                       json={"name": "Marcus Lee", "email": "marcus@harbor.example"}).json()
    note = client.post("/api/activities", headers=headers,
                       json={"type": "note", "related_type": "contact", "related_id": duplicate_id,
                             "subject": "Prefers mornings"})
    assert note.status_code == 200, note.text

    response = client.post(f"/api/contacts/{duplicate_id}/merge", headers=headers,
                           json={"into_id": kept["id"]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["contact"]["phone"] == "555-777-0101"  # filled from the duplicate
    assert body["contact"]["email"] == "marcus@harbor.example"  # the kept value wins
    assert find_one(client, "opportunities", {"id": lead["opportunity_id"]})["contact_ids"] == [kept["id"]]
    assert find_one(client, "tasks", {"id": lead["task_id"]})["related_id"] == kept["id"]
    assert find_one(client, detectors.WEB_ENQUIRIES, {"id": lead["id"]})["contact_id"] == kept["id"]
    assert find_one(client, "crm_activities", {"id": note.json()["id"]})["related_id"] == kept["id"]
    gone = find_one(client, "contacts", {"id": duplicate_id})
    assert gone["archived_at"] and gone["merged_into"] == kept["id"]
    timeline = client.get(f"/api/contacts/{kept['id']}", headers=headers).json()
    assert len(timeline["deals"]) == 1 and len(timeline["tasks"]) == 1
    events = {e["event_type"] for e in find_all(client, "domain_events", {"tenant_id": owner["tenant_id"]})}
    assert "contact.merged" in events


def test_a_contact_cannot_merge_into_itself_or_into_another_tenant(client):
    owner = register(client)
    stranger = register(client)
    mine = client.post("/api/contacts", headers=owner["headers"], json={"name": "Mine"}).json()
    theirs = client.post("/api/contacts", headers=stranger["headers"], json={"name": "Theirs"}).json()
    assert client.post(f"/api/contacts/{mine['id']}/merge", headers=owner["headers"],
                       json={"into_id": mine["id"]}).status_code == 422
    assert client.post(f"/api/contacts/{mine['id']}/merge", headers=owner["headers"],
                       json={"into_id": theirs["id"]}).status_code == 404
    assert client.post(f"/api/contacts/{theirs['id']}/merge", headers=owner["headers"],
                       json={"into_id": mine["id"]}).status_code == 404
    assert find_one(client, "contacts", {"id": theirs["id"]}).get("archived_at") is None


def test_an_interrupted_merge_finishes_when_run_again(client):
    owner = register(client)
    headers = owner["headers"]
    lead = submit(client, contact_form(client, owner), email="twin@example.com", company="")
    duplicate_id = lead["contact_id"]
    kept = client.post("/api/contacts", headers=headers, json={"name": "Twin", "email": "twin@work.example"}).json()
    # As if a first attempt stopped after recording where it was going.
    call(client, server.db.contacts.update_one, {"id": duplicate_id}, {"$set": {"merged_into": kept["id"]}})
    response = client.post(f"/api/contacts/{duplicate_id}/merge", headers=headers, json={"into_id": kept["id"]})
    assert response.status_code == 200, response.text
    assert find_one(client, "opportunities", {"id": lead["opportunity_id"]})["contact_ids"] == [kept["id"]]
    assert find_one(client, "contacts", {"id": duplicate_id})["archived_at"]
    again = client.post(f"/api/contacts/{duplicate_id}/merge", headers=headers, json={"into_id": kept["id"]})
    assert again.status_code == 200
    history = find_one(client, "contacts", {"id": kept["id"]})["history"]
    assert sum(1 for h in history if h.get("action") == "merged") == 0  # the repeat added none
    other = client.post("/api/contacts", headers=headers, json={"name": "Someone else"}).json()
    assert client.post(f"/api/contacts/{duplicate_id}/merge", headers=headers,
                       json={"into_id": other["id"]}).status_code == 422
