"""Online booking: a lead picks a real open time, and it lands as worked CRM business (M-05).

A real-estate lead who wants to see a home, talk about buying or selling, or just have a
call should not have to wait for a phone tag to settle on a time. This module is the whole
path, end to end:

1.  **Booking pages.** A tenant defines event types -- home showing, buyer consultation,
    listing appointment, phone call ship as presets -- each with a duration, buffers
    before and after (travel time between showings), a minimum notice, how far ahead it
    can be booked, a slot interval, where it happens, who hosts it (one agent, or
    round-robin), the questions it asks, and what the CRM does with the booking.
2.  **Availability.** Each agent has weekly hours in their own time zone, plus days off
    and special hours. Mon-Sat 9:00-18:00 until they say otherwise.
3.  **Slots.** Computed here, in UTC, from the agent's hours in the agent's zone (so a
    DST change moves the UTC times and not the agent's day), minus every appointment
    the agent already has -- with both bookings' buffers -- minus Google Calendar busy
    times when that calendar is connected for that agent, minus the minimum notice,
    within the horizon. A public slot list carries free start times and nothing else.
4.  **A public door**, CORS-open and never credentialed, like the website forms one:
    honeypot, minimum fill time, rate limits, an idempotency key, and **no double
    booking**: each booking is written under a per-agent lock after re-checking the
    agent's calendar, and a unique index on the active (agent, start) claim backs it up,
    so two people racing for one time get one booking and one "that time was just
    taken" with the times still open.
5.  **Worked CRM business.** The booking runs through the website-forms `LeadPipeline`
    -- contact match-or-create, a deal valued at expected commission, `lead.received`
    -- and becomes an appointment in the same `appointments` collection client
    operations use, with the same fields and statuses, so the recovery detectors see
    cancellations and no-shows of booked appointments without knowing this module
    exists. The lead itself is recorded as answered by the booking: the person chose a
    time with an agent, which is not an unanswered enquiry.
6.  **Changes.** The person gets a signed, single-purpose link to view, reschedule or
    cancel; agents can mark attended / no-show, cancel or reschedule on their behalf.
    An `.ics` file and a Google Calendar link put it in the person's calendar.
7.  **Reminders**, 24 hours and 1 hour before by default, each claimed exactly once with
    a conditional update (`send_due_reminders`, also `POST /api/cron/booking-reminders`).

WHY THE TASK IS "CONFIRM THE SHOWING", NOT "CALL WITHIN 5 MINUTES"

A website lead is called at once because they are waiting to hear from someone. A person
who booked a time is not waiting -- calling them minutes later to "respond" is noise. What
a booking does need is the agent's preparation: a showing needs access arranged with the
listing agent or showing service, a listing appointment needs a pricing analysis, a
consultation needs the file read. So each booking gets one preparation task for the host,
due a configurable time before the appointment (or now, if it was booked closer than that),
attached to the contact. A phone call gets none: the calendar entry is the follow-up. The
task is deliberately not attached to the appointment record itself -- the no-show detector
reads a task against an appointment as somebody having followed up on it.

THE EMAILS TO THE PERSON AND THE APPROVAL GATE

The governing document's M-07 amendment lets a standing approval authorise exactly one
thing -- a website form's automatic-reply template -- and says no other action may ride
one. A booking confirmation is not that, so it does not get one. Each confirmation, change
notice and reminder to the person is written into the booking's own conversation with a
consent record (the basis: this person booked this appointment and gave this address for
it), and raises its own single-use M-07 approval bound to its exact words. An admin
approves it -- on the calendar or in Operations -> Approvals -- and only then is it
delivered, through `conversations.attempt_delivery` like every other message. An approval
still open when the appointment starts lapses. When no email channel is authorised,
nothing is drafted: the person already has their confirmation on screen, an
add-to-calendar file and the manage link. Letting a standing approval cover booking
confirmations would be an owner amendment to M-07, not something this module assumes.

ADAPTED FROM CAL.DIY (MIT), RE-IMPLEMENTED

The booking model -- event types with duration and buffers, weekly availability with date
overrides, minimum notice, a rolling horizon, slots computed for the booker's time zone,
confirmation and reminders, reschedule/cancel links -- follows `calcom/cal.diy` (MIT).
None of its code is copied and Cal is not run: no second application, no second database,
none of its auth or team model. Everything here is written against this CRM's own
collections.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import html
import json
import logging
import os
import re
import secrets
import time as monotonic_clock
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

import approval_queue
import conversations as conversation_service
import crm_core
import detectors
import recovery_strategy
import website_forms as wf

logger = logging.getLogger("clientverse.booking")

EVENT_TYPES = "booking_event_types"
AVAILABILITY = "booking_availability"
ATTEMPTS = "booking_attempts"
LOCKS = "booking_locks"
APPOINTMENTS = "appointments"

SYSTEM_ACTOR = "system:booking"

# Added to the website forms' public set, so a browser on any website may call these
# paths -- never with credentials. Nothing under it reads tenant data beyond one page's
# free times, or one booking through its own token.
PUBLIC_PATH_PREFIX = "/api/public/booking/"
# The one SPA route an agent's website may frame. The manage page and the app are not.
FRAMEABLE_PAGE_PATH = re.compile(r"^/book/[a-z0-9][a-z0-9\-]{1,78}[a-z0-9]/?$")

# Statuses that hold a slot and are still ahead of the agent. `confirmed` is what a
# booking starts as; `scheduled` is what an appointment typed into client operations is.
ACTIVE_STATUSES = ("confirmed", "scheduled")
CANCELLED_STATUSES = detectors.CANCELLED_APPOINTMENT_STATUSES
OUTCOMES = {"attended": "completed", "no_show": "no_show"}

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DEFAULT_HOURS = {"start": "09:00", "end": "18:00"}
DEFAULT_WORKDAYS = WEEKDAYS[:6]

MAX_RANGE_DAYS = 42
MAX_INTERVALS_PER_DAY = 6
MAX_OVERRIDES = 366
REMINDER_CHOICES = (1, 2, 4, 12, 24, 48)
LOCK_SECONDS = 15
LOCK_WAIT_SECONDS = 6.0
BUSY_CACHE_SECONDS = 60

RATE_BOOK_PER_VISITOR_PER_HOUR = int(os.environ.get("BOOKING_RATE_PER_VISITOR_PER_HOUR", "10"))
RATE_BOOK_PER_PAGE_PER_MINUTE = int(os.environ.get("BOOKING_RATE_PER_PAGE_PER_MINUTE", "60"))
RATE_READ_PER_VISITOR_PER_HOUR = int(os.environ.get("BOOKING_READ_RATE_PER_VISITOR_PER_HOUR", "600"))
RATE_MANAGE_PER_VISITOR_PER_HOUR = int(os.environ.get("BOOKING_MANAGE_RATE_PER_VISITOR_PER_HOUR", "30"))

LOCATION_KINDS = {
    "property": "At the property",
    "office": "At our office",
    "phone": "Phone call",
    "video": "Video call",
}

# The website-forms catalogue fields a booking page may ask, beyond name and email.
QUESTION_KEYS = ("phone", "property_address", "listing_id", "pre_approved", "working_with_agent",
                 "timeline", "price_max", "message", "consent_sms", "consent_email")
IDENTITY_FIELDS = (("first_name", True), ("last_name", True), ("email", True))

RESERVED_KEYS = {"manage", "embed", "embed-js"}
SLUG = re.compile(r"^[a-z0-9][a-z0-9\-]{1,78}[a-z0-9]$")
TOKEN = re.compile(r"^[A-Za-z0-9_\-]{40,60}$")
HM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$|^24:00$")


def _q(*spec: tuple) -> list[dict]:
    return [{"key": key, "required": bool(required)} for key, required in spec]


PRESETS: dict[str, dict] = {
    "home_showing": {
        "label": "Home showing", "duration": 30, "before": 15, "after": 15,
        "notice_hours": 2, "days_ahead": 30, "interval": 30,
        "description": "See the home in person. Tell us which property and we'll meet you there.",
        "location": {"kind": "property", "text": ""},
        "questions": _q(("phone", True), ("property_address", True), ("listing_id", False),
                        ("pre_approved", False), ("message", False), ("consent_sms", False)),
        "opportunity": True,
        "task": {"enabled": True, "lead_minutes": 120,
                 "title": "Confirm the showing with {name}: arrange access to {address}"},
        "reminders": [24, 1],
        "confirmation": "We'll meet you at the property. If anything changes, use the link "
                        "below to reschedule or cancel.",
    },
    "buyer_consultation": {
        "label": "Buyer consultation", "duration": 45, "before": 0, "after": 15,
        "notice_hours": 4, "days_ahead": 60, "interval": 30,
        "description": "Talk through your budget, neighborhoods and the buying process "
                       "with an agent.",
        "location": {"kind": "office", "text": ""},
        "questions": _q(("phone", True), ("pre_approved", False), ("timeline", False),
                        ("price_max", False), ("message", False), ("consent_sms", False)),
        "opportunity": True,
        "task": {"enabled": True, "lead_minutes": 60,
                 "title": "Prepare for the buyer consultation with {name}"},
        "reminders": [24, 1],
        "confirmation": "Bring your questions — and your pre-approval letter if you have one.",
    },
    "listing_appointment": {
        "label": "Listing appointment", "duration": 60, "before": 30, "after": 30,
        "notice_hours": 24, "days_ahead": 60, "interval": 30,
        "description": "We'll walk through your home, talk pricing and plan the sale.",
        "location": {"kind": "property", "text": ""},
        "questions": _q(("phone", True), ("property_address", True), ("timeline", False),
                        ("message", False), ("consent_sms", False)),
        "opportunity": True,
        "task": {"enabled": True, "lead_minutes": 1440,
                 "title": "Prepare a pricing analysis (CMA) for {address} before meeting {name}"},
        "reminders": [24, 1],
        "confirmation": "We'll come to the property at the time above.",
    },
    "phone_call": {
        "label": "Phone call", "duration": 15, "before": 0, "after": 5,
        "notice_hours": 1, "days_ahead": 30, "interval": 15,
        "description": "A quick call to answer your questions.",
        "location": {"kind": "phone", "text": ""},
        "questions": _q(("phone", True), ("message", False), ("consent_sms", False)),
        "opportunity": False,
        # The calendar entry is the follow-up; a task would only repeat it.
        "task": {"enabled": False, "lead_minutes": 0, "title": "Call {name}"},
        "reminders": [1],
        "confirmation": "We'll call you at the number you gave.",
    },
}
DEFAULT_PRESET_ORDER = ("home_showing", "buyer_consultation", "listing_appointment", "phone_call")


# ------------------------------------------------------------------------ helpers

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: Any) -> Optional[datetime]:
    return detectors.parse_time(value)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_duplicate_key(exc: Exception) -> bool:
    return getattr(exc, "code", None) == 11000 or "E11000" in str(exc) \
        or "duplicate key" in str(exc).lower()


def zone(name: Any) -> ZoneInfo:
    """A time zone by IANA name, or ValueError. `UTC` is a zone like any other."""
    text = str(name or "").strip()
    if not text or len(text) > 64 or not re.fullmatch(r"[A-Za-z0-9_+\-/]+", text):
        raise ValueError(f"'{text}' is not a time zone")
    try:
        return ZoneInfo(text)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"'{text}' is not a time zone")


def _minutes(value: str) -> int:
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def _parse_day(value: Any) -> date:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        raise ValueError(f"'{value}' is not a date like 2026-10-20")


def _clean_intervals(raw: Any, where: str) -> list[dict]:
    """Validate and merge a day's intervals. Raises ValueError naming `where`."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{where} must be a list of times")
    spans = []
    for item in raw[:MAX_INTERVALS_PER_DAY + 1]:
        start = str((item or {}).get("start") or "")
        end = str((item or {}).get("end") or "")
        if not HM.match(start) or not HM.match(end):
            raise ValueError(f"{where}: times must look like 09:00")
        if _minutes(end) <= _minutes(start):
            raise ValueError(f"{where}: each block must end after it starts")
        spans.append((_minutes(start), _minutes(end)))
    if len(spans) > MAX_INTERVALS_PER_DAY:
        raise ValueError(f"{where}: at most {MAX_INTERVALS_PER_DAY} blocks a day")
    spans.sort()
    merged: list[list[int]] = []
    for start_m, end_m in spans:
        if merged and start_m <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end_m)
        else:
            merged.append([start_m, end_m])
    return [{"start": f"{s // 60:02d}:{s % 60:02d}", "end": f"{e // 60:02d}:{e % 60:02d}"}
            for s, e in merged]


def default_weekly() -> dict:
    return {day: ([dict(DEFAULT_HOURS)] if day in DEFAULT_WORKDAYS else []) for day in WEEKDAYS}


def validate_availability(timezone_name: Any, weekly: Any, overrides: Any) -> dict:
    """Return clean {timezone, weekly, overrides}, or raise ValueError with a plain reason."""
    zone(timezone_name)
    if not isinstance(weekly, dict):
        raise ValueError("weekly hours must list each day")
    clean_weekly = {day: _clean_intervals(weekly.get(day), day.title()) for day in WEEKDAYS}
    clean_overrides = []
    seen: set[str] = set()
    for item in (overrides or [])[:MAX_OVERRIDES + 1]:
        day = _parse_day((item or {}).get("date")).isoformat()
        if day in seen:
            raise ValueError(f"{day} is listed twice")
        seen.add(day)
        clean_overrides.append({"date": day,
                                "intervals": _clean_intervals((item or {}).get("intervals"), day),
                                "label": str((item or {}).get("label") or "").strip()[:80] or None})
    if len(clean_overrides) > MAX_OVERRIDES:
        raise ValueError(f"At most {MAX_OVERRIDES} days off or special days")
    clean_overrides.sort(key=lambda o: o["date"])
    return {"timezone": str(timezone_name).strip(), "weekly": clean_weekly,
            "overrides": clean_overrides}


# ------------------------------------------------------------------ slot math

Busy = tuple[datetime, datetime, int, int]  # start, end, buffer before, buffer after


def host_windows(availability: dict, range_start: datetime,
                 range_end: datetime) -> list[tuple[datetime, datetime]]:
    """The agent's open hours as UTC intervals, for every local day touching the range.

    Each local day's hours are read in the agent's own zone and converted on that day,
    so 9:00 stays 9:00 for the agent across a DST change while its UTC instant moves. A
    wall-clock time that does not exist (the spring-forward hour) collapses to nothing,
    and one that happens twice (the fall-back hour) is counted twice, because those are
    two real hours.
    """
    tz = zone(availability.get("timezone") or "UTC")
    overrides = {o["date"]: o.get("intervals") or [] for o in availability.get("overrides") or []}
    weekly = availability.get("weekly") or {}
    first = range_start.astimezone(tz).date() - timedelta(days=1)
    last = range_end.astimezone(tz).date() + timedelta(days=1)
    windows = []
    day = first
    while day <= last:
        intervals = overrides.get(day.isoformat())
        if intervals is None:
            intervals = weekly.get(WEEKDAYS[day.weekday()]) or []
        midnight = datetime(day.year, day.month, day.day, tzinfo=tz)
        for span in intervals:
            # Aware arithmetic on one tzinfo is wall-clock arithmetic, which is what an
            # opening hour is; the UTC conversion afterwards applies that day's offset.
            start = (midnight + timedelta(minutes=_minutes(span["start"]))).astimezone(timezone.utc)
            end = (midnight + timedelta(minutes=_minutes(span["end"]))).astimezone(timezone.utc)
            if end > start:
                windows.append((start, end))
        day += timedelta(days=1)
    return windows


