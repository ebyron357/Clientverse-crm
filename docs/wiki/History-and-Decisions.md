# History and Decisions

## Governing product decisions
- ClientVerse is multi-tenant.
- Authorization is enforced server-side; UI hiding is not authorization.
- MCP mutations are governed and reversible where designed.
- Webhooks are signed and delivery attempts are auditable.
- External integrations normalize provider data into the CRM rather than letting provider-specific logic spread across the core.
- Production demo data must not be silently seeded.
- Scheduler / automation status must be based on live evidence.

## Retroactive history rule
When adding a historical milestone, record:
- date;
- PR / commit;
- what actually changed;
- whether it merged;
- whether it deployed;
- verification evidence;
- remaining external or owner gates.
