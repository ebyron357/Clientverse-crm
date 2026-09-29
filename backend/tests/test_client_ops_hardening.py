"""The client-ops review, as tests: each is an attack or accident that used to succeed.

Anyone can register a tenant, and the client portal needs no account at all, so these
are requests a stranger, a member or a client's browser could make.
"""

import concurrent.futures
import os
import uuid

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/") + "/api"
ADMIN = {"email": os.environ.get("ADMIN_EMAIL", "admin@example.com"),
         "password": os.environ.get("ADMIN_PASSWORD", "AdminPass123!")}
MEMBER = {"email": os.environ.get("DEMO_MEMBER_EMAIL", "demo.member@clientverse.io"),
          "password": os.environ.get("DEMO_MEMBER_PASSWORD", "Member2026!")}
_db = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
    os.environ.get("DB_NAME", "test_database")]


def _login(creds):
    response = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _tenant():
    response = requests.post(f"{API}/auth/register", timeout=30, json={
        "email": f"hard_{uuid.uuid4().hex[:10]}@example.com",
        "password": "Hardening2026!", "name": "Hardening"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _workspace(headers):
    response = requests.post(f"{API}/workspaces", headers=headers, timeout=30,
                             json={"name": f"WS {uuid.uuid4().hex[:6]}"})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _portal(headers, workspace_id):
    response = requests.post(f"{API}/portal-links", headers=headers, timeout=30,
                             json={"workspace_id": workspace_id, "client_label": "Client"})
    assert response.status_code == 200, response.text
    body = response.json()
    return body.get("token") or body.get("portal_token") or body["link"]["token"]


# ------------------------------------------------------------------ body size

def test_an_oversized_import_is_refused_before_it_is_parsed():
    headers = _tenant()
    big = "name\n" + "x\n" * (2 * 1024 * 1024)
    response = requests.post(f"{API}/import/contacts", headers=headers, timeout=60,
                             json={"csv": big})
    assert response.status_code == 413


def test_leaving_out_content_length_is_no_way_around_the_limit():
    headers = _tenant()

    def chunks():
        yield b'{"name": "'
        for _ in range(64):
            yield b"x" * 32 * 1024
        yield b'"}'

    response = requests.post(f"{API}/companies", data=chunks(), timeout=60,
                             headers={**headers, "Content-Type": "application/json"})
    assert response.status_code == 413


# ------------------------------------------------------------------ money values

@pytest.mark.parametrize("body", ['{"value": 1e308}', '{"value": Infinity}',
                                  '{"value": NaN}', '{"value": -5}'])
def test_a_deal_value_must_be_a_real_amount(body):
    headers = _tenant()
    deal = requests.post(f"{API}/opportunities", headers=headers, timeout=30,
                         json={"name": "Deal", "value": 100}).json()
    patched = requests.patch(f"{API}/opportunities/{deal['id']}", data=body, timeout=30,
                             headers={**headers, "Content-Type": "application/json"})
    assert patched.status_code == 422, (body, patched.status_code)
    created = requests.post(f"{API}/opportunities", data='{"name": "x", ' + body[1:],
                            timeout=30, headers={**headers, "Content-Type": "application/json"})
    assert created.status_code == 422, (body, created.status_code)
    assert requests.get(f"{API}/dashboard", headers=headers, timeout=30).status_code == 200


def test_an_estimate_cannot_total_infinity():
    headers = _tenant()
    ws = _workspace(headers)
    response = requests.post(f"{API}/estimates", headers=headers, timeout=30, json={
        "workspace_id": ws, "title": "Huge", "lines": [
            {"label": "a", "quantity": 1e200, "unit_price": 1e200}]})
    assert response.status_code == 422


def test_an_imported_deal_value_must_be_finite():
    headers = _tenant()
    result = requests.post(f"{API}/import/deals", headers=headers, timeout=30, json={
        "csv": "name,value\nGood,100\nBad,nan\nWorse,inf\n"}).json()
    assert result["created"] == 1 and result["rejected"] == 2


def test_a_stored_non_finite_number_no_longer_takes_the_tenant_down():
    headers = _tenant()
    deal = requests.post(f"{API}/opportunities", headers=headers, timeout=30,
                         json={"name": "Legacy", "value": 10}).json()
    _db.opportunities.update_one({"id": deal["id"]}, {"$set": {"value": float("inf")}})
    listing = requests.get(f"{API}/opportunities", headers=headers, timeout=30)
    assert listing.status_code == 200
    assert next(d for d in listing.json() if d["id"] == deal["id"])["value"] is None


# ------------------------------------------------------------------ the portal

def test_the_portal_request_route_is_throttled_and_bounded():
    headers = _tenant()
    token = _portal(headers, _workspace(headers))
    statuses = [requests.post(f"{API}/portal/{token}/requests", timeout=30,
                              headers={"X-Forwarded-For": f"10.9.{i}.1"},
                              json={"title": f"Request {i}"}).status_code
                for i in range(21)]
    assert statuses[:20] == [200] * 20 and statuses[20] == 429
    other = _portal(headers, _workspace(headers))
    huge = requests.post(f"{API}/portal/{other}/requests", timeout=30,
                         json={"title": "x", "padding": "y" * 40000})
    assert huge.status_code == 413


def test_the_portal_shows_only_commitments_an_admin_shared_and_no_staff_details():
    admin, member = _login(ADMIN), _login(MEMBER)
    ws = _workspace(admin)
    assert requests.post(f"{API}/commitments", headers=member, timeout=30, json={
        "workspace_id": ws, "title": "INTERNAL: client pays late",
        "owner": "staff-private@corp.example"}).status_code == 200
    assert requests.post(f"{API}/commitments", headers=member, timeout=30, json={
        "workspace_id": ws, "title": "Member shares", "client_visible": True}).status_code == 403
    assert requests.post(f"{API}/commitments", headers=admin, timeout=30, json={
        "workspace_id": ws, "title": "Kick-off call", "owner": "lead@corp.example",
        "client_visible": True}).status_code == 200
    portal = requests.get(f"{API}/portal/{_portal(admin, ws)}", timeout=30).json()
    assert [c["title"] for c in portal["commitments"]] == ["Kick-off call"]
    assert set(portal["commitments"][0]) <= {"id", "title", "status", "due_date"}
    assert "staff-private@corp.example" not in str(portal)


def test_approving_a_document_share_shares_it():
    admin = _login(ADMIN)
    ws = _workspace(admin)
    document = requests.post(f"{API}/documents", headers=admin, timeout=30, json={
        "workspace_id": ws, "title": "Onboarding plan", "client_visible": True,
        "requires_approval": True, "external_url": "https://docs.example.com/plan"}).json()
    assert document["status"] == "pending_approval" and document.get("approval_id")
    decided = requests.post(f"{API}/approval-queue/{document['approval_id']}/decision",
                            headers=admin, json={"decision": "approved", "rationale": "ok"},
                            timeout=30)
    assert decided.status_code == 200, decided.text
    portal = requests.get(f"{API}/portal/{_portal(admin, ws)}", timeout=30).json()
    assert [d["title"] for d in portal["documents"]] == ["Onboarding plan"]


# ------------------------------------------------------------------ invoices

def _sent_estimate(headers, ws, total=1000):
    estimate = requests.post(f"{API}/estimates", headers=headers, timeout=30, json={
        "workspace_id": ws, "title": "Work", "lines": [
            {"label": "Work", "quantity": 1, "unit_price": total}]}).json()
    assert requests.patch(f"{API}/estimates/{estimate['id']}", headers=headers, timeout=30,
                          json={"status": "sent"}).status_code == 200
    return estimate["id"]


def test_converting_an_estimate_twice_at_once_makes_one_invoice():
    headers = _tenant()
    ws = _workspace(headers)
    estimate_id = _sent_estimate(headers, ws)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: requests.post(
            f"{API}/estimates/{estimate_id}/invoice", headers=headers, timeout=30), range(10)))
    assert all(r.status_code == 200 for r in results)
    ids = {r.json()["invoice"]["id"] for r in results}
    assert len(ids) == 1
    assert sum(1 for r in results if r.json()["duplicate"] is False) == 1


