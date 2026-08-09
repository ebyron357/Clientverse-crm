"""Live integrations engine: providers, encrypted credentials, normalizers,
Google token helpers, adapters and the bounded/idempotent sync engine."""
import os
import asyncio
import json as _json
import httpx
import stripe as _stripe
from cryptography.fernet import Fernet
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException
from app.shared import db, new_id, now_iso, record_event, FRONTEND_URL

PROVIDERS = ["gmail", "google_calendar", "stripe"]
ADAPTER_VERSION = "1.0"
CONN_STATUSES = ["disconnected", "connecting", "active", "degraded", "expired", "revoked", "error"]
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI") or f"{FRONTEND_URL}/api/integrations/google/callback"
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

_FERNET = None
def _fernet():
    global _FERNET
    if _FERNET is None:
        key = os.environ.get("INTEGRATION_ENC_KEY")
        if not key:
            raise HTTPException(status_code=500, detail="Secure credential storage not configured (INTEGRATION_ENC_KEY)")
        _FERNET = Fernet(key.encode())
    return _FERNET

def enc_secret(d: dict) -> str:
    return _fernet().encrypt(_json.dumps(d).encode()).decode()

def dec_secret(s: str) -> dict:
    return _json.loads(_fernet().decrypt(s.encode()).decode())

SAFE_CONN_FIELDS = {"_id": 0, "enc": 0, "oauth_state": 0, "code_verifier": 0}

def _public_conn(c: dict) -> dict:
    return {k: v for k, v in c.items() if k not in ("_id", "enc", "oauth_state", "code_verifier")}

async def ensure_connections(tenant_id: str):
    for p in PROVIDERS:
        if not await db.integration_connections.find_one({"tenant_id": tenant_id, "provider": p}):
            await db.integration_connections.insert_one({
                "id": new_id("conn"), "tenant_id": tenant_id, "provider": p, "status": "disconnected",
                "account_identity": None, "scopes": [], "connected_by": None, "connected_at": None,
                "last_sync_at": None, "last_success_at": None, "last_error": None, "revoked_at": None,
                "credential_version": 0, "adapter_version": ADAPTER_VERSION, "created_at": now_iso(),
            })

async def set_conn(tenant_id, provider, **fields):
    await db.integration_connections.update_one({"tenant_id": tenant_id, "provider": provider}, {"$set": fields})

async def _contacts_by_email(tenant_id):
    rows = await db.contacts.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(5000)
    return {(r.get("email") or "").lower(): r for r in rows if r.get("email")}

async def _workspace_for_company(tenant_id, company_id):
    if not company_id:
        return None
    ws = await db.workspaces.find_one({"tenant_id": tenant_id, "company_id": company_id}, {"_id": 0, "id": 1})
    return ws["id"] if ws else None

# ---- Pure normalizers (unit-testable, no network) ----

