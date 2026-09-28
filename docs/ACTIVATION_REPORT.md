# ClientVerse Activation Report

**Date:** 2026-09-21
**Branch:** `claude/trusting-brahmagupta-lj26xf` (7 commits, 58 files, +9,144 / −201)
**Companion document:** [`docs/OWNER_HANDOFF.md`](OWNER_HANDOFF.md)

Every status below is stated against the definition the work was commissioned under:

> IMPLEMENTED → TESTED → DEPLOYED → CONFIGURED → AUTHENTICATED → EXTERNALLY REACHABLE
> → EXERCISED IN PRODUCTION → RESULT VERIFIED → OPERATOR HANDOFF DOCUMENTED

**Nothing in this report is marked LIVE VERIFIED.** Everything here stops at TESTED,
for one reason stated once and not repeated in every row: this session's network policy
refused every connection to the production host with an HTTP 403 at the CONNECT stage.
Production could not be reached, so production could not be exercised. That is recorded
in §"Outstanding Defects" with its evidence, and §8 of the handoff is the script for
the owner to complete the remaining stages.

---

## Release

| | |
|---|---|
| Environment | Railway `production` |
| Production URL | `https://clientverse-crm-production-production.up.railway.app` |
| Deployed git SHA | `730b1b3b30e5b8f9d88bffc0dc3161c1a8046296` (`main`) |
| Railway deployment ID | `4b5f7f84-fcca-43ed-8777-415082747e6e` |
| Deployment timestamp | 2026-09-16T23:33:41Z, status SUCCESS |
| Healthcheck | `/api/health`, matches the service's configured path (verified against the Railway service config) |
| **This branch's SHA** | `cc511539ba1eab68a7a388fc6a8f2ca8d816108a` — **not deployed** |
| Live verification | **NOT POSSIBLE FROM THIS SESSION** — egress policy denial, see Outstanding Defects #1 |

---

## Administrator Access

| | |
|---|---|
| Tenant | The tenant seeded from `ADMIN_EMAIL` at first boot |
| Admin email | The value of the `ADMIN_EMAIL` Railway variable (not reproduced here) |
| Role | `admin` |
| Login tested | PASS locally against this exact code; **NOT VERIFIED** in production |
| Logout tested | PASS locally; **NOT VERIFIED** in production |
| Session revocation tested | PASS locally — a token replayed after logout returns 401 (`test_session_revocation.py`, smoke step 49); **NOT VERIFIED** in production |
| Password handoff method | Railway service variable `ADMIN_PASSWORD`, read from and rotated in the Railway dashboard. `seed()` re-syncs the hash on every boot, so setting a new value and letting the redeploy finish is the rotation. No password appears in this repository or in any document |

---

## CRM Baseline

Marked against behaviour exercised by test and by the 82-assertion release smoke,
**not** against route existence.

