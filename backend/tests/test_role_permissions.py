import os
import uuid
from datetime import datetime, timezone, timedelta

import requests
import pymongo

BASE = os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"
API = f"{BASE}/api"
ADMIN = {"email": os.environ.get("ADMIN_EMAIL", "tvpro357@gmail.com"),
         "password": os.environ.get("ADMIN_PASSWORD", "ClientVerse2026!")}
MEMBER = {"email": "demo.member@clientverse.io", "password": "Member2026!"}

_mongo = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
_db = _mongo[os.environ.get("DB_NAME", "test_database")]


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.text}"
    return r.json()["token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _register(email=None):
    email = email or f"invitee_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Invitee2026!", "name": "Invitee"}, timeout=15)
    assert r.status_code == 200, r.text
    return email, r.json()["token"], r.json()["user"]


def _admin():
    return _login(ADMIN)


def _member():
    return _login(MEMBER)


# --------------------------- member denials (403) ---------------------------

def test_member_denied_governance_actions():
    m = _h(_member())
    a = _h(_admin())
    ws = requests.get(f"{API}/workspaces", headers=a, timeout=15).json()[0]["id"]
    hooks = requests.get(f"{API}/webhooks", headers=a, timeout=15).json()
    wid = hooks[0]["id"]

    assert requests.get(f"{API}/team/members", headers=m, timeout=15).status_code == 403
    assert requests.post(f"{API}/team/invitations", headers=m, json={"email": "x@y.com", "role": "member"}, timeout=15).status_code == 403
    assert requests.patch(f"{API}/mcp/server/kill", headers=m, json={"enabled": True}, timeout=15).status_code == 403
    assert requests.post(f"{API}/mcp/invocations/does-not-exist/undo", headers=m, json={"reason": "x"}, timeout=15).status_code == 403
    assert requests.patch(f"{API}/workspaces/{ws}/undo-window", headers=m, json={"minutes": 30}, timeout=15).status_code == 403
    assert requests.post(f"{API}/webhooks", headers=m, json={"name": "n", "url": "http://x", "events": []}, timeout=15).status_code == 403
    assert requests.patch(f"{API}/webhooks/{wid}", headers=m, json={"rotate_secret": True}, timeout=15).status_code == 403
    assert requests.get(f"{API}/webhooks/{wid}/secret", headers=m, timeout=15).status_code == 403
    assert requests.patch(f"{API}/approvals/some-id", headers=m, json={"status": "approved"}, timeout=15).status_code == 403


def test_admin_can_perform_governance_actions():
    a = _h(_admin())
    ws = requests.get(f"{API}/workspaces", headers=a, timeout=15).json()[0]["id"]
    hooks = requests.get(f"{API}/webhooks", headers=a, timeout=15).json()
    assert all("secret" not in h for h in hooks), "list must not leak secrets"
    wid = hooks[0]["id"]

    assert requests.get(f"{API}/team/members", headers=a, timeout=15).status_code == 200
    assert requests.patch(f"{API}/mcp/server/kill", headers=a, json={"enabled": True}, timeout=15).status_code == 200
    assert requests.patch(f"{API}/mcp/server/kill", headers=a, json={"enabled": False}, timeout=15).status_code == 200
    assert requests.patch(f"{API}/workspaces/{ws}/undo-window", headers=a, json={"minutes": 45}, timeout=15).status_code == 200
    rs = requests.get(f"{API}/webhooks/{wid}/secret", headers=a, timeout=15)
    assert rs.status_code == 200 and rs.json().get("secret")
    assert requests.patch(f"{API}/webhooks/{wid}", headers=a, json={"rotate_secret": True}, timeout=15).status_code == 200


# --------------------------- member CRM access ---------------------------

def test_member_retains_crm_access():
    m = _h(_member())
    for path in ["/companies", "/contacts", "/opportunities", "/workspaces", "/dashboard", "/events"]:
        assert requests.get(f"{API}{path}", headers=m, timeout=15).status_code == 200, path
    # member can create an operational CRM record
    r = requests.post(f"{API}/companies", headers=m, json={"name": f"MemberCo {uuid.uuid4().hex[:5]}"}, timeout=15)
    assert r.status_code == 200


# --------------------------- invitation lifecycle ---------------------------

def test_admin_invite_and_member_accept():
    a = _h(_admin())
    email, itoken, _ = _register()
    r = requests.post(f"{API}/team/invitations", headers=a, json={"email": email, "role": "member"}, timeout=15)
    assert r.status_code == 200, r.text
    invite_token = r.json()["invite_token"]

    look = requests.get(f"{API}/team/invitations/lookup", params={"token": invite_token}, timeout=15)
    assert look.status_code == 200 and look.json()["status"] == "pending"

    acc = requests.post(f"{API}/team/invitations/accept", headers=_h(itoken), json={"token": invite_token}, timeout=15)
    assert acc.status_code == 200, acc.text
    me = requests.get(f"{API}/auth/me", headers=_h(itoken), timeout=15).json()
    assert me["role"] == "member"
    # they now belong to the admin's tenant
    admin_me = requests.get(f"{API}/auth/me", headers=a, timeout=15).json()
    assert me["tenant_id"] == admin_me["tenant_id"]


def test_duplicate_active_invitation_rejected():
    a = _h(_admin())
    email = f"dup_{uuid.uuid4().hex[:8]}@example.com"
    r1 = requests.post(f"{API}/team/invitations", headers=a, json={"email": email, "role": "member"}, timeout=15)
    assert r1.status_code == 200
    r2 = requests.post(f"{API}/team/invitations", headers=a, json={"email": email, "role": "member"}, timeout=15)
    assert r2.status_code == 400


