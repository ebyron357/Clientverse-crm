# ClientVerse CRM — Railway Production Runbook

Single-service deployment: one Railway service builds the root `Dockerfile` (React build
stage + FastAPI runtime) and serves the SPA and API from one HTTPS origin. No Railway
database plugin is created or required — production data lives in the existing MongoDB
Atlas cluster.

## 1. Service setup (one-time)

1. Railway project → **New Service → GitHub Repo** → `ebyron357/Clientverse-crm`, branch `main`.
2. Railway auto-detects the root `Dockerfile`; `railway.json` pins the builder and sets
   the health check to `GET /api/health`.
3. **Settings → Networking → Generate Domain** (e.g. `<service>.up.railway.app`).
   Railway injects `RAILWAY_PUBLIC_DOMAIN` and `PORT` at runtime; the application derives
   `FRONTEND_URL`, `CORS_ORIGINS`, `PUBLIC_BACKEND_URL`, and the Google OAuth callback
   from it automatically (verified by `backend/tests/test_railway_config.py`).

## 2. Required variables (names only — set values in Railway → Variables)

| Variable | Required | Value source |
|---|---|---|
| `MONGO_URL` | yes | Existing Atlas SRV connection string (do not create a new database) |
| `DB_NAME` | yes | `clientverse` |
| `JWT_SECRET` | yes | Generate: `openssl rand -hex 32` |
| `INTEGRATION_ENC_KEY` | yes | Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `WEBHOOK_CRON_SECRET` | yes | Generate: `openssl rand -hex 32` |
| `ADMIN_EMAIL` | yes | Owner login email for the seeded administrator |
| `ADMIN_PASSWORD` | yes | Strong unique password for the seeded administrator |
| `APP_ENV` | yes | `production` |
| `SEED_DEMO_DATA` | yes | `false` |

Optional (safe degradation without them — connect endpoints return 400/503 until set):

- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`
- `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET` (test mode only)
- `EMERGENT_LLM_KEY`, `EMERGENT_EMAIL_KEY`
- `FRONTEND_URL`, `CORS_ORIGINS`, `PUBLIC_BACKEND_URL` — only needed to override the
  auto-derived Railway domain (e.g. a custom domain).

Do NOT set `REACT_APP_BACKEND_URL` — the Dockerfile builds the SPA with same-origin
`/api` resolution.

## 3. MongoDB Atlas network access

Railway egress IPs are dynamic on standard plans. In Atlas → **Network Access**, either:

- add `0.0.0.0/0` (Atlas recommendation for dynamic-IP platforms; the SRV credential in
  `MONGO_URL` remains the access control), or
- enable Railway static egress IPs (paid Railway feature) and allowlist those IPs only.

## 4. Boot verification

After variables are set and the deploy is green:

```bash
curl -i https://<service>.up.railway.app/api/health      # expect HTTP 200 {"status":"ok","database":"up"}
curl -I https://<service>.up.railway.app/                # expect HTTP 200 (SPA)
CLIENTVERSE_API_BASE=https://<service>.up.railway.app \
CLIENTVERSE_ADMIN_EMAIL=<ADMIN_EMAIL> \
CLIENTVERSE_ADMIN_PASSWORD=<ADMIN_PASSWORD> \
node scripts/proof_of_life.mjs                           # expect exit 0
```

Startup failure map (all are configuration, not code):

| Log signature | Missing/incorrect variable |
|---|---|
| `KeyError: 'MONGO_URL'` | `MONGO_URL` |
| `KeyError: 'DB_NAME'` | `DB_NAME` |
| `JWT_SECRET must be a strong secret` | `JWT_SECRET` (<32 chars or a known default) |
| `FRONTEND_URL must use HTTPS in production` | domain not generated / `FRONTEND_URL` override not https |
| `Missing required production configuration` | `WEBHOOK_CRON_SECRET` and/or `INTEGRATION_ENC_KEY` |
| `INTEGRATION_ENC_KEY must be a valid Fernet key` | regenerate with the command above |
| `KeyError: 'ADMIN_EMAIL'` at seed | `ADMIN_EMAIL` / `ADMIN_PASSWORD` |

## 5. Provider callbacks (after the domain exists)

- Google OAuth authorized redirect URI:
  `https://<service>.up.railway.app/api/integrations/google/callback`
  (auto-derived; set `GOOGLE_REDIRECT_URI` only when overriding)
