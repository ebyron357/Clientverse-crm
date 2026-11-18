import { act } from "react";
import { createRoot } from "react-dom/client";
/* global jest */
import { afterEach, beforeEach, expect, test } from "@jest/globals";
import { LeadFollowUp } from "./LeadFollowUp";
import { leadFollowUp } from "@/lib/leadFollowUp";

// Jest 27 cannot resolve React Router 7's exports-only entry point.
jest.mock("react-router-dom", () => ({ Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a> }), { virtual: true });

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const now = Date.parse("2026-11-13T12:00:00Z");
const lead = { id: "one", status: "new", phone: "+15555550123", assigned_to: "agent@example.com", task_id: "task-one", contact_id: "contact-one" };
let container;
let root;
beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

const next = (changes = {}) => leadFollowUp({ ...lead, ...changes }, now);
async function render(changes = {}) {
  await act(async () => root.render(<LeadFollowUp lead={{ ...lead, ...changes }} />));
}

test("new leads have a concrete next step, recorded owner, and encoded task link", () => {
  expect(next({ task_id: "a/b?c", assigned_name: "Alex" })).toMatchObject({ title: "Call the lead", owner: "Alex", action: { to: "/tasks?task=a%2Fb%3Fc" } });
});
test("escalation takes precedence over an inconsistent future deadline", () => {
  expect(next({ sla: { escalated_at: "2026-11-13T11:00:00Z", due_at: "2026-11-13T13:00:00Z" } }).reason).toContain("was escalated");
});
test.each(["2026-11-13T11:59:59Z", "2026-11-13T12:00:00Z"])("expired deadlines explain the overdue response: %s", (due_at) => {
  expect(next({ sla: { due_at } }).reason).toContain("deadline has passed");
});
test("future deadlines explain the open response window", () => {
  expect(next({ sla: { due_at: "2026-11-13T12:00:01Z" } }).reason).toContain("window is still open");
});
test.each([undefined, null, "", "invalid"])("missing or invalid deadlines do not invent urgency: %s", (due_at) => {
  expect(next({ sla: { due_at } }).reason).toBe("No first response has been recorded yet.");
});
test("email-only leads and email preferences recommend email", () => {
  expect(next({ phone: " ", email: "person@example.com" }).title).toBe("Send a personal email");
  expect(next({ email: "person@example.com", fields: { preferred_contact: " Email " } }).title).toBe("Send a personal email");
  expect(next({ fields: { preferred_contact: 42 } }).title).toBe("Call the lead");
});
test("missing communication details point to the contact rather than inventing a channel", () => {
  expect(next({ phone: null, contact_id: "contact/one" })).toMatchObject({ title: "Check contact details", action: { to: "/contacts?contact=contact%2Fone" } });
  expect(next({ phone: null, contact_id: null, task_id: null }).action).toBeNull();
});
test("assignment and automation failures explain additional attention", () => {
  const result = next({ assigned_to: null, automation: [{ result: "failed" }] });
  expect(result.owner).toBe("Unassigned");
  expect(result.reason).toContain("No owner is assigned");
  expect(result.reason).toContain("An automation step failed");
});
test("contacted leads review follow-up without claiming a linked task is open", () => {
  const result = next({ status: "responded", sla: { escalated_at: "2026-11-12" } });
  expect(result.title).toBe("Review the next follow-up");
  expect(result.reason).toContain("does not mean the linked task is still open");
  expect(next({ status: "responded", task_id: null, contact_id: null }).action.to).toBe("/tasks");
});
test.each(["closed", "spam"])("%s leads do not recommend outreach or task actions", (status) => {
  expect(next({ status, sla: { escalated_at: "2026-11-12" } })).toMatchObject({ title: "No outreach suggested", action: null });
});
test("test submissions override urgency and recommend only review", () => {
  expect(next({ is_test: true, sla: { escalated_at: "2026-11-12" } })).toMatchObject({ title: "Review test lead" });
});
test("unknown statuses and missing task links have honest fallbacks", () => {
  expect(next({ status: "unknown" }).title).toBe("Review lead status");
  expect(next({ task_id: null }).action.to).toBe("/contacts?contact=contact-one");
});
test("panel displays the reason, owner and task navigation without a write control", async () => {
  await render({ assigned_to: null });
  expect(container.textContent).toContain("Next step");
  expect(container.textContent).toContain("Owner: Unassigned");
  expect(container.textContent).toContain("An automatic reply is not a personal response");
  expect(container.querySelector("a").getAttribute("href")).toBe("/tasks?task=task-one");
  expect(container.querySelector("button")).toBeNull();
});
test("closed panel has no action link or first-response reminder", async () => {
  await render({ status: "closed" });
  expect(container.querySelector("a")).toBeNull();
  expect(container.textContent).not.toContain("Mark contacted");
});
test("test panel does not prompt an actual contact", async () => {
  await render({ is_test: true });
  expect(container.textContent).toContain("not a live follow-up");
  expect(container.textContent).not.toContain("Mark contacted");
});
