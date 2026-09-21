# ClientVerse — Owner Handoff

**Prepared:** 2026-09-21
**Branch this describes:** `claude/trusting-brahmagupta-lj26xf`
**Currently deployed:** `main@730b1b3` (this branch is **not** deployed — see §1)

This document is what the owner needs to take the system over. It states what is
running, what is not, what only the owner can do, and how to verify each claim rather
than take it on trust.

It contains **no** passwords, API keys, OAuth client secrets, encryption keys, webhook
signing secrets or database URIs. Where a secret is needed, the delivery method is
named instead of the secret.

---

## 1. Release state — read this first

| | |
|---|---|
| Production URL | `https://clientverse-crm-production-production.up.railway.app` |
| Login URL | `https://clientverse-crm-production-production.up.railway.app/login` |
| Deployed git SHA | `730b1b3b30e5b8f9d88bffc0dc3161c1a8046296` (`main`) |
| Railway deployment ID | `4b5f7f84-fcca-43ed-8777-415082747e6e` |
| Deployment status | SUCCESS |
| Deployment timestamp | 2026-09-16T23:33:41Z |
| Healthcheck path | `/api/health` |

**The work described in this handoff is not in production.** It is on
`claude/trusting-brahmagupta-lj26xf`, verified by CI against a real MongoDB, and
deploys when that branch is merged to `main` (Railway auto-deploys `main`).

**No capability in this handoff is marked LIVE VERIFIED**, because this session could
not reach the production host at all. The egress policy for the session refused every
connection to `clientverse-crm-production-production.up.railway.app` with HTTP 403 at
the CONNECT stage. That is a policy denial, not an outage, and it is recorded in the
proxy's own failure log. A previous session hit the same block (see the commit message
on `3150530`: "the session egress policy blocks railway.app"). Production behaviour
therefore has to be verified by the owner, from a network that can reach it. §8 is the
script for doing that.

---

## 2. Application access

| | |
|---|---|
| Tenant / workspace | The tenant seeded from `ADMIN_EMAIL` at first boot |
| Initial admin email | The value of the `ADMIN_EMAIL` Railway variable |
| Admin role | `admin` |
| Login tested | **In production: NO** (host unreachable from this session). Against a local instance of this exact code: YES |
| Logout tested | Same — local YES, production NO |
| Session revocation tested | Same — local YES, production NO. A token replayed after logout returns 401; asserted by `scripts/crm_release_smoke.mjs` step 49 and by `backend/tests/test_session_revocation.py` |

### Password handoff method

**No password is written here, into the repository, or into any documentation.**

The admin password is whatever is currently in the Railway variable `ADMIN_PASSWORD`.
`seed()` re-reads it on every boot and re-syncs the password hash, so rotating it is:

1. Set a new `ADMIN_PASSWORD` value in Railway (Variables → the service → edit).
   Railway triggers a redeploy on the change.
2. Wait for the deployment to reach SUCCESS.
3. Sign in with the new password.

Read the current value only from the Railway dashboard, which is the approved secret
store for this deployment. **Rotate it now if it has ever been shared over chat,
email, or a ticket**, because those are not approved stores.

---

## 3. Railway configuration

| | |
|---|---|
| Project | `welcoming-vibrancy` (`bbcb2596-d6f9-45c5-9c03-59cb97f373ea`) |
| Service | `clientverse-crm-production` (`5e2ea598-91f0-4f95-a67b-067585b80aa9`) |
| Environment | `production` (`12d1d2d7-3fdf-44a9-b6b6-f1d992642188`) |
| Deployment branch | `main` (auto-deploy) |
| Builder | RAILPACK, build environment V3 |
| Region | `sfo`, 1 replica |
| Healthcheck path | `/api/health` — **verified against the service configuration**, matches the route the application serves |
| Healthcheck status | Deployment reports SUCCESS; the endpoint itself could not be probed from this session |

### Variables present

