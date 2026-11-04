"""Fixes from the 2026-11-04 AI quality audit (security batch A).

* SSRF: a self-registered admin could point a webhook at loopback, private or metadata
  addresses and read the outcome from the delivery log. Destinations are now checked
  when saved and re-resolved before every attempt; redirects are not followed; failure
  reasons are coarse labels, not raw connection errors.
* Self-registration accepted any password ("a"); it now uses the same rule as
  invitations and password changes.
* An expired login lockout kept its failure count, so one more wrong guess re-locked
  the account at once; and nothing throttled one address trying many emails.
* The type-check gate printed "clean" when mypy was missing or crashed.
* Custom-field labels reached CSV export headers without the formula guard.

In-process against the real `app`, with a fresh motor client per test for the reason
given in test_security_headers.py.
"""

import os
import socket
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_audit_security_unit")
os.environ.setdefault("JWT_SECRET", "audit-security-unit-jwt-secret-long-enough-1234")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "audit-security-admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "Audit-Security-Admin-1!")

from fastapi.testclient import TestClient

import outbound_url
import server

STRONG = "Str0ng-Passw0rd!"


def _reset_motor_client():
    server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
    server.db = server.mclient[os.environ["DB_NAME"]]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _register(client, password=STRONG):
    response = client.post("/api/auth/register", json={
        "email": f"audit_{uuid.uuid4().hex[:10]}@example.com", "password": password, "name": "Audit"})
    client.cookies.clear()
    return response


@pytest.fixture(autouse=True)
def _no_private_override(monkeypatch):
    monkeypatch.delenv("WEBHOOK_ALLOW_PRIVATE_TARGETS", raising=False)


# ----------------------------------------------------------------------------- SSRF

@pytest.mark.parametrize("url", [
    "http://example.com/hook",            # not https
    "https://127.0.0.1/hook",             # loopback literal
    "https://localhost:8000/hook",        # loopback name
    "https://10.0.0.5/hook",              # private range
    "https://169.254.169.254/latest",     # cloud metadata
    "https://[::1]/hook",                 # IPv6 loopback
    "https://[::ffff:127.0.0.1]/hook",    # IPv4-mapped loopback
    "https://api.railway.internal/hook",  # private DNS suffix
    "https://user:pass@example.com/hook", # credentials in the URL
    "ftp://example.com/hook",
    "not a url",
])
def test_webhook_destinations_that_point_inside_are_refused_when_saved(url):
    _reset_motor_client()
    with TestClient(server.app) as client:
        token = _register(client).json()["token"]
        response = client.post("/api/webhooks", headers=_h(token), json={"name": "probe", "url": url, "events": ["*"]})
        assert response.status_code == 422, (url, response.text)


def test_a_public_https_webhook_is_still_accepted():
    _reset_motor_client()
    with TestClient(server.app) as client:
        token = _register(client).json()["token"]
        response = client.post("/api/webhooks", headers=_h(token),
                               json={"name": "ok", "url": "https://hooks.example.com/in", "events": ["*"]})
        assert response.status_code == 200, response.text


def _fake_resolution(address):
    def getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]
    return getaddrinfo


def test_a_name_that_resolves_inside_is_never_contacted(monkeypatch):
    """DNS rebinding: the hostname passed the save-time check but now resolves to a
    private address. The attempt is refused before any request is made."""
    _reset_motor_client()
    posts = []
    monkeypatch.setattr(outbound_url.socket, "getaddrinfo", _fake_resolution("10.1.2.3"))
    monkeypatch.setattr(server.requests, "post", lambda *a, **k: posts.append((a, k)))
    with TestClient(server.app) as client:
        token = _register(client).json()["token"]
        hook = client.post("/api/webhooks", headers=_h(token),
                           json={"name": "rebind", "url": "https://rebind.example.com/in", "events": ["*"]}).json()
        result = client.post(f"/api/webhooks/{hook['id']}/test", headers=_h(token)).json()
        assert result["status"] == "failed"
        assert posts == []
        delivery = client.get("/api/webhook-deliveries", headers=_h(token)).json()[0]
        assert [a["error"] for a in delivery["attempts"]] == ["blocked_destination"]


