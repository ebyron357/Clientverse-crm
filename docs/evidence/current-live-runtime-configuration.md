# Current Live Runtime Configuration Presence

**Inspection UTC:** 2026-08-16T22:19:00Z  
**Inspected process:** externally reachable backend process serving port 8001.  
**Method:** environment variable names only; no values were read or recorded.

| Name | State |
|---|---|
| `MONGO_URL` | PRESENT |
| `DB_NAME` | PRESENT |
| `JWT_SECRET` | PRESENT |
| `FRONTEND_URL` | PRESENT |
| `CORS_ORIGINS` | PRESENT |
| `PUBLIC_BACKEND_URL` | MISSING |
| `INTEGRATION_ENC_KEY` | MISSING |
| `GOOGLE_CLIENT_ID` | MISSING |
| `GOOGLE_CLIENT_SECRET` | MISSING |
| `GOOGLE_REDIRECT_URI` | MISSING |
| `STRIPE_API_KEY` | MISSING |

`GOOGLE_REDIRECT_URI` is not marked as derived because `PUBLIC_BACKEND_URL` is missing in the inspected running process.
