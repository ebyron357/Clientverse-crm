// C-30: exercise the installed packages, including the advisory regressions. Node's
// runner resolves package exports that the older CRA Jest resolver cannot handle.
const assert = require("node:assert/strict");
const { test } = require("node:test");
const axios = require("axios");
const { createMemoryRouter, generatePath } = require("react-router-dom");

test("Axios ignores an inherited default HTTP method (GHSA-9fr6-4gfg-395g)", async () => {
  let method;
  Object.prototype.method = "DELETE";
  try {
    await axios.request({
      url: "/api/contacts",
      adapter: async (config) => {
        method = config.method;
        return { data: [], status: 200, statusText: "OK", headers: {}, config };
      },
    });
  } finally {
    delete Object.prototype.method;
  }
  assert.equal(method, "get");
});

test("Axios retains authenticated CRM writes and JSON responses", async () => {
  const api = axios.create({ baseURL: "/api", withCredentials: true });
  api.interceptors.request.use((config) => {
    config.headers.Authorization = "Bearer disposable-test-token";
    return config;
  });
  let sent;
  const response = await api.patch("/tasks/task-1", { status: "done" }, {
    adapter: async (config) => {
      sent = config;
      return { data: '{"ok":true}', status: 200, statusText: "OK", headers: {}, config };
    },
  });
  assert.equal(sent.method, "patch");
  assert.equal(sent.withCredentials, true);
  assert.equal(sent.headers.Authorization, "Bearer disposable-test-token");
  assert.deepEqual(JSON.parse(sent.data), { status: "done" });
  assert.deepEqual(response.data, { ok: true });
});

test("React Router keeps generated record paths on the CRM origin", () => {
  for (const id of ["\\\\evil.example", "/\\evil.example", "//evil.example"]) {
    const path = generatePath("/:id", { id });
    assert.equal(new URL(path, "https://crm.example").origin, "https://crm.example");
  }
});

test("React Router preserves task params, query filters, and navigation blockers", async () => {
  const router = createMemoryRouter([
    { path: "/tasks", element: null },
    { path: "/tasks/:taskId", element: null },
  ], { initialEntries: ["/tasks?status=todo"] });
  try {
    await router.navigate("/tasks/task-1?from=leads");
    assert.equal(router.state.matches.at(-1).params.taskId, "task-1");
    assert.equal(router.state.location.search, "?from=leads");
    router.getBlocker("unsaved-note", () => true);
    await router.navigate("/tasks");
    assert.equal(router.state.location.pathname, "/tasks/task-1");
    assert.equal(router.state.blockers.get("unsaved-note").state, "blocked");
    router.state.blockers.get("unsaved-note").reset();
    router.deleteBlocker("unsaved-note");
    await router.navigate("/tasks");
    assert.equal(router.state.location.pathname, "/tasks");
  } finally {
    router.dispose();
  }
});
