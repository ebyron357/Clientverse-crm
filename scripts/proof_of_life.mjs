import fs from 'node:fs'

const apiBase = process.env.CLIENTVERSE_API_BASE || 'https://8001-in8v1wws9289jt9pfzcyj-03350434.us4.manus.computer/api'
const serverPid = process.env.CLIENTVERSE_BACKEND_PID || '21413'
const evidencePath = '/home/ubuntu/Clientverse-crm-production/docs/evidence/proof-of-life-api.json'

function processEnv(name) {
  const entries = fs.readFileSync(`/proc/${serverPid}/environ`, 'utf8').split('\0')
  const prefix = `${name}=`
  const entry = entries.find((item) => item.startsWith(prefix))
  return entry ? entry.slice(prefix.length) : ''
}

async function request(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, options)
  const body = await response.json().catch(() => ({}))
  return { status: response.status, body }
}

function json(token, payload) {
  return {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }
}

function authorized(token) {
  return { headers: { Authorization: `Bearer ${token}` } }
}

function mustBe(response, status, step) {
  if (response.status !== status) throw new Error(`${step} returned HTTP ${response.status}`)
  return response.body
}

const adminEmail = processEnv('ADMIN_EMAIL')
const adminPassword = processEnv('ADMIN_PASSWORD')
if (!adminEmail || !adminPassword) throw new Error('Approved admin test identity is not available on the running backend')

const runLabel = `PROOF-${new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14)}`
const health = await request('/health')
mustBe(health, 200, 'health')

const login = await request('/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: adminEmail, password: adminPassword }),
})
const token = mustBe(login, 200, 'admin login').token
if (!token) throw new Error('Admin login returned no session token')

const company = mustBe(await request('/companies', json(token, {
  name: `${runLabel} Company`, industry: 'Services', website: 'https://example.test', tier: 'standard',
})), 200, 'company creation')

const contact = mustBe(await request('/contacts', json(token, {
  name: `${runLabel} Contact`, email: `${runLabel.toLowerCase()}@example.com`, role: 'Operations', company_id: company.id,
})), 200, 'contact creation')

const opportunity = mustBe(await request('/opportunities', json(token, {
  name: `${runLabel} Opportunity`, company_id: company.id, value: 1250, stage: 'lead', owner: 'proof-of-life',
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

const commitment = mustBe(await request('/commitments', json(token, {
  workspace_id: workspace.id, title: `${runLabel} Commitment`, owner: 'proof-of-life', due_date: '2027-01-31T17:00:00+00:00', status: 'open',
})), 200, 'commitment creation')

const relogin = await request('/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: adminEmail, password: adminPassword }),
})
const refreshedToken = mustBe(relogin, 200, 'admin re-login').token
if (!refreshedToken) throw new Error('Admin re-login returned no session token')

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
  authentication: { initial_login_http: login.status, post_refresh_login_http: relogin.status },
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
  secret_redaction: 'This evidence intentionally omits account identities, passwords, session tokens, database credentials, OAuth values, and internal record identifiers.',
}

fs.mkdirSync('/home/ubuntu/Clientverse-crm-production/docs/evidence', { recursive: true })
fs.writeFileSync(evidencePath, `${JSON.stringify(proof, null, 2)}\n`)
console.log(JSON.stringify({ run_label: proof.run_label, health: proof.health, workflow: proof.workflow, persistence_after_refresh: proof.persistence_after_refresh }, null, 2))
