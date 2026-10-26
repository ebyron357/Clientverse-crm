"""Import and export: a workspace brings its own spreadsheet in, and gets its data out.

The import screen sends a file to the preview, lets the admin match columns to fields,
then imports the same file. These tests hold the promises the screen makes: the preview
writes nothing, imported records are made the way the screens make them, a familiar row is
not a second record, custom fields are checked, an import starts no automations, and one
workspace never sees or matches another's records. They run against the live server over
HTTP, as the other record tests do, plus a few pure checks of the file reader.
"""

import csv
import io
import os
import uuid

import pytest
import requests
from fastapi import HTTPException

import data_transfer

BASE = os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"
API = f"{BASE}/api"
TIMEOUT = 30


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _register(prefix):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    response = requests.post(f"{API}/auth/register", timeout=TIMEOUT,
                             json={"email": email, "password": "DataTransfer2026!!", "name": "Import Test"})
    assert response.status_code == 200, response.text
    body = response.json()
    return body.get("token") or body["access_token"], email


class Workspace:
    def __init__(self, prefix="imp"):
        self.token, self.email = _register(prefix)
        self.h = _h(self.token)
        self.tag = uuid.uuid4().hex[:6]

    def call(self, method, path, expect=200, **kwargs):
        response = requests.request(method, f"{API}{path}", headers=self.h, timeout=TIMEOUT, **kwargs)
        assert response.status_code == expect, f"{method} {path} -> {response.status_code} {response.text}"
        return response.json() if response.headers.get("content-type", "").startswith("application/json") else response

    def preview(self, entity, text, **body):
        return self.call("POST", f"/import/{entity}/preview", json={"csv": text, **body})

    def imports(self, entity, text, **body):
        return self.call("POST", f"/import/{entity}", json={"csv": text, **body})

    def contacts(self):
        return self.call("GET", "/contacts", params={"limit": 1000})


@pytest.fixture()
def ws():
    return Workspace()


def _mapping(preview):
    return {column["header"]: column["field"] for column in preview["columns"]}


# --------------------------------------------------------------------- the preview

def test_the_preview_matches_columns_from_their_headers_and_writes_nothing(ws):
    text = ("First Name,Last Name,E-mail,Phone Number,Company Name,Lifecycle Stage,Favourite colour\n"
            f"Ada,Lovelace,ada_{ws.tag}@analytical.example,(555) 010-0001,Analytical {ws.tag},Qualified,Blue\n"
            f"Alan,Turing,alan_{ws.tag}@bletchley.example,,Bletchley {ws.tag},Lead,Green\n")
    preview = ws.preview("contacts", text, file_name="people.csv")
    assert _mapping(preview) == {
        "First Name": "first_name", "Last Name": "last_name", "E-mail": "email",
        "Phone Number": "phone", "Company Name": "company", "Lifecycle Stage": "lifecycle",
        "Favourite colour": ""}
    assert preview["rows"] == 2 and preview["created"] == 2 and preview["missing"] == []
    assert preview["companies_created"] == 2
    assert [row["label"] for row in preview["plan"]] == ["Ada Lovelace", "Alan Turing"]
    assert preview["columns"][0]["samples"] == ["Ada", "Alan"]
    assert {field["key"] for field in preview["fields"]} >= {"name", "email", "company", "lifecycle"}
    # Nothing was written: no contact, no company.
    assert not [c for c in ws.contacts() if ws.tag in (c.get("email") or "")]
    assert not [c for c in ws.call("GET", "/companies") if ws.tag in c["name"]]


def test_the_preview_says_when_nothing_is_matched_to_the_name(ws):
    preview = ws.preview("contacts", "Email\nnobody@example.com\n", mapping={"Email": "email"})
    assert preview["missing"] == ["Name"]
    assert preview["rejected"] == 1 and preview["errors"][0]["error"] == "missing name"
    refused = requests.post(f"{API}/import/contacts", headers=ws.h, timeout=TIMEOUT,
                            json={"csv": "Email\nnobody@example.com\n", "mapping": {"Email": "email"}})
    assert refused.status_code == 422 and "Name" in refused.json()["detail"]


