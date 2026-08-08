from pathlib import Path

TESTS = Path(__file__).resolve().parents[1] / "backend" / "tests" / "test_role_permissions.py"
text = TESTS.read_text()
text = text.replace(
    "import requests\nfrom datetime import datetime, timezone, timedelta\n",
    "import requests\nfrom pymongo import MongoClient\nfrom datetime import datetime, timezone, timedelta\n",
)
old = '''def test_expired_invite_rejected_via_test_hookless_token_status():
    ah = admin_headers(); email = unique_email("expired")
    inv = requests.post(f"{API}/team/invitations", headers=ah, json={"email": email}, timeout=20)
    assert inv.status_code == 200
    # Expiration behavior is covered server-side by expires_at comparison; force path through an invalidated old token by resend.
    old = inv.json()["invite_token"]
    assert requests.post(f"{API}/team/invitations/{inv.json()['id']}/resend", headers=ah, timeout=20).status_code == 200
    _, mh = register(email)
    r = requests.post(f"{API}/team/invitations/accept/{old}", headers=mh, timeout=20)
    assert r.status_code in (404, 410)
'''
new = '''def test_expired_invite_rejected():
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
'''
if old not in text:
    raise RuntimeError("expired invitation test anchor not found")
text = text.replace(old, new, 1)
old2 = '''    w = requests.get(f"{API}/workspaces", headers=mh, timeout=20)
    assert w.status_code == 200
'''
new2 = '''    w = requests.get(f"{API}/workspaces", headers=mh, timeout=20)
    assert w.status_code == 200
    if w.json():
        detail = requests.get(f"{API}/workspaces/{w.json()[0]['id']}", headers=mh, timeout=20)
        assert detail.status_code == 200
        payload = detail.json()
        assert all(k in payload for k in ("tasks", "deliverables", "commitments", "events", "health"))
'''
if old2 not in text:
    raise RuntimeError("member CRM access anchor not found")
text = text.replace(old2, new2, 1)

extra = r'''

def test_admin_can_reject_mcp_write_and_manage_member_lifecycle():
    ah, mh, accepted, _ = invite_and_accept()
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
    target = next(m for m in members.json() if m["user_id"] == accepted.get("membership_id", "") or m["user"] and m["user"].get("email") != ADMIN["email"])
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
'''
if "def test_admin_can_reject_mcp_write_and_manage_member_lifecycle" not in text:
    text += extra
TESTS.write_text(text)
print("role permission tests strengthened")
