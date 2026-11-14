import { act, createContext, useContext } from "react";
import "whatwg-fetch";
import { createMemoryRouter, RouterProvider, useSearchParams } from "react-router-dom";
import { createRoot } from "react-dom/client";
/* global jest */
import { afterEach, beforeEach, expect, test } from "@jest/globals";
import { LeadStatusUpdate } from "./LeadStatusUpdate";

// Jest 27 cannot resolve React Router 7's exports-only entry point.
jest.mock("react-router-dom", () => {
  globalThis.TextEncoder = jest.requireActual("util").TextEncoder;
  return jest.requireActual("../../node_modules/react-router/dist/development/index.js");
}, { virtual: true });
jest.mock("@/lib/api", () => ({ formatErr: (detail) => Array.isArray(detail) ? detail.map((item) => item.msg).join(" ") : String(detail) }));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const lead = { id: "lead-one", status: "new", contact_id: "contact-one" };
let container;
let root;
let onStatus;
let router;
const EditorProps = createContext({});
function Editor() {
  const props = useContext(EditorProps);
  const [params] = useSearchParams();
  const current = props.lead || { ...lead, id: params.get("lead") };
  return params.has("lead") ? <LeadStatusUpdate key={current.id} lead={current} onStatus={onStatus} {...props} /> : <p>Lead list</p>;
}
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
  await act(async () => root.render(<EditorProps.Provider value={props}><RouterProvider router={router} /></EditorProps.Provider>));
}
beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  onStatus = jest.fn().mockResolvedValue(true);
  router = createMemoryRouter([
    { path: "/leads", element: <Editor /> },
    { path: "/contacts", element: <p>Contacts destination</p> },
  ], { initialEntries: ["/contacts", "/leads?lead=lead-one"] });
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  router.dispose();
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
const guardButton = (id) => document.querySelector(`[data-testid="${id}"]`);
const navigate = (to) => act(async () => { await router.navigate(to); });
const leaveEvent = () => {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event;
};

test.each(["/leads", "/leads?lead=lead-two", "/contacts", -1])("navigation %s preserves the draft until explicitly discarded", async (destination) => {
  await render();
  await typeNote("Keep this conversation");
  await navigate(destination);
  expect(router.state.location.search).toBe("?lead=lead-one");
  expect(document.querySelector("[role=alertdialog]").textContent).toContain("Discard your unsaved note?");
  expect(document.activeElement).toBe(guardButton("lead-note-keep"));
  await act(async () => guardButton("lead-note-keep").click());
  expect(draft()).toBe("Keep this conversation");
  expect(document.querySelector("[role=alertdialog]")).toBeNull();
  // Radix restores focus on the task following its unmount cleanup.
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)));
  expect(document.activeElement).toBe(get("lead-note"));
  await navigate(destination);
  await act(async () => guardButton("lead-note-discard").click());
  expect(router.state.location.pathname + router.state.location.search).toBe(destination === -1 ? "/contacts" : destination);
  expect(get("lead-note")?.value || "").toBe("");
  expect(onStatus).not.toHaveBeenCalled();
});

test.each(["", "   "])("empty draft %s does not block closing or unload", async (value) => {
  await render();
  await typeNote(value);
  expect(leaveEvent().defaultPrevented).toBe(false);
  await navigate("/leads");
  expect(container.textContent).toBe("Lead list");
  expect(document.querySelector("[role=alertdialog]")).toBeNull();
});

test("refresh warnings remain after failed saves and are removed after confirmed saves", async () => {
  onStatus.mockRejectedValueOnce(new Error("Offline"));
  await render();
  await typeNote("Protect across failed attempts");
  expect(leaveEvent().defaultPrevented).toBe(true);
  await click("responded");
  expect(leaveEvent().defaultPrevented).toBe(true);
  await click("responded");
  expect(leaveEvent().defaultPrevented).toBe(false);
  await navigate("/contacts");
  expect(container.textContent).toBe("Contacts destination");
});

test("query changes that keep the same lead do not discard or block the note", async () => {
  await render();
  await typeNote("Same lead");
  await navigate("/leads?lead=lead-one&form=another#history");
  expect(draft()).toBe("Same lead");
  expect(document.querySelector("[role=alertdialog]")).toBeNull();
});

test("an in-flight update prevents departure and never resumes it automatically", async () => {
  let resolve;
  onStatus.mockReturnValue(new Promise((done) => { resolve = done; }));
  await render();
  await click("responded");
  expect(leaveEvent().defaultPrevented).toBe(true);
  await navigate("/contacts");
  expect(document.querySelector("[role=alertdialog]").textContent).toContain("Update still saving");
  expect(guardButton("lead-note-discard")).toBeNull();
  await act(async () => resolve(true));
  expect(document.querySelector("[role=alertdialog]")).toBeNull();
  expect(router.state.location.pathname).toBe("/leads");
  expect(leaveEvent().defaultPrevented).toBe(false);
});

test("failed in-flight update allows keeping or discarding the preserved note", async () => {
  let reject;
  onStatus.mockReturnValue(new Promise((_, fail) => { reject = fail; }));
  await render();
  await typeNote("Keep on failure");
  await click("responded");
  await navigate("/contacts");
  await act(async () => reject(new Error("Offline")));
  expect(document.querySelector("[role=alertdialog]").textContent).toContain("Discard your unsaved note?");
  await act(async () => guardButton("lead-note-keep").click());
  expect(draft()).toBe("Keep on failure");
  expect(leaveEvent().defaultPrevented).toBe(true);
});

test("unmount cleans up the browser unload warning", async () => {
  await render();
  await typeNote("Draft before unmount");
  expect(leaveEvent().defaultPrevented).toBe(true);
  await act(async () => root.render(null));
  expect(leaveEvent().defaultPrevented).toBe(false);
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
