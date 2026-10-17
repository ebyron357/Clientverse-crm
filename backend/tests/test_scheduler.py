"""The in-process scheduler.

The external scheduler never once reached production, so the recovery sweeps never ran
there. The API now runs them itself. What has to hold for that to be safe and honest:

* exactly one instance runs a job per window, however many replicas ask, and a restart
  does not run a finished window again;
* an instance that dies mid-run does not strand its window: the lease expires and
  another instance takes it over, while a long job that is still alive keeps it;
* one failing job stops neither the loop nor any other job;
* it is off when configured off, and off under test unless a test turns it on;
* it runs the very function each `/api/cron/<path>` route runs, on the cadence the
  workflow gives it;
* every run is in the cron ledger, marked in-process, without making
  `receiving_scheduled_traffic` claim that anything outside reached production;
* with an external scheduler also running, a window it already ran is not run again,
  and the reverse order is documented and safe.
"""

import asyncio
import importlib.util
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ["LEAD_SLA_WATCHER"] = "0"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_scheduler_unit")
os.environ.setdefault("JWT_SECRET", "scheduler-unit-jwt-secret-long-enough-1234567")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("WEBHOOK_CRON_SECRET", "scheduler-test-secret-abc123")
os.environ.setdefault("ADMIN_EMAIL", "admin@scheduler.example")
os.environ.setdefault("ADMIN_PASSWORD", "Scheduler-Admin-Passw0rd!")

from fastapi.testclient import TestClient

import cron_ledger
import scheduler
import server

# A minute past an hourly firing, so every cadence in these tests has room to move
# around inside one window.
T0 = datetime(2026, 10, 17, 12, 5, 10, tzinfo=timezone.utc)


