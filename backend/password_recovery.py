"""Signed-out recovery. Database-backed limits, encrypted mail jobs, hashed grants.

No user lookup or provider call occurs on the request-email response path. A worker
claims each persisted job once. Ambiguous sends are not retried; request a new link.
The user password compare-and-swap is the single-use boundary, including when two
different grants race or a process dies before updating the grant's bookkeeping.
"""

import asyncio
import hashlib
import hmac
import logging
import os
import re
import secrets
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet
from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)
GENERIC_MESSAGE = "If an account can be recovered, you will receive an email with a reset link."
INVALID_LINK = "This reset link is invalid or has expired. Request a new link."
TOKEN_MINUTES = 20
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def private_key(kind: str, value: str) -> str:
    return hmac.new(os.environ["JWT_SECRET"].encode(), f"recovery:{kind}:{value}".encode(), hashlib.sha256).hexdigest()


def configuration() -> tuple[str, str, str, Fernet]:
    origin = os.environ.get("FRONTEND_URL", "").rstrip("/")
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment):
        raise ValueError("recovery_origin_unconfigured")
    key = os.environ.get("PASSWORD_RECOVERY_RESEND_API_KEY", "")
    sender = os.environ.get("PASSWORD_RECOVERY_FROM", "")
    if not key or not sender or "@" not in sender or "\n" in sender or "\r" in sender:
        raise ValueError("recovery_mail_unconfigured")
    cipher = Fernet(os.environ.get("INTEGRATION_ENC_KEY", "").encode())
    return origin, key, sender, cipher


async def send_mail(to: str, subject: str, text: str, message_id: str) -> None:
    _, key, sender, _ = configuration()
    # Fixed HTTPS endpoint; never log provider bodies, recipients, or the reset link.
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        response = await client.post("https://api.resend.com/emails", headers={
            "Authorization": f"Bearer {key}", "Idempotency-Key": message_id,
        }, json={"from": sender, "to": [to], "subject": subject, "text": text})
    if response.status_code not in (200, 201, 202):
        raise RuntimeError("recovery_delivery_failed")


