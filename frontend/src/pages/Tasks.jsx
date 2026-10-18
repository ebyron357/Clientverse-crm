/* Tasks: every call-back and follow-up in one list, with what is late at the top.

   A website lead's "call within 5 minutes" task lands here the moment the lead arrives --
   assigned to someone or not -- and its clock ticks without a reload. The lists refresh
   every 30 seconds, like the Leads inbox. Ticking a lead's call-back task off marks the
   lead as contacted; un-ticking it puts the lead back in the queue if that tick was what
   marked it. A link to /tasks?task=<id> opens that task. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Avatar, PageHeader, PropertyList, Toolbar, ViewTabs } from "@/components/page/Page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { SurfaceEmpty, SurfaceError } from "@/components/SurfaceState";
import { AlarmClock, ArrowUpRight, Briefcase, Building2, CalendarClock, CheckCircle2, ChevronRight, CircleAlert, ListTodo, Pencil, Phone, Plus, RefreshCw, RotateCcw, Timer, User, UserRound, X, Zap } from "lucide-react";

const OPEN_STATUSES = "todo,in_progress,blocked";
const DONE_DAYS = 7;
const MINUTE = 60 * 1000;
const DAY = 24 * 60 * MINUTE;
const UNASSIGNED = "__unassigned__";
const PAGE = 200;

const TABS = [
  { key: "overdue", label: "Overdue", empty: "Nothing is overdue." },
  { key: "today", label: "Today", empty: "Nothing else is due today." },
  { key: "upcoming", label: "Upcoming", empty: "Nothing is planned after today." },
  { key: "done", label: "Done", empty: `Tasks you finish stay here for ${DONE_DAYS} days.` },
];

/** Rows are grouped by where the work stands, Linear-style; the tab already says when it is due. */
const GROUPS = [
  { key: "in_progress", label: "In progress" },
  { key: "todo", label: "To do" },
  { key: "blocked", label: "Waiting on something" },
  { key: "done", label: "Done" },
];
const STATUS_LABEL = { todo: "To do", in_progress: "In progress", blocked: "Waiting on something", done: "Done", cancelled: "Cancelled" };

const PRIORITY = {
  urgent: { label: "Urgent", bars: 0 },
  high: { label: "High", bars: 3 },
  medium: { label: "Medium", bars: 2 },
  low: { label: "Low", bars: 1 },
};

// ------------------------------------------------------------------ dates in words

function parseDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function startOfDay(date) {
  const day = new Date(date);
  day.setHours(0, 0, 0, 0);
  return day;
}

/** Now, the end of the local day, and the start of tomorrow: the edges of the tabs. */
function boundaries(now = new Date()) {
  const tomorrow = startOfDay(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  return { now, tomorrow, endOfToday: new Date(tomorrow.getTime() - 1) };
}

function span(ms) {
  const minutes = Math.max(1, Math.floor(Math.abs(ms) / MINUTE));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"}`;
}

const clock = (date) => date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

/** "Due in 3 min", "Overdue by 2 h", "Tomorrow 9:00 AM" -- never a raw timestamp. */
export function dueWords(value, now = new Date()) {
  const due = parseDate(value);
  if (!due) return { text: "No due date", tone: "none" };
  const diff = due.getTime() - now.getTime();
  if (diff < 0) return { text: `Overdue by ${span(diff)}`, tone: "overdue" };
  if (diff < 60 * MINUTE) return { text: `Due in ${span(diff)}`, tone: "soon" };
  const days = Math.round((startOfDay(due) - startOfDay(now)) / DAY);
  if (days === 0) return { text: `Today ${clock(due)}`, tone: "today" };
  if (days === 1) return { text: `Tomorrow ${clock(due)}`, tone: "later" };
  if (days < 7) return { text: `${due.toLocaleDateString([], { weekday: "long" })} ${clock(due)}`, tone: "later" };
  const sameYear = due.getFullYear() === now.getFullYear();
  const date = due.toLocaleDateString([], { month: "short", day: "numeric", ...(sameYear ? {} : { year: "numeric" }) });
  return { text: `${date}, ${clock(due)}`, tone: "later" };
}

function doneWords(task, now = new Date()) {
  const completed = parseDate(task.completed_at);
  return completed ? `Done ${span(now - completed)} ago` : "Done";
}

function agoWords(value, now = new Date()) {
  const date = parseDate(value);
  if (!date) return "";
  const diff = now - date;
  if (diff < MINUTE) return "just now";
  if (diff < 7 * DAY) return `${span(diff)} ago`;
  return date.toLocaleDateString([], { month: "short", day: "numeric", ...(date.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }) });
}

const stamp = (date) => `${date.toLocaleDateString([], { month: "short", day: "numeric" })}, ${clock(date)}`;

/** Which tab a task belongs in right now. */
function bucketOf(task, now = new Date()) {
  if (task.status === "done") return "done";
  if (task.status === "cancelled") return null;
  const due = parseDate(task.due_date);
  if (!due) return "upcoming";
  if (due < now) return "overdue";
  return due < boundaries(now).tomorrow ? "today" : "upcoming";
}

function tabQuery(key, { now, tomorrow, endOfToday }) {
  if (key === "overdue") return { status: OPEN_STATUSES, due_before: new Date(now.getTime() - 1).toISOString() };
  if (key === "today") return { status: OPEN_STATUSES, due_after: now.toISOString(), due_before: endOfToday.toISOString() };
  if (key === "upcoming") return { status: OPEN_STATUSES, due_after: tomorrow.toISOString(), include_undated: true };
  return { status: "done", completed_after: new Date(now.getTime() - DONE_DAYS * DAY).toISOString(), sort: "completed_at", order: "desc" };
}

