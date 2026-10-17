"""Creating an account straight from a team invitation.

Before this, a brand-new invitee had to register first -- which created an organisation of
their own with them as its admin -- and only then accept, which moved them into the
inviting team and left the stray organisation behind. `POST /api/team/invitations/accept-new`
creates the account directly inside the inviting tenant in one operation.

In-process against the real `app` through FastAPI's TestClient (real lifespan, so the
unique email index the race tests rely on exists), with a fresh motor client per test for
the reason given in test_security_headers.py. Every test makes its own inviting team via
/auth/register, so nothing depends on the shared seeded admin.
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_invitation_signup_unit")
os.environ.setdefault("JWT_SECRET", "invitation-signup-unit-jwt-secret-long-enough-1")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "invitation-signup-admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "Invitation-Signup-Admin-1!")

from fastapi.testclient import TestClient

import server

PASSWORD = "Teammate-Passw0rd!"


def _reset_motor_client():
    server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
    server.db = server.mclient[os.environ["DB_NAME"]]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _suffix():
    return uuid.uuid4().hex[:10]


def _db(client, fn):
    """Run one database call on the app's own event loop (motor binds to it)."""
    return client.portal.call(fn)


def _owner(client, name=None):
    """A fresh inviting team: its own tenant with this person as admin."""
    name = name or f"Owner {_suffix()}"
    r = client.post("/api/auth/register", json={"email": f"owner_{_suffix()}@example.com", "password": "Owner-Passw0rd!", "name": name})
    assert r.status_code == 200, r.text
    client.cookies.clear()  # authenticate explicitly per request; the cookie would win over the header
    return r.json()["token"], r.json()["user"]


def _invite(client, admin_token, role="member", email=None):
    email = email or f"teammate_{_suffix()}@example.com"
    r = client.post("/api/team/invitations", headers=_h(admin_token), json={"email": email, "role": role})
    assert r.status_code == 200, r.text
    return email, r.json()


def _accept_new(client, token, name="Riley Teammate", password=PASSWORD):
    r = client.post("/api/team/invitations/accept-new", json={"token": token, "name": name, "password": password})
    client.cookies.clear()
    return r


class FakeResponse:
    def __init__(self):
        self.cookies = []

    def set_cookie(self, *args, **kwargs):
        self.cookies.append((args, kwargs))


# --------------------------------------------------------------------------- happy path

def test_new_account_joins_the_inviting_team_with_the_invited_role_and_no_new_org():
    _reset_motor_client()
    with TestClient(server.app) as client:
        for role in ("member", "admin"):
            admin_token, admin = _owner(client)
            email, created = _invite(client, admin_token, role=role)
            token = created["invite_token"]
            name = f"Riley {_suffix()}"

            r = _accept_new(client, token, name=name)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["tenant_id"] == admin["tenant_id"]
            assert body["role"] == role
            assert body["user"]["email"] == email
            assert body["user"]["tenant_id"] == admin["tenant_id"]
            assert body["user"]["role"] == role
            assert "password_hash" not in body["user"]

            # The session it issued works, and lands in the inviting team.
            me = client.get("/api/auth/me", headers=_h(body["token"]))
            client.cookies.clear()
            assert me.status_code == 200, me.text
            assert me.json()["tenant_id"] == admin["tenant_id"]
            assert me.json()["role"] == role

            uid = body["user"]["user_id"]
            memberships = _db(client, lambda uid=uid: server.db.memberships.find({"user_id": uid}, {"_id": 0}).to_list(10))
            assert [(m["tenant_id"], m["role"], m["status"]) for m in memberships] == [(admin["tenant_id"], role, "active")]
            assert memberships[0]["invited_by"] == admin["email"]
            # No organisation of their own was created.
            stray = _db(client, lambda name=name: server.db.tenants.find_one({"name": f"{name}'s Org"}))
            assert stray is None
            assert _db(client, lambda email=email: server.db.users.count_documents({"email": email})) == 1

            inv = _db(client, lambda i=created["invitation"]["id"]: server.db.invitations.find_one({"id": i}, {"_id": 0}))
            assert inv["status"] == "accepted" and inv["accepted_at"] and inv["token_hash"] is None

            event = _db(client, lambda i=inv["id"]: server.db.domain_events.find_one(
                {"event_type": "team.invitation_accepted", "resource_id": i}, {"_id": 0}))
            assert event["tenant_id"] == admin["tenant_id"]
            assert event["actor"] == email
            assert event["payload"] == {"email": email, "role": role, "new_account": True}

            # The admin sees them on the team, and they can sign in with the new password.
            team = client.get("/api/team/members", headers=_h(admin_token)).json()
            assert any(m["user_id"] == uid and m["role"] == role for m in team)
            login = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
            client.cookies.clear()
            assert login.status_code == 200, login.text
            assert login.json()["user"]["tenant_id"] == admin["tenant_id"]


