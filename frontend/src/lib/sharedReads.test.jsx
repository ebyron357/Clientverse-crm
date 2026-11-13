import { act } from "react";
import { createRoot } from "react-dom/client";
/* global jest */
import { afterEach, beforeEach, expect, test } from "@jest/globals";
import { api } from "./api";
import { affectedReads, OVERDUE_COUNT, SharedReadsProvider, SHARED_READ_INTERVAL, useMenuCounts, useSharedRead } from "./sharedReads";

// CRA's Jest 27 needs Axios's CommonJS build rather than its ESM entry point.
jest.mock("axios", () => jest.requireActual("axios/dist/node/axios.cjs"));
jest.mock("sonner", () => ({ toast: { error: jest.fn() } }));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const user = { id: "user-one", tenant_id: "tenant-one", role: "admin" };
let root;
let container;
let requests;
let values;
let respond;
let handles;

function Reader({ path, name = "page", params = null }) {
  const result = useSharedRead(path, params);
  handles[name] = result;
  return <output data-testid={name}>{JSON.stringify({ data: result.data, error: Boolean(result.error), loading: result.isLoading, validating: result.isValidating })}</output>;
}
function Menu() {
  return <output data-testid="menu">{JSON.stringify(useMenuCounts())}</output>;
}
function Route({ page }) {
  return <><Menu />{page && <Reader key={page} path={page} />}</>;
}
const read = (name = "page") => JSON.parse(container.querySelector(`[data-testid="${name}"]`).textContent);
const count = (path) => requests.filter((config) => config.method === "get" && (!path || config.url === path)).length;
const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

beforeEach(() => {
  requests = [];
  handles = {};
  values = {
    "/leads/summary": { open_now: 4 }, "/conversations/summary": { open_conversations: 3 },
    "/approval-queue/summary": { awaiting_decision: 2 }, "/tasks": { total: 5 },
    "/leads": { items: [{ id: "lead-one", status: "new" }], total: 1 },
    "/approval-queue": [{ id: "approval-one" }], "/conversations": [{ id: "thread-one" }],
  };
  respond = async (config) => values[config.url] || {};
  api.defaults.adapter = async (config) => {
    requests.push(config);
    return { data: await respond(config), config, status: 200, statusText: "OK", headers: {} };
  };
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  jest.useRealTimers();
});

async function render(children, identity = user) {
  await act(async () => root.render(<SharedReadsProvider user={identity}>{children}</SharedReadsProvider>));
}
async function until(assertion) {
  for (let i = 0; i < 40; i += 1) {
    try { assertion(); return; } catch (error) { if (i === 39) throw error; }
    await act(async () => new Promise((resolve) => setTimeout(resolve, 10)));
  }
}

test("six rapid navigations share four menu reads, including page summaries", async () => {
  const paths = ["/leads/summary", "/conversations/summary", "/approval-queue/summary", "/leads/summary", "/approval-queue/summary", "/conversations/summary"];
  for (const path of paths) {
    await render(<Route page={path} />);
    await until(() => expect(read().data).toEqual(values[path]));
  }
  expect(count()).toBe(4);
  expect(read("menu")).toEqual({ leads: 4, inbox: 3, approvals: 2, tasks: 5 });
  const taskRead = requests.find((config) => config.url === "/tasks");
  expect(taskRead.params).toMatchObject({ mine: true, include_unassigned: true, limit: 1, status: "todo,in_progress,blocked" });
  expect(Date.parse(taskRead.params.due_before)).toBeLessThanOrEqual(Date.now());
});

test("concurrent consumers share the same pending response", async () => {
  const pending = deferred();
  respond = () => pending.promise;
  await render(<><Reader path="/leads/summary" /><Reader path="/leads/summary" name="second" /></>);
  expect(count()).toBe(1);
  await act(async () => pending.resolve({ open_now: 9 }));
  await until(() => expect(read().data).toEqual({ open_now: 9 }));
  expect(read("second").data).toEqual(read().data);
});

test("manual refresh retains rows and a refresh failure retains the last response", async () => {
  await render(<Reader path="/leads" />);
  await until(() => expect(read().data?.total).toBe(1));
  const pending = deferred();
  respond = () => pending.promise;
  let refreshing;
  await act(async () => { refreshing = handles.page.mutate().catch(() => undefined); });
  expect(read()).toMatchObject({ data: values["/leads"], loading: false, validating: true });
  await act(async () => { pending.reject(new Error("offline")); await refreshing; });
  expect(read()).toMatchObject({ data: values["/leads"], loading: false, error: true });
  respond = async () => ({ items: [], total: 0 });
  await act(async () => handles.page.mutate());
  expect(read()).toMatchObject({ data: { items: [], total: 0 }, error: false });
});

