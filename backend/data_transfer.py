"""Getting records in and out: a spreadsheet import with a preview, and CSV export.

A business moving to ClientVerse arrives with a spreadsheet, or an export from the CRM it
is leaving. Until now only engineering could load one, with columns named exactly as the
database names them. This module is the self-serve version, behind Settings → Import and
export:

* **Match, preview, then import.** The screen sends the file to
  `POST /api/import/{entity}/preview` and gets back every column with a suggested field
  (from its header: "E-mail", "Company Name", "Job Title" and so on) and what the import
  would do with every row. Nothing is written until the same file and the same column
  choices are sent to `POST /api/import/{entity}`, which runs the same plan for real.
* **Records are made the way the screens make them.** A contact gets the phone key website
  leads are matched on and a company linked by name or work-email domain; a company its
  domain; a deal its stage history, and its people become customers when it lands won.
  Custom fields are checked against their definitions, as an edit is.
* **A familiar row is not a second record.** A contact is matched on email, else phone; a
  company on name, else website domain; a deal on name and company. Archived records are
  not matched. The importer chooses to skip, update or create; a repeat inside the same
  file is reported against its first row.
* **An import is one event.** It records `data.imported` once and never a
  `contact.created` per row, so loading 5,000 contacts does not start 5,000 automations.
* **Tenancy holds as everywhere.** Every lookup is filtered by the caller's tenant, and an
  id from another tenant answers as unknown.

`POST /api/import/{entity}` without column choices keeps its original contract: columns
must be named as the fields are, and an unknown column is refused.
"""

from __future__ import annotations

import csv
import io
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, Field

import crm_core
import record_fields

IMPORTS = "data_imports"
ENTITIES = ("contacts", "companies", "deals")
MAX_ROWS = crm_core.MAX_IMPORT_ROWS
MAX_CSV_CHARS = 5_000_000
# What a response carries row by row. The counts are always the true totals.
SHOWN_ROWS = 100
INSERT_BATCH = 500
TIERS = ("standard", "growth", "enterprise")
TRUE_WORDS = {"yes", "y", "true", "t", "1", "x", "✓", "checked"}
FALSE_WORDS = {"no", "n", "false", "f", "0", "", "unchecked"}


@dataclass(frozen=True)
class Target:
    """A field a column can be matched to. `aliases` are headers other tools export it
    under; `hidden` targets are accepted by name through the API but not offered on screen."""
    key: str
    label: str
    aliases: tuple[str, ...] = ()
    hidden: bool = False


TARGETS: dict[str, tuple[Target, ...]] = {
    "contacts": (
        Target("name", "Name", ("full name", "contact name", "contact", "person")),
        Target("first_name", "First name", ("firstname", "given name", "first")),
        Target("last_name", "Last name", ("lastname", "surname", "family name", "last")),
        Target("email", "Email", ("e mail", "email address", "e mail address", "work email",
                                  "primary email")),
        Target("phone", "Phone", ("phone number", "mobile", "mobile phone", "mobile number", "cell",
                                  "cell phone", "telephone", "work phone")),
        Target("title", "Job title", ("position", "job")),
        Target("role", "Role"),
        Target("company", "Company", ("company name", "organization", "organisation", "account",
                                      "account name", "business")),
        Target("lifecycle", "Lifecycle stage", ("lifecycle", "stage")),
        Target("owner", "Owner", ("contact owner", "owner email", "assigned to", "sales rep")),
        Target("company_id", "Company ID", hidden=True),
    ),
    "companies": (
        Target("name", "Company name", ("company", "organization", "organisation", "account",
                                        "account name", "business", "business name")),
        Target("industry", "Industry", ("sector", "vertical")),
        Target("website", "Website", ("web site", "url", "website url", "company website", "domain")),
        Target("tier", "Client tier", ("tier", "segment")),
        Target("owner", "Owner", ("company owner", "account owner", "owner email")),
        Target("domain", "Domain", hidden=True),
    ),
    "deals": (
        Target("name", "Deal name", ("deal", "opportunity", "opportunity name", "title")),
        Target("value", "Value", ("amount", "deal value", "deal amount", "price")),
        Target("currency", "Currency"),
        Target("stage", "Stage", ("deal stage", "pipeline stage", "status")),
        Target("expected_close_date", "Expected close date", ("close date", "expected close",
                                                              "closing date")),
        Target("company", "Company", ("company name", "organization", "organisation", "account",
                                      "account name")),
        Target("contact_email", "Contact email", ("contact emails", "email", "person email",
                                                  "primary contact email")),
        Target("owner", "Owner", ("deal owner", "owner email", "assigned to", "sales rep")),
        Target("company_id", "Company ID", hidden=True),
    ),
}
# What each record type cannot be imported without, in the screen's words.
REQUIRED = {"contacts": "Name", "companies": "Company name", "deals": "Deal name"}
LIMITS = {"name": 200, "title": 160, "role": 160, "industry": 160, "website": 300, "domain": 200,
          "phone": 60}


