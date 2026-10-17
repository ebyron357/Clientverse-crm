"""Website forms: how a lead on an agent's website becomes worked CRM business, automatically.

The intake door that came before this (`recovery_intake`) recorded a web enquiry and left
it there. Nothing turned it into a contact, nobody was told, and the only thing that
would ever look at it was the recovery detector -- 24 hours later, and only if the
external scheduler ran, which in production it never has. It was also unreachable from
the places leads actually come from: a browser on another domain was refused by CORS, a
plain HTML form was refused for not being JSON, and every real-estate field a form sent
(property address, MLS number, price, timeline, consent) was silently dropped. A lead
that is stored where no one can see it is a lost lead with extra steps.

This module is the whole path, end to end:

1.  **A managed form.** A tenant defines forms from real-estate presets (contact,
    showing request, home valuation, buyer and seller consultations, open house sign-in,
    listing alerts), chooses fields from a catalogue, and gets a public form key, an
    embed script (inline or pop-up), a hosted page that can be linked or framed, and a
    raw HTML snippet for bring-your-own forms. The key is public by design -- it sits in
    a web page's source -- so it authorises exactly one thing: submitting that form.
2.  **A door real websites can use.** Cross-origin requests are answered on the public
    paths only, and never with credentials, because the CRM's own session cookie is
    `SameSite=None`: putting a customer's website into the global CORS list would let
    its scripts act as any CRM user who visited it. JSON, `text/plain` JSON (which a
    browser sends without a preflight), URL-encoded and multipart bodies are all
    accepted, and an HTML form gets a redirect or a thank-you page instead of JSON.
3.  **Nothing dropped.** Every catalogue field is captured typed and bounded; anything
    else a form sends is kept verbatim in `extra`; UTM tags, referrer and page are kept
    as attribution; consent is kept with the wording shown and the evidence for it.
4.  **Abuse handled before it costs anything.** A honeypot field and a minimum fill
    time catch scripted bots, which are answered exactly like a success so they learn
    nothing. Per-visitor and per-form rate limits cap a flood. A retry or double-click
    carrying the same submission id is idempotent, and the same person sending the same
    thing within minutes collapses onto the first submission.
5.  **Automatic follow-through**, in the order a good agent would do it by hand: match
    or create the contact (no duplicates), assign an owner (the existing owner, a named
    agent, or round-robin), open a deal at the configured stage valued at expected
    commission, create a speed-to-lead call-back task due in minutes, alert the agent
    in-app and by email, publish `lead.received` with the full lead to the tenant's
    webhooks (Zapier, SMS tools, Slack), and send the lead an automatic reply.
6.  **A clock that runs.** The speed-to-lead clock is watched in-process -- it does not
    depend on the external scheduler -- and a lead nobody has responded to by the
    escalation deadline is escalated to the admins, once. A response is recognised from
    the call-back task being completed, an activity logged on the contact, or the lead
    being marked responded, and the response time is recorded.

THE AUTOMATIC REPLY AND THE APPROVAL GATE

Every outbound message in this system passes through `conversations.attempt_delivery`,
which requires a human approval bound to the exact words being sent. An automatic reply
to every lead cannot wait for a human per message -- that is the whole point of it -- so
the approval is moved to where a human can actually give it: the *template*. An admin
approves the exact subject and body once. Each lead's reply is then rendered from that
template using only a fixed allowlist of values taken from the lead's own submission and
the assigned agent's name, and still goes through the full choke point: its own
conversation, its own consent record (the basis is the enquiry the person just sent),
its own single-use approval decided by `standing-approval:<id>` with the template
fingerprint and merge values recorded, and the same channel, consent and provider checks
as any other message. Editing the template invalidates the approval. Nothing else is
sent on a standing approval. This is a deliberate, bounded amendment to M-07 at the
owner's direction (2026-10-17), recorded in the canonical governing document.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import html
import io
import json
import logging
import os
import re
import secrets
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

import approval_queue
import conversations as conversation_service
import crm_core
import detectors

logger = logging.getLogger("clientverse.website_forms")

FORMS = "website_forms"
ATTEMPTS = "form_submission_attempts"

SYSTEM_ACTOR = "system:website-forms"

# Paths a browser on any website may call. Nothing under them reads tenant data.
PUBLIC_PATH_PREFIXES = ("/api/public/forms/", "/api/intake/public/")
HOSTED_PAGE_PATH = re.compile(r"^/api/public/forms/[A-Za-z0-9_\-]+/page$")

LEAD_STATUSES = ("new", "responded", "closed", "spam")

RATE_PER_VISITOR_PER_HOUR = int(os.environ.get("FORM_RATE_PER_VISITOR_PER_HOUR", "20"))
RATE_PER_FORM_PER_MINUTE = int(os.environ.get("FORM_RATE_PER_FORM_PER_MINUTE", "120"))
DUPLICATE_WINDOW_MINUTES = int(os.environ.get("FORM_DUPLICATE_WINDOW_MINUTES", "10"))
MIN_FILL_MILLISECONDS = int(os.environ.get("FORM_MIN_FILL_MILLISECONDS", "1200"))
OPEN_DEAL_REUSE_DAYS = int(os.environ.get("FORM_OPEN_DEAL_REUSE_DAYS", "30"))
WATCH_INTERVAL_SECONDS = int(os.environ.get("LEAD_SLA_INTERVAL_SECONDS", "60"))
# Prices used for an expected-commission value. Outside this band the configured flat
# value is used instead.
MIN_PRICE_BASIS = 10_000.0
MAX_PRICE_BASIS = 100_000_000.0

MAX_TEXT = 300
MAX_LONG_TEXT = 4000
MAX_EXTRA_KEYS = 40
MAX_EXTRA_VALUE = 1000

# ----------------------------------------------------------------------- catalogue

_SELECTS = {
    "lead_type": ["Buying", "Selling", "Buying and selling", "Renting", "Investing"],
    "property_condition": ["Move-in ready", "Needs minor work", "Needs major work", "Not sure"],
    "timeline": ["As soon as possible", "1-3 months", "3-6 months", "6-12 months",
                 "12+ months", "Just browsing"],
    "pre_approved": ["Yes", "No", "Paying cash", "Not sure"],
    "working_with_agent": ["No", "Yes"],
    "preferred_time": ["Morning", "Afternoon", "Evening"],
    "preferred_contact": ["Call", "Text", "Email"],
}

FIELD_CATALOG: dict[str, dict] = {
    "first_name": {"label": "First name", "type": "text", "autocomplete": "given-name"},
    "last_name": {"label": "Last name", "type": "text", "autocomplete": "family-name"},
    "name": {"label": "Full name", "type": "text", "autocomplete": "name"},
    "email": {"label": "Email", "type": "email", "autocomplete": "email"},
    "phone": {"label": "Phone", "type": "tel", "autocomplete": "tel"},
    "message": {"label": "Message", "type": "textarea"},
    "lead_type": {"label": "I'm interested in", "type": "select"},
    "property_address": {"label": "Property address", "type": "text",
                         "autocomplete": "street-address"},
    "listing_id": {"label": "MLS / listing number", "type": "text"},
    "price_min": {"label": "Minimum price", "type": "number"},
    "price_max": {"label": "Maximum price", "type": "number"},
    "estimated_home_value": {"label": "Estimated home value", "type": "number"},
    "bedrooms": {"label": "Bedrooms", "type": "number"},
    "bathrooms": {"label": "Bathrooms", "type": "number"},
    "preferred_areas": {"label": "Preferred areas or neighborhoods", "type": "text"},
    "property_condition": {"label": "Property condition", "type": "select"},
    "timeline": {"label": "When are you looking to move?", "type": "select"},
    "pre_approved": {"label": "Pre-approved for a mortgage?", "type": "select"},
    "working_with_agent": {"label": "Are you working with an agent?", "type": "select"},
    "preferred_date": {"label": "Preferred date", "type": "date"},
    "preferred_time": {"label": "Preferred time", "type": "select"},
    "preferred_contact": {"label": "Best way to reach you", "type": "select"},
    "consent_sms": {"label": "Text message consent", "type": "checkbox"},
    "consent_email": {"label": "Email consent", "type": "checkbox"},
}
for _key, _options in _SELECTS.items():
    FIELD_CATALOG[_key]["options"] = _options

NUMBER_FIELDS = {k for k, v in FIELD_CATALOG.items() if v["type"] == "number"}
CHECKBOX_FIELDS = {k for k, v in FIELD_CATALOG.items() if v["type"] == "checkbox"}
LONG_TEXT_FIELDS = {k for k, v in FIELD_CATALOG.items() if v["type"] == "textarea"}

# Captured whenever present; the embed script fills them in itself.
TRACKING_FIELDS = ("page_url", "referrer", "landing_page", "utm_source", "utm_medium",
                   "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid",
                   "listing_url")

CUSTOM_FIELD_TYPES = ("text", "textarea", "select", "checkbox", "number", "date")
CUSTOM_KEY = re.compile(r"^custom_[a-z0-9_]{1,40}$")

DEFAULT_SMS_CONSENT = ("By checking this box, I agree to receive text messages about my "
                       "real estate inquiry. Message and data rates may apply. Reply STOP "
                       "to opt out.")
DEFAULT_EMAIL_CONSENT = "I agree to receive emails about listings and market updates."


def _fields(*spec: tuple) -> list[dict]:
    return [{"key": key, "required": bool(required)} for key, required in spec]


PRESETS: dict[str, dict] = {
    "contact": {
        "label": "Contact",
        "fields": _fields(("first_name", True), ("last_name", False), ("email", True),
                          ("phone", False), ("lead_type", False), ("message", False),
                          ("consent_sms", False)),
        "create_opportunity": True, "submit_text": "Send message",
    },
    "showing_request": {
        "label": "Schedule a showing",
        "fields": _fields(("first_name", True), ("last_name", False), ("email", True),
                          ("phone", True), ("property_address", False),
                          ("listing_id", False), ("preferred_date", False),
                          ("preferred_time", False), ("pre_approved", False),
                          ("working_with_agent", False), ("message", False),
                          ("consent_sms", False)),
        "create_opportunity": True, "submit_text": "Request a showing",
    },
    "home_valuation": {
        "label": "What's my home worth?",
        "fields": _fields(("first_name", True), ("last_name", False), ("email", True),
                          ("phone", False), ("property_address", True), ("bedrooms", False),
                          ("bathrooms", False), ("property_condition", False),
                          ("timeline", False), ("consent_sms", False)),
        "create_opportunity": True, "submit_text": "Get my home value",
    },
    "buyer_consultation": {
        "label": "Buyer consultation",
        "fields": _fields(("first_name", True), ("last_name", False), ("email", True),
                          ("phone", True), ("price_max", False), ("preferred_areas", False),
                          ("bedrooms", False), ("timeline", False), ("pre_approved", False),
                          ("message", False), ("consent_sms", False)),
        "create_opportunity": True, "submit_text": "Start my home search",
    },
    "seller_consultation": {
        "label": "Seller consultation",
        "fields": _fields(("first_name", True), ("last_name", False), ("email", True),
                          ("phone", True), ("property_address", True),
                          ("estimated_home_value", False), ("timeline", False),
                          ("message", False), ("consent_sms", False)),
        "create_opportunity": True, "submit_text": "Talk to an agent",
    },
    "open_house": {
        "label": "Open house sign-in",
        "fields": _fields(("first_name", True), ("last_name", True), ("email", False),
                          ("phone", False), ("working_with_agent", True),
                          ("timeline", False), ("pre_approved", False),
                          ("consent_sms", False)),
        "create_opportunity": True, "submit_text": "Sign in",
    },
    "listing_alerts": {
        "label": "Listing alerts / newsletter",
        "fields": _fields(("first_name", False), ("email", True), ("preferred_areas", False),
                          ("price_max", False), ("consent_email", True)),
        "create_opportunity": False, "submit_text": "Subscribe",
    },
    "custom": {
        "label": "Custom form",
        "fields": _fields(("first_name", True), ("last_name", False), ("email", True),
                          ("phone", False), ("message", False)),
        "create_opportunity": True, "submit_text": "Submit",
    },
}

DEFAULT_AUTO_REPLY_SUBJECT = "Thanks for reaching out, {first_name}"
DEFAULT_AUTO_REPLY_BODY = (
    "Hi {first_name},\n\n"
    "Thanks for your message through our {form_name} form. {agent_name} has it and will "
    "be in touch shortly.\n\n"
    "If it's urgent, just reply to this email.\n")
MERGE_FIELDS = ("first_name", "agent_name", "form_name")


# ------------------------------------------------------------------------ helpers

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime] = None) -> str:
    return (value or _now()).astimezone(timezone.utc).isoformat()


def _parse(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _public(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    return {k: v for k, v in doc.items() if k != "_id"}


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_duplicate_key(exc: Exception) -> bool:
    return getattr(exc, "code", None) == 11000 or "E11000" in str(exc) \
        or "duplicate key" in str(exc).lower()


# One definition of "the same number", shared with contact editing so a number changed
# by hand is matched exactly as one that arrived through a form.
phone_digits = crm_core.phone_digits


def normalise_origin(value: Optional[str]) -> Optional[str]:
    """`https://Example.com/path` -> `https://example.com`. None for anything else."""
    if not value:
        return None
    parsed = urlparse(str(value).strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    port = f":{parsed.port}" if parsed.port and parsed.port not in (80, 443) else ""
    return f"{parsed.scheme}://{parsed.hostname.lower()}{port}"


def parse_amount(value: Any) -> Optional[float]:
    """`$450,000`, `450k`, `1.2m`, `450000` -> a float. None when it is not a number."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        raw = str(value).strip().lower().replace(",", "").replace("$", "").replace(" ", "")
        multiplier = 1.0
        if raw.endswith("k"):
            multiplier, raw = 1_000.0, raw[:-1]
        elif raw.endswith("m"):
            multiplier, raw = 1_000_000.0, raw[:-1]
        try:
            number = float(raw) * multiplier
        except ValueError:
            return None
    if number != number or number < 0 or number > 10_000_000_000:  # NaN or out of range
        return None
    return round(number, 2)


# Hyphen, en dash, em dash, or "to": websites write ranges every one of these ways.
_RANGE_SPLIT = re.compile(r"\s*(?:-|\u2013|\u2014|to)\s*", re.IGNORECASE)


def parse_price_range(value: Any) -> tuple[Optional[float], Optional[float]]:
    """`$400k-$500k` (any dash), `400,000 to 500,000`, `under 300k`, `500k+` -> (low, high)."""
    text = str(value or "").strip().lower()
    if not text:
        return None, None
    text = text.replace("under", "").replace("up to", "").replace("+", "").replace("over", "")
    parts = [p for p in _RANGE_SPLIT.split(text) if p.strip()]
    amounts: list[float] = [a for a in (parse_amount(p) for p in parts[:2]) if a]
    if not amounts:
        return None, None
    return min(amounts), max(amounts)


def normalise_lead_type(value: Any) -> Optional[str]:
    """Map a website's own wording to the catalogue's options, or None if it is not one."""
    text = str(value or "").strip()
    if text in _SELECTS["lead_type"]:
        return text
    lowered = text.lower()
    if ("buy" in lowered and "sell" in lowered) or "both" in lowered:
        return "Buying and selling"
    if "sell" in lowered or "home_value" in lowered or "home value" in lowered \
            or "valuation" in lowered:
        return "Selling"
    if "buy" in lowered or "purchase" in lowered:
        return "Buying"
    if "rent" in lowered or "lease" in lowered:
        return "Renting"
    if "invest" in lowered:
        return "Investing"
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on", "y", "checked",
                                                 "agree", "agreed")


