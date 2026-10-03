# Deployment and Operations

## Operational areas
- backend health endpoint
- frontend production build
- MongoDB availability
- scheduled cron endpoints
- Google OAuth refresh health
- Stripe read-only sync
- webhook delivery / DLQ
- MCP approvals and undo
- team and role administration

## Common incident checks
1. Confirm backend health and MongoDB reachability.
2. Confirm production environment values exist without printing them.
3. Confirm scheduled jobs are actually reaching production.
4. Distinguish authentication failure, authorization failure, provider failure, and certification/configuration gates.
5. For Google, confirm the live grant can refresh.
6. For outbound email, confirm both scope/grant and product certification requirements.
7. Preserve evidence in the relevant closeout / operations record.
