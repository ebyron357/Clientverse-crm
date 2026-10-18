"""The API behind the Tasks page.

The "call this lead within 5 minutes" task used to be invisible: website call-back tasks
have no workspace, the only on-screen task list was a workspace tab, the assignment
notice linked to a page that did not exist and told every user in the organisation that
a task was theirs. These tests hold the backend to what the page needs: "my" tasks (with
the unowned ones beside them), due windows for the Overdue / Today / Upcoming / Done tabs,
what each task is about, the lead's response clock moving the moment its call-back task
is ticked off -- and un-ticked -- and an assignment notice that reaches only the assignee.

Runs in-process against the real `app`, like the website-form tests.
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
os.environ["LEAD_SLA_WATCHER"] = "0"  # sweeps are driven explicitly below
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_tasks_page_unit")
os.environ.setdefault("JWT_SECRET", "tasks-page-unit-jwt-secret-that-is-long-enough-1")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "admin@tasks-page.example")
os.environ.setdefault("ADMIN_PASSWORD", "Tasks-Page-Admin-1!")

from fastapi.testclient import TestClient

import detectors
import server

SITE = "https://www.agent-homes.example"
OPEN = "todo,in_progress,blocked"


@pytest.fixture(scope="module")
def client():
    # Same reasoning as the website-form tests: route modules hold the database they were
    # registered with, so point the globals back at it and stay on one event loop.
    registered = server.lead_pipeline.db
    server.db = registered
    server.mclient = getattr(registered, "client", server.mclient)
    with TestClient(server.app) as test_client:
        yield test_client


def call(client, fn, *args, **kwargs):
    async def _run():
        return await fn(*args, **kwargs)
    return client.portal.call(_run)


def find_one(client, collection, query):
    return call(client, server.db[collection].find_one, query, {"_id": 0})


def find_all(client, collection, query):
    async def _run():
        return await server.db[collection].find(query, {"_id": 0}).to_list(1000)
    return client.portal.call(_run)


def register(client, name="Agent"):
    email = f"agent-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post("/api/auth/register",
                           json={"email": email, "password": "Str0ng-Passw0rd!", "name": name})
    assert response.status_code == 200, response.text
    client.cookies.clear()
    body = response.json()
    return {"email": email, "tenant_id": body["user"]["tenant_id"],
            "user_id": body["user"]["user_id"],
            "headers": {"Authorization": f"Bearer {body['token']}"}}


def join(client, owner, role="member", name="Colleague"):
    """A second real user in the owner's team -- what accepting an invitation leaves."""
    person = register(client, name)
    call(client, server.db.users.update_one, {"user_id": person["user_id"]},
         {"$set": {"tenant_id": owner["tenant_id"], "role": role}})
    call(client, server.db.memberships.insert_one,
         {"id": f"mem_{uuid.uuid4().hex[:8]}", "tenant_id": owner["tenant_id"],
          "user_id": person["user_id"], "email": person["email"], "role": role,
          "status": "active"})
    person["tenant_id"] = owner["tenant_id"]
    return person


def iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat()


def new_task(client, who, **body):
    response = client.post("/api/crm/tasks", headers=who["headers"],
                           json={"title": f"Task {uuid.uuid4().hex[:6]}", **body})
    assert response.status_code == 200, response.text
    return response.json()


def tasks(client, who, **params):
    response = client.get("/api/tasks", headers=who["headers"], params=params)
    assert response.status_code == 200, response.text
    return response.json()


def ids(page):
    return {item["id"] for item in page["items"]}


def submit_lead(client, owner, assign_to=None):
    form = client.post("/api/website-forms", headers=owner["headers"], json={
        "name": "Showing form", "preset": "showing_request",
        "settings": {"assignment": {"mode": "specific", "users": [assign_to or owner["email"]]}},
    })
    assert form.status_code == 200, form.text
    data = {"first_name": "Jane", "last_name": "Buyer", "email": "jane.buyer@example.com",
            "phone": "(555) 010-0100", "property_address": "12 Oak St",
            "preferred_date": "2030-05-01", "preferred_time": "Morning",
            "_sid": uuid.uuid4().hex, "_elapsed_ms": 9000}
    response = client.post(f"/api/public/forms/{form.json()['public_key']}/submit",
                           content=json.dumps(data),
                           headers={"Content-Type": "text/plain;charset=UTF-8", "Origin": SITE})
    assert response.status_code == 200, response.text
    return find_one(client, detectors.WEB_ENQUIRIES, {"id": response.json()["id"]})


# --------------------------------------------------------------- the list itself

