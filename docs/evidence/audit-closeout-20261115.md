# C-26 / C-30 / C-31 and deployment investigation — 15 November 2026

## Verified source and production state

`git fetch --all --prune` succeeded. Main was
`dd576c372980feb597ff1316130701ec04f9e0d5` (2026-11-14 18:12:29 -05:00),
“Merge pull request #65 from ebyron357/v0/improve-next-actions”.
PR #64 merged 2026-11-10T16:05:46Z as
`916729f9cf1be320d26576f4659ca7c0b7ebe4d3`; `git merge-base --is-ancestor`
confirmed it is in main.

GET `https://crm.clientverse.io/api/health` returned HTTP 200 at
2026-11-15T05:04:14Z:

```json
{"service":"ClientVerse","version":"v1","status":"ok","database":"up","git_sha":"5fb563ed82a00c2958db5b8e29e28d89af4b906d"}
```

That commit is dated 2026-11-04T14:17:32-05:00. Railway independently reports it
as the latest SUCCESS deployment, `f11316d9-ebdc-49e6-adaf-939a33e52d19`, created
2026-11-04T19:17:35.256Z. No newer deployment appears in the service's history.

## Deployment investigation (read-only)

1. Repository: `railway.json` selects the root Dockerfile, with `/api/health`, a
   120-second health timeout and ON_FAILURE restart policy. Docker builds the React
   frontend with Node 22 / frozen Yarn lockfile, then installs Python dependencies in
   Python 3.12 and serves both via uvicorn. No railway.toml, Procfile or Nixpacks file.
2. Railway: project `welcoming-vibrancy`, production environment, service
   `clientverse-crm-production` (`5e2ea598-91f0-4f95-a67b-067585b80aa9`). Live source
   configuration reports `ebyron357/Clientverse-crm`, branch `main`, root `.`,
   `checkSuites: false`. Serialized build configuration says RAILPACK; the repo's
   config selects Dockerfile. This difference alone does not prove a failure.
   The connector does not return an auto-deploy-enabled field. Dashboard access
   showed Login / 404; its toggle could not be verified. Three variable changes were
   already staged (CORS_ORIGINS, FRONTEND_URL, GOOGLE_REDIRECT_URI); none was applied
   or altered during this investigation.
3. GitHub: PR #64's push CI [run 42851123338](https://github.com/ebyron357/Clientverse-crm/actions/runs/42851123338)
   was cancelled. Its branch CI [run 42836385717](https://github.com/ebyron357/Clientverse-crm/actions/runs/42836385717)
   passed. Later PR CI failures exist, including backend tests in
   [43380061006](https://github.com/ebyron357/Clientverse-crm/actions/runs/43380061006)
   on 13 November; current main's CI
   [43652068571](https://github.com/ebyron357/Clientverse-crm/actions/runs/43652068571)
   passed. Scheduled jobs continue to fail. These results do not explain the absent
   Railway deployment attempt, particularly with checkSuites false.
4. Local main Docker build attempted before edits. Yarn failed downloading
   `lucide-react-0.516.0.tgz` from registry.npmjs.org with `ESOCKETTIMEDOUT`.
   This is local download evidence, not a demonstrated application build defect.

**Root cause: not determined.** Owner inspection needed: Railway → welcoming-vibrancy
→ production → clientverse-crm-production → Settings → Source: verify the GitHub
connection, main branch and automatic deploy setting. In the same service's Deployments
tab, inspect any skipped/queued/approval entry around 10 November 16:05Z. If automatic
deploy is enabled with no event, Railway support/GitHub integration event evidence is
needed to explain why no deployment was created. Do not apply staged changes as part
of this diagnosis. No deployment, redeploy, variable edit, secret rotation or merge
was performed.

## Audit findings (quoted before implementation)

From `docs/evidence/ai-quality-audit-20261104.md`:

- C-26: “Status fields accept any string; non-unique memberships index; concurrent
  same-email registration leaves an empty org; long search input can 500”.
- C-30: “Runtime frontend packages with advisories (axios, react-router, zod)”.
- C-31: “SSRF residual: the HTTP library resolves again after the check”.

Implementation: separate allowed status sets for each workspace record/decision;
unique tenant/user membership index without deleting existing records; remove only
the losing registration's newly allocated organization on a duplicate-email race;
truncate search literals before regex escaping. Pin axios 1.20.0, react-router and
react-router-dom 7.18.2, and zod 4.6.6, including the lockfile. The registry's advisories
identify those patched version ranges. Webhook requests connect to a checked numeric
address while preserving TLS hostname/certificate checks, Host and signed payload;
no environment proxies, redirects or implicit retries. Every outer retry resolves and
validates anew; response bodies are not buffered.

The unique index intentionally refuses startup if legacy duplicate memberships exist;
it does not choose permissions or discard records. Review and reconcile such data
before a later deployment. This PR does not change production data.

## Validation

- PR [#67](https://github.com/ebyron357/Clientverse-crm/pull/67), one branch against main; not merged.
- CI [43681981818](https://github.com/ebyron357/Clientverse-crm/actions/runs/43681981818)
  passed on implementation commit `0325b229af9ca5babac4eb6c4afd463168eff152`:
  backend full suite **1,267 passed, 4 skipped** against MongoDB 7 replica set;
  release smoke, frontend build/tests, lint, blocking types, dependency scan and config checks passed.
- Local production frontend build passed (`CI=true`, production mode, no source maps,
  same-origin API). **116 frontend tests passed**. Frontend and backend lint passed.
- Local focused audit suite **23 passed** against real MongoDB, including the additional
  real-socket transport test. It proves an unresolvable URL hostname is delivered through
  the checked IP with its original Host and signed bytes, while redirects and environment
  proxies are ignored.
- Local full backend suite was started against real MongoDB; stopped after the full CI
  suite passed to release scarce host memory. It is not reported as a completed local pass.
- Type gate: zero findings in the 16 blocking modules; 138 existing findings in the
  nonblocking modules. Configuration validation passed.
- Fresh Yarn registry audit: zero findings for axios, react-router and zod. The overall
  tree still reports 207 findings (12 low, 51 moderate, 141 high, 3 critical), outside
  this bounded package fix; no claim that the entire dependency tree is clean.
- Jev: `node scripts/jev_qc.mjs local-qc-payload.json` returned
  **QC GATE ERROR — FAIL CLOSED**, `JEV_QC_WEBHOOK_URL is not set`, no execution id.
  No Jev VERIFIED_COMPLETE claim. This task is not covered by the separate PR #65 waiver.

The additional transport regression and this evidence update are submitted as new
commits on the same branch; no history rewrite. See the PR checks for the final head's result.
