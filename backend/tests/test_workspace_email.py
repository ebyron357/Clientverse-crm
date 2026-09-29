"""A workspace's email is the Gmail mirror and the conversation store read as one.

Mail sent through the CRM, and replies placed on its threads, live in conversations; the
workspace surfaces read only the Gmail sync mirror, so a client emailed yesterday through
the CRM showed as "no recent email" and flagged the workspace's health.
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("JWT_SECRET", "workspace-email-unit-jwt-secret-long-enough-1")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

import conversations as cv
import server

TENANT = "ten_ws_email"
USER = {"tenant_id": TENANT, "email": "admin@example.com", "role": "admin"}


def ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _run(body):
    name = f"clientverse_wsmail_{uuid.uuid4().hex[:8]}"

    async def wrapped():
        server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
        previous, server.db = server.db, server.mclient[name]
        try:
            db = server.db
            await db.workspaces.insert_one({"id": "ws_1", "tenant_id": TENANT,
                                            "company_id": "co_1", "name": "Acme"})
            await db.crm_communications.insert_one({
                "id": "comm_1", "tenant_id": TENANT, "workspace_id": "ws_1",
                "provider": "gmail", "external_id": "gm_1", "subject": "Old thread",
                "from_email": "buyer@acme.test", "ts": ago(20)})
            await db[cv.CONVERSATIONS].insert_many([
                {"id": "cnv_1", "tenant_id": TENANT, "channel": cv.CHANNEL_EMAIL,
                 "company_id": "co_1", "workspace_id": None, "subject": "Renewal"},
                {"id": "cnv_other", "tenant_id": "ten_someone_else",
                 "channel": cv.CHANNEL_EMAIL, "company_id": "co_1", "subject": "Theirs"}])
            base = {"tenant_id": TENANT, "conversation_id": "cnv_1",
                    "channel": cv.CHANNEL_EMAIL, "provider": "gmail", "body": "Hello"}
            await db[cv.MESSAGES].insert_many([
                {**base, "id": "msg_dup", "direction": cv.OUTBOUND, "status": cv.SENT,
                 "provider_message_id": "gm_1", "sent_at": ago(20), "created_at": ago(20)},
                {**base, "id": "msg_reply", "direction": cv.INBOUND, "status": cv.RECEIVED,
                 "provider_message_id": "gm_2", "from_address": "buyer@acme.test",
                 "delivered_at": ago(1), "created_at": ago(1)},
                {**base, "id": "msg_draft", "direction": cv.OUTBOUND, "status": cv.DRAFT,
                 "created_at": ago(0)},
                {**base, "id": "msg_theirs", "tenant_id": "ten_someone_else",
                 "conversation_id": "cnv_other", "direction": cv.INBOUND,
                 "status": cv.RECEIVED, "created_at": ago(0), "delivered_at": ago(0)}])
            await db.integration_connections.insert_one({
                "tenant_id": TENANT, "provider": "gmail", "status": "active",
                "last_success_at": ago(0)})
            return await body()
        finally:
            await server.mclient.drop_database(name)
            server.db = previous

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(wrapped())
    finally:
        loop.close()


def test_activity_lists_conversation_mail_once_beside_the_mirror():
    activity = _run(lambda: server.workspace_activity("ws_1", user=USER))
    ids = [row["id"] for row in activity["communications"]]
    assert ids == ["msg_reply", "comm_1"], ids


def test_the_timeline_shows_a_reply_received_through_the_crm():
    timeline = _run(lambda: server.workspace_timeline(
        "ws_1", sources=None, severity=None, q=None, date_from=None, date_to=None,
        limit=100, offset=0, user=USER))
    items = timeline["items"] if isinstance(timeline, dict) else timeline
    assert any(item["id"] == "msg_reply" and item["event_type"] == "email.message"
               for item in items)
    assert not any(item["id"] in ("msg_draft", "msg_theirs", "msg_dup") for item in items)


def test_a_client_emailed_yesterday_is_not_flagged_as_stale():
    signals = _run(lambda: server.workspace_health_signals("ws_1", user=USER))
    rows = signals["signals"] if isinstance(signals, dict) else signals
    assert not any(row["signal"] == "Stale client communication" for row in rows)