def _clip(value: Any, limit: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


def valid_email(value: str) -> bool:
    return bool(_EMAIL.match(value)) and len(value) <= 254


def _safe_first_name(value: Optional[str]) -> str:
    """A merge value for an outbound template. Anything odd falls back to 'there'."""
    text = str(value or "").strip().split(" ")[0]
    if text and re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ'\-]{1,40}", text):
        return text
    return "there"


def render_template(template: str, values: dict) -> str:
    """Substitute only the allowlisted merge fields; leave every other brace alone."""
    out = template
    for key in MERGE_FIELDS:
        out = out.replace("{" + key + "}", str(values.get(key) or ""))
    return out


def template_fingerprint(subject: str, body: str) -> str:
    return _sha(f"{subject}\n\x1f\n{body}")


def client_ip(request: Request) -> str:
    """The visitor's address. Railway's edge sets X-Real-IP; X-Forwarded-For's last hop
    is the one our own proxy appended, so it is the one a client cannot forge."""
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()[:64]
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


async def read_submission(request: Request) -> tuple[dict, bool]:
    """The body as a flat dict, whatever the form sent it as.

    Returns (data, wants_html): an HTML form post expects a page back, not JSON.
    """
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    accept = (request.headers.get("accept") or "").lower()
    if content_type in ("application/x-www-form-urlencoded", "multipart/form-data"):
        form = await request.form()
        data: dict[str, Any] = {}
        for key, value in form.multi_items():
            if hasattr(value, "filename"):
                continue  # file uploads are not accepted through a public form
            if key in data:  # repeated keys (checkbox groups) are joined, not lost
                data[key] = f"{data[key]}, {value}"
            else:
                data[key] = value
        wants_html = "application/json" not in accept and data.get("_format") != "json"
        return data, wants_html
    raw = await request.body()
    if not raw:
        return {}, False
    if len(raw) > 64_000:
        raise HTTPException(status_code=413, detail="Submission too large")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="Submission must be JSON or form data")
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="Submission must be a JSON object")
    return parsed, False


# ------------------------------------------------------------------ normalisation

class SubmissionInvalid(Exception):
    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def normalise_submission(raw: dict, form: dict) -> dict:
    """Turn whatever a website sent into typed, bounded lead data, losing nothing.

    Known fields are typed; tracking fields go to `attribution`; anything else goes to
    `extra` verbatim (bounded), so a field nobody anticipated is still on the record.
    Control fields (`_hp`, `_sid`, `_elapsed_ms`) are returned separately.
    """
    custom_defs = {f["key"]: f for f in form.get("fields") or [] if CUSTOM_KEY.match(f["key"])}
    control: dict[str, Any] = {}
    fields: dict[str, Any] = {}
    attribution: dict[str, str] = {}
    extra: dict[str, str] = {}
    errors: dict[str, str] = {}

    aliases = {"firstname": "first_name", "fname": "first_name", "lastname": "last_name",
               "lname": "last_name", "full_name": "name", "fullname": "name",
               "your-name": "name", "your-email": "email", "your-message": "message",
               "telephone": "phone", "phone_number": "phone", "mobile": "phone",
               "comments": "message", "address": "property_address", "mls": "listing_id",
               "mls_id": "listing_id", "mls_number": "listing_id", "source_page": "page_url",
               "budget": "price_max", "home_value": "estimated_home_value",
               # The camelCase contract a website's own server sends (see LeadPipeline docs).
               "propertyaddress": "property_address", "timeframe": "timeline",
               "consultationdate": "preferred_date", "consultationtime": "preferred_time",
               "leadtype": "lead_type", "goal": "lead_type", "preapproval": "pre_approved",
               "pre_approval": "pre_approved", "condition": "property_condition",
               "listingid": "listing_id", "pageurl": "page_url", "estimatedhomevalue":
               "estimated_home_value", "pricemin": "price_min", "pricemax": "price_max"}
    control_aliases = {"idempotencykey": "_sid", "idempotency_key": "_sid"}

    # A server integration nests its own extras under `payload`. Lift them to the top
    # level -- without letting them override a top-level field -- so they are typed,
    # aliased and kept like any other field.
    flat: dict[str, Any] = {}
    nested = (raw or {}).get("payload")
    for raw_key, value in (raw or {}).items():
        if raw_key != "payload" or not isinstance(nested, dict):
            flat[raw_key] = value
    if isinstance(nested, dict):
        for raw_key, value in list(nested.items())[:MAX_EXTRA_KEYS]:
            flat.setdefault(raw_key, value)

    for raw_key, value in flat.items():
        key = str(raw_key).strip()
        lowered = key.lower()
        lowered = control_aliases.get(lowered, lowered)
        if lowered in ("_hp", "_sid", "_elapsed_ms", "_format", "external_id",
                       "cf-turnstile-response", "client_ip", "user_agent"):
            control[lowered] = value
            continue
        if lowered in ("pricerange", "price_range"):
            low, high = parse_price_range(value)
            if high is not None:
                fields.setdefault("price_max", high)
                if low is not None and low != high:
                    fields.setdefault("price_min", low)
            if len(extra) < MAX_EXTRA_KEYS:
                extra["price_range"] = _clip(value, MAX_EXTRA_VALUE) or ""
            continue
        if lowered.startswith("_"):
            continue
        key = aliases.get(lowered, lowered)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if key in TRACKING_FIELDS:
            attribution[key] = _clip(value, 1000) or ""
        elif key in CHECKBOX_FIELDS:
            fields[key] = _truthy(value)
        elif key in NUMBER_FIELDS:
            amount = parse_amount(value)
            if amount is None:
                errors[key] = "Enter a number (for example 450000 or 450k)"
            else:
                fields[key] = amount
        elif key == "lead_type":
            if "lead_type" in fields:
                if len(extra) < MAX_EXTRA_KEYS:
                    extra.setdefault(lowered, _clip(value, MAX_EXTRA_VALUE) or "")
                continue
            mapped = normalise_lead_type(value)
            if mapped:
                fields["lead_type"] = mapped
                if mapped != str(value).strip() and len(extra) < MAX_EXTRA_KEYS:
                    extra[f"site_{lowered}"] = _clip(value, MAX_EXTRA_VALUE) or ""
            elif len(extra) < MAX_EXTRA_KEYS:
                # "consultation", "contact": a kind of request, not a buy/sell intent.
                extra[f"site_{lowered}"] = _clip(value, MAX_EXTRA_VALUE) or ""
        elif key in FIELD_CATALOG:
            fields[key] = _clip(value, MAX_LONG_TEXT if key in LONG_TEXT_FIELDS else MAX_TEXT)
        elif key in custom_defs:
            ctype = custom_defs[key].get("type")
            if ctype == "checkbox":
                fields[key] = _truthy(value)
            elif ctype == "number":
                amount = parse_amount(value)
                if amount is None:
                    errors[key] = "Enter a number"
                else:
                    fields[key] = amount
            else:
                fields[key] = _clip(value, MAX_LONG_TEXT if ctype == "textarea" else MAX_TEXT)
        elif len(extra) < MAX_EXTRA_KEYS:
            # Includes a visitor-supplied `estimated_value`: kept as what they said, never
            # trusted as money. A lead's value comes from the form's own configuration.
            extra[str(raw_key).strip()[:60]] = (_clip(value if not isinstance(value, (dict, list))
                                     else json.dumps(value)[:MAX_EXTRA_VALUE],
                                     MAX_EXTRA_VALUE) or "")

    if fields.get("email"):
        fields["email"] = str(fields["email"]).strip().lower()
        if not valid_email(fields["email"]):
            errors["email"] = "Enter a valid email address"
    if fields.get("phone"):
        digits = re.sub(r"\D", "", fields["phone"])
        if not 7 <= len(digits) <= 15:
            errors["phone"] = "Enter a valid phone number"
        fields["phone"] = str(fields["phone"])[:40]

    if not fields.get("name"):
        composed = " ".join(p for p in (fields.get("first_name"), fields.get("last_name")) if p)
        if composed:
            fields["name"] = composed[:MAX_TEXT]
    if fields.get("name") and not fields.get("first_name"):
        fields["first_name"] = fields["name"].split(" ")[0][:MAX_TEXT]

    def shown(spec: dict) -> bool:
        """A conditional field counts only when the answer it depends on matches."""
        condition = spec.get("show_if")
        if not condition:
            return True
        answer = fields.get(condition["field"])
        if isinstance(answer, bool):
            answer = "Yes" if answer else "No"
        return str(answer) in condition["values"] if answer not in (None, "") else False

    for spec in form.get("fields") or []:
        key = spec["key"]
        if not shown(spec):
            # Hidden from the visitor, so neither required nor kept: a stale answer to
            # a question that no longer applied must not reach the record.
            fields.pop(key, None)
            errors.pop(key, None)
            continue
        if not spec.get("required") or key in errors:
            continue
        present = fields.get(key)
        if key in CHECKBOX_FIELDS or (key in custom_defs and custom_defs[key].get("type") == "checkbox"):
            if not present:
                errors[key] = "Please confirm to continue"
        elif present in (None, ""):
            label = (spec.get("label") or FIELD_CATALOG.get(key, {}).get("label") or key)
            errors[key] = f"{label} is required"

    if not form.get("legacy") and not (fields.get("email") or fields.get("phone")) \
            and "email" not in errors and "phone" not in errors:
        errors["email"] = "Enter an email address or a phone number so we can reach you"
    if form.get("legacy") and not (fields.get("email") or fields.get("phone")
                                   or fields.get("message")):
        errors["email"] = "An enquiry needs at least an email, a phone number or a message"

    if errors:
        raise SubmissionInvalid(errors)
    return {"fields": fields, "attribution": attribution, "extra": extra, "control": control}


# ---------------------------------------------------------------- form documents

def _default_settings(preset_key: str) -> dict:
    preset = PRESETS[preset_key]
    return {
        "submit_text": preset["submit_text"],
        "success_message": "Thank you! We received your request and will be in touch shortly.",
        "redirect_url": None,
        "allowed_origins": [],
        "duplicate_policy": "update_existing",
        "tags": ["website-lead", preset_key.replace("_", "-")],
        "assignment": {"mode": "unassigned", "users": [], "keep_existing_owner": True,
                       "weights": {}},
        "opportunity": {"enabled": preset["create_opportunity"], "stage": None,
                        "value_mode": "fixed", "fixed_value": 0.0,
                        "commission_rate": 2.5, "currency": "USD"},
        "speed_to_lead": {"task_enabled": True, "due_minutes": 5,
                          "escalate_after_minutes": 15},
        "notify": {"in_app": True, "email": True},
        "auto_reply": {"enabled": False, "subject": DEFAULT_AUTO_REPLY_SUBJECT,
                       "body": DEFAULT_AUTO_REPLY_BODY, "approval_id": None,
                       "template_sha256": None},
        "consent": {"sms_text": DEFAULT_SMS_CONSENT, "email_text": DEFAULT_EMAIL_CONSENT},
        "theme": {"primary_color": "#1a9fbf", "layout": "stacked"},
        # Pre-fill name, email and phone for a visitor who already submitted a form on
        # this website ("sticky contact"). Off by default: it keeps those details in the
        # visitor's browser, which is wrong on a shared computer.
        "remember_visitor": False,
        # Optional CAPTCHA. The secret is stored encrypted on the form, never here.
        "captcha": {"provider": "none", "site_key": None, "secret_configured": False},
    }


def _field_definition(spec: dict) -> dict:
    key = spec["key"]
    base = FIELD_CATALOG.get(key, {})
    return {
        "key": key,
        "label": spec.get("label") or base.get("label") or key,
        "type": spec.get("type") or base.get("type", "text"),
        "required": bool(spec.get("required")),
        "options": spec.get("options") or base.get("options"),
        "placeholder": spec.get("placeholder"),
        "autocomplete": base.get("autocomplete"),
        "show_if": spec.get("show_if"),
        "step": int(spec.get("step") or 1),
    }


class FieldSpec(BaseModel):
    key: str = Field(min_length=1, max_length=48)
    required: bool = False
    label: Optional[str] = Field(default=None, max_length=200)
    type: Optional[str] = Field(default=None, max_length=20)
    options: Optional[list[str]] = None
    placeholder: Optional[str] = Field(default=None, max_length=200)
    # Conditional display: {"field": "<earlier field key>", "values": ["Selling", ...]}.
    show_if: Optional[dict] = None
    # Multi-step forms: the page this field is on, 1-based.
    step: Optional[int] = Field(default=None, ge=1, le=10)


class FormCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    preset: str = "contact"
    fields: Optional[list[FieldSpec]] = None
    settings: Optional[dict] = None


class FormPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    status: Optional[str] = None
    fields: Optional[list[FieldSpec]] = None
    settings: Optional[dict] = None


class LeadPatch(BaseModel):
    status: str
    note: Optional[str] = Field(default=None, max_length=2000)


class TestLead(BaseModel):
    data: Optional[dict] = None


def validate_fields(specs: list[FieldSpec]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    if len(specs) > 40:
        raise HTTPException(status_code=422, detail="A form can have at most 40 fields")
    for spec in specs:
        key = spec.key.strip().lower()
        if key in seen:
            raise HTTPException(status_code=422, detail=f"Field '{key}' appears twice")
        seen.add(key)
        if key not in FIELD_CATALOG and not CUSTOM_KEY.match(key):
            raise HTTPException(status_code=422,
                                detail=f"Unknown field '{key}'. Custom fields must be named "
                                       "custom_<name> using lowercase letters, digits and _")
        if CUSTOM_KEY.match(key) and (spec.type or "text") not in CUSTOM_FIELD_TYPES:
            raise HTTPException(status_code=422,
                                detail=f"Custom field type must be one of {', '.join(CUSTOM_FIELD_TYPES)}")
        options = [str(o).strip()[:120] for o in (spec.options or []) if str(o).strip()][:50]
        show_if = None
        if spec.show_if:
            target = str(spec.show_if.get("field") or "").strip().lower()
            values = [str(v).strip()[:120] for v in spec.show_if.get("values") or []
                      if str(v).strip()][:20]
            if target not in seen or target == key:
                raise HTTPException(status_code=422,
                                    detail=f"Field '{key}' can only depend on a field above it")
            if not values:
                raise HTTPException(status_code=422,
                                    detail=f"Field '{key}' needs at least one value to show on")
            show_if = {"field": target, "values": values}
        out.append({"key": key, "required": spec.required,
                    "label": (spec.label or "").strip() or None,
                    "type": (spec.type if CUSTOM_KEY.match(key) else None),
                    "options": options or None,
                    "placeholder": (spec.placeholder or "").strip() or None,
                    "show_if": show_if, "step": spec.step or 1})
    steps = sorted({f["step"] for f in out})
    if steps != list(range(1, len(steps) + 1)):
        raise HTTPException(status_code=422,
                            detail="Steps must be numbered 1, 2, 3 … with no gaps")
    for field in out:
        depends_on = (field.get("show_if") or {}).get("field")
        if depends_on and next(f["step"] for f in out if f["key"] == depends_on) > field["step"]:
            raise HTTPException(status_code=422,
                                detail=f"Field '{field['key']}' depends on a field on a later step")
    if not any(f["key"] in ("email", "phone") for f in out):
        raise HTTPException(status_code=422,
                            detail="A form needs an email or a phone field, or no one can "
                                   "follow up on the lead")
    return out


def merge_settings(current: dict, patch: dict) -> dict:
    """Apply a partial settings update, validating every value that changes behaviour."""
    merged = json.loads(json.dumps(current))
    for key, value in (patch or {}).items():
        if key not in merged:
            raise HTTPException(status_code=422, detail=f"Unknown setting '{key}'")
        if isinstance(merged[key], dict):
            if not isinstance(value, dict):
                raise HTTPException(status_code=422, detail=f"Setting '{key}' must be an object")
            for sub, sub_value in value.items():
                if sub not in merged[key]:
                    raise HTTPException(status_code=422, detail=f"Unknown setting '{key}.{sub}'")
                merged[key][sub] = sub_value
        else:
            merged[key] = value

    for key in ("submit_text", "success_message"):
        merged[key] = (_clip(merged.get(key), 500) or _default_settings("contact")[key])
    redirect = merged.get("redirect_url")
    if redirect:
        if not normalise_origin(redirect):
            raise HTTPException(status_code=422, detail="redirect_url must be an http(s) URL")
        merged["redirect_url"] = str(redirect).strip()[:1000]
    origins = []
    for origin in merged.get("allowed_origins") or []:
        normalised = normalise_origin(origin)
        if not normalised:
            raise HTTPException(status_code=422,
                                detail=f"'{origin}' is not a website address like https://example.com")
        origins.append(normalised)
    merged["allowed_origins"] = sorted(set(origins))[:20]
    if merged.get("duplicate_policy") not in ("update_existing", "always_new"):
        raise HTTPException(status_code=422,
                            detail="duplicate_policy must be update_existing or always_new")
    merged["tags"] = sorted({str(t).strip().lower()[:40] for t in merged.get("tags") or []
                             if str(t).strip()})[:20]
    assignment = merged["assignment"]
    if assignment.get("mode") not in ("unassigned", "specific", "round_robin"):
        raise HTTPException(status_code=422,
                            detail="assignment.mode must be unassigned, specific or round_robin")
    assignment["users"] = [str(u).strip().lower() for u in assignment.get("users") or []
                           if str(u).strip()][:25]
    weights = {}
    for user, weight in (assignment.get("weights") or {}).items():
        key = str(user).strip().lower()
        if key not in assignment["users"]:
            continue
        try:
            weight = int(weight)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Round-robin weights must be whole numbers")
        if not 1 <= weight <= 10:
            raise HTTPException(status_code=422, detail="Round-robin weights must be between 1 and 10")
        weights[key] = weight
    assignment["weights"] = weights
    if assignment["mode"] != "unassigned" and not assignment["users"]:
        raise HTTPException(status_code=422, detail="Choose at least one agent to assign leads to")
    opportunity = merged["opportunity"]
    if opportunity.get("value_mode") not in ("fixed", "commission"):
        raise HTTPException(status_code=422,
                            detail="opportunity.value_mode must be fixed or commission")
    for numeric, upper in (("fixed_value", 1e9), ("commission_rate", 100)):
        number = parse_amount(opportunity.get(numeric))
        if number is None or number > upper:
            raise HTTPException(status_code=422, detail=f"opportunity.{numeric} is out of range")
        opportunity[numeric] = number
    opportunity["currency"] = (str(opportunity.get("currency") or "USD").upper()[:3])
    stl = merged["speed_to_lead"]
    for numeric, low, high in (("due_minutes", 1, 1440), ("escalate_after_minutes", 1, 10080)):
        try:
            stl[numeric] = int(stl.get(numeric))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail=f"speed_to_lead.{numeric} must be a number")
        if not low <= stl[numeric] <= high:
            raise HTTPException(status_code=422,
                                detail=f"speed_to_lead.{numeric} must be between {low} and {high}")
    reply = merged["auto_reply"]
    reply["subject"] = _clip(reply.get("subject"), 200) or DEFAULT_AUTO_REPLY_SUBJECT
    reply["body"] = _clip(reply.get("body"), 5000) or DEFAULT_AUTO_REPLY_BODY
    reply["enabled"] = bool(reply.get("enabled"))
    color = str(merged["theme"].get("primary_color") or "#1a9fbf")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise HTTPException(status_code=422, detail="theme.primary_color must be a hex colour like #1a9fbf")
    merged["theme"]["primary_color"] = color
    if merged["theme"].get("layout") not in ("stacked", "two_column"):
        merged["theme"]["layout"] = "stacked"
    merged["remember_visitor"] = bool(merged.get("remember_visitor"))
    captcha = merged["captcha"]
    if captcha.get("provider") not in ("none", "turnstile"):
        raise HTTPException(status_code=422, detail="captcha.provider must be none or turnstile")
    site_key = _clip(captcha.get("site_key"), 200)
    if site_key and not re.fullmatch(r"[A-Za-z0-9_\-]{8,200}", site_key):
        raise HTTPException(status_code=422, detail="captcha.site_key does not look like a site key")
    captcha["site_key"] = site_key
    captcha["secret_configured"] = bool(captcha.get("secret_configured"))
    return merged