def run(scenario):
    """Run `scenario()` on a fresh loop against a database of its own.

    Fresh loop and client for the same reason as test_cron_ledger. A database per test,
    because these tests read the ledger and lease collections whole, and under a real
    mongod other modules write the same collections in parallel.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    name = f"{os.environ['DB_NAME']}_{uuid.uuid4().hex[:8]}"
    try:
        server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
        server.db = server.mclient[name]
        return loop.run_until_complete(scenario())
    finally:
        try:
            loop.run_until_complete(server.mclient.drop_database(name))
        except Exception:
            pass
        loop.close()


class Clock:
    def __init__(self, at=T0):
        self.at = at

    def __call__(self):
        return self.at

    def advance(self, **delta):
        self.at += timedelta(**delta)


class Counter:
    """A job that records each call and can be held open until released."""

    def __init__(self, hold=False, fail=False):
        self.calls = []
        self.release = asyncio.Event()
        self.started = asyncio.Event()
        if not hold:
            self.release.set()
        self.fail = fail

    async def __call__(self, run_id, actor):
        self.calls.append((run_id, actor))
        self.started.set()
        await self.release.wait()
        if self.fail:
            raise RuntimeError("the job broke")
        return {"ran": len(self.calls)}


def make(db, jobs, clock, schedule=None, holder=None):
    return scheduler.InProcessScheduler(
        db, jobs, schedule=schedule or dict.fromkeys(jobs, "5 * * * *"), clock=clock,
        holder=holder or f"test-{uuid.uuid4().hex[:6]}", lease_seconds=120,
        heartbeat_seconds=0.01, start_jitter_seconds=0, tick_seconds=0.01)


async def within(awaitable, seconds=5):
    """Every wait is bounded: a regression here should fail the test, not hang the suite."""
    return await asyncio.wait_for(awaitable, seconds)


async def settle(*schedulers):
    """Run one tick on each scheduler and wait for what it started."""
    tasks = [task for each in schedulers for task in each.tick()]
    await within(asyncio.gather(*tasks))


async def lease(db, job):
    return await db[scheduler.LEASES].find_one({"_id": job})


async def ledger(db, job):
    return await db[cron_ledger.COLLECTION].find(
        {"job": job}, {"_id": 0}).sort("received_at", 1).to_list(50)


class FakeRequest:
    def __init__(self, run_id):
        self.headers = {"Authorization": f"Bearer {os.environ['WEBHOOK_CRON_SECRET']}",
                        "X-Webhook-Id": run_id, "User-Agent": "pytest-external/1.0"}
        self.cookies = {}


async def drain_background():
    while server._BACKGROUND_TASKS:
        await asyncio.gather(*list(server._BACKGROUND_TASKS), return_exceptions=True)


# ------------------------------------------------------------------------- windows

def test_window_start_follows_the_cron_expression():
    at = datetime(2026, 10, 17, 12, 7, 30, tzinfo=timezone.utc)
    hour = at.replace(minute=0, second=0)
    assert scheduler.window_start("*/5 * * * *", at) == hour.replace(minute=5)
    assert scheduler.window_start("*/15 * * * *", at) == hour
    assert scheduler.window_start("0,30 * * * *", at.replace(minute=30, second=0)) == hour.replace(minute=30)
    assert scheduler.window_start("10,40 * * * *", at) == hour - timedelta(minutes=20)
    # Before this hour's firing, the window is the one that opened last hour.
    assert scheduler.window_start("5 * * * *", at.replace(minute=3)) == hour - timedelta(minutes=55)
    with pytest.raises(ValueError):
        scheduler.firing_minutes("0 9 * * *")   # only minute-of-hour schedules exist here


def test_run_ids_are_deterministic_per_job_and_window():
    window = datetime(2026, 10, 17, 12, 5, tzinfo=timezone.utc)
    assert scheduler.run_id_for("work-queue", window) == "inprocess-work-queue-20261017T1205Z"
    assert scheduler.run_id_for("work-queue", window, 2) == "inprocess-work-queue-20261017T1205Z-r2"


# ---------------------------------------------------------------------- exactly once

def test_two_instances_sharing_a_database_run_each_window_exactly_once():
    async def scenario():
        clock = Clock()
        job = Counter()
        first = make(server.db, {"probe": job}, clock, schedule={"probe": "*/5 * * * *"})
        second = make(server.db, {"probe": job}, clock, schedule={"probe": "*/5 * * * *"})
        # Both ask at the same instant, repeatedly, inside one window.
        for _ in range(3):
            await settle(first, second)
            clock.advance(seconds=40)
        once = len(job.calls)
        clock.at = T0.replace(minute=10, second=3)   # the next window
        await settle(second, first)
        await settle(first, second)
        return once, len(job.calls), await lease(server.db, "probe")

    once, total, record = run(scenario)
    assert once == 1, "two instances asking for the same window must produce one run"
    assert total == 2, "the next window runs once more, and only once"
    assert record["state"] == scheduler.DONE
    assert record["window_start"] == T0.replace(minute=10, second=0).isoformat()


def test_a_second_instance_waits_while_the_holder_is_still_running():
    async def scenario():
        clock = Clock()
        job = Counter(hold=True)
        holder = make(server.db, {"probe": job}, clock)
        other = make(server.db, {"probe": job}, clock)
        running = holder.tick()
        await within(job.started.wait())
        await settle(other)                       # same window, held: no second run
        clock.advance(minutes=10)                 # well past the lease, but renewed...
        await asyncio.sleep(0.05)                 # ...by the holder's heartbeat
        await settle(other)
        calls_while_held = len(job.calls)
        job.release.set()
        await within(asyncio.gather(*running))
        await settle(other)                       # settled now: nothing left to run
        return calls_while_held, len(job.calls)

    while_held, total = run(scenario)
    assert while_held == 1, "a live holder renewing its lease must not be taken over"
    assert total == 1


def test_a_restart_does_not_run_a_finished_window_again():
    async def scenario():
        clock = Clock()
        job = Counter()
        await settle(make(server.db, {"probe": job}, clock, holder="before-restart"))
        clock.advance(minutes=20)                 # same hourly window
        await settle(make(server.db, {"probe": job}, clock, holder="after-restart"))
        return len(job.calls)

    assert run(scenario) == 1


def test_an_expired_lease_is_taken_over():
    async def scenario():
        clock = Clock()
        key = scheduler.window_start("5 * * * *", clock()).isoformat()
        # A holder that claimed this window and then died: it never finished and stopped
        # renewing, so its lease runs out.
        await server.db[scheduler.LEASES].insert_one({
            "_id": "probe", "job": "probe", "window_start": key, "state": scheduler.RUNNING,
            "holder": "crashed-instance", "attempt": 1,
            "expires_at": (clock() + timedelta(seconds=60)).isoformat()})
        job = Counter()
        survivor = make(server.db, {"probe": job}, clock)
        await settle(survivor)
        before_expiry = len(job.calls)
        clock.advance(minutes=2)
        await settle(survivor)
        return before_expiry, job.calls, await lease(server.db, "probe"), await ledger(server.db, "probe")

    before_expiry, calls, record, entries = run(scenario)
    assert before_expiry == 0, "a lease that has not expired is not taken"
    assert len(calls) == 1
    assert record["state"] == scheduler.DONE and record["attempt"] == 2
    assert record["holder"] != "crashed-instance"
    assert calls[0][0].endswith("-r2"), "a takeover is visibly a retry of the same window"
    assert entries[-1]["run_id"] == calls[0][0]


def test_a_stopped_instance_hands_its_window_back_at_once():
    async def scenario():
        clock = Clock()
        job = Counter(hold=True)
        leaving = make(server.db, {"probe": job}, clock)
        leaving.tick()
        await within(job.started.wait())
        await leaving.stop()                      # e.g. a redeploy replaces the instance
        job.release.set()
        replacement = make(server.db, {"probe": job}, clock)
        await settle(replacement)
        return job.calls, await ledger(server.db, "probe")

    calls, entries = run(scenario)
    assert len(calls) == 2, "the interrupted window is retried without waiting for expiry"
    assert entries[0]["status"] == cron_ledger.FAILED
    assert "interrupted" in entries[0]["error"]
    assert entries[1]["status"] == cron_ledger.SUCCEEDED


def test_a_still_running_previous_window_holds_back_the_next():
    async def scenario():
        clock = Clock()
        job = Counter(hold=True)
        first = make(server.db, {"probe": job}, clock, schedule={"probe": "*/5 * * * *"})
        other = make(server.db, {"probe": job}, clock, schedule={"probe": "*/5 * * * *"})
        running = first.tick()
        await within(job.started.wait())
        clock.at = T0.replace(minute=10, second=1)
        await asyncio.sleep(0.05)                 # heartbeat renews against the new time
        await settle(other)
        overlapping = len(job.calls)
        job.release.set()
        await within(asyncio.gather(*running))
        await settle(other)
        return overlapping, len(job.calls)

    overlapping, total = run(scenario)
    assert overlapping == 1, "a job never overlaps its own previous run"
    assert total == 2, "once it finishes, the window it was blocking runs"


# -------------------------------------------------------------------------- failure

def test_a_failing_job_does_not_stop_the_others_or_the_next_window(caplog):
    async def scenario():
        clock = Clock()
        broken, healthy = Counter(fail=True), Counter()
        instance = make(server.db, {"broken": broken, "healthy": healthy}, clock,
                        schedule={"broken": "*/5 * * * *", "healthy": "*/5 * * * *"})
        with caplog.at_level(logging.ERROR, logger="clientverse.scheduler"):
            await settle(instance)
            clock.advance(minutes=5)
            await settle(instance)
        return (len(broken.calls), len(healthy.calls), await lease(server.db, "broken"),
                await ledger(server.db, "broken"))

    broken_calls, healthy_calls, record, entries = run(scenario)
    assert healthy_calls == 2, "a broken job must not take a healthy one down with it"
    assert broken_calls == 2, "a failure spends its window; the next window tries again"
    assert record["state"] == scheduler.FAILED and "the job broke" in record["error"]
    assert [entry["status"] for entry in entries] == [cron_ledger.FAILED, cron_ledger.FAILED]
    failures = [r for r in caplog.records if "failed for window" in r.getMessage()]
    assert failures and all(r.exc_info for r in failures), "failures are logged with traceback"


def test_the_loop_keeps_running_and_stops_cleanly(monkeypatch):
    monkeypatch.setenv("IN_PROCESS_SCHEDULER", "1")
    monkeypatch.delenv("IN_PROCESS_SCHEDULER_JOBS", raising=False)

    async def scenario():
        clock = Clock()
        broken, healthy = Counter(fail=True), Counter()
        instance = make(server.db, {"broken": broken, "healthy": healthy}, clock,
                        schedule={"broken": "*/5 * * * *", "healthy": "*/5 * * * *"})

        def explode(now=None):
            raise RuntimeError("a tick that blows up")

        instance.start()
        started = instance.running
        await asyncio.sleep(0.1)
        clock.advance(minutes=5)
        await asyncio.sleep(0.1)
        original, instance.tick = instance.tick, explode
        await asyncio.sleep(0.05)                 # several failing ticks
        instance.tick = original
        clock.advance(minutes=5)
        await asyncio.sleep(0.1)
        still_running = instance.running
        await instance.stop()
        return started, still_running, instance.running, len(healthy.calls)

    started, still_running, after_stop, healthy_calls = run(scenario)
    assert started and still_running, "neither a failing job nor a failing tick ends the loop"
    assert healthy_calls == 3
    assert after_stop is False


# ------------------------------------------------------------------- configuration

@pytest.mark.parametrize("value", ["0", "false", "no", "off", " FALSE "])
def test_it_can_be_turned_off(monkeypatch, value):
    monkeypatch.setenv("IN_PROCESS_SCHEDULER", value)

    async def scenario():
        instance = make(server.db, {"probe": Counter()}, Clock())
        instance.start()
        return instance.running

    assert run(scenario) is False


def test_it_is_on_by_default_outside_the_test_harness(monkeypatch):
    # conftest.py sets IN_PROCESS_SCHEDULER=0 for the whole suite; without it, on.
    assert os.environ.get("IN_PROCESS_SCHEDULER") == "0"
    monkeypatch.delenv("IN_PROCESS_SCHEDULER")
    assert scheduler.enabled_from_env() is True


def test_the_job_list_can_be_limited(monkeypatch, caplog):
    monkeypatch.setenv("IN_PROCESS_SCHEDULER_JOBS", " approval-expiry,work-queue , lead-sla")
    with caplog.at_level(logging.WARNING, logger="clientverse.scheduler"):
        chosen = scheduler.jobs_from_env(scheduler.SCHEDULE)
    assert chosen == ["work-queue", "approval-expiry"]
    assert any("lead-sla" in r.getMessage() for r in caplog.records)
    monkeypatch.setenv("IN_PROCESS_SCHEDULER_JOBS", "")
    assert scheduler.jobs_from_env(scheduler.SCHEDULE) == list(scheduler.SCHEDULE)


def _fresh_client():
    # The lifespan closes the client on exit, and a previous test may have bound
    # `server.db` to a loop that no longer exists: give each startup its own.
    server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
    server.db = server.mclient[os.environ["DB_NAME"]]


def test_the_application_lifespan_leaves_it_off_under_test_and_starts_it_when_asked(monkeypatch):
    _fresh_client()
    with TestClient(server.app):
        off_under_test = server.job_scheduler.running
    # Turned on, it starts with the application and stops with it. Its first tick waits
    # out the start jitter, so nothing runs against the shared test database here.
    monkeypatch.setenv("IN_PROCESS_SCHEDULER", "1")
    monkeypatch.setenv("IN_PROCESS_SCHEDULER_JOBS", "approval-expiry")
    monkeypatch.setattr(server.job_scheduler, "start_jitter_seconds", 3600)
    _fresh_client()
    with TestClient(server.app):
        on_when_asked = server.job_scheduler.running
    assert off_under_test is False
    assert on_when_asked is True
    assert server.job_scheduler.running is False, "lifespan exit stops it"


# ----------------------------------------------------- the same jobs, the same cadence

def test_every_cron_route_has_one_job_and_the_scheduler_runs_that_same_function():
    served = {route.path.removeprefix("/api/cron/") for route in server.api.routes
              if getattr(route, "path", "").startswith("/api/cron/")
              and "POST" in getattr(route, "methods", set())}
    assert "work-queue" in served
    assert set(server.CRON_JOBS) == served, "every cron route runs from the job table"
    assert set(scheduler.SCHEDULE) | set(scheduler.RUNS_ELSEWHERE) == served
    assert not set(scheduler.SCHEDULE) & set(scheduler.RUNS_ELSEWHERE)
    for job in scheduler.SCHEDULE:
        assert server.job_scheduler.jobs[job] is server.CRON_JOBS[job], job


@pytest.mark.parametrize("job, owner, name, takes_actor", [
    ("commitment-risk", "server", "evaluate_commitment_risk", True),
    ("work-queue", "server", "run_worker_tick", False),
    ("detect-recovery", "detectors", "run_detection_all_tenants", True),
    ("lead-sla", "lead_pipeline", "sweep", False),
    ("second-chance", "server", "run_second_chance_sweep", True),
    ("next-best-actions", "nba_service", "generate_all_tenants", True),
    ("recovery-strategies", "recovery_service", "compose_all_tenants", True),
    ("recovery-runner", "recovery_runner_service", "run_ready_cases_all_tenants", True),
    ("approval-expiry", "approval_service", "expire_due", False),
    ("inbound-email", "server", "run_inbound_email_sweep", True),
    ("reconcile-unknown", "server", "run_reconcile_unknown_sweep", True),
    ("integration-sync", "server", "run_integration_sync_sweep", True),
    ("daily-digest", "server", "run_daily_digest_sweep", False),
])
def test_each_job_runs_the_function_its_route_always_ran(monkeypatch, job, owner, name, takes_actor):
    calls = []

    async def fake(*args, **kwargs):
        calls.append(kwargs)
        return {"faked": name}

    target = server if owner == "server" else getattr(server, owner)
    monkeypatch.setattr(target, name, fake)
    result = asyncio.run(server.CRON_JOBS[job]("run-1", scheduler.ACTOR))
    assert result == {"faked": name}
    assert len(calls) == 1
    if takes_actor:
        assert calls[0]["actor"] == scheduler.ACTOR, "the run is attributed to the scheduler"
    if job == "work-queue":
        assert calls[0]["worker_id"] == f"{scheduler.ACTOR}-run-1"


def test_the_route_and_the_scheduler_reach_the_same_table_entry(monkeypatch):
    calls = []

    async def fake(run_id, actor):
        calls.append((run_id, actor))
        return {"ok": True}

    monkeypatch.setitem(server.CRON_JOBS, "approval-expiry", fake)

    async def scenario():
        delivery = f"gha-approval-expiry-{uuid.uuid4().hex[:8]}"
        await server.cron_approval_expiry(FakeRequest(delivery))
        await drain_background()
        clock = Clock(datetime.now(timezone.utc) + timedelta(hours=2))   # a later window
        instance = scheduler.InProcessScheduler(
            server.db, server.CRON_JOBS, schedule={"approval-expiry": "5 * * * *"}, clock=clock)
        await settle(instance)
        return delivery

    delivery = run(scenario)
    assert calls[0] == (delivery, server.CRON_ACTOR)
    assert calls[1][1] == scheduler.ACTOR and calls[1][0].startswith("inprocess-approval-expiry-")


def _validate_config():
    spec = importlib.util.spec_from_file_location(
        "validate_config_under_test", REPO_ROOT / "scripts" / "validate_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cadences_mirror_the_scheduler_workflow():
    workflow = (REPO_ROOT / ".github/workflows/scheduled-jobs.yml").read_text()
    scheduled = _validate_config().workflow_schedule(workflow)
    for path, cron in scheduled.items():
        if path in scheduler.RUNS_ELSEWHERE:
            continue
        assert scheduler.SCHEDULE.get(path) == cron, path
    assert set(scheduler.SCHEDULE) <= set(scheduled)


def test_the_config_check_catches_a_drifted_cadence(tmp_path):
    validate = _validate_config()
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / "backend").mkdir()
    workflow = (REPO_ROOT / ".github/workflows/scheduled-jobs.yml").read_text()
    (tmp_path / ".github/workflows/scheduled-jobs.yml").write_text(
        workflow.replace("'*/15 * * * *')  paths='commitment-risk'",
                         "'*/20 * * * *')  paths='commitment-risk'"))
    (tmp_path / "backend/scheduler.py").write_text((BACKEND_DIR / "scheduler.py").read_text())
    validate.ROOT = tmp_path
    validate.FINDINGS.clear()
    validate.check_in_process_schedule()
    assert any("commitment-risk" in finding for finding in validate.FINDINGS), validate.FINDINGS


# --------------------------------------------------------------------------- ledger

def test_in_process_runs_are_in_the_ledger_and_do_not_count_as_external_traffic():
    async def scenario():
        clock = Clock(datetime.now(timezone.utc))
        job = Counter()
        instance = make(server.db, {"approval-expiry": job}, clock)
        await settle(instance)
        entries = await ledger(server.db, "approval-expiry")
        before = await cron_ledger.health(server.db, window_minutes=120)
        await server.cron_approval_expiry(FakeRequest(f"gha-{uuid.uuid4().hex[:8]}"))
        await drain_background()
        after = await cron_ledger.health(server.db, window_minutes=120)
        return clock, instance, entries, before, after

    clock, instance, entries, before, after = run(scenario)
    assert len(entries) == 1
    entry = entries[0]
    window = scheduler.window_start("5 * * * *", clock())
    assert entry["origin"] == cron_ledger.ORIGIN_IN_PROCESS
    assert entry["source"] == f"in-process scheduler {instance.holder}"
    assert entry["run_id"] == scheduler.run_id_for("approval-expiry", window)
    assert entry["detail"] == {"window_start": window.isoformat(), "attempt": 1}
    assert entry["status"] == cron_ledger.SUCCEEDED
    assert entry["started_at"] and entry["finished_at"] and entry["result"] == {"ran": 1}

    # Jobs running is not the same claim as production being reachable from outside.
    assert before["receiving_scheduled_traffic"] is False
    assert before["requests_in_window"] == 0
    assert before["last_authenticated_call_at"] is None
    assert before["in_process"]["runs_in_window"] == 1
    assert before["in_process"]["by_status"] == {cron_ledger.SUCCEEDED: 1}
    assert before["in_process"]["last_job"] == "approval-expiry"
    assert before["scheduled_jobs_running"] is True

    assert after["receiving_scheduled_traffic"] is True
    assert after["requests_in_window"] == 1
    assert after["in_process"]["runs_in_window"] == 1


def test_a_failed_in_process_run_is_reported_as_the_last_failure():
    async def scenario():
        instance = make(server.db, {"broken": Counter(fail=True)}, Clock(datetime.now(timezone.utc)))
        await settle(instance)
        return await cron_ledger.health(server.db, window_minutes=120)

    health = run(scenario)
    assert health["last_failed_job"] == "broken"
    assert health["last_failed_origin"] == cron_ledger.ORIGIN_IN_PROCESS
    assert "the job broke" in health["last_failed_error"]


# --------------------------------------------------- alongside an external scheduler

def test_a_window_the_external_scheduler_already_ran_is_not_run_again(monkeypatch):
    calls = []

    async def fake(run_id, actor):
        calls.append(actor)
        return {"ok": True}

    monkeypatch.setitem(server.CRON_JOBS, "approval-expiry", fake)

    async def scenario():
        await server.cron_approval_expiry(FakeRequest(f"gha-{uuid.uuid4().hex[:8]}"))
        await drain_background()
        external = (await ledger(server.db, "approval-expiry"))[0]
        # The same window as the external request, by construction.
        instance = scheduler.InProcessScheduler(
            server.db, server.CRON_JOBS, schedule={"approval-expiry": "5 * * * *"},
            clock=Clock(datetime.fromisoformat(external["received_at"])))
        await settle(instance)
        await settle(instance)
        return external, await lease(server.db, "approval-expiry"), await ledger(server.db, "approval-expiry")

    external, record, entries = run(scenario)
    assert calls == [server.CRON_ACTOR], "the in-process scheduler deferred to the external run"
    assert record["state"] == scheduler.DEFERRED
    assert record["deferred_to"] == external["id"]
    assert len(entries) == 1, "a deferral is not dressed up as a run in the ledger"


def test_an_external_request_after_an_in_process_run_runs_again_and_is_harmless():
    """The documented asymmetry. The endpoint keeps its contract -- every new delivery id
    runs -- because it is also the operator's run-now lever. What makes the repeat safe
    is that each job is an idempotent sweep: shown here with the real commitment-risk
    job, which a second run leaves exactly as the first did."""
    async def scenario():
        past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        await server.db.commitments.insert_one({
            "id": "cmt_overdue", "tenant_id": "tenant_sched", "workspace_id": "ws_sched",
            "title": "Send the signed contract", "status": "open", "due_date": past})
        instance = scheduler.InProcessScheduler(
            server.db, server.CRON_JOBS, schedule={"commitment-risk": "*/15 * * * *"},
            clock=Clock(datetime.now(timezone.utc)))
        await settle(instance)
        await server.cron_commitment_risk(FakeRequest(f"gha-{uuid.uuid4().hex[:8]}"))
        await drain_background()
        entries = await ledger(server.db, "commitment-risk")
        breached = await server.db.domain_events.find(
            {"event_type": "commitment.breached", "resource_id": "cmt_overdue"},
            {"_id": 0}).to_list(10)
        commitment = await server.db.commitments.find_one({"id": "cmt_overdue"})
        return entries, breached, commitment

    entries, breached, commitment = run(scenario)
    assert [e["origin"] for e in entries] == [cron_ledger.ORIGIN_IN_PROCESS, cron_ledger.ORIGIN_EXTERNAL]
    assert all(e["status"] == cron_ledger.SUCCEEDED for e in entries), "both ran"
    assert commitment["status"] == "breached"
    assert len(breached) == 1, "the second run found nothing left to flag"
    assert breached[0]["actor"] == scheduler.ACTOR, "the audit trail names who flagged it"
