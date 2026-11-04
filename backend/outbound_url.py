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

A small window remains between the check and the connection (the HTTP library resolves
again). Closing it fully means pinning the connection to the checked address; that is
recorded as follow-up in the audit record rather than hidden.

`WEBHOOK_ALLOW_PRIVATE_TARGETS=1` lets local development and the test harness deliver
to their own machine. It is ignored when the app runs in production.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from typing import Optional
from urllib.parse import urlsplit

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


def resolve_public_addresses(url: str, *, allow_private: bool = False) -> Optional[str]:
    """Resolve the URL's host and return a coarse refusal reason, or None when every
    address it resolves to is public. Blocking: call it off the event loop."""
    problem = webhook_url_problem(url, allow_private=allow_private)
    if problem:
        return "blocked_destination"
    if allow_private:
        return None
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").rstrip(".")
    port = parts.port or 443
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        return "dns_error"
    addresses = {info[4][0] for info in infos}
    if not addresses:
        return "dns_error"
    for raw in addresses:
        try:
            address = ipaddress.ip_address(raw.split("%", 1)[0])
        except ValueError:
            return "blocked_destination"
        if not _is_public(address):
            return "blocked_destination"
    return None


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
