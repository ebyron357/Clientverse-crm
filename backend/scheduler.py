"""The scheduled jobs, run by the API itself.

Every recovery sweep -- detection, strategy composition, the runner, the durable
work-queue worker, approval expiry, reconciliation, the digest -- used to run only when
an external scheduler POSTed to `/api/cron/*`. That scheduler has never made a
production request (its repository secrets were never set, and then GitHub Actions
stopped running anything at all), so in production none of these jobs ever ran and the
lost-revenue page never filled. The lead SLA watcher already showed the way out: run the
sweep inside the API, and keep the HTTP entry point for anyone who wants to drive it
from outside.

What runs is not reimplemented here. `server.CRON_JOBS` maps each `/api/cron/<path>`
to the one function its route runs, and this module runs that same function on the
cadence `.github/workflows/scheduled-jobs.yml` gives it (`SCHEDULE` below;
`scripts/validate_config.py` fails the build if the two drift).

Exactly once per window, across replicas and restarts
-----------------------------------------------------
A job's window is the span from one of its cron firings to the next. Each job has one
lease document in `scheduler_leases` (`_id` = job) holding the window it last claimed,
its state and an expiry. Claiming a window is a single atomic `find_one_and_update`
that only matches when the stored window is *earlier* than the one being claimed and
the previous run is finished (or its holder has gone quiet), so of any number of
instances asking at once exactly one gets it, and a window can never be claimed twice
or go backwards. The holder renews the expiry while the job runs; an instance that dies
mid-run stops renewing, and once the lease expires another instance takes the same
window over (as a numbered retry). A finished window stays finished across restarts
because the record lives in MongoDB, not in the process.

Alongside an external scheduler
-------------------------------
Running both is safe and mostly redundant. Before running, the claimed window is checked
against the cron ledger: if an external request already ran (or is running) the job in
this window, the in-process run defers to it. The reverse is not suppressed: a request
that arrives after the in-process run still runs, because the endpoint's contract is
"every new delivery id runs" and it is also the operator's run-now lever. That second run
is safe because every job is an idempotent sweep -- each acts only on records still in
the state it is looking for (a commitment not yet flagged, a lead not yet escalated, an
approval still pending, a digest not yet delivered for the day) and the work queue's own
leases keep two worker ticks off the same item. The one exposure is two runs of the same
job overlapping in time, which is the same exposure two overlapping external deliveries
already had.

Every in-process run is written to the same ledger the endpoints use, as
`origin: in_process`, so `/api/cron/runs` shows it; `/api/cron/health` keeps
`receiving_scheduled_traffic` for external requests and reports these separately.

Configuration
-------------
`IN_PROCESS_SCHEDULER` -- on unless `0`/`false`/`no`/`off`. The test harness sets it to
`0` (`tests/conftest.py`), the same way `LEAD_SLA_WATCHER=0` keeps the lead watcher out
of tests.
`IN_PROCESS_SCHEDULER_JOBS` -- optional comma list of job paths to run; empty runs all.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import random
import socket
import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pymongo import ReturnDocument

import cron_ledger

logger = logging.getLogger("clientverse.scheduler")

LEASES = "scheduler_leases"

# The cadence of every scheduled job, keyed by its `/api/cron/<path>`. These are the
# expressions `.github/workflows/scheduled-jobs.yml` fires them on, minute field only.
SCHEDULE: dict[str, str] = {
    "commitment-risk": "*/15 * * * *",    # flag commitments at risk / breached
    "work-queue": "*/5 * * * *",          # durable work-queue worker tick
    "recovery-runner": "*/5 * * * *",     # queue approved recovery cases for execution
    "integration-sync": "0,30 * * * *",   # sync connected providers, re-evaluate alerts
    "next-best-actions": "0,30 * * * *",  # recompute recommendations
    "inbound-email": "10,40 * * * *",     # pull replies back into the CRM
    "reconcile-unknown": "10,40 * * * *",  # resolve dispatches whose outcome was never seen
    "daily-digest": "5 * * * *",          # per-tenant digest at its local hour
    "second-chance": "5 * * * *",         # Second Chance detection
    "detect-recovery": "5 * * * *",       # every other detector family
    "recovery-strategies": "5 * * * *",   # compose strategies, raise approvals
    "approval-expiry": "5 * * * *",       # lapse undecided approvals
}

# Scheduled by the workflow, but already run inside the API by something else. Running it
# here as well would only repeat that sweep.
RUNS_ELSEWHERE: dict[str, str] = {
    "lead-sla": "website_forms.LeadPipeline's watcher sweeps every minute (LEAD_SLA_WATCHER)",
}

# The actor recorded on audit events a scheduled run writes, so they read as the
# in-process scheduler's and not as an HTTP caller's ("cron").
ACTOR = "scheduler"

TICK_SECONDS = 20.0
START_JITTER_SECONDS = 15.0
LEASE_SECONDS = 120.0
HEARTBEAT_SECONDS = 30.0

# Lease states.
RUNNING = "running"
DONE = "done"
FAILED = "failed"
DEFERRED = "deferred"   # an external request already ran the job in this window

JobFn = Callable[[str, str], Awaitable[Any]]   # (run_id, actor) -> the job's result


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    # The cron ledger's format, so a window boundary compares directly with `received_at`.
    return value.astimezone(timezone.utc).isoformat()


def firing_minutes(cron: str) -> tuple[int, ...]:
    """The minutes past each hour a minute-only cron expression fires on."""
    fields = cron.split()
    if len(fields) != 5 or fields[1:] != ["*", "*", "*", "*"]:
        raise ValueError(f"only minute-of-hour schedules are supported, not {cron!r}")
    minute = fields[0]
    if minute.startswith("*/"):
        step = int(minute[2:])
        if step < 1:
            raise ValueError(f"invalid step in {cron!r}")
        return tuple(range(0, 60, step))
    minutes = sorted({int(part) for part in minute.split(",")})
    if not minutes or minutes[0] < 0 or minutes[-1] > 59:
        raise ValueError(f"minutes out of range in {cron!r}")
    return tuple(minutes)


def window_start(cron: str, now: datetime) -> datetime:
    """The most recent firing at or before `now`: the start of the window `now` is in."""
    minutes = firing_minutes(cron)
    now = now.astimezone(timezone.utc)
    hour = now.replace(minute=0, second=0, microsecond=0)
    earlier = [minute for minute in minutes if minute <= now.minute]
    if earlier:
        return hour + timedelta(minutes=earlier[-1])
    return hour - timedelta(hours=1) + timedelta(minutes=minutes[-1])


def run_id_for(job: str, window: datetime, attempt: int = 1) -> str:
    """Deterministic per job and window, so the ledger ties every run to its window and a
    takeover after a crash is visibly the same window's retry."""
    run_id = f"inprocess-{job}-{window.astimezone(timezone.utc):%Y%m%dT%H%MZ}"
    return run_id if attempt <= 1 else f"{run_id}-r{attempt}"