/** Soonest first; tasks with no date at the end. */
function byDue(a, b) {
  const first = parseDate(a.due_date);
  const second = parseDate(b.due_date);
  if (!first && !second) return 0;
  if (!first) return 1;
  if (!second) return -1;
  return first - second;
}

function toLocalInputs(value) {
  const date = parseDate(value);
  if (!date) return { date: "", time: "" };
  const pad = (number) => String(number).padStart(2, "0");
  return { date: `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`, time: `${pad(date.getHours())}:${pad(date.getMinutes())}` };
}

function fromLocalInputs(date, time) {
  if (!date) return null;
  const [year, month, day] = date.split("-").map(Number);
  const [hour, minute] = (time || "09:00").split(":").map(Number);
  const local = new Date(year, month - 1, day, hour, minute);
  return Number.isNaN(local.getTime()) ? null : local.toISOString();
}

function nextHour() {
  const date = new Date();
  date.setMinutes(0, 0, 0);
  date.setHours(date.getHours() + 1);
  return toLocalInputs(date.toISOString());
}

// ------------------------------------------------------------------ people and records

const samePerson = (first, second) => Boolean(first && second) && String(first).trim().toLowerCase() === String(second).trim().toLowerCase();
const telHref = (phone) => `tel:${String(phone).replace(/[^\d+]/g, "")}`;

/** What a task is about, as a label and a link -- never a raw id. */
function aboutOf(task) {
  const related = task.related || {};
  if (related.lead_id) {
    return { kind: "lead", label: "Website lead", name: related.contact?.name || related.name || "Open the lead", to: `/leads?lead=${encodeURIComponent(related.lead_id)}` };
  }
  const routes = {
    contact: { kind: "contact", label: "Contact", to: (id) => `/contacts?contact=${id}` },
    deal: { kind: "deal", label: "Deal", to: (id) => `/deals?deal=${id}` },
    company: { kind: "company", label: "Company", to: (id) => `/companies?company=${id}` },
    workspace: { kind: "client", label: "Client", to: (id) => `/workspaces/${id}` },
  };
  const route = routes[related.type];
  if (!route || !related.id) return null;
  if (!related.name) return { ...route, name: "No longer available", to: null };
  return { ...route, name: related.name, to: route.to(encodeURIComponent(related.id)) };
}

const ABOUT_ICON = { lead: Zap, contact: User, deal: Briefcase, company: Building2, client: Building2 };

function assigneeChoices({ me, isAdmin, team, current }) {
  const choices = isAdmin && team.length
    ? team.map((member) => ({ value: member.email, label: samePerson(member.email, me) ? `${member.name} (you)` : member.name }))
    : [{ value: me, label: "Me" }];
  if (current && !choices.some((choice) => samePerson(choice.value, current))) choices.push({ value: current, label: current });
  return [...choices, { value: UNASSIGNED, label: "Unassigned" }];
}

function choiceFor(choices, assignee) {
  return choices.find((choice) => choice.value !== UNASSIGNED && samePerson(choice.value, assignee))?.value || UNASSIGNED;
}

// ------------------------------------------------------------------ icons

/** Linear-style status glyph: an open ring, a half-filled ring, a paused ring, a filled check. */
function StatusIcon({ status, className = "" }) {
  const common = { viewBox: "0 0 16 16", "aria-hidden": true, className: `size-4 shrink-0 ${className}` };
  if (status === "done") {
    return <svg {...common} className={`${common.className} text-emerald-600`}><circle cx="8" cy="8" r="7" fill="currentColor" /><path d="M5 8.2 7 10.2 11 6" fill="none" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className="stroke-card" /></svg>;
  }
  if (status === "in_progress") {
    return <svg {...common} className={`${common.className} text-brand`}><circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M8 4.25a3.75 3.75 0 0 1 0 7.5z" fill="currentColor" /></svg>;
  }
  if (status === "blocked") {
    return <svg {...common} className={`${common.className} text-violet-600`}><circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M6.5 5.75v4.5M9.5 5.75v4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>;
  }
  return <svg {...common} className={`${common.className} text-muted-foreground`}><circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>;
}

/** Signal bars for high / medium / low, a soft red mark for urgent; nothing when it has none. */
function PriorityIcon({ priority, className = "" }) {
  const meta = PRIORITY[priority];
  if (!meta) return <span className={`inline-block size-4 shrink-0 ${className}`} aria-hidden="true" />;
  const label = `${meta.label} priority`;
  if (priority === "urgent") {
    return <svg viewBox="0 0 16 16" role="img" aria-label={label} className={`size-4 shrink-0 text-red-600 ${className}`}>
      <title>{label}</title>
      <rect x="1.5" y="1.5" width="13" height="13" rx="3.5" fill="currentColor" />
      <path d="M8 4.5v4.25" strokeWidth="1.8" strokeLinecap="round" className="stroke-card" /><circle cx="8" cy="11.25" r="1" className="fill-card" />
    </svg>;
  }
  return <svg viewBox="0 0 16 16" role="img" aria-label={label} className={`size-4 shrink-0 text-foreground/70 ${className}`}>
    <title>{label}</title>
    {[0, 1, 2].map((index) => <rect key={index} x={2 + index * 4.5} y={10 - index * 3} width="3" height={4 + index * 3} rx="1" fill="currentColor" opacity={index < meta.bars ? 1 : 0.22} />)}
  </svg>;
}

// ------------------------------------------------------------------ pieces