test("completing and undoing a task refreshes both lead and overdue counts, not unrelated summaries", async () => {
  await render(<Route page="/leads/summary" />);
  await until(() => expect(read("menu").tasks).toBe(5));
  values["/tasks"] = { total: 4 };
  values["/leads/summary"] = { open_now: 3 };
  await act(async () => api.patch("/crm/tasks/task-one", { status: "done" }));
  await until(() => expect(read("menu")).toMatchObject({ leads: 3, tasks: 4 }));
  expect(read().data.open_now).toBe(3);
  values["/tasks"] = { total: 5 };
  values["/leads/summary"] = { open_now: 4 };
  await act(async () => api.patch("/crm/tasks/task-one", { status: "todo" }));
  await until(() => expect(read("menu")).toMatchObject({ leads: 4, tasks: 5 }));
  expect(count("/tasks")).toBe(3);
  expect(count("/leads/summary")).toBe(3);
  expect(count("/approval-queue/summary")).toBe(1);
  expect(count("/conversations/summary")).toBe(1);
});

test.each(["/approval-queue/one/decision", "/conversations/one/close"])("%s refreshes related lists and summaries", async (url) => {
  await render(<><Menu /><Reader path="/approval-queue" /><Reader path="/conversations" name="inbox" /></>);
  await until(() => expect(read("menu").inbox).toBe(3));
  values["/approval-queue"] = [];
  values["/conversations"] = [];
  values["/approval-queue/summary"] = { awaiting_decision: 1 };
  values["/conversations/summary"] = { open_conversations: 2 };
  await act(async () => api.post(url, { decision: "approved" }));
  await until(() => expect(read("menu")).toMatchObject({ inbox: 2, approvals: 1 }));
  expect(read().data).toEqual([]);
  expect(read("inbox").data).toEqual([]);
  expect(count("/tasks")).toBe(1);
});

test("failed writes do not invalidate cached reads", async () => {
  await render(<Route page="/leads/summary" />);
  await until(() => expect(read().data.open_now).toBe(4));
  respond = async () => { throw new Error("Forbidden"); };
  await act(async () => { await expect(api.patch("/leads/one", { status: "closed" })).rejects.toThrow("Forbidden"); });
  expect(count()).toBe(4);
  expect(read().data.open_now).toBe(4);
});

test("a mutation invalidates cached pages even while unmounted", async () => {
  await render(<Reader path="/leads" />);
  await until(() => expect(read().data.total).toBe(1));
  await render(<Menu />);
  values["/leads"] = { items: [], total: 0 };
  await act(async () => api.patch("/leads/one", { status: "closed" }));
  await render(<Reader path="/leads" />);
  await until(() => expect(read().data.total).toBe(0));
  expect(count("/leads")).toBe(2);
});

test("an older pending read cannot overwrite the refresh after a save", async () => {
  const old = deferred();
  let first = true;
  respond = async (config) => {
    if (config.method === "get" && first) { first = false; return old.promise; }
    return { open_now: 1 };
  };
  await render(<Reader path="/leads/summary" />);
  await act(async () => api.patch("/leads/one", { status: "responded" }));
  await until(() => expect(read().data?.open_now).toBe(1));
  await act(async () => old.resolve({ open_now: 99 }));
  expect(read().data.open_now).toBe(1);
});

test.each([
  { ...user, tenant_id: "tenant-two" }, { ...user, id: "user-two" },
  { ...user, role: "member" }, { ...user, acting: { tenant_id: "client-two" } },
])("session changes isolate pending replies and cached data: %j", async (identity) => {
  const old = deferred();
  respond = () => old.promise;
  await render(<Reader path="/leads/summary" />);
  respond = async () => ({ open_now: 2 });
  await render(<Reader path="/leads/summary" />, identity);
  await until(() => expect(read().data?.open_now).toBe(2));
  await act(async () => old.resolve({ open_now: 99 }));
  expect(read().data.open_now).toBe(2);
  expect(count()).toBe(2);
});

test("sign-out unmount discards the cache even when the same user returns", async () => {
  await render(<Reader path="/leads/summary" />);
  await until(() => expect(read().data?.open_now).toBe(4));
  await act(async () => root.render(null));
  values["/leads/summary"] = { open_now: 8 };
  await render(<Reader path="/leads/summary" />);
  await until(() => expect(read().data?.open_now).toBe(8));
  expect(count()).toBe(2);
});

test("visible counts refresh as time passes without route navigation", async () => {
  jest.useFakeTimers();
  await render(<Menu />);
  expect(read("menu").tasks).toBe(5);
  values["/tasks"] = { total: 6 };
  await act(async () => { jest.advanceTimersByTime(SHARED_READ_INTERVAL + 1); });
  expect(read("menu").tasks).toBe(6);
  expect(count("/tasks")).toBe(2);
});

test("hidden tabs do not poll", async () => {
  jest.useFakeTimers();
  await render(<Menu />);
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
  await act(async () => { jest.advanceTimersByTime(SHARED_READ_INTERVAL + 1); });
  expect(count()).toBe(4);
});

test("mutation routing does not invalidate on reads, failed feedback or unrelated writes", () => {
  expect(affectedReads({ method: "get", url: "/leads" })).toEqual([]);
  expect(affectedReads({ method: "patch", url: "/next-best-actions/one" })).toEqual([]);
  expect(affectedReads({ method: "post", url: "/auth/logout" })).toEqual([]);
  expect(affectedReads({ method: "post", url: "/playbooks/new/apply" })).toContain(OVERDUE_COUNT);
});