def conflicts(start: datetime, duration: int, before: int, after: int, busy: list[Busy]) -> bool:
    """Whether a booking at `start` collides with anything already on the calendar.

    A collision is this booking's padded window over another booking's meeting, or this
    booking's meeting over another's padded window. Two buffers may overlap each other:
    the travel time after one showing can be the travel time before the next.
    """
    end = start + timedelta(minutes=duration)
    padded_start = start - timedelta(minutes=before)
    padded_end = end + timedelta(minutes=after)
    for other_start, other_end, other_before, other_after in busy:
        if padded_start < other_end and padded_end > other_start:
            return True
        if start < other_end + timedelta(minutes=other_after) and \
                end > other_start - timedelta(minutes=other_before):
            return True
    return False


def available_starts(*, windows: list[tuple[datetime, datetime]], busy: list[Busy],
                     duration: int, interval: int, before: int, after: int,
                     lower: datetime, upper: datetime) -> list[datetime]:
    """Start times on each window's own grid that fit, are free, and fall in [lower, upper)."""
    out: set[datetime] = set()
    step = timedelta(minutes=max(5, interval))
    length = timedelta(minutes=duration)
    for window_start, window_end in windows:
        start = window_start
        while start + length <= window_end:
            if lower <= start < upper and not conflicts(start, duration, before, after, busy):
                out.add(start)
            start += step
    return sorted(out)


# ------------------------------------------------------------- event type rules

class BookingInvalid(Exception):
    pass


class SlotTaken(Exception):
    """The requested time is not (or no longer) open."""


def _int_in(value: Any, low: int, high: int, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise BookingInvalid(f"{label} must be a whole number")
    if not low <= number <= high:
        raise BookingInvalid(f"{label} must be between {low} and {high}")
    return number


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:60].strip("-")
    return slug or "booking"


def new_event_type(preset_key: str, *, tenant_id: str, name: Optional[str], creator: str,
                   new_id: Callable[[str], str], now: str) -> dict:
    preset = PRESETS[preset_key]
    label = (name or preset["label"]).strip()[:120]
    return {
        "id": new_id("bkp"), "tenant_id": tenant_id, "preset": preset_key, "name": label,
        "public_key": f"{slugify(label)}-{secrets.token_hex(3)}",
        "description": preset["description"], "brand_name": None,
        "duration_minutes": preset["duration"],
        "buffer_before_minutes": preset["before"], "buffer_after_minutes": preset["after"],
        "min_notice_hours": preset["notice_hours"], "max_days_ahead": preset["days_ahead"],
        "slot_interval_minutes": preset["interval"],
        "location": dict(preset["location"]),
        "hosts": {"mode": "specific", "users": [creator.lower()]},
        "questions": [dict(q) for q in preset["questions"]],
        "confirmation_message": preset["confirmation"],
        "opportunity": {"enabled": preset["opportunity"], "stage": None,
                        "value_mode": "commission", "fixed_value": 0.0,
                        "commission_rate": 2.5, "currency": "USD"},
        "prep_task": dict(preset["task"]),
        "reminders": {"hours": list(preset["reminders"])},
        "notify_person": {"email": True},
        "consent": {"sms_text": wf.DEFAULT_SMS_CONSENT, "email_text": wf.DEFAULT_EMAIL_CONSENT},
        "color": "#0a6177", "status": "active",
        "stats": {"views": 0, "bookings": 0, "round_robin_cursor": 0},
        "created_by": creator.lower(), "created_at": now, "updated_at": now,
    }


def validate_event_type(doc: dict) -> dict:
    """Normalise every setting that changes behaviour. Raises BookingInvalid."""
    out = json.loads(json.dumps(doc))
    out["name"] = str(out.get("name") or "").strip()[:120]
    if not out["name"]:
        raise BookingInvalid("Give the booking page a name")
    out["description"] = (str(out.get("description") or "").strip()[:2000]) or None
    out["brand_name"] = (str(out.get("brand_name") or "").strip()[:120]) or None
    key = str(out.get("public_key") or "").strip().lower()
    if not SLUG.match(key) or key in RESERVED_KEYS:
        raise BookingInvalid("The link name may use lowercase letters, numbers and dashes "
                             "(3-80 characters)")
    out["public_key"] = key
    out["duration_minutes"] = _int_in(out.get("duration_minutes"), 5, 480, "Length")
    out["buffer_before_minutes"] = _int_in(out.get("buffer_before_minutes"), 0, 240, "Time before")
    out["buffer_after_minutes"] = _int_in(out.get("buffer_after_minutes"), 0, 240, "Time after")
    out["slot_interval_minutes"] = _int_in(out.get("slot_interval_minutes"), 5, 240, "Start times every")
    out["max_days_ahead"] = _int_in(out.get("max_days_ahead"), 1, 365, "Bookable ahead (days)")
    try:
        notice = round(float(out.get("min_notice_hours")), 2)
    except (TypeError, ValueError):
        raise BookingInvalid("Minimum notice must be a number of hours")
    if not 0 <= notice <= 720:
        raise BookingInvalid("Minimum notice must be between 0 and 720 hours")
    out["min_notice_hours"] = notice

    location = out.get("location") or {}
    kind = location.get("kind")
    if kind not in LOCATION_KINDS:
        raise BookingInvalid(f"Location must be one of {', '.join(LOCATION_KINDS)}")
    text = str(location.get("text") or "").strip()[:500]
    # An office without an address yet still saves (the presets install before anyone has
    # typed one); the booking page then says "At our office" and the editor asks for it.
    if kind == "video" and not re.match(r"^https?://\S+$", text):
        raise BookingInvalid("Enter the video meeting link, starting with https://")
    out["location"] = {"kind": kind, "text": text}

    hosts = out.get("hosts") or {}
    if hosts.get("mode") not in ("specific", "round_robin"):
        raise BookingInvalid("Hosts must be one agent or round-robin")
    users = []
    for email in hosts.get("users") or []:
        email = str(email or "").strip().lower()
        if email and email not in users:
            users.append(email)
    if not users:
        raise BookingInvalid("Choose at least one agent to host this booking page")
    out["hosts"] = {"mode": hosts["mode"], "users": users[:25] if hosts["mode"] == "round_robin"
                    else users[:1]}

    questions: list[dict] = []
    for item in out.get("questions") or []:
        qkey = str((item or {}).get("key") or "").strip()
        if qkey not in QUESTION_KEYS:
            raise BookingInvalid(f"'{qkey}' is not a question a booking page can ask")
        if any(q["key"] == qkey for q in questions):
            continue
        questions.append({"key": qkey, "required": bool((item or {}).get("required"))})
    # Where the meeting happens decides what must be asked: a showing needs the property,
    # a phone call needs the number.
    needed = {"property": "property_address", "phone": "phone"}.get(kind)
    if needed:
        found = next((q for q in questions if q["key"] == needed), None)
        if found:
            found["required"] = True
        else:
            questions.insert(0, {"key": needed, "required": True})
    out["questions"] = questions

    out["confirmation_message"] = str(out.get("confirmation_message") or "").strip()[:1000] \
        or PRESETS.get(out.get("preset") or "", PRESETS["phone_call"])["confirmation"]
    opportunity = out.get("opportunity") or {}
    if opportunity.get("value_mode") not in ("fixed", "commission"):
        raise BookingInvalid("Deal value must be expected commission or a flat value")
    for numeric, upper in (("fixed_value", 1e9), ("commission_rate", 100)):
        number = wf.parse_amount(opportunity.get(numeric))
        if number is None or number > upper:
            raise BookingInvalid(f"Deal {numeric.replace('_', ' ')} is out of range")
        opportunity[numeric] = number
    out["opportunity"] = {"enabled": bool(opportunity.get("enabled")),
                          "stage": (str(opportunity.get("stage") or "").strip()[:60] or None),
                          "value_mode": opportunity["value_mode"],
                          "fixed_value": opportunity["fixed_value"],
                          "commission_rate": opportunity["commission_rate"],
                          "currency": str(opportunity.get("currency") or "USD").upper()[:3]}
    task = out.get("prep_task") or {}
    out["prep_task"] = {"enabled": bool(task.get("enabled")),
                        "title": str(task.get("title") or "").strip()[:200] or "Prepare for {type} with {name}",
                        "lead_minutes": _int_in(task.get("lead_minutes") or 0, 0, 10080,
                                                "Task due before (minutes)")}
    hours = sorted({_int_in(h, 1, 48, "Reminder") for h in (out.get("reminders") or {}).get("hours") or []},
                   reverse=True)
    if any(h not in REMINDER_CHOICES for h in hours):
        raise BookingInvalid(f"Reminders can be {', '.join(str(h) for h in REMINDER_CHOICES)} hours before")
    out["reminders"] = {"hours": hours[:3]}
    out["notify_person"] = {"email": bool((out.get("notify_person") or {}).get("email"))}
    consent = out.get("consent") or {}
    out["consent"] = {"sms_text": str(consent.get("sms_text") or "").strip()[:600] or wf.DEFAULT_SMS_CONSENT,
                      "email_text": str(consent.get("email_text") or "").strip()[:600] or wf.DEFAULT_EMAIL_CONSENT}
    color = str(out.get("color") or "#0a6177")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise BookingInvalid("Colour must be a hex colour like #0a6177")
    out["color"] = color
    if out.get("status") not in ("active", "paused", "archived"):
        raise BookingInvalid("Status must be active, paused or archived")
    return out


def _question_definition(key: str, required: bool, consent: dict) -> dict:
    base = wf.FIELD_CATALOG[key]
    label = base["label"]
    if key == "consent_sms":
        label = consent.get("sms_text") or wf.DEFAULT_SMS_CONSENT
    elif key == "consent_email":
        label = consent.get("email_text") or wf.DEFAULT_EMAIL_CONSENT
    elif key == "listing_id":
        label = "MLS # (if you have it)"
    return {"key": key, "label": label, "type": base["type"], "required": bool(required),
            "options": base.get("options"), "autocomplete": base.get("autocomplete")}


# ---------------------------------------------------------------- .ics & links

