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
import logging
import math
import re
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, HTTPException, Query, Response
from pydantic import BaseModel, EmailStr, Field, field_validator

import record_fields

logger = logging.getLogger("clientverse.crm_core")

# --------------------------------------------------------------------------- constants

CONTACTS = "contacts"
COMPANIES = "companies"
DEALS = "opportunities"

# A deal's money: finite, never negative, below an absurd ceiling, in an ISO 4217 code.
# The same bounds a recovery case puts on a potential value, so a deal that saves here
# can always be booked when it is won.
MAX_DEAL_VALUE = 1e10
CURRENCY_PATTERN = r"^[A-Z]{3}$"
TASKS = "tasks"
ACTIVITIES = "crm_activities"
PIPELINES = "pipelines"
# `website_forms.FORMS`. Named here rather than imported because website_forms imports
# this module; the pipeline only reads which stage each form sends its new deals to.
WEBSITE_FORMS = "website_forms"

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

ACTIVITY_TYPES = ("note", "call", "meeting", "email", "text", "status_change")
# The activity types that mean somebody reached out to the person. A note is a person
# writing something down; it is not contact, and it must never stop a lead's clock.
OUTREACH_TYPES = ("call", "email", "meeting", "text")
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
    CONTACTS: ("created_at", "updated_at", "name", "owner", "lifecycle"),
    COMPANIES: ("created_at", "updated_at", "name", "owner"),
    DEALS: ("created_at", "updated_at", "name", "value", "stage", "expected_close_date", "owner"),
    TASKS: ("created_at", "updated_at", "due_date", "status", "assignee", "title",
            "completed_at"),
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


def csv_safe(value: Any) -> Any:
    """Neutralise a cell a spreadsheet would execute as a formula.

    Website visitors can now put text into contacts and leads, and a name like
    `=HYPERLINK(...)` would run when an agent opens the export in Excel or Sheets.
    """
    if value is None:
        return ""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _escape_regex(value: str) -> str:
    return re.escape(value.strip())[:200]


def phone_digits(value: Optional[str]) -> str:
    """The comparable part of a phone number: its last ten digits.

    Stored beside the number as typed so a website lead from "555.010.0100" finds the
    contact someone entered as "(555) 010-0100".
    """
    return re.sub(r"\D", "", str(value or ""))[-10:]


