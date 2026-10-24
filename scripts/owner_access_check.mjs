#!/usr/bin/env node
/**
 * Owner access check: the owner's own sign-in works on production, read-only.
 *
 *   CLIENTVERSE_API_BASE=https://crm.clientverse.io \
 *   CLIENTVERSE_OWNER_EMAIL=... CLIENTVERSE_OWNER_PASSWORD=... node scripts/owner_access_check.mjs
 *
 * Signs in as the owner (the ADMIN_EMAIL account), confirms the account is the admin of
 * the owner's organization, reads the platform job ledger only that organization may read,
 * signs out and confirms the session ended. It writes no records. It prints no
 * credential, token or record content; only counts and yes/no answers.
 */
import { writeFileSync } from 'node:fs'

const base = (process.env.CLIENTVERSE_API_BASE || '').replace(/\/$/, '')
const email = process.env.CLIENTVERSE_OWNER_EMAIL
const password = process.env.CLIENTVERSE_OWNER_PASSWORD
const evidencePath = process.env.CLIENTVERSE_EVIDENCE_PATH
if (!base || !email || !password) {
  console.error('CLIENTVERSE_API_BASE, CLIENTVERSE_OWNER_EMAIL and CLIENTVERSE_OWNER_PASSWORD are required')
  process.exit(2)
}

const evidence = { base, started_at: new Date().toISOString(), steps: [], result: 'running' }
function done(result) {
  evidence.result = result
  evidence.finished_at = new Date().toISOString()
  if (evidencePath) writeFileSync(evidencePath, JSON.stringify(evidence, null, 2))
}
function check(cond, name, detail = {}) {
  evidence.steps.push({ name, ok: Boolean(cond), ...detail })
  console.log(`${cond ? 'ok  ' : 'FAIL'} ${name}`)
  if (!cond) { done('failed'); process.exit(1) }
}
async function api(path, { method = 'GET', token, body } = {}) {
  const headers = { Accept: 'application/json', 'User-Agent': 'clientverse-owner-check' }
  if (token) headers.Authorization = `Bearer ${token}`
  if (body) headers['Content-Type'] = 'application/json'
  const response = await fetch(`${base}/api${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined })
  let json = null
  try { json = await response.json() } catch { json = null }
  return { status: response.status, json }
}

const login = await api('/auth/login', { method: 'POST', body: { email, password } })
check(login.status === 200 && login.json?.token, 'owner signs in with email and password', { status: login.status })
const token = login.json.token
const me = await api('/auth/me', { token })
check(me.status === 200 && me.json?.role === 'admin', 'owner is an admin', { role: me.json?.role })
check(!me.json?.must_change_password, 'owner is not held on a temporary password')
const ledger = await api('/cron/health', { token })
check(ledger.status === 200, "owner reads the platform job ledger (owner's organization only)", { status: ledger.status })
evidence.scheduler = { scheduled_jobs_running: ledger.json?.scheduled_jobs_running ?? null,
  receiving_scheduled_traffic: ledger.json?.receiving_scheduled_traffic ?? null }
const team = await api('/team/members', { token })
check(team.status === 200, 'owner reads the team', { members: Array.isArray(team.json) ? team.json.length
  : (team.json?.members || []).length })
const out = await api('/auth/logout', { method: 'POST', token })
check(out.status === 200, 'owner signs out')
const after = await api('/auth/me', { token })
check(after.status === 401, 'the signed-out session no longer works', { status: after.status })
done('passed')
console.log('\nPASSED owner access check')
