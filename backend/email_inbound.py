"""The return path: replies, bounces and outcomes coming back into CRM records.

The system could compose, approve and (with an adapter) send. What it could not do was
hear anything back. A reply landed in somebody's mailbox and the CRM went on believing
the last thing that happened was that a message went out. `conversations.record_inbound`
and `conversations.record_receipt` existed but nothing ever called them, so the loop was
open at exactly the point where a recovery case learns whether it worked.

This module closes it.

HOW A REPLY IS MATCHED, AND WHAT HAPPENS WHEN IT CANNOT BE

Matching is attempted strongest-evidence-first, and stops at the first answer:

1. **The provider thread.** The reply carries the same Gmail thread id as a conversation
   we already own. This is the provider's own assertion that these messages belong
   together.
2. **A reply header pointing at something we sent.** `In-Reply-To` / `References` name
   the deterministic `Message-ID` this system minted for an outbound dispatch. That is
   proof the counterparty was replying to us specifically.
3. **The sender's address against an open conversation's contact participant.** Weaker,
   so it is only accepted when exactly one open conversation with that contact exists.

An ambiguous match -- two candidate conversations, or a sender that maps to more than
one contact -- is **not** guessed at. It is recorded as unmatched, with the reason, for
a human to place. Attaching a client's reply to the wrong case is worse than leaving it
in a queue, and far worse than it looks: a recovery case that reads a stranger's "yes"
as its own outcome is how unearned credit gets claimed.

TENANCY

Every lookup is tenant-scoped, and a poll runs per tenant with that tenant's own
credentials. There is no path here that can associate a message with a tenant other than
the one whose mailbox produced it.

IDEMPOTENCY

Ingestion is keyed on the provider's message id, which `conversations` enforces with a
unique index. Replaying a poll, or a webhook that fires twice, records nothing twice.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Optional

import conversations as conversation_service

logger = logging.getLogger("clientverse.inbound")

UNMATCHED = "inbound_unmatched"
PROVIDER_GMAIL = "gmail"

# Addresses that carry delivery reports rather than a human reply.
BOUNCE_SENDERS = ("mailer-daemon@", "postmaster@")
# Read only on something already known to be a delivery report -- never on its own. A
# subject is the one field a client (or a case title quoted back in "Re: ...") controls.
FAILURE_SUBJECT_HINTS = ("failure", "failed", "undeliverable", "undelivered",
                         "returned mail", "returned to sender", "could not be delivered",
                         "rejected", "not delivered")
# Temporary: the provider will keep trying. Marking the message failed on one of these
# licenses a resend of something that may still arrive.
DELAY_SUBJECT_HINTS = ("delay", "delayed", "will retry", "delivery incomplete",
                       "temporar", "warning")

REPORT_BOUNCE = "bounce"
REPORT_DELAY = "delay"
REPORT_UNCLEAR = "unclear_report"

AUTO_REPLY_PRECEDENCE = ("auto_reply", "bulk", "junk", "list")

MATCH_THREAD = "provider_thread"
MATCH_REPLY_HEADER = "reply_header"
MATCH_CONTACT = "contact_address"
MATCH_NONE = "unmatched"

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
MESSAGE_ID_RE = re.compile(r"<([^>]+)>")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def ensure_indexes(db: Any) -> None:
    await db[UNMATCHED].create_index([("tenant_id", 1), ("provider", 1),
                                      ("provider_message_id", 1)], unique=True)
    await db[UNMATCHED].create_index([("tenant_id", 1), ("status", 1), ("received_at", -1)])


# ------------------------------------------------------------------ normalisation

def normalize(gmail_message: dict) -> dict:
    """Turn one Gmail message into the shape this module reasons about.

    Pure: no network, no database. Everything downstream is a decision about this dict,
    so it is the thing worth testing exhaustively.
    """
    payload = gmail_message.get("payload") or {}
    headers = {h.get("name", "").lower(): h.get("value", "")
               for h in (payload.get("headers") or [])}
    received_at = None
    if gmail_message.get("internalDate"):
        try:
            received_at = datetime.fromtimestamp(
                int(gmail_message["internalDate"]) / 1000, tz=timezone.utc).isoformat()
        except (TypeError, ValueError):
            received_at = None

    def addresses(value: Optional[str]) -> list[str]:
        return [match.lower() for match in EMAIL_RE.findall(value or "")]

    references = MESSAGE_ID_RE.findall(
        f"{headers.get('in-reply-to', '')} {headers.get('references', '')}")

    return {
        "provider": PROVIDER_GMAIL,
        "provider_message_id": gmail_message.get("id"),
        "thread_id": gmail_message.get("threadId"),
        "subject": headers.get("subject") or "(no subject)",
        "from_address": next(iter(addresses(headers.get("from"))), None),
        "to": addresses(headers.get("to")) + addresses(headers.get("cc")),
        "in_reply_to": [ref.strip().lower() for ref in references],
        "body": gmail_message.get("snippet") or "",
        "received_at": received_at or _now_iso(),
        "labels": gmail_message.get("labelIds") or [],
        "failed_recipients": addresses(headers.get("x-failed-recipients")),
        "content_type": (headers.get("content-type") or "").lower(),
        "auto_reply": _is_auto_reply(headers),
    }


def _is_auto_reply(headers: dict) -> bool:
    """An out-of-office or other machine reply (RFC 3834 and the common variants).

    Recorded as a reply it would stop follow-up and engage the case on a message no
    person wrote.
    """
    auto_submitted = (headers.get("auto-submitted") or "").strip().lower()
    if auto_submitted and auto_submitted != "no":
        return True
    if (headers.get("precedence") or "").strip().lower() in AUTO_REPLY_PRECEDENCE:
        return True
    return bool(headers.get("x-autoreply") or headers.get("x-autorespond"))


def classify_report(record: dict) -> Optional[str]:
    """None for an ordinary message; otherwise what kind of delivery report it is.

    Two mistakes are possible and both are expensive. A bounce read as a reply tells a
    case the client engaged when the message never arrived. A reply -- or a temporary
    delay notice -- read as a bounce marks a delivered message failed, which invites
    resending it. So a report is only a *bounce* on a permanent-failure signal, and
    nothing is a report on its subject alone.
    """
    if record.get("failed_recipients"):
        # Set by the rejecting mail server on a permanent failure.
        return REPORT_BOUNCE
    sender = (record.get("from_address") or "").lower()
    is_report = any(sender.startswith(prefix) for prefix in BOUNCE_SENDERS) or \
        "multipart/report" in (record.get("content_type") or "")
    if not is_report:
        return None
    subject = (record.get("subject") or "").lower()
    if any(hint in subject for hint in DELAY_SUBJECT_HINTS):
        return REPORT_DELAY
    if any(hint in subject for hint in FAILURE_SUBJECT_HINTS):
        return REPORT_BOUNCE
    return REPORT_UNCLEAR


def is_bounce(record: dict) -> bool:
    """Is this a permanent delivery failure (see `classify_report`)?"""
    return classify_report(record) == REPORT_BOUNCE


# ---------------------------------------------------------------------- matching

async def _sent_message_with_wire_id(db: Any, tenant_id: str, reference: str) -> Optional[dict]:
    """The outbound message this system sent under the given RFC 2822 Message-ID.

    Checked against the dedicated field first, and against the dispatch history second so
    messages sent before that field existed still match their own replies.
    """
    found: Optional[dict] = await db[conversation_service.MESSAGES].find_one(
        {"tenant_id": tenant_id,
         "$or": [{"rfc822_message_id": reference}, {"dispatch_message_id": reference}]},
        {"_id": 0})
    if found:
        return found
    fallback: Optional[dict] = await db[conversation_service.MESSAGES].find_one(
        {"tenant_id": tenant_id, "history.detail.rfc822_message_id": reference}, {"_id": 0})
    return fallback


async def match_conversation(db: Any, tenant_id: str, record: dict) -> dict:
    """Find the conversation this inbound message belongs to.

    Returns `{"conversation": doc|None, "basis": <MATCH_*>, "reason": str}`. The basis is
    kept because "which evidence placed this reply" is a question an operator will ask of
    any case whose outcome turns on it.
    """
    thread_id = record.get("thread_id")
    if thread_id:
        conversation = await db[conversation_service.CONVERSATIONS].find_one(
            {"tenant_id": tenant_id,
             "$or": [{"provider_thread_id": thread_id},
                     {"external_thread_id": thread_id}]}, {"_id": 0})
        if conversation:
            return {"conversation": conversation, "basis": MATCH_THREAD,
                    "reason": f"Provider thread {thread_id} is already tracked."}

    for reference in record.get("in_reply_to") or []:
        sent = await _sent_message_with_wire_id(db, tenant_id, reference)
        if not sent:
            continue
        conversation = await db[conversation_service.CONVERSATIONS].find_one(
            {"tenant_id": tenant_id, "id": sent["conversation_id"]}, {"_id": 0})
        if conversation:
            return {"conversation": conversation, "basis": MATCH_REPLY_HEADER,
                    "reason": f"Replies to message {sent['id']} that this system sent."}

    sender = (record.get("from_address") or "").lower()
    if sender:
        contacts = await db.contacts.find(
            {"tenant_id": tenant_id, "email": {"$regex": f"^{re.escape(sender)}$",
                                               "$options": "i"}},
            {"_id": 0, "id": 1}).to_list(5)
        if len(contacts) > 1:
            return {"conversation": None, "basis": MATCH_NONE,
                    "reason": (f"{len(contacts)} contacts share the address {sender}; "
                               "placing this reply would be a guess.")}
        if contacts:
            candidates = await db[conversation_service.CONVERSATIONS].find(
                {"tenant_id": tenant_id,
                 # An email can only belong to an email thread.
                 "channel": conversation_service.CHANNEL_EMAIL,
                 "$or": [{"contact_id": contacts[0]["id"]},
                         {"participants": {"$elemMatch": {
                             "kind": conversation_service.PARTICIPANT_CONTACT,
                             "id": contacts[0]["id"]}}}],
                 "status": {"$in": list(conversation_service.OPEN_CONVERSATION_STATUSES)}},
                {"_id": 0}).sort("last_activity_at", -1).to_list(5)
            if len(candidates) == 1:
                return {"conversation": candidates[0], "basis": MATCH_CONTACT,
                        "reason": f"Only open conversation with the contact at {sender}."}
            if len(candidates) > 1:
                return {"conversation": None, "basis": MATCH_NONE,
                        "reason": (f"{len(candidates)} open conversations with {sender}; "
                                   "the right one cannot be determined from the reply.")}
    return {"conversation": None, "basis": MATCH_NONE,
            "reason": (f"Nothing links this message to a tracked conversation "
                       f"(sender: {sender or 'unknown'}).")}


# --------------------------------------------------------------------- ingestion

async def record_unmatched(db: Any, tenant_id: str, record: dict, reason: str) -> dict:
    """Park a message that could not be safely placed.

    Unmatched is a queue, not a bin: it keeps the message, the reason it could not be
    placed, and everything needed to place it by hand.
    """
    doc = {
        "id": f"inb_{(record.get('provider_message_id') or '')[:24] or _now_iso()}",
        "tenant_id": tenant_id,
        "provider": record.get("provider"),
        "provider_message_id": record.get("provider_message_id"),
        "thread_id": record.get("thread_id"),
        "from_address": record.get("from_address"),
        "subject": record.get("subject"),
        "body": record.get("body"),
        "received_at": record.get("received_at"),
        "reason": reason,
        "status": "open",
        "created_at": _now_iso(),
    }
    try:
        await db[UNMATCHED].insert_one(dict(doc))
    except Exception as exc:
        if conversation_service._is_duplicate_key(exc):
            return {**doc, "deduplicated": True}
        raise
    return {**doc, "deduplicated": False}


async def ingest(db: Any, *, tenant_id: str, record: dict,
                 on_reply: Optional[Callable[..., Any]] = None) -> dict:
    """Record one inbound message against the CRM.

    Bounces become delivery evidence on the message they refer to. Replies become
    inbound messages on their conversation. Anything that cannot be placed with evidence
    is parked, never guessed.
    """
    provider_message_id = record.get("provider_message_id")
    if not provider_message_id:
        return {"outcome": "ignored", "reason": "message carried no provider id"}
    labels = set(record.get("labels") or [])
    if labels & {"SENT", "DRAFT"}:
        # Our own mail. An outbound stuck in `outcome_unknown` has no provider id yet, so
        # the unique index could not stop it being recorded as the client's reply.
        return {"outcome": "ignored", "reason": "the tenant's own sent or draft mail"}

    # Already recorded on an earlier poll: never match it again (a second match could
    # place it somewhere else), but finish anything the first pass did not.
    existing = await db[conversation_service.MESSAGES].find_one(
        {"tenant_id": tenant_id, "provider": record.get("provider"),
         "provider_message_id": provider_message_id}, {"_id": 0})
    if existing:
        if (on_reply and existing.get("direction") == conversation_service.INBOUND
                and not existing.get("reply_effects_applied_at")):
            conversation = await conversation_service.get_conversation(
                db, tenant_id, existing["conversation_id"])
            if conversation:
                await _apply_reply_effects(db, tenant_id, conversation, existing, record,
                                           "replay", on_reply)
        return {"outcome": "reply", "conversation_id": existing.get("conversation_id"),
                "message_id": existing["id"], "deduplicated": True}

    report = classify_report(record)
    if report == REPORT_BOUNCE:
        return await _ingest_bounce(db, tenant_id, record)
    if report == REPORT_DELAY:
        return {"outcome": "ignored", "reason": "a temporary delay notice; delivery continues"}
    if report == REPORT_UNCLEAR:
        parked = await record_unmatched(
            db, tenant_id, record,
            "A delivery report with no permanent-failure signal; a person should read it.")
        return {"outcome": "unmatched", "reason": parked["reason"],
                "deduplicated": parked.get("deduplicated", False)}
    if record.get("auto_reply"):
        return {"outcome": "ignored", "reason": "an automatic reply, not a person"}

    match = await match_conversation(db, tenant_id, record)
    conversation = match["conversation"]
    if not conversation:
        parked = await record_unmatched(db, tenant_id, record, match["reason"])
        return {"outcome": "unmatched", "reason": match["reason"],
                "deduplicated": parked.get("deduplicated", False)}

    message = await conversation_service.record_inbound(
        db, tenant_id=tenant_id, conversation_id=conversation["id"],
        body=record.get("body") or "", from_address=record.get("from_address"),
        subject=record.get("subject"), provider=record.get("provider"),
        provider_message_id=provider_message_id, received_at=record.get("received_at"))

    if (not message.get("deduplicated") and record.get("thread_id")
            and match["basis"] in (MATCH_THREAD, MATCH_REPLY_HEADER)
            and not conversation.get("provider_thread_id")):
        # Learn the provider thread from the first reply, so later messages in it match
        # on the strongest evidence rather than the weakest. Only from a strong match: a
        # thread learned from a sender-address guess would make an unrelated thread
        # this conversation's -- and send the next recovery email into it.
        await db[conversation_service.CONVERSATIONS].update_one(
            {"id": conversation["id"], "tenant_id": tenant_id},
            {"$set": {"provider_thread_id": record["thread_id"]}})

    # A reply parked on an earlier poll that now places with evidence leaves the queue.
    await db[UNMATCHED].update_many(
        {"tenant_id": tenant_id, "provider": record.get("provider"),
         "provider_message_id": provider_message_id, "status": "open"},
        {"$set": {"status": "assigned", "assigned_to_conversation": conversation["id"],
                  "assigned_by": "inbound-sweep", "assigned_at": _now_iso(),
                  "match_basis": match["basis"]}})

    if on_reply and not message.get("deduplicated"):
        await _apply_reply_effects(db, tenant_id, conversation, message, record,
                                   match["basis"], on_reply)

    return {"outcome": "reply", "basis": match["basis"], "reason": match["reason"],
            "conversation_id": conversation["id"], "message_id": message["id"],
            "deduplicated": bool(message.get("deduplicated"))}


async def _apply_reply_effects(db: Any, tenant_id: str, conversation: dict, message: dict,
                               record: dict, basis: str,
                               on_reply: Callable[..., Any]) -> None:
    """Run what a reply changes outside its conversation, and record that it ran.

    The message is stored before this runs, so a failure here used to be permanent: the
    next poll saw a duplicate and skipped it, and the case never learned of the reply.
    Now the next poll finishes the job.
    """
    await on_reply(tenant_id=tenant_id, conversation=conversation, message=message,
                   record=record, basis=basis)
    await db[conversation_service.MESSAGES].update_one(
        {"tenant_id": tenant_id, "id": message["id"]},
        {"$set": {"reply_effects_applied_at": _now_iso()}})


async def _ingest_bounce(db: Any, tenant_id: str, record: dict) -> dict:
    """Apply a delivery report to the outbound message it refers to.

    A bounce that cannot be tied to a specific message is parked rather than applied to
    a guess: marking the wrong message undelivered would invite a resend to someone who
    did receive it.
    """
    for reference in record.get("in_reply_to") or []:
        sent = await _sent_message_with_wire_id(db, tenant_id, reference)
        if not sent or not sent.get("provider_message_id"):
            continue
        try:
            await conversation_service.record_receipt(
                db, tenant_id=tenant_id, provider=sent.get("provider") or PROVIDER_GMAIL,
                provider_message_id=sent["provider_message_id"],
                status=conversation_service.FAILED,
                detail={"error": "Provider returned a delivery failure",
                        "bounce_message_id": record.get("provider_message_id"),
                        "failed_recipients": record.get("failed_recipients")})
        except conversation_service.MessageNotFound:
            continue
        except conversation_service.InvalidMessageTransition:
            # Already terminal; the bounce adds nothing it does not already know.
            return {"outcome": "bounce", "message_id": sent["id"], "applied": False}
        return {"outcome": "bounce", "message_id": sent["id"], "applied": True}

    parked = await record_unmatched(
        db, tenant_id, record,
        "Delivery report does not reference a message this system sent.")
    return {"outcome": "unmatched", "reason": parked["reason"],
            "deduplicated": parked.get("deduplicated", False)}


# ------------------------------------------------------------------------- polling

async def poll_tenant(db: Any, *, tenant_id: str, fetch_messages: Callable[..., Any],
                      on_reply: Optional[Callable[..., Any]] = None,
                      limit: int = 50) -> dict:
    """Ingest recent inbound mail for one tenant.

    `fetch_messages` is injected so this is testable without a network and so the
    transport (a poll now, a Pub/Sub push later) is not baked into the logic. Failures
    on one message do not abandon the rest: a single unparseable mail must not stop a
    reply from reaching the case that is waiting for it.
    """
    summary: dict[str, Any] = {"tenant_id": tenant_id, "fetched": 0, "replies": 0,
                               "bounces": 0, "unmatched": 0, "duplicates": 0,
                               "ignored": 0, "errors": 0}
    try:
        raw_messages = await fetch_messages(tenant_id=tenant_id, limit=limit)
    except Exception as exc:
        summary["errors"] += 1
        summary["error"] = str(exc)[:300]
        return summary

    for raw in raw_messages or []:
        summary["fetched"] += 1
        try:
            result = await ingest(db, tenant_id=tenant_id, record=normalize(raw),
                                  on_reply=on_reply)
        except Exception:
            logger.exception("Failed to ingest an inbound message for %s", tenant_id)
            summary["errors"] += 1
            continue
        if result.get("deduplicated"):
            summary["duplicates"] += 1
            continue
        outcome = result.get("outcome")
        if outcome == "reply":
            summary["replies"] += 1
        elif outcome == "bounce":
            summary["bounces"] += 1
        elif outcome == "unmatched":
            summary["unmatched"] += 1
        elif outcome == "ignored":
            summary["ignored"] += 1
    return summary


async def list_unmatched(db: Any, tenant_id: str, *, status: str = "open",
                         limit: int = 100) -> list[dict]:
    query: dict[str, Any] = {"tenant_id": tenant_id}
    if status:
        query["status"] = status
    rows: list[dict] = await db[UNMATCHED].find(query, {"_id": 0}).sort(
        "received_at", -1).to_list(max(1, min(int(limit or 100), 500)))
    return rows


async def assign_unmatched(db: Any, *, tenant_id: str, inbound_id: str, conversation_id: str,
                           actor: str) -> dict:
    """Place a parked message by hand, on a person's judgement rather than a guess."""
    parked = await db[UNMATCHED].find_one(
        {"tenant_id": tenant_id, "id": inbound_id, "status": "open"}, {"_id": 0})
    if not parked:
        raise conversation_service.MessageNotFound("No open unmatched message with that id")
    conversation = await conversation_service.get_conversation(db, tenant_id, conversation_id)
    if not conversation:
        raise conversation_service.ConversationNotFound("Conversation not found")

    message = await conversation_service.record_inbound(
        db, tenant_id=tenant_id, conversation_id=conversation_id,
        body=parked.get("body") or "", from_address=parked.get("from_address"),
        subject=parked.get("subject"), provider=parked.get("provider"),
        provider_message_id=parked.get("provider_message_id"),
        received_at=parked.get("received_at"))
    await db[UNMATCHED].update_one(
        {"tenant_id": tenant_id, "id": inbound_id},
        {"$set": {"status": "assigned", "assigned_to_conversation": conversation_id,
                  "assigned_by": actor, "assigned_at": _now_iso(),
                  # The basis is recorded as what it is: a person decided, not evidence.
                  "match_basis": "manual"}})
    return {"ok": True, "conversation_id": conversation_id, "message_id": message["id"]}
