"""Agency accounts: an agency workspace runs client accounts, opens them, and pushes
snapshots to many at once, while every client account stays separate.

The tests sign in as the agency's admin and member, a client account's own admin and an
unrelated agency, and check what each can reach, including after access is taken away.
"""

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
os.environ.setdefault("DB_NAME", "clientverse_agency_unit")
os.environ.setdefault("JWT_SECRET", "agency-unit-jwt-secret-long-enough-123456789")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "admin@agency.example")
os.environ.setdefault("ADMIN_PASSWORD", "Agency-Admin-Passw0rd-1!")

from fastapi.testclient import TestClient

import server


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


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def register(client, name="Avery Agency"):
    email = f"owner-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post("/api/auth/register", json={"email": email, "password": "Str0ng-Passw0rd!", "name": name})
    assert response.status_code == 200, response.text
    client.cookies.clear()
    body = response.json()
    return {"email": email, "user_id": body["user"]["user_id"], "tenant_id": body["user"]["tenant_id"],
            "headers": auth(body["token"])}


def person(client, tenant_id, role):
    email = f"{role}-{uuid.uuid4().hex[:8]}@example.com"
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    call(client, server.db.users.insert_one,
         {"user_id": user_id, "email": email, "name": f"Pat {role.title()}", "role": role, "tenant_id": tenant_id,
          "password_hash": server.hash_password("Str0ng-Passw0rd!"), "created_at": server.now_iso()})
    call(client, server.db.memberships.insert_one,
         {"id": f"mem_{uuid.uuid4().hex[:8]}", "tenant_id": tenant_id, "user_id": user_id, "email": email,
          "role": role, "status": "active", "created_at": server.now_iso()})
    return {"email": email, "user_id": user_id, "tenant_id": tenant_id,
            "headers": auth(server.create_access_token(user_id, email))}


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def agency_with_snapshot(client):
    agency = register(client)
    ok(client.post("/api/industry-templates/agency/apply", headers=agency["headers"]))
    ok(client.post("/api/contacts", headers=agency["headers"], json={"name": "Agency Own Client", "email": "own@agency.example"}))
    snap = ok(client.post("/api/snapshots", headers=agency["headers"], json={"name": "Agency starter"}))
    return agency, snap


def enter(client, who, tenant_id):
    """Open a client account. The session that opened it ends (one browser, one session),
    so `who` carries on with a fresh session of their own, as a second browser would."""
    body = ok(client.post(f"/api/agency/accounts/{tenant_id}/enter", headers=who["headers"]))
    client.cookies.clear()
    assert client.get("/api/auth/me", headers=who["headers"]).status_code == 401
    who["headers"] = auth(server.create_access_token(who["user_id"], who["email"]))
    return body


# ----------------------------------------------------------------------------- tests

def test_a_client_account_starts_from_a_snapshot_and_holds_none_of_the_agencys_records(client):
    agency, snap = agency_with_snapshot(client)
    created = ok(client.post("/api/agency/accounts", headers=agency["headers"],
                             json={"name": "Bright Dental", "snapshot_id": snap["id"]}))
    account = created["account"]
    assert account["name"] == "Bright Dental" and account["contacts"] == 0
    assert {i["action"] for i in created["items"]} == {"add"}
    tid = account["tenant_id"]
    pages = find_all(client, "booking_event_types", {"tenant_id": tid})
    assert {p["name"] for p in pages} == {"Discovery call", "Strategy session", "Client check-in"}
    # Nobody is on the new account's team yet, so its booking pages wait, paused, for a host.
    assert {p["status"] for p in pages} == {"paused"}
    assert all("paused until someone" in i["detail"] for i in created["items"] if i["kind"] == "booking_page")
    assert find_all(client, "contacts", {"tenant_id": tid}) == []
    listed = ok(client.get("/api/agency/accounts", headers=agency["headers"]))
    assert [a["name"] for a in listed["items"]] == ["Bright Dental"]
    assert listed["items"][0]["last_snapshot"]["name"] == "Agency starter"
    me = ok(client.get("/api/auth/me", headers=agency["headers"]))
    assert me["workspace"]["kind"] == "agency" and me["workspace"]["client_accounts"] == 1


