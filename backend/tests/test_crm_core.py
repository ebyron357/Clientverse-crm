"""Baseline CRM behaviour.

These cover the ordinary CRM the recovery engine sits on top of: opening and editing a
record, owning it, relating records to each other, following work up, keeping history,
finding things again, getting data in and out, and never seeing another tenant's rows.

Written against the live server over HTTP for the same reason the other integration
files are: several of these paths involve the application's own audit and notification
wiring, not just a data-layer call.
"""

import csv
import io
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"
API = f"{BASE}/api"
TIMEOUT = 20


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _register(prefix="crm"):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    response = requests.post(f"{API}/auth/register", timeout=TIMEOUT,
                             json={"email": email, "password": "CrmCore2026!!",
                                   "name": "CRM Core Test"})
    assert response.status_code == 200, response.text
    body = response.json()
    return body.get("token") or body["access_token"], email


class Tenant:
    """A fresh tenant with one company, one contact and one deal already linked."""

    def __init__(self, prefix="crm"):
        self.token, self.email = _register(prefix)
        self.h = _h(self.token)
        self.tag = uuid.uuid4().hex[:8]
        self.company_id = self.post("/companies", {"name": f"Co-{self.tag}",
                                                   "industry": "Services"})["id"]
        self.contact_id = self.post("/contacts", {
            "name": f"Person-{self.tag}", "email": f"p_{self.tag}@example.com",
            "company_id": self.company_id})["id"]
        self.deal_id = self.post("/opportunities", {
            "name": f"Deal-{self.tag}", "company_id": self.company_id, "value": 1000,
            "contact_ids": [self.contact_id]})["id"]

    def post(self, path, body, expect=200):
        response = requests.post(f"{API}{path}", headers=self.h, json=body, timeout=TIMEOUT)
        assert response.status_code == expect, f"POST {path} -> {response.status_code} {response.text}"
        return response.json()

    def patch(self, path, body, expect=200):
        response = requests.patch(f"{API}{path}", headers=self.h, json=body, timeout=TIMEOUT)
        assert response.status_code == expect, f"PATCH {path} -> {response.status_code} {response.text}"
        return response.json()

    def put(self, path, body, expect=200):
        response = requests.put(f"{API}{path}", headers=self.h, json=body, timeout=TIMEOUT)
        assert response.status_code == expect, f"PUT {path} -> {response.status_code} {response.text}"
        return response.json()

    def get(self, path, expect=200):
        response = requests.get(f"{API}{path}", headers=self.h, timeout=TIMEOUT)
        assert response.status_code == expect, f"GET {path} -> {response.status_code} {response.text}"
        return response.json()

    def raw(self, method, path, **kwargs):
        return requests.request(method, f"{API}{path}", headers=self.h, timeout=TIMEOUT, **kwargs)


@pytest.fixture(scope="module")
def tenant():
    return Tenant("crm_a")


@pytest.fixture(scope="module")
def other():
    return Tenant("crm_b")


# ------------------------------------------------------------------------------ records

def test_a_contact_can_be_opened_and_carries_its_context(tenant):
    detail = tenant.get(f"/contacts/{tenant.contact_id}")
    assert detail["contact"]["id"] == tenant.contact_id
    assert detail["company"]["id"] == tenant.company_id
    assert any(deal["id"] == tenant.deal_id for deal in detail["deals"]), (
        "a contact must show the deals it is on")
    assert "timeline" in detail


def test_a_contact_can_be_edited_and_the_change_is_in_its_own_history(tenant):
    updated = tenant.patch(f"/contacts/{tenant.contact_id}",
                           {"title": "Head of Operations", "phone": "+15550100"})
    assert updated["title"] == "Head of Operations"
    assert updated["phone"] == "+15550100"
    actions = [entry["action"] for entry in updated["history"]]
    assert "created" in actions and "updated" in actions, (
        "a record's own history is where its state transitions live")


def test_archiving_hides_a_contact_from_lists_without_destroying_it(tenant):
    contact_id = tenant.post("/contacts", {"name": f"Temp-{uuid.uuid4().hex[:6]}"})["id"]
    tenant.post(f"/contacts/{contact_id}/archive", {})

    listed = tenant.get("/contacts")
    assert not any(c["id"] == contact_id for c in listed)
    assert any(c["id"] == contact_id for c in tenant.get("/contacts?include_archived=true"))
    # Still readable by id: archiving files a record away, it does not erase history
    # that conversations and cases may cite.
    assert tenant.get(f"/contacts/{contact_id}")["contact"]["archived_at"]

    tenant.post(f"/contacts/{contact_id}/restore", {})
    assert any(c["id"] == contact_id for c in tenant.get("/contacts"))


