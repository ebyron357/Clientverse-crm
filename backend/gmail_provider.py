"""Gmail as an outbound email channel.

Until now nothing in this repository implemented `ChannelProvider`, so every outbound
attempt refused with `no_provider_registered`. That refusal was honest -- the system
could compose and approve a message but had no way to send one -- and it is the last
thing standing between a drafted recovery message and a client actually receiving it.

This adapter plugs into the existing delivery choke point rather than around it. It does
not decide whether a message may be sent: `attempt_delivery` has already established
that the channel is authorised for the tenant, that consent was granted, that an
approval exists, and that the approval binds these exact words. By the time `send` is
called the only remaining question is whether Gmail accepts the message.

IDEMPOTENCY, WHICH GMAIL DOES NOT GIVE US

The Gmail API has no idempotency key. A retried dispatch would ordinarily deliver a
second copy to a client, which is the single worst failure this subsystem can have. So
the adapter manufactures one:

* Every dispatch carries a deterministic RFC 2822 `Message-ID` derived from the
  dispatch key that `conversations.dispatch_key` produced for this message and attempt.
* Before sending, the adapter asks Gmail whether it already holds a message with that
  id (`rfc822msgid:` search). If it does, the send is not repeated -- the existing
  provider message id is returned and the message is recorded as sent, once.
* The same lookup answers the reconciliation question for a message stranded in
  `outcome_unknown`: does the provider hold it or not.

The residual risk is stated rather than hidden: a provider that rewrote the supplied
`Message-ID` would defeat the lookup. Gmail preserves a caller-supplied `Message-ID` on
`messages.send`, and the adapter records the id it searched for alongside the id Gmail
returned so a mismatch is visible in the message history rather than silent.

WHAT COUNTS AS A FAILURE

`DeliveryRejected` is raised only where Gmail proved it did not accept the message: a
4xx that is not a rate limit, a missing or insufficient authorisation, a recipient the
message does not have. Everything else -- a timeout, a dropped connection, a 5xx, a
429 -- is left to raise, because from here those are indistinguishable from a message
Gmail accepted and then failed to acknowledge. The caller turns that into
`outcome_unknown`, which is a dead end until reconciliation, and that is the point.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from email.message import EmailMessage
from email.utils import format_datetime, formataddr
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

import httpx

import conversations as conversation_service

logger = logging.getLogger("clientverse.gmail")

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
MESSAGE_ID_DOMAIN = "clientverse.app"

# Gmail replies to a 4xx with a definite answer; these are the ones that mean "this
# message was not accepted and never will be in its current form".
PROVEN_REJECTION_CODES = {400, 401, 403, 404, 413, 422}


class GmailNotAuthorized(conversation_service.DeliveryRejected):
    """The tenant has no usable Gmail send authorisation.

    A rejection rather than an unknown outcome: nothing was dispatched, so a fresh
    attempt after the owner reconnects is safe.
    """


def message_id_for(tenant_id: str, idempotency_key: str) -> str:
    """The deterministic RFC 2822 Message-ID this dispatch will carry.

    Derived from the tenant and the dispatch key, so the same message and attempt always
    produces the same id and a different attempt never does. Hashed rather than
    concatenated so internal identifiers do not travel in a mail header.
    """
    digest = hashlib.sha256(f"{tenant_id}:{idempotency_key}".encode("utf-8")).hexdigest()[:40]
    return f"cv-{digest}@{MESSAGE_ID_DOMAIN}"


def _recipient(message: dict, conversation: dict) -> Optional[str]:
    """Who this message is actually addressed to.

    Prefers what the message itself carries, then the conversation's contact
    participant. Returns None rather than guessing: sending recovery outreach to an
    address nobody chose is worse than not sending it.
    """
    direct = (message.get("to_address") or "").strip()
    if direct:
        return direct
    for participant in conversation.get("participants") or []:
        if participant.get("kind") == conversation_service.PARTICIPANT_CONTACT:
            address = (participant.get("address") or participant.get("email") or "").strip()
            if address:
                return address
    return None


def build_mime(*, message: dict, conversation: dict, sender: Optional[str],
               recipient: str, message_id: str) -> str:
    """Render the approved message as a base64url-encoded RFC 2822 document.

    The body is used verbatim. Nothing is appended, reformatted or templated here: the
    text a human approved is the text that goes out, and the approval's fingerprint is
    checked against that same text at the choke point.
    """
    mail = EmailMessage()
    mail["To"] = recipient
    if sender:
        mail["From"] = formataddr(("", sender)) if "@" in sender else sender
    mail["Subject"] = (message.get("subject") or conversation.get("subject")
                       or "(no subject)")[:300]
    mail["Message-ID"] = f"<{message_id}>"
    mail["Date"] = format_datetime(datetime.now(timezone.utc))
    # A reply must thread, or the recipient sees an unrelated new mail and the
    # conversation this system is tracking is not the one they are having.
    in_reply_to = conversation.get("provider_last_message_id")
    if in_reply_to:
        mail["In-Reply-To"] = f"<{in_reply_to}>"
        mail["References"] = f"<{in_reply_to}>"
    mail.set_content(message.get("body") or "")
    return base64.urlsafe_b64encode(mail.as_bytes()).decode("ascii")


class GmailChannelProvider:
    """`ChannelProvider` for the email channel, backed by a tenant's Gmail connection.

    One adapter instance serves every tenant: the credentials are resolved per call from
    the `tenant_id` on the message, so a tenant that has not connected Gmail -- or has
    connected it without the send scope -- is refused rather than borrowing another
    tenant's authorisation.
    """

    channel = conversation_service.CHANNEL_EMAIL
    name = "gmail"

    def __init__(self, *,
                 access_token: Callable[..., Awaitable[Optional[str]]],
                 connection: Callable[[str], Awaitable[Optional[dict]]],
                 http_client: Optional[Callable[[], Any]] = None,
                 timeout: float = 25.0):
        self._access_token = access_token
        self._connection = connection
        self._http_client = http_client or (lambda: httpx.AsyncClient(timeout=timeout))

    # --------------------------------------------------------------- authorisation

    async def _authorized_token(self, tenant_id: str) -> tuple[str, Optional[str]]:
        """Return a usable access token and the connected mailbox, or refuse.

        Fails closed on every missing piece, and says which piece: an operator who has
        to reconnect needs to know whether the problem is the connection, the scope, or
        the token.
        """
        connection = await self._connection(tenant_id)
        if not connection or str(connection.get("status") or "").lower() != "active":
            raise GmailNotAuthorized(
                "Gmail is not connected for this tenant, so no email can be sent.")
        scopes = set(connection.get("scopes") or [])
        if GMAIL_SEND_SCOPE not in scopes:
            raise GmailNotAuthorized(
                "The Gmail connection for this tenant is read-only: it does not hold "
                f"the {GMAIL_SEND_SCOPE} scope. Reconnect Google and grant send access.")
        try:
            token = await self._access_token(tenant_id)
        except Exception as exc:  # a refresh failure is a proven non-dispatch
            raise GmailNotAuthorized(f"Gmail authorisation could not be refreshed: {exc}")
        if not token:
            raise GmailNotAuthorized("Gmail holds no usable access token for this tenant.")
        return token, connection.get("account_identity")

    # ------------------------------------------------------------------- lookups

    async def locate(self, *, tenant_id: str, idempotency_key: str) -> Optional[str]:
        """Does Gmail already hold the message this dispatch would send?

        Answers the only question reconciliation is allowed to ask. A lookup that cannot
        be completed raises, because "I could not check" must never be recorded as "it
        is not there" -- that reading is what turns a stranded message into a duplicate.
        """
        token, _ = await self._authorized_token(tenant_id)
        return await self._find(token, message_id_for(tenant_id, idempotency_key))

    async def _find(self, token: str, message_id: str) -> Optional[str]:
        async with self._http_client() as client:
            response = await client.get(
                f"{GMAIL_API}/messages",
                params={"q": f"rfc822msgid:{message_id}", "maxResults": 1},
                headers={"Authorization": f"Bearer {token}"})
        if response.status_code in PROVEN_REJECTION_CODES:
            raise GmailNotAuthorized(
                f"Gmail refused the lookup with HTTP {response.status_code}.")
        if response.status_code != 200:
            # Ambiguous: let it propagate so the caller does not read a failed lookup
            # as a definite "not sent".
            raise RuntimeError(f"Gmail lookup returned HTTP {response.status_code}")
        messages = (response.json() or {}).get("messages") or []
        return messages[0].get("id") if messages else None

    # ---------------------------------------------------------------------- send

    async def send(self, *, message: dict, conversation: dict,
                   idempotency_key: str) -> conversation_service.DeliveryResult:
        tenant_id = message["tenant_id"]
        token, mailbox = await self._authorized_token(tenant_id)

        recipient = _recipient(message, conversation)
        if not recipient:
            raise conversation_service.DeliveryRejected(
                "This conversation has no email address to send to.")

        rfc_message_id = message_id_for(tenant_id, idempotency_key)

        # Idempotency, part one: if this exact dispatch already reached Gmail, do not
        # send it again. This is what makes a retry safe.
        existing = await self._find(token, rfc_message_id)
        if existing:
            logger.info("Gmail already holds dispatch %s; not sending again", rfc_message_id)
            return conversation_service.DeliveryResult(
                provider_message_id=existing,
                detail={"deduplicated": True, "rfc822_message_id": rfc_message_id,
                        "note": "Gmail already held this dispatch; it was not sent twice."})

        raw = build_mime(message=message, conversation=conversation, sender=mailbox,
                         recipient=recipient, message_id=rfc_message_id)
        payload: dict[str, Any] = {"raw": raw}
        # `provider_thread_id` is Gmail's own thread id, learned from a previous send or
        # reply. `external_thread_id` is this system's internal thread key and is often a
        # synthetic value (a recovery case, for instance) -- sending that to Gmail as a
        # threadId would be rejected outright.
        if conversation.get("provider_thread_id"):
            payload["threadId"] = conversation["provider_thread_id"]

        async with self._http_client() as client:
            response = await client.post(
                f"{GMAIL_API}/messages/send", json=payload,
                headers={"Authorization": f"Bearer {token}"})

        if response.status_code in PROVEN_REJECTION_CODES:
            raise conversation_service.DeliveryRejected(
                f"Gmail rejected the message with HTTP {response.status_code}: "
                f"{response.text[:300]}")
        if response.status_code != 200:
            # 429 and 5xx included on purpose. Gmail may have accepted and failed to
            # tell us; the caller records that as an unknown outcome and refuses to
            # retry until it has been reconciled.
            raise RuntimeError(f"Gmail send returned HTTP {response.status_code}")

        body = response.json() or {}
        provider_message_id = body.get("id")
        if not provider_message_id:
            raise RuntimeError("Gmail accepted the send but returned no message id")
        return conversation_service.DeliveryResult(
            provider_message_id=provider_message_id,
            detail={"deduplicated": False, "rfc822_message_id": rfc_message_id,
                    "thread_id": body.get("threadId"), "mailbox": mailbox})
