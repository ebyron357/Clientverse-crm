# ClientVerse.io — AI-native Client Operations Platform

ClientVerse manages the complete client lifecycle — **WIN → ONBOARD → SERVE → RETAIN → EXPAND** — with a governed, integration-first core: pipeline, client workspaces, commitment ledger, deliverables/requests/approvals, explainable client health, evidence-backed AI, a governed MCP server, live webhooks, and a per-client Outcome Graph.

**Stack:** FastAPI + MongoDB (backend) · React + Tailwind + shadcn/ui (frontend). Modular monolith.

---

## 1. Local installation

```bash
# Backend deps
cd backend && pip install -r requirements.txt

# Frontend deps (use yarn, NOT npm)
cd frontend && yarn install
```

Requirements: Python 3.11+, Node 18+, Yarn, MongoDB 5+.

## 2. Environment setup

Copy the example files and fill in real values:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

**Backend (`backend/.env`)**

| Variable | Purpose |
|---|---|
| `MONGO_URL` | MongoDB connection string |
| `DB_NAME` | Database name |
| `CORS_ORIGINS` | Allowed browser origin (the frontend URL) |
| `FRONTEND_URL` | Public frontend URL (used for CORS + OAuth redirect) |
| `JWT_SECRET` | Long random hex string for signing JWTs (`openssl rand -hex 32`) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Seeded admin/owner account |
| `EMERGENT_LLM_KEY` | Emergent Universal LLM key for evidence-backed AI |

**Frontend (`frontend/.env`)**

| Variable | Purpose |
|---|---|
| `REACT_APP_BACKEND_URL` | Base URL of the backend (all API calls are prefixed with `/api`) |

> Never commit real `.env` files — they are gitignored. Only `.env.example` (placeholders) is tracked.

## 3. Database requirements

- MongoDB reachable at `MONGO_URL`. Collections are created on demand.
- On first startup the backend **seeds** an admin user (`ADMIN_EMAIL`/`ADMIN_PASSWORD`), a demo tenant ("ClientVerse HQ") with sample companies, contacts, opportunities, a client workspace, commitments, deliverables, approvals, outcomes with target snapshots, and governed registries (integrations / MCP servers / plugins / webhooks). Seeding is idempotent (skipped if the admin already exists).

## 4. Backend startup

Managed by supervisor (binds `0.0.0.0:8001`):

```bash
sudo supervisorctl restart backend
# logs: tail -n 100 /var/log/supervisor/backend.*.log
```

## 5. Frontend startup

```bash
sudo supervisorctl restart frontend      # serves on :3000
# or for local dev: cd frontend && yarn start
```

## 6. Test commands

```bash
# Backend API/integration test suite (hits the running backend)
cd backend && python -m pytest tests/ -q
# Latest result: 50 passed, 1 skipped (by design)
```

## 7. Production build

```bash
cd frontend && yarn build     # outputs frontend/build/ (static, deployable)
```

## 8. Authentication configuration

Two methods, both issue an httpOnly `access_token` cookie (7-day) with an `Authorization: Bearer` fallback; `get_current_user` accepts either:

- **JWT email/password** — `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`. Passwords hashed with bcrypt. Multi-tenant; roles: `admin` / `member`.
- **Emergent-managed Google login** — `POST /api/auth/google/session` exchanges an Emergent `session_id` for a session token.

Every tenant-owned record is tenant-scoped; server-side authorization is enforced on all routes (UI hiding is not authorization).

## 9. Webhook signing and replay behavior

- Payloads are signed with **HMAC-SHA256**. Header `X-ClientVerse-Signature: sha256=<hex>` plus `X-ClientVerse-Delivery`, `X-ClientVerse-Event`, `X-ClientVerse-Timestamp`.
- Delivery auto-fires on matching domain events. **Subscriptions support wildcards** (`commitment.*`, `approval.*`, `*`, or exact types) via `event_matches`.
- **Retries**: up to 3 attempts with backoff; final failure moves the delivery to **dead-letter (DLQ)**.
- **Delivery log** records each attempt; **manual replay** re-attempts a delivery. Endpoints can be enabled/disabled and secrets rotated. A **test event** and a built-in `POST /api/webhooks/sink` (returns 200) are provided for verification. A "Verify" dialog exposes the signing secret and a copyable Node.js verification snippet. A "match preview" shows how many of the last 100 events a pattern would match.
- The seeded "Ops Alerts (external)" endpoint points to an unreachable URL **by design** to demonstrate retry + DLQ.

## 10. MCP approval and undo behavior

ClientVerse acts as a **governed MCP server** with tiered tools:

- **Level 1 (read-only)** execute live through the policy wrapper (tenant scope, allowlist, kill switch, rate limit, timeout, idempotency, execution history).
- **Level 2 (reversible writes)** — e.g. `create_task`, `add_note` — are **gated behind an approval request**. Invoking returns `pending_approval` and raises an approval in the client workspace; approving it executes the write, rejecting cancels it.
- **Level 3+** remain non-executable by design.
- **Undo**: an admin can reverse a successful Level-2 write from the MCP Console or the Audit trail. Undo **requires a non-empty reason** (422 otherwise), is **admin-only**, and is limited to a **per-workspace undo window** (default 60 min, configurable via `PATCH /api/workspaces/{id}/undo-window`, clamped 1–1440). Reversal restores prior state and records an `mcp.tool_undone` audit event.

Every significant state change emits a normalized domain event (visible on the Automation & Audit feed).

## 11. Known non-blocking warnings

- **ESLint (`react-hooks/exhaustive-deps`)** in `OutcomeGraph.jsx` and `Mcp.jsx` — intentional stable `load` dependency; build compiles successfully with warnings.
- **Recharts** first-paint console warning `width(-1)/height(-1)` from a sparkline `ResponsiveContainer` — cosmetic only; the sparkline renders correctly.

---

_Release candidate: ClientVerse connected CRM core. Validated: backend 50 passed / 1 skipped, frontend production build succeeds._
