"""Online booking, driven the way a lead and an agent actually use it.

The slot math is tested as pure functions with a fixed clock (weekly hours, days off,
buffers, notice, horizon, and both New York DST changes). Everything else goes in through
the HTTP doors -- the public booking page with a browser's headers, the agent's calendar
with a session -- and then reads back what the CRM did: the appointment in the shared
`appointments` collection, the lead, contact, deal and task the website-forms pipeline
made, the alert, the approval each email to the person waits on, the reminders, and what
the recovery detectors make of a no-show.

Runs in-process against the real `app`, like the website-forms tests.
"""

import asyncio
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ["LEAD_SLA_WATCHER"] = "0"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_booking_unit")
os.environ.setdefault("JWT_SECRET", "booking-unit-jwt-secret-that-is-long-enough-1234")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "admin@booking.example")
os.environ.setdefault("ADMIN_PASSWORD", "Booking-Admin-Passw0rd-1!")

from fastapi.testclient import TestClient

import approval_queue
import booking
import conversations as cv
import detectors
import scheduler
import server

SITE = "https://www.agent-homes.example"
UTC = timezone.utc
NY = "America/New_York"


@pytest.fixture(scope="module")
def client():
    registered = server.booking_service.db
    server.db = registered
    server.mclient = getattr(registered, "client", server.mclient)
    with TestClient(server.app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clean_service():
    service = server.booking_service
    fetcher = service.busy_fetcher
    service.registry = None
    yield
    service.registry = None
    service.busy_fetcher = fetcher


def call(client, fn, *args, **kwargs):
    async def _run():
        return await fn(*args, **kwargs)
    return client.portal.call(_run)


def find_one(client, collection, query):
    return call(client, server.db[collection].find_one, query, {"_id": 0})


def find_all(client, collection, query):
    async def _run():
        return await server.db[collection].find(query, {"_id": 0}).to_list(1000)
    return client.portal.call(_run)


def update(client, collection, query, change):
    return call(client, server.db[collection].update_one, query, change)


def register(client, name="Avery Agent"):
    email = f"agent-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post("/api/auth/register",
                           json={"email": email, "password": "Str0ng-Passw0rd!", "name": name})
    assert response.status_code == 200, response.text
    client.cookies.clear()
    body = response.json()
    owner = {"email": email, "tenant_id": body["user"]["tenant_id"],
             "headers": {"Authorization": f"Bearer {body['token']}"}}
    assert client.get("/api/booking/catalog", headers=owner["headers"]).status_code == 200
    return owner


def add_member(client, owner, role="member", name="Morgan Member"):
    email = f"member-{uuid.uuid4().hex[:8]}@example.com"
    password = "Str0ng-Passw0rd!"
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    call(client, server.db.users.insert_one,
         {"user_id": user_id, "email": email, "name": name, "role": role,
          "tenant_id": owner["tenant_id"], "password_hash": server.hash_password(password),
          "created_at": server.now_iso()})
    call(client, server.db.memberships.insert_one,
         {"id": f"mem_{uuid.uuid4().hex[:8]}", "tenant_id": owner["tenant_id"], "user_id": user_id,
          "email": email, "role": role, "status": "active"})
    token = server.create_access_token(user_id, email)
    return {"email": email, "tenant_id": owner["tenant_id"],
            "headers": {"Authorization": f"Bearer {token}"}}


ALWAYS = {day: [{"start": "00:00", "end": "24:00"}] for day in booking.WEEKDAYS}


def open_all_day(client, person, *, tz="UTC", headers=None):
    response = client.put(f"/api/booking/availability/{person['email']}",
                          headers=headers or person["headers"],
                          json={"timezone": tz, "weekly": ALWAYS, "overrides": []})
    assert response.status_code == 200, response.text


def create_page(client, owner, **overrides):
    body = {"preset": "home_showing", "name": "Home showing", "min_notice_hours": 0,
            "buffer_before_minutes": 0, "buffer_after_minutes": 0, **overrides}
    response = client.post("/api/booking/event-types", headers=owner["headers"], json=body)
    assert response.status_code == 200, response.text
    return response.json()


def day(offset):
    return (datetime.now(UTC) + timedelta(days=offset)).date()


def slots(client, page, *, first=None, last=None, tz="UTC", origin=SITE):
    first = first or day(2)
    last = last or first
    response = client.get(f"/api/public/booking/{page['public_key']}/slots",
                          params={"start": first.isoformat(), "end": last.isoformat(), "tz": tz},
                          headers={"Origin": origin})
    assert response.status_code == 200, response.text
    return [s for d in response.json()["days"] for s in d["slots"]]


def person(**overrides):
    data = {"first_name": "Jamie", "last_name": "Buyer", "email": "jamie.buyer@example.com",
            "phone": "(555) 010-0142", "property_address": "12 Oak St, Springfield",
            "listing_id": "MLS-4471", "pre_approved": "Yes", "message": "Is the yard fenced?",
            "consent_sms": True, "utm_source": "zillow", "page_url": f"{SITE}/listings/12-oak",
            "_sid": uuid.uuid4().hex, "_elapsed_ms": 8000}
    data.update(overrides)
    return data


def book(client, page, start, *, tz="UTC", origin=SITE, **overrides):
    payload = {"start": start, "timezone": tz, **person(**overrides)}
    # What the booking page sends: JSON as text/plain, so the browser skips a preflight.
    return client.post(f"/api/public/booking/{page['public_key']}/book",
                       content=json.dumps(payload),
                       headers={"Content-Type": "text/plain;charset=UTF-8", "Origin": origin})


def token_of(response):
    return response.json()["booking"]["links"]["manage_url"].rsplit("/", 1)[-1]


class FakeEmail:
    channel = cv.CHANNEL_EMAIL
    name = "fake-email"

    def __init__(self):
        self.sent = []

    async def send(self, *, message, conversation, idempotency_key):
        self.sent.append(message)
        return cv.DeliveryResult(provider_message_id=f"pm_{len(self.sent)}")


