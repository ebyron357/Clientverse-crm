# ClientVerse CRM — Integrated Validation Evidence

This is the canonical validation record for the ClientVerse CRM release candidate. It consolidates lifecycle, security, accessibility, performance, browser, provider-readiness, and deployment-path evidence. It intentionally excludes passwords, session tokens, OAuth tokens, client secrets, encryption keys, database credentials, portal tokens, authorization codes, connection strings, and internal record identifiers.

## 2026-08-28 Post-Merge Closeout Addendum

**Current closeout candidate:** `538d2eb14d4956cc0a10e56975eeb392dfe3888e` on `manus/final-provider-closeout`
**Baseline on `main`:** `1bd32b3eb7e136f7c98e94611a7b3136bd03a643`
**CI:** [run 33231588528](https://github.com/ebyron357/Clientverse-crm/actions/runs/33231588528) — **PASS** for the candidate SHA.

> **Current verdict: NOT CLOSED.** This addendum supersedes any older implication that the next action is merely a merge approval. PR #9 is already merged, while Issue #10 remains open. The current candidate has passing code, build, lint, and CI evidence, but production deployment and credential-backed provider lifecycle evidence remain unavailable.

| Current closeout gate | Result | Current evidence or exact blocker |
|---|---|---|
| Provider lifecycle hardening | **PASS** | Google reconnect/401 recovery, re-auth failure classification, response redaction, Stripe test PaymentIntent, signed webhook, retryable event leases, identity checks, and monotonic paid-state protection are implemented and covered by 19 deterministic tests. |
| Provider-specific tests | **PASS** | `backend/tests/test_provider_lifecycle_unit.py`: **19 passed**, 1 upstream multipart warning. |
| Full backend CI | **PASS** | CI run 33231588528 passed; the final local suite reports **124 passed, 4 skipped, 2 warnings**. The skipped cases do not satisfy live-provider certification. |
| Frontend build and lint | **PASS** | Candidate CI frontend job passed; local `yarn lint` completed with zero warnings. |
| Accessibility P1 | **PASS — carried forward** | No frontend source changed in the candidate. Prior authenticated axe assessment remains the latest route-level evidence; current static lint passed. |
| Performance P1 | **PASS — carried forward** | No frontend source changed. Prior isolated Locust evidence remains applicable; current production bundle is 331.89 kB gzipped JavaScript and 14.84 kB gzipped CSS. |
| Gmail credential-backed certification | **BLOCKED** | No authenticated Google Cloud configuration, deployed callback origin, or approved test-account OAuth consent was available. |
| Google Calendar credential-backed certification | **BLOCKED** | Same missing Google OAuth and verified public-runtime prerequisites. |
| Stripe test-mode certification | **BLOCKED** | No authenticated Stripe sandbox, configured test key, webhook signing secret, or real test-event delivery was available. |
| Production deployment and smoke | **BLOCKED** | GitHub has no deployment records or production environment for this repository; authenticated Render access was unavailable. No production URL, deployed SHA, or production health response exists. |
| Issue #10 closure | **BLOCKED** | Issue #10 remains open until all credential-backed provider and production acceptance gates pass. |

## Validation Environment and Scope

Autonomous gates ran against a disposable FastAPI application and local MongoDB database built from the current release-candidate source. The temporary frontend build targeted that API. No sandbox, prototype preview, Atlas project, or Render Blueprint configuration is represented as proof of permanent production deployment.

| Environment | Purpose | Boundary |
|---|---|---|
| Isolated FastAPI and MongoDB | Regression, tenant-isolation, provider-ready state, production-startup guard, and performance testing | Disposable verification environment; no production claim. |
| Local production frontend build | Authenticated axe-core and browser validation | Connected only to the isolated API. |
| Render Blueprint configuration | Provider-specific deployment configuration review | No Render service has been created or deployed. |
| Atlas project provisioning | Managed production data-store preparation | No application connection or production data exists yet. |

## Automated Regression and Lifecycle Evidence

| Gate | Exact result | Notes |
|---|---|---|
| Integrated CRM acceptance harness | **PASS — 42 passed, 0 failed** | Controlled lifecycle acceptance remains applicable; no product workflow redesign occurred. |
| Full backend regression suite | **PASS — 104 passed, 5 skipped, 1 warning** | Includes authentication, role permissions, tenant isolation, timeline, notification/digest, commitment/SLA, integrations, client-value, and the closeout isolation probe. |
| Focused integration and role regression | **PASS — 26 passed, 1 skipped, 1 warning in 13.61s** | Run after the Render URL fallback and deployment configuration work. The skip is provider-dependent and is not used as live-provider evidence. |
| CI baseline | **PASS** | [Run 32207878461](https://github.com/ebyron357/Clientverse-crm/actions/runs/32207878461) completed frontend build and backend API tests for `2d68b3c5498115e9aae910bf257671bf391a1814`. |
| ESLint release gate | **PASS — exit 0, 0 errors, 0 warnings** | `eslint "src/**/*.{js,jsx}" --max-warnings=0`. |
| Frontend production build | **PASS** | Warnings-as-errors production build passed. |
| FastAPI lifespan migration | **PASS** | Deprecated event decorators are absent; lifespan startup completed in the isolated API. |
| Production guard and Render URL fallback | **PASS** | `APP_ENV=production`, `SEED_DEMO_DATA=false`, `RENDER_EXTERNAL_URL`, valid secret guards, and Render-style standard-base64 256-bit Fernet material yielded successful startup and a healthy `/api/health` response. |

The provider-dependent skips are not treated as substitutes for credential-backed Gmail, Google Calendar, or Stripe certification. The multipart import pending-deprecation warning is recorded as an upstream dependency warning, not an application lifecycle failure.

## Accessibility Evidence

An authenticated axe-core assessment using WCAG 2.2 AA rules exercised `/dashboard`, `/directory`, `/workspaces`, `/settings`, `/registries`, `/client-ops`, `/field`, and `/notifications`.

| Measurement | Result |
|---|---|
| Routes assessed | 8 protected CRM routes |
| Final violations | **0** |
| Final serious or critical violations | **0** |
| Corrective work | Shared contrast tokens, navigation contrast, named Select and Switch controls, decorative-status semantics, and invalid missing tab-panel references were corrected. |
| Raw evidence | `docs/evidence/a11y-axe-release-pass.json` |

This automated assessment does not replace an owner-led assistive-technology or device-lab study, but it closes the verified critical and serious automated violations for the covered release surfaces.

## Performance Evidence

Locust exercised authenticated login, dashboard, companies, contacts, workspace list/detail, portal-link administration, Client Operations summary, appointments, and Field Ops check-ins. The run used 10 concurrent users, a two-user-per-second ramp, and a 60-second duration against the isolated API.

| Metric | Result |
|---|---|
| Total requests | 3,196 |
| Failed requests | **0** |
| Aggregate throughput | 54.11 requests/s |
| Aggregate p95 response time | 24 ms |
| Aggregate p99 response time | 42 ms |
| Slowest measured route | Login averaged 622.68 ms; all ten login requests succeeded. |
| Read-path result | Dashboard, client lists, workspace detail, portal-link administration, appointments, and field read paths completed without failures. |

The complete statistics are stored in `docs/evidence/performance-locust_stats.csv` and `docs/evidence/performance-locust_failures.csv`. This is an isolated release-readiness assessment, not a claim of tenant-volume or permanent-host capacity certification.

## Browser and Authorization Evidence

The browser smoke harness authenticated against the isolated API before the application loaded, then rendered five desktop routes and the mobile Field Ops route. It also pressed Tab through the initial keyboard sequence and collected uncaught console errors.

| Surface | Exact result |
|---|---|
| Desktop routes | **PASS** — `/dashboard`, `/settings`, `/client-ops`, `/field`, and `/notifications` each displayed a visible main region. |
| Keyboard navigation | **PASS** — focus reached the named command-center button, then `Command Center`, `Action Center`, `Pipeline`, and `Directory` navigation links. |
| Mobile | **PASS** — `/field` rendered at 375×812. |
| Console | **PASS** — 0 uncaught console errors. |
| Tenant isolation | **PASS** — a dedicated probe rejected cross-tenant reads and mutations across the listed client-value and integration-activity resources. |
| Unauthenticated access | **PASS** — protected integration and client-value tests reject unauthenticated requests. |
| Credential redaction | **PASS — code/test scope** — portal-token redaction and integration safe-response behavior were verified. |

## Production Deployment-Path Evidence

The repository now contains a root `Dockerfile`, `render.yaml`, and `docs/RENDER_ATLAS_RUNBOOK.md`. The Blueprint defines a Docker web service in Render Virginia, health check `/api/health`, CI-gated deploys, production demo-data suppression, and Render-generated non-provider secrets. Render documents `RENDER_EXTERNAL_URL` for web services; the application uses it as its first-deploy same-origin fallback until a custom domain is intentionally configured.[1] [2]

The local sandbox does not have a Docker engine, so a local `docker build` could not be executed. This is recorded as an environment limitation, not a simulated build pass. The Docker image must therefore be validated by the first actual Render build before permanent production is certified.

Atlas provisioning is owner-console work. The owner created the ClientVerse Production project and approved the M10 AWS N. Virginia cluster. No connection string has been disclosed, stored, or tested; no claim is made that Render currently reaches Atlas. Atlas recommends co-locating an application and cluster where possible, and its UI supports restricted database-user access.[3] [4]

The committed `scripts/proof_of_life.mjs` harness also executed successfully against a disposable isolated runtime. It validated health; administrator login and re-login; HTTP 401 for unauthenticated company access; a controlled company/contact/opportunity/commitment lifecycle; close-won workspace creation; persistence after re-login; and HTTP 404 cross-tenant workspace denial. Its output redacts all credentials, tokens, and internal record identifiers. The same harness is ready for the first Render URL and creates explicitly prefixed `PRODUCTION-SMOKE` records for review and deliberate cleanup.

## Provider-Readiness Evidence

| Area | Current result | Scope boundary |
|---|---|---|
| Gmail and Calendar code readiness | **READY FOR OWNER CONFIGURATION** | OAuth connect/callback/disconnect/sync, refresh/re-auth classification, encrypted credential storage, and tenant-scoped deterministic tests are present. Live OAuth and provider operations remain unperformed. |
| Stripe code readiness | **READY FOR OWNER CONFIGURATION** | Test-mode PaymentIntent creation, signed raw-body webhook verification, atomic duplicate suppression, tenant-scoped invoice updates, and deterministic failure-path tests are present. Live Stripe actions remain unperformed. |
| Runtime secrets | **SAFE FIRST-DEPLOY PATH** | Render will generate JWT, scheduler, and encryption secrets. The owner must enter only `MONGO_URL`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` for the core CRM deployment. |

## Remaining Production Evidence Required

The following evidence is still required before a **GO** verdict can be issued: the completed Atlas cluster and least-privilege network/user configuration; the actual Render Docker build log and service URL; production health; administrator authentication; controlled durable-record persistence; cross-tenant denial; empty operational tenant confirmation; browser smoke against the deployed URL; and the credential-backed Google and Stripe lifecycle records once approved provider access exists.

## References

[1]: https://render.com/docs/blueprint-spec — Render Blueprint YAML reference.
[2]: https://render.com/docs/environment-variables — Render default environment variables.
[3]: https://www.mongodb.com/docs/atlas/tutorial/create-new-cluster/ — MongoDB Atlas cluster-creation guidance.
[4]: https://www.mongodb.com/docs/atlas/security-add-mongodb-users/ — MongoDB Atlas database-user and privilege guidance.
