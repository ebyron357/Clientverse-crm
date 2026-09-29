"""A review of the round-three fixes found regressions and gaps in them. Pinned here.

A tiny outcome target took the dashboard down; an MCP write whose approval lapsed was
replayed as pending forever; the recommendation truncation guard counted the wrong
thing; a double-click on first login was refused unchecked; a voided invoice blocked
re-invoicing; two concurrent links named two clients; a usage-priced estimate line was
refused; a lapsed document-share approval stranded the document.
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from cryptography.fernet import Fernet
from motor.motor_asyncio import AsyncIOMotorClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("JWT_SECRET", "fix-review-hardening-jwt-secret-long-enough-1")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

import approval_queue as aq
import next_best_action as nba
import recovery_case as rc
import server

API = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/") + "/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "clientverse_ci")


def ago(**kwargs):
    return (datetime.now(timezone.utc) - timedelta(**kwargs)).isoformat()


def ahead(**kwargs):
    return (datetime.now(timezone.utc) + timedelta(**kwargs)).isoformat()


def isolated(body):
    name = f"clientverse_fr_{uuid.uuid4().hex[:10]}"

    async def wrapped():
        server.mclient = server.AsyncIOMotorClient(MONGO_URL)
        previous, server.db = server.db, server.mclient[name]
        try:
            await server.db.login_lockouts.create_index("email", unique=True)
            await aq.ensure_indexes(server.db)
            return await body(server.db)
        finally:
            await server.mclient.drop_database(name)
            server.db = previous

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(wrapped())
    finally:
        loop.close()


def shared_db(body):
    """Run `body(db)` against the database the running API uses."""
    async def wrapped():
        client = AsyncIOMotorClient(MONGO_URL)
        try:
            return await body(client[DB_NAME])
        finally:
            client.close()

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(wrapped())
    finally:
        loop.close()


def _admin():
    response = requests.post(f"{API}/auth/register", timeout=30, json={
        "email": f"fr_{uuid.uuid4().hex[:10]}@example.com",
        "password": "FixReview2026!", "name": "FR"})
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}, response.json()["user"]["tenant_id"]


def _workspace(headers):
    response = requests.post(f"{API}/workspaces", headers=headers, json={"name": "Acme"},
                             timeout=30)
    assert response.status_code == 200, response.text
    return response.json()["id"]


# ------------------------------------------------------------ outcome progress

def test_a_tiny_target_does_not_take_the_dashboard_down():
    headers, tenant = _admin()
    ws = _workspace(headers)
    created = requests.post(f"{API}/outcomes", headers=headers, timeout=30, json={
        "workspace_id": ws, "title": "Tiny", "target_value": 1e-320, "current_value": 5})
    assert created.status_code == 200, created.text

    async def legacy_nan(db):
        await db.outcomes.insert_one({"id": f"out_nan_{uuid.uuid4().hex[:6]}",
                                      "tenant_id": tenant, "workspace_id": ws,
                                      "title": "Legacy", "target_value": 100,
                                      "current_value": float("nan")})

    shared_db(legacy_nan)
    assert requests.get(f"{API}/dashboard", headers=headers, timeout=30).status_code == 200


def test_outcome_progress_is_none_when_it_cannot_be_computed():
    assert server.outcome_pct(5, 1e-320) is None
    assert server.outcome_pct(float("nan"), 100) is None
    assert server.outcome_pct(50, 100) == 50
    assert server.outcome_pct(500, 100) == 100


# ------------------------------------------------------------ MCP writes

def test_an_mcp_write_whose_approval_lapsed_is_asked_again():
    headers, tenant = _admin()
    ws = _workspace(headers)
    body = {"tool": "create_task", "args": {"workspace_id": ws, "title": "Follow up"},
            "idempotency_key": f"k-{uuid.uuid4().hex[:8]}"}
    first = requests.post(f"{API}/mcp/invoke", headers=headers, json=body, timeout=30).json()
    assert first["status"] == "pending_approval"

    async def lapse(db):
        await db[aq.COLLECTION].update_one({"id": first["approval_id"]},
                                           {"$set": {"expires_at": ago(minutes=1)}})

    shared_db(lapse)
    again = requests.post(f"{API}/mcp/invoke", headers=headers, json=body, timeout=30).json()
    assert again["status"] == "pending_approval"
    assert not again.get("idempotent_replay")
    assert again["approval_id"] != first["approval_id"]


# ------------------------------------------------------------ recommendations

def test_recommendations_are_not_retired_when_a_rule_read_more_rows_than_its_cap():
    async def body(db):
        tenant = "ten_nba_cap"
        await nba.ensure_indexes(db)
        # The reviewer's sequence: a thousand finished tasks, then one overdue one.
        await db.tasks.insert_many([
            {"id": f"t{n}", "tenant_id": tenant, "title": "Later", "status": "done",
             "due_date": ahead(days=30)} for n in range(nba.RULE_QUERY_CAP + 5)])
        await db.tasks.insert_one({"id": "late", "tenant_id": tenant, "title": "Late",
                                   "status": "todo", "due_date": ago(days=3)})
        await nba.generate(db, tenant)
        # The finished tasks are reopened (not yet due): the rule now reads more rows
        # than its cap, and the overdue task may not be among the first thousand.
        await db.tasks.update_many({"tenant_id": tenant, "status": "done"},
                                   {"$set": {"status": "todo"}})
        await nba.generate(db, tenant)
        return await db[nba.COLLECTION].find_one(
            {"tenant_id": tenant, "dedupe_key": f"{nba.ACTION_ADVANCE_TASK}:late"})

    rec = isolated(body)
    assert rec["state"] != nba.STATE_COMPLETED


# ------------------------------------------------------------ login

def test_a_double_click_on_a_first_login_is_not_refused_unchecked(monkeypatch):
    monkeypatch.setattr(server, "verify_password", lambda password, hashed: password == hashed)

    async def body(db):
        refused = 0
        for n in range(20):
            email = f"first_{n}@example.com"
            await db.users.insert_one({"user_id": f"u_{n}", "email": email,
                                       "password_hash": "right", "tenant_id": "t"})

            async def attempt(email=email):
                try:
                    await server.login(server.LoginInput(email=email, password="right"),
                                       server.Response())
                    return True
                except server.HTTPException:
                    return False

            results = await asyncio.gather(attempt(), attempt())
            refused += results.count(False)
        return refused

    monkeypatch.setattr(server, "resolve_membership", _passthrough)
    assert isolated(body) == 0


async def _passthrough(user):
    return user


def test_repeated_lockouts_lengthen():
    async def body(db):
        email = "escalate@example.com"
        await db.login_lockouts.insert_one({
            "email": email, "failed_count": 0, "locked_until": None, "lock_count": 2})
        for _ in range(server.LOGIN_LOCKOUT_THRESHOLD):
            await server._reserve_login_attempt(email)
        return await db.login_lockouts.find_one({"email": email})

    record = isolated(body)
    locked_until = datetime.fromisoformat(record["locked_until"])
    minutes = (locked_until - datetime.now(timezone.utc)).total_seconds() / 60
    assert minutes > server.LOGIN_LOCKOUT_MINUTES * 3
    assert record["lock_count"] == 3


# ------------------------------------------------------------ invoices and estimates

def _estimate(headers, ws, quantity=1, unit_price=1000):
    estimate = requests.post(f"{API}/estimates", headers=headers, timeout=30, json={
        "workspace_id": ws, "title": "Work",
        "lines": [{"label": "Service", "quantity": quantity, "unit_price": unit_price}]})
    return estimate


def test_a_voided_invoice_does_not_block_invoicing_the_estimate_again():
    headers, _ = _admin()
    ws = _workspace(headers)
    estimate = _estimate(headers, ws).json()
    requests.patch(f"{API}/estimates/{estimate['id']}", headers=headers, timeout=30,
                   json={"status": "sent"})
    first = requests.post(f"{API}/estimates/{estimate['id']}/invoice", headers=headers,
                          timeout=30).json()["invoice"]
    voided = requests.patch(f"{API}/invoices/{first['id']}", headers=headers, timeout=30,
                            json={"status": "void"})
    assert voided.status_code == 200
    second = requests.post(f"{API}/estimates/{estimate['id']}/invoice", headers=headers,
                           timeout=30).json()
    assert second["duplicate"] is False and second["invoice"]["id"] != first["id"]
    third = requests.post(f"{API}/estimates/{estimate['id']}/invoice", headers=headers,
                          timeout=30).json()
    assert third["duplicate"] is True and third["invoice"]["id"] == second["invoice"]["id"]


def test_a_mistaken_manual_payment_can_be_corrected_until_it_is_booked():
    headers, tenant = _admin()
    ws = _workspace(headers)
    estimate = _estimate(headers, ws).json()
    requests.patch(f"{API}/estimates/{estimate['id']}", headers=headers, timeout=30,
                   json={"status": "sent"})
    invoice = requests.post(f"{API}/estimates/{estimate['id']}/invoice", headers=headers,
                            timeout=30).json()["invoice"]
    for status in ("issued", "paid"):
        assert requests.patch(f"{API}/invoices/{invoice['id']}", headers=headers, timeout=30,
                              json={"status": status}).status_code == 200
    corrected = requests.patch(f"{API}/invoices/{invoice['id']}", headers=headers,
                               timeout=30, json={"status": "issued"})
    assert corrected.status_code == 200, corrected.text

    async def check_and_book(db):
        row = await db.invoices.find_one({"id": invoice["id"]})
        await db.attribution_entries.insert_one({
            "id": f"attr_{uuid.uuid4().hex[:8]}", "tenant_id": tenant, "case_id": "rc_x",
            "booked_record": f"invoices:{invoice['id']}", "duplicate_of": None,
            "claim": "attributed", "outcome": {"kind": "invoice_paid"}})
        return row

    row = shared_db(check_and_book)
    assert row["payment_status"] != "paid" and not row.get("paid_at")
    requests.patch(f"{API}/invoices/{invoice['id']}", headers=headers, timeout=30,
                   json={"status": "paid"})
    booked = requests.patch(f"{API}/invoices/{invoice['id']}", headers=headers, timeout=30,
                            json={"status": "issued"})
    assert booked.status_code == 409


def test_a_usage_priced_line_is_accepted():
    headers, _ = _admin()
    ws = _workspace(headers)
    response = _estimate(headers, ws, quantity=2_500_000, unit_price=0.004)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 10000


# ------------------------------------------------------------ recovery case links

def test_two_concurrent_links_cannot_name_two_clients():
    async def body(db):
        tenant = "ten_link_race"
        await db.companies.insert_many([{"id": "co_a", "tenant_id": tenant},
                                        {"id": "co_b", "tenant_id": tenant}])
        await db.contacts.insert_one({"id": "ct_a", "tenant_id": tenant, "company_id": "co_a"})
        both = 0
        for n in range(10):
            case = await rc.open_case(db, rc.normalize_event(
                tenant_id=tenant, source=rc.SOURCE_MISSED_CALL, source_event_id=f"c{n}",
                reason="Rang out"))
            await asyncio.gather(
                rc.link_crm_records(db, tenant_id=tenant, case_id=case["id"], actor="a",
                                    contact_id="ct_a"),
                rc.link_crm_records(db, tenant_id=tenant, case_id=case["id"], actor="b",
                                    company_id="co_b"),
                return_exceptions=True)
            final = await rc.get_case(db, tenant, case["id"])
            both += bool(final.get("contact_id") and final.get("company_id"))
        return both

    assert isolated(body) == 0


# ------------------------------------------------------------ document shares

def test_a_lapsed_document_share_returns_the_document_to_draft():
    async def body(db):
        tenant = "ten_doc_lapse"
        await db.client_documents.insert_one({"id": "doc_1", "tenant_id": tenant,
                                              "title": "Plan", "status": "pending_approval"})
        approval = await aq.request(
            db, tenant_id=tenant, title="Share document", kind="document_share",
            actor="admin@example.com", requester_kind=aq.REQUESTER_HUMAN, summary="Share",
            action={"type": "document_share", "document_id": "doc_1"},
            subject_type="client_document", subject_id="doc_1")
        await db[aq.COLLECTION].update_one({"id": approval["id"]},
                                           {"$set": {"expires_at": ago(minutes=1)}})
        await server.run_approval_expiry_sweep()
        return (await db.client_documents.find_one({"id": "doc_1"}))["status"]

    assert isolated(body) == "draft"
