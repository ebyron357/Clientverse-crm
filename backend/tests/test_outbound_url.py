"""A webhook URL is an address chosen by a stranger; the platform must not call inward.

Any visitor can register and administer a new tenant, so these are the probes that
visitor could run with a webhook: the loopback API, the cloud metadata service, private
ranges, IPv6 and IPv4-mapped forms, names that resolve inward, and redirects.
"""

import os
import socket
import uuid

import pytest
import requests

import outbound_url


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8001/api/health",
    "http://localhost:8001/",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/",
    "http://192.168.1.1/",
    "http://172.16.0.1/",
    "http://[::1]/",
    "http://[::ffff:127.0.0.1]/",
    "http://[64:ff9b::a9fe:a9fe]/",       # NAT64 -> 169.254.169.254
    "http://[64:ff9b::a00:1]/",           # NAT64 -> 10.0.0.1
    "http://[::7f00:1]/",                 # IPv4-compatible -> 127.0.0.1
    "http://[::ffff:0:a9fe:a9fe]/",       # IPv4-translated -> 169.254.169.254
    "http://[2002:a9fe:a9fe::1]/",        # 6to4 -> 169.254.169.254
    "http://[fec0::1]/",                  # deprecated site-local
    "http://0.0.0.0/",
    "http://100.64.0.1/",
    "http://metadata.google.internal/",
    "http://printer.local/",
    "file:///etc/passwd",
    "gopher://example.com/",
    "http://user:pass@example.com/",
    "http:///nohost",
])
def test_an_internal_or_malformed_destination_is_refused(url):
    with pytest.raises(outbound_url.UnsafeDestination):
        outbound_url.check(url)
    with pytest.raises(outbound_url.UnsafeDestination):
        outbound_url.post(url, data=b"{}", headers={}, timeout=1)


def test_a_name_that_resolves_inward_is_refused_on_every_send(monkeypatch):
    def resolves_to_loopback(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolves_to_loopback)
    with pytest.raises(outbound_url.UnsafeDestination, match="private or internal"):
        outbound_url.post("https://rebinding.example.com/hook", data=b"{}", headers={},
                          timeout=1)


def test_a_host_that_does_not_resolve_may_be_saved_but_is_never_sent_to():
    assert outbound_url.check("https://hooks.invalid/x", allow_unresolved=True) is None
    with pytest.raises(outbound_url.UnresolvedDestination):
        outbound_url.check("https://hooks.invalid/x")


def test_the_connection_goes_to_the_checked_address_without_redirects(monkeypatch):
    seen = {}

    def resolves_public(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    def fake_send(self, request, **kwargs):
        seen["url"], seen["host"] = request.url, request.headers.get("Host")
        seen["allow_redirects"] = kwargs.get("allow_redirects")
        seen["proxies"] = kwargs.get("proxies")
        response = requests.Response()
        response.status_code = 302
        response.headers["Location"] = "http://127.0.0.1:8001/"
        response.request = request
        return response

    monkeypatch.setattr(socket, "getaddrinfo", resolves_public)
    monkeypatch.setattr(requests.Session, "send", fake_send)
    response = outbound_url.post("http://hooks.example.com:8080/in?x=1", data=b"{}",
                                 headers={}, timeout=1)
    assert seen["url"] == "http://93.184.216.34:8080/in?x=1"
    assert seen["host"] == "hooks.example.com:8080"
    assert seen["allow_redirects"] is False
    assert not seen["proxies"]
    assert response.status_code == 302, "a redirect is a failed delivery, not followed"


def test_failures_are_described_without_the_raw_error_text():
    probe = requests.exceptions.ConnectionError(
        "HTTPConnectionPool(host='10.0.0.5', port=6379): [Errno 111] Connection refused")
    assert outbound_url.describe_failure(probe) == "Could not connect"
    assert outbound_url.describe_failure(requests.exceptions.ReadTimeout()) == "Timed out"
    assert outbound_url.describe_failure(RuntimeError("secret detail")) == "Delivery failed"


# ------------------------------------------------------------------ through the API

API = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/") + "/api"


def _stranger():
    response = requests.post(f"{API}/auth/register", json={
        "email": f"ssrf_{uuid.uuid4().hex[:10]}@example.com",
        "password": "OutboundTest2026!", "name": "Stranger"}, timeout=30)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_a_new_tenant_cannot_point_a_webhook_at_the_platform():
    admin = _stranger()
    for url in ("http://127.0.0.1:8001/api/health", "http://169.254.169.254/latest/"):
        refused = requests.post(f"{API}/webhooks", headers=admin, timeout=30,
                                json={"name": "probe", "url": url, "events": ["*"]})
        assert refused.status_code == 422, (url, refused.text)


def test_a_failed_delivery_does_not_echo_the_network_error():
    admin = _stranger()
    created = requests.post(f"{API}/webhooks", headers=admin, timeout=30,
                            json={"name": "later", "url": "https://hooks.invalid/in",
                                  "events": ["*"]})
    assert created.status_code == 200, created.text
    tested = requests.post(f"{API}/webhooks/{created.json()['id']}/test", headers=admin,
                           timeout=60)
    assert tested.json()["status"] == "failed"
    deliveries = requests.get(f"{API}/webhook-deliveries", headers=admin, timeout=30).json()
    errors = {a["error"] for d in deliveries for a in d["attempts"]}
    assert errors == {"The URL's host could not be resolved"}
    assert len(deliveries[0]["attempts"]) == 1, "a refused destination is not retried"
