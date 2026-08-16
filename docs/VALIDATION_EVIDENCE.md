# ClientVerse CRM — Validation Evidence

This document is the canonical detailed evidence log for the 2026-08-16 certification cycle. It supersedes earlier incremental notes that stated a MongoDB-backed authenticated browser environment was unavailable.

## Environment and Test Data

| Item | Value used for certification |
|---|---|
| CRM tenant | ClientVerse HQ |
| Test roles | Workspace administrator and invited team member |
| Created company | Queen City Certification Services |
| Created contact | Morgan Certification |
| Created opportunity | Queen City Certification Rollout — $32,500 |
| Generated Client 360 workspace | Queen City Certification Rollout — onboard |
| Created commitment | Approve the certification rollout scope — due 2026-08-30 |
| Created task | Schedule the certification rollout kickoff |
| Created approval | Approve the certification rollout plan — approved |
| Created outcome | Certification rollout readiness — 0 / 100 % readiness |

All records are fictional certification data. No customer data, production credentials, or provider tokens were used.

## End-to-End Browser Evidence

| Time sequence | Browser action | Result | Evidence |
|---:|---|---|---|
| 1 | Administrator sign-in | Authenticated Command Center displayed seeded and created tenant data. | `docs/evidence/dashboard-1440x900.png` |
| 2 | Company creation | Company count increased and the relationship record opened. | `docs/evidence/company-detail.webp` |
| 3 | Contact creation | Contact was linked to the created company and displayed in Directory. | `docs/evidence/contacts-list.webp`, `docs/evidence/contact-detail.webp` |
| 4 | Opportunity creation and movement | Opportunity moved Lead → Proposal → Won. | `docs/evidence/pipeline-1440x900.png` |
| 5 | Client 360 activation | Won opportunity generated an onboard workspace. | `docs/evidence/client-workspaces.webp` |
| 6 | Commitment and task creation | Dated commitment and delivery task persisted. | `docs/evidence/client360-1280x800.png`, `docs/evidence/client360-timeline.webp` |
| 7 | Approval lifecycle | Requested approval was completed by the administrator. | `docs/evidence/approval-completed.webp` |
| 8 | Outcome and audit lifecycle | Outcome appeared in graph; events appeared in timeline and audit feed. | `docs/evidence/outcome-graph.webp`, `docs/evidence/client360-timeline.webp`, `docs/evidence/automation-audit.webp` |
| 9 | Member invitation and role change | Invited member accepted the tenant invitation and reached a member dashboard. | `docs/evidence/team-admin.webp`, `docs/evidence/team-member-denied.webp` |
| 10 | Persistence | Administrator logged out, logged in again, and observed the Client 360 workspace and outcome. | `docs/evidence/dashboard-1440x900.png` |

## Runtime Repairs Discovered by Real Browser Testing

| Defect | Reproduction | Repair | Retest |
|---|---|---|---|
| Onboarding checklist crashed when integration health returned an object. | Dashboard received `{ providers: [] }` instead of an array. | Normalize the input inside memoized checklist construction. | Dashboard loaded after rebuild; production build passed. |
| Client Workspaces route errored during loading. | `WorkspaceSkeleton` referenced an undefined `Skeleton` component. | Import `Skeleton` from the UI component library. | Client Workspaces loaded with both seeded and generated workspaces. |
| Fresh build routed API calls to the static origin when `REACT_APP_BACKEND_URL` was omitted. | Workspaces remained in loading/error state after a rebuild without the public backend URL. | Rebuild with the required environment variable; document the requirement for release automation. | Dashboard, pipeline, directory, workspaces, registries, MCP, audit, team, and notifications loaded over the real API. |

## API/Network Evidence

| Endpoint | Status | Non-sensitive result |
|---|---:|---|
| `GET /api/companies` | 200 | Queen City Certification Services present. |
| `GET /api/contacts` | 200 | `morgan@certification-clientverse.com` present. |
| `GET /api/opportunities` | 200 | Queen City Certification Rollout reported `closed_won`, `32500`. |
| `GET /api/workspaces` | 200 | Generated Queen City workspace reported `onboard`. |
| `GET /api/workspaces/{id}/timeline` | 200 | Seven workflow events returned. |
| `GET /api/workspaces` with no credentials | 401 | `Not authenticated`. |
| `GET /api/team/members` as invited member | 403 | `You do not have permission to perform this action`. |

