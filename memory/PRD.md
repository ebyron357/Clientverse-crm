# ClientVerse.io — Product Requirements & Architecture

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

## Backlog (prioritized)
- P0: Wire live MCP server (Level 1 read tools) + real webhook delivery with signing/retry/DLQ.
- P0: Streaming AI responses + cost/token telemetry per run.
- P1: Real integration OAuth connect flow (Gmail/Calendar/Stripe adapters).
- P1: Role/permission enforcement beyond admin (member role, field-level access).
- P1: Opportunity/company edit + delete; commitment due-date automation → commitment.at_risk.
- P2: Split server.py into routers; add DB indexes (tenant_id, timestamp); public API + OpenAPI/sandbox.
- P2: Plugin manifest install flow; kill switches; approval preauthorization for Level 3 tools.

## Next Tasks
See backlog P0 items first (live MCP read tools, webhook delivery).
