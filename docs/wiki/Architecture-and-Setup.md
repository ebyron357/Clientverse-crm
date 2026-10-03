# Architecture and Setup

## Local setup
Backend:
```bash
cd backend
pip install -r requirements.txt
```

Frontend:
```bash
cd frontend
yarn install
```

Use Yarn for the frontend as documented by the repository.

## Core environment categories
Do not store values here.

Backend categories include:
- MongoDB connection and database name
- CORS and public frontend/backend URLs
- JWT secret
- seeded admin credentials
- webhook cron secret
- optional AI provider keys
- integration encryption key
- Google OAuth credentials
- Stripe key

Frontend:
- public backend base URL

## Security architecture
- tenant-scoped records
- server-side role enforcement
- encrypted provider credentials
- approval-gated MCP writes
- audit events for sensitive actions
- webhook signing and replay controls
