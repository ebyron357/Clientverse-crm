"""Industry templates: a starting setup for the kind of business using ClientVerse.

ClientVerse serves any business; real estate is one template among several. A template
is a starting point, not a mode: it adds a pipeline, booking pages, a website form, the
fields that trade tracks and draft automations, through the same builders the screens use.

Applying a template only adds what is missing, so it is safe to apply twice or to switch:

* the pipeline's stages are set only while the business has never changed them and no
  deal, form or booking page uses a stage the template would remove;
* a booking page, form, field or automation is added only when none with that name exists
  (an archived booking page, form or automation does not count; an archived field does, so
  restoring it brings its values back);
* nothing already there is renamed, changed or removed.

The preview reports the same plan without writing anything, so a person sees exactly what
a template will add, and what it will leave alone and why, before choosing it.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException

import automations
import booking
import crm_core
import record_fields
import website_forms as wf

LOST = {"key": "lost", "label": "Lost", "probability": 0, "is_closed": True, "is_won": False}


def _stages(*open_stages: tuple[str, int], won: str = "Won") -> list[dict]:
    stages = [{"key": re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_"), "label": label,
               "probability": probability, "is_closed": False, "is_won": False}
              for label, probability in open_stages]
    stages.append({"key": "won", "label": won, "probability": 100, "is_closed": True, "is_won": True})
    stages.append(dict(LOST))
    return stages


def _choice(key: str, label: str, options: list[str], required: bool = False) -> dict:
    return {"key": key, "label": label, "type": "select", "options": options, "required": required}


CONTACT_BASICS = [{"key": "first_name", "required": True}, {"key": "last_name", "required": True},
                  {"key": "email", "required": True}, {"key": "phone"}]

TEMPLATES: dict[str, dict[str, Any]] = {
    "agency": {
        "label": "Agency & services", "icon": "briefcase",
        "description": "Marketing, design, IT and other service businesses that win clients through calls and proposals.",
        "stages": _stages(("Lead", 10), ("Qualified", 25), ("Proposal", 50), ("Negotiation", 75)),
        "booking_pages": [("Discovery call", "meeting", 30), ("Strategy session", "meeting", 45), ("Client check-in", "meeting", 30)],
        "form": {"name": "Contact us", "fields": [
            *CONTACT_BASICS,
            {"key": "company"},
            _choice("custom_service", "What do you need?", ["Website", "SEO", "Ads", "Content", "Automation", "Something else"]),
            _choice("custom_budget", "Budget", ["Under $2,000", "$2,000 to $10,000", "$10,000 to $50,000", "Over $50,000"]),
            {"key": "message"},
        ]},
        "fields": [("contacts", "Budget", "number", None), ("contacts", "Service", "select", ["Website", "SEO", "Ads", "Content", "Automation"]),
                   ("deals", "Contract length", "select", ["One-off project", "Monthly", "12 months", "24 months"])],
        "automations": ["speed_to_lead", "deal_won_onboarding", "no_show_rebook"],
    },
    "real_estate": {
        "label": "Real estate", "icon": "home",
        "description": "Agents and teams: showings, buyer and listing consultations, and deals valued at commission.",
        "stages": _stages(("New lead", 10), ("Appointment set", 25), ("Showing", 40), ("Offer", 60), ("Pending", 85), won="Closed"),
        "booking_pages": [("Home showing", "home_showing", None), ("Buyer consultation", "buyer_consultation", None),
                          ("Listing appointment", "listing_appointment", None)],
        "form": {"name": "Showing request", "preset": "showing_request"},
        "fields": [("contacts", "Pre-approved", "checkbox", None), ("contacts", "Preferred areas", "text", None),
                   ("deals", "Property type", "select", ["House", "Condo", "Townhouse", "Land", "Multi-family"])],
        "automations": ["speed_to_lead", "no_show_rebook", "nurture_quiet_lead"],
    },
    "home_services": {
        "label": "Home services", "icon": "wrench",
        "description": "Trades and home services: estimates on site, jobs booked and done.",
        "stages": _stages(("New request", 10), ("Estimate booked", 30), ("Estimate sent", 50), ("Job booked", 80), won="Done"),
        "booking_pages": [("On-site estimate", "meeting", 60), ("Service call", "meeting", 60)],
        "form": {"name": "Request a quote", "fields": [
            *CONTACT_BASICS,
            {"key": "custom_service_address", "label": "Service address", "type": "text", "required": True},
            _choice("custom_job_type", "Job type", ["Repair", "Installation", "Maintenance", "Emergency"], required=True),
            {"key": "preferred_date"},
            {"key": "message"},
        ]},
        "fields": [("contacts", "Service address", "text", None),
                   ("deals", "Job type", "select", ["Repair", "Installation", "Maintenance", "Emergency"])],
        "automations": ["speed_to_lead", "no_show_rebook", "nurture_quiet_lead"],
    },
    "health_wellness": {
        "label": "Health & wellness", "icon": "sparkles",
        "description": "Gyms, studios, clinics and therapists: consultations that become memberships or plans.",
        "stages": _stages(("Inquiry", 10), ("Consult booked", 35), ("Plan offered", 60), won="Member"),
        "booking_pages": [("Free consultation", "meeting", 30), ("Intro session", "meeting", 45)],
        "form": {"name": "Book a free consultation", "fields": [
            *CONTACT_BASICS,
            {"key": "custom_goal", "label": "What would you like to achieve?", "type": "textarea"},
            {"key": "preferred_time"},
        ]},
        "fields": [("contacts", "Goal", "text", None),
                   ("contacts", "Membership plan", "select", ["Drop-in", "Monthly", "Annual"])],
        "automations": ["speed_to_lead", "nurture_quiet_lead", "no_show_rebook"],
    },
    "coaching": {
        "label": "Coaching & consulting", "icon": "users",
        "description": "Coaches and consultants: a discovery call, a proposal, then a program.",
        "stages": _stages(("Lead", 10), ("Discovery call", 30), ("Proposal", 60), won="Enrolled"),
        "booking_pages": [("Discovery call", "meeting", 30), ("Coaching session", "meeting", 60)],
        "form": {"name": "Apply for coaching", "fields": [
            *CONTACT_BASICS,
            {"key": "custom_goal", "label": "Your goal", "type": "textarea", "required": True},
            _choice("custom_budget", "Budget", ["Under $1,000", "$1,000 to $5,000", "Over $5,000"]),
        ]},
        "fields": [("contacts", "Goal", "text", None), ("contacts", "Budget", "number", None),
                   ("deals", "Program", "select", ["1:1 coaching", "Group program", "Workshop"])],
        "automations": ["speed_to_lead", "deal_won_onboarding", "nurture_quiet_lead"],
    },
    "b2b_sales": {
        "label": "B2B sales", "icon": "chart",
        "description": "Companies selling to companies: qualify, demo, propose, negotiate.",
        "stages": _stages(("Lead", 10), ("Qualified", 20), ("Demo", 40), ("Proposal", 60), ("Negotiation", 80)),
        "booking_pages": [("Intro call", "meeting", 30), ("Demo", "meeting", 45)],
        "form": {"name": "Talk to sales", "fields": [
            *CONTACT_BASICS,
            {"key": "company", "required": True},
            _choice("custom_team_size", "Team size", ["1 to 10", "11 to 50", "51 to 200", "201 to 1,000", "1,000+"]),
            {"key": "custom_role", "label": "Your role", "type": "text"},
            {"key": "message"},
        ]},
        "fields": [("companies", "Employees", "number", None), ("contacts", "Decision maker", "checkbox", None),
                   ("deals", "Contract length", "select", ["Monthly", "12 months", "24 months", "36 months"])],
        "automations": ["speed_to_lead", "deal_won_onboarding", "lost_deal_check_in"],
    },
}


def form_questions(template: dict) -> list[str]:
    """What the template's form asks beyond name, email and phone, as labels."""
    form = template["form"]
    specs = form.get("fields") or wf.PRESETS[form["preset"]]["fields"]
    basics = {"first_name", "last_name", "name", "email", "phone", "consent_sms", "consent_email"}
    return [spec.get("label") or wf.FIELD_CATALOG.get(spec["key"], {}).get("label", spec["key"])
            for spec in specs if spec["key"] not in basics]


