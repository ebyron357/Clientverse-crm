"""Snapshots: a workspace's setup, saved so it can be loaded into another workspace.

A snapshot captures the configuration an agency or a business builds once and wants
again: pipeline stages, custom fields, booking pages, website forms, automations and the
team's shared list views. It never captures records (contacts, companies, deals, leads,
messages, appointments), people (members, hosts, owners, assignees), connected accounts,
public links or secrets, so a snapshot can be handed to someone else.

It loads three ways, each through `setup_loader` and so with the same "only add what is
missing" rules as an industry template:

* from this workspace's own list (to bring back something deleted);
* with a share code: an admin turns sharing on, gets a code once, and anyone signed in to
  another workspace who has it can preview and load the snapshot. Only the code's hash is
  stored; a new code replaces the old one and turning sharing off stops it;
* from a downloaded file, which is checked item by item as anything typed into a screen.

Snapshots are admin-only: they read and change a workspace's whole setup.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Callable
from typing import Any, Optional

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import automations
import booking
import crm_core
import record_fields
import setup_loader
import website_forms as wf

SNAPSHOTS = "snapshots"
FORMAT = "clientverse.snapshot"
VERSION = 1
MAX_SNAPSHOTS = 50
MAX_BYTES = 1_000_000
CODE_PREFIX = "cvs_"
LOADS = ("own", "code", "file")


def _bad(message: str, status: int = 422) -> HTTPException:
    return HTTPException(status_code=status, detail=message)


def code_hash(code: str) -> str:
    return hashlib.sha256(code.strip().encode()).hexdigest()


async def capture(db: Any, tenant: str, include: set[str]) -> dict:
    """This workspace's setup, with every record, person, link and secret left out."""
    contents: dict[str, Any] = {"pipeline": None, **{section: [] for section in setup_loader.LIMITS}}
    if "pipeline" in include:
        contents["pipeline"] = {"stages": [{k: s.get(k) for k in ("key", "label", "probability", "is_closed", "is_won")}
                                           for s in await crm_core.resolve_stages(db, tenant)]}
    if "fields" in include:
        for obj in record_fields.OBJECTS:
            contents["fields"] += [{"object": obj, "key": d["key"], "label": d["label"], "type": d["type"],
                                    "options": d.get("options"), "help_text": d.get("help_text")}
                                   for d in await record_fields.definitions(db, tenant, obj)]
    live = {"tenant_id": tenant, "status": {"$in": ["active", "paused"]}}
    # Ids stay behind; items refer to each other by a reference local to the snapshot.
    page_refs: dict[str, str] = {}
    pages = await db[booking.EVENT_TYPES].find(live, {"_id": 0}).sort("created_at", 1).to_list(setup_loader.LIMITS["booking_pages"])
    for index, page in enumerate(pages, 1):
        page_refs[page["id"]] = f"page_{index}"
    if "booking_pages" in include:
        contents["booking_pages"] = [{"ref": page_refs[p["id"]], "name": p["name"], "preset": p.get("preset"),
                                      "status": p.get("status"), **setup_loader.page_settings(p)} for p in pages]
    form_refs: dict[str, str] = {}
    forms = await db[wf.FORMS].find(live, {"_id": 0}).sort("created_at", 1).to_list(setup_loader.LIMITS["forms"])
    for index, form in enumerate(forms, 1):
        form_refs[form["id"]] = f"form_{index}"
    if "forms" in include:
        contents["forms"] = [{"ref": form_refs[f["id"]], "name": f["name"], "form_type": f.get("form_type"),
                              "status": f.get("status"), "fields": f.get("fields") or [],
                              "settings": setup_loader.form_settings(wf.with_defaults(f)["settings"])} for f in forms]
    if "automations" in include:
        docs = await db[automations.AUTOMATIONS].find(
            {"tenant_id": tenant, "status": {"$ne": "archived"}}, {"_id": 0}).sort("created_at", 1).to_list(setup_loader.LIMITS["automations"])
        for doc in docs:
            trigger = {k: v for k, v in (doc.get("trigger") or {}).items() if k in ("event", "stage")}
            if (doc.get("trigger") or {}).get("form_id") in form_refs and "forms" in include:
                trigger["form_ref"] = form_refs[doc["trigger"]["form_id"]]
            if (doc.get("trigger") or {}).get("booking_page_id") in page_refs and "booking_pages" in include:
                trigger["booking_page_ref"] = page_refs[doc["trigger"]["booking_page_id"]]
            contents["automations"].append({
                "name": doc["name"], "description": doc.get("description"), "trigger": trigger,
                "conditions": doc.get("conditions") or [],
                "steps": [{k: v for k, v in step.items() if k != "id"}
                          for step in setup_loader.people_free_steps(doc.get("steps") or [])],
                "stop_rules": doc.get("stop_rules") or [], "once_per_contact": bool(doc.get("once_per_contact"))})
    if "views" in include:
        views = await db[record_fields.SAVED_VIEWS].find(
            {"tenant_id": tenant, "shared": True}, {"_id": 0}).sort("created_at", 1).to_list(setup_loader.LIMITS["views"])
        contents["views"] = [{"object": v["object"], "name": v["name"], "filters": v.get("filters") or [],
                              "sort": v.get("sort"), "columns": v.get("columns")} for v in views]
    return contents


