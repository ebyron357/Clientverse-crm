"""Automations: when something happens, do these steps, and stop when the person answers.

An automation is a trigger, optional conditions, a list of steps and stop rules:

    When a website lead arrives (from the "Contact us" form, if their Budget is over 10,000)
    -> create a task "Call {{contact.first_name}} now", due in 5 minutes
    -> wait 5 minutes
    -> notify the owner and the admins
    Stop as soon as someone replies to them.

Triggers are the domain events the CRM already records (`record_event`), so nothing has to
remember to call an automation: a lead, a booking, a won deal or a no-show each start the
automations listening for it. Events an automation itself caused never start another
automation, so two automations cannot feed each other in a loop.

Every run leaves a receipt (`automation_runs`): which event started it, each step with
what it did and links to the records it made, and how it ended -- completed, stopped (and
why: "Stopped: they replied"), or failed (and where). The same event never starts the
same automation twice (a unique index on the automation and the event), and while a run is
active for a person another one for the same person is not started, so a burst of form
fills cannot stack up duplicate follow-ups.

What an automation can do is deliberately inside the CRM: tasks, field and tag changes,
owner assignment, in-app notices and waits. Nothing it does leaves ClientVerse, so it needs
no consent record or approval; a step that would message a person outside the business is
not offered here (email goes through its own approved-template path).

A wait step parks the run with `resume_at`; the watcher (every 30 s, `AUTOMATION_WATCHER`,
on unless `0`) claims due runs one at a time with an atomic update, so several API
instances can run it without doing a step twice. Stop rules are checked before every step,
including on resuming after a wait.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import crm_core
import detectors
import record_fields

logger = logging.getLogger("clientverse.automations")

AUTOMATIONS = "automations"
RUNS = "automation_runs"
SOURCE = "automation"

MAX_STEPS = 20
MAX_AUTOMATIONS = 100
MAX_WAIT_MINUTES = 90 * 24 * 60
LEASE = timedelta(minutes=5)
ACTIVE = ("running", "waiting")

# What starts an automation: the event, how a person reads it, and what it is about.
TRIGGERS: dict[str, dict[str, str]] = {
    "lead.received": {"label": "A website lead arrives", "subject": "lead"},
    "lead.sla_breached": {"label": "A lead waits past the reply goal", "subject": "lead"},
    "appointment.booked": {"label": "Someone books a time", "subject": "appointment"},
    "appointment.no_show": {"label": "A booked person doesn't show", "subject": "appointment"},
    "appointment.cancelled": {"label": "A booking is cancelled", "subject": "appointment"},
    "opportunity.closed_won": {"label": "A deal is won", "subject": "deal"},
    "opportunity.closed_lost": {"label": "A deal is lost", "subject": "deal"},
    "opportunity.stage_changed": {"label": "A deal moves to a stage", "subject": "deal"},
    "contact.created": {"label": "A contact is added", "subject": "contact"},
    "commitment.at_risk": {"label": "A client commitment is at risk", "subject": "commitment"},
}

STEP_TYPES = {
    "create_task": "Create a task",
    "set_field": "Set a field",
    "add_tag": "Add a tag",
    "assign_owner": "Assign an owner",
    "notify": "Notify the team",
    "wait": "Wait",
}

STOP_RULES = {
    "replied": "Someone replies to them (a call, text, email or meeting is logged, or the lead is marked answered)",
    "booked": "They book a time",
    "deal_closed": "The deal is won or lost",
    "stage_changed": "The deal moves to another stage",
    "became_customer": "They become a customer",
}

# Built-in fields a set_field step may change, and the values each takes.
SETTABLE = {
    "contact": {"lifecycle": crm_core.LIFECYCLE_STAGES,
                "sentiment": ("positive", "neutral", "negative"),
                "influence": ("low", "medium", "high")},
    "deal": {},
}
TASK_PRIORITIES = ("low", "medium", "high")
ASSIGN_TO = ("record_owner", "unassigned", "specific")
AUDIENCES = ("owner", "admins", "everyone")
PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\.([a-z_]+)\s*\}\}")

# Ready-made automations a business starts from. Each becomes a draft to review and turn on.
RECIPES: dict[str, dict[str, Any]] = {
    "speed_to_lead": {
        "name": "New lead: call within 5 minutes",
        "description": "A task to call right away, then an alert if nobody has replied after 5 minutes.",
        "trigger": {"event": "lead.received"},
        "steps": [
            {"type": "create_task", "title": "Call {{contact.first_name}} now", "due_in_minutes": 5,
             "priority": "high", "assign": "record_owner"},
            {"type": "wait", "minutes": 5},
            {"type": "notify", "audience": "admins",
             "message": "{{contact.name}} has waited 5 minutes and nobody has replied yet."},
        ],
        "stop_rules": ["replied"],
    },
    "deal_won_onboarding": {
        "name": "Deal won: start onboarding",
        "description": "Makes the people on the deal customers and lines up the kickoff, welcome and 30-day check-in.",
        "trigger": {"event": "opportunity.closed_won"},
        "steps": [
            {"type": "set_field", "object": "contact", "field": "lifecycle", "value": "customer"},
            {"type": "create_task", "title": "Send the welcome pack to {{contact.name}}", "due_in_minutes": 24 * 60,
             "priority": "high", "assign": "record_owner"},
            {"type": "create_task", "title": "Kickoff call with {{contact.name}} ({{deal.name}})", "due_in_minutes": 2 * 24 * 60,
             "priority": "high", "assign": "record_owner"},
            {"type": "notify", "audience": "everyone", "message": "{{deal.name}} is won. Onboarding has started."},
            {"type": "wait", "minutes": 30 * 24 * 60},
            {"type": "create_task", "title": "30-day check-in with {{contact.name}}", "due_in_minutes": 0,
             "priority": "medium", "assign": "record_owner"},
        ],
        "stop_rules": [],
    },
    "no_show_rebook": {
        "name": "No-show: get them rebooked",
        "description": "Call to rebook within the hour, then try again in 2 days unless they have booked.",
        "trigger": {"event": "appointment.no_show"},
        "steps": [
            {"type": "create_task", "title": "Call {{contact.first_name}} to rebook", "due_in_minutes": 60,
             "priority": "high", "assign": "record_owner"},
            {"type": "wait", "minutes": 2 * 24 * 60},
            {"type": "create_task", "title": "Second try: rebook {{contact.first_name}}", "due_in_minutes": 0,
             "priority": "medium", "assign": "record_owner"},
        ],
        "stop_rules": ["booked"],
    },
    "nurture_quiet_lead": {
        "name": "Quiet lead: follow up after 2 days",
        "description": "If nobody has replied and they have not booked in 2 days, a follow-up task.",
        "trigger": {"event": "lead.received"},
        "steps": [
            {"type": "wait", "minutes": 2 * 24 * 60},
            {"type": "create_task", "title": "Follow up with {{contact.name}}", "due_in_minutes": 0,
             "priority": "medium", "assign": "record_owner"},
        ],
        "stop_rules": ["replied", "booked"],
    },
    "lost_deal_check_in": {
        "name": "Lost deal: check back in 90 days",
        "description": "A lost deal is often a 'not yet'. A reminder to ask again in 3 months.",
        "trigger": {"event": "opportunity.closed_lost"},
        "steps": [
            {"type": "add_tag", "tag": "lost-check-back"},
            {"type": "wait", "minutes": 90 * 24 * 60},
            {"type": "create_task", "title": "Check back in with {{contact.name}} about {{deal.name}}", "due_in_minutes": 0,
             "priority": "medium", "assign": "record_owner"},
        ],
        "stop_rules": [],
    },
    "commitment_at_risk": {
        "name": "Client commitment at risk: alert the admins",
        "description": "Admins hear about a commitment at risk the moment it is flagged.",
        "trigger": {"event": "commitment.at_risk"},
        "steps": [
            {"type": "notify", "audience": "admins", "message": "At risk: {{commitment.title}} ({{workspace.name}})."},
        ],
        "stop_rules": [],
    },
}


# --------------------------------------------------------------------------- helpers

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def duration(minutes: int) -> str:
    """"5 minutes", "2 hours", "3 days": a wait as a person says it."""
    if minutes and minutes % (24 * 60) == 0:
        days = minutes // (24 * 60)
        return f"{days} day{'s' if days != 1 else ''}"
    if minutes and minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} hour{'s' if hours != 1 else ''}"
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


def render(template: str, context: dict) -> str:
    """Fill {{contact.first_name}}-style placeholders from the run's records. A
    placeholder with nothing to fill becomes empty rather than showing braces."""
    def value(match: re.Match) -> str:
        record = context.get(match.group(1)) or {}
        if match.group(1) == "contact" and match.group(2) == "first_name":
            return str(record.get("name") or "").split(" ")[0]
        found = record.get(match.group(2))
        return "" if found is None or isinstance(found, (dict, list)) else str(found)
    text = PLACEHOLDER.sub(value, template or "")
    return re.sub(r"\s{2,}", " ", text).strip()


def describe(step: dict) -> str:
    """One line for a step, as the editor and the receipt show it."""
    kind = step.get("type")
    if kind == "create_task":
        due = step.get("due_in_minutes") or 0
        when = "due now" if not due else f"due in {duration(due)}"
        return f"Create a task: {step.get('title')} ({when})"
    if kind == "set_field":
        return f"Set {step.get('object')} {step.get('field')} to {step.get('value')}"
    if kind == "add_tag":
        return f"Add the tag {step.get('tag')}"
    if kind == "assign_owner":
        return "Assign an owner by round robin" if step.get("mode") == "round_robin" else f"Assign {step.get('email')}"
    if kind == "notify":
        return f"Notify {'the owner' if step.get('audience') == 'owner' else 'the admins' if step.get('audience') == 'admins' else 'everyone'}"
    if kind == "wait":
        return f"Wait {duration(int(step.get('minutes') or 0))}"
    return str(kind)


# --------------------------------------------------------------------------- payloads

class TriggerInput(BaseModel):
    event: str
    form_id: Optional[str] = Field(default=None, max_length=80)
    stage: Optional[str] = Field(default=None, max_length=80)
    booking_page_id: Optional[str] = Field(default=None, max_length=80)


class AutomationInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    trigger: TriggerInput
    conditions: list[record_fields.ViewFilter] = Field(default_factory=list, max_length=10)
    steps: list[dict] = Field(default_factory=list, max_length=MAX_STEPS)
    stop_rules: list[str] = Field(default_factory=list, max_length=len(STOP_RULES))
    once_per_contact: bool = False


class AutomationPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    trigger: Optional[TriggerInput] = None
    conditions: Optional[list[record_fields.ViewFilter]] = Field(default=None, max_length=10)
    steps: Optional[list[dict]] = Field(default=None, max_length=MAX_STEPS)
    stop_rules: Optional[list[str]] = Field(default=None, max_length=len(STOP_RULES))
    once_per_contact: Optional[bool] = None


class StatusInput(BaseModel):
    status: str = Field(pattern="^(on|off)$")


class RecipeInput(BaseModel):
    recipe: str = Field(min_length=1, max_length=60)


class TestInput(BaseModel):
    record_type: str = Field(pattern="^(contact|deal|lead|appointment)$")
    record_id: str = Field(min_length=1, max_length=80)


def _bad(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail=message)


def _clean_text(value: Any, label: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise _bad(f"{label} is required")
    return text[:limit]


def _minutes(value: Any, label: str, low: int, high: int) -> int:
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        raise _bad(f"{label} must be a whole number of minutes")
    if not low <= minutes <= high:
        raise _bad(f"{label} must be between {duration(low) if low else '0 minutes'} and {duration(high)}")
    return minutes


# --------------------------------------------------------------------------- engine

class AutomationEngine:
    def __init__(self, db: Any, *, new_id: Callable[[str], str], now_iso: Callable[[], str],
                 record_event: Callable[..., Awaitable[Any]]) -> None:
        self.db = db
        self.new_id = new_id
        self.now_iso = now_iso
        self.record_event = record_event
        self._pending: set[asyncio.Task] = set()
        self._watcher: Optional[asyncio.Task] = None

    async def ensure_indexes(self) -> None:
        await self.db[AUTOMATIONS].create_index([("tenant_id", 1), ("status", 1), ("trigger.event", 1)])
        await self.db[RUNS].create_index([("automation_id", 1), ("event_id", 1)], unique=True)
        await self.db[RUNS].create_index([("tenant_id", 1), ("automation_id", 1), ("created_at", -1)])
        await self.db[RUNS].create_index([("status", 1), ("resume_at", 1)])
        await self.db[RUNS].create_index([("tenant_id", 1), ("automation_id", 1), ("contact_id", 1), ("status", 1)])

    # ------------------------------------------------------------ validation

    async def clean_steps(self, tenant_id: str, steps: list[dict]) -> list[dict]:
        if len(steps) > MAX_STEPS:
            raise _bad(f"An automation can have at most {MAX_STEPS} steps")
        defs = {d["key"]: d for d in await record_fields.definitions(self.db, tenant_id, "contacts")}
        deal_defs = {d["key"]: d for d in await record_fields.definitions(self.db, tenant_id, "deals")}
        out = []
        for index, raw in enumerate(steps, 1):
            if not isinstance(raw, dict):
                raise _bad(f"Step {index} is not a step")
            kind = raw.get("type")
            label = f"Step {index}"
            step: dict[str, Any] = {"id": str(raw.get("id") or self.new_id("stp"))[:40], "type": kind}
            if kind == "create_task":
                step["title"] = _clean_text(raw.get("title"), f"{label}: the task title", 200)
                step["due_in_minutes"] = _minutes(raw.get("due_in_minutes", 0), f"{label}: when it is due", 0, 365 * 24 * 60)
                step["priority"] = raw.get("priority") or "medium"
                if step["priority"] not in TASK_PRIORITIES:
                    raise _bad(f"{label}: priority must be low, medium or high")
                step["assign"] = raw.get("assign") or "record_owner"
                if step["assign"] not in ASSIGN_TO:
                    raise _bad(f"{label}: assign must be record_owner, unassigned or specific")
                if step["assign"] == "specific":
                    step["email"] = await self._member_email(tenant_id, raw.get("email"), label)
            elif kind == "set_field":
                obj = raw.get("object") or "contact"
                if obj not in SETTABLE:
                    raise _bad(f"{label}: object must be contact or deal")
                field = str(raw.get("field") or "")
                step.update(object=obj, field=field)
                if field in SETTABLE[obj]:
                    if raw.get("value") not in SETTABLE[obj][field]:
                        raise _bad(f"{label}: {field} must be one of {', '.join(SETTABLE[obj][field])}")
                    step["value"] = raw["value"]
                elif field.startswith("custom_fields.") and field[14:] in (defs if obj == "contact" else deal_defs):
                    definition = (defs if obj == "contact" else deal_defs)[field[14:]]
                    step["value"] = record_fields.coerce(definition, raw.get("value"))
                else:
                    raise _bad(f"{label}: '{field}' is not a field an automation can set")
            elif kind == "add_tag":
                tag = re.sub(r"[^a-z0-9-]+", "-", str(raw.get("tag") or "").strip().lower()).strip("-")[:40]
                if not tag:
                    raise _bad(f"{label}: the tag is required")
                step["tag"] = tag
            elif kind == "assign_owner":
                step["mode"] = raw.get("mode") or "round_robin"
                if step["mode"] not in ("round_robin", "specific"):
                    raise _bad(f"{label}: mode must be round_robin or specific")
                if step["mode"] == "specific":
                    step["email"] = await self._member_email(tenant_id, raw.get("email"), label)
                step["only_if_unowned"] = raw.get("only_if_unowned", True) is not False
            elif kind == "notify":
                step["audience"] = raw.get("audience") or "owner"
                if step["audience"] not in AUDIENCES:
                    raise _bad(f"{label}: audience must be owner, admins or everyone")
                step["message"] = _clean_text(raw.get("message"), f"{label}: the message", 500)
            elif kind == "wait":
                step["minutes"] = _minutes(raw.get("minutes"), f"{label}: the wait", 1, MAX_WAIT_MINUTES)
            else:
                raise _bad(f"{label}: '{kind}' is not a step an automation can take")
            out.append(step)
        return out

    async def _member_email(self, tenant_id: str, email: Any, label: str) -> str:
        address = str(email or "").strip().lower()
        if not address or not await self.db.memberships.find_one(
                {"tenant_id": tenant_id, "email": {"$regex": f"^{re.escape(address)}$", "$options": "i"},
                 "status": {"$ne": "disabled"}}, {"_id": 1}):
            raise _bad(f"{label}: choose someone on the team")
        return address

    def clean_trigger(self, trigger: TriggerInput) -> dict:
        if trigger.event not in TRIGGERS:
            raise _bad("Choose what starts the automation")
        out: dict[str, Any] = {"event": trigger.event}
        if trigger.form_id and TRIGGERS[trigger.event]["subject"] == "lead":
            out["form_id"] = trigger.form_id
        if trigger.stage and trigger.event == "opportunity.stage_changed":
            out["stage"] = trigger.stage
        if trigger.booking_page_id and TRIGGERS[trigger.event]["subject"] == "appointment":
            out["booking_page_id"] = trigger.booking_page_id
        return out

    @staticmethod
    def clean_stop_rules(rules: list[str]) -> list[str]:
        for rule in rules:
            if rule not in STOP_RULES:
                raise _bad(f"'{rule}' is not a stop rule")
        return list(dict.fromkeys(rules))

    async def create(self, tenant: str, actor: str, body: dict) -> dict:
        """A new automation, as a draft. Used by the editor, recipes and industry templates."""
        db = self.db
        if await db[AUTOMATIONS].count_documents({"tenant_id": tenant, "status": {"$ne": "archived"}}) >= MAX_AUTOMATIONS:
            raise _bad(f"A workspace can have at most {MAX_AUTOMATIONS} automations")
        inp = AutomationInput(**body)
        conditions = record_fields.clean_filters(inp.conditions)
        await record_fields.compile_filters(db, tenant, "contacts", conditions)
        now = self.now_iso()
        doc: dict[str, Any] = {"id": self.new_id("auto"), "tenant_id": tenant, "name": inp.name.strip(),
               "description": (inp.description or "").strip() or None,
               "trigger": self.clean_trigger(inp.trigger), "conditions": conditions,
               "steps": await self.clean_steps(tenant, inp.steps),
               "stop_rules": self.clean_stop_rules(inp.stop_rules),
               "once_per_contact": inp.once_per_contact, "status": "draft", "version": 1,
               "runs_total": 0, "last_run_at": None, "round_robin_cursor": 0,
               "created_by": actor, "created_at": now, "updated_at": now}
        await db[AUTOMATIONS].insert_one(dict(doc))
        await self.record_event("automation.created", "automation", doc["id"], tenant, actor,
                                payload={"name": doc["name"], "trigger": doc["trigger"]["event"]})
        return doc

    def recipe_body(self, key: str) -> dict:
        recipe = RECIPES[key]
        return {k: recipe[k] for k in ("name", "description", "trigger", "steps", "stop_rules")}

    # ------------------------------------------------------------ context

    async def context_for(self, tenant_id: str, subject: str, record_id: str,
                          payload: Optional[dict] = None) -> Optional[dict]:
        """The records a run works on, found from what the event was about."""
        db = self.db
        ctx: dict[str, Any] = {"lead": None, "appointment": None, "deal": None, "contact": None,
                               "company": None, "commitment": None, "workspace": None}
        scope = {"tenant_id": tenant_id, "id": record_id}
        if subject == "lead":
            ctx["lead"] = await db[detectors.WEB_ENQUIRIES].find_one(scope, {"_id": 0, "visitor": 0, "automation": 0})
            if not ctx["lead"]:
                return None
            contact_id, deal_id = ctx["lead"].get("contact_id"), ctx["lead"].get("opportunity_id")
        elif subject == "appointment":
            ctx["appointment"] = await db.appointments.find_one(scope, {"_id": 0})
            if not ctx["appointment"]:
                return None
            contact_id, deal_id = ctx["appointment"].get("contact_id"), ctx["appointment"].get("opportunity_id")
        elif subject == "deal":
            ctx["deal"] = await db[crm_core.DEALS].find_one(scope, {"_id": 0, "history": 0})
            if not ctx["deal"]:
                return None
            contact_id, deal_id = (ctx["deal"].get("contact_ids") or [None])[0], record_id
        elif subject == "contact":
            contact_id, deal_id = record_id, None
        elif subject == "commitment":
            ctx["commitment"] = await db.commitments.find_one(scope, {"_id": 0})
            if not ctx["commitment"]:
                return None
            contact_id, deal_id = None, None
            if ctx["commitment"].get("workspace_id"):
                ctx["workspace"] = await db.workspaces.find_one(
                    {"tenant_id": tenant_id, "id": ctx["commitment"]["workspace_id"]}, {"_id": 0})
        else:
            return None
        if contact_id:
            ctx["contact"] = await db[crm_core.CONTACTS].find_one(
                {"tenant_id": tenant_id, "id": contact_id}, {"_id": 0, "history": 0, "inquiries": 0})
        if deal_id and not ctx["deal"]:
            ctx["deal"] = await db[crm_core.DEALS].find_one(
                {"tenant_id": tenant_id, "id": deal_id}, {"_id": 0, "history": 0})
        company_id = (ctx["contact"] or {}).get("company_id") or (ctx["deal"] or {}).get("company_id")
        if company_id:
            ctx["company"] = await db[crm_core.COMPANIES].find_one(
                {"tenant_id": tenant_id, "id": company_id}, {"_id": 0, "history": 0})
        ctx["stage_at_start"] = (payload or {}).get("to") or (ctx["deal"] or {}).get("stage")
        return ctx

    async def matches(self, automation: dict, ctx: dict) -> bool:
        trigger = automation.get("trigger") or {}
        if trigger.get("form_id") and (ctx.get("lead") or {}).get("form_id") != trigger["form_id"]:
            return False
        if trigger.get("stage") and ctx.get("stage_at_start") != trigger["stage"]:
            return False
        if trigger.get("booking_page_id") and (ctx.get("appointment") or {}).get("event_type_id") != trigger["booking_page_id"]:
            return False
        conditions = automation.get("conditions") or []
        if conditions:
            contact = ctx.get("contact")
            if not contact:
                return False
            compiled = await record_fields.compile_filters(self.db, automation["tenant_id"], "contacts", conditions)
            return bool(await self.db[crm_core.CONTACTS].count_documents(
                {"tenant_id": automation["tenant_id"], "id": contact["id"], "$and": compiled}))
        return True

    # ------------------------------------------------------------ events

    def on_event(self, event: dict) -> None:
        """Called for every recorded event. The work runs in the background so the request
        that recorded the event never waits on, or fails because of, an automation."""
        if event.get("source") == SOURCE or event.get("event_type") not in TRIGGERS:
            return
        task = asyncio.get_running_loop().create_task(self._handle_safely(event))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def idle(self) -> None:
        """Wait for automations already started by events to finish their immediate steps."""
        while self._pending:
            await asyncio.gather(*list(self._pending), return_exceptions=True)

    async def _handle_safely(self, event: dict) -> None:
        try:
            await self.handle(event)
        except Exception:
            logger.exception("Automation handling failed for event %s", event.get("id"))

    async def handle(self, event: dict) -> list[dict]:
        tenant = event["tenant_id"]
        automations = await self.db[AUTOMATIONS].find(
            {"tenant_id": tenant, "status": "on", "trigger.event": event["event_type"]},
            {"_id": 0}).to_list(MAX_AUTOMATIONS)
        if not automations:
            return []
        subject = TRIGGERS[event["event_type"]]["subject"]
        ctx = await self.context_for(tenant, subject, event["resource_id"], event.get("payload"))
        if not ctx:
            return []
        runs = []
        for automation in automations:
            if not await self.matches(automation, ctx):
                continue
            run = await self.start(automation, ctx, event)
            if run:
                runs.append(await self.advance(run))
        return runs

    async def start(self, automation: dict, ctx: dict, event: dict) -> Optional[dict]:
        contact_id = (ctx.get("contact") or {}).get("id")
        if contact_id:
            statuses = None if automation.get("once_per_contact") else {"$in": list(ACTIVE)}
            query: dict[str, Any] = {"tenant_id": automation["tenant_id"], "automation_id": automation["id"],
                                     "contact_id": contact_id}
            if statuses:
                query["status"] = statuses
            if await self.db[RUNS].find_one(query, {"_id": 1}):
                return None
        now = _now()
        run = {
            "id": self.new_id("arun"), "tenant_id": automation["tenant_id"],
            "automation_id": automation["id"], "automation_name": automation["name"],
            "automation_version": automation.get("version", 1),
            "event_id": event["id"], "event_type": event["event_type"],
            "trigger_label": TRIGGERS[event["event_type"]]["label"],
            "contact_id": contact_id, "contact_name": (ctx.get("contact") or {}).get("name"),
            "deal_id": (ctx.get("deal") or {}).get("id"), "lead_id": (ctx.get("lead") or {}).get("id"),
            "appointment_id": (ctx.get("appointment") or {}).get("id"),
            "commitment_id": (ctx.get("commitment") or {}).get("id"),
            "workspace_id": (ctx.get("workspace") or {}).get("id"),
            "stage_at_start": ctx.get("stage_at_start"),
            # The steps as they were when the run began: editing the automation later
            # changes future runs, never what a receipt says this one did.
            "steps": automation.get("steps") or [], "stop_rules": automation.get("stop_rules") or [],
            "status": "running", "next_step": 0, "receipt": [],
            "lease_until": _iso(now + LEASE), "resume_at": None,
            "stop_reason": None, "error": None,
            "created_at": _iso(now), "started_at": _iso(now), "finished_at": None,
        }
        try:
            await self.db[RUNS].insert_one(dict(run))
        except DuplicateKeyError:
            return None  # this event already started this automation
        await self.db[AUTOMATIONS].update_one({"id": automation["id"]}, {"$set": {"last_run_at": run["created_at"]},
                                                                       "$inc": {"runs_total": 1}})
        return run

    # ------------------------------------------------------------ running

    async def advance(self, run: dict) -> dict:
        """Take the run's steps from `next_step` until it waits, stops, fails or ends."""
        steps = run["steps"]
        while run["next_step"] < len(steps):
            reason = await self.stop_reason(run)
            if reason:
                return await self._finish(run, "stopped", stop_reason=reason)
            index = run["next_step"]
            step = steps[index]
            if step["type"] == "wait":
                resume = _now() + timedelta(minutes=int(step["minutes"]))
                entry = {"index": index, "type": "wait", "label": describe(step), "status": "waiting",
                         "at": self.now_iso(), "detail": f"Waiting {duration(int(step['minutes']))}"}
                run = await self._save(run, {"status": "waiting", "resume_at": _iso(resume), "lease_until": None},
                                       entry=entry, next_step=index)
                return run
            ctx = await self._fresh_context(run)
            label = render(describe(step), ctx)
            try:
                detail, links = await self.perform(step, run, ctx)
                entry = {"index": index, "type": step["type"], "label": label,
                         "status": "skipped" if detail.startswith("Skipped") else "done",
                         "at": self.now_iso(), "detail": detail, "links": links}
            except Exception as exc:
                logger.exception("Automation step failed (run %s, step %s)", run["id"], index)
                entry = {"index": index, "type": step["type"], "label": label, "status": "failed",
                         "at": self.now_iso(), "detail": str(exc)[:300] or exc.__class__.__name__}
                run = await self._save(run, {}, entry=entry, next_step=index)
                return await self._finish(run, "failed", error=entry["detail"])
            run = await self._save(run, {"lease_until": _iso(_now() + LEASE)}, entry=entry, next_step=index + 1)
        return await self._finish(run, "completed")

    async def _save(self, run: dict, changes: dict, *, entry: dict, next_step: int) -> dict:
        receipt = [e for e in run["receipt"] if not (e["index"] == entry["index"] and e["status"] == "waiting")]
        receipt.append(entry)
        changes = {**changes, "receipt": receipt, "next_step": next_step}
        await self.db[RUNS].update_one({"id": run["id"]}, {"$set": changes})
        return {**run, **changes}

    async def _finish(self, run: dict, status: str, *, stop_reason: Optional[str] = None,
                      error: Optional[str] = None) -> dict:
        changes = {"status": status, "finished_at": self.now_iso(), "lease_until": None, "resume_at": None,
                   "stop_reason": stop_reason, "error": error}
        await self.db[RUNS].update_one({"id": run["id"]}, {"$set": changes})
        await self.record_event(f"automation.run_{status}", "automation_run", run["id"], run["tenant_id"],
                                f"automation:{run['automation_id']}", source=SOURCE,
                                payload={"automation_id": run["automation_id"], "stop_reason": stop_reason,
                                         "error": error, "steps": len(run["receipt"])})
        return {**run, **changes}

    async def _fresh_context(self, run: dict) -> dict:
        tenant = run["tenant_id"]
        ctx: dict[str, Any] = {}
        for key, collection in (("contact", crm_core.CONTACTS), ("deal", crm_core.DEALS),
                                ("lead", detectors.WEB_ENQUIRIES), ("appointment", "appointments"),
                                ("commitment", "commitments"), ("workspace", "workspaces")):
            record_id = run.get(f"{key}_id")
            ctx[key] = await self.db[collection].find_one(
                {"tenant_id": tenant, "id": record_id}, {"_id": 0, "history": 0, "visitor": 0}) if record_id else None
        company_id = (ctx["contact"] or {}).get("company_id") or (ctx["deal"] or {}).get("company_id")
        ctx["company"] = await self.db[crm_core.COMPANIES].find_one(
            {"tenant_id": tenant, "id": company_id}, {"_id": 0, "history": 0}) if company_id else None
        return ctx

    async def stop_reason(self, run: dict) -> Optional[str]:
        """Why this run must not take another step, or None. Checked before every step."""
        db, tenant = self.db, run["tenant_id"]
        automation = await db[AUTOMATIONS].find_one({"tenant_id": tenant, "id": run["automation_id"]},
                                                    {"_id": 0, "status": 1})
        if not automation or automation.get("status") != "on":
            return "The automation was turned off"
        contact = None
        if run.get("contact_id"):
            contact = await db[crm_core.CONTACTS].find_one(
                {"tenant_id": tenant, "id": run["contact_id"]}, {"_id": 0, "archived_at": 1, "lifecycle": 1, "merged_into": 1})
            if not contact or contact.get("archived_at"):
                return "The contact was archived" if contact else "The contact no longer exists"
        rules = set(run.get("stop_rules") or [])
        since = run["started_at"]
        if "replied" in rules and run.get("contact_id"):
            if await db[crm_core.ACTIVITIES].find_one(
                    {"tenant_id": tenant, "related_type": "contact", "related_id": run["contact_id"],
                     "type": {"$in": list(crm_core.OUTREACH_TYPES)},
                     "$or": [{"occurred_at": {"$gte": since}}, {"created_at": {"$gte": since}}]}, {"_id": 1}):
                return "They were contacted (a call, text, email or meeting was logged)"
            if await db[detectors.WEB_ENQUIRIES].find_one(
                    {"tenant_id": tenant, "contact_id": run["contact_id"], "sla.first_response_at": {"$gte": since}},
                    {"_id": 1}):
                return "Their website request was answered"
        if "booked" in rules and run.get("contact_id"):
            if await db.appointments.find_one(
                    {"tenant_id": tenant, "contact_id": run["contact_id"], "id": {"$ne": run.get("appointment_id")},
                     "created_at": {"$gte": since}, "status": {"$nin": ["cancelled", "canceled"]}}, {"_id": 1}):
                return "They booked a time"
        if run.get("deal_id") and rules & {"deal_closed", "stage_changed"}:
            deal = await db[crm_core.DEALS].find_one({"tenant_id": tenant, "id": run["deal_id"]}, {"_id": 0, "stage": 1})
            stage = (deal or {}).get("stage")
            if "deal_closed" in rules and stage:
                outcome = crm_core.classify_stage(stage, await crm_core.stage_classes(db, tenant))
                if outcome in (crm_core.STAGE_WON, crm_core.STAGE_LOST):
                    return f"The deal was {'won' if outcome == crm_core.STAGE_WON else 'lost'}"
            if "stage_changed" in rules and stage and stage != run.get("stage_at_start"):
                return "The deal moved to another stage"
        if "became_customer" in rules and run.get("contact_id"):
            if (contact or {}).get("lifecycle") == "customer":
                return "They became a customer"
        return None

    async def perform(self, step: dict, run: dict, ctx: dict, *, dry_run: bool = False) -> tuple[str, dict]:
        """Do one step. Returns what happened, in words, and links to what it made."""
        db, tenant = self.db, run["tenant_id"]
        actor = f"automation:{run['automation_id']}"
        contact, deal = ctx.get("contact"), ctx.get("deal")
        kind = step["type"]
        if kind == "create_task":
            title = render(step["title"], ctx) or "Follow up"
            owner = (contact or {}).get("owner") or (deal or {}).get("owner")
            assignee = {"record_owner": owner, "unassigned": None}.get(step["assign"], step.get("email"))
            due = _now() + timedelta(minutes=int(step.get("due_in_minutes") or 0))
            related_type, related_id = ("contact", contact["id"]) if contact else ("deal", deal["id"]) if deal else (None, None)
            if run.get("workspace_id") and not related_type:
                related_type, related_id = "workspace", run["workspace_id"]
            who = assignee or "nobody yet"
            if dry_run:
                minutes = int(step.get("due_in_minutes") or 0)
                return f"Would create “{title}” for {who}, due {'now' if not minutes else 'in ' + duration(minutes)}", {}
            doc = {"id": self.new_id("task"), "tenant_id": tenant, "title": title[:200], "assignee": assignee,
                   "due_date": _iso(due), "status": "todo", "priority": step.get("priority", "medium"),
                   "notes": f"Created by the automation “{run['automation_name']}”.",
                   "related_type": related_type, "related_id": related_id,
                   "workspace_id": run.get("workspace_id"), "archived_at": None,
                   "created_at": self.now_iso(), "updated_at": self.now_iso(), "created_by": actor,
                   "completed_at": None, "source": {"kind": "automation", "automation_id": run["automation_id"],
                                                    "run_id": run["id"]},
                   "history": [crm_core._history_entry("created", actor)]}
            await db[crm_core.TASKS].insert_one(dict(doc))
            await self.record_event("task.created", "task", doc["id"], tenant, actor, workspace_id=doc["workspace_id"],
                                    source=SOURCE, payload={"title": doc["title"], "assignee": assignee,
                                                            "related_type": related_type, "related_id": related_id})
            if assignee:
                await self._notify(tenant, [assignee], f"New task: {doc['title']}", f"From the automation “{run['automation_name']}”.",
                                   f"/tasks?task={doc['id']}", dry_run=False)
            return f"Created “{doc['title']}” for {who}", {"task_id": doc["id"]}
        if kind == "set_field":
            record, collection = (contact, crm_core.CONTACTS) if step["object"] == "contact" else (deal, crm_core.DEALS)
            if not record:
                return f"Skipped: there is no {step['object']} to change", {}
            field, value = step["field"], step["value"]
            current = record
            for part in field.split("."):
                current = (current or {}).get(part) if isinstance(current, dict) else None
            if current == value:
                return f"Skipped: {field} was already {value}", {}
            if dry_run:
                return f"Would set {field} to {value} (now {current if current is not None else 'empty'})", {}
            await db[collection].update_one(
                {"tenant_id": tenant, "id": record["id"]},
                {"$set": {field: value, "updated_at": self.now_iso()},
                 "$push": {"history": crm_core._history_entry("updated", actor, {"changed": [field], "from": {field: current}})}})
            return f"Set {field} from {current if current is not None else 'empty'} to {value}", {f"{step['object']}_id": record["id"]}
        if kind == "add_tag":
            if not contact:
                return "Skipped: there is no contact to tag", {}
            if step["tag"] in (contact.get("tags") or []):
                return f"Skipped: already tagged {step['tag']}", {}
            if dry_run:
                return f"Would tag {contact.get('name')} {step['tag']}", {}
            await db[crm_core.CONTACTS].update_one({"tenant_id": tenant, "id": contact["id"]},
                                                   {"$addToSet": {"tags": step["tag"]}, "$set": {"updated_at": self.now_iso()}})
            return f"Tagged {contact.get('name')} {step['tag']}", {"contact_id": contact["id"]}
        if kind == "assign_owner":
            records = [(r, c) for r, c in ((contact, crm_core.CONTACTS), (deal, crm_core.DEALS)) if r]
            if not records:
                return "Skipped: nothing to assign", {}
            if step.get("only_if_unowned", True) and all(r.get("owner") for r, _ in records):
                return f"Skipped: already owned by {records[0][0].get('owner')}", {}
            if step["mode"] == "specific":
                owner = step["email"]
            else:
                members = sorted(m["email"].lower() for m in await db.memberships.find(
                    {"tenant_id": tenant, "status": "active"}, {"_id": 0, "email": 1}).to_list(500) if m.get("email"))
                if not members:
                    return "Skipped: nobody on the team to assign", {}
                if dry_run:
                    return "Would assign the next person in turn", {}
                updated = await db[AUTOMATIONS].find_one_and_update(
                    {"id": run["automation_id"]}, {"$inc": {"round_robin_cursor": 1}},
                    projection={"_id": 0, "round_robin_cursor": 1}, return_document=ReturnDocument.AFTER)
                owner = members[(int((updated or {}).get("round_robin_cursor") or 1) - 1) % len(members)]
            if dry_run:
                return f"Would assign {owner}", {}
            for record, collection in records:
                if step.get("only_if_unowned", True) and record.get("owner"):
                    continue
                await db[collection].update_one({"tenant_id": tenant, "id": record["id"]},
                                                {"$set": {"owner": owner, "updated_at": self.now_iso()}})
            return f"Assigned {owner}", {}
        if kind == "notify":
            message = render(step["message"], ctx) or run["automation_name"]
            if step["audience"] == "owner":
                owner = (contact or {}).get("owner") or (deal or {}).get("owner")
                recipients = [owner] if owner else await self._admins(tenant)
            elif step["audience"] == "admins":
                recipients = await self._admins(tenant)
            else:
                recipients = []
            link = (f"/contacts?contact={contact['id']}" if contact else f"/deals?deal={deal['id']}" if deal
                    else f"/workspaces/{run['workspace_id']}" if run.get("workspace_id") else "/automations")
            audience = ", ".join(recipients) if recipients else "everyone"
            if dry_run:
                return f"Would notify {audience}: {message}", {}
            await self._notify(tenant, recipients, message, f"From the automation “{run['automation_name']}”.", link, dry_run=False)
            return f"Notified {audience}", {}
        raise ValueError(f"Unknown step {kind}")

    async def _admins(self, tenant_id: str) -> list[str]:
        return sorted(m["email"].lower() for m in await self.db.memberships.find(
            {"tenant_id": tenant_id, "status": "active", "role": "admin"}, {"_id": 0, "email": 1}).to_list(100)
            if m.get("email"))

    async def _notify(self, tenant_id: str, recipients: list[str], title: str, body: str, link: str,
                      *, dry_run: bool) -> None:
        if dry_run:
            return
        targets: list[Optional[str]] = list(recipients) or [None]  # nobody named: the whole team
        for recipient in targets:
            user_id = None
            if recipient:
                member = await self.db.memberships.find_one(
                    {"tenant_id": tenant_id, "email": {"$regex": f"^{re.escape(recipient)}$", "$options": "i"}},
                    {"_id": 0, "user_id": 1})
                user_id = (member or {}).get("user_id")
            await self.db.notifications.insert_one({
                "id": self.new_id("ntf"), "tenant_id": tenant_id, "user_id": user_id, "recipient": recipient,
                "workspace_id": None, "type": "automation", "severity": "info", "category": "automation",
                "source": SOURCE, "title": title[:300], "body": body[:2000], "deep_link": link,
                "read": False, "created_at": self.now_iso()})

    # ------------------------------------------------------------ waiting runs

    async def resume_due(self, *, now: Optional[datetime] = None, limit: int = 100) -> int:
        """Continue runs whose wait is over, and runs whose holder stopped mid-step.
        Each is claimed with one atomic update, so two instances never take the same run."""
        now = now or _now()
        done = 0
        for _ in range(limit):
            run = await self.db[RUNS].find_one_and_update(
                {"$or": [{"status": "waiting", "resume_at": {"$lte": _iso(now)}},
                         {"status": "running", "lease_until": {"$lte": _iso(now)}}]},
                {"$set": {"status": "running", "lease_until": _iso(now + LEASE)}},
                projection={"_id": 0}, return_document=ReturnDocument.AFTER)
            if not run:
                break
            index = run["next_step"]
            if index < len(run["steps"]) and run["steps"][index]["type"] == "wait" and run.get("resume_at"):
                step = run["steps"][index]
                entry = {"index": index, "type": "wait", "label": describe(step), "status": "done",
                         "at": self.now_iso(), "detail": f"Waited {duration(int(step['minutes']))}"}
                run = await self._save(run, {"resume_at": None}, entry=entry, next_step=index + 1)
            try:
                await self.advance(run)
            except Exception:
                logger.exception("Resuming automation run %s failed", run.get("id"))
            done += 1
        return done

    async def run_watcher(self, interval: float = 30.0) -> None:
        while True:
            try:
                await self.resume_due()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Automation watcher sweep failed")
            await asyncio.sleep(interval)

    def start_watcher(self) -> None:
        if os.environ.get("AUTOMATION_WATCHER", "1") in ("0", "false", "no", "off") or self._watcher:
            return
        self._watcher = asyncio.create_task(self.run_watcher())

    async def stop_watcher(self) -> None:
        if self._watcher:
            self._watcher.cancel()
            try:
                await self._watcher
            except (asyncio.CancelledError, Exception):
                pass
            self._watcher = None

    # ------------------------------------------------------------ test runs

    async def dry_run(self, automation: dict, record_type: str, record_id: str) -> dict:
        """What the automation would do for one record, step by step, writing nothing."""
        subject = {"contact": "contact", "deal": "deal", "lead": "lead", "appointment": "appointment"}[record_type]
        ctx = await self.context_for(automation["tenant_id"], subject, record_id)
        if not ctx:
            raise HTTPException(status_code=404, detail="Not found")
        if not await self.matches({**automation, "trigger": {**automation["trigger"], "stage": None,
                                                             "form_id": None, "booking_page_id": None}}, ctx):
            return {"matches": False, "reason": "This record does not meet the automation's conditions", "steps": []}
        run = {"id": "test", "tenant_id": automation["tenant_id"], "automation_id": automation["id"],
               "automation_name": automation["name"], "workspace_id": (ctx.get("workspace") or {}).get("id")}
        out = []
        for index, step in enumerate(automation.get("steps") or []):
            if step["type"] == "wait":
                out.append({"index": index, "label": describe(step), "detail": f"Would wait {duration(int(step['minutes']))}, then check the stop rules"})
                continue
            detail, _ = await self.perform(step, run, ctx, dry_run=True)
            out.append({"index": index, "label": render(describe(step), ctx), "detail": detail})
        return {"matches": True, "contact": (ctx.get("contact") or {}).get("name"), "steps": out}