def test_a_company_reports_open_pipeline_and_won_revenue_separately(tenant):
    detail = tenant.get(f"/companies/{tenant.company_id}")
    commercial = detail["commercial"]
    assert "open_pipeline_value" in commercial and "closed_won_value" in commercial
    assert commercial["open_pipeline_value"] != commercial["closed_won_value"] or (
        commercial["open_pipeline_value"] == 0)
    assert any(c["id"] == tenant.contact_id for c in detail["contacts"])
    assert any(d["id"] == tenant.deal_id for d in detail["deals"])


def test_a_deal_is_fully_editable_not_just_draggable(tenant):
    updated = tenant.patch(f"/opportunities/{tenant.deal_id}", {
        "value": 7500, "owner": tenant.email, "expected_close_date": "2027-06-30",
        "description": "Renewal with expansion",
    })
    assert updated["value"] == 7500
    assert updated["owner"] == tenant.email
    assert updated["expected_close_date"].startswith("2027-06-30")


def test_a_deal_keeps_its_own_stage_history(tenant):
    tenant.patch(f"/opportunities/{tenant.deal_id}/stage", {"stage": "qualified"})
    tenant.patch(f"/opportunities/{tenant.deal_id}/stage", {"stage": "proposal"})
    detail = tenant.get(f"/opportunities/{tenant.deal_id}")
    transitions = [(h.get("from"), h["to"]) for h in detail["stage_history"]]
    assert (None, "lead") in transitions, "creation is the first transition"
    assert ("lead", "qualified") in transitions
    assert ("qualified", "proposal") in transitions
    assert detail["deal"]["stage"] == "proposal"


def test_weighted_value_is_reported_as_an_estimate_beside_the_deal_value(tenant):
    detail = tenant.get(f"/opportunities/{tenant.deal_id}")
    assert "weighted_value_estimate" in detail
    assert detail["weighted_value_estimate"] != detail["deal"]["value"] or (
        detail["stage"]["probability"] == 100)
    # The estimate must never replace the figure it is derived from.
    assert detail["deal"]["value"] is not None


def test_an_invalid_expected_close_date_is_refused_not_stored(tenant):
    response = tenant.raw("PATCH", f"/opportunities/{tenant.deal_id}",
                          json={"expected_close_date": "next tuesday"})
    assert response.status_code == 422


# ----------------------------------------------------------------------------- pipeline

def test_pipeline_stages_are_configurable_and_report_stage_totals(tenant):
    pipeline = tenant.get("/pipelines/default")
    assert [stage["key"] for stage in pipeline["stages"]][0] == "lead"
    assert "totals" in pipeline
    assert set(pipeline["totals"]["proposal"]) == {
        "deal_count", "deal_value", "weighted_value_estimate"}

    stages = pipeline["stages"] + [{"key": "pilot", "label": "Pilot", "probability": 60,
                                    "is_closed": False, "is_won": False}]
    updated = tenant.put("/pipelines/default", {"stages": stages})
    assert "pilot" in [stage["key"] for stage in updated["stages"]]
    # A stage that exists must be usable.
    tenant.patch(f"/opportunities/{tenant.deal_id}/stage", {"stage": "pilot"})
    assert tenant.get(f"/opportunities/{tenant.deal_id}")["deal"]["stage"] == "pilot"


def test_a_stage_holding_deals_cannot_be_deleted_out_from_under_them(tenant):
    pipeline = tenant.get("/pipelines/default")
    without_pilot = [s for s in pipeline["stages"] if s["key"] != "pilot"]
    response = tenant.raw("PUT", "/pipelines/default", json={"stages": without_pilot})
    assert response.status_code == 409, (
        "removing a stage that still holds deals would strand them")
    # Move the deal out, then the same change is allowed.
    tenant.patch(f"/opportunities/{tenant.deal_id}/stage", {"stage": "proposal"})
    tenant.put("/pipelines/default", {"stages": without_pilot})


def test_a_pipeline_with_no_closed_won_stage_is_refused(tenant):
    stages = [{"key": "a", "label": "A", "probability": 10, "is_closed": False, "is_won": False},
              {"key": "b", "label": "B", "probability": 20, "is_closed": False, "is_won": False}]
    assert tenant.raw("PUT", "/pipelines/default", json={"stages": stages}).status_code == 422


def test_a_deal_cannot_be_moved_into_a_stage_the_pipeline_does_not_have(tenant):
    response = tenant.raw("PATCH", f"/opportunities/{tenant.deal_id}/stage",
                          json={"stage": "invented_stage"})
    assert response.status_code == 400