def test_a_mapping_must_name_real_columns_and_fields_once_each(ws):
    text = "Name,Mail,Other mail\nA,a@example.com,b@example.com\n"
    for mapping, words in (({"Name": "name", "Nope": "email"}, "no column"),
                           ({"Name": "name", "Mail": "not_a_field"}, "Unknown field"),
                           ({"Name": "name", "Mail": "email", "Other mail": "email"}, "Two columns")):
        response = requests.post(f"{API}/import/contacts/preview", headers=ws.h, timeout=TIMEOUT,
                                 json={"csv": text, "mapping": mapping})
        assert response.status_code == 422 and words in response.json()["detail"], (mapping, response.text)


# ----------------------------------------------------------------- the import

def test_imported_contacts_are_made_the_way_the_screens_make_them(ws):
    text = ("Full name,Email,Mobile,Company,Stage\n"
            f"Grace Hopper,grace_{ws.tag}@navy.example, (555) 010-0002 ,Navy {ws.tag},Former customer\n"
            f"Hedy Lamarr,hedy_{ws.tag}@navy.example,,navy {ws.tag},customer\n")
    preview = ws.preview("contacts", text)
    result = ws.imports("contacts", text, mapping=_mapping(preview), file_name="team.csv")
    assert (result["created"], result["rejected"], result["companies_created"]) == (2, 0, 1)
    people = {c["name"]: c for c in ws.contacts() if ws.tag in (c.get("email") or "")}
    grace, hedy = people["Grace Hopper"], people["Hedy Lamarr"]
    # The phone key website leads are matched on, and the source the contact page shows.
    assert grace["phone"] == "(555) 010-0002" and grace["phone_digits"] == "5550100002"
    assert grace["lead_source"] == "import" and grace["source"]["import_id"] == result["import_id"]
    assert (grace["lifecycle"], hedy["lifecycle"]) == ("former_customer", "customer")
    # One company, whatever case the file wrote it in, made once and linked to both.
    navy = [c for c in ws.call("GET", "/companies") if c["name"].lower() == f"navy {ws.tag}"]
    assert len(navy) == 1 and grace["company_id"] == hedy["company_id"] == navy[0]["id"]
    assert grace["history"][0]["action"] == "created" and grace["history"][0]["detail"]["via"] == "import"
    assert grace["owner"] == ws.email
    recent = ws.call("GET", "/imports")["items"]
    assert recent[0]["id"] == result["import_id"] and recent[0]["file_name"] == "team.csv"
    assert recent[0]["created"] == 2


def test_a_contact_without_a_company_column_joins_the_company_of_their_work_email(ws):
    company = ws.call("POST", "/companies", json={"name": f"Northwind {ws.tag}",
                                                  "website": f"https://www.northwind{ws.tag}.example/about"})
    ws.call("PATCH", f"/companies/{company['id']}", json={"domain": f"northwind{ws.tag}.example"})
    text = f"name,email\nBob Ross,bob@northwind{ws.tag}.example\nPat Personal,pat_{ws.tag}@gmail.com\n"
    assert ws.imports("contacts", text)["created"] == 2
    people = {c["name"]: c for c in ws.contacts() if c["name"] in ("Bob Ross", "Pat Personal")}
    assert people["Bob Ross"]["company_id"] == company["id"]
    assert people["Pat Personal"].get("company_id") is None


