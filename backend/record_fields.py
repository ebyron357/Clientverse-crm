"""Custom fields and saved views: shaping the CRM to the business without code.

Every CRM a buyer compares ClientVerse with lets an admin add fields to contacts,
companies and deals, and lets anyone save the list they keep coming back to. Two small
collections carry that here:

* `custom_field_defs` -- one definition per field: the record type it belongs to, a
  stable key (`cf_...`), a label, a type and, for a choice, its options. Values live on
  the record itself under `custom_fields.<key>`, beside the fields website forms already
  capture, so a form answer and an admin-defined field read the same way.
* `saved_views` -- a named list: filters, sort and columns for one record type, private
  to its creator or shared with the team.

A value is checked against its definition before it is stored, so a number field holds a
number and a choice holds one of its options. Archiving a definition hides the field and
keeps every value it already has; nothing here deletes data.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError
from pymongo.errors import DuplicateKeyError

FIELD_DEFS = "custom_field_defs"
SAVED_VIEWS = "saved_views"

OBJECTS = ("contacts", "companies", "deals")
FIELD_TYPES = ("text", "long_text", "number", "date", "select", "checkbox", "url", "email", "phone")
MAX_FIELDS_PER_OBJECT = 100
MAX_OPTIONS = 50
MAX_TEXT = 300
MAX_LONG_TEXT = 4000

FILTER_OPS = ("is", "is_not", "contains", "is_empty", "is_not_empty", "gt", "lt", "before", "after", "in")
FIELD_PATH = re.compile(r"^[a-z_][a-z0-9_]{0,60}(\.[a-z0-9_]{1,60})?$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# The built-in fields a view may filter on or show, and how each compares. Anything else
# a view names must be a custom field (`custom_fields.<key>`) the tenant has defined.
BUILTIN_FIELDS = {
    "contacts": {"name": "text", "email": "text", "phone": "text", "role": "text",
                 "title": "text", "owner": "text", "company_id": "id", "lifecycle": "select",
                 "sentiment": "select", "influence": "select", "tags": "list",
                 "created_at": "date", "updated_at": "date", "last_inquiry_at": "date"},
    "companies": {"name": "text", "industry": "text", "website": "text", "domain": "text",
                  "owner": "text", "tier": "select", "tags": "list", "created_at": "date",
                  "updated_at": "date"},
    "deals": {"name": "text", "owner": "text", "stage": "select", "company_id": "id",
              "value": "number", "expected_close_date": "date", "source": "text",
              "created_at": "date", "updated_at": "date"},
}
# How a custom field's type compares, in the terms above.
_CUSTOM_COMPARISON = {"text": "text", "long_text": "text", "url": "text", "email": "text",
                      "phone": "text", "number": "number", "date": "date", "select": "select",
                      "checkbox": "checkbox"}


def _slug(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:40].strip("_")
    return slug or "field"


def coerce(definition: dict, value: Any) -> Any:
    """The value as its field's type stores it, or a 422 naming the problem."""
    label = definition.get("label") or definition["key"]
    kind = definition.get("type")
    if value is None or (isinstance(value, str) and not value.strip() and kind != "checkbox"):
        return None
    if kind == "checkbox":
        if isinstance(value, bool):
            return value
        raise HTTPException(status_code=422, detail=f"{label} must be true or false")
    if kind == "number":
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail=f"{label} must be a number")
        if number != number or number in (float("inf"), float("-inf")) or abs(number) > 1e15:
            raise HTTPException(status_code=422, detail=f"{label} is out of range")
        return number
    text = str(value).strip()
    if kind == "date":
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            raise HTTPException(status_code=422, detail=f"{label} must be a date (YYYY-MM-DD)")
    if kind == "select":
        if text not in (definition.get("options") or []):
            raise HTTPException(status_code=422, detail=f"{label} must be one of its options")
        return text
    if kind == "email" and not EMAIL.match(text):
        raise HTTPException(status_code=422, detail=f"{label} must be an email address")
    if kind == "url" and not re.match(r"^https?://\S+\.\S+", text):
        raise HTTPException(status_code=422, detail=f"{label} must be a web address starting with http")
    return text[:MAX_LONG_TEXT if kind == "long_text" else MAX_TEXT]


async def definitions(db, tenant_id: str, object_name: str, *, include_archived: bool = False) -> list[dict]:
    query: dict[str, Any] = {"tenant_id": tenant_id, "object": object_name}
    if not include_archived:
        query["archived_at"] = None
    return await db[FIELD_DEFS].find(query, {"_id": 0}).sort("position", 1).to_list(MAX_FIELDS_PER_OBJECT * 2)


