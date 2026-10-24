#!/usr/bin/env node
/**
 * Production browser pass: real Chromium against a live deployment, at phone, tablet,
 * laptop and desktop widths.
 *
 *   CLIENTVERSE_API_BASE=https://crm.clientverse.io CLIENTVERSE_SCREENSHOT_DIR=shots \
 *   CLIENTVERSE_EVIDENCE_PATH=browser.json node scripts/production_browser.mjs
 *
 * Like production_acceptance.mjs it needs no owner credentials: it registers its own
 * clearly named test organization on a reserved example.com address, turns email alerts
 * off, files one test lead through the website server door, then signs in through the
 * real sign-in page. On each width it checks the sign-in page (no third-party button,
 * visible keyboard focus), signs in, opens every main page (no horizontal scroll, no
 * page error, no "Something went wrong"), finds the test lead in Leads, and signs out
 * with the menu's own button. Requires the `playwright` package and its Chromium.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { randomBytes } from 'node:crypto'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const { chromium } = require('playwright')

const base = (process.env.CLIENTVERSE_API_BASE || '').replace(/\/$/, '')
if (!base) { console.error('CLIENTVERSE_API_BASE is required'); process.exit(2) }
const shots = process.env.CLIENTVERSE_SCREENSHOT_DIR || 'browser-shots'
const evidencePath = process.env.CLIENTVERSE_EVIDENCE_PATH
mkdirSync(shots, { recursive: true })
const tag = `${process.env.GITHUB_RUN_ID || 'local'}-${randomBytes(3).toString('hex')}`.toLowerCase()

const PAGES = ['/dashboard', '/leads', '/pipeline', '/directory', '/tasks', '/workspaces',
  '/website-forms', '/scheduling/calendar', '/notifications', '/team', '/settings']
const WIDTHS = [['phone', 390, 844], ['tablet', 768, 1024], ['laptop', 1024, 768], ['desktop', 1440, 900]]

const evidence = { base, started_at: new Date().toISOString(), checks: [], result: 'running' }
let failures = 0
function record(ok, name, detail = {}) {
  evidence.checks.push({ ok, name, ...detail })
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${ok ? '' : ` ${JSON.stringify(detail)}`}`)
  if (!ok) failures += 1
}

async function api(path, { method = 'GET', token, body, headers = {} } = {}) {
  const init = { method, headers: { Accept: 'application/json', 'User-Agent': 'clientverse-acceptance', ...headers } }
  if (token) init.headers.Authorization = `Bearer ${token}`
  if (body) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body) }
  const response = await fetch(`${base}${path}`, init)
  let json = null
  try { json = await response.json() } catch { json = null }
  return { status: response.status, json }
}

async function setUp() {
  const email = `acceptance+browser-${tag}@example.com`
  const password = `Acc-${randomBytes(9).toString('base64url')}-9`
  const reg = await api('/api/auth/register', { method: 'POST',
    body: { email, password, name: 'ClientVerse Acceptance Test Browser' } })
  if (reg.status !== 200) throw new Error(`register ${reg.status}`)
  const token = reg.json.token
  await api('/api/notifications/preferences/me', { method: 'PUT', token,
    body: { prefs: { channels: { email: false, in_app: true } } } })
  const form = await api('/api/website-forms', { method: 'POST', token, body: {
    name: `Acceptance browser form ${tag}`, preset: 'contact',
    settings: { notify: { in_app: true, email: false }, assignment: { mode: 'specific', users: [email] } } } })
  const key = await api(`/api/website-forms/${form.json.id}/server-key`, { method: 'POST', token })
  const leadName = `Acceptance Browser Lead ${tag}`
  const lead = await api('/api/intake/leads', { method: 'POST', headers: { Authorization: `Bearer ${key.json.key}` },
    body: { idempotencyKey: `acceptance-browser-${tag}`, source: 'acceptance', leadType: 'buyer', name: leadName,
      email: `browser-lead-${tag}@example.com`, phone: '704-555-0142', message: 'Acceptance test - please ignore.',
      payload: { priceRange: '$500,000+' } } })
  if (lead.json?.outcome !== 'accepted') throw new Error(`lead ${lead.status}`)
  await api('/api/auth/logout', { method: 'POST', token })
  evidence.records = { tenant_id: reg.json.user.tenant_id, admin: email, form: form.json.id, lead: lead.json.id }
  return { email, password, leadName, formId: form.json.id, leadId: lead.json.id }
}

async function tearDown(account) {
  const login = await api('/api/auth/login', { method: 'POST', body: { email: account.email, password: account.password } })
  const token = login.json?.token
  if (!token) return
  const lead = await api(`/api/leads/${account.leadId}`, { token })
  await api(`/api/leads/${account.leadId}`, { method: 'PATCH', token, body: { status: 'responded' } })
  await api(`/api/leads/${account.leadId}`, { method: 'PATCH', token, body: { status: 'closed' } })
  if (lead.json?.opportunity_id) await api(`/api/opportunities/${lead.json.opportunity_id}/archive`, { method: 'POST', token })
  if (lead.json?.contact_id) await api(`/api/contacts/${lead.json.contact_id}/archive`, { method: 'POST', token })
  await api(`/api/website-forms/${account.formId}`, { method: 'PATCH', token, body: { status: 'paused' } })
  await api('/api/auth/logout', { method: 'POST', token })
}

async function main() {
  const account = await setUp()
  const browser = await chromium.launch()
  try {
    for (const [label, width, height] of WIDTHS) {
      const context = await browser.newContext({ viewport: { width, height } })
      const page = await context.newPage()
      const errors = []
      page.on('pageerror', (error) => errors.push(String(error).slice(0, 200)))

      await page.goto(`${base}/login`, { waitUntil: 'networkidle' })
      await page.getByRole('heading', { name: 'Sign in to ClientVerse' }).waitFor()
      record(await page.getByText('Continue with Google').count() === 0, `${label}: no third-party sign-in button`)
      await page.keyboard.press('Tab')
      const focus = await page.evaluate(() => {
        const el = document.activeElement
        if (!el || el === document.body) return { visible: false }
        const style = getComputedStyle(el)
        return { tag: el.tagName, visible: style.outlineStyle !== 'none' || style.boxShadow !== 'none' }
      })
      record(focus.visible, `${label}: keyboard focus is visible on the sign-in page`, focus)
      await page.screenshot({ path: `${shots}/${label}-login.png`, fullPage: true })

      await page.getByTestId('email-input').fill(account.email)
      await page.getByTestId('password-input').fill(account.password)
      await page.getByTestId('submit-auth-button').click()
      await page.waitForURL(/\/dashboard/, { timeout: 30000 })
      record(true, `${label}: signed in through the sign-in page`)

      for (const path of PAGES) {
        await page.goto(`${base}${path}`, { waitUntil: 'networkidle' })
        await page.waitForTimeout(400)
        const state = await page.evaluate(() => ({
          overflow: document.scrollingElement.scrollWidth - window.innerWidth,
          crashed: /Something went wrong/i.test(document.body.innerText),
          signedOut: location.pathname === '/login',
        }))
        record(state.overflow <= 1 && !state.crashed && !state.signedOut, `${label}: ${path} renders`, state)
        await page.screenshot({ path: `${shots}/${label}${path.replaceAll('/', '-')}.png`, fullPage: false })
      }

      await page.goto(`${base}/leads`, { waitUntil: 'networkidle' })
      const found = await page.getByText(account.leadName).first().waitFor({ timeout: 15000 }).then(() => true, () => false)
      record(found, `${label}: the test lead is listed in Leads`)
      await page.reload({ waitUntil: 'networkidle' })
      const persisted = await page.getByText(account.leadName).first().waitFor({ timeout: 15000 }).then(() => true, () => false)
      record(persisted, `${label}: the lead is still listed after a reload`)

      // On narrow screens the menu sits behind its "Open navigation" toggle.
      const opener = page.getByRole('button', { name: 'Open navigation' })
      if (await opener.isVisible().catch(() => false)) await opener.click()
      await page.getByTestId('sign-out-button').click()
      await page.waitForURL(/\/login/, { timeout: 15000 }).catch(() => {})
      record(page.url().includes('/login'), `${label}: signed out with the menu's sign-out button`)
      await page.goto(`${base}/dashboard`, { waitUntil: 'networkidle' })
      record(page.url().includes('/login'), `${label}: a signed-out visitor is sent to sign in`)
      record(errors.length === 0, `${label}: no page errors`, { errors })
      await context.close()
    }
  } finally {
    await browser.close()
    await tearDown(account).catch(() => {})
  }
  evidence.result = failures ? 'failed' : 'passed'
  evidence.finished_at = new Date().toISOString()
  if (evidencePath) writeFileSync(evidencePath, JSON.stringify(evidence, null, 2))
  console.log(`\n${failures ? `FAILED ${failures} of` : 'PASSED'} ${evidence.checks.length} browser checks against ${base}`)
  process.exit(failures ? 1 : 0)
}

main().catch((error) => {
  evidence.result = 'failed'
  evidence.error = String(error?.stack || error).slice(0, 2000)
  if (evidencePath) writeFileSync(evidencePath, JSON.stringify(evidence, null, 2))
  console.error(error)
  process.exit(1)
})
