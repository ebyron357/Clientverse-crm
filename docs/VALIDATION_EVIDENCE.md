# ClientVerse CRM — Validation Evidence

This is the canonical detailed evidence record for the 2026-08-16 certification cycle. It supersedes prior incremental notes and reflects closure of the repository-controlled Settings-surface blocker.

## Settings Audit Outcome

No dedicated `/settings` route, Settings page, or Settings navigation entry existed before this task. Existing capability was distributed across `Action Center` for notification preferences, `Registries` for provider state, `Team & Access` for admin-only governance, and the authenticated session context for account information.

The new Settings page deliberately acts as a concise **index of supported controls**, not a duplicate configuration system. It presents account identity and a session sign-out action, summarizes effective notification and delivery state, lists safe provider statuses, and routes users to the existing dedicated pages that own each editable workflow.

## Files Changed for Settings

| File | Change |
|---|---|
| `frontend/src/pages/Settings.jsx` | Added authenticated settings index with safe API summaries, role-aware organization section, and routed actions. |
| `frontend/src/App.js` | Added protected `/settings` route. |
| `frontend/src/components/AppShell.jsx` | Added role-aware Settings sidebar entry and page-title metadata. |
| `frontend/src/components/GlobalCommandDialog.jsx` | Added keyboard-discoverable Settings command. |
| `docs/evidence/settings-desktop-1440x900.png` | Added administrator desktop evidence. |
| `docs/evidence/settings-mobile-390x844.png` | Added administrator mobile evidence. |
| `docs/evidence/settings-member.webp` | Added member-role evidence. |
| `docs/evidence/settings-command-palette.webp` | Added keyboard command-palette evidence. |

## Settings Browser Verification

| Check | Result | Evidence |
|---|---|---|
| Route availability | **PASS** — served `GET /settings` returned HTTP 200; browser route rendered under the authenticated shell. | Browser route run and production build server check |
| Desktop administrator view | **PASS** — profile, notification, provider, and organization cards were visible at 1440 × 900. | `docs/evidence/settings-desktop-1440x900.png` |
| Mobile administrator view | **PASS** — compact header, full-width refresh action, readable identity data, and sign-out control at 390 × 844. | `docs/evidence/settings-mobile-390x844.png` |
| Member view | **PASS** — team/member identity shown; governance marked **Admin managed**; no team administration action exposed. | `docs/evidence/settings-member.webp` |
| Notifications route | **PASS** — Settings button navigated to the existing Action Center preference screen. | Authenticated browser run |
| Integrations route | **PASS** — member Settings button navigated to Registries and showed **Admin manages** provider state. | Authenticated browser run |
| Sidebar route | **PASS** — Settings navigation returned from Registries without a broken link. | Authenticated browser run |
| Keyboard focus | **PASS** — visible Tab focus on ClientVerse navigation; focused Settings refresh action invoked with Enter. | Browser keyboard run |
| Command palette | **PASS** — Settings appeared after Ctrl/⌘ K search and Enter activated the route. | `docs/evidence/settings-command-palette.webp` |
| Console | **PASS** — no uncaught console errors after administrator/member render and navigation tests. | Browser console review |

## Settings Authorization and Data Safety

| API or control | Role | Result |
|---|---|---|
| `GET /api/notifications/preferences` | Member | 200; returned effective preference state and non-sensitive `email_configured` environment state. |
| `GET /api/integrations/connections` | Member | 200; returned three safe provider status rows. |
| `GET /api/team/members` | Member | 403; returned `You do not have permission to perform this action`. |
| Team & Access link | Administrator | Visible and routed to existing server-protected team workflow. |
| Team & Access link | Member | Not rendered; passive governance explanation shown instead. |
| Provider credentials and secrets | All users | Not rendered by Settings; only connection status labels are displayed. |

The Settings page introduces no backend mutation endpoint and no client-only authorization rule. Existing server-side role checks remain authoritative for team, invitation, integration connection, sync, and governance operations.

## Full Validation Commands

| Command | Exact result |
|---|---|
| `cd frontend && REACT_APP_BACKEND_URL=<certification backend> npm run build` | **PASS** — compiled successfully; 323.12 kB JavaScript and 14.38 kB CSS after gzip. |
| `cd backend && PYTHONPATH=backend REACT_APP_BACKEND_URL=<certification backend> ADMIN_EMAIL=<certification admin> ADMIN_PASSWORD=<certification password> DEMO_MEMBER_EMAIL=<certification member> DEMO_MEMBER_PASSWORD=<certification password> MONGO_URL=mongodb://127.0.0.1:27018 DB_NAME=clientverse_cert JWT_SECRET=<certification secret> pytest -q -n 0` | **PASS** — `100 passed, 5 skipped, 5 warnings in 44.50s`. |
| `curl -sS -o /dev/null -w '%{http_code}' <frontend>/settings` | **PASS** — `200`. |

The five skipped tests are optional provider-dependent checks. The five warnings concern FastAPI lifecycle and multipart deprecations; they remain recorded rather than hidden.

## Existing Authenticated CRM Evidence

The prior real browser certification still applies: it created and persisted fictional company, contact, opportunity, won workspace, commitment, task, approval, outcome, audit, invitation, member restriction, and logout/login persistence data. Existing evidence remains in `docs/evidence/`.

| Surface | Status |
|---|---|
| Login, Command Center, Pipeline, Directory | **PASS** |
| Client Workspaces, Client Health, Commitments, Tasks, Approvals, Outcomes, Timeline | **PASS** |
| Notifications, Registries, Team, MCP, Automation & Audit | **PASS** |
| Dashboard, Pipeline, Client 360 responsive captures at 1440×900, 1280×800, 768×1024, 390×844 | **PASS** |
| Settings desktop, mobile, member, and keyboard command coverage | **PASS** |

## Current Release Gate

> **NO-GO.** The Settings route is now real, reachable, browser-verified, permission-safe, and covered by the production build and backend suite. The remaining release blocker is credential-backed Gmail, Google Calendar, and Stripe lifecycle validation.

The canonical release decision and remaining closure requirements are maintained in [RELEASE_CERTIFICATION.md](./RELEASE_CERTIFICATION.md).
