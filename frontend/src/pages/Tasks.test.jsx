import { act } from "react";
import { createRoot } from "react-dom/client";
/* global jest */
import { afterEach, beforeEach, expect, test } from "@jest/globals";
import { TaskDetail } from "./Tasks";
import { taskSchedulePreset } from "@/components/TaskScheduleShortcuts";

// Jest 27 cannot resolve React Router 7's exports-only entry point.
jest.mock("react-router-dom", () => ({ Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a> }), { virtual: true });
jest.mock("@/lib/api", () => ({ api: {}, formatErr: String }));
jest.mock("@/lib/sharedReads", () => ({}));
jest.mock("@/context/AuthContext", () => ({}));
jest.mock("@/components/ui/sheet", () => ({
  SheetTitle: ({ children, ...props }) => <h2 {...props}>{children}</h2>,
  SheetDescription: ({ children, ...props }) => <p {...props}>{children}</p>,
}));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let container;
let root;
let onSave;
let onToggle;
const task = { id: "one", title: "Follow up with Jordan", status: "todo", due_date: "2026-11-12T14:00:00Z", assignee: null };
const get = (id) => container.querySelector(`[data-testid="${id}"]`);
const click = async (id) => act(async () => get(id).click());

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  onSave = jest.fn();
  onToggle = jest.fn();
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});
async function render(props = {}) {
  await act(async () => root.render(<TaskDetail task={task} now={new Date()} me="agent@example.com" isAdmin={false} team={[]}
    nameOf={(email) => email} busy={false} onSave={onSave} onToggle={onToggle} {...props} />));
}

test("one-hour preset crosses midnight without changing its source date", () => {
  const now = new Date(2026, 11, 31, 23, 30);
  const before = now.getTime();
  const result = new Date(taskSchedulePreset("hour", now));
  expect(result.getTime() - before).toBe(3600000);
  expect(result.getFullYear()).toBe(2027);
  expect(now.getTime()).toBe(before);
});

test.each([new Date(2026, 11, 31, 23, 30), new Date(2026, 2, 7, 12), new Date(2026, 9, 31, 12)])("tomorrow uses the next local calendar day at 9 am: %s", (now) => {
  const expected = new Date(now);
  expected.setDate(expected.getDate() + 1);
  const result = new Date(taskSchedulePreset("tomorrow", now));
  expect(result.toDateString()).toBe(expected.toDateString());
  expect([result.getHours(), result.getMinutes(), result.getSeconds()]).toEqual([9, 0, 0]);
});

test("clear removes a due date and unknown presets fail explicitly", () => {
  expect(taskSchedulePreset("clear")).toBeNull();
  expect(() => taskSchedulePreset("unknown")).toThrow("Unknown task schedule preset");
});

test("shortcuts prepare an editable draft and do not save automatically", async () => {
  await render();
  expect(get("task-detail-save").disabled).toBe(true);
  await click("task-schedule-tomorrow");
  expect(get("task-detail-due-time").value).toBe("09:00");
  expect(get("task-detail-save").disabled).toBe(false);
  expect(get("task-detail-toggle").disabled).toBe(true);
  expect(onSave).not.toHaveBeenCalled();
  await click("task-detail-save");
  expect(onSave).toHaveBeenCalledWith(task, { due_date: expect.any(String) });
  expect(new Date(onSave.mock.calls[0][1].due_date).getHours()).toBe(9);
});

test("discard restores both date and assignment without a server write", async () => {
  await render();
  const date = get("task-detail-due-date").value;
  const time = get("task-detail-due-time").value;
  await click("task-schedule-clear");
  await click("task-assign-me");
  expect(get("task-detail-due-date").value).toBe("");
  expect(get("task-detail-due-time").disabled).toBe(true);
  expect(get("task-assign-me")).toBeNull();
  expect(container.textContent).not.toContain("Unassigned — anyone on the team can take it.");
  await click("task-detail-discard");
  expect(get("task-detail-due-date").value).toBe(date);
  expect(get("task-detail-due-time").value).toBe(time);
  expect(get("task-assign-me")).not.toBeNull();
  expect(get("task-detail-save").disabled).toBe(true);
  expect(get("task-detail-toggle").disabled).toBe(false);
  expect(onSave).not.toHaveBeenCalled();
});

test("self-assignment and removing the due date save only the changed fields", async () => {
  await render({ isAdmin: true, team: [{ email: "other@example.com", name: "Other" }] });
  await click("task-schedule-clear");
  await click("task-assign-me");
  await click("task-detail-save");
  expect(onSave).toHaveBeenCalledWith(task, { due_date: null, assignee: "agent@example.com" });
});

test("busy state prevents edits, duplicate saves, discard and completion", async () => {
  await render({ busy: true });
  for (const id of ["task-schedule-hour", "task-schedule-tomorrow", "task-schedule-clear", "task-detail-save", "task-detail-discard", "task-detail-toggle", "task-assign-me", "task-detail-due-date", "task-detail-due-time", "task-detail-assignee"]) {
    expect(get(id).disabled).toBe(true);
  }
  await click("task-schedule-hour");
  await click("task-detail-save");
  expect(onSave).not.toHaveBeenCalled();
});

test("completion and reopening retain the existing task callback", async () => {
  await render();
  await click("task-detail-toggle");
  expect(onToggle).toHaveBeenCalledWith(task);
  const completed = { ...task, status: "done" };
  await render({ task: completed });
  expect(get("task-detail-toggle").textContent).toBe("Reopen");
  await click("task-detail-toggle");
  expect(onToggle).toHaveBeenLastCalledWith(completed);
});
