# ClientVerse CRM — Agent Memory

## Session state (2026-09-21, branch `claude/trusting-brahmagupta-lj26xf`)

- **The scheduler has never made a production request.** Proven three ways: the
  workflow log (`BASE_URL:`/`CRON_SECRET:` empty), 1,622 green no-op runs, and
  Railway's HTTP log containing no `/api/cron/*` request at all. The two GitHub
  secrets are still unset and **cannot be set from an agent session** — the proxy
  refuses the Actions secrets API with 403. Owner action.
- **Production is unreachable from agent sessions.** Egress policy answers 403 to
  CONNECT for `clientverse-crm-production-production.up.railway.app`. Do not spend
  time retrying it; verify through CI and hand production checks to the owner.
  Railway's MCP tools *do* work and are the way to read deployment state and logs.
- Deployed head is `main@730b1b3` (deployment `4b5f7f84-…`, 2026-09-16). This branch
  is not deployed.
- **Run the suite locally with `MONGO_URL=mongomock://local`** where no mongod is
  reachable (`backend/requirements-dev.txt`). 675 of 695 pass; the 16 failures are
  driver fidelity, not defects. CI against mongo:7 is the gate.
- New gates: `ruff check .` (blocking), `scripts/typecheck.py` (ratcheting — a module
  joins the blocking set by being clean), `pip-audit`, `scripts/validate_config.py`,
  and `scripts/crm_release_smoke.mjs` (82 assertions, release gate in CI).
- Handoff and status: `docs/OWNER_HANDOFF.md`, `docs/ACTIVATION_REPORT.md`.


## Closeout state (2026-09-01, production LIVE)

- **Production is live and verified.** Railway deployment `d9af2985-30e4-4fb8-b030-ac8b1446db89` (commit `ca30587` = main) SUCCESS at 2026-09-01T22:44Z; `/api/health` → 200 `{"service":"ClientVerse","version":"v1","status":"ok","database":"up"}`; SPA 200; `scripts/proof_of_life.mjs` exit 0 (all gates incl. cross-tenant 404); smoke records fully cleaned (0 references); evidence `docs/evidence/production-smoke-20260901.json`.
- Task ledger: `todo.md`. Status channel: GitHub Issue #10 (required report format: COMPLETED / BLOCKED / EXACT OWNER INPUT REQUIRED).
- Deployment path: **Railway only** (Render superseded; do not run both against the same Atlas DB). Docs: `docs/RAILWAY_RUNBOOK.md`.
- Railway: project `welcoming-vibrancy` (`bbcb2596-d6f9-45c5-9c03-59cb97f373ea`), env `production` (`12d1d2d7-3fdf-44a9-b6b6-f1d992642188`), service `clientverse-crm-production` (`5e2ea598-91f0-4f95-a67b-067585b80aa9`), domain `clientverse-crm-production-production.up.railway.app`, source repo `ebyron357/Clientverse-crm` (`main`), Dockerfile artifact.
- All production variables verified set (incl. `MONGO_URL` repaired from misspelled `Mongo_url`, valid Fernet `INTEGRATION_ENC_KEY`, `ADMIN_EMAIL`/`ADMIN_PASSWORD` via delegated bootstrap). Atlas network access fixed by owner (`0.0.0.0/0`, 2026-09-01).
- Remaining owner-only: Google OAuth + Stripe test credentials (provider certification), external scheduler for `/api/cron/*`, custom domain/DNS + Google callback registration, `ADMIN_PASSWORD` rotation after first login, legacy Stripe webhook secret rotation, optional deletion of misspelled `Mongo_url`.

## Railway API access (hard-won)

- Use the **`$Railway`** env var (NOT `$RAILWAY_API_TOKEN` — rejected) as a **`Project-Access-Token` header** on `https://backboard.railway.com/graphql/v2`. Bearer/account paths and `projectToken` introspection return "Not Authorized"/"Project Token not found" by design.
- Secret injection caveat: the secret is only exported when the command text literally references its name — e.g. run `RW_TOKEN=$Railway python3 script.py` and read `RW_TOKEN` inside the script.
- urllib clients get HTTP 403 without a browser/curl-like `User-Agent` header; curl works as-is.
- Useful mutations/queries: `projectToken { projectId environmentId }`, `project(id:)`, `variables(projectId:environmentId:serviceId:)`, `variableUpsert(input:)` (auto-triggers a redeploy per change), `deployments(first:input:{projectId,environmentId,serviceId})`, `deploymentLogs(deploymentId:)`, `buildLogs(deploymentId:)`.
- Never print variable VALUES — audit by NAME and length only.

## Repo/environment facts

- Suite: `cd backend && python -m pytest tests/ -q` (149 passed, 4 skipped as of PR #14); frontend `yarn lint --max-warnings=0` and `CI=true yarn build` are the CI gates (`.github/workflows/ci.yml`).
- `seed()` reads `ADMIN_EMAIL`/`ADMIN_PASSWORD` at every boot and re-syncs the admin password hash — rotating = set new value + redeploy.
- Public URL probes return 404 while no healthy deployment exists (expected; not a routing problem).
- Do not commit/push unless the owner explicitly asks; post state to Issue #10 instead.
