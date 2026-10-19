# ClientVerse CRM — Owner/Admin Manual

| | |
|---|---|
| **Document** | ClientVerse CRM Owner/Admin Manual |
| **Version** | 1.2 |
| **Date** | 2026-10-19 |
| **Repository** | `ebyron357/Clientverse-crm` |
| **Branch documented** | `main` — written against `main@838f00d` (PR #42), which production runs |
| **Production environment** | Railway project `welcoming-vibrancy` → environment `production` → service `clientverse-crm-production` |
| **Production URL** | https://crm.clientverse.io (the Railway address https://clientverse-crm-production-production.up.railway.app reaches the same CRM) |
| **Sign-in page** | https://crm.clientverse.io/login |
| **Purpose** | Everything the owner needs to reach, sign in to, operate, administer, verify and get help with ClientVerse CRM — without a developer beside them and without reading source code. |
| **Intended audience** | Primary: the CRM owner / business administrator. Secondary: a future client admin or operator. |
| **Authority** | The official owner/admin handoff source of truth, registered in [the canonical governing document](CLIENTVERSE_CRM_CANONICAL_GOVERNING_DOCUMENT.md) (§0.2, §0.5). Product scope and capability status remain governed by that document. |
| **Tracking issue** | [ebyron357/Clientverse-crm#33](https://github.com/ebyron357/Clientverse-crm/issues/33) |

> **No secrets are in this manual.** It never contains passwords, API keys, OAuth client
> secrets, tokens, invite links, portal links or database addresses. Where one is needed,
> it names the place the secret is kept (for example the Railway variable `ADMIN_PASSWORD`)
> and never the value.

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
[Chapter 14](#14-production-verification-checklist) is the final live confirmation.

---

## Table of Contents

1. [Owner Quick Start](#1-owner-quick-start)
2. [System Access](#2-system-access)
3. [Login and Access](#3-login-and-access)
4. [First Login Orientation](#4-first-login-orientation)
5. [Google / Gmail Setup](#5-google--gmail-setup)
6. [Email Production Verification](#6-email-production-verification)
7. [CRM Daily Use](#7-crm-daily-use)
8. [Users, Roles, and Administration](#8-users-roles-and-administration)
9. [Account Recovery](#9-account-recovery)
10. [Integrations](#10-integrations)
11. [Scheduler / Automations](#11-scheduler--automations)
12. [Troubleshooting Matrix](#12-troubleshooting-matrix)
13. [Security and Owner Safety](#13-security-and-owner-safety)
14. [Production Verification Checklist](#14-production-verification-checklist)
15. [Support / Escalation](#15-support--escalation)

Appendices

- [A. Acceptance self-test — questions this manual answers](#appendix-a-acceptance-self-test)
- [B. System state on 2026-10-19](#appendix-b-system-state-on-2026-10-19)
- [C. Engineer-assisted email verification (API procedure)](#appendix-c-engineer-assisted-email-verification)
- [D. Configuration and secrets register (names only)](#appendix-d-configuration-and-secrets-register)
- [E. Related documents](#appendix-e-related-documents)
- [F. Document control](#appendix-f-document-control)

---

## 1. Owner Quick Start

The shortest path from nothing to a working, checked CRM. About ten minutes.

### 1.1 Quick-reference card

| What | Where |
|---|---|
| Production CRM | https://clientverse-crm-production-production.up.railway.app |
| Sign in | https://clientverse-crm-production-production.up.railway.app/login |
| Is the service up? (no sign-in needed) | https://clientverse-crm-production-production.up.railway.app/api/health |
| Is the automation running? (sign in as admin first) | https://clientverse-crm-production-production.up.railway.app/api/cron/health |
| Hosting dashboard | Railway → project `welcoming-vibrancy` → service `clientverse-crm-production` (https://railway.com/project/bbcb2596-d6f9-45c5-9c03-59cb97f373ea) |
| Optional second scheduler (GitHub) | https://github.com/ebyron357/Clientverse-crm/actions/workflows/scheduled-jobs.yml |
| Sign-in method | Email address + password. **Not** "Continue with Google" ([§3.1](#31-supported-sign-in-methods)) |
| Your account | The address in the Railway variable `ADMIN_EMAIL`, with the password in the Railway variable `ADMIN_PASSWORD` ([§3.3](#33-which-account-the-owner-uses)) |

### 1.2 Sign in

1. Open **https://clientverse-crm-production-production.up.railway.app/login** in a current
   Chrome, Edge, Firefox or Safari.
2. Under the heading **"Sign in to ClientVerse"**, type your owner email in **"Work email"** and
   your password in **"Password"**. The eye button beside the password shows or hides what you typed.
3. Click **"Sign in"**.
4. **Check:** the page changes to **Command Center**. At the bottom of the left sidebar you see
   your name and **"Workspace admin"**.

**Warning:** Do not click **"Continue with Google"** (the first button on the page) or
**"Create a workspace"** at the bottom. Both can create a *separate, empty* organization that is
not your CRM ([§3.1](#31-supported-sign-in-methods)).

### 1.3 Find Settings and Integrations

The sidebar groups **Command**, **CRM** and **Client Success** are always open. The others —
including **Platform** — open when you click their name.

- **Settings:** left sidebar → click **Platform** → **"Settings"**.
- **Integrations** (Google, Stripe): left sidebar → **Platform** → **"Registries"**. The
  **"Integrations"** tab opens first. You can also go through **Settings** → the
  **"Integrations"** section → **"View integrations"**.

### 1.4 First things to verify

Do these five checks after every first sign-in, and whenever something seems wrong.

| # | Check | Where | Healthy answer |
|---|---|---|---|
| 1 | You are an admin | **Settings** → **"Profile"** → **"Access level"** | **"Workspace admin"** |
| 2 | The service and database are up | Open `/api/health` (link in [§1.1](#11-quick-reference-card)) | `"status":"ok"` and `"database":"up"` |
| 3 | Google is connected | **Registries** → **Integrations** → **Gmail** row | **"Connected"**, no red error line. If it says **"Needs auth"**, follow [§5.6](#56-re-authorize-google) |
| 4 | Automation is running | Open `/api/cron/health` while signed in as admin | `"scheduled_jobs_running": true` ([§11.4](#114-verify-that-automation-is-healthy)) |
| 5 | No critical alerts | **Action Center** (sidebar → **Command**) | Nothing unexpected under **"Needs action"** |

**Check 3 is expected to fail until you reconnect Google once.** Google refused to refresh the
saved Google permission on 2026-09-30 (Verified (live, 2026-09-30): Railway log
`POST https://oauth2.googleapis.com/token` → `400 Bad Request`), and on 2026-10-19 production's
log showed no Google sync at all — consistent with no working Google connection. Since
2026-10-19 the CRM also records exactly which permissions Google granted, so a connection made
before that date must be renewed anyway. Reconnect: [§5.6](#56-re-authorize-google) or
[§5.7](#57-disconnect-safely-and-when-it-is-required). What the Gmail row shows today is
UNVERIFIED — OWNER/ENGINEERING INPUT REQUIRED.

### 1.5 If something is broken

- Look up the symptom in the [Troubleshooting Matrix](#12-troubleshooting-matrix).
- If the matrix says to escalate, collect the evidence in [§15.2](#152-evidence-to-collect-before-you-escalate).
  Never include a password or secret.

---

## 2. System Access

### 2.1 Addresses

| Environment | Address | Use it? |
|---|---|---|
| **Production** | **https://crm.clientverse.io** | **Yes — use this address.** |
| Production, Railway address | https://clientverse-crm-production-production.up.railway.app | Same CRM, same data. It keeps working, so older links and the Stripe webhook still reach production. Signing in on one address does not sign you in on the other. |
| Custom domain status | Verified (live, 2026-10-19): Railway reports `crm.clientverse.io` verified, certificate valid, CNAME `crm` → `br0g4oob.up.railway.app` propagated. Railway sets `FRONTEND_URL` and `GOOGLE_REDIRECT_URI` to this address, and `CORS_ORIGINS` lists both addresses ([§10.2](#102-google--gmail-and-google-calendar)). | — |
| Staging | None. No staging environment is configured or documented. The only deployment path is Railway `production`. | — |
| Old preview and hosting addresses (Render, Manus, OpenHands, Emergent previews) | Historical only. | **No.** They are not production. Never run a second copy against the production database. |

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

### 2.3 If the site does not load

1. Check your own connection by opening any other website.
2. Open https://clientverse-crm-production-production.up.railway.app/api/health and read the result:

   | What you see | Meaning | Next step |
   |---|---|---|
   | `"status":"ok"` and `"database":"up"` | The CRM is running. The problem is your browser or session. | [§9.4](#94-stale-browser-session) |
   | `"status":"degraded"` and `"database":"down"` (HTTP 503) | The application is up but cannot reach its database (MongoDB Atlas). | Escalate to engineering ([§15](#15-support--escalation)). The owner can check MongoDB Atlas for an outage or a network-access change. |
   | A Railway-branded error page ("Application failed to respond", "Not Found") | No healthy deployment is serving. | Step 3 |
   | The browser cannot connect at all | DNS, network or Railway outage. | Step 3 |

3. Open the Railway dashboard → project `welcoming-vibrancy` → service
   `clientverse-crm-production` → **Deployments**, and read the newest entry:
   - **BUILDING / DEPLOYING** — a deploy is in progress. A normal build takes about 2–3 minutes
     (2026-10-19: 01:14 → 01:16 UTC). Wait 5 minutes and retry.
   - **SUCCESS** — the service should be up. Click **View logs**, look for errors, and escalate with
     a screenshot.
   - **FAILED** or **CRASHED** — escalate to engineering at once, with the deployment time and a
     screenshot of the log ([§15](#15-support--escalation)). Railway normally keeps the previous
     healthy deployment serving while a new deployment fails its health check, so a failed *new*
     deploy does not always mean the site is down.
4. **Safe owner action:** on the latest **SUCCESS** deployment, use **Restart** (Railway ⋮ menu) once.
   **Needs engineering agreement:** Rollback, Redeploy of an older commit, or any change to
   variables other than `ADMIN_PASSWORD`.

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

## 3. Login and Access

### 3.1 Supported sign-in methods

| Method | Status | Should the owner use it? |
|---|---|---|
| **Email + password** | Verified (code). Last proven live in production on 2026-09-01 (`scripts/proof_of_life.mjs` against `ca30587`). | **Yes — this is the owner's method.** |
| **"Continue with Google"** button (first on the sign-in page) | Sends you to a third-party sign-in service (`auth.emergentagent.com`) left over from the platform the CRM was prototyped on. It is **not** the owner's Google Cloud app and **not** the Gmail connection. Whether it works in production is UNVERIFIED — OWNER/ENGINEERING INPUT REQUIRED. | **No.** If the Google address has no ClientVerse account, it silently creates a new, empty organization in which that person is admin. It also ignores invitation links. |
| **"Create a workspace"** (self-registration, at the bottom of the sign-in page) | Verified (code). It works, but always creates a **new, separate organization** with the new person as its admin. It gives no access to your data. | **No** for the owner. Team members join through invitations, which create their account directly inside your team ([§8.3](#83-what-to-tell-the-invitee-accepting-an-invitation)). |

### 3.2 Sign in with email and password

1. Go to https://crm.clientverse.io/login.
2. The heading reads **"Sign in to ClientVerse"**. If it reads **"Create your workspace"**, click
   **"Sign in"** at the bottom to switch back.
3. **"Work email"** — your owner email. **"Password"** — your password.
4. Click **"Sign in"**. The button shows **"Please wait…"** while it works.
5. **Check:** you arrive on **Command Center** (`/dashboard`).
6. If a red box shows **"Invalid email or password"**, see [§9.1](#91-wrong-password) and
   [§9.3](#93-account-locked-out). The CRM gives the **same message** for a wrong password, an
   unknown address and a locked account, on purpose.
7. If the screen **"Choose your own password"** appears instead, you signed in with a temporary
   password an admin gave you — see [§9.2](#92-forgotten-password).

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
  a change made in **Settings** → **"Change password"** ([§3.9](#39-change-your-own-password))
  lasts only until the next deploy. Change the owner password in Railway ([§9.2](#92-forgotten-password)).
- **Warning: never change `ADMIN_EMAIL`.** At the next start the server would create a brand-new,
  empty **"ClientVerse HQ"** organization for the new address. Your existing data would stay with
  the old account. If the owner login address must change, escalate to engineering.

### 3.4 Verify the sign-in and your role

- **Sidebar footer** (bottom left) shows your initials, your name and either **"Workspace admin"**
  or **"Team member"**.
- **Settings** → **"Profile"** shows **"Name"**, **"Email"** and **"Access level"**.
- Admins see **"Team & Access"** in the sidebar under **Platform**. Members do not.

### 3.5 Sign out

1. Click the sign-out icon at the bottom right of the sidebar (its tooltip reads **"Sign out"**).
   Alternatively: **Settings** → **"Security"** → **"Session"** → **"Sign out"**.
2. **Check:** you return to the sign-in page.
3. Signing out cancels that session on the server immediately. Closing the tab does **not** sign
   you out — a session otherwise lasts **7 days**. Always sign out on a shared computer.

### 3.6 Password requirements

- **New passwords need at least 8 characters**: when you change your password, when a teammate
  creates their account from an invitation, and when a new workspace is created. Verified (code).
- `ADMIN_PASSWORD` in Railway is not checked for length.
- **Owner policy — follow it anyway:** at least 16 characters, unique to ClientVerse, and generated
  and stored by a password manager.
- A **temporary password** from an admin reset looks like three groups of four characters joined by
  dashes. It opens nothing until the person chooses their own ([§8.8](#88-reset-a-members-password)).

### 3.7 Lockout behaviour

Verified (code); defaults, which the recorded production variable list does not override.

- After **5 failed sign-ins in a row** for the same email address, that address is locked for
  **15 minutes**.
- While it is locked, even the **correct** password shows **"Invalid email or password"**.
- A wrong **current** password in **"Change password"** counts as a failed sign-in too.
- The failure count resets only on a successful sign-in, or when an admin resets that person's
  password. So after a lockout ends, **one more wrong password locks it again** for another
  15 minutes. Make your next attempt count.
- The lock follows the email address, on every device and browser. See [§9.3](#93-account-locked-out).

### 3.8 What must never appear in a document, issue or message

The value of `ADMIN_PASSWORD` or any password (including temporary ones), and `JWT_SECRET`,
`INTEGRATION_ENC_KEY`, `WEBHOOK_CRON_SECRET`, `GOOGLE_CLIENT_SECRET`, `STRIPE_API_KEY`,
`STRIPE_WEBHOOK_SECRET` or `MONGO_URL`.

That also covers:

- session cookies and tokens (`access_token`, `cv_access_token`)
- invitation links (`/invite?token=…`)
- client-portal links (`/portal/…`) and booking manage links (`/booking/manage/…`)
- webhook signing secrets

See [Chapter 13](#13-security-and-owner-safety).

### 3.9 Change your own password

1. **Settings** → **"Security"** → **"Password"** → **"Change password"**.
2. In **"Change your password"**, type **"Current password"**, then **"New password"** and
   **"New password again"** (at least 8 characters). **"Show passwords"** reveals what you typed.
3. Click **"Change password"**.
4. **Check:** the message **"Password changed"**. You stay signed in here; every other phone or
   computer signed in to your account is signed out.

- **Owner account:** see the warning in [§3.3](#33-which-account-the-owner-uses) — use Railway.
- An account that signs in only with Google has no ClientVerse password to change.

---

## 4. First Login Orientation

### 4.1 Screen landmarks

| Landmark | Where | What it does |
|---|---|---|
| **Sidebar** | Left edge | All modules, in groups. **Command**, **CRM** and **Client Success** are always open; click any other group's name to open or close it (the browser remembers). The **"Collapse navigation"** button shrinks it to icons. On a phone it opens from the menu button. |
| **Search** | Top of the sidebar: **"Search"** (Ctrl/⌘ K) | Jumps to a *module or action*. It does **not** search your records ([§7.19](#719-search)). |
| **Sidebar footer** | Bottom of sidebar | Your initials, name and role (**"Workspace admin"** / **"Team member"**), the theme button (light → dark → match device) and the sign-out icon. |
| **Breadcrumb** | Top bar, left | The sidebar group and the page you are on, for example *CRM › Contacts*. |
| **"Create"** | Top bar, right | Quick create: company, contact, opportunity or client workspace. |
| **Bell** | Top bar, far right | Notifications, with an unread count ([§7.12](#712-action-center-and-notifications)). |
| **Amber dot** beside a sidebar item | Sidebar | The module is **not active yet** (placeholder page). |
| **Side panel** | Right edge, over the page | Opening a contact, company, deal, lead or task slides its record in from the right: tabs on one side, a **"Details"** panel on the other. Close it with ✕ or Esc. |

### 4.2 What you see after sign-in: Command Center

**Command Center** (`/dashboard`) is the home page. Its header reads **"Command Center"** —
*"Revenue, delivery risk and the client relationships that need your team next."* — with the
buttons **"Refresh"** and **"Review pipeline"**. From top to bottom:

1. **A strip of four figures.** Click any one to open its list.
   - **"Open pipeline"**
   - **"Won revenue"**
   - **"Active clients"**
   - **"Delivery risk"**
2. **"Set up your workspace"** — a 4-step setup checklist. Dismissing it hides it in this browser
   only. It reappears in another browser, or after clearing site data.
3. **"Next actions"** — up to five ranked follow-ups, each a link.
4. **"Next best actions"** — ranked recommendations across all clients, with **"Accept"**,
   **"Done"**, **"Snooze"** and **"Not relevant"**.
5. **"Client health"** — the health score of every client workspace.
6. On the right (below, on a narrow screen): **"Pipeline by stage"**, **"Outcome momentum"**,
   **"Operational alerts"** (with **"Scan now"**) and **"Connection health"** (admins only).

A new, empty CRM shows friendly empty states — for example **"Your pipeline starts here"**. That
is correct, not an error.

### 4.3 Sidebar map — every item and whether it is active

Verified (code): `frontend/src/platform/modules.js`, `frontend/src/App.js`.

| Group | Sidebar item | Opens | Status | Admin only |
|---|---|---|---|---|
| Command | **Command Center** | `/dashboard` | Active | |
| Command | **Action Center** | `/notifications` | Active | |
| CRM | **Leads** | `/leads` | Active | |
| CRM | **Tasks** | `/tasks` | Active | |
| CRM | **Website Forms** | `/website-forms` | Active | Creating and changing forms: admin |
| CRM | **Contacts** | `/contacts` | Active | |
| CRM | **Companies** | `/companies` | Active | |
| CRM | **Deals** | `/deals` (the Pipeline board) | Active | **"Customize stages"**: admin |
| CRM | **Pipelines** | `/pipeline` (the same board) | Active | |
| Client Success | **Client 360** | `/workspaces` | Active | |
| Client Success | **Client Operations** | `/client-ops` | Active | Some buttons: admin |
| Communications | **Email** | `/communications/email` | **Not active** — "Configuration required" | |
| Communications | **Unified Inbox** | `/operations?tab=conversations` | Active (read, hand off and close only — [§7.13](#713-operations)) | |
| Communications | **SMS** | `/communications/sms` | **Not active** — "Configuration required" | |
| Communications | **Calling** | `/communications/calling` | **Not active** — "Backend contract pending" | |
| Scheduling | **Calendar** | `/scheduling/calendar` | Active — online booking ([§7.7](#77-calendar-and-online-booking)) | Booking pages and approving emails: admin |
| Automation | **Workflows** | `/automation/workflows` | **Not active** — "Backend contract pending" | |
| Automation | **Approvals** | `/operations?tab=approvals` | Active | Deciding: admin |
| Automation | **Operations** | `/operations` | Active | Some buttons: admin |
| Revenue | **Revenue Operations** | `/revenue` | **Not active** — "Backend contract pending" | |
| Revenue | **Recovery Proof** | `/proof` | Active | |
| Support | **Support** | `/support` | **Not active** — "Backend contract pending" | |
| Intelligence | **Reporting** | `/intelligence/reporting` | **Not active** — "Backend contract pending" | |
| Intelligence | **Relationship Intelligence** | `/intelligence/relationships` | **Not active** — "Backend contract pending" | |
| Platform | **Migration** | `/platform/migration` | **Not active** — "Backend contract pending" | |
| Platform | **Registries** (integrations) | `/registries` | Active | Connect/sync: admin |
| Platform | **MCP Console** | `/mcp` | Active | Kill switch and undo: admin |
| Platform | **Automation & Audit** | `/audit` | Active | Undo: admin |
| Platform | **Team & Access** | `/team` | Active | **Yes** (hidden from members) |
| Platform | **Settings** | `/settings` | Active | |
| Platform | **Knowledge** | `/platform/knowledge` | **Not active** — "Backend contract pending" | |

Pages that have **no sidebar entry**:

- **Field Ops** — `/field`. Type the address to open it.
- **Directory** — `/directory`. The combined contacts-and-companies page.
- **Accept invitation** — `/invite`. Opened from an invitation.
- **Client portal** — `/portal/…`. For clients, opened from a portal link.
- **Public booking page** — `/book/…`. For the public, opened from a booking link ([§7.7](#77-calendar-and-online-booking)).
- **Manage a booking** — `/booking/manage/…`. For the person who booked, from their own link.

A **not active** item opens a placeholder page headed with the module's name, with a
**"Configuration required"** or **"Backend contract pending"** badge and a **"Module contract"**
card. It says: *"No sample records or simulated writes are shown."* Nothing can be done there.
That is by design, not a fault.

### 4.4 Module quick reference

Full procedures are in [Chapter 7](#7-crm-daily-use).

| Module | What it is for | Key actions | Do **not** | Saved when you see |
|---|---|---|---|---|
| **Command Center** | Today's priorities | Open figures, act on next actions | Treat an empty dashboard as broken | Lists refresh; messages for decisions |
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

## 5. Google / Gmail Setup

### 5.1 What the Google connection does

One Google consent connects **two** rows at once: **Gmail** and **Google Calendar**.
Verified (code). With the connection active, the CRM:

- **reads Gmail** — the 25 most recent messages' headers (sender, recipients, subject, labels and
  snippet), matched to your contacts by email address. They appear on a client's **Client 360** →
  **Activity** → **"Recent email threads"** — **only when** the matched contact belongs to a
  company that has a Client 360 workspace.
- **captures replies** — every 30 minutes (at :10 and :40 past the hour) it checks the inbox for
  the last 7 days and attaches replies to the conversations they answer ([§6](#6-email-production-verification)).
- **sends email** — only messages a human approved, and only through the connected mailbox
  ([§6](#6-email-production-verification)).
- **reads Google Calendar** — the next 25 events, matched to contacts by attendee email. They
  appear under **Client 360** → **Activity** → **"Upcoming meetings"**, with the same
  company-and-workspace condition. Online booking also leaves out times when the connected
  calendar is busy ([§7.7](#77-calendar-and-online-booking)).

Only **admins** can connect, re-authorize, sync or disconnect. Members see **"Admin manages"**.

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
  ([§5.6](#56-re-authorize-google) or [§5.7](#57-disconnect-safely-and-when-it-is-required)) to make
  the record true.

### 5.3 Where the Google controls are

- **Path A:** **Settings** → the **"Integrations"** section lists **Gmail**, **Google Calendar**
  and **Stripe** with a status. Admins see **"Connect"** or **"Manage"** on each row, and
  **"View integrations"** at the bottom. All of them open the Registries page.
- **Path B:** sidebar → **Platform** → **"Registries"**.

Either path lands on the **Registries** page, on the **"Integrations"** tab (the first of
**"Integrations"**, **"MCP Servers"**, **"Plugins"**, **"Webhooks"**). The tab shows:

- a **"Status honesty"** note
- one row each for **Gmail**, **Google Calendar** and **Stripe**
- below them, **"Governed capability contracts"** — catalogue records, for information

The Gmail row's description still reads *"Read-only message + thread metadata…"*. That text is
older than the send feature; the connection also carries send permission when Google granted it
([§5.2](#52-exact-google-permissions-scopes-the-crm-requests)).

### 5.4 Read the connection status

| Registries status | Settings label | Meaning | Buttons (admin) | Your action |
|---|---|---|---|---|
| **"Not connected"** | Not connected | No Google permission is stored | **"Connect"** | [§5.5](#55-connect-google-first-time) |
| **"Connecting…"** | Connecting… | A sync is running (it shows briefly during every sync), or a consent was started and never finished — for example cancelled at Google | **"Sync"**, **"Disconnect"** | If still shown after 10 minutes: full reset ([§5.7](#57-disconnect-safely-and-when-it-is-required)) |
| **"Connected"** | Connected | The permission is active | **"Sync"**, **"Disconnect"** | None. Confirm send permission ([§5.8](#58-verify-that-gmailsend-was-actually-granted)) |
| **"Degraded"** | Needs attention | The last sync failed for a non-permission reason | **"Sync"**, **"Disconnect"** | **"Sync"** once. If still degraded, escalate. |
| **"Needs auth"** + **"Re-authorize"** tag | Needs auth | Google refused to refresh the permission (expired or revoked) | **"Re-authorize"**, **"Sync"**, **"Disconnect"** | [§5.6](#56-re-authorize-google) |
| **"Error"** | Error | Connecting failed while exchanging the Google code | **"Reconnect"**, **"Sync"**, **"Disconnect"** | **"Reconnect"**. If it repeats, see [§5.9](#59-google-troubleshooting). |

Other parts of the row:

- **"Stale"** tag — connected, but no successful sync for more than 24 hours.
- **Red line under the row** — the last error, for example `token_refresh_failed:400`.
- **The Google address** (small monospaced text) — the mailbox connected.
- **Small grey tags** (`gmail.readonly`, `gmail.send`, …) — the permissions recorded on the
  connection. The row shows **at most four**, so a tag that is not shown may still be recorded.
  See [§5.8](#58-verify-that-gmailsend-was-actually-granted).
- **"Last sync …"** or **"No successful sync yet"**.

### 5.5 Connect Google (first time)

**One-time prerequisites (owner, in Google Cloud)** — governing-document owner action O-01:

- **Recorded done:** `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set in Railway. The boot log
  line `Registered outbound channel provider: gmail` (Verified (live, 2026-10-19)) confirms the
  server sees them.
- The OAuth client's **authorized redirect URI** must be exactly
  `https://clientverse-crm-production-production.up.railway.app/api/integrations/google/callback`.
- The **Gmail API** and the **Google Calendar API** must be enabled.
- The **OAuth consent screen** must list the scopes in [§5.2](#52-exact-google-permissions-scopes-the-crm-requests).
  If its publishing status is **Testing**, the Google account you connect must be listed as a test
  user.
- The Google Cloud project's name is UNVERIFIED — OWNER/ENGINEERING INPUT REQUIRED. The owner
  should record it in [Appendix D](#appendix-d-configuration-and-secrets-register).

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
9. Verify send permission ([§5.8](#58-verify-that-gmailsend-was-actually-granted)).

**If it fails**

- **"Google authorization failed"** — you cancelled or refused, or Google returned an error. The
  rows may be left on **"Connecting…"**. Do the full reset in [§5.7](#57-disconnect-safely-and-when-it-is-required).
- **"Authorization link expired — try again"** — more than 10 minutes passed. Start again from
  step 2.

### 5.6 Re-authorize Google

Use this when the Gmail or Google Calendar row shows **"Needs auth"** or **"Error"**.

1. On the **Gmail** row, click **"Re-authorize"** (or **"Reconnect"** on an **"Error"** row).
2. Complete the Google consent exactly as in [§5.5](#55-connect-google-first-time), steps 3–6.
3. **Check:** **"Google connected"**. Both rows read **"Connected"**, with no red error line.
4. Click **"Sync"** on the Gmail row to confirm.

If the rows return to **"Needs auth"** within about a week, see
[§5.9](#59-google-troubleshooting) → *Token refresh returns 400*.

### 5.7 Disconnect safely, and when it is required

**Disconnect first, then connect, when:**

- the row shows **"Connected"** or **"Degraded"** but you need a *fresh* permission. There is no
  **"Re-authorize"** button in those states. This applies when:
  - the connection was made before 2026-10-19, so its recorded permissions are not the ones Google
    granted ([§5.2](#52-exact-google-permissions-scopes-the-crm-requests))
  - you left **send email on your behalf** unticked
  - you want to use a different Google mailbox
- the rows are stuck on **"Connecting…"**
- the connection keeps looping back to **"Needs auth"** or **"Error"**

**Full reset procedure**

1. Tell your team that Gmail sync, reply capture and outbound email pause until you reconnect.
   Do this when no approved email is waiting to be sent.
2. On the **Gmail** row, click **"Disconnect"**. **Check:** **"Disconnected Gmail"**.
3. On the **Google Calendar** row, click **"Disconnect"**. **Check:**
   **"Disconnected Google Calendar"**.
   - **Why both:** both rows share one saved Google permission. Disconnecting either row
     revokes it at Google.
     - The CRM deletes its saved copy when you disconnect a row while the other row is **not**
       **"Connected"**.
     - If the other row is still **"Connected"**, the saved copy stays (already revoked) until you
       disconnect that row too.
     - Disconnecting both rows always leaves a clean slate.
4. (Recommended for a stale or looping permission.) Open **Google Account** → **Security** →
   the list of third-party apps and services with access to your account. Find your ClientVerse
   app and remove its access. ClientVerse already asks Google to revoke on Disconnect; this
   confirms it.
5. **Check:** both rows read **"Not connected"**, with no Google address shown.
6. Connect again ([§5.5](#55-connect-google-first-time)).

**What Disconnect does not do:** it does not delete email and meeting records already shown on
Client 360, and it does not delete conversations or messages.

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
      reading email, the permission is read-only: do the full reset in [§5.7](#57-disconnect-safely-and-when-it-is-required)
      and tick every box.
3. **The CRM's authorization view.** Open **Operations** → **"Recovery strategies"** tab. The amber
   box **"Outbound channels not authorised"** lists every channel that cannot send (**SMS** and
   **Phone** always appear; no provider exists for them). Then read:
   - **"Email — No connected email provider (gmail is not connected)."** — the Gmail row is not
     **"Connected"**. Re-authorize or reconnect.
   - **"Email — gmail is connected, but no integration record marks it configured for this tenant,
     so outbound email is not certified."** — the Google side is fine. Sending is held by the CRM's
     **certification gate**, which only engineering can clear ([§6.1](#61-read-this-first--current-status)).
   - **Email not listed at all** — the email channel is authorized. (This view does not check
     `gmail.send`; checks 1 and 2 do.)
4. **Definitive proof.** A real message reaches status **"sent"** ([§6](#6-email-production-verification)).
   Without `gmail.send` it is refused instead, with *"The Gmail connection for this tenant is
   read-only … Reconnect Google and grant send access."*

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
- **Owner action:** Re-authorize ([§5.6](#56-re-authorize-google)).
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

1. Do the full reset in [§5.7](#57-disconnect-safely-and-when-it-is-required), including step 4.
2. Connect again, finishing within 10 minutes, and tick every permission.
3. If Google itself shows a `redirect_uri_mismatch` error, the Google Cloud redirect URI is
   wrong ([§5.5](#55-connect-google-first-time) prerequisites). That is an owner fix in Google Cloud.
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
| "Sync failed: not_connected" | No stored permission | Connect ([§5.5](#55-connect-google-first-time)) |

**Who does what**

| Owner can do it | Needs engineering |
|---|---|
| Connect, Re-authorize, Sync, Disconnect | Changing `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` or `PUBLIC_BACKEND_URL` (with the owner) |
| Google Cloud consent screen, test users, redirect URI, publishing status | Outbound email certification ([§6.1](#61-read-this-first--current-status)) |
| Removing app access in the Google account | Any error that survives a full reset |

---

## 6. Email Production Verification

### 6.1 Read this first — current status

**Status on 2026-10-19: BLOCKED.** Three verified reasons, and each needs a different person:

1. **The Google permission needs reconnecting** ([§1.4](#14-first-things-to-verify)): Google
   refused the refresh on 2026-09-30, and any connection made before 2026-10-19 must be renewed so
   the CRM records what Google granted. **Owner:** [§5.6](#56-re-authorize-google) or
   [§5.7](#57-disconnect-safely-and-when-it-is-required).
2. **No screen lets you write your own email to a contact, or record a contact's consent.**
   - **Operations** → **"Conversations"** can only *read* a thread, **"Hand to human"** /
     **"Hand to agent"**, and **"Close"**.
   - Creating a conversation, recording consent, drafting, requesting approval and sending exist
     only as server API calls. Verified (code).
   - Two screens release emails the CRM itself wrote, once reasons 1 and 3 are cleared:
     **Calendar** booking emails (**"Review and approve"** → **"Approve and send"**,
     [§7.7](#77-calendar-and-online-booking)) and a **Website Forms** auto-reply whose wording an
     admin approved ([§7.6](#76-website-forms)).
   - **Engineering-assisted:** for the full send / duplicate / reply test below, an engineer
     performs the API steps ([Appendix C](#appendix-c-engineer-assisted-email-verification)) while
     the owner approves and verifies in the screens.
3. **The outbound certification gate.**
   - The CRM lets email go out only when the organization's **Gmail catalogue record** (shown under
     **Registries** → **"Governed capability contracts"**) is in a certified state.
   - It is created as **REQUIRES_CONFIGURATION**, and no screen or API changes it. Verified (code).
     Whether production's record has since been changed by hand is UNVERIFIED — OWNER/ENGINEERING
     INPUT REQUIRED.
   - Until engineering records that certification, every send is refused with
     *"…no integration record marks it configured for this tenant, so outbound email is not
     certified."*
   - **Engineering**, after the owner approves certification.

Reply capture also needs the scheduler, which runs inside the CRM ([§11](#11-scheduler--automations)).

**How do I send a real email?** Today, only through the engineer-assisted procedure below, or by
approving a booking email or form auto-reply, once reasons 1 and 3 are cleared. The Gmail
**"Sync"** button does not send anything; it is a read-only mirror of the inbox. Invitation and
alert emails use a separate delivery service, not Gmail ([§10.6](#106-email-notifications-and-ai)).

### 6.2 Result definitions

| Result | Means |
|---|---|
| **PASS** | Every expected result in the step was observed, and its evidence was captured ([§6.8](#68-what-counts-as-pass-evidence)). |
| **FAIL** | The step ran, and the CRM or Google did something other than expected — for example two copies arrived, or a reply landed on the wrong conversation. |
| **BLOCKED** | The step could not run because a prerequisite is missing (for example **"Needs auth"**, or the certification gate). Record the exact blocking message. |
| **NOT TESTED** | Not attempted yet. |

### 6.3 Prerequisites (owner-verifiable)

- [ ] The **Gmail** row is **"Connected"**, shows the sending mailbox, and was connected on or
      after 2026-10-19 ([§5.4](#54-read-the-connection-status)).
- [ ] Google shows the send permission ([§5.8](#58-verify-that-gmailsend-was-actually-granted), check 2).
- [ ] **Operations** → **"Recovery strategies"** does **not** list **Email** as not authorised ([§5.8](#58-verify-that-gmailsend-was-actually-granted), check 3).
- [ ] The scheduler is healthy ([§11.4](#114-verify-that-automation-is-healthy)). Reply capture depends on it.
- [ ] A **test contact** exists: **Contacts** → **"New contact"** → name `CV Email Test`, and an
      **Email** you control that is **not** the connected mailbox (for example a personal
      secondary address). The reply must come *from* the contact *to* the connected mailbox.
- [ ] An engineer is available for the API steps ([Appendix C](#appendix-c-engineer-assisted-email-verification)).

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

### 6.6 Procedure C — capture the reply

1. **Owner:** from the test mailbox, **Reply** to the email received. Keep the subject and do not
   change recipients.
2. Wait for the next reply sweep. The CRM's built-in scheduler runs `inbound-email` at **:10 and
   :40** past every hour (UTC), so allow up to **35 minutes**. To start it at once, use GitHub →
   **Actions** → **Scheduled jobs** → **"Run workflow"** → jobs: `inbound-email` (only while that
   optional workflow is configured, [§11.7](#117-run-the-jobs-by-hand)).
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

### 6.7 Where failures surface

| Where | What you see | Meaning |
|---|---|---|
| **Operations** → **"Approvals"** row | **"Approving this will not unblock it — …"** | A prerequisite blocks the send (not connected, consent, certification) |
| **Operations** → **"Conversations"** | Figure **"Blocked messages"** above 0; the message status **"Blocked"**, with the reason | The CRM refused before contacting Google, and named why |
| Same, status **"Failed"** | Only the status. The screen does not show Google's reason; an engineer reads it from the message's `error` field (`GET /api/messages/<id>`) — e.g. *"Gmail rejected the message with HTTP 403…"* | Google refused. A 403 usually means the send permission is missing — full reset ([§5.7](#57-disconnect-safely-and-when-it-is-required)) |
| Same, status **"Outcome unknown"** | Only the status. Google did not confirm either way | **Never re-send.** The reconcile sweep (:10/:40) asks Gmail. If Google access is revoked or refused, the message deliberately stays "Outcome unknown" until access is restored — a refused lookup never counts as "not sent". Escalate if it persists after 1 hour with Google **"Connected"**. |
| **Calendar** → an appointment | **"Waiting for approval"**, **"Could not send"**, or *"Email isn't connected, so nothing was emailed."* | A booking email awaits an admin, failed, or the email channel is not authorised ([§7.7](#77-calendar-and-online-booking)) |
| **Registries** → Gmail row, red line | e.g. `token_refresh_failed:400` | Permission problem ([§5.9](#59-google-troubleshooting)) |
| **Operations** → **"Recovery strategies"** amber box | **"Email — …"** | Channel not authorised ([§5.8](#58-verify-that-gmailsend-was-actually-granted)) |
| **Automation & Audit** | `communication_message.refused` | A send was refused; the reason is on the message |
| `/api/cron/health` | `last_failed_job` is `inbound-email` or `reconcile-unknown` | Reply capture or reconciliation failed ([§11](#11-scheduler--automations)) |

### 6.8 What counts as PASS evidence

- **Outbound:** screenshots of the conversation showing **"Sent"**, of Gmail **Sent**, and of the
  received email with its time. The engineer records the message's `provider_message_id` and
  `rfc822_message_id`. These are identifiers, not secrets.
- **Duplicate:** the refusal (HTTP 409 text) and a screenshot showing a single copy.
- **Inbound:** a screenshot of the same thread with the **inbound** / **"Received"** message, the
  `communication_message.received` audit event, and the contact's **"Activity"** history.
- **Redact** personal email addresses before sharing screenshots outside the company.

---

## 7. CRM Daily Use

Each section gives: **Purpose**, **Where**, **Common actions**, **Common mistakes**, and **Saved when**.

### 7.1 Command Center

- **Purpose:** your daily starting point — pipeline value, won revenue, active clients, delivery
  risk, recommended next steps, alerts and client health.
- **Where:** sidebar → **Command** → **"Command Center"**; or click the ClientVerse logo.
- **Common actions:**
  1. Click a figure in the top strip to open its list.
  2. Work the **"Next actions"** list from the top.
  3. In **"Next best actions"**, choose **"Accept"**, **"Done"**, **"Snooze"** (a day) or
     **"Not relevant"**.
  4. Under **"Operational alerts"**, click **"Scan now"** for a fresh alert check. Use the ✓ and ✕
     icons to acknowledge or resolve.
- **Common mistakes:**
  - Treating empty sections as a fault.
  - Expecting **"Connection health"** to show for members — it is admin-only.
- **Saved when:** **"Alert scan complete (N new)"**; recommendation buttons change the list, and
  only failures show a message (the server's reason, or **"Could not record that decision"**).

### 7.2 Leads

- **Purpose:** every lead from your website forms and online booking, with its speed-to-lead
  clock and what the CRM did automatically.
- **Where:** sidebar → **CRM** → **"Leads"**. New teammates land here after accepting an invitation.
- **Common actions:**
  1. Read the tabs **"New"**, **"Contacted"**, **"Closed"**, **"Spam"**, **"All"**. Search by name,
     email, phone, address or MLS number; filter by form (**"All forms"**). The list refreshes
     every 30 seconds.
  2. Click a lead to open it. Use **"Call …"** / **"Text"** to reach the person from your phone,
     then **"Mark contacted"**. Or open the contact (**"Open contact to log a call"**) and log what
     happened.
  3. **"Close"** a lead that is finished, **"Spam"** junk, **"Reopen"** a closed one.
  4. **"Export CSV"** downloads the leads in the current view as `leads.csv`.
- **How the clock works:** every new lead gets a call-back task in **Tasks** (due 5 minutes after
  arrival by default) and an alert. Logging a call, text, email or meeting on the contact, or
  ticking that task done, marks the lead contacted. A note does not. Verified (code).
- **Common mistakes:**
  - Marking a lead contacted before you have reached them — it stops the clock.
  - Marking a real person as spam.
  - Treating a lead tagged **"Test lead"** as real: it came from **"Send a test lead"**
    ([§7.6](#76-website-forms)).
- **Saved when:** **"Marked as contacted"**, **"Lead marked closed"**, **"Lead marked spam"**.

### 7.3 Tasks

- **Purpose:** every call-back and follow-up in one list, with what is late at the top.
- **Where:** sidebar → **CRM** → **"Tasks"**.
- **Common actions:**
  1. Read the tabs **"Overdue"**, **"Today"**, **"Upcoming"** and **"Done"** (finished tasks stay
     7 days). Admins can switch between **"My tasks"** and **"Everyone"**.
  2. **"New task"**: **"What needs doing"** (required), **"Who it's about (optional)"**, a due date
     and time, **"Assign to"**, **"Notes (optional)"** → **"Add task"**. Unassigned tasks can be
     taken by anyone on the team.
  3. Open a task to change it (**"Save changes"**), **"Mark done"** or **"Reopen"**.
- **Common mistakes:** leaving a task unassigned when one person should own it.
- **Saved when:** **"Task added"**, **"Changes saved"**; **"Undo"** on the message reverses a tick.

### 7.4 Contacts and Companies

- **Purpose:** the people and accounts behind every relationship.
- **Where:**
  - sidebar → **CRM** → **"Contacts"** or **"Companies"**
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
  4. **Open a contact** (side panel):
     - tabs **"Activity"**, **"Deals"**, **"Tasks"**, **"Website requests"**, and the
       **"Details"** panel
     - **"Edit"** (or **"Edit · add phone"**) → change details → **"Save changes"**
     - **"Activity"** → **"Log what happened"**: Call, Text, Email, Meeting or Note. Logging an
       email records it; *nothing is sent to them*.
     - **"Archive contact"** hides them from the list (nothing is deleted). To bring one back,
       turn on **"Show archived"**, open them, and click **"Restore"**.
  5. **Open a company** (side panel): tabs **"Contacts"**, **"Deals"**, **"Client 360"**, and the
     **"Details"** panel. It is read-only.
- **Common mistakes:**
  - **Companies cannot be edited, archived or deleted from the screens.** Type carefully.
    Engineering can edit or archive a company through the server. Nothing can be deleted at all.
  - Creating the same company twice — search first.
  - Leaving out a contact's email, which stops email and calendar matching.
  - Each list shows at most **200** records. Beyond that, older ones are not visible in the
    screens (UNVERIFIED — OWNER/ENGINEERING INPUT REQUIRED whether any organization has reached this).
- **Saved when:** **"Company created"**, **"Contact created"**, **"Contact saved"**,
  **"Contact archived"** / **"Contact restored"**. On failure: **"Could not create company"** /
  **"Could not create contact"**, with the reason.

### 7.5 Deals and Pipeline

- **Purpose:** move revenue opportunities through your stages — by default **Lead → Qualified →
  Proposal → Negotiation → Closed won**, with **Closed lost** behind **"Show lost deals"**.
- **Where:** sidebar → **CRM** → **"Deals"** or **"Pipelines"**. Both open the **Pipeline** board.
- **Common actions:**
  1. **"New deal"**: **"Deal name"**, **"Who is it with?"**, **"Company (optional)"**,
     **"Expected value"**, **"Currency"**, **"Starting stage"**, **"Expected close date"**,
     **"Owner"** → **"Create deal"**.
  2. **Move a deal:** drag its card to another column, or use the card's **"⋯"** → **"Move to
     stage"** (the only way on a phone).
  3. **Open a deal** (side panel): edit its name, value, close date, owner and notes →
     **"Save changes"**; **"Log activity"** (Call, Email, Meeting, Note — logging an email sends
     nothing); read **"Stage history"**; move it on with **"Move to …"** or **"Mark as won"**.
  4. **Winning** a deal that has a company **automatically creates a Client 360 workspace**:
     **"Deal won — client workspace created"**, with **"Open workspace"**. Without a company the
     message is **"Deal marked as won"** and no workspace is made.
  5. Filter with **"Search deals, people or companies"** and **"Everyone's deals"** / **"My deals"**.
  6. Admin: **"Customize stages"** renames, adds, reorders or removes stages → **"Save stages"**.
- **Common mistakes:**
  - Looking for a lost deal on the board — turn on **"Show lost deals"**. A lost deal can be moved
    back to an open stage the same way as any other.
  - **"Archive this deal"** takes it off the board entirely. It stays listed on its contact's
    **"Deals"** tab, where you can open it and **"Restore"** it.
- **Saved when:** **"Deal created"**, **"Moved to {stage}"**, **"Deal saved"**. If a move fails,
  the card jumps back and **"That move did not save"** appears.

### 7.6 Website Forms

- **Purpose:** the forms on your website. Every submission becomes a contact, an owner, a deal, a
  call-back task and an alert, automatically.
- **Where:** sidebar → **CRM** → **"Website Forms"**. Engineering guide: [WEBSITE_FORMS.md](WEBSITE_FORMS.md).
- **Common actions (admin):**
  1. **"New form"** → choose a **"Template"** → **"Create form"**.
  2. Work through the tabs **"Fields"**, **"Settings"**, **"Automation"**, **"Auto-reply"** and
     **"Embed & test"**, then **"Save changes"**.
  3. **"Embed & test"**: copy the embed code for your website, and **"Send a test lead"** to prove
     the whole chain. **"Open form"** opens the hosted page.
  4. **"Auto-reply"**: write the automatic reply, save it, read it, then **"Approve this wording"**.
     Each reply is still checked before it goes (consent, and an authorised email channel —
     [§6.1](#61-read-this-first--current-status)). Changing the wording needs a new approval.
- **Members** can view forms and copy embed codes only.
- **Common mistakes:** approving reply wording you have not read; forgetting that test leads land
  in **Leads**, tagged **"Test lead"**.
- **Saved when:** **"Test lead processed end to end"**; the header shows **"Saved"**.

### 7.7 Calendar and online booking

- **Purpose:** appointments people book online, the booking pages they book through, and each
  agent's hours.
- **Where:** sidebar → click **Scheduling** → **"Calendar"**. Engineering guide: [BOOKING.md](BOOKING.md).
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
     **"New booking page"**, **"Edit"**, pause, and **"Copy link"** or an embed code.
     **"Copy my link"** copies your own booking page link.
  4. **"Availability"** tab: each agent's weekly hours and days off.
- **Public pages:** `/book/…` is your public booking page (no sign-in). `/booking/manage/…` is the
  person's private link to view, reschedule or cancel — treat it like a password.
- **Common mistakes:** approving an email you have not read; leaving past appointments without an
  outcome.
- **Saved when:** **"Approved and sent"** (or *"Approved — it couldn't be sent yet; the reason is
  on the appointment"*); **"Booking link copied"**.

### 7.8 Client 360 workspaces

- **Purpose:** one operating page per client — health, commitments, outcomes, activity, timeline,
  tasks, deliverables, requests and approvals.
- **Where:** sidebar → **Client Success** → **"Client 360"** (list), then click a row.
- **Common actions:**
  1. **"New workspace"**: **"Workspace name"**, **"Company"**, **"Lifecycle stage"** →
     **"Create workspace"**. Or win a deal ([§7.5](#75-deals-and-pipeline)).
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
     15 minutes anyway ([§11](#11-scheduler--automations)).
  5. **Approvals:** an admin sees **"Approve"** / **"Reject"**. Members see **"Awaiting admin"**.
- **Common mistakes:**
  - Only the title can be entered for tasks, deliverables and requests, and nothing here can be
    edited or deleted later. (The **Tasks** page in the CRM group is separate and fully editable.)
  - The owner and due date of a commitment cannot be changed after creation.
  - Status-menu changes show no message if they fail. Refresh the tab to confirm.
- **Saved when:** **"Commitment added"**, **"Updated"**, **"Approval requested"**,
  **"SLA check complete · N at-risk, N breached"**.

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

### 7.12 Action Center and notifications

- **Purpose:** client risks and delivery blockers that need a person, plus your notification
  preferences.
- **Where:** sidebar → **Command** → **"Action Center"**; or the bell → the gear icon.
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
  ([§10.6](#106-email-notifications-and-ai)).
- **Common mistakes:** resolving an alert before the underlying issue is fixed — it will reappear.
- **Saved when:** **"Alert acknowledged"** / **"Alert resolved"**,
  **"Your notification preferences were saved"**, **"Team notification defaults were saved"**.

### 7.13 Operations

- **Purpose:** the control room for automation — recommendations, the durable work queue,
  recovery strategies, approvals, client conversations and the security gate.
- **Where:** sidebar → **Automation** → **"Operations"**.
- **Tabs and common actions:**

  | Tab | What you can do | Admin only |
  |---|---|---|
  | **"Next best actions"** | **"Refresh"**; **"Accept"** / **"Done"** / **"Snooze"** / **"Not relevant"** | — |
  | **"Work queue"** | **"Acknowledge"**, **"Resolve"**; figures **"Open"**, **"Retry scheduled"**, **"Dead letter"**, **"Needs operator"** | **"Run recovery detection"**, **"Replay"** |
  | **"Recovery strategies"** | Read proposed strategies. The amber box **"Outbound channels not authorised"** ([§5.8](#58-verify-that-gmailsend-was-actually-granted)) | **"Compose strategies"** |
  | **"Approvals"** | Read what is waiting — including booking emails and form auto-replies | **"Approve"**, **"Reject"** |
  | **"Conversations"** | Read threads; **"Hand to human"** / **"Hand to agent"**; **"Close"** | — |
  | **"Security gate"** | Read scanner and component status (read-only) | — |

- **Common mistakes:**
  - **Approving without reading.** **"Approve"** takes effect on one click, with no confirmation.
    The summary on the row shows what will run or be sent (message text is cut at 500
    characters).
  - Expecting **"Conversations"** to compose or send email. It cannot ([§6.1](#61-read-this-first--current-status)).
  - Expecting a consent button. Consent is recorded only by an admin through the API.
  - The **"Security gate"** shows scanners as not configured until the owner supplies scanner
    endpoints (governing document O-14). That is the intended safe default.
- **Saved when:**
  - **"Approved"** / **"Rejected"**
  - **"Acknowledged"** / **"Resolved"** / **"Replayed"**
  - **"Handoff recorded"**, **"Closed"**
  - **"Detection complete · N new, N already open"**

### 7.14 Recovery Proof

- **Purpose:** what the recovery engine found, what was actually sent, and what was recovered,
  with the records that prove it.
- **Where:** sidebar → **Revenue** → **"Recovery Proof"**.
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
- The sidebar **"Reporting"** item is not active; this is the live report.

### 7.15 Client Operations and the client portal

- **Purpose:** client-facing coordination per workspace — secure portal links, documents,
  estimates and invoices (local records only), appointments, referrals, review requests, safe
  internal automations and playbooks.
- **Where:** sidebar → **Client Success** → **"Client Operations"**. Pick a workspace in
  **"Choose a workspace"**.
  - Tabs: **"Overview"**, **"Client portal"**, **"Commercial"**.
  - **"More workflows"** adds **"Appointments"**, **"Growth"**, **"Safe automation"** and
    **"Capacity & playbooks"**.
- **Common actions:**
  1. Admin: **"Client portal"** → **"Client-facing label"** → **"Create secure portal link"**.
     - The link is copied to your clipboard (**"Secure portal URL copied"**).
     - **Paste it somewhere safe immediately — it is never shown again.**
     - The client opens it without signing in. They see commitments, approved documents and
       issued invoices, and can submit a request.
  2. **"Commercial"** → **"Add document"**, **"Create estimate"** (admin).
  3. **"Appointments"** → **"Schedule"**; **"Prepare reminder"** creates an *internal* task only.
     (Online booking is the separate **Calendar** module.)
  4. **"Growth"** → **"Add referral source"**; **"Prepare for approval"** (review request, admin).
  5. **"Safe automation"** (admin) → **"Enable safe workflow"**, **"Run safely"**. These only
     create internal tasks.
  6. **"Capacity & playbooks"** (admin) → **"Apply"** a playbook's task sequence.
- **Common mistakes:**
  - Losing a portal link. There is no revoke button and no way to show it again; ask engineering
    to revoke a leaked link.
  - Members clicking **"Create estimate"** or **"Prepare for approval"** get a permission refusal.
  - **"Create invoice"** appears only for sent or approved estimates, and the screens cannot mark an
    estimate sent. Treat invoicing here as a record, not billing. Stripe is not configured.
  - Nothing here sends email or SMS, or charges a card.
- **Saved when:** a message per action — e.g. **"Client portal link created"**,
  **"Estimate drafted"**, **"Appointment scheduled"**. Errors read **"Action could not be completed"**.

### 7.16 Field Ops

- **Purpose:** on-site check-ins from a phone.
- **Where:** type `/field` after the production address. There is no sidebar entry.
- **Common actions:**
  - **"Check in to a client workspace"**: **"Workspace"**, **"Location label"**, **"Onsite note"**,
    then **"Save check-in"**
  - **"Prepare reminder"** on an upcoming appointment
- **Common mistakes:** expecting photo upload. It is not available.
- **Saved when:** **"Field check-in saved"**.

### 7.17 Automation & Audit

- **Purpose:** the organization's record of every significant change, including approvals, sends,
  password changes and resets, permission denials (`authz.denied`) and team changes. Failed
  sign-ins are **not** recorded here.
- **Where:** sidebar → **Platform** → **"Automation & Audit"**; or **Settings** → **"Organization"**
  → **"Open audit"**.
- **Common actions:** read the newest events; filter by event, actor or record, and by resource.
  Admin: **"Undo"** on an approved AI-tool write, within the undo window (default 60 minutes), with
  a **required reason**.
- **Saved when:** **"Reversed"** (undo).

### 7.18 MCP Console (governed AI tools)

- **Purpose:** run the CRM's governed tools. Read tools run at once; write tools need approval
  first.
- **Where:** sidebar → **Platform** → **"MCP Console"**.
- **Common actions:**
  - Pick a tool, fill its fields, **"Invoke tool"**.
  - A Level-2 write returns **"Approval required (Level 2)"**; an admin approves it in
    **Operations** → **"Approvals"**.
  - Admin: the **"Kill switch"** disables all tools at once.
  - Admin: **"Undo"** in **"Execution history"**.
- **Common mistakes:** flipping the kill switch as a test. Everyone sees the toggle, but only admins
  can change it.
- **Saved when:** **"{tool} → {status}"**; **"Kill switch ON — tools disabled"** /
  **"Kill switch OFF — tools live"**.

### 7.19 Search

- **Ctrl/⌘ K** (the **"Search"** box at the top of the sidebar) opens **"Search modules and
  actions…"**. It finds **modules and actions only** — for example "Pipeline", "Team & Access",
  "Create opportunity". **It does not find contacts, companies, deals or workspaces.**
- To find a record, open its list page and use that page's search box:
  - Leads: name, email, phone, address or MLS number
  - Contacts: **"Search name, phone, email…"**; Companies: **"Search companies…"**
  - Pipeline: **"Search deals, people or companies"**
  - Client 360: **"Search clients…"**
  - a workspace's **"Search timeline…"**

### 7.20 Import and export

- **Export:** only **Leads** → **"Export CSV"** in the screens. Contacts, companies and deals can be
  exported as CSV by engineering through the server.
- **Import:** no screen. The server has a CSV import (admin) that engineering can run.
- For a full data copy (a backup, or offboarding a client), ask engineering. See also
  [§13.5](#135-backups-and-data-export).

### 7.21 Known screen limitations (current code)

These are verified behaviours of the deployed code. None loses data.

1. **Companies and workspaces cannot be edited or archived** in the screens. Contacts and deals can.
   Nothing can be deleted.
2. **No screen writes your own email to a contact, records consent, or shows unmatched inbound
   mail** ([§6.1](#61-read-this-first--current-status)).
3. **Company and contact lists show at most 200 records** each (the Pipeline loads up to 1,000 deals).
4. **No message on some failures:** workspace status menus and outcome updates. Refresh to confirm
   the change saved.
5. **A session that expires mid-use does not redirect** to the sign-in page. Pages show
   "…unavailable" errors instead. Reload the page to sign in again ([§9.4](#94-stale-browser-session)).
6. **Some buttons are visible to members but refused by the server:**
   - the MCP **"Kill switch"**
   - the webhook on/off switch
   - **"Create estimate"**
   - **"Prepare for approval"**

---

## 8. Users, Roles, and Administration

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
| Record conversation consent (API only) | ✓ | ✗ |
| MCP kill switch, undo, workspace undo window | ✓ | ✗ |
| Webhook create / enable / reveal secret / rotate secret | ✓ | ✗ |
| Portal links, estimates, invoices, review requests, safe automations, playbooks | ✓ | ✗ |
| Team notification defaults; **"Send digest"**; rename the business | ✓ | ✗ |
| Read the scheduler ledger (`/api/cron/health`, `/api/cron/runs`) | ✓ | ✗ |

A member who tries an admin action sees **"You do not have permission to perform this action"**.

### 8.2 Invite a user

1. Sidebar → **Platform** → **"Team & Access"**.
2. Click **"Invite"**. The dialog **"Invite a teammate"** opens.
3. **"Their email"** — the person's work address. **"What they can do"** — **"Member"** (default)
   or **"Admin"**.
4. Click **"Create invite"**.
5. **Check:**
   - **"Invitation emailed"** and the dialog **"Invitation sent"** — the CRM emailed the link. This
     happens only when email delivery is configured ([§10.6](#106-email-notifications-and-ai)).
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
5. **Do not use "Continue with Google"** for this: it ignores the invitation and can create a
   separate organization.

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

### 8.4 Resend an invitation

In **"Pending invitations"**, click **"Resend"** on the row.

- It creates a **new link** and restarts the 7 days. **The old link stops working.**
- **Check:** **"Invitation emailed again"** or **"New invite link ready"**, and the dialog shows the
  new link to share.

### 8.5 Revoke an invitation

In **"Pending invitations"**, click **"Revoke"**.

- **There is no confirmation.**
- **Check:** **"Invitation revoked"**. The link now shows **"This invitation was cancelled"**.

### 8.6 Expired invitations

Expired, revoked and accepted invitations move to **"Invitation history"**, which has no buttons.
To re-invite, create a **new** invitation for the same email ([§8.2](#82-invite-a-user)).

### 8.7 Change a member's role

1. Members table → the person's **"Role"** menu → **Admin** or **Member**.
2. **Check:** **"{email} is now {role}"**.
3. **The last active admin cannot be demoted:** *"Cannot demote the last active admin. Promote
   another admin first."*

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
- **Not available** for yourself (use [§3.9](#39-change-your-own-password)), for disabled members,
  or for accounts that sign in only with Google.
- **Do not reset the owner account this way.** Its password comes from Railway
  ([§9.2](#92-forgotten-password)).

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

### 8.11 Ownership considerations

- **Keep at least two active admins.** If one is locked out or leaves, the other can still manage
  the team and integrations, and reset passwords.
- The owner account is tied to `ADMIN_EMAIL`, and its password is always reset to `ADMIN_PASSWORD`
  at each deploy ([§3.3](#33-which-account-the-owner-uses)).
- **To hand day-to-day ownership to someone:** invite them as **admin**, confirm they can sign in,
  then decide with engineering whether `ADMIN_EMAIL` stays as is. Never change it yourself.
- Records carry an "owner". Deals and tasks can be reassigned in their side panels, and a
  contact's owner by an admin; other records cannot.

### 8.12 Actions that need engineering

| Request | Why |
|---|---|
| Delete a user, or change a user's email address | No screen or API |
| Change `ADMIN_EMAIL` | It would create a new, empty organization |
| Edit or archive companies; import data; export anything but leads | API only, no screen. Deleting records, and editing workspaces, are not possible even through the API. |
| Revoke a client portal link | No revoke button |
| Certify outbound email | Certification record ([§6.1](#61-read-this-first--current-status)) |
| Clear a lockout on the owner account early | Database change ([§9.3](#93-account-locked-out)) |

---

## 9. Account Recovery

### 9.1 Wrong password

1. Retype the password carefully. Check Caps Lock and the email address; the eye button shows
   what you typed.
2. **Stop after 3 failures.** At 5 the account locks for 15 minutes ([§3.7](#37-lockout-behaviour)).
3. **Owner account:** copy the password from the Railway variable `ADMIN_PASSWORD` (Railway →
   service → **Variables**) or from your password manager.
4. Still failing: [§9.2](#92-forgotten-password).

### 9.2 Forgotten password

There is **no self-service "forgot password" email**. The sign-in page says *"Forgot it? Your
workspace admin can reset it from Team & Access."*

**Member account:** an admin resets it ([§8.8](#88-reset-a-members-password)). The member then
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
back ([§3.3](#33-which-account-the-owner-uses)) — unless Railway is set to the same new password, as
below.

**If the owner password may be known to someone else** (leaked, shared, typed on a shared
computer), the Railway change above is not enough on its own. It replaces the password but signs
nobody out: a browser already signed in stays signed in for up to 7 days. Do this instead:

1. Sign in, then **Settings** → **"Change password"** to a new password
   ([§3.9](#39-change-your-own-password)). Every other phone and computer is signed out.
2. **Straight away**, set Railway `ADMIN_PASSWORD` to that **same** new password and deploy (steps
   1–4 above). Until you do, the next deploy puts the old password back.
3. If you cannot sign in, reset the password in Railway first (steps 1–5 above), sign in with it,
   then do steps 1 and 2 with a second new password. Settings refuses a new password that matches
   the current one.

### 9.3 Account locked out

1. Stop trying — attempts while locked do not help.
2. Wait **15 minutes** after the fifth failure.
3. Try **once**, carefully, with the correct password. One more failure re-locks the account for
   another 15 minutes.
4. If you do not know the correct password, reset it first ([§9.2](#92-forgotten-password)), then
   wait out the lock.
5. **A member** can be let in at once: an admin's **"Reset password"** also clears the lock
   ([§8.8](#88-reset-a-members-password)). For the owner account, only engineering can clear a lock
   early, in the database.

### 9.4 Stale browser session

**Symptoms:** after a long break, pages show **"… unavailable"** or empty lists, while
`/api/health` is fine. Sessions last 7 days. When one expires or is revoked mid-use, the screens do
not jump to the sign-in page by themselves. *"Your password was changed. Please sign in again."*
means your password was changed on another device or reset by an admin.

1. **Reload** the page (F5 / ⌘R). If the session has ended you land on the sign-in page — sign in
   again.
2. If you land back on the same errors, do the full reset ([§9.8](#98-full-sign-out-and-sign-in-reset)).

### 9.5 "Your access to this workspace has been disabled"

An admin disabled your membership. Ask an admin to **"Enable access"** for you
([§8.9](#89-offboard-a-user-disable)). If you are the only admin, you cannot be disabled — the
server prevents it.

### 9.6 "Continue with Google" failed

That button is not a supported owner sign-in method ([§3.1](#31-supported-sign-in-methods)). Use
email and password.

- If it took you to a strange empty CRM, it created a separate organization. Sign out, and sign in
  with email and password.
- If someone else signed in this way by mistake, have them tell an admin. Engineering can clean up
  the stray organization.

### 9.7 Email and password rejected, but you are sure the password is right

Likely causes, most likely first:

1. The account is **locked** — wait 15 minutes ([§9.3](#93-account-locked-out)).
2. **The password was changed:** `ADMIN_PASSWORD` in Railway (owner), **"Change password"** on
   another device, or an admin reset (members get a temporary password from the admin).
3. A **deployment is still in progress** after a password change — wait for SUCCESS.
4. **The email address is different** — for example a typo, or another alias of the same mailbox.
   The owner account is the exact `ADMIN_EMAIL` value.
5. The site is down or degraded — check `/api/health` ([§2.3](#23-if-the-site-does-not-load)).

### 9.8 Full sign-out and sign-in reset

1. Click the sign-out icon if you can reach it.
2. Close every ClientVerse tab.
3. Clear this site's cookies and data:
   - **Chrome / Edge:** padlock icon → **Site settings** → **Delete data**
   - **Firefox:** padlock → **Clear cookies and site data**
   - **Safari:** Settings → **Privacy** → **Manage Website Data**
4. Open the sign-in page fresh and sign in.

### 9.9 Who can fix what

| Problem | Owner, in the CRM | Owner, in Railway | Engineering |
|---|---|---|---|
| Forgotten **owner** password | — | ✓ `ADMIN_PASSWORD` ([§9.2](#92-forgotten-password)) | — |
| Forgotten **member** password | ✓ **"Reset password"** ([§8.8](#88-reset-a-members-password)) | — | — |
| Member locked out | ✓ **"Reset password"**, or wait 15 minutes | — | ✓ Clear early |
| Owner locked out | Wait 15 minutes | — | ✓ Clear early |
| Member disabled | ✓ **"Enable access"** (another admin) | — | — |
| All admins locked out | — | ✓ Reset the owner password | ✓ |
| Stale session | ✓ Reload / reset (§9.4, §9.8) | — | — |
| Site down / database down | — | Restart the latest SUCCESS deployment once | ✓ |
| Wrong `ADMIN_EMAIL` or stray organizations | — | — | ✓ |

---

## 10. Integrations

Statuses use the labels from [the Project Completion Standard](PROJECT_COMPLETION_STANDARD.md):
LIVE + VERIFIED, CONFIGURATION REQUIRED, AVAILABLE BUT NOT CERTIFIED, DEGRADED, NOT IMPLEMENTED,
DEFERRED, DEPRECATED.

### 10.1 Integration status summary (2026-10-19)

| Integration | Exists in the product | Status |
|---|---|---|
| **Google — Gmail and Google Calendar connection** | Yes (**Registries**) | **DEGRADED** — Google refused the permission refresh on 2026-09-30, and no Google sync appears in production's log on 2026-10-19. Reconnect once ([§5.6](#56-re-authorize-google), [§5.7](#57-disconnect-safely-and-when-it-is-required)). The flows have never been live-certified. |
| **Gmail — outbound email** | Yes (server, approvals, booking emails, form auto-reply) | **CONFIGURATION REQUIRED** — certification gate, and no screen to write your own email ([§6.1](#61-read-this-first--current-status)) |
| **Gmail — reply capture** | Yes (scheduler) | **AVAILABLE BUT NOT CERTIFIED** — never tested live ([§6.6](#66-procedure-c--capture-the-reply)) |
| **Google Calendar — meeting sync and booking busy times** | Yes | **AVAILABLE BUT NOT CERTIFIED** |
| **Website forms** | Yes (**Website Forms**) | **AVAILABLE BUT NOT CERTIFIED** — no production lead from a real website recorded yet (governing document C-30) |
| **Online booking** | Yes (**Calendar**) | **AVAILABLE BUT NOT CERTIFIED** — no production booking recorded yet (governing document M-05) |
| **Stripe** | Yes (**Registries**) | **CONFIGURATION REQUIRED** — `STRIPE_API_KEY` / `STRIPE_WEBHOOK_SECRET` are not set (O-02) |
| **Outbound webhooks** | Yes (**Registries** → **"Webhooks"**) | **AVAILABLE BUT NOT CERTIFIED** — admin-configured |
| **MCP server (governed AI tools)** | Yes (**MCP Console**) | **AVAILABLE BUT NOT CERTIFIED** |
| **Email notifications and invitation emails** | Yes (**Action Center**, **Team & Access**) | **CONFIGURATION REQUIRED** — `EMERGENT_EMAIL_KEY` was not set when last recorded; **Settings** → **"Notifications"** → **"Email delivery"** shows the live answer |
| **AI generation** | Yes (Client 360 **"Evidence-backed AI"**) | **CONFIGURATION REQUIRED** — `EMERGENT_LLM_KEY` is not set (O-11) |
| **Security-gate scanners** | Yes (**Operations** → **"Security gate"**) | **CONFIGURATION REQUIRED** (O-13, O-14) |
| **Scheduler — built into the CRM** | Yes | **LIVE** since 2026-10-18; Verified (live, 2026-10-19) from the boot log ([§11](#11-scheduler--automations)) |
| **Scheduler — GitHub Actions workflow** | Yes | **LIVE**, optional second driver; its calls answered `200` on 2026-10-19 |
| **"Continue with Google" sign-in** | Button present | UNVERIFIED — OWNER/ENGINEERING INPUT REQUIRED. Do not use ([§3.1](#31-supported-sign-in-methods)). |
| **Recovery intake** (call logs, web enquiries, external CRM events) | Server API only, no screen | **AVAILABLE BUT NOT CERTIFIED** — for engineering integrations |
| **n8n, Slack, ClickUp** | No working CRM integration. Catalogue entries may appear in **Registries** as contracts only. | **NOT IMPLEMENTED** (O-08, O-09) |
| **SMS, Calling / telephony** | Placeholder modules only | **NOT IMPLEMENTED** (O-06) |

The **Jev QC gate** (an n8n workflow) is an engineering quality gate that AI agents use before
claiming work is complete. It is **not** a CRM feature, and it never touches CRM data.

### 10.2 Google — Gmail and Google Calendar

- **Purpose:** matched email and meetings on Client 360; busy times for online booking; reply
  capture; sending approved email.
- **Connect / verify / disconnect / troubleshoot:** [Chapter 5](#5-google--gmail-setup).
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

### 10.3 Stripe

- **Purpose:** read customers, invoices and subscriptions and match them to contacts. Stripe
  **"Billing & subscriptions"** items appear on Client 360 → **Activity**.
- **Status:** CONFIGURATION REQUIRED. **"Connect"** on the Stripe row currently answers
  **"Stripe is not configured (STRIPE_API_KEY)."**
- **Required owner action** (governing document O-02):
  1. Decide whether Stripe is in scope.
  2. If it is, create a **test-mode** restricted key, and a webhook endpoint at
     `https://clientverse-crm-production-production.up.railway.app/api/integrations/stripe/webhook`.
  3. Have `STRIPE_API_KEY` and `STRIPE_WEBHOOK_SECRET` set in Railway.
- **Connect:** **Registries** → Stripe → **"Connect"**. It uses the Railway key. The screen has no
  field for a per-organization key.
- **Verify:** the row shows **"Connected"** and the Stripe account. **"Sync"** shows
  **"Synced Stripe: N record(s) matched"**.
- **Disconnect:** **"Disconnect"** → **"Disconnected Stripe"**. Records already synced stay.
- **Limitations:** read-only, apart from payment intents on invoices (server only). No charges or
  refunds from the screens. The webhook refuses every event until its secret is set. That is
  correct, fail-closed behaviour.

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

### 10.5 MCP server (governed AI tools)

- **Purpose:** lets approved AI tools read CRM data (Level 1), and propose reversible writes that
  need human approval (Level 2). Level 3 and above are refused.
- **Controls:**
  - **"Kill switch"** (admin) turns every tool off at once
  - **"Undo"** (admin, with a reason, within the undo window)
  - all activity is in **Automation & Audit**
- **Secret names:** none for the built-in tools. External tools must pass the security gate, whose
  scanners are not configured.

### 10.6 Email notifications and AI

- **Email notifications** — alert emails, the daily digest, **invitation emails** and booking
  alerts to your own team — need `EMERGENT_EMAIL_KEY` (and optionally `EMAIL_FROM_NAME`). Until
  then, **Action Center** shows **"Email delivery is not configured."**, invitations are shared by
  link ([§8.2](#82-invite-a-user)), and in-app alerts still work. This is **not** Gmail: these
  emails come from a separate delivery service. Emails to *clients* (booking emails, auto-replies,
  approved messages) go through Gmail only ([§6](#6-email-production-verification)).
- **AI generation** needs `EMERGENT_LLM_KEY`. Until then, **"Generate with evidence"** fails.

---

## 11. Scheduler / Automations

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

### 11.3 Configuration (names only)

| Where | Name | Holds |
|---|---|---|
| Railway → service → **Variables** | `IN_PROCESS_SCHEDULER` | Leave unset. `0` turns the built-in scheduler **off** — an engineering decision |
| Same | `IN_PROCESS_SCHEDULER_JOBS` | Leave unset. Engineering can limit the built-in scheduler to listed jobs |
| Same | `WEBHOOK_CRON_SECRET` | The shared secret for calls from outside (the workflow, or an engineer running a job by hand) |
| GitHub → repository **Settings** → **Secrets and variables** → **Actions** | `CLIENTVERSE_PRODUCTION_URL` | The production address in [§2.1](#21-addresses) — workflow only |
| Same | `WEBHOOK_CRON_SECRET` | **The same value** as the Railway variable — workflow only |

### 11.4 Verify that automation is healthy

**A. Production (owner, signed in as admin in the same browser)**

1. Open https://clientverse-crm-production-production.up.railway.app/api/cron/health. It covers
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

### 11.5 What the results mean

| You see | Meaning | Action |
|---|---|---|
| `"scheduled_jobs_running": false` | Nothing ran any job in the last 2 hours | Check the Railway boot log for the start-up line (§11.4 B). If it is missing, or says the scheduler is disabled, escalate. |
| `"in_process"` → `"last_run_at"` older than ~10 minutes while `/api/health` is ok | Either the GitHub workflow ran every job first, or the built-in scheduler has stopped | First check `"last_authenticated_call_at"`: if it is recent, or the Railway log shows `In-process job '<job>': an external request already ran window …`, automation is healthy — nothing to do. Otherwise restart the latest SUCCESS deployment once ([§2.3](#23-if-the-site-does-not-load)); escalate if it persists. |
| `"last_failed_job"` recent | One job raised an error | Note the job and `last_failed_error`; escalate if it repeats |
| `"receiving_scheduled_traffic": false` | No outside scheduler is calling | Expected if you rely on the built-in scheduler. If GitHub shows green runs at the same time, escalate. |
| **403** on `/api/cron/health` in your browser | You are signed in as a member, not an admin | Sign in as an admin |
| GitHub **green run** | Production was called, answered `200` for every job, **and** recorded the run | None |
| GitHub **red run** | Something in the chain failed. Open the run to see which step. | See the rows below |
| **401 Unauthorized** (workflow) | The shared secret is missing or different at one end (GitHub vs Railway). Production records the refusal. | Make both `WEBHOOK_CRON_SECRET` values identical ([§11.8](#118-rotate-or-fix-the-scheduler-secret)) |
| *"Scheduler not configured"* — *Missing repository secret(s)* | A GitHub secret is not set | Add it (§11.3), or disable the workflow if you rely on the built-in scheduler |
| *"No request reached production"* | None of the calls returned 200 | Read the **HTTP** column of the run summary: `000` = production unreachable (check `/api/health` and Railway, [§2.3](#23-if-the-site-does-not-load)); `401` = secret mismatch ([§11.8](#118-rotate-or-fix-the-scheduler-secret)); `404` = wrong `CLIENTVERSE_PRODUCTION_URL` |
| *"Run not recorded"* / *"Ledger unreadable"* | Calls were accepted, but the ledger check failed | Escalate |
| Every workflow job fails in 2–4 seconds with no log | A GitHub account-level Actions problem (billing, spending limit, Actions disabled) — as from 2026-09-27 22:35 until 2026-09-30 | Owner: GitHub → **Settings** → **Billing and plans**; repository **Settings** → **Actions** → **General**. The built-in scheduler keeps running meanwhile. |
| Workflow runs stop appearing at all | GitHub disables scheduled workflows after 60 days without repository activity | **Actions** → **Scheduled jobs** → GitHub's enable button — or leave it off |

**Stopping the workflow.** If you decide to rely on the built-in scheduler alone, disable the
workflow in GitHub (**Actions** → **Scheduled jobs** → its menu → disable). Do not just delete its
secrets: without them every run fails by design.

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

### 11.7 Run the jobs by hand

You rarely need to: the built-in scheduler runs every job within its window. To run one now:

- **From the screens:** **"Run SLA check"** (commitment risk, [§7.9](#79-work-inside-a-workspace-commitments-tasks-deliverables-requests-approvals)),
  **"Sync"** on an integration (§5.5), **"Run recovery detection"** and **"Compose strategies"**
  (Operations, admin), **"Send digest"** (Action Center, admin), **"Refresh"** on next best actions.
- **From GitHub** (while the workflow is configured): **Actions** → **Scheduled jobs** →
  **"Run workflow"** (on `main`). Leave **jobs** empty to run all fourteen, or enter a
  comma-separated list, for example `inbound-email,reconcile-unknown`.

This is safe: every job is idempotent.

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

## 12. Troubleshooting Matrix

| Problem | Likely cause | Exact owner action | Escalate when |
|---|---|---|---|
| **Cannot log in** (any reason) | Wrong password, lockout, wrong address, stale session, site down | 1. Check `/api/health` (§2.3). 2. Check the email is exactly right (owner: the `ADMIN_EMAIL` value). 3. See the rows below. | After §9.1–§9.8 fail, or the site is down |
| **Wrong password** — "Invalid email or password" | Typo, Caps Lock, or the password changed | Owner: copy it from Railway `ADMIN_PASSWORD` or your password manager. Member: an admin resets it (§8.8). Stop after 3 tries. (§9.1) | Never needed |
| **Forgot password** | — | Owner: change `ADMIN_PASSWORD` in Railway (§9.2). Member: **"Reset password"** (§8.8). | No admin can sign in |
| **Account locked** — the right password is still refused | 5 failures → 15-minute lock | Wait 15 minutes, then try **once** (§9.3). A member: an admin's reset clears it. | The owner needs access sooner |
| **"Choose your own password"** appears after sign-in | You signed in with a temporary password | Type it again under **"Temporary password"**, choose your own, **"Save my password"** (§8.8) | It reappears after saving |
| **"Your password was changed. Please sign in again."** | Your password was changed elsewhere, or reset by an admin | Sign in with the new password (§9.4) | You did not change it and no admin reset it — treat as a security problem (§13.6) |
| **Google sign-in fails** ("Continue with Google") | Unsupported third-party sign-in | Use email + password (§3.1, §9.6) | Someone ended up in a stray organization |
| **Google connection fails** — "Google authorization failed" | Consent cancelled or refused, redirect URI mismatch, not a test user | Full reset (§5.7), then connect within 10 minutes and tick every box (§5.5) | It fails twice after a full reset |
| **Google reconnect loop** — stuck "Connecting…" or back to "Error" | Abandoned consent; secret or redirect mismatch | Disconnect **both** rows, remove app access in the Google account, connect again (§5.7, §5.9) | `token_exchange_failed` or `redirect_uri_mismatch` persists |
| **Google token refresh 400** — "Needs auth", `token_refresh_failed:400` | Permission revoked or expired; consent screen in Testing (7-day expiry); client secret rotated | **"Re-authorize"** (§5.6) | It recurs within a week (Testing mode), or the reconnect itself ends in "Error" / `token_exchange_failed` (secret or redirect mismatch) |
| **Integration says disconnected** — "Not connected" | Never connected, or someone disconnected it | Admin → **"Connect"** (§5.5). Check **Automation & Audit** for `integration.disconnected` to see who. | Connect fails |
| **Gmail send refused as "read-only"** | The connection does not record `gmail.send`: unticked at Google, or made before 2026-10-19 | Full reset and tick **send** on consent (§5.7, §5.8) | It still says read-only after that |
| **Gmail send fails** — message "Blocked" | Not connected, no consent, certification gate | Read the reason on the message. Fix the connection (§5.6). Certification needs engineering (§6.1). | The reason mentions certification, consent or a provider |
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
| **Portal link lost or leaked** | It is shown only once; there is no revoke button | Create a new link and share it privately | A leaked link must be revoked |

---

## 13. Security and Owner Safety

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

### 13.2 Where secrets may and may not go

| Allowed | Never |
|---|---|
| Railway → service → **Variables** (the approved store for production secrets) | GitHub issues, pull requests, comments, wikis. **This repository is public: anything posted there is public.** |
| GitHub → **Settings** → **Secrets and variables** → **Actions** (scheduler secrets only) | Any committed file — **never commit a `.env` file** (they are git-ignored for this reason) |
| Your password manager | Chat, email, Slack, ClickUp, tickets, screenshots |
| Google Cloud Console (its own client secret) | This manual, or any document |

**If a secret was ever exposed** — pasted, screenshotted, emailed or committed — treat it as
compromised and **rotate it** (§13.4), even if you deleted the message.

### 13.3 Which settings are safe to change

| Safe for the owner | Needs engineering review first |
|---|---|
| **In the CRM:** notification preferences, team invites, roles, disable/enable, password resets, your own password (not the owner's — §3.3), business name, Google connect/re-authorize/disconnect, webhook endpoints you own | **Railway:** any variable other than `ADMIN_PASSWORD` and `WEBHOOK_CRON_SECRET` — including `IN_PROCESS_SCHEDULER` |
| **Railway:** `ADMIN_PASSWORD` (§9.2); `WEBHOOK_CRON_SECRET` together with GitHub (§11.8); **Restart** of the latest SUCCESS deployment | **Railway:** Rollback / Redeploy of an older commit; switching to the custom domain (set `PUBLIC_BACKEND_URL` and `GOOGLE_REDIRECT_URI` first) |
| **GitHub:** Actions secrets; enabling or disabling the workflow; manual runs | **Never:** `ADMIN_EMAIL`, `MONGO_URL`, `DB_NAME`, `INTEGRATION_ENC_KEY` (changing it makes every stored integration permission unreadable), `JWT_SECRET` (changing it signs everyone out), `APP_ENV`, `SEED_DEMO_DATA` (must stay false) |
| **Google Cloud:** consent-screen test users | **Google Cloud:** redirect URIs, client secret rotation (Railway must be updated at the same moment) |
| **DNS:** the records Railway shows for the custom domain (O-12) | **MongoDB Atlas:** network access, users, backups |

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

### 13.6 Report a problem safely

- **Operational problems:** follow [Chapter 15](#15-support--escalation). Use the status issue, or
  your private engineering channel.
- **Security problems** (a leaked secret, suspicious access): do **not** open a public issue.
  - Use GitHub's **private vulnerability reporting** for this repository (see `SECURITY.md`), or
    contact engineering privately.
  - Rotate the affected secret immediately.

### 13.7 Screenshots — what is safe

| Safe to send | Redact first | Never send |
|---|---|---|
| Error messages, page headings, status labels, the Registries rows, GitHub run summaries, Railway deployment lists and log lines | Client names, email addresses and phone numbers (when sharing outside the company); the connected Google address if the mailbox is personal; **access codes in addresses** — any `?token=` part, and the code after `/portal/` or `/booking/manage/` | Railway **Variables** with values visible; the webhook **"Verify"** dialog; the **"Invitation ready"** dialog; the **"Temporary password ready"** dialog; browser developer tools showing cookies, headers or storage; Google Cloud credential pages |

---

## 14. Production Verification Checklist

Mark each item **PASS**, **FAIL**, **BLOCKED** or **NOT TESTED**. Definitions are in
[§6.2](#62-result-definitions). Write the date, and attach evidence for every PASS.

The *Known on 2026-10-19* column is what the engineering review could observe without opening the
website. The owner's result is the authority. Use a **test member** for the password checks, never
the owner account.

| # | Check | How | Expected | Known on 2026-10-19 | Result |
|---|---|---|---|---|---|
| 1 | Production URL loads | Open the production URL | Sign-in page, **"Sign in to ClientVerse"** | Deployment SUCCESS; health 200 in the Railway log | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 2 | Service healthy | `/api/health` | `status ok`, `database up`, `git_sha` = Railway commit | Health 200 at boot (01:16 UTC) | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 3 | Login works | §3.2 | **Command Center** | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 4 | Logout works | Sign-out icon, then open `/dashboard` | Returns to the sign-in page | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 5 | Admin role verified | Settings → **"Profile"** → **"Access level"**; **"Team & Access"** visible | **"Workspace admin"** | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 6 | Member role verified | Invite a test member (§8.2); they create their account from the link in a private window | **"Team member"**; no **"Team & Access"**; the Registries rows show **"Admin manages"** | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 7 | Password reset and change work | Reset the test member's password (§8.8); they sign in with it, see **"Choose your own password"**, save; later **"Change password"** (§3.9) | Temporary password opens only that screen; **"Password changed"** | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 8 | Core CRM records load | Leads, Tasks, Contacts, Companies, Pipeline, Calendar, Client 360 | Lists or honest empty states; no "…unavailable" | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 9 | Create record works | Create company `ZZ Test Co` and contact `ZZ Test Person` | **"Company created"**, **"Contact created"**; both appear after a reload | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 10 | Edit record works | Open `ZZ Test Person` → **"Edit"** → add a phone → **"Save changes"**; move a test deal **Lead → Qualified**; reload | **"Contact saved"**, **"Moved to Qualified"**; both persist after the reload | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 11 | Archive / restore | **"Archive contact"** on `ZZ Test Person`; **"Show archived"**; **"Restore"** | **"Contact archived"**, **"Contact restored"** | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 12 | Google connected | Registries → Gmail | **"Connected"**, no red line, connected on or after 2026-10-19 | No Google sync in the 2026-10-19 log; reconnect needed (§1.4) | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 13 | gmail.send verified | §5.8 checks 1–3 | Google lists send permission; Email not listed as unauthorised | Blocked by 12 and by certification | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 14 | Outbound email works | §6.4 | **"Sent"**; in Gmail Sent; received | BLOCKED (§6.1) | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 15 | Duplicate-send protection | §6.5 | Refused; one copy only | BLOCKED (§6.1) | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 16 | Inbound reply works | §6.6 | Inbound **"Received"** on the same thread | BLOCKED (§6.1) | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 17 | Automation healthy | §11.4 A | `scheduled_jobs_running: true`; recent `in_process.last_run_at`, or a recent `last_authenticated_call_at` when the workflow runs too | Boot log shows the built-in scheduler; workflow calls answered 200 | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 18 | Railway deployment healthy | Railway → Deployments | Newest **SUCCESS**, no crash loop | `838f00d` SUCCESS 01:16 UTC | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 19 | Integrations show correct status | Settings → **"Integrations"** vs Registries | Same statuses in both; Stripe **"Not connected"** | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 20 | No visible critical errors | Visit every active sidebar item | No **"This view needs a refresh"**, no "…unavailable" | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 21 | Clean up | Archive `ZZ Test Person` and the test deal; disable the test member. The test company has no archive button — note its name for engineering. | Recorded | — | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |

**Sign-off:** date ____________ · verified by ____________ · evidence location ____________

---

## 15. Support / Escalation

### 15.1 When to escalate

| Situation | Who |
|---|---|
| Anything this manual lets the owner fix (sign-in, member passwords, Google reconnect, invitations, scheduler secrets) | **Owner** — follow the chapter |
| Site down, deployment FAILED or CRASHED, database down, automation stopped, any repeated `500` | **Engineering — urgent** |
| Outbound email certification, company edits, deletes, export or import | **Engineering — planned** |
| Leaked secret or suspicious access | **Rotate now**, then report **privately** (§13.6) |
| Google Cloud, Stripe account, GitHub billing, DNS, MongoDB Atlas account decisions | **Owner** (engineering can advise) |

### 15.2 Evidence to collect before you escalate

- [ ] **Time** of the problem, with your timezone (for example `2026-10-19 01:16 UTC`)
- [ ] **Page or module** — the sidebar item and tab, and the address bar with every access code
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

### 15.5 Where to report

- **Status and owner actions:** the repository's status issue
  ([ebyron357/Clientverse-crm#10](https://github.com/ebyron357/Clientverse-crm/issues/10)).
  - Required format: **COMPLETED / BLOCKED / EXACT OWNER INPUT REQUIRED**.
  - It is **public**, so never include secrets or client data.
- **Security:** private vulnerability reporting (see `SECURITY.md`).
- **Day-to-day:** your engineering contact's private channel.

---

## Appendix A. Acceptance self-test

A first-time owner must be able to answer each question from this manual alone.

| Question | Answer in one line | Where |
|---|---|---|
| What URL do I open? | https://clientverse-crm-production-production.up.railway.app/login | [§1.1](#11-quick-reference-card), [§2.1](#21-addresses) |
| How do I log in? | Email + password → **"Sign in"**. Not Google. | [§3.2](#32-sign-in-with-email-and-password) |
| What account type am I using? | The **admin** account whose email is Railway `ADMIN_EMAIL`, in your organization (first named "ClientVerse HQ") | [§3.3](#33-which-account-the-owner-uses) |
| What do I see after login? | Command Center — four figures, next actions, next best actions, client health | [§4.2](#42-what-you-see-after-sign-in-command-center) |
| Where are Settings? | Sidebar → Platform → **"Settings"** | [§1.3](#13-find-settings-and-integrations) |
| Where are Integrations? | Sidebar → Platform → **"Registries"** → **"Integrations"** tab (or Settings → **"View integrations"**) | [§5.3](#53-where-the-google-controls-are) |
| How do I connect Google? | Registries → Gmail → **"Connect"** → consent (tick all) → **"Google connected"** | [§5.5](#55-connect-google-first-time) |
| How do I reconnect Google? | **"Re-authorize"** on "Needs auth"; otherwise disconnect **both** rows, then Connect. Reconnect once since 2026-10-19. | [§5.6](#56-re-authorize-google), [§5.7](#57-disconnect-safely-and-when-it-is-required) |
| How do I verify gmail.send? | Google Account → third-party connections shows send permission; the connection records `gmail.send`; Operations → Recovery strategies does not list Email | [§5.8](#58-verify-that-gmailsend-was-actually-granted) |
| How do I send a real email? | Engineer-assisted test today (no compose screen), or approve a booking email / form auto-reply — after reconnecting and certification | [§6.1](#61-read-this-first--current-status), [§6.4](#64-procedure-a--send-one-real-outbound-email), [App. C](#appendix-c-engineer-assisted-email-verification) |
| How do I verify the reply came back? | Operations → Conversations → the same thread shows inbound **"Received"** within ~35 minutes | [§6.6](#66-procedure-c--capture-the-reply) |
| How do I manage users? | Team & Access → **"Invite"**, role menu, **"⋯"** → **"Reset password"** / **"Disable access"** | [§8](#8-users-roles-and-administration) |
| How do I recover access? | Owner: change `ADMIN_PASSWORD` in Railway; members: an admin resets it; locked: wait 15 minutes | [§9](#9-account-recovery) |
| How do I know scheduled automations are healthy? | `/api/cron/health` shows `scheduled_jobs_running: true` and a recent `in_process.last_run_at` — or, when the GitHub workflow runs too, a recent `last_authenticated_call_at` | [§11.4](#114-verify-that-automation-is-healthy) |
| What does 401 mean? | Not signed in, or the session expired (workflow: secret mismatch) | [§12](#12-troubleshooting-matrix), [§11.5](#115-what-the-results-mean) |
| What does 500 mean? | A server error — retry once, then escalate with evidence | [§12](#12-troubleshooting-matrix) |
| What do I do when Railway is down? | Check `/api/health` and Railway Deployments; restart the last SUCCESS once; escalate | [§2.3](#23-if-the-site-does-not-load) |
| What evidence do I collect before escalation? | Time, page, action, exact error, screenshot, account, browser, repeatability, health results, deployment | [§15.2](#152-evidence-to-collect-before-you-escalate) |

---

## Appendix B. System state on 2026-10-19

| Fact | Evidence |
|---|---|
| Production serves `main@838f00d` (PR #42) | Railway deployment `e7790295-5af4-4977-8d58-ff600b1a2633`, redeployed 2026-10-19 01:47 UTC to apply the custom-domain variables. The first deployment of this commit, `406f320e-…` (SUCCESS 01:16 UTC), is REMOVED. |
| Service boots with the Gmail adapter and the built-in scheduler | Deploy log: `Registered outbound channel provider: gmail` → `In-process scheduler started for 13 job(s): commitment-risk, work-queue, recovery-runner, booking-reminders, integration-sync, next-best-actions, inbound-email, reconcile-unknown, daily-digest, second-chance, detect-recovery, recovery-strategies, approval-expiry` → `Application startup complete` → `GET /api/health 200` |
| The GitHub workflow also reaches production | Railway logs of `d4d2e07f` and `406f320e`: `200 OK` for all fourteen workflow paths and `GET /api/cron/runs`, 00:19–01:17 UTC |
| No Google connection is being synced | No Google API request in the `d4d2e07f` log through 01:09 UTC, although `integration-sync` ran; that job syncs only active or degraded connections (`run_integration_sync_sweep` in `backend/server.py`). Last known: the refresh refused on 2026-09-30. |
| A connection records the scopes Google granted | Code since PR #42: `google_callback` in `backend/server.py` stores `creds["scopes"]`; `backend/gmail_provider.py` refuses to send without `gmail.send` |
| The custom domain is live | Railway domain status for `crm.clientverse.io`: verified, certificate valid, CNAME propagated. Railway variables `FRONTEND_URL` and `GOOGLE_REDIRECT_URI` point to it; `CORS_ORIGINS` lists it and the Railway address. Railway's HTTP log shows pages served on `crm.clientverse.io` from 01:36 UTC, and Google returning to its callback at 01:42 UTC. |
| Outbound email is held by a certification gate | Code: `backend/recovery_strategy.py` (`authorized_channels`, `CONFIGURED_INTEGRATION_STATUSES`); the Gmail catalogue record is seeded `REQUIRES_CONFIGURATION` in `backend/server.py`, and nothing updates it |
| No screen writes an email to a contact or records consent | Code: `frontend/src/pages/Operations.jsx` calls only conversation handoff and close. The only screen-released emails are booking emails (`frontend/src/pages/Calendar.jsx`) and an approved auto-reply (`frontend/src/pages/WebsiteForms.jsx`). |
| Invitations are emailed only when email delivery is configured | Code: `_email_invitation` in `backend/server.py`; `email_configured()` reads `EMERGENT_EMAIL_KEY` |
| Last full live production smoke | 2026-09-01 on `ca30587` (`docs/evidence/production-smoke-20260901.json`). No live smoke since. |
| Email notifications and AI not configured (as recorded) | `EMERGENT_EMAIL_KEY` and `EMERGENT_LLM_KEY` absent from the Railway variable list recorded on 2026-09-21 ([OWNER_HANDOFF.md](OWNER_HANDOFF.md) §3); not re-read since |
| History — 2026-09-30 | The workflow first reached production (runs #3551–#3555, after #3544–#3550 failed on a `401` secret mismatch); Google's token endpoint refused the stored grant at 16:08 UTC (`400`) |

---

## Appendix C. Engineer-assisted email verification

**For an engineer working with the owner.** Every value in angle brackets is a placeholder.
Never paste a real token into a ticket or log.

**Step 0 — prerequisites the engineer confirms:**

1. The Gmail connection is **"Connected"**, made on or after 2026-10-19, and records `gmail.send`
   (§5.6–§5.8).
2. The organization's Gmail catalogue record (`integrations` collection, `name: "Gmail"`, the
   owner organization) is in a certified state — one of `CONNECTED`, `ACTIVE`, `CERTIFIED`,
   `ENABLED`, `AVAILABLE` (`backend/recovery_strategy.py`).
   - There is no API for this. It is a **deliberate certification decision the owner approves**.
     Record it in the governing document before changing the record.
3. `GET /api/recovery-strategies/channel-authority` shows `email.authorized: true`.

**Secret handling in this procedure.** Run it in `bash`. The password is typed at a hidden
prompt, never on a command line. The session token is held only in the shell, and is passed to
`curl` through a configuration on a file descriptor, so it does not appear in process arguments,
shell history or output. Nothing below prints the password or the token.

```bash
BASE=https://clientverse-crm-production-production.up.railway.app

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

Record the results against [§14](#14-production-verification-checklist) rows 13–16, and in the
governing document (M-01), with the ids — never the token.

---

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

Railway variable presence was last read by name on 2026-09-21 ([OWNER_HANDOFF.md](OWNER_HANDOFF.md)
§3). The scheduler rows are updated from the 2026-10-19 boot log and Railway request log.

---

## Appendix E. Related documents

**Governing and engineering documents.** These are kept for developers; this manual does not
replace them.

- [Canonical governing document](CLIENTVERSE_CRM_CANONICAL_GOVERNING_DOCUMENT.md) — scope,
  capability status, owner-action register (O-01…O-16)
- [Project Completion Standard](PROJECT_COMPLETION_STANDARD.md) — the closeout baseline this manual
  serves
- [Railway runbook](RAILWAY_RUNBOOK.md) and [Production configuration](PRODUCTION.md) — deployment
  and scheduler mechanics
- [Website forms guide](WEBSITE_FORMS.md) and [Booking guide](BOOKING.md) — engineering detail for
  §7.6 and §7.7
- [Owner handoff (2026-09-21, engineering record)](OWNER_HANDOFF.md) and
  [Activation report](ACTIVATION_REPORT.md) — history and evidence
- [Google provider certification](GOOGLE_PROVIDER_CERTIFICATION.md),
  [Stripe provider certification](STRIPE_PROVIDER_CERTIFICATION.md)
- [Security policy](../SECURITY.md), [README](../README.md)

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

## Appendix F. Document control

| Version | Date | Change |
|---|---|---|
| 1.2 | 2026-10-19 | `crm.clientverse.io` is live: addresses (§2.1–2.2, §3.2), Google addresses (§10.2), Appendices B and D. Review fixes ([ebyron357/Clientverse-crm#43](https://github.com/ebyron357/Clientverse-crm/pull/43)): signing everyone out when the owner password may be known (§9.2, §13.4); scheduler health when the GitHub workflow runs first (§11.4, §11.5, checklist row 17, Appendix A); access codes in `/portal/` and `/booking/manage/` addresses (§13.7, §15.2). |
| 1.1 | 2026-10-19 | Refreshed for `main@838f00d` (PRs #35–#42). Scheduler: built into the CRM (13 jobs), with the GitHub workflow as an optional second driver; health is read from `scheduled_jobs_running` and `in_process`. Sign-in: the redesigned page, password change in Settings, admin reset of a temporary password, invitation sign-up and invitation emails. Screens: collapsible sidebar groups, breadcrumbs, theme button, side panels; new Leads, Tasks, Website Forms and Calendar sections; contacts and deals can now be edited and archived; deals move by drag or **"⋯"** → **"Move to stage"**. Email: booking emails and form auto-replies are the screen-released emails; a connection records the scopes Google granted (PR #42), so reconnect once; a refused lookup never counts as "not sent". Custom domain `crm.clientverse.io` recorded as added but not live. Verified against the code and Railway deployment records and logs of 2026-10-19. |
| 1.0 | 2026-09-30 | First complete owner/admin manual ([ebyron357/Clientverse-crm#33](https://github.com/ebyron357/Clientverse-crm/issues/33)). Verified against `main@8f23f63` code, Railway deployment records and logs, and GitHub Actions run records of 2026-09-30. |

**Keeping it true**

- Update this manual **in the same change** as any code change that alters a screen label, a
  route, a sign-in rule, a Google scope, a scheduler job or an owner procedure.
- When a production fact changes (for example certification granted, or the Google permission
  restored), update [Appendix B](#appendix-b-system-state-on-2026-10-19) and the governing
  document together.
- Never add a secret value. Names only.
