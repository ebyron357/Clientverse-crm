# ClientVerse CRM — Managed FastAPI + MongoDB Deployment Guide

## Purpose

This guide deploys the existing ClientVerse release candidate as one container: the FastAPI application serves `/api`, and the compiled React application is served from the same HTTPS origin. This avoids browser CORS ambiguity, keeps authentication cookies predictable, and preserves the verified tenant-scoped implementation.

## Required Production Components

| Component | Requirement |
|---|---|
| Application host | A managed service that builds and runs the repository `Dockerfile`, terminates HTTPS, injects environment variables securely, and exposes a configurable health check. |
| Database | A managed MongoDB-compatible cluster with restricted network access, automated backups, point-in-time recovery where available, and a separate production database name. |
| Domain | One production HTTPS domain for the container. Point the domain at the application host only after health checks succeed. |
| Secrets | Host-managed environment variables; never `.env` files in Git or browser-accessible frontend variables. |
| Observability | Application logs, host metrics, uptime monitoring for `/api/health`, and a database backup/restore test. |

## Deployment Procedure

1. Create a managed MongoDB production cluster and a least-privilege database user. Restrict inbound network access to the selected application host.
2. Create a managed Python/container web service from this repository using the root `Dockerfile`. Set its health check to `GET /api/health`; a healthy response reports `status: ok` and `database: up` without exposing secrets.
3. Configure the production environment variables listed below through the hosting control plane. Generate strong secrets with an approved secret generator and retain them only in the chosen secret manager.
4. Deploy the container. Verify `/api/health`, sign in, use the Command Center, create/read a controlled record, and verify a second tenant cannot access it.
5. Bind the production domain and set `FRONTEND_URL` and `CORS_ORIGINS` to that exact HTTPS origin. Redeploy if either value changes.
6. Register the final Google callback only after the production origin is stable: `https://<production-domain>/api/integrations/google/callback`.
7. Run the production acceptance checklist before enabling the PR for merge. Do not represent Google, Calendar, or Stripe as connected until their credential-backed lifecycle certifications pass.

## Required Environment Variables

| Variable | Production requirement |
|---|---|
| `MONGO_URL` | Managed production MongoDB connection string, stored as a host secret. |
| `DB_NAME` | Dedicated production database name. |
| `APP_ENV` | Set to `production`; production defaults prevent fictional demo records from being created. |
| `SEED_DEMO_DATA` | Set to `false`; do not enable this in an environment that accepts customer data. |
| `JWT_SECRET` | A strong secret of at least 32 characters. Do not reuse a development value. |
| `FRONTEND_URL` | Exact public HTTPS application origin, for example `https://crm.example.com`. |
| `CORS_ORIGINS` | The same exact public origin for the one-container deployment. |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Initial controlled administrator bootstrap values; rotate after first administrative access. |
| `INTEGRATION_ENC_KEY` | A persistent Fernet-compatible encryption key before any provider credential is stored. |
| `WEBHOOK_CRON_SECRET` | A separate strong secret for authenticated internal scheduler/webhook triggers. |
| `PUBLIC_BACKEND_URL` or `GOOGLE_REDIRECT_URI` | Required before Google OAuth lifecycle certification. Use the final HTTPS callback URL. |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Required only for approved Gmail and Google Calendar certification. |
| `STRIPE_API_KEY` | Required only for approved Stripe test-mode certification. |

## Backup, Recovery, and Rollback

The production database must have automated backups before customer data is accepted. Verify a restore into a separate recovery database, then confirm the restored application can pass `/api/health` and read a controlled tenant record. Retain the last verified container revision and database restore point before each schema or release change. Application rollback must never be used as a substitute for a database restoration plan.

## Production Startup Safeguards

The application refuses to start in `APP_ENV=production` unless `FRONTEND_URL` and every CORS origin use explicit HTTPS, and both `WEBHOOK_CRON_SECRET` and `INTEGRATION_ENC_KEY` are present. These checks prevent a production deployment from silently accepting wildcard browser origins, unauthenticated scheduler calls, or unencrypted provider credentials. The application also returns baseline response headers for content-type handling, referrer handling, framing, browser capability restrictions, and HTTPS transport security.

## Safety Gates

The following remain mandatory: server-side tenant isolation, no production secrets in source control, provider credential redaction, authenticated webhook/scheduler triggers, draft PR review, final CI, deployed smoke tests, and provider certification with approved test credentials. The current release record remains the authoritative status document: [RELEASE_CERTIFICATION.md](./RELEASE_CERTIFICATION.md).