`ADMIN_EMAIL`, `ADMIN_PASSWORD`, `APP_ENV`, `DB_NAME`, `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET`, `INTEGRATION_ENC_KEY`, `JWT_SECRET`, `MONGO_URL`, `Mongo_url`,
`SEED_DEMO_DATA`, `WEBHOOK_CRON_SECRET`.

### Variables missing, and what each one costs

| Variable | Consequence while unset | Owner action |
|---|---|---|
| `STRIPE_API_KEY` | Stripe sync and payment intents are unavailable. Invoice-paid outcomes must be recorded by an operator instead of read from Stripe. | Set a **test-mode** key first |
| `STRIPE_WEBHOOK_SECRET` | The Stripe webhook route cannot verify signatures, so it refuses events. This is correct fail-closed behaviour, not a bug | Set after creating the endpoint in Stripe |
| `GOOGLE_REDIRECT_URI` | Derived from `PUBLIC_BACKEND_URL`, which is also unset, so it falls back to the Railway public domain. Works, but breaks silently the moment a custom domain is added | Set explicitly |
| `PUBLIC_BACKEND_URL` | As above | Set to the public URL |
| `GIT_SHA` | Not required. Railway injects `RAILWAY_GIT_COMMIT_SHA`, which `/api/health` reads | None |

### Variable requiring cleanup

`Mongo_url` is a misspelled duplicate of `MONGO_URL`. It is unused by the application
and should be deleted, so nobody later edits the wrong one and cannot work out why the
change had no effect.

---

## 4. GitHub configuration

| | |
|---|---|
| Repository | `ebyron357/Clientverse-crm` |
| Default branch | `main` |
| Work branch | `claude/trusting-brahmagupta-lj26xf` |
| Deployment workflow | None in GitHub — Railway deploys from `main` directly |
| CI workflow | `.github/workflows/ci.yml` (frontend lint + build, backend static analysis, backend suite, CRM release smoke) |
| Scheduler workflow | `.github/workflows/scheduled-jobs.yml` |

### The two secrets, and why nothing has been running

| Secret | Status | |
|---|---|---|
| `CLIENTVERSE_PRODUCTION_URL` | **NOT SET** | |
| `WEBHOOK_CRON_SECRET` | **NOT SET** in GitHub (it *is* set on Railway) | |

**Last successful real production scheduler invocation: NONE. Not once.**

This is the single most consequential finding in this handoff, and it is proven from
three independent directions:

1. **The workflow's own logs.** Run 35650309168, job "Call scheduled endpoints",
   2026-09-21T20:19:11Z, prints:
   `CLIENTVERSE_PRODUCTION_URL or WEBHOOK_CRON_SECRET is not configured; nothing was
   called.` with `BASE_URL:` and `CRON_SECRET:` both empty in the step environment.
2. **The run history.** 1,622 scheduled runs, every one green, every one a no-op.
   The old workflow exited 0 when unconfigured, so success meant nothing.
3. **Production's own HTTP logs.** Railway's request log for the live deployment
   contains no `/api/cron/*` request at all — the most recent traffic of any kind is
   from 2026-09-18, and the deploy log has no cron entries since 2026-09-16.

So: the detectors have never run in production, the durable work queue has never had a
worker, no recovery case has ever been created by a schedule, and no approval has ever
expired on time. The product's automation has not been running since it was deployed.

**This is fixed in code but cannot be fixed from here.** The GitHub Actions secrets API
is blocked for this session (`403: Access to this GitHub Actions path is not permitted
through this proxy`), so setting the two secrets is an owner action. See §8.1.

### What changed so this cannot happen silently again

The scheduler workflow now **fails** when it is not configured, when a tick dispatches
nothing, when any endpoint returns non-200, and when production has no ledger entry for
the run it just made — it reads `/api/cron/runs` back and checks for its own delivery
ids. Green now means production was called, answered, and can prove it.

