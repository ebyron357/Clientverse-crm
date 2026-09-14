# Remaining Work

Status reconciled against `main@5c18061` plus integrated closeout work through PR-equivalent heads #21/#22/#24/#25/#23 on 2026-09-14.

## Engineering status

No incomplete repository task remains that can be truthfully closed without access to an owner-controlled provider or production account. The application, Railway deployment configuration, tenant-isolation controls, CI workflow, deploy SHA health parity, Command Center UX improvements, pipeline/workspace UX refinements, and credential-free provider contract tests are implemented. `todo.md` remains the canonical historical task ledger.

Do not mark the external-provider lifecycle as certified based only on mocks, contract tests, or environment-variable presence. Certification requires a real test account and sanitized evidence from the live lifecycle.

## Owner-controlled closeout

| Item | Exact owner input required | Agent follow-through after access is supplied |
|---|---|---|
| Google/Gmail/Calendar | Approved Google OAuth web client, registered production callback, and authorization to use a least-privilege test account | Run connect, consent, Gmail sync, Calendar sync, refresh, disconnect, and reconnect lifecycle checks; record sanitized evidence |
| Stripe | Approved restricted Stripe test key and test webhook signing secret/account authorization | Run customer/invoice/subscription sync plus PaymentIntent/webhook lifecycle checks; record sanitized evidence |
| Scheduler | An owner-approved external scheduler connected to the production service | Configure the three authenticated cron calls at the cadences in `RAILWAY_RUNBOOK.md`, then verify delivery without exposing the bearer secret |
| Custom domain | The chosen domain and authorization to update DNS | Bind the Railway domain, verify TLS, update public origins, and register the final Google callback |
| Admin credential | Owner chooses/sets the replacement production admin password | Update `ADMIN_PASSWORD`, redeploy, verify login, and revoke the bootstrap session |
| Secret cleanup | Owner access to the production variable settings and Stripe dashboard | Delete the misspelled `Mongo_url` variable and rotate the legacy Stripe webhook secret |

None of these actions should be simulated, and secret values must never be committed or copied into an issue, pull request, log, or evidence artifact.

## Repository validation

CI-equivalent validation requires:

```bash
cd frontend && yarn install --frozen-lockfile
cd frontend && yarn lint --max-warnings=0
cd frontend && CI=true REACT_APP_BACKEND_URL=http://localhost:8001 yarn build

# With MongoDB running and the ephemeral environment from .github/workflows/ci.yml:
cd backend && python -m pytest tests/ -q
```

The GitHub issue closeout report should use exactly three sections: `COMPLETED`, `BLOCKED`, and `EXACT OWNER INPUT REQUIRED`.