def normalize_gmail_message(msg: dict) -> dict:
    headers = {h.get("name", "").lower(): h.get("value", "") for h in (msg.get("payload", {}).get("headers") or [])}
    ts = None
    if msg.get("internalDate"):
        try:
            ts = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc).isoformat()
        except Exception:
            ts = None
    def _emails(v):
        import re
        return [e.lower() for e in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", v or "")]
    return {
        "external_id": msg.get("id"), "thread_id": msg.get("threadId"),
        "subject": headers.get("subject", "(no subject)"),
        "from_email": (_emails(headers.get("from")) or [None])[0], "from_raw": headers.get("from"),
        "to": _emails(headers.get("to")) + _emails(headers.get("cc")),
        "labels": msg.get("labelIds") or [], "snippet": msg.get("snippet", ""), "ts": ts,
    }

def normalize_calendar_event(ev: dict) -> dict:
    start = (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date")
    end = (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date")
    org = (ev.get("organizer") or {}).get("email")
    attendees = [(a.get("email") or "").lower() for a in (ev.get("attendees") or []) if a.get("email")]
    conf = None
    ep = (ev.get("conferenceData") or {}).get("entryPoints") or []
    for e in ep:
        if e.get("uri"):
            conf = e["uri"]; break
    conf = conf or ev.get("hangoutLink")
    return {
        "external_id": ev.get("id"), "title": ev.get("summary", "(untitled)"),
        "start": start, "end": end, "organizer": (org or "").lower() or None,
        "attendees": attendees, "conference_link": conf, "status": ev.get("status"),
    }

def normalize_stripe_customer(c) -> dict:
    return {"external_id": c.get("id"), "type": "customer", "email": (c.get("email") or "").lower() or None,
            "name": c.get("name"), "status": "active", "amount": None, "currency": c.get("currency"),
            "ts": datetime.fromtimestamp(c.get("created", 0), tz=timezone.utc).isoformat() if c.get("created") else None}

def normalize_stripe_invoice(inv) -> dict:
    return {"external_id": inv.get("id"), "type": "invoice", "email": (inv.get("customer_email") or "").lower() or None,
            "status": inv.get("status"), "amount": (inv.get("amount_due") or 0) / 100.0, "currency": inv.get("currency"),
            "payment_status": "paid" if inv.get("paid") else (inv.get("status") or "open"),
            "ts": datetime.fromtimestamp(inv.get("created", 0), tz=timezone.utc).isoformat() if inv.get("created") else None}

def normalize_stripe_subscription(sub) -> dict:
    return {"external_id": sub.get("id"), "type": "subscription", "email": None,
            "status": sub.get("status"), "amount": None,
            "currency": (sub.get("items", {}).get("data", [{}])[0].get("price", {}) or {}).get("currency"),
            "customer": sub.get("customer"),
            "ts": datetime.fromtimestamp(sub.get("created", 0), tz=timezone.utc).isoformat() if sub.get("created") else None}

# ---- Google token helpers ----

async def _google_creds(tenant_id):
    doc = await db.google_credentials.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if not doc:
        return None
    return dec_secret(doc["enc"]), doc

async def _google_access_token(tenant_id):
    creds, doc = (await _google_creds(tenant_id)) or (None, None)
    if not creds:
        return None
    exp = creds.get("expires_at", 0)
    if datetime.now(timezone.utc).timestamp() < exp - 60:
        return creds["access_token"]
    # refresh
    if not creds.get("refresh_token"):
        return None
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": creds["refresh_token"], "grant_type": "refresh_token"})
    if r.status_code != 200:
        raise RuntimeError(f"token_refresh_failed:{r.status_code}")
    tok = r.json()
    creds["access_token"] = tok["access_token"]
    creds["expires_at"] = datetime.now(timezone.utc).timestamp() + tok.get("expires_in", 3600)
    await db.google_credentials.update_one({"tenant_id": tenant_id},
        {"$set": {"enc": enc_secret(creds), "updated_at": now_iso()}})
    return creds["access_token"]

# ---- Adapters (sync returns a normalized summary; bounded, idempotent upserts) ----

async def _upsert_comm(tenant_id, rec, contacts, actor_provider="gmail"):
    matched = [contacts[e] for e in ([rec.get("from_email")] + rec.get("to", [])) if e and e in contacts]
    contact_ids = list({m["id"] for m in matched})
    if not contact_ids:
        return False
    company_id = next((m.get("company_id") for m in matched if m.get("company_id")), None)
    ws_id = await _workspace_for_company(tenant_id, company_id)
    doc = {"tenant_id": tenant_id, "provider": actor_provider, "external_id": rec["external_id"],
           "thread_id": rec.get("thread_id"), "subject": rec["subject"], "from_email": rec.get("from_email"),
           "to": rec.get("to"), "snippet": rec.get("snippet"), "labels": rec.get("labels"), "ts": rec.get("ts"),
           "contact_ids": contact_ids, "company_id": company_id, "workspace_id": ws_id, "source": "external",
           "synced_at": now_iso()}
    await db.crm_communications.update_one(
        {"tenant_id": tenant_id, "provider": actor_provider, "external_id": rec["external_id"]},
        {"$set": doc, "$setOnInsert": {"id": new_id("comm")}}, upsert=True)
    return True

async def sync_gmail(tenant_id, actor):
    token = await _google_access_token(tenant_id)
    if not token:
        raise RuntimeError("not_connected")
    contacts = await _contacts_by_email(tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    matched = 0
    async with httpx.AsyncClient(timeout=25) as client:
        lst = await client.get("https://gmail.googleapis.com/gmail/v1/users/me/messages",
                               params={"maxResults": 25}, headers=headers)
        if lst.status_code == 429:
            raise RuntimeError("rate_limited")
        lst.raise_for_status()
        for m in (lst.json().get("messages") or [])[:25]:
            gm = await client.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}",
                                  params={"format": "metadata", "metadataHeaders": ["From", "To", "Cc", "Subject"]},
                                  headers=headers)
            if gm.status_code != 200:
                continue
            if await _upsert_comm(tenant_id, normalize_gmail_message(gm.json()), contacts, "gmail"):
                matched += 1
    return {"scanned": 25, "matched": matched}

async def sync_calendar(tenant_id, actor):
    token = await _google_access_token(tenant_id)
    if not token:
        raise RuntimeError("not_connected")
    contacts = await _contacts_by_email(tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    matched = 0
    now = datetime.now(timezone.utc).isoformat()
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.get("https://www.googleapis.com/calendar/v3/calendars/primary/events",
                             params={"timeMin": now, "maxResults": 25, "singleEvents": "true", "orderBy": "startTime"},
                             headers=headers)
        if r.status_code == 429:
            raise RuntimeError("rate_limited")
        r.raise_for_status()
        for ev in (r.json().get("items") or [])[:25]:
            rec = normalize_calendar_event(ev)
            emails = rec["attendees"] + ([rec["organizer"]] if rec["organizer"] else [])
            mm = [contacts[e] for e in emails if e in contacts]
            if not mm:
                continue
            company_id = next((m.get("company_id") for m in mm if m.get("company_id")), None)
            ws_id = await _workspace_for_company(tenant_id, company_id)
            doc = {"tenant_id": tenant_id, "provider": "google_calendar", **rec,
                   "contact_ids": list({m["id"] for m in mm}), "company_id": company_id,
                   "workspace_id": ws_id, "source": "external", "synced_at": now_iso()}
            await db.crm_meetings.update_one(
                {"tenant_id": tenant_id, "external_id": rec["external_id"]},
                {"$set": doc, "$setOnInsert": {"id": new_id("mtg")}}, upsert=True)
            matched += 1
    return {"scanned": 25, "matched": matched}

async def sync_stripe(tenant_id, actor):
    key = os.environ.get("STRIPE_API_KEY")
    if not key:
        raise RuntimeError("not_connected")
    _stripe.api_key = key
    contacts = await _contacts_by_email(tenant_id)
    companies = {c["id"]: c for c in await db.companies.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(5000)}
    count = 0
    def match(email):
        c = contacts.get((email or "").lower())
        return (c["id"] if c else None, c.get("company_id") if c else None)
    for norm, items in [
        (normalize_stripe_customer, _stripe.Customer.list(limit=50).data),
        (normalize_stripe_invoice, _stripe.Invoice.list(limit=50).data),
        (normalize_stripe_subscription, _stripe.Subscription.list(limit=50).data),
    ]:
        for it in items:
            rec = norm(it)
            contact_id, company_id = match(rec.get("email"))
            ws_id = await _workspace_for_company(tenant_id, company_id)
            doc = {"tenant_id": tenant_id, "provider": "stripe", **rec, "contact_id": contact_id,
                   "company_id": company_id, "workspace_id": ws_id, "source": "external", "synced_at": now_iso()}
            await db.crm_billing.update_one(
                {"tenant_id": tenant_id, "type": rec["type"], "external_id": rec["external_id"]},
                {"$set": doc, "$setOnInsert": {"id": new_id("bill")}}, upsert=True)
            count += 1
    return {"scanned": count, "matched": count}

SYNC_FUNCS = {"gmail": sync_gmail, "google_calendar": sync_calendar, "stripe": sync_stripe}

async def run_sync(tenant_id, provider, actor):
    conn = await db.integration_connections.find_one({"tenant_id": tenant_id, "provider": provider}, {"_id": 0})
    if not conn or conn["status"] in ("disconnected", "revoked"):
        raise HTTPException(status_code=400, detail="Provider is not connected")
    await set_conn(tenant_id, provider, status="connecting")
    await record_event("integration.sync_started", "integration", provider, tenant_id, actor, payload={"provider": provider})
    log = {"id": new_id("synclog"), "tenant_id": tenant_id, "provider": provider, "started_at": now_iso(),
           "actor": actor, "attempts": 0, "status": "running", "result": None, "error": None}
    last_err = None
    for attempt in range(1, 4):  # bounded retries with backoff
        log["attempts"] = attempt
        try:
            summary = await SYNC_FUNCS[provider](tenant_id, actor)
            log.update({"status": "completed", "result": summary, "finished_at": now_iso()})
            await db.integration_sync_logs.insert_one(dict(log))
            await set_conn(tenant_id, provider, status="active", last_sync_at=now_iso(),
                           last_success_at=now_iso(), last_error=None)
            await record_event("integration.sync_completed", "integration", provider, tenant_id, actor, payload=summary)
            return {**summary, "status": "completed"}
        except HTTPException:
            raise
        except Exception as e:
            last_err = str(e)[:300]
            if "rate_limited" in last_err:
                await asyncio.sleep(min(2 ** attempt, 5))
                continue
            if "not_connected" in last_err:
                break
            await asyncio.sleep(min(0.5 * attempt, 2))
    log.update({"status": "failed", "error": last_err, "finished_at": now_iso()})
    await db.integration_sync_logs.insert_one(dict(log))
    status = "expired" if last_err and "token_refresh_failed" in last_err else "degraded"
    await set_conn(tenant_id, provider, status=status, last_sync_at=now_iso(), last_error=last_err)
    await record_event("integration.sync_failed", "integration", provider, tenant_id, actor,
                       payload={"provider": provider, "error": last_err})
    return {"status": "failed", "error": last_err}
