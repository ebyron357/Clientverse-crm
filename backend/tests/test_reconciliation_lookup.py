"""A lookup that fails or is refused cannot prove an earlier email was never delivered."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from test_provider_lifecycle_unit import server

ANSWERS = [
    (server.gmail_provider.GmailNotAuthorized("OAuth grant revoked"), "unresolved"),
    (server.conversation_service.DeliveryRejected("Lookup refused"), "unresolved"),
    (RuntimeError("Provider unavailable"), "unresolved"),
    (None, "resolved_failed"),
    ("provider-message-1", "resolved_sent"),
]


def _lookup(answer):
    if isinstance(answer, Exception):
        return AsyncMock(side_effect=answer)
    return AsyncMock(return_value=answer)


def _wire(monkeypatch, lookup):
    registry = SimpleNamespace(get=lambda _channel: SimpleNamespace(locate=lookup))
    monkeypatch.setattr(server.conversation_service, "REGISTRY", registry)
    reconcile = AsyncMock(return_value={"status": "reconciled"})
    monkeypatch.setattr(server.conversation_service, "reconcile_unknown", reconcile)
    return reconcile


@pytest.mark.parametrize("answer, expected", ANSWERS)
def test_only_a_completed_lookup_resolves_an_unknown_dispatch(monkeypatch, answer, expected):
    message = {"id": "msg_1", "tenant_id": "tenant_a", "channel": "email", "attempt_count": 1}
    cursor = SimpleNamespace(to_list=AsyncMock(return_value=[message]))
    messages = SimpleNamespace(find=lambda *_args, **_kwargs: cursor)
    monkeypatch.setattr(server, "db", {server.conversation_service.MESSAGES: messages})
    lookup = _lookup(answer)
    reconcile = _wire(monkeypatch, lookup)

    result = asyncio.run(server.run_reconcile_unknown_sweep())

    assert result["examined"] == 1
    assert result[expected] == 1
    assert sum(result[key] for key in ("unresolved", "resolved_failed", "resolved_sent")) == 1
    assert lookup.await_args.kwargs["tenant_id"] == "tenant_a"
    if expected == "unresolved":
        reconcile.assert_not_awaited()
    else:
        reconcile.assert_awaited_once()
        assert reconcile.await_args.kwargs["found"] is (answer is not None)
        assert reconcile.await_args.kwargs["tenant_id"] == "tenant_a"


@pytest.mark.parametrize("answer, expected", ANSWERS)
def test_manual_reconcile_never_records_absence_from_a_failed_lookup(monkeypatch, answer, expected):
    message = {"id": "msg_1", "tenant_id": "tenant_a", "channel": "email",
               "status": server.conversation_service.OUTCOME_UNKNOWN}
    monkeypatch.setattr(server.conversation_service, "get_message", AsyncMock(return_value=message))
    monkeypatch.setattr(server, "record_event", AsyncMock())
    lookup = _lookup(answer)
    reconcile = _wire(monkeypatch, lookup)
    admin = {"tenant_id": "tenant_a", "email": "admin@example.com", "role": "admin"}

    if expected == "unresolved":
        with pytest.raises(HTTPException) as refused:
            asyncio.run(server.reconcile_message("msg_1", user=admin))
        assert refused.value.status_code == 502
        reconcile.assert_not_awaited()
    else:
        asyncio.run(server.reconcile_message("msg_1", user=admin))
        reconcile.assert_awaited_once()
        assert reconcile.await_args.kwargs["found"] is (answer is not None)
        assert reconcile.await_args.kwargs["tenant_id"] == "tenant_a"
