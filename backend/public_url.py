"""Which public addresses the CRM may put in links, callbacks and scheduled calls.

The CRM builds outward-facing URLs from configuration:

* `FRONTEND_URL` -- invitation links, booking manage links, website-form links, the page
  Google sends the owner back to after connecting;
* `GOOGLE_REDIRECT_URI` (or `PUBLIC_BACKEND_URL` + `/api/integrations/google/callback`) --
  the address Google calls back with the OAuth code;
* the GitHub secret `CLIENTVERSE_PRODUCTION_URL` -- where `.github/workflows/scheduled-jobs.yml`
  sends `/api/cron/*` calls.

Each of these has gone wrong in a way that still "worked": the scheduler secret was found
pointing at a Vercel copy of the screens (`*.vercel.app`) that forwards `/api` to Railway,
and old preview hosts (Render, Emergent, Manus) were once live addresses. A link or a
callback on such a host keeps working until the copy is deleted, and then fails silently.
A localhost or private address in production is simply broken.

This module says, without any network access, what is wrong with an address:

* `local`    -- localhost, `*.local`/`*.internal`, or a private / loopback IP literal;
* `preview`  -- a host on a preview or copy platform (`*.vercel.app`, `*.netlify.app`, ...);
* `insecure` -- not `https://` (production only);
* `invalid`  -- not a usable absolute base URL (credentials, query, fragment, no host).

The application refuses to boot in production on a `local`, `insecure` or `invalid`
`FRONTEND_URL` (those are already broken), logs a `preview` one loudly, and refuses to
start a Google connection whose callback has any finding. The scheduler workflow runs
`python backend/public_url.py scheduler "$URL"`, which additionally requires one of the
known production hosts and exits non-zero, with a GitHub error annotation, otherwise.

Standard library only, so the workflow can run it without installing the backend.
"""
from __future__ import annotations

import ipaddress
import sys
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

# The address people use. Everything else is either the Railway fallback or wrong.
CANONICAL_PRODUCTION_URL = "https://crm.clientverse.io"
RAILWAY_PRODUCTION_HOST = "clientverse-crm-production-production.up.railway.app"
# The hosts the scheduler may call. Adding a production domain is a code change on
# purpose: the secret alone must not be able to aim production traffic somewhere new.
PRODUCTION_HOSTS = ("crm.clientverse.io", RAILWAY_PRODUCTION_HOST)

GOOGLE_CALLBACK_PATH = "/api/integrations/google/callback"

LOCAL = "local"
PREVIEW = "preview"
INSECURE = "insecure"
INVALID = "invalid"
# Kinds that mean the address cannot work at all in production.
FATAL_IN_PRODUCTION = frozenset({LOCAL, INSECURE, INVALID})

_LOCAL_NAMES = {"localhost", "localhost.localdomain"}
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain", ".home.arpa")
# Hosting platforms whose default hostnames are previews or copies, never this CRM's
# production. `up.railway.app` is deliberately absent: production's own Railway address
# lives there and is listed in PRODUCTION_HOSTS.
_PREVIEW_SUFFIXES = (
    ".vercel.app", ".vercel.sh", ".now.sh", ".netlify.app", ".netlify.com", ".pages.dev",
    ".workers.dev", ".onrender.com", ".herokuapp.com", ".ngrok.io", ".ngrok-free.app",
    ".ngrok.app", ".trycloudflare.com", ".loca.lt", ".github.dev", ".gitpod.io",
    ".preview.emergentagent.com", ".emergent.host", ".manus.space", ".manus.computer",
)


@dataclass(frozen=True)
class Finding:
    kind: str
    message: str


def host_of(url: Optional[str]) -> str:
    """The lower-cased hostname of `url`, or '' when there is none. Never raises."""
    try:
        return (urlsplit((url or "").strip()).hostname or "").rstrip(".").lower()
    except ValueError:
        return ""


def normalize(url: Optional[str]) -> str:
    """`url` without surrounding space or trailing slashes."""
    return (url or "").strip().rstrip("/")