def summary(key: str, template: dict, recipes: dict) -> dict:
    return {"key": key, "label": template["label"], "icon": template["icon"], "description": template["description"],
            "stages": [s["label"] for s in template["stages"] if not (s["is_closed"] and not s["is_won"])],
            "booking_pages": [name for name, _, _ in template["booking_pages"]],
            "form": template["form"]["name"], "form_asks": form_questions(template),
            "fields": [{"object": obj, "label": label} for obj, label, _, _ in template["fields"]],
            "automations": [recipes[r]["name"] for r in template["automations"]]}


class TemplateService:
    def __init__(self, db: Any, *, new_id: Callable[[str], str], now_iso: Callable[[], str],
                 record_event: Callable[..., Any], engine: Any) -> None:
        self.db = db
        self.new_id = new_id
        self.now_iso = now_iso
        self.record_event = record_event
        self.engine = engine  # the automation engine, which makes the draft automations

    async def plan(self, tenant: str, key: str, actor: str, *, apply: bool) -> dict:
        """What the template adds and what it leaves alone. With `apply`, do it."""
        template = TEMPLATES[key]
        db = self.db
        items: list[dict] = []

        def note(kind: str, name: str, action: str, detail: str = "") -> None:
            items.append({"kind": kind, "name": name, "action": action, "detail": detail})

        # Pipeline: only an untouched pipeline, and only if no record uses a stage that would go.
        configured = await db[crm_core.PIPELINES].find_one({"tenant_id": tenant, "id": "default"}, {"_id": 0})
        stage_names = " → ".join(s["label"] for s in template["stages"] if not s["is_closed"] or s["is_won"])
        if configured:
            note("pipeline", "Pipeline stages", "keep", "You have set your own stages; they stay as they are.")
        else:
            current = [s["key"] for s in crm_core.DEFAULT_STAGES]
            removed = [k for k in current if k not in {s["key"] for s in template["stages"]}]
            in_use = (await db[crm_core.DEALS].count_documents({"tenant_id": tenant, "stage": {"$in": removed}})
                      or await db[wf.FORMS].count_documents({"tenant_id": tenant, "settings.opportunity.stage": {"$in": removed}})
                      or await db[booking.EVENT_TYPES].count_documents({"tenant_id": tenant, "opportunity.stage": {"$in": removed}}))
            if in_use:
                note("pipeline", "Pipeline stages", "keep", "Deals, forms or booking pages already use your current stages; they stay.")
            else:
                note("pipeline", "Pipeline stages", "add", stage_names)
                if apply:
                    stages = [crm_core.StageConfig(**s).model_dump() for s in template["stages"]]
                    await db[crm_core.PIPELINES].update_one(
                        {"tenant_id": tenant, "id": "default"},
                        {"$set": {"stages": stages, "updated_at": self.now_iso(), "updated_by": actor},
                         "$setOnInsert": {"created_at": self.now_iso()}}, upsert=True)
                    await self.record_event("pipeline.configured", "pipeline", "default", tenant, actor,
                                            payload={"stages": [s["key"] for s in stages], "template": key})

        # Fields, by record type and name.
        for obj, label, kind, options in template["fields"]:
            # An archived field counts: its values are kept, and restoring it brings them back.
            existing = await db[record_fields.FIELD_DEFS].find_one(
                {"tenant_id": tenant, "object": obj, "label": {"$regex": f"^{re.escape(label)}$", "$options": "i"}},
                {"_id": 0, "archived_at": 1})
            singular = {"contacts": "contact", "companies": "company", "deals": "deal"}[obj]
            if existing:
                note("field", f"{label} ({singular})", "keep",
                     "Archived; restore it in Settings → Fields" if existing.get("archived_at") else "Already a field")
                continue
            note("field", f"{label} ({singular})", "add", record_fields_type_label(kind))
            if apply:
                await record_fields.create_definition(db, tenant, obj, label, kind, options=options, actor=actor,
                                                      new_id=self.new_id, now_iso=self.now_iso, record_event=self.record_event)

        # Booking pages, by name.
        for name, preset, minutes in template["booking_pages"]:
            if await db[booking.EVENT_TYPES].find_one(
                    {"tenant_id": tenant, "name": {"$regex": f"^{re.escape(name)}$", "$options": "i"},
                     "status": {"$ne": "archived"}}, {"_id": 1}):
                note("booking_page", name, "keep", "A booking page with this name exists")
                continue
            duration = minutes or booking.PRESETS[preset]["duration"]
            note("booking_page", name, "add", f"{duration} minutes, hosted by you")
            if apply:
                doc = booking.new_event_type(preset, tenant_id=tenant, name=name, creator=actor,
                                             new_id=self.new_id, now=self.now_iso())
                doc["duration_minutes"] = duration
                doc = booking.validate_event_type(doc)
                await db[booking.EVENT_TYPES].insert_one(dict(doc))
                await self.record_event("booking_page.created", "booking_page", doc["id"], tenant, actor,
                                        payload={"name": doc["name"], "preset": preset, "template": key})

        # The website form, by name.
        form = template["form"]
        if await db[wf.FORMS].find_one({"tenant_id": tenant, "name": {"$regex": f"^{re.escape(form['name'])}$", "$options": "i"},
                                        "status": {"$ne": "archived"}}, {"_id": 1}):
            note("form", form["name"], "keep", "A form with this name exists")
        else:
            note("form", form["name"], "add", "Asks for " + ", ".join(form_questions(template)))
            if apply:
                await self._create_form(tenant, actor, form, key)

        # Draft automations, by name. They start off: a person reviews and turns them on.
        for recipe_key in template["automations"]:
            name = automations.RECIPES[recipe_key]["name"]
            if await db[automations.AUTOMATIONS].find_one(
                    {"tenant_id": tenant, "name": name, "status": {"$ne": "archived"}}, {"_id": 1}):
                note("automation", name, "keep", "Already an automation")
                continue
            note("automation", name, "add", "A draft to review and turn on")
            if apply:
                await self.engine.create(tenant, actor, self.engine.recipe_body(recipe_key))

        if apply:
            await db.tenants.update_one({"tenant_id": tenant}, {"$set": {
                "industry_template": key, "industry_template_applied_at": self.now_iso()}})
            await self.record_event("industry_template.applied", "tenant", tenant, tenant, actor,
                                    payload={"template": key, "added": [i["name"] for i in items if i["action"] == "add"]})
        return {"template": key, "label": template["label"], "applied": apply, "items": items}

    async def _create_form(self, tenant: str, actor: str, form: dict, key: str) -> None:
        preset = form.get("preset") or "custom"
        raw = form.get("fields") or wf.PRESETS[preset]["fields"]
        specs = [wf.FieldSpec(**spec) for spec in raw]
        # Auto-replies need their own approval before anything is sent; a template does not
        # switch one on.
        settings = wf.merge_settings(wf._default_settings(preset), {"auto_reply": {"enabled": False}})
        now = self.now_iso()
        doc = {"id": self.new_id("wf"), "tenant_id": tenant, "name": form["name"], "form_type": preset,
               "public_key": "f_" + secrets.token_urlsafe(18), "status": "active",
               "fields": wf.validate_fields(specs), "settings": settings,
               "stats": {"views": 0, "submissions": 0, "spam_blocked": 0, "last_submission_at": None,
                         "round_robin_cursor": 0},
               "created_by": actor, "created_at": now, "updated_at": now, "captcha_secret_enc": None}
        await self.db[wf.FORMS].insert_one(dict(doc))
        await self.record_event("website_form.created", "website_form", doc["id"], tenant, actor,
                                payload={"name": doc["name"], "preset": preset, "template": key})


