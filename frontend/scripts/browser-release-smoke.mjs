import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const baseUrl = (process.env.BROWSER_SMOKE_BASE_URL || "http://127.0.0.1:3004").replace(/\/$/, "");
const apiBaseUrl = (process.env.BROWSER_SMOKE_API_BASE_URL || "http://127.0.0.1:8004").replace(/\/$/, "");
const email = process.env.BROWSER_SMOKE_EMAIL;
const password = process.env.BROWSER_SMOKE_PASSWORD;
const outputPath = process.env.BROWSER_SMOKE_OUTPUT || path.resolve("../docs/evidence/browser-release-smoke.json");
const screenshotDir = path.dirname(outputPath);
const routes = ["/dashboard", "/settings", "/client-ops", "/field", "/notifications"];

if (!email || !password) {
  throw new Error("BROWSER_SMOKE_EMAIL and BROWSER_SMOKE_PASSWORD must be supplied through the environment.");
}

const browser = await chromium.launch({ headless: true });
const report = { generated_at: new Date().toISOString(), target: baseUrl, desktop: {}, mobile: {}, console_errors: [] };

async function authenticate(context, page) {
  const response = await context.request.post(`${apiBaseUrl}/api/auth/login`, { data: { email, password } });
  if (!response.ok()) throw new Error(`Browser smoke authentication failed with ${response.status()}.`);
  const token = (await response.json()).token;
  if (!token) throw new Error("Browser smoke authentication did not return an access token.");
  await context.addInitScript((accessToken) => window.localStorage.setItem("cv_access_token", accessToken), token);
  await page.goto(`${baseUrl}/dashboard`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(350);
}

try {
  await mkdir(screenshotDir, { recursive: true });
  const desktop = await browser.newContext({ viewport: { width: 1440, height: 1024 } });
  const desktopPage = await desktop.newPage();
  desktopPage.on("pageerror", (error) => report.console_errors.push({ type: "pageerror", message: error.message }));
  desktopPage.on("console", (message) => { if (message.type() === "error") report.console_errors.push({ type: "console", message: message.text() }); });
  await authenticate(desktop, desktopPage);
  report.desktop.keyboard_focus = [];
  for (let index = 0; index < 5; index += 1) {
    await desktopPage.keyboard.press("Tab");
    report.desktop.keyboard_focus.push(await desktopPage.evaluate(() => ({
      tag: document.activeElement?.tagName,
      label: document.activeElement?.getAttribute("aria-label") || document.activeElement?.textContent?.trim().slice(0, 80) || null,
    })));
  }
  report.desktop.routes = [];
  for (const route of routes) {
    await desktopPage.goto(`${baseUrl}${route}`, { waitUntil: "domcontentloaded" });
    await desktopPage.waitForTimeout(350);
    const main = desktopPage.locator("main");
    report.desktop.routes.push({ route, main_visible: await main.isVisible(), title: await desktopPage.title() });
  }
  await desktopPage.screenshot({ path: path.join(screenshotDir, "browser-release-desktop.png"), fullPage: true });
  await desktop.close();

  const mobile = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true });
  const mobilePage = await mobile.newPage();
  mobilePage.on("pageerror", (error) => report.console_errors.push({ type: "pageerror", message: error.message }));
  mobilePage.on("console", (message) => { if (message.type() === "error") report.console_errors.push({ type: "console", message: message.text() }); });
  await authenticate(mobile, mobilePage);
  await mobilePage.goto(`${baseUrl}/field`, { waitUntil: "domcontentloaded" });
  await mobilePage.waitForTimeout(350);
  report.mobile = { field_visible: await mobilePage.getByTestId("field-ops-page").isVisible() };
  await mobilePage.screenshot({ path: path.join(screenshotDir, "browser-release-mobile-field.png"), fullPage: true });
  await mobile.close();
} finally {
  await browser.close();
}

await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(JSON.stringify({ desktop_routes: report.desktop.routes?.length || 0, mobile_field: report.mobile.field_visible, console_errors: report.console_errors.length }));
process.exitCode = report.console_errors.length > 0 ? 2 : 0;
