// Local fixture verification only. No hosted account, credential, or provider is used.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, stat, mkdir } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const root = path.resolve("build");
const server = createServer(async (req, res) => {
  let file = path.join(root, decodeURIComponent(new URL(req.url, "http://localhost").pathname));
  try { if (!(await stat(file)).isFile()) file = path.join(root, "index.html"); } catch { file = path.join(root, "index.html"); }
  const type = file.endsWith(".js") ? "application/javascript" : file.endsWith(".css") ? "text/css" : "text/html";
  res.writeHead(200, { "Content-Type": type }); res.end(await readFile(file));
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch();
const user = { user_id: "fixture-member", tenant_id: "fixture-tenant", email: "test@example.com", name: "Fixture member", role: "member" };
const today = {
  plan_total: 1, plan: [{ kind: "overdue_task", id: "task-1", title: "Return the inquiry", detail: "Owner: Fixture member", reason: "Due yesterday", link: "/tasks?task=task-1" }],
  stats: { leads_waiting: 0, booked_this_week: 0, open_deals: 0, approvals_waiting: 0, commitments_at_risk: 0, overdue_tasks: 0, open_by_currency: {}, weighted_by_currency: {} },
  leads: [], appointments: [], pipeline: [], commitments: [], tasks: [],
};
let currentPage;
let available = true;
let providerError = false;
const posted = [];
const mutations = [];
const responses = {
  "/auth/me": user, "/today": today, "/dashboard": { portfolio: [], open_opportunities: 0, active_workspaces: 0 },
  "/integrations/health": [], "/alerts": [], "/notifications": { items: [], unread_count: 0 },
  "/contacts": [{ id: "c-a", name: "Fixture contact" }], "/companies": [], "/opportunities": [], "/workspaces": [],
  "/contacts/c-a": { contact: { id: "c-a", name: "Fixture contact", owner: user.email }, deals: [], tasks: [], timeline: [] },
  "/leads": { items: [] }, "/contacts/cleanup": { duplicates: [] }, "/next-best-actions": [],
};
try {
  await mkdir("/tmp/crm-assistant-ui", { recursive: true });
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    const context = await browser.newContext({ viewport, serviceWorkers: "block" });
    const page = await context.newPage();
    currentPage = page;
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on("console", message => { if (message.type() === "error") console.error("CONSOLE", message.text()); });
    page.on("pageerror", error => { errors.push(error.message); console.error("UI ERROR", error.message); });
    await page.route("**/api/**", async route => {
      const url = new URL(route.request().url());
      const key = url.pathname.replace(/^\/api/, "");
      if (route.request().method() !== "GET") mutations.push(key);
      let data;
      let status = 200;
      if (key === "/assistant/status") data = { available };
      else if (key === "/assistant/preview") {
        const body = route.request().postDataJSON(); posted.push(body);
        if (providerError) { status = 502; data = { detail: "Provider unavailable; nothing changed" }; }
        else data = { summary: [{ text: "Fixture recorded fact", source_refs: ["contact:0"] }], suggestions: [{ text: "Fixture draft; verify before using", source_refs: ["contact:0"] }], sources: [{ ref: "contact:0", label: "Fixture contact record", href: "/contacts?contact=c-a", facts: { name: "Fixture contact" } }], intent: body.mode === "search" ? "unanswered_leads" : "none", matches: [{ label: "Fixture inquiry", href: "/leads?lead=l-a" }], read_only: true, notice: "Fixture response, not a real AI generation. No customer records changed." };
      } else data = responses[key] ?? (key.endsWith("summary") ? {} : []);
      await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
    });
    console.log("Dashboard", viewport.width);
    await page.goto(`${base}/dashboard`);
    await page.getByRole("heading", { name: "Do next", exact: true }).waitFor();
    const plan = page.getByTestId("dashboard-priority-panel");
    assert.equal(await plan.getByTestId("priority-action-0").getAttribute("href"), "/tasks?task=task-1");
    const recommendations = page.getByTestId("command-center-nba");
    assert.equal(await recommendations.getAttribute("open"), null);
    console.log("Queue loaded");
    const prepare = page.locator("details").filter({ has: page.locator("summary", { hasText: "Prepare with AI" }) }).first();
    await prepare.locator("summary").first().click();
    const panel = page.getByTestId("assistant-panel");
    await panel.getByLabel("Help with").waitFor();
    const button = panel.getByRole("button", { name: "Prepare preview", exact: true });
    assert.equal(await button.isDisabled(), true);
    await panel.getByLabel(/What do you need/).fill("Show unanswered leads");
    await panel.getByRole("checkbox").check();
    await button.click();
    await panel.getByText("Fixture recorded fact", { exact: true }).waitFor();
    assert.equal(posted.at(-1).allow_provider, true);
    assert.equal(await panel.getByRole("link", { name: "Fixture inquiry" }).getAttribute("href"), "/leads?lead=l-a");
    // Changing intent invalidates old output. No automatic generation or mutation.
    const before = posted.length;
    await panel.getByLabel("Help with").selectOption("workflow");
    assert.equal(await panel.getByTestId("assistant-result").count(), 0);
    assert.equal(posted.length, before);
    providerError = true;
    await button.click();
    await panel.getByRole("alert").waitFor();
    providerError = false;
    await page.screenshot({ path: `/tmp/crm-assistant-ui/dashboard-${viewport.width}.png`, fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    console.log("Contact", viewport.width);
    await page.goto(`${base}/contacts?contact=c-a`);
    await page.getByTestId("contact-record").waitFor();
    await page.getByTestId("contact-tab-assistant").click();
    const contactPanel = page.getByTestId("assistant-panel");
    await contactPanel.getByLabel("Help with").selectOption("follow_up");
    await contactPanel.getByRole("checkbox").check();
    await contactPanel.getByRole("button", { name: "Prepare preview" }).click();
    await contactPanel.getByText("Fixture draft; verify before using", { exact: true }).waitFor();
    assert.equal(posted.at(-1).contact_id, "c-a");
    assert.equal(posted.at(-1).mode, "follow_up");
    assert.equal(await contactPanel.getByRole("button", { name: /^Send|^Save task|^Activate/ }).count(), 0);
    await page.screenshot({ path: `/tmp/crm-assistant-ui/contact-${viewport.width}.png`, fullPage: true });
    available = false;
    await page.reload();
    await page.getByTestId("contact-tab-assistant").click();
    await page.getByText(/AI assistance is not configured on this server/).waitFor();
    assert.equal(await page.getByRole("button", { name: "Prepare preview", exact: true }).count(), 0);
    available = true;
    assert.deepEqual(errors, []);
    await context.close();
  }
  assert.equal(mutations.every(key => key === "/assistant/preview"), true);
  console.log("PASS: desktop/mobile daily queue, source-linked preview, consent gate, mode invalidation, provider error, contact drafts, honest unavailable state, no automatic mutations or overflow (fixture API, not provider certification).");
} catch (error) { console.error(await currentPage?.locator("body").innerText()); throw error; } finally { await browser.close(); server.close(); }
