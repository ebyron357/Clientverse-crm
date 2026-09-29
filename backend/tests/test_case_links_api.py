"""Linking a recovery case to its client over HTTP: admin only, own records, no re-pointing."""

import os
import uuid

import pymongo
import requests

import recovery_case as rc

API = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/") + "/api"
_db = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
    os.environ.get("DB_NAME", "test_database")]


def _tenant():
    response = requests.post(f"{API}/auth/register", timeout=30, json={
        "email": f"links_{uuid.uuid4().hex[:10]}@example.com",
        "password": "CaseLinks2026!", "name": "Links"})
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['token']}"}
    return headers, response.json()["user"]["tenant_id"]


def _case(tenant_id):
    case_id = f"rc_{uuid.uuid4().hex[:12]}"
    _db[rc.COLLECTION].insert_one({
        "id": case_id, "tenant_id": tenant_id, "source": rc.SOURCE_MISSED_CALL,
        "source_event_id": f"call_{uuid.uuid4().hex[:6]}", "state": rc.DETECTED,
        "contact_id": None, "company_id": None, "opportunity_id": None,
        "workspace_id": None, "history": []})
    return case_id


def test_a_case_is_linked_to_its_client_and_not_re_pointed():
    headers, tenant_id = _tenant()
    first = requests.post(f"{API}/companies", headers=headers, json={"name": "First"},
                          timeout=30).json()["id"]
    second = requests.post(f"{API}/companies", headers=headers, json={"name": "Second"},
                           timeout=30).json()["id"]
    case_id = _case(tenant_id)
    linked = requests.post(f"{API}/recovery-cases/{case_id}/link", headers=headers,
                           json={"company_id": first}, timeout=30)
    assert linked.status_code == 200 and linked.json()["company_id"] == first
    moved = requests.post(f"{API}/recovery-cases/{case_id}/link", headers=headers,
                          json={"company_id": second}, timeout=30)
    assert moved.status_code == 409
    proof = requests.get(f"{API}/proof/cases/{case_id}", headers=headers, timeout=30)
    assert proof.status_code == 200, proof.text
    assert proof.json()["case"]["links"]["company_id"] == first


def test_another_tenants_record_or_case_is_not_found():
    headers, tenant_id = _tenant()
    other_headers, other_tenant = _tenant()
    theirs = requests.post(f"{API}/companies", headers=other_headers, json={"name": "Theirs"},
                           timeout=30).json()["id"]
    case_id = _case(tenant_id)
    assert requests.post(f"{API}/recovery-cases/{case_id}/link", headers=headers,
                         json={"company_id": theirs}, timeout=30).status_code == 404
    assert requests.post(f"{API}/recovery-cases/{case_id}/link", headers=other_headers,
                         json={"company_id": theirs}, timeout=30).status_code == 404
    assert _db[rc.COLLECTION].find_one({"id": case_id})["company_id"] is None