def connect_email(client, owner):
    call(client, server.db.integration_connections.insert_one,
         {"tenant_id": owner["tenant_id"], "provider": "gmail", "status": "active"})
    call(client, server.db.integrations.insert_one,
         {"tenant_id": owner["tenant_id"], "name": "gmail", "provider": "gmail", "status": "CONNECTED"})
    registry = cv.ProviderRegistry()
    fake = FakeEmail()
    registry.register(fake)
    server.booking_service.registry = registry
    return fake


# ------------------------------------------------------------------ slot math

def ny_availability(**overrides):
    return {"timezone": NY, "weekly": booking.default_weekly(), "overrides": [], **overrides}


def starts(availability, first, last, *, duration=30, interval=30, before=0, after=0,
           busy=None, lower=None, upper=None):
    lo = datetime(first.year, first.month, first.day, tzinfo=UTC) - timedelta(hours=12)
    hi = datetime(last.year, last.month, last.day, tzinfo=UTC) + timedelta(hours=36)
    return booking.available_starts(
        windows=booking.host_windows(availability, lo, hi), busy=busy or [], duration=duration,
        interval=interval, before=before, after=after, lower=lower or lo, upper=upper or hi)


def local(values, tz=NY):
    return [v.astimezone(booking.zone(tz)).strftime("%a %H:%M") for v in values]


def test_slots_follow_weekly_hours_in_the_agents_own_zone():
    tuesday = date(2026, 10, 20)
    found = [s for s in starts(ny_availability(), tuesday, tuesday)
             if s.astimezone(booking.zone(NY)).date() == tuesday]
    assert len(found) == 18  # 9:00 .. 17:30, every half hour, a 30-minute showing
    assert found[0] == datetime(2026, 10, 20, 13, 0, tzinfo=UTC)  # 9:00 EDT
    assert local(found)[-1] == "Tue 17:30"
    sunday = date(2026, 10, 25)
    assert not [s for s in starts(ny_availability(), sunday, sunday)
                if s.astimezone(booking.zone(NY)).date() == sunday]


def test_a_day_off_and_special_hours_override_the_week():
    availability = ny_availability(overrides=[
        {"date": "2026-10-20", "intervals": []},
        {"date": "2026-10-21", "intervals": [{"start": "13:00", "end": "15:00"}]},
        {"date": "2026-10-25", "intervals": [{"start": "10:00", "end": "11:00"}]}])
    found = local(starts(availability, date(2026, 10, 20), date(2026, 10, 25)))
    assert not [s for s in found if s.startswith("Tue")]
    assert [s for s in found if s.startswith("Wed")] == ["Wed 13:00", "Wed 13:30", "Wed 14:00", "Wed 14:30"]
    assert [s for s in found if s.startswith("Sun")] == ["Sun 10:00", "Sun 10:30"]


def test_buffers_keep_travel_time_between_showings_but_may_overlap_each_other():
    tuesday = date(2026, 10, 20)
    existing = (datetime(2026, 10, 20, 14, 0, tzinfo=UTC), datetime(2026, 10, 20, 14, 30, tzinfo=UTC), 15, 15)
    found = local(starts(ny_availability(), tuesday, tuesday, before=15, after=15, busy=[existing]))
    # The showing is 10:00-10:30 EDT with 15 minutes of travel each side.
    assert "Tue 09:00" in found and "Tue 11:00" in found
    for blocked in ("Tue 09:30", "Tue 10:00", "Tue 10:30"):
        assert blocked not in found


def test_minimum_notice_and_the_horizon_bound_the_offered_times():
    tuesday = date(2026, 10, 20)
    now = datetime(2026, 10, 20, 14, 10, tzinfo=UTC)  # 10:10 EDT
    found = starts(ny_availability(), tuesday, date(2026, 10, 30),
                   lower=now + timedelta(hours=2), upper=now + timedelta(days=3))
    assert found[0] == datetime(2026, 10, 20, 16, 30, tzinfo=UTC)  # 12:30, on the half-hour grid
    assert max(found) < now + timedelta(days=3)


def test_dst_fall_back_and_spring_forward_in_new_york():
    # On a normal day 9:00 local moves from 13:00Z to 14:00Z across the November change.
    weekly = {d: [{"start": "09:00", "end": "10:00"}] for d in booking.WEEKDAYS}
    sat_before = starts(ny_availability(weekly=weekly), date(2026, 10, 31), date(2026, 10, 31))
    mon_after = starts(ny_availability(weekly=weekly), date(2026, 11, 2), date(2026, 11, 2))
    assert datetime(2026, 10, 31, 13, 0, tzinfo=UTC) in sat_before
    assert datetime(2026, 11, 2, 14, 0, tzinfo=UTC) in mon_after
    assert datetime(2026, 11, 2, 13, 0, tzinfo=UTC) not in mon_after
    # Midnight to 4:00 on the fall-back night is five real hours: 1:00 happens twice.
    night = {"date": "2026-11-01", "intervals": [{"start": "00:00", "end": "04:00"}]}
    fall = [s for s in starts(ny_availability(weekly={d: [] for d in booking.WEEKDAYS}, overrides=[night]),
                              date(2026, 11, 1), date(2026, 11, 1), duration=60, interval=60)]
    assert [s.hour for s in fall] == [4, 5, 6, 7, 8]
    assert [s.astimezone(booking.zone(NY)).strftime("%H:%M %Z") for s in fall] == [
        "00:00 EDT", "01:00 EDT", "01:00 EST", "02:00 EST", "03:00 EST"]
    # ...and on the spring-forward night it is three: 2:00-3:00 does not exist.
    spring_night = {"date": "2027-03-14", "intervals": [{"start": "00:00", "end": "04:00"}]}
    spring = starts(ny_availability(weekly={d: [] for d in booking.WEEKDAYS}, overrides=[spring_night]),
                    date(2027, 3, 14), date(2027, 3, 14), duration=60, interval=60)
    assert [s.astimezone(booking.zone(NY)).strftime("%H:%M") for s in spring] == ["00:00", "01:00", "03:00"]


