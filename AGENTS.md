# ClientVerse CRM — Agent Memory

## Session state (2026-09-30)

- **Owner/admin procedures live in one place:**
  `docs/CLIENTVERSE_CRM_OWNER_ADMIN_MANUAL.md` (Issue #33). It is registered as the owner
  source of truth in the governing document, v1.11 §0.5. Change the manual in the same commit
  as any change to a screen label, route, sign-in rule, Google scope or cron job. Do not write
  new owner instructions anywhere else.
- **GitHub Actions is running again, and the scheduler reaches production.** Scheduled-jobs runs
  #3551–#3555 were green from 16:11Z, with Railway `200` on all twelve `/api/cron/*` endpoints.
  Earlier runs #3544–#3550 failed on `401` (a cron secret mismatch, since fixed). The 2026-09-28
  and 2026-09-21 notes below saying Actions runs nothing and the scheduler never ran are **stale**.
- **The Google grant needs owner re-authorization.** The 16:08Z `integration-sync` got `400` from
  Google's token endpoint.
- **Outbound email has two further blockers**, besides `gmail.send`:
  - The tenant's Gmail `integrations` catalogue record is `REQUIRES_CONFIGURATION`, so
    `authorized_channels` refuses email. Only a database change clears it; that is a
    certification decision.
  - No UI composes, sends, or records consent.

  See governing document M-01 and §8 #27–#28.
- Production is on `main@8f23f63` (application code identical to `c9f5a6e`). The production
  host still refuses CONNECT (403) from agent sessions; Railway MCP tools and GitHub Actions
  records work.

## Session state (2026-09-28)

- **Running application code is `main@c9f5a6e`** (the recovery-engine merge). Railway
  deployment `1f809799-a4a2-4dc9-9e38-8d19ba1b282d` put it live 2026-09-28T05:25Z; PR #30
  (`c931b4e`, docs and agent tooling only — no change under `backend/`, `frontend/`,
  `Dockerfile`, `railway.json`) redeployed the same code as `84c89214-…` at 18:05Z. Every
  `main` commit redeploys, so **read the live deployment id from Railway, not from docs**;
  `/api/health` reports its `git_sha`. Boot log each time: `Registered outbound channel
  provider: gmail` → `Application startup complete` → `/api/health` 200. The 2026-09-21
  notes below that say `730b1b3` is deployed are stale.
- **GitHub Actions has run nothing since 2026-09-27T22:35Z.** Every job on every
  branch (CI and Scheduled jobs) completes as `failure` in 2–4 s with `runner_id: 0`
  and no log, starting mid-schedule on an unchanged commit. That is an account-level
  runner/billing condition, not a code failure — do not "fix" code for it. Until the
  owner restores Actions, CI is not a usable gate: run the gates locally (below).
- **Jev QC gate is live and verified** — `docs/evidence/jev-qc-live-20260928/`
  (`VERIFIED_COMPLETE`, `n8n_execution_id` 146). The gate section at the end of this
  file is mandatory.
- Password change/recovery (Issue #10, 2026-09-27 update, local commit `b8b8b4c`) is
  **not on GitHub and not in `main`**. Do not rebuild it; the owner must push it.

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

## Jev QC verification gate (mandatory before claiming completion)

**Rule: no agent may report a task VERIFIED COMPLETE until the Jev QC gate has returned
`qc_status: VERIFIED_COMPLETE` for that task.** The gate is the production n8n *Jev QC
Central Verification Gate*, which relays to TypeSafe Jev and returns the decision.
Never call TypeSafe directly, never request or store a TypeSafe API key, and never stand
up a second Jev service or modify the production n8n workflow.

```
Claude Code → n8n Jev QC Central Gate → TypeSafe Jev → QC decision → Claude Code
```

### Invocation

```bash
node scripts/jev_qc.mjs <payload.json>     # or: yarn qc <payload.json>
node scripts/jev_qc.mjs -                  # payload on stdin
```

Configuration. **The webhook path is a capability** — anyone who knows it can invoke the
gate — so it is supplied by the session environment (Claude Code environment settings),
never committed, and never written to evidence (records carry `webhook_host` only):

| Variable | Default | Purpose |
| --- | --- | --- |
| `JEV_QC_WEBHOOK_URL` | **none — required** | Gate endpoint. Unset ⇒ fail-closed `QC GATE ERROR` |
| `JEV_QC_WEBHOOK_TOKEN` | unset | Sent as `X-Jev-QC-Token` for n8n Header Auth on the webhook. Never logged |
| `JEV_QC_TIMEOUT_MS` | `120000` | Request timeout |
| `JEV_QC_EVIDENCE_PATH` | unset | Writes the request/verdict record to this path |

The 2026-09-28 security review of PR #30 found the original webhook path published in
this public repository and the webhook accepting unauthenticated requests. Owner
remediation: enable Header Auth (header `X-Jev-QC-Token`) on the n8n webhook node, rotate
the webhook path, and set both variables above in the Claude Code environment.

### Payload

```json
{
  "task_id": "unique task identifier",
  "task": "description of work performed",
  "worker": "Claude Code",
  "worker_claim": "Task complete.",
  "completion_requirements": ["requirement 1", "requirement 2"],
  "evidence": {
    "implementation": "...", "tests": "...", "build": "...",
    "deployment": "...", "verification": "..."
  }
}
```

`worker` and `worker_claim` default as shown. Use concrete evidence only — commit SHA,
changed files, test command + result, build command + result, deployment evidence, URL,
PR number, validation output, logs.

**Evidence rule: never fabricate evidence.** Any evidence field left absent or blank is
submitted verbatim as `"No evidence supplied."` so Jev scores the real gap. Do not invent
artifacts to force a pass.

### Verdicts and exit codes

| `qc_status` | Exit | Agent must report |
| --- | --- | --- |
| `VERIFIED_COMPLETE` | 0 | `QC VERIFIED COMPLETE`, including the Jev result |
| `INCOMPLETE` | 1 | `QC INCOMPLETE` + the unsupported requirements — **not** verified complete |
| `NEEDS_HUMAN_REVIEW` | 2 | `QC NEEDS HUMAN REVIEW` + the reason — **not** verified complete |
| (gate error) | 3 | `QC GATE ERROR — FAIL CLOSED` — **not** verified complete |

**Fail closed.** Exit 3 covers an unreachable gate, timeout, non-2xx response, invalid
JSON, a response carrying no `qc_status`, and any unrecognized status. Only an explicit
`VERIFIED_COMPLETE` permits a completion claim.

The gate's execution identifier is reported as **`n8n_execution_id`** and is passed
through verbatim — do not rename it or assume `execution_id`.

### Network requirement

The gate host `bwa357.app.n8n.cloud` must be reachable from the session's egress policy.
Sandboxed sessions whose network policy does not allow it get a CONNECT 403, which the
script surfaces as a fail-closed `QC GATE ERROR`; allowlist the host (or run from a
session that can reach it) rather than skipping the gate.