async def value_updates(db, tenant_id: str, object_name: str, values: dict) -> dict[str, Any]:
    """`{key: value}` from a patch, checked against the live definitions.

    Returns `{key: stored_value}`. A key with no live definition is refused: a typo must
    not quietly create a field nobody can see or report on.
    """
    if not isinstance(values, dict):
        raise HTTPException(status_code=422, detail="custom_fields must be an object")
    defs = {d["key"]: d for d in await definitions(db, tenant_id, object_name)}
    out: dict[str, Any] = {}
    for key, value in values.items():
        definition = defs.get(str(key))
        if not definition:
            raise HTTPException(status_code=422, detail=f"Unknown custom field '{key}'")
        out[definition["key"]] = coerce(definition, value)
    return out


# ------------------------------------------------------------------------ payloads

class FieldInput(BaseModel):
    object: str = Field(pattern="^(contacts|companies|deals)$")
    label: str = Field(min_length=1, max_length=80)
    type: str = Field(pattern="^(text|long_text|number|date|select|checkbox|url|email|phone)$")
    options: Optional[list[str]] = Field(default=None, max_length=MAX_OPTIONS)
    help_text: Optional[str] = Field(default=None, max_length=200)


class FieldPatch(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=80)
    options: Optional[list[str]] = Field(default=None, max_length=MAX_OPTIONS)
    help_text: Optional[str] = Field(default=None, max_length=200)
    position: Optional[int] = Field(default=None, ge=0, le=1000)
    archived: Optional[bool] = None


class ViewFilter(BaseModel):
    field: str = Field(min_length=1, max_length=122)
    op: str
    value: Any = None


class ViewSort(BaseModel):
    field: str = Field(min_length=1, max_length=122)
    order: str = Field(default="desc", pattern="^(asc|desc)$")


class ViewInput(BaseModel):
    object: str = Field(pattern="^(contacts|companies|deals)$")
    name: str = Field(min_length=1, max_length=60)
    filters: list[ViewFilter] = Field(default_factory=list, max_length=20)
    sort: Optional[ViewSort] = None
    columns: Optional[list[str]] = Field(default=None, max_length=30)
    shared: bool = True


class ViewPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    filters: Optional[list[ViewFilter]] = Field(default=None, max_length=20)
    sort: Optional[ViewSort] = None
    columns: Optional[list[str]] = Field(default=None, max_length=30)
    shared: Optional[bool] = None


def clean_options(kind: str, options: Optional[list[str]]) -> Optional[list[str]]:
    if kind != "select":
        return None
    cleaned = list(dict.fromkeys(str(o).strip()[:80] for o in options or [] if str(o).strip()))
    if not cleaned:
        raise HTTPException(status_code=422, detail="A choice field needs at least one option")
    return cleaned


def clean_filters(filters: list[ViewFilter]) -> list[dict]:
    out = []
    for item in filters:
        if not FIELD_PATH.match(item.field):
            raise HTTPException(status_code=422, detail=f"'{item.field}' is not a field a view can filter on")
        if item.op not in FILTER_OPS:
            raise HTTPException(status_code=422, detail=f"'{item.op}' is not a filter operator")
        value = item.value
        if isinstance(value, list):
            value = [str(v)[:200] for v in value[:50]]
        elif value is not None and not isinstance(value, (bool, int, float)):
            value = str(value)[:200]
        out.append({"field": item.field, "op": item.op, "value": value})
    return out


def clean_columns(columns: Optional[list[str]]) -> Optional[list[str]]:
    if columns is None:
        return None
    for column in columns:
        if not FIELD_PATH.match(column):
            raise HTTPException(status_code=422, detail=f"'{column}' is not a column")
    return list(dict.fromkeys(columns))


async def field_kinds(db, tenant_id: str, object_name: str) -> dict[str, str]:
    """Every field a view of this record type may use, and how it compares.

    Archived custom fields stay usable: their values are kept, so a saved view that
    filters on one keeps working."""
    kinds = dict(BUILTIN_FIELDS[object_name])
    for definition in await definitions(db, tenant_id, object_name, include_archived=True):
        kinds[f"custom_fields.{definition['key']}"] = _CUSTOM_COMPARISON.get(str(definition.get("type")), "text")
    return kinds


def _unknown(field: str) -> HTTPException:
    return HTTPException(status_code=422, detail=f"'{field}' is not a field this list has")


async def check_view_fields(db, tenant_id: str, object_name: str, filters: list[dict],
                            columns: Optional[list[str]]) -> None:
    kinds = await field_kinds(db, tenant_id, object_name)
    for name in [item["field"] for item in filters] + list(columns or []):
        if name not in kinds:
            raise _unknown(name)


