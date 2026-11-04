# AI quality audit record — 2026-11-04

| Field | Value |
| --- | --- |
| Repository | `ebyron357/Clientverse-crm` |
| Commit inspected | `main@e75bb71` (merge of PR #55) |
| Environment | Agent sandbox. Backend under `mongomock` (in-process and as a live uvicorn API); frontend production build served by the API. **No real MongoDB, no production access** (agent egress refuses `crm.clientverse.io` and Railway). CI against `mongo:7` was the real-database check for every fix. |
| Inspected scope | Backend (`server.py` and routers), frontend (`frontend/src`), CI workflows, scripts, dependencies. Three parallel code reviews: security and data; UI honesty and hygiene; accessibility, performance and testing. Each finding below was re-checked against the code before recording. |
| Standard | Canonical Version 1.0 (see `docs/AI_SOFTWARE_QUALITY_ADOPTION.md`) |
| Performed by | Claude Code agent session, on the owner's instruction. **This is not the independent QA/security review or the Jev QC gate**; both remain required and unrecorded. |
| Owner approval | Fix PRs #57 and #58 merged on the owner's instruction (2026-11-04). #59 open. |

## Commands run (results)

| Command | Result |
| --- | --- |
| `ruff check .` (backend) | Pass |
| `python scripts/typecheck.py backend` | Printed "clean" with mypy absent: **false pass** (C-06). With mypy installed: 0 findings in the 16 blocking modules |
| `pip-audit -r backend/requirements.txt` | No known vulnerabilities |
| `yarn audit --groups dependencies` | 237 advisories (3 critical, 151 high), almost all build-time via `react-scripts` 5.0.1; runtime: axios 1.18.0, react-router 7.15.x (RSC/SSR advisories not applicable to this SPA), zod 3.24.4 (C-30) |
| `yarn lint --max-warnings=0`, `CI=true yarn build` | Pass; one 505.6 kB (gzip) bundle (C-07) |
| Backend suite under mongomock with a live API | 1153 passed; the 16 failures and 2 errors are mongomock limitations, identical before and after every fix |
| axe-core WCAG 2.0–2.2 A/AA, 31 pages, 390 and 1280px, light and dark, empty and seeded | 0 violations except C-24 |
| Git history secret scan | Only the known `whsec_` value in `test_reports/iteration_10.json` (C-40) |

## Findings

Severity: P0 exploitable or data loss now · P1 fix before more customers · P2 should fix · P3 minor. No P0 was found. Every Mongo read and write is tenant-scoped (AST scan plus manual review), so no cross-tenant path was found.

| ID | Sev | Category | Finding | Evidence | Status |
| --- | --- | --- | --- | --- | --- |
| C-01 | P1 | 6 Security | SSRF: a self-registered admin could point a webhook at loopback, private or metadata addresses and read the result from the delivery log | `server.py` `WebhookInput.url: str`, `requests.post(webhook["url"])` following redirects, raw error stored; reproduced in-process | **Fixed, PR #57 (merged)**: https-only, private literals and names refused on save, every attempt re-resolved, no redirects, coarse error labels. Residual: check-then-connect window (C-31) |
| C-02 | P2 | 6 Security | Self-registration accepted any password ("a") | `register()` skipped `_new_password_problem` | **Fixed, PR #57** |
| C-03 | P2 | 6 Security | Expired lockout kept its count, so one wrong guess re-locked the owner; no per-address limit on failed sign-ins | `_record_login_failure` | **Fixed, PR #57**: decay plus 30 failures / 15 min per address. Residual: many addresses can still lock one email for 15 min (C-32) |
| C-04 | P2 | 6 Security | Google OAuth `state` not bound to the browser that started it | `server.py` OAuth start/callback | **Open**, owner decision (changes Connect Google) |
| C-05 | P2 | 6 Security | Bearer token in localStorage; CSP allows inline script | `lib/api.js`; `server.py` CSP | **Open**, owner decision (changes sign-in) |
| C-06 | P2 | 13 Testing | Type-check gate passed when mypy was missing or crashed | `scripts/typecheck.py` ignored return code | **Fixed, PR #57** |
| C-07 | P2 | 10 Performance | One 505.6 kB gzip bundle, no code splitting | build output; no `React.lazy` | **Fix in PR #59**: 206.6 kB main bundle, a chunk per page |
| C-08 | P2 | 10 Performance | Static files served uncompressed and uncached | no GZip, no `Cache-Control` | **Fix in PR #59**: static-only gzip, immutable cache for hashed files, `no-cache` for the shell; API not compressed (BREACH) |
| C-09 | P2 | 5 Accessibility | Closed phone menu reachable by Tab, off screen | `AppShell.jsx` aside `-translate-x-full` | **Fixed, PR #58 (merged)** |
| C-10 | P2 | 5 Accessibility | Phone menu: no Escape, no focus move or return | `AppShell.jsx` | **Fixed, PR #58** |
| C-11 | P2 | 5 Accessibility | Focus lost to `<body>` when Search and Create dialogs close | state-controlled dialogs | **Fixed, PR #58** |
| C-12 | P2 | 5 Accessibility | Every signed-in page had the same title; no focus move on navigation | 31 pages, one title | **Fixed, PR #58** |
| C-13 | P2 | 3 Functional UI | Several saves failed silently on a server error | `WorkspaceDetail.jsx`, `OutcomeGraph.jsx`, `WebhookManager.jsx` | **Fix in PR #59**: `attempt()` shows the server's reason; secret rotation confirms first |
| C-14 | P2 | 13 Testing | Accessibility evidence dated 2026-08-17 and run by nothing; no frontend tests or pre-merge browser checks | `frontend/scripts/axe-release-audit.mjs` unreferenced; no `*.test.*` | **Open**, needs a CI job (owner decision on scope) |
| C-20 | P3 | 6 Security | HSTS never sent behind Railway (uvicorn sees http) | `server.py` scheme check | **Fixed, PR #57**: sent whenever production |
| C-21 | P3 | 6 Security | Custom-field labels reached CSV headers without the formula guard | `data_transfer.py` header row | **Fixed, PR #57** |
| C-22 | P3 | 6 Security | Public source maps | `GENERATE_SOURCEMAP` unset | **Fixed, PR #57** (Dockerfile) |
| C-23 | P3 | 10 Performance | Render-blocking Google Fonts link for a font already bundled | `public/index.html` | **Fixed, PR #58** |
| C-24 | P3 | 5 Accessibility | Command dialog list empty on open (`aria-required-children`, known `cmdk` issue); Directory empty-state heading order | axe | **Open** |
| C-25 | P3 | 7 Backend | `/webhook-deliveries?limit` unbounded | `server.py` | **Fixed, PR #57** (max 500) |
| C-26 | P3 | 7 Backend | Status fields accept any string; non-unique memberships index; concurrent same-email registration leaves an empty org; long search input can 500 | `TaskStatus`, startup indexes, `crm_core._escape_regex` | **Open** |
| C-27 | P3 | 2 Hygiene | ~27 unused UI components; unused frontend and backend packages; dev tools in the production image | `components/ui/*`, `package.json`, `requirements.txt`, Dockerfile | **Open** |
| C-28 | P3 | 1 Visual | 542 raw palette classes, dark mode patched by ~40 global `!important` overrides | `index.css`, components | **Open** |
| C-29 | P3 | 3 Functional UI | Search box searches pages only, not records; an out-of-date note on placeholder pages | `GlobalCommandDialog.jsx`, `ModuleStatus.jsx` | **Open** |
| C-30 | P3 | 6 Security | Runtime frontend packages with advisories (axios, react-router, zod) | `yarn audit` | **Open** |
| C-31 | P3 | 6 Security | SSRF residual: the HTTP library resolves again after the check | `outbound_url.py` docstring | **Open**, pin the connection to the checked address |
| C-32 | P3 | 6 Security | Lockout residual: many addresses can still lock one email for 15 minutes | lockout design | **Open**, owner decision (CAPTCHA or softer lock) |
| C-33 | P3 | 13 Testing | Rollback documented but never rehearsed | closeout handoff §rollback | **Open** |
| C-40 | — | 6 Security | Known: legacy webhook secret in git history; `Mongo_url` variable to delete; Atlas backups unverified | `REMAINING_WORK.md`, owner manual | **Open, owner action** (not new) |

## Verified OK (no finding)

- Tenant isolation on every Mongo read and write; cross-tenant references (company_id, contact merge, inbound assign) rejected; agency act-as rechecks the parent tenant and admin role.
- bcrypt passwords; JWT secret length and placeholder checks at startup; HS256 pinned; revoked tokens hashed with TTL; password change ends older sessions; HttpOnly, Secure cookie; CSRF guard on cookie-authenticated writes; retired Google sign-in answers 410.
- Invite tokens hashed, compared in constant time, single use. Cron secret compared with `hmac.compare_digest` and deduplicated. Stripe webhooks signature-verified and claimed through a unique index.
- Import admin-only and capped (5 MB, 5,000 rows); export cells formula-guarded; no `$where`; filters limited to known fields.
- Production startup refuses non-https CORS origins and missing secrets. Contacts, companies and deals are archived, not deleted. A real restore drill workflow exists.
- Every frontend API call matches a backend route; every route renders a real page; "Coming soon" modules show no sample data; charts use live data; no fabricated testimonials or metrics.
- No horizontal scroll at 390px; one h1 and one main per page; tables have headers; status colours paired with text; reduced motion honoured; dialogs trap focus.

## Not inspected (required before release)

- Category 9, AI agent and workforce governance, and category 12, privacy and regulatory readiness: not in this pass.
- Real Core Web Vitals and Lighthouse; Safari, Firefox and Edge; screen readers; 400% zoom.
- Production behaviour: edge compression, HSTS on the live domain, Railway's `X-Real-IP` handling (the public rate limits trust it).
- Atlas backups; live Gmail, Google Calendar and Stripe flows.
