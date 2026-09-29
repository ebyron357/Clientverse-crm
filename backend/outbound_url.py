"""Outbound requests to addresses a tenant chose.

Any visitor can register and become admin of a new tenant, so a webhook URL is an
address chosen by a stranger. Posting to it from inside the platform's network would let
that stranger reach whatever the server can reach: the loopback API, the cloud metadata
service, private services on the same network. This module is the only way such a URL
is called:

  * the URL must be http(s) with a host and no credentials;
  * every address the host resolves to must be publicly routable, checked on every
    send, not only when the URL was saved (DNS can change after it is saved);
  * the connection goes to the address that was checked (pinned), so a second lookup
    at connect time cannot swap in an internal one;
  * redirects are not followed, proxies from the environment are not used, and the
    caller gets a fixed description of a failure rather than the raw error text, which
    would otherwise tell a prober which internal ports are open.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any, Optional
from urllib.parse import SplitResult, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter

ALLOWED_SCHEMES = ("http", "https")
BLOCKED_HOSTNAMES = ("localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback")
BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain")


class UnsafeDestination(ValueError):
    """The URL may not be called from the platform."""


class UnresolvedDestination(UnsafeDestination):
    """The host did not resolve. Allowed when saving, never when sending."""


def _parts(url: str) -> tuple[SplitResult, str, int]:
    parsed = urlsplit((url or "").strip())
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeDestination("The URL must start with http:// or https://")
    if parsed.username or parsed.password:
        raise UnsafeDestination("The URL must not contain a user name or password")
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeDestination("The URL has no host")
    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise UnsafeDestination("The URL's port is not valid") from exc
    return parsed, host, port


NAT64 = ipaddress.ip_network("64:ff9b::/96")
NAT64_LOCAL = ipaddress.ip_network("64:ff9b:1::/48")
IPV4_COMPATIBLE = ipaddress.ip_network("::/96")
IPV4_TRANSLATED = ipaddress.ip_network("::ffff:0:0:0/96")


def _embedded_ipv4(ip: ipaddress.IPv6Address) -> Optional[ipaddress.IPv4Address]:
    """The IPv4 address an IPv6 form carries, where it carries one.

    `is_global` judges the IPv6 wrapper, not what it wraps: NAT64 `64:ff9b::a9fe:a9fe`
    reaches 169.254.169.254 on a network with a NAT64 gateway, and still reads global.
    """
    if ip.ipv4_mapped:
        return ip.ipv4_mapped
    if ip.sixtofour:
        return ip.sixtofour
    if ip.teredo:
        return ip.teredo[1]
    if ip in NAT64 or ip in IPV4_TRANSLATED or ip in IPV4_COMPATIBLE:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address):
        if ip in NAT64_LOCAL or ip.is_site_local:
            return False
        embedded = _embedded_ipv4(ip)
        if embedded is not None:
            return embedded.is_global and not embedded.is_multicast
    return ip.is_global and not ip.is_multicast


def _refuse_named_internal(host: str) -> None:
    if host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_SUFFIXES):
        raise UnsafeDestination("The URL points at an internal host")


def _resolve(host: str, port: int) -> list[str]:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = [str(literal)]
    else:
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except (socket.gaierror, UnicodeError) as exc:
            raise UnresolvedDestination("The URL's host could not be resolved") from exc
        addresses = sorted({str(info[4][0]) for info in infos})
    if not addresses:
        raise UnresolvedDestination("The URL's host could not be resolved")
    if not all(_is_public(address) for address in addresses):
        raise UnsafeDestination("The URL resolves to a private or internal address")
    return addresses


def check(url: str, *, allow_unresolved: bool = False) -> Optional[str]:
    """Refuse a URL that may not be called; return the public address it resolves to.

    With `allow_unresolved` (used when a URL is saved), a host that does not resolve yet
    is accepted and None is returned: it is checked again on every send.
    """
    _, host, port = _parts(url)
    _refuse_named_internal(host)
    try:
        return _resolve(host, port)[0]
    except UnresolvedDestination:
        if allow_unresolved:
            return None
        raise


class _PinnedAdapter(HTTPAdapter):
    """Connects to a checked address while verifying TLS for the original host name."""

    def __init__(self, hostname: str):
        self._hostname = hostname
        super().__init__(max_retries=0)

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        kwargs["server_hostname"] = self._hostname
        kwargs["assert_hostname"] = self._hostname
        super().init_poolmanager(*args, **kwargs)


def post(url: str, *, data: bytes, headers: dict, timeout: float) -> requests.Response:
    """POST to a tenant-chosen URL. Raises UnsafeDestination or requests exceptions."""
    parsed, host, port = _parts(url)
    _refuse_named_internal(host)
    address = _resolve(host, port)[0]
    netloc = f"[{address}]" if ":" in address else address
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    pinned = urlunsplit((parsed.scheme, netloc, parsed.path or "/", parsed.query, ""))
    host_header = parsed.hostname or host
    if parsed.port:
        host_header = f"{host_header}:{parsed.port}"
    session = requests.Session()
    session.trust_env = False
    if parsed.scheme.lower() == "https":
        session.mount("https://", _PinnedAdapter(host))
    try:
        return session.post(pinned, data=data, headers={**headers, "Host": host_header},
                            timeout=timeout, allow_redirects=False)
    finally:
        session.close()


def describe_failure(exc: Exception) -> str:
    """A fixed description of why a send failed. Never the raw error text."""
    if isinstance(exc, UnsafeDestination):
        return str(exc)
    if isinstance(exc, requests.exceptions.SSLError):
        return "TLS handshake failed"
    if isinstance(exc, requests.exceptions.Timeout):
        return "Timed out"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "Could not connect"
    return "Delivery failed"
