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
TESTS.write_text(text)
print("role permission tests strengthened")
