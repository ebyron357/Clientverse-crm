# Password recovery — scoped implementation and release evidence

Repository: `ebyron357/Clientverse-crm`. Base: `e75bb71145b197c298991098c8ab0ca9a349b362`.
Branch: `codex/secure-password-recovery`. Date: 2026-11-04.
Review: [draft PR #56](https://github.com/ebyron357/Clientverse-crm/pull/56).
Scope: signed-out password recovery, owner bootstrap behavior, session revocation, mail,
rate limits, audit records, tests, governing/owner documentation. This is not a whole-CRM audit.
Implementation revision: the commit carrying this record; exact PR/CI head is recorded by GitHub.

## Findings and repair

| Finding | Severity | Reproduction and evidence | Impact and cause | Repair and acceptance | Owner / status |
|---|---|---|---|---|---|
| REC-01: locked-out owner cannot recover independently | P1 | Base `frontend/src/pages/Login.jsx` directs users to a workspace admin; production OpenAPI has no `/api/auth/forgot-password` or `/api/auth/reset-password` | Owner has no authenticated route to choose a new password | Public recovery screens and endpoints, mailbox proof, 20-minute single-use link, no automatic login. Test `test_signed_out_owner_recovers_and_restart_does_not_restore_bootstrap` | Engineering implementation; owner release decision pending |
| REC-02: startup restores environment password | P1 | Base `backend/server.py::seed` overwrites existing owner hash from `ADMIN_PASSWORD` on every boot | A new chosen password is lost after restart; obsolete credentials can return | Bootstrap-only seed; regression covers reset then seed then login with new/old passwords | Implemented and locally tested; not deployed |
| REC-03: timestamp-only session invalidation has a login race | P1 | A login that read an old hash can issue its token after recovery; millisecond timestamps alone cannot distinguish it | A late token can survive credential replacement | Random `session_version` changes with password; login and agency switching carry the version observed. In-flight password changes use compare-and-swap. Regression rejects a token issued after reset with the old version | Implemented and locally tested; not deployed |
| REC-04: transactional recovery mail unavailable in production | P1 release blocker | Railway names-only inspection lacks both recovery provider variables | No provider credential or verified sender configured | Exact configuration and private owner procedure in manual §9.2.1. Provider transport is tested locally; real inbox acceptance remains required | Owner/provider setup; BLOCKED |
| REC-05: locally throttled attempts consume shared recovery capacity | Medium; two independently reachable endpoints | Independent source review of `b1ae0a3` found global counters charged before local limits in both request and reset paths; isolated MongoDB regressions reproduced denial to an unrelated user | A blocked caller could exhaust recovery capacity for other accounts | Apply IP/email admission before shared mail capacity and IP admission before shared reset capacity. Both regressions fail before the fix and pass afterward; independent source re-review confirms the correction | Fixed on the recovery branch; not deployed |

## Architecture and security contract

- The existing FastAPI/Motor/MongoDB and React SPA are preserved. Recovery does not use
  Google OAuth, create an identity/tenant, alter roles, or enable disabled memberships.
- `/api/auth/forgot-password` returns HTTP 202 and the same JSON for known, unknown,
  disabled, throttled, or provider-unconfigured addresses. The response path performs **no
  account lookup and no provider request**. Encrypted recipient jobs are persisted uniformly;
  the worker later resolves eligibility. Invalid email syntax can return schema validation.
- Resend is a fixed HTTPS destination, through the existing `httpx` dependency, with a
  15-second timeout, no redirects and no automatic retries. The sending key is backend-only.
  A provider acceptance is not evidence of delivery to the inbox. There is no development
  endpoint, logging fallback, or screen that returns a real token.
- A 32-byte random URL-safe token is generated at delivery time. Only its SHA-256 digest,
  user ID, credential fingerprint and expiration are stored. Reset URL origin comes exclusively
  from validated `FRONTEND_URL`, never request `Host`, `Origin` or a submitted redirect.
- The token travels in a URL **fragment**, not a query/path. The reset page moves it into
  component memory and clears the fragment without storing it in local/session storage.
  Passwords are never mailed. Recovery pages/API responses use `no-store`, `no-referrer`, and
  `noindex, nofollow`. Merely visiting a link does not consume it.
- Reset requires an unexpired grant, the same credential and email fingerprints, and an active membership.
  A single MongoDB user-document compare-and-swap replaces the password and session version.
  This is the single-use boundary: concurrent submissions, including different valid links,
  cannot both replace the same credential. All old links become invalid even if grant cleanup
  fails after the atomic update. Current-password changes and admin resets also invalidate links.
- Success clears login lockout and temporary-password state, invalidates previous JWTs and
  legacy sessions, clears the browser auth cookie, and queues a security notice. It does not
  issue a new authenticated session. Users must sign in. An older queued request is skipped
  if the password changed after it was queued.
- Limits are atomic MongoDB counters with unique `_id` keys, shared across replicas/restarts:
  requests: 3/email/hour, 20/network address/15 minutes, 100/global/hour; reset attempts:
  30/network address/15 minutes and 300/global/15 minutes. Windows are fixed, so boundary
  bursts can span adjacent windows. Request throttling stays generic; reset throttling is 429.
  No recovery request locks the account. Both real and unknown addresses consume counters.
- Client network identity is `request.client.host`. The application does not parse arbitrary
  forwarding headers. Uvicorn must trust only the actual upstream proxy addresses; do not set
  an unrestricted forwarding trust policy. If the peer is a shared proxy, the limit is
  conservatively shared until the infrastructure trust boundary is validated.
- `password_recovery_jobs` encrypts recipients with the existing Fernet key, removes them
  after an attempt, and expires records after 20 minutes. Workers atomically claim jobs.
  Ambiguous in-flight sends after a crash become `delivery_unknown`; they are not resent.
  The recipient can request a new link subject to limits. There is no promise of exactly-once
  provider delivery across a process crash. Link single-use does not depend on delivery state.
- Grants expire after 20 minutes, checked on redemption regardless of MongoDB TTL timing.
  Counter TTL is two fixed windows. `password_recovery_events` retains outcomes for 90 days
  and uses HMAC email identifiers, not submitted email/IP plaintext. Success also emits
  `auth.password_recovered` to the existing tenant audit log. No token, reset URL, password,
  provider response body, or API key is included. Provider settings and data retention require
  the owner's normal processor/access review; no regulatory certification is claimed.
- Required indexes are built at startup and fail closed. No destructive migration or replica-set
  transaction is needed. Existing identities acquire a session version on their next change.

## Validation

| Check | Result and scope |
|---|---|
| Focused backend tests | **PASS: 45 tests** on `1075803`, real MongoDB 7.0.16, Python 3.12.10; recovery, password change, login lockout and agency modules. Final hardening adds the in-flight email-change case and expiry recheck; **25 recovery tests pass** on that revised code. Synthetic isolated accounts only; email transport replaced. |
| Full backend suite | **PASS: 1,209 passed, 4 skipped** in GitHub CI [41809667634](https://github.com/ebyron357/Clientverse-crm/actions/runs/41809667634) on `10758036d5e0922feec0c8112d3132e41ca60f45`, MongoDB 7, Python 3.11. Final email-race/expiry hardening is locally regression-tested and requires the new head's CI gate; the linked run does not certify later commits. |
| CRM release smoke | **PASS** in the same GitHub run. No production smoke claimed. |
| Recovery browser checks | **PASS: 27 checks**, actual optimized build, Chromium, 390/768/1440px, form states, password mismatch, invalid/expired response, network failure, no auto-login, fragment removal, keyboard tab order, no JS page errors, and axe WCAG A/AA checks. UI API responses are intercepted; backend semantics are covered independently with real MongoDB. |
| Visual check | Desktop recovery screen inspected and consistent with the existing AuthLayout. Manual screen-reader, Safari/Firefox/Edge and independent visual review remain unverified. |
| Frontend | ESLint with zero warnings and CI production build passed. |
| Backend static checks | Ruff clean; configuration validator passed; 17 blocking mypy modules clean, including new recovery module. 123 findings remain in 8 non-blocking legacy modules; not silently waived or fixed by this task. |
| Dependencies | `pip-audit -r backend/requirements.txt`: no known vulnerabilities reported. No new production dependency added. |
| Jev QC | **QC GATE ERROR — FAIL CLOSED**: submitter ran, `JEV_QC_WEBHOOK_URL` absent; no gate request or `n8n_execution_id`. Token also absent. No verified-complete claim. |
| Independent security review | Independent agent architecture/backend source review completed on `b1ae0a3`; two medium quota-poisoning findings reproduced and fixed. A separate source re-review confirmed both fixes and found no further concrete issue in that correction. Parent reviewed all other changed source files. This scoped automated review is not human certification, deployment approval, or Jev QC. |

Test commands: `python -m pytest tests/test_password_recovery.py tests/test_password_change.py
tests/test_login_lockout.py tests/test_agency.py -q` in backend; `node
scripts/password_recovery_browser.mjs` after frontend build; normal repository lint, types,
configuration and dependency gates. CI includes the new browser check and the recovery tests.

Follow-up validation on 2026-11-04: the two new quota-isolation regressions first failed
against the reviewed code, then the complete recovery/password-change/login-lockout/agency
selection passed **48 tests** on real MongoDB 7.0.16 after the fix. Ruff and the 17 blocking
type-check modules pass. The docs-only follow-up `25b48b9` also passed all CI jobs in run
`41819930325` (1,210 backend tests); the subsequent code-fix CI is recorded on the PR.
The review concerns application code and source controls; actual provider setup, inbox
delivery, production proxy attribution, manual screen-reader review and Jev remain unverified.
Windows build invocation used `NODE_ENV=production` in the environment before invoking CRACO;
the repository's existing `yarn build` shell syntax targets Linux CI.

## Deployment validation and blockers

Direct production observations (2026-11-04):

- `GET https://crm.clientverse.io/api/health`: 200, database up,
  `git_sha=e75bb71145b197c298991098c8ab0ca9a349b362`.
- Railway: deployment `98967475-8f35-47dc-9519-499e0a6b0a79`, SUCCESS, same commit,
  created 2026-11-02T03:43:59.769Z.
- OpenAPI has neither recovery endpoint. The new non-destructive release probe fails on
  recovery-page `Referrer-Policy` (`strict-origin-when-cross-origin`, expected `no-referrer`).
  This is expected for the old deployed build; it is not a passing recovery deployment test.
- Names-only configuration read: both `PASSWORD_RECOVERY_RESEND_API_KEY` and
  `PASSWORD_RECOVERY_FROM` absent. Existing `FRONTEND_URL`, `INTEGRATION_ENC_KEY`, `JWT_SECRET`
  and core database configuration are present. No values were printed or modified.
- GitHub's existing Vercel integration automatically built a frontend preview for PR #56.
  That is not the Railway production deployment and is not recovery certification. The
  canonical application and acceptance target remain `https://crm.clientverse.io`.

**Implemented is not deployed.** No merge, deployment, production email or owner password
change has been performed. The sole owner setup and recovery procedure is the full revised
[Owner/Admin Manual §9.2](../CLIENTVERSE_CRM_OWNER_ADMIN_MANUAL.md#92-forgotten-password).

Engineering post-release check: set `CLIENTVERSE_EXPECTED_GIT_SHA` to the full approved
deployed SHA and run `node scripts/password_recovery_deployment.mjs`. It defaults to the
canonical production origin; an explicit HTTPS staging origin may be supplied through
`CLIENTVERSE_RECOVERY_BASE_URL`. It checks SHA, health, public routes, headers and invalid-token
rejection; it sends no mail and changes no password. Real mailbox receipt, full signed-out reset,
restart durability, old-session rejection, owner sign-in and independent QA remain separate gates.

Rollback: this is additive data/index work; preserve existing users and records. Prefer a
forward repair or disabling recovery email configuration while retaining the bootstrap-only
seed behavior. Rolling back to the old seed implementation can restore an obsolete owner
password from `ADMIN_PASSWORD`; that is a security-sensitive rollback requiring an explicit plan.

References: [OWASP recovery guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html),
[Resend send-email API](https://resend.com/docs/api-reference/emails/send-email), governing
document C-40/O-19, approved quality master v1.0, and AGENTS.md Jev gate. External MCP/agent
allowlists and scanner gates are unchanged; no new external agent capability is introduced.
