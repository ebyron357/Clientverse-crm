import os
import uuid
import requests
from pymongo import MongoClient
from datetime import datetime, timezone, timedelta

BASE = os.environ.get("TEST_API_BASE", os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8001"))
API = f"{BASE}/api"
ADMIN = {"email": os.environ.get("ADMIN_EMAIL", "admin@example.com"), "password": os.environ.get("ADMIN_PASSWORD", "AdminPass123!")}


def login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def register(email, password="MemberPass123!", name="Test User"):
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": password, "name": name}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json(), {"Authorization": f"Bearer {r.json()['token']}"}


def unique_email(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


def admin_headers():
    return login(ADMIN["email"], ADMIN["password"])


def invite_and_accept(role="member"):
    ah = admin_headers()
    email = unique_email("member")
    _, mh = register(email)
    inv = requests.post(f"{API}/team/invitations", headers=ah, json={"email": email, "role": role}, timeout=20)
    assert inv.status_code == 200, inv.text
    token = inv.json()["invite_token"]
    accepted = requests.post(f"{API}/team/invitations/accept/{token}", headers=mh, timeout=20)
    assert accepted.status_code == 200, accepted.text
    return ah, mh, accepted.json(), inv.json()


def test_admin_can_invite_and_member_can_accept():
    ah = admin_headers(); email = unique_email("invite"); _, mh = register(email)
    r = requests.post(f"{API}/team/invitations", headers=ah, json={"email": email, "role": "member"}, timeout=20)
    assert r.status_code == 200, r.text
    a = requests.post(f"{API}/team/invitations/accept/{r.json()['invite_token']}", headers=mh, timeout=20)
    assert a.status_code == 200 and a.json()["role"] == "member"


def test_duplicate_invite_rejected():
    ah = admin_headers(); email = unique_email("dupe")
    r1 = requests.post(f"{API}/team/invitations", headers=ah, json={"email": email}, timeout=20)
    r2 = requests.post(f"{API}/team/invitations", headers=ah, json={"email": email}, timeout=20)
    assert r1.status_code == 200 and r2.status_code == 409


def test_revoked_invite_rejected():
    ah = admin_headers(); email = unique_email("revoked"); _, mh = register(email)
    inv = requests.post(f"{API}/team/invitations", headers=ah, json={"email": email}, timeout=20).json()
    assert requests.post(f"{API}/team/invitations/{inv['id']}/revoke", headers=ah, timeout=20).status_code == 200
    r = requests.post(f"{API}/team/invitations/accept/{inv['invite_token']}", headers=mh, timeout=20)
    assert r.status_code == 410


def test_expired_invite_rejected():
    ah = admin_headers(); email = unique_email("expired"); _, mh = register(email)
    inv = requests.post(f"{API}/team/invitations", headers=ah, json={"email": email}, timeout=20)
    assert inv.status_code == 200
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    db.team_invitations.update_one(
        {"id": inv.json()["id"]},
        {"$set": {"expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}},
    )
    r = requests.post(f"{API}/team/invitations/accept/{inv.json()['invite_token']}", headers=mh, timeout=20)
    assert r.status_code == 410, r.text
    assert "expired" in r.json()["detail"].lower()


def test_member_restricted_governance_and_crm_access():
    ah, mh, _, _ = invite_and_accept()
    assert requests.get(f"{API}/companies", headers=mh, timeout=20).status_code == 200
    assert requests.get(f"{API}/contacts", headers=mh, timeout=20).status_code == 200
    assert requests.get(f"{API}/opportunities", headers=mh, timeout=20).status_code == 200
    w = requests.get(f"{API}/workspaces", headers=mh, timeout=20)
    assert w.status_code == 200
    if w.json():
        detail = requests.get(f"{API}/workspaces/{w.json()[0]['id']}", headers=mh, timeout=20)
        assert detail.status_code == 200
        payload = detail.json()
        assert all(k in payload for k in ("tasks", "deliverables", "commitments", "events", "health"))
    assert requests.post(f"{API}/team/invitations", headers=mh, json={"email": unique_email('nope')}, timeout=20).status_code == 403
    assert requests.patch(f"{API}/mcp/server/kill", headers=mh, json={"enabled": True}, timeout=20).status_code == 403
    if w.json():
        wid = w.json()[0]["id"]
        assert requests.patch(f"{API}/workspaces/{wid}/undo-window", headers=mh, json={"minutes": 30}, timeout=20).status_code == 403
    hooks = requests.get(f"{API}/webhooks", headers=mh, timeout=20)
    assert hooks.status_code == 200
    if hooks.json():
        hook = hooks.json()[0]
        assert "secret" not in hook
        assert requests.patch(f"{API}/webhooks/{hook['id']}", headers=mh, json={"rotate_secret": True}, timeout=20).status_code == 403
        assert requests.get(f"{API}/webhooks/{hook['id']}/secret", headers=mh, timeout=20).status_code == 403


def test_member_cannot_approve_mcp_write_and_admin_can():
    ah, mh, _, _ = invite_and_accept()
    workspaces = requests.get(f"{API}/workspaces", headers=mh, timeout=20).json()
    assert workspaces
    inv = requests.post(f"{API}/mcp/invoke", headers=mh, json={"tool": "create_task", "args": {"workspace_id": workspaces[0]["id"], "title": "permission test task"}}, timeout=20)
    assert inv.status_code == 200, inv.text
    approval_id = inv.json()["approval_id"]
    denied = requests.patch(f"{API}/approvals/{approval_id}", headers=mh, json={"status": "approved"}, timeout=20)
    assert denied.status_code == 403
    allowed = requests.patch(f"{API}/approvals/{approval_id}", headers=ah, json={"status": "approved"}, timeout=20)
    assert allowed.status_code == 200, allowed.text
    invocation_id = allowed.json()["execution"]["invocation_id"]
    assert requests.post(f"{API}/mcp/invocations/{invocation_id}/undo", headers=mh, json={"reason": "member should be denied"}, timeout=20).status_code == 403
    assert requests.post(f"{API}/mcp/invocations/{invocation_id}/undo", headers=ah, json={"reason": "admin verification"}, timeout=20).status_code == 200


def test_admin_governance_actions():
    ah = admin_headers()
    k = requests.patch(f"{API}/mcp/server/kill", headers=ah, json={"enabled": True}, timeout=20); assert k.status_code == 200
    assert requests.patch(f"{API}/mcp/server/kill", headers=ah, json={"enabled": False}, timeout=20).status_code == 200
    w = requests.get(f"{API}/workspaces", headers=ah, timeout=20).json(); assert w
    assert requests.patch(f"{API}/workspaces/{w[0]['id']}/undo-window", headers=ah, json={"minutes": 45}, timeout=20).status_code == 200
    hooks = requests.get(f"{API}/webhooks", headers=ah, timeout=20).json(); assert hooks
    hid = hooks[0]["id"]
    assert requests.patch(f"{API}/webhooks/{hid}", headers=ah, json={"rotate_secret": True}, timeout=20).status_code == 200
    s = requests.get(f"{API}/webhooks/{hid}/secret", headers=ah, timeout=20); assert s.status_code == 200 and s.json()["secret"]


def test_tenant_a_cannot_manipulate_tenant_b_membership():
    ah = admin_headers()
    email_b = unique_email("admin-b"); _, bh = register(email_b, name="Admin B")
    bmembers = requests.get(f"{API}/team/members", headers=bh, timeout=20); assert bmembers.status_code == 200
    target = bmembers.json()[0]["id"]
    assert requests.patch(f"{API}/team/members/{target}/role", headers=ah, json={"role": "member"}, timeout=20).status_code == 404
    assert requests.delete(f"{API}/team/members/{target}", headers=ah, timeout=20).status_code == 404


def test_last_admin_safety():
    email = unique_email("sole-admin"); _, h = register(email, name="Sole Admin")
    members = requests.get(f"{API}/team/members", headers=h, timeout=20).json(); assert len(members) == 1
    mid = members[0]["id"]
    assert requests.patch(f"{API}/team/members/{mid}/role", headers=h, json={"role": "member"}, timeout=20).status_code == 409
    assert requests.delete(f"{API}/team/members/{mid}", headers=h, timeout=20).status_code == 409


def test_admin_can_reject_mcp_write_and_manage_member_lifecycle():
    ah, mh, accepted, invitation = invite_and_accept()
    workspaces = requests.get(f"{API}/workspaces", headers=mh, timeout=20).json()
    assert workspaces
    pending = requests.post(
        f"{API}/mcp/invoke", headers=mh,
        json={"tool": "create_task", "args": {"workspace_id": workspaces[0]["id"], "title": "rejection authorization test"}},
        timeout=20,
    )
    assert pending.status_code == 200, pending.text
    approval_id = pending.json()["approval_id"]
    denied = requests.patch(f"{API}/approvals/{approval_id}", headers=mh, json={"status": "rejected"}, timeout=20)
    assert denied.status_code == 403
    rejected = requests.patch(f"{API}/approvals/{approval_id}", headers=ah, json={"status": "rejected"}, timeout=20)
    assert rejected.status_code == 200, rejected.text

    members = requests.get(f"{API}/team/members", headers=ah, timeout=20)
    assert members.status_code == 200
    target = next(m for m in members.json() if m.get("user") and m["user"].get("email") == invitation["email"])
    membership_id = target["id"]
    promoted = requests.patch(f"{API}/team/members/{membership_id}/role", headers=ah, json={"role": "admin"}, timeout=20)
    assert promoted.status_code == 200, promoted.text
    demoted = requests.patch(f"{API}/team/members/{membership_id}/role", headers=ah, json={"role": "member"}, timeout=20)
    assert demoted.status_code == 200, demoted.text
    disabled = requests.delete(f"{API}/team/members/{membership_id}", headers=ah, timeout=20)
    assert disabled.status_code == 200 and disabled.json()["status"] == "disabled"


def test_admin_can_resend_invitation_and_old_token_is_single_use_invalidated():
    ah = admin_headers(); email = unique_email("resend")
    first = requests.post(f"{API}/team/invitations", headers=ah, json={"email": email, "role": "member"}, timeout=20)
    assert first.status_code == 200, first.text
    old_token = first.json()["invite_token"]
    resent = requests.post(f"{API}/team/invitations/{first.json()['id']}/resend", headers=ah, timeout=20)
    assert resent.status_code == 200, resent.text
    assert resent.json()["invite_token"] != old_token
    _, mh = register(email)
    assert requests.post(f"{API}/team/invitations/accept/{old_token}", headers=mh, timeout=20).status_code == 404
    accepted = requests.post(f"{API}/team/invitations/accept/{resent.json()['invite_token']}", headers=mh, timeout=20)
    assert accepted.status_code == 200, accepted.text
