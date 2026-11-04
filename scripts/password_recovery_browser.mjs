// Recovery UI contract checks. API security is tested separately against MongoDB.
// Serves the actual production build locally; no live email or production account.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const { chromium } = require('playwright');
const { default: AxeBuilder } = require('@axe-core/playwright');
const build = path.join(root, 'frontend/build');
const server = createServer(async (req, res) => {
  try {
    const name = new URL(req.url, 'http://localhost').pathname;
    const file = path.resolve(build, `.${name.includes('.') ? name : '/index.html'}`);
    if (!file.startsWith(`${build}${path.sep}`)) { res.writeHead(404).end(); return; }
    const mime = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' }[path.extname(file)];
    res.writeHead(200, { 'Content-Type': mime || 'application/octet-stream' });
    res.end(await readFile(file));
  } catch { res.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ headless: true });
let checks = 0;
const check = (condition) => { assert.ok(condition); checks++; };
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('pageerror', error => consoleErrors.push(error.message));
  await page.route('**/api/auth/me', route => route.fulfill({ status: 401, json: { detail: 'Not authenticated' } }));
  let requests = 0;
  await page.route('**/api/auth/forgot-password', async route => {
    requests++;
    await new Promise(resolve => setTimeout(resolve, 200));
    await route.fulfill({ status: 202, json: { message: 'If an account can be recovered, you will receive an email with a reset link.' } });
  });
  await page.goto(`${base}/login`);
  await page.getByRole('link', { name: 'Forgot password?' }).click();
  await page.getByLabel('Account email').fill('local-test@example.com');
  await page.getByRole('button', { name: 'Send reset link' }).click();
  check(await page.getByRole('button', { name: 'Please wait…' }).isDisabled());
  await page.getByRole('status').waitFor();
  check((await page.getByRole('status').innerText()).includes('If an account can be recovered'));
  check(requests === 1);

  await page.goto(`${base}/reset-password`);
  check(await page.getByRole('link', { name: 'Request a new link' }).isVisible());
  const testToken = 'A'.repeat(43); // synthetic UI fixture, never a valid server token
  let submitted = null;
  await page.route('**/api/auth/reset-password', async route => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 400, json: { detail: 'This reset link is invalid or has expired. Request a new link.' } });
  });
  await page.goto(`${base}/reset-password#token=${testToken}`);
  await page.getByLabel('New password', { exact: true }).fill('Test-only-long-password!');
  check(!page.url().includes('#') && !page.url().includes(testToken));
  await page.getByLabel('Confirm new password').fill('Does-not-match!');
  await page.getByRole('button', { name: 'Save new password' }).click();
  check((await page.getByRole('alert').innerText()).includes('do not match'));
  check(submitted === null);
  await page.getByLabel('Confirm new password').fill('Test-only-long-password!');
  await page.getByRole('button', { name: 'Save new password' }).click();
  await page.getByText('This reset link is invalid or has expired. Request a new link.', { exact: true }).waitFor();
  check(submitted.token === testToken);
  await page.route('**/api/auth/reset-password', route => route.fulfill({ status: 200,
    json: { message: 'Your password has been reset. Sign in with your new password.' } }));
  await page.getByRole('button', { name: 'Save new password' }).click();
  await page.getByRole('status').waitFor();
  check(page.url().endsWith('/reset-password')); // no automatic authenticated redirect
  check(await page.getByRole('link', { name: 'Back to sign in' }).isVisible());
  check(await page.evaluate(() => localStorage.getItem('cv_access_token')) === null);
  check(await page.getByLabel('New password', { exact: true }).count() === 0);

  await page.goto(`${base}/forgot-password`);
  await page.route('**/api/auth/forgot-password', route => route.abort());
  await page.getByLabel('Account email').fill('local-test@example.com');
  await page.getByRole('button', { name: 'Send reset link' }).click();
  await page.getByText('We could not connect. Please try again.', { exact: true }).waitFor();
  check(await page.getByRole('button', { name: 'Send reset link' }).isEnabled());

  for (const width of [390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const route of ['/forgot-password', `/reset-password#token=${testToken}`]) {
      await page.goto(`${base}${route}`);
      await page.getByRole('heading', { level: 1 }).waitFor();
      check(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
      const accessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      assert.deepEqual(accessibility.violations.map(v => ({ id: v.id, impact: v.impact })), []);
      checks++;
    }
  }
  await page.goto(`${base}/forgot-password`);
  await page.getByLabel('Account email').focus();
  await page.keyboard.press('Tab');
  check(await page.getByRole('button', { name: 'Send reset link' }).evaluate(el => el === document.activeElement));
  check(consoleErrors.length === 0);
  if (process.env.RECOVERY_SCREENSHOT_PATH) await page.screenshot({ path: process.env.RECOVERY_SCREENSHOT_PATH, fullPage: true });
  console.log(`Password recovery UI: ${checks} checks passed (Chromium; 390/768/1440px; axe; keyboard).`);
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