def test_a_familiar_row_is_skipped_updated_or_created_as_the_importer_chooses(ws):
    existing = ws.call("POST", "/contacts", json={"name": "Existing Person", "email": f"known_{ws.tag}@example.com"})
    text = (f"name,email,title\nExisting Person,KNOWN_{ws.tag}@example.com,Director\n"
            f"Someone New,new_{ws.tag}@example.com,Analyst\n"
            f"Someone New again,new_{ws.tag}@example.com,Analyst\n")
    skip = ws.preview("contacts", text, mapping={"name": "name", "email": "email", "title": "title"})
    assert [row["action"] for row in skip["plan"]] == ["skip", "create", "skip"]
    assert "Existing Person" in skip["plan"][0]["reason"] and skip["plan"][2]["reason"] == "Same as row 3 in this file"

    result = ws.imports("contacts", text, on_duplicate="update",
                        mapping={"name": "name", "email": "email", "title": "title"})
    assert (result["created"], result["updated"], result["skipped"]) == (1, 1, 1)
    updated = ws.call("GET", f"/contacts/{existing['id']}")["contact"]
    assert updated["title"] == "Director" and updated["history"][-1]["action"] == "imported"
    assert len([c for c in ws.contacts() if c.get("email") == f"new_{ws.tag}@example.com"]) == 1


def test_a_repeat_of_a_rejected_row_is_imported_rather_than_skipped(ws):
    long_company = "C" * 201
    text = (f"name,email,company\nFirst Try,again_{ws.tag}@example.com,{long_company}\n"
            f"Second Try,again_{ws.tag}@example.com,Short Co {ws.tag}\n")
    result = ws.imports("contacts", text)
    assert (result["created"], result["rejected"], result["skipped"]) == (1, 1, 0)
    assert "company is longer than 200 characters" in result["errors"][0]["error"]


def test_a_bad_value_rejects_its_row_with_the_reason_and_keeps_the_rest(ws):
    text = (f"name,email,lifecycle,owner\nGood One,good_{ws.tag}@example.com,lead,{ws.email}\n"
            "Bad Mail,not-an-email,,\n"
            f"Bad Stage,bad_{ws.tag}@example.com,prospect,\n"
            f"Stranger Owner,stranger_{ws.tag}@example.com,,someone@elsewhere.example\n")
    result = ws.imports("contacts", text)
    assert (result["created"], result["rejected"]) == (2, 2)
    errors = {error["row"]: error["error"] for error in result["errors"]}
    assert "not an email address" in errors[3] and "lifecycle stage must be one of" in errors[4]
    # An owner who is not on the team is not refused: the importer owns the record instead.
    assert result["warnings"][0]["row"] == 5 and "not on your team" in result["warnings"][0]["warning"]
    stranger = [c for c in ws.contacts() if c["name"] == "Stranger Owner"][0]
    assert stranger["owner"] == ws.email


def test_custom_fields_are_imported_as_their_type_and_checked_like_an_edit(ws):
    budget = ws.call("POST", "/custom-fields", json={"object": "contacts", "label": "Budget", "type": "number"})
    approved = ws.call("POST", "/custom-fields", json={"object": "contacts", "label": "Pre-approved",
                                                       "type": "checkbox"})
    area = ws.call("POST", "/custom-fields", json={"object": "contacts", "label": "Area", "type": "select",
                                                   "options": ["North", "South"]})
    text = ("Name,Budget,Pre-approved,Area\n"
            "Fine Row,450000,yes,North\nBad Number,lots,no,South\nBad Choice,1,no,East\n")
    preview = ws.preview("contacts", text)
    assert _mapping(preview) == {"Name": "name", "Budget": budget["key"], "Pre-approved": approved["key"],
                                 "Area": area["key"]}
    result = ws.imports("contacts", text, mapping=_mapping(preview))
    assert (result["created"], result["rejected"]) == (1, 2)
    assert {e["row"]: e["error"] for e in result["errors"]} == {
        3: "Budget must be a number", 4: "Area must be one of its options"}
    fine = [c for c in ws.contacts() if c["name"] == "Fine Row"][0]
    assert fine["custom_fields"] == {budget["key"]: 450000.0, approved["key"]: True, area["key"]: "North"}