| Capability | Status | What was found and done |
|---|---|---|
| Authentication | PASS | Register, login, logout, session persistence, real server-side revocation, bcrypt hashing, login lockout, admin/member enforcement. All pre-existing and all now covered by the release gate |
| Team invitation | PASS | Invite, accept, resend, revoke, lookup, status. Resending now proves it **mints a new token and invalidates the old**, which was untested |
| Contacts | PASS | **Was PARTIAL.** Create and list existed; open, edit, archive, restore, timeline, owner, phone and title did not. All added |
| Companies | PASS | **Was PARTIAL.** Same gap. Detail view now carries related contacts, deals, workspaces and commercial context with open pipeline and closed-won reported separately |
| Deals | PASS | **Was PARTIAL.** Value, owner, close date and contact links were effectively write-once; only stage could change. Full edit, detail, archive and per-deal `stage_history` added |
| Pipelines | PASS | **Was NOT IMPLEMENTED** as a configurable capability — stages were a module constant. Now tenant-configurable, defaulting to the shipped stages. A stage still holding deals cannot be removed; a pipeline with no closed-won stage is refused |
| Tasks | PASS | **Was PARTIAL.** Tasks existed only inside a delivery workspace. Now attach to any CRM record, list with filters, surface overdue and upcoming, record completion time, and notify the assignee |
| Activity / timeline | PASS | **Notes, calls, meetings and logged emails were NOT IMPLEMENTED.** Added as first-class activity with a merged per-record timeline. Logging an email records that a person sent one and sends nothing |
| Search | PASS | **Was NOT IMPLEMENTED.** Global search across contacts, companies, deals and tasks, restricted to explicitly searchable fields |
| Filtering | PASS | **Was NOT IMPLEMENTED** beyond `contacts?company_id=`. Owner, stage, status, company, due-date and free-text filters with sorting on an allow-list |
| Notifications | PASS | Pre-existing; assignment notifications added, since a task assigned with nobody told is not an assignment |
| Settings | PASS | Pre-existing account, provider, tenant and preference configuration |
| Import | PASS | **Was NOT IMPLEMENTED.** CSV import for contacts, companies and deals. Reports bad rows rather than dropping them; refuses an unknown column; refuses a cross-tenant reference |
| Export | PASS | **Was NOT IMPLEMENTED.** CSV export for contacts, companies, deals and tasks |
| Cross-tenant isolation | PASS | Another tenant's record answers 404, never 403. Asserted for read, edit, archive, timeline, search, export and association on every new surface |
| Audit trail | PASS | `domain_events` for organisation-wide activity and per-record `history` for state transitions, kept distinct as the project requires. Every new mutation writes both |

---

## Recovery Engine

| Capability | Status | Note |
|---|---|---|
| Detector scheduler | PARTIAL | Code complete and CI-verified. **Has never run in production**, because the two GitHub secrets are unset — see Outstanding Defects #2 |
| Dormant-deal detection | PASS (tested) | Pre-existing, unchanged |
| Missed-follow-up detection | PASS (tested) | Pre-existing, unchanged |
| Remaining detectors | PASS (tested) | All eight declared families implemented: missed calls, web enquiries, unanswered quotes, unanswered estimates, no-response, cancellations, no-shows, external CRM events. 40 tests, half of which assert the lanes do **not** fire on ordinary business |
| Recovery case creation | PASS (tested) | Every new lane opens a case through the existing normalized contract, deduplicated on (source, record) |
| Strategy composition | PASS (tested) | Pre-existing. Verified it already sweeps unplanned cases, so the new sources enter the same pipeline rather than a parallel one |
| Approval queue | PASS (tested) | Pre-existing. Strengthened: an approval now binds a fingerprint of the exact approved text |
| Recovery runner | PASS (tested) | Pre-existing. **Its cron endpoint was never scheduled** — found by the new configuration validator and fixed |
| Durable work queue | PASS (tested) | Pre-existing |
| Approval expiry | PASS (tested) | Pre-existing; scheduled, but the schedule has never reached production |
| Cron execution | **BLOCKED** | Owner action: set the two repository secrets |

---

## Communications

| Capability | Status | Note |
|---|---|---|
| Gmail connected | NOT VERIFIED | Requires reaching production |
| Outbound provider | PASS (tested) | `GmailChannelProvider` implements `ChannelProvider`. **Was NOT IMPLEMENTED** — this was the gap that made every send refuse |
| Outbound send | PARTIAL | Code complete, 33 tests. Cannot send until the owner grants `gmail.send` (a new scope; an existing connection is read-only and is refused rather than attempted) |
| Consent enforcement | PASS (tested) | Unchanged and re-verified through the real adapter: consent withdrawn between approval and dispatch stops the send |
| Approval binding | PASS (tested) | **Strengthened.** The approval records a SHA-256 of the body it was raised for and the choke point re-checks it before consuming the approval, so a body rewritten after a human read it cannot ride that decision |
| Duplicate-send protection | PASS (tested) | Gmail has no idempotency key, so the adapter mints one: a deterministic RFC 2822 Message-ID per dispatch, checked against Gmail before sending. An inconclusive check stops the dispatch rather than falling through into a send |
| Inbound replies | PASS (tested) | **Was NOT IMPLEMENTED.** Poll-driven ingestion, matched strongest-evidence-first, idempotent on the provider's message id |
| Conversation matching | PASS (tested) | Provider thread → reply header naming a message we sent → sender against a single open conversation. Anything ambiguous is parked for a human, never guessed |
| Delivery / bounce status | PASS (tested) | Bounces classified before replies and applied as delivery evidence. A bounce is never recorded as engagement |

