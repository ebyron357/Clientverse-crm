"""Reconciling a dispatch nobody saw complete -- without inviting a duplicate.

A message in `outcome_unknown` may well have reached the client. The only question the
system may ask is whether the provider holds it, and the answer "no" is only worth
something if the lookup could have found it. These tests pin the three ways "no" used
to be believed when it should not have been.
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_reconcile_unit")
os.environ.setdefault("JWT_SECRET", "reconcile-unit-jwt-secret-long-enough-123456")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

import conversations as cv
import gmail_provider
import server

TENANT = "ten_reconcile_a"
ADMIN = {"tenant_id": TENANT, "email": "admin@example.com", "role": "admin"}


class LookupProvider:
    channel = cv.CHANNEL_EMAIL
    name = "gmail"

    def __init__(self, answer):
        self.answer = answer

    async def send(self, **kwargs):  # pragma: no cover - never called here
        raise AssertionError("reconciliation must never send")

    async def locate(self, *, tenant_id, idempotency_key):
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def scenario(answer, *, minutes_ago=60, proven=False, body=None):
    """Run `body(db, message_id)` against an isolated database with `answer` as the
    provider's lookup result, a stranded message `minutes_ago` old, and -- if `proven`
    -- an earlier send whose Message-ID was read back unchanged."""
    name = f"clientverse_reconcile_{uuid.uuid4().hex[:10]}"

    async def wrapped():
        previous_db = server.db
        previous_provider = cv.REGISTRY.get(cv.CHANNEL_EMAIL)
        server.db = server.mclient[name]
        cv.REGISTRY.register(LookupProvider(answer))
        try:
            db = server.db
            when = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
            message_id = f"msg_{uuid.uuid4().hex[:10]}"
            await db[cv.MESSAGES].insert_one({
                "id": message_id, "tenant_id": TENANT, "conversation_id": "cnv_1",
                "channel": cv.CHANNEL_EMAIL, "direction": cv.OUTBOUND,
                "status": cv.OUTCOME_UNKNOWN, "body": "Hello", "approval_id": "apr_1",
                "history": [{"action": cv.OUTCOME_UNKNOWN, "actor": "worker", "at": when,
                             "detail": {}}]})
            if proven:
                await db[cv.MESSAGES].insert_one({
                    "id": "msg_proven", "tenant_id": TENANT, "conversation_id": "cnv_0",
                    "channel": cv.CHANNEL_EMAIL, "direction": cv.OUTBOUND,
                    "status": cv.SENT, "provider": "gmail",
                    "provider_message_id": "gm-proven", "message_id_verified": True,
                    "message_id_rewritten": False, "history": []})
            return await body(db, message_id)
        finally:
            await server.mclient.drop_database(name)
            server.db = previous_db
            if previous_provider:
                cv.REGISTRY.register(previous_provider)
            else:
                cv.REGISTRY._providers.pop(cv.CHANNEL_EMAIL, None)

    return run(wrapped())


async def _sweep_then_status(db, message_id):
    totals = await server.run_reconcile_unknown_sweep(actor="test")
    return totals, (await cv.get_message(db, TENANT, message_id))["status"]


# ------------------------------------------------------------------ the sweep

def test_a_lookup_that_could_not_check_leaves_the_message_unresolved():
    """A reconnect in progress, a refresh that failed, a 403: used to become FAILED."""
    totals, status = scenario(gmail_provider.LookupUnavailable("connection is connecting"),
                              proven=True, body=_sweep_then_status)
    assert status == cv.OUTCOME_UNKNOWN
    assert totals["unresolved"] == 1 and totals["resolved_failed"] == 0


def test_a_recent_dispatch_missing_from_search_is_not_yet_proof():
    totals, status = scenario(None, minutes_ago=2, proven=True, body=_sweep_then_status)
    assert status == cv.OUTCOME_UNKNOWN and totals["unresolved"] == 1


def test_absence_proves_nothing_until_the_tenant_has_shown_gmail_keeps_the_id():
    """If Gmail rewrote Message-IDs, every lookup would come back empty, sent or not."""
    totals, status = scenario(None, proven=False, body=_sweep_then_status)
    assert status == cv.OUTCOME_UNKNOWN and totals["unresolved"] == 1


def test_absence_is_believed_once_it_could_have_been_found():
    totals, status = scenario(None, proven=True, body=_sweep_then_status)
    assert status == cv.FAILED and totals["resolved_failed"] == 1


def test_a_dispatch_the_provider_holds_is_recorded_as_sent():
    totals, status = scenario("gm-found", body=_sweep_then_status)
    assert status == cv.SENT and totals["resolved_sent"] == 1


# ------------------------------------------------------------------ the admin route

def test_the_route_says_why_absence_is_not_proof_and_changes_nothing():
    async def body(db, message_id):
        with pytest.raises(HTTPException) as refused:
            await server.reconcile_message(message_id, None, user=ADMIN)
        return refused.value, (await cv.get_message(db, TENANT, message_id))["status"]

    refused, status = scenario(None, proven=False, body=body)
    assert refused.status_code == 409
    assert refused.detail["reason"] == "absence_not_proof"
    assert status == cv.OUTCOME_UNKNOWN


def test_a_person_who_checked_the_mailbox_can_record_not_sent():
    async def body(db, message_id):
        result = await server.reconcile_message(
            message_id, server.ReconcileInput(confirm_not_sent=True), user=ADMIN)
        return result

    result = scenario(None, proven=False, body=body)
    assert result["status"] == cv.FAILED
    assert "confirmed after checking the mailbox" in result["history"][-1]["detail"]["lookup"]


def test_the_route_never_records_not_sent_when_it_could_not_check():
    async def body(db, message_id):
        with pytest.raises(HTTPException) as failed:
            await server.reconcile_message(
                message_id, server.ReconcileInput(confirm_not_sent=True), user=ADMIN)
        return failed.value, (await cv.get_message(db, TENANT, message_id))["status"]

    failed, status = scenario(gmail_provider.LookupUnavailable("token refresh failed"),
                              body=body)
    assert failed.status_code == 502 and status == cv.OUTCOME_UNKNOWN
