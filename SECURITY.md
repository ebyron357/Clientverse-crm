# Security policy

## Supported versions

ClientVerse is developed on the `main` branch; security fixes are applied there
and released from it. Please upgrade to the latest `main` before reporting.

## Reporting a vulnerability

**Do not open a public issue for security problems.**

Use GitHub's private vulnerability reporting for this repository
(*Security* → *Report a vulnerability*). Include:

- a description of the issue and its impact,
- reproduction steps or a proof of concept,
- affected endpoints/files and any relevant configuration.

You can expect an acknowledgement within 5 business days and a status update as
triage progresses. Please give us a reasonable window to ship a fix before any
public disclosure.

## Deployment hardening checklist

- Generate a strong `JWT_SECRET` (`openssl rand -hex 32`). Startup refuses weak
  or placeholder values; never set `ALLOW_INSECURE_JWT` outside disposable local
  environments.
- After the recovery release, `ADMIN_PASSWORD` is bootstrap-only. Existing credentials are
  changed through Settings or signed-out email recovery, which invalidates older sessions.
  Recovery links are 256-bit random capabilities stored as SHA-256 hashes, expire in 20 minutes,
  and are consumed by an atomic password compare-and-swap. Queued recipients are encrypted,
  rate limits are shared in MongoDB, and public responses do not reveal account existence.
  No reset URL, raw token, password, provider body, or credential is written to audit records.
  See the [Owner/Admin Manual](docs/CLIENTVERSE_CRM_OWNER_ADMIN_MANUAL.md) §9.2 for procedures
  and provider setup. This branch is not deployed or independently security-certified.

- Leave `DEMO_MEMBER_EMAIL` / `DEMO_MEMBER_PASSWORD` unset in production — no
  demo account is seeded unless both are provided.
- Set `CORS_ORIGINS` to the exact browser origins of your deployment.
- Set `WEBHOOK_CRON_SECRET` so `/api/cron/*` endpoints are authenticated.
- Set `INTEGRATION_ENC_KEY` (Fernet) before connecting any OAuth integration —
  credentials are encrypted at rest and are never returned by the API.
- Serve both the API and the SPA over HTTPS so the `access_token` cookie is only
  sent on secure origins.

See `docs/PRODUCTION.md` for the full configuration catalog.
