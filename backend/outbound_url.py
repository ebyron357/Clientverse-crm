"""Where a tenant-configured webhook may send requests.

Anyone can register an organization and become its admin, and an admin can point a
custom webhook at any URL and then read each delivery's outcome. Without a check, that
makes the server a probe for its own network: loopback services, the platform's private
hosts, and cloud metadata addresses (169.254.169.254) answer with status codes or
connection errors that the delivery log hands back.

Two checks close that:

1. `webhook_url_problem` runs when a webhook is saved. It needs no DNS: https only, a
   real hostname, no credentials in the URL, and no address or name that is private by
   construction (an IP literal in a private range, `localhost`, `*.internal`, ...).
2. `resolve_public_addresses` runs immediately before every delivery attempt. It
   resolves the host and refuses the attempt if ANY resolved address is not public, so a
   name that later starts pointing inside (DNS rebinding) is caught at send time.
   Deliveries also never follow redirects, so a public URL cannot bounce the request to
   a private one.

Delivery connects to a checked numeric address while preserving the original TLS
server name, certificate verification and Host header. No proxy or redirect can
resolve the hostname a second time.

`WEBHOOK_ALLOW_PRIVATE_TARGETS=1` lets local development and the test harness deliver
to their own machine. It is ignored when the app runs in production.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from typing import Optional
from urllib.parse import urlsplit

import certifi
import urllib3

# The resolver this module uses. Tests replace this name, never `socket.getaddrinfo`
# itself: patching the socket module would also redirect the database driver.
_getaddrinfo = socket.getaddrinfo

_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain", ".home.arpa")
_BLOCKED_NAMES = {"localhost", "localhost.localdomain"}


def private_targets_allowed(is_production: bool) -> bool:
    return not is_production and os.environ.get("WEBHOOK_ALLOW_PRIVATE_TARGETS") == "1"


def _is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return _is_public(address.ipv4_mapped)
    return address.is_global and not address.is_multicast


def webhook_url_problem(url: str, *, allow_private: bool = False) -> Optional[str]:
    """Why this URL cannot be a webhook destination, or None when it can."""
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return "Enter a valid URL."
    scheme = parts.scheme.lower()
    if scheme != "https" and not (allow_private and scheme == "http"):
        return "Webhook URLs must start with https://."
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        return "Enter a valid URL with a hostname."
    if parts.username or parts.password:
        return "Remove the username and password from the URL."
    try:
        _ = parts.port  # raises on an invalid port
    except ValueError:
        return "Enter a valid port."
    if allow_private:
        return None
    if host in _BLOCKED_NAMES or host.endswith(_BLOCKED_SUFFIXES):
        return "Webhooks must point to a public address."
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        return None  # a hostname; checked again by resolution at send time
    return None if _is_public(literal) else "Webhooks must point to a public address."


class DestinationRefused(ValueError):
    """A fixed public error label, never raw resolver details."""


def checked_addresses(url: str, *, allow_private: bool = False) -> list[str]:
    if webhook_url_problem(url, allow_private=allow_private):
        raise DestinationRefused("blocked_destination")
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").rstrip(".").encode("idna").decode("ascii")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = _getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        raise DestinationRefused("dns_error") from None
    addresses = list(dict.fromkeys(info[4][0] for info in infos))
    if not addresses:
        raise DestinationRefused("dns_error")
    for raw in addresses:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError:
            raise DestinationRefused("blocked_destination") from None
        if not allow_private and not _is_public(address):
            raise DestinationRefused("blocked_destination")
    return addresses


def resolve_public_addresses(url: str, *, allow_private: bool = False) -> Optional[str]:
    """Compatibility check for callers that only need a refusal reason."""
    try:
        checked_addresses(url, allow_private=allow_private)
    except DestinationRefused as exc:
        return str(exc)
    return None


def post_webhook(url: str, *, data: bytes, headers: dict, timeout: float = 6,
                 allow_private: bool = False) -> int:
    """Resolve once per attempt and send only to that checked address.

    urllib3's explicit pool ignores environment proxies. TLS still verifies the URL
    hostname, not the IP. The caller owns retries, each with a fresh resolution.
    Only response headers are read; webhook bodies can be unbounded.
    """
    addresses = checked_addresses(url, allow_private=allow_private)
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").rstrip(".").encode("idna").decode("ascii")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    authority = f"[{host}]" if ":" in host else host
    if parts.port:
        authority += f":{port}"
    target = parts.path or "/"
    if parts.query:
        target += "?" + parts.query
    options = {"timeout": urllib3.Timeout(connect=timeout, read=timeout), "retries": False}
    if parts.scheme == "https":
        pool = urllib3.HTTPSConnectionPool(addresses[0], port, server_hostname=host,
                                           assert_hostname=host, cert_reqs="CERT_REQUIRED",
                                           ca_certs=certifi.where(), **options)
    else:
        pool = urllib3.HTTPConnectionPool(addresses[0], port, **options)
    try:
        response = pool.urlopen("POST", target, body=data,
                                headers={**headers, "Host": authority},
                                redirect=False, retries=False, preload_content=False,
                                assert_same_host=False)
        try:
            return response.status
        finally:
            response.close()
    finally:
        pool.close()


def delivery_error_reason(error: BaseException) -> str:
    """A coarse, fixed label for a failed delivery attempt. The raw exception text names
    hosts, ports and resolver details, which is exactly what a probe wants to read."""
    name = type(error).__name__
    if "Timeout" in name:
        return "timeout"
    if "SSL" in name:
        return "tls_error"
    if "Connection" in name:
        return "connection_error"
    return "request_error"
