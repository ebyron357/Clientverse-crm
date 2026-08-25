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
- Rotate `ADMIN_PASSWORD` immediately after the first login.
- Leave `DEMO_MEMBER_EMAIL` / `DEMO_MEMBER_PASSWORD` unset in production — no
  demo account is seeded unless both are provided.
- Set `CORS_ORIGINS` to the exact browser origins of your deployment.
- Set `WEBHOOK_CRON_SECRET` so `/api/cron/*` endpoints are authenticated.
- Set `INTEGRATION_ENC_KEY` (Fernet) before connecting any OAuth integration —
  credentials are encrypted at rest and are never returned by the API.
- Serve both the API and the SPA over HTTPS so the `access_token` cookie is only
  sent on secure origins.

See `docs/PRODUCTION.md` for the full configuration catalog.
