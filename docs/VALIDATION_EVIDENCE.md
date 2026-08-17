# ClientVerse CRM — Integrated Validation Evidence

This is the canonical validation record for the ClientVerse CRM release candidate. It supersedes fragmented closeout notes by consolidating lifecycle, security, accessibility, performance, browser, provider-readiness, and deployment evidence. It intentionally excludes passwords, session tokens, OAuth tokens, client secrets, encryption keys, database credentials, portal tokens, authorization codes, and internal record identifiers.

## Validation Environment

The autonomous validation gates ran against a disposable FastAPI application and local MongoDB database using the current release-candidate source. The temporary frontend build targeted that API. The sandbox health endpoint was also checked for proof of life, but no temporary runtime is labeled permanent production and no deployment occurred in this closeout cycle.

| Environment | Purpose | Boundary |
|---|---|---|
| Isolated FastAPI and MongoDB | Regression, tenant-isolation, provider-ready state, and performance testing | Disposable verification environment; no production claim. |
| Local production frontend build | Authenticated axe-core and browser validation | Connected only to the isolated API. |
| Temporary sandbox endpoint | Reachability proof | HTTP 200 health confirmation only; not a permanent deployment target. |

## Automated Regression and Lifecycle Evidence

| Gate | Exact result | Notes |
|---|---|---|
| Integrated CRM acceptance harness | **PASS** — `42 passed, 0 failed` | Prior controlled lifecycle acceptance remains applicable; no product workflow redesign occurred. |
| Full backend regression suite | **PASS** — `104 passed, 5 skipped, 1 warning in 34.20s` | Includes authentication, role permissions, tenant isolation, timeline, notification/digest, commitment/SLA, integrations, client-value, and the closeout isolation probe. |
| Explicit client-value tenant isolation | **PASS** — `1 passed in 1.85s` | Tenant B received HTTP 404 for Tenant A resource queries and HTTP 403/404 for mutation attempts across workspace, documents, estimates, invoices, appointments, field check-ins, portal links, and integration activity. |
| ESLint release gate | **PASS** — exit 0, 0 errors, 0 warnings | `eslint "src/**/*.{js,jsx}" --max-warnings=0`. |
| Frontend production build | **PASS** | `NODE_ENV=production craco build`; 331.14 kB JavaScript and 14.81 kB CSS gzip. |
| FastAPI lifespan migration | **PASS** | Deprecated event decorators are absent; lifespan startup completed in the isolated API. |

The five skipped backend tests require unavailable provider or schedule configuration. They were not used as a substitute for external provider certification. The sole remaining warning is a multipart import pending deprecation and is not an application lifecycle warning.

## Accessibility Evidence

An authenticated axe-core assessment using WCAG 2.2 AA rules exercised `/dashboard`, `/directory`, `/workspaces`, `/settings`, `/registries`, `/client-ops`, `/field`, and `/notifications`.

| Measurement | Result |
|---|---|
| Routes assessed | 8 protected CRM routes |
| Final violations | **0** |
| Final serious or critical violations | **0** |
| Corrective work | Shared contrast tokens, navigation contrast, named Select and Switch controls, decorative-status semantics, and invalid missing tab-panel references were corrected. |
| Raw evidence | `docs/evidence/a11y-axe-release-pass.json` |

The automated assessment does not replace an owner-led assistive-technology or device-lab study, but it closes the verified critical and serious automated violations for the covered release surfaces.

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

The complete statistics, including endpoint-level response times and zero recorded failures, are stored in `docs/evidence/performance-locust_stats.csv` and `docs/evidence/performance-locust_failures.csv`. This is an isolated release-readiness assessment, not a claim of tenant-volume or permanent-host capacity certification.

## Browser Evidence

The browser smoke harness authenticated against the isolated API before the application loaded, then rendered five desktop routes and the mobile Field Ops route. It also pressed Tab through the initial keyboard sequence and collected uncaught console errors.

| Surface | Exact result |
|---|---|
| Desktop routes | **PASS** — `/dashboard`, `/settings`, `/client-ops`, `/field`, and `/notifications` each displayed a visible main region. |
| Keyboard navigation | **PASS** — focus reached the named command-center button, then `Command Center`, `Action Center`, `Pipeline`, and `Directory` navigation links. |
| Mobile | **PASS** — `/field` rendered at 375×812. |
| Console | **PASS** — 0 uncaught console errors. |
| Screenshots | `docs/evidence/browser-release-desktop.png` and `docs/evidence/browser-release-mobile-field.png`. |

## Security and Provider-Readiness Evidence

| Area | Current result | Scope boundary |
|---|---|---|
| Protected endpoints | **PASS** | Existing integration and client-value tests reject unauthenticated protected requests. |
| Tenant isolation | **PASS** | The closeout probe explicitly rejected cross-tenant reads and mutations across the listed client-value and integration-activity resources. |
| Credential redaction | **PASS — code/test scope** | Portal token redaction and integration safe-response behavior were verified; no secret-bearing material appears in stored evidence. |
| Gmail and Calendar code readiness | **READY FOR OWNER CONFIGURATION** | OAuth connect/callback/disconnect/sync and encrypted credential-storage paths are present and focused non-credential tests pass. Live OAuth and provider operations remain unperformed. |
| Stripe code readiness | **READY FOR OWNER CONFIGURATION** | Configuration-gated connection/sync handling and truthful local `requires_stripe_configuration` outcome are present. Live Stripe actions remain unperformed. |

## Runtime and Deployment Evidence

Only environment-variable presence was inspected. In the temporary runtime, core database, JWT, frontend, and CORS variables were present; `PUBLIC_BACKEND_URL`, `INTEGRATION_ENC_KEY`, Google OAuth variables, `STRIPE_API_KEY`, and `WEBHOOK_CRON_SECRET` were absent. The external sandbox health endpoint returned HTTP 200 during this cycle, but no permanent hosting target or deployment manifest was found. That endpoint must not be cited as final production certification.

## Owner Acceptance and Release State

> **WAITING ON OWNER — AGENT WORK COMPLETE.** The candidate should remain a draft PR. Before merge, the owner must supply approved Google and Stripe test configuration through a secret mechanism, authorize permanent hosting, run the credential-backed provider lifecycles and permanent deployment smoke checks, confirm final CI, and approve PR #9.

The complete gate table, evidence inventory, deployment determination, and exact owner actions are maintained in [RELEASE_CERTIFICATION.md](./RELEASE_CERTIFICATION.md).
