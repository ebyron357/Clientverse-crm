"""Integration connection, OAuth, sync and activity routes."""
import os
import secrets
import base64
import hashlib
import httpx
import stripe as _stripe
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Request, Depends, Query
from fastapi.responses import RedirectResponse

from app.shared import (db, new_id, now_iso, record_event, get_current_user,
                        require_role, FRONTEND_URL)
from app.services.integrations import (PROVIDERS, SAFE_CONN_FIELDS, ensure_connections,
                                       set_conn, enc_secret, dec_secret, run_sync,
                                       GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
                                       GOOGLE_REDIRECT_URI, GOOGLE_SCOPES)

router = APIRouter(prefix="/api")

@router.get("/integrations/connections")
async def list_connections(user=Depends(get_current_user)):
    await ensure_connections(user["tenant_id"])
    rows = await db.integration_connections.find({"tenant_id": user["tenant_id"]}, SAFE_CONN_FIELDS).to_list(50)
    return rows

@router.post("/integrations/google/connect")
async def google_connect(user=Depends(require_role("admin"))):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.")
    await ensure_connections(user["tenant_id"])
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    await db.oauth_states.insert_one({"state": state, "tenant_id": user["tenant_id"], "actor": user["email"],
        "code_verifier": verifier, "created_at": now_iso(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()})
    for p in ("gmail", "google_calendar"):
        await set_conn(user["tenant_id"], p, status="connecting")
    params = {"client_id": GOOGLE_CLIENT_ID, "redirect_uri": GOOGLE_REDIRECT_URI, "response_type": "code",
              "scope": " ".join(GOOGLE_SCOPES), "access_type": "offline", "prompt": "consent",
              "include_granted_scopes": "true", "state": state,
              "code_challenge": challenge, "code_challenge_method": "S256"}
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return {"authorization_url": url}

@router.get("/integrations/google/callback")
async def google_callback(state: str = Query(None), code: str = Query(None), error: str = Query(None)):
    dest = f"{FRONTEND_URL}/registries?tab=integrations"
    st = await db.oauth_states.find_one({"state": state}, {"_id": 0}) if state else None
    if error or not st or not code:
        return RedirectResponse(url=f"{dest}&oauth=error")
    try:
        exp_dt = datetime.fromisoformat(st["expires_at"])
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        if exp_dt < datetime.now(timezone.utc):
            return RedirectResponse(url=f"{dest}&oauth=expired")
    except Exception:
        pass
    await db.oauth_states.delete_one({"state": state})
    tenant_id, actor = st["tenant_id"], st["actor"]
    async with httpx.AsyncClient(timeout=20) as client:
        tr = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET, "code": code,
            "grant_type": "authorization_code", "redirect_uri": GOOGLE_REDIRECT_URI,
            "code_verifier": st["code_verifier"]})
        if tr.status_code != 200:
            for p in ("gmail", "google_calendar"):
                await set_conn(tenant_id, p, status="error", last_error="token_exchange_failed")
            return RedirectResponse(url=f"{dest}&oauth=error")
        tok = tr.json()
        ui = await client.get("https://www.googleapis.com/oauth2/v2/userinfo",
                              headers={"Authorization": f"Bearer {tok['access_token']}"})
    email = ui.json().get("email") if ui.status_code == 200 else None
    creds = {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token"),
             "expires_at": datetime.now(timezone.utc).timestamp() + tok.get("expires_in", 3600),
             "scopes": tok.get("scope", "").split()}
    ver_doc = await db.google_credentials.find_one({"tenant_id": tenant_id}, {"_id": 0, "credential_version": 1})
    version = ((ver_doc or {}).get("credential_version") or 0) + 1
    await db.google_credentials.update_one({"tenant_id": tenant_id},
        {"$set": {"enc": enc_secret(creds), "account_email": email, "credential_version": version, "updated_at": now_iso()}}, upsert=True)
    for p in ("gmail", "google_calendar"):
        await set_conn(tenant_id, p, status="active", account_identity=email, scopes=GOOGLE_SCOPES,
                       connected_by=actor, connected_at=now_iso(), revoked_at=None, last_error=None, credential_version=version)
        await record_event("integration.connected", "integration", p, tenant_id, actor, payload={"provider": p, "account": email})
    return RedirectResponse(url=f"{dest}&oauth=connected")