async def ensure_indexes(db: Any) -> None:
    await db[SNAPSHOTS].create_index([("tenant_id", 1), ("created_at", -1)])
    await db[SNAPSHOTS].create_index("share.code_hash", sparse=True)


def counts(contents: dict) -> dict:
    out = {section: len(contents.get(section) or []) for section in setup_loader.LIMITS}
    out["stages"] = len((contents.get("pipeline") or {}).get("stages") or [])
    return out


def names(contents: dict) -> dict:
    """What a snapshot holds, by name, for a person deciding whether to load it."""
    stages = (contents.get("pipeline") or {}).get("stages") or []
    return {
        "stages": [s.get("label") for s in stages if isinstance(s, dict)],
        "fields": [f"{f.get('label')} ({setup_loader.SINGULAR.get(str(f.get('object')), f.get('object'))})"
                   for f in contents.get("fields") or []],
        **{section: [item.get("name") for item in contents.get(section) or []]
           for section in ("booking_pages", "forms", "automations", "views")},
    }


def summary(doc: dict) -> dict:
    share = doc.get("share") or {}
    return {"id": doc["id"], "name": doc["name"], "description": doc.get("description"),
            "counts": doc.get("counts") or counts(doc.get("contents") or {}),
            "created_by": doc.get("created_by"), "created_at": doc.get("created_at"),
            "shared": bool(share.get("enabled")), "shared_at": share.get("created_at") if share.get("enabled") else None,
            "loads": int(share.get("loads") or 0)}


def file_body(doc: dict) -> dict:
    return {"format": FORMAT, "version": VERSION, "name": doc["name"], "description": doc.get("description"),
            "created_at": doc.get("created_at"), "contents": doc["contents"]}


def _size(contents: dict) -> int:
    return len(json.dumps(contents, default=str))


class SnapshotInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=300)
    include: list[str] = Field(default_factory=lambda: list(setup_loader.SECTIONS), max_length=len(setup_loader.SECTIONS))


class LoadInput(BaseModel):
    snapshot_id: Optional[str] = Field(default=None, max_length=80)
    code: Optional[str] = Field(default=None, max_length=100)
    file: Optional[dict] = None