Production keeps an append-only ledger of every scheduled request it receives
(`cron_run_log`), including rejected ones, so a mismatched shared secret is
distinguishable from a scheduler that never fired. `GET /api/cron/health` answers the
question directly: `receiving_scheduled_traffic: false` with a scheduler configured
means the scheduler is not reaching production, whatever its own runs say.

---

## 5. Google / Gmail configuration

| | |
|---|---|
| Google Cloud project | Not visible from the repository or from Railway. **Owner to record it here.** |
| OAuth client identifier | Held in the Railway variable `GOOGLE_CLIENT_ID` (set) |
| OAuth client secret | Held in the Railway variable `GOOGLE_CLIENT_SECRET` (set). Not printed anywhere |
| Authorized redirect URI | `https://clientverse-crm-production-production.up.railway.app/api/integrations/google/callback` (derived, because `GOOGLE_REDIRECT_URI` and `PUBLIC_BACKEND_URL` are unset) |
| Scopes previously requested | `gmail.readonly`, `calendar.readonly`, `userinfo.email`, `openid` |
| Scopes now requested | The above **plus `gmail.send`** |
| Current connection state | Unknown from here — `/api/integrations/connections` requires reaching production |
| Sending enabled | **NO.** Two reasons, both must be cleared: the deployed code has no provider adapter at all, and any existing Google connection predates the send scope and is therefore read-only |
| Inbound configured | **NO** in the deployed code. On this branch, inbound is a poll driven by `/api/cron/inbound-email`, which needs the scheduler secrets from §4 |
| Last successful send test | **Never.** No message has ever been sent by this system |
| Last successful inbound reply test | **Never** |

### Reconnect instructions (required after merging this branch)

`gmail.send` is a new scope, so an existing consent does not cover it. Google will not
grant it retroactively and the adapter refuses to attempt a send without it — by
design, because a read-only token that tried to send would fail in a way that looks
like a delivery problem rather than a configuration one.

1. In Google Cloud Console → APIs & Services → Credentials, confirm the OAuth client's
   authorized redirect URI matches the one above exactly.
2. In the Google Cloud consent screen configuration, add
   `https://www.googleapis.com/auth/gmail.send` to the scope list. If the app is in
   testing mode, confirm the sending mailbox is a listed test user.
3. In ClientVerse → Settings → Integrations, **disconnect** Google, then connect again.
   Reconnecting without disconnecting reuses the existing grant and will not acquire
   the new scope.
4. Verify: `GET /api/integrations/connections` should show the `gmail` provider
   `active` with `gmail.send` among its `scopes`. Until it does, every outbound attempt
   is refused with a message naming the missing scope.

---

## 6. Stripe configuration

| | |
|---|---|
| Mode | **Neither.** No Stripe credential is configured on the service |
| Webhook endpoint | `https://clientverse-crm-production-production.up.railway.app/api/integrations/stripe/webhook` |
| Webhook verification status | Cannot verify — `STRIPE_WEBHOOK_SECRET` is unset, so the route refuses every event. This is fail-closed and correct |
| Last successful webhook test | **Never** |
| Deduplication verified | **By test, yes** — `stripe_webhook_events.event_id` carries a unique index and the suite asserts a replayed event is handled once (`backend/tests/test_provider_lifecycle_unit.py`). **In production, no** |
| Secret storage location | Railway service variables, once set. Nowhere else |

A legacy webhook signing secret was noted in earlier project records as needing
rotation. Since no Stripe secret is currently set on the service, rotating means
generating a fresh one when the endpoint is created, not reusing anything previous.

---

## 7. Database configuration

