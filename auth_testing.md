# Auth Testing Playbook (ClientVerse)

Use credentials from your local `backend/.env` (never commit real secrets).

Default local seed (from `backend/.env.example`):
- Admin: `$ADMIN_EMAIL` / `$ADMIN_PASSWORD` (role `admin`, tenant ClientVerse HQ)
- Demo member: `$DEMO_MEMBER_EMAIL` / `$DEMO_MEMBER_PASSWORD` (role `member`)

Auth uses httpOnly cookie `access_token` (JWT, 7d) with Authorization Bearer fallback.
Emergent Google OAuth also supported: `POST /api/auth/google/session` `{session_id}` → stores `session_token`.

## API test

```bash
# Set these from your local backend/.env — never hardcode real credentials here.
export ADMIN_EMAIL="$ADMIN_EMAIL"
export ADMIN_PASSWORD="$ADMIN_PASSWORD"
curl -c cookies.txt -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}"
curl -b cookies.txt http://localhost:8001/api/auth/me
curl -b cookies.txt http://localhost:8001/api/dashboard
curl http://localhost:8001/api/health
```

## Browser (Google session) test

Set cookie `access_token` = a valid `user_sessions.session_token`, or use password login via UI.
