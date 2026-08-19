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

async function request(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, options)
  const body = await response.json().catch(() => ({}))
  return { status: response.status, body }
}

function payload(token, body) {
  return {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

function authorized(token) {
  return { headers: { Authorization: `Bearer ${token}` } }
}

function mustBe(response, status, step) {
  const allowed = Array.isArray(status) ? status : [status]
  if (!allowed.includes(response.status)) throw new Error(`${step} returned HTTP ${response.status}`)
  return response.body
}

function sessionToken(body, step) {
  const token = body.access_token || body.token
  if (!token) throw new Error(`${step} returned no session token`)
  return token
}

async function login(email, password, step) {
  const response = await request('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  return sessionToken(mustBe(response, 200, step), step)
}

const runLabel = `PRODUCTION-SMOKE-${new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14)}`
const health = await request('/health')
mustBe(health, 200, 'health')

const unauthenticatedCompanies = await request('/companies')
mustBe(unauthenticatedCompanies, 401, 'unauthenticated company access')

const token = await login(adminEmail, adminPassword, 'administrator login')
const company = mustBe(await request('/companies', payload(token, {
  name: `${runLabel} Company`, industry: 'Services', website: 'https://example.test', tier: 'standard',
})), 200, 'company creation')

const contact = mustBe(await request('/contacts', payload(token, {
  name: `${runLabel} Contact`, email: `${runLabel.toLowerCase()}@example.com`, role: 'Operations', company_id: company.id,
})), 200, 'contact creation')

const opportunity = mustBe(await request('/opportunities', payload(token, {
  name: `${runLabel} Opportunity`, company_id: company.id, value: 1250, stage: 'lead', owner: 'production-smoke',
})), 200, 'opportunity creation')

const closedWon = await request(`/opportunities/${opportunity.id}/stage`, {
  method: 'PATCH',
  headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ stage: 'closed_won' }),
})
mustBe(closedWon, 200, 'opportunity close-won transition')

const workspaces = mustBe(await request('/workspaces', authorized(token)), 200, 'workspace lookup')
const workspace = workspaces.find((item) => item.opportunity_id === opportunity.id)
if (!workspace) throw new Error('Close-won opportunity did not create a client workspace')

const commitment = mustBe(await request('/commitments', payload(token, {
  workspace_id: workspace.id, title: `${runLabel} Commitment`, owner: 'production-smoke', due_date: '2027-01-31T17:00:00+00:00', status: 'open',
})), 200, 'commitment creation')

const isolatedEmail = `${runLabel.toLowerCase()}-isolation@example.com`
const registration = await request('/auth/register', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: isolatedEmail, password: 'SmokeTestPass123!', name: 'Production Smoke Isolation' }),
})
const isolatedToken = sessionToken(mustBe(registration, [200, 201], 'isolated-user registration'), 'isolated-user registration')
const isolatedWorkspace = await request(`/workspaces/${workspace.id}`, authorized(isolatedToken))
if (![403, 404].includes(isolatedWorkspace.status)) {
  throw new Error(`cross-tenant workspace access returned HTTP ${isolatedWorkspace.status}`)
}

const refreshedToken = await login(adminEmail, adminPassword, 'administrator re-login')
const [companies, contacts, opportunities, workspaceDetail, finalHealth] = await Promise.all([
  request('/companies', authorized(refreshedToken)),
  request('/contacts', authorized(refreshedToken)),
  request('/opportunities', authorized(refreshedToken)),
  request(`/workspaces/${workspace.id}`, authorized(refreshedToken)),
  request('/health'),
])

mustBe(companies, 200, 'company persistence lookup')
mustBe(contacts, 200, 'contact persistence lookup')
mustBe(opportunities, 200, 'opportunity persistence lookup')
mustBe(workspaceDetail, 200, 'workspace persistence lookup')
mustBe(finalHealth, 200, 'final health')

const proof = {
  run_label: runLabel,
  api_base: apiBase,
  health: { initial_http: health.status, final_http: finalHealth.status, service: finalHealth.body.service, status: finalHealth.body.status, database: finalHealth.body.database },
  authentication: { administrator_login_http: 200, administrator_relogin_http: 200, unauthenticated_access_http: unauthenticatedCompanies.status },
  workflow: {
    company_create_http: 200,
    contact_create_http: 200,
    opportunity_create_http: 200,
    close_won_http: closedWon.status,
    workspace_created_from_opportunity: Boolean(workspace),
    commitment_create_http: 200,
  },
  persistence_after_refresh: {
    company: companies.body.some((item) => item.id === company.id),
    contact: contacts.body.some((item) => item.id === contact.id && item.company_id === company.id),
    opportunity: opportunities.body.some((item) => item.id === opportunity.id && item.stage === 'closed_won'),
    workspace: workspaceDetail.body.workspace?.id === workspace.id && workspaceDetail.body.workspace?.company_id === company.id,
    commitment: workspaceDetail.body.commitments?.some((item) => item.id === commitment.id && item.workspace_id === workspace.id),
  },
  tenant_isolation: { cross_tenant_workspace_http: isolatedWorkspace.status },
  cleanup_note: 'This run creates explicitly named PRODUCTION-SMOKE records in the administrator tenant. Review and remove them only after retaining the approved validation evidence.',
  secret_redaction: 'This evidence intentionally omits account identities, passwords, session tokens, database credentials, OAuth values, and internal record identifiers.',
}

if (evidencePath) {
  fs.mkdirSync(path.dirname(evidencePath), { recursive: true })
  fs.writeFileSync(evidencePath, `${JSON.stringify(proof, null, 2)}\n`)
}

console.log(JSON.stringify(proof, null, 2))