# -------------------------------------------------------------------------------- tasks

def test_a_follow_up_can_be_created_against_a_deal_and_completed(tenant):
    task = tenant.post("/crm/tasks", {
        "title": "Call them back", "related_type": "deal", "related_id": tenant.deal_id,
        "assignee": tenant.email, "due_date": "2027-02-01", "priority": "high"})
    assert task["related_id"] == tenant.deal_id
    assert task["completed_at"] is None

    done = tenant.patch(f"/crm/tasks/{task['id']}", {"status": "done"})
    assert done["status"] == "done"
    assert done["completed_at"], "completion must record when it happened"

    reopened = tenant.patch(f"/crm/tasks/{task['id']}", {"status": "todo"})
    assert reopened["completed_at"] is None, (
        "reopening a task must clear the completion timestamp, not leave a stale one")


def test_a_task_cannot_be_attached_to_a_record_that_does_not_exist(tenant):
    response = tenant.raw("POST", "/crm/tasks", json={
        "title": "Orphan", "related_type": "deal", "related_id": "opp_does_not_exist"})
    assert response.status_code == 422


def test_overdue_and_upcoming_work_is_surfaced(tenant):
    past = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    tenant.post("/crm/tasks", {"title": "Late one", "due_date": past,
                               "related_type": "contact", "related_id": tenant.contact_id})
    tenant.post("/crm/tasks", {"title": "Soon one", "due_date": soon,
                               "related_type": "contact", "related_id": tenant.contact_id})
    overview = tenant.get("/tasks/overview")
    assert any(t["title"] == "Late one" for t in overview["overdue"])
    assert any(t["title"] == "Soon one" for t in overview["upcoming"])
    assert overview["counts"]["overdue"] >= 1


def test_assigning_a_task_to_someone_else_notifies_them(tenant):
    tenant.post("/crm/tasks", {"title": "For a colleague", "assignee": "colleague@example.com",
                               "related_type": "company", "related_id": tenant.company_id})
    notifications = tenant.get("/notifications")["notifications"]
    assigned = [n for n in notifications if "assigned" in (n.get("title") or "").lower()]
    assert assigned, "an assignment nobody is told about is not an assignment"
    assert assigned[0]["recipient"] == "colleague@example.com"
    assert assigned[0]["read"] is False


# --------------------------------------------------------------------------- activities

@pytest.mark.parametrize("activity_type", ["note", "call", "meeting", "email"])
def test_ordinary_crm_activity_types_can_be_logged(tenant, activity_type):
    logged = tenant.post("/activities", {
        "type": activity_type, "related_type": "contact", "related_id": tenant.contact_id,
        "subject": f"{activity_type} subject", "body": "what happened"})
    assert logged["type"] == activity_type
    assert logged["actor"] == tenant.email

    timeline = tenant.get(f"/contacts/{tenant.contact_id}/timeline")["timeline"]
    assert any(entry["type"] == activity_type for entry in timeline)


def test_a_caller_cannot_fabricate_a_system_recorded_activity(tenant):
    response = tenant.raw("POST", "/activities", json={
        "type": "status_change", "related_type": "deal", "related_id": tenant.deal_id,
        "subject": "moved itself"})
    assert response.status_code == 422, (
        "a caller inventing a state transition would be forging the record's history")


def test_logging_an_email_records_history_and_sends_nothing(tenant):
    before = tenant.get("/conversations/summary")
    tenant.post("/activities", {
        "type": "email", "related_type": "contact", "related_id": tenant.contact_id,
        "subject": "Following up", "body": "I sent this from my own mailbox"})
    after = tenant.get("/conversations/summary")
    # Logging what a person already did must not create an outbound message, or
    # "drafted" and "sent" stop meaning anything.
    assert after.get("messages") == before.get("messages")


# --------------------------------------------------------------------- search and sort

def test_search_finds_records_across_types(tenant):
    results = tenant.get(f"/search?q={tenant.tag}")
    assert any(c["id"] == tenant.company_id for c in results["companies"])
    assert any(c["id"] == tenant.contact_id for c in results["contacts"])
    assert any(d["id"] == tenant.deal_id for d in results["deals"])


def test_lists_can_be_filtered_and_sorted(tenant):
    tenant.patch(f"/opportunities/{tenant.deal_id}", {"owner": tenant.email})
    by_owner = tenant.get(f"/opportunities?owner={tenant.email}")
    assert any(d["id"] == tenant.deal_id for d in by_owner)

    ascending = tenant.get("/opportunities?sort=value&order=asc")
    values = [float(d.get("value") or 0) for d in ascending]
    assert values == sorted(values)