---

## Attribution

| Capability | Status | Note |
|---|---|---|
| Attribution ledger merged | **N/A — the premise was wrong** | The specification said it was built, tested and unmerged. There is no such branch on the remote and no attribution code in the repository. Reported as a discrepancy and built from scratch |
| Outcome recording | PASS (tested) | Invoice paid, deal won, operator confirmation. Amounts read from the record, not the request |
| Attribution evidence | PASS (tested) | Named basis plus the message and reply ids it rests on. **No confidence score is produced**, because there is no honest way to compute one |
| Recovered revenue calculation | PASS (tested) | Only a message a provider accepted counts as contact. Draft, approved, blocked, failed and `outcome_unknown` support nothing. No contact means no claim, recorded as unattributed with the reason |
| Adversarial attribution test | PASS | 31 tests attempt to make the ledger claim unearned credit: supply the basis, smuggle it through a free-text note, inflate the amount, claim an unpaid invoice, claim an open deal, claim another tenant's invoice, use another tenant's sent message as evidence, book the same outcome twice. All refused |

---

## Proof / Reporting

| Capability | Status | Note |
|---|---|---|
| Case-level proof | PASS (tested) | Detection and its reason, source record, strategy, approvals, drafted vs actually sent, replies, meetings, outcome, attribution basis and evidence, owner, timestamps |
| Portfolio reporting | PASS (tested) | Cases detected / worked / awaiting approval, messages drafted vs sent vs unknown, replies, attributed and unattributed revenue, time to recovery |
| Potential vs confirmed separation | PASS (tested) | Three separate named figures. There is **no combined total anywhere**, asserted by test and by the release gate |
| Evidence drill-down | PASS | `/proof` page, verified by driving the built SPA in Chromium. `GET /api/proof/traceability` ships the query behind every figure |

---

## Production Certification

| Check | Result |
|---|---|
| Git SHA parity | **NOT VERIFIED** — `/api/health` unreachable. Deployed SHA confirmed as `730b1b3` from Railway's deployment record instead |
| Proof-of-life | **NOT RUN** — host unreachable |
| CRM smoke test | PASS against this code in CI (MongoDB 7) and locally. **NOT RUN** against production |
| Cross-tenant smoke | PASS in CI and locally. **NOT RUN** against production |
| Scheduler verification | **FAILED — and this is the finding, not a gap in testing.** Production has never received a scheduled request. Proven three ways: the workflow's own log (`BASE_URL:` and `CRON_SECRET:` both empty), 1,622 green no-op runs, and Railway's HTTP log containing no `/api/cron/*` request at all |
| Outbound send verification | **NOT RUN** — no adapter is deployed, and `gmail.send` has not been granted |
| Inbound verification | **NOT RUN** — same |
| Attribution verification | **NOT RUN** in production; 31 adversarial tests pass in CI |

---

## Configuration

