# Website forms — connecting an agent's real-estate website to ClientVerse

**Status (2026-10-17):** built on branch `claude/inspiring-edison-myhdzx`. Not yet merged or
deployed. Verified locally: 30 backend tests (`backend/tests/test_website_forms.py`) and an
18-step real-browser run. In that run a page served from a *different origin* rendered the
embed and submitted through it, and a plain HTML form posted and redirected. The CRM UI then
showed each lead with its clock, the contact, the deal, the task and the alert.

## Why this exists

The earlier intake door (`POST /api/intake/public/{token}/web-enquiries`) could not take a
lead from a real website end to end:

| Problem | Effect |
|---|---|
| CORS refused every browser on another domain | Any JavaScript form on the agent's site failed |
| JSON-only body | A plain HTML `<form method="post">` got a 422 |
| Unknown fields silently dropped | Property address, MLS #, price, timeline, consent: all lost |
| No contact, no owner, no alert | The lead sat in a collection nobody could see |
| Only "detection" after 24 h, and only if the scheduler ran | A real-estate lead is cold within minutes |
| No spam protection, no rate limit, no de-duplication | Bots and double-clicks became leads |
| No screen to mint a token or see enquiries | API-only |

The public route had **no tests**, which is why none of this was caught. Every test now goes in
through the public HTTP door with the headers a browser sends.

## What happens to every submission (automatically, in about a second)

1. **Accepted from where websites really post from.** Browser JavaScript on any domain (or only
   the domains you allow), plain HTML forms, Zapier/Make, and form-plugin webhooks. Accepted
   formats are JSON, `text/plain` JSON (no browser preflight), URL-encoded and multipart.
2. **Policed.** A honeypot and a minimum fill time catch bots, which get the same "thank you"
   a person gets. Each visitor is limited to 20 per hour and each form to 120 per minute. A
   retry with the same submission id is filed once. The same person sending the same thing
   within 10 minutes collapses onto the first submission.
3. **Nothing lost.** Every catalogue field is typed, unknown fields are kept verbatim, UTM tags,
   referrer and page are kept as attribution, and consent is kept with the exact wording shown,
   the time, the IP and the page.
4. **Contact matched or created.** Matching is on email (case-insensitive) or phone (last ten
   digits, any formatting), so a returning lead is never duplicated. You choose per form;
   "always new" is available.
5. **Owner assigned.** The existing owner, a specific agent, or round-robin across the agents
   you pick.
6. **Deal opened** at the stage you choose, valued at *expected commission*. That is the price
   the visitor gave (max price, home value or min price) × your commission %. With no realistic
   price it uses your flat value. A visitor can never set the money figure themselves. A
   returning lead with an open deal from the same form within 30 days is linked to it, not
   doubled.
7. **Speed-to-lead task** "Call new lead now", due in 5 minutes (configurable), high priority,
   with the whole request in its notes.
8. **Agent alerted** in-app, and by email when email delivery is configured.
9. **`lead.received` webhook event** with the full lead. Point a webhook at Zapier, Slack or an
   SMS tool for text alerts.
10. **Automatic reply** to the lead (optional). See *Approval* below.
11. **The clock is watched.** The API checks every minute, without the external scheduler, and
    `POST /api/cron/lead-sla` runs the same sweep. A response is recognised from:
    - the call-back task being completed,
    - a call, email or meeting logged on the contact,
    - the lead being marked contacted.

    The response time is recorded. A lead still uncontacted at the escalation deadline (15 min
    by default) is escalated to the admins and the agent, once.

## Setting it up (agent / owner)

1. **Website forms → New form.** Pick a template:
   - Contact
   - Schedule a showing
   - What's my home worth
   - Buyer consultation
   - Seller consultation
   - Open house sign-in
   - Listing alerts
   - Custom
2. **Fields:** add, remove, reorder, rename, mark required, add custom fields (text, long text,
   dropdown, checkbox, number, date).
3. **Settings:**
   - button text and thank-you message, or a redirect to your own thank-you page (use that to
     fire ad pixels);
   - allowed websites;
   - duplicate handling;
   - tags;
   - consent wording;
   - colour and layout.
4. **Automation:** assignment, call-back time, escalation time, alerts, deal stage and value.
5. **Auto-reply:** write it, save, then **Approve this wording**.
6. **Embed & test:** **Send a test lead** proves the whole path; test leads never count in
   reporting. Then copy the embed that suits the site:

