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
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { SurfaceEmpty, SurfaceError } from "@/components/SurfaceState";
import { AlarmClock, CalendarClock, CheckCircle2, Circle, ListTodo, Phone, Plus, RefreshCw, RotateCcw, Timer, X } from "lucide-react";

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

const TONE = {
  overdue: "text-red-700",
  soon: "text-amber-700",
  today: "text-[#0a6177]",
  later: "text-slate-600",
  none: "text-slate-500",
  done: "text-emerald-700",
};

const PRIORITY = {
  urgent: { label: "Urgent", className: "border-red-200 bg-red-50 text-red-700" },
  high: { label: "High priority", className: "border-amber-200 bg-amber-50 text-amber-800" },
  low: { label: "Low priority", className: "border-slate-200 bg-slate-50 text-slate-600" },
};
const STATUS_CHIP = {
  in_progress: { label: "In progress", className: "border-cyan-200 bg-cyan-50 text-[#0a6177]" },
  blocked: { label: "Waiting on something", className: "border-violet-200 bg-violet-50 text-violet-700" },
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

// ------------------------------------------------------------------ pieces

function DueLabel({ task, now }) {
  if (task.status === "done") {
    return <span className={`inline-flex items-center gap-1 font-semibold ${TONE.done}`}><CheckCircle2 className="h-3.5 w-3.5" />{doneWords(task, now)}</span>;
  }
  const due = dueWords(task.due_date, now);
  const Icon = due.tone === "overdue" ? AlarmClock : due.tone === "soon" ? Timer : CalendarClock;
  return <span className={`inline-flex items-center gap-1 font-semibold ${TONE[due.tone]}`}><Icon className="h-3.5 w-3.5" />{due.text}</span>;
}

function Chips({ task }) {
  const priority = PRIORITY[task.priority];
  const status = STATUS_CHIP[task.status];
  return (
    <>
      {priority && <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${priority.className}`}>{priority.label}</span>}
      {status && <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${status.className}`}>{status.label}</span>}
    </>
  );
}

function TaskRow({ task, now, showAssignee, nameOf, busy, highlighted, onToggle, onOpen }) {
  const done = task.status === "done";
  const about = aboutOf(task);
  const contact = task.related?.contact;
  const owner = task.assignee ? nameOf(task.assignee) : null;
  return (
    <li id={`task-${task.id}`} className={`cv-data-row ${highlighted ? "bg-cyan-50/70 ring-2 ring-inset ring-[#4ac4e0]" : ""}`} data-testid={`task-row-${task.id}`}>
      <div className="flex items-start gap-3 px-4 py-3.5 sm:px-5">
        <button type="button" onClick={() => onToggle(task)} disabled={busy} aria-pressed={done}
          aria-label={done ? `Reopen: ${task.title}` : `Mark done: ${task.title}`}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-slate-300 transition-colors hover:bg-emerald-50 hover:text-emerald-600 disabled:opacity-50"
          data-testid={`task-toggle-${task.id}`}>
          {done ? <CheckCircle2 className="h-6 w-6 text-emerald-600" /> : <Circle className="h-6 w-6" />}
        </button>
        <div className="min-w-0 flex-1 pt-1.5">
          <button type="button" onClick={() => onOpen(task)}
            className={`block w-full break-words text-left text-[15px] font-semibold leading-6 hover:text-[#0a6177] ${done ? "text-slate-500 line-through decoration-slate-300" : "text-[#132038]"}`}
            data-testid={`task-open-${task.id}`}>
            {task.title}
          </button>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm">
            <DueLabel task={task} now={now} />
            <Chips task={task} />
            {showAssignee || !owner
              ? <span className="text-slate-500">{owner ? `Assigned to ${owner === "You" ? "you" : owner}` : "Unassigned"}</span>
              : null}
          </div>
          {about && (
            <div className="mt-1 break-words text-sm text-slate-500">
              {about.label}:{" "}
              {about.to
                ? <Link to={about.to} className="font-semibold text-[#127b96] hover:underline" data-testid={`task-about-${task.id}`}>{about.name}</Link>
                : <span>{about.name}</span>}
              {about.kind === "deal" && contact?.name ? ` · ${contact.name}` : ""}
            </div>
          )}
        </div>
        {contact?.phone && !done && (
          <Button asChild size="sm" variant="outline" className="mt-1 shrink-0">
            <a href={telHref(contact.phone)} aria-label={`Call ${contact.name || "them"} at ${contact.phone}`} data-testid={`task-call-${task.id}`}>
              <Phone className="mr-1.5 h-4 w-4" />Call
            </a>
          </Button>
        )}
      </div>
    </li>
  );
}

