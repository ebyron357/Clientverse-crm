# ClientVerse CRM — Agent Memory

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

Configuration (endpoint is configuration, **not** a secret):

| Variable | Default | Purpose |
| --- | --- | --- |
| `JEV_QC_WEBHOOK_URL` | `https://bwa357.app.n8n.cloud/webhook/jev-qc-central-gate` | Gate endpoint |
| `JEV_QC_TIMEOUT_MS` | `120000` | Request timeout |
| `JEV_QC_EVIDENCE_PATH` | unset | Writes the full request/verdict record to this path |

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
