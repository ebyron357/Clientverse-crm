"""Durable work-queue engine tests.

These exercise the engine directly against MongoDB rather than through HTTP, because
the behaviour that matters here — atomic claim under a race, lease expiry after a
worker crash, retry ladder, dead-letter transition — is queue semantics, not routing.
The HTTP surface is covered by test_operations_api.py.
"""

import asyncio
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from work_queue import (
    CLAIMED,
    COMPLETED,
    DEAD_LETTER,
    PROCESSING,
    QUEUED,
    RETRY_SCHEDULED,
    InvalidTransition,
    WorkQueue,
    WorkQueueError,
    backoff_seconds,
    run_worker_tick,
)

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")


_LOOP = None


def run(coro):
    """Run a coroutine on a loop this module owns.

    The suite runs under xdist with `--dist loadscope`, so several modules share one
    worker process. Relying on the ambient event loop makes these tests fail when an
    earlier module closes it; owning the loop here keeps them independent.
    """
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


@pytest.fixture()
def queue_env():
    """Isolated database per test, torn down afterwards."""
    db_name = f"cv_wq_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    queue = WorkQueue(client[db_name])
    run(queue.ensure_indexes())
    yield queue
    run(client.drop_database(db_name))
    client.close()


TENANT = "ten_test_a"
OTHER_TENANT = "ten_test_b"


def test_enqueue_claim_complete_happy_path(queue_env):
    item = run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="demo.job",
                                 payload={"n": 1}))
    assert item["status"] == QUEUED
    assert item["attempts"] == 0

    claimed = run(queue_env.claim(worker_id="w1", queue="system", limit=5))
    assert len(claimed) == 1
    assert claimed[0]["status"] == CLAIMED
    assert claimed[0]["attempts"] == 1
    assert claimed[0]["lease_owner"] == "w1"

    processing = run(queue_env.start_processing(item["id"], tenant_id=TENANT, worker_id="w1"))
    assert processing["status"] == PROCESSING

    done = run(queue_env.complete(item["id"], tenant_id=TENANT, result={"ok": True}))
    assert done["status"] == COMPLETED
    assert done["completed_at"]
    assert done["result"] == {"ok": True}


def test_concurrent_claim_race_yields_one_winner(queue_env):
    run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="demo.job"))

    async def _race():
        return await asyncio.gather(
            queue_env.claim(worker_id="w1", queue="system", limit=1),
            queue_env.claim(worker_id="w2", queue="system", limit=1),
            queue_env.claim(worker_id="w3", queue="system", limit=1),
        )

    results = run(_race())
    winners = [r for r in results if r]
    assert len(winners) == 1, "exactly one worker may hold the item"
    assert len(winners[0]) == 1


def test_expired_lease_is_recovered_for_retry(queue_env):
    item = run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="demo.job"))
    run(queue_env.claim(worker_id="w1", queue="system", limit=1, lease_seconds=0))

    recovery = run(queue_env.recover_expired_leases())
    assert recovery["recovered"] == 1

    refreshed = run(queue_env.get(item["id"], tenant_id=TENANT))
    assert refreshed["status"] == RETRY_SCHEDULED
    assert refreshed["lease_owner"] is None
    assert "Lease expired" in refreshed["last_error"]


def test_worker_crash_does_not_strand_work(queue_env):
    """A worker that claims and never reports is indistinguishable from a crash."""
    item = run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="demo.job",
                                 max_attempts=3))
    run(queue_env.claim(worker_id="crashed-worker", queue="system", limit=1, lease_seconds=0))
    run(queue_env.recover_expired_leases())

    # Available again after the backoff window is cleared for the test.
    run(queue_env.collection.update_one({"id": item["id"]},
                                        {"$set": {"available_at": "2000-01-01T00:00:00+00:00"}}))
    reclaimed = run(queue_env.claim(worker_id="healthy-worker", queue="system", limit=1))
    assert len(reclaimed) == 1
    assert reclaimed[0]["lease_owner"] == "healthy-worker"
    assert reclaimed[0]["attempts"] == 2