def test_the_service_groups_free_times_by_the_visitors_day(client):
    owner = register(client)
    client.put(f"/api/booking/availability/{owner['email']}", headers=owner["headers"],
               json={"timezone": NY, "weekly": booking.default_weekly(), "overrides": []})
    page = create_page(client, owner, max_days_ahead=60)
    stored = find_one(client, booking.EVENT_TYPES, {"id": page["id"]})
    now = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    result = call(client, server.booking_service.slot_days, stored, date(2026, 10, 31), date(2026, 11, 2),
                  "Europe/London", now=now)
    by_day = {d["date"]: d["slots"] for d in result["days"]}
    # 9:00 New York is 13:00 London on 31 Oct (both summer time ended differently) ...
    assert by_day["2026-10-31"][0] == "2026-10-31T13:00:00+00:00"
    # ... and Monday's 9:00 EST is 14:00 UTC; Sunday is the agent's day off.
    assert "2026-11-01" not in by_day
    assert by_day["2026-11-02"][0] == "2026-11-02T14:00:00+00:00"


def test_availability_is_validated_in_plain_words(client):
    owner = register(client)
    bad = client.put(f"/api/booking/availability/{owner['email']}", headers=owner["headers"],
                     json={"timezone": "Mars/Olympus", "weekly": ALWAYS, "overrides": []})
    assert bad.status_code == 422 and "time zone" in bad.json()["detail"]
    backwards = client.put(f"/api/booking/availability/{owner['email']}", headers=owner["headers"],
                           json={"timezone": NY, "weekly": {"mon": [{"start": "17:00", "end": "09:00"}]},
                                 "overrides": []})
    assert backwards.status_code == 422 and "end after it starts" in backwards.json()["detail"]


# --------------------------------------------------------------- the public door

def test_a_website_on_another_domain_may_call_the_booking_door_without_credentials(client):
    preflight = client.options("/api/public/booking/home-showing-abc123/book",
                               headers={"Origin": SITE, "Access-Control-Request-Method": "POST",
                                        "Access-Control-Request-Headers": "content-type"})
    assert preflight.status_code == 204
    assert preflight.headers["access-control-allow-origin"] == SITE
    assert "access-control-allow-credentials" not in preflight.headers
    private = client.options("/api/booking/event-types",
                             headers={"Origin": SITE, "Access-Control-Request-Method": "GET"})
    assert private.headers.get("access-control-allow-origin") != SITE


def test_the_booking_page_can_be_framed_and_the_rest_cannot(client):
    page = client.get("/book/home-showing-abc123")
    assert "frame-ancestors *" in page.headers["content-security-policy"]
    assert "x-frame-options" not in page.headers
    assert client.get("/booking/manage/whatever").headers["x-frame-options"] == "SAMEORIGIN"
    assert client.get("/api/health").headers["x-frame-options"] == "SAMEORIGIN"
    script = client.get("/api/public/booking/embed.js")
    assert script.status_code == 200 and "javascript" in script.headers["content-type"]


def test_a_booking_becomes_a_lead_a_contact_a_deal_an_appointment_a_task_and_an_alert(client):
    owner = register(client, name="Avery Agent")
    open_all_day(client, owner)
    page = create_page(client, owner)
    config = client.get(f"/api/public/booking/{page['public_key']}/config", headers={"Origin": SITE})
    assert config.status_code == 200
    assert config.headers["access-control-allow-origin"] == SITE
    body = config.json()
    assert body["host_name"] == "Avery Agent" and "tenant_id" not in body
    assert [q["key"] for q in body["questions"]][:5] == ["first_name", "last_name", "email", "phone",
                                                         "property_address"]
    start = slots(client, page)[0]
    response = book(client, page, start, tz=NY)
    assert response.status_code == 200, response.text
    shown = response.json()["booking"]
    assert shown["start_at"] == start and shown["timezone"] == NY
    assert shown["location"]["text"] == "12 Oak St, Springfield"
    assert shown["links"]["ics_url"].endswith("/event.ics")
    assert "calendar.google.com" in shown["links"]["google_calendar_url"]

    appointment = find_one(client, "appointments", {"tenant_id": owner["tenant_id"]})
    assert appointment["status"] == "confirmed" and appointment["owner"] == owner["email"]
    assert appointment["start_at"] == start
    assert appointment["contact_id"] and appointment["opportunity_id"] and appointment["enquiry_id"]
    lead = find_one(client, detectors.WEB_ENQUIRIES, {"id": appointment["enquiry_id"]})
    assert lead["appointment_id"] == appointment["id"]
    # The person chose a time: the lead is answered by the booking, not a stale enquiry.
    assert lead["status"] == "responded" and lead["sla"]["responded_via"] == "booked_online"
    assert lead["sla"]["response_minutes"] is None
    assert lead["fields"]["listing_id"] == "MLS-4471" and lead["attribution"]["utm_source"] == "zillow"
    contact = find_one(client, "contacts", {"id": appointment["contact_id"]})
    assert contact["email"] == "jamie.buyer@example.com" and "booking" in contact["tags"]
    deal = find_one(client, "opportunities", {"id": appointment["opportunity_id"]})
    assert deal["owner"] == owner["email"] and "12 Oak St" in deal["name"]
    task = find_one(client, "tasks", {"source.appointment_id": appointment["id"]})
    assert task["title"].startswith("Confirm the showing with Jamie Buyer")
    assert (task["related_type"], task["related_id"]) == ("contact", appointment["contact_id"])
    assert task["assignee"] == owner["email"]
    alert = find_one(client, "notifications", {"tenant_id": owner["tenant_id"], "type": "booking.new"})
    assert alert["recipient"] == owner["email"] and "Jamie Buyer" in alert["title"]
    assert alert["deep_link"] == f"/scheduling/calendar?appointment={appointment['id']}"
    events = {e["event_type"] for e in find_all(client, "domain_events", {"tenant_id": owner["tenant_id"]})}
    assert {"lead.received", "appointment.booked", "contact.created"} <= events
    # The detectors see a live booking as neither a no-show nor a lost web lead.
    assert not call(client, detectors.detect_web_enquiries, server.db, owner["tenant_id"], grace_hours=0)
    # The calendar shows it, with the links an agent needs.
    listed = client.get("/api/booking/appointments", headers=owner["headers"]).json()["items"]
    assert listed[0]["person"]["name"] == "Jamie Buyer"
    assert listed[0]["enquiry_id"] == lead["id"] and listed[0]["can_manage"]
    # The time is gone from the page.
    assert start not in slots(client, page)