| | |
|---|---|
| Provider | MongoDB Atlas |
| Cluster / project | Held in the `MONGO_URL` Railway variable. Not printed here: the URI contains credentials |
| Database name | Held in the `DB_NAME` Railway variable |
| Connectivity | **Not verifiable from this session.** Atlas is reachable only on a non-HTTPS port and the session's egress is HTTPS-proxied, so no connection could be attempted. The last deployment reaching SUCCESS with a `/api/health` healthcheck is indirect evidence that the application connected at boot |
| Network access | Set to `0.0.0.0/0` by the owner on 2026-09-01 per the project record. **Worth narrowing** to Railway's egress addresses |
| Backup status | **Unknown — owner to confirm.** Atlas shared tiers have no continuous backup. This is the largest unmitigated data risk in the deployment and should be settled before real customer data lands |
| Credential storage | Railway service variables only |
| Collections observed | Not observable from here. The application creates and indexes 60+ collections at boot; this branch adds `cron_run_log`, `crm_activities`, `pipelines`, `attribution_entries`, `attribution_settings`, `inbound_unmatched`, `call_logs`, `web_enquiries`, `external_crm_events` and `intake_tokens` |
| Schema / data compatibility | **No migration is required.** Every field this branch adds is optional and read with a default. Records created before it keep working: a contact with no `archived_at` is treated as not archived, a deal with no `stage_history` shows an empty history, and a tenant with no pipeline configuration gets the shipped default stages |

---

## 8. Owner actions, in order

Each step says how to tell it worked.

### 8.1 Set the two GitHub secrets — *unblocks all automation*

Repository → Settings → Secrets and variables → Actions → New repository secret.

| Name | Value |
|---|---|
| `CLIENTVERSE_PRODUCTION_URL` | `https://clientverse-crm-production-production.up.railway.app` |
| `WEBHOOK_CRON_SECRET` | **Exactly** the value of the `WEBHOOK_CRON_SECRET` variable on the Railway service |

The two must match byte for byte. If they do not, production answers 401 and — on this
branch — records the rejection, so `GET /api/cron/runs?status=unauthorized` will show
it rather than leaving you guessing.

**Verify:** Actions → Scheduled jobs → Run workflow. The run must be green, its summary
table must show HTTP 200 and an evidence id per endpoint, and the final step must
report that production recorded the run. If either secret is still missing, the run now
**fails** with "Scheduler not configured" instead of quietly passing.

### 8.2 Merge this branch and let it deploy

Nothing in §8.3 onwards exists in production until this is done. Railway auto-deploys
`main`.

**Verify:** `curl -s https://<host>/api/health` returns the merge commit's SHA in
`git_sha`. If it returns an older SHA, the deployment has not rolled over yet.

### 8.3 Run the release gates against production

```bash
CLIENTVERSE_API_BASE=https://clientverse-crm-production-production.up.railway.app \
CLIENTVERSE_ADMIN_EMAIL='<admin email>' \
CLIENTVERSE_ADMIN_PASSWORD='<admin password>' \
CLIENTVERSE_EVIDENCE_PATH=docs/evidence/production-crm-smoke.json \
node scripts/crm_release_smoke.mjs
```

82 assertions: invitation through cross-tenant probe, session revocation, search,
pipeline history, and the recovery report's own invariants. Exit 0 or it names the step
that failed. It creates records prefixed `CRM-SMOKE-<timestamp>`; re-run with
`CLIENTVERSE_CLEANUP=1` to archive them.

Then `scripts/proof_of_life.mjs` and `scripts/operations_smoke.mjs` as before.

### 8.4 Grant the Gmail send scope

Per §5. Until this is done, outbound email is refused — correctly — and every recovery
message stops at the provider boundary with the missing scope named.

**Verify:** `GET /api/integrations/connections` shows `gmail` active with
`gmail.send` in `scopes`.

### 8.5 Send one real email end to end

Pick a real recovery case, or create a conversation to an address you control:

1. Record consent on the conversation with a stated basis.
2. Draft the message, request approval, approve it.
3. `POST /api/messages/{id}/send`.

**Verify:** the message reaches `sent`, carries a `provider_message_id` and an
`rfc822_message_id`, and the mail actually arrives. Then **send it again** — the
adapter asks Gmail whether it already holds that dispatch and must return the same
provider id without a second copy arriving.