| Website / tool | Use |
|---|---|
| WordPress (Custom HTML block), Squarespace (Code block), Webflow (Embed), most IDX "custom HTML" areas | **Inline form**, or **On a listing page** to attach the MLS # and address to every lead from that page |
| Any site, as a button / timed / scroll / exit-intent pop-up | **Pop-up on a button**, **Pop-up after a delay** (`data-trigger="delay:15"`, `scroll:50`, `exit`), **Slide-in** |
| Wix and builders that only allow iframes | **iFrame** (the hosted page is the only CRM page that may be framed) |
| Text messages, email signatures, QR codes, social bios | **Hosted link** |
| Keep the site's existing form design | **Your own HTML form**: point its `action` at the submit URL and keep the hidden `_hp` field |
| Contact Form 7 / Gravity Forms / WPForms / Elementor webhooks, Zapier, Make, IDX vendors that post leads | **API**: `POST` JSON or form data to the submit URL. Common field names are understood (`your-name`, `your-email`, `fname`, `mls_number`, `address`, `budget`, …). Send a unique `_sid` per submission so retries are never filed twice |

### Custom-built websites (recommended): server connection

A website with its own form backend should forward leads from its server instead of embedding
a form. Next.js, a custom app, or a WordPress plugin that posts server-side all qualify. The
site keeps its own form design, saves each lead in its own database first, and delivers it to
the CRM with a **server key**, retrying until the CRM accepts it. A lead survives either side
being briefly down. This is stronger than GoHighLevel's usual fire-and-forget webhook.

1. **Website Forms → (form) → Embed & test → Create server key.** The key is shown once and
   stored hashed. **Replace key** rotates it and the old key stops working at once; **Revoke**
   turns it off.
2. Put the three values shown into the website's hosting environment and redeploy:
   `CRM_PROVIDER=clientverse`, `CLIENTVERSE_INTAKE_URL=https://<crm>/api/intake/leads`,
   `CLIENTVERSE_API_KEY=cvsk_…`. One intake address serves every website: the key identifies the
   form, and so the workspace. A keyed post to the form's own `/submit` URL works the same way.
3. The website's server sends `POST` with `Authorization: Bearer cvsk_…` and a JSON body.

**What the CRM accepts on this path:**
- The website's own field names: `name`, `email`, `phone`, `propertyAddress`, `timeframe`,
  `consultationDate`, `consultationTime`, `leadType`, `source`, `message`.
- A nested `payload`, whose entries are lifted to the top level. Examples: `priceRange` such as
  "$400k–$500k" becomes `price_min` and `price_max`; `preapproval`; `condition`; `goal`;
  `firstName` and `lastName`.
- `idempotencyKey`: a retry with the same key is filed once.
- `leadType` / `goal` wording is mapped to Buying / Selling / Buying and selling / Renting /
  Investing, and the original wording is kept.

**How these requests are treated:**
- They skip browser-only checks: allowed websites, CAPTCHA, and the per-visitor limit (every
  lead comes from the same server).
- They are filed even when the visual form marks a field required that the site doesn't
  collect. Refusing a real lead over a display setting would lose it.
- They still need an email or a phone number, and still count against the per-form limit.
- A wrong or revoked key gets `401`. A lead with no way to contact the person gets `422`, which
  the website should treat as final. `429` and `5xx` should be retried.

Website builders' JavaScript can listen for the `clientverse:lead` browser event (fired on
`window` after a successful submission) to trigger their own analytics.

## Approval of the automatic reply (governance)

Every outbound message passes through `conversations.attempt_delivery`, which requires a human
approval bound to the exact words. For automatic replies, the approval is given **once, for the
template**:

- **What the admin approves:** the exact subject and body.
- **How each reply is built:** from that template, filling in only `{first_name}` (sanitised),
  `{agent_name}` and `{form_name}`.
- **What each reply still goes through:** its own conversation and its own consent record (the
  basis is the enquiry the person just sent). It also gets its own single-use approval, decided
  by `standing-approval:<id>`, with the template fingerprint and merge values recorded. The same
  channel, consent and provider checks apply as for any other message.
- **What revokes it:** editing the template.

Nothing else is ever sent on a standing approval. This bounded amendment to M-07 was made at the
owner's direction on 2026-10-17 and is recorded in the canonical governing document.