def test_invoice_and_estimate_status_moves_follow_a_table():
    headers = _tenant()
    ws = _workspace(headers)
    estimate_id = _sent_estimate(headers, ws)
    invoice = requests.post(f"{API}/estimates/{estimate_id}/invoice", headers=headers,
                            timeout=30).json()["invoice"]
    url = f"{API}/invoices/{invoice['id']}"
    assert requests.patch(url, headers=headers, json={"status": "paid"},
                          timeout=30).status_code == 409  # draft cannot jump to paid
    assert requests.patch(url, headers=headers, json={"status": "issued"},
                          timeout=30).status_code == 200
    assert requests.patch(url, headers=headers, json={"status": "paid"},
                          timeout=30).status_code == 200
    assert requests.patch(url, headers=headers, json={"status": "draft"},
                          timeout=30).status_code == 409
    paid = next(i for i in requests.get(f"{API}/invoices", headers=headers, timeout=30).json()
                if i["id"] == invoice["id"])
    assert paid["payment_status"] == "paid" and paid.get("paid_at")
    assert requests.patch(f"{API}/estimates/{estimate_id}", headers=headers, timeout=30,
                          json={"status": "declined"}).status_code == 409
    assert requests.post(f"{API}/estimates", headers=headers, timeout=30, json={
        "workspace_id": ws, "title": "Bad date", "valid_until": "not-a-date"}
    ).status_code == 422


