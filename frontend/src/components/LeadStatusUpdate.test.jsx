import { act } from "react";
import { createRoot } from "react-dom/client";
/* global jest */
import { afterEach, beforeEach, expect, test } from "@jest/globals";
import { LeadStatusUpdate } from "./LeadStatusUpdate";

jest.mock("@/lib/api", () => ({ formatErr: (detail) => Array.isArray(detail) ? detail.map((item) => item.msg).join(" ") : String(detail) }));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const lead = { id: "lead-one", status: "new", contact_id: "contact-one" };
let container;
let root;
let onStatus;
const get = (testId) => container.querySelector(`[data-testid="${testId}"]`);
const click = async (status) => act(async () => get(`lead-status-${status}`).click());
const draft = () => get("lead-note").value;
async function typeNote(value) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(get("lead-note"), value);
    get("lead-note").dispatchEvent(new Event("input", { bubbles: true }));
  });
}
async function render(props = {}) {
  const current = props.lead || lead;
  await act(async () => root.render(<LeadStatusUpdate key={current.id} lead={current} onStatus={onStatus} {...props} />));
}
beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  onStatus = jest.fn().mockResolvedValue(true);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

test("typing drafts a note without saving or changing status", async () => {
  await render();
  await typeNote("Called; viewing requested.");
  expect(draft()).toBe("Called; viewing requested.");
  expect(container.textContent).toContain("Unsaved note");
  expect(onStatus).not.toHaveBeenCalled();
  expect(get("lead-status-new")).toBeNull();
});
test("confirmed save sends exact draft and clears it", async () => {
  await render();
  await typeNote("Called; viewing requested.");
  await click("responded");
  expect(onStatus).toHaveBeenCalledWith(lead, "responded", "Called; viewing requested.");
  expect(draft()).toBe("");
  expect(get("lead-update-error")).toBeNull();
});
test("failed update preserves draft, explains uncertainty, and permits a deliberate retry", async () => {
  onStatus.mockRejectedValueOnce({ response: { data: { detail: "Service temporarily unavailable" } } });
  await render();
  await typeNote("Do not lose this note");
  await click("responded");
  expect(draft()).toBe("Do not lose this note");
  expect(get("lead-update-error").textContent).toContain("Service temporarily unavailable");
  expect(document.activeElement).toBe(get("lead-update-error"));
  expect(get("lead-update-error").textContent).toContain("may have received the change");
  expect(get("lead-status-responded").disabled).toBe(false);
  expect(onStatus).toHaveBeenCalledTimes(1);
  await click("responded");
  expect(onStatus).toHaveBeenCalledTimes(2);
  expect(draft()).toBe("");
  expect(get("lead-update-error")).toBeNull();
});
test.each([false, undefined])("unconfirmed result (%s) never clears a draft", async (result) => {
  onStatus.mockResolvedValue(result);
  await render();
  await typeNote("Keep until confirmed");
  await click("closed");
  expect(draft()).toBe("Keep until confirmed");
  expect(get("lead-update-error").textContent).toContain("Update not confirmed");
});
test("network error has useful fallback text without an automatic retry", async () => {
  onStatus.mockRejectedValue(new Error("Network Error"));
  await render();
  await click("closed");
  expect(container.textContent).toContain("Check your connection");
  expect(onStatus).toHaveBeenCalledTimes(1);
});
test("pending update locks editing and rejects same-tick repeat actions", async () => {
  let resolve;
  onStatus.mockReturnValue(new Promise((done) => { resolve = done; }));
  await render();
  await typeNote("One submission");
  await act(async () => {
    get("lead-status-responded").click();
    get("lead-status-closed").click();
    get("lead-status-responded").click();
  });
  expect(onStatus).toHaveBeenCalledTimes(1);
  expect(get("lead-note").disabled).toBe(true);
  expect([...container.querySelectorAll("button")].every((button) => button.disabled)).toBe(true);
  expect(container.textContent).toContain("Saving…");
  expect(draft()).toBe("One submission");
  await act(async () => resolve(true));
  expect(draft()).toBe("");
  expect(get("lead-note").disabled).toBe(false);
});
test("another lead's in-flight update disables this editor", async () => {
  await render({ busy: true });
  await click("responded");
  expect(onStatus).not.toHaveBeenCalled();
});
test("leads without contacts cannot submit notes that the API would discard", async () => {
  const noContact = { ...lead, contact_id: null };
  await render({ lead: noContact });
  expect(get("lead-note").disabled).toBe(true);
  expect(container.textContent).toContain("Notes need a linked contact");
  await click("closed");
  expect(onStatus).toHaveBeenCalledWith(noContact, "closed", "");
});
test("refreshing the same lead preserves a draft, switching leads clears it", async () => {
  await render();
  await typeNote("Only for lead one");
  await render({ lead: { ...lead, status: "responded" } });
  expect(draft()).toBe("Only for lead one");
  expect(get("lead-status-responded")).toBeNull();
  expect(get("lead-status-new")).not.toBeNull();
  await render({ lead: { ...lead, id: "lead-two" } });
  expect(draft()).toBe("");
});