def test_deliveries_do_not_follow_redirects_and_store_only_coarse_errors(monkeypatch):
    _reset_motor_client()
    calls = []

    def failing_post(url, **kwargs):
        calls.append(kwargs)
        raise server.requests.exceptions.ConnectionError(
            "HTTPConnectionPool(host='10.0.0.9', port=6379): Max retries exceeded")

    monkeypatch.setattr(outbound_url.socket, "getaddrinfo", _fake_resolution("93.184.216.34"))
    monkeypatch.setattr(server.requests, "post", failing_post)
    with TestClient(server.app) as client:
        token = _register(client).json()["token"]
        hook = client.post("/api/webhooks", headers=_h(token),
                           json={"name": "down", "url": "https://down.example.com/in", "events": ["*"]}).json()
        client.post(f"/api/webhooks/{hook['id']}/test", headers=_h(token))
        assert calls and all(kwargs.get("allow_redirects") is False for kwargs in calls)
        delivery = client.get("/api/webhook-deliveries", headers=_h(token)).json()[0]
        errors = {a["error"] for a in delivery["attempts"]}
        assert errors == {"connection_error"}, errors
        assert "10.0.0.9" not in str(delivery)


def test_the_delivery_log_limit_is_bounded():
    _reset_motor_client()
    with TestClient(server.app) as client:
        token = _register(client).json()["token"]
        assert client.get("/api/webhook-deliveries?limit=100000", headers=_h(token)).status_code == 422


def test_the_private_target_override_never_applies_in_production(monkeypatch):
    monkeypatch.setenv("WEBHOOK_ALLOW_PRIVATE_TARGETS", "1")
    assert outbound_url.private_targets_allowed(is_production=False) is True
    assert outbound_url.private_targets_allowed(is_production=True) is False


# ------------------------------------------------------------------ registration

@pytest.mark.parametrize("password", ["a", "1234567", "        ", "x" * 73])
def test_self_registration_refuses_weak_or_overlong_passwords(password):
    _reset_motor_client()
    with TestClient(server.app) as client:
        response = _register(client, password)
        assert response.status_code == 400, response.text


# ---------------------------------------------------------------------- sign-in

def test_an_expired_lockout_does_not_relock_on_the_next_wrong_guess():
    _reset_motor_client()
    with TestClient(server.app) as client:
        reg = client.post("/api/auth/register", json={
            "email": (email := f"decay_{uuid.uuid4().hex[:10]}@example.com"), "password": STRONG, "name": "Decay"})
        assert reg.status_code == 200
        client.cookies.clear()
        for _ in range(server.LOGIN_LOCKOUT_THRESHOLD):
            client.post("/api/auth/login", json={"email": email, "password": "wrong-password"})

        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

        async def expire():
            await server.db.login_lockouts.update_one({"email": email}, {"$set": {"locked_until": past}})
        client.portal.call(expire)

        client.post("/api/auth/login", json={"email": email, "password": "one-more-wrong"})
        good = client.post("/api/auth/login", json={"email": email, "password": STRONG})
        assert good.status_code == 200, "one wrong guess after expiry re-locked the account"


def test_one_address_trying_many_emails_is_throttled(monkeypatch):
    _reset_motor_client()
    monkeypatch.setattr(server, "LOGIN_IP_FAILURE_LIMIT", 5)
    headers = {"X-Real-IP": f"198.51.100.{uuid.uuid4().int % 250}"}
    with TestClient(server.app) as client:
        for n in range(5):
            r = client.post("/api/auth/login", headers=headers,
                            json={"email": f"stuff_{n}_{uuid.uuid4().hex[:6]}@example.com", "password": "guess"})
            assert r.status_code == 401
        blocked = client.post("/api/auth/login", headers=headers,
                              json={"email": "another@example.com", "password": "guess"})
        assert blocked.status_code == 429
        other = client.post("/api/auth/login", headers={"X-Real-IP": "203.0.113.77"},
                            json={"email": "another@example.com", "password": "guess"})
        assert other.status_code == 401


# ------------------------------------------------------------------ release gates

def test_the_type_check_gate_fails_when_mypy_does_not_run(monkeypatch, capsys):
    sys.path.insert(0, str(BACKEND_DIR.parent / "scripts"))
    import typecheck

    monkeypatch.setattr(typecheck.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="No module named mypy"))
    monkeypatch.setattr(sys, "argv", ["typecheck.py", str(BACKEND_DIR)])
    assert typecheck.main() == 2
    assert "did not complete" in capsys.readouterr().out

    monkeypatch.setattr(typecheck.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=0, stdout="Success: no issues found in 3 source files", stderr=""))
    assert typecheck.main() == 0


def test_custom_field_labels_get_the_csv_formula_guard():
    source = (BACKEND_DIR / "data_transfer.py").read_text()
    assert "crm_core.csv_safe(header) for header, _ in custom_headers" in source
    import crm_core
    assert not crm_core.csv_safe("=HYPERLINK(\"http://x\")").startswith("=")


def test_hsts_is_sent_in_production_even_behind_a_plain_http_proxy_hop():
    source = (BACKEND_DIR / "server.py").read_text()
    assert 'if request.url.scheme == "https" or IS_PRODUCTION:' in source
