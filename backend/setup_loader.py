"""Loading a workspace setup: the engine behind industry templates and snapshots.

A setup is the configuration of a CRM, never its records: pipeline stages, custom fields,
booking pages, website forms, automations and shared saved views. An industry template is
a setup written in code; a snapshot is one captured from a workspace. Both load the same
way, through the same validators the screens use, and only ever add what is missing:

* the pipeline's stages are set only while the workspace has never changed them and no
  deal, form or booking page uses a stage that would go or change between open, won and
  lost;
* a field is matched by record type and label, a booking page, form or automation by
  name, a saved view by record type and name; one that exists is left as it is (an
  archived booking page, form or automation does not count; an archived field does, so
  restoring it brings its values back);
* nothing already there is renamed, changed or removed.

People never travel with a setup. Booking pages are hosted by the person loading them,
forms assign nobody, and an automation step that named someone falls back to the
record's owner or round robin. Automations arrive as drafts and form auto-replies off.

References inside a setup are rewritten for the workspace it lands in: an automation
that started from one form starts from that form's copy, and a filter on a custom field
uses the key that field has here. An item that cannot load is skipped with the reason;
the rest still load. The preview reports the same plan without writing anything.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import ValidationError

import automations
import booking
import crm_core
import record_fields
import website_forms as wf

SECTIONS = ("pipeline", "fields", "booking_pages", "forms", "automations", "views")
LIMITS = {"fields": 100, "booking_pages": 50, "forms": 50, "automations": 50, "views": 50}
SINGULAR = {"contacts": "contact", "companies": "company", "deals": "deal"}
LIST_NAMES = {"contacts": "contacts", "companies": "companies", "deals": "deals"}

# What a booking page carries to another workspace. Its link, host, brand name and
# counters belong to the workspace it was made in.
PAGE_SETTINGS = ("description", "duration_minutes", "buffer_before_minutes", "buffer_after_minutes",
                 "min_notice_hours", "max_days_ahead", "slot_interval_minutes", "location", "questions",
                 "confirmation_message", "opportunity", "prep_task", "reminders", "notify_person",
                 "consent", "color")
# What a form carries. Its website addresses, redirect, lead assignment (people) and
# CAPTCHA keys do not; the auto-reply carries its wording but never its approval.
FORM_SETTINGS = ("submit_text", "success_message", "duplicate_policy", "tags", "opportunity",
                 "speed_to_lead", "notify", "auto_reply", "consent", "theme", "remember_visitor")
BASIC_QUESTIONS = {"first_name", "last_name", "name", "email", "phone", "consent_sms", "consent_email"}
TYPE_LABELS = {"text": "Short text", "long_text": "Long text", "number": "Number", "date": "Date",
               "select": "Choice", "checkbox": "Yes / no", "email": "Email", "phone": "Phone",
               "url": "Web address"}


def _bad(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail=message)


def _named(name: str) -> dict:
    return {"$regex": f"^{re.escape(name)}$", "$options": "i"}


def _clip(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _reason(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    if isinstance(exc, ValidationError):
        errors = exc.errors()
        if not errors:
            return "not valid"
        where = ".".join(str(part) for part in errors[0]["loc"])
        return f"{where}: {errors[0]['msg']}" if where else errors[0]["msg"]
    return str(exc) or "not valid"


# Anything a setup's contents can be built from may be malformed when it comes from a
# file, so each item is checked by the real validator and these are what they raise.
INVALID = (HTTPException, ValidationError, booking.BookingInvalid, TypeError, ValueError, AttributeError, KeyError)


def page_settings(doc: dict) -> dict:
    return {key: doc[key] for key in PAGE_SETTINGS if key in doc}


def form_settings(settings: dict) -> dict:
    out = {key: settings[key] for key in FORM_SETTINGS if key in settings}
    reply = settings.get("auto_reply") or {}
    out["auto_reply"] = {"enabled": False, "subject": reply.get("subject"), "body": reply.get("body")}
    return out


def people_free_steps(steps: list) -> list:
    """Automation steps with every named person replaced: a task for someone becomes a
    task for the record's owner, assigning someone becomes round robin."""
    out = []
    for step in steps:
        if not isinstance(step, dict):
            out.append(step)
            continue
        step = {k: v for k, v in step.items() if k != "email"}
        if step.get("type") == "create_task" and step.get("assign") == "specific":
            step["assign"] = "record_owner"
        if step.get("type") == "assign_owner" and step.get("mode") == "specific":
            step["mode"] = "round_robin"
        out.append(step)
    return out


