# ClientVerse Hosting Selection

## Recommendation

Deploy the existing ClientVerse single-container FastAPI and React application as a **Render Docker Web Service**, with **MongoDB Atlas** as the production database. This is the most compatible managed path for the current architecture because the repository already provides a Dockerfile, serves the built React application and `/api` from one origin, and contains authenticated scheduler endpoints that can be invoked by a platform cron service.

## Comparison

| Option | Compatibility with current CRM | Operational fit | Decision |
|---|---|---|---|
| **Render Web Service + MongoDB Atlas** | Direct Docker deployment, FastAPI support, environment secrets, HTTPS, and scheduled jobs. | Clear separation between the API and managed database; Atlas supports a managed MongoDB lifecycle. | **Recommended** |
| Railway + external MongoDB | Supports GitHub and Docker FastAPI deployment plus scheduled services. | Viable alternative, but its scheduled-service process must finish and exit cleanly; less aligned with the prepared Render deployment documentation. | Suitable fallback |
| Fly.io + external MongoDB | Supports containerized FastAPI deployment. | More infrastructure configuration and operational ownership than needed for the current first production release. | Not preferred for initial launch |

## Required Production Components

| Component | Purpose | ClientVerse configuration |
|---|---|---|
| Render Docker Web Service | Serves the React SPA and FastAPI API from a single HTTPS origin. | Deploy the `Dockerfile`; set the health check to `/api/health`. |
| MongoDB Atlas cluster | Stores tenant-scoped CRM data. | Set `MONGO_URL` to a least-privilege application connection string; restrict network access to the Render service. |
| Render Cron Job | Calls the authenticated commitment-risk endpoint or runs a short-lived worker. | Use a separate `WEBHOOK_CRON_SECRET`; schedule in UTC; ensure any task exits when complete. |
| Render environment group | Keeps production secrets out of Git and shared only by the intended services. | Store JWT, encryption, provider, database, and scheduler values only in the host secret manager. |

## Security Requirements

Production must use explicit HTTPS values for `FRONTEND_URL` and `CORS_ORIGINS`, a strong `JWT_SECRET`, a valid `INTEGRATION_ENC_KEY`, and a separate `WEBHOOK_CRON_SECRET`. ClientVerse refuses production startup if those mandatory browser-origin, scheduler, or encryption safeguards are missing. Google and Stripe keys remain absent until approved test credentials are configured and provider lifecycle certification is complete.

## Sources

Render documents FastAPI web-service deployment, platform cron jobs, environment-variable secret handling, and Atlas connectivity. Railway and Fly.io are compatible alternatives that both support FastAPI and Docker deployments, but do not offer a stronger first-launch fit for this repository.

1. [Render FastAPI deployment](https://render.com/docs/deploy-fastapi)
2. [Render Cron Jobs](https://render.com/docs/cronjobs)
3. [Render MongoDB Atlas connectivity](https://render.com/docs/connect-to-mongodb-atlas)
4. [Render environment variables and secrets](https://render.com/docs/configure-environment-variables)
5. [Railway FastAPI deployment](https://docs.railway.com/guides/fastapi)
6. [Railway Cron Jobs](https://docs.railway.com/cron-jobs)
7. [Fly.io FastAPI deployment](https://fly.io/docs/python/frameworks/fastapi/)
