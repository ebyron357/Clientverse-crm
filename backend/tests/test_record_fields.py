"""Custom fields, lifecycle stages and saved views, through the HTTP API.

An admin adds fields to contacts, companies and deals; anyone sets their values, which
are checked against the field's type; people save the lists they keep coming back to,
for themselves or the team. Each test reads back what was stored, and the tenant and
role boundaries are tested the way an outsider would probe them.
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
os.environ.setdefault("DB_NAME", "clientverse_record_fields_unit")
os.environ.setdefault("JWT_SECRET", "record-fields-unit-jwt-secret-long-enough-1234")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "admin@record-fields.example")
os.environ.setdefault("ADMIN_PASSWORD", "Record-Fields-Admin-1!")

from fastapi.testclient import TestClient

import detectors
import server


@pytest.fixture(scope="module")
def client():
    registered = server.lead_pipeline.db
    server.db = registered
    server.mclient = getattr(registered, "client", server.mclient)
    with TestClient(server.app) as test_client:
        yield test_client


def call(client, fn, *args, **kwargs):
    async def _run():
        return await fn(*args, **kwargs)
    return client.portal.call(_run)


def find_one(client, collection, query):
    return call(client, server.db[collection].find_one, query, {"_id": 0})


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


def field(client, owner, **body):
    response = client.post("/api/custom-fields", headers=owner["headers"], json={"object": "contacts", **body})
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------------ definitions

def test_an_admin_adds_typed_fields_with_stable_keys(client):
    owner = register(client)
    budget = field(client, owner, label="Budget", type="number")
    assert budget["key"] == "cf_budget" and budget["type"] == "number" and budget["archived_at"] is None
    again = field(client, owner, label="Budget", type="number")
    assert again["key"] == "cf_budget_2"
    plan = field(client, owner, label="Plan", type="select", options=["Starter", "Growth", "Starter", " "])
    assert plan["options"] == ["Starter", "Growth"]
    listed = client.get("/api/custom-fields", params={"object": "contacts"}, headers=owner["headers"]).json()
    assert [f["key"] for f in listed["items"]] == ["cf_budget", "cf_budget_2", "cf_plan"]
    assert "select" in listed["types"]


def test_a_choice_needs_options_and_bad_input_is_named(client):
    owner = register(client)
    response = client.post("/api/custom-fields", headers=owner["headers"],
                           json={"object": "contacts", "label": "Plan", "type": "select", "options": []})
    assert response.status_code == 422
    assert client.post("/api/custom-fields", headers=owner["headers"],
                       json={"object": "invoices", "label": "X", "type": "text"}).status_code == 422
    assert client.post("/api/custom-fields", headers=owner["headers"],
                       json={"object": "contacts", "label": "X", "type": "formula"}).status_code == 422


def test_only_an_admin_defines_fields(client):
    owner = register(client)
    member = add_member(client, owner)
    response = client.post("/api/custom-fields", headers=member["headers"],
                           json={"object": "contacts", "label": "Budget", "type": "number"})
    assert response.status_code == 403
    assert client.get("/api/custom-fields", headers=member["headers"]).status_code == 200


# ----------------------------------------------------------------------- values

def test_values_are_checked_against_their_field_and_stored_by_key(client):
    owner = register(client)
    headers = owner["headers"]
    field(client, owner, label="Budget", type="number")
    field(client, owner, label="Plan", type="select", options=["Starter", "Growth"])
    field(client, owner, label="Renewal date", type="date")
    field(client, owner, label="VIP", type="checkbox")
    field(client, owner, label="Website", type="url")
    contact = client.post("/api/contacts", headers=headers, json={"name": "Jordan Lee"}).json()

    ok = client.patch(f"/api/contacts/{contact['id']}", headers=headers,
                      json={"custom_fields": {"cf_budget": "18000", "cf_plan": "Growth",
                                              "cf_renewal_date": "2027-01-15T00:00:00Z", "cf_vip": True,
                                              "cf_website": "https://brightline.example"}})
    assert ok.status_code == 200, ok.text
    stored = ok.json()["custom_fields"]
    assert stored == {"cf_budget": 18000.0, "cf_plan": "Growth", "cf_renewal_date": "2027-01-15",
                      "cf_vip": True, "cf_website": "https://brightline.example"}
    for bad in ({"cf_budget": "lots"}, {"cf_plan": "Enterprise"}, {"cf_renewal_date": "soon"},
                {"cf_vip": "yes"}, {"cf_website": "brightline"}, {"cf_unknown": "x"}):
        response = client.patch(f"/api/contacts/{contact['id']}", headers=headers, json={"custom_fields": bad})
        assert response.status_code == 422, bad
    # A refused patch changes nothing.
    assert find_one(client, "contacts", {"id": contact["id"]})["custom_fields"]["cf_plan"] == "Growth"
    history = find_one(client, "contacts", {"id": contact["id"]})["history"]
    assert any("custom_fields.cf_budget" in (h.get("detail") or {}).get("changed", []) for h in history)


def test_setting_a_field_keeps_what_a_website_form_captured(client):
    owner = register(client)
    form = client.post("/api/website-forms", headers=owner["headers"],
                       json={"name": "Contact", "preset": "custom",
                             "fields": [{"key": "first_name", "required": True}, {"key": "email", "required": True},
                                        {"key": "custom_service", "label": "Service", "type": "text"}]}).json()
    response = client.post(f"/api/public/forms/{form['public_key']}/submit",
                           content=json.dumps({"first_name": "Amara", "email": "amara@osei.example",
                                               "custom_service": "Ads", "_sid": uuid.uuid4().hex,
                                               "_elapsed_ms": 9000}),
                           headers={"Content-Type": "text/plain;charset=UTF-8", "Origin": "https://site.example"})
    lead = find_one(client, detectors.WEB_ENQUIRIES, {"id": response.json()["id"]})
    contact = find_one(client, "contacts", {"id": lead["contact_id"]})
    assert contact["lifecycle"] == "lead"
    field(client, owner, label="Budget", type="number")
    client.patch(f"/api/contacts/{contact['id']}", headers=owner["headers"], json={"custom_fields": {"cf_budget": 2500}})
    assert find_one(client, "contacts", {"id": contact["id"]})["custom_fields"] == {"custom_service": "Ads", "cf_budget": 2500.0}


def test_an_archived_field_keeps_its_values_but_takes_no_new_ones(client):
    owner = register(client)
    budget = field(client, owner, label="Budget", type="number")
    contact = client.post("/api/contacts", headers=owner["headers"], json={"name": "Ben Carter"}).json()
    client.patch(f"/api/contacts/{contact['id']}", headers=owner["headers"], json={"custom_fields": {"cf_budget": 900}})
    archived = client.patch(f"/api/custom-fields/{budget['id']}", headers=owner["headers"], json={"archived": True})
    assert archived.json()["archived_at"]
    assert client.get("/api/custom-fields", headers=owner["headers"]).json()["items"] == []
    assert client.patch(f"/api/contacts/{contact['id']}", headers=owner["headers"],
                        json={"custom_fields": {"cf_budget": 1}}).status_code == 422
    assert find_one(client, "contacts", {"id": contact["id"]})["custom_fields"]["cf_budget"] == 900.0


def test_companies_and_deals_take_their_own_fields(client):
    owner = register(client)
    headers = owner["headers"]
    field(client, owner, object="companies", label="Employees", type="number")
    field(client, owner, object="deals", label="Contract length", type="select", options=["12 months", "24 months"])
    company = client.post("/api/companies", headers=headers, json={"name": "Northwind"}).json()
    deal = client.post("/api/opportunities", headers=headers, json={"name": "Expansion", "value": 120000}).json()
    assert client.patch(f"/api/companies/{company['id']}", headers=headers,
                        json={"custom_fields": {"cf_employees": 85}}).json()["custom_fields"] == {"cf_employees": 85.0}
    assert client.patch(f"/api/opportunities/{deal['id']}", headers=headers,
                        json={"custom_fields": {"cf_contract_length": "24 months"}}).status_code == 200
    # A contact field does not exist on a company.
    assert client.patch(f"/api/companies/{company['id']}", headers=headers,
                        json={"custom_fields": {"cf_contract_length": "24 months"}}).status_code == 422


def test_another_tenants_fields_are_invisible_and_unusable(client):
    owner = register(client)
    stranger = register(client)
    theirs = field(client, stranger, label="Secret score", type="number")
    assert client.get("/api/custom-fields", headers=owner["headers"]).json()["items"] == []
    assert client.patch(f"/api/custom-fields/{theirs['id']}", headers=owner["headers"],
                        json={"label": "Mine now"}).status_code == 404
    mine = client.post("/api/contacts", headers=owner["headers"], json={"name": "Pat"}).json()
    assert client.patch(f"/api/contacts/{mine['id']}", headers=owner["headers"],
                        json={"custom_fields": {"cf_secret_score": 1}}).status_code == 422


# -------------------------------------------------------------------- lifecycle

def test_lifecycle_is_set_by_hand_filtered_on_and_moved_by_a_win(client):
    owner = register(client)
    headers = owner["headers"]
    contact = client.post("/api/contacts", headers=headers, json={"name": "Dana Reyes", "lifecycle": "qualified"}).json()
    assert contact["lifecycle"] == "qualified"
    assert client.post("/api/contacts", headers=headers, json={"name": "X", "lifecycle": "vip"}).status_code == 422
    assert client.patch(f"/api/contacts/{contact['id']}", headers=headers, json={"lifecycle": "vip"}).status_code == 422
    deal = client.post("/api/opportunities", headers=headers,
                       json={"name": "Expansion", "value": 120000, "contact_ids": [contact["id"]]}).json()
    won = client.patch(f"/api/opportunities/{deal['id']}/stage", headers=headers, json={"stage": "closed_won"})
    assert won.status_code == 200, won.text
    assert find_one(client, "contacts", {"id": contact["id"]})["lifecycle"] == "customer"
    listed = client.get("/api/contacts", params={"lifecycle": "customer"}, headers=headers).json()
    assert [c["id"] for c in listed] == [contact["id"]]
    # A partner on a won deal stays a partner: the CRM only promotes leads.
    partner = client.post("/api/contacts", headers=headers, json={"name": "Pat", "lifecycle": "partner"}).json()
    deal = client.post("/api/opportunities", headers=headers,
                       json={"name": "Referral", "value": 1, "contact_ids": [partner["id"]]}).json()
    client.patch(f"/api/opportunities/{deal['id']}/stage", headers=headers, json={"stage": "closed_won"})
    assert find_one(client, "contacts", {"id": partner["id"]})["lifecycle"] == "partner"


# ------------------------------------------------------------------------ views

def view(client, person, **body):
    return client.post("/api/views", headers=person["headers"],
                       json={"object": "contacts", "name": "Leads not contacted",
                             "filters": [{"field": "lifecycle", "op": "is", "value": "lead"}], **body})


def test_a_saved_view_is_shared_or_private_and_only_its_maker_changes_it(client):
    owner = register(client)
    member = add_member(client, owner)
    field(client, owner, label="Budget", type="number")
    shared = view(client, owner, sort={"field": "created_at", "order": "desc"},
                  columns=["name", "company_id", "lifecycle", "custom_fields.cf_budget"]).json()
    private = view(client, owner, name="My hot list", shared=False).json()
    assert shared["filters"] == [{"field": "lifecycle", "op": "is", "value": "lead"}]
    assert shared["columns"] == ["name", "company_id", "lifecycle", "custom_fields.cf_budget"]
    seen = client.get("/api/views", params={"object": "contacts"}, headers=member["headers"]).json()["items"]
    assert [v["id"] for v in seen] == [shared["id"]]
    assert client.patch(f"/api/views/{shared['id']}", headers=member["headers"], json={"name": "Mine"}).status_code == 403
    assert client.delete(f"/api/views/{private['id']}", headers=member["headers"]).status_code == 404
    renamed = client.patch(f"/api/views/{shared['id']}", headers=owner["headers"], json={"name": "New leads"})
    assert renamed.json()["name"] == "New leads"
    own = view(client, member, name="Member view").json()
    assert client.delete(f"/api/views/{own['id']}", headers=member["headers"]).json() == {"ok": True}


def test_a_view_refuses_operators_and_fields_it_cannot_use(client):
    owner = register(client)
    assert view(client, owner, filters=[{"field": "lifecycle", "op": "regex", "value": ".*"}]).status_code == 422
    assert view(client, owner, filters=[{"field": "$where", "op": "is", "value": "1"}]).status_code == 422
    assert view(client, owner, columns=["name; drop"]).status_code == 422
    # Well-formed but not a field this list has: a password hash, a typo, another tenant's field.
    assert view(client, owner, filters=[{"field": "password_hash", "op": "is_empty"}]).status_code == 422
    assert view(client, owner, columns=["custom_fields.cf_nothing"]).status_code == 422
    made = view(client, owner).json()
    assert client.patch(f"/api/views/{made['id']}", headers=owner["headers"],
                        json={"filters": [{"field": "tenant_id", "op": "is", "value": "x"}]}).status_code == 422
    # A comparison the field cannot make would save a view that never loads.
    field(client, owner, label="Budget", type="number")
    assert view(client, owner, filters=[{"field": "name", "op": "gt", "value": "a"}]).status_code == 422
    assert view(client, owner, filters=[{"field": "custom_fields.cf_budget", "op": "gt", "value": "lots"}]).status_code == 422
    assert client.patch(f"/api/views/{made['id']}", headers=owner["headers"],
                        json={"filters": [{"field": "name", "op": "before", "value": "2026-01-01"}]}).status_code == 422


# ------------------------------------------------------------------ filtering

def where(client, owner, filters, path="/api/contacts"):
    response = client.get(path, params={"where": json.dumps(filters)}, headers=owner["headers"])
    assert response.status_code == 200, response.text
    return sorted(record["name"] for record in response.json())


def test_a_list_filters_on_built_in_and_custom_fields_server_side(client):
    owner = register(client)
    headers = owner["headers"]
    budget = field(client, owner, label="Budget", type="number")
    plan = field(client, owner, label="Plan", type="select", options=["Starter", "Growth"])
    renews = field(client, owner, label="Renews", type="date")
    company = client.post("/api/companies", headers=headers, json={"name": "Northwind"}).json()
    people = [("Ana Ruiz", "ana@northwind.com", company["id"], "customer", {budget["key"]: 50000, plan["key"]: "Growth", renews["key"]: "2027-01-15"}),
              ("Ben Cho", "ben@gmail.com", None, "lead", {budget["key"]: 8000, plan["key"]: "Starter"}),
              ("Cleo Park", None, None, None, {})]
    for name, email, company_id, lifecycle, values in people:
        made = client.post("/api/contacts", headers=headers, json={"name": name, "email": email, "company_id": company_id, "lifecycle": lifecycle})
        assert made.status_code == 200, made.text
        if values:
            assert client.patch(f"/api/contacts/{made.json()['id']}", headers=headers, json={"custom_fields": values}).status_code == 200
    budget_path, plan_path, renews_path = (f"custom_fields.{f['key']}" for f in (budget, plan, renews))
    assert where(client, owner, [{"field": "lifecycle", "op": "is", "value": "lead"}]) == ["Ben Cho"]
    assert where(client, owner, [{"field": "lifecycle", "op": "is_empty"}]) == ["Cleo Park"]
    assert where(client, owner, [{"field": "company_id", "op": "is_empty"}]) == ["Ben Cho", "Cleo Park"]
    assert where(client, owner, [{"field": "email", "op": "is", "value": "ANA@NORTHWIND.COM"}]) == ["Ana Ruiz"]
    assert where(client, owner, [{"field": "email", "op": "contains", "value": "gmail."}]) == ["Ben Cho"]
    assert where(client, owner, [{"field": "email", "op": "is_not", "value": "ben@gmail.com"}]) == ["Ana Ruiz", "Cleo Park"]
    assert where(client, owner, [{"field": budget_path, "op": "gt", "value": "10000"}]) == ["Ana Ruiz"]
    assert where(client, owner, [{"field": budget_path, "op": "lt", "value": 10000},
                                 {"field": plan_path, "op": "is", "value": "Starter"}]) == ["Ben Cho"]
    assert where(client, owner, [{"field": plan_path, "op": "in", "value": ["Starter", "Growth"]}]) == ["Ana Ruiz", "Ben Cho"]
    assert where(client, owner, [{"field": renews_path, "op": "before", "value": "2027-02-01"}]) == ["Ana Ruiz"]
    assert where(client, owner, [{"field": budget_path, "op": "is_not_empty"}]) == ["Ana Ruiz", "Ben Cho"]
    # A regex in a value is text to match, not a pattern to run.
    assert where(client, owner, [{"field": "name", "op": "contains", "value": ".*"}]) == []
    # Fields the list does not have, and comparisons a field cannot make, are refused.
    for bad in ([{"field": "password_hash", "op": "is_empty"}],
                [{"field": "name", "op": "gt", "value": "a"}],
                [{"field": budget_path, "op": "gt", "value": "lots"}],
                [{"field": plan_path, "op": "contains", "value": "Gro"}],
                [{"field": "name", "op": "matches", "value": "a"}]):
        assert client.get("/api/contacts", params={"where": json.dumps(bad)}, headers=headers).status_code == 422, bad
    for raw in ("not json", json.dumps({"field": "name"}), json.dumps([{"op": "is"}])):
        assert client.get("/api/contacts", params={"where": raw}, headers=headers).status_code == 422, raw
    deals = client.get("/api/opportunities", params={"where": json.dumps([{"field": "value", "op": "gt", "value": 0}])}, headers=headers)
    assert deals.status_code == 200 and deals.json() == []
    companies = where(client, owner, [{"field": "name", "op": "is", "value": "northwind"}], path="/api/companies")
    assert companies == ["Northwind"]


def test_a_filter_never_reaches_another_tenants_custom_field(client):
    owner = register(client)
    stranger = register(client)
    theirs = field(client, stranger, label="Secret score", type="number")
    bad = [{"field": f"custom_fields.{theirs['key']}", "op": "gt", "value": 0}]
    assert client.get("/api/contacts", params={"where": json.dumps(bad)}, headers=owner["headers"]).status_code == 422


def test_clean_up_sets_a_lifecycle_from_history_and_leaves_hand_set_ones(client):
    owner = register(client)
    headers = owner["headers"]
    won_person = client.post("/api/contacts", headers=headers, json={"name": "Won Person"}).json()
    open_person = client.post("/api/contacts", headers=headers, json={"name": "Open Person"}).json()
    quiet = client.post("/api/contacts", headers=headers, json={"name": "Quiet Person"}).json()
    partner = client.post("/api/contacts", headers=headers, json={"name": "Partner Person", "lifecycle": "partner"}).json()
    won = client.post("/api/opportunities", headers=headers, json={"name": "Won", "value": 100, "contact_ids": [won_person["id"], partner["id"]]}).json()
    # Close it straight in the store, so the win itself does not set the stage first.
    call(client, server.db.opportunities.update_one, {"id": won["id"]}, {"$set": {"stage": "closed_won"}})
    client.post("/api/opportunities", headers=headers, json={"name": "Open", "value": 100, "contact_ids": [open_person["id"]]})
    scan = client.get("/api/contacts/cleanup", headers=headers).json()["lifecycle"]
    assert scan == {"customer": [won_person["id"]], "lead": [open_person["id"]]}
    applied = client.post("/api/contacts/cleanup/apply", headers=headers, json={"action": "set_lifecycle"}).json()
    assert applied["linked"] == 2
    stages = {c["name"]: c.get("lifecycle") for c in client.get("/api/contacts", headers=headers).json()}
    assert stages == {"Won Person": "customer", "Open Person": "lead", "Quiet Person": None, "Partner Person": "partner"}
    assert find_one(client, "contacts", {"id": won_person["id"]})["history"][-1]["action"] == "lifecycle_set"
    assert quiet["id"] not in client.get("/api/contacts/cleanup", headers=headers).json()["lifecycle"]["lead"]


def test_views_never_cross_tenants(client):
    owner = register(client)
    stranger = register(client)
    theirs = view(client, stranger).json()
    assert client.get("/api/views", headers=owner["headers"]).json()["items"] == []
    assert client.patch(f"/api/views/{theirs['id']}", headers=owner["headers"], json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/views/{theirs['id']}", headers=owner["headers"]).status_code == 404
