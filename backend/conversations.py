"""Conversation and CommunicationMessage — the omnichannel foundation (§8 #1, #2).

The canonical governing document names these as the two items that block the most
expansion work: M-01 (email), M-02 (unified inbox), M-03 (SMS), E-09 (omnichannel) and
E-10 (human handoff) all wait on them, as does every outbound step the recovery strategy
composer currently marks blocked.

This module is deliberately **contract work, not channel work**. It needs no provider
credential, and it activates no channel. What it establishes:

* A tenant-scoped `Conversation` — a thread with participants, a channel, an assignment,
  a visible agent-versus-human boundary, and a per-channel consent record.
* A `CommunicationMessage` with an explicit state machine, so a message that was drafted,
  one that is waiting on an approval, and one that actually reached a provider are
  distinguishable states rather than a boolean.
* A provider-agnostic delivery interface: a registry, a protocol a provider implements,
  and one choke point every outbound message must pass through.

That choke point is the point of the module. Before anything is dispatched it checks, in
order: the message is dispatchable, the channel is authorised for this tenant, consent is
granted, an M-07 approval exists and is claimed for exactly this message, and a provider
is registered. Each failure is a named refusal recorded on the message. With no provider
registered and no channel authorised — which is the state of every tenant today — every
outbound attempt refuses, and the reason says which precondition failed.

Inbound and receipt paths exist too, so a provider adapter added later has somewhere to
deliver into rather than inventing its own storage.

One guarantee is deliberately *not* claimed: "the approval was consumed once" is not the
same statement as "the external communication happened once". A provider call that times
out after acceptance is indistinguishable here from one that was rejected, so the two are
separate states — `failed` for a rejection the provider proved, `outcome_unknown` for
everything else — and only the first is retryable. An unknown outcome is resolved by
reconciling against the provider, never by sending again.

Not in scope here: `crm_communications`, the read-only Gmail sync mirror. Folding it into
this model is follow-on work and is recorded as such in the canonical document.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol

import approval_queue
import recovery_strategy

CONVERSATIONS = "conversations"
MESSAGES = "communication_messages"

# ---------------------------------------------------------------- vocabulary

CHANNEL_INTERNAL = recovery_strategy.CHANNEL_INTERNAL
CHANNEL_EMAIL = recovery_strategy.CHANNEL_EMAIL
CHANNEL_SMS = recovery_strategy.CHANNEL_SMS
CHANNEL_PHONE = recovery_strategy.CHANNEL_PHONE
CHANNELS = (CHANNEL_INTERNAL, CHANNEL_EMAIL, CHANNEL_SMS, CHANNEL_PHONE)

STATUS_OPEN = "open"
STATUS_PENDING = "pending"        # waiting on the counterparty
STATUS_SNOOZED = "snoozed"
STATUS_CLOSED = "closed"
CONVERSATION_STATUSES = (STATUS_OPEN, STATUS_PENDING, STATUS_SNOOZED, STATUS_CLOSED)
OPEN_CONVERSATION_STATUSES = (STATUS_OPEN, STATUS_PENDING)

# The agent/human boundary E-10 requires to be visible rather than implied.
HANDLED_BY_HUMAN = "human"
HANDLED_BY_AGENT = "agent"
HANDLERS = (HANDLED_BY_HUMAN, HANDLED_BY_AGENT)

CONSENT_UNKNOWN = "unknown"
CONSENT_GRANTED = "granted"
CONSENT_DENIED = "denied"
CONSENT_WITHDRAWN = "withdrawn"
CONSENT_STATES = (CONSENT_UNKNOWN, CONSENT_GRANTED, CONSENT_DENIED, CONSENT_WITHDRAWN)

INBOUND = "inbound"
OUTBOUND = "outbound"
DIRECTIONS = (INBOUND, OUTBOUND)

PARTICIPANT_CONTACT = "contact"
PARTICIPANT_USER = "user"
PARTICIPANT_AGENT = "agent"
PARTICIPANT_KINDS = (PARTICIPANT_CONTACT, PARTICIPANT_USER, PARTICIPANT_AGENT)

# Message states. An outbound message walks left to right; a refusal lands in BLOCKED,
# from which it can be retried once the precondition that refused it is satisfied.
DRAFT = "draft"
PENDING_APPROVAL = "pending_approval"
APPROVED = "approved"
SENDING = "sending"
SENT = "sent"
DELIVERED = "delivered"
FAILED = "failed"
# The provider may or may not have accepted the message — a timeout or a dropped
# connection after dispatch looks exactly like a rejection from here, and treating the two
# alike is how a retry turns into a duplicate message to a client. `failed` means proven
# not sent; `outcome_unknown` means nobody knows yet, and it is deliberately a dead end
# until an adapter reconciles it against the provider.
OUTCOME_UNKNOWN = "outcome_unknown"
BLOCKED = "blocked"
RECEIVED = "received"
MESSAGE_STATES = (DRAFT, PENDING_APPROVAL, APPROVED, SENDING, SENT, DELIVERED, FAILED,
                  OUTCOME_UNKNOWN, BLOCKED, RECEIVED)

MESSAGE_TRANSITIONS = {
    DRAFT: {PENDING_APPROVAL, BLOCKED},
    # approved -> pending_approval is a re-request after the message body was edited:
    # an approval authorises the text that was approved, not a later rewrite of it.
    PENDING_APPROVAL: {APPROVED, BLOCKED, DRAFT},
    APPROVED: {SENDING, BLOCKED, PENDING_APPROVAL},
    SENDING: {SENT, FAILED, OUTCOME_UNKNOWN, BLOCKED},
    SENT: {DELIVERED, FAILED},
    DELIVERED: set(),
    FAILED: {PENDING_APPROVAL, DRAFT},
    # No path back to draft or approval. A message whose outcome is unknown can only be
    # resolved by reconciling it with the provider: to `sent` if the provider has it, to
    # `failed` if it proves it does not. Re-approving and resending from here is exactly
    # the duplicate this state exists to prevent.
    OUTCOME_UNKNOWN: {SENT, DELIVERED, FAILED},
    BLOCKED: {DRAFT, PENDING_APPROVAL},
    RECEIVED: set(),
}

# Named refusals. The operator needs to know which precondition stopped a send, not that
# "sending failed".
REFUSAL_NOT_DISPATCHABLE = "message_not_dispatchable"
REFUSAL_CHANNEL = "channel_not_authorized"
REFUSAL_CONSENT = "consent_not_granted"
REFUSAL_APPROVAL = "approval_missing_or_unusable"
REFUSAL_PROVIDER = "no_provider_registered"
REFUSAL_PROVIDER_ERROR = "provider_error"


class ConversationError(Exception):
    pass


class ConversationNotFound(ConversationError):
    pass


class MessageNotFound(ConversationError):
    pass


class InvalidMessageTransition(ConversationError):
    pass


class DeliveryRefused(ConversationError):
    """Raised when a precondition refuses dispatch. `reason` names which one."""

    def __init__(self, reason: str, detail: str):
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


class DeliveryRejected(ConversationError):
    """Raised by a provider that can prove it did not accept the message.

    A provider raises this only for a definite rejection it observed — a validation error,
    an authentication failure, a 4xx the provider returned. Anything else (a timeout, a
    dropped connection, an ambiguous 5xx) must **not** use it: the provider may already
    have accepted the message, and the caller has to treat that as an unknown outcome
    rather than a failure it can retry.
    """


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _history(action: str, actor: str, detail: Optional[dict] = None) -> dict:
    return {"action": action, "actor": actor, "at": _iso(_now()), "detail": detail or {}}


def _public(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    return {k: v for k, v in doc.items() if k != "_id"}


async def ensure_indexes(db) -> None:
    await db[CONVERSATIONS].create_index([("tenant_id", 1), ("status", 1), ("last_activity_at", -1)])
    await db[CONVERSATIONS].create_index([("tenant_id", 1), ("workspace_id", 1)])
    await db[CONVERSATIONS].create_index([("tenant_id", 1), ("contact_id", 1)])
    await db[CONVERSATIONS].create_index([("tenant_id", 1), ("recovery_case_id", 1)])
    await db[CONVERSATIONS].create_index([("tenant_id", 1), ("provider_thread_id", 1)])
    # One thread per external provider thread, so a provider adapter replaying a webhook
    # cannot fork a conversation in two.
    await db[CONVERSATIONS].create_index(
        [("tenant_id", 1), ("channel", 1), ("external_thread_id", 1)],
        unique=True,
        partialFilterExpression={"external_thread_id": {"$type": "string"}},
    )
    await db[MESSAGES].create_index([("tenant_id", 1), ("conversation_id", 1), ("created_at", 1)])
    await db[MESSAGES].create_index([("tenant_id", 1), ("status", 1)])
    await db[MESSAGES].create_index(
        [("tenant_id", 1), ("idempotency_key", 1)],
        unique=True,
        partialFilterExpression={"idempotency_key": {"$type": "string"}},
    )
    await db[MESSAGES].create_index(
        [("tenant_id", 1), ("provider", 1), ("provider_message_id", 1)],
        unique=True,
        partialFilterExpression={"provider_message_id": {"$type": "string"}},
    )
    # The on-the-wire id an inbound reply refers back to.
    await db[MESSAGES].create_index(
        [("tenant_id", 1), ("rfc822_message_id", 1)],
        partialFilterExpression={"rfc822_message_id": {"$type": "string"}},
    )


def body_fingerprint(body: str) -> str:
    """A stable fingerprint of the exact text a human approved.

    An approval authorises specific words, not a message slot. Recording the fingerprint
    when the approval is raised and re-checking it immediately before dispatch closes the
    gap between "this message was approved" and "these words were approved" -- which is
    the gap a rewrite between approval and send would otherwise walk through.
    """
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def _is_duplicate_key(exc: Exception) -> bool:
    return getattr(exc, "code", None) == 11000 or "E11000" in str(exc)


# ------------------------------------------------------------- provider layer

class DeliveryResult:
    """What a provider returns. `provider_message_id` is what a receipt later refers to."""

    def __init__(self, *, provider_message_id: str, status: str = SENT,
                 detail: Optional[dict] = None):
        self.provider_message_id = provider_message_id
        self.status = status
        self.detail = detail or {}


def dispatch_key(message: dict) -> str:
    """The idempotency key an adapter must hand to its provider.

    It is derived from the message id and its dispatch attempt, so a provider that
    supports idempotent sends collapses a retried dispatch of the same message rather than
    delivering it twice. The message's own `idempotency_key` protects local creation only;
    it says nothing about the provider's side effect.
    """
    attempts = len([h for h in (message.get("history") or []) if h.get("action") == SENDING])
    return f"{message['id']}:{max(1, attempts)}"


class ChannelProvider(Protocol):
    """What an email/SMS adapter must implement. Nothing in this repository implements it
    yet, which is why every outbound attempt refuses with `no_provider_registered`.

    `send` receives an `idempotency_key` and must pass it to the provider wherever the
    provider supports one. It may raise `DeliveryRejected` **only** when it can prove the
    provider did not accept the message; every other exception is treated as an unknown
    outcome, which is the safe reading.
    """

    channel: str
    name: str

    async def send(self, *, message: dict, conversation: dict,
                   idempotency_key: str) -> DeliveryResult:
        ...


class ProviderRegistry:
    """Per-channel provider lookup.

    Kept as an explicit object rather than a module global so a test can register a fake
    without leaking it into another test, and so the application's own registry is empty
    by construction rather than by convention.
    """

    def __init__(self):
        self._providers: dict[str, ChannelProvider] = {}

    def register(self, provider: ChannelProvider) -> None:
        if provider.channel not in CHANNELS:
            raise ConversationError(f"Unknown channel '{provider.channel}'")
        self._providers[provider.channel] = provider

    def unregister(self, channel: str) -> None:
        self._providers.pop(channel, None)

    def get(self, channel: str) -> Optional[ChannelProvider]:
        return self._providers.get(channel)

    def describe(self) -> list[dict]:
        return [{"channel": channel,
                 "provider": getattr(self._providers.get(channel), "name", None),
                 "registered": channel in self._providers}
                for channel in CHANNELS]


# The application's registry. It is empty, and that is the honest state: no provider
# adapter has been built or certified (M-01, M-03, O-01, O-06).
REGISTRY = ProviderRegistry()


# ------------------------------------------------------------- conversations

def _participant(entry: dict) -> dict:
    kind = entry.get("kind")
    if kind not in PARTICIPANT_KINDS:
        raise ConversationError(f"participant kind must be one of {PARTICIPANT_KINDS}")
    return {
        "kind": kind,
        "id": entry.get("id"),
        "address": entry.get("address"),
        "display_name": entry.get("display_name"),
    }


async def create_conversation(db, *, tenant_id: str, channel: str, actor: str,
                              subject: Optional[str] = None,
                              participants: Optional[list] = None,
                              workspace_id: Optional[str] = None,
                              company_id: Optional[str] = None,
                              contact_id: Optional[str] = None,
                              handled_by: str = HANDLED_BY_HUMAN,
                              assignee: Optional[str] = None,
                              external_thread_id: Optional[str] = None,
                              recovery_case_id: Optional[str] = None,
                              provider_thread_id: Optional[str] = None,
                              provider_last_message_id: Optional[str] = None) -> dict:
    if channel not in CHANNELS:
        raise ConversationError(f"channel must be one of {CHANNELS}")
    if handled_by not in HANDLERS:
        raise ConversationError(f"handled_by must be one of {HANDLERS}")

    now = _now()
    doc = {
        "id": f"cnv_{uuid.uuid4().hex[:12]}",
        "tenant_id": tenant_id,
        "channel": channel,
        "subject": (str(subject).strip()[:300] if subject else None),
        "status": STATUS_OPEN,
        "handled_by": handled_by,
        "assignee": assignee,
        "assigned_at": _iso(now) if assignee else None,
        "participants": [_participant(p) for p in (participants or [])],
        "workspace_id": workspace_id,
        "company_id": company_id,
        "contact_id": contact_id,
        # Which recovery case this thread belongs to, when it belongs to one. The
        # attribution ledger reads it to find what was actually sent on a case.
        "recovery_case_id": recovery_case_id,
        # Gmail's (or another provider's) own thread and last-message ids, learned from
        # traffic. Distinct from `external_thread_id`, which is this system's key.
        "provider_thread_id": provider_thread_id,
        "provider_last_message_id": provider_last_message_id,
        "external_thread_id": external_thread_id,
        # Consent is per conversation because it is per counterparty and per channel.
        # It starts unknown: no record means no permission, never assumed permission.
        "consent": {"state": CONSENT_UNKNOWN, "basis": None, "source": None,
                    "recorded_at": None, "recorded_by": None},
        "message_count": 0,
        "last_message_at": None,
        "last_direction": None,
        "last_activity_at": _iso(now),
        "snoozed_until": None,
        "created_at": _iso(now),
        "created_by": actor,
        "history": [_history("created", actor, {"channel": channel})],
    }
    try:
        await db[CONVERSATIONS].insert_one(dict(doc))
    except Exception as exc:
        if _is_duplicate_key(exc) and external_thread_id:
            existing = await db[CONVERSATIONS].find_one(
                {"tenant_id": tenant_id, "channel": channel,
                 "external_thread_id": external_thread_id})
            if existing:
                result = _public(existing)
                result["deduplicated"] = True
                return result
        raise
    result = _public(doc)
    result["deduplicated"] = False
    return result


async def get_conversation(db, tenant_id: str, conversation_id: str) -> Optional[dict]:
    return _public(await db[CONVERSATIONS].find_one(
        {"id": conversation_id, "tenant_id": tenant_id}))


async def find_conversation_by_external_thread(db, tenant_id: str, channel: str,
                                              external_thread_id: str) -> Optional[dict]:
    """The thread a provider (or a caller using its own key) already opened, if any."""
    return _public(await db[CONVERSATIONS].find_one(
        {"tenant_id": tenant_id, "channel": channel,
         "external_thread_id": external_thread_id}))


async def find_message_by_idempotency_key(db, tenant_id: str, key: str) -> Optional[dict]:
    """The message a previous attempt already drafted under this key, if any.

    A caller that wants to be re-runnable asks this before drafting, rather than relying
    on the unique index to reject the second write.
    """
    return _public(await db[MESSAGES].find_one(
        {"tenant_id": tenant_id, "idempotency_key": key}))


async def list_conversations(db, tenant_id: str, *, status: Optional[str] = "open",
                             channel: Optional[str] = None,
                             handled_by: Optional[str] = None,
                             assignee: Optional[str] = None,
                             workspace_id: Optional[str] = None,
                             limit: int = 100) -> list[dict]:
    criteria: dict[str, Any] = {"tenant_id": tenant_id}
    if status == "open":
        criteria["status"] = {"$in": list(OPEN_CONVERSATION_STATUSES)}
    elif status and status != "all":
        criteria["status"] = status
    if channel:
        criteria["channel"] = channel
    if handled_by:
        criteria["handled_by"] = handled_by
    if assignee:
        criteria["assignee"] = assignee
    if workspace_id:
        criteria["workspace_id"] = workspace_id
    docs = await db[CONVERSATIONS].find(criteria).sort("last_activity_at", -1).to_list(int(limit))
    return [_public(d) for d in docs]


async def _update_conversation(db, tenant_id: str, conversation_id: str, update: dict,
                               history: Optional[dict] = None) -> dict:
    ops: dict[str, Any] = {"$set": {**update, "last_activity_at": _iso(_now())}}
    if history:
        ops["$push"] = {"history": history}
    updated = await db[CONVERSATIONS].find_one_and_update(
        {"id": conversation_id, "tenant_id": tenant_id}, ops, return_document=True)
    if not updated:
        raise ConversationNotFound("Conversation not found")
    return _public(updated)


async def set_status(db, *, tenant_id: str, conversation_id: str, status: str, actor: str,
                     snooze_minutes: Optional[int] = None) -> dict:
    if status not in CONVERSATION_STATUSES:
        raise ConversationError(f"status must be one of {CONVERSATION_STATUSES}")
    update: dict[str, Any] = {"status": status}
    if status == STATUS_SNOOZED:
        minutes = int(snooze_minutes or 60)
        if minutes <= 0:
            raise ConversationError("snooze_minutes must be positive")
        update["snoozed_until"] = _iso(_now() + timedelta(minutes=minutes))
    else:
        update["snoozed_until"] = None
    if status == STATUS_CLOSED:
        update["closed_at"] = _iso(_now())
        update["closed_by"] = actor
    return await _update_conversation(db, tenant_id, conversation_id, update,
                                      _history(f"status:{status}", actor))


async def assign(db, *, tenant_id: str, conversation_id: str, assignee: Optional[str],
                 actor: str) -> dict:
    return await _update_conversation(
        db, tenant_id, conversation_id,
        {"assignee": assignee, "assigned_at": _iso(_now()) if assignee else None,
         "assigned_by": actor},
        _history("assigned", actor, {"assignee": assignee}))


async def handoff(db, *, tenant_id: str, conversation_id: str, to: str, actor: str,
                  assignee: Optional[str] = None, reason: Optional[str] = None) -> dict:
    """Move a conversation between agent and human handling (E-10).

    The boundary is a recorded state change with an actor and a reason, not an implicit
    consequence of somebody replying.
    """
    if to not in HANDLERS:
        raise ConversationError(f"handoff target must be one of {HANDLERS}")
    update: dict[str, Any] = {"handled_by": to}
    if to == HANDLED_BY_HUMAN:
        update["assignee"] = assignee
        update["assigned_at"] = _iso(_now()) if assignee else None
        update["status"] = STATUS_OPEN
    return await _update_conversation(
        db, tenant_id, conversation_id, update,
        _history(f"handoff:{to}", actor, {"assignee": assignee, "reason": reason}))


async def record_consent(db, *, tenant_id: str, conversation_id: str, state: str, actor: str,
                         basis: Optional[str] = None, source: Optional[str] = None) -> dict:
    """Record what the counterparty actually agreed to.

    `granted` requires a stated basis, because "we have consent" with no recorded reason is
    the claim this rule exists to prevent.
    """
    if state not in CONSENT_STATES:
        raise ConversationError(f"consent state must be one of {CONSENT_STATES}")
    if state == CONSENT_GRANTED and not str(basis or "").strip():
        raise ConversationError("Recording consent as granted requires a stated basis")
    consent = {"state": state, "basis": (str(basis).strip()[:500] if basis else None),
               "source": (str(source).strip()[:300] if source else None),
               "recorded_at": _iso(_now()), "recorded_by": actor}
    return await _update_conversation(db, tenant_id, conversation_id, {"consent": consent},
                                      _history(f"consent:{state}", actor, {"basis": basis}))


# ------------------------------------------------------------------ messages

async def draft_message(db, *, tenant_id: str, conversation_id: str, body: str, actor: str,
                        subject: Optional[str] = None, to_address: Optional[str] = None,
                        from_address: Optional[str] = None,
                        idempotency_key: Optional[str] = None,
                        requester_kind: str = approval_queue.REQUESTER_HUMAN) -> dict:
    """Compose an outbound message. Drafting is always allowed; sending is not."""
    conversation = await get_conversation(db, tenant_id, conversation_id)
    if not conversation:
        raise ConversationNotFound("Conversation not found")
    if not str(body or "").strip():
        raise ConversationError("body is required")

    now = _now()
    doc = {
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "tenant_id": tenant_id,
        "conversation_id": conversation_id,
        "channel": conversation["channel"],
        "direction": OUTBOUND,
        "status": DRAFT,
        "subject": (str(subject).strip()[:300] if subject else conversation.get("subject")),
        "body": str(body)[:20000],
        "from_address": from_address,
        "to_address": to_address,
        "author": actor,
        "author_kind": requester_kind,
        "approval_id": None,
        "provider": None,
        "provider_message_id": None,
        "provider_status": None,
        "blocked_reason": None,
        "blocked_detail": None,
        "error": None,
        "idempotency_key": idempotency_key,
        "created_at": _iso(now),
        "sent_at": None,
        "delivered_at": None,
        "history": [_history("drafted", actor, {})],
    }
    try:
        await db[MESSAGES].insert_one(dict(doc))
    except Exception as exc:
        if _is_duplicate_key(exc) and idempotency_key:
            existing = await db[MESSAGES].find_one(
                {"tenant_id": tenant_id, "idempotency_key": idempotency_key})
            if existing:
                result = _public(existing)
                result["deduplicated"] = True
                return result
        raise
    await _touch_conversation(db, tenant_id, conversation_id, direction=None)
    result = _public(doc)
    result["deduplicated"] = False
    return result


async def _touch_conversation(db, tenant_id: str, conversation_id: str, *,
                              direction: Optional[str], counted: bool = False) -> None:
    update: dict[str, Any] = {"last_activity_at": _iso(_now())}
    if direction:
        update["last_message_at"] = _iso(_now())
        update["last_direction"] = direction
    ops: dict[str, Any] = {"$set": update}
    if counted:
        ops["$inc"] = {"message_count": 1}
    await db[CONVERSATIONS].update_one({"id": conversation_id, "tenant_id": tenant_id}, ops)


async def get_message(db, tenant_id: str, message_id: str) -> Optional[dict]:
    return _public(await db[MESSAGES].find_one({"id": message_id, "tenant_id": tenant_id}))


async def list_messages(db, tenant_id: str, conversation_id: str, *,
                        limit: int = 200) -> list[dict]:
    docs = await db[MESSAGES].find(
        {"tenant_id": tenant_id, "conversation_id": conversation_id}
    ).sort("created_at", 1).to_list(int(limit))
    return [_public(d) for d in docs]


async def _transition(db, tenant_id: str, message: dict, target: str, actor: str,
                      extra: Optional[dict] = None,
                      detail: Optional[dict] = None) -> dict:
    current = message.get("status", DRAFT)
    if target not in MESSAGE_TRANSITIONS.get(current, set()):
        raise InvalidMessageTransition(f"Cannot move message from '{current}' to '{target}'")
    updated = await db[MESSAGES].find_one_and_update(
        {"id": message["id"], "tenant_id": tenant_id, "status": current},
        {"$set": {"status": target, **(extra or {})},
         "$push": {"history": _history(target, actor, detail)}},
        return_document=True)
    if not updated:
        raise InvalidMessageTransition("Message changed concurrently")
    return _public(updated)


async def request_approval(db, *, tenant_id: str, message_id: str, actor: str,
                           risk: str = approval_queue.RISK_MEDIUM,
                           expires_in_hours: Optional[int] = None,
                           registry: Optional["ProviderRegistry"] = None) -> dict:
    """Raise the M-07 approval an outbound message needs before it can be dispatched.

    The blocks that would refuse dispatch are computed now and recorded on the request, so
    an operator approving it can see that approval alone will not make it send.
    """
    message = await get_message(db, tenant_id, message_id)
    if not message:
        raise MessageNotFound("Message not found")
    conversation = await get_conversation(db, tenant_id, message["conversation_id"])
    if not conversation:
        raise ConversationNotFound("Conversation not found")

    blocked_reasons = await _preflight_blocks(db, tenant_id, message, conversation,
                                             registry=registry)
    approval = await approval_queue.request(
        db, tenant_id=tenant_id,
        title=f"Send {message['channel']} message: {message.get('subject') or 'no subject'}",
        kind="communication_message",
        actor=actor,
        requester_kind=message.get("author_kind") or approval_queue.REQUESTER_HUMAN,
        summary=message["body"][:500],
        risk=risk,
        action={"type": "communication_message.send", "message_id": message["id"],
                "conversation_id": conversation["id"], "channel": message["channel"],
                # The approval authorises these exact words. `attempt_delivery` re-checks
                # the fingerprint before it consumes the approval, so a body that changed
                # after a human read it cannot ride that human's decision.
                "body_sha256": body_fingerprint(message["body"])},
        subject_type="communication_message", subject_id=message["id"],
        workspace_id=conversation.get("workspace_id"),
        facts=[{"label": "Channel", "value": message["channel"],
                "source": f"conversation:{conversation['id']}"},
               {"label": "Consent", "value": (conversation.get("consent") or {}).get("state"),
                "source": f"conversation:{conversation['id']}"}],
        blocked_reasons=blocked_reasons,
        dedupe_key=f"communication_message:{message['id']}",
        expires_in_hours=expires_in_hours)

    updated = await _transition(db, tenant_id, message, PENDING_APPROVAL, actor,
                                extra={"approval_id": approval["id"]},
                                detail={"approval_id": approval["id"]})
    return updated


async def _preflight_blocks(db, tenant_id: str, message: dict, conversation: dict,
                            registry: Optional[ProviderRegistry] = None) -> list[str]:
    """Everything that would refuse this message right now, computed without changing it.

    This is a snapshot for the operator, not the gate. The gate is `attempt_delivery`,
    which re-checks each of these live immediately before dispatch — so a block recorded
    here and later resolved does not need to refuse forever.
    """
    registry = registry if registry is not None else REGISTRY
    blocks: list[str] = []
    channel = message["channel"]
    if channel != CHANNEL_INTERNAL:
        authority = await recovery_strategy.authorized_channels(db, tenant_id)
        verdict = authority.get(channel, {"authorized": False,
                                          "reason": f"Unknown channel '{channel}'."})
        if not verdict["authorized"]:
            blocks.append(verdict["reason"])
        consent = (conversation.get("consent") or {}).get("state")
        if consent != CONSENT_GRANTED:
            blocks.append(f"Consent for this conversation is '{consent}', not 'granted'.")
        if registry.get(channel) is None:
            blocks.append(f"No delivery provider is registered for {channel}.")
    return blocks


async def mark_approved(db, *, tenant_id: str, message_id: str, actor: str) -> dict:
    """Move a message to `approved` once its approval request was approved.

    Called by the approval decision hook; it verifies the approval rather than trusting
    the caller, so nothing can promote a message by asserting that it was approved.
    """
    message = await get_message(db, tenant_id, message_id)
    if not message:
        raise MessageNotFound("Message not found")
    approval_id = message.get("approval_id")
    if not approval_id:
        raise ConversationError("Message has no approval request")
    approval = await approval_queue.get(db, tenant_id, approval_id)
    if not approval or approval.get("status") != approval_queue.APPROVED:
        raise ConversationError("The message's approval request is not approved")
    return await _transition(db, tenant_id, message, APPROVED, actor,
                             detail={"approval_id": approval_id})


async def mark_refused(db, *, tenant_id: str, message_id: str, actor: str,
                       reason: str, detail: str) -> dict:
    message = await get_message(db, tenant_id, message_id)
    if not message:
        raise MessageNotFound("Message not found")
    return await _transition(db, tenant_id, message, BLOCKED, actor,
                             extra={"blocked_reason": reason, "blocked_detail": detail},
                             detail={"reason": reason, "detail": detail})


async def attempt_delivery(db, *, tenant_id: str, message_id: str, actor: str,
                           registry: Optional[ProviderRegistry] = None) -> dict:
    """The single choke point every outbound message passes through.

    Preconditions are checked in order and each failure is a named refusal recorded on the
    message. The approval is consumed **last**, immediately before the provider call: a
    refusal must not burn an approval. The residual risk is the narrow window between
    consuming and sending — a crash there loses the approval rather than sending twice,
    which is the safer of the two failures.
    """
    registry = registry if registry is not None else REGISTRY
    message = await get_message(db, tenant_id, message_id)
    if not message:
        raise MessageNotFound("Message not found")

    if message.get("direction") != OUTBOUND or message.get("status") != APPROVED:
        detail = (f"A message must be outbound and '{APPROVED}' to be dispatched; this one "
                  f"is '{message.get('status')}'.")
        # Record the refusal where the state machine allows it. A message that is already
        # terminal (delivered, received) is simply not dispatchable and is left alone.
        if BLOCKED in MESSAGE_TRANSITIONS.get(message.get("status"), set()):
            await mark_refused(db, tenant_id=tenant_id, message_id=message_id, actor=actor,
                               reason=REFUSAL_NOT_DISPATCHABLE, detail=detail)
        raise DeliveryRefused(REFUSAL_NOT_DISPATCHABLE, detail)

    conversation = await get_conversation(db, tenant_id, message["conversation_id"])
    if not conversation:
        raise ConversationNotFound("Conversation not found")

    channel = message["channel"]

    async def refuse(reason: str, detail: str):
        await mark_refused(db, tenant_id=tenant_id, message_id=message_id, actor=actor,
                           reason=reason, detail=detail)
        raise DeliveryRefused(reason, detail)

    if channel != CHANNEL_INTERNAL:
        authority = await recovery_strategy.authorized_channels(db, tenant_id)
        verdict = authority.get(channel, {"authorized": False,
                                          "reason": f"Unknown channel '{channel}'."})
        if not verdict["authorized"]:
            await refuse(REFUSAL_CHANNEL, verdict["reason"])

        consent = (conversation.get("consent") or {}).get("state")
        if consent != CONSENT_GRANTED:
            await refuse(REFUSAL_CONSENT,
                         f"Consent for this conversation is '{consent}', not 'granted'.")

        if registry.get(channel) is None:
            await refuse(REFUSAL_PROVIDER,
                         f"No delivery provider is registered for {channel}.")

    approval_id = message.get("approval_id")
    if not approval_id:
        await refuse(REFUSAL_APPROVAL, "The message carries no approval request.")

    approval = await approval_queue.get(db, tenant_id, approval_id)
    approved_fingerprint = ((approval or {}).get("action") or {}).get("body_sha256")
    if approved_fingerprint and approved_fingerprint != body_fingerprint(message["body"]):
        # The words that were approved are not the words about to be sent.
        await refuse(REFUSAL_APPROVAL,
                     "The message body changed after it was approved; it must be "
                     "re-approved before it can be sent.")

    # Every precondition above was just re-checked live and passed. The blocks recorded on
    # the approval when it was raised are a snapshot of conditions that have since changed,
    # so write the current answer back before consuming — otherwise a block that has been
    # resolved would refuse the send forever.
    try:
        await approval_queue.refresh_blocks(
            db, tenant_id=tenant_id, approval_id=approval_id,
            blocked_reasons=await _preflight_blocks(db, tenant_id, message, conversation,
                                                    registry=registry),
            actor=actor)
    except approval_queue.ApprovalError as exc:
        await refuse(REFUSAL_APPROVAL, str(exc)[:300])

    try:
        # Bind the claim to this exact message, so an approval for one message can never
        # be spent sending another.
        await approval_queue.consume(
            db, tenant_id=tenant_id, approval_id=approval_id, actor=actor,
            expected_action={"type": "communication_message.send", "message_id": message_id})
    except approval_queue.ApprovalError as exc:
        await refuse(REFUSAL_APPROVAL, str(exc)[:300])

    provider = registry.get(channel)
    sending = await _transition(db, tenant_id, message, SENDING, actor,
                                extra={"provider": getattr(provider, "name", "internal")})
    if channel == CHANNEL_INTERNAL:
        # An internal message has no provider and never leaves the CRM; it is delivered
        # the moment it is recorded.
        delivered = await _transition(db, tenant_id, sending, SENT, actor,
                                      extra={"sent_at": _iso(_now())})
        await _touch_conversation(db, tenant_id, conversation["id"], direction=OUTBOUND,
                                  counted=True)
        return delivered

    try:
        result = await provider.send(message=sending, conversation=conversation,
                                     idempotency_key=dispatch_key(sending))
    except DeliveryRejected as exc:
        # The provider proved it did not accept the message, so this is an ordinary
        # failure and a fresh attempt is safe.
        return await _transition(db, tenant_id, sending, FAILED, actor,
                                 extra={"error": str(exc)[:500]},
                                 detail={"reason": REFUSAL_PROVIDER_ERROR, "proven": True})
    except Exception as exc:
        # Anything else is ambiguous. A timeout or a dropped connection after the provider
        # accepted looks identical from here, so recording this as `failed` would invite a
        # retry that sends the client a second copy. `approval consumed once` is not the
        # same guarantee as `external communication happened once`, and this is where the
        # two come apart.
        return await _transition(db, tenant_id, sending, OUTCOME_UNKNOWN, actor,
                                 extra={"error": str(exc)[:500]},
                                 detail={"reason": REFUSAL_PROVIDER_ERROR, "proven": False})

    sent = await _transition(db, tenant_id, sending, SENT, actor,
                             extra={"provider_message_id": result.provider_message_id,
                                    "provider_status": result.status,
                                    # The id the message carried on the wire. A reply's
                                    # In-Reply-To header names this, so it is what the
                                    # inbound path matches on -- stored as a field of its
                                    # own rather than buried in a history entry.
                                    "rfc822_message_id": result.detail.get("rfc822_message_id"),
                                    "sent_at": _iso(_now())},
                             detail=result.detail)
    await _touch_conversation(db, tenant_id, conversation["id"], direction=OUTBOUND,
                              counted=True)
    # Learn the provider's own thread from the first successful send, so later messages
    # thread onto it and a reply can be matched on the provider's own assertion.
    provider_thread = (result.detail or {}).get("thread_id")
    updates = {}
    if provider_thread and not conversation.get("provider_thread_id"):
        updates["provider_thread_id"] = provider_thread
    if sent.get("rfc822_message_id"):
        updates["provider_last_message_id"] = sent["rfc822_message_id"]
    if updates:
        await db[CONVERSATIONS].update_one(
            {"id": conversation["id"], "tenant_id": tenant_id}, {"$set": updates})
    return sent


async def reconcile_unknown(db, *, tenant_id: str, message_id: str, actor: str,
                            found: bool, provider_message_id: Optional[str] = None,
                            detail: Optional[dict] = None) -> dict:
    """Resolve a message whose dispatch outcome was never observed.

    An adapter answers one question against the provider — does it hold this message? —
    and this records the answer. `found` moves it to `sent` with the provider's own id;
    not found moves it to `failed`, from which a fresh approval and a fresh attempt are
    safe. Nothing else may move a message out of `outcome_unknown`, which is what stops a
    lost response from becoming a second message to the client.
    """
    message = await get_message(db, tenant_id, message_id)
    if not message:
        raise MessageNotFound("Message not found")
    if message.get("status") != OUTCOME_UNKNOWN:
        raise InvalidMessageTransition(
            f"Only a message in '{OUTCOME_UNKNOWN}' can be reconciled; this one is "
            f"'{message.get('status')}'")
    if found and not provider_message_id:
        raise ConversationError(
            "Reconciling a message the provider holds requires its provider message id")

    if found:
        extra = {"provider_message_id": provider_message_id, "sent_at": _iso(_now()),
                 "error": None}
        if (detail or {}).get("rfc822_message_id"):
            extra["rfc822_message_id"] = detail["rfc822_message_id"]
        return await _transition(db, tenant_id, message, SENT, actor, extra=extra,
                                 detail={"reconciled": True, **(detail or {})})
    return await _transition(db, tenant_id, message, FAILED, actor,
                             extra={"error": "Provider confirmed it never accepted this message"},
                             detail={"reconciled": True, "proven": True, **(detail or {})})


async def record_receipt(db, *, tenant_id: str, provider: str, provider_message_id: str,
                         status: str, detail: Optional[dict] = None) -> dict:
    """Apply a provider delivery receipt to the message it refers to."""
    message = await db[MESSAGES].find_one(
        {"tenant_id": tenant_id, "provider": provider,
         "provider_message_id": provider_message_id})
    if not message:
        raise MessageNotFound("No message matches that provider message id")
    target = DELIVERED if status == DELIVERED else FAILED
    extra = {"provider_status": status}
    if target == DELIVERED:
        extra["delivered_at"] = _iso(_now())
    else:
        extra["error"] = (detail or {}).get("error", status)
    return await _transition(db, tenant_id, _public(message), target, f"provider:{provider}",
                             extra=extra, detail=detail)


async def record_inbound(db, *, tenant_id: str, conversation_id: str, body: str,
                         from_address: Optional[str] = None, subject: Optional[str] = None,
                         provider: Optional[str] = None,
                         provider_message_id: Optional[str] = None,
                         received_at: Optional[str] = None) -> dict:
    """Append a received message and reopen the conversation.

    Inbound never passes the outbound preconditions — receiving is not sending — but it
    does reopen a closed or snoozed thread, because a reply is exactly the event those
    states were waiting for.
    """
    conversation = await get_conversation(db, tenant_id, conversation_id)
    if not conversation:
        raise ConversationNotFound("Conversation not found")

    now = _now()
    doc = {
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "tenant_id": tenant_id,
        "conversation_id": conversation_id,
        "channel": conversation["channel"],
        "direction": INBOUND,
        "status": RECEIVED,
        "subject": subject or conversation.get("subject"),
        "body": str(body)[:20000],
        "from_address": from_address,
        "to_address": None,
        "author": from_address or "counterparty",
        "author_kind": PARTICIPANT_CONTACT,
        "approval_id": None,
        "provider": provider,
        "provider_message_id": provider_message_id,
        "provider_status": None,
        "blocked_reason": None,
        "blocked_detail": None,
        "error": None,
        "idempotency_key": None,
        "created_at": received_at or _iso(now),
        "sent_at": None,
        "delivered_at": received_at or _iso(now),
        "history": [_history("received", provider or "inbound", {})],
    }
    try:
        await db[MESSAGES].insert_one(dict(doc))
    except Exception as exc:
        if _is_duplicate_key(exc) and provider_message_id:
            existing = await db[MESSAGES].find_one(
                {"tenant_id": tenant_id, "provider": provider,
                 "provider_message_id": provider_message_id})
            if existing:
                result = _public(existing)
                result["deduplicated"] = True
                return result
        raise

    reopened = {"last_message_at": _iso(now), "last_direction": INBOUND,
                "last_activity_at": _iso(now), "snoozed_until": None}
    if conversation.get("status") in (STATUS_CLOSED, STATUS_SNOOZED, STATUS_PENDING):
        reopened["status"] = STATUS_OPEN
    await db[CONVERSATIONS].update_one(
        {"id": conversation_id, "tenant_id": tenant_id},
        {"$set": reopened, "$inc": {"message_count": 1},
         "$push": {"history": _history("inbound_received", provider or "inbound", {})}})

    result = _public(doc)
    result["deduplicated"] = False
    return result


async def summary(db, tenant_id: str) -> dict:
    by_status: dict[str, int] = {}
    async for row in db[CONVERSATIONS].aggregate([
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]):
        by_status[row["_id"] or STATUS_OPEN] = row["count"]

    by_channel: dict[str, int] = {}
    async for row in db[CONVERSATIONS].aggregate([
        {"$match": {"tenant_id": tenant_id, "status": {"$in": list(OPEN_CONVERSATION_STATUSES)}}},
        {"$group": {"_id": "$channel", "count": {"$sum": 1}}},
    ]):
        by_channel[row["_id"] or CHANNEL_INTERNAL] = row["count"]

    awaiting_approval = await db[MESSAGES].count_documents(
        {"tenant_id": tenant_id, "status": PENDING_APPROVAL})
    blocked = await db[MESSAGES].count_documents({"tenant_id": tenant_id, "status": BLOCKED})
    unknown = await db[MESSAGES].count_documents(
        {"tenant_id": tenant_id, "status": OUTCOME_UNKNOWN})
    agent_handled = await db[CONVERSATIONS].count_documents(
        {"tenant_id": tenant_id, "handled_by": HANDLED_BY_AGENT,
         "status": {"$in": list(OPEN_CONVERSATION_STATUSES)}})

    return {
        "tenant_id": tenant_id,
        "open_conversations": sum(by_status.get(s, 0) for s in OPEN_CONVERSATION_STATUSES),
        "agent_handled_open": agent_handled,
        "messages_awaiting_approval": awaiting_approval,
        "messages_blocked": blocked,
        "messages_outcome_unknown": unknown,
        "by_status": by_status,
        "by_channel": by_channel,
        "providers": REGISTRY.describe(),
    }