class ImportRequest(BaseModel):
    csv: str = Field(min_length=1, max_length=MAX_CSV_CHARS)
    # Column header -> field key, or "" to leave the column out. Without it the columns must
    # be named as the fields are (the original contract of POST /api/import/{entity}).
    mapping: Optional[dict[str, str]] = None
    on_duplicate: str = "skip"  # skip | update | create
    file_name: Optional[str] = Field(default=None, max_length=200)


def normalize(text: Optional[str]) -> str:
    """`" E-mail Address "` -> `"e mail address"`: what two headers are compared as."""
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def name_key(text: Optional[str]) -> str:
    return " ".join(str(text or "").split()).lower()


def lifecycle_label(key: str) -> str:
    return key.replace("_", " ").capitalize()


def parse_csv(text: str) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """The header and the data rows of a file, each row with its spreadsheet row number.

    Reads files saved by Excel (a byte-order mark, `;` in some locales) as well as plain
    CSV. Blank headers become "Column N" and a repeated header gets " (2)", so every column
    can be told apart. Completely blank rows are dropped.
    """
    text = text.lstrip("\ufeff")
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    # The separator the header row uses most; a comma when it has none (a single column).
    delimiter = max((",", ";", "\t", "|"), key=first_line.count)
    if not first_line.count(delimiter):
        delimiter = ","
    try:
        records = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    except csv.Error as exc:
        raise HTTPException(status_code=422, detail=f"Could not read the file as CSV: {exc}")
    index = next((i for i, record in enumerate(records) if any(cell.strip() for cell in record)), None)
    if index is None:
        raise HTTPException(status_code=422, detail="The file is empty")
    headers: list[str] = []
    seen: dict[str, int] = {}
    for position, cell in enumerate(records[index], start=1):
        header = " ".join(cell.split()) or f"Column {position}"
        count = seen.get(header.lower(), 0) + 1
        seen[header.lower()] = count
        headers.append(header if count == 1 else f"{header} ({count})")
    rows = [(number, record) for number, record in enumerate(records[index + 1:], start=index + 2)
            if any(cell.strip() for cell in record)]
    if not rows:
        raise HTTPException(status_code=422, detail="The file has a header row but no data rows")
    if len(rows) > MAX_ROWS:
        raise HTTPException(status_code=422, detail=(
            f"An import can hold up to {MAX_ROWS:,} rows; this file has {len(rows):,}. "
            "Split it and import each part."))
    return headers, rows


def field_menu(entity: str, defs: list[dict]) -> list[dict]:
    """What a column can be matched to on screen: the built-in fields, then custom ones."""
    menu = [{"key": target.key, "label": target.label, "custom": False,
             "required": target.label == REQUIRED[entity]}
            for target in TARGETS[entity] if not target.hidden]
    menu += [{"key": d["key"], "label": d["label"], "custom": True, "required": False,
              "type": d.get("type")} for d in defs]
    return menu


def suggest_mapping(entity: str, headers: list[str], defs: list[dict]) -> dict[str, str]:
    """A field for each header the import recognises, never the same field twice."""
    candidates: list[tuple[str, set[str]]] = [
        (target.key, {normalize(target.key), normalize(target.label), *map(normalize, target.aliases)})
        for target in TARGETS[entity] if not target.hidden]
    candidates += [(d["key"], {normalize(d["label"]), normalize(d["key"]), normalize(d["key"][3:])})
                   for d in defs]
    used: set[str] = set()
    mapping: dict[str, str] = {}
    for header in headers:
        wanted = normalize(header)
        pick = next((key for key, names in candidates if key not in used and wanted in names), "")
        mapping[header] = pick
        if pick:
            used.add(pick)
    return mapping


def check_mapping(entity: str, headers: list[str], mapping: dict[str, str],
                  defs: list[dict]) -> dict[str, str]:
    known = {target.key for target in TARGETS[entity]} | {d["key"] for d in defs}
    labels = {target.key: target.label for target in TARGETS[entity]} | {d["key"]: d["label"] for d in defs}
    missing = [header for header in mapping if header not in headers]
    if missing:
        raise HTTPException(status_code=422, detail=f"The file has no column '{missing[0]}'")
    taken: dict[str, str] = {}
    clean: dict[str, str] = {}
    for header in headers:
        field = (mapping.get(header) or "").strip()
        if field and field not in known:
            raise HTTPException(status_code=422, detail=f"Unknown field '{field}' for {entity}")
        if field and field in taken:
            raise HTTPException(status_code=422, detail=(
                f"Two columns, '{taken[field]}' and '{header}', are matched to {labels[field]}. "
                "Match one of them to nothing."))
        if field:
            taken[field] = header
        clean[header] = field
    return clean