def form_asks(fields: list[dict]) -> list[str]:
    """What a form asks beyond name, email and phone, as labels."""
    return [field.get("label") or wf.FIELD_CATALOG.get(field["key"], {}).get("label", field["key"])
            for field in fields if field["key"] not in BASIC_QUESTIONS]


def check_contents(raw: Any) -> dict:
    """The shape of a setup from outside (a file), before each item meets its validator."""
    if not isinstance(raw, dict):
        raise _bad("The snapshot has no contents")
    out: dict[str, Any] = {"pipeline": None}
    pipeline = raw.get("pipeline")
    if pipeline is not None:
        if not isinstance(pipeline, dict) or not isinstance(pipeline.get("stages"), list):
            raise _bad("The snapshot's pipeline must list its stages")
        out["pipeline"] = {"stages": pipeline["stages"]}
    for section, limit in LIMITS.items():
        items = raw.get(section) or []
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise _bad(f"The snapshot's {section.replace('_', ' ')} must be a list")
        if len(items) > limit:
            raise _bad(f"A snapshot can hold at most {limit} {section.replace('_', ' ')}")
        out[section] = items
    return out


def _rekey(name: Any, obj: str, key_map: dict) -> Any:
    """A field path with a custom field's key swapped for the key it has in this workspace."""
    if isinstance(name, str) and name.startswith("custom_fields."):
        return f"custom_fields.{key_map.get((obj, name[14:]), name[14:])}"
    return name


def _rekey_filters(filters: Any, obj: str, key_map: dict) -> list:
    return [{**item, "field": _rekey(item.get("field"), obj, key_map)} if isinstance(item, dict) else item
            for item in (filters if isinstance(filters, list) else [])]


