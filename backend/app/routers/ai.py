"""Evidence-backed AI generation route."""
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.shared import (db, new_id, now_iso, record_event, get_current_user,
                        compute_health, logger)

router = APIRouter(prefix="/api")

class AIInput(BaseModel):
    workspace_id: str
    mode: str = "health_summary"  # or draft_message
    instruction: Optional[str] = None

@router.post("/ai/generate")
async def ai_generate(inp: AIInput, user=Depends(get_current_user)):
    ws = await db.workspaces.find_one({"id": inp.workspace_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    scoped = {"tenant_id": user["tenant_id"], "workspace_id": inp.workspace_id}
    commitments = await db.commitments.find(scoped, {"_id": 0}).to_list(500)
    tasks = await db.tasks.find(scoped, {"_id": 0}).to_list(500)
    deliverables = await db.deliverables.find(scoped, {"_id": 0}).to_list(500)
    requests_ = await db.client_requests.find(scoped, {"_id": 0}).to_list(500)
    health = compute_health(commitments, tasks, deliverables, requests_)

    sources = []
    for c in commitments:
        sources.append({"type": "commitment", "id": c["id"], "label": c["title"], "status": c.get("status")})
    for r in requests_:
        sources.append({"type": "client_request", "id": r["id"], "label": r["title"], "status": r.get("status")})
    for t in tasks:
        sources.append({"type": "task", "id": t["id"], "label": t["title"], "status": t.get("status")})

    facts_text = "\n".join([f"- [{s['type']}] {s['label']} (status: {s['status']})" for s in sources]) or "- No records yet."
    run_id = new_id("airun")
    await record_event("agent.run_started", "ai_run", run_id, user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"mode": inp.mode})

    if inp.mode == "draft_message":
        system = "You are a client operations assistant. Draft a concise, professional client update email based ONLY on the provided facts. Do not invent facts. Clearly separate what is known (fact) from any suggestion (inference)."
        prompt = f"Client workspace: {ws['name']}\nHealth score: {health['score']}/100 ({health['band']}).\nKnown facts:\n{facts_text}\n\nInstruction: {inp.instruction or 'Write a status update to the client.'}"
    else:
        system = "You are a client health analyst. Summarize the client's health based ONLY on the provided facts. Be explicit about what is a fact vs an inference. Keep it under 150 words."
        prompt = f"Client workspace: {ws['name']}\nComputed health score: {health['score']}/100 ({health['band']}).\nContributing factors:\n" + "\n".join([f"- {f['factor']}: {f['impact']} ({f['detail']})" for f in health['factors']]) + f"\n\nKnown facts:\n{facts_text}"

    ai_text = ""
    model_version = "claude-sonnet-4-6"
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=run_id,
                       system_message=system).with_model("anthropic", model_version)
        resp = await chat.send_message(UserMessage(text=prompt))
        ai_text = resp if isinstance(resp, str) else str(resp)
        await record_event("agent.run_completed", "ai_run", run_id, user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"mode": inp.mode})
    except Exception as e:
        logger.exception("AI generation failed")
        await record_event("agent.run_failed", "ai_run", run_id, user["tenant_id"], user["email"], workspace_id=inp.workspace_id, payload={"error": str(e)})
        raise HTTPException(status_code=502, detail="AI generation failed. Please retry.")

    result = {
        "run_id": run_id, "mode": inp.mode, "output": ai_text.strip(),
        "sources": sources, "health": health,
        "confidence": "high" if len(sources) >= 3 else ("medium" if sources else "low"),
        "model_version": model_version, "prompt_version": "v1", "policy_version": "v1",
        "freshness": now_iso(), "classification": {"fact_basis": len(sources)},
    }
    await db.ai_runs.insert_one({"id": run_id, "tenant_id": user["tenant_id"], "workspace_id": inp.workspace_id,
                                 "created_at": now_iso(), **result})
    return {k: v for k, v in result.items()}
