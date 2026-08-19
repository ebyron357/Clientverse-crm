# ClientVerse CRM — Integrated Validation Evidence

This is the canonical validation record for the ClientVerse CRM release candidate. It consolidates lifecycle, security, accessibility, performance, browser, provider-readiness, and deployment-path evidence. It intentionally excludes passwords, session tokens, OAuth tokens, client secrets, encryption keys, database credentials, portal tokens, authorization codes, connection strings, and internal record identifiers.

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
| CI baseline | **PASS** | [Run 32207426078](https://github.com/ebyron357/Clientverse-crm/actions/runs/32207426078) completed frontend build and backend API tests for `72314053b8634b3f4664e564a901cddc956b9d60`. |
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

## Provider-Readiness Evidence

| Area | Current result | Scope boundary |
|---|---|---|
| Gmail and Calendar code readiness | **READY FOR OWNER CONFIGURATION** | OAuth connect/callback/disconnect/sync and encrypted credential-storage paths are present and focused non-credential tests pass. Live OAuth and provider operations remain unperformed. |
| Stripe code readiness | **READY FOR OWNER CONFIGURATION** | Configuration-gated connection/sync handling and truthful local `requires_stripe_configuration` outcome are present. Live Stripe actions remain unperformed. |
| Runtime secrets | **SAFE FIRST-DEPLOY PATH** | Render will generate JWT, scheduler, and encryption secrets. The owner must enter only `MONGO_URL`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` for the core CRM deployment. |

## Remaining Production Evidence Required

The following evidence is still required before a **GO** verdict can be issued: the completed Atlas cluster and least-privilege network/user configuration; the actual Render Docker build log and service URL; production health; administrator authentication; controlled durable-record persistence; cross-tenant denial; empty operational tenant confirmation; browser smoke against the deployed URL; and the credential-backed Google and Stripe lifecycle records once approved provider access exists.

## References

[1]: https://render.com/docs/blueprint-spec — Render Blueprint YAML reference.
[2]: https://render.com/docs/environment-variables — Render default environment variables.
[3]: https://www.mongodb.com/docs/atlas/tutorial/create-new-cluster/ — MongoDB Atlas cluster-creation guidance.
[4]: https://www.mongodb.com/docs/atlas/security-add-mongodb-users/ — MongoDB Atlas database-user and privilege guidance.
