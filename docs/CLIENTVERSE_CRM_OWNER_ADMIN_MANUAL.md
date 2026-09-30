# ClientVerse CRM — Owner/Admin Manual

| | |
|---|---|
| **Document** | ClientVerse CRM Owner/Admin Manual |
| **Version** | 1.0 |
| **Date** | 2026-09-30 |
| **Repository** | `ebyron357/Clientverse-crm` |
| **Branch documented** | `main` — written against `main@8f23f63`, whose application code is identical to `c9f5a6e` (every later commit changed documentation only) |
| **Production environment** | Railway project `welcoming-vibrancy` → environment `production` → service `clientverse-crm-production` |
| **Production URL** | https://clientverse-crm-production-production.up.railway.app |
| **Sign-in page** | https://clientverse-crm-production-production.up.railway.app/login |
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
- **Bold text in quotes** — for example **"Sign in to ClientVerse"** — is a label exactly as it
  appears on screen, so you can find it.
- **Warning:** marks something that can lock you out, lose data or expose a secret.
- **Check:** tells you how to know a step worked.
- Every fact carries its evidence:
  - **Verified (code)** — read from the application code that production runs.
  - **Verified (live, 2026-09-30)** — observed in production on 2026-09-30 through Railway's
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
- [B. System state on 2026-09-30](#appendix-b-system-state-on-2026-09-30)
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
| Automation runs | https://github.com/ebyron357/Clientverse-crm/actions/workflows/scheduled-jobs.yml |
| Sign-in method | Email address + password. **Not** "Continue with Google" ([§3.1](#31-supported-sign-in-methods)) |
| Your account | The address in the Railway variable `ADMIN_EMAIL`, with the password in the Railway variable `ADMIN_PASSWORD` ([§3.3](#33-which-account-the-owner-uses)) |

### 1.2 Sign in

1. Open **https://clientverse-crm-production-production.up.railway.app/login** in a current
   Chrome, Edge, Firefox or Safari.
2. Under **"Welcome back"**, type your owner email in **"Work email"** and your password in
   **"Password"**.
3. Click **"Sign in to ClientVerse"**.
4. **Check:** the page changes to **Command Center**, with the large heading **"Good to see you"**.
   At the bottom of the left sidebar you see your name and **"Workspace admin"**.

**Warning:** Do not click **"Continue with Google"** or **"Create one"** on the sign-in page. Both
can create a *separate, empty* organization that is not your CRM ([§3.1](#31-supported-sign-in-methods)).

### 1.3 Find Settings and Integrations

- **Settings:** left sidebar → group **Platform** → **"Settings"**.
- **Integrations** (Google, Stripe): left sidebar → **Platform** → **"Registries"**. The
  **"Integrations"** tab opens first. You can also go through **Settings** → the
  **"Connected providers"** card → **"View integrations"**.

### 1.4 First things to verify

Do these five checks after every first sign-in, and whenever something seems wrong.

| # | Check | Where | Healthy answer |
|---|---|---|---|
| 1 | You are an admin | **Settings** → **"Profile & account"** → **"Access level"** | **"Workspace admin"** |
| 2 | The service and database are up | Open `/api/health` (link in [§1.1](#11-quick-reference-card)) | `"status":"ok"` and `"database":"up"` |
| 3 | Google is connected | **Registries** → **Integrations** → **Gmail** card | **"Connected"**, no red error line. If it says **"Needs auth"**, follow [§5.6](#56-re-authorize-google) |
| 4 | Automation is running | GitHub → Actions → **Scheduled jobs** | The newest runs have green ticks ([§11.4](#114-verify-that-automation-is-healthy)) |
| 5 | No critical alerts | **Action Center** (sidebar → **Command**) | Nothing unexpected under **"Priority work queue"** |

**As of 2026-09-30, check 3 is expected to fail.** Google refused to refresh the saved Google
permission during the 16:08 UTC sync (Railway log: `POST https://oauth2.googleapis.com/token`
→ `400 Bad Request`), so the Gmail and Google Calendar cards should read **"Needs auth"**.
Re-authorize Google ([§5.6](#56-re-authorize-google)).

### 1.5 If something is broken

- Look up the symptom in the [Troubleshooting Matrix](#12-troubleshooting-matrix).
- If the matrix says to escalate, collect the evidence in [§15.2](#152-evidence-to-collect-before-you-escalate).
  Never include a password or secret.

---

## 2. System Access

### 2.1 Addresses

| Environment | Address | Use it? |
|---|---|---|
| **Production** | https://clientverse-crm-production-production.up.railway.app | **Yes — this is the only live CRM.** Verified (live, 2026-09-30): Railway reports this as the service's only domain. |
| Staging | None. No staging environment is configured or documented. The only deployment path is Railway `production`. | — |
| Custom domain (for example `crm.<yourcompany>`) | None yet. Choosing one is an open owner decision (governing document O-12). | — |
| Old preview and hosting addresses (Render, Manus, OpenHands, Emergent previews) | Historical only. | **No.** They are not production. Never run a second copy against the production database. |

### 2.2 Confirm you are on the correct deployment

1. The address bar shows exactly `clientverse-crm-production-production.up.railway.app`, with a
   padlock (HTTPS).
2. The browser tab reads **"ClientVerse — Client Operations Platform"**. The sign-in page shows the
   ClientVerse logo and **"Welcome back"**.
3. Open https://clientverse-crm-production-production.up.railway.app/api/health. A healthy answer
   looks like this:

   ```json
   {"service":"ClientVerse","version":"v1","status":"ok","database":"up","git_sha":"<40-character commit id>"}
   ```

4. Compare `git_sha` with the commit shown on Railway's active deployment: Railway → service
   `clientverse-crm-production` → **Deployments** → the top **ACTIVE / SUCCESS** entry. They should
   match. Every change merged to `main` redeploys automatically, so the deployment id changes with
   each merge. Always read it from Railway, not from a document.
   - Verified (live, 2026-09-30): the active deployment built commit `8f23f63…`, reached SUCCESS at
     15:52 UTC, and logged `Registered outbound channel provider: gmail` →
     `Application startup complete` → `GET /api/health 200`.

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
     (2026-09-30: 15:50:05 → 15:52:25 UTC). Wait 5 minutes and retry.
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

- Use a current desktop Chrome, Edge, Firefox or Safari. On a phone the sidebar is behind the
  menu button at the top left.
- The site must be allowed to store cookies and site data. The session is kept in an
  `access_token` cookie and in browser storage. Private or incognito windows work, but sign you out
  when closed.
- **Ctrl+K** (Windows) or **⌘K** (Mac) opens search. On a Mac, avoid **⌘Q**: the app binds it to
  "Quick create", but the browser usually quits first.
- In the browser developer console, one `401` from `/api/auth/me` on the sign-in page is normal.
  That is the app checking whether you are already signed in.

---

## 3. Login and Access

### 3.1 Supported sign-in methods

| Method | Status | Should the owner use it? |
|---|---|---|
| **Email + password** | Verified (code). Last proven live in production on 2026-09-01 (`scripts/proof_of_life.mjs` against `ca30587`). | **Yes — this is the owner's method.** |
| **"Continue with Google"** button | Sends you to a third-party sign-in service (`auth.emergentagent.com`) left over from the platform the CRM was prototyped on. It is **not** the owner's Google Cloud app and **not** the Gmail connection. Whether it works in production is UNVERIFIED — OWNER/ENGINEERING INPUT REQUIRED. | **No.** If the Google address has no ClientVerse account, it silently creates a new, empty organization in which that person is admin. It also ignores invitation links. |
| **"Create one"** (self-registration) | Verified (code). It works, but always creates a **new, separate organization** with the new person as its admin. It gives no access to your data. | **No** for the owner. Team members join through invitations ([§8.2](#82-invite-a-user)). |

### 3.2 Sign in with email and password

1. Go to https://clientverse-crm-production-production.up.railway.app/login.
2. The page heading reads **"Welcome back"**. If it reads **"Create your workspace"**, click
   **"Sign in"** at the bottom to switch back.
3. **"Work email"** — your owner email. **"Password"** — your password.
4. Click **"Sign in to ClientVerse"**. The button shows **"Please wait…"** while it works.
5. **Check:** you arrive on **Command Center** (`/dashboard`) with the heading **"Good to see you"**.
6. If a red box shows **"Invalid email or password"**, see [§9.1](#91-wrong-password) and
   [§9.3](#93-account-locked-out). The CRM gives the **same message** for a wrong password, an
   unknown address and a locked account, on purpose.

### 3.3 Which account the owner uses

- The owner account is created automatically the first time the server starts, from two Railway
  variables:
  - **email** = the value of `ADMIN_EMAIL`
  - **password** = the value of `ADMIN_PASSWORD`

  It is an **admin** of the organization named **"ClientVerse HQ"**. Verified (code).
- The owner already knows this address. It is deliberately not written here. To look it up, open
  Railway → service → **Variables**. Only the Railway dashboard is an approved place to read it.
- **Your password is re-applied at every restart and every deploy.** The server resets the owner
  account's password to whatever `ADMIN_PASSWORD` holds. That variable is therefore the *only*
  way to set or change the owner password ([§9.2](#92-forgotten-password)).
- **Warning: never change `ADMIN_EMAIL`.** At the next start the server would create a brand-new,
  empty **"ClientVerse HQ"** organization for the new address. Your existing data would stay with
  the old account. If the owner login address must change, escalate to engineering.

### 3.4 Verify the sign-in and your role

- **Sidebar footer** (bottom left) shows your name and either **"Workspace admin"** or
  **"Team member"**.
- **Settings** → **"Profile & account"** shows **"Name"**, **"Email"** and **"Access level"**.
- Admins see **"Team & Access"** in the sidebar under **Platform**. Members do not.

### 3.5 Sign out

1. Click **"Sign out"** at the bottom of the left sidebar. Alternatively: **Settings** →
   **"Profile & account"** → **"Session security"** → **"Sign out"**.
2. **Check:** you return to the sign-in page.
3. Signing out cancels that session on the server immediately. Closing the tab does **not** sign
   you out — a session otherwise lasts **7 days**. Always sign out on a shared computer.

### 3.6 Password requirements

- The application enforces **no** minimum length or complexity (Verified (code)).
- **Owner policy — follow it anyway:** at least 16 characters, unique to ClientVerse, and generated
  and stored by a password manager.
- The owner's password lives only in the Railway variable `ADMIN_PASSWORD`. Team members set their
  own when they create an account from an invitation. Ask them to follow the same policy.

### 3.7 Lockout behaviour

Verified (code); defaults, which the recorded production variable list does not override.

- After **5 failed sign-ins in a row** for the same email address, that address is locked for
  **15 minutes**.
- While it is locked, even the **correct** password shows **"Invalid email or password"**.
- The failure count resets **only on a successful sign-in**. So after a lockout ends, **one more
  wrong password locks it again** for another 15 minutes. Make your next attempt count.
- The lock follows the email address, on every device and browser. No screen can unlock it early.
  See [§9.3](#93-account-locked-out).

### 3.8 What must never appear in a document, issue or message

The value of `ADMIN_PASSWORD` or any password, and `JWT_SECRET`, `INTEGRATION_ENC_KEY`,
`WEBHOOK_CRON_SECRET`, `GOOGLE_CLIENT_SECRET`, `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET` or
`MONGO_URL`.

That also covers:

- session cookies and tokens (`access_token`, `cv_access_token`)
- invitation links (`/invite?token=…`)
- client-portal links (`/portal/…`)
- webhook signing secrets

See [Chapter 13](#13-security-and-owner-safety).

---

## 4. First Login Orientation

### 4.1 Screen landmarks

| Landmark | Where | What it does |
|---|---|---|
| **Sidebar** | Left edge | All modules, grouped. The **"Collapse navigation"** arrow shrinks it to icons. On a phone it opens from the menu button. |
| **Sidebar footer** | Bottom of sidebar | Your name, your role (**"Workspace admin"** / **"Team member"**) and **"Sign out"**. |
| **Page title** | Top bar, left | The module you are in and a one-line description. |
| **Search** | Top bar, centre: **"Search modules and actions…"** (Ctrl/⌘ K) | Jumps to a *module or action*. It does **not** search your records ([§7.16](#716-search)). |
| **"Create"** | Top bar, right | Quick create: company, contact, opportunity or client workspace. |
| **Bell** | Top bar, far right | Notifications, with an unread count ([§7.9](#79-action-center-and-notifications)). |
| **Amber dot** beside a sidebar item | Sidebar | The module is **not active yet** (placeholder page). |

### 4.2 What you see after sign-in: Command Center

**Command Center** (`/dashboard`) is the home page. It has the eyebrow **"Today’s client operations"**,
the heading **"Good to see you"**, and the buttons **"Refresh"** and **"Review pipeline"**. From top
to bottom:

1. **Four summary cards.** Click any card to open its list.
   - **"Open pipeline"**
   - **"Won revenue"**
   - **"Active clients"**
   - **"Delivery risk"**
2. **"Set up your client operations workspace"** — a 4-step setup checklist. Once you dismiss it
   with **X**, it cannot be brought back.
3. **"Next actions"** — up to five ranked follow-ups, each with a link.
4. **"Next best actions"** — ranked recommendations across all clients, with **"Accept"**,
   **"Done"**, **"Snooze"** and **"Not relevant"**.
5. **"Operational Alerts"** (with **"Scan now"**) and **"Connection Health"** (admins only).
6. **"Revenue movement"** — pipeline value by stage.
7. **"Outcome momentum"** — progress toward client outcome goals.
8. **"Client health portfolio"** — the health score of every client workspace.

A new, empty CRM shows friendly empty states — for example **"Your pipeline starts here"**. That
is correct, not an error.

### 4.3 Sidebar map — every item and whether it is active

| Group | Sidebar item | Opens | Status | Admin only |
|---|---|---|---|---|
| Command | **Command Center** | `/dashboard` | Active | |
| Command | **Action Center** | `/notifications` | Active | |
| CRM | **Contacts** | `/contacts` (Directory, Contacts tab) | Active | |
| CRM | **Companies** | `/companies` (Directory, Companies tab) | Active | |
| CRM | **Deals** | `/deals` (the Pipeline board) | Active | |
| CRM | **Pipelines** | `/pipeline` | Active | |
| Client Success | **Client 360** | `/workspaces` | Active | |
| Client Success | **Client Operations** | `/client-ops` | Active | |
| Communications | **Email** | `/communications/email` | **Not active** — "Configuration required" | |
| Communications | **Unified Inbox** | `/operations?tab=conversations` | Active (read, hand off and close only — [§7.10](#710-operations)) | |
| Communications | **SMS** | `/communications/sms` | **Not active** — "Configuration required" | |
| Communications | **Calling** | `/communications/calling` | **Not active** — "Backend contract pending" | |
| Scheduling | **Calendar** | `/scheduling/calendar` | **Not active** — "Backend contract pending". The Google Calendar *sync* is separate and does work ([§10](#10-integrations)). | |
| Automation | **Workflows** | `/automation/workflows` | **Not active** — "Backend contract pending" | |
| Automation | **Approvals** | `/operations?tab=approvals` | Active | Deciding: admin |
| Automation | **Operations** | `/operations` | Active | Some buttons: admin |
| Revenue | **Revenue Operations** | `/revenue` | **Not active** — "Backend contract pending" | |
| Revenue | **Recovery Proof** | `/proof` | Active (read-only) | |
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
- **Accept invitation** — `/invite`. Opened from an invitation link.
- **Client portal** — `/portal/…`. For clients, opened from a portal link.

A **not active** item opens a placeholder page headed **"Full-platform architecture"**, with a
**"Configuration required"** or **"Backend contract pending"** badge. It says: *"No sample records or
simulated writes are shown."* Nothing can be done there. That is by design, not a fault.

### 4.4 Module quick reference

Full procedures are in [Chapter 7](#7-crm-daily-use).

| Module | What it is for | Key actions | Do **not** | Saved when you see |
|---|---|---|---|---|
| **Command Center** | Today's priorities | Open cards, act on next actions | Treat an empty dashboard as broken | Lists refresh; toasts for decisions |
| **Contacts / Companies** | People and accounts | **"New contact"**, **"New company"**, open a record | Expect edit, delete or archive — the screens cannot | **"Contact created"** / **"Company created"** |
| **Deals / Pipelines** | Revenue opportunities by stage | **"New opportunity"**, **"Advance →"**, stage menu | Choose **"Closed lost"** by mistake — the card leaves the board and cannot be reopened from the screen | **"Opportunity created"**, **"Moved to {stage}"** |
| **Client 360** | One operating page per client | **"New workspace"**, commitments, tasks, outcomes | Create duplicate workspaces for one client | **"Client workspace created"** |
| **Tasks / Commitments** | Delivery follow-through inside a workspace | **"+ Task"**, **"+ Commitment"**, status menus, **"Run SLA check"** | Expect to edit a title, owner or due date after creating | **"Task added"**, **"Commitment added"**, **"Updated"** |
| **Action Center** | Alerts needing follow-through; notification settings | **"Acknowledge"**, **"Resolve"**, preferences | Resolve an alert you have not dealt with | **"Alert resolved"**, **"…preferences were saved"** |
| **Operations** | Recommendations, work queue, recovery, approvals, conversations | **"Approve"** / **"Reject"**, **"Acknowledge"**, **"Resolve"** | Approve something you have not read — there is no confirmation | **"Approved"**, **"Resolved"** |
| **Recovery Proof** | What was recovered, with evidence | Read figures, open a case | Add "potential" and "confirmed" together | Read-only |
| **Client Operations** | Portal links, documents, estimates, appointments | Create records per workspace | Lose a new portal link — it is shown only once | Toast per action |
| **Registries** | Integrations and webhooks | **"Connect"**, **"Re-authorize"**, **"Sync"**, **"Disconnect"** | Disconnect Google during an active send | **"Google connected"**, **"Synced Gmail: …"** |
| **Team & Access** | Users, roles, invitations | **"Invite member"**, role menu, **"Disable"** | Post an invite link anywhere public | **"Invitation created"**, **"Member disabled"** |
| **Settings** | Your profile, notification and provider status, links onward | **"Refresh status"**, **"Sign out"** | Expect to change your password here — it is not possible | Status pills update |
| **Automation & Audit** | The record of every significant change | Read; admin **"Undo"** of approved AI tool writes | Undo without a reason — a reason is required | **"Reversed"** |
| **MCP Console** | Governed AI tool operations | Invoke tools; admin **kill switch** | Flip the kill switch casually | **"Kill switch ON — tools disabled"** |
| **Search (Ctrl/⌘ K)** | Jump to a module | Type a module name | Expect it to find a contact — it cannot | — |
| **Import / Export** | — | **Not available in the screens** | — | — |
| **Reporting** | — | **Not active** (Recovery Proof is the live report) | — | — |

---

## 5. Google / Gmail Setup

### 5.1 What the Google connection does

One Google consent connects **two** cards at once: **Gmail** and **Google Calendar**.
Verified (code). With the connection active, the CRM:

- **reads Gmail** — the 25 most recent messages' headers (sender, recipients, subject, labels and
  snippet), matched to your contacts by email address. They appear on a client's **Client 360** →
  **Activity** → **"Recent email threads"**.
- **captures replies** — every 30 minutes (at :10 and :40 past the hour) it checks the inbox for
  the last 7 days and attaches replies to the conversations they answer ([§6](#6-email-production-verification)).
- **sends email** — only messages a human approved, and only through the connected mailbox
  ([§6](#6-email-production-verification)).
- **reads Google Calendar** — the next 25 events, matched to contacts by attendee email. They
  appear under **Client 360** → **Activity** → **"Upcoming meetings"**.

Only **admins** can connect, re-authorize, sync or disconnect. Members see **"Admin manages"**.

### 5.2 Exact Google permissions (scopes) the CRM requests

Verified (code), from `GOOGLE_SCOPES` in `backend/server.py`:

| Scope | What Google shows the user (wording varies) | Why ClientVerse needs it |
|---|---|---|
| `https://www.googleapis.com/auth/gmail.readonly` | View your email messages and settings | Gmail sync, reply capture, and the duplicate check before every send |
| `https://www.googleapis.com/auth/gmail.send` | Send email on your behalf | Sending approved messages. It cannot read, delete or change mail. |
| `https://www.googleapis.com/auth/calendar.readonly` | See your calendars and events | Meetings on Client 360 |
| `https://www.googleapis.com/auth/userinfo.email` | See your primary Google Account email address | Showing which mailbox is connected ("Account: …") |
| `openid` | Associate you with your personal info on Google | Standard sign-in identity |

How the request is made:

- ClientVerse requests **offline access**, so it can refresh the permission without you present.
- It forces Google's consent screen every time.
- It uses PKCE and a one-time `state` value.
- **The consent must be finished within 10 minutes**, or the attempt expires.

### 5.3 Where the Google controls are

- **Path A:** **Settings** → the **"Connected providers"** card lists **Gmail**,
  **Google Calendar** and **Stripe** with a status. Click **"View integrations"**.
- **Path B:** sidebar → **Platform** → **"Registries"**.

Either path lands on the **Registries** page, on the **"Integrations"** tab (the first of
**"Integrations"**, **"MCP Servers"**, **"Plugins"**, **"Webhooks"**). The page shows:

- a **"Status honesty"** note
- one card each for **Gmail**, **Google Calendar** and **Stripe**
- below them, **"Governed capability contracts"** — catalogue records, for information

The Gmail card's description still reads *"Read-only message + thread metadata…"*. That text is
older than the send feature; the connection now also carries send permission ([§5.2](#52-exact-google-permissions-scopes-the-crm-requests)).

### 5.4 Read the connection status

| Registries badge | Settings label | Meaning | Buttons (admin) | Your action |
|---|---|---|---|---|
| **"Not connected"** | Not connected | No Google permission is stored | **"Connect"** | [§5.5](#55-connect-google-first-time) |
| **"Connecting…"** | Connecting… | A consent was started and never finished — for example cancelled at Google | **"Sync"**, **"Disconnect"** | If still shown after 10 minutes: full reset ([§5.7](#57-disconnect-safely-and-when-it-is-required)) |
| **"Connected"** | Connected | The permission is active | **"Sync"**, **"Disconnect"** | None. Confirm send permission ([§5.8](#58-verify-that-gmailsend-was-actually-granted)) |
| **"Degraded"** | Needs attention | The last sync failed for a non-permission reason | **"Sync"**, **"Disconnect"** | **"Sync"** once. If still degraded, escalate. |
| **"Needs auth"** + **"Re-authorize"** tag | Needs auth | Google refused to refresh the permission (expired or revoked) | **"Re-authorize"**, **"Sync"**, **"Disconnect"** | [§5.6](#56-re-authorize-google) |
| **"Error"** | Error | Connecting failed while exchanging the Google code | **"Reconnect"**, **"Sync"**, **"Disconnect"** | **"Reconnect"**. If it repeats, see [§5.9](#59-google-troubleshooting). |

Other parts of the card:

- **"Stale"** tag — connected, but no successful sync for more than 24 hours.
- **Red line under the card** — the last error, for example `token_refresh_failed:400`.
- **"Account: …"** — the Google address connected.
- **Small grey tags** (`gmail.readonly`, `gmail.send`, …) — the permissions the CRM **asked for and
  recorded**. They are **not proof** that Google granted them. See [§5.8](#58-verify-that-gmailsend-was-actually-granted).

### 5.5 Connect Google (first time)

**One-time prerequisites (owner, in Google Cloud)** — governing-document owner action O-01:

- **Recorded done:** `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set in Railway. The
  2026-09-30 boot log line `Registered outbound channel provider: gmail` confirms the server sees
  them.
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
2. On the **Gmail** card, click **"Connect"**. The **Google Calendar** card's **"Connect"** does
   the same thing.
3. Google opens. Choose the Google account whose mailbox the CRM should use. **This mailbox becomes
   the "From" address of every email the CRM sends.**
4. If Google warns **"Google hasn't verified this app"**, check that the app name on the screen is
   the one your organization created in Google Cloud. Only then continue. If the name is unfamiliar,
   stop and escalate.
5. On the consent screen, read the permissions. **If Google shows a tick-box for each permission,
   tick every one** — especially the one to **send email on your behalf**. Then click
   **Continue / Allow**.
6. You return to **Registries** → **Integrations** with the message **"Google connected"**.
7. **Check:** both **Gmail** and **Google Calendar** show **"Connected"** and
   **"Account: \<your address\>"**.
8. On the Gmail card, click **"Sync"**.
   - **Check:** the message **"Synced Gmail: N record(s) matched"**, and **"Last sync …"** on the card.
   - N can be 0. That only means none of the 25 newest emails involve a contact's address.
9. Verify send permission ([§5.8](#58-verify-that-gmailsend-was-actually-granted)).

**If it fails**

- **"Google authorization failed"** — you cancelled or refused, or Google returned an error. The
  cards may be left on **"Connecting…"**. Do the full reset in [§5.7](#57-disconnect-safely-and-when-it-is-required).
- **"Authorization link expired — try again"** — more than 10 minutes passed. Start again from
  step 2.

### 5.6 Re-authorize Google

Use this when the Gmail or Google Calendar card shows **"Needs auth"** or **"Error"**.

1. On the **Gmail** card, click **"Re-authorize"** (or **"Reconnect"** on an **"Error"** card).
2. Complete the Google consent exactly as in [§5.5](#55-connect-google-first-time), steps 3–6.
3. **Check:** **"Google connected"**. Both cards read **"Connected"**, with no red error line.
4. Click **"Sync"** on the Gmail card to confirm.

If the cards return to **"Needs auth"** within about a week, see
[§5.9](#59-google-troubleshooting) → *Token refresh returns 400*.

### 5.7 Disconnect safely, and when it is required

**Disconnect first, then connect, when:**

- the card shows **"Connected"** or **"Degraded"** but you need a *fresh* permission. There is no
  **"Re-authorize"** button in those states. This applies when:
  - the permission was granted before send access existed
  - you left **"Send email on your behalf"** unticked
  - you want to use a different Google mailbox
- the cards are stuck on **"Connecting…"**
- the connection keeps looping back to **"Needs auth"** or **"Error"**

**Full reset procedure**

1. Tell your team that Gmail sync, reply capture and outbound email pause until you reconnect.
   Do this when no approved email is waiting to be sent.
2. On the **Gmail** card, click **"Disconnect"**. **Check:** **"Disconnected Gmail"**.
3. On the **Google Calendar** card, click **"Disconnect"**. **Check:**
   **"Disconnected Google Calendar"**.
   - **Why both:** both cards share one saved Google permission. The CRM deletes it only when
     *both* are disconnected. Disconnecting one card revokes the permission at Google, but leaves
     the other card holding it.
4. (Recommended for a stale or looping permission.) Open **Google Account** → **Security** →
   **"Your connections to third-party apps & services"**. Find your ClientVerse app and remove its
   access. ClientVerse already asks Google to revoke on Disconnect; this confirms it.
5. **Check:** both cards read **"Not connected"**, with no **"Account:"** line.
6. Connect again ([§5.5](#55-connect-google-first-time)).

**What Disconnect does not do:** it does not delete email and meeting records already shown on
Client 360, and it does not delete conversations or messages.

### 5.8 Verify that gmail.send was actually granted

Work down this list. Each check is stronger than the one before it.

1. **The CRM's record (necessary, not sufficient).** The Gmail card's grey tags include
   **`gmail.send`**. The CRM writes the permissions it *requested*, so a tag alone does not prove
   Google granted it.
2. **Google's record (owner-verifiable).**
   1. Signed in to the *connected* Google account, open **Google Account** → **Security** →
      **"Your connections to third-party apps & services"**.
   2. Open your ClientVerse app.
   3. Its access list should include **sending email on your behalf** (Gmail). If it only lists
      reading email, the permission is read-only: do the full reset in [§5.7](#57-disconnect-safely-and-when-it-is-required)
      and tick every box.
3. **The CRM's authorization view.** Open **Operations** → **"Recovery strategies"** tab. The amber
   box **"Outbound channels not authorised"** lists every channel that cannot send (**SMS** and
   **PHONE** always appear; no provider exists for them). Then read:
   - **"EMAIL — No connected email provider (gmail is not connected)."** — the Gmail card is not
     **"Connected"**. Re-authorize or reconnect.
   - **"EMAIL — gmail is connected, but no integration record marks it configured for this tenant,
     so outbound email is not certified."** — the Google side is fine. Sending is held by the CRM's
     **certification gate**, which only engineering can clear ([§6.1](#61-read-this-first--current-status)).
   - **EMAIL not listed at all** — the email channel is authorized.
4. **Definitive proof.** A real message reaches status **"sent"** ([§6](#6-email-production-verification)).

### 5.9 Google troubleshooting

**Token refresh returns 400 (Needs auth).**

- **Seen live on 2026-09-30 at 16:08 UTC.** During the scheduled sync, Railway logged
  `POST https://oauth2.googleapis.com/token` → `400 Bad Request`, twice (Gmail and Calendar).
- **What it means:** Google rejected the saved permission. The CRM marks both cards
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
- **It fails again immediately after a fresh reconnect:** the `GOOGLE_CLIENT_SECRET` in Railway
  probably no longer matches Google Cloud. Escalate: the owner updates the Railway variable with
  engineering.

**Reconnect loop** — you connect, return, and the cards stay on **"Connecting…"** or go straight
to **"Error"**.

1. Do the full reset in [§5.7](#57-disconnect-safely-and-when-it-is-required), including step 4.
2. Connect again, finishing within 10 minutes, and tick every permission.
3. If Google itself shows **"Error 400: redirect_uri_mismatch"**, the Google Cloud redirect URI is
   wrong ([§5.5](#55-connect-google-first-time) prerequisites). That is an owner fix in Google Cloud.
4. If the card shows **"Error"** with `token_exchange_failed`, the client secret or redirect URI
   does not match. Escalate with a screenshot.

**Stale permission** — **"Connected"** but tagged **"Stale"**, or no new email on Client 360.

1. Click **"Sync"** on the card.
2. If the red error line appears, act on it (above).
3. If there is still no new data and no error, do the full reset.

**Other messages**

| Message | Meaning | Who fixes it |
|---|---|---|
| **"Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."** | Railway variables missing | Owner in Railway, with engineering |
| **"Google OAuth redirect is not configured. Set GOOGLE_REDIRECT_URI or PUBLIC_BACKEND_URL."** | No usable redirect address | Engineering |
| **"Access blocked"** (at Google) | Your account is not a test user, or the app is restricted | Owner in Google Cloud |
| **"Integration center unavailable"** | The Registries page could not load connections | Reload; if it repeats, escalate |
| **"Sync failed: rate_limited"** | Google throttled requests | Wait 15 minutes and retry |
| **"Sync failed: not_connected"** | No stored permission | Connect ([§5.5](#55-connect-google-first-time)) |

**Who does what**

| Owner can do it | Needs engineering |
|---|---|
| Connect, Re-authorize, Sync, Disconnect | Changing `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` or `PUBLIC_BACKEND_URL` (with the owner) |
| Google Cloud consent screen, test users, redirect URI, publishing status | Outbound email certification ([§6.1](#61-read-this-first--current-status)) |
| Removing app access in the Google account | Any error that survives a full reset |

---

## 6. Email Production Verification

### 6.1 Read this first — current status

**Status on 2026-09-30: BLOCKED.** Three verified reasons, and each needs a different person:

1. **The Google permission needs re-authorization** — Google refused the refresh on 2026-09-30,
   ([§5.9](#59-google-troubleshooting)). **Owner:** [§5.6](#56-re-authorize-google).
2. **No screen can compose or send an email, or record a contact's consent.**
   - **Operations** → **"Conversations"** can only *read* a thread, **"Hand to human"** /
     **"Hand to agent"**, and **"Close"**.
   - Creating a conversation, recording consent, drafting, requesting approval and sending exist
     only as server API calls. Verified (code).
   - **Engineering-assisted:** an engineer performs those steps ([Appendix C](#appendix-c-engineer-assisted-email-verification))
     while the owner approves and verifies in the screens.
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

Reply capture additionally needs the scheduler, which is running as of 2026-09-30 ([§11.6](#116-current-state-verified-live-2026-09-30)).

**How do I send a real email?** Today, only through the engineer-assisted procedure below, once
reasons 1 and 3 are cleared. The Gmail **"Sync"** button does not send anything. It is a read-only
mirror of the inbox.

### 6.2 Result definitions

| Result | Means |
|---|---|
| **PASS** | Every expected result in the step was observed, and its evidence was captured ([§6.8](#68-what-counts-as-pass-evidence)). |
| **FAIL** | The step ran, and the CRM or Google did something other than expected — for example two copies arrived, or a reply landed on the wrong conversation. |
| **BLOCKED** | The step could not run because a prerequisite is missing (for example **"Needs auth"**, or the certification gate). Record the exact blocking message. |
| **NOT TESTED** | Not attempted yet. |

### 6.3 Prerequisites (owner-verifiable)

- [ ] The **Gmail** card is **"Connected"**, and **"Account:"** shows the sending mailbox ([§5.4](#54-read-the-connection-status)).
- [ ] Google shows the send permission ([§5.8](#58-verify-that-gmailsend-was-actually-granted), check 2).
- [ ] **Operations** → **"Recovery strategies"** does **not** list **EMAIL** as not authorised ([§5.8](#58-verify-that-gmailsend-was-actually-granted), check 3).
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
   1. Read the summary: it is the exact text that will be sent.
   2. If the row says **"Approving this will not unblock it — …"**, note the reason. The send will
      be refused (BLOCKED).
   3. Click **"Approve"**. **Check:** **"Approved"**.
3. **Engineer:** send the message (Appendix C, step 6).
4. **Owner — verify it left the CRM:**
   1. **Operations** → **"Conversations"** → open the thread.
   2. The **OUTBOUND** message shows status **"sent"**.
   3. **Automation & Audit** shows an event `communication_message.sent`.
5. **Owner — verify Google accepted it:** in the connected mailbox, Gmail's **Sent** folder holds
   the message.
6. **Owner — verify delivery:** the test mailbox receives it. Check spam too. Note the time.

### 6.5 Procedure B — duplicate protection

1. **Engineer:** repeat the send call for the **same** message (Appendix C, step 7).
2. **Expected:** the CRM refuses — HTTP 409, `message_not_dispatchable`,
   *"…this one is 'sent'"*. The message stays **"sent"**.
3. **Owner:** wait 10 minutes. The test mailbox has **exactly one** copy, and Gmail **Sent** holds
   exactly one.
4. **PASS:** refused, and exactly one copy. **FAIL:** a second copy arrived.

The deeper retry protection is automatic. Before every dispatch the CRM asks Gmail whether it
already holds that message, using a fixed Message-ID. It is covered by automated tests; this step
proves the guarantee you can see.

### 6.6 Procedure C — capture the reply

1. **Owner:** from the test mailbox, **Reply** to the email received. Keep the subject and do not
   change recipients.
2. Wait for the next reply sweep. The scheduler calls `/api/cron/inbound-email` at **:10 and :40**
   past every hour (UTC). GitHub can run a few minutes late, so allow up to **35 minutes**. An
   engineer or the owner can start it at once: GitHub → **Actions** → **Scheduled jobs** →
   **"Run workflow"** → jobs: `inbound-email`.
3. **Owner — verify capture:** **Operations** → **"Conversations"** → the **same** thread shows a
   new **INBOUND** message with status **"received"** and your reply text.
4. **Owner — verify matching:** the reply is on the *same* conversation, not a new one.
   - The CRM matches on Gmail's thread, then on the reply headers, then (only when unambiguous) on
     the sender.
   - An ambiguous reply is **parked for a person** rather than guessed. If the reply is missing
     after 35 minutes, the engineer checks the unmatched queue (Appendix C, step 9).
5. **Contact timeline entry:** the CRM records an activity **"reply_received"** on the contact.
   - **No screen shows a contact's timeline.** The engineer confirms it (Appendix C, step 10).
   - If the conversation is linked to a client workspace, **Client 360** → **"Timeline"** also shows
     the event.
   - **Automation & Audit** always shows `communication_message.received`.
6. **Recovery Proof** → **"Replies received"** counts only replies on recovery cases. A standalone
   test conversation will not change it — do not use it as test evidence.

### 6.7 Where failures surface

| Where | What you see | Meaning |
|---|---|---|
| **Operations** → **"Approvals"** row | **"Approving this will not unblock it — …"** | A prerequisite blocks the send (not connected, consent, certification) |
| **Operations** → **"Conversations"** | Tile **"Blocked messages"** above 0; the message badge **"blocked"**, with the reason | The CRM refused before contacting Google, and named why |
| Same, badge **"failed"** | e.g. *"Gmail rejected the message with HTTP 403…"* | Google refused. Usually the send permission is missing — full reset ([§5.7](#57-disconnect-safely-and-when-it-is-required)) |
| Same, badge **"outcome unknown"** | Google did not confirm either way | **Never re-send.** The reconcile sweep (:10/:40) asks Gmail. Escalate if it persists after 1 hour. |
| **Registries** → Gmail card, red line | e.g. `token_refresh_failed:400` | Permission problem ([§5.9](#59-google-troubleshooting)) |
| **Operations** → **"Recovery strategies"** amber box | **"EMAIL — …"** | Channel not authorised ([§5.8](#58-verify-that-gmailsend-was-actually-granted)) |
| **Automation & Audit** | `communication_message.refused` | A send was refused; the reason is on the message |
| GitHub **Scheduled jobs** | A red run, or no run at :10/:40 | Reply capture did not run ([§11](#11-scheduler--automations)) |

### 6.8 What counts as PASS evidence

- **Outbound:** screenshots of the conversation showing **"sent"**, of Gmail **Sent**, and of the
  received email with its time. The engineer records the message's `provider_message_id` and
  `rfc822_message_id`. These are identifiers, not secrets.
- **Duplicate:** the refusal (HTTP 409 text) and a screenshot showing a single copy.
- **Inbound:** a screenshot of the same thread with the **INBOUND** / **"received"** message, the
  `communication_message.received` audit event, and the engineer's contact-timeline output.
- **Redact** personal email addresses before sharing screenshots outside the company.

---

## 7. CRM Daily Use

Each section gives: **Purpose**, **Where**, **Common actions**, **Common mistakes**, and **Saved when**.

### 7.1 Command Center

- **Purpose:** your daily starting point — pipeline value, won revenue, active clients, delivery
  risk, recommended next steps, alerts and client health.
- **Where:** sidebar → **Command** → **"Command Center"**; or click the ClientVerse logo.
- **Common actions:**
  1. Click a summary card to open its list.
  2. Work the **"Next actions"** list from the top.
  3. In **"Next best actions"**, choose **"Accept"**, **"Done"**, **"Snooze"** (24 hours) or
     **"Not relevant"**.
  4. Under **"Operational Alerts"**, click **"Scan now"** for a fresh alert check. Use the ✓ and ✕
     icons to acknowledge or resolve.
- **Common mistakes:**
  - Treating empty cards as a fault.
  - Expecting **"Connection Health"** to show for members — it is admin-only.
- **Saved when:** **"Alert scan complete (N new)"**; recommendation buttons change the list, and
  only failures show a message (**"Could not record that decision"**).
- **Cosmetic:** the card text may read "opportunityies". That is a display typo, not a data problem.

### 7.2 Contacts and Companies (Directory)

- **Purpose:** the people and accounts behind every relationship.
- **Where:**
  - sidebar → **CRM** → **"Contacts"** or **"Companies"**
  - the page is **Directory**, with the tabs **"Companies"** and **"Contacts"**
  - the top-bar **"Create"** button also creates both
- **Common actions:**
  1. **"New company"**:
     - **"Company name *"** (required)
     - **"Industry"**, **"Website"**, **"Client tier"** (Standard / Growth / Enterprise)
     - then **"Create company"**
  2. **"New contact"**:
     - **"Name *"** (required)
     - **"Email"**, **"Company"**, **"Role"**, **"Influence"**
     - then **"Create contact"**
     - Add the email address: Gmail and Calendar matching depend on it.
  3. Type in the search box to filter the loaded list by name, industry, email or company.
  4. Click a row to open its record:
     - company record tabs: **"Overview"**, **"Contacts"**, **"Revenue"**, **"Client 360"**
     - contact record tabs: **"Overview"**, **"Opportunities"**, **"Client 360"**
- **Common mistakes:**
  - **Records cannot be edited, archived or deleted from the screens.** The server supports it,
    but no button exists. Type carefully. For a correction, ask engineering.
  - Creating the same company twice — search first.
  - Leaving out a contact's email, which stops email and calendar matching.
  - Each list shows at most **200** records. Beyond that, older ones are not visible in the
    screens (UNVERIFIED — OWNER/ENGINEERING INPUT REQUIRED whether any organization has reached this).
- **Saved when:** **"Company created"** / **"Contact created"**. On failure: **"Could not create
  company"** / **"Could not create contact"**, with the reason.

### 7.3 Deals and Pipeline

- **Purpose:** move revenue opportunities through **Lead → Qualified → Proposal → Negotiation →
  Won**.
- **Where:** sidebar → **CRM** → **"Deals"** or **"Pipelines"**. Both open the **Pipeline** board.
- **Common actions:**
  1. **"New opportunity"**:
     - **"Opportunity name *"**
     - **"Estimated value"**, **"Company"**, **"Starting stage"**
     - then **"Create opportunity"**
  2. **"Advance →"** on a card moves it one stage right. Or use the card's stage menu.
  3. Moving a deal to **Won** with a company attached **automatically creates a Client 360
     workspace**: **"Opportunity won — Client 360 workspace created"**.
  4. Use **"Search pipeline…"** and **"All companies"** to filter the board.
- **Common mistakes:**
  - **"Closed lost" removes the card from the board, and the screens cannot reopen it.** It stays
    visible, read-only, on the company record's **"Revenue"** tab. Choose it only when final.
  - Winning a deal with no company — no workspace is created, even though the message still says
    **"Opportunity won — Client 360 workspace created"**. Check **Client 360** afterwards.
  - The **"Company"** button on a card opens the company *list*, not that company.
  - After a win, reload the page to see the card's **"Workspace"** button.
  - There is no drag-and-drop, and no editing of a deal's name, value or company.
- **Saved when:** **"Opportunity created"**, **"Moved to {stage}"**. If a stage change fails, the
  card jumps back and **"Stage change did not save"** appears.

### 7.4 Client 360 workspaces

- **Purpose:** one operating page per client — health, commitments, outcomes, activity, timeline,
  tasks, deliverables, requests and approvals.
- **Where:** sidebar → **Client Success** → **"Client 360"** (list), then **"Open Client 360 →"** on
  a card.
- **Common actions:**
  1. **"New workspace"**:
     - **"Workspace name *"**
     - **"Company"**, **"Lifecycle stage"**
     - then **"Create workspace"**
     - Or win a deal (§7.3).
  2. Filter by the **Onboard / Serve / Retain / Expand** tiles, or with **"Search clients…"**.
  3. In a workspace, read **"Explainable Client Health"**: the score, and the factors raising or
     lowering it.
  4. Use the tabs, starting with **"Commitment Ledger"**:
     - **"Outcome Graph"**, **"Activity"**, **"Timeline"**
     - **"Tasks"**, **"Deliverables"**, **"Requests"**, **"Approvals"**
- **Common mistakes:**
  - Duplicate workspaces for one client.
  - A workspace's name, stage and company cannot be changed after creation.
  - A workspace made from the top-bar **"Create"** button is stored with a slightly different stage
    value, so it does not count under the **Onboard** tile. Prefer **"New workspace"** on the
    Client 360 page.
  - If a workspace page stays on a grey loading skeleton, reload. If it persists, escalate.
- **Saved when:** **"Client workspace created"**; the new workspace opens.

### 7.5 Tasks, deliverables, client requests and approvals (inside a workspace)

- **Purpose:** delivery follow-through for one client.
- **Where:** **Client 360** → a workspace → the **"Tasks"**, **"Deliverables"**, **"Requests"** or
  **"Approvals"** tab.
- **Common actions:**
  1. **"+ Task"** / **"+ Deliverable"** / **"+ Request"** / **"+ Approval"**:
     - type a clear **"Title *"**
     - click **"Add task"** / **"Add deliverable"** / **"Add request"** / **"Request approval"**
  2. Change status with the menu on each row:
     - tasks: `todo` → `in_progress` → `done`
     - deliverables: `draft` → `in_review` → `approved`
     - requests: `open` → `in_progress` → `done`
     - **Marking a task done** = choose `done` in its menu.
  3. **Approvals:** an admin sees **"Approve"** / **"Reject"**. Members see **"Awaiting admin"**.
- **Common mistakes:**
  - Only the title can be entered. The assignee, description and priority cannot be set, and
    nothing can be edited or deleted later.
  - Status-menu changes show no message if they fail. Refresh the tab to confirm.
- **Saved when:** **"Task added"** / **"Deliverable added"** / **"Request added"** /
  **"Approval requested"**; **"Approved"** / **"Rejected"**.

### 7.6 Commitments

- **Purpose:** promises made to a client, each with an owner and a due date, so risk is visible
  before it becomes a breach.
- **Where:** **Client 360** → a workspace → **"Commitment Ledger"** (the default tab).
- **Common actions:**
  1. **"+ Commitment"**:
     - **"Title"**, **"Owner"** (an email address), **"Due date"**
     - then **"Add commitment"**
  2. The ledger shows **"due in Nd"** or **"overdue Nd"**, with a status badge.
  3. Change status with the menu: `open`, `at_risk`, `breached`, `fulfilled`.
  4. **"Run SLA check"** runs the risk check now across your **whole organization**, not only this
     workspace:
     - due within 48 hours → `at_risk`
     - past due → `breached`
     - The scheduler does this automatically every 15 minutes ([§11](#11-scheduler--automations)).
- **Common mistakes:**
  - The owner and due date cannot be changed after creation.
  - A failed status change shows no message — refresh to confirm.
- **Saved when:** **"Commitment added"**, **"Updated"**,
  **"SLA check complete · N at-risk, N breached"**.

### 7.7 Outcome Graph and evidence-backed AI

- **Purpose:** measurable client outcomes (goals with targets), and health over time.
- **Where:** a workspace → **"Outcome Graph"** tab; the **"Evidence-backed AI"** panel on the
  workspace page.
- **Common actions:**
  1. **"Add outcome"**:
     - **"Title"**, **"Target description"**, **"Target value"**, **"Unit"**
     - then **"Create"**
  2. Type a new value in **"Update"** and press ✓ or Enter. **Check:** **"Progress updated"**.
- **AI:**
  - **"Health Summary"** / **"Draft Message"**, then **"Generate with evidence"**.
  - **Not active in production:** the AI key (`EMERGENT_LLM_KEY`) is not set, so this returns
    **"AI generation failed. Please retry."** Retrying will not help.
  - It is an open owner decision (governing document O-11). A drafted message is never sent
    automatically.
- **Common mistakes:**
  - A blank title makes **"Create"** do nothing.
  - Goals cannot be renamed or deleted.
- **Saved when:** **"Outcome added"**, **"Progress updated"**.

### 7.8 Activity and Timeline

- **Purpose:** what is happening with a client — matched email, meetings and billing (Activity),
  and every event, alert and health signal (Timeline).
- **Where:** a workspace → **"Activity"** / **"Timeline"** tabs.
- **Common actions:**
  - **Activity** is read-only:
    - **"Upcoming meetings"**
    - **"Billing & subscriptions"**
    - **"Recent email threads"** — items tagged **"External"**
  - **Timeline:**
    - search **"Search timeline…"**
    - filter by source and severity
    - page with **"Prev"** / **"Next"**
    - **"Ack"** or **"Resolve"** an alert
- **Common mistakes:** expecting email on Activity before Google is connected and synced. Its empty
  state says to connect from **Registries → Integrations**.
- **Saved when:** **"Alert acknowledged"** / **"Alert resolved"**.

### 7.9 Action Center and notifications

- **Purpose:** client risks and delivery blockers that need a person, plus your notification
  preferences.
- **Where:** sidebar → **Command** → **"Action Center"**; the bell → gear icon.
- **Common actions:**
  1. Work the **"Action inbox"** tab:
     - **"Priority work queue"** → **"Open client"**, **"Acknowledge"**, **"Resolve"**
     - **"Recent alert activity"** → **"Mark read"**, **"Mark all read"**
  2. **"My preferences"**:
     - channels, alert categories, daily digest, digest hour, timezone, escalation
     - then **"Save my preferences"**
  3. Admin: **"Team defaults"** tab → **"Save team defaults"**. Admin: **"Send digest"** sends a
     digest now.
  4. **Bell:** the unread count (checked every 30 seconds), **"Mark all read"**; click an item to
     open it.
- **Email notifications are not active.** An amber banner reads **"Email delivery is not
  configured."** because `EMERGENT_EMAIL_KEY` is not set. In-app notifications work.
- **Common mistakes:**
  - Resolving an alert before the underlying issue is fixed. It will reappear.
  - If the page stays on a loading skeleton after **"Could not load notification preferences"**,
    reload.
- **Saved when:**
  - **"Alert acknowledged"** / **"Alert resolved"**
  - **"Your notification preferences were saved"**
  - **"Team notification defaults were saved"**

### 7.10 Operations

- **Purpose:** the control room for automation — recommendations, the durable work queue,
  recovery strategies, approvals, client conversations and the security gate.
- **Where:** sidebar → **Automation** → **"Operations"**. Heading **"Recovery & automation
  control"**.
- **Tabs and common actions:**

  | Tab | What you can do | Admin only |
  |---|---|---|
  | **"Next best actions"** | **"Refresh"**; **"Accept"** / **"Done"** / **"Snooze"** / **"Not relevant"** | — |
  | **"Work queue"** | **"Acknowledge"**, **"Resolve"**; tiles **"Open"**, **"Retry scheduled"**, **"Dead letter"**, **"Needs operator"** | **"Run recovery detection"**, **"Replay"** |
  | **"Recovery strategies"** | Read proposed strategies. The amber box **"Outbound channels not authorised"** ([§5.8](#58-verify-that-gmailsend-was-actually-granted)) | **"Compose strategies"** |
  | **"Approvals"** | Read what is waiting | **"Approve"**, **"Reject"** |
  | **"Conversations"** | Read threads; **"Hand to human"** / **"Hand to agent"**; **"Close"** | — |
  | **"Security gate"** | Read scanner and component status (read-only) | — |

- **Common mistakes:**
  - **Approving without reading.** **"Approve"** takes effect on one click, with no confirmation.
    The summary on the row is exactly what will run or be sent.
  - Expecting **"Conversations"** to compose or send email. It cannot ([§6.1](#61-read-this-first--current-status)).
  - Expecting a consent button. Consent is recorded only by an admin through the API.
  - The **"Security gate"** shows **"Scanners not configured"** until the owner supplies scanner
    endpoints (governing document O-14). That is the intended safe default.
- **Saved when:**
  - **"Approved"** / **"Rejected"**
  - **"Acknowledged"** / **"Resolved"** / **"Replayed"**
  - **"Handoff recorded"**, **"Closed"**
  - **"Detection complete · N new, N already open"**

### 7.11 Recovery Proof (proof and reporting)

- **Purpose:** what the recovery engine found, what was actually sent, and what was recovered,
  with the records that prove it.
- **Where:** sidebar → **Revenue** → **"Recovery Proof"**.
- **What you see:**
  - **"Open potential"** — an estimate, *not revenue*
  - **"Attributed recovered"** — money a record says arrived after outreach reached the client
  - **"Unattributed outcomes"**
  - counters: **"Cases detected"**, **"Cases worked"**, **"Messages sent"**, **"Replies received"**,
    **"Outcome unknown"**, **"Blocked or failed"**, **"Median time to recovery"**
  - **"Cases"** — click one for its evidence, attribution and messages
- **Common mistakes:** adding "potential" and "recovered" together. They are deliberately separate.
  An empty report (**"No recovery cases yet"**) is honest, not broken.
- **Saved when:** read-only.
- The sidebar **"Reporting"** item is not active; this is the live report.

### 7.12 Client Operations and the client portal

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
       issued invoices, and can **"Submit request"**.
  2. **"Commercial"** → **"Add document"**, **"Create estimate"** (admin).
  3. **"Appointments"** → **"Schedule"**; **"Prepare reminder"** creates an *internal* task only.
  4. **"Growth"** → **"Add referral source"**; **"Prepare for approval"** (review request, admin).
  5. **"Safe automation"** (admin) → **"Enable safe workflow"**, **"Run safely"**. These only
     create internal tasks.
  6. **"Capacity & playbooks"** (admin) → **"Apply"** a playbook's task sequence.
- **Common mistakes:**
  - Losing a portal link. There is no revoke button and no way to show it again; ask engineering
    to revoke a leaked link.
  - Members clicking **"Create estimate"** or **"Prepare for approval"** get a permission refusal.
    These are admin actions.
  - **"Create invoice"** appears only for sent or approved estimates, and the screens cannot mark an
    estimate sent. Treat invoicing here as a record, not billing. Stripe is not configured.
  - Nothing here sends email or SMS, or charges a card.
- **Saved when:** a message per action — e.g. **"Client portal link created"**,
  **"Estimate drafted"**, **"Appointment scheduled"**. Errors read **"Action could not be
  completed"**.

### 7.13 Field Ops

- **Purpose:** on-site check-ins from a phone.
- **Where:** type `/field` after the production address. There is no sidebar entry.
- **Common actions:**
  - **"Check in to a client workspace"**: **"Workspace"**, **"Location label"**, **"Onsite note"**,
    then **"Save check-in"**
  - **"Prepare reminder"** on an upcoming appointment
- **Common mistakes:** expecting photo upload. It is not available.
- **Saved when:** **"Field check-in saved"**.

### 7.14 Automation & Audit

- **Purpose:** the organization's record of every significant change, including approvals, sends,
  sign-in denials and team changes.
- **Where:** sidebar → **Platform** → **"Automation & Audit"**.
- **Common actions:** read the newest 200 events. Each shows its type, actor and time. Admin:
  **"Undo"** on an approved AI-tool write, within the undo window (default 60 minutes), with a
  **required reason**.
- **Common mistakes:** there is no search or filter — use your browser's find (Ctrl/⌘ F).
- **Saved when:** **"Reversed"** (undo).

### 7.15 MCP Console (governed AI tools)

- **Purpose:** run the CRM's governed tools. Read tools run at once; write tools need approval
  first.
- **Where:** sidebar → **Platform** → **"MCP Console"**.
- **Common actions:**
  - Pick a tool, fill its fields, **"Invoke tool"**.
  - A Level-2 write returns **"Approval required (Level 2)"**; an admin approves it in
    **Operations** → **"Approvals"**.
  - Admin: the **"Kill switch"** disables all tools at once.
  - Admin: **"Undo"** in **"Execution History"**.
- **Common mistakes:** flipping the kill switch as a test. Everyone sees the toggle, but only admins
  can change it.
- **Saved when:** **"{tool} → {status}"**; **"Kill switch ON — tools disabled"** /
  **"Kill switch OFF — tools live"**.

### 7.16 Search

- **Ctrl/⌘ K** (top-bar **"Search modules and actions…"**) finds **modules and actions only** —
  for example "Pipeline", "Team & Access", "Create opportunity". **It does not find contacts,
  companies, deals or workspaces.**
- To find a record, open its list page and use that page's search box:
  - Directory: **"Search companies…"** / **"Search contacts…"**
  - Pipeline: **"Search pipeline…"**
  - Client 360: **"Search clients…"**
  - a workspace's **"Search timeline…"**

### 7.17 Import and export

**Not available in the screens.** The server has CSV import and export functions, but no button
calls them. For a data export (a backup copy, or offboarding a client), ask engineering. See also
[§13.5](#135-backups-and-data-export).

### 7.18 Known screen limitations (current code)

These are verified behaviours of the deployed code. None loses data.

1. **No editing, archiving or deleting** of companies, contacts, deals or workspaces.
2. **No compose, send or consent screen** for email ([§6.1](#61-read-this-first--current-status)).
3. **Closed-lost deals leave the board** and cannot be reopened in the screens.
4. **Lists show at most 200 records** per type.
5. **No message on some failures:** workspace status menus, the commitment form and outcome
   updates. Refresh to confirm the change saved.
6. **A session that expires mid-use does not redirect** to the sign-in page. Pages show
   "…unavailable" errors instead. Reload the page to sign in again ([§9.4](#94-stale-browser-session)).
7. **Invitations are not emailed.** You share the link yourself ([§8.2](#82-invite-a-user)).
8. **Some buttons are visible to members but refused by the server:**
   - the MCP **"Kill switch"**
   - the webhook on/off switch
   - **"Create estimate"**
   - **"Prepare for approval"**
9. **Cosmetic:** the word "opportunityies".

---

## 8. Users, Roles, and Administration

### 8.1 Roles and permissions

There are exactly two roles: **admin** and **member** (Verified (code)). The server enforces them
on every request, and hiding a button is never the protection.

| Action | Admin | Member |
|---|---|---|
| Sign in; view all CRM records of your organization | ✓ | ✓ |
| Create companies, contacts, deals, workspaces, tasks, commitments, outcomes | ✓ | ✓ |
| Move deal stages; change task, commitment and deliverable status | ✓ | ✓ |
| Acknowledge or resolve alerts and work items; next-best-action decisions | ✓ | ✓ |
| Personal notification preferences | ✓ | ✓ |
| **Team & Access** — invite, resend, revoke, change role, disable/enable | ✓ | ✗ |
| Connect / re-authorize / sync / disconnect integrations; see **"Connection Health"** | ✓ | ✗ |
| **"Approve"** / **"Reject"** approvals (workspace and Operations) | ✓ | ✗ |
| Record conversation consent (API only) | ✓ | ✗ |
| MCP kill switch, undo, workspace undo window | ✓ | ✗ |
| Webhook create / enable / reveal secret / rotate secret | ✓ | ✗ |
| Portal links, estimates, invoices, review requests, safe automations, playbooks | ✓ | ✗ |
| Team notification defaults; **"Send digest"** | ✓ | ✗ |
| Read the scheduler ledger (`/api/cron/health`, `/api/cron/runs`) | ✓ | ✗ |

A member who tries an admin action sees **"You do not have permission to perform this action"**.

### 8.2 Invite a user

1. Sidebar → **Platform** → **"Team & Access"**. The heading reads **"Team & Access"**.
2. Click **"Invite member"**. The dialog **"Invite a member"** opens.
3. **"Email"** — the person's work address. **"Role"** — **"member"** (default) or **"admin"**.
4. Click **"Create invite"**. The button briefly reads "Sending…", **but nothing is emailed**.
5. **Check:** **"Invitation created"**. The dialog changes to **"Invitation ready"**, showing the
   link.
6. Click the copy icon (**"Invite link copied"**), then **"Done"**.
7. **Send the link to the person yourself, privately** — a direct email or a private message.
   - **The link is a single-use key to your organization until it is accepted.**
   - Never post it in a public channel, GitHub, or a shared document.
8. The link **expires in 7 days**. The invitation appears under **"Pending invitations (N)"**.

Possible refusals:

- **"This person is already an active member of your team"**
- **"An active invitation already exists for this email"** — use **"Resend"** instead.

### 8.3 What to tell the invitee (accepting an invitation)

1. Open the link. The page reads **"Join {organization}"** and *"This invitation was sent to
   {email}."*
2. Click **"Sign in to accept"**.
   - **Already have a ClientVerse account with that exact email?** Sign in with it.
   - **New?** Click **"Create one"**. Enter **"Your name"**, the **invited email** exactly, and a
     strong **"Password"**. Click **"Create secure workspace"**. (This briefly creates a personal
     organization; accepting moves you into the inviting one.)
3. Back on the invitation, click **"Accept & join {organization}"**.
4. **Check:** **"You're in!"** — *"You joined {organization} as a {role}."* Then click **"Continue
   to workspace"**.
5. **Do not use "Continue with Google"** for this: it ignores the invitation and can create a
   separate organization.

If it says *"You're signed in as X, but this invite is for Y"*, click **"Switch account"** and sign
in with the invited email.

**Warning — an account belongs to one organization at a time.** Accepting an invitation *moves* the
account into the inviting organization. Verified (code): `accept_invitation` replaces the
account's organization and role. After that, the account no longer opens its previous
organization. The screens offer no way to switch back.

- Accepting with a brand-new account, or with the throw-away personal organization that
  **"Create one"** makes, is harmless.
- **Do not accept with an account already used for another real organization.** Invite a
  different email address instead, or ask engineering first.
- **Owner: never accept an invitation from any other organization with your owner account** (the
  `ADMIN_EMAIL` address). The owner account would leave **"ClientVerse HQ"**, and a restart would
  not bring it back. Only engineering could repair it.

### 8.4 Resend an invitation

In **"Pending invitations"**, click **"Resend"** on the row.

- It creates a **new link** and restarts the 7 days. **The old link stops working.**
- **Check:** **"New invite link generated"**, and the dialog shows the new link to share.

### 8.5 Revoke an invitation

In **"Pending invitations"**, click **"Revoke"**.

- **There is no confirmation.**
- **Check:** **"Invitation revoked"**. The link now shows **"Invitation revoked"** to anyone who
  opens it.

### 8.6 Expired invitations

Expired invitations move to **"History:"**, which has no buttons. To re-invite, create a **new**
invitation for the same email ([§8.2](#82-invite-a-user)).

### 8.7 Change a member's role

1. **"Members (N)"** table → the person's **"Role"** menu → **"admin"** or **"member"**.
2. **Check:** **"{email} is now {role}"**.
3. **The last active admin cannot be demoted:** *"Cannot demote the last active admin. Promote
   another admin first."*

### 8.8 Offboard a user (disable)

1. **"Members (N)"** → the person's row → **"Disable"**. **There is no confirmation.**
2. **Check:** **"Member disabled"**. From their very next action they see **"Your access to this
   workspace has been disabled"**, even on an open session.
3. Also:
   - revoke any pending invitations they created that you do not want
   - rotate any shared secret they knew (webhook secrets, Railway access, Google Cloud access)
   - remove them from Railway, GitHub, Google Cloud and MongoDB Atlas if they had access there
4. **To restore access:** click **"Enable"** (**"Member re-enabled"**).
5. **There is no delete.** Disabled members stay listed, for the audit trail.
6. The last active admin cannot be disabled.

### 8.9 Organizations (tenants) and workspaces

- **Organization (tenant):** your company's private space. The owner's is **"ClientVerse HQ"**.
  Every record belongs to exactly one organization.
- **Client workspace (Client 360):** one client's operating page *inside* your organization. It is
  not a separate login or a separate organization.
- **Cross-organization isolation:** people in another organization cannot see your records. A
  direct link to one of your records returns *"not found"* (404) for them.
  - Verified (code and automated tests).
  - Last proven live on 2026-09-01 (`ca30587`, production smoke including the cross-tenant 404).
- **Anyone can create their own separate organization** with **"Create one"** on the sign-in page.
  It cannot see your data. It is not a way to join yours.

### 8.10 Ownership considerations

- **Keep at least two active admins.** If one is locked out or leaves, the other can still manage
  the team and integrations.
- The owner account is tied to `ADMIN_EMAIL`, and its password is always reset to `ADMIN_PASSWORD`
  at each deploy ([§3.3](#33-which-account-the-owner-uses)).
- **To hand day-to-day ownership to someone:** invite them as **admin**, confirm they can sign in,
  then decide with engineering whether `ADMIN_EMAIL` stays as is. Never change it yourself.
- Records carry an "owner" (the person who created them). The screens cannot reassign it.

### 8.11 Actions that need engineering

| Request | Why |
|---|---|
| Delete a user, or change a user's email address | No screen or API |
| Reset a **member's** forgotten password | No reset feature exists ([§9.2](#92-forgotten-password)) |
| Change `ADMIN_EMAIL` | It would create a new, empty organization |
| Edit, archive, restore or delete records; import or export data | Server-only functions |
| Revoke a client portal link | No revoke button |
| Certify outbound email | Certification record ([§6.1](#61-read-this-first--current-status)) |

---

## 9. Account Recovery

### 9.1 Wrong password

1. Retype the password carefully. Check Caps Lock and the email address.
2. **Stop after 3 failures.** At 5 the account locks for 15 minutes ([§3.7](#37-lockout-behaviour)).
3. **Owner account:** copy the password from the Railway variable `ADMIN_PASSWORD` (Railway →
   service → **Variables**) or from your password manager.
4. Still failing: [§9.2](#92-forgotten-password).

### 9.2 Forgotten password

**There is no "Forgot password" link and no in-app password change.**

- Settings says *"Profile and password edits are not exposed by the current CRM API."*
- A password change/recovery feature was prepared on 2026-09-27 (local commit `b8b8b4c`), but it
  is **not on GitHub and not in production**. The owner must push it before it can be reviewed and
  deployed.

**Owner account — reset it in Railway** (the owner can do this):

1. Sign in to Railway → project `welcoming-vibrancy` → service `clientverse-crm-production` →
   **Variables**.
2. Edit **`ADMIN_PASSWORD`**. Paste a new strong password from your password manager, then save.
   If Railway shows the change as staged, click **Deploy** to apply it.
3. **Do not touch any other variable** — above all, not `ADMIN_EMAIL`.
4. Wait until the new deployment shows **SUCCESS** (about 2–5 minutes).
5. Sign in with the new password. If you were locked out, wait out the 15 minutes first.
   Changing the password does not lift a lockout.

**Member account:** no one in the organization can reset it. Escalate to engineering.

### 9.3 Account locked out

1. Stop trying — attempts while locked do not help.
2. Wait **15 minutes** after the fifth failure.
3. Try **once**, carefully, with the correct password. One more failure re-locks the account for
   another 15 minutes.
4. If you do not know the correct password, reset it first ([§9.2](#92-forgotten-password)), then
   wait out the lock.
5. **Engineering** can clear a lock early, in the database.

### 9.4 Stale browser session

**Symptoms:** after a long break, pages show **"… unavailable"**, **"Something went wrong."** or
empty lists, while `/api/health` is fine. Sessions last 7 days. When one expires or is revoked
mid-use, the screens do not jump to the sign-in page by themselves.

1. **Reload** the page (F5 / ⌘R). If the session has ended you land on the sign-in page — sign in
   again.
2. If you land back on the same errors, do the full reset ([§9.8](#98-full-sign-out-and-sign-in-reset)).

### 9.5 "Your access to this workspace has been disabled"

An admin disabled your membership. Ask an admin to **"Enable"** you ([§8.8](#88-offboard-a-user-disable)).
If you are the only admin, you cannot be disabled — the server prevents it.

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
2. **`ADMIN_PASSWORD` was changed** in Railway, possibly by someone else. Read the current value
   there.
3. A **deployment is still in progress** after a password change — wait for SUCCESS.
4. **The email address is different** — for example a typo, or another alias of the same mailbox.
   The account is the exact `ADMIN_EMAIL` value.
5. The site is down or degraded — check `/api/health` ([§2.3](#23-if-the-site-does-not-load)).

### 9.8 Full sign-out and sign-in reset

1. Click **"Sign out"** if you can reach it.
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
| Forgotten **member** password | — | — | ✓ |
| Locked out | Wait 15 minutes | — | ✓ Clear early |
| Member disabled | ✓ **"Enable"** (another admin) | — | — |
| All admins locked out | — | ✓ Reset the owner password | ✓ |
| Stale session | ✓ Reload / reset (§9.4, §9.8) | — | — |
| Site down / database down | — | Restart the latest SUCCESS deployment once | ✓ |
| Wrong `ADMIN_EMAIL` or stray organizations | — | — | ✓ |

---

## 10. Integrations

Statuses use the labels from [the Project Completion Standard](PROJECT_COMPLETION_STANDARD.md):
LIVE + VERIFIED, CONFIGURATION REQUIRED, AVAILABLE BUT NOT CERTIFIED, DEGRADED, NOT IMPLEMENTED,
DEFERRED, DEPRECATED.

### 10.1 Integration status summary (2026-09-30)

| Integration | Exists in the product | Status |
|---|---|---|
| **Google — Gmail and Google Calendar connection** | Yes (**Registries**) | **DEGRADED** — Google refused the permission refresh on 2026-09-30. Re-authorize ([§5.6](#56-re-authorize-google)). The flows have never been live-certified. |
| **Gmail — outbound email** | Yes (server + approvals) | **CONFIGURATION REQUIRED** — certification gate plus the missing compose screen ([§6.1](#61-read-this-first--current-status)) |
| **Gmail — reply capture** | Yes (scheduler) | **AVAILABLE BUT NOT CERTIFIED** — never tested live ([§6.6](#66-procedure-c--capture-the-reply)) |
| **Google Calendar — meeting sync** | Yes | **AVAILABLE BUT NOT CERTIFIED** |
| **Stripe** | Yes (**Registries**) | **CONFIGURATION REQUIRED** — `STRIPE_API_KEY` / `STRIPE_WEBHOOK_SECRET` are not set (O-02) |
| **Outbound webhooks** | Yes (**Registries** → **"Webhooks"**) | **AVAILABLE BUT NOT CERTIFIED** — admin-configured |
| **MCP server (governed AI tools)** | Yes (**MCP Console**) | **AVAILABLE BUT NOT CERTIFIED** |
| **Email notifications** (alerts and digest) | Yes (**Action Center**) | **CONFIGURATION REQUIRED** — `EMERGENT_EMAIL_KEY` is not set |
| **AI generation** | Yes (Client 360 **"Evidence-backed AI"**) | **CONFIGURATION REQUIRED** — `EMERGENT_LLM_KEY` is not set (O-11) |
| **Security-gate scanners** | Yes (**Operations** → **"Security gate"**) | **CONFIGURATION REQUIRED** (O-13, O-14) |
| **Scheduler (GitHub Actions)** | Yes | **LIVE** since 2026-09-30 16:11 UTC ([§11](#11-scheduler--automations)); its first full day is still to be observed |
| **"Continue with Google" sign-in** | Button present | UNVERIFIED — OWNER/ENGINEERING INPUT REQUIRED. Do not use ([§3.1](#31-supported-sign-in-methods)). |
| **Recovery intake** (call logs, web enquiries, external CRM events) | Server API only, no screen | **AVAILABLE BUT NOT CERTIFIED** — for engineering integrations |
| **n8n, Slack, ClickUp** | No working CRM integration. Catalogue entries may appear in **Registries** as contracts only. | **NOT IMPLEMENTED** (O-08, O-09) |
| **SMS, Calling / telephony, Calendar module** | Placeholder modules only | **NOT IMPLEMENTED** (O-06) |

The **Jev QC gate** (an n8n workflow) is an engineering quality gate that AI agents use before
claiming work is complete. It is **not** a CRM feature, and it never touches CRM data.

### 10.2 Google — Gmail and Google Calendar

- **Purpose:** matched email and meetings on Client 360; reply capture; sending approved email.
- **Connect / verify / disconnect / troubleshoot:** [Chapter 5](#5-google--gmail-setup).
- **Required owner action:** Google Cloud consent screen and test users; re-authorize when needed.
- **Secret names:** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`. Optional: `GOOGLE_REDIRECT_URI`,
  `PUBLIC_BACKEND_URL`.
  - Both are unset today, so the redirect address comes from the Railway domain.
  - Set both **before** adding a custom domain. Otherwise Google connect breaks silently.
- **Stored permission:** encrypted at rest with `INTEGRATION_ENC_KEY`. It is never shown in any
  screen or API.
- **Known limitations:**
  - Sync reads the 25 newest messages and events per run.
  - Reply capture looks back 7 days.
  - One mailbox per organization.

### 10.3 Stripe

- **Purpose:** read customers, invoices and subscriptions and match them to contacts. Stripe
  **Billing & subscriptions** items appear on Client 360 → **Activity**.
- **Status:** CONFIGURATION REQUIRED. **"Connect"** on the Stripe card currently answers
  **"Stripe is not configured (STRIPE_API_KEY)."**
- **Required owner action** (governing document O-02):
  1. Decide whether Stripe is in scope.
  2. If it is, create a **test-mode** restricted key, and a webhook endpoint at
     `https://clientverse-crm-production-production.up.railway.app/api/integrations/stripe/webhook`.
  3. Have `STRIPE_API_KEY` and `STRIPE_WEBHOOK_SECRET` set in Railway.
- **Connect:** **Registries** → Stripe → **"Connect"**. It uses the Railway key. The screen has no
  field for a per-organization key.
- **Verify:** the card shows **"Connected"** and **"Account: …"**. **"Sync"** shows
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
  1. **"New Endpoint"**.
  2. **"Name"**, **"URL"** (HTTPS), and the **"Subscribed events"** chips.
  3. **"Create"**.
- **Verify:**
  - **"Send test"** → **"Test event → {status}"**.
  - **"Delivery Log"** lists every attempt.
  - Failed deliveries retry 3 times, then go to the dead-letter list, marked **"· DLQ"**.
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

### 10.6 Email notifications and AI (not active)

- **Email notifications** need `EMERGENT_EMAIL_KEY` (and optionally `EMAIL_FROM_NAME`). Until then,
  **Action Center** shows **"Email delivery is not configured."** In-app alerts still work. This
  is **not** Gmail: alert emails would come from a separate delivery service.
- **AI generation** needs `EMERGENT_LLM_KEY`. Until then, **"Generate with evidence"** fails with
  **"AI generation failed. Please retry."**

---

## 11. Scheduler / Automations

### 11.1 What runs, and where

- **What:** the GitHub Actions workflow **"Scheduled jobs"** (`.github/workflows/scheduled-jobs.yml`,
  job **"Call scheduled endpoints"**).
- **Where it runs:** on GitHub's servers. Nothing runs on your computer.
- **What it does:** calls production's `/api/cron/…` endpoints over HTTPS, with a shared secret.
  Then it reads production's own run record (the "ledger") back, to prove each call was recorded.
- **Times are UTC.** GitHub can start scheduled runs a few minutes late under load.

### 11.2 Scheduled jobs

| Endpoint | What it does | Cadence (UTC cron) |
|---|---|---|
| `/api/cron/commitment-risk` | Flags commitments due within 48 hours as at-risk and past-due ones as breached | `*/15 * * * *` — every 15 minutes |
| `/api/cron/work-queue` | Runs the durable work queue: recovers abandoned jobs, processes due items | `*/5 * * * *` — every 5 minutes |
| `/api/cron/recovery-runner` | Runs approved recovery steps. Outbound steps are drafted for approval, never sent without it. | `*/5 * * * *` |
| `/api/cron/integration-sync` | Syncs Gmail, Google Calendar and Stripe for connected organizations | `0,30 * * * *` — :00 and :30 |
| `/api/cron/next-best-actions` | Recomputes ranked next best actions | `0,30 * * * *` |
| `/api/cron/inbound-email` | Checks connected Gmail inboxes for replies and bounces | `10,40 * * * *` — :10 and :40 |
| `/api/cron/reconcile-unknown` | Asks Gmail about messages whose outcome is unknown. **Never re-sends.** | `10,40 * * * *` |
| `/api/cron/daily-digest` | Sends each user's daily digest at their chosen hour (email needs `EMERGENT_EMAIL_KEY`) | `5 * * * *` — hourly at :05 |
| `/api/cron/second-chance` | Second Chance detection of stalled and lost revenue | `5 * * * *` |
| `/api/cron/detect-recovery` | Runs every other recovery detector (for example missed calls) | `5 * * * *` |
| `/api/cron/recovery-strategies` | Composes a recovery strategy for each open candidate | `5 * * * *` |
| `/api/cron/approval-expiry` | Expires approval requests past their deadline | `5 * * * *` |

Each call is accepted at once and does its work in the background. A repeated delivery of the same
call is recognized and ignored.

### 11.3 Required configuration (names only)

| Where | Name | Holds |
|---|---|---|
| GitHub → repository **Settings** → **Secrets and variables** → **Actions** | `CLIENTVERSE_PRODUCTION_URL` | The production address in [§2.1](#21-addresses) |
| Same | `WEBHOOK_CRON_SECRET` | The shared scheduler secret |
| Railway → service → **Variables** | `WEBHOOK_CRON_SECRET` | **The same value** as the GitHub secret |

### 11.4 Verify that automation is healthy

**A. GitHub (owner, no sign-in to the CRM needed)**

1. Open https://github.com/ebyron357/Clientverse-crm/actions/workflows/scheduled-jobs.yml.
2. The newest runs have green ticks, and a new run appears about every 5 minutes.
3. Open a run → **Summary**. The table **endpoint | HTTP | accepted | evidence id** shows `200`
   and `true` for every row. The last line reads
   **"Production recorded N ledger reference(s) for this run"**.

**B. Production (owner, signed in as admin in the same browser)**

1. Open https://clientverse-crm-production-production.up.railway.app/api/cron/health. It shows the
   last 120 minutes.
2. **Healthy:**
   - `"receiving_scheduled_traffic": true`
   - `"last_authenticated_call_at"` within the last ~15 minutes
   - `"by_status"` mostly `succeeded`
3. `"last_rejected_call_at"` — the last call refused because of a wrong secret. It should be older
   than the last authenticated call.
4. `"last_failed_job"` / `"last_failed_error"` — the last job that ran but raised an error.
5. More detail: `/api/cron/runs` lists individual runs.

**C. Railway (owner)**

Railway → service → **Deployments** → the active deployment → **View logs**. Look for lines like
`"POST /api/cron/work-queue HTTP/1.1" 200 OK`.

### 11.5 What the results mean

| You see | Meaning | Action |
|---|---|---|
| **Green run** | Production was called, answered `200` for every job, **and** recorded the run in its ledger | None |
| **Red run** | Something in the chain failed. Open the run to see which step. | See the rows below |
| **200** | Production accepted the call. The job runs in the background; its own result is in `/api/cron/runs`. | None |
| **401 Unauthorized** | The shared secret is missing or different at one end (GitHub vs Railway). Production records the refusal. | Make both `WEBHOOK_CRON_SECRET` values identical ([§11.8](#118-rotate-or-fix-the-scheduler-secret)) |
| **403** on `/api/cron/health` in your browser | You are signed in as a member, not an admin | Sign in as an admin |
| **"Scheduler not configured"** — *Missing repository secret(s)* | `CLIENTVERSE_PRODUCTION_URL` or `WEBHOOK_CRON_SECRET` is not set in GitHub | Owner adds the secret(s) (§11.3) |
| **"No request reached production"** / HTTP `000` | Production did not answer | Check `/api/health` and Railway ([§2.3](#23-if-the-site-does-not-load)) |
| **404** from the cron endpoints | `CLIENTVERSE_PRODUCTION_URL` points to the wrong address | Fix the GitHub secret |
| **"Run not recorded"** / **"Ledger unreadable"** | Calls were accepted, but the ledger check failed | Escalate |
| Every job fails in 2–4 seconds with no log | A GitHub account-level Actions problem (billing, spending limit, Actions disabled) — as from 2026-09-27 22:35 until 2026-09-30 | Owner: GitHub → **Settings** → **Billing and plans**; repository **Settings** → **Actions** → **General** |
| Runs stop appearing at all | GitHub disables scheduled workflows after 60 days without repository activity | **Actions** → **Scheduled jobs** → **"Enable workflow"** |
| `"receiving_scheduled_traffic": false` while GitHub shows green | Impossible by design — the workflow verifies the ledger — so treat it as serious | Escalate |

### 11.6 Current state (verified live 2026-09-30)

- **The scheduler is running.** Scheduled-jobs runs **#3551** (attempt 3, 16:11 UTC) through
  **#3555** (16:29 UTC) all **succeeded**.
  - Railway's log shows `200 OK` for all twelve endpoints between 16:08 and 16:29 UTC, plus
    `GET /api/cron/runs` ledger reads.
  - This is the first time production has received scheduled traffic. Before 2026-09-30, earlier
    records correctly said it never had.
- **Before that:**
  - Runs **#3544–#3550** (15:39–15:58 UTC) **failed**. Railway shows `401 Unauthorized` on the cron
    calls at 15:54 and 15:58 UTC — a secret mismatch that was then corrected.
  - From 2026-09-27 22:35 UTC, GitHub Actions ran nothing at all.
- **Still to observe:** a full day of green runs, including the hourly `:05` jobs and a daily
  digest. Recheck with §11.4.

### 11.7 Run the jobs by hand

GitHub → **Actions** → **Scheduled jobs** → **"Run workflow"** (on `main`).

- Leave **jobs** empty to run all twelve.
- Or enter a comma-separated list, for example `inbound-email,reconcile-unknown`.

This is safe: every job is idempotent.

### 11.8 Rotate or fix the scheduler secret

1. Generate a new long random value in your password manager.
2. **GitHub:** repository **Settings** → **Secrets and variables** → **Actions** →
   `WEBHOOK_CRON_SECRET` → **Update**.
3. **Railway:** service → **Variables** → `WEBHOOK_CRON_SECRET` → the same value → save and deploy.
4. Until both match and the deploy is SUCCESS, runs fail with 401. That is expected for a few
   minutes.
5. **Check:** the next run is green (§11.4).

**Owner can do:** secrets in GitHub and Railway; restoring GitHub Actions billing; re-enabling the
workflow; manual runs.

**Needs engineering:** changing job cadence, adding jobs, or any red run that is not explained in
§11.5.

---

## 12. Troubleshooting Matrix

| Problem | Likely cause | Exact owner action | Escalate when |
|---|---|---|---|
| **Cannot log in** (any reason) | Wrong password, lockout, wrong address, stale session, site down | 1. Check `/api/health` (§2.3). 2. Check the email is exactly the `ADMIN_EMAIL` value. 3. See the rows below. | After §9.1–§9.8 fail, or the site is down |
| **Wrong password** — "Invalid email or password" | Typo, Caps Lock, or `ADMIN_PASSWORD` changed | Copy the password from Railway `ADMIN_PASSWORD` or your password manager. Stop after 3 tries. (§9.1) | Never needed for the owner. Member passwords always need engineering. |
| **Account locked** — the right password is still refused | 5 failures → 15-minute lock | Wait 15 minutes, then try **once** (§9.3) | You need access sooner |
| **Google sign-in fails** ("Continue with Google") | Unsupported third-party sign-in | Use email + password (§3.1, §9.6) | Someone ended up in a stray organization |
| **Google connection fails** — "Google authorization failed" | Consent cancelled or refused, redirect URI mismatch, not a test user | Full reset (§5.7), then connect within 10 minutes and tick every box (§5.5) | It fails twice after a full reset |
| **Google reconnect loop** — stuck "Connecting…" or back to "Error" | Abandoned consent; secret or redirect mismatch | Disconnect **both** cards, remove app access in the Google account, connect again (§5.7, §5.9) | `token_exchange_failed` or `redirect_uri_mismatch` persists |
| **Google token refresh 400** — "Needs auth", `token_refresh_failed:400` | Permission revoked or expired; consent screen in Testing (7-day expiry); client secret rotated | **"Re-authorize"** (§5.6) | It recurs within a week (Testing mode), or fails right after reconnecting (secret mismatch) |
| **Integration says disconnected** — "Not connected" | Never connected, or someone disconnected it | Admin → **"Connect"** (§5.5). Check **Automation & Audit** for `integration.disconnected` to see who. | Connect fails |
| **Gmail send fails** — message "blocked" | Not connected, no consent, certification gate | Read the reason on the message. Fix the connection (§5.6). Certification needs engineering (§6.1). | The reason mentions certification, consent or a provider |
| **Gmail send fails** — message "failed", HTTP 403 | Send permission not actually granted | Full reset, and tick **send** on consent (§5.7, §5.8) | It still fails after that |
| **Gmail send** — "outcome unknown" | Google did not confirm | **Do not re-send.** Wait for the :10 / :40 reconcile. | Still unknown after 1 hour |
| **Inbound reply missing** | Sweep not run yet; Gmail not Connected; reply ambiguous (parked) | Wait up to 35 minutes, or **"Run workflow"** with `inbound-email` (§11.7). Check the Gmail card is "Connected". | Missing after 35 minutes with a healthy scheduler — engineering checks the unmatched queue (Appendix C) |
| **Scheduled job failed** — red run | See §11.5 | Open the run and match its message in §11.5 | Unexplained, or 3 red runs in a row |
| **Scheduler not configured** — red run "Missing repository secret(s)" | GitHub secret missing | Add `CLIENTVERSE_PRODUCTION_URL` / `WEBHOOK_CRON_SECRET` (§11.3) | — |
| **Scheduler secret mismatch** — cron calls return 401 | GitHub and Railway `WEBHOOK_CRON_SECRET` differ | Set both to the same value (§11.8) | Still 401 after both are set and the deploy is SUCCESS |
| **401** anywhere | You are not signed in, or your session expired or was revoked | Reload; sign in again (§9.4). For cron calls, see the secret-mismatch row. | It recurs right after signing in |
| **403** — "You do not have permission to perform this action" | The action is admin-only | Ask an admin, or sign in as one (§8.1) | An admin gets it |
| **403** — "Your access to this workspace has been disabled" | Membership disabled | An admin clicks **"Enable"** (§8.8) | No admin is available |
| **404** / "not found" | Wrong address, a record from another organization, or an invalid invite or portal link | Check the address. Open records from lists, not old links. Ask for a fresh invite. | A record you created is missing |
| **500** / "Something went wrong." | A server error | Retry once. Note the time and action. Check `/api/health`. | It repeats — send the evidence (§15.2) |
| **502** "AI generation failed. Please retry." | AI key not configured | None — AI is not active (§10.6) | You want AI enabled (owner decision O-11) |
| **503** on `/api/health` — "database":"down" | The database is unreachable | Check MongoDB Atlas status and network access | Always |
| **Blank page or dashboard** | A display error (**"This view needs a refresh"**), expired session, or loading error | Click **"Reload ClientVerse"** or reload. Then the full reset (§9.8). | A blank page persists after §9.8 |
| **Data not appearing** | Filtered view, a different organization, over 200 records, not synced yet | Clear the search and filters. Check you are in your organization (Settings). For email and meetings, connect and **"Sync"**. | Records you created are gone |
| **Save or update does not persist** | Silent failure (status menus), expired session, permission | Refresh the page to see the true state. Reload and sign in. Retry. | It reverts twice |
| **CRM unavailable** — site will not load | Railway down, a failed deploy, the database | Follow §2.3 | Railway shows FAILED or CRASHED, or the database is down |
| **Railway deployment failed** — FAILED or CRASHED | Build or boot error in a new commit | Screenshot the deployment and logs. Restart the last SUCCESS deployment once (§2.3). | Always — engineering decides on rollback |
| **Invitation link does not work** | Expired (7 days), revoked, already used, or replaced by **"Resend"** | Create a new invitation (§8.2) | The new link also fails |
| **Portal link lost or leaked** | It is shown only once; there is no revoke button | Create a new link and share it privately | A leaked link must be revoked |

---

## 13. Security and Owner Safety

### 13.1 Never share these

- **Passwords** — yours, a member's, or the value of `ADMIN_PASSWORD`.
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
  - webhook signing secrets
  - the Jev QC webhook address

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
| **In the CRM:** notification preferences, team invites, roles, disable/enable, Google connect/re-authorize/disconnect, webhook endpoints you own | **Railway:** any variable other than `ADMIN_PASSWORD` and `WEBHOOK_CRON_SECRET` |
| **Railway:** `ADMIN_PASSWORD` (§9.2); `WEBHOOK_CRON_SECRET` together with GitHub (§11.8); **Restart** of the latest SUCCESS deployment | **Railway:** Rollback / Redeploy of an older commit; adding a custom domain (set `PUBLIC_BACKEND_URL` and `GOOGLE_REDIRECT_URI` first) |
| **GitHub:** Actions secrets; enabling the workflow; manual runs | **Never:** `ADMIN_EMAIL`, `MONGO_URL`, `DB_NAME`, `INTEGRATION_ENC_KEY` (changing it makes every stored integration permission unreadable), `JWT_SECRET` (changing it signs everyone out), `APP_ENV`, `SEED_DEMO_DATA` (must stay false) |
| **Google Cloud:** consent-screen test users | **Google Cloud:** redirect URIs, client secret rotation (Railway must be updated at the same moment) |
| — | **MongoDB Atlas:** network access, users, backups |

### 13.4 Rotate credentials safely

1. **Plan it.** Know which two places must change together: Railway + GitHub for the cron secret;
   Google Cloud + Railway for the Google client secret.
2. Generate the new value in your password manager.
3. Change the **source** first (Google Cloud / Stripe), then **Railway**, then **GitHub** if it
   applies. Deploy.
4. Verify:
   - `/api/health` is ok
   - you can sign in
   - the scheduler is green (§11.4)
   - Google is still **"Connected"**
5. Record *that* you rotated, and when — **never the value** — in the governing document's
   owner-action register.

**Open rotations (governing document O-04, O-05):**

- Rotate `ADMIN_PASSWORD` if it has ever left the Railway dashboard.
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
- **Export:** there is no export button (§7.17). Ask engineering for a CSV export per record type.

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
| Error messages, page headings, status badges, the Registries cards, GitHub run summaries, Railway deployment lists and log lines | Client names, email addresses and phone numbers (when sharing outside the company); the **"Account:"** line if the mailbox is personal | Railway **Variables** with values visible; the webhook **"Verify"** dialog; the **"Invitation ready"** dialog; browser developer tools showing cookies, headers or storage; Google Cloud credential pages |

---

## 14. Production Verification Checklist

Mark each item **PASS**, **FAIL**, **BLOCKED** or **NOT TESTED**. Definitions are in
[§6.2](#62-result-definitions). Write the date, and attach evidence for every PASS.

The *Known on 2026-09-30* column is what the engineering review could observe without opening the
website. The owner's result is the authority.

| # | Check | How | Expected | Known on 2026-09-30 | Result |
|---|---|---|---|---|---|
| 1 | Production URL loads | Open the production URL | Sign-in page, **"Welcome back"** | Deployment SUCCESS; health 200 in the Railway log | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 2 | Service healthy | `/api/health` | `status ok`, `database up`, `git_sha` = Railway commit | Health 200 at boot and at 16:16 UTC | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 3 | Login works | §3.2 | **"Good to see you"** | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 4 | Logout works | **"Sign out"**, then open `/dashboard` | Returns to the sign-in page | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 5 | Admin role verified | Settings → **"Access level"**; **"Team & Access"** visible | **"Workspace admin"** | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 6 | Member role verified | Invite a test member (§8.2); sign in as them in a private window | **"Team member"**; no **"Team & Access"**; the Registries cards show **"Admin manages"** | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 7 | Core CRM records load | Contacts, Companies, Pipeline, Client 360 | Lists or honest empty states; no "…unavailable" | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 8 | Create record works | Create company `ZZ Test Co` | **"Company created"**; it appears after a reload | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 9 | Edit record works | Move a test deal **Lead → Qualified**; reload | **"Moved to Qualified"**; it persists after the reload. (Field editing does not exist in the screens — record that as a known limitation, not a FAIL.) | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 10 | Archive / restore | — | **Not supported in the screens** (§7.18) | Known limitation | ☐ NOT TESTED (not applicable) |
| 11 | Google connected | Registries → Gmail | **"Connected"**, no red line | Expected **"Needs auth"** (refresh 400 at 16:08 UTC) | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 12 | gmail.send verified | §5.8 checks 2 and 3 | Google lists send permission; EMAIL not listed as unauthorised | Blocked by 11 and by certification | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 13 | Outbound email works | §6.4 | **"sent"**; in Gmail Sent; received | BLOCKED (§6.1) | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 14 | Duplicate-send protection | §6.5 | Refused; one copy only | BLOCKED (§6.1) | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 15 | Inbound reply works | §6.6 | INBOUND **"received"** on the same thread | BLOCKED (§6.1) | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 16 | Scheduler healthy | §11.4 A and B | Green runs; `receiving_scheduled_traffic: true` | Runs #3551–#3555 green; all 12 endpoints 200 | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 17 | Railway deployment healthy | Railway → Deployments | Newest **SUCCESS**, no crash loop | `8f23f63` SUCCESS 15:52 UTC | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 18 | Integrations show correct status | Settings → **"Connected providers"** vs Registries | Same statuses in both; Stripe **"Not connected"** | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 19 | No visible critical errors | Visit every active sidebar item | No **"This view needs a refresh"**, no "…unavailable" | Not observed | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |
| 20 | Clean up | The test company and test deal have no delete button. Note their names for engineering to archive. | Recorded | — | ☐ PASS ☐ FAIL ☐ BLOCKED ☐ NOT TESTED |

**Sign-off:** date ____________ · verified by ____________ · evidence location ____________

---

## 15. Support / Escalation

### 15.1 When to escalate

| Situation | Who |
|---|---|
| Anything this manual lets the owner fix (sign-in, Google reconnect, invitations, scheduler secrets) | **Owner** — follow the chapter |
| Site down, deployment FAILED or CRASHED, database down, any repeated `500` | **Engineering — urgent** |
| Outbound email certification, record edits or deletes, member password reset, export | **Engineering — planned** |
| Leaked secret or suspicious access | **Rotate now**, then report **privately** (§13.6) |
| Google Cloud, Stripe account, GitHub billing, MongoDB Atlas account decisions | **Owner** (engineering can advise) |

### 15.2 Evidence to collect before you escalate

- [ ] **Time** of the problem, with your timezone (for example `2026-09-30 16:08 UTC`)
- [ ] **Page or module** — the sidebar item and tab, and the address bar with any `?token=` part removed
- [ ] **Action attempted** — the exact button you clicked, and what you typed (never passwords)
- [ ] **Exact error text**, copied word for word, or a screenshot of it
- [ ] **Screenshot** of the whole screen, following §13.7
- [ ] **Affected account** — the email address of the user involved, and whether admin or member
- [ ] **Browser and device** — for example "Chrome 129 on Windows 11"
- [ ] **Repeatability** — every time / sometimes / once; and does it happen in a private window?
- [ ] **`/api/health` result** at the time (copy the text)
- [ ] **GitHub Actions run number** if it concerns automation (for example "Scheduled jobs #3550")
- [ ] **Railway deployment time and status** if the site is affected (for example "SUCCESS 15:52 UTC")
- [ ] For Google: the Gmail card's status and red error line; for email, the message status and
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
GitHub Actions run # (if automation):
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
- invitation, portal or webhook links and secrets

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
| How do I log in? | Email + password → **"Sign in to ClientVerse"**. Not Google. | [§3.2](#32-sign-in-with-email-and-password) |
| What account type am I using? | The **admin** account whose email is Railway `ADMIN_EMAIL`, in organization "ClientVerse HQ" | [§3.3](#33-which-account-the-owner-uses) |
| What do I see after login? | Command Center — **"Good to see you"**, four summary cards, next actions | [§4.2](#42-what-you-see-after-sign-in-command-center) |
| Where are Settings? | Sidebar → Platform → **"Settings"** | [§1.3](#13-find-settings-and-integrations) |
| Where are Integrations? | Sidebar → Platform → **"Registries"** → **"Integrations"** tab (or Settings → **"View integrations"**) | [§5.3](#53-where-the-google-controls-are) |
| How do I connect Google? | Registries → Gmail → **"Connect"** → consent (tick all) → **"Google connected"** | [§5.5](#55-connect-google-first-time) |
| How do I reconnect Google? | **"Re-authorize"** on "Needs auth"; otherwise disconnect **both** cards, then Connect | [§5.6](#56-re-authorize-google), [§5.7](#57-disconnect-safely-and-when-it-is-required) |
| How do I verify gmail.send? | Google Account → third-party connections shows send permission, and Operations → Recovery strategies does not list EMAIL | [§5.8](#58-verify-that-gmailsend-was-actually-granted) |
| How do I send a real email? | Engineer-assisted today (no compose screen), after re-authorization and certification | [§6.1](#61-read-this-first--current-status), [§6.4](#64-procedure-a--send-one-real-outbound-email), [App. C](#appendix-c-engineer-assisted-email-verification) |
| How do I verify the reply came back? | Operations → Conversations → the same thread shows INBOUND **"received"** within ~35 minutes | [§6.6](#66-procedure-c--capture-the-reply) |
| How do I manage users? | Team & Access → **"Invite member"** (share the link yourself), role menu, **"Disable"** | [§8](#8-users-roles-and-administration) |
| How do I recover access? | Owner: change `ADMIN_PASSWORD` in Railway; locked: wait 15 minutes; members: engineering | [§9](#9-account-recovery) |
| How do I know scheduled automations are healthy? | GitHub Scheduled jobs green, and `/api/cron/health` shows `receiving_scheduled_traffic: true` | [§11.4](#114-verify-that-automation-is-healthy) |
| What does 401 mean? | Not signed in, or the session expired (cron: secret mismatch) | [§12](#12-troubleshooting-matrix), [§11.5](#115-what-the-results-mean) |
| What does 500 mean? | A server error — retry once, then escalate with evidence | [§12](#12-troubleshooting-matrix) |
| What do I do when Railway is down? | Check `/api/health` and Railway Deployments; restart the last SUCCESS once; escalate | [§2.3](#23-if-the-site-does-not-load) |
| What evidence do I collect before escalation? | Time, page, action, exact error, screenshot, account, browser, repeatability, run #, deployment | [§15.2](#152-evidence-to-collect-before-you-escalate) |

---

## Appendix B. System state on 2026-09-30

| Fact | Evidence |
|---|---|
| Production serves `main@8f23f63` (application code identical to `c9f5a6e`) | Railway deployment list: SUCCESS 2026-09-30 15:52 UTC; `git diff c9f5a6e 8f23f63` is empty for `backend/`, `frontend/`, `Dockerfile`, `railway.json` and `.github/` |
| Service boots with the Gmail adapter registered | Deploy log: `Registered outbound channel provider: gmail` → `Application startup complete` → `GET /api/health 200` |
| Only one public domain; no custom domain | Railway domain list for `production` |
| Scheduler reaching production | Scheduled jobs #3551–#3555 success; Railway log `200 OK` for all 12 cron endpoints, 16:08–16:29 UTC |
| Scheduler secret mismatch before 16:08 UTC | Runs #3544–#3550 failure; Railway log `401 Unauthorized` at 15:54 and 15:58 UTC |
| Google permission refresh refused | Railway log 16:08:28 and 16:08:30 UTC: `POST https://oauth2.googleapis.com/token "HTTP/1.1 400 Bad Request"` |
| Outbound email is held by a certification gate | Code: `backend/recovery_strategy.py` (`authorized_channels`, `CONFIGURED_INTEGRATION_STATUSES`); the Gmail catalogue record is seeded `REQUIRES_CONFIGURATION` in `backend/server.py`, and nothing updates it |
| No compose, send or consent screen | Code: `frontend/src/pages/Operations.jsx` calls only conversation handoff and close |
| Invitations are not emailed | Code: `create_invitation` in `backend/server.py` returns the link only |
| Last full live production smoke | 2026-09-01 on `ca30587` (`docs/evidence/production-smoke-20260901.json`). No live smoke since. |
| Email notifications and AI not configured | `EMERGENT_EMAIL_KEY` and `EMERGENT_LLM_KEY` absent from the recorded Railway variable list ([OWNER_HANDOFF.md](OWNER_HANDOFF.md) §3) |

---

## Appendix C. Engineer-assisted email verification

**For an engineer working with the owner.** Every value in angle brackets is a placeholder.
Never paste a real token into a ticket or log.

**Step 0 — prerequisites the engineer confirms:**

1. The Gmail connection is **"Connected"** after re-authorization (§5.6).
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

# 10. Contact timeline entry (activity outcome "reply_received")
cv "$BASE/api/contacts/<contact id>/timeline"

# 11. End the session: revoke the token on the server, then forget it locally
cv -X POST "$BASE/api/auth/logout"; unset TOKEN
```

Record the results against [§14](#14-production-verification-checklist) rows 12–15, and in the
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
| `WEBHOOK_CRON_SECRET` | Railway **and** GitHub Actions | Set in both; matching since 2026-09-30 16:08 UTC | Scheduler authentication |
| `CLIENTVERSE_PRODUCTION_URL` | GitHub Actions | Set (runs succeed) | Scheduler target |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Railway | Set | Google connection |
| `GOOGLE_REDIRECT_URI`, `PUBLIC_BACKEND_URL` | Railway | Not set (derived from the Railway domain) | Set before any custom domain |
| `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET` | Railway | Not set | Stripe (O-02) |
| `EMERGENT_EMAIL_KEY`, `EMAIL_FROM_NAME` | Railway | Not set | Email notifications |
| `EMERGENT_LLM_KEY` | Railway | Not set | AI generation (O-11) |
| `SEED_DEMO_DATA` | Railway | Set (must stay false) | Keeps fictional demo data out of production |
| `LOGIN_LOCKOUT_THRESHOLD`, `LOGIN_LOCKOUT_MINUTES` | Railway | Not set (defaults 5 and 15) | Lockout policy |
| `SECURITY_GATE_*_URL` (three scanners) | Railway | Not set | Security gate (O-14) |
| `DEMO_MEMBER_EMAIL`, `DEMO_MEMBER_PASSWORD`, `ALLOW_INSECURE_JWT` | — | **Must never be set in production** | Test only |
| Google Cloud project name | Google Cloud | UNVERIFIED — OWNER/ENGINEERING INPUT REQUIRED | Owner to record here |

Railway variable presence was last read by name on 2026-09-21 ([OWNER_HANDOFF.md](OWNER_HANDOFF.md)
§3). The scheduler rows are updated from the 2026-09-30 run evidence.

---

## Appendix E. Related documents

**Governing and engineering documents.** These are kept for developers; this manual does not
replace them.

- [Canonical governing document](CLIENTVERSE_CRM_CANONICAL_GOVERNING_DOCUMENT.md) — scope,
  capability status, owner-action register (O-01…O-16)
- [Project Completion Standard](PROJECT_COMPLETION_STANDARD.md) — the closeout baseline this manual
  serves
- [Railway runbook](RAILWAY_RUNBOOK.md) and [Production configuration](PRODUCTION.md) — deployment
  mechanics
- [Owner handoff (2026-09-21, engineering record)](OWNER_HANDOFF.md) and
  [Activation report](ACTIVATION_REPORT.md) — history and evidence
- [Google provider certification](GOOGLE_PROVIDER_CERTIFICATION.md),
  [Stripe provider certification](STRIPE_PROVIDER_CERTIFICATION.md)
- [Security policy](../SECURITY.md), [README](../README.md)

**Superseded for owner use.** From 2026-09-30, the owner-facing parts of these documents are
superseded by this manual. Each carries a banner saying so:

- `docs/OWNER_HANDOFF.md` — §2, §5, §8, §10
- `docs/ACTIVATION_REPORT.md` — "Administrator Access", "Owner Actions Required"
- `docs/RAILWAY_RUNBOOK.md` — §6 (scheduler) and the password text in §7
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
| 1.0 | 2026-09-30 | First complete owner/admin manual ([ebyron357/Clientverse-crm#33](https://github.com/ebyron357/Clientverse-crm/issues/33)). Verified against `main@8f23f63` code, Railway deployment records and logs, and GitHub Actions run records of 2026-09-30. |

**Keeping it true**

- Update this manual **in the same change** as any code change that alters a screen label, a
  route, a sign-in rule, a Google scope, a scheduler job or an owner procedure.
- When a production fact changes (for example certification granted, or the Google permission
  restored), update [Appendix B](#appendix-b-system-state-on-2026-09-30) and the governing
  document together.
- Never add a secret value. Names only.