def test_an_agency_admin_works_inside_a_client_account_and_comes_back(client):
    agency, _ = agency_with_snapshot(client)
    tid = ok(client.post("/api/agency/accounts", headers=agency["headers"], json={"name": "Oak Realty"}))["account"]["tenant_id"]
    inside = enter(client, agency, tid)
    acting = auth(inside["token"])
    assert inside["user"]["tenant_id"] == tid and inside["user"]["role"] == "admin"
    me = ok(client.get("/api/auth/me", headers=acting))
    assert me["acting"]["name"] == "Oak Realty" and me["acting"]["agency_tenant_id"] == agency["tenant_id"]
    assert me["workspace"]["kind"] == "client"
    # Work done inside lands in the client account, and the agency's records are not there.
    ok(client.post("/api/contacts", headers=acting, json={"name": "Oak Buyer", "email": "buyer@oak.example"}))
    names = {c["name"] for c in ok(client.get("/api/contacts", headers=acting))}
    assert "Oak Buyer" in names and "Agency Own Client" not in names
    assert [c["name"] for c in find_all(client, "contacts", {"tenant_id": tid})] == ["Oak Buyer"]
    # Both audit trails record the visit.
    for tenant in (tid, agency["tenant_id"]):
        assert find_all(client, "domain_events", {"tenant_id": tenant, "event_type": "agency.account_opened"}), tenant
    back = ok(client.post("/api/agency/leave", headers=acting))
    client.cookies.clear()
    assert back["user"]["tenant_id"] == agency["tenant_id"] and "acting" not in back["user"]
    # The session that was inside the client account ended when they left.
    assert client.get("/api/auth/me", headers=acting).status_code == 401
    assert "Agency Own Client" in {c["name"] for c in ok(client.get("/api/contacts", headers=auth(back["token"])))}


def test_signing_in_and_changing_password_return_the_workspace_a_reload_would_show(client):
    agency, _ = agency_with_snapshot(client)
    tid = ok(client.post("/api/agency/accounts", headers=agency["headers"], json={"name": "Cedar Law"}))["account"]["tenant_id"]
    # The screens show the account switcher from the signed-in user, so sign-in must carry
    # the same workspace /auth/me does, not wait for a page reload.
    signed_in = ok(client.post("/api/auth/login", json={"email": agency["email"], "password": "Str0ng-Passw0rd!"}))
    client.cookies.clear()
    assert signed_in["user"]["workspace"]["kind"] == "agency"
    assert signed_in["user"]["workspace"] == ok(client.get("/api/auth/me", headers=auth(signed_in["token"])))["workspace"]
    # Changing the password inside a client account keeps this browser in that account.
    inside = enter(client, agency, tid)
    changed = ok(client.post("/api/auth/change-password", headers=auth(inside["token"]),
                             json={"current_password": "Str0ng-Passw0rd!", "new_password": "N3w-Str0ng-Passw0rd!"}))
    client.cookies.clear()
    assert changed["user"]["acting"]["tenant_id"] == tid and changed["user"]["workspace"]["kind"] == "client"
    me = ok(client.get("/api/auth/me", headers=auth(changed["token"])))
    assert me["tenant_id"] == tid and me["acting"]["name"] == "Cedar Law"
    # The change belongs to the person, so it is recorded in their own workspace.
    assert find_all(client, "domain_events", {"tenant_id": agency["tenant_id"], "event_type": "auth.password_changed"})
    assert not find_all(client, "domain_events", {"tenant_id": tid, "event_type": "auth.password_changed"})


def test_access_to_a_client_account_ends_as_soon_as_the_agency_admin_loses_it(client):
    agency, _ = agency_with_snapshot(client)
    colleague = person(client, agency["tenant_id"], "admin")
    tid = ok(client.post("/api/agency/accounts", headers=agency["headers"], json={"name": "Peak Fitness"}))["account"]["tenant_id"]
    acting = auth(enter(client, colleague, tid)["token"])
    assert client.get("/api/contacts", headers=acting).status_code == 200
    call(client, server.db.memberships.update_one, {"tenant_id": agency["tenant_id"], "user_id": colleague["user_id"]},
         {"$set": {"role": "member"}})
    assert client.get("/api/contacts", headers=acting).status_code == 401
    call(client, server.db.memberships.update_one, {"tenant_id": agency["tenant_id"], "user_id": colleague["user_id"]},
         {"$set": {"role": "admin"}})
    acting = auth(enter(client, colleague, tid)["token"])
    # Moving the account out of the agency ends access too.
    call(client, server.db.tenants.update_one, {"tenant_id": tid}, {"$set": {"parent_tenant_id": "ten_elsewhere"}})
    assert client.get("/api/contacts", headers=acting).status_code == 401


