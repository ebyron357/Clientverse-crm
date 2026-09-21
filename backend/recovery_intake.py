"""Intake for the recovery sources that do not originate inside this CRM.

Three of the new detector families read records nothing in ClientVerse creates: a
missed call comes from a phone system, a web enquiry from a website form, and an
external CRM event from another vendor's product. Without somewhere to put them the
detectors would be looking at permanently empty collections, which is a detector in
name only.

WHAT THIS DELIBERATELY DOES NOT DO

Intake records a fact. It does not open a recovery case, compose a strategy, or send
anything. The detector sweep picks these records up on its next pass and takes them
through the same pipeline as every other source. Letting intake create cases directly
would give an unauthenticated caller a way to inject work into the recovery engine,
which is precisely the door this design keeps shut.

AUTHENTICATION

Two doors, and they are different on purpose:

* **The signed-in door.** An operator or a customer's own backend posts with a session.
  Ordinary tenant authentication, ordinary tenant scoping.
* **The website door.** A web form has no session, so a tenant mints an intake token.
  The token is stored hashed, is revocable, names the tenant it belongs to, and can do
  exactly one thing: file a web enquiry. It cannot read anything, cannot reach any other
  record, and cannot create a recovery case.

Every intake path is idempotent on the caller's own `external_id` where one is given,
so a phone system retrying a webhook does not produce two missed calls.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

import detectors

INTAKE_TOKENS = "intake_tokens"

# A web form is an open door, so what comes through it is bounded hard.
MAX_MESSAGE = 4000
MAX_FIELD = 300


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def ensure_indexes(db) -> None:
    await db[INTAKE_TOKENS].create_index("token_hash", unique=True)
    await db[INTAKE_TOKENS].create_index([("tenant_id", 1), ("status", 1)])


class CallLogInput(BaseModel):
    direction: str = Field(pattern="^(inbound|outbound)$")
    from_number: Optional[str] = Field(default=None, max_length=40)
    to_number: Optional[str] = Field(default=None, max_length=40)
    outcome: str = Field(max_length=40)
    occurred_at: Optional[str] = None
    duration_seconds: Optional[int] = Field(default=None, ge=0, le=86400)
    external_id: Optional[str] = Field(default=None, max_length=200)
    contact_id: Optional[str] = None
    recording_url: Optional[str] = Field(default=None, max_length=1000)
    provider: Optional[str] = Field(default=None, max_length=80)


class WebEnquiryInput(BaseModel):
    name: Optional[str] = Field(default=None, max_length=MAX_FIELD)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=40)
    message: Optional[str] = Field(default=None, max_length=MAX_MESSAGE)
    source_page: Optional[str] = Field(default=None, max_length=1000)
    estimated_value: Optional[float] = Field(default=None, ge=0)
    external_id: Optional[str] = Field(default=None, max_length=200)


class ExternalEventInput(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    kind: str = Field(min_length=1, max_length=80)
    external_id: str = Field(min_length=1, max_length=200)
    occurred_at: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=MAX_FIELD)
    summary: Optional[str] = Field(default=None, max_length=1000)
    contact_email: Optional[str] = Field(default=None, max_length=MAX_FIELD)
    contact_phone: Optional[str] = Field(default=None, max_length=40)
    external_contact_id: Optional[str] = Field(default=None, max_length=200)
    value: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, max_length=8)


class IntakeTokenInput(BaseModel):
    label: str = Field(min_length=1, max_length=120)


def register_intake_routes(router, db, new_id, now_iso, record_event,
                           get_current_user, require_role):
    """Attach the intake surface, using the application's own helpers."""

    async def _insert_idempotent(collection: str, doc: dict, key: dict) -> dict:
        """Insert, or return what is already there for the caller's own id.

        A phone system or a CRM webhook that retries must not produce two records, and
        answering the retry with the original is how the caller learns that.
        """
        try:
            await db[collection].insert_one(dict(doc))
        except Exception as exc:
            if getattr(exc, "code", None) == 11000 or "E11000" in str(exc):
                existing = await db[collection].find_one(key, {"_id": 0})
                if existing:
                    return {**existing, "deduplicated": True}
            raise
        return {**{k: v for k, v in doc.items() if k != "_id"}, "deduplicated": False}

    # ------------------------------------------------------------------ call logs

    @router.post("/intake/calls")
    async def record_call(inp: CallLogInput, user=Depends(get_current_user)):
        """File a call. A missed one becomes a recovery case on the next sweep."""
        doc = {
            "id": new_id("call"), "tenant_id": user["tenant_id"],
            "direction": inp.direction, "from_number": (inp.from_number or "").strip(),
            "to_number": (inp.to_number or "").strip(), "outcome": inp.outcome.lower(),
            "occurred_at": inp.occurred_at or now_iso(),
            "duration_seconds": inp.duration_seconds, "external_id": inp.external_id,
            "contact_id": inp.contact_id, "recording_url": inp.recording_url,
            "provider": inp.provider, "recorded_by": user["email"],
            "created_at": now_iso(),
        }
        if inp.contact_id:
            known = await db.contacts.find_one(
                {"id": inp.contact_id, "tenant_id": user["tenant_id"]}, {"_id": 1})
            if not known:
                raise HTTPException(status_code=422, detail="Unknown contact_id")
        result = await _insert_idempotent(
            detectors.CALL_LOGS, doc,
            {"tenant_id": user["tenant_id"], "external_id": inp.external_id})
        if not result.get("deduplicated"):
            await record_event("call.recorded", "call", result["id"], user["tenant_id"],
                               user["email"],
                               payload={"direction": inp.direction, "outcome": doc["outcome"]})
        return result

    @router.get("/intake/calls")
    async def list_calls(limit: int = 100, user=Depends(get_current_user)):
        return {"items": await db[detectors.CALL_LOGS].find(
            {"tenant_id": user["tenant_id"]}, {"_id": 0}
        ).sort("occurred_at", -1).to_list(max(1, min(int(limit or 100), 500)))}

    # -------------------------------------------------------------- web enquiries

    async def _file_enquiry(tenant_id: str, inp: WebEnquiryInput, *, actor: str,
                            channel: str) -> dict:
        doc = {
            "id": new_id("enq"), "tenant_id": tenant_id,
            "name": inp.name, "email": (str(inp.email).lower() if inp.email else None),
            "phone": inp.phone, "message": inp.message, "source_page": inp.source_page,
            "estimated_value": inp.estimated_value, "external_id": inp.external_id,
            "status": "new", "received_at": _now_iso(), "received_via": channel,
            "received_by": actor, "contact_id": None, "company_id": None,
            "created_at": _now_iso(),
        }
        result = await _insert_idempotent(
            detectors.WEB_ENQUIRIES, doc,
            {"tenant_id": tenant_id, "external_id": inp.external_id})
        if not result.get("deduplicated"):
            await record_event("web_enquiry.received", "web_enquiry", result["id"],
                               tenant_id, actor, payload={"via": channel})
        return result

    @router.post("/intake/web-enquiries")
    async def record_web_enquiry(inp: WebEnquiryInput, user=Depends(get_current_user)):
        return await _file_enquiry(user["tenant_id"], inp, actor=user["email"],
                                   channel="authenticated")

    @router.post("/intake/public/{token}/web-enquiries")
    async def record_public_web_enquiry(token: str, inp: WebEnquiryInput):
        """The website door.

        The token identifies the tenant and authorises exactly this one write. It reads
        nothing, returns nothing that was not just supplied, and cannot open a recovery
        case -- the detector sweep does that later, inside the tenant, on the same terms
        as every other source.
        """
        record = await db[INTAKE_TOKENS].find_one(
            {"token_hash": _hash(token), "status": "active"}, {"_id": 0})
        if not record:
            # The same answer for a revoked token, a wrong token and a token that never
            # existed: anything else confirms which.
            raise HTTPException(status_code=404, detail="Not found")
        if not (inp.email or inp.phone or inp.message):
            raise HTTPException(status_code=422,
                                detail="An enquiry needs at least an email, a phone number or a message")
        result = await _file_enquiry(record["tenant_id"], inp,
                                     actor=f"intake_token:{record['id']}",
                                     channel="public_form")
        await db[INTAKE_TOKENS].update_one(
            {"id": record["id"]},
            {"$set": {"last_used_at": _now_iso()}, "$inc": {"use_count": 1}})
        # Deliberately thin: the caller learns it was accepted and nothing about the
        # tenant behind the token.
        return {"accepted": True, "id": result["id"]}

    @router.get("/intake/web-enquiries")
    async def list_web_enquiries(status: Optional[str] = None, limit: int = 100,
                                 user=Depends(get_current_user)):
        query: dict[str, Any] = {"tenant_id": user["tenant_id"]}
        if status:
            query["status"] = status
        return {"items": await db[detectors.WEB_ENQUIRIES].find(query, {"_id": 0}).sort(
            "received_at", -1).to_list(max(1, min(int(limit or 100), 500)))}

    # ------------------------------------------------------------- intake tokens

    @router.get("/intake/tokens")
    async def list_intake_tokens(user=Depends(require_role("admin"))):
        """Tokens are listed by label and state. The secret itself is never readable
        again after the call that created it."""
        return {"items": await db[INTAKE_TOKENS].find(
            {"tenant_id": user["tenant_id"]},
            {"_id": 0, "token_hash": 0}).sort("created_at", -1).to_list(100)}

    @router.post("/intake/tokens")
    async def create_intake_token(inp: IntakeTokenInput,
                                  user=Depends(require_role("admin"))):
        token = secrets.token_urlsafe(32)
        doc = {"id": new_id("itk"), "tenant_id": user["tenant_id"], "label": inp.label,
               "token_hash": _hash(token), "status": "active", "use_count": 0,
               "last_used_at": None, "created_by": user["email"],
               "created_at": now_iso(), "revoked_at": None}
        await db[INTAKE_TOKENS].insert_one(doc)
        await record_event("intake_token.created", "intake_token", doc["id"],
                           user["tenant_id"], user["email"], payload={"label": inp.label})
        return {"token": doc["id"], "label": inp.label,
                # Returned exactly once. It is stored hashed, so nothing can show it again.
                "secret": token,
                "note": "Store this now. It is hashed at rest and cannot be shown again."}

    @router.post("/intake/tokens/{token_id}/revoke")
    async def revoke_intake_token(token_id: str, user=Depends(require_role("admin"))):
        result = await db[INTAKE_TOKENS].update_one(
            {"id": token_id, "tenant_id": user["tenant_id"], "status": "active"},
            {"$set": {"status": "revoked", "revoked_at": now_iso(),
                      "revoked_by": user["email"]}})
        if not result.matched_count:
            raise HTTPException(status_code=404, detail="Not found")
        await record_event("intake_token.revoked", "intake_token", token_id,
                           user["tenant_id"], user["email"])
        return {"ok": True}

    # ------------------------------------------------------- external CRM events

    @router.post("/intake/external-events")
    async def record_external_event(inp: ExternalEventInput,
                                    user=Depends(get_current_user)):
        """File an event another system reported.

        The identifiers it carries have not been verified by this CRM, so they are kept
        as evidence rather than attached as fact. Only the event kinds declared
        recoverable are ever turned into cases; anything else is stored and ignored,
        because an unknown event is not an opportunity.
        """
        doc = {
            "id": new_id("xev"), "tenant_id": user["tenant_id"],
            "provider": inp.provider, "kind": inp.kind, "external_id": inp.external_id,
            "occurred_at": inp.occurred_at or now_iso(), "title": inp.title,
            "summary": inp.summary, "contact_email": (inp.contact_email or "").lower() or None,
            "contact_phone": inp.contact_phone,
            "external_contact_id": inp.external_contact_id,
            "value": inp.value, "currency": (inp.currency or "").upper() or None,
            "status": "new",
            "recoverable": inp.kind in detectors.RECOVERABLE_EXTERNAL_KINDS,
            "recorded_by": user["email"], "created_at": now_iso(),
        }
        result = await _insert_idempotent(
            detectors.EXTERNAL_EVENTS, doc,
            {"tenant_id": user["tenant_id"], "provider": inp.provider,
             "external_id": inp.external_id})
        if not result.get("deduplicated"):
            await record_event("external_crm_event.received", "external_event",
                               result["id"], user["tenant_id"], user["email"],
                               payload={"provider": inp.provider, "kind": inp.kind,
                                        "recoverable": doc["recoverable"]})
        return result

    @router.get("/intake/external-events")
    async def list_external_events(limit: int = 100, user=Depends(get_current_user)):
        return {"items": await db[detectors.EXTERNAL_EVENTS].find(
            {"tenant_id": user["tenant_id"]}, {"_id": 0}
        ).sort("occurred_at", -1).to_list(max(1, min(int(limit or 100), 500)))}