def test_my_tasks_are_mine_with_the_unowned_ones_beside_them(client):
    owner = register(client)
    colleague = join(client, owner)
    shouted = new_task(client, owner, assignee=owner["email"].upper())
    theirs = new_task(client, owner, assignee=colleague["email"])
    nobodys = new_task(client, owner)

    assert ids(tasks(client, owner, mine="true")) == {shouted["id"]}, (
        "an address typed in another case is still the same person")
    assert ids(tasks(client, owner, mine="true", include_unassigned="true")) == {
        shouted["id"], nobodys["id"]}
    assert ids(tasks(client, colleague, mine="true")) == {theirs["id"]}
    assert ids(tasks(client, owner)) >= {shouted["id"], theirs["id"], nobodys["id"]}


def test_the_tabs_read_their_own_due_windows(client):
    owner = register(client)
    me = owner["email"]
    overdue = new_task(client, owner, assignee=me, due_date=iso(-timedelta(hours=2)))
    soon = new_task(client, owner, assignee=me, due_date=iso(timedelta(minutes=10)))
    later = new_task(client, owner, assignee=me, due_date=iso(timedelta(days=3)))
    undated = new_task(client, owner, assignee=me)
    finished = new_task(client, owner, assignee=me, due_date=iso(-timedelta(hours=1)))
    client.patch(f"/api/crm/tasks/{finished['id']}", headers=owner["headers"],
                 json={"status": "done"})
    now, end_of_day = iso(timedelta(0)), iso(timedelta(hours=1))

    page = tasks(client, owner, mine="true", status=OPEN, due_before=now)
    assert ids(page) == {overdue["id"]} and page["total"] == 1, (
        "a finished task is never overdue")
    assert ids(tasks(client, owner, mine="true", status=OPEN, due_after=now,
                     due_before=end_of_day)) == {soon["id"]}
    upcoming = tasks(client, owner, mine="true", status=OPEN, due_after=end_of_day,
                     include_undated="true")
    assert ids(upcoming) == {later["id"], undated["id"]}
    done = tasks(client, owner, mine="true", status="done",
                 completed_after=iso(-timedelta(days=7)), sort="completed_at", order="desc")
    assert ids(done) == {finished["id"]} and done["items"][0]["completed_at"]


def test_each_task_says_what_it_is_about_and_who_to_call(client):
    owner = register(client)
    contact = client.post("/api/contacts", headers=owner["headers"],
                          json={"name": "Sam Seller"}).json()
    client.patch(f"/api/contacts/{contact['id']}", headers=owner["headers"],
                 json={"phone": "555-0101"})
    deal = client.post("/api/opportunities", headers=owner["headers"],
                       json={"name": "12 Oak St listing", "value": 9000,
                             "contact_ids": [contact["id"]]}).json()
    about_contact = new_task(client, owner, related_type="contact", related_id=contact["id"])
    about_deal = new_task(client, owner, related_type="deal", related_id=deal["id"])
    lead = submit_lead(client, owner)

    page = tasks(client, owner, expand="related", limit=50)
    by_id = {item["id"]: item["related"] for item in page["items"]}
    assert by_id[about_contact["id"]]["name"] == "Sam Seller"
    assert by_id[about_contact["id"]]["contact"]["phone"] == "555-0101"
    assert by_id[about_deal["id"]]["name"] == "12 Oak St listing"
    assert by_id[about_deal["id"]]["contact"]["id"] == contact["id"], (
        "the person to call about a deal is its contact")
    call_back = by_id[lead["task_id"]]
    assert call_back["lead_id"] == lead["id"]
    assert call_back["contact"]["phone"] == "(555) 010-0100"

    single = client.get(f"/api/crm/tasks/{lead['task_id']}", headers=owner["headers"])
    assert single.status_code == 200 and single.json()["related"]["lead_id"] == lead["id"]
    # Without the expansion the shape is what every existing caller already reads.
    assert "related" not in tasks(client, owner)["items"][0]


