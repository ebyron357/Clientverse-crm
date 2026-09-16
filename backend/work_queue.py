"""Durable, tenant-scoped work queue.

This is the persistence foundation the canonical governing document (E-05) requires:
every item lives in MongoDB, survives process restarts, is leased to exactly one
worker at a time, retries with backoff, and lands in a dead-letter state rather than
disappearing. Nothing here holds state in memory.

The queue is deliberately generic. Producers (Second Chance detectors, scheduled
follow-up, future channel work) enqueue typed items; a worker tick claims, processes
and completes them. Operator-facing items additionally carry acknowledgement and
resolution so a human closing the loop is recorded.
"""

from __future__ import annotations

import asyncio
import math
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Awaitable, Optional

QUEUED = "queued"
CLAIMED = "claimed"
PROCESSING = "processing"
COMPLETED = "completed"
RETRY_SCHEDULED = "retry_scheduled"
FAILED = "failed"
DEAD_LETTER = "dead_letter"

STATES = (QUEUED, CLAIMED, PROCESSING, COMPLETED, RETRY_SCHEDULED, FAILED, DEAD_LETTER)
OPEN_STATES = (QUEUED, CLAIMED, PROCESSING, RETRY_SCHEDULED)
TERMINAL_STATES = (COMPLETED, DEAD_LETTER)

# Explicit transition matrix. Anything not listed is rejected by `_assert_transition`,
# so an invalid state change fails loudly instead of silently corrupting the queue.
ALLOWED_TRANSITIONS = {
    # queued -> completed is an operator closing an item that no worker ever claimed.
    # Second Chance candidates live exactly there: a person resolves them, so the
    # transition is legitimate rather than a special case bolted onto `resolve`.
    QUEUED: {CLAIMED, COMPLETED, FAILED, DEAD_LETTER},
    RETRY_SCHEDULED: {CLAIMED, COMPLETED, FAILED, DEAD_LETTER},
    CLAIMED: {PROCESSING, COMPLETED, RETRY_SCHEDULED, FAILED, DEAD_LETTER, QUEUED},
    PROCESSING: {COMPLETED, RETRY_SCHEDULED, FAILED, DEAD_LETTER, QUEUED},
    FAILED: {QUEUED},
    DEAD_LETTER: {QUEUED},
    COMPLETED: set(),
}

DEFAULT_MAX_ATTEMPTS = int(os.environ.get("WORK_QUEUE_MAX_ATTEMPTS", "5"))
DEFAULT_LEASE_SECONDS = int(os.environ.get("WORK_QUEUE_LEASE_SECONDS", "120"))
DEFAULT_BACKOFF_SECONDS = int(os.environ.get("WORK_QUEUE_BACKOFF_SECONDS", "30"))
MAX_BACKOFF_SECONDS = int(os.environ.get("WORK_QUEUE_MAX_BACKOFF_SECONDS", "3600"))
# Bounded concurrency: a single claim call never takes more than this many items, so
# one busy tenant cannot monopolise a worker tick.
MAX_CLAIM_BATCH = int(os.environ.get("WORK_QUEUE_MAX_CLAIM_BATCH", "25"))


class WorkQueueError(Exception):
    """Raised for invalid queue operations (bad transition, unknown item)."""


