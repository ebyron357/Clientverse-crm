# Password recovery integration verification

Date: November 17, 2026 (America/New_York).

## Code reviewed

The recovery branch combines the existing recovery implementation with main
`dd576c372980feb597ff1316130701ec04f9e0d5`. Main's lazy-loaded pages and lead transactions
are preserved. The public recovery screens use the existing layout.

Additional corrections require an active membership in the user's home workspace,
preserve an accepted reset link when a subsequent audit write fails, and report a
committed password change truthfully if later cleanup or notification bookkeeping fails.
Authoritative credential and session-version checks still invalidate old links and
sessions. Existing owner passwords remain unchanged by application startup.

## Local checks

| Check | Result |
| --- | --- |
| Recovery, password change, session revocation, login lockout, agency, authentication and lead-transaction regression tests | 91 passed, zero failures, 95.16 seconds |
| Database | Disposable MongoDB 7.0.16 replica set |
| Recovery-specific cases included above | 36 |
| Backend Ruff | Passed |
| Configured blocking type gate | Passed; 17 blocking modules clean |
| Other type findings | 125 findings in nine nonblocking modules, reported without suppression |
| Configuration validation | Passed |
| Python compilation | Passed |

The tests use synthetic accounts and mocked email delivery. Six dependency deprecation
warnings were reported. JUnit outcomes and timings are in
[password-recovery-integration-20261117.xml](password-recovery-integration-20261117.xml);
the runner hostname has been omitted.

A separate bounded source review checked home-workspace eligibility, post-commit failure
handling, link/session invalidation and preservation of main's lead-transaction code.
No blocking defect was found in that reviewed recovery delta.

## Limits

These results do not establish production deployment, actual inbox delivery, provider
certification, or final combined-branch acceptance. The full combined repair candidate
and hosted CI are separate checks. Operator-document updates are held outside this
public repair publication; this evidence does not claim those manuals were updated.
