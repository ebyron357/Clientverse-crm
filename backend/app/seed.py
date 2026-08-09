"""Idempotent startup seed (admin, demo data, registries, team, indexes)."""
import os
import secrets
from datetime import datetime, timezone, timedelta

from app.shared import db, new_id, now_iso, hash_password, verify_password, record_event, logger

async def seed():
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    admin_pw = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        tenant_id = new_id("ten")
        await db.tenants.insert_one({"tenant_id": tenant_id, "name": "ClientVerse HQ", "created_at": now_iso()})
        uid = new_id("user")
        await db.users.insert_one({"user_id": uid, "email": admin_email, "name": "TV Pro", "role": "admin",
                                   "tenant_id": tenant_id, "password_hash": hash_password(admin_pw),
                                   "picture": None, "created_at": now_iso(), "auth": "password"})
        await seed_demo(tenant_id, admin_email)
        logger.info("Seeded admin + demo data")
    else:
        if existing.get("password_hash") and not verify_password(admin_pw, existing["password_hash"]):
            await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_pw)}})
    # registries seed (idempotent by name)
    await seed_registries()
    await seed_team()
    await db.users.create_index("email", unique=True)
    await db.memberships.create_index([("tenant_id", 1), ("user_id", 1)])
    await db.invitations.create_index("token_hash")

async def seed_team():
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    au = await db.users.find_one({"email": admin_email}, {"_id": 0})
    if not au:
        return
    t = au["tenant_id"]
    if not await db.memberships.find_one({"tenant_id": t, "user_id": au["user_id"]}):
        await db.memberships.insert_one({"id": new_id("mem"), "tenant_id": t, "user_id": au["user_id"], "email": admin_email,
            "role": "admin", "status": "active", "invited_by": None, "invited_at": None,
            "accepted_at": now_iso(), "disabled_at": None, "created_at": now_iso()})
    mem_email = "demo.member@clientverse.io"
    if not await db.users.find_one({"email": mem_email}):
        muid = new_id("user")
        await db.users.insert_one({"user_id": muid, "email": mem_email, "name": "Demo Member", "role": "member",
            "tenant_id": t, "password_hash": hash_password("Member2026!"), "picture": None, "created_at": now_iso(), "auth": "password"})
        await db.memberships.insert_one({"id": new_id("mem"), "tenant_id": t, "user_id": muid, "email": mem_email,
            "role": "member", "status": "active", "invited_by": admin_email, "invited_at": now_iso(),
            "accepted_at": now_iso(), "disabled_at": None, "created_at": now_iso()})