function DueText({ task, now, className = "" }) {
  const base = `shrink-0 whitespace-nowrap ${className}`;
  if (task.status === "done") return <span className={`text-muted-foreground ${base}`}>{doneWords(task, now)}</span>;
  const due = dueWords(task.due_date, now);
  if (due.tone === "overdue") return <span className={`inline-flex items-center gap-1 font-medium text-red-700 ${base}`}><AlarmClock className="size-3.5 shrink-0" aria-hidden="true" />{due.text}</span>;
  if (due.tone === "soon") return <span className={`inline-flex items-center gap-1 text-amber-700 ${base}`}><Timer className="size-3.5 shrink-0" aria-hidden="true" />{due.text}</span>;
  return <span className={`text-muted-foreground ${base}`}>{due.text}</span>;
}

function AssigneeMark({ email, name }) {
  if (!email) {
    return <span className="inline-flex size-6 shrink-0 items-center justify-center rounded-full border border-dashed border-muted-foreground/50 text-muted-foreground" title="Unassigned">
      <UserRound className="size-3" aria-hidden="true" /><span className="sr-only">Unassigned</span>
    </span>;
  }
  const words = name === "You" ? "Assigned to you" : `Assigned to ${name}`;
  return <span className="inline-flex" title={words}><Avatar name={name} size="sm" /><span className="sr-only">{words}</span></span>;
}

function TaskRow({ task, now, avatarName, busy, highlighted, onToggle, onOpen }) {
  const done = task.status === "done";
  const about = aboutOf(task);
  const contact = task.related?.contact;
  const AboutIcon = ABOUT_ICON[about?.kind] || ArrowUpRight;
  return (
    <li id={`task-${task.id}`} data-testid={`task-row-${task.id}`}
      className={`group relative flex items-center gap-2.5 border-b border-border/70 px-3 py-2 transition-colors last:border-0 hover:bg-muted/50 sm:px-4 ${highlighted ? "bg-brand-soft/60 hover:bg-brand-soft/60" : ""}`}>
      <button type="button" onClick={() => onToggle(task)} disabled={busy} aria-pressed={done}
        aria-label={done ? `Reopen: ${task.title}` : `Mark done: ${task.title}`}
        className="relative z-10 -ml-1 flex size-7 shrink-0 items-center justify-center rounded-full transition-colors hover:bg-muted disabled:opacity-50"
        data-testid={`task-toggle-${task.id}`}>
        <StatusIcon status={task.status} />
      </button>
      <div className="flex min-w-0 flex-1 flex-col sm:flex-row sm:items-center sm:gap-2.5">
        {/* The title is the row's link: its hit area stretches over the whole row. */}
        <button type="button" onClick={() => onOpen(task)} data-testid={`task-open-${task.id}`}
          className={`min-w-0 text-left text-[13px] font-medium leading-5 after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-inset focus-visible:after:ring-ring ${done ? "text-muted-foreground line-through decoration-muted-foreground/50" : "text-foreground"}`}>
          <span className="line-clamp-2 break-words sm:line-clamp-1">{task.title}</span>
        </button>
        <div className="mt-0.5 flex min-w-0 items-center gap-2 text-xs sm:mt-0 sm:shrink-0">
          <DueText task={task} now={now} className="sm:hidden" />
          {about && (about.to
            ? <Link to={about.to} data-testid={`task-about-${task.id}`}
                className="relative z-10 inline-flex h-6 min-w-0 max-w-[13rem] items-center gap-1 rounded-md border border-border px-1.5 text-muted-foreground transition-colors hover:border-input hover:text-foreground">
                <AboutIcon className="size-3 shrink-0" aria-hidden="true" /><span className="sr-only">{about.label}: </span><span className="truncate">{about.name}</span>
                {about.kind === "deal" && contact?.name ? <span className="hidden truncate md:inline">· {contact.name}</span> : null}
              </Link>
            : <span className="inline-flex h-6 min-w-0 items-center gap-1 px-1.5 text-muted-foreground"><span className="truncate">{about.label}: {about.name}</span></span>)}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2.5 sm:gap-3">
        <PriorityIcon priority={task.priority} className="hidden sm:block" />
        <DueText task={task} now={now} className="tabular hidden w-[8.75rem] justify-end text-right text-xs sm:inline-flex" />
        <AssigneeMark email={task.assignee} name={task.assignee ? avatarName(task.assignee) : null} />
        {contact?.phone && !done
          ? <Button asChild size="sm" variant="ghost" className="relative z-10 size-7 px-0 text-muted-foreground hover:text-foreground">
              <a href={telHref(contact.phone)} aria-label={`Call ${contact.name || "them"} at ${contact.phone}`} title={`Call ${contact.phone}`} data-testid={`task-call-${task.id}`}>
                <Phone aria-hidden="true" />
              </a>
            </Button>
          : <span className="hidden size-7 sm:block" aria-hidden="true" />}
      </div>
    </li>
  );
}

function createdLine(task, nameOf) {
  const created = parseDate(task.created_at);
  const when = created ? stamp(created) : "";
  const automatic = String(task.created_by || "").startsWith("system:");
  const lead = task.source && typeof task.source === "object" && task.source.kind === "website_form";
  const creator = task.created_by ? nameOf(task.created_by) : null;
  const who = automatic ? (lead ? "Added automatically when the lead came in" : "Added automatically")
    : creator ? `Added by ${creator === "You" ? "you" : creator}` : "Added";
  return when ? `${who} · ${when}` : who;
}

/** The task's history as sentences, oldest first. Each change records what it changed
    *from*; walking back from the task as it is now tells us what it changed *to*. */
