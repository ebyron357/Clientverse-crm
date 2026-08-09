# ClientVerse Backend Architecture

The backend was refactored from a single 2,600-line `server.py` monolith into a
focused modular package. Externally observable behavior (routes, methods,
request/response shapes, auth, tenant isolation, permissions, audit events,
cron, webhooks, MCP, integrations) is unchanged.

## Layout

```
backend/
├── server.py                 # thin bootstrap ONLY (app, routers, middleware, startup/shutdown)
└── app/
    ├── shared.py             # infrastructure base layer (see below)
    ├── seed.py               # idempotent startup seed (admin, demo, registries, team, indexes)
    ├── services/             # domain engines (no route handlers)
    │   ├── commitments.py     # evaluate_commitment_risk (SLA sweep)
    │   ├── mcp.py             # tool catalog + implementations + execute_pending_mcp
    │   ├── integrations.py    # providers, Fernet creds, normalizers, adapters, sync engine
    │   ├── notifications.py   # send_email, prefs, notify_alert, escalation, digest
    │   └── alerts.py          # deduplicated alert evaluation engine
    └── routers/              # FastAPI APIRouter modules (all prefixed /api)
        ├── auth.py            # /api/auth/*
        ├── team.py            # /api/team/*
        ├── crm.py             # companies, contacts, opportunities, workspaces
        ├── delivery.py        # tasks, deliverables, client-requests, approvals, commitments
        ├── dashboard.py       # registries, events feed, dashboard rollup
        ├── ai.py              # /api/ai/generate
        ├── mcp.py             # /api/mcp/*, undo, undo-window
        ├── webhooks.py        # webhook CRUD, deliveries, replay, sink, match-preview
        ├── outcomes.py        # outcome graph
        ├── integrations.py    # connections, OAuth, sync, activity
        ├── insights.py        # timeline, alerts, connection health, health-signals
        ├── notifications.py   # notification center, preferences, digest
        └── cron.py            # /api/cron/* (commitment-risk, integration-sync, daily-digest)
```

## Entrypoint (`server.py`)
Creates the FastAPI `app`, includes every router once, registers the `/api/`
root route, wires `startup` (seed + index creation) and `shutdown` (close Mongo),
and adds CORS. It contains **no** business logic, route handlers, or models.

## Shared layer (`app/shared.py`)
The acyclic base every other module imports from. Holds: config/env, the Mongo
client + `db`, id/time/password/JWT/cookie helpers, `record_event` (domain event
emission + webhook fan-out + health recompute), auth dependency
`get_current_user` + `resolve_membership`, authorization (`ROLE_PERMISSIONS`,
`require_role`, `require_permission`), `gen_list`/`scope`, `compute_health` +
`record_health_snapshot`, the webhook delivery/signing engine, and insight
constants (`STALE_SYNC_HOURS`, `HEALTH_CRITICAL`, …) + `_age_hours`.

`record_event` calls the webhook dispatcher and health snapshotter — both live in
`shared`, so the base has **no upward dependency** on services.

## Dependency boundaries (no circular imports)
```
routers  ->  services  ->  shared
                 └─ alerts -> notifications   (one-way; notifications never imports alerts)
```
- `shared` imports nothing from `app/`.
- Every `services/*` module imports only from `shared`, except `alerts` which also
  imports `notify_alert` from `notifications` (a single one-way edge).
- `routers/*` import from `shared` and from the services they need.

## Where to add new features
- **New endpoint in an existing domain** → add the route + its Pydantic model to
  the matching `app/routers/<domain>.py`.
- **New domain** → create `app/routers/<domain>.py` with `router = APIRouter(prefix="/api")`
  and register it in `server.py`'s `ROUTERS` list. Put reusable logic in a new
  `app/services/<domain>.py`.
- **Cross-cutting helper used by many modules** → add to `app/shared.py`.
- **Scheduled work** → add a handler to `app/routers/cron.py` and an entry in
  `.emergent/crons.yml`.
- Keep services free of `APIRouter`/route handlers; keep `server.py` a bootstrap.

## Reliability guards
`backend/tests/test_module_structure.py` fails if: any module stops parsing,
the app can't import (circular import), business logic/models creep back into
`server.py`, a route is registered twice, or duplicate `(method, path)` routes
appear.