def test_a_retry_with_the_same_submission_id_is_booked_once(client):
    owner = register(client)
    open_all_day(client, owner)
    page = create_page(client, owner)
    start = slots(client, page)[0]
    sid = uuid.uuid4().hex
    first = book(client, page, start, _sid=sid)
    again = book(client, page, start, _sid=sid)
    assert first.status_code == again.status_code == 200
    assert again.json()["replayed"] is True
    assert token_of(first) == token_of(again)
    assert len(find_all(client, "appointments", {"tenant_id": owner["tenant_id"]})) == 1


def test_the_same_time_cannot_be_booked_twice(client):
    owner = register(client)
    open_all_day(client, owner)
    page = create_page(client, owner)
    start = slots(client, page)[0]
    assert book(client, page, start).status_code == 200
    second = book(client, page, start, email="someone.else@example.com", phone="5550100143")
    assert second.status_code == 409
    assert second.json()["code"] == "slot_taken"
    fresh = [s for d in second.json()["days"] for s in d["slots"]]
    assert fresh and start not in fresh


def test_two_people_racing_for_one_time_get_exactly_one_booking(client, monkeypatch):
    owner = register(client)
    open_all_day(client, owner)
    page = create_page(client, owner)
    start_text = slots(client, page)[0]
    stored = find_one(client, booking.EVENT_TYPES, {"id": page["id"]})
    service = server.booking_service
    real_busy = service.busy_for

    async def slow_busy(*args, **kwargs):
        # Widen the window between reading the calendar and writing the booking, so the
        # race is real: both requests read "free" before either writes.
        await asyncio.sleep(0.05)
        return await real_busy(*args, **kwargs)

    monkeypatch.setattr(service, "busy_for", slow_busy)
    start = datetime.fromisoformat(start_text)

    async def race():
        meta = {"channel": "booking", "visitor": "v"}
        return await asyncio.gather(
            service.book(stored, start=start, raw=person(), display_tz="UTC", meta=meta),
            service.book(stored, start=start, raw=person(email="b@example.com", phone="5550100144"),
                         display_tz="UTC", meta=meta),
            return_exceptions=True)

    results = client.portal.call(race)
    booked = [r for r in results if isinstance(r, dict)]
    refused = [r for r in results if isinstance(r, booking.SlotTaken)]
    assert len(booked) == 1 and len(refused) == 1, results
    assert len(find_all(client, "appointments", {"tenant_id": owner["tenant_id"], "status": "confirmed"})) == 1


def test_the_database_refuses_a_second_active_claim_even_if_the_overlap_check_were_wrong(client, monkeypatch):
    owner = register(client)
    open_all_day(client, owner)
    page = create_page(client, owner)
    start = slots(client, page)[0]
    assert book(client, page, start).status_code == 200
    monkeypatch.setattr(booking, "conflicts", lambda *args, **kwargs: False)
    second = book(client, page, start, email="late@example.com", phone="5550100145")
    assert second.status_code == 409
    assert len(find_all(client, "appointments", {"tenant_id": owner["tenant_id"]})) == 1


def test_an_overlapping_booking_of_another_length_is_refused(client):
    owner = register(client)
    open_all_day(client, owner)
    showing = create_page(client, owner, slot_interval_minutes=15)
    listing = create_page(client, owner, preset="listing_appointment", name="Listing appointment",
                          duration_minutes=60, slot_interval_minutes=15)
    start = slots(client, showing)[4]
    assert book(client, showing, start).status_code == 200
    later = (datetime.fromisoformat(start) + timedelta(minutes=15)).isoformat()
    assert later not in slots(client, listing)
    assert book(client, listing, later, email="o@example.com", phone="5550100146").status_code == 409


def test_a_bot_filling_the_honeypot_or_submitting_instantly_books_nothing(client):
    owner = register(client)
    open_all_day(client, owner)
    page = create_page(client, owner)
    start = slots(client, page)[0]
    trapped = book(client, page, start, _hp="http://spam.example")
    instant = book(client, page, start, _elapsed_ms=200)
    assert trapped.status_code == instant.status_code == 200
    assert trapped.json()["accepted"] is True
    assert not find_all(client, "appointments", {"tenant_id": owner["tenant_id"]})
    assert start in slots(client, page)


def test_a_flood_of_bookings_from_one_visitor_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(booking, "RATE_BOOK_PER_VISITOR_PER_HOUR", 2)
    owner = register(client)
    open_all_day(client, owner)
    page = create_page(client, owner)
    times = slots(client, page)
    codes = [book(client, page, times[i], email=f"p{i}@example.com", phone=f"555010{i:04d}").status_code
             for i in range(3)]
    assert codes == [200, 200, 429]


def test_bad_input_is_named(client):
    owner = register(client)
    open_all_day(client, owner)
    page = create_page(client, owner)
    start = slots(client, page)[0]
    missing = book(client, page, start, email="", property_address="")
    assert missing.status_code == 422
    assert {"email", "property_address"} <= set(missing.json()["errors"])
    off_grid = (datetime.fromisoformat(start) + timedelta(minutes=7)).isoformat()
    assert book(client, page, off_grid).status_code == 409
    assert book(client, page, "tomorrow at noon").status_code == 422
    assert book(client, page, start, tz="Nowhere/Land").status_code == 422
    assert client.get(f"/api/public/booking/{page['public_key']}/slots",
                      params={"start": "2026-01-01", "end": "2026-12-31", "tz": "UTC"}).status_code == 422