Replies go through the connected Gmail account. If Gmail isn't connected and certified, the lead
shows the reply as **blocked** with the reason; the lead itself is unaffected.

## Owner actions for production

| # | Action | Why |
|---|---|---|
| 1 | Merge this branch and let Railway redeploy | Nothing above is live until then |
| 2 | Check **Settings → Email delivery** shows *Configured* (`EMERGENT_EMAIL_KEY`) | Email alerts to agents. In-app alerts work regardless |
| 3 | Keep `FRONTEND_URL` set to the public `https://` address agents' sites will use (ideally the custom domain) | Embed codes, hosted links and email buttons are built from it |
| 4 | For automatic replies: connect Gmail with send permission, then approve the template | Without it, replies show as *blocked*; leads still flow |
| 5 | Optional: add `lead-sla` to the external scheduler | The API already runs this sweep every minute; this is belt and braces |
| 6 | Optional: point a webhook at `lead.received` (Registries → Webhooks) | Text-message or Slack alerts via Zapier until an SMS provider exists |

## API reference

**Public (no login).** Every one is CORS-open and never credentialed.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/public/forms/embed.js` | Embed script |
| `GET` | `/api/public/forms/{key}/config` | How to draw the form. Counts a view |
| `GET` | `/api/public/forms/{key}/page` | Hosted page (frameable) |
| `POST` | `/api/public/forms/{key}/submit` | Submit. Returns JSON, or 303/HTML for HTML forms. Possible errors: 422 with per-field `errors`, 403 (site not allowed), 429 with `Retry-After`, 404 (paused or unknown) |
| `POST` | `/api/intake/public/{token}/web-enquiries` | Legacy token door, now through the same pipeline |

**Signed in:**

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/website-forms/catalog` | |
| `GET` | `/api/website-forms` | |
| `GET` | `/api/website-forms/{id}` | |
| `POST` | `/api/website-forms` | Admin only |
| `PATCH` | `/api/website-forms/{id}` | Admin only |
| `POST` | `/api/website-forms/{id}/test` | Admin only |
| `GET` | `/api/leads` | Filters: `status`, `form_id`, `q`, `include_tests` |
| `GET` | `/api/leads/summary` | |
| `GET` | `/api/leads/{id}` | |
| `PATCH` | `/api/leads/{id}` | `{status: new\|responded\|closed\|spam, note?}`. Marking spam archives the contact and deal the submission created |

**Events:**
- `web_enquiry.received`
- `lead.received` (full lead)
- `lead.responded`
- `lead.sla_breached`
- `lead.status_changed`
- `website_form.created` / `updated`

## Feature map against GoHighLevel (forms and what happens after)

Legend: ✅ built · 🟡 partly / different approach · ❌ not yet.