def record_fields_type_label(kind: str) -> str:
    return {"text": "Short text", "number": "Number", "select": "Choice", "checkbox": "Yes / no",
            "date": "Date"}.get(kind, kind)


def register_template_routes(router: Any, service: TemplateService, get_current_user: Any,
                             require_role: Any) -> None:
    db = service.db

    def known(key: str) -> str:
        if key not in TEMPLATES:
            raise HTTPException(status_code=404, detail="Not found")
        return key

    @router.get("/industry-templates")
    async def list_templates(user: dict = Depends(get_current_user)) -> dict:
        tenant = await db.tenants.find_one({"tenant_id": user["tenant_id"]}, {"_id": 0, "industry_template": 1})
        return {"items": [summary(key, t, automations.RECIPES) for key, t in TEMPLATES.items()],
                "in_use": (tenant or {}).get("industry_template")}

    @router.get("/industry-templates/{key}/preview")
    async def preview(key: str, user: dict = Depends(get_current_user)) -> dict:
        return await service.plan(user["tenant_id"], known(key), user["email"], apply=False)

    @router.post("/industry-templates/{key}/apply")
    async def apply(key: str, user: dict = Depends(require_role("admin"))) -> dict:
        return await service.plan(user["tenant_id"], known(key), user["email"], apply=True)
