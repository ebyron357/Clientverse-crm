import os
import uuid

import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"
API = f"{BASE}/api"
ADMIN = {"email": os.environ.get("ADMIN_EMAIL", "admin@example.com"),
         "password": os.environ.get("ADMIN_PASSWORD", "AdminPass123!")}
MEMBER = {"email": os.environ.get("DEMO_MEMBER_EMAIL", "demo.member@clientverse.io"),
          "password": os.environ.get("DEMO_MEMBER_PASSWORD", "Member2026!")}


def _tok(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _register():
    email = f"int_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Pw2026!!", "name": "I"}, timeout=15)
    assert r.status_code == 200
    return email, r.json()["token"]


# ---------- token leakage / connection listing ----------

def test_connections_never_leak_tokens():
    h = _h(_tok(ADMIN))
    r = requests.get(f"{API}/integrations/connections", headers=h, timeout=15)
    assert r.status_code == 200
    body = r.text
    data = r.json()
    assert {c["provider"] for c in data} == {"gmail", "google_calendar", "stripe"}
    for bad in ("enc", "oauth_state", "code_verifier", "access_token", "refresh_token"):
        assert bad not in body, f"leaked field {bad}"


# ---------- permissions ----------

def test_member_denied_connection_management():
    m = _h(_tok(MEMBER))
    assert requests.post(f"{API}/integrations/stripe/connect", headers=m, timeout=15).status_code == 403
    assert requests.post(f"{API}/integrations/gmail/sync", headers=m, timeout=15).status_code == 403
    assert requests.post(f"{API}/integrations/stripe/disconnect", headers=m, timeout=15).status_code == 403
    assert requests.post(f"{API}/integrations/google/connect", headers=m, timeout=15).status_code == 403
    assert requests.get(f"{API}/integrations/sync-logs", headers=m, timeout=15).status_code == 403
    # members may still VIEW connection status
    assert requests.get(f"{API}/integrations/connections", headers=m, timeout=15).status_code == 200


# ---------- Stripe live read + idempotent sync ----------

def test_stripe_connect_and_idempotent_sync():
    if not os.environ.get("STRIPE_API_KEY"):
        import pytest
        pytest.skip("STRIPE_API_KEY not configured — Stripe live sync requires an external secret")
    h = _h(_tok(ADMIN))
    c = requests.post(f"{API}/integrations/stripe/connect", headers=h, timeout=30)
    assert c.status_code == 200 and c.json()["ok"] is True
    s1 = requests.post(f"{API}/integrations/stripe/sync", headers=h, timeout=60).json()
    assert s1["status"] == "completed"
    s2 = requests.post(f"{API}/integrations/stripe/sync", headers=h, timeout=60).json()
    assert s2["status"] == "completed"
    # idempotent: same set of records upserted, counts stable
    assert s1["scanned"] == s2["scanned"]
    # connection reflects a real successful sync
    conns = requests.get(f"{API}/integrations/connections", headers=h, timeout=15).json()
    stripe = next(x for x in conns if x["provider"] == "stripe")
    assert stripe["status"] == "active"
    assert stripe["last_success_at"] and stripe["account_identity"]


# ---------- Google OAuth foundation ----------

def test_google_connect_requires_configuration():
    h = _h(_tok(ADMIN))
    r = requests.post(f"{API}/integrations/google/connect", headers=h, timeout=15)
    # env has no GOOGLE_CLIENT_ID in this environment -> clear 400 (never a fake connected state)
    if r.status_code == 400:
        assert "google" in r.json()["detail"].lower()
    else:
        assert r.status_code == 200 and r.json()["authorization_url"].startswith("https://accounts.google.com/")


def test_oauth_callback_rejects_bad_state():
    r = requests.get(f"{API}/integrations/google/callback", params={"state": "bogus", "code": "x"},
                     allow_redirects=False, timeout=15)
    assert r.status_code in (302, 307)
    assert "oauth=error" in r.headers.get("location", "")


