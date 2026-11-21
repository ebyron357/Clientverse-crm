# PR #64 deployment investigation and C-26/C-30/C-31 fixes

Inspected 2026-11-21. Repository: `ebyron357/Clientverse-crm`. Deployment investigation
is read-only; this change is one pull request against `main`, with no merge or deployment.
These IDs refer to the **2026-11-04 audit**, not the similarly numbered capability register.

## Deployment findings

- [PR #64](https://github.com/ebyron357/Clientverse-crm/pull/64) merged to `main` on
  2026-11-10 at 11:05:46 EST (16:05:46 UTC), merge `916729f9cf1be320d26576f4659ca7c0b7ebe4d3`.
- Railway was accessible through its connector. Project `welcoming-vibrancy`, production
  service `clientverse-crm-production`, owns `crm.clientverse.io`.
- The 50 returned deployments cover September through November. **No record for #64 or
  between November 4 and November 20 appears in that response**: no failed build,
  skipped deployment, pending approval or queued deployment for that merge appears.
  This is an observation about the retrieved history, not proof that a deployment
  was never created or that no historical record was omitted or removed.
- The November 4 deployment `f11316d9-ebdc-49e6-adaf-939a33e52d19` used `5fb563e` and is now
  `REMOVED`. The current `SUCCESS` deployment is `07513bb6-160d-43ff-b380-6e6b504f91a5`,
  created November 20 at 01:27:52 EST (06:27:52 UTC), using `dd576c372980feb597ff1316130701ec04f9e0d5`
  (PR #65). Git ancestry confirms **this deployed commit includes PR #64**. The original
  report that production still runs November 4 code is no longer current.
- November 20 build logs show the Dockerfile frontend build completing, image export,
  and a successful `/api/health` check at 06:29:42 UTC. Runtime logs contain successful
  HTTP requests. No deployment was initiated during this investigation.
- Current Railway source: `ebyron357/Clientverse-crm`, branch `main`, root `.`,
  `checkSuites: false` (not waiting for CI). No watch-path restriction is present in the
  returned configuration. `railway.json` selects the Dockerfile and `/api/health`.
  Three older staged URL-variable changes exist; they were not applied.
- GitHub `main` is unprotected, with no required status checks. The merge's
  [push CI run](https://github.com/ebyron357/Clientverse-crm/actions/runs/42851123338)
  was **cancelled**, not a failed build: frontend build and backend tests never ran.
  The PR head `c511eda` passed both
  [PR CI](https://github.com/ebyron357/Clientverse-crm/actions/runs/42851201284) and
  [push CI](https://github.com/ebyron357/Clientverse-crm/actions/runs/42836385717).

**Conclusion: root cause undetermined.** The available records neither establish the
failure stage nor identify why #64 did not deploy at the time. A Railway compilation
failure is not demonstrated; it cannot be ruled out solely by the absent record.
The connector does not expose historical trigger/audit or webhook-delivery records,
the dashboard session is signed out, no Railway CLI/API token is available, and GitHub's
repository-webhook API returns 403. That repository-hook endpoint also does not establish
access to Railway's GitHub App delivery records. The cancelled merge CI is a separate
observed issue; current `checkSuites: false` does not establish that CI cancellation
prevented the November 10 deployment. No trigger setting was changed.

Evidence needed to determine the cause:

- Railway workspace audit events that establish the source branch, autodeploy state,
  watch paths, CI gating and integration changes in effect at the November 10 merge,
  plus any deployment create/skip/delete events for this service.
- Railway's receipt and processing trace for the GitHub push of
  `916729f9cf1be320d26576f4659ca7c0b7ebe4d3` at `2026-11-10T16:05:46Z`, including any
  rejection/skip reason or deployment ID. A deployment ID would allow its build logs
  to be checked directly. A missing record by itself is not a root-cause finding.
- Correlation of those events with GitHub's merge and CI records. If the necessary
  records were not retained, the historical cause may remain unknowable.

Railway's [audit-log documentation](https://docs.railway.com/enterprise/audit-logs)
provides workspace-admin access and the `auditLogs` GraphQL query. Documented retention
is 48 hours on Free/Trial/Hobby, 30 days on Pro, and 18 months on Enterprise; this
workspace's plan was not established. Its
[autodeploy troubleshooting guide](https://docs.railway.com/deployments/github-autodeploys)
requests project/service/environment, repository, branch, commit SHA and UTC timestamp
when escalating unexplained missing deployments to support. These are avenues for
obtaining evidence, not evidence of a cause. No support message was sent.

## Fixes and validation scope

- **C-26:** validate workspace task, deliverable, client-request, approval decision,
  commitment and outcome states independently. Preserve supported states. Enforce one
  membership per tenant/user with a named unique index that coexists with the legacy
  non-unique index. Reserve the unique email before creating a sign-up organization;
  compensate for subsequent creation errors using only that request's generated IDs.
  Truncate search text before escaping it, so the regex cannot end in half an escape.
- **C-30:** axios 1.21.1, react-router-dom/react-router 7.18.6 and follow-redirects 1.16.3.
  Zod and `@hookform/resolvers` have no imports in the application and are removed.
  `yarn audit --groups dependencies --json` reports no advisory for these packages
  or any remaining direct dependency. The overall scan still reports 198 transitive
  advisories (9 low, 51 moderate, 135 high, 3 critical), principally in the existing
  build toolchain; this is not a claim that the whole dependency tree is clean.
- **C-31:** a direct urllib3 pool connects to a checked IP. TLS certificate verification,
  SNI and the Host header use the original hostname. Every resolved address must pass;
  redirects, environment proxies and hidden HTTP retries are disabled. Responses are
  closed without reading their untrusted bodies. Retry accounting and coarse error
  labels stay in the delivery ledger. Connection failures before sending may try the
  next checked IP; read, TLS and protocol failures do not silently repeat the POST.
  The development-only private-target switch
  remains unavailable in production.
- Regression coverage includes forced concurrent same-email registration, error cleanup,
  unique-index upgrade on real MongoDB 7, valid/invalid resource states, long literal
  searches, mixed private/public DNS answers, IPv4/IPv6 pinning, a DNS answer that changes
  after validation, real TLS SNI/Host/body handling, redirects, and rejection of a
  certificate for the wrong hostname.

Local validation: frontend lint, 113 frontend tests and the production build passed;
backend lint, the 16 blocking type-check modules, configuration validation and pip-audit
passed. The local release smoke passed 82/82 assertions. The full local suite could not
complete: the disposable MongoDB container hit its host-enforced file-descriptor limit
and exited with WiredTiger `Too many open files`. The focused regression suite uses a
separate real MongoDB 7 instance; GitHub's full replica-set suite is the release check.

An unrelated check on the PR is red: **Vercel — mighty-warriors-project-foundation**,
deployment `dpl_4ff1wyUwwHhhwcqPyns7DLgRexmr`. The deployment metadata and build logs show
that project linked to this repository with framework `nextjs` and entrypoint `.`;
it fails `NEXT_NO_VERSION` because this repository is a React/CRACO frontend under
`frontend/`, not a Next.js application. **Vercel — clientverse-crm** passed. No Vercel
project settings were changed and no deployment command was invoked. These previews
were started by the pre-existing Git integration on branch push/PR creation.

Release caveat: existing duplicate membership pairs must be reconciled before rollout;
startup deliberately fails instead of selecting a role or deleting data. The owner
procedure is in the Owner/Admin Manual §2.2. This PR does not inspect or mutate production
memberships. Jev is not verified: the session has no `JEV_QC_WEBHOOK_URL` or token; the
PR #65 waiver is explicitly scoped to that earlier task and is not reused here.
