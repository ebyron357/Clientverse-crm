# ClientVerse CRM — Integrated Validation Evidence

This is the canonical validation record for the ClientVerse CRM release candidate. It incorporates controlled lifecycle acceptance, lint and CI closure, provider blocked-state evidence, deployed proof-of-life evidence, and the client-value release. No passwords, session tokens, OAuth tokens, client secrets, encryption keys, database credentials, portal tokens, or authorization codes are included.

## Client-Value Release Evidence

| Capability | Tested outcome | Integrity or safety proof |
|---|---|---|
| Client portal | An administrator created a portal link; public portal data and a client request were accepted. | Link lists redacted the token and a revoked token returned HTTP 404. |
| Documents | A workspace document record was created in pending-approval state. | The record is tenant/workspace-scoped and external document URLs are optional metadata only. |
| Estimate and invoice | An estimate changed to sent, created a local invoice, then safely returned the existing invoice on retry. | Invoice creation is idempotent and payment status reports `requires_stripe_configuration`. |
| Appointments | One appointment was created and a colliding owner time range returned HTTP 409. | Reminder preparation returned `outbound: disabled` and created internal work instead of a provider send. |
| Field check-in | An authenticated user saved a workspace check-in. | The check-in records the authenticated actor and tenant/workspace references. |
| Safe automation | A configured template ran successfully. | The run result reported `outbound: disabled`; it created internal work only. |
| Review request | A review request record was prepared. | The record reported `outbound: disabled`; nothing was sent or posted. |
| Capacity and playbooks | Capacity grouped open/overdue tasks by owner; a vertical playbook created tasks. | Repeat playbook application returned `duplicate: true`. |
| Scope and access | Unauthenticated Client Operations access and cross-tenant workspace document access were checked. | Results were HTTP 401 and HTTP 404 respectively. |

The sanitized result is stored at `docs/evidence/client-value-api.json`. Its content excludes account identities, portal tokens, passwords, provider credentials, and all durable record identifiers.

## Browser Evidence

The temporary client-value frontend build was authenticated as a controlled workspace administrator against the updated disposable API. The following user-visible surfaces rendered without browser-console output.

| Surface | Verified detail | Screenshot |
|---|---|---|
| Client Operations `/client-ops` | Workspace selector, portal controls, safe-by-default configuration notice, and client-value metrics rendered. | `docs/evidence/client-value-browser.md` |
| Commercial & Documents | Document/approval coordination, estimate creation, local invoice control, scoped commercial history, and Stripe limitation rendered. | `docs/evidence/client-value-browser.md` |
| Field Ops `/field` | Mobile-first check-in form, appointment context, internal reminder control, and persisted field activity rendered. | `docs/evidence/client-value-browser.md` |
| Capacity & Playbooks | Owner workload, overdue counts, and four vertical playbook controls rendered. | `docs/evidence/client-value-browser.md` |

This browser verification used temporary exposed verification ports only. It did not alter the deployed frontend/backend pair or publish any branch contents.

## Existing Live Deployment Evidence

| Evidence point | Exact result |
|---|---|
| Frontend availability | `https://3001-in8v1wws9289jt9pfzcyj-03350434.us4.manus.computer` returned HTTP 200 and rendered the authenticated CRM. |
| Backend availability | `https://8001-in8v1wws9289jt9pfzcyj-03350434.us4.manus.computer/api` accepted authenticated CRM workflow requests. |
| Health | `GET /api/health` returned HTTP 200 with `service: ClientVerse`, `status: ok`, and `database: up` before and after the workflow. |
| Callback reachability | `GET /api/integrations/google/callback` returned HTTP 307 safe error redirect without OAuth inputs, confirming the deployed route resolves. |
| Browser console | No console output during the authenticated Dashboard, Directory, and reloaded Client Workspaces checks. |

The prior controlled run `PROOF-20260816211130` created a company, linked contact, opportunity, closed-won workspace, and commitment. It then reauthenticated and reloaded the frontend. Persisted-record assertions all returned true. The supporting files remain `docs/evidence/proof-of-life-api.json` and `docs/evidence/proof-of-life-browser.md`.

## Regression Evidence

| Gate | Exact result |
|---|---|
| Controlled CRM acceptance | **PASS** — `42 passed, 0 failed`. |
| Client-value focused API script | **PASS** — all portal, commercial, appointment, field, automation, review, capacity, playbook, isolation, and redaction checks passed. |
| Client-value backend tests | **PASS** — `2 passed`. |
| Full isolated backend suite | **PASS** — `103 passed, 5 skipped, 5 warnings in 33.09s`. |
| ESLint 9 | **PASS** — zero errors and zero warnings. |
| Frontend production build | **PASS** — CI-style warnings-as-errors build completed; 330.94 kB JavaScript and 14.74 kB CSS after gzip. |
| Client-value browser console | **PASS** — no console output. |

The backend warnings are the previously recorded multipart and FastAPI startup/shutdown deprecations. The skips are provider-dependent and do not represent Gmail, Google Calendar, or Stripe lifecycle certification.

## Deployment Configuration Presence

| Name | State |
|---|---|
| `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `FRONTEND_URL`, `CORS_ORIGINS` | **PRESENT** |
| `PUBLIC_BACKEND_URL`, `INTEGRATION_ENC_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | **MISSING** |

The exact reachable OAuth callback route is `https://8001-in8v1wws9289jt9pfzcyj-03350434.us4.manus.computer/api/integrations/google/callback`. It cannot be used for a complete credential-backed lifecycle until the required Google client, callback/base URL, encrypted-storage, and approved test-account configuration is present.

## Final Release Gate

> **NO-GO.** The client-value release is code- and workflow-verified, and the existing CRM remains reachable with proven persistence. Credential-backed Gmail, Google Calendar, and Stripe lifecycles remain unresolved P0 requirements. Full accessibility/performance assessment and FastAPI lifespan migration remain P1/P2 requirements.

The canonical release summary, current evidence locations, provider setup instructions, and owner actions are maintained in [RELEASE_CERTIFICATION.md](./RELEASE_CERTIFICATION.md).