def test_a_paused_page_takes_no_bookings(client):
    owner = register(client)
    open_all_day(client, owner)
    page = create_page(client, owner)
    start = slots(client, page)[0]
    client.patch(f"/api/booking/event-types/{page['id']}", headers=owner["headers"], json={"status": "paused"})
    assert client.get(f"/api/public/booking/{page['public_key']}/config").status_code == 404
    assert book(client, page, start).status_code == 404


# --------------------------------------------------------- the person's link

def test_the_person_reschedules_and_cancels_from_their_link(client):
    owner = register(client)
    open_all_day(client, owner)
    page = create_page(client, owner)
    times = slots(client, page)
    response = book(client, page, times[0], tz=NY)
    token = token_of(response)
    view = client.get(f"/api/public/booking/manage/{token}", headers={"Origin": SITE})
    assert view.status_code == 200 and view.json()["can_change"] is True
    assert view.json()["person"]["email"].startswith("j") and "*" in view.json()["person"]["email"]

    open_times = client.get(f"/api/public/booking/manage/{token}/slots",
                            params={"start": day(2).isoformat(), "end": day(2).isoformat(), "tz": "UTC"}).json()
    offered = [s for d in open_times["days"] for s in d["slots"]]
    assert times[0] in offered, "the booking's own time stays offered while moving it"
    moved = client.post(f"/api/public/booking/manage/{token}/reschedule",
                        content=json.dumps({"start": times[3], "timezone": NY}),
                        headers={"Content-Type": "text/plain;charset=UTF-8", "Origin": SITE})
    assert moved.status_code == 200, moved.text
    stored = find_one(client, "appointments", {"tenant_id": owner["tenant_id"]})
    assert stored["start_at"] == times[3] and stored["booking"]["rescheduled_count"] == 1
    assert times[0] in slots(client, page) and times[3] not in slots(client, page)
    assert find_one(client, "notifications", {"tenant_id": owner["tenant_id"], "type": "booking.rescheduled"})

    ics = client.get(f"/api/public/booking/manage/{token}/event.ics")
    assert ics.status_code == 200 and ics.headers["content-type"].startswith("text/calendar")
    assert "SEQUENCE:1" in ics.text and "DTSTART:" + datetime.fromisoformat(times[3]).strftime("%Y%m%dT%H%M%SZ") in ics.text

    cancelled = client.post(f"/api/public/booking/manage/{token}/cancel",
                            content=json.dumps({"reason": "We found a place"}),
                            headers={"Content-Type": "text/plain;charset=UTF-8"})
    assert cancelled.status_code == 200 and cancelled.json()["booking"]["status"] == "cancelled"
    stored = find_one(client, "appointments", {"id": stored["id"]})
    assert stored["status"] == "cancelled" and stored["cancel_reason"] == "We found a place"
    assert "slot_claim" not in stored
    assert times[3] in slots(client, page)
    alert = find_one(client, "notifications", {"tenant_id": owner["tenant_id"], "type": "booking.cancelled"})
    assert "We found a place" in alert["body"]
    # Once cancelled, the link cannot move or re-cancel it.
    assert client.post(f"/api/public/booking/manage/{token}/reschedule",
                       json={"start": times[5]}).status_code == 409
    # The cancelled booking is what the cancelled-appointment detector looks for.
    found = call(client, detectors.detect_cancelled_appointments, server.db, owner["tenant_id"])
    assert [d["record_id"] for d in found] == [stored["id"]]


def test_a_link_reaches_its_own_booking_and_nothing_else(client):
    first_owner = register(client)
    open_all_day(client, first_owner)
    first_page = create_page(client, first_owner)
    other_owner = register(client)
    open_all_day(client, other_owner)
    other_page = create_page(client, other_owner)
    mine = book(client, first_page, slots(client, first_page)[0])
    theirs = book(client, other_page, slots(client, other_page)[0], email="t@example.com")
    my_token, their_token = token_of(mine), token_of(theirs)
    assert my_token != their_token
    # Cancelling through one link leaves the other tenant's booking alone.
    client.post(f"/api/public/booking/manage/{their_token}/cancel", json={"reason": "x"})
    assert find_one(client, "appointments", {"tenant_id": first_owner["tenant_id"]})["status"] == "confirmed"
    # A forged or altered token is refused, not guessed at.
    forged = my_token[:-4] + ("AAAA" if not my_token.endswith("AAAA") else "BBBB")
    assert client.get(f"/api/public/booking/manage/{forged}").status_code == 404
    assert client.get("/api/public/booking/manage/short").status_code == 404
    assert client.post(f"/api/public/booking/manage/{forged}/cancel", json={}).status_code == 404


# ------------------------------------------------------------ tenant isolation

def test_booking_pages_and_appointments_are_tenant_scoped(client):
    owner = register(client)
    open_all_day(client, owner)
    page = create_page(client, owner)
    book(client, page, slots(client, page)[0])
    appointment = find_one(client, "appointments", {"tenant_id": owner["tenant_id"]})
    stranger = register(client)
    assert client.get(f"/api/booking/event-types/{page['id']}", headers=stranger["headers"]).status_code == 404
    assert client.patch(f"/api/booking/event-types/{page['id']}", headers=stranger["headers"],
                        json={"name": "Mine now"}).status_code == 404
    assert client.get("/api/booking/event-types", headers=stranger["headers"]).json()["items"] == []
    assert client.get("/api/booking/appointments", headers=stranger["headers"]).json()["items"] == []
    for path in ("outcome", "cancel", "reschedule"):
        response = client.post(f"/api/booking/appointments/{appointment['id']}/{path}",
                               headers=stranger["headers"], json={"outcome": "attended", "start": "2030-01-01T10:00:00+00:00"})
        assert response.status_code == 404, path
    # A stranger cannot host another team's page or set its agents' hours: to them, that
    # agent does not exist.
    assert client.put(f"/api/booking/availability/{owner['email']}", headers=stranger["headers"],
                      json={"timezone": "UTC", "weekly": ALWAYS}).status_code == 404
    assert client.post("/api/booking/event-types", headers=stranger["headers"],
                       json={"preset": "phone_call", "hosts": {"mode": "specific", "users": [owner["email"]]}}
                       ).status_code == 422


