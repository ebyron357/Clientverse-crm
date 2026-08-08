# ClientVerse.io — Product Requirements & Architecture

## Implemented (2026-06 — this phase) — Role & Permission Enforcement — status AVAILABLE
- Multi-tenant team membership (`memberships`): user/tenant/role/status/invited_by/invited_at/accepted_at/disabled_at. `get_current_user` → `resolve_membership` resolves effective role and blocks disabled members (403); legacy users self-heal.
- Invitations (`invitations`): admin invite-by-email, secure single-use token (only SHA-256 hash stored), 7-day TTL, statuses pending/accepted/expired/revoked, duplicate-active + already-member rejection, resend/revoke, accept attaches authed user to tenant. Endpoints under `/api/team/*` incl. public `lookup`.
- Centralized authz: `require_role()` / `require_permission()` + `ROLE_PERMISSIONS`. Admin-gated (403 for members): MCP approvals, kill switch, undo, undo-window, webhook secret reveal (`GET /api/webhooks/{id}/secret`) + rotation + create/patch, team management. Webhook list no longer leaks secrets.
- Security: tenant isolation (cross-tenant ops → 404), token hashing/expiry/single-use, last-admin safety (cannot demote/disable final active admin). Audit: authz.denied, team.invitation_* , team.role_changed, team.member_disabled/enabled.
- Frontend: `/team` admin console (members table + role/status controls, invitations, invite dialog with copyable single-use link), `/invite?token=` accept page (loading/pending/expired/revoked/accepted/wrong-account/success states), admin-only nav + role badge, member-gated webhook/approval controls, login `?redirect=` for invite return.
- Seeded demo member: demo.member@clientverse.io / Member2026! (member) in ClientVerse HQ.
- Tests: `backend/tests/test_role_permissions.py` 13/13 pass; full backend suite 66 passed / 2 skipped; frontend flows 11/11 pass (iteration_9 + iteration_10 retest); production build succeeds.

## Implemented (2026-06 — this phase) — Commitment SLA Risk Automation — status AVAILABLE
- Commitments carry an optional `due_date`; `PATCH /api/commitments/{id}` now accepts `status` and/or `due_date` (CommitmentPatch).
- `evaluate_commitment_risk()` sweep: open commitments due within 48h → `at_risk` (commitment.at_risk); overdue open/at_risk → `breached` (commitment.breached). Emits domain events → Audit + Webhooks + health recompute (commitment.breached added to HEALTH_AFFECTING).
- `POST /api/commitments/evaluate-risk` (tenant-scoped, on-demand) + `POST /api/cron/commitment-risk` (Bearer `WEBHOOK_CRON_SECRET`, idempotent on X-Webhook-Id, acks 2xx, backgrounds all-tenant sweep).
- `.emergent/crons.yml` → `commitment-sla` cron every 15 min. `WEBHOOK_CRON_SECRET` added to backend/.env.
- Frontend WorkspaceDetail: due-date countdown + status badges on the ledger, "Run SLA check" button, and a New Commitment dialog (title/owner/due date).
- Tests: `backend/tests/test_commitment_sla.py` (4 pass) + full existing suite (50 passed / 1 skipped) + production build succeeds. Verified via curl + screenshots.
- Recovery note: a server.py tail-corruption (duplicated ending block) reoccurred from a parallel search_replace batch touching the file end; truncated the duplicate, re-applied the CommitmentPatch/sweep block as an isolated edit, AST-verified single defs.

## Original Problem Statement
Build ClientVerse.io — an AI-native Client Operations Platform (not a generic CRM) managing the full client lifecycle: WIN → ONBOARD → SERVE → RETAIN → EXPAND. Integration-first, evidence-driven, governed automation, MCP/plugin interoperability, capability governance.

## Stack / Architecture (as built)
- Modular monolith: FastAPI (`/app/backend/server.py`) + MongoDB + React (`/app/frontend/src`).
- Multi-tenant: every record tenant-scoped via `tenant_id`; server-side auth on all routes (`get_current_user`).
- Auth: JWT email/password (httpOnly cookie `access_token`, Bearer fallback) AND Emergent Google OAuth (`/api/auth/google/session`).
- Normalized domain events written on every significant state change (`domain_events` collection) → Audit feed.
- Evidence-backed AI via emergentintegrations (Claude claude-sonnet-4-6, EMERGENT_LLM_KEY).

