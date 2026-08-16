# ClientVerse CRM — Validation Evidence

## Visual QA

| Date | Surface | Viewport | Result | Evidence |
|---|---|---:|---|---|
| 2026-08-15 | Authentication / sign-in | Desktop browser viewport | **PASS — visual review**. The ClientVerse brand lockup, dark navy brand panel, cyan operating-intelligence highlights, login card hierarchy, labels, error-ready form structure, and primary action were visible with legible contrast and no observed clipping. | `/home/ubuntu/screenshots/3001-in8v1wws9289jt9_2026-08-15_23-47-21_9685.webp` |
| 2026-08-15 | Authentication / sign-in | Desktop browser viewport | **PASS — console review**. No client-side console output was reported after rendering the updated sign-in route. | `/home/ubuntu/console_outputs/view_console_2026-08-15_23-48-16_668.log` |

This log will be extended with executable build, test, workflow, and multi-viewport evidence before pull-request handoff.

## Automated Validation

| Environment | Command or workflow step | Result | Evidence |
|---|---|---|---|
| Local sandbox | `cd frontend && yarn install --frozen-lockfile` | **PASS**. Lockfile install completed successfully, with dependency-resolution and peer-dependency warnings only. | Local terminal session `frontend-clean-install` |
| Local sandbox | `cd frontend && CI=true yarn build` | **PASS**. Production compilation completed successfully; final compressed artifacts were 320.86 kB JavaScript and 14.34 kB CSS. | Local terminal session `frontend-release-build` |
| Local sandbox | `git diff --check` | **PASS**. No whitespace errors reported before commit. | Local terminal session `git-diff-check` |
| GitHub Actions | CI run `31915858511` — Frontend build | **PASS**. Frozen-lockfile install completed; production build compiled successfully in 32.26 seconds. | https://github.com/ebyron357/Clientverse-crm/actions/runs/31915858511 |
| GitHub Actions | CI run `31915858511` — Backend API tests | **PASS**. The MongoDB-backed API suite completed with **101 passed, 4 skipped, and 5 warnings** in 30.88 seconds. | https://github.com/ebyron357/Clientverse-crm/actions/runs/31915858511 |

> The four skipped tests are expected optional AI-provider tests. The external `emergentintegrations` package and an `EMERGENT_LLM_KEY` are intentionally not required for core product startup or CI.

## Release Validation Status

The branch has a successful clean dependency install, deterministic frontend production build, whitespace check, browser login visual check, and completed GitHub Actions run. The remaining validation work before a production decision is credential-backed provider testing (Google, Gmail, Calendar, Stripe, and the optional AI provider) plus full multi-viewport authenticated visual QA against a live environment. These are **external configuration requirements**, not known implementation failures.

## Local Production-Stack Availability

The certification sandbox does not have a running MongoDB service or preconfigured `MONGO_URL` / `DB_NAME`. The official MongoDB 8.0 Ubuntu 24.04 package source was verified, but the package transfer stalled in this environment and was stopped rather than leaving a long-running, partially downloaded install. Accordingly, a local authenticated browser stack cannot be honestly represented as available. The GitHub Actions workflow has already executed the same backend against its managed MongoDB service successfully; the remaining browser journey requires a provisioned local or staging database environment.

## Security Negative-Test Coverage

The successful GitHub Actions API run includes `backend/tests/test_role_permissions.py` and the tenant, webhook, integration, invitation, and undo tests under `backend/tests/`. The exercised coverage explicitly includes cross-tenant workspace-scoped writes (all expected to return 404), invitation acceptance and rotation, tenant membership isolation, last-admin demotion/disable protection, disabled-member access denial, member restrictions for governance operations, and secret-related webhook controls. The CI run completed **101 passed, 4 skipped, and 5 warnings**; no security-test failure was reported.

The full authenticated browser execution of these controls is **BLOCKED** in this sandbox by the unavailable local MongoDB-backed stack. This limitation does not weaken the API-level CI result; it prevents certification of the separate browser interaction and visual evidence requirements.

## Browser Visual and Console QA

The current locally served login route was re-rendered in the browser after the final product changes. The desktop composition remained visually coherent: the navy brand panel, cyan hierarchy accents, form labels, controls, primary action, and contrast remained legible with no observed clipping. Browser console inspection reported no output. Authenticated dashboard, records, Client 360, notifications, integrations, team, and governance screenshots at desktop/tablet/mobile breakpoints remain **BLOCKED** because the sandbox lacks a MongoDB-backed backend environment; they have not been substituted with static or fabricated evidence.

## Integration Certification

| Provider | Implementation validation | Live credential validation | External configuration required |
|---|---|---|---|
| Gmail | **PASS — code review and CI coverage.** Admin-gated OAuth initiation uses random state, PKCE S256, encrypted credential storage, tenant-scoped connection documents, safe field projections, bounded sync, idempotent upserts, normalized CRM communications, and failure state handling. | **BLOCKED.** No Google OAuth values are available in the sandbox. | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` or `PUBLIC_BACKEND_URL`, plus `INTEGRATION_ENC_KEY`; configure the Google redirect URI and complete an admin OAuth flow. |
| Google Calendar | **PASS — code review and CI coverage.** Shares the protected Google OAuth flow, normalizes calendar events, tenant-scopes persistence, associates matched contact/company/workspace context, and exposes admin-gated sync logs. | **BLOCKED.** No Google OAuth values are available in the sandbox. | The Gmail Google configuration above, then authorize the Calendar read scope and run a tenant-scoped sync. |
| Stripe | **PASS — code review and CI coverage.** Admin-gated verification and sync use a server-side key only, normalize customer/invoice/subscription data, upsert per tenant, feed billing records to CRM context, and expose disconnect/degraded state. | **BLOCKED.** No Stripe key is available in the sandbox. | `STRIPE_API_KEY` with read-only access for the target test or production account, then connect and run a sync. |
| Evidence-backed AI | **PASS — optional implementation boundary.** The provider is not required for core startup or CI; AI behavior remains configuration-dependent rather than simulated. | **BLOCKED.** No `EMERGENT_LLM_KEY` or private provider package access is available. | Supply `EMERGENT_LLM_KEY` and provider package access only if enabling the optional AI features; perform grounding, disclosure, authorization, and fallback testing. |

The sandbox credential-presence check returned **ABSENT** for every listed Google, Stripe, encryption, public-backend, and optional AI variable. Credential absence is recorded as **EXTERNAL CONFIGURATION REQUIRED**, not an unfinished integration implementation.

## Reconciled Acceptance Finding

The repository's historical `test_reports/iteration_9.json` reported that the admin **Verify** action in the webhook manager was missing its `openVerify` handler. The current implementation defines `openVerify`, requests `GET /api/webhooks/{id}/secret`, displays the value only in the admin-gated verification dialog, and preserves the copyable Node.js HMAC verification guidance. The historical report is therefore treated as a **resolved** issue; the behavior remains subject to backend-enabled end-to-end validation in CI.
