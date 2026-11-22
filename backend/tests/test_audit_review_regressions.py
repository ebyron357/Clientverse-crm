"""C-26 review regressions: provisioning races and recovery completion states."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request
from test_audit_data_integrity import client as client
from test_audit_security_fixes import STRONG, _register
from test_invitation_signup import _invite

import recovery_case
import recovery_reconcile
import second_chance
import server
from work_queue import WorkQueue


class Proxy:
    def __init__(self, wrapped, **overrides):
        self.wrapped = wrapped
        self.__dict__.update(overrides)

    def __getattr__(self, key):
        return getattr(self.wrapped, key)


@pytest.mark.parametrize("signup", ["register", "invitation"])
@pytest.mark.parametrize("auth", ["login", "jwt", "google", "repair"])
def test_provisioning_account_cannot_authenticate_or_repair_membership(client, monkeypatch, signup, auth):
    email = f"pending_{uuid.uuid4().hex}@example.com"
    invitation = None
    if signup == "invitation":
        owner = _register(client).json()
        client.cookies.clear()
        _, invitation = _invite(client, owner["token"], email=email)

    async def race():
        database = server.db
        reserved, resume = asyncio.Event(), asyncio.Event()

        async def reserve(document, *args, **kwargs):
            result = await database.users.insert_one(document, *args, **kwargs)
            if document["email"] == email:
                reserved.set()
                await asyncio.wait_for(resume.wait(), 10)
            return result

        monkeypatch.setattr(server, "db", Proxy(database, users=Proxy(database.users, insert_one=reserve)))
        if signup == "register":
            operation = server.register(server.RegisterInput(email=email, password=STRONG, name="Pending"), Response())
        else:
            operation = server.accept_invitation_new_account(
                server.InviteSignupInput(token=invitation["invite_token"], password=STRONG, name="Pending"), Response())
        task = asyncio.create_task(operation)
        try:
            await asyncio.wait_for(reserved.wait(), 10)
            user = await database.users.find_one({"email": email}, {"_id": 0})
            response = Response()
            if auth == "login":
                attempt = server.login(server.LoginInput(email=email, password=STRONG), response)
            elif auth == "repair":
                attempt = server.resolve_membership(dict(user))
            else:
                token = server.create_access_token(user["user_id"], email)
                if auth == "google":
                    token = uuid.uuid4().hex
                    await database.user_sessions.insert_one({
                        "session_token": token, "user_id": user["user_id"],
                        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
                    })
                request = Request({"type": "http", "method": "GET", "path": "/api/auth/me",
                                   "headers": [(b"authorization", f"Bearer {token}".encode())]})
                attempt = server.get_current_user(request)
            outcome = (await asyncio.gather(attempt, return_exceptions=True))[0]
            memberships = await database.memberships.count_documents({"user_id": user["user_id"]})
        finally:
            resume.set()
            result = (await asyncio.gather(task, return_exceptions=True))[0]
            monkeypatch.setattr(server, "db", database)
        assert isinstance(outcome, HTTPException) and outcome.status_code == 401, outcome
        assert "set-cookie" not in response.headers
        assert memberships == 0
        assert isinstance(result, dict), result
        active = await database.users.find_one({"email": email})
        assert not active.get("registration_pending")
        member = await database.memberships.find_one({"user_id": active["user_id"]})
        if invitation:
            assert member["invited_by"] == owner["user"]["email"]
            assert member["invited_at"]
        assert (await server.login(server.LoginInput(email=email, password=STRONG), Response()))["token"]
    client.portal.call(race)


def test_invitation_provisioning_failure_releases_claim_and_identity(client, monkeypatch):
    owner = _register(client).json()
    client.cookies.clear()
    email, invitation = _invite(client, owner["token"])

    async def check():
        database = server.db
        async def unavailable(*args, **kwargs):
            raise RuntimeError("membership unavailable")
        monkeypatch.setattr(server, "db", Proxy(database, memberships=Proxy(
            database.memberships, insert_one=unavailable, find_one_and_update=unavailable)))
        with pytest.raises(RuntimeError, match="membership unavailable"):
            await server.accept_invitation_new_account(server.InviteSignupInput(
                token=invitation["invite_token"], name="Invitee", password=STRONG), Response())
        monkeypatch.setattr(server, "db", database)
        assert await database.users.count_documents({"email": email}) == 0
        assert await database.memberships.count_documents({"email": email}) == 0
        assert (await server._pending_invitation(invitation["invite_token"]))["status"] == "pending"
    client.portal.call(check)


def test_existing_account_invitation_tolerates_concurrent_membership_repair(client, monkeypatch):
    owner = _register(client).json()
    invitee = _register(client).json()["user"]
    _, invitation = _invite(client, owner["token"], email=invitee["email"])

    async def race():
        database = server.db
        key = {"tenant_id": owner["user"]["tenant_id"], "user_id": invitee["user_id"]}
        async def repair():
            # Model the legacy login repair winning before the invitation's write.
            await database.memberships.update_one(key, {"$setOnInsert": {
                **key, "id": f"mem_{uuid.uuid4().hex}", "email": invitee["email"],
                "role": "admin", "status": "active", "invited_by": None, "invited_at": None}}, upsert=True)
        async def stale_read(query, *args, **kwargs):
            result = await database.memberships.find_one(query, *args, **kwargs)
            if query == key:
                await repair()
            return result
        async def racing_upsert(query, *args, **kwargs):
            if query == key:
                await repair()
            return await database.memberships.find_one_and_update(query, *args, **kwargs)
        monkeypatch.setattr(server, "db", Proxy(database, memberships=Proxy(
            database.memberships, find_one=stale_read, find_one_and_update=racing_upsert)))
        result = await server.accept_invitation(server.TokenInput(token=invitation["invite_token"]), invitee)
        monkeypatch.setattr(server, "db", database)
        assert result["ok"]
        assert await database.memberships.count_documents(key) == 1
        membership = await database.memberships.find_one(key)
        assert membership["role"] == "member"
        assert membership["invited_by"] == owner["user"]["email"]
        assert membership["invited_at"] and membership["accepted_at"]
        with pytest.raises(HTTPException) as replay:
            await server.accept_invitation(server.TokenInput(token=invitation["invite_token"]), invitee)
        assert replay.value.status_code == 404  # the consumed token hash is no longer searchable
    client.portal.call(race)


@pytest.mark.parametrize("demo", [False, True])
def test_concurrent_team_seeding_preserves_unique_memberships_and_permissions(client, monkeypatch, demo):
    owner = _register(client).json()["user"]
    monkeypatch.setenv("ADMIN_EMAIL", owner["email"])
    demo_email = f"seed_{uuid.uuid4().hex}@example.com" if demo else ""
    monkeypatch.setenv("DEMO_MEMBER_EMAIL", demo_email)
    monkeypatch.setenv("DEMO_MEMBER_PASSWORD", STRONG if demo else "")

    async def check():
        database = server.db
        await database.memberships.delete_many({"user_id": owner["user_id"]})
        # Force both old read-then-insert writers to observe the same missing row.
        checked, arrived = asyncio.Event(), 0
        async def stale_read(query, *args, **kwargs):
            nonlocal arrived
            result = await database.memberships.find_one(query, *args, **kwargs)
            if query == {"tenant_id": owner["tenant_id"], "user_id": owner["user_id"]}:
                arrived += 1
                if arrived == 2:
                    checked.set()
                await asyncio.wait_for(checked.wait(), 10)
            return result
        monkeypatch.setattr(server, "db", Proxy(database, memberships=Proxy(database.memberships, find_one=stale_read)))
        results = await asyncio.gather(server.seed_team(), server.seed_team(), return_exceptions=True)
        monkeypatch.setattr(server, "db", database)
        assert results == [None, None], results
        assert await database.memberships.count_documents({"user_id": owner["user_id"]}) == 1
        if demo:
            assert await database.users.count_documents({"email": demo_email}) == 1
            assert await database.memberships.count_documents({"email": demo_email}) == 1
        await database.memberships.update_one({"user_id": owner["user_id"]},
                                              {"$set": {"status": "disabled", "role": "member"}})
        await server.seed_team()
        member = await database.memberships.find_one({"user_id": owner["user_id"]})
        assert (member["status"], member["role"]) == ("disabled", "member")
    client.portal.call(check)


@pytest.mark.parametrize("status", ["fulfilled", "met", "resolved", "closed", "cancelled", "done", "complete", "completed"])
def test_api_commitment_completion_stops_detection_and_closes_recovery(client, status):
    owner = _register(client).json()
    tenant = owner["user"]["tenant_id"]
    workspace = f"ws_{uuid.uuid4().hex}"
    headers = {"Authorization": f"Bearer {owner['token']}"}
    async def setup():
        await server.db.workspaces.insert_one({"id": workspace, "tenant_id": tenant})
    client.portal.call(setup)
    payload = {"title": "Overdue followup", "workspace_id": workspace,
               "due_date": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()}
    created = client.post("/api/commitments", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    commitment = created.json()
    async def detect():
        await second_chance.run_detection(server.db, WorkQueue(server.db), tenant)
        return await server.db[recovery_case.COLLECTION].find_one({"tenant_id": tenant})
    case = client.portal.call(detect)
    assert case and case["source_event_id"] == f"commitment:{commitment['id']}"
    updated = client.patch(f"/api/commitments/{commitment['id']}", headers=headers, json={"status": status})
    assert updated.status_code == 200, updated.text
    async def resolved():
        assert await second_chance.detect_missed_followups(server.db, WorkQueue(server.db), tenant) == []
        await recovery_reconcile.reconcile_tenant(server.db, tenant)
        closed = await server.db[recovery_case.COLLECTION].find_one({"id": case["id"]})
        assert closed["state"] == recovery_case.CLOSED
        assert closed["close_reason"] == "source_resolved"
    client.portal.call(resolved)
    # Importers may also create a commitment already completed.
    assert client.post("/api/commitments", headers=headers, json={**payload, "status": status}).status_code == 200
