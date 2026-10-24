# ClientVerse CRM — Production Closeout Package

This package is the complete owner and operator documentation for ClientVerse CRM. **Part 1** is the closeout handoff: what was delivered and verified, the production environment, access and recovery, configuration, operations, costs, test results, remaining owner actions and the closeout record. **Part 2** is the Owner and Administrator Manual: step-by-step instructions for every user and administrator workflow, with exact screen labels.

It is generated from the two source documents in the repository (`docs/closeout/CLIENTVERSE_CRM_CLOSEOUT_HANDOFF.md` and `docs/CLIENTVERSE_CRM_OWNER_ADMIN_MANUAL.md`) by `scripts/build_closeout_docs.py`. To change it, edit a source and rebuild; this file is not edited by hand.

<a id="part-1"></a>

# Part 1 — Production Closeout Handoff

<a id="p1-clientverse-crm--production-closeout-handoff"></a>

## ClientVerse CRM — Production Closeout Handoff

| | |
|---|---|
| **Document** | ClientVerse CRM Production Closeout Handoff (Part 1 of the closeout package) |
| **Version** | 1.0 |
| **Date** | 2026-10-24 |
| **Released revision** | `main@6d0d4c6` (merge of PR #48), verified running in production on 2026-10-24 ([§13.3](#p1-133-production-acceptance-results)) |
| **Production address** | **[https://crm.clientverse.io](https://crm.clientverse.io)** (sign in at **[https://crm.clientverse.io/login](https://crm.clientverse.io/login)**) |
| **Part 2 of the package** | [Owner/Admin Manual](#part-2): screen-by-screen procedures for every user and administrator workflow |
| **Governing document** | [Canonical Governing Document](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/CLIENTVERSE_CRM_CANONICAL_GOVERNING_DOCUMENT.md): product scope and capability status |
| **Repository** | `ebyron357/Clientverse-crm` |

> **No secrets are in this document.** It names where each password, key and connection
> string is kept, never its value.

---

<a id="p1-1-closeout-summary"></a>

## 1. Closeout summary

<a id="p1-11-where-things-stand"></a>

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

<a id="p1-12-what-is-verified-and-how"></a>

### 1.2 What is verified, and how

| Area | Verified by | Result |
|---|---|---|
| Intake repair (precedence, duplicates, changed data, budget semantics, tenant isolation) | 124 website-form tests (29 new); full CI on real MongoDB 7 | See [§13](#p1-13-tests-performed-and-production-acceptance-results) |
| Whole CRM journey (sign-in/out, roles, invitations, portal, forms, leads, pipeline, tasks, booking, integrations, export, UX at 3 widths, accessibility scan) | Local full stack driven by Playwright; release smoke 82/82; proof-of-life | See [§13](#p1-13-tests-performed-and-production-acceptance-results) |
| Production deployment, revision, health, database, authenticated lead journey, browser pass | **Production acceptance** workflow run against https://crm.clientverse.io | See [§13.3](#p1-133-production-acceptance-results) |
| Scheduled jobs reach production and are recorded | Scheduled-jobs workflow runs (every few minutes) with ledger read-back | See [§8.4](#p1-84-scheduled-jobs) |
| Backup and restore procedure | Backup-and-restore drill workflow | See [§10.4](#p1-104-restore-tested-procedure) |

<a id="p1-13-what-only-the-owner-can-complete"></a>

### 1.3 What only the owner can complete

These need the owner's own accounts or decisions. Each is listed with the exact action in
[§14](#p1-14-remaining-limitations-and-exact-owner-actions):

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

<a id="p1-2-production-environment-map"></a>

## 2. Production environment map

<a id="p1-21-addresses"></a>

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

<a id="p1-22-deployed-revision"></a>

### 2.2 Deployed revision

- Every merge into `main` deploys. To read what production runs, open
  https://crm.clientverse.io/api/health and read `git_sha`, then compare it with the newest
  commit on `main`.
- The closeout release is **`main@6d0d4c6`**, the merge of PR #48. Production reported exactly
  this `git_sha` during acceptance on 2026-10-24 at 21:27 UTC
  ([§13.3](#p1-133-production-acceptance-results)). Later documentation-only merges redeploy the same
  application code with a newer `git_sha`.
- The previous running revision was `main@394f095` (PR #46). Its scheduled jobs answered `200`
  on 2026-10-24.

<a id="p1-23-environment-map"></a>

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
  at it ([§14.1](#p1-141-owner-actions-exact) items 11–12).
- **Cloudflare Worker `clientverse-crm`** (created 2026-10-19 in the owner's Cloudflare account):
  it fails its own builds.

---

<a id="p1-3-owner-sign-in-account-setup-administration-and-recovery"></a>

## 3. Owner sign-in, account setup, administration and recovery

<a id="p1-31-the-owner-account"></a>

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

<a id="p1-32-sign-in-owner-and-every-user"></a>

### 3.2 Sign in (owner and every user)

1. Open **[https://crm.clientverse.io/login](https://crm.clientverse.io/login)**.
2. Under **"Sign in to ClientVerse"**, type your email in **"Work email"** and your password in
   **"Password"**.
3. Click **"Sign in"**.
4. **Check:** you arrive on **Today**, and the bottom of the left menu shows your name and
   **"Workspace admin"**.

Email and password is the **only** sign-in method. "Continue with Google" was removed on
2026-10-24 ([§14.3](#p1-143-security-notes)). **"Create a workspace"** at the bottom of the sign-in
page makes a *separate, empty organization*. The owner and the team should not use it; team
members join by invitation ([§4.2](#p1-42-invite-a-team-member)).

<a id="p1-33-sessions-and-sign-out"></a>

### 3.3 Sessions and sign-out

- A sign-in lasts **7 days**. It is kept in a secure, HTTP-only cookie and works across tabs and
  reloads.
- **Sign out:** the arrow icon at the bottom of the left menu. On a phone, open the menu (☰)
  first.
- After you sign out, that session can never be used again.
- **Lockout:** five wrong passwords lock the account for 15 minutes. Every failure shows the same
  message, *"Invalid email or password"*.

<a id="p1-34-change-your-password"></a>

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

<a id="p1-35-recovery"></a>

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

<a id="p1-4-roles-workspaces-and-invitations"></a>

## 4. Roles, workspaces and invitations

<a id="p1-41-roles"></a>

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

<a id="p1-42-invite-a-team-member"></a>

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

<a id="p1-43-client-workspaces-and-the-client-portal"></a>

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

<a id="p1-44-agency-and-client-accounts"></a>

### 4.4 Agency and client accounts

An admin can create separate client *organizations* under the agency:
- **Settings → Agency → "Client accounts"**: up to 200 accounts.
- Open a client account with **"Enter"**. A banner shows whose account you are working in.
- Snapshots copy a setup into up to 100 accounts at once.

Manual §7.24–§7.25.

---

<a id="p1-5-user-and-administrator-workflows"></a>

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
| Website forms: create, configure assignment and alerts, embed, server key | Admin | **Settings → Website Forms** | §7.6 and [§6](#p1-6-website-and-form-integration) |
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

<a id="p1-51-the-lead-journey-at-a-glance"></a>

### 5.1 The lead journey at a glance

1. **Lead in:** a visitor submits a website form, or the website's server forwards the lead
   ([§6](#p1-6-website-and-form-integration)).
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

<a id="p1-6-website-and-form-integration"></a>

## 6. Website and form integration

Full guide: [`docs/WEBSITE_FORMS.md`](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/WEBSITE_FORMS.md).

<a id="p1-61-integration-map"></a>

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

<a id="p1-62-field-mapping"></a>

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
| `priceRange`, `budget`, `pricemin`, `pricemax` | Minimum and maximum price ([§6.3](#p1-63-lead-processing-rules)) |
| `message`, `comments`, `your-message` | Message |
| `pageUrl`, `utm_*`, `gclid`, `fbclid`, `referrer` | **Source attribution** (first and latest touch on the contact) |
| `idempotencyKey`, `_sid` | Retry protection: a lead with the same key is filed once |
| Anything else | Kept on the lead under its own name (up to 40 extra answers) |

<a id="p1-63-lead-processing-rules"></a>

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

<a id="p1-64-alerts"></a>

### 6.4 Alerts

The form's **Automation → Speed to lead** section has **"In-app alert"** and **"Email alert"**
switches. Each controls its own channel. Email alerts need email delivery configured
([§7.3](#p1-73-email-notifications-transactional)). The no-response escalation is always sent.

---

<a id="p1-7-integrations-setup-and-operation"></a>

## 7. Integrations: setup and operation

<a id="p1-71-google-gmail-and-google-calendar"></a>

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

<a id="p1-72-gmail-outbound-email-consent-and-reply-capture"></a>

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

<a id="p1-73-email-notifications-transactional"></a>

### 7.3 Email notifications (transactional)

Invitations, new-lead email alerts and the daily digest use a separate email service.
- It is configured by the Railway variable **`EMERGENT_EMAIL_KEY`**. It was **not set** when last
  recorded.
- **Settings** shows whether it is configured, in the **"Email delivery"** row.
- Without it:
  - invitations show a link to copy;
  - in-app alerts still work.

<a id="p1-74-scheduling-and-online-booking"></a>

### 7.4 Scheduling and online booking

**Calendar** holds appointments and **booking pages**.
- An admin creates pages with **"Create my booking pages"** or one at a time.
- Each page has a public link `/book/<key>`, which can be embedded on a website.
- The `booking-reminders` job sends reminders exactly once.
- Booking confirmation emails need Gmail sending on. Until then the Calendar shows *"Not emailed
  — Email isn't connected"*.

Manual §7.7.

<a id="p1-75-billing-and-payments-stripe"></a>

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
5. Certify per [`docs/STRIPE_PROVIDER_CERTIFICATION.md`](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/STRIPE_PROVIDER_CERTIFICATION.md).

<a id="p1-76-other-integrations"></a>

### 7.6 Other integrations

| Integration | State |
|---|---|
| Outbound webhooks (for example `lead.received` to Zapier or Slack) | Available: **Registries → Webhooks** (admin). Signed and retried. |
| AI generation | **Off.** It needs `EMERGENT_LLM_KEY` **and** the `emergentintegrations` package, which the Docker image does not install. Without both, AI requests fail with an error and no fake output. |
| SMS, calling, Slack, ClickUp, n8n | Not implemented. Their screens say so. |
| MCP console (governed AI tools) | Available. The admin kill switch stops every tool at once. |

---

<a id="p1-8-architecture-services-data-and-scheduled-jobs"></a>

## 8. Architecture, services, data and scheduled jobs

<a id="p1-81-services"></a>

### 8.1 Services

| Part | What it is |
|---|---|
| **Web application** | One Railway service: a Python FastAPI API (`backend/`) that also serves the React screens (`frontend/`) from the same address |
| **Background work** | Inside the same process, no separate worker: the scheduler (13 jobs, coordinated through MongoDB leases), the lead speed-to-lead watcher (every 60 s) and the automation watcher (every 30 s). The durable work queue is a MongoDB collection. |
| **Database** | MongoDB Atlas, about 60 collections. Every record carries its organization (`tenant_id`); every query is scoped to it. |
| **File storage** | **None.** The CRM stores no uploaded files. Documents are links; exports are generated on request. |
| **External calls** | Google (OAuth, Gmail, Calendar); the Emergent email API (only if `EMERGENT_EMAIL_KEY` is set); Stripe (only if configured); webhooks the organization sets up |

<a id="p1-82-main-data-collections"></a>

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

<a id="p1-83-health-signals"></a>

### 8.3 Health signals

- **`GET /api/health`** (no sign-in) returns
  `{"service":"ClientVerse","version":"v1","status":"ok","database":"up","git_sha":"<commit>"}`.
  If the database does not answer, it returns `503` with `"database":"down"`. Railway uses it as
  the deployment health check.
- **`GET /api/cron/health`** (owner organization admin, or the scheduler secret) reports
  `scheduled_jobs_running`, the last runs, the last failure and the last rejected call.

<a id="p1-84-scheduled-jobs"></a>

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

<a id="p1-9-configuration-variables"></a>

## 9. Configuration variables

Values are never written down. Names, purpose and where each is managed:

<a id="p1-91-railway-service-clientverse-crm-production--variables"></a>

### 9.1 Railway: service `clientverse-crm-production` → Variables

| Variable | Purpose | Required |
|---|---|---|
| `MONGO_URL` | Atlas connection string | Yes |
| `DB_NAME` | Database name | Yes |
| `JWT_SECRET` | Signs sign-in sessions (at least 32 characters) | Yes |
| `INTEGRATION_ENC_KEY` | Encrypts stored Google and Stripe tokens. **Changing it breaks saved connections.** | Yes |
| `WEBHOOK_CRON_SECRET` | Secret the scheduler must present; same value as the GitHub secret | Yes |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Owner account and password ([§3.1](#p1-31-the-owner-account)) | Yes |
| `APP_ENV` | `production` turns on strict start-up checks (the image's default) | Default |
| `FRONTEND_URL` | Public address used in links and cookies: `https://crm.clientverse.io` | Yes |
| `CORS_ORIGINS` | Browser origins allowed: the custom domain and the Railway address | Yes |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | Google connection | For Google |
| `STRIPE_API_KEY` / `STRIPE_WEBHOOK_SECRET` | Stripe | Not set |
| `EMERGENT_EMAIL_KEY` / `EMAIL_FROM_NAME` | Notification and invitation emails | Not set (last recorded) |
| `EMERGENT_LLM_KEY` | AI generation (also needs a package; see [§7.6](#p1-76-other-integrations)) | Not set |
| `SEED_DEMO_DATA` | Must stay `false` in production | Default false |
| `IN_PROCESS_SCHEDULER`, `LEAD_SLA_WATCHER`, `AUTOMATION_WATCHER` | Background loops. Leave unset (on). | Default on |
| `LOGIN_LOCKOUT_THRESHOLD` / `LOGIN_LOCKOUT_MINUTES` | Lockout policy (5 / 15) | Default |
| `FORM_*`, `BOOKING_RATE_*`, `RECOVERY_*`, `WORK_QUEUE_*`, `SECOND_CHANCE_*` | Tuning knobs; the code defaults are in use | Optional |
| `Mongo_url` | **Unused misspelled duplicate. Delete it.** | — |

Railway itself supplies `PORT`, `RAILWAY_PUBLIC_DOMAIN` and `RAILWAY_GIT_COMMIT_SHA`. The last
one becomes `git_sha` in `/api/health`.

<a id="p1-92-github-repository--settings--secrets-and-variables--actions"></a>

### 9.2 GitHub: repository → Settings → Secrets and variables → Actions

| Secret | Used by | State |
|---|---|---|
| `CLIENTVERSE_PRODUCTION_URL` | Scheduled jobs | Set, but it points at the **Vercel** copy (`*.vercel.app`), not `https://crm.clientverse.io`. **Owner action 11.** Production acceptance does not use it; it tests `https://crm.clientverse.io`. |
| `WEBHOOK_CRON_SECRET` | Scheduled jobs (same value as Railway) | Set |
| `CLIENTVERSE_OWNER_EMAIL` / `CLIENTVERSE_OWNER_PASSWORD` | Optional read-only owner check in Production acceptance | **Not set: owner action** |

<a id="p1-93-agent-tooling-not-the-crm"></a>

### 9.3 Agent tooling (not the CRM)

`JEV_QC_WEBHOOK_URL` and `JEV_QC_WEBHOOK_TOKEN` (Claude Code environment) configure the Jev QC
verification gate. They were **not present** in this closeout session.

---

<a id="p1-10-deployment-rollback-backup-and-restore"></a>

## 10. Deployment, rollback, backup and restore

<a id="p1-101-deploy"></a>

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

<a id="p1-102-roll-back"></a>

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

<a id="p1-103-backup"></a>

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

<a id="p1-104-restore-tested-procedure"></a>

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

The result is in [§13.2](#p1-132-repository-and-local-verification). It proves the procedure and
the tools, not Atlas's own backups.

---

<a id="p1-11-monitoring-logs-diagnosis-support-and-maintenance"></a>

## 11. Monitoring, logs, diagnosis, support and maintenance

<a id="p1-111-what-to-watch"></a>

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

<a id="p1-112-logs"></a>

### 11.2 Logs

- **Railway → service → Deployments → (deployment) → Logs**. Useful lines:
  - start-up: `Application startup complete`, `In-process scheduler started for 13 job(s)`,
    `Registered outbound channel provider: gmail`;
  - failures: `In-process job '<job>' failed for window …`, `Lead automation failed for …`.
- **GitHub Actions** run logs for the scheduler, CI, acceptance and the drill.
- **Audit** page (in the CRM): who did what, when.

<a id="p1-113-failure-diagnosis"></a>

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

<a id="p1-114-routine-maintenance"></a>

### 11.4 Routine maintenance

| How often | Task |
|---|---|
| Weekly while Google is in Testing | Reconnect Google, or publish the consent screen to stop the 7-day lapse |
| Monthly | Check that the **Backup and restore drill** is green; read Atlas backup status; review **Team & Access** for leavers; review active portal links |
| After every release | Run **Production acceptance** |
| Quarterly | Rotate `ADMIN_PASSWORD` (Railway); review provider costs; review Railway and Atlas access lists |
| On a leaver | **Disable access** for them; revoke any portal links they shared |

---

<a id="p1-12-ongoing-service-costs"></a>

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

<a id="p1-13-tests-performed-and-production-acceptance-results"></a>

## 13. Tests performed and production acceptance results

<a id="p1-131-what-was-tested"></a>

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

<a id="p1-132-repository-and-local-verification"></a>

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
| Local browser journey: 33 routes × 3 widths; roles; invitation; reset; portal isolation; forms; pipeline; booking; export; dark mode; keyboard focus | `588bcea` | **Pass.** It found the defects fixed in PR #48 (portal link, revoke, copy feedback, contrast, MCP switch). An axe scan left two minor items ([§14.2](#p1-142-known-product-limitations-current-code)). |
| Local `production_acceptance.mjs` / `production_browser.mjs` | `7bca2c7` | **39/39 · 76/76** |
| **Backup and restore drill** (GitHub, MongoDB 7): create → `mongodump` → drop → `mongorestore` → verify | `7954a8f`, run #2 | **Pass.** Same password signs in. Lead fields, deal stage and value, contact and completed task restored. Server key and duplicate protection work. Run #1 failed in its dump step: the tool ran outside the database container. The drill now runs inside it. |
| Copilot review of PR #48: 4 findings on the intake code | — | All 4 reproduced, fixed in `d7d7645` with tests, and resolved |

<a id="p1-133-production-acceptance-results"></a>

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

Owner actions 11 and 12 in [§14.1](#p1-141-owner-actions-exact) resolve both.

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

<a id="p1-14-remaining-limitations-and-exact-owner-actions"></a>

## 14. Remaining limitations and exact owner actions

<a id="p1-141-owner-actions-exact"></a>

### 14.1 Owner actions (exact)

| # | Action | Where | Why |
|---|---|---|---|
| 1 | **Confirm owner access.** Either (a) add the repository secrets `CLIENTVERSE_OWNER_EMAIL` and `CLIENTVERSE_OWNER_PASSWORD` (the `ADMIN_EMAIL` / `ADMIN_PASSWORD` values), then run **Actions → Production acceptance** with **"owner_check"** ticked; or (b) sign in at https://crm.clientverse.io/login and tick Manual §14 rows 3–5. | GitHub → Settings → Secrets → Actions | No owner credential is available to engineering, by design. The check is read-only. |
| 2 | **Gmail:** open **Registries → Integrations → Gmail** and confirm **"Connected"**. Then decide whether to **"Send test & turn on"**. Then run Manual §6 Procedures A–C (send, duplicate protection, reply capture). | CRM (owner) | Only an admin session can see or turn on sending. Reply capture has never been certified live. |
| 3 | **Atlas backups:** confirm backup is on; record the cluster tier and retention. Optionally narrow network access from `0.0.0.0/0`. | cloud.mongodb.com | Largest open data risk |
| 4 | **Stripe:** decide whether it is in scope. If yes, follow [§7.5](#p1-75-billing-and-payments-stripe). | Stripe, Railway | Not configured |
| 5 | **Email notifications:** set `EMERGENT_EMAIL_KEY`, or accept link-only invitations and in-app alerts | Railway | Not set |
| 6 | **Rotate `ADMIN_PASSWORD`** (open item O-04); **delete `Mongo_url`**; rotate the legacy Stripe webhook secret that is in git history (O-05) | Railway, Stripe | Hygiene |
| 7 | **Record costs** in [§12](#p1-12-ongoing-service-costs) | Provider billing pages | No verified figures exist |
| 8 | **Policy:** should members be able to export leads and read the audit log? ([§4.1](#p1-41-roles)) | Reply in Issue #10 | Current behaviour allows both |
| 9 | **Cloudflare Worker `clientverse-crm`:** delete it, or tell engineering what it is for | dash.cloudflare.com | Fails on every push; unused |
| 10 | **Jev QC gate:** set `JEV_QC_WEBHOOK_URL` / `JEV_QC_WEBHOOK_TOKEN` in the Claude Code environment, and allow its host in the session network policy | Claude Code environment settings | Required by the repository's completion rule; absent in this session |
| 11 | **Point the scheduler at production:** set the GitHub secret `CLIENTVERSE_PRODUCTION_URL` to `https://crm.clientverse.io` (no trailing slash). Then confirm the next *Scheduled jobs* run is green, and that *Production acceptance*'s first step says *"Scheduler secret -> the custom domain"*. | GitHub → Settings → Secrets and variables → Actions | It points at the Vercel copy today. If that project changes or is deleted, the external scheduler stops (the in-app scheduler keeps running). |
| 12 | **Vercel project `clientverse-crm`:** after item 11, delete the project (recommended), or remove its `REACT_APP_BACKEND_URL` variable so its copy uses its `/api` forwarding | vercel.com → team `tradeiq` → project → Settings | It publishes a second, non-working sign-in page at `clientverse-crm.vercel.app` on every push |

<a id="p1-142-known-product-limitations-current-code"></a>

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

<a id="p1-143-security-notes"></a>

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

<a id="p1-15-final-operational-checklist"></a>

## 15. Final operational checklist

Tick each item, write the date, and keep this page with the closeout record.

**Production is healthy**

- [ ] https://crm.clientverse.io/login shows **"Sign in to ClientVerse"**
- [ ] https://crm.clientverse.io/api/health shows `"status":"ok"`, `"database":"up"` and the
      released `git_sha` ([§13.3](#p1-133-production-acceptance-results))
- [ ] Railway → Deployments: newest deployment **SUCCESS**
- [ ] GitHub → Actions: **CI** green on `main`; **Scheduled jobs** green in the last hour;
      **Production acceptance** green for this release; **Backup and restore drill** green

**Owner access** ([§3](#p1-3-owner-sign-in-account-setup-administration-and-recovery))

- [ ] The owner signs in with email and password and sees **"Workspace admin"**
- [ ] The owner signs out; opening `/dashboard` returns to the sign-in page
- [ ] `/api/cron/health`, signed in as the owner, shows `"scheduled_jobs_running": true`
- [ ] `ADMIN_PASSWORD` rotated in Railway (O-04) and stored in the owner's password manager

**Team and clients** ([§4](#p1-4-roles-workspaces-and-invitations))

- [ ] Every real team member has an account from an invitation; leavers are disabled
- [ ] Client portal links in use are listed under **Active links**; unknown links are revoked

**Lead intake** ([§6](#p1-6-website-and-form-integration))

- [ ] Each live website form is **Live**, with its allowed websites set (embed) or a server
      key in the website's environment (server connection)
- [ ] One real test lead from each website reached **Leads** with its fields and source, then
      was marked responded and closed

**Integrations** ([§7](#p1-7-integrations-setup-and-operation))

- [ ] Gmail row **"Connected"** (or a decision recorded not to use Gmail)
- [ ] Email sending decision recorded (on with **"Send test & turn on"**, or off)
- [ ] Stripe decision recorded (in scope or not)
- [ ] Email notifications decision recorded (`EMERGENT_EMAIL_KEY` set, or link-only)

**Data safety** ([§10](#p1-10-deployment-rollback-backup-and-restore))

- [ ] Atlas backup confirmed on; tier and retention recorded
- [ ] Unused `Mongo_url` variable deleted from Railway
- [ ] Monthly restore drill reviewed

**Costs** ([§12](#p1-12-ongoing-service-costs))

- [ ] Monthly amounts recorded for Railway, Atlas, the domain and GitHub


---

<a id="p1-16-closeout-record"></a>

## 16. Closeout record

| Item | Record |
|---|---|
| Closeout date | 2026-10-24 |
| Released revision | `main@6d0d4c6`: merge of PR #48, which carries PR #47 |
| Production address | https://crm.clientverse.io (Railway service `clientverse-crm-production`) |
| Production verification | Production acceptance run `40134314474`: API 40/40, browser 76/76, revision match ([§13.3](#p1-133-production-acceptance-results)) |
| Restore procedure | Tested: Backup and restore drill, pass ([§10.4](#p1-104-restore-tested-procedure)) |
| Pull requests | #48 merged; #47 merged through #48; #36 closed as superseded (its fixes were already on `main`) |
| Defects fixed in this closeout | 17. Intake: alias overwrite, refused list budgets, open-ended budgets, inverted ranges, nested precedence, stale contact ceiling, re-pricing race and currency. Security: third-party sign-in, ledger exposure. UI: alert switch ignored, clipped table actions, lost portal link and no revoke, false "copied", contrast, member MCP switch. |
| Documentation | This handoff (Part 1); Owner/Admin Manual v1.13 (Part 2); the generated Word and Markdown package; `WEBSITE_FORMS.md`; `RAILWAY_RUNBOOK.md`; governing document v1.27; `AGENTS.md` |
| Jev QC gate | **Not run.** Its variables were absent from this session ([§14.1](#p1-141-owner-actions-exact) item 10). The repository rule therefore forbids recording this work as Jev `VERIFIED_COMPLETE`. The verification above is the GitHub evidence listed. |
| Open owner items | [§14.1](#p1-141-owner-actions-exact). Owner sign-in confirmation, Gmail sending, Atlas backups, the scheduler secret and the Vercel copy matter most. |
| Status | **Released and verified in production for the lead journey and the screens.** The items in §14.1 remain the owner's to close. |


<a id="part-2"></a>

# Part 2 — Owner and Administrator Manual

<a id="p2-clientverse-crm--owneradmin-manual"></a>

## ClientVerse CRM — Owner/Admin Manual

| | |
|---|---|
| **Document** | ClientVerse CRM Owner/Admin Manual |
| **Version** | 1.13 |
| **Date** | 2026-10-24 |
| **Repository** | `ebyron357/Clientverse-crm` |
| **Branch documented** | `main` after the closeout release (PR #48, 2026-10-24). Read the running commit from `/api/health` → `git_sha` ([§2.2](#p2-22-confirm-you-are-on-the-correct-deployment)) |
| **Production environment** | Railway project `welcoming-vibrancy` → environment `production` → service `clientverse-crm-production` |
| **Production URL** | https://crm.clientverse.io (the Railway address https://clientverse-crm-production-production.up.railway.app reaches the same CRM) |
| **Sign-in page** | https://crm.clientverse.io/login |
| **Purpose** | Everything the owner needs to reach, sign in to, operate, administer, verify and get help with ClientVerse CRM — without a developer beside them and without reading source code. |
| **Intended audience** | Primary: the CRM owner / business administrator. Secondary: a future client admin or operator. |
| **Authority** | The official owner/admin handoff source of truth, registered in [the canonical governing document](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/CLIENTVERSE_CRM_CANONICAL_GOVERNING_DOCUMENT.md) (§0.2, §0.5). Product scope and capability status remain governed by that document. |
| **Tracking issue** | [ebyron357/Clientverse-crm#33](https://github.com/ebyron357/Clientverse-crm/issues/33) |

> **No secrets are in this manual.** It never contains passwords, API keys, OAuth client
> secrets, tokens, invite links, portal links or database addresses. Where one is needed,
> it names the place the secret is kept (for example the Railway variable `ADMIN_PASSWORD`)
> and never the value.

<a id="p2-how-to-read-this-manual"></a>

### How to read this manual

- **Numbered steps** are procedures. Do them in order.
- **Bold text in quotes** — for example **"Sign in"** — is a label exactly as it appears on
  screen, so you can find it.
- **Warning:** marks something that can lock you out, lose data or expose a secret.
- **Check:** tells you how to know a step worked.
- Every fact carries its evidence:
  - **Verified (code)** — read from the application code that production runs.
  - **Verified (live, \<date\>)** — observed in production on that date through Railway's
    deployment records and logs, or GitHub Actions run records.
  - **UNVERIFIED — OWNER/ENGINEERING INPUT REQUIRED** — could not be confirmed. Do not rely on it
    until someone confirms it and this manual is updated.

**How the screens were verified.** Every screen description comes from the code deployed in
production. The engineering environment that wrote this manual cannot open the production
website itself (its network policy refuses the connection), so the owner's own walk-through in
[Chapter 14](#p2-14-production-verification-checklist) is the final live confirmation.

---

<a id="p2-table-of-contents"></a>

## Table of Contents

1. [Owner Quick Start](#p2-1-owner-quick-start)
2. [System Access](#p2-2-system-access)
3. [Login and Access](#p2-3-login-and-access)
4. [First Login Orientation](#p2-4-first-login-orientation)
5. [Google / Gmail Setup](#p2-5-google--gmail-setup)
6. [Email Production Verification](#p2-6-email-production-verification)
7. [CRM Daily Use](#p2-7-crm-daily-use)
8. [Users, Roles, and Administration](#p2-8-users-roles-and-administration)
9. [Account Recovery](#p2-9-account-recovery)
10. [Integrations](#p2-10-integrations)
11. [Scheduler / Automations](#p2-11-scheduler--automations)
12. [Troubleshooting Matrix](#p2-12-troubleshooting-matrix)
13. [Security and Owner Safety](#p2-13-security-and-owner-safety)
14. [Production Verification Checklist](#p2-14-production-verification-checklist)
15. [Support / Escalation](#p2-15-support--escalation)

Appendices

- [A. Acceptance self-test — questions this manual answers](#p2-appendix-a-acceptance-self-test)
- [B. System state on 2026-10-19](#p2-appendix-b-system-state-on-2026-10-19)
- [C. Engineer-assisted email verification (API procedure)](#p2-appendix-c-engineer-assisted-email-verification)
- [D. Configuration and secrets register (names only)](#p2-appendix-d-configuration-and-secrets-register)
- [E. Related documents](#p2-appendix-e-related-documents)
- [F. Document control](#p2-appendix-f-document-control)

---

<a id="p2-1-owner-quick-start"></a>

## 1. Owner Quick Start

The shortest path from nothing to a working, checked CRM. About ten minutes.

<a id="p2-11-quick-reference-card"></a>

### 1.1 Quick-reference card

| What | Where |
|---|---|
| Production CRM | https://crm.clientverse.io |
| Sign in | https://crm.clientverse.io/login |
| Is the service up? (no sign-in needed) | https://crm.clientverse.io/api/health |
| Is the automation running? (sign in as admin first) | https://crm.clientverse.io/api/cron/health |
| Hosting dashboard | Railway → project `welcoming-vibrancy` → service `clientverse-crm-production` (https://railway.com/project/bbcb2596-d6f9-45c5-9c03-59cb97f373ea) |
| Optional second scheduler (GitHub) | https://github.com/ebyron357/Clientverse-crm/actions/workflows/scheduled-jobs.yml |
| Sign-in method | Email address + password, the only sign-in method ([§3.1](#p2-31-supported-sign-in-methods)) |
| Your account | The address in the Railway variable `ADMIN_EMAIL`, with the password in the Railway variable `ADMIN_PASSWORD` ([§3.3](#p2-33-which-account-the-owner-uses)) |

<a id="p2-12-sign-in"></a>

### 1.2 Sign in

1. Open **[https://crm.clientverse.io/login](https://crm.clientverse.io/login)** in a current
   Chrome, Edge, Firefox or Safari.
2. Under the heading **"Sign in to ClientVerse"**, type your owner email in **"Work email"** and
   your password in **"Password"**. The eye button beside the password shows or hides what you typed.
3. Click **"Sign in"**.
4. **Check:** the page changes to **Today** (`/dashboard`, headed **"Good morning, {your name}"**). At the
   bottom of the dark menu on the left you see your name and **"Workspace admin"**.

**Warning:** Do not click **"Create a workspace"** at the bottom. It creates a *separate, empty*
organization that is not your CRM ([§3.1](#p2-31-supported-sign-in-methods)).

<a id="p2-13-find-settings-and-integrations"></a>

### 1.3 Find Settings and Integrations

The main menu on the left lists the eleven everyday pages. **"Settings"** is pinned at its
bottom, and the Settings page has its own menu on the left ([§4.3](#p2-43-main-menu-and-settings-map--every-item-and-whether-it-is-active)).

- **Settings:** left menu → **"Settings"** (bottom). It opens on **"General"**.
- **Integrations** (Google, Stripe): **Settings** → **Connections** → **"Integrations"**. This opens
  the **Registries** page on its **"Integrations"** tab. You can also go through **Settings** →
  **"General"** → the **"Integrations"** section → **"View integrations"**.

<a id="p2-14-first-things-to-verify"></a>

### 1.4 First things to verify

Do these five checks after every first sign-in, and whenever something seems wrong.

| # | Check | Where | Healthy answer |
|---|---|---|---|
| 1 | You are an admin | **Settings** → **"Profile"** → **"Access level"** | **"Workspace admin"** |
| 2 | The service and database are up | Open `/api/health` (link in [§1.1](#p2-11-quick-reference-card)) | `"status":"ok"` and `"database":"up"` |
| 3 | Google is connected | **Registries** → **Integrations** → **Gmail** row | **"Connected"**, no red error line. If it says **"Needs auth"**, follow [§5.6](#p2-56-re-authorize-google) |
| 4 | Automation is running | Open `/api/cron/health` while signed in as admin | `"scheduled_jobs_running": true` ([§11.4](#p2-114-verify-that-automation-is-healthy)) |
| 5 | No critical alerts | **Action Center** (the bell → **"View all in Action Center"**) | Nothing unexpected under **"Needs action"** |

**Check 3: what is known.** Google refused to refresh the saved permission on 2026-09-30
(Railway log `POST https://oauth2.googleapis.com/token` → `400 Bad Request`). The owner then
reconnected Google on 2026-10-19 at 02:02 UTC, and the Railway log shows Google granting
`gmail.readonly`, `gmail.send` and `calendar.readonly` ([§6.1](#p2-61-read-this-first--current-status)).
Engineering cannot see the Gmail row itself; only an admin session can. If the row says
**"Needs auth"** or shows a red line, reconnect ([§5.6](#p2-56-re-authorize-google)). While the Google
consent screen is in **Testing**, Google ends the permission after 7 days, so expect to reconnect
weekly until it is published.

<a id="p2-15-if-something-is-broken"></a>

### 1.5 If something is broken

- Look up the symptom in the [Troubleshooting Matrix](#p2-12-troubleshooting-matrix).
- If the matrix says to escalate, collect the evidence in [§15.2](#p2-152-evidence-to-collect-before-you-escalate).
  Never include a password or secret.

---

<a id="p2-2-system-access"></a>

## 2. System Access

<a id="p2-21-addresses"></a>

### 2.1 Addresses

| Environment | Address | Use it? |
|---|---|---|
| **Production** | **[https://crm.clientverse.io](https://crm.clientverse.io)** | **Yes — use this address.** |
| Production, Railway address | https://clientverse-crm-production-production.up.railway.app | Same CRM, same data. It keeps working, so older links and the Stripe webhook still reach production. Signing in on one address does not sign you in on the other. |
| Custom domain status | Verified (live, 2026-10-19): Railway reports `crm.clientverse.io` verified, certificate valid, CNAME `crm` → `br0g4oob.up.railway.app` propagated. Railway sets `FRONTEND_URL` and `GOOGLE_REDIRECT_URI` to this address, and `CORS_ORIGINS` lists both addresses ([§10.2](#p2-102-google--gmail-and-google-calendar)). | — |
| Staging | None. No staging environment is configured or documented. The only deployment path is Railway `production`. | — |
| Old preview and hosting addresses (Render, Manus, OpenHands, Emergent previews) | Historical only. | **No.** They are not production. Never run a second copy against the production database. |

<a id="p2-22-confirm-you-are-on-the-correct-deployment"></a>

### 2.2 Confirm you are on the correct deployment

1. The address bar shows exactly `crm.clientverse.io` (or the Railway address in §2.1), with a
   padlock (HTTPS).
2. The browser tab reads **"ClientVerse — Client Operations Platform"**. The sign-in page shows the
   ClientVerse logo and **"Sign in to ClientVerse"**.
3. Open https://crm.clientverse.io/api/health. A healthy answer
   looks like this:

   ```json
   {"service":"ClientVerse","version":"v1","status":"ok","database":"up","git_sha":"<40-character commit id>"}
   ```

4. Compare `git_sha` with the commit shown on Railway's active deployment: Railway → service
   `clientverse-crm-production` → **Deployments** → the top **ACTIVE / SUCCESS** entry. They should
   match. Every change merged to `main` redeploys automatically, so the deployment id changes with
   each merge. Always read it from Railway, not from a document.
   - Verified (live, 2026-10-19): the active deployment `e7790295-…` runs commit `838f00d…`; it
     was redeployed at 01:47 UTC to apply the custom-domain variables. Each start-up logged `Registered outbound channel provider: gmail` →
     `In-process scheduler started for 13 job(s): …` → `Application startup complete` →
     `GET /api/health 200`.

<a id="p2-23-if-the-site-does-not-load"></a>

### 2.3 If the site does not load

1. Check your own connection by opening any other website.
2. Open https://crm.clientverse.io/api/health and read the result:

   | What you see | Meaning | Next step |
   |---|---|---|
   | `"status":"ok"` and `"database":"up"` | The CRM is running. The problem is your browser or session. | [§9.4](#p2-94-stale-browser-session) |
   | `"status":"degraded"` and `"database":"down"` (HTTP 503) | The application is up but cannot reach its database (MongoDB Atlas). | Escalate to engineering ([§15](#p2-15-support--escalation)). The owner can check MongoDB Atlas for an outage or a network-access change. |
   | A Railway-branded error page ("Application failed to respond", "Not Found") | No healthy deployment is serving. | Step 3 |
   | The browser cannot connect at all | DNS, network or Railway outage. | Step 3 |

3. Open the Railway dashboard → project `welcoming-vibrancy` → service
   `clientverse-crm-production` → **Deployments**, and read the newest entry:
   - **BUILDING / DEPLOYING** — a deploy is in progress. A normal build takes about 2–3 minutes
     (2026-10-19: 01:14 → 01:16 UTC). Wait 5 minutes and retry.
   - **SUCCESS** — the service should be up. Click **View logs**, look for errors, and escalate with
     a screenshot.
   - **FAILED** or **CRASHED** — escalate to engineering at once, with the deployment time and a
     screenshot of the log ([§15](#p2-15-support--escalation)). Railway normally keeps the previous
     healthy deployment serving while a new deployment fails its health check, so a failed *new*
     deploy does not always mean the site is down.
4. **Safe owner action:** on the latest **SUCCESS** deployment, use **Restart** (Railway ⋮ menu) once.
   **Needs engineering agreement:** Rollback, Redeploy of an older commit, or any change to
   variables other than `ADMIN_PASSWORD`.

<a id="p2-24-browser-considerations"></a>

### 2.4 Browser considerations

- Use a current desktop Chrome, Edge, Firefox or Safari. On a phone the sidebar opens from the menu
  button at the top left, and search and **"Create"** are icons in the top bar.
- The site must be allowed to store cookies and site data. The session is kept in an
  `access_token` cookie and in browser storage. Private or incognito windows work, but sign you out
  when closed.
- **Ctrl+K** (Windows) or **⌘K** (Mac) opens search. **Ctrl+Q** / **⌘Q** opens "Quick create", but on
  a Mac the browser usually quits first — use the **"Create"** button instead.
- Light, dark or "match my device" colours: the theme button at the bottom of the sidebar. The
  choice is kept in this browser only.
- In the browser developer console, one `401` from `/api/auth/me` on the sign-in page is normal.
  That is the app checking whether you are already signed in.

---

<a id="p2-3-login-and-access"></a>

## 3. Login and Access

<a id="p2-31-supported-sign-in-methods"></a>

### 3.1 Supported sign-in methods

| Method | Status | Should the owner use it? |
|---|---|---|
| **Email + password** | Verified (code). Last proven live in production on 2026-09-01 (`scripts/proof_of_life.mjs` against `ca30587`). | **Yes — this is the owner's method.** |
| **"Continue with Google"** (removed 2026-10-24) | **Removed.** The button sent people to a third-party sign-in service (`auth.emergentagent.com`) left over from the platform the CRM was prototyped on, which the owner does not control. The server trusted that service to say who a visitor was, so whoever controls the service could sign in as any user, the owner included. It also created stray organizations and ignored invitations. The server now refuses it (`410`); it was never the Gmail connection, which is unaffected ([§5](#p2-5-google--gmail-setup)). | Not available. |
| **"Create a workspace"** (self-registration, at the bottom of the sign-in page) | Verified (code). It works, but always creates a **new, separate organization** with the new person as its admin. It gives no access to your data. | **No** for the owner. Team members join through invitations, which create their account directly inside your team ([§8.3](#p2-83-what-to-tell-the-invitee-accepting-an-invitation)). |

<a id="p2-32-sign-in-with-email-and-password"></a>

### 3.2 Sign in with email and password

1. Go to https://crm.clientverse.io/login.
2. The heading reads **"Sign in to ClientVerse"**. If it reads **"Create your workspace"**, click
   **"Sign in"** at the bottom to switch back.
3. **"Work email"** — your owner email. **"Password"** — your password.
4. Click **"Sign in"**. The button shows **"Please wait…"** while it works.
5. **Check:** you arrive on **Today** (`/dashboard`).
6. If a red box shows **"Invalid email or password"**, see [§9.1](#p2-91-wrong-password) and
   [§9.3](#p2-93-account-locked-out). The CRM gives the **same message** for a wrong password, an
   unknown address and a locked account, on purpose.
7. If the screen **"Choose your own password"** appears instead, you signed in with a temporary
   password an admin gave you — see [§9.2](#p2-92-forgotten-password).

<a id="p2-33-which-account-the-owner-uses"></a>

### 3.3 Which account the owner uses

- The owner account is created automatically the first time the server starts, from two Railway
  variables:
  - **email** = the value of `ADMIN_EMAIL`
  - **password** = the value of `ADMIN_PASSWORD`

  It is an **admin** of the organization first named **"ClientVerse HQ"**. An admin can rename the
  organization in **Settings** → **"Organization"** → **"Business name"**. Verified (code).
- The owner already knows this address. It is deliberately not written here. To look it up, open
  Railway → service → **Variables**. Only the Railway dashboard is an approved place to read it.
- **Your password is re-applied at every restart and every deploy.** The server resets the owner
  account's password to whatever `ADMIN_PASSWORD` holds, and every merge to `main` redeploys. So
  a change made in **Settings** → **"Change password"** ([§3.9](#p2-39-change-your-own-password))
  lasts only until the next deploy. Change the owner password in Railway ([§9.2](#p2-92-forgotten-password)).
- **Warning: never change `ADMIN_EMAIL`.** At the next start the server would create a brand-new,
  empty **"ClientVerse HQ"** organization for the new address. Your existing data would stay with
  the old account. If the owner login address must change, escalate to engineering.

<a id="p2-34-verify-the-sign-in-and-your-role"></a>

### 3.4 Verify the sign-in and your role

- **Sidebar footer** (bottom left) shows your initials, your name and either **"Workspace admin"**
  or **"Team member"**.
- **Settings** → **"Profile"** shows **"Name"**, **"Email"** and **"Access level"**.
- Admins see **"Team and roles"** under **Workspace**, and the **Developer** group, in the Settings
  menu. Members do not.

<a id="p2-35-sign-out"></a>

### 3.5 Sign out

1. Click the sign-out icon at the bottom right of the sidebar (its tooltip reads **"Sign out"**).
   Alternatively: **Settings** → **"Security"** → **"Session"** → **"Sign out"**.
2. **Check:** you return to the sign-in page.
3. Signing out cancels that session on the server immediately. Closing the tab does **not** sign
   you out — a session otherwise lasts **7 days**. Always sign out on a shared computer.

<a id="p2-36-password-requirements"></a>

### 3.6 Password requirements

- **New passwords need at least 8 characters**: when you change your password, when a teammate
  creates their account from an invitation, and when a new workspace is created. Verified (code).
- `ADMIN_PASSWORD` in Railway is not checked for length.
- **Owner policy — follow it anyway:** at least 16 characters, unique to ClientVerse, and generated
  and stored by a password manager.
- A **temporary password** from an admin reset looks like three groups of four characters joined by
  dashes. It opens nothing until the person chooses their own ([§8.8](#p2-88-reset-a-members-password)).

<a id="p2-37-lockout-behaviour"></a>

### 3.7 Lockout behaviour

Verified (code); defaults, which the recorded production variable list does not override.

- After **5 failed sign-ins in a row** for the same email address, that address is locked for
  **15 minutes**.
- While it is locked, even the **correct** password shows **"Invalid email or password"**.
- A wrong **current** password in **"Change password"** counts as a failed sign-in too.
- The failure count resets only on a successful sign-in, or when an admin resets that person's
  password. So after a lockout ends, **one more wrong password locks it again** for another
  15 minutes. Make your next attempt count.
- The lock follows the email address, on every device and browser. See [§9.3](#p2-93-account-locked-out).

<a id="p2-38-what-must-never-appear-in-a-document-issue-or-message"></a>

### 3.8 What must never appear in a document, issue or message

The value of `ADMIN_PASSWORD` or any password (including temporary ones), and `JWT_SECRET`,
`INTEGRATION_ENC_KEY`, `WEBHOOK_CRON_SECRET`, `GOOGLE_CLIENT_SECRET`, `STRIPE_API_KEY`,
`STRIPE_WEBHOOK_SECRET` or `MONGO_URL`.

That also covers:

- session cookies and tokens (`access_token`, `cv_access_token`)
- invitation links (`/invite?token=…`)
- client-portal links (`/portal/…`) and booking manage links (`/booking/manage/…`)
- webhook signing secrets

See [Chapter 13](#p2-13-security-and-owner-safety).

<a id="p2-39-change-your-own-password"></a>

### 3.9 Change your own password

1. **Settings** → **"Security"** → **"Password"** → **"Change password"**.
2. In **"Change your password"**, type **"Current password"**, then **"New password"** and
   **"New password again"** (at least 8 characters). **"Show passwords"** reveals what you typed.
3. Click **"Change password"**.
4. **Check:** the message **"Password changed"**. You stay signed in here; every other phone or
   computer signed in to your account is signed out. If you were working in a client account
   ([§7.25](#p2-725-agency-and-client-accounts)), you stay in it.

- **Owner account:** see the warning in [§3.3](#p2-33-which-account-the-owner-uses) — use Railway.
- An account that signs in only with Google has no ClientVerse password to change.

---

<a id="p2-4-first-login-orientation"></a>

## 4. First Login Orientation

<a id="p2-41-screen-landmarks"></a>

### 4.1 Screen landmarks

| Landmark | Where | What it does |
|---|---|---|
| **Main menu** (the dark sidebar) | Left edge | The eleven everyday pages — **Today**, **Leads**, **Inbox**, **Contacts**, **Pipeline**, **Calendar**, **Tasks**, **Approvals**, **Clients**, **Automations**, **Reports** — with **"Settings"** pinned at the bottom ([§4.3](#p2-43-main-menu-and-settings-map--every-item-and-whether-it-is-active)). The **"Collapse navigation"** button shrinks it to icons (the browser remembers). On a phone it opens from the menu button. |
| **Counts** beside menu items | Main menu | **Leads**: new leads nobody has contacted. **Inbox**: open conversations. **Tasks**: your overdue tasks, plus overdue tasks nobody owns. **Approvals**: requests waiting for a decision. Red means act now; grey is a count to get to today. No badge means zero, or the count could not be read. |
| **Search** | Top bar: **"Search or jump to…"** (Ctrl/⌘ K) | Jumps to a *page or action*. It does **not** search your records ([§7.19](#p2-719-search)). |
| **Menu footer** | Bottom of the main menu | Your initials, name and role (**"Workspace admin"** / **"Team member"**), the theme button (light → dark → match device) and the sign-out icon. |
| **Breadcrumb** | Top bar, left | Where the page sits, for example *Contacts*, *Pipeline › Deals* or *Settings › Audit log*. |
| **"Create"** | Top bar, right | Quick create: company, contact, opportunity or client workspace. |
| **Bell** | Top bar, far right | Notifications, with an unread count ([§7.12](#p2-712-action-center-and-notifications)). |
| **Settings menu** | Left of every Settings page | Workspace, Capture, Connections, Compliance, Developer (admins only) and **Coming soon** — the modules that are **not active yet** (placeholder pages). |
| **Side panel** | Right edge, over the page | Opening a contact, company, deal, lead or task slides its record in from the right: tabs on one side, a **"Details"** panel on the other. Close it with ✕ or Esc. |

<a id="p2-42-what-you-see-after-sign-in-today"></a>

### 4.2 What you see after sign-in: Today

**Today** (`/dashboard`, **"Today"** in the main menu) is the home page. Its header greets you
(**"Good morning, {name}"**, afternoon or evening by your computer's clock), with the date, how many
things are on your plan, and **"Refresh"**. From top to bottom:

1. **Four figures.** Click any one to open its list.
   - **"Leads not acted on"** — website and booking leads nobody has replied to, and how long the
     oldest has waited.
   - **"Booked this week"** — appointments this week (Monday to Sunday), by kind.
   - **"Open pipeline"** — the value of open deals, the number of deals, and the value weighted by
     each stage's probability. Amounts in different currencies are shown side by side, never added.
   - **"Waiting on you"** — approval requests waiting for a decision plus client commitments marked
     at risk or breached.
2. **"Set up your workspace"** — a 4-step setup checklist. Its first step, **"Choose your industry
   template"**, opens **Settings → Industry template** ([§7.23](#p2-723-industry-templates)) and is
   ticked once a template has been applied. Dismissing the checklist hides it in this browser
   only. It reappears in another browser, or after clearing site data.
3. **"Your plan"** — what to do next, numbered in order, each with the reason it is there
   (on a phone it comes first). The order is fixed and checkable:
   1. new leads, oldest first (three by name; the rest as **"Reply to N more new leads"**) —
      *"Waiting 2 h 10 min; the goal is a reply within 5 min"*;
   2. an appointment starting within 2 hours — *"Starts in 45 min"*;
   3. overdue tasks — *"Overdue by 2 days"*;
   4. approval requests waiting for a decision (admins only);
   5. client commitments at risk or breached;
   6. tasks due today;
   7. deals with no activity for 14 days and no task planned — **"Set a next step for …"**.
   Tasks are yours plus the ones nobody owns, as on **Tasks**. **"Show all N"** lists the rest.
4. **"New leads waiting"** — each lead with its company, topic, a booked appointment if there is one,
   their message, how long they have waited (red once past the reply goal), and **"Call"**, text
   and email buttons. **"All leads"** opens **Leads**.
5. **"Pipeline"** — deals and value per stage. **"Clients"** — client health and commitments at
   risk.
6. **"Next best actions"** — ranked recommendations across all clients, with **"Accept"**,
   **"Done"**, **"Snooze"** and **"Not relevant"**.
7. On the right (below, on a narrow screen): **"Appointments"** (**"Today"** / **"Week"**),
   **"Tasks"** (tick one to mark it done; **"Call N new leads now"** → **"Start"** opens Leads),
   **"Operational alerts"** (with **"Scan now"**) and **"Connection health"** (admins only).

Won deals and their value are in the **"Closed won"** column of the **Pipeline** board; outcome
progress is on each client's **Client 360** page. A new, empty CRM shows friendly empty states — for example **"Your pipeline
starts here"** and **"You're clear"**. That is correct, not an error.

<a id="p2-43-main-menu-and-settings-map--every-item-and-whether-it-is-active"></a>

### 4.3 Main menu and Settings map — every item and whether it is active

Verified (code): `frontend/src/platform/navigation.js`, `frontend/src/platform/modules.js`,
`frontend/src/App.js`.

**Main menu** (left edge, in this order). Every item is active. A module that is not active
never appears here.

| Menu item | Opens (page heading) | Count badge | Admin only |
|---|---|---|---|
| **Today** | `/dashboard` (**Today**: your plan, new leads, appointments, tasks) | | |
| **Leads** | `/leads` | New leads nobody has contacted (red) | |
| **Inbox** | `/operations?tab=conversations` (Operations → **Conversations**; read, hand off and close only — [§7.13](#p2-713-operations)) | Open conversations (red) | |
| **Contacts** | `/contacts` — the page with the **"Companies"** and **"Contacts"** tabs (`/companies` opens the other tab) | | |
| **Pipeline** | `/pipeline` (the Pipeline board; `/deals` opens the same board) | | **"Customize stages"**: admin |
| **Calendar** | `/scheduling/calendar` — online booking ([§7.7](#p2-77-calendar-and-online-booking)) | | Booking pages and approving emails: admin |
| **Tasks** | `/tasks` | Your overdue tasks, plus overdue tasks nobody owns (grey) | |
| **Approvals** | `/operations?tab=approvals` (Operations → **Approvals**) | Requests waiting for a decision (grey) | Deciding: admin |
| **Clients** | `/workspaces` (**Client 360**) | | |
| **Automations** | `/automations` — when something happens, do these steps ([§7.22](#p2-722-automations)) | | Creating, changing, turning on or off: admin |
| **Reports** | `/proof` (**Recovery Proof**) | | |
| **Settings** (pinned at the bottom) | `/settings` (**General**) | | |

**Settings menu** (left of every Settings page).

| Group | Item | Opens (page heading) | Admin only |
|---|---|---|---|
| Workspace | **General** | `/settings` — profile, security, notifications, integration status, organization | |
| Workspace | **Industry template** | `/settings/templates` — a starting setup for your kind of business ([§7.23](#p2-723-industry-templates)) | Applying one: admin |
| Workspace | **Snapshots** | `/settings/snapshots` — save this workspace's setup and load it into another ([§7.24](#p2-724-snapshots)) | **Yes** (hidden from members) |
| Agency | **Client accounts** | `/settings/agency` — the client accounts your agency runs ([§7.25](#p2-725-agency-and-client-accounts)); not shown inside a client account's own workspace | **Yes** (the group is hidden from members) |
| Workspace | **Fields** | `/settings/fields` — your own fields on contacts, companies and deals ([§7.4](#p2-74-contacts-and-companies) item 8) | Adding and changing fields: admin |
| Workspace | **Team and roles** | `/team` (**Team & Access**) | **Yes** (hidden from members) |
| Workspace | **Client portal and playbooks** | `/client-ops` (**Client Operations**: safe automation rules, playbooks, the client portal and commercial records — [§7.15](#p2-715-client-operations-and-the-client-portal)) | Some buttons: admin |
| Workspace | **Lead routing** | `/website-forms` — each form's **"Assign the lead"** section sets who gets its leads | Changing it: admin |
| Capture | **Forms** | `/website-forms` (**Website Forms**) | Creating and changing forms: admin |
| Capture | **Booking pages** | `/scheduling/calendar?tab=pages` (Calendar → **"Booking pages"**) | Creating and changing pages: admin |
| Connections | **Integrations** | `/registries?tab=integrations` (Registries → **"Integrations"**) | Connect/sync: admin |
| Connections | **Email sending** | The same page: the sending switch is on the **Gmail** row ([§5.10](#p2-510-turn-email-sending-on-or-off)) | Turning it on or off: admin |
| Compliance | **Audit log** | `/audit` (**Automation & Audit**) | Undo: admin |
| Developer | **MCP console** | `/mcp` (**MCP Console**) | **Yes** (the group is hidden from members); kill switch and undo: admin |
| Developer | **Registries** | `/registries` (MCP servers, plugins, webhooks) | **Yes** |
| Developer | **Operations** | `/operations` (work queue, recovery strategies, security gate) | **Yes**; some buttons: admin |
| Coming soon | **Email**, **SMS** | `/communications/email`, `/communications/sms` | **Not active** — "Configuration required" |
| Coming soon | **Calling**, **Revenue Operations**, **Support**, **Reporting**, **Relationship Intelligence**, **Migration**, **Knowledge** | `/communications/calling`, `/revenue`, `/support`, `/intelligence/reporting`, `/intelligence/relationships`, `/platform/migration`, `/platform/knowledge` | **Not active** — "Backend contract pending" |

The Settings menu sits beside General, Industry template, Snapshots, Fields, Team and roles, Forms, Integrations and Registries, Audit
log, MCP console and every Coming soon page. **Booking pages** and **Operations** open pages that
are also reached from the main menu (Calendar; Inbox and Approvals), so those keep their own
layout and the Settings menu is one click back. A member's address for **Operations** still
works; only the menu entry is hidden.

Pages that have **no menu entry**:

- **Action Center** — `/notifications`. Open it from the bell → **"View all in Action Center"**.
- **Field Ops** — `/field`. Type the address to open it.
- **Directory** — `/directory`. The combined contacts-and-companies page.
- **Accept invitation** — `/invite`. Opened from an invitation.
- **Client portal** — `/portal/…`. For clients, opened from a portal link.
- **Public booking page** — `/book/…`. For the public, opened from a booking link ([§7.7](#p2-77-calendar-and-online-booking)).
- **Manage a booking** — `/booking/manage/…`. For the person who booked, from their own link.

A **not active** item opens a placeholder page headed with the module's name, with a
**"Configuration required"** or **"Backend contract pending"** badge and a **"Module contract"**
card. It says: *"No sample records or simulated writes are shown."* Nothing can be done there.
That is by design, not a fault.

<a id="p2-44-module-quick-reference"></a>

### 4.4 Module quick reference

Full procedures are in [Chapter 7](#p2-7-crm-daily-use).

| Module | What it is for | Key actions | Do **not** | Saved when you see |
|---|---|---|---|---|
| **Today** | The day's work in order, with reasons | Work **"Your plan"** from the top; **"Call"** a lead; tick a task done | Treat an empty plan as broken — it means nothing is waiting | **"Task done"**; lists refresh |
| **Leads** | Website and booking leads, with the speed-to-lead clock | **"Mark contacted"**, **"Close"**, **"Spam"**, **"Export CSV"** | Mark a lead contacted before you have reached them | **"Marked as contacted"** |
| **Tasks** | Every call-back and follow-up | **"New task"**, **"Mark done"**, **"Reopen"** | Leave **"Overdue"** unread | **"Task added"**, **"Changes saved"** |
| **Contacts / Companies** | People and accounts | **"New contact"**, **"New company"**; open a contact to edit, log activity or archive | Expect to edit or archive a *company* — the screens cannot | **"Contact created"**, **"Contact saved"** |
| **Deals / Pipelines** | Revenue opportunities by stage | **"New deal"**, drag a card, the card's **"⋯"** → **"Move to stage"** | Archive a deal you only meant to mark lost | **"Deal created"**, **"Moved to {stage}"** |
| **Website Forms** | The forms on your website and what happens to each lead | **"New form"**, **"Send a test lead"**, copy embed code | Approve auto-reply wording you have not read | **"Test lead processed end to end"** |
| **Calendar** | Online booking: appointments, booking pages, hours | **"Attended"**, **"No-show"**, **"Reschedule"**, **"Cancel"**, **"Review and approve"** | Approve a booking email you have not read | **"Approved and sent"** |
| **Client 360** | One operating page per client | **"New workspace"**; in a workspace, **"New"** → commitment, task, deliverable, request, approval | Create duplicate workspaces for one client | **"Client workspace created"** |
| **Action Center** | Alerts needing follow-through; notification settings | **"Acknowledge"**, **"Resolve"**, preferences | Resolve an alert you have not dealt with | **"Alert resolved"**, **"…preferences were saved"** |
| **Operations** | Recommendations, work queue, recovery, approvals, conversations | **"Approve"** / **"Reject"**, **"Acknowledge"**, **"Resolve"** | Approve something you have not read — there is no confirmation | **"Approved"**, **"Resolved"** |
| **Recovery Proof** | What was recovered, with evidence | Read figures, open a case | Add "potential" and "confirmed" together | Read-only, apart from **"Close case"** |
| **Automations** | Follow-ups that run themselves, with a receipt per run | **"New automation"** → a recipe; edit steps; **"Turn on"**; **"Test with a contact"** | Turn one on without testing it on a contact first | **"Automation saved"**, **"Automation on"** |
| **Client Operations** | Portal links, documents, estimates, appointments | Create records per workspace | Lose a new portal link — it is shown only once | A message per action |
| **Registries** | Integrations and webhooks | **"Connect"**, **"Re-authorize"**, **"Sync"**, **"Disconnect"** | Disconnect Google during an active send | **"Google connected"**, **"Synced Gmail: …"** |
| **Team & Access** | Users, roles, invitations, password resets | **"Invite"**, role menu, **"⋯"** → **"Reset password"** / **"Disable access"** | Post an invite link or a temporary password anywhere public | **"Invitation emailed"** / **"Invitation created"**, **"Member disabled"** |
| **Settings** | Your profile, password, notification and provider status, business name | **"Change password"**, **"Sign out"**, **"Rename"** | Change the *owner* password here — it reverts at the next deploy | **"Password changed"** |
| **Automation & Audit** | The record of every significant change | Read and filter; admin **"Undo"** of approved AI tool writes | Undo without a reason — a reason is required | **"Reversed"** |
| **MCP Console** | Governed AI tool operations | Invoke tools; admin **kill switch** | Flip the kill switch casually | **"Kill switch ON — tools disabled"** |
| **Search (Ctrl/⌘ K)** | Jump to a module | Type a module name | Expect it to find a contact — it cannot | — |
| **Import / Export** | — | Only **Leads** → **"Export CSV"** in the screens | — | A `leads.csv` download |
| **Reporting** | — | **Not active** (Recovery Proof is the live report) | — | — |

---

<a id="p2-5-google--gmail-setup"></a>

## 5. Google / Gmail Setup

<a id="p2-51-what-the-google-connection-does"></a>

### 5.1 What the Google connection does

One Google consent connects **two** rows at once: **Gmail** and **Google Calendar**.
Verified (code). With the connection active, the CRM:

- **reads Gmail** — the 25 most recent messages' headers (sender, recipients, subject, labels and
  snippet), matched to your contacts by email address. They appear on a client's **Client 360** →
  **Activity** → **"Recent email threads"** — **only when** the matched contact belongs to a
  company that has a Client 360 workspace.
- **captures replies** — every 30 minutes (at :10 and :40 past the hour) it checks the inbox for
  the last 7 days and attaches replies to the conversations they answer ([§6](#p2-6-email-production-verification)).
- **sends email** — only messages a human approved, and only through the connected mailbox
  ([§6](#p2-6-email-production-verification)).
- **reads Google Calendar** — the next 25 events, matched to contacts by attendee email. They
  appear under **Client 360** → **Activity** → **"Upcoming meetings"**, with the same
  company-and-workspace condition. Online booking also leaves out times when the connected
  calendar is busy ([§7.7](#p2-77-calendar-and-online-booking)).

Only **admins** can connect, re-authorize, sync or disconnect. Members see **"Admin manages"**.

<a id="p2-52-exact-google-permissions-scopes-the-crm-requests"></a>

### 5.2 Exact Google permissions (scopes) the CRM requests

Verified (code), from `GOOGLE_SCOPES` in `backend/server.py`:

| Scope | What Google shows the user (wording varies) | Why ClientVerse needs it |
|---|---|---|
| `https://www.googleapis.com/auth/gmail.readonly` | View your email messages and settings | Gmail sync, reply capture, and the duplicate check before every send |
| `https://www.googleapis.com/auth/gmail.send` | Send email on your behalf | Sending approved messages. It cannot read, delete or change mail. |
| `https://www.googleapis.com/auth/calendar.readonly` | See your calendars and events | Meetings on Client 360; busy times for online booking |
| `https://www.googleapis.com/auth/userinfo.email` | See your primary Google Account email address | Showing which mailbox is connected |
| `openid` | Associate you with your personal info on Google | Standard sign-in identity |

How the request is made:

- ClientVerse requests **offline access**, so it can refresh the permission without you present.
- It forces Google's consent screen every time.
- It uses PKCE and a one-time `state` value.
- **The consent must be finished within 10 minutes**, or the attempt expires.
- **Since 2026-10-19 (PR #42) the CRM records the permissions Google actually granted**, not the
  ones it asked for. Sending checks that record for `gmail.send`. A connection made before that
  date carries the full requested list whatever Google granted, so **reconnect Google once**
  ([§5.6](#p2-56-re-authorize-google) or [§5.7](#p2-57-disconnect-safely-and-when-it-is-required)) to make
  the record true.

<a id="p2-53-where-the-google-controls-are"></a>

### 5.3 Where the Google controls are

- **Path A:** **Settings** → **"General"** → the **"Integrations"** section lists **Gmail**,
  **Google Calendar** and **Stripe** with a status. Admins see **"Connect"** or **"Manage"** on
  each row, and **"View integrations"** at the bottom. All of them open the Registries page.
- **Path B:** **Settings** → **Connections** → **"Integrations"** (or **"Email sending"**).

Either path lands on the **Registries** page, on the **"Integrations"** tab (the first of
**"Integrations"**, **"MCP Servers"**, **"Plugins"**, **"Webhooks"**). The tab shows:

- a **"Status honesty"** note
- one row each for **Gmail**, **Google Calendar** and **Stripe**
- below them, **"Governed capability contracts"** — catalogue records, for information

The Gmail row's description still reads *"Read-only message + thread metadata…"*. That text is
older than the send feature; the connection also carries send permission when Google granted it
([§5.2](#p2-52-exact-google-permissions-scopes-the-crm-requests)).

<a id="p2-54-read-the-connection-status"></a>

### 5.4 Read the connection status

| Registries status | Settings label | Meaning | Buttons (admin) | Your action |
|---|---|---|---|---|
| **"Not connected"** | Not connected | No Google permission is stored | **"Connect"** | [§5.5](#p2-55-connect-google-first-time) |
| **"Connecting…"** | Connecting… | A sync is running (it shows briefly during every sync), or a consent was started and never finished — for example cancelled at Google | **"Sync"**, **"Disconnect"** | If still shown after 10 minutes: full reset ([§5.7](#p2-57-disconnect-safely-and-when-it-is-required)) |
| **"Connected"** | Connected | The permission is active | **"Sync"**, **"Disconnect"** | None. Confirm send permission ([§5.8](#p2-58-verify-that-gmailsend-was-actually-granted)) |
| **"Degraded"** | Needs attention | The last sync failed for a non-permission reason | **"Sync"**, **"Disconnect"** | **"Sync"** once. If still degraded, escalate. |
| **"Needs auth"** + **"Re-authorize"** tag | Needs auth | Google refused to refresh the permission (expired or revoked) | **"Re-authorize"**, **"Sync"**, **"Disconnect"** | [§5.6](#p2-56-re-authorize-google) |
| **"Error"** | Error | Connecting failed while exchanging the Google code | **"Reconnect"**, **"Sync"**, **"Disconnect"** | **"Reconnect"**. If it repeats, see [§5.9](#p2-59-google-troubleshooting). |

Other parts of the row:

- **"Stale"** tag — connected, but no successful sync for more than 24 hours.
- **Red line under the row** — the last error, for example `token_refresh_failed:400`.
- **The Google address** (small monospaced text) — the mailbox connected.
- **Small grey tags** (`gmail.readonly`, `gmail.send`, …) — the permissions recorded on the
  connection. The row shows **at most four**, so a tag that is not shown may still be recorded.
  See [§5.8](#p2-58-verify-that-gmailsend-was-actually-granted).
- **"Last sync …"** or **"No successful sync yet"**.

<a id="p2-55-connect-google-first-time"></a>

### 5.5 Connect Google (first time)

**One-time prerequisites (owner, in Google Cloud)** — governing-document owner action O-01:

- **Recorded done:** `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set in Railway. The boot log
  line `Registered outbound channel provider: gmail` (Verified (live, 2026-10-19)) confirms the
  server sees them.
- The OAuth client's **authorized redirect URI** must be exactly the Railway variable
  `GOOGLE_REDIRECT_URI`, which since 2026-10-19 is
  `https://crm.clientverse.io/api/integrations/google/callback`. The owner's reconnection at
  02:02Z that day succeeded through it, which shows Google accepts it.
- The **Gmail API** and the **Google Calendar API** must be enabled.
- The **OAuth consent screen** must list the scopes in [§5.2](#p2-52-exact-google-permissions-scopes-the-crm-requests).
  If its publishing status is **Testing**, the Google account you connect must be listed as a test
  user.
- The Google Cloud project's name is UNVERIFIED — OWNER/ENGINEERING INPUT REQUIRED. The owner
  should record it in [Appendix D](#p2-appendix-d-configuration-and-secrets-register).

**Steps**

1. Sign in as an admin. Open **Registries** → **Integrations**.
2. On the **Gmail** row, click **"Connect"**. The **Google Calendar** row's **"Connect"** does
   the same thing.
3. Google opens. Choose the Google account whose mailbox the CRM should use. **This mailbox becomes
   the "From" address of every email the CRM sends.**
4. If Google warns that it hasn't verified the app, check that the app name on the screen is the
   one your organization created in Google Cloud. Only then continue. If the name is unfamiliar,
   stop and escalate.
5. On the consent screen, read the permissions. **If Google shows a tick-box for each permission,
   tick every one** — especially the one to **send email on your behalf**. Then click
   **Continue / Allow**.
6. You return to **Registries** → **Integrations** with the message **"Google connected"**.
7. **Check:** both **Gmail** and **Google Calendar** show **"Connected"** and your Google address.
8. On the Gmail row, click **"Sync"**.
   - **Check:** the message **"Synced Gmail: N record(s) matched"**, and **"Last sync …"** on the row.
   - N can be 0. That only means none of the 25 newest emails involve a contact's address.
   - N counts matches to contacts. An email shows on Client 360 only when that contact's company
     has a workspace.
9. Verify send permission ([§5.8](#p2-58-verify-that-gmailsend-was-actually-granted)).

**If it fails**

- **"Google authorization failed"** — you cancelled or refused, or Google returned an error. The
  rows may be left on **"Connecting…"**. Do the full reset in [§5.7](#p2-57-disconnect-safely-and-when-it-is-required).
- **"Authorization link expired — try again"** — more than 10 minutes passed. Start again from
  step 2.

<a id="p2-56-re-authorize-google"></a>

### 5.6 Re-authorize Google

Use this when the Gmail or Google Calendar row shows **"Needs auth"** or **"Error"**.

1. On the **Gmail** row, click **"Re-authorize"** (or **"Reconnect"** on an **"Error"** row).
2. Complete the Google consent exactly as in [§5.5](#p2-55-connect-google-first-time), steps 3–6.
3. **Check:** **"Google connected"**. Both rows read **"Connected"**, with no red error line.
4. Click **"Sync"** on the Gmail row to confirm.

If the rows return to **"Needs auth"** within about a week, see
[§5.9](#p2-59-google-troubleshooting) → *Token refresh returns 400*.

<a id="p2-57-disconnect-safely-and-when-it-is-required"></a>

### 5.7 Disconnect safely, and when it is required

**Disconnect first, then connect, when:**

- the row shows **"Connected"** or **"Degraded"** but you need a *fresh* permission. There is no
  **"Re-authorize"** button in those states. This applies when:
  - the connection was made before 2026-10-19, so its recorded permissions are not the ones Google
    granted ([§5.2](#p2-52-exact-google-permissions-scopes-the-crm-requests))
  - you left **send email on your behalf** unticked
  - you want to use a different Google mailbox
- the rows are stuck on **"Connecting…"**
- the connection keeps looping back to **"Needs auth"** or **"Error"**

**Full reset procedure**

1. Tell your team that Gmail sync, reply capture and outbound email pause until you reconnect,
   and that email sending must be turned on again afterwards ([§5.10](#p2-510-turn-email-sending-on-or-off)). Do this when no approved
   email is waiting to be sent.
2. On the **Gmail** row, click **"Disconnect"**. **Check:** **"Disconnected Gmail"**.
3. On the **Google Calendar** row, click **"Disconnect"**. **Check:**
   **"Disconnected Google Calendar"**.
   - **Why both:** both rows share one saved Google permission. The CRM revokes it at Google,
     and deletes its saved copy, only when you disconnect the second row. While either row is
     still **"Connected"**, it keeps working.
     - Disconnecting **Gmail** also turns **email sending** off ([§5.10](#p2-510-turn-email-sending-on-or-off)).
     - Disconnecting both rows always leaves a clean slate.
4. (Recommended for a stale or looping permission.) Open **Google Account** → **Security** →
   the list of third-party apps and services with access to your account. Find your ClientVerse
   app and remove its access. ClientVerse already asks Google to revoke on Disconnect; this
   confirms it.
5. **Check:** both rows read **"Not connected"**, with no Google address shown.
6. Connect again ([§5.5](#p2-55-connect-google-first-time)).

**What Disconnect does not do:** it does not delete email and meeting records already shown on
Client 360, and it does not delete conversations or messages.

<a id="p2-58-verify-that-gmailsend-was-actually-granted"></a>

### 5.8 Verify that gmail.send was actually granted

Work down this list. Each check is stronger than the one before it.

1. **The CRM's record.** On a connection made on or after 2026-10-19, the recorded permissions are
   the ones Google granted, and sending is refused unless `gmail.send` is among them. The row
   shows at most four tags, so look for `gmail.send` there but do not treat its absence as
   proof. On an older connection the tags only show what was requested — reconnect first.
2. **Google's record (owner-verifiable).**
   1. Signed in to the *connected* Google account, open **Google Account** → **Security** → the
      list of third-party apps and services with access to your account.
   2. Open your ClientVerse app.
   3. Its access list should include **sending email on your behalf** (Gmail). If it only lists
      reading email, the permission is read-only: do the full reset in [§5.7](#p2-57-disconnect-safely-and-when-it-is-required)
      and tick every box.
3. **The CRM's authorization view.** Open **Operations** → **"Recovery strategies"** tab. The amber
   box **"Outbound channels not authorised"** lists every channel that cannot send (**SMS** and
   **Phone** always appear; no provider exists for them). Then read:
   - **"Email — No connected email provider (gmail is not connected)."** — the Gmail row is not
     **"Connected"**. Re-authorize or reconnect.
   - **"Email — gmail is connected, but no integration record marks it configured for this tenant,
     so outbound email is not certified."** — the Google side is fine, but **email sending** is
     off. An admin turns it on with a test email ([§5.10](#p2-510-turn-email-sending-on-or-off)).
   - **Email not listed at all** — the email channel is authorized. (This view does not check
     `gmail.send`; checks 1 and 2 do.)
4. **Definitive proof.** A real message reaches status **"sent"** ([§6](#p2-6-email-production-verification)).
   Without `gmail.send` it is refused instead, with *"The Gmail connection for this tenant is
   read-only … Reconnect Google and grant send access."*

<a id="p2-59-google-troubleshooting"></a>

### 5.9 Google troubleshooting

**Token refresh returns 400 (Needs auth).**

- **Seen live on 2026-09-30 at 16:08 UTC.** During the scheduled sync, Railway logged
  `POST https://oauth2.googleapis.com/token` → `400 Bad Request`, twice (Gmail and Calendar).
- **What it means:** Google rejected the saved permission. The CRM marks both rows
  **"Needs auth"** and records `token_refresh_failed:400`.
- **Common causes (Google-side):**
  - the permission was revoked in the Google account
  - the Google account's password changed (Google revokes Gmail permissions when it does)
  - the permission went unused for months
  - the consent screen's publishing status is **Testing** — Google then expires permissions after
    about **7 days**
  - the OAuth client secret was rotated in Google Cloud
- **Owner action:** Re-authorize ([§5.6](#p2-56-re-authorize-google)).
- **It returns roughly every 7 days:** the consent screen is almost certainly in **Testing**. That
  is an owner decision in Google Cloud — publish the app (Gmail scopes may need Google's
  verification), or accept a weekly re-authorization.
- **The reconnect itself ends in "Error"** (`token_exchange_failed`): the `GOOGLE_CLIENT_SECRET`
  in Railway, or the redirect URI, no longer matches Google Cloud. Escalate: the owner updates the
  Railway variable with engineering.
  - A reconnect that *succeeds* proves the secret matches, because connecting uses the same
    secret as refreshing.

**Reconnect loop** — you connect, return, and the rows stay on **"Connecting…"** or go straight
to **"Error"**.

1. Do the full reset in [§5.7](#p2-57-disconnect-safely-and-when-it-is-required), including step 4.
2. Connect again, finishing within 10 minutes, and tick every permission.
3. If Google itself shows a `redirect_uri_mismatch` error, the Google Cloud redirect URI is
   wrong ([§5.5](#p2-55-connect-google-first-time) prerequisites). That is an owner fix in Google Cloud.
4. If the row shows **"Error"** with `token_exchange_failed`, the client secret or redirect URI
   does not match. Escalate with a screenshot.

**Stale permission** — **"Connected"** but tagged **"Stale"**, or no new email on Client 360.

1. Click **"Sync"** on the row.
2. If the red error line appears, act on it (above).
3. If there is still no new data and no error, do the full reset.

**Other messages**

| Message | Meaning | Who fixes it |
|---|---|---|
| **"Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."** | Railway variables missing | Owner in Railway, with engineering |
| **"Google OAuth redirect is not configured. Set GOOGLE_REDIRECT_URI or PUBLIC_BACKEND_URL."** | No usable redirect address | Engineering |
| "Access blocked" (at Google) | Your account is not a test user, or the app is restricted | Owner in Google Cloud |
| **"Integration center unavailable"** | The Registries page could not load connections | Reload; if it repeats, escalate |
| "Sync failed: rate_limited" | Google throttled requests | Wait 15 minutes and retry |
| "Sync failed: not_connected" | No stored permission | Connect ([§5.5](#p2-55-connect-google-first-time)) |

**Who does what**

| Owner can do it | Needs engineering |
|---|---|
| Connect, Re-authorize, Sync, Disconnect | Changing `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` or `PUBLIC_BACKEND_URL` (with the owner) |
| Google Cloud consent screen, test users, redirect URI, publishing status; turning email sending on or off ([§5.10](#p2-510-turn-email-sending-on-or-off)) | — |
| Removing app access in the Google account | Any error that survives a full reset |

<a id="p2-510-turn-email-sending-on-or-off"></a>

### 5.10 Turn email sending on or off

Outbound email needs two things: Gmail **"Connected"** with send permission
([§5.8](#p2-58-verify-that-gmailsend-was-actually-granted)), and **email sending** turned on. Turning
it on is the organization's decision that email may leave the CRM. Each email to a client still
needs that contact's consent and a human approval of its exact words.

**Turn it on (admin):**

1. **Registries** → **"Integrations"**. The Gmail row reads **"Connected"**.
2. Under it, the strip reads **"Email sending off"**. Click **"Send test & turn on"**.
3. The CRM sends one test email from the connected mailbox **to itself**
   (*"ClientVerse: test message before email sending is turned on"*). No client receives it.
4. **Check:** the message *"Test email sent to \<mailbox\>. Email sending is on."*, and the strip
   reads **"Email sending on"**, with the time and who turned it on. The test email is in that
   mailbox's inbox and **Sent**.
5. If Gmail refuses, sending stays off and the message says why — for example a connection
   without send permission: do the full reset in [§5.7](#p2-57-disconnect-safely-and-when-it-is-required)
   and tick every box.

**Turn it off (admin):** click **"Turn off sending"** on the same strip. Email already approved is
then refused until sending is turned on again.

**It turns itself off when the proof no longer holds:**

- Gmail is disconnected.
- Google is reconnected **without** permission to send, or with a **different** mailbox.

Every change is recorded in **Automation & Audit** as `integration.sending_enabled` or
`integration.sending_disabled`, with who made it and why.

---

<a id="p2-6-email-production-verification"></a>

## 6. Email Production Verification

<a id="p2-61-read-this-first--current-status"></a>

### 6.1 Read this first — current status

**Status on 2026-10-19:** three things decide whether email can go out. The first is done; the
other two need different people:

1. **The Google permission — done.** Verified (live, 2026-10-19 02:02 UTC): the owner reconnected
   Google on `crm.clientverse.io`, and Google granted `gmail.readonly`, `gmail.send` and
   `calendar.readonly` (Railway log of the Google callback). If the Gmail row ever shows
   **"Needs auth"** again: [§5.6](#p2-56-re-authorize-google) or
   [§5.7](#p2-57-disconnect-safely-and-when-it-is-required).
2. **No screen lets you write your own email to a contact, or record a contact's consent.**
   - **Operations** → **"Conversations"** can only *read* a thread, **"Hand to human"** /
     **"Hand to agent"**, and **"Close"**.
   - Creating a conversation, recording consent, drafting, requesting approval and sending exist
     only as server API calls. Verified (code).
   - Two screens release emails the CRM itself wrote, once reasons 1 and 3 are cleared:
     **Calendar** booking emails (**"Review and approve"** → **"Approve and send"**,
     [§7.7](#p2-77-calendar-and-online-booking)) and a **Website Forms** auto-reply whose wording an
     admin approved ([§7.6](#p2-76-website-forms)).
   - **Engineering-assisted:** for the full send / duplicate / reply test below, an engineer
     performs the API steps ([Appendix C](#p2-appendix-c-engineer-assisted-email-verification)) while
     the owner approves and verifies in the screens.
3. **Email sending must be turned on.**
   - The CRM lets email go out only when the organization's **Gmail catalogue record** (shown under
     **Registries** → **"Governed capability contracts"**) is certified.
   - An admin certifies it with **"Send test & turn on"** on the Gmail row: Gmail must accept a
     test email from the connected mailbox to itself first ([§5.10](#p2-510-turn-email-sending-on-or-off)). **Owner.**
   - Until then, every send is refused with *"…no integration record marks it configured for
     this tenant, so outbound email is not certified."*

Reply capture also needs the scheduler, which runs inside the CRM ([§11](#p2-11-scheduler--automations)).

**How do I send a real email?** Once email sending is on: by approving a booking email or form
auto-reply, or through the engineer-assisted procedure below for an email you write yourself. The Gmail
**"Sync"** button does not send anything; it is a read-only mirror of the inbox. Invitation and
alert emails use a separate delivery service, not Gmail ([§10.6](#p2-106-email-notifications-and-ai)).

<a id="p2-62-result-definitions"></a>

### 6.2 Result definitions

| Result | Means |
|---|---|
| **PASS** | Every expected result in the step was observed, and its evidence was captured ([§6.8](#p2-68-what-counts-as-pass-evidence)). |
| **FAIL** | The step ran, and the CRM or Google did something other than expected — for example two copies arrived, or a reply landed on the wrong conversation. |
| **BLOCKED** | The step could not run because a prerequisite is missing (for example **"Needs auth"**, or the certification gate). Record the exact blocking message. |
| **NOT TESTED** | Not attempted yet. |

<a id="p2-63-prerequisites-owner-verifiable"></a>

### 6.3 Prerequisites (owner-verifiable)

- [ ] The **Gmail** row is **"Connected"**, shows the sending mailbox, and was connected on or
      after 2026-10-19 ([§5.4](#p2-54-read-the-connection-status)).
- [ ] Google shows the send permission ([§5.8](#p2-58-verify-that-gmailsend-was-actually-granted), check 2).
- [ ] **Operations** → **"Recovery strategies"** does **not** list **Email** as not authorised ([§5.8](#p2-58-verify-that-gmailsend-was-actually-granted), check 3).
- [ ] The scheduler is healthy ([§11.4](#p2-114-verify-that-automation-is-healthy)). Reply capture depends on it.
- [ ] A **test contact** exists: **Contacts** → **"New contact"** → name `CV Email Test`, and an
      **Email** you control that is **not** the connected mailbox (for example a personal
      secondary address). The reply must come *from* the contact *to* the connected mailbox.
- [ ] An engineer is available for the API steps ([Appendix C](#p2-appendix-c-engineer-assisted-email-verification)).

<a id="p2-64-procedure-a--send-one-real-outbound-email"></a>

### 6.4 Procedure A — send one real outbound email

1. **Engineer:** in Appendix C, create an email conversation with the test contact, record consent
   (**granted**, basis "Owner's own test mailbox"), draft a short message, and request approval.
2. **Owner:** open **Operations** → **"Approvals"**. Find the row titled
   **"Send email message: \<subject\>"**.
   1. Read the summary: it shows the exact text that will be sent (cut at 500 characters).
   2. If the row says **"Approving this will not unblock it — …"**, note the reason. The send will
      be refused (BLOCKED).
   3. Click **"Approve"**. **Check:** **"Approved"**.
3. **Engineer:** send the message (Appendix C, step 6).
4. **Owner — verify it left the CRM:**
   1. **Operations** → **"Conversations"** → open the thread.
   2. The **outbound** message shows status **"Sent"**.
   3. **Automation & Audit** shows an event `communication_message.sent`.
5. **Owner — verify Google accepted it:** in the connected mailbox, Gmail's **Sent** folder holds
   the message.
6. **Owner — verify delivery:** the test mailbox receives it. Check spam too. Note the time.

<a id="p2-65-procedure-b--duplicate-protection"></a>

### 6.5 Procedure B — duplicate protection

1. **Engineer:** repeat the send call for the **same** message (Appendix C, step 7).
2. **Expected:** the CRM refuses — HTTP 409, `message_not_dispatchable`,
   *"…this one is 'sent'"*. The message stays **"Sent"**.
3. **Owner:** wait 10 minutes. The test mailbox has **exactly one** copy, and Gmail **Sent** holds
   exactly one.
4. **PASS:** refused, and exactly one copy. **FAIL:** a second copy arrived.

The deeper retry protection is automatic. Before every dispatch the CRM asks Gmail whether it
already holds that message, using a fixed Message-ID. It is covered by automated tests; this step
proves the guarantee you can see.

<a id="p2-66-procedure-c--capture-the-reply"></a>

### 6.6 Procedure C — capture the reply

1. **Owner:** from the test mailbox, **Reply** to the email received. Keep the subject and do not
   change recipients.
2. Wait for the next reply sweep. The CRM's built-in scheduler runs `inbound-email` at **:10 and
   :40** past every hour (UTC), so allow up to **35 minutes**. To start it at once, use GitHub →
   **Actions** → **Scheduled jobs** → **"Run workflow"** → jobs: `inbound-email` (only while that
   optional workflow is configured, [§11.7](#p2-117-run-the-jobs-by-hand)).
3. **Owner — verify capture:** **Operations** → **"Conversations"** → the **same** thread shows a
   new **inbound** message with status **"Received"** and your reply text.
4. **Owner — verify matching:** the reply is on the *same* conversation, not a new one.
   - The CRM matches on Gmail's thread, then on the reply headers, then (only when unambiguous) on
     the sender.
   - An ambiguous reply is **parked for a person** rather than guessed. If the reply is missing
     after 35 minutes, the engineer checks the unmatched queue (Appendix C, step 9).
5. **Contact history:** open **Contacts** → `CV Email Test` → **"Activity"**. The history shows an
   entry *"CV Email Test emailed you"* for the reply.
   - If the conversation is linked to a client workspace, **Client 360** → **"Timeline"** also shows
     the event.
   - **Automation & Audit** always shows `communication_message.received`.
6. **Recovery Proof** → **"Replies received"** counts only replies on recovery cases. A standalone
   test conversation will not change it — do not use it as test evidence.

<a id="p2-67-where-failures-surface"></a>

### 6.7 Where failures surface

| Where | What you see | Meaning |
|---|---|---|
| **Operations** → **"Approvals"** row | **"Approving this will not unblock it — …"** | A prerequisite blocks the send (not connected, consent, certification) |
| **Operations** → **"Conversations"** | Figure **"Blocked messages"** above 0; the message status **"Blocked"**, with the reason | The CRM refused before contacting Google, and named why |
| Same, status **"Failed"** | Only the status. The screen does not show Google's reason; an engineer reads it from the message's `error` field (`GET /api/messages/<id>`) — e.g. *"Gmail rejected the message with HTTP 403…"* | Google refused. A 403 usually means the send permission is missing — full reset ([§5.7](#p2-57-disconnect-safely-and-when-it-is-required)) |
| Same, status **"Outcome unknown"** | Only the status. Google did not confirm either way | **Never re-send.** The reconcile sweep (:10/:40) asks Gmail. If Google access is revoked or refused, the message deliberately stays "Outcome unknown" until access is restored — a refused lookup never counts as "not sent". Escalate if it persists after 1 hour with Google **"Connected"**. |
| **Calendar** → an appointment | **"Waiting for approval"**, **"Could not send"**, or *"Email isn't connected, so nothing was emailed."* | A booking email awaits an admin, failed, or the email channel is not authorised ([§7.7](#p2-77-calendar-and-online-booking)) |
| **Registries** → Gmail row, red line | e.g. `token_refresh_failed:400` | Permission problem ([§5.9](#p2-59-google-troubleshooting)) |
| **Operations** → **"Recovery strategies"** amber box | **"Email — …"** | Channel not authorised ([§5.8](#p2-58-verify-that-gmailsend-was-actually-granted)) |
| **Automation & Audit** | `communication_message.refused` | A send was refused; the reason is on the message |
| `/api/cron/health` | `last_failed_job` is `inbound-email` or `reconcile-unknown` | Reply capture or reconciliation failed ([§11](#p2-11-scheduler--automations)) |

<a id="p2-68-what-counts-as-pass-evidence"></a>

### 6.8 What counts as PASS evidence

- **Outbound:** screenshots of the conversation showing **"Sent"**, of Gmail **Sent**, and of the
  received email with its time. The engineer records the message's `provider_message_id` and
  `rfc822_message_id`. These are identifiers, not secrets.
- **Duplicate:** the refusal (HTTP 409 text) and a screenshot showing a single copy.
- **Inbound:** a screenshot of the same thread with the **inbound** / **"Received"** message, the
  `communication_message.received` audit event, and the contact's **"Activity"** history.
- **Redact** personal email addresses before sharing screenshots outside the company.

---

<a id="p2-7-crm-daily-use"></a>

## 7. CRM Daily Use

Each section gives: **Purpose**, **Where**, **Common actions**, **Common mistakes**, and **Saved when**.

<a id="p2-71-today"></a>

### 7.1 Today

- **Purpose:** your daily starting point — what to do next and why, new leads, appointments,
  tasks, pipeline, clients, recommendations and alerts ([§4.2](#p2-42-what-you-see-after-sign-in-today)).
- **Where:** main menu → **"Today"**; or click the ClientVerse logo.
- **Common actions:**
  1. Work **"Your plan"** from the top. Each item opens the lead, task, deal, client or approval it
     is about; its grey line says why it is on the plan.
  2. In **"New leads waiting"**, click **"Call"** (or the text or email button) to reach the person
     from your phone or computer. Then log the call on their record, or mark the lead in **Leads**:
     calling from here records nothing by itself.
  3. In **"Tasks"**, tick a task to mark it done.
  4. In **"Next best actions"**, choose **"Accept"**, **"Done"**, **"Snooze"** (a day) or
     **"Not relevant"**.
  5. Under **"Operational alerts"**, click **"Scan now"** for a fresh alert check. Use the ✓ and ✕
     icons to acknowledge or resolve.
- **Common mistakes:**
  - Treating empty sections as a fault.
  - Expecting **"Connection health"**, or approval items on the plan, to show for members — they are
    admin-only.
  - Expecting **"Call"** to mark the lead contacted. It only dials.
- **Saved when:** **"Task done"**, **"Alert scan complete (N new)"**; recommendation buttons change
  the list, and only failures show a message (the server's reason, **"The task was not updated"** or
  **"Could not record that decision"**).

<a id="p2-72-leads"></a>

### 7.2 Leads

- **Purpose:** every lead from your website forms and online booking, with its speed-to-lead
  clock and what the CRM did automatically.
- **Where:** main menu → **"Leads"** (the red count is new leads nobody has contacted). New
  teammates land here after accepting an invitation.
- **Common actions:**
  1. Read the tabs **"New"**, **"Contacted"**, **"Closed"**, **"Spam"**, **"All"**. Search by name,
     email, phone, address or MLS number; filter by form (**"All forms"**). The list refreshes
     every 30 seconds.
  2. Click a lead to open it. Use **"Call …"** / **"Text"** to reach the person from your phone,
     then **"Mark contacted"**. Or open the contact (**"Open contact to log a call"**) and log what
     happened.
  3. **"Close"** a lead that is finished, **"Spam"** junk, **"Reopen"** a closed one.
  4. **"Export CSV"** downloads the leads in the current view as `leads.csv`.
- **Existing clients:** a form or booking from someone you already serve (their company has a
  Client 360 workspace, or they are on a won deal) is marked **"Existing client"**. It opens no new
  deal, and its task reads **"Reply to client: …"** instead of **"Call new lead now: …"**.
- **How the clock works:** every new lead gets a call-back task in **Tasks** (due 5 minutes after
  arrival by default) and an alert. Logging a call, text, email or meeting on the contact, or
  ticking that task done, marks the lead contacted. A note does not. Verified (code).
- **Common mistakes:**
  - Marking a lead contacted before you have reached them — it stops the clock.
  - Marking a real person as spam.
  - Treating a lead tagged **"Test lead"** as real: it came from **"Send a test lead"**
    ([§7.6](#p2-76-website-forms)).
- **Saved when:** **"Marked as contacted"**, **"Lead marked closed"**, **"Lead marked spam"**.

<a id="p2-73-tasks"></a>

### 7.3 Tasks

- **Purpose:** every call-back and follow-up in one list, with what is late at the top.
- **Where:** main menu → **"Tasks"** (the count is your overdue tasks, plus overdue tasks nobody
  owns — the **"Overdue"** tab of the default view).
- **Common actions:**
  1. Read the tabs **"Overdue"**, **"Today"**, **"Upcoming"** and **"Done"** (finished tasks stay
     7 days). Admins can switch between **"My tasks"** and **"Everyone"**.
  2. **"New task"**: **"What needs doing"** (required), **"Who it's about (optional)"**, a due date
     and time, **"Assign to"**, **"Notes (optional)"** → **"Add task"**. Unassigned tasks can be
     taken by anyone on the team.
  3. Open a task to change it (**"Save changes"**), **"Mark done"** or **"Reopen"**.
- **Common mistakes:** leaving a task unassigned when one person should own it.
- **Saved when:** **"Task added"**, **"Changes saved"**; **"Undo"** on the message reverses a tick.

<a id="p2-74-contacts-and-companies"></a>

### 7.4 Contacts and Companies

- **Purpose:** the people and accounts behind every relationship.
- **Where:**
  - main menu → **"Contacts"**
  - one page with the tabs **"Companies"** and **"Contacts"**
  - the top-bar **"Create"** button also creates both
- **Common actions:**
  1. **"New company"**: **"Company name"** (required), **"Industry"**, **"Website"**,
     **"Client tier"** (Standard / Growth / Enterprise) → **"Create company"**.
  2. **"New contact"**: **"Name"** (required), **"Email"**, **"Phone"**, **"Company"**,
     **"Role"**, **"Influence"** → **"Create contact"**. Add the email address: Gmail and Calendar
     matching depend on it.
  3. Search (**"Search name, phone, email…"** / **"Search companies…"**), filter by company or
     tier, and sort.
  4. **Views of the contact list.** The row above the list holds the views:
     - **"All contacts"**, **"Leads"**, **"Customers"**, **"My contacts"** and **"No company"** are
       built in. **"Leads"** and **"Customers"** go by the **Lifecycle** stage (item 6).
     - **"Filter"** → choose a field → a condition (**"is"**, **"is not"**, **"contains"**,
       **"is empty"**, **"is not empty"**, **"more than"**, **"less than"**, **"before"**,
       **"after"**) → a value → **"Apply"**. Each filter shows as a chip under the toolbar; **"×"**
       removes it and **"Clear filters"** removes them all. A list shows only people who meet
       *every* filter. Your own fields (item 8) can be filtered too.
     - **"Columns"** chooses what the list shows. **"Manage fields…"** at the bottom opens
       **Settings → Fields**.
     - **"+ Save view"** → **"Name"** → **"Share with the team"** (on: everyone sees it; off: only
       you, marked with a lock) → **"Save view"**. It keeps the filters, the columns and the order.
       Change an open saved view and **"Save changes"** appears; the **"⋯"** beside it deletes it.
       Only the person who made a view, or an admin, can change or delete it.
     - The address of the page names the open view (`/contacts?view=…`), so a view can be
       bookmarked or sent to a colleague who can see it.
  5. **Open a contact** (side panel):
     - tabs **"Activity"**, **"Deals"**, **"Tasks"**, **"Website requests"**, and the
       **"Details"** panel
     - **"Edit"** (or **"Edit · add phone"**) → change details, including **"Lifecycle stage"** →
       **"Save changes"**
     - **"More fields"** → **"Edit"** → fill in your own fields → **"Save fields"**. Each value is
       checked against its field: a number field takes only a number, a choice only one of its
       choices.
     - **"Activity"** → **"Log what happened"**: Call, Text, Email, Meeting or Note. Logging an
       email records it; *nothing is sent to them*.
     - **"Archive contact"** hides them from the list (nothing is deleted). To bring one back,
       turn on **"Show archived"**, open them, and click **"Restore"**.
  6. **Lifecycle stage** — where a person stands with you: **Lead**, **Qualified**, **Customer**,
     **Former customer**, **Partner** or **Other**. It is shown in the **"Details"** panel and as a
     list column. The CRM sets it in two cases and never overrides a stage someone chose:
     - a person who first arrives through a website form or booking page starts as **Lead**;
     - when a deal is won, everyone on it who is a **Lead**, **Qualified** or not yet staged
       becomes **Customer**. A **Partner** stays a **Partner**.
  7. **Open a company** (side panel): tabs **"Contacts"**, **"Deals"**, **"Client 360"**, and the
     **"Details"** panel. Only **"More fields"** can be edited there.
  8. **Your own fields** (**Settings** → **Workspace** → **"Fields"**, `/settings/fields`; also **"Columns"** →
     **"Manage fields…"**). An admin adds the details the business tracks on every contact,
     company or deal:
     1. Choose the tab **"Contacts"**, **"Companies"** or **"Deals"** → **"New … field"**.
     2. **"Name"** (for example *Budget*), **"Type"** (Short text, Long text, Number, Date, Choice,
        Yes / no, Email, Phone, Web address), for a **Choice** its **"Choices, one per line"**, and
        optional **"Help text"** → **"Add field"**.
     3. The field appears on every record under **"More fields"**, in **"Filter"** and in
        **"Columns"**.
     - The **type cannot be changed** once the field exists, so stored values always fit it.
       Renaming keeps the values.
     - The archive button hides a field from records and keeps every value; **"Show archived"** →
       the restore button brings it back. A field is never deleted.
     - **"API key"** (`custom_fields.cf_…`) is the name integrations and the API use.
     - Members see this page but cannot change it.
  9. **Companies fill themselves in.** When a form or booking page asks **"Company"**, the person
     is linked to that company, which is created if it doesn't exist yet. A person whose work email
     matches a company's domain or website is linked to it. Personal addresses (Gmail, Outlook,
     iCloud and similar) never link anyone to a company.
  10. **"Clean up"** card, at the top of the **"Contacts"** tab, appears only when there is something
     to tidy:
     - **"Create and link"** — companies people typed into forms that don't exist yet are created,
       and those people are linked to them.
     - **"Link to company"** — people whose work email matches a company are linked to it.
     - **"Review and merge"** — people entered twice (same email, or the same name). Choose the
       record to keep → **"Merge into the selected record"**. Its deals, tasks, notes, website
       requests, appointments and conversations move to the kept record, its empty fields are
       filled from the other, and the other is archived (turn on **"Show archived"** to see it).
       Nothing is deleted. If a merge is interrupted, running it again finishes it.
     - **"Set from history"** — people with no lifecycle stage get one from what has happened:
       on a won deal, or at a company with a Client 360 workspace → **Customer**; on an open deal,
       or with a website request → **Lead**. Anyone else is left for you to set. A stage set by
       hand is never changed.
- **Common mistakes:**
  - **Companies cannot be edited, archived or deleted from the screens.** Type carefully.
    Engineering can edit or archive a company through the server. Nothing can be deleted at all.
  - Creating the same company twice — search first. Two people already entered twice can be
    merged with **"Review and merge"**.
  - Leaving out a contact's email, which stops email and calendar matching.
  - The contact list shows at most **1,000** people per view; filter it to see the ones you need.
    The company list shows at most **200** (UNVERIFIED — OWNER/ENGINEERING INPUT REQUIRED whether
    any organization has reached either limit).
  - Expecting **"Customers"** to list everyone you have served before stages existed: run
    **"Set from history"** in the **"Clean up"** card first.
- **Saved when:** **"Company created"**, **"Contact created"**, **"Contact saved"**,
  **"Contact archived"** / **"Contact restored"**, **"Linked … created …"** after a clean-up, and
  **"Merged into …"** after a merge, **"Fields saved"**, **"Saved “{view}”"** /
  **"Updated “{view}”"** / **"Deleted “{view}”"**, and **"Added “{field}”"** /
  **"Field saved"** on **Settings → Fields**. On failure: **"Could not create company"** /
  **"Could not create contact"**, **"Nothing was saved"**, **"The view was not saved"** or
  **"The field was not saved"**, with the reason.

<a id="p2-75-deals-and-pipeline"></a>

### 7.5 Deals and Pipeline

- **Purpose:** move revenue opportunities through your stages — by default **Lead → Qualified →
  Proposal → Negotiation → Closed won**, with **Closed lost** behind **"Show lost deals"**.
- **Where:** main menu → **"Pipeline"**. It opens the **Pipeline** board (`/deals` opens the same board).
- **Common actions:**
  1. **"New deal"**: **"Deal name"**, **"Who is it with?"**, **"Company (optional)"**,
     **"Expected value"**, **"Currency"**, **"Starting stage"**, **"Expected close date"**,
     **"Owner"** → **"Create deal"**.
  2. **Move a deal:** drag its card to another column, or use the card's **"⋯"** → **"Move to
     stage"** (the only way on a phone).
  3. **Open a deal** (side panel): edit its name, value, close date, owner and notes →
     **"Save changes"**; **"Log activity"** (Call, Email, Meeting, Note — logging an email sends
     nothing); read **"Stage history"**; move it on with **"Move to …"** or **"Mark as won"**;
     **"More fields"** → **"Edit"** fills in your own deal fields ([§7.4](#p2-74-contacts-and-companies)
     item 8). Winning a deal makes the people on it **Customers** (§7.4 item 6).
  4. **Winning** a deal that has a company **automatically creates a Client 360 workspace**:
     **"Deal won — client workspace created"**, with **"Open workspace"**. Without a company the
     message is **"Deal marked as won"** and no workspace is made.
  5. Filter with **"Search deals, people or companies"** and **"Everyone's deals"** / **"My deals"**.
  6. Admin: **"Customize stages"** renames, adds, reorders or removes stages → **"Save stages"**.
  7. **One open deal per person.** A person who fills in a form and later books a time, or fills
     in a second form, stays on their one open deal (opened in the last 30 days). Their new request
     is added to its history instead of opening a second deal.
- **Common mistakes:**
  - Looking for a lost deal on the board — turn on **"Show lost deals"**. A lost deal can be moved
    back to an open stage the same way as any other.
  - **"Archive this deal"** takes it off the board entirely. It stays listed on its contact's
    **"Deals"** tab, where you can open it and **"Restore"** it.
- **Saved when:** **"Deal created"**, **"Moved to {stage}"**, **"Deal saved"**. If a move fails,
  the card jumps back and **"That move did not save"** appears.

<a id="p2-76-website-forms"></a>

### 7.6 Website Forms

- **Purpose:** the forms on your website. Every submission becomes a contact, an owner, a deal, a
  call-back task and an alert, automatically.
- **Where:** **Settings** → **Capture** → **"Forms"** (**Workspace** → **"Lead routing"** opens the
  same page). Engineering guide: [WEBSITE_FORMS.md](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/WEBSITE_FORMS.md).
- **Common actions (admin):**
  1. **"New form"** → choose a **"Template"** → **"Create form"**.
  2. Work through the tabs **"Fields"**, **"Settings"**, **"Automation"**, **"Auto-reply"** and
     **"Embed & test"**, then **"Save changes"**.
  3. **"Embed & test"**: copy the embed code for your website, and **"Send a test lead"** to prove
     the whole chain. **"Open form"** opens the hosted page.
  4. **"Auto-reply"**: write the automatic reply, save it, read it, then **"Approve this wording"**.
     Each reply is still checked before it goes (consent, and an authorised email channel —
     [§6.1](#p2-61-read-this-first--current-status)). Changing the wording needs a new approval.
- **"Company"** is one of the standard fields. Add it to link each lead to their company
  ([§7.4](#p2-74-contacts-and-companies)).
- **Members** can view forms and copy embed codes only.
- **Common mistakes:** approving reply wording you have not read; forgetting that test leads land
  in **Leads**, tagged **"Test lead"**.
- **Saved when:** **"Test lead processed end to end"**; the header shows **"Saved"**.

<a id="p2-77-calendar-and-online-booking"></a>

### 7.7 Calendar and online booking

- **Purpose:** appointments people book online, the booking pages they book through, and each
  agent's hours.
- **Where:** main menu → **"Calendar"**; or **Settings** → **Capture** → **"Booking pages"**,
  which opens its **"Booking pages"** tab. Engineering guide: [BOOKING.md](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/BOOKING.md).
- **Common actions:**
  1. **"Upcoming"** tab: appointments by day (**"Mine"** / **"Everyone's"**, **"List"** /
     **"Week"**). For each: **"Attended"**, **"No-show"**, **"Reschedule"**, **"Cancel"**.
     Appointments whose time has passed without an outcome stay at the top until someone records
     one — a recorded no-show feeds recovery.
  2. **Emails to the person** (confirmations, reminders, change notices) each wait for an admin:
     **"Review and approve"** → **"Approve this email?"** → **"Approve and send"**. They also appear
     in **Operations** → **"Approvals"**. With no authorised email channel nothing is drafted, and
     the appointment says *"Email isn't connected, so nothing was emailed."*
  3. **"Booking pages"** tab (admin): **"Create my booking pages"** the first time, then
     **"New booking page"**, **"Edit"**, pause, and **"Copy link"** or an embed code. A new page
     starts from **"Meeting"** (30 min, a preparation task, no property questions); the
     real-estate templates (Home showing, Buyer consultation, Listing appointment, Phone call)
     are still in the list. Booking pages can also ask **"Company"**.
     **"Copy my link"** copies your own booking page link.
  4. **"Availability"** tab: each agent's weekly hours and days off.
- **Public pages:** `/book/…` is your public booking page (no sign-in). `/booking/manage/…` is the
  person's private link to view, reschedule or cancel — treat it like a password.
- **Common mistakes:** approving an email you have not read; leaving past appointments without an
  outcome.
- **Saved when:** **"Approved and sent"** (or *"Approved — it couldn't be sent yet; the reason is
  on the appointment"*); **"Booking link copied"**.

<a id="p2-78-client-360-workspaces"></a>

### 7.8 Client 360 workspaces

- **Purpose:** one operating page per client — health, commitments, outcomes, activity, timeline,
  tasks, deliverables, requests and approvals.
- **Where:** main menu → **"Clients"** (the **Client 360** list), then click a row.
- **Common actions:**
  1. **"New workspace"**: **"Workspace name"**, **"Company"**, **"Lifecycle stage"** →
     **"Create workspace"**. Or win a deal ([§7.5](#p2-75-deals-and-pipeline)).
  2. Filter by lifecycle stage (**Onboard / Serve / Retain / Expand**), or with **"Search clients…"**.
  3. In a workspace, read the figures (**"Health score"**, **"Open commitments"**, **"Open tasks"**,
     **"Pending approvals"**) and the tabs **"Overview"** (health breakdown and next best actions),
     **"Commitments"**, **"Tasks"**, **"Deliverables"**, **"Requests"**, **"Approvals"**,
     **"Outcomes"**, **"Timeline"**, **"Activity"**.
- **Common mistakes:**
  - Duplicate workspaces for one client.
  - A workspace's name, stage and company cannot be changed after creation.
  - A workspace made from the top-bar **"Create"** button is stored with a slightly different stage
    value, so it does not count under **Onboard**. Prefer **"New workspace"** on the Client 360 page.
  - If a workspace page stays on a grey loading skeleton, reload. If it persists, escalate.
- **Saved when:** **"Client workspace created"**; the new workspace opens.

<a id="p2-79-work-inside-a-workspace-commitments-tasks-deliverables-requests-approvals"></a>

### 7.9 Work inside a workspace: commitments, tasks, deliverables, requests, approvals

- **Purpose:** delivery follow-through for one client. A **commitment** is a promise with an owner
  and a due date, so risk shows before it becomes a breach.
- **Where:** **Client 360** → a workspace → **"New"** (top right) and the matching tab.
- **Common actions:**
  1. **"New"** → **"Commitment"**: **"Title"**, **"Owner"** (an email address), **"Due date"** →
     **"Add commitment"**.
  2. **"New"** → **"Task"**, **"Deliverable"**, **"Client request"** or **"Approval"**: a clear
     **"Title"** → **"Add task"** / **"Add deliverable"** / **"Add request"** / **"Request approval"**.
  3. Change status with the menu on each row:
     - commitments: `open`, `at_risk`, `breached`, `fulfilled`
     - tasks: `todo` → `in_progress` → `done`
     - deliverables: `draft` → `in_review` → `approved`
     - requests: `open` → `in_progress` → `done`
  4. **"Run SLA check"** runs the commitment risk check now across your **whole organization**:
     due within 48 hours → `at_risk`; past due → `breached`. The scheduler does this every
     15 minutes anyway ([§11](#p2-11-scheduler--automations)).
  5. **Approvals:** an admin sees **"Approve"** / **"Reject"**. Members see **"Awaiting admin"**.
- **Common mistakes:**
  - Only the title can be entered for tasks, deliverables and requests, and nothing here can be
    edited or deleted later. (The **Tasks** page in the main menu is separate and fully editable.)
  - The owner and due date of a commitment cannot be changed after creation.
  - Status-menu changes show no message if they fail. Refresh the tab to confirm.
- **Saved when:** **"Commitment added"**, **"Updated"**, **"Approval requested"**,
  **"SLA check complete · N at-risk, N breached"**.

<a id="p2-710-outcomes-and-evidence-backed-ai"></a>

### 7.10 Outcomes and evidence-backed AI

- **Purpose:** measurable client outcomes (goals with targets), and health over time.
- **Where:** a workspace → **"Outcomes"** tab; the **"Evidence-backed AI"** panel on the
  workspace page.
- **Common actions:**
  1. **"Add outcome"**: **"Title"**, **"Target description"**, **"Target value"**, **"Unit"** →
     **"Create"**.
  2. Type a new value in **"Update"** and press ✓ or Enter. **Check:** **"Progress updated"**.
- **AI:**
  - **"Health summary"** / **"Draft message"**, then **"Generate with evidence"**.
  - **Not active in production:** the AI key (`EMERGENT_LLM_KEY`) is not set (as recorded), so this
    fails with an error message. Retrying will not help.
  - It is an open owner decision (governing document O-11). A drafted message is never sent
    automatically.
- **Common mistakes:** a blank title makes **"Create"** do nothing; goals cannot be renamed or
  deleted.
- **Saved when:** **"Outcome added"**, **"Progress updated"**.

<a id="p2-711-activity-and-timeline"></a>

### 7.11 Activity and Timeline

- **Purpose:** what is happening with a client — matched email, meetings and billing (Activity),
  and every event, alert and health signal (Timeline).
- **Where:** a workspace → **"Activity"** / **"Timeline"** tabs.
- **Common actions:**
  - **Activity** is read-only: **"Upcoming meetings"**, **"Billing & subscriptions"**,
    **"Recent email threads"** (items tagged **"External"**).
  - **Timeline:** search **"Search timeline…"**, filter by source and severity, page with
    **"Prev"** / **"Next"**, and **"Ack"** or **"Resolve"** an alert.
- **Common mistakes:**
  - Expecting email on Activity before Google is connected and synced.
  - Expecting email or meetings for a contact with no company, or whose company has no workspace.
    Link the contact to the client's company.
- **Saved when:** **"Alert acknowledged"** / **"Alert resolved"**.

<a id="p2-712-action-center-and-notifications"></a>

### 7.12 Action Center and notifications

- **Purpose:** client risks and delivery blockers that need a person, plus your notification
  preferences.
- **Where:** the bell → **"View all in Action Center"**, or the bell → the gear icon.
- **Common actions:**
  1. **"Inbox"** tab:
     - **"Needs action"** → **"Open client"**, **"Acknowledge"**, **"Resolve"**
     - **"Recent activity"** → **"Mark read"**, **"Mark all read"**, filter by category
  2. **"My preferences"**: channels, alert categories, daily digest, digest hour, timezone,
     escalation → **"Save my preferences"**.
  3. Admin: **"Team defaults"** tab → **"Save team defaults"**. Admin: **"Send digest"** sends a
     digest now.
     - The scheduled daily digest follows the **Team defaults** hour and timezone, and goes to
       active admins. A personal digest hour in **"My preferences"** does not change it.
  4. **Bell:** the unread count (checked every 30 seconds) and **"Mark all read"**; click an item
     to open it.
- **Email notifications** need a delivery service. While it is not configured, an amber banner
  reads **"Email delivery is not configured."** and only in-app notifications work
  ([§10.6](#p2-106-email-notifications-and-ai)).
- **Common mistakes:** resolving an alert before the underlying issue is fixed — it will reappear.
- **Saved when:** **"Alert acknowledged"** / **"Alert resolved"**,
  **"Your notification preferences were saved"**, **"Team notification defaults were saved"**.

<a id="p2-713-operations"></a>

### 7.13 Operations

- **Purpose:** the control room for automation — recommendations, the durable work queue,
  recovery strategies, approvals, client conversations and the security gate.
- **Where:** **Settings** → **Developer** → **"Operations"** (admins). Main menu → **"Inbox"** opens
  its **"Conversations"** tab and **"Approvals"** its **"Approvals"** tab, for everyone.
- **Tabs and common actions:**

  | Tab | What you can do | Admin only |
  |---|---|---|
  | **"Next best actions"** | **"Refresh"**; **"Accept"** / **"Done"** / **"Snooze"** / **"Not relevant"** | — |
  | **"Work queue"** | **"Acknowledge"**, **"Resolve"**; figures **"Open"**, **"Retry scheduled"**, **"Dead letter"**, **"Needs operator"** | **"Run recovery detection"**, **"Replay"** |
  | **"Recovery strategies"** | Read proposed strategies. The amber box **"Outbound channels not authorised"** ([§5.8](#p2-58-verify-that-gmailsend-was-actually-granted)) | **"Compose strategies"** |
  | **"Approvals"** | Read what is waiting — including booking emails and form auto-replies | **"Approve"**, **"Reject"** |
  | **"Conversations"** | Read threads; **"Hand to human"** / **"Hand to agent"**; **"Close"** | — |
  | **"Security gate"** | Read scanner and component status (read-only) | — |

- **Common mistakes:**
  - **Approving without reading.** **"Approve"** takes effect on one click, with no confirmation.
    The summary on the row shows what will run or be sent (message text is cut at 500
    characters).
  - Expecting **"Conversations"** to compose or send email. It cannot ([§6.1](#p2-61-read-this-first--current-status)).
  - Expecting a consent button. Consent is recorded only by an admin through the API.
  - The **"Security gate"** shows scanners as not configured until the owner supplies scanner
    endpoints (governing document O-14). That is the intended safe default.
- **Saved when:**
  - **"Approved"** / **"Rejected"**
  - **"Acknowledged"** / **"Resolved"** / **"Replayed"**
  - **"Handoff recorded"**, **"Closed"**
  - **"Detection complete · N new, N already open"**

<a id="p2-714-recovery-proof"></a>

### 7.14 Recovery Proof

- **Purpose:** what the recovery engine found, what was actually sent, and what was recovered,
  with the records that prove it.
- **Where:** main menu → **"Reports"**.
- **What you see:**
  - **"Open potential"** — an estimate, *not revenue*
  - **"Attributed recovered"** — money a record says arrived after outreach reached the client
  - **"Unattributed outcomes"**
  - counters: **"Cases detected"**, **"Cases worked"**, **"Messages sent"**, **"Replies received"**,
    **"Outcome unknown"**, **"Blocked or failed"**, **"Median time to recovery"**
  - the cases — click one for its evidence, attribution and messages; **"Close case"** with a
    reason when a case is no longer worth working
- **Common mistakes:** adding "potential" and "recovered" together. They are deliberately separate.
  An empty report (**"No recovery cases yet"**) is honest, not broken.
- **Saved when:** a closed case shows **"Closed"**.
- **Settings** → **Coming soon** → **"Reporting"** is not active; this is the live report.

<a id="p2-715-client-operations-and-the-client-portal"></a>

### 7.15 Client Operations and the client portal

- **Purpose:** client-facing coordination per workspace — secure portal links, documents,
  estimates and invoices (local records only), appointments, referrals, review requests, safe
  internal automations and playbooks.
- **Where:** **Settings** → **Workspace** → **"Client portal and playbooks"** (the page is headed
  **"Client Operations"**; the **Automations** page links to it too). Pick a workspace in
  **"Choose a workspace"**.
  - Tabs: **"Overview"**, **"Client portal"**, **"Commercial"**.
  - **"More workflows"** adds **"Appointments"**, **"Growth"**, **"Safe automation"** and
    **"Capacity & playbooks"**.
- **Common actions:**
  1. Admin: **"Client portal"** → **"Client-facing label"** → **"Create secure portal link"**.
     - The link appears under the button as **"Link for {label}: shown only now"**, with a
       **"Copy"** button, and is also copied to your clipboard (**"Portal link copied"**). If the
       browser refuses the copy you see **"Couldn't copy the portal link"**: select the text in
       the box and copy it by hand.
     - **Send it to your client or save it now — it is never shown again.** Click **"Done, I've
       saved it"** to hide it.
  2. Admin, to end a link: **"Active links"** → **"Revoke"** on the link → **"Revoke link"**. It
     stops working at once (the client sees **"This portal link is unavailable"**). Create a new
     link if the client still needs access.
     - The client opens it without signing in. They see commitments, approved documents and
       issued invoices, and can submit a request.
  3. **"Commercial"** → **"Add document"**, **"Create estimate"** (admin).
  4. **"Appointments"** → **"Schedule"**; **"Prepare reminder"** creates an *internal* task only.
     (Online booking is the separate **Calendar** module.)
  5. **"Growth"** → **"Add referral source"**; **"Prepare for approval"** (review request, admin).
  6. **"Safe automation"** (admin) → **"Enable safe workflow"**, **"Run safely"**. These only
     create internal tasks.
  7. **"Capacity & playbooks"** (admin) → **"Apply"** a playbook's task sequence.
- **Common mistakes:**
  - Losing a portal link. It cannot be shown again: revoke it and create a new one. Revoke a
    leaked link at once.
  - Members clicking **"Create estimate"** or **"Prepare for approval"** get a permission refusal.
  - **"Create invoice"** appears only for sent or approved estimates, and the screens cannot mark an
    estimate sent. Treat invoicing here as a record, not billing. Stripe is not configured.
  - Nothing here sends email or SMS, or charges a card.
- **Saved when:** a message per action — e.g. **"Client portal link created"**,
  **"Estimate drafted"**, **"Appointment scheduled"**. Errors read **"Action could not be completed"**.

<a id="p2-716-field-ops"></a>

### 7.16 Field Ops

- **Purpose:** on-site check-ins from a phone.
- **Where:** type `/field` after the production address. There is no menu entry.
- **Common actions:**
  - **"Check in to a client workspace"**: **"Workspace"**, **"Location label"**, **"Onsite note"**,
    then **"Save check-in"**
  - **"Prepare reminder"** on an upcoming appointment
- **Common mistakes:** expecting photo upload. It is not available.
- **Saved when:** **"Field check-in saved"**.

<a id="p2-717-automation--audit"></a>

### 7.17 Automation & Audit

- **Purpose:** the organization's record of every significant change, including approvals, sends,
  password changes and resets, permission denials (`authz.denied`) and team changes. Failed
  sign-ins are **not** recorded here.
- **Where:** **Settings** → **Compliance** → **"Audit log"**; or **Settings** → **"General"** →
  **"Organization"** → **"Open audit"**.
- **Common actions:** read the newest events; filter by event, actor or record, and by resource.
  Admin: **"Undo"** on an approved AI-tool write, within the undo window (default 60 minutes), with
  a **required reason**.
- **Saved when:** **"Reversed"** (undo).

<a id="p2-718-mcp-console-governed-ai-tools"></a>

### 7.18 MCP Console (governed AI tools)

- **Purpose:** run the CRM's governed tools. Read tools run at once; write tools need approval
  first.
- **Where:** **Settings** → **Developer** → **"MCP console"** (the group is shown to admins; a
  member can still open `/mcp`).
- **Common actions:**
  - Pick a tool, fill its fields, **"Invoke tool"**.
  - A Level-2 write returns **"Approval required (Level 2)"**; an admin approves it in
    **Operations** → **"Approvals"**.
  - Admin: the **"Kill switch"** disables all tools at once.
  - Admin: **"Undo"** in **"Execution history"**.
- **Common mistakes:** flipping the kill switch as a test. Members see the toggle greyed out
  (**"Only an admin can use the kill switch"**); only admins can change it.
- **Saved when:** **"{tool} → {status}"**; **"Kill switch ON — tools disabled"** /
  **"Kill switch OFF — tools live"**.

<a id="p2-719-search"></a>

### 7.19 Search

- **Ctrl/⌘ K** (the **"Search or jump to…"** box in the top bar) opens **"Search pages and
  actions…"**. It lists the main menu, the Settings menu, a few other pages and **Coming soon**,
  in the menus' words, and finds **pages and actions only** — for example "Pipeline",
  "Team and roles", "Create opportunity". **It does not find contacts, companies, deals or
  workspaces.**
- To find a record, open its list page and use that page's search box:
  - Leads: name, email, phone, address or MLS number
  - Contacts: **"Search name, phone, email…"**; Companies: **"Search companies…"**
  - Pipeline: **"Search deals, people or companies"**
  - Client 360: **"Search clients…"**
  - a workspace's **"Search timeline…"**

<a id="p2-720-import-and-export"></a>

### 7.20 Import and export

- **Export:** only **Leads** → **"Export CSV"** in the screens. Contacts, companies and deals can be
  exported as CSV by engineering through the server.
- **Import:** no screen. The server has a CSV import (admin) that engineering can run.
- For a full data copy (a backup, or offboarding a client), ask engineering. See also
  [§13.5](#p2-135-backups-and-data-export).

<a id="p2-721-known-screen-limitations-current-code"></a>

### 7.21 Known screen limitations (current code)

These are verified behaviours of the deployed code. None loses data.

1. **Companies and workspaces cannot be edited or archived** in the screens. Contacts and deals can.
   Nothing can be deleted.
2. **No screen writes your own email to a contact, records consent, or shows unmatched inbound
   mail** ([§6.1](#p2-61-read-this-first--current-status)).
3. **The company list shows at most 200 records**; the contact list shows up to 1,000 per view
   and the Pipeline loads up to 1,000 deals.
4. **No message on some failures:** workspace status menus and outcome updates. Refresh to confirm
   the change saved.
5. **A session that expires mid-use does not redirect** to the sign-in page. Pages show
   "…unavailable" errors instead. Reload the page to sign in again ([§9.4](#p2-94-stale-browser-session)).
6. **Some buttons are visible to members but refused by the server:**
   - the MCP **"Kill switch"**
   - the webhook on/off switch
   - **"Create estimate"**
   - **"Prepare for approval"**

<a id="p2-722-automations"></a>

### 7.22 Automations

- **Purpose:** follow-ups that run themselves. *When* something happens, *do* these steps, and
  *stop* as soon as the person answers. Every run keeps a receipt.
- **Where:** main menu → **"Automations"** (`/automations`). Members can read automations and
  their receipts; only an admin creates, changes, turns on or off, tests or stops one.
- **What starts an automation** (**"What starts it"**): a website lead arrives (optionally from one
  form); a lead waits past the reply goal; someone books a time, doesn't show, or cancels
  (optionally on one booking page); a deal is won, lost, or moves to a stage (optionally one
  stage); a contact is added; a client commitment is at risk. **"Only for people who match"**
  narrows it with the same filters as the contact list, including your own fields.
- **What it can do** (the **"+"** between steps): **"Create a task"** (for the record's owner,
  nobody yet, or a named person; due now or after a delay; with a priority), **"Set a field"**
  (lifecycle, relationship, influence or one of your own contact fields), **"Add a tag"**,
  **"Assign an owner"** (round robin or a named person, by default only when nobody owns them),
  **"Notify the team"** (an in-app notice to the owner, the admins or everyone), and **"Wait"**
  (minutes, hours or days, up to 90 days). Task titles and notices can use
  `{{contact.first_name}}`, `{{contact.name}}`, `{{deal.name}}` and `{{company.name}}`.
- **Stop early when:** someone replies to them (a call, text, email or meeting is logged, or their
  website request is marked answered), they book a time, the deal is won or lost, the deal moves
  stage, or they become a customer. The rules are checked before every step, including when a
  wait ends. A run also stops if the contact is archived or the automation is turned off.
- **Common actions:**
  1. **"New automation"** → **"Start from a recipe"** → **"Use this"**. Recipes: *New lead: call
     within 5 minutes*; *Deal won: start onboarding*; *No-show: get them rebooked*; *Quiet lead:
     follow up after 2 days*; *Lost deal: check back in 90 days*; *Client commitment at risk:
     alert the admins*. Each becomes a **Draft**.
  2. Change the name, the trigger, the steps (**"Edit"** on a step; the arrows reorder it;
     **"Remove"**) and the stop rules → **"Save changes"**.
  3. **"Test with a contact"** → search → pick someone. It lists what each step would do for them.
     Nothing is changed. It uses the saved steps.
  4. **"Turn on"**. From then on every matching event starts a run.
  5. **"Runs"** lists every run: **Waiting**, **Completed**, **Stopped** (with the reason) or
     **Failed** (with the error). Open one for its receipt: each step, what it did, when, and
     **"Open the task"** / **"Open the contact"** / **"Open the deal"**. **"Stop this run"** ends a
     waiting run.
  6. **"Turn off"** stops new runs and ends the waiting ones, each with the reason on its receipt.
     The bin button deletes an automation from the list. Its receipts are kept.
- **Guardrails, always on:**
  - Nothing an automation does leaves ClientVerse. Emails and texts to people are not an
    automation step.
  - The same event never starts the same automation twice. While a person has a run in progress,
    a new event for them does not start a second one. **"Run once per person, ever"** makes it
    once for good.
  - Something an automation did never starts another automation, so two automations cannot loop.
  - Changing an automation affects new runs only. A run in progress keeps the steps it started
    with, and its receipt says which version that was.
- **Common mistakes:**
  - Expecting a draft to run. Only an automation that is **On** runs.
  - Testing after editing without saving. **"Test with a contact"** uses the saved steps.
  - Two automations on the same trigger both run. That is intended. Merge them if you want one
    list of steps.
- **Saved when:** **"Created “…”"**, **"Automation saved"**, **"Automation on"** /
  **"Automation off"** (with how many waiting runs stopped), **"Run stopped"**. On failure:
  **"Nothing was saved"** or **"Nothing was changed"**, with the reason (for example *"Step 2: choose
  someone on the team"*).
- **Under the hood:** wait steps are picked up by the API itself every 30 seconds, so nothing
  external has to be scheduled (`AUTOMATION_WATCHER`, on by default).

<a id="p2-723-industry-templates"></a>

### 7.23 Industry templates

- **Purpose:** a starting setup for the kind of business using the CRM. A template adds pipeline
  stages, booking pages, a website form, the fields that trade tracks and draft automations, all
  of which you can change afterwards. Real estate is one template among six.
- **Where:** **Settings** → **Workspace** → **"Industry template"** (`/settings/templates`), or
  **Today** → **"Set up your workspace"** → **"Choose your industry template"**. Anyone can
  preview a template; only an admin applies one.
- **The templates** (each card lists exactly what it brings):

  | Template | Pipeline (open stages → won) | Booking pages | Website form |
  |---|---|---|---|
  | **Agency & services** | Lead → Qualified → Proposal → Negotiation → Won | Discovery call, Strategy session, Client check-in | **"Contact us"** |
  | **Real estate** | New lead → Appointment set → Showing → Offer → Pending → Closed | Home showing, Buyer consultation, Listing appointment | **"Showing request"** |
  | **Home services** | New request → Estimate booked → Estimate sent → Job booked → Done | On-site estimate, Service call | **"Request a quote"** |
  | **Health & wellness** | Inquiry → Consult booked → Plan offered → Member | Free consultation, Intro session | **"Book a free consultation"** |
  | **Coaching & consulting** | Lead → Discovery call → Proposal → Enrolled | Discovery call, Coaching session | **"Apply for coaching"** |
  | **B2B sales** | Lead → Qualified → Demo → Proposal → Negotiation → Won | Intro call, Demo | **"Talk to sales"** |

  Every pipeline also ends in **"Lost"**. Each template adds two or three fields (for example
  *Service address* and *Job type* for home services) and three draft automations from the
  recipes in [§7.22](#p2-722-automations).
- **Common actions:**
  1. **"Preview"** on a card. The dialog lists **"Will add"** and **"Already there, left as it
     is"**, each with the reason. Nothing changes until you apply.
  2. **"Add N things"** applies it. The dialog then shows what was added and **"Next"** links:
     review the draft automations, put the form on your website, share your booking pages, see
     the new fields. The card you applied shows **"In use"**.
  3. To switch, preview and apply another template. It adds what that one brings and is missing;
     everything already there stays. **"Check what is missing"** on the card in use adds back any
     of its booking pages, forms or automations you have since archived or deleted. An archived
     field is not copied: the preview says **"Archived; restore it in Settings → Fields"**, and
     restoring it brings its values back.
- **What applying never does:**
  - It never renames, changes or removes anything you have. Booking pages, forms, fields and
    automations are matched by name (capitals ignored); one with the same name is left as it is.
  - It replaces the pipeline stages only while you have never customized them and no deal, form
    or booking page uses a stage that would go or change between open, won and lost. Otherwise
    the stages stay, and the preview says why. Change them yourself with **"Customize stages"** on
    the Pipeline board.
  - Automations arrive as **Drafts**; nothing runs until you **"Turn on"** each one.
  - The form's auto-reply is off. Turning it on needs its own approval ([§7.6](#p2-76-website-forms)).
- **Common mistakes:**
  - Expecting the template's stages on a pipeline that already has deals in the current stages.
    The preview shows **"Pipeline stages"** under **"Already there"** in that case.
  - Expecting automations to run straight away. They are drafts.
- **Saved when:** **"{Template} applied"** with how many things were added, or **"You already had
  everything it brings."** On failure: **"The template was not applied"**, with the reason.

<a id="p2-724-snapshots"></a>

### 7.24 Snapshots

- **Purpose:** build a setup once and reuse it. A snapshot saves this workspace's setup so it
  can be loaded into another workspace: a new client, a new location, or a business you set up
  for someone. Loading follows the same rules as an industry template ([§7.23](#p2-723-industry-templates)):
  it only adds what is missing.
- **Where:** **Settings** → **Workspace** → **"Snapshots"** (`/settings/snapshots`). Admins only;
  members do not see the menu item, and the server refuses them.
- **What a snapshot holds:** pipeline stages, fields, booking pages, website forms, automations
  and shared list views. It never holds contacts, companies, deals, leads, messages,
  appointments, team members, connected accounts, public links or passwords. On the way in:
  - booking pages leave their host behind and get a new link. The person who loads them hosts
    them; when that person is not on the workspace's team (an agency admin in a client account),
    its first admin does, and a workspace with no team yet gets them paused ([§7.25](#p2-725-agency-and-client-accounts));
  - forms leave their website addresses, thank-you redirect, lead assignment and CAPTCHA keys
    behind, and their auto-reply arrives switched off;
  - automations leave behind anyone they named: a task for a named person becomes a task for the
    record's owner, and assigning a named person becomes round robin. They arrive as **Drafts**;
  - private list views stay private and are not saved.

  A snapshot **does** carry the wording you wrote, such as confirmation messages, auto-reply
  text, task titles and a meeting location. Check those before you share it.
- **Common actions:**
  1. **"New snapshot"** → a name, an optional description, and **"What it holds"** (each part
     with how many there are now) → **"Save snapshot"**. It is a copy: changing the workspace
     later does not change the snapshot.
  2. **"⋯"** → **"Share…"** → **"Turn on sharing"**. The share code (it starts `cvs_`) is shown
     **once**: **"Copy"** it and send it. **"Make a new code"** replaces it (the old code stops
     working); **"Stop sharing"** turns it off. The list shows **"Shared · loaded N×"**.
  3. **"⋯"** → **"Download file"** saves a `.clientverse-snapshot.json` file to keep or send.
  4. To load one into this workspace: **"Load a snapshot"** → **"Share code"** (paste it) or
     **"File"** (choose the file) → **"Preview"**. The preview lists **"Will add"**, **"Can't be
     loaded"** (with the reason) and **"Already there, left as it is"**. **"Add N things"** loads it
     and shows **"Next"** links. **"Load here"** on a row loads one of your own snapshots, which
     brings back anything of it you have since deleted.
  5. **"⋯"** → **"Delete"** removes the snapshot and its share code. Nothing in any workspace
     changes.
- **How references are kept:** an automation that started from a form or booking page starts from
  that item's copy. A filter or column on one of your own fields uses the field with the same name
  in the workspace it lands in, even if that field was made under a different internal key. If
  the form an automation started from was not loaded, the preview says **"Its form did not come
  with it, so it starts for any form"**.
- **Common mistakes:**
  - Expecting contacts or deals to move. Snapshots are setup only; use import and export
    ([§7.20](#p2-720-import-and-export)) for records.
  - Losing the share code. It is shown once; make a new code (the old one stops working).
  - Expecting loaded automations to run. They are drafts until you **"Turn on"** each one.
  - Expecting a loaded pipeline to replace stages you already customized. It does not; the
    preview says so.
- **Saved when:** **"“{name}” saved"** with what it holds; **"Code copied"**; **"Sharing stopped"**;
  **"“{name}” loaded"** with how many things were added; **"“{name}” deleted"**. On failure:
  **"The snapshot was not saved"**, **"The snapshot was not loaded"**, **"No shared snapshot has
  this code. Check it, or ask for a new one."**, **"This file is not a ClientVerse snapshot"**, with
  the reason.
- **Limits:** 50 snapshots per workspace; a snapshot up to 1 MB holding up to 100 fields, 50
  booking pages, 50 forms, 50 automations and 50 shared views.

<a id="p2-725-agency-and-client-accounts"></a>

### 7.25 Agency and client accounts

- **Purpose:** run many clients from one agency. Each client gets a **client account**: a
  workspace of its own, with its own contacts, deals, team, connections and settings. The agency
  sets accounts up from its snapshots, opens any of them to work there, and pushes a snapshot to
  many at once.
- **Where:** **Settings** → **Agency** → **"Client accounts"** (`/settings/agency`), and the
  **account switcher** at the top of the main menu (it appears once your workspace has a client
  account). Agency admins only.
- **Who can do what:**
  - An **admin of the agency** can create, rename and open every client account, and is an admin
    inside each one while working there. Taking admin away from them, or disabling them in the
    agency, ends their access to every client account at once, even mid-session.
  - A **member of the agency** cannot open client accounts.
  - A **client account's own people** (invited from its **Team** page) sign in to their account
    as usual. They never see the agency, its records or any other client. A client account cannot
    have client accounts of its own.
- **Common actions:**
  1. **"New client account"** → the client's name and **"Start from"** (one of your snapshots,
     or **"A blank account"**) → **"Create account"**. The toast offers **"Open it"**.
  2. **"Open"** on a row (or pick it in the account switcher). ClientVerse reloads inside that
     account, and a banner says **"You are working in {client}, a client account of {agency}"**.
     Everything you do there is done in that account. **"Back to {agency}"** in the banner (or
     the agency's name in the switcher) returns you.
  3. Inside the client account, invite the client's team from **Settings** → **"Team and
     roles"**, then choose who hosts each booking page.
  4. **"Push a snapshot"** → a snapshot and the accounts (**"Choose all"** or some) →
     **"Preview"**. Each account shows **"Adds N · M already there"**; open one to see its full
     list. **"Push to N accounts"** loads it into each, with the same rules as loading a snapshot
     ([§7.24](#p2-724-snapshots)): only what is missing is added, and nothing a client has is
     changed. The **"Last snapshot"** column shows what was pushed last and how much it added.
  5. **"⋯"** → **"Rename"** changes the client's name; their team sees it too.
- **Booking pages in client accounts:** a page only takes bookings for hosts on that account's
  team. When a snapshot is loaded into a client account, its booking pages are hosted by the
  account's first admin; an account with no team yet gets them **paused**, and the preview says
  **"paused until someone on this account's team hosts it"**. Invite the team, then choose the
  host and turn the page on.
- **Common mistakes:**
  - Looking for a client's records from the agency. Open the client account first; the agency's
    own lists never show a client's records.
  - Expecting a push to overwrite a client's own changes. It adds only what is missing.
  - Pushing before the client's team exists, then wondering why booking pages are paused.
- **Saved when:** **"“{name}” created"**, **"Account renamed"**, **"“{snapshot}” pushed to N
  accounts"** with how many things were added in all. On failure: **"The account was not
  created"**, **"“{name}” could not be opened"**, **"The snapshot was not pushed"**, with the
  reason. Opening an account, creating one and pushing to it are recorded in the audit log of
  both the agency and the client account.
- **Limits:** 200 client accounts per agency; a push reaches up to 100 accounts at once. Every
  account in a push is checked first: if one is not yours, nothing is loaded anywhere.

---

<a id="p2-8-users-roles-and-administration"></a>

## 8. Users, Roles, and Administration

<a id="p2-81-roles-and-permissions"></a>

### 8.1 Roles and permissions

There are exactly two roles: **admin** and **member** (Verified (code)). The server enforces them
on every request, and hiding a button is never the protection.

| Action | Admin | Member |
|---|---|---|
| Sign in; view all CRM records of your organization | ✓ | ✓ |
| Create and edit contacts and deals; create companies, workspaces, tasks, commitments, outcomes | ✓ | ✓ |
| Work leads; move deal stages; change task, commitment and deliverable status; record booking outcomes | ✓ | ✓ |
| Acknowledge or resolve alerts and work items; next-best-action decisions | ✓ | ✓ |
| Change your own password; personal notification preferences | ✓ | ✓ |
| **Team & Access** — invite, resend, revoke, change role, disable/enable, reset a member's password | ✓ | ✗ |
| Connect / re-authorize / sync / disconnect integrations; see **"Connection health"** | ✓ | ✗ |
| **"Approve"** / **"Reject"** approvals (workspace, Operations, booking emails, auto-reply wording) | ✓ | ✗ |
| Website forms, booking pages and pipeline stages — create and change | ✓ | ✗ |
| Apply an industry template (**Settings → Industry template**; anyone can preview one) | ✓ | ✗ |
| Snapshots — save, share, download, load and delete (**Settings → Snapshots**) | ✓ | ✗ |
| Client accounts — create, rename, open and work in, push a snapshot (**Settings → Agency**); an admin of the agency is an admin in every one of its client accounts | ✓ | ✗ |
| Record conversation consent (API only) | ✓ | ✗ |
| MCP kill switch, undo, workspace undo window | ✓ | ✗ |
| Webhook create / enable / reveal secret / rotate secret | ✓ | ✗ |
| Portal links, estimates, invoices, review requests, safe automations, playbooks | ✓ | ✗ |
| Team notification defaults; **"Send digest"**; rename the business | ✓ | ✗ |
| Read the scheduler ledger (`/api/cron/health`, `/api/cron/runs`) — admins of the owner's own organization only (the one seeded from `ADMIN_EMAIL`); the ledger covers the whole platform | ✓ | ✗ |

A member who tries an admin action sees **"You do not have permission to perform this action"**.

<a id="p2-82-invite-a-user"></a>

### 8.2 Invite a user

1. **Settings** → **Workspace** → **"Team and roles"** (the page is headed **"Team & Access"**).
2. Click **"Invite"**. The dialog **"Invite a teammate"** opens.
3. **"Their email"** — the person's work address. **"What they can do"** — **"Member"** (default)
   or **"Admin"**.
4. Click **"Create invite"**.
5. **Check:**
   - **"Invitation emailed"** and the dialog **"Invitation sent"** — the CRM emailed the link. This
     happens only when email delivery is configured ([§10.6](#p2-106-email-notifications-and-ai)).
   - **"Invitation created"** and the dialog **"Invitation ready"** — nothing was emailed. Click
     **"Copy"** (**"Invite link copied"**) and send the link yourself, privately.
6. Click **"Done"**.

- **The link is a single-use key to your organization until it is accepted.** Never post it in a
  public channel, GitHub, or a shared document.
- The link **expires in 7 days**. The invitation appears under **"Pending invitations"**, whose
  **"Delivery"** column reads **"Emailed"** or **"Email didn't send — share the link"**.

Possible refusals:

- **"This person is already an active member of your team"**
- **"An active invitation already exists for this email"** — use **"Resend"** instead.

<a id="p2-83-what-to-tell-the-invitee-accepting-an-invitation"></a>

### 8.3 What to tell the invitee (accepting an invitation)

1. Open the link. The page reads **"Join {organization}"** — *"{inviter} invited you to join as a
   team member"* (or *"an admin"*).
2. **New to ClientVerse?** Fill in **"Create your account"**: **"Your name"**, the email (already
   filled in and locked), **"Create a password"** (at least 8 characters) and **"Confirm
   password"** → **"Create account and join"**. The account is created directly inside your team,
   and they land on **Leads**.
3. **Already have a ClientVerse account with that email?** Click **"Sign in"** under the form (or
   **"Sign in to accept"** if the page says the account exists), sign in, and click
   **"Accept and join {organization}"**.
4. If it says *"You're signed in as X, but this invitation is for Y"*, click **"Sign out and
   continue"**.
5. Accept with email and password; that is the only sign-in method.

Other pages the link can show: **"This invitation has expired"**, **"This invitation was
cancelled"**, **"You've already joined"**, **"This invitation has already been used"**, **"This
invitation link doesn't work"** — each says what to do next.

**Warning — an account belongs to one organization at a time.** Accepting an invitation with an
*existing* account *moves* it into the inviting organization. Verified (code): `accept_invitation`
replaces the account's organization and role. After that, the account no longer opens its
previous organization. The screens offer no way to switch back.

- A brand-new account made from the invitation is the safe path.
- **Do not accept with an account already used for another real organization.** Invite a
  different email address instead, or ask engineering first.
- **Owner: never accept an invitation from any other organization with your owner account** (the
  `ADMIN_EMAIL` address). The owner account would leave your organization, and a restart would not
  bring it back. Only engineering could repair it.

<a id="p2-84-resend-an-invitation"></a>

### 8.4 Resend an invitation

In **"Pending invitations"**, click **"Resend"** on the row.

- It creates a **new link** and restarts the 7 days. **The old link stops working.**
- **Check:** **"Invitation emailed again"** or **"New invite link ready"**, and the dialog shows the
  new link to share.

<a id="p2-85-revoke-an-invitation"></a>

### 8.5 Revoke an invitation

In **"Pending invitations"**, click **"Revoke"**.

- **There is no confirmation.**
- **Check:** **"Invitation revoked"**. The link now shows **"This invitation was cancelled"**.

<a id="p2-86-expired-invitations"></a>

### 8.6 Expired invitations

Expired, revoked and accepted invitations move to **"Invitation history"**, which has no buttons.
To re-invite, create a **new** invitation for the same email ([§8.2](#p2-82-invite-a-user)).

<a id="p2-87-change-a-members-role"></a>

### 8.7 Change a member's role

1. Members table → the person's **"Role"** menu → **Admin** or **Member**.
2. **Check:** **"{email} is now {role}"**.
3. **The last active admin cannot be demoted:** *"Cannot demote the last active admin. Promote
   another admin first."*

<a id="p2-88-reset-a-members-password"></a>

### 8.8 Reset a member's password

For a teammate who forgot their password, or is locked out.

1. Members table → the person's **"⋯"** menu → **"Reset password"**.
2. Read **"Reset {name}'s password?"** — they are signed out everywhere; their records are
   untouched. Click **"Reset password"**.
3. **"Temporary password ready"** shows the temporary password **once**. Click **"Copy"**, then
   **"Done"**.
4. Give it to them **privately** — by phone or a direct text. Never in a shared channel or email
   thread others can read.
5. They sign in with it. ClientVerse shows **"Choose your own password"**: they type the
   temporary one under **"Temporary password"**, choose a **"New password"** (at least 8
   characters), repeat it, and click **"Save my password"**. Until then the temporary password
   opens nothing else.

- The reset also clears a lockout on their address.
- **Not available** for yourself (use [§3.9](#p2-39-change-your-own-password)), for disabled members,
  or for accounts that sign in only with Google.
- **Do not reset the owner account this way.** Its password comes from Railway
  ([§9.2](#p2-92-forgotten-password)).

<a id="p2-89-offboard-a-user-disable"></a>

### 8.9 Offboard a user (disable)

1. Members table → the person's **"⋯"** menu → **"Disable access"**. **There is no confirmation.**
2. **Check:** **"Member disabled"**. From their very next action they see **"Your access to this
   workspace has been disabled"**, even on an open session.
3. Also:
   - revoke any pending invitations they created that you do not want
   - rotate any shared secret they knew (webhook secrets, Railway access, Google Cloud access)
   - remove them from Railway, GitHub, Google Cloud and MongoDB Atlas if they had access there
4. **To restore access:** **"⋯"** → **"Enable access"** (**"Member re-enabled"**).
5. **There is no delete.** Disabled members stay listed, for the audit trail.
6. The last active admin cannot be disabled.

<a id="p2-810-organizations-tenants-and-workspaces"></a>

### 8.10 Organizations (tenants) and workspaces

- **Organization (tenant):** your company's private space. The owner's was created as
  **"ClientVerse HQ"**; an admin can rename it in **Settings** → **"Organization"** →
  **"Business name"** → **"Rename"**. Invitations show that name. Every record belongs to exactly
  one organization.
- **Client workspace (Client 360):** one client's operating page *inside* your organization. It is
  not a separate login or a separate organization.
- **Cross-organization isolation:** people in another organization cannot see your records. A
  direct link to one of your records returns *"not found"* (404) for them.
  - Verified (code and automated tests).
  - Last proven live on 2026-09-01 (`ca30587`, production smoke including the cross-tenant 404).
- **Anyone can create their own separate organization** with **"Create a workspace"** on the
  sign-in page. It cannot see your data. It is not a way to join yours.

<a id="p2-811-ownership-considerations"></a>

### 8.11 Ownership considerations

- **Keep at least two active admins.** If one is locked out or leaves, the other can still manage
  the team and integrations, and reset passwords.
- The owner account is tied to `ADMIN_EMAIL`, and its password is always reset to `ADMIN_PASSWORD`
  at each deploy ([§3.3](#p2-33-which-account-the-owner-uses)).
- **To hand day-to-day ownership to someone:** invite them as **admin**, confirm they can sign in,
  then decide with engineering whether `ADMIN_EMAIL` stays as is. Never change it yourself.
- Records carry an "owner". Deals and tasks can be reassigned in their side panels, and a
  contact's owner by an admin; other records cannot.

<a id="p2-812-actions-that-need-engineering"></a>

### 8.12 Actions that need engineering

| Request | Why |
|---|---|
| Delete a user, or change a user's email address | No screen or API |
| Change `ADMIN_EMAIL` | It would create a new, empty organization |
| Edit or archive companies; import data; export anything but leads | API only, no screen. Deleting records, and editing workspaces, are not possible even through the API. |
| Clear a lockout on the owner account early | Database change ([§9.3](#p2-93-account-locked-out)) |

---

<a id="p2-9-account-recovery"></a>

## 9. Account Recovery

<a id="p2-91-wrong-password"></a>

### 9.1 Wrong password

1. Retype the password carefully. Check Caps Lock and the email address; the eye button shows
   what you typed.
2. **Stop after 3 failures.** At 5 the account locks for 15 minutes ([§3.7](#p2-37-lockout-behaviour)).
3. **Owner account:** copy the password from the Railway variable `ADMIN_PASSWORD` (Railway →
   service → **Variables**) or from your password manager.
4. Still failing: [§9.2](#p2-92-forgotten-password).

<a id="p2-92-forgotten-password"></a>

### 9.2 Forgotten password

There is **no self-service "forgot password" email**. The sign-in page says *"Forgot it? Your
workspace admin can reset it from Team & Access."*

**Member account:** an admin resets it ([§8.8](#p2-88-reset-a-members-password)). The member then
signs in with the temporary password and chooses their own.

**Owner account — reset it in Railway** (the owner can do this):

1. Sign in to Railway → project `welcoming-vibrancy` → service `clientverse-crm-production` →
   **Variables**.
2. Edit **`ADMIN_PASSWORD`**. Paste a new strong password from your password manager, then save.
   If Railway shows the change as staged, click **Deploy** to apply it.
3. **Do not touch any other variable** — above all, not `ADMIN_EMAIL`.
4. Wait until the new deployment shows **SUCCESS** (about 2–5 minutes).
5. Sign in with the new password. If you were locked out, wait out the 15 minutes first.
   Changing the password does not lift a lockout.

Why not **Settings** → **"Change password"** for the owner: the next deploy puts the Railway value
back ([§3.3](#p2-33-which-account-the-owner-uses)) — unless Railway is set to the same new password, as
below.

**If the owner password may be known to someone else** (leaked, shared, typed on a shared
computer), the Railway change above is not enough on its own. It replaces the password but signs
nobody out: a browser already signed in stays signed in for up to 7 days. Do this instead:

1. Sign in, then **Settings** → **"Change password"** to a new password
   ([§3.9](#p2-39-change-your-own-password)). Every other phone and computer is signed out.
2. **Straight away**, set Railway `ADMIN_PASSWORD` to that **same** new password and deploy (steps
   1–4 above). Until you do, the next deploy puts the old password back.
3. If you cannot sign in, reset the password in Railway first (steps 1–5 above), sign in with it,
   then do steps 1 and 2 with a second new password. Settings refuses a new password that matches
   the current one.

<a id="p2-93-account-locked-out"></a>

### 9.3 Account locked out

1. Stop trying — attempts while locked do not help.
2. Wait **15 minutes** after the fifth failure.
3. Try **once**, carefully, with the correct password. One more failure re-locks the account for
   another 15 minutes.
4. If you do not know the correct password, reset it first ([§9.2](#p2-92-forgotten-password)), then
   wait out the lock.
5. **A member** can be let in at once: an admin's **"Reset password"** also clears the lock
   ([§8.8](#p2-88-reset-a-members-password)). For the owner account, only engineering can clear a lock
   early, in the database.

<a id="p2-94-stale-browser-session"></a>

### 9.4 Stale browser session

**Symptoms:** after a long break, pages show **"… unavailable"** or empty lists, while
`/api/health` is fine. Sessions last 7 days. When one expires or is revoked mid-use, the screens do
not jump to the sign-in page by themselves. *"Your password was changed. Please sign in again."*
means your password was changed on another device or reset by an admin.

1. **Reload** the page (F5 / ⌘R). If the session has ended you land on the sign-in page — sign in
   again.
2. If you land back on the same errors, do the full reset ([§9.8](#p2-98-full-sign-out-and-sign-in-reset)).

<a id="p2-95-your-access-to-this-workspace-has-been-disabled"></a>

### 9.5 "Your access to this workspace has been disabled"

An admin disabled your membership. Ask an admin to **"Enable access"** for you
([§8.9](#p2-89-offboard-a-user-disable)). If you are the only admin, you cannot be disabled — the
server prevents it.

<a id="p2-96-someone-asks-about-continue-with-google"></a>

### 9.6 Someone asks about "Continue with Google"

That button was removed on 2026-10-24 ([§3.1](#p2-31-supported-sign-in-methods)). Sign in with email
and password. A person who used it earlier and landed in a strange empty CRM had a separate
organization created for them; they sign in with email and password through an invitation
instead, and engineering can remove the stray organization.

<a id="p2-97-email-and-password-rejected-but-you-are-sure-the-password-is-right"></a>

### 9.7 Email and password rejected, but you are sure the password is right

Likely causes, most likely first:

1. The account is **locked** — wait 15 minutes ([§9.3](#p2-93-account-locked-out)).
2. **The password was changed:** `ADMIN_PASSWORD` in Railway (owner), **"Change password"** on
   another device, or an admin reset (members get a temporary password from the admin).
3. A **deployment is still in progress** after a password change — wait for SUCCESS.
4. **The email address is different** — for example a typo, or another alias of the same mailbox.
   The owner account is the exact `ADMIN_EMAIL` value.
5. The site is down or degraded — check `/api/health` ([§2.3](#p2-23-if-the-site-does-not-load)).

<a id="p2-98-full-sign-out-and-sign-in-reset"></a>

### 9.8 Full sign-out and sign-in reset

1. Click the sign-out icon if you can reach it.
2. Close every ClientVerse tab.
3. Clear this site's cookies and data:
   - **Chrome / Edge:** padlock icon → **Site settings** → **Delete data**
   - **Firefox:** padlock → **Clear cookies and site data**
   - **Safari:** Settings → **Privacy** → **Manage Website Data**
4. Open the sign-in page fresh and sign in.

<a id="p2-99-who-can-fix-what"></a>

### 9.9 Who can fix what

| Problem | Owner, in the CRM | Owner, in Railway | Engineering |
|---|---|---|---|
| Forgotten **owner** password | — | ✓ `ADMIN_PASSWORD` ([§9.2](#p2-92-forgotten-password)) | — |
| Forgotten **member** password | ✓ **"Reset password"** ([§8.8](#p2-88-reset-a-members-password)) | — | — |
| Member locked out | ✓ **"Reset password"**, or wait 15 minutes | — | ✓ Clear early |
| Owner locked out | Wait 15 minutes | — | ✓ Clear early |
| Member disabled | ✓ **"Enable access"** (another admin) | — | — |
| All admins locked out | — | ✓ Reset the owner password | ✓ |
| Stale session | ✓ Reload / reset (§9.4, §9.8) | — | — |
| Site down / database down | — | Restart the latest SUCCESS deployment once | ✓ |
| Wrong `ADMIN_EMAIL` or stray organizations | — | — | ✓ |

---

<a id="p2-10-integrations"></a>

## 10. Integrations

Statuses use the labels from [the Project Completion Standard](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/PROJECT_COMPLETION_STANDARD.md):
LIVE + VERIFIED, CONFIGURATION REQUIRED, AVAILABLE BUT NOT CERTIFIED, DEGRADED, NOT IMPLEMENTED,
DEFERRED, DEPRECATED.

<a id="p2-101-integration-status-summary-2026-10-19"></a>

### 10.1 Integration status summary (2026-10-19)

| Integration | Exists in the product | Status |
|---|---|---|
| **Google — Gmail and Google Calendar connection** | Yes (**Registries**) | **RECONNECTED 2026-10-19 02:02 UTC** (Railway log: `gmail.send`, `gmail.readonly`, `calendar.readonly` granted). The row's current state needs an admin session to read; reconnect if it shows **"Needs auth"** ([§5.6](#p2-56-re-authorize-google)). While the consent screen is in Testing, the permission lapses after 7 days. The flows have never been live-certified. |
| **Gmail — outbound email** | Yes (server, approvals, booking emails, form auto-reply) | **OFF UNTIL AN ADMIN TURNS IT ON** — **"Send test & turn on"** on the Gmail row ([§5.10](#p2-510-turn-email-sending-on-or-off)); no screen to write your own email ([§6.1](#p2-61-read-this-first--current-status)) |
| **Gmail — reply capture** | Yes (scheduler) | **AVAILABLE BUT NOT CERTIFIED** — never tested live ([§6.6](#p2-66-procedure-c--capture-the-reply)) |
| **Google Calendar — meeting sync and booking busy times** | Yes | **AVAILABLE BUT NOT CERTIFIED** |
| **Website forms** | Yes (**Website Forms**) | **AVAILABLE BUT NOT CERTIFIED** — no production lead from a real website recorded yet (governing document C-30) |
| **Online booking** | Yes (**Calendar**) | **AVAILABLE BUT NOT CERTIFIED** — no production booking recorded yet (governing document M-05) |
| **Stripe** | Yes (**Registries**) | **CONFIGURATION REQUIRED** — `STRIPE_API_KEY` / `STRIPE_WEBHOOK_SECRET` are not set (O-02) |
| **Outbound webhooks** | Yes (**Registries** → **"Webhooks"**) | **AVAILABLE BUT NOT CERTIFIED** — admin-configured |
| **MCP server (governed AI tools)** | Yes (**MCP Console**) | **AVAILABLE BUT NOT CERTIFIED** |
| **Email notifications and invitation emails** | Yes (**Action Center**, **Team & Access**) | **CONFIGURATION REQUIRED** — `EMERGENT_EMAIL_KEY` was not set when last recorded; **Settings** → **"Notifications"** → **"Email delivery"** shows the live answer |
| **AI generation** | Yes (Client 360 **"Evidence-backed AI"**) | **CONFIGURATION REQUIRED** — `EMERGENT_LLM_KEY` is not set (O-11) |
| **Security-gate scanners** | Yes (**Operations** → **"Security gate"**) | **CONFIGURATION REQUIRED** (O-13, O-14) |
| **Scheduler — built into the CRM** | Yes | **LIVE** since 2026-10-18; Verified (live, 2026-10-19) from the boot log ([§11](#p2-11-scheduler--automations)) |
| **Scheduler — GitHub Actions workflow** | Yes | **LIVE**, optional second driver; its calls answered `200` on 2026-10-19 |
| **"Continue with Google" sign-in** | No (removed 2026-10-24) | **REMOVED** — third-party prototype sign-in; the server answers `410` ([§3.1](#p2-31-supported-sign-in-methods)) |
| **Recovery intake** (call logs, web enquiries, external CRM events) | Server API only, no screen | **AVAILABLE BUT NOT CERTIFIED** — for engineering integrations |
| **n8n, Slack, ClickUp** | No working CRM integration. Catalogue entries may appear in **Registries** as contracts only. | **NOT IMPLEMENTED** (O-08, O-09) |
| **SMS, Calling / telephony** | Placeholder modules only | **NOT IMPLEMENTED** (O-06) |

The **Jev QC gate** (an n8n workflow) is an engineering quality gate that AI agents use before
claiming work is complete. It is **not** a CRM feature, and it never touches CRM data.

<a id="p2-102-google--gmail-and-google-calendar"></a>

### 10.2 Google — Gmail and Google Calendar

- **Purpose:** matched email and meetings on Client 360; busy times for online booking; reply
  capture; sending approved email.
- **Connect / verify / disconnect / troubleshoot:** [Chapter 5](#p2-5-google--gmail-setup).
- **Required owner action:** Google Cloud consent screen and test users; reconnect once since
  2026-10-19, and re-authorize when needed.
- **Secret names:** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`. Optional:
  `PUBLIC_BACKEND_URL`.
- **Addresses** (Railway, set 2026-10-19):
  - `GOOGLE_REDIRECT_URI` = `https://crm.clientverse.io/api/integrations/google/callback`. It must
    also be listed under **Authorized redirect URIs** in Google Cloud, with
    `https://crm.clientverse.io` under **Authorized JavaScript origins**.
  - `FRONTEND_URL` = `https://crm.clientverse.io`. Google returns you here after connecting, and
    invitation, booking and email links use it. Start **"Connect"** from this address, so you are
    already signed in when Google sends you back.
  - The address Google is sent to when you click **"Connect"** must be the one the CRM uses to
    finish the connection. Change `GOOGLE_REDIRECT_URI` only between connection attempts, and
    register the new address in Google Cloud **first**. Otherwise **"Connect"** ends with an error.
- **Stored permission:** encrypted at rest with `INTEGRATION_ENC_KEY`. It is never shown in any
  screen or API.
- **Known limitations:**
  - Sync reads the 25 newest messages and events per run.
  - Reply capture looks back 7 days.
  - One mailbox per organization.

<a id="p2-103-stripe"></a>

### 10.3 Stripe

- **Purpose:** read customers, invoices and subscriptions and match them to contacts. Stripe
  **"Billing & subscriptions"** items appear on Client 360 → **Activity**.
- **Status:** CONFIGURATION REQUIRED. **"Connect"** on the Stripe row currently answers
  **"Stripe is not configured (STRIPE_API_KEY)."**
- **Required owner action** (governing document O-02):
  1. Decide whether Stripe is in scope.
  2. If it is, create a **test-mode** restricted key, and a webhook endpoint at
     `https://crm.clientverse.io/api/integrations/stripe/webhook`.
  3. Have `STRIPE_API_KEY` and `STRIPE_WEBHOOK_SECRET` set in Railway.
- **Connect:** **Registries** → Stripe → **"Connect"**. It uses the Railway key. The screen has no
  field for a per-organization key.
- **Verify:** the row shows **"Connected"** and the Stripe account. **"Sync"** shows
  **"Synced Stripe: N record(s) matched"**.
- **Disconnect:** **"Disconnect"** → **"Disconnected Stripe"**. Records already synced stay.
- **Limitations:** read-only, apart from payment intents on invoices (server only). No charges or
  refunds from the screens. The webhook refuses every event until its secret is set. That is
  correct, fail-closed behaviour.

<a id="p2-104-outbound-webhooks"></a>

### 10.4 Outbound webhooks

- **Purpose:** send signed event notifications (HMAC-SHA256) to another system, such as automation
  tools.
- **Where:** **Registries** → **"Webhooks"**.
- **Connect (admin):**
  1. **"New endpoint"**.
  2. **"Name"**, **"URL"** (HTTPS), and the **"Subscribed events"** chips.
  3. **"Create"**.
- **Verify:**
  - **"Send test"** → **"Test event → {status}"**.
  - **"Delivery log"** lists every attempt.
  - Each delivery gets up to 3 attempts in total. After the last one fails, it goes to the
    dead-letter list, marked **"DLQ"**.
  - **"Replay"** re-sends one.
- **Secrets:**
  - admin **"Verify"** reveals the signing secret, to give to the receiving system privately
  - **"Rotate"** replaces it immediately, with no confirmation
  - update the receiver at the same time
- **Disconnect:** switch the endpoint off. There is no delete button.
- **Limitations:** the seeded example endpoints are placeholders until configured.

<a id="p2-105-mcp-server-governed-ai-tools"></a>

### 10.5 MCP server (governed AI tools)

- **Purpose:** lets approved AI tools read CRM data (Level 1), and propose reversible writes that
  need human approval (Level 2). Level 3 and above are refused.
- **Controls:**
  - **"Kill switch"** (admin) turns every tool off at once
  - **"Undo"** (admin, with a reason, within the undo window)
  - all activity is in **Automation & Audit**
- **Secret names:** none for the built-in tools. External tools must pass the security gate, whose
  scanners are not configured.

<a id="p2-106-email-notifications-and-ai"></a>

### 10.6 Email notifications and AI

- **Email notifications** — alert emails, the daily digest, **invitation emails** and booking
  alerts to your own team — need `EMERGENT_EMAIL_KEY` (and optionally `EMAIL_FROM_NAME`). Until
  then, **Action Center** shows **"Email delivery is not configured."**, invitations are shared by
  link ([§8.2](#p2-82-invite-a-user)), and in-app alerts still work. This is **not** Gmail: these
  emails come from a separate delivery service. Emails to *clients* (booking emails, auto-replies,
  approved messages) go through Gmail only ([§6](#p2-6-email-production-verification)).
- **AI generation** needs `EMERGENT_LLM_KEY`. Until then, **"Generate with evidence"** fails.

---

<a id="p2-11-scheduler--automations"></a>

## 11. Scheduler / Automations

<a id="p2-111-what-runs-and-where"></a>

### 11.1 What runs, and where

- **The built-in scheduler** runs inside the CRM service on Railway. It starts with the application
  and runs each job once per time window, even when several copies of the service run. Each run is
  recorded in production's run record (the "ledger") as `origin: in_process`. **Nothing needs
  configuring.** Verified (code: `backend/scheduler.py`) and Verified (live, 2026-10-19): the boot
  log reads `In-process scheduler started for 13 job(s): …`.
- **The GitHub Actions workflow "Scheduled jobs"** (`.github/workflows/scheduled-jobs.yml`, job
  **"Call scheduled endpoints"**) is an **optional second driver**. It calls the same
  `/api/cron/…` endpoints over HTTPS with a shared secret, then reads production's ledger back to
  prove each call was recorded. It is still configured: Verified (live, 2026-10-19) — production
  answered its calls with `200`.
- **Running both is safe.** The built-in run skips a window the workflow already ran; a workflow
  call that arrives after the built-in run repeats a sweep that finds nothing left to do.
- **The lead watcher** (website leads' speed-to-lead escalation) runs inside the CRM every minute.
  The workflow also calls its endpoint, `lead-sla`.
- **Times are UTC.** GitHub can start its runs a few minutes late; the built-in scheduler does not
  depend on GitHub.

<a id="p2-112-scheduled-jobs"></a>

### 11.2 Scheduled jobs

Verified (code): the job table in `backend/scheduler.py`, which `scripts/validate_config.py` keeps
equal to the workflow's cadences.

| Job (`/api/cron/…`) | What it does | Cadence (UTC cron) |
|---|---|---|
| `commitment-risk` | Flags commitments due within 48 hours as at-risk and past-due ones as breached | `*/15 * * * *` — every 15 minutes |
| `work-queue` | Runs the durable work queue: recovers abandoned jobs, processes due items | `*/5 * * * *` — every 5 minutes |
| `recovery-runner` | Runs approved recovery steps. Outbound steps are drafted for approval, never sent without it. | `*/5 * * * *` |
| `booking-reminders` | Handles booking reminders that are due (each exactly once), then sends booking emails an admin approved | `*/5 * * * *` |
| `integration-sync` | Syncs Gmail, Google Calendar and Stripe for connected organizations, then re-checks alerts | `0,30 * * * *` — :00 and :30 |
| `next-best-actions` | Recomputes ranked next best actions | `0,30 * * * *` |
| `inbound-email` | Checks connected Gmail inboxes for replies and bounces | `10,40 * * * *` — :10 and :40 |
| `reconcile-unknown` | Asks Gmail about messages whose outcome is unknown. **Never re-sends**, and a refused lookup never counts as "not sent". | `10,40 * * * *` |
| `daily-digest` | At the organization's **Team defaults** digest hour and timezone: runs alert escalations and sends one organization digest to active admins (email needs `EMERGENT_EMAIL_KEY`) | `5 * * * *` — hourly at :05 |
| `second-chance` | Second Chance detection of stalled and lost revenue | `5 * * * *` |
| `detect-recovery` | Runs every other recovery detector (for example missed calls and no-shows) | `5 * * * *` |
| `recovery-strategies` | Composes a recovery strategy for each open candidate | `5 * * * *` |
| `approval-expiry` | Expires approval requests past their deadline | `5 * * * *` |
| `lead-sla` | Escalates website leads nobody answered in time | Every minute, by the lead watcher — not by the built-in scheduler. The workflow also calls it every 5 minutes. |

Each workflow call is accepted at once and does its work in the background. A repeated delivery of
the same call is recognized and ignored.

<a id="p2-113-configuration-names-only"></a>

### 11.3 Configuration (names only)

| Where | Name | Holds |
|---|---|---|
| Railway → service → **Variables** | `IN_PROCESS_SCHEDULER` | Leave unset. `0` turns the built-in scheduler **off** — an engineering decision |
| Same | `IN_PROCESS_SCHEDULER_JOBS` | Leave unset. Engineering can limit the built-in scheduler to listed jobs |
| Same | `WEBHOOK_CRON_SECRET` | The shared secret for calls from outside (the workflow, or an engineer running a job by hand) |
| GitHub → repository **Settings** → **Secrets and variables** → **Actions** | `CLIENTVERSE_PRODUCTION_URL` | The production address in [§2.1](#p2-21-addresses) — workflow only |
| Same | `WEBHOOK_CRON_SECRET` | **The same value** as the Railway variable — workflow only |

<a id="p2-114-verify-that-automation-is-healthy"></a>

### 11.4 Verify that automation is healthy

**A. Production (owner, signed in as admin in the same browser)**

1. Open https://crm.clientverse.io/api/cron/health. It covers
   the last 120 minutes.
2. **Healthy:**
   - `"scheduled_jobs_running": true`
   - under `"in_process"`: `"last_run_at"` within the last ~5 minutes, and `"by_status"` mostly
     `succeeded` — **or**, if the GitHub workflow runs too, a recent
     `"last_authenticated_call_at"`. When the workflow has already run a job in a window, the
     built-in scheduler skips that window and records nothing new under `"in_process"`.
3. **If you keep the GitHub workflow:** `"receiving_scheduled_traffic": true` and
   `"last_authenticated_call_at"` within the last ~15 minutes. These count only calls from outside
   the CRM, so with the workflow off they are `false` / old — that is expected.
4. `"last_failed_job"`, `"last_failed_error"`, `"last_failed_origin"` — the last job that ran but
   raised an error, and which scheduler ran it.
5. `"last_rejected_call_at"` — the last outside call refused because of a wrong secret. It should be
   older than the last authenticated call.
6. More detail: `/api/cron/runs` lists individual runs. Built-in runs show `origin: in_process` and
   an id like `inprocess-<job>-<time>`.

**B. Railway (owner)**

Railway → service → **Deployments** → the active deployment → **View logs**:

- at start-up: `In-process scheduler started for 13 job(s): …`
- a failing job: `In-process job '<job>' failed for window …`
- workflow calls: lines like `"POST /api/cron/work-queue HTTP/1.1" 200 OK`

**C. GitHub (only if you keep the workflow)**

1. Open https://github.com/ebyron357/Clientverse-crm/actions/workflows/scheduled-jobs.yml.
2. The newest runs have green ticks, and a new run appears about every 5 minutes.
3. Open a run → **Summary**. The table **endpoint | HTTP | accepted | evidence id** shows `200`
   and `true` for every row. The last line reads
   *"Production recorded N ledger reference(s) for this run"*.

<a id="p2-115-what-the-results-mean"></a>

### 11.5 What the results mean

| You see | Meaning | Action |
|---|---|---|
| `"scheduled_jobs_running": false` | Nothing ran any job in the last 2 hours | Check the Railway boot log for the start-up line (§11.4 B). If it is missing, or says the scheduler is disabled, escalate. |
| `"in_process"` → `"last_run_at"` older than ~10 minutes while `/api/health` is ok | Either the GitHub workflow ran every job first, or the built-in scheduler has stopped | First check `"last_authenticated_call_at"`: if it is recent, or the Railway log shows `In-process job '<job>': an external request already ran window …`, automation is healthy — nothing to do. Otherwise restart the latest SUCCESS deployment once ([§2.3](#p2-23-if-the-site-does-not-load)); escalate if it persists. |
| `"last_failed_job"` recent | One job raised an error | Note the job and `last_failed_error`; escalate if it repeats |
| `"receiving_scheduled_traffic": false` | No outside scheduler is calling | Expected if you rely on the built-in scheduler. If GitHub shows green runs at the same time, escalate. |
| **403** on `/api/cron/health` in your browser | You are signed in as a member, not an admin | Sign in as an admin |
| GitHub **green run** | Production was called, answered `200` for every job, **and** recorded the run | None |
| GitHub **red run** | Something in the chain failed. Open the run to see which step. | See the rows below |
| **401 Unauthorized** (workflow) | The shared secret is missing or different at one end (GitHub vs Railway). Production records the refusal. | Make both `WEBHOOK_CRON_SECRET` values identical ([§11.8](#p2-118-rotate-or-fix-the-scheduler-secret)) |
| *"Scheduler not configured"* — *Missing repository secret(s)* | A GitHub secret is not set | Add it (§11.3), or disable the workflow if you rely on the built-in scheduler |
| *"No request reached production"* | None of the calls returned 200 | Read the **HTTP** column of the run summary: `000` = production unreachable (check `/api/health` and Railway, [§2.3](#p2-23-if-the-site-does-not-load)); `401` = secret mismatch ([§11.8](#p2-118-rotate-or-fix-the-scheduler-secret)); `404` = wrong `CLIENTVERSE_PRODUCTION_URL` |
| *"Run not recorded"* / *"Ledger unreadable"* | Calls were accepted, but the ledger check failed | Escalate |
| Every workflow job fails in 2–4 seconds with no log | A GitHub account-level Actions problem (billing, spending limit, Actions disabled) — as from 2026-09-27 22:35 until 2026-09-30 | Owner: GitHub → **Settings** → **Billing and plans**; repository **Settings** → **Actions** → **General**. The built-in scheduler keeps running meanwhile. |
| Workflow runs stop appearing at all | GitHub disables scheduled workflows after 60 days without repository activity | **Actions** → **Scheduled jobs** → GitHub's enable button — or leave it off |

**Stopping the workflow.** If you decide to rely on the built-in scheduler alone, disable the
workflow in GitHub (**Actions** → **Scheduled jobs** → its menu → disable). Do not just delete its
secrets: without them every run fails by design.

<a id="p2-116-current-state-verified-live-2026-10-19"></a>

### 11.6 Current state (verified live 2026-10-19)

- **The built-in scheduler runs.** Production runs `main@838f00d` (Railway deployment
  `406f320e-…`, SUCCESS 01:16 UTC), and its boot log reads `In-process scheduler started for 13
  job(s)` with the thirteen jobs of §11.2. It has run since PR #38 was deployed on 2026-10-18.
- **The GitHub workflow also reaches production.** Railway's log shows `200 OK` for all fourteen
  workflow paths, with the ledger read-backs, between 00:19 and 01:17 UTC on 2026-10-19.
- **Not observed:** the `/api/cron/health` answer itself. It needs an admin session, and the
  engineering environment cannot open the production website. Read it yourself (§11.4 A).
- **History:**
  - 2026-09-30: the workflow reached production for the first time — runs **#3551–#3555** green,
    after **#3544–#3550** failed with `401 Unauthorized` (a secret mismatch, then corrected).
  - 2026-09-27 22:35 → 2026-09-30: GitHub Actions ran nothing at all.
  - Before that, the workflow's secrets were unset and no scheduled job had ever run in production.

<a id="p2-117-run-the-jobs-by-hand"></a>

### 11.7 Run the jobs by hand

You rarely need to: the built-in scheduler runs every job within its window. To run one now:

- **From the screens:** **"Run SLA check"** (commitment risk, [§7.9](#p2-79-work-inside-a-workspace-commitments-tasks-deliverables-requests-approvals)),
  **"Sync"** on an integration (§5.5), **"Run recovery detection"** and **"Compose strategies"**
  (Operations, admin), **"Send digest"** (Action Center, admin), **"Refresh"** on next best actions.
- **From GitHub** (while the workflow is configured): **Actions** → **Scheduled jobs** →
  **"Run workflow"** (on `main`). Leave **jobs** empty to run all fourteen, or enter a
  comma-separated list, for example `inbound-email,reconcile-unknown`.

This is safe: every job is idempotent.

<a id="p2-118-rotate-or-fix-the-scheduler-secret"></a>

### 11.8 Rotate or fix the scheduler secret

The built-in scheduler does not use this secret. It matters only for the GitHub workflow and for
jobs an engineer runs by hand.

1. Generate a new long random value in your password manager.
2. **GitHub:** repository **Settings** → **Secrets and variables** → **Actions** →
   `WEBHOOK_CRON_SECRET` → **Update**.
3. **Railway:** service → **Variables** → `WEBHOOK_CRON_SECRET` → the same value → save and deploy.
4. Until both match and the deploy is SUCCESS, workflow runs fail with 401. That is expected for a
   few minutes.
5. **Check:** the next workflow run is green (§11.4 C).

**Owner can do:** secrets in GitHub and Railway; restoring GitHub Actions billing; enabling or
disabling the workflow; manual runs.

**Needs engineering:** turning the built-in scheduler off or limiting it, changing job cadence,
adding jobs, or any failure that is not explained in §11.5.

---

<a id="p2-12-troubleshooting-matrix"></a>

## 12. Troubleshooting Matrix

| Problem | Likely cause | Exact owner action | Escalate when |
|---|---|---|---|
| **Cannot log in** (any reason) | Wrong password, lockout, wrong address, stale session, site down | 1. Check `/api/health` (§2.3). 2. Check the email is exactly right (owner: the `ADMIN_EMAIL` value). 3. See the rows below. | After §9.1–§9.8 fail, or the site is down |
| **Wrong password** — "Invalid email or password" | Typo, Caps Lock, or the password changed | Owner: copy it from Railway `ADMIN_PASSWORD` or your password manager. Member: an admin resets it (§8.8). Stop after 3 tries. (§9.1) | Never needed |
| **Forgot password** | — | Owner: change `ADMIN_PASSWORD` in Railway (§9.2). Member: **"Reset password"** (§8.8). | No admin can sign in |
| **Account locked** — the right password is still refused | 5 failures → 15-minute lock | Wait 15 minutes, then try **once** (§9.3). A member: an admin's reset clears it. | The owner needs access sooner |
| **"Choose your own password"** appears after sign-in | You signed in with a temporary password | Type it again under **"Temporary password"**, choose your own, **"Save my password"** (§8.8) | It reappears after saving |
| **"Your password was changed. Please sign in again."** | Your password was changed elsewhere, or reset by an admin | Sign in with the new password (§9.4) | You did not change it and no admin reset it — treat as a security problem (§13.6) |
| **"Continue with Google" missing** | Removed on 2026-10-24 | Use email + password (§3.1, §9.6) | Someone ended up in a stray organization before the removal |
| **Google connection fails** — "Google authorization failed" | Consent cancelled or refused, redirect URI mismatch, not a test user | Full reset (§5.7), then connect within 10 minutes and tick every box (§5.5) | It fails twice after a full reset |
| **Google reconnect loop** — stuck "Connecting…" or back to "Error" | Abandoned consent; secret or redirect mismatch | Disconnect **both** rows, remove app access in the Google account, connect again (§5.7, §5.9) | `token_exchange_failed` or `redirect_uri_mismatch` persists |
| **Google token refresh 400** — "Needs auth", `token_refresh_failed:400` | Permission revoked or expired; consent screen in Testing (7-day expiry); client secret rotated | **"Re-authorize"** (§5.6) | It recurs within a week (Testing mode), or the reconnect itself ends in "Error" / `token_exchange_failed` (secret or redirect mismatch) |
| **Integration says disconnected** — "Not connected" | Never connected, or someone disconnected it | Admin → **"Connect"** (§5.5). Check **Automation & Audit** for `integration.disconnected` to see who. | Connect fails |
| **Gmail send refused as "read-only"** | The connection does not record `gmail.send`: unticked at Google, or made before 2026-10-19 | Full reset and tick **send** on consent (§5.7, §5.8) | It still says read-only after that |
| **Gmail send fails** — message "Blocked" | Not connected, no consent, or email sending off | Read the reason on the message. Fix the connection (§5.6). Turn email sending on (§5.10). | The reason mentions consent or a provider |
| **Gmail send fails** — message "Failed" (the engineer finds HTTP 403 in the message's `error` field) | Send permission not actually granted | Full reset, and tick **send** on consent (§5.7, §5.8) | It still fails after that |
| **Gmail send** — "Outcome unknown" | Google did not confirm | **Do not re-send.** Wait for the :10 / :40 reconcile; if Google is not **"Connected"**, reconnect first (§6.7). | Still unknown 1 hour after Google is connected |
| **Booking email not sent** — "Waiting for approval", "Could not send", or "Email isn't connected…" | Awaiting an admin; Gmail failed; email channel not authorised | Admin: **"Review and approve"** (§7.7). Otherwise as the Gmail rows above. | The reason is unclear |
| **Inbound reply missing** | Sweep not run yet; Gmail not Connected; reply ambiguous (parked) | Wait up to 35 minutes (the sweep runs at :10 and :40). Check the Gmail row is "Connected". | Missing after 35 minutes with healthy automation — engineering checks the unmatched queue (Appendix C) |
| **Invitation email not received** | Email delivery not configured, or the send failed | **Team & Access** → **"Pending invitations"** → **"Delivery"**. Send the link yourself (**"Resend"** shows a fresh one). (§8.2, §8.4) | — |
| **Automation not running** — `scheduled_jobs_running: false` | Built-in scheduler stopped or turned off | See §11.5 | Always |
| **Scheduled job failed** — red workflow run, or `last_failed_job` | See §11.5 | Open the run, or read `last_failed_error`, and match it in §11.5 | Unexplained, or repeats 3 times |
| **Scheduler not configured** — red run "Missing repository secret(s)" | A GitHub secret is missing | Add it (§11.3), or disable the workflow (§11.5) | — |
| **Scheduler secret mismatch** — workflow calls return 401 | GitHub and Railway `WEBHOOK_CRON_SECRET` differ | Set both to the same value (§11.8) | Still 401 after both are set and the deploy is SUCCESS |
| **401** anywhere | You are not signed in, or your session expired or was revoked | Reload; sign in again (§9.4). For workflow calls, see the secret-mismatch row. | It recurs right after signing in |
| **403** — "You do not have permission to perform this action" | The action is admin-only | Ask an admin, or sign in as one (§8.1) | An admin gets it |
| **403** — "Your access to this workspace has been disabled" | Membership disabled | An admin clicks **"Enable access"** (§8.9) | No admin is available |
| **404** / "not found" | Wrong address, a record from another organization, or an invalid invite, portal or booking link | Check the address. Open records from lists, not old links. Ask for a fresh invite. | A record you created is missing |
| **500** / "Something went wrong." | A server error | Retry once. Note the time and action. Check `/api/health`. | It repeats — send the evidence (§15.2) |
| **AI generation fails** | AI key not configured | None — AI is not active (§10.6) | You want AI enabled (owner decision O-11) |
| **503** on `/api/health` — "database":"down" | The database is unreachable | Check MongoDB Atlas status and network access | Always |
| **Blank page** | A display error (**"This view needs a refresh"**), expired session, or loading error | Click **"Reload ClientVerse"** or reload. Then the full reset (§9.8). | A blank page persists after §9.8 |
| **Data not appearing** | Filtered view, archived contact, lost deal, a different organization, over 200 records, not synced yet | Clear the search and filters; turn on **"Show archived"** / **"Show lost deals"**. Check you are in your organization (Settings). For email and meetings, connect and **"Sync"**. | Records you created are gone |
| **Save or update does not persist** | Silent failure (workspace status menus), expired session, permission | Refresh the page to see the true state. Reload and sign in. Retry. | It reverts twice |
| **CRM unavailable** — site will not load | Railway down, a failed deploy, the database | Follow §2.3 | Railway shows FAILED or CRASHED, or the database is down |
| **Railway deployment failed** — FAILED or CRASHED | Build or boot error in a new commit | Screenshot the deployment and logs. Restart the last SUCCESS deployment once (§2.3). | Always — engineering decides on rollback |
| **Invitation link does not work** | Expired (7 days), revoked, already used, or replaced by **"Resend"** | Create a new invitation (§8.2) | The new link also fails |
| **Portal link lost or leaked** | It is shown only once | **"Revoke"** it (Client Operations → Client portal → Active links) and create a new link; share it privately | Revoking fails |

---

<a id="p2-13-security-and-owner-safety"></a>

## 13. Security and Owner Safety

<a id="p2-131-never-share-these"></a>

### 13.1 Never share these

- **Passwords** — yours, a member's, a temporary one, or the value of `ADMIN_PASSWORD`. (Give a
  temporary password only to its owner, privately.)
- **API keys and secrets:**
  - `JWT_SECRET`
  - `INTEGRATION_ENC_KEY`
  - `WEBHOOK_CRON_SECRET`
  - `GOOGLE_CLIENT_SECRET`
  - `STRIPE_API_KEY`
  - `STRIPE_WEBHOOK_SECRET`
  - `EMERGENT_LLM_KEY`
  - `EMERGENT_EMAIL_KEY`
- **OAuth client secrets** from Google Cloud.
- **Database addresses** — `MONGO_URL`, which contains the database password.
- **Session tokens and cookies** — `access_token`, `cv_access_token`, or anything copied from the
  browser's developer tools.
- **Links that grant access:**
  - invitation links (`/invite?token=…`)
  - client-portal links (`/portal/…`)
  - booking manage links (`/booking/manage/…`)
  - webhook signing secrets
  - the Jev QC webhook address

Public booking pages (`/book/…`) and website-form embed codes are meant to be public.

<a id="p2-132-where-secrets-may-and-may-not-go"></a>

### 13.2 Where secrets may and may not go

| Allowed | Never |
|---|---|
| Railway → service → **Variables** (the approved store for production secrets) | GitHub issues, pull requests, comments, wikis. **This repository is public: anything posted there is public.** |
| GitHub → **Settings** → **Secrets and variables** → **Actions** (scheduler secrets only) | Any committed file — **never commit a `.env` file** (they are git-ignored for this reason) |
| Your password manager | Chat, email, Slack, ClickUp, tickets, screenshots |
| Google Cloud Console (its own client secret) | This manual, or any document |

**If a secret was ever exposed** — pasted, screenshotted, emailed or committed — treat it as
compromised and **rotate it** (§13.4), even if you deleted the message.

<a id="p2-133-which-settings-are-safe-to-change"></a>

### 13.3 Which settings are safe to change

| Safe for the owner | Needs engineering review first |
|---|---|
| **In the CRM:** notification preferences, team invites, roles, disable/enable, password resets, your own password (not the owner's — §3.3), business name, Google connect/re-authorize/disconnect, webhook endpoints you own | **Railway:** any variable other than `ADMIN_PASSWORD` and `WEBHOOK_CRON_SECRET` — including `IN_PROCESS_SCHEDULER` |
| **Railway:** `ADMIN_PASSWORD` (§9.2); `WEBHOOK_CRON_SECRET` together with GitHub (§11.8); **Restart** of the latest SUCCESS deployment | **Railway:** Rollback / Redeploy of an older commit; changing the production address (done once, 2026-10-19: `FRONTEND_URL`, `GOOGLE_REDIRECT_URI` and `CORS_ORIGINS` change together, and an OAuth attempt in progress fails) |
| **GitHub:** Actions secrets; enabling or disabling the workflow; manual runs | **Never:** `ADMIN_EMAIL`, `MONGO_URL`, `DB_NAME`, `INTEGRATION_ENC_KEY` (changing it makes every stored integration permission unreadable), `JWT_SECRET` (changing it signs everyone out), `APP_ENV`, `SEED_DEMO_DATA` (must stay false) |
| **Google Cloud:** consent-screen test users | **Google Cloud:** redirect URIs, client secret rotation (Railway must be updated at the same moment) |
| **DNS:** the records Railway shows for the custom domain (O-12) | **MongoDB Atlas:** network access, users, backups |

<a id="p2-134-rotate-credentials-safely"></a>

### 13.4 Rotate credentials safely

1. **Plan it.** Know which two places must change together: Railway + GitHub for the cron secret;
   Google Cloud + Railway for the Google client secret.
2. Generate the new value in your password manager.
3. Change the **source** first (Google Cloud / Stripe), then **Railway**, then **GitHub** if it
   applies. Deploy.
4. Verify:
   - `/api/health` is ok
   - you can sign in
   - automation is healthy (§11.4)
   - Google is still **"Connected"**
5. Record *that* you rotated, and when — **never the value** — in the governing document's
   owner-action register.

**Open rotations (governing document O-04, O-05):**

- Rotate `ADMIN_PASSWORD` if it has ever left the Railway dashboard. If someone else may know it,
  follow §9.2 *"If the owner password may be known to someone else"*: a Railway-only change does
  not sign out a browser that is already signed in.
- Rotate the legacy Stripe webhook secret recoverable from old git history when Stripe is set up.
- Delete the unused misspelled Railway variable `Mongo_url`.
- Rotate the Jev QC webhook path, and enable its header authentication.

<a id="p2-135-backups-and-data-export"></a>

### 13.5 Backups and data export

- **Backups:** the database is MongoDB Atlas. Whether backups are enabled is UNVERIFIED —
  OWNER/ENGINEERING INPUT REQUIRED.
  - Atlas's free and shared tiers do not keep continuous backups.
  - Confirm the backup policy in Atlas **before real client data grows**. This is the largest open
    data risk.
- **Network access:** Atlas network access has been open to all addresses (`0.0.0.0/0`) since
  2026-09-01. Narrowing it is recommended (owner, with engineering).
- **Export:** only leads can be exported from the screens (§7.20). Ask engineering for a CSV export
  of other record types.

<a id="p2-136-report-a-problem-safely"></a>

### 13.6 Report a problem safely

- **Operational problems:** follow [Chapter 15](#p2-15-support--escalation). Use the status issue, or
  your private engineering channel.
- **Security problems** (a leaked secret, suspicious access): do **not** open a public issue.
  - Use GitHub's **private vulnerability reporting** for this repository (see `SECURITY.md`), or
    contact engineering privately.
  - Rotate the affected secret immediately.

<a id="p2-137-screenshots--what-is-safe"></a>

### 13.7 Screenshots — what is safe

| Safe to send | Redact first | Never send |
|---|---|---|
| Error messages, page headings, status labels, the Registries rows, GitHub run summaries, Railway deployment lists and log lines | Client names, email addresses and phone numbers (when sharing outside the company); the connected Google address if the mailbox is personal; **access codes in addresses** — any `?token=` part, and the code after `/portal/` or `/booking/manage/` | Railway **Variables** with values visible; the webhook **"Verify"** dialog; the **"Invitation ready"** dialog; the **"Temporary password ready"** dialog; browser developer tools showing cookies, headers or storage; Google Cloud credential pages |

---

<a id="p2-14-production-verification-checklist"></a>

## 14. Production Verification Checklist

Mark each item **PASS**, **FAIL**, **BLOCKED** or **NOT TESTED**. Definitions are in
[§6.2](#p2-62-result-definitions). Write the date, and attach evidence for every PASS.

The *Known on 2026-10-19* column is what the engineering review could observe without opening the
website. The owner's result is the authority. Use a **test member** for the password checks, never
the owner account.

| # | Check | How | Expected | Known on 2026-10-19 | Result |
|---|---|---|---|---|---|
| 1 | Production URL loads | Open the production URL | Sign-in page, **"Sign in to ClientVerse"** | Deployment SUCCESS; health 200 in the Railway log | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 2 | Service healthy | `/api/health` | `status ok`, `database up`, `git_sha` = Railway commit | Health 200 at boot (01:16 UTC) | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 3 | Login works | §3.2 | **Today** | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 4 | Logout works | Sign-out icon, then open `/dashboard` | Returns to the sign-in page | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 5 | Admin role verified | Settings → **"Profile"** → **"Access level"**; **"Team & Access"** visible | **"Workspace admin"** | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 6 | Member role verified | Invite a test member (§8.2); they create their account from the link in a private window | **"Team member"**; no **"Team & Access"**; the Registries rows show **"Admin manages"** | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 7 | Password reset and change work | Reset the test member's password (§8.8); they sign in with it, see **"Choose your own password"**, save; later **"Change password"** (§3.9) | Temporary password opens only that screen; **"Password changed"** | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 8 | Core CRM records load | Leads, Tasks, Contacts, Companies, Pipeline, Calendar, Client 360 | Lists or honest empty states; no "…unavailable" | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 9 | Create record works | Create company `ZZ Test Co` and contact `ZZ Test Person` | **"Company created"**, **"Contact created"**; both appear after a reload | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 10 | Edit record works | Open `ZZ Test Person` → **"Edit"** → add a phone → **"Save changes"**; move a test deal **Lead → Qualified**; reload | **"Contact saved"**, **"Moved to Qualified"**; both persist after the reload | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 11 | Archive / restore | **"Archive contact"** on `ZZ Test Person`; **"Show archived"**; **"Restore"** | **"Contact archived"**, **"Contact restored"** | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 12 | Google connected | Registries → Gmail | **"Connected"**, no red line, connected on or after 2026-10-19 | Reconnected 2026-10-19 02:02 UTC; row state needs an admin session (§1.4) | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 13 | gmail.send verified | §5.8 checks 1–3, §5.10 | Google lists send permission; **"Email sending on"**; Email not listed as unauthorised | Google granted `gmail.send` on 2026-10-19 02:02 UTC; sending not yet turned on | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 14 | Outbound email works | §6.4 | **"Sent"**; in Gmail Sent; received | BLOCKED (§6.1) | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 15 | Duplicate-send protection | §6.5 | Refused; one copy only | BLOCKED (§6.1) | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 16 | Inbound reply works | §6.6 | Inbound **"Received"** on the same thread | BLOCKED (§6.1) | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 17 | Automation healthy | §11.4 A | `scheduled_jobs_running: true`; recent `in_process.last_run_at`, or a recent `last_authenticated_call_at` when the workflow runs too | Boot log shows the built-in scheduler; workflow calls answered 200 | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 18 | Railway deployment healthy | Railway → Deployments | Newest **SUCCESS**, no crash loop | `838f00d` SUCCESS 01:16 UTC | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 19 | Integrations show correct status | Settings → **"Integrations"** vs Registries | Same statuses in both; Stripe **"Not connected"** | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 20 | No visible critical errors | Visit every main menu item and every Settings item above **Coming soon** | No **"This view needs a refresh"**, no "…unavailable" | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 21 | Clean up | Archive `ZZ Test Person` and the test deal; disable the test member. The test company has no archive button — note its name for engineering. | Recorded | — | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |

**Sign-off:** date ____________ · verified by ____________ · evidence location ____________

---

<a id="p2-15-support--escalation"></a>

## 15. Support / Escalation

<a id="p2-151-when-to-escalate"></a>

### 15.1 When to escalate

| Situation | Who |
|---|---|
| Anything this manual lets the owner fix (sign-in, member passwords, Google reconnect, invitations, scheduler secrets) | **Owner** — follow the chapter |
| Site down, deployment FAILED or CRASHED, database down, automation stopped, any repeated `500` | **Engineering — urgent** |
| Company edits, deletes, export or import | **Engineering — planned** |
| Leaked secret or suspicious access | **Rotate now**, then report **privately** (§13.6) |
| Google Cloud, Stripe account, GitHub billing, DNS, MongoDB Atlas account decisions | **Owner** (engineering can advise) |

<a id="p2-152-evidence-to-collect-before-you-escalate"></a>

### 15.2 Evidence to collect before you escalate

- [ ] **Time** of the problem, with your timezone (for example `2026-10-19 01:16 UTC`)
- [ ] **Page or module** — the menu item and tab, and the address bar with every access code
      removed: any `?token=` part, and the code after `/portal/` or `/booking/manage/` (write
      `/portal/<removed>`). Those codes open a client's portal or booking to whoever has them.
- [ ] **Action attempted** — the exact button you clicked, and what you typed (never passwords)
- [ ] **Exact error text**, copied word for word, or a screenshot of it
- [ ] **Screenshot** of the whole screen, following §13.7
- [ ] **Affected account** — the email address of the user involved, and whether admin or member
- [ ] **Browser and device** — for example "Chrome 129 on Windows 11"
- [ ] **Repeatability** — every time / sometimes / once; and does it happen in a private window?
- [ ] **`/api/health` result** at the time (copy the text)
- [ ] **`/api/cron/health` result** if it concerns automation, or the GitHub Actions run number
- [ ] **Railway deployment time and status** if the site is affected (for example "SUCCESS 01:16 UTC")
- [ ] For Google: the Gmail row's status and red error line; for email, the message status and
      reason

<a id="p2-153-report-template-copy-and-paste"></a>

### 15.3 Report template (copy and paste)

```text
Subject: ClientVerse — <short symptom>

When (with timezone):
Where (module / tab / address without tokens):
What I did (exact buttons):
What happened (exact error text):
Expected:
Affected account (email, admin/member):
Browser / device:
Repeatable? (always / sometimes / once; private window?):
/api/health result:
/api/cron/health result or GitHub Actions run # (if automation):
Railway deployment time + status (if site-wide):
Screenshots attached (redacted per manual §13.7): yes/no
```

<a id="p2-154-never-include"></a>

### 15.4 Never include

- passwords, including temporary or "old" ones
- secret values: API keys, `WEBHOOK_CRON_SECRET`, `JWT_SECRET`, `INTEGRATION_ENC_KEY`
- tokens and cookies (`access_token`, `cv_access_token`, anything from developer tools)
- OAuth client secrets
- private `.env` values
- database credentials or `MONGO_URL`
- invitation, portal, booking-manage or webhook links and secrets

If an engineer asks for one of these, refuse. A legitimate engineer never needs it sent to them.
They use Railway access directly.

<a id="p2-155-where-to-report"></a>

### 15.5 Where to report

- **Status and owner actions:** the repository's status issue
  ([ebyron357/Clientverse-crm#10](https://github.com/ebyron357/Clientverse-crm/issues/10)).
  - Required format: **COMPLETED / BLOCKED / EXACT OWNER INPUT REQUIRED**.
  - It is **public**, so never include secrets or client data.
- **Security:** private vulnerability reporting (see `SECURITY.md`).
- **Day-to-day:** your engineering contact's private channel.

---

<a id="p2-appendix-a-acceptance-self-test"></a>

## Appendix A. Acceptance self-test

A first-time owner must be able to answer each question from this manual alone.

| Question | Answer in one line | Where |
|---|---|---|
| What URL do I open? | https://crm.clientverse.io/login | [§1.1](#p2-11-quick-reference-card), [§2.1](#p2-21-addresses) |
| How do I log in? | Email + password → **"Sign in"**. Not Google. | [§3.2](#p2-32-sign-in-with-email-and-password) |
| What account type am I using? | The **admin** account whose email is Railway `ADMIN_EMAIL`, in your organization (first named "ClientVerse HQ") | [§3.3](#p2-33-which-account-the-owner-uses) |
| What do I see after login? | Today — four figures, your plan with reasons, new leads, appointments, tasks, pipeline, clients | [§4.2](#p2-42-what-you-see-after-sign-in-today) |
| Where are Settings? | Main menu → **"Settings"** (pinned at the bottom) | [§1.3](#p2-13-find-settings-and-integrations) |
| Where are Integrations? | **Settings** → **Connections** → **"Integrations"** (or Settings → **"General"** → **"View integrations"**) | [§5.3](#p2-53-where-the-google-controls-are) |
| How do I connect Google? | Registries → Gmail → **"Connect"** → consent (tick all) → **"Google connected"** | [§5.5](#p2-55-connect-google-first-time) |
| How do I reconnect Google? | **"Re-authorize"** on "Needs auth"; otherwise disconnect **both** rows, then Connect. Reconnect once since 2026-10-19. | [§5.6](#p2-56-re-authorize-google), [§5.7](#p2-57-disconnect-safely-and-when-it-is-required) |
| How do I verify gmail.send? | Google Account → third-party connections shows send permission; the connection records `gmail.send`; Operations → Recovery strategies does not list Email | [§5.8](#p2-58-verify-that-gmailsend-was-actually-granted) |
| How do I send a real email? | Engineer-assisted test today (no compose screen), or approve a booking email / form auto-reply — after reconnecting and certification | [§6.1](#p2-61-read-this-first--current-status), [§6.4](#p2-64-procedure-a--send-one-real-outbound-email), [App. C](#p2-appendix-c-engineer-assisted-email-verification) |
| How do I verify the reply came back? | Operations → Conversations → the same thread shows inbound **"Received"** within ~35 minutes | [§6.6](#p2-66-procedure-c--capture-the-reply) |
| How do I manage users? | Team & Access → **"Invite"**, role menu, **"⋯"** → **"Reset password"** / **"Disable access"** | [§8](#p2-8-users-roles-and-administration) |
| How do I recover access? | Owner: change `ADMIN_PASSWORD` in Railway; members: an admin resets it; locked: wait 15 minutes | [§9](#p2-9-account-recovery) |
| How do I know scheduled automations are healthy? | `/api/cron/health` shows `scheduled_jobs_running: true` and a recent `in_process.last_run_at` — or, when the GitHub workflow runs too, a recent `last_authenticated_call_at` | [§11.4](#p2-114-verify-that-automation-is-healthy) |
| What does 401 mean? | Not signed in, or the session expired (workflow: secret mismatch) | [§12](#p2-12-troubleshooting-matrix), [§11.5](#p2-115-what-the-results-mean) |
| What does 500 mean? | A server error — retry once, then escalate with evidence | [§12](#p2-12-troubleshooting-matrix) |
| What do I do when Railway is down? | Check `/api/health` and Railway Deployments; restart the last SUCCESS once; escalate | [§2.3](#p2-23-if-the-site-does-not-load) |
| What evidence do I collect before escalation? | Time, page, action, exact error, screenshot, account, browser, repeatability, health results, deployment | [§15.2](#p2-152-evidence-to-collect-before-you-escalate) |

---

<a id="p2-appendix-b-system-state-on-2026-10-19"></a>

## Appendix B. System state on 2026-10-19

> **Newer state (2026-10-24):** the closeout release `main@6d0d4c6` is running and was verified
> from outside: lead journey 40/40, browser pass 76/76, restore drill passed. See
> [the closeout handoff §13.3](#p1-133-production-acceptance-results).
> The table below is kept as the 2026-10-19 record.

| Fact | Evidence |
|---|---|
| Production serves `main@838f00d` (PR #42) | Railway deployment `e7790295-5af4-4977-8d58-ff600b1a2633`, redeployed 2026-10-19 01:47 UTC to apply the custom-domain variables. The first deployment of this commit, `406f320e-…` (SUCCESS 01:16 UTC), is REMOVED. |
| Service boots with the Gmail adapter and the built-in scheduler | Deploy log: `Registered outbound channel provider: gmail` → `In-process scheduler started for 13 job(s): commitment-risk, work-queue, recovery-runner, booking-reminders, integration-sync, next-best-actions, inbound-email, reconcile-unknown, daily-digest, second-chance, detect-recovery, recovery-strategies, approval-expiry` → `Application startup complete` → `GET /api/health 200` |
| The GitHub workflow also reaches production | Railway logs of `d4d2e07f` and `406f320e`: `200 OK` for all fourteen workflow paths and `GET /api/cron/runs`, 00:19–01:17 UTC |
| No Google connection is being synced | No Google API request in the `d4d2e07f` log through 01:09 UTC, although `integration-sync` ran; that job syncs only active or degraded connections (`run_integration_sync_sweep` in `backend/server.py`). Last known: the refresh refused on 2026-09-30. |
| A connection records the scopes Google granted | Code since PR #42: `google_callback` in `backend/server.py` stores `creds["scopes"]`; `backend/gmail_provider.py` refuses to send without `gmail.send` |
| The custom domain is live | Railway domain status for `crm.clientverse.io`: verified, certificate valid, CNAME propagated. Railway variables `FRONTEND_URL` and `GOOGLE_REDIRECT_URI` point to it; `CORS_ORIGINS` lists it and the Railway address. Railway's HTTP log shows pages served on `crm.clientverse.io` from 01:36 UTC, and Google returning to its callback at 01:42 UTC. |
| Outbound email is off until an admin turns it on | Code: `backend/recovery_strategy.py` (`authorized_channels`, `CONFIGURED_INTEGRATION_STATUSES`). The Gmail catalogue record is seeded `REQUIRES_CONFIGURATION`; only `POST /api/integrations/gmail/sending/enable` certifies it, after Gmail accepts a test email (`send_test` in `backend/gmail_provider.py`), and disconnecting Gmail or reconnecting without `gmail.send` or with another mailbox resets it |
| No screen writes an email to a contact or records consent | Code: `frontend/src/pages/Operations.jsx` calls only conversation handoff and close. The only screen-released emails are booking emails (`frontend/src/pages/Calendar.jsx`) and an approved auto-reply (`frontend/src/pages/WebsiteForms.jsx`). |
| Invitations are emailed only when email delivery is configured | Code: `_email_invitation` in `backend/server.py`; `email_configured()` reads `EMERGENT_EMAIL_KEY` |
| Last full live production smoke | 2026-09-01 on `ca30587` (`docs/evidence/production-smoke-20260901.json`). No live smoke since. |
| Email notifications and AI not configured (as recorded) | `EMERGENT_EMAIL_KEY` and `EMERGENT_LLM_KEY` absent from the Railway variable list recorded on 2026-09-21 ([OWNER_HANDOFF.md](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/OWNER_HANDOFF.md) §3); not re-read since |
| History — 2026-09-30 | The workflow first reached production (runs #3551–#3555, after #3544–#3550 failed on a `401` secret mismatch); Google's token endpoint refused the stored grant at 16:08 UTC (`400`) |

---

<a id="p2-appendix-c-engineer-assisted-email-verification"></a>

## Appendix C. Engineer-assisted email verification

**For an engineer working with the owner.** Every value in angle brackets is a placeholder.
Never paste a real token into a ticket or log.

**Step 0 — prerequisites the engineer confirms:**

1. The Gmail connection is **"Connected"**, made on or after 2026-10-19, and records `gmail.send`
   (§5.6–§5.8).
2. The organization's Gmail catalogue record (`integrations` collection, `name: "Gmail"`, the
   owner organization) is in a certified state — one of `CONNECTED`, `ACTIVE`, `CERTIFIED`,
   `ENABLED`, `AVAILABLE` (`backend/recovery_strategy.py`).
   - An admin sets it with **"Send test & turn on"** ([§5.10](#p2-510-turn-email-sending-on-or-off)). Never change the record by hand.
3. `GET /api/recovery-strategies/channel-authority` shows `email.authorized: true`.

**Secret handling in this procedure.** Run it in `bash`. The password is typed at a hidden
prompt, never on a command line. The session token is held only in the shell, and is passed to
`curl` through a configuration on a file descriptor, so it does not appear in process arguments,
shell history or output. Nothing below prints the password or the token.

```bash
BASE=https://crm.clientverse.io

# 1. Admin session: hidden password prompt; the token stays in this shell only.
read -r  -p "Admin email: " CV_EMAIL
read -rs -p "Admin password (from Railway, not shown): " CV_PASSWORD; echo
TOKEN=$(CV_EMAIL="$CV_EMAIL" CV_PASSWORD="$CV_PASSWORD" python3 -c \
  'import json,os; print(json.dumps({"email": os.environ["CV_EMAIL"], "password": os.environ["CV_PASSWORD"]}))' \
  | curl -sS -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' --data-binary @- \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("token", ""))')
unset CV_PASSWORD
if [ -n "$TOKEN" ]; then echo "signed in"; else echo "sign-in failed"; fi
# cv = curl that sends the session token without exposing it
cv() { curl -sS -K <(printf 'header = "Authorization: Bearer %s"\n' "$TOKEN") "$@"; }

# 2. Conversation on the email channel with the test contact
cv -X POST "$BASE/api/conversations" -H 'Content-Type: application/json' \
  -d '{"channel":"email","subject":"ClientVerse email verification","contact_id":"<contact id>",
       "participants":[{"kind":"contact","id":"<contact id>","address":"<test mailbox>"}]}'

# 3. Consent (admin only; "granted" requires a basis)
cv -X POST "$BASE/api/conversations/<conversation id>/consent" -H 'Content-Type: application/json' \
  -d '{"state":"granted","basis":"Owner-controlled test mailbox","source":"owner verification"}'

# 4. Draft
cv -X POST "$BASE/api/conversations/<conversation id>/messages" -H 'Content-Type: application/json' \
  -d '{"body":"ClientVerse production email test. Please reply to this message.",
       "subject":"ClientVerse email verification","to_address":"<test mailbox>"}'

# 5. Request approval  ->  the OWNER approves in Operations -> Approvals (manual §6.4 step 2)
cv -X POST "$BASE/api/messages/<message id>/request-approval" -H 'Content-Type: application/json' -d '{}'

# 6. Send (after approval): expect status "sent", provider_message_id, rfc822_message_id
cv -X POST "$BASE/api/messages/<message id>/send"

# 7. Duplicate test: same call again -> HTTP 409 message_not_dispatchable
cv -X POST "$BASE/api/messages/<message id>/send"

# 8. After the owner replies and the :10/:40 sweep runs: inbound message with status "received"
cv "$BASE/api/conversations/<conversation id>/messages"

# 9. If the reply is missing: ambiguous replies are parked here, with the reason
cv "$BASE/api/inbound/unmatched"

# 10. Contact timeline entry (activity outcome "reply_received"; also on the contact's Activity tab)
cv "$BASE/api/contacts/<contact id>/timeline"

# 11. End the session: revoke the token on the server, then forget it locally
cv -X POST "$BASE/api/auth/logout"; unset TOKEN
```

Record the results against [§14](#p2-14-production-verification-checklist) rows 13–16, and in the
governing document (M-01), with the ids — never the token.

---

<a id="p2-appendix-d-configuration-and-secrets-register"></a>

## Appendix D. Configuration and secrets register

**Names only. Values live in Railway, GitHub Actions secrets, or the provider's own console.**

| Name | Where | Status (recorded) | Purpose |
|---|---|---|---|
| `ADMIN_EMAIL` | Railway | Set | Owner account email. **Never change.** |
| `ADMIN_PASSWORD` | Railway | Set | Owner password, re-applied every boot |
| `APP_ENV` | Railway | Set | `production` mode (strict security checks) |
| `MONGO_URL`, `DB_NAME` | Railway | Set | Database connection (contains credentials) |
| `Mongo_url` | Railway | Set — **unused duplicate, delete** (O-05) | — |
| `JWT_SECRET` | Railway | Set | Signs sessions; changing it signs everyone out |
| `INTEGRATION_ENC_KEY` | Railway | Set | Encrypts stored integration permissions |
| `IN_PROCESS_SCHEDULER`, `IN_PROCESS_SCHEDULER_JOBS` | Railway | Built-in scheduler on, all 13 jobs (boot log, 2026-10-19) | Built-in scheduler switch and job list |
| `LEAD_SLA_WATCHER` | Railway | Not recorded (on unless `0`) | Lead watcher switch |
| `WEBHOOK_CRON_SECRET` | Railway **and** GitHub Actions | Set in both and matching (workflow calls answered 200 on 2026-10-19) | Authentication for outside scheduler calls |
| `CLIENTVERSE_PRODUCTION_URL` | GitHub Actions | Set (workflow reaches production) | Workflow target |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Railway | Set | Google connection |
| `FRONTEND_URL` | Railway | `https://crm.clientverse.io` (2026-10-19) | Links in invitations, bookings and emails; where Google returns you |
| `CORS_ORIGINS` | Railway | Both production addresses (2026-10-19) | Browser addresses allowed to call the API while signed in |
| `GOOGLE_REDIRECT_URI` | Railway | `https://crm.clientverse.io/api/integrations/google/callback` (2026-10-19) | Must match an authorized redirect URI in Google Cloud |
| `PUBLIC_BACKEND_URL` | Railway | Not set | Not needed while the API and screens share one address |
| `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET` | Railway | Not set | Stripe (O-02) |
| `EMERGENT_EMAIL_KEY`, `EMAIL_FROM_NAME` | Railway | Not set when recorded | Email notifications and invitation emails |
| `EMERGENT_LLM_KEY` | Railway | Not set | AI generation (O-11) |
| `SEED_DEMO_DATA` | Railway | Set (must stay false) | Keeps fictional demo data out of production |
| `LOGIN_LOCKOUT_THRESHOLD`, `LOGIN_LOCKOUT_MINUTES` | Railway | Not set (defaults 5 and 15) | Lockout policy |
| `SECURITY_GATE_*_URL` (three scanners) | Railway | Not set | Security gate (O-14) |
| `DEMO_MEMBER_EMAIL`, `DEMO_MEMBER_PASSWORD`, `ALLOW_INSECURE_JWT` | — | **Must never be set in production** | Test only |
| Google Cloud project name | Google Cloud | UNVERIFIED — OWNER/ENGINEERING INPUT REQUIRED | Owner to record here |

Railway variable presence was last read by name on 2026-09-21 ([OWNER_HANDOFF.md](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/OWNER_HANDOFF.md)
§3). The scheduler rows are updated from the 2026-10-19 boot log and Railway request log.

---

<a id="p2-appendix-e-related-documents"></a>

## Appendix E. Related documents

**Governing and engineering documents.** These are kept for developers; this manual does not
replace them.

- [Canonical governing document](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/CLIENTVERSE_CRM_CANONICAL_GOVERNING_DOCUMENT.md) — scope,
  capability status, owner-action register (O-01…O-16)
- [Project Completion Standard](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/PROJECT_COMPLETION_STANDARD.md) — the closeout baseline this manual
  serves
- [Railway runbook](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/RAILWAY_RUNBOOK.md) and [Production configuration](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/PRODUCTION.md) — deployment
  and scheduler mechanics
- [Website forms guide](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/WEBSITE_FORMS.md) and [Booking guide](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/BOOKING.md) — engineering detail for
  §7.6 and §7.7
- [Owner handoff (2026-09-21, engineering record)](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/OWNER_HANDOFF.md) and
  [Activation report](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/ACTIVATION_REPORT.md) — history and evidence
- [Google provider certification](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/GOOGLE_PROVIDER_CERTIFICATION.md),
  [Stripe provider certification](https://github.com/ebyron357/Clientverse-crm/blob/main/docs/STRIPE_PROVIDER_CERTIFICATION.md)
- [Security policy](https://github.com/ebyron357/Clientverse-crm/blob/main/SECURITY.md), [README](https://github.com/ebyron357/Clientverse-crm/blob/main/README.md)

**Superseded for owner use.** From 2026-09-30, the owner-facing parts of these documents are
superseded by this manual. Each carries a banner saying so:

- `docs/OWNER_HANDOFF.md` — §2, §5, §8, §10
- `docs/ACTIVATION_REPORT.md` — "Administrator Access", "Owner Actions Required"
- `docs/RAILWAY_RUNBOOK.md` — the owner-facing scheduler checks in §6, and the password text in §7
- `docs/PRODUCTION.md`, `docs/DEPLOYMENT_GUIDE.md`, `docs/GOOGLE_PROVIDER_CERTIFICATION.md`
- `docs/STRIPE_PROVIDER_CERTIFICATION.md`, `docs/RELEASE_CERTIFICATION.md`,
  `docs/VALIDATION_EVIDENCE.md`, `docs/closeout/OPENHANDS_PRODUCTION_CERTIFICATION.md` —
  owner actions from the Render era
- `docs/RENDER_ATLAS_RUNBOOK.md`, `docs/HOSTING_SELECTION.md` — whole documents (Render is not
  used)
- `SECURITY.md` — the admin-password rotation line (corrected in place)
- `README.md` — §8, §11, §12 and §14 (corrected in place)

**Project Completion Standard handoff files.** This manual covers the owner-facing content that
the standard expects in `ADMIN_OPERATIONS_MANUAL.md`, `CLIENT_USER_MANUAL.md` and
`TROUBLESHOOTING_AND_SUPPORT.md`. Those files are **not** created separately, so there is one
maintainable manual rather than fragments. The remaining standard files are tracked in the
governing document.

---

<a id="p2-appendix-f-document-control"></a>

## Appendix F. Document control

| Version | Date | Change |
|---|---|---|
| 1.13 | 2026-10-24 | Production closeout (PR #48). The manual is now Part 2 of the closeout package; Part 1 is [the closeout handoff](#part-1). Changes: **"Continue with Google" removed**, so email and password is the only sign-in (§1.1, §1.2, §3.1, §8.3, §9.6, §10.1, §12). The job ledger is limited to the owner's organization (§8.1). Client portal links stay on screen with **"Copy"** and can be **"Revoke"**d (§7.15, §8.12, §12). The MCP kill switch is greyed out for members (§7.18). All procedures use `https://crm.clientverse.io` (§1.1, §1.2, §2.2, §11.4, Appendices A and C); the Google redirect address is the custom domain (§5.5). Google status is consistent with the 2026-10-19 reconnection (§1.4, §10.1, §14 row 12). The custom-domain switch is recorded as done (§13.3). |
| 1.12 | 2026-10-19 | The account switcher (§7.25) shows as soon as an agency admin signs in, not only after a reload. Changing your password while working in a client account keeps you in it (§3.9). |
| 1.11 | 2026-10-19 | **Agency and client accounts** (§7.25, new): client accounts under an agency, the account switcher and the "working in" banner, opening a client account as an agency admin (checked on every request), creating accounts from a snapshot, and pushing a snapshot to many accounts with a preview per account. **Settings → Agency → "Client accounts"** (§4.3); roles (§8.1). Booking pages loaded into a workspace are hosted by someone on its team, or arrive paused (§7.24, §7.25). |
| 1.10 | 2026-10-19 | **Snapshots** (§7.24, new): save this workspace's setup (pipeline stages, fields, booking pages, forms, automations, shared views — never records, people, links or secrets), share it with a code shown once, download it as a file, and load one into a workspace through a preview that only adds what is missing. **Settings → Workspace → "Snapshots"**, admin only (§4.3, §8.1). §7.23: a template's stages also stay when a stage in use would change between open, won and lost. |
| 1.9 | 2026-10-19 | **Industry templates** (§7.23, new): six starting setups (agency, real estate, home services, health and wellness, coaching, B2B sales) that add a pipeline, booking pages, a form, fields and draft automations, only where missing. **Settings → Workspace → "Industry template"** (§4.3); the first step of **"Set up your workspace"** on Today is now **"Choose your industry template"** (§4.2); applying one is admin-only (§8.1). |
| 1.8 | 2026-10-19 | **Automations** (§7.22, new): triggers, steps, stop rules, recipes, test runs and run receipts. The main-menu **"Automations"** entry opens it (§4.3, §4.4). Client Operations moves to **Settings → Workspace → "Client portal and playbooks"** (§4.3, §7.15). **Workflows** leaves "Coming soon". §7.21 item 3 corrected for the 1,000-person contact list. |
| 1.7 | 2026-10-19 | **Today** replaces the Command Center page at `/dashboard` (§4.2, §7.1, §4.3, §4.4, §1.4 step 4, §3.2, checklist row 3, the quick answers): four figures, **"Your plan"** in a fixed order with the reason for each item, new leads with **"Call"**, appointments, tasks with a tick to complete, pipeline, clients; won deals and outcome progress are on the Pipeline board and Client 360. |
| 1.6 | 2026-10-19 | The new app shell: an 11-item main menu (Today, Leads, Inbox, Contacts, Pipeline, Calendar, Tasks, Approvals, Clients, Automations, Reports) with counts, **"Settings"** pinned at the bottom, and a Settings menu (Workspace, Capture, Connections, Compliance, Developer, Coming soon) replacing the grouped sidebar; search moved to the top bar. Updated §1.2–1.4, §3.4, §4.1–4.3 (new map), §5.3, the "Where" lines of §7, §7.19, §8.2, §14 row 20, §15.2, Appendix A. Applies from the deployment that carries this change; until then production shows the grouped sidebar of v1.3. **Settings → Workspace → "Fields"** opens the field manager of v1.5. |
| 1.5 | 2026-10-19 | Contacts: built-in and saved views, filters, columns (§7.4 item 4); lifecycle stage and how the CRM sets it (item 6); your own fields on contacts, companies and deals — **Settings → Fields** (item 8, §7.5, §4.3); **"Set from history"** in the **"Clean up"** card (item 10); the contact list now shows up to 1,000 people. |
| 1.4 | 2026-10-19 | One record per real thing: existing clients (§7.2), companies filled in from forms and email domains, the **"Clean up"** card and merging (§7.4), one open deal per person (§7.5), the **"Company"** question (§7.6), the **"Meeting"** booking preset (§7.7). |
| 1.3 | 2026-10-19 | Email sending switch: §5.10 (new), §5.7, §5.8, §6.1, capability status, troubleshooting, checklist row 13, escalation, Appendices B and C. Google reconnected with send permission (§6.1). Disconnecting Calendar no longer cancels Gmail's permission (§5.7). |
| 1.2 | 2026-10-19 | `crm.clientverse.io` is live: addresses (§2.1–2.2, §3.2), Google addresses (§10.2), Appendices B and D. Review fixes ([ebyron357/Clientverse-crm#43](https://github.com/ebyron357/Clientverse-crm/pull/43)): signing everyone out when the owner password may be known (§9.2, §13.4); scheduler health when the GitHub workflow runs first (§11.4, §11.5, checklist row 17, Appendix A); access codes in `/portal/` and `/booking/manage/` addresses (§13.7, §15.2). |
| 1.1 | 2026-10-19 | Refreshed for `main@838f00d` (PRs #35–#42). Scheduler: built into the CRM (13 jobs), with the GitHub workflow as an optional second driver; health is read from `scheduled_jobs_running` and `in_process`. Sign-in: the redesigned page, password change in Settings, admin reset of a temporary password, invitation sign-up and invitation emails. Screens: collapsible sidebar groups, breadcrumbs, theme button, side panels; new Leads, Tasks, Website Forms and Calendar sections; contacts and deals can now be edited and archived; deals move by drag or **"⋯"** → **"Move to stage"**. Email: booking emails and form auto-replies are the screen-released emails; a connection records the scopes Google granted (PR #42), so reconnect once; a refused lookup never counts as "not sent". Custom domain `crm.clientverse.io` recorded as added but not live. Verified against the code and Railway deployment records and logs of 2026-10-19. |
| 1.0 | 2026-09-30 | First complete owner/admin manual ([ebyron357/Clientverse-crm#33](https://github.com/ebyron357/Clientverse-crm/issues/33)). Verified against `main@8f23f63` code, Railway deployment records and logs, and GitHub Actions run records of 2026-09-30. |

**Keeping it true**

- Update this manual **in the same change** as any code change that alters a screen label, a
  route, a sign-in rule, a Google scope, a scheduler job or an owner procedure.
- When a production fact changes (for example certification granted, or the Google permission
  restored), update [Appendix B](#p2-appendix-b-system-state-on-2026-10-19) and the governing
  document together.
- Never add a secret value. Names only.