## User Personas
- Agency/services operator (admin): manages pipeline, workspaces, delivery, client health.
- Delivery team member: tasks, deliverables, requests.
- Ops/governance owner: approvals, registries, audit.

## Core Requirements (static)
Lifecycle CRM + Client Workspaces + Commitment Ledger + Deliverables/Requests/Approvals + Explainable Health + Evidence-backed AI + Governed registries (Integrations/MCP/Plugins/Webhooks) + Audit event feed.

## Implemented (2026-08-05) — status AVAILABLE
- Auth (JWT + Google), multi-tenant isolation (verified by tests).
- Command Center dashboard: KPIs, pipeline funnel chart, client health portfolio.
- Pipeline (Kanban stages); closed_won auto-creates a client workspace + onboarding events.
- Directory: Companies + Contacts (influence/sentiment).
- Client Workspaces + WorkspaceDetail: Commitment Ledger, Tasks, Deliverables, Client Requests, Approvals.
- Explainable Client Health (deterministic scoring with contributing factors, fact-typed).
- Evidence-backed AI panel: health summary + draft message, with source records, confidence, model/prompt/policy versions, run id; agent.run_started/completed/failed events.
- Registries (Integrations/MCP Servers/Plugins/Webhooks) with capability status badges — status ALPHA/PLANNED/BETA/AVAILABLE (registry data-backed; live external execution NOT wired).
- Automation & Audit domain-event feed.
- Tests: 15/15 backend + 10/10 E2E flows pass (iteration_1).

## Implemented (2026-08-05) — Slice 6: Undo Window Config, Goal Sparklines, Webhook Pattern Preview — status AVAILABLE
- Undo Window Config: per-workspace undo grace period (undo_window_minutes) set by admins via PATCH /api/workspaces/{id}/undo-window (clamped 1..1440); mcp_undo enforces the per-workspace window (fallback 60). UI control in WorkspaceDetail header (admin-only).
- Goal Trend Sparklines: outcome_snapshots recorded on outcome create/update; /api/dashboard goal_rollup goals include trend[]; Command Center rollup renders an inline recharts sparkline per goal.
- Webhook Pattern Preview: POST /api/webhooks/match-preview scans the last 100 tenant events and returns matched counts by type; the New Endpoint dialog shows a live "N of M match" preview. Wildcard patterns supported via event_matches (exact, trailing ".*", "*").
- Recovery: fixed TWO recurring server.py file-tail corruptions (duplicated include_router/CORS blocks) introduced during edits; backend confirmed clean (single defs, AST OK, HTTP 200).
- Tests: iteration_7 — 50/50 backend pass (1 skipped by design) + sparkline fix verified, no bugs.

## Capability: Server Modularization — status PLANNED (deferred)
- server.py is ~1328 lines. A full split (auth/mcp/webhooks/outcomes/approvals/dashboard modules + shared core) is planned but intentionally DEFERRED this session: two tail-corruptions already occurred from large in-place edits, and a full refactor carries high regression risk with no user-visible change. Per platform governance ("do not sacrifice platform integrity for fast completion"), it will be done as a dedicated, test-gated refactor. Not represented as implemented.

## Implemented (2026-08-05) — Slice 5: Rollup, Undo Window, Webhook Patterns — status AVAILABLE
- Outcome Targets Rollup: /api/dashboard returns goal_rollup (total/on-track/at-risk/avg + per-workspace goal progress); Command Center shows a "Client Goal Progress" card with progress bars.
- Undo Window + Reason: POST /api/mcp/invocations/{id}/undo now requires a non-empty reason (422 otherwise), enforces a 60-min window via executed_at, stays admin-only, and records the reason on the mcp.tool_undone event. Undo prompts for a reason in both MCP Console and Audit trail.
- Webhook Event Filters: dispatch supports wildcard subscriptions via event_matches() — exact, trailing ".*" prefix (e.g. commitment.*), and "*". Create dialog offers pattern chips.
- Recovery: fixed a backend file-tail corruption (duplicated block → IndentationError) that had taken the server down; single clean definitions confirmed.
- Tests: iteration_5 — 43 backend tests pass + full frontend E2E + regression breadth, no bugs (test_iteration5.py added).

