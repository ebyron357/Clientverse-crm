"""C-31: real TLS verifies the hostname while the transport dials the checked IP."""
import ipaddress
import socket
import ssl
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import urllib3
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import outbound_url


def resolution(*addresses):
    return [(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM,
             socket.IPPROTO_TCP, "", (address, 443)) for address in addresses]


@pytest.fixture
def https_hook(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hooks.example.com")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("hooks.example.com")]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    requests, sni = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append({"path": self.path, "host": self.headers["Host"],
                             "body": self.rfile.read(int(self.headers["Content-Length"]))})
            self.send_response(302)
            self.send_header("Location", "https://127.0.0.1/private")
            self.end_headers()

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    context.set_servername_callback(lambda sock, server_name, ctx: sni.append(server_name))
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_port, str(cert_path), requests, sni
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("address", ["93.184.216.34", "2606:4700:4700::1111"])
def test_pinned_transport_preserves_tls_name_host_and_body_without_redirects(https_hook, monkeypatch, address):
    port, ca, received, sni = https_hook
    lookups, connections = [], []
    def rebinding(host, port, **kwargs):
        lookups.append(host)
        return resolution(address if len(lookups) == 1 else "127.0.0.1")
    monkeypatch.setattr(outbound_url, "_getaddrinfo", rebinding)
    original_pool = urllib3.HTTPSConnectionPool
    monkeypatch.setattr(urllib3, "HTTPSConnectionPool", lambda *a, **kw: original_pool(*a, ca_certs=ca, **kw))

    def dial(destination, *args, **kwargs):
        connections.append(destination)
        # The real urllib3 transport must receive a numeric, validated destination.
        assert ipaddress.ip_address(destination[0]) == ipaddress.ip_address(address)
        assert destination[1] == port
        return socket.create_connection(("127.0.0.1", port), timeout=3)
    monkeypatch.setattr(urllib3.util.connection, "create_connection", dial)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    result = outbound_url.post_webhook(f"https://hooks.example.com:{port}/in?a=1", data=b'{"test":true}',
                                      headers={"Content-Type": "application/json"})
    assert result == 302
    assert lookups == ["hooks.example.com"]
    assert len(connections) == 1
    assert sni == ["hooks.example.com"]
    assert received == [{"path": "/in?a=1", "host": f"hooks.example.com:{port}", "body": b'{"test":true}'}]


def test_pinning_does_not_disable_certificate_hostname_verification(https_hook, monkeypatch):
    port, ca, received, _ = https_hook
    monkeypatch.setattr(outbound_url, "_getaddrinfo", lambda *a, **kw: resolution("93.184.216.34"))
    original_pool = urllib3.HTTPSConnectionPool
    monkeypatch.setattr(urllib3, "HTTPSConnectionPool", lambda *a, **kw: original_pool(*a, ca_certs=ca, **kw))
    monkeypatch.setattr(urllib3.util.connection, "create_connection",
                        lambda *a, **kw: socket.create_connection(("127.0.0.1", port), timeout=3))
    with pytest.raises(urllib3.exceptions.SSLError):
        outbound_url.post_webhook(f"https://wrong.example.com:{port}/in", data=b"secret", headers={})
    assert received == []


def test_unreachable_address_falls_back_only_to_an_already_checked_address(https_hook, monkeypatch):
    port, ca, received, sni = https_hook
    addresses = ["2606:4700:4700::1111", "93.184.216.34"]
    monkeypatch.setattr(outbound_url, "_getaddrinfo", lambda *a, **kw: resolution(*addresses))
    original_pool = urllib3.HTTPSConnectionPool
    monkeypatch.setattr(urllib3, "HTTPSConnectionPool", lambda *a, **kw: original_pool(*a, ca_certs=ca, **kw))
    dialed = []
    def dial(destination, *args, **kwargs):
        dialed.append(destination[0])
        if destination[0] == addresses[0]:
            raise ConnectionRefusedError("No IPv6 route in this environment")
        assert destination[0] == addresses[1]
        return socket.create_connection(("127.0.0.1", port), timeout=3)
    monkeypatch.setattr(urllib3.util.connection, "create_connection", dial)
    assert outbound_url.post_webhook(f"https://hooks.example.com:{port}/in", data=b"once", headers={}) == 302
    assert dialed == addresses
    assert len(received) == 1
    assert sni == ["hooks.example.com"]