def _ics_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ics_text(value: str) -> str:
    return (str(value or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """RFC 5545 line folding: at most 75 octets per line, continuation lines start with
    a space, and a multi-byte character is never split."""
    out, current, size = [], "", 0
    for char in line:
        width = len(char.encode("utf-8"))
        limit = 75 if not out else 74
        if size + width > limit:
            out.append(current)
            current, size = "", 0
        current += char
        size += width
    out.append(current)
    return "\r\n ".join(out)


def ics_document(appointment: dict, *, description: str, location: str,
                 now: Optional[datetime] = None) -> str:
    start = _parse(appointment["start_at"]) or _now()
    end = _parse(appointment.get("end_at")) or start
    booking = appointment.get("booking") or {}
    cancelled = str(appointment.get("status") or "") in CANCELLED_STATUSES
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ClientVerse//Booking//EN",
        "CALSCALE:GREGORIAN", "METHOD:" + ("CANCEL" if cancelled else "PUBLISH"),
        "BEGIN:VEVENT", f"UID:{appointment['id']}@clientverse",
        f"DTSTAMP:{_ics_time(now or _now())}", f"DTSTART:{_ics_time(start)}",
        f"DTEND:{_ics_time(end)}", f"SEQUENCE:{int(booking.get('sequence') or 0)}",
        f"SUMMARY:{_ics_text(appointment.get('title') or 'Appointment')}",
        f"DESCRIPTION:{_ics_text(description)}", f"LOCATION:{_ics_text(location)}",
        "STATUS:" + ("CANCELLED" if cancelled else "CONFIRMED"),
        "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def google_calendar_url(*, title: str, start: datetime, end: datetime, details: str,
                        location: str) -> str:
    return "https://calendar.google.com/calendar/render?" + urlencode({
        "action": "TEMPLATE", "text": title, "dates": f"{_ics_time(start)}/{_ics_time(end)}",
        "details": details, "location": location})


def when_label(value: datetime, tz_name: str, *, with_zone: bool = True) -> str:
    """'Tuesday, October 20 at 2:00 PM EDT' in the given zone, without platform strftime flags."""
    local = value.astimezone(zone(tz_name))
    hour = local.hour % 12 or 12
    meridiem = "AM" if local.hour < 12 else "PM"
    label = f"{local:%A}, {local:%B} {local.day} at {hour}:{local:%M} {meridiem}"
    return f"{label} {local.tzname()}" if with_zone else label


def time_label(value: datetime, tz_name: str) -> str:
    local = value.astimezone(zone(tz_name))
    return f"{local.hour % 12 or 12}:{local:%M} {'AM' if local.hour < 12 else 'PM'}"


def mask_email(value: Optional[str]) -> Optional[str]:
    if not value or "@" not in value:
        return value
    name, domain = value.split("@", 1)
    return f"{name[:1]}{'*' * max(2, min(6, len(name) - 1))}@{domain}"


# ------------------------------------------------------------------ embed script

EMBED_JS = r"""/* ClientVerse booking embed. Usage:
   Pop-up:  <a href="https://YOUR-CRM/book/KEY" data-clientverse-booking>Book a showing</a>
   Inline:  <div data-clientverse-booking-inline="https://YOUR-CRM/book/KEY"></div>
            <script async src="https://YOUR-CRM/api/public/booking/embed.js"></script> */
(function () {
  "use strict";
  if (window.__clientverseBooking) { window.__clientverseBooking.scan(); return; }
  function withEmbed(url) { return url + (url.indexOf("?") === -1 ? "?" : "&") + "embed=1"; }
  function frame(url, title) {
    var f = document.createElement("iframe");
    f.src = withEmbed(url); f.title = title || "Book a time"; f.setAttribute("loading", "lazy");
    f.style.cssText = "width:100%;min-height:640px;border:0;display:block;background:transparent";
    return f;
  }
  window.addEventListener("message", function (e) {
    var d = e.data || {};
    if (d.type !== "clientverse:booking:height" || !d.height) return;
    Array.prototype.forEach.call(document.querySelectorAll("iframe[data-cvb]"), function (f) {
      if (f.contentWindow === e.source) f.style.height = Math.min(4000, Math.max(480, d.height)) + "px";
    });
  });
  function open(url, title) {
    var last = document.activeElement;
    var overlay = document.createElement("div");
    overlay.setAttribute("role", "dialog"); overlay.setAttribute("aria-modal", "true"); overlay.setAttribute("aria-label", title || "Book a time");
    overlay.style.cssText = "position:fixed;inset:0;z-index:2147483000;background:rgba(15,23,42,.6);display:flex;align-items:center;justify-content:center;padding:12px";
    var box = document.createElement("div");
    box.style.cssText = "position:relative;width:min(980px,100%);height:min(860px,calc(100vh - 24px));background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 24px 60px rgba(15,23,42,.35)";
    var close = document.createElement("button");
    close.type = "button"; close.setAttribute("aria-label", "Close"); close.textContent = "\u00d7";
    close.style.cssText = "position:absolute;top:8px;right:10px;z-index:1;width:40px;height:40px;border:0;border-radius:999px;background:#f1f5f9;color:#0f172a;font-size:24px;cursor:pointer";
    var f = frame(url, title); f.setAttribute("data-cvb", "1"); f.style.height = "100%"; f.style.minHeight = "0";
    box.appendChild(close); box.appendChild(f); overlay.appendChild(box);
    function shut() { overlay.remove(); document.removeEventListener("keydown", esc); if (last && last.focus) last.focus(); }
    function esc(e) { if (e.key === "Escape") shut(); }
    close.addEventListener("click", shut);
    overlay.addEventListener("click", function (e) { if (e.target === overlay) shut(); });
    document.addEventListener("keydown", esc);
    document.body.appendChild(overlay); close.focus();
  }
  function scan() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-clientverse-booking]"), function (el) {
      if (el.getAttribute("data-cvb-ready")) return; el.setAttribute("data-cvb-ready", "1");
      el.addEventListener("click", function (e) { e.preventDefault(); open(el.getAttribute("href") || el.getAttribute("data-clientverse-booking"), el.textContent); });
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-clientverse-booking-inline]"), function (el) {
      if (el.getAttribute("data-cvb-ready")) return; el.setAttribute("data-cvb-ready", "1");
      var f = frame(el.getAttribute("data-clientverse-booking-inline")); f.setAttribute("data-cvb", "1"); el.appendChild(f);
    });
  }
  window.__clientverseBooking = { scan: scan, open: open };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", scan); else scan();
})();
"""


def frameable_csp(base_policy: str) -> str:
    """The application's own policy, except that any website may frame this page."""
    return base_policy.replace("frame-ancestors 'self'", "frame-ancestors *")


# ------------------------------------------------------------------- the service

class BookingService:
    """Everything a booking does, from the free times on a page to the reminder."""

    def __init__(self, db, *, pipeline: wf.LeadPipeline, new_id: Callable[[str], str],
                 now_iso: Callable[[], str], record_event: Callable[..., Awaitable[dict]],
                 manage_secret: bytes, public_base_url: str = "",
                 send_email: Optional[Callable[..., Awaitable[Any]]] = None,
                 email_configured: Optional[Callable[[], bool]] = None,
                 google_access_token: Optional[Callable[..., Awaitable[Optional[str]]]] = None,
                 registry: Optional[conversation_service.ProviderRegistry] = None):
        self.db = db
        self.pipeline = pipeline
        self.new_id = new_id
        self.now_iso = now_iso
        self.record_event = record_event
        self.manage_secret = manage_secret
        self.public_base_url = (public_base_url or "").rstrip("/")
        self.send_email = send_email
        self.email_configured = email_configured or (lambda: False)
        self.google_access_token = google_access_token
        self.registry = registry
        # Replaceable in tests; None means busy times come from the CRM alone.
        self.busy_fetcher: Optional[Callable[..., Awaitable[Optional[list]]]] = \
            self._google_busy if google_access_token else None
        self._busy_cache: dict[tuple, tuple[float, list]] = {}

    # ----------------------------------------------------------------- indexes

    async def ensure_indexes(self) -> None:
        db = self.db
        await db[EVENT_TYPES].create_index("public_key", unique=True)
        await db[EVENT_TYPES].create_index([("tenant_id", 1), ("status", 1)])
        await db[AVAILABILITY].create_index([("tenant_id", 1), ("user_email", 1)], unique=True)
        await db[ATTEMPTS].create_index("at", expireAfterSeconds=86400)
        await db[ATTEMPTS].create_index([("scope", 1), ("visitor", 1), ("at", -1)])
        await db[LOCKS].create_index("expires_at", expireAfterSeconds=0)
        await db[APPOINTMENTS].create_index([("tenant_id", 1), ("owner", 1), ("start_at", 1)])
        await db[APPOINTMENTS].create_index([("status", 1), ("start_at", 1)])
        # The last line of defence against a double booking: one active claim per agent
        # per start time. Cancelling or moving a booking removes its claim.
        await db[APPOINTMENTS].create_index(
            "slot_claim", unique=True, partialFilterExpression={"slot_claim": {"$type": "string"}})
        await db[APPOINTMENTS].create_index(
            "booking.manage_token_hash", unique=True,
            partialFilterExpression={"booking.manage_token_hash": {"$type": "string"}})
        await db[APPOINTMENTS].create_index(
            [("tenant_id", 1), ("booking.idempotency_key", 1)], unique=True,
            partialFilterExpression={"booking.idempotency_key": {"$type": "string"}})

    # ------------------------------------------------------------ lookups

    async def event_type_by_key(self, public_key: str, *, active_only: bool = True) -> Optional[dict]:
        if not SLUG.match(str(public_key or "")):
            return None
        query: dict[str, Any] = {"public_key": public_key}
        query["status"] = "active" if active_only else {"$ne": "archived"}
        return await self.db[EVENT_TYPES].find_one(query, {"_id": 0})

    async def tenant_timezone(self, tenant_id: str) -> str:
        prefs = await self.db.notification_prefs.find_one(
            {"tenant_id": tenant_id, "user_id": None}, {"_id": 0, "timezone": 1})
        name = (prefs or {}).get("timezone") or "UTC"
        try:
            zone(name)
        except ValueError:
            return "UTC"
        return name

    async def availability_for(self, tenant_id: str, email: str) -> dict:
        saved = await self.db[AVAILABILITY].find_one(
            {"tenant_id": tenant_id, "user_email": email.lower()}, {"_id": 0})
        if saved:
            return {**saved, "saved": True}
        return {"tenant_id": tenant_id, "user_email": email.lower(),
                "timezone": await self.tenant_timezone(tenant_id), "weekly": default_weekly(),
                "overrides": [], "saved": False}

    async def members(self, tenant_id: str) -> dict[str, dict]:
        rows = await self.db.memberships.find(
            {"tenant_id": tenant_id, "status": "active"}, {"_id": 0}).to_list(500)
        out = {}
        for row in rows:
            email = str(row.get("email") or "").lower()
            if email:
                out[email] = row
        return out

    async def names(self, emails: list[str]) -> dict[str, str]:
        wanted = sorted({e for e in emails if e})
        if not wanted:
            return {}
        rows = await self.db.users.find({"email": {"$in": wanted}},
                                        {"_id": 0, "email": 1, "name": 1}).to_list(len(wanted) + 5)
        return {str(r.get("email") or "").lower(): (r.get("name") or r.get("email")) for r in rows}

    async def active_hosts(self, event_type: dict) -> list[str]:
        members = await self.members(event_type["tenant_id"])
        return [u for u in (event_type.get("hosts") or {}).get("users") or [] if u in members]

    # ----------------------------------------------------------- busy times

    async def busy_for(self, tenant_id: str, hosts: list[str], lo: datetime, hi: datetime,
                       *, ignore_id: Optional[str] = None) -> dict[str, list[Busy]]:
        """Every host's commitments around [lo, hi): CRM appointments and, when connected,
        Google Calendar busy times. Cancelled appointments hold nothing."""
        busy: dict[str, list[Busy]] = {h: [] for h in hosts}
        if not hosts:
            return busy
        # Timestamps are compared as strings only to narrow the read; two days of padding
        # covers any offset a hand-typed appointment was written with, and the precise
        # comparison happens on parsed times below.
        rows = await self.db[APPOINTMENTS].find(
            {"tenant_id": tenant_id, "owner": {"$in": hosts},
             "status": {"$nin": list(CANCELLED_STATUSES)},
             "start_at": {"$gte": _iso(lo - timedelta(days=2)), "$lt": _iso(hi + timedelta(days=2))}},
            {"_id": 0, "id": 1, "owner": 1, "start_at": 1, "end_at": 1,
             "buffer_before_minutes": 1, "buffer_after_minutes": 1}).to_list(5000)
        for row in rows:
            if ignore_id and row.get("id") == ignore_id:
                continue
            start = _parse(row.get("start_at"))
            if not start:
                continue
            end = _parse(row.get("end_at")) or start + timedelta(minutes=30)
            owner = str(row.get("owner") or "").lower()
            if owner in busy:
                busy[owner].append((start, end, int(row.get("buffer_before_minutes") or 0),
                                    int(row.get("buffer_after_minutes") or 0)))
        if self.busy_fetcher:
            for host in hosts:
                external = await self.busy_fetcher(tenant_id, host, lo, hi)
                for start, end in external or []:
                    busy[host].append((start, end, 0, 0))
        return busy

    async def google_calendar_account(self, tenant_id: str) -> Optional[str]:
        connection = await self.db.integration_connections.find_one(
            {"tenant_id": tenant_id, "provider": "google_calendar", "status": "active"},
            {"_id": 0, "account_identity": 1})
        account = str((connection or {}).get("account_identity") or "").strip().lower()
        return account or None

    async def _google_busy(self, tenant_id: str, host: str, lo: datetime,
                           hi: datetime) -> Optional[list]:
        """Busy times on the connected Google calendar, when it is this host's calendar.

        The Google connection is one account per tenant, so it describes one agent's
        calendar -- the account that connected it -- and nobody else's. Anything that
        goes wrong (not connected, token refresh refused, Google down) returns None and
        slots fall back to the CRM's own appointments: free/busy is never guessed.
        """
        if not self.google_access_token or await self.google_calendar_account(tenant_id) != host:
            return None
        key = (tenant_id, host, _iso(lo)[:13], _iso(hi)[:13])
        cached = self._busy_cache.get(key)
        if cached and cached[0] > monotonic_clock.monotonic():
            return cached[1]
        try:
            token = await self.google_access_token(tenant_id)
            if not token:
                return None
            async with httpx.AsyncClient(timeout=6) as client:
                response = await client.post(
                    "https://www.googleapis.com/calendar/v3/freeBusy",
                    json={"timeMin": _iso(lo), "timeMax": _iso(hi), "items": [{"id": "primary"}]},
                    headers={"Authorization": f"Bearer {token}"})
            if response.status_code != 200:
                logger.warning("Google free/busy answered %s for tenant %s",
                               response.status_code, tenant_id)
                return None
            calendar = ((response.json() or {}).get("calendars") or {}).get("primary") or {}
            if calendar.get("errors"):
                return None
            busy = []
            for span in calendar.get("busy") or []:
                start, end = _parse(span.get("start")), _parse(span.get("end"))
                if start and end and end > start:
                    busy.append((start, end))
        except Exception:
            logger.warning("Google free/busy could not be read for tenant %s", tenant_id)
            return None
        if len(self._busy_cache) > 500:
            self._busy_cache.clear()
        self._busy_cache[key] = (monotonic_clock.monotonic() + BUSY_CACHE_SECONDS, busy)
        return busy

    # ----------------------------------------------------------------- slots

    async def compute_slots(self, event_type: dict, range_start: datetime, range_end: datetime,
                            *, now: Optional[datetime] = None, ignore_id: Optional[str] = None,
                            enforce_notice: bool = True,
                            hosts: Optional[list[str]] = None) -> dict[datetime, list[str]]:
        """Free start times in [range_start, range_end), each with the hosts free then."""
        now = now or _now()
        notice = timedelta(hours=float(event_type.get("min_notice_hours") or 0)) \
            if enforce_notice else timedelta(0)
        lower = max(range_start, now + notice)
        upper = min(range_end, now + timedelta(days=int(event_type.get("max_days_ahead") or 30)))
        candidates = hosts if hosts is not None else await self.active_hosts(event_type)
        if not candidates or upper <= lower:
            return {}
        busy = await self.busy_for(event_type["tenant_id"], candidates, lower - timedelta(days=1),
                                   upper + timedelta(days=1), ignore_id=ignore_id)
        result: dict[datetime, list[str]] = {}
        for host in candidates:
            availability = await self.availability_for(event_type["tenant_id"], host)
            for start in available_starts(
                    windows=host_windows(availability, lower, upper), busy=busy.get(host, []),
                    duration=int(event_type["duration_minutes"]),
                    interval=int(event_type["slot_interval_minutes"]),
                    before=int(event_type.get("buffer_before_minutes") or 0),
                    after=int(event_type.get("buffer_after_minutes") or 0),
                    lower=lower, upper=upper):
                result.setdefault(start, []).append(host)
        return dict(sorted(result.items()))

    async def slot_days(self, event_type: dict, first: date, last: date, tz_name: str, *,
                        now: Optional[datetime] = None, ignore_id: Optional[str] = None,
                        enforce_notice: bool = True) -> dict:
        """Free times for local days [first, last] in `tz_name`, grouped by local day."""
        tz = zone(tz_name)
        if last < first or (last - first).days >= MAX_RANGE_DAYS:
            raise BookingInvalid(f"Ask for at most {MAX_RANGE_DAYS} days at a time")
        range_start = datetime(first.year, first.month, first.day, tzinfo=tz).astimezone(timezone.utc)
        after_last = last + timedelta(days=1)
        range_end = datetime(after_last.year, after_last.month, after_last.day,
                             tzinfo=tz).astimezone(timezone.utc)
        slots = await self.compute_slots(event_type, range_start, range_end, now=now,
                                         ignore_id=ignore_id, enforce_notice=enforce_notice)
        days: dict[str, list[str]] = {}
        for start in slots:
            days.setdefault(start.astimezone(tz).date().isoformat(), []).append(_iso(start))
        return {"timezone": tz_name, "start": first.isoformat(), "end": last.isoformat(),
                "days": [{"date": d, "slots": s} for d, s in sorted(days.items())]}

    # ------------------------------------------------------------- locking

    @asynccontextmanager
    async def host_lock(self, tenant_id: str, host: str) -> AsyncIterator[None]:
        """Serialise every booking write for one agent.

        A unique index can only refuse two bookings that start at the same instant; it
        cannot see a 30-minute showing at 10:00 overlapping a 60-minute listing appointment
        at 10:15. Taking this lock, re-reading the agent's calendar and only then writing
        makes the overlap check and the write one step. The lock expires on its own if a
        holder dies.
        """
        key = f"{tenant_id}|{host}"
        token = secrets.token_hex(8)
        deadline = monotonic_clock.monotonic() + LOCK_WAIT_SECONDS
        while True:
            now = _now()
            try:
                await self.db[LOCKS].insert_one(
                    {"_id": key, "token": token, "expires_at": now + timedelta(seconds=LOCK_SECONDS)})
                break
            except Exception as exc:
                if not _is_duplicate_key(exc):
                    raise
                await self.db[LOCKS].delete_one({"_id": key, "expires_at": {"$lt": now}})
                if monotonic_clock.monotonic() > deadline:
                    raise SlotTaken("The calendar is busy; please try again") from exc
                await asyncio.sleep(0.03)
        try:
            yield
        finally:
            await self.db[LOCKS].delete_one({"_id": key, "token": token})

    # ------------------------------------------------------------ tokens

    def manage_token(self, appointment: dict) -> str:
        nonce = (appointment.get("booking") or {}).get("manage_nonce") or ""
        digest = hmac.new(self.manage_secret, f"booking-manage:{appointment['id']}:{nonce}".encode(),
                          hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    async def appointment_by_token(self, token: str) -> Optional[dict]:
        if not TOKEN.match(str(token or "")):
            return None
        return await self.db[APPOINTMENTS].find_one(
            {"booking.manage_token_hash": _sha(token)}, {"_id": 0})

    def links(self, appointment: dict, token: Optional[str]) -> dict:
        base = self.public_base_url
        booking = appointment.get("booking") or {}
        start = _parse(appointment["start_at"]) or _now()
        end = _parse(appointment.get("end_at")) or start
        out = {"rebook_url": f"{base}/book/{booking.get('public_key')}" if booking.get("public_key") else None,
               "google_calendar_url": google_calendar_url(
                   title=appointment.get("title") or "Appointment", start=start, end=end,
                   details=self._description(appointment, token),
                   location=self.location_text(appointment))}
        if token:
            out["manage_url"] = f"{base}/booking/manage/{token}"
            out["ics_url"] = f"{base}/api/public/booking/manage/{token}/event.ics"
        return out

    # ---------------------------------------------------------- presentation

    @staticmethod
    def location_text(appointment: dict) -> str:
        booking = appointment.get("booking") or {}
        location = booking.get("location") or {}
        person = booking.get("person") or {}
        kind = location.get("kind")
        if kind == "property":
            return (booking.get("answers") or {}).get("property_address") or location.get("text") or ""
        if kind == "phone":
            return f"Phone call to {person.get('phone')}" if person.get("phone") else "Phone call"
        return location.get("text") or LOCATION_KINDS.get(kind or "", "")

    def _description(self, appointment: dict, token: Optional[str]) -> str:
        booking = appointment.get("booking") or {}
        parts = [f"{booking.get('event_type_name') or appointment.get('title')} with "
                 f"{booking.get('host_name') or 'your agent'}"]
        where = self.location_text(appointment)
        if where:
            parts.append(f"Where: {where}")
        if token:
            parts.append(f"Reschedule or cancel: {self.public_base_url}/booking/manage/{token}")
        return "\n".join(parts)

    def public_booking(self, appointment: dict, token: Optional[str], *,
                       event_type: Optional[dict] = None) -> dict:
        """What the person who booked may see: their own booking, nothing else."""
        booking = appointment.get("booking") or {}
        start = _parse(appointment["start_at"]) or _now()
        status = str(appointment.get("status") or "")
        location = booking.get("location") or {}
        return {
            "title": booking.get("event_type_name") or appointment.get("title"),
            "start_at": appointment["start_at"], "end_at": appointment.get("end_at"),
            "duration_minutes": booking.get("duration_minutes"),
            "timezone": booking.get("timezone") or "UTC",
            "status": "cancelled" if status in CANCELLED_STATUSES else
                      "completed" if status in detectors.COMPLETED_APPOINTMENT_STATUSES else
                      "no_show" if status == "no_show" else "confirmed",
            "can_change": status in ACTIVE_STATUSES and start > _now(),
            "location": {"kind": location.get("kind"),
                         "label": LOCATION_KINDS.get(location.get("kind") or "", ""),
                         "text": self.location_text(appointment)},
            "host_name": booking.get("host_name"),
            "person": {"first_name": (booking.get("person") or {}).get("first_name"),
                       "email": mask_email((booking.get("person") or {}).get("email"))},
            "confirmation_message": (event_type or {}).get("confirmation_message")
                                    or booking.get("confirmation_message"),
            "page": {"public_key": booking.get("public_key"),
                     "name": booking.get("event_type_name"),
                     "color": (event_type or {}).get("color") or "#0a6177"},
            "cancel_reason": appointment.get("cancel_reason"),
            "links": self.links(appointment, token),
        }

    async def public_config(self, event_type: dict) -> dict:
        tenant_id = event_type["tenant_id"]
        hosts = await self.active_hosts(event_type)
        names = await self.names(hosts)
        host_name = names.get(hosts[0]) if len(hosts) == 1 else None
        tz_name = (await self.availability_for(tenant_id, hosts[0]))["timezone"] if hosts \
            else await self.tenant_timezone(tenant_id)
        location = event_type["location"]
        questions = [_question_definition(k, r, event_type.get("consent") or {})
                     for k, r in IDENTITY_FIELDS]
        questions += [_question_definition(q["key"], q["required"], event_type.get("consent") or {})
                      for q in event_type.get("questions") or []]
        return {
            "key": event_type["public_key"], "name": event_type["name"],
            "description": event_type.get("description"),
            "brand_name": event_type.get("brand_name") or host_name,
            "host_name": host_name, "team": len(hosts) > 1,
            "duration_minutes": event_type["duration_minutes"],
            "location": {"kind": location["kind"], "label": LOCATION_KINDS[location["kind"]],
                         # The office address is public; a video link is given to the
                         # person who books, not to every visitor.
                         "text": location["text"] if location["kind"] == "office" else None},
            "questions": questions, "timezone": tz_name, "color": event_type.get("color"),
            "max_days_ahead": event_type["max_days_ahead"],
            "min_notice_hours": event_type["min_notice_hours"],
            "available": bool(hosts),
        }

    # -------------------------------------------------------------- the lead

    def lead_form(self, event_type: dict, host: Optional[str]) -> dict:
        """The booking as the website-forms pipeline understands a form.

        Assignment names the host (a contact who already has an owner keeps them), the
        pipeline's call-back task and lead alert are off because a booking has its own,
        and there is no auto-reply: confirmations to the person go through approvals.
        """
        fields = [{"key": k, "required": r} for k, r in IDENTITY_FIELDS]
        fields += [{"key": q["key"], "required": q["required"]} for q in event_type.get("questions") or []]
        return wf.with_defaults({
            "id": event_type["id"], "tenant_id": event_type["tenant_id"],
            "name": event_type["name"], "form_type": "booking", "fields": fields,
            "created_by": host or event_type.get("created_by"),
            "settings": {
                "tags": ["website-lead", "booking", str(event_type.get("preset") or "booking").replace("_", "-")],
                "assignment": {"mode": "specific" if host else "unassigned",
                               "users": [host] if host else [], "keep_existing_owner": True,
                               "weights": {}},
                "opportunity": dict(event_type.get("opportunity") or {}),
                "speed_to_lead": {"task_enabled": False, "due_minutes": 5,
                                  "escalate_after_minutes": 15},
                "notify": {"in_app": False, "email": False},
                "consent": dict(event_type.get("consent") or {}),
            },
        })

    async def _run_lead(self, event_type: dict, appointment: dict, raw: dict, meta: dict) -> dict:
        """Contact, owner, deal and `lead.received`, through the website-forms pipeline."""
        tenant_id = event_type["tenant_id"]
        booking = appointment["booking"]
        start = _parse(appointment["start_at"]) or _now()
        data = {k: v for k, v in raw.items() if not str(k).startswith("_")
                and k not in ("start", "timezone", "external_id", "idempotency_key")}
        data.update({"preferred_date": start.astimezone(zone(booking["timezone"])).date().isoformat(),
                     "preferred_time": time_label(start, booking["timezone"]),
                     "external_id": f"booking:{appointment['id']}"})
        result = await self.pipeline.submit(self.lead_form(event_type, appointment["owner"]),
                                            data, {**meta, "channel": "booking"})
        enquiry = await self.db[detectors.WEB_ENQUIRIES].find_one(
            {"id": result["id"], "tenant_id": tenant_id}, {"_id": 0}) or {}
        # The person chose a time with an agent: that answers the enquiry. Recorded as
        # answered by the booking -- not as a response time, which measures people.
        await self.db[detectors.WEB_ENQUIRIES].update_one(
            {"id": result["id"], "tenant_id": tenant_id, "status": "new"},
            {"$set": {"status": "responded", "sla.first_response_at": appointment["created_at"],
                      "sla.responded_via": "booked_online", "responded_by": SYSTEM_ACTOR}})
        await self.db[detectors.WEB_ENQUIRIES].update_one(
            {"id": result["id"], "tenant_id": tenant_id},
            {"$set": {"appointment_id": appointment["id"],
                      "booking": {"event_type_id": event_type["id"],
                                  "event_type_name": event_type["name"],
                                  "start_at": appointment["start_at"],
                                  "timezone": booking["timezone"], "host": appointment["owner"]}}})
        linked = {"contact_id": result.get("contact_id") or enquiry.get("contact_id"),
                  "opportunity_id": result.get("opportunity_id") or enquiry.get("opportunity_id"),
                  "enquiry_id": result["id"]}
        await self.db[APPOINTMENTS].update_one({"id": appointment["id"], "tenant_id": tenant_id},
                                               {"$set": linked})
        return linked

    async def _prep_task(self, event_type: dict, appointment: dict) -> Optional[dict]:
        cfg = event_type.get("prep_task") or {}
        if not cfg.get("enabled") or not appointment.get("contact_id"):
            return None
        booking = appointment["booking"]
        person = booking.get("person") or {}
        start = _parse(appointment["start_at"]) or _now()
        due = max(_now(), start - timedelta(minutes=int(cfg.get("lead_minutes") or 0)))
        address = (booking.get("answers") or {}).get("property_address") or "the property"
        title = (str(cfg.get("title") or "")
                 .replace("{name}", person.get("name") or "the client")
                 .replace("{address}", address)
                 .replace("{type}", (event_type.get("name") or "the appointment").lower()))[:300]
        when = when_label(start, booking.get("host_timezone") or booking["timezone"])
        notes = [f"{event_type['name']}: {when}", f"Where: {self.location_text(appointment)}"]
        notes += [f"{wf.FIELD_CATALOG[k]['label']}: {v}" for k, v in (booking.get("answers") or {}).items()
                  if k in wf.FIELD_CATALOG and v not in (None, "", False)]
        now = self.now_iso()
        doc = {
            "id": self.new_id("task"), "tenant_id": appointment["tenant_id"], "title": title,
            "assignee": appointment["owner"], "due_date": _iso(due), "status": "todo",
            "priority": "high" if event_type.get("preset") == "home_showing" else "medium",
            "notes": "\n".join(notes)[:4000],
            # Against the contact, not the appointment: a task on the appointment is what
            # the no-show detector reads as somebody having followed up on it.
            "related_type": "contact", "related_id": appointment["contact_id"],
            "workspace_id": None, "archived_at": None, "created_at": now, "updated_at": now,
            "created_by": SYSTEM_ACTOR, "completed_at": None,
            "source": {"kind": "booking", "appointment_id": appointment["id"],
                       "enquiry_id": appointment.get("enquiry_id")},
            "history": [crm_core._history_entry("created", SYSTEM_ACTOR)],
        }
        await self.db.tasks.insert_one(dict(doc))
        await self.db[APPOINTMENTS].update_one({"id": appointment["id"], "tenant_id": appointment["tenant_id"]},
                                               {"$set": {"booking.task_id": doc["id"]}})
        await self.record_event("task.created", "task", doc["id"], appointment["tenant_id"], SYSTEM_ACTOR,
                                payload={"title": title, "assignee": appointment["owner"],
                                         "related_type": "contact", "related_id": appointment["contact_id"]})
        return doc

    # ------------------------------------------------------------- alerts

    async def _user_id(self, tenant_id: str, email: Optional[str]) -> Optional[str]:
        if not email:
            return None
        member = await self.db.memberships.find_one(
            {"tenant_id": tenant_id, "email": email, "status": "active"}, {"_id": 0, "user_id": 1})
        return (member or {}).get("user_id")

    async def alert(self, tenant_id: str, recipients: list[str], *, title: str, body: str,
                    deep_link: str, ntype: str, dedupe_key: str, severity: str = "info",
                    email: bool = True) -> None:
        """In-app to each agent, then email when the CRM can send it. Once per dedupe key."""
        if await self.db.notification_deliveries.find_one(
                {"tenant_id": tenant_id, "dedupe_key": dedupe_key}, {"_id": 1}):
            return
        for recipient in list(recipients) or [None]:
            await self.db.notifications.insert_one({
                "id": self.new_id("ntf"), "tenant_id": tenant_id,
                "user_id": await self._user_id(tenant_id, recipient), "recipient": recipient,
                "workspace_id": None, "type": ntype, "severity": severity, "category": "calendar",
                "source": "booking", "title": title[:300], "body": body[:2000],
                "deep_link": deep_link, "read": False, "created_at": self.now_iso()})
        delivery = {"id": self.new_id("ndl"), "tenant_id": tenant_id, "channel": "email",
                    "notification_type": ntype, "dedupe_key": dedupe_key, "status": "skipped",
                    "recipient": None, "attempted_at": self.now_iso(), "failure_reason": None}
        if not email:
            delivery.update(status="in_app_only")
        elif not self.send_email or not self.email_configured():
            delivery.update(status="not_configured", failure_reason="email_not_configured")
        elif recipients:
            link = f"{self.public_base_url}{deep_link}" if self.public_base_url else ""
            page = (f"<h2 style='font-family:system-ui'>{html.escape(title)}</h2>"
                    f"<p style='font-family:system-ui;white-space:pre-line'>{html.escape(body)}</p>"
                    + (f"<p><a href='{html.escape(link)}'>Open the calendar</a></p>" if link else ""))
            sent, failures = 0, []
            for address in recipients:
                try:
                    await self.send_email(address, title, page)
                    sent += 1
                except Exception as exc:
                    failures.append(str(exc)[:120])
            delivery.update(status="delivered" if sent and not failures else
                            "partial" if sent else "failed",
                            recipient=",".join(recipients)[:500],
                            failure_reason="; ".join(failures)[:500] or None)
        await self.db.notification_deliveries.insert_one(delivery)

    def _summary(self, appointment: dict, tz_name: str) -> str:
        booking = appointment.get("booking") or {}
        person = booking.get("person") or {}
        start = _parse(appointment["start_at"]) or _now()
        lines = [when_label(start, tz_name), f"Where: {self.location_text(appointment)}",
                 " · ".join(v for v in (person.get("name"), person.get("phone"), person.get("email")) if v)]
        answers = booking.get("answers") or {}
        for key in ("listing_id", "pre_approved", "timeline", "price_max", "message"):
            if answers.get(key) not in (None, "", False):
                lines.append(f"{wf.FIELD_CATALOG[key]['label']}: {answers[key]}")
        return "\n".join(lines)

    # ------------------------------------------------- messages to the person

    async def _conversation(self, appointment: dict) -> dict:
        tenant_id = appointment["tenant_id"]
        thread = f"booking:{appointment['id']}"
        existing = await conversation_service.find_conversation_by_external_thread(
            self.db, tenant_id, conversation_service.CHANNEL_EMAIL, thread)
        if existing:
            return existing
        booking = appointment["booking"]
        person = booking.get("person") or {}
        conversation = await conversation_service.create_conversation(
            self.db, tenant_id=tenant_id, channel=conversation_service.CHANNEL_EMAIL,
            actor=SYSTEM_ACTOR, subject=appointment.get("title"),
            contact_id=appointment.get("contact_id"), assignee=appointment.get("owner"),
            participants=[{"kind": conversation_service.PARTICIPANT_CONTACT,
                           "id": appointment.get("contact_id"), "address": person.get("email"),
                           "display_name": person.get("name")}],
            external_thread_id=thread)
        await conversation_service.record_consent(
            self.db, tenant_id=tenant_id, conversation_id=conversation["id"],
            state=conversation_service.CONSENT_GRANTED, actor=SYSTEM_ACTOR,
            basis=(f"This person booked '{booking.get('event_type_name')}' through the booking "
                   f"page at {appointment['created_at']} and gave this address for its "
                   "confirmation, reminders and changes."),
            source=f"appointment:{appointment['id']}")
        return conversation

    def _person_text(self, appointment: dict, kind: str, *, reason: Optional[str] = None) -> tuple[str, str]:
        booking = appointment["booking"]
        person = booking.get("person") or {}
        tz_name = booking.get("timezone") or "UTC"
        start = _parse(appointment["start_at"]) or _now()
        when = when_label(start, tz_name)
        what = booking.get("event_type_name") or "appointment"
        host = booking.get("host_name") or "your agent"
        first = wf._safe_first_name(person.get("first_name") or person.get("name"))
        token = self.manage_token(appointment)
        manage = f"{self.public_base_url}/booking/manage/{token}"
        where = self.location_text(appointment)
        if kind == "cancelled":
            subject = f"Cancelled: {what} on {when_label(start, tz_name, with_zone=False)}"
            body = (f"Hi {first},\n\nYour {what.lower()} with {host} on {when} has been cancelled."
                    + (f"\n\nReason: {reason}" if reason else "")
                    + (f"\n\nTo book a new time: {self.public_base_url}/book/{booking.get('public_key')}"
                       if booking.get("public_key") else "") + "\n")
            return subject[:300], body
        if kind.startswith("reminder_"):
            subject = f"Reminder: {what} {when_label(start, tz_name, with_zone=False)}"
            opening = f"This is a reminder of your {what.lower()} with {host} on {when}."
        elif kind == "rescheduled":
            subject = f"Moved: {what} is now {when_label(start, tz_name, with_zone=False)}"
            opening = f"Your {what.lower()} with {host} has moved to {when}."
        else:
            subject = f"Confirmed: {what} on {when_label(start, tz_name, with_zone=False)}"
            opening = (f"You're booked for a {what.lower()} with {host} on {when} "
                       f"({booking.get('duration_minutes')} minutes).")
        body = f"Hi {first},\n\n{opening}\n\n" + (f"Where: {where}\n\n" if where else "")
        if kind == "confirmation" and booking.get("confirmation_message"):
            body += f"{booking['confirmation_message']}\n\n"
        body += f"Need to change it? Reschedule or cancel here: {manage}\n"
        return subject[:300], body

    async def queue_person_message(self, appointment: dict, kind: str, *,
                                   reason: Optional[str] = None) -> dict:
        """Write one email to the person and put it in front of an admin for approval.

        Never sends. See THE EMAILS TO THE PERSON AND THE APPROVAL GATE above.
        """
        tenant_id = appointment["tenant_id"]
        booking = appointment.get("booking") or {}
        person = booking.get("person") or {}
        record: dict[str, Any] = {"kind": kind, "at": self.now_iso(), "message_id": None,
                                  "approval_id": None}
        if not booking.get("notify_person_email"):
            record.update(status="off", detail="Emails to the person are turned off for this booking page.")
        elif not person.get("email"):
            record.update(status="not_sent", detail="The person left no email address.")
        else:
            authority = (await recovery_strategy.authorized_channels(self.db, tenant_id)).get(
                conversation_service.CHANNEL_EMAIL) or {}
            if not authority.get("authorized"):
                record.update(status="not_sent",
                              detail=("Email isn't connected, so nothing was emailed. The person "
                                      "saw the booking on screen with an add-to-calendar file "
                                      "and their change link."))
            else:
                start = _parse(appointment["start_at"]) or _now()
                subject, body = self._person_text(appointment, kind, reason=reason)
                conversation = await self._conversation(appointment)
                message = await conversation_service.draft_message(
                    self.db, tenant_id=tenant_id, conversation_id=conversation["id"], body=body,
                    actor=SYSTEM_ACTOR, subject=subject, to_address=person["email"],
                    idempotency_key=f"booking:{appointment['id']}:{kind}:{appointment['start_at']}",
                    requester_kind=approval_queue.REQUESTER_SYSTEM)
                record["message_id"] = message["id"]
                if message.get("status") == conversation_service.DRAFT:
                    # A reminder or confirmation approved after the appointment starts is
                    # worthless, so the approval lapses then.
                    hours_left = int((start - _now()).total_seconds() // 3600)
                    expires = max(1, min(approval_queue.MAX_EXPIRY_HOURS, hours_left)) \
                        if kind != "cancelled" else 72
                    message = await conversation_service.request_approval(
                        self.db, tenant_id=tenant_id, message_id=message["id"], actor=SYSTEM_ACTOR,
                        risk=approval_queue.RISK_LOW, expires_in_hours=expires, registry=self.registry)
                record.update(approval_id=message.get("approval_id"), status=message.get("status"),
                              detail="Waiting for an admin to approve these exact words.")
        await self.db[APPOINTMENTS].update_one(
            {"id": appointment["id"], "tenant_id": tenant_id},
            {"$set": {f"booking.messages.{kind}": record}})
        return record

    async def supersede_messages(self, appointment: dict, actor: str) -> int:
        """Withdraw every unsent email about a time that no longer stands."""
        tenant_id = appointment["tenant_id"]
        ids = [m.get("message_id") for m in ((appointment.get("booking") or {}).get("messages") or {}).values()
               if m.get("message_id")]
        if not ids:
            return 0
        rows = await self.db[conversation_service.MESSAGES].find(
            {"tenant_id": tenant_id, "id": {"$in": ids},
             "status": {"$in": [conversation_service.DRAFT, conversation_service.PENDING_APPROVAL,
                                conversation_service.APPROVED]}}, {"_id": 0}).to_list(50)
        count = 0
        for message in rows:
            if message.get("status") == conversation_service.PENDING_APPROVAL and message.get("approval_id"):
                try:
                    await approval_queue.cancel(self.db, tenant_id=tenant_id,
                                                approval_id=message["approval_id"], actor=actor,
                                                reason="The appointment changed")
                except approval_queue.ApprovalError:
                    pass
            try:
                await conversation_service.mark_refused(
                    self.db, tenant_id=tenant_id, message_id=message["id"], actor=actor,
                    reason="superseded", detail="The appointment changed; this email no longer applies.")
                count += 1
            except conversation_service.ConversationError:
                continue
        return count

    async def deliver_approved(self, *, appointment_id: Optional[str] = None,
                               tenant_id: Optional[str] = None) -> dict:
        """Send the booking emails an admin approved, through the delivery choke point."""
        query: dict[str, Any] = {"status": conversation_service.APPROVED,
                                 "idempotency_key": {"$regex": r"^booking:"}}
        if tenant_id:
            query["tenant_id"] = tenant_id
        if appointment_id:
            query["idempotency_key"] = {"$regex": "^" + re.escape(f"booking:{appointment_id}:")}
        rows = await self.db[conversation_service.MESSAGES].find(query, {"_id": 0}).to_list(200)
        sent = refused = 0
        for message in rows:
            parts = str(message.get("idempotency_key") or "").split(":", 3)
            appointment = await self.db[APPOINTMENTS].find_one(
                {"id": parts[1] if len(parts) > 1 else "", "tenant_id": message["tenant_id"]}, {"_id": 0})
            kind = parts[2] if len(parts) > 2 else ""
            start = _parse((appointment or {}).get("start_at"))
            stale = (not appointment or (parts[3] if len(parts) > 3 else "") != appointment.get("start_at")
                     or (kind != "cancelled" and (str(appointment.get("status")) not in ACTIVE_STATUSES
                                                  or not start or start <= _now())))
            if stale:
                try:
                    await conversation_service.mark_refused(
                        self.db, tenant_id=message["tenant_id"], message_id=message["id"],
                        actor=SYSTEM_ACTOR, reason="superseded",
                        detail="The appointment changed or already started; this email no longer applies.")
                except conversation_service.ConversationError:
                    pass
                refused += 1
                continue
            try:
                await conversation_service.attempt_delivery(
                    self.db, tenant_id=message["tenant_id"], message_id=message["id"],
                    actor=SYSTEM_ACTOR, registry=self.registry)
                sent += 1
            except (conversation_service.DeliveryRefused, conversation_service.ConversationError):
                refused += 1
        return {"sent": sent, "refused": refused}

    # -------------------------------------------------------------- booking

    def _appointment_doc(self, event_type: dict, *, host: str, host_name: Optional[str],
                         host_tz: str, start: datetime, fields: dict, display_tz: str,
                         idempotency_key: Optional[str], meta: dict, actor: str) -> dict:
        duration = int(event_type["duration_minutes"])
        end = start + timedelta(minutes=duration)
        now = self.now_iso()
        answers = {k: fields.get(k) for k in QUESTION_KEYS if fields.get(k) not in (None, "")}
        person_name = fields.get("name") or " ".join(
            p for p in (fields.get("first_name"), fields.get("last_name")) if p)
        appointment_id = self.new_id("apt")
        return {
            "id": appointment_id, "tenant_id": event_type["tenant_id"],
            "title": f"{event_type['name']} — {person_name}"[:200],
            "start_at": _iso(start), "end_at": _iso(end), "owner": host,
            "workspace_id": None, "company_id": None, "contact_id": None,
            "opportunity_id": None, "enquiry_id": None,
            "appointment_type": event_type.get("preset") or "booking",
            "status": "confirmed", "notes": answers.get("message"),
            "reminder_state": "booking_reminders",
            "buffer_before_minutes": int(event_type.get("buffer_before_minutes") or 0),
            "buffer_after_minutes": int(event_type.get("buffer_after_minutes") or 0),
            "slot_claim": f"{event_type['tenant_id']}|{host}|{_iso(start)}",
            "created_by": actor, "created_at": now, "updated_at": now,
            "booking": {
                "event_type_id": event_type["id"], "event_type_name": event_type["name"],
                "preset": event_type.get("preset"), "public_key": event_type["public_key"],
                "timezone": display_tz, "host_timezone": host_tz, "host_name": host_name,
                "duration_minutes": duration,
                "location": dict(event_type["location"]),
                "person": {"name": person_name, "first_name": fields.get("first_name"),
                           "email": fields.get("email"), "phone": fields.get("phone")},
                "answers": answers,
                "confirmation_message": event_type.get("confirmation_message"),
                "manage_nonce": secrets.token_hex(16), "manage_token_hash": None,
                "idempotency_key": idempotency_key,
                "source": meta.get("channel") or "booking_page", "visitor": meta.get("visitor"),
                "reminder_hours": list((event_type.get("reminders") or {}).get("hours") or []),
                "reminders_claimed": [], "reminders": {},
                "notify_person_email": bool((event_type.get("notify_person") or {}).get("email")),
                "messages": {}, "sequence": 0, "rescheduled_count": 0,
                "history": [{"action": "booked", "actor": actor, "at": now,
                             "detail": {"start_at": _iso(start)}}],
            },
        }

    async def _host_order(self, event_type: dict, hosts: list[str], email: Optional[str]) -> list[str]:
        """Who should take this booking, best first: the contact's own agent if they are
        free, then the round-robin rotation from where it last stopped."""
        if len(hosts) <= 1:
            return list(hosts)
        order: list[str] = []
        existing = await self.pipeline._find_contact(event_type["tenant_id"], email, None) if email else None
        owner = str((existing or {}).get("owner") or "").lower()
        if owner in hosts:
            order.append(owner)
        rotation = [u for u in (event_type.get("hosts") or {}).get("users") or [] if u in hosts]
        updated = await self.db[EVENT_TYPES].find_one_and_update(
            {"id": event_type["id"]}, {"$inc": {"stats.round_robin_cursor": 1}},
            projection={"_id": 0, "stats": 1}, return_document=True)
        cursor = int(((updated or {}).get("stats") or {}).get("round_robin_cursor") or 1) - 1
        for offset in range(len(rotation)):
            host = rotation[(cursor + offset) % len(rotation)]
            if host not in order:
                order.append(host)
        return order + [h for h in hosts if h not in order]

    async def _reserve(self, event_type: dict, start: datetime, hosts: list[str], build: Callable[[str], dict],
                       *, ignore_id: Optional[str] = None) -> Optional[dict]:
        """Write the first booking that fits, one agent at a time, under that agent's lock."""
        duration = int(event_type["duration_minutes"])
        before = int(event_type.get("buffer_before_minutes") or 0)
        after = int(event_type.get("buffer_after_minutes") or 0)
        for host in hosts:
            async with self.host_lock(event_type["tenant_id"], host):
                busy = await self.busy_for(event_type["tenant_id"], [host], start - timedelta(days=1),
                                           start + timedelta(days=1), ignore_id=ignore_id)
                if conflicts(start, duration, before, after, busy.get(host, [])):
                    continue
                doc = build(host)
                try:
                    if ignore_id:
                        result = await self.db[APPOINTMENTS].update_one(
                            {"id": ignore_id, "tenant_id": event_type["tenant_id"],
                             "status": {"$in": list(ACTIVE_STATUSES)}}, doc)
                        if not result.modified_count:
                            return None
                        return await self.db[APPOINTMENTS].find_one({"id": ignore_id}, {"_id": 0})
                    await self.db[APPOINTMENTS].insert_one(dict(doc))
                    return doc
                except Exception as exc:
                    if _is_duplicate_key(exc):
                        continue
                    raise
        return None

    async def book(self, event_type: dict, *, start: datetime, raw: dict, display_tz: str,
                   meta: dict, idempotency_key: Optional[str] = None,
                   actor: str = SYSTEM_ACTOR) -> dict:
        """Book one time. Returns {appointment, token, replayed}. Raises SubmissionInvalid,
        BookingInvalid or SlotTaken."""
        tenant_id = event_type["tenant_id"]
        if idempotency_key:
            existing = await self.db[APPOINTMENTS].find_one(
                {"tenant_id": tenant_id, "booking.idempotency_key": idempotency_key}, {"_id": 0})
            if existing:
                return {"appointment": existing, "token": self.manage_token(existing), "replayed": True}
        zone(display_tz)
        normalised = wf.normalise_submission(raw, self.lead_form(event_type, None))
        fields = normalised["fields"]
        offered = await self.compute_slots(event_type, start, start + timedelta(minutes=1))
        hosts = offered.get(start) or []
        if not hosts:
            raise SlotTaken("That time is no longer available")
        order = await self._host_order(event_type, hosts, fields.get("email"))
        names = await self.names(order)
        timezones = {h: (await self.availability_for(tenant_id, h))["timezone"] for h in order}

        def build(host: str) -> dict:
            return self._appointment_doc(event_type, host=host, host_name=names.get(host),
                                         host_tz=timezones[host], start=start, fields=fields,
                                         display_tz=display_tz, idempotency_key=idempotency_key,
                                         meta=meta, actor=actor)

        try:
            appointment = await self._reserve(event_type, start, order, build)
        except SlotTaken:
            appointment = None
        if not appointment:
            if idempotency_key:
                existing = await self.db[APPOINTMENTS].find_one(
                    {"tenant_id": tenant_id, "booking.idempotency_key": idempotency_key}, {"_id": 0})
                if existing:
                    return {"appointment": existing, "token": self.manage_token(existing), "replayed": True}
            raise SlotTaken("That time was just taken")
        token = self.manage_token(appointment)
        await self.db[APPOINTMENTS].update_one(
            {"id": appointment["id"], "tenant_id": tenant_id},
            {"$set": {"booking.manage_token_hash": _sha(token)}})
        appointment["booking"]["manage_token_hash"] = _sha(token)
        await self.db[EVENT_TYPES].update_one({"id": event_type["id"]},
                                              {"$inc": {"stats.bookings": 1},
                                               "$set": {"stats.last_booking_at": appointment["created_at"]}})
        await self.record_event("appointment.booked", "appointment", appointment["id"], tenant_id, actor,
                                payload={"event_type_id": event_type["id"], "start_at": appointment["start_at"],
                                         "host": appointment["owner"], "source": meta.get("channel")})
        try:
            appointment.update(await self._run_lead(event_type, appointment, raw, meta))
        except Exception:
            # The booking stands whatever happens to the lead: losing the person's
            # appointment because a deal could not be written would be the worse failure.
            logger.exception("Lead pipeline failed for booking %s", appointment["id"])
        try:
            await self._prep_task(event_type, appointment)
        except Exception:
            logger.exception("Preparation task failed for booking %s", appointment["id"])
        await self._announce(appointment, "new", actor=actor)
        try:
            await self.queue_person_message(appointment, "confirmation")
        except Exception:
            logger.exception("Confirmation email could not be queued for %s", appointment["id"])
        return {"appointment": appointment, "token": token, "replayed": False}

    async def _announce(self, appointment: dict, what: str, *, actor: str,
                        previous_host: Optional[str] = None, reason: Optional[str] = None) -> None:
        booking = appointment.get("booking") or {}
        person = (booking.get("person") or {}).get("name") or "Someone"
        tz_name = booking.get("host_timezone") or booking.get("timezone") or "UTC"
        start = _parse(appointment["start_at"]) or _now()
        what_name = booking.get("event_type_name") or appointment.get("title") or "Appointment"
        title = {"new": f"New booking: {what_name} with {person}",
                 "rescheduled": f"Booking moved: {what_name} with {person}",
                 "cancelled": f"Booking cancelled: {what_name} with {person}"}[what]
        title += f" — {when_label(start, tz_name, with_zone=False)}"
        body = self._summary(appointment, tz_name)
        if reason:
            body += f"\nReason: {reason}"
        if actor not in (SYSTEM_ACTOR, "person"):
            body += f"\nBy {actor}"
        recipients = sorted({r for r in (appointment.get("owner"), previous_host) if r})
        await self.alert(appointment["tenant_id"], recipients, title=title, body=body,
                         deep_link=f"/scheduling/calendar?appointment={appointment['id']}",
                         ntype=f"booking.{what}", severity="warning" if what == "cancelled" else "info",
                         dedupe_key=f"booking:{appointment['id']}:{what}:{appointment['start_at']}:"
                                    f"{booking.get('sequence') or 0}")

    # ---------------------------------------------------------- changes

    async def reschedule(self, appointment: dict, *, start: datetime, actor: str,
                         enforce_notice: bool = True, notify_person: bool = True,
                         outside_hours: bool = False) -> dict:
        """Move a booking to a new free time, atomically. Raises SlotTaken/BookingInvalid."""
        tenant_id = appointment["tenant_id"]
        if str(appointment.get("status")) not in ACTIVE_STATUSES:
            raise BookingInvalid("Only an upcoming appointment can be moved")
        booking = appointment.get("booking") or {}
        event_type = await self.db[EVENT_TYPES].find_one(
            {"id": booking.get("event_type_id"), "tenant_id": tenant_id}, {"_id": 0}) if booking else None
        current = str(appointment.get("owner") or "").lower()
        if event_type and not outside_hours:
            offered = await self.compute_slots(event_type, start, start + timedelta(minutes=1),
                                               ignore_id=appointment["id"], enforce_notice=enforce_notice)
            hosts = offered.get(start) or []
            if not hosts:
                raise SlotTaken("That time is no longer available")
            order = ([current] if current in hosts else []) + [h for h in hosts if h != current]
        else:
            if start <= _now():
                raise BookingInvalid("Pick a time in the future")
            order = [current] if current else []
        old_start = _parse(appointment["start_at"]) or _now()
        old_end = _parse(appointment.get("end_at")) or old_start
        duration = int((event_type or {}).get("duration_minutes")
                       or max(5, int((old_end - old_start).total_seconds() // 60)))
        rule = event_type or {"tenant_id": tenant_id, "duration_minutes": duration,
                              "buffer_before_minutes": appointment.get("buffer_before_minutes") or 0,
                              "buffer_after_minutes": appointment.get("buffer_after_minutes") or 0}
        rule = {**rule, "duration_minutes": duration}
        names = await self.names(order)
        now = self.now_iso()

        def build(host: str) -> dict:
            sets: dict[str, Any] = {
                "start_at": _iso(start), "end_at": _iso(start + timedelta(minutes=duration)),
                "owner": host, "updated_at": now, "reminder_state": appointment.get("reminder_state")}
            if booking:
                sets.update({"slot_claim": f"{tenant_id}|{host}|{_iso(start)}",
                             "booking.host_name": names.get(host) or booking.get("host_name"),
                             "booking.reminders_claimed": [], "booking.reminders": {},
                             "booking.rescheduled_count": int(booking.get("rescheduled_count") or 0) + 1,
                             "booking.sequence": int(booking.get("sequence") or 0) + 1})
            return {"$set": sets, "$push": {"booking.history" if booking else "history": {
                "action": "rescheduled", "actor": actor, "at": now,
                "detail": {"from": appointment["start_at"], "to": _iso(start), "host": host}}}}

        updated = await self._reserve(rule, start, order, build, ignore_id=appointment["id"])
        if not updated:
            raise SlotTaken("That time was just taken")
        await self.record_event("appointment.rescheduled", "appointment", appointment["id"], tenant_id, actor,
                                payload={"from": appointment["start_at"], "to": updated["start_at"],
                                         "host": updated.get("owner")})
        if booking:
            await self.supersede_messages(appointment, actor)
            await self._announce(updated, "rescheduled", actor=actor,
                                 previous_host=current if current != updated.get("owner") else None)
            if notify_person:
                try:
                    await self.queue_person_message(updated, "rescheduled")
                except Exception:
                    logger.exception("Reschedule email could not be queued for %s", appointment["id"])
            if updated.get("enquiry_id"):
                await self.db[detectors.WEB_ENQUIRIES].update_one(
                    {"id": updated["enquiry_id"], "tenant_id": tenant_id},
                    {"$set": {"booking.start_at": updated["start_at"], "booking.host": updated.get("owner")}})
        return await self.db[APPOINTMENTS].find_one({"id": appointment["id"]}, {"_id": 0}) or updated

    async def cancel(self, appointment: dict, *, actor: str, reason: Optional[str],
                     by_person: bool, notify_person: bool = False) -> dict:
        tenant_id = appointment["tenant_id"]
        if str(appointment.get("status")) not in ACTIVE_STATUSES:
            raise BookingInvalid("This appointment is not upcoming, so it cannot be cancelled")
        now = self.now_iso()
        reason = (str(reason or "").strip()[:500]) or None
        result = await self.db[APPOINTMENTS].update_one(
            {"id": appointment["id"], "tenant_id": tenant_id, "status": {"$in": list(ACTIVE_STATUSES)}},
            {"$set": {"status": "cancelled", "cancelled_at": now, "cancelled_by": actor,
                      "cancelled_by_person": by_person, "cancel_reason": reason, "updated_at": now,
                      "booking.sequence": int((appointment.get("booking") or {}).get("sequence") or 0) + 1},
             "$unset": {"slot_claim": ""},
             "$push": {"booking.history" if appointment.get("booking") else "history": {
                 "action": "cancelled", "actor": actor, "at": now, "detail": {"reason": reason}}}})
        if not result.modified_count:
            raise BookingInvalid("This appointment changed; reload and try again")
        updated = await self.db[APPOINTMENTS].find_one({"id": appointment["id"]}, {"_id": 0}) or appointment
        await self.record_event("appointment.cancelled", "appointment", appointment["id"], tenant_id, actor,
                                payload={"by_person": by_person, "reason": reason})
        if appointment.get("booking"):
            await self.supersede_messages(appointment, actor)
            await self._announce(updated, "cancelled", actor="person" if by_person else actor, reason=reason)
            if notify_person and not by_person:
                try:
                    await self.queue_person_message(updated, "cancelled", reason=reason)
                except Exception:
                    logger.exception("Cancellation email could not be queued for %s", appointment["id"])
            task_id = (appointment.get("booking") or {}).get("task_id")
            if task_id:
                await self.db.tasks.update_one(
                    {"id": task_id, "tenant_id": tenant_id, "status": {"$nin": ["done", "cancelled"]}},
                    {"$set": {"status": "cancelled", "updated_at": now},
                     "$push": {"history": crm_core._history_entry("cancelled", actor,
                                                                  {"via": "booking_cancelled"})}})
        return await self.db[APPOINTMENTS].find_one({"id": appointment["id"]}, {"_id": 0}) or updated

    async def record_outcome(self, appointment: dict, *, outcome: str, actor: str) -> dict:
        """Attended or no-show. A no-show stays on the record exactly as the no-show
        recovery detector reads it."""
        status = OUTCOMES.get(outcome)
        if not status:
            raise BookingInvalid("Outcome must be attended or no_show")
        start = _parse(appointment.get("start_at"))
        if not start or start > _now():
            raise BookingInvalid("This appointment hasn't started yet")
        if str(appointment.get("status")) in CANCELLED_STATUSES:
            raise BookingInvalid("A cancelled appointment has no outcome")
        now = self.now_iso()
        await self.db[APPOINTMENTS].update_one(
            {"id": appointment["id"], "tenant_id": appointment["tenant_id"]},
            {"$set": {"status": status, "outcome_recorded_at": now, "outcome_recorded_by": actor,
                      "updated_at": now},
             "$unset": {"slot_claim": ""},
             "$push": {"booking.history" if appointment.get("booking") else "history": {
                 "action": outcome, "actor": actor, "at": now, "detail": {}}}})
        await self.record_event(f"appointment.{'attended' if outcome == 'attended' else 'no_show'}",
                                "appointment", appointment["id"], appointment["tenant_id"], actor,
                                payload={"status": status})
        return await self.db[APPOINTMENTS].find_one({"id": appointment["id"]}, {"_id": 0}) or appointment

    # ----------------------------------------------------------- reminders

    async def send_due_reminders(self, now: Optional[datetime] = None) -> dict:
        """Send every booking reminder that is due, each exactly once, then deliver the
        booking emails admins have approved.

        A reminder is claimed with a conditional `$addToSet` on the appointment, so two
        runs -- the API's own scheduler and the cron route, or two replicas -- cannot both
        send it. A booking made after a reminder's time skips that reminder rather than
        sending a "tomorrow" email an hour after the confirmation.
        """
        now = now or _now()
        horizon = now + timedelta(hours=max(REMINDER_CHOICES) + 1)
        rows = await self.db[APPOINTMENTS].find(
            {"status": {"$in": list(ACTIVE_STATUSES)}, "booking.reminder_hours.0": {"$exists": True},
             "start_at": {"$gte": _iso(now - timedelta(days=1)), "$lt": _iso(horizon + timedelta(days=1))}},
            {"_id": 0}).to_list(2000)
        sent = skipped = 0
        for appointment in rows:
            start = _parse(appointment.get("start_at"))
            if not start or start <= now:
                continue
            booking = appointment["booking"]
            created = _parse(appointment.get("updated_at") if booking.get("rescheduled_count")
                             else appointment.get("created_at")) or now
            for hours in booking.get("reminder_hours") or []:
                due_at = start - timedelta(hours=int(hours))
                if now < due_at:
                    continue
                key = f"{int(hours)}h"
                claimed = await self.db[APPOINTMENTS].update_one(
                    {"id": appointment["id"], "tenant_id": appointment["tenant_id"],
                     "start_at": appointment["start_at"], "status": {"$in": list(ACTIVE_STATUSES)},
                     "booking.reminders_claimed": {"$ne": key}},
                    {"$addToSet": {"booking.reminders_claimed": key}})
                if not claimed.modified_count:
                    continue  # already sent, or another run got it first
                if created > due_at:
                    skipped += 1
                    await self.db[APPOINTMENTS].update_one(
                        {"id": appointment["id"]},
                        {"$set": {f"booking.reminders.{key}": {"status": "skipped", "at": _iso(now),
                                                               "detail": "Booked after this reminder's time."}}})
                    continue
                person = await self.queue_person_message(appointment, f"reminder_{key}")
                tz_name = booking.get("host_timezone") or booking.get("timezone") or "UTC"
                who = (booking.get("person") or {}).get("name") or "your client"
                await self.alert(
                    appointment["tenant_id"], [appointment["owner"]] if appointment.get("owner") else [],
                    title=f"Coming up: {booking.get('event_type_name')} with {who} at "
                          f"{time_label(start, tz_name)} (in {int(hours)} hour{'s' if int(hours) != 1 else ''})",
                    body=self._summary(appointment, tz_name),
                    deep_link=f"/scheduling/calendar?appointment={appointment['id']}",
                    ntype="booking.reminder", dedupe_key=f"booking:{appointment['id']}:reminder:{key}:"
                                                         f"{appointment['start_at']}", email=False)
                await self.db[APPOINTMENTS].update_one(
                    {"id": appointment["id"]},
                    {"$set": {f"booking.reminders.{key}": {"status": "sent", "at": _iso(now),
                                                           "host": "in_app", "person": person.get("status")}}})
                sent += 1
        delivered = await self.deliver_approved()
        return {"reminders_sent": sent, "reminders_skipped": skipped, "emails": delivered}

    # -------------------------------------------------------- agent views

    async def present_appointments(self, rows: list[dict], user: dict) -> list[dict]:
        message_ids = [m.get("message_id") for row in rows
                       for m in ((row.get("booking") or {}).get("messages") or {}).values() if m.get("message_id")]
        messages = {}
        if message_ids:
            found = await self.db[conversation_service.MESSAGES].find(
                {"tenant_id": user["tenant_id"], "id": {"$in": message_ids}},
                {"_id": 0, "id": 1, "status": 1, "approval_id": 1, "blocked_detail": 1, "error": 1,
                 "subject": 1, "body": 1}).to_list(len(message_ids))
            messages = {m["id"]: m for m in found}
        names = await self.names([str(r.get("owner") or "") for r in rows])
        now = _now()
        out = []
        for row in rows:
            booking = row.get("booking") or {}
            start = _parse(row.get("start_at"))
            status = str(row.get("status") or "")
            mail = []
            for kind, record in (booking.get("messages") or {}).items():
                live = messages.get(record.get("message_id") or "") or {}
                mail.append({"kind": kind, "status": live.get("status") or record.get("status"),
                             "detail": live.get("blocked_detail") or live.get("error") or record.get("detail"),
                             "message_id": record.get("message_id"),
                             "approval_id": live.get("approval_id") or record.get("approval_id"),
                             "subject": live.get("subject"), "body": live.get("body"), "at": record.get("at")})
            owner = str(row.get("owner") or "").lower()
            out.append({
                "id": row["id"], "title": row.get("title"), "start_at": row.get("start_at"),
                "end_at": row.get("end_at"), "status": status, "owner": owner,
                "host_name": names.get(owner) or booking.get("host_name") or owner or None,
                "appointment_type": row.get("appointment_type"),
                "type_name": booking.get("event_type_name") or (row.get("appointment_type") or "").replace("_", " ").title(),
                "event_type_id": booking.get("event_type_id"), "source": "booking" if booking else "manual",
                "person": {k: (booking.get("person") or {}).get(k) for k in ("name", "email", "phone")},
                "location": {"kind": (booking.get("location") or {}).get("kind"),
                             "label": LOCATION_KINDS.get((booking.get("location") or {}).get("kind") or "", ""),
                             "text": self.location_text(row) if booking else None},
                "answers": booking.get("answers") or {}, "notes": row.get("notes"),
                "contact_id": row.get("contact_id"), "opportunity_id": row.get("opportunity_id"),
                "enquiry_id": row.get("enquiry_id"), "company_id": row.get("company_id"),
                "timezone": booking.get("timezone"), "cancel_reason": row.get("cancel_reason"),
                "cancelled_by_person": row.get("cancelled_by_person"),
                "needs_outcome": status in ACTIVE_STATUSES and bool(start and start <= now),
                "can_manage": user.get("role") == "admin" or owner == str(user.get("email") or "").lower(),
                "messages": mail, "reminders": booking.get("reminders") or {},
                "history": booking.get("history") or row.get("history") or [],
            })
        return out

    def present_event_type(self, event_type: dict, names: dict[str, str]) -> dict:
        base = self.public_base_url
        link = f"{base}/book/{event_type['public_key']}"
        out = {k: v for k, v in event_type.items() if k != "_id"}
        out["host_names"] = {u: names.get(u) or u for u in (event_type.get("hosts") or {}).get("users") or []}
        out["links"] = {
            "page": link,
            "inline": (f'<div data-clientverse-booking-inline="{link}"></div>\n'
                       f'<script async src="{base}/api/public/booking/embed.js"></script>'),
            "iframe": (f'<iframe src="{link}?embed=1" title="{html.escape(event_type["name"])}" '
                       'style="width:100%;min-height:760px;border:0" loading="lazy"></iframe>'),
            "popup": (f'<a href="{link}" data-clientverse-booking>{html.escape(event_type["name"])}</a>\n'
                      f'<script async src="{base}/api/public/booking/embed.js"></script>'),
        }
        return out


# ------------------------------------------------------------------- routes

class EventTypeInput(BaseModel):
    preset: Optional[str] = None
    name: Optional[str] = Field(default=None, max_length=120)
    public_key: Optional[str] = Field(default=None, max_length=80)
    description: Optional[str] = Field(default=None, max_length=2000)
    brand_name: Optional[str] = Field(default=None, max_length=120)
    duration_minutes: Optional[int] = None
    buffer_before_minutes: Optional[int] = None
    buffer_after_minutes: Optional[int] = None
    min_notice_hours: Optional[float] = None
    max_days_ahead: Optional[int] = None
    slot_interval_minutes: Optional[int] = None
    location: Optional[dict] = None
    hosts: Optional[dict] = None
    questions: Optional[list[dict]] = None
    confirmation_message: Optional[str] = Field(default=None, max_length=1000)
    opportunity: Optional[dict] = None
    prep_task: Optional[dict] = None
    reminders: Optional[dict] = None
    notify_person: Optional[dict] = None
    consent: Optional[dict] = None
    color: Optional[str] = None
    status: Optional[str] = None


class DefaultsInput(BaseModel):
    timezone: Optional[str] = Field(default=None, max_length=64)


class AvailabilityInput(BaseModel):
    timezone: str = Field(min_length=1, max_length=64)
    weekly: dict
    overrides: list[dict] = Field(default_factory=list)


class OutcomeInput(BaseModel):
    outcome: str


class CancelInput(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)
    notify_person: bool = True


class RescheduleInput(BaseModel):
    start: str = Field(min_length=10, max_length=40)
    notify_person: bool = True
    outside_hours: bool = False


EDITABLE = ("name", "public_key", "description", "brand_name", "duration_minutes",
            "buffer_before_minutes", "buffer_after_minutes", "min_notice_hours", "max_days_ahead",
            "slot_interval_minutes", "location", "hosts", "questions", "confirmation_message",
            "opportunity", "prep_task", "reminders", "notify_person", "consent", "color", "status")


def _start(value: Any) -> datetime:
    parsed = None
    text = str(value or "")
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", text):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
    if not parsed or parsed.tzinfo is None:
        raise BookingInvalid("Pick a time from the list")
    return parsed.astimezone(timezone.utc)


def register_booking_routes(router, db, *, pipeline: wf.LeadPipeline, new_id, now_iso, record_event,
                            get_current_user, require_role, manage_secret: bytes,
                            public_base_url: str = "", send_email=None, email_configured=None,
                            google_access_token=None, registry=None) -> BookingService:
    global SERVICE
    service = BookingService(db, pipeline=pipeline, new_id=new_id, now_iso=now_iso,
                             record_event=record_event, manage_secret=manage_secret,
                             public_base_url=public_base_url, send_email=send_email,
                             email_configured=email_configured,
                             google_access_token=google_access_token, registry=registry)
    SERVICE = service

    def bad(exc: Exception, status: int = 422) -> HTTPException:
        return HTTPException(status_code=status, detail=str(exc))

    async def load_event_type(event_type_id: str, user: dict) -> dict:
        doc = await db[EVENT_TYPES].find_one({"id": event_type_id, "tenant_id": user["tenant_id"],
                                              "status": {"$ne": "archived"}}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        return doc

    async def load_appointment(appointment_id: str, user: dict, *, manage: bool = False) -> dict:
        doc = await db[APPOINTMENTS].find_one({"id": appointment_id, "tenant_id": user["tenant_id"]},
                                              {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        if manage and user.get("role") != "admin" and \
                str(doc.get("owner") or "").lower() != str(user.get("email") or "").lower():
            raise HTTPException(status_code=403, detail="Only the agent hosting this appointment or an "
                                                        "admin can change it")
        return doc

    async def check_hosts(event_type: dict) -> None:
        members = await service.members(event_type["tenant_id"])
        unknown = [u for u in event_type["hosts"]["users"] if u not in members]
        if unknown:
            raise HTTPException(status_code=422, detail=f"{', '.join(unknown)} is not an active member of this team")

    async def presented(docs: list[dict]) -> list[dict]:
        names = await service.names([u for d in docs for u in (d.get("hosts") or {}).get("users") or []])
        return [service.present_event_type(d, names) for d in docs]

    # ------------------------------------------------------------- catalogue

    @router.get("/booking/catalog")
    async def booking_catalog(user=Depends(get_current_user)):
        return {
            "presets": [{"key": k, "label": v["label"], "duration_minutes": v["duration"],
                         "location": v["location"]["kind"], "description": v["description"]}
                        for k, v in PRESETS.items()],
            "questions": [{"key": k, "label": wf.FIELD_CATALOG[k]["label"],
                           "type": wf.FIELD_CATALOG[k]["type"]} for k in QUESTION_KEYS],
            "location_kinds": [{"key": k, "label": v} for k, v in LOCATION_KINDS.items()],
            "reminder_hours": list(REMINDER_CHOICES), "weekdays": list(WEEKDAYS),
            "task_merge_fields": ["{name}", "{address}", "{type}"],
        }

    @router.get("/booking/status")
    async def booking_status(user=Depends(get_current_user)):
        tenant_id = user["tenant_id"]
        email = (await recovery_strategy.authorized_channels(db, tenant_id)).get(
            conversation_service.CHANNEL_EMAIL) or {}
        waiting = await db[approval_queue.COLLECTION].count_documents(
            {"tenant_id": tenant_id, "status": approval_queue.REQUESTED,
             "kind": "communication_message", "requested_by": SYSTEM_ACTOR})
        return {"email_channel": {"authorized": bool(email.get("authorized")), "reason": email.get("reason")},
                "google_calendar": {"account": await service.google_calendar_account(tenant_id),
                                    "busy_times_checked": bool(service.busy_fetcher)},
                "emails_waiting_for_approval": waiting,
                "standing_approval": False,
                "governance": ("Each email to a person who booked needs its own admin approval. "
                               "Only the website-form auto-reply may use a standing approval (M-07)."),
                "public_base_url": service.public_base_url}

    @router.get("/booking/hosts")
    async def booking_hosts(user=Depends(get_current_user)):
        members = await service.members(user["tenant_id"])
        names = await service.names(list(members))
        items = []
        for email, member in members.items():
            availability = await service.availability_for(user["tenant_id"], email)
            items.append({"email": email, "name": names.get(email) or email, "role": member.get("role"),
                          "timezone": availability["timezone"], "availability_saved": availability["saved"]})
        return {"items": sorted(items, key=lambda i: (i["email"] != user["email"], i["name"].lower()))}

    # ----------------------------------------------------------- event types

    @router.get("/booking/event-types")
    async def list_event_types(user=Depends(get_current_user)):
        docs = await db[EVENT_TYPES].find({"tenant_id": user["tenant_id"], "status": {"$ne": "archived"}},
                                          {"_id": 0}).sort("created_at", 1).to_list(100)
        return {"items": await presented(docs)}

    @router.post("/booking/event-types")
    async def create_event_type(inp: EventTypeInput, user=Depends(require_role("admin"))):
        preset = inp.preset or "home_showing"
        if preset not in PRESETS:
            raise HTTPException(status_code=422, detail=f"preset must be one of {', '.join(PRESETS)}")
        doc = new_event_type(preset, tenant_id=user["tenant_id"], name=inp.name, creator=user["email"],
                             new_id=new_id, now=now_iso())
        for key in EDITABLE:
            value = getattr(inp, key)
            if value is not None:
                doc[key] = value
        try:
            doc = validate_event_type(doc)
        except BookingInvalid as exc:
            raise bad(exc)
        await check_hosts(doc)
        try:
            await db[EVENT_TYPES].insert_one(dict(doc))
        except Exception as exc:
            if _is_duplicate_key(exc):
                raise HTTPException(status_code=409, detail="That link name is taken; choose another")
            raise
        await record_event("booking_page.created", "booking_page", doc["id"], user["tenant_id"], user["email"],
                           payload={"name": doc["name"], "preset": preset})
        return (await presented([doc]))[0]

    @router.post("/booking/event-types/defaults")
    async def install_default_event_types(inp: DefaultsInput, user=Depends(require_role("admin"))):
        """The four real-estate booking pages, hosted by the admin, in one step."""
        tenant_id = user["tenant_id"]
        if inp.timezone:
            try:
                zone(inp.timezone)
            except ValueError as exc:
                raise bad(exc)
            if not await db[AVAILABILITY].find_one({"tenant_id": tenant_id, "user_email": user["email"].lower()}):
                await db[AVAILABILITY].insert_one({
                    "id": new_id("bav"), "tenant_id": tenant_id, "user_email": user["email"].lower(),
                    "timezone": inp.timezone, "weekly": default_weekly(), "overrides": [],
                    "updated_at": now_iso(), "updated_by": user["email"]})
        existing = {d.get("preset") for d in await db[EVENT_TYPES].find(
            {"tenant_id": tenant_id, "status": {"$ne": "archived"}}, {"_id": 0, "preset": 1}).to_list(100)}
        created = []
        for preset in DEFAULT_PRESET_ORDER:
            if preset in existing:
                continue
            doc = validate_event_type(new_event_type(
                preset, tenant_id=tenant_id, name=None, creator=user["email"], new_id=new_id, now=now_iso()))
            await db[EVENT_TYPES].insert_one(dict(doc))
            created.append(doc)
            await record_event("booking_page.created", "booking_page", doc["id"], tenant_id, user["email"],
                               payload={"name": doc["name"], "preset": preset})
        return {"created": await presented(created)}

    @router.get("/booking/event-types/{event_type_id}")
    async def get_event_type(event_type_id: str, user=Depends(get_current_user)):
        return (await presented([await load_event_type(event_type_id, user)]))[0]

    @router.patch("/booking/event-types/{event_type_id}")
    async def update_event_type(event_type_id: str, inp: EventTypeInput, user=Depends(require_role("admin"))):
        doc = await load_event_type(event_type_id, user)
        merged = dict(doc)
        for key in EDITABLE:
            value = getattr(inp, key)
            if value is not None:
                merged[key] = value
        try:
            merged = validate_event_type(merged)
        except BookingInvalid as exc:
            raise bad(exc)
        await check_hosts(merged)
        changes = {k: merged[k] for k in EDITABLE if merged.get(k) != doc.get(k)}
        changes["updated_at"] = now_iso()
        try:
            await db[EVENT_TYPES].update_one({"id": event_type_id, "tenant_id": user["tenant_id"]},
                                             {"$set": changes})
        except Exception as exc:
            if _is_duplicate_key(exc):
                raise HTTPException(status_code=409, detail="That link name is taken; choose another")
            raise
        await record_event("booking_page.updated", "booking_page", event_type_id, user["tenant_id"],
                           user["email"], payload={"changed": sorted(k for k in changes if k != "updated_at")})
        return (await presented([{**doc, **changes}]))[0]

    @router.get("/booking/event-types/{event_type_id}/slots")
    async def agent_slots(event_type_id: str, start: str, end: str, tz: str,
                          ignore: Optional[str] = None, user=Depends(get_current_user)):
        """Free times for an agent rescheduling on someone's behalf: the page's hours and
        calendar rules, without the minimum notice the public page enforces."""
        doc = await load_event_type(event_type_id, user)
        try:
            return await service.slot_days(doc, _parse_day(start), _parse_day(end), tz,
                                           ignore_id=ignore, enforce_notice=False)
        except (ValueError, BookingInvalid) as exc:
            raise bad(exc)

    # ---------------------------------------------------------- availability

    @router.get("/booking/availability")
    async def list_availability(user=Depends(get_current_user)):
        emails = list(await service.members(user["tenant_id"])) if user.get("role") == "admin" \
            else [user["email"].lower()]
        names = await service.names(emails)
        account = await service.google_calendar_account(user["tenant_id"])
        items = []
        for email in emails:
            availability = await service.availability_for(user["tenant_id"], email)
            items.append({**{k: v for k, v in availability.items() if k != "_id"},
                          "name": names.get(email) or email,
                          "google_calendar": "connected" if account == email else None})
        return {"items": items, "google_calendar_account": account}

    @router.put("/booking/availability/{email}")
    async def save_availability(email: str, inp: AvailabilityInput, user=Depends(get_current_user)):
        email = email.strip().lower()
        if user.get("role") != "admin" and email != str(user["email"]).lower():
            raise HTTPException(status_code=403, detail="You can change only your own hours")
        if email not in await service.members(user["tenant_id"]):
            raise HTTPException(status_code=404, detail="Not found")
        try:
            clean = validate_availability(inp.timezone, inp.weekly, inp.overrides)
        except ValueError as exc:
            raise bad(exc)
        await db[AVAILABILITY].update_one(
            {"tenant_id": user["tenant_id"], "user_email": email},
            {"$set": {**clean, "updated_at": now_iso(), "updated_by": user["email"]},
             "$setOnInsert": {"id": new_id("bav"), "tenant_id": user["tenant_id"], "user_email": email}},
            upsert=True)
        await record_event("booking_availability.updated", "booking_availability", email, user["tenant_id"],
                           user["email"], payload={"timezone": clean["timezone"],
                                                   "overrides": len(clean["overrides"])})
        return await service.availability_for(user["tenant_id"], email)

    # ---------------------------------------------------------- appointments

    @router.get("/booking/appointments")
    async def list_booked_appointments(start: Optional[str] = None, end: Optional[str] = None,
                                       scope: str = "all", user=Depends(get_current_user)):
        now = _now()
        lo = _parse(start) or now - timedelta(days=7)
        hi = _parse(end) or now + timedelta(days=90)
        if hi <= lo or (hi - lo).days > 400:
            raise HTTPException(status_code=422, detail="Choose a range of at most 400 days")
        query: dict[str, Any] = {"tenant_id": user["tenant_id"],
                                 "start_at": {"$gte": _iso(lo - timedelta(days=1)), "$lt": _iso(hi + timedelta(days=1))}}
        if scope == "mine":
            query["owner"] = str(user["email"]).lower()
        rows = await db[APPOINTMENTS].find(query, {"_id": 0}).sort("start_at", 1).to_list(2000)
        rows = [r for r in rows if (s := _parse(r.get("start_at"))) and lo <= s < hi]
        return {"items": await service.present_appointments(rows, user)}

    @router.get("/booking/appointments/{appointment_id}")
    async def get_booked_appointment(appointment_id: str, user=Depends(get_current_user)):
        return (await service.present_appointments([await load_appointment(appointment_id, user)], user))[0]

    @router.post("/booking/appointments/{appointment_id}/outcome")
    async def appointment_outcome(appointment_id: str, inp: OutcomeInput, user=Depends(get_current_user)):
        doc = await load_appointment(appointment_id, user, manage=True)
        try:
            updated = await service.record_outcome(doc, outcome=inp.outcome, actor=user["email"])
        except BookingInvalid as exc:
            raise bad(exc, 409)
        return (await service.present_appointments([updated], user))[0]

    @router.post("/booking/appointments/{appointment_id}/cancel")
    async def cancel_booked_appointment(appointment_id: str, inp: CancelInput, user=Depends(get_current_user)):
        doc = await load_appointment(appointment_id, user, manage=True)
        try:
            updated = await service.cancel(doc, actor=user["email"], reason=inp.reason, by_person=False,
                                           notify_person=inp.notify_person)
        except BookingInvalid as exc:
            raise bad(exc, 409)
        return (await service.present_appointments([updated], user))[0]

    @router.post("/booking/appointments/{appointment_id}/reschedule")
    async def reschedule_booked_appointment(appointment_id: str, inp: RescheduleInput,
                                            user=Depends(get_current_user)):
        doc = await load_appointment(appointment_id, user, manage=True)
        try:
            updated = await service.reschedule(doc, start=_start(inp.start), actor=user["email"],
                                               enforce_notice=False, notify_person=inp.notify_person,
                                               outside_hours=inp.outside_hours)
        except BookingInvalid as exc:
            raise bad(exc, 409)
        except SlotTaken as exc:
            raise bad(exc, 409)
        return (await service.present_appointments([updated], user))[0]

    @router.post("/booking/appointments/{appointment_id}/deliver")
    async def deliver_appointment_emails(appointment_id: str, user=Depends(get_current_user)):
        """Send this booking's approved emails now, rather than on the next sweep."""
        await load_appointment(appointment_id, user, manage=True)
        return await service.deliver_approved(appointment_id=appointment_id, tenant_id=user["tenant_id"])

    # ---------------------------------------------------------------- public

    def visitor_of(request: Request, scope: str) -> str:
        return _sha(f"{scope}|{wf.client_ip(request)}")[:32]

    async def rate_limited(scope: str, visitor: str, per_hour: int,
                           scope_per_minute: Optional[int] = None) -> int:
        now = _now()
        attempts = db[ATTEMPTS]
        if await attempts.count_documents({"scope": scope, "visitor": visitor,
                                           "at": {"$gte": now - timedelta(hours=1)}}) >= per_hour:
            return 3600
        if scope_per_minute and await attempts.count_documents(
                {"scope": scope, "at": {"$gte": now - timedelta(minutes=1)}}) >= scope_per_minute:
            return 60
        await attempts.insert_one({"scope": scope, "visitor": visitor, "at": now})
        return 0

    def too_many(seconds: int) -> JSONResponse:
        return JSONResponse(status_code=429, headers={"Retry-After": str(seconds)},
                            content={"detail": "Too many requests. Please try again shortly."})

    def public(content: dict, status: int = 200) -> JSONResponse:
        return JSONResponse(status_code=status, content=content, headers={"Cache-Control": "no-store"})

    async def public_page(public_key: str) -> dict:
        doc = await service.event_type_by_key(public_key)
        if not doc:
            # The same answer for a paused, archived, mistyped or invented page.
            raise HTTPException(status_code=404, detail="This booking page is not available")
        return doc

    async def fresh_days(event_type: dict, start: datetime, tz_name: str, *,
                         ignore_id: Optional[str] = None) -> list[dict]:
        first = start.astimezone(zone(tz_name)).date()
        try:
            return (await service.slot_days(event_type, first, first + timedelta(days=6), tz_name,
                                            ignore_id=ignore_id))["days"]
        except (ValueError, BookingInvalid):
            return []

    @router.get("/public/booking/embed.js")
    async def booking_embed_script():
        return Response(EMBED_JS, media_type="application/javascript",
                        headers={"Cache-Control": "public, max-age=300"})

    # Manage routes come first: `/public/booking/manage/...` must never be read as a page key.
    @router.get("/public/booking/manage/{token}")
    async def public_manage_view(token: str, request: Request):
        limited = await rate_limited("manage", visitor_of(request, "manage"), RATE_READ_PER_VISITOR_PER_HOUR)
        if limited:
            return too_many(limited)
        appointment = await service.appointment_by_token(token)
        if not appointment:
            raise HTTPException(status_code=404, detail="This booking link is not valid")
        event_type = await db[EVENT_TYPES].find_one({"id": (appointment.get("booking") or {}).get("event_type_id")},
                                                    {"_id": 0})
        return public(service.public_booking(appointment, token, event_type=event_type))

    @router.get("/public/booking/manage/{token}/slots")
    async def public_manage_slots(token: str, start: str, end: str, tz: str, request: Request):
        limited = await rate_limited("manage-slots", visitor_of(request, "manage"), RATE_READ_PER_VISITOR_PER_HOUR)
        if limited:
            return too_many(limited)
        appointment = await service.appointment_by_token(token)
        event_type = await db[EVENT_TYPES].find_one(
            {"id": ((appointment or {}).get("booking") or {}).get("event_type_id"), "status": {"$ne": "archived"}},
            {"_id": 0}) if appointment else None
        if not appointment or not event_type:
            raise HTTPException(status_code=404, detail="This booking link is not valid")
        try:
            return public(await service.slot_days(event_type, _parse_day(start), _parse_day(end), tz,
                                                  ignore_id=appointment["id"]))
        except (ValueError, BookingInvalid) as exc:
            raise bad(exc)

    @router.post("/public/booking/manage/{token}/reschedule")
    async def public_reschedule(token: str, request: Request):
        limited = await rate_limited("manage-write", visitor_of(request, "manage"), RATE_MANAGE_PER_VISITOR_PER_HOUR)
        if limited:
            return too_many(limited)
        data, _ = await wf.read_submission(request)
        appointment = await service.appointment_by_token(token)
        if not appointment:
            raise HTTPException(status_code=404, detail="This booking link is not valid")
        if not service.public_booking(appointment, token)["can_change"]:
            return public({"detail": "This booking can no longer be changed."}, 409)
        tz_name = str(data.get("timezone") or (appointment.get("booking") or {}).get("timezone") or "UTC")
        try:
            zone(tz_name)
            new_start = _start(data.get("start"))
            updated = await service.reschedule(appointment, start=new_start, actor="person")
        except (ValueError, BookingInvalid) as exc:
            return public({"detail": str(exc)}, 422)
        except SlotTaken:
            event_type = await db[EVENT_TYPES].find_one(
                {"id": (appointment.get("booking") or {}).get("event_type_id")}, {"_id": 0})
            days = await fresh_days(event_type, _start(data.get("start")), tz_name,
                                    ignore_id=appointment["id"]) if event_type else []
            return public({"detail": "That time was just taken. Here are the times still open.",
                           "code": "slot_taken", "days": days}, 409)
        if tz_name != (updated.get("booking") or {}).get("timezone"):
            await db[APPOINTMENTS].update_one({"id": updated["id"]}, {"$set": {"booking.timezone": tz_name}})
            updated["booking"]["timezone"] = tz_name
        return public({"accepted": True, "booking": service.public_booking(updated, token)})

    @router.post("/public/booking/manage/{token}/cancel")
    async def public_cancel(token: str, request: Request):
        limited = await rate_limited("manage-write", visitor_of(request, "manage"), RATE_MANAGE_PER_VISITOR_PER_HOUR)
        if limited:
            return too_many(limited)
        data, _ = await wf.read_submission(request)
        appointment = await service.appointment_by_token(token)
        if not appointment:
            raise HTTPException(status_code=404, detail="This booking link is not valid")
        if not service.public_booking(appointment, token)["can_change"]:
            return public({"detail": "This booking can no longer be changed."}, 409)
        try:
            updated = await service.cancel(appointment, actor="person", reason=data.get("reason"),
                                           by_person=True)
        except BookingInvalid as exc:
            return public({"detail": str(exc)}, 409)
        return public({"accepted": True, "booking": service.public_booking(updated, token)})

    @router.get("/public/booking/manage/{token}/event.ics")
    async def public_ics(token: str, request: Request):
        limited = await rate_limited("manage", visitor_of(request, "manage"), RATE_READ_PER_VISITOR_PER_HOUR)
        if limited:
            return too_many(limited)
        appointment = await service.appointment_by_token(token)
        if not appointment:
            raise HTTPException(status_code=404, detail="This booking link is not valid")
        body = ics_document(appointment, description=service._description(appointment, token),
                            location=service.location_text(appointment))
        name = slugify((appointment.get("booking") or {}).get("event_type_name") or "appointment")
        return Response(body, media_type="text/calendar; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}.ics"',
                                 "Cache-Control": "no-store"})

    @router.get("/public/booking/{public_key}/config")
    async def public_page_config(public_key: str, request: Request):
        limited = await rate_limited("read", visitor_of(request, "read"), RATE_READ_PER_VISITOR_PER_HOUR)
        if limited:
            return too_many(limited)
        doc = await public_page(public_key)
        await db[EVENT_TYPES].update_one({"id": doc["id"]}, {"$inc": {"stats.views": 1}})
        return public(await service.public_config(doc))

    @router.get("/public/booking/{public_key}/slots")
    async def public_page_slots(public_key: str, start: str, end: str, tz: str, request: Request):
        limited = await rate_limited("read", visitor_of(request, "read"), RATE_READ_PER_VISITOR_PER_HOUR)
        if limited:
            return too_many(limited)
        doc = await public_page(public_key)
        try:
            return public(await service.slot_days(doc, _parse_day(start), _parse_day(end), tz))
        except (ValueError, BookingInvalid) as exc:
            raise bad(exc)

    @router.post("/public/booking/{public_key}/book")
    async def public_book(public_key: str, request: Request):
        doc = await public_page(public_key)
        visitor = _sha(f"{doc['tenant_id']}|{wf.client_ip(request)}")[:32]
        limited = await rate_limited(f"book:{doc['id']}", visitor, RATE_BOOK_PER_VISITOR_PER_HOUR,
                                     RATE_BOOK_PER_PAGE_PER_MINUTE)
        if limited:
            return too_many(limited)
        data, _ = await wf.read_submission(request)
        tz_name = str(data.get("timezone") or "UTC")[:64]
        try:
            zone(tz_name)
            start = _start(data.get("start"))
        except (ValueError, BookingInvalid) as exc:
            return public({"detail": str(exc), "errors": {"start": str(exc)}}, 422)
        # Bots fill every field and submit at once. Answer them like a person, keep nothing.
        elapsed = wf.parse_amount(data.get("_elapsed_ms"))
        if str(data.get("_hp") or "").strip() or (elapsed is not None and elapsed < wf.MIN_FILL_MILLISECONDS):
            await db[EVENT_TYPES].update_one({"id": doc["id"]}, {"$inc": {"stats.spam_blocked": 1}})
            end = start + timedelta(minutes=int(doc["duration_minutes"]))
            return public({"accepted": True, "booking": {
                "title": doc["name"], "start_at": _iso(start), "end_at": _iso(end), "timezone": tz_name,
                "duration_minutes": doc["duration_minutes"], "status": "confirmed", "can_change": False,
                "location": {"kind": doc["location"]["kind"], "label": LOCATION_KINDS[doc["location"]["kind"]],
                             "text": None}, "host_name": None, "person": {}, "page": {"public_key": doc["public_key"]},
                "confirmation_message": doc.get("confirmation_message"), "links": {}}})
        key = wf._clip(data.get("_sid") or data.get("idempotency_key"), 200)
        meta = {"ip": wf.client_ip(request), "visitor": visitor,
                "user_agent": (request.headers.get("user-agent") or "")[:400],
                "origin": wf.normalise_origin(request.headers.get("origin")), "channel": "booking"}
        try:
            result = await service.book(doc, start=start, raw=data, display_tz=tz_name, meta=meta,
                                        idempotency_key=key)
        except wf.SubmissionInvalid as exc:
            return public({"detail": "Please check the highlighted fields.", "errors": exc.errors}, 422)
        except BookingInvalid as exc:
            return public({"detail": str(exc)}, 422)
        except SlotTaken:
            return public({"detail": "That time was just taken. Here are the times still open.",
                           "code": "slot_taken", "days": await fresh_days(doc, start, tz_name)}, 409)
        appointment = result["appointment"]
        return public({"accepted": True, "replayed": result["replayed"],
                       "booking": service.public_booking(appointment, result["token"], event_type=doc)})

    return service


SERVICE: Optional[BookingService] = None


async def send_due_reminders(db, now: Optional[datetime] = None) -> dict:
    """Entry point for a scheduler: send due booking reminders and approved booking emails.

    Uses the service the application registered (so alerts can email and messages use the
    application's provider registry); `db` must be the database it was registered with.
    """
    if SERVICE is None or SERVICE.db is not db:
        raise RuntimeError("booking routes are not registered for this database")
    return await SERVICE.send_due_reminders(now)