def test_retry_then_dead_letter_after_max_attempts(queue_env):
    item = run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="demo.job",
                                 max_attempts=2))
    run(queue_env.claim(worker_id="w1", queue="system", limit=1))
    retried = run(queue_env.fail(item["id"], tenant_id=TENANT, reason="transient upstream error"))
    assert retried["status"] == RETRY_SCHEDULED
    assert retried["last_error"] == "transient upstream error"

    run(queue_env.collection.update_one({"id": item["id"]},
                                        {"$set": {"available_at": "2000-01-01T00:00:00+00:00"}}))
    run(queue_env.claim(worker_id="w1", queue="system", limit=1))
    dead = run(queue_env.fail(item["id"], tenant_id=TENANT, reason="still failing"))
    assert dead["status"] == DEAD_LETTER
    assert dead["failure_reason"] == "still failing"


def test_non_retryable_failure_dead_letters_immediately(queue_env):
    item = run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="demo.job",
                                 max_attempts=5))
    run(queue_env.claim(worker_id="w1", queue="system", limit=1))
    dead = run(queue_env.fail(item["id"], tenant_id=TENANT, reason="unknown type",
                              retryable=False))
    assert dead["status"] == DEAD_LETTER


def test_backoff_is_exponential_and_capped():
    assert backoff_seconds(1) < backoff_seconds(2) < backoff_seconds(3)
    assert backoff_seconds(50) == backoff_seconds(60), "backoff must be capped"


def test_duplicate_submission_is_deduplicated_by_key(queue_env):
    first = run(queue_env.enqueue(tenant_id=TENANT, queue="second_chance",
                                  item_type="demo.job", dedupe_key="opp:1"))
    second = run(queue_env.enqueue(tenant_id=TENANT, queue="second_chance",
                                   item_type="demo.job", dedupe_key="opp:1"))
    assert second["id"] == first["id"]
    assert second.get("deduplicated") is True
    assert second["occurrence_count"] == 2
    assert run(queue_env.collection.count_documents({"tenant_id": TENANT})) == 1


def test_idempotent_replay_of_submission(queue_env):
    key = "idem-123"
    first = run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="demo.job",
                                  idempotency_key=key))
    second = run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="demo.job",
                                   idempotency_key=key))
    assert second["id"] == first["id"]
    assert run(queue_env.collection.count_documents({"tenant_id": TENANT})) == 1


def test_dedupe_key_does_not_block_a_new_item_once_closed(queue_env):
    first = run(queue_env.enqueue(tenant_id=TENANT, queue="second_chance",
                                  item_type="demo.job", dedupe_key="opp:2"))
    run(queue_env.claim(worker_id="w1", queue="second_chance", limit=1))
    run(queue_env.complete(first["id"], tenant_id=TENANT))
    second = run(queue_env.enqueue(tenant_id=TENANT, queue="second_chance",
                                   item_type="demo.job", dedupe_key="opp:2"))
    assert second["id"] != first["id"]


def test_tenant_isolation_on_claim_and_read(queue_env):
    mine = run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="demo.job"))
    theirs = run(queue_env.enqueue(tenant_id=OTHER_TENANT, queue="system", item_type="demo.job"))

    claimed = run(queue_env.claim(worker_id="w1", queue="system", tenant_id=TENANT, limit=10))
    assert [c["id"] for c in claimed] == [mine["id"]]

    assert run(queue_env.get(theirs["id"], tenant_id=TENANT)) is None
    listed = run(queue_env.list_items(tenant_id=TENANT))
    assert all(i["tenant_id"] == TENANT for i in listed)

    with pytest.raises(WorkQueueError):
        run(queue_env.complete(theirs["id"], tenant_id=TENANT))


def test_manual_replay_requires_failed_or_dead_letter(queue_env):
    item = run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="demo.job",
                                 max_attempts=1))
    with pytest.raises(InvalidTransition):
        run(queue_env.replay(item["id"], tenant_id=TENANT, actor="admin@example.com"))

    run(queue_env.claim(worker_id="w1", queue="system", limit=1))
    run(queue_env.fail(item["id"], tenant_id=TENANT, reason="boom"))
    replayed = run(queue_env.replay(item["id"], tenant_id=TENANT, actor="admin@example.com"))
    assert replayed["status"] == QUEUED
    assert replayed["attempts"] == 0


def test_invalid_state_transition_is_rejected(queue_env):
    item = run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="demo.job"))
    run(queue_env.claim(worker_id="w1", queue="system", limit=1))
    run(queue_env.complete(item["id"], tenant_id=TENANT))
    # Completed is terminal: nothing may move out of it.
    with pytest.raises(InvalidTransition):
        run(queue_env.start_processing(item["id"], tenant_id=TENANT, worker_id="w1"))
    with pytest.raises(InvalidTransition):
        run(queue_env.replay(item["id"], tenant_id=TENANT, actor="admin@example.com"))