def with_defaults(form: dict) -> dict:
    """A form saved before a setting existed reads as if it had the default."""
    form_type = str(form.get("form_type") or "")
    defaults = _default_settings(form_type if form_type in PRESETS else "contact")
    settings = form.get("settings") or {}
    merged = {**defaults, **settings}
    for key, value in defaults.items():
        if isinstance(value, dict):
            merged[key] = {**value, **(settings.get(key) or {})}
    return {**form, "settings": merged}


def captcha_active(form: dict) -> bool:
    captcha = form["settings"].get("captcha") or {}
    return (captcha.get("provider") == "turnstile" and bool(captcha.get("site_key"))
            and bool(form.get("captcha_secret_enc")))


def public_config(form: dict) -> dict:
    """What a website may know about a form: how to draw it. Nothing about the tenant."""
    settings = form["settings"]
    fields = [_field_definition(f) for f in form["fields"]]
    for field in fields:
        if field["key"] == "consent_sms":
            field["label"] = settings["consent"]["sms_text"]
        elif field["key"] == "consent_email":
            field["label"] = settings["consent"]["email_text"]
    return {"key": form["public_key"], "name": form["name"], "fields": fields,
            "submit_text": settings["submit_text"],
            "success_message": settings["success_message"],
            "redirect_url": settings.get("redirect_url"),
            "theme": settings["theme"],
            "remember_visitor": bool(settings.get("remember_visitor")),
            "steps": max([f["step"] for f in fields] or [1]),
            "captcha": ({"provider": "turnstile", "site_key": settings["captcha"]["site_key"]}
                        if captcha_active(form) else None)}


# -------------------------------------------------------------- CORS for websites