def test_a_sort_field_that_is_not_allowed_falls_back_rather_than_leaking(tenant):
    # Sorting by an arbitrary field would let a caller probe fields it cannot read.
    response = tenant.raw("GET", "/contacts?sort=password_hash&order=asc")
    assert response.status_code == 200
    assert all("password_hash" not in row for row in response.json())


# ------------------------------------------------------------------------ import/export

def test_contacts_export_round_trips_through_import(tenant):
    response = tenant.raw("GET", "/export/contacts")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert any(row["id"] == tenant.contact_id for row in rows)

    payload = "name,email,title\nImported One,imported_one@example.com,Buyer\n"
    result = tenant.post("/import/contacts", {"csv": payload, "on_duplicate": "skip"})
    assert result["created"] == 1 and result["rejected"] == 0
    assert any(c["email"] == "imported_one@example.com" for c in tenant.get("/contacts"))


def test_import_reports_bad_rows_instead_of_silently_dropping_them(tenant):
    payload = ("name,email\n"
               ",no_name@example.com\n"
               "Good Row,good_row@example.com\n")
    result = tenant.post("/import/contacts", {"csv": payload})
    assert result["created"] == 1
    assert result["rejected"] == 1
    assert result["errors"][0]["row"] == 2


def test_import_refuses_a_column_it_does_not_understand(tenant):
    response = tenant.raw("POST", "/import/contacts",
                          json={"csv": "name,secret_field\nX,Y\n"})
    assert response.status_code == 422


def test_import_will_not_attach_a_record_to_another_tenants_company(tenant, other):
    payload = f"name,company_id\nCross Tenant,{other.company_id}\n"
    result = tenant.post("/import/contacts", {"csv": payload})
    assert result["created"] == 0 and result["rejected"] == 1


def test_importing_deals_validates_stages_against_this_tenants_pipeline(tenant):
    result = tenant.post("/import/deals", {
        "csv": "name,stage,value\nStaged Deal,proposal,100\nBad Deal,not_a_stage,100\n"})
    assert result["created"] == 1
    assert result["rejected"] == 1


# ------------------------------------------------------------------- tenant isolation

@pytest.mark.parametrize("path_for", [
    lambda t: f"/contacts/{t.contact_id}",
    lambda t: f"/companies/{t.company_id}",
    lambda t: f"/opportunities/{t.deal_id}",
    lambda t: f"/contacts/{t.contact_id}/timeline",
    lambda t: f"/companies/{t.company_id}/timeline",
    lambda t: f"/opportunities/{t.deal_id}/timeline",
])
def test_another_tenants_record_is_indistinguishable_from_one_that_does_not_exist(
        tenant, other, path_for):
    response = other.raw("GET", path_for(tenant))
    assert response.status_code == 404, (
        "a 403 here would confirm the id is real; a 404 tells the caller nothing")


@pytest.mark.parametrize("method,path_for,body", [
    ("PATCH", lambda t: f"/contacts/{t.contact_id}", {"title": "hijacked"}),
    ("PATCH", lambda t: f"/companies/{t.company_id}", {"name": "hijacked"}),
    ("PATCH", lambda t: f"/opportunities/{t.deal_id}", {"value": 1}),
    ("POST", lambda t: f"/contacts/{t.contact_id}/archive", {}),
    ("POST", lambda t: f"/opportunities/{t.deal_id}/archive", {}),
])
def test_another_tenant_cannot_mutate_a_record_it_cannot_see(
        tenant, other, method, path_for, body):
    assert other.raw(method, path_for(tenant), json=body).status_code == 404


def test_a_deal_cannot_be_linked_to_another_tenants_contact(tenant, other):
    response = tenant.raw("PATCH", f"/opportunities/{tenant.deal_id}",
                          json={"contact_ids": [other.contact_id]})
    assert response.status_code == 422
    # And the refusal must be total: no partial link survives it.
    detail = tenant.get(f"/opportunities/{tenant.deal_id}")
    assert other.contact_id not in (detail["deal"].get("contact_ids") or [])


def test_a_contact_cannot_be_created_against_another_tenants_company(tenant, other):
    response = tenant.raw("POST", "/contacts",
                          json={"name": "Cross", "company_id": other.company_id})
    assert response.status_code == 422


def test_search_never_crosses_a_tenant_boundary(tenant, other):
    results = other.get(f"/search?q={tenant.tag}")
    assert results["total"] == 0


def test_export_only_contains_the_callers_own_rows(tenant, other):
    response = other.raw("GET", "/export/contacts")
    assert response.status_code == 200
    assert tenant.contact_id not in response.text
