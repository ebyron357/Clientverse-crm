/* Calendar (M-05): the appointments people booked, the booking pages they booked through,
   and the hours those pages offer.

   Upcoming lists appointments by day (today marked), with the person, the time, where
   it is, links to the lead, contact and deal, and Attended / No-show / Reschedule / Cancel.
   Anything whose time has passed without an outcome sits at the top until somebody says
   what happened -- a no-show recorded here is what the no-show recovery picks up. Emails
   to the person show where they are: each one waits for an admin to approve its words.
   The same appointments can be read as a week grid; an event there opens its details.
   Booking pages are the event types (edit, pause, copy the link or an embed code, open the
   page); Availability is each agent's weekly hours and days off. ?appointment=<id> opens one. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { SurfaceEmpty, SurfaceError } from "@/components/SurfaceState";
import { Avatar, PageHeader, StatusDot, Toolbar, ViewTabs } from "@/components/page/Page";
import SlotPicker, { brandStyle } from "@/components/booking/SlotPicker";
import EventTypeEditor from "@/components/booking/EventTypeEditor";
import AvailabilityEditor from "@/components/booking/AvailabilityEditor";
import {
  Building2, CalendarClock, CalendarDays, CalendarRange, CheckCircle2, ChevronLeft, ChevronRight, CircleDollarSign,
  Clock3, Code2, Copy, ExternalLink, Home, Inbox, List, Mail, MapPin, Pencil, Phone, Plus, RefreshCw, ShieldCheck,
  Sparkles, UserRound, UserX, Users, Video,
} from "lucide-react";
import { addDays, browserTimeZone, dayKey, formatDay, formatRange, formatTime, weekdayOf } from "@/lib/booking";

const cx = (...parts) => parts.filter(Boolean).join(" ");

const STATUS = {
  confirmed: { label: "Booked", tone: "brand" },
  scheduled: { label: "Scheduled", tone: "brand" },
  completed: { label: "Attended", tone: "success" },
  no_show: { label: "No-show", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};
// Event blocks in the week grid: a soft fill and a 2px accent bar in the status hue.
const BLOCK = {
  brand: { fill: "bg-brand-soft text-brand-strong hover:bg-brand-soft/70", bar: "bg-brand" },
  success: { fill: "bg-emerald-50 text-emerald-700 hover:bg-emerald-100", bar: "bg-emerald-500" },
  warning: { fill: "bg-amber-50 text-amber-700 hover:bg-amber-100", bar: "bg-amber-500" },
  danger: { fill: "bg-red-50 text-red-700 hover:bg-red-100", bar: "bg-red-500" },
  neutral: { fill: "bg-muted text-muted-foreground line-through hover:bg-muted/70", bar: "bg-muted-foreground/40" },
};
const LOCATION_ICON = { property: Home, office: Building2, phone: Phone, video: Video };
const MESSAGE_KIND = {
  confirmation: "Confirmation email", rescheduled: "New-time email", cancelled: "Cancellation email",
};
const ANSWER_LABELS = { listing_id: "MLS #", pre_approved: "Pre-approved", timeline: "Moving", price_max: "Budget up to", working_with_agent: "Has an agent" };
const CHIP = "inline-flex h-6 items-center gap-1 rounded-md border border-border bg-card px-2 text-xs font-medium text-foreground/80 transition-colors hover:bg-muted hover:text-foreground";

function messageLabel(kind) {
  if (MESSAGE_KIND[kind]) return MESSAGE_KIND[kind];
  const hours = Number(String(kind).replace(/\D/g, ""));
  return hours >= 24 ? `Reminder (${hours / 24} day${hours > 24 ? "s" : ""} before)` : `Reminder (${hours} hour${hours > 1 ? "s" : ""} before)`;
}

function messageState(message) {
  switch (message.status) {
    case "pending_approval": return { text: "Waiting for approval", tone: "text-amber-700" };
    case "approved": case "sending": return { text: "Approved — sending", tone: "text-brand" };
    case "sent": case "delivered": return { text: "Sent", tone: "text-emerald-700" };
    case "off": return { text: "Off for this page", tone: "text-muted-foreground" };
    case "not_sent": return { text: "Not emailed", tone: "text-muted-foreground" };
    case "blocked": return { text: message.detail?.includes("no longer applies") ? "Withdrawn (the time changed)" : "Not sent", tone: "text-muted-foreground" };
    case "failed": case "outcome_unknown": return { text: "Could not send", tone: "text-red-700" };
    default: return { text: message.status || "—", tone: "text-muted-foreground" };
  }
}

/** Status of an appointment for display; a past one nobody has closed reads as needing an outcome. */
function statusOf(appointment) {
  if (appointment.needs_outcome) return { label: "Needs outcome", tone: "warning" };
  return STATUS[appointment.status] || STATUS.scheduled;
}

/** Minutes since midnight of an instant, in a zone. */
function minutesOfDay(value, zone) {
  try {
    const parts = new Intl.DateTimeFormat("en-US", { timeZone: zone, hour: "numeric", minute: "numeric", hourCycle: "h23" }).formatToParts(new Date(value));
    const hour = Number(parts.find((part) => part.type === "hour")?.value || 0) % 24;
    return hour * 60 + Number(parts.find((part) => part.type === "minute")?.value || 0);
  } catch {
    const date = new Date(value);
    return date.getHours() * 60 + date.getMinutes();
  }
}

function zoneShort(zone) {
  try {
    return new Intl.DateTimeFormat("en-US", { timeZone: zone, timeZoneName: "short" }).formatToParts(new Date()).find((part) => part.type === "timeZoneName")?.value || zone;
  } catch {
    return zone;
  }
}

const startOfWeek = (key) => addDays(key, -((weekdayOf(key) + 6) % 7));

function weekLabel(start) {
  const options = { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" };
  const first = new Date(`${start}T12:00:00Z`);
  const last = new Date(`${addDays(start, 6)}T12:00:00Z`);
  try {
    return new Intl.DateTimeFormat(undefined, options).formatRange(first, last);
  } catch {
    return `${formatDay(start, "short")} – ${formatDay(addDays(start, 6), "short")}`;
  }
}

function hourLabel(hour) {
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(2020, 0, 1, hour % 24)));
}

/** Overlapping appointments share the column side by side, like any calendar. */
function layoutLanes(events) {
  const sorted = [...events].sort((a, b) => a.start - b.start || b.end - a.end);
  let cluster = [];
  let clusterEnd = -1;
  const close = () => {
    const lanes = cluster.reduce((max, event) => Math.max(max, event.lane + 1), 1);
    cluster.forEach((event) => { event.lanes = lanes; });
    cluster = [];
  };
  sorted.forEach((event) => {
    if (cluster.length && event.start >= clusterEnd) { close(); clusterEnd = -1; }
    const taken = new Set(cluster.filter((other) => other.end > event.start).map((other) => other.lane));
    let lane = 0;
    while (taken.has(lane)) lane += 1;
    event.lane = lane;
    cluster.push(event);
    clusterEnd = Math.max(clusterEnd, event.end);
  });
  if (cluster.length) close();
  return sorted;
}

