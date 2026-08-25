# ClientVerse production setup

This document separates configuration by audience and risk. Never commit real secret values.

## Variable catalog

| Variable | Required? | Side | Purpose | Where to configure | Secret? |
|---|---|---|---|---|---|
| `MONGO_URL` | Required (core) | Backend | MongoDB connection string | Hosting provider env / secret store | Yes |
| `DB_NAME` | Required (core) | Backend | Database name | Hosting provider env | No (but environment-specific) |
| `JWT_SECRET` | Required (core) | Backend | Signs access tokens; must be ≥32 chars and non-placeholder | Operator-generated (`openssl rand -hex 32`) | Yes — generate |
| `FRONTEND_URL` | Required (core) | Backend | Primary public frontend origin (cookies / redirects) | Hosting provider env | No |
| `CORS_ORIGINS` | Required (core) | Backend | Comma-separated browser allowlist; defaults to `FRONTEND_URL` | Hosting provider env | No |
| `PUBLIC_BACKEND_URL` | Required (core) when using Google OAuth without explicit redirect | Backend | Public API base URL | Hosting provider env | No |
| `ADMIN_EMAIL` | Required (core) | Backend | Seeded admin identity on first boot | Operator-chosen | Semi — treat as confidential |
| `ADMIN_PASSWORD` | Required (core) | Backend | Seeded admin password (rotated on boot if changed) | Operator-generated | Yes — generate |
| `WEBHOOK_CRON_SECRET` | Required (core) for scheduled jobs | Backend | Bearer token for `/api/cron/*` | Operator-generated | Yes — generate |
| `INTEGRATION_ENC_KEY` | Optional (integrations) | Backend | Fernet key for OAuth/token encryption at rest | Operator-generated | Yes — generate |
| `GOOGLE_CLIENT_ID` | Optional (integrations) | Backend | Google OAuth web client ID | Google Cloud Console | Semi |
| `GOOGLE_CLIENT_SECRET` | Optional (integrations) | Backend | Google OAuth web client secret | Google Cloud Console | Yes — obtain |
| `GOOGLE_REDIRECT_URI` | Optional (integrations) | Backend | Must equal `<PUBLIC_BACKEND_URL>/api/integrations/google/callback` | Google Cloud Console + env | No |
| `STRIPE_API_KEY` | Optional (integrations) | Backend | Stripe test-mode account reads and PaymentIntent creation; prefer least-privilege `rk_test_...` | Stripe Dashboard / secret manager | Yes — obtain |
| `STRIPE_WEBHOOK_SECRET` | Optional (integrations) | Backend | Verifies the raw request body for `POST /api/integrations/stripe/webhook` | Stripe Workbench webhook endpoint / secret manager | Yes — obtain |
| `EMERGENT_LLM_KEY` | Optional (AI) | Backend | Evidence-backed AI | Emergent profile | Yes — obtain |
| `EMERGENT_EMAIL_KEY` | Optional (email) | Backend | Digest/email delivery | Emergent integrations | Yes — obtain |
| `EMAIL_FROM_NAME` | Optional (email) | Backend | From display name | Hosting provider env | No |
| `DEMO_MEMBER_EMAIL` | Testing only | Backend | Seeded member identity — **omit in production** | Local `.env` only | Testing |
| `DEMO_MEMBER_PASSWORD` | Testing only | Backend | Seeded member password — **omit in production** | Local `.env` only | Testing |
| `ALLOW_INSECURE_JWT` | Testing only | Backend | Bypass JWT strength check for disposable local envs | Local `.env` only — never production | N/A |
| `REACT_APP_BACKEND_URL` | Required (core) | Frontend (build-time) | Backend base URL baked into the SPA | Frontend host / CI build env | No (public) |

## Hosting notes

- Bind the API with uvicorn/gunicorn to `0.0.0.0:$PORT` on platforms like Render.
- Frontend is a static CRA build (`yarn build` → `frontend/build`).
- Filesystem is ephemeral on most PaaS hosts — use MongoDB/object storage, not local disk.
- Set `CORS_ORIGINS` to the exact browser origin(s) of the deployed frontend.
- Confirm `GET /api/health` returns a payload containing `"status":"ok"` and `"database":"up"` after deploy.
- For Stripe certification, use only an `rk_test_...` or `sk_test_...` key and register `<PUBLIC_BACKEND_URL>/api/integrations/stripe/webhook` for `payment_intent.succeeded`, `payment_intent.payment_failed`, and `payment_intent.canceled`; store the resulting `whsec_...` value as `STRIPE_WEBHOOK_SECRET`.
- Do not ship `ADMIN_PASSWORD` / demo member passwords as long-lived production credentials; rotate after first login.
- Leave `DEMO_MEMBER_EMAIL` / `DEMO_MEMBER_PASSWORD` **unset** in production. The demo member is seeded only when both are provided, so an unconfigured deployment never gets a well-known member login.

## What must never be committed

- `.env` files with real values
- JWT secrets, cron secrets, Fernet keys, OAuth client secrets, Stripe API/webhook keys, email/LLM keys
- `node_modules/`, `frontend/build/`, Python caches, MongoDB dumps

## Going public with this repository

Before flipping visibility to public:

1. Confirm no real `.env`, key file, or database dump is tracked or present in
   git history (`git log --diff-filter=A --name-only`). Only `.env.example`
   files should ever be committed.
2. Rotate every credential that was used in a shared preview/demo environment —
   `JWT_SECRET`, `ADMIN_PASSWORD`, `WEBHOOK_CRON_SECRET`, `INTEGRATION_ENC_KEY`,
   OAuth client secrets, Stripe and Emergent keys.
3. Unset `DEMO_MEMBER_EMAIL` / `DEMO_MEMBER_PASSWORD` and `ALLOW_INSECURE_JWT`
   in every non-local environment.
4. In repository settings, enable branch protection on `main`, private
   vulnerability reporting, secret scanning, and Dependabot alerts.
5. Verify CI is green (`.github/workflows/ci.yml`: frontend build + backend API
   tests) and that `GET /api/health` reports `{"status":"ok","database":"up"}`
   on the deployed environment.