def _is_local_literal(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return not address.is_global


def is_preview_host(host: str) -> bool:
    return bool(host) and host.endswith(_PREVIEW_SUFFIXES)


def check(url: Optional[str], *, production: bool, name: str = "The address",
          allow_path: bool = False) -> list[Finding]:
    """Everything wrong with `url` as a public base address. Empty means usable.

    `allow_path` permits a path (a callback URI has one); a base URL may only end in `/`.
    Outside production only `invalid` findings are reported: local development
    legitimately runs on plain http and localhost.
    """
    raw = (url or "").strip()
    if not raw:
        return [Finding(INVALID, f"{name} is not set.")]
    try:
        parts = urlsplit(raw)
        _ = parts.port  # raises on an invalid port
    except ValueError:
        return [Finding(INVALID, f"{name} is not a valid URL.")]
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").rstrip(".").lower()
    if scheme not in ("http", "https") or not host:
        return [Finding(INVALID, f"{name} must be an absolute http(s) URL with a hostname.")]
    findings: list[Finding] = []
    if parts.username or parts.password:
        findings.append(Finding(INVALID, f"{name} must not contain a username or password."))
    if parts.query or parts.fragment:
        findings.append(Finding(INVALID, f"{name} must not contain '?' or '#'."))
    if not allow_path and parts.path not in ("", "/"):
        findings.append(Finding(INVALID, f"{name} must be a bare address with no path."))
    if not production:
        return findings
    if scheme != "https":
        findings.append(Finding(INSECURE, f"{name} must use https:// in production."))
    if host in _LOCAL_NAMES or host.endswith(_LOCAL_SUFFIXES) or _is_local_literal(host):
        findings.append(Finding(
            LOCAL, f"{name} points at a local or private address ({host}); nothing outside "
                   f"this machine can reach it."))
    elif is_preview_host(host):
        findings.append(Finding(
            PREVIEW, f"{name} points at a preview or copy host ({host}), not production. "
                     f"Use {CANONICAL_PRODUCTION_URL}."))
    return findings


def fatal(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.kind in FATAL_IN_PRODUCTION]


def check_google_redirect(uri: Optional[str], *, production: bool) -> list[Finding]:
    """Findings for the OAuth callback Google is told to call."""
    findings = check(uri, production=production, name="GOOGLE_REDIRECT_URI", allow_path=True)
    if findings and findings[0].kind == INVALID and "not set" in findings[0].message:
        return findings
    try:
        path = urlsplit((uri or "").strip()).path.rstrip("/")
    except ValueError:
        return findings
    if path != GOOGLE_CALLBACK_PATH:
        findings.append(Finding(
            INVALID, f"GOOGLE_REDIRECT_URI must end in {GOOGLE_CALLBACK_PATH}."))
    return findings


def check_scheduler_target(url: Optional[str]) -> list[Finding]:
    """Findings for the scheduler's CLIENTVERSE_PRODUCTION_URL. Empty means call it.

    Stricter than `check`: the host must be one of PRODUCTION_HOSTS, because the
    scheduler authenticates with the cron secret and must never present it elsewhere.
    """
    findings = check(url, production=True, name="CLIENTVERSE_PRODUCTION_URL")
    if findings:
        return findings
    host = host_of(url)
    if host not in PRODUCTION_HOSTS:
        return [Finding(
            INVALID, f"CLIENTVERSE_PRODUCTION_URL points at {host}, which is not a known "
                     f"production address ({', '.join(PRODUCTION_HOSTS)}). Set it to "
                     f"{CANONICAL_PRODUCTION_URL}.")]
    return []


def report(name: str, url: Optional[str], findings: list[Finding]) -> dict:
    """A JSON-safe summary for health output: the host and the problems, never more."""
    return {"name": name, "host": host_of(url) or None, "ok": not findings,
            "problems": [{"kind": f.kind, "message": f.message} for f in findings]}


def _main(argv: list[str]) -> int:
    """`python public_url.py scheduler <url>`: print the normalized URL, or fail.

    The URL is read from argv because a workflow passes it from a secret; on failure only
    the findings are printed (they name the host, never the full value).
    """
    if len(argv) != 3 or argv[1] != "scheduler":
        print("usage: public_url.py scheduler <url>", file=sys.stderr)
        return 2
    findings = check_scheduler_target(argv[2])
    if findings:
        for finding in findings:
            print(f"::error title=Scheduler address refused ({finding.kind})::{finding.message} "
                  f"No production request was made.")
        return 1
    print(normalize(argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
