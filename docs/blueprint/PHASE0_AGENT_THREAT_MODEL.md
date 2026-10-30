# Phase 0 — Agent and MCP threat model

**Blueprint:** §6 (zero-trust agent architecture) and §9 Phase 0 ("threat model").
**Program record:** [`README.md`](README.md). **Code as of:** `main@ce1affe` plus this branch.

## Rule

The model may request an action. It never grants itself permission. Every agent action passes
a server-side check that a prompt cannot change (blueprint §6).

## How an agent action flows today

```
caller (a person's session) → POST /api/mcp/invoke
  → tool allowlisted in the catalog?            (400 if not)
  → level 3+ refused                            (403)
  → emergency stop active? [gateway]            (423)
  → kill switch on?                             (423)
  → tool in the tenant's allowlist?             (403)
  → external tool: dual security gate approved? (403)
  → required arguments present?                 (422)
  → rate limit per tool per minute              (429)
  → level 1 (read): run with a timeout, record the invocation
  → level 2 (reversible write): store a pending action + raise an approval
        approval bound to tool, pending-action id [+ SHA-256 of the arguments, gateway]
     → a person approves → single-use atomic claim (must match the bound action)
     → re-check emergency stop, kill switch, allowlist at execution [gateway]
     → run, record, undo available
```

`[gateway]` marks the checks added on this branch behind `AGENT_GATEWAY_V2`.

## Threats, controls and gaps

| # | Threat | Control today | Gap | Status |
|---|---|---|---|---|
| T1 | Approved write is swapped for a different one after approval | Single-use claim bound to action type and pending-action id | Arguments were not bound | **Closed on branch:** the approval records the SHA-256 of the arguments, and the claim must match the stored arguments |
| T2 | Approval decided after the kill switch still executes | Kill switch checked at request time only | No check at execution | **Closed on branch:** emergency stop, kill switch and allowlist re-checked at execution |
| T3 | Kill switch leaves queued work and waiting approvals alive | Kill switch refuses new MCP calls | Did not touch queues or approvals | **Closed on branch:** emergency stop cancels agent approvals and pending writes, dead-letters queued work, and stops claims for the tenant. Work a worker already holds is reported as in flight, not killed |
| T4 | Agent acts with a person's full privileges | Roles (admin, member); MCP level limits | No per-agent identity or scoped, short-lived credential | **Open.** Next gateway slice |
| T5 | Prompt injection via email, web pages, documents, tool output | Rules engines (no model) decide recovery actions; outbound needs approval | No content classification; no taint marking on untrusted input | **Open.** Needs design before AI voice or AI email drafting |
| T6 | Cross-tenant access | Every query tenant-scoped; isolation tested every release | — | Controlled (live-verified) |
| T7 | Mass send or runaway agent loop | Per-tool rate limit; approvals; outbound refused unless a channel is authorised | No budgets on tool calls, run time, tokens, money or messages per agent | **Open.** Budgets belong with per-agent identity (T4) |
| T8 | Malicious external tool | Dual security gate refuses unapproved external tools | Scanners not connected (O-13, O-14) | Open (owner) |
| T9 | Tampered or missing audit | Domain events and invocation records in MongoDB | Records are mutable by anyone with database access; no export | **Open.** Signed or append-only evidence export (Agent Command Center) |
| T10 | Emergency stop misused to block a tenant | Admin-only routes; each stop and release is an audited event with the actor and reason | — | Controlled on branch |
| T11 | Irreversible external actions (sent email) | Outbound needs approval and an authorised channel | Undo exists only for internal writes | Accepted: sends cannot be undone. Dry run before send is a Phase 1 item |

## What the first gateway slice does (branch only, flag off)

- `backend/agent_gateway.py`, wired into `backend/server.py` (MCP invoke and approval
  follow-through) and `backend/work_queue.py` (claims skip a stopped tenant).
- New admin routes, answering 404 while the flag is off:
  - `POST /api/agents/emergency-stop` `{"reason": "..."}` → receipt (approvals cancelled,
    pending writes cancelled, work items stopped, work items in flight)
  - `GET /api/agents/emergency-stop` → whether a stop is active
  - `POST /api/agents/emergency-stop/release` → ends the stop; the kill switch stays on, so
    turning agents back on is a second, deliberate step
- With the flag on, an approval raised **before** the flag was turned on carries no argument
  digest and is refused (409). Re-request those actions after turning the flag on.
- Tests: `backend/tests/test_agent_gateway.py` (8 tests: flag off changes nothing, argument
  swap refused, unchanged arguments execute, kill switch re-checked, stop and release, one
  tenant's stop leaves another alone, admin only).

## Red-team list before any release with the flag on (blueprint §6)

1. Swap arguments between request and approval (covered by a test).
2. Approve while the kill switch is on (covered by a test).
3. Race: emergency stop during an approval decision; during a worker claim.
4. Prompt injection through an inbound email that reaches a recovery draft.
5. Cross-tenant: stop tenant A, act as tenant B (covered by a test).
6. Mass send: an approved strategy with many recipients (needs T7 budgets first).
