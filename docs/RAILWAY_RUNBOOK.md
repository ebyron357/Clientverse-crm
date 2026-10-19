# ClientVerse CRM — Railway Production Runbook

> **Owner/admin instructions — see the [ClientVerse CRM Owner/Admin Manual](CLIENTVERSE_CRM_OWNER_ADMIN_MANUAL.md)** (2026-09-30), the official owner/admin source of truth. The owner-facing scheduler checks in §6 (manual §11) and the admin-password text in §7 are superseded by the manual. Deployment mechanics, and the scheduler mechanics in §6, remain current for engineering.

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
- `IN_PROCESS_SCHEDULER` — leave unset. The scheduled jobs run inside the API by
  default; `0` turns that off (§6). `IN_PROCESS_SCHEDULER_JOBS` optionally limits it to a
  comma-separated list of job paths.

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

## 6. Scheduled jobs (built in — no external scheduler required)

*Changed 2026-10-17.* The API runs every scheduled job itself (`backend/scheduler.py`,
started with the application). Each job runs **once per window across all replicas**: a
MongoDB lease per job (`scheduler_leases`) admits one instance per window, a crashed
instance's lease expires and another takes the window over, and a finished window is
not run again after a restart. Every run is recorded in the same ledger the endpoints
use, as `origin: in_process`. Nothing needs configuring.

Until this, the jobs ran only when something called the endpoints, and nothing ever
did: commitments never auto-flagged, integrations never auto-synced, digests never
sent, the durable work queue had no worker and no recovery sweep ever ran.

| Job | Path | Cadence |
|---|---|---|
| Commitment risk | `POST /api/cron/commitment-risk` | every 15 minutes |
| Work-queue worker | `POST /api/cron/work-queue` | every 5 minutes — recovers leases abandoned by crashed workers, then claims and processes due durable jobs |
| Recovery runner | `POST /api/cron/recovery-runner` | every 5 minutes — queues every approved Recovery Case for execution |
| Integration sync | `POST /api/cron/integration-sync` | every 30 minutes (:00, :30) |
| Next best actions | `POST /api/cron/next-best-actions` | every 30 minutes (:00, :30) — recomputes the ranked recommendation queue |
| Inbound email | `POST /api/cron/inbound-email` | every 30 minutes (:10, :40) — pulls replies back into the CRM |
| Reconcile unknown dispatches | `POST /api/cron/reconcile-unknown` | every 30 minutes (:10, :40) — resolves messages whose dispatch outcome was never observed |
| Daily digest | `POST /api/cron/daily-digest` | hourly at :05 (the job itself checks each tenant's configured local digest hour) |
| Second Chance detection | `POST /api/cron/second-chance` | hourly at :05 — detects stalled leads and missed follow-ups, then queues a recommendation refresh per tenant |
| Recovery detection | `POST /api/cron/detect-recovery` | hourly at :05 — every remaining detector family |
| Recovery strategy composition | `POST /api/cron/recovery-strategies` | hourly at :05 — composes a recovery strategy for every open Second Chance candidate and raises its approval request. Composition only: no outbound step can execute while its channel is unauthorised |
| Approval expiry | `POST /api/cron/approval-expiry` | hourly at :05 — lapses approval requests nobody decided, so a stale request can never authorise an action |
| Lead SLA | `POST /api/cron/lead-sla` | every minute, by the lead watcher (`LEAD_SLA_WATCHER`), not by this scheduler |

The cadences are the ones `.github/workflows/scheduled-jobs.yml` uses;
`scripts/validate_config.py` fails the build if the two drift apart.

**Is it running?** `GET /api/cron/health` (admin session or the cron secret):
`scheduled_jobs_running: true` and a recent `in_process.last_run_at`. `GET
/api/cron/runs` lists each run, with `origin: in_process` and a run id of the form
`inprocess-<job>-<window>`. `receiving_scheduled_traffic` deliberately counts external
requests only, so it stays `false` when nothing outside calls the endpoints.

**Turning it off.** Set `IN_PROCESS_SCHEDULER=0` on the service and redeploy — for
example, if a dedicated external scheduler should be the only driver. To run only some
jobs in-process, set `IN_PROCESS_SCHEDULER_JOBS` to a comma-separated list of paths
(e.g. `work-queue,recovery-runner`).

### External scheduler (optional, redundant)

The endpoints remain, authenticated and safe to call concurrently or repeatedly
(idempotent per `X-Webhook-Id`); they are also the way to run a job *now*. The
repository's driver, `.github/workflows/scheduled-jobs.yml`, calls them on the cadences
above once two repository secrets are set: `CLIENTVERSE_PRODUCTION_URL` and
`WEBHOOK_CRON_SECRET`. Until both exist the workflow fails loudly rather than reporting
success without calling anything — so if you rely on the built-in scheduler alone,
disable that workflow (Actions → Scheduled jobs → Disable workflow) instead of leaving
it failing every tick.

Running it alongside the built-in scheduler is safe and mostly redundant. If an
external request has already run a job in the current window, the in-process run
defers to it. An external request that arrives *after* the in-process run in the same
window runs the job again — every job is an idempotent sweep that only acts on records
still in the state it looks for, so the second run finds nothing left to do. To have
the external scheduler be the only driver, set `IN_PROCESS_SCHEDULER=0`.

To wire a different external scheduler (Railway Cron, n8n, or any HTTP-capable
scheduler), call the paths above on the **production** domain.

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
  every boot (see `backend/server.py`). Settings → Change password works for the owner
  account only until the next restart or deploy, so the Railway variable is the only durable
  way to rotate the owner password: change `ADMIN_PASSWORD` in Railway and let it redeploy
  (Owner/Admin Manual §9.2). Other accounts change their own password in Settings, and an
  admin can reset a member's (Team & Access). Never change
  `ADMIN_EMAIL` — a new value seeds a new, empty tenant.
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