def test_accept_new_sets_the_session_cookie_like_login():
    _reset_motor_client()
    with TestClient(server.app) as client:
        admin_token, _ = _owner(client)
        _, created = _invite(client, admin_token)
        r = client.post("/api/team/invitations/accept-new",
                        json={"token": created["invite_token"], "name": "Cookie Teammate", "password": PASSWORD})
        assert r.status_code == 200, r.text
        cookie = r.headers.get("set-cookie", "")
        assert cookie.startswith("access_token=")
        assert "httponly" in cookie.lower()
        assert client.get("/api/auth/me").json()["email"] == r.json()["user"]["email"]
        client.cookies.clear()


def test_lookup_names_the_inviter_and_team():
    _reset_motor_client()
    with TestClient(server.app) as client:
        admin_token, admin = _owner(client, name="Jordan Avery")
        email, created = _invite(client, admin_token)
        look = client.get("/api/team/invitations/lookup", params={"token": created["invite_token"]})
        assert look.status_code == 200
        assert look.json()["invited_by_name"] == "Jordan Avery"
        assert look.json()["tenant_name"] == "Jordan Avery's Org"
        assert look.json()["email"] == email
        assert look.json()["status"] == "pending"


# --------------------------------------------------------------------------- refusals

def test_invalid_expired_revoked_and_used_tokens_are_refused():
    _reset_motor_client()
    with TestClient(server.app) as client:
        admin_token, _ = _owner(client)

        r = _accept_new(client, "not-a-real-token")
        assert r.status_code == 404

        expired_email, expired = _invite(client, admin_token)
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        _db(client, lambda: server.db.invitations.update_one({"id": expired["invitation"]["id"]}, {"$set": {"expires_at": past}}))
        r = _accept_new(client, expired["invite_token"])
        assert r.status_code == 400 and "expired" in r.json()["detail"]

        revoked_email, revoked = _invite(client, admin_token)
        assert client.post(f"/api/team/invitations/{revoked['invitation']['id']}/revoke", headers=_h(admin_token)).status_code == 200
        r = _accept_new(client, revoked["invite_token"])
        assert r.status_code == 400 and "revoked" in r.json()["detail"]

        used_email, used = _invite(client, admin_token)
        assert _accept_new(client, used["invite_token"]).status_code == 200
        r = _accept_new(client, used["invite_token"], password="Another-Passw0rd!")
        # Once consumed the token no longer resolves to anything at all.
        assert r.status_code == 404

        for email in (expired_email, revoked_email):
            assert _db(client, lambda email=email: server.db.users.find_one({"email": email})) is None
        assert _db(client, lambda: server.db.users.count_documents({"email": used_email})) == 1


def test_an_email_that_already_has_an_account_is_sent_to_sign_in():
    _reset_motor_client()
    with TestClient(server.app) as client:
        admin_token, admin = _owner(client)
        existing_email = f"existing_{_suffix()}@example.com"
        reg = client.post("/api/auth/register", json={"email": existing_email, "password": "Existing-Passw0rd!", "name": "Existing"})
        client.cookies.clear()
        assert reg.status_code == 200
        _, created = _invite(client, admin_token, email=existing_email)

        r = _accept_new(client, created["invite_token"])
        assert r.status_code == 409
        assert "Sign in" in r.json()["detail"] and existing_email in r.json()["detail"]

        # Nothing changed: one account, its own password, the invitation still usable.
        assert _db(client, lambda: server.db.users.count_documents({"email": existing_email})) == 1
        assert client.post("/api/auth/login", json={"email": existing_email, "password": PASSWORD}).status_code == 401
        login = client.post("/api/auth/login", json={"email": existing_email, "password": "Existing-Passw0rd!"})
        client.cookies.clear()
        assert login.status_code == 200
        look = client.get("/api/team/invitations/lookup", params={"token": created["invite_token"]})
        assert look.json()["status"] == "pending"

        # ...and the existing sign-in-then-accept path still takes them in.
        acc = client.post("/api/team/invitations/accept", headers=_h(login.json()["token"]), json={"token": created["invite_token"]})
        assert acc.status_code == 200, acc.text
        assert acc.json()["tenant_id"] == admin["tenant_id"]


def test_name_and_password_rules_are_enforced_before_the_invitation_is_consumed():
    _reset_motor_client()
    with TestClient(server.app) as client:
        admin_token, _ = _owner(client)
        email, created = _invite(client, admin_token)
        token = created["invite_token"]
        for name, password in (("Riley", "short"), ("Riley", " " * 12), ("Riley", "x" * 73), ("   ", PASSWORD)):
            r = _accept_new(client, token, name=name, password=password)
            assert r.status_code == 422, (name, password, r.text)
        assert _db(client, lambda: server.db.users.find_one({"email": email})) is None
        assert client.get("/api/team/invitations/lookup", params={"token": token}).json()["status"] == "pending"
        assert _accept_new(client, token).status_code == 200


