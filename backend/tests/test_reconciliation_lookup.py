"""A failed lookup cannot prove that an earlier email was never delivered."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_provider_lifecycle_unit import server


@pytest.mark.parametrize("answer, expected", [
    (server.gmail_provider.GmailNotAuthorized("OAuth grant revoked"), "unresolved"),
    (server.conversation_service.DeliveryRejected("Lookup refused"), "unresolved"),
    (RuntimeError("Provider unavailable"), "unresolved"),
    (None, "resolved_failed"),
    ("provider-message-1", "resolved_sent"),
])
def test_only_successful_lookup_resolves_unknown_dispatch(monkeypatch, answer, expected):
    message = {"id": "msg_1", "tenant_id": "tenant_a", "channel": "email", "attempt_count": 1}
    cursor = SimpleNamespace(to_list=AsyncMock(return_value=[message]))
    messages = SimpleNamespace(find=lambda *_args, **_kwargs: cursor)
    monkeypatch.setattr(server, "db", {server.conversation_service.MESSAGES: messages})
    lookup = AsyncMock(side_effect=answer) if isinstance(answer, Exception) else AsyncMock(return_value=answer)
    registry = SimpleNamespace(get=lambda _channel: SimpleNamespace(locate=lookup))
    monkeypatch.setattr(server.conversation_service, "REGISTRY", registry)
    reconcile = AsyncMock()
    monkeypatch.setattr(server.conversation_service, "reconcile_unknown", reconcile)

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
