"""The scheduled-execution evidence chain.

These tests exist because of a specific production failure: the scheduler workflow
reported success on every tick for months while making no production request at all,
and nothing in production could contradict it. Green was not evidence.

What is asserted here is the chain itself -- that production records, for every
scheduled delivery, that it arrived, whether it was authenticated, whether it was a
duplicate, when the job started and finished, and what it returned or raised -- and
that a caller who cannot prove they are the scheduler or an admin cannot read it.
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_cron_ledger_unit")
os.environ.setdefault("JWT_SECRET", "cron-ledger-unit-jwt-secret-long-enough-1234")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("WEBHOOK_CRON_SECRET", "cron-ledger-test-secret-abc123")

import cron_ledger
import server

SECRET = os.environ["WEBHOOK_CRON_SECRET"]


def run(coro):
    # Same rationale as test_cron_idempotency: bind a fresh client to a fresh loop.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
        server.db = server.mclient[os.environ["DB_NAME"]]
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _db(fn):
    return await fn()


class FakeRequest:
    def __init__(self, headers=None, cookies=None):
        self.headers = headers or {}
        self.cookies = cookies or {}


def _headers(run_id, secret=SECRET, agent="pytest-scheduler/1.0"):
    return {"Authorization": f"Bearer {secret}", "X-Webhook-Id": run_id,
            "User-Agent": agent}


def _new_run_id(prefix="led"):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


async def _entries_for(run_id):
    return await server.db[cron_ledger.COLLECTION].find(
        {"run_id": run_id}, {"_id": 0}).sort("received_at", 1).to_list(20)


# --------------------------------------------------------------------------- accepted

def test_an_authenticated_request_records_the_whole_chain():
    run_id = _new_run_id()

    async def scenario():
        await cron_ledger.ensure_indexes(server.db)
        response = await server.cron_second_chance(FakeRequest(_headers(run_id)))
        # The endpoint hands the work to a background task; let it finish so the
        # 'executed' and 'result recorded' stages are real and not raced.
        await asyncio.sleep(0.4)
        return response, await _entries_for(run_id)

    response, entries = run(scenario())

    assert response["accepted"] is True
    assert response["run_id"] == run_id
    assert response["evidence_id"], "the caller must be handed the id of its own evidence"

    assert len(entries) == 1
    entry = entries[0]
    assert entry["id"] == response["evidence_id"]
    assert entry["job"] == "second-chance"
    assert entry["received_at"], "production must record that the request arrived"
    assert "pytest-scheduler" in (entry["source"] or ""), "the caller must be attributable"
    assert entry["status"] == cron_ledger.SUCCEEDED
    assert entry["started_at"], "the job executing is its own observable stage"
    assert entry["finished_at"]
    assert entry["duration_ms"] is not None
    assert entry["result"] is not None, "a run with no recorded result is not evidence"
    assert entry["error"] is None


def test_the_ledger_never_stores_the_shared_secret():
    run_id = _new_run_id()

    async def scenario():
        await server.cron_approval_expiry(FakeRequest(_headers(run_id)))
        await asyncio.sleep(0.2)
        return await _entries_for(run_id)

    entries = run(scenario())
    assert entries
    assert SECRET not in repr(entries)


# ------------------------------------------------------------------------- duplicates

def test_a_duplicate_delivery_is_recorded_as_a_duplicate_not_a_second_run():
    run_id = _new_run_id()

    async def scenario():
        # Deduplication is enforced by the unique index the application creates at
        # startup; without it the test would be measuring a missing index.
        await server.db.cron_runs.create_index("run_id", unique=True)
        first = await server.cron_approval_expiry(FakeRequest(_headers(run_id)))
        second = await server.cron_approval_expiry(FakeRequest(_headers(run_id)))
        await asyncio.sleep(0.2)
        return first, second, await _entries_for(run_id)

    first, second, entries = run(scenario())

    assert not first.get("duplicate")
    assert second["duplicate"] is True
    statuses = [e["status"] for e in entries]
    assert cron_ledger.DUPLICATE in statuses
    # The suppressed delivery must never look like a second execution.
    assert sum(1 for e in entries if e["started_at"]) == 1


# ----------------------------------------------------------------------- authorization

def test_a_rejected_request_is_recorded_so_a_wrong_secret_is_not_silence():
    run_id = _new_run_id()

    async def scenario():
        with pytest.raises(HTTPException) as excinfo:
            await server.cron_second_chance(
                FakeRequest(_headers(run_id, secret="not-the-secret")))
        assert excinfo.value.status_code == 401
        return await _entries_for(run_id)

    entries = run(scenario())
    assert len(entries) == 1
    assert entries[0]["status"] == cron_ledger.UNAUTHORIZED
    assert entries[0]["started_at"] is None, "a rejected request must never run the job"
    assert "not-the-secret" not in repr(entries[0])


def test_the_ledger_is_not_readable_without_the_secret_or_an_admin_session():
    async def scenario():
        with pytest.raises(HTTPException) as excinfo:
            await server._authorize_cron_observer(
                FakeRequest({"Authorization": "Bearer wrong"}))
        return excinfo.value.status_code

    # No cron secret and no session at all: the session path rejects it.
    assert run(scenario()) in (401, 403)


def test_the_scheduler_itself_can_read_the_ledger_back():
    run_id = _new_run_id()

    async def scenario():
        await server.cron_approval_expiry(FakeRequest(_headers(run_id)))
        await asyncio.sleep(0.2)
        return await server.cron_runs(FakeRequest(_headers(run_id)), limit=100)

    payload = run(scenario())
    assert any(entry["run_id"] == run_id for entry in payload["runs"])


# ----------------------------------------------------------------------------- failure

def test_a_failing_job_is_recorded_as_failed_and_its_delivery_can_be_retried():
    run_id = _new_run_id()

    async def scenario():
        entry_id = await cron_ledger.record_request(
            server.db, job="second-chance", run_id=run_id,
            status=cron_ledger.ACCEPTED, source="pytest")
        assert await server._claim_cron_run("second-chance", run_id) is True

        async def boom():
            raise RuntimeError("provider exploded")

        with pytest.raises(RuntimeError):
            await server._run_cron_job("second-chance", run_id, boom, entry_id)

        entry = await server.db[cron_ledger.COLLECTION].find_one(
            {"id": entry_id}, {"_id": 0})
        # A proven failure must release the claim, or the redelivery that would fix it
        # is silently suppressed and the work is lost.
        reclaimed = await server._claim_cron_run("second-chance", run_id)
        return entry, reclaimed

    entry, reclaimed = run(scenario())

    assert entry["status"] == cron_ledger.FAILED
    assert "provider exploded" in (entry["error"] or "")
    assert entry["finished_at"], "a failure is still a recorded outcome"
    assert reclaimed is True, "a proven failure must leave the delivery retryable"


def test_the_evidence_survives_the_claim_being_released():
    """The claim row is transient; the evidence must not be."""
    run_id = _new_run_id()

    async def scenario():
        entry_id = await cron_ledger.record_request(
            server.db, job="work-queue", run_id=run_id,
            status=cron_ledger.ACCEPTED, source="pytest")
        await server._claim_cron_run("work-queue", run_id)
        await server._release_cron_run("work-queue", run_id)
        claims = await server.db.cron_runs.count_documents({"run_id": run_id})
        entry = await server.db[cron_ledger.COLLECTION].find_one({"id": entry_id}, {"_id": 0})
        return claims, entry

    claims, entry = run(scenario())
    assert claims == 0
    assert entry is not None, "releasing a claim must not erase the record that it happened"


# ------------------------------------------------------------------------------ health

def test_health_reports_whether_production_is_being_called_at_all():
    async def scenario():
        before = await cron_ledger.health(server.db, window_minutes=1)
        await server.cron_approval_expiry(FakeRequest(_headers(_new_run_id())))
        await asyncio.sleep(0.2)
        after = await cron_ledger.health(server.db, window_minutes=1)
        return before, after

    before, after = run(scenario())
    assert after["requests_in_window"] > before["requests_in_window"]
    assert after["receiving_scheduled_traffic"] is True
    assert after["last_authenticated_call_at"]


def test_a_window_with_only_rejected_calls_is_not_reported_as_healthy_traffic():
    async def scenario():
        # Isolate the window: only the rejected call below can fall inside it.
        await server.db[cron_ledger.COLLECTION].delete_many({})
        with pytest.raises(HTTPException):
            await server.cron_second_chance(
                FakeRequest(_headers(_new_run_id(), secret="wrong")))
        return await cron_ledger.health(server.db, window_minutes=60)

    health = run(scenario())
    assert health["requests_in_window"] == 1
    assert health["by_status"].get(cron_ledger.UNAUTHORIZED) == 1
    assert health["receiving_scheduled_traffic"] is False, (
        "a scheduler hammering production with the wrong secret is not healthy traffic")
    assert health["last_rejected_call_at"]
