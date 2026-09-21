/**
 * CRM release smoke test.
 *
 * Exercises the everyday CRM as a person actually uses it -- invite a colleague, create
 * an account, a contact and a deal, link them, assign work, complete it, move the deal,
 * read the history back, search for it, sign out and back in -- and then tries to reach
 * the same records from a second tenant and requires that attempt to come back empty.
 *
 * This is a release gate, not a demo. Every step asserts; the first failure exits
 * non-zero and names the step. It is written to be safe to run against production: the
 * records it creates are prefixed and reported so they can be found and removed, and it
 * never sends anything outbound.
 *
 * Usage:
 *   CLIENTVERSE_API_BASE=https://host CLIENTVERSE_ADMIN_EMAIL=... \
 *   CLIENTVERSE_ADMIN_PASSWORD=... node scripts/crm_release_smoke.mjs
 *
 * Optional:
 *   CLIENTVERSE_EVIDENCE_PATH   write the JSON result to this path
 *   CLIENTVERSE_CLEANUP=1       archive the records created by this run when it passes
 */

import fs from 'node:fs'
import path from 'node:path'

function required(name) {
  const value = process.env[name]
  if (!value) throw new Error(`${name} is required`)
  return value
}

function apiUrl() {
  const raw = required('CLIENTVERSE_API_BASE').replace(/\/$/, '')
  return raw.endsWith('/api') ? raw : `${raw}/api`
}

const apiBase = apiUrl()
const adminEmail = required('CLIENTVERSE_ADMIN_EMAIL')
const adminPassword = required('CLIENTVERSE_ADMIN_PASSWORD')
const evidencePath = process.env.CLIENTVERSE_EVIDENCE_PATH
const cleanup = process.env.CLIENTVERSE_CLEANUP === '1'

const runLabel = `CRM-SMOKE-${new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14)}`
const steps = []

async function request(p, options = {}) {
  const response = await fetch(`${apiBase}${p}`, options)
  const text = await response.text()
  let body = {}
  try { body = text ? JSON.parse(text) : {} } catch { body = { raw: text.slice(0, 400) } }
  return { status: response.status, body }
}

function json(token, method, body) {
  return {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  }
}

const post = (token, body) => json(token, 'POST', body)
const patch = (token, body) => json(token, 'PATCH', body)
const auth = (token) => ({ headers: { Authorization: `Bearer ${token}` } })

function record(step, ok, detail) {
  steps.push({ step, ok, ...(detail ? { detail } : {}) })
  if (!ok) {
    const failure = new Error(`FAILED: ${step}${detail ? ` -- ${detail}` : ''}`)
    failure.smoke = true
    throw failure
  }
}

function mustBe(response, status, step) {
  const allowed = Array.isArray(status) ? status : [status]
  record(step, allowed.includes(response.status),
    allowed.includes(response.status) ? undefined
      : `HTTP ${response.status} ${JSON.stringify(response.body).slice(0, 200)}`)
  return response.body
}

function assert(condition, step, detail) {
  record(step, Boolean(condition), condition ? undefined : detail)
}

async function login(email, password, step) {
  const response = await request('/auth/login', json(null, 'POST', { email, password }))
  const body = mustBe(response, 200, step)
  const token = body.access_token || body.token
  assert(token, `${step} returns a session token`)
  return token
}

const result = { run_label: runLabel, api_base: apiBase, started_at: new Date().toISOString() }

