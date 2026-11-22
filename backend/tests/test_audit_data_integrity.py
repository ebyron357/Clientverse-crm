"""C-26: invalid states, sign-up races, membership uniqueness and literal search."""
import asyncio
import re
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError
from test_audit_security_fixes import STRONG, _register, _reset_motor_client

import crm_core
import server


@pytest.fixture
def client():
    _reset_motor_client()
    with TestClient(server.app) as client:
        yield client


@pytest.mark.parametrize("path,initial,updated", [
    ("tasks", "todo", "done"),
    ("deliverables", "draft", "approved"),
    ("client-requests", "open", "done"),
    ("commitments", "open", "fulfilled"),
    ("outcomes", "on_track", "at_risk"),
])
def test_each_resource_refuses_invalid_states_before_writing(client, path, initial, updated):
    user = _register(client).json()
    headers = {"Authorization": f"Bearer {user['token']}"}
    workspace_id = f"ws_{uuid.uuid4().hex}"

    async def workspace():
        await server.db.workspaces.insert_one({"id": workspace_id, "tenant_id": user["user"]["tenant_id"]})
    client.portal.call(workspace)
    body = {"workspace_id": workspace_id, "title": "State validation"}
    invalid = client.post(f"/api/{path}", headers=headers, json={**body, "status": "not-a-state"})
    assert invalid.status_code == 422, invalid.text
    created = client.post(f"/api/{path}", headers=headers, json={**body, "status": initial})
    assert created.status_code == 200, created.text
    record_id = created.json()["id"]
    invalid = client.patch(f"/api/{path}/{record_id}", headers=headers, json={"status": "not-a-state"})
    assert invalid.status_code == 422, invalid.text

    async def read():
        collection = path.replace("-", "_")
        return await server.db[collection].find_one({"id": record_id})
    assert client.portal.call(read)["status"] == initial
    changed = client.patch(f"/api/{path}/{record_id}", headers=headers, json={"status": updated})
    assert changed.status_code == 200, changed.text
    assert client.portal.call(read)["status"] == updated


@pytest.mark.parametrize("term", ["a" * 199 + "[", "a" * 199 + "\\", "(" * 201, " "+"x" * 300])
def test_long_search_remains_a_literal_pattern(client, term):
    pattern = crm_core._escape_regex(term)
    assert re.fullmatch(pattern, term.strip()[:200])
    user = _register(client).json()
    response = client.get("/api/contacts", params={"q": term},
                          headers={"Authorization": f"Bearer {user['token']}"})
    assert response.status_code == 200, response.text


def test_concurrent_same_email_registration_creates_only_one_org(client, monkeypatch):
    email = f"race_{uuid.uuid4().hex}@example.com"
    name = f"Race {uuid.uuid4().hex}"

    async def race():
        database = server.db
        arrived = 0
        both_checked = asyncio.Event()
        users = database.users

        async def checked_find(query, *args, **kwargs):
            nonlocal arrived
            if query == {"email": email}:
                result = await users.find_one(query, *args, **kwargs)
                arrived += 1
                if arrived == 2:
                    both_checked.set()
                await asyncio.wait_for(both_checked.wait(), timeout=10)
                return result
            return await users.find_one(query, *args, **kwargs)

        class DatabaseProxy:
            def __getattr__(self, key):
                return getattr(database, key)

        proxy = DatabaseProxy()
        proxy.users = SimpleNamespace(find_one=checked_find, insert_one=users.insert_one,
                                      delete_one=users.delete_one, update_one=users.update_one)
        monkeypatch.setattr(server, "db", proxy)
        inp = server.RegisterInput(email=email, name=name, password=STRONG)
        results = await asyncio.gather(server.register(inp, Response()), server.register(inp, Response()),
                                       return_exceptions=True)
        monkeypatch.setattr(server, "db", database)
        assert sum(isinstance(item, dict) for item in results) == 1, results
        rejected = next(item for item in results if isinstance(item, HTTPException))
        assert rejected.status_code == 400
        assert rejected.detail == "Email already registered"
        assert await users.count_documents({"email": email}) == 1
        assert await database.tenants.count_documents({"name": f"{name}'s Org"}) == 1
        assert await database.memberships.count_documents({"email": email}) == 1
    client.portal.call(race)


