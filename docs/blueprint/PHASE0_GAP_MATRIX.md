# Phase 0 — Capability inventory and competitive gap matrix

**Blueprint:** *ClientVerse Competitive CRM & AI Security Blueprint* (owner, 28 October 2026),
§2, §3, §4 and §10. **Program record:** [`README.md`](README.md).
**Inventory as of:** `main@ce1affe` (2026-10-28), read from the source and the governing
document's capability register (§4). Production evidence: *Production acceptance* run
`40776931126` at `735d168` (API 40/40, browser 76/76). `ce1affe` adds documentation only.

## How to read this

**Status** uses the blueprint's six words (§10):

| Status | Meaning here |
|---|---|
| **Live-verified** | Exercised in production by an automated acceptance run |
| **Implemented** | Code merged and deployed, tests pass, not exercised in production by a check |
| **Configured** | Built, and needs an owner credential or switch before it does anything |
| **Partial** | Some of the capability exists; the gap is named |
| **Placeholder** | A screen or record exists with no working capability behind it |
| **Missing** | Nothing in the code |

**Impact, effort, risk and differentiation** are engineering estimates (High / Medium / Low),
not measured figures. Competitor capabilities come from the blueprint's own table and are
**not re-verified against current vendor documentation**; check them before relying on them.

## 1. Inventory of what ClientVerse has today