# ------------------------------------------------------------------ pipeline and search

def test_a_custom_won_stage_counts_as_won():
    headers = _tenant()
    stages = [{"key": "open", "label": "Open", "probability": 20},
              {"key": "won", "label": "Won", "probability": 100, "is_closed": True, "is_won": True},
              {"key": "lost", "label": "Lost", "probability": 0, "is_closed": True}]
    assert requests.put(f"{API}/pipelines/default", headers=headers, json={"stages": stages},
                        timeout=30).status_code == 200
    company = requests.post(f"{API}/companies", headers=headers, json={"name": "Won Co"},
                            timeout=30).json()["id"]
    deal = requests.post(f"{API}/opportunities", headers=headers, timeout=30, json={
        "name": "Big", "value": 50000, "stage": "open", "company_id": company}).json()
    assert requests.patch(f"{API}/opportunities/{deal['id']}/stage", headers=headers,
                          json={"stage": "won"}, timeout=30).status_code == 200
    dashboard = requests.get(f"{API}/dashboard", headers=headers, timeout=30).json()
    kpis = dashboard.get("kpis", dashboard)
    assert kpis["won_value"] == 50000 and kpis["pipeline_value"] == 0
    workspaces = requests.get(f"{API}/workspaces", headers=headers, timeout=30).json()
    assert any(w.get("opportunity_id") == deal["id"] for w in workspaces)


def test_a_long_search_with_special_characters_is_not_a_server_error():
    headers = _tenant()
    for path in ("/search", "/contacts", "/tasks"):
        response = requests.get(f"{API}{path}", headers=headers, timeout=30,
                                params={"q": "a" + "." * 150})
        assert response.status_code == 200, (path, response.status_code)


def test_a_negative_timeline_limit_is_not_a_server_error():
    headers = _tenant()
    contact = requests.post(f"{API}/contacts", headers=headers, json={"name": "Tim"},
                            timeout=30).json()
    response = requests.get(f"{API}/contacts/{contact['id']}/timeline", headers=headers,
                            params={"limit": -1}, timeout=30)
    assert response.status_code == 200


def test_a_portal_token_never_reaches_the_access_log():
    import logging

    import server

    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 0, '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "POST", "/api/portal/Zx9-secretTOKEN_abc/requests", "1.1", 200), None)
    for handler_filter in logging.getLogger("uvicorn.access").filters:
        handler_filter.filter(record)
    assert "secretTOKEN" not in record.getMessage()
    assert "/api/portal/[redacted]/requests" in record.getMessage()
