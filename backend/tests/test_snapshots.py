"""Snapshots: one workspace's setup, saved and loaded into another.

Each test builds a real setup in one workspace through the API, snapshots it, and loads it
into a second workspace by share code or file, then reads back what exists there,
including a lead sent through the copied form and the automation it starts.
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
os.environ.setdefault("DB_NAME", "clientverse_snapshots_unit")
os.environ.setdefault("JWT_SECRET", "snapshots-unit-jwt-secret-long-enough-123456789")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "admin@snapshots.example")
os.environ.setdefault("ADMIN_PASSWORD", "Snapshots-Admin-Passw0rd-1!")

from fastapi.testclient import TestClient

import detectors
import server

SITE = "https://www.example-agency.example"


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


def register(client, name="Taylor Owner"):
    email = f"owner-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post("/api/auth/register", json={"email": email, "password": "Str0ng-Passw0rd!", "name": name})
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


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def build_source(client):
    """An agency workspace with a real setup and real records that must never travel."""
    owner = register(client, "Avery Agency")
    member = add_member(client, owner)
    h = owner["headers"]
    ok(client.post("/api/industry-templates/agency/apply", headers=h))
    ok(client.post("/api/custom-fields", headers=h, json={"object": "contacts", "label": "Plan", "type": "select",
                                                          "options": ["Starter", "Growth"]}))
    form = next(f for f in find_all(client, "website_forms", {"tenant_id": owner["tenant_id"]}) if f["name"] == "Contact us")
    # Settings that belong to this workspace alone: its website, its people.
    ok(client.patch(f"/api/website-forms/{form['id']}", headers=h, json={"settings": {
        "allowed_origins": [SITE], "redirect_url": f"{SITE}/thanks",
        "assignment": {"mode": "specific", "users": [member["email"]]}}}))
    ok(client.post("/api/automations", headers=h, json={
        "name": "Contact us lead: Growth plan follow-up",
        "trigger": {"event": "lead.received", "form_id": form["id"]},
        "conditions": [{"field": "custom_fields.cf_plan", "op": "is", "value": "Growth"}],
        "steps": [{"type": "create_task", "title": "Call {{contact.first_name}}", "assign": "specific", "email": member["email"]},
                  {"type": "assign_owner", "mode": "specific", "email": member["email"]}],
        "stop_rules": ["replied"]}))
    ok(client.post("/api/views", headers=h, json={"object": "contacts", "name": "Growth plans",
                                                  "filters": [{"field": "custom_fields.cf_plan", "op": "is", "value": "Growth"}],
                                                  "columns": ["name", "custom_fields.cf_plan"], "shared": True}))
    ok(client.post("/api/views", headers=h, json={"object": "contacts", "name": "My private view", "shared": False}))
    ok(client.post("/api/contacts", headers=h, json={"name": "Secret Customer",
                                                     "email": "secret.customer@example.com"}))
    ok(client.post("/api/opportunities", headers=h, json={"name": "Confidential retainer", "value": 9000}))
    return owner, member, form


def snapshot(client, owner, **body):
    return ok(client.post("/api/snapshots", headers=owner["headers"], json={"name": "Agency starter", **body}))


def by(items):
    return {(i["kind"], i["name"]): i for i in items}


# ----------------------------------------------------------------------------- tests

def test_a_snapshot_holds_the_setup_and_no_records_people_links_or_secrets(client):
    owner, member, form = build_source(client)
    snap = snapshot(client, owner, description="Our standard setup")
    assert snap["counts"] == {"stages": 6, "fields": 4, "booking_pages": 3, "forms": 1, "automations": 4, "views": 1}
    body = client.get(f"/api/snapshots/{snap['id']}/file", headers=owner["headers"])
    assert body.status_code == 200 and "attachment" in body.headers["content-disposition"]
    text = json.dumps(body.json())
    assert body.json()["format"] == "clientverse.snapshot" and body.json()["version"] == 1
    for never in (member["email"], owner["email"], owner["tenant_id"], form["id"], form["public_key"], SITE,
                  "Secret", "secret.customer@example.com", "Confidential retainer", "My private view"):
        assert never not in text, never
    contents = body.json()["contents"]
    [automation] = [a for a in contents["automations"] if a["name"].startswith("Contact us lead")]
    assert automation["trigger"] == {"event": "lead.received", "form_ref": "form_1"}
    assert automation["steps"][0]["assign"] == "record_owner" and automation["steps"][1]["mode"] == "round_robin"
    [copied_form] = contents["forms"]
    assert copied_form["ref"] == "form_1" and "allowed_origins" not in copied_form["settings"]
    assert "assignment" not in copied_form["settings"] and copied_form["settings"]["auto_reply"]["enabled"] is False
    detail = ok(client.get(f"/api/snapshots/{snap['id']}", headers=owner["headers"]))
    assert "Growth plans" in detail["names"]["views"] and "Plan (contact)" in detail["names"]["fields"]


def test_a_share_code_loads_the_setup_into_another_workspace_and_the_copy_works(client):
    owner, _, _ = build_source(client)
    snap = snapshot(client, owner)
    code = ok(client.post(f"/api/snapshots/{snap['id']}/share", headers=owner["headers"]))["code"]
    assert code.startswith("cvs_")
    stored = call(client, server.db.snapshots.find_one, {"id": snap["id"]}, {"_id": 0})
    assert code not in json.dumps(stored)  # only its hash is kept

    target = register(client, "Blair Builder")
    preview = ok(client.post("/api/snapshot-loads/preview", headers=target["headers"], json={"code": code}))
    plan = by(preview["items"])
    assert preview["applied"] is False and preview["name"] == "Agency starter"
    assert plan[("pipeline", "Pipeline stages")]["action"] == "add"
    assert plan[("form", "Contact us")]["action"] == "add"
    assert plan[("view", "Growth plans (contacts)")]["action"] == "add"
    assert find_all(client, "website_forms", {"tenant_id": target["tenant_id"]}) == []

    result = ok(client.post("/api/snapshot-loads/apply", headers=target["headers"], json={"code": code}))
    assert all(i["action"] == "add" for i in result["items"]), [i for i in result["items"] if i["action"] != "add"]
    tenant = target["tenant_id"]
    [form] = find_all(client, "website_forms", {"tenant_id": tenant})
    assert form["settings"]["allowed_origins"] == [] and form["settings"]["assignment"]["mode"] == "unassigned"
    autos = {a["name"]: a for a in find_all(client, "automations", {"tenant_id": tenant})}
    assert {a["status"] for a in autos.values()} == {"draft"}
    copied = autos["Contact us lead: Growth plan follow-up"]
    assert copied["trigger"]["form_id"] == form["id"]
    assert copied["steps"][0]["assign"] == "record_owner" and copied["steps"][1]["mode"] == "round_robin"
    pages = find_all(client, "booking_event_types", {"tenant_id": tenant})
    assert {p["hosts"]["users"][0] for p in pages} == {target["email"]}
    [view] = find_all(client, "saved_views", {"tenant_id": tenant})
    assert view["owner"] == target["email"] and view["shared"] is True
    assert find_all(client, "contacts", {"tenant_id": tenant}) == []
    assert find_all(client, "opportunities", {"tenant_id": tenant}) == []
    assert ok(client.get("/api/snapshots", headers=owner["headers"]))["items"][0]["loads"] == 1

    # The copied form takes a real lead in the new workspace, and its copied automation turns on.
    ok(client.post(f"/api/automations/{copied['id']}/status", headers=target["headers"], json={"status": "on"}))
    payload = {"first_name": "Rae", "last_name": "Lee", "email": "rae@example.com", "phone": "555-201-7788",
               "message": "Need a site", "_sid": uuid.uuid4().hex, "_elapsed_ms": 9000}
    response = client.post(f"/api/public/forms/{form['public_key']}/submit", content=json.dumps(payload),
                           headers={"Content-Type": "text/plain;charset=UTF-8", "Origin": SITE})
    assert response.status_code == 200, response.text
    lead = call(client, server.db[detectors.WEB_ENQUIRIES].find_one, {"id": response.json()["id"]}, {"_id": 0})
    assert lead["tenant_id"] == tenant

    again = ok(client.post("/api/snapshot-loads/apply", headers=target["headers"], json={"code": code}))
    assert all(i["action"] == "keep" for i in again["items"])


def test_a_custom_field_keeps_its_meaning_when_its_key_differs_in_the_target(client):
    owner, _, _ = build_source(client)
    snap = snapshot(client, owner, include=["fields", "views", "automations", "forms"])
    file_body = client.get(f"/api/snapshots/{snap['id']}/file", headers=owner["headers"]).json()
    target = register(client)
    # The target already tracks "Plan", under the key an older version gave it.
    call(client, server.db.custom_field_defs.insert_one,
         {"id": f"fld_{uuid.uuid4().hex[:8]}", "tenant_id": target["tenant_id"], "object": "contacts",
          "key": "cf_plan_tier", "label": "Plan", "type": "select", "options": ["Starter", "Growth"],
          "help_text": None, "position": 0, "archived_at": None, "created_by": target["email"],
          "created_at": server.now_iso(), "updated_at": server.now_iso()})
    result = ok(client.post("/api/snapshot-loads/apply", headers=target["headers"], json={"file": file_body}))
    plan = by(result["items"])
    assert plan[("field", "Plan (contact)")]["action"] == "keep"
    assert "pipeline" not in {i["kind"] for i in result["items"]}  # not included in this snapshot
    [view] = find_all(client, "saved_views", {"tenant_id": target["tenant_id"]})
    assert view["filters"][0]["field"] == "custom_fields.cf_plan_tier"
    assert view["columns"] == ["name", "custom_fields.cf_plan_tier"]
    copied = next(a for a in find_all(client, "automations", {"tenant_id": target["tenant_id"]})
                  if a["name"].startswith("Contact us lead"))
    assert copied["conditions"][0]["field"] == "custom_fields.cf_plan_tier"


def test_a_file_is_checked_item_by_item_and_a_bad_item_is_skipped_with_its_reason(client):
    owner, _, _ = build_source(client)
    snap = snapshot(client, owner)
    body = client.get(f"/api/snapshots/{snap['id']}/file", headers=owner["headers"]).json()
    target = register(client)
    h = target["headers"]
    assert client.post("/api/snapshot-loads/preview", headers=h, json={"file": {**body, "format": "other"}}).status_code == 422
    assert client.post("/api/snapshot-loads/preview", headers=h, json={"file": {**body, "version": 99}}).status_code == 422
    assert client.post("/api/snapshot-loads/preview", headers=h,
                       json={"file": {**body, "contents": {**body["contents"], "forms": "lots"}}}).status_code == 422
    huge = {**body, "contents": {**body["contents"], "views": [{"object": "contacts", "name": "x" * 60, "filters": [],
                                                                "padding": "y" * 1_000_000}]}}
    assert client.post("/api/snapshot-loads/preview", headers=h, json={"file": huge}).status_code in (413, 422)
    tampered = json.loads(json.dumps(body))
    tampered["contents"]["booking_pages"][0]["duration_minutes"] = 100000
    tampered["contents"]["forms"][0]["fields"] = [{"key": "drop table"}]
    tampered["contents"]["automations"][0]["steps"] = [{"type": "send_money"}]
    tampered["contents"]["automations"][0]["name"] = "Tampered automation"
    tampered["contents"]["fields"].append({"object": "contacts", "label": "Weird", "type": "binary"})
    result = ok(client.post("/api/snapshot-loads/apply", headers=h, json={"file": tampered}))
    plan = by(result["items"])
    page_name = body["contents"]["booking_pages"][0]["name"]
    assert plan[("booking_page", page_name)]["action"] == "skip" and "Length" in plan[("booking_page", page_name)]["detail"]
    assert plan[("form", "Contact us")]["action"] == "skip"
    assert plan[("automation", "Tampered automation")]["action"] == "skip"
    assert plan[("field", "Weird (contact)")]["action"] == "skip"
    # Everything sound in the same file still loaded.
    assert plan[("pipeline", "Pipeline stages")]["action"] == "add"
    names = {p["name"] for p in find_all(client, "booking_event_types", {"tenant_id": target["tenant_id"]})}
    assert page_name not in names and len(names) == 2
    # The automation that started from the skipped form loads, and says so.
    contact_lead = plan[("automation", "Contact us lead: Growth plan follow-up")]
    assert contact_lead["action"] == "add" and "starts for any form" in contact_lead["detail"]


def test_sharing_can_be_stopped_and_a_new_code_replaces_the_old_one(client):
    owner, _, _ = build_source(client)
    snap = snapshot(client, owner)
    target = register(client)
    first = ok(client.post(f"/api/snapshots/{snap['id']}/share", headers=owner["headers"]))["code"]
    second = ok(client.post(f"/api/snapshots/{snap['id']}/share", headers=owner["headers"]))["code"]
    assert client.post("/api/snapshot-loads/preview", headers=target["headers"], json={"code": first}).status_code == 404
    assert client.post("/api/snapshot-loads/preview", headers=target["headers"], json={"code": second}).status_code == 200
    stopped = ok(client.delete(f"/api/snapshots/{snap['id']}/share", headers=owner["headers"]))
    assert stopped["shared"] is False
    assert client.post("/api/snapshot-loads/preview", headers=target["headers"], json={"code": second}).status_code == 404
    assert client.post("/api/snapshot-loads/preview", headers=target["headers"], json={"code": "cvs_guess"}).status_code == 404


def test_snapshots_are_admin_only_and_private_to_their_workspace(client):
    owner, member, _ = build_source(client)
    snap = snapshot(client, owner)
    stranger = register(client)
    sid = snap["id"]
    for method, path in (("get", "/api/snapshots"), ("post", "/api/snapshots"), ("get", f"/api/snapshots/{sid}"),
                         ("get", f"/api/snapshots/{sid}/file"), ("post", f"/api/snapshots/{sid}/share"),
                         ("delete", f"/api/snapshots/{sid}"), ("post", "/api/snapshot-loads/preview")):
        kwargs = {"json": {"name": "x", "snapshot_id": sid}} if method == "post" else {}
        assert getattr(client, method)(path, headers=member["headers"], **kwargs).status_code == 403, path
    for method, path in (("get", f"/api/snapshots/{sid}"), ("get", f"/api/snapshots/{sid}/file"),
                         ("post", f"/api/snapshots/{sid}/share"), ("delete", f"/api/snapshots/{sid}")):
        assert getattr(client, method)(path, headers=stranger["headers"]).status_code == 404, path
    # Another workspace cannot load a snapshot by its id, only by a share code.
    assert client.post("/api/snapshot-loads/preview", headers=stranger["headers"],
                       json={"snapshot_id": sid}).status_code == 404
    assert ok(client.get("/api/snapshots", headers=stranger["headers"]))["items"] == []
    assert client.post("/api/snapshot-loads/preview", headers=owner["headers"],
                       json={"snapshot_id": sid, "code": "cvs_x"}).status_code == 422
    ok(client.delete(f"/api/snapshots/{sid}", headers=owner["headers"]))
    assert ok(client.get("/api/snapshots", headers=owner["headers"]))["items"] == []


def test_loading_your_own_snapshot_brings_back_what_was_deleted(client):
    owner, _, _ = build_source(client)
    snap = snapshot(client, owner)
    h = owner["headers"]
    [form] = find_all(client, "website_forms", {"tenant_id": owner["tenant_id"]})
    ok(client.patch(f"/api/website-forms/{form['id']}", headers=h, json={"status": "archived"}))
    plan = by(ok(client.post("/api/snapshot-loads/preview", headers=h, json={"snapshot_id": snap["id"]}))["items"])
    assert plan[("form", "Contact us")]["action"] == "add"
    assert plan[("pipeline", "Pipeline stages")]["action"] == "keep"
    assert {i["action"] for k, i in plan.items() if k != ("form", "Contact us")} == {"keep"}
