"""Regression coverage for audit C-26 and C-31."""
import asyncio
import os
import re
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException, Response
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017/?replicaSet=rs0")
os.environ.setdefault("DB_NAME", "clientverse_audit_closeout")
os.environ.setdefault("JWT_SECRET", "audit-closeout-test-only-secret-long-enough")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "audit-closeout@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "Audit-Closeout-Password-1!")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")

import crm_core
import outbound_url
import server


@pytest.mark.parametrize("model,valid", [
    (server.TaskStatus, "done"), (server.DeliverableStatus, "approved"),
    (server.RequestStatus, "done"), (server.ApprovalDecision, "rejected"),
    (server.CommitmentPatch, "fulfilled"), (server.OutcomePatch, "at_risk"),
])
def test_status_models_reject_unknown_states(model, valid):
    assert model(status=valid).status == valid
    with pytest.raises(ValidationError):
        model(status="arbitrary-unrecognized-state")


@pytest.mark.parametrize("model", [server.TaskInput, server.DeliverableInput,
                                  server.RequestInput, server.ApprovalInput,
                                  server.CommitmentInput, server.OutcomeInput])
def test_creation_rejects_unknown_status(model):
    with pytest.raises(ValidationError):
        model(workspace_id="workspace", title="item", status="unknown")


@pytest.mark.parametrize("term", ["a" * 199 + "[", "a" * 199 + "\\", "[" * 250,
                                 ".*" * 250, "a" * 10000])
def test_long_search_remains_a_valid_literal_regex(term):
    pattern = crm_core._escape_regex(term)
    assert re.fullmatch(pattern, term[:200])


def test_losing_registration_removes_only_its_empty_organization(monkeypatch):
    tenants = AsyncMock()
    users = AsyncMock()
    users.find_one.return_value = None  # both registrants passed the preflight
    users.insert_one.side_effect = DuplicateKeyError("another registration won")
    memberships = AsyncMock()
    monkeypatch.setattr(server, "db", SimpleNamespace(tenants=tenants, users=users,
                                                     memberships=memberships))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.register(server.RegisterInput(
            email="race@example.com", name="Race", password="Strong-Password-1!"), Response()))
    assert exc.value.status_code == 400
    created = tenants.insert_one.call_args.args[0]
    tenants.delete_one.assert_awaited_once_with({"tenant_id": created["tenant_id"]})
    memberships.insert_one.assert_not_called()


def test_membership_unique_index_rejects_duplicates(monkeypatch):
    import uuid

    from pymongo import MongoClient
    if os.getenv("MONGO_URL", "").startswith("mongomock"):
        pytest.skip("Requires real MongoDB index migration semantics")
    client = MongoClient(os.environ["MONGO_URL"])
    database = client["audit_index_" + uuid.uuid4().hex]
    try:
        collection = database.memberships
        keys = [("tenant_id", 1), ("user_id", 1)]
        collection.create_index(keys)  # upgrade an existing non-unique index
        from motor.motor_asyncio import AsyncIOMotorClient
        async def seed():
            motor = AsyncIOMotorClient(os.environ["MONGO_URL"])
            try:
                monkeypatch.setattr(server, "db", motor[database.name])
                await server.seed()
            finally:
                motor.close()
        asyncio.run(seed())
        collection.insert_one({"tenant_id": "a", "user_id": "u"})
        with pytest.raises(DuplicateKeyError):
            collection.insert_one({"tenant_id": "a", "user_id": "u"})
        collection.insert_one({"tenant_id": "b", "user_id": "u"})
    finally:
        client.drop_database(database.name)
        client.close()


@pytest.mark.parametrize("address", ["93.184.216.34", "2606:4700:4700::1111"])
def test_pinned_delivery_preserves_tls_identity_and_cannot_rebind(monkeypatch, address):
    resolutions = []
    pools = []
    requests = []
    def resolve(host, port, **kwargs):
        resolutions.append(host)
        # A second lookup of the hostname would now point inside.
        ip = address if len(resolutions) == 1 else "127.0.0.1"
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET,
                 socket.SOCK_STREAM, 6, "", (ip, port))]
    class Pool:
        def __init__(self, host, port, **kwargs):
            pools.append((host, port, kwargs))
        def urlopen(self, method, target, **kwargs):
            requests.append((method, target, kwargs))
            return SimpleNamespace(status=302, close=lambda: None)
        def close(self):
            pass
    monkeypatch.setattr(outbound_url, "_getaddrinfo", resolve)
    monkeypatch.setattr(outbound_url.urllib3, "HTTPSConnectionPool", Pool)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9999")
    assert outbound_url.post_webhook("https://hooks.example.com:8443/send?q=1",
                                     data=b"signed", headers={"X-Signature": "sig"}) == 302
    assert resolutions == ["hooks.example.com"]
    host, port, options = pools[0]
    assert (host, port) == (address, 8443)
    assert options["server_hostname"] == options["assert_hostname"] == "hooks.example.com"
    assert options["cert_reqs"] == "CERT_REQUIRED"
    assert options["ca_certs"]
    method, target, kwargs = requests[0]
    assert (method, target) == ("POST", "/send?q=1")
    assert kwargs["headers"]["Host"] == "hooks.example.com:8443"
    assert kwargs["body"] == b"signed"
    assert kwargs["redirect"] is False and kwargs["retries"] is False


def test_mixed_public_private_resolution_never_opens_a_pool(monkeypatch):
    monkeypatch.setattr(outbound_url, "_getaddrinfo", lambda *a, **kw: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))
        for ip in ["93.184.216.34", "169.254.169.254"]])
    def forbidden(*a, **kw):
        pytest.fail("must refuse before opening a connection")
    monkeypatch.setattr(outbound_url.urllib3, "HTTPSConnectionPool", forbidden)
    with pytest.raises(outbound_url.DestinationRefused, match="blocked_destination"):
        outbound_url.post_webhook("https://hooks.example.com", data=b"", headers={})
