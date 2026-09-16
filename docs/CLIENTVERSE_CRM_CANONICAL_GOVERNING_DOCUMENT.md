# ClientVerse CRM — Canonical Governing Document

**Version:** 1.10 — complete replacement
**Effective:** 2026-09-16
**Status:** ACTIVE — this is the single source of truth for ClientVerse CRM product scope, capability status, and implementation order.
**Repository:** `ebyron357/Clientverse-crm`
**Baseline commit at issue:** `main@3f14347610e5ca6cd8521c74f4420d3b2c08a9e8` (PR #24 merged 2026-09-15T18:19Z)
**Current `main` at this revision:** `main@e8d5678` (PR #27 squash-merged 2026-09-16T02:55Z; PR #26 at `3150530` before it)

---

## 0. Document control

### 0.1 What this document replaces

This document is a **living canonical replacement**, not an addendum. It merges every still-valid requirement from the documents below, removes duplicates and superseded statements, corrects completion claims that evidence does not support, and adds the recovered expansion scope.

| Superseded document | Disposition |
|---|---|
| `memory/PRD.md` | Merged. Product requirements and implemented-feature claims folded into §4. Retained as a historical implementation log only. |
| `docs/CLIENTVERSE_PRODUCT_COMPLETION_BRIEF.md` | Merged. Product/UX standard folded into §1.3 and §4.B. Retained as a historical execution directive; its 42 phases are no longer a separate scope authority. |
| `docs/UX_SYSTEM_IMPROVEMENTS_ASSESSMENT.md` (2026-08-18) | Merged. Its P0/P1/P2 portfolio is reconciled into §4 and §9. |
| `docs/REMAINING_WORK.md` (2026-09-10) | Merged into §10 (owner-only blockers). |
| `todo.md` | Demoted to historical task ledger. Its completion ticks are **not** capability status; §4 governs status. |
| `AGENTS.md` (closeout state section) | Merged into §3. Operational Railway/API notes retained there as runbook material. |
| ClickUp `CONTROL — W2 — ClientVerse Website + CRM Closeout` (task `86e2tkptk`, canonical replacement 2026-09-13) | **Primary recovered authority.** Its CRM sections (§6, §7, §10, §11) are carried forward verbatim in intent into §1, §4, and §9. The ClickUp control remains the operational status plane; this document remains the engineering scope authority. Keep them reconciled. |
| Slack canvas `ClientVerse CRM — Release Candidate Command Brief` (`F0BPNUF7VK3`, 2026-08-11) | Merged. Its security, UI/UX, and engineering operating rules are carried into §1.3, §1.4 and §12. |

### 0.2 Authority order

1. This document — CRM product scope, capability status, implementation order.
2. ClickUp `CONTROL — W2` — program-level operational status and owner gates.
3. GitHub (`main`, CI, PRs, Issue #10) — engineering and evidence truth.
4. `docs/RAILWAY_RUNBOOK.md`, `docs/PRODUCTION.md` — deployment/runbook mechanics.

Where any two disagree, the newer owner-approved instruction wins and **this document must be updated in place** rather than patched by a new fragment.

### 0.3 Provenance rules used to build this document

Every capability in §4 carries a **provenance** marker:

- `RECOVERED` — the requirement exists in a pre-existing ClientVerse record (repository, ClickUp control, Slack directive, issue, PR, or doc). The record is cited.
- `DIRECTIVE 2026-09-15` — the requirement enters scope through the owner's 2026-09-15 scope-recovery directive only. No earlier ClientVerse record for it was found in this audit.
- `UNRESOLVED` — named in the directive but the source or exact prior approval cannot be established; owner confirmation required.

Nothing in §4 was invented. Where the directive named a capability that the audit could not tie to a prior approved record, it is marked `DIRECTIVE 2026-09-15` and the absence is stated plainly in §7 rather than backfilled with assumed behavior.

### 0.4 Audit scope actually performed (2026-09-15)

- `ebyron357/Clientverse-crm` — full history across **all 31 remote refs** (`git rev-list --all`), all 20 pull requests, all 4 issues and every Issue #10 comment, all in-repo docs and evidence.
- `ebyron357/Clientverse-AI-AGENT-Workforce` — `main` plus open PR #9 (`ai-wos-v2`): canonical operating contract and implementation register.
- `ebyron357/clientverse` (website) — `main@b96beda`, including `docs/GITHUB_REPOSITORY_REGISTRY.md`.
- `ebyron357/clientverse-website-audit` — `docs/clientverse-doctrine/` V4 doctrine set.
- ClickUp — workspace search; `CONTROL — W2 — ClientVerse Website + CRM Closeout` (`86e2tkptk`) read in full.
- Slack — workspace-wide search; `#clientverse-crm`, `#life-os-command-center`, `#quality-control`; canvas `F0BPNUF7VK3` read in full.
- Gmail — **not searched**: the Gmail connector was unauthenticated for this session. See §7.4.

---

## 1. Product definition and non-negotiables

### 1.1 What ClientVerse CRM is

ClientVerse CRM is the **AI-native client operations platform** for the complete customer lifecycle — **WIN → ONBOARD → SERVE → RETAIN → EXPAND** — operated as one commercial program with the `clientverse.io` public website. The website sells the promise; the CRM must visibly prove it. Neither is commercially closed in isolation.

### 1.2 Commercial north star (recovered verbatim in intent from ClickUp `CONTROL — W2` §11)

The representative revenue-recovery workflow the product must be able to run end to end:

1. detect or select a dormant or lost opportunity
2. gather authorized context
3. evaluate account, history, and opportunity
4. recommend a recovery strategy
5. request approval where required
6. launch communication
7. generate personalized media/content when useful
8. return replies, meetings, decisions, and tasks to the CRM
9. continue permitted follow-up
10. attribute recovered, lost, and pending revenue

This workflow is the spine of the **Second Chance** capability family in §4.C. Every expansion capability in this document exists to serve one of its ten steps.

### 1.3 Preserved product and UX standard

- Continue from the existing **FastAPI + MongoDB backend and React + Tailwind + shadcn/ui frontend**. Do **not** restart the CRM. Do **not** replace it wholesale with another CRM.
- Open-source projects are **capability donors, adapters, or references only**, adopted where they improve the existing product without creating duplicate systems.
- The product must read as one coherent premium AI-native operations platform, not a pile of separate tools: command-center dashboard, strong global navigation and search, pipeline/workspace views with fewer clicks, Customer 360, communications surface, meeting-intelligence surface, agent workforce/activity surface, automation/integration center, research/intelligence surface, contextual growth/video/SEO actions where approved, responsive layouts, strong accessibility, and consistent loading/empty/error/approval/audit states.
- Status honesty is part of the UX: a surface must never imply a provider is certified or a capability is live when it is not.

### 1.4 Non-negotiable security and tenancy standard

- Authorization is enforced **server-side**. Tenant A must never reach Tenant B data by changing identifiers, URLs, requests, search terms, API calls, exports, webhooks, integrations, or background jobs.
- No secrets in source, fixtures, logs, documentation, evidence artifacts, or client bundles. Configuration is audited by **name and presence only**.
- No test, demo, or smoke records may persist in a customer-production tenant.
- Every external agent skill, MCP server, MCP tool, agent plugin, or external agent package must pass the §6 security pipeline before it is eligible for production use.
- No capability may weaken or disable a test to pass a gate.

---

## 2. Architecture baseline (preserved, not re-litigated)

| Layer | Current state |
|---|---|
| Backend | FastAPI, single modular service `backend/server.py` (3,352 lines) + `backend/client_value.py`; ~90 `/api/*` endpoints |
| Datastore | MongoDB (Atlas cluster `clientverse-production`) |
| Frontend | React SPA, Tailwind + shadcn/ui, 17 pages, module registry at `frontend/src/platform/modules.js` |
| Module contract | `CLIENTVERSE_MODULES` with three explicit states: `available`, `configuration_required`, `contract_pending` |
| Deployment | Railway, Dockerfile artifact, `/api/health` health check pinned via `railway.json`; Render blueprint retained but superseded |
| CI | `.github/workflows/ci.yml` — backend pytest against MongoDB, frontend `yarn lint --max-warnings=0` and `CI=true yarn build` |
| Scheduled work | `/api/cron/commitment-risk`, `/api/cron/integration-sync`, `/api/cron/daily-digest`, Bearer `WEBHOOK_CRON_SECRET`, idempotent |
| Governed tool execution | MCP console: static tool catalog, per-tenant allowlist, approval levels, undo window, invocation audit |

The module registry is the **contract of record** for which surfaces exist and which are still contracts. New expansion capabilities register there before any route ships.

---

## 3. Verified truth and corrected completion claims

### 3.1 Engineering truth

- `main@7d2235f` — exact-head CI run **#34999894464 passed**: backend **192 passed, 4 skipped, 4 warnings**; frontend warnings-as-errors production build compiled. Exact-head commit statuses successful for Railway (`welcoming-vibrancy / clientverse-crm-production`) and Vercel. (Issue #10, 2026-09-15.)
- `main@3f14347` (head at the time of this revision) — verified directly in a clean local environment against MongoDB 7.0.34 on 2026-09-15:
  - backend suite **196 passed, 4 skipped**;
  - `CI=true yarn build` **passed**;
  - `yarn lint --max-warnings=0` **FAILED** — one `no-unused-vars` error in `frontend/src/pages/WorkspaceDetail.jsx`. See §3.3.
  - `scripts/proof_of_life.mjs` exit 0 (login, unauthenticated 401, full CRM lifecycle, close-won → workspace, persistence, cross-tenant 404).
- `main@3150530` (head as of 2026-09-16) — PR #26 squash-merged at 2026-09-15T23:53Z, bringing the durable work queue, the Second Chance detectors, the Next Best Action service, the dual-gate pipeline, the `/operations` surface and the CI lint gate into `main`. Those capabilities move from `TESTED` to `MERGED`. **`MERGED` is not `DEPLOYED`**: this head has not been deployed or certified against production, and §3.2 still applies.
- `main@e8d5678` (head as of 2026-09-16) — PR #27 squash-merged at 2026-09-16T02:55Z, bringing the approval queue (M-07), the recovery strategy composer (E-20), the `Conversation` / `CommunicationMessage` foundation with its provider-agnostic delivery interface (M-02, E-10), the Recovery strategies / Approvals / Conversations panels, and two further cron entry points. Verified on its head before merge: backend **432 passed, 4 skipped** against a server restarted on the code under test, lint exit 0, build exit 0, `scripts/operations_smoke.mjs` **PASS** with zero failed checks across 63 steps. Evidence: `docs/evidence/operations-verification-20260916.json`. Those capabilities are now `MERGED`. **`MERGED` is not `DEPLOYED`**: the only head ever deployed and certified against production is `ca30587` (2026-09-01, §3.2); no head since — this one included — has been, and §3.2 still applies.
- `main@730b1b3` (head as of 2026-09-16) — PR #28 squash-merged at 2026-09-16T23:31Z, bringing the Recovery Case and normalized recovery-event foundation (E-21), the recovery runner (E-22), the recovery-case operations routes, and the fixes from that PR's review round. Verified on the merged head in a clean local environment: backend **508 passed, 4 skipped**. Exact-head CI on the merged branch was green across all five checks before merge (Backend API tests ×2, Frontend build ×2, Vercel). Those capabilities move from `TESTED` to `MERGED`. **`MERGED` is not `DEPLOYED`**: the only head ever deployed and certified against production remains `ca30587` (2026-09-01, §3.2), and §3.2 still applies.
- `claude/clientverse-scope-recovery-bj6u7w` (restarted from `main@730b1b3`) carries unmerged capability work: the recovery attribution ledger (E-23). Status `TESTED`, not `MERGED`.

### 3.2 Production truth

- Railway deployment `d9af2985-30e4-4fb8-b030-ac8b1446db89` running `ca30587` was **LIVE VERIFIED** on 2026-09-01: `/api/health` 200 `{"status":"ok","database":"up"}`, `scripts/proof_of_life.mjs` exit 0 including cross-tenant 404, smoke records fully purged. Evidence: `docs/evidence/production-smoke-20260901.json`.
- A fresh Railway health probe returned HTTP 200 `status=ok`, `database=up` on 2026-09-15 (recorded in Issue #10), but **the runtime SHA is not exposed by the current production deployment**. `git_sha` on `/api/health` is merged in code at `3706c7a`; production has not been redeployed onto a head containing it.
- **Production is not reachable from the current execution environment.** The session egress policy rejects both `clientverse-crm-production-production.up.railway.app:443` and `backboard.railway.com:443` with HTTP 403 at CONNECT. Deployment, production health verification, production smoke, and the two-company production isolation smoke therefore carry status `BLOCKED — TECHNICAL` for any agent running under this policy; they are not owner blockers and require no owner action other than running them from an environment that can reach Railway. Nothing in this document reports production behaviour that was not observed.

### 3.3 Completion claims corrected by this document

| Claim as previously written | Correction |
|---|---|
| `AGENTS.md`: "Production is live and verified" (unqualified) | True **only for `ca30587` as of 2026-09-01**. Current `main` is nine commits ahead and is **not** production-certified. Status: `DEPLOYED`, not `LIVE VERIFIED`. |
| `todo.md`: "Deploy the approved full-stack revision and verify … — VERIFIED 2026-09-01" ticked complete | Accurate for that revision only. It does not certify any later revision. Re-certification is required per release. |
| `memory/PRD.md`: Alert Notifications & Digests "status AVAILABLE" | Code is merged and tested, but email delivery requires `EMERGENT_EMAIL_KEY` and the digest/escalation sweep requires an external scheduler that is **not configured**. Status: `MERGED`, with a `BLOCKED — OWNER INPUT` dependency. |
| Provider lifecycle work described as "certified" in older PR narratives | Mocked, contract, and unit tests do **not** substitute for live provider certification. Google/Gmail/Calendar and Stripe are `BLOCKED — OWNER INPUT`. |
| `docs/REMAINING_WORK.md`: "No incomplete repository task remains" | True only for the pre-expansion release-closeout scope. It is **false** against the scope in §4.B and §4.C of this document. |
| `AGENTS.md` and `docs/REMAINING_WORK.md`: "frontend `yarn lint --max-warnings=0` … are the CI gates" | **False as written.** `.github/workflows/ci.yml` ran only `yarn install` and `yarn build` for the frontend; lint was never executed in CI. A `no-unused-vars` error consequently reached `main@3f14347` unnoticed. Corrected in this change set: the lint gate is added to the workflow and the error is fixed. |
| Next Best Action described as delivered | The workspace strip was client-side only. A backend recommendation service, aggregate queue, and persisted feedback now exist; see NBA-1 in §4.C. |
| Module registry surfaces marked `available` | `available` means the route and API contract exist, not that the capability is live-verified in production. |

### 3.4 Open pull requests

| PR | Title | State | Disposition |
|---|---|---|---|
| #21 | expose non-secret `git_sha` on `/api/health` for deploy parity | closed, merged | Merged into `main` at `3706c7a`; production still does not expose SHA because production has not been redeployed to a head containing it. |
| #26 | Durable work queue, Second Chance detection, Next Best Action service, and the dual security gate | closed, merged | Squash-merged into `main` at `3150530` on 2026-09-15. The capabilities it carries are `MERGED`; none is `DEPLOYED`. |
| #27 | Approval queue (M-07), recovery strategy composer (E-20), and the Conversation / CommunicationMessage foundation | closed, merged | Squash-merged into `main` at `e8d5678` on 2026-09-16. Fifteen review findings across two reviewers; twelve were real and fixed on the branch. The capabilities it carries are `MERGED`; none is `DEPLOYED`. |
| — | No CRM pull request is currently open. | | |
| Workforce PR #9 | AI-WOS v2 canonical operating contract + implementation register | **open (draft)** | Governs the agent-workforce repository, not the CRM. Do not merge as part of CRM work. |

---

## 4. Capability register

**Status vocabulary (exactly one per capability):**
`APPROVED — NOT STARTED` · `IN IMPLEMENTATION` · `CODE COMPLETE` · `TESTED` · `MERGED` · `DEPLOYED` · `LIVE VERIFIED` · `BLOCKED — OWNER INPUT` · `BLOCKED — TECHNICAL` · `DEFERRED`

**Completion rule:** only `LIVE VERIFIED` counts as fully complete. Research, repo selection, a written prompt, local code, an open PR, or passing unit tests never qualify.

### 4.A Core CRM — implemented and merged

| ID | Capability | Status | Evidence / note | Provenance |
|---|---|---|---|---|
| C-01 | Authentication, sessions, login lockout, session revocation | MERGED | PR #17; backend suite | RECOVERED (PR #17, Issue #6) |
| C-02 | Multi-tenant isolation (direct-ID, exports, webhooks, background jobs) | MERGED | PR #17 isolation tests; cross-tenant 404 in production smoke | RECOVERED (Command Brief §Security) |
| C-03 | Contacts, Companies | MERGED | `/api/contacts`, `/api/companies` | RECOVERED (module registry) |
| C-04 | Opportunities, Deals, Pipeline stages | MERGED | `/api/opportunities`, `PATCH /stage` | RECOVERED (module registry) |
| C-05 | Client 360 workspaces, health signals, outcome graph, timeline | MERGED | `/api/workspaces/*` | RECOVERED (module registry) |
| C-06 | Commitments + commitment-risk evaluation | MERGED | `/api/commitments`, `/api/commitments/evaluate-risk` | RECOVERED (PRD) |
| C-07 | Alerts + Action Center work queue with deduplicated lifecycle | MERGED | `/api/alerts`, acknowledge/resolve/escalate | RECOVERED (UX assessment P0 #2; todo.md) |
| C-08 | Notifications, preferences, timezone-aware daily digest | MERGED | `/api/notifications*`, `/api/digest/*` | RECOVERED (PRD) |
| C-09 | Approvals + undo window | MERGED | `/api/approvals`, `PATCH /workspaces/{id}/undo-window` | RECOVERED (Command Brief) |
| C-10 | Signed, versioned, retryable webhooks with replay and match preview | MERGED | `/api/webhooks*`, `/api/webhook-deliveries/*` | RECOVERED (PRD) |
| C-11 | MCP console — allowlist, approval levels, undo, invocation audit | MERGED | `/api/mcp/*`; static catalog + per-tenant allowlist | RECOVERED (module registry) |
| C-12 | Registries and integration health | MERGED | `/api/registry/{kind}`, `/api/integrations/health` | RECOVERED (module registry) |
| C-13 | Team, roles, invitations | MERGED | `/api/team/*` | RECOVERED (PR #1) |
| C-14 | Audit trail and domain events | MERGED | `/api/audit`, `/api/events` | RECOVERED (module registry) |
| C-15 | Client Operations + Client Portal + Field Ops | MERGED | `/client-ops`, `/portal/:token`, `/field` | RECOVERED (module registry) |
| C-16 | Cron endpoints (commitment-risk 15m, integration-sync 30m, daily-digest hourly), idempotent, Bearer-authenticated | MERGED | `/api/cron/*`; **no external scheduler is wired** → see O-03 | RECOVERED (RAILWAY_RUNBOOK) |
| C-17 | Google / Gmail / Calendar integration lifecycle (PKCE connect, callback, refresh-on-401, reconnect, disconnect, redaction) | BLOCKED — OWNER INPUT | 22 deterministic lifecycle tests pass; live certification impossible without owner OAuth client + consent | RECOVERED (Issue #10) |
| C-18 | Stripe test-mode lifecycle (PaymentIntent, signed webhook, idempotency, tenant-scoped invoice) | BLOCKED — OWNER INPUT | Tests pass; unsigned webhook → 503 safe refusal; live certification needs owner test key | RECOVERED (Issue #10) |
| C-19 | AI generation endpoint | BLOCKED — OWNER INPUT | `/api/ai/generate` requires `EMERGENT_LLM_KEY`; 2 tests skipped for its absence | RECOVERED (PRD, CI skips) |
| C-20 | Railway production deployment + health check | DEPLOYED | LIVE VERIFIED at `ca30587` 2026-09-01; current `main` not re-certified | RECOVERED (Issue #10) |
| C-21 | Shared surface states (loading/empty/error + retry) across Command Center, integrations, workspace activity, audit, MCP | MERGED | PR #24, `SurfaceState.jsx` | RECOVERED (PR #24) |
| C-22 | Next Best Action | MERGED | Superseded by NBA-1 in §4.C — the client-side strip is removed and the surface now consumes the backend service. | RECOVERED (UX assessment P0 #3) |
| C-23 | Frontend lint enforced in CI | MERGED | `.github/workflows/ci.yml` now runs `yarn lint --max-warnings=0` before the build; the pre-existing error on `main` is fixed. | PR #26 (§3.3) |
| C-24 | `/operations` operator surface | MERGED | Work-queue queue depth and dead-letter visibility with acknowledge / resolve / admin replay, the recovery-detection trigger, the ranked recommendation queue, and the security-gate panel that reports scanner configuration honestly. Registered in `CLIENTVERSE_MODULES` as `available`. The Recovery strategies, Approvals and Conversations panels added on top of it merged with PR #27. | PR #26, extended by PR #27 |
| C-25 | Scheduled-job driver | MERGED | `.github/workflows/scheduled-jobs.yml` calls every cron endpoint on the documented cadences once two repository secrets exist, and exits cleanly while they do not. See O-03. | PR #26 |
| C-26 | Conversations operator surface | MERGED | The `/operations` Conversations panel: open threads with channel, handler, consent state and message count; a thread reader with its messages and any blocked-send reason; assign, handoff and close. It states plainly that no delivery provider is registered rather than offering a send button that would fail. | This change set |

### 4.B Approved module contracts — registered, not yet built

These were declared in `frontend/src/platform/modules.js` as `contract_pending` and are therefore approved scope with a named contract. All are `APPROVED — NOT STARTED` **except M-07**, which now carries its own status in the Status column below.

| ID | Module | Declared contract | Status | Expansion role |
|---|---|---|---|---|
| M-01 | Email | `CommunicationMessage service` | **BLOCKED — OWNER INPUT** | The `CommunicationMessage` model, its state machine and the provider-agnostic delivery interface are delivered (§8 #2). What is missing is an email provider adapter and the Google authorisation to run it (O-01). Drafting works; sending is refused, and the refusal names the missing precondition. |
| M-02 | Unified Inbox | `Conversation service` | MERGED | `backend/conversations.py`. Tenant-scoped threads with participants, channel, status, assignment, the agent/human boundary, a per-channel consent record, provider-thread deduplication, and an inbound path that reopens a closed thread. Operator surface at `/operations`. 29 tests. |
| M-03 | SMS | `Message delivery service` | **BLOCKED — OWNER INPUT** | Same position as M-01: the message model and delivery interface exist; no SMS provider is registered in the integration catalogue and none has been chosen (O-06 covers the adjacent telephony decision). |
| M-04 | Calling | `Call activity service` | APPROVED — NOT STARTED | Phone execution (E-06), missed-call recovery (E-02) |
| M-05 | Calendar | `Calendar event service` | APPROVED — NOT STARTED | Meeting intelligence (E-12) |
| M-06 | Workflows | `Workflow definition and run services` | APPROVED — NOT STARTED | Durable work queues (E-04), orchestration (E-15) |
| M-07 | Approvals (module surface) | `Approval queue service` | MERGED | `backend/approval_queue.py`. Built on C-09's own `approvals` collection rather than beside it, so a request raised by `POST /api/approvals`, by an agent, or by an MCP level-2 write is one record with one state machine. Adds a bound action (an approval authorises *that* action, not a category), single-use consumption via an atomic claim so concurrent workers produce exactly one execution, expiry evaluated on read as well as by the sweep, database-enforced deduplication, requester provenance, risk tier, optional separation of duties, and a full decision history. **An approval never unblocks a missing prerequisite**: consumption re-checks the recorded blocks and refuses. 27 tests. |
| M-08 | Revenue Operations | `Revenue ledger and forecast services` | APPROVED — NOT STARTED | Recovery attribution (north-star step 10) |
| M-09 | Support | `Case and SLA services` | APPROVED — NOT STARTED | Omnichannel handoff |
| M-10 | Reporting | `Metric and report services` | APPROVED — NOT STARTED | Recovery/agent measurement |
| M-11 | Relationship Intelligence | `Recommendation service v1` | APPROVED — NOT STARTED | Next Best Action backend (E-05) |
| M-12 | Migration | `Import job and reconciliation services` | APPROVED — NOT STARTED | Onboarding new tenants |
| M-13 | Knowledge | `Knowledge item service` | APPROVED — NOT STARTED | Agent context for recovery outreach |

### 4.C Expansion capability register

| ID | Capability | Status | Provenance | Notes |
|---|---|---|---|---|
| E-01 | **Second Chance** — missed-opportunity / dormant-and-lost revenue recovery (the ten-step north-star workflow end to end) | APPROVED — NOT STARTED | RECOVERED — ClickUp `CONTROL — W2` §11 | The umbrella capability, still not started **as a whole**: steps 1–4 exist (detection E-03/E-04, strategy composition E-20), steps 5–10 do not. E-02…E-04 are its detection lanes; E-05…E-15 are its execution and intelligence services. |
| E-02 | Missed-call recovery | APPROVED — NOT STARTED | DIRECTIVE 2026-09-15 (corroborated by the public product promise on `clientverse.io`: "cannot afford a missed call") | Hard-blocked on E-06 (call activity capture). No prior CRM record specifies the recovery behavior; contract must be written before build. |
| E-03 | Stalled-lead recovery | MERGED | RECOVERED — ClickUp §11 ("dormant or lost opportunity"); UX assessment ("opportunity has no future activity") | `backend/second_chance.py`. Deterministic rule: an open opportunity with no qualifying activity (event, stage change, or update) for `SECOND_CHANCE_STALLED_LEAD_DAYS` (default 14). Emits an explainable reason, an `opportunity:<id>` source reference, and a deduplicated durable work item. Closed stages are out of scope. No outbound communication. 13 tests. |
| E-04 | Missed-follow-up recovery | MERGED | RECOVERED — C-06 commitment-risk evaluation exists and is the seed signal | `backend/second_chance.py`. An unresolved commitment or delivery task past its due date plus a configurable grace window becomes a recovery candidate with overdue days, owner and source reference. No outbound communication. |
| E-05 | Durable autonomous work queues | MERGED | DIRECTIVE 2026-09-15 | `backend/work_queue.py`. MongoDB-backed, tenant-scoped, explicit state machine (`queued`/`claimed`/`processing`/`completed`/`retry_scheduled`/`failed`/`dead_letter`) with a rejected-transition matrix, atomic single-winner claim, leases with crash recovery, exponential capped backoff, dead-letter, database-enforced idempotency key, dedupe key, acknowledgement/resolution, admin replay, operator stats, bounded concurrency and round-robin per-tenant fairness. Worker tick at `POST /api/cron/work-queue`. 20 engine tests + API tests. |
| E-06 | Scheduled agent follow-up | APPROVED — NOT STARTED | RECOVERED — ClickUp §11 step 9 ("continue permitted follow-up") | E-05 and M-07 are now delivered, so this is unblocked technically. It still requires an authorised outbound channel (M-01 or M-03) before a follow-up can leave the CRM. |
| E-07 (NBA-1) | Next Best Action / agent task routing (backend service + aggregate queue) | MERGED | RECOVERED — UX assessment P0 #3 | `backend/next_best_action.py`. Tenant-scoped records from six deterministic rules (commitments, approvals, overdue tasks, Second Chance work items, degraded integrations, client health), each with reason, cited `source_refs`, evidence and a fixed priority band. Lifecycle `new`/`accepted`/`dismissed`/`completed`/`snoozed` with outcome and note; generation refreshes explanation without trampling feedback and retires cleared conditions. No fabricated confidence score. Surfaced in Client 360, the Command Center and `/operations`. 14 service tests + API tests. |
| E-08 | Phone execution / phone agent capability | APPROVED — NOT STARTED | DIRECTIVE 2026-09-15 (module M-04 pre-registers the surface) | Telephony provider is an unmade owner decision. Consent, recording, and jurisdiction policy must precede any build. |
| E-09 | Omnichannel conversations | APPROVED — NOT STARTED | RECOVERED — module registry M-01/M-02/M-03; ClickUp §10 "communications surface" | **Its prerequisite is now delivered**: the unified `Conversation` model and the provider-agnostic `CommunicationMessage` interface exist (M-02, §8 #1–#2). The capability itself stays not started, because "omnichannel" means channels, and no channel can carry traffic until a provider adapter is built and authorised (M-01, M-03). |
| E-10 | Human handoff | MERGED | RECOVERED — ClickUp §10; Command Brief (approvals/undo) | Both halves exist. The approval gate is M-07, reusing C-09's `approvals` collection rather than a parallel gate; the conversation-level handoff is `conversations.handoff` — an explicit, audited state change with an actor and a reason, never an implicit consequence of somebody replying. **Limit stated plainly:** handoff operates on conversations that cannot yet send externally, so today it is exercised on internal threads and on drafts waiting for a channel. |
| E-11 | Agent workforce roles surfaced in CRM | APPROVED — NOT STARTED | RECOVERED — ClickUp §10 "agent workforce/activity surface"; `Clientverse-AI-AGENT-Workforce` implements nine roles (operations, sales, marketing, support, engineering, research, browser, project_management, communications) | The workforce runtime is a **separate repository and separate lifecycle**. The CRM consumes it across a contract; it is not merged into the CRM. |
| E-12 | Security scanning before external skills/MCPs are trusted (dual NVIDIA + Cisco gate) | MERGED (pipeline) / BLOCKED — OWNER INPUT (scanners) | DIRECTIVE 2026-09-15; architectural need corroborated by the AI Project Governance Blueprint v2 "third-party intake/security gate" (Slack, 2026-09-13) | `backend/security_gate.py`. Intake registry plus Gate A (16 supply-chain checks) and Gate B (14 capability/execution checks), the full state machine (`DISCOVERED`/`UNDER_REVIEW`/`REJECTED`/`QUARANTINED`/`APPROVED_LIMITED`/`APPROVED`/`REVOKED`), decisions bound to an exact source and version with expiry, and enforcement on `POST /api/mcp/invoke` for any tool marked external. **Approval is impossible while a required scanner is unconfigured — an unrun scanner is never treated as a pass** (owner blocker O-13/O-14). Provenance conflict remains as recorded in §7.2. 24 tests. |
| E-13 | OSINT / intelligence enrichment | APPROVED — NOT STARTED | DIRECTIVE 2026-09-15 (ClickUp §10 approves a "research/intelligence surface" generically) | Data-protection and lawful-basis review required before any build. |
| E-14 | SEO / growth intelligence | APPROVED — NOT STARTED | RECOVERED — ClickUp §10 "contextual growth/video/SEO actions **where approved**" | The ClickUp clause is conditional. Treat the 2026-09-15 directive as the approval that satisfies "where approved". |
| E-15 | Video-agent capability | APPROVED — NOT STARTED | RECOVERED — ClickUp §10 (same conditional clause); ClickUp §11 step 7 ("generate personalized media/content when useful") | Serves north-star step 7. |
| E-16 | Meeting intelligence | APPROVED — NOT STARTED | RECOVERED — ClickUp §10 "meeting intelligence surface" | Capability is approved; its **source repository is unresolved** — see §7.1. Requires M-05. |
| E-17 | CRM feature/UX enhancements mined from Twenty | APPROVED — NOT STARTED | DIRECTIVE 2026-09-15 | Pattern mining only. No code copy, no data-model adoption, no dependency. |
| E-18 | n8n-based orchestration | APPROVED — NOT STARTED | RECOVERED — the workforce repo ships an n8n adapter and four `cvw-*` workflows; `ebyron357/n8n` is a registered active component | **No n8n integration exists in the CRM repository.** Approved only as an execution edge behind an explicit CRM-side contract. |
| E-19 | Slack / ClickUp handoffs | APPROVED — NOT STARTED | RECOVERED — canonical operating contract (ClickUp = task/status plane, Slack = operator/alert plane); workforce repo ships both adapters | **Not present in the CRM.** The CRM contains only a seeded registry record `Slack Notifier` (status `BETA`) — a catalog entry, not an integration. |
| E-20 | Recovery strategy composer (north-star steps 2–4) | MERGED | RECOVERED — ClickUp `CONTROL — W2` §11 steps 2–4 ("gather authorized context", "evaluate the account and its history", "recommend a recovery strategy") | `backend/recovery_strategy.py`. Reads only tenant-owned CRM records — no external lookup and no enrichment. An ordered playbook of six named lanes (`commitment_repair`, `delivery_recovery`, `commitment_repair_first`, `dormant_nurture`, `owner_led_reengagement`, `written_followup`, plus an explicit `needs_human_triage` fallback) selects a lane by stated entry conditions; the output names the rule and cites every fact to the record it came from. **No score, no confidence, no model judgement.** Each step declares the channel it needs and is marked `blocked` with the reason when that channel is not authorised for the tenant. Composition raises an M-07 approval request; it never sends. 25 tests. |
| E-21 | Recovery Case + normalized recovery-event foundation | MERGED | DIRECTIVE 2026-09-16 (Phase 1 execution authorization) | `backend/recovery_case.py`. One normalized event contract for all ten declared sources, and the Recovery Case the event becomes. **Removes the requirement that a recovery opportunity originate as an internal CRM record**: `contact_id`, `company_id`, `opportunity_id` and `workspace_id` are all optional, so a missed call known only by a phone number is a first-class case. Case identity is (tenant, source, source event) with a unique index, so concurrent workers produce one case. Every tenant-owned reference is ownership-checked at creation and at resolution. **Potential and confirmed value are separate fields**; confirming recovered revenue requires evidence. Transitions reuse the existing domain-event log. The two existing detectors emit cases without losing their work items, and `recovery_strategy.compose_for_case` lets a case with no CRM context reach the planner. 61 tests. |
| E-22 | Recovery runner (execution to the provider boundary) | MERGED | DIRECTIVE 2026-09-16 (Phase 1 follow-on) | `backend/recovery_runner.py`. Claims an approved Recovery Case off the durable queue and walks its plan: internal steps are **executed** (a task lands against the case), outbound steps are **drafted into a conversation and stop at the provider boundary** with the refusal named. Each outbound message raises its own M-07 approval carrying the exact text — the plan's approval authorised a motion, not a sentence. The plan's approval is re-read at run time, so a withdrawn approval halts execution rather than relying on the case's state flag. Idempotent per case and per step: a replayed job adopts the existing draft and task instead of producing a second copy. The case reaches `executing` and no further — `engaged` would mean a counterparty engaged, and none can be reached. Worker handler + `POST /api/cron/recovery-runner` + `POST /api/recovery-cases/{id}/run`. 15 tests. |
| E-23 | Recovery attribution ledger | TESTED | DIRECTIVE 2026-09-16 (E-01 step 10, M-08) | `backend/attribution.py`. Records, per Recovery Case, **what the outcome was** (recovered / lost / pending) and, separately, **what we may claim about causing it**. The basis is derived from evidence, never supplied by the caller: `_derive_basis` returns the strongest claim the record supports, and a basis that depends on outreach having reached someone is refused unless an outbound message exists in `sent` or `delivered`. `outcome_unknown` is explicitly not evidence of delivery, a blocked outbound step earns no credit, and an inbound message predating our first send is not a reply. No provider adapter exists (§8 #26), so `outreach_delivered` and `counterparty_replied` are **unreachable by construction today** and attributed revenue is zero — the summary states this rather than presenting a bare zero. An operator may assert a recovery was ours, with a required reason; the assertion is stored beside the derived basis, never in place of it, and is reported as its own figure. Confirmed and potential value stay separate and are reported per currency, never summed across it. Confirmed value is read only from a recovered case. One entry per case under a unique index. Aggregates per lane, per period, per basis. Reuses the existing domain-event log. Read routes + admin refresh/assert + `POST /api/cron/attribution`. 32 tests. |

### 4.D Capabilities explicitly out of scope

- Restarting or replacing the CRM. (ClickUp `CONTROL — W2` §6, §14.)
- Creating a competing ClientVerse tracker or a second canonical repository. (Repository registry operating rule.)
- Autonomous outbound sales email, unattended production deploys, and silent browser checkouts. (Workforce repo explicit non-goals; they bind any agent capability the CRM consumes.)
- Exposing deep security scanning as a default public feature. (ClientVerse doctrine `04a-governance-metrics-roadmap.md`.) The §6 gate is an internal control plane, not a customer-facing product surface.

---

## 5. Source repository → ClientVerse capability mapping

**Adoption rule:** these are capability donors, adapters, and references. Extract approved architecture, workflows, patterns, controls, and tests. Do not replace ClientVerse with any of them, and do not vendor an entire repository. Every adoption must name what is adapted, what is rejected, and the licence obligation it creates.

Each source carries an explicit disposition. **ADOPT** = take the component itself.
**ADAPT** = re-implement its approach inside ClientVerse. **EXTRACT** = lift specific
patterns only. **WATCH** = no action now, revisit when a dependency clears. **REJECT** =
do not use. No source may be executed or depended upon until it has passed §6, whatever
its disposition here.

| # | Source | Disposition | Donates to | Extract | Explicitly reject |
|---|---|---|---|---|---|
| 1 | `trycompai/crm` | ADAPT | E-04, E-05, E-06 | Durable work-queue model, job lease/retry/dead-letter semantics, scheduled autonomous follow-up patterns, agentic task contracts | Its CRM data model, schema, and UI |
| 2 | `chatwoot/chatwoot` | ADAPT | E-09, E-10, M-01, M-02, M-03, M-09 | Conversation/inbox/contact-channel model, assignment and human-handoff state machine, agent-bot boundary, canned-response and SLA patterns | Running Chatwoot as a service; its Rails stack; its identity model |
| 3 | `ShawnPana/phone-harness` | WATCH | E-08, M-04 | Controlled phone/mobile agent execution harness, action allowlisting, session boundaries, failure containment | Uncontrolled device automation; anything bypassing E-12 or M-07 |
| 4 | `NVIDIA/SkillSpector` | ADOPT | E-12 (Gate 1) | Agent-skill scanning of external skills before trust | Treating a single scanner as sufficient; auto-allow on pass |
| 5 | `cisco-ai-defense/skill-scanner` | ADOPT | E-12 (Gate 2A) | Independent agent-skill scanning | Collapsing Gate 2A and Gate 1 into one scan |
| 6 | `cisco-ai-defense/mcp-scanner` | ADOPT | E-12 (Gate 2B) | MCP server/tool scanning, tool-poisoning and description-injection detection | Applying MCP scanning to non-MCP skills and calling the gate satisfied |
| 7 | `smicallef/spiderfoot` | WATCH | E-13 | OSINT enrichment modules, source attribution, per-module opt-in, rate/consent controls | Unbounded scanning; enrichment without lawful basis; storing raw OSINT against a contact without provenance |
| 8 | `every-app/open-seo` | EXTRACT | E-14 | SEO/growth intelligence signal extraction and reporting patterns | Publishing or mutating a client's site from the CRM |
| 9 | `browser-use/video-use` | EXTRACT | E-15 | Agent video capability and generation/return-path patterns | Unattended publication of generated media |
| 10 | `twentyhq/twenty` | EXTRACT | E-17, C-03…C-05 refinements | CRM product patterns and UX: record-page composition, view/filter model, keyboard-first navigation, data-table ergonomics | Code copy, schema adoption, any runtime dependency |
| 11 | `n8n-io/n8n` | ADOPT | E-18, M-06 | Automation/orchestration patterns; execution-edge workflow transport (the workforce repo already proves the Slack→workforce→Slack path) | n8n as the system of record; orchestration logic that bypasses CRM approvals or tenancy |
| 12 | `facebook/docusaurus` | EXTRACT | Documentation architecture | Versioned documentation IA, ordered doc sets, audience separation | Migrating this governing document out of the repository |
| 13 | **DodoNote / meeting-intelligence source** | BLOCKED | E-16, M-05 | Meeting capture, transcription, summary, action-item extraction, CRM write-back | — |


**Disposition rationale.** ADAPT for #1 and #2: both are whole products with their own
data models, so ClientVerse takes the approach (durable job semantics; the conversation
and handoff state machine) and not the system. ADOPT for #4–#6: the scanners are used as
scanners, exactly what §6 requires, and are the only sources intended to be run rather
than read — which is why they are also the ones gated behind owner blockers O-13 and O-14.
ADOPT for #11: n8n is an execution edge behind a CRM-side contract, never the system of
record. WATCH for #3 and #7: both are blocked on an owner decision (telephony and consent
policy, O-06; OSINT lawful basis, O-07) and no work should start until those clear.
EXTRACT for #8–#10 and #12: patterns only, no dependency, no code copy. BLOCKED for #13:
the source is unresolved (§7.1, O-10) so no disposition can honestly be assigned yet.

**Source #13 is unresolved. `SOURCE URL UNRESOLVED — OWNER CONFIRMATION REQUIRED`** — see §7.1.

---

## 6. Mandatory external-component security architecture

Any external **agent skill, MCP server, MCP tool, agent plugin, or external agent package** must complete this pipeline before it is eligible for production use. This is a hard gate, not a recommendation.

```
EXTERNAL SOURCE
      |
      v
NVIDIA SkillSpector                     (Gate 1 — agent-skill scan)
      |
      v
Cisco Skill Scanner  OR  Cisco MCP Scanner   (Gate 2A / Gate 2B, as applicable)
      |
      v
SECURITY REVIEW RESULT
      |
      v
ALLOW  /  BLOCK  /  OWNER REVIEW
```

**Binding rules**

1. The pipeline must **not** be collapsed to a single scanner. NVIDIA and Cisco are both approved layers and both must run.
2. Gate 2 routing: a skill/plugin/package goes to Cisco Skill Scanner; an MCP server or MCP tool goes to Cisco MCP Scanner. A component that is both is scanned by both.
3. Every decision is recorded with: component identity and version/digest, source URL, both scanner versions, both raw results, reviewer, decision, timestamp, and expiry. `BLOCK` and `OWNER REVIEW` are terminal until re-run.
4. A component that has not completed the pipeline **cannot be added to any tenant MCP allowlist** and cannot be invoked by any agent capability.
5. Re-scan on every version change. A passed scan does not transfer across versions.
6. `ALLOW` makes a component *eligible*; per-tenant allowlisting and approval level (C-11) still govern actual invocation.
7. The gate is an internal control plane. It is not exposed as a customer-facing feature (§4.D).

**Current state:** the pipeline above is implemented and tested (`backend/security_gate.py`,
E-12 in §4.C): intake, both gates, the state machine, version-and-digest-bound decisions
with expiry, and enforcement on `POST /api/mcp/invoke`. Intake routes exist at
`/api/security-gate/components`.

Two limits are real and deliberate. **No scanner is wired** (owner blockers O-13 and
O-14), and the gate refuses every approval while a required scanner is unconfigured, so
nothing can currently be approved — the safe default. **Scanner results are
operator-attested**: a reviewer records that a scan ran, which the gate stores and
requires, but cannot yet verify. Once the scanner endpoints exist, results must be
fetched from the scanner and bound to source, version and digest rather than accepted
from the caller. Until then no external component should be treated as trusted on the
strength of a recorded result alone.

---

## 7. Unresolved source references and provenance gaps

### 7.1 DodoNote / meeting-intelligence source — `SOURCE URL UNRESOLVED — OWNER CONFIRMATION REQUIRED`

The exhaustive audit in §0.4 found **no occurrence** of "DodoNote" (any casing) in: all 31 refs and full commit history of `Clientverse-crm`; `Clientverse-AI-AGENT-Workforce` (`main` + `ai-wos-v2`); `clientverse`; `clientverse-website-audit`; any GitHub issue, PR, or comment; any ClickUp task or doc; any Slack message. The **capability** (meeting intelligence) is recovered and approved from ClickUp `CONTROL — W2` §10; only the **source repository** is unresolvable. Owner must supply the exact repository URL before E-16 leaves the contract stage.

### 7.2 Provenance conflict on the security-gate tooling

- The 2026-09-15 directive states the NVIDIA + Cisco dual gate is **approved**.
- The only earlier ClientVerse record naming any of this tooling is Slack `#life-os-command-center`, 2026-09-13: *"Tool candidates remain unapproved until verified: NVIDIA SkillSpector, GraphAI-fy/Graphify capability implementation, Token Optimizer MCP, Omni routing component."*

The same message makes a **"third-party intake/security gate"** a mandatory addition to the AI Project Governance Blueprint v2, so the *architecture* is corroborated while the *specific tools* were explicitly unapproved two days earlier. The later owner instruction governs, so E-12 is carried as approved — but the earlier record is preserved here and the tools should be verified before they are trusted, consistent with that record's own standard.

### 7.3 Source repositories 1–12 have no prior approval record

None of `trycompai/crm`, `chatwoot`, `phone-harness`, `SkillSpector`, `skill-scanner`, `mcp-scanner`, `spiderfoot`, `open-seo`, `video-use`, `twenty`, `n8n-io/n8n`, or `docusaurus` appears anywhere in the ClientVerse repositories, issues, PRs, ClickUp, or Slack. Their approval of record is the **2026-09-15 directive itself**. The *capability areas* they serve are largely recoverable (§4.C provenance column); the *repository selections* are new to the record. This is stated rather than papered over, because the directive's own rule is to recover exact approved behavior first and not to invent.

### 7.4 Gmail not searched

The Gmail connector was unauthenticated for this session. If an approval thread for the expansion scope exists only in email, it was not reachable. Owner re-authorization would let this audit be completed against that channel.

### 7.5 "September 12 CRM modernization blueprint" not located

ClickUp `CONTROL — W2` §7 and the Slack closeout of 2026-09-13 both instruct agents to "implement the September 12 blueprint." Its five established principles are quoted in that control and are carried into §9 of this document. **The blueprint document itself was not found** in any repository, ClickUp task or doc, or Slack message. The CRM work packages that reference it (PRs #21–#25, labelled `P3-UI-*`, `T6`, `CONTINUE-001 Stream E`) imply a work-package plan that is not in the record either. If that document exists outside these systems, supplying it may add specificity to §4.B and §9; nothing in this document depends on it.

---

## 8. Missing implementation items

Concrete build items, by capability. Items struck through and marked **DELIVERED** have
been built since this list was first written; everything not so marked does not exist.

**Foundations (block most expansion work)**
0. ~~Source-agnostic recovery intake~~ — **DELIVERED** (`backend/recovery_case.py`; see E-21). The recovery engine no longer requires a CRM record to exist before an opportunity can be represented. The existing detectors, and any future missed-call, web-enquiry, quote, appointment or external-CRM source, converge on one normalized event and one Recovery Case before planning. (E-21)
1. ~~`Conversation` domain model — tenant-scoped thread, participants, channel, direction, consent state, assignment, status~~ — **DELIVERED** (`backend/conversations.py`; see M-02). Adds the agent/human boundary E-10 requires to be visible, provider-thread deduplication so a replayed webhook cannot fork a thread, and an inbound path that reopens a closed conversation. Consent starts `unknown`: no record means no permission, never assumed permission. (M-02, E-09)
2. ~~`CommunicationMessage` model + provider-agnostic delivery/receipt interface~~ — **DELIVERED** (`backend/conversations.py`; see M-01, M-03). An explicit message state machine, a `ChannelProvider` protocol with a per-channel registry, and one delivery choke point that checks — in order — that the message is dispatchable, the channel is authorised, consent is granted, an M-07 approval exists and is claimed for exactly this message, and a provider is registered. Each failure is a named refusal recorded on the message. A provider call that is rejected and one that times out after acceptance are **separate states** — `failed` and `outcome_unknown` — because only the first is safe to retry; an unknown outcome is resolved by reconciling against the provider, never by sending again, and adapters receive a dispatch idempotency key. **The application registry is empty**: no provider adapter has been built or certified, so every outbound attempt refuses today. Receipt and inbound paths exist so an adapter added later has somewhere to deliver into. (M-01, M-03)
3. ~~Durable work-queue service~~ — **DELIVERED** (`backend/work_queue.py`; see E-05). Persisted items, lease with crash recovery, attempt counter, capped exponential backoff, dead-letter, database-enforced idempotency key, dedupe key, round-robin per-tenant fairness, admin replay. (E-05)
4. Scheduler contract — **partially delivered**: durable jobs now survive redeploys and record every attempt, and five new authenticated cron entry points exist (`/api/cron/work-queue`, `/api/cron/second-chance`, `/api/cron/next-best-actions`, `/api/cron/recovery-strategies`, `/api/cron/approval-expiry`, all idempotent per delivery id and documented in `docs/RAILWAY_RUNBOOK.md`). Misfire detection and a first-class schedule record remain open. (E-06, still needs O-03)
5. ~~Recommendation service v1~~ — **DELIVERED** (`backend/next_best_action.py`; see NBA-1). Explainable facts, cited source records, priority bands, and accept/dismiss/complete/snooze feedback with outcome; Command Center and `/operations` aggregate queues. (M-11, E-07)
6. ~~Approval queue service as a first-class module surface, reusing C-09 primitives~~ — **DELIVERED** (`backend/approval_queue.py`; see M-07). Bound actions, single-use consumption, expiry, deduplication, requester provenance, risk tiers and a decision history, all on C-09's own collection. `POST /api/approvals`, the `PATCH /api/approvals/{id}` decision route and MCP level-2 writes now run through it, so there is one gate rather than two. Operator surface at `/operations`. (M-07, E-10)

**Second Chance family**
7. Recovery-candidate detector — **stalled lead and missed follow-up DELIVERED** (`backend/second_chance.py`). Dormant/lost-opportunity re-engagement and missed call (requires #12) remain open. (E-01…E-04)
8. ~~Recovery strategy composer: authorized-context gathering, account/history evaluation, strategy recommendation with rationale~~ — **DELIVERED** (`backend/recovery_strategy.py`; see E-20). Authorised CRM context only, an ordered playbook with named rules, facts cited to their source record, per-step channel authority derived from the tenant's own integration records, and an M-07 approval request per proposal. Composition sweep at `POST /api/cron/recovery-strategies`. (E-01 steps 2–4)
9. ~~Recovery campaign runner on the durable queue, with approval gate before any outbound step~~ — **DELIVERED** (`backend/recovery_runner.py`; see E-22). Executes internal steps, drafts outbound steps with their own approval, and stops at the provider boundary. (E-01 steps 5–6, 9)
10. Reply/meeting/decision/task return path into CRM objects. (E-01 step 8)
11. ~~Recovery attribution ledger: recovered / lost / pending revenue per candidate, per lane, per period~~ — **DELIVERED** (`backend/attribution.py`; see E-23). Records outcome and attribution basis separately, and refuses to attribute a recovery to outreach that was never delivered. Attributed revenue is zero today because no message has ever been sent, and the ledger says so. (E-01 step 10, M-08)

25. Fold the Gmail sync mirror (`crm_communications`) into `Conversation` / `CommunicationMessage`. The sync writes a read-only inbound mirror that predates the conversation model and is not threaded, consent-aware or outbound-capable; the two are not yet one store. (M-01, M-02)
26. Channel provider adapters implementing `conversations.ChannelProvider` — one per channel, each behind its own authorisation. Nothing implements the protocol today. (M-01, M-03, O-01, O-06)

**Channels and execution**
12. Call activity capture + telephony provider adapter behind a consent/recording/jurisdiction policy. (M-04, E-08, unblocks E-02)
13. Phone agent execution harness with action allowlist, session boundary, and containment. (E-08)
14. Unified inbox surface with assignment, human handoff, and a visible agent/human boundary. (M-02, E-10)
15. Calendar event service + meeting capture/transcription/summary/action-item extraction with CRM write-back. (M-05, E-16 — source blocked, §7.1)

**Intelligence**
16. OSINT enrichment service: per-module opt-in, lawful-basis record, source attribution, rate limiting, provenance on every stored field. (E-13)
17. SEO/growth intelligence signal service and contextual action surface. (E-14)
18. Video generation capability with human approval before any client-visible use. (E-15)

**Governance and orchestration**
19. ~~External-component intake registry + the §6 dual-gate pipeline, with decision records and version-scoped expiry~~ — **DELIVERED** (`backend/security_gate.py`). Scanner integration itself remains owner-blocked (O-13, O-14). (E-12)
20. ~~Extension of the MCP invoke path to require a passing gate record~~ — **DELIVERED**: `POST /api/mcp/invoke` calls `security_gate.assert_executable` for any tool marked external. Built-in ClientVerse tools ship with the application and are exempt by construction. (E-12 ↔ C-11)
21. Agent workforce contract: CRM ↔ `Clientverse-AI-AGENT-Workforce` boundary — task submission, run status, evidence return, approval callback, tenancy propagation. (E-11)
22. n8n execution-edge contract: signed, idempotent, tenant-scoped CRM webhooks in and out; no orchestration logic that bypasses CRM approvals. (E-18, M-06)
23. Slack and ClickUp handoff adapters in the CRM, replacing the catalog-only `Slack Notifier` record with a real integration behind the registry health model. (E-19)

**Release and honesty**
24. Exact-head CI + deployment evidence for the current `main`, and production exposure of the runtime SHA. (§3.1, §3.2)
25. Two-company production tenant-isolation smoke on the current approved release. (ClickUp §8)
26. Every new surface registered in `CLIENTVERSE_MODULES` with a truthful state before its route ships. (§1.3)

---

## 9. Exact implementation order

Carried forward from the September 12 principles recorded in ClickUp `CONTROL — W2` §7: preserve the current architecture; modernize UI inside the existing stack; deepen incomplete workflows rather than restart; build missing modules only behind explicit contracts; use non-overlapping agent work packages with tests and QC.

**Wave 0 — Release truth (must precede new feature work)**
1. Exact-head CI evidence for `main@3f14347`; redeploy and certify the current release. → §8 #24
2. Two-company production tenant-isolation smoke on that release. → §8 #25
3. Expose the runtime SHA on `/api/health` in production (code already merged at `3706c7a`). → §3.2

**Wave 1 — Foundations**
4. ~~Durable work-queue service~~ — **DONE** (MERGED at `main@3150530`, awaiting deploy). → §8 #3
5. Scheduler contract — **partially done**; misfire detection outstanding. → §8 #4
6. Approval queue module surface. → §8 #6
7. ~~Recommendation service v1 + Command Center aggregate NBA queue~~ — **DONE** (MERGED). → §8 #5

**Wave 2 — Second Chance, lowest-dependency lanes first**
8. ~~Recovery-candidate detector for stalled leads (E-03) and missed follow-ups (E-04)~~ — **DONE** (MERGED). → §8 #7
9. Recovery strategy composer. → §8 #8
10. Recovery campaign runner with mandatory approval gate. → §8 #9
11. Attribution ledger (E-01 step 10). → §8 #11

**Wave 3 — Conversations and human handoff**
12. `Conversation` + `CommunicationMessage` models. → §8 #1, #2
13. Email and SMS channel modules. → M-01, M-03
14. Unified inbox with assignment and human handoff. → §8 #14
15. Reply/meeting/decision/task return path (closes the Second Chance loop). → §8 #10

**Wave 4 — Governance gate (mandatory before any external component is ingested)**
16. ~~External-component intake registry + §6 dual-gate pipeline~~ — **DONE** (MERGED); scanner wiring is owner-blocked (O-13, O-14). → §8 #19
17. ~~MCP invoke requires a passing gate record for external tools~~ — **DONE** (MERGED). → §8 #20

**Wave 5 — Agent workforce and orchestration**
18. CRM ↔ workforce contract. → §8 #21
19. n8n execution-edge contract. → §8 #22
20. Slack / ClickUp handoff adapters. → §8 #23

**Wave 6 — Phone**
21. Consent/recording/jurisdiction policy (owner decision, see O-06). → §10
22. Call activity capture + telephony adapter. → §8 #12
23. Phone agent execution harness. → §8 #13
24. Missed-call recovery lane (E-02) joins the Second Chance detector. → §8 #7

**Wave 7 — Intelligence and media**
25. Meeting intelligence (E-16) — gated on §7.1 source resolution. → §8 #15
26. SEO/growth intelligence (E-14). → §8 #17
27. Video agent (E-15). → §8 #18
28. OSINT enrichment (E-13) — gated on lawful-basis review (O-07). → §8 #16

**Continuous — Twenty-derived UX refinements (E-17)**
Fold pattern improvements into whichever wave touches the relevant surface. Never as a standalone rebuild.

---

## 10. Dependencies and owner-only blockers

### 10.1 Capability dependencies (hard)

| Capability | Requires |
|---|---|
| E-01 Second Chance | E-05, M-07, M-11 and E-20 are delivered; it still needs at least one **authorised** outbound channel (M-01 or M-03), which is an owner decision |
| E-02 Missed-call recovery | E-08 → M-04 → owner telephony + consent decision (O-06) |
| E-03 Stalled-lead recovery | E-05 only — **no new external dependency** |
| E-04 Missed-follow-up recovery | E-05 + existing C-06 |
| E-06 Scheduled agent follow-up | E-05 + §8 #4 + M-07 |
| E-07 Next Best Action | M-11 |
| E-09 Omnichannel | ~~§8 #1, #2~~ delivered → now only M-01/M-03, i.e. a provider adapter and its authorisation (O-01, O-06) |
| E-10 Human handoff | ~~M-02 + C-09~~ — both delivered; `MERGED` |
| E-11 Agent workforce in CRM | §8 #21; workforce repo runtime verification (its own register lists approval gates and durable run store as PARTIAL) |
| E-12 Security gate | Nothing internal — buildable immediately; **must precede** any external-skill/MCP ingestion |
| E-13 OSINT | O-07 lawful-basis decision |
| E-14 SEO, E-15 Video | E-05 for scheduled runs; M-07 for approval before client-visible output |
| E-16 Meeting intelligence | §7.1 source resolution + M-05 + C-17 (Google Calendar certification) |
| E-18 n8n | §8 #22 + owner-hosted n8n instance (O-08) |
| E-19 Slack/ClickUp handoffs | §8 #23 + workspace app credentials (O-09) |

### 10.2 Owner-only blockers

| ID | Blocker | Exact owner action | Unblocks |
|---|---|---|---|
| O-01 | Google OAuth not configured | Google Cloud: enable Gmail + Calendar APIs, consent screen, OAuth web client with callback `https://<production-origin>/api/integrations/google/callback`; set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` in Railway; authorize a least-privilege test account | C-17, E-16 |
| O-02 | Stripe test credentials absent | Stripe: test-mode restricted key + webhook endpoint `https://<production-origin>/api/integrations/stripe/webhook` for `payment_intent.succeeded\|payment_failed\|canceled`; set `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET` | C-18, M-08 |
| O-03 | No external scheduler | **Reduced to two repository secrets.** `.github/workflows/scheduled-jobs.yml` now drives every cron endpoint on the documented cadences; the owner only adds `CLIENTVERSE_PRODUCTION_URL` and `WEBHOOK_CRON_SECRET` under repository secrets. With either missing the workflow exits cleanly without calling anything. A dedicated scheduler may replace it; disable the workflow if so. **Until the secrets exist the durable queue has no worker in production and recovery candidates are only produced on demand.** | C-08, C-16, E-03, E-04, E-05, E-06, NBA-1 |
| O-04 | Admin credential rotation outstanding | Rotate `ADMIN_PASSWORD` in Railway after first login (`seed()` re-syncs the hash each boot) | Security hygiene |
| O-05 | Legacy secret + variable cleanup | Rotate the preview Stripe webhook secret recoverable from pre-redaction git history; delete the superseded misspelled `Mongo_url` variable | Security hygiene |
| O-06 | Telephony/consent policy undecided | Choose the telephony provider and approve the call consent, recording, and jurisdiction policy | E-08, E-02, M-04 |
| O-07 | OSINT lawful basis undecided | Approve the lawful basis, permitted sources, retention, and provenance requirements for contact enrichment | E-13 |
| O-08 | n8n instance not designated | Designate the n8n instance and its credential boundary | E-18 |
| O-09 | Slack/ClickUp app credentials | Provide workspace app credentials scoped to the CRM integration | E-19 |
| O-10 | Meeting-intelligence source unknown | Supply the exact DodoNote / meeting-intelligence repository URL | E-16 |
| O-11 | AI provider key absent | Provide `EMERGENT_LLM_KEY` (or approve an alternative provider) | C-19, and the AI-assisted parts of E-01 steps 3–4 |
| O-12 | Custom domain / DNS | Choose the domain, authorize DNS, re-register the final Google callback | Production origin finalization |
| O-13 | Security-gate tooling verification | Confirm that the 2026-09-15 approval of NVIDIA SkillSpector and the Cisco scanners supersedes the 2026-09-13 "unapproved until verified" record, and authorize their use | E-12 (§7.2) |
| O-14 | Security-gate scanners not configured | Provide reachable endpoints for `SECURITY_GATE_NVIDIA_SKILLSPECTOR_URL`, `SECURITY_GATE_CISCO_SKILL_SCANNER_URL` and `SECURITY_GATE_CISCO_MCP_SCANNER_URL`. The gate refuses every approval while any required scanner is unconfigured, which is the intended safe default, so no external component can be trusted until this is done. | E-12 execution |
| O-15 | Production is unreachable from the agent environment | None, if the owner is content for deployment to run elsewhere. The session egress policy blocks `railway.app` and `backboard.railway.com`, so production deploy/verify must be run from an environment that can reach Railway (CI, the owner's machine, or a differently-scoped agent session). This is `BLOCKED — TECHNICAL`, not an owner decision. | Current-head deployment and production certification |

Secrets are never to be pasted into GitHub, ClickUp, Slack, chat, logs, or evidence artifacts. Configuration is reported by name and presence only.

---

## 11. What can start immediately

Delivered in the 2026-09-15 execution pass and **merged into `main@3150530`** via PR #26:
the durable work queue, the stalled-lead and missed-follow-up detectors, the Next Best
Action backend service with its aggregate queues, the dual-gate security pipeline with MCP
enforcement, the CI lint gate, and the `/operations` operator surface. Merged, **not
deployed** — see §3.2.

Delivered in the 2026-09-16 pass and **merged into `main@e8d5678`** via PR #27: the
approval queue module surface (M-07), the recovery strategy composer (E-20), the
`Conversation` and `CommunicationMessage` models with their provider-agnostic delivery
interface (M-02, E-10), their operator panels on `/operations`, and two further cron entry
points. Merged, **not deployed** — see §3.2.

Remaining work that needs no owner input and no unresolved source:

1. **Certify `main@e8d5678`** — deploy it, then run `scripts/proof_of_life.mjs` and
   `scripts/operations_smoke.mjs` against production from an environment that can reach
   Railway (O-15). This is now the largest single gap in the programme: three waves of
   capability are merged and **none of it has ever been certified against production**.
   Every capability below `MERGED` in §4 is blocked on this one step, not on more building.
2. **Recovery campaign runner (§8 #9)** — consumes an approved strategy off the durable queue
   and executes only its internal steps, drafting the outbound ones into conversations where
   they wait, correctly, for a channel.
3. **Reply/decision return path (§8 #10)** — turning an inbound reply, meeting or decision
   back into CRM objects. The inbound path now exists to hang this on.
4. **Fold the Gmail sync mirror into conversations (§8 #25)** — one store rather than two.
5. **Attribution ledger (§8 #11)** — closes the north-star loop for recovered/lost/pending revenue.
6. **Scheduler misfire detection (§8 #4)** — completes the scheduler contract.
7. **Twenty-derived UX refinements (E-17)** on surfaces already being touched.

What is **not** on that list, deliberately: a channel provider adapter (§8 #26). Writing one
needs a provider decision and its credentials (O-01 for email, O-06 for telephony), so it is
owner-blocked rather than agent-blocked.

**Recommendation:** merge and certify first (item 1), then item 2. Steps 1–4 of the north
star exist end to end and stop, correctly, at a gate. The runner can carry steps 5–6 as far
as a drafted, approved message sitting in a conversation; the last hop out of the CRM waits
on an owner decision, not on more building.

## 12. Status control and evidence rules

1. Every capability in §4 carries **exactly one** status from the vocabulary in §4.
2. **Only `LIVE VERIFIED` is complete.** A capability is never called complete because it was researched, because a source repository was selected, because a prompt was written, because code exists locally, because a PR exists, or because unit tests passed.
3. `DEPLOYED` applies to a **specific commit**. It does not transfer to a later commit. Each release re-certifies.
4. Mocked, contract, and unit tests never substitute for live provider certification.
5. Missing evidence means **UNVERIFIED**, never assumed-passing.
6. Execution and inspection are separate functions; independent QC may reject a completion claim.
7. Status reporting to GitHub Issue #10 uses exactly three sections: `COMPLETED`, `BLOCKED`, `EXACT OWNER INPUT REQUIRED`.
8. When status changes, **update this document in place** and reconcile ClickUp `CONTROL — W2`. Do not create a competing tracker or a disconnected addendum.

---

## 13. Definition of done for the CRM program

ClientVerse CRM is closed only when all of the following hold:

- production runs the approved current code, with exact-head CI and runtime-SHA parity evidence;
- the UI modernization in §1.3 is shipped and QC-passed;
- Google / Gmail / Calendar live flows are certified;
- Stripe test-mode and webhook flow are certified;
- the scheduler is operational;
- a two-company tenant-isolation production smoke passes;
- the Second Chance north-star workflow (§1.2) runs end to end in production with approval gates enforced and attribution recorded;
- every external skill/MCP in use carries a passing §6 dual-gate decision record;
- the agent workforce experience is credible and operational where in scope;
- the website → lead/demo/CRM conversion path works;
- no P0/P1 blocker remains;
- evidence is recorded against this document and ClickUp `CONTROL — W2`.

---

## 14. Change log

| Version | Date | Change |
|---|---|---|
| 1.10 | 2026-09-16 | Added the recovery attribution ledger (E-23), closing §8 #11 and the ATTRIBUTE stage of the loop. The design question this slice exists to answer is not "what was recovered" — the Recovery Case already knows — but "what may we claim to have caused". Those are recorded as separate fields, and the second is derived from evidence rather than accepted from the caller: a basis requiring delivered outreach is refused unless a message reached `sent` or `delivered`. Since no channel provider is registered, attributed revenue is zero by construction, and the summary states that rather than presenting an unexplained zero. Confirmed and potential value stay separate and per-currency throughout. Backend suite **540 passed, 4 skipped** (508/4 before; +32, no regressions). Still nothing sent. |
| 1.9 | 2026-09-16 | Reconciled with the merge of PR #28 (`main@730b1b3`, squash-merged 23:31Z). E-21 and E-22 move from `TESTED` to `MERGED`; §3.1 records the merged head and the branch restart. The merged head was re-verified in a clean local environment — backend **508 passed, 4 skipped** — rather than inheriting the pre-merge branch result. `MERGED` is still not `DEPLOYED`: `ca30587` (2026-09-01) remains the only production-certified head. |
| 1.8 | 2026-09-16 | Worked the PR #28 review in full. Nine posted and six suppressed findings were verified against the code and fixed, not deflected. The material ones: `attach()` tenant-checked only the four CRM references, so a plan, approval, conversation or work item belonging to another tenant could be stapled onto a case — all eight attachable references are now checked; `confirm_recovery()` wrote the state and the amount separately, and a failure between them left a case terminal with nothing recorded and no legal transition back — it is one conditional write now; `float()` admitted `nan` and the infinities past the `< 0` check, which would have made every value aggregate non-finite; `source_event_id` was truncated to 200 characters *before* the unique index, so two distinct events sharing a prefix deduplicated into one case; `summary()` summed value across currencies, reporting £40,000 + $40,000 as 80,000; `compose_for_tenant` swept only the work queue, so a case-only source — the missed call this slice exists for — was never planned for in production; and a folded work item kept the case link only in memory. Corrected two overclaims in §3.1 of this document: `ca30587` *has* been deployed to production (2026-09-01, §3.2), and PR #28 is open unmerged work. Backend suite **508 passed, 4 skipped** (475/4 before; +33, no regressions). |
| 1.7 | 2026-09-16 | Added the recovery runner (E-22): the first stage that acts on an approval. Internal steps execute; outbound steps are drafted, given their own approval carrying the exact text, and refused at the provider boundary. Idempotent per case and per step, so a durable-queue redelivery cannot produce a second message. §8 #9 struck through. Backend suite 475 passed, 4 skipped (460 before; +15, no regressions). Still nothing sent: `outbound_sent` is 0 by construction and stated in the runner's own result. |
| 1.6 | 2026-09-16 | Phase 1 of the Revenue Recovery Platform directive. Added the Recovery Case and the normalized recovery-event contract (E-21), removing the architectural requirement that every recovery opportunity originate as an internal CRM record. Existing dormant-deal and missed-follow-up detection is preserved and now also emits cases; the planner gained a boundary that accepts a case with no CRM context. Potential value and confirmed recovered revenue are separate fields with separate provenance, and confirmation requires evidence. Backend suite 460 passed, 4 skipped (baseline 432/4; +28, no regressions). Nothing here executes, sends or attributes — those stages remain as recorded in §8. |
| 1.5 | 2026-09-16 | Reconciliation with the squash-merge of PR #27 into `main@e8d5678`. M-02, M-07, E-10, E-20 and C-26 move from `TESTED` to `MERGED`, and C-24's note about panels "not yet merged" is corrected. §3.1 records the new head and the evidence it was verified against; §3.4 records PR #27 closed and no CRM pull request open; §11 re-orders so that certifying a deployed head is item 1. No capability moves to `DEPLOYED` or `LIVE VERIFIED`: three waves are now merged and none has ever been certified against production (O-15). |
| 1.4 | 2026-09-16 | Omnichannel foundation. Added `backend/conversations.py`: the tenant-scoped `Conversation` thread (participants, channel, status, assignment, the visible agent/human boundary, a per-channel consent record that starts `unknown`, provider-thread deduplication, and an inbound path that reopens a closed thread) and the `CommunicationMessage` model with an explicit state machine that separates a proven provider rejection from an unobserved outcome, so a lost response can never become a duplicate message to a client. Added the provider-agnostic delivery interface — a `ChannelProvider` protocol, a per-channel registry, and one choke point that checks dispatchability, channel authority, consent, a claimed M-07 approval and a registered provider, recording a named refusal for each failure. The application registry is empty, so every outbound attempt refuses today and says why. Added `approval_queue.refresh_blocks` so a prerequisite that has since been resolved stops refusing forever, while remaining unable to revive a rejected, cancelled or lapsed request. Consolidated every approval decision path — the legacy `PATCH /api/approvals/{id}`, the queue decision route and the cancel route — onto one follow-through hook. M-02 and E-10 move to `TESTED`; M-01 and M-03 move to `BLOCKED — OWNER INPUT` because their model is built and only a provider adapter and its authorisation are missing; E-09 stays not started because omnichannel means channels. §8 gains two honest follow-on items (#25 folding the Gmail sync mirror into conversations, #26 the provider adapters). 40 new tests (backend suite 416 passed, 4 skipped). |
| 1.3 | 2026-09-16 | Wave 2 execution pass. Added the approval queue module surface (M-07, `backend/approval_queue.py`) built on C-09's own `approvals` collection rather than beside it: bound actions, single-use consumption, expiry on read as well as by sweep, database-enforced deduplication, requester provenance, risk tiers, optional separation of duties, and a decision history. `POST /api/approvals`, `PATCH /api/approvals/{id}` and MCP level-2 writes were re-pointed at it so one state machine governs every approval, and both decision routes now share one follow-through. Added the recovery strategy composer (E-20, `backend/recovery_strategy.py`): authorised CRM context only, an ordered playbook of named lanes, facts cited to their source record, per-step channel authority derived from the tenant's own integration records, and an approval request per proposal. Added `/api/cron/recovery-strategies` and `/api/cron/approval-expiry` and wired both into the scheduled-jobs workflow. Added the Recovery strategies and Approvals panels to `/operations` and moved the `approvals` module out of `contract_pending`. Restated E-01: steps 1–4 of the north star exist, steps 5–10 do not, so the umbrella capability stays `APPROVED — NOT STARTED`. 71 new tests (backend suite 371 passed, 4 skipped). Reconciled §3 and §4 with the squash-merge of PR #26 into `main@3150530`: the Wave-1 capabilities (E-03, E-04, E-05, E-07, the E-12 pipeline, C-23) move from `TESTED` to `MERGED`, which is still not `DEPLOYED`. |
| 1.2 | 2026-09-15 | Review-remediation pass on PR #26. Fixed concurrency defects in the durable queue (lease ownership on terminal transitions, atomic recovery, in-flight lease renewal, database-enforced deduplication, starvation-free tenant rotation, operator/worker resolve race); made cron deliveries releasable so a crashed job is retried rather than lost, and gave each tick a distinct worker identity; bound security-gate identity and enforcement to the content digest and made a re-scan re-open review; stopped a failed Next Best Action rule from retiring valid recommendations, moved the health rule onto the canonical health snapshot, and made generation upsert atomically; removed an N+1 scan from detection and indexed the lookup it performs. Rewrote the operations smoke to run in disposable tenants with asserted seeds — the previous evidence passed while two seeds were rejected with HTTP 422, so it proved less than claimed. |
| 1.1 | 2026-09-15 | Execution pass. Reduced O-03 from "choose and wire a scheduler" to two repository secrets by adding `.github/workflows/scheduled-jobs.yml`. Recorded verified evidence for `main@3f14347` and the work branch. Moved E-03, E-04, E-05, E-07/NBA-1 and the E-12 pipeline to `TESTED`; added C-23 (CI lint gate). Corrected two further completion claims: CI never ran the documented lint gate, and Next Best Action was previously described as delivered when only a client-side strip existed. Added owner blockers O-14 (scanners unconfigured) and O-15 (production unreachable from the agent environment), and expanded O-03 with the three new cron entry points. |
| 1.0 | 2026-09-15 | Initial canonical replacement. Merged `memory/PRD.md`, `docs/CLIENTVERSE_PRODUCT_COMPLETION_BRIEF.md`, `docs/UX_SYSTEM_IMPROVEMENTS_ASSESSMENT.md`, `docs/REMAINING_WORK.md`, `todo.md`, `AGENTS.md` closeout state, ClickUp `CONTROL — W2`, and Slack canvas `F0BPNUF7VK3` into one governing document. Added the recovered expansion capability register (§4.C), source-repository mapping (§5), the mandatory dual-gate security architecture (§6), unresolved source references (§7), implementation order (§9), dependencies and owner blockers (§10). Corrected six completion claims that evidence does not support (§3.3). |
