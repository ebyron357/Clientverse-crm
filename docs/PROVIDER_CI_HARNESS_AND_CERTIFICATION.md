# Provider CI harness and live certification procedure

**Scope of this document:** credential-free CI mock/harness evidence versus the separate Owner-gated live certification for Gmail, Google Calendar, and Stripe.

**Status (Issue #10):** mocks/CI harness only. Live credential-backed certification remains **BLOCKED** pending Owner Google OAuth and Stripe test secrets. Do not treat deterministic pytest green as provider certification. **DoD #4 (live provider certification) is NOT claimed.**

## What CI proves (credential-free)

GitHub Actions and local `pytest` exercise provider adapters with fakes/mocks only. No real Gmail, Calendar, or Stripe network calls, tokens, or secrets are required.

| Area | Deterministic coverage (representative) | Test module |
|---|---|---|
| Google OAuth PKCE connect URL (read-only scopes) | Authorization URL, state persistence, connecting status | `backend/tests/test_provider_lifecycle_unit.py` |
| Token refresh / re-auth | Refresh preserves refresh_token; missing/revoked refresh fails; OAuth-not-configured failure | same |
| Gmail sync | Success after 401→refresh; persistent 401 after refresh; not_connected | same |
| Google Calendar sync | Duplicate tenant-scoped upsert; 401→refresh; unmatched attendees skipped | same |
| Sync orchestration | Rate-limit retry; token failure → `expired`; revoked/disconnected rejected | same |
| Stripe PaymentIntent | Test-mode only; live-key reject; tenant-scoped invoice filter; idempotency key; sanitized failure | same |
| Stripe webhook | Missing secret → 503; missing/invalid signature; idempotent claim; retry after failure; paid monotonicity; amount/currency match | same |
| Redaction | Public connection payloads exclude credential material | same |
| Stripe tenant isolation | Cross-tenant sync/webhook isolation (Mongo-backed CI) | `backend/tests/test_stripe_tenant_isolation.py` |
| Normalizers | Pure Gmail/Calendar/Stripe payload shaping | `backend/tests/test_unit_integrations.py` |

CI-safe command (no provider secrets):

```bash
cd backend && python -m pytest tests/test_provider_lifecycle_unit.py tests/test_unit_integrations.py -q -n 0
```

Full backend suite (CI workflow) still requires ephemeral MongoDB and generated non-provider secrets (`JWT_SECRET`, `INTEGRATION_ENC_KEY`, etc.) as in `.github/workflows/ci.yml`. It must **not** set real `GOOGLE_*` or `STRIPE_*` values.

## What CI does **not** prove

- Live Gmail connect → consent → sync → refresh → disconnect → reconnect
- Live Google Calendar event sync against a real calendar
- Live Stripe test-mode PaymentIntent, signed webhook delivery, or Dashboard-registered endpoint behavior

Those remain Owner-gated. See also `docs/GOOGLE_PROVIDER_CERTIFICATION.md` and `docs/STRIPE_PROVIDER_CERTIFICATION.md`.

## Owner-required secrets (names only — never commit values)

Store values only in the production secret manager (Railway Variables or equivalent). Do **not** paste values into GitHub issues, PRs, chat, evidence JSON, or git history.

| Secret / config name | Provider | Purpose | Expected form (description only) |
|---|---|---|---|
| `GOOGLE_CLIENT_ID` | Google | OAuth web client id | Google Cloud OAuth client id |
| `GOOGLE_CLIENT_SECRET` | Google | OAuth web client secret | Google Cloud OAuth client secret |
| `GOOGLE_REDIRECT_URI` | Google | OAuth callback | `https://<public-api-host>/api/integrations/google/callback` |
| `INTEGRATION_ENC_KEY` | Platform | Encrypt tokens at rest | Fernet key (already required for production boot) |
| Least-privilege Google test account | Google | Consent + sync subject | Owner-approved test user (not a repo secret) |
| `STRIPE_API_KEY` | Stripe | Test-mode API access | Prefer restricted `rk_test_…` (never `sk_live_` / `rk_live_` for certification) |
| `STRIPE_WEBHOOK_SECRET` | Stripe | Webhook signature verify | Endpoint signing secret `whsec_…` |
| Stripe test webhook endpoint | Stripe | Dashboard registration | `https://<public-api-host>/api/integrations/stripe/webhook` for `payment_intent.succeeded`, `payment_intent.payment_failed`, `payment_intent.canceled` |

Related production boot secrets (`MONGO_URL`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `WEBHOOK_CRON_SECRET`) are documented in `docs/RAILWAY_RUNBOOK.md` and are **not** provider certification secrets.

## Owner procedure after secrets are provisioned

1. Confirm production `GET /api/health` returns `status=ok` and `database=up`.
2. Set the Google and Stripe names above in the secret manager; redeploy.
3. As an admin, connect Google from Integrations; complete consent with the approved test account.
4. Run Gmail sync and Calendar sync; confirm tenant-scoped matched records only.
5. Force refresh/re-auth and disconnect/reconnect; confirm encrypted credential storage and redacted registry responses.
6. Connect Stripe in test mode; create a test PaymentIntent against a tenant-owned invoice; deliver signed webhooks (including a duplicate) from Stripe.
7. Record **sanitized** evidence only (HTTP status, pass/fail matrices, redacted ids). No tokens, secrets, raw OAuth payloads, or customer PII in the repository.

Until steps 2–6 succeed with real credentials, Issue #10 acceptance criteria for live Gmail, Calendar, and Stripe certification stay **BLOCKED**.

## Safety rules

- Never commit `.env`, tokens, authorization codes, webhook secrets, or API keys.
- Prefer restricted Stripe **test** keys; reject live-mode keys in the certification PaymentIntent path (enforced in code + tests).
- Preserve tenant scoping and server-side admin auth on connect/sync/payment endpoints.
- Mocks may use obvious placeholders (`whsec_fake`, `sk_test_x`, `client-secret`) inside pytest only; they are not production credentials.