async def seed_demo(tenant_id, actor):
    co1 = {"id": new_id("co"), "tenant_id": tenant_id, "name": "Northwind Analytics", "industry": "Data & AI", "website": "northwind.example", "tier": "enterprise", "created_at": now_iso()}
    co2 = {"id": new_id("co"), "tenant_id": tenant_id, "name": "Harbor Logistics", "industry": "Supply Chain", "website": "harbor.example", "tier": "growth", "created_at": now_iso()}
    await db.companies.insert_many([co1, co2])
    await db.contacts.insert_many([
        {"id": new_id("ct"), "tenant_id": tenant_id, "name": "Dana Reyes", "email": "dana@northwind.example", "role": "VP Product", "company_id": co1["id"], "influence": "high", "sentiment": "positive", "created_at": now_iso()},
        {"id": new_id("ct"), "tenant_id": tenant_id, "name": "Marcus Lee", "email": "marcus@harbor.example", "role": "COO", "company_id": co2["id"], "influence": "high", "sentiment": "neutral", "created_at": now_iso()},
    ])
    await db.opportunities.insert_many([
        {"id": new_id("opp"), "tenant_id": tenant_id, "name": "Northwind Platform Expansion", "company_id": co1["id"], "value": 120000, "stage": "negotiation", "owner": actor, "created_at": now_iso()},
        {"id": new_id("opp"), "tenant_id": tenant_id, "name": "Harbor Onboarding Package", "company_id": co2["id"], "value": 45000, "stage": "proposal", "owner": actor, "created_at": now_iso()},
        {"id": new_id("opp"), "tenant_id": tenant_id, "name": "Acme Pilot", "company_id": None, "value": 20000, "stage": "qualified", "owner": actor, "created_at": now_iso()},
    ])
    ws = {"id": new_id("ws"), "tenant_id": tenant_id, "name": "Northwind Delivery", "company_id": co1["id"], "opportunity_id": None, "stage": "serve", "created_at": now_iso()}
    await db.workspaces.insert_one(ws)
    wid = ws["id"]
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    await db.tasks.insert_many([
        {"id": new_id("task"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Kickoff workshop", "assignee": actor, "due_date": past, "status": "done", "created_at": now_iso()},
        {"id": new_id("task"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Data integration setup", "assignee": actor, "due_date": past, "status": "in_progress", "created_at": now_iso()},
        {"id": new_id("task"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Dashboard review", "assignee": actor, "due_date": future, "status": "todo", "created_at": now_iso()},
    ])
    await db.deliverables.insert_many([
        {"id": new_id("dlv"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Onboarding Plan", "description": "30-day onboarding roadmap", "status": "approved", "created_at": now_iso()},
        {"id": new_id("dlv"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Analytics Dashboard v1", "description": "First analytics build", "status": "in_review", "created_at": now_iso()},
    ])
    await db.client_requests.insert_many([
        {"id": new_id("req"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Add revenue forecast widget", "priority": "high", "status": "open", "created_at": now_iso()},
    ])
    cmt1 = {"id": new_id("cmt"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Deliver dashboard by month end", "owner": actor, "due_date": future, "status": "at_risk", "created_at": now_iso()}
    cmt2 = {"id": new_id("cmt"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Weekly status call", "owner": actor, "due_date": future, "status": "open", "created_at": now_iso()}
    await db.commitments.insert_many([cmt1, cmt2])
    out1 = {"id": new_id("out"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Launch analytics platform", "target": "Production go-live", "target_value": 100, "current_value": 65, "unit": "% complete", "status": "on_track", "linked_commitment_ids": [cmt1["id"]], "created_at": now_iso()}
    out2 = {"id": new_id("out"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Cut reporting time", "target": "Reduce vs baseline", "target_value": 50, "current_value": 28, "unit": "% reduction", "status": "at_risk", "linked_commitment_ids": [cmt1["id"], cmt2["id"]], "created_at": now_iso()}
    await db.outcomes.insert_many([out1, out2])
    for i, pct in enumerate([30, 45, 55, 65]):
        await db.outcome_snapshots.insert_one({"id": new_id("os"), "tenant_id": tenant_id, "outcome_id": out1["id"], "pct": pct, "at": (datetime.now(timezone.utc) - timedelta(days=(4 - i))).isoformat()})
    for i, pct in enumerate([20, 36, 44, 56]):
        await db.outcome_snapshots.insert_one({"id": new_id("os"), "tenant_id": tenant_id, "outcome_id": out2["id"], "pct": pct, "at": (datetime.now(timezone.utc) - timedelta(days=(4 - i))).isoformat()})
    for i, sc in enumerate([58, 64, 72, 69, 78]):
        ts = (datetime.now(timezone.utc) - timedelta(days=(5 - i))).isoformat()
        band = "healthy" if sc >= 75 else ("at_risk" if sc >= 50 else "critical")
        await db.health_snapshots.insert_one({"id": new_id("hs"), "tenant_id": tenant_id, "workspace_id": wid, "score": sc, "band": band, "at": ts})
    await db.approvals.insert_one({"id": new_id("apr"), "tenant_id": tenant_id, "workspace_id": wid, "title": "Send Q1 renewal proposal to client", "kind": "external_effect", "status": "requested", "created_at": now_iso()})
    await record_event("client_workspace.created", "workspace", wid, tenant_id, actor, workspace_id=wid, payload={"name": ws["name"]})
    await record_event("commitment.at_risk", "commitment", "seed", tenant_id, actor, workspace_id=wid, payload={"title": "Deliver dashboard by month end"})

async def seed_registries():
    tenant = await db.tenants.find_one({"name": "ClientVerse HQ"})
    if not tenant:
        return
    t = tenant["tenant_id"]
    if await db.integrations.find_one({"tenant_id": t}):
        return
    await db.integrations.insert_many([
        {"id": new_id("intg"), "tenant_id": t, "name": "Gmail", "provider": "Google", "category": "communications", "status": "AVAILABLE", "auth_method": "OAuth", "scopes": ["mail.send", "mail.read"], "description": "Send and read client emails.", "created_at": now_iso()},
        {"id": new_id("intg"), "tenant_id": t, "name": "Stripe", "provider": "Stripe", "category": "billing", "status": "BETA", "auth_method": "API key", "scopes": ["invoices.write"], "description": "Invoicing and payments.", "created_at": now_iso()},
        {"id": new_id("intg"), "tenant_id": t, "name": "Google Calendar", "provider": "Google", "category": "scheduling", "status": "PLANNED", "auth_method": "OAuth", "scopes": ["calendar.events"], "description": "Schedule client meetings.", "created_at": now_iso()},
    ])
    await db.mcp_servers.insert_many([
        {"id": new_id("mcp"), "tenant_id": t, "name": "ClientVerse Read Tools", "version": "1.0.0", "level": 1, "status": "AVAILABLE", "tools": ["search_contacts", "get_client_health", "list_open_commitments"], "description": "Read-only MCP tools.", "created_at": now_iso()},
        {"id": new_id("mcp"), "tenant_id": t, "name": "ClientVerse Write Tools", "version": "0.4.0", "level": 2, "status": "ALPHA", "tools": ["create_task", "add_note", "create_approval_request"], "description": "Reversible internal writes.", "created_at": now_iso()},
        {"id": new_id("mcp"), "tenant_id": t, "name": "ClientVerse External Effects", "version": "0.1.0", "level": 3, "status": "PLANNED", "tools": ["send_message", "schedule_meeting"], "description": "External effects, approval-gated.", "created_at": now_iso()},
    ])
    await db.plugins.insert_many([
        {"id": new_id("plg"), "tenant_id": t, "name": "Health Score Analyzer", "version": "1.2.0", "publisher": "ClientVerse", "type": "analytics provider", "status": "AVAILABLE", "permissions": ["read:workspace"], "description": "Explainable client health scoring.", "created_at": now_iso()},
        {"id": new_id("plg"), "tenant_id": t, "name": "Slack Notifier", "version": "0.9.0", "publisher": "Community", "type": "communications provider", "status": "BETA", "permissions": ["events:consume"], "description": "Post workspace events to Slack.", "created_at": now_iso()},
    ])
    await db.webhooks.insert_many([
        {"id": new_id("wh"), "tenant_id": t, "name": "Ops Alerts (external)", "url": "https://hooks.invalid.example/ops", "events": ["commitment.at_risk", "approval.requested"], "status": "AVAILABLE", "signed": True, "enabled": True, "secret": "whsec_ops_" + secrets.token_hex(8), "description": "External endpoint — unreachable in demo, shows retry + dead-letter.", "created_at": now_iso()},
        {"id": new_id("wh"), "tenant_id": t, "name": "Local Test Sink", "url": "http://localhost:8001/api/webhooks/sink", "events": ["commitment.at_risk", "commitment.breached", "approval.requested", "task.created", "mcp.tool_invoked", "webhook.test", "commitment.fulfilled", "deliverable.approved"], "status": "AVAILABLE", "signed": True, "enabled": True, "secret": "whsec_sink_" + secrets.token_hex(8), "description": "Built-in sink returning 200 — shows successful signed delivery.", "created_at": now_iso()},
    ])