def exact_mapping(entity: str, headers: list[str], defs: list[dict]) -> dict[str, str]:
    """The original contract: every column is named as its field, or the import is refused."""
    known = {target.key for target in TARGETS[entity]} | {d["key"] for d in defs}
    unknown = sorted({header for header in headers if header.strip() not in known})
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown column(s): {', '.join(unknown[:10])}")
    return check_mapping(entity, headers, {header: header.strip() for header in headers}, defs)


def parse_money(text: str) -> float:
    cleaned = re.sub(r"[\s$£€¥]", "", text)
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", cleaned):
        cleaned = cleaned.replace(",", "")
    try:
        amount = float(cleaned)
    except ValueError:
        raise ValueError("value must be a number, like 1250 or 1250.50")
    if not math.isfinite(amount) or not 0 <= amount <= crm_core.MAX_DEAL_VALUE:
        raise ValueError(f"value must be a finite amount from 0 to {crm_core.MAX_DEAL_VALUE:,.0f}")
    return amount


def parse_checkbox(definition: dict, text: str) -> bool:
    word = text.strip().lower()
    if word in TRUE_WORDS:
        return True
    if word in FALSE_WORDS:
        return False
    raise ValueError(f"{definition['label']} must be yes or no")


class RowProblem(Exception):
    """A row that cannot be imported, with the reason shown beside it."""


class Importer:
    def __init__(self, db: Any, *, new_id: Callable[[str], str], now_iso: Callable[[], str],
                 record_event: Callable[..., Any]):
        self.db = db
        self.new_id = new_id
        self.now_iso = now_iso
        self.record_event = record_event

    # ------------------------------------------------------------------- the run

    async def run(self, entity: str, request: ImportRequest, user: dict, *, commit: bool) -> dict:
        if entity not in ENTITIES:
            raise HTTPException(status_code=404, detail="Unknown import")
        if request.on_duplicate not in ("skip", "update", "create"):
            raise HTTPException(status_code=422, detail="on_duplicate must be skip, update or create")
        tenant, actor = user["tenant_id"], user["email"]
        headers, rows = parse_csv(request.csv)
        defs = await record_fields.definitions(self.db, tenant, entity)
        if request.mapping is not None:
            mapping = check_mapping(entity, headers, request.mapping, defs)
        elif commit:
            mapping = exact_mapping(entity, headers, defs)
        else:
            mapping = suggest_mapping(entity, headers, defs)
        mapped = set(mapping.values())
        name_fields = {"name", "first_name", "last_name"} if entity == "contacts" else {"name"}
        missing_required = [] if mapped & name_fields else [REQUIRED[entity]]
        if commit and request.mapping is not None and missing_required:
            raise HTTPException(status_code=422,
                                detail=f"Match a column to {missing_required[0]} before importing")

        run = Run(self, entity, tenant, actor, request.on_duplicate, commit,
                  import_id=self.new_id("imp"), defs=defs)
        await run.load_context()
        for number, record in rows:
            cells = {header: (record[position].strip() if position < len(record) else "")
                     for position, header in enumerate(headers)}
            values = {field: cells[header] for header, field in mapping.items() if field and cells[header]}
            await run.row(number, values)
        await run.finish()

        result = run.summary()
        if commit:
            await self.db[IMPORTS].insert_one({
                "id": run.import_id, "tenant_id": tenant, "entity": entity, "actor": actor,
                "file_name": request.file_name, "on_duplicate": request.on_duplicate,
                "created_at": self.now_iso(), "rows": len(rows),
                **{key: result[key] for key in ("created", "updated", "skipped", "rejected",
                                                "companies_created")},
                "mapping": {header: field for header, field in mapping.items() if field}})
            await self.record_event("data.imported", entity, run.import_id, tenant, actor,
                                    payload={key: result[key] for key in (
                                        "created", "updated", "skipped", "rejected", "companies_created")})
            return {"entity": entity, "import_id": run.import_id, **result}
        samples: dict[str, list[str]] = {header: [] for header in headers}
        for _number, record in rows:
            for position, header in enumerate(headers):
                cell = record[position].strip() if position < len(record) else ""
                if cell and len(samples[header]) < 3:
                    samples[header].append(cell[:80])
        return {
            "entity": entity, "file_name": request.file_name, "rows": len(rows),
            "on_duplicate": request.on_duplicate, "missing": missing_required,
            "columns": [{"header": header, "field": mapping.get(header, ""), "samples": samples[header]}
                        for header in headers],
            "fields": field_menu(entity, defs),
            **result,
        }

    async def recent(self, tenant: str, limit: int) -> list[dict]:
        items: list[dict] = await self.db[IMPORTS].find({"tenant_id": tenant}, {"_id": 0, "mapping": 0}).sort(
            "created_at", -1).to_list(limit)
        return items


