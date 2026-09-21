"""Baseline CRM: the records a salesperson actually works in.

ClientVerse grew outward from delivery workspaces and a recovery engine, and the
ordinary CRM underneath it was never finished. Contacts and companies could be created
and listed but not opened, edited or archived. A deal could be created and dragged
between stages, but its value, owner and close date were write-once. Tasks existed only
inside a delivery workspace, so "call this contact back on Thursday" had nowhere to
live. There were no notes, calls or meetings at all, no search, and no way to get data
in or out.

This module closes that gap. It is deliberately conventional: the shapes here are the
ones a person moving from another CRM expects, because a recovery engine layered on a
CRM nobody can run their week in is not a product.

Three rules hold throughout, and they are the same rules the rest of the system keeps:

* **Tenancy is absolute.** Every query is filtered by `tenant_id` before anything else,
  and a record belonging to another tenant is indistinguishable from one that does not
  exist -- a 404, never a 403, because a 403 confirms the id is real.
* **Two audit trails, kept apart.** Organisation-wide activity goes to `domain_events`
  via `record_event`. A record's own state transitions go into that record's `history`.
  They answer different questions and are not merged.
* **Nothing here reaches outside.** Logging a call or an email records that a human did
  it. It sends nothing. Everything outbound goes through the communications path, with
  its approvals and consent checks.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from fastapi import Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, EmailStr, Field

# --------------------------------------------------------------------------- constants

CONTACTS = "contacts"
COMPANIES = "companies"
DEALS = "opportunities"
TASKS = "tasks"
ACTIVITIES = "crm_activities"
PIPELINES = "pipelines"

# The stage set the product shipped with. It stays the default so every existing tenant
# and every existing opportunity keeps working unchanged; a tenant that configures its
# own pipeline overrides it.
DEFAULT_STAGES = [
    {"key": "lead", "label": "Lead", "probability": 10, "is_closed": False, "is_won": False},
    {"key": "qualified", "label": "Qualified", "probability": 25, "is_closed": False, "is_won": False},
    {"key": "proposal", "label": "Proposal", "probability": 50, "is_closed": False, "is_won": False},
    {"key": "negotiation", "label": "Negotiation", "probability": 75, "is_closed": False, "is_won": False},
    {"key": "closed_won", "label": "Closed won", "probability": 100, "is_closed": True, "is_won": True},
    {"key": "closed_lost", "label": "Closed lost", "probability": 0, "is_closed": True, "is_won": False},
]

ACTIVITY_TYPES = ("note", "call", "meeting", "email", "status_change")
TASK_STATUSES = ("todo", "in_progress", "blocked", "done", "cancelled")

# What a search or filter is allowed to reach. Anything not listed is not queryable,
# which keeps a caller from steering a query at a field it should not see.
SEARCHABLE = {
    CONTACTS: ("name", "email", "role", "phone", "title"),
    COMPANIES: ("name", "industry", "website", "domain"),
    DEALS: ("name", "owner"),
    TASKS: ("title", "assignee"),
}
SORTABLE = {
    CONTACTS: ("created_at", "updated_at", "name", "owner"),
    COMPANIES: ("created_at", "updated_at", "name", "owner"),
    DEALS: ("created_at", "updated_at", "name", "value", "stage", "expected_close_date", "owner"),
    TASKS: ("created_at", "updated_at", "due_date", "status", "assignee", "title"),
}

MAX_PAGE = 200
MAX_IMPORT_ROWS = 5000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime] = None) -> str:
    return (value or _now()).astimezone(timezone.utc).isoformat()


def _public(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    return {k: v for k, v in doc.items() if k != "_id"}


def _history_entry(action: str, actor: str, detail: Optional[dict] = None) -> dict:
    return {"action": action, "actor": actor, "at": _iso(), "detail": detail or {}}


def _escape_regex(value: str) -> str:
    return re.escape(value.strip())[:200]


def _parse_date(value: Optional[str], field: str) -> Optional[str]:
    """Accept an ISO date or datetime and normalise it, or refuse it.

    Silently keeping an unparseable date is how a pipeline ends up with close dates
    nobody can sort or report on.
    """
    if value in (None, ""):
        return None
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422,
                            detail=f"{field} must be an ISO 8601 date or datetime")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return _iso(parsed)


async def ensure_indexes(db) -> None:
    await db[CONTACTS].create_index([("tenant_id", 1), ("created_at", -1)])
    await db[CONTACTS].create_index([("tenant_id", 1), ("company_id", 1)])
    await db[CONTACTS].create_index([("tenant_id", 1), ("owner", 1)])
    await db[COMPANIES].create_index([("tenant_id", 1), ("created_at", -1)])
    await db[COMPANIES].create_index([("tenant_id", 1), ("owner", 1)])
    await db[DEALS].create_index([("tenant_id", 1), ("stage", 1)])
    await db[DEALS].create_index([("tenant_id", 1), ("company_id", 1)])
    await db[DEALS].create_index([("tenant_id", 1), ("owner", 1)])
    await db[DEALS].create_index([("tenant_id", 1), ("expected_close_date", 1)])
    await db[TASKS].create_index([("tenant_id", 1), ("status", 1), ("due_date", 1)])
    await db[TASKS].create_index([("tenant_id", 1), ("assignee", 1)])
    await db[TASKS].create_index([("tenant_id", 1), ("related_type", 1), ("related_id", 1)])
    await db[ACTIVITIES].create_index([("tenant_id", 1), ("related_type", 1),
                                       ("related_id", 1), ("occurred_at", -1)])
    await db[ACTIVITIES].create_index([("tenant_id", 1), ("type", 1), ("occurred_at", -1)])
    await db[PIPELINES].create_index([("tenant_id", 1), ("id", 1)], unique=True)


# ------------------------------------------------------------- helpers used by server

def created_history(actor: str) -> dict:
    """The first entry in a record's own history."""
    return _history_entry("created", actor)