def test_only_agency_admins_reach_client_accounts_and_clients_never_reach_the_agency(client):
    agency, snap = agency_with_snapshot(client)
    member = person(client, agency["tenant_id"], "member")
    first = ok(client.post("/api/agency/accounts", headers=agency["headers"], json={"name": "First Client"}))["account"]["tenant_id"]
    second = ok(client.post("/api/agency/accounts", headers=agency["headers"], json={"name": "Second Client"}))["account"]["tenant_id"]
    client_admin = person(client, first, "admin")
    other_agency = register(client, "Other Agency")

    assert client.get("/api/agency/accounts", headers=member["headers"]).status_code == 403
    assert client.post(f"/api/agency/accounts/{first}/enter", headers=member["headers"]).status_code == 403
    # A client account's own admin works in their account only.
    assert client.get("/api/agency/accounts", headers=client_admin["headers"]).status_code == 403
    assert client.post("/api/agency/accounts", headers=client_admin["headers"], json={"name": "Nested"}).status_code == 403
    assert client.post(f"/api/agency/accounts/{second}/enter", headers=client_admin["headers"]).status_code == 403
    assert "Agency Own Client" not in {c["name"] for c in ok(client.get("/api/contacts", headers=client_admin["headers"]))}
    assert ok(client.get("/api/snapshots", headers=client_admin["headers"]))["items"] == []
    me = ok(client.get("/api/auth/me", headers=client_admin["headers"]))
    assert me["workspace"] == {"name": "First Client", "kind": "client", "agency_name": me["workspace"]["agency_name"]}
    # Another agency cannot open, rename or push to these accounts.
    assert client.post(f"/api/agency/accounts/{first}/enter", headers=other_agency["headers"]).status_code == 404
    assert client.patch(f"/api/agency/accounts/{first}", headers=other_agency["headers"], json={"name": "x"}).status_code == 404
    other_snap = ok(client.post("/api/snapshots", headers=other_agency["headers"], json={"name": "Theirs"}))
    assert client.post("/api/agency/snapshot-push/apply", headers=other_agency["headers"],
                       json={"snapshot_id": other_snap["id"], "account_ids": [first]}).status_code == 404
    assert client.post("/api/agency/snapshot-push/apply", headers=agency["headers"],
                       json={"snapshot_id": other_snap["id"], "account_ids": [first]}).status_code == 404
    # A forged token naming an account outside the agency is refused.
    forged = server.create_access_token(other_agency["user_id"], other_agency["email"], acting_tenant=first)
    assert client.get("/api/contacts", headers=auth(forged)).status_code == 401
    # Working inside a client account, new client accounts still belong to the agency.
    acting = auth(enter(client, agency, first)["token"])
    made = ok(client.post("/api/agency/accounts", headers=acting, json={"name": "Third Client", "snapshot_id": snap["id"]}))
    third = call(client, server.db.tenants.find_one, {"tenant_id": made["account"]["tenant_id"]}, {"_id": 0})
    assert third["parent_tenant_id"] == agency["tenant_id"]


def test_a_snapshot_is_pushed_to_many_accounts_with_a_result_for_each(client):
    agency, snap = agency_with_snapshot(client)
    a = ok(client.post("/api/agency/accounts", headers=agency["headers"], json={"name": "Alpha"}))["account"]["tenant_id"]
    b = ok(client.post("/api/agency/accounts", headers=agency["headers"], json={"name": "Beta"}))["account"]["tenant_id"]
    beta_admin = person(client, b, "admin")
    # Beta already has its own "Discovery call", set its own way.
    acting = auth(enter(client, agency, b)["token"])
    page = ok(client.post("/api/booking/event-types", headers=acting, json={
        "preset": "meeting", "name": "Discovery call", "hosts": {"mode": "specific", "users": [beta_admin["email"]]}}))
    body = {"snapshot_id": snap["id"], "account_ids": [a, b]}

    preview = ok(client.post("/api/agency/snapshot-push/preview", headers=agency["headers"], json=body))
    by_name = {r["name"]: r for r in preview["accounts"]}
    assert by_name["Alpha"]["skip"] == 0 and by_name["Alpha"]["keep"] == 0
    assert by_name["Beta"]["keep"] == 1
    assert find_all(client, "website_forms", {"tenant_id": a}) == []

    pushed = ok(client.post("/api/agency/snapshot-push/apply", headers=agency["headers"], json=body))
    assert {r["name"]: r["add"] for r in pushed["accounts"]} == {"Alpha": by_name["Alpha"]["add"], "Beta": by_name["Beta"]["add"]}
    for tid in (a, b):
        assert [f["name"] for f in find_all(client, "website_forms", {"tenant_id": tid})] == ["Contact us"]
        assert {x["status"] for x in find_all(client, "automations", {"tenant_id": tid})} == {"draft"}
    beta_pages = {p["name"]: p for p in find_all(client, "booking_event_types", {"tenant_id": b})}
    assert beta_pages["Discovery call"]["id"] == page["id"]  # theirs, untouched
    # Pages pushed into Beta are hosted by Beta's own admin and take bookings; Alpha has no
    # team yet, so its pages wait, paused.
    assert beta_pages["Strategy session"]["hosts"]["users"] == [beta_admin["email"]]
    assert beta_pages["Strategy session"]["status"] == "active"
    assert {p["status"] for p in find_all(client, "booking_event_types", {"tenant_id": a})} == {"paused"}

    again = ok(client.post("/api/agency/snapshot-push/apply", headers=agency["headers"], json=body))
    assert all(r["add"] == 0 for r in again["accounts"])
    # One account that is not the agency's stops the whole push before anything loads.
    c = ok(client.post("/api/agency/accounts", headers=agency["headers"], json={"name": "Gamma"}))["account"]["tenant_id"]
    refused = client.post("/api/agency/snapshot-push/apply", headers=agency["headers"],
                          json={"snapshot_id": snap["id"], "account_ids": [c, "ten_not_ours"]})
    assert refused.status_code == 404
    assert find_all(client, "website_forms", {"tenant_id": c}) == []