class InvalidTransition(WorkQueueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _parse(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def backoff_seconds(attempts: int, base: int = DEFAULT_BACKOFF_SECONDS) -> int:
    """Exponential backoff, capped. `attempts` is the number already made."""
    if attempts <= 0:
        return base
    return int(min(MAX_BACKOFF_SECONDS, base * math.pow(2, attempts - 1)))


def _assert_transition(current: str, target: str) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"Cannot move work item from '{current}' to '{target}'")


def _history(action: str, actor: str, detail: Optional[dict] = None) -> dict:
    return {"action": action, "actor": actor, "at": _iso(_now()), "detail": detail or {}}


class WorkQueue:
    """MongoDB-backed durable queue. All reads and writes are tenant-scoped."""

    def __init__(self, db, collection: str = "work_queue"):
        self.db = db
        self.collection = db[collection]

    async def ensure_indexes(self) -> None:
        # Idempotency is enforced by the database, not by application checks, so two
        # concurrent producers cannot both insert the same logical item.
        await self.collection.create_index(
            [("tenant_id", 1), ("idempotency_key", 1)],
            unique=True,
            partialFilterExpression={"idempotency_key": {"$type": "string"}},
        )
        await self.collection.create_index([("tenant_id", 1), ("status", 1), ("available_at", 1)])
        await self.collection.create_index([("tenant_id", 1), ("dedupe_key", 1), ("status", 1)])
        # Deduplication is enforced by the database, not by a read-then-insert check.
        # `active_dedupe_key` mirrors `dedupe_key` while the item is open and is cleared
        # when it reaches a terminal state, so at most one open item exists per key while
        # a later, genuinely new occurrence can still be created.
        await self.collection.create_index(
            [("tenant_id", 1), ("active_dedupe_key", 1)],
            unique=True,
            partialFilterExpression={"active_dedupe_key": {"$type": "string"}},
        )
        await self.collection.create_index([("status", 1), ("lease_expires_at", 1)])
        await self.collection.create_index([("tenant_id", 1), ("created_at", -1)])

    # ---------------------------------------------------------------- produce

    async def enqueue(
        self,
        *,
        tenant_id: str,
        queue: str,
        item_type: str,
        payload: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
        dedupe_key: Optional[str] = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        available_at: Optional[datetime] = None,
        priority: int = 100,
        source_ref: Optional[str] = None,
        evidence: Optional[dict] = None,
        actor: str = "system",
        workspace_id: Optional[str] = None,
    ) -> dict:
        """Insert an item, or return the existing one when it is a duplicate.

        Two independent guards:
          * `idempotency_key` — a unique index; a retried submission returns the
            original item instead of creating a second one.
          * `dedupe_key` — while an item with the same key is still open, a new
            detection folds into it rather than piling up duplicates.
        """
        if not tenant_id:
            raise WorkQueueError("tenant_id is required")
        now = _now()

        if dedupe_key:
            # Fold into the open item for this key if one exists. The unique index on
            # `active_dedupe_key` below is what makes this safe under concurrency; this
            # read is only the fast path.
            folded = await self.collection.find_one_and_update(
                {"tenant_id": tenant_id, "active_dedupe_key": dedupe_key},
                {"$set": {"updated_at": _iso(now), "last_seen_at": _iso(now)},
                 "$inc": {"occurrence_count": 1}},
                projection={"_id": 0},
                return_document=True,
            )
            if folded:
                folded["deduplicated"] = True
                return folded

        item = {
            "id": f"wq_{uuid.uuid4().hex[:12]}",
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "queue": queue,
            "type": item_type,
            "payload": payload or {},
            "idempotency_key": idempotency_key,
            "dedupe_key": dedupe_key,
            "active_dedupe_key": dedupe_key,
            "status": QUEUED,
            "priority": priority,
            "attempts": 0,
            "max_attempts": max(1, int(max_attempts)),
            "available_at": _iso(available_at or now),
            "lease_owner": None,
            "lease_expires_at": None,
            "last_error": None,
            "failure_reason": None,
            "result": None,
            "source_ref": source_ref,
            "evidence": evidence or {},
            "occurrence_count": 1,
            "acknowledged_at": None,
            "acknowledged_by": None,
            "resolved_at": None,
            "resolved_by": None,
            "resolution": None,
            "created_at": _iso(now),
            "updated_at": _iso(now),
            "last_seen_at": _iso(now),
            "completed_at": None,
            "history": [_history("enqueued", actor, {"queue": queue, "type": item_type})],
        }
        try:
            await self.collection.insert_one(dict(item))
        except Exception as exc:  # a concurrent producer won the race
            if "duplicate key" not in str(exc).lower():
                raise
            criteria = None
            if dedupe_key:
                criteria = {"tenant_id": tenant_id, "active_dedupe_key": dedupe_key}
            elif idempotency_key:
                criteria = {"tenant_id": tenant_id, "idempotency_key": idempotency_key}
            if criteria:
                existing = await self.collection.find_one_and_update(
                    criteria,
                    {"$set": {"updated_at": _iso(now), "last_seen_at": _iso(now)},
                     "$inc": {"occurrence_count": 1}},
                    projection={"_id": 0}, return_document=True,
                )
                if existing:
                    existing["deduplicated"] = True
                    return existing
            raise
        item.pop("_id", None)
        return item

    # ---------------------------------------------------------------- consume

    async def _claim_one(self, *, worker_id: str, queue: Optional[str], tenant_id: Optional[str],
                         lease_seconds: int) -> Optional[dict]:
        now = _now()
        criteria: dict[str, Any] = {
            "status": {"$in": [QUEUED, RETRY_SCHEDULED]},
            "available_at": {"$lte": _iso(now)},
        }
        if queue:
            criteria["queue"] = queue
        if tenant_id:
            criteria["tenant_id"] = tenant_id
        return await self.collection.find_one_and_update(
            criteria,
            {
                "$set": {
                    "status": CLAIMED,
                    "lease_owner": worker_id,
                    "lease_expires_at": _iso(now + timedelta(seconds=lease_seconds)),
                    "updated_at": _iso(now),
                },
                "$inc": {"attempts": 1},
                "$push": {"history": _history("claimed", worker_id, {"lease_seconds": lease_seconds})},
            },
            sort=[("priority", 1), ("created_at", 1)],
            projection={"_id": 0},
            return_document=True,
        )

    async def _tenants_with_due_work(self, queue: Optional[str], limit: int = 500) -> list[str]:
        """Tenants with due work, longest-waiting first.

        Ordering by each tenant's oldest due item removes the starting-index bias of a
        plain `distinct`: a tenant that has been waiting cannot be perpetually skipped
        because it sorts late, no matter how many ticks run.
        """
        criteria: dict[str, Any] = {
            "status": {"$in": [QUEUED, RETRY_SCHEDULED]},
            "available_at": {"$lte": _iso(_now())},
        }
        if queue:
            criteria["queue"] = queue
        pipeline = [
            {"$match": criteria},
            {"$group": {"_id": "$tenant_id", "oldest": {"$min": "$available_at"}}},
            {"$sort": {"oldest": 1}},
            {"$limit": int(limit)},
        ]
        return [row["_id"] async for row in self.collection.aggregate(pipeline)]

    async def claim(
        self,
        *,
        worker_id: str,
        queue: Optional[str] = None,
        tenant_id: Optional[str] = None,
        limit: int = 10,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> list[dict]:
        """Atomically lease up to `limit` due items.

        Each item is taken with a single `find_one_and_update`, so two workers racing
        for the same item cannot both win it.

        Across tenants the claim rotates round-robin rather than draining a global
        priority order. Without that, a tenant with hundreds of due items starves every
        other tenant on a bounded tick — which is exactly what a shared queue in a
        multi-tenant product must not do.
        """
        limit = max(1, min(int(limit), MAX_CLAIM_BATCH))
        claimed: list[dict] = []

        if tenant_id:
            for _ in range(limit):
                doc = await self._claim_one(worker_id=worker_id, queue=queue,
                                            tenant_id=tenant_id, lease_seconds=lease_seconds)
                if not doc:
                    break
                claimed.append(doc)
            return claimed

        tenants = await self._tenants_with_due_work(queue)
        if not tenants:
            return claimed
        exhausted: set[str] = set()
        while len(claimed) < limit and len(exhausted) < len(tenants):
            for candidate in tenants:
                if len(claimed) >= limit:
                    break
                if candidate in exhausted:
                    continue
                doc = await self._claim_one(worker_id=worker_id, queue=queue,
                                            tenant_id=candidate, lease_seconds=lease_seconds)
                if doc:
                    claimed.append(doc)
                else:
                    exhausted.add(candidate)
        return claimed

    async def start_processing(self, item_id: str, *, tenant_id: str, worker_id: str) -> dict:
        return await self._transition(
            item_id, tenant_id, PROCESSING, actor=worker_id, expect_owner=worker_id
        )

    async def heartbeat(self, item_id: str, *, tenant_id: str, worker_id: str,
                        lease_seconds: int = DEFAULT_LEASE_SECONDS) -> dict:
        now = _now()
        doc = await self.collection.find_one_and_update(
            {"id": item_id, "tenant_id": tenant_id, "lease_owner": worker_id,
             "status": {"$in": [CLAIMED, PROCESSING]}},
            {"$set": {"lease_expires_at": _iso(now + timedelta(seconds=lease_seconds)),
                      "updated_at": _iso(now)}},
            projection={"_id": 0},
            return_document=True,
        )
        if not doc:
            raise WorkQueueError("Lease is no longer held by this worker")
        return doc

    async def complete(self, item_id: str, *, tenant_id: str, actor: str = "worker",
                       result: Optional[dict] = None, worker_id: Optional[str] = None) -> dict:
        """Finish an item.

        `worker_id` must be supplied by a worker. Without it a stale worker whose lease
        already expired — and whose item another worker has since claimed — could mark
        the live attempt complete.
        """
        return await self._transition(
            item_id, tenant_id, COMPLETED, actor=actor,
            extra={"result": result or {}, "completed_at": _iso(_now()),
                   "lease_owner": None, "lease_expires_at": None,
                   "active_dedupe_key": None},
            expect_owner=worker_id,
        )

    async def fail(self, item_id: str, *, tenant_id: str, reason: str, actor: str = "worker",
                   retryable: bool = True, worker_id: Optional[str] = None) -> dict:
        """Record a failure: reschedule with backoff, or dead-letter when exhausted.

        As with `complete`, a worker must identify itself so a stale attempt cannot
        fail an item that now belongs to a different worker.
        """
        current = await self.collection.find_one({"id": item_id, "tenant_id": tenant_id}, {"_id": 0})
        if not current:
            raise WorkQueueError("Work item not found")
        attempts = int(current.get("attempts", 0))
        max_attempts = int(current.get("max_attempts", DEFAULT_MAX_ATTEMPTS))
        if not retryable or attempts >= max_attempts:
            return await self._transition(
                item_id, tenant_id, DEAD_LETTER, actor=actor,
                extra={"last_error": reason, "failure_reason": reason,
                       "lease_owner": None, "lease_expires_at": None,
                       "active_dedupe_key": None},
                detail={"attempts": attempts, "max_attempts": max_attempts, "retryable": retryable},
                expect_owner=worker_id,
            )
        delay = backoff_seconds(attempts)
        return await self._transition(
            item_id, tenant_id, RETRY_SCHEDULED, actor=actor,
            extra={"last_error": reason, "lease_owner": None, "lease_expires_at": None,
                   "available_at": _iso(_now() + timedelta(seconds=delay))},
            detail={"attempts": attempts, "retry_in_seconds": delay},
            expect_owner=worker_id,
        )

    # ------------------------------------------------------------- recovery

    async def recover_expired_leases(self, *, actor: str = "recovery", limit: int = 100) -> dict:
        """Return items whose worker died mid-flight.

        A crashed worker leaves an item `claimed`/`processing` with a lease that stops
        being renewed. Once the lease expires the item becomes eligible again (or
        dead-letters when its attempts are exhausted), so work is never stranded.
        """
        now = _now()
        recovered, dead_lettered = 0, 0
        cursor = self.collection.find(
            {"status": {"$in": [CLAIMED, PROCESSING]}, "lease_expires_at": {"$lt": _iso(now)}},
            {"_id": 0},
        ).limit(limit)
        for doc in await cursor.to_list(limit):
            attempts = int(doc.get("attempts", 0))
            max_attempts = int(doc.get("max_attempts", DEFAULT_MAX_ATTEMPTS))
            reason = "Lease expired before the worker reported completion"
            # The cursor is only a snapshot. Every recovery update re-asserts the same
            # owner and an expiry still in the past, so a worker that heartbeats between
            # the read and the write keeps its item instead of being recovered out from
            # under itself.
            still_expired = {"lease_owner": doc.get("lease_owner"),
                             "lease_expires_at": {"$lt": _iso(_now())}}
            try:
                if attempts >= max_attempts:
                    await self._transition(
                        doc["id"], doc["tenant_id"], DEAD_LETTER, actor=actor,
                        extra={"last_error": reason, "failure_reason": reason,
                               "lease_owner": None, "lease_expires_at": None,
                               "active_dedupe_key": None},
                        detail={"attempts": attempts, "max_attempts": max_attempts},
                        extra_criteria=still_expired,
                    )
                    dead_lettered += 1
                else:
                    delay = backoff_seconds(attempts)
                    await self._transition(
                        doc["id"], doc["tenant_id"], RETRY_SCHEDULED, actor=actor,
                        extra={"last_error": reason, "lease_owner": None, "lease_expires_at": None,
                               "available_at": _iso(now + timedelta(seconds=delay))},
                        detail={"attempts": attempts, "retry_in_seconds": delay},
                        extra_criteria=still_expired,
                    )
                    recovered += 1
            except WorkQueueError:
                # Either the transition is no longer valid or the worker renewed its
                # lease first. Both mean this item is not ours to recover.
                continue
        return {"recovered": recovered, "dead_lettered": dead_lettered}

    async def replay(self, item_id: str, *, tenant_id: str, actor: str) -> dict:
        """Operator-initiated safe replay of a failed or dead-lettered item."""
        current = await self.collection.find_one({"id": item_id, "tenant_id": tenant_id}, {"_id": 0})
        if not current:
            raise WorkQueueError("Work item not found")
        if current.get("status") not in (FAILED, DEAD_LETTER):
            raise InvalidTransition("Only failed or dead-lettered work can be replayed")
        return await self._transition(
            item_id, tenant_id, QUEUED, actor=actor,
            extra={"attempts": 0, "available_at": _iso(_now()), "lease_owner": None,
                   "lease_expires_at": None, "last_error": None,
                   "active_dedupe_key": current.get("dedupe_key")},
            detail={"replayed_from": current.get("status")},
        )

    # --------------------------------------------------------- operator view

    async def acknowledge(self, item_id: str, *, tenant_id: str, actor: str) -> dict:
        now = _iso(_now())
        doc = await self.collection.find_one_and_update(
            {"id": item_id, "tenant_id": tenant_id},
            {"$set": {"acknowledged_at": now, "acknowledged_by": actor, "updated_at": now},
             "$push": {"history": _history("acknowledged", actor)}},
            projection={"_id": 0},
            return_document=True,
        )
        if not doc:
            raise WorkQueueError("Work item not found")
        return doc

    async def resolve(self, item_id: str, *, tenant_id: str, actor: str,
                      resolution: str = "resolved") -> dict:
        current = await self.collection.find_one({"id": item_id, "tenant_id": tenant_id}, {"_id": 0})
        if not current:
            raise WorkQueueError("Work item not found")
        if current.get("status") in (CLAIMED, PROCESSING) and current.get("lease_owner"):
            # A worker holds this item right now. Completing it here would make that
            # worker's own completion fail, so the operator is told to wait rather than
            # silently creating a race.
            raise InvalidTransition(
                "This item is being processed by a worker right now; resolve it once the "
                "current attempt finishes"
            )
        now = _iso(_now())
        extra = {"resolved_at": now, "resolved_by": actor, "resolution": resolution,
                 "lease_owner": None, "lease_expires_at": None, "active_dedupe_key": None}
        if current.get("status") in TERMINAL_STATES:
            doc = await self.collection.find_one_and_update(
                {"id": item_id, "tenant_id": tenant_id},
                {"$set": {**extra, "updated_at": now},
                 "$push": {"history": _history("resolved", actor, {"resolution": resolution})}},
                projection={"_id": 0}, return_document=True,
            )
            return doc
        return await self._transition(
            item_id, tenant_id, COMPLETED, actor=actor,
            extra={**extra, "completed_at": now},
            detail={"resolution": resolution},
            action="resolved",
        )

    async def list_items(self, *, tenant_id: str, status: Optional[str] = None,
                         queue: Optional[str] = None, item_type: Optional[str] = None,
                         limit: int = 100) -> list[dict]:
        criteria: dict[str, Any] = {"tenant_id": tenant_id}
        if status == "open":
            criteria["status"] = {"$in": list(OPEN_STATES)}
        elif status:
            criteria["status"] = status
        if queue:
            criteria["queue"] = queue
        if item_type:
            criteria["type"] = item_type
        limit = max(1, min(int(limit), 500))
        return await self.collection.find(criteria, {"_id": 0}).sort("created_at", -1).to_list(limit)

    async def get(self, item_id: str, *, tenant_id: str) -> Optional[dict]:
        return await self.collection.find_one({"id": item_id, "tenant_id": tenant_id}, {"_id": 0})

    async def set_payload_fields(self, item_id: str, *, tenant_id: str,
                                 fields: dict) -> Optional[dict]:
        """Merge keys into a queued item's payload without touching anything else.

        `enqueue()` returns the *existing* item when a detection folds into an open one,
        so a caller that wants to record something about that item — a link back to the
        record it belongs to — has no other way to make the change durable. Scoped to the
        payload, so it cannot be used to move an item's state behind the state machine.
        """
        if not fields:
            return await self.get(item_id, tenant_id=tenant_id)
        return await self.collection.find_one_and_update(
            {"id": item_id, "tenant_id": tenant_id},
            {"$set": {**{f"payload.{k}": v for k, v in fields.items()},
                      "updated_at": _iso(_now())}},
            projection={"_id": 0}, return_document=True)

    async def stats(self, *, tenant_id: str) -> dict:
        counts = {state: 0 for state in STATES}
        pipeline = [{"$match": {"tenant_id": tenant_id}},
                    {"$group": {"_id": "$status", "count": {"$sum": 1}}}]
        async for row in self.collection.aggregate(pipeline):
            if row["_id"] in counts:
                counts[row["_id"]] = row["count"]
        counts["open"] = sum(counts[s] for s in OPEN_STATES)
        counts["total"] = sum(counts[s] for s in STATES)
        counts["needs_operator"] = counts[DEAD_LETTER] + counts[FAILED]
        return counts

    # ------------------------------------------------------------- internals

    async def _transition(self, item_id: str, tenant_id: str, target: str, *, actor: str,
                          extra: Optional[dict] = None, detail: Optional[dict] = None,
                          expect_owner: Optional[str] = None, action: Optional[str] = None,
                          extra_criteria: Optional[dict] = None) -> dict:
        current = await self.collection.find_one({"id": item_id, "tenant_id": tenant_id}, {"_id": 0})
        if not current:
            raise WorkQueueError("Work item not found")
        _assert_transition(current.get("status", QUEUED), target)
        if expect_owner and current.get("lease_owner") != expect_owner:
            raise WorkQueueError("Lease is no longer held by this worker")
        if expect_owner is None and current.get("lease_owner") and target in TERMINAL_STATES:
            # A leased item may only be finished by its lease holder. An anonymous
            # caller here is either a bug or a stale worker.
            raise WorkQueueError(
                "This work item is leased to a worker and cannot be finished anonymously"
            )
        updates = {"status": target, "updated_at": _iso(_now())}
        updates.update(extra or {})
        criteria: dict[str, Any] = {"id": item_id, "tenant_id": tenant_id,
                                    "status": current["status"]}
        if expect_owner:
            # Part of the same atomic update, not a separate read: a lease that expires
            # between the check and the write must lose the race, not win it.
            criteria["lease_owner"] = expect_owner
        criteria.update(extra_criteria or {})
        doc = await self.collection.find_one_and_update(
            criteria,
            {"$set": updates,
             "$push": {"history": _history(action or target, actor, detail)}},
            projection={"_id": 0},
            return_document=True,
        )
        if not doc:
            # Another worker changed the row between read and write.
            raise InvalidTransition(f"Work item changed state before it could move to '{target}'")
        return doc


async def _keep_lease_alive(queue: "WorkQueue", item: dict, worker_id: str,
                            lease_seconds: int) -> None:
    """Renew a lease while its handler runs.

    Without this, any handler slower than the lease is recovered mid-flight and the same
    job runs twice. The renewal interval is deliberately well inside the lease so a
    single slow renewal does not lose it.
    """
    interval = max(1, lease_seconds // 3)
    while True:
        await asyncio.sleep(interval)
        try:
            await queue.heartbeat(item["id"], tenant_id=item["tenant_id"],
                                  worker_id=worker_id, lease_seconds=lease_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            # The lease is gone: stop renewing and let the handler's own completion
            # fail the ownership check rather than pretending we still hold it.
            return


async def run_worker_tick(
    queue: WorkQueue,
    handlers: dict[str, Callable[[dict], Awaitable[dict]]],
    *,
    worker_id: Optional[str] = None,
    limit: int = 25,
    queue_name: Optional[str] = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> dict:
    """Recover expired leases, then claim and process due items.

    Unknown item types are dead-lettered rather than retried forever: a type with no
    handler will never succeed, so burning retries on it only hides the problem.

    Each tick gets its own worker identity. Sharing one id across ticks would defeat the
    lease-ownership checks, because a stale tick and the tick that replaced it would be
    indistinguishable.
    """
    worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
    recovery = await queue.recover_expired_leases()
    claimed = await queue.claim(worker_id=worker_id, queue=queue_name, limit=limit,
                                lease_seconds=lease_seconds)
    processed, failed, lost = 0, 0, 0
    for item in claimed:
        handler = handlers.get(item.get("type"))
        if handler is None:
            try:
                await queue.fail(item["id"], tenant_id=item["tenant_id"],
                                 reason=f"No handler registered for type '{item.get('type')}'",
                                 actor=worker_id, retryable=False, worker_id=worker_id)
                failed += 1
            except WorkQueueError:
                lost += 1
            continue

        heartbeat = asyncio.create_task(
            _keep_lease_alive(queue, item, worker_id, lease_seconds))
        try:
            await queue.start_processing(item["id"], tenant_id=item["tenant_id"],
                                         worker_id=worker_id)
            result = await handler(item)
            await queue.complete(item["id"], tenant_id=item["tenant_id"], actor=worker_id,
                                 result=result if isinstance(result, dict) else {"ok": True},
                                 worker_id=worker_id)
            processed += 1
        except asyncio.CancelledError:
            raise
        except WorkQueueError:
            # The item moved on without us — lease lost, or an operator resolved it.
            # Recording a failure now would overwrite whatever legitimately happened.
            lost += 1
        except Exception as exc:
            try:
                await queue.fail(item["id"], tenant_id=item["tenant_id"], reason=str(exc)[:500],
                                 actor=worker_id, worker_id=worker_id)
                failed += 1
            except WorkQueueError:
                lost += 1
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except (asyncio.CancelledError, Exception):
                pass
    return {"worker_id": worker_id, "claimed": len(claimed), "processed": processed,
            "failed": failed, "lost": lost, **recovery}