def stage_history(actor: str, transition: dict) -> dict:
    return _history_entry("stage_changed", actor, transition)


def parse_date(value: Optional[str], field: str) -> Optional[str]:
    return _parse_date(value, field)


async def query_records(db, collection: str, tenant_id: str, *,
                        q: Optional[str] = None,
                        filters: Optional[dict] = None,
                        sort: Optional[str] = None,
                        order: Optional[str] = None,
                        limit: int = 200,
                        offset: int = 0,
                        include_archived: bool = False) -> list[dict]:
    """Search, filter and sort one collection inside one tenant.

    Returns a bare list because the endpoints that use it always have: the directory
    surfaces and existing integrations read an array, and changing that shape to carry
    pagination metadata would break them for no benefit they asked for.

    Only the fields named in SEARCHABLE / SORTABLE are reachable. A caller cannot steer
    a query at a field it has no business reading, and cannot sort by one either.
    """
    query: dict[str, Any] = {"tenant_id": tenant_id}
    if q and q.strip():
        pattern = {"$regex": _escape_regex(q), "$options": "i"}
        query["$or"] = [{field: pattern} for field in SEARCHABLE.get(collection, ())]
    for key, value in (filters or {}).items():
        if value not in (None, ""):
            query[key] = value
    if not include_archived:
        # Records created before archiving existed have no `archived_at` field at all,
        # so "not archived" has to mean missing-or-null, not null.
        query["archived_at"] = None
    sortable = SORTABLE.get(collection, ("created_at",))
    field = sort if sort in sortable else "created_at"
    direction = 1 if (order or "desc").lower() == "asc" else -1
    limit = max(1, min(int(limit or 200), 1000))
    offset = max(0, int(offset or 0))
    return await (db[collection].find(query, {"_id": 0})
                  .sort([(field, direction)])
                  .skip(offset).limit(limit).to_list(limit))


# ---------------------------------------------------------------------------- pipeline

async def resolve_stages(db, tenant_id: str) -> list[dict]:
    """The stage set this tenant works in.

    Falls back to the shipped default rather than to nothing: a tenant that has never
    touched pipeline configuration must still have a working pipeline.
    """
    doc = await db[PIPELINES].find_one({"tenant_id": tenant_id, "id": "default"}, {"_id": 0})
    stages = (doc or {}).get("stages")
    if not stages:
        return [dict(stage) for stage in DEFAULT_STAGES]
    return [dict(stage) for stage in stages]


async def stage_keys(db, tenant_id: str) -> list[str]:
    return [stage["key"] for stage in await resolve_stages(db, tenant_id)]


# ------------------------------------------------------------------- request payloads

class ContactPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=60)
    title: Optional[str] = Field(default=None, max_length=160)
    role: Optional[str] = Field(default=None, max_length=160)
    company_id: Optional[str] = None
    owner: Optional[str] = Field(default=None, max_length=200)
    influence: Optional[str] = None
    sentiment: Optional[str] = None


class CompanyPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    industry: Optional[str] = Field(default=None, max_length=160)
    website: Optional[str] = Field(default=None, max_length=300)
    domain: Optional[str] = Field(default=None, max_length=200)
    tier: Optional[str] = Field(default=None, max_length=60)
    owner: Optional[str] = Field(default=None, max_length=200)
    annual_value: Optional[float] = Field(default=None, ge=0)


class DealPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    company_id: Optional[str] = None
    contact_ids: Optional[list[str]] = None
    value: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, max_length=8)
    owner: Optional[str] = Field(default=None, max_length=200)
    expected_close_date: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=4000)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    assignee: Optional[str] = Field(default=None, max_length=200)
    due_date: Optional[str] = None
    status: str = "todo"
    priority: str = "medium"
    notes: Optional[str] = Field(default=None, max_length=4000)
    # A follow-up belongs to whatever it is a follow-up on. Workspace stays supported
    # because delivery tasks already live there.
    related_type: Optional[str] = None
    related_id: Optional[str] = None
    workspace_id: Optional[str] = None


class TaskPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    assignee: Optional[str] = Field(default=None, max_length=200)
    due_date: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=4000)


class ActivityCreate(BaseModel):
    type: str
    related_type: str
    related_id: str
    subject: Optional[str] = Field(default=None, max_length=300)
    body: Optional[str] = Field(default=None, max_length=8000)
    occurred_at: Optional[str] = None
    duration_minutes: Optional[int] = Field(default=None, ge=0, le=24 * 60)
    participants: Optional[list[str]] = None
    outcome: Optional[str] = Field(default=None, max_length=200)


class StageConfig(BaseModel):
    key: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=80)
    probability: int = Field(default=0, ge=0, le=100)
    is_closed: bool = False
    is_won: bool = False


class PipelineInput(BaseModel):
    stages: list[StageConfig] = Field(min_length=2, max_length=20)


class ImportInput(BaseModel):
    csv: str = Field(min_length=1)
    # Importing is the one place a caller can create many records at once, so it is
    # explicit about what it will do with a row that already looks familiar.
    on_duplicate: str = "skip"  # skip | update | create


