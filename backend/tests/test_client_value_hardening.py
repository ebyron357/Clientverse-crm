"""The fourth review round's client-value findings, as tests over HTTP.

A conflict check that stopped working after 1,000 bookings, reminders that could be
repeated for a cancelled appointment, statuses that were never checked, a disabled
automation that still ran, cancelled tasks counted as open work, a playbook applied
twice at once, and a member able to mark a queued system job done. Each used to happen.
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import requests
from motor.motor_asyncio import AsyncIOMotorClient

from work_queue import WorkQueue

API = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/") + "/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "clientverse_ci")


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _register():
    email = f"cvh_{uuid.uuid4().hex[:10]}@example.com"
    response = requests.post(f"{API}/auth/register", timeout=30, json={
        "email": email, "password": "ClientValue2026!", "name": "CV"})
    assert response.status_code == 200, response.text
    return email, response.json()["token"]


def _admin():
    return _h(_register()[1])


def _member_of(admin_headers):
    email, token = _register()
    invite = requests.post(f"{API}/team/invitations", headers=admin_headers, timeout=30,
                           json={"email": email, "role": "member"})
    assert invite.status_code == 200, invite.text
    accepted = requests.post(f"{API}/team/invitations/accept", headers=_h(token), timeout=30,
                             json={"token": invite.json()["invite_token"]})
    assert accepted.status_code == 200, accepted.text
    return _h(token)


def _tenant_of(headers):
    return requests.get(f"{API}/auth/me", headers=headers, timeout=30).json()["tenant_id"]


def _workspace(headers):
    response = requests.post(f"{API}/workspaces", headers=headers, json={"name": "Acme"},
                             timeout=30)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _with_db(body):
    async def wrapped():
        client = AsyncIOMotorClient(MONGO_URL)
        try:
            return await body(client[DB_NAME])
        finally:
            client.close()

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(wrapped())
    finally:
        loop.close()


def _slot(days, hours=1):
    start = datetime.now(timezone.utc) + timedelta(days=days)
    return start.isoformat(), (start + timedelta(hours=hours)).isoformat()


# ------------------------------------------------------------ appointments

def test_the_conflict_check_survives_a_long_booking_history():
    headers = _admin()
    tenant = _tenant_of(headers)
    owner = "busy@example.com"

    async def seed(db):
        base = datetime.now(timezone.utc) - timedelta(days=2000)
        await db.appointments.insert_many([
            {"id": f"apt_old_{tenant}_{n}", "tenant_id": tenant, "title": "Old", "owner": owner,
             "status": "scheduled",
             "start_at": (base + timedelta(days=n)).isoformat(),
             "end_at": (base + timedelta(days=n, hours=1)).isoformat()}
            for n in range(1100)])

    _with_db(seed)
    start, end = _slot(40)
    first = requests.post(f"{API}/appointments", headers=headers, timeout=30, json={
        "title": "New", "owner": owner, "start_at": start, "end_at": end})
    second = requests.post(f"{API}/appointments", headers=headers, timeout=30, json={
        "title": "Overlapping", "owner": owner, "start_at": start, "end_at": end})
    assert first.status_code == 200, first.text
    assert second.status_code == 409


def test_a_conflict_is_found_across_time_zone_offsets():
    headers = _admin()
    base = (datetime.now(timezone.utc) + timedelta(days=50)).replace(hour=15, minute=0,
                                                                     second=0, microsecond=0)
    utc_start = base.isoformat()
    utc_end = (base + timedelta(hours=1)).isoformat()
    # The same hour, written in New York time.
    ny = timezone(timedelta(hours=-5))
    ny_start = base.astimezone(ny).isoformat()
    ny_end = (base + timedelta(hours=1)).astimezone(ny).isoformat()
    ok = requests.post(f"{API}/appointments", headers=headers, timeout=30, json={
        "title": "UTC", "owner": "tz@example.com", "start_at": utc_start, "end_at": utc_end})
    clash = requests.post(f"{API}/appointments", headers=headers, timeout=30, json={
        "title": "NY", "owner": "tz@example.com", "start_at": ny_start, "end_at": ny_end})
    assert ok.status_code == 200 and clash.status_code == 409


def test_an_unknown_appointment_status_is_refused():
    headers = _admin()
    start, end = _slot(60)
    response = requests.post(f"{API}/appointments", headers=headers, timeout=30, json={
        "title": "Odd", "start_at": start, "end_at": end, "status": "banana"})
    assert response.status_code == 422


def test_a_member_cannot_rewrite_a_finished_appointment():
    admin = _admin()
    member = _member_of(admin)
    start, end = _slot(-3)
    created = requests.post(f"{API}/appointments", headers=admin, timeout=30, json={
        "title": "Done", "start_at": start, "end_at": end}).json()
    assert requests.patch(f"{API}/appointments/{created['id']}", headers=admin, timeout=30,
                          json={"status": "completed"}).status_code == 200
    moved = requests.patch(f"{API}/appointments/{created['id']}", headers=member, timeout=30,
                           json={"status": "no_show"})
    assert moved.status_code == 409
    # An admin may correct a mistaken outcome.
    corrected = requests.patch(f"{API}/appointments/{created['id']}", headers=admin,
                               timeout=30, json={"status": "no_show"})
    assert corrected.status_code == 200


def test_an_appointment_records_its_contact():
    headers = _admin()
    contact = requests.post(f"{API}/contacts", headers=headers, timeout=30, json={
        "name": "Ada", "email": "ada@example.com"}).json()
    start, end = _slot(70)
    created = requests.post(f"{API}/appointments", headers=headers, timeout=30, json={
        "title": "With Ada", "start_at": start, "end_at": end, "contact_id": contact["id"]})
    assert created.status_code == 200 and created.json()["contact_id"] == contact["id"]
    stranger = requests.post(f"{API}/appointments", headers=headers, timeout=30, json={
        "title": "Nobody", "start_at": start, "end_at": end, "contact_id": "ct_not_mine"})
    assert stranger.status_code == 404


def test_a_reminder_is_prepared_once_and_never_for_a_cancelled_appointment():
    headers = _admin()
    ws = _workspace(headers)
    start, end = _slot(80)
    apt = requests.post(f"{API}/appointments", headers=headers, timeout=30, json={
        "title": "Review", "start_at": start, "end_at": end, "workspace_id": ws}).json()
    first = requests.post(f"{API}/appointments/{apt['id']}/reminder", headers=headers,
                          timeout=30)
    again = requests.post(f"{API}/appointments/{apt['id']}/reminder", headers=headers,
                          timeout=30)
    assert first.status_code == 200 and again.status_code == 200
    assert again.json()["task"]["id"] == first.json()["task"]["id"]
    assert again.json().get("duplicate") is True

    cancelled = requests.post(f"{API}/appointments", headers=headers, timeout=30, json={
        "title": "Cancelled", "start_at": _slot(81)[0], "end_at": _slot(81)[1],
        "workspace_id": ws}).json()
    requests.patch(f"{API}/appointments/{cancelled['id']}", headers=headers, timeout=30,
                   json={"status": "cancelled"})
    refused = requests.post(f"{API}/appointments/{cancelled['id']}/reminder", headers=headers,
                            timeout=30)
    assert refused.status_code == 409


# ------------------------------------------------------------ automations and capacity

def test_a_disabled_automation_does_not_run():
    headers = _admin()
    ws = _workspace(headers)
    rule = requests.post(f"{API}/automations/safe-rules", headers=headers, timeout=30, json={
        "template": "appointment_reminder", "workspace_id": ws, "enabled": False}).json()
    ran = requests.post(f"{API}/automations/safe-rules/{rule['id']}/run", headers=headers,
                        timeout=30)
    assert ran.status_code == 409


def test_cancelled_tasks_are_not_open_work():
    headers = _admin()
    tenant = _tenant_of(headers)
    owner = f"cap_{uuid.uuid4().hex[:6]}@example.com"

    async def seed(db):
        await db.tasks.insert_many([
            {"id": f"t_{owner}_{s}", "tenant_id": tenant, "title": s, "assignee": owner,
             "status": s} for s in ("todo", "cancelled", "done", "completed")])

    _with_db(seed)
    people = requests.get(f"{API}/delivery/capacity", headers=headers, timeout=30).json()["people"]
    row = next(p for p in people if p["owner"] == owner)
    assert row["open_tasks"] == 1


def test_a_playbook_applied_twice_at_once_is_applied_once():
    headers = _admin()
    ws = _workspace(headers)
    playbooks = requests.get(f"{API}/playbooks", headers=headers, timeout=30).json()
    key = playbooks["templates"][0]["key"]

    async def burst():
        loop = asyncio.get_running_loop()
        return await asyncio.gather(*(loop.run_in_executor(None, lambda: requests.post(
            f"{API}/playbooks/{key}/apply", headers=headers, json={"workspace_id": ws},
            timeout=30)) for _ in range(8)))

    loop = asyncio.new_event_loop()
    try:
        responses = loop.run_until_complete(burst())
    finally:
        loop.close()
    assert all(r.status_code == 200 for r in responses)
    assert sum(1 for r in responses if not r.json()["duplicate"]) == 1
    applied = requests.get(f"{API}/playbooks", headers=headers, timeout=30).json()["applications"]
    assert len([a for a in applied if a["workspace_id"] == ws]) == 1


# ------------------------------------------------------------ the work queue

def test_a_member_cannot_mark_a_system_job_done():
    admin = _admin()
    member = _member_of(admin)
    tenant = _tenant_of(admin)

    async def enqueue(db):
        return await WorkQueue(db).enqueue(
            tenant_id=tenant, queue="system", item_type="recovery.run_case",
            payload={"tenant_id": tenant, "case_id": "rc_x"},
            dedupe_key=f"recovery.run_case:{uuid.uuid4().hex}", actor="admin")

    item = _with_db(enqueue)
    refused = requests.post(f"{API}/work-queue/{item['id']}/resolve", headers=member,
                            json={"resolution": "done"}, timeout=30)
    assert refused.status_code == 403
    allowed = requests.post(f"{API}/work-queue/{item['id']}/resolve", headers=admin,
                            json={"resolution": "done"}, timeout=30)
    assert allowed.status_code == 200
