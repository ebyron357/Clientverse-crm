"""Changing your own password, and an admin giving a teammate a temporary one.

Before this, nobody could change a password: an owner who set someone up with a temporary
password had no way to let them replace it. `POST /api/auth/change-password` needs the
current password, ends every other session and keeps this one; `POST
/api/team/members/{id}/reset-password` gives a teammate a temporary password that opens
nothing until they choose their own.

In-process against the real `app` through FastAPI's TestClient, with a fresh motor client
per test for the reason given in test_security_headers.py.
"""

import os
import sys
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_password_change_unit")
os.environ.setdefault("JWT_SECRET", "password-change-unit-jwt-secret-long-enough-12")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "password-change-admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "Password-Change-Admin-1!")

from fastapi.testclient import TestClient

import server

TEMPORARY = "Temporary-Passw0rd!"
CHOSEN = "Jasmine-Chosen-Passw0rd!"


def _reset_motor_client():
    server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
    server.db = server.mclient[os.environ["DB_NAME"]]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _account(client, password=TEMPORARY):
    email = f"agent_{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": password, "name": "Jasmine Parker"})
    assert r.status_code == 200, r.text
    client.cookies.clear()  # authenticate explicitly per request; the cookie would win over the header
    return email, r.json()["token"], r.json()["user"]


def _login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    client.cookies.clear()
    return r


def _change(client, token, current, new):
    r = client.post("/api/auth/change-password", headers=_h(token),
                    json={"current_password": current, "new_password": new})
    client.cookies.clear()
    return r


def test_changing_a_temporary_password_keeps_this_session_and_ends_the_others():
    _reset_motor_client()
    with TestClient(server.app) as client:
        email, phone_token, _ = _account(client)
        laptop_token = _login(client, email, TEMPORARY).json()["token"]

        r = _change(client, laptop_token, TEMPORARY, CHOSEN)
        assert r.status_code == 200, r.text
        fresh = r.json()["token"]

        assert client.get("/api/auth/me", headers=_h(fresh)).status_code == 200
        for old in (phone_token, laptop_token):
            gone = client.get("/api/auth/me", headers=_h(old))
            assert gone.status_code == 401
        assert _login(client, email, TEMPORARY).status_code == 401
        assert _login(client, email, CHOSEN).status_code == 200


def test_the_current_password_must_be_right_and_wrong_guesses_count_towards_the_lockout():
    _reset_motor_client()
    with TestClient(server.app) as client:
        email, token, _ = _account(client)
        r = _change(client, token, "not-my-password", CHOSEN)
        assert r.status_code == 400
        assert r.json()["detail"] == "Your current password isn't right."
        for _ in range(server.LOGIN_LOCKOUT_THRESHOLD):
            _change(client, token, "still-wrong", CHOSEN)
        locked = _change(client, token, TEMPORARY, CHOSEN)
        assert locked.status_code == 429
        assert _login(client, email, TEMPORARY).status_code == 401  # the same lock sign-in honours


def test_a_new_password_is_checked_before_anything_changes():
    _reset_motor_client()
    with TestClient(server.app) as client:
        email, token, _ = _account(client)
        assert _change(client, token, TEMPORARY, "short").status_code == 422
        assert _change(client, token, TEMPORARY, "x" * 73).status_code == 422
        same = _change(client, token, TEMPORARY, TEMPORARY)
        assert same.status_code == 422
        assert same.json()["detail"] == "Choose a password different from your current one."
        assert _login(client, email, TEMPORARY).status_code == 200


def test_an_admin_reset_gives_a_temporary_password_that_opens_nothing_until_replaced():
    _reset_motor_client()
    with TestClient(server.app) as client:
        admin_email, admin_token, _ = _account(client)
        teammate = f"assistant_{uuid.uuid4().hex[:10]}@example.com"
        invite = client.post("/api/team/invitations", headers=_h(admin_token),
                             json={"email": teammate, "role": "member"}).json()
        joined = client.post("/api/team/invitations/accept-new",
                             json={"token": invite["invite_token"], "name": "Alex Assistant", "password": CHOSEN})
        client.cookies.clear()
        assert joined.status_code == 200, joined.text
        teammate_id, teammate_old_token = joined.json()["user"]["user_id"], joined.json()["token"]

        r = client.post(f"/api/team/members/{teammate_id}/reset-password", headers=_h(admin_token))
        assert r.status_code == 200, r.text
        temporary = r.json()["temporary_password"]
        assert len(temporary) == 14 and temporary.count("-") == 2

        assert client.get("/api/auth/me", headers=_h(teammate_old_token)).status_code == 401
        signed_in = _login(client, teammate, temporary)
        assert signed_in.status_code == 200
        assert signed_in.json()["user"]["must_change_password"] is True
        token = signed_in.json()["token"]
        assert client.get("/api/auth/me", headers=_h(token)).status_code == 200
        blocked = client.get("/api/leads", headers=_h(token))
        assert blocked.status_code == 403
        assert blocked.json()["detail"] == "Choose your own password to continue."

        changed = _change(client, token, temporary, "Alex-Own-Passw0rd!")
        assert changed.status_code == 200, changed.text
        assert changed.json()["user"]["must_change_password"] is False
        assert client.get("/api/leads", headers=_h(changed.json()["token"])).status_code == 200


def test_only_an_admin_resets_and_only_for_their_own_team():
    _reset_motor_client()
    with TestClient(server.app) as client:
        _, admin_token, admin = _account(client)
        _, other_admin_token, other_admin = _account(client)
        own = client.post(f"/api/team/members/{admin['user_id']}/reset-password", headers=_h(admin_token))
        assert own.status_code == 400
        assert own.json()["detail"] == "Change your own password under Settings."
        across = client.post(f"/api/team/members/{other_admin['user_id']}/reset-password", headers=_h(admin_token))
        assert across.status_code == 404


def test_the_audit_trail_records_the_change_without_any_password():
    _reset_motor_client()
    with TestClient(server.app) as client:
        email, token, user = _account(client)
        assert _change(client, token, TEMPORARY, CHOSEN).status_code == 200

        async def events():
            return await server.db.domain_events.find(
                {"tenant_id": user["tenant_id"], "event_type": "auth.password_changed"}, {"_id": 0}).to_list(10)

        recorded = client.portal.call(events)
        assert len(recorded) == 1
        assert TEMPORARY not in str(recorded) and CHOSEN not in str(recorded)
