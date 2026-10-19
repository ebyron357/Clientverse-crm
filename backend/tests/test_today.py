"""Today: a person's day, ranked, with the recorded reason for each item.

Leads come in through the public form door, as they do in production; deals, tasks and
approvals through the API. Each test reads `GET /api/today` and checks the order, the
reason a person is shown, and who sees what: a member sees their own tasks and the ones
nobody owns, never a colleague's, and never another tenant's anything.
"""

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ["LEAD_SLA_WATCHER"] = "0"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_today_unit")
os.environ.setdefault("JWT_SECRET", "today-unit-jwt-secret-long-enough-1234567890")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "admin@today.example")
os.environ.setdefault("ADMIN_PASSWORD", "Today-Admin-Passw0rd-1!")

from fastapi.testclient import TestClient

import detectors
import server
import today

SITE = "https://www.example-agency.example"
UTC = timezone.utc


@pytest.fixture(scope="module")
def client():
    registered = server.lead_pipeline.db
    server.db = registered
    server.mclient = getattr(registered, "client", server.mclient)
    with TestClient(server.app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _no_providers():
    server.lead_pipeline.registry = None
    yield
    server.lead_pipeline.registry = None


def call(client, fn, *args, **kwargs):
    async def _run():
        return await fn(*args, **kwargs)
    return client.portal.call(_run)


def register(client):
    email = f"owner-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post("/api/auth/register",
                           json={"email": email, "password": "Str0ng-Passw0rd!", "name": "Taylor Owner"})
    assert response.status_code == 200, response.text
    client.cookies.clear()
    body = response.json()
    return {"email": email, "tenant_id": body["user"]["tenant_id"], "user": body["user"],
            "headers": {"Authorization": f"Bearer {body['token']}"}}


def add_member(client, owner):
    email = f"member-{uuid.uuid4().hex[:8]}@example.com"
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    call(client, server.db.users.insert_one,
         {"user_id": user_id, "email": email, "name": "Morgan Member", "role": "member",
          "tenant_id": owner["tenant_id"], "password_hash": server.hash_password("Str0ng-Passw0rd!"),
          "created_at": server.now_iso()})
    call(client, server.db.memberships.insert_one,
         {"id": f"mem_{uuid.uuid4().hex[:8]}", "tenant_id": owner["tenant_id"], "user_id": user_id,
          "email": email, "role": "member", "status": "active"})
    return {"email": email, "headers": {"Authorization": f"Bearer {server.create_access_token(user_id, email)}"}}


def contact_form(client, owner):
    fields = [{"key": "first_name", "required": True}, {"key": "last_name", "required": True},
              {"key": "email", "required": True}, {"key": "phone"}, {"key": "company"},
              {"key": "message"}]
    response = client.post("/api/website-forms", headers=owner["headers"],
                           json={"name": "Contact us", "preset": "custom", "fields": fields})
    assert response.status_code == 200, response.text
    return response.json()


def submit(client, form, **data):
    payload = {"first_name": "Jordan", "last_name": "Lee", "email": f"{uuid.uuid4().hex[:6]}@brightline.example",
               "phone": "555-410-2201", "company": "Brightline Dental",
               "message": "We need a new website and local SEO.", "_sid": uuid.uuid4().hex,
               "_elapsed_ms": 9000, **data}
    response = client.post(f"/api/public/forms/{form['public_key']}/submit", content=json.dumps(payload),
                           headers={"Content-Type": "text/plain;charset=UTF-8", "Origin": SITE})
    assert response.status_code == 200, response.text
    return call(client, server.db[detectors.WEB_ENQUIRIES].find_one, {"id": response.json()["id"]}, {"_id": 0})


def age(client, collection, record_id, **fields):
    call(client, server.db[collection].update_one, {"id": record_id}, {"$set": fields})


def ago(**delta):
    return (datetime.now(UTC) - timedelta(**delta)).isoformat()


def ahead(**delta):
    return (datetime.now(UTC) + timedelta(**delta)).isoformat()