function taskActivity(task, nameOf) {
  const actor = (email) => {
    if (!email) return "Someone";
    if (String(email).startsWith("system:")) return "ClientVerse";
    return nameOf(email);
  };
  const person = (email) => { const name = nameOf(email); return name === "You" ? "you" : name; };
  const history = Array.isArray(task.history) ? task.history : [];
  if (!history.length) {
    const fallback = [];
    if (task.created_at) fallback.push({ key: "created", at: task.created_at, icon: Plus, text: createdLine(task, nameOf).split(" · ")[0] });
    if (task.completed_at) fallback.push({ key: "completed", at: task.completed_at, status: "done", text: "Marked done" });
    return fallback;
  }
  const current = { status: task.status, due_date: task.due_date, assignee: task.assignee, priority: task.priority, title: task.title, notes: task.notes };
  const out = [];
  for (let index = history.length - 1; index >= 0; index -= 1) {
    const entry = history[index] || {};
    const who = actor(entry.actor);
    const key = `${index}`;
    if (entry.action === "created" || entry.action === "imported") {
      const lead = task.source && typeof task.source === "object" && task.source.kind === "website_form";
      const automatic = String(entry.actor || "").startsWith("system:");
      out.push({ key, at: entry.at, icon: Plus, text: automatic ? (lead ? "Added automatically when the lead came in" : "Added automatically") : `${who} ${entry.action === "imported" ? "imported" : "created"} the task` });
      continue;
    }
    if (entry.action === "completed") {
      out.push({ key, at: entry.at, status: "done", text: `${who} marked it done` });
      current.status = undefined;
      continue;
    }
    const changed = entry.detail?.changed || [];
    const from = entry.detail?.from || {};
    if (!changed.length) { out.push({ key, at: entry.at, icon: Pencil, text: `${who} updated the task` }); continue; }
    changed.forEach((field) => {
      const to = current[field];
      const was = from[field];
      let line;
      if (field === "status") {
        line = to === "done" ? { status: "done", text: `${who} marked it done` }
          : was === "done" ? { icon: RotateCcw, text: `${who} reopened it` }
            : { status: to, text: to ? `${who} moved it to ${STATUS_LABEL[to] || to}` : `${who} changed the status` };
      } else if (field === "due_date") {
        const date = parseDate(to);
        line = { icon: CalendarClock, text: date ? `${who} set the due date to ${stamp(date)}` : to === undefined ? `${who} changed the due date` : `${who} removed the due date` };
      } else if (field === "assignee") {
        const took = to && samePerson(to, entry.actor);
        line = { icon: UserRound, text: took ? `${who} took the task` : to ? `${who} assigned it to ${person(to)}` : to === undefined ? `${who} changed who it is assigned to` : `${who} unassigned it` };
      } else if (field === "priority") {
        line = { icon: Pencil, text: PRIORITY[to] ? `${who} set the priority to ${PRIORITY[to].label.toLowerCase()}` : `${who} changed the priority` };
      } else if (field === "title") {
        line = { icon: Pencil, text: `${who} renamed it` };
      } else if (field === "notes") {
        line = { icon: Pencil, text: `${who} edited the notes` };
      } else {
        line = { icon: Pencil, text: `${who} changed the ${field.replace(/_/g, " ")}` };
      }
      out.push({ key: `${key}-${field}`, at: entry.at, ...line });
      current[field] = was;
    });
  }
  return out.reverse();
}

function ActivityList({ entries, now }) {
  if (!entries.length) return <p className="text-[13px] text-muted-foreground">Nothing has happened to this task yet.</p>;
  return <ol>
    {entries.map(({ key, at, icon: Icon, status, text }) => <li key={key} className="relative flex gap-3 pb-4 before:absolute before:bottom-0 before:left-[11px] before:top-7 before:w-px before:bg-border last:pb-0 last:before:hidden">
      <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border border-border bg-card">
        {status ? <StatusIcon status={status} className="size-3.5" /> : <Icon className="size-3.5 text-muted-foreground" aria-hidden="true" />}
      </span>
      <div className="min-w-0 pt-0.5 text-[13px] leading-5">
        <span className="text-foreground/90">{text}</span>
        {at && <time dateTime={at} title={parseDate(at)?.toLocaleString()} className="ml-1.5 whitespace-nowrap text-xs text-muted-foreground">{agoWords(at, now)}</time>}
      </div>
    </li>)}
  </ol>;
}