def test_free_times_never_reveal_who_booked_what(client):
    owner = register(client)
    open_all_day(client, owner)
    page = create_page(client, owner)
    book(client, page, slots(client, page)[0])
    raw = client.get(f"/api/public/booking/{page['public_key']}/slots",
                     params={"start": day(2).isoformat(), "end": day(2).isoformat(), "tz": "UTC"}).text
    for secret in ("jamie", "Jamie", "555", "Oak", "apt_", owner["email"]):
        assert secret not in raw


# ----------------------------------------------------------------- permissions

def test_members_see_the_calendar_and_manage_only_their_own_appointments(client):
    owner = register(client)
    member = add_member(client, owner)
    open_all_day(client, owner)
    open_all_day(client, member)
    mine = create_page(client, owner)
    theirs = create_page(client, owner, name="Member showing",
                         hosts={"mode": "specific", "users": [member["email"]]})
    book(client, mine, slots(client, mine)[0])
    book(client, theirs, slots(client, theirs)[1], email="m@example.com", phone="5550100150")
    rows = client.get("/api/booking/appointments", headers=member["headers"]).json()["items"]
    assert len(rows) == 2
    owners = {r["owner"]: r for r in rows}
    assert owners[member["email"]]["can_manage"] and not owners[owner["email"]]["can_manage"]
    assert client.get("/api/booking/appointments?scope=mine", headers=member["headers"]).json()["items"][0]["owner"] == member["email"]
    # Members cannot create or change booking pages, or anyone else's hours.
    assert client.post("/api/booking/event-types", headers=member["headers"], json={"preset": "phone_call"}).status_code == 403
    assert client.patch(f"/api/booking/event-types/{mine['id']}", headers=member["headers"], json={"name": "x"}).status_code == 403
    assert client.put(f"/api/booking/availability/{owner['email']}", headers=member["headers"],
                      json={"timezone": "UTC", "weekly": ALWAYS}).status_code == 403
    assert client.put(f"/api/booking/availability/{member['email']}", headers=member["headers"],
                      json={"timezone": NY, "weekly": booking.default_weekly()}).status_code == 200
    # ...and cannot cancel a colleague's appointment, but can cancel their own.
    other_id = owners[owner["email"]]["id"]
    own_id = owners[member["email"]]["id"]
    assert client.post(f"/api/booking/appointments/{other_id}/cancel", headers=member["headers"],
                       json={"reason": "no"}).status_code == 403
    assert client.post(f"/api/booking/appointments/{own_id}/cancel", headers=member["headers"],
                       json={"reason": "Client asked", "notify_person": False}).status_code == 200
    # Admins see everyone's hours; a member sees their own.
    assert len(client.get("/api/booking/availability", headers=owner["headers"]).json()["items"]) == 2
    assert [i["user_email"] for i in client.get("/api/booking/availability", headers=member["headers"]).json()["items"]] == [member["email"]]


def test_round_robin_spreads_bookings_and_keeps_a_returning_client_with_their_agent(client):
    owner = register(client)
    member = add_member(client, owner)
    open_all_day(client, owner)
    open_all_day(client, member)
    page = create_page(client, owner, hosts={"mode": "round_robin", "users": [owner["email"], member["email"]]})
    times = slots(client, page)
    hosts = []
    for index in range(4):
        response = book(client, page, times[index * 2], email=f"rr{index}@example.com", phone=f"555020{index:04d}")
        assert response.status_code == 200, response.text
        hosts.append(find_one(client, "appointments", {"booking.person.email": f"rr{index}@example.com"})["owner"])
    assert set(hosts) == {owner["email"], member["email"]}
    # Both agents are free at one time: it stays on the page until both are booked.
    shared = times[10]
    assert book(client, page, shared, email="s1@example.com", phone="5550300001").status_code == 200
    assert shared in slots(client, page)
    assert book(client, page, shared, email="s2@example.com", phone="5550300002").status_code == 200
    assert shared not in slots(client, page)
    # A returning client goes back to the agent who owns them, when that agent is free.
    first_host = find_one(client, "appointments", {"booking.person.email": "rr0@example.com"})["owner"]
    book(client, page, times[14], email="rr0@example.com", phone="5550200000")
    again = find_all(client, "appointments", {"booking.person.email": "rr0@example.com"})
    assert {a["owner"] for a in again} == {first_host}


# ------------------------------------------------------- agent actions & no-shows

def test_a_no_show_marked_by_the_agent_is_picked_up_by_the_no_show_detector(client):
    owner = register(client)
    open_all_day(client, owner)
    page = create_page(client, owner)
    book(client, page, slots(client, page)[0])
    appointment = find_one(client, "appointments", {"tenant_id": owner["tenant_id"]})
    early = client.post(f"/api/booking/appointments/{appointment['id']}/outcome",
                        headers=owner["headers"], json={"outcome": "no_show"})
    assert early.status_code == 409, "a future appointment cannot be a no-show"
    past = datetime.now(UTC) - timedelta(minutes=40)
    update(client, "appointments", {"id": appointment["id"]},
           {"$set": {"start_at": past.isoformat(), "end_at": (past + timedelta(minutes=30)).isoformat()}})
    marked = client.post(f"/api/booking/appointments/{appointment['id']}/outcome",
                         headers=owner["headers"], json={"outcome": "no_show"})
    assert marked.status_code == 200 and marked.json()["status"] == "no_show"
    # Marked within the grace period, and with a preparation task on the contact: the
    # explicit no-show is still found.
    found = call(client, detectors.detect_no_shows, server.db, owner["tenant_id"])
    assert [d["record_id"] for d in found] == [appointment["id"]]
    assert "recorded as a no-show" in found[0]["reason"]
    assert found[0]["contact_id"] == appointment["contact_id"]
    attended = client.post(f"/api/booking/appointments/{appointment['id']}/outcome",
                           headers=owner["headers"], json={"outcome": "attended"})
    assert attended.json()["status"] == "completed"
    assert not call(client, detectors.detect_no_shows, server.db, owner["tenant_id"])


