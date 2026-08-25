# ClientVerse Current Live Proof Package

**Package created UTC:** 2026-08-16T22:30:00Z

| Evidence ID | Artifact | Exact location | What it proves | SHA/identifier if applicable |
|---|---|---|---|---|
| E-01 | Release candidate and deployment metadata query | `current-live-deployment-metadata.json` | Current Git branch/SHA/PR identity and GitHub Deployments API result. Hosting provider identity, deployment ID, timestamp, environment, and hosting-reported SHA are `UNVERIFIED`. | Candidate `f78da2081c6db8b21ad8978cf3a7fcd93cdc15c2`; PR #9 |
| E-02 | Endpoint checks and callback redirect | `current-live-endpoints.md` | HTTP status, timestamp, final URL, redirect, and protection observations for the currently reachable public frontend, API, health, and callback URLs. | N/A |
| E-03 | Raw health response | `current-live-health-response.json` | HTTP 200 with `{ "service": "ClientVerse", "version": "v1", "status": "ok", "database": "up" }`. | N/A |
| E-04 | Runtime configuration presence | `current-live-runtime-configuration.md` | Name-only environment presence report from the backend process serving external port 8001. | Process `21413` |
| E-05 | Sanitized live API lifecycle transcript | `current-live-proof-api.json` | Login, company, contact, opportunity, closed-won, workspace, commitment, re-login, and post-reauthentication retrieval results for `CLIENTVERSE-PROOF-20260816222022`. | Controlled label `CLIENTVERSE-PROOF-20260816222022` |
| E-06 | Sanitized live authorization transcript | `current-live-security-api.json` | HTTP 401 unauthenticated protection, HTTP 200 authenticated access, HTTP 404 cross-tenant denial, and HTTP 403 member admin-action denial. | Controlled label `CLIENTVERSE-PROOF-SECURITY-20260816222811` |
| E-07 | Live browser observations | `current-live-browser-observations.md` | URL-scoped browser observations for live login, browser-created company/contact/opportunity/workspace/commitment, refresh, logout, re-login, and record presence. | Browser label `CLIENTVERSE-PROOF-20260816222130` |
| E-08 | Live login screenshot | `current-live-login.webp` | Actual browser render of the public live login route. The browser automation record holds the URL metadata; the image alone does not contain address-bar chrome. | `/login` |
| E-09 | Authenticated dashboard screenshot | `current-live-dashboard-reauth.webp` | Post-logout/re-login browser render showing the controlled workspace in the dashboard client-health portfolio. | `/dashboard` |
| E-10 | Persisted company screenshot | `current-live-company-persisted.webp` | Post-relogin Directory shows the controlled company with one contact, one opportunity, and active workspace. | `/directory` |
| E-11 | Persisted contact screenshot | `current-live-contact-persisted.webp` | Post-relogin Contacts view shows the controlled contact attached to the controlled company. | `/directory` |
| E-12 | Opportunity screenshot | `current-live-opportunity.webp` | Browser-created controlled opportunity appeared in Lead before its later move to Won. | `/pipeline` |
| E-13 | Workspace screenshot | `current-live-workspace.webp` | Browser-created closed-won opportunity appeared in Client Workspaces. | `/workspaces` |
| E-14 | Commitment screenshot | `current-live-commitment.webp` | Browser-created commitment appeared in Client 360. The displayed date was `2/2/70131`; this artifact does not validate date-input correctness. | `/workspaces/ws_063e07c14748` |
| E-15 | Refresh persistence screenshot | `current-live-persistence-refresh.webp` | The browser refresh retained the controlled workspace and commitment prior to logout/re-login. | `/workspaces/ws_063e07c14748` |
| E-16 | Sanitized runtime log extract | `current-live-runtime-log-sanitized.txt` | Actual backend access-log proof trail for the API flow; critical-marker scan returned zero matches in the extracted proof window. | Process `21413` |
| E-17 | Browser console capture | `current-live-browser-console.log` | Browser console capture after proof flow recorded no output. | 2026-08-16T22:28:47Z |

## Deployment-Identity Result

The GitHub Deployments API returned an empty list. No hosting-platform metadata exposing a provider, project ID, deployment ID, timestamp, environment, or deployed commit SHA was available in this proof run. Therefore no deployed-SHA comparison can be made.

## Required Verdict Condition

The proof package records verified endpoint, health, authentication, persistence, authorization, and runtime evidence. It does **not** contain a hosting-platform-reported deployed SHA matching `f78da2081c6db8b21ad8978cf3a7fcd93cdc15c2`. Under the requested gate, deployment identity is therefore **UNVERIFIED**.