## Security Evidence

| Control | Result | Evidence |
|---|---|---|
| Role-aware navigation | **PASS** — Team & Access link and page are admin-only. | `docs/evidence/team-admin.webp`, `docs/evidence/team-member-denied.webp` |
| Server-side authorization | **PASS** — member request to Team API returned 403. | Recorded API proof above. |
| Anonymous authorization | **PASS** — uncredentialed workspace request returned 401. | Recorded API proof above. |
| Auditability | **PASS** — authorization denials, invitation acceptance, approval, task, commitment, outcome, and workspace events were logged. | `docs/evidence/automation-audit.webp` |
| Tenant persistence | **PASS** — created records survived administrator logout/login. | `docs/evidence/dashboard-1440x900.png` |

## Responsive Evidence and Findings

The local capture harness produced authenticated Dashboard, Pipeline, and Client 360 screenshots at **1440 × 900**, **1280 × 800**, **768 × 1024**, and **390 × 844**.

| Viewport | Findings |
|---:|---|
| 1440 × 900 | Desktop sidebar, KPI cards, onboarding checklist, and five-stage Kanban were legible and aligned. |
| 1280 × 800 | Client 360 preserved headline, health, evidence actions, workstream tabs, and commitment details. |
| 768 × 1024 | Compact header activated. Wide Kanban and Client 360 workstream strips stayed intentionally horizontally scrollable. |
| 390 × 844 | Dashboard cards stacked clearly; Client 360 preserved health, evidence controls, tab context, and readable touch targets. |

Representative evidence: `docs/evidence/dashboard-1440x900.png`, `docs/evidence/pipeline-768x1024.png`, `docs/evidence/client360-1280x800.png`, `docs/evidence/dashboard-390x844.png`, and `docs/evidence/client360-390x844.png`.

## Major-Surface Coverage

| Surface | Status | Evidence or limitation |
|---|---|---|
| Login, Dashboard, Pipeline, Directory, companies, contacts | **PASS** | Captured in real authenticated browser. |
| Client Workspaces, Client Health, Commitments, Tasks, Approvals, Outcomes, Timeline | **PASS** | Captured in real authenticated browser. |
| Notifications / Action Center | **PASS** | `docs/evidence/action-center.webp` |
| Integrations | **PASS — disconnected UI only** | `docs/evidence/integrations.webp`; no provider credentials supplied. |
| Team | **PASS** | Admin and member-denied screens captured. |
| MCP Console | **PASS — UI only** | `docs/evidence/mcp-console.webp` |
| Automation & Audit | **PASS** | `docs/evidence/automation-audit.webp` |
| Command Palette / Quick Create | **PASS** | `docs/evidence/command-palette.webp`, `docs/evidence/quick-create.webp` |
| Settings | **FAIL** | Dedicated `/settings` route and screen do not exist in the certified repository. |

## Automated Validation

| Command | Result |
|---|---|
| `REACT_APP_BACKEND_URL=<certification backend> npm run build` in `frontend/` | **PASS** — production build compiled successfully. |
| `PYTHONPATH=backend ... pytest -q -n 0` in `backend/` using the active certification environment | **PASS** — `100 passed, 5 skipped, 5 warnings` in 41.30 seconds. |

The skipped tests are optional provider-dependent checks. The warnings are FastAPI lifecycle and multipart deprecations; they are maintained as follow-up work, not suppressed.

## Release-Gate Conclusion

> **NO-GO.** The real authenticated CRM and its core workflows are now evidenced, but production readiness is blocked by the missing Settings implementation and absent credential-backed Gmail, Calendar, and Stripe verification.

The canonical release decision and closure criteria are maintained in [RELEASE_CERTIFICATION.md](./RELEASE_CERTIFICATION.md).