def test_tasks_and_what_they_point_at_stay_inside_the_tenant(client):
    owner, other = register(client), register(client)
    secret = client.post("/api/contacts", headers=other["headers"],
                         json={"name": "Other Tenant Person"}).json()
    client.patch(f"/api/contacts/{secret['id']}", headers=other["headers"],
                 json={"phone": "555-0199"})
    theirs = new_task(client, other, assignee=other["email"])
    # A reference that should never exist, written straight to the database: the
    # expansion must not follow it into another tenant.
    planted = f"task_{uuid.uuid4().hex[:8]}"
    call(client, server.db.tasks.insert_one,
         {"id": planted, "tenant_id": owner["tenant_id"], "title": "Planted",
          "status": "todo", "assignee": owner["email"], "due_date": None,
          "related_type": "contact", "related_id": secret["id"], "archived_at": None,
          "created_at": iso(timedelta(0))})

    for params in ({}, {"mine": "true", "include_unassigned": "true"}, {"q": "Task"}):
        assert theirs["id"] not in ids(tasks(client, owner, **params))
    assert client.get(f"/api/crm/tasks/{theirs['id']}",
                      headers=owner["headers"]).status_code == 404
    leaked = tasks(client, owner, expand="related")["items"]
    related = next(item["related"] for item in leaked if item["id"] == planted)
    assert related["name"] is None and related["contact"] is None
    assert client.post("/api/crm/tasks", headers=owner["headers"],
                       json={"title": "x", "related_type": "contact",
                             "related_id": secret["id"]}).status_code == 422


# ------------------------------------------- the call-back task and its lead

def test_ticking_off_a_call_back_task_marks_the_lead_responded_at_once(client):
    owner = register(client)
    lead = submit_lead(client, owner)
    response = client.patch(f"/api/crm/tasks/{lead['task_id']}", headers=owner["headers"],
                            json={"status": "done"})
    assert response.status_code == 200, response.text

    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead["id"]})
    assert stored["status"] == "responded", "no sweep needed: the tick is the response"
    assert stored["sla"]["responded_via"] == "task_completed"
    assert stored["sla"]["first_response_at"] == response.json()["completed_at"]
    assert stored["responded_by"] == owner["email"]


def test_un_ticking_the_task_withdraws_the_response_it_recorded(client):
    owner = register(client)
    lead = submit_lead(client, owner)
    path = f"/api/crm/tasks/{lead['task_id']}"
    client.patch(path, headers=owner["headers"], json={"status": "done"})
    client.patch(path, headers=owner["headers"], json={"status": "todo"})

    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead["id"]})
    assert stored["status"] == "new"
    assert stored["sla"]["first_response_at"] is None
    assert stored["sla"]["response_minutes"] is None
    assert find_one(client, "domain_events", {"tenant_id": owner["tenant_id"],
                                              "event_type": "lead.reopened",
                                              "resource_id": lead["id"]})
    # The open task is not a response, so the sweep leaves the lead waiting...
    call(client, server.lead_pipeline.sweep, owner["tenant_id"])
    assert find_one(client, detectors.WEB_ENQUIRIES, {"id": lead["id"]})["status"] == "new"
    # ...and ticking it again records the response afresh.
    client.patch(path, headers=owner["headers"], json={"status": "done"})
    assert find_one(client, detectors.WEB_ENQUIRIES, {"id": lead["id"]})["status"] == "responded"


def test_reopening_the_task_keeps_a_response_recorded_another_way(client):
    owner = register(client)
    lead = submit_lead(client, owner)
    client.patch(f"/api/leads/{lead['id']}", headers=owner["headers"],
                 json={"status": "responded"})
    assert find_one(client, "tasks", {"id": lead["task_id"]})["status"] == "done"
    client.patch(f"/api/crm/tasks/{lead['task_id']}", headers=owner["headers"],
                 json={"status": "todo"})

    stored = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead["id"]})
    assert stored["status"] == "responded", (
        "the lead was contacted from the lead itself; reopening a follow-up does not undo that")
    assert stored["sla"]["responded_via"] == "marked_in_inbox"


def test_reopening_a_lead_reopens_its_call_back_task(client):
    owner = register(client)
    lead = submit_lead(client, owner)
    client.patch(f"/api/leads/{lead['id']}", headers=owner["headers"],
                 json={"status": "responded"})
    client.patch(f"/api/leads/{lead['id']}", headers=owner["headers"], json={"status": "new"})

    task = find_one(client, "tasks", {"id": lead["task_id"]})
    assert task["status"] == "todo" and task["completed_at"] is None
    call(client, server.lead_pipeline.sweep, owner["tenant_id"])
    reopened = find_one(client, detectors.WEB_ENQUIRIES, {"id": lead["id"]})
    assert reopened["status"] == "new", (
        "a finished call-back task left behind used to mark the reopened lead contacted again")
    # The old response no longer counts: not in the response figures, and not as a reason
    # for lost-lead detection to skip it.
    sla = reopened["sla"]
    assert sla["first_response_at"] is None and sla["response_minutes"] is None
    assert sla["responded_via"] is None
    assert not detectors.enquiry_is_resolved(reopened)


# ------------------------------------------------------- assignment notices

