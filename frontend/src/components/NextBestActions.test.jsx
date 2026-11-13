import { act } from "react";
import { createRoot } from "react-dom/client";
import { SWRConfig } from "swr";
/* global jest */
import { afterEach, beforeEach, expect, test } from "@jest/globals";
import NextBestActions from "./NextBestActions";
import RecommendationCard from "./RecommendationCard";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), patch: jest.fn(), post: jest.fn() }, formatErr: (detail) => detail }));
jest.mock("@/context/AuthContext", () => ({ useAuth: jest.fn() }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
// CRA's Jest 27 resolver cannot resolve React Router 7's exports-only entry point.
jest.mock("react-router-dom", () => ({ Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a> }), { virtual: true });

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let container;
let root;
let records;
let cache;
const fixture = {
  id: "nba-test", state: "new", priority: 30, action_type: "decide_approval",
  title: "Review an overdue approval", reason: "The client is waiting for your decision.",
  deep_link: "/operations?tab=approvals", workspace_id: "workspace-test",
  evidence: { overdue_days: 3, owner: "Test owner" }, source_refs: ["approval:test"],
};
const user = { id: "user-test", tenant_id: "tenant-test" };

beforeEach(() => {
  jest.clearAllMocks();
  records = [{ ...fixture }];
  cache = new Map();
  useAuth.mockReturnValue({ user });
  api.get.mockImplementation(async () => ({ data: records.filter((item) => ["new", "accepted"].includes(item.state)).map((item) => ({ ...item })) }));
  api.patch.mockImplementation(async (_, body) => {
    records = records.map((item) => ({ ...item, ...body }));
    return { data: records[0] };
  });
  api.post.mockResolvedValue({ data: {} });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

async function render(element = <NextBestActions compact />) {
  await act(async () => root.render(
    <SWRConfig value={{ provider: () => cache, dedupingInterval: 0 }}>{element}</SWRConfig>,
  ));
}

async function until(assertion) {
  for (let count = 0; count < 30; count += 1) {
    try { assertion(); return; } catch (error) { if (count === 29) throw error; }
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); });
  }
}

async function click(selector) {
  const element = document.querySelector(selector);
  expect(element).not.toBeNull();
  await act(async () => element.click());
}

async function loaded() {
  await until(() => expect(container.querySelector('[data-testid="nba-open"]')).not.toBeNull());
}

test("uses a specific navigation action and exposes evidence without recording feedback", async () => {
  await render();
  await loaded();
  const link = container.querySelector('[data-testid="nba-open"]');
  expect(link.textContent).toBe("Review approval");
  expect(link.getAttribute("href")).toBe(fixture.deep_link);
  expect(container.querySelector("details").textContent).toContain("3 days overdue");
  expect(container.querySelector("details").textContent).toContain("approval:test");
  expect(api.patch).not.toHaveBeenCalled();
});

test.each([
  ["resolve_commitment", "Review commitment"], ["advance_task", "Open task"],
  ["recover_stalled_lead", "Review recovery"], ["recover_missed_followup", "Review follow-up"],
  ["repair_integration", "Check integration"], ["review_client_health", "Review client health"],
  ["future_action", "Review details"],
])("labels %s without changing the server destination", async (actionType, label) => {
  await render(<RecommendationCard item={{ ...fixture, action_type: actionType }} onFeedback={jest.fn()} />);
  expect(container.querySelector("a").textContent).toBe(label);
  expect(container.querySelector("a").getAttribute("href")).toBe(fixture.deep_link);
});

test("accept persists and remains visible", async () => {
  await render(); await loaded();
  await click('[data-testid="nba-accept"]');
  await until(() => expect(container.textContent).toContain("Accepted"));
  expect(api.patch).toHaveBeenCalledWith("/next-best-actions/nba-test", { state: "accepted" });
  expect(container.querySelector('[data-testid="nba-accept"]')).toBeNull();
});

test("dismiss changes only the recommendation and supports server-persisted undo", async () => {
  records[0].state = "accepted";
  await render(); await loaded();
  await click('[data-testid="nba-dismiss"]');
  await until(() => expect(container.querySelector('[data-testid="nba-empty"]')).not.toBeNull());
  expect(api.patch).toHaveBeenLastCalledWith("/next-best-actions/nba-test", { state: "dismissed", outcome: "not_relevant" });
  const [message, options] = toast.success.mock.calls[0];
  expect(message).toContain("linked records unchanged");
  await act(async () => options.action.onClick());
  await loaded();
  expect(api.patch).toHaveBeenLastCalledWith("/next-best-actions/nba-test", { state: "accepted", outcome: "", note: "" });
  expect(container.textContent).toContain("Accepted");
});

test.each([["1 hour", 60], ["4 hours", 240], ["1 day", 1440], ["3 days", 4320], ["1 week", 10080]])("snoozes for %s only after selecting a duration", async (label, minutes) => {
  await render(); await loaded();
  const trigger = container.querySelector('[data-testid="nba-snooze"]');
  await act(async () => trigger.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, button: 0, ctrlKey: false })));
  expect(api.patch).not.toHaveBeenCalled();
  const option = [...document.querySelectorAll('[role="menuitem"]')].find((item) => item.textContent === label);
  expect(option).toBeDefined();
  await act(async () => option.click());
  await until(() => expect(api.patch).toHaveBeenCalledWith("/next-best-actions/nba-test", { state: "snoozed", snooze_minutes: minutes }));
  expect(toast.success.mock.calls[0][0]).toContain(label);
});