def _number(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"'{field}' compares with a number")


def _condition(field: str, kind: str, op: str, value: Any) -> dict:
    empty: list[Any] = [None, "", []]
    if op == "is_empty":
        return {field: {"$in": empty}}
    if op == "is_not_empty":
        return {field: {"$nin": empty}}
    if op == "in":
        values = value if isinstance(value, list) else [value]
        return {field: {"$in": [_number(v, field) for v in values] if kind == "number" else values}}
    if op in ("gt", "lt", "before", "after"):
        if kind not in ("number", "date"):
            raise HTTPException(status_code=422, detail=f"'{field}' cannot be compared as more or less")
        bound = _number(value, field) if kind == "number" else str(value or "")[:32]
        if not bound and bound != 0:
            raise HTTPException(status_code=422, detail=f"'{field}' needs a value to compare with")
        return {field: {"$gt" if op in ("gt", "after") else "$lt": bound}}
    if op == "contains":
        if kind not in ("text", "list"):
            raise HTTPException(status_code=422, detail=f"'{field}' cannot be searched for text")
        return {field: {"$regex": re.escape(str(value or "")), "$options": "i"}}
    # is / is_not
    if kind == "checkbox":
        match: Any = value is True or str(value).lower() == "true"
    elif kind == "number":
        match = _number(value, field)
    elif kind == "text":
        # Text matches whole, ignoring case: "Is: ana@x.com" finds Ana@X.com.
        match = {"$regex": f"^{re.escape(str(value or ''))}$", "$options": "i"}
    else:
        match = value
    if op == "is":
        return {field: match}
    return {field: {"$not": match}} if isinstance(match, dict) else {field: {"$ne": match}}


async def compile_filters(db, tenant_id: str, object_name: str, filters: list[dict]) -> list[dict]:
    """A view's filters as MongoDB conditions, all of which must hold.

    Only fields `field_kinds` knows are reachable, so a filter cannot steer a query at
    data the list does not show."""
    if not filters:
        return []
    kinds = await field_kinds(db, tenant_id, object_name)
    out = []
    for item in filters:
        kind = kinds.get(item["field"])
        if not kind:
            raise _unknown(item["field"])
        out.append(_condition(item["field"], kind, item["op"], item.get("value")))
    return out