### 8.6 Reply to that email and confirm the loop closes

Reply from the recipient mailbox, then either wait for the `inbound-email` tick or
trigger it from the Actions tab.

**Verify:** the reply appears as an inbound message on the same conversation,
`GET /api/inbound/unmatched` does **not** contain it, and the contact's timeline shows
it.

### 8.7 Confirm one recovery outcome and check the claim

`POST /api/attribution/outcomes` with the case id and a paid invoice id.

**Verify:** on a case where a message actually reached the client, the entry comes back
`claim: attributed` with `basis: reply_after_contact` or `delivered_contact` and the
message ids as evidence. On a case where nothing was sent, it comes back
`claim: unattributed` with the reason — **and that is correct behaviour, not a
failure.** If a case where nothing was sent ever comes back attributed, stop and
report it.

### 8.8 Settle the outstanding decisions

- Confirm Atlas backup policy (§7).
- Narrow Atlas network access from `0.0.0.0/0`.
- Delete the `Mongo_url` duplicate variable.
- Rotate `ADMIN_PASSWORD` if it has ever left the Railway dashboard.
- Decide whether Stripe is in scope; if so, configure test mode first.
- Set `PUBLIC_BACKEND_URL` and `GOOGLE_REDIRECT_URI` explicitly before adding a custom
  domain.

---

## 9. Security configuration

| | Status | Evidence |
|---|---|---|
| `INTEGRATION_ENC_KEY` configured | **YES** | Present on the Railway service; the application refuses to store an integration credential without it |
| Integration credential encryption tested | **YES, by test** | Fernet round-trip and tenant-scoped credential isolation, `backend/tests/test_stripe_tenant_isolation.py`, `test_unit_integrations.py`. Not exercised in production |
| JWT / session configuration present | **YES** | `JWT_SECRET` set; the application refuses to boot with a weak or default secret unless `ALLOW_INSECURE_JWT` is explicitly set, which it is not |
| Session revocation works | **YES, by test; NOT in production** | A token replayed after logout returns 401 (`test_session_revocation.py`, smoke step 49) |
| OAuth state validation works | **YES, by test** | `test_integrations.py` covers state mismatch and replay on the Google callback |
| Cron shared secret matches both ends | **NO — it is absent from one end** | Set on Railway, **not set in GitHub**. §4 |
| Provider credentials absent from browser responses | **YES** | `SENSITIVE_CONN_FIELDS` is projected out of every connection response; asserted by test |
| Production secrets absent from source control | **YES** | No secret value appears in the repository or in this document. GitHub secret scanning is enabled on the repository |

### One production defect found and fixed on this branch

The Content-Security-Policy blocked `api.fontshare.com`, which
`frontend/src/index.css` imports both display typefaces from. Every production page
load silently failed to load them and fell back to system fonts. Found by loading the
built SPA in a browser and reading the console — the only place that failure was
visible. The policy now allows the two font hosts the application actually uses, and
nothing else.

---

## 10. How to check the system is alive, from now on

Three questions, three endpoints, all admin-authenticated:

| Question | Endpoint | Healthy answer |
|---|---|---|
| Is the service up? | `GET /api/health` | `status: ok`, `database: up`, and a `git_sha` matching what you deployed |
| Is the automation actually running? | `GET /api/cron/health` | `receiving_scheduled_traffic: true` and a recent `last_authenticated_call_at`. **`false` means the scheduler is not reaching production, regardless of what GitHub Actions reports** |
| Is the recovery engine producing anything? | `GET /api/proof/portfolio` | Cases detected, messages *actually sent* (not drafted), and attributed recovered value reported separately from open potential |

If `receiving_scheduled_traffic` is `false` and the scheduler workflow is green, the
workflow is lying and the fix is §8.1 — that is exactly the failure this system has had
since it was deployed.