def get_today(client, who, **params):
    response = client.get("/api/today", params=params, headers=who["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def task(client, who, **body):
    response = client.post("/api/crm/tasks", headers=who["headers"], json={"title": "Follow up", **body})
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- tests

def test_new_leads_come_first_oldest_first_with_the_wait_as_the_reason(client):
    owner = register(client)
    form = contact_form(client, owner)
    older = submit(client, form, first_name="Amara", last_name="Osei", company="Osei Fitness")
    newer = submit(client, form, first_name="Ben", last_name="Carter", company="Carter Plumbing")
    age(client, detectors.WEB_ENQUIRIES, older["id"], received_at=ago(hours=2, minutes=10))
    day = get_today(client, owner)
    assert [lead["name"] for lead in day["leads"]] == ["Amara Osei", "Ben Carter"]
    assert day["leads"][0]["company"] == "Osei Fitness"
    assert day["leads"][0]["message"].startswith("We need a new website")
    assert day["stats"]["leads_waiting"] == 2 and day["stats"]["oldest_lead_minutes"] >= 130
    first = day["plan"][0]
    assert first["kind"] == "lead" and first["title"] == "Reply to Amara Osei"
    assert first["reason"].startswith("Waiting 2 h 10 min") and "the goal is a reply within" in first["reason"]
    assert first["link"] == f"/leads?lead={older['id']}"
    # Contacted leads and test submissions are not waiting on anyone.
    assert client.patch(f"/api/leads/{newer['id']}", headers=owner["headers"], json={"status": "responded"}).status_code == 200
    trial = submit(client, form, first_name="Test", last_name="Lead")
    age(client, detectors.WEB_ENQUIRIES, trial["id"], is_test=True)
    assert [lead["name"] for lead in get_today(client, owner)["leads"]] == ["Amara Osei"]


def test_a_busy_inbox_names_three_leads_and_sums_up_the_rest(client):
    owner = register(client)
    form = contact_form(client, owner)
    names = ["Ana Ruiz", "Ben Cho", "Cleo Park", "Dev Shah", "Eli Moss"]
    for minutes, name in zip((50, 40, 30, 20, 10), names, strict=True):
        first, last = name.split()
        lead = submit(client, form, first_name=first, last_name=last)
        age(client, detectors.WEB_ENQUIRIES, lead["id"], received_at=ago(minutes=minutes))
    task(client, owner, title="Send the proposal", assignee=owner["email"], due_date=ago(days=1))
    plan = get_today(client, owner)["plan"]
    assert [item["title"] for item in plan[:4]] == [
        "Reply to Ana Ruiz", "Reply to Ben Cho", "Reply to Cleo Park", "Reply to 2 more new leads"]
    assert plan[3]["detail"] == "Dev Shah, Eli Moss" and plan[3]["reason"].startswith("The longest of them has waited 20 min")
    assert plan[4]["title"] == "Send the proposal"


def test_an_appointment_is_called_by_its_kind_not_its_full_title():
    assert today._appointment_name({"type_name": "Discovery call", "title": "Discovery call — Lena"}) == "Discovery call"
    assert today._appointment_name({"title": "Quick call — Jordan Lee"}) == "Quick call"
    assert today._appointment_name({"title": "Site visit"}) == "Site visit"
    assert today._appointment_name({}) == "Appointment"


def test_tasks_are_mine_or_nobodys_and_overdue_ranks_above_due_today(client):
    owner = register(client)
    member = add_member(client, owner)
    late = task(client, owner, title="Send the proposal", assignee=owner["email"], due_date=ago(days=2))
    task(client, owner, title="Call back about pricing", assignee=None, due_date=ahead(minutes=30))
    task(client, owner, title="Morgan's call", assignee=member["email"], due_date=ago(days=1))
    done = task(client, owner, title="Already done", assignee=owner["email"], due_date=ago(days=3))
    client.patch(f"/api/crm/tasks/{done['id']}", headers=owner["headers"], json={"status": "done"})
    task(client, owner, title="Next week", assignee=owner["email"], due_date=ahead(days=8))
    day = get_today(client, owner, tz="UTC")
    titles = [item["title"] for item in day["plan"]]
    assert "Send the proposal" in titles and "Morgan's call" not in titles and "Already done" not in titles
    assert "Next week" not in titles
    overdue = next(item for item in day["plan"] if item["title"] == "Send the proposal")
    assert overdue["kind"] == "overdue_task" and overdue["reason"].startswith("Overdue by 2 days")
    assert overdue["link"] == f"/tasks?task={late['id']}"
    assert day["stats"]["overdue_tasks"] == 1
    # The member sees their own overdue call and the unassigned one, not the owner's.
    member_titles = [item["title"] for item in get_today(client, member, tz="UTC")["plan"]]
    assert "Morgan's call" in member_titles and "Send the proposal" not in member_titles


def test_today_ends_where_the_persons_day_ends(client):
    owner = register(client)
    # 22:30 in New York on 19 October is 02:30 UTC on the 20th.
    now = datetime(2026, 10, 20, 2, 30, tzinfo=UTC)
    task(client, owner, title="Due later tonight in New York", assignee=owner["email"],
         due_date=datetime(2026, 10, 20, 3, 30, tzinfo=UTC).isoformat())
    task(client, owner, title="Due tomorrow in New York", assignee=owner["email"],
         due_date=datetime(2026, 10, 20, 15, 0, tzinfo=UTC).isoformat())
    user = {"tenant_id": owner["tenant_id"], "email": owner["email"], "role": "admin", "name": "Taylor"}
    ny = call(client, today.build_today, server.db, user, tz="America/New_York", now=now)
    assert ny["date"] == "2026-10-19"
    assert [t["title"] for t in ny["tasks"]] == ["Due later tonight in New York"]
    utc = call(client, today.build_today, server.db, user, tz="UTC", now=now)
    assert utc["date"] == "2026-10-20"
    assert sorted(t["title"] for t in utc["tasks"]) == ["Due later tonight in New York", "Due tomorrow in New York"]
    assert client.get("/api/today", params={"tz": "Mars/Olympus"}, headers=owner["headers"]).status_code == 422


def test_a_task_due_earlier_today_is_overdue_not_due_today(client):
    owner = register(client)
    noon = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
    task(client, owner, title="9 am call-back", assignee=owner["email"], due_date=datetime(2026, 10, 19, 9, 0, tzinfo=UTC).isoformat())
    task(client, owner, title="5 pm call-back", assignee=owner["email"], due_date=datetime(2026, 10, 19, 17, 0, tzinfo=UTC).isoformat())
    user = {"tenant_id": owner["tenant_id"], "email": owner["email"], "role": "admin", "name": "Taylor"}
    day = call(client, today.build_today, server.db, user, tz="UTC", now=noon)
    kinds = {item["title"]: item["kind"] for item in day["plan"]}
    assert kinds == {"9 am call-back": "overdue_task", "5 pm call-back": "due_today"}
    assert day["stats"]["overdue_tasks"] == 1 and day["stats"]["due_today"] == 1
    assert [t["overdue"] for t in day["tasks"]] == [True, False]


def test_an_appointment_soon_says_prepare_and_shows_on_the_lead(client):
    owner = register(client)
    form = contact_form(client, owner)
    lead = submit(client, form, first_name="Lena", last_name="Fischer", company="Fischer Legal")
    call(client, server.db.appointments.insert_one,
         {"id": f"apt_{uuid.uuid4().hex[:8]}", "tenant_id": owner["tenant_id"], "contact_id": lead["contact_id"],
          "type_name": "Discovery call", "title": "Discovery call — Lena Fischer", "status": "confirmed",
          "owner": owner["email"], "start_at": ahead(minutes=50), "end_at": ahead(minutes=80)})
    call(client, server.db.appointments.insert_one,
         {"id": f"apt_{uuid.uuid4().hex[:8]}", "tenant_id": owner["tenant_id"], "contact_id": lead["contact_id"],
          "type_name": "Cancelled call", "status": "cancelled", "owner": owner["email"],
          "start_at": ahead(minutes=30), "end_at": ahead(minutes=45)})
    day = get_today(client, owner)
    prepare = next(item for item in day["plan"] if item["kind"] == "appointment")
    assert prepare["title"] == "Prepare for Discovery call with Lena Fischer"
    assert prepare["reason"].startswith("Starts in 4")  # 49 or 50 minutes, depending on the clock
    assert [a["title"] for a in day["appointments"]] == ["Discovery call"]
    assert day["leads"][0]["next_appointment"]["title"] == "Discovery call"
    # A lead waiting outranks preparing for a call; preparing outranks old tasks.
    assert [item["kind"] for item in day["plan"]][:2] == ["lead", "appointment"]


def test_pipeline_counts_stages_and_weights_open_value_by_probability(client):
    owner = register(client)
    headers = owner["headers"]
    for name, value, stage in (("Website rebuild", 10000, "proposal"), ("SEO retainer", 4000, "lead"),
                               ("Signed", 7000, "closed_won")):
        deal = client.post("/api/opportunities", headers=headers, json={"name": name, "value": value}).json()
        if stage != "lead":
            assert client.patch(f"/api/opportunities/{deal['id']}/stage", headers=headers, json={"stage": stage}).status_code == 200
    day = get_today(client, owner)
    stages = {s["key"]: s for s in day["pipeline"]}
    assert stages["proposal"]["count"] == 1 and stages["proposal"]["value_by_currency"] == {"USD": 10000.0}
    assert stages["closed_won"]["count"] == 1
    assert day["stats"]["open_deals"] == 2
    assert day["stats"]["open_by_currency"] == {"USD": 14000.0}
    # 10,000 at 50% plus 4,000 at 10%.
    assert day["stats"]["weighted_by_currency"] == {"USD": 5400.0}


def test_a_deal_with_nothing_planned_or_done_for_two_weeks_asks_for_a_next_step(client):
    owner = register(client)
    headers = owner["headers"]
    quiet = client.post("/api/opportunities", headers=headers, json={"name": "Quiet deal", "value": 100}).json()
    planned = client.post("/api/opportunities", headers=headers, json={"name": "Planned deal", "value": 100}).json()
    fresh = client.post("/api/opportunities", headers=headers, json={"name": "Fresh deal", "value": 100}).json()
    for deal in (quiet, planned):
        age(client, "opportunities", deal["id"], updated_at=ago(days=21), created_at=ago(days=30))
    task(client, owner, title="Send revised quote", related_type="deal", related_id=planned["id"], due_date=ahead(days=3))
    day = get_today(client, owner)
    stalled = [item for item in day["plan"] if item["kind"] == "stalled_deal"]
    assert [item["title"] for item in stalled] == ["Set a next step for Quiet deal"]
    assert stalled[0]["reason"] == "No activity for 21 days and no task planned"
    assert fresh["id"] not in [d["id"] for d in day["stalled_deals"]]


def test_approvals_are_on_an_admins_plan_and_not_a_members(client):
    owner = register(client)
    member = add_member(client, owner)
    response = client.post("/api/approval-queue", headers=owner["headers"],
                           json={"title": "Send the renewal email", "kind": "external_effect"})
    assert response.status_code == 200, response.text
    admin_plan = get_today(client, owner)["plan"]
    assert any(item["kind"] == "approval" and item["title"] == "Decide 1 approval request" for item in admin_plan)
    assert not any(item["kind"] == "approval" for item in get_today(client, member)["plan"])


def test_nothing_from_another_tenant_reaches_today(client):
    owner = register(client)
    stranger = register(client)
    submit(client, contact_form(client, stranger), first_name="Secret", last_name="Lead")
    task(client, stranger, title="Their overdue task", assignee=None, due_date=ago(days=1))
    client.post("/api/opportunities", headers=stranger["headers"], json={"name": "Their deal", "value": 999})
    day = get_today(client, owner)
    assert day["leads"] == [] and day["tasks"] == [] and day["plan"] == []
    assert day["stats"]["open_deals"] == 0


def test_waited_reads_like_a_person_would_say_it():
    assert today.waited(4) == "4 min"
    assert today.waited(60) == "1 h"
    assert today.waited(130) == "2 h 10 min"
    assert today.waited(60 * 24 * 3 + 5) == "3 days"
    assert today.waited(-5) == "0 min"
