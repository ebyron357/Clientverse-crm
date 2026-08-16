# ClientVerse CRM — Final Integrated Acceptance Evidence

This document is the canonical, complete replacement evidence record for the final CRM v1 release-candidate acceptance cycle. It supersedes earlier incremental Settings and integration-verification notes while preserving their supported findings.

## Controlled Acceptance Result

The acceptance harness created controlled data under a unique run label, then exercised real FastAPI endpoints against the local MongoDB-backed certification tenant. The final run recorded **42 passed, 0 failed**. It created a company, contact, opportunity, workspace, commitment, task, approval, outcome, member invitation, member account, and isolated outsider tenant. It did not store or display access tokens, invitation tokens, passwords, or provider credentials in this document.

| Domain | Checks completed | Result |
|---|---|---|
| Authentication and Dashboard | Administrator login, dashboard load, re-login persistence | **PASS** |
| Revenue and client activation | Company, contact, opportunity stages, close-won workspace, idempotent repeated close-won | **PASS** |
| Client delivery | Dated commitment, task, approval request and administrator completion | **PASS** |
| Outcomes and health | Outcome creation, Outcome Graph persistence, explainable health | **PASS** |
| Operational evidence | Timeline, audit event query, notification query and Action Center rendering | **PASS** |
| Team and permissions | Invite, register, accept, member dashboard, administrator governance | **PASS** |
| Settings and integration state | Settings preferences, safe provider status, truthful unconfigured failures | **PASS — state only** |
| Durable persistence | Company, contact, workspace, commitment, task, approved approval, and outcome after re-login | **PASS** |

## Acceptance Journey Detail

| Step | API and browser evidence | Result |
|---:|---|---|
| 1–2 | `POST /auth/login`, `GET /dashboard`, administrator Dashboard browser render | **PASS** |
| 3–4 | `POST /companies`, `POST /contacts` | **PASS** |
| 5–7 | `POST /opportunities`, then stage patches through `closed_won` | **PASS** |
| 8 | `GET /workspaces` found one opportunity-linked workspace; repeated close-won did not add another | **PASS** |
| 9–10 | `POST /commitments` with due date and `POST /tasks` | **PASS** |
| 11–12 | `POST /approvals`; member patch denied; admin patch approved | **PASS** |
| 13–14 | `POST /outcomes`, `GET /workspaces/{id}/outcome-graph`, and `GET /workspaces/{id}` | **PASS** |
| 15–17 | Workspace timeline, audit event query, notification query, and Action Center browser render | **PASS** |
| 18–20 | Team invitation, controlled registration, invitation acceptance, and member dashboard | **PASS** |
| 21–22 | Member 403 and administrator 200 checks for approval/team/integration governance | **PASS** |
| 23–24 | Administrator Settings browser render and connection status query | **PASS — provider status only** |
| 25–27 | Administrator re-login and durable record verification | **PASS** |

## Negative, Authorization, and Data Integrity Evidence

| Check | HTTP result | Outcome |
|---|---:|---|
| Unauthenticated `GET /workspaces` | 401 | Protected route rejects anonymous access. |
| Cross-tenant company read | 404 | Isolated tenant cannot read controlled company. |
| Cross-tenant workspace read | 404 | Isolated tenant cannot read controlled workspace. |
| Invalid workspace read | 404 | Invalid identifier fails safely. |
| Task creation for invalid workspace | 404 | Invalid reference does not create a task. |
| Member approval decision | 403 | Governance action remains server-side admin-only. |
| Member team listing | 403 | Team administration remains server-side admin-only. |
| Member Google connection initiation | 403 | Provider-management action remains server-side admin-only. |
| Repeated close-won stage patch | 200; one workspace | Idempotent workspace creation behavior verified. |
| Malformed contact email | 422 | Validation repair prevents corrupt contact input. |

## Integration Evidence and Truthful Blocked State

| Provider | Initial status | Connection attempt | Lifecycle verdict |
|---|---|---|---|
| Gmail | `disconnected`; no sensitive fields in connection response | `POST /integrations/google/connect` returned 400 stating that Google OAuth credentials are not configured. | **BLOCKED** — no approved Google OAuth test client/account supplied. |
| Google Calendar | `disconnected`; no sensitive fields in connection response | Shares the Google OAuth connection flow; same 400 configuration failure. | **BLOCKED** — no approved Google OAuth test client/account supplied. |
| Stripe | `disconnected`; no sensitive fields in connection response | `POST /integrations/stripe/connect` returned 400 stating that `STRIPE_API_KEY` is not configured. | **BLOCKED** — no approved Stripe test-mode key supplied. |

The active certification backend contained none of the provider configuration variable names required for the full lifecycle. Google additionally requires a callback setup through `GOOGLE_REDIRECT_URI` or `PUBLIC_BACKEND_URL` and encrypted credential storage through `INTEGRATION_ENC_KEY`. No fabricated connected state, sync result, disconnect, or reconnect result was recorded.

## Lifecycle Defect Found and Repaired

| Item | Evidence |
|---|---|
| Defect | The initial final-acceptance run accepted `not-an-email` with HTTP 200 when creating a contact. |
| Repair | `ContactInput.email` now uses `Optional[EmailStr]`; a dedicated backend regression test was added. |
| Retest | Final acceptance run returned HTTP 422 for malformed email and finished with 42 passing checks. |

## Automated Validation

| Command or gate | Exact result |
|---|---|
| `node /home/ubuntu/run_final_crm_acceptance.mjs` | **PASS** — `42 passed, 0 failed`. |
| `cd frontend && REACT_APP_BACKEND_URL=<certification backend> npm run build` | **PASS** — compiled successfully; 323.12 kB JavaScript and 14.38 kB CSS after gzip. |
| `cd backend && PYTHONPATH=backend ... pytest -q -n 0` | **PASS** — `101 passed, 5 skipped, 5 warnings in 44.49s`. |
| `npx eslint src --max-warnings=0` | **FAIL** — exit code 2 because ESLint 9 found no flat configuration file. |
| Browser console review | **PASS** — no uncaught console output during final administrator dashboard, Client 360, notifications, and Settings verification. |

Backend coverage includes the repository’s authentication, role-permission, tenant-isolation, integration normalizer, timeline, notification/digest, and commitment/SLA tests. The five skipped tests are optional provider-dependent checks; their external dependencies are unavailable and the provider blocker is explicitly retained.

## Visual Evidence

| Surface | Evidence location |
|---|---|
| Administrator Dashboard | `docs/evidence/acceptance-dashboard-admin.webp` |
| Client 360 health | `docs/evidence/acceptance-client360-health.webp` |
| Outcome Graph | `docs/evidence/acceptance-outcome-graph.webp` |
| Timeline | `docs/evidence/acceptance-timeline.webp` |
| Action Center | `docs/evidence/acceptance-notifications.webp` |
| Settings | `docs/evidence/acceptance-settings.webp` |
| Disconnected integration registry | `docs/evidence/integration-provider-blocked.webp` |

## Final Release Gate

> **NO-GO.** The core CRM lifecycle and the final controlled acceptance journey passed. The branch remains blocked by missing credential-backed Gmail, Google Calendar, and Stripe lifecycle evidence, and by the absent ESLint static-analysis configuration required by this release gate.

The canonical release summary and required owner actions are maintained in [RELEASE_CERTIFICATION.md](./RELEASE_CERTIFICATION.md).
