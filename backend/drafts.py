"""Private, server-backed editor drafts.

A draft belongs to exactly one (tenant, actor, record type, record ID, editor purpose).
It is never a committed record change: saving a draft does not touch the target record,
and the target record never reads from drafts. Every request re-checks that the actor can
still access the target record, so a revoked or deleted record cannot restore content.

Concurrency is optimistic. Each write carries the draft version it was based on; a stale
autosave (an older tab, a slower request) is refused with the current draft rather than
silently overwriting newer text. A retry of the same write is recognised by its
operation ID and returns the stored result instead of bumping the version twice.
Discarding names the exact version consumed, so a newer draft written during a record
save survives.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Literal, Optional

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

COLLECTION = "record_drafts"
IDENTITY_INDEX = "draft_identity_unique"
EXPIRY_INDEX = "draft_expiry_ttl"
INACTIVITY_DAYS = 30
MAX_CONTENT = 2000

RecordType = Literal["lead"]
Purpose = Literal["note"]


class DraftWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    expected_draft_version: int = Field(ge=0, strict=True)
    target_version: int = Field(ge=0, strict=True)
    content: str = Field(max_length=MAX_CONTENT)


def enabled(tenant_id: str) -> bool:
    raw = os.getenv("RECORD_DRAFT_TENANTS", "")
    return tenant_id in {value.strip() for value in raw.split(",") if value.strip()}


async def prepare(db) -> None:
    await db[COLLECTION].create_index(
        [("tenant_id", 1), ("actor_id", 1), ("record_type", 1), ("record_id", 1), ("purpose", 1)],
        unique=True, name=IDENTITY_INDEX)
    await db[COLLECTION].create_index("expires_at", expireAfterSeconds=0, name=EXPIRY_INDEX)


async def is_ready(db) -> bool:
    index = (await db[COLLECTION].index_information()).get(IDENTITY_INDEX, {})
    return bool(index.get("unique"))


def _public(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    return {
        "record_type": doc["record_type"], "record_id": doc["record_id"], "purpose": doc["purpose"],
        "content": doc["content"], "draft_version": doc["draft_version"],
        "target_version": doc["target_version"], "created_at": doc["created_at"].isoformat(),
        "updated_at": doc["updated_at"].isoformat(), "expires_at": doc["expires_at"].isoformat(),
    }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class DraftStore:
    def __init__(self, db, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.db = db
        self.clock = clock

    def _identity(self, user: dict, record_type: str, record_id: str, purpose: str) -> dict:
        return {"tenant_id": user["tenant_id"], "actor_id": user["user_id"],
                "record_type": record_type, "record_id": record_id, "purpose": purpose}

    async def _live(self, identity: dict) -> Optional[dict]:
        doc = await self.db[COLLECTION].find_one(identity, {"_id": 0})
        if doc and _aware(doc["expires_at"]) <= self.clock():
            # TTL deletion is lazy; never restore content past its expiry.
            await self.db[COLLECTION].delete_one({**identity, "draft_version": doc["draft_version"]})
            return None
        if doc:
            for key in ("created_at", "updated_at", "expires_at"):
                doc[key] = _aware(doc[key])
        return doc

    async def read(self, user, record_type, record_id, purpose) -> Optional[dict]:
        return _public(await self._live(self._identity(user, record_type, record_id, purpose)))

    async def write(self, user, record_type, record_id, purpose, intent: DraftWrite) -> dict:
        identity = self._identity(user, record_type, record_id, purpose)
        now = self.clock()
        expires = now + timedelta(days=INACTIVITY_DAYS)
        current = await self._live(identity)

        if current and current.get("last_operation_id") == intent.operation_id:
            if current.get("content") != intent.content:
                raise HTTPException(409, detail={"code": "operation_key_reused",
                                                 "message": "This draft operation ID belongs to different text."})
            return {"state": "draft_saved", "draft": _public(current)}

        current_version = current["draft_version"] if current else 0
        if current_version != intent.expected_draft_version:
            raise HTTPException(409, detail={
                "code": "draft_conflict",
                "message": "A newer draft exists from another tab or device. Review it before saving.",
                "current": _public(current)})

        fields = {"content": intent.content, "target_version": intent.target_version,
                  "updated_at": now, "expires_at": expires, "last_operation_id": intent.operation_id}
        if not current:
            doc = {**identity, **fields, "created_at": now, "draft_version": 1}
            try:
                await self.db[COLLECTION].insert_one(doc)
            except DuplicateKeyError:
                raise HTTPException(409, detail={
                    "code": "draft_conflict", "message": "A draft was started elsewhere. Review it before saving.",
                    "current": _public(await self._live(identity))}) from None
            return {"state": "draft_saved", "draft": _public(doc)}

        updated = await self.db[COLLECTION].find_one_and_update(
            {**identity, "draft_version": intent.expected_draft_version},
            {"$set": fields, "$inc": {"draft_version": 1}},
            return_document=ReturnDocument.AFTER)
        if not updated:
            raise HTTPException(409, detail={
                "code": "draft_conflict", "message": "A newer draft exists. Review it before saving.",
                "current": _public(await self._live(identity))})
        for key in ("created_at", "updated_at", "expires_at"):
            updated[key] = _aware(updated[key])
        return {"state": "draft_saved", "draft": _public(updated)}

    async def discard(self, user, record_type, record_id, purpose, draft_version: int) -> dict:
        identity = self._identity(user, record_type, record_id, purpose)
        result = await self.db[COLLECTION].delete_one({**identity, "draft_version": draft_version})
        if result.deleted_count:
            return {"state": "discarded"}
        current = await self._live(identity)
        if current is None:
            return {"state": "discarded"}
        return {"state": "newer_draft_kept", "draft": _public(current)}

    async def purge_actor(self, tenant_id: str, actor_id: str) -> int:
        result = await self.db[COLLECTION].delete_many({"tenant_id": tenant_id, "actor_id": actor_id})
        return result.deleted_count


AccessCheck = Callable[[dict, str, str], Awaitable[None]]


def register_draft_routes(api, db, get_current_user, can_access: AccessCheck) -> DraftStore:
    store = DraftStore(db)

    async def guard(user, record_type, record_id):
        if not enabled(user["tenant_id"]):
            raise HTTPException(503, detail={"code": "rollout_disabled",
                                             "message": "Draft recovery is not enabled for this organization. Your text stays in this editor only."})
        if not await is_ready(db):
            raise HTTPException(503, detail={"code": "rollout_not_ready",
                                             "message": "Draft storage has not been prepared. Your text stays in this editor only."})
        await can_access(user, record_type, record_id)

    @api.get("/drafts/{record_type}/{record_id}")
    async def read_draft(record_type: RecordType, record_id: str, purpose: Purpose = Query("note"),
                         user=Depends(get_current_user)):
        await guard(user, record_type, record_id)
        return {"draft": await store.read(user, record_type, record_id, purpose)}

    @api.put("/drafts/{record_type}/{record_id}")
    async def save_draft(record_type: RecordType, record_id: str, intent: DraftWrite,
                         purpose: Purpose = Query("note"), user=Depends(get_current_user)):
        await guard(user, record_type, record_id)
        return await store.write(user, record_type, record_id, purpose, intent)

    @api.delete("/drafts/{record_type}/{record_id}")
    async def discard_draft(record_type: RecordType, record_id: str,
                            draft_version: int = Query(ge=1), purpose: Purpose = Query("note"),
                            user=Depends(get_current_user)):
        await guard(user, record_type, record_id)
        return await store.discard(user, record_type, record_id, purpose, draft_version)

    return store
