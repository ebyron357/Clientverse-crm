import { writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";

const baseUrl = (process.env.A11Y_BASE_URL || "http://127.0.0.1:3004").replace(/\/$/, "");
const email = process.env.A11Y_EMAIL;
const password = process.env.A11Y_PASSWORD;
const outputPath = process.env.A11Y_OUTPUT || path.resolve("../docs/evidence/a11y-axe-release.json");
const routes = [
  "/dashboard",
  "/directory",
  "/workspaces",
  "/settings",
  "/registries",
  "/client-ops",
  "/field",
  "/notifications",
];

if (!email || !password) {
  throw new Error("A11Y_EMAIL and A11Y_PASSWORD must be supplied through the environment.");
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1024 } });
const page = await context.newPage();
const report = {
  generated_at: new Date().toISOString(),
  target: baseUrl,
  standard: "WCAG 2.2 AA",
  routes: [],
};

try {
  await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded" });
  await page.getByTestId("email-input").fill(email);
  await page.getByTestId("password-input").fill(password);
  await page.getByTestId("submit-auth-button").click();
  await page.waitForURL(/\/dashboard$/, { timeout: 15000 });

  for (const route of routes) {
    await page.goto(`${baseUrl}${route}`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(350);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    report.routes.push({
      route,
      violation_count: results.violations.length,
      incomplete_count: results.incomplete.length,
      violations: results.violations.map((violation) => ({
        id: violation.id,
        impact: violation.impact,
        help: violation.help,
        help_url: violation.helpUrl,
        nodes: violation.nodes.map((node) => ({
          target: node.target,
          failure_summary: node.failureSummary,
        })),
      })),
      incomplete: results.incomplete.map((item) => ({
        id: item.id,
        impact: item.impact,
        help: item.help,
      })),
    });
  }
} finally {
  await context.close();
  await browser.close();
}

await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
const violationCount = report.routes.reduce((total, route) => total + route.violation_count, 0);
const seriousOrCritical = report.routes.reduce(
  (total, route) => total + route.violations.filter((item) => item.impact === "serious" || item.impact === "critical").length,
  0,
);
console.log(JSON.stringify({ routes: report.routes.length, violations: violationCount, serious_or_critical: seriousOrCritical }));
process.exitCode = seriousOrCritical > 0 ? 2 : 0;