# --------------------------------------------------------------------------- routes

def register_automation_routes(router: Any, engine: AutomationEngine, get_current_user: Any,
                               require_role: Any) -> None:
    db = engine.db

    def public(doc: dict) -> dict:
        doc.pop("_id", None)
        return doc

    async def load(automation_id: str, user: dict) -> dict:
        doc: Optional[dict] = await db[AUTOMATIONS].find_one(
            {"tenant_id": user["tenant_id"], "id": automation_id, "status": {"$ne": "archived"}}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        return doc

    @router.get("/automations/catalog")
    async def catalog(user: dict = Depends(get_current_user)) -> dict:
        return {"triggers": [{"event": key, **value} for key, value in TRIGGERS.items()],
                "steps": [{"type": key, "label": value} for key, value in STEP_TYPES.items()],
                "stop_rules": [{"key": key, "label": value} for key, value in STOP_RULES.items()],
                "settable": {obj: {field: list(values) for field, values in fields.items()} for obj, fields in SETTABLE.items()},
                "recipes": [{"key": key, "name": r["name"], "description": r["description"],
                             "trigger": TRIGGERS[r["trigger"]["event"]]["label"],
                             "steps": [describe(s) for s in r["steps"]]} for key, r in RECIPES.items()]}

    @router.get("/automations")
    async def list_automations(user: dict = Depends(get_current_user)) -> dict:
        items = await db[AUTOMATIONS].find({"tenant_id": user["tenant_id"], "status": {"$ne": "archived"}},
                                           {"_id": 0}).sort("created_at", 1).to_list(MAX_AUTOMATIONS)
        for item in items:
            item["active_runs"] = await db[RUNS].count_documents(
                {"tenant_id": user["tenant_id"], "automation_id": item["id"], "status": {"$in": list(ACTIVE)}})
            item["trigger_label"] = TRIGGERS.get(item["trigger"]["event"], {}).get("label")
        return {"items": items}

    async def save_new(user: dict, body: dict) -> dict:
        return await engine.create(user["tenant_id"], user["email"], body)

    @router.post("/automations")
    async def create_automation(inp: AutomationInput, user: dict = Depends(require_role("admin"))) -> dict:
        return await save_new(user, inp.model_dump())

    @router.post("/automations/from-recipe")
    async def from_recipe(inp: RecipeInput, user: dict = Depends(require_role("admin"))) -> dict:
        if inp.recipe not in RECIPES:
            raise HTTPException(status_code=404, detail="Not found")
        return await save_new(user, engine.recipe_body(inp.recipe))

    @router.get("/automations/{automation_id}")
    async def get_automation(automation_id: str, user: dict = Depends(get_current_user)) -> dict:
        doc = await load(automation_id, user)
        doc["trigger_label"] = TRIGGERS.get(doc["trigger"]["event"], {}).get("label")
        doc["step_labels"] = [describe(step) for step in doc.get("steps") or []]
        return doc

    @router.patch("/automations/{automation_id}")
    async def update_automation(automation_id: str, inp: AutomationPatch,
                                user: dict = Depends(require_role("admin"))) -> dict:
        doc = await load(automation_id, user)
        tenant = user["tenant_id"]
        changes: dict[str, Any] = {}
        if inp.name is not None:
            changes["name"] = inp.name.strip()
        if inp.description is not None:
            changes["description"] = inp.description.strip() or None
        if inp.trigger is not None:
            changes["trigger"] = engine.clean_trigger(inp.trigger)
        if inp.conditions is not None:
            changes["conditions"] = record_fields.clean_filters(inp.conditions)
            await record_fields.compile_filters(db, tenant, "contacts", changes["conditions"])
        if inp.steps is not None:
            changes["steps"] = await engine.clean_steps(tenant, inp.steps)
        if inp.stop_rules is not None:
            changes["stop_rules"] = engine.clean_stop_rules(inp.stop_rules)
        if inp.once_per_contact is not None:
            changes["once_per_contact"] = inp.once_per_contact
        if changes:
            changes.update(version=int(doc.get("version") or 1) + 1, updated_at=engine.now_iso())
            await db[AUTOMATIONS].update_one({"tenant_id": tenant, "id": automation_id}, {"$set": changes})
            await engine.record_event("automation.updated", "automation", automation_id, tenant, user["email"],
                                      payload={"changed": sorted(k for k in changes if k not in ("version", "updated_at")),
                                               "version": changes["version"]})
        updated: dict = await get_automation(automation_id, user)
        return updated

    @router.post("/automations/{automation_id}/status")
    async def set_status(automation_id: str, inp: StatusInput, user: dict = Depends(require_role("admin"))) -> dict:
        doc = await load(automation_id, user)
        if inp.status == "on" and not doc.get("steps"):
            raise _bad("Add at least one step before turning it on")
        await db[AUTOMATIONS].update_one({"tenant_id": user["tenant_id"], "id": automation_id},
                                         {"$set": {"status": inp.status, "updated_at": engine.now_iso()}})
        stopped = 0
        if inp.status == "off":
            # Waiting runs end now, with the reason on their receipt, rather than waking
            # later to find the automation off.
            async for run in db[RUNS].find({"tenant_id": user["tenant_id"], "automation_id": automation_id,
                                            "status": "waiting"}, {"_id": 0}):
                await engine._finish(run, "stopped", stop_reason="The automation was turned off")
                stopped += 1
        await engine.record_event(f"automation.turned_{inp.status}", "automation", automation_id, user["tenant_id"],
                                  user["email"], payload={"stopped_runs": stopped})
        return {"status": inp.status, "stopped_runs": stopped}

    @router.delete("/automations/{automation_id}")
    async def archive_automation(automation_id: str, user: dict = Depends(require_role("admin"))) -> dict:
        await set_status(automation_id, StatusInput(status="off"), user)
        await db[AUTOMATIONS].update_one({"tenant_id": user["tenant_id"], "id": automation_id},
                                         {"$set": {"status": "archived", "archived_at": engine.now_iso()}})
        await engine.record_event("automation.archived", "automation", automation_id, user["tenant_id"], user["email"])
        return {"ok": True}

    @router.post("/automations/{automation_id}/test")
    async def test_automation(automation_id: str, inp: TestInput, user: dict = Depends(require_role("admin"))) -> dict:
        return await engine.dry_run(await load(automation_id, user), inp.record_type, inp.record_id)

    @router.get("/automations/{automation_id}/runs")
    async def list_runs(automation_id: str, limit: int = 50, user: dict = Depends(get_current_user)) -> dict:
        await load(automation_id, user)
        limit = max(1, min(int(limit or 50), 200))
        items = await db[RUNS].find({"tenant_id": user["tenant_id"], "automation_id": automation_id},
                                    {"_id": 0, "steps": 0}).sort("created_at", -1).to_list(limit)
        counts: dict[str, int] = {}
        async for row in db[RUNS].aggregate([{"$match": {"tenant_id": user["tenant_id"], "automation_id": automation_id}},
                                             {"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
            counts[row["_id"]] = row["n"]
        return {"items": items, "counts": counts}

    @router.get("/automation-runs/{run_id}")
    async def get_run(run_id: str, user: dict = Depends(get_current_user)) -> dict:
        run: Optional[dict] = await db[RUNS].find_one({"tenant_id": user["tenant_id"], "id": run_id}, {"_id": 0})
        if not run:
            raise HTTPException(status_code=404, detail="Not found")
        return run

    @router.post("/automation-runs/{run_id}/stop")
    async def stop_run(run_id: str, user: dict = Depends(require_role("admin"))) -> dict:
        run = await db[RUNS].find_one({"tenant_id": user["tenant_id"], "id": run_id, "status": {"$in": list(ACTIVE)}},
                                      {"_id": 0})
        if not run:
            raise HTTPException(status_code=404, detail="Not found")
        return await engine._finish(run, "stopped", stop_reason=f"Stopped by {user['email']}")
