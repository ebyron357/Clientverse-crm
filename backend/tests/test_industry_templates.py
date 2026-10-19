"""Industry templates: a starting setup per trade that only ever adds what is missing.

Each test applies templates through the API and reads back what exists, including a lead
sent through the template's own form by the public door, so the setup is shown to work,
not just to be stored.
"""

import json
import os
import sys
import uuid
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ["LEAD_SLA_WATCHER"] = "0"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_templates_unit")
os.environ.setdefault("JWT_SECRET", "templates-unit-jwt-secret-long-enough-123456789")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "admin@templates.example")
os.environ.setdefault("ADMIN_PASSWORD", "Templates-Admin-Passw0rd-1!")

from fastapi.testclient import TestClient

import detectors
import server

SITE = "https://www.example-trade.example"


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


def apply(client, owner, key):
    response = client.post(f"/api/industry-templates/{key}/apply", headers=owner["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def actions(result):
    return {(item["kind"], item["name"]): item["action"] for item in result["items"]}


def setup(client, owner):
    tenant = owner["tenant_id"]
    return {
        "stages": [s["key"] for s in client.get("/api/pipelines/default", headers=owner["headers"]).json()["stages"]],
        "fields": sorted((f["object"], f["label"]) for f in find_all(client, "custom_field_defs", {"tenant_id": tenant})),
        "pages": sorted(p["name"] for p in find_all(client, "booking_event_types", {"tenant_id": tenant})),
        "forms": sorted(f["name"] for f in find_all(client, "website_forms", {"tenant_id": tenant})),
        "automations": sorted((a["name"], a["status"]) for a in find_all(client, "automations", {"tenant_id": tenant})),
    }


# ----------------------------------------------------------------------------- tests

def test_six_templates_are_offered_and_none_is_in_use_at_first(client):
    owner = register(client)
    body = client.get("/api/industry-templates", headers=owner["headers"]).json()
    assert [t["key"] for t in body["items"]] == ["agency", "real_estate", "home_services", "health_wellness", "coaching", "b2b_sales"]
    assert body["in_use"] is None
    home = next(t for t in body["items"] if t["key"] == "home_services")
    assert home["stages"] == ["New request", "Estimate booked", "Estimate sent", "Job booked", "Done"]
    assert home["booking_pages"] == ["On-site estimate", "Service call"]
    assert "Job type" in home["form_asks"] and "Service address" in home["form_asks"]


def test_a_preview_lists_the_plan_and_changes_nothing(client):
    owner = register(client)
    before = setup(client, owner)
    response = client.get("/api/industry-templates/agency/preview", headers=owner["headers"])
    assert response.status_code == 200, response.text
    plan = actions(response.json())
    assert plan[("pipeline", "Pipeline stages")] == "add"
    assert plan[("booking_page", "Discovery call")] == "add"
    assert plan[("form", "Contact us")] == "add"
    assert plan[("automation", "New lead: call within 5 minutes")] == "add"
    assert response.json()["applied"] is False
    assert setup(client, owner) == before


def test_applying_sets_up_the_business_and_applying_again_adds_nothing(client):
    owner = register(client)
    result = apply(client, owner, "agency")
    assert all(item["action"] == "add" for item in result["items"])
    state = setup(client, owner)
    assert state["stages"] == ["lead", "qualified", "proposal", "negotiation", "won", "lost"]
    assert state["fields"] == [("contacts", "Budget"), ("contacts", "Service"), ("deals", "Contract length")]
    assert state["pages"] == ["Client check-in", "Discovery call", "Strategy session"]
    assert state["forms"] == ["Contact us"]
    # Automations arrive as drafts: nothing runs until a person turns it on.
    assert {status for _, status in state["automations"]} == {"draft"}
    assert len(state["automations"]) == 3
    assert client.get("/api/industry-templates", headers=owner["headers"]).json()["in_use"] == "agency"
    again = apply(client, owner, "agency")
    assert all(item["action"] == "keep" for item in again["items"])
    assert setup(client, owner) == state


def test_switching_adds_what_is_missing_and_keeps_everything_already_there(client):
    owner = register(client)
    apply(client, owner, "agency")
    before = setup(client, owner)
    result = actions(apply(client, owner, "coaching"))
    # The pipeline is already set, so it stays; shared names are not duplicated.
    assert result[("pipeline", "Pipeline stages")] == "keep"
    assert result[("booking_page", "Discovery call")] == "keep"
    assert result[("field", "Budget (contact)")] == "keep"
    assert result[("automation", "New lead: call within 5 minutes")] == "keep"
    assert result[("booking_page", "Coaching session")] == "add"
    after = setup(client, owner)
    assert after["stages"] == before["stages"]
    assert set(before["pages"]) < set(after["pages"]) and "Coaching session" in after["pages"]
    assert ("contacts", "Goal") in after["fields"] and after["fields"].count(("contacts", "Budget")) == 1
    assert client.get("/api/industry-templates", headers=owner["headers"]).json()["in_use"] == "coaching"


def test_the_pipeline_is_kept_when_deals_already_use_its_stages(client):
    owner = register(client)
    client.post("/api/opportunities", headers=owner["headers"], json={"name": "Existing", "value": 100})
    result = actions(apply(client, owner, "real_estate"))
    assert result[("pipeline", "Pipeline stages")] == "keep"
    assert setup(client, owner)["stages"] == ["lead", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]


def test_the_template_form_takes_a_real_lead_into_the_template_pipeline(client):
    owner = register(client)
    apply(client, owner, "home_services")
    [form] = find_all(client, "website_forms", {"tenant_id": owner["tenant_id"]})
    assert form["settings"]["auto_reply"]["enabled"] is False
    payload = {"first_name": "Ray", "last_name": "Diaz", "email": "ray@example.com", "phone": "555-301-4400",
               "custom_service_address": "12 Oak St", "custom_job_type": "Repair", "message": "Leaking pipe.",
               "_sid": uuid.uuid4().hex, "_elapsed_ms": 9000}
    response = client.post(f"/api/public/forms/{form['public_key']}/submit", content=json.dumps(payload),
                           headers={"Content-Type": "text/plain;charset=UTF-8", "Origin": SITE})
    assert response.status_code == 200, response.text
    lead = call(client, server.db[detectors.WEB_ENQUIRIES].find_one, {"id": response.json()["id"]}, {"_id": 0})
    assert lead["fields"]["custom_job_type"] == "Repair"
    deal = call(client, server.db.opportunities.find_one, {"id": lead["opportunity_id"]}, {"_id": 0})
    assert deal["stage"] == "new_request"
    pages = find_all(client, "booking_event_types", {"tenant_id": owner["tenant_id"]})
    assert {p["name"]: p["duration_minutes"] for p in pages} == {"On-site estimate": 60, "Service call": 60}


def test_only_an_admin_applies_and_templates_stay_inside_their_tenant(client):
    owner = register(client)
    member = add_member(client, owner)
    stranger = register(client)
    assert client.get("/api/industry-templates/agency/preview", headers=member["headers"]).status_code == 200
    assert client.post("/api/industry-templates/agency/apply", headers=member["headers"]).status_code == 403
    assert client.post("/api/industry-templates/nonsense/apply", headers=owner["headers"]).status_code == 404
    apply(client, owner, "b2b_sales")
    untouched = setup(client, stranger)
    assert untouched["fields"] == [] and untouched["pages"] == [] and untouched["forms"] == [] and untouched["automations"] == []
    assert client.get("/api/industry-templates", headers=stranger["headers"]).json()["in_use"] is None


def test_archived_pages_and_forms_come_back_and_an_archived_field_is_restored_not_copied(client):
    owner = register(client)
    apply(client, owner, "coaching")
    tenant = owner["tenant_id"]
    call(client, server.db.booking_event_types.update_one, {"tenant_id": tenant, "name": "Coaching session"},
         {"$set": {"status": "archived"}})
    call(client, server.db.website_forms.update_one, {"tenant_id": tenant, "name": "Apply for coaching"},
         {"$set": {"status": "archived"}})
    call(client, server.db.custom_field_defs.update_one, {"tenant_id": tenant, "label": "Goal"},
         {"$set": {"archived_at": server.now_iso()}})
    plan = client.get("/api/industry-templates/coaching/preview", headers=owner["headers"]).json()["items"]
    detail = {(i["kind"], i["name"]): (i["action"], i["detail"]) for i in plan}
    assert detail[("booking_page", "Coaching session")][0] == "add"
    assert detail[("form", "Apply for coaching")][0] == "add"
    assert detail[("field", "Goal (contact)")] == ("keep", "Archived; restore it in Settings → Fields")
    apply(client, owner, "coaching")
    assert len([f for f in find_all(client, "custom_field_defs", {"tenant_id": tenant}) if f["label"] == "Goal"]) == 1
    live = find_all(client, "booking_event_types", {"tenant_id": tenant, "name": "Coaching session", "status": {"$ne": "archived"}})
    assert len(live) == 1


def test_a_template_pipelines_won_and_lost_deals_are_not_counted_as_open(client):
    owner = register(client)
    apply(client, owner, "home_services")
    company = client.post("/api/companies", headers=owner["headers"], json={"name": "Oak Street Homes"}).json()
    for name, stage, value in [("Kitchen", "job_booked", 900), ("Roof", "won", 5000), ("Fence", "lost", 300)]:
        response = client.post("/api/opportunities", headers=owner["headers"],
                               json={"name": name, "value": value, "stage": stage, "company_id": company["id"]})
        assert response.status_code == 200, response.text
    commercial = client.get(f"/api/companies/{company['id']}", headers=owner["headers"]).json()["commercial"]
    assert commercial == {"open_deal_count": 1, "open_pipeline_value": 900.0, "won_deal_count": 1, "closed_won_value": 5000.0}
    funnel = client.get("/api/dashboard", headers=owner["headers"]).json()["funnel"]
    assert list(funnel) == ["new_request", "estimate_booked", "estimate_sent", "job_booked", "won", "lost"]
    assert funnel["won"] == 1 and funnel["lost"] == 1


def test_a_deal_created_without_a_stage_starts_in_the_template_pipelines_first_stage(client):
    owner = register(client)
    apply(client, owner, "health_wellness")
    response = client.post("/api/opportunities", headers=owner["headers"], json={"name": "Annual plan", "value": 600})
    assert response.status_code == 200, response.text
    assert response.json()["stage"] == "inquiry"
    assert client.post("/api/opportunities", headers=owner["headers"],
                       json={"name": "Old stage", "stage": "lead"}).status_code == 422
