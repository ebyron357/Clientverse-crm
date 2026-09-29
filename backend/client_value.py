"""Tenant-scoped client-value CRM workflows.

This module intentionally keeps provider-dependent outcomes explicit. It coordinates
records, approvals, tasks, and in-app notices; it never sends Gmail, SMS, review, or
payment-provider traffic without a separately certified connection.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field, HttpUrl
from pymongo.errors import DuplicateKeyError

import approval_queue
from crm_core import MAX_MONEY
from crm_core import parse_date as crm_parse_date
from recovery_intake import _client_address, _take

# The portal request route is public: anyone holding a link can call it, and each call
# writes a request, an audit event, a critical in-app notice and a webhook delivery.
PORTAL_HOURLY_PER_LINK = 20
PORTAL_HOURLY_PER_CLIENT = 30
PORTAL_MAX_OPEN_PER_LINK = 50


class PortalLinkInput(BaseModel):
    workspace_id: str
    client_label: str = Field(min_length=2, max_length=120)
    expires_at: Optional[str] = None


class PortalRequestInput(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    priority: str = "medium"


class DocumentInput(BaseModel):
    workspace_id: str
    title: str = Field(min_length=2, max_length=200)
    kind: str = "document"
    external_url: Optional[HttpUrl] = None
    client_visible: bool = False
    requires_approval: bool = False


class RecordStatusInput(BaseModel):
    status: str


class EstimateLine(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    # Usage-priced lines run to millions of units (2.5M impressions at 0.004). The line
    # and estimate totals are bounded by MAX_MONEY, which is what matters.
    quantity: float = Field(default=1, gt=0, le=1_000_000_000_000, allow_inf_nan=False)
    unit_price: float = Field(default=0, ge=0, le=MAX_MONEY, allow_inf_nan=False)


class EstimateInput(BaseModel):
    workspace_id: str
    title: str = Field(min_length=2, max_length=200)
    currency: str = "USD"
    lines: list[EstimateLine] = Field(default_factory=list)
    valid_until: Optional[str] = None


class ReferralInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    source_type: str = "partner"
    company_id: Optional[str] = None
    contact_email: Optional[str] = None
    status: str = "active"


APPOINTMENT_STATUSES = ("scheduled", "confirmed", "completed", "no_show", "cancelled")
# Where an appointment may go next. Any-to-any let a member turn a completed visit into a
# no-show, which the no-show detector then chased as a recovery. Finished outcomes are
# final for members; an admin may correct one (`ADMIN_CORRECTIONS`).
APPOINTMENT_TRANSITIONS = {
    "scheduled": {"confirmed", "completed", "no_show", "cancelled"},
    "confirmed": {"scheduled", "completed", "no_show", "cancelled"},
    "completed": set(),
    "no_show": set(),
    "cancelled": set(),
}
APPOINTMENT_ADMIN_CORRECTIONS = {
    "completed": {"no_show"},
    "no_show": {"completed", "scheduled"},
    "cancelled": {"scheduled"},
}
# A reminder is prepared only for a booking that is still going to happen.
REMINDABLE_APPOINTMENT_STATUSES = ("scheduled", "confirmed")


class AppointmentInput(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    start_at: str
    end_at: str
    owner: Optional[str] = None
    workspace_id: Optional[str] = None
    company_id: Optional[str] = None
    # Who the appointment is with. The appointment detectors read it to know whom a
    # cancelled or missed booking should be followed up with.
    contact_id: Optional[str] = None
    appointment_type: str = "service"
    status: Literal["scheduled", "confirmed", "completed", "no_show", "cancelled"] = "scheduled"
    notes: Optional[str] = Field(default=None, max_length=1000)


class AppointmentPatch(BaseModel):
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=1000)


class CheckInInput(BaseModel):
    workspace_id: str
    note: Optional[str] = Field(default=None, max_length=1000)
    location_label: Optional[str] = Field(default=None, max_length=120)


class AutomationRuleInput(BaseModel):
    template: str
    enabled: bool = False
    workspace_id: Optional[str] = None
    owner: Optional[str] = None


class ReviewRequestInput(BaseModel):
    workspace_id: str
    contact_id: Optional[str] = None
    message: Optional[str] = Field(default=None, max_length=600)


class PlaybookApplyInput(BaseModel):
    workspace_id: str


AUTOMATION_TEMPLATES = {
    "new_lead_follow_up": {
        "label": "New-lead follow-up",
        "trigger": "Contact created",
        "task": "Review new lead and prepare a consent-aware follow-up draft",
    },
    "missed_appointment_recovery": {
        "label": "Missed-appointment recovery",
        "trigger": "Appointment marked no-show",
        "task": "Review no-show and prepare a recovery task; no outbound message is sent automatically",
    },
    "appointment_reminder": {
        "label": "Appointment reminder",
        "trigger": "Scheduled appointment",
        "task": "Confirm appointment readiness and prepare the reminder for human review",
    },
}

PLAYBOOKS = {
    "home_services": {
        "label": "Home services job handoff",
        "tasks": ["Confirm site access and arrival window", "Capture job photos and service notes", "Request customer completion acknowledgement"],
    },
    "real_estate": {
        "label": "Real-estate client journey",
        "tasks": ["Confirm next showing or milestone", "Prepare offer or listing document checklist", "Review client decision and follow-up owner"],
    },
    "coaching": {
        "label": "Coaching engagement",
        "tasks": ["Confirm session objective", "Capture action commitments", "Schedule accountability follow-up"],
    },
    "agency": {
        "label": "Agency delivery cadence",
        "tasks": ["Confirm campaign or sprint brief", "Collect client approval", "Review results and next recommendation"],
    },
}


async def ensure_indexes(db) -> None:
    """One live invoice per estimate. Its own try: a deployment that already holds
    duplicates from before this index must still boot, and says why it is missing."""
    # Appointment times as real instants, so the conflict check can be a range query.
    await db.appointments.create_index([("tenant_id", 1), ("owner", 1), ("start_ts", 1)])
    await backfill_appointment_instants(db)
    # One reminder task per appointment; only reminder tasks carry `appointment_id`.
    await db.tasks.create_index(
        [("tenant_id", 1), ("appointment_id", 1)], unique=True,
        partialFilterExpression={"appointment_id": {"$type": "string"}},
        name="one_reminder_per_appointment")
    # One application of a playbook per workspace. Keyed on a field only new applications
    # carry, so a deployment holding duplicates from before still boots.
    await db.playbook_applications.create_index(
        [("tenant_id", 1), ("application_key", 1)], unique=True,
        partialFilterExpression={"application_key": {"$type": "string"}})
    # Keyed on `active_estimate_id`, which a void clears: keyed on `estimate_id`, a
    # voided invoice blocked invoicing its estimate ever again.
    try:
        await db.invoices.drop_index("one_invoice_per_estimate")
    except Exception:
        pass  # never built, or already dropped
    await db.invoices.update_many(
        {"estimate_id": {"$type": "string"}, "status": {"$ne": "void"},
         "active_estimate_id": {"$exists": False}},
        [{"$set": {"active_estimate_id": "$estimate_id"}}])
    try:
        await db.invoices.create_index(
            [("tenant_id", 1), ("active_estimate_id", 1)], unique=True,
            partialFilterExpression={"active_estimate_id": {"$type": "string"}},
            name="one_live_invoice_per_estimate")
    except Exception:
        logging.getLogger("clientverse").exception(
            "Could not create the one-live-invoice-per-estimate index; several live "
            "invoices for one estimate already exist and all but one must be voided")


def appointment_instant(value) -> Optional[datetime]:
    """An appointment time as a UTC instant, or None when it cannot be read."""
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


async def backfill_appointment_instants(db, *, batch: int = 1000) -> int:
    """Give appointments stored before `start_ts`/`end_ts` existed their instants."""
    done = 0
    async for row in db.appointments.find({"start_ts": {"$exists": False}},
                                          {"_id": 1, "start_at": 1, "end_at": 1}).limit(50_000):
        start, end = appointment_instant(row.get("start_at")), appointment_instant(row.get("end_at"))
        await db.appointments.update_one({"_id": row["_id"]},
                                         {"$set": {"start_ts": start, "end_ts": end}})
        done += 1
    return done


# What an unauthenticated portal visitor may see of each record. Everything else --
# who created it, internal ids, notes -- stays inside the workspace.
PORTAL_FIELDS = {
    "commitments": ("id", "title", "status", "due_date"),
    "documents": ("id", "title", "kind", "status", "external_url"),
    "estimates": ("id", "title", "currency", "lines", "total", "status", "valid_until"),
    "invoices": ("id", "title", "currency", "lines", "total", "status", "payment_status"),
}


# Where an invoice or estimate may go next. Any-to-any let a paid invoice be moved back
# to draft and paid again, and an invoiced estimate be declined.
INVOICE_TRANSITIONS = {
    "draft": {"issued", "void"},
    "issued": {"paid", "overdue", "void"},
    "overdue": {"paid", "issued", "void"},
    "paid": {"void"},
    "void": set(),
}
ESTIMATE_TRANSITIONS = {
    "draft": {"sent", "expired"},
    "sent": {"approved", "declined", "expired", "draft"},
    "approved": {"expired"},
    "declined": set(),
    "expired": {"draft"},
}


def _check_move(kind: str, table: dict, current: Optional[str], target: str) -> None:
    current = current or "draft"
    if target == current:
        return
    if target not in table.get(current, set()):
        raise HTTPException(status_code=409,
                            detail=f"A {current} {kind} cannot be moved to {target}")


def portal_view(kind: str, record: dict) -> dict:
    return {field: record.get(field) for field in PORTAL_FIELDS[kind] if field in record}


def was_paid(invoice: Optional[dict]) -> bool:
    return bool(invoice) and "paid" in (str(invoice.get("status") or "").lower(),
                                         str(invoice.get("payment_status") or "").lower())


async def stamp_paid_at(db, *, tenant_id: str, invoice_id: str, at: str,
                        previously_paid: bool) -> None:
    """Record when an invoice became paid -- only on the move into paid, and only once.

    Attribution dates a payment by this field. An invoice that was already paid before
    this call keeps whatever it has: one paid before payment dates were kept has none,
    and re-saving it must not date that old payment to today, after this week's
    outreach. It stays undated, and the ledger asks for an operator confirmation.
    """
    if previously_paid:
        return
    await db.invoices.update_one(
        {"id": invoice_id, "tenant_id": tenant_id, "paid_at": None,
         "$or": [{"status": "paid"}, {"payment_status": "paid"}]},
        {"$set": {"paid_at": at}})


def register_client_value_routes(router, db, new_id, now_iso, record_event, assert_workspace, get_current_user, require_role):
    """Attach client-value routes to the existing API router with injected app helpers."""

    async def visible_workspace(user, workspace_id):
        return await assert_workspace(user, workspace_id)

    async def in_app_notice(tenant_id, title, body, workspace_id=None, category="critical"):
        await db.notifications.insert_one({
            "id": new_id("ntf"), "tenant_id": tenant_id, "user_id": None,
            "workspace_id": workspace_id, "type": category, "severity": "info",
            "source": "client_value", "title": title, "body": body,
            "deep_link": f"/workspaces/{workspace_id}" if workspace_id else "/client-ops",
            "read": False, "created_at": now_iso(),
        })

    def clean(document):
        return {k: v for k, v in document.items() if k not in ("_id", "tenant_id", "token_hash")}

    async def workspace_company(tenant_id, workspace_id):
        workspace = await db.workspaces.find_one({"tenant_id": tenant_id, "id": workspace_id}, {"_id": 0})
        company = None
        if workspace and workspace.get("company_id"):
            company = await db.companies.find_one({"tenant_id": tenant_id, "id": workspace["company_id"]}, {"_id": 0})
        return workspace, company

    @router.get("/client-ops/summary")
    async def client_ops_summary(user=Depends(get_current_user)):
        tenant_id = user["tenant_id"]
        documents = await db.client_documents.count_documents({"tenant_id": tenant_id})
        estimates = await db.estimates.count_documents({"tenant_id": tenant_id, "status": {"$in": ["draft", "sent", "approved"]}})
        invoices = await db.invoices.count_documents({"tenant_id": tenant_id, "status": {"$in": ["draft", "issued", "overdue"]}})
        appointments = await db.appointments.count_documents({"tenant_id": tenant_id, "status": {"$in": ["scheduled", "confirmed"]}})
        reviews = await db.review_requests.count_documents({"tenant_id": tenant_id, "status": "ready_for_review"})
        return {"documents": documents, "active_estimates": estimates, "open_invoices": invoices,
                "scheduled_appointments": appointments, "reviews_awaiting_human_send": reviews,
                "provider_note": "Provider-dependent delivery and payments remain disabled until their integrations are configured and certified."}

    @router.get("/portal-links")
    async def list_portal_links(user=Depends(require_role("admin"))):
        rows = await db.portal_links.find({"tenant_id": user["tenant_id"]}, {"_id": 0, "token_hash": 0}).sort("created_at", -1).to_list(500)
        return rows

    @router.post("/portal-links")
    async def create_portal_link(inp: PortalLinkInput, user=Depends(require_role("admin"))):
        await visible_workspace(user, inp.workspace_id)
        raw = secrets.token_urlsafe(32)
        doc = {"id": new_id("portal"), "tenant_id": user["tenant_id"], "workspace_id": inp.workspace_id,
               "client_label": inp.client_label, "token_hash": hashlib.sha256(raw.encode()).hexdigest(),
               "status": "active", "expires_at": inp.expires_at, "created_by": user["email"], "created_at": now_iso()}
        await db.portal_links.insert_one(doc)
        await record_event("portal.link_created", "portal_link", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id,
                           payload={"client_label": inp.client_label})
        return {"portal_link": clean(doc), "portal_token": raw, "portal_path": f"/portal/{raw}",
                "security_note": "The portal token is returned only at creation. Store it securely; it is not returned by list endpoints."}

    @router.patch("/portal-links/{link_id}")
    async def update_portal_link(link_id: str, inp: RecordStatusInput, user=Depends(require_role("admin"))):
        if inp.status not in ("active", "revoked"):
            raise HTTPException(status_code=422, detail="Portal link status must be active or revoked")
        result = await db.portal_links.update_one({"id": link_id, "tenant_id": user["tenant_id"]}, {"$set": {"status": inp.status, "updated_at": now_iso()}})
        if not result.matched_count:
            raise HTTPException(status_code=404, detail="Portal link not found")
        await record_event("portal.link_updated", "portal_link", link_id, user["tenant_id"], user["email"], payload={"status": inp.status})
        return {"ok": True, "status": inp.status}

    async def public_portal(token: str):
        link = await db.portal_links.find_one({"token_hash": hashlib.sha256(token.encode()).hexdigest(), "status": "active"}, {"_id": 0})
        if not link:
            raise HTTPException(status_code=404, detail="Portal link is unavailable")
        if link.get("expires_at"):
            try:
                expires = datetime.fromisoformat(link["expires_at"])
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires < datetime.now(timezone.utc):
                    raise HTTPException(status_code=410, detail="Portal link has expired")
            except ValueError:
                raise HTTPException(status_code=410, detail="Portal link has expired")
        return link

    @router.get("/portal/{token}")
    async def get_client_portal(token: str):
        link = await public_portal(token)
        workspace, company = await workspace_company(link["tenant_id"], link["workspace_id"])
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace no longer exists")
        docs = await db.client_documents.find({"tenant_id": link["tenant_id"], "workspace_id": link["workspace_id"], "client_visible": True, "status": {"$in": ["approved", "shared"]}}, {"_id": 0}).to_list(200)
        estimates = await db.estimates.find({"tenant_id": link["tenant_id"], "workspace_id": link["workspace_id"], "status": {"$in": ["sent", "approved"]}}, {"_id": 0}).to_list(100)
        invoices = await db.invoices.find({"tenant_id": link["tenant_id"], "workspace_id": link["workspace_id"], "status": {"$in": ["issued", "paid", "overdue"]}}, {"_id": 0}).to_list(100)
        # Only commitments an admin chose to share. They are internal by default: a
        # member's note ("client is a late payer") must not reach the client unseen.
        commitments = await db.commitments.find({"tenant_id": link["tenant_id"], "workspace_id": link["workspace_id"], "client_visible": True}, {"_id": 0}).sort("due_date", 1).to_list(100)
        return {"client_label": link["client_label"], "workspace": {"name": workspace["name"], "stage": workspace.get("stage")},
                "company": {"name": (company or {}).get("name")},
                "commitments": [portal_view("commitments", v) for v in commitments],
                "documents": [portal_view("documents", v) for v in docs],
                "estimates": [portal_view("estimates", v) for v in estimates],
                "invoices": [portal_view("invoices", v) for v in invoices],
                "capability_note": "This portal supports read-only status and client requests. Billing, signatures, and messages remain provider-dependent and require human review."}

    @router.post("/portal/{token}/requests")
    async def portal_request(token: str, inp: PortalRequestInput, request: Request):
        link = await public_portal(token)
        hour = timedelta(hours=1)
        if not await _take(db, f"portal:link:{link['id']}", PORTAL_HOURLY_PER_LINK, hour) or \
                not await _take(db, f"portal:ip:{_client_address(request)}",
                                PORTAL_HOURLY_PER_CLIENT, hour):
            raise HTTPException(status_code=429, detail="Too many requests; try again later")
        if await db.client_requests.count_documents(
                {"tenant_id": link["tenant_id"], "portal_link_id": link["id"],
                 "status": "open"}) >= PORTAL_MAX_OPEN_PER_LINK:
            raise HTTPException(status_code=429,
                                detail="This portal already has many open requests awaiting a reply")
        doc = {"id": new_id("req"), "tenant_id": link["tenant_id"], "workspace_id": link["workspace_id"], "title": inp.title,
               "priority": inp.priority if inp.priority in ("low", "medium", "high") else "medium", "status": "open", "source": "portal",
               "portal_link_id": link["id"], "created_at": now_iso()}
        await db.client_requests.insert_one(doc)
        await record_event("portal.request_created", "client_request", doc["id"], link["tenant_id"], "portal", workspace_id=link["workspace_id"], payload={"title": inp.title})
        await in_app_notice(link["tenant_id"], "New portal request", inp.title, link["workspace_id"])
        return {"ok": True, "request": clean(doc)}

    @router.get("/documents")
    async def list_documents(workspace_id: Optional[str] = None, user=Depends(get_current_user)):
        if workspace_id:
            await visible_workspace(user, workspace_id)
        query = {"tenant_id": user["tenant_id"]}
        if workspace_id:
            query["workspace_id"] = workspace_id
        return [clean(row) for row in await db.client_documents.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)]

    @router.post("/documents")
    async def create_document(inp: DocumentInput, user=Depends(get_current_user)):
        await visible_workspace(user, inp.workspace_id)
        status = "pending_approval" if inp.requires_approval else "draft"
        doc = {"id": new_id("doc"), "tenant_id": user["tenant_id"], "workspace_id": inp.workspace_id, "title": inp.title,
               "kind": inp.kind, "external_url": str(inp.external_url) if inp.external_url else None, "client_visible": inp.client_visible,
               "requires_approval": inp.requires_approval, "status": status, "created_by": user["email"], "created_at": now_iso()}
        await db.client_documents.insert_one(dict(doc))
        if inp.requires_approval:
            # Through the approval queue, so the request has an expiry and an audit trail,
            # and deciding it actually shares (or withholds) the document.
            approval = await approval_queue.request(
                db, tenant_id=user["tenant_id"], title=f"Approve document: {inp.title}",
                kind="document_share", actor=user["email"],
                requester_kind=approval_queue.REQUESTER_HUMAN,
                summary=f"Share '{inp.title}' with the client in the portal.",
                action={"type": "document_share", "document_id": doc["id"]},
                subject_type="client_document", subject_id=doc["id"],
                workspace_id=inp.workspace_id)
            await db.client_documents.update_one(
                {"id": doc["id"], "tenant_id": user["tenant_id"]},
                {"$set": {"approval_id": approval["id"]}})
            doc["approval_id"] = approval["id"]
        await record_event("document.created", "document", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"title": inp.title, "status": status})
        return clean(doc)

    @router.patch("/documents/{document_id}")
    async def update_document(document_id: str, inp: RecordStatusInput, user=Depends(require_role("admin"))):
        if inp.status not in ("draft", "pending_approval", "approved", "shared", "archived"):
            raise HTTPException(status_code=422, detail="Unsupported document status")
        result = await db.client_documents.update_one({"id": document_id, "tenant_id": user["tenant_id"]}, {"$set": {"status": inp.status, "updated_at": now_iso()}})
        if not result.matched_count:
            raise HTTPException(status_code=404, detail="Document not found")
        return {"ok": True, "status": inp.status}

    @router.get("/estimates")
    async def list_estimates(workspace_id: Optional[str] = None, user=Depends(get_current_user)):
        if workspace_id:
            await visible_workspace(user, workspace_id)
        query = {"tenant_id": user["tenant_id"]}
        if workspace_id:
            query["workspace_id"] = workspace_id
        return [clean(row) for row in await db.estimates.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)]

    @router.post("/estimates")
    async def create_estimate(inp: EstimateInput, user=Depends(require_role("admin"))):
        await visible_workspace(user, inp.workspace_id)
        lines = [{"label": line.label, "quantity": line.quantity, "unit_price": line.unit_price, "total": round(line.quantity * line.unit_price, 2)} for line in inp.lines]
        total = round(sum(line["total"] for line in lines), 2)
        if total > MAX_MONEY:
            raise HTTPException(status_code=422, detail=f"An estimate total cannot exceed {MAX_MONEY:,}")
        doc = {"id": new_id("est"), "tenant_id": user["tenant_id"], "workspace_id": inp.workspace_id, "title": inp.title,
               "currency": inp.currency.upper(), "lines": lines, "total": total,
               "valid_until": crm_parse_date(inp.valid_until, "valid_until"), "status": "draft",
               "created_by": user["email"], "created_at": now_iso()}
        await db.estimates.insert_one(doc)
        await record_event("estimate.created", "estimate", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"title": inp.title, "total": total})
        return clean(doc)

    @router.patch("/estimates/{estimate_id}")
    async def update_estimate(estimate_id: str, inp: RecordStatusInput, user=Depends(require_role("admin"))):
        if inp.status not in ESTIMATE_TRANSITIONS:
            raise HTTPException(status_code=422, detail="Unsupported estimate status")
        estimate = await db.estimates.find_one({"id": estimate_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not estimate:
            raise HTTPException(status_code=404, detail="Estimate not found")
        _check_move("estimate", ESTIMATE_TRANSITIONS, estimate.get("status"), inp.status)
        if inp.status in ("declined", "expired", "draft") and await db.invoices.find_one(
                {"tenant_id": user["tenant_id"], "estimate_id": estimate_id,
                 "status": {"$ne": "void"}}, {"_id": 1}):
            raise HTTPException(status_code=409,
                                detail="This estimate has been invoiced; void the invoice first")
        result = await db.estimates.update_one(
            {"id": estimate_id, "tenant_id": user["tenant_id"], "status": estimate.get("status")},
            {"$set": {"status": inp.status, "updated_at": now_iso()}})
        if not result.matched_count:
            raise HTTPException(status_code=409, detail="The estimate changed; reload it")
        return {"ok": True, "status": inp.status}

    @router.post("/estimates/{estimate_id}/invoice")
    async def create_invoice_from_estimate(estimate_id: str, user=Depends(require_role("admin"))):
        estimate = await db.estimates.find_one({"id": estimate_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not estimate:
            raise HTTPException(status_code=404, detail="Estimate not found")
        if estimate.get("status") not in ("approved", "sent"):
            raise HTTPException(status_code=400, detail="Only sent or approved estimates can be converted")
        live = {"tenant_id": user["tenant_id"], "estimate_id": estimate_id, "status": {"$ne": "void"}}
        existing = await db.invoices.find_one(live, {"_id": 0})
        if existing:
            return {"invoice": clean(existing), "duplicate": True}
        invoice = {"id": new_id("inv"), "tenant_id": user["tenant_id"], "workspace_id": estimate["workspace_id"], "estimate_id": estimate_id,
                   "active_estimate_id": estimate_id,
                   "title": estimate["title"], "currency": estimate["currency"], "lines": estimate["lines"], "total": estimate["total"],
                   "status": "draft", "payment_status": "requires_stripe_configuration", "created_at": now_iso()}
        try:
            await db.invoices.insert_one(dict(invoice))
        except Exception as exc:
            # A second click or a retry racing the first: the unique index lets exactly
            # one invoice exist for the estimate, and the loser returns that one.
            if getattr(exc, "code", None) != 11000 and "E11000" not in str(exc):
                raise
            winner = await db.invoices.find_one(live, {"_id": 0})
            return {"invoice": clean(winner or invoice), "duplicate": True}
        await record_event("invoice.created", "invoice", invoice["id"], user["tenant_id"], user["email"], workspace_id=invoice["workspace_id"], payload={"estimate_id": estimate_id, "total": invoice["total"]})
        return {"invoice": clean(invoice), "duplicate": False, "provider_note": "Invoice created locally. Payment collection is unavailable until Stripe lifecycle certification passes."}

    @router.get("/invoices")
    async def list_invoices(workspace_id: Optional[str] = None, user=Depends(get_current_user)):
        if workspace_id:
            await visible_workspace(user, workspace_id)
        query = {"tenant_id": user["tenant_id"]}
        if workspace_id:
            query["workspace_id"] = workspace_id
        return [clean(row) for row in await db.invoices.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)]

    @router.patch("/invoices/{invoice_id}")
    async def update_invoice(invoice_id: str, inp: RecordStatusInput, user=Depends(require_role("admin"))):
        if inp.status not in INVOICE_TRANSITIONS:
            raise HTTPException(status_code=422, detail="Unsupported invoice status")
        invoice = await db.invoices.find_one({"id": invoice_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")
        unset: dict = {}
        if invoice.get("status") == "paid" and inp.status == "issued":
            update = await manual_payment_correction(user, invoice)
            unset = {"paid_at": ""}
        else:
            _check_move("invoice", INVOICE_TRANSITIONS, invoice.get("status"), inp.status)
            update = {"status": inp.status, "updated_at": now_iso()}
        if inp.status == "paid" and invoice.get("payment_status") != "paid":
            # Recorded by a person, so the payment status says so rather than keeping a
            # provider state ("requires_stripe_configuration") that contradicts it.
            update.update({"payment_status": "paid", "payment_source": "manual",
                           "payment_status_before_manual": invoice.get("payment_status")})
        if inp.status == "void":
            # Frees the estimate to be invoiced again.
            unset["active_estimate_id"] = ""
        result = await db.invoices.update_one(
            {"id": invoice_id, "tenant_id": user["tenant_id"], "status": invoice.get("status")},
            {"$set": update, **({"$unset": unset} if unset else {})})
        if not result.matched_count:
            raise HTTPException(status_code=409, detail="The invoice changed; reload it")
        if inp.status == "paid":
            await stamp_paid_at(db, tenant_id=user["tenant_id"], invoice_id=invoice_id,
                                at=now_iso(), previously_paid=was_paid(invoice))
        return {"ok": True, "status": inp.status}

    async def manual_payment_correction(user, invoice):
        """Undo a payment a person recorded by mistake: paid -> issued.

        Only a manual payment (a provider's is the provider's record, not ours to undo),
        and only while the attribution ledger has not booked it -- un-paying a booked
        invoice would leave recovered revenue claimed on money that never arrived.
        """
        if invoice.get("payment_source") != "manual":
            raise HTTPException(status_code=409,
                                detail="Only a payment recorded by hand can be corrected here")
        booked = await db.attribution_entries.find_one(
            {"tenant_id": user["tenant_id"], "booked_record": f"invoices:{invoice['id']}",
             "duplicate_of": None}, {"_id": 0, "id": 1})
        if booked:
            raise HTTPException(status_code=409,
                                detail="This payment is booked in the attribution ledger; it "
                                       "cannot be undone here")
        return {"status": "issued", "updated_at": now_iso(),
                "payment_status": invoice.get("payment_status_before_manual") or "unpaid",
                "payment_source": None, "payment_corrected_by": user["email"],
                "payment_corrected_at": now_iso()}

    @router.get("/referrals")
    async def list_referrals(user=Depends(get_current_user)):
        return [clean(row) for row in await db.referrals.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("created_at", -1).to_list(1000)]

    @router.post("/referrals")
    async def create_referral(inp: ReferralInput, user=Depends(get_current_user)):
        if inp.company_id:
            company = await db.companies.find_one({"id": inp.company_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")
        doc = {"id": new_id("ref"), "tenant_id": user["tenant_id"], "name": inp.name, "source_type": inp.source_type,
               "company_id": inp.company_id, "contact_email": inp.contact_email, "status": inp.status, "created_at": now_iso()}
        await db.referrals.insert_one(doc)
        await record_event("referral.created", "referral", doc["id"], user["tenant_id"], user["email"], payload={"name": inp.name, "source_type": inp.source_type})
        return clean(doc)

    async def parse_range(start_at, end_at):
        try:
            start = datetime.fromisoformat(start_at)
            end = datetime.fromisoformat(end_at)
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=422, detail="Appointment times must be ISO-8601 timestamps")
        if end <= start:
            raise HTTPException(status_code=422, detail="Appointment end must be after its start")
        return start, end

    async def appointment_conflict(tenant_id, owner, start, end, ignore_id=None):
        """An existing live booking of this owner's that overlaps [start, end).

        The overlap is the query itself, on the stored UTC instants. Reading the owner's
        first 1,000 bookings and comparing in Python stopped finding conflicts once past
        bookings -- never moved out of `scheduled` -- filled those 1,000 slots.
        """
        if not owner:
            return None
        query = {"tenant_id": tenant_id, "owner": owner,
                 "status": {"$in": ["scheduled", "confirmed"]},
                 "start_ts": {"$lt": end}, "end_ts": {"$gt": start}}
        if ignore_id:
            query["id"] = {"$ne": ignore_id}
        return await db.appointments.find_one(query, {"_id": 0})

    @router.get("/appointments")
    async def list_appointments(workspace_id: Optional[str] = None, user=Depends(get_current_user)):
        if workspace_id:
            await visible_workspace(user, workspace_id)
        query = {"tenant_id": user["tenant_id"]}
        if workspace_id:
            query["workspace_id"] = workspace_id
        return [clean(row) for row in await db.appointments.find(query, {"_id": 0}).sort("start_at", 1).to_list(1000)]

    @router.post("/appointments")
    async def create_appointment(inp: AppointmentInput, user=Depends(get_current_user)):
        if inp.workspace_id:
            await visible_workspace(user, inp.workspace_id)
        if inp.company_id:
            company = await db.companies.find_one({"tenant_id": user["tenant_id"], "id": inp.company_id}, {"_id": 0})
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")
        if inp.contact_id:
            contact = await db.contacts.find_one({"tenant_id": user["tenant_id"], "id": inp.contact_id}, {"_id": 0, "id": 1})
            if not contact:
                raise HTTPException(status_code=404, detail="Contact not found")
        start, end = await parse_range(inp.start_at, inp.end_at)
        conflict = await appointment_conflict(user["tenant_id"], inp.owner, start, end)
        if conflict:
            raise HTTPException(status_code=409, detail={"message": "Appointment conflicts with an existing owner schedule", "conflict_title": conflict.get("title"), "conflict_start": conflict.get("start_at")})
        doc = {"id": new_id("apt"), "tenant_id": user["tenant_id"], "title": inp.title, "start_at": start.isoformat(), "end_at": end.isoformat(),
               "start_ts": start.astimezone(timezone.utc), "end_ts": end.astimezone(timezone.utc),
               "owner": inp.owner, "workspace_id": inp.workspace_id, "company_id": inp.company_id,
               "contact_id": inp.contact_id, "appointment_type": inp.appointment_type,
               "status": inp.status, "notes": inp.notes, "reminder_state": "draft_only", "created_by": user["email"], "created_at": now_iso()}
        await db.appointments.insert_one(doc)
        await record_event("appointment.created", "appointment", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"title": inp.title, "status": inp.status})
        return clean(doc)

    @router.patch("/appointments/{appointment_id}")
    async def update_appointment(appointment_id: str, inp: AppointmentPatch, user=Depends(get_current_user)):
        row = await db.appointments.find_one({"id": appointment_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not row:
            raise HTTPException(status_code=404, detail="Appointment not found")
        start_value, end_value = inp.start_at or row["start_at"], inp.end_at or row["end_at"]
        start, end = await parse_range(start_value, end_value)
        conflict = await appointment_conflict(user["tenant_id"], row.get("owner"), start, end, ignore_id=appointment_id)
        if conflict:
            raise HTTPException(status_code=409, detail={"message": "Reschedule conflicts with an existing owner schedule", "conflict_title": conflict.get("title"), "conflict_start": conflict.get("start_at")})
        patch = {"start_at": start.isoformat(), "end_at": end.isoformat(),
                 "start_ts": start.astimezone(timezone.utc), "end_ts": end.astimezone(timezone.utc),
                 "updated_at": now_iso()}
        current = row.get("status") or "scheduled"
        if inp.status and inp.status != current:
            if inp.status not in APPOINTMENT_STATUSES:
                raise HTTPException(status_code=422, detail="Unsupported appointment status")
            allowed = set(APPOINTMENT_TRANSITIONS.get(current, set()))
            if user.get("role") == "admin":
                allowed |= APPOINTMENT_ADMIN_CORRECTIONS.get(current, set())
            if inp.status not in allowed:
                raise HTTPException(status_code=409,
                                    detail=f"An appointment cannot move from '{current}' to '{inp.status}'")
            patch["status"] = inp.status
            if inp.status == "cancelled":
                # The cancelled-appointment detector dates the recovery from this.
                patch["cancelled_at"] = now_iso()
        if inp.notes is not None:
            patch["notes"] = inp.notes
        # Conditional on the status read above, so two concurrent moves cannot both apply.
        moved = await db.appointments.update_one(
            {"id": appointment_id, "tenant_id": user["tenant_id"], "status": row.get("status")},
            {"$set": patch})
        if not moved.matched_count:
            raise HTTPException(status_code=409, detail="The appointment changed meanwhile; reload it")
        await record_event("appointment.updated", "appointment", appointment_id, user["tenant_id"], user["email"], workspace_id=row.get("workspace_id"), payload={"status": patch.get("status", row.get("status"))})
        return {"ok": True, **patch}

    @router.post("/appointments/{appointment_id}/reminder")
    async def prepare_appointment_reminder(appointment_id: str, user=Depends(get_current_user)):
        appointment = await db.appointments.find_one({"id": appointment_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")
        if not appointment.get("workspace_id"):
            raise HTTPException(status_code=400, detail="Appointment must be linked to a workspace before creating a reminder task")
        if (appointment.get("status") or "scheduled") not in REMINDABLE_APPOINTMENT_STATUSES:
            raise HTTPException(status_code=409,
                                detail=f"A '{appointment.get('status')}' appointment needs no reminder")
        # One reminder task per appointment. Repeating the call used to add another task
        # each time, and each became its own missed-follow-up recovery case.
        task_id = f"task_rem_{appointment_id}"
        existing = await db.tasks.find_one({"tenant_id": user["tenant_id"], "id": task_id}, {"_id": 0})
        if existing:
            return {"task": clean(existing), "duplicate": True, "outbound": "disabled",
                    "note": "A reminder task already exists for this appointment."}
        task = {"id": task_id, "tenant_id": user["tenant_id"], "workspace_id": appointment["workspace_id"],
                "title": f"Prepare reminder: {appointment['title']}", "assignee": appointment.get("owner"), "due_date": appointment["start_at"],
                "status": "todo", "source": "appointment_reminder", "appointment_id": appointment_id,
                "created_at": now_iso()}
        try:
            await db.tasks.insert_one(dict(task))
        except DuplicateKeyError:
            existing = await db.tasks.find_one({"tenant_id": user["tenant_id"], "appointment_id": appointment_id}, {"_id": 0})
            return {"task": clean(existing or task), "duplicate": True, "outbound": "disabled",
                    "note": "A reminder task already exists for this appointment."}
        await db.appointments.update_one({"id": appointment_id, "tenant_id": user["tenant_id"]}, {"$set": {"reminder_state": "task_created"}})
        await in_app_notice(user["tenant_id"], "Appointment reminder needs review", task["title"], appointment["workspace_id"])
        await record_event("appointment.reminder_prepared", "appointment", appointment_id, user["tenant_id"], user["email"], workspace_id=appointment["workspace_id"], payload={"task_id": task["id"], "outbound": "disabled"})
        return {"task": clean(task), "duplicate": False, "outbound": "disabled", "note": "No email or SMS was sent; a human-review task was created."}

    @router.get("/field/check-ins")
    async def list_field_checkins(workspace_id: Optional[str] = None, user=Depends(get_current_user)):
        if workspace_id:
            await visible_workspace(user, workspace_id)
        query = {"tenant_id": user["tenant_id"]}
        if workspace_id:
            query["workspace_id"] = workspace_id
        return [clean(row) for row in await db.field_checkins.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)]

    @router.post("/field/check-ins")
    async def create_field_checkin(inp: CheckInInput, user=Depends(get_current_user)):
        await visible_workspace(user, inp.workspace_id)
        doc = {"id": new_id("checkin"), "tenant_id": user["tenant_id"], "workspace_id": inp.workspace_id, "note": inp.note,
               "location_label": inp.location_label, "actor": user["email"], "created_at": now_iso()}
        await db.field_checkins.insert_one(doc)
        await record_event("field.check_in", "field_checkin", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"location_label": inp.location_label})
        return clean(doc)

    @router.get("/automations/safe-rules")
    async def list_safe_automation_rules(user=Depends(get_current_user)):
        rows = await db.safe_automation_rules.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
        return {"templates": [{"key": key, **value, "outbound": "disabled"} for key, value in AUTOMATION_TEMPLATES.items()], "rules": [clean(row) for row in rows]}

    @router.post("/automations/safe-rules")
    async def create_safe_automation_rule(inp: AutomationRuleInput, user=Depends(require_role("admin"))):
        if inp.template not in AUTOMATION_TEMPLATES:
            raise HTTPException(status_code=422, detail="Unknown safe automation template")
        if inp.workspace_id:
            await visible_workspace(user, inp.workspace_id)
        doc = {"id": new_id("auto"), "tenant_id": user["tenant_id"], "template": inp.template, "enabled": inp.enabled,
               "workspace_id": inp.workspace_id, "owner": inp.owner, "outbound": "disabled", "created_by": user["email"], "created_at": now_iso()}
        await db.safe_automation_rules.insert_one(doc)
        await record_event("automation.rule_created", "automation_rule", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"template": inp.template, "enabled": inp.enabled, "outbound": "disabled"})
        return clean(doc)

    @router.post("/automations/safe-rules/{rule_id}/run")
    async def run_safe_automation_rule(rule_id: str, user=Depends(require_role("admin"))):
        rule = await db.safe_automation_rules.find_one({"id": rule_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not rule:
            raise HTTPException(status_code=404, detail="Automation rule not found")
        if not rule.get("enabled"):
            raise HTTPException(status_code=409, detail="This automation rule is disabled")
        if not rule.get("workspace_id"):
            raise HTTPException(status_code=400, detail="Select a workspace before running a safe automation")
        await visible_workspace(user, rule["workspace_id"])
        template = AUTOMATION_TEMPLATES[rule["template"]]
        task = {"id": new_id("task"), "tenant_id": user["tenant_id"], "workspace_id": rule["workspace_id"], "title": template["task"],
                "assignee": rule.get("owner"), "due_date": None, "status": "todo", "source": "safe_automation", "created_at": now_iso()}
        await db.tasks.insert_one(task)
        run = {"id": new_id("autorun"), "tenant_id": user["tenant_id"], "rule_id": rule_id, "workspace_id": rule["workspace_id"],
               "status": "completed", "outbound": "disabled", "result": {"task_id": task["id"]}, "created_at": now_iso()}
        await db.safe_automation_runs.insert_one(run)
        await in_app_notice(user["tenant_id"], "Safe automation created a task", task["title"], rule["workspace_id"])
        await record_event("automation.safe_run", "automation_run", run["id"], user["tenant_id"], user["email"], workspace_id=rule["workspace_id"], payload={"template": rule["template"], "outbound": "disabled"})
        return {"run": clean(run), "task": clean(task), "note": "The workflow created internal work only. Outbound messages remain disabled."}

    @router.get("/reviews")
    async def list_review_requests(user=Depends(get_current_user)):
        return [clean(row) for row in await db.review_requests.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)]

    @router.post("/reviews")
    async def create_review_request(inp: ReviewRequestInput, user=Depends(require_role("admin"))):
        await visible_workspace(user, inp.workspace_id)
        if inp.contact_id:
            contact = await db.contacts.find_one({"id": inp.contact_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
            if not contact:
                raise HTTPException(status_code=404, detail="Contact not found")
        doc = {"id": new_id("review"), "tenant_id": user["tenant_id"], "workspace_id": inp.workspace_id, "contact_id": inp.contact_id,
               "message": inp.message or "Thank the client and request a review only after human approval.", "status": "ready_for_review", "outbound": "disabled", "created_by": user["email"], "created_at": now_iso()}
        await db.review_requests.insert_one(doc)
        await in_app_notice(user["tenant_id"], "Review request needs human approval", "No review request has been sent automatically.", inp.workspace_id)
        await record_event("review.request_prepared", "review_request", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"outbound": "disabled"})
        return clean(doc)

    @router.get("/delivery/capacity")
    async def delivery_capacity(user=Depends(get_current_user)):
        # Open means not finished in any way: a cancelled task is not work anyone carries.
        rows = await db.tasks.find({"tenant_id": user["tenant_id"],
                                    "status": {"$nin": ["done", "cancelled", "complete", "completed"]}},
                                   {"_id": 0}).to_list(2000)
        people = {}
        now = datetime.now(timezone.utc)
        for task in rows:
            owner = task.get("assignee") or "Unassigned"
            item = people.setdefault(owner, {"owner": owner, "open_tasks": 0, "overdue": 0, "workspace_ids": set()})
            item["open_tasks"] += 1
            if task.get("workspace_id"):
                item["workspace_ids"].add(task["workspace_id"])
            if task.get("due_date"):
                try:
                    due = datetime.fromisoformat(task["due_date"])
                    if due.tzinfo is None:
                        due = due.replace(tzinfo=timezone.utc)
                    if due < now:
                        item["overdue"] += 1
                except ValueError:
                    pass
        return {"people": [{**item, "active_workspaces": len(item.pop("workspace_ids"))} for item in people.values()]}

    @router.get("/playbooks")
    async def list_playbooks(user=Depends(get_current_user)):
        applied = await db.playbook_applications.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
        return {"templates": [{"key": key, **value} for key, value in PLAYBOOKS.items()], "applications": [clean(row) for row in applied]}

    @router.post("/playbooks/{playbook_key}/apply")
    async def apply_playbook(playbook_key: str, inp: PlaybookApplyInput, user=Depends(require_role("admin"))):
        playbook = PLAYBOOKS.get(playbook_key)
        if not playbook:
            raise HTTPException(status_code=404, detail="Playbook not found")
        await visible_workspace(user, inp.workspace_id)
        existing = await db.playbook_applications.find_one({"tenant_id": user["tenant_id"], "workspace_id": inp.workspace_id, "playbook_key": playbook_key}, {"_id": 0})
        if existing:
            return {"application": clean(existing), "duplicate": True}
        app = {"id": new_id("play"), "tenant_id": user["tenant_id"], "workspace_id": inp.workspace_id, "playbook_key": playbook_key,
               "application_key": f"{inp.workspace_id}:{playbook_key}", "created_at": now_iso(), "created_by": user["email"]}
        try:
            # The unique index decides a race the read above cannot: eight concurrent
            # applies used to create eight applications and three times as many tasks.
            await db.playbook_applications.insert_one(dict(app))
        except DuplicateKeyError:
            winner = await db.playbook_applications.find_one(
                {"tenant_id": user["tenant_id"], "application_key": app["application_key"]}, {"_id": 0})
            return {"application": clean(winner or app), "duplicate": True}
        tasks = []
        for title in playbook["tasks"]:
            task = {"id": new_id("task"), "tenant_id": user["tenant_id"], "workspace_id": inp.workspace_id, "title": title,
                    "assignee": None, "due_date": None, "status": "todo", "source": f"playbook:{playbook_key}", "created_at": now_iso()}
            await db.tasks.insert_one(task)
            tasks.append(clean(task))
        await record_event("playbook.applied", "playbook_application", app["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"playbook": playbook_key, "task_count": len(tasks)})
        return {"application": clean(app), "tasks": tasks, "duplicate": False}
