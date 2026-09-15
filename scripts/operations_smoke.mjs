/**
 * Operations smoke — durable work queue, Second Chance detection, Next Best Action,
 * and the external-component security gate, verified end to end against a running
 * deployment.
 *
 * Companion to proof_of_life.mjs. Same rules: no secret values are printed, records
 * created here are explicitly named so they can be found and removed, and every
 * assertion is recorded as an observed HTTP result rather than an assumption.
 *
 * Required environment:
 *   CLIENTVERSE_API_BASE, CLIENTVERSE_ADMIN_EMAIL, CLIENTVERSE_ADMIN_PASSWORD
 * Optional:
 *   CLIENTVERSE_CRON_SECRET   — exercises the worker tick and detection cron
 *   CLIENTVERSE_EVIDENCE_PATH — writes sanitized evidence JSON
 */

import fs from 'node:fs'
import path from 'node:path'

const PREFIX = 'OPERATIONS-SMOKE'

function required(name) {
  const value = process.env[name]
  if (!value) throw new Error(`${name} is required`)
  return value
}

const apiBase = (() => {
  const raw = required('CLIENTVERSE_API_BASE').replace(/\/$/, '')
  return raw.endsWith('/api') ? raw : `${raw}/api`
})()
const adminEmail = required('CLIENTVERSE_ADMIN_EMAIL')
const adminPassword = required('CLIENTVERSE_ADMIN_PASSWORD')
const cronSecret = process.env.CLIENTVERSE_CRON_SECRET || ''
const evidencePath = process.env.CLIENTVERSE_EVIDENCE_PATH

const evidence = { generated_at: new Date().toISOString(), steps: {}, failures: [] }

async function call(pathname, { method = 'GET', token = null, body = null, headers = {} } = {}) {
  const init = { method, headers: { ...headers } }
  if (token) init.headers.Authorization = `Bearer ${token}`
  if (body !== null) {
    init.headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }
  const response = await fetch(`${apiBase}${pathname}`, init)
  const parsed = await response.json().catch(() => ({}))
  return { status: response.status, body: parsed }
}

function record(name, value) {
  evidence.steps[name] = value
  return value
}

function check(name, condition, detail) {
  if (!condition) evidence.failures.push({ check: name, detail: detail ?? null })
  return condition
}

function daysAgo(days) {
  return new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString()
}