# ------------------------------------------------------------------------ registration

def register_crm_core_routes(router, db, new_id, now_iso, record_event,
                             get_current_user, require_role):
    """Attach the baseline CRM routes, using the application's own helpers.

    Injection rather than import keeps this module free of a circular dependency on
    `server`, and keeps every audit event flowing through the one `record_event` the
    rest of the application uses.
    """

    # ------------------------------------------------------------------ shared helpers

    def tenant_of(user) -> str:
        return user["tenant_id"]

    async def load(collection: str, record_id: str, user) -> dict:
        """Read one record inside the caller's tenant, or 404.

        A record in another tenant answers exactly as a record that does not exist.
        Anything else -- a 403, a different message, a different latency profile -- tells
        an attacker the id was real.
        """
        doc = await db[collection].find_one(
            {"id": record_id, "tenant_id": tenant_of(user)}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        return doc

    async def assert_exists(collection: str, record_id: Optional[str], user,
                            label: str) -> None:
        """Refuse a reference to a record the caller cannot see.

        Without this a contact could be pointed at another tenant's company id and the
        two tenants would quietly share a relationship.
        """
        if not record_id:
            return
        found = await db[collection].find_one(
            {"id": record_id, "tenant_id": tenant_of(user)}, {"_id": 1})
        if not found:
            raise HTTPException(status_code=422, detail=f"Unknown {label}")

    async def apply_patch(collection: str, record_id: str, user, changes: dict,
                          event_type: str, resource_type: str,
                          action: str = "updated") -> dict:
        existing = await load(collection, record_id, user)
        changed = {k: v for k, v in changes.items() if existing.get(k) != v}
        if not changed:
            return existing
        before = {k: existing.get(k) for k in changed}
        update = {**changed, "updated_at": now_iso()}
        await db[collection].update_one(
            {"id": record_id, "tenant_id": tenant_of(user)},
            {"$set": update,
             "$push": {"history": _history_entry(action, user["email"],
                                                 {"changed": sorted(changed), "from": before})}})
        await record_event(event_type, resource_type, record_id, tenant_of(user),
                           user["email"], payload={"changed": sorted(changed)})
        return await load(collection, record_id, user)

    def text_filter(collection: str, term: Optional[str]) -> dict:
        if not term or not term.strip():
            return {}
        pattern = {"$regex": _escape_regex(term), "$options": "i"}
        return {"$or": [{field: pattern} for field in SEARCHABLE[collection]]}

    def sort_spec(collection: str, sort: Optional[str], order: Optional[str]):
        field = sort if sort in SORTABLE[collection] else "created_at"
        direction = 1 if (order or "desc").lower() == "asc" else -1
        return [(field, direction)]

    def archive_filter(include_archived: bool) -> dict:
        # Archived records stay readable by id -- history does not disappear because a
        # record was filed away -- but they leave the working lists.
        return {} if include_archived else {"archived_at": None}

    async def listing(collection: str, user, *, query: dict, sort: Optional[str],
                      order: Optional[str], limit: int, offset: int) -> dict:
        base = {"tenant_id": tenant_of(user), **query}
        limit = max(1, min(int(limit or 50), MAX_PAGE))
        offset = max(0, int(offset or 0))
        cursor = (db[collection].find(base, {"_id": 0})
                  .sort(sort_spec(collection, sort, order))
                  .skip(offset).limit(limit))
        items = await cursor.to_list(limit)
        total = await db[collection].count_documents(base)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def timeline_for(user, related_type: str, related_id: str,
                           limit: int = 100) -> list[dict]:
        """One record's activity, from both audit trails.

        `crm_activities` holds what people did (notes, calls, meetings, logged email).
        `domain_events` holds what the system recorded about the record. They are read
        together here for display and stay separate at rest.
        """
        scope = {"tenant_id": tenant_of(user), "related_type": related_type,
                 "related_id": related_id}
        activities = await db[ACTIVITIES].find(scope, {"_id": 0}).sort(
            "occurred_at", -1).to_list(limit)
        events = await db.domain_events.find(
            {"tenant_id": tenant_of(user), "resource_id": related_id},
            {"_id": 0}).sort("timestamp", -1).to_list(limit)
        merged = [
            {"kind": "activity", "at": item.get("occurred_at") or item.get("created_at"),
             "type": item.get("type"), "subject": item.get("subject"),
             "body": item.get("body"), "actor": item.get("actor"), "id": item.get("id"),
             "outcome": item.get("outcome")}
            for item in activities
        ] + [
            {"kind": "event", "at": item.get("timestamp"), "type": item.get("event_type"),
             "subject": None, "body": None, "actor": item.get("actor"),
             "id": item.get("id"), "payload": item.get("payload")}
            for item in events
        ]
        merged.sort(key=lambda entry: entry.get("at") or "", reverse=True)
        return merged[:limit]

    # ------------------------------------------------------------------------ contacts

    @router.get("/contacts/{contact_id}")
    async def get_contact(contact_id: str, user=Depends(get_current_user)):
        """One contact with the context that makes it worth opening."""
        contact = await load(CONTACTS, contact_id, user)
        tenant = tenant_of(user)
        company = None
        if contact.get("company_id"):
            company = _public(await db[COMPANIES].find_one(
                {"id": contact["company_id"], "tenant_id": tenant}, {"_id": 0}))
        deals = await db[DEALS].find(
            {"tenant_id": tenant, "contact_ids": contact_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(100)
        tasks = await db[TASKS].find(
            {"tenant_id": tenant, "related_type": "contact", "related_id": contact_id},
            {"_id": 0}).sort("due_date", 1).to_list(100)
        conversations = await db.conversations.find(
            {"tenant_id": tenant, "participants.contact_id": contact_id}, {"_id": 0}
        ).sort("last_message_at", -1).to_list(25)
        return {"contact": contact, "company": company, "deals": deals, "tasks": tasks,
                "conversations": conversations,
                "timeline": await timeline_for(user, "contact", contact_id)}

    @router.patch("/contacts/{contact_id}")
    async def update_contact(contact_id: str, inp: ContactPatch,
                             user=Depends(get_current_user)):
        changes = {k: v for k, v in inp.model_dump(exclude_unset=True).items()}
        if "email" in changes and changes["email"] is not None:
            changes["email"] = str(changes["email"])
        await assert_exists(COMPANIES, changes.get("company_id"), user, "company_id")
        return await apply_patch(CONTACTS, contact_id, user, changes,
                                 "contact.updated", "contact")

    @router.post("/contacts/{contact_id}/archive")
    async def archive_contact(contact_id: str, user=Depends(get_current_user)):
        """Archive rather than delete.

        A contact is referenced by conversations, recovery cases and attribution
        evidence. Deleting the row would leave those citing something that no longer
        exists, which is worse than a record that is merely out of the way.
        """
        return await apply_patch(CONTACTS, contact_id, user, {"archived_at": now_iso()},
                                 "contact.archived", "contact", action="archived")

    @router.post("/contacts/{contact_id}/restore")
    async def restore_contact(contact_id: str, user=Depends(get_current_user)):
        return await apply_patch(CONTACTS, contact_id, user, {"archived_at": None},
                                 "contact.restored", "contact", action="restored")

    @router.get("/contacts/{contact_id}/timeline")
    async def contact_timeline(contact_id: str, limit: int = 100,
                               user=Depends(get_current_user)):
        await load(CONTACTS, contact_id, user)
        return {"timeline": await timeline_for(user, "contact", contact_id, limit)}

    # ----------------------------------------------------------------------- companies

    @router.get("/companies/{company_id}")
    async def get_company(company_id: str, user=Depends(get_current_user)):
        company = await load(COMPANIES, company_id, user)
        tenant = tenant_of(user)
        contacts = await db[CONTACTS].find(
            {"tenant_id": tenant, "company_id": company_id, "archived_at": None},
            {"_id": 0}).sort("created_at", -1).to_list(200)
        deals = await db[DEALS].find(
            {"tenant_id": tenant, "company_id": company_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(200)
        workspaces = await db.workspaces.find(
            {"tenant_id": tenant, "company_id": company_id}, {"_id": 0}).to_list(50)
        open_deals = [deal for deal in deals if not deal.get("stage", "").startswith("closed")]
        won = [deal for deal in deals if deal.get("stage") == "closed_won"]
        return {
            "company": company, "contacts": contacts, "deals": deals,
            "workspaces": workspaces,
            # Commercial context, stated as what it is. Open pipeline is an estimate and
            # is never added to closed-won revenue.
            "commercial": {
                "open_deal_count": len(open_deals),
                "open_pipeline_value": round(sum(float(d.get("value") or 0) for d in open_deals), 2),
                "won_deal_count": len(won),
                "closed_won_value": round(sum(float(d.get("value") or 0) for d in won), 2),
            },
            "timeline": await timeline_for(user, "company", company_id),
        }

    @router.patch("/companies/{company_id}")
    async def update_company(company_id: str, inp: CompanyPatch,
                             user=Depends(get_current_user)):
        changes = inp.model_dump(exclude_unset=True)
        return await apply_patch(COMPANIES, company_id, user, changes,
                                 "company.updated", "company")

    @router.post("/companies/{company_id}/archive")
    async def archive_company(company_id: str, user=Depends(get_current_user)):
        return await apply_patch(COMPANIES, company_id, user, {"archived_at": now_iso()},
                                 "company.archived", "company", action="archived")

    @router.post("/companies/{company_id}/restore")
    async def restore_company(company_id: str, user=Depends(get_current_user)):
        return await apply_patch(COMPANIES, company_id, user, {"archived_at": None},
                                 "company.restored", "company", action="restored")

    @router.get("/companies/{company_id}/timeline")
    async def company_timeline(company_id: str, limit: int = 100,
                               user=Depends(get_current_user)):
        await load(COMPANIES, company_id, user)
        return {"timeline": await timeline_for(user, "company", company_id, limit)}

    # --------------------------------------------------------------------------- deals

    @router.get("/opportunities/{deal_id}")
    async def get_deal(deal_id: str, user=Depends(get_current_user)):
        deal = await load(DEALS, deal_id, user)
        tenant = tenant_of(user)
        company = None
        if deal.get("company_id"):
            company = _public(await db[COMPANIES].find_one(
                {"id": deal["company_id"], "tenant_id": tenant}, {"_id": 0}))
        contacts = await db[CONTACTS].find(
            {"tenant_id": tenant, "id": {"$in": deal.get("contact_ids") or []}},
            {"_id": 0}).to_list(100)
        tasks = await db[TASKS].find(
            {"tenant_id": tenant, "related_type": "deal", "related_id": deal_id},
            {"_id": 0}).sort("due_date", 1).to_list(100)
        stages = await resolve_stages(db, tenant)
        current = next((s for s in stages if s["key"] == deal.get("stage")), None)
        return {
            "deal": deal, "company": company, "contacts": contacts, "tasks": tasks,
            "stage": current, "stages": stages,
            "stage_history": deal.get("stage_history") or [],
            # Weighted value is an estimate derived from the stage's own probability. It
            # is reported beside the deal value, never in place of it, and it is not
            # revenue.
            "weighted_value_estimate": round(
                float(deal.get("value") or 0) * (current or {}).get("probability", 0) / 100.0, 2),
            "timeline": await timeline_for(user, "deal", deal_id),
        }

    @router.patch("/opportunities/{deal_id}")
    async def update_deal(deal_id: str, inp: DealPatch, user=Depends(get_current_user)):
        """Edit everything about a deal except its stage.

        Stage moves keep their own route because they carry side effects (stage history,
        workspace creation on won) that a generic field update must not trigger by
        accident.
        """
        changes = inp.model_dump(exclude_unset=True)
        if "expected_close_date" in changes:
            changes["expected_close_date"] = _parse_date(
                changes["expected_close_date"], "expected_close_date")
        await assert_exists(COMPANIES, changes.get("company_id"), user, "company_id")
        if changes.get("contact_ids") is not None:
            contact_ids = list(dict.fromkeys(changes["contact_ids"]))[:100]
            visible = await db[CONTACTS].find(
                {"tenant_id": tenant_of(user), "id": {"$in": contact_ids}},
                {"_id": 0, "id": 1}).to_list(100)
            known = {c["id"] for c in visible}
            unknown = [cid for cid in contact_ids if cid not in known]
            if unknown:
                # Refusing the whole update is deliberate: silently dropping the ids the
                # caller cannot see would look like success while losing the link.
                raise HTTPException(status_code=422,
                                    detail=f"Unknown contact_id(s): {', '.join(unknown[:5])}")
            changes["contact_ids"] = contact_ids
        return await apply_patch(DEALS, deal_id, user, changes, "opportunity.updated",
                                 "opportunity")

    @router.post("/opportunities/{deal_id}/archive")
    async def archive_deal(deal_id: str, user=Depends(get_current_user)):
        return await apply_patch(DEALS, deal_id, user, {"archived_at": now_iso()},
                                 "opportunity.archived", "opportunity", action="archived")

    @router.post("/opportunities/{deal_id}/restore")
    async def restore_deal(deal_id: str, user=Depends(get_current_user)):
        return await apply_patch(DEALS, deal_id, user, {"archived_at": None},
                                 "opportunity.restored", "opportunity", action="restored")

    @router.get("/opportunities/{deal_id}/timeline")
    async def deal_timeline(deal_id: str, limit: int = 100,
                            user=Depends(get_current_user)):
        await load(DEALS, deal_id, user)
        return {"timeline": await timeline_for(user, "deal", deal_id, limit)}

    # ----------------------------------------------------------------------- pipelines

    @router.get("/pipelines/default")
    async def get_pipeline(user=Depends(get_current_user)):
        stages = await resolve_stages(db, tenant_of(user))
        configured = await db[PIPELINES].find_one(
            {"tenant_id": tenant_of(user), "id": "default"}, {"_id": 0})
        counts: dict[str, dict] = {}
        for stage in stages:
            scope = {"tenant_id": tenant_of(user), "stage": stage["key"], "archived_at": None}
            deals = await db[DEALS].find(scope, {"_id": 0, "value": 1}).to_list(1000)
            total = round(sum(float(d.get("value") or 0) for d in deals), 2)
            counts[stage["key"]] = {
                "deal_count": len(deals),
                "deal_value": total,
                # Weighted, and labelled as an estimate. It is not recovered or booked
                # revenue and must never be presented as either.
                "weighted_value_estimate": round(total * stage.get("probability", 0) / 100.0, 2),
            }
        return {"id": "default", "stages": stages, "is_customised": bool(configured),
                "totals": counts}

    @router.put("/pipelines/default")
    async def set_pipeline(inp: PipelineInput, user=Depends(require_role("admin"))):
        """Configure this tenant's stages.

        A stage that still holds deals cannot be removed. Rewriting the stage set out
        from under live records would leave them in a stage the pipeline does not have,
        which is how a deal becomes invisible.
        """
        stages = [stage.model_dump() for stage in inp.stages]
        keys = [stage["key"] for stage in stages]
        if len(set(keys)) != len(keys):
            raise HTTPException(status_code=422, detail="Stage keys must be unique")
        if not any(stage["is_closed"] and stage["is_won"] for stage in stages):
            raise HTTPException(status_code=422,
                                detail="At least one stage must be a closed-won stage")
        current = await stage_keys(db, tenant_of(user))
        removed = [key for key in current if key not in keys]
        if removed:
            blocking = await db[DEALS].count_documents(
                {"tenant_id": tenant_of(user), "stage": {"$in": removed}})
            if blocking:
                raise HTTPException(
                    status_code=409,
                    detail=(f"{blocking} deal(s) are still in stage(s) "
                            f"{', '.join(removed)}; move them before removing"))
        await db[PIPELINES].update_one(
            {"tenant_id": tenant_of(user), "id": "default"},
            {"$set": {"stages": stages, "updated_at": now_iso(),
                      "updated_by": user["email"]},
             "$setOnInsert": {"created_at": now_iso()}},
            upsert=True)
        await record_event("pipeline.configured", "pipeline", "default",
                           tenant_of(user), user["email"],
                           payload={"stages": keys, "removed": removed})
        return {"id": "default", "stages": stages, "is_customised": True}

    # --------------------------------------------------------------------------- tasks

    RELATABLE = {"contact": CONTACTS, "company": COMPANIES, "deal": DEALS,
                 "workspace": "workspaces"}

    async def validate_relation(user, related_type: Optional[str],
                                related_id: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        if not related_type and not related_id:
            return None, None
        if not related_type or not related_id:
            raise HTTPException(status_code=422,
                                detail="related_type and related_id must be given together")
        collection = RELATABLE.get(related_type)
        if not collection:
            raise HTTPException(
                status_code=422,
                detail=f"related_type must be one of {', '.join(sorted(RELATABLE))}")
        await assert_exists(collection, related_id, user, f"{related_type} id")
        return related_type, related_id

    @router.get("/tasks")
    async def list_tasks(
        q: Optional[str] = None,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        related_type: Optional[str] = None,
        related_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        due_before: Optional[str] = None,
        due_after: Optional[str] = None,
        sort: Optional[str] = "due_date",
        order: Optional[str] = "asc",
        limit: int = 50,
        offset: int = 0,
        user=Depends(get_current_user),
    ):
        """Every task in the tenant, not just the ones inside a delivery workspace."""
        query: dict[str, Any] = {**text_filter(TASKS, q)}
        if status:
            query["status"] = status
        if assignee:
            query["assignee"] = assignee
        if related_type:
            query["related_type"] = related_type
        if related_id:
            query["related_id"] = related_id
        if workspace_id:
            query["workspace_id"] = workspace_id
        due: dict[str, str] = {}
        if due_before:
            due["$lte"] = _parse_date(due_before, "due_before") or ""
        if due_after:
            due["$gte"] = _parse_date(due_after, "due_after") or ""
        if due:
            query["due_date"] = due
        return await listing(TASKS, user, query=query, sort=sort, order=order,
                             limit=limit, offset=offset)

    @router.post("/crm/tasks")
    async def create_crm_task(inp: TaskCreate, user=Depends(get_current_user)):
        """Create a follow-up against any CRM record.

        Separate path from the existing workspace-only `POST /tasks` so that route's
        contract, and everything already calling it, is untouched.
        """
        if inp.status not in TASK_STATUSES:
            raise HTTPException(status_code=422,
                                detail=f"status must be one of {', '.join(TASK_STATUSES)}")
        related_type, related_id = await validate_relation(user, inp.related_type, inp.related_id)
        workspace_id = inp.workspace_id
        if workspace_id:
            await assert_exists("workspaces", workspace_id, user, "workspace_id")
        doc = {
            "id": new_id("task"), "tenant_id": tenant_of(user), "title": inp.title,
            "assignee": inp.assignee, "due_date": _parse_date(inp.due_date, "due_date"),
            "status": inp.status, "priority": inp.priority, "notes": inp.notes,
            "related_type": related_type, "related_id": related_id,
            "workspace_id": workspace_id, "archived_at": None,
            "created_at": now_iso(), "updated_at": now_iso(),
            "created_by": user["email"], "completed_at": None,
            "history": [_history_entry("created", user["email"])],
        }
        await db[TASKS].insert_one(dict(doc))
        await record_event("task.created", "task", doc["id"], tenant_of(user),
                           user["email"], workspace_id=workspace_id,
                           payload={"title": inp.title, "assignee": inp.assignee,
                                    "related_type": related_type, "related_id": related_id})
        if inp.assignee and inp.assignee != user["email"]:
            await notify_assignment(user, doc)
        return _public(doc)

    async def notify_assignment(user, task: dict) -> None:
        """Tell someone a task landed on them.

        An assignment nobody is told about is not an assignment.
        """
        await db.notifications.insert_one({
            "id": new_id("ntf"), "tenant_id": tenant_of(user), "user_id": None,
            "recipient": task.get("assignee"), "workspace_id": task.get("workspace_id"),
            "type": "assignment", "severity": "info", "source": "crm",
            "title": "A task was assigned to you",
            "body": f"{user['email']} assigned you \"{task['title']}\"",
            "deep_link": f"/tasks/{task['id']}", "read": False, "created_at": now_iso(),
        })

    @router.patch("/crm/tasks/{task_id}")
    async def update_crm_task(task_id: str, inp: TaskPatch, user=Depends(get_current_user)):
        changes = inp.model_dump(exclude_unset=True)
        if "status" in changes and changes["status"] not in TASK_STATUSES:
            raise HTTPException(status_code=422,
                                detail=f"status must be one of {', '.join(TASK_STATUSES)}")
        if "due_date" in changes:
            changes["due_date"] = _parse_date(changes["due_date"], "due_date")
        before = await load(TASKS, task_id, user)
        if changes.get("status") == "done" and before.get("status") != "done":
            changes["completed_at"] = now_iso()
        if changes.get("status") and changes["status"] != "done":
            changes["completed_at"] = None
        updated = await apply_patch(TASKS, task_id, user, changes, "task.updated", "task")
        if changes.get("status") == "done" and before.get("status") != "done":
            await record_event("task.completed", "task", task_id, tenant_of(user),
                               user["email"], workspace_id=before.get("workspace_id"),
                               payload={"title": before.get("title")})
        if changes.get("assignee") and changes["assignee"] != before.get("assignee"):
            await notify_assignment(user, updated)
        return updated

    @router.get("/tasks/overview")
    async def task_overview(days_ahead: int = 7, user=Depends(get_current_user)):
        """Overdue and upcoming work, which is the only task view most people open."""
        tenant = tenant_of(user)
        now = _iso()
        horizon = _iso(_now() + timedelta(days=max(1, min(int(days_ahead or 7), 90))))
        open_status = {"$nin": ["done", "cancelled"]}
        overdue = await db[TASKS].find(
            {"tenant_id": tenant, "status": open_status,
             "due_date": {"$ne": None, "$lt": now}},
            {"_id": 0}).sort("due_date", 1).to_list(MAX_PAGE)
        upcoming = await db[TASKS].find(
            {"tenant_id": tenant, "status": open_status,
             "due_date": {"$gte": now, "$lte": horizon}},
            {"_id": 0}).sort("due_date", 1).to_list(MAX_PAGE)
        undated = await db[TASKS].count_documents(
            {"tenant_id": tenant, "status": open_status, "due_date": None})
        mine = [task for task in overdue + upcoming if task.get("assignee") == user["email"]]
        return {"overdue": overdue, "upcoming": upcoming,
                "counts": {"overdue": len(overdue), "upcoming": len(upcoming),
                           "undated_open": undated, "assigned_to_me": len(mine)}}

    # ---------------------------------------------------------------------- activities

    @router.post("/activities")
    async def log_activity(inp: ActivityCreate, user=Depends(get_current_user)):
        """Log something that happened: a note, a call, a meeting, an email already sent.

        This records history. It sends nothing and schedules nothing -- an email logged
        here is one a person already sent, which is a different fact from one this
        system delivered, and the two are never merged.
        """
        if inp.type not in ACTIVITY_TYPES:
            raise HTTPException(status_code=422,
                                detail=f"type must be one of {', '.join(ACTIVITY_TYPES)}")
        if inp.type == "status_change":
            # The system writes these from real transitions; a caller inventing one
            # would be fabricating a record's history.
            raise HTTPException(status_code=422,
                                detail="status_change activities are recorded by the system")
        related_type, related_id = await validate_relation(user, inp.related_type, inp.related_id)
        doc = {
            "id": new_id("act"), "tenant_id": tenant_of(user), "type": inp.type,
            "related_type": related_type, "related_id": related_id,
            "subject": inp.subject, "body": inp.body,
            "occurred_at": _parse_date(inp.occurred_at, "occurred_at") or now_iso(),
            "duration_minutes": inp.duration_minutes,
            "participants": (inp.participants or [])[:50], "outcome": inp.outcome,
            "actor": user["email"], "created_at": now_iso(), "logged_by": user["email"],
        }
        await db[ACTIVITIES].insert_one(dict(doc))
        await record_event(f"activity.{inp.type}_logged", related_type, related_id,
                           tenant_of(user), user["email"],
                           payload={"activity_id": doc["id"], "subject": inp.subject})
        return _public(doc)

    @router.get("/activities")
    async def list_activities(
        related_type: Optional[str] = None,
        related_id: Optional[str] = None,
        type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        user=Depends(get_current_user),
    ):
        query: dict[str, Any] = {"tenant_id": tenant_of(user)}
        if related_type:
            query["related_type"] = related_type
        if related_id:
            query["related_id"] = related_id
        if type:
            query["type"] = type
        limit = max(1, min(int(limit or 50), MAX_PAGE))
        offset = max(0, int(offset or 0))
        items = await db[ACTIVITIES].find(query, {"_id": 0}).sort(
            "occurred_at", -1).skip(offset).limit(limit).to_list(limit)
        return {"items": items, "total": await db[ACTIVITIES].count_documents(query),
                "limit": limit, "offset": offset}

    # -------------------------------------------------------------------- global search

    @router.get("/search")
    async def global_search(q: str = Query(min_length=1, max_length=200),
                           limit: int = 10, user=Depends(get_current_user)):
        """One box, every record type a person is likely to be looking for."""
        tenant = tenant_of(user)
        limit = max(1, min(int(limit or 10), 50))
        results: dict[str, list] = {}
        for collection, label in ((CONTACTS, "contacts"), (COMPANIES, "companies"),
                                  (DEALS, "deals"), (TASKS, "tasks")):
            query = {"tenant_id": tenant, **text_filter(collection, q),
                     **archive_filter(False)}
            results[label] = await db[collection].find(query, {"_id": 0}).sort(
                "created_at", -1).to_list(limit)
        results["total"] = sum(len(v) for v in results.values() if isinstance(v, list))
        results["query"] = q
        return results

    # -------------------------------------------------------------------- import/export

    EXPORTABLE = {
        "contacts": (CONTACTS, ["id", "name", "email", "phone", "title", "role",
                                "company_id", "owner", "created_at", "archived_at"]),
        "companies": (COMPANIES, ["id", "name", "industry", "website", "domain", "tier",
                                  "owner", "annual_value", "created_at", "archived_at"]),
        "deals": (DEALS, ["id", "name", "company_id", "value", "currency", "stage",
                          "owner", "expected_close_date", "created_at", "archived_at"]),
        "tasks": (TASKS, ["id", "title", "assignee", "due_date", "status", "priority",
                          "related_type", "related_id", "created_at"]),
    }

    @router.get("/export/{entity}")
    async def export_entity(entity: str, include_archived: bool = False,
                            user=Depends(get_current_user)):
        """Export one record type as CSV.

        A CRM you cannot get your data out of is a CRM you cannot trust, so this is a
        plain, complete, tenant-scoped dump rather than a sampled report.
        """
        if entity not in EXPORTABLE:
            raise HTTPException(status_code=404, detail="Unknown export")
        collection, columns = EXPORTABLE[entity]
        query = {"tenant_id": tenant_of(user), **archive_filter(include_archived)}
        rows = await db[collection].find(query, {"_id": 0}).sort(
            "created_at", -1).to_list(50000)
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})
        await record_event("data.exported", entity, entity, tenant_of(user),
                           user["email"], payload={"rows": len(rows)})
        return Response(
            content=buffer.getvalue(), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{entity}.csv"'})

    IMPORTABLE = {
        "contacts": (CONTACTS, "ct", ("name",),
                     ("name", "email", "phone", "title", "role", "company_id", "owner")),
        "companies": (COMPANIES, "co", ("name",),
                      ("name", "industry", "website", "domain", "tier", "owner")),
        "deals": (DEALS, "opp", ("name",),
                  ("name", "company_id", "value", "currency", "stage", "owner",
                   "expected_close_date")),
    }
    # What makes two rows "the same record" for import purposes.
    IMPORT_IDENTITY = {"contacts": "email", "companies": "name", "deals": "name"}

    @router.post("/import/{entity}")
    async def import_entity(entity: str, inp: ImportInput,
                            user=Depends(require_role("admin"))):
        """Import records from CSV.

        Deliberately strict: an unknown column, a row that fails validation, or a
        reference to a record in another tenant is reported per row rather than
        silently dropped. A half-finished import you cannot see is worse than a
        refused one.
        """
        if entity not in IMPORTABLE:
            raise HTTPException(status_code=404, detail="Unknown import")
        if inp.on_duplicate not in ("skip", "update", "create"):
            raise HTTPException(status_code=422,
                                detail="on_duplicate must be skip, update or create")
        collection, prefix, required, allowed = IMPORTABLE[entity]
        identity = IMPORT_IDENTITY[entity]
        tenant = tenant_of(user)

        try:
            reader = csv.DictReader(io.StringIO(inp.csv))
            rows = list(reader)
        except csv.Error as exc:
            raise HTTPException(status_code=422, detail=f"Could not parse CSV: {exc}")
        if not rows:
            raise HTTPException(status_code=422, detail="CSV contained no data rows")
        if len(rows) > MAX_IMPORT_ROWS:
            raise HTTPException(
                status_code=422,
                detail=f"Import is limited to {MAX_IMPORT_ROWS} rows per request")
        unknown_columns = [c for c in (reader.fieldnames or [])
                           if c and c.strip() not in allowed]
        if unknown_columns:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown column(s): {', '.join(sorted(set(unknown_columns))[:10])}")

        valid_stages = await stage_keys(db, tenant)
        created, updated, skipped, errors = 0, 0, 0, []

        for index, raw in enumerate(rows, start=2):  # row 1 is the header
            row = {k.strip(): (v.strip() if isinstance(v, str) else v)
                   for k, v in raw.items() if k and k.strip() in allowed}
            row = {k: v for k, v in row.items() if v not in (None, "")}
            missing = [field for field in required if not row.get(field)]
            if missing:
                errors.append({"row": index, "error": f"missing {', '.join(missing)}"})
                continue
            if entity == "deals":
                if row.get("stage") and row["stage"] not in valid_stages:
                    errors.append({"row": index,
                                   "error": f"unknown stage '{row['stage']}'"})
                    continue
                row.setdefault("stage", valid_stages[0])
                if row.get("value"):
                    try:
                        row["value"] = float(row["value"])
                    except ValueError:
                        errors.append({"row": index, "error": "value must be a number"})
                        continue
                if row.get("expected_close_date"):
                    try:
                        row["expected_close_date"] = _parse_date(
                            row["expected_close_date"], "expected_close_date")
                    except HTTPException:
                        errors.append({"row": index,
                                       "error": "expected_close_date must be ISO 8601"})
                        continue
            if row.get("company_id"):
                exists = await db[COMPANIES].find_one(
                    {"id": row["company_id"], "tenant_id": tenant}, {"_id": 1})
                if not exists:
                    errors.append({"row": index,
                                   "error": f"unknown company_id '{row['company_id']}'"})
                    continue

            existing = None
            if row.get(identity):
                existing = await db[collection].find_one(
                    {"tenant_id": tenant, identity: row[identity]}, {"_id": 0})
            if existing and inp.on_duplicate == "skip":
                skipped += 1
                continue
            if existing and inp.on_duplicate == "update":
                await db[collection].update_one(
                    {"id": existing["id"], "tenant_id": tenant},
                    {"$set": {**row, "updated_at": now_iso()},
                     "$push": {"history": _history_entry("imported", user["email"],
                                                         {"row": index})}})
                updated += 1
                continue
            doc = {"id": new_id(prefix), "tenant_id": tenant, "created_at": now_iso(),
                   "updated_at": now_iso(), "archived_at": None,
                   "history": [_history_entry("imported", user["email"], {"row": index})],
                   **row}
            await db[collection].insert_one(doc)
            created += 1

        await record_event("data.imported", entity, entity, tenant, user["email"],
                           payload={"created": created, "updated": updated,
                                    "skipped": skipped, "rejected": len(errors)})
        return {"entity": entity, "created": created, "updated": updated,
                "skipped": skipped, "rejected": len(errors),
                # Capped so one bad file cannot return a megabyte of errors, but the
                # count above is always the true total.
                "errors": errors[:100]}

    return {"resolve_stages": resolve_stages, "stage_keys": stage_keys}