function DetailRow({ label, children }) {
  if (children == null || children === "" || children === false) return null;
  return (
    <div className="grid grid-cols-[7.5rem_1fr] gap-3 border-t border-slate-100 py-2 text-sm first:border-t-0">
      <dt className="text-slate-500">{label}</dt>
      <dd className="min-w-0 break-words text-[#132038]">{children}</dd>
    </div>
  );
}

function createdLine(task, nameOf) {
  const created = parseDate(task.created_at);
  const when = created ? `${created.toLocaleDateString([], { month: "short", day: "numeric" })}, ${clock(created)}` : "";
  const automatic = String(task.created_by || "").startsWith("system:");
  const lead = task.source && typeof task.source === "object" && task.source.kind === "website_form";
  const creator = task.created_by ? nameOf(task.created_by) : null;
  const who = automatic ? (lead ? "Added automatically when the lead came in" : "Added automatically")
    : creator ? `Added by ${creator === "You" ? "you" : creator}` : "Added";
  return when ? `${who} · ${when}` : who;
}

/** One task: what it is, the quick actions, and the edits (due date, owner). */
function TaskDetail({ task, now, me, isAdmin, team, nameOf, busy, onToggle, onSave }) {
  const initial = toLocalInputs(task.due_date);
  const choices = assigneeChoices({ me, isAdmin, team, current: task.assignee });
  const [date, setDate] = useState(initial.date);
  const [time, setTime] = useState(initial.time);
  const [assignee, setAssignee] = useState(choiceFor(choices, task.assignee));
  const [touched, setTouched] = useState({ due: false, assignee: false });
  const done = task.status === "done";
  const about = aboutOf(task);
  const contact = task.related?.contact;

  const save = () => {
    const changes = {};
    if (touched.due) changes.due_date = fromLocalInputs(date, time);
    if (touched.assignee) changes.assignee = assignee === UNASSIGNED ? null : assignee;
    onSave(task, changes);
  };

  return (
    <div className="space-y-6 pb-10" data-testid="task-detail">
      <div className="flex flex-wrap items-center gap-2 text-sm"><DueLabel task={task} now={now} /><Chips task={task} /></div>

      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant={done ? "outline" : "default"} className={done ? "" : "cv-action-primary"} disabled={busy} onClick={() => onToggle(task)} data-testid="task-detail-toggle">
          {done ? <><RotateCcw className="mr-1.5 h-4 w-4" />Reopen</> : <><CheckCircle2 className="mr-1.5 h-4 w-4" />Mark done</>}
        </Button>
        {contact?.phone && (
          <Button asChild size="sm" variant="outline">
            <a href={telHref(contact.phone)} data-testid="task-detail-call"><Phone className="mr-1.5 h-4 w-4" />Call {contact.phone}</a>
          </Button>
        )}
        {about?.to && <Button asChild size="sm" variant="outline"><Link to={about.to} data-testid="task-detail-about">Open the {about.kind}</Link></Button>}
      </div>

      <section>
        <h3 className="mb-1 text-xs font-bold uppercase tracking-[0.06em] text-slate-500">Details</h3>
        <dl>
          <DetailRow label="Person">{contact?.name ? [contact.name, contact.phone, contact.email].filter(Boolean).join(" · ") : null}</DetailRow>
          <DetailRow label="Assigned to">{task.assignee ? nameOf(task.assignee) : "Unassigned — anyone on the team can take it"}</DetailRow>
          <DetailRow label="Created">{createdLine(task, nameOf)}</DetailRow>
        </dl>
      </section>

      {task.notes && (
        <section>
          <h3 className="mb-1 text-xs font-bold uppercase tracking-[0.06em] text-slate-500">Notes</h3>
          <p className="whitespace-pre-wrap break-words text-sm leading-6 text-[#132038]">{task.notes}</p>
        </section>
      )}

      <section className="space-y-3">
        <h3 className="text-xs font-bold uppercase tracking-[0.06em] text-slate-500">Change</h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="task-due-date">Due date</Label>
            <Input id="task-due-date" type="date" value={date} onChange={(event) => { setDate(event.target.value); setTouched((value) => ({ ...value, due: true })); }} data-testid="task-detail-due-date" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="task-due-time">Time</Label>
            <Input id="task-due-time" type="time" value={time} onChange={(event) => { setTime(event.target.value); setTouched((value) => ({ ...value, due: true })); }} data-testid="task-detail-due-time" />
          </div>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="task-assignee">Assigned to</Label>
          <Select value={assignee} onValueChange={(value) => { setAssignee(value); setTouched((current) => ({ ...current, assignee: true })); }}>
            <SelectTrigger id="task-assignee" data-testid="task-detail-assignee"><SelectValue /></SelectTrigger>
            <SelectContent>{choices.map((choice) => <SelectItem key={choice.value} value={choice.value}>{choice.label}</SelectItem>)}</SelectContent>
          </Select>
          {!isAdmin && <p className="text-xs text-slate-500">Only admins can see the team list, so you can take a task yourself or leave it unassigned.</p>}
        </div>
        <Button size="sm" className="cv-action-primary" disabled={busy || (!touched.due && !touched.assignee)} onClick={save} data-testid="task-detail-save">Save changes</Button>
      </section>
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
      <div className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
        <span className="min-w-0 break-words text-[#132038]"><span className="font-semibold">{value.name}</span>{value.phone ? ` · ${value.phone}` : value.email ? ` · ${value.email}` : ""}</span>
        <Button type="button" size="sm" variant="ghost" onClick={() => onChange(null)} aria-label={`Remove ${value.name}`} data-testid="new-task-contact-clear"><X className="h-4 w-4" /></Button>
      </div>
    );
  }
  return (
    <div className="space-y-1.5">
      <Input id="new-task-contact" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Type a name, email or phone" autoComplete="off" data-testid="new-task-contact-search" />
      {searching && <p className="text-xs text-slate-500">Searching…</p>}
      {!searching && query.trim().length >= 2 && results.length === 0 && <p className="text-xs text-slate-500">No contact matches “{query.trim()}”.</p>}
      {results.length > 0 && (
        <ul className="max-h-48 divide-y divide-slate-100 overflow-y-auto rounded-lg border border-slate-200">
          {results.map((contact) => (
            <li key={contact.id}>
              <button type="button" onClick={() => { onChange(contact); setQuery(""); }} className="w-full px-3 py-2 text-left text-sm hover:bg-slate-50" data-testid={`new-task-contact-option-${contact.id}`}>
                <span className="font-semibold text-[#132038]">{contact.name}</span>
                <span className="block text-xs text-slate-500">{[contact.phone, contact.email].filter(Boolean).join(" · ") || "No phone or email yet"}</span>
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
    <form onSubmit={submit} className="grid gap-4 py-2">
      <div className="grid gap-1.5">
        <Label htmlFor="new-task-title">What needs doing <span className="text-red-500">*</span></Label>
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
          <SelectTrigger id="new-task-assignee" data-testid="new-task-assignee"><SelectValue /></SelectTrigger>
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
      <DialogFooter className="gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>Cancel</Button>
        <Button type="submit" className="cv-action-primary" disabled={saving} data-testid="new-task-submit">{saving ? "Adding…" : "Add task"}</Button>
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
  const focusedAbout = focused ? aboutOf(focused) : null;

  return (
    <div className="cv-page" data-testid="tasks-page">
      <div className="cv-page-header">
        <div>
          <div className="cv-eyebrow">Follow-through</div>
          <h1 className="cv-page-title">Tasks</h1>
          <p className="cv-page-description">Every call-back and follow-up in one place. When a lead comes in from your website, its call-back shows up here within seconds.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={load} data-testid="tasks-refresh"><RefreshCw className="mr-1.5 h-4 w-4" />Refresh</Button>
          <Button className="cv-action-primary" onClick={() => setCreating(true)} data-testid="tasks-new"><Plus className="mr-1.5 h-4 w-4" />New task</Button>
        </div>
      </div>

      <div className="cv-card overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-slate-100 p-3 sm:p-4 lg:flex-row lg:items-center lg:justify-between">
          <div role="tablist" aria-label="Tasks by when they are due" className="grid grid-cols-4 gap-1 lg:flex">
            {TABS.map(({ key, label }) => {
              const count = buckets?.[key]?.total;
              const selected = tab === key;
              const alarm = key === "overdue" && count > 0;
              return (
                <button key={key} type="button" role="tab" aria-selected={selected} onClick={() => setTab(key)}
                  className={`flex min-w-0 flex-col items-center gap-0.5 rounded-lg px-2 py-1.5 text-[13px] font-semibold sm:flex-row sm:justify-center sm:gap-2 sm:text-sm lg:px-3 ${selected ? (alarm ? "bg-red-700 text-white" : "bg-[#0a1628] text-white") : alarm ? "text-red-700 hover:bg-red-50" : "text-slate-600 hover:bg-slate-100"}`}
                  data-testid={`tasks-tab-${key}`}>
                  <span>{label}</span>
                  <span className={`min-w-[1.5rem] rounded-full px-1.5 text-center text-[11px] leading-5 ${selected ? "bg-white/20" : alarm ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-600"}`}>{count == null ? "–" : count}</span>
                </button>
              );
            })}
          </div>
          {isAdmin ? (
            <div role="group" aria-label="Whose tasks to show" className="grid grid-cols-2 rounded-lg border border-slate-200 p-0.5 text-sm font-semibold lg:inline-grid">
              {[["mine", "My tasks"], ["everyone", "Everyone"]].map(([key, label]) => (
                <button key={key} type="button" aria-pressed={view === key} onClick={() => switchView(key)}
                  className={`rounded-md px-3 py-1.5 ${view === key ? "bg-cyan-50 text-[#0a6177]" : "text-slate-600 hover:bg-slate-50"}`}
                  data-testid={`tasks-view-${key}`}>{label}</button>
              ))}
            </div>
          ) : null}
        </div>
        <p className="border-b border-slate-100 px-4 py-2 text-xs text-slate-500 sm:px-5">
          {view === "mine" ? "Tasks assigned to you, plus any nobody has taken yet." : "Every task on the team."}
        </p>

        {error && buckets && <div className="m-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800" role="status">{error}</div>}
        {error && !buckets ? (
          <div className="p-4"><SurfaceError title="Tasks could not be loaded" description={error} onRetry={load} testid="tasks-error" /></div>
        ) : !current ? (
          <div className="space-y-2 p-4">{[0, 1, 2].map((index) => <Skeleton key={index} className="h-16 rounded-xl" />)}</div>
        ) : current.items.length === 0 ? (
          <div className="p-4">
            <SurfaceEmpty icon={tab === "done" ? ListTodo : CheckCircle2}
              title={tab === "done" ? "Nothing finished lately" : "You're all caught up"}
              description={activeTab?.empty}
              action={<Button className="mt-5 cv-action-primary" onClick={() => setCreating(true)} data-testid="tasks-empty-new"><Plus className="mr-1.5 h-4 w-4" />New task</Button>}
              testid="tasks-empty" />
          </div>
        ) : (
          <ul className="divide-y divide-slate-100" data-testid={`tasks-list-${tab}`}>
            {current.items.map((task) => (
              <TaskRow key={task.id} task={task} now={now} showAssignee={view === "everyone"} nameOf={nameOf}
                busy={busyId === task.id} highlighted={task.id === focusId} onToggle={toggle} onOpen={open} />
            ))}
          </ul>
        )}
        {current && current.total > current.items.length && (
          <div className="border-t border-slate-100 px-5 py-3 text-xs text-slate-500">Showing the first {current.items.length} of {current.total}.</div>
        )}
      </div>

      <Sheet open={Boolean(focusId && focused)} onOpenChange={(value) => { if (!value) close(); }}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          {focused && (
            <>
              <SheetHeader className="mb-4 pr-6">
                <SheetTitle className="break-words">{focused.title}</SheetTitle>
                <SheetDescription>{focusedAbout ? `${focusedAbout.label}: ${focusedAbout.name}` : "A follow-up task"}</SheetDescription>
              </SheetHeader>
              <TaskDetail key={`${focused.id}:${focused.updated_at || ""}:${focused.status}`} task={focused} now={now} me={me}
                isAdmin={isAdmin} team={team} nameOf={nameOf} busy={busyId === focused.id} onToggle={toggle} onSave={save} />
            </>
          )}
        </SheetContent>
      </Sheet>

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-[520px]" data-testid="new-task-dialog">
          <DialogHeader>
            <DialogTitle className="font-display text-2xl">New task</DialogTitle>
            <DialogDescription>Write down the next thing to do and when. It shows up in Tasks for whoever you assign it to.</DialogDescription>
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
