#!/usr/bin/env node
/**
 * Production acceptance: the authenticated lead journey, run against a live deployment.
 *
 *   CLIENTVERSE_API_BASE=https://crm.clientverse.io \
 *   CLIENTVERSE_EXPECTED_SHA=<commit> CLIENTVERSE_EVIDENCE_PATH=acceptance.json \
 *   node scripts/production_acceptance.mjs
 *
 * It needs no owner credentials and touches no customer data. It registers two clearly
 * named test organizations ("ClientVerse Acceptance Test …") on reserved `example.com`
 * addresses, which cannot receive mail. It turns email alerts off for the test user and
 * the test form, then drives the journey a real website and agent would:
 *
 *   health + revision -> sign-in page -> website form -> server key -> lead in
 *   -> fields, attribution, assignee, deal, task -> visible after a fresh sign-in
 *   -> same answers again (duplicate) -> same key again (idempotent)
 *   -> changed time and `$500,000+` budget (new enquiry, same contact, minimum not ceiling)
 *   -> alias precedence -> another organization sees none of it -> pipeline move
 *   -> task done -> lead responded -> export -> sign-out ends the session -> archive.
 *
 * Each step is an assertion; the first failure exits 1. Evidence (no secrets, no tokens)
 * goes to CLIENTVERSE_EVIDENCE_PATH. The test organizations stay, archived and closed, so
 * the evidence can be re-read; they hold only the records this script made.
 */
import { writeFileSync } from 'node:fs'
import { randomBytes } from 'node:crypto'

const base = (process.env.CLIENTVERSE_API_BASE || '').replace(/\/$/, '')
if (!base) { console.error('CLIENTVERSE_API_BASE is required'); process.exit(2) }
const expectedSha = (process.env.CLIENTVERSE_EXPECTED_SHA || '').trim()
const waitSeconds = Number(process.env.CLIENTVERSE_DEPLOY_WAIT_SECONDS || 0)
const evidencePath = process.env.CLIENTVERSE_EVIDENCE_PATH
const run = process.env.GITHUB_RUN_ID ? `${process.env.GITHUB_RUN_ID}-${process.env.GITHUB_RUN_ATTEMPT || 1}`
  : `local-${Date.now()}`
const tag = `${run}-${randomBytes(3).toString('hex')}`

const evidence = { base, run, expected_sha: expectedSha || null, started_at: new Date().toISOString(),
  steps: [], records: {}, result: 'running' }
let step = 0

function save() {
  if (evidencePath) writeFileSync(evidencePath, JSON.stringify(evidence, null, 2))
}
function pass(name, detail = {}) {
  step += 1
  evidence.steps.push({ n: step, name, ok: true, ...detail })
  console.log(`ok ${String(step).padStart(2, '0')} ${name}`)
}
function fail(name, detail) {
  step += 1
  evidence.steps.push({ n: step, name, ok: false, detail })
  evidence.result = 'failed'
  evidence.finished_at = new Date().toISOString()
  save()
  console.error(`FAIL ${String(step).padStart(2, '0')} ${name}: ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`)
  process.exit(1)
}
function check(cond, name, detail = {}, failure) {
  if (cond) pass(name, detail)
  else fail(name, failure ?? detail)
}

async function request(path, { method = 'GET', token, body, headers = {}, raw = false } = {}) {
  const init = { method, headers: { Accept: 'application/json', 'User-Agent': 'clientverse-acceptance', ...headers } }
  if (token) init.headers.Authorization = `Bearer ${token}`
  if (body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body) }
  const response = await fetch(`${base}${path.startsWith('/') ? path : `/${path}`}`, init)
  const text = await response.text()
  let json = null
  if (!raw) { try { json = JSON.parse(text) } catch { json = null } }
  return { status: response.status, json, text, headers: response.headers }
}
const api = (path, options) => request(`/api${path}`, options)

async function waitForRevision() {
  const deadline = Date.now() + waitSeconds * 1000
  for (;;) {
    let health
    try { health = await api('/health') } catch (error) { health = { status: 0, json: null, text: String(error) } }
    const sha = health.json?.git_sha || ''
    const matches = !expectedSha || (sha && (sha.startsWith(expectedSha) || expectedSha.startsWith(sha)))
    if (health.status === 200 && matches) return health
    if (Date.now() >= deadline) return health
    await new Promise((resolve) => setTimeout(resolve, 20000))
  }
}

