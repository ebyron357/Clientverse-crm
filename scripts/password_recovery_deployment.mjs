// Non-destructive deployed-release validation: never request an email or change a password.
// Mailbox receipt and the owner's private reset are separate acceptance steps in the manual.
import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
const base = process.env.CLIENTVERSE_RECOVERY_BASE_URL || 'https://crm.clientverse.io';
const expected = process.env.CLIENTVERSE_EXPECTED_GIT_SHA;
assert.match(base, /^https:\/\/[^/?#]+$/);
assert.match(expected || '', /^[a-f0-9]{40}$/, 'Set CLIENTVERSE_EXPECTED_GIT_SHA to the approved release SHA');
const get = (path, options = {}) => fetch(`${base}${path}`, { ...options, redirect: 'error', signal: AbortSignal.timeout(20000) });
const health = await get('/api/health');
assert.equal(health.status, 200);
const status = await health.json();
assert.equal(status.git_sha, expected, 'Production must run the exact approved revision');
assert.equal(status.database, 'up');
for (const path of ['/forgot-password', '/reset-password']) {
  const page = await get(path);
  assert.equal(page.status, 200);
  assert.match(page.headers.get('content-type') || '', /text\/html/);
  assert.equal(page.headers.get('referrer-policy'), 'no-referrer');
  assert.equal(page.headers.get('cache-control'), 'no-store');
}
// Intentionally invalid, no user identity or account capability involved.
const invalid = await get('/api/auth/reset-password', { method: 'POST',
  headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: 'invalid-deployment-probe', new_password: 'Not-an-account-password-123!' }) });
assert.equal(invalid.status, 400);
assert.equal(invalid.headers.get('cache-control'), 'no-store');
assert.equal(invalid.headers.get('referrer-policy'), 'no-referrer');
assert.equal((await invalid.json()).detail, 'This reset link is invalid or has expired. Request a new link.');
const evidence = { checked_at: new Date().toISOString(), origin: base, git_sha: expected,
  result: 'PUBLIC_DEPLOYMENT_CHECKS_PASS', mailbox_delivery: 'NOT_TESTED', owner_recovery: 'NOT_TESTED' };
if (process.env.CLIENTVERSE_EVIDENCE_PATH) await writeFile(process.env.CLIENTVERSE_EVIDENCE_PATH, JSON.stringify(evidence, null, 2));
console.log(JSON.stringify(evidence));
