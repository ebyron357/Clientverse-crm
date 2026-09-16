/**
 * Operations smoke — durable work queue, Second Chance detection, recovery strategy
 * composition, the approval queue, conversations and communication messages, Next Best
 * Action, and the external-component security gate, verified end to end against a running
 * deployment.
 *
 * Companion to proof_of_life.mjs, with one important difference: every record this
 * script creates lives in a disposable tenant it registers for the run. The API has no
 * delete endpoints, so seeding into the operator's tenant would leave fabricated
 * recovery work and recommendations behind permanently. Working in a throwaway tenant
 * also means every assertion runs against data this run created — there is no
 * pre-existing data that could make a broken check look green.
 *
 * No secret values are printed. Every assertion records an observed HTTP result rather
 * than an assumption.
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

/**
 * Register a disposable tenant. A newly registered user is an admin of its own tenant,
 * so this token can exercise the admin-only routes without touching operator data.
 */
async function disposableTenant(label) {
  const email = `operations-smoke-${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`
  const response = await call('/auth/register', {
    method: 'POST',
    body: { email, password: 'OperationsSmoke2026!', name: `${PREFIX} ${label}` },
  })
  const token = response.body.token || response.body.access_token
  record(`${label}_tenant_register_http`, response.status)
  check(`${label}_tenant_registered`, response.status === 200 && !!token)
  return token
}

function assertCreated(name, response) {
  const id = response.body?.id
  record(`${name}_http`, response.status)
  const ok = response.status === 200 && !!id
  check(`${name}_created`, ok, ok ? null : response.body)
  if (!ok) {
    throw new Error(`${name} could not be seeded (HTTP ${response.status}); refusing to ` +
      'assert against data this run did not create')
  }
  return id
}

