# Online booking (M-05)

People pick a real open time for a home showing, a buyer consultation, a listing
appointment or a phone call. The booking lands in ClientVerse as a lead, a contact, a deal
and an appointment; the agent is alerted; the person gets a confirmation with
add-to-calendar buttons and a link to reschedule or cancel; reminders follow.

Code: `backend/booking.py` (tests: `backend/tests/test_booking.py`),
`frontend/src/pages/Calendar.jsx`, `frontend/src/pages/PublicBooking.jsx`,
`frontend/src/pages/ManageBooking.jsx`, `frontend/src/components/booking/`.

## Set it up (admin, five minutes)

1. **Calendar → Booking pages → Create my booking pages.** This makes four pages hosted
   by you — Home showing (30 min), Buyer consultation (45), Listing appointment (60) and
   Phone call (15) — and saves your hours as Monday to Saturday, 9 to 6, in your
   computer's time zone.
2. **Calendar → Availability.** Check the time zone, change any day's hours (add a second
   block for a lunch break), and add days off or special hours (a Sunday open house). Save.
   Every agent can set their own; admins can set anyone's.
3. **Edit each page** if you want to: the length, the free time before and after (travel
   between showings), how much notice you need, how far ahead people can book, where it
   happens (the property they name, your office address, a phone call, a video link), who
   hosts it (one agent, or round-robin — a returning client goes back to their own agent
   when that agent is free), which questions it asks, whether it opens a deal (valued at
   your commission when they give a price), the preparation task, and the reminders.
4. **Share it.** Copy the link, or **Embed code** for a website: a link, a pop-up button,
   the page inside your page (it grows to fit), or a plain iframe. On a listing page add
   `?property_address=…&listing_id=…` to the link to fill in the property. A website form
   can send people to booking after they submit: set its thank-you redirect (Website forms
   → Settings) to the booking link.

## What happens on each booking

- The time is re-checked and written under a per-agent lock; a second person who picked
  the same time is told it was just taken and shown the times still open.
- The person runs through the website-forms pipeline: matched to an existing contact or
  added, assigned, a deal opened if the page says so, and `lead.received` published to
  webhooks. The lead is recorded as answered by the booking (it is not an unanswered
  enquiry), without a response time.
- The appointment goes into the same `appointments` collection client operations uses,
  status `confirmed`, linked to the contact, the deal and the lead.
- The host gets a preparation task (for a showing: arrange access; for a listing
  appointment: a pricing analysis), due before the appointment, and an alert in the app —
  and by email when the CRM's mail is configured.
- The person sees a confirmation with Google Calendar and `.ics` buttons and their change
  link.

## Emails to the person need approval

The governing document allows a standing approval for exactly one thing: a website form's
automatic reply. Booking emails are not that, so **each confirmation, new-time notice,
cancellation notice and reminder waits for an admin to approve its exact words** — on the
Calendar (Review and approve) or in Operations → Approvals — and is then sent from the
connected Gmail through the same delivery checks as every other message. An approval still
open when the appointment starts lapses. If email isn't connected, nothing is drafted and
the calendar says so; the person still has their on-screen confirmation, calendar file and
change link. Letting booking emails go out without per-email approval would be an owner
amendment to M-07.

## Reminders

24 hours and 1 hour before by default (choose up to three of 48, 24, 12, 4, 2, 1 hours).
Each is claimed exactly once with a conditional update, so the in-process scheduler, the
cron route and a second replica never send it twice. A booking made inside a reminder's
window skips that reminder. The host's reminder is in-app; the person's follows the
approval rule above. Runs every five minutes as the `booking-reminders` job
(`backend/scheduler.py`), also callable as `POST /api/cron/booking-reminders` with the cron
secret, or from code as `await booking.send_due_reminders(db)`.

## After the appointment

Anything whose time has passed without an outcome is listed under **Did these happen?**
Mark **They came** or **No-show**. A no-show is what the no-show recovery lane picks up;
a cancellation that is not rebooked is what the cancelled-appointment lane picks up.

## Google Calendar

When Google is connected (Registries → Integrations), busy times on that account's
primary calendar are taken off the booking pages of the agent who owns that account. The
connection is one Google account per team, so other agents' Google calendars are not read.
If Google cannot be reached, slots fall back to ClientVerse's own appointments.

## API

Signed-in (`Authorization: Bearer …`):

| Method and path | Who | What |
| --- | --- | --- |
| `GET /api/booking/catalog` | all | presets, questions, location kinds, reminder choices |
| `GET /api/booking/status` | all | email channel, Google Calendar account, emails waiting for approval |
| `GET /api/booking/hosts` | all | active team members, with time zones |
| `GET /api/booking/event-types` · `GET …/{id}` | all | booking pages, with links and embed codes |
| `POST /api/booking/event-types` | admin | new page from a preset; without one, the neutral `meeting` preset |
| `POST /api/booking/event-types/defaults` | admin | the four presets, plus your default hours (`{"timezone"}`) |
| `PATCH /api/booking/event-types/{id}` | admin | change a page |
| `GET /api/booking/event-types/{id}/slots?start&end&tz&ignore` | all | free times for an agent rescheduling (no minimum notice) |
| `GET /api/booking/availability` | all | everyone's hours (admin) or your own |
| `PUT /api/booking/availability/{email}` | admin, or yourself | `{timezone, weekly, overrides}` |
| `GET /api/booking/appointments?start&end&scope=mine\|all` | all | appointments with person, links, emails and reminders |
| `POST /api/booking/appointments/{id}/outcome` | host or admin | `{"outcome": "attended" \| "no_show"}` |
| `POST /api/booking/appointments/{id}/cancel` | host or admin | `{reason, notify_person}` |
| `POST /api/booking/appointments/{id}/reschedule` | host or admin | `{start, notify_person, outside_hours}` |
| `POST /api/booking/appointments/{id}/deliver` | host or admin | send this booking's approved emails now |

Public (any website, never with credentials; rate-limited):

| Method and path | What |
| --- | --- |
| `GET /api/public/booking/{key}/config` | how to draw the page (no tenant data) |
| `GET /api/public/booking/{key}/slots?start=YYYY-MM-DD&end=YYYY-MM-DD&tz=Area/City` | free start times only, grouped by the visitor's day (at most 42 days) |
| `POST /api/public/booking/{key}/book` | `{start, timezone, first_name, last_name, email, …questions, _sid, _elapsed_ms, _hp}`; 409 `slot_taken` with fresh times |
| `GET /api/public/booking/manage/{token}` | the person's own booking |
| `GET /api/public/booking/manage/{token}/slots` | free times to move to (their own time stays offered) |
| `POST /api/public/booking/manage/{token}/reschedule` | `{start, timezone}` |
| `POST /api/public/booking/manage/{token}/cancel` | `{reason}` |
| `GET /api/public/booking/manage/{token}/event.ics` | calendar file |
| `GET /api/public/booking/embed.js` | the embed script |

The manage token is an HMAC of the appointment, keyed from `JWT_SECRET`, stored only as a
hash; it opens that one booking and nothing else. `/book/<key>` is the only app route any
site may frame.

## Source

The booking model — event types with durations and buffers, weekly availability with
date overrides, minimum notice, a rolling horizon, slots in the booker's time zone,
confirmation, reminders and change links — is adapted from `calcom/cal.diy` (MIT),
governing document §5 #14. It is re-implemented against ClientVerse's own collections; no
Cal code is copied and Cal is not run.
