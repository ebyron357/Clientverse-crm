"""Cron run idempotency / TOCTOU tests (pilot-readiness security pass, Phase 5).

Background: all three /api/cron/* endpoints deduped on X-Webhook-Id via a plain
find_one() followed by insert_one() -- two concurrent requests with the same id could
both pass the find_one check before either insert landed, double-running the job. This
mirrors the fix already used for stripe_webhook_events (a unique index + catching the
duplicate-key error instead of pre-checking).
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_cron_idempotency_unit")
os.environ.setdefault("JWT_SECRET", "cron-idempotency-unit-jwt-secret-long-enough-12")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("WEBHOOK_CRON_SECRET", "cron-idempotency-test-secret-abc123")

import server  # noqa: E402


def run(coro):
    # Motor's AsyncIOMotorClient binds to whatever event loop is running when it first
    # performs an operation; reusing plain asyncio.run() (a fresh loop every call) across
    # many calls in one process breaks it with "Event loop is closed" against a real
    # MongoDB (this only worked against a mongomock substitute, which has no such
    # binding). Bind a fresh client to a fresh loop on every call instead.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
        server.db = server.mclient[os.environ["DB_NAME"]]
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}


async def _ensure_unique_index():
    await server.db.cron_runs.create_index("run_id", unique=True)


def test_concurrent_identical_webhook_ids_claim_the_run_exactly_once():
    run(_ensure_unique_index())
    run_id = f"cron_{uuid.uuid4().hex[:10]}"

    async def scenario():
        results = await asyncio.gather(
            server._claim_cron_run("commitment-risk", run_id),
            server._claim_cron_run("commitment-risk", run_id),
        )
        return results

    results = run(scenario())
    assert sorted(results) == [False, True], "exactly one concurrent claim should win"

    count = run(server.db.cron_runs.count_documents({"run_id": run_id}))
    assert count == 1


def test_a_new_webhook_id_is_not_treated_as_a_duplicate():
    run(_ensure_unique_index())
    run_id = f"cron_{uuid.uuid4().hex[:10]}"
    assert run(server._claim_cron_run("integration-sync", run_id)) is True


def test_cron_commitment_risk_endpoint_rejects_duplicate_webhook_id():
    run(_ensure_unique_index())
    run_id = f"cron_{uuid.uuid4().hex[:10]}"
    headers = {"Authorization": f"Bearer {os.environ['WEBHOOK_CRON_SECRET']}", "X-Webhook-Id": run_id}

    first = run(server.cron_commitment_risk(FakeRequest(headers)))
    second = run(server.cron_commitment_risk(FakeRequest(headers)))

    assert first["accepted"] is True and not first.get("duplicate")
    assert second == {"accepted": True, "duplicate": True}


def test_cron_daily_digest_endpoint_rejects_duplicate_webhook_id():
    run(_ensure_unique_index())
    run_id = f"cron_{uuid.uuid4().hex[:10]}"
    headers = {"Authorization": f"Bearer {os.environ['WEBHOOK_CRON_SECRET']}", "X-Webhook-Id": run_id}

    first = run(server.cron_daily_digest(FakeRequest(headers)))
    second = run(server.cron_daily_digest(FakeRequest(headers)))

    assert first["accepted"] is True and not first.get("duplicate")
    assert second == {"accepted": True, "duplicate": True}
