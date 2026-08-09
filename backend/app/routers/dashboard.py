"""Read routes: registries, domain events feed, dashboard rollup."""
from fastapi import APIRouter, HTTPException, Depends, Query

from app.shared import db, gen_list, compute_health, STAGES, get_current_user

router = APIRouter(prefix="/api")

REGISTRIES = {
    "integrations": "integrations",
    "mcp-servers": "mcp_servers",
    "plugins": "plugins",
    "webhooks": "webhooks",
}

@router.get("/registry/{kind}")
async def list_registry(kind: str, user=Depends(get_current_user)):
    coll = REGISTRIES.get(kind)
    if not coll:
        raise HTTPException(status_code=404, detail="Unknown registry")
    return await gen_list(coll, user)

# ----------------------------- Domain events / Audit -----------------------------

@router.get("/events")
async def list_events(limit: int = Query(200), user=Depends(get_current_user)):
    docs = await db.domain_events.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return docs

# ----------------------------- Dashboard summary -----------------------------

@router.get("/dashboard")
async def dashboard(user=Depends(get_current_user)):
    t = user["tenant_id"]
    opps = await db.opportunities.find({"tenant_id": t}, {"_id": 0}).to_list(2000)
    workspaces = await db.workspaces.find({"tenant_id": t}, {"_id": 0}).to_list(2000)
    commitments = await db.commitments.find({"tenant_id": t}, {"_id": 0}).to_list(2000)
    pipeline_value = sum(o.get("value", 0) for o in opps if o.get("stage") not in ("closed_won", "closed_lost"))
    won_value = sum(o.get("value", 0) for o in opps if o.get("stage") == "closed_won")
    funnel = {s: len([o for o in opps if o.get("stage") == s]) for s in STAGES}
    # health per workspace
    portfolio = []
    for ws in workspaces:
        scoped = {"tenant_id": t, "workspace_id": ws["id"]}
        cm = [c for c in commitments if c.get("workspace_id") == ws["id"]]
        tasks = await db.tasks.find(scoped, {"_id": 0}).to_list(500)
        dl = await db.deliverables.find(scoped, {"_id": 0}).to_list(500)
        rq = await db.client_requests.find(scoped, {"_id": 0}).to_list(500)
        h = compute_health(cm, tasks, dl, rq)
        portfolio.append({"id": ws["id"], "name": ws["name"], "stage": ws.get("stage"), "health": h})
    at_risk = len([c for c in commitments if c.get("status") in ("at_risk", "breached")])
    # Outcome (goal) rollup across portfolio
    outcomes = await db.outcomes.find({"tenant_id": t}, {"_id": 0}).to_list(2000)
    osnaps = await db.outcome_snapshots.find({"tenant_id": t}, {"_id": 0}).sort("at", 1).to_list(5000)
    trend_map = {}
    for s in osnaps:
        trend_map.setdefault(s["outcome_id"], []).append(s["pct"])
    def gpct(g):
        return min(100, round((g.get("current_value", 0) / g["target_value"]) * 100)) if g.get("target_value") else None
    ws_rollup = []
    for ws in workspaces:
        gs = [g for g in outcomes if g.get("workspace_id") == ws["id"]]
        pcts = [gpct(g) for g in gs if gpct(g) is not None]
        ws_rollup.append({
            "id": ws["id"], "name": ws["name"], "goal_count": len(gs),
            "avg_pct": round(sum(pcts) / len(pcts)) if pcts else None,
            "goals": [{"id": g["id"], "title": g["title"], "pct": gpct(g), "status": g.get("status"),
                       "current_value": g.get("current_value"), "target_value": g.get("target_value"), "unit": g.get("unit"), "trend": trend_map.get(g["id"], [])} for g in gs],
        })
    all_pcts = [gpct(g) for g in outcomes if gpct(g) is not None]
    goal_rollup = {
        "total_goals": len(outcomes),
        "on_track": len([g for g in outcomes if g.get("status") == "on_track"]),
        "at_risk": len([g for g in outcomes if g.get("status") == "at_risk"]),
        "avg_progress": round(sum(all_pcts) / len(all_pcts)) if all_pcts else 0,
        "workspaces": [w for w in ws_rollup if w["goal_count"] > 0],
    }
    return {
        "pipeline_value": pipeline_value, "won_value": won_value,
        "open_opportunities": len([o for o in opps if o.get("stage") not in ("closed_won", "closed_lost")]),
        "active_workspaces": len(workspaces), "at_risk_commitments": at_risk,
        "funnel": funnel, "portfolio": portfolio, "goal_rollup": goal_rollup,
    }
