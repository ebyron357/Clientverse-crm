import { act } from "react";
import { createRoot } from "react-dom/client";
/* global jest */
import { afterEach, beforeEach, expect, test } from "@jest/globals";
import { api } from "./api";
import { affectedReads, OVERDUE_COUNT, TASK_BUCKETS, SharedReadsProvider, SHARED_READ_INTERVAL, useMenuCounts, useSharedRead } from "./sharedReads";
import { taskBoundaries, taskQuery, byTaskDue } from "./taskQueries";

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

function taskResponse(config) {
  if (config.method !== "get" || config.url !== "/tasks") return {};
  if (config.params.limit === 1) return { total: 1 };
  const { params } = config;
  const bucket = params.status === "done" ? "done" : params.include_undated ? "upcoming" : params.due_after ? "today" : "overdue";
  return { items: [{ id: `${params.mine ? "mine" : "everyone"}-${bucket}` }], total: 1 };
}

test("task remounts and view switches reuse four reads per scope without mixing views", async () => {
  respond = async (config) => taskResponse(config);
  await render(<Reader path={TASK_BUCKETS} params={{ view: "mine" }} />);
  await until(() => expect(read().data?.overdue.items[0].id).toBe("mine-overdue"));
  expect(count("/tasks")).toBe(4);
  await render(null);
  await render(<Reader path={TASK_BUCKETS} params={{ view: "mine" }} />);
  expect(read().data.overdue.items[0].id).toBe("mine-overdue");
  expect(count("/tasks")).toBe(4);
  const pending = deferred();
  respond = async (config) => { await pending.promise; return taskResponse(config); };
  await render(<Reader path={TASK_BUCKETS} params={{ view: "everyone" }} />);
  expect(read().data).toBeUndefined();
  await act(async () => pending.resolve());
  await until(() => expect(read().data?.overdue.items[0].id).toBe("everyone-overdue"));
  await render(<Reader path={TASK_BUCKETS} params={{ view: "mine" }} />);
  expect(read().data.overdue.items[0].id).toBe("mine-overdue");
  expect(count("/tasks")).toBe(8);
  expect(requests.slice(0, 4).every(({ params }) => params.mine && params.include_unassigned && params.expand === "related")).toBe(true);
  expect(requests.slice(4).every(({ params }) => params.mine === undefined && params.include_unassigned === undefined)).toBe(true);
});

test.each([
  ["post", "/crm/tasks", { title: "Call back" }],
  ["patch", "/crm/tasks/one", { status: "done" }],
  ["patch", "/crm/tasks/one", { status: "todo" }],
  ["patch", "/crm/tasks/one", { assignee: "teammate@example.com" }],
  ["delete", "/crm/tasks/one", undefined],
])("%s %s %j refreshes task buckets and sidebar once", async (method, url, data) => {
  let generation = 1;
  respond = async (config) => {
    if (config.method !== "get") { generation += 1; return {}; }
    const result = taskResponse(config);
    return { ...result, total: generation };
  };
  await render(<><Reader path={TASK_BUCKETS} params={{ view: "mine" }} /><Reader path={OVERDUE_COUNT} name="count" /></>);
  await until(() => expect(read().data?.overdue.total).toBe(1));
  await act(async () => api.request({ method, url, data }));
  await until(() => expect(read().data?.overdue.total).toBe(2));
  expect(read("count").data.total).toBe(2);
  expect(count("/tasks")).toBe(10);
});

test("a failed bucket refresh keeps the whole previous snapshot, then recovers on retry", async () => {
  respond = async (config) => taskResponse(config);
  await render(<Reader path={TASK_BUCKETS} params={{ view: "mine" }} />);
  await until(() => expect(read().data?.today.total).toBe(1));
  const previous = read().data;
  respond = async (config) => {
    if (config.params.include_undated) throw new Error("offline");
    return { items: [], total: 0 };
  };
  await act(async () => { await handles.page.mutate().catch(() => undefined); });
  expect(read()).toMatchObject({ data: previous, loading: false, error: true });
  respond = async () => ({ items: [], total: 0 });
  await act(async () => handles.page.mutate());
  expect(read()).toMatchObject({ data: { overdue: { total: 0 }, today: { total: 0 } }, error: false });
});

test("HTML or malformed task responses are failures, not an empty successful list", async () => {
  respond = async () => "<!doctype html>";
  await render(<Reader path={TASK_BUCKETS} params={{ view: "mine" }} />);
  await until(() => expect(read().error).toBe(true));
  expect(read().data).toBeUndefined();
});

test("task polling recalculates midnight boundaries instead of freezing the cached query", async () => {
  jest.useFakeTimers();
  const before = new Date(2026, 10, 13, 23, 59, 50);
  jest.setSystemTime(before);
  respond = async (config) => taskResponse(config);
  await render(<Reader path={TASK_BUCKETS} params={{ view: "mine" }} />);
  const first = requests.filter(({ params }) => params.include_undated)[0];
  expect(new Date(first.params.due_after).getDate()).toBe(14);
  await act(async () => { jest.advanceTimersByTime(SHARED_READ_INTERVAL + 1); });
  const second = requests.filter(({ params }) => params.include_undated)[1];
  expect(new Date(second.params.due_after).getDate()).toBe(15);
  expect(count("/tasks")).toBe(8);
});

test("task windows do not overlap at now or local midnight, and undated tasks sort last", () => {
  const now = new Date(2026, 10, 13, 13, 0, 0);
  const bounds = taskBoundaries(now);
  const overdue = taskQuery("overdue", bounds);
  const today = taskQuery("today", bounds);
  const upcoming = taskQuery("upcoming", bounds);
  const done = taskQuery("done", bounds);
  expect(Date.parse(overdue.due_before) + 1).toBe(Date.parse(today.due_after));
  expect(Date.parse(today.due_before) + 1).toBe(Date.parse(upcoming.due_after));
  expect(upcoming.include_undated).toBe(true);
  expect(new Date(upcoming.due_after).getHours()).toBe(0);
  expect(now - Date.parse(done.completed_after)).toBe(7 * 24 * 60 * 60 * 1000);
  expect(done).toMatchObject({ sort: "completed_at", order: "desc", status: "done" });
  const tasks = [{ id: "undated" }, { id: "later", due_date: "2026-11-15" }, { id: "earlier", due_date: "2026-11-14" }];
  expect(tasks.sort(byTaskDue).map(({ id }) => id)).toEqual(["earlier", "later", "undated"]);
});

test("mutation routing does not invalidate on reads, failed feedback or unrelated writes", () => {
  expect(affectedReads({ method: "get", url: "/leads" })).toEqual([]);
  expect(affectedReads({ method: "patch", url: "/next-best-actions/one" })).toEqual([]);
  expect(affectedReads({ method: "post", url: "/auth/logout" })).toEqual([]);
  expect(affectedReads({ method: "post", url: "/playbooks/new/apply" })).toContain(OVERDUE_COUNT);
});
