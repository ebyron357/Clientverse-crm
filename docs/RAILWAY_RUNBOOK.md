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

## 6. Security reminders

- Rotate the legacy preview Stripe webhook secret redacted during the 2026-08-31
  closeout (value persists in pre-redaction git history; see
  `docs/closeout/OPENHANDS_PRODUCTION_CERTIFICATION.md`).
- Never commit variable values; Railway Variables are the only store.
- `docs/PRODUCTION.md` and `render.yaml` describe the alternate Render path; Railway is
  the active deployment path — do not run both against the same Atlas database.
