"""Agent security gateway, first slice (blueprint §6, P0 "Agent security gateway").

The blueprint's rule is that a model may ask for an action but never grants itself
permission. ClientVerse already routes every MCP call through server-side checks
(allowlist, kill switch, security gate, rate limit, level-2 approval). This module closes
three gaps the Phase 0 threat model found in that path:

* **Approval bound to the exact arguments.** A level-2 approval authorised the tool and a
  pending-action id, but not what the action would write. The gateway records a SHA-256
  of the canonical arguments on the approval and the claim must match it, so changing
  the stored arguments after approval invalidates the approval.
* **Execution-time re-check.** An approval decided after the kill switch was turned on
  still executed. The gateway re-checks the kill switch, the emergency stop and the
  tenant allowlist at the moment of execution, not only at request time.
* **Emergency stop.** The kill switch only refused new MCP calls. The emergency stop
  also cancels the agent approvals still waiting, cancels pending MCP writes, takes the
  tenant's open work-queue items out of service, and stops workers claiming more for
  that tenant until an admin releases it. It returns a receipt of what it did.

Everything here sits behind ``AGENT_GATEWAY_V2`` (off by default), so deploying this code
changes nothing until the flag is turned on, first in staging.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

FLAG = "AGENT_GATEWAY_V2"
STOPS = "agent_emergency_stops"


def enabled() -> bool:
    """Read the flag on every call, so a test or an operator can change it at run time."""
    return os.environ.get(FLAG, "0").strip().lower() in ("1", "true", "yes", "on")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GatewayRefusal(Exception):
    """The gateway refused an action. `status_code` is the HTTP answer to give."""

    def __init__(self, status_code: int, reason: str):
        super().__init__(reason)
        self.status_code = status_code
        self.reason = reason


def args_digest(args: Optional[dict]) -> str:
    """SHA-256 of the arguments in canonical JSON (sorted keys, no whitespace).

    Canonical so that the same arguments always give the same digest, whatever order a
    client sent the keys in.
    """
    canonical = json.dumps(args or {}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def stop_state(db: Any, tenant_id: str) -> Optional[dict]:
    """The tenant's active emergency stop, or None."""
    doc: Optional[dict] = await db[STOPS].find_one({"tenant_id": tenant_id, "active": True}, {"_id": 0})
    return doc


async def is_stopped(db: Any, tenant_id: str) -> bool:
    if not enabled():
        return False
    return await stop_state(db, tenant_id) is not None


async def assert_may_execute(db: Any, *, tenant_id: str, tool: str, server: dict) -> None:
    """Re-check, at execution time, what was checked when the action was requested."""
    if not enabled():
        return
    if await stop_state(db, tenant_id):
        raise GatewayRefusal(423, "Agent actions are stopped for this workspace (emergency stop)")
    if server.get("kill_switch"):
        raise GatewayRefusal(423, "MCP server is disabled by kill switch")
    if tool not in (server.get("allowlist") or []):
        raise GatewayRefusal(403, "Tool is no longer in the tenant allowlist")


async def emergency_stop(db: Any, *, tenant_id: str, actor: str, reason: str) -> dict:
    """Stop agent activity for one tenant and return a receipt of what was stopped.

    Order matters: the stop record is written first, so a worker or an approval that
    races this call sees the stop on its own re-check even if it slips past a step below.
    """
    import approval_queue as approvals
    import work_queue as wq

    at = _now()
    await db[STOPS].update_one(
        {"tenant_id": tenant_id, "active": True},
        {"$setOnInsert": {"tenant_id": tenant_id, "active": True, "stopped_at": at,
                          "stopped_by": actor, "reason": reason}},
        upsert=True,
    )
    await db.mcp_server_state.update_many({"tenant_id": tenant_id}, {"$set": {"kill_switch": True}})

    receipt: dict[str, Any] = {"tenant_id": tenant_id, "stopped_at": at, "stopped_by": actor,
                               "reason": reason, "approvals_cancelled": 0,
                               "pending_actions_cancelled": 0, "work_items_stopped": 0,
                               "work_items_in_flight": 0}

    # Agent requests and MCP writes still waiting for a person are withdrawn. Requests a
    # person raised for themselves are left alone: the stop is about agents.
    waiting = db[approvals.COLLECTION].find(
        {"tenant_id": tenant_id, "status": approvals.REQUESTED,
         "$or": [{"requester_kind": approvals.REQUESTER_AGENT}, {"kind": "mcp_write"}]},
        {"_id": 0, "id": 1})
    async for doc in waiting:
        try:
            await approvals.cancel(db, tenant_id=tenant_id, approval_id=doc["id"], actor=actor,
                                   reason=f"Emergency stop: {reason}")
            receipt["approvals_cancelled"] += 1
        except approvals.ApprovalError:
            pass  # decided concurrently; the execution-time re-check still refuses it

    cancelled = await db.mcp_pending_actions.update_many(
        {"tenant_id": tenant_id, "status": "pending_approval"},
        {"$set": {"status": "cancelled", "cancelled_at": at, "cancelled_by": actor}})
    receipt["pending_actions_cancelled"] = cancelled.modified_count

    # Items no worker holds go straight to dead-letter, where an admin can replay them
    # after the release. Items a worker holds keep their lease; the worker's own finish
    # still runs, but no worker can claim another item for this tenant while it is stopped.
    stopped = await db.work_queue.update_many(
        {"tenant_id": tenant_id, "status": {"$in": [wq.QUEUED, wq.RETRY_SCHEDULED]}},
        {"$set": {"status": wq.DEAD_LETTER, "updated_at": at, "active_dedupe_key": None,
                  "last_error": f"Emergency stop: {reason}", "failure_reason": "emergency_stop"},
         "$push": {"history": {"action": "emergency_stop", "actor": actor, "at": at,
                               "detail": {"reason": reason}}}})
    receipt["work_items_stopped"] = stopped.modified_count
    receipt["work_items_in_flight"] = await db.work_queue.count_documents(
        {"tenant_id": tenant_id, "status": {"$in": [wq.CLAIMED, wq.PROCESSING]}})

    await db[STOPS].update_one({"tenant_id": tenant_id, "active": True},
                               {"$set": {"receipt": receipt}})
    return receipt


async def release(db: Any, *, tenant_id: str, actor: str) -> dict:
    """End the emergency stop. The kill switch stays on until an admin turns it off,
    so agent tools come back by a second, deliberate step."""
    at = _now()
    result = await db[STOPS].update_many(
        {"tenant_id": tenant_id, "active": True},
        {"$set": {"active": False, "released_at": at, "released_by": actor}})
    return {"tenant_id": tenant_id, "released": result.modified_count > 0, "released_at": at,
            "kill_switch": "still on; turn it off on the MCP page when ready"}