async def display_names(db, tenant_id: str, emails: Iterable[Optional[str]]) -> dict[str, str]:
    """Each teammate's name, keyed by the email address it was asked for.

    Records store who did something as an email address, which is right for an audit
    trail and wrong for a person reading it. Only members of `tenant_id` are resolved,
    so an address on a record can never be used to read another tenant's user names;
    anything else (a system actor, a former teammate with no name) is simply absent and
    the caller shows the address it already has.
    """
    wanted = {str(email): str(email).strip().lower() for email in emails
              if email and "@" in str(email)}
    if not wanted:
        return {}
    members = await db.memberships.find(
        {"tenant_id": tenant_id}, {"_id": 0, "email": 1, "user_id": 1}).to_list(500)
    user_ids = {str(m.get("email") or "").lower(): m["user_id"]
                for m in members if m.get("user_id")}
    ids = sorted({user_ids[lowered] for lowered in wanted.values() if lowered in user_ids})
    if not ids:
        return {}
    users = await db.users.find(
        {"user_id": {"$in": ids}}, {"_id": 0, "user_id": 1, "name": 1}).to_list(len(ids))
    names = {u["user_id"]: str(u["name"]).strip() for u in users if u.get("name")}
    return {email: names[user_ids[lowered]] for email, lowered in wanted.items()
            if lowered in user_ids and user_ids[lowered] in names}


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
    await db[CONTACTS].create_index([("tenant_id", 1), ("lifecycle", 1)])
    await db[record_fields.FIELD_DEFS].create_index(
        [("tenant_id", 1), ("object", 1), ("key", 1)], unique=True)
    await db[record_fields.SAVED_VIEWS].create_index([("tenant_id", 1), ("object", 1), ("owner", 1)])


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
                        include_archived: bool = False,
                        conditions: Optional[list[dict]] = None) -> list[dict]:
    """Search, filter and sort one collection inside one tenant.

    Returns a bare list because the endpoints that use it always have: the directory
    surfaces and existing integrations read an array, and changing that shape to carry
    pagination metadata would break them for no benefit they asked for.

    Only the fields named in SEARCHABLE / SORTABLE are reachable. A caller cannot steer
    a query at a field it has no business reading, and cannot sort by one either.
    `conditions` are a saved view's filters, already checked by `record_fields`.
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
    if conditions:
        query["$and"] = conditions
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


# Stage names the product shipped with before pipelines were configurable. They are only
# consulted for a deal whose stage the tenant's pipeline no longer contains, so a legacy
# record is still classified rather than silently treated as open revenue.
LEGACY_WON_STAGES = ("closed_won", "won")
LEGACY_LOST_STAGES = ("closed_lost", "lost")

STAGE_OPEN = "open"
STAGE_WON = "won"
STAGE_LOST = "lost"


async def stage_classes(db, tenant_id: str) -> dict[str, set[str]]:
    """Which of this tenant's stage keys are open, closed-won and closed-lost.

    Read from the tenant's own pipeline, because a tenant that renamed "closed_won" to
    "signed" has still won the deal. Anything that decides whether a deal is revenue,
    pipeline or lost must ask this rather than compare against a hard-coded name.
    """
    stages = await resolve_stages(db, tenant_id)
    return {
        STAGE_WON: {s["key"] for s in stages if s.get("is_closed") and s.get("is_won")},
        STAGE_LOST: {s["key"] for s in stages if s.get("is_closed") and not s.get("is_won")},
        STAGE_OPEN: {s["key"] for s in stages if not s.get("is_closed")},
    }


def classify_stage(stage: Optional[str], classes: dict[str, set[str]]) -> str:
    """Classify one deal stage as open, won or lost for the tenant `classes` came from.

    A stage the pipeline does not contain falls back to the shipped names and otherwise
    counts as open: an unknown stage is live until something says it closed.
    """
    key = str(stage or "")
    for outcome in (STAGE_WON, STAGE_LOST, STAGE_OPEN):
        if key in classes.get(outcome, set()):
            return outcome
    lowered = key.lower()
    if lowered in LEGACY_WON_STAGES:
        return STAGE_WON
    if lowered in LEGACY_LOST_STAGES:
        return STAGE_LOST
    return STAGE_OPEN


def stage_outcome(stage: dict) -> str:
    """Whether one configured stage is open, closed-won or closed-lost.

    The same rule `stage_classes` applies, for a single stage definition: `is_won` only
    counts on a closed stage.
    """
    if not stage.get("is_closed"):
        return STAGE_OPEN
    return STAGE_WON if stage.get("is_won") else STAGE_LOST


# ------------------------------------------------------- companies, clients, duplicates

# Addresses at these domains belong to a person, not to a company, so they never link
# a contact to a company and never name a new one.
FREE_MAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "outlook.com", "hotmail.com",
    "live.com", "msn.com", "icloud.com", "me.com", "mac.com", "aol.com", "proton.me",
    "protonmail.com", "gmx.com", "gmx.net", "mail.com", "yandex.com", "zoho.com",
    "fastmail.com", "hey.com", "comcast.net", "verizon.net", "att.net", "sbcglobal.net",
})


def business_domain(email: Optional[str]) -> Optional[str]:
    """The company domain an email address points at, or None for a personal address."""
    text = str(email or "").strip().lower()
    if "@" not in text:
        return None
    domain = text.rsplit("@", 1)[1].strip(". ")
    if not domain or "." not in domain or domain in FREE_MAIL_DOMAINS:
        return None
    return domain


def website_domain(value: Optional[str]) -> Optional[str]:
    """`https://www.acme.com/about` -> `acme.com`; anything unparseable -> None."""
    text = str(value or "").strip().lower()
    if not text:
        return None
    text = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text).split("/", 1)[0].split(":", 1)[0]
    text = text[4:] if text.startswith("www.") else text
    return text if "." in text else None


async def find_company(db, tenant_id: str, *, name: Optional[str] = None,
                       domain: Optional[str] = None) -> Optional[dict]:
    """A live company with exactly this name (any case), else one on this domain."""
    base = {"tenant_id": tenant_id, "archived_at": None}
    clean = str(name or "").strip()
    if clean:
        found = await db[COMPANIES].find_one(
            {**base, "name": {"$regex": f"^{re.escape(clean)}$", "$options": "i"}}, {"_id": 0})
        if found:
            return found
    if domain:
        found = await db[COMPANIES].find_one(
            {**base, "$or": [{"domain": domain},
                             {"website": {"$regex": rf"(^|[/.]){re.escape(domain)}(/|$)",
                                          "$options": "i"}}]}, {"_id": 0})
        if found:
            return found
    return None


async def link_contact_company(db, tenant_id: str, contact: dict, company_name: Optional[str],
                               *, new_id: Callable[[str], str], now_iso: Callable[[], str],
                               actor: str, record_event=None) -> tuple[Optional[str], str]:
    """Attach a contact to its company: matched by name, then by email domain, or created
    from the name the person typed. A contact that already has a company keeps it.

    Returns (company_id or None, how) where how is kept / matched / created / none.
    """
    if contact.get("company_id"):
        return contact["company_id"], "kept"
    name = str(company_name or "").strip()[:200]
    domain = business_domain(contact.get("email"))
    company = await find_company(db, tenant_id, name=name or None, domain=domain)
    how = "matched"
    if not company and name:
        now = now_iso()
        company = {"id": new_id("co"), "tenant_id": tenant_id, "name": name,
                   "industry": None, "website": None, "domain": domain, "tier": None,
                   "owner": contact.get("owner"), "created_at": now, "updated_at": now,
                   "archived_at": None, "source": {"kind": "contact", "contact_id": contact["id"]},
                   "history": [created_history(actor)]}
        await db[COMPANIES].insert_one(dict(company))
        if record_event:
            await record_event("company.created", "company", company["id"], tenant_id, actor,
                               payload={"name": name, "from": "contact"})
        how = "created"
    if not company:
        return None, "none"
    await db[CONTACTS].update_one(
        {"id": contact["id"], "tenant_id": tenant_id, "company_id": None},
        {"$set": {"company_id": company["id"], "updated_at": now_iso()},
         "$push": {"history": _history_entry("company_linked", actor,
                                             {"company_id": company["id"], "how": how})}})
    return company["id"], how


async def is_existing_client(db, tenant_id: str, contact: dict) -> bool:
    """True when the business already serves this person: their company has a client
    workspace, or they are on a won deal. Client work is not a new lead to win."""
    if contact.get("company_id") and await db.workspaces.find_one(
            {"tenant_id": tenant_id, "company_id": contact["company_id"],
             "archived_at": None}, {"_id": 1}):
        return True
    won = (await stage_classes(db, tenant_id))[STAGE_WON] | set(LEGACY_WON_STAGES)
    return bool(await db[DEALS].find_one(
        {"tenant_id": tenant_id, "contact_ids": contact["id"], "stage": {"$in": list(won)},
         "archived_at": None}, {"_id": 1}))


def _name_key(name: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()


# Where a contact's id is recorded, so a merge can move every reference at once.
# (collection, field, kind): kind "value" is a scalar field, "array" a list of ids,
# "related" a related_type/related_id pair.
CONTACT_REFERENCES = (
    (DEALS, "contact_ids", "array"),
    (TASKS, "related_id", "related"),
    (ACTIVITIES, "related_id", "related"),
    ("web_enquiries", "contact_id", "value"),
    ("appointments", "contact_id", "value"),
    ("conversations", "contact_id", "value"),
    ("crm_communications", "contact_ids", "array"),
)


# Where a person stands with the business. Set by hand, or by the CRM: a website lead
# starts as "lead", and winning a deal makes everyone on it a "customer".
LIFECYCLE_STAGES = ("lead", "qualified", "customer", "former_customer", "partner", "other")


async def promote_to_customers(db, tenant_id: str, contact_ids: Iterable[str], actor: str) -> int:
    """Everyone on a won deal is a customer, unless someone already said otherwise
    (a partner stays a partner). Called wherever a person can end up on a won deal: the
    deal is moved to won, created already won, or has people added once won."""
    ids = [cid for cid in dict.fromkeys(contact_ids) if cid]
    if not ids:
        return 0
    result = await db[CONTACTS].update_many(
        {"tenant_id": tenant_id, "id": {"$in": ids}, "lifecycle": {"$in": [None, "lead", "qualified"]}},
        {"$set": {"lifecycle": "customer", "updated_at": _iso()},
         "$push": {"history": _history_entry("lifecycle_set", actor, {"lifecycle": "customer", "how": "deal won"})}})
    return result.modified_count


async def is_won_stage(db, tenant_id: str, stage: Optional[str]) -> bool:
    return classify_stage(stage, await stage_classes(db, tenant_id)) == STAGE_WON


def check_lifecycle(value: Optional[str]) -> Optional[str]:
    if value is not None and value not in LIFECYCLE_STAGES:
        raise ValueError(f"lifecycle must be one of {', '.join(LIFECYCLE_STAGES)}")
    return value


# ------------------------------------------------------------------- request payloads

class CleanupApply(BaseModel):
    action: str = Field(pattern="^(create_typed_companies|link_by_domain|set_lifecycle)$")
    contact_ids: Optional[list[str]] = Field(default=None, max_length=500)


class MergeInput(BaseModel):
    into_id: str = Field(min_length=1, max_length=80)


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
    lifecycle: Optional[str] = None
    custom_fields: Optional[dict] = None

    @field_validator("lifecycle")
    @classmethod
    def _lifecycle_known(cls, value: Optional[str]) -> Optional[str]:
        return check_lifecycle(value)


class CompanyPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    industry: Optional[str] = Field(default=None, max_length=160)
    website: Optional[str] = Field(default=None, max_length=300)
    domain: Optional[str] = Field(default=None, max_length=200)
    tier: Optional[str] = Field(default=None, max_length=60)
    owner: Optional[str] = Field(default=None, max_length=200)
    annual_value: Optional[float] = Field(default=None, ge=0)
    custom_fields: Optional[dict] = None


class DealPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    company_id: Optional[str] = None
    contact_ids: Optional[list[str]] = None
    # Finite as well as non-negative: `ge=0` alone admits Infinity, which no JSON
    # response can carry, so one bad patch would break every listing of this deal.
    value: Optional[float] = Field(default=None, ge=0, le=MAX_DEAL_VALUE, allow_inf_nan=False)
    # ISO 4217, stored uppercase. "$" saved here used to make every later win of the deal
    # unbookable, and the recovery sweep re-raised that error on every run.
    currency: Optional[str] = Field(default=None, pattern=CURRENCY_PATTERN)
    owner: Optional[str] = Field(default=None, max_length=200)
    expected_close_date: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=4000)
    custom_fields: Optional[dict] = None

    @field_validator("currency", mode="before")
    @classmethod
    def _uppercase_currency(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


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
                             get_current_user, require_role,
                             on_activity_logged: Optional[
                                 Callable[[dict], Awaitable[Any]]] = None,
                             *, on_task_status_changed=None):
    """Attach the baseline CRM routes, using the application's own helpers.

    Injection rather than import keeps this module free of a circular dependency on
    `server`, and keeps every audit event flowing through the one `record_event` the
    rest of the application uses. `on_activity_logged` is told about every activity a
    person logs, after it is stored, so work that depends on it (a lead's speed-to-lead
    clock) moves at once instead of on the next sweep. `on_task_status_changed(task,
    previous_status, actor)` is awaited after a task changes status through
    `PATCH /crm/tasks/{id}`.
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

    async def patch_with_custom(collection: str, object_name: str, record_id: str, user,
                                changes: dict, event_type: str, resource_type: str) -> dict:
        """`apply_patch`, plus admin-defined field values checked against their types.

        Custom values are compared and stored one key at a time under `custom_fields.`,
        so setting one field never overwrites the answers a website form captured.
        """
        values = changes.pop("custom_fields", None)
        if values:
            updates = await record_fields.value_updates(db, tenant_of(user), object_name, values)
            existing = await load(collection, record_id, user)
            current = existing.get("custom_fields") or {}
            changed = {k: v for k, v in updates.items() if current.get(k) != v}
            if changed:
                await db[collection].update_one(
                    {"id": record_id, "tenant_id": tenant_of(user)},
                    {"$set": {**{f"custom_fields.{k}": v for k, v in changed.items()},
                              "updated_at": now_iso()},
                     "$push": {"history": _history_entry(
                         "updated", user["email"],
                         {"changed": [f"custom_fields.{k}" for k in sorted(changed)],
                          "from": {f"custom_fields.{k}": current.get(k) for k in changed}})}})
                await record_event(event_type, resource_type, record_id, tenant_of(user),
                                   user["email"],
                                   payload={"changed": [f"custom_fields.{k}" for k in sorted(changed)]})
        return await apply_patch(collection, record_id, user, changes, event_type, resource_type)

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
             "outcome": item.get("outcome"), "direction": item.get("direction")}
            for item in activities
        ] + [
            {"kind": "event", "at": item.get("timestamp"), "type": item.get("event_type"),
             "subject": None, "body": None, "actor": item.get("actor"),
             "id": item.get("id"), "payload": item.get("payload")}
            for item in events
        ]
        merged.sort(key=lambda entry: entry.get("at") or "", reverse=True)
        merged = merged[:limit]
        # Who did it, as a name a person recognises. The address stays on `actor`.
        names = await display_names(db, tenant_of(user),
                                    (entry.get("actor") for entry in merged))
        for entry in merged:
            entry["actor_name"] = names.get(entry.get("actor") or "")
        return merged

    # ------------------------------------------------------------------------ contacts

    # ---------------------------------------------------------------- clean-up

    async def cleanup_scan(tenant: str) -> dict:
        contacts = await db[CONTACTS].find(
            {"tenant_id": tenant, "archived_at": None},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "company_id": 1, "custom_fields": 1,
             "created_at": 1, "lifecycle": 1, "last_inquiry_at": 1}).to_list(5000)
        companies = await db[COMPANIES].find(
            {"tenant_id": tenant, "archived_at": None},
            {"_id": 0, "id": 1, "name": 1, "domain": 1, "website": 1}).to_list(5000)
        by_domain: dict[str, dict] = {}
        by_name = {_name_key(c.get("name")): c for c in companies if c.get("name")}
        for company in companies:
            for domain in (company.get("domain"), website_domain(company.get("website"))):
                if domain:
                    by_domain.setdefault(str(domain).lower(), company)
        # Company names people typed into a form, for contacts not yet linked to one.
        typed: dict[str, dict] = {}
        domain_matches = []
        for contact in contacts:
            if contact.get("company_id"):
                continue
            custom = contact.get("custom_fields") or {}
            name = next((str(custom[k]).strip() for k in ("company", "custom_company", "company_name")
                         if str(custom.get(k) or "").strip()), "")
            domain = business_domain(contact.get("email"))
            if name:
                group = typed.setdefault(_name_key(name), {
                    "name": name[:200], "contact_ids": [],
                    "existing_company_id": (by_name.get(_name_key(name)) or {}).get("id")})
                group["contact_ids"].append(contact["id"])
            elif domain and domain in by_domain:
                company = by_domain[domain]
                domain_matches.append({"contact_id": contact["id"], "contact_name": contact.get("name"),
                                       "company_id": company["id"], "company_name": company.get("name"),
                                       "domain": domain})
        groups: dict[str, list[dict]] = {}
        for contact in contacts:
            email = str(contact.get("email") or "").strip().lower()
            if email:
                groups.setdefault(f"email:{email}", []).append(contact)
        grouped = {c["id"] for members in groups.values() if len(members) > 1 for c in members}
        for contact in contacts:
            key = _name_key(contact.get("name"))
            if key and contact["id"] not in grouped:
                groups.setdefault(f"name:{key}", []).append(contact)
        duplicates = [
            {"reason": "same email" if key.startswith("email:") else "same name",
             "contacts": [{k: c.get(k) for k in ("id", "name", "email", "company_id", "created_at")}
                          for c in sorted(members, key=lambda c: c.get("created_at") or "")]}
            for key, members in groups.items() if len(members) > 1][:50]
        return {"typed_companies": list(typed.values())[:100],
                "domain_matches": domain_matches[:100], "duplicates": duplicates,
                "lifecycle": await lifecycle_suggestions(tenant, contacts)}

    async def lifecycle_suggestions(tenant: str, contacts: list[dict]) -> dict:
        """A lifecycle stage for people who have none, read from their history: on a won
        deal or at a company with a client workspace -> customer; on an open deal or with a
        website enquiry -> lead. Anyone else is left for a person to decide."""
        unset = [c for c in contacts if not c.get("lifecycle")]
        if not unset:
            return {"customer": [], "lead": []}
        classes = await stage_classes(db, tenant)
        won = classes[STAGE_WON] | set(LEGACY_WON_STAGES)
        closed = won | classes[STAGE_LOST] | set(LEGACY_LOST_STAGES)
        deals = await db[DEALS].find(
            {"tenant_id": tenant, "archived_at": None, "contact_ids": {"$in": [c["id"] for c in unset]}},
            {"_id": 0, "contact_ids": 1, "stage": 1}).to_list(10000)
        on_won = {cid for d in deals if d.get("stage") in won for cid in d.get("contact_ids") or []}
        on_open = {cid for d in deals if d.get("stage") not in closed for cid in d.get("contact_ids") or []}
        served = {w["company_id"] for w in await db.workspaces.find(
            {"tenant_id": tenant, "archived_at": None, "company_id": {"$ne": None}},
            {"_id": 0, "company_id": 1}).to_list(5000)}
        customer, lead = [], []
        for contact in unset:
            if contact["id"] in on_won or (contact.get("company_id") in served):
                customer.append(contact["id"])
            elif contact["id"] in on_open or contact.get("last_inquiry_at"):
                lead.append(contact["id"])
        return {"customer": customer[:1000], "lead": lead[:1000]}

    @router.get("/contacts/cleanup")
    async def contacts_cleanup(user=Depends(get_current_user)):
        """What would tidy the contact list: companies typed in forms but never created,
        contacts whose work email matches a company, and people entered twice."""
        return await cleanup_scan(tenant_of(user))

    @router.post("/contacts/cleanup/apply")
    async def contacts_cleanup_apply(inp: CleanupApply, user=Depends(get_current_user)):
        tenant = tenant_of(user)
        scan = await cleanup_scan(tenant)
        wanted = set(inp.contact_ids or [])
        linked = created = 0
        if inp.action == "create_typed_companies":
            for group in scan["typed_companies"]:
                for contact_id in group["contact_ids"]:
                    if wanted and contact_id not in wanted:
                        continue
                    contact = await db[CONTACTS].find_one(
                        {"id": contact_id, "tenant_id": tenant}, {"_id": 0})
                    if not contact:
                        continue
                    company_id, how = await link_contact_company(
                        db, tenant, contact, group["name"], new_id=new_id, now_iso=now_iso,
                        actor=user["email"], record_event=record_event)
                    linked += bool(company_id)
                    created += how == "created"
        elif inp.action == "set_lifecycle":
            for stage in ("customer", "lead"):
                ids = [cid for cid in scan["lifecycle"][stage] if not wanted or cid in wanted]
                if not ids:
                    continue
                # Only people still without a stage: one set by hand meanwhile stays.
                result = await db[CONTACTS].update_many(
                    {"tenant_id": tenant, "id": {"$in": ids}, "lifecycle": None},
                    {"$set": {"lifecycle": stage, "updated_at": now_iso()},
                     "$push": {"history": _history_entry("lifecycle_set", user["email"],
                                                         {"lifecycle": stage, "how": "clean-up"})}})
                linked += result.modified_count
        else:
            for match in scan["domain_matches"]:
                if wanted and match["contact_id"] not in wanted:
                    continue
                result = await db[CONTACTS].update_one(
                    {"id": match["contact_id"], "tenant_id": tenant, "company_id": None},
                    {"$set": {"company_id": match["company_id"], "updated_at": now_iso()},
                     "$push": {"history": _history_entry("company_linked", user["email"],
                                                         {"company_id": match["company_id"],
                                                          "how": "email domain"})}})
                linked += result.modified_count
        await record_event("contacts.cleaned_up", "contact", tenant, tenant, user["email"],
                           payload={"action": inp.action, "linked": linked, "created": created})
        return {"action": inp.action, "linked": linked, "created_companies": created}

    async def mark_merging(tenant: str, source_id: str, target_id: str) -> None:
        """Record the destination before anything moves, so a merge that stops part-way
        is recognised as the same merge when it is run again."""
        await db[CONTACTS].update_one({"id": source_id, "tenant_id": tenant},
                                      {"$set": {"merged_into": target_id}})

    @router.post("/contacts/{contact_id}/merge")
    async def merge_contact(contact_id: str, inp: MergeInput, user=Depends(get_current_user)):
        """Fold one contact into another: every deal, task, activity, enquiry, appointment
        and conversation moves to the kept record, which fills its empty fields from the
        duplicate. The duplicate is archived with `merged_into`, so it can be found.

        Every step is safe to repeat, so a merge interrupted part-way is finished by
        running it again: references already moved simply match nothing."""
        if inp.into_id == contact_id:
            raise HTTPException(status_code=422, detail="Choose a different contact to merge into")
        tenant = tenant_of(user)
        source = await load(CONTACTS, contact_id, user)
        target = await load(CONTACTS, inp.into_id, user)
        if target.get("archived_at"):
            raise HTTPException(status_code=422, detail="Restore the contact you are keeping first")
        if source.get("merged_into") and source["merged_into"] != target["id"]:
            raise HTTPException(status_code=422, detail="That contact was already merged into another one")
        # A repeat of a finished or interrupted merge: the fields and inquiries were
        # already folded in, so only the references and the archive step run again.
        repeat = source.get("merged_into") == target["id"]
        now = now_iso()
        sets: dict[str, Any] = {"updated_at": now}
        for key in ("email", "phone", "phone_digits", "title", "role", "company_id", "owner",
                    "consent", "lead_source", "source"):
            if not target.get(key) and source.get(key):
                sets[key] = source[key]
        for key, value in (source.get("custom_fields") or {}).items():
            if (target.get("custom_fields") or {}).get(key) in (None, ""):
                sets[f"custom_fields.{key}"] = value
        if not repeat:
            await mark_merging(tenant, source["id"], target["id"])
        await db[CONTACTS].update_one(
            {"id": target["id"], "tenant_id": tenant},
            {"$set": sets} if repeat else {"$set": sets,
             "$addToSet": {"tags": {"$each": list(source.get("tags") or [])}},
             "$push": {"inquiries": {"$each": list(source.get("inquiries") or []), "$slice": -50},
                       "history": _history_entry("merged", user["email"],
                                                 {"merged_contact_id": source["id"],
                                                  "merged_name": source.get("name")})}})
        moved: dict[str, int] = {}
        for collection, field, kind in CONTACT_REFERENCES:
            if kind == "related":
                result = await db[collection].update_many(
                    {"tenant_id": tenant, "related_type": "contact", field: source["id"]},
                    {"$set": {field: target["id"]}})
                moved[collection] = result.modified_count
            elif kind == "value":
                result = await db[collection].update_many(
                    {"tenant_id": tenant, field: source["id"]}, {"$set": {field: target["id"]}})
                moved[collection] = result.modified_count
            else:
                count = 0
                async for row in db[collection].find({"tenant_id": tenant, field: source["id"]},
                                                     {"_id": 0, "id": 1, field: 1}):
                    ids = [target["id"] if i == source["id"] else i for i in row.get(field) or []]
                    await db[collection].update_one(
                        {"id": row["id"], "tenant_id": tenant},
                        {"$set": {field: list(dict.fromkeys(ids))}})
                    count += 1
                moved[collection] = count
        count = 0
        async for row in db.conversations.find(
                {"tenant_id": tenant,
                 "participants": {"$elemMatch": {"kind": "contact", "id": source["id"]}}},
                {"_id": 0, "id": 1, "participants": 1}):
            participants = [
                {**p, "id": target["id"]} if p.get("kind") == "contact" and p.get("id") == source["id"]
                else p for p in row.get("participants") or []]
            await db.conversations.update_one({"id": row["id"], "tenant_id": tenant},
                                              {"$set": {"participants": participants}})
            count += 1
        moved["conversation participants"] = count
        await db[CONTACTS].update_one(
            {"id": source["id"], "tenant_id": tenant},
            {"$set": {"archived_at": now, "merged_into": target["id"], "updated_at": now},
             "$push": {"history": _history_entry("merged_into", user["email"],
                                                 {"contact_id": target["id"]})}})
        await record_event("contact.merged", "contact", target["id"], tenant, user["email"],
                           payload={"merged_contact_id": source["id"], "moved": moved})
        kept = await db[CONTACTS].find_one({"id": target["id"], "tenant_id": tenant}, {"_id": 0})
        return {"contact": kept, "merged_contact_id": source["id"], "moved": moved}

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
            {"tenant_id": tenant,
             "$or": [{"contact_id": contact_id},
                     {"participants": {"$elemMatch": {"kind": "contact",
                                                      "id": contact_id}}}]},
            {"_id": 0}).sort("last_message_at", -1).to_list(25)
        owner_names = await display_names(db, tenant, [contact.get("owner")])
        return {"contact": contact, "company": company, "deals": deals, "tasks": tasks,
                "conversations": conversations,
                "owner_name": owner_names.get(contact.get("owner") or ""),
                "timeline": await timeline_for(user, "contact", contact_id)}

    @router.patch("/contacts/{contact_id}")
    async def update_contact(contact_id: str, inp: ContactPatch,
                             user=Depends(get_current_user)):
        changes = dict(inp.model_dump(exclude_unset=True))
        if "email" in changes and changes["email"] is not None:
            changes["email"] = str(changes["email"])
        if "phone" in changes:
            # Kept in step with the number, or the next website lead from this person
            # would be matched against the number they used to have.
            changes["phone"] = (changes["phone"] or "").strip() or None
            changes["phone_digits"] = phone_digits(changes["phone"]) or None
        await assert_exists(COMPANIES, changes.get("company_id"), user, "company_id")
        return await patch_with_custom(CONTACTS, "contacts", contact_id, user, changes,
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
        # Open and won follow the tenant's own stages: an industry template's "Won" or
        # "Closed" is a win, and its "Lost" is not open pipeline.
        classes = await stage_classes(db, tenant)
        open_deals = [deal for deal in deals if classify_stage(deal.get("stage"), classes) == STAGE_OPEN]
        won = [deal for deal in deals if classify_stage(deal.get("stage"), classes) == STAGE_WON]
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
        return await patch_with_custom(COMPANIES, "companies", company_id, user, changes,
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

    # Registered before `/opportunities/{deal_id}` so the path is not read as a deal id.
    @router.get("/opportunities/owner-options")
    async def deal_owner_options(user=Depends(get_current_user)):
        """The people a deal can be given to: this tenant's active members.

        Names and emails only. A member needs this to hand a deal to a colleague; roles,
        status and invitations stay on the admin-only team page.
        """
        tenant = tenant_of(user)
        members = await db.memberships.find(
            {"tenant_id": tenant, "status": "active"},
            {"_id": 0, "user_id": 1, "email": 1}).sort("created_at", 1).to_list(500)
        user_ids = [m["user_id"] for m in members if m.get("user_id")]
        people = await db.users.find(
            {"user_id": {"$in": user_ids}}, {"_id": 0, "user_id": 1, "name": 1}
        ).to_list(len(user_ids) or 1)
        names = {person["user_id"]: person.get("name") for person in people}
        options = [{"email": m["email"], "name": names.get(m.get("user_id")) or None}
                   for m in members if m.get("email")]
        if not any(option["email"] == user["email"] for option in options):
            options.insert(0, {"email": user["email"], "name": user.get("name")})
        return {"items": options}

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
        deal = await patch_with_custom(DEALS, "deals", deal_id, user, changes,
                                       "opportunity.updated", "opportunity")
        if changes.get("contact_ids") and await is_won_stage(db, tenant_of(user), deal.get("stage")):
            await promote_to_customers(db, tenant_of(user), changes["contact_ids"], user["email"])
        return deal

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

    async def stage_usage(tenant: str, keys: list[str]) -> dict[str, dict]:
        """What depends on each stage: the deals in it and the website forms feeding it.

        Archived deals count. Restoring one would otherwise put it back in a stage the
        pipeline no longer has, or in one that now means something else. A website form
        counts unless it is archived: a paused form can be switched back on.
        """
        usage: dict[str, dict] = {key: {"deals": 0, "archived_deals": 0, "website_forms": []}
                                  for key in keys}
        if not keys:
            return usage
        for key in keys:
            scope = {"tenant_id": tenant, "stage": key}
            usage[key]["deals"] = await db[DEALS].count_documents(scope)
            usage[key]["archived_deals"] = await db[DEALS].count_documents(
                {**scope, "archived_at": {"$ne": None}})
        forms = await db[WEBSITE_FORMS].find(
            {"tenant_id": tenant, "status": {"$ne": "archived"},
             "settings.opportunity.stage": {"$in": keys}},
            {"_id": 0, "id": 1, "name": 1, "settings": 1}).to_list(200)
        for form in forms:
            target = ((form.get("settings") or {}).get("opportunity") or {}).get("stage")
            if target in usage:
                usage[target]["website_forms"].append(
                    {"id": form.get("id"), "name": form.get("name")})
        return usage

    def deals_phrase(usage: dict) -> str:
        total, archived = usage["deals"], usage["archived_deals"]
        noun = "deal" if total == 1 else "deals"
        if archived and archived == total:
            return f"{total} archived {noun}"
        if archived:
            return f"{total} {noun} ({archived} archived)"
        return f"{total} {noun}"

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
                "totals": counts,
                # What the stage editor needs to say up front which stages cannot be
                # removed or reclassified, instead of finding out from a refusal.
                "in_use": await stage_usage(tenant_of(user),
                                            [stage["key"] for stage in stages])}

    @router.put("/pipelines/default")
    async def set_pipeline(inp: PipelineInput, user=Depends(require_role("admin"))):
        """Configure this tenant's stages.

        Three changes are refused, because each would change deals nobody touched:

        * removing a stage that still holds deals. Rewriting the stage set out from under
          live records would leave them in a stage the pipeline does not have, which is
          how a deal becomes invisible;
        * switching a stage that holds deals between open, won and lost. Every deal in it
          would become revenue, or be written off, without anyone moving it -- and the
          recovery engine settles its cases on exactly that classification;
        * removing or closing a stage a website form sends its new leads to. The form
          would quietly start filing leads somewhere else.
        """
        stages = [stage.model_dump() for stage in inp.stages]
        for stage in stages:
            stage["label"] = stage["label"].strip()
            if not stage["label"]:
                raise HTTPException(status_code=422, detail="Every stage needs a name")
        keys = [stage["key"] for stage in stages]
        if len(set(keys)) != len(keys):
            raise HTTPException(status_code=422, detail="Stage keys must be unique")
        if not any(stage["is_closed"] and stage["is_won"] for stage in stages):
            raise HTTPException(status_code=422,
                                detail="At least one stage must be a closed-won stage")
        if not any(stage_outcome(stage) == STAGE_OPEN for stage in stages):
            raise HTTPException(
                status_code=422,
                detail="Keep at least one open stage: new deals and website leads start there")
        tenant = tenant_of(user)
        previous = {stage["key"]: stage for stage in await resolve_stages(db, tenant)}
        removed = [key for key in previous if key not in keys]
        reclassified = [stage["key"] for stage in stages if stage["key"] in previous
                        and stage_outcome(stage) != stage_outcome(previous[stage["key"]])]
        newly_closed = [key for key in reclassified
                        if stage_outcome(previous[key]) == STAGE_OPEN]
        usage = await stage_usage(tenant, removed + reclassified)
        # The name the admin knows the stage by, which is the old one if it was renamed.
        labels = {key: stage.get("label") or key for key, stage in previous.items()}
        problems: list[str] = []
        for key in removed:
            if usage[key]["deals"]:
                problems.append(
                    f"“{labels[key]}” still has {deals_phrase(usage[key])}. "
                    "Move them to another stage before removing it.")
        for key in reclassified:
            if usage[key]["deals"]:
                problems.append(
                    f"“{labels[key]}” has {deals_phrase(usage[key])}, so it cannot switch "
                    "between open, won and lost: that would change those deals without "
                    "anyone moving them. Move them to another stage first.")
        for key in removed + newly_closed:
            for form in usage[key]["website_forms"]:
                problems.append(
                    f"Your website form “{form['name']}” puts new leads in "
                    f"“{labels[key]}”. Choose a different starting stage for that form first.")
        if problems:
            raise HTTPException(status_code=409, detail=" ".join(problems))
        await db[PIPELINES].update_one(
            {"tenant_id": tenant, "id": "default"},
            {"$set": {"stages": stages, "updated_at": now_iso(),
                      "updated_by": user["email"]},
             "$setOnInsert": {"created_at": now_iso()}},
            upsert=True)
        await record_event("pipeline.configured", "pipeline", "default",
                           tenant, user["email"],
                           payload={"stages": keys, "removed": removed,
                                    "reclassified": reclassified})
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

    def same_person(first: Optional[str], second: Optional[str]) -> bool:
        return bool(first and second) and str(first).strip().lower() == str(second).strip().lower()

    def email_match(email: str) -> dict:
        # Assignees are typed by people and written by automation, so the case an address
        # was stored in says nothing about who it belongs to.
        return {"$regex": f"^{re.escape(email.strip())}$", "$options": "i"}

    async def attach_related(user, tasks: list[dict]) -> list[dict]:
        """Say what each task is about, in a form a person can act on.

        A row reading "related_type: contact, related_id: c_91f2" is not something an agent
        can call back. Each task gets a `related` summary: the record's name, the person
        to call (the contact itself, or a deal's first contact) with their phone, and --
        for a website lead's call-back task -- the lead it came from. One tenant-scoped
        query per collection, however many tasks there are.
        """
        tenant = tenant_of(user)
        wanted: dict[str, set[str]] = {collection: set() for collection in RELATABLE.values()}
        for task in tasks:
            collection = RELATABLE.get(task.get("related_type") or "")
            if collection and task.get("related_id"):
                wanted[collection].add(task["related_id"])
        projection = {"_id": 0, "id": 1, "name": 1, "phone": 1, "email": 1, "contact_ids": 1}

        async def fetch(collection: str) -> dict[str, dict]:
            ids = sorted(wanted[collection])
            if not ids:
                return {}
            rows = await db[collection].find({"tenant_id": tenant, "id": {"$in": ids}},
                                             projection).to_list(len(ids))
            return {row["id"]: row for row in rows}

        found = {collection: await fetch(collection)
                 for collection in (DEALS, COMPANIES, "workspaces")}
        for deal in found[DEALS].values():
            if deal.get("contact_ids"):
                wanted[CONTACTS].add(deal["contact_ids"][0])
        found[CONTACTS] = await fetch(CONTACTS)

        def person(contact_id: Optional[str]) -> Optional[dict]:
            contact = found[CONTACTS].get(contact_id or "")
            if not contact:
                return None
            return {"id": contact["id"], "name": contact.get("name"),
                    "phone": contact.get("phone"), "email": contact.get("email")}

        for task in tasks:
            related_type = task.get("related_type")
            record = found.get(RELATABLE.get(related_type or "", ""), {}).get(
                task.get("related_id") or "")
            if related_type == "contact":
                contact = person(task.get("related_id"))
            elif related_type == "deal" and record and record.get("contact_ids"):
                contact = person(record["contact_ids"][0])
            else:
                contact = None
            source = task.get("source")
            lead_id = None
            if isinstance(source, dict) and source.get("kind") == "website_form":
                lead_id = source.get("enquiry_id")
            task["related"] = {
                "type": related_type, "id": task.get("related_id"),
                "name": (record or {}).get("name"), "contact": contact, "lead_id": lead_id,
            }
        return tasks

    @router.get("/tasks")
    async def list_tasks(
        q: Optional[str] = None,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        mine: bool = False,
        include_unassigned: bool = False,
        related_type: Optional[str] = None,
        related_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        due_before: Optional[str] = None,
        due_after: Optional[str] = None,
        include_undated: bool = False,
        completed_after: Optional[str] = None,
        expand: Optional[str] = None,
        sort: Optional[str] = "due_date",
        order: Optional[str] = "asc",
        limit: int = 50,
        offset: int = 0,
        user=Depends(get_current_user),
    ):
        """Every task in the tenant, not just the ones inside a delivery workspace.

        The Tasks page reads its tabs from here. `mine` narrows to the caller's own work,
        and `include_unassigned` keeps the tasks nobody owns yet beside it -- a website
        lead that no one was assigned is everyone's call to make, and hiding it from every
        "My tasks" view is how a call-back goes unmade. `status` takes a comma-separated
        set ("todo,in_progress,blocked" is "still open"); a due window can keep undated
        tasks with `include_undated`; `expand=related` says what each task is about.
        """
        query: dict[str, Any] = {**text_filter(TASKS, q)}
        clauses: list[dict] = []
        if status:
            statuses = [value.strip() for value in status.split(",") if value.strip()]
            query["status"] = statuses[0] if len(statuses) == 1 else {"$in": statuses}
        if mine:
            owned: list[dict] = [{"assignee": email_match(user["email"])}]
            if include_unassigned:
                owned += [{"assignee": None}, {"assignee": ""}]
            clauses.append({"$or": owned})
        elif assignee:
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
        if due and include_undated:
            clauses.append({"$or": [{"due_date": due}, {"due_date": None}]})
        elif due:
            query["due_date"] = due
        if completed_after:
            query["completed_at"] = {"$gte": _parse_date(completed_after, "completed_after")}
        if clauses:
            query["$and"] = clauses
        page = await listing(TASKS, user, query=query, sort=sort, order=order,
                             limit=limit, offset=offset)
        if expand == "related":
            await attach_related(user, page["items"])
        return page

    @router.get("/crm/tasks/{task_id}")
    async def get_crm_task(task_id: str, user=Depends(get_current_user)):
        """One task with what it is about, for a link that names it (`/tasks?task=`)."""
        task = await load(TASKS, task_id, user)
        return (await attach_related(user, [task]))[0]

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
        if inp.assignee and not same_person(inp.assignee, user["email"]):
            await notify_assignment(user, doc)
        return _public(doc)

    async def notify_assignment(user, task: dict) -> None:
        """Tell someone a task landed on them -- and only them.

        An assignment nobody is told about is not an assignment, and one the whole team
        is told about is noise: a notice with no `user_id` is a team-wide one, which is
        how every user used to read "a task was assigned to you". So it is addressed to
        the assignee's own user. Someone who is not an active member here has no bell to
        ring, and nothing is stored for them.
        """
        assignee = str(task.get("assignee") or "").strip()
        if not assignee:
            return
        member = await db.memberships.find_one(
            {"tenant_id": tenant_of(user), "email": email_match(assignee), "status": "active"},
            {"_id": 0, "user_id": 1})
        if not (member or {}).get("user_id"):
            return
        await db.notifications.insert_one({
            "id": new_id("ntf"), "tenant_id": tenant_of(user), "user_id": member["user_id"],
            "recipient": assignee, "workspace_id": task.get("workspace_id"),
            "type": "assignment", "severity": "info", "source": "crm", "category": "tasks",
            "task_id": task["id"], "title": "A task was assigned to you",
            "body": f"{user['email']} assigned you \"{task['title']}\"",
            "deep_link": f"/tasks?task={task['id']}", "read": False, "created_at": now_iso(),
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
        if updated.get("status") != before.get("status") and on_task_status_changed:
            # Whatever else hangs off a task -- a website lead's response clock -- moves
            # with it now, not on the next sweep.
            await on_task_status_changed(updated, before.get("status"), user["email"])
        if changes.get("assignee") and changes["assignee"] != before.get("assignee") \
                and not same_person(changes["assignee"], user["email"]):
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
        """Log something that happened: a note, a call, a meeting, an email or a text
        already sent.

        This records history. It sends nothing and schedules nothing -- an email or text
        logged here is one a person already sent from their own phone or mailbox, which
        is a different fact from one this system delivered, and the two are never merged.
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
        if on_activity_logged:
            try:
                await on_activity_logged(dict(doc))
            except Exception:
                # The activity is stored and on the record's timeline. A fault in what
                # follows from it must not turn a logged call into a failed request; the
                # periodic sweep recognises it later all the same.
                logger.exception("Follow-up for activity %s failed", doc["id"])
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
        results: dict[str, Any] = {}
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
            writer.writerow({column: csv_safe(row.get(column, "")) for column in columns})
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
                        amount = float(row["value"])
                    except ValueError:
                        errors.append({"row": index, "error": "value must be a number"})
                        continue
                    row["value"] = amount
                    if not math.isfinite(amount) or not 0 <= amount <= MAX_DEAL_VALUE:
                        errors.append({"row": index, "error": (
                            "value must be a finite amount from 0 to "
                            f"{MAX_DEAL_VALUE:,.0f}")})
                        continue
                if row.get("currency"):
                    row["currency"] = str(row["currency"]).strip().upper()
                    if not re.match(CURRENCY_PATTERN, row["currency"]):
                        errors.append({"row": index, "error": (
                            "currency must be a 3-letter ISO 4217 code")})
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