GHL behaviour is taken from GHL's help-centre and tutorial material:
- [Allow duplicate contacts](https://help.gohighlevel.com/support/solutions/articles/48001181714-allow-duplicate-contacts-contact-deduplication-preferences-)
- [Embedding forms on non-HighLevel sites](https://help.gohighlevel.com/support/solutions/articles/155000004524-embedding-highlevel-forms-on-non-highlevel-websites)
- [Embedding options: triggers, layouts, deactivation](https://growthable.io/gohighlevel-tutorials/forms/how-to-use-embedding-options-for-forms-in-gohighlevel-triggers-layouts-and-deactivation-settings-explained/)
- [Sticky contact](https://growthable.io/gohighlevel-tutorials/forms/sticky-contact-form-in-gohighlevel/)
- [Round-robin assignment](https://growthable.io/gohighlevel-tutorials/workflows/how-to-use-workflows-to-assign-users-to-leads-for-gohighlevel/)

### Building the form

| GHL option | ClientVerse | Notes |
|---|---|---|
| Field builder, standard + custom fields, reorder, required | ✅ | Real-estate catalogue of 24 fields plus custom text / long text / dropdown / checkbox / number / date |
| Templates | ✅ | 8 real-estate templates |
| Hidden fields / URL capture (UTM, source, page) | ✅ | Automatic: page, referrer, landing page, UTM ×5, gclid, fbclid; listing prefill from the page or URL |
| T&C / SMS consent checkbox | ✅ | Wording configurable; stored with evidence (time, IP, page, user agent) |
| Styling | 🟡 | Button colour and 1/2-column layout; inherits the site's fonts. No custom CSS editor |
| Conditional logic | ✅ | Show a field only when an earlier answer matches (e.g. the address only for sellers). Hidden answers are neither required nor stored |
| Multi-step forms | ✅ | Up to 5 steps with progress, Back/Next, and per-step validation. A server error jumps back to the right step |
| Surveys with scoring / disqualification | ❌ | Next |
| File upload | ❌ | Deliberately not accepted on a public form (malware/PII risk) until storage scanning exists |
| CAPTCHA | ✅ | Cloudflare Turnstile per form, with its secret encrypted at rest and never returned. Always on as well: honeypot, minimum fill time, per-visitor and per-form rate limits |

### On submit and duplicates

| GHL option | ClientVerse | Notes |
|---|---|---|
| Thank-you message or redirect | ✅ | |
| Fire a pixel on submit | 🟡 | Redirect to your own thank-you page, or listen for the `clientverse:lead` event |
| Allow duplicate contacts on/off | ✅ | Per form, not location-wide |
| Sticky contact (pre-fill a known visitor) | ✅ | Opt-in per form ("Remember returning visitors"). Off by default because it keeps details in the visitor's browser |

### Embedding

| GHL option | ClientVerse | Notes |
|---|---|---|
| Inline JS embed | ✅ | |
| iFrame | ✅ | |
| Direct link | ✅ | |
| Pop-up | ✅ | |
| Pop-up triggers (time, scroll %, exit) | ✅ | |
| Slide-in | ✅ | |
| Don't show again after submission | ✅ | |
| WordPress plugin | 🟡 | Paste into a Custom HTML block; webhook mapping for CF7, Gravity Forms and WPForms field names |

### Automation after submit (GHL builds these as a workflow)

| GHL option | ClientVerse | Notes |
|---|---|---|
| Create / update contact | ✅ | |
| Add tags | ✅ | |
| Assign user / round-robin | ✅ | Equal or weighted split (1×–5× share per agent) |
| Create opportunity (pipeline, stage, value) | ✅ | Value can be expected commission (GCI) |
| Internal notification | ✅ | In-app and email; SMS via the `lead.received` webhook |
| Create task | ✅ | Speed-to-lead task due in minutes |
| Speed-to-lead escalation | ✅ | Built in; in GHL you assemble it yourself |
| Send email to the lead | ✅ | Approved template, via Gmail |
| Send SMS to the lead | ❌ | Needs an SMS provider (M-03, owner decision) |
| Missed-call text-back | ❌ | Needs telephony (O-06) |
| Webhook | ✅ | `lead.received` and the other events listed above |
| Inbound from a custom website's server | ✅ | Server key with rotation and revocation, idempotent, delivered from the site's own durable outbox. Stronger than an inbound webhook URL anyone could post to |
| Wait / delays, if-else, drip sequences | ❌ | The Workflows module (contract pending) |
| Lead scoring | ❌ | |

### Reporting and lead sources

| GHL option | ClientVerse | Notes |
|---|---|---|
| Submissions list per form | ✅ | Leads inbox with filters, search and CSV export (formula-safe) |
| Form views and conversion rate | ✅ | |
| Response-time reporting | ✅ | Median, share inside 5 minutes, escalations |
| Lead source attribution | ✅ | By UTM source or referrer |
| Facebook / Google lead ads, Zillow, Realtor.com | 🟡 | Via Zapier → the API URL. Native connectors and lead-email parsing are next |
| Calendar booking ("book a showing" slot picker) | ❌ | The Calendar module (M-05) |
| Chat widget | ❌ | |

## Testing it yourself, end to end

1. Create a form, then **Send a test lead**. Check that the green box lists contact, assignment,
   opportunity and task, and that the lead appears in **Leads** marked *Test*.
2. Paste the inline embed on a page of the real website. Open it in a private window with
   `?utm_source=test`, submit, and check:
   - the thank-you message appears;
   - the lead appears in **Leads** within 30 seconds, with the page, the UTM source and the
     consent record;
   - the agent got the alert.
3. Wait past the escalation time without touching it: an escalation alert arrives once. Then
   **Mark contacted**: the response time is recorded and the call-back task closes.
4. Submit twice quickly with the same details: only one lead.
