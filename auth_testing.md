# Auth Testing Playbook (ClientVerse)

Admin: tvpro357@gmail.com / ClientVerse2026! (role admin, tenant ClientVerse HQ, seeded demo data)

Auth uses httpOnly cookie `access_token` (JWT, 7d) with Authorization Bearer fallback.
Emergent Google OAuth also supported: POST /api/auth/google/session {session_id} -> stores session_token.

## API test
curl -c cookies.txt -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" -d '{"email":"tvpro357@gmail.com","password":"ClientVerse2026!"}'
curl -b cookies.txt http://localhost:8001/api/auth/me
curl -b cookies.txt http://localhost:8001/api/dashboard

## Browser (Google session) test
Set cookie access_token = a valid user_sessions.session_token, or use password login via UI.
