"""Observable evidence for scheduled execution.

The scheduler used to be unfalsifiable. A GitHub Actions run went green whether it
had called production or not, and production kept no record that survived the call:
`cron_runs` holds a claim row that exists only to deduplicate a delivery id, and the
failure path *deletes* it so a retry is not suppressed. The result was a system that
could report perfect scheduled health for weeks while making no production request at
all -- which is exactly what it did.

This module is the other half of the fix. It is an append-only ledger of what actually
happened to each scheduled request, so every stage of

    scheduler triggered
      -> HTTP request dispatched
      -> production accepted
      -> job enqueued
      -> job executed
      -> result recorded

is observable after the fact from production itself rather than inferred from a green
workflow. It is deliberately separate from the `cron_runs` claim row: that row is
transient by design (a claim taken and sometimes released), this one is never deleted
by the request path, so a crashed job leaves evidence instead of leaving nothing.

Rejected requests are recorded too. A mismatched shared secret is otherwise
indistinguishable from a scheduler that never fired, and telling those two apart is the
single most common question an operator has about this subsystem.

Nothing here stores the bearer token, and the ledger is only readable by a caller that
already holds the cron secret or an admin session.

Two things write here. An HTTP request to `/api/cron/*` (the external scheduler, or an
operator) is `origin: external`; a run started by the API's own scheduler
(`scheduler.py`) is `origin: in_process`. They are kept apart in `health()` because
"is anything outside reaching production?" and "are the jobs running?" are different
questions, and an in-process run must not be able to answer the first one with a yes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

COLLECTION = "cron_run_log"

# Terminal and non-terminal states an entry can hold.
ACCEPTED = "accepted"        # authenticated, claimed, work handed to the background task
DUPLICATE = "duplicate"      # authenticated, but this delivery id was already claimed
UNAUTHORIZED = "unauthorized"  # the shared secret did not match (or is unset)
RUNNING = "running"          # the background job started
SUCCEEDED = "succeeded"      # the background job returned
FAILED = "failed"            # the background job raised

# Who started the run. Entries written before this field existed are external: until the
# in-process scheduler, an HTTP request was the only way in.
ORIGIN_EXTERNAL = "external"
ORIGIN_IN_PROCESS = "in_process"

RETENTION_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


async def ensure_indexes(db: Any) -> None:
    await db[COLLECTION].create_index([("job", 1), ("received_at", -1)])
    await db[COLLECTION].create_index([("status", 1), ("received_at", -1)])
    await db[COLLECTION].create_index("run_id")
    try:
        # Evidence is worth keeping, but not forever: a fixed window keeps the ledger
        # bounded without an operator having to prune it.
        await db[COLLECTION].create_index("expires_at", expireAfterSeconds=0)
    except Exception:
        # A backend without TTL support (or an existing index with other options) must
        # not stop the ledger from recording.
        pass


async def record_request(db: Any, *, job: str, run_id: Optional[str], status: str,
                         source: Optional[str] = None,
                         detail: Optional[dict] = None,
                         origin: str = ORIGIN_EXTERNAL) -> str:
    """Record that production received a scheduled request, and how it was answered.

    Returns the ledger entry id. `status` is one of ACCEPTED / DUPLICATE / UNAUTHORIZED.
    """
    entry_id = f"cronlog_{uuid.uuid4().hex[:16]}"
    now = _now()
    doc: dict[str, Any] = {
        "id": entry_id,
        "job": job,
        "run_id": run_id,
        "status": status,
        "origin": origin,
        "received_at": _iso(now),
        "source": source,
        "detail": detail or {},
        "started_at": None,
        "finished_at": None,
        "duration_ms": None,
        "result": None,
        "error": None,
        "expires_at": now + timedelta(days=RETENTION_DAYS),
    }
    try:
        await db[COLLECTION].insert_one(doc)
    except Exception:
        # The ledger is evidence, not a dependency: never fail a scheduled request
        # because the evidence write failed.
        return entry_id
    return entry_id


async def mark_started(db: Any, entry_id: str) -> None:
    try:
        await db[COLLECTION].update_one(
            {"id": entry_id},
            {"$set": {"status": RUNNING, "started_at": _iso(_now())}})
    except Exception:
        pass


async def mark_finished(db: Any, entry_id: str, *, status: str,
                        result: Optional[Any] = None,
                        error: Optional[str] = None) -> None:
    try:
        entry = await db[COLLECTION].find_one({"id": entry_id}, {"_id": 0, "started_at": 1})
        duration_ms = None
        if entry and entry.get("started_at"):
            try:
                started = datetime.fromisoformat(entry["started_at"])
                duration_ms = int((_now() - started).total_seconds() * 1000)
            except Exception:
                duration_ms = None
        await db[COLLECTION].update_one(
            {"id": entry_id},
            {"$set": {"status": status, "finished_at": _iso(_now()),
                      "duration_ms": duration_ms,
                      "result": _summarise(result), "error": error}})
    except Exception:
        pass


def _summarise(result: Any) -> Any:
    """Keep a job's return value, but never let an unbounded structure into the ledger."""
    if result is None:
        return None
    if isinstance(result, (int, float, str, bool)):
        return result
    if isinstance(result, dict):
        out: dict[str, Any] = {}
        for key, value in list(result.items())[:25]:
            if isinstance(value, (int, float, str, bool)) or value is None:
                out[str(key)] = value
            elif isinstance(value, (list, tuple)):
                out[str(key)] = len(value)
            elif isinstance(value, dict):
                out[str(key)] = {"keys": len(value)}
            else:
                out[str(key)] = str(value)[:120]
        return out
    if isinstance(result, (list, tuple)):
        return {"count": len(result)}
    return str(result)[:200]