async function main() {
  // ---- the deployment's own administrator still has to work ------------------
  const login = await call('/auth/login', {
    method: 'POST', body: { email: adminEmail, password: adminPassword },
  })
  record('admin_login_http', login.status)
  check('admin_login', login.status === 200 && !!(login.body.token || login.body.access_token))

  // ---- everything else happens in disposable tenants -------------------------
  const token = await disposableTenant('primary')
  const otherToken = await disposableTenant('isolation')
  if (!token) throw new Error('Could not register the disposable tenant; cannot continue')

  // A brand-new tenant starts empty. Proving that makes every later assertion
  // unambiguous: anything found afterwards was created by this run.
  const initialQueue = await call('/work-queue?status=&limit=50', { token })
  const initialRecommendations = await call('/next-best-actions?state=&limit=50', { token })
  const startsEmpty = (initialQueue.body || []).length === 0 &&
                      (initialRecommendations.body || []).length === 0
  record('tenant_starts_empty', startsEmpty)
  check('disposable_tenant_starts_empty', startsEmpty,
        {queue: (initialQueue.body || []).length,
         recommendations: (initialRecommendations.body || []).length})

  // ---- seed a recoverable condition ------------------------------------------
  // Every seed is asserted. An earlier revision only recorded status codes; two seeds
  // were silently rejected with 422 and the run still passed by matching pre-existing
  // data — exactly the false green this harness exists to prevent.
  const company = await call('/companies', {
    method: 'POST', token,
    body: { name: `${PREFIX} Recovery Co`, industry: 'Testing', website: 'operations-smoke.example', tier: 'growth' },
  })
  const companyId = assertCreated('seed_company', company)

  // `OppInput` takes `name`, not `title`.
  const opportunity = await call('/opportunities', {
    method: 'POST', token,
    body: { name: `${PREFIX} Dormant renewal`, company_id: companyId, value: 24000, stage: 'proposal' },
  })
  const opportunityId = assertCreated('seed_opportunity', opportunity)

  // `CommitmentInput.workspace_id` is required and is validated against the tenant.
  const workspace = await call('/workspaces', {
    method: 'POST', token,
    body: { name: `${PREFIX} Recovery workspace`, company_id: companyId, stage: 'onboarding' },
  })
  const workspaceId = assertCreated('seed_workspace', workspace)

  const commitment = await call('/commitments', {
    method: 'POST', token,
    body: {
      title: `${PREFIX} Overdue follow-up`,
      workspace_id: workspaceId,
      due_date: daysAgo(6),
      owner: adminEmail,
    },
  })
  const commitmentId = assertCreated('seed_commitment', commitment)
  const seededRefs = new Set([`opportunity:${opportunityId}`, `commitment:${commitmentId}`])

  // ---- Second Chance detection ------------------------------------------------
  const detect = await call('/second-chance/detect', { method: 'POST', token })
  record('detection_http', detect.status)
  record('detection_summary', detect.body)
  check('detection_runs', detect.status === 200, detect.body)
  check('detection_reports_thresholds', !!detect.body?.thresholds?.stalled_lead_days)
  // The overdue commitment was created by this run, so detection must find it.
  check('detection_found_the_seeded_missed_followup',
        (detect.body?.missed_followups_detected ?? 0) >= 1, detect.body)
  check('detection_created_work', (detect.body?.work_items_created ?? 0) >= 1, detect.body)

  const detectAgain = await call('/second-chance/detect', { method: 'POST', token })
  record('detection_repeat_created', detectAgain.body?.work_items_created)
  record('detection_repeat_deduplicated', detectAgain.body?.work_items_deduplicated)
  check('detection_is_deduplicated',
        (detectAgain.body?.work_items_created ?? 1) === 0 &&
        (detectAgain.body?.work_items_deduplicated ?? 0) >= 1,
        detectAgain.body)

  const queue = await call('/work-queue?status=open&limit=100', { token })
  record('work_queue_http', queue.status)
  record('work_queue_open_items', Array.isArray(queue.body) ? queue.body.length : null)
  const candidate = (queue.body || []).find((item) => seededRefs.has(item.source_ref))
  check('work_queue_has_recovery_candidate_from_this_run', !!candidate,
        {seeded: [...seededRefs], seen: (queue.body || []).map((i) => i.source_ref)})
  if (candidate) {
    check('candidate_has_explainable_reason', !!candidate.payload?.reason, candidate.payload)
    check('candidate_has_source_reference', !!candidate.source_ref, candidate.source_ref)
    record('candidate_type', candidate.type)
  }

  // Coverage boundary, stated rather than implied: the API does not let a client set
  // an opportunity's activity timestamps, so a freshly seeded opportunity can never be
  // stale enough to trigger the stalled-lead rule. This run therefore exercises the
  // missed-follow-up lane end to end; the stalled-lead rule is covered by
  // backend/tests/test_second_chance.py against backdated records.
  record('stalled_lead_lane_exercised_here', false)
  record('stalled_lead_lane_covered_by', 'backend/tests/test_second_chance.py')

  const stats = await call('/work-queue/stats', { token })
  record('work_queue_stats', stats.body)
  check('work_queue_stats_shape', stats.status === 200 && 'dead_letter' in (stats.body || {}))

  // ---- Next Best Action --------------------------------------------------------
  const generate = await call('/next-best-actions/generate', { method: 'POST', token })
  record('nba_generate_http', generate.status)
  record('nba_generate_summary', generate.body)
  check('nba_generates', generate.status === 200)
  check('nba_reports_no_failed_rules', (generate.body?.failed_rules || []).length === 0,
        generate.body?.failed_rules)

  const recommendations = await call('/next-best-actions?state=open&limit=50', { token })
  record('nba_open_count', Array.isArray(recommendations.body) ? recommendations.body.length : null)
  const recommendation = (recommendations.body || [])[0]
  check('nba_returns_recommendations', !!recommendation)
  if (recommendation) {
    check('nba_has_reason', !!recommendation.reason)
    check('nba_has_source_refs', (recommendation.source_refs || []).length > 0)
    check('nba_has_no_fabricated_confidence', !('confidence' in recommendation))
    const ordered = (recommendations.body || []).every((item, index, all) =>
      index === 0 || all[index - 1].priority <= item.priority)
    record('nba_priority_ordering_is_ascending', ordered)
    check('nba_is_priority_ordered', ordered)

    const accepted = await call(`/next-best-actions/${recommendation.id}`, {
      method: 'PATCH', token, body: { state: 'accepted' },
    })
    record('nba_feedback_http', accepted.status)
    check('nba_feedback_persists', accepted.status === 200 && accepted.body?.state === 'accepted')
  }

  // ---- recovery strategy composition -------------------------------------------
  // The candidate detected above must turn into a strategy that cites its facts and
  // refuses to mark any outbound step ready while no channel is authorised.
  const authority = await call('/recovery-strategies/channel-authority', { token })
  record('channel_authority_http', authority.status)
  record('channel_authority', authority.body)
  check('internal_channel_is_available', authority.body?.internal?.authorized === true)
  check('no_outbound_channel_is_authorized_for_a_new_tenant',
        ['email', 'sms', 'phone'].every((channel) => authority.body?.[channel]?.authorized === false),
        'a fresh tenant has no certified provider, so nothing may be sent')

  const composed = await call('/recovery-strategies/compose', { method: 'POST', token })
  record('compose_http', composed.status)
  record('compose_summary', composed.body)
  check('composer_runs', composed.status === 200)
  check('composer_produces_a_strategy_for_this_runs_candidate',
        (composed.body?.strategies_composed || 0) >= 1,
        'detection queued a candidate, so composition must produce a strategy')
  check('composer_reports_no_errors', (composed.body?.errors || []).length === 0)

  const strategies = await call('/recovery-strategies?state=proposed', { token })
  const strategy = Array.isArray(strategies.body) ? strategies.body[0] : null
  record('proposed_strategy_count', Array.isArray(strategies.body) ? strategies.body.length : null)
  check('proposed_strategies_are_listed', !!strategy)
  if (strategy) {
    record('strategy_lane', strategy.lane)
    record('strategy_rule', strategy.rule)
    check('strategy_names_its_rule', !!strategy.rule && !!strategy.rationale)
    check('strategy_cites_facts_to_a_record',
          (strategy.facts || []).length > 0 && (strategy.facts || []).every((f) => 'source' in f))
    check('strategy_has_no_fabricated_confidence',
          !('confidence' in strategy) && !('score' in strategy))
    const steps = strategy.steps || []
    check('strategy_has_steps', steps.length > 0)
    check('every_outbound_step_is_blocked_with_a_reason',
          steps.filter((s) => s.channel !== 'internal')
               .every((s) => s.status === 'blocked' && !!s.blocked_reason),
          'no channel is authorised, so no outbound step may read as ready')
    check('internal_steps_are_ready',
          steps.filter((s) => s.channel === 'internal').every((s) => s.status === 'ready'))
  }

  // ---- approval queue ------------------------------------------------------------
  // Composition must raise an approval, and approving a blocked action must not make it
  // executable. That second assertion is the whole point of the gate.
  const queuedApprovals = await call('/approval-queue?kind=recovery_strategy', { token })
  const strategyApproval = Array.isArray(queuedApprovals.body) ? queuedApprovals.body[0] : null
  record('strategy_approval_count', Array.isArray(queuedApprovals.body) ? queuedApprovals.body.length : null)
  check('composition_raises_an_approval_request', !!strategyApproval)
  if (strategyApproval) {
    check('approval_records_that_an_agent_raised_it',
          strategyApproval.requester_kind === 'agent')
    check('approval_binds_to_the_strategy_it_authorises',
          strategyApproval.action?.strategy_id === strategy?.id)
    check('approval_carries_its_blocks', (strategyApproval.blocked_reasons || []).length > 0)
    check('approval_expires', !!strategyApproval.expires_at)
  }

  const raised = await call('/approval-queue', {
    method: 'POST', token,
    body: { title: `${PREFIX} approval ${Date.now()}`, kind: 'external_effect', risk: 'high' },
  })
  record('approval_raise_http', raised.status)
  check('an_approval_can_be_raised', raised.status === 200 && raised.body?.status === 'requested')
  if (raised.body?.id) {
    const decided = await call(`/approval-queue/${raised.body.id}/decision`, {
      method: 'POST', token, body: { decision: 'approved', rationale: `${PREFIX} smoke` },
    })
    record('approval_decision_http', decided.status)
    check('an_approval_can_be_decided',
          decided.status === 200 && decided.body?.status === 'approved' && !!decided.body?.decided_by)

    const again = await call(`/approval-queue/${raised.body.id}/decision`, {
      method: 'POST', token, body: { decision: 'rejected' },
    })
    record('approval_second_decision_http', again.status)
    check('a_decided_approval_cannot_be_decided_again', again.status === 409,
          'an approval decided twice is not a gate')
  }

  const approvalSummary = await call('/approval-queue/summary', { token })
  record('approval_summary', approvalSummary.body)
  check('approval_summary_counts_blocked_requests',
        (approvalSummary.body?.awaiting_decision_blocked || 0) >= 1)

  // ---- conversations and communication messages ---------------------------------
  // The point of this section is what does NOT happen. A message can be drafted and
  // approved, and it still cannot be sent, because approval does not authorise a channel.
  const thread = await call('/conversations', {
    method: 'POST', token,
    body: {
      channel: 'email',
      subject: `${PREFIX} thread ${Date.now()}`,
      participants: [{ kind: 'contact', id: 'con_smoke', address: 'client@example.invalid' }],
    },
  })
  record('conversation_create_http', thread.status)
  check('a_conversation_can_be_created', thread.status === 200 && !!thread.body?.id)
  check('a_new_conversation_has_no_consent', thread.body?.consent?.state === 'unknown',
        'no record must mean no permission, never assumed permission')

  const conversationSummary = await call('/conversations/summary', { token })
  record('conversation_providers', conversationSummary.body?.providers)
  check('no_delivery_provider_is_registered',
        (conversationSummary.body?.providers || []).every((p) => p.registered === false),
        'no channel adapter has been built or certified')

  if (thread.body?.id) {
    const drafted = await call(`/conversations/${thread.body.id}/messages`, {
      method: 'POST', token, body: { body: `${PREFIX} draft body`, to_address: 'client@example.invalid' },
    })
    record('message_draft_http', drafted.status)
    check('a_message_can_be_drafted', drafted.status === 200 && drafted.body?.status === 'draft',
          'composing is not sending, so drafting must never require a channel')

    const premature = await call(`/messages/${drafted.body?.id}/send`, { method: 'POST', token })
    record('message_send_draft_http', premature.status)
    check('a_draft_cannot_be_sent', premature.status === 409)

    const requested = await call(`/messages/${drafted.body?.id}/request-approval`, {
      method: 'POST', token, body: {},
    })
    record('message_approval_request_http', requested.status)
    check('a_message_raises_an_approval', requested.status === 200 && !!requested.body?.approval_id)

    const messageApproval = await call(`/approval-queue/${requested.body?.approval_id}`, { token })
    record('message_approval_blocks', messageApproval.body?.blocked_reasons)
    check('the_operator_can_see_what_still_blocks_the_send',
          (messageApproval.body?.blocked_reasons || []).length > 0)

    const approvedMessage = await call(`/approval-queue/${requested.body?.approval_id}/decision`, {
      method: 'POST', token, body: { decision: 'approved', rationale: `${PREFIX} smoke` },
    })
    record('message_approval_decision_http', approvedMessage.status)
    check('the_message_approval_can_be_decided', approvedMessage.status === 200)

    const afterApproval = await call(`/messages/${drafted.body?.id}`, { token })
    record('message_state_after_approval', afterApproval.body?.status)
    check('approval_promotes_the_message', afterApproval.body?.status === 'approved',
          'the decision hook must move the message, not leave the two records disagreeing')

    const refused = await call(`/messages/${drafted.body?.id}/send`, { method: 'POST', token })
    record('message_send_after_approval_http', refused.status)
    record('message_send_refusal_reason', refused.body?.detail?.reason)
    check('an_approved_message_is_still_refused_with_no_channel',
          refused.status === 409 && refused.body?.detail?.reason === 'channel_not_authorized',
          'approving an action does not authorise a channel')

    const consentWithoutBasis = await call(`/conversations/${thread.body.id}/consent`, {
      method: 'POST', token, body: { state: 'granted' },
    })
    record('consent_without_basis_http', consentWithoutBasis.status)
    check('consent_granted_requires_a_stated_basis', consentWithoutBasis.status === 400)

    const handoff = await call(`/conversations/${thread.body.id}/handoff`, {
      method: 'POST', token, body: { to: 'agent', reason: `${PREFIX} smoke` },
    })
    record('conversation_handoff_http', handoff.status)
    check('the_agent_human_boundary_is_recordable',
          handoff.status === 200 && handoff.body?.handled_by === 'agent')
  }

  // ---- security gate -----------------------------------------------------------
  const gateStatus = await call('/security-gate/status', { token })
  record('security_gate_status', gateStatus.body)
  check('security_gate_declares_two_gates', (gateStatus.body?.gates || []).length === 2)
  check('security_gate_lists_all_three_scanners', (gateStatus.body?.scanners || []).length === 3)

  const sourceUrl = `https://github.com/example/${PREFIX.toLowerCase()}-${Date.now()}`
  const registered = await call('/security-gate/components', {
    method: 'POST', token,
    body: { name: `${PREFIX} example external skill`, kind: 'skill', source_url: sourceUrl,
            version: '1.0.0', digest: 'sha256:aaa' },
  })
  const componentId = assertCreated('security_gate_register', registered)
  check('registration_grants_nothing', registered.body?.state === 'DISCOVERED', registered.body?.state)

  const approveAttempt = await call(`/security-gate/components/${componentId}/decision`, {
    method: 'POST', token,
    body: { decision: 'APPROVED', rationale: 'smoke check — must be refused' },
  })
  record('security_gate_premature_approval_http', approveAttempt.status)
  check('premature_approval_is_refused', approveAttempt.status >= 400, approveAttempt.body)

  // Republished content under the same version must not inherit the record.
  const republished = await call('/security-gate/components', {
    method: 'POST', token,
    body: { name: `${PREFIX} example external skill`, kind: 'skill', source_url: sourceUrl,
            version: '1.0.0', digest: 'sha256:bbb' },
  })
  record('security_gate_digest_change_http', republished.status)
  check('digest_change_is_rejected', republished.status >= 400, republished.body)

  // ---- tenant isolation --------------------------------------------------------
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
  if (otherToken && componentId) {
    const crossComponent = await call(`/security-gate/components/${componentId}`, { token: otherToken })
    record('cross_tenant_component_http', crossComponent.status)
    check('cross_tenant_component_denied', crossComponent.status === 404, crossComponent.status)
  }

  // ---- scheduled work ----------------------------------------------------------
  const unauthenticatedCron = await call('/cron/work-queue', { method: 'POST' })
  record('cron_unauthenticated_http', unauthenticatedCron.status)
  check('cron_requires_authentication', unauthenticatedCron.status === 401)

  if (cronSecret) {
    const sweep = await call('/cron/second-chance', {
      method: 'POST',
      headers: { Authorization: `Bearer ${cronSecret}`, 'X-Webhook-Id': `${PREFIX}-sweep-${Date.now()}` },
    })
    record('cron_second_chance_http', sweep.status)
    check('cron_second_chance_accepted', sweep.status === 200 && sweep.body?.accepted === true)

    // The sweep acknowledges immediately and runs in the background.
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

    // Track the specific job queued for this tenant. Counting completed system jobs
    // would also count work finished before this run, which proves nothing.
    const systemQueue = await call('/work-queue?status=&queue=system&limit=50', { token })
    const targetJob = (systemQueue.body || [])
      .find((item) => item.type === 'next_best_action.generate')
    record('system_job_queued', !!targetJob)
    check('sweep_queued_a_durable_refresh_job', !!targetJob,
          'the sweep should queue a recommendation refresh on the durable queue')

    let ticksUsed = 0
    let jobState = targetJob?.status ?? null
    if (targetJob) {
      // Each tick is bounded and rotates across tenants, so this tenant's job may not
      // be claimed on the first pass. Drive the worker the way a scheduler would.
      for (let attempt = 0; attempt < 10 && jobState !== 'completed'; attempt += 1) {
        ticksUsed += 1
        await call('/cron/work-queue', {
          method: 'POST',
          headers: { Authorization: `Bearer ${cronSecret}`, 'X-Webhook-Id': `${PREFIX}-tick-${Date.now()}-${attempt}` },
        })
        await new Promise((resolve) => setTimeout(resolve, 3000))
        const refreshed = await call(`/work-queue/${targetJob.id}`, { token })
        jobState = refreshed.body?.status ?? jobState
      }
    }
    record('worker_ticks_used', ticksUsed)
    record('tracked_system_job_state', jobState)
    check('worker_tick_completed_this_runs_system_job', jobState === 'completed',
          `last observed state: ${jobState}`)
  } else {
    record('cron_secret_supplied', false)
  }

  evidence.cleanup_note =
    'Every record this run created lives in disposable tenants registered for the run, so ' +
    "nothing is written into an operator's tenant. The API exposes no delete endpoints, so " +
    'those tenants and their records remain until an operator removes them; they are inert ' +
    'and isolated by the same tenancy boundary this run asserts.'
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
  evidence.result = 'FAIL'
  evidence.fatal_error = String(error).slice(0, 500)
  if (evidencePath) {
    try {
      fs.mkdirSync(path.dirname(evidencePath), { recursive: true })
      fs.writeFileSync(evidencePath, `${JSON.stringify(evidence, null, 2)}\n`)
    } catch { /* evidence capture is best effort once the run has already failed */ }
  }
  process.exit(1)
})
