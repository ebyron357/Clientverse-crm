"""Approval queue — the human-in-the-loop gate for autonomous action (M-07).

The canonical governing document requires an approval surface that every autonomous
capability must pass through, and requires it to **reuse the existing C-09 primitives
rather than introduce a parallel gate** (§4 E-10, §8 #6). So this module writes to the
same `approvals` collection that `POST /api/approvals` and `PATCH /api/approvals/{id}`
already use. Records created here are richer, but a record created by the older route
still lists, reads and decides correctly, and a record created here is still decidable
through the older route.

What this adds on top of C-09:

* **A bound action.** A request carries the exact payload that would execute if it is
  approved. An approval authorises *that* action, not a category of actions.
* **Single-use consumption.** `consume()` atomically flips an approved request from
  `pending` to `consumed`. Two workers racing the same approval produce exactly one
  execution; the loser gets nothing. Without this an approval is a label, not a gate.
* **Expiry.** A request that is never decided goes stale rather than sitting approvable
  forever. Expiry is evaluated on read as well as by the sweep, so a lapsed request can
  never be approved just because the sweep has not run yet.
* **Provenance.** Who or what asked, whether it was an agent or a person, which record
  it concerns, and the facts cited in support — all recorded on the request.
* **Deduplication.** A second identical open request collapses onto the first, enforced
  by a unique index rather than a read-then-insert check.
* **An audit trail.** Every state change appends to `history` with actor and timestamp.

Deliberately NOT here: execution. This module records that an action is permitted; the
caller performs it. Nothing in this module sends, calls, or writes to a third party.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

COLLECTION = "approvals"

REQUESTED = "requested"
APPROVED = "approved"
REJECTED = "rejected"
EXPIRED = "expired"
CANCELLED = "cancelled"

STATUSES = (REQUESTED, APPROVED, REJECTED, EXPIRED, CANCELLED)
OPEN_STATUSES = (REQUESTED,)
DECIDED_STATUSES = (APPROVED, REJECTED)
# A request in one of these can never be decided again.
CLOSED_STATUSES = (APPROVED, REJECTED, EXPIRED, CANCELLED)

# Execution states for the bound action on an approved request.
EXECUTION_PENDING = "pending"
EXECUTION_CONSUMED = "consumed"
EXECUTION_NOT_APPLICABLE = "not_applicable"

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
RISK_CRITICAL = "critical"
RISK_TIERS = (RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL)
RISK_ORDER = {tier: index for index, tier in enumerate(RISK_TIERS)}

REQUESTER_AGENT = "agent"
REQUESTER_HUMAN = "human"
REQUESTER_SYSTEM = "system"
REQUESTER_KINDS = (REQUESTER_AGENT, REQUESTER_HUMAN, REQUESTER_SYSTEM)

DEFAULT_EXPIRY_HOURS = int(os.environ.get("APPROVAL_DEFAULT_EXPIRY_HOURS", str(7 * 24)))
MAX_EXPIRY_HOURS = int(os.environ.get("APPROVAL_MAX_EXPIRY_HOURS", str(90 * 24)))


class ApprovalError(Exception):
    """Raised for invalid approval operations."""


class ApprovalNotFound(ApprovalError):
    pass


class InvalidApprovalTransition(ApprovalError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _parse(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _history(action: str, actor: str, detail: Optional[dict] = None) -> dict:
    return {"action": action, "actor": actor, "at": _iso(_now()), "detail": detail or {}}


def normalise_risk(risk: Optional[str]) -> str:
    candidate = str(risk or "").strip().lower()
    return candidate if candidate in RISK_TIERS else RISK_MEDIUM


def _is_expired(doc: dict, reference: Optional[datetime] = None) -> bool:
    """True when an undecided request has passed its expiry."""
    if doc.get("status") not in OPEN_STATUSES:
        return False
    expires_at = _parse(doc.get("expires_at"))
    if expires_at is None:
        return False
    return (reference or _now()) >= expires_at


async def ensure_indexes(db) -> None:
    collection = db[COLLECTION]
    # Deduplication is enforced by the database. `active_dedupe_key` is present only
    # while a request is open, so an identical request may be raised again once the
    # previous one has been decided, rejected or has lapsed.
    await collection.create_index(
        [("tenant_id", 1), ("active_dedupe_key", 1)],
        unique=True,
        partialFilterExpression={"active_dedupe_key": {"$type": "string"}},
    )
    await collection.create_index([("tenant_id", 1), ("status", 1), ("created_at", -1)])
    await collection.create_index([("tenant_id", 1), ("expires_at", 1)])
    await collection.create_index([("tenant_id", 1), ("subject_type", 1), ("subject_id", 1)])


def _public(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    return {k: v for k, v in doc.items() if k not in ("_id", "active_dedupe_key")}


async def request(db, *, tenant_id: str, title: str, kind: str = "external_effect",
                  actor: str, requester_kind: str = REQUESTER_AGENT,
                  summary: Optional[str] = None, risk: str = RISK_MEDIUM,
                  action: Optional[dict] = None, subject_type: Optional[str] = None,
                  subject_id: Optional[str] = None, workspace_id: Optional[str] = None,
                  facts: Optional[list] = None, blocked_reasons: Optional[list] = None,
                  required_role: str = "admin", dedupe_key: Optional[str] = None,
                  expires_in_hours: Optional[int] = None,
                  require_separate_approver: bool = False) -> dict:
    """Raise an approval request.

    `action` is the bound payload — the exact thing that executes if this is approved.
    `blocked_reasons` records why the action cannot execute *even if approved* (no
    channel authorised yet, for instance). A request whose action is blocked is still
    worth raising: it tells the operator what the system wants to do and what is
    missing, and it never silently becomes executable later — the block is re-checked
    at consumption.
    """
    if not tenant_id:
        raise ApprovalError("tenant_id is required")
    if not str(title or "").strip():
        raise ApprovalError("title is required")
    if requester_kind not in REQUESTER_KINDS:
        raise ApprovalError(f"requester_kind must be one of {REQUESTER_KINDS}")

    hours = DEFAULT_EXPIRY_HOURS if expires_in_hours is None else int(expires_in_hours)
    if hours <= 0 or hours > MAX_EXPIRY_HOURS:
        raise ApprovalError(f"expires_in_hours must be between 1 and {MAX_EXPIRY_HOURS}")

    now = _now()
    doc = {
        "id": f"apr_{uuid.uuid4().hex[:12]}",
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "title": str(title).strip()[:300],
        "summary": (str(summary).strip()[:2000] if summary else None),
        "kind": kind,
        "status": REQUESTED,
        "risk": normalise_risk(risk),
        "requested_by": actor,
        "requester_kind": requester_kind,
        "required_role": required_role,
        "require_separate_approver": bool(require_separate_approver),
        "subject_type": subject_type,
        "subject_id": subject_id,
        "action": action or {},
        "facts": facts or [],
        "blocked_reasons": blocked_reasons or [],
        "execution": {
            "state": EXECUTION_PENDING if action else EXECUTION_NOT_APPLICABLE,
            "consumed_at": None,
            "consumed_by": None,
        },
        "dedupe_key": dedupe_key,
        "active_dedupe_key": dedupe_key,
        "created_at": _iso(now),
        "expires_at": _iso(now + timedelta(hours=hours)),
        "decided_by": None,
        "decided_at": None,
        "decision_rationale": None,
        "history": [_history("requested", actor, {"risk": normalise_risk(risk), "kind": kind})],
    }

    if dedupe_key:
        try:
            await db[COLLECTION].insert_one(dict(doc))
        except Exception as exc:  # duplicate key -> an identical request is already open
            if not _is_duplicate_key(exc):
                raise
            existing = await db[COLLECTION].find_one(
                {"tenant_id": tenant_id, "active_dedupe_key": dedupe_key}, {"_id": 0})
            if existing:
                result = _public(existing)
                result["deduplicated"] = True
                return result
            raise
    else:
        await db[COLLECTION].insert_one(dict(doc))

    result = _public(doc)
    result["deduplicated"] = False
    return result


def _is_duplicate_key(exc: Exception) -> bool:
    return getattr(exc, "code", None) == 11000 or "E11000" in str(exc)


async def get(db, tenant_id: str, approval_id: str) -> Optional[dict]:
    """Read one request, applying expiry so a lapsed request never reads as approvable."""
    doc = await db[COLLECTION].find_one({"id": approval_id, "tenant_id": tenant_id})
    if not doc:
        return None
    if _is_expired(doc):
        doc = await _mark_expired(db, doc) or doc
    return _public(doc)


async def _mark_expired(db, doc: dict) -> Optional[dict]:
    """Persist the lapse. Conditioned on the status we read, so a decision that lands
    in between wins and the request is not retroactively expired."""
    return await db[COLLECTION].find_one_and_update(
        {"id": doc["id"], "tenant_id": doc["tenant_id"], "status": REQUESTED},
        {"$set": {"status": EXPIRED, "expired_at": _iso(_now())},
         "$unset": {"active_dedupe_key": ""},
         "$push": {"history": _history("expired", "system",
                                       {"expires_at": doc.get("expires_at")})}},
        return_document=True,
    )


async def list_requests(db, tenant_id: str, *, status: Optional[str] = "open",
                        kind: Optional[str] = None, risk: Optional[str] = None,
                        subject_type: Optional[str] = None, subject_id: Optional[str] = None,
                        workspace_id: Optional[str] = None, limit: int = 100) -> list[dict]:
    criteria: dict[str, Any] = {"tenant_id": tenant_id}
    if status == "open":
        criteria["status"] = {"$in": list(OPEN_STATUSES)}
    elif status and status != "all":
        criteria["status"] = status
    if kind:
        criteria["kind"] = kind
    if risk:
        criteria["risk"] = normalise_risk(risk)
    if subject_type:
        criteria["subject_type"] = subject_type
    if subject_id:
        criteria["subject_id"] = subject_id
    if workspace_id:
        criteria["workspace_id"] = workspace_id

    docs = await db[COLLECTION].find(criteria).sort("created_at", -1).to_list(int(limit))
    results: list[dict] = []
    for doc in docs:
        if _is_expired(doc):
            doc = await _mark_expired(db, doc) or doc
            # An expired request is no longer open, so drop it from the open listing
            # rather than reporting a request the operator can no longer act on.
            if status == "open":
                continue
        results.append(_public(doc))
    return results


async def decide(db, *, tenant_id: str, approval_id: str, decision: str, actor: str,
                 rationale: Optional[str] = None) -> dict:
    """Approve or reject. Refuses anything already closed, and refuses a lapsed request."""
    if decision not in DECIDED_STATUSES:
        raise ApprovalError(f"decision must be one of {DECIDED_STATUSES}")

    doc = await db[COLLECTION].find_one({"id": approval_id, "tenant_id": tenant_id})
    if not doc:
        raise ApprovalNotFound("Approval request not found")

    if _is_expired(doc):
        await _mark_expired(db, doc)
        raise InvalidApprovalTransition(
            f"Approval request expired at {doc.get('expires_at')} and can no longer be decided")

    status = doc.get("status", REQUESTED)
    if status in CLOSED_STATUSES:
        raise InvalidApprovalTransition(f"Approval request is already '{status}'")

    if doc.get("require_separate_approver") and actor and actor == doc.get("requested_by"):
        # Separation of duties, only where the requester asked for it. It is off by
        # default so the long-standing C-09 flow (a person raises and then approves
        # their own request) keeps working unchanged.
        raise InvalidApprovalTransition(
            "This request requires a different approver from the person who raised it")

    updated = await db[COLLECTION].find_one_and_update(
        {"id": approval_id, "tenant_id": tenant_id, "status": status},
        {"$set": {"status": decision, "decided_by": actor, "decided_at": _iso(_now()),
                  "decision_rationale": (str(rationale)[:2000] if rationale else None)},
         "$unset": {"active_dedupe_key": ""},
         "$push": {"history": _history(decision, actor, {"rationale": rationale})}},
        return_document=True,
    )
    if not updated:
        # Someone decided it between our read and our write.
        raise InvalidApprovalTransition("Approval request was decided concurrently")
    return _public(updated)


async def cancel(db, *, tenant_id: str, approval_id: str, actor: str,
                 reason: Optional[str] = None) -> dict:
    """Withdraw an undecided request — the situation changed, or the candidate resolved."""
    doc = await db[COLLECTION].find_one({"id": approval_id, "tenant_id": tenant_id})
    if not doc:
        raise ApprovalNotFound("Approval request not found")
    status = doc.get("status", REQUESTED)
    if status in CLOSED_STATUSES:
        raise InvalidApprovalTransition(f"Approval request is already '{status}'")

    updated = await db[COLLECTION].find_one_and_update(
        {"id": approval_id, "tenant_id": tenant_id, "status": status},
        {"$set": {"status": CANCELLED, "cancelled_at": _iso(_now()), "cancelled_by": actor},
         "$unset": {"active_dedupe_key": ""},
         "$push": {"history": _history("cancelled", actor, {"reason": reason})}},
        return_document=True,
    )
    if not updated:
        raise InvalidApprovalTransition("Approval request changed concurrently")
    return _public(updated)


async def consume(db, *, tenant_id: str, approval_id: str, actor: str) -> dict:
    """Claim an approved request for exactly one execution.

    This is the property that makes the gate real rather than decorative: the flip from
    `pending` to `consumed` is a single conditional update, so concurrent workers cannot
    both act on one approval. The caller executes only if this returns.
    """
    doc = await db[COLLECTION].find_one({"id": approval_id, "tenant_id": tenant_id})
    if not doc:
        raise ApprovalNotFound("Approval request not found")
    if doc.get("status") != APPROVED:
        raise InvalidApprovalTransition(
            f"Approval request is '{doc.get('status')}', not '{APPROVED}'")

    blocked = doc.get("blocked_reasons") or []
    if blocked:
        # Approving an action does not unblock a missing prerequisite. A channel that
        # was never authorised is still not authorised.
        raise InvalidApprovalTransition(
            "Approved, but the action is still blocked: " + "; ".join(str(b) for b in blocked))

    execution = doc.get("execution") or {}
    if execution.get("state") == EXECUTION_NOT_APPLICABLE:
        raise InvalidApprovalTransition("This approval carries no bound action to execute")

    updated = await db[COLLECTION].find_one_and_update(
        {"id": approval_id, "tenant_id": tenant_id, "status": APPROVED,
         "execution.state": EXECUTION_PENDING},
        {"$set": {"execution.state": EXECUTION_CONSUMED,
                  "execution.consumed_at": _iso(_now()),
                  "execution.consumed_by": actor},
         "$push": {"history": _history("consumed", actor, {})}},
        return_document=True,
    )
    if not updated:
        raise InvalidApprovalTransition("Approval has already been used for an execution")
    return _public(updated)


async def refresh_blocks(db, *, tenant_id: str, approval_id: str,
                         blocked_reasons: list, actor: str) -> dict:
    """Re-record what currently blocks an approved or pending request.

    `blocked_reasons` is a snapshot of conditions that can legitimately change — a channel
    gets authorised, consent gets recorded, a provider gets registered. Leaving the
    original snapshot in place would make a resolved block refuse forever, so the caller
    that re-checks those conditions live writes the result back here before consuming.

    This never changes status, so it cannot revive a rejected, cancelled or lapsed
    request; and it is recorded in the history, so a block that disappeared is visible
    rather than silent.
    """
    doc = await db[COLLECTION].find_one({"id": approval_id, "tenant_id": tenant_id})
    if not doc:
        raise ApprovalNotFound("Approval request not found")
    if doc.get("status") not in (REQUESTED, APPROVED):
        raise InvalidApprovalTransition(
            f"Cannot refresh blocks on a '{doc.get('status')}' request")

    current = list(doc.get("blocked_reasons") or [])
    incoming = [str(reason) for reason in (blocked_reasons or [])]
    if current == incoming:
        return _public(doc)

    updated = await db[COLLECTION].find_one_and_update(
        {"id": approval_id, "tenant_id": tenant_id, "status": doc["status"]},
        {"$set": {"blocked_reasons": incoming},
         "$push": {"history": _history("blocks_refreshed", actor,
                                       {"was": current, "now": incoming})}},
        return_document=True,
    )
    if not updated:
        raise InvalidApprovalTransition("Approval request changed concurrently")
    return _public(updated)


async def expire_due(db, *, tenant_id: Optional[str] = None, limit: int = 500) -> dict:
    """Sweep lapsed requests. Safe to run repeatedly; it only ever closes open requests."""
    criteria: dict[str, Any] = {"status": REQUESTED, "expires_at": {"$lte": _iso(_now())}}
    if tenant_id:
        criteria["tenant_id"] = tenant_id
    docs = await db[COLLECTION].find(criteria, {"_id": 0}).to_list(int(limit))
    expired = 0
    for doc in docs:
        if await _mark_expired(db, doc):
            expired += 1
    return {"examined": len(docs), "expired": expired}


async def summary(db, tenant_id: str) -> dict:
    """Counts for the operator surface: what is waiting, and how risky is it."""
    by_status: dict[str, int] = {}
    async for row in db[COLLECTION].aggregate([
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]):
        by_status[row["_id"] or REQUESTED] = row["count"]

    by_risk: dict[str, int] = {}
    async for row in db[COLLECTION].aggregate([
        {"$match": {"tenant_id": tenant_id, "status": {"$in": list(OPEN_STATUSES)}}},
        {"$group": {"_id": "$risk", "count": {"$sum": 1}}},
    ]):
        by_risk[row["_id"] or RISK_MEDIUM] = row["count"]

    awaiting = await db[COLLECTION].count_documents(
        {"tenant_id": tenant_id, "status": {"$in": list(OPEN_STATUSES)}})
    blocked = await db[COLLECTION].count_documents(
        {"tenant_id": tenant_id, "status": {"$in": list(OPEN_STATUSES)},
         "blocked_reasons.0": {"$exists": True}})
    ready = await db[COLLECTION].count_documents(
        {"tenant_id": tenant_id, "status": APPROVED, "execution.state": EXECUTION_PENDING})

    return {
        "tenant_id": tenant_id,
        "awaiting_decision": awaiting,
        "awaiting_decision_blocked": blocked,
        "approved_awaiting_execution": ready,
        "by_status": by_status,
        "by_risk": by_risk,
    }
