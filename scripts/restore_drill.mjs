#!/usr/bin/env node
/**
 * Backup-and-restore drill, two halves around a real `mongodump` / `mongorestore`.
 *
 *   CLIENTVERSE_API_BASE=http://127.0.0.1:8001 DRILL_STATE=state.json node scripts/restore_drill.mjs seed
 *   ... mongodump, drop the database, mongorestore, restart the API ...
 *   CLIENTVERSE_API_BASE=http://127.0.0.1:8001 DRILL_STATE=state.json node scripts/restore_drill.mjs verify
 *
 * `seed` creates an organization with a known password, a website form, a lead (which
 * brings a contact, a deal and a task), moves the deal and completes the task, then writes
 * what it made to DRILL_STATE. `verify` signs in with the same password after the restore
 * and checks every record, its fields and its state came back; a restored database that
 * lost users, password hashes, indexes or records fails here. Used by
 * .github/workflows/backup-restore-drill.yml against a throwaway MongoDB, never production.
 */
import { readFileSync, writeFileSync } from 'node:fs'

const base = (process.env.CLIENTVERSE_API_BASE || '').replace(/\/$/, '')
const statePath = process.env.DRILL_STATE || 'restore-drill-state.json'
const mode = process.argv[2]
if (!base || !['seed', 'verify'].includes(mode)) {
  console.error('usage: CLIENTVERSE_API_BASE=... node scripts/restore_drill.mjs seed|verify')
  process.exit(2)
}

function check(cond, name, detail) {
  console.log(`${cond ? 'ok  ' : 'FAIL'} ${name}${cond || detail === undefined ? '' : ` ${JSON.stringify(detail)}`}`)
  if (!cond) process.exit(1)
}
async function api(path, { method = 'GET', token, body, headers = {} } = {}) {
  const init = { method, headers: { Accept: 'application/json', ...headers } }
  if (token) init.headers.Authorization = `Bearer ${token}`
  if (body) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body) }
  const response = await fetch(`${base}/api${path}`, init)
  let json = null
  try { json = await response.json() } catch { json = null }
  return { status: response.status, json }
}

async function seed() {
  const stamp = Date.now()
  const email = `restore-drill-${stamp}@example.com`
  const password = `Drill-${stamp}-Passw0rd!`
  const reg = await api('/auth/register', { method: 'POST', body: { email, password, name: 'Restore Drill' } })
  check(reg.status === 200, 'organization registered')
  const token = reg.json.token
  const form = await api('/website-forms', { method: 'POST', token, body: { name: 'Restore drill form', preset: 'contact',
    settings: { assignment: { mode: 'specific', users: [email] }, notify: { in_app: true, email: false },
      opportunity: { enabled: true, value_mode: 'commission', commission_rate: 2.5 } } } })
  const key = await api(`/website-forms/${form.json.id}/server-key`, { method: 'POST', token })
  const lead = await fetch(`${base}/api/intake/leads`, { method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key.json.key}` },
    body: JSON.stringify({ idempotencyKey: `drill-${stamp}`, name: 'Drill Lead', email: `lead-${stamp}@example.com`,
      phone: '704-555-0142', leadType: 'buyer', payload: { priceRange: '$400k-$500k' } }) }).then((r) => r.json())
  check(lead.outcome === 'accepted', 'lead filed')
  const stored = (await api(`/leads/${lead.id}`, { token })).json
  await api(`/opportunities/${stored.opportunity_id}/stage`, { method: 'PATCH', token, body: { stage: 'qualified' } })
  await api(`/tasks/${stored.task_id}`, { method: 'PATCH', token, body: { status: 'done' } })
  const state = { email, password, tenant_id: reg.json.user.tenant_id, form_id: form.json.id,
    server_key: key.json.key, lead_id: lead.id, contact_id: stored.contact_id,
    deal_id: stored.opportunity_id, task_id: stored.task_id, idempotency_key: `drill-${stamp}`,
    lead_email: `lead-${stamp}@example.com` }
  writeFileSync(statePath, JSON.stringify(state, null, 2))
  check(true, `seeded; state written to ${statePath}`)
}

async function verify() {
  const state = JSON.parse(readFileSync(statePath, 'utf8'))
  const health = await api('/health')
  check(health.status === 200 && health.json?.database === 'up', 'restored API is healthy with the database up')
  const login = await api('/auth/login', { method: 'POST', body: { email: state.email, password: state.password } })
  check(login.status === 200, 'the same password signs in after the restore (users and hashes restored)')
  const token = login.json.token
  const lead = (await api(`/leads/${state.lead_id}`, { token })).json || {}
  check(lead.email === state.lead_email && lead.fields?.price_min === 400000 && lead.fields?.price_max === 500000,
    'lead and its mapped fields restored')
  const deal = await api(`/opportunities/${state.deal_id}`, { token })
  const dealDoc = deal.json?.deal || {}
  check(deal.status === 200 && dealDoc.stage === 'qualified' && dealDoc.value === 12500, 'deal restored at its stage and value',
    { status: deal.status, stage: dealDoc.stage, value: dealDoc.value })
  const contact = await api(`/contacts/${state.contact_id}`, { token })
  check(contact.status === 200, 'contact restored')
  const tasks = (await api('/tasks', { token })).json
  const taskList = Array.isArray(tasks) ? tasks : tasks?.tasks || tasks?.items || []
  check(taskList.some((t) => t.id === state.task_id && t.status === 'done'), 'completed task restored')
  // The server key's hash and the unique idempotency index both came back: the same key is
  // accepted and the same idempotency key is still recognised as already filed.
  const again = await fetch(`${base}/api/intake/leads`, { method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${state.server_key}` },
    body: JSON.stringify({ idempotencyKey: state.idempotency_key, name: 'Drill Lead', email: state.lead_email,
      phone: '704-555-0142', message: 'retry after restore' }) }).then((r) => r.json())
  check(again.outcome === 'duplicate' && again.id === state.lead_id, 'server key and idempotency survive the restore')
  console.log('\nPASSED restore drill')
}

await (mode === 'seed' ? seed() : verify())