def test_the_agent_reschedules_and_cancels_on_the_persons_behalf(client):
    owner = register(client)
    open_all_day(client, owner)
    page = create_page(client, owner, min_notice_hours=24)
    times = slots(client, page)
    book(client, page, times[0])
    appointment = find_one(client, "appointments", {"tenant_id": owner["tenant_id"]})
    agent_times = client.get(f"/api/booking/event-types/{page['id']}/slots", headers=owner["headers"],
                             params={"start": day(0).isoformat(), "end": day(1).isoformat(), "tz": "UTC",
                                     "ignore": appointment["id"]}).json()
    soon = [s for d in agent_times["days"] for s in d["slots"]]
    assert soon, "an agent is not held to the public page's minimum notice"
    moved = client.post(f"/api/booking/appointments/{appointment['id']}/reschedule", headers=owner["headers"],
                        json={"start": soon[-1], "notify_person": True})
    assert moved.status_code == 200, moved.text
    assert moved.json()["start_at"] == soon[-1]
    # No email channel: the reschedule note is recorded as not emailed, with the reason.
    rescheduled = [m for m in moved.json()["messages"] if m["kind"] == "rescheduled"][0]
    assert rescheduled["status"] == "not_sent" and "isn't connected" in rescheduled["detail"]
    cancelled = client.post(f"/api/booking/appointments/{appointment['id']}/cancel", headers=owner["headers"],
                            json={"reason": "Seller withdrew the listing"})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    task = find_one(client, "tasks", {"source.appointment_id": appointment["id"]})
    assert task["status"] == "cancelled"


# --------------------------------------------------- emails to the person: governance

def test_each_email_to_the_person_waits_for_its_own_admin_approval(client):
    owner = register(client)
    open_all_day(client, owner)
    fake = connect_email(client, owner)
    page = create_page(client, owner)
    response = book(client, page, slots(client, page)[0])
    appointment = find_one(client, "appointments", {"tenant_id": owner["tenant_id"]})
    record = appointment["booking"]["messages"]["confirmation"]
    assert record["status"] == cv.PENDING_APPROVAL
    approval = find_one(client, approval_queue.COLLECTION, {"id": record["approval_id"]})
    assert approval["status"] == approval_queue.REQUESTED and approval["kind"] == "communication_message"
    assert approval["requested_by"] == booking.SYSTEM_ACTOR
    # Nothing leaves before a person approves, however often the sweep runs.
    call(client, server.booking_service.send_due_reminders)
    assert fake.sent == []
    message = find_one(client, cv.MESSAGES, {"id": record["message_id"]})
    assert token_of(response) in message["body"], "the email carries the person's change link"
    conversation = find_one(client, cv.CONVERSATIONS, {"id": message["conversation_id"]})
    assert conversation["consent"]["state"] == cv.CONSENT_GRANTED
    assert "booked 'Home showing'" in conversation["consent"]["basis"]
    decided = client.post(f"/api/approval-queue/{approval['id']}/decision", headers=owner["headers"],
                          json={"decision": "approved", "rationale": "Confirmation wording is right"})
    assert decided.status_code == 200, decided.text
    assert client.post(f"/api/booking/appointments/{appointment['id']}/deliver",
                       headers=owner["headers"]).json() == {"sent": 1, "refused": 0}
    assert len(fake.sent) == 1 and fake.sent[0]["to_address"] == "jamie.buyer@example.com"
    assert fake.sent[0]["subject"].startswith("Confirmed: Home showing")
    # A second sweep does not send it again.
    call(client, server.booking_service.send_due_reminders)
    assert len(fake.sent) == 1
    status = client.get("/api/booking/status", headers=owner["headers"]).json()
    assert status["standing_approval"] is False and status["email_channel"]["authorized"] is True


def test_moving_a_booking_withdraws_the_unsent_emails_about_the_old_time(client):
    owner = register(client)
    open_all_day(client, owner)
    fake = connect_email(client, owner)
    page = create_page(client, owner)
    times = slots(client, page)
    token = token_of(book(client, page, times[0]))
    first = find_one(client, "appointments", {"tenant_id": owner["tenant_id"]})["booking"]["messages"]["confirmation"]
    client.post(f"/api/public/booking/manage/{token}/reschedule", json={"start": times[2]})
    old = find_one(client, cv.MESSAGES, {"id": first["message_id"]})
    assert old["status"] == cv.BLOCKED and old["blocked_reason"] == "superseded"
    assert find_one(client, approval_queue.COLLECTION, {"id": first["approval_id"]})["status"] == approval_queue.CANCELLED
    moved = find_one(client, "appointments", {"tenant_id": owner["tenant_id"]})["booking"]["messages"]["rescheduled"]
    assert moved["status"] == cv.PENDING_APPROVAL
    assert fake.sent == []


# --------------------------------------------------------------------- reminders

def test_reminders_go_out_once_each_at_24_hours_and_1_hour(client):
    owner = register(client)
    open_all_day(client, owner)
    page = create_page(client, owner)
    start_text = slots(client, page, first=day(3))[0]
    book(client, page, start_text)
    appointment = find_one(client, "appointments", {"tenant_id": owner["tenant_id"]})
    start = datetime.fromisoformat(start_text)
    service = server.booking_service

    # The sweep covers every tenant, so this reads only this tenant's reminders.
    def reminders():
        return [n for n in find_all(client, "notifications", {"tenant_id": owner["tenant_id"],
                                                              "type": "booking.reminder"})]

    call(client, service.send_due_reminders, start - timedelta(hours=30))
    assert reminders() == []
    call(client, service.send_due_reminders, start - timedelta(hours=23))
    assert len(reminders()) == 1 and "in 24 hours" in reminders()[0]["title"]
    call(client, service.send_due_reminders, start - timedelta(hours=22))
    assert len(reminders()) == 1

    async def two_at_once():
        return await asyncio.gather(service.send_due_reminders(start - timedelta(minutes=50)),
                                    service.send_due_reminders(start - timedelta(minutes=50)))

    client.portal.call(two_at_once)
    assert len(reminders()) == 2
    assert "in 1 hour" in reminders()[-1]["title"]
    stored = find_one(client, "appointments", {"id": appointment["id"]})
    assert set(stored["booking"]["reminders_claimed"]) == {"24h", "1h"}
    assert stored["booking"]["reminders"]["1h"]["person"] == "not_sent"
    # The module-level entry point a scheduler calls runs the same sweep.
    assert asyncio.iscoroutinefunction(booking.send_due_reminders)