class Run:
    """One pass over a file: a plan when previewing, the import itself when committing."""

    def __init__(self, importer: Importer, entity: str, tenant: str, actor: str, on_duplicate: str,
                 commit: bool, *, import_id: str, defs: list[dict]):
        self.importer, self.db = importer, importer.db
        self.entity, self.tenant, self.actor = entity, tenant, actor
        self.on_duplicate, self.commit, self.import_id = on_duplicate, commit, import_id
        self.defs = {d["key"]: d for d in defs}
        self.counts = {"create": 0, "update": 0, "skip": 0, "reject": 0}
        self.companies_created = 0
        self.plan: list[dict] = []
        self.errors: list[dict] = []
        self.warnings: list[dict] = []
        self.warning_count = 0
        self.pending: list[dict] = []
        self.won_contacts: list[str] = []
        self.seen: dict[tuple[str, str], int] = {}

    # ------------------------------------------------------------------ context

    async def load_context(self) -> None:
        """Everything a row is matched against, read once rather than once per row."""
        db, tenant = self.db, self.tenant
        live = {"tenant_id": tenant, "archived_at": None}
        self.members = {m["email"].lower(): m["email"] for m in await db.memberships.find(
            {"tenant_id": tenant, "status": "active"}, {"_id": 0, "email": 1}).to_list(1000) if m.get("email")}
        self.companies_by_name: dict[str, dict] = {}
        self.companies_by_domain: dict[str, dict] = {}
        async for company in db[crm_core.COMPANIES].find(live, {"_id": 0, "id": 1, "name": 1, "domain": 1,
                                                                 "website": 1}):
            self.companies_by_name.setdefault(name_key(company.get("name")), company)
            domain = company.get("domain") or crm_core.website_domain(company.get("website"))
            if domain:
                self.companies_by_domain.setdefault(domain, company)
        self.contacts_by_email: dict[str, dict] = {}
        self.contacts_by_phone: dict[str, dict] = {}
        if self.entity in ("contacts", "deals"):
            async for contact in db[crm_core.CONTACTS].find(live, {"_id": 0, "id": 1, "name": 1, "email": 1,
                                                                    "phone_digits": 1}):
                if contact.get("email"):
                    self.contacts_by_email.setdefault(contact["email"].strip().lower(), contact)
                if len(contact.get("phone_digits") or "") >= 7:
                    self.contacts_by_phone.setdefault(contact["phone_digits"], contact)
        self.deals_by_key: dict[tuple[str, str], dict] = {}
        self.stages: list[dict] = []
        if self.entity == "deals":
            async for deal in db[crm_core.DEALS].find(live, {"_id": 0, "id": 1, "name": 1, "company_id": 1,
                                                              "stage": 1, "contact_ids": 1}):
                self.deals_by_key.setdefault((name_key(deal.get("name")), deal.get("company_id") or ""), deal)
            self.stages = await crm_core.resolve_stages(db, tenant)
            self.won = (await crm_core.stage_classes(db, tenant))[crm_core.STAGE_WON]

    # --------------------------------------------------------------------- rows

    async def row(self, number: int, values: dict[str, str]) -> None:
        warnings: list[str] = []
        try:
            fields, custom, label = await self.build(values, warnings)
            identity, existing, how = self.identify(fields, values)
        except RowProblem as problem:
            self.record(number, "reject", values.get("name") or self.display(values), str(problem), warnings)
            return
        first = self.seen.get(identity) if identity else None
        if first and self.on_duplicate != "create":
            self.record(number, "skip", label, f"Same as row {first} in this file", warnings)
            return
        if existing and self.on_duplicate == "skip":
            if identity:
                self.seen.setdefault(identity, number)
            self.record(number, "skip", label, f"Already in ClientVerse as “{existing.get('name')}” ({how})",
                        warnings)
            return
        try:
            fields = await self.resolve_company(fields, values, warnings)
        except RowProblem as problem:
            self.record(number, "reject", label, str(problem), warnings)
            return
        # Only a row that goes in is the one later repeats are reported against.
        if identity:
            self.seen.setdefault(identity, number)
        if existing and self.on_duplicate == "update":
            if self.commit:
                await self.update(existing, fields, custom, number)
            self.record(number, "update", label, f"Updates “{existing.get('name')}” ({how})", warnings)
            return
        if self.commit:
            await self.create(fields, custom, number)
        self.record(number, "create", label, None, warnings)

    def display(self, values: dict[str, str]) -> str:
        return (" ".join(part for part in (values.get("first_name"), values.get("last_name")) if part)
                or values.get("email") or values.get("name") or "")

    def record(self, number: int, action: str, label: str, reason: Optional[str], warnings: list[str]) -> None:
        self.counts[action] += 1
        if action == "reject":
            if len(self.errors) < SHOWN_ROWS:
                self.errors.append({"row": number, "error": reason, "label": label})
        for warning in warnings:
            self.warning_count += 1
            if len(self.warnings) < SHOWN_ROWS:
                self.warnings.append({"row": number, "warning": warning, "label": label})
        if len(self.plan) < SHOWN_ROWS:
            self.plan.append({"row": number, "action": action, "label": label, "reason": reason,
                              "warnings": warnings})

    # ------------------------------------------------------------- build a row

    async def build(self, values: dict[str, str], warnings: list[str]) -> tuple[dict, dict, str]:
        """The record's own fields and custom values from one row, or a RowProblem."""
        fields: dict[str, Any] = {}
        for key in ("name", "title", "role", "industry", "website", "domain", "phone"):
            if values.get(key):
                if len(values[key]) > LIMITS[key]:
                    raise RowProblem(f"{key.replace('_', ' ')} is longer than {LIMITS[key]} characters")
                fields[key] = values[key]
        if self.entity == "contacts":
            if not fields.get("name"):
                joined = " ".join(part for part in (values.get("first_name"), values.get("last_name")) if part)
                if joined:
                    fields["name"] = joined[:LIMITS["name"]]
            if values.get("email"):
                if not record_fields.EMAIL.match(values["email"]) or len(values["email"]) > 254:
                    raise RowProblem(f"“{values['email']}” is not an email address")
                fields["email"] = values["email"]
            if "phone" in fields:
                fields["phone_digits"] = crm_core.phone_digits(fields["phone"]) or None
            if values.get("lifecycle"):
                fields["lifecycle"] = self.lifecycle(values["lifecycle"])
        if self.entity == "companies":
            if fields.get("website") and not fields.get("domain"):
                fields["domain"] = crm_core.website_domain(fields["website"])
            if values.get("tier"):
                tier = values["tier"].strip().lower()
                if tier not in TIERS:
                    raise RowProblem("client tier must be Standard, Growth or Enterprise")
                fields["tier"] = tier
        if self.entity == "deals":
            if values.get("value"):
                try:
                    fields["value"] = parse_money(values["value"])
                except ValueError as exc:
                    raise RowProblem(str(exc))
            if values.get("currency"):
                currency = values["currency"].strip().upper()
                if not re.match(crm_core.CURRENCY_PATTERN, currency):
                    raise RowProblem("currency must be a 3-letter code such as USD")
                fields["currency"] = currency
            if values.get("stage"):
                fields["stage"] = self.stage(values["stage"])
            if values.get("expected_close_date"):
                try:
                    fields["expected_close_date"] = crm_core.parse_date(values["expected_close_date"],
                                                                        "expected_close_date")
                except HTTPException:
                    raise RowProblem("expected close date must be a date written YYYY-MM-DD")
            if values.get("contact_email"):
                ids = []
                for email in re.split(r"[;,\s]+", values["contact_email"]):
                    contact = self.contacts_by_email.get(email.strip().lower()) if email.strip() else None
                    if contact:
                        ids.append(contact["id"])
                    elif email.strip():
                        warnings.append(f"No contact has the email {email.strip()}, so the deal has no "
                                        "person for it")
                fields["contact_ids"] = list(dict.fromkeys(ids))[:100]
        if not fields.get("name"):
            raise RowProblem(f"missing {REQUIRED[self.entity].lower()}")
        if values.get("owner"):
            owner = self.members.get(values["owner"].strip().lower())
            if owner:
                fields["owner"] = owner
            else:
                warnings.append(f"{values['owner']} is not on your team, so {self.actor} is the owner")
        custom: dict[str, Any] = {}
        for key, definition in self.defs.items():
            if key not in values:
                continue
            try:
                raw: Any = values[key]
                if definition.get("type") == "checkbox":
                    raw = parse_checkbox(definition, raw)
                custom[key] = record_fields.coerce(definition, raw)
            except ValueError as exc:
                raise RowProblem(str(exc))
            except HTTPException as exc:
                raise RowProblem(str(exc.detail))
        return fields, custom, fields["name"]

    def lifecycle(self, text: str) -> str:
        wanted = normalize(text)
        for key in crm_core.LIFECYCLE_STAGES:
            if wanted in (normalize(key), normalize(lifecycle_label(key))):
                return key
        raise RowProblem("lifecycle stage must be one of "
                         + ", ".join(lifecycle_label(key) for key in crm_core.LIFECYCLE_STAGES))

    def stage(self, text: str) -> str:
        wanted = name_key(text)
        for stage in self.stages:
            if wanted in (name_key(stage["key"]), name_key(stage.get("label"))):
                return str(stage["key"])
        raise RowProblem(f"unknown stage '{text}'; your stages are "
                         + ", ".join(stage.get("label") or stage["key"] for stage in self.stages))

    # ---------------------------------------------------------------- matching

    def identify(self, fields: dict, values: dict) -> tuple[Optional[tuple[str, str]], Optional[dict], str]:
        """(this row's identity, the live record it matches, how it matched)."""
        if self.entity == "contacts":
            email = (fields.get("email") or "").lower()
            if email:
                return ("email", email), self.contacts_by_email.get(email), "same email"
            digits = fields.get("phone_digits") or ""
            if len(digits) >= 7:
                return ("phone", digits), self.contacts_by_phone.get(digits), "same phone"
            return None, None, ""
        if self.entity == "companies":
            key = name_key(fields["name"])
            if key in self.companies_by_name:
                return ("name", key), self.companies_by_name[key], "same name"
            domain = fields.get("domain")
            if domain and domain in self.companies_by_domain:
                return ("name", key), self.companies_by_domain[domain], "same website"
            return ("name", key), None, ""
        # A repeat in the file is told by the company as written, so two rows about a deal at
        # a company this import is about to make are still the same deal.
        deal = name_key(fields["name"])
        company_id = values.get("company_id") or ""
        written = company_id
        if not company_id and values.get("company"):
            written = "name:" + name_key(values["company"])
            known = self.companies_by_name.get(name_key(values["company"]))
            company_id = known["id"] if known else None
        existing = self.deals_by_key.get((deal, company_id)) if company_id is not None else None
        return ("deal", f"{deal}|{written}"), existing, "same name and company"

    async def resolve_company(self, fields: dict, values: dict, warnings: list[str]) -> dict:
        """The row's company: an id named outright, a company matched or made from its name,
        or for a contact the company its work email's domain belongs to."""
        if self.entity == "companies":
            return fields
        if values.get("company_id"):
            exists = await self.db[crm_core.COMPANIES].find_one(
                {"id": values["company_id"], "tenant_id": self.tenant}, {"_id": 1})
            if not exists:
                raise RowProblem(f"unknown company_id '{values['company_id']}'")
            return {**fields, "company_id": values["company_id"]}
        if values.get("company"):
            name = " ".join(values["company"].split())
            if len(name) > LIMITS["name"]:
                raise RowProblem(f"company is longer than {LIMITS['name']} characters")
            known = self.companies_by_name.get(name_key(name))
            if not known:
                known = await self.new_company(name, fields)
            return {**fields, "company_id": known["id"]}
        if self.entity == "contacts":
            domain = crm_core.business_domain(fields.get("email"))
            known = self.companies_by_domain.get(domain) if domain else None
            if known:
                return {**fields, "company_id": known["id"]}
        return fields

    async def new_company(self, name: str, fields: dict) -> dict:
        """A company the file names that does not exist yet: made once, however many rows name it."""
        now = self.importer.now_iso()
        domain = crm_core.business_domain(fields.get("email")) if self.entity == "contacts" else None
        company = {"id": self.importer.new_id("co"), "tenant_id": self.tenant, "name": name,
                   "industry": None, "website": None, "domain": domain, "tier": "standard",
                   "owner": fields.get("owner") or self.actor, "created_at": now, "updated_at": now,
                   "archived_at": None, "source": {"kind": "import", "import_id": self.import_id},
                   "history": [crm_core._history_entry("created", self.actor,
                                                       {"via": "import", "import_id": self.import_id})]}
        if self.commit:
            await self.db[crm_core.COMPANIES].insert_one(dict(company))
        self.companies_by_name[name_key(name)] = company
        if domain:
            self.companies_by_domain.setdefault(domain, company)
        self.companies_created += 1
        return company

    # ----------------------------------------------------------------- writing

    async def create(self, fields: dict, custom: dict, number: int) -> None:
        now = self.importer.now_iso()
        prefix = {"contacts": "ct", "companies": "co", "deals": "opp"}[self.entity]
        doc: dict[str, Any] = {
            "id": self.importer.new_id(prefix), "tenant_id": self.tenant, "created_at": now,
            "updated_at": now, "archived_at": None, "owner": self.actor,
            "source": {"kind": "import", "import_id": self.import_id},
            "history": [crm_core._history_entry("created", self.actor,
                                                {"via": "import", "import_id": self.import_id, "row": number})],
        }
        if self.entity == "contacts":
            doc.update({"name": None, "email": None, "phone": None, "phone_digits": None, "title": None,
                        "role": None, "company_id": None, "influence": "medium", "sentiment": "neutral",
                        "lifecycle": None, "lead_source": "import"})
        elif self.entity == "companies":
            doc.update({"industry": None, "website": None, "domain": None, "tier": "standard"})
        else:
            stage = fields.get("stage") or next(
                (s["key"] for s in self.stages if not s.get("is_closed")), self.stages[0]["key"])
            doc.update({"company_id": None, "value": 0.0, "currency": "USD", "expected_close_date": None,
                        "contact_ids": [], "lead_source": "import",
                        "stage_history": [{"from": None, "to": stage, "at": now, "actor": self.actor}]})
            fields = {**fields, "stage": stage}
        doc.update(fields)
        if custom:
            doc["custom_fields"] = custom
        self.remember(doc)
        self.pending.append(doc)
        if self.entity == "deals" and doc["stage"] in self.won and doc.get("contact_ids"):
            self.won_contacts += doc["contact_ids"]
        if len(self.pending) >= INSERT_BATCH:
            await self.flush()

    async def update(self, existing: dict, fields: dict, custom: dict, number: int) -> None:
        collection = {"contacts": crm_core.CONTACTS, "companies": crm_core.COMPANIES,
                      "deals": crm_core.DEALS}[self.entity]
        now = self.importer.now_iso()
        # People named for a deal join the ones already on it; an import never takes anyone off.
        added_people = fields.pop("contact_ids", None) or []
        # The same address in other capitals is the address already stored.
        if (fields.get("email") or "").lower() == (existing.get("email") or "").lower():
            fields.pop("email", None)
        changes = {**fields, "updated_at": now, **{f"custom_fields.{key}": value for key, value in custom.items()}}
        update: dict[str, Any] = {"$set": changes, "$push": {"history": crm_core._history_entry(
            "imported", self.actor, {"import_id": self.import_id, "row": number,
                                     "fields": sorted([*fields, *custom, *(["contact_ids"] if added_people else [])])})}}
        if added_people:
            update["$addToSet"] = {"contact_ids": {"$each": added_people}}
        if self.entity == "deals":
            stage = fields.get("stage") or existing.get("stage")
            if fields.get("stage") and fields["stage"] != existing.get("stage"):
                update["$push"]["stage_history"] = {"from": existing.get("stage"), "to": fields["stage"],
                                                    "at": now, "actor": self.actor}
                if stage in self.won:
                    self.won_contacts += [*(existing.get("contact_ids") or []), *added_people]
            elif added_people and stage in self.won:
                self.won_contacts += added_people
        await self.db[collection].update_one({"id": existing["id"], "tenant_id": self.tenant}, update)

    def remember(self, doc: dict) -> None:
        """A record this import made, so a later row naming it finds it."""
        if self.entity == "contacts":
            if doc.get("email"):
                self.contacts_by_email.setdefault(doc["email"].lower(), doc)
            if len(doc.get("phone_digits") or "") >= 7:
                self.contacts_by_phone.setdefault(doc["phone_digits"], doc)
        elif self.entity == "companies":
            self.companies_by_name.setdefault(name_key(doc["name"]), doc)
            if doc.get("domain"):
                self.companies_by_domain.setdefault(doc["domain"], doc)

    async def flush(self) -> None:
        if self.pending:
            collection = {"contacts": crm_core.CONTACTS, "companies": crm_core.COMPANIES,
                          "deals": crm_core.DEALS}[self.entity]
            await self.db[collection].insert_many([dict(doc) for doc in self.pending])
            self.pending = []

    async def finish(self) -> None:
        if not self.commit:
            return
        await self.flush()
        if self.won_contacts:
            await crm_core.promote_to_customers(self.db, self.tenant, self.won_contacts, self.actor)

    def summary(self) -> dict:
        return {
            "created": self.counts["create"], "updated": self.counts["update"],
            "skipped": self.counts["skip"], "rejected": self.counts["reject"],
            "companies_created": self.companies_created, "warning_count": self.warning_count,
            "errors": self.errors, "warnings": self.warnings, "plan": self.plan,
        }