# ---------- tenant isolation ----------

def test_tenant_isolation_activity():
    # a fresh user in their own tenant cannot read HQ workspace activity
    _, tok = _register()
    h = _h(tok)
    # find any HQ workspace id from admin
    ah = _h(_tok(ADMIN))
    ws = requests.get(f"{API}/workspaces", headers=ah, timeout=15).json()[0]["id"]
    r = requests.get(f"{API}/integrations/workspaces/{ws}/activity", headers=h, timeout=15)
    assert r.status_code == 404
    # their own connections are isolated + all disconnected initially
    conns = requests.get(f"{API}/integrations/connections", headers=h, timeout=15).json()
    assert all(c["status"] == "disconnected" for c in conns)


# ---------- disconnect / revoke path ----------

def test_disconnect_marks_disconnected_and_blocks_sync():
    h = _h(_tok(ADMIN))
    requests.post(f"{API}/integrations/stripe/connect", headers=h, timeout=30)
    assert requests.post(f"{API}/integrations/stripe/disconnect", headers=h, timeout=15).status_code == 200
    conns = requests.get(f"{API}/integrations/connections", headers=h, timeout=15).json()
    assert next(x for x in conns if x["provider"] == "stripe")["status"] == "disconnected"
    # sync on a disconnected provider is rejected
    assert requests.post(f"{API}/integrations/stripe/sync", headers=h, timeout=15).status_code == 400
    # reconnect for later tests
    requests.post(f"{API}/integrations/stripe/connect", headers=h, timeout=30)


# ---------- pure normalizers (no network) ----------

def test_gmail_normalizer():
    import server
    msg = {"id": "m1", "threadId": "t1", "snippet": "hi there", "labelIds": ["INBOX"],
           "internalDate": "1700000000000",
           "payload": {"headers": [{"name": "From", "value": "Alice <alice@acme.com>"},
                                    {"name": "To", "value": "me@x.com"},
                                    {"name": "Subject", "value": "Kickoff"}]}}
    n = server.normalize_gmail_message(msg)
    assert n["external_id"] == "m1" and n["subject"] == "Kickoff"
    assert n["from_email"] == "alice@acme.com" and "me@x.com" in n["to"]
    assert n["labels"] == ["INBOX"] and n["ts"] is not None


def test_calendar_normalizer():
    import server
    ev = {"id": "e1", "summary": "Review", "status": "confirmed",
          "start": {"dateTime": "2026-07-01T10:00:00Z"}, "end": {"dateTime": "2026-07-01T11:00:00Z"},
          "organizer": {"email": "Bob@Acme.com"},
          "attendees": [{"email": "Carol@acme.com"}, {"email": "me@x.com"}],
          "hangoutLink": "https://meet.google.com/abc"}
    n = server.normalize_calendar_event(ev)
    assert n["external_id"] == "e1" and n["title"] == "Review"
    assert n["organizer"] == "bob@acme.com" and "carol@acme.com" in n["attendees"]
    assert n["conference_link"] == "https://meet.google.com/abc"


def test_stripe_normalizers():
    import server
    inv = server.normalize_stripe_invoice({"id": "in_1", "customer_email": "X@Y.com", "status": "open",
                                           "amount_due": 25000, "currency": "usd", "paid": False, "created": 1700000000})
    assert inv["type"] == "invoice" and inv["amount"] == 250.0 and inv["email"] == "x@y.com"
    cust = server.normalize_stripe_customer({"id": "cus_1", "email": "A@B.com", "name": "Acme", "created": 1700000000})
    assert cust["type"] == "customer" and cust["email"] == "a@b.com"


# ---------- existing CRM still works ----------

def test_existing_crm_unaffected():
    h = _h(_tok(MEMBER))
    for p in ["/companies", "/contacts", "/workspaces", "/dashboard"]:
        assert requests.get(f"{API}{p}", headers=h, timeout=15).status_code == 200