| | Status |
|---|---|
| GitHub required secrets | **BOTH MISSING.** `CLIENTVERSE_PRODUCTION_URL` and `WEBHOOK_CRON_SECRET`. The GitHub Actions secrets API is blocked for this session (`403: Access to this GitHub Actions path is not permitted through this proxy`), so this is an owner action |
| Railway required variables | 12 present. Missing: `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET`, `PUBLIC_BACKEND_URL`, `GOOGLE_REDIRECT_URI`. One duplicate to delete: `Mongo_url` |
| Google configuration | Client id and secret present. `gmail.send` newly requested and **not yet granted** — requires disconnect and reconnect |
| Stripe configuration | Not configured in either mode. The webhook route refuses events without a signing secret, which is correct fail-closed behaviour |
| MongoDB configuration | Atlas, credentials in Railway only. **Backup status unknown — owner to confirm.** Network access is `0.0.0.0/0` and should be narrowed |
| Security configuration | See handoff §9. One production defect found and fixed: the CSP blocked the font host the SPA imports both typefaces from |

---

## Owner Actions Required

1. **Set `CLIENTVERSE_PRODUCTION_URL` and `WEBHOOK_CRON_SECRET` as GitHub repository secrets.** Until this is done no automation runs in production, and none ever has.
2. **Merge this branch to `main`** and confirm `/api/health` returns the merge SHA.
3. **Run `scripts/crm_release_smoke.mjs` against production** and keep the evidence file.
4. **Grant the `gmail.send` scope** by disconnecting and reconnecting Google.
5. **Send one real email, then send it again**, and confirm only one arrives.
6. **Reply to it** and confirm the reply lands on the conversation and the contact timeline.
7. **Confirm one recovery outcome** and check the ledger's verdict — including that a case with no sent message comes back *unattributed*.
8. **Confirm the Atlas backup policy**, narrow network access, delete `Mongo_url`, and rotate `ADMIN_PASSWORD` if it has ever left the Railway dashboard.

Steps 1 and 2 are the difference between a product that runs and one that does not.

---

## Outstanding Defects

### 1. Production is unreachable from this session — everything is verified short of production

- **Severity:** Critical to the commission, not to the product
- **Affected capability:** Every stage after TESTED
- **Evidence:** `curl` to `https://clientverse-crm-production-production.up.railway.app/api/health` returns `000`; the agent proxy's failure log records `connect_rejected — gateway answered 403 to CONNECT (policy denial)` for that host at 2026-09-21T21:35:21Z. An earlier session hit the same wall (commit `3150530`: "the session egress policy blocks railway.app")
- **Recommended fix:** The owner runs the §8 verification steps from a network that can reach the host
- **Blocking launch:** YES for a launch that claims production verification; NO for merging

### 2. The scheduler has never made a single production request

- **Severity:** Critical
- **Affected capability:** All recovery automation — detection, the durable work queue worker, strategy composition, the recovery runner, approval expiry, integration sync, the daily digest
- **Evidence:** Three independent sources. Workflow run 35650309168 logs `CLIENTVERSE_PRODUCTION_URL or WEBHOOK_CRON_SECRET is not configured; nothing was called.` with both variables empty. 1,622 consecutive green runs, every one a no-op. Railway's HTTP request log for the live deployment contains no `/api/cron/*` request of any kind
- **Recommended fix:** Owner action 1. The workflow now fails loudly in this state and verifies its run against a production-side ledger, so it cannot recur silently
- **Blocking launch:** YES

### 3. `/api/cron/recovery-runner` was served but never scheduled

- **Severity:** High
- **Affected capability:** Recovery execution — an approved case would have sat approved indefinitely
- **Evidence:** Found by `scripts/validate_config.py` on its first run
- **Recommended fix:** Done. Scheduled on the five-minute tick alongside the work queue it feeds
- **Blocking launch:** NO (fixed)

### 4. Fourteen background tasks could be garbage-collected mid-flight

- **Severity:** High
- **Affected capability:** Every scheduled sweep and every webhook dispatch
- **Evidence:** `asyncio.create_task` was called without retaining the result in 14 places. Python holds only a weak reference, so a running task can be collected and simply stop, with no error anywhere
- **Recommended fix:** Done. All routed through `spawn_background`, which holds a strong reference until completion
- **Blocking launch:** NO (fixed)