@router.post("/integrations/stripe/connect")
async def stripe_connect(user=Depends(require_role("admin"))):
    key = os.environ.get("STRIPE_API_KEY")
    if not key:
        raise HTTPException(status_code=400, detail="Stripe is not configured (STRIPE_API_KEY).")
    await ensure_connections(user["tenant_id"])
    _stripe.api_key = key
    try:
        acct = _stripe.Account.retrieve()
        identity = acct.get("email") or acct.get("id")
    except Exception as e:
        await set_conn(user["tenant_id"], "stripe", status="error", last_error=str(e)[:200])
        raise HTTPException(status_code=400, detail="Could not verify Stripe account")
    version = 1
    await set_conn(user["tenant_id"], "stripe", status="active", account_identity=identity,
                   scopes=["read:customers", "read:invoices", "read:subscriptions"], connected_by=user["email"],
                   connected_at=now_iso(), revoked_at=None, last_error=None, credential_version=version)
    await record_event("integration.connected", "integration", "stripe", user["tenant_id"], user["email"], payload={"account": identity})
    return {"ok": True, "account": identity}

@router.post("/integrations/{provider}/disconnect")
async def disconnect_provider(provider: str, user=Depends(require_role("admin"))):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")
    if provider in ("gmail", "google_calendar"):
        creds = await db.google_credentials.find_one({"tenant_id": user["tenant_id"]}, {"_id": 0})
        if creds:
            try:
                tok = dec_secret(creds["enc"]).get("refresh_token") or dec_secret(creds["enc"]).get("access_token")
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post("https://oauth2.googleapis.com/revoke", params={"token": tok})
            except Exception:
                pass
        if not await db.integration_connections.find_one({"tenant_id": user["tenant_id"], "provider": ("google_calendar" if provider == "gmail" else "gmail"), "status": "active"}):
            await db.google_credentials.delete_one({"tenant_id": user["tenant_id"]})
    await set_conn(user["tenant_id"], provider, status="disconnected", account_identity=None, scopes=[],
                   revoked_at=now_iso())
    await record_event("integration.disconnected", "integration", provider, user["tenant_id"], user["email"], payload={"provider": provider})
    return {"ok": True}

@router.post("/integrations/{provider}/sync")
async def sync_provider(provider: str, user=Depends(require_role("admin"))):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")
    return await run_sync(user["tenant_id"], provider, user["email"])

@router.get("/integrations/sync-logs")
async def integration_sync_logs(user=Depends(require_role("admin"))):
    return await db.integration_sync_logs.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("started_at", -1).to_list(50)

@router.get("/integrations/workspaces/{ws_id}/activity")
async def workspace_activity(ws_id: str, user=Depends(get_current_user)):
    ws = await db.workspaces.find_one({"id": ws_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    comms = await db.crm_communications.find({"tenant_id": user["tenant_id"], "workspace_id": ws_id}, {"_id": 0}).sort("ts", -1).to_list(25)
    meetings = await db.crm_meetings.find({"tenant_id": user["tenant_id"], "workspace_id": ws_id}, {"_id": 0}).sort("start", 1).to_list(25)
    billing = await db.crm_billing.find({"tenant_id": user["tenant_id"], "workspace_id": ws_id}, {"_id": 0}).sort("ts", -1).to_list(50)
    conns = await db.integration_connections.find({"tenant_id": user["tenant_id"]}, SAFE_CONN_FIELDS).to_list(50)
    return {"communications": comms, "meetings": meetings, "billing": billing, "connections": conns}