class PasswordRecovery:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def ensure_indexes(self) -> None:
        # These are required, not best-effort: TTL bounds encrypted mail and audit retention.
        for collection in ("password_recovery_jobs", "password_recovery_grants", "password_recovery_limits",
                           "password_recovery_events"):
            await self.db[collection].create_index("expires_at", expireAfterSeconds=0)
        await self.db.password_recovery_grants.create_index("user_id")
        await self.db.password_recovery_jobs.create_index([("state", 1), ("created_at", 1)])

    async def audit(self, outcome: str, *, subject: Optional[str] = None,
                    user_id: Optional[str] = None, job_id: Optional[str] = None) -> None:
        await self.db.password_recovery_events.insert_one({
            "outcome": outcome, "subject": subject, "user_id": user_id, "job_id": job_id,
            "created_at": utcnow(), "expires_at": utcnow() + timedelta(days=90),
        })

    async def limited(self, scope: str, principal: str, maximum: int, seconds: int) -> bool:
        now = utcnow()
        window = int(now.timestamp()) // seconds
        key = f"{scope}:{private_key(scope, principal)}:{window}"
        try:
            row = await self.db.password_recovery_limits.find_one_and_update(
                {"_id": key}, {"$inc": {"count": 1}, "$setOnInsert": {
                    "expires_at": datetime.fromtimestamp((window + 2) * seconds, timezone.utc)}},
                upsert=True, return_document=ReturnDocument.AFTER)
        except DuplicateKeyError:
            row = await self.db.password_recovery_limits.find_one_and_update(
                {"_id": key}, {"$inc": {"count": 1}}, return_document=ReturnDocument.AFTER)
        return row is None or bool(row["count"] > maximum)

    async def request(self, email: str, ip: str) -> None:
        subject = private_key("email", email)
        # Same counters, queue write and response for existing/unknown/disabled accounts.
        if await self.limited("request_global", "all", 100, 3600):
            return
        if await self.limited("request_ip", ip, 20, 900):
            await self.audit("request_throttled", subject=subject)
            return
        if await self.limited("request_email", email, 3, 3600):
            await self.audit("request_throttled", subject=subject)
            return
        try:
            _, _, _, cipher = configuration()
        except (ValueError, KeyError):
            await self.audit("configuration_unavailable", subject=subject)
            logger.warning("Password recovery configuration unavailable")
            return
        job_id = uuid.uuid4().hex
        await self.db.password_recovery_jobs.insert_one({
            "_id": job_id, "recipient": cipher.encrypt(email.encode()).decode(),
            "subject": subject, "kind": "link", "state": "queued", "created_at": utcnow(),
            "expires_at": utcnow() + timedelta(minutes=TOKEN_MINUTES),
        })
        await self.audit("requested", subject=subject, job_id=job_id)

    async def deliver_one(self) -> bool:
        now = utcnow()
        # A crash during delivery is ambiguous. Do not automatically resend such jobs.
        await self.db.password_recovery_jobs.update_many(
            {"state": "sending", "started_at": {"$lt": now - timedelta(minutes=2)}},
            {"$set": {"state": "delivery_unknown"}, "$unset": {"recipient": ""}})
        job = await self.db.password_recovery_jobs.find_one_and_update(
            {"state": "queued", "expires_at": {"$gt": now}},
            {"$set": {"state": "sending", "started_at": now}},
            sort=[("created_at", 1)], return_document=ReturnDocument.AFTER)
        if not job:
            return False
        grant_id = None
        try:
            origin, _, _, cipher = configuration()
            email = cipher.decrypt(job["recipient"].encode()).decode()
            if job["kind"] == "confirmation":
                await send_mail(email, "Your ClientVerse password was changed",
                                "Your ClientVerse password was changed and previous sessions were ended. "
                                "If you did not make this change, recover your account immediately at "
                                f"{origin}/forgot-password and contact your workspace administrator.", job["_id"])
            else:
                user = await self.db.users.find_one({"email": email})
                # Never create accounts or change memberships through recovery.
                member = await self.db.memberships.find_one({"user_id": user["user_id"], "status": "active"}) if user else None
                if not user or not user.get("password_hash") or not member:
                    await self.audit("ineligible", subject=job["subject"], job_id=job["_id"])
                    return True
                changed_at = user.get("password_changed_at")
                queued_at = job["created_at"].replace(tzinfo=timezone.utc)
                if changed_at and datetime.fromisoformat(changed_at) > queued_at:
                    await self.audit("superseded", subject=job["subject"], job_id=job["_id"])
                    return True
                token = secrets.token_urlsafe(32)
                grant_id = digest(token)
                await self.db.password_recovery_grants.insert_one({
                    "_id": grant_id, "user_id": user["user_id"],
                    "password_fingerprint": digest(user["password_hash"]),
                    "email_fingerprint": digest(user["email"]),
                    "created_at": now, "expires_at": now + timedelta(minutes=TOKEN_MINUTES),
                })
                # Fragment never reaches HTTP access logs or Referer. The SPA removes it on load.
                await send_mail(email, "Reset your ClientVerse password",
                                f"Reset your password: {origin}/reset-password#token={token}\n\n"
                                f"This link expires in {TOKEN_MINUTES} minutes and works once. "
                                "If you did not request it, ignore this email; your password has not changed.", job["_id"])
            await self.audit("delivery_accepted", subject=job["subject"], job_id=job["_id"])
        except Exception:
            if grant_id:
                await self.db.password_recovery_grants.delete_one({"_id": grant_id})
            await self.audit("delivery_failed", subject=job["subject"], job_id=job["_id"])
            logger.warning("Password recovery delivery failed")
        finally:
            await self.db.password_recovery_jobs.update_one(
                {"_id": job["_id"]}, {"$set": {"state": "finished"}, "$unset": {"recipient": ""}})
        return True

    async def reset(self, token: str, password: str, ip: str, hash_password: Callable[[str], str],
                    password_problem: Callable[[str], Optional[str]]) -> dict:
        if (await self.limited("reset_global", "all", 300, 900)
                or await self.limited("reset_ip", ip, 30, 900)):
            await self.audit("reset_throttled")
            raise HTTPException(429, "Too many attempts. Please wait 15 minutes and try again.")
        if not TOKEN_PATTERN.fullmatch(token):
            await self.audit("reset_rejected")
            raise HTTPException(400, INVALID_LINK)
        grant = await self.db.password_recovery_grants.find_one({"_id": digest(token), "expires_at": {"$gt": utcnow()}})
        user = await self.db.users.find_one({"user_id": grant["user_id"]}) if grant else None
        active = await self.db.memberships.find_one({"user_id": user["user_id"], "status": "active"}) if user else None
        if (not grant or not user or not active or not user.get("password_hash")
                or not hmac.compare_digest(grant.get("email_fingerprint", ""), digest(user["email"]))
                or not hmac.compare_digest(grant["password_fingerprint"], digest(user["password_hash"]))):
            await self.audit("reset_rejected")
            raise HTTPException(400, INVALID_LINK)
        problem = password_problem(password)
        if problem:
            raise HTTPException(422, problem)
        new_hash = await asyncio.to_thread(hash_password, password)
        await self.audit("reset_attempted", user_id=user["user_id"])
        changed = await self.db.users.update_one(
            {"_id": user["_id"], "password_hash": user["password_hash"]},
            {"$set": {"password_hash": new_hash, "password_changed_at": utcnow().isoformat(),
                      "session_version": uuid.uuid4().hex, "must_change_password": False}})
        if changed.modified_count != 1:
            await self.audit("reset_rejected")
            raise HTTPException(400, INVALID_LINK)
        # The credential fingerprint now rejects every older link even if cleanup fails.
        await self.audit("reset_completed", user_id=user["user_id"])
        await self.db.password_recovery_grants.delete_many({
            "user_id": user["user_id"], "password_fingerprint": grant["password_fingerprint"]})
        await self.db.user_sessions.delete_many({"user_id": user["user_id"]})
        await self.db.login_lockouts.update_one({"email": user["email"]}, {
            "$set": {"failed_count": 0, "locked_until": None}}, upsert=True)
        try:
            _, _, _, cipher = configuration()
            await self.db.password_recovery_jobs.insert_one({
                "_id": uuid.uuid4().hex, "recipient": cipher.encrypt(user["email"].encode()).decode(),
                "subject": private_key("email", user["email"]), "kind": "confirmation", "state": "queued",
                "created_at": utcnow(), "expires_at": utcnow() + timedelta(minutes=TOKEN_MINUTES),
            })
        except Exception:
            await self.audit("confirmation_failed", user_id=user["user_id"])
        return dict(user)

    async def run(self) -> None:
        while True:
            try:
                if await self.deliver_one():
                    continue
            except Exception:
                logger.warning("Password recovery worker unavailable")
            await asyncio.sleep(5)