def test_acknowledge_and_resolve_records_the_operator(queue_env):
    item = run(queue_env.enqueue(tenant_id=TENANT, queue="second_chance",
                                 item_type="second_chance.stalled_lead"))
    acked = run(queue_env.acknowledge(item["id"], tenant_id=TENANT, actor="ops@example.com"))
    assert acked["acknowledged_by"] == "ops@example.com"

    resolved = run(queue_env.resolve(item["id"], tenant_id=TENANT, actor="ops@example.com",
                                     resolution="contacted"))
    assert resolved["resolution"] == "contacted"
    assert resolved["resolved_by"] == "ops@example.com"
    assert resolved["status"] == COMPLETED


def test_bounded_concurrency_caps_a_single_claim(queue_env):
    for i in range(40):
        run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="demo.job",
                              idempotency_key=f"bulk-{i}"))
    claimed = run(queue_env.claim(worker_id="w1", queue="system", limit=1000))
    assert len(claimed) <= 25


def test_stats_reports_open_and_operator_attention(queue_env):
    run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="demo.job",
                          idempotency_key="s1"))
    dead = run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="demo.job",
                                 idempotency_key="s2", max_attempts=1))
    run(queue_env.claim(worker_id="w1", queue="system", limit=10))
    run(queue_env.fail(dead["id"], tenant_id=TENANT, reason="fatal", retryable=False))

    stats = run(queue_env.stats(tenant_id=TENANT))
    assert stats["total"] == 2
    assert stats["dead_letter"] == 1
    assert stats["needs_operator"] == 1


def test_worker_tick_processes_and_dead_letters_unknown_types(queue_env):
    run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="known.job",
                          idempotency_key="k1"))
    unknown = run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="mystery.job",
                                    idempotency_key="k2"))

    async def handler(item):
        return {"handled": item["id"]}

    result = run(run_worker_tick(queue_env, {"known.job": handler}, queue_name="system"))
    assert result["processed"] == 1
    assert result["failed"] == 1

    unknown_after = run(queue_env.get(unknown["id"], tenant_id=TENANT))
    assert unknown_after["status"] == DEAD_LETTER
    assert "No handler registered" in unknown_after["failure_reason"]


def test_worker_tick_retries_a_failing_handler(queue_env):
    item = run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="flaky.job",
                                 max_attempts=3))

    async def handler(_item):
        raise RuntimeError("upstream unavailable")

    result = run(run_worker_tick(queue_env, {"flaky.job": handler}, queue_name="system"))
    assert result["failed"] == 1
    after = run(queue_env.get(item["id"], tenant_id=TENANT))
    assert after["status"] == RETRY_SCHEDULED
    assert "upstream unavailable" in after["last_error"]


def test_claim_rotates_across_tenants_rather_than_starving_them(queue_env):
    """A tenant with a backlog must not consume the whole bounded tick."""
    for i in range(30):
        run(queue_env.enqueue(tenant_id="ten_noisy", queue="system", item_type="demo.job",
                              idempotency_key=f"noisy-{i}"))
    run(queue_env.enqueue(tenant_id="ten_quiet", queue="system", item_type="demo.job",
                          idempotency_key="quiet-1"))

    claimed = run(queue_env.claim(worker_id="w1", queue="system", limit=10))
    tenants = {item["tenant_id"] for item in claimed}
    assert "ten_quiet" in tenants, "the quiet tenant must be served on the same tick"
    assert len(claimed) == 10


def test_claim_still_drains_a_single_tenant_when_scoped(queue_env):
    for i in range(5):
        run(queue_env.enqueue(tenant_id=TENANT, queue="system", item_type="demo.job",
                              idempotency_key=f"scoped-{i}"))
    run(queue_env.enqueue(tenant_id=OTHER_TENANT, queue="system", item_type="demo.job",
                          idempotency_key="other-1"))
    claimed = run(queue_env.claim(worker_id="w1", queue="system", tenant_id=TENANT, limit=10))
    assert len(claimed) == 5
    assert {c["tenant_id"] for c in claimed} == {TENANT}