async function main() {
  // ---- authentication -------------------------------------------------------
  const login = await call('/auth/login', { method: 'POST', body: { email: adminEmail, password: adminPassword } })
  const adminToken = login.body.token || login.body.access_token
  record('admin_login_http', login.status)
  check('admin_login', login.status === 200 && !!adminToken)
  if (!adminToken) throw new Error('Administrator login failed; cannot continue')

  // A second, independent tenant for the isolation assertions.
  const otherEmail = `operations-smoke-${Date.now()}@example.com`
  const register = await call('/auth/register', {
    method: 'POST',
    body: { email: otherEmail, password: 'OperationsSmoke2026!', name: `${PREFIX} Isolation User` },
  })
  const otherToken = register.body.token || register.body.access_token
  record('second_tenant_register_http', register.status)
  check('second_tenant_register', register.status === 200 && !!otherToken)

  // ---- seed a recoverable condition ----------------------------------------
  const company = await call('/companies', {
    method: 'POST', token: adminToken,
    body: { name: `${PREFIX} Recovery Co`, industry: 'Testing', website: 'operations-smoke.example', tier: 'growth' },
  })
  const opportunity = await call('/opportunities', {
    method: 'POST', token: adminToken,
    body: { title: `${PREFIX} Dormant renewal`, company_id: company.body.id, value: 24000, stage: 'proposal' },
  })
  record('seed_company_http', company.status)
  record('seed_opportunity_http', opportunity.status)

  const commitment = await call('/commitments', {
    method: 'POST', token: adminToken,
    body: {
      title: `${PREFIX} Overdue follow-up`,
      workspace_id: null,
      due_date: daysAgo(6),
      owner: adminEmail,
    },
  })
  record('seed_commitment_http', commitment.status)

  // ---- Second Chance detection ---------------------------------------------
  const detect = await call('/second-chance/detect', { method: 'POST', token: adminToken })
  record('detection_http', detect.status)
  record('detection_summary', detect.body)
  check('detection_runs', detect.status === 200)
  check('detection_reports_thresholds', !!detect.body?.thresholds?.stalled_lead_days)

  // Running detection twice must deduplicate rather than pile up duplicates.
  const detectAgain = await call('/second-chance/detect', { method: 'POST', token: adminToken })
  record('detection_repeat_created', detectAgain.body?.work_items_created)
  record('detection_repeat_deduplicated', detectAgain.body?.work_items_deduplicated)
  check('detection_is_deduplicated',
        (detectAgain.body?.work_items_created ?? 1) === 0 ||
        (detectAgain.body?.work_items_deduplicated ?? 0) > 0,
        detectAgain.body)

  const queue = await call('/work-queue?status=open&limit=100', { token: adminToken })
  record('work_queue_http', queue.status)
  record('work_queue_open_items', Array.isArray(queue.body) ? queue.body.length : null)
  const candidate = (queue.body || []).find((item) => String(item.type).startsWith('second_chance.'))
  check('work_queue_has_recovery_candidate', !!candidate)
  if (candidate) {
    check('candidate_has_explainable_reason', !!candidate.payload?.reason, candidate.payload)
    check('candidate_has_source_reference', !!candidate.source_ref, candidate.source_ref)
    record('candidate_type', candidate.type)
  }

  const stats = await call('/work-queue/stats', { token: adminToken })
  record('work_queue_stats', stats.body)
  check('work_queue_stats_shape', stats.status === 200 && 'dead_letter' in (stats.body || {}))

  // ---- Next Best Action ------------------------------------------------------
  const generate = await call('/next-best-actions/generate', { method: 'POST', token: adminToken })
  record('nba_generate_http', generate.status)
  record('nba_generate_summary', generate.body)
  check('nba_generates', generate.status === 200)

  const recommendations = await call('/next-best-actions?state=open&limit=50', { token: adminToken })
  record('nba_open_count', Array.isArray(recommendations.body) ? recommendations.body.length : null)
  const recommendation = (recommendations.body || [])[0]
  check('nba_returns_recommendations', !!recommendation)
  if (recommendation) {
    check('nba_has_reason', !!recommendation.reason)
    check('nba_has_source_refs', (recommendation.source_refs || []).length > 0)
    check('nba_has_no_fabricated_confidence', !('confidence' in recommendation))
    record('nba_priority_ordering_is_ascending',
           (recommendations.body || []).every((item, index, all) =>
             index === 0 || all[index - 1].priority <= item.priority))

    const accepted = await call(`/next-best-actions/${recommendation.id}`, {
      method: 'PATCH', token: adminToken, body: { state: 'accepted' },
    })
    record('nba_feedback_http', accepted.status)
    check('nba_feedback_persists', accepted.status === 200 && accepted.body?.state === 'accepted')
  }

  // ---- security gate ---------------------------------------------------------
  const gateStatus = await call('/security-gate/status', { token: adminToken })
  record('security_gate_status', gateStatus.body)
  check('security_gate_declares_two_gates', (gateStatus.body?.gates || []).length === 2)
  check('security_gate_lists_all_three_scanners', (gateStatus.body?.scanners || []).length === 3)

  const componentPayload = {
    name: `${PREFIX} example external skill`,
    kind: 'skill',
    source_url: `https://github.com/example/${PREFIX.toLowerCase()}-${Date.now()}`,
    version: '1.0.0',
  }
  const registered = await call('/security-gate/components', {
    method: 'POST', token: adminToken, body: componentPayload,
  })
  record('security_gate_register_http', registered.status)
  check('registration_grants_nothing', registered.body?.state === 'DISCOVERED', registered.body?.state)

  const approveAttempt = await call(`/security-gate/components/${registered.body?.id}/decision`, {
    method: 'POST', token: adminToken,
    body: { decision: 'APPROVED', rationale: 'smoke check — must be refused' },
  })
  record('security_gate_premature_approval_http', approveAttempt.status)
  check('premature_approval_is_refused', approveAttempt.status >= 400, approveAttempt.body)

  // ---- tenant isolation ------------------------------------------------------
  if (otherToken && candidate) {
    const crossRead = await call(`/work-queue/${candidate.id}`, { token: otherToken })
    record('cross_tenant_work_item_http', crossRead.status)
    check('cross_tenant_work_item_denied', crossRead.status === 404, crossRead.status)
  }
  if (otherToken && recommendation) {
    const crossPatch = await call(`/next-best-actions/${recommendation.id}`, {
      method: 'PATCH', token: otherToken, body: { state: 'dismissed' },
    })
    record('cross_tenant_recommendation_patch_http', crossPatch.status)
    check('cross_tenant_recommendation_denied', crossPatch.status === 404, crossPatch.status)
  }
  if (otherToken && registered.body?.id) {
    const crossComponent = await call(`/security-gate/components/${registered.body.id}`, { token: otherToken })
    record('cross_tenant_component_http', crossComponent.status)
    check('cross_tenant_component_denied', crossComponent.status === 404, crossComponent.status)
  }

  // ---- scheduled work --------------------------------------------------------
  const unauthenticatedCron = await call('/cron/work-queue', { method: 'POST' })
  record('cron_unauthenticated_http', unauthenticatedCron.status)
  check('cron_requires_authentication', unauthenticatedCron.status === 401)

  if (cronSecret) {
    const sweep = await call('/cron/second-chance', {
      method: 'POST', headers: { Authorization: `Bearer ${cronSecret}`, 'X-Webhook-Id': `${PREFIX}-sweep-${Date.now()}` },
    })
    record('cron_second_chance_http', sweep.status)
    check('cron_second_chance_accepted', sweep.status === 200 && sweep.body?.accepted === true)

    // The sweep acknowledges immediately and runs in the background, so give it time to
    // enqueue its durable follow-up jobs before the worker tick looks for them.
    await new Promise((resolve) => setTimeout(resolve, 5000))

    const runId = `${PREFIX}-tick-${Date.now()}`
    const tick = await call('/cron/work-queue', {
      method: 'POST', headers: { Authorization: `Bearer ${cronSecret}`, 'X-Webhook-Id': runId },
    })
    record('cron_work_queue_http', tick.status)
    check('cron_work_queue_accepted', tick.status === 200 && tick.body?.accepted === true)

    const duplicate = await call('/cron/work-queue', {
      method: 'POST', headers: { Authorization: `Bearer ${cronSecret}`, 'X-Webhook-Id': runId },
    })
    record('cron_duplicate_suppressed', duplicate.body?.duplicate === true)
    check('cron_is_idempotent', duplicate.body?.duplicate === true, duplicate.body)

    // Each tick is bounded and rotates across tenants, so this tenant's job may not be
    // claimed on the first pass. Drive the worker the way a scheduler would — repeated
    // ticks — and assert the job is durably completed rather than lost.
    let completedSystemJobs = 0
    let ticksUsed = 0
    for (let attempt = 0; attempt < 10 && completedSystemJobs === 0; attempt += 1) {
      ticksUsed += 1
      await call('/cron/work-queue', {
        method: 'POST',
        headers: { Authorization: `Bearer ${cronSecret}`, 'X-Webhook-Id': `${PREFIX}-tick-${Date.now()}-${attempt}` },
      })
      await new Promise((resolve) => setTimeout(resolve, 3000))
      const systemQueue = await call('/work-queue?status=completed&queue=system&limit=20', { token: adminToken })
      completedSystemJobs = Array.isArray(systemQueue.body) ? systemQueue.body.length : 0
    }
    record('worker_ticks_used', ticksUsed)
    record('system_jobs_completed', completedSystemJobs)
    check('worker_tick_processed_a_system_job', completedSystemJobs > 0,
          'the durable worker tick should have completed the queued recommendation refresh')

  } else {
    record('cron_secret_supplied', false)
  }

  evidence.cleanup_note =
    `This run creates explicitly named ${PREFIX} records (company, opportunity, commitment, ` +
    'work items, recommendations, and one external-component registration) plus an isolated ' +
    'second tenant. Remove them after retaining the approved evidence.'
  evidence.secret_redaction =
    'This evidence intentionally omits account identities, passwords, session tokens, database ' +
    'credentials, provider values, and internal record identifiers.'
  evidence.result = evidence.failures.length === 0 ? 'PASS' : 'FAIL'

  const output = JSON.stringify(evidence, null, 2)
  console.log(output)
  if (evidencePath) {
    fs.mkdirSync(path.dirname(evidencePath), { recursive: true })
    fs.writeFileSync(evidencePath, `${output}\n`)
  }
  if (evidence.failures.length) {
    console.error(`FAILED CHECKS: ${evidence.failures.map((f) => f.check).join(', ')}`)
    process.exit(1)
  }
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