def test_membership_unique_index_upgrades_an_existing_nonunique_index(client):
    async def check():
        # Model the pre-upgrade index, then rerun startup's idempotent index creation.
        await server.db.memberships.create_index([("tenant_id", 1), ("user_id", 1)])
        await server.seed()
        await server.seed()
        tenant, user = uuid.uuid4().hex, uuid.uuid4().hex
        await server.db.memberships.insert_one({"tenant_id": tenant, "user_id": user, "role": "member"})
        with pytest.raises(DuplicateKeyError):
            await server.db.memberships.insert_one({"tenant_id": tenant, "user_id": user, "role": "admin"})
        # The same user is allowed in another organization.
        await server.db.memberships.insert_one({"tenant_id": uuid.uuid4().hex, "user_id": user})
    client.portal.call(check)


def test_registration_failure_cleans_only_its_own_records(client, monkeypatch):
    email = f"failed_{uuid.uuid4().hex}@example.com"
    name = f"Failed {uuid.uuid4().hex}"

    async def fail():
        database = server.db
        async def unavailable(*args, **kwargs):
            raise RuntimeError("membership write refused")
        class DatabaseProxy:
            def __getattr__(self, key):
                return getattr(database, key)
        proxy = DatabaseProxy()
        proxy.memberships = SimpleNamespace(find_one_and_update=unavailable, delete_many=database.memberships.delete_many)
        monkeypatch.setattr(server, "db", proxy)
        with pytest.raises(RuntimeError, match="membership write refused"):
            await server.register(server.RegisterInput(email=email, name=name, password=STRONG), Response())
        monkeypatch.setattr(server, "db", database)
        assert await database.users.count_documents({"email": email}) == 0
        assert await database.tenants.count_documents({"name": f"{name}'s Org"}) == 0
        assert await database.memberships.count_documents({"email": email}) == 0
    client.portal.call(fail)


def test_concurrent_legacy_membership_repair_creates_one_row(client):
    user = _register(client).json()["user"]

    async def repair():
        await server.db.memberships.delete_many({"user_id": user["user_id"]})
        results = await asyncio.gather(*(server.resolve_membership(dict(user)) for _ in range(8)))
        assert all(item["membership_status"] == "active" for item in results)
        assert await server.db.memberships.count_documents({"user_id": user["user_id"]}) == 1
        # Repair may not overwrite an existing disable decision or stale user role.
        await server.db.memberships.update_one({"user_id": user["user_id"]}, {"$set": {"status": "disabled"}})
        with pytest.raises(HTTPException) as rejected:
            await server.resolve_membership(dict(user))
        assert rejected.value.status_code == 403
    client.portal.call(repair)


def test_duplicate_legacy_memberships_fail_closed_without_choosing_a_role(client):
    async def check():
        database = server.db.client[f"audit_duplicates_{uuid.uuid4().hex}"]
        try:
            await database.memberships.insert_many([
                {"tenant_id": "one", "user_id": "person", "role": role} for role in ("admin", "member")])
            with pytest.raises(DuplicateKeyError):
                await server.ensure_identity_indexes(database)
            assert await database.memberships.count_documents({}) == 2
        finally:
            await server.db.client.drop_database(database.name)
    client.portal.call(check)


def test_approval_status_is_validated_and_cannot_bypass_a_decision(client):
    user = _register(client).json()
    headers = {"Authorization": f"Bearer {user['token']}"}
    workspace_id = f"ws_{uuid.uuid4().hex}"

    async def workspace():
        await server.db.workspaces.insert_one({"id": workspace_id, "tenant_id": user["user"]["tenant_id"]})
    client.portal.call(workspace)
    payload = {"workspace_id": workspace_id, "title": "Audit approval"}
    assert client.post("/api/approvals", headers=headers, json={**payload, "status": "todo"}).status_code == 422
    created = client.post("/api/approvals", headers=headers, json={**payload, "status": "approved"})
    assert created.status_code == 200, created.text
    approval = created.json()
    assert approval["status"] == "requested"
    assert client.patch(f"/api/approvals/{approval['id']}", headers=headers,
                        json={"status": "done"}).status_code == 422
    assert client.patch(f"/api/approvals/{approval['id']}", headers=headers,
                        json={"status": "approved"}).status_code == 200
