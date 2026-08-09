# Contributor & Agent Guide — ClientVerse

Read this before adding backend code. The backend was deliberately refactored
out of a single oversized `server.py` (which repeatedly suffered tail
corruption). **Do not grow `server.py` again.**

## Backend structure (see `docs/BACKEND_ARCHITECTURE.md` for detail)

```
backend/
├── server.py                 # THIN bootstrap ONLY (app, router registration, middleware, startup/shutdown)
├── scripts/
│   └── validate_app_structure.py   # structural guard — run before you commit
└── app/
    ├── shared.py             # config, db, id/time/auth helpers, record_event, authz, webhook+health engine
    ├── seed.py               # startup seed
    ├── services/             # domain engines, NO route handlers (commitments, mcp, integrations, notifications, alerts)
    └── routers/              # FastAPI APIRouter modules, one per domain (all prefixed /api)
```

## Where to add things

| You are adding… | Put it in… |
|---|---|
| A new endpoint in an existing domain | the matching `app/routers/<domain>.py` (route + its Pydantic model) |
| A brand-new domain | new `app/routers/<domain>.py` with `router = APIRouter(prefix="/api")`, then add it to the `ROUTERS` list in `server.py` |
| Reusable business logic / engine | `app/services/<domain>.py` |
| A helper used across many modules | `app/shared.py` |
| Scheduled work | a handler in `app/routers/cron.py` + an entry in `.emergent/crons.yml` |

## Hard rules
- **Never** put route handlers, Pydantic models, or business logic in `server.py`.
- **Never** import a router from a service or a shared helper (would create a cycle).
  Dependency direction is strictly `routers → services → shared`.
- Register every router exactly once, only in `server.py`'s `ROUTERS` list.
- Preserve existing endpoint paths, methods, status codes, auth, tenant isolation
  and role/permission behavior. Do not rename public APIs unless fixing a verified defect.
- Get `db`, `record_event`, `get_current_user`, `require_role`, `require_permission`,
  `new_id`, `now_iso` etc. from `app.shared` — do not re-implement them.

## Before committing backend changes
```
python backend/scripts/validate_app_structure.py          # must exit 0
cd backend && python -m pytest -o addopts="" -q            # full suite green
cd frontend && yarn build                                  # production build succeeds
```
`validate_app_structure.py` fails on syntax corruption, circular imports,
duplicate routes, duplicate router inclusion, missing routers, or business logic
leaking back into `server.py`.

## Git
Work on the current feature branch only. Do not commit to or merge into `main`;
use the "Save to GitHub" feature for pushes.