async function register(label) {
  const email = `acceptance+${label}-${tag}@example.com`.toLowerCase()
  const password = `Acc-${randomBytes(9).toString('base64url')}-9`
  const response = await api('/auth/register', { method: 'POST',
    body: { email, password, name: `ClientVerse Acceptance Test ${label}` } })
  return { email, password, response }
}

const SITE = 'https://acceptance.clientverse.example'

async function main() {
  // 1. The deployment: healthy, database up, and the revision we meant to release.
  const health = await waitForRevision()
  evidence.health = health.json
  check(health.status === 200 && health.json?.status === 'ok' && health.json?.database === 'up',
    'API healthy with the database up', { health: health.json }, { status: health.status, body: health.text.slice(0, 300) })
  if (expectedSha) {
    const sha = health.json?.git_sha || ''
    check(sha && (sha.startsWith(expectedSha) || expectedSha.startsWith(sha)),
      'production runs the expected revision', { git_sha: sha }, { git_sha: sha, expected: expectedSha })
  }

  // 2. The public doors a visitor and a website use.
  const login = await request('/login', { raw: true, headers: { Accept: 'text/html' } })
  check(login.status === 200 && /<div id="root">/.test(login.text), 'sign-in page is served', { status: login.status })
  const embed = await api('/public/forms/embed.js', { raw: true })
  check(embed.status === 200, 'website embed script is served', { status: embed.status })
  const retired = await api('/auth/google/session', { method: 'POST', body: { session_id: 'acceptance' } })
  check(retired.status === 410, 'retired third-party Google sign-in is refused', { status: retired.status })

  // 3. An isolated test organization, its admin signed in, email alerts off.
  const one = await register('A')
  check(one.response.status === 200 && one.response.json?.token, 'test organization A registered',
    { email: one.email }, { status: one.response.status, body: one.response.text.slice(0, 300) })
  let token = one.response.json.token
  const tenantA = one.response.json.user.tenant_id
  evidence.records.organization_a = { tenant_id: tenantA, admin: one.email }
  const prefs = await api('/notifications/preferences/me', { method: 'PUT', token,
    body: { prefs: { channels: { email: false, in_app: true } } } })
  check(prefs.status === 200 && prefs.json?.effective?.channels?.email === false,
    'email alerts off for the test admin', { effective: prefs.json?.effective?.channels })

  const form = await api('/website-forms', { method: 'POST', token, body: {
    name: `Acceptance form ${tag}`, preset: 'contact', settings: {
      allowed_origins: [SITE],
      assignment: { mode: 'specific', users: [one.email] },
      opportunity: { enabled: true, value_mode: 'commission', commission_rate: 2.5 },
      notify: { in_app: true, email: false } } } })
  check(form.status === 200 && form.json?.id, 'website form created', { form_id: form.json?.id },
    { status: form.status, body: form.text.slice(0, 300) })
  evidence.records.form = form.json.id
  const key = await api(`/website-forms/${form.json.id}/server-key`, { method: 'POST', token })
  check(key.status === 200 && key.json?.key?.startsWith('cvsk_'), 'server key minted for the website')
  const serverKey = key.json.key
  const intake = (body) => request('/api/intake/leads', { method: 'POST', body,
    headers: { Authorization: `Bearer ${serverKey}` } })

  // 4. A lead in, the way a website's own server sends one.
  const leadBody = {
    idempotencyKey: `acceptance-${tag}-1`, source: 'acceptance-buyer-guide', leadType: 'buyer',
    name: 'Acceptance Test Buyer', email: `buyer-${tag}@example.com`, phone: '704-555-0142',
    propertyAddress: '1200 Queens Rd, Charlotte, NC', message: 'Acceptance test - please ignore.',
    timeframe: '3-6 months', consultationDate: '2030-05-01', consultationTime: '09:30',
    pageUrl: `${SITE}/buyers`,
    payload: { priceRange: '$400k-$500k', preapproval: 'Yes', propertyType: 'Single family' },
  }
  const first = await intake(leadBody)
  check(first.status === 200 && first.json?.accepted === true && first.json?.outcome === 'accepted',
    'website lead accepted', { id: first.json?.id }, { status: first.status, body: first.text.slice(0, 300) })
  const leadId = first.json.id
  evidence.records.lead = leadId

  const stored = (await api(`/leads/${leadId}`, { token })).json || {}
  const f = stored.fields || {}
  check(stored.tenant_id === tenantA && stored.form_id === form.json.id, 'lead filed in the right organization and form')
  check(stored.name === leadBody.name && stored.email === leadBody.email && stored.phone === leadBody.phone
    && stored.property_address === leadBody.propertyAddress, 'contact fields mapped')
  check(f.lead_type === 'Buying' && f.timeline === '3-6 months' && f.preferred_date === '2030-05-01'
    && f.preferred_time === '09:30' && f.pre_approved === 'Yes', 'intent, timing and qualification mapped', { fields: f })
  check(f.price_min === 400000 && f.price_max === 500000, 'budget range mapped to both bounds')
  check(stored.source_page === `${SITE}/buyers` && stored.extra?.source === 'acceptance-buyer-guide'
    && stored.received_via === 'server', 'source attribution recorded',
    { source_page: stored.source_page, source: stored.extra?.source })
  check(stored.assigned_to === one.email && stored.contact_id && stored.opportunity_id && stored.task_id,
    'assigned, with a contact, a deal and a follow-up task', { assigned_to: stored.assigned_to })
  check(stored.estimated_value === 12500, 'deal priced from the budget (2.5% of $500,000)', { value: stored.estimated_value })
  evidence.records.contact = stored.contact_id
  evidence.records.deal = stored.opportunity_id
  evidence.records.task = stored.task_id

  // 5. Persistence: sign out, sign back in, the lead is still there.
  const out = await api('/auth/logout', { method: 'POST', token })
  check(out.status === 200, 'signed out')
  const after = await api('/auth/me', { token })
  check(after.status === 401, 'the signed-out session no longer works', { status: after.status })
  const wrong = await api('/auth/login', { method: 'POST', body: { email: one.email, password: 'not-the-password' } })
  check(wrong.status === 401, 'a wrong password is refused', { status: wrong.status })
  const again = await api('/auth/login', { method: 'POST', body: { email: one.email, password: one.password } })
  check(again.status === 200 && again.json?.token, 'signed back in')
  token = again.json.token
  const listed = await api('/leads', { token })
  const rows = listed.json?.leads || listed.json?.items || (Array.isArray(listed.json) ? listed.json : [])
  check(listed.status === 200 && rows.some((row) => row.id === leadId), 'lead visible in the inbox after a fresh sign-in')

  // 6. Repeats: the same answers collapse; the same key is idempotent; a change is kept.
  const dup = await intake({ ...leadBody, idempotencyKey: `acceptance-${tag}-double-click` })
  check(dup.json?.outcome === 'duplicate' && dup.json?.id === leadId, 'same answers again collapse as a duplicate')
  const retry = await intake({ ...leadBody, consultationTime: '11:00' })
  check(retry.json?.outcome === 'duplicate' && retry.json?.id === leadId, 'same idempotency key is not filed twice')
  const changed = await intake({ ...leadBody, idempotencyKey: `acceptance-${tag}-2`, consultationTime: '15:30',
    payload: { ...leadBody.payload, priceRange: '$500,000+' } })
  check(changed.json?.outcome === 'accepted' && changed.json?.id !== leadId,
    'changed time and budget filed as a new enquiry', { id: changed.json?.id })
  const second = (await api(`/leads/${changed.json.id}`, { token })).json || {}
  check(second.contact_id === stored.contact_id && second.opportunity_id === stored.opportunity_id,
    'same person: same contact and same open deal')
  check(second.fields?.price_min === 500000 && second.fields?.price_max === undefined,
    '$500,000+ is a minimum, not a ceiling', { fields: { price_min: second.fields?.price_min, price_max: second.fields?.price_max } })
  check(second.fields?.preferred_time === '15:30', 'changed consultation time kept')
  const contact = (await api(`/contacts/${stored.contact_id}`, { token })).json || {}
  const custom = contact.custom_fields || contact.contact?.custom_fields || {}
  check(custom.price_min === 500000 && custom.price_max === undefined, 'contact budget replaced, no stale ceiling',
    { custom: { price_min: custom.price_min, price_max: custom.price_max } })
  const alias = await intake({ ...leadBody, idempotencyKey: `acceptance-${tag}-3`, email: `alias-${tag}@example.com`,
    phone: '704-555-0100', mobile: '704-555-0199', consultationTime: '16:00' })
  const aliasLead = (await api(`/leads/${alias.json?.id}`, { token })).json || {}
  check(aliasLead.phone === '704-555-0100' && aliasLead.extra?.mobile === '704-555-0199',
    'an alias never replaces the field itself', { phone: aliasLead.phone })

  // 7. Isolation: a second organization sees none of it.
  const two = await register('B')
  check(two.response.status === 200, 'test organization B registered')
  const tokenB = two.response.json.token
  evidence.records.organization_b = { tenant_id: two.response.json.user.tenant_id, admin: two.email }
  const peek = await api(`/leads/${leadId}`, { token: tokenB })
  const peekDeal = await api(`/opportunities/${stored.opportunity_id}`, { token: tokenB })
  const peekContact = await api(`/contacts/${stored.contact_id}`, { token: tokenB })
  check(peek.status === 404 && peekDeal.status === 404 && peekContact.status === 404,
    'another organization cannot read the lead, deal or contact',
    { statuses: [peek.status, peekDeal.status, peekContact.status] })
  const otherKey = await request('/api/intake/leads', { method: 'POST', body: leadBody,
    headers: { Authorization: 'Bearer cvsk_not-a-real-key' } })
  check(otherKey.status === 401, 'an unknown server key is refused')
  await api('/auth/logout', { method: 'POST', token: tokenB })

  // 8. Working the lead: pipeline, task, response, export.
  const move = await api(`/opportunities/${stored.opportunity_id}/stage`, { method: 'PATCH', token, body: { stage: 'qualified' } })
  check(move.status === 200 && move.json?.stage === 'qualified', 'deal moved to Qualified')
  const done = await api(`/tasks/${stored.task_id}`, { method: 'PATCH', token, body: { status: 'done' } })
  check(done.status === 200, 'follow-up task completed')
  for (const id of [leadId, changed.json.id, alias.json.id]) {
    const responded = await api(`/leads/${id}`, { method: 'PATCH', token, body: { status: 'responded' } })
    if (responded.status !== 200) fail('lead marked responded', { id, status: responded.status })
  }
  const lead = (await api(`/leads/${leadId}`, { token })).json || {}
  check(lead.status === 'responded' && lead.sla?.first_response_at, 'lead marked responded; its clock stopped')
  const csv = await api('/leads/export', { token, raw: true })
  check(csv.status === 200 && csv.text.includes(leadBody.email), 'leads export contains the lead')
  const today = await api('/today', { token })
  check([200, 404].includes(today.status), 'Today plan answers', { status: today.status })
  const cron = await api('/cron/health', { token })
  check(cron.status === 403, 'a self-registered admin cannot read the platform job ledger', { status: cron.status })

  // 9. Leave nothing open: close the leads, archive the deal and contacts.
  for (const id of [leadId, changed.json.id, alias.json.id]) {
    await api(`/leads/${id}`, { method: 'PATCH', token, body: { status: 'closed' } })
  }
  const archivedDeal = await api(`/opportunities/${stored.opportunity_id}/archive`, { method: 'POST', token })
  const archivedContact = await api(`/contacts/${stored.contact_id}/archive`, { method: 'POST', token })
  if (aliasLead.contact_id && aliasLead.contact_id !== stored.contact_id) {
    await api(`/contacts/${aliasLead.contact_id}/archive`, { method: 'POST', token })
  }
  await api(`/website-forms/${form.json.id}`, { method: 'PATCH', token, body: { status: 'paused' } })
  check(archivedDeal.status === 200 && archivedContact.status === 200, 'test records closed and archived')
  await api('/auth/logout', { method: 'POST', token })

  evidence.result = 'passed'
  evidence.finished_at = new Date().toISOString()
  save()
  console.log(`\nPASSED ${step} checks against ${base}${expectedSha ? ` at ${expectedSha}` : ''}`)
}

main().catch((error) => fail('unexpected error', String(error?.stack || error)))