/** One task, laid out like an issue: what it is and what happened on the left, its properties on the right. */
function TaskDetail({ task, now, me, isAdmin, team, nameOf, busy, tabLabel, onToggle, onSave }) {
  const initial = toLocalInputs(task.due_date);
  const choices = assigneeChoices({ me, isAdmin, team, current: task.assignee });
  const [date, setDate] = useState(initial.date);
  const [time, setTime] = useState(initial.time);
  const [assignee, setAssignee] = useState(choiceFor(choices, task.assignee));
  const [touched, setTouched] = useState({ due: false, assignee: false });
  const done = task.status === "done";
  const about = aboutOf(task);
  const contact = task.related?.contact;
  const activity = useMemo(() => taskActivity(task, nameOf), [task, nameOf]);
  const priority = PRIORITY[task.priority];
  const AboutIcon = ABOUT_ICON[about?.kind] || ArrowUpRight;

  const save = () => {
    const changes = {};
    if (touched.due) changes.due_date = fromLocalInputs(date, time);
    if (touched.assignee) changes.assignee = assignee === UNASSIGNED ? null : assignee;
    onSave(task, changes);
  };

  const field = "h-8 text-[13px]";
  const properties = [
    { label: "Status", value: <span className="inline-flex items-center gap-2"><StatusIcon status={task.status} />{STATUS_LABEL[task.status] || task.status}</span> },
    { label: "Priority", value: priority ? <span className="inline-flex items-center gap-2"><PriorityIcon priority={task.priority} />{priority.label}</span> : <span className="text-muted-foreground">No priority</span> },
    { label: "Due", value: <DueText task={task} now={now} /> },
    {
      label: "Assignee", value: (
        <Select value={assignee} onValueChange={(value) => { setAssignee(value); setTouched((current) => ({ ...current, assignee: true })); }}>
          <SelectTrigger id="task-assignee" aria-label="Assigned to" className={`${field} -ml-2 w-[calc(100%+0.5rem)] border-transparent bg-transparent px-2 shadow-none hover:bg-muted/60 focus:border-input`} data-testid="task-detail-assignee"><SelectValue /></SelectTrigger>
          <SelectContent>{choices.map((choice) => <SelectItem key={choice.value} value={choice.value}>{choice.label}</SelectItem>)}</SelectContent>
        </Select>
      ),
    },
    { label: "Due date", value: <Input id="task-due-date" type="date" aria-label="Due date" value={date} onChange={(event) => { setDate(event.target.value); setTouched((value) => ({ ...value, due: true })); }} className={field} data-testid="task-detail-due-date" /> },
    { label: "Time", value: <Input id="task-due-time" type="time" aria-label="Due time" value={time} onChange={(event) => { setTime(event.target.value); setTouched((value) => ({ ...value, due: true })); }} className={field} data-testid="task-detail-due-time" /> },
    { label: "Linked to", value: about ? (about.to
      ? <Link to={about.to} className="inline-flex max-w-full items-center gap-1.5 font-medium text-brand hover:underline"><AboutIcon className="size-3.5 shrink-0" aria-hidden="true" /><span className="truncate">{about.name}</span></Link>
      : <span className="text-muted-foreground">{about.name}</span>) : null },
    { label: "Person", value: contact?.name ? <span>{contact.name}{[contact.phone, contact.email].filter(Boolean).length ? <span className="block text-xs text-muted-foreground">{[contact.phone, contact.email].filter(Boolean).join(" · ")}</span> : null}</span> : null },
    { label: "Created", value: parseDate(task.created_at) ? stamp(parseDate(task.created_at)) : null },
  ].filter(({ value }) => value != null);

  return (
    <div className="flex min-h-full flex-col" data-testid="task-detail">
      <div className="flex h-12 shrink-0 items-center gap-1.5 border-b border-border px-5 pr-14 text-[13px] text-muted-foreground sm:px-6">
        <ListTodo className="size-4" aria-hidden="true" />Tasks<ChevronRight className="size-3.5" aria-hidden="true" /><span className="text-foreground">{tabLabel || STATUS_LABEL[task.status] || "Task"}</span>
      </div>
      <div className="grid flex-1 lg:grid-cols-[minmax(0,1fr)_320px] lg:grid-rows-[auto_1fr]">
        <div className="min-w-0 px-5 pb-6 pt-6 sm:px-7">
          <SheetTitle className="break-words text-xl font-semibold leading-7 tracking-tight">{task.title}</SheetTitle>
          <SheetDescription className="mt-1 text-[13px]">{about ? `${about.label}: ${about.name}` : "A follow-up task"}</SheetDescription>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button size="sm" variant={done ? "outline" : "default"} disabled={busy} onClick={() => onToggle(task)} data-testid="task-detail-toggle">
              {done ? <><RotateCcw aria-hidden="true" />Reopen</> : <><CheckCircle2 aria-hidden="true" />Mark done</>}
            </Button>
            {contact?.phone && (
              <Button asChild size="sm" variant="outline">
                <a href={telHref(contact.phone)} data-testid="task-detail-call"><Phone aria-hidden="true" />Call {contact.phone}</a>
              </Button>
            )}
            {about?.to && <Button asChild size="sm" variant="outline"><Link to={about.to} data-testid="task-detail-about"><ArrowUpRight aria-hidden="true" />Open the {about.kind}</Link></Button>}
          </div>
          <div className="mt-6">
            {task.notes
              ? <p className="whitespace-pre-wrap break-words text-sm leading-6 text-foreground/90">{task.notes}</p>
              : <p className="text-sm text-muted-foreground">No notes on this task.</p>}
          </div>
        </div>

        <aside className="border-y border-border bg-muted/20 px-5 py-5 sm:px-6 lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:border-y-0 lg:border-l lg:px-5">
          <h3 className="mb-1.5 text-xs font-medium text-muted-foreground">Properties</h3>
          <PropertyList className="[&>div]:grid-cols-[84px_minmax(0,1fr)] [&>div]:items-center [&>div]:min-h-[2.5rem]" items={properties} />
          <Button size="sm" className="mt-4 w-full" disabled={busy || (!touched.due && !touched.assignee)} onClick={save} data-testid="task-detail-save">Save changes</Button>
          {!task.assignee && <p className="mt-3 text-xs text-muted-foreground">Unassigned — anyone on the team can take it.</p>}
          {!isAdmin && <p className="mt-2 text-xs text-muted-foreground">Only admins can see the team list, so you can take a task yourself or leave it unassigned.</p>}
        </aside>

        <section className="min-w-0 border-border px-5 pb-10 pt-6 sm:px-7 lg:border-t" aria-label="Activity">
          <h3 className="mb-4 text-sm font-semibold text-foreground">Activity</h3>
          <ActivityList entries={activity} now={now} />
        </section>
      </div>
    </div>
  );
}