- Stripe webhook endpoint (test mode):
  `https://<service>.up.railway.app/api/integrations/stripe/webhook`

**Two-pilot-company deployments**: `STRIPE_API_KEY` is a single, shared Stripe account
for the whole deployment. If two tenants both need Stripe and must not share one
underlying account, each tenant's admin should instead call
`POST /api/integrations/stripe/connect` with `{"api_key": "<their own restricted key>"}`
in the request body — this stores an encrypted, tenant-scoped credential (mirroring how
Google credentials are already isolated per tenant) that takes priority over the shared
`STRIPE_API_KEY` for that tenant's syncs and payment intents. Calling connect with no
body keeps the previous shared-key behavior.

## 6. External scheduler (required — the app never calls these on its own)

The three `/api/cron/*` endpoints exist, are authenticated, and are safe to call
concurrently/repeatedly (idempotent per `X-Webhook-Id`), but **nothing in this codebase
calls them automatically**. Without an external trigger wired to the production URL,
commitments never auto-flag at-risk/breached, integrations never auto-sync, and digests
never send — this is a configuration step, not a code deficiency.

Wire an external scheduler (Railway Cron, n8n, or any HTTP-capable scheduler) to call, on
the **production** domain:

| Job | Path | Cadence |
|---|---|---|
| Commitment risk | `POST /api/cron/commitment-risk` | every 15 minutes |
| Integration sync | `POST /api/cron/integration-sync` | every 30 minutes |
| Daily digest | `POST /api/cron/daily-digest` | hourly (the job itself checks each tenant's configured local digest hour) |

Every call must carry:

```
Authorization: Bearer <WEBHOOK_CRON_SECRET>
```

A missing or wrong secret returns `401`. Optionally send a stable `X-Webhook-Id` header
per scheduled firing so a retried/duplicate delivery is recognized and skipped instead of
re-running the job.

n8n specifically: a Schedule Trigger node on the desired cadence, feeding an HTTP Request
node calling the URL above with the `Authorization` header set directly on the node (not
via n8n's built-in Bearer-Auth credential type, which has a known issue not always
sending the header) — no ClientVerse code changes are needed for this.

## 7. Security reminders

- **Rotate the compromised Stripe webhook secret.** A real `whsec_…` value was committed
  in plaintext in `test_reports/iteration_10.json` (introduced in commit `3682fd3`,
  redacted at the tracked tip in commit `3ec3517`) and remains fully recoverable from the
  repository's full git history by anyone who clones it — redacting the tracked tip does
  **not** remove it from history. This is an **owner-only** action: sign in to the Stripe
  dashboard, roll the webhook endpoint's signing secret, and set the new value as
  `STRIPE_WEBHOOK_SECRET` in Railway. No code change can close this — only rotating the
  live secret does.
- **`ADMIN_PASSWORD` rotation is not durable if done only in the app.** `seed()` re-syncs
  the admin account's password hash from the `ADMIN_PASSWORD` environment variable on
  every boot (see `backend/server.py`). If you only change the password through the
  product UI/API, the next redeploy or restart silently reverts it back to whatever
  `ADMIN_PASSWORD` is still set to in Railway. **Always update the Railway variable in the
  same action** as any admin password rotation (which will trigger a redeploy).
- **Google OAuth setup is owner-only.** Creating/verifying the OAuth consent screen and
  Web OAuth client in Google Cloud Console, registering the callback URL above, and
  setting `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` in Railway all require the owner's
  Google Cloud account access — an agent cannot do this.
- **Stripe test credentials and webhook registration are owner-only.** Obtaining a
  `sk_test_…`/`rk_test_…` key and registering the webhook endpoint above in the Stripe
  dashboard require the owner's Stripe account access.
- **Never commit variable values or real secrets anywhere** — not in `.env` files, test
  fixtures, code comments, commit messages, or chat/issue transcripts. Railway Variables
  (or a tenant's own encrypted credential, for Stripe) are the only store.
- `docs/PRODUCTION.md` and `render.yaml` describe the alternate Render path; Railway is
  the active deployment path — do not run both against the same Atlas database.
