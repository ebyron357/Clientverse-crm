"""Approval queue tests (M-07).

The gate has to hold under the conditions that make gates fail in practice: a lapsed
request, a second decision arriving after the first, two workers racing one approval,
and an approval whose prerequisite was never satisfied. Each of those is a test here.
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import approval_queue as aq

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT = "ten_apr_a"
OTHER_TENANT = "ten_apr_b"

_LOOP = None


def run(coro):
    """Run a coroutine on a loop this module owns (see test_second_chance for why)."""
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


@pytest.fixture()
def db():
    db_name = f"cv_apr_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[db_name]
    run(aq.ensure_indexes(database))
    yield database
    run(client.drop_database(db_name))
    client.close()


def _request(db, **overrides):
    kwargs = dict(tenant_id=TENANT, title="Send recovery email", actor="agent:composer",
                  action={"type": "test.action"})
    kwargs.update(overrides)
    return run(aq.request(db, **kwargs))


# ----------------------------------------------------------------- raising

def test_request_records_provenance_and_binding(db):
    req = _request(db, risk=aq.RISK_HIGH, subject_type="opportunity", subject_id="opp_1",
                   facts=[{"label": "Days idle", "value": 21, "source": "opportunity:opp_1"}])
    assert req["status"] == aq.REQUESTED
    assert req["risk"] == aq.RISK_HIGH
    assert req["requester_kind"] == aq.REQUESTER_AGENT
    assert req["requested_by"] == "agent:composer"
    assert req["subject_id"] == "opp_1"
    assert req["action"] == {"type": "test.action"}
    assert req["facts"][0]["source"] == "opportunity:opp_1"
    assert req["execution"]["state"] == aq.EXECUTION_PENDING
    assert req["history"][0]["action"] == "requested"


def test_request_without_action_is_not_executable(db):
    req = _request(db, action=None)
    assert req["execution"]["state"] == aq.EXECUTION_NOT_APPLICABLE
    run(aq.decide(db, tenant_id=TENANT, approval_id=req["id"], decision=aq.APPROVED,
                  actor="admin@example.com"))
    with pytest.raises(aq.InvalidApprovalTransition):
        run(aq.consume(db, tenant_id=TENANT, approval_id=req["id"], actor="worker-1"))


def test_unknown_risk_falls_back_to_medium(db):
    assert _request(db, risk="catastrophic")["risk"] == aq.RISK_MEDIUM


def test_title_is_required(db):
    with pytest.raises(aq.ApprovalError):
        _request(db, title="   ")


def test_expiry_bounds_are_enforced(db):
    with pytest.raises(aq.ApprovalError):
        _request(db, expires_in_hours=0)
    with pytest.raises(aq.ApprovalError):
        _request(db, expires_in_hours=aq.MAX_EXPIRY_HOURS + 1)


def test_duplicate_open_request_collapses(db):
    first = _request(db, dedupe_key="strategy:rcv_1")
    second = _request(db, dedupe_key="strategy:rcv_1")
    assert second["deduplicated"] is True
    assert second["id"] == first["id"]
    assert len(run(aq.list_requests(db, TENANT))) == 1


def test_dedupe_key_is_released_once_decided(db):
    first = _request(db, dedupe_key="strategy:rcv_1")
    run(aq.decide(db, tenant_id=TENANT, approval_id=first["id"], decision=aq.REJECTED,
                  actor="admin@example.com"))
    again = _request(db, dedupe_key="strategy:rcv_1")
    assert again["deduplicated"] is False
    assert again["id"] != first["id"]


# ---------------------------------------------------------------- deciding

def test_approve_records_the_decider_and_rationale(db):
    req = _request(db)
    decided = run(aq.decide(db, tenant_id=TENANT, approval_id=req["id"], decision=aq.APPROVED,
                            actor="admin@example.com", rationale="Account confirmed by owner"))
    assert decided["status"] == aq.APPROVED
    assert decided["decided_by"] == "admin@example.com"
    assert decided["decision_rationale"] == "Account confirmed by owner"
    assert [h["action"] for h in decided["history"]] == ["requested", "approved"]


def test_second_decision_is_refused(db):
    req = _request(db)
    run(aq.decide(db, tenant_id=TENANT, approval_id=req["id"], decision=aq.APPROVED,
                  actor="admin@example.com"))
    with pytest.raises(aq.InvalidApprovalTransition):
        run(aq.decide(db, tenant_id=TENANT, approval_id=req["id"], decision=aq.REJECTED,
                      actor="other@example.com"))


def test_decision_must_be_approve_or_reject(db):
    req = _request(db)
    with pytest.raises(aq.ApprovalError):
        run(aq.decide(db, tenant_id=TENANT, approval_id=req["id"], decision="maybe",
                      actor="admin@example.com"))


def test_decision_is_tenant_scoped(db):
    req = _request(db)
    with pytest.raises(aq.ApprovalNotFound):
        run(aq.decide(db, tenant_id=OTHER_TENANT, approval_id=req["id"], decision=aq.APPROVED,
                      actor="admin@example.com"))


def test_separate_approver_is_enforced_only_when_requested(db):
    guarded = _request(db, actor="alice@example.com", requester_kind=aq.REQUESTER_HUMAN,
                       require_separate_approver=True)
    with pytest.raises(aq.InvalidApprovalTransition):
        run(aq.decide(db, tenant_id=TENANT, approval_id=guarded["id"], decision=aq.APPROVED,
                      actor="alice@example.com"))
    assert run(aq.decide(db, tenant_id=TENANT, approval_id=guarded["id"],
                         decision=aq.APPROVED, actor="bob@example.com"))["status"] == aq.APPROVED

    # The default keeps the long-standing C-09 behaviour: raise and approve your own.
    plain = _request(db, actor="alice@example.com", requester_kind=aq.REQUESTER_HUMAN)
    assert run(aq.decide(db, tenant_id=TENANT, approval_id=plain["id"], decision=aq.APPROVED,
                         actor="alice@example.com"))["status"] == aq.APPROVED


# ----------------------------------------------------------------- expiry

def _backdate(db, approval_id, hours=1):
    run(db[aq.COLLECTION].update_one(
        {"id": approval_id},
        {"$set": {"expires_at": (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()}}))


def test_lapsed_request_cannot_be_approved(db):
    req = _request(db)
    _backdate(db, req["id"])
    with pytest.raises(aq.InvalidApprovalTransition):
        run(aq.decide(db, tenant_id=TENANT, approval_id=req["id"], decision=aq.APPROVED,
                      actor="admin@example.com"))
    assert run(aq.get(db, TENANT, req["id"]))["status"] == aq.EXPIRED


def test_expiry_is_applied_on_read_not_only_by_the_sweep(db):
    req = _request(db)
    _backdate(db, req["id"])
    # No sweep has run; the read alone must not report an approvable request.
    assert run(aq.get(db, TENANT, req["id"]))["status"] == aq.EXPIRED


def test_expired_requests_leave_the_open_listing(db):
    live = _request(db, title="Still live")
    stale = _request(db, title="Gone stale")
    _backdate(db, stale["id"])
    open_ids = [r["id"] for r in run(aq.list_requests(db, TENANT, status="open"))]
    assert open_ids == [live["id"]]
    assert stale["id"] in [r["id"] for r in run(aq.list_requests(db, TENANT, status="all"))]


def test_expire_due_sweep_is_idempotent(db):
    req = _request(db)
    _backdate(db, req["id"])
    assert run(aq.expire_due(db, tenant_id=TENANT))["expired"] == 1
    assert run(aq.expire_due(db, tenant_id=TENANT))["expired"] == 0


def test_expiry_releases_the_dedupe_key(db):
    first = _request(db, dedupe_key="strategy:rcv_9")
    _backdate(db, first["id"])
    run(aq.expire_due(db, tenant_id=TENANT))
    assert _request(db, dedupe_key="strategy:rcv_9")["deduplicated"] is False


# -------------------------------------------------------------- consumption

def test_consume_requires_approval(db):
    req = _request(db)
    with pytest.raises(aq.InvalidApprovalTransition):
        run(aq.consume(db, tenant_id=TENANT, approval_id=req["id"], actor="worker-1"))


def test_an_approval_authorises_exactly_one_execution(db):
    req = _request(db)
    run(aq.decide(db, tenant_id=TENANT, approval_id=req["id"], decision=aq.APPROVED,
                  actor="admin@example.com"))
    claimed = run(aq.consume(db, tenant_id=TENANT, approval_id=req["id"], actor="worker-1"))
    assert claimed["execution"]["state"] == aq.EXECUTION_CONSUMED
    assert claimed["execution"]["consumed_by"] == "worker-1"
    with pytest.raises(aq.InvalidApprovalTransition):
        run(aq.consume(db, tenant_id=TENANT, approval_id=req["id"], actor="worker-2"))


def test_concurrent_workers_produce_one_execution(db):
    req = _request(db)
    run(aq.decide(db, tenant_id=TENANT, approval_id=req["id"], decision=aq.APPROVED,
                  actor="admin@example.com"))

    async def race():
        return await asyncio.gather(
            *[aq.consume(db, tenant_id=TENANT, approval_id=req["id"], actor=f"worker-{i}")
              for i in range(6)],
            return_exceptions=True)

    results = run(race())
    winners = [r for r in results if not isinstance(r, Exception)]
    assert len(winners) == 1, f"expected exactly one winner, got {len(winners)}"


def test_approval_does_not_unblock_a_missing_prerequisite(db):
    req = _request(db, blocked_reasons=["No connected email provider (gmail is not connected)."])
    run(aq.decide(db, tenant_id=TENANT, approval_id=req["id"], decision=aq.APPROVED,
                  actor="admin@example.com"))
    with pytest.raises(aq.InvalidApprovalTransition) as exc:
        run(aq.consume(db, tenant_id=TENANT, approval_id=req["id"], actor="worker-1"))
    assert "still blocked" in str(exc.value)


# ---------------------------------------------------------- cancel and read

def test_cancel_withdraws_an_undecided_request(db):
    req = _request(db)
    cancelled = run(aq.cancel(db, tenant_id=TENANT, approval_id=req["id"], actor="admin@example.com",
                              reason="Client replied"))
    assert cancelled["status"] == aq.CANCELLED
    with pytest.raises(aq.InvalidApprovalTransition):
        run(aq.decide(db, tenant_id=TENANT, approval_id=req["id"], decision=aq.APPROVED,
                      actor="admin@example.com"))


def test_cancel_refuses_a_decided_request(db):
    req = _request(db)
    run(aq.decide(db, tenant_id=TENANT, approval_id=req["id"], decision=aq.APPROVED,
                  actor="admin@example.com"))
    with pytest.raises(aq.InvalidApprovalTransition):
        run(aq.cancel(db, tenant_id=TENANT, approval_id=req["id"], actor="admin@example.com"))


def test_listing_is_tenant_scoped(db):
    _request(db, title="Tenant A")
    _request(db, tenant_id=OTHER_TENANT, title="Tenant B")
    titles = [r["title"] for r in run(aq.list_requests(db, TENANT))]
    assert titles == ["Tenant A"]


def test_listing_filters_by_kind_and_risk(db):
    _request(db, kind="recovery_strategy", risk=aq.RISK_LOW, title="Low")
    _request(db, kind="mcp_write", risk=aq.RISK_HIGH, title="High")
    assert [r["title"] for r in run(aq.list_requests(db, TENANT, kind="mcp_write"))] == ["High"]
    assert [r["title"] for r in run(aq.list_requests(db, TENANT, risk=aq.RISK_LOW))] == ["Low"]


def test_summary_counts_what_is_waiting(db):
    _request(db, risk=aq.RISK_HIGH)
    blocked = _request(db, risk=aq.RISK_LOW, blocked_reasons=["No channel"])
    approved = _request(db, title="Ready")
    run(aq.decide(db, tenant_id=TENANT, approval_id=approved["id"], decision=aq.APPROVED,
                  actor="admin@example.com"))

    summary = run(aq.summary(db, TENANT))
    assert summary["awaiting_decision"] == 2
    assert summary["awaiting_decision_blocked"] == 1
    assert summary["approved_awaiting_execution"] == 1
    assert summary["by_risk"][aq.RISK_LOW] == 1
    assert blocked["id"]


def test_legacy_records_without_the_new_fields_still_decide(db):
    """A record written by the pre-queue `/api/approvals` route must still work."""
    run(db[aq.COLLECTION].insert_one({
        "id": "apr_legacy", "tenant_id": TENANT, "workspace_id": "ws_1",
        "title": "Legacy approval", "kind": "external_effect", "status": "requested",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }))
    assert "apr_legacy" in [r["id"] for r in run(aq.list_requests(db, TENANT))]
    decided = run(aq.decide(db, tenant_id=TENANT, approval_id="apr_legacy",
                            decision=aq.APPROVED, actor="admin@example.com"))
    assert decided["status"] == aq.APPROVED


# ----------------------------------------------------------- refreshing blocks

def test_refreshing_blocks_lets_a_resolved_prerequisite_proceed(db):
    req = _request(db, blocked_reasons=["No delivery provider is registered for email."])
    run(aq.decide(db, tenant_id=TENANT, approval_id=req["id"], decision=aq.APPROVED,
                  actor="admin@example.com"))
    with pytest.raises(aq.InvalidApprovalTransition):
        run(aq.consume(db, tenant_id=TENANT, approval_id=req["id"], actor="worker-1"))

    # The caller re-checked the condition live and it no longer holds.
    refreshed = run(aq.refresh_blocks(db, tenant_id=TENANT, approval_id=req["id"],
                                      blocked_reasons=[], actor="worker-1"))
    assert refreshed["blocked_reasons"] == []
    assert any(h["action"] == "blocks_refreshed" for h in refreshed["history"])
    assert run(aq.consume(db, tenant_id=TENANT, approval_id=req["id"],
                          actor="worker-1"))["execution"]["state"] == aq.EXECUTION_CONSUMED


def test_refreshing_blocks_can_add_a_new_one(db):
    req = _request(db)
    run(aq.decide(db, tenant_id=TENANT, approval_id=req["id"], decision=aq.APPROVED,
                  actor="admin@example.com"))
    run(aq.refresh_blocks(db, tenant_id=TENANT, approval_id=req["id"],
                          blocked_reasons=["Consent was withdrawn."], actor="worker-1"))
    with pytest.raises(aq.InvalidApprovalTransition):
        run(aq.consume(db, tenant_id=TENANT, approval_id=req["id"], actor="worker-1"))


def test_refreshing_blocks_cannot_revive_a_closed_request(db):
    """It must never be a back door that makes a rejected or lapsed request usable."""
    rejected = _request(db, blocked_reasons=["Something"])
    run(aq.decide(db, tenant_id=TENANT, approval_id=rejected["id"], decision=aq.REJECTED,
                  actor="admin@example.com"))
    with pytest.raises(aq.InvalidApprovalTransition):
        run(aq.refresh_blocks(db, tenant_id=TENANT, approval_id=rejected["id"],
                              blocked_reasons=[], actor="worker-1"))

    lapsed = _request(db, blocked_reasons=["Something"])
    _backdate(db, lapsed["id"])
    run(aq.expire_due(db, tenant_id=TENANT))
    with pytest.raises(aq.InvalidApprovalTransition):
        run(aq.refresh_blocks(db, tenant_id=TENANT, approval_id=lapsed["id"],
                              blocked_reasons=[], actor="worker-1"))


def test_refreshing_blocks_is_tenant_scoped(db):
    req = _request(db)
    with pytest.raises(aq.ApprovalNotFound):
        run(aq.refresh_blocks(db, tenant_id=OTHER_TENANT, approval_id=req["id"],
                              blocked_reasons=[], actor="worker-1"))