# ------------------------------------------------------------------------- export

BASE_EXPORT = {
    "contacts": ["id", "name", "email", "phone", "title", "role", "company", "company_id", "lifecycle",
                 "owner", "created_at", "archived_at"],
    "companies": ["id", "name", "industry", "website", "domain", "tier", "owner", "annual_value",
                  "created_at", "archived_at"],
    "deals": ["id", "name", "value", "currency", "stage", "expected_close_date", "company", "company_id",
              "contact_email", "owner", "created_at", "archived_at"],
    "tasks": ["id", "title", "assignee", "due_date", "status", "priority", "related_type", "related_id",
              "created_at"],
}


async def export_csv(db: Any, entity: str, tenant: str, *, include_archived: bool) -> tuple[str, int]:
    """One record type as CSV, with its company and people by name and its custom fields by
    label, so the file reads in a spreadsheet and imports straight back."""
    collection = {"contacts": crm_core.CONTACTS, "companies": crm_core.COMPANIES,
                  "deals": crm_core.DEALS, "tasks": crm_core.TASKS}[entity]
    query: dict[str, Any] = {"tenant_id": tenant}
    if not include_archived:
        query["archived_at"] = None
    rows = await db[collection].find(query, {"_id": 0}).sort("created_at", -1).to_list(50000)
    defs = await record_fields.definitions(db, tenant, entity) if entity in ENTITIES else []
    columns = list(BASE_EXPORT[entity])
    custom_headers: list[tuple[str, dict]] = []
    taken = {column.lower() for column in columns}
    for definition in defs:
        header = definition["label"]
        if header.lower() in taken:
            header = f"{header} (field)"
        taken.add(header.lower())
        custom_headers.append((header, definition))
    company_names: dict[str, str] = {}
    contact_emails: dict[str, str] = {}
    if entity in ("contacts", "deals"):
        ids = list({row["company_id"] for row in rows if row.get("company_id")})
        async for company in db[crm_core.COMPANIES].find({"tenant_id": tenant, "id": {"$in": ids}},
                                                         {"_id": 0, "id": 1, "name": 1}):
            company_names[company["id"]] = company.get("name") or ""
    if entity == "deals":
        ids = list({cid for row in rows for cid in row.get("contact_ids") or []})
        async for contact in db[crm_core.CONTACTS].find({"tenant_id": tenant, "id": {"$in": ids}},
                                                        {"_id": 0, "id": 1, "email": 1}):
            contact_emails[contact["id"]] = contact.get("email") or ""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns + [header for header, _ in custom_headers])
    for row in rows:
        derived = {
            "company": company_names.get(row.get("company_id") or "", ""),
            "contact_email": "; ".join(filter(None, (contact_emails.get(cid) for cid in row.get("contact_ids") or []))),
        }
        line = [crm_core.csv_safe(derived[column] if column in derived else row.get(column, ""))
                for column in columns]
        for _header, definition in custom_headers:
            value = (row.get("custom_fields") or {}).get(definition["key"])
            if isinstance(value, bool):
                value = "yes" if value else "no"
            line.append(crm_core.csv_safe(value))
        writer.writerow(line)
    return buffer.getvalue(), len(rows)