def register_snapshot_routes(router: Any, db: Any, loader: setup_loader.SetupLoader, *,
                             new_id: Callable[[str], str], now_iso: Callable[[], str],
                             record_event: Callable[..., Any], require_role: Any) -> None:
    admin = require_role("admin")

    async def own(snapshot_id: str, user: dict) -> dict:
        doc: Optional[dict] = await db[SNAPSHOTS].find_one({"tenant_id": user["tenant_id"], "id": snapshot_id}, {"_id": 0})
        if not doc:
            raise _bad("Not found", 404)
        return doc

    @router.get("/snapshots")
    async def list_snapshots(user: dict = Depends(admin)) -> dict:
        docs = await db[SNAPSHOTS].find({"tenant_id": user["tenant_id"]}, {"_id": 0, "contents": 0}).sort(
            "created_at", -1).to_list(MAX_SNAPSHOTS)
        return {"items": [summary(d) for d in docs], "limit": MAX_SNAPSHOTS}

    # Registered before /snapshots/{snapshot_id} so the path is not read as an id.
    @router.get("/snapshots/current-setup")
    async def current_setup(user: dict = Depends(admin)) -> dict:
        """What a snapshot of this workspace would hold now, counted."""
        return {"counts": counts(await capture(db, user["tenant_id"], set(setup_loader.SECTIONS)))}

    @router.post("/snapshots")
    async def create_snapshot(inp: SnapshotInput, user: dict = Depends(admin)) -> dict:
        tenant = user["tenant_id"]
        include = set(inp.include)
        unknown = include - set(setup_loader.SECTIONS)
        if unknown:
            raise _bad(f"'{sorted(unknown)[0]}' is not part of a setup")
        if not include:
            raise _bad("Choose at least one part of the setup to save")
        if await db[SNAPSHOTS].count_documents({"tenant_id": tenant}) >= MAX_SNAPSHOTS:
            raise _bad(f"A workspace can keep at most {MAX_SNAPSHOTS} snapshots. Delete one first.")
        contents = await capture(db, tenant, include)
        if _size(contents) > MAX_BYTES:
            raise _bad("This setup is too large to save as one snapshot")
        doc = {"id": new_id("snap"), "tenant_id": tenant, "name": inp.name.strip(),
               "description": (inp.description or "").strip() or None, "contents": contents,
               "counts": counts(contents), "created_by": user["email"], "created_at": now_iso(),
               "share": {"enabled": False, "code_hash": None, "created_at": None, "loads": 0}}
        await db[SNAPSHOTS].insert_one(dict(doc))
        await record_event("snapshot.created", "snapshot", doc["id"], tenant, user["email"],
                           payload={"name": doc["name"], "counts": doc["counts"]})
        return summary(doc)

    @router.get("/snapshots/{snapshot_id}")
    async def get_snapshot(snapshot_id: str, user: dict = Depends(admin)) -> dict:
        doc = await own(snapshot_id, user)
        return {**summary(doc), "names": names(doc["contents"])}

    @router.get("/snapshots/{snapshot_id}/file")
    async def download_snapshot(snapshot_id: str, user: dict = Depends(admin)) -> JSONResponse:
        doc = await own(snapshot_id, user)
        slug = re.sub(r"[^a-z0-9]+", "-", doc["name"].lower()).strip("-")[:60] or "snapshot"
        await record_event("snapshot.downloaded", "snapshot", doc["id"], user["tenant_id"], user["email"],
                           payload={"name": doc["name"]})
        return JSONResponse(file_body(doc), headers={
            "Content-Disposition": f'attachment; filename="{slug}.clientverse-snapshot.json"'})

    @router.post("/snapshots/{snapshot_id}/share")
    async def share_snapshot(snapshot_id: str, user: dict = Depends(admin)) -> dict:
        """Turn sharing on with a new code, shown once. Any earlier code stops working."""
        doc = await own(snapshot_id, user)
        code = CODE_PREFIX + secrets.token_urlsafe(24)
        await db[SNAPSHOTS].update_one({"id": doc["id"], "tenant_id": user["tenant_id"]}, {"$set": {
            "share.enabled": True, "share.code_hash": code_hash(code), "share.created_at": now_iso()}})
        await record_event("snapshot.shared", "snapshot", doc["id"], user["tenant_id"], user["email"],
                           payload={"name": doc["name"]})
        return {"code": code, **summary({**doc, "share": {**(doc.get("share") or {}), "enabled": True, "created_at": now_iso()}})}

    @router.delete("/snapshots/{snapshot_id}/share")
    async def stop_sharing(snapshot_id: str, user: dict = Depends(admin)) -> dict:
        doc = await own(snapshot_id, user)
        await db[SNAPSHOTS].update_one({"id": doc["id"], "tenant_id": user["tenant_id"]}, {"$set": {
            "share.enabled": False, "share.code_hash": None}})
        await record_event("snapshot.unshared", "snapshot", doc["id"], user["tenant_id"], user["email"],
                           payload={"name": doc["name"]})
        return summary({**doc, "share": {**(doc.get("share") or {}), "enabled": False}})

    @router.delete("/snapshots/{snapshot_id}")
    async def delete_snapshot(snapshot_id: str, user: dict = Depends(admin)) -> dict:
        doc = await own(snapshot_id, user)
        await db[SNAPSHOTS].delete_one({"id": doc["id"], "tenant_id": user["tenant_id"]})
        await record_event("snapshot.deleted", "snapshot", doc["id"], user["tenant_id"], user["email"],
                           payload={"name": doc["name"]})
        return {"deleted": True}

    async def source(inp: LoadInput, user: dict) -> tuple[Any, str, str, Optional[dict]]:
        """The contents to load, how they came, their name, and the stored snapshot if any."""
        given = [kind for kind, value in (("own", inp.snapshot_id), ("code", inp.code), ("file", inp.file)) if value]
        if len(given) != 1:
            raise _bad("Choose one snapshot to load: one of yours, a share code or a file")
        if given[0] == "own":
            doc = await own(str(inp.snapshot_id), user)
            return doc["contents"], "own", doc["name"], doc
        if given[0] == "code":
            doc = await db[SNAPSHOTS].find_one({"share.enabled": True, "share.code_hash": code_hash(str(inp.code))},
                                               {"_id": 0})
            if not doc:
                raise _bad("No shared snapshot has this code. Check it, or ask for a new one.", 404)
            return doc["contents"], "code", doc["name"], doc
        body = inp.file or {}
        if body.get("format") != FORMAT:
            raise _bad("This file is not a ClientVerse snapshot")
        if body.get("version") != VERSION:
            raise _bad("This snapshot was made by a different version of ClientVerse")
        if _size(body) > MAX_BYTES:
            raise _bad("This snapshot file is too large", 413)
        return body.get("contents"), "file", str(body.get("name") or "Snapshot file")[:80], None

    async def load(inp: LoadInput, user: dict, apply: bool) -> dict:
        raw, kind, name, doc = await source(inp, user)
        contents = setup_loader.check_contents(raw)
        tenant = user["tenant_id"]
        origin = {"snapshot": name, "loaded_from": kind}
        items = await loader.plan(tenant, contents, user["email"], apply=apply, origin=origin)
        if apply:
            added = [i["name"] for i in items if i["action"] == "add"]
            await record_event("snapshot.loaded", "tenant", tenant, tenant, user["email"],
                               payload={**origin, "added": added,
                                        "skipped": [i["name"] for i in items if i["action"] == "skip"]})
            if doc is not None and kind == "code":
                await db[SNAPSHOTS].update_one({"id": doc["id"]}, {"$inc": {"share.loads": 1}})
        return {"name": name, "loaded_from": kind, "applied": apply, "items": items}

    @router.post("/snapshot-loads/preview")
    async def preview_load(inp: LoadInput, user: dict = Depends(admin)) -> dict:
        return await load(inp, user, apply=False)

    @router.post("/snapshot-loads/apply")
    async def apply_load(inp: LoadInput, user: dict = Depends(admin)) -> dict:
        return await load(inp, user, apply=True)
