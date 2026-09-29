"""Approvals whose decision moves something else cannot be forged or cancelled by others.

Deciding or cancelling an approval runs follow-through on its subject: an MCP write runs,
a recovery plan is approved or withdrawn, a message is released or refused. These are
the ways a member used to override an admin's decision through that follow-through.
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

import requests
from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("JWT_SECRET", "approval-forgery-unit-jwt-secret-long-enough-1")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

API = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/") + "/api"
ADMIN = {"email": os.environ.get("ADMIN_EMAIL", "admin@example.com"),
         "password": os.environ.get("ADMIN_PASSWORD", "AdminPass123!")}
MEMBER = {"email": os.environ.get("DEMO_MEMBER_EMAIL", "demo.member@clientverse.io"),
          "password": os.environ.get("DEMO_MEMBER_PASSWORD", "Member2026!")}


def _headers(creds):
    response = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _raise(headers, **body):
    return requests.post(f"{API}/approval-queue", headers=headers, timeout=30,
                         json={"title": f"Check {uuid.uuid4().hex[:6]}", **body})


def test_a_request_cannot_claim_a_system_kind_or_subject():
    member = _headers(MEMBER)
    for body in ({"kind": "communication_message"}, {"kind": "mcp_write"},
                 {"kind": "recovery_strategy"},
                 {"subject_type": "communication_message", "subject_id": "msg_x"},
                 {"subject_type": "recovery_strategy", "subject_id": "rs_x"},
                 {"subject_type": "mcp_pending_action", "subject_id": "pa_x"}):
        refused = _raise(member, **body)
        assert refused.status_code == 400, (body, refused.text)
    assert requests.post(f"{API}/approvals", headers=member, timeout=30, json={
        "title": "x", "kind": "mcp_write",
        "workspace_id": requests.get(f"{API}/workspaces", headers=member,
                                     timeout=30).json()[0]["id"]}).status_code == 400


def test_a_member_cannot_cancel_someone_elses_request():
    admin, member = _headers(ADMIN), _headers(MEMBER)
    theirs = _raise(admin)
    assert theirs.status_code == 200, theirs.text
    denied = requests.post(f"{API}/approval-queue/{theirs.json()['id']}/cancel",
                           headers=member, json={"reason": "mine now"}, timeout=30)
    assert denied.status_code == 403
    own = _raise(member)
    assert requests.post(f"{API}/approval-queue/{own.json()['id']}/cancel", headers=member,
                         json={"reason": "not needed"}, timeout=30).status_code == 200


# ------------------------------------------------------------------ the follow-through

def test_a_decision_moves_only_the_subject_that_names_it():
    """A request pointing at a message it does not govern (raised before the reserved
    kinds existed, or superseded) must leave that message alone when cancelled."""
    import conversations as cv
    import server

    tenant = f"ten_forge_{uuid.uuid4().hex[:8]}"
    name = f"clientverse_forge_{uuid.uuid4().hex[:8]}"

    async def body():
        server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
        previous, server.db = server.db, server.mclient[name]
        try:
            db = server.db
            await db[cv.MESSAGES].insert_one({
                "id": "msg_1", "tenant_id": tenant, "status": cv.APPROVED,
                "approval_id": "apr_real", "history": []})
            await db.recovery_strategies.insert_one({
                "id": "rs_1", "tenant_id": tenant, "state": "awaiting_approval",
                "approval_id": "apr_real_plan", "history": []})
            await db.mcp_pending_actions.insert_one({
                "id": "pa_1", "tenant_id": tenant, "status": "pending_approval",
                "approval_id": "apr_real_mcp", "invocation_id": "inv_1"})
            user = {"tenant_id": tenant, "email": "member@example.com", "role": "member"}
            for approval in (
                    {"id": "apr_forged", "tenant_id": tenant, "status": "cancelled",
                     "subject_type": "communication_message", "subject_id": "msg_1"},
                    {"id": "apr_forged2", "tenant_id": tenant, "status": "cancelled",
                     "subject_type": "recovery_strategy", "subject_id": "rs_1"},
                    {"id": "apr_forged3", "tenant_id": tenant, "status": "rejected",
                     "kind": "mcp_write", "action": {"pending_action_id": "pa_1"}}):
                await server._apply_approval_side_effects(approval, user)
            return (await db[cv.MESSAGES].find_one({"id": "msg_1"}))["status"], \
                (await db.recovery_strategies.find_one({"id": "rs_1"}))["state"], \
                (await db.mcp_pending_actions.find_one({"id": "pa_1"}))["status"]
        finally:
            await server.mclient.drop_database(name)
            server.db = previous

    loop = asyncio.new_event_loop()
    try:
        message, strategy, pending = loop.run_until_complete(body())
    finally:
        loop.close()
    assert message == cv.APPROVED
    assert strategy == "awaiting_approval"
    assert pending == "pending_approval"
