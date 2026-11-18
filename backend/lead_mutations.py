"""Opt-in, receipt-backed lead saves. No sequential fallback on transaction failure."""

import asyncio
import hashlib
import json
import logging
import os
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

RECEIPTS = "lead_operation_receipts"
INDEX_NAME = "tenant_operation_unique"
logger = logging.getLogger("clientverse.lead_mutations")


class LeadMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    expected_version: int = Field(ge=0, strict=True)
    status: Literal["new", "responded", "closed", "spam"]
    note: str = Field(default="", max_length=2000)


def enabled(tenant_id: str) -> bool:
    return tenant_id in {value.strip() for value in os.getenv("LEAD_MUTATION_TENANTS", "").split(",") if value.strip()}


def version_filter(version: int) -> dict:
    return {"$or": [{"version": 0}, {"version": {"$exists": False}}]} if version == 0 else {"version": version}


def public_lead(lead: dict) -> dict:
    return {**{k: v for k, v in lead.items() if k not in ("_id", "visitor")},
            "version": lead.get("version", 0),
            "mutation_contract": "receipt-v1" if enabled(lead["tenant_id"]) else None}


async def require_ready(db) -> None:
    hello = await db.command("hello")
    if not (hello.get("setName") or hello.get("msg") == "isdbgrid"):
        raise HTTPException(503, detail={"code": "transactions_unavailable", "message": "Lead saves require a MongoDB replica set. Nothing was saved."})
    indexes = await db[RECEIPTS].index_information()
    index = indexes.get(INDEX_NAME, {})
    if not index.get("unique") or list(index.get("key", [])) != [("tenant_id", 1), ("operation_id", 1)]:
        raise HTTPException(503, detail={"code": "rollout_not_ready", "message": "Lead save indexes have not been prepared. Nothing was saved."})


async def prepare(db) -> None:
    hello = await db.command("hello")
    if not (hello.get("setName") or hello.get("msg") == "isdbgrid"):
        raise RuntimeError("Replica set or mongos required; rollout refused")
    await db[RECEIPTS].create_index([("tenant_id", 1), ("operation_id", 1)], unique=True, name=INDEX_NAME)


async def transact(db, callback):
    async with await db.client.start_session() as session:
        async with asyncio.timeout(20):
            return await session.with_transaction(callback, read_concern=ReadConcern("snapshot"),
                                                  write_concern=WriteConcern("majority"), max_commit_time_ms=5000)


class LeadMutations:
    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.db = pipeline.db

    async def receipt(self, lead_id, operation_id, user, *, session=None):
        from detectors import WEB_ENQUIRIES
        lead = await self.db[WEB_ENQUIRIES].find_one(
            {"id": lead_id, "tenant_id": user["tenant_id"]}, {"_id": 0}, session=session)
        if not lead:
            raise HTTPException(404, "Not found")
        collection = self.db[RECEIPTS] if session else self.db[RECEIPTS].with_options(read_concern=ReadConcern("majority"))
        receipt = await collection.find_one(
            {"tenant_id": user["tenant_id"], "operation_id": operation_id}, {"_id": 0}, session=session)
        if receipt and (receipt["actor_id"] != user["user_id"] or receipt["lead_id"] != lead_id):
            raise HTTPException(409, detail={"code": "operation_key_reused", "message": "This operation ID is already in use. Review the lead before starting a new update."})
        return receipt

    async def save(self, lead_id, intent: LeadMutation, user):
        from detectors import WEB_ENQUIRIES
        payload_hash = hashlib.sha256(json.dumps(
            {"lead_id": lead_id, "actor_id": user["user_id"], **intent.model_dump(exclude={"operation_id"})},
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()

        def replay(receipt):
            if receipt["payload_hash"] != payload_hash:
                raise HTTPException(409, detail={"code": "operation_key_reused", "message": "This operation ID belongs to a different update. Nothing new was saved."})
            return receipt["response"]

        receipt = await self.receipt(lead_id, intent.operation_id, user)
        if receipt:
            return replay(receipt)
        if not enabled(user["tenant_id"]):
            raise HTTPException(503, detail={"code": "rollout_disabled", "message": "Retry-safe lead saves are not enabled for this organization. Do not resend through the legacy endpoint."})
        await require_ready(self.db)

        async def commit(session):
            receipt = await self.receipt(lead_id, intent.operation_id, user, session=session)
            if receipt:
                return replay(receipt)
            criteria = {"id": lead_id, "tenant_id": user["tenant_id"]}
            lead = await self.db[WEB_ENQUIRIES].find_one(criteria, {"_id": 0}, session=session)
            if lead.get("version", 0) != intent.expected_version:
                raise HTTPException(409, detail={"code": "version_conflict", "message": "This lead changed since you started editing. Reload and review it before reapplying your update.",
                                                 "current_version": lead.get("version", 0), "current_status": lead["status"]})
            if intent.note:
                contact = await self.db.contacts.find_one(
                    {"tenant_id": user["tenant_id"], "id": lead.get("contact_id")}, {"_id": 1}, session=session)
                if not contact:
                    raise HTTPException(422, detail={"code": "missing_contact", "message": "The linked contact is missing. Your note was not saved; no status change was made."})
            result = await self.db[WEB_ENQUIRIES].update_one(
                {**criteria, **version_filter(intent.expected_version)}, {"$inc": {"version": 1}}, session=session)
            if not result.modified_count:
                raise HTTPException(409, detail={"code": "version_conflict", "message": "Reload and review the latest lead."})
            await self.pipeline.apply_lead_update(lead, intent.status, intent.note, user["email"], session=session)
            updated = await self.db[WEB_ENQUIRIES].find_one(criteria, {"_id": 0}, session=session)
            response = {"state": "committed", "operation_id": intent.operation_id, "lead": public_lead(updated)}
            await self.db[RECEIPTS].insert_one({
                "tenant_id": user["tenant_id"], "operation_id": intent.operation_id,
                "actor_id": user["user_id"], "lead_id": lead_id, "payload_hash": payload_hash,
                "committed_at": self.pipeline.now_iso(), "response": response}, session=session)
            return response

        try:
            result = await transact(self.db, commit)
            logger.info("lead_mutation outcome=committed operation=%s", intent.operation_id)
            return result
        except (PyMongoError, TimeoutError):
            # Commit may have reached a majority even when its acknowledgment was lost.
            try:
                receipt = await self.receipt(lead_id, intent.operation_id, user)
                if receipt:
                    return replay(receipt)
            except PyMongoError:
                pass
            logger.warning("lead_mutation outcome=unknown operation=%s", intent.operation_id)
            raise HTTPException(503, detail={"code": "outcome_unknown", "operation_id": intent.operation_id,
                                            "message": "The save outcome is unknown. Check the receipt or retry this same operation; do not create a new update."}) from None
