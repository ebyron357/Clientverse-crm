"""Recovery runner — turns an approved Recovery Case into work that has actually happened.

This is the stage between approval and a provider. Until now an approved recovery strategy
sat there: the plan existed, a human had authorised it, and nothing moved. The runner is
what moves it.

For each approved case it walks the plan's steps in order and does what each one permits:

* an **internal** step is executed here and now — it never leaves the CRM, so there is
  nothing to authorise beyond the approval already given;
* an **outbound** step is drafted into a conversation and bound to its own M-07 approval,
  and then it stops. It stops at the provider boundary, with a named refusal, because no
  channel adapter exists. That refusal is the honest outcome, not a failure to handle.

Two deliberate choices worth stating, because both could reasonably have gone the other
way:

**The strategy's approval is not the message's approval.** An operator approving "reach
out to this client by email" has approved a plan, not a specific sentence. Each outbound
message therefore raises its own approval carrying the exact text that would be sent. That
is more friction, and it is the friction that makes the audit trail mean something.

**Running is idempotent per case.** The queue can deliver a job twice — that is what a
durable queue does — so the runner records what it produced against the case and a second
run adopts that work instead of drafting a second copy of the same message. A retry must
never turn into a client receiving the same thing twice.

This module executes; it does not decide. Lane selection lives in `recovery_strategy`,
authorisation in `approval_queue`, delivery in `conversations`.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

import approval_queue
import conversations
import recovery_case
import recovery_strategy

JOB_RUN_RECOVERY_CASE = "recovery.run_case"

# Outcomes a step can reach. `blocked` is not an error: it is the system correctly
# refusing to do something it is not yet permitted to do.
STEP_DONE = "done"
STEP_DRAFTED = "drafted"
STEP_BLOCKED = "blocked"
STEP_SKIPPED = "skipped"


class RecoveryRunnerError(Exception):
    pass


async def enqueue_case(queue, *, tenant_id: str, case_id: str,
                       actor: str = "recovery-runner") -> dict:
    """Queue an approved case for execution.

    The dedupe key is the case, so a case queued twice before the first run completes
    collapses to one job rather than racing itself.
    """
    return await queue.enqueue(
        tenant_id=tenant_id,
        queue="system",
        item_type=JOB_RUN_RECOVERY_CASE,
        payload={"tenant_id": tenant_id, "case_id": case_id},
        dedupe_key=f"{JOB_RUN_RECOVERY_CASE}:{case_id}",
        source_ref=f"recovery_case:{case_id}",
        actor=actor,
    )


async def _existing_message_for_step(db, tenant_id: str, case_id: str,
                                     step_index: int) -> Optional[dict]:
    """The message a previous run already drafted for this step, if there was one.

    Idempotency rests on this: the draft carries an idempotency key derived from the case
    and the step, so re-running finds the original rather than writing another.
    """
    return await conversations.find_message_by_idempotency_key(
        db, tenant_id, _step_key(case_id, step_index))


def _step_key(case_id: str, step_index: int) -> str:
    return f"recovery:{case_id}:step:{step_index}"


async def _conversation_for_case(db, tenant_id: str, case: dict, channel: str,
                                 actor: str) -> dict:
    """Find or open the thread this case's outreach belongs to.

    Keyed on the case so every step of one recovery lands in one conversation rather than
    scattering across threads an operator then has to reassemble.
    """
    external_thread_id = f"recovery_case:{case['id']}:{channel}"
    existing = await conversations.find_conversation_by_external_thread(
        db, tenant_id, channel, external_thread_id)
    if existing:
        return existing

    participants = []
    if case.get("contact_id"):
        participants.append({"kind": conversations.PARTICIPANT_CONTACT,
                             "id": case["contact_id"]})
    elif case.get("external_identity"):
        # All we know about the counterparty is how they reached us.
        identity = case["external_identity"]
        participants.append({"kind": conversations.PARTICIPANT_CONTACT,
                             "id": None, "address": identity.get("value"),
                             "display_name": identity.get("value")})

    return await conversations.create_conversation(
        db, tenant_id=tenant_id, channel=channel, actor=actor,
        subject=f"Recovery: {case.get('title') or case.get('reason')}"[:300],
        participants=participants,
        workspace_id=case.get("workspace_id"),
        company_id=case.get("company_id"),
        contact_id=case.get("contact_id"),
        handled_by=conversations.HANDLED_BY_AGENT,
        external_thread_id=external_thread_id)


def _draft_body(case: dict, step: dict) -> str:
    """The text an operator will be asked to approve.

    Deliberately a plain statement of intent built from the case's own cited facts — not
    generated prose. A drafting model can be introduced later behind the same approval;
    what must not happen is an unreviewed message reaching a client because the draft
    looked finished.
    """
    lines = [
        f"[DRAFT — prepared by ClientVerse for {step['action'].replace('_', ' ')}]",
        "",
        f"Recovery reason: {case.get('reason')}",
    ]
    if case.get("potential_value") is not None:
        lines.append(
            f"Opportunity value on record: {case['potential_value']} "
            f"{case.get('currency') or ''} (estimated, not recovered)")
    lines += ["", f"Intended next step: {step['detail']}", "",
              "This text has not been sent. It requires approval, an authorised channel, "
              "and a registered delivery provider before it can leave the CRM."]
    return "\n".join(lines)


async def _run_internal_step(db, tenant_id: str, case: dict, step: dict, actor: str,
                             audit: Optional[Callable[..., Awaitable[Any]]]) -> dict:
    """Execute a step that never leaves the CRM.

    Internal steps are the part of a recovery that can genuinely happen today, so they are
    performed rather than described: the work lands as a task an owner can see.
    """
    task = {
        "id": f"task_{case['id'][-8:]}_{step['action'][:12]}",
        "tenant_id": tenant_id,
        "workspace_id": case.get("workspace_id"),
        "title": f"{step['action'].replace('_', ' ').capitalize()}: {case.get('title')}"[:200],
        "assignee": (case.get("evidence") or {}).get("owner"),
        "due_date": None,
        "status": "todo",
        "source": "recovery_runner",
        "recovery_case_id": case["id"],
        "detail": step["detail"],
    }
    # Idempotent by construction: the id is derived from the case and the step, so a
    # replayed job updates the same task instead of creating another.
    await db.tasks.update_one({"id": task["id"], "tenant_id": tenant_id},
                              {"$setOnInsert": task}, upsert=True)
    if audit:
        await audit("recovery_case.step_executed", "recovery_case", case["id"], tenant_id,
                    actor, workspace_id=case.get("workspace_id"),
                    payload={"action": step["action"], "task_id": task["id"]})
    return {"status": STEP_DONE, "action": step["action"], "channel": step["channel"],
            "task_id": task["id"]}


async def _run_outbound_step(db, tenant_id: str, case: dict, step: dict, index: int,
                             actor: str,
                             audit: Optional[Callable[..., Awaitable[Any]]]) -> dict:
    """Draft an outbound step and take it as far as the gate allows.

    The furthest this can currently go is a message that exists, carries its own approval
    request, and is refused at dispatch with the precondition that stopped it named.
    """
    existing = await _existing_message_for_step(db, tenant_id, case["id"], index)
    if existing:
        return {"status": STEP_DRAFTED, "action": step["action"], "channel": step["channel"],
                "message_id": existing["id"], "approval_id": existing.get("approval_id"),
                "reused": True,
                "blocked_reason": existing.get("blocked_reason") or step.get("blocked_reason")}

    conversation = await _conversation_for_case(db, tenant_id, case, step["channel"], actor)
    message = await conversations.draft_message(
        db, tenant_id=tenant_id, conversation_id=conversation["id"],
        body=_draft_body(case, step), actor=actor,
        idempotency_key=_step_key(case["id"], index),
        requester_kind=approval_queue.REQUESTER_AGENT)

    # Its own approval, carrying the exact text. The strategy's approval authorised the
    # plan; this authorises the words.
    message = await conversations.request_approval(
        db, tenant_id=tenant_id, message_id=message["id"], actor=actor)

    if audit:
        await audit("recovery_case.step_drafted", "recovery_case", case["id"], tenant_id,
                    actor, workspace_id=case.get("workspace_id"),
                    payload={"action": step["action"], "channel": step["channel"],
                             "message_id": message["id"],
                             "approval_id": message.get("approval_id")})
    return {"status": STEP_DRAFTED, "action": step["action"], "channel": step["channel"],
            "message_id": message["id"], "approval_id": message.get("approval_id"),
            "reused": False, "blocked_reason": step.get("blocked_reason")}


async def run_case(db, *, tenant_id: str, case_id: str, actor: str = "recovery-runner",
                   audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    """Execute one approved Recovery Case as far as it is permitted to go.

    Refuses anything not approved. Moves the case to `executing` on entry and to `engaged`
    only if something actually reached a counterparty — which, with no provider registered,
    it currently cannot. The case does not advance on the strength of intent.
    """
    case = await recovery_case.get_case(db, tenant_id, case_id)
    if not case:
        raise RecoveryRunnerError("Recovery case not found")

    if case["state"] not in (recovery_case.APPROVED, recovery_case.EXECUTING):
        raise RecoveryRunnerError(
            f"Only an approved case can be run; this one is '{case['state']}'")

    plan_id = case.get("plan_reference")
    if not plan_id:
        raise RecoveryRunnerError("Recovery case has no plan to execute")
    strategy = await recovery_strategy.get_strategy(db, tenant_id, plan_id)
    if not strategy:
        raise RecoveryRunnerError("The case's recovery plan no longer exists")

    # Verify the plan's own approval rather than trusting the case's state, so a case
    # whose approval was later withdrawn cannot be executed on a stale flag.
    approval_id = case.get("approval_reference")
    approval = (await approval_queue.get(db, tenant_id, approval_id)) if approval_id else None
    if not approval or approval.get("status") != approval_queue.APPROVED:
        raise RecoveryRunnerError(
            "The recovery plan's approval is not approved; nothing may be executed")

    if case["state"] != recovery_case.EXECUTING:
        case = await recovery_case.set_state(
            db, tenant_id=tenant_id, case_id=case_id, state=recovery_case.EXECUTING,
            actor=actor, detail={"plan": plan_id}, audit=audit)

    results = []
    for index, step in enumerate(strategy.get("steps") or []):
        if step["channel"] == conversations.CHANNEL_INTERNAL:
            results.append(await _run_internal_step(db, tenant_id, case, step, actor, audit))
        else:
            results.append(
                await _run_outbound_step(db, tenant_id, case, step, index, actor, audit))

    drafted = [r for r in results if r["status"] == STEP_DRAFTED]
    if drafted:
        # Every outbound step has a home and an approval; none has been sent. Point the
        # case at the conversation so an operator can find the pending work.
        first = drafted[0]
        message = await conversations.get_message(db, tenant_id, first["message_id"])
        if message:
            await recovery_case.attach(db, tenant_id=tenant_id, case_id=case_id, actor=actor,
                                       conversation_reference=message["conversation_id"])

    return {
        "case_id": case_id,
        "plan_id": plan_id,
        "steps": results,
        "internal_executed": len([r for r in results if r["status"] == STEP_DONE]),
        "outbound_drafted": len(drafted),
        # Stated plainly so no caller can read this result as "the client was contacted".
        "outbound_sent": 0,
        "awaiting": [r["approval_id"] for r in drafted if r.get("approval_id")],
        "blocked_reasons": sorted({r["blocked_reason"] for r in results
                                   if r.get("blocked_reason")}),
    }


async def run_ready_cases(db, queue, *, tenant_id: str, actor: str = "recovery-runner",
                          limit: int = 50,
                          audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    """Queue every approved case for one tenant. Queuing, not running: the worker runs it."""
    cases = await recovery_case.list_cases(db, tenant_id, state=recovery_case.APPROVED,
                                           limit=limit)
    queued = []
    for case in cases:
        item = await enqueue_case(queue, tenant_id=tenant_id, case_id=case["id"], actor=actor)
        queued.append({"case_id": case["id"], "work_item_id": item["id"],
                       "deduplicated": item.get("deduplicated", False)})
    return {"tenant_id": tenant_id, "approved_cases": len(cases), "queued": queued}


async def run_ready_cases_all_tenants(db, queue, *, actor: str = "cron",
                                      audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    tenant_ids = await db.tenants.distinct("tenant_id")
    summaries = []
    for tenant_id in tenant_ids:
        try:
            summaries.append(await run_ready_cases(db, queue, tenant_id=tenant_id,
                                                   actor=actor, audit=audit))
        except Exception as exc:  # one tenant must never block the sweep
            summaries.append({"tenant_id": tenant_id, "error": str(exc)[:300]})
    return {"tenants": len(tenant_ids), "summaries": summaries}