class PublicFormCORSMiddleware:
    """Answer cross-origin requests on the public form paths, and only there.

    Added outside the application's own CORSMiddleware so it sees a website's preflight
    before that middleware refuses it. It never sets `Access-Control-Allow-Credentials`:
    a browser therefore never attaches the CRM session cookie to these requests, and the
    responses carry nothing a session would unlock anyway. Which websites a form accepts
    is enforced per form by the endpoint, where the form's own allowlist is known.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith(PUBLIC_PATH_PREFIXES):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers") or []}
        origin = headers.get("origin")
        if scope.get("method") == "OPTIONS" and "access-control-request-method" in headers:
            response_headers = [
                (b"access-control-allow-origin", (origin or "*").encode("latin-1")),
                (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
                (b"access-control-allow-headers", b"content-type, accept, x-requested-with"),
                (b"access-control-max-age", b"600"),
                (b"vary", b"Origin"),
                (b"content-length", b"0"),
            ]
            await send({"type": "http.response.start", "status": 204,
                        "headers": response_headers})
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_with_cors(message):
            if message["type"] == "http.response.start" and origin:
                existing = {k.lower() for k, _ in message.get("headers") or []}
                extra = []
                if b"access-control-allow-origin" not in existing:
                    extra.append((b"access-control-allow-origin", origin.encode("latin-1")))
                    extra.append((b"vary", b"Origin"))
                message = {**message, "headers": list(message.get("headers") or []) + extra}
            await send(message)

        await self.app(scope, receive, send_with_cors)


# ------------------------------------------------------------------ the pipeline

class LeadPipeline:
    """Everything that happens to a lead between the website and the agent's phone."""

    def __init__(self, db, *, new_id: Callable[[str], str], now_iso: Callable[[], str],
                 record_event: Callable[..., Awaitable[dict]],
                 spawn: Callable[[Any], Any],
                 send_email: Optional[Callable[..., Awaitable[Any]]] = None,
                 email_configured: Optional[Callable[[], bool]] = None,
                 get_prefs: Optional[Callable[..., Awaitable[dict]]] = None,
                 public_base_url: str = "",
                 provider_registry: Optional[conversation_service.ProviderRegistry] = None,
                 encrypt: Optional[Callable[[dict], str]] = None,
                 decrypt: Optional[Callable[[str], dict]] = None):
        self.db = db
        self.encrypt = encrypt
        self.decrypt = decrypt
        self.new_id = new_id
        self.now_iso = now_iso
        self.record_event = record_event
        self.spawn = spawn
        self.send_email = send_email
        self.email_configured = email_configured or (lambda: False)
        self.get_prefs = get_prefs
        self.public_base_url = (public_base_url or "").rstrip("/")
        self.registry = provider_registry
        self._watcher: Optional[asyncio.Task] = None

    # ----------------------------------------------------------------- indexes

    async def ensure_indexes(self) -> None:
        db = self.db
        await db[FORMS].create_index("public_key", unique=True)
        await db[FORMS].create_index("server_key_hash", unique=True,
                                     partialFilterExpression={"server_key_hash": {"$type": "string"}})
        await db[FORMS].create_index([("tenant_id", 1), ("status", 1)])
        await db[ATTEMPTS].create_index("at", expireAfterSeconds=86400)
        await db[ATTEMPTS].create_index([("form_id", 1), ("visitor", 1), ("at", -1)])
        await db[detectors.WEB_ENQUIRIES].create_index(
            [("tenant_id", 1), ("form_id", 1), ("fingerprint", 1), ("received_at", -1)])
        await db[detectors.WEB_ENQUIRIES].create_index(
            [("status", 1), ("sla.escalated_at", 1), ("sla.escalate_at", 1)])
        await db.contacts.create_index([("tenant_id", 1), ("phone_digits", 1)])

    # ------------------------------------------------------------ form loading

    async def form_by_key(self, public_key: str) -> Optional[dict]:
        form = await self.db[FORMS].find_one(
            {"public_key": public_key, "status": "active"}, {"_id": 0})
        return with_defaults(form) if form else None

    @staticmethod
    def legacy_form(token: dict) -> dict:
        """A pre-existing intake token behaves as a contact form with default automation."""
        settings = _default_settings("contact")
        settings["allowed_origins"] = token.get("allowed_origins") or []
        settings["opportunity"]["enabled"] = False
        settings["tags"] = ["website-lead"]
        return {"id": token["id"], "tenant_id": token["tenant_id"],
                "name": token.get("label") or "Website", "form_type": "contact",
                "fields": [], "settings": settings, "legacy": True,
                "created_by": token.get("created_by")}

    # ------------------------------------------------------------- the request

    @staticmethod
    def server_key_matches(form: dict, header: Optional[str]) -> Optional[bool]:
        """None when no server key was presented; True/False when one was."""
        if not header:
            return None
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return False
        stored = str(form.get("server_key_hash") or "")
        return bool(stored) and secrets.compare_digest(stored, _sha(token.strip()))

    async def handle_public_submission(self, request: Request, form: dict) -> Response:
        """Parse, police and process one public submission, answering in kind.

        A request carrying the form's server key is a website's own server forwarding a
        lead it already validated and stored. It is trusted for exactly that: no browser
        checks (origin, CAPTCHA, per-visitor limit -- every lead arrives from the same
        server address), and the visual form's required fields do not apply, because
        refusing a real lead over a display setting would lose it. It still needs an
        email or phone, still passes the per-form limit, and is still idempotent.
        """
        trusted = self.server_key_matches(form, request.headers.get("authorization"))
        if trusted is False:
            return JSONResponse(status_code=401, content={"detail": "Invalid server key"})
        if trusted:
            return await self._handle_server_submission(request, form)
        data, wants_html = await read_submission(request)
        settings = form["settings"]

        origin = normalise_origin(request.headers.get("origin")) \
            or normalise_origin(request.headers.get("referer"))
        allowed = set(settings.get("allowed_origins") or [])
        own = normalise_origin(self.public_base_url)
        if allowed and origin and origin not in allowed and origin != own:
            return self._respond(wants_html, 403, {"detail": "This form is not enabled for this website"},
                                 form)

        ip = client_ip(request)
        visitor = _sha(f"{form['tenant_id']}|{ip}")[:32]
        limited = await self._rate_limited(form, visitor)
        if limited:
            response = self._respond(wants_html, 429,
                                     {"detail": "Too many submissions. Please try again shortly."},
                                     form)
            response.headers["Retry-After"] = str(limited)
            return response

        if not await self._captcha_passed(form, data.get("cf-turnstile-response"), ip):
            return self._respond(wants_html, 422,
                                 {"detail": "Please complete the verification and try again.",
                                  "errors": {"captcha": "Please complete the verification"}},
                                 form)
        meta = {"ip": ip, "visitor": visitor,
                "user_agent": (request.headers.get("user-agent") or "")[:400],
                "origin": origin, "channel": "public_form"}
        try:
            result = await self.submit(form, data, meta)
        except SubmissionInvalid as exc:
            return self._respond(wants_html, 422,
                                 {"detail": "Please check the highlighted fields.",
                                  "errors": exc.errors}, form)
        body = {"accepted": True, "id": result["id"],
                "message": settings.get("success_message")}
        if settings.get("redirect_url"):
            body["redirect_url"] = settings["redirect_url"]
        return self._respond(wants_html, 200, body, form)

    async def _handle_server_submission(self, request: Request, form: dict) -> Response:
        data, _ = await read_submission(request)
        limited = await self._rate_limited(form, "server", per_visitor=False)
        if limited:
            return JSONResponse(status_code=429, headers={"Retry-After": str(limited)},
                                content={"detail": "Too many submissions. Retry shortly."})
        relaxed = {**form, "fields": [{**f, "required": False} for f in form["fields"]]}
        ip = _clip(data.get("client_ip"), 64)
        meta = {"ip": ip, "visitor": _sha(f"{form['tenant_id']}|{ip or 'server'}")[:32],
                "user_agent": _clip(data.get("user_agent"), 400),
                "origin": None, "channel": "server"}
        try:
            result = await self.submit(relaxed, data, meta)
        except SubmissionInvalid as exc:
            return JSONResponse(status_code=422, content={
                "detail": "The lead is missing what the CRM needs.", "errors": exc.errors})
        await self.db[FORMS].update_one({"id": form["id"]},
                                        {"$set": {"server_key_last_used_at": _iso()}})
        return JSONResponse({"accepted": True, "id": result["id"],
                             "outcome": result.get("outcome"),
                             "contact_id": result.get("contact_id")})

    def _respond(self, wants_html: bool, status: int, body: dict, form: dict) -> Response:
        if not wants_html:
            return JSONResponse(status_code=status, content=body)
        redirect = form["settings"].get("redirect_url")
        if status == 200 and redirect:
            return RedirectResponse(redirect, status_code=303)
        if status == 200:
            heading, detail = "Thank you", form["settings"].get("success_message") or ""
        else:
            heading = "We couldn't send that"
            errors = body.get("errors") or {}
            detail = body.get("detail", "") + ("".join(
                f"<li>{html.escape(str(v))}</li>" for v in errors.values()) and
                "<ul>" + "".join(f"<li>{html.escape(str(v))}</li>" for v in errors.values())
                + "</ul>")
        page = (
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(heading)}</title><style>body{{font-family:system-ui,sans-serif;"
            "max-width:560px;margin:12vh auto;padding:0 20px;color:#132038}"
            "a{color:#1a9fbf}</style></head><body>"
            f"<h1>{html.escape(heading)}</h1><div>{detail if status != 200 else html.escape(detail)}</div>"
            "<p><a href='javascript:history.back()'>Go back</a></p></body></html>")
        return HTMLResponse(page, status_code=status)

    async def verify_turnstile(self, secret: str, token: str, ip: Optional[str]) -> bool:
        """Ask Cloudflare whether the visitor passed the challenge. Fails closed."""
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.post(
                    "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                    data={"secret": secret, "response": token, "remoteip": ip or ""})
            return bool(response.status_code == 200 and (response.json() or {}).get("success"))
        except Exception:
            logger.warning("Turnstile verification could not be completed")
            return False

    async def _captcha_passed(self, form: dict, token: Any, ip: Optional[str]) -> bool:
        if not captcha_active(form):
            return True
        if not token or not self.decrypt:
            return False
        try:
            secret = self.decrypt(form["captcha_secret_enc"]).get("secret") or ""
        except Exception:
            logger.exception("Could not read the CAPTCHA secret for form %s", form.get("id"))
            return False
        return await self.verify_turnstile(secret, str(token)[:4096], ip)

    async def _rate_limited(self, form: dict, visitor: str, *, per_visitor: bool = True) -> int:
        """Seconds to wait, or 0. Every attempt counts, including ones later refused."""
        now = _now()
        attempts = self.db[ATTEMPTS]
        if per_visitor:
            count = await attempts.count_documents(
                {"form_id": form["id"], "visitor": visitor,
                 "at": {"$gte": now - timedelta(hours=1)}})
            if count >= RATE_PER_VISITOR_PER_HOUR:
                return 3600
        per_form = await attempts.count_documents(
            {"form_id": form["id"], "at": {"$gte": now - timedelta(minutes=1)}})
        if per_form >= RATE_PER_FORM_PER_MINUTE:
            return 60
        await attempts.insert_one({"form_id": form["id"], "visitor": visitor, "at": now})
        return 0

    # ------------------------------------------------------------- processing

    async def submit(self, form: dict, raw: dict, meta: dict, *, test: bool = False) -> dict:
        """File one submission and run its automation. Returns {id, outcome, ...}."""
        normalised = normalise_submission(raw, form)
        control = normalised["control"]
        fields = normalised["fields"]
        tenant_id = form["tenant_id"]

        # Bots fill every field they find and submit instantly. Answer them exactly as a
        # success would, so the absence of an error tells them nothing.
        elapsed = parse_amount(control.get("_elapsed_ms"))
        if str(control.get("_hp") or "").strip() or (elapsed is not None and elapsed < MIN_FILL_MILLISECONDS):
            if not form.get("legacy"):
                await self.db[FORMS].update_one({"id": form["id"]},
                                                {"$inc": {"stats.spam_blocked": 1}})
            return {"id": self.new_id("enq"), "outcome": "spam_blocked"}

        external_id = _clip(control.get("external_id") or control.get("_sid"), 200)
        fingerprint = _sha("|".join(str(fields.get(k) or "") for k in (
            "email", "phone", "message", "listing_id", "property_address", "preferred_date")
        ) + f"|{form['id']}")
        if fields.get("email") or fields.get("phone"):
            recent = await self.db[detectors.WEB_ENQUIRIES].find_one(
                {"tenant_id": tenant_id, "form_id": form["id"], "fingerprint": fingerprint,
                 "received_at": {"$gte": _iso(_now() - timedelta(minutes=DUPLICATE_WINDOW_MINUTES))}},
                {"_id": 0, "id": 1})
            if recent:
                return {"id": recent["id"], "outcome": "duplicate"}

        received_at = _iso()
        settings = form["settings"]
        consent = None
        if fields.get("consent_sms") or fields.get("consent_email"):
            consent = {"sms": bool(fields.get("consent_sms")),
                       "email": bool(fields.get("consent_email")),
                       "sms_text": settings["consent"]["sms_text"] if fields.get("consent_sms") else None,
                       "email_text": settings["consent"]["email_text"] if fields.get("consent_email") else None,
                       "recorded_at": received_at, "ip": meta.get("ip"),
                       "user_agent": meta.get("user_agent"),
                       "page_url": normalised["attribution"].get("page_url")}
        sla_cfg = settings["speed_to_lead"]
        received = _parse(received_at) or _now()
        doc = {
            "id": self.new_id("enq"), "tenant_id": tenant_id,
            "name": fields.get("name"), "email": fields.get("email"),
            "phone": fields.get("phone"), "message": fields.get("message"),
            "source_page": normalised["attribution"].get("page_url"),
            "estimated_value": None,
            "external_id": external_id, "fingerprint": fingerprint,
            "status": "new", "received_at": received_at,
            "received_via": meta.get("channel", "public_form"),
            "received_by": f"website_form:{form['id']}",
            "form_id": form["id"], "form_name": form["name"],
            "form_type": form.get("form_type"),
            "lead_type": fields.get("lead_type"),
            "property_address": fields.get("property_address"),
            "listing_id": fields.get("listing_id"),
            "fields": fields, "extra": normalised["extra"],
            "attribution": normalised["attribution"], "consent": consent,
            "origin": meta.get("origin"), "visitor": meta.get("visitor"),
            "is_test": bool(test),
            "contact_id": None, "company_id": None, "opportunity_id": None,
            "task_id": None, "assigned_to": None, "conversation_id": None,
            "auto_reply": {"status": "off"},
            "sla": {"due_at": _iso(received + timedelta(minutes=sla_cfg["due_minutes"])),
                    "escalate_at": _iso(received + timedelta(minutes=sla_cfg["escalate_after_minutes"])),
                    "escalated_at": None, "first_response_at": None, "response_minutes": None,
                    "responded_via": None},
            "automation": [], "created_at": received_at,
        }
        try:
            await self.db[detectors.WEB_ENQUIRIES].insert_one(dict(doc))
        except Exception as exc:
            if external_id and _is_duplicate_key(exc):
                existing = await self.db[detectors.WEB_ENQUIRIES].find_one(
                    {"tenant_id": tenant_id, "external_id": external_id}, {"_id": 0, "id": 1})
                if existing:
                    return {"id": existing["id"], "outcome": "duplicate"}
            raise

        if not form.get("legacy"):
            await self.db[FORMS].update_one(
                {"id": form["id"]},
                {"$inc": {"stats.submissions": 1}, "$set": {"stats.last_submission_at": received_at}})
        await self.record_event("web_enquiry.received", "web_enquiry", doc["id"], tenant_id,
                                doc["received_by"],
                                payload={"via": doc["received_via"], "form_id": form["id"]})
        try:
            outcome = await self.automate(form, doc)
        except Exception:
            # The lead is stored and visible whatever happens next; an automation fault
            # must never turn into a lost lead or a failed submission.
            logger.exception("Lead automation failed for %s", doc["id"])
            await self._log(doc, "automation", "failed", "Automation raised an error; the "
                                                         "lead is stored and in the inbox.")
            outcome = {}
        return {"id": doc["id"], "outcome": "accepted", **outcome}

    async def _log(self, enquiry: dict, step: str, result: str, detail: str = "") -> None:
        entry = {"step": step, "result": result, "detail": detail[:500], "at": _iso()}
        await self.db[detectors.WEB_ENQUIRIES].update_one(
            {"id": enquiry["id"], "tenant_id": enquiry["tenant_id"]},
            {"$push": {"automation": entry}})

    async def automate(self, form: dict, enquiry: dict) -> dict:
        settings = form["settings"]
        tenant_id = enquiry["tenant_id"]
        contact, created_contact = await self._upsert_contact(form, enquiry)
        await self._log(enquiry, "contact", "created" if created_contact else "matched",
                        contact["id"])
        assignee = await self._assign(form, contact)
        await self._log(enquiry, "assignment", "assigned" if assignee else "unassigned",
                        assignee or "No agent configured; every admin is alerted.")
        if assignee and contact.get("owner") != assignee:
            await self.db.contacts.update_one({"id": contact["id"], "tenant_id": tenant_id},
                                              {"$set": {"owner": assignee}})
        opportunity = None
        if settings["opportunity"]["enabled"]:
            opportunity, created_deal = await self._opportunity(form, enquiry, contact, assignee)
            await self._log(enquiry, "opportunity", "created" if created_deal else "linked",
                            opportunity["id"])
        task = None
        if settings["speed_to_lead"]["task_enabled"]:
            task = await self._task(form, enquiry, contact, assignee)
            await self._log(enquiry, "task", "created", task["id"])

        # The lead's value is the deal's value, which the form's own configuration set.
        # No deal (a newsletter sign-up, say) means no value -- not a guess.
        value = (opportunity or {}).get("value")
        update = {"contact_id": contact["id"], "assigned_to": assignee,
                  "opportunity_id": (opportunity or {}).get("id"),
                  "task_id": (task or {}).get("id"),
                  "created_contact": created_contact,
                  "estimated_value": value or None,
                  "currency": settings["opportunity"]["currency"]}
        await self.db[detectors.WEB_ENQUIRIES].update_one(
            {"id": enquiry["id"], "tenant_id": tenant_id}, {"$set": update})
        enquiry = {**enquiry, **update}

        await self._notify_new_lead(form, enquiry, contact, assignee)
        await self.record_event("lead.received", "web_enquiry", enquiry["id"], tenant_id,
                                SYSTEM_ACTOR, payload=self.lead_payload(enquiry))
        if settings["auto_reply"]["enabled"] and enquiry.get("email") and not enquiry.get("is_test"):
            self.spawn(self._auto_reply_safely(form, enquiry, contact, assignee))
        elif settings["auto_reply"]["enabled"] and not enquiry.get("email"):
            await self._set_auto_reply(enquiry, "skipped", "The lead left no email address.")
        return {"contact_id": contact["id"], "opportunity_id": update["opportunity_id"],
                "task_id": update["task_id"], "assigned_to": assignee}

    @staticmethod
    def lead_payload(enquiry: dict) -> dict:
        """The lead as an outside tool (Zapier, an SMS service, Slack) needs it."""
        keys = ("name", "email", "phone", "message", "form_id", "form_name", "form_type",
                "lead_type", "property_address", "listing_id", "contact_id", "opportunity_id",
                "task_id", "assigned_to", "estimated_value", "currency", "received_at",
                "source_page")
        payload = {k: enquiry.get(k) for k in keys}
        payload["fields"] = enquiry.get("fields") or {}
        payload["attribution"] = enquiry.get("attribution") or {}
        payload["consent"] = {k: v for k, v in (enquiry.get("consent") or {}).items()
                              if k in ("sms", "email", "sms_text", "email_text", "recorded_at")}
        payload["sla_due_at"] = (enquiry.get("sla") or {}).get("due_at")
        payload["is_test"] = bool(enquiry.get("is_test"))
        return payload

    # ------------------------------------------------------------- contacts

    async def _find_contact(self, tenant_id: str, email: Optional[str],
                            phone: Optional[str]) -> Optional[dict]:
        base = {"tenant_id": tenant_id, "archived_at": None}
        if email:
            found = await self.db.contacts.find_one(
                {**base, "email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}},
                {"_id": 0})
            if found:
                return found
        digits = phone_digits(phone)
        if len(digits) >= 7:
            found = await self.db.contacts.find_one({**base, "phone_digits": digits}, {"_id": 0})
            if found:
                return found
            # Contacts created by hand carry the number as typed.
            pattern = r"\D*".join(re.escape(d) for d in digits) + r"\D*$"
            found = await self.db.contacts.find_one(
                {**base, "phone": {"$regex": pattern}}, {"_id": 0})
            if found:
                return found
        return None

    async def _upsert_contact(self, form: dict, enquiry: dict) -> tuple[dict, bool]:
        settings = form["settings"]
        tenant_id = enquiry["tenant_id"]
        fields = enquiry.get("fields") or {}
        tags = list(settings.get("tags") or [])
        if enquiry.get("is_test"):
            tags.append("test-lead")
        source = {"kind": "website_form", "form_id": form["id"], "form_name": form["name"],
                  "enquiry_id": enquiry["id"], "page_url": enquiry.get("source_page"),
                  "at": enquiry["received_at"]}
        custom = {k: v for k, v in fields.items()
                  if k not in ("first_name", "last_name", "name", "email", "phone", "message",
                               "consent_sms", "consent_email")}
        existing = None
        if settings.get("duplicate_policy", "update_existing") == "update_existing":
            existing = await self._find_contact(tenant_id, enquiry.get("email"),
                                                enquiry.get("phone"))
        if existing:
            sets: dict[str, Any] = {"updated_at": self.now_iso(),
                                    "last_inquiry_at": enquiry["received_at"],
                                    "last_attribution": enquiry.get("attribution") or {}}
            for key in ("phone", "email", "name"):
                if not existing.get(key) and enquiry.get(key):
                    sets[key] = enquiry[key]
            if enquiry.get("phone") and not existing.get("phone_digits"):
                sets["phone_digits"] = phone_digits(enquiry["phone"])
            for key, value in custom.items():
                sets[f"custom_fields.{key}"] = value
            if enquiry.get("consent"):
                sets["consent"] = enquiry["consent"]
            await self.db.contacts.update_one(
                {"id": existing["id"], "tenant_id": tenant_id},
                {"$set": sets, "$addToSet": {"tags": {"$each": tags}},
                 "$push": {"inquiries": {"$each": [source], "$slice": -50},
                           "history": crm_core._history_entry(
                               "website_inquiry", SYSTEM_ACTOR,
                               {"form": form["name"], "enquiry_id": enquiry["id"]})}})
            return {**existing, **{k: v for k, v in sets.items() if "." not in k}}, False

        now = self.now_iso()
        doc = {
            "id": self.new_id("ct"), "tenant_id": tenant_id, "created_at": now,
            "updated_at": now, "archived_at": None, "owner": None,
            "name": enquiry.get("name") or enquiry.get("email") or enquiry.get("phone")
            or "Website lead",
            "email": enquiry.get("email"), "phone": enquiry.get("phone"),
            "phone_digits": phone_digits(enquiry.get("phone")) or None,
            "title": None, "role": None, "company_id": None,
            "influence": "medium", "sentiment": "neutral",
            "tags": sorted(set(tags)), "lead_source": "website", "source": source,
            "first_attribution": enquiry.get("attribution") or {},
            "last_attribution": enquiry.get("attribution") or {},
            "custom_fields": custom, "consent": enquiry.get("consent"),
            "inquiries": [source], "last_inquiry_at": enquiry["received_at"],
            "history": [crm_core.created_history(f"website_form:{form['id']}")],
        }
        await self.db.contacts.insert_one(dict(doc))
        await self.record_event("contact.created", "contact", doc["id"], tenant_id,
                                SYSTEM_ACTOR, payload={"name": doc["name"], "source": "website_form",
                                                       "form_id": form["id"]})
        return doc, True

    # ----------------------------------------------------------- assignment

    async def _active_members(self, tenant_id: str) -> dict[str, dict]:
        rows = await self.db.memberships.find(
            {"tenant_id": tenant_id, "status": "active"}, {"_id": 0}).to_list(500)
        return {str(r.get("email") or "").lower(): r for r in rows if r.get("email")}

    async def _assign(self, form: dict, contact: dict) -> Optional[str]:
        settings = form["settings"]["assignment"]
        members = await self._active_members(form["tenant_id"])
        owner = str(contact.get("owner") or "").lower()
        if settings.get("keep_existing_owner", True) and owner in members:
            return owner
        candidates = [u for u in settings.get("users") or [] if u in members]
        if settings.get("mode") == "specific" and candidates:
            return candidates[0]
        if settings.get("mode") == "round_robin" and candidates and not form.get("legacy"):
            updated = await self.db[FORMS].find_one_and_update(
                {"id": form["id"]}, {"$inc": {"stats.round_robin_cursor": 1}},
                projection={"_id": 0, "stats": 1}, return_document=True)
            cursor = int(((updated or {}).get("stats") or {}).get("round_robin_cursor") or 1)
            # Weighted: an agent with weight 2 takes two turns in each cycle.
            weights = settings.get("weights") or {}
            rotation = [u for u in candidates for _ in range(int(weights.get(u) or 1))]
            return rotation[(cursor - 1) % len(rotation)]
        return None

    # ---------------------------------------------------------- opportunity

    async def _opportunity(self, form: dict, enquiry: dict, contact: dict,
                           assignee: Optional[str]) -> tuple[dict, bool]:
        tenant_id = enquiry["tenant_id"]
        cfg = form["settings"]["opportunity"]
        stages = await crm_core.resolve_stages(self.db, tenant_id)
        open_keys = [s["key"] for s in stages if not s.get("is_closed")]
        cutoff = _iso(_now() - timedelta(days=OPEN_DEAL_REUSE_DAYS))
        existing = await self.db.opportunities.find_one(
            {"tenant_id": tenant_id, "archived_at": None, "contact_ids": contact["id"],
             "stage": {"$in": open_keys}, "source.form_id": form["id"],
             "created_at": {"$gte": cutoff}}, {"_id": 0})
        if existing:
            await self.db.opportunities.update_one(
                {"id": existing["id"], "tenant_id": tenant_id},
                {"$push": {"history": crm_core._history_entry(
                    "website_inquiry", SYSTEM_ACTOR, {"enquiry_id": enquiry["id"]})},
                 "$set": {"updated_at": self.now_iso()}})
            return existing, False

        stage = cfg.get("stage") if cfg.get("stage") in open_keys else (open_keys[0] if open_keys else "lead")
        value = self.expected_value(cfg, enquiry.get("fields") or {})
        label = PRESETS.get(form.get("form_type") or "", {}).get("label") or form["name"]
        parts = [contact.get("name") or "Website lead", label]
        if enquiry.get("property_address"):
            parts.append(enquiry["property_address"])
        now = self.now_iso()
        doc = {
            "id": self.new_id("opp"), "tenant_id": tenant_id, "name": " · ".join(parts)[:200],
            "company_id": None, "value": value, "stage": stage, "owner": assignee,
            "currency": cfg.get("currency") or "USD", "expected_close_date": None,
            "contact_ids": [contact["id"]], "created_at": now, "updated_at": now,
            "archived_at": None, "lead_source": "website",
            "value_basis": self.value_basis(cfg, enquiry.get("fields") or {}),
            "source": {"kind": "website_form", "form_id": form["id"],
                       "enquiry_id": enquiry["id"]},
            "history": [crm_core.created_history(f"website_form:{form['id']}")],
            "stage_history": [{"from": None, "to": stage, "at": now,
                               "actor": f"website_form:{form['id']}"}],
        }
        if not doc["owner"]:
            doc["owner"] = form.get("created_by")
        await self.db.opportunities.insert_one(dict(doc))
        await self.record_event("opportunity.created", "opportunity", doc["id"], tenant_id,
                                SYSTEM_ACTOR, payload={"name": doc["name"], "value": value,
                                                       "source": "website_form"})
        return doc, True

    @staticmethod
    def _price_basis(fields: dict) -> Optional[float]:
        """The visitor's own price, bounded. A price outside what a home plausibly costs
        is a typo or abuse, and it must not become an expected-commission figure."""
        for key in ("price_max", "estimated_home_value", "price_min"):
            price = fields.get(key)
            if price and MIN_PRICE_BASIS <= float(price) <= MAX_PRICE_BASIS:
                return float(price)
        return None

    @classmethod
    def expected_value(cls, cfg: dict, fields: dict) -> float:
        """Expected commission when a price is known and commission mode is on, else the
        configured flat value. Never a guess dressed as a figure: no price, no commission."""
        if cfg.get("value_mode") == "commission":
            basis = cls._price_basis(fields)
            if basis:
                return round(basis * float(cfg.get("commission_rate") or 0) / 100.0, 2)
        return round(float(cfg.get("fixed_value") or 0), 2)

    @classmethod
    def value_basis(cls, cfg: dict, fields: dict) -> dict:
        basis = cls._price_basis(fields) if cfg.get("value_mode") == "commission" else None
        if basis:
            return {"method": "commission", "price": basis,
                    "commission_rate": cfg.get("commission_rate")}
        return {"method": "fixed", "value": cfg.get("fixed_value") or 0}

    # ------------------------------------------------------------------ task

    async def _task(self, form: dict, enquiry: dict, contact: dict,
                    assignee: Optional[str]) -> dict:
        label = PRESETS.get(form.get("form_type") or "", {}).get("label") or form["name"]
        lines = [f"{k.replace('_', ' ').title()}: {v}" for k, v in (enquiry.get("fields") or {}).items()
                 if k not in ("first_name", "last_name") and v not in (None, "", False)]
        if enquiry.get("source_page"):
            lines.append(f"Page: {enquiry['source_page']}")
        now = self.now_iso()
        doc = {
            "id": self.new_id("task"), "tenant_id": enquiry["tenant_id"],
            "title": f"Call new lead now: {contact.get('name') or 'website lead'} ({label})"[:300],
            "assignee": assignee, "due_date": (enquiry.get("sla") or {}).get("due_at"),
            "status": "todo", "priority": "high", "notes": "\n".join(lines)[:4000],
            "related_type": "contact", "related_id": contact["id"], "workspace_id": None,
            "archived_at": None, "created_at": now, "updated_at": now,
            "created_by": SYSTEM_ACTOR, "completed_at": None,
            "source": {"kind": "website_form", "enquiry_id": enquiry["id"]},
            "history": [crm_core._history_entry("created", SYSTEM_ACTOR)],
        }
        await self.db.tasks.insert_one(dict(doc))
        await self.record_event("task.created", "task", doc["id"], enquiry["tenant_id"],
                                SYSTEM_ACTOR, payload={"title": doc["title"], "assignee": assignee,
                                                       "related_type": "contact",
                                                       "related_id": contact["id"]})
        return doc

    # --------------------------------------------------------- notifications

    async def _user_id(self, tenant_id: str, email: Optional[str]) -> Optional[str]:
        if not email:
            return None
        member = await self.db.memberships.find_one(
            {"tenant_id": tenant_id, "email": email, "status": "active"}, {"_id": 0, "user_id": 1})
        return (member or {}).get("user_id")

    async def _admins(self, tenant_id: str) -> list[str]:
        rows = await self.db.memberships.find(
            {"tenant_id": tenant_id, "role": "admin", "status": "active"},
            {"_id": 0, "email": 1}).to_list(50)
        return [r["email"] for r in rows if r.get("email")]

    def _summary_lines(self, enquiry: dict) -> list[tuple[str, str]]:
        rows = [("Name", enquiry.get("name")), ("Email", enquiry.get("email")),
                ("Phone", enquiry.get("phone")), ("Form", enquiry.get("form_name")),
                ("Property", enquiry.get("property_address")),
                ("Listing", enquiry.get("listing_id")), ("Message", enquiry.get("message"))]
        fields = enquiry.get("fields") or {}
        for key in ("lead_type", "timeline", "pre_approved", "price_max", "preferred_date",
                    "preferred_time", "working_with_agent"):
            if fields.get(key) not in (None, ""):
                rows.append((FIELD_CATALOG[key]["label"], fields[key]))
        source = (enquiry.get("attribution") or {}).get("utm_source")
        if source:
            rows.append(("Source", source))
        return [(k, str(v)) for k, v in rows if v not in (None, "")]

    async def _notify(self, tenant_id: str, *, recipients: list[str], title: str, body: str,
                      deep_link: str, severity: str, ntype: str, dedupe_key: str,
                      email_subject: str, email_html: str) -> None:
        """In-app to each recipient (or the whole team when there is none), then email."""
        if await self.db.notification_deliveries.find_one(
                {"tenant_id": tenant_id, "dedupe_key": dedupe_key}, {"_id": 1}):
            return
        targets: list[Optional[str]] = list(recipients) or [None]
        for recipient in targets:
            await self.db.notifications.insert_one({
                "id": self.new_id("ntf"), "tenant_id": tenant_id,
                "user_id": await self._user_id(tenant_id, recipient), "recipient": recipient,
                "workspace_id": None, "type": ntype, "severity": severity,
                "category": "leads", "source": "website_form", "title": title[:300],
                "body": body[:2000], "deep_link": deep_link, "read": False,
                "created_at": self.now_iso()})
        delivery = {"id": self.new_id("ndl"), "tenant_id": tenant_id, "channel": "email",
                    "notification_type": ntype, "dedupe_key": dedupe_key,
                    "status": "skipped", "recipient": None, "attempted_at": self.now_iso(),
                    "failure_reason": None}
        email_to = recipients or await self._admins(tenant_id)
        if not self.send_email or not self.email_configured():
            delivery.update(status="not_configured", failure_reason="email_not_configured")
        elif email_to:
            delivered, failures = 0, []
            for address in email_to:
                if self.get_prefs:
                    prefs = await self.get_prefs(tenant_id, await self._user_id(tenant_id, address))
                    if not (prefs.get("channels") or {}).get("email", True):
                        continue
                try:
                    await self.send_email(address, email_subject, email_html)
                    delivered += 1
                except Exception as exc:
                    failures.append(str(exc)[:120])
            delivery.update(status="delivered" if delivered and not failures
                            else "partial" if delivered else "failed" if failures else "skipped",
                            recipient=",".join(email_to)[:500],
                            failure_reason="; ".join(failures)[:500] or None)
        await self.db.notification_deliveries.insert_one(delivery)

    def _email_html(self, heading: str, enquiry: dict, footer: str) -> str:
        rows = "".join(
            f"<tr><td style='padding:4px 12px 4px 0;color:#64748b'>{html.escape(k)}</td>"
            f"<td style='padding:4px 0'>{html.escape(v)}</td></tr>"
            for k, v in self._summary_lines(enquiry))
        link = f"{self.public_base_url}/leads?lead={enquiry['id']}" if self.public_base_url else ""
        button = (f"<p><a href='{html.escape(link)}' style='background:#1a9fbf;color:#fff;"
                  "padding:10px 16px;border-radius:8px;text-decoration:none'>Open the lead</a></p>"
                  if link else "")
        return (f"<h2 style='font-family:system-ui'>{html.escape(heading)}</h2>"
                f"<table style='font-family:system-ui;font-size:14px'>{rows}</table>"
                f"{button}<p style='color:#94a3b8;font-size:12px'>{html.escape(footer)}</p>")

    async def _notify_new_lead(self, form: dict, enquiry: dict, contact: dict,
                               assignee: Optional[str]) -> None:
        if not form["settings"]["notify"].get("in_app", True) \
                and not form["settings"]["notify"].get("email", True):
            return
        who = enquiry.get("name") or enquiry.get("email") or enquiry.get("phone") or "a visitor"
        due = form["settings"]["speed_to_lead"]["due_minutes"]
        prefix = "[TEST] " if enquiry.get("is_test") else ""
        title = f"{prefix}New lead: {who} — {form['name']}"
        body = " · ".join(f"{k}: {v}" for k, v in self._summary_lines(enquiry))
        await self._notify(
            enquiry["tenant_id"], recipients=[assignee] if assignee else [],
            title=title, body=body, deep_link=f"/leads?lead={enquiry['id']}",
            severity="warning", ntype="lead.new", dedupe_key=f"lead:{enquiry['id']}:new",
            email_subject=f"{prefix}New lead from your website: {who}",
            email_html=self._email_html(f"New lead — call within {due} minutes", enquiry,
                                        f"Received {enquiry['received_at']} via {form['name']}."))

    # ------------------------------------------------------------ auto-reply

    async def _set_auto_reply(self, enquiry: dict, status: str, detail: str = "",
                              conversation_id: Optional[str] = None) -> None:
        sets: dict[str, Any] = {"auto_reply": {"status": status, "detail": detail[:500],
                                               "at": self.now_iso()}}
        if conversation_id:
            sets["conversation_id"] = conversation_id
        await self.db[detectors.WEB_ENQUIRIES].update_one(
            {"id": enquiry["id"], "tenant_id": enquiry["tenant_id"]}, {"$set": sets})

    async def template_approval_state(self, form: dict) -> dict:
        reply = form["settings"]["auto_reply"]
        sha = template_fingerprint(reply["subject"], reply["body"])
        approval = None
        if reply.get("approval_id"):
            approval = await approval_queue.get(self.db, form["tenant_id"], reply["approval_id"])
        bound = ((approval or {}).get("action") or {}).get("template_sha256")
        if not approval or bound != sha:
            return {"state": "not_requested", "approval": None, "template_sha256": sha}
        status = str(approval.get("status") or "")
        return {"state": {"requested": "awaiting_approval", "approved": "approved",
                          "rejected": "rejected", "expired": "expired",
                          "cancelled": "cancelled"}.get(status, status),
                "approval": approval, "template_sha256": sha}

    async def _auto_reply_safely(self, form: dict, enquiry: dict, contact: dict,
                                 assignee: Optional[str]) -> None:
        try:
            await self.auto_reply(form, enquiry, contact, assignee)
        except Exception as exc:
            logger.exception("Automatic reply failed for %s", enquiry["id"])
            await self._set_auto_reply(enquiry, "failed", str(exc)[:300])

    async def auto_reply(self, form: dict, enquiry: dict, contact: dict,
                         assignee: Optional[str]) -> dict:
        tenant_id = enquiry["tenant_id"]
        state = await self.template_approval_state(form)
        if state["state"] != "approved":
            await self._set_auto_reply(enquiry, "awaiting_template_approval",
                                       "The automatic reply template has not been approved.")
            return {"status": "awaiting_template_approval"}
        template_approval = state["approval"]
        reply = form["settings"]["auto_reply"]
        agent_name = None
        if assignee:
            user = await self.db.users.find_one({"email": assignee}, {"_id": 0, "name": 1})
            agent_name = (user or {}).get("name")
        values = {"first_name": _safe_first_name((enquiry.get("fields") or {}).get("first_name")
                                                 or enquiry.get("name")),
                  "agent_name": (agent_name or "Our team")[:80],
                  "form_name": form["name"][:120]}
        subject = render_template(reply["subject"], values)[:300]
        body = render_template(reply["body"], values)

        conversation = await conversation_service.create_conversation(
            self.db, tenant_id=tenant_id, channel=conversation_service.CHANNEL_EMAIL,
            actor=SYSTEM_ACTOR, subject=subject, contact_id=contact["id"], assignee=assignee,
            participants=[{"kind": conversation_service.PARTICIPANT_CONTACT, "id": contact["id"],
                           "address": enquiry["email"], "display_name": enquiry.get("name")}],
            external_thread_id=f"website-form:{enquiry['id']}")
        await conversation_service.record_consent(
            self.db, tenant_id=tenant_id, conversation_id=conversation["id"],
            state=conversation_service.CONSENT_GRANTED, actor=SYSTEM_ACTOR,
            basis=(f"Reply to an enquiry this person submitted through the website form "
                   f"'{form['name']}' at {enquiry['received_at']}, asking to be contacted."),
            source=f"web_enquiry:{enquiry['id']}")
        message = await conversation_service.draft_message(
            self.db, tenant_id=tenant_id, conversation_id=conversation["id"], body=body,
            actor=SYSTEM_ACTOR, subject=subject, to_address=enquiry["email"],
            idempotency_key=f"website-form-auto-reply:{enquiry['id']}",
            requester_kind=approval_queue.REQUESTER_SYSTEM)
        if message.get("deduplicated") and message.get("status") != conversation_service.DRAFT:
            return {"status": "already_handled"}
        pending = await conversation_service.request_approval(
            self.db, tenant_id=tenant_id, message_id=message["id"], actor=SYSTEM_ACTOR,
            risk=approval_queue.RISK_LOW, registry=self.registry)
        await approval_queue.decide(
            self.db, tenant_id=tenant_id, approval_id=pending["approval_id"],
            decision=approval_queue.APPROVED,
            actor=f"standing-approval:{template_approval['id']}",
            rationale=(f"Rendered from the automatic reply template "
                       f"{state['template_sha256'][:16]} approved by "
                       f"{template_approval.get('decided_by')} at "
                       f"{template_approval.get('decided_at')}. Merge values from the lead's "
                       f"own submission and the assigned agent: {json.dumps(values)}"))
        await conversation_service.mark_approved(self.db, tenant_id=tenant_id,
                                                 message_id=message["id"], actor=SYSTEM_ACTOR)
        try:
            sent = await conversation_service.attempt_delivery(
                self.db, tenant_id=tenant_id, message_id=message["id"], actor=SYSTEM_ACTOR,
                registry=self.registry)
        except conversation_service.DeliveryRefused as exc:
            await self._set_auto_reply(enquiry, "blocked", f"{exc}", conversation["id"])
            return {"status": "blocked", "detail": str(exc)}
        status = "sent" if sent.get("status") == conversation_service.SENT \
            else str(sent.get("status") or "unknown")
        await self._set_auto_reply(enquiry, status, sent.get("error") or "", conversation["id"])
        return {"status": status}

    # ------------------------------------------------- response clock & SLA

    async def mark_responded(self, enquiry: dict, *, via: str, at: Optional[str] = None,
                             actor: str = SYSTEM_ACTOR) -> bool:
        at = at or self.now_iso()
        received = _parse(enquiry.get("received_at")) or _now()
        responded = _parse(at) or _now()
        minutes = max(0, int((responded - received).total_seconds() // 60))
        result = await self.db[detectors.WEB_ENQUIRIES].update_one(
            {"id": enquiry["id"], "tenant_id": enquiry["tenant_id"], "status": "new"},
            {"$set": {"status": "responded", "sla.first_response_at": at,
                      "sla.response_minutes": minutes, "sla.responded_via": via,
                      "responded_by": actor}})
        if not result.modified_count:
            return False
        if enquiry.get("task_id") and via != "task_completed":
            await self.db.tasks.update_one(
                {"id": enquiry["task_id"], "tenant_id": enquiry["tenant_id"],
                 "status": {"$nin": ["done", "cancelled"]}},
                {"$set": {"status": "done", "completed_at": at, "updated_at": at},
                 "$push": {"history": crm_core._history_entry("completed", actor,
                                                              {"via": "lead_responded"})}})
        await self.record_event("lead.responded", "web_enquiry", enquiry["id"],
                                enquiry["tenant_id"], actor,
                                payload={"via": via, "response_minutes": minutes})
        return True

    async def sync_responses(self, tenant_id: Optional[str] = None) -> int:
        """Recognise responses that happened elsewhere in the CRM."""
        query: dict[str, Any] = {"status": "new"}
        if tenant_id:
            query["tenant_id"] = tenant_id
        open_leads = await self.db[detectors.WEB_ENQUIRIES].find(
            query, {"_id": 0}).to_list(2000)
        count = 0
        for lead in open_leads:
            if lead.get("task_id"):
                task = await self.db.tasks.find_one(
                    {"id": lead["task_id"], "tenant_id": lead["tenant_id"]},
                    {"_id": 0, "status": 1, "completed_at": 1})
                if task and task.get("status") == "done":
                    count += await self.mark_responded(lead, via="task_completed",
                                                       at=task.get("completed_at"))
                    continue
            if lead.get("contact_id"):
                activity = await self.db.crm_activities.find_one(
                    {"tenant_id": lead["tenant_id"], "related_type": "contact",
                     "related_id": lead["contact_id"],
                     "type": {"$in": ["call", "email", "meeting"]},
                     "occurred_at": {"$gte": lead["received_at"]}},
                    {"_id": 0, "occurred_at": 1, "type": 1}, sort=[("occurred_at", 1)])
                if activity:
                    count += await self.mark_responded(
                        lead, via=f"activity_{activity['type']}", at=activity["occurred_at"])
        return count

    async def escalate_overdue(self, tenant_id: Optional[str] = None) -> int:
        now = self.now_iso()
        query: dict[str, Any] = {"status": "new", "sla.escalated_at": None,
                                 "sla.escalate_at": {"$lte": now}, "is_test": {"$ne": True}}
        if tenant_id:
            query["tenant_id"] = tenant_id
        overdue = await self.db[detectors.WEB_ENQUIRIES].find(query, {"_id": 0}).to_list(500)
        count = 0
        for lead in overdue:
            claimed = await self.db[detectors.WEB_ENQUIRIES].update_one(
                {"id": lead["id"], "tenant_id": lead["tenant_id"], "status": "new",
                 "sla.escalated_at": None},
                {"$set": {"sla.escalated_at": now}})
            if not claimed.modified_count:
                continue  # another worker got it first
            count += 1
            waited = int(((_parse(now) or _now()) - (_parse(lead["received_at"]) or _now()))
                         .total_seconds() // 60)
            who = lead.get("name") or lead.get("email") or lead.get("phone") or "a visitor"
            recipients = sorted(set(await self._admins(lead["tenant_id"])
                                    + ([lead["assigned_to"]] if lead.get("assigned_to") else [])))
            await self._notify(
                lead["tenant_id"], recipients=recipients,
                title=f"Lead waiting {waited} min with no response: {who}",
                body=(f"{who} came in through {lead.get('form_name')} and nobody has responded. "
                      f"Assigned to {lead.get('assigned_to') or 'nobody'}."),
                deep_link=f"/leads?lead={lead['id']}", severity="critical",
                ntype="lead.sla_breached", dedupe_key=f"lead:{lead['id']}:escalated",
                email_subject=f"Uncontacted lead: {who} has waited {waited} minutes",
                email_html=self._email_html(f"No response after {waited} minutes", lead,
                                            "Escalated because the speed-to-lead window passed."))
            await self.record_event("lead.sla_breached", "web_enquiry", lead["id"],
                                    lead["tenant_id"], SYSTEM_ACTOR,
                                    payload={**self.lead_payload(lead), "waited_minutes": waited})
        return count

    async def sweep(self, tenant_id: Optional[str] = None) -> dict:
        responded = await self.sync_responses(tenant_id)
        escalated = await self.escalate_overdue(tenant_id)
        return {"responded": responded, "escalated": escalated}

    async def run_watcher(self, interval: int = WATCH_INTERVAL_SECONDS) -> None:
        """The speed-to-lead clock. Runs inside the API so a lead never waits on the
        external scheduler; every step is a conditional update, so a second replica or
        the cron endpoint running the same sweep cannot double-notify."""
        while True:
            try:
                await self.sweep()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Lead SLA sweep failed")
            await asyncio.sleep(max(5, interval))

    def start_watcher(self) -> None:
        if os.environ.get("LEAD_SLA_WATCHER", "1") == "0" or self._watcher:
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


# ---------------------------------------------------------------- embed assets

EMBED_JS = r"""/* ClientVerse website forms embed. Usage:
   <div data-clientverse-form="FORM_KEY"></div>
   <script async src="https://YOUR-CRM/api/public/forms/embed.js"></script>
   Options on the div: data-mode="popup" data-layout="slide-in" data-button-text="Contact us"
   data-trigger="delay:10|scroll:50|exit" data-listing-id="MLS123"
   data-property-address="12 Oak St" (prefills hidden listing fields). */
(function () {
  "use strict";
  if (window.__clientverseForms) { window.__clientverseForms.scan(); return; }
  var script = document.currentScript;
  var BASE = (script && script.src ? script.src : "").replace(/\/api\/public\/forms\/embed\.js.*$/, "");
  var STORE = "cvf_attribution";
  var TRACK = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"];

  function attribution() {
    var saved = {};
    try { saved = JSON.parse(window.sessionStorage.getItem(STORE) || "{}"); } catch (e) { saved = {}; }
    var params = new URLSearchParams(window.location.search);
    var fresh = {};
    TRACK.forEach(function (k) { if (params.get(k)) fresh[k] = params.get(k); });
    if (Object.keys(fresh).length || !saved.landing_page) {
      saved = Object.assign({ landing_page: window.location.href, referrer: document.referrer || "" }, saved, fresh);
      try { window.sessionStorage.setItem(STORE, JSON.stringify(saved)); } catch (e) { /* private mode */ }
    }
    return saved;
  }
  function uuid() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return "sid-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
  }
  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") node.textContent = attrs[k];
      else if (attrs[k] !== null && attrs[k] !== undefined && attrs[k] !== false) node.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }
  function css(color) {
    if (document.getElementById("cvf-style")) return;
    var s = el("style", { id: "cvf-style" });
    s.textContent = ".cvf{font-family:inherit;max-width:640px;color:inherit}.cvf *{box-sizing:border-box}" +
      ".cvf-field{margin:0 0 14px}.cvf-label{display:block;font-size:14px;font-weight:600;margin:0 0 6px}" +
      ".cvf-input{width:100%;padding:10px 12px;border:1px solid #cbd5e1;border-radius:8px;font:inherit;background:#fff;color:#0f172a}" +
      ".cvf-input:focus{outline:2px solid var(--cvf-color);outline-offset:1px}" +
      ".cvf-check{display:flex;gap:8px;align-items:flex-start;font-size:13px;line-height:1.4}" +
      ".cvf-err{color:#b91c1c;font-size:13px;margin-top:4px}.cvf-btn{background:var(--cvf-color);color:#fff;border:0;border-radius:8px;padding:12px 18px;font:inherit;font-weight:600;cursor:pointer;width:100%}" +
      ".cvf-btn[disabled]{opacity:.6;cursor:wait}.cvf-done{padding:16px;border-radius:8px;background:#ecfeff;border:1px solid #a5f3fc}" +
      ".cvf-nav{display:flex;gap:10px}.cvf-back{background:none;border:1px solid #cbd5e1;border-radius:8px;padding:12px 18px;font:inherit;cursor:pointer;color:inherit}" +
      ".cvf-progress{font-size:13px;font-weight:600;margin:0 0 12px;opacity:.75}" +
      ".cvf-hp{position:absolute!important;left:-10000px!important;width:1px;height:1px;overflow:hidden}" +
      ".cvf-two{display:grid;grid-template-columns:1fr 1fr;gap:0 14px}@media(max-width:560px){.cvf-two{grid-template-columns:1fr}}" +
      ".cvf-overlay{position:fixed;inset:0;background:rgba(15,23,42,.55);display:flex;align-items:center;justify-content:center;z-index:2147483000;padding:16px}" +
      ".cvf-modal{background:#fff;color:#0f172a;border-radius:14px;padding:22px;max-width:560px;width:100%;max-height:90vh;overflow:auto;position:relative}" +
      ".cvf-overlay.cvf-slide{inset:auto 16px 16px auto;background:none;padding:0;display:block}.cvf-slide .cvf-modal{width:min(420px,calc(100vw - 32px));max-height:80vh;box-shadow:0 20px 50px rgba(15,23,42,.25)}" +
      ".cvf-close{position:absolute;top:8px;right:12px;background:none;border:0;font-size:24px;cursor:pointer;color:#64748b}";
    document.head.appendChild(s);
  }
  function fieldNode(f, prefill) {
    var id = "cvf-" + Math.random().toString(36).slice(2) + "-" + f.key;
    var input;
    if (f.type === "textarea") input = el("textarea", { id: id, name: f.key, rows: "4", "class": "cvf-input", placeholder: f.placeholder, required: f.required ? "required" : null });
    else if (f.type === "select") {
      input = el("select", { id: id, name: f.key, "class": "cvf-input", required: f.required ? "required" : null }, [el("option", { value: "", text: "Select…" })]);
      (f.options || []).forEach(function (o) { input.appendChild(el("option", { value: o, text: o })); });
    } else if (f.type === "checkbox") {
      input = el("input", { id: id, name: f.key, type: "checkbox", value: "yes", required: f.required ? "required" : null });
      return el("div", { "class": "cvf-field", "data-key": f.key }, [el("label", { "class": "cvf-check", "for": id }, [input, el("span", { text: f.label + (f.required ? " *" : "") })]), el("div", { "class": "cvf-err" })]);
    } else {
      var type = { email: "email", tel: "tel", number: "text", date: "date" }[f.type] || "text";
      input = el("input", { id: id, name: f.key, type: type, "class": "cvf-input", placeholder: f.placeholder, autocomplete: f.autocomplete, inputmode: f.type === "number" ? "decimal" : null, required: f.required ? "required" : null });
    }
    if (prefill[f.key]) input.value = prefill[f.key];
    return el("div", { "class": "cvf-field", "data-key": f.key }, [el("label", { "class": "cvf-label", "for": id, text: f.label + (f.required ? " *" : "") }), input, el("div", { "class": "cvf-err" })]);
  }
  var VISITOR = "cvf_visitor";
  var REMEMBERED = ["first_name", "last_name", "name", "email", "phone"];
  function remembered() {
    try { return JSON.parse(window.localStorage.getItem(VISITOR) || "{}"); } catch (e) { return {}; }
  }
  function withTurnstile(callback, tries) {
    if (window.turnstile && window.turnstile.render) { callback(window.turnstile); return; }
    if (!document.getElementById("cvf-turnstile")) {
      document.head.appendChild(el("script", { id: "cvf-turnstile", src: "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit", async: "async" }));
    }
    if ((tries || 0) < 100) setTimeout(function () { withTurnstile(callback, (tries || 0) + 1); }, 100);
  }
  function render(host, cfg) {
    css(cfg.theme && cfg.theme.primary_color);
    var started = Date.now();
    var sid = uuid();
    var ds = host.dataset || {};
    var params = new URLSearchParams(window.location.search);
    var prefill = { listing_id: ds.listingId || params.get("listing_id") || "", property_address: ds.propertyAddress || params.get("property_address") || "" };
    if (cfg.remember_visitor) {
      var known = remembered();
      REMEMBERED.forEach(function (k) { if (known[k] && !prefill[k]) prefill[k] = known[k]; });
    }
    var form = el("form", { "class": "cvf", novalidate: "novalidate" });
    form.style.setProperty("--cvf-color", (cfg.theme && cfg.theme.primary_color) || "#1a9fbf");
    var layout = cfg.theme && cfg.theme.layout === "two_column" ? "cvf-two" : "";
    var steps = Math.max(1, cfg.steps || 1);
    var current = 1;
    var pages = [];
    for (var i = 1; i <= steps; i++) pages.push(el("div", { "class": layout, "data-step": String(i) }));
    var progress = steps > 1 ? el("div", { "class": "cvf-progress", "aria-live": "polite" }) : null;
    if (progress) form.appendChild(progress);
    var keys = {};
    cfg.fields.forEach(function (f) {
      keys[f.key] = true;
      var node = fieldNode(f, prefill);
      if (f.show_if) {
        node.setAttribute("data-show-field", f.show_if.field);
        node.setAttribute("data-show-values", JSON.stringify(f.show_if.values));
      }
      pages[Math.min(steps, Math.max(1, f.step || 1)) - 1].appendChild(node);
    });
    pages.forEach(function (page) { form.appendChild(page); });
    ["listing_id", "property_address"].forEach(function (k) { if (!keys[k] && prefill[k]) form.appendChild(el("input", { type: "hidden", name: k, value: prefill[k] })); });
    form.appendChild(el("div", { "class": "cvf-hp", "aria-hidden": "true" }, [el("label", { text: "Leave this field empty" }, [el("input", { type: "text", name: "_hp", tabindex: "-1", autocomplete: "off" })])]));
    var captcha = null;
    var widget = null;
    if (cfg.captcha && cfg.captcha.provider === "turnstile") {
      var slot = el("div");
      captcha = el("div", { "class": "cvf-field cvf-captcha", "data-key": "captcha" }, [slot, el("div", { "class": "cvf-err" })]);
      form.appendChild(captcha);
      withTurnstile(function (ts) { widget = ts.render(slot, { sitekey: cfg.captcha.site_key }); });
    }
    var status = el("div", { "class": "cvf-err", role: "alert" });
    var back = el("button", { type: "button", "class": "cvf-back", text: "Back" });
    var next = el("button", { type: "button", "class": "cvf-btn", text: "Next" });
    var button = el("button", { type: "submit", "class": "cvf-btn", text: cfg.submit_text || "Submit" });
    form.appendChild(el("div", { "class": "cvf-nav" }, [back, next, button]));
    form.appendChild(status);

    function clearErrors(scope) { Array.prototype.forEach.call((scope || form).querySelectorAll(".cvf-err"), function (n) { n.textContent = ""; }); }
    function applyConditions() {
      Array.prototype.forEach.call(form.querySelectorAll("[data-show-field]"), function (node) {
        var source = form.querySelector('[name="' + node.getAttribute("data-show-field") + '"]');
        var value = "";
        if (source && !source.disabled) value = source.type === "checkbox" ? (source.checked ? "Yes" : "No") : source.value;
        var visible = JSON.parse(node.getAttribute("data-show-values") || "[]").indexOf(value) !== -1;
        node.style.display = visible ? "" : "none";
        Array.prototype.forEach.call(node.querySelectorAll("input,select,textarea"), function (input) { input.disabled = !visible; });
      });
    }
    function showStep(n) {
      current = n;
      pages.forEach(function (page, index) { page.style.display = index + 1 === n ? "" : "none"; });
      if (progress) progress.textContent = "Step " + n + " of " + steps;
      back.style.display = n > 1 ? "" : "none";
      next.style.display = n < steps ? "" : "none";
      button.style.display = n === steps ? "" : "none";
      if (captcha) captcha.style.display = n === steps ? "" : "none";
    }
    function stepValid(n) {
      var ok = true;
      Array.prototype.forEach.call(pages[n - 1].querySelectorAll("input,select,textarea"), function (input) {
        if (input.disabled || input.type === "hidden" || input.checkValidity()) return;
        ok = false;
        var wrap = input.closest("[data-key]");
        var err = wrap && wrap.querySelector(".cvf-err");
        if (err) err.textContent = input.validationMessage || "Please complete this field";
      });
      return ok;
    }
    next.addEventListener("click", function () { clearErrors(pages[current - 1]); if (stepValid(current)) showStep(current + 1); });
    back.addEventListener("click", function () { showStep(current - 1); });
    form.addEventListener("change", applyConditions);
    form.addEventListener("input", applyConditions);
    applyConditions();
    showStep(1);

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      clearErrors();
      var data = {};
      Array.prototype.forEach.call(form.elements, function (n) {
        if (!n.name || n.disabled) return;
        if (n.type === "checkbox") { if (n.checked) data[n.name] = true; }
        else if (n.value) data[n.name] = n.value;
      });
      var a = attribution();
      Object.keys(a).forEach(function (k) { if (a[k]) data[k] = a[k]; });
      data.page_url = window.location.href;
      data._sid = sid;
      data._elapsed_ms = Date.now() - started;
      button.disabled = true;
      fetch(BASE + "/api/public/forms/" + encodeURIComponent(cfg.key) + "/submit", {
        method: "POST", headers: { "Content-Type": "text/plain;charset=UTF-8" }, body: JSON.stringify(data)
      }).then(function (r) { return r.json().then(function (b) { return { ok: r.ok, status: r.status, body: b }; }); })
        .then(function (res) {
          button.disabled = false;
          if (res.ok) {
            try { window.localStorage.setItem("cvf_done_" + cfg.key, "1"); } catch (e) { /* private mode */ }
            if (cfg.remember_visitor) {
              var keep = {};
              REMEMBERED.forEach(function (k) { if (data[k]) keep[k] = data[k]; });
              try { window.localStorage.setItem(VISITOR, JSON.stringify(keep)); } catch (e) { /* private mode */ }
            }
            try { window.dispatchEvent(new CustomEvent("clientverse:lead", { detail: { form: cfg.key, id: res.body.id } })); } catch (e) { /* old browser */ }
            if (res.body.redirect_url) { (window.top || window).location.href = res.body.redirect_url; return; }
            form.replaceWith(el("div", { "class": "cvf cvf-done", role: "status", text: res.body.message || cfg.success_message }));
            return;
          }
          if (widget !== null && window.turnstile) { try { window.turnstile.reset(widget); } catch (e) { /* ignore */ } }
          var errors = res.body.errors || {};
          var firstStep = null;
          Object.keys(errors).forEach(function (k) {
            var holder = form.querySelector('[data-key="' + k + '"]');
            var wrap = holder && holder.querySelector(".cvf-err");
            if (wrap) wrap.textContent = errors[k]; else status.textContent = errors[k];
            var page = holder && holder.closest("[data-step]");
            if (page) { var n = parseInt(page.getAttribute("data-step"), 10); if (firstStep === null || n < firstStep) firstStep = n; }
          });
          if (firstStep !== null && firstStep !== current) showStep(firstStep);
          if (!Object.keys(errors).length) status.textContent = res.body.detail || "Something went wrong. Please try again.";
        })
        .catch(function () { button.disabled = false; status.textContent = "We couldn't send that. Please check your connection and try again."; });
    });
    return form;
  }
  function popup(host, cfg) {
    var ds = host.dataset || {};
    var opened = false;
    function open() {
      if (opened) return; opened = true;
      var close = el("button", { "class": "cvf-close", type: "button", "aria-label": "Close", text: "\u00d7" });
      var slide = (ds.layout || "") === "slide-in";
      var modal = el("div", { "class": "cvf-modal", role: "dialog", "aria-modal": slide ? "false" : "true", "aria-label": cfg.name }, [close, render(host, cfg)]);
      var overlay = el("div", { "class": slide ? "cvf-overlay cvf-slide" : "cvf-overlay" }, [modal]);
      function shut() { overlay.remove(); opened = false; }
      close.addEventListener("click", shut);
      overlay.addEventListener("click", function (e) { if (e.target === overlay) shut(); });
      document.addEventListener("keydown", function esc(e) { if (e.key === "Escape") { shut(); document.removeEventListener("keydown", esc); } });
      document.body.appendChild(overlay);
    }
    css(cfg.theme && cfg.theme.primary_color);
    var trigger = ds.trigger || "click";
    if (trigger === "click" || ds.buttonText) {
      var b = el("button", { type: "button", "class": "cvf-btn", text: ds.buttonText || cfg.submit_text || "Contact us" });
      b.style.setProperty("--cvf-color", (cfg.theme && cfg.theme.primary_color) || "#1a9fbf");
      b.addEventListener("click", open); host.appendChild(b);
    }
    var once = "cvf_popup_" + cfg.key;
    var seen = false;
    try {
      // Never interrupt someone who already submitted this form, on any visit.
      seen = !!window.sessionStorage.getItem(once) || !!window.localStorage.getItem("cvf_done_" + cfg.key);
    } catch (e) { seen = false; }
    function auto() { if (seen) return; seen = true; try { window.sessionStorage.setItem(once, "1"); } catch (e) { /* ignore */ } open(); }
    if (trigger.indexOf("delay:") === 0) setTimeout(auto, (parseInt(trigger.slice(6), 10) || 10) * 1000);
    if (trigger.indexOf("scroll:") === 0) {
      var pct = parseInt(trigger.slice(7), 10) || 50;
      window.addEventListener("scroll", function onScroll() {
        var h = document.documentElement; if ((h.scrollTop + window.innerHeight) / h.scrollHeight * 100 >= pct) { window.removeEventListener("scroll", onScroll); auto(); }
      });
    }
    if (trigger === "exit") document.addEventListener("mouseout", function onOut(e) { if (!e.relatedTarget && e.clientY <= 0) { document.removeEventListener("mouseout", onOut); auto(); } });
  }
  function mount(host) {
    if (host.getAttribute("data-cvf-mounted")) return;
    host.setAttribute("data-cvf-mounted", "1");
    var key = host.getAttribute("data-clientverse-form");
    attribution();
    fetch(BASE + "/api/public/forms/" + encodeURIComponent(key) + "/config")
      .then(function (r) { if (!r.ok) throw new Error("form unavailable"); return r.json(); })
      .then(function (cfg) {
        if ((host.getAttribute("data-mode") || "inline") === "popup") popup(host, cfg);
        else host.appendChild(render(host, cfg));
      })
      .catch(function () { host.textContent = "This form is temporarily unavailable."; });
  }
  function scan() { Array.prototype.forEach.call(document.querySelectorAll("[data-clientverse-form]"), mount); }
  window.__clientverseForms = { scan: scan };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", scan); else scan();
})();
"""


def hosted_page(form: dict) -> str:
    title = html.escape(form["name"])
    key = html.escape(form["public_key"])
    color = html.escape(form["settings"]["theme"]["primary_color"])
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title><style>body{{margin:0;font-family:system-ui,-apple-system,"
        "'Segoe UI',sans-serif;background:#f8fafc;color:#0f172a}"
        ".wrap{max-width:640px;margin:0 auto;padding:32px 20px}"
        f"h1{{font-size:24px;margin:0 0 18px;color:{color}}}"
        "body.embedded{background:transparent}body.embedded h1{display:none}"
        "body.embedded .wrap{padding:8px}</style></head><body>"
        "<script>if(window.self!==window.top)document.body.className='embedded';</script>"
        f"<div class='wrap'><h1>{title}</h1><div data-clientverse-form='{key}'></div></div>"
        "<script src='/api/public/forms/embed.js'></script></body></html>")


HOSTED_PAGE_CSP = "; ".join([
    "default-src 'self'",
    # Cloudflare Turnstile, for forms that turn the CAPTCHA on.
    "script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com",
    "frame-src https://challenges.cloudflare.com",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:", "connect-src 'self'", "frame-ancestors *", "base-uri 'self'",
    "form-action 'self'",
])


def embed_snippets(form: dict, base_url: str) -> dict:
    base = base_url.rstrip("/")
    key = form["public_key"]
    fields = [_field_definition(f) for f in form["fields"]]
    html_inputs = []
    for f in fields:
        req = " required" if f["required"] else ""
        label = html.escape(f["label"])
        if f["type"] == "textarea":
            control = f'<textarea name="{f["key"]}"{req}></textarea>'
        elif f["type"] == "select":
            opts = "".join(f'<option>{html.escape(o)}</option>' for o in f["options"] or [])
            control = f'<select name="{f["key"]}"{req}><option value="">Select…</option>{opts}</select>'
        elif f["type"] == "checkbox":
            control = f'<input type="checkbox" name="{f["key"]}" value="yes"{req}>'
        else:
            kind = {"email": "email", "tel": "tel", "date": "date"}.get(f["type"], "text")
            control = f'<input type="{kind}" name="{f["key"]}"{req}>'
        html_inputs.append(f'  <label>{label}<br>{control}</label><br>')
    raw_form = (
        f'<form method="POST" action="{base}/api/public/forms/{key}/submit">\n'
        + "\n".join(html_inputs) +
        '\n  <!-- Keep this hidden field: it stops spam bots. -->\n'
        '  <div style="position:absolute;left:-10000px" aria-hidden="true">'
        '<input type="text" name="_hp" tabindex="-1" autocomplete="off"></div>\n'
        f'  <button type="submit">{html.escape(form["settings"]["submit_text"])}</button>\n'
        '</form>')
    return {
        "public_key": key,
        "hosted_url": f"{base}/api/public/forms/{key}/page",
        "inline": (f'<div data-clientverse-form="{key}"></div>\n'
                   f'<script async src="{base}/api/public/forms/embed.js"></script>'),
        "popup": (f'<div data-clientverse-form="{key}" data-mode="popup" '
                  'data-button-text="Contact us"></div>\n'
                  f'<script async src="{base}/api/public/forms/embed.js"></script>'),
        "popup_auto": (f'<div data-clientverse-form="{key}" data-mode="popup" '
                       'data-trigger="delay:15"></div>\n'
                       f'<script async src="{base}/api/public/forms/embed.js"></script>'),
        "slide_in": (f'<div data-clientverse-form="{key}" data-mode="popup" data-layout="slide-in" '
                     'data-trigger="scroll:50"></div>\n'
                     f'<script async src="{base}/api/public/forms/embed.js"></script>'),
        "listing_page": (f'<div data-clientverse-form="{key}" data-listing-id="MLS-NUMBER" '
                         'data-property-address="123 Main St"></div>\n'
                         f'<script async src="{base}/api/public/forms/embed.js"></script>'),
        "iframe": (f'<iframe src="{base}/api/public/forms/{key}/page" title="{html.escape(form["name"])}" '
                   'style="width:100%;min-height:720px;border:0" loading="lazy"></iframe>'),
        "html_form": raw_form,
        "api": {"method": "POST", "url": f"{base}/api/public/forms/{key}/submit",
                "content_types": ["application/json", "text/plain (JSON body)",
                                  "application/x-www-form-urlencoded", "multipart/form-data"],
                "fields": [f["key"] for f in fields] + list(TRACKING_FIELDS),
                "idempotency": "Send a unique `_sid` (or `external_id`) per submission; "
                               "a retry with the same value is not filed twice."},
    }


# ---------------------------------------------------------------------- routes

def register_website_form_routes(router, db, *, new_id, now_iso, record_event,
                                 get_current_user, require_role, spawn,
                                 send_email=None, email_configured=None, get_prefs=None,
                                 public_base_url: str = "",
                                 provider_registry=None, encrypt=None,
                                 decrypt=None) -> LeadPipeline:
    pipeline = LeadPipeline(db, new_id=new_id, now_iso=now_iso, record_event=record_event,
                            spawn=spawn, send_email=send_email,
                            email_configured=email_configured, get_prefs=get_prefs,
                            public_base_url=public_base_url,
                            provider_registry=provider_registry,
                            encrypt=encrypt, decrypt=decrypt)

    async def load_form(form_id: str, user: dict) -> dict:
        form = await db[FORMS].find_one({"id": form_id, "tenant_id": user["tenant_id"],
                                         "status": {"$ne": "archived"}}, {"_id": 0})
        if not form:
            raise HTTPException(status_code=404, detail="Not found")
        return with_defaults(form)

    def take_captcha_secret(settings_patch: Optional[dict]) -> Optional[str]:
        """Pull a write-only CAPTCHA secret out of a settings update before it is stored.

        Returns the new secret, "" to clear it, or None when the update does not touch it.
        """
        captcha = (settings_patch or {}).get("captcha")
        if not isinstance(captcha, dict) or "secret" not in captcha:
            return None
        secret = str(captcha.pop("secret") or "").strip()
        if secret and not re.fullmatch(r"[A-Za-z0-9_\-.]{8,300}", secret):
            raise HTTPException(status_code=422, detail="captcha secret does not look like a secret key")
        if secret and not encrypt:
            raise HTTPException(status_code=500, detail="Secure credential storage is not configured")
        return secret

    def apply_captcha_secret(changes: dict, settings: dict, secret: Optional[str]) -> None:
        if secret is None:
            return
        if secret:
            changes["captcha_secret_enc"] = encrypt({"secret": secret}) if encrypt else None
        else:
            changes["captcha_secret_enc"] = None
        settings["captcha"]["secret_configured"] = bool(secret)

    async def present(form: dict) -> dict:
        form = with_defaults(form)
        out = {k: v for k, v in form.items()
               if k not in ("_id", "captcha_secret_enc", "server_key_hash")}
        out["server_key"] = {"configured": bool(form.get("server_key_hash")),
                             "hint": form.get("server_key_hint"),
                             "created_at": form.get("server_key_created_at"),
                             "last_used_at": form.get("server_key_last_used_at")}
        out["embed"] = embed_snippets(form, pipeline.public_base_url)
        state = await pipeline.template_approval_state(form)
        out["auto_reply_state"] = {"state": state["state"],
                                   "approval_id": (state["approval"] or {}).get("id")}
        counts = {}
        for status in LEAD_STATUSES:
            counts[status] = await db[detectors.WEB_ENQUIRIES].count_documents(
                {"tenant_id": form["tenant_id"], "form_id": form["id"], "status": status})
        out["lead_counts"] = counts
        return out

    async def request_template_approval(form: dict, user: dict) -> dict:
        reply = form["settings"]["auto_reply"]
        sha = template_fingerprint(reply["subject"], reply["body"])
        approval = await approval_queue.request(
            db, tenant_id=form["tenant_id"],
            title=f"Approve the automatic reply for website form '{form['name']}'",
            kind="website_form.auto_reply_template", actor=user["email"],
            requester_kind=approval_queue.REQUESTER_HUMAN,
            summary=f"Subject: {reply['subject']}\n\n{reply['body']}",
            risk=approval_queue.RISK_MEDIUM,
            action={"type": "website_form.auto_reply_template", "form_id": form["id"],
                    "template_sha256": sha},
            subject_type="website_form", subject_id=form["id"],
            facts=[{"label": "Sent to", "value": "Every new lead from this form who left an email",
                    "source": f"website_form:{form['id']}"},
                   {"label": "Merge fields", "value": ", ".join(MERGE_FIELDS),
                    "source": "website_forms.MERGE_FIELDS"}],
            dedupe_key=f"website_form_auto_reply:{form['id']}:{sha}",
            expires_in_hours=approval_queue.MAX_EXPIRY_HOURS)
        await db[FORMS].update_one({"id": form["id"], "tenant_id": form["tenant_id"]},
                                   {"$set": {"settings.auto_reply.approval_id": approval["id"],
                                             "settings.auto_reply.template_sha256": sha}})
        form["settings"]["auto_reply"].update(approval_id=approval["id"], template_sha256=sha)
        return approval

    # ------------------------------------------------------------ catalogue

    @router.get("/website-forms/catalog")
    async def form_catalog(user=Depends(get_current_user)):
        return {"fields": [{"key": k, **v} for k, v in FIELD_CATALOG.items()],
                "tracking_fields": list(TRACKING_FIELDS),
                "custom_field_types": list(CUSTOM_FIELD_TYPES),
                "presets": [{"key": k, "label": v["label"],
                             "fields": [_field_definition(f) for f in v["fields"]]}
                            for k, v in PRESETS.items()],
                "merge_fields": list(MERGE_FIELDS)}

    # ---------------------------------------------------------------- forms

    @router.get("/website-forms")
    async def list_forms(user=Depends(get_current_user)):
        forms = await db[FORMS].find({"tenant_id": user["tenant_id"],
                                      "status": {"$ne": "archived"}},
                                     {"_id": 0}).sort("created_at", -1).to_list(200)
        forms = [with_defaults(f) for f in forms]
        return {"items": [await present(f) for f in forms]}

    @router.post("/website-forms")
    async def create_form(inp: FormCreate, user=Depends(require_role("admin"))):
        if inp.preset not in PRESETS:
            raise HTTPException(status_code=422,
                                detail=f"preset must be one of {', '.join(PRESETS)}")
        specs = inp.fields if inp.fields is not None else [
            FieldSpec(**f) for f in PRESETS[inp.preset]["fields"]]
        patch = json.loads(json.dumps(inp.settings or {}))
        secret = take_captcha_secret(patch)
        settings = merge_settings(_default_settings(inp.preset), patch)
        secret_fields: dict[str, Any] = {}
        apply_captcha_secret(secret_fields, settings, secret)
        if settings["captcha"]["provider"] == "turnstile" and not (
                secret_fields.get("captcha_secret_enc") and settings["captcha"]["site_key"]):
            raise HTTPException(status_code=422,
                                detail="Turnstile needs both a site key and a secret key")
        now = now_iso()
        doc = {"id": new_id("wf"), "tenant_id": user["tenant_id"], "name": inp.name.strip(),
               "form_type": inp.preset, "public_key": "f_" + secrets.token_urlsafe(18),
               "status": "active", "fields": validate_fields(specs), "settings": settings,
               "stats": {"views": 0, "submissions": 0, "spam_blocked": 0,
                         "last_submission_at": None, "round_robin_cursor": 0},
               "created_by": user["email"], "created_at": now, "updated_at": now,
               "captcha_secret_enc": secret_fields.get("captcha_secret_enc")}
        await db[FORMS].insert_one(dict(doc))
        await record_event("website_form.created", "website_form", doc["id"], user["tenant_id"],
                           user["email"], payload={"name": doc["name"], "preset": inp.preset})
        if settings["auto_reply"]["enabled"]:
            await request_template_approval(doc, user)
        return await present(doc)

    @router.get("/website-forms/{form_id}")
    async def get_form(form_id: str, user=Depends(get_current_user)):
        return await present(await load_form(form_id, user))

    @router.patch("/website-forms/{form_id}")
    async def update_form(form_id: str, inp: FormPatch, user=Depends(require_role("admin"))):
        form = await load_form(form_id, user)
        changes: dict[str, Any] = {"updated_at": now_iso()}
        if inp.name is not None:
            changes["name"] = inp.name.strip()
        if inp.status is not None:
            if inp.status not in ("active", "paused", "archived"):
                raise HTTPException(status_code=422, detail="status must be active, paused or archived")
            changes["status"] = inp.status
        if inp.fields is not None:
            changes["fields"] = validate_fields(inp.fields)
        if inp.settings is not None:
            patch = json.loads(json.dumps(inp.settings))
            secret = take_captcha_secret(patch)
            changes["settings"] = merge_settings(form["settings"], patch)
            apply_captcha_secret(changes, changes["settings"], secret)
        if (changes.get("settings") or form["settings"])["captcha"]["provider"] == "turnstile":
            merged = {**form, **changes}
            if not (merged.get("captcha_secret_enc") and merged["settings"]["captcha"]["site_key"]):
                raise HTTPException(status_code=422,
                                    detail="Turnstile needs both a site key and a secret key")
        await db[FORMS].update_one({"id": form_id, "tenant_id": user["tenant_id"]},
                                   {"$set": changes})
        await record_event("website_form.updated", "website_form", form_id, user["tenant_id"],
                           user["email"], payload={"changed": sorted(
                               k for k in changes if k not in ("updated_at", "captcha_secret_enc"))})
        form = {**form, **changes}
        reply = form["settings"]["auto_reply"]
        if reply["enabled"]:
            state = await pipeline.template_approval_state(form)
            if state["state"] in ("not_requested", "rejected", "expired", "cancelled"):
                await request_template_approval(form, user)
        return await present(form)

    @router.post("/website-forms/{form_id}/server-key")
    async def create_server_key(form_id: str, user=Depends(require_role("admin"))):
        """Mint the key a website's own server sends to forward leads. Shown once.

        Creating a new key replaces the old one immediately, so rotating is one click and
        a leaked key stops working the moment it is replaced.
        """
        form = await load_form(form_id, user)
        key = "cvsk_" + secrets.token_urlsafe(32)
        await db[FORMS].update_one(
            {"id": form["id"], "tenant_id": user["tenant_id"]},
            {"$set": {"server_key_hash": _sha(key), "server_key_hint": key[-4:],
                      "server_key_created_at": now_iso(), "server_key_last_used_at": None}})
        await record_event("website_form.server_key_created", "website_form", form["id"],
                           user["tenant_id"], user["email"], payload={"hint": key[-4:]})
        return {"key": key, "hint": key[-4:],
                # One address for every website server; the key says which form.
                "intake_url": f"{pipeline.public_base_url}/api/intake/leads",
                "submit_url": embed_snippets(form, pipeline.public_base_url)["api"]["url"],
                "note": "Store this now. It is hashed at rest and cannot be shown again."}

    @router.delete("/website-forms/{form_id}/server-key")
    async def revoke_server_key(form_id: str, user=Depends(require_role("admin"))):
        form = await load_form(form_id, user)
        await db[FORMS].update_one(
            {"id": form["id"], "tenant_id": user["tenant_id"]},
            {"$set": {"server_key_hash": None, "server_key_hint": None,
                      "server_key_created_at": None}})
        await record_event("website_form.server_key_revoked", "website_form", form["id"],
                           user["tenant_id"], user["email"])
        return {"ok": True}

    @router.post("/website-forms/{form_id}/test")
    async def test_form(form_id: str, inp: TestLead, user=Depends(require_role("admin"))):
        """Run a lead through the real pipeline, marked as a test, to prove the wiring."""
        form = await load_form(form_id, user)
        sample = inp.data or {"first_name": "Test", "last_name": "Lead",
                              "email": f"test-lead+{secrets.token_hex(3)}@example.com",
                              "phone": "555-010-0199",
                              "message": "Test submission from the CRM to check this form end to end."}
        for spec in form["fields"]:
            if spec.get("required") and spec["key"] not in sample:
                definition = _field_definition(spec)
                sample[spec["key"]] = (True if definition["type"] == "checkbox" else
                                       (definition["options"] or ["Test"])[0]
                                       if definition["type"] == "select" else
                                       "450000" if definition["type"] == "number" else
                                       "2030-01-01" if definition["type"] == "date" else "Test")
        try:
            result = await pipeline.submit(form, sample, {"channel": "test",
                                                          "origin": None, "visitor": "test"},
                                           test=True)
        except SubmissionInvalid as exc:
            raise HTTPException(status_code=422, detail={"errors": exc.errors})
        lead = await db[detectors.WEB_ENQUIRIES].find_one(
            {"id": result["id"], "tenant_id": user["tenant_id"]}, {"_id": 0})
        return {"result": result, "lead": lead}

    # ---------------------------------------------------------------- leads

    @router.get("/leads")
    async def list_leads(status: Optional[str] = None, form_id: Optional[str] = None,
                         q: Optional[str] = None, include_tests: bool = True,
                         limit: int = 50, offset: int = 0,
                         user=Depends(get_current_user)):
        query: dict[str, Any] = {"tenant_id": user["tenant_id"]}
        if status:
            if status not in LEAD_STATUSES:
                raise HTTPException(status_code=422,
                                    detail=f"status must be one of {', '.join(LEAD_STATUSES)}")
            query["status"] = status
        if form_id:
            query["form_id"] = form_id
        if not include_tests:
            query["is_test"] = {"$ne": True}
        if q:
            pattern = {"$regex": re.escape(q.strip())[:100], "$options": "i"}
            query["$or"] = [{"name": pattern}, {"email": pattern}, {"phone": pattern},
                            {"property_address": pattern}, {"listing_id": pattern}]
        limit = max(1, min(int(limit or 50), 200))
        offset = max(0, int(offset or 0))
        items = await db[detectors.WEB_ENQUIRIES].find(query, {"_id": 0, "visitor": 0}).sort(
            "received_at", -1).skip(offset).limit(limit).to_list(limit)
        return {"items": items,
                "total": await db[detectors.WEB_ENQUIRIES].count_documents(query),
                "limit": limit, "offset": offset}

    @router.get("/leads/summary")
    async def lead_summary(days: int = 30, user=Depends(get_current_user)):
        tenant = user["tenant_id"]
        since = _iso(_now() - timedelta(days=max(1, min(int(days or 30), 365))))
        rows = await db[detectors.WEB_ENQUIRIES].find(
            {"tenant_id": tenant, "received_at": {"$gte": since}, "is_test": {"$ne": True}},
            {"_id": 0, "status": 1, "sla": 1, "form_name": 1, "attribution": 1,
             "estimated_value": 1, "currency": 1}).to_list(10000)
        by_status = dict.fromkeys(LEAD_STATUSES, 0)
        by_form: dict[str, int] = {}
        by_source: dict[str, int] = {}
        minutes = []
        breached = 0
        uncontacted_value = 0.0
        for row in rows:
            by_status[row.get("status", "new")] = by_status.get(row.get("status", "new"), 0) + 1
            by_form[row.get("form_name") or "Website"] = by_form.get(row.get("form_name") or "Website", 0) + 1
            attribution = row.get("attribution") or {}
            source = attribution.get("utm_source") or (
                urlparse(attribution.get("referrer") or "").hostname or "direct")
            by_source[source] = by_source.get(source, 0) + 1
            sla = row.get("sla") or {}
            if sla.get("response_minutes") is not None:
                minutes.append(sla["response_minutes"])
            if sla.get("escalated_at"):
                breached += 1
            if row.get("status") == "new":
                uncontacted_value += float(row.get("estimated_value") or 0)
        minutes.sort()
        median = minutes[len(minutes) // 2] if minutes else None
        open_now = await db[detectors.WEB_ENQUIRIES].count_documents(
            {"tenant_id": tenant, "status": "new", "is_test": {"$ne": True}})
        return {"window_days": days, "total": len(rows), "by_status": by_status,
                "by_form": by_form, "by_source": by_source,
                "median_response_minutes": median,
                "within_5_minutes": sum(1 for m in minutes if m <= 5),
                "responded": len(minutes), "sla_breaches": breached, "open_now": open_now,
                # An estimate, labelled as one: value of leads nobody has responded to yet.
                "uncontacted_value_estimate": round(uncontacted_value, 2)}

    @router.get("/leads/export")
    async def export_leads(status: Optional[str] = None, form_id: Optional[str] = None,
                           include_tests: bool = False, user=Depends(get_current_user)):
        """Every lead as CSV, for a spreadsheet or another system."""
        query: dict[str, Any] = {"tenant_id": user["tenant_id"]}
        if status in LEAD_STATUSES:
            query["status"] = status
        if form_id:
            query["form_id"] = form_id
        if not include_tests:
            query["is_test"] = {"$ne": True}
        rows = await db[detectors.WEB_ENQUIRIES].find(query, {"_id": 0}).sort(
            "received_at", -1).to_list(50000)
        columns = ["received_at", "status", "name", "email", "phone", "form_name",
                   "lead_type", "property_address", "listing_id", "message", "assigned_to",
                   "estimated_value", "currency", "response_minutes", "escalated_at",
                   "utm_source", "utm_medium", "utm_campaign", "referrer", "page_url",
                   "consent_sms", "consent_email", "contact_id", "opportunity_id", "id"]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            attribution = row.get("attribution") or {}
            consent = row.get("consent") or {}
            sla = row.get("sla") or {}
            flat = {**{k: row.get(k) for k in columns},
                    "lead_type": (row.get("fields") or {}).get("lead_type"),
                    "response_minutes": sla.get("response_minutes"),
                    "escalated_at": sla.get("escalated_at"),
                    "utm_source": attribution.get("utm_source"),
                    "utm_medium": attribution.get("utm_medium"),
                    "utm_campaign": attribution.get("utm_campaign"),
                    "referrer": attribution.get("referrer"),
                    "page_url": attribution.get("page_url"),
                    "consent_sms": consent.get("sms"), "consent_email": consent.get("email")}
            writer.writerow({k: crm_core.csv_safe(v) for k, v in flat.items()})
        await record_event("data.exported", "leads", "leads", user["tenant_id"], user["email"],
                           payload={"rows": len(rows)})
        return Response(content=buffer.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="leads.csv"'})

    @router.get("/leads/{lead_id}")
    async def get_lead(lead_id: str, user=Depends(get_current_user)):
        lead = await db[detectors.WEB_ENQUIRIES].find_one(
            {"id": lead_id, "tenant_id": user["tenant_id"]}, {"_id": 0, "visitor": 0})
        if not lead:
            raise HTTPException(status_code=404, detail="Not found")
        return lead

    @router.patch("/leads/{lead_id}")
    async def update_lead(lead_id: str, inp: LeadPatch, user=Depends(get_current_user)):
        if inp.status not in LEAD_STATUSES:
            raise HTTPException(status_code=422,
                                detail=f"status must be one of {', '.join(LEAD_STATUSES)}")
        lead = await db[detectors.WEB_ENQUIRIES].find_one(
            {"id": lead_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not lead:
            raise HTTPException(status_code=404, detail="Not found")
        if inp.status == "responded" and lead["status"] == "new":
            await pipeline.mark_responded(lead, via="marked_in_inbox", actor=user["email"])
        elif inp.status != lead["status"]:
            await db[detectors.WEB_ENQUIRIES].update_one(
                {"id": lead_id, "tenant_id": user["tenant_id"]},
                {"$set": {"status": inp.status, "status_changed_by": user["email"],
                          "status_changed_at": now_iso()}})
            if inp.status == "spam" and lead.get("created_contact"):
                # The contact and deal exist only because of this submission, so they go
                # with it -- archived, never deleted, and restorable.
                stamp = now_iso()
                if lead.get("contact_id"):
                    await db.contacts.update_one(
                        {"id": lead["contact_id"], "tenant_id": user["tenant_id"]},
                        {"$set": {"archived_at": stamp, "archived_reason": "spam"}})
                if lead.get("opportunity_id"):
                    await db.opportunities.update_one(
                        {"id": lead["opportunity_id"], "tenant_id": user["tenant_id"]},
                        {"$set": {"archived_at": stamp, "archived_reason": "spam"}})
                if lead.get("task_id"):
                    await db.tasks.update_one(
                        {"id": lead["task_id"], "tenant_id": user["tenant_id"]},
                        {"$set": {"status": "cancelled", "updated_at": stamp}})
        if inp.note and lead.get("contact_id"):
            await db.crm_activities.insert_one({
                "id": new_id("act"), "tenant_id": user["tenant_id"], "type": "note",
                "related_type": "contact", "related_id": lead["contact_id"],
                "subject": f"Lead {inp.status}", "body": inp.note, "occurred_at": now_iso(),
                "duration_minutes": None, "participants": [], "outcome": None,
                "actor": user["email"], "created_at": now_iso(), "logged_by": user["email"]})
        await record_event("lead.status_changed", "web_enquiry", lead_id, user["tenant_id"],
                           user["email"], payload={"from": lead["status"], "to": inp.status})
        return await db[detectors.WEB_ENQUIRIES].find_one(
            {"id": lead_id, "tenant_id": user["tenant_id"]}, {"_id": 0, "visitor": 0})

    # --------------------------------------------------------------- public

    @router.get("/public/forms/embed.js")
    async def embed_script():
        return Response(EMBED_JS, media_type="application/javascript",
                        headers={"Cache-Control": "public, max-age=300"})

    @router.get("/public/forms/{public_key}/config")
    async def public_form_config(public_key: str):
        form = await pipeline.form_by_key(public_key)
        if not form:
            raise HTTPException(status_code=404, detail="Not found")
        # Every render of the form fetches this once, so it is the form's view count:
        # submissions over views is its conversion rate.
        await db[FORMS].update_one({"id": form["id"]}, {"$inc": {"stats.views": 1}})
        return JSONResponse(public_config(form), headers={"Cache-Control": "no-store"})

    @router.get("/public/forms/{public_key}/page")
    async def public_form_page(public_key: str):
        form = await pipeline.form_by_key(public_key)
        if not form:
            return HTMLResponse("<!doctype html><title>Form unavailable</title>"
                                "<p>This form is not available.</p>", status_code=404)
        return HTMLResponse(hosted_page(form),
                            headers={"Content-Security-Policy": HOSTED_PAGE_CSP,
                                     "Cache-Control": "no-store"})

    @router.post("/intake/leads")
    async def server_intake(request: Request):
        """The server-to-server lead intake: one address, the key names the form.

        This is the interface a website's own backend was built against
        (`POST /api/intake/leads`, `Authorization: Bearer <key>`). It is the same trusted
        path as a keyed post to the form's own submit URL.
        """
        scheme, _, token = (request.headers.get("authorization") or "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return JSONResponse(status_code=401, content={"detail": "A server key is required"})
        form = await db[FORMS].find_one(
            {"server_key_hash": _sha(token.strip()), "status": "active"}, {"_id": 0})
        if not form:
            # Wrong, revoked, or for a paused form: the same answer for each.
            return JSONResponse(status_code=401, content={"detail": "Invalid server key"})
        return await pipeline._handle_server_submission(request, with_defaults(form))

    @router.post("/public/forms/{public_key}/submit")
    async def public_form_submit(public_key: str, request: Request):
        form = await pipeline.form_by_key(public_key)
        if not form:
            # The same answer for a paused, archived, mistyped or invented key.
            raise HTTPException(status_code=404, detail="Not found")
        return await pipeline.handle_public_submission(request, form)

    return pipeline
