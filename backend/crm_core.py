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
