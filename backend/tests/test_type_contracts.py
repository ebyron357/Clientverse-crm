"""Behavior at nullable boundaries made explicit by backend type checking."""

import asyncio
from unittest.mock import AsyncMock

import pytest

import approval_queue
import conversations
import recovery_case
import server


@pytest.mark.parametrize("module", [approval_queue, conversations, recovery_case])
def test_document_serializers_distinguish_missing_from_empty_records(module):
    assert module._public(None) is None
    assert module._public({}) == {}
    source = {"_id": "private", "id": "record", "status": "open"}
    assert module._public(source) == {"id": "record", "status": "open"}
    assert source["_id"] == "private"


@pytest.mark.parametrize("event_type", [None, ""])
def test_missing_event_type_cannot_match_even_a_wildcard_webhook(event_type):
    assert server.event_matches(event_type, ["*", "contact.*"]) is False


def test_approval_without_tenant_refuses_before_execution(monkeypatch):
    consume = AsyncMock()
    execute = AsyncMock()
    monkeypatch.setattr(server.approval_service, "consume", consume)
    monkeypatch.setattr(server, "execute_pending_mcp", execute)
    approval = {"id": "approval", "kind": "mcp_write", "status": "approved",
                "pending_action_id": "pending"}

    with pytest.raises(server.HTTPException) as error:
        asyncio.run(server._apply_approval_side_effects(approval, {"email": "owner@example.com"}))

    assert error.value.status_code == 400
    consume.assert_not_awaited()
    execute.assert_not_awaited()


@pytest.mark.parametrize("handler,service,method", [
    (server._handle_generate_next_best_actions, server.nba_service, "generate"),
    (server._handle_run_recovery_case, server.recovery_runner_service, "run_case"),
])
def test_background_work_without_tenant_refuses_before_domain_work(monkeypatch, handler, service, method):
    execute = AsyncMock()
    monkeypatch.setattr(service, method, execute)

    with pytest.raises(ValueError, match="tenant context"):
        asyncio.run(handler({"payload": {"case_id": "case"}}))

    execute.assert_not_awaited()