def test_cannot_invite_existing_active_member():
    a = _h(_admin())
    r = requests.post(f"{API}/team/invitations", headers=a, json={"email": MEMBER["email"], "role": "member"}, timeout=15)
    assert r.status_code == 400


def test_expired_invitation_rejected():
    a = _h(_admin())
    email, itoken, _ = _register()
    r = requests.post(f"{API}/team/invitations", headers=a, json={"email": email, "role": "member"}, timeout=15)
    inv_id = r.json()["invitation"]["id"]
    invite_token = r.json()["invite_token"]
    # backdate expiry directly in the DB
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    _db.invitations.update_one({"id": inv_id}, {"$set": {"expires_at": past}})
    acc = requests.post(f"{API}/team/invitations/accept", headers=_h(itoken), json={"token": invite_token}, timeout=15)
    assert acc.status_code == 400 and "expired" in acc.json()["detail"].lower()


def test_revoked_invitation_rejected():
    a = _h(_admin())
    email, itoken, _ = _register()
    r = requests.post(f"{API}/team/invitations", headers=a, json={"email": email, "role": "member"}, timeout=15)
    inv_id = r.json()["invitation"]["id"]
    invite_token = r.json()["invite_token"]
    assert requests.post(f"{API}/team/invitations/{inv_id}/revoke", headers=a, timeout=15).status_code == 200
    acc = requests.post(f"{API}/team/invitations/accept", headers=_h(itoken), json={"token": invite_token}, timeout=15)
    assert acc.status_code == 400 and "revoked" in acc.json()["detail"].lower()


def test_resend_generates_new_working_token():
    a = _h(_admin())
    email, itoken, _ = _register()
    r = requests.post(f"{API}/team/invitations", headers=a, json={"email": email, "role": "member"}, timeout=15)
    inv_id = r.json()["invitation"]["id"]
    old_token = r.json()["invite_token"]
    rs = requests.post(f"{API}/team/invitations/{inv_id}/resend", headers=a, timeout=15)
    assert rs.status_code == 200
    new_token = rs.json()["invite_token"]
    assert new_token != old_token
    # old token no longer resolves to a pending invite (single active token)
    assert requests.get(f"{API}/team/invitations/lookup", params={"token": old_token}, timeout=15).status_code == 404
    assert requests.post(f"{API}/team/invitations/accept", headers=_h(itoken), json={"token": new_token}, timeout=15).status_code == 200


def test_wrong_email_cannot_accept():
    a = _h(_admin())
    email, _, _ = _register()  # invited person
    _, other_token, _ = _register()  # different logged-in user
    r = requests.post(f"{API}/team/invitations", headers=a, json={"email": email, "role": "member"}, timeout=15)
    invite_token = r.json()["invite_token"]
    acc = requests.post(f"{API}/team/invitations/accept", headers=_h(other_token), json={"token": invite_token}, timeout=15)
    assert acc.status_code == 403


# --------------------------- tenant isolation ---------------------------

def test_tenant_isolation_membership():
    a = _h(_admin())
    # a user in a *different* tenant (freshly registered -> own tenant)
    _, _, other_user = _register()
    other_uid = other_user["user_id"]
    r = requests.patch(f"{API}/team/members/{other_uid}/role", headers=a, json={"role": "admin"}, timeout=15)
    assert r.status_code == 404  # not visible/manipulable from tenant A


# --------------------------- last-admin safety ---------------------------

def test_last_admin_protection_and_safe_demotion():
    a = _h(_admin())
    members = requests.get(f"{API}/team/members", headers=a, timeout=15).json()
    admins = [m for m in members if m["role"] == "admin" and m["status"] == "active"]
    admin_uid = next(m["user_id"] for m in admins)
    member_row = next(m for m in members if m["email"] == MEMBER["email"])
    member_uid = member_row["user_id"]

    # only 1 admin -> cannot self-demote or self-disable
    if len(admins) == 1:
        assert requests.patch(f"{API}/team/members/{admin_uid}/role", headers=a, json={"role": "member"}, timeout=15).status_code == 400
        assert requests.patch(f"{API}/team/members/{admin_uid}/status", headers=a, json={"status": "disabled"}, timeout=15).status_code == 400

    # promote the demo member -> now 2 admins -> demoting one is allowed
    assert requests.patch(f"{API}/team/members/{member_uid}/role", headers=a, json={"role": "admin"}, timeout=15).status_code == 200
    assert requests.patch(f"{API}/team/members/{member_uid}/role", headers=a, json={"role": "member"}, timeout=15).status_code == 200  # safe: original admin remains
    # restore original state (demo member stays member)
    restored = requests.get(f"{API}/team/members", headers=a, timeout=15).json()
    assert next(m for m in restored if m["email"] == MEMBER["email"])["role"] == "member"


def test_disabled_member_loses_access():
    a = _h(_admin())
    email, itoken, _ = _register()
    r = requests.post(f"{API}/team/invitations", headers=a, json={"email": email, "role": "member"}, timeout=15)
    requests.post(f"{API}/team/invitations/accept", headers=_h(itoken), json={"token": r.json()["invite_token"]}, timeout=15)
    me = requests.get(f"{API}/auth/me", headers=_h(itoken), timeout=15).json()
    uid = me["user_id"]
    assert requests.patch(f"{API}/team/members/{uid}/status", headers=a, json={"status": "disabled"}, timeout=15).status_code == 200
    # disabled member is now blocked
    assert requests.get(f"{API}/auth/me", headers=_h(itoken), timeout=15).status_code == 403
    assert requests.get(f"{API}/companies", headers=_h(itoken), timeout=15).status_code == 403