test("review confirmation can be cancelled without completing anything", async () => {
  await render(); await loaded();
  await click('[data-testid="nba-complete"]');
  expect(document.querySelector('[role="alertdialog"]').textContent).toContain("does not complete a task");
  expect(api.patch).not.toHaveBeenCalled();
  const cancel = [...document.querySelectorAll('[role="alertdialog"] button')].find((button) => button.textContent === "Keep in queue");
  await act(async () => cancel.click());
  expect(document.querySelector('[role="alertdialog"]')).toBeNull();
  expect(api.patch).not.toHaveBeenCalled();
});

test("review confirmation persists only recommendation feedback", async () => {
  await render(); await loaded();
  await click('[data-testid="nba-complete"]');
  const confirm = [...document.querySelectorAll('[role="alertdialog"] button')].find((button) => button.textContent === "Mark reviewed");
  await act(async () => confirm.click());
  expect(api.patch).toHaveBeenCalledWith("/next-best-actions/nba-test", { state: "completed", outcome: "done" });
  await until(() => expect(container.querySelector('[data-testid="nba-empty"]')).not.toBeNull());
});

test("failed feedback leaves the recommendation visible and reports the server error", async () => {
  api.patch.mockRejectedValueOnce({ response: { data: { detail: "Permission denied" } } });
  await render(); await loaded();
  await click('[data-testid="nba-dismiss"]');
  expect(toast.error).toHaveBeenCalledWith("Permission denied");
  expect(toast.success).not.toHaveBeenCalled();
  expect(container.querySelector('[data-testid="nba-open"]')).not.toBeNull();
});

test("prevents duplicate feedback while a save is pending", async () => {
  let resolve;
  api.patch.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  await render(); await loaded();
  await click('[data-testid="nba-dismiss"]');
  expect(container.querySelector('[data-testid="nba-accept"]').disabled).toBe(true);
  await click('[data-testid="nba-dismiss"]');
  expect(api.patch).toHaveBeenCalledTimes(1);
  await act(async () => resolve({ data: {} }));
});

test("a failed load has an honest retry instead of an empty queue", async () => {
  api.get.mockRejectedValueOnce(new Error("offline"));
  await render();
  await until(() => expect(container.querySelector('[data-testid="nba-error"]')).not.toBeNull());
  expect(container.querySelector('[data-testid="nba-empty"]')).toBeNull();
  await click('[data-testid="nba-error-retry"]');
  await loaded();
});

test("refresh regenerates then reloads the queues", async () => {
  await render(); await loaded();
  const before = api.get.mock.calls.length;
  await click('[data-testid="nba-refresh"]');
  expect(api.post).toHaveBeenCalledWith("/next-best-actions/generate");
  expect(api.get.mock.calls.length).toBeGreaterThan(before);
});

test("does not reuse another tenant's cached recommendations", async () => {
  await render(); await loaded();
  useAuth.mockReturnValue({ user: { ...user, tenant_id: "different-tenant" } });
  api.get.mockResolvedValueOnce({ data: [] });
  await render();
  await until(() => expect(container.querySelector('[data-testid="nba-empty"]')).not.toBeNull());
  expect(container.textContent).not.toContain(fixture.title);
});

test("failed review confirmation stays open for retry", async () => {
  api.patch.mockRejectedValueOnce(new Error("offline"));
  await render(); await loaded();
  await click('[data-testid="nba-complete"]');
  const confirm = [...document.querySelectorAll('[role="alertdialog"] button')].find((button) => button.textContent === "Mark reviewed");
  await act(async () => confirm.click());
  expect(document.querySelector('[role="alertdialog"]')).not.toBeNull();
  expect(toast.error).toHaveBeenCalledWith("Could not record that decision");
  expect(records[0].state).toBe("new");
});

test("saved feedback is not reported as failed when the subsequent refresh fails", async () => {
  await render(); await loaded();
  api.get.mockRejectedValueOnce(new Error("offline"));
  await click('[data-testid="nba-dismiss"]');
  expect(records[0].state).toBe("dismissed");
  expect(toast.success.mock.calls[0][0]).toContain("Recommendation dismissed");
  expect(toast.error).not.toHaveBeenCalled();
  expect(container.querySelector('[data-testid="nba-error"]')).not.toBeNull();
});

test("feedback refreshes mounted queues with different workspace scopes", async () => {
  await render(<><NextBestActions compact /><NextBestActions workspaceId="workspace-test" compact /></>);
  await until(() => expect(container.querySelectorAll('[data-testid="nba-open"]').length).toBe(2));
  const before = api.get.mock.calls.length;
  await click('[data-testid="nba-dismiss"]');
  await until(() => expect(container.querySelectorAll('[data-testid="nba-empty"]').length).toBe(2));
  expect(api.get.mock.calls.length - before).toBe(2);
});

test("does not fetch without an authenticated tenant", async () => {
  useAuth.mockReturnValue({ user: null });
  await render();
  expect(api.get).not.toHaveBeenCalled();
});