def enabled_from_env() -> bool:
    return os.environ.get("IN_PROCESS_SCHEDULER", "1").strip().lower() not in {
        "0", "false", "no", "off"}


def jobs_from_env(available: Iterable[str]) -> list[str]:
    jobs = list(available)
    wanted = {part.strip() for part in os.environ.get("IN_PROCESS_SCHEDULER_JOBS", "").split(",")
              if part.strip()}
    if not wanted:
        return jobs
    unknown = sorted(wanted - set(jobs))
    if unknown:
        logger.warning("IN_PROCESS_SCHEDULER_JOBS names jobs this scheduler does not run: %s",
                       ", ".join(unknown))
    return [job for job in jobs if job in wanted]


def _is_duplicate_key(exc: Exception) -> bool:
    return getattr(exc, "code", None) == 11000 or "duplicate key" in str(exc).lower()


class InProcessScheduler:
    """Runs each scheduled job once per window, whichever replica gets there first."""

    def __init__(self, db: Any, jobs: Mapping[str, JobFn], *,
                 schedule: Optional[Mapping[str, str]] = None,
                 clock: Callable[[], datetime] = _now,
                 holder: Optional[str] = None,
                 tick_seconds: float = TICK_SECONDS,
                 lease_seconds: float = LEASE_SECONDS,
                 heartbeat_seconds: float = HEARTBEAT_SECONDS,
                 start_jitter_seconds: float = START_JITTER_SECONDS) -> None:
        self.db = db
        self.schedule = dict(SCHEDULE if schedule is None else schedule)
        missing = sorted(set(self.schedule) - set(jobs))
        if missing:
            raise ValueError(f"scheduled jobs with nothing to run: {', '.join(missing)}")
        for cron in self.schedule.values():
            firing_minutes(cron)  # a bad expression fails at import, not at the first tick
        self.jobs: dict[str, JobFn] = {name: jobs[name] for name in self.schedule}
        self.holder = holder or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self.tick_seconds = tick_seconds
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.start_jitter_seconds = start_jitter_seconds
        self._clock = clock
        self._active: list[str] = list(self.schedule)
        self._loop_task: Optional[asyncio.Task[None]] = None
        # Strong references: a task nobody holds can be garbage-collected mid-run.
        self._runs: dict[str, asyncio.Task[None]] = {}
        self._settled: dict[str, datetime] = {}

    # ----------------------------------------------------------------- lifecycle

    def start(self) -> None:
        if self._loop_task is not None:
            return
        if not enabled_from_env():
            logger.info("In-process scheduler disabled by IN_PROCESS_SCHEDULER")
            return
        self._active = jobs_from_env(self.schedule)
        if not self._active:
            logger.warning("In-process scheduler has no jobs to run; not starting")
            return
        logger.info("In-process scheduler started for %d job(s): %s",
                    len(self._active), ", ".join(self._active))
        self._loop_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        tasks = [task for task in (self._loop_task, *self._runs.values())
                 if task is not None and not task.done()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._loop_task = None
        self._runs.clear()

    @property
    def running(self) -> bool:
        return self._loop_task is not None and not self._loop_task.done()

    async def _run_loop(self) -> None:
        # Replicas booted together would otherwise all ask for every lease at the same
        # instant. Only one can win each, but there is no reason to make them all try.
        await asyncio.sleep(random.uniform(0, self.start_jitter_seconds))
        while True:
            try:
                self.tick()
            except Exception:
                logger.exception("In-process scheduler tick failed")
            await asyncio.sleep(self.tick_seconds * random.uniform(0.8, 1.2))

    # ---------------------------------------------------------------- scheduling

    def tick(self, now: Optional[datetime] = None) -> list[asyncio.Task[None]]:
        """Start every job whose current window this instance has not yet settled.

        Each job runs in its own task, so a slow or failing job holds up nothing else,
        and a job never runs twice at once on one instance.
        """
        now = now or self._clock()
        started: list[asyncio.Task[None]] = []
        for job in self._active:
            current = self._runs.get(job)
            if current is not None and not current.done():
                continue
            window = window_start(self.schedule[job], now)
            if self._settled.get(job) == window:
                continue
            task = asyncio.create_task(self._run_window(job, window))
            self._runs[job] = task
            started.append(task)
        return started

    async def _run_window(self, job: str, window: datetime) -> None:
        key = _iso(window)
        try:
            lease = await self._acquire(job, key)
            if lease is None:
                # Someone else holds it. Stop asking only once the window is decided;
                # while another instance is still running it, keep asking, so its lease
                # can be taken over if that instance dies.
                if await self._window_settled(job, key):
                    self._settled[job] = window
                return
            self._settled[job] = window
            await self._execute(job, key, window, int(lease.get("attempt") or 1))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("In-process scheduler could not run '%s' for window %s", job, key)

    # --------------------------------------------------------------------- lease

    async def _acquire(self, job: str, key: str) -> Optional[dict[str, Any]]:
        """Claim `job`'s window `key` for this instance, or return None if it is not ours."""
        leases = self.db[LEASES]
        now = self._clock()
        now_s = _iso(now)
        claim = {"job": job, "window_start": key, "state": RUNNING, "holder": self.holder,
                 "acquired_at": now_s, "expires_at": _iso(now + timedelta(seconds=self.lease_seconds)),
                 "finished_at": None, "error": None, "deferred_to": None}
        # A new window: free once the previous run has finished, or its holder has gone
        # quiet. `$lt` keeps the lease moving forward only.
        lease: Optional[dict[str, Any]] = await leases.find_one_and_update(
            {"_id": job, "window_start": {"$lt": key},
             "$or": [{"state": {"$ne": RUNNING}}, {"expires_at": {"$lte": now_s}}]},
            {"$set": {**claim, "attempt": 1}}, return_document=ReturnDocument.AFTER)
        if lease is not None:
            return lease
        # This window, abandoned mid-run by a holder that stopped renewing its lease.
        lease = await leases.find_one_and_update(
            {"_id": job, "window_start": key, "state": RUNNING, "expires_at": {"$lte": now_s}},
            {"$set": claim, "$inc": {"attempt": 1}}, return_document=ReturnDocument.AFTER)
        if lease is not None:
            logger.warning("In-process job '%s': took over window %s from a holder that stopped "
                           "renewing its lease", job, key)
            return lease
        # The first run this job has ever had. `_id` is unique, so one insert wins.
        try:
            await leases.insert_one({"_id": job, **claim, "attempt": 1})
        except Exception as exc:
            if _is_duplicate_key(exc):
                return None
            raise
        return {**claim, "attempt": 1}

    async def _window_settled(self, job: str, key: str) -> bool:
        lease = await self.db[LEASES].find_one({"_id": job}, {"window_start": 1, "state": 1})
        if not lease:
            return False
        stored = lease.get("window_start") or ""
        return bool(stored > key or (stored == key and lease.get("state") != RUNNING))

    async def _heartbeat(self, job: str, key: str) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            try:
                renewed = await self.db[LEASES].update_one(
                    {"_id": job, "window_start": key, "holder": self.holder, "state": RUNNING},
                    {"$set": {"expires_at": _iso(self._clock() + timedelta(seconds=self.lease_seconds))}})
            except Exception:
                logger.exception("In-process job '%s': could not renew its lease", job)
                continue
            if not renewed.matched_count:
                logger.warning("In-process job '%s' lost its lease for window %s; another "
                               "instance may run it too", job, key)
                return

    async def _settle(self, job: str, key: str, state: str, **fields: Any) -> None:
        try:
            await self.db[LEASES].update_one(
                {"_id": job, "window_start": key, "holder": self.holder},
                {"$set": {"state": state, "finished_at": _iso(self._clock()), **fields}})
        except Exception:
            # Left `running`, the lease expires and the window is retried: a repeat of an
            # idempotent sweep, not a lost one.
            logger.exception("In-process job '%s': could not record the end of window %s", job, key)

    # --------------------------------------------------------------------- run

    async def _external_run_in_window(self, job: str, key: str) -> Optional[str]:
        entry = await self.db[cron_ledger.COLLECTION].find_one(
            {"job": job, "origin": {"$ne": cron_ledger.ORIGIN_IN_PROCESS},
             "status": {"$in": [cron_ledger.ACCEPTED, cron_ledger.RUNNING, cron_ledger.SUCCEEDED]},
             "received_at": {"$gte": key}},
            {"_id": 0, "id": 1})
        return entry.get("id") if entry else None

    async def _execute(self, job: str, key: str, window: datetime, attempt: int) -> None:
        deferred_to = await self._external_run_in_window(job, key)
        if deferred_to:
            logger.info("In-process job '%s': an external request already ran window %s (%s)",
                        job, key, deferred_to)
            await self._settle(job, key, DEFERRED, deferred_to=deferred_to)
            return

        run_id = run_id_for(job, window, attempt)
        entry_id = await cron_ledger.record_request(
            self.db, job=job, run_id=run_id, status=cron_ledger.ACCEPTED,
            source=f"in-process scheduler {self.holder}", origin=cron_ledger.ORIGIN_IN_PROCESS,
            detail={"window_start": key, "attempt": attempt})
        await cron_ledger.mark_started(self.db, entry_id)
        heartbeat = asyncio.create_task(self._heartbeat(job, key))
        try:
            result = await self.jobs[job](run_id, ACTOR)
        except asyncio.CancelledError:
            await cron_ledger.mark_finished(self.db, entry_id, status=cron_ledger.FAILED,
                                            error="interrupted: the scheduler stopped mid-run")
            await self._release(job, key)
            raise
        except Exception as exc:
            logger.exception("In-process job '%s' failed for window %s", job, key)
            error = f"{type(exc).__name__}: {exc}"[:500]
            await cron_ledger.mark_finished(self.db, entry_id, status=cron_ledger.FAILED, error=error)
            # The window is spent; the next one retries. Retrying a failing job inside its
            # own window would turn one failure into a loop.
            await self._settle(job, key, FAILED, error=error)
        else:
            await cron_ledger.mark_finished(self.db, entry_id, status=cron_ledger.SUCCEEDED,
                                            result=result)
            await self._settle(job, key, DONE)
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat

    async def _release(self, job: str, key: str) -> None:
        """Hand an interrupted window back at once rather than after the lease times out,
        so the next instance (a redeploy's replacement, typically) retries it promptly."""
        try:
            await self.db[LEASES].update_one(
                {"_id": job, "window_start": key, "holder": self.holder, "state": RUNNING},
                {"$set": {"expires_at": _iso(self._clock())}})
        except Exception:
            logger.exception("In-process job '%s': could not release window %s", job, key)