/** A small two- or three-way switch for the toolbar (whose appointments, list or week). */
function Segmented({ label, options, value, onChange }) {
  return (
    <div role="group" aria-label={label} className="inline-flex h-8 items-center rounded-lg border border-border bg-card p-0.5">
      {options.map(({ value: key, label: text, icon: Icon, testid }) => (
        <button key={key} type="button" onClick={() => onChange(key)} aria-pressed={value === key} data-testid={testid}
          className={cx("inline-flex h-full items-center gap-1.5 rounded-md px-2.5 text-[13px] font-medium transition-colors",
            value === key ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground")}>
          {Icon && <Icon className="size-3.5" aria-hidden="true" />}{text}
        </button>
      ))}
    </div>
  );
}

function CodeBlock({ title, description, code, testid }) {
  const copy = () => { navigator.clipboard?.writeText(code); toast.success(`${title} copied`); };
  return (
    <div className="px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[13px] font-medium text-foreground">{title}</div>
          {description && <p className="text-xs leading-5 text-muted-foreground">{description}</p>}
        </div>
        <Button size="sm" variant="outline" onClick={copy} data-testid={testid}><Copy />Copy</Button>
      </div>
      <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-muted/50 px-3 py-2 font-mono text-[11.5px] leading-5 text-foreground/80">{code}</pre>
    </div>
  );
}

// ------------------------------------------------------------------- appointments

function ApproveDialog({ appointment, message, onClose, onDone }) {
  const [busy, setBusy] = useState(false);
  const approve = async () => {
    setBusy(true);
    try {
      await api.post(`/approval-queue/${message.approval_id}/decision`, { decision: "approved", rationale: "Booking email approved on the Calendar" });
      const { data } = await api.post(`/booking/appointments/${appointment.id}/deliver`);
      toast.success(data.sent ? "Approved and sent" : "Approved — it couldn't be sent yet; the reason is on the appointment");
      onDone();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Approve this email?</DialogTitle>
          <DialogDescription>To {appointment.person.email}. Approving sends these exact words once.</DialogDescription>
        </DialogHeader>
        <div className="min-w-0 space-y-2 overflow-hidden rounded-lg border border-border bg-muted/40 p-4 text-[13px]">
          <div className="font-semibold text-foreground [overflow-wrap:anywhere]">{message.subject}</div>
          <pre className="whitespace-pre-wrap font-sans leading-5 text-foreground/80 [overflow-wrap:anywhere]" data-testid="approve-email-body">{message.body}</pre>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Not now</Button>
          <Button onClick={approve} disabled={busy} data-testid="approve-email-confirm"><ShieldCheck />{busy ? "Sending…" : "Approve and send"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RescheduleDialog({ appointment, onClose, onDone }) {
  const [zone, setZone] = useState(browserTimeZone());
  const [start, setStart] = useState(null);
  const [manual, setManual] = useState("");
  const [notify, setNotify] = useState(Boolean(appointment.person?.email));
  const [busy, setBusy] = useState(false);
  const loadDays = useCallback(async (first, last, tz) => {
    const { data } = await api.get(`/booking/event-types/${appointment.event_type_id}/slots`, { params: { start: first, end: last, tz, ignore: appointment.id } });
    return data.days;
  }, [appointment.event_type_id, appointment.id]);
  const save = async () => {
    const value = appointment.event_type_id ? start : (manual ? new Date(manual).toISOString() : null);
    if (!value) { toast.error("Choose the new time"); return; }
    setBusy(true);
    try {
      await api.post(`/booking/appointments/${appointment.id}/reschedule`, { start: value, notify_person: notify, outside_hours: !appointment.event_type_id });
      toast.success("Moved");
      onDone();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[92vh] max-w-3xl overflow-y-auto" data-testid="reschedule-dialog">
        <DialogHeader>
          <DialogTitle>Move {appointment.person?.name || appointment.title}</DialogTitle>
          <DialogDescription>Now {formatRange(appointment.start_at, appointment.end_at, zone)}. Only times free on {appointment.host_name || "the host"}'s calendar are offered.</DialogDescription>
        </DialogHeader>
        {appointment.event_type_id ? (
          <div style={brandStyle()}>
            <SlotPicker loadDays={loadDays} zone={zone} onZoneChange={setZone} maxKey={addDays(dayKey(new Date(), zone), 365)}
              selectedStart={start} onPick={setStart} testid="reschedule-slots" />
            {start && <p className="mt-3 text-[13px] font-medium text-brand" data-testid="reschedule-chosen">New time: {formatRange(start, null, zone)}</p>}
          </div>
        ) : (
          <div className="space-y-1.5">
            <Label htmlFor="reschedule-manual" className="text-[13px]">New start</Label>
            <Input id="reschedule-manual" type="datetime-local" value={manual} onChange={(event) => setManual(event.target.value)} />
          </div>
        )}
        {appointment.person?.email && (
          <div className="flex items-start gap-3 text-[13px]">
            <Switch id="reschedule-notify" checked={notify} onCheckedChange={setNotify} data-testid="reschedule-notify" />
            <Label htmlFor="reschedule-notify" className="text-[13px] font-normal leading-5">Email {appointment.person.name || "them"} the new time <span className="text-muted-foreground">(waits for an admin's approval)</span></Label>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={busy || (appointment.event_type_id ? !start : !manual)} data-testid="reschedule-save">{busy ? "Moving…" : "Move it"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CancelDialog({ appointment, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [notify, setNotify] = useState(Boolean(appointment.person?.email));
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      await api.post(`/booking/appointments/${appointment.id}/cancel`, { reason, notify_person: notify });
      toast.success("Cancelled — the time is open again");
      onDone();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md" data-testid="cancel-dialog">
        <DialogHeader>
          <DialogTitle>Cancel this appointment?</DialogTitle>
          <DialogDescription>{appointment.person?.name || appointment.title} · {formatRange(appointment.start_at, appointment.end_at, browserTimeZone())}</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="cancel-reason-agent" className="text-[13px]">Reason</Label>
          <Textarea id="cancel-reason-agent" rows={3} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="e.g. The seller accepted an offer" data-testid="cancel-reason" />
        </div>
        {appointment.person?.email && (
          <div className="flex items-start gap-3 text-[13px]">
            <Switch id="cancel-notify" checked={notify} onCheckedChange={setNotify} data-testid="cancel-notify" />
            <Label htmlFor="cancel-notify" className="text-[13px] font-normal leading-5">Email {appointment.person.name || "them"} that it's cancelled <span className="text-muted-foreground">(waits for an admin's approval)</span></Label>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Keep it</Button>
          <Button variant="destructive" onClick={save} disabled={busy} data-testid="cancel-confirm">{busy ? "Cancelling…" : "Cancel appointment"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Where it happens, on one line: icon, kind and the address or link. */
function Place({ location }) {
  if (!location?.kind) return null;
  const Icon = LOCATION_ICON[location.kind] || MapPin;
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      <Icon className="size-3.5 shrink-0" aria-hidden="true" />
      <span className="min-w-0 break-words">{location.label}{location.text ? <span className="text-foreground/80"> · {location.text}</span> : null}</span>
    </span>
  );
}

/** What can be done with an appointment now: an outcome once its time has passed, otherwise move or cancel. */
function AppointmentActions({ appointment, onAction, testids = true }) {
  const upcoming = ["confirmed", "scheduled"].includes(appointment.status) && !appointment.needs_outcome;
  if (!appointment.can_manage || !(appointment.needs_outcome || upcoming)) return null;
  const id = (name) => (testids ? `appointment-${name}-${appointment.id}` : undefined);
  return appointment.needs_outcome ? (
    <>
      <Button size="sm" variant="outline" onClick={() => onAction(appointment, "attended")} data-testid={id("attended")}><CheckCircle2 className="text-emerald-600" />They came</Button>
      <Button size="sm" variant="outline" onClick={() => onAction(appointment, "no_show")} data-testid={id("noshow")}><UserX className="text-amber-600" />No-show</Button>
    </>
  ) : (
    <>
      <Button size="sm" variant="outline" onClick={() => onAction(appointment, "reschedule")} data-testid={id("reschedule")}><CalendarClock />Reschedule</Button>
      <Button size="sm" variant="ghost" className="text-red-700 hover:text-red-700" onClick={() => onAction(appointment, "cancel")} data-testid={id("cancel")}>Cancel</Button>
    </>
  );
}

function AppointmentRow({ appointment, showHost, highlighted, isAdmin, onAction, onApprove }) {
  const zone = browserTimeZone();
  const status = statusOf(appointment);
  const answers = Object.entries(appointment.answers || {}).filter(([key, value]) => ANSWER_LABELS[key] && value);
  const person = appointment.person || {};
  const name = person.name || appointment.title;
  const cancelled = appointment.status === "cancelled";
  const ref = useRef(null);
  useEffect(() => { if (highlighted) ref.current?.scrollIntoView({ block: "center" }); }, [highlighted]);
  const hasLinks = appointment.enquiry_id || appointment.contact_id || appointment.opportunity_id;
  return (
    <li ref={ref} id={`appointment-${appointment.id}`} data-testid={`appointment-${appointment.id}`}
      className={cx("flex flex-col gap-2 border-b border-border/70 px-4 py-3 transition-colors last:border-0 md:flex-row md:gap-5",
        highlighted ? "bg-brand-soft/60 ring-1 ring-inset ring-brand/50" : "hover:bg-muted/40", cancelled && "opacity-70")}>
      <div className="flex shrink-0 items-baseline gap-1.5 md:block md:w-[4.5rem] md:pt-0.5">
        <div className={cx("tabular text-[13px] font-medium", cancelled ? "text-muted-foreground line-through" : "text-foreground")}>{formatTime(appointment.start_at, zone)}</div>
        <div className="tabular text-xs text-muted-foreground"><span className="md:hidden">– </span>{formatTime(appointment.end_at || appointment.start_at, zone)}</div>
        <StatusDot tone={status.tone} className="ml-auto self-center text-xs md:hidden">{status.label}</StatusDot>
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2">
          <Avatar name={name} size="sm" />
          <div className="flex min-w-0 flex-wrap items-baseline gap-x-2">
            <span className="text-[13px] font-medium text-foreground">{name}</span>
            <span className="text-[13px] text-muted-foreground">{appointment.type_name}</span>
            {showHost && appointment.host_name && <span className="text-xs text-muted-foreground">with {appointment.host_name}</span>}
          </div>
        </div>
        <div className="mt-1.5 space-y-1.5 pl-8 text-xs leading-5 text-muted-foreground">
          {(person.phone || person.email || appointment.location?.kind || hasLinks) && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              {person.phone && <a href={`tel:${person.phone.replace(/[^\d+]/g, "")}`} className="tabular inline-flex items-center gap-1.5 font-medium text-foreground/80 hover:text-brand hover:underline" data-testid={`appointment-call-${appointment.id}`}><Phone className="size-3.5" aria-hidden="true" />{person.phone}</a>}
              {person.email && <a href={`mailto:${person.email}`} className="inline-flex min-w-0 items-center gap-1.5 text-foreground/80 hover:text-brand hover:underline"><Mail className="size-3.5 shrink-0" aria-hidden="true" /><span className="truncate">{person.email}</span></a>}
              <Place location={appointment.location} />
              {hasLinks && (
                <span className="flex flex-wrap gap-1.5">
                  {appointment.enquiry_id && <Link to={`/leads?lead=${appointment.enquiry_id}`} className={CHIP} data-testid={`appointment-lead-${appointment.id}`}><Inbox className="size-3" aria-hidden="true" />Lead</Link>}
                  {appointment.contact_id && <Link to={`/contacts?contact=${appointment.contact_id}`} className={CHIP} data-testid={`appointment-contact-${appointment.id}`}><UserRound className="size-3" aria-hidden="true" />Contact</Link>}
                  {appointment.opportunity_id && <Link to={`/deals?deal=${appointment.opportunity_id}`} className={CHIP} data-testid={`appointment-deal-${appointment.id}`}><CircleDollarSign className="size-3" aria-hidden="true" />Deal</Link>}
                </span>
              )}
            </div>
          )}
          {(answers.length > 0 || appointment.notes) && (
            <div>
              {answers.map(([key, value]) => <span key={key} className="mr-3">{ANSWER_LABELS[key]}: <span className="font-medium text-foreground/80">{String(value)}</span></span>)}
              {appointment.notes && <div className="italic">“{appointment.notes}”</div>}
            </div>
          )}
          {appointment.cancel_reason && <div>Cancelled{appointment.cancelled_by_person ? " by the client" : ""}: {appointment.cancel_reason}</div>}
          {appointment.messages?.length > 0 && (
            <ul className="space-y-0.5" aria-label="Emails to the person">
              {appointment.messages.map((message) => {
                const state = messageState(message);
                return (
                  <li key={message.kind} className="flex flex-wrap items-center gap-x-1.5" data-testid={`appointment-email-${appointment.id}-${message.kind}`}>
                    <Mail className="size-3.5" aria-hidden="true" />
                    <span>{messageLabel(message.kind)}:</span>
                    <span className={cx("font-medium", state.tone)} title={message.detail || undefined}>{state.text}</span>
                    {message.status === "not_sent" && message.detail && <span>— {message.detail.split(".")[0]}.</span>}
                    {message.status === "pending_approval" && isAdmin && (
                      <button type="button" onClick={() => onApprove(appointment, message)} className="ml-1 font-medium text-brand hover:underline" data-testid={`approve-email-${appointment.id}-${message.kind}`}>Review and approve</button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-2 pl-8 empty:hidden md:-mt-1 md:h-8 md:flex-nowrap md:pl-0">
        <StatusDot tone={status.tone} className="mr-1 hidden md:inline-flex">{status.label}</StatusDot>
        <AppointmentActions appointment={appointment} onAction={onAction} />
      </div>
    </li>
  );
}

/** The week as a grid: hour rows, one column a day, appointments as tinted blocks. */
function WeekGrid({ items, weekStart, today, zone, showHost, onAction }) {
  const HOUR = 48;
  const [openId, setOpenId] = useState(null);
  const [now, setNow] = useState(() => new Date());
  const scroller = useRef(null);
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60000);
    return () => clearInterval(timer);
  }, []);
  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => addDays(weekStart, index)), [weekStart]);
  const byDay = useMemo(() => {
    const out = Object.fromEntries(days.map((key) => [key, []]));
    items.forEach((appointment) => {
      const key = dayKey(appointment.start_at, zone);
      if (!out[key]) return;
      const start = minutesOfDay(appointment.start_at, zone);
      let end = appointment.end_at ? minutesOfDay(appointment.end_at, zone) : start + 30;
      if (appointment.end_at && dayKey(appointment.end_at, zone) !== key) end = 24 * 60;
      if (end <= start) end = Math.min(start + 15, 24 * 60);
      out[key].push({ appointment, start, end });
    });
    Object.keys(out).forEach((key) => { out[key] = layoutLanes(out[key]); });
    return out;
  }, [days, items, zone]);
  const all = Object.values(byDay).flat();
  const firstHour = Math.max(0, Math.min(8, ...all.map((event) => Math.floor(event.start / 60))));
  const lastHour = Math.min(24, Math.max(19, ...all.map((event) => Math.ceil(event.end / 60))));
  const hours = Array.from({ length: lastHour - firstHour }, (_, index) => firstHour + index);
  const nowMinutes = minutesOfDay(now, zone);
  const showNow = days.includes(today) && nowMinutes >= firstHour * 60 && nowMinutes <= lastHour * 60;
  const columns = "grid grid-cols-[3.25rem_repeat(7,minmax(0,1fr))]";
  // On a narrow screen the week scrolls sideways; start with today in view.
  useEffect(() => {
    const el = scroller.current;
    const column = el?.querySelector(`[data-day="${today}"]`);
    if (el && el.scrollWidth > el.clientWidth) el.scrollLeft = column ? Math.max(0, column.offsetLeft - 52) : 0;
  }, [today, weekStart]);

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card" data-testid="calendar-week">
      <div ref={scroller} className="cv-scrollbar overflow-x-auto">
        <div className="min-w-[720px]">
          <div className={cx(columns, "border-b border-border/70")}>
            <div className="sticky left-0 z-30 flex items-end justify-end bg-card px-2 pb-2 text-[10.5px] font-medium text-muted-foreground" title={zone}>{zoneShort(zone)}</div>
            {days.map((key) => {
              const isToday = key === today;
              const date = new Date(`${key}T12:00:00Z`);
              return (
                <div key={key} className="flex items-center justify-center gap-1.5 border-l border-border/70 py-2" aria-current={isToday ? "date" : undefined}>
                  <span className={cx("text-xs font-medium", isToday ? "text-foreground" : "text-muted-foreground")}>{new Intl.DateTimeFormat(undefined, { weekday: "short", timeZone: "UTC" }).format(date)}</span>
                  <span className={cx("tabular inline-flex size-6 items-center justify-center rounded-full text-[13px] font-semibold",
                    isToday ? "bg-brand text-brand-foreground dark:bg-brand-strong dark:text-background" : "text-foreground")}>{date.getUTCDate()}</span>
                </div>
              );
            })}
          </div>
          <div className={cx(columns, "relative")} style={{ height: hours.length * HOUR }}>
            <div className="sticky left-0 z-30 bg-card" aria-hidden="true">
              {hours.map((hour, index) => (
                <span key={hour} className={cx("tabular absolute right-2 text-xs text-muted-foreground", index > 0 && "-translate-y-1/2")} style={{ top: index === 0 ? 2 : index * HOUR }}>{hourLabel(hour)}</span>
              ))}
            </div>
            {days.map((key) => (
              <div key={key} data-day={key} className={cx("relative border-l border-border/70", key === today && "bg-brand-soft/30")} data-testid={`calendar-week-day-${key}`}>
                {byDay[key].map(({ appointment, start, end, lane, lanes }) => {
                  const status = statusOf(appointment);
                  const block = BLOCK[status.tone] || BLOCK.brand;
                  const height = Math.max(22, ((end - start) / 60) * HOUR - 2);
                  const name = appointment.person?.name || appointment.title;
                  const past = !appointment.needs_outcome && new Date(appointment.end_at || appointment.start_at) < now;
                  return (
                    <Popover key={appointment.id} open={openId === appointment.id} onOpenChange={(open) => setOpenId(open ? appointment.id : null)}>
                      <PopoverTrigger asChild>
                        <button type="button" data-testid={`calendar-week-event-${appointment.id}`}
                          aria-label={`${name}, ${appointment.type_name}, ${formatRange(appointment.start_at, appointment.end_at, zone)}, ${status.label}`}
                          className={cx("absolute z-10 overflow-hidden rounded-md py-[3px] pl-2.5 pr-1.5 text-left text-[11.5px] leading-4 transition-colors", block.fill, past && "opacity-70")}
                          style={{ top: ((start - firstHour * 60) / 60) * HOUR + 1, height, left: `calc(${(lane / lanes) * 100}% + 2px)`, width: `calc(${100 / lanes}% - 4px)` }}>
                          <span aria-hidden="true" className={cx("absolute inset-y-1 left-1 w-[2px] rounded-full", block.bar)} />
                          {height >= 34 ? <>
                            <span className="block truncate font-medium">{name}</span>
                            <span className="tabular block truncate opacity-80">{formatTime(appointment.start_at, zone)} · {appointment.type_name}</span>
                          </> : <span className="block truncate"><span className="font-medium">{name}</span> <span className="tabular opacity-80">{formatTime(appointment.start_at, zone)}</span></span>}
                        </button>
                      </PopoverTrigger>
                      <PopoverContent align="start" className="w-80 overflow-hidden p-0">
                        <div className="space-y-3 p-4">
                          <div className="flex items-start gap-2.5">
                            <Avatar name={name} size="md" />
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-sm font-semibold text-foreground">{name}</div>
                              <div className="text-xs text-muted-foreground">{appointment.type_name}{showHost && appointment.host_name ? ` · with ${appointment.host_name}` : ""}</div>
                            </div>
                            <StatusDot tone={status.tone} className="shrink-0 text-xs">{status.label}</StatusDot>
                          </div>
                          <div className="space-y-1.5 text-xs text-muted-foreground">
                            <div className="flex items-center gap-1.5"><Clock3 className="size-3.5 shrink-0" aria-hidden="true" /><span className="tabular text-foreground/80">{formatRange(appointment.start_at, appointment.end_at, zone)}</span></div>
                            {appointment.location?.kind && <div><Place location={appointment.location} /></div>}
                            {appointment.person?.phone && <a href={`tel:${appointment.person.phone.replace(/[^\d+]/g, "")}`} className="tabular flex items-center gap-1.5 text-foreground/80 hover:text-brand hover:underline"><Phone className="size-3.5" aria-hidden="true" />{appointment.person.phone}</a>}
                            {appointment.person?.email && <a href={`mailto:${appointment.person.email}`} className="flex min-w-0 items-center gap-1.5 text-foreground/80 hover:text-brand hover:underline"><Mail className="size-3.5 shrink-0" aria-hidden="true" /><span className="truncate">{appointment.person.email}</span></a>}
                          </div>
                          <div className="flex flex-wrap items-center gap-1.5 empty:hidden">
                            {appointment.enquiry_id && <Link to={`/leads?lead=${appointment.enquiry_id}`} className={CHIP}><Inbox className="size-3" aria-hidden="true" />Lead</Link>}
                            {appointment.contact_id && <Link to={`/contacts?contact=${appointment.contact_id}`} className={CHIP}><UserRound className="size-3" aria-hidden="true" />Contact</Link>}
                            {appointment.opportunity_id && <Link to={`/deals?deal=${appointment.opportunity_id}`} className={CHIP}><CircleDollarSign className="size-3" aria-hidden="true" />Deal</Link>}
                          </div>
                        </div>
                        {appointment.can_manage && (appointment.needs_outcome || ["confirmed", "scheduled"].includes(appointment.status)) && (
                          <div className="flex flex-wrap justify-end gap-2 border-t border-border bg-muted/30 px-4 py-2.5">
                            <AppointmentActions appointment={appointment} testids={false} onAction={(item, action) => { setOpenId(null); onAction(item, action); }} />
                          </div>
                        )}
                      </PopoverContent>
                    </Popover>
                  );
                })}
                {showNow && key === today && (
                  <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 z-20 h-px bg-brand" style={{ top: ((nowMinutes - firstHour * 60) / 60) * HOUR }}>
                    <span className="absolute -left-[4px] -top-[3px] size-[7px] rounded-full bg-brand" />
                  </div>
                )}
              </div>
            ))}
            <div aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-[3.25rem] right-0">
              {hours.slice(1).map((hour, index) => <div key={hour} className="absolute inset-x-0 border-t border-border/70" style={{ top: (index + 1) * HOUR }} />)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function UpcomingTab({ items, loading, error, onReload, scope, setScope, isAdmin, highlightId, onAction, onApprove, hasPages, onGoToPages }) {
  const [showCancelled, setShowCancelled] = useState(false);
  const [view, setView] = useState("list");
  const zone = browserTimeZone();
  const today = dayKey(new Date(), zone);
  const tomorrow = addDays(today, 1);
  const [weekStart, setWeekStart] = useState(() => startOfWeek(today));
  // A link to one appointment (?appointment=<id>) opens it in the list.
  useEffect(() => { if (highlightId) setView("list"); }, [highlightId]);
  const needOutcome = items.filter((a) => a.needs_outcome);
  const groups = useMemo(() => {
    const out = {};
    items.filter((a) => !a.needs_outcome && dayKey(a.start_at, zone) >= today && (showCancelled || a.status !== "cancelled"))
      .forEach((a) => { const key = dayKey(a.start_at, zone); (out[key] = out[key] || []).push(a); });
    return Object.entries(out).sort(([a], [b]) => a.localeCompare(b));
  }, [items, zone, today, showCancelled]);
  const weekItems = useMemo(() => items.filter((a) => showCancelled || a.status !== "cancelled"), [items, showCancelled]);
  const showHost = scope === "all";
  // Appointments are loaded from two weeks back to four months ahead; the grid stays inside that.
  const firstWeek = startOfWeek(addDays(today, -14));
  const lastWeek = startOfWeek(addDays(today, 119));

  return (
    <div>
      <Toolbar className="justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <Segmented label="Whose appointments" value={scope} onChange={setScope}
            options={[{ value: "mine", label: "Mine", testid: "calendar-scope-mine" }, { value: "all", label: "Everyone's", testid: "calendar-scope-all" }]} />
          <Segmented label="Layout" value={view} onChange={setView}
            options={[{ value: "list", label: "List", icon: List, testid: "calendar-view-list" }, { value: "week", label: "Week", icon: CalendarRange, testid: "calendar-view-week" }]} />
          {view === "week" && (
            <div className="flex items-center gap-1">
              <Button size="icon" variant="ghost" className="size-8" onClick={() => setWeekStart(addDays(weekStart, -7))} disabled={weekStart <= firstWeek} aria-label="Previous week" title="Previous week" data-testid="calendar-week-prev"><ChevronLeft /></Button>
              <Button size="sm" variant="outline" onClick={() => setWeekStart(startOfWeek(today))} data-testid="calendar-week-today">Today</Button>
              <Button size="icon" variant="ghost" className="size-8" onClick={() => setWeekStart(addDays(weekStart, 7))} disabled={weekStart >= lastWeek} aria-label="Next week" title="Next week" data-testid="calendar-week-next"><ChevronRight /></Button>
              <span className="tabular ml-1 text-[13px] font-medium text-foreground" aria-live="polite">{weekLabel(weekStart)}</span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2"><Switch id="calendar-show-cancelled" checked={showCancelled} onCheckedChange={setShowCancelled} data-testid="calendar-show-cancelled" /><Label htmlFor="calendar-show-cancelled" className="text-[13px] font-normal text-muted-foreground">Show cancelled</Label></div>
          <Button size="icon" variant="outline" className="size-8" onClick={onReload} aria-label="Refresh" title="Refresh"><RefreshCw /></Button>
        </div>
      </Toolbar>

      {error ? <SurfaceError title="The calendar could not be loaded" description={error} onRetry={onReload} />
        : loading ? (
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            {[0, 1, 2, 3].map((n) => <div key={n} className="flex items-center gap-4 border-b border-border/70 px-4 py-3 last:border-0"><Skeleton className="h-4 w-14" /><Skeleton className="size-6 rounded-full" /><Skeleton className="h-4 w-48" /><Skeleton className="ml-auto h-4 w-20" /></div>)}
          </div>
        ) : view === "week" ? (
          <div className="space-y-3">
            {needOutcome.length > 0 && (
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-700" role="status">
                <CalendarClock className="size-4 shrink-0" aria-hidden="true" />
                <span>{needOutcome.length} {needOutcome.length === 1 ? "appointment has" : "appointments have"} passed without an outcome.</span>
                <button type="button" onClick={() => setView("list")} className="font-medium underline-offset-2 hover:underline">Say what happened</button>
              </div>
            )}
            <WeekGrid items={weekItems} weekStart={weekStart} today={today} zone={zone} showHost={showHost} onAction={onAction} />
          </div>
        ) : (
          <div className="space-y-5">
            {needOutcome.length > 0 && (
              <section className="overflow-hidden rounded-xl border border-amber-200 bg-card" data-testid="calendar-needs-outcome">
                <div className="flex flex-col gap-0.5 border-b border-amber-200 bg-amber-50/60 px-4 py-2.5 sm:flex-row sm:items-center sm:gap-3">
                  <h2 className="flex items-center gap-2 text-[13px] font-semibold text-foreground">
                    <span className="size-1.5 rounded-full bg-amber-500" aria-hidden="true" />Did these happen?
                    <span className="tabular rounded bg-amber-100 px-1 text-xs font-medium text-amber-700">{needOutcome.length}</span>
                  </h2>
                  <p className="text-xs text-muted-foreground">Say whether they came. A no-show goes to lost-revenue recovery so someone follows up.</p>
                </div>
                <ul>{needOutcome.map((a) => <AppointmentRow key={a.id} appointment={a} showHost={showHost} isAdmin={isAdmin} highlighted={a.id === highlightId} onAction={onAction} onApprove={onApprove} />)}</ul>
              </section>
            )}
            {groups.length === 0 ? (
              <SurfaceEmpty icon={CalendarDays} title={items.length ? "Nothing else coming up" : "Nothing booked yet"} testid="calendar-empty"
                description={hasPages ? "Share your booking page link or put it on your website, and bookings land here." : "Set up your booking pages first — it takes one click."}
                action={<Button size="sm" onClick={onGoToPages} data-testid="calendar-empty-pages">{hasPages ? "Get my booking links" : "Set up booking pages"}</Button>} />
            ) : (
              <div className="overflow-hidden rounded-xl border border-border bg-card">
                {groups.map(([key, list], index) => {
                  const isToday = key === today;
                  return (
                    <section key={key} className={cx(index > 0 && "border-t border-border")} data-testid={`calendar-day-${key}`} aria-label={formatDay(key)}>
                      <div className="flex h-9 items-center justify-between gap-2 border-b border-border/70 bg-muted/40 px-4">
                        <h2 className="flex items-center gap-2 text-xs font-medium">
                          {isToday && <span className="size-1.5 rounded-full bg-brand" aria-hidden="true" />}
                          <span className={isToday ? "text-foreground" : "text-foreground/80"}>{isToday ? "Today" : key === tomorrow ? "Tomorrow" : formatDay(key)}</span>
                          {(isToday || key === tomorrow) && <span className="font-normal text-muted-foreground">{formatDay(key, "short")}</span>}
                        </h2>
                        <span className="tabular text-xs text-muted-foreground">{list.length} {list.length === 1 ? "appointment" : "appointments"}</span>
                      </div>
                      <ul>{list.map((a) => <AppointmentRow key={a.id} appointment={a} showHost={showHost} isAdmin={isAdmin} highlighted={a.id === highlightId} onAction={onAction} onApprove={onApprove} />)}</ul>
                    </section>
                  );
                })}
              </div>
            )}
          </div>
        )}
    </div>
  );
}

// ------------------------------------------------------------------- booking pages

function EmbedDialog({ eventType, onClose }) {
  const links = eventType.links;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[92vh] max-w-2xl overflow-y-auto" data-testid="embed-dialog">
        <DialogHeader>
          <DialogTitle>Put “{eventType.name}” on your website</DialogTitle>
          <DialogDescription>Paste one of these where you want it (WordPress Custom HTML block, Squarespace Code block, Wix Embed, an IDX page).</DialogDescription>
        </DialogHeader>
        <div className="divide-y divide-border/70 overflow-hidden rounded-xl border border-border">
          <CodeBlock title="Link" description="For a button, an email signature, a text message or a social bio." code={links.page} testid="embed-copy-link" />
          <CodeBlock title="Pop-up button" description="A link that opens the booking page over your website." code={links.popup} testid="embed-copy-popup" />
          <CodeBlock title="On the page" description="The booking page inside your page; it grows to fit." code={links.inline} testid="embed-copy-inline" />
          <CodeBlock title="iFrame" description="For builders that only allow iframes." code={links.iframe} testid="embed-copy-iframe" />
        </div>
        <p className="text-xs leading-5 text-muted-foreground">On a listing page, add <code className="rounded bg-muted px-1 font-mono text-[11px]">?property_address=…&amp;listing_id=…</code> to the link to fill in the property. A website form can send people here after they submit: set its thank-you redirect (Website forms → Settings) to the link above.</p>
      </DialogContent>
    </Dialog>
  );
}

function BookingPageRow({ page, catalog, isAdmin, onEdit, onEmbed, onToggle, toggling }) {
  const copy = (text, what) => { navigator.clipboard?.writeText(text); toast.success(`${what} copied`); };
  const hostNames = Object.values(page.host_names || {}).join(", ");
  const live = page.status === "active";
  const LocationIcon = LOCATION_ICON[page.location?.kind] || MapPin;
  const locationLabel = (catalog?.location_kinds || []).find((k) => k.key === page.location?.kind)?.label;
  return (
    <li className="flex flex-col gap-3 border-b border-border/70 px-4 py-3.5 transition-colors last:border-0 hover:bg-muted/40 md:flex-row md:items-center md:gap-4" data-testid={`booking-page-${page.id}`}>
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border border-border bg-muted/40 text-muted-foreground" aria-hidden="true"><LocationIcon className="size-4" /></span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
            <h2 className={cx("text-[13px] font-semibold", live ? "text-foreground" : "text-muted-foreground")}>{page.name}</h2>
            {(!isAdmin || !live) && <StatusDot tone={live ? "success" : "neutral"} className="text-xs">{live ? "Live" : "Paused"}</StatusDot>}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span className="tabular inline-flex items-center gap-1"><Clock3 className="size-3.5" aria-hidden="true" />{page.duration_minutes} min</span>
            {locationLabel && <span>{locationLabel}</span>}
            {hostNames && <span className="inline-flex min-w-0 items-center gap-1"><Users className="size-3.5 shrink-0" aria-hidden="true" />{page.hosts?.mode === "round_robin" ? `Takes turns: ${hostNames}` : hostNames}</span>}
            <span className="tabular">{page.stats?.bookings || 0} booked · {page.stats?.views || 0} views</span>
            {page.location?.kind === "office" && !page.location?.text && <StatusDot tone="warning" className="text-xs text-amber-700">Add your office address</StatusDot>}
          </div>
          <div className="mt-1.5 flex min-w-0 items-center gap-1">
            <span className="min-w-0 truncate text-xs text-muted-foreground" data-testid={`booking-page-link-${page.id}`}>{page.links.page}</span>
          </div>
        </div>
      </div>
      <div className="flex w-full shrink-0 items-center gap-1.5 md:w-auto">
        <Button size="sm" variant="outline" onClick={() => copy(page.links.page, "Link")} data-testid={`booking-page-copy-${page.id}`}><Copy />Copy link</Button>
        <Button size="icon" variant="ghost" className="size-8 text-muted-foreground" asChild>
          <a href={page.links.page} target="_blank" rel="noreferrer" aria-label={`Open ${page.name}`} title="Open the booking page" data-testid={`booking-page-open-${page.id}`}><ExternalLink /></a>
        </Button>
        <Button size="icon" variant="ghost" className="size-8 text-muted-foreground" onClick={() => onEmbed(page)} aria-label={`Embed code for ${page.name}`} title="Embed code" data-testid={`booking-page-embed-${page.id}`}><Code2 /></Button>
        {isAdmin && <Button size="sm" variant="outline" onClick={() => onEdit(page)} data-testid={`booking-page-edit-${page.id}`}><Pencil />Edit</Button>}
        {isAdmin && (
          <span className="ml-auto flex items-center border-l border-border pl-3 md:ml-1.5">
            <Switch checked={live} disabled={toggling} onCheckedChange={(on) => onToggle(page, on)} aria-label={`Taking bookings on ${page.name}`} title={live ? "Taking bookings" : "Paused"} data-testid={`booking-page-live-${page.id}`} />
          </span>
        )}
      </div>
    </li>
  );
}

function BookingPagesTab({ pages, status, catalog, hosts, isAdmin, onChanged, loading, creating, setCreating }) {
  const [editing, setEditing] = useState(null);
  const [embedding, setEmbedding] = useState(null);
  const [newPage, setNewPage] = useState({ preset: "meeting", name: "" });
  const [installing, setInstalling] = useState(false);
  const [toggling, setToggling] = useState(null);
  const install = async () => {
    setInstalling(true);
    try {
      const { data } = await api.post("/booking/event-types/defaults", { timezone: browserTimeZone() });
      toast.success(`${data.created.length} booking pages are live`);
      onChanged();
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); } finally { setInstalling(false); }
  };
  const create = async () => {
    try {
      const { data } = await api.post("/booking/event-types", { preset: newPage.preset, name: newPage.name.trim() || undefined });
      setCreating(false); setNewPage({ preset: "meeting", name: "" });
      toast.success("Booking page created");
      await onChanged();
      setEditing(data);
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  };
  const toggleLive = async (page, on) => {
    setToggling(page.id);
    try {
      await api.patch(`/booking/event-types/${page.id}`, { status: on ? "active" : "paused" });
      toast.success(on ? `${page.name} is taking bookings` : `${page.name} is paused — it shows as unavailable`);
      await onChanged();
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); } finally { setToggling(null); }
  };
  const emailOn = Boolean(status?.email_channel?.authorized);
  const google = status?.google_calendar?.account;

  return (
    <div className="space-y-5 pt-5">
      {loading ? (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          {[0, 1, 2].map((n) => <div key={n} className="flex items-center gap-3 border-b border-border/70 px-4 py-4 last:border-0"><Skeleton className="size-8 rounded-lg" /><div className="flex-1 space-y-2"><Skeleton className="h-4 w-40" /><Skeleton className="h-3 w-72" /></div><Skeleton className="h-8 w-24" /></div>)}
        </div>
      ) : pages.length === 0 ? (
        <SurfaceEmpty icon={Sparkles} title="Set up your booking pages" testid="booking-pages-empty"
          description="One click makes four real-estate booking pages — home showing (30 min), buyer consultation (45), listing appointment (60) and phone call (15) — using your hours, Monday to Saturday 9 to 6. You can change everything afterwards."
          action={isAdmin ? <Button size="sm" onClick={install} disabled={installing} data-testid="booking-pages-install">{installing ? "Setting up…" : "Create my booking pages"}</Button>
            : <p className="text-[13px] text-muted-foreground">Ask an admin to set them up.</p>} />
      ) : (
        <ul className="overflow-hidden rounded-xl border border-border bg-card">
          {pages.map((page) => (
            <BookingPageRow key={page.id} page={page} catalog={catalog} isAdmin={isAdmin} onEdit={setEditing} onEmbed={setEmbedding}
              onToggle={toggleLive} toggling={toggling === page.id} />
          ))}
        </ul>
      )}

      <div className="grid overflow-hidden rounded-xl border border-border bg-card md:grid-cols-2">
        <div className="flex gap-3 px-4 py-3" data-testid="booking-email-status">
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5">
              <span className="text-[13px] font-medium text-foreground">Emails to the people who book</span>
              <StatusDot tone={emailOn ? "success" : "neutral"} className="text-xs">{emailOn ? "Approval required" : "Not connected"}</StatusDot>
            </div>
            <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
              {emailOn
                ? "Each confirmation and reminder is written for you and waits until an admin approves its exact words."
                : "Email isn't connected, so nothing is emailed. People see their confirmation on screen with an add-to-calendar file and their change link."}
              {" "}Only the website-form auto-reply may be approved once for everyone.
            </p>
            {status?.emails_waiting_for_approval > 0 && <p className="mt-1 text-xs font-medium text-amber-700">{status.emails_waiting_for_approval} waiting — approve them on Upcoming or in <Link to="/operations?tab=approvals" className="underline">Approvals</Link>.</p>}
          </div>
        </div>
        <div className="flex gap-3 border-t border-border px-4 py-3 md:border-l md:border-t-0" data-testid="booking-google-status">
          <CalendarDays className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5">
              <span className="text-[13px] font-medium text-foreground">Google Calendar</span>
              <StatusDot tone={google ? "success" : "neutral"} className="text-xs">{google ? "Connected" : "Not connected"}</StatusDot>
            </div>
            <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{google
              ? `Busy times on ${google}'s Google Calendar are taken off that agent's pages.`
              : "Not connected. Only appointments in ClientVerse block times. Connect it in Registries → Integrations."}</p>
          </div>
        </div>
      </div>

      {editing && <EventTypeEditor eventType={editing} catalog={catalog} hosts={hosts} open onOpenChange={(open) => !open && setEditing(null)} onSaved={() => { setEditing(null); onChanged(); }} />}
      {embedding && <EmbedDialog eventType={embedding} onClose={() => setEmbedding(null)} />}
      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New booking page</DialogTitle><DialogDescription>Start from a real-estate template; change anything afterwards.</DialogDescription></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="new-page-preset" className="text-[13px]">Template</Label>
              <Select value={newPage.preset} onValueChange={(preset) => setNewPage({ ...newPage, preset })}>
                <SelectTrigger id="new-page-preset"><SelectValue /></SelectTrigger>
                <SelectContent>{(catalog?.presets || []).map((preset) => <SelectItem key={preset.key} value={preset.key}>{preset.label} ({preset.duration_minutes} min)</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="new-page-name" className="text-[13px]">Name <span className="font-normal text-muted-foreground">(optional)</span></Label>
              <Input id="new-page-name" value={newPage.name} onChange={(event) => setNewPage({ ...newPage, name: event.target.value })} placeholder="e.g. Open house tour" />
            </div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setCreating(false)}>Cancel</Button><Button onClick={create} data-testid="booking-page-create">Create</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ------------------------------------------------------------------------ the page

export default function Calendar() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [params, setParams] = useSearchParams();
  const tab = ["pages", "availability"].includes(params.get("tab")) ? params.get("tab") : "upcoming";
  const highlightId = params.get("appointment");
  const [scope, setScope] = useState(isAdmin ? "all" : "mine");
  const [appointments, setAppointments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pages, setPages] = useState([]);
  const [pagesLoading, setPagesLoading] = useState(true);
  const [status, setStatus] = useState(null);
  const [catalog, setCatalog] = useState(null);
  const [hosts, setHosts] = useState([]);
  const [availability, setAvailability] = useState({ items: [], google_calendar_account: null });
  const [dialog, setDialog] = useState(null);
  const [creating, setCreating] = useState(false);

  const loadAppointments = useCallback(async () => {
    const start = new Date(Date.now() - 14 * 24 * 3600 * 1000).toISOString();
    const end = new Date(Date.now() + 120 * 24 * 3600 * 1000).toISOString();
    try {
      const { data } = await api.get("/booking/appointments", { params: { start, end, scope } });
      setAppointments(data.items); setError("");
    } catch (e) {
      setError(formatErr(e.response?.data?.detail) || "The calendar could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [scope]);

  const loadSetup = useCallback(async () => {
    try {
      const [pageResponse, statusResponse, catalogResponse, hostResponse, availabilityResponse] = await Promise.all([
        api.get("/booking/event-types"), api.get("/booking/status"), api.get("/booking/catalog"),
        api.get("/booking/hosts"), api.get("/booking/availability")]);
      setPages(pageResponse.data.items); setStatus(statusResponse.data); setCatalog(catalogResponse.data);
      setHosts(hostResponse.data.items); setAvailability(availabilityResponse.data);
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || "Booking settings could not be loaded.");
    } finally {
      setPagesLoading(false);
    }
  }, []);

  useEffect(() => { loadAppointments(); }, [loadAppointments]);
  useEffect(() => { loadSetup(); }, [loadSetup]);
  useEffect(() => {
    const timer = setInterval(() => { if (document.visibilityState === "visible") loadAppointments(); }, 60000);
    return () => clearInterval(timer);
  }, [loadAppointments]);

  const setTab = (value) => setParams(value === "upcoming" ? {} : { tab: value });
  const refresh = () => { loadAppointments(); loadSetup(); };
  const onAction = async (appointment, action) => {
    if (action === "attended" || action === "no_show") {
      try {
        await api.post(`/booking/appointments/${appointment.id}/outcome`, { outcome: action });
        toast.success(action === "attended" ? "Marked as attended" : "Marked as a no-show — it's queued for follow-up");
        loadAppointments();
      } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
      return;
    }
    setDialog({ type: action, appointment });
  };
  const myPage = pages.find((page) => page.status === "active" && (page.hosts?.users || []).includes(String(user?.email || "").toLowerCase())) || pages.find((page) => page.status === "active");
  const zone = browserTimeZone();
  const today = dayKey(new Date(), zone);
  const upcomingCount = appointments.filter((a) => a.needs_outcome || (["confirmed", "scheduled"].includes(a.status) && dayKey(a.start_at, zone) >= today)).length;

  return (
    <div className="cv-page" data-testid="calendar-page">
      <PageHeader icon={CalendarDays} title="Calendar" description="Showings, consultations and calls people booked themselves."
        actions={(myPage || (tab === "pages" && isAdmin && pages.length > 0)) && <>
          {myPage && <Button size="sm" variant="outline" asChild><a href={myPage.links.page} target="_blank" rel="noreferrer" data-testid="calendar-open-my-page"><ExternalLink />Open my booking page</a></Button>}
          {myPage && <Button size="sm" variant={tab === "pages" && isAdmin ? "outline" : "default"} onClick={() => { navigator.clipboard?.writeText(myPage.links.page); toast.success("Booking link copied"); }} data-testid="calendar-copy-my-link"><Copy />Copy my link</Button>}
          {tab === "pages" && isAdmin && pages.length > 0 && <Button size="sm" onClick={() => setCreating(true)} data-testid="booking-page-new"><Plus />New booking page</Button>}
        </>} />
      <ViewTabs label="Calendar views" value={tab} onChange={setTab} items={[
        { value: "upcoming", label: "Upcoming", count: loading || error ? undefined : upcomingCount, testid: "calendar-tab-upcoming" },
        { value: "pages", label: "Booking pages", count: pagesLoading ? undefined : pages.length, testid: "calendar-tab-pages" },
        { value: "availability", label: "Availability", testid: "calendar-tab-availability" },
      ]} />
      <div role="tabpanel" aria-label={{ upcoming: "Upcoming", pages: "Booking pages", availability: "Availability" }[tab]}>
        {tab === "upcoming" && (
          <UpcomingTab items={appointments} loading={loading} error={error} onReload={refresh} scope={scope} setScope={setScope}
            isAdmin={isAdmin} highlightId={highlightId} onAction={onAction} onApprove={(appointment, message) => setDialog({ type: "approve", appointment, message })}
            hasPages={pages.length > 0} onGoToPages={() => setTab("pages")} />
        )}
        {tab === "pages" && (
          <BookingPagesTab pages={pages} status={status} catalog={catalog} hosts={hosts} isAdmin={isAdmin} onChanged={loadSetup} loading={pagesLoading}
            creating={creating} setCreating={setCreating} />
        )}
        {tab === "availability" && (
          <div className="pt-5">
            {availability.items.length
              ? <AvailabilityEditor items={availability.items} hosts={hosts} me={String(user?.email || "").toLowerCase()} isAdmin={isAdmin}
                  googleAccount={availability.google_calendar_account} onSaved={() => { loadSetup(); }} />
              : <Skeleton className="h-96 rounded-xl" />}
          </div>
        )}
      </div>
      {dialog?.type === "reschedule" && <RescheduleDialog appointment={dialog.appointment} onClose={() => setDialog(null)} onDone={() => { setDialog(null); loadAppointments(); }} />}
      {dialog?.type === "cancel" && <CancelDialog appointment={dialog.appointment} onClose={() => setDialog(null)} onDone={() => { setDialog(null); loadAppointments(); }} />}
      {dialog?.type === "approve" && <ApproveDialog appointment={dialog.appointment} message={dialog.message} onClose={() => setDialog(null)} onDone={() => { setDialog(null); refresh(); }} />}
    </div>
  );
}