def test_read_failure_does_not_silently_post_to_another_address(monkeypatch):
    addresses = ["93.184.216.34", "1.1.1.1"]
    monkeypatch.setattr(outbound_url, "_getaddrinfo", lambda *a, **kw: resolution(*addresses))
    calls = []
    def timed_out(pool, *args, **kwargs):
        calls.append(pool.host)
        raise urllib3.exceptions.ReadTimeoutError(pool, "/in", "The request may already have been received")
    monkeypatch.setattr(urllib3.HTTPSConnectionPool, "urlopen", timed_out)
    with pytest.raises(urllib3.exceptions.ReadTimeoutError):
        outbound_url.post_webhook("https://hooks.example.com/in", data=b"once", headers={})
    assert calls == [addresses[0]]


@pytest.mark.parametrize("addresses", [
    ("93.184.216.34", "10.0.0.1"), ("93.184.216.34", "::1"),
    ("::ffff:127.0.0.1",), ("169.254.169.254",), (),
])
def test_all_resolved_addresses_must_be_public_before_connecting(monkeypatch, addresses):
    monkeypatch.setattr(outbound_url, "_getaddrinfo", lambda *a, **kw: resolution(*addresses))
    def unexpected_connection(*args, **kwargs):
        pytest.fail("A refused destination must not open a connection")
    monkeypatch.setattr(urllib3, "HTTPSConnectionPool", unexpected_connection)
    with pytest.raises(outbound_url.DestinationRefused):
        outbound_url.post_webhook("https://hooks.example.com/in", data=b"secret", headers={})


@pytest.mark.parametrize("elapsed,expected", [(2, [6, 4, 2]), (6, [6])])
def test_address_fallback_shares_one_timeout_budget(monkeypatch, elapsed, expected):
    clock, budgets = [100], []
    monkeypatch.setattr(outbound_url, "_monotonic", lambda: clock[0], raising=False)
    monkeypatch.setattr(outbound_url, "_getaddrinfo",
                        lambda *a, **kw: resolution(*(f"93.184.216.{i}" for i in range(1, 9))))
    def unreachable(pool, *args, **kwargs):
        budgets.append(pool.timeout.total)
        clock[0] += elapsed
        raise urllib3.exceptions.ConnectTimeoutError("unreachable")
    monkeypatch.setattr(urllib3.HTTPSConnectionPool, "urlopen", unreachable)
    with pytest.raises(urllib3.exceptions.ConnectTimeoutError):
        outbound_url.post_webhook("https://hooks.example.com/in", data=b"once", headers={}, timeout=6)
    assert budgets == expected


def test_fast_failures_cannot_walk_an_unbounded_dns_answer(monkeypatch):
    calls = []
    monkeypatch.setattr(outbound_url, "_getaddrinfo",
                        lambda *a, **kw: resolution(*(f"93.184.216.{i}" for i in range(1, 50))))
    def unreachable(pool, *args, **kwargs):
        calls.append(pool.host)
        raise urllib3.exceptions.NewConnectionError(None, "unreachable")
    monkeypatch.setattr(urllib3.HTTPSConnectionPool, "urlopen", unreachable)
    with pytest.raises(urllib3.exceptions.ConnectTimeoutError):
        outbound_url.post_webhook("https://hooks.example.com/in", data=b"once", headers={})
    assert calls == ["93.184.216.1", "93.184.216.2", "93.184.216.3"]


def test_address_limit_does_not_skip_validation_of_later_dns_answers(monkeypatch):
    test_all_resolved_addresses_must_be_public_before_connecting(
        monkeypatch, [*(f"93.184.216.{i}" for i in range(1, 10)), "127.0.0.1"])


def test_expired_budget_after_resolution_does_not_start_a_connection(monkeypatch):
    clock = [100]
    monkeypatch.setattr(outbound_url, "_monotonic", lambda: clock[0], raising=False)
    def slow_resolution(*args, **kwargs):
        clock[0] += 7
        return resolution("93.184.216.34")
    monkeypatch.setattr(outbound_url, "_getaddrinfo", slow_resolution)
    def unexpected_connection(*args, **kwargs):
        pytest.fail("Resolution consumed the attempt's budget")
    monkeypatch.setattr(urllib3, "HTTPSConnectionPool", unexpected_connection)
    with pytest.raises(urllib3.exceptions.ConnectTimeoutError):
        outbound_url.post_webhook("https://hooks.example.com/in", data=b"once", headers={}, timeout=6)
