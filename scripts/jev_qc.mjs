// Jev QC Central Verification Gate submitter.
//
// Claude Code (or any worker) submits completed work plus concrete evidence to the
// production n8n "Jev QC Central Verification Gate", which relays to TypeSafe Jev and
// returns a QC decision. This script is the ONLY supported path: never call TypeSafe
// directly and never handle a TypeSafe API key.
//
// Usage:
//   node scripts/jev_qc.mjs <payload.json>    # payload file
//   node scripts/jev_qc.mjs -                 # payload on stdin
//
// Exit codes: 0 VERIFIED_COMPLETE, 1 INCOMPLETE, 2 NEEDS_HUMAN_REVIEW, 3 gate error.
// The gate fails CLOSED: anything that is not an explicit VERIFIED_COMPLETE means the
// work must NOT be reported as verified complete.

import fs from 'node:fs'
import path from 'node:path'

const DEFAULT_WEBHOOK_URL = 'https://bwa357.app.n8n.cloud/webhook/jev-qc-central-gate'
const NO_EVIDENCE = 'No evidence supplied.'
const EVIDENCE_FIELDS = ['implementation', 'tests', 'build', 'deployment', 'verification']
const KNOWN_STATUSES = ['VERIFIED_COMPLETE', 'INCOMPLETE', 'NEEDS_HUMAN_REVIEW']
const EXIT_CODES = { VERIFIED_COMPLETE: 0, INCOMPLETE: 1, NEEDS_HUMAN_REVIEW: 2, GATE_ERROR: 3 }
const BANNERS = {
  VERIFIED_COMPLETE: 'QC VERIFIED COMPLETE',
  INCOMPLETE: 'QC INCOMPLETE',
  NEEDS_HUMAN_REVIEW: 'QC NEEDS HUMAN REVIEW',
  GATE_ERROR: 'QC GATE ERROR — FAIL CLOSED',
}

// The endpoint is configuration, not a secret: it may be overridden per environment.
const webhookUrl = (process.env.JEV_QC_WEBHOOK_URL || DEFAULT_WEBHOOK_URL).trim()
const timeoutMs = Number(process.env.JEV_QC_TIMEOUT_MS || 120000)
const evidencePath = process.env.JEV_QC_EVIDENCE_PATH

function readSource(source) {
  if (!source) throw new Error('usage: node scripts/jev_qc.mjs <payload.json | ->')
  return fs.readFileSync(source === '-' ? 0 : source, 'utf8')
}

function text(value) {
  return typeof value === 'string' ? value.trim() : ''
}

// Evidence rule: never fabricate. Anything absent or blank is submitted verbatim as
// "No evidence supplied." so Jev scores the gap instead of an invented artifact.
function normalize(raw) {
  const taskId = text(raw.task_id)
  const task = text(raw.task)
  if (!taskId) throw new Error('payload.task_id is required')
  if (!task) throw new Error('payload.task is required')

  const requirements = (Array.isArray(raw.completion_requirements) ? raw.completion_requirements : [])
    .map(text)
    .filter(Boolean)
  if (requirements.length === 0) throw new Error('payload.completion_requirements must list at least one requirement')

  const suppliedEvidence = raw.evidence && typeof raw.evidence === 'object' ? raw.evidence : {}
  const evidence = {}
  for (const field of EVIDENCE_FIELDS) evidence[field] = text(suppliedEvidence[field]) || NO_EVIDENCE

  return {
    task_id: taskId,
    task,
    worker: text(raw.worker) || 'Claude Code',
    worker_claim: text(raw.worker_claim) || 'Task complete.',
    completion_requirements: requirements,
    evidence,
  }
}

async function submit(payload) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(webhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
    return { http_status: response.status, raw: await response.text() }
  } finally {
    clearTimeout(timer)
  }
}

// n8n may answer with the decision object, a single-item array, or the decision nested
// under a wrapper key. Unwrap defensively, but never rename gate fields.
function decisionFrom(parsed) {
  const seen = new Set()
  const queue = [parsed]
  while (queue.length > 0) {
    const node = queue.shift()
    if (!node || typeof node !== 'object' || seen.has(node)) continue
    seen.add(node)
    if (Array.isArray(node)) {
      queue.push(...node)
      continue
    }
    if (typeof node.qc_status === 'string') return node
    for (const value of Object.values(node)) {
      if (value && typeof value === 'object') queue.push(value)
    }
  }
  return null
}

function findExecutionId(parsed, decision) {
  if (decision && decision.n8n_execution_id !== undefined) return decision.n8n_execution_id
  const seen = new Set()
  const queue = [parsed]
  while (queue.length > 0) {
    const node = queue.shift()
    if (!node || typeof node !== 'object' || seen.has(node)) continue
    seen.add(node)
    if (!Array.isArray(node) && node.n8n_execution_id !== undefined) return node.n8n_execution_id
    for (const value of Object.values(node)) {
      if (value && typeof value === 'object') queue.push(value)
    }
  }
  return null
}

function interpret(result) {
  if (result.http_status < 200 || result.http_status >= 300) {
    return { status: 'GATE_ERROR', gate_error: `gate returned HTTP ${result.http_status}` }
  }

  let parsed
  try {
    parsed = JSON.parse(result.raw)
  } catch {
    return { status: 'GATE_ERROR', gate_error: 'gate returned invalid JSON' }
  }

  const decision = decisionFrom(parsed)
  if (!decision) return { status: 'GATE_ERROR', gate_error: 'gate response contained no qc_status' }

  const qcStatus = decision.qc_status
  if (!KNOWN_STATUSES.includes(qcStatus)) {
    return { status: 'GATE_ERROR', gate_error: `gate returned unknown qc_status ${JSON.stringify(qcStatus)}`, parsed, decision }
  }

  return { status: qcStatus, parsed, decision, n8n_execution_id: findExecutionId(parsed, decision) }
}

const payload = normalize(JSON.parse(readSource(process.argv[2])))

let outcome
try {
  outcome = interpret(await submit(payload))
} catch (error) {
  const reason = error.name === 'AbortError' ? `gate did not respond within ${timeoutMs}ms` : `gate unreachable: ${error.message}`
  outcome = { status: 'GATE_ERROR', gate_error: reason }
}

const record = {
  submitted_at: new Date().toISOString(),
  webhook_url: webhookUrl,
  request: payload,
  verdict: outcome.status,
  verified_complete: outcome.status === 'VERIFIED_COMPLETE',
  n8n_execution_id: outcome.n8n_execution_id ?? null,
  gate_error: outcome.gate_error ?? null,
  gate_response: outcome.parsed ?? null,
}

if (evidencePath) {
  fs.mkdirSync(path.dirname(path.resolve(evidencePath)), { recursive: true })
  fs.writeFileSync(evidencePath, `${JSON.stringify(record, null, 2)}\n`)
}

console.log(BANNERS[outcome.status])
console.log(JSON.stringify(record, null, 2))
process.exit(EXIT_CODES[outcome.status])
