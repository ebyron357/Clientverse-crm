export const TASK_PAGE_SIZE = 200;
export const TASK_DONE_DAYS = 7;
export const TASK_BUCKET_KEYS = ["overdue", "today", "upcoming", "done"];
const OPEN_STATUSES = "todo,in_progress,blocked";
const DAY = 24 * 60 * 60 * 1000;

export function taskBoundaries(now = new Date()) {
  const tomorrow = new Date(now);
  tomorrow.setHours(0, 0, 0, 0);
  tomorrow.setDate(tomorrow.getDate() + 1);
  return { now, tomorrow, endOfToday: new Date(tomorrow.getTime() - 1) };
}

export function taskQuery(key, { now, tomorrow, endOfToday }) {
  if (key === "overdue") return { status: OPEN_STATUSES, due_before: new Date(now.getTime() - 1).toISOString() };
  if (key === "today") return { status: OPEN_STATUSES, due_after: now.toISOString(), due_before: endOfToday.toISOString() };
  if (key === "upcoming") return { status: OPEN_STATUSES, due_after: tomorrow.toISOString(), include_undated: true };
  return { status: "done", completed_after: new Date(now.getTime() - TASK_DONE_DAYS * DAY).toISOString(), sort: "completed_at", order: "desc" };
}

export function byTaskDue(a, b) {
  const first = a.due_date ? Date.parse(a.due_date) : NaN;
  const second = b.due_date ? Date.parse(b.due_date) : NaN;
  if (Number.isNaN(first) && Number.isNaN(second)) return 0;
  if (Number.isNaN(first)) return 1;
  if (Number.isNaN(second)) return -1;
  return first - second;
}