def test_deals_take_stage_labels_money_as_written_and_their_people(ws):
    person = ws.call("POST", "/contacts", json={"name": "Deal Person", "email": f"buyer_{ws.tag}@example.com"})
    text = ("Deal,Amount,Deal stage,Close date,Company,Contact email\n"
            f"Big Win {ws.tag},\"$1,250.50\",Closed won,2026-12-01,Acme {ws.tag},BUYER_{ws.tag}@example.com\n"
            f"Early {ws.tag},300,,,Acme {ws.tag},ghost_{ws.tag}@example.com\n"
            f"Nowhere {ws.tag},10,Signed,,,\n")
    preview = ws.preview("deals", text)
    assert _mapping(preview) == {"Deal": "name", "Amount": "value", "Deal stage": "stage",
                                 "Close date": "expected_close_date", "Company": "company",
                                 "Contact email": "contact_email"}
    result = ws.imports("deals", text, mapping=_mapping(preview))
    assert (result["created"], result["rejected"], result["companies_created"]) == (2, 1, 1)
    assert "unknown stage 'Signed'" in result["errors"][0]["error"]
    assert "No contact has the email" in result["warnings"][0]["warning"]
    deals = {d["name"]: d for d in ws.call("GET", "/opportunities", params={"limit": 200})}
    won, early = deals[f"Big Win {ws.tag}"], deals[f"Early {ws.tag}"]
    assert (won["value"], won["stage"]) == (1250.5, "closed_won")
    # Stored as the board stores a close date it is given.
    assert won["expected_close_date"].startswith("2026-12-01")
    assert won["contact_ids"] == [person["id"]] and won["stage_history"][0]["to"] == "closed_won"
    # Opened at the first open stage, like a deal made on the board, with no people.
    assert (early["stage"], early["contact_ids"]) == ("lead", [])
    assert won["company_id"] == early["company_id"]
    # Everyone on a deal that lands won becomes a customer.
    assert ws.call("GET", f"/contacts/{person['id']}")["contact"]["lifecycle"] == "customer"


def test_an_import_is_one_event_and_starts_no_automation(ws):
    text = "".join(f"Person {n} {ws.tag},p{n}_{ws.tag}@example.com\n" for n in range(25))
    result = ws.imports("contacts", "name,email\n" + text)
    assert result["created"] == 25
    events = ws.call("GET", "/events", params={"limit": 200})
    kinds = [event["event_type"] for event in events]
    assert kinds.count("data.imported") == 1 and "contact.created" not in kinds


def test_a_workspace_never_matches_or_links_another_workspaces_records(ws):
    other = Workspace("imp_other")
    shared = f"shared_{ws.tag}@example.com"
    other.call("POST", "/contacts", json={"name": "Theirs", "email": shared})
    theirs = other.call("POST", "/companies", json={"name": f"Their Co {ws.tag}"})
    preview = ws.preview("contacts", f"name,email,company\nMine,{shared},Their Co {ws.tag}\n")
    assert preview["plan"][0]["action"] == "create" and preview["companies_created"] == 1
    refused = ws.imports("contacts", f"name,company_id\nCross,{theirs['id']}\n")
    assert refused["rejected"] == 1 and "unknown company_id" in refused["errors"][0]["error"]


def test_only_an_admin_can_preview_or_import(ws):
    member_token, member_email = _register("imp_member")
    invite = ws.call("POST", "/team/invitations", json={"email": member_email, "role": "member"})
    accepted = requests.post(f"{API}/team/invitations/accept", headers=_h(member_token),
                             json={"token": invite["invite_token"]}, timeout=TIMEOUT)
    assert accepted.status_code == 200, accepted.text
    for path in ("/import/contacts/preview", "/import/contacts"):
        response = requests.post(f"{API}{path}", headers=_h(member_token), timeout=TIMEOUT,
                                 json={"csv": "name\nX\n"})
        assert response.status_code == 403, (path, response.text)
    assert requests.get(f"{API}/export/contacts", headers=_h(member_token), timeout=TIMEOUT).status_code == 200