### 5. The CSP blocked the application's own fonts in production

- **Severity:** Low
- **Affected capability:** Visual presentation on every production page
- **Evidence:** Console errors while driving the built SPA: both `api.fontshare.com` stylesheet imports refused by `style-src`
- **Recommended fix:** Done. The two font hosts the application actually uses are allowed; nothing else
- **Blocking launch:** NO (fixed)

### 6. The specification's attribution premise does not match the repository

- **Severity:** Medium (planning accuracy)
- **Affected capability:** Attribution
- **Evidence:** The specification states the ledger is built and tested but unmerged. `git ls-remote` shows 34 remote branches, none of them attribution work; there are no open pull requests; and the only occurrence of the word in the codebase is an unrelated one in a UI file
- **Recommended fix:** Built from scratch on this branch. Reported rather than forced to match the assumption
- **Blocking launch:** NO

### 7. Sixteen tests cannot run without a real MongoDB

- **Severity:** Low
- **Affected capability:** Local development only
- **Evidence:** Under the `mongomock://` fallback, 675 of 695 collected tests pass. The 16 failures are all driver fidelity, not product defects: tests that write through their own client and read back over HTTP cannot share an in-process store across two processes, and mongomock does not enforce unique indexes under concurrency. All 16 pass in CI against MongoDB 7
- **Recommended fix:** None needed. CI is the gate and it uses the real thing; this is documented in `backend/requirements-dev.txt`
- **Blocking launch:** NO

### 8. 121 pre-existing type findings in the older modules

- **Severity:** Low
- **Affected capability:** None observed
- **Evidence:** `mypy .` reports 121, almost all the same shape — a value read from Mongo is `Optional[dict]` and the code knows it is not None
- **Recommended fix:** The ratchet in `scripts/typecheck.py`. Six modules are clean and blocking; the rest are reported. A module joins the blocking set by being clean, so the number can only go down
- **Blocking launch:** NO

---

## Secrets Statement

| | |
|---|---|
| Plaintext production secrets included in this report | **NO** |
| Production secrets committed to source control | **NO** |
| Secrets stored only in approved secret stores | **YES** — Railway service variables and (once the owner sets them) GitHub repository secrets. The cron bearer token is never written to the production ledger; the intake token is stored hashed and shown exactly once |

---

## FINAL STATUS

| Capability | Status | The one-line reason |
|---|---|---|
| **CRM BASELINE** | **PARTIAL** | Complete and fully tested; not deployed, so not production-verified |
| **RECOVERY DETECTION** | **PARTIAL** | All ten families implemented and tested; the schedule that would run them has never reached production |
| **RECOVERY PLANNING** | **DEPLOYED NOT VERIFIED** | Pre-existing and deployed, but never exercised in production because nothing has ever triggered it |
| **APPROVALS** | **DEPLOYED NOT VERIFIED** | Deployed; the text-binding strengthening is on this branch and not yet deployed |
| **SCHEDULING** | **BLOCKED** | Two repository secrets, owner-only. Nothing has run since deployment |
| **OUTBOUND EMAIL** | **PARTIAL** | Adapter implemented and tested against every provider answer; cannot send until `gmail.send` is granted |
| **INBOUND COMMUNICATION** | **PARTIAL** | Implemented and tested; the poll that drives it needs the scheduler secrets |
| **ATTRIBUTION** | **PARTIAL** | Built and adversarially tested; never exercised against production data |
| **REPORTING** | **PARTIAL** | Both surfaces built and verified in a browser; not deployed |
| **PRODUCTION CERTIFICATION** | **BLOCKED** | The production host could not be reached from this session |

**No capability is LIVE VERIFIED, and none is claimed to be.** Seven of the ten are one
merge and two repository secrets away from being verifiable; the remaining three also
need the Google send grant. The handoff is written so the owner can close each of those
stages and see for themselves rather than take this report's word for it.
