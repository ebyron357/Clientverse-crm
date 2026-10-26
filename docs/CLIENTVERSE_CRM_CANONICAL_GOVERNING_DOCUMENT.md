# ClientVerse CRM — Canonical Governing Document

**Version:** 1.29 — complete replacement
**Effective:** 2026-10-26
**Owner/admin handoff guide:** [`docs/CLIENTVERSE_CRM_OWNER_ADMIN_MANUAL.md`](CLIENTVERSE_CRM_OWNER_ADMIN_MANUAL.md) — the official owner/admin source of truth for operating production (§0.5)
**Status:** ACTIVE — this is the single source of truth for ClientVerse CRM product scope, capability status, and implementation order.
**Repository:** `ebyron357/Clientverse-crm`
**Baseline commit at issue:** `main@3f14347610e5ca6cd8521c74f4420d3b2c08a9e8` (PR #24 merged 2026-09-15T18:19Z)
**Running application code at this revision:** `main@6d0d4c6` (PR #48, the closeout release; production reported this `git_sha` on 2026-10-24 — §3.2). Earlier heads: `394f095` (PR #46), `4873f67` (PR #45), `de1277e` (PR #44), `838f00d` (PR #42), `1a39fa4` (PR #41), `b854059` (PR #38), `9bd9723` (PR #37), `c9f5a6e` (recovery-engine activation merge, 2026-09-28), `730b1b3` (PR #28), `e8d5678` (PR #27), `3150530` (PR #26)

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
| Owner-facing instructions in `docs/OWNER_HANDOFF.md` (§2, §5, §8, §10), `docs/ACTIVATION_REPORT.md` ("Administrator Access", "Owner Actions Required"), `docs/RAILWAY_RUNBOOK.md` (§6, and the password text in §7), `docs/PRODUCTION.md`, `docs/DEPLOYMENT_GUIDE.md`, `docs/GOOGLE_PROVIDER_CERTIFICATION.md`, `docs/STRIPE_PROVIDER_CERTIFICATION.md`, `docs/RELEASE_CERTIFICATION.md`, `docs/VALIDATION_EVIDENCE.md`, `docs/closeout/OPENHANDS_PRODUCTION_CERTIFICATION.md`, `docs/RENDER_ATLAS_RUNBOOK.md` and `docs/HOSTING_SELECTION.md` (the last two Render-era, whole document), plus `SECURITY.md` and `README.md` (2026-09-30) | **Superseded for owner use** by [`docs/CLIENTVERSE_CRM_OWNER_ADMIN_MANUAL.md`](CLIENTVERSE_CRM_OWNER_ADMIN_MANUAL.md) (§0.5). The twelve `docs/` files carry a banner pointing to the manual. `README.md`, `SECURITY.md` and the stale scheduler and password text in `docs/RAILWAY_RUNBOOK.md` were corrected in place. All are retained as engineering and evidence records. |

### 0.2 Authority order

1. This document — CRM product scope, capability status, implementation order.
2. ClickUp `CONTROL — W2` — program-level operational status and owner gates.
3. GitHub (`main`, CI, PRs, Issue #10) — engineering and evidence truth.
4. `docs/RAILWAY_RUNBOOK.md`, `docs/PRODUCTION.md` — deployment/runbook mechanics.
5. [`docs/CLIENTVERSE_CRM_OWNER_ADMIN_MANUAL.md`](CLIENTVERSE_CRM_OWNER_ADMIN_MANUAL.md) — **the official owner/admin handoff source of truth**. It covers how the owner reaches, signs in to, operates, administers, verifies, recovers and escalates the production CRM. For owner procedures it outranks every other document. On capability status it must agree with this document: where the manual records a newer verified production fact, this document is updated in the same change (§0.5).

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

### 0.5 Owner/admin handoff guide (2026-09-30, re-verified 2026-10-19)

[`docs/CLIENTVERSE_CRM_OWNER_ADMIN_MANUAL.md`](CLIENTVERSE_CRM_OWNER_ADMIN_MANUAL.md) (v1.13, Issue #33) is the **official owner/admin handoff source of truth**. Since 2026-10-24 it is Part 2 of the closeout package; Part 1 is [`docs/closeout/CLIENTVERSE_CRM_CLOSEOUT_HANDOFF.md`](closeout/CLIENTVERSE_CRM_CLOSEOUT_HANDOFF.md) (environment, configuration, operations, tests, owner actions). `python scripts/build_closeout_docs.py` generates the Word and Markdown package from the two. It is the one place a non-technical owner is sent for:

- production and sign-in addresses
- the supported sign-in method, lockout and recovery
- every active module and how to use it
- Google/Gmail connect, re-authorize and `gmail.send` verification
- the email send and reply verification procedure (PASS / FAIL / BLOCKED)
- users, roles and invitations
- integrations truth
- scheduler health
- the troubleshooting matrix
- the production verification checklist
- escalation and evidence rules

Rules:

1. **One manual.** Owner/admin instructions are maintained only there. Other documents that once gave owner instructions carry a banner pointing to it (§0.1). A new owner procedure is added to the manual, not to a new file.
2. **Verified against the running code and production.** Every screen label, route, scope, cron job and sign-in rule in the manual was checked against `main@8f23f63` and Railway and GitHub Actions records on 2026-09-30, and re-checked against `main@838f00d` and Railway records on 2026-10-19 (manual v1.1). Anything that could not be confirmed is marked `UNVERIFIED — OWNER/ENGINEERING INPUT REQUIRED`.
3. **Kept true with the code.** A change that alters a screen label, route, sign-in rule, Google scope, scheduler job or owner procedure updates the manual in the same change.
4. **Project Completion Standard coverage.** The manual covers the owner-facing content that [`docs/PROJECT_COMPLETION_STANDARD.md`](PROJECT_COMPLETION_STANDARD.md) expects in `ADMIN_OPERATIONS_MANUAL.md`, `CLIENT_USER_MANUAL.md` and `TROUBLESHOOTING_AND_SUPPORT.md`. Those are deliberately not separate files, so there are no overlapping fragments. The standard's other handoff files — closeout status, security/access handoff, deployment/recovery runbook, data lifecycle/offboarding, client access template and final acceptance — remain to be produced or marked `NOT APPLICABLE` in a closeout status file.

---

## 1. Product definition and non-negotiables

### 1.1 What ClientVerse CRM is

ClientVerse CRM is the **AI-native client operations platform** for the complete customer lifecycle — **WIN → ONBOARD → SERVE → RETAIN → EXPAND** — operated as one commercial program with the `clientverse.io` public website. The website sells the promise; the CRM must visibly prove it. Neither is commercially closed in isolation.

**Owner directive 2026-10-19 — market and scope.** ClientVerse is a CRM for any business, not one industry. It competes with Salesforce, HubSpot, Zoho CRM, Pipedrive, HighLevel, Microsoft Dynamics 365 Sales, monday CRM, Freshsales, Close and Attio. Real estate is one industry template among several (agency and services, home services, health and wellness, coaching and consulting, B2B sales), and nothing may assume a real-estate business unless that template is chosen. The owner set the feature scope in §1.5.

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

### 1.5 Owner feature scope (2026-10-19)

The owner's list, verbatim in substance, with each item's status against `main@6d0d4c6` (PR #48), which production reported on 2026-10-24 (§3.2). LIVE = in production; PARTIAL = part of it is in production and the gap is named; MISSING = not built. Phases are the build order (§9 continues to govern the existing waves).

**Must-have CRM features**

| # | Feature | Status | Gap | Phase |
|---|---|---|---|---|
| 1 | Contact, company and customer management | LIVE (C-03, C-05, C-27, C-32) | — | 1 |
| 2 | Lead capture, qualification and assignment | LIVE (C-30, M-05; lifecycle stages C-33; industry forms C-36) | Qualification scoring | 1 |
| 3 | Customizable sales pipelines | PARTIAL (C-04) | More than one pipeline | 2 |
| 4 | Email synchronization and communication history | PARTIAL (C-17, M-02) | Outlook; compose box; forms and bookings in the inbox | 2 |
| 5 | Tasks, reminders and follow-up tracking | LIVE (C-27, E-04) | — | — |
| 6 | Calendar synchronization and appointment booking | PARTIAL (M-05) | Writing bookings back to Google or Outlook | 2 |
| 7 | Workflow automation with stop rules | PARTIAL (C-35 automation builder with user-set stop rules; C-30, E-22, C-15) | Branching; email and text steps through approved templates | 2 |
| 8 | Sales reporting and dashboards | PARTIAL (M-10 recovery proof) | Report builder, dashboards, forecasting | 3 |
| 9 | Custom fields, filters and views | PARTIAL (C-30 form fields; C-33 field manager, server-side filters and saved views) | Saved views on the company and deal lists; sorting by a custom field | 1 |
| 10 | Integrations, API access and webhooks | PARTIAL (C-10, C-11, C-17) | API keys and public docs; Zapier; Slack | 3 |
| 11 | Data import, export and duplicate management | PARTIAL (C-27, C-32; C-39 import screen with field mapping, and full exports, `TESTED` on branch) | Field mapping not yet in production; CRM importers (M-12) | 1–2 |
| 12 | Accessible desktop and mobile interfaces | PARTIAL (new shell: 11-item main menu, Settings hub) | Installable mobile app | 1, 4 |
| 13 | Security, permissions, audit logs and backups | PARTIAL (C-01, C-02, C-13, C-14) | Two-factor login, SSO, finer permissions, tested restore | 3 |
| 14 | Guided onboarding, migration and customer support | PARTIAL (setup checklist; its first step is choosing an industry template, C-36; C-39 spreadsheet import `TESTED` on branch) | Importers from other CRMs, in-app help (M-09) | 2 |

**Features that provide additional value**

| # | Feature | Status | Gap | Phase |
|---|---|---|---|---|
| 1 | Lost-lead and missed-opportunity recovery | LIVE (E-03, E-04, E-23) | — | — |
| 2 | Dormant-customer reactivation | PARTIAL (dormant-deal lane) | Dormant client lane after the sale | 3 |
| 3 | AI-assisted customer-record updates with source references | PARTIAL (E-07 cites sources; C-19 blocked on the owner's AI key) | AI updates | 2 |
| 4 | Call and meeting summaries with action extraction | MISSING (E-16) | Needs call or meeting capture first | 3 |
| 5 | Prioritized daily work plans | LIVE (C-34 Today plan; C-07, C-08, E-07) | — | 1 |
| 6 | Explainable next-action recommendations | LIVE (E-07) | — | — |
| 7 | Verified automation with execution receipts | LIVE (C-35: a receipt per run with each step's outcome and links; C-28, E-22, C-14) | — | 2 |
| 8 | Human approval controls and duplicate-send protection | LIVE (C-09, M-07, M-02) | — | — |
| 9 | Connection-health monitoring and failure alerts | LIVE (C-12, C-28) | — | — |
| 10 | Automated sales-to-onboarding handoffs | LIVE (a won deal with a company creates a Client 360 workspace; C-35 "Deal won: start onboarding" recipe) | — | 2 |
| 11 | Customer portals for documents, approvals and status | PARTIAL (C-15) | Approvals and branding in the portal | 3 |
| 12 | Proposal, contract and payment integrations | PARTIAL (C-15 estimates → invoices; C-18 blocked) | E-signature; payments need Stripe keys | 3 |
| 13 | Renewal, retention and referral workflows | PARTIAL (C-15 referrals, reviews) | Renewal workflow | 3 |
| 14 | Industry-specific templates and ready-to-use workflows | PARTIAL (C-36: six templates — agency, real estate, home services, health and wellness, coaching, B2B sales — each with a pipeline, booking pages, a form, fields and draft automations; C-32 neutral defaults) | Per-industry record names (for example "Job" for a deal) | 2 |
| 15 | Measurable revenue recovery and customer-value reporting | LIVE (M-10, M-08 attribution) | — | — |

**Agency and white-label**

| # | Feature | Status | Gap | Phase |
|---|---|---|---|---|
| 1 | Branded client workspaces and custom domains | PARTIAL (brand name on booking pages and the portal) | Logo, colours and domain per account | 4 |
| 2 | Secure separation between client accounts | PARTIAL (C-02 tenant isolation; C-38 client accounts under one agency) | Agency-wide reporting across client accounts; per-client branding (agency 1) | 2 |
| 3 | Reusable client configurations and workflow templates | LIVE (C-37 snapshots, share code or file; C-38 create a client account from a snapshot and push a snapshot to many client accounts at once) | — | 2 |
| 4 | Centralized management across client accounts | MISSING | Agency view across accounts | 4 |
| 5 | Subscription billing, usage tracking and spending controls | MISSING (C-18 blocked) | Plans, usage meters, caps | 4 |

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
- `main@730b1b3` — PR #28 squash-merged at 2026-09-16T23:31Z, bringing the Recovery Case and normalized recovery-event foundation (E-21) and the recovery runner (E-22). Exact-head CI run 35162676444 passed.
- `main@c9f5a6e` (head as of 2026-09-28) — the owner merged `claude/trusting-brahmagupta-lj26xf` (scheduler falsifiability, CRM baseline completion, Gmail send/receive, the attribution ledger, the eight declared detector families, backend lint/type/dependency/config CI gates, and the proof surface). Its capability-level findings (`docs/ACTIVATION_REPORT.md`) are reconciled into §4 as of v1.10: C-27…C-29 and E-23 added; M-01, M-08, M-10, E-01, E-02 and E-09 updated. **Exact-head CI could not run:** since 2026-09-27T22:35Z every GitHub Actions job on every branch fails in 2–4 s with no runner assigned (§10.2 O-16). The same gates were run locally on this tree on 2026-09-28: `ruff` clean, `scripts/typecheck.py` blocking modules clean, `pip-audit` no known vulnerabilities, `scripts/validate_config.py` passed, `yarn lint --max-warnings=0` passed, `CI=true yarn build` passed, `scripts/crm_release_smoke.mjs` 82/82, backend 675 passed / 16 failed / 4 skipped on `mongomock` — the documented driver-fidelity baseline; the 16 need a real mongod, which the session cannot reach.

### 3.2 Production truth

- Railway deployment `d9af2985-30e4-4fb8-b030-ac8b1446db89` running `ca30587` was **LIVE VERIFIED** on 2026-09-01: `/api/health` 200 `{"status":"ok","database":"up"}`, `scripts/proof_of_life.mjs` exit 0 including cross-tenant 404, smoke records fully purged. Evidence: `docs/evidence/production-smoke-20260901.json`.
- A fresh Railway health probe returned HTTP 200 `status=ok`, `database=up` on 2026-09-15 (recorded in Issue #10), but **the runtime SHA is not exposed by the current production deployment**. `git_sha` on `/api/health` is merged in code at `3706c7a`; production has not been redeployed onto a head containing it.
- **Production is not reachable from the current execution environment.** The session egress policy rejects both `clientverse-crm-production-production.up.railway.app:443` and `backboard.railway.com:443` with HTTP 403 at CONNECT. Deployment, production health verification, production smoke, and the two-company production isolation smoke therefore carry status `BLOCKED — TECHNICAL` for any agent running under this policy; they are not owner blockers and require no owner action other than running them from an environment that can reach Railway. Nothing in this document reports production behaviour that was not observed.

- **`main@c9f5a6e` is `DEPLOYED`** (Railway deployment `1f809799-a4a2-4dc9-9e38-8d19ba1b282d`, SUCCESS 2026-09-28T05:25Z). PR #30 (`c931b4e`, no change under `backend/`, `frontend/`, `Dockerfile` or `railway.json`) redeployed the same application code as `84c89214-0c38-4cdf-b38c-9a3d1ee59d6c` (SUCCESS 2026-09-28T18:05Z, identical boot log), after which `1f809799` is REMOVED. Each `main` commit redeploys, so the live deployment id is read from Railway, not from this document. The deploy log reads `Registered outbound channel provider: gmail` → `Application startup complete` → `GET /api/health 200` from Railway's healthcheck. This head contains `3706c7a`, so `/api/health` now exposes `git_sha` and runtime-SHA parity can be checked. It is **not `LIVE VERIFIED`**: no authenticated production smoke has run against it, and on 2026-09-28 the production host still refused CONNECT from the agent environment with 403.
- Railway's HTTP log for that deployment shows **no inbound request of any kind** after the boot healthcheck (read 2026-09-28). The scheduler is therefore still not calling production (O-03, O-16). *Superseded 2026-09-30 and 2026-10-18: see the next two items.*
- **2026-09-30 (read through Railway and GitHub; the production host itself still refuses CONNECT from the agent environment):**
  - **Current deployment.** Production serves `main@8f23f63` as Railway deployment `b9a868c3-4edd-4ad7-b4fe-f353fb69c680`, SUCCESS at 15:52Z. Its application code is identical to `c9f5a6e`. The boot log is unchanged, and the service's only domain is `clientverse-crm-production-production.up.railway.app`, with no custom domain.
  - **The scheduler reaches production for the first time.** GitHub Actions is restored. *Scheduled jobs* runs #3544–#3550 (15:39–15:58Z) failed, with Railway logging `401 Unauthorized` on the cron calls at 15:54Z and 15:58Z — a shared-secret mismatch. Runs #3551 (attempt 3, 16:11Z) through #3555 (16:29Z) succeeded. Railway logs `200 OK` for all twelve `/api/cron/*` endpoints between 16:08Z and 16:29Z, plus the workflow's `GET /api/cron/runs` ledger read-back.
  - **The stored Google grant fails to refresh.** During the 16:08Z `integration-sync`, Google's token endpoint answered `400 Bad Request` twice (Gmail and Calendar). By `run_sync`, that marks both connections `expired` ("Needs auth"), so the owner must re-authorize (O-01).
  - **Not `LIVE VERIFIED`.** No authenticated production smoke has run against this deployment.

  *Superseded 2026-10-18 by the next item: the scheduled jobs now also run inside the API (C-31).*
- **`main@b854059` (PR #38) is `DEPLOYED`** (Railway deployment `a65dc4e1-9a79-4bd8-a19d-81dc49d0e1b0`, SUCCESS 2026-10-18T03:37:33Z; `6d1116b3-…` is REMOVED). Boot log: `Registered outbound channel provider: gmail`, `In-process scheduler started for 13 job(s)` (commitment-risk, work-queue, recovery-runner, booking-reminders, integration-sync, next-best-actions, inbound-email, reconcile-unknown, daily-digest, second-chance, detect-recovery, recovery-strategies, approval-expiry), `Application startup complete`, then `GET /api/health` 200. **Scheduled jobs now reach production from both drivers.** The GitHub Actions `Scheduled jobs` workflow calls the cron endpoints selected on each tick. Runs 8174–8178 (03:23–03:43Z) passed except one call, which is covered below. Run 8176 logged `work-queue` → `cronlog_4dae6edb314b434a`, for example, and Railway's HTTP log shows the calls; the in-process scheduler skips each window an external request already ran (`an external request already ran window …`). One call failed during the swap: run 8176 reached the old deployment at 03:37:02Z, before the new one was ready at 03:37:39Z, and `booking-reminders`, which the old code does not have, answered 405.
- **2026-10-19: `main@1a39fa4` (PR #41) is `DEPLOYED`** (Railway deployment `d4d2e07f-b201-44f9-90fe-a06c59dabad5`, SUCCESS 2026-10-19T00:16Z; PR #40's `b34dfd4a-…` is REMOVED). PRs #39–#41 change documentation and the frontend only: `git diff b854059 1a39fa4` is empty under `backend/`, `Dockerfile`, `railway.json` and `.github/`. The boot log is PR #38's: `Registered outbound channel provider: gmail`, `In-process scheduler started for 13 job(s)` (the same thirteen), `Application startup complete`, then `GET /api/health` 200. The GitHub Actions workflow still calls production: this deployment's log shows `200 OK` for all fourteen workflow paths (the thirteen jobs plus `lead-sla`) and for the `GET /api/cron/runs` read-back between 00:19Z and 00:58Z. No Google API request appears in the log through 01:09Z, so no tenant has an active Google connection to sync; whether the 2026-09-30 grant was re-authorized is unrecorded (O-01). Not `LIVE VERIFIED`.
- **2026-10-19: `main@838f00d` (PR #42) is `DEPLOYED`** (Railway deployment `406f320e-96c1-42a4-a243-77e518a3e17e`, SUCCESS 01:16Z; `d4d2e07f-…` is REMOVED). Same boot log, including the thirteen in-process jobs; the workflow's calls answer `200` from 01:17Z. PR #42 changes delivery safety only: a refused provider lookup no longer resolves an outcome-unknown email as not sent, and the Google OAuth callback records the scopes Google granted instead of the requested list. Because the Gmail send guard reads that record, a Google connection made before this deployment must be renewed once (O-01). Railway also lists a custom domain, `crm.clientverse.io`, that is not verified: its CNAME and TXT records are unset and its certificate is waiting on ownership validation (O-12). Not `LIVE VERIFIED`. The owner-facing account of this state is the manual's Appendix B.

- **2026-10-19: `crm.clientverse.io` is live.** Railway reports the domain verified with a valid certificate. Railway variables `FRONTEND_URL` and `GOOGLE_REDIRECT_URI` now point to it and `CORS_ORIGINS` lists both addresses; applying them redeployed `838f00d` as `9e61bcac-…` (01:42Z) and `e7790295-…` (01:47Z). A Google connection attempt begun before the first redeploy and finished after it failed (`oauth=error`, 01:42:53Z) because the callback address changed mid-attempt; the second redeploy settles it on the custom domain. The Railway address still serves the same application.
- **2026-10-19: `main@4873f67` (PR #45, Phase 1) is `DEPLOYED`** (Railway deployment `21d4b7b5-f2a5-435e-bd23-afe7b3d3c8f4`, SUCCESS 09:28Z). Boot log: `Registered outbound channel provider: gmail`, `In-process scheduler started for 13 job(s)`, `Application startup complete`, `GET /api/health` 200. It carries C-32, C-33, C-34 and the new main menu. Not `LIVE VERIFIED`.
- **2026-10-19: `main@394f095` (PR #46, Phase 2) is `DEPLOYED`** (Railway deployment `56756228-a849-42c0-b7ff-53226b6880dd`, SUCCESS 17:36:53Z; `21d4b7b5-…` is REMOVED). The same boot log, with the thirteen jobs. A search of its deploy log for `Traceback`, `ERROR`, `Exception`, `WARNING` and ` 500 ` found nothing. At 17:40Z the inbound-email sweep read the connected Gmail inbox and every Gmail request answered 200, so the grant renewed at 02:02Z (O-01) works. It carries C-35 to C-38. Not `LIVE VERIFIED`: no authenticated production smoke has run against it.
- **2026-10-24: `main@6d0d4c6` (PR #48, the closeout release) is `DEPLOYED` and verified from outside.** Production had run `394f095` (PR #46; its scheduled jobs answered `200` throughout the day). Merging PR #48 deployed `6d0d4c6`. *Production acceptance* run `40134314474` (GitHub runner, 21:27–21:31Z) ran against `https://crm.clientverse.io` and checked:
  - production reported exactly `git_sha` `6d0d4c6`;
  - the authenticated lead journey, 40/40 checks: server-key intake, field mapping, attribution, assignee, deal and task, sign-out and sign-in, duplicate and idempotency, `$500,000+` as a minimum, alias precedence, two-organization isolation, pipeline, task, response and export;
  - a real-browser pass, 76/76 checks: sign-in through the form; 11 pages at 390, 768, 1024 and 1440 px; the lead after a reload; sign-out.

  The *Backup and restore drill* (`mongodump` → drop → `mongorestore`, verified through the API) passed on MongoDB 7. Atlas's own backups remain unverified.

  **Found:** the scheduler's GitHub secret `CLIENTVERSE_PRODUCTION_URL` points at a Vercel copy of the screens (`clientverse-crm.vercel.app`, project `clientverse-crm`, team `tradeiq`), which forwards `/api` to Railway. Sign-in on that copy fails, because its build calls the Railway API across origins. Owner actions O-17 and O-18 cover it.

  The owner's own sign-in, live Gmail sending and Stripe were not exercised. No owner credential is held by engineering, and sending and Stripe are off. The Jev QC gate was not run: its variables were absent from the session.

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
| `README.md` §12: "Read-only scopes only: `gmail.readonly`, `calendar.readonly`, `userinfo.email` … No sending." | **Stale since the Gmail adapter.** `GOOGLE_SCOPES` requests `gmail.readonly`, `gmail.send`, `calendar.readonly`, `userinfo.email` and `openid`. README corrected in v1.16. |
| O-03 and C-25 (this document, v1.10–v1.15) and `docs/RAILWAY_RUNBOOK.md` §6 (until 2026-10-17): the scheduler workflow "exits cleanly" when its secrets are missing | **False since the workflow was hardened.** It fails loudly when unconfigured, when no request reaches production, and when production has no ledger entry for the run. O-03 is corrected below. |
| `docs/OWNER_HANDOFF.md` §5: "In ClientVerse → Settings → Integrations, **disconnect** Google" | Settings has only an **Integrations** status section; its buttons open **Registries** → **Integrations**, where the controls are. Disconnecting either card revokes the shared grant at Google. The stored copy is deleted only once neither card is still active, so a clean reset disconnects both. See manual §5.7. |
| M-01 (v1.10): outbound email "still blocked on two owner actions" — `gmail.send` (O-01) and the scheduler | **Incomplete.** `recovery_strategy.authorized_channels` also requires the tenant's Gmail **catalogue record** (`integrations`, `name: "Gmail"`) to be in a configured state. That record is seeded `REQUIRES_CONFIGURATION`, and no API or UI changes it, so every send refuses with `channel_not_authorized` until engineering records the certification. Separately, **no UI** creates a conversation, records consent, or drafts an owner-written message; those exist only as API endpoints. The only screens that release email are the Calendar's approval of system-written booking emails (M-05) and Website Forms' approval of an auto-reply template (C-30, M-07). See M-01 and §8 #27–#28. |

### 3.4 Open pull requests

| PR | Title | State | Disposition |
|---|---|---|---|
| #21 | expose non-secret `git_sha` on `/api/health` for deploy parity | closed, merged | Merged into `main` at `3706c7a`; production still does not expose SHA because production has not been redeployed to a head containing it. |
| #26 | Durable work queue, Second Chance detection, Next Best Action service, and the dual security gate | closed, merged | Squash-merged into `main` at `3150530` on 2026-09-15. The capabilities it carries are `MERGED`; none is `DEPLOYED`. |
| #27 | Approval queue (M-07), recovery strategy composer (E-20), and the Conversation / CommunicationMessage foundation | closed, merged | Squash-merged into `main` at `e8d5678` on 2026-09-16. Fifteen review findings across two reviewers; twelve were real and fixed on the branch. The capabilities it carries are `MERGED`; none is `DEPLOYED`. |
| #28 | Recovery Case foundation and recovery runner | closed, merged | Squash-merged into `main` at `730b1b3` on 2026-09-16. |
| #30 | Jev QC gate + live verification evidence, and the deployed-state record | closed, merged | Merged into `main` at `c931b4e` on 2026-09-28. Documentation and standalone agent tooling (`scripts/jev_qc.mjs`); no runtime change. |
| #36 | Google consent and delivery safety; accessible report scrolling (Codex) | closed, superseded (2026-10-24) | Both backend fixes and their reconciliation test were already on `main` (`server.py` publishes Google's granted scopes; a refused lookup leaves an outcome-unknown send unresolved; `tests/test_reconciliation_lookup.py`). The PyMongo bump was superseded by 4.18.2 / Motor 3.7.1. The Recovery Proof scroll navigation targeted the pre-redesign page. Nothing was ported. |
| #47 | Preserve Allure intake fields and meaningful resubmissions (Codex) | merged through #48 (2026-10-24) | Reviewed against `main@394f095`. Its two commits were carried unchanged into #48, together with fixes for the gaps found in review (C-30). |
| #48 | Closeout release: intake repair, sign-in and ledger hardening, UI fixes, production acceptance | merged (2026-10-24) | See §3.2 (2026-10-24) and C-30. Copilot raised four findings on the intake code; all were reproduced and fixed. |
| Workforce PR #9 | AI-WOS v2 canonical operating contract + implementation register | **open (draft)** | Governs the agent-workforce repository, not the CRM. Do not merge as part of CRM work. |

---

## 4. Capability register

**Status vocabulary (exactly one per capability):**
`APPROVED — NOT STARTED` · `IN IMPLEMENTATION` · `CODE COMPLETE` · `TESTED` · `MERGED` · `DEPLOYED` · `LIVE VERIFIED` · `BLOCKED — OWNER INPUT` · `BLOCKED — TECHNICAL` · `DEFERRED`

**Completion rule:** only `LIVE VERIFIED` counts as fully complete. Research, repo selection, a written prompt, local code, an open PR, or passing unit tests never qualify.

**A `DEPLOYED` status below refers to the application code of `main@c9f5a6e`** (first live as Railway `1f809799-…`, 2026-09-28) **unless its row names a later deployment**; C-30 to C-38 and M-05 name theirs. None is `LIVE VERIFIED` — see §3.2.

### 4.A Core CRM — implemented and merged

| ID | Capability | Status | Evidence / note | Provenance |
|---|---|---|---|---|
| C-01 | Authentication, sessions, login lockout, session revocation | DEPLOYED | PR #17; backend suite | RECOVERED (PR #17, Issue #6) |
| C-02 | Multi-tenant isolation (direct-ID, exports, webhooks, background jobs) | DEPLOYED | PR #17 isolation tests; cross-tenant 404 in production smoke | RECOVERED (Command Brief §Security) |
| C-03 | Contacts, Companies | DEPLOYED | `/api/contacts`, `/api/companies` | RECOVERED (module registry) |
| C-04 | Opportunities, Deals, Pipeline stages | DEPLOYED | `/api/opportunities`, `PATCH /stage` | RECOVERED (module registry) |
| C-05 | Client 360 workspaces, health signals, outcome graph, timeline | DEPLOYED | `/api/workspaces/*` | RECOVERED (module registry) |
| C-06 | Commitments + commitment-risk evaluation | DEPLOYED | `/api/commitments`, `/api/commitments/evaluate-risk` | RECOVERED (PRD) |
| C-07 | Alerts + Action Center work queue with deduplicated lifecycle | DEPLOYED | `/api/alerts`, acknowledge/resolve/escalate | RECOVERED (UX assessment P0 #2; todo.md) |
| C-08 | Notifications, preferences, timezone-aware daily digest | DEPLOYED | `/api/notifications*`, `/api/digest/*` | RECOVERED (PRD) |
| C-09 | Approvals + undo window | DEPLOYED | `/api/approvals`, `PATCH /workspaces/{id}/undo-window` | RECOVERED (Command Brief) |
| C-10 | Signed, versioned, retryable webhooks with replay and match preview | DEPLOYED | `/api/webhooks*`, `/api/webhook-deliveries/*` | RECOVERED (PRD) |
| C-11 | MCP console — allowlist, approval levels, undo, invocation audit | DEPLOYED | `/api/mcp/*`; static catalog + per-tenant allowlist | RECOVERED (module registry) |
| C-12 | Registries and integration health | DEPLOYED | `/api/registry/{kind}`, `/api/integrations/health` | RECOVERED (module registry) |
| C-13 | Team, roles, invitations | DEPLOYED | `/api/team/*` | RECOVERED (PR #1) |
| C-14 | Audit trail and domain events | DEPLOYED | `/api/audit`, `/api/events` | RECOVERED (module registry) |
| C-15 | Client Operations + Client Portal + Field Ops | DEPLOYED | `/client-ops`, `/portal/:token`, `/field` | RECOVERED (module registry) |
| C-16 | Cron endpoints (commitment-risk 15m, integration-sync 30m, daily-digest hourly), idempotent, Bearer-authenticated | DEPLOYED | `/api/cron/*`; driven since 2026-10-18 by the in-process scheduler (C-31) and the GitHub Actions workflow (C-25). Deferral is one-way. An in-process run skips a window an external request already ran. An external request that arrives after an in-process run still runs: every new delivery id runs, and every job is an idempotent sweep (`backend/scheduler.py`). §3.2 has the evidence. Fourteen endpoints: the thirteen in-process jobs plus `lead-sla`, which the lead watcher runs (manual §11.2). | RECOVERED (RAILWAY_RUNBOOK) |
| C-17 | Google / Gmail / Calendar integration lifecycle (PKCE connect, callback, refresh-on-401, reconnect, disconnect, redaction) | BLOCKED — OWNER INPUT | 22 deterministic lifecycle tests pass; live certification impossible without owner OAuth client + consent | RECOVERED (Issue #10) |
| C-18 | Stripe test-mode lifecycle (PaymentIntent, signed webhook, idempotency, tenant-scoped invoice) | BLOCKED — OWNER INPUT | Tests pass; unsigned webhook → 503 safe refusal; live certification needs owner test key | RECOVERED (Issue #10) |
| C-19 | AI generation endpoint | BLOCKED — OWNER INPUT | `/api/ai/generate` requires `EMERGENT_LLM_KEY`; 2 tests skipped for its absence | RECOVERED (PRD, CI skips) |
| C-20 | Railway production deployment + health check | DEPLOYED | LIVE VERIFIED at `ca30587` 2026-09-01; current `main` not re-certified | RECOVERED (Issue #10) |
| C-21 | Shared surface states (loading/empty/error + retry) across Command Center, integrations, workspace activity, audit, MCP | DEPLOYED | PR #24, `SurfaceState.jsx` | RECOVERED (PR #24) |
| C-22 | Next Best Action | DEPLOYED | Superseded by NBA-1 in §4.C — the client-side strip is removed and the surface now consumes the backend service. | RECOVERED (UX assessment P0 #3) |
| C-23 | Frontend lint enforced in CI | MERGED | `.github/workflows/ci.yml` now runs `yarn lint --max-warnings=0` before the build; the pre-existing error on `main` is fixed. | PR #26 (§3.3) |
| C-24 | `/operations` operator surface | DEPLOYED | Work-queue queue depth and dead-letter visibility with acknowledge / resolve / admin replay, the recovery-detection trigger, the ranked recommendation queue, and the security-gate panel that reports scanner configuration honestly. Registered in `CLIENTVERSE_MODULES` as `available`. The Recovery strategies, Approvals and Conversations panels added on top of it merged with PR #27. | PR #26, extended by PR #27 |
| C-25 | Scheduled-job driver | DEPLOYED | Running: observed 2026-10-18 calling production. Runs 8174, 8175, 8177 and 8178 succeeded, which the workflow allows only when every call it made returned HTTP 200. Run 8176's `work-queue`, `recovery-runner` and `lead-sla` calls returned 200 with cron-ledger evidence ids. Its `booking-reminders` call got 405 from the old deployment during the swap (§3.2). So the repository secrets exist (O-03) and Actions runs again (O-16). Optional since C-31: the API runs every job itself. The in-process run skips a window this workflow already ran, but not the reverse (C-16). Earlier it could not run: the secrets were unset and from 2026-09-27T22:35Z Actions assigned no runner. Design: `.github/workflows/scheduled-jobs.yml` calls every cron endpoint on the documented cadences once two repository secrets exist, and fails loudly while they do not (§3.3). It first reached production on 2026-09-30 (runs #3551–#3555 green, after #3544–#3550 failed on a `401` secret mismatch). See O-03; owner check: manual §11.4. | PR #26 |
| C-26 | Conversations operator surface | DEPLOYED | The `/operations` Conversations panel: open threads with channel, handler, consent state and message count; a thread reader with its messages and any blocked-send reason; assign, handoff and close. It states plainly that no delivery provider is registered rather than offering a send button that would fail. | This change set |
| C-27 | CRM baseline completion — record detail, edit, archive/restore and timeline for contacts, companies and deals; tenant-configurable pipelines with per-deal stage history; tasks on any record; notes, calls, meetings and logged emails as activity; global search; filtering; CSV import and export | DEPLOYED | `backend/crm_core.py` (33 tests): `/api/contacts\|companies\|opportunities/{id}` with `archive`, `restore`, `timeline`; `GET\|PUT /api/pipelines/default`; `/api/tasks`, `/api/crm/tasks`, `/api/tasks/overview`; `/api/activities`; `GET /api/search`; `GET /api/export/{entity}`; `POST /api/import/{entity}`. Cross-tenant access answers 404 on every new surface. Release smoke `scripts/crm_release_smoke.mjs` 82/82 locally on 2026-09-28; **not run against production**. | `docs/ACTIVATION_REPORT.md` (branch `claude/trusting-brahmagupta-lj26xf`, merged at `c9f5a6e`) |
| C-28 | Scheduled-run ledger and scheduler health | DEPLOYED | `backend/cron_ledger.py` (10 tests): every scheduled request, including rejected ones, is recorded in `cron_run_log`; `GET /api/cron/runs` and `GET /api/cron/health` (`receiving_scheduled_traffic`). Production has recorded scheduled traffic since 2026-09-30T16:08Z: the workflow's ledger read-back (`GET /api/cron/runs` 200) passes on every green run. | Same |
| C-29 | Backend CI gates — `ruff`, `scripts/typecheck.py` ratchet, `pip-audit`, `scripts/validate_config.py` | MERGED | `.github/workflows/ci.yml` job *Backend lint and types*. CI configuration, so `DEPLOYED` does not apply; the job cannot currently run (O-16). All four pass locally on `main` (2026-09-28). | Same |
| C-30 | Website forms and automatic lead handling — managed real-estate forms (8 templates, 24-field catalogue, custom fields), a public door real websites can use (CORS-open public paths without credentials; JSON, `text/plain`, URL-encoded and multipart bodies; HTML-form redirects), embeds (inline, pop-up with delay/scroll/exit triggers, slide-in, iframe-able hosted page, raw HTML, API), honeypot + fill-time + rate limits + idempotent `_sid` + duplicate window, contact match-or-create, owner assignment (existing / specific / round-robin), a deal valued at expected commission, a speed-to-lead task, in-app and email alerts, `lead.received` webhook event, an in-process SLA watcher with one-time escalation, response-time capture, a leads inbox and a form editor | DEPLOYED | `backend/website_forms.py`, `frontend/src/pages/Leads.jsx`, `frontend/src/pages/WebsiteForms.jsx`; `backend/tests/test_website_forms.py` (30 tests, every one through the public HTTP door with browser headers); an 18-step real-browser run from a separate origin. The legacy token door (E-23) now runs through the same pipeline; it previously refused browsers, refused HTML forms and dropped every unrecognised field, and had no test. Guide and GoHighLevel feature map: `docs/WEBSITE_FORMS.md`. Merged in PR #37 (`main@9bd9723`) and deployed to Railway 2026-10-17 (deployment `6d1116b3-…`: startup complete, `/api/health` 200). Not `LIVE VERIFIED`: no production lead has been submitted from an agent's site yet. **2026-10-24 (PR #48, completing PR #47):** a field's own name and a top-level value now outrank an alias or a `payload` value, and the losing answer is kept in `extra`. A budget is one answer, so no inverted range; `$500,000+` is a minimum, never a ceiling. A list-picked `budget` is filed instead of refused. A changed resubmission is a new enquiry on the same contact and deal. The contact's budget is replaced whole. An untouched deal is re-priced by compare-and-set, and never across currencies. The form's in-app and email alert switches are honoured. 132 tests in `backend/tests/test_website_forms.py`. Production acceptance exercises the server-key journey end to end; see §3.2. | DIRECTIVE 2026-10-17 (owner: connect agents' real-estate websites end to end, GoHighLevel option parity, automatic) |
| C-35 | Automations — an admin builds automations from a trigger (website lead, lead past its reply goal, booking made / no-show / cancelled, deal won / lost / moved to a stage, contact added, commitment at risk; optional form, stage or booking-page filter), conditions on the contact (the C-33 filter compiler), steps (create a task, set a field, add a tag, assign an owner, notify the team, wait up to 90 days) and stop rules (replied, booked, deal closed, stage changed, became a customer; plus archived contact and automation turned off, always). Triggers are the domain events `record_event` already records, handed to the engine in the background; events an automation caused never start another. Each run snapshots its steps and keeps a receipt (`automation_runs`): every step's outcome, links to what it made, and how the run ended. A unique (automation, event) index makes an event start an automation once; one active run per person; optional once per person ever. Wait steps resume from an in-process watcher (`AUTOMATION_WATCHER`) claiming runs atomically. Six recipes (speed to lead, deal-won onboarding, no-show rebooking, quiet-lead follow-up, lost-deal check-back, commitment at risk); a dry-run test against a contact; runs stoppable by an admin. Nothing an automation does leaves the CRM. Screen: `/automations` (the main-menu entry; replaces the "Workflows" placeholder) | DEPLOYED | Merged in PR #46 (`main@394f095`) and deployed 2026-10-19 (Railway deployment `56756228-…`, SUCCESS 17:36Z; §3.2). `backend/automations.py`, `backend/server.py` (event hand-off, indexes, watcher); `frontend/src/pages/Automations.jsx`; `backend/tests/test_automations.py` (12 tests, leads through the public form door: speed-to-lead with the wait resumed, stop on a logged call, one run per event and per person, loop protection, deal-won onboarding and turning off, conditions and stage filter, validation and permissions, dry run writes nothing, edits never rewrite a run, manual stop, tenant isolation). Browser run: recipe → edit → save → turn on → a real form lead starts a run with its receipt → test with a contact; light, dark, 390 px. | DIRECTIVE 2026-10-19 (owner feature scope, §1.5 must-have 7, value-add 7 and 10) |
| C-36 | Industry templates — six starting setups (agency and services, real estate, home services, health and wellness, coaching and consulting, B2B sales). Each brings pipeline stages, booking pages, one website form with its trade's questions, two or three custom fields (C-33) and three draft automations from the C-35 recipes. Applying only adds what is missing: booking pages, forms, fields and automations are matched by name (an archived page, form or automation does not count; an archived field does and is flagged for restore); the pipeline's stages are replaced only while the tenant has never configured them and no deal, form or booking page uses a stage that would go. Nothing existing is renamed, changed or removed; automations arrive as drafts; the form's auto-reply is off (its own approval, C-30). A preview reports the same plan without writing. The tenant records the template in use (`industry_template`), shown on the cards and completing the first step of the Today setup checklist. Applying is admin-only; preview is open to members. Because template pipelines use their own stage keys, a deal created without a stage starts in the first open stage (it defaulted to `lead`), and the company page, dashboard funnel and MCP pipeline summary classify won and lost by the tenant's stages (they compared against `closed_won`). Screen: Settings → Workspace → "Industry template" (`/settings/templates`) | DEPLOYED | Merged in PR #46 (`main@394f095`) and deployed 2026-10-19 (Railway deployment `56756228-…`, SUCCESS 17:36Z; §3.2). `backend/industry_templates.py`, `backend/record_fields.py` (`create_definition`), `backend/automations.py` (`create`, `recipe_body`), `backend/server.py` (routes, dashboard `industry_template`, first-stage default, stage-aware funnel), `backend/crm_core.py` (company figures); `frontend/src/pages/IndustryTemplates.jsx`, `frontend/src/components/OnboardingChecklist.jsx`, `frontend/src/components/QuickCreateDialog.jsx` (no fixed stage); `backend/tests/test_industry_templates.py` (10 tests: the six offered, preview writes nothing, apply then re-apply adds nothing, switching keeps what exists, the pipeline kept when deals use its stages, a lead through the template's own public form lands in the template's first stage, admin-only apply and tenant isolation, archived pages and forms re-added while an archived field is flagged, a template pipeline's won and lost deals counted correctly on the company page and funnel, a stage-less deal starting in the first stage). Browser run: preview → apply → next steps → Today checklist ticked; light, dark, 390 px. | DIRECTIVE 2026-10-19 (owner feature scope, §1.5 must-haves 2 and 14, value-add 14) |
| C-37 | Snapshots — an admin saves the workspace's setup (pipeline stages, custom fields, booking pages, website forms, automations, shared saved views; each part optional) as a snapshot, shares it with a code shown once (only its SHA-256 is stored; a new code replaces the old, sharing can be stopped), downloads it as a versioned JSON file (`clientverse.snapshot` v1), and loads a snapshot from the workspace's own list, a share code or a file. A snapshot holds no records, people, links or secrets: booking pages drop their host, link and brand name; forms drop allowed origins, redirect, lead assignment and CAPTCHA keys and keep the auto-reply's wording but never its approval; automation steps that named a person fall back to the record owner or round robin; private views are not saved; items refer to each other by snapshot-local references, never ids. Loading goes through `setup_loader`, the engine industry templates (C-36) now use too: the same "add only what is missing" rules (the pipeline is also kept when a stage in use would change between open, won and lost), every item checked by the validator its screen uses, an invalid item skipped with its reason while the rest load, form and booking-page references in automation triggers rewritten to the loaded copies, and custom-field keys in automation conditions, set-field steps and view filters, columns and sort rewritten to the target's field of the same label. Admin-only; 50 snapshots per workspace, 1 MB and per-section caps. Screen: Settings → Workspace → "Snapshots" (`/settings/snapshots`) | DEPLOYED | Merged in PR #46 (`main@394f095`) and deployed 2026-10-19 (Railway deployment `56756228-…`, SUCCESS 17:36Z; §3.2). `backend/setup_loader.py` (new; the loader), `backend/snapshots.py` (new; capture, storage, sharing, file, routes), `backend/industry_templates.py` (templates as loader contents), `backend/server.py` (registration, indexes); `frontend/src/pages/Snapshots.jsx`, `frontend/src/components/SetupPlan.jsx` (plan list shared with the template page); `backend/tests/test_snapshots.py` (7 tests: contents hold no records, people, links, ids or secrets; a share code loads into a new workspace and the copied form takes a real lead; a field's key is remapped by label in views and automation conditions; a tampered file is checked item by item with sound items still loading; codes are replaced and stopped; admin-only and private to the workspace; loading your own snapshot restores an archived form) and the 10 industry-template tests on the shared loader. Browser run: save → share → download → a new account previews and loads by code → file preview; light, dark, 390 px. | DIRECTIVE 2026-10-19 (owner: "We need to be able to generate snap shots"; §1.5 agency 3) |
| C-38 | Agency and client accounts — a workspace's admins create client accounts under it (tenants with `parent_tenant_id`; no nesting: a client account cannot have client accounts). A client account is a full tenant (C-02 isolation applies unchanged); its own people sign in to it as usual. An agency admin opens a client account by taking a fresh session whose token carries `act` (the client tenant); `agency.act_as` re-checks on every request that the person is still an active admin of their own workspace and that the account still belongs to it, and refuses with 401 otherwise, so demotion, disabling or moving the account ends access at once. Opening and leaving replace the session (the old one is revoked): one browser, one session. Inside, the agency admin is an admin of the client account; `/auth/me` and every response that signs someone in (sign-in, sign-up, Google, invitation sign-up, password change) carry `acting` and `workspace` (agency / client / standalone), so the switcher shows without a reload; a password change inside a client account keeps the browser there and is recorded in the person's own workspace. An account can be created from one of the agency's snapshots; a snapshot can be pushed to up to 100 accounts with a per-account preview and result, every account verified before any is changed, each load through `setup_loader` (C-37) and recorded in the client's and the agency's audit trails. Booking pages loaded into any workspace are now hosted by someone on that workspace's team (the loader's actor if a member, else its first admin), or arrive paused when it has no team. Screens: account switcher at the top of the main menu, "working in" banner, Settings → Agency → "Client accounts" (`/settings/agency`) | DEPLOYED | Merged in PR #46 (`main@394f095`) and deployed 2026-10-19 (Railway deployment `56756228-…`, SUCCESS 17:36Z; §3.2). `backend/agency.py` (new), `backend/server.py` (`create_access_token(acting_tenant=)`, `get_current_user` → `act_as`, `session_user` for `/auth/me` and every sign-in response, password change keeps `act`, routes, index), `backend/setup_loader.py` (host resolution); `frontend/src/components/AgencySwitcher.jsx`, `frontend/src/pages/AgencyAccounts.jsx`, `frontend/src/components/AppShell.jsx`, `frontend/src/platform/navigation.js`; `backend/tests/test_agency.py` (6 tests: sign-in returns the same workspace as `/auth/me`, and a password change inside a client account stays there and is recorded in the agency; an account starts from a snapshot with none of the agency's records and paused pages; working inside and coming back, with both audit trails and the replaced session revoked; access ends on demotion and when the account moves; members, a client's own admin and another agency are refused, a forged acting token is refused, accounts made from inside a client still belong to the agency; a push previews and applies per account, keeps a client's own page, hosts with the client's admin, adds nothing the second time, and loads nothing when one account is not the agency's). Browser run: create from snapshot and blank → open → switch → back → push preview and apply; light, dark, 390 px. | DIRECTIVE 2026-10-19 (owner: "We need to have that capability" — pushing snapshots to client accounts; §1.5 agency 2 and 3) |
| C-39 | Self-serve import and export — Settings → Import and export (`/settings/import`). An admin imports contacts, companies or deals from a CSV file (up to 5,000 rows; Excel files with a byte-order mark or `;` separators read as they are): every column gets a suggested field from its header (aliases such as *E-mail* or *Company Name*, first and last name, custom fields by label), the admin adjusts the matches, and `POST /api/import/{entity}/preview` shows what happens to every row before `POST /api/import/{entity}` runs the same plan. Records are made the way the screens make them (contact phone key and lifecycle, company domain, deal stage history and first open stage, won deals promote their people); a Company column links or creates the company once; custom values are checked by their definitions. A contact is matched by email, else phone; a company by name, else website domain; a deal by name and company; the admin chooses skip, update or create, and a repeat in the file is reported against its first row. An import records one `data.imported` event, never a `contact.created` per row, so it starts no automations; each run is kept in `data_imports`. Exports of contacts, companies, deals and tasks carry company names, a deal's people and custom fields by label, and import straight back. Companies are edited, archived and restored from their side panel, with Show archived on the Companies tab; a new website brings its domain. | TESTED | `backend/data_transfer.py` (new; joins the blocking type-check set), `backend/crm_core.py` (old import/export removed; company domain follows its website), `frontend/src/pages/ImportExport.jsx` (new), `frontend/src/pages/Directory.jsx`, `frontend/src/pages/Pipeline.jsx`; `backend/tests/test_data_transfer.py` (19 tests) and a company edit/archive test and the original import tests in `test_crm_core.py`, which pass unchanged against the new engine; browser pass (Playwright, local stack): import with matching, the duplicate choice, export, company edit/archive/restore and a member's view at 1440 and 390 px in light and dark, 15 views with no console error or sideways scroll. Not deployed. | DIRECTIVE 2026-10-26 (owner: "go 1" — self-serve data: import with field mapping, company editing, exports; §1.5 must-haves 11 and 14) |
| C-34 | Today plan — `GET /api/today?tz=` ranks one person's day from recorded facts, each item with its reason: new leads oldest first (three by name, the rest summed), appointments starting within 2 hours, overdue tasks, approvals waiting (admins), at-risk or breached commitments, tasks due today, and open deals with no activity for 14 days and no task. Tasks are the caller's plus unassigned ones; "today" ends at midnight in the caller's time zone. It also returns the screen's figures (leads waiting and the oldest wait, bookings this week by kind, open and probability-weighted pipeline per currency, approvals and risks), leads with their next appointment, the week's appointments, stage counts and values, tasks and at-risk commitments. The `/dashboard` page becomes **Today** | DEPLOYED | Merged in PR #45 (`main@4873f67`) and deployed 2026-10-19 (Railway deployment `21d4b7b5-…`, SUCCESS 09:28Z; §3.2). `backend/today.py` (in the blocking typecheck set), `frontend/src/pages/Dashboard.jsx`; `backend/tests/test_today.py` (11 tests: ranking and reasons, the summed lead item, task scope for a member, time-zone day boundary, appointment preparation, weighted pipeline, stalled deals, admin-only approvals, tenant isolation). Browser run on local data at 1440 px light and dark and 390 px: no horizontal scroll, no console errors. | DIRECTIVE 2026-10-19 (owner feature scope, §1.5 value-add 5) |
| C-33 | Custom fields, filters, saved views and lifecycle — an admin defines typed fields (text, long text, number, date, choice, yes/no, email, phone, web address) on contacts, companies and deals with stable keys `cf_<slug>` (`GET/POST/PATCH /api/custom-fields`); values are checked against their type on every record `PATCH` (`custom_fields`) and stored beside form answers, with history; archiving keeps values. Lists take `?where=` filters (`GET /api/contacts`, `/api/companies`, `/api/opportunities`) compiled on the server against an allow-list of built-in and the tenant's own fields. Saved views (`GET/POST/PATCH/DELETE /api/views`) store filters, columns and order, shared or private; only the maker or an admin changes one. Contacts carry a lifecycle stage: website/booking contacts start as `lead`, winning a deal makes `lead`/`qualified`/unset contacts `customer`, and a clean-up action sets unset stages from history. Screens: Contacts views, filter builder, columns, **Settings → Fields**, **"More fields"** on contact, company and deal records | DEPLOYED | Merged in PR #45 (`main@4873f67`) and deployed 2026-10-19 (Railway deployment `21d4b7b5-…`, SUCCESS 09:28Z; §3.2). `backend/record_fields.py`, `backend/crm_core.py`, `backend/server.py`, `backend/website_forms.py`; `frontend/src/components/ListViews.jsx`, `frontend/src/components/CustomFields.jsx`, `frontend/src/pages/CustomFieldsSettings.jsx`, `frontend/src/pages/Directory.jsx`; `backend/tests/test_record_fields.py` (15 tests: typing, admin-only definitions, tenant isolation, filters including refused fields and regex text, views sharing and permissions, lifecycle). Browser run on local data: filter, columns, save, reload of a saved view, record fields, Fields page; no horizontal scroll at 390px. | DIRECTIVE 2026-10-19 (owner feature scope, §1.5 must-haves 1, 2, 9) |
| C-32 | Data integrity — one open deal per person across forms and bookings (`opportunity.reuse_open_deal`, default on); a form or booking from an existing client (company with a Client 360 workspace, or a won deal) opens no deal and gets a "Reply to client" task; a **Company** catalogue field on forms and booking pages that links or creates the company, and linking by work email domain (personal domains never link); contacts clean-up suggestions and actions (`GET /api/contacts/cleanup`, `POST /api/contacts/cleanup/apply`) and a repeat-safe merge (`POST /api/contacts/{id}/merge`) that moves deals, tasks, activities, enquiries, appointments and conversations; new booking pages default to the neutral `meeting` preset, and only real-estate pages value deals at commission | DEPLOYED | Merged in PR #45 (`main@4873f67`) and deployed 2026-10-19 (Railway deployment `21d4b7b5-…`, SUCCESS 09:28Z; §3.2). `backend/crm_core.py`, `backend/website_forms.py`, `backend/booking.py`, `frontend/src/components/ContactCleanup.jsx`, `frontend/src/pages/Directory.jsx`, `frontend/src/pages/Leads.jsx`; `backend/tests/test_data_integrity.py` (15 tests through the public form and booking doors). Found by loading data through the real doors on 2026-10-19: a form fill then a booking opened two deals; an existing client's check-in opened a new $0 deal; companies typed into forms were never created; a page made without a preset inherited "Confirm the showing… arrange access to the property". | DIRECTIVE 2026-10-19 (owner feature scope, §1.5 must-haves 1, 2, 11) |
| C-31 | In-process scheduled jobs — the API runs every `/api/cron/*` job itself on the workflow's cadences, once per window across replicas under a MongoDB lease, recorded in the cron ledger as `origin: in_process`; it skips a window an external request already ran | DEPLOYED | `backend/scheduler.py`, `backend/tests/test_scheduler.py`; `IN_PROCESS_SCHEDULER=0` turns it off; `scripts/validate_config.py` checks its job table against `.github/workflows/scheduled-jobs.yml`. Merged in PR #38 (`main@b854059`) and deployed 2026-10-18 (deployment `a65dc4e1-…`): `In-process scheduler started for 13 job(s)`, and its deferral to external runs is in the boot log (§3.2). | DIRECTIVE 2026-10-17 (owner: finish the client product) |

### 4.B Approved module contracts — registered, not yet built

These were declared in `frontend/src/platform/modules.js` as `contract_pending` and are therefore approved scope with a named contract. All are `APPROVED — NOT STARTED` **except M-07 and M-05**, which carry their own status in the Status column below.

| ID | Module | Declared contract | Status | Expansion role |
|---|---|---|---|---|
| M-01 | Email | `CommunicationMessage service` | **BLOCKED — OWNER INPUT** | The email adapter is now **deployed** at `c9f5a6e`: `backend/gmail_provider.py` (`GmailChannelProvider`, 17 tests; boot log `Registered outbound channel provider: gmail`) sends through the existing `CommunicationMessage` contract with a deterministic Message-ID per dispatch and a pre-send duplicate check; inbound replies are ingested by `backend/email_inbound.py` (23 tests) via `POST /api/cron/inbound-email`, with ambiguous mail parked at `GET /api/inbound/unmatched`. Still blocked (re-verified 2026-09-30): **(1) Google grant (owner, O-01).** The stored Google grant failed to refresh on 2026-09-30 (Google answered HTTP 400 at 16:08Z), and no Google sync appears in the 2026-10-19 production log. The owner must reconnect, granting `gmail.send`; since PR #42 the connection records the scopes Google granted, which the send guard checks. **Done 2026-10-19:** the owner reconnected at 02:02Z with `gmail.send` (O-01), and the inbound sweep read the inbox at 17:40Z (§3.2). **(2) Email sending switch (owner).** The tenant's Gmail catalogue record must be moved out of `REQUIRES_CONFIGURATION`; until then `authorized_channels` refuses email with `channel_not_authorized`. An admin does it with **"Send test & turn on"** on the Gmail row, which certifies the record only after Gmail accepts a test email from the connected mailbox to itself, and records `integration.sending_enabled` (§8 #28, manual §5.10). **(3) No UI for an owner-written message.** No UI creates a conversation, records consent, or drafts a message. The screens release only system-written email: Calendar booking emails (M-05) and an approved Website Forms auto-reply (C-30), both still subject to (1) and (2). A live send-and-reply test therefore needs engineer-assisted API calls today (manual Appendix C; §8 #27). Inbound polling runs in-process (C-31). |
| M-02 | Unified Inbox | `Conversation service` | DEPLOYED | `backend/conversations.py`. Tenant-scoped threads with participants, channel, status, assignment, the agent/human boundary, a per-channel consent record, provider-thread deduplication, and an inbound path that reopens a closed thread. Operator surface at `/operations`. 29 tests. |
| M-03 | SMS | `Message delivery service` | **BLOCKED — OWNER INPUT** | Same position as M-01: the message model and delivery interface exist; no SMS provider is registered in the integration catalogue and none has been chosen (O-06 covers the adjacent telephony decision). |
| M-04 | Calling | `Call activity service` | APPROVED — NOT STARTED | Phone execution (E-06), missed-call recovery (E-02) |
| M-05 | Calendar | `Calendar event service` | DEPLOYED | Online booking, merged in PR #38 (`main@b854059`) and deployed to Railway 2026-10-18 (deployment `a65dc4e1-…`, `booking-reminders` among the in-process jobs). Not `LIVE VERIFIED`: no production booking has been made yet. `backend/booking.py`; `frontend/src/pages/Calendar.jsx`, `PublicBooking.jsx` (`/book/:key`), `ManageBooking.jsx` (`/booking/manage/:token`); guide `docs/BOOKING.md`. Booking pages (event types) with duration, buffers, minimum notice, horizon, slot interval, location, one host or round-robin, website-forms catalogue questions, a deal at expected commission and a preparation task; four real-estate presets (home showing 30 min, buyer consultation 45, listing appointment 60, phone call 15). Per-agent weekly hours and days off in the agent's own zone; slots computed in UTC, DST-correct, minus the agent's appointments with both bookings' buffers. A CORS-open public door without credentials (honeypot, fill time, rate limits, idempotency key) that cannot double-book: a per-agent lock around re-check and write, backed by a unique index on the active (agent, start) claim. Each booking runs through C-30's pipeline (contact, owner, deal, `lead.received`) and lands in the shared `appointments` collection, so E-23's cancelled-appointment and no-show lanes see it; the no-show lane now also reads a recorded `no_show`. Signed single-booking manage links (view, reschedule, cancel), an `.ics` file and a Google Calendar link; agents mark attended / no-show, cancel or reschedule. Reminders (24 h and 1 h by default) claimed exactly once: `booking.send_due_reminders`, the in-process scheduler's `booking-reminders` job and `POST /api/cron/booking-reminders`. Google Calendar busy times are subtracted for the agent whose calendar is connected; C-17 remains owner-blocked, so that path is unverified live. **Emails to the person do not ride a standing approval** — the M-07 amendment covers only the website-form auto-reply — so each confirmation, change notice and reminder gets its own consent record and single-use approval and is sent through `attempt_delivery` only after an admin approves its exact words; with no email channel authorised nothing is drafted. Evidence: `backend/tests/test_booking.py` (37 tests) and a 30-check real-browser run at 390 px and 1440 px (two visitors racing for one time, the page framed on another origin). Adapted from §5 #14 (`calcom/cal.diy`, MIT): the model only, no code copied, Cal not run. Expansion role: meeting intelligence (E-12). |
| M-06 | Workflows | `Workflow definition and run services` | APPROVED — NOT STARTED | Durable work queues (E-04), orchestration (E-15) |
| M-07 | Approvals (module surface) | `Approval queue service` | DEPLOYED | `backend/approval_queue.py`. Built on C-09's own `approvals` collection rather than beside it, so a request raised by `POST /api/approvals`, by an agent, or by an MCP level-2 write is one record with one state machine. Adds a bound action (an approval authorises *that* action, not a category), single-use consumption via an atomic claim so concurrent workers produce exactly one execution, expiry evaluated on read as well as by the sweep, database-enforced deduplication, requester provenance, risk tier, optional separation of duties, and a full decision history. **An approval never unblocks a missing prerequisite**: consumption re-checks the recorded blocks and refuses. 27 tests. **Amendment 2026-10-17 (owner direction, confirmed by the owner the same day):** a *standing approval* may authorise exactly one website-form auto-reply template (subject and body, fingerprinted). Each reply rendered from it still gets its own conversation, consent record and single-use approval decided by `standing-approval:<id>` with the fingerprint and merge values recorded, and still passes every `attempt_delivery` check; only `{first_name}`, `{agent_name}` and `{form_name}` are substituted; editing the template voids the approval. No other action may ride a standing approval (C-30). |
| M-08 | Revenue Operations | `Revenue ledger and forecast services` | DEPLOYED (attribution ledger) / APPROVED — NOT STARTED (forecast) | Recovery attribution (north-star step 10) is **deployed** at `c9f5a6e`: `backend/attribution.py`, `POST /api/attribution/outcomes`, `GET /api/attribution/entries\|totals`, `GET\|PUT /api/attribution/window`; 26 tests, including adversarial attempts to claim unearned credit. Only a provider-accepted message counts as contact; no confidence score is produced. Never exercised against production data. The forecast half of the contract is not started. |
| M-09 | Support | `Case and SLA services` | APPROVED — NOT STARTED | Omnichannel handoff |
| M-10 | Reporting | `Metric and report services` | DEPLOYED (recovery proof) / APPROVED — NOT STARTED (agent measurement) | Recovery measurement is **deployed** at `c9f5a6e`: `backend/recovery_proof.py`, `GET /api/proof/portfolio`, `/api/proof/traceability`, `/api/proof/cases/{case_id}`, the `/proof` page; 12 tests. Potential and confirmed value are reported separately with no combined total. Agent measurement is not started. |
| M-11 | Relationship Intelligence | `Recommendation service v1` | APPROVED — NOT STARTED | Next Best Action backend (E-05) |
| M-12 | Migration | `Import job and reconciliation services` | APPROVED — NOT STARTED | Onboarding new tenants |
| M-13 | Knowledge | `Knowledge item service` | APPROVED — NOT STARTED | Agent context for recovery outreach |

### 4.C Expansion capability register

| ID | Capability | Status | Provenance | Notes |
|---|---|---|---|---|
| E-01 | **Second Chance** — missed-opportunity / dormant-and-lost revenue recovery (the ten-step north-star workflow end to end) | **BLOCKED — OWNER INPUT** | RECOVERED — ClickUp `CONTROL — W2` §11 | Every step now has deployed code at `c9f5a6e`: detection (E-02…E-04, E-23), strategy composition (E-20), approval (M-07), execution (E-22), outbound email (M-01 adapter), reply ingestion (M-01 inbound), attribution (M-08) and proof (M-10). It has **never run end to end**, and cannot until the scheduler runs (O-03, O-16) and `gmail.send` is granted (O-01). No step is `LIVE VERIFIED`. |
| E-02 | Missed-call recovery | DEPLOYED (detection) / BLOCKED — OWNER INPUT (telephony) | DIRECTIVE 2026-09-15 (corroborated by the public product promise on `clientverse.io`: "cannot afford a missed call") | Detection is **deployed** at `c9f5a6e`: call logs are captured through `POST /api/intake/calls` (`backend/recovery_intake.py`) and `detect_missed_calls` in `backend/detectors.py` opens a Recovery Case, run by `POST /api/cron/detect-recovery`. Call capture is an intake API, not a telephony integration; recovery by phone still needs the telephony and consent decision (O-06, E-08 → M-04). Recovery by email follows M-01. |
| E-03 | Stalled-lead recovery | DEPLOYED | RECOVERED — ClickUp §11 ("dormant or lost opportunity"); UX assessment ("opportunity has no future activity") | `backend/second_chance.py`. Deterministic rule: an open opportunity with no qualifying activity (event, stage change, or update) for `SECOND_CHANCE_STALLED_LEAD_DAYS` (default 14). Emits an explainable reason, an `opportunity:<id>` source reference, and a deduplicated durable work item. Closed stages are out of scope. No outbound communication. 13 tests. |
| E-04 | Missed-follow-up recovery | DEPLOYED | RECOVERED — C-06 commitment-risk evaluation exists and is the seed signal | `backend/second_chance.py`. An unresolved commitment or delivery task past its due date plus a configurable grace window becomes a recovery candidate with overdue days, owner and source reference. No outbound communication. |
| E-05 | Durable autonomous work queues | DEPLOYED | DIRECTIVE 2026-09-15 | `backend/work_queue.py`. MongoDB-backed, tenant-scoped, explicit state machine (`queued`/`claimed`/`processing`/`completed`/`retry_scheduled`/`failed`/`dead_letter`) with a rejected-transition matrix, atomic single-winner claim, leases with crash recovery, exponential capped backoff, dead-letter, database-enforced idempotency key, dedupe key, acknowledgement/resolution, admin replay, operator stats, bounded concurrency and round-robin per-tenant fairness. Worker tick at `POST /api/cron/work-queue`. 20 engine tests + API tests. |
| E-06 | Scheduled agent follow-up | APPROVED — NOT STARTED | RECOVERED — ClickUp §11 step 9 ("continue permitted follow-up") | E-05 and M-07 are now delivered, so this is unblocked technically. It still requires an authorised outbound channel (M-01 or M-03) before a follow-up can leave the CRM. |
| E-07 (NBA-1) | Next Best Action / agent task routing (backend service + aggregate queue) | DEPLOYED | RECOVERED — UX assessment P0 #3 | `backend/next_best_action.py`. Tenant-scoped records from six deterministic rules (commitments, approvals, overdue tasks, Second Chance work items, degraded integrations, client health), each with reason, cited `source_refs`, evidence and a fixed priority band. Lifecycle `new`/`accepted`/`dismissed`/`completed`/`snoozed` with outcome and note; generation refreshes explanation without trampling feedback and retires cleared conditions. No fabricated confidence score. Surfaced in Client 360, the Command Center and `/operations`. 14 service tests + API tests. |
| E-08 | Phone execution / phone agent capability | APPROVED — NOT STARTED | DIRECTIVE 2026-09-15 (module M-04 pre-registers the surface) | Telephony provider is an unmade owner decision. Consent, recording, and jurisdiction policy must precede any build. |
| E-09 | Omnichannel conversations | **BLOCKED — OWNER INPUT** | RECOVERED — module registry M-01/M-02/M-03; ClickUp §10 "communications surface" | The first channel adapter is deployed: email (M-01, `GmailChannelProvider` + inbound ingestion). It cannot carry traffic until `gmail.send` is granted (O-01). SMS and phone have no provider (M-03, O-06). |
| E-10 | Human handoff | DEPLOYED | RECOVERED — ClickUp §10; Command Brief (approvals/undo) | Both halves exist. The approval gate is M-07, reusing C-09's `approvals` collection rather than a parallel gate; the conversation-level handoff is `conversations.handoff` — an explicit, audited state change with an actor and a reason, never an implicit consequence of somebody replying. **Limit stated plainly:** handoff operates on conversations that cannot yet send externally, so today it is exercised on internal threads and on drafts waiting for a channel. |
| E-11 | Agent workforce roles surfaced in CRM | APPROVED — NOT STARTED | RECOVERED — ClickUp §10 "agent workforce/activity surface"; `Clientverse-AI-AGENT-Workforce` implements nine roles (operations, sales, marketing, support, engineering, research, browser, project_management, communications) | The workforce runtime is a **separate repository and separate lifecycle**. The CRM consumes it across a contract; it is not merged into the CRM. |
| E-12 | Security scanning before external skills/MCPs are trusted (dual NVIDIA + Cisco gate) | DEPLOYED (pipeline) / BLOCKED — OWNER INPUT (scanners) | DIRECTIVE 2026-09-15; architectural need corroborated by the AI Project Governance Blueprint v2 "third-party intake/security gate" (Slack, 2026-09-13) | `backend/security_gate.py`. Intake registry plus Gate A (16 supply-chain checks) and Gate B (14 capability/execution checks), the full state machine (`DISCOVERED`/`UNDER_REVIEW`/`REJECTED`/`QUARANTINED`/`APPROVED_LIMITED`/`APPROVED`/`REVOKED`), decisions bound to an exact source and version with expiry, and enforcement on `POST /api/mcp/invoke` for any tool marked external. **Approval is impossible while a required scanner is unconfigured — an unrun scanner is never treated as a pass** (owner blocker O-13/O-14). Provenance conflict remains as recorded in §7.2. 24 tests. |
| E-13 | OSINT / intelligence enrichment | APPROVED — NOT STARTED | DIRECTIVE 2026-09-15 (ClickUp §10 approves a "research/intelligence surface" generically) | Data-protection and lawful-basis review required before any build. |
| E-14 | SEO / growth intelligence | APPROVED — NOT STARTED | RECOVERED — ClickUp §10 "contextual growth/video/SEO actions **where approved**" | The ClickUp clause is conditional. Treat the 2026-09-15 directive as the approval that satisfies "where approved". |
| E-15 | Video-agent capability | APPROVED — NOT STARTED | RECOVERED — ClickUp §10 (same conditional clause); ClickUp §11 step 7 ("generate personalized media/content when useful") | Serves north-star step 7. |
| E-16 | Meeting intelligence | APPROVED — NOT STARTED | RECOVERED — ClickUp §10 "meeting intelligence surface" | Capability is approved; its **source repository is unresolved** — see §7.1. Requires M-05. |
| E-17 | CRM feature/UX enhancements mined from Twenty | APPROVED — NOT STARTED | DIRECTIVE 2026-09-15 | Pattern mining only. No code copy, no data-model adoption, no dependency. |
| E-18 | n8n-based orchestration | APPROVED — NOT STARTED | RECOVERED — the workforce repo ships an n8n adapter and four `cvw-*` workflows; `ebyron357/n8n` is a registered active component | **No n8n integration exists in the CRM repository.** Approved only as an execution edge behind an explicit CRM-side contract. |
| E-19 | Slack / ClickUp handoffs | APPROVED — NOT STARTED | RECOVERED — canonical operating contract (ClickUp = task/status plane, Slack = operator/alert plane); workforce repo ships both adapters | **Not present in the CRM.** The CRM contains only a seeded registry record `Slack Notifier` (status `BETA`) — a catalog entry, not an integration. |
| E-20 | Recovery strategy composer (north-star steps 2–4) | DEPLOYED | RECOVERED — ClickUp `CONTROL — W2` §11 steps 2–4 ("gather authorized context", "evaluate the account and its history", "recommend a recovery strategy") | `backend/recovery_strategy.py`. Reads only tenant-owned CRM records — no external lookup and no enrichment. An ordered playbook of six named lanes (`commitment_repair`, `delivery_recovery`, `commitment_repair_first`, `dormant_nurture`, `owner_led_reengagement`, `written_followup`, plus an explicit `needs_human_triage` fallback) selects a lane by stated entry conditions; the output names the rule and cites every fact to the record it came from. **No score, no confidence, no model judgement.** Each step declares the channel it needs and is marked `blocked` with the reason when that channel is not authorised for the tenant. Composition raises an M-07 approval request; it never sends. 25 tests. |
| E-21 | Recovery Case + normalized recovery-event foundation | DEPLOYED | DIRECTIVE 2026-09-16 (Phase 1 execution authorization) | `backend/recovery_case.py`. One normalized event contract for all ten declared sources, and the Recovery Case the event becomes. **Removes the requirement that a recovery opportunity originate as an internal CRM record**: `contact_id`, `company_id`, `opportunity_id` and `workspace_id` are all optional, so a missed call known only by a phone number is a first-class case. Case identity is (tenant, source, source event) with a unique index, so concurrent workers produce one case. Every tenant-owned reference is ownership-checked at creation and at resolution. **Potential and confirmed value are separate fields**; confirming recovered revenue requires evidence. Transitions reuse the existing domain-event log. The two existing detectors emit cases without losing their work items, and `recovery_strategy.compose_for_case` lets a case with no CRM context reach the planner. 61 tests. |
| E-22 | Recovery runner (execution to the provider boundary) | DEPLOYED | DIRECTIVE 2026-09-16 (Phase 1 follow-on) | `backend/recovery_runner.py`. Claims an approved Recovery Case off the durable queue and walks its plan: internal steps are **executed** (a task lands against the case), outbound steps are **drafted into a conversation and stop at the provider boundary** with the refusal named. Each outbound message raises its own M-07 approval carrying the exact text — the plan's approval authorised a motion, not a sentence. The plan's approval is re-read at run time, so a withdrawn approval halts execution rather than relying on the case's state flag. Idempotent per case and per step: a replayed job adopts the existing draft and task instead of producing a second copy. The case reaches `executing` and no further — `engaged` would mean a counterparty engaged, and none can be reached. Worker handler + `POST /api/cron/recovery-runner` + `POST /api/recovery-cases/{id}/run`. 15 tests. |
| E-23 | Recovery intake and the remaining detector families — web enquiries (including a public token-scoped intake), unanswered quotes, unanswered estimates, no-response, cancelled appointments, no-shows, external CRM events | DEPLOYED | DIRECTIVE 2026-09-16 (the ten declared recovery sources, E-21) | `backend/detectors.py` (32 tests; about half assert the lanes do **not** fire on ordinary business) and `backend/recovery_intake.py` (`/api/intake/calls`, `/api/intake/web-enquiries`, `/api/intake/public/{token}/web-enquiries`, `/api/intake/tokens`, `/api/intake/external-events`). All families run from `POST /api/cron/detect-recovery` and open cases through E-21, deduplicated on (source, record). Detection sends nothing. Has never run in production (O-03, O-16). |

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
| 14 | `calcom/cal.diy` (MIT) | ADAPT | M-05 | Booking-page model: event types with duration and buffers, weekly availability, minimum notice, slot computation in the booker's time zone, confirmation and reminder flow | Running Cal as a second app or database; its auth and team model. MIT: keep the copyright notice on any code adapted verbatim |
| 15 | `documenso/documenso` (AGPL-3.0) | WATCH | C-15 (documents), C-30 (buyer agreements) | E-signature as a separate service behind a CRM-side contract: send, signed/declined webhooks, signed-PDF retrieval | Copying its code into ClientVerse (AGPL would extend to the CRM). Blocked on an owner hosting decision |
| 16 | `pipecat-ai/pipecat` (BSD-2) | WATCH | M-04, E-08, E-02 | Voice-agent pipeline for consented speed-to-lead calls: turn-taking, interruption, tool calls into CRM booking | Any call without recorded consent, or outside M-07 and E-12. Blocked on O-06 (telephony and consent policy) and a provider account |
| 17 | `puckeditor/puck` (MIT) | ADAPT | C-30 (landing pages), E-14 | Visual editor for tenant landing pages whose forms post through C-30's pipeline | Pages that bypass C-30 intake, consent or rate limits |
| 18 | `knadh/listmonk` (AGPL-3.0) | WATCH | M-01, E-06 | Listing-alert and nurture campaigns as a separate service fed by consented CRM segments | Copying its code; sending to contacts without email consent |
| 19 | `umami-software/umami` (MIT) | EXTRACT | E-14 | Privacy-first page and campaign analytics joined to C-30 attribution | Cookies or tracking without the site's consent banner |
| 20 | `resend/react-email` (MIT) | ADOPT | M-01, C-30 | Branded templates for auto-replies, lead alerts and digests | Templates that skip the delivery choke point or M-07 approval |
| 21 | `papermark/papermark` (mixed licence) | WATCH | C-15 | Document-view analytics (who opened a price analysis and for how long) as a hot-lead signal | Any use before its licence split is reviewed |
| 22 | `nateherkai/scroll-craft` | EXTRACT | Agent websites (outside the CRM); C-30 landing-page templates later | Design workflow and page grammars for scroll-driven sites, read and reviewed before use | Running its scripts or image-generation calls unreviewed; it is an external agent skill, so §6 applies before any runtime use |


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
#14–#22 were proposed on 2026-10-17 and approved by the owner ("lead the way") as the
next sources of value for real-estate tenants. ADAPT for #14 and #17: both are MIT, and
ClientVerse re-implements the approach inside its own tenancy rather than running them.
WATCH for #15 and #18: both are AGPL-3.0, so they may only ever run as separate services
behind a CRM-side contract, never as copied code, and both wait on an owner hosting
decision. WATCH for #16: telephony waits on O-06. ADOPT for #20: a template library,
MIT, with no runtime reach. EXTRACT for #19 and #22: patterns only. #21's licence mixes
AGPL and a commercial edition and must be reviewed first.

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
11. Recovery attribution ledger: recovered / lost / pending revenue per candidate, per lane, per period. (E-01 step 10, M-08)

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
24. ~~Exact-head CI + deployment evidence for the current `main`, and production exposure of the runtime SHA.~~ **DELIVERED 2026-10-24:** *Production acceptance* checks production's `git_sha` against the released commit (run `40134314474`: `6d0d4c6`). (§3.1, §3.2)
25. ~~Two-company production tenant-isolation smoke on the current approved release.~~ **DELIVERED 2026-10-24:** *Production acceptance* registers two organizations on production and proves the second cannot read the first's lead, deal or contact (404), on every run. (ClickUp §8)
26. Every new surface registered in `CLIENTVERSE_MODULES` with a truthful state before its route ships. (§1.3)

**Owner operability** (found by the owner-manual audit, v1.16; see the manual's §7.21)
27. An owner-facing screen for the outbound email path: create an email conversation with a contact, record consent (admin, with basis), draft, request approval, send, and view unmatched inbound mail. Every step exists as an API (`/api/conversations`, `/api/conversations/{id}/consent`, `/api/conversations/{id}/messages`, `/api/messages/{id}/request-approval`, `/api/messages/{id}/send`, `/api/inbound/unmatched`), but `frontend/src/pages/Operations.jsx` calls only handoff and close; only booking emails (`Calendar.jsx`) and the form auto-reply (`WebsiteForms.jsx`) can be released from a screen. Until this exists, a live send test is engineer-assisted (manual Appendix C). (M-01, E-09, M-02)
28. A governed, audited certification control for a tenant's integration catalogue record. Outbound email needs the `integrations` record `Gmail` to be out of `REQUIRES_CONFIGURATION` (`recovery_strategy.CONFIGURED_INTEGRATION_STATUSES`), and nothing but a direct database change can do that today. It should be an admin action that records who certified it and when. (M-01, O-01) **Built 2026-10-19:** `POST /api/integrations/gmail/sending/enable` and `/disable` (admin), shown on the Gmail row; turning on requires Gmail to accept a test email to the connected mailbox, and disconnecting Gmail or reconnecting without `gmail.send` or with another mailbox turns it off. Each change is a domain event (manual §5.10).
29. Record-level edit, archive/restore, CSV import/export and record search in the UI. *Partly delivered by PRs #38–#41:* contacts and deals are edited and archived/restored in their side panels, and leads export as CSV. *C-39 (`TESTED`, not deployed) adds* company edit and archive, CSV import with field mapping, and export of contacts, companies, deals and tasks. Still missing: record search in global search (`/api/search`). (C-27, C-39)

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
| O-01 | Google OAuth not configured | Google Cloud: enable Gmail + Calendar APIs, consent screen, OAuth web client with callback `https://<production-origin>/api/integrations/google/callback`; set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` in Railway; authorize a least-privilege test account. **2026-09-30:** the client is configured (boot log registers the Gmail provider), but the stored grant fails to refresh (Google token endpoint 400 at 16:08Z). Re-authorize from **Registries** → **Integrations**, ticking the send permission. If it recurs about weekly, the consent screen is in Testing mode (7-day refresh-token expiry). **2026-10-19:** no Google sync in the production log; since PR #42 the connection records the granted scopes, so a connection made before 838f00d's deployment must be renewed once. **2026-10-19 02:02Z:** the owner reconnected on `crm.clientverse.io`; the callback's grant includes `gmail.readonly`, `gmail.send` and `calendar.readonly` (Railway log). Manual §5.6–§5.10 | C-17, E-16 |
| O-02 | Stripe test credentials absent | Stripe: test-mode restricted key + webhook endpoint `https://<production-origin>/api/integrations/stripe/webhook` for `payment_intent.succeeded\|payment_failed\|canceled`; set `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET` | C-18, M-08 |
| O-03 | No external scheduler | **Resolved (observed 2026-10-18):** the workflow calls production with HTTP 200 (§3.2, C-25), so both secrets are set; the in-process scheduler (C-31) would run every job even without them. The workflow first reached production on 2026-09-30 (runs #3551–#3555, after #3544–#3550 failed on a `401` secret mismatch). It **fails loudly** when a secret is missing, when no request reaches production, or when production has no ledger entry for the run (§3.3). Owner check: manual §11.4. Previously: **reduced to two repository secrets.** `.github/workflows/scheduled-jobs.yml` now drives every cron endpoint on the documented cadences; the owner only adds `CLIENTVERSE_PRODUCTION_URL` and `WEBHOOK_CRON_SECRET` under repository secrets. With either missing the workflow exits cleanly without calling anything. A dedicated scheduler may replace it; disable the workflow if so. **Until the secrets exist the durable queue has no worker in production and recovery candidates are only produced on demand.** | C-08, C-16, E-03, E-04, E-05, E-06, NBA-1 |
| O-04 | Admin credential rotation outstanding | Rotate `ADMIN_PASSWORD` in Railway after first login (`seed()` re-syncs the hash each boot) | Security hygiene |
| O-05 | Legacy secret + variable cleanup | Rotate the preview Stripe webhook secret recoverable from pre-redaction git history; delete the superseded misspelled `Mongo_url` variable | Security hygiene |
| O-06 | Telephony/consent policy undecided | Choose the telephony provider and approve the call consent, recording, and jurisdiction policy | E-08, E-02, M-04 |
| O-07 | OSINT lawful basis undecided | Approve the lawful basis, permitted sources, retention, and provenance requirements for contact enrichment | E-13 |
| O-08 | n8n instance not designated | Designate the n8n instance and its credential boundary | E-18 |
| O-09 | Slack/ClickUp app credentials | Provide workspace app credentials scoped to the CRM integration | E-19 |
| O-10 | Meeting-intelligence source unknown | Supply the exact DodoNote / meeting-intelligence repository URL | E-16 |
| O-11 | AI provider key absent | Provide `EMERGENT_LLM_KEY` (or approve an alternative provider) | C-19, and the AI-assisted parts of E-01 steps 3–4 |
| O-12 | Custom domain / DNS | **Done 2026-10-19:** `crm.clientverse.io` is verified on the Railway service (certificate valid, CNAME propagated). Railway sets `FRONTEND_URL` and `GOOGLE_REDIRECT_URI` to it and `CORS_ORIGINS` to both addresses (manual §2.1, §10.2). Google accepted the new callback (Railway HTTP log, 01:42Z), so it is registered in Google Cloud. Open: a successful Google connection through it (O-01) | Production origin finalization |
| O-13 | Security-gate tooling verification | Confirm that the 2026-09-15 approval of NVIDIA SkillSpector and the Cisco scanners supersedes the 2026-09-13 "unapproved until verified" record, and authorize their use | E-12 (§7.2) |
| O-14 | Security-gate scanners not configured | Provide reachable endpoints for `SECURITY_GATE_NVIDIA_SKILLSPECTOR_URL`, `SECURITY_GATE_CISCO_SKILL_SCANNER_URL` and `SECURITY_GATE_CISCO_MCP_SCANNER_URL`. The gate refuses every approval while any required scanner is unconfigured, which is the intended safe default, so no external component can be trusted until this is done. | E-12 execution |
| O-15 | Production is unreachable from the agent environment | None, if the owner is content for deployment to run elsewhere. The session egress policy blocks `railway.app` and `backboard.railway.com`, so production deploy/verify must be run from an environment that can reach Railway (CI, the owner's machine, or a differently-scoped agent session). This is `BLOCKED — TECHNICAL`, not an owner decision. | Current-head deployment and production certification |
| O-16 | GitHub Actions executes nothing | **Resolved (observed 2026-10-18):** CI and `Scheduled jobs` run and pass again (PR #38's checks; scheduled runs 8174–8178). Scheduled runs had first executed again on 2026-09-30 (#3544 onward). Previously: since 2026-09-27T22:35Z every job on every branch (CI and Scheduled jobs) completes as `failure` in 2–4 s with `runner_id: 0` and no log; it began between two scheduled runs of the same unchanged commit. Restore Actions: GitHub → Settings → Billing and plans (Actions spending limit / payment), and the repository's Settings → Actions → General | CI as a merge gate; C-25 and therefore every scheduled cron endpoint (O-03) |
| O-17 | The scheduler's address is a Vercel copy, not production (found 2026-10-24) | Set GitHub secret `CLIENTVERSE_PRODUCTION_URL` to `https://crm.clientverse.io`. Agent sessions cannot write repository secrets. | The external scheduler no longer depends on the Vercel project |
| O-18 | Vercel project `clientverse-crm` (team `tradeiq`) publishes a second, non-working sign-in page at `clientverse-crm.vercel.app` on every push | After O-17, delete the project (recommended), or remove its `REACT_APP_BACKEND_URL` so it uses its `/api` forwarding | One front door: `crm.clientverse.io` |

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
| 1.29 | 2026-10-26 | Added C-39 (self-serve import and export, and company editing; `TESTED` on branch). §1.5 must-haves 11 and 14 and §8 #29 updated. Manual v1.14 (§4.3, §7.4, §7.20, §7.21, §8.1). |
| 1.28 | 2026-10-26 | Restores the record of the 2026-10-19 deployments of PR #45 (`4873f67`) and PR #46 (`394f095`), which the 1.27 closeout merge had rolled back. §1.5 reports against `main@6d0d4c6` again, with the Phase 1 and 2 items as in production: must-haves 2, 7, 9, 12 and 14, value-add 5, 7, 10 and 14, and agency 2 and 3. C-32 to C-38 are `DEPLOYED`, each naming its deployment. §3.2 regains the two 2026-10-19 entries, and the §4 note again says which rows name a later deployment. The header lists PR #45 and PR #44 among the earlier heads, and M-01 records the 2026-10-19 reconnection and inbox read. Documentation only: no change to scope, status rules or owner actions. |
| 1.27 | 2026-10-24 | **Production closeout (PR #48, `main@6d0d4c6`).**<br>**Releases:** PR #47's intake repair, plus the gaps found in its review (C-30): alias precedence, budgets as one answer, list-picked and open-ended budgets, changed resubmissions, compare-and-set re-pricing and the form alert switches. Also: the prototype Google sign-in is retired (`410`); the job ledger is limited to the owner's organization; and UI fixes from an end-to-end browser pass (portal link shown and revocable, honest copy feedback, wide tables, contrast, the member MCP switch).<br>**New workflows:** *Production acceptance* and the *Backup and restore drill*. §8 #24 and #25 are delivered.<br>**Production:** verified from outside (§3.2).<br>**Pull requests:** PR #36 closed as superseded and PR #47 merged through #48 (§3.4).<br>**Owner items:** O-17 and O-18 added.<br>**Closeout package:** the owner manual v1.13 becomes Part 2 of the closeout package (§0.5). Nothing moves to `LIVE VERIFIED` under §12, because the Jev gate did not run. |
| 1.26 | 2026-10-19 | C-38: every sign-in response carries `workspace` and `acting` like `/auth/me` (the account switcher showed only after a reload); a password change inside a client account keeps that account and is recorded in the person's own workspace. |
| 1.25 | 2026-10-19 | Added C-38 (agency and client accounts; `TESTED` on branch); §1.5 agency 2 and 3 updated; C-37 loads host booking pages with the target workspace's team. |
| 1.24 | 2026-10-19 | Added C-37 (snapshots; `TESTED` on branch); §1.5 agency 3 updated. C-36 now loads through the shared setup loader. |
| 1.23 | 2026-10-19 | Added C-36 (industry templates; `TESTED` on branch); §1.5 must-haves 2 and 14 and value-add 14 updated. |
| 1.22 | 2026-10-19 | Added C-35 (automations with stop rules and run receipts; `TESTED` on branch); §1.5 must-have 7, value-add 7 and 10 updated. |
| 1.21 | 2026-10-19 | Added C-34 (Today plan; `TESTED` on branch); §1.5 value-add 5 and must-have 12 updated. |
| 1.20 | 2026-10-19 | Added C-33 (custom fields, filters, saved views, lifecycle; `TESTED` on branch); §1.5 must-haves 2 and 9 updated. |
| 1.19 | 2026-10-19 | Owner directive: ClientVerse is a CRM for any business, competing with ten named CRMs; real estate becomes one industry template (§1.1). Recorded the owner's feature scope of 34 items with status, gap and phase (§1.5). Added C-32 (data integrity, `TESTED` on branch). |
| 1.18 | 2026-10-19 | Email sending switch built (§8 #28, M-01 item 2): an admin certifies the Gmail catalogue record after a test email; it resets on disconnect or a reconnect that loses `gmail.send` or changes mailbox. Disconnecting Calendar no longer revokes the Google grant Gmail shares. O-01: the owner reconnected Google with send permission (02:02Z). |
| 1.17 | 2026-10-19 | Custom domain `crm.clientverse.io` live (§3.2, O-12): Railway variables `FRONTEND_URL`, `GOOGLE_REDIRECT_URI` and `CORS_ORIGINS` set; production redeployed as `e7790295-…`. No code change. |
| 1.16 | 2026-10-19 | **Owner/admin handoff** (PR #34, merged with `main` at v1.15). Registered [`docs/CLIENTVERSE_CRM_OWNER_ADMIN_MANUAL.md`](CLIENTVERSE_CRM_OWNER_ADMIN_MANUAL.md) (Issue #33) as the owner handoff source of truth: header, §0.1, §0.2 item 5 and §0.5. Superseded the owner-facing parts of twelve other documents with banners, and corrected `README.md`, `SECURITY.md` and `docs/RAILWAY_RUNBOOK.md` in place. The manual (v1.1) is re-verified against `main@838f00d`: in-process scheduler (C-31) with the workflow as an optional second driver, password change and admin reset of a temporary password, the redesigned screens (PRs #40/#41), Leads, Tasks, Website Forms and Calendar. §3.2 records the 2026-09-30 observations as history (the workflow first reached production; the stored Google grant failed to refresh) and the 2026-10-19 deployments of `1a39fa4` (`d4d2e07f-…`) and `838f00d` (`406f320e-…`, PR #42: a refused lookup never means "not sent"; the connection records the granted Google scopes, so the owner reconnects once). O-12 records the unverified `crm.clientverse.io`. C-16, C-25, O-03, O-16 and O-01 keep v1.15's status and gain those facts; C-25 and O-03 now say the workflow fails loudly (§3.3). **Corrected M-01** (§3.3): besides the grant, outbound email is held by an unrecorded certification gate — the tenant's Gmail catalogue record is seeded `REQUIRES_CONFIGURATION` and nothing but a direct database change alters it — and no screen composes an owner-written email or records consent. Added §8 #27–#29 for the owner-operability gaps the manual audit found (#29 is now partly delivered). Nothing moves to `LIVE VERIFIED`. |
| 1.15 | 2026-10-18 | PR #38 merged (`main@b854059`) and deployed to Railway (deployment `a65dc4e1-…`, SUCCESS, startup complete, `/api/health` 200). M-05 (Calendar) moves to `DEPLOYED`. Added C-31 (in-process scheduled jobs, `DEPLOYED`), which reconciles the sections v1.13 left open. C-25 moves to `DEPLOYED`, and O-03 and O-16 are resolved, all on observed evidence: the GitHub Actions scheduler calls production with HTTP 200 and ledger evidence ids, and the in-process scheduler skips a window it already ran (one-way: an external request after an in-process run still runs). Recorded the one 405 from the deploy swap. PR #38 also carried review fixes: Google sessions obey password rules; cookie-only writes must come from ClientVerse's own pages; the Google sign-in return runs only top-level on `/dashboard`; `.ics` text is escaped; booking email wording is shown only to the host or an admin; booking fill time counts from page open; reopened leads clear their response markers. Open owner decision: booking emails still carry the manage link into the tenant-wide inbox. Nothing moves to `LIVE VERIFIED`. |
| 1.14 | 2026-10-18 | M-05 (Calendar) moves to `TESTED` on branch: online booking pages with real free times, a public door that cannot double-book, bookings that become a lead, contact, deal and appointment through C-30's pipeline, manage links, `.ics` and Google Calendar links, agent outcome actions, and reminders sent exactly once (`booking-reminders` added to `backend/scheduler.py` and the scheduled-jobs workflow). E-23's no-show lane now also detects an appointment a person recorded as `no_show`; before, recording the outcome before the first sweep hid it from recovery. Booking confirmations and reminders to the person each need their own M-07 approval: the standing-approval amendment is limited to the website-form auto-reply, and extending it is an owner decision that this change does not assume. |
| 1.13 | 2026-10-17 | The external scheduler is no longer the only way the `/api/cron/*` jobs run. On the website-forms branch (`TESTED`, not deployed), the API runs every scheduled job itself (`backend/scheduler.py`, `backend/tests/test_scheduler.py`): the same function each route runs, on the workflow's cadences, once per window across replicas via a MongoDB lease, recorded in the cron ledger as `origin: in_process` (`receiving_scheduled_traffic` still counts external requests only). Once deployed, what O-03 and O-16 block through the scheduler — C-16, E-01, E-23 and the work-queue worker — no longer depends on them, and the external scheduler (C-25) becomes optional. Sections that state otherwise are not yet reconciled. |
| 1.12 | 2026-10-17 | C-30 moves to `DEPLOYED` (PR #37, `main@9bd9723`, Railway deployment healthy). Added sources #14–#22 to §5 with dispositions and licence obligations, as owner-approved next sources of value: Cal (booking, M-05), Documenso (e-signature), Pipecat (voice agent), Puck (landing pages), Listmonk (campaigns), Umami (analytics), React Email (templates), Papermark (document analytics) and scroll-craft (agent-site design). |
| 1.11 | 2026-10-17 | Added C-30 (website forms and automatic lead handling, `TESTED` on branch). Recorded the owner-directed M-07 amendment: a standing approval may authorise one exact website-form auto-reply template, with every reply still individually approved, consented and checked at the delivery choke point. Recorded that the E-23 public intake door could not accept a lead from a real website (CORS refusal, JSON-only body, unknown fields dropped, no contact or alert, no test) and now runs through C-30's pipeline. |
| 1.10 | 2026-09-28 | Reconciled the capability findings of the merged recovery-engine branch (`docs/ACTIVATION_REPORT.md`) into §4, each checked against the code on `main` before being recorded. Added C-27 (CRM baseline completion), C-28 (scheduled-run ledger and health), C-29 (backend CI gates, `MERGED`) and E-23 (recovery intake and the remaining detector families). M-01 keeps `BLOCKED — OWNER INPUT` but records the deployed Gmail adapter and inbound ingestion; M-08 and M-10 become deployed for their recovery halves; E-01 and E-09 move to `BLOCKED — OWNER INPUT` because every step now exists and only owner grants and the scheduler stand in the way; E-02 detection is deployed while telephony stays blocked. Nothing moves to `LIVE VERIFIED`. |
| 1.9 | 2026-09-28 | Deployed-state reconciliation. `main@c9f5a6e` (the owner's merge of `claude/trusting-brahmagupta-lj26xf`) is deployed on Railway (`1f809799-…`, 2026-09-28T05:25Z), so every capability that was `MERGED` — and E-21/E-22, which PR #28 merged at `730b1b3` — moves to `DEPLOYED` at that commit, except C-23 (CI configuration, stays `MERGED`) and C-25 (cannot run → `BLOCKED — OWNER INPUT`). None moves to `LIVE VERIFIED`. §3.1/§3.2/§3.4 record the new heads, the local gate results that stand in for CI, and the absence of any scheduler traffic. Added O-16: GitHub Actions has assigned no runner to any job since 2026-09-27T22:35Z. The capabilities `docs/ACTIVATION_REPORT.md` records for the merged branch are not yet reconciled row by row. |
| 1.8 | 2026-09-16 | Worked the PR #28 review in full. Nine posted and six suppressed findings were verified against the code and fixed, not deflected. The material ones: `attach()` tenant-checked only the four CRM references, so a plan, approval, conversation or work item belonging to another tenant could be stapled onto a case — all eight attachable references are now checked; `confirm_recovery()` wrote the state and the amount separately, and a failure between them left a case terminal with nothing recorded and no legal transition back — it is one conditional write now; `float()` admitted `nan` and the infinities past the `< 0` check, which would have made every value aggregate non-finite; `source_event_id` was truncated to 200 characters *before* the unique index, so two distinct events sharing a prefix deduplicated into one case; `summary()` summed value across currencies, reporting £40,000 + $40,000 as 80,000; `compose_for_tenant` swept only the work queue, so a case-only source — the missed call this slice exists for — was never planned for in production; and a folded work item kept the case link only in memory. Corrected two overclaims in §3.1 of this document: `ca30587` *has* been deployed to production (2026-09-01, §3.2), and PR #28 is open unmerged work. Backend suite **508 passed, 4 skipped** (475/4 before; +33, no regressions). |
| 1.7 | 2026-09-16 | Added the recovery runner (E-22): the first stage that acts on an approval. Internal steps execute; outbound steps are drafted, given their own approval carrying the exact text, and refused at the provider boundary. Idempotent per case and per step, so a durable-queue redelivery cannot produce a second message. §8 #9 struck through. Backend suite 475 passed, 4 skipped (460 before; +15, no regressions). Still nothing sent: `outbound_sent` is 0 by construction and stated in the runner's own result. |
| 1.6 | 2026-09-16 | Phase 1 of the Revenue Recovery Platform directive. Added the Recovery Case and the normalized recovery-event contract (E-21), removing the architectural requirement that every recovery opportunity originate as an internal CRM record. Existing dormant-deal and missed-follow-up detection is preserved and now also emits cases; the planner gained a boundary that accepts a case with no CRM context. Potential value and confirmed recovered revenue are separate fields with separate provenance, and confirmation requires evidence. Backend suite 460 passed, 4 skipped (baseline 432/4; +28, no regressions). Nothing here executes, sends or attributes — those stages remain as recorded in §8. |
| 1.5 | 2026-09-16 | Reconciliation with the squash-merge of PR #27 into `main@e8d5678`. M-02, M-07, E-10, E-20 and C-26 move from `TESTED` to `MERGED`, and C-24's note about panels "not yet merged" is corrected. §3.1 records the new head and the evidence it was verified against; §3.4 records PR #27 closed and no CRM pull request open; §11 re-orders so that certifying a deployed head is item 1. No capability moves to `DEPLOYED` or `LIVE VERIFIED`: three waves are now merged and none has ever been certified against production (O-15). |
| 1.4 | 2026-09-16 | Omnichannel foundation. Added `backend/conversations.py`: the tenant-scoped `Conversation` thread (participants, channel, status, assignment, the visible agent/human boundary, a per-channel consent record that starts `unknown`, provider-thread deduplication, and an inbound path that reopens a closed thread) and the `CommunicationMessage` model with an explicit state machine that separates a proven provider rejection from an unobserved outcome, so a lost response can never become a duplicate message to a client. Added the provider-agnostic delivery interface — a `ChannelProvider` protocol, a per-channel registry, and one choke point that checks dispatchability, channel authority, consent, a claimed M-07 approval and a registered provider, recording a named refusal for each failure. The application registry is empty, so every outbound attempt refuses today and says why. Added `approval_queue.refresh_blocks` so a prerequisite that has since been resolved stops refusing forever, while remaining unable to revive a rejected, cancelled or lapsed request. Consolidated every approval decision path — the legacy `PATCH /api/approvals/{id}`, the queue decision route and the cancel route — onto one follow-through hook. M-02 and E-10 move to `TESTED`; M-01 and M-03 move to `BLOCKED — OWNER INPUT` because their model is built and only a provider adapter and its authorisation are missing; E-09 stays not started because omnichannel means channels. §8 gains two honest follow-on items (#25 folding the Gmail sync mirror into conversations, #26 the provider adapters). 40 new tests (backend suite 416 passed, 4 skipped). |
| 1.3 | 2026-09-16 | Wave 2 execution pass. Added the approval queue module surface (M-07, `backend/approval_queue.py`) built on C-09's own `approvals` collection rather than beside it: bound actions, single-use consumption, expiry on read as well as by sweep, database-enforced deduplication, requester provenance, risk tiers, optional separation of duties, and a decision history. `POST /api/approvals`, `PATCH /api/approvals/{id}` and MCP level-2 writes were re-pointed at it so one state machine governs every approval, and both decision routes now share one follow-through. Added the recovery strategy composer (E-20, `backend/recovery_strategy.py`): authorised CRM context only, an ordered playbook of named lanes, facts cited to their source record, per-step channel authority derived from the tenant's own integration records, and an approval request per proposal. Added `/api/cron/recovery-strategies` and `/api/cron/approval-expiry` and wired both into the scheduled-jobs workflow. Added the Recovery strategies and Approvals panels to `/operations` and moved the `approvals` module out of `contract_pending`. Restated E-01: steps 1–4 of the north star exist, steps 5–10 do not, so the umbrella capability stays `APPROVED — NOT STARTED`. 71 new tests (backend suite 371 passed, 4 skipped). Reconciled §3 and §4 with the squash-merge of PR #26 into `main@3150530`: the Wave-1 capabilities (E-03, E-04, E-05, E-07, the E-12 pipeline, C-23) move from `TESTED` to `MERGED`, which is still not `DEPLOYED`. |
| 1.2 | 2026-09-15 | Review-remediation pass on PR #26. Fixed concurrency defects in the durable queue (lease ownership on terminal transitions, atomic recovery, in-flight lease renewal, database-enforced deduplication, starvation-free tenant rotation, operator/worker resolve race); made cron deliveries releasable so a crashed job is retried rather than lost, and gave each tick a distinct worker identity; bound security-gate identity and enforcement to the content digest and made a re-scan re-open review; stopped a failed Next Best Action rule from retiring valid recommendations, moved the health rule onto the canonical health snapshot, and made generation upsert atomically; removed an N+1 scan from detection and indexed the lookup it performs. Rewrote the operations smoke to run in disposable tenants with asserted seeds — the previous evidence passed while two seeds were rejected with HTTP 422, so it proved less than claimed. |
| 1.1 | 2026-09-15 | Execution pass. Reduced O-03 from "choose and wire a scheduler" to two repository secrets by adding `.github/workflows/scheduled-jobs.yml`. Recorded verified evidence for `main@3f14347` and the work branch. Moved E-03, E-04, E-05, E-07/NBA-1 and the E-12 pipeline to `TESTED`; added C-23 (CI lint gate). Corrected two further completion claims: CI never ran the documented lint gate, and Next Best Action was previously described as delivered when only a client-side strip existed. Added owner blockers O-14 (scanners unconfigured) and O-15 (production unreachable from the agent environment), and expanded O-03 with the three new cron entry points. |
| 1.0 | 2026-09-15 | Initial canonical replacement. Merged `memory/PRD.md`, `docs/CLIENTVERSE_PRODUCT_COMPLETION_BRIEF.md`, `docs/UX_SYSTEM_IMPROVEMENTS_ASSESSMENT.md`, `docs/REMAINING_WORK.md`, `todo.md`, `AGENTS.md` closeout state, ClickUp `CONTROL — W2`, and Slack canvas `F0BPNUF7VK3` into one governing document. Added the recovered expansion capability register (§4.C), source-repository mapping (§5), the mandatory dual-gate security architecture (§6), unresolved source references (§7), implementation order (§9), dependencies and owner blockers (§10). Corrected six completion claims that evidence does not support (§3.3). |
