"""API surface for the durable work queue, Second Chance, the recovery strategy
composer, the approval queue, Next Best Action, and the external-component security gate.

Routes are attached to the existing `/api` router with the application's own auth,
tenancy and audit helpers injected, matching the pattern already used by
`client_value.register_client_value_routes`. Every handler is tenant-scoped through
`user["tenant_id"]`; no route accepts a caller-supplied tenant.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field

import approval_queue
import next_best_action as nba
import recovery_strategy
import second_chance
import security_gate
from work_queue import WorkQueue, WorkQueueError, InvalidTransition


class WorkItemResolution(BaseModel):
    resolution: str = Field(default="resolved", max_length=200)


class RecommendationPatch(BaseModel):
    state: str
    outcome: Optional[str] = Field(default=None, max_length=200)
    note: Optional[str] = Field(default=None, max_length=1000)
    snooze_minutes: Optional[int] = Field(default=None, ge=1, le=60 * 24 * 30)


class ApprovalRequestInput(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    kind: str = Field(default="external_effect", max_length=100)
    summary: Optional[str] = Field(default=None, max_length=2000)
    risk: str = Field(default=approval_queue.RISK_MEDIUM)
    workspace_id: Optional[str] = None
    subject_type: Optional[str] = Field(default=None, max_length=100)
    subject_id: Optional[str] = Field(default=None, max_length=100)
    action: Optional[dict] = None
    facts: Optional[list] = None
    expires_in_hours: Optional[int] = Field(default=None, ge=1, le=90 * 24)
    require_separate_approver: bool = False


class ApprovalDecisionInput(BaseModel):
    decision: str
    rationale: Optional[str] = Field(default=None, max_length=2000)


class ApprovalCancelInput(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class ComponentInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str
    source_url: str = Field(min_length=1, max_length=500)
    version: str = Field(min_length=1, max_length=100)
    digest: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)


class GateInput(BaseModel):
    checks: dict
    findings: Optional[list] = None
    scanner_results: Optional[list] = None


class DecisionInput(BaseModel):
    decision: str
    rationale: str = Field(min_length=1, max_length=2000)
    limitations: Optional[list] = None
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=365)


def register_operations_routes(router, db, record_event, get_current_user, require_role,
                               on_approval_decided=None):
    """Attach operations routes. Returns the shared WorkQueue instance.

    `on_approval_decided` is an optional async hook called with the decided approval and
    the deciding user. The application uses it to run the follow-through an approval
    authorises (executing a pending MCP write, for instance), so this surface and the
    older `/approvals` route produce identical behaviour.
    """
    queue = WorkQueue(db)

    # ------------------------------------------------------------ work queue

    @router.get("/work-queue")
    async def list_work_items(status: Optional[str] = Query(default="open"),
                              queue_name: Optional[str] = Query(default=None, alias="queue"),
                              item_type: Optional[str] = Query(default=None, alias="type"),
                              limit: int = Query(default=100, ge=1, le=500),
                              user=Depends(get_current_user)):
        return await queue.list_items(tenant_id=user["tenant_id"], status=status,
                                      queue=queue_name, item_type=item_type, limit=limit)

    @router.get("/work-queue/stats")
    async def work_queue_stats(user=Depends(get_current_user)):
        return await queue.stats(tenant_id=user["tenant_id"])

    @router.get("/work-queue/{item_id}")
    async def get_work_item(item_id: str, user=Depends(get_current_user)):
        item = await queue.get(item_id, tenant_id=user["tenant_id"])
        if not item:
            raise HTTPException(status_code=404, detail="Work item not found")
        return item

    @router.post("/work-queue/{item_id}/acknowledge")
    async def acknowledge_work_item(item_id: str, user=Depends(get_current_user)):
        try:
            item = await queue.acknowledge(item_id, tenant_id=user["tenant_id"], actor=user["email"])
        except WorkQueueError:
            raise HTTPException(status_code=404, detail="Work item not found")
        await record_event("work_item.acknowledged", "work_item", item_id, user["tenant_id"],
                           user["email"], workspace_id=item.get("workspace_id"),
                           payload={"type": item.get("type")})
        return item

    @router.post("/work-queue/{item_id}/resolve")
    async def resolve_work_item(item_id: str, inp: WorkItemResolution,
                                user=Depends(get_current_user)):
        try:
            item = await queue.resolve(item_id, tenant_id=user["tenant_id"], actor=user["email"],
                                       resolution=inp.resolution)
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except WorkQueueError:
            raise HTTPException(status_code=404, detail="Work item not found")
        await record_event("work_item.resolved", "work_item", item_id, user["tenant_id"],
                           user["email"], workspace_id=item.get("workspace_id"),
                           payload={"type": item.get("type"), "resolution": inp.resolution})
        return item

    @router.post("/work-queue/{item_id}/replay")
    async def replay_work_item(item_id: str, user=Depends(require_role("admin"))):
        try:
            item = await queue.replay(item_id, tenant_id=user["tenant_id"], actor=user["email"])
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except WorkQueueError:
            raise HTTPException(status_code=404, detail="Work item not found")
        await record_event("work_item.replayed", "work_item", item_id, user["tenant_id"],
                           user["email"], payload={"type": item.get("type")})
        return item

    # --------------------------------------------------------- second chance

    @router.post("/second-chance/detect")
    async def run_second_chance(user=Depends(require_role("admin"))):
        summary = await second_chance.run_detection(db, queue, user["tenant_id"],
                                                    actor=user["email"])
        await record_event("second_chance.detection_run", "second_chance", user["tenant_id"],
                           user["tenant_id"], user["email"], payload=summary)
        return summary

    @router.get("/second-chance/candidates")
    async def second_chance_candidates(limit: int = Query(default=100, ge=1, le=500),
                                       user=Depends(get_current_user)):
        return await queue.list_items(tenant_id=user["tenant_id"], status="open",
                                      queue=second_chance.QUEUE_NAME, limit=limit)

    # ------------------------------------------------------ next best action

    @router.get("/next-best-actions")
    async def list_next_best_actions(workspace_id: Optional[str] = Query(default=None),
                                     state: Optional[str] = Query(default="open"),
                                     limit: int = Query(default=50, ge=1, le=200),
                                     user=Depends(get_current_user)):
        return await nba.list_recommendations(db, user["tenant_id"], workspace_id=workspace_id,
                                              state=state, limit=limit)

    @router.get("/next-best-actions/summary")
    async def next_best_actions_summary(user=Depends(get_current_user)):
        return await nba.summary(db, user["tenant_id"])

    @router.post("/next-best-actions/generate")
    async def generate_next_best_actions(user=Depends(get_current_user)):
        result = await nba.generate(db, user["tenant_id"], actor=user["email"])
        await record_event("next_best_action.generated", "next_best_action", user["tenant_id"],
                           user["tenant_id"], user["email"], payload=result)
        return result

    @router.patch("/next-best-actions/{recommendation_id}")
    async def patch_next_best_action(recommendation_id: str, inp: RecommendationPatch,
                                     user=Depends(get_current_user)):
        try:
            updated = await nba.set_state(db, user["tenant_id"], recommendation_id,
                                          state=inp.state, actor=user["email"],
                                          outcome=inp.outcome, note=inp.note,
                                          snooze_minutes=inp.snooze_minutes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if not updated:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        await record_event("next_best_action.feedback", "next_best_action", recommendation_id,
                           user["tenant_id"], user["email"],
                           workspace_id=updated.get("workspace_id"),
                           payload={"state": inp.state, "outcome": inp.outcome})
        return updated

    # -------------------------------------------------------- approval queue

    @router.get("/approval-queue")
    async def list_approval_requests(status: Optional[str] = Query(default="open"),
                                     kind: Optional[str] = Query(default=None),
                                     risk: Optional[str] = Query(default=None),
                                     limit: int = Query(default=100, ge=1, le=500),
                                     user=Depends(get_current_user)):
        return await approval_queue.list_requests(db, user["tenant_id"], status=status,
                                                  kind=kind, risk=risk, limit=limit)

    @router.get("/approval-queue/summary")
    async def approval_queue_summary(user=Depends(get_current_user)):
        return await approval_queue.summary(db, user["tenant_id"])

    @router.post("/approval-queue")
    async def raise_approval_request(inp: ApprovalRequestInput,
                                     user=Depends(get_current_user)):
        try:
            request = await approval_queue.request(
                db, tenant_id=user["tenant_id"], title=inp.title, kind=inp.kind,
                actor=user["email"], requester_kind=approval_queue.REQUESTER_HUMAN,
                summary=inp.summary, risk=inp.risk, action=inp.action,
                subject_type=inp.subject_type, subject_id=inp.subject_id,
                workspace_id=inp.workspace_id, facts=inp.facts,
                expires_in_hours=inp.expires_in_hours,
                require_separate_approver=inp.require_separate_approver)
        except approval_queue.ApprovalError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        await record_event("approval.requested", "approval", request["id"], user["tenant_id"],
                           user["email"], workspace_id=inp.workspace_id,
                           payload={"title": inp.title, "risk": request["risk"]})
        return request

    @router.get("/approval-queue/{approval_id}")
    async def get_approval_request(approval_id: str, user=Depends(get_current_user)):
        request = await approval_queue.get(db, user["tenant_id"], approval_id)
        if not request:
            raise HTTPException(status_code=404, detail="Approval request not found")
        return request

    @router.post("/approval-queue/{approval_id}/decision")
    async def decide_approval_request(approval_id: str, inp: ApprovalDecisionInput,
                                      user=Depends(require_role("admin"))):
        try:
            request = await approval_queue.decide(
                db, tenant_id=user["tenant_id"], approval_id=approval_id,
                decision=inp.decision, actor=user["email"], rationale=inp.rationale)
        except approval_queue.ApprovalNotFound:
            raise HTTPException(status_code=404, detail="Approval request not found")
        except approval_queue.InvalidApprovalTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except approval_queue.ApprovalError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        await _sync_strategy_state(request, user["email"])
        if on_approval_decided:
            side_effects = await on_approval_decided(request, user)
            if side_effects:
                request = {**request, **side_effects}
        await record_event("approval.completed", "approval", approval_id, user["tenant_id"],
                           user["email"], workspace_id=request.get("workspace_id"),
                           payload={"decision": inp.decision})
        return request

    @router.post("/approval-queue/{approval_id}/cancel")
    async def cancel_approval_request(approval_id: str, inp: ApprovalCancelInput,
                                      user=Depends(get_current_user)):
        try:
            request = await approval_queue.cancel(
                db, tenant_id=user["tenant_id"], approval_id=approval_id,
                actor=user["email"], reason=inp.reason)
        except approval_queue.ApprovalNotFound:
            raise HTTPException(status_code=404, detail="Approval request not found")
        except approval_queue.InvalidApprovalTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        await _sync_strategy_state(request, user["email"])
        await record_event("approval.cancelled", "approval", approval_id, user["tenant_id"],
                           user["email"], workspace_id=request.get("workspace_id"),
                           payload={"reason": inp.reason})
        return request

    async def _sync_strategy_state(request: dict, actor: str):
        """Keep a recovery strategy's own state in step with its approval decision, so
        the two surfaces can never disagree about whether a proposal is still live."""
        if request.get("subject_type") != "recovery_strategy" or not request.get("subject_id"):
            return
        mapping = {
            approval_queue.APPROVED: recovery_strategy.STATE_APPROVED,
            approval_queue.REJECTED: recovery_strategy.STATE_REJECTED,
            approval_queue.CANCELLED: recovery_strategy.STATE_WITHDRAWN,
        }
        state = mapping.get(request.get("status"))
        if not state:
            return
        try:
            await recovery_strategy.set_state(db, request["tenant_id"], request["subject_id"],
                                              state=state, actor=actor)
        except recovery_strategy.RecoveryStrategyError:
            pass

    # ----------------------------------------------------- recovery strategies

    @router.get("/recovery-strategies")
    async def list_recovery_strategies(state: Optional[str] = Query(default=None),
                                       lane: Optional[str] = Query(default=None),
                                       limit: int = Query(default=100, ge=1, le=500),
                                       user=Depends(get_current_user)):
        return await recovery_strategy.list_strategies(db, user["tenant_id"], state=state,
                                                       lane=lane, limit=limit)

    @router.get("/recovery-strategies/summary")
    async def recovery_strategies_summary(user=Depends(get_current_user)):
        return await recovery_strategy.summary(db, user["tenant_id"])

    @router.get("/recovery-strategies/channel-authority")
    async def recovery_channel_authority(user=Depends(get_current_user)):
        """What this tenant is actually allowed to send on, and why not."""
        return await recovery_strategy.authorized_channels(db, user["tenant_id"])

    @router.post("/recovery-strategies/compose")
    async def compose_recovery_strategies(user=Depends(require_role("admin"))):
        summary_ = await recovery_strategy.compose_for_tenant(db, queue, user["tenant_id"],
                                                              actor=user["email"])
        await record_event("recovery_strategy.composed", "recovery_strategy",
                           user["tenant_id"], user["tenant_id"], user["email"],
                           payload=summary_)
        return summary_

    @router.get("/recovery-strategies/{strategy_id}")
    async def get_recovery_strategy(strategy_id: str, user=Depends(get_current_user)):
        strategy = await recovery_strategy.get_strategy(db, user["tenant_id"], strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Recovery strategy not found")
        return strategy

    # --------------------------------------------------------- security gate

    @router.get("/security-gate/status")
    async def security_gate_status(user=Depends(get_current_user)):
        return security_gate.pipeline_status()

    @router.get("/security-gate/components")
    async def list_external_components(state: Optional[str] = Query(default=None),
                                       kind: Optional[str] = Query(default=None),
                                       limit: int = Query(default=100, ge=1, le=500),
                                       user=Depends(get_current_user)):
        return await security_gate.list_components(db, user["tenant_id"], state=state,
                                                   kind=kind, limit=limit)

    @router.post("/security-gate/components")
    async def register_external_component(inp: ComponentInput,
                                          user=Depends(require_role("admin"))):
        try:
            component = await security_gate.register_component(
                db, tenant_id=user["tenant_id"], name=inp.name, kind=inp.kind,
                source_url=inp.source_url, version=inp.version, digest=inp.digest,
                description=inp.description, actor=user["email"])
        except security_gate.SecurityGateError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        await record_event("security_gate.component_registered", "external_component",
                           component["id"], user["tenant_id"], user["email"],
                           payload={"kind": inp.kind, "source_url": inp.source_url,
                                    "version": inp.version})
        return component

    @router.get("/security-gate/components/{component_id}")
    async def get_external_component(component_id: str, user=Depends(get_current_user)):
        component = await security_gate.get_component(db, user["tenant_id"], component_id)
        if not component:
            raise HTTPException(status_code=404, detail="Component not found")
        return component

    @router.post("/security-gate/components/{component_id}/gate-a")
    async def record_gate_a(component_id: str, inp: GateInput,
                            user=Depends(require_role("admin"))):
        return await _record_gate(component_id, "gate_a", inp, user)

    @router.post("/security-gate/components/{component_id}/gate-b")
    async def record_gate_b(component_id: str, inp: GateInput,
                            user=Depends(require_role("admin"))):
        return await _record_gate(component_id, "gate_b", inp, user)

    async def _record_gate(component_id: str, gate: str, inp: GateInput, user):
        try:
            component = await security_gate.record_gate(
                db, tenant_id=user["tenant_id"], component_id=component_id, gate=gate,
                checks=inp.checks, reviewer=user["email"], findings=inp.findings,
                scanner_results=inp.scanner_results)
        except security_gate.SecurityGateError as exc:
            detail = str(exc)
            raise HTTPException(status_code=404 if "not found" in detail.lower() else 400,
                                detail=detail)
        await record_event(f"security_gate.{gate}_recorded", "external_component", component_id,
                           user["tenant_id"], user["email"],
                           payload={"status": (component.get(gate) or {}).get("status")})
        return component

    @router.post("/security-gate/components/{component_id}/decision")
    async def decide_external_component(component_id: str, inp: DecisionInput,
                                        user=Depends(require_role("admin"))):
        kwargs = {}
        if inp.expires_in_days is not None:
            kwargs["expires_in_days"] = inp.expires_in_days
        try:
            component = await security_gate.decide(
                db, tenant_id=user["tenant_id"], component_id=component_id,
                decision=inp.decision, actor=user["email"], rationale=inp.rationale,
                limitations=inp.limitations, **kwargs)
        except security_gate.InvalidGateTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except security_gate.SecurityGateError as exc:
            detail = str(exc)
            raise HTTPException(status_code=404 if "not found" in detail.lower() else 400,
                                detail=detail)
        await record_event("security_gate.decision", "external_component", component_id,
                           user["tenant_id"], user["email"],
                           payload={"decision": inp.decision})
        return component

    return queue
