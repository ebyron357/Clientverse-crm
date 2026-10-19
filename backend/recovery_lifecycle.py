"""Recovery case lifecycle — the moves that depend on what actually happened.

`recovery_case` owns the state machine; it deliberately knows nothing about messages,
approvals or the work queue. Two of its transitions, though, can only be decided by
reading those records, and before this module nothing made either of them:

* **executing -> engaged.** `engaged` means outreach on the case reached the client: a
  message a provider accepted. The runner drafts and stops at the approval gate, so the
  moment of engagement is whenever a drafted message is finally sent -- through the send
  route, a reconciled `outcome_unknown`, or anything else. `sync_engagement` derives the
  state from the messages, so every one of those paths reaches the same answer, and a
  draft never does: drafted is not sent.

* **open -> closed.** Closing takes a case out of open potential, and it must also stop
  the case's pending work. A case closed while its strategy approval or a drafted
  message's approval is still open would leave an operator able to approve -- and send --
  outreach for a recovery nobody is pursuing. `close_case` withdraws that work in the same
  call that closes the case.

Nothing here sends anything, and nothing here decides an outcome: an outcome is the
attribution ledger's to record.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Optional

import approval_queue
import conversations as conversation_service
import recovery_case
import recovery_strategy
from work_queue import OPEN_STATES as WORK_OPEN_STATES
from work_queue import WorkQueue, WorkQueueError

# Message states that are still on their way to a client and must be stopped when the
# case they serve is closed. Anything past these has either gone or failed already.
PENDING_MESSAGE_STATES = (conversation_service.DRAFT, conversation_service.PENDING_APPROVAL,
                          conversation_service.APPROVED)
CONTACT_STATES = (conversation_service.SENT, conversation_service.DELIVERED)


async def _case_conversation_ids(db: Any, tenant_id: str, case_ids: list[str]) -> dict[str, str]:
    """conversation id -> recovery case id, for the given cases."""
    if not case_ids:
        return {}
    rows = await db[conversation_service.CONVERSATIONS].find(
        {"tenant_id": tenant_id, "recovery_case_id": {"$in": case_ids}},
        {"_id": 0, "id": 1, "recovery_case_id": 1}).to_list(len(case_ids) * 4 + 50)
    return {row["id"]: row["recovery_case_id"] for row in rows}


async def last_contact_by_case(db: Any, tenant_id: str, case_ids: list[str]) -> dict[str, str]:
    """The most recent time a message on each case reached the client, where one did.

    Only `sent` and `delivered` count. A draft, an approved-but-unsent message, a blocked
    one and an `outcome_unknown` one all leave a case un-engaged.
    """
    conversation_cases = await _case_conversation_ids(db, tenant_id, case_ids)
    if not conversation_cases:
        return {}
    messages = await db[conversation_service.MESSAGES].find(
        {"tenant_id": tenant_id, "conversation_id": {"$in": list(conversation_cases)},
         "direction": conversation_service.OUTBOUND,
         "status": {"$in": list(CONTACT_STATES)}},
        {"_id": 0, "conversation_id": 1, "sent_at": 1, "delivered_at": 1, "created_at": 1},
    ).to_list(len(conversation_cases) * 20 + 100)
    latest: dict[str, str] = {}
    for message in messages:
        case_id = conversation_cases.get(message.get("conversation_id"))
        at = str(message.get("delivered_at") or message.get("sent_at")
                 or message.get("created_at") or "")
        if case_id and at > latest.get(case_id, ""):
            latest[case_id] = at
    return latest


async def sync_engagement(db: Any, *, tenant_id: str, case_id: str,
                          actor: str = "recovery-lifecycle",
                          audit: Optional[Callable[..., Awaitable[Any]]] = None
                          ) -> Optional[dict]:
    """Move an `executing` case to `engaged` if, and only if, a message on it was sent.

    Returns the updated case when it moved, otherwise None. Idempotent: a case already
    engaged, or one with nothing sent, is left as it is.
    """
    case = await recovery_case.get_case(db, tenant_id, case_id)
    if not case or case.get("state") != recovery_case.EXECUTING:
        return None
    contact = await last_contact_by_case(db, tenant_id, [case_id])
    if case_id not in contact:
        return None
    try:
        return await recovery_case.set_state(
            db, tenant_id=tenant_id, case_id=case_id, state=recovery_case.ENGAGED,
            actor=actor, detail={"last_contact_at": contact[case_id],
                                 "basis": "a message on this case reached the client"},
            audit=audit)
    except recovery_case.InvalidCaseTransition:
        # Moved concurrently -- by another sync, or closed. Either way nothing to do.
        return None


async def withdraw_pending_work(db: Any, *, tenant_id: str, case: dict, reason: str,
                                actor: str) -> dict:
    """Stop everything still queued up on behalf of a case that is no longer pursued.

    Withdraws an undecided strategy approval, refuses every drafted or approved message
    (cancelling its approval first, so it cannot be decided afterwards), and resolves the
    operator work item. Each step is best-effort and reported: a record that already moved
    on is not an error, and one failure must not stop the rest.
    """
    detail = f"The recovery case was closed ({reason}); this will not be sent."
    report: dict[str, Any] = {"approvals_cancelled": [], "messages_refused": [],
                              "work_item_resolved": None, "errors": []}

    async def cancel_approval(approval_id: Optional[str]) -> None:
        if not approval_id:
            return
        approval = await approval_queue.get(db, tenant_id, approval_id)
        if not approval or approval.get("status") != approval_queue.REQUESTED:
            return
        try:
            await approval_queue.cancel(db, tenant_id=tenant_id, approval_id=approval_id,
                                        actor=actor, reason=detail)
            report["approvals_cancelled"].append(approval_id)
        except approval_queue.ApprovalError as exc:
            report["errors"].append(f"approval {approval_id}: {str(exc)[:120]}")

    await cancel_approval(case.get("approval_reference"))
    # A plan still only proposed is withdrawn with its approval, so it stops being listed
    # as awaiting a decision. An approved plan is left as it is: that decision was made.
    plan = (await recovery_strategy.get_strategy(db, tenant_id, case["plan_reference"])
            if case.get("plan_reference") else None)
    if plan and plan.get("state") == recovery_strategy.STATE_PROPOSED:
        try:
            await recovery_strategy.set_state(db, tenant_id, plan["id"],
                                              state=recovery_strategy.STATE_WITHDRAWN,
                                              actor=actor)
            report["strategy_withdrawn"] = plan["id"]
        except recovery_strategy.RecoveryStrategyError as exc:
            report["errors"].append(f"strategy {plan['id']}: {str(exc)[:120]}")

    conversation_cases = await _case_conversation_ids(db, tenant_id, [case["id"]])
    if conversation_cases:
        pending = await db[conversation_service.MESSAGES].find(
            {"tenant_id": tenant_id, "conversation_id": {"$in": list(conversation_cases)},
             "direction": conversation_service.OUTBOUND,
             "status": {"$in": list(PENDING_MESSAGE_STATES)}},
            {"_id": 0, "id": 1, "approval_id": 1}).to_list(200)
        for message in pending:
            await cancel_approval(message.get("approval_id"))
            try:
                await conversation_service.mark_refused(
                    db, tenant_id=tenant_id, message_id=message["id"], actor=actor,
                    reason=conversation_service.REFUSAL_APPROVAL, detail=detail)
                report["messages_refused"].append(message["id"])
            except conversation_service.ConversationError as exc:
                report["errors"].append(f"message {message['id']}: {str(exc)[:120]}")

    item_id = case.get("work_item_reference")
    if item_id:
        queue = WorkQueue(db)
        item = await queue.get(item_id, tenant_id=tenant_id)
        if item and item.get("status") in WORK_OPEN_STATES:
            try:
                await queue.resolve(item_id, tenant_id=tenant_id, actor=actor,
                                    resolution=f"recovery_case_closed:{reason}")
                report["work_item_resolved"] = item_id
            except WorkQueueError as exc:
                report["errors"].append(f"work item {item_id}: {str(exc)[:120]}")
    return report


async def close_case(db: Any, *, tenant_id: str, case_id: str, reason: str,
                     actor: str = "recovery-lifecycle", note: Optional[str] = None,
                     detail: Optional[dict] = None,
                     audit: Optional[Callable[..., Awaitable[Any]]] = None) -> dict:
    """Close a case with a named reason and withdraw the work still pending on it.

    Raises `RecoveryCaseNotFound` for a case this tenant does not own and
    `InvalidCaseTransition` for one already closed -- the API maps those to 404 and 409.
    """
    closed = await recovery_case.close_case(
        db, tenant_id=tenant_id, case_id=case_id, reason=reason, actor=actor, note=note,
        detail=detail, audit=audit)
    withdrawn = await withdraw_pending_work(db, tenant_id=tenant_id, case=closed,
                                            reason=reason, actor=actor)
    return {**closed, "withdrawn": withdrawn}


async def close_if_open(db: Any, *, tenant_id: str, case_id: str, reason: str,
                        actor: str = "recovery-lifecycle", note: Optional[str] = None,
                        detail: Optional[dict] = None,
                        audit: Optional[Callable[..., Awaitable[Any]]] = None
                        ) -> Optional[dict]:
    """Close the case if it is still open; return it, or None if it was not open."""
    case = await recovery_case.get_case(db, tenant_id, case_id)
    if not case or case.get("state") not in recovery_case.OPEN_STATES:
        return None
    try:
        return await close_case(db, tenant_id=tenant_id, case_id=case_id, reason=reason,
                                actor=actor, note=note, detail=detail, audit=audit)
    except recovery_case.InvalidCaseTransition:
        return None
