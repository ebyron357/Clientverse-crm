# Provider authorization and Recovery Proof implementation evidence

Date: 2026-10-13. Base: `1ff7b4c37f1a8d047d984003c457231ec86b33f3`.
Branch: `codex/crm-provider-scope-scroll-20261013`.
Status: implemented and locally tested; awaiting review and authorized release. This is an evidence report, not a replacement governing document.

## Changes

- Google OAuth connection records now contain the scopes actually granted by Google. Previously they advertised all requested scopes, including send permission when consent was partial. Existing encrypted credentials already stored the actual grant; the connection record used by Gmail authorization now agrees with it. Refresh-token preservation remains intact. Existing connection records are not migrated; reconnect and certify the authorized tenant before live sending.
- A failed provider lookup leaves an earlier message's delivery outcome unknown. Previously a lookup rejected because OAuth was revoked could mark the message failed, making an unsafe duplicate retry eligible. Only a successful lookup can now resolve delivery status.
- Recovery Proof now has native, scroll-aware Revenue / Delivery / Cases navigation, keyboard focus transfer, a gentle one-time section entry, and responsive case rows. Reduced motion uses immediate navigation with no entry animations. Content is never hidden pending animation, and there is no perpetual animation loop, scroll hijacking, or new dependency.

The website enhancement adapts the flow, one-time IntersectionObserver reveal, native scrolling and reduced-motion patterns from `nateherkai/scroll-craft` at `75d81f74e83692add18cd7a8a8e078b8a887a579`, under `plugins/nateherk-design/skills/scroll-craft`. The full landing-page engine was inspected but not copied into this operational CRM report. Existing branding, data distinctions, authorization and detail controls are preserved.

## Verification

| Check | Observed result |
| --- | --- |
| Focused backend tests | 64 passed: provider lifecycle, Gmail provider, reconciliation lookup |
| Baseline regression check | Four new cases fail against unchanged base server; all pass after fixes |
| Backend Ruff | Pass, entire backend |
| Configuration validator | Pass |
| Frontend lint | Pass, zero warnings |
| Production build | Pass, `CI=true yarn build` |
| Browser QA | 1440×900, 390×844, 320×740; synthetic local APIs only |
| Mobile layout | No horizontal document overflow in all three viewports; new navigation links 44px high |
| Accessibility | Keyboard focus reaches section; reduced motion produces zero report animations; new navigation has zero axe violations |
| Existing report flow | Case detail opens and returns in all three viewports |
| Runtime | No application JavaScript errors in the successful browser run; existing external font requests intentionally blocked |

Backend command: `python -m pytest tests/test_provider_lifecycle_unit.py tests/test_gmail_provider.py tests/test_reconciliation_lookup.py -q` from `backend/`.
The new regression cases exercise partial/empty/full consent and authorization-denied/error/absent/found delivery lookups, including tenant identity.

[Browser measurements](browser-results.json), [desktop screenshot](recovery-proof-desktop.png), [mobile screenshot](recovery-proof-mobile.png). Screenshots contain synthetic QA fixtures, not customer records.

Production bundle comparison against a separate clean build of the base commit: JavaScript adds 885 gzip bytes (0.252%); CSS adds 299 gzip bytes. No new runtime dependency or media request is introduced. These are local bundle measurements, not a production Core Web Vitals certification. [Exact comparison](bundle-comparison.json).

## CI-discovered dependency repair

Initial PR run [38427696213](https://github.com/ebyron357/Clientverse-crm/actions/runs/38427696213) passed the full Backend API tests job (including CRM release smoke) and frontend build. Its dependency scan identified four existing vulnerabilities in pinned PyMongo 4.6.3: CVE-2026-88029, CVE-2026-96747, CVE-2026-96748 and CVE-2026-96749.

The security follow-up pins PyMongo 4.18.3 and Motor 3.7.1 together. [Motor's official requirements](https://github.com/mongodb/motor/blob/3.7.1/requirements.txt) permit PyMongo >=4.9,<5.0; the old Motor 3.3.1 is incompatible with PyMongo's newer internals. [PyMongo 4.18.3's official release](https://www.mongodb.com/community/forums/t/pymongo-4-18-3-released/344145) also fixes CVE-2026-106435. No audit exception, suppression or scanner gate was added.

With the upgraded drivers, 64 focused tests pass, pip reports no broken requirements, and `pip-audit -r backend/requirements.txt` reports no known vulnerabilities. CI runs against MongoDB 7. Production server version was not retrieved; confirm MongoDB >=4.4 before the separately authorized release because PyMongo 4.18 drops older server support. This is a driver version update, not a database migration or an async architecture rewrite.

## Limits and next actions

- The full local backend suite was stopped by automatic approval review because a test unexpectedly attempted an untrusted external webhook. That call was not retried or bypassed. The focused deterministic suite above passed. The initial PR CI independently passed the full Backend API tests job; the local suite remains unverified and a separate local-only webhook harness is needed for local completion.
- Jev QC was not run: its endpoint and token are unavailable in the execution environment. No `VERIFIED COMPLETE` or live-provider certification claim is made.
- Live OAuth consent, Gmail sending, Calendar sync and Stripe operations were not performed. Tenant connection state is not proven by service-variable presence.
- Production is still on the base SHA. Railway's main-branch deployment and Vercel's main production deployment were verified; no production deployment, merge, secret change or database mutation was performed.
- Governance PR #34 already addresses historical operating-document reconciliation. This PR makes no material governance policy changes and does not duplicate that work.
- The approved YouTube reference `VzKy4AuKjbU` could not be retrieved; no video feature claims or unapproved feature expansion were made.

Maintainer: review the code and CI, supply the existing Jev route if applicable, authorize any live provider certification, and approve merge/deployment separately.
