"""The declared schedule and misfire detection.

The ledger (test_cron_ledger) proves production records what it receives. That is not
enough on its own: a scheduler that stops firing produces no ledger entries at all, and
an absence is invisible unless something knows what should have arrived. These tests
pin the other half -- that every declared job is judged against its cadence, and that
each way a schedule goes wrong is named rather than reported as healthy.
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
os.environ.setdefault("DB_NAME", "clientverse_cron_schedule_unit")
os.environ.setdefault("JWT_SECRET", "cron-schedule-unit-jwt-secret-long-enough-1234")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("WEBHOOK_CRON_SECRET", "cron-schedule-test-secret-abc123")

import cron_ledger
import cron_schedule
import server

SECRET = os.environ["WEBHOOK_CRON_SECRET"]
NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
FIVE = cron_schedule.BY_JOB["work-queue"]          # */5, grace 30
HOURLY = cron_schedule.BY_JOB["second-chance"]     # 5 * * * *, grace 45


def _entry(job, status, received, **extra):
    row = {"id": f"cronlog_{uuid.uuid4().hex[:12]}", "job": job, "run_id": uuid.uuid4().hex,
           "status": status, "received_at": received.isoformat(),
           "started_at": None, "finished_at": None, "error": None}
    row.update(extra)
    return row


# ------------------------------------------------------------------ cadence parsing

@pytest.mark.parametrize("expression, expected", [
    ("*/15 * * * *", (0, 15, 30, 45)),
    ("0,30 * * * *", (0, 30)),
    ("10,40 * * * *", (10, 40)),
    ("5 * * * *", (5,)),
    ("0-10/5 * * * *", (0, 5, 10)),
])
def test_minute_fields_parse_to_the_minutes_they_fire_on(expression, expected):
    assert cron_schedule.parse_minute_field(expression) == expected


@pytest.mark.parametrize("expression", [
    "*/15 */2 * * *",   # an hour restriction would be silently evaluated as hourly
    "5 * * * 1-5",      # so would a weekday restriction
    "61 * * * *",
    "* * * *",
    "*/0 * * * *",
])
def test_cadences_this_module_would_misjudge_are_refused(expression):
    with pytest.raises(ValueError):
        cron_schedule.parse_minute_field(expression)


def test_every_declared_cadence_is_one_the_evaluator_understands():
    for job in cron_schedule.SCHEDULE:
        assert job.minutes, job.job
        assert 1 <= job.interval_minutes <= 60, job.job
        assert job.grace_minutes > 0 and job.max_runtime_minutes > 0


def test_every_declared_job_is_an_endpoint_the_application_serves():
    served = {getattr(route, "path", None) for route in server.api.routes}
    for job in cron_schedule.SCHEDULE:
        assert f"/api/cron/{job.job}" in served, job.job


def test_interval_is_the_longest_gap_including_the_wrap_to_the_next_hour():
    assert FIVE.interval_minutes == 5
    assert HOURLY.interval_minutes == 60
    assert cron_schedule.BY_JOB["inbound-email"].interval_minutes == 30


def test_ticks_are_exclusive_of_start_and_inclusive_of_end():
    start = datetime(2026, 9, 29, 10, 5, tzinfo=timezone.utc)
    ticks = cron_schedule.ticks_between(FIVE, start, start + timedelta(minutes=15))
    assert [t.minute for t in ticks] == [10, 15, 20]
    assert cron_schedule.ticks_between(HOURLY, start, start + timedelta(hours=2)) == [
        start + timedelta(hours=1), start + timedelta(hours=2)]


def test_tick_enumeration_is_bounded():
    start = NOW - timedelta(days=30)
    assert len(cron_schedule.ticks_between(FIVE, start, NOW)) == cron_schedule.MAX_TICKS


# ------------------------------------------------------------------ verdicts

def test_a_job_called_within_its_cadence_is_on_schedule():
    rows = [_entry("work-queue", cron_ledger.SUCCEEDED, NOW - timedelta(minutes=4),
                   finished_at=(NOW - timedelta(minutes=4)).isoformat())]
    verdict = cron_schedule.evaluate_job(FIVE, rows, NOW)
    assert verdict["status"] == cron_schedule.ON_SCHEDULE
    assert verdict["problems"] == []
    assert verdict["missed_ticks"] == 0
    assert verdict["next_expected_at"] == (NOW + timedelta(minutes=5)).isoformat()


def test_no_record_at_all_is_never_run_not_healthy():
    verdict = cron_schedule.evaluate_job(FIVE, [], NOW)
    assert verdict["status"] == cron_schedule.NEVER_RUN
    assert verdict["last_called_at"] is None


def test_a_late_tick_inside_its_grace_is_not_yet_a_misfire():
    # Last call 25 minutes ago on a five-minute job: GitHub delays are this long often
    # enough that calling it overdue would train operators to ignore the signal.
    rows = [_entry("work-queue", cron_ledger.SUCCEEDED, NOW - timedelta(minutes=25))]
    verdict = cron_schedule.evaluate_job(FIVE, rows, NOW)
    assert verdict["status"] == cron_schedule.ON_SCHEDULE


def test_ticks_past_their_grace_with_no_request_are_counted_as_missed():
    last = NOW - timedelta(hours=2)
    rows = [_entry("work-queue", cron_ledger.SUCCEEDED, last)]
    verdict = cron_schedule.evaluate_job(FIVE, rows, NOW)
    assert verdict["status"] == cron_schedule.OVERDUE
    # Ticks from 10:05 through 11:30 (now minus 30 minutes of grace), every 5 minutes.
    assert verdict["missed_ticks"] == 18
    assert verdict["first_missed_tick_at"] == (last + timedelta(minutes=5)).isoformat()


def test_an_hourly_job_gets_its_own_grace():
    rows = [_entry("second-chance", cron_ledger.SUCCEEDED, datetime(2026, 9, 29, 10, 5,
                                                                     tzinfo=timezone.utc))]
    at_1149 = datetime(2026, 9, 29, 11, 49, tzinfo=timezone.utc)
    at_1151 = datetime(2026, 9, 29, 11, 51, tzinfo=timezone.utc)
    assert cron_schedule.evaluate_job(HOURLY, rows, at_1149)["status"] == \
        cron_schedule.ON_SCHEDULE
    late = cron_schedule.evaluate_job(HOURLY, rows, at_1151)
    assert late["status"] == cron_schedule.OVERDUE and late["missed_ticks"] == 1


def test_a_run_that_started_and_never_finished_is_stalled():
    started = NOW - timedelta(minutes=FIVE.max_runtime_minutes + 5)
    rows = [_entry("work-queue", cron_ledger.RUNNING, NOW - timedelta(minutes=2),
                   started_at=started.isoformat())]
    verdict = cron_schedule.evaluate_job(FIVE, rows, NOW)
    assert verdict["status"] == cron_schedule.STALLED
    assert verdict["stalled_runs"][0]["reason"] == "started and never finished"


def test_a_run_accepted_but_never_started_is_stalled():
    # The shape a redeploy leaves behind: the request was acknowledged, the background
    # task died with the process before it began.
    rows = [_entry("work-queue", cron_ledger.ACCEPTED, NOW - timedelta(minutes=2)),
            _entry("work-queue", cron_ledger.ACCEPTED, NOW - timedelta(minutes=20))]
    verdict = cron_schedule.evaluate_job(FIVE, rows, NOW)
    assert verdict["status"] == cron_schedule.STALLED
    assert len(verdict["stalled_runs"]) == 1
    assert verdict["stalled_runs"][0]["reason"] == "accepted and never started"


def test_a_latest_run_that_raised_is_failing_with_its_error():
    rows = [_entry("work-queue", cron_ledger.FAILED, NOW - timedelta(minutes=3),
                   error="RuntimeError: boom"),
            _entry("work-queue", cron_ledger.SUCCEEDED, NOW - timedelta(minutes=8),
                   finished_at=(NOW - timedelta(minutes=8)).isoformat())]
    verdict = cron_schedule.evaluate_job(FIVE, rows, NOW)
    assert verdict["status"] == cron_schedule.FAILING
    assert verdict["last_error"] == "RuntimeError: boom"
    assert verdict["last_succeeded_at"] == (NOW - timedelta(minutes=8)).isoformat()


def test_recovery_after_a_failure_clears_the_verdict():
    rows = [_entry("work-queue", cron_ledger.SUCCEEDED, NOW - timedelta(minutes=3)),
            _entry("work-queue", cron_ledger.FAILED, NOW - timedelta(minutes=8))]
    assert cron_schedule.evaluate_job(FIVE, rows, NOW)["status"] == cron_schedule.ON_SCHEDULE


def test_a_scheduler_calling_with_the_wrong_secret_is_named_as_such():
    # Rejected calls are not traffic. A scheduler whose secret drifted must not look
    # like a scheduler that is simply quiet, and must not look healthy either.
    rows = [_entry("work-queue", cron_ledger.SUCCEEDED, NOW - timedelta(hours=3)),
            _entry("work-queue", cron_ledger.UNAUTHORIZED, NOW - timedelta(minutes=2))]
    verdict = cron_schedule.evaluate_job(FIVE, rows, NOW)
    # Overdue is the status -- a refused call proves nothing about the scheduler, since
    # anyone can send one -- and the refusals are named beside it.
    assert verdict["status"] == cron_schedule.OVERDUE
    assert cron_schedule.REJECTED in verdict["problems"]


def test_a_strangers_refused_calls_cannot_hide_a_stopped_scheduler():
    rows = [_entry("work-queue", cron_ledger.SUCCEEDED, NOW - timedelta(hours=2)),
            _entry("work-queue", cron_ledger.UNAUTHORIZED, NOW - timedelta(minutes=1))]
    verdict = cron_schedule.evaluate_job(FIVE, rows, NOW)
    assert verdict["status"] == cron_schedule.OVERDUE and verdict["missed_ticks"] > 0


def test_a_run_cut_off_by_a_redeploy_is_history_once_a_later_run_finishes():
    rows = [_entry("work-queue", cron_ledger.RUNNING, NOW - timedelta(days=20)),
            _entry("work-queue", cron_ledger.SUCCEEDED, NOW - timedelta(minutes=2))]
    verdict = cron_schedule.evaluate_job(FIVE, rows, NOW)
    assert verdict["status"] == cron_schedule.ON_SCHEDULE, verdict["problems"]
    still_open = [_entry("work-queue", cron_ledger.SUCCEEDED, NOW - timedelta(hours=1)),
                  _entry("work-queue", cron_ledger.RUNNING, NOW - timedelta(minutes=50))]
    assert cron_schedule.STALLED in cron_schedule.evaluate_job(FIVE, still_open, NOW)["problems"]


def test_rejections_followed_by_accepted_calls_are_history_not_a_problem():
    rows = [_entry("work-queue", cron_ledger.UNAUTHORIZED, NOW - timedelta(minutes=9)),
            _entry("work-queue", cron_ledger.SUCCEEDED, NOW - timedelta(minutes=4))]
    assert cron_schedule.evaluate_job(FIVE, rows, NOW)["status"] == cron_schedule.ON_SCHEDULE


def test_a_duplicate_delivery_still_proves_the_scheduler_fired():
    rows = [_entry("work-queue", cron_ledger.DUPLICATE, NOW - timedelta(minutes=4))]
    assert cron_schedule.evaluate_job(FIVE, rows, NOW)["status"] == cron_schedule.ON_SCHEDULE


# ------------------------------------------------------------------ against the ledger

def run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class FakeRequest:
    def __init__(self, headers=None, cookies=None):
        self.headers = headers or {}
        self.cookies = cookies or {}


def _isolated(scenario):
    """Run against a database of its own: the evaluation is global by design, so any
    ledger rows another test wrote would change the verdicts under test."""
    name = f"clientverse_cron_schedule_{uuid.uuid4().hex[:10]}"

    async def wrapper():
        previous = server.db
        server.db = server.mclient[name]
        try:
            await cron_ledger.ensure_indexes(server.db)
            return await scenario(server.db)
        finally:
            await server.mclient.drop_database(name)
            server.db = previous

    return run(wrapper())


def test_an_empty_ledger_reports_every_declared_job_as_never_run():
    async def scenario(db):
        return await server.cron_schedule_status(
            FakeRequest({"Authorization": f"Bearer {SECRET}"}))

    evaluation = _isolated(scenario)
    assert evaluation["healthy"] is False
    assert sorted(evaluation["jobs_by_status"][cron_schedule.NEVER_RUN]) == sorted(
        job.job for job in cron_schedule.SCHEDULE)


def test_real_ledger_entries_drive_the_verdicts():
    async def scenario(db):
        now = datetime.now(timezone.utc)
        coll = db[cron_ledger.COLLECTION]
        await coll.insert_many([
            _entry("work-queue", cron_ledger.SUCCEEDED, now - timedelta(minutes=1)),
            _entry("recovery-runner", cron_ledger.SUCCEEDED, now - timedelta(hours=3)),
            _entry("commitment-risk", cron_ledger.FAILED, now - timedelta(minutes=2),
                   error="ValueError: bad"),
            _entry("inbound-email", cron_ledger.UNAUTHORIZED, now - timedelta(minutes=1)),
            _entry("not-a-declared-job", cron_ledger.SUCCEEDED, now),
        ])
        evaluation = await cron_schedule.evaluate(db)
        health = await server.cron_health(FakeRequest({"Authorization": f"Bearer {SECRET}"}))
        return evaluation, health

    evaluation, health = _isolated(scenario)
    verdicts = {job["job"]: job for job in evaluation["jobs"]}
    assert verdicts["work-queue"]["status"] == cron_schedule.ON_SCHEDULE
    assert verdicts["recovery-runner"]["status"] == cron_schedule.OVERDUE
    assert verdicts["recovery-runner"]["missed_ticks"] >= 25
    assert verdicts["commitment-risk"]["status"] == cron_schedule.FAILING
    assert verdicts["inbound-email"]["status"] == cron_schedule.NEVER_RUN
    assert cron_schedule.REJECTED in verdicts["inbound-email"]["problems"]
    assert evaluation["undeclared_jobs_in_ledger"] == ["not-a-declared-job"]

    schedule = health["schedule"]
    assert schedule["healthy"] is False
    assert schedule["declared_jobs"] == len(cron_schedule.SCHEDULE)
    assert schedule["overdue"] == ["recovery-runner"]
    assert schedule["failing"] == ["commitment-risk"]
    assert schedule["rejected"] == ["inbound-email"]


def test_the_schedule_is_not_readable_without_the_secret_or_an_admin_session():
    async def scenario(db):
        with pytest.raises(HTTPException) as denied:
            await server.cron_schedule_status(
                FakeRequest({"Authorization": "Bearer wrong-secret"}))
        return denied.value.status_code

    assert _isolated(scenario) in (401, 403)


# ------------------------------------------------------------------ who may read it

def test_scheduler_evidence_is_refused_to_a_self_registered_tenant_admin():
    """The ledger spans every tenant: job results and error text from all of them.
    Registration is self-serve and makes the registrant an admin of a new tenant, so
    'is an admin' cannot be what grants it."""
    import requests

    base = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/")
    email = f"cron_observer_{uuid.uuid4().hex[:10]}@example.com"
    registered = requests.post(f"{base}/api/auth/register",
                               json={"email": email, "password": "CronObserver2026!",
                                     "name": "Cron Observer"}, timeout=30)
    assert registered.status_code == 200, registered.text
    assert registered.json()["user"]["role"] == "admin"
    tenant_admin = {"Authorization": f"Bearer {registered.json()['token']}"}

    operator_login = requests.post(
        f"{base}/api/auth/login",
        json={"email": os.environ.get("ADMIN_EMAIL", "admin@example.com"),
              "password": os.environ.get("ADMIN_PASSWORD", "AdminPass123!")}, timeout=30)
    assert operator_login.status_code == 200, operator_login.text
    operator = {"Authorization": f"Bearer {operator_login.json()['token']}"}

    for path in ("/api/cron/runs", "/api/cron/health", "/api/cron/schedule"):
        refused = requests.get(f"{base}{path}", headers=tenant_admin, timeout=30)
        assert refused.status_code == 403, (path, refused.status_code)
        allowed = requests.get(f"{base}{path}", headers=operator, timeout=30)
        assert allowed.status_code == 200, (path, allowed.status_code, allowed.text)

    schedule = requests.get(f"{base}/api/cron/schedule", headers=operator, timeout=30).json()
    assert {job["job"] for job in schedule["jobs"]} == set(cron_schedule.BY_JOB)