async def list_runs(db: Any, *, job: Optional[str] = None, status: Optional[str] = None,
                    limit: int = 50) -> list[dict]:
    query: dict[str, Any] = {}
    if job:
        query["job"] = job
    if status:
        query["status"] = status
    limit = max(1, min(int(limit or 50), 500))
    cursor = db[COLLECTION].find(query, {"_id": 0, "expires_at": 0}).sort("received_at", -1)
    rows: list[dict] = await cursor.to_list(limit)
    return rows


async def health(db: Any, *, window_minutes: int = 120) -> dict:
    """What an operator actually needs to know: has production been called at all, and
    did the calls do anything.

    `last_authenticated_call_at` being absent while the scheduler is supposedly enabled
    is the exact failure this subsystem was blind to.

    The request fields (`requests_in_window`, `by_status`, `last_authenticated_*`,
    `receiving_scheduled_traffic`) count external requests only, so they keep meaning
    "something outside is calling production". What the in-process scheduler ran is
    reported under `in_process`, and `scheduled_jobs_running` answers the question an
    operator usually means: is anything running the jobs at all.
    """
    cutoff = _iso(_now() - timedelta(minutes=max(1, int(window_minutes or 120))))
    recent = await db[COLLECTION].find(
        {"received_at": {"$gte": cutoff}}, {"_id": 0, "expires_at": 0}
    ).sort("received_at", -1).to_list(1000)
    external = [entry for entry in recent if entry.get("origin") != ORIGIN_IN_PROCESS]
    in_process = [entry for entry in recent if entry.get("origin") == ORIGIN_IN_PROCESS]

    by_status = _count_statuses(external)
    receiving = bool(external and any(entry["status"] != UNAUTHORIZED for entry in external))

    projection = {"_id": 0, "expires_at": 0}
    latest_ok = await db[COLLECTION].find_one(
        {"status": {"$in": [ACCEPTED, RUNNING, SUCCEEDED, DUPLICATE]},
         "origin": {"$ne": ORIGIN_IN_PROCESS}},
        projection, sort=[("received_at", -1)])
    latest_rejected = await db[COLLECTION].find_one(
        {"status": UNAUTHORIZED}, projection, sort=[("received_at", -1)])
    # A failed job is a failed job whichever path started it.
    latest_failed = await db[COLLECTION].find_one(
        {"status": FAILED}, projection, sort=[("received_at", -1)])
    latest_in_process = await db[COLLECTION].find_one(
        {"origin": ORIGIN_IN_PROCESS}, projection, sort=[("received_at", -1)])

    return {
        "window_minutes": window_minutes,
        "requests_in_window": len(external),
        "by_status": by_status,
        "last_authenticated_call_at": (latest_ok or {}).get("received_at"),
        "last_authenticated_job": (latest_ok or {}).get("job"),
        "last_rejected_call_at": (latest_rejected or {}).get("received_at"),
        "last_failed_job": (latest_failed or {}).get("job"),
        "last_failed_at": (latest_failed or {}).get("received_at"),
        "last_failed_error": (latest_failed or {}).get("error"),
        "last_failed_origin": ((latest_failed.get("origin") or ORIGIN_EXTERNAL)
                               if latest_failed else None),
        # The honest headline. `false` here with a scheduler configured means the
        # scheduler is not reaching production, whatever its own runs report. In-process
        # runs are deliberately not counted: they prove the jobs run, not that anything
        # outside can reach production.
        "receiving_scheduled_traffic": receiving,
        "in_process": {
            "runs_in_window": len(in_process),
            "by_status": _count_statuses(in_process),
            "last_run_at": (latest_in_process or {}).get("received_at"),
            "last_job": (latest_in_process or {}).get("job"),
            "last_status": (latest_in_process or {}).get("status"),
        },
        "scheduled_jobs_running": receiving or bool(in_process),
    }


def _count_statuses(entries: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return counts
