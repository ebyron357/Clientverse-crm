"""Industry templates: a starting setup for the kind of business using ClientVerse.

ClientVerse serves any business; real estate is one template among several. A template
is a starting point, not a mode: it adds a pipeline, booking pages, a website form, the
fields that trade tracks and draft automations, through the same builders the screens use.

Applying a template only adds what is missing, so it is safe to apply twice or to switch.
A template is loaded by `setup_loader`, the engine snapshots use too, so its rules are the
ones there: nothing already there is renamed, changed or removed, and the preview reports
the same plan without writing anything.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import Depends, HTTPException

import automations
import setup_loader
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


def template_contents(key: str) -> dict:
    """A template as a setup the loader takes, the same shape a snapshot holds."""
    template = TEMPLATES[key]
    form = template["form"]
    preset = form.get("preset") or "custom"
    return {
        "pipeline": {"stages": template["stages"]},
        "fields": [{"object": obj, "label": label, "type": kind, "options": options, "key": ""}
                   for obj, label, kind, options in template["fields"]],
        "booking_pages": [{"ref": f"page_{index}", "name": name, "preset": page_preset,
                           **({"duration_minutes": minutes} if minutes else {})}
                          for index, (name, page_preset, minutes) in enumerate(template["booking_pages"], 1)],
        "forms": [{"ref": "form_1", "name": form["name"], "form_type": preset,
                   "fields": form.get("fields") or wf.PRESETS[preset]["fields"], "settings": {}}],
        "automations": [{k: automations.RECIPES[recipe][k] for k in ("name", "description", "trigger", "steps", "stop_rules")}
                        for recipe in template["automations"]],
        "views": [],
    }


class TemplateService:
    def __init__(self, loader: setup_loader.SetupLoader) -> None:
        self.loader = loader
        self.db = loader.db

    async def plan(self, tenant: str, key: str, actor: str, *, apply: bool) -> dict:
        """What the template adds and what it leaves alone. With `apply`, do it."""
        template = TEMPLATES[key]
        items = await self.loader.plan(tenant, template_contents(key), actor, apply=apply, origin={"template": key})
        if apply:
            await self.db.tenants.update_one({"tenant_id": tenant}, {"$set": {
                "industry_template": key, "industry_template_applied_at": self.loader.now_iso()}})
            await self.loader.record_event("industry_template.applied", "tenant", tenant, tenant, actor,
                                           payload={"template": key, "added": [i["name"] for i in items if i["action"] == "add"]})
        return {"template": key, "label": template["label"], "applied": apply, "items": items}


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