function ContactPicker({ value, onChange }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    const term = query.trim();
    if (value || term.length < 2) { setResults([]); return undefined; }
    let cancelled = false;
    const handle = setTimeout(async () => {
      setSearching(true);
      try {
        const { data } = await api.get("/contacts", { params: { q: term, limit: 8 } });
        if (!cancelled) setResults(Array.isArray(data) ? data : data?.items || []);
      } catch {
        if (!cancelled) setResults([]);
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, 250);
    return () => { cancelled = true; clearTimeout(handle); };
  }, [query, value]);

  if (value) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-lg border border-border bg-muted/40 py-1 pl-2.5 pr-1 text-[13px]">
        <span className="flex min-w-0 items-center gap-2 text-foreground"><Avatar name={value.name} size="sm" /><span className="min-w-0 break-words"><span className="font-medium">{value.name}</span><span className="text-muted-foreground">{value.phone ? ` · ${value.phone}` : value.email ? ` · ${value.email}` : ""}</span></span></span>
        <Button type="button" size="sm" variant="ghost" className="size-7 px-0" onClick={() => onChange(null)} aria-label={`Remove ${value.name}`} data-testid="new-task-contact-clear"><X aria-hidden="true" /></Button>
      </div>
    );
  }
  return (
    <div className="space-y-1.5">
      <Input id="new-task-contact" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Type a name, email or phone" autoComplete="off" data-testid="new-task-contact-search" />
      {searching && <p className="text-xs text-muted-foreground">Searching…</p>}
      {!searching && query.trim().length >= 2 && results.length === 0 && <p className="text-xs text-muted-foreground">No contact matches “{query.trim()}”.</p>}
      {results.length > 0 && (
        <ul className="max-h-48 overflow-y-auto rounded-lg border border-border">
          {results.map((contact) => (
            <li key={contact.id} className="border-b border-border/70 last:border-0">
              <button type="button" onClick={() => { onChange(contact); setQuery(""); }} className="flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-muted/50" data-testid={`new-task-contact-option-${contact.id}`}>
                <Avatar name={contact.name} size="sm" />
                <span className="min-w-0">
                  <span className="block text-[13px] font-medium text-foreground">{contact.name}</span>
                  <span className="block text-xs text-muted-foreground">{[contact.phone, contact.email].filter(Boolean).join(" · ") || "No phone or email yet"}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function NewTaskForm({ me, isAdmin, team, onCreated, onCancel }) {
  const choices = assigneeChoices({ me, isAdmin, team, current: null });
  const start = nextHour();
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(start.date);
  const [time, setTime] = useState(start.time);
  const [assignee, setAssignee] = useState(choiceFor(choices, me));
  const [contact, setContact] = useState(null);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (!title.trim()) { toast.error("Give the task a short title, like “Call Jane about Saturday’s showing”."); return; }
    setSaving(true);
    try {
      const { data } = await api.post("/crm/tasks", {
        title: title.trim(), due_date: fromLocalInputs(date, time),
        assignee: assignee === UNASSIGNED ? null : assignee,
        ...(contact ? { related_type: "contact", related_id: contact.id } : {}),
        notes: notes.trim() || undefined,
      });
      onCreated(data);
    } catch (error) {
      toast.error("The task could not be added", { description: formatErr(error.response?.data?.detail) });
    } finally { setSaving(false); }
  };

  return (
    <form onSubmit={submit} className="grid gap-4 pt-1">
      <div className="grid gap-1.5">
        <Label htmlFor="new-task-title">What needs doing <span className="text-red-600" aria-hidden="true">*</span></Label>
        <Input id="new-task-title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. Call Jane about Saturday’s showing" data-testid="new-task-title" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="new-task-date">Due date</Label>
          <Input id="new-task-date" type="date" value={date} onChange={(event) => setDate(event.target.value)} data-testid="new-task-date" />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="new-task-time">Time</Label>
          <Input id="new-task-time" type="time" value={time} onChange={(event) => setTime(event.target.value)} data-testid="new-task-time" />
        </div>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="new-task-assignee">Assign to</Label>
        <Select value={assignee} onValueChange={setAssignee}>
          <SelectTrigger id="new-task-assignee" aria-label="Assign to" data-testid="new-task-assignee"><SelectValue /></SelectTrigger>
          <SelectContent>{choices.map((choice) => <SelectItem key={choice.value} value={choice.value}>{choice.label}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="new-task-contact">Who it’s about (optional)</Label>
        <ContactPicker value={contact} onChange={setContact} />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="new-task-notes">Notes (optional)</Label>
        <Textarea id="new-task-notes" value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} placeholder="Anything you’ll want to remember when you do it" data-testid="new-task-notes" />
      </div>
      <DialogFooter className="gap-2 pt-1">
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>Cancel</Button>
        <Button type="submit" size="sm" disabled={saving} data-testid="new-task-submit">{saving ? "Adding…" : "Add task"}</Button>
      </DialogFooter>
    </form>
  );
}

// ------------------------------------------------------------------ the page

export default function Tasks() {
  const { user } = useAuth();
  const me = user?.email || "";
  const isAdmin = user?.role === "admin";
  const [searchParams, setSearchParams] = useSearchParams();
  const focusId = searchParams.get("task");
  const [view, setView] = useState("mine");
  const [tab, setTab] = useState(null);
  const [buckets, setBuckets] = useState(null);
  const [error, setError] = useState("");
  const [team, setTeam] = useState([]);
  const [busyId, setBusyId] = useState(null);
  const [creating, setCreating] = useState(false);
  const [fetched, setFetched] = useState(null);
  const [, setTick] = useState(0);
  const loadSeq = useRef(0);
  const ready = buckets !== null;

  const load = useCallback(async () => {
    const sequence = ++loadSeq.current;
    const bounds = boundaries();
    const scope = view === "mine" ? { mine: true, include_unassigned: true } : {};
    try {
      const pages = await Promise.all(TABS.map(({ key }) => api.get("/tasks", {
        params: { sort: "due_date", order: "asc", ...tabQuery(key, bounds), ...scope, expand: "related", limit: PAGE },
      })));
      if (sequence !== loadSeq.current) return;
      const next = Object.fromEntries(TABS.map(({ key }, index) => {
        const { items, total } = pages[index].data;
        return [key, { items: key === "upcoming" ? [...items].sort(byDue) : items, total }];
      }));
      setBuckets(next);
      setError("");
      // Open on the most pressing list that has something in it, then leave the choice alone.
      setTab((current) => current || TABS.slice(0, 3).find(({ key }) => next[key].total > 0)?.key || "today");
    } catch (e) {
      if (sequence !== loadSeq.current) return;
      setError(e.response?.data?.detail ? formatErr(e.response.data.detail) : "Tasks could not be loaded. Check your connection and try again.");
    }
  }, [view]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const refresh = setInterval(load, 30000);
    const tick = setInterval(() => setTick((value) => value + 1), 15000);
    return () => { clearInterval(refresh); clearInterval(tick); };
  }, [load]);
  useEffect(() => {
    // The team list is admin-only on the server; members assign to themselves.
    if (!isAdmin) return;
    api.get("/team/members")
      .then(({ data }) => setTeam((data || []).filter((member) => member.status === "active" && member.email)
        .map((member) => ({ email: member.email, name: member.name || member.email }))))
      .catch(() => setTeam([]));
  }, [isAdmin]);

  // A link naming a task: fetch it, open the tab (and, for an admin, the view) it is in.
  useEffect(() => {
    if (!focusId) return undefined;
    let cancelled = false;
    api.get(`/crm/tasks/${encodeURIComponent(focusId)}`).then(({ data }) => {
      if (cancelled) return;
      setFetched(data);
      const bucket = bucketOf(data);
      if (bucket) setTab(bucket);
      if (isAdmin && data.assignee && !samePerson(data.assignee, me)) setView("everyone");
    }).catch(() => {
      if (cancelled) return;
      toast.error("That task could not be found. It may have been removed.");
      setSearchParams((params) => { params.delete("task"); return params; }, { replace: true });
    });
    return () => { cancelled = true; };
  }, [focusId, isAdmin, me, setSearchParams]);

  useEffect(() => {
    if (!focusId || !ready) return;
    document.getElementById(`task-${focusId}`)?.scrollIntoView?.({ block: "center", behavior: "smooth" });
  }, [focusId, tab, ready]);

  const focused = useMemo(() => {
    if (!focusId) return null;
    for (const { key } of TABS) {
      const hit = buckets?.[key]?.items.find((task) => task.id === focusId);
      if (hit) return hit;
    }
    return fetched?.id === focusId ? fetched : null;
  }, [focusId, buckets, fetched]);

  const nameOf = useCallback((email) => {
    if (samePerson(email, me)) return "You";
    return team.find((member) => samePerson(member.email, email))?.name || email;
  }, [me, team]);
  // Initials want a real name, so "You" becomes the signed-in person's own.
  const avatarName = useCallback((email) => (samePerson(email, me) ? user?.name || email : nameOf(email)), [me, user, nameOf]);

  const open = (task) => setSearchParams((params) => { params.set("task", task.id); return params; });
  const close = () => setSearchParams((params) => { params.delete("task"); return params; });
  const switchView = (next) => { if (next === view) return; setBuckets(null); setView(next); };

  const setStatus = async (task, status, { undo = false } = {}) => {
    setBusyId(task.id);
    try {
      const { data } = await api.patch(`/crm/tasks/${task.id}`, { status });
      const updated = { ...task, ...data, related: task.related };
      setFetched((current) => (current?.id === task.id ? updated : current));
      if (focusId === task.id) { const bucket = bucketOf(updated); if (bucket) setTab(bucket); }
      const leadId = task.related?.lead_id;
      let description;
      if (leadId && status === "done") description = "The lead is marked as contacted.";
      if (leadId && status !== "done") {
        const lead = await api.get(`/leads/${encodeURIComponent(leadId)}`).then((response) => response.data).catch(() => null);
        description = lead?.status === "new" ? "The lead is back to waiting for a call." : "The lead stays marked as contacted.";
      }
      if (undo) toast.success("Undone", { description });
      else {
        toast.success(status === "done" ? `Done: ${task.title}` : `Reopened: ${task.title}`, {
          description,
          action: { label: "Undo", onClick: () => setStatus(updated, task.status || "todo", { undo: true }) },
        });
      }
      await load();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail));
    } finally { setBusyId(null); }
  };

  const toggle = (task) => setStatus(task, task.status === "done" ? "todo" : "done");

  const save = async (task, changes) => {
    if (!Object.keys(changes).length) return;
    setBusyId(task.id);
    try {
      const { data } = await api.patch(`/crm/tasks/${task.id}`, changes);
      const updated = { ...task, ...data, related: task.related };
      setFetched(updated);
      const bucket = bucketOf(updated);
      if (bucket) setTab(bucket);
      toast.success("Changes saved", { description: "assignee" in changes && changes.assignee && !samePerson(changes.assignee, me) ? `${nameOf(changes.assignee)} will see it in their tasks.` : undefined });
      await load();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail));
    } finally { setBusyId(null); }
  };

  const created = (task) => {
    setCreating(false);
    const bucket = bucketOf(task);
    if (bucket) setTab(bucket);
    const theirs = task.assignee && !samePerson(task.assignee, me);
    toast.success("Task added", { description: theirs ? `${nameOf(task.assignee)} will see it in their tasks.` : undefined });
    load();
  };

  const now = new Date();
  const current = tab && buckets ? buckets[tab] : null;
  const activeTab = TABS.find(({ key }) => key === tab);
  const groups = useMemo(() => {
    if (!current) return [];
    const known = new Set(GROUPS.map(({ key }) => key));
    return GROUPS.map((group) => ({ ...group, items: current.items.filter((task) => (known.has(task.status) ? task.status : "todo") === group.key) }))
      .filter((group) => group.items.length);
  }, [current]);

  const tabs = TABS.map(({ key, label }) => {
    const count = buckets?.[key]?.total;
    const alarm = key === "overdue" && count > 0;
    return { value: key, label, testid: `tasks-tab-${key}`, count: count == null ? "–" : alarm ? <span className="font-medium text-red-700">{count}</span> : count };
  });

  return (
    <div className="cv-page" data-testid="tasks-page">
      <PageHeader icon={ListTodo} title="Tasks"
        description="Every call-back and follow-up in one place, with what is late at the top."
        actions={<>
          <Button variant="outline" size="sm" className="w-8 px-0" onClick={load} aria-label="Refresh tasks" title="Refresh" data-testid="tasks-refresh"><RefreshCw aria-hidden="true" /></Button>
          <Button size="sm" onClick={() => setCreating(true)} data-testid="tasks-new"><Plus aria-hidden="true" />New task</Button>
        </>} />

      <ViewTabs label="Tasks by when they are due" items={tabs} value={tab} onChange={setTab} />
      <Toolbar>
        {isAdmin ? (
          <div role="group" aria-label="Whose tasks to show" className="inline-flex h-8 items-center rounded-lg border border-border bg-card p-0.5 text-[13px] font-medium">
            {[["mine", "My tasks"], ["everyone", "Everyone"]].map(([key, label]) => (
              <button key={key} type="button" aria-pressed={view === key} onClick={() => switchView(key)}
                className={`h-full rounded-md px-2.5 transition-colors ${view === key ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"}`}
                data-testid={`tasks-view-${key}`}>{label}</button>
            ))}
          </div>
        ) : null}
        <p className="text-xs text-muted-foreground">
          {view === "mine" ? "Tasks assigned to you, plus any nobody has taken yet." : "Every task on the team."}
        </p>
      </Toolbar>

      {error && buckets && <div className="mb-3 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-700" role="status"><CircleAlert className="size-4 shrink-0" aria-hidden="true" />{error}</div>}
      {error && !buckets ? (
        <SurfaceError title="Tasks could not be loaded" description={error} onRetry={load} testid="tasks-error" />
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-card" data-testid={current && current.items.length ? `tasks-list-${tab}` : undefined}>
          {!current ? (
            <div className="space-y-2 p-3">{[0, 1, 2].map((index) => <Skeleton key={index} className="h-9 rounded-lg" />)}</div>
          ) : current.items.length === 0 ? (
            <div className="[&>.cv-empty]:rounded-none [&>.cv-empty]:border-0">
              <SurfaceEmpty icon={tab === "done" ? ListTodo : CheckCircle2}
                title={tab === "done" ? "Nothing finished lately" : "You're all caught up"}
                description={activeTab?.empty}
                action={<Button size="sm" variant="outline" onClick={() => setCreating(true)} data-testid="tasks-empty-new"><Plus aria-hidden="true" />New task</Button>}
                testid="tasks-empty" />
            </div>
          ) : groups.map((group, index) => (
            <section key={group.key} aria-label={`${group.label}: ${group.items.length}`} className={index ? "border-t border-border" : ""}>
              <h2 className="flex h-9 items-center gap-2 border-b border-border/70 bg-muted/40 px-4 text-xs font-medium text-muted-foreground">
                <StatusIcon status={group.key} className="size-3.5" />
                <span className="text-foreground/80">{group.label}</span>
                <span className="tabular">{group.items.length}</span>
              </h2>
              <ul>
                {group.items.map((task) => (
                  <TaskRow key={task.id} task={task} now={now} avatarName={avatarName}
                    busy={busyId === task.id} highlighted={task.id === focusId} onToggle={toggle} onOpen={open} />
                ))}
              </ul>
            </section>
          ))}
          {current && current.total > current.items.length && (
            <div className="border-t border-border bg-muted/30 px-4 py-2.5 text-xs text-muted-foreground">Showing the first {current.items.length} of {current.total}.</div>
          )}
        </div>
      )}

      <Sheet open={Boolean(focusId && focused)} onOpenChange={(value) => { if (!value) close(); }}>
        <SheetContent className="w-full overflow-y-auto p-0 sm:max-w-[860px]">
          {focused && (
            <TaskDetail key={`${focused.id}:${focused.updated_at || ""}:${focused.status}`} task={focused} now={now} me={me}
              isAdmin={isAdmin} team={team} nameOf={nameOf} busy={busyId === focused.id} tabLabel={TABS.find(({ key }) => key === bucketOf(focused, now))?.label}
              onToggle={toggle} onSave={save} />
          )}
        </SheetContent>
      </Sheet>

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-[520px]" data-testid="new-task-dialog">
          <DialogHeader>
            <DialogTitle>New task</DialogTitle>
            <DialogDescription className="text-[13px]">It shows up in Tasks for whoever you assign it to.</DialogDescription>
          </DialogHeader>
          <NewTaskForm me={me} isAdmin={isAdmin} team={team} onCreated={created} onCancel={() => setCreating(false)} />
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** Older notifications linked to /tasks/<id>; send them to the task on the Tasks page. */
export function TaskRedirect() {
  const { taskId } = useParams();
  return <Navigate to={`/tasks?task=${encodeURIComponent(taskId || "")}`} replace />;
}