class SetupLoader:
    def __init__(self, db: Any, *, new_id: Callable[[str], str], now_iso: Callable[[], str],
                 record_event: Callable[..., Any], engine: Any) -> None:
        self.db = db
        self.new_id = new_id
        self.now_iso = now_iso
        self.record_event = record_event
        self.engine = engine  # the automation engine, which makes the draft automations

    async def plan(self, tenant: str, contents: dict, actor: str, *, apply: bool,
                   origin: dict) -> list[dict]:
        """What loading `contents` adds, keeps and skips, and why. With `apply`, do it.
        `origin` (for example {"template": "agency"}) is recorded on every event."""
        items: list[dict] = []

        def note(kind: str, name: str, action: str, detail: str = "") -> dict:
            item = {"kind": kind, "name": name, "action": action, "detail": detail}
            items.append(item)
            return item

        ctx = {"tenant": tenant, "actor": actor, "apply": apply, "origin": origin, "note": note}
        stage_keys = await self._pipeline(ctx, contents.get("pipeline"))
        key_map = await self._fields(ctx, contents.get("fields") or [])
        page_ids = await self._booking_pages(ctx, contents.get("booking_pages") or [], stage_keys)
        form_ids = await self._forms(ctx, contents.get("forms") or [], stage_keys)
        await self._automations(ctx, contents.get("automations") or [], form_ids, page_ids, key_map, stage_keys)
        await self._views(ctx, contents.get("views") or [], key_map)
        return items

    # ------------------------------------------------------------------ pipeline

    async def _pipeline(self, ctx: dict, spec: Optional[dict]) -> set[str]:
        db, tenant, note = self.db, ctx["tenant"], ctx["note"]
        current = await crm_core.resolve_stages(db, tenant)
        current_keys = {s["key"] for s in current}
        if not spec:
            return current_keys
        try:
            stages = [s.model_dump() for s in crm_core.PipelineInput(stages=spec.get("stages") or []).stages]
            keys = [s["key"] for s in stages]
            if len(set(keys)) != len(keys):
                raise _bad("Stage keys must be unique")
            if not any(s["is_closed"] and s["is_won"] for s in stages):
                raise _bad("At least one stage must be a closed-won stage")
            if not any(crm_core.stage_outcome(s) == crm_core.STAGE_OPEN for s in stages):
                raise _bad("Keep at least one open stage")
        except INVALID as exc:
            note("pipeline", "Pipeline stages", "skip", f"Not a pipeline ClientVerse can use: {_reason(exc)}")
            return current_keys
        names = " → ".join(s["label"] for s in stages if not s["is_closed"] or s["is_won"])
        if [(s["key"], s["label"]) for s in stages] == [(s["key"], s["label"]) for s in current]:
            note("pipeline", "Pipeline stages", "keep", "Your stages are already these.")
            return current_keys
        if await db[crm_core.PIPELINES].find_one({"tenant_id": tenant, "id": "default"}, {"_id": 1}):
            note("pipeline", "Pipeline stages", "keep", "You have set your own stages; they stay as they are.")
            return current_keys
        # A stage that would go, or switch between open, won and lost, must hold nothing.
        incoming = {s["key"]: crm_core.stage_outcome(s) for s in stages}
        touched = [s["key"] for s in current
                   if s["key"] not in incoming or incoming[s["key"]] != crm_core.stage_outcome(s)]
        in_use = touched and (
            await db[crm_core.DEALS].count_documents({"tenant_id": tenant, "stage": {"$in": touched}})
            or await db[wf.FORMS].count_documents({"tenant_id": tenant, "settings.opportunity.stage": {"$in": touched}})
            or await db[booking.EVENT_TYPES].count_documents({"tenant_id": tenant, "opportunity.stage": {"$in": touched}}))
        if in_use:
            note("pipeline", "Pipeline stages", "keep", "Deals, forms or booking pages already use your current stages; they stay.")
            return current_keys
        note("pipeline", "Pipeline stages", "add", names)
        if ctx["apply"]:
            await db[crm_core.PIPELINES].update_one(
                {"tenant_id": tenant, "id": "default"},
                {"$set": {"stages": stages, "updated_at": self.now_iso(), "updated_by": ctx["actor"]},
                 "$setOnInsert": {"created_at": self.now_iso()}}, upsert=True)
            await self.record_event("pipeline.configured", "pipeline", "default", tenant, ctx["actor"],
                                    payload={"stages": keys, **ctx["origin"]})
        return set(keys)

    # ------------------------------------------------------------------ fields

    async def _fields(self, ctx: dict, specs: list[dict]) -> dict[tuple[str, str], str]:
        db, tenant, note = self.db, ctx["tenant"], ctx["note"]
        key_map: dict[tuple[str, str], str] = {}
        for raw in specs:
            obj, label, kind = raw.get("object"), _clip(raw.get("label"), 80), raw.get("type")
            name = f"{label or 'A field'} ({SINGULAR.get(str(obj), str(obj))})"
            if obj not in record_fields.OBJECTS or not label or kind not in record_fields.FIELD_TYPES:
                note("field", name, "skip", "Not a field ClientVerse can make")
                continue
            source_key = str(raw.get("key") or "")
            # An archived field counts: its values are kept, and restoring it brings them back.
            existing = await db[record_fields.FIELD_DEFS].find_one(
                {"tenant_id": tenant, "object": obj, "label": _named(label)}, {"_id": 0, "key": 1, "archived_at": 1})
            if existing:
                key_map[(obj, source_key)] = existing["key"]
                note("field", name, "keep",
                     "Archived; restore it in Settings → Fields" if existing.get("archived_at") else "Already a field")
                continue
            try:
                options = record_fields.clean_options(kind, raw.get("options"))
            except INVALID as exc:
                note("field", name, "skip", _reason(exc))
                continue
            item = note("field", name, "add", TYPE_LABELS.get(kind, kind))
            if ctx["apply"]:
                try:
                    doc = await record_fields.create_definition(
                        db, tenant, obj, label, kind, options=options, help_text=_clip(raw.get("help_text"), 200) or None,
                        actor=ctx["actor"], new_id=self.new_id, now_iso=self.now_iso, record_event=self.record_event)
                    key_map[(obj, source_key)] = doc["key"]
                except INVALID as exc:
                    item.update(action="skip", detail=_reason(exc))
        return key_map

    # ------------------------------------------------------------------ booking pages

    async def _booking_pages(self, ctx: dict, specs: list[dict], stage_keys: set[str]) -> dict[str, str]:
        db, tenant, note = self.db, ctx["tenant"], ctx["note"]
        ids: dict[str, str] = {}
        for raw in specs:
            name, ref = _clip(raw.get("name"), 120), str(raw.get("ref") or "")
            if not name:
                note("booking_page", "A booking page", "skip", "It has no name")
                continue
            existing = await db[booking.EVENT_TYPES].find_one(
                {"tenant_id": tenant, "name": _named(name), "status": {"$ne": "archived"}}, {"_id": 0, "id": 1})
            if existing:
                ids[ref] = existing["id"]
                note("booking_page", name, "keep", "A booking page with this name exists")
                continue
            requested = str(raw.get("preset") or "")
            preset = requested if requested in booking.PRESETS else "meeting"
            doc = booking.new_event_type(preset, tenant_id=tenant, name=name, creator=ctx["actor"],
                                         new_id=self.new_id, now=self.now_iso())
            for key, value in page_settings(raw).items():
                # A setting keeps its shape: an object setting from a file must be an object.
                if isinstance(doc.get(key), dict) and not isinstance(value, dict):
                    continue
                doc[key] = value
            doc["status"] = raw.get("status") if raw.get("status") in ("active", "paused") else "active"
            try:
                if isinstance(doc.get("opportunity"), dict) and doc["opportunity"].get("stage") not in stage_keys:
                    doc["opportunity"]["stage"] = None
                doc = booking.validate_event_type(doc)
            except INVALID as exc:
                note("booking_page", name, "skip", _reason(exc))
                continue
            note("booking_page", name, "add", f"{doc['duration_minutes']} minutes, hosted by you")
            ids[ref] = doc["id"]
            if ctx["apply"]:
                await db[booking.EVENT_TYPES].insert_one(dict(doc))
                await self.record_event("booking_page.created", "booking_page", doc["id"], tenant, ctx["actor"],
                                        payload={"name": doc["name"], "preset": preset, **ctx["origin"]})
        return ids

    # ------------------------------------------------------------------ forms

    async def _forms(self, ctx: dict, specs: list[dict], stage_keys: set[str]) -> dict[str, str]:
        db, tenant, note = self.db, ctx["tenant"], ctx["note"]
        ids: dict[str, str] = {}
        for raw in specs:
            name, ref = _clip(raw.get("name"), 120), str(raw.get("ref") or "")
            if not name:
                note("form", "A form", "skip", "It has no name")
                continue
            existing = await db[wf.FORMS].find_one(
                {"tenant_id": tenant, "name": _named(name), "status": {"$ne": "archived"}}, {"_id": 0, "id": 1})
            if existing:
                ids[ref] = existing["id"]
                note("form", name, "keep", "A form with this name exists")
                continue
            requested = str(raw.get("form_type") or "")
            preset = requested if requested in wf.PRESETS else "custom"
            settings_given = raw.get("settings")
            try:
                fields = wf.validate_fields([wf.FieldSpec(**spec) for spec in raw.get("fields") or wf.PRESETS[preset]["fields"]])
                patch = form_settings(settings_given if isinstance(settings_given, dict) else {})
                opportunity = patch.get("opportunity")
                if isinstance(opportunity, dict) and opportunity.get("stage") not in stage_keys:
                    patch["opportunity"] = {**opportunity, "stage": None}
                # Auto-replies need their own approval before anything is sent.
                settings = wf.merge_settings(wf._default_settings(preset), patch)
            except INVALID as exc:
                note("form", name, "skip", _reason(exc))
                continue
            note("form", name, "add", "Asks for " + (", ".join(form_asks(fields)) or "name and contact details"))
            ids[ref] = self.new_id("wf")
            if ctx["apply"]:
                now = self.now_iso()
                doc = {"id": ids[ref], "tenant_id": tenant, "name": name, "form_type": preset,
                       "public_key": "f_" + secrets.token_urlsafe(18),
                       "status": raw.get("status") if raw.get("status") in ("active", "paused") else "active",
                       "fields": fields, "settings": settings,
                       "stats": {"views": 0, "submissions": 0, "spam_blocked": 0, "last_submission_at": None,
                                 "round_robin_cursor": 0},
                       "created_by": ctx["actor"], "created_at": now, "updated_at": now, "captcha_secret_enc": None}
                await db[wf.FORMS].insert_one(dict(doc))
                await self.record_event("website_form.created", "website_form", doc["id"], tenant, ctx["actor"],
                                        payload={"name": name, "preset": preset, **ctx["origin"]})
        return ids

    # ------------------------------------------------------------------ automations

    async def _automations(self, ctx: dict, specs: list[dict], form_ids: dict[str, str], page_ids: dict[str, str],
                           key_map: dict, stage_keys: set[str]) -> None:
        db, tenant, note = self.db, ctx["tenant"], ctx["note"]
        for raw in specs:
            name = _clip(raw.get("name"), 120)
            if not name:
                note("automation", "An automation", "skip", "It has no name")
                continue
            if await db[automations.AUTOMATIONS].find_one(
                    {"tenant_id": tenant, "name": _named(name), "status": {"$ne": "archived"}}, {"_id": 1}):
                note("automation", name, "keep", "Already an automation")
                continue
            given_trigger, given_steps = raw.get("trigger"), raw.get("steps")
            trigger: dict[str, Any] = dict(given_trigger) if isinstance(given_trigger, dict) else {}
            form_ref, page_ref = trigger.pop("form_ref", None), trigger.pop("booking_page_ref", None)
            # An id from another workspace means nothing here; only a reference to an item
            # that came with the setup is followed.
            trigger.pop("form_id", None)
            trigger.pop("booking_page_id", None)
            warnings = []
            if form_ref:
                if form_ref in form_ids:
                    trigger["form_id"] = form_ids[form_ref]
                else:
                    warnings.append("Its form did not come with it, so it starts for any form")
            if page_ref:
                if page_ref in page_ids:
                    trigger["booking_page_id"] = page_ids[page_ref]
                else:
                    warnings.append("Its booking page did not come with it, so it starts for any page")
            if trigger.get("stage") and trigger["stage"] not in stage_keys:
                warnings.append(f"Its stage “{trigger['stage']}” is not in your pipeline; choose one before turning it on")
            steps = people_free_steps(given_steps if isinstance(given_steps, list) else [])
            steps = [{**step, "field": _rekey(step.get("field"), "contacts" if step.get("object", "contact") == "contact" else "deals", key_map)}
                     if isinstance(step, dict) and step.get("type") == "set_field" else step for step in steps]
            body: dict[str, Any] = {"name": name, "description": _clip(raw.get("description"), 500) or None, "trigger": trigger,
                    "conditions": _rekey_filters(raw.get("conditions"), "contacts", key_map), "steps": steps,
                    "stop_rules": raw.get("stop_rules") if isinstance(raw.get("stop_rules"), list) else [],
                    "once_per_contact": raw.get("once_per_contact") is True}
            try:
                parsed = automations.AutomationInput(**body)
                self.engine.clean_trigger(parsed.trigger)
                self.engine.clean_stop_rules(parsed.stop_rules)
            except INVALID as exc:
                note("automation", name, "skip", _reason(exc))
                continue
            item = note("automation", name, "add", ". ".join(["A draft to review and turn on", *warnings]))
            if ctx["apply"]:
                try:
                    await self.engine.create(tenant, ctx["actor"], body)
                except INVALID as exc:
                    item.update(action="skip", detail=_reason(exc))

    # ------------------------------------------------------------------ saved views

    async def _views(self, ctx: dict, specs: list[dict], key_map: dict) -> None:
        db, tenant, note = self.db, ctx["tenant"], ctx["note"]
        for raw in specs:
            obj, name = raw.get("object"), _clip(raw.get("name"), 60)
            label = f"{name or 'A view'} ({LIST_NAMES.get(str(obj), str(obj))})"
            if obj not in record_fields.OBJECTS or not name:
                note("view", label, "skip", "Not a list ClientVerse has")
                continue
            if await db[record_fields.SAVED_VIEWS].find_one(
                    {"tenant_id": tenant, "object": obj, "shared": True, "name": _named(name)}, {"_id": 1}):
                note("view", label, "keep", "A shared view with this name exists")
                continue
            given_sort = raw.get("sort")
            sort: Any = given_sort if isinstance(given_sort, dict) else None
            try:
                inp = record_fields.ViewInput(
                    object=obj, name=name, filters=_rekey_filters(raw.get("filters"), obj, key_map),
                    sort=record_fields.ViewSort(**{**sort, "field": _rekey(sort.get("field"), obj, key_map)}) if sort else None,
                    columns=[_rekey(c, obj, key_map) for c in raw["columns"]] if isinstance(raw.get("columns"), list) else None,
                    shared=True)
                filters, columns = record_fields.clean_filters(inp.filters), record_fields.clean_columns(inp.columns)
            except INVALID as exc:
                note("view", label, "skip", _reason(exc))
                continue
            count = len(filters)
            item = note("view", label, "add", f"Shared with the team, {count} filter{'s' if count != 1 else ''}")
            if ctx["apply"]:
                try:
                    await record_fields.check_view_fields(db, tenant, obj, filters, columns)
                except INVALID as exc:
                    item.update(action="skip", detail=_reason(exc))
                    continue
                now = self.now_iso()
                doc = {"id": self.new_id("view"), "tenant_id": tenant, "object": obj, "name": name,
                       "filters": filters, "sort": inp.sort.model_dump() if inp.sort else None,
                       "columns": columns, "shared": True, "owner": ctx["actor"].lower(),
                       "created_at": now, "updated_at": now}
                await db[record_fields.SAVED_VIEWS].insert_one(dict(doc))
                await self.record_event("saved_view.created", "saved_view", doc["id"], tenant, ctx["actor"],
                                        payload={"object": obj, "name": name, **ctx["origin"]})
