"""The declared schedule, and misfire detection against it.

`cron_ledger` answers "what did production receive?". It cannot answer "what should
it have received?", and without that second question a scheduler that stops firing is
silent: the ledger simply stops growing, and nothing in production notices an absence.

This module is the missing half of the scheduler contract (canonical document §8 #4):

- **A first-class schedule record.** `SCHEDULE` declares, for every authenticated cron
  endpoint, the cadence it is expected to run on, how late a tick may arrive before it
  counts as missed, and how long one run may take before it counts as stalled. The
  scheduler workflow is checked against this declaration at build time
  (`scripts/validate_config.py`), so the two cannot drift apart unnoticed.
- **Misfire detection.** `evaluate()` reads the ledger back against the declaration and
  reports, per job: scheduled ticks that produced no request (`overdue`), runs that
  started and never finished or were accepted and never started (`stalled`), a latest
  run that raised (`failing`), a scheduler that is calling with the wrong secret
  (`rejected`), and a job production has no record of ever receiving (`never_run`).

Detection is computed on read from evidence production already holds. It needs no
scheduler of its own, which is the point: it still works when the scheduler is the
thing that has stopped.

Cadences are expressed in the same five-field cron syntax the workflow uses. Only the
minute field may vary; every job here runs on a fixed minute pattern each hour, and a
declaration outside that is refused at import rather than evaluated wrongly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import cron_ledger

# Job states, worst first. A job reports the first that applies.
REJECTED = "rejected"        # the scheduler is calling, but with a secret production refuses
NEVER_RUN = "never_run"      # production holds no record of this job ever being requested
OVERDUE = "overdue"          # at least one scheduled tick, past its grace, produced no request
STALLED = "stalled"          # a run was accepted or started and never reached a result
FAILING = "failing"          # the latest run that finished raised
ON_SCHEDULE = "on_schedule"

SEVERITY = (REJECTED, NEVER_RUN, OVERDUE, STALLED, FAILING, ON_SCHEDULE)

# How long an accepted request may wait for its background task to start. Starting is
# immediate in-process, so anything this old was lost (typically to a redeploy).
ACCEPTED_START_TIMEOUT_MINUTES = 10

# Bound on how many ticks are ever enumerated in one evaluation, so a very long gap on
# a five-minute job cannot make the health endpoint expensive.
MAX_TICKS = 2000


@dataclass(frozen=True)
class ScheduledJob:
    job: str
    cron: str
    description: str
    # GitHub's scheduled runs are best effort: delays of tens of minutes and dropped
    # ticks both happen under load. Grace absorbs that so `overdue` means a scheduler
    # that has actually stopped, not one having a slow afternoon.
    grace_minutes: int = 30
    max_runtime_minutes: int = 30

    @property
    def minutes(self) -> tuple[int, ...]:
        return parse_minute_field(self.cron)

    @property
    def interval_minutes(self) -> int:
        """The longest gap between two consecutive ticks of this job."""
        marks = self.minutes
        gaps = [(marks[(i + 1) % len(marks)] - marks[i]) % 60 or 60
                for i in range(len(marks))]
        return max(gaps)


# The declared schedule. The workflow at .github/workflows/scheduled-jobs.yml must
# drive exactly these jobs on exactly these cadences; validate_config.py enforces it.
SCHEDULE: tuple[ScheduledJob, ...] = (
    ScheduledJob("commitment-risk", "*/15 * * * *",
                 "Re-evaluate commitment risk and raise alerts"),
    ScheduledJob("work-queue", "*/5 * * * *",
                 "Durable work-queue worker"),
    ScheduledJob("recovery-runner", "*/5 * * * *",
                 "Execute approved recovery strategies to the provider boundary"),
    ScheduledJob("integration-sync", "0,30 * * * *",
                 "Sync connected integrations and evaluate integration alerts"),
    ScheduledJob("next-best-actions", "0,30 * * * *",
                 "Regenerate next best actions for every tenant"),
    ScheduledJob("inbound-email", "10,40 * * * *",
                 "Pull inbound mail back into conversations"),
    ScheduledJob("reconcile-unknown", "10,40 * * * *",
                 "Resolve dispatches whose outcome was never observed"),
    ScheduledJob("daily-digest", "5 * * * *",
                 "Send daily digests at each tenant's local digest hour",
                 grace_minutes=45),
    ScheduledJob("second-chance", "5 * * * *",
                 "Second Chance sweep for stalled leads and missed follow-ups",
                 grace_minutes=45),
    ScheduledJob("detect-recovery", "5 * * * *",
                 "Run every recovery detector family",
                 grace_minutes=45),
    ScheduledJob("recovery-strategies", "5 * * * *",
                 "Compose recovery strategies for open cases",
                 grace_minutes=45),
    ScheduledJob("approval-expiry", "5 * * * *",
                 "Expire approvals past their deadline",
                 grace_minutes=45),
    ScheduledJob("recovery-followups", "5 * * * *",
                 "Draft due recovery follow-ups for approval",
                 grace_minutes=45),
)

BY_JOB: dict[str, ScheduledJob] = {entry.job: entry for entry in SCHEDULE}


def parse_minute_field(expression: str) -> tuple[int, ...]:
    """Return the sorted minutes-past-the-hour a five-field cron expression fires on.

    Supports `*`, `*/n`, `a`, `a-b`, `a-b/n` and comma lists of those in the minute
    field. The hour, day, month and weekday fields must all be `*`; anything else is a
    cadence this module would evaluate wrongly, so it is refused.
    """
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError(f"'{expression}' is not a five-field cron expression")
    if any(field != "*" for field in fields[1:]):
        raise ValueError(f"'{expression}': only the minute field may be restricted")
    minutes: set[int] = set()
    for part in fields[0].split(","):
        step = 1
        if "/" in part:
            part, raw_step = part.split("/", 1)
            step = int(raw_step)
            if step < 1:
                raise ValueError(f"'{expression}': step must be positive")
        if part == "*":
            low, high = 0, 59
        elif "-" in part:
            raw_low, raw_high = part.split("-", 1)
            low, high = int(raw_low), int(raw_high)
        else:
            low = high = int(part)
        if not (0 <= low <= high <= 59):
            raise ValueError(f"'{expression}': minute out of range")
        minutes.update(range(low, high + 1, step))
    if not minutes:
        raise ValueError(f"'{expression}' never fires")
    return tuple(sorted(minutes))


def ticks_between(job: ScheduledJob, start: datetime, end: datetime,
                  limit: int = MAX_TICKS) -> list[datetime]:
    """Scheduled fire times `t` with `start < t <= end`, oldest first, at most `limit`."""
    if end <= start:
        return []
    marks = job.minutes
    hour = start.replace(minute=0, second=0, microsecond=0)
    out: list[datetime] = []
    while hour <= end and len(out) < limit:
        for minute in marks:
            tick = hour + timedelta(minutes=minute)
            if start < tick <= end:
                out.append(tick)
                if len(out) >= limit:
                    break
        hour += timedelta(hours=1)
    return out


def next_tick(job: ScheduledJob, after: datetime) -> datetime:
    upcoming = ticks_between(job, after, after + timedelta(hours=2), limit=1)
    return upcoming[0]


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.astimezone(timezone.utc).isoformat() if value else None


_CALLED = (cron_ledger.ACCEPTED, cron_ledger.RUNNING, cron_ledger.SUCCEEDED,
           cron_ledger.FAILED, cron_ledger.DUPLICATE)
_FINISHED = (cron_ledger.SUCCEEDED, cron_ledger.FAILED)


def evaluate_job(job: ScheduledJob, entries: Iterable[dict], now: datetime) -> dict:
    """Judge one job against its declaration, from its ledger entries (any order)."""
    rows = sorted(entries, key=lambda row: row.get("received_at") or "", reverse=True)
    called = [row for row in rows if row.get("status") in _CALLED]
    finished = [row for row in rows if row.get("status") in _FINISHED]
    last_called = called[0] if called else None
    last_rejected = next((row for row in rows
                          if row.get("status") == cron_ledger.UNAUTHORIZED), None)
    last_finished = finished[0] if finished else None
    last_succeeded = next((row for row in finished
                           if row.get("status") == cron_ledger.SUCCEEDED), None)

    last_called_at = _parse((last_called or {}).get("received_at"))
    last_rejected_at = _parse((last_rejected or {}).get("received_at"))

    # A tick is only missed once its grace has elapsed with no request after it.
    horizon = now - timedelta(minutes=job.grace_minutes)
    missed_ticks = 0
    first_missed_at = None
    if last_called_at is not None:
        missed = ticks_between(job, last_called_at, horizon)
        missed_ticks = len(missed)
        first_missed_at = missed[0] if missed else None

    stalled: list[dict] = []
    for row in rows:
        status = row.get("status")
        if status == cron_ledger.RUNNING:
            started = _parse(row.get("started_at")) or _parse(row.get("received_at"))
            if started and now - started > timedelta(minutes=job.max_runtime_minutes):
                stalled.append({"id": row.get("id"), "run_id": row.get("run_id"),
                                "reason": "started and never finished",
                                "since": _iso(started)})
        elif status == cron_ledger.ACCEPTED:
            received = _parse(row.get("received_at"))
            if received and now - received > timedelta(
                    minutes=ACCEPTED_START_TIMEOUT_MINUTES):
                stalled.append({"id": row.get("id"), "run_id": row.get("run_id"),
                                "reason": "accepted and never started",
                                "since": _iso(received)})

    problems: list[str] = []
    rejected_since_last_call = last_rejected_at is not None and (
        last_called_at is None or last_rejected_at > last_called_at)
    if rejected_since_last_call:
        problems.append(REJECTED)
    if last_called_at is None:
        problems.append(NEVER_RUN)
    if missed_ticks:
        problems.append(OVERDUE)
    if stalled:
        problems.append(STALLED)
    if last_finished and last_finished.get("status") == cron_ledger.FAILED:
        problems.append(FAILING)
    status = next((state for state in SEVERITY if state in problems), ON_SCHEDULE)

    return {
        "job": job.job,
        "cron": job.cron,
        "description": job.description,
        "interval_minutes": job.interval_minutes,
        "grace_minutes": job.grace_minutes,
        "max_runtime_minutes": job.max_runtime_minutes,
        "status": status,
        "problems": problems,
        "last_called_at": _iso(last_called_at),
        "last_rejected_at": _iso(last_rejected_at),
        "last_succeeded_at": (last_succeeded or {}).get("finished_at")
                             or (last_succeeded or {}).get("received_at"),
        "last_finished_status": (last_finished or {}).get("status"),
        "last_error": (last_finished or {}).get("error")
                      if (last_finished or {}).get("status") == cron_ledger.FAILED else None,
        "missed_ticks": missed_ticks,
        "missed_ticks_capped": missed_ticks >= MAX_TICKS,
        "first_missed_tick_at": _iso(first_missed_at),
        "stalled_runs": stalled[:10],
        "next_expected_at": _iso(next_tick(job, now)),
    }


async def evaluate(db: Any, *, now: Optional[datetime] = None) -> dict:
    """Every declared job judged against the ledger, plus a headline."""
    now = now or datetime.now(timezone.utc)
    jobs = [entry.job for entry in SCHEDULE]
    coll = db[cron_ledger.COLLECTION]
    # The ledger is bounded by its retention window; read what is needed per job rather
    # than the whole collection. The newest call, rejection, finished and successful run
    # are enough for status, and open (accepted/running) rows for stall detection.
    results = []
    for job in SCHEDULE:
        projection = {"_id": 0, "expires_at": 0, "detail": 0, "result": 0}
        wanted: list[dict] = []
        for statuses in (_CALLED, (cron_ledger.UNAUTHORIZED,), _FINISHED,
                         (cron_ledger.SUCCEEDED,)):
            row = await coll.find_one({"job": job.job, "status": {"$in": list(statuses)}},
                                      projection, sort=[("received_at", -1)])
            if row:
                wanted.append(row)
        open_rows = await coll.find(
            {"job": job.job, "status": {"$in": [cron_ledger.ACCEPTED, cron_ledger.RUNNING]}},
            projection).sort("received_at", -1).to_list(50)
        seen = {row.get("id") for row in wanted}
        wanted.extend(row for row in open_rows if row.get("id") not in seen)
        results.append(evaluate_job(job, wanted, now))

    by_status: dict[str, list[str]] = {}
    for result in results:
        by_status.setdefault(result["status"], []).append(result["job"])
    unscheduled = sorted({row async for row in _ledger_jobs(db)} - set(jobs))
    return {
        "evaluated_at": _iso(now),
        "healthy": all(result["status"] == ON_SCHEDULE for result in results),
        "jobs_by_status": by_status,
        "jobs": results,
        # A job name in the ledger that nothing declares is a scheduler calling an
        # endpoint this record does not know about; worth surfacing, never fatal.
        "undeclared_jobs_in_ledger": unscheduled,
    }


async def _ledger_jobs(db: Any) -> AsyncIterator[str]:
    for name in await db[cron_ledger.COLLECTION].distinct("job"):
        if name:
            yield name


def summary(evaluation: dict) -> dict:
    """The headline of an evaluation, small enough to embed in /api/cron/health."""
    by_status = evaluation.get("jobs_by_status") or {}
    return {
        "healthy": evaluation.get("healthy", False),
        "declared_jobs": len(evaluation.get("jobs") or []),
        "on_schedule": len(by_status.get(ON_SCHEDULE, [])),
        "overdue": by_status.get(OVERDUE, []),
        "stalled": by_status.get(STALLED, []),
        "failing": by_status.get(FAILING, []),
        "rejected": by_status.get(REJECTED, []),
        "never_run": by_status.get(NEVER_RUN, []),
    }


def declared() -> list[dict]:
    return [{"job": entry.job, "cron": entry.cron, "description": entry.description,
             "interval_minutes": entry.interval_minutes,
             "grace_minutes": entry.grace_minutes,
             "max_runtime_minutes": entry.max_runtime_minutes}
            for entry in SCHEDULE]
