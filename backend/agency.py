"""Agency accounts: one workspace that runs client accounts.

An agency is an ordinary workspace whose admins create client accounts under it. A client
account is a workspace of its own: its records, team, connections and settings are
separate from the agency's and from every other client's, exactly as two unrelated
workspaces are, and its own people sign in to it as usual.

What the agency adds:

* its admins can open any of its client accounts and work there as an admin. The session
  then carries the client account it is acting in (`act` in the token), and that is
  checked on every request: the person must still be an active admin of the agency and
  the account must still belong to it. Demote them, disable them, or move the account,
  and the next request is refused;
* a client account can be created from one of the agency's snapshots;
* a snapshot can be pushed to many client accounts at once, previewed first, with a
  result per account. Each load follows `setup_loader`'s rules, so nothing a client
  already has is changed;
* opening an account and pushing to it are recorded in both the agency's and the client's
  audit trail.

A client account cannot have client accounts of its own, and its people never see the
agency's records or another client's.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Optional

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

import crm_core
import setup_loader
import snapshots

MAX_ACCOUNTS = 200
MAX_PUSH = 100


def _refused(message: str, status: int = 403) -> HTTPException:
    return HTTPException(status_code=status, detail=message)


async def act_as(db: Any, user: dict, tenant_id: str) -> dict:
    """The signed-in agency admin, working inside one of the agency's client accounts.
    `user` is already resolved against their own workspace. Raises 401 when the access
    no longer holds, so the browser signs in again and lands back in the agency."""
    home = user["tenant_id"]
    if tenant_id == home:
        return user
    if user.get("role") != "admin":
        raise _refused("You no longer have access to that client account. Sign in again.", 401)
    client = await db.tenants.find_one({"tenant_id": tenant_id, "parent_tenant_id": home},
                                       {"_id": 0, "tenant_id": 1, "name": 1})
    if not client:
        raise _refused("You no longer have access to that client account. Sign in again.", 401)
    agency = await db.tenants.find_one({"tenant_id": home}, {"_id": 0, "name": 1}) or {}
    return {**user, "tenant_id": tenant_id, "role": "admin", "home_tenant_id": home,
            "acting": {"tenant_id": tenant_id, "name": client.get("name"),
                       "agency_tenant_id": home, "agency_name": agency.get("name")}}


async def workspace_info(db: Any, user: dict) -> dict:
    """What kind of workspace the person is in: an agency, a client account, or neither."""
    tenant = await db.tenants.find_one({"tenant_id": user["tenant_id"]}, {"_id": 0}) or {}
    if tenant.get("parent_tenant_id"):
        parent = await db.tenants.find_one({"tenant_id": tenant["parent_tenant_id"]}, {"_id": 0, "name": 1}) or {}
        return {"name": tenant.get("name"), "kind": "client", "agency_name": parent.get("name")}
    accounts = await db.tenants.count_documents({"parent_tenant_id": user["tenant_id"]})
    return {"name": tenant.get("name"), "kind": "agency" if accounts else "standalone", "client_accounts": accounts}


class AccountInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    snapshot_id: Optional[str] = Field(default=None, max_length=80)


class AccountPatch(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class PushInput(BaseModel):
    snapshot_id: str = Field(min_length=1, max_length=80)
    account_ids: list[str] = Field(min_length=1, max_length=MAX_PUSH)


def register_agency_routes(router: Any, db: Any, loader: setup_loader.SetupLoader, *,
                           new_id: Callable[[str], str], now_iso: Callable[[], str],
                           record_event: Callable[..., Any], get_current_user: Any,
                           create_access_token: Callable[..., str],
                           set_auth_cookie: Callable[[Response, str], None],
                           extract_token: Callable[[Request], Optional[str]],
                           revoke_token: Callable[[str], Awaitable[None]],
                           resolve_membership: Callable[[dict], Awaitable[dict]]) -> None:

    async def agency_admin(user: dict = Depends(get_current_user)) -> dict:
        """An admin of an agency (any workspace that is not itself a client account),
        whether they are in it now or working in one of its client accounts."""
        home = user.get("home_tenant_id") or user["tenant_id"]
        if user.get("role") != "admin":
            raise _refused("Only an admin can manage client accounts")
        tenant = await db.tenants.find_one({"tenant_id": home}, {"_id": 0}) or {}
        if tenant.get("parent_tenant_id"):
            raise _refused("A client account cannot have client accounts of its own")
        return {**user, "agency_tenant_id": home, "agency_name": tenant.get("name")}

    async def child(agency: dict, tenant_id: str) -> dict:
        account: Optional[dict] = await db.tenants.find_one(
            {"tenant_id": tenant_id, "parent_tenant_id": agency["agency_tenant_id"]}, {"_id": 0})
        if not account:
            raise _refused("Not found", 404)
        return account

    async def summary(account: dict) -> dict:
        tid = account["tenant_id"]
        classes = await crm_core.stage_classes(db, tid)
        return {"tenant_id": tid, "name": account.get("name"), "created_at": account.get("created_at"),
                "created_by": account.get("created_by"),
                "members": await db.memberships.count_documents({"tenant_id": tid, "status": {"$ne": "disabled"}}),
                "contacts": await db.contacts.count_documents({"tenant_id": tid, "archived_at": None}),
                "open_deals": await db.opportunities.count_documents(
                    {"tenant_id": tid, "archived_at": None, "stage": {"$in": sorted(classes[crm_core.STAGE_OPEN])}}),
                "last_snapshot": account.get("last_snapshot")}

    async def session_for(request: Request, response: Response, user: dict, acting: Optional[str]) -> dict:
        """A fresh session for the same person, in their agency or acting in a client account.
        The session it replaces ends, so one browser holds one session."""
        old = extract_token(request)
        if old:
            await revoke_token(old)
        token = create_access_token(user["user_id"], user["email"], acting_tenant=acting)
        set_auth_cookie(response, token)
        me: Optional[dict] = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password_hash": 0})
        resolved = await resolve_membership(me or {})
        if acting:
            resolved = await act_as(db, resolved, acting)
        return {"token": token, "user": resolved}

    @router.get("/agency")
    async def agency_state(user: dict = Depends(get_current_user)) -> dict:
        home = {**user, "tenant_id": user.get("home_tenant_id") or user["tenant_id"]}
        return {"workspace": await workspace_info(db, home), "acting": user.get("acting")}

    @router.get("/agency/accounts")
    async def list_accounts(agency: dict = Depends(agency_admin)) -> dict:
        accounts = await db.tenants.find({"parent_tenant_id": agency["agency_tenant_id"]}, {"_id": 0}).sort(
            "name", 1).to_list(MAX_ACCOUNTS)
        return {"agency_name": agency["agency_name"], "items": [await summary(a) for a in accounts],
                "limit": MAX_ACCOUNTS}

    @router.get("/agency/snapshots")
    async def agency_snapshots(agency: dict = Depends(agency_admin)) -> dict:
        """The agency's own snapshots, also from inside a client account."""
        docs = await db[snapshots.SNAPSHOTS].find({"tenant_id": agency["agency_tenant_id"]},
                                                  {"_id": 0, "contents": 0}).sort("created_at", -1).to_list(snapshots.MAX_SNAPSHOTS)
        return {"items": [snapshots.summary(d) for d in docs]}

    @router.post("/agency/accounts")
    async def create_account(inp: AccountInput, agency: dict = Depends(agency_admin)) -> dict:
        home = agency["agency_tenant_id"]
        if await db.tenants.count_documents({"parent_tenant_id": home}) >= MAX_ACCOUNTS:
            raise _refused(f"An agency can have at most {MAX_ACCOUNTS} client accounts", 422)
        snapshot = None
        if inp.snapshot_id:
            snapshot = await db[snapshots.SNAPSHOTS].find_one({"tenant_id": home, "id": inp.snapshot_id}, {"_id": 0})
            if not snapshot:
                raise _refused("Choose one of your agency's snapshots", 422)
        tenant_id = new_id("ten")
        account = {"tenant_id": tenant_id, "name": inp.name.strip(), "created_at": now_iso(),
                   "parent_tenant_id": home, "created_by": agency["email"], "last_snapshot": None}
        await db.tenants.insert_one(dict(account))
        await record_event("agency.account_created", "tenant", tenant_id, home, agency["email"],
                           payload={"name": account["name"]})
        await record_event("agency.account_created", "tenant", tenant_id, tenant_id, agency["email"],
                           payload={"name": account["name"], "agency": agency["agency_name"]})
        items: list[dict] = []
        if snapshot:
            items = await load_into(agency, account, snapshot, apply=True)
            account = await child(agency, tenant_id)
        return {"account": await summary(account), "items": items}

    @router.patch("/agency/accounts/{tenant_id}")
    async def rename_account(tenant_id: str, inp: AccountPatch, agency: dict = Depends(agency_admin)) -> dict:
        account = await child(agency, tenant_id)
        await db.tenants.update_one({"tenant_id": tenant_id}, {"$set": {"name": inp.name.strip()}})
        await record_event("agency.account_renamed", "tenant", tenant_id, agency["agency_tenant_id"], agency["email"],
                           payload={"from": account.get("name"), "to": inp.name.strip()})
        return await summary({**account, "name": inp.name.strip()})

    @router.post("/agency/accounts/{tenant_id}/enter")
    async def enter_account(tenant_id: str, request: Request, response: Response,
                            agency: dict = Depends(agency_admin)) -> dict:
        account = await child(agency, tenant_id)
        await record_event("agency.account_opened", "tenant", tenant_id, agency["agency_tenant_id"], agency["email"],
                           payload={"name": account.get("name")})
        await record_event("agency.account_opened", "tenant", tenant_id, tenant_id, agency["email"],
                           payload={"agency": agency["agency_name"]})
        return await session_for(request, response, agency, tenant_id)

    @router.post("/agency/leave")
    async def leave_account(request: Request, response: Response, user: dict = Depends(get_current_user)) -> dict:
        return await session_for(request, response, user, None)

    async def load_into(agency: dict, account: dict, snapshot: dict, *, apply: bool) -> list[dict]:
        tid = account["tenant_id"]
        # The loader hosts booking pages with the account's own team (its first admin), since
        # the agency admin is not on it; an account with no team yet gets them paused.
        items: list[dict] = await loader.plan(
            tid, setup_loader.check_contents(snapshot["contents"]), agency["email"], apply=apply,
            origin={"snapshot": snapshot["name"], "loaded_from": "agency"})
        if apply:
            added = [i["name"] for i in items if i["action"] == "add"]
            await record_event("snapshot.loaded", "tenant", tid, tid, agency["email"],
                               payload={"snapshot": snapshot["name"], "loaded_from": "agency", "agency": agency["agency_name"],
                                        "added": added, "skipped": [i["name"] for i in items if i["action"] == "skip"]})
            await db.tenants.update_one({"tenant_id": tid}, {"$set": {"last_snapshot": {
                "name": snapshot["name"], "loaded_at": now_iso(), "added": len(added)}}})
        return items

    async def push(inp: PushInput, agency: dict, apply: bool) -> dict:
        home = agency["agency_tenant_id"]
        snapshot = await db[snapshots.SNAPSHOTS].find_one({"tenant_id": home, "id": inp.snapshot_id}, {"_id": 0})
        if not snapshot:
            raise _refused("Choose one of your agency's snapshots", 404)
        # Every account is checked before any is changed, so one wrong id loads nothing.
        accounts = [await child(agency, tenant_id) for tenant_id in dict.fromkeys(inp.account_ids)]
        results = []
        for account in accounts:
            tenant_id = account["tenant_id"]
            items = await load_into(agency, account, snapshot, apply=apply)
            results.append({"tenant_id": tenant_id, "name": account.get("name"), "items": items,
                            **{action: sum(1 for i in items if i["action"] == action) for action in ("add", "keep", "skip")}})
        if apply:
            await record_event("agency.snapshot_pushed", "snapshot", snapshot["id"], home, agency["email"],
                               payload={"snapshot": snapshot["name"],
                                        "accounts": [{"name": r["name"], "added": r["add"], "skipped": r["skip"]} for r in results]})
        return {"snapshot": snapshot["name"], "applied": apply, "accounts": results}

    @router.post("/agency/snapshot-push/preview")
    async def preview_push(inp: PushInput, agency: dict = Depends(agency_admin)) -> dict:
        return await push(inp, agency, apply=False)

    @router.post("/agency/snapshot-push/apply")
    async def apply_push(inp: PushInput, agency: dict = Depends(agency_admin)) -> dict:
        return await push(inp, agency, apply=True)
