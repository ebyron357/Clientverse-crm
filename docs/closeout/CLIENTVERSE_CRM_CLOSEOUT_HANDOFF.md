# ClientVerse CRM — Production Closeout Handoff

| | |
|---|---|
| **Document** | ClientVerse CRM Production Closeout Handoff (Part 1 of the closeout package) |
| **Version** | 1.0 |
| **Date** | 2026-10-24 |
| **Released revision** | `main@6d0d4c6` (merge of PR #48), verified running in production on 2026-10-24 ([§13.3](#133-production-acceptance-results)) |
| **Production address** | **[https://crm.clientverse.io](https://crm.clientverse.io)** (sign in at **[https://crm.clientverse.io/login](https://crm.clientverse.io/login)**) |
| **Part 2 of the package** | [Owner/Admin Manual](../CLIENTVERSE_CRM_OWNER_ADMIN_MANUAL.md): screen-by-screen procedures for every user and administrator workflow |
| **Governing document** | [Canonical Governing Document](../CLIENTVERSE_CRM_CANONICAL_GOVERNING_DOCUMENT.md): product scope and capability status |
| **Repository** | `ebyron357/Clientverse-crm` |

> **No secrets are in this document.** It names where each password, key and connection
> string is kept, never its value.

---

## 1. Closeout summary

### 1.1 Where things stand

ClientVerse CRM runs in production on Railway at **[https://crm.clientverse.io](https://crm.clientverse.io)**, backed by
MongoDB Atlas. A deployment starts automatically for every change merged into `main` on GitHub.
The scheduled jobs run inside the application and are also called every few minutes by a
GitHub Actions workflow. That workflow confirms each call was recorded in production's ledger.

This closeout made one release (PR #48), which:

1. **Completed the website intake repair** (PR #47 and the gaps found in its review):
   - an alias can no longer overwrite a lead's real fields;
   - a changed resubmission is kept as a new enquiry, not discarded;
   - **`$500,000+` is stored as a minimum, never a ceiling**;
   - a budget picked from a website's list (`$500,000+`, `$400k–$500k`) is no longer refused.
2. **Closed two security gaps:**
   - Removed the leftover "Continue with Google" sign-in, which trusted a third party's demo
     service to vouch for any user, including the owner.
   - Restricted the platform-wide job log to the owner's organization.
3. **Fixed defects found by driving the whole CRM in a real browser:**
   - a form's "Email alert" switch was ignored;
   - the Website Forms table hid row actions on laptop screens;
   - a client portal link could be lost;
   - portal links could not be revoked from the screen;
   - copy buttons reported success when the copy had failed;
   - low-contrast buttons;
   - an MCP control that members could see but not use.
4. **Added repeatable production checks** that run from GitHub:
   - **Production acceptance:** the authenticated lead journey and a browser pass on four
     screen widths;
   - **Backup and restore drill:** a real `mongodump` → drop → `mongorestore` cycle, verified
     through the application.

### 1.2 What is verified, and how

| Area | Verified by | Result |
|---|---|---|
| Intake repair (precedence, duplicates, changed data, budget semantics, tenant isolation) | 124 website-form tests (29 new); full CI on real MongoDB 7 | See [§13](#13-tests-performed-and-production-acceptance-results) |
| Whole CRM journey (sign-in/out, roles, invitations, portal, forms, leads, pipeline, tasks, booking, integrations, export, UX at 3 widths, accessibility scan) | Local full stack driven by Playwright; release smoke 82/82; proof-of-life | See [§13](#13-tests-performed-and-production-acceptance-results) |
| Production deployment, revision, health, database, authenticated lead journey, browser pass | **Production acceptance** workflow run against https://crm.clientverse.io | See [§13.3](#133-production-acceptance-results) |
| Scheduled jobs reach production and are recorded | Scheduled-jobs workflow runs (every few minutes) with ledger read-back | See [§8.4](#84-scheduled-jobs) |
| Backup and restore procedure | Backup-and-restore drill workflow | See [§10.4](#104-restore-tested-procedure) |

### 1.3 What only the owner can complete

These need the owner's own accounts or decisions. Each is listed with the exact action in
[§14](#14-remaining-limitations-and-exact-owner-actions):

- **Confirm owner access:** add the two GitHub secrets that let the read-only owner check run, or
  sign in once and tick the checklist.
- **Gmail:** confirm the Gmail connection is live, then decide whether to turn email sending on.
- **Atlas backups:** confirm the Atlas cluster tier and that backups are enabled.
- **Stripe:** decide whether it is in scope (it is not configured).
- **Email notifications:** set the email delivery key, or accept link-only invitations.
- **Costs:** read and record the actual monthly costs from each provider's billing page.
- **Scheduler address and the Vercel copy:** point the scheduler's GitHub secret at
  `https://crm.clientverse.io`, then decide on the unused Vercel project.

---

## 2. Production environment map

### 2.1 Addresses

| What | Address |
|---|---|
| **Production CRM** | **[https://crm.clientverse.io](https://crm.clientverse.io)** |
| Sign in | https://crm.clientverse.io/login |
| Health (no sign-in needed) | https://crm.clientverse.io/api/health |
| Job health (owner's organization admin only) | https://crm.clientverse.io/api/cron/health |
| Railway address (same CRM, same data; kept for old links) | https://clientverse-crm-production-production.up.railway.app |
| Public booking pages | `https://crm.clientverse.io/book/<page key>` |
| Client portal links | `https://crm.clientverse.io/portal/<secret token>` (shown once when created) |
| Website lead intake (server to server) | `POST https://crm.clientverse.io/api/intake/leads` with `Authorization: Bearer cvsk_…` |

`crm.clientverse.io` is a DNS CNAME to Railway. Railway issues and renews its certificate. It
was verified on 2026-10-19.

### 2.2 Deployed revision

- Every merge into `main` deploys. To read what production runs, open
  https://crm.clientverse.io/api/health and read `git_sha`, then compare it with the newest
  commit on `main`.
- The closeout release is **`main@6d0d4c6`**, the merge of PR #48. Production reported exactly
  this `git_sha` during acceptance on 2026-10-24 at 21:27 UTC
  ([§13.3](#133-production-acceptance-results)). Later documentation-only merges redeploy the same
  application code with a newer `git_sha`.
- The previous running revision was `main@394f095` (PR #46). Its scheduled jobs answered `200`
  on 2026-10-24.

### 2.3 Environment map

| Layer | Service | Identifier / location | Managed in |
|---|---|---|---|
| Application | Railway service `clientverse-crm-production` | Project `welcoming-vibrancy` (`bbcb2596-d6f9-45c5-9c03-59cb97f373ea`), environment `production` (`12d1d2d7-3fdf-44a9-b6b6-f1d992642188`), service `5e2ea598-91f0-4f95-a67b-067585b80aa9` | railway.com → project → service |
| Build | Dockerfile (Node 22 builds the screens; Python 3.12 runs the API) | `Dockerfile`, `railway.json` (health check `/api/health`, restart on failure ×5) | GitHub repository |
| Database | MongoDB Atlas cluster `clientverse-production`, database name in `DB_NAME` | Connection string in Railway variable `MONGO_URL` | cloud.mongodb.com |
| Domain | `crm.clientverse.io` CNAME → Railway | DNS for `clientverse.io` | The domain's DNS provider |
| Source and CI | GitHub `ebyron357/Clientverse-crm` | Workflows: CI, Scheduled jobs, Production acceptance, Backup and restore drill | github.com |
| Google | OAuth client for Gmail and Calendar | `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`, redirect `https://crm.clientverse.io/api/integrations/google/callback` | console.cloud.google.com |
| Staging | **None.** There is one environment, production | — | — |

Two other services build copies of the code but are **not** how the CRM is served:

- **Vercel project `clientverse-crm`** (team `tradeiq`): it builds the screens on every push, at
  `clientverse-crm.vercel.app`, and forwards `/api` to Railway. Sign-in on that copy fails, because
  its build calls the Railway API across origins. The scheduler's GitHub secret currently points
  at it ([§14.1](#141-owner-actions-exact) items 11–12).
- **Cloudflare Worker `clientverse-crm`** (created 2026-10-19 in the owner's Cloudflare account):
  it fails its own builds.

---

## 3. Owner sign-in, account setup, administration and recovery

### 3.1 The owner account

- The owner account is created by the application itself from two Railway variables:
  - **`ADMIN_EMAIL`** is the owner's sign-in email;
  - **`ADMIN_PASSWORD`** is the owner's password.
- On first start the application created the organization **"ClientVerse HQ"** with this account
  as its admin.
- **At every restart or deployment the owner password is reset to `ADMIN_PASSWORD`.**
- **Never change `ADMIN_EMAIL`:** a new address creates a new, empty organization.

The values are not in any document. Read them in **Railway → `clientverse-crm-production` →
Variables**.

### 3.2 Sign in (owner and every user)

1. Open **[https://crm.clientverse.io/login](https://crm.clientverse.io/login)**.
2. Under **"Sign in to ClientVerse"**, type your email in **"Work email"** and your password in
   **"Password"**.
3. Click **"Sign in"**.
4. **Check:** you arrive on **Today**, and the bottom of the left menu shows your name and
   **"Workspace admin"**.

Email and password is the **only** sign-in method. "Continue with Google" was removed on
2026-10-24 ([§14.3](#143-security-notes)). **"Create a workspace"** at the bottom of the sign-in
page makes a *separate, empty organization*. The owner and the team should not use it; team
members join by invitation ([§4.2](#42-invite-a-team-member)).

### 3.3 Sessions and sign-out

- A sign-in lasts **7 days**. It is kept in a secure, HTTP-only cookie and works across tabs and
  reloads.
- **Sign out:** the arrow icon at the bottom of the left menu. On a phone, open the menu (☰)
  first.
- After you sign out, that session can never be used again.
- **Lockout:** five wrong passwords lock the account for 15 minutes. Every failure shows the same
  message, *"Invalid email or password"*.

### 3.4 Change your password

- **Settings → Security → Password → "Change password"**: enter your current password, then the
  new one twice. Every other signed-in device is signed out.
- **The owner's** change lasts only until the next deployment or restart, because
  `ADMIN_PASSWORD` resets it.
- To change the owner password permanently:
  1. Set the new value in Railway variable `ADMIN_PASSWORD` (Railway redeploys, about 2–5
     minutes).
  2. Sign in with the new password.
  3. If the old password may have leaked, change it in Settings first, then set Railway to the
     same value.

### 3.5 Recovery

| Situation | What to do |
|---|---|
| Owner forgot the password | Set a new `ADMIN_PASSWORD` in Railway, wait for the deployment, sign in. |
| Owner locked out (5 failures) | Wait 15 minutes, then try once. An early unlock needs a database change by engineering. |
| A team member forgot their password | An admin: **Team & Access → "⋯" → "Reset password"**. A temporary password is shown once. Give it to the member privately. They sign in and must choose their own password before anything else opens. |
| A member is locked out | The same admin reset clears the lockout. |
| "Your access to this workspace has been disabled" | An admin re-enables them: **Team & Access → "⋯" → "Enable access"**. |
| Self-service "forgot password" email | **Not built.** The sign-in page says: *"Forgot it? Your workspace admin can reset it from Team & Access."* |

Full procedures: Owner/Admin Manual §3 and §9.

---

## 4. Roles, workspaces and invitations

### 4.1 Roles

There are exactly two roles in an organization.

| Role | Can do |
|---|---|
| **Admin** ("Workspace admin") | Everything: team and invitations, roles, password resets, disabling access, website forms and server keys, integrations, client portal links, estimates, approvals, webhooks, snapshots, agency accounts, organization settings, the MCP kill switch. |
| **Member** ("Team member") | Daily work: leads, contacts, companies, deals, tasks, calendar, workspaces, notes. A member cannot manage the team, integrations, forms, portal links or organization settings. Trying shows *"You do not have permission to perform this action."* |

**Policy question for the owner** (current behaviour, not a defect):
- A member can download the leads export, which includes contact details.
- A member can read the audit log.

If either should be admin-only, say so and it will be changed.

The last active admin cannot be demoted or disabled.

### 4.2 Invite a team member

1. **Settings → Workspace → "Team and roles"** (page **Team & Access**) → **"Invite"**.
2. Enter **"Their email"**, choose **"What they can do"** (Admin or Member), then **"Create
   invite"**.
3. If email delivery is configured, the invitation is emailed (**"Invitation emailed"**).
   Otherwise the page shows the link with **"Copy"** (**"Invitation ready"**). Send it privately.
4. The person opens the link, chooses **"Create your account"** (name and password) and lands
   in your organization. If they already have a ClientVerse account, they sign in and click
   **"Accept and join"**. **Accepting moves that account into your organization.**
5. Invitations expire after **7 days**. **"Resend"** makes a new link and kills the old one;
   **"Revoke"** cancels it.

### 4.3 Client workspaces and the client portal

- A **client workspace** (menu **Clients**) is a page inside your organization for one client:
  commitments, deliverables, requests, approvals and outcomes. A workspace opens automatically
  when a deal is moved to **Won**, or an admin can create one.
- Clients **do not sign in**. They use a secret **portal link**. To create one:
  1. Go to **Settings → Workspace → "Client portal and playbooks"** (page **Client Operations**).
  2. Pick the workspace, open **"Client portal"**, then click **"Create secure portal link"**.
- The link is **shown once**, in a box with a **"Copy"** button. Send it to the client.
- The client sees that workspace's commitments, approved documents, estimates and invoices, and
  can send a request. They never see another workspace.
- **Revoke** a link under **"Active links"** → **"Revoke"** → **"Revoke link"**. It stops working
  at once.

**"Jasmine":** the project records name no Jasmine workspace or client requirement. "Jasmine
Parker" appears only as sample data in code comments and automated tests. If a real client
called Jasmine needs a workspace, create it as above.

### 4.4 Agency and client accounts

An admin can create separate client *organizations* under the agency:
- **Settings → Agency → "Client accounts"**: up to 200 accounts.
- Open a client account with **"Enter"**. A banner shows whose account you are working in.
- Snapshots copy a setup into up to 100 accounts at once.

Manual §7.24–§7.25.

---

## 5. User and administrator workflows

Every workflow below is a step-by-step procedure in **Part 2, the Owner/Admin Manual**. The
table points to it.

| Workflow | Who | Where in the CRM | Manual |
|---|---|---|---|
| Sign in, sign out, change password | Everyone | `/login`; Settings → Security | §3 |
| Read Today: the day's plan, overdue items, new leads | Everyone | **Today** | §4.2, §7.1 |
| Work a new lead: call, mark responded, close | Everyone | **Leads** | §7.2 |
| Tasks: create, assign, complete | Everyone | **Tasks** | §7.3 |
| Contacts and companies: add, edit, merge duplicates, archive | Everyone | **Contacts** | §7.4 |
| Deals: create, move between stages, win or lose (a win opens a workspace) | Everyone | **Pipeline** | §7.5 |
| Website forms: create, configure assignment and alerts, embed, server key | Admin | **Settings → Website Forms** | §7.6 and [§6](#6-website-and-form-integration) |
| Calendar and online booking pages | Everyone (pages: admin) | **Calendar** | §7.7 |
| Client workspaces: commitments, deliverables, requests, approvals | Everyone | **Clients** | §7.8–§7.9 |
| Client portal links: create, revoke | Admin | **Client Operations** | §7.15 |
| Automations: triggers, steps, waits | Admin | **Automations** | §7.22 |
| Industry templates, snapshots, agency accounts | Admin | Settings | §7.23–§7.25 |
| Invite, change role, reset password, disable access | Admin | **Team & Access** | §8 |
| Connect Google; turn email sending on or off | Admin | **Registries → Integrations** | §5 |
| Export leads to CSV | Everyone | **Leads → "Export CSV"** | §7.20 |
| Verify production health and scheduled jobs | Owner | `/api/health`, `/api/cron/health` | §2.2, §11.4 |
| Production checklist | Owner | — | §14 |

### 5.1 The lead journey at a glance

1. **Lead in:** a visitor submits a website form, or the website's server forwards the lead
   ([§6](#6-website-and-form-integration)).
2. **Filed automatically:**
   - the CRM matches or creates the **contact**;
   - assigns an **owner**;
   - opens or reuses a **deal** in the first pipeline stage;
   - creates a **"Call new lead now"** task, due in 5 minutes;
   - sends the alert.
3. **Work it:**
   - open **Leads**, call or email, and mark the lead **Responded**; completing its task does
     the same;
   - the speed-to-lead clock stops when the lead is marked responded.
4. **Move the deal:** **Pipeline**, drag the card or use its **"⋯"** menu. **Won** opens a
   client workspace.
5. **No response:** if nobody responds within the escalation time (15 minutes by default),
   admins get one escalation alert.

---

## 6. Website and form integration

Full guide: [`docs/WEBSITE_FORMS.md`](../WEBSITE_FORMS.md).

### 6.1 Integration map

| Website type | How it connects | Address |
|---|---|---|
| Any site (copy-paste) | **Embed script**: Website Forms → (form) → **Embed & test** | `<script src="https://crm.clientverse.io/api/public/forms/embed.js" …>` |
| Link only (texts, QR codes, social bios) | **Hosted form page** | `https://crm.clientverse.io/api/public/forms/<form key>/page` |
| Site keeps its own HTML form | Form `action` → submit address, plus the hidden `_hp` field | `POST /api/public/forms/<form key>/submit` |
| **Custom-built site with its own server (recommended)** | **Server key**: **Embed & test → "Create server key"** (shown once). The site's server sends `Authorization: Bearer cvsk_…` | `POST https://crm.clientverse.io/api/intake/leads` |
| Plugins, Zapier, IDX vendors | The submit address with JSON or form data | as above |

A server-key request skips browser-only checks (allowed websites, CAPTCHA). It must still carry
an email or a phone number.

### 6.2 Field mapping

| Website sends | Stored as |
|---|---|
| `name`, `firstName`/`lastName`, `fullname`, `your-name` | Name (and first/last name) |
| `email`, `your-email` | Email (lower-cased, validated) |
| `phone`, `telephone`, `mobile`, `phone_number` | Phone (7–15 digits) |
| `propertyAddress`, `address` | Property address |
| `timeframe` | Timeline |
| `consultationDate`, `consultationTime` | Preferred date and time |
| `leadType`, `goal` | Intent: Buying / Selling / Buying and selling / Renting / Investing. The original wording is kept. |
| `preapproval` | Pre-approved |
| `priceRange`, `budget`, `pricemin`, `pricemax` | Minimum and maximum price ([§6.3](#63-lead-processing-rules)) |
| `message`, `comments`, `your-message` | Message |
| `pageUrl`, `utm_*`, `gclid`, `fbclid`, `referrer` | **Source attribution** (first and latest touch on the contact) |
| `idempotencyKey`, `_sid` | Retry protection: a lead with the same key is filed once |
| Anything else | Kept on the lead under its own name (up to 40 extra answers) |

### 6.3 Lead processing rules

**Which value wins:**
- A field's own name beats an alias: `phone` beats `mobile`, `property_address` beats
  `address`, `price_max` beats `budget`.
- A top-level value beats the same field inside `payload`.
- The losing value is kept on the lead, never dropped.

**Budgets:**
- `$400k–$500k` is stored as minimum 400,000 and maximum 500,000.
- **`$500,000+`, "or more", "and up" or "over" is stored as a minimum only.**
- "Under", "up to" or "or less" is stored as a maximum only.
- A single figure is stored as the maximum.
- Text that is not a budget (for example "Not sure") is kept as text with no price.
- `budget: "lots"` is refused with an "Enter a number" message.

**Repeats:**

| What arrives | What happens |
|---|---|
| Same idempotency key again | One enquiry, however long after |
| Same answers within 10 minutes | Collapsed into the first enquiry (a double-click) |
| Changed answers: time, intent, budget, pre-approval, any custom answer, consent | A **new enquiry** on the **same contact** and **same open deal** (see below) |

When a changed answer arrives:
- The contact takes the new answers. A new budget replaces both bounds.
- The deal is re-priced from the new budget only if nobody has typed a value on it.

**Isolation:** forms, keys, duplicates and records are per organization. Another organization
can never see or match them.

### 6.4 Alerts

The form's **Automation → Speed to lead** section has **"In-app alert"** and **"Email alert"**
switches. Each controls its own channel. Email alerts need email delivery configured
([§7.3](#73-email-notifications-transactional)). The no-response escalation is always sent.

---

## 7. Integrations: setup and operation

### 7.1 Google: Gmail and Google Calendar

| Item | State |
|---|---|
| OAuth client | Set in Railway (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`). The boot log shows `Registered outbound channel provider: gmail`. |
| Redirect address | `https://crm.clientverse.io/api/integrations/google/callback` (Railway `GOOGLE_REDIRECT_URI`). It must match the OAuth client in Google Cloud. |
| Permissions requested | `gmail.readonly`, `gmail.send`, `calendar.readonly`, plus the account email |
| Last connection | The owner reconnected on **2026-10-19 02:02 UTC**; Google granted all three permissions (Railway log). |
| Current row state | Visible only to an admin: **Registries → Integrations → Gmail**. **Owner check.** |
| Weekly lapse | While the Google consent screen is in **Testing**, Google ends the permission after 7 days. Reconnect, or publish the consent screen. |

**Connect or reconnect:**
1. Go to **Registries → Integrations → Gmail → "Connect"** (or **"Re-authorize"**).
2. Approve **every** permission box.
3. **Check:** the row reads **"Connected"**.

Manual §5.

### 7.2 Gmail outbound email, consent and reply capture

- **Sending is off until an admin turns it on:** on the Gmail row, click **"Send test & turn
  on"**. That sends one test email to the connected mailbox, then turns sending on.
  **"Turn off"** reverses it.
- **What can send today:**
  - Calendar booking emails;
  - an approved website-form auto-reply.

  Every message needs a human approval of the exact words. Each is recorded with its consent
  basis.
- **No screen yet for writing a one-off email** to a contact, or for recording consent by hand
  (API only). This is a known limitation, governing document §8 #27.
- **Failed sends:** a send whose outcome is unknown is never resent blindly. The
  `reconcile-unknown` job asks Gmail whether it went (every 30 minutes, at :10 and :40).
- **Reply capture:** the `inbound-email` job pulls replies and bounces into the matching
  conversation (at :10 and :40). Unmatched mail is listed for review. It has **never been
  certified live**: run Manual §6 Procedures A–C once sending is on.

### 7.3 Email notifications (transactional)

Invitations, new-lead email alerts and the daily digest use a separate email service.
- It is configured by the Railway variable **`EMERGENT_EMAIL_KEY`**. It was **not set** when last
  recorded.
- **Settings** shows whether it is configured, in the **"Email delivery"** row.
- Without it:
  - invitations show a link to copy;
  - in-app alerts still work.

### 7.4 Scheduling and online booking

**Calendar** holds appointments and **booking pages**.
- An admin creates pages with **"Create my booking pages"** or one at a time.
- Each page has a public link `/book/<key>`, which can be embedded on a website.
- The `booking-reminders` job sends reminders exactly once.
- Booking confirmation emails need Gmail sending on. Until then the Calendar shows *"Not emailed
  — Email isn't connected"*.

Manual §7.7.

### 7.5 Billing and payments (Stripe)

**Not configured.**
- `STRIPE_API_KEY` and `STRIPE_WEBHOOK_SECRET` are not set. **"Connect"** on the Stripe row
  answers *"Stripe is not configured (STRIPE_API_KEY)."*
- Estimates and invoices are kept as records only.
- The screens say *"Stripe payment collection stays disabled"*.
- **No charges can occur.**

To enable Stripe:
1. Decide whether Stripe is in scope.
2. Create a test-mode restricted key.
3. Create a webhook to `https://crm.clientverse.io/api/integrations/stripe/webhook`.
4. Set both variables in Railway.
5. Certify per [`docs/STRIPE_PROVIDER_CERTIFICATION.md`](../STRIPE_PROVIDER_CERTIFICATION.md).

### 7.6 Other integrations

| Integration | State |
|---|---|
| Outbound webhooks (for example `lead.received` to Zapier or Slack) | Available: **Registries → Webhooks** (admin). Signed and retried. |
| AI generation | **Off.** It needs `EMERGENT_LLM_KEY` **and** the `emergentintegrations` package, which the Docker image does not install. Without both, AI requests fail with an error and no fake output. |
| SMS, calling, Slack, ClickUp, n8n | Not implemented. Their screens say so. |
| MCP console (governed AI tools) | Available. The admin kill switch stops every tool at once. |

---

## 8. Architecture, services, data and scheduled jobs

### 8.1 Services

| Part | What it is |
|---|---|
| **Web application** | One Railway service: a Python FastAPI API (`backend/`) that also serves the React screens (`frontend/`) from the same address |
| **Background work** | Inside the same process, no separate worker: the scheduler (13 jobs, coordinated through MongoDB leases), the lead speed-to-lead watcher (every 60 s) and the automation watcher (every 30 s). The durable work queue is a MongoDB collection. |
| **Database** | MongoDB Atlas, about 60 collections. Every record carries its organization (`tenant_id`); every query is scoped to it. |
| **File storage** | **None.** The CRM stores no uploaded files. Documents are links; exports are generated on request. |
| **External calls** | Google (OAuth, Gmail, Calendar); the Emergent email API (only if `EMERGENT_EMAIL_KEY` is set); Stripe (only if configured); webhooks the organization sets up |

### 8.2 Main data collections

| Area | Collections |
|---|---|
| Identity and access | `tenants`, `users`, `memberships`, `invitations`, `login_lockouts`, `revoked_tokens` |
| CRM records | `contacts`, `companies`, `opportunities`, `pipelines`, `tasks`, `crm_activities`, `notes`, custom fields and saved views |
| Website intake | `website_forms`, `web_enquiries` (the leads), `form_submission_attempts` |
| Clients | `workspaces`, `commitments`, `deliverables`, `client_requests`, `portal_links`, `estimates`, `invoices` |
| Messaging | `conversations`, `communication_messages`, `inbound_unmatched`, `approvals`, `notifications`, `notification_deliveries` |
| Integrations | `integrations`, `integration_connections`, `google_credentials` (encrypted with `INTEGRATION_ENC_KEY`), `oauth_states` |
| Scheduling and jobs | `appointments`, `booking_*`, `work_queue`, `cron_run_log`, `scheduler_leases` |
| Audit | `domain_events` (Audit page), `automation_runs` |

### 8.3 Health signals

- **`GET /api/health`** (no sign-in) returns
  `{"service":"ClientVerse","version":"v1","status":"ok","database":"up","git_sha":"<commit>"}`.
  If the database does not answer, it returns `503` with `"database":"down"`. Railway uses it as
  the deployment health check.
- **`GET /api/cron/health`** (owner organization admin, or the scheduler secret) reports
  `scheduled_jobs_running`, the last runs, the last failure and the last rejected call.

### 8.4 Scheduled jobs

Two drivers run the same jobs. Each run is recorded once in the ledger `cron_run_log`, whichever
driver ran it:
1. **In the application** (always on).
2. **The GitHub Actions workflow "Scheduled jobs"** (every 5 minutes). It reads the ledger back
   and fails if production did not record the call.

| Job | When (UTC) | What it does | Where to see the result |
|---|---|---|---|
| `commitment-risk` | every 15 min | Flags client commitments at risk or breached | Action Center, client workspace |
| `work-queue` | every 5 min | Runs due queue items, recovers stuck ones | `/api/cron/health` |
| `recovery-runner` | every 5 min | Queues approved recovery cases; drafts only, never sends without approval | Operations |
| `booking-reminders` | every 5 min | Booking reminders (exactly once); sends approved booking emails | Calendar |
| `integration-sync` | :00, :30 | Gmail, Calendar and Stripe sync for connected organizations | Registries rows, client Activity |
| `next-best-actions` | :00, :30 | Recomputes recommendations | Today |
| `inbound-email` | :10, :40 | Pulls replies and bounces | Conversations, unmatched inbound |
| `reconcile-unknown` | :10, :40 | Asks Gmail about sends with an unknown outcome; never resends | Message status |
| `daily-digest` | hourly at :05 | Digest at each organization's local hour (email needs the email key) | Inbox / email |
| `second-chance` | hourly at :05 | Finds stalled leads and missed follow-ups | Operations |
| `detect-recovery` | hourly at :05 | Other recovery detectors | Operations |
| `recovery-strategies` | hourly at :05 | Proposes strategies; raises approvals | Approvals |
| `approval-expiry` | hourly at :05 | Lapses undecided approvals | Approvals |
| `lead-sla` | every 60 s (in the app) and every 5 min (workflow) | Escalates unanswered website leads | Notifications, lead's clock |

**Observed 2026-10-24:**
- Scheduled-jobs workflow runs #10214–#10218 (20:13–20:28 UTC) succeeded.
- Each call answered `HTTP 200 accepted=true`, and production recorded the run in its ledger
  (for example *"production recorded 2 reference(s) for 40129902019-1"*).

---

## 9. Configuration variables

Values are never written down. Names, purpose and where each is managed:

### 9.1 Railway: service `clientverse-crm-production` → Variables

| Variable | Purpose | Required |
|---|---|---|
| `MONGO_URL` | Atlas connection string | Yes |
| `DB_NAME` | Database name | Yes |
| `JWT_SECRET` | Signs sign-in sessions (at least 32 characters) | Yes |
| `INTEGRATION_ENC_KEY` | Encrypts stored Google and Stripe tokens. **Changing it breaks saved connections.** | Yes |
| `WEBHOOK_CRON_SECRET` | Secret the scheduler must present; same value as the GitHub secret | Yes |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Owner account and password ([§3.1](#31-the-owner-account)) | Yes |
| `APP_ENV` | `production` turns on strict start-up checks (the image's default) | Default |
| `FRONTEND_URL` | Public address used in links and cookies: `https://crm.clientverse.io` | Yes |
| `CORS_ORIGINS` | Browser origins allowed: the custom domain and the Railway address | Yes |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | Google connection | For Google |
| `STRIPE_API_KEY` / `STRIPE_WEBHOOK_SECRET` | Stripe | Not set |
| `EMERGENT_EMAIL_KEY` / `EMAIL_FROM_NAME` | Notification and invitation emails | Not set (last recorded) |
| `EMERGENT_LLM_KEY` | AI generation (also needs a package; see [§7.6](#76-other-integrations)) | Not set |
| `SEED_DEMO_DATA` | Must stay `false` in production | Default false |
| `IN_PROCESS_SCHEDULER`, `LEAD_SLA_WATCHER`, `AUTOMATION_WATCHER` | Background loops. Leave unset (on). | Default on |
| `LOGIN_LOCKOUT_THRESHOLD` / `LOGIN_LOCKOUT_MINUTES` | Lockout policy (5 / 15) | Default |
| `FORM_*`, `BOOKING_RATE_*`, `RECOVERY_*`, `WORK_QUEUE_*`, `SECOND_CHANCE_*` | Tuning knobs; the code defaults are in use | Optional |
| `Mongo_url` | **Unused misspelled duplicate. Delete it.** | — |

Railway itself supplies `PORT`, `RAILWAY_PUBLIC_DOMAIN` and `RAILWAY_GIT_COMMIT_SHA`. The last
one becomes `git_sha` in `/api/health`.

### 9.2 GitHub: repository → Settings → Secrets and variables → Actions

| Secret | Used by | State |
|---|---|---|
| `CLIENTVERSE_PRODUCTION_URL` | Scheduled jobs | Set, but it points at the **Vercel** copy (`*.vercel.app`), not `https://crm.clientverse.io`. **Owner action 11.** Production acceptance does not use it; it tests `https://crm.clientverse.io`. |
| `WEBHOOK_CRON_SECRET` | Scheduled jobs (same value as Railway) | Set |
| `CLIENTVERSE_OWNER_EMAIL` / `CLIENTVERSE_OWNER_PASSWORD` | Optional read-only owner check in Production acceptance | **Not set: owner action** |

### 9.3 Agent tooling (not the CRM)

`JEV_QC_WEBHOOK_URL` and `JEV_QC_WEBHOOK_TOKEN` (Claude Code environment) configure the Jev QC
verification gate. They were **not present** in this closeout session.

---

## 10. Deployment, rollback, backup and restore

### 10.1 Deploy

1. Changes reach `main` through a pull request. CI must pass: frontend lint and build, backend
   lint and types, the backend tests on MongoDB 7, and the 82-step release smoke.
2. Merging starts a Railway deployment automatically. Railway builds the Dockerfile (about 2–3
   minutes), starts it and waits for `/api/health` to answer.
3. **Check:**
   - Railway → Deployments shows the newest deployment as **SUCCESS**;
   - https://crm.clientverse.io/api/health shows the new `git_sha`;
   - the boot log shows `Application startup complete`.
4. **Then run Actions → "Production acceptance" → "Run workflow".**

### 10.2 Roll back

The fastest way back is Railway's own rollback:

1. **Railway → Deployments**: pick the last good **SUCCESS** deployment.
2. Open its **"⋮"** menu and choose **"Rollback"**. Railway runs that exact build again.
3. Check `/api/health` → `git_sha` shows the older commit. Then run **Production acceptance** with
   **`expected_sha`** set to that older commit. Left blank, it waits for the newest `main` commit
   and fails.
4. Revert the bad change on GitHub too (**"Revert"** on its pull request), or the next merge
   brings it back.

**Database note:** a rollback changes the code, not the data. No release in this closeout
changed the data format, so the database works with the earlier code. A rollback is not a
substitute for a database restore.

**Security note:** a rollback to a commit before `6d0d4c6` (for example `394f095`) **brings back
the two security exposures this release closed**: the prototype "Continue with Google" sign-in
and the job ledger readable by any organization's admin. Use such a rollback only as a
short emergency measure. Ask engineering for a fix on top of `main` (or a revert of only the
faulty change) that keeps those fixes, and move to it as soon as possible.

**Tested?**
- Railway redeploys are routine (every merge).
- A deliberate rollback has **not** been exercised in production.

### 10.3 Backup

- **Atlas:** whether continuous backup or snapshots are on, and the cluster tier, are
  **unverified**. The records conflict: one says an M10 cluster, others suggest a shared tier,
  which has no continuous backup. **Owner action:** Atlas → cluster → **Backup** → confirm it is
  on, and record the tier and the retention period.
- **On-demand logical backup** (anyone with the connection string, from a trusted machine):
  ```
  mongodump --uri "<MONGO_URL value>" --db "<DB_NAME value>" --archive=clientverse-YYYYMMDD.archive.gz --gzip
  ```
  Keep the file encrypted and off shared drives: it contains every customer record and the
  password hashes.
- **Leads only, from the screen:** **Leads → "Export CSV"**.
- **Setup only (no customer data):** **Settings → Snapshots → "Download file"**.

### 10.4 Restore (tested procedure)

Restore into a **new** database first, never over production:

1. `mongorestore --uri "<MONGO_URL value>" --archive=clientverse-YYYYMMDD.archive.gz --gzip --nsFrom "<DB_NAME>.*" --nsTo "<DB_NAME>_restore.*"`
2. Check it **without letting it act**. The restored database holds real contacts, pending work
   and encrypted Google tokens, and a running copy of the CRM would act on them:
   - run the check locally (or in a throwaway service), never as a second copy beside
     production;
   - set `IN_PROCESS_SCHEDULER=0`, `LEAD_SLA_WATCHER=0` and `AUTOMATION_WATCHER=0`, so no
     scheduled job, escalation or automation runs;
   - leave `EMERGENT_EMAIL_KEY`, `STRIPE_*` and `GOOGLE_*` unset, and use a **new**
     `INTEGRATION_ENC_KEY`, so stored provider tokens cannot be used and nothing can be sent;
   - give it no `WEBHOOK_CRON_SECRET` the scheduler knows, so no external cron traffic reaches it;
   - point it at `DB_NAME=<DB_NAME>_restore`, confirm `/api/health` shows `"database":"up"`,
     sign in, and open a known lead, deal and contact;
   - **stop it** before going further.
3. To make the restore live:
   - set Railway `DB_NAME` to the restored database (Railway redeploys);
   - run **Production acceptance**;
   - keep the old database until you are sure.

**Tested:** the **Backup and restore drill** workflow (`.github/workflows/backup-restore-drill.yml`,
monthly and on demand) does this end to end on a throwaway MongoDB 7:
1. It creates records through the real application.
2. It backs up with `mongodump`, drops the whole database, then restores with `mongorestore`.
3. It restarts the application and confirms:
   - the same password still signs in;
   - the lead, deal (stage and value), contact and completed task are back;
   - the website server key and the duplicate-protection index still work.

The result is in [§13.2](#132-repository-and-local-verification). It proves the procedure and
the tools, not Atlas's own backups.

---

## 11. Monitoring, logs, diagnosis, support and maintenance

### 11.1 What to watch

| Signal | Where | Healthy |
|---|---|---|
| Service up | https://crm.clientverse.io/api/health | `status ok`, `database up` |
| Deployment | Railway → Deployments | Newest **SUCCESS**; no crash loop |
| Jobs | `/api/cron/health` (signed in as the owner) | `scheduled_jobs_running: true`, no recent `last_failed_job` |
| Scheduler workflow | GitHub → Actions → Scheduled jobs | Green runs every few minutes |
| CI | GitHub → Actions → CI | Green on `main` |
| Monthly restore drill | GitHub → Actions → Backup and restore drill | Green |
| In-app problems | **Action Center** (the bell) | Nothing unexpected under **"Needs action"** |

### 11.2 Logs

- **Railway → service → Deployments → (deployment) → Logs**. Useful lines:
  - start-up: `Application startup complete`, `In-process scheduler started for 13 job(s)`,
    `Registered outbound channel provider: gmail`;
  - failures: `In-process job '<job>' failed for window …`, `Lead automation failed for …`.
- **GitHub Actions** run logs for the scheduler, CI, acceptance and the drill.
- **Audit** page (in the CRM): who did what, when.

### 11.3 Failure diagnosis

| Symptom | Likely cause | First step |
|---|---|---|
| Site does not load | Deployment failed or restarting | Railway → Deployments → logs. Restart the last SUCCESS deployment once. |
| `/api/health` says `database: down` (503) | Atlas unreachable or paused, or `MONGO_URL` wrong | Atlas status and network access; Railway `MONGO_URL` |
| Everyone signed out after a deploy | `JWT_SECRET` changed | Expected after a rotation; sign in again |
| Google rows show errors | Permission lapsed (Testing mode) or the redirect address mismatched | Reconnect (Manual §5.6); check `GOOGLE_REDIRECT_URI` matches Google Cloud |
| Scheduler workflow red with `401` | `WEBHOOK_CRON_SECRET` differs between GitHub and Railway | Set both to the same value (Manual §11.8) |
| Leads not arriving from a site | Wrong or revoked server key (`401`), paused form, the site sends neither email nor phone (`422`) | Website Forms → the form's status and key; the site's logs |
| Duplicate leads | The site sends a new idempotency key *and* changed answers (by design, a new enquiry) | Check the two enquiries' differing fields |

More: Manual §12 (troubleshooting matrix) and §15 (escalation, with a report template).

### 11.4 Routine maintenance

| How often | Task |
|---|---|
| Weekly while Google is in Testing | Reconnect Google, or publish the consent screen to stop the 7-day lapse |
| Monthly | Check that the **Backup and restore drill** is green; read Atlas backup status; review **Team & Access** for leavers; review active portal links |
| After every release | Run **Production acceptance** |
| Quarterly | Rotate `ADMIN_PASSWORD` (Railway); review provider costs; review Railway and Atlas access lists |
| On a leaver | **Disable access** for them; revoke any portal links they shared |

---

## 12. Ongoing service costs

**No cost figure is recorded anywhere in the project.** This closeout session could not reach
any provider's billing page. Nothing below is a verified amount.

| Service | What is known | Where the owner reads the actual cost |
|---|---|---|
| Railway (hosting) | One service, one replica, region `sfo` | railway.com → workspace → **Usage / Billing** |
| MongoDB Atlas (database) | Cluster `clientverse-production`; tier unverified (M10 vs shared) | cloud.mongodb.com → Organization → **Billing** |
| Domain `clientverse.io` | `crm` CNAME exists | The registrar's billing page |
| GitHub (CI, scheduler, checks) | Actions minutes used every 5 minutes by the scheduler workflow | github.com → Settings → **Billing and plans** |
| Google Cloud (OAuth) | OAuth client only; normally no charge | console.cloud.google.com → **Billing** |
| Cloudflare | A Worker exists (not used by the CRM) | dash.cloudflare.com → **Billing** |
| Stripe | Not configured; no fees | — |
| Emergent (email / AI) | Keys not set | — |
| n8n (Jev QC gate, agent tooling only) | Host `bwa357.app.n8n.cloud` | n8n account billing |

**Owner action:** record the monthly amounts in this table at the next revision.

---

## 13. Tests performed and production acceptance results

### 13.1 What was tested

| # | Test | Scope |
|---|---|---|
| T1 | Backend unit and API suite | 1,000+ tests. CI runs them against MongoDB 7 with a live API; this session also ran them on mongomock. Includes 124 website-form tests. |
| T2 | Release smoke (`scripts/crm_release_smoke.mjs`) | 82 assertions: an admin's week. Invite a colleague, records, pipeline, tasks, cross-organization isolation, scheduler health. |
| T3 | Proof of life (`scripts/proof_of_life.mjs`) | Records persist; another organization gets 404 |
| T4 | Full CRM journey in a real browser (local full stack) | Sign-in/out, wrong password, lockout, change password, invite and accept, member limits, admin reset, client workspace and portal isolation, forms, server key, hosted form at phone width, `$500,000+`, duplicates, changed lead, leads after reload, pipeline drag and menu, tasks, Today, booking (public page at phone width), billing and integration states, CSV export, snapshot download, 33 routes × 3 widths for overflow, console errors, dead controls, keyboard focus, dark mode, axe accessibility scan |
| T5 | Production acceptance (API): `scripts/production_acceptance.mjs` | 40 checks: health and revision, the lead journey end to end, isolation, sign-out |
| T6 | Production browser pass: `scripts/production_browser.mjs` | Sign-in page, sign-in, 11 main pages × 4 widths, lead listed and persisted, sign-out from the menu |
| T7 | Backup and restore drill | `mongodump` → drop → `mongorestore` → verify through the application |

### 13.2 Repository and local verification

| Check | Revision | Result |
|---|---|---|
| CI: frontend lint (`--max-warnings=0`) and production build | PR #48 head `02b8d78` | **Pass** |
| CI: backend `ruff`, type ratchet, `pip-audit`, config validation | `02b8d78` | **Pass** |
| CI: backend API suite on MongoDB 7 with a live API, then the 82-step release smoke | `02b8d78` (and every earlier PR #48 commit) | **Pass** |
| Website-form tests: 132, of which 37 are new. Before each fix, 21 and then 6 of the new tests were shown to fail on the code. | `02b8d78` | **132 passed** |
| Security tests: retired Google sign-in (`410`, creates nothing); job ledger refused to a self-registered admin | `02b8d78` | **Pass** |
| Local full stack, real API and built screens on one address (mongomock): release smoke | `588bcea` | **82/82** |
| Local full stack: `proof_of_life.mjs` (persistence, cross-organization 404) | `588bcea` | **Pass** |
| Local browser journey: 33 routes × 3 widths; roles; invitation; reset; portal isolation; forms; pipeline; booking; export; dark mode; keyboard focus | `588bcea` | **Pass.** It found the defects fixed in PR #48 (portal link, revoke, copy feedback, contrast, MCP switch). An axe scan left two minor items ([§14.2](#142-known-product-limitations-current-code)). |
| Local `production_acceptance.mjs` / `production_browser.mjs` | `7bca2c7` | **39/39 · 76/76** |
| **Backup and restore drill** (GitHub, MongoDB 7): create → `mongodump` → drop → `mongorestore` → verify | `7954a8f`, run #2 | **Pass.** Same password signs in. Lead fields, deal stage and value, contact and completed task restored. Server key and duplicate protection work. Run #1 failed in its dump step: the tool ran outside the database container. The drill now runs inside it. |
| Copilot review of PR #48: 4 findings on the intake code | — | All 4 reproduced, fixed in `d7d7645` with tests, and resolved |

### 13.3 Production acceptance results

**Run:** GitHub Actions → *Production acceptance*, run `40134314474`, 2026-10-24 21:27–21:31 UTC, against
**https://crm.clientverse.io**. Production reported `git_sha` **`6d0d4c627518acbd12038ff2a4eade95df2e1e1a`**, the merge of
PR #48, which is the expected revision.

**API journey: 40 of 40 passed.**

| # | Check | # | Check |
|---|---|---|---|
| 01 | API healthy with the database up | 21 | Signed back in |
| 02 | Production runs the expected revision | 22 | Lead visible in the inbox after a fresh sign-in |
| 03 | Sign-in page is served | 23 | Same answers again collapse as a duplicate |
| 04 | Website embed script is served | 24 | Same idempotency key is not filed twice |
| 05 | Retired third-party Google sign-in is refused | 25 | Changed time and budget filed as a new enquiry |
| 06 | Test organization A registered | 26 | Same person: same contact and same open deal |
| 07 | Email alerts off for the test admin | 27 | **$500,000+ is a minimum, not a ceiling** |
| 08 | Website form created | 28 | Changed consultation time kept |
| 09 | Server key minted for the website | 29 | Contact budget replaced, no stale ceiling |
| 10 | Website lead accepted | 30 | An alias never replaces the field itself |
| 11 | Lead filed in the right organization and form | 31 | Test organization B registered |
| 12 | Contact fields mapped | 32 | Another organization cannot read the lead, deal or contact |
| 13 | Intent, timing and qualification mapped | 33 | An unknown server key is refused |
| 14 | Budget range mapped to both bounds | 34 | Deal moved to Qualified |
| 15 | Source attribution recorded | 35 | Follow-up task completed |
| 16 | Assigned, with a contact, a deal and a follow-up task | 36 | Lead marked responded; its clock stopped |
| 17 | Deal priced from the budget (2.5% of $500,000) | 37 | Leads export contains the lead |
| 18 | Signed out | 38 | Today plan answers |
| 19 | The signed-out session no longer works | 39 | A self-registered admin cannot read the platform job ledger |
| 20 | A wrong password is refused | 40 | Test records closed and archived |

**Browser pass: 76 of 76 passed.** Real Chromium was used at phone (390 px), tablet (768), laptop
(1024) and desktop (1440) widths. At each width it checked:
- the sign-in page has no third-party button and shows keyboard focus;
- sign-in works through the form;
- **Today, Leads, Pipeline, Contacts, Tasks, Clients, Website Forms, Calendar, Notifications,
  Team and Settings** render with no sideways scroll, no crash and no page error;
- the test lead is listed, and still listed after a reload;
- the menu's **Sign out** button works, and `/dashboard` then sends the visitor to sign in.

**Scheduled jobs:** the *Scheduled jobs* workflow ran green throughout the day. Each call answered
`HTTP 200 accepted=true`, and production recorded each run in its ledger.

**Found during acceptance, not a defect in the CRM:**
- A Vercel project (`clientverse-crm` in the `tradeiq` team) builds a **second copy of the screens** at
  `clientverse-crm.vercel.app` on every push. Its build sends API calls straight to the Railway
  address, so **sign-in on that Vercel copy fails** (blocked by the browser's cross-origin rules).
- The GitHub secret **`CLIENTVERSE_PRODUCTION_URL` points at that Vercel address**, so the
  scheduler's calls currently pass through Vercel's `/api` forwarding.
- Production at `crm.clientverse.io` is unaffected (above).

Owner actions 11 and 12 in [§14.1](#141-owner-actions-exact) resolve both.

**Not verified, by design:**
- **The owner's own sign-in.** No owner credential is available to engineering. See owner action 1.
- **Live outbound email and reply capture.** Sending is off until an admin turns it on (owner
  action 2).
- **Stripe.** Not configured.

**Evidence:**
- GitHub Actions run `40134314474`, with artifact `production-acceptance-40134314474`: JSON results
  and 48 screenshots.
- *Backup and restore drill* run 2.
- PR #48 checks.
- The test organizations ("ClientVerse Acceptance Test A/B/Browser", `acceptance+…@example.com`)
  remain in production with their leads closed and their records archived.

---

## 14. Remaining limitations and exact owner actions

### 14.1 Owner actions (exact)

| # | Action | Where | Why |
|---|---|---|---|
| 1 | **Confirm owner access.** Either (a) add the repository secrets `CLIENTVERSE_OWNER_EMAIL` and `CLIENTVERSE_OWNER_PASSWORD` (the `ADMIN_EMAIL` / `ADMIN_PASSWORD` values), then run **Actions → Production acceptance** with **"owner_check"** ticked; or (b) sign in at https://crm.clientverse.io/login and tick Manual §14 rows 3–5. | GitHub → Settings → Secrets → Actions | No owner credential is available to engineering, by design. The check is read-only. |
| 2 | **Gmail:** open **Registries → Integrations → Gmail** and confirm **"Connected"**. Then decide whether to **"Send test & turn on"**. Then run Manual §6 Procedures A–C (send, duplicate protection, reply capture). | CRM (owner) | Only an admin session can see or turn on sending. Reply capture has never been certified live. |
| 3 | **Atlas backups:** confirm backup is on; record the cluster tier and retention. Optionally narrow network access from `0.0.0.0/0`. | cloud.mongodb.com | Largest open data risk |
| 4 | **Stripe:** decide whether it is in scope. If yes, follow [§7.5](#75-billing-and-payments-stripe). | Stripe, Railway | Not configured |
| 5 | **Email notifications:** set `EMERGENT_EMAIL_KEY`, or accept link-only invitations and in-app alerts | Railway | Not set |
| 6 | **Rotate `ADMIN_PASSWORD`** (open item O-04); **delete `Mongo_url`**; rotate the legacy Stripe webhook secret that is in git history (O-05) | Railway, Stripe | Hygiene |
| 7 | **Record costs** in [§12](#12-ongoing-service-costs) | Provider billing pages | No verified figures exist |
| 8 | **Policy:** should members be able to export leads and read the audit log? ([§4.1](#41-roles)) | Reply in Issue #10 | Current behaviour allows both |
| 9 | **Cloudflare Worker `clientverse-crm`:** delete it, or tell engineering what it is for | dash.cloudflare.com | Fails on every push; unused |
| 10 | **Jev QC gate:** set `JEV_QC_WEBHOOK_URL` / `JEV_QC_WEBHOOK_TOKEN` in the Claude Code environment, and allow its host in the session network policy | Claude Code environment settings | Required by the repository's completion rule; absent in this session |
| 11 | **Point the scheduler at production:** set the GitHub secret `CLIENTVERSE_PRODUCTION_URL` to `https://crm.clientverse.io` (no trailing slash). Then confirm the next *Scheduled jobs* run is green, and that *Production acceptance*'s first step says *"Scheduler secret -> the custom domain"*. | GitHub → Settings → Secrets and variables → Actions | It points at the Vercel copy today. If that project changes or is deleted, the external scheduler stops (the in-app scheduler keeps running). |
| 12 | **Vercel project `clientverse-crm`:** after item 11, delete the project (recommended), or remove its `REACT_APP_BACKEND_URL` variable so its copy uses its `/api` forwarding | vercel.com → team `tradeiq` → project → Settings | It publishes a second, non-working sign-in page at `clientverse-crm.vercel.app` on every push |

### 14.2 Known product limitations (current code)

- No self-service "forgot password" email. No two-factor sign-in or single sign-on.
- No screen to write a one-off email to a contact, or to record email consent by hand (API only).
  Outbound email has never been certified live.
- Screens cannot edit or archive companies (API only). There is no CSV import screen. The only
  export screen is for leads (the API exports other records).
- Stripe, SMS, calling, AI generation and the Slack, ClickUp and n8n integrations are not
  active. Their screens say so; none pretends to work.
- A changed resubmission adds a second **"Call new lead now"** task for the same person (each
  request gets its own follow-up).
- One environment only: there is no staging.
- Minor accessibility items from the scan:
  - the Audit table's scroll area is not reachable by keyboard alone;
  - one skipped heading level on Companies.

### 14.3 Security notes

- **Removed "Continue with Google" sign-in (2026-10-24).** It trusted
  `demobackend.emergentagent.com`, a third party's demo service, to say who a visitor was. It
  then signed them in as the matching user, the owner included, or created a new organization
  with them as admin.
- Sessions it issued earlier expire within 7 days and follow the normal password rules.
- The job ledger is now readable only by the owner's organization.
- Anyone can register a new, empty organization from the sign-in page (self-signup). It gives no
  access to anyone else's data; cross-organization isolation is tested on every release.
- `ADMIN_PASSWORD` has no enforced length: choose a long one.

---

## 15. Final operational checklist

Tick each item, write the date, and keep this page with the closeout record.

**Production is healthy**

- [ ] https://crm.clientverse.io/login shows **"Sign in to ClientVerse"**
- [ ] https://crm.clientverse.io/api/health shows `"status":"ok"`, `"database":"up"` and the
      released `git_sha` ([§13.3](#133-production-acceptance-results))
- [ ] Railway → Deployments: newest deployment **SUCCESS**
- [ ] GitHub → Actions: **CI** green on `main`; **Scheduled jobs** green in the last hour;
      **Production acceptance** green for this release; **Backup and restore drill** green

**Owner access** ([§3](#3-owner-sign-in-account-setup-administration-and-recovery))

- [ ] The owner signs in with email and password and sees **"Workspace admin"**
- [ ] The owner signs out; opening `/dashboard` returns to the sign-in page
- [ ] `/api/cron/health`, signed in as the owner, shows `"scheduled_jobs_running": true`
- [ ] `ADMIN_PASSWORD` rotated in Railway (O-04) and stored in the owner's password manager

**Team and clients** ([§4](#4-roles-workspaces-and-invitations))

- [ ] Every real team member has an account from an invitation; leavers are disabled
- [ ] Client portal links in use are listed under **Active links**; unknown links are revoked

**Lead intake** ([§6](#6-website-and-form-integration))

- [ ] Each live website form is **Live**, with its allowed websites set (embed) or a server
      key in the website's environment (server connection)
- [ ] One real test lead from each website reached **Leads** with its fields and source, then
      was marked responded and closed

**Integrations** ([§7](#7-integrations-setup-and-operation))

- [ ] Gmail row **"Connected"** (or a decision recorded not to use Gmail)
- [ ] Email sending decision recorded (on with **"Send test & turn on"**, or off)
- [ ] Stripe decision recorded (in scope or not)
- [ ] Email notifications decision recorded (`EMERGENT_EMAIL_KEY` set, or link-only)

**Data safety** ([§10](#10-deployment-rollback-backup-and-restore))

- [ ] Atlas backup confirmed on; tier and retention recorded
- [ ] Unused `Mongo_url` variable deleted from Railway
- [ ] Monthly restore drill reviewed

**Costs** ([§12](#12-ongoing-service-costs))

- [ ] Monthly amounts recorded for Railway, Atlas, the domain and GitHub


---

## 16. Closeout record

| Item | Record |
|---|---|
| Closeout date | 2026-10-24 |
| Released revision | `main@6d0d4c6`: merge of PR #48, which carries PR #47 |
| Production address | https://crm.clientverse.io (Railway service `clientverse-crm-production`) |
| Production verification | Production acceptance run `40134314474`: API 40/40, browser 76/76, revision match ([§13.3](#133-production-acceptance-results)) |
| Restore procedure | Tested: Backup and restore drill, pass ([§10.4](#104-restore-tested-procedure)) |
| Pull requests | #48 merged; #47 merged through #48; #36 closed as superseded (its fixes were already on `main`) |
| Defects fixed in this closeout | 17. Intake: alias overwrite, refused list budgets, open-ended budgets, inverted ranges, nested precedence, stale contact ceiling, re-pricing race and currency. Security: third-party sign-in, ledger exposure. UI: alert switch ignored, clipped table actions, lost portal link and no revoke, false "copied", contrast, member MCP switch. |
| Documentation | This handoff (Part 1); Owner/Admin Manual v1.13 (Part 2); the generated Word and Markdown package; `WEBSITE_FORMS.md`; `RAILWAY_RUNBOOK.md`; governing document v1.27; `AGENTS.md` |
| Jev QC gate | **Not run.** Its variables were absent from this session ([§14.1](#141-owner-actions-exact) item 10). The repository rule therefore forbids recording this work as Jev `VERIFIED_COMPLETE`. The verification above is the GitHub evidence listed. |
| Open owner items | [§14.1](#141-owner-actions-exact). Owner sign-in confirmation, Gmail sending, Atlas backups, the scheduler secret and the Vercel copy matter most. |
| Status | **Released and verified in production for the lead journey and the screens.** The items in §14.1 remain the owner's to close. |
