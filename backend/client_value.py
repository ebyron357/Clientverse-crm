"""Tenant-scoped client-value CRM workflows.

This module intentionally keeps provider-dependent outcomes explicit. It coordinates
records, approvals, tasks, and in-app notices; it never sends Gmail, SMS, review, or
payment-provider traffic without a separately certified connection.
"""

from datetime import datetime, timezone
import hashlib
import secrets
from typing import List, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl


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
    quantity: float = Field(default=1, gt=0)
    unit_price: float = Field(default=0, ge=0)


class EstimateInput(BaseModel):
    workspace_id: str
    title: str = Field(min_length=2, max_length=200)
    currency: str = "USD"
    lines: List[EstimateLine] = Field(default_factory=list)
    valid_until: Optional[str] = None


class ReferralInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    source_type: str = "partner"
    company_id: Optional[str] = None
    contact_email: Optional[str] = None
    status: str = "active"


class AppointmentInput(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    start_at: str
    end_at: str
    owner: Optional[str] = None
    workspace_id: Optional[str] = None
    company_id: Optional[str] = None
    appointment_type: str = "service"
    status: str = "scheduled"
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
        commitments = await db.commitments.find({"tenant_id": link["tenant_id"], "workspace_id": link["workspace_id"]}, {"_id": 0}).sort("due_date", 1).to_list(100)
        return {"client_label": link["client_label"], "workspace": {"name": workspace["name"], "stage": workspace.get("stage")},
                "company": {"name": (company or {}).get("name")}, "commitments": [clean(v) for v in commitments],
                "documents": [clean(v) for v in docs], "estimates": [clean(v) for v in estimates], "invoices": [clean(v) for v in invoices],
                "capability_note": "This portal supports read-only status and client requests. Billing, signatures, and messages remain provider-dependent and require human review."}

    @router.post("/portal/{token}/requests")
    async def portal_request(token: str, inp: PortalRequestInput):
        link = await public_portal(token)
        doc = {"id": new_id("req"), "tenant_id": link["tenant_id"], "workspace_id": link["workspace_id"], "title": inp.title,
               "priority": inp.priority if inp.priority in ("low", "medium", "high") else "medium", "status": "open", "source": "portal", "created_at": now_iso()}
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
        await db.client_documents.insert_one(doc)
        if inp.requires_approval:
            approval = {"id": new_id("apr"), "tenant_id": user["tenant_id"], "workspace_id": inp.workspace_id,
                        "title": f"Approve document: {inp.title}", "kind": "document_share", "status": "requested", "document_id": doc["id"], "created_at": now_iso()}
            await db.approvals.insert_one(approval)
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
        doc = {"id": new_id("est"), "tenant_id": user["tenant_id"], "workspace_id": inp.workspace_id, "title": inp.title,
               "currency": inp.currency.upper(), "lines": lines, "total": total, "valid_until": inp.valid_until, "status": "draft",
               "created_by": user["email"], "created_at": now_iso()}
        await db.estimates.insert_one(doc)
        await record_event("estimate.created", "estimate", doc["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"title": inp.title, "total": total})
        return clean(doc)

    @router.patch("/estimates/{estimate_id}")
    async def update_estimate(estimate_id: str, inp: RecordStatusInput, user=Depends(require_role("admin"))):
        if inp.status not in ("draft", "sent", "approved", "declined", "expired"):
            raise HTTPException(status_code=422, detail="Unsupported estimate status")
        result = await db.estimates.update_one({"id": estimate_id, "tenant_id": user["tenant_id"]}, {"$set": {"status": inp.status, "updated_at": now_iso()}})
        if not result.matched_count:
            raise HTTPException(status_code=404, detail="Estimate not found")
        return {"ok": True, "status": inp.status}

    @router.post("/estimates/{estimate_id}/invoice")
    async def create_invoice_from_estimate(estimate_id: str, user=Depends(require_role("admin"))):
        estimate = await db.estimates.find_one({"id": estimate_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not estimate:
            raise HTTPException(status_code=404, detail="Estimate not found")
        if estimate.get("status") not in ("approved", "sent"):
            raise HTTPException(status_code=400, detail="Only sent or approved estimates can be converted")
        existing = await db.invoices.find_one({"tenant_id": user["tenant_id"], "estimate_id": estimate_id}, {"_id": 0})
        if existing:
            return {"invoice": clean(existing), "duplicate": True}
        invoice = {"id": new_id("inv"), "tenant_id": user["tenant_id"], "workspace_id": estimate["workspace_id"], "estimate_id": estimate_id,
                   "title": estimate["title"], "currency": estimate["currency"], "lines": estimate["lines"], "total": estimate["total"],
                   "status": "draft", "payment_status": "requires_stripe_configuration", "created_at": now_iso()}
        await db.invoices.insert_one(invoice)
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
        if inp.status not in ("draft", "issued", "paid", "overdue", "void"):
            raise HTTPException(status_code=422, detail="Unsupported invoice status")
        result = await db.invoices.update_one({"id": invoice_id, "tenant_id": user["tenant_id"]}, {"$set": {"status": inp.status, "updated_at": now_iso()}})
        if not result.matched_count:
            raise HTTPException(status_code=404, detail="Invoice not found")
        return {"ok": True, "status": inp.status}

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
        if not owner:
            return None
        query = {"tenant_id": tenant_id, "owner": owner, "status": {"$in": ["scheduled", "confirmed"]}}
        if ignore_id:
            query["id"] = {"$ne": ignore_id}
        rows = await db.appointments.find(query, {"_id": 0}).to_list(1000)
        for row in rows:
            try:
                existing_start, existing_end = await parse_range(row["start_at"], row["end_at"])
                if existing_start < end and existing_end > start:
                    return row
            except HTTPException:
                continue
        return None

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
        start, end = await parse_range(inp.start_at, inp.end_at)
        conflict = await appointment_conflict(user["tenant_id"], inp.owner, start, end)
        if conflict:
            raise HTTPException(status_code=409, detail={"message": "Appointment conflicts with an existing owner schedule", "conflict_title": conflict.get("title"), "conflict_start": conflict.get("start_at")})
        doc = {"id": new_id("apt"), "tenant_id": user["tenant_id"], "title": inp.title, "start_at": start.isoformat(), "end_at": end.isoformat(),
               "owner": inp.owner, "workspace_id": inp.workspace_id, "company_id": inp.company_id, "appointment_type": inp.appointment_type,
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
        patch = {"start_at": start.isoformat(), "end_at": end.isoformat(), "updated_at": now_iso()}
        if inp.status:
            if inp.status not in ("scheduled", "confirmed", "completed", "no_show", "cancelled"):
                raise HTTPException(status_code=422, detail="Unsupported appointment status")
            patch["status"] = inp.status
        if inp.notes is not None:
            patch["notes"] = inp.notes
        await db.appointments.update_one({"id": appointment_id, "tenant_id": user["tenant_id"]}, {"$set": patch})
        await record_event("appointment.updated", "appointment", appointment_id, user["tenant_id"], user["email"], workspace_id=row.get("workspace_id"), payload={"status": patch.get("status", row.get("status"))})
        return {"ok": True, **patch}

    @router.post("/appointments/{appointment_id}/reminder")
    async def prepare_appointment_reminder(appointment_id: str, user=Depends(get_current_user)):
        appointment = await db.appointments.find_one({"id": appointment_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")
        if not appointment.get("workspace_id"):
            raise HTTPException(status_code=400, detail="Appointment must be linked to a workspace before creating a reminder task")
        task = {"id": new_id("task"), "tenant_id": user["tenant_id"], "workspace_id": appointment["workspace_id"],
                "title": f"Prepare reminder: {appointment['title']}", "assignee": appointment.get("owner"), "due_date": appointment["start_at"],
                "status": "todo", "source": "appointment_reminder", "created_at": now_iso()}
        await db.tasks.insert_one(task)
        await db.appointments.update_one({"id": appointment_id}, {"$set": {"reminder_state": "task_created"}})
        await in_app_notice(user["tenant_id"], "Appointment reminder needs review", task["title"], appointment["workspace_id"])
        await record_event("appointment.reminder_prepared", "appointment", appointment_id, user["tenant_id"], user["email"], workspace_id=appointment["workspace_id"], payload={"task_id": task["id"], "outbound": "disabled"})
        return {"task": clean(task), "outbound": "disabled", "note": "No email or SMS was sent; a human-review task was created."}

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
        rows = await db.tasks.find({"tenant_id": user["tenant_id"], "status": {"$ne": "done"}}, {"_id": 0}).to_list(2000)
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
        app = {"id": new_id("play"), "tenant_id": user["tenant_id"], "workspace_id": inp.workspace_id, "playbook_key": playbook_key, "created_at": now_iso(), "created_by": user["email"]}
        await db.playbook_applications.insert_one(app)
        tasks = []
        for title in playbook["tasks"]:
            task = {"id": new_id("task"), "tenant_id": user["tenant_id"], "workspace_id": inp.workspace_id, "title": title,
                    "assignee": None, "due_date": None, "status": "todo", "source": f"playbook:{playbook_key}", "created_at": now_iso()}
            await db.tasks.insert_one(task)
            tasks.append(clean(task))
        await record_event("playbook.applied", "playbook_application", app["id"], user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"playbook": playbook_key, "task_count": len(tasks)})
        return {"application": clean(app), "tasks": tasks, "duplicate": False}