def test_a_booking_made_inside_a_reminders_window_skips_that_reminder(client):
    owner = register(client)
    open_all_day(client, owner)
    page = create_page(client, owner)
    soon = datetime.now(UTC) + timedelta(hours=20)
    start_text = [s for s in slots(client, page, first=day(0), last=day(1))
                  if datetime.fromisoformat(s) > soon][0]
    book(client, page, start_text)
    start = datetime.fromisoformat(start_text)
    assert start - timedelta(hours=24) < datetime.now(UTC), "booked inside the 24-hour window"
    call(client, server.booking_service.send_due_reminders, start - timedelta(hours=2))
    stored = find_one(client, "appointments", {"tenant_id": owner["tenant_id"]})
    assert stored["booking"]["reminders"]["24h"]["status"] == "skipped"
    assert not find_all(client, "notifications", {"tenant_id": owner["tenant_id"], "type": "booking.reminder"})


def test_the_reminder_job_is_scheduled_and_served(client):
    assert scheduler.SCHEDULE["booking-reminders"] == "*/5 * * * *"
    assert "booking-reminders" in server.CRON_JOBS
    assert server.job_scheduler.jobs["booking-reminders"] is server.CRON_JOBS["booking-reminders"]
    assert client.post("/api/cron/booking-reminders").status_code == 401


# ------------------------------------------------------------ Google Calendar

def test_google_busy_times_are_subtracted_for_the_connected_agent_only(client):
    owner = register(client)
    open_all_day(client, owner)
    page = create_page(client, owner)
    times = slots(client, page)
    blocked = datetime.fromisoformat(times[2])
    seen = []

    async def fake_busy(tenant_id, host, lo, hi):
        seen.append(host)
        return [(blocked, blocked + timedelta(minutes=30))] if host == owner["email"] else None

    server.booking_service.busy_fetcher = fake_busy
    assert times[2] not in slots(client, page)
    assert seen and set(seen) == {owner["email"]}
    # Without a Google connection the real fetcher declines without calling Google.
    real = call(client, server.booking_service._google_busy, owner["tenant_id"], owner["email"],
                blocked, blocked + timedelta(hours=1))
    assert real is None


# --------------------------------------------------------------- booking pages

def test_booking_pages_are_validated_and_the_presets_install_in_one_step(client):
    owner = register(client)
    installed = client.post("/api/booking/event-types/defaults", headers=owner["headers"],
                            json={"timezone": NY})
    assert installed.status_code == 200
    names = [p["name"] for p in installed.json()["created"]]
    assert names == ["Home showing", "Buyer consultation", "Listing appointment", "Phone call"]
    durations = {p["preset"]: p["duration_minutes"] for p in installed.json()["created"]}
    assert durations == {"home_showing": 30, "buyer_consultation": 45, "listing_appointment": 60, "phone_call": 15}
    again = client.post("/api/booking/event-types/defaults", headers=owner["headers"], json={})
    assert again.json()["created"] == []
    availability = client.get("/api/booking/availability", headers=owner["headers"]).json()["items"][0]
    assert availability["timezone"] == NY and availability["saved"] is True
    consultation = next(p for p in installed.json()["created"] if p["preset"] == "buyer_consultation")
    # A video meeting needs its link; an office address can be added later.
    assert client.patch(f"/api/booking/event-types/{consultation['id']}", headers=owner["headers"],
                        json={"location": {"kind": "video", "text": "zoom"}}).status_code == 422
    fixed = client.patch(f"/api/booking/event-types/{consultation['id']}", headers=owner["headers"],
                         json={"location": {"kind": "office", "text": "1 Main St, Suite 2"}})
    assert fixed.status_code == 200
    # Meeting at the property makes the property address a required question.
    moved = client.patch(f"/api/booking/event-types/{consultation['id']}", headers=owner["headers"],
                         json={"location": {"kind": "property"}})
    questions = {q["key"]: q["required"] for q in moved.json()["questions"]}
    assert questions["property_address"] is True
    showing = next(p for p in installed.json()["created"] if p["preset"] == "home_showing")
    assert client.patch(f"/api/booking/event-types/{showing['id']}", headers=owner["headers"],
                        json={"public_key": "Not a Slug!"}).status_code == 422
    assert client.patch(f"/api/booking/event-types/{showing['id']}", headers=owner["headers"],
                        json={"public_key": consultation["public_key"]}).status_code == 409
    renamed = client.patch(f"/api/booking/event-types/{showing['id']}", headers=owner["headers"],
                           json={"public_key": f"avery-showings-{uuid.uuid4().hex[:6]}"})
    assert renamed.status_code == 200 and renamed.json()["links"]["page"].endswith(renamed.json()["public_key"])
    assert 'data-clientverse-booking' in renamed.json()["links"]["popup"]
    assert 'embed=1' in renamed.json()["links"]["iframe"]


def test_the_calendar_file_folds_long_lines_and_escapes_text():
    appointment = {"id": "apt_1", "title": "Home showing — Jamie, Buyer; with notes",
                   "start_at": "2026-10-20T14:00:00+00:00", "end_at": "2026-10-20T14:30:00+00:00",
                   "status": "confirmed", "booking": {"sequence": 2}}
    text = booking.ics_document(appointment, description="Line one\nLine two " + "x" * 120,
                                location="12 Oak St, Springfield")
    lines = text.split("\r\n")
    assert all(len(line.encode("utf-8")) <= 75 for line in lines)
    assert "SUMMARY:Home showing — Jamie\\, Buyer\\; with notes" in text.replace("\r\n ", "")
    assert "DTSTART:20261020T140000Z" in text and "SEQUENCE:2" in text
    assert "LOCATION:12 Oak St\\, Springfield" in text