# ------------------------------------------------------------------------- routes

def register_data_transfer_routes(router: Any, db: Any, *, new_id: Callable[[str], str],
                                  now_iso: Callable[[], str], record_event: Callable[..., Any],
                                  get_current_user: Any, require_role: Any) -> Importer:
    admin = require_role("admin")
    importer = Importer(db, new_id=new_id, now_iso=now_iso, record_event=record_event)

    @router.post("/import/{entity}/preview")
    async def preview_import(entity: str, inp: ImportRequest, user: dict = Depends(admin)) -> dict:
        """What importing this file would do, row by row. Nothing is written."""
        return await importer.run(entity, inp, user, commit=False)

    @router.post("/import/{entity}")
    async def import_records(entity: str, inp: ImportRequest, user: dict = Depends(admin)) -> dict:
        """Import records from CSV.

        Strict where it matters: an unknown column (without column choices), a row that fails
        validation, or a reference to a record in another tenant is reported per row rather
        than silently dropped. A half-finished import you cannot see is worse than a refused one.
        """
        return await importer.run(entity, inp, user, commit=True)

    @router.get("/imports")
    async def recent_imports(limit: int = 10, user: dict = Depends(admin)) -> dict:
        return {"items": await importer.recent(user["tenant_id"], max(1, min(limit, 50)))}

    @router.get("/export/{entity}")
    async def export_entity(entity: str, include_archived: bool = False,
                            user: dict = Depends(get_current_user)) -> Response:
        """One record type as CSV.

        A CRM you cannot get your data out of is a CRM you cannot trust, so this is a plain,
        complete, tenant-scoped dump rather than a sampled report.
        """
        if entity not in BASE_EXPORT:
            raise HTTPException(status_code=404, detail="Unknown export")
        content, count = await export_csv(db, entity, user["tenant_id"], include_archived=include_archived)
        await record_event("data.exported", entity, entity, user["tenant_id"], user["email"],
                           payload={"rows": count})
        return Response(content=content, media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{entity}.csv"'})

    return importer