| Area | Capability | Status | Evidence |
|---|---|---|---|
| Core CRM | Contacts, companies, deals, pipelines, tasks, notes, search, filters | Live-verified (lead journey) / Implemented (rest) | C-03, C-04, C-27; acceptance checks 06–40 |
| Core CRM | Custom fields, saved views, lifecycle | Implemented | C-33 |
| Core CRM | CSV import and export | Implemented | C-39 (PR #51) |
| Core CRM | Client 360 workspaces, client health score (rule-based, explained) | Implemented | C-05; `server.py` health score |
| Lead capture | Website forms, embeds, server intake, duplicates, budget mapping | Live-verified | C-30; acceptance checks 08–30 |
| Booking | Booking pages, public booking, reminders | Implemented | M-05; no production booking made yet |
| Automation | Trigger → conditions → steps automations (form list, not a visual canvas) | Implemented | C-35 |
| Automation | Durable work queue, in-process scheduler, cron ledger | Implemented | E-05, C-31, C-28 |
| Agency | Client accounts under an agency (sub-accounts), switch into a client account | Implemented | C-38 |
| Agency | Snapshots (save and share a setup), industry templates | Implemented | C-37, C-36 |
| Agency | White-label branding | Missing | No branding fields or theming per tenant |
| Agency | Plans and billing per client account | Missing | Stripe lifecycle exists (C-18) but no plans or rebilling |
| Communications | Unified inbox (conversation model, assignment, handoff, consent record) | Partial | M-02 implemented; only email can carry traffic |
| Communications | Email out (Gmail) | Configured | M-01; Google connected 2026-10-19; sending switch off, never certified live |
| Communications | Email in (reply capture) | Implemented | Inbound sweep reads the inbox (2026-10-19 log); never certified end to end |
| Communications | SMS | Missing | M-03: no provider; owner decision O-06 |
| Communications | Calling, call tracking | Missing | M-04; only a call-log intake API (E-02) |
| Communications | AI voice agents | Missing | E-08 |
| Marketing | Funnels and landing-page builder | Missing | `puckeditor/puck` on WATCH (governing doc §5 #17) |
| Marketing | Campaigns and nurture sequences | Missing | |
| Marketing | Attribution | Partial | Lead source attribution (C-30) and recovery attribution (M-08); no campaign analytics |
| Payments | Stripe payment intents, signed webhooks | Configured | C-18; no owner key |
| AI | AI text generation | Configured | C-19; needs `EMERGENT_LLM_KEY` |
| AI | Next Best Action, recovery strategy, Second Chance detectors | Implemented | E-07, E-20, E-03, E-23 (rules, no model) |
| AI governance | MCP tool catalog with levels, allowlist, rate limits, audit, undo | Implemented | C-11 |
| AI governance | Approvals bound to an action, expiring, single-use | Implemented | M-07 |
| AI governance | Approval bound to exact arguments; execution-time re-check; emergency stop | Implemented on branch, flag off | `backend/agent_gateway.py`, `AGENT_GATEWAY_V2` |
| AI governance | Per-agent identities and scoped short-lived credentials | Missing | Agents act through a person's session |
| AI governance | External tool security gate (dual scanners) | Configured | E-12; scanners not connected (O-13, O-14) |
| AI governance | Agent Command Center (inventory, modes, costs) | Missing | Blueprint §7 |
| Reporting | Recovery proof, dashboard, today plan | Implemented | M-10, C-34 |
| Reporting | Lead or deal scoring, forecasting | Missing | M-08 forecast and M-11 not started |
| Enterprise | Roles (admin, member), team invitations, audit trail | Implemented | C-13, C-14 |
| Enterprise | Custom objects, fine-grained permissions, public developer API | Missing | |
| Operations | Tenant isolation tested on every release | Live-verified | C-02; acceptance check 32 |
| Operations | Backup restore drill (mongodump → drop → restore → verify) | Live-verified on CI | *Backup and restore drill* workflow; Atlas's own backups unverified |
| Operations | Staging environment | Missing | One production environment only |
| Operations | Rollback | Partial | Railway can redeploy an earlier deployment; no documented, tested rollback drill |

## 2. Gap matrix against the benchmarks

| Gap | GHL | Votel | HubSpot | Salesforce | Revenue impact | Effort | Security risk | Differentiation | Blueprint priority |
|---|---|---|---|---|---|---|---|---|---|
| Staging environment | — | — | — | — | Low (enables everything) | Low | Lowers risk | — | P0 |
| Agent gateway: per-agent identity, scoped credentials, policy engine | — | Partial | — | — | Medium | Medium | **Lowers** a High risk | **High** | P0 |
| Two-way SMS with consent and opt-out | Has | Has | Has | Has | **High** | Medium (+ carrier registration lead time) | High (consent law) | Low | P0 |
| Calling and call tracking | Has | Has | Has | Has | High | Medium | High | Low | P0 |
| Email certified live (send, reply, failure recovery) | Has | Has | Has | Has | High | Low | Medium | Low | P0 |
| Unified timeline across channels | Has | Has | Has | Has | Medium | Low (model exists) | Low | Low | P0 |
| Visual workflow editor | Has | Has | Has | Has | High | Medium | Medium | Medium | P1 |
| White-label and agency plans with rebilling | Has | Has | — | — | **High** for agency SaaS | Medium | Medium (billing) | Low | P1 |
| Funnels and landing-page builder | Has | — | Has | — | High | High | Medium (public pages) | Low | P1 |
| Campaigns and nurture | Has | Has | Has | Has | Medium | Medium | High (consent) | Low | P1 |
| AI voice agent with human oversight | Partial | Has | — | — | High | High | High | **High** with governance | P1 |
| Agent Command Center | — | Partial | — | — | Medium | Medium | Lowers risk | **High** | P1 (blueprint §7) |
| Explainable lead and deal scoring | Partial | — | Has | Has | Medium | Medium | Low | Medium | P2 |
| Forecasting | — | — | Has | Has | Medium | Medium | Low | Low | P2 |
| Custom objects, fine-grained permissions, developer API | — | — | Has | Has | Medium | High | Medium | Low | P2 |

"Has" and "Partial" repeat the blueprint's benchmark table; they are not verified here.

## 3. What Phase 0 changes in the plan

1. **Several P0 items are already done or partly done** (restore drill, tenant isolation,
   approvals, audit trail). Phase 0 narrows the P0 list to staging, the remaining agent
   gateway work, and communications.
2. **The quickest security win is the agent gateway**, because the approval and MCP code
   exists. Its first slice is on the branch (see the threat model).
3. **SMS and calling carry the longest outside lead time** (provider choice, US carrier
   registration, consent policy O-06). Start the owner decisions now, even though the code
   comes in Phase 1.
4. **Staging needs an owner action** on Railway (a second environment and its own
   database). Engineering cannot create it from an agent session.
