# Contributing to ClientVerse

Thanks for your interest in improving ClientVerse. This guide covers the local
setup, expectations for changes, and how work gets reviewed.

## Local setup

```bash
# Backend
cd backend && pip install -r requirements.txt
cp .env.example .env      # fill in real values (never commit .env)

# Frontend (use yarn, not npm)
cd frontend && yarn install
cp .env.example .env
```

Requirements: Python 3.11+, Node 18+, Yarn 1.x, MongoDB 5+.

Run the API with `uvicorn server:app --reload --port 8001` from `backend/`, and
the SPA with `yarn start` from `frontend/`.

## Before opening a pull request

```bash
# Frontend must build warning-free (CI treats warnings as errors)
cd frontend && CI=true yarn build

# Backend suite drives the HTTP API — a backend + MongoDB must be running
cd backend && python -m pytest tests/ -q
```

Tests read `REACT_APP_BACKEND_URL`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`,
`DEMO_MEMBER_EMAIL`, `DEMO_MEMBER_PASSWORD`, `MONGO_URL` and `DB_NAME` from the
environment. Never hard-code credentials in test files.

## Change guidelines

- Keep changes focused; unrelated refactors belong in separate pull requests.
- Preserve multi-tenant scoping and server-side authorization on every new
  route — UI hiding is never authorization.
- Any state change that matters to operators should emit a domain event so it
  appears on the Automation & Audit feed.
- New provider integrations go behind the existing adapter contract
  (`SYNC_FUNCS`, `normalize_*`) instead of touching CRM core.
- Never commit secrets, `.env` files, build output, or dependency directories.

## Commit and PR conventions

- Use short, imperative commit subjects, optionally prefixed with a scope
  (`fix(webhooks): ...`, `docs: ...`).
- Describe *what* changed and *why* in the PR body, and list the commands you
  ran to validate it.
- Link related issues.

## Reporting security issues

Do not open a public issue for vulnerabilities — see [SECURITY.md](SECURITY.md).