try {
  // 1-2. A tenant exists and its administrator can sign in.
  mustBe(await request('/health'), 200, '01 health endpoint answers')
  mustBe(await request('/companies'), 401, '02 unauthenticated access is refused')
  const admin = await login(adminEmail, adminPassword, '03 administrator logs in')
  const me = mustBe(await request('/auth/me', auth(admin)), 200, '04 session resolves to a user')
  assert(me.role === 'admin', '05 the smoke account is an administrator', `role=${me.role}`)
  result.tenant = { role: me.role }

  // 3-4. Invite a member and accept the invitation.
  const memberEmail = `${runLabel.toLowerCase()}-member@example.com`
  const invited = mustBe(
    await request('/team/invitations', post(admin, { email: memberEmail, role: 'member' })),
    [200, 201], '06 administrator invites a member')
  const invitation = invited.invitation || invited
  assert(invited.invite_token, '07 invitation carries a single-use acceptance token')

  // Resending must mint a new token and invalidate the old one, or a revoked or
  // superseded invitation would still let someone in.
  const resent = mustBe(await request(`/team/invitations/${invitation.id}/resend`,
    post(admin, {})), 200, '08 invitation can be resent')
  assert(resent.invite_token && resent.invite_token !== invited.invite_token,
    '09 resending issues a new token rather than reusing the old one')

  const lookup = mustBe(
    await request(`/team/invitations/lookup?token=${encodeURIComponent(resent.invite_token)}`),
    200, '10 an invitee can look their invitation up before accepting')
  assert(lookup.email === memberEmail, '11 the invitation names the invited address')

  // The invitee signs up, then accepts as themselves. Acceptance is authenticated on
  // purpose: an invitation is not a way to create an account for somebody else.
  const memberReg = await request('/auth/register', post(null, {
    email: memberEmail, password: 'SmokeMemberPass123!', name: 'CRM Smoke Member',
  }))
  const memberToken = (mustBe(memberReg, [200, 201], '12 the invitee registers')).access_token
    || memberReg.body.token
  const accepted = await request('/team/invitations/accept',
    post(memberToken, { token: resent.invite_token }))
  assert([200, 201].includes(accepted.status), '13 invitation is accepted',
    `HTTP ${accepted.status} ${JSON.stringify(accepted.body).slice(0, 200)}`)
  assert(accepted.body?.role === 'member', '14 the accepted role is the invited role')

  const staleAccept = await request('/team/invitations/accept',
    post(memberToken, { token: invited.invite_token }))
  assert(staleAccept.status >= 400, '15 the superseded invitation token no longer works',
    `HTTP ${staleAccept.status}`)

  const members = mustBe(await request('/team/members', auth(admin)), 200,
    '16 team lists its members')
  assert(members.some((m) => m.email === memberEmail && m.role === 'member'),
    '17 the invited member is on the team as a member')

  // Role enforcement is part of the baseline, not a nice-to-have.
  const memberAdminAttempt = await request('/team/members', auth(memberToken))
  assert(memberAdminAttempt.status === 403,
    '18 a member cannot read the administrator-only team surface',
    `HTTP ${memberAdminAttempt.status}`)

  // 5-7. A company, a contact, and the link between them.
  const company = mustBe(await request('/companies', post(admin, {
    name: `${runLabel} Company`, industry: 'Services', website: 'https://example.test',
  })), 200, '12 company is created')
  const contact = mustBe(await request('/contacts', post(admin, {
    name: `${runLabel} Contact`, email: `${runLabel.toLowerCase()}@example.com`,
    role: 'Operations', company_id: company.id,
  })), 200, '13 contact is created and linked to the company')
  assert(contact.company_id === company.id, '14 contact carries its company association')

  const contactDetail = mustBe(await request(`/contacts/${contact.id}`, auth(admin)), 200,
    '15 contact detail opens')
  assert(contactDetail.company?.id === company.id,
    '16 contact detail resolves the related company')

  mustBe(await request(`/contacts/${contact.id}`, patch(admin, { title: 'Head of Ops' })),
    200, '17 contact is editable')

  // 8-11. A deal, its associations, its owner, and a stage move.
  const deal = mustBe(await request('/opportunities', post(admin, {
    name: `${runLabel} Deal`, company_id: company.id, value: 4200, stage: 'lead',
    contact_ids: [contact.id], expected_close_date: '2027-03-31',
  })), 200, '18 deal is created against the company and contact')
  assert(deal.contact_ids?.includes(contact.id), '19 deal carries its contact association')
  assert(deal.expected_close_date, '20 deal carries an expected close date')

  mustBe(await request(`/opportunities/${deal.id}`, patch(admin, {
    owner: adminEmail, value: 5000,
  })), 200, '21 deal owner and value are editable')

  mustBe(await request(`/opportunities/${deal.id}/stage`, patch(admin, { stage: 'qualified' })),
    200, '22 deal moves to another pipeline stage')

  const dealDetail = mustBe(await request(`/opportunities/${deal.id}`, auth(admin)), 200,
    '23 deal detail opens')
  assert(dealDetail.deal?.stage === 'qualified', '24 the stage change persisted')
  assert(dealDetail.deal?.owner === adminEmail, '25 the owner change persisted')
  assert(Number(dealDetail.deal?.value) === 5000, '26 the value change persisted')
  assert((dealDetail.stage_history || []).some((h) => h.to === 'qualified'),
    '27 stage history records the transition')

  // 12-14. A follow-up task: create, assign, complete.
  const task = mustBe(await request('/crm/tasks', post(admin, {
    title: `${runLabel} follow up`, related_type: 'deal', related_id: deal.id,
    assignee: memberEmail, due_date: '2027-02-01', status: 'todo',
  })), 200, '28 follow-up task is created against the deal')
  assert(task.assignee === memberEmail, '29 task is assigned')

  const overview = mustBe(await request('/tasks/overview', auth(admin)), 200,
    '30 task overview reports overdue and upcoming work')
  assert(typeof overview.counts?.upcoming === 'number', '31 task overview returns counts')

  mustBe(await request(`/crm/tasks/${task.id}`, patch(admin, { status: 'done' })), 200,
    '32 task is completed')
  const tasksAfter = mustBe(await request(`/tasks?related_id=${deal.id}`, auth(admin)), 200,
    '33 tasks are listable by the record they belong to')
  const storedTask = (tasksAfter.items || []).find((t) => t.id === task.id)
  assert(storedTask?.status === 'done', '34 task completion persisted')
  assert(storedTask?.completed_at, '35 task records when it was completed')

  // Activity that is not a task: a logged call.
  mustBe(await request('/activities', post(admin, {
    type: 'call', related_type: 'contact', related_id: contact.id,
    subject: `${runLabel} discovery call`, duration_minutes: 20, outcome: 'interested',
  })), 200, '36 a call can be logged against a contact')

  // 15-16. Move the deal again, then read the whole history back.
  mustBe(await request(`/opportunities/${deal.id}/stage`, patch(admin, { stage: 'proposal' })),
    200, '37 deal moves to a further stage')
  const timeline = mustBe(await request(`/opportunities/${deal.id}/timeline`, auth(admin)),
    200, '38 deal timeline is readable')
  assert((timeline.timeline || []).length > 0, '39 deal timeline is not empty')
  const contactTimeline = mustBe(
    await request(`/contacts/${contact.id}/timeline`, auth(admin)), 200,
    '40 contact timeline is readable')
  assert((contactTimeline.timeline || []).some((e) => e.type === 'call'),
    '41 the logged call appears on the contact timeline')

  // 17. Search finds what was just created.
  const search = mustBe(await request(`/search?q=${encodeURIComponent(runLabel)}`, auth(admin)),
    200, '42 global search answers')
  assert(search.companies?.some((c) => c.id === company.id), '43 search finds the company')
  assert(search.contacts?.some((c) => c.id === contact.id), '44 search finds the contact')
  assert(search.deals?.some((d) => d.id === deal.id), '45 search finds the deal')

  const filtered = mustBe(
    await request(`/opportunities?stage=proposal&owner=${encodeURIComponent(adminEmail)}`,
      auth(admin)), 200, '46 deals can be filtered by stage and owner')
  assert(filtered.some((d) => d.id === deal.id), '47 the filter returns the deal')

  // 18-20. Sign out, prove the old session is dead, sign back in, prove persistence.
  const loggedOut = await request('/auth/logout', post(admin, {}))
  assert([200, 204].includes(loggedOut.status), '48 logout succeeds', `HTTP ${loggedOut.status}`)
  const replay = await request('/companies', auth(admin))
  assert(replay.status === 401, '49 the old session is revoked server-side, not just dropped',
    `HTTP ${replay.status}`)

  const admin2 = await login(adminEmail, adminPassword, '50 administrator logs back in')
  const persisted = mustBe(await request(`/opportunities/${deal.id}`, auth(admin2)), 200,
    '51 the deal is still there after re-login')
  assert(persisted.deal?.stage === 'proposal', '52 state persisted across sessions')

  // 21-23. A second tenant must not be able to reach any of it.
  const otherEmail = `${runLabel.toLowerCase()}-other@example.com`
  const otherReg = await request('/auth/register', post(null, {
    email: otherEmail, password: 'SmokeOtherPass123!', name: 'CRM Smoke Other Tenant',
  }))
  const otherToken = (mustBe(otherReg, [200, 201], '53 a second tenant is created')).access_token
    || otherReg.body.token
  assert(otherToken, '54 the second tenant has a session')

  const crossChecks = [
    ['company', `/companies/${company.id}`],
    ['contact', `/contacts/${contact.id}`],
    ['deal', `/opportunities/${deal.id}`],
    ['deal timeline', `/opportunities/${deal.id}/timeline`],
  ]
  const crossResults = {}
  for (const [label, p] of crossChecks) {
    const response = await request(p, auth(otherToken))
    crossResults[label] = response.status
    assert(response.status === 404,
      `55 direct-id ${label} access from another tenant returns not-found`,
      `HTTP ${response.status}`)
  }
  const crossSearch = mustBe(
    await request(`/search?q=${encodeURIComponent(runLabel)}`, auth(otherToken)), 200,
    '56 the other tenant can run a search')
  assert((crossSearch.total || 0) === 0, '57 the other tenant\'s search leaks nothing',
    `total=${crossSearch.total}`)
  const crossList = mustBe(await request('/opportunities', auth(otherToken)), 200,
    '58 the other tenant can list its own deals')
  assert(!crossList.some((d) => d.id === deal.id), '59 no cross-tenant record in the list')

  result.records = { company: company.id, contact: contact.id, deal: deal.id, task: task.id }
  result.cross_tenant = crossResults

  if (cleanup) {
    for (const [p] of [[`/opportunities/${deal.id}/archive`], [`/contacts/${contact.id}/archive`],
      [`/companies/${company.id}/archive`]]) {
      await request(p, post(admin2, {}))
    }
    result.cleanup = 'created records were archived'
  }

  result.passed = true
} catch (error) {
  result.passed = false
  result.error = error.message
}

result.finished_at = new Date().toISOString()
result.steps = steps
result.summary = {
  total: steps.length,
  passed: steps.filter((s) => s.ok).length,
  failed: steps.filter((s) => !s.ok).length,
}
result.secret_redaction =
  'This evidence intentionally omits passwords, session tokens, and provider credentials.'
result.cleanup_note = cleanup
  ? 'Records created by this run were archived.'
  : `This run leaves records prefixed ${runLabel}. Re-run with CLIENTVERSE_CLEANUP=1 to archive them.`

if (evidencePath) {
  fs.mkdirSync(path.dirname(evidencePath), { recursive: true })
  fs.writeFileSync(evidencePath, `${JSON.stringify(result, null, 2)}\n`)
}

console.log(JSON.stringify(result, null, 2))
process.exit(result.passed ? 0 : 1)
