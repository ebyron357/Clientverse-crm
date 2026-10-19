"""Today: one person's day, ranked, with the reason for each item.

The Today screen answers "what do I do next?" without making anyone open five pages.
`GET /api/today` reads what is already recorded -- website leads, booked appointments,
tasks, deals, approvals and client commitments -- and returns:

* `plan`: what to do next, in order. Every item carries `reason`, the recorded fact
  that put it there ("Waiting 2 h 10 min; the goal is a reply within 5 minutes"), so
  the order can be checked rather than trusted.
* the panels the screen draws: `stats`, `leads`, `appointments`, `pipeline`, `tasks`.

It changes nothing, apart from what every approvals read does: closing requests that
have lapsed, so they are not counted as waiting. Scope follows the Tasks page: a person's own tasks plus the ones
nobody owns, because an unassigned call-back is everyone's to make.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, HTTPException

import approval_queue
import crm_core
import detectors

PLAN_LIMIT = 12
LEADS_LIMIT = 10
# Leads named one by one on the plan; the rest become one "reply to N more" item, so a
# busy inbox does not push every other kind of work off the list.
PLAN_LEADS = 3
TASKS_LIMIT = 8
STALLED_AFTER_DAYS = 14
PREPARE_WITHIN = timedelta(hours=2)
OPEN_TASK = ("todo", "in_progress", "blocked")

# Higher comes first. Gaps leave room for new kinds without renumbering.
WEIGHT = {"lead": 600, "appointment": 500, "overdue_task": 400, "approval": 300,
          "commitment": 250, "due_today": 200, "stalled_deal": 100}


def _parse(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(str(value)[:10]), time())
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def waited(minutes: float) -> str:
    """"45 min", "2 h 10 min", "3 days": how long something has waited, for a reason."""
    minutes = max(0, int(minutes))
    if minutes < 60:
        return f"{minutes} min"
    if minutes < 60 * 24:
        hours, rest = divmod(minutes, 60)
        return f"{hours} h {rest} min" if rest else f"{hours} h"
    days = minutes // (60 * 24)
    return f"{days} day{'s' if days != 1 else ''}"


def _zone(tz: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(tz or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=422, detail="tz must be an IANA time zone, such as America/New_York")


def _appointment_name(row: dict) -> str:
    """The kind of appointment ("Discovery call"), not its full title, which also names
    the person ("Discovery call — Lena Fischer")."""
    if row.get("type_name"):
        return str(row["type_name"])
    title = str(row.get("title") or "Appointment")
    # An em dash, an en dash or a hyphen between spaces separates the kind from the name.
    return re.split(r"\s+[\u2014\u2013-]\s+", title, maxsplit=1)[0] or "Appointment"


def _lead_company(lead: dict, companies: dict[str, str]) -> Optional[str]:
    fields = lead.get("fields") or {}
    for key in ("company", "custom_company", "company_name"):
        if str(fields.get(key) or "").strip():
            return str(fields[key]).strip()[:120]
    return companies.get(lead.get("company_id") or "")


def _lead_topic(lead: dict) -> Optional[str]:
    fields = lead.get("fields") or {}
    for key in ("service", "custom_service", "lead_type", "interest"):
        if str(fields.get(key) or "").strip():
            return str(fields[key]).strip()[:60]
    return lead.get("lead_type")


async def build_today(db: Any, user: dict, *, tz: Optional[str] = None,
                      now: Optional[datetime] = None) -> dict:
    tenant = user["tenant_id"]
    email = str(user.get("email") or "").lower()
    is_admin = user.get("role") == "admin"
    zone = _zone(tz)
    now = now or datetime.now(timezone.utc)
    local_today = now.astimezone(zone).date()
    day_start = datetime.combine(local_today, time(), zone)
    day_end = day_start + timedelta(days=1)
    week_end = day_start + timedelta(days=7)
    # The local week the "booked this week" figure counts: Monday to Sunday.
    week_start = day_start - timedelta(days=local_today.weekday())

    companies = {c["id"]: c.get("name") or "" for c in await db[crm_core.COMPANIES].find(
        {"tenant_id": tenant}, {"_id": 0, "id": 1, "name": 1}).to_list(5000)}

    # ------------------------------------------------------------- appointments
    appointment_rows = await db.appointments.find(
        {"tenant_id": tenant, "status": {"$nin": ["cancelled", "canceled"]},
         "start_at": {"$gte": _iso(week_start - timedelta(days=1)), "$lt": _iso(week_end + timedelta(days=1))}},
        {"_id": 0}).sort("start_at", 1).to_list(1000)
    contact_ids = {a.get("contact_id") for a in appointment_rows if a.get("contact_id")}

    # ------------------------------------------------------------------- leads
    lead_rows = await db[detectors.WEB_ENQUIRIES].find(
        {"tenant_id": tenant, "status": "new", "is_test": {"$ne": True}},
        {"_id": 0, "visitor": 0, "automation": 0}).sort("received_at", 1).to_list(500)
    contact_ids |= {lead.get("contact_id") for lead in lead_rows if lead.get("contact_id")}
    contacts = {c["id"]: c for c in await db[crm_core.CONTACTS].find(
        {"tenant_id": tenant, "id": {"$in": [cid for cid in contact_ids if cid]}},
        {"_id": 0, "id": 1, "name": 1, "company_id": 1, "phone": 1, "email": 1}).to_list(2000)}

    upcoming_by_contact: dict[str, dict] = {}
    appointments = []
    booked_this_week: dict[str, int] = {}
    for row in appointment_rows:
        start = _parse(row.get("start_at"))
        if not start:
            continue
        if week_start <= start < week_start + timedelta(days=7):
            name = _appointment_name(row)
            booked_this_week[name] = booked_this_week.get(name, 0) + 1
        if not (day_start <= start < week_end):
            continue
        contact = contacts.get(row.get("contact_id") or "") or {}
        item = {"id": row["id"], "title": _appointment_name(row),
                "start_at": row.get("start_at"), "end_at": row.get("end_at"),
                "status": row.get("status"), "owner": row.get("owner"),
                "contact_id": row.get("contact_id"), "contact_name": contact.get("name"),
                "company": companies.get(contact.get("company_id") or row.get("company_id") or ""),
                "today": start < day_end}
        appointments.append(item)
        if start >= now and row.get("contact_id") and row["contact_id"] not in upcoming_by_contact:
            upcoming_by_contact[row["contact_id"]] = item

    leads = []
    for lead in lead_rows:
        contact = contacts.get(lead.get("contact_id") or "") or {}
        received = _parse(lead.get("received_at")) or now
        sla_due = _parse((lead.get("sla") or {}).get("due_at"))
        goal = int((sla_due - received).total_seconds() // 60) if sla_due else None
        leads.append({
            "id": lead["id"], "name": lead.get("name") or contact.get("name") or "Website visitor",
            "contact_id": lead.get("contact_id"), "phone": lead.get("phone") or contact.get("phone"),
            "email": lead.get("email") or contact.get("email"),
            "company": _lead_company(lead, companies), "topic": _lead_topic(lead),
            "message": (lead.get("message") or "")[:280], "form_name": lead.get("form_name"),
            "received_at": lead.get("received_at"), "waiting_minutes": int((now - received).total_seconds() // 60),
            "goal_minutes": goal, "overdue": bool(sla_due and now > sla_due),
            "existing_client": bool(lead.get("existing_client")),
            "next_appointment": upcoming_by_contact.get(lead.get("contact_id") or ""),
        })

    # ------------------------------------------------------------------- tasks
    mine = {"$or": [{"assignee": {"$regex": f"^{re.escape(email)}$", "$options": "i"}},
                    {"assignee": None}, {"assignee": ""}]}
    task_rows = await db[crm_core.TASKS].find(
        {"tenant_id": tenant, "status": {"$in": list(OPEN_TASK)}, **mine,
         "due_date": {"$ne": None, "$lt": _iso(day_end)}},
        {"_id": 0}).sort("due_date", 1).to_list(500)
    overdue = [t for t in task_rows if (_parse(t.get("due_date")) or now) < day_start]
    due_today = [t for t in task_rows if t not in overdue]

    overdue_ids = {t["id"] for t in overdue}

    def task_view(task: dict) -> dict:
        return {"id": task["id"], "title": task.get("title"), "due_date": task.get("due_date"),
                "status": task.get("status"), "priority": task.get("priority"),
                "assignee": task.get("assignee"), "related_type": task.get("related_type"),
                "related_id": task.get("related_id"), "workspace_id": task.get("workspace_id"),
                "overdue": task["id"] in overdue_ids}

    # ------------------------------------------------------------------- deals
    stages = await crm_core.resolve_stages(db, tenant)
    classes = await crm_core.stage_classes(db, tenant)
    deals = await db[crm_core.DEALS].find(
        {"tenant_id": tenant, "archived_at": None},
        {"_id": 0, "id": 1, "name": 1, "stage": 1, "value": 1, "currency": 1, "owner": 1,
         "updated_at": 1, "created_at": 1, "contact_ids": 1}).to_list(5000)
    by_stage = {s["key"]: {"key": s["key"], "label": s.get("label") or s["key"],
                           "probability": s.get("probability"), "is_closed": bool(s.get("is_closed")),
                           "is_won": bool(s.get("is_won")), "count": 0, "value_by_currency": {}}
                for s in stages}
    open_by_currency: dict[str, float] = {}
    weighted_by_currency: dict[str, float] = {}
    open_deals = []
    for deal in deals:
        try:
            amount = float(deal.get("value") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        currency = str(deal.get("currency") or "USD").upper()
        stage = by_stage.get(deal.get("stage") or "")
        if stage:
            stage["count"] += 1
            stage["value_by_currency"][currency] = round(stage["value_by_currency"].get(currency, 0.0) + amount, 2)
        if crm_core.classify_stage(deal.get("stage"), classes) == crm_core.STAGE_OPEN:
            open_deals.append(deal)
            open_by_currency[currency] = round(open_by_currency.get(currency, 0.0) + amount, 2)
            probability = (stage or {}).get("probability")
            if probability is not None:
                weighted_by_currency[currency] = round(
                    weighted_by_currency.get(currency, 0.0) + amount * float(probability) / 100, 2)

    # A deal stalls when nothing is planned and nothing has happened for a while.
    stalled = []
    if open_deals:
        open_ids = [d["id"] for d in open_deals]
        planned = {t.get("related_id") for t in await db[crm_core.TASKS].find(
            {"tenant_id": tenant, "status": {"$in": list(OPEN_TASK)}, "related_type": "deal",
             "related_id": {"$in": open_ids}}, {"_id": 0, "related_id": 1}).to_list(5000)}
        cutoff = now - timedelta(days=STALLED_AFTER_DAYS)
        recent = {a.get("related_id") for a in await db[crm_core.ACTIVITIES].find(
            {"tenant_id": tenant, "related_type": "deal", "related_id": {"$in": open_ids},
             "occurred_at": {"$gte": _iso(cutoff)}}, {"_id": 0, "related_id": 1}).to_list(10000)}
        for deal in open_deals:
            last = _parse(deal.get("updated_at") or deal.get("created_at"))
            if deal["id"] in planned or deal["id"] in recent or not last or last >= cutoff:
                continue
            if not is_admin and str(deal.get("owner") or "").lower() not in ("", email):
                continue
            stalled.append({"id": deal["id"], "name": deal.get("name"), "stage": deal.get("stage"),
                            "idle_days": (now - last).days})
        stalled.sort(key=lambda d: -d["idle_days"])

    # ------------------------------------------------------- approvals, clients
    approvals = await approval_queue.summary(db, tenant)
    waiting_decisions = int(approvals.get("awaiting_decision") or 0)
    commitments = await db.commitments.find(
        {"tenant_id": tenant, "status": {"$in": ["at_risk", "breached"]}},
        {"_id": 0, "id": 1, "title": 1, "status": 1, "due_date": 1, "workspace_id": 1}).sort(
        "due_date", 1).to_list(50)

    workspaces = {w["id"]: w.get("name") for w in await db.workspaces.find(
        {"tenant_id": tenant, "id": {"$in": list({c.get("workspace_id") for c in commitments if c.get("workspace_id")})}},
        {"_id": 0, "id": 1, "name": 1}).to_list(100)}

    # ------------------------------------------------------------------- plan
    plan: list[dict] = []
    for lead in leads[:PLAN_LEADS]:
        goal = lead["goal_minutes"]
        reason = f"Waiting {waited(lead['waiting_minutes'])}"
        if goal is not None:
            reason += f"; the goal is a reply within {waited(goal)}"
        plan.append({"kind": "lead", "id": lead["id"], "title": f"Reply to {lead['name']}",
                     "detail": lead["company"] or lead["form_name"], "reason": reason,
                     "link": f"/leads?lead={lead['id']}", "phone": lead["phone"], "email": lead["email"],
                     "score": WEIGHT["lead"] + min(lead["waiting_minutes"], 99)})
    if len(leads) > PLAN_LEADS:
        rest = leads[PLAN_LEADS:]
        plan.append({"kind": "lead", "id": "more-leads",
                     "title": f"Reply to {len(rest)} more new lead{'s' if len(rest) != 1 else ''}",
                     "detail": ", ".join(lead["name"] for lead in rest[:3]) + ("…" if len(rest) > 3 else ""),
                     "reason": f"The longest of them has waited {waited(rest[0]['waiting_minutes'])}",
                     "link": "/leads", "score": WEIGHT["lead"] - 1})
    for item in appointments:
        start = _parse(item["start_at"])
        if start and now <= start <= now + PREPARE_WITHIN:
            who = item["contact_name"] or "your next appointment"
            plan.append({"kind": "appointment", "id": item["id"], "title": f"Prepare for {item['title']} with {who}",
                         "detail": item["company"], "reason": f"Starts in {waited((start - now).total_seconds() / 60)}",
                         "link": "/scheduling/calendar", "score": WEIGHT["appointment"]})
    for task in overdue:
        due = _parse(task.get("due_date")) or now
        plan.append({"kind": "overdue_task", "id": task["id"], "title": task.get("title") or "Task",
                     "reason": f"Overdue by {waited((now - due).total_seconds() / 60)}",
                     "link": f"/tasks?task={task['id']}", "score": WEIGHT["overdue_task"] + (5 if task.get("priority") == "high" else 0)})
    if is_admin and waiting_decisions:
        plan.append({"kind": "approval", "id": "approvals",
                     "title": f"Decide {waiting_decisions} approval request{'s' if waiting_decisions != 1 else ''}",
                     "reason": "Nothing they cover is sent or changed until someone decides",
                     "link": "/operations?tab=approvals", "score": WEIGHT["approval"]})
    for commitment in commitments[:3]:
        plan.append({"kind": "commitment", "id": commitment["id"],
                     "title": f"Rescue: {commitment.get('title') or 'client commitment'}",
                     "detail": workspaces.get(commitment.get("workspace_id") or ""),
                     "reason": "Marked breached" if commitment.get("status") == "breached" else "Marked at risk",
                     "link": f"/workspaces/{commitment.get('workspace_id')}", "score": WEIGHT["commitment"]})
    for task in due_today:
        plan.append({"kind": "due_today", "id": task["id"], "title": task.get("title") or "Task",
                     "reason": "Due today", "link": f"/tasks?task={task['id']}",
                     "score": WEIGHT["due_today"] + (5 if task.get("priority") == "high" else 0)})
    for deal in stalled[:3]:
        plan.append({"kind": "stalled_deal", "id": deal["id"], "title": f"Set a next step for {deal['name']}",
                     "reason": f"No activity for {deal['idle_days']} days and no task planned",
                     "link": f"/deals?deal={deal['id']}", "score": WEIGHT["stalled_deal"] + min(deal["idle_days"], 90)})
    plan.sort(key=lambda item: -item["score"])

    oldest = leads[0]["waiting_minutes"] if leads else None
    return {
        "generated_at": _iso(now), "timezone": str(zone), "date": local_today.isoformat(),
        "user": {"name": user.get("name"), "email": email},
        "stats": {
            "leads_waiting": len(leads), "oldest_lead_minutes": oldest,
            "booked_this_week": sum(booked_this_week.values()), "booked_by_type": booked_this_week,
            "open_deals": len(open_deals), "open_by_currency": open_by_currency,
            "weighted_by_currency": weighted_by_currency,
            "approvals_waiting": waiting_decisions, "commitments_at_risk": len(commitments),
            "overdue_tasks": len(overdue), "due_today": len(due_today),
        },
        "plan": plan[:PLAN_LIMIT], "plan_total": len(plan),
        "leads": leads[:LEADS_LIMIT],
        "appointments": appointments,
        "pipeline": list(by_stage.values()),
        "tasks": [task_view(t) for t in (overdue + due_today)[:TASKS_LIMIT]],
        "commitments": [{**c, "workspace_name": workspaces.get(c.get("workspace_id") or "")} for c in commitments[:5]],
        "stalled_deals": stalled[:5],
    }


def register_today_routes(router: Any, db: Any, get_current_user: Any) -> None:

    @router.get("/today")
    async def today(tz: Optional[str] = None, user: dict = Depends(get_current_user)) -> dict:
        """The caller's day: a ranked plan with a reason per item, and the panels of the
        Today screen. `tz` is the person's IANA time zone; it decides where today ends."""
        return await build_today(db, user, tz=tz)
