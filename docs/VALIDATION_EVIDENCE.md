# ClientVerse CRM — Integrated Validation Evidence

This is the canonical validation record for the ClientVerse CRM release candidate. It incorporates controlled lifecycle acceptance, lint and CI closure, provider blocked-state evidence, and the externally reachable deployment proof-of-life exercise. No passwords, session tokens, OAuth tokens, client secrets, encryption keys, database credentials, or authorization codes are included.

## Live Deployment Evidence

| Evidence point | Exact result |
|---|---|
| Frontend availability | `https://3001-in8v1wws9289jt9pfzcyj-03350434.us4.manus.computer` returned HTTP 200 and rendered the authenticated CRM. |
| Backend availability | `https://8001-in8v1wws9289jt9pfzcyj-03350434.us4.manus.computer/api` accepted authenticated CRM workflow requests. |
| Health | `GET /api/health` returned HTTP 200 with `service: ClientVerse`, `status: ok`, and `database: up` before and after the workflow. |
| Callback reachability | `GET /api/integrations/google/callback` returned HTTP 307 safe error redirect without OAuth inputs, confirming the deployed route resolves. |
| Browser console | No console output during the authenticated Dashboard, Directory, and reloaded Client Workspaces checks. |

## Deployed End-to-End Proof of Life

The controlled run `PROOF-20260816211130` used the real external API and an approved administrator identity held only in backend process memory. It created the following records and then reauthenticated and reloaded the frontend. The persisted record assertions all returned true.

| Workflow step | Result |
|---|---|
| Authenticate | **PASS** — initial and post-refresh login HTTP 200. |
| Create company | **PASS** — HTTP 200. |
| Create linked contact | **PASS** — HTTP 200. |
| Create opportunity | **PASS** — HTTP 200. |
| Move to closed won | **PASS** — HTTP 200. |
| Confirm client workspace | **PASS** — workspace created from the controlled opportunity. |
| Create commitment | **PASS** — HTTP 200 in the controlled workspace. |
| Re-login and API persistence check | **PASS** — company, contact, closed-won opportunity, workspace, and commitment remained present. |
| Browser reload persistence check | **PASS** — controlled workspace remained visible on reloaded Client Workspaces route. |

The sanitized machine-readable result is `docs/evidence/proof-of-life-api.json`; live browser observations and screenshots are stored under `docs/evidence/proof-of-life-*`.

## Deployment Configuration Presence

| Name | State |
|---|---|
| `MONGO_URL` | **PRESENT** |
| `DB_NAME` | **PRESENT** |
| `JWT_SECRET` | **PRESENT** |
| `FRONTEND_URL` | **PRESENT** |
| `CORS_ORIGINS` | **PRESENT** |
| `PUBLIC_BACKEND_URL` | **MISSING** |
| `INTEGRATION_ENC_KEY` | **MISSING** |
| `GOOGLE_CLIENT_ID` | **MISSING** |
| `GOOGLE_CLIENT_SECRET` | **MISSING** |
| `GOOGLE_REDIRECT_URI` | **MISSING** |

The exact reachable OAuth callback route is `https://8001-in8v1wws9289jt9pfzcyj-03350434.us4.manus.computer/api/integrations/google/callback`. It cannot be derived by the application until `PUBLIC_BACKEND_URL` is configured, and it cannot be used for a complete OAuth lifecycle until the required Google client and encrypted-storage configuration is present.

## Controlled Lifecycle, Authorization, and Provider Baseline

| Domain | Result |
|---|---|
| Final controlled CRM acceptance | **PASS** — `42 passed, 0 failed`. |
| Tenant isolation | **PASS** — controlled cross-tenant company and workspace reads returned HTTP 404. |
| Protected routes | **PASS** — unauthenticated protected request returned HTTP 401. |
| Governance authorization | **PASS** — member approval, team, and Google integration management were server-side HTTP 403. |
| Contact validation | **PASS** — malformed contact email returns HTTP 422. |
| Gmail and Calendar baseline | **PASS — truthful blocked state** — both are `disconnected`; connection and Gmail sync fail safely without configuration; registry responses expose no secret markers. |
| Credential-backed Google lifecycle | **BLOCKED** — OAuth client configuration, redirect configuration, encrypted-storage key, and approved test-account authorization are absent. |

## Regression Evidence

| Gate | Exact result |
|---|---|
| ESLint 9 | **PASS** — zero errors and zero warnings. |
| Frontend production build | **PASS** — local production bundle built successfully. |
| Backend CI | **PASS** — `102 passed, 4 skipped, 5 warnings`. |
| Current deployment proof of life | **PASS** — health, authentication, data creation, workspace activation, commitment creation, and persistence passed against the external frontend/backend pair. |

No source code or runtime configuration was changed during the proof-of-life exercise. Therefore the existing successful CI run remains the applicable code-regression result.

## Final Release Gate

> **NO-GO.** The CRM is deployed, reachable, and demonstrably functional, but Gmail, Google Calendar, and Stripe credential-backed lifecycles remain required before a production release verdict can change.

The canonical release summary, externally reachable endpoints, callback instruction, evidence locations, and owner actions are maintained in [RELEASE_CERTIFICATION.md](./RELEASE_CERTIFICATION.md).
