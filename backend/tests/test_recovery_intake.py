"""The public intake door, tested as the open door it is.

The website form's token is embedded in a public page, so anyone can use it. These tests
are attacks a stranger could run with that token: poison the tenant's figures with an
absurd value, flood the tenant until real enquiries fall out of detection, pre-empt the
tenant's own lead ids, and read the secret back out of the logs.
"""

import logging
import os
import uuid

import pytest
import requests

import recovery_case as rc
import recovery_intake

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/")
API = f"{BASE}/api"


def _admin():
    response = requests.post(f"{API}/auth/register", json={
        "email": f"intake_{uuid.uuid4().hex[:10]}@example.com",
        "password": "IntakeTest2026!", "name": "Intake Test"}, timeout=30)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _token(admin):
    response = requests.post(f"{API}/intake/tokens", headers=admin,
                             json={"label": "website"}, timeout=30)
    assert response.status_code == 200, response.text
    return response.json()["secret"]


def _submit(secret, body, *, header=True, extra_headers=None):
    headers = dict(extra_headers or {})
    if header:
        headers["X-Intake-Token"] = secret
        return requests.post(f"{API}/intake/public/web-enquiries", json=body,
                             headers=headers, timeout=30)
    return requests.post(f"{API}/intake/public/{secret}/web-enquiries", json=body,
                         headers=headers, timeout=30)


def _enquiries(admin):
    return requests.get(f"{API}/intake/web-enquiries", headers=admin,
                        timeout=30).json()["items"]


@pytest.fixture()
def door():
    admin = _admin()
    return admin, _token(admin)


# ------------------------------------------------------------------ the basics

def test_both_forms_of_the_door_accept_an_enquiry_and_reveal_nothing(door):
    admin, secret = door
    by_header = _submit(secret, {"email": "a@visitor.example", "message": "Quote please"})
    by_path = _submit(secret, {"email": "b@visitor.example", "message": "Hi"}, header=False)
    assert by_header.status_code == 200 and by_header.json() == {"accepted": True}
    assert by_path.status_code == 200 and by_path.json() == {"accepted": True}
    assert len(_enquiries(admin)) == 2


def test_a_wrong_or_missing_token_is_not_found(door):
    assert _submit("not-a-token", {"message": "x"}).status_code == 404
    assert requests.post(f"{API}/intake/public/web-enquiries", json={"message": "x"},
                         timeout=30).status_code == 404


# ------------------------------------------------------------------ poisoned values

@pytest.mark.parametrize("value", ["Infinity", "NaN", "1e308", "1e10"])
def test_an_absurd_value_is_refused(door, value):
    _, secret = door
    body = f'{{"message": "x", "estimated_value": {value}}}'
    response = requests.post(f"{API}/intake/public/web-enquiries", data=body, timeout=30,
                             headers={"X-Intake-Token": secret,
                                      "Content-Type": "application/json"})
    assert response.status_code == 422, (value, response.status_code)


def test_a_visitors_stated_value_is_kept_but_is_not_potential_value(door):
    admin, secret = door
    assert _submit(secret, {"message": "Big job", "estimated_value": 50000}).status_code == 200
    enquiry = _enquiries(admin)[0]
    assert enquiry["estimated_value"] is None, "a stranger's claim must not become potential"
    assert enquiry["visitor_stated_value"] == 50000
    listing = requests.get(f"{API}/intake/web-enquiries", headers=admin, timeout=30)
    assert listing.status_code == 200


def test_the_tenants_own_estimate_still_counts(door):
    admin, _ = door
    filed = requests.post(f"{API}/intake/web-enquiries", headers=admin,
                          json={"message": "From our CRM", "estimated_value": 1200},
                          timeout=30)
    assert filed.status_code == 200
    assert filed.json()["estimated_value"] == 1200