def parse_where(raw: Optional[str]) -> list[dict]:
    """The `where` query parameter of a list: a JSON array of {field, op, value}."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=422, detail="where must be a JSON list of filters")
    if not isinstance(data, list) or len(data) > 20:
        raise HTTPException(status_code=422, detail="where must be a list of at most 20 filters")
    try:
        return clean_filters([ViewFilter(**item) for item in data])
    except (TypeError, ValidationError):
        raise HTTPException(status_code=422, detail="Each filter needs a field, an operator and a value")


# -------------------------------------------------------------------------- routes

def register_record_field_routes(router, db, new_id, now_iso, record_event, get_current_user, require_role):

    @router.get("/custom-fields")
    async def list_fields(object: str = "contacts", include_archived: bool = False,
                          user=Depends(get_current_user)):
        if object not in OBJECTS:
            raise HTTPException(status_code=422, detail="object must be contacts, companies or deals")
        return {"items": await definitions(db, user["tenant_id"], object, include_archived=include_archived),
                "types": list(FIELD_TYPES)}

    @router.post("/custom-fields")
    async def create_field(inp: FieldInput, user=Depends(require_role("admin"))):
        tenant = user["tenant_id"]
        count = await db[FIELD_DEFS].count_documents({"tenant_id": tenant, "object": inp.object})
        if count >= MAX_FIELDS_PER_OBJECT:
            raise HTTPException(status_code=422, detail=f"A record type can have at most {MAX_FIELDS_PER_OBJECT} fields")
        base = f"cf_{_slug(inp.label)}"
        options = clean_options(inp.type, inp.options)
        now = now_iso()
        suffix = 1
        while True:
            key = base if suffix == 1 else f"{base}_{suffix}"
            doc = {"id": new_id("fld"), "tenant_id": tenant, "object": inp.object, "key": key,
                   "label": inp.label.strip(), "type": inp.type, "options": options,
                   "help_text": (inp.help_text or "").strip() or None, "position": count,
                   "archived_at": None, "created_by": user["email"], "created_at": now,
                   "updated_at": now}
            try:
                # The unique (tenant, object, key) index decides between two admins adding
                # "Budget" at the same moment: the second gets cf_budget_2.
                await db[FIELD_DEFS].insert_one(dict(doc))
                break
            except DuplicateKeyError:
                suffix += 1
                if suffix > 50:
                    raise HTTPException(status_code=409, detail="Choose a different label")
        await record_event("custom_field.created", "custom_field", doc["id"], tenant, user["email"],
                           payload={"object": inp.object, "key": key, "type": inp.type})
        return doc

    @router.patch("/custom-fields/{field_id}")
    async def update_field(field_id: str, inp: FieldPatch, user=Depends(require_role("admin"))):
        tenant = user["tenant_id"]
        doc = await db[FIELD_DEFS].find_one({"id": field_id, "tenant_id": tenant}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        changes: dict[str, Any] = {}
        if inp.label is not None:
            changes["label"] = inp.label.strip()
        if inp.options is not None:
            changes["options"] = clean_options(doc["type"], inp.options)
        if inp.help_text is not None:
            changes["help_text"] = inp.help_text.strip() or None
        if inp.position is not None:
            changes["position"] = inp.position
        if inp.archived is not None:
            changes["archived_at"] = now_iso() if inp.archived else None
        if changes:
            await db[FIELD_DEFS].update_one({"id": field_id, "tenant_id": tenant},
                                            {"$set": {**changes, "updated_at": now_iso()}})
            await record_event("custom_field.updated", "custom_field", field_id, tenant, user["email"],
                               payload={"changed": sorted(changes)})
        return await db[FIELD_DEFS].find_one({"id": field_id, "tenant_id": tenant}, {"_id": 0})

    # ------------------------------------------------------------------ views

    def visible(user) -> dict:
        return {"tenant_id": user["tenant_id"],
                "$or": [{"shared": True}, {"owner": user["email"].lower()}]}

    @router.get("/views")
    async def list_views(object: str = "contacts", user=Depends(get_current_user)):
        if object not in OBJECTS:
            raise HTTPException(status_code=422, detail="object must be contacts, companies or deals")
        items = await db[SAVED_VIEWS].find({**visible(user), "object": object}, {"_id": 0}).sort(
            "created_at", 1).to_list(200)
        return {"items": items, "operators": list(FILTER_OPS)}

    @router.post("/views")
    async def create_view(inp: ViewInput, user=Depends(get_current_user)):
        now = now_iso()
        filters, columns = clean_filters(inp.filters), clean_columns(inp.columns)
        await check_view_fields(db, user["tenant_id"], inp.object, filters, columns)
        doc = {"id": new_id("view"), "tenant_id": user["tenant_id"], "object": inp.object,
               "name": inp.name.strip(), "filters": filters,
               "sort": inp.sort.model_dump() if inp.sort else None,
               "columns": columns, "shared": inp.shared,
               "owner": user["email"].lower(), "created_at": now, "updated_at": now}
        await db[SAVED_VIEWS].insert_one(dict(doc))
        await record_event("saved_view.created", "saved_view", doc["id"], user["tenant_id"], user["email"],
                           payload={"object": inp.object, "name": doc["name"]})
        return doc

    async def own_view(view_id: str, user) -> dict:
        doc = await db[SAVED_VIEWS].find_one({**visible(user), "id": view_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        if doc["owner"] != user["email"].lower() and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only the person who made this view or an admin can change it")
        return doc

    @router.patch("/views/{view_id}")
    async def update_view(view_id: str, inp: ViewPatch, user=Depends(get_current_user)):
        view = await own_view(view_id, user)
        changes: dict[str, Any] = {}
        if inp.name is not None:
            changes["name"] = inp.name.strip()
        if inp.filters is not None:
            changes["filters"] = clean_filters(inp.filters)
        if inp.sort is not None:
            changes["sort"] = inp.sort.model_dump()
        if inp.columns is not None:
            changes["columns"] = clean_columns(inp.columns)
        if inp.shared is not None:
            changes["shared"] = inp.shared
        if "filters" in changes or "columns" in changes:
            await check_view_fields(db, user["tenant_id"], view["object"],
                                    changes.get("filters", []), changes.get("columns"))
        if changes:
            await db[SAVED_VIEWS].update_one({"id": view_id, "tenant_id": user["tenant_id"]},
                                             {"$set": {**changes, "updated_at": now_iso()}})
        return await db[SAVED_VIEWS].find_one({"id": view_id, "tenant_id": user["tenant_id"]}, {"_id": 0})

    @router.delete("/views/{view_id}")
    async def delete_view(view_id: str, user=Depends(get_current_user)):
        await own_view(view_id, user)
        await db[SAVED_VIEWS].delete_one({"id": view_id, "tenant_id": user["tenant_id"]})
        await record_event("saved_view.deleted", "saved_view", view_id, user["tenant_id"], user["email"])
        return {"ok": True}