def test_a_locked_out_email_cannot_get_a_session_through_the_invitation():
    _reset_motor_client()
    with TestClient(server.app) as client:
        admin_token, _ = _owner(client)
        email, created = _invite(client, admin_token)
        until = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        _db(client, lambda: server.db.login_lockouts.update_one(
            {"email": email}, {"$set": {"email": email, "failed_count": 9, "locked_until": until}}, upsert=True))
        r = _accept_new(client, created["invite_token"])
        assert r.status_code == 429
        assert _db(client, lambda: server.db.users.find_one({"email": email})) is None
        assert client.get("/api/team/invitations/lookup", params={"token": created["invite_token"]}).json()["status"] == "pending"


# --------------------------------------------------------------------------- races

def test_two_concurrent_submits_create_exactly_one_account(monkeypatch):
    _reset_motor_client()
    with TestClient(server.app) as client:
        admin_token, admin = _owner(client)
        email, created = _invite(client, admin_token)
        token = created["invite_token"]

        # Hold both requests after each has read the invitation as pending and found no
        # account for the email, so the only thing deciding the outcome is the claim.
        real_account_exists = server._account_exists

        async def slow_account_exists(address):
            found = await real_account_exists(address)
            await asyncio.sleep(0.05)
            return found

        monkeypatch.setattr(server, "_account_exists", slow_account_exists)

        async def race():
            def submit(password):
                return server.accept_invitation_new_account(
                    server.InviteSignupInput(token=token, name="Racer", password=password), FakeResponse())
            return await asyncio.gather(submit("Racer-One-Passw0rd!"), submit("Racer-Two-Passw0rd!"), return_exceptions=True)

        results = client.portal.call(race)
        wins = [r for r in results if isinstance(r, dict)]
        losses = [r for r in results if isinstance(r, server.HTTPException)]
        assert len(wins) == 1 and len(losses) == 1, results
        assert losses[0].status_code == 400 and "already been used" in losses[0].detail
        assert wins[0]["tenant_id"] == admin["tenant_id"]

        assert _db(client, lambda: server.db.users.count_documents({"email": email})) == 1
        uid = wins[0]["user"]["user_id"]
        assert _db(client, lambda: server.db.memberships.count_documents({"user_id": uid})) == 1
        events = _db(client, lambda: server.db.domain_events.count_documents(
            {"event_type": "team.invitation_accepted", "resource_id": created["invitation"]["id"]}))
        assert events == 1


def test_an_account_created_elsewhere_mid_request_gives_the_invitation_back(monkeypatch):
    _reset_motor_client()
    with TestClient(server.app) as client:
        admin_token, _ = _owner(client)
        email = f"racer_{_suffix()}@example.com"
        _, created = _invite(client, admin_token, email=email)
        reg = client.post("/api/auth/register", json={"email": email, "password": "Elsewhere-Passw0rd!", "name": "Elsewhere"})
        client.cookies.clear()
        assert reg.status_code == 200

        # Simulate the account appearing after the existence check: the unique email
        # index is then the only thing standing between this request and a second user.
        async def not_yet(_email):
            return False

        monkeypatch.setattr(server, "_account_exists", not_yet)
        r = _accept_new(client, created["invite_token"])
        assert r.status_code == 409, r.text
        assert _db(client, lambda: server.db.users.count_documents({"email": email})) == 1
        look = client.get("/api/team/invitations/lookup", params={"token": created["invite_token"]})
        assert look.status_code == 200 and look.json()["status"] == "pending"


def test_concurrent_accepts_by_a_signed_in_user_consume_the_invitation_once(monkeypatch):
    _reset_motor_client()
    with TestClient(server.app) as client:
        admin_token, _ = _owner(client)
        email = f"signedin_{_suffix()}@example.com"
        reg = client.post("/api/auth/register", json={"email": email, "password": "Signed-In-Passw0rd!", "name": "Signed In"})
        client.cookies.clear()
        user = reg.json()["user"]
        _, created = _invite(client, admin_token, email=email)

        # Both requests read the invitation as pending before either claims it.
        real_expire_if_needed = server._expire_if_needed

        async def slow_expire_if_needed(inv):
            inv = await real_expire_if_needed(inv)
            await asyncio.sleep(0.05)
            return inv

        monkeypatch.setattr(server, "_expire_if_needed", slow_expire_if_needed)

        async def race():
            def accept():
                return server.accept_invitation(server.TokenInput(token=created["invite_token"]), dict(user))
            return await asyncio.gather(accept(), accept(), return_exceptions=True)

        results = client.portal.call(race)
        assert sum(isinstance(r, dict) for r in results) == 1, results
        assert sum(isinstance(r, server.HTTPException) for r in results) == 1, results