## Implemented (2026-08-05) — Slice 4: Undo, Webhook Signature Docs, Outcome Targets — status AVAILABLE
- Undo Actions: admin-only POST /api/mcp/invocations/{id}/undo reverses a successful Level-2 MCP write (deletes the created task/note), marks it undone, emits mcp.tool_undone. Undo buttons on MCP Console history rows and on the Audit trail (executed-write events).
- Webhook Signature Docs: per-endpoint "Verify" dialog exposes the HMAC signing secret + a copyable Node.js verification snippet and lists the signature headers.
- Outcome Targets: outcomes carry target_value/current_value/unit; progress bars on the Outcome Graph; add via shadcn Dialog; inline current-value updates via PATCH /api/outcomes/{id}.
- Tests: iteration_4 — 21/21 backend + all frontend flows pass (new /app/backend/tests/test_iteration4.py).

## Implemented (2026-08-05) — Slice 3: Write governance, Webhooks, Outcome Graph — status AVAILABLE
- MCP Level 2 reversible write tools (create_task, add_note) gated behind approval: invoke returns pending_approval, creates an mcp_write approval; approving in the workspace executes the tool (execute_pending_mcp) and flips the invocation to success. Rejecting cancels.
- Live Webhooks: HMAC-SHA256 signed delivery, auto-dispatch on every domain event to subscribed endpoints, up to 3 retry attempts with backoff, dead-letter (DLQ) on final failure, delivery log with attempt history, manual replay, enable/disable toggle, secret rotation, test-event, built-in sink. Endpoints /api/webhooks*, /api/webhook-deliveries*. UI: WebhookManager in Registries → Webhooks tab.
- Client Outcome Graph: per-workspace goals (outcomes) linking to commitments and health, plus health-over-time snapshots (record_health_snapshot on outcome-affecting events). Endpoints POST /api/outcomes, GET /api/workspaces/{id}/outcome-graph. UI: OutcomeGraph component in WorkspaceDetail → Outcome Graph tab.
- Tests: iteration_3 — 100% backend + frontend, no regressions.

## Implemented (2026-08-05) — Slice 2: Governed MCP Server — status AVAILABLE
- Live MCP server exposing 5 Level-1 read tools (search_contacts, get_client_health, list_open_commitments, get_pipeline_summary, list_tasks) through a policy wrapper.
- Governance enforced server-side: tenant scope, tool allowlist, kill switch (admin-only, 423), Level>1 denied, required-arg validation (422), per-tool rate limit (429), timeout (504), idempotency key replay, execution history (mcp_tool_invocations), correlation IDs.
- Domain events: mcp.tool_invoked / mcp.tool_failed → Audit feed.
- MCP Console UI (/mcp): tool catalog with level/scope/timeout/rate badges, invoke panel (workspace-aware args), kill switch, execution history with retry.
- Endpoints: GET /api/mcp/tools, GET /api/mcp/server, PATCH /api/mcp/server/kill, POST /api/mcp/invoke, GET /api/mcp/invocations.
- Tests: E2E frontend + backend pass (iteration_2), no regressions.

## Backlog (prioritized)
- P0: Governed MCP server Level 1 read tools — DONE (see below). Next: Level 2 reversible writes with approval gating.
- P0: Real webhook delivery with signing/retry/DLQ + delivery history.
- P0: Streaming AI responses + cost/token telemetry per run.
- P1: Real integration OAuth connect flow (Gmail/Calendar/Stripe adapters).
- P1: Role/permission enforcement beyond admin (member role, field-level access).
- P1: Opportunity/company edit + delete; commitment due-date automation → commitment.at_risk.
- P2: Split server.py into routers; add DB indexes (tenant_id, timestamp); public API + OpenAPI/sandbox.
- P2: Plugin manifest install flow; kill switches; approval preauthorization for Level 3 tools.

## Next Tasks
See backlog P0 items first (live MCP read tools, webhook delivery).