# ----------------------------------------------------------------------- export

def test_an_export_names_companies_and_custom_fields_and_imports_straight_back(ws):
    field = ws.call("POST", "/custom-fields", json={"object": "contacts", "label": "Budget", "type": "number"})
    company = ws.call("POST", "/companies", json={"name": f"Export Co {ws.tag}"})
    contact = ws.call("POST", "/contacts", json={"name": "Exported Person", "email": f"exp_{ws.tag}@example.com",
                                                 "company_id": company["id"], "lifecycle": "qualified"})
    ws.call("PATCH", f"/contacts/{contact['id']}", json={"custom_fields": {field["key"]: 1200}})
    exported = requests.get(f"{API}/export/contacts", headers=ws.h, timeout=TIMEOUT)
    assert exported.status_code == 200 and exported.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    row = [r for r in rows if r["id"] == contact["id"]][0]
    assert (row["company"], row["lifecycle"], row["Budget"]) == (f"Export Co {ws.tag}", "qualified", "1200.0")

    again = Workspace("imp_again")
    again.call("POST", "/custom-fields", json={"object": "contacts", "label": "Budget", "type": "number"})
    preview = again.preview("contacts", exported.text)
    mapping = _mapping(preview)
    assert (mapping["name"], mapping["email"], mapping["company"], mapping["lifecycle"]) == (
        "name", "email", "company", "lifecycle")
    assert mapping["Budget"].startswith("cf_") and mapping["id"] == "" and mapping["company_id"] == ""
    assert preview["created"] == len(rows) and preview["rejected"] == 0


def test_deal_exports_name_their_company_and_people(ws):
    company = ws.call("POST", "/companies", json={"name": f"Deal Co {ws.tag}"})
    person = ws.call("POST", "/contacts", json={"name": "On The Deal", "email": f"on_{ws.tag}@example.com"})
    deal = ws.call("POST", "/opportunities", json={"name": f"Exported Deal {ws.tag}", "company_id": company["id"],
                                                    "contact_ids": [person["id"]], "value": 10})
    rows = list(csv.DictReader(io.StringIO(requests.get(f"{API}/export/deals", headers=ws.h, timeout=TIMEOUT).text)))
    row = [r for r in rows if r["id"] == deal["id"]][0]
    assert (row["company"], row["contact_email"]) == (f"Deal Co {ws.tag}", f"on_{ws.tag}@example.com")


# ------------------------------------------------------------------- the file reader

def test_excel_files_with_a_byte_order_mark_and_semicolons_are_read():
    headers, rows = data_transfer.parse_csv("\ufeffName;Email;Email\nA;a@example.com;b@example.com\n\n;;\n")
    assert headers == ["Name", "Email", "Email (2)"]
    assert rows == [(2, ["A", "a@example.com", "b@example.com"])]


def test_an_empty_or_oversized_file_is_refused_with_a_reason():
    with pytest.raises(HTTPException) as empty:
        data_transfer.parse_csv("Name,Email\n")
    assert "no data rows" in empty.value.detail
    with pytest.raises(HTTPException) as large:
        data_transfer.parse_csv("Name\n" + "x\n" * (data_transfer.MAX_ROWS + 1))
    assert "Split it" in large.value.detail


def test_money_is_read_as_written_in_a_spreadsheet():
    assert data_transfer.parse_money("$1,250.50") == 1250.5
    assert data_transfer.parse_money("£ 900") == 900
    for bad in ("1.234,56", "-5", "inf", "nan", "1e12", "lots"):
        with pytest.raises(ValueError):
            data_transfer.parse_money(bad)


def test_suggestions_never_use_one_field_twice():
    mapping = data_transfer.suggest_mapping("contacts", ["Email", "E-mail", "Work Email", "Name"], [])
    assert mapping == {"Email": "email", "E-mail": "", "Work Email": "", "Name": "name"}