def notices(client, who):
    response = client.get("/api/notifications", headers=who["headers"])
    assert response.status_code == 200, response.text
    return response.json()["notifications"]


def test_an_assignment_notice_reaches_only_the_assignee_and_opens_the_task(client):
    owner = register(client)
    colleague = join(client, owner)
    task = new_task(client, owner, title="Call the Bells about Saturday",
                    assignee=colleague["email"])

    theirs = [n for n in notices(client, colleague) if n["type"] == "assignment"]
    assert len(theirs) == 1
    assert theirs[0]["deep_link"] == f"/tasks?task={task['id']}"
    assert theirs[0]["user_id"] == colleague["user_id"]
    assert theirs[0]["category"] == "tasks"
    assert not [n for n in notices(client, owner) if n["type"] == "assignment"], (
        "nobody else is told a task was assigned to them")
    assert client.post(f"/api/notifications/{theirs[0]['id']}/read",
                       headers=owner["headers"]).status_code == 404

    # Reassigning tells the new assignee; assigning to yourself tells nobody.
    client.patch(f"/api/crm/tasks/{task['id']}", headers=colleague["headers"],
                 json={"assignee": owner["email"]})
    assert [n for n in notices(client, owner) if n["type"] == "assignment"]
    before = len(find_all(client, "notifications", {"tenant_id": owner["tenant_id"],
                                                    "type": "assignment"}))
    client.patch(f"/api/crm/tasks/{task['id']}", headers=owner["headers"],
                 json={"assignee": owner["email"].upper()})
    new_task(client, owner, assignee=owner["email"])
    assert len(find_all(client, "notifications", {"tenant_id": owner["tenant_id"],
                                                  "type": "assignment"})) == before


def test_an_assignee_outside_the_team_gets_no_team_wide_notice(client):
    owner = register(client)
    new_task(client, owner, assignee="stranger@example.com")
    assert not find_all(client, "notifications", {"tenant_id": owner["tenant_id"],
                                                  "type": "assignment"})


def test_older_assignment_notices_stay_with_the_person_they_name(client):
    owner = register(client)
    colleague = join(client, owner)
    stamp = iso(timedelta(0))
    call(client, server.db.notifications.insert_many, [
        {"id": f"ntf_{uuid.uuid4().hex[:8]}", "tenant_id": owner["tenant_id"], "user_id": None,
         "recipient": colleague["email"], "type": "assignment", "source": "crm",
         "title": "A task was assigned to you", "deep_link": "/tasks/task_legacy",
         "read": False, "created_at": stamp},
        {"id": f"ntf_{uuid.uuid4().hex[:8]}", "tenant_id": owner["tenant_id"], "user_id": None,
         "recipient": None, "type": "lead.new", "category": "leads", "source": "website_form",
         "title": "New lead: Jane", "deep_link": "/leads?lead=x", "read": False,
         "created_at": stamp},
    ])
    assert {n["type"] for n in notices(client, colleague)} >= {"assignment", "lead.new"}
    owner_view = notices(client, owner)
    assert "lead.new" in {n["type"] for n in owner_view}, "team-wide notices still reach everyone"
    assert "assignment" not in {n["type"] for n in owner_view}

    client.post("/api/notifications/read-all", headers=owner["headers"])
    legacy = find_one(client, "notifications", {"tenant_id": owner["tenant_id"],
                                                "type": "assignment"})
    assert legacy["read"] is False, "marking my notices read leaves someone else's alone"


# --------------------------------------------------------- next best action

def test_an_overdue_task_recommendation_links_to_the_task(client):
    owner = register(client)
    task = new_task(client, owner, title="Send the CMA", due_date=iso(-timedelta(days=2)))
    assert client.post("/api/next-best-actions/generate",
                       headers=owner["headers"]).status_code == 200
    items = client.get("/api/next-best-actions", headers=owner["headers"]).json()
    advance = next(i for i in items if i["action_type"] == "advance_task")
    assert advance["deep_link"] == f"/tasks?task={task['id']}"

    # Following the link is navigation: the recommendation's own state is untouched by a
    # regeneration that adds or refreshes it.
    client.patch(f"/api/next-best-actions/{advance['id']}", headers=owner["headers"],
                 json={"state": "accepted"})
    call(client, server.db.next_best_actions.update_one, {"id": advance["id"]},
         {"$unset": {"deep_link": ""}})
    client.post("/api/next-best-actions/generate", headers=owner["headers"])
    again = next(i for i in client.get("/api/next-best-actions", headers=owner["headers"]).json()
                 if i["id"] == advance["id"])
    assert again["state"] == "accepted"
    assert again["deep_link"] == f"/tasks?task={task['id']}"
