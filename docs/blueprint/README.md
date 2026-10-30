# ClientVerse blueprint program

**Directive (owner, 2026-10-30):** follow the *ClientVerse Competitive CRM & AI Security
Blueprint* (owner document, 28 October 2026), and build it on a separate branch so the
running system is not affected.

This folder is the blueprint's working record in the repository. The canonical governing
document (`docs/CLIENTVERSE_CRM_CANONICAL_GOVERNING_DOCUMENT.md`) registers it in §0.6
and keeps authority over everything else.

## The blueprint in one paragraph

Upgrade the existing ClientVerse CRM; do not rebuild or replace it. Compete with
GoHighLevel for agency SaaS, learn from Salesforce and HubSpot, benchmark Votel AI, and
differentiate through tightly governed AI agents. Close purchase-blocking gaps first
(two-way SMS and email, calling, booking, billing, unified inbox, workflows, funnels).
Every agent action passes a deterministic server-side gateway; the model never grants
itself permission. Open-source projects are components, services or references, never
replacement engines. Work proceeds in gated phases 0–5.

## How the branch keeps production safe

- **Railway deploys only `main`.** Work happens on the program branch and reaches
  production only when the owner approves a merge (blueprint §10).
- **Every new capability ships behind a feature flag that is off by default**, so even a
  merge changes nothing until the flag is turned on, first in staging.
- **Vercel builds a preview of every branch.** That preview's screens call the production
  API, and its sign-in fails across origins. Do not test this branch through a Vercel
  preview link (owner action O-18 removes the Vercel project).

## Phases, gates and status

| Phase | Work | Gate (blueprint §9) | Status |
|---|---|---|---|
| 0 Safety + audit | Code and test review; feature inventory; staging; restore drill; threat model | No production change before approval | **In progress.** Inventory and gap matrix done ([PHASE0_GAP_MATRIX.md](PHASE0_GAP_MATRIX.md)); threat model done ([PHASE0_AGENT_THREAT_MODEL.md](PHASE0_AGENT_THREAT_MODEL.md)); restore drill already live (monthly workflow). **Staging needs the owner** (below) |
| P0 Agent security gateway | Scoped identities, policy checks, approval binding, revocation | Approval, tenant isolation, red-team and kill-switch tests | **First slice built, flag off** (`AGENT_GATEWAY_V2`): approval bound to exact arguments, execution-time re-check, emergency stop with receipt. Next: per-agent identities and budgets |
| 1 Commercial basics | Certify email, calendar, Stripe; add SMS and calling; unified timeline | Consent, retries, end-to-end integration tests | Not started. Needs owner decisions O-06 (telephony and consent), SMS provider, Stripe key |
| 2 GHL parity | Visual workflow editor, funnels, campaigns, snapshots, agency billing | Parity demos and regression suite | Not started. Snapshots and sub-accounts already exist |
| 3 Governed AI | Voice agents, customer memory, AI actions through the gateway | Approval, isolation, red-team, kill-switch tests | Not started |
| 4 Intelligence | Explainable scoring, forecasting, attribution | Quality, privacy, bias evaluations | Not started |
| 5 Enterprise | Extensibility, audit, observability, resilience, marketplace | Load and security acceptance | Not started |

## Feature flags

| Flag | Default | What it turns on | Where to turn it on first |
|---|---|---|---|
| `AGENT_GATEWAY_V2` | off | Argument-bound approvals, execution-time re-check, `/api/agents/emergency-stop` | Staging |

## Owner decisions this program needs

1. **Staging on Railway.** Create a second environment (for example `staging`) in project
   `welcoming-vibrancy`, with its own MongoDB database (never the production one), its own
   `JWT_SECRET`, `INTEGRATION_ENC_KEY` and `ADMIN_PASSWORD`, deploying this branch. No
   Google, Gmail or Stripe production credentials in staging.
2. **SMS and calling provider** and the consent and recording policy (O-06). US business
   texting also needs carrier registration, which can take weeks, so it should start
   before Phase 1 code.
3. **When to merge** each slice into `main`. A merge with its flag off changes nothing;
   turning a flag on in production is a separate decision.

## Engineering rules for this program (blueprint §10)

For every feature: inspect current code → measure the gap → choose extend, embed,
integrate or reference → check licence and security → build behind a flag → test →
stage → review → deploy with rollback. Classify every capability as live-verified,
implemented, configured, partial, placeholder or missing. Explicit owner approval before
migrations, production changes, merging to `main` or any external messaging.

Open-source projects in blueprint §5 join the governing document's source register (§5)
with a disposition before any use. Licences are checked one by one; AGPL and GPL code is
never copied into ClientVerse. The blueprint's §8 (closed-source research with REA) applies
only to software the owner is authorised to study, and its legal conditions are part of
the blueprint.