def test_no_recovery_case_can_hold_an_implausible_amount():
    with pytest.raises(rc.RecoveryCaseError):
        rc._amount(1e13, "Potential value")
    assert rc._amount(250000.0, "Potential value") == 250000.0


# ------------------------------------------------------------------ pre-empting ids

def test_a_visitor_cannot_pre_empt_the_tenants_own_lead_id(door):
    admin, secret = door
    assert _submit(secret, {"message": "squatting", "external_id": "form-1001"}
                   ).status_code == 200
    real = requests.post(f"{API}/intake/web-enquiries", headers=admin,
                         json={"message": "The real lead", "external_id": "form-1001"},
                         timeout=30)
    assert real.status_code == 200
    assert real.json()["deduplicated"] is False, "the real lead must not be swallowed"
    ids = sorted(e["external_id"] for e in _enquiries(admin))
    assert ids == ["form-1001", "public:form-1001"]


def test_a_repeated_public_submission_is_answered_like_a_new_one(door):
    admin, secret = door
    first = _submit(secret, {"message": "once", "external_id": "x-1"})
    again = _submit(secret, {"message": "once", "external_id": "x-1"})
    assert first.json() == again.json() == {"accepted": True}
    assert len(_enquiries(admin)) == 1


# ------------------------------------------------------------------ flooding

def test_one_client_is_limited_per_hour(door):
    _, secret = door
    limit = recovery_intake.PUBLIC_HOURLY_PER_CLIENT
    statuses = [_submit(secret, {"message": f"m{i}"}).status_code for i in range(limit + 1)]
    assert statuses[:limit] == [200] * limit
    assert statuses[limit] == 429


def test_a_token_is_limited_per_day_whoever_calls(door):
    admin, secret = door
    limit = recovery_intake.PUBLIC_DAILY_LIMIT
    session = requests.Session()
    accepted = 0
    last = None
    for i in range(limit + 1):
        # A different client each time, so only the daily cap can stop it.
        last = session.post(f"{API}/intake/public/web-enquiries",
                            json={"message": f"flood {i}"}, timeout=30,
                            headers={"X-Intake-Token": secret,
                                     "X-Forwarded-For": f"10.{i // 250}.{i % 250}.1"})
        accepted += last.status_code == 200
    assert accepted == limit
    assert last.status_code == 429


def test_an_oversized_body_is_refused(door):
    _, secret = door
    response = requests.post(f"{API}/intake/public/web-enquiries", timeout=30,
                             data=b'{"message": "' + b"x" * 20000 + b'"}',
                             headers={"X-Intake-Token": secret,
                                      "Content-Type": "application/json"})
    assert response.status_code == 413


def test_junk_can_be_marked_spam_and_only_by_its_own_tenant(door):
    admin, secret = door
    _submit(secret, {"message": "buy cheap watches"})
    enquiry = _enquiries(admin)[0]
    stranger = _admin()
    assert requests.patch(f"{API}/intake/web-enquiries/{enquiry['id']}", headers=stranger,
                          json={"status": "spam"}, timeout=30).status_code == 404
    marked = requests.patch(f"{API}/intake/web-enquiries/{enquiry['id']}", headers=admin,
                            json={"status": "spam"}, timeout=30)
    assert marked.status_code == 200 and marked.json()["status"] == "spam"
    assert requests.patch(f"{API}/intake/web-enquiries/{enquiry['id']}", headers=admin,
                          json={"status": "deleted"}, timeout=30).status_code == 422


# ------------------------------------------------------------------ the logs

def test_the_secret_never_reaches_the_access_log():
    import server

    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 0, '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "POST", "/api/intake/public/s3cr3t-T0KEN_x/web-enquiries", "1.1",
         200), None)
    for handler_filter in logging.getLogger("uvicorn.access").filters:
        handler_filter.filter(record)
    assert "s3cr3t" not in record.getMessage()
    assert "/api/intake/public/[redacted]/web-enquiries" in record.getMessage()
    assert server  # the filter is installed by importing the application
