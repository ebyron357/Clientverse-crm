"""ClientVerse API — application bootstrap. Business logic lives in app/*.
Creates the app, registers routers, wires startup/shutdown. Nothing else."""
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

from app.shared import FRONTEND_URL, db, mclient
from app.seed import seed
from app.routers import (auth, team, crm, delivery, dashboard, ai, mcp, webhooks,
                         outcomes, integrations, insights, notifications, cron)

app = FastAPI(title="ClientVerse API", version="v1")

ROUTERS = [auth, team, crm, delivery, dashboard, ai, mcp, webhooks,
           outcomes, integrations, insights, notifications, cron]
for _r in ROUTERS:
    app.include_router(_r.router)

root_router = APIRouter(prefix="/api")


@root_router.get("/")
async def root():
    return {"service": "ClientVerse", "version": "v1", "status": "ok"}


app.include_router(root_router)


@app.on_event("startup")
async def on_startup():
    await seed()
    try:
        await db.domain_events.create_index([("tenant_id", 1), ("workspace_id", 1), ("timestamp", -1)])
        await db.alerts.create_index([("tenant_id", 1), ("status", 1)])
        await db.alerts.create_index([("tenant_id", 1), ("type", 1), ("source_ref", 1)])
        await db.crm_communications.create_index([("tenant_id", 1), ("workspace_id", 1)])
        await db.crm_meetings.create_index([("tenant_id", 1), ("workspace_id", 1)])
        await db.crm_billing.create_index([("tenant_id", 1), ("workspace_id", 1)])
    except Exception:
        pass


@app.on_event("shutdown")
async def on_shutdown():
    mclient.close()


app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
