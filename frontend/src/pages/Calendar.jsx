/* Calendar (M-05): the appointments people booked, the booking pages they booked through,
   and the hours those pages offer.

   Upcoming lists appointments by day (today highlighted), with the person, the time, where
   it is, links to the lead, contact and deal, and Attended / No-show / Reschedule / Cancel.
   Anything whose time has passed without an outcome sits at the top until somebody says
   what happened -- a no-show recorded here is what the no-show recovery picks up. Emails
   to the person show where they are: each one waits for an admin to approve its words.
   Booking pages are the event types (edit, copy the link or an embed code, open the page);
   Availability is each agent's weekly hours and days off. ?appointment=<id> opens one. */
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { SurfaceEmpty, SurfaceError } from "@/components/SurfaceState";
import SlotPicker, { brandStyle } from "@/components/booking/SlotPicker";
import { LocationLine } from "@/components/booking/BookingParts";
import EventTypeEditor from "@/components/booking/EventTypeEditor";
import AvailabilityEditor from "@/components/booking/AvailabilityEditor";
import {
  CalendarClock, CalendarDays, CheckCircle2, Copy, ExternalLink, Mail, Pencil, Phone, Plus, RefreshCw,
  ShieldCheck, Sparkles, UserX,
} from "lucide-react";
import { addDays, browserTimeZone, dayKey, formatDay, formatRange, formatTime } from "@/lib/booking";

const STATUS = {
  confirmed: { label: "Booked", className: "border-emerald-200 bg-emerald-50 text-emerald-700" },
  scheduled: { label: "Scheduled", className: "border-emerald-200 bg-emerald-50 text-emerald-700" },
  completed: { label: "Attended", className: "border-slate-200 bg-slate-50 text-slate-700" },
  no_show: { label: "No-show", className: "border-amber-200 bg-amber-50 text-amber-800" },
  cancelled: { label: "Cancelled", className: "border-slate-200 bg-slate-100 text-slate-500" },
};
const MESSAGE_KIND = {
  confirmation: "Confirmation email", rescheduled: "New-time email", cancelled: "Cancellation email",
};
const ANSWER_LABELS = { listing_id: "MLS #", pre_approved: "Pre-approved", timeline: "Moving", price_max: "Budget up to", working_with_agent: "Has an agent" };

function messageLabel(kind) {
  if (MESSAGE_KIND[kind]) return MESSAGE_KIND[kind];
  const hours = Number(String(kind).replace(/\D/g, ""));
  return hours >= 24 ? `Reminder (${hours / 24} day${hours > 24 ? "s" : ""} before)` : `Reminder (${hours} hour${hours > 1 ? "s" : ""} before)`;
}

function messageState(message) {
  switch (message.status) {
    case "pending_approval": return { text: "Waiting for approval", tone: "text-amber-700" };
    case "approved": case "sending": return { text: "Approved — sending", tone: "text-[#0a6177]" };
    case "sent": case "delivered": return { text: "Sent", tone: "text-emerald-700" };
    case "off": return { text: "Off for this page", tone: "text-slate-500" };
    case "not_sent": return { text: "Not emailed", tone: "text-slate-500" };
    case "blocked": return { text: message.detail?.includes("no longer applies") ? "Withdrawn (the time changed)" : "Not sent", tone: "text-slate-500" };
    case "failed": case "outcome_unknown": return { text: "Could not send", tone: "text-red-700" };
    default: return { text: message.status || "—", tone: "text-slate-500" };
  }
}

function CodeBlock({ title, description, code, testid }) {
  const copy = () => { navigator.clipboard?.writeText(code); toast.success(`${title} copied`); };
  return (
    <div className="rounded-xl border border-slate-200">
      <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-[#132038]">{title}</div>
          {description && <p className="text-xs leading-5 text-slate-500">{description}</p>}
        </div>
        <Button size="sm" variant="outline" onClick={copy} data-testid={testid}><Copy className="mr-1 h-3.5 w-3.5" />Copy</Button>
      </div>
      <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all bg-slate-50 px-4 py-3 text-xs text-slate-700">{code}</pre>
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
        <div className="min-w-0 space-y-2 overflow-hidden rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
          <div className="font-semibold text-[#132038] [overflow-wrap:anywhere]">{message.subject}</div>
          <pre className="whitespace-pre-wrap font-sans text-slate-700 [overflow-wrap:anywhere]" data-testid="approve-email-body">{message.body}</pre>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Not now</Button>
          <Button className="cv-action-primary" onClick={approve} disabled={busy} data-testid="approve-email-confirm"><ShieldCheck className="mr-1.5 h-4 w-4" />{busy ? "Sending…" : "Approve and send"}</Button>
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
            {start && <p className="mt-3 text-sm font-semibold text-[#0a6177]" data-testid="reschedule-chosen">New time: {formatRange(start, null, zone)}</p>}
          </div>
        ) : (
          <div className="space-y-1.5">
            <Label htmlFor="reschedule-manual">New start</Label>
            <Input id="reschedule-manual" type="datetime-local" value={manual} onChange={(event) => setManual(event.target.value)} />
          </div>
        )}
        {appointment.person?.email && (
          <div className="flex items-start gap-3 text-sm">
            <Switch id="reschedule-notify" checked={notify} onCheckedChange={setNotify} data-testid="reschedule-notify" />
            <Label htmlFor="reschedule-notify" className="font-normal leading-5">Email {appointment.person.name || "them"} the new time <span className="text-slate-500">(waits for an admin's approval)</span></Label>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button className="cv-action-primary" onClick={save} disabled={busy || (appointment.event_type_id ? !start : !manual)} data-testid="reschedule-save">{busy ? "Moving…" : "Move it"}</Button>
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
          <Label htmlFor="cancel-reason-agent">Reason</Label>
          <Textarea id="cancel-reason-agent" rows={3} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="e.g. The seller accepted an offer" data-testid="cancel-reason" />
        </div>
        {appointment.person?.email && (
          <div className="flex items-start gap-3 text-sm">
            <Switch id="cancel-notify" checked={notify} onCheckedChange={setNotify} data-testid="cancel-notify" />
            <Label htmlFor="cancel-notify" className="font-normal leading-5">Email {appointment.person.name || "them"} that it's cancelled <span className="text-slate-500">(waits for an admin's approval)</span></Label>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Keep it</Button>
          <Button className="bg-red-700 text-white hover:bg-red-800" onClick={save} disabled={busy} data-testid="cancel-confirm">{busy ? "Cancelling…" : "Cancel appointment"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AppointmentCard({ appointment, showHost, highlighted, isAdmin, onAction, onApprove }) {
  const zone = browserTimeZone();
  const status = STATUS[appointment.status] || STATUS.scheduled;
  const upcoming = ["confirmed", "scheduled"].includes(appointment.status) && !appointment.needs_outcome;
  const answers = Object.entries(appointment.answers || {}).filter(([key, value]) => ANSWER_LABELS[key] && value);
  const person = appointment.person || {};
  const ref = useRef(null);
  useEffect(() => { if (highlighted) ref.current?.scrollIntoView({ block: "center" }); }, [highlighted]);
  return (
    <li ref={ref} id={`appointment-${appointment.id}`} data-testid={`appointment-${appointment.id}`}
      className={`cv-data-row px-4 py-4 sm:px-5 ${highlighted ? "bg-cyan-50/70 ring-2 ring-inset ring-[#4ac4e0]" : ""} ${appointment.status === "cancelled" ? "opacity-70" : ""}`}>
      <div className="flex flex-col gap-3 md:flex-row md:items-start">
        <div className="w-full shrink-0 md:w-36">
          <div className={`font-display text-base font-bold ${appointment.status === "cancelled" ? "text-slate-500 line-through" : "text-[#0a1628]"}`}>{formatTime(appointment.start_at, zone)}</div>
          <div className="text-xs text-slate-500">to {formatTime(appointment.end_at || appointment.start_at, zone)}</div>
        </div>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-[#132038]">{person.name || appointment.title}</span>
            <span className="rounded-full border border-cyan-200 bg-cyan-50 px-2 py-0.5 text-[11px] font-semibold text-[#0a6177]">{appointment.type_name}</span>
            <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${status.className}`}>{status.label}</span>
            {showHost && appointment.host_name && <span className="text-xs text-slate-500">with {appointment.host_name}</span>}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {person.phone && <a href={`tel:${person.phone.replace(/[^\d+]/g, "")}`} className="inline-flex items-center gap-1.5 font-semibold text-[#127b96] hover:underline" data-testid={`appointment-call-${appointment.id}`}><Phone className="h-3.5 w-3.5" />{person.phone}</a>}
            {person.email && <a href={`mailto:${person.email}`} className="inline-flex min-w-0 items-center gap-1.5 text-[#127b96] hover:underline"><Mail className="h-3.5 w-3.5 shrink-0" /><span className="truncate">{person.email}</span></a>}
          </div>
          {appointment.location?.kind && <LocationLine location={appointment.location} className="text-sm" />}
          {(answers.length > 0 || appointment.notes) && (
            <div className="text-xs leading-5 text-slate-600">
              {answers.map(([key, value]) => <span key={key} className="mr-3">{ANSWER_LABELS[key]}: <strong>{String(value)}</strong></span>)}
              {appointment.notes && <div className="mt-1 italic">“{appointment.notes}”</div>}
            </div>
          )}
          {appointment.cancel_reason && <div className="text-xs text-slate-500">Cancelled{appointment.cancelled_by_person ? " by the client" : ""}: {appointment.cancel_reason}</div>}
          {appointment.messages?.length > 0 && (
            <ul className="space-y-1 text-xs" aria-label="Emails to the person">
              {appointment.messages.map((message) => {
                const state = messageState(message);
                return (
                  <li key={message.kind} className="flex flex-wrap items-center gap-x-2 gap-y-1" data-testid={`appointment-email-${appointment.id}-${message.kind}`}>
                    <Mail className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
                    <span className="text-slate-600">{messageLabel(message.kind)}:</span>
                    <span className={`font-semibold ${state.tone}`} title={message.detail || undefined}>{state.text}</span>
                    {message.status === "not_sent" && message.detail && <span className="text-slate-500">— {message.detail.split(".")[0]}.</span>}
                    {message.status === "pending_approval" && isAdmin && (
                      <button type="button" onClick={() => onApprove(appointment, message)} className="font-semibold text-[#127b96] hover:underline" data-testid={`approve-email-${appointment.id}-${message.kind}`}>Review and approve</button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs font-semibold">
            {appointment.enquiry_id && <Link to={`/leads?lead=${appointment.enquiry_id}`} className="text-[#127b96] hover:underline" data-testid={`appointment-lead-${appointment.id}`}>Lead</Link>}
            {appointment.contact_id && <Link to={`/contacts?contact=${appointment.contact_id}`} className="text-[#127b96] hover:underline" data-testid={`appointment-contact-${appointment.id}`}>Contact</Link>}
            {appointment.opportunity_id && <Link to={`/deals?deal=${appointment.opportunity_id}`} className="text-[#127b96] hover:underline" data-testid={`appointment-deal-${appointment.id}`}>Deal</Link>}
          </div>
        </div>
        {appointment.can_manage && (appointment.needs_outcome || upcoming) && (
          <div className="flex shrink-0 flex-wrap gap-2 md:w-44 md:flex-col md:items-stretch">
            {appointment.needs_outcome ? (
              <>
                <Button size="sm" className="cv-action-primary" onClick={() => onAction(appointment, "attended")} data-testid={`appointment-attended-${appointment.id}`}><CheckCircle2 className="mr-1.5 h-4 w-4" />They came</Button>
                <Button size="sm" variant="outline" className="text-amber-800" onClick={() => onAction(appointment, "no_show")} data-testid={`appointment-noshow-${appointment.id}`}><UserX className="mr-1.5 h-4 w-4" />No-show</Button>
              </>
            ) : (
              <>
                <Button size="sm" variant="outline" onClick={() => onAction(appointment, "reschedule")} data-testid={`appointment-reschedule-${appointment.id}`}><CalendarClock className="mr-1.5 h-4 w-4" />Reschedule</Button>
                <Button size="sm" variant="ghost" className="text-red-700" onClick={() => onAction(appointment, "cancel")} data-testid={`appointment-cancel-${appointment.id}`}>Cancel</Button>
              </>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

function UpcomingTab({ items, loading, error, onReload, scope, setScope, isAdmin, highlightId, onAction, onApprove, hasPages, onGoToPages }) {
  const [showCancelled, setShowCancelled] = useState(false);
  const zone = browserTimeZone();
  const today = dayKey(new Date(), zone);
  const tomorrow = addDays(today, 1);
  const needOutcome = items.filter((a) => a.needs_outcome);
  const groups = useMemo(() => {
    const out = {};
    items.filter((a) => !a.needs_outcome && dayKey(a.start_at, zone) >= today && (showCancelled || a.status !== "cancelled"))
      .forEach((a) => { const key = dayKey(a.start_at, zone); (out[key] = out[key] || []).push(a); });
    return Object.entries(out).sort(([a], [b]) => a.localeCompare(b));
  }, [items, zone, today, showCancelled]);
  const showHost = scope === "all";

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="inline-flex rounded-xl border border-slate-200 bg-white p-1" role="group" aria-label="Whose appointments">
          {[["mine", "Mine"], ["all", "Everyone's"]].map(([value, label]) => (
            <button key={value} type="button" onClick={() => setScope(value)} aria-pressed={scope === value} data-testid={`calendar-scope-${value}`}
              className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${scope === value ? "bg-[#0a6177] text-white" : "text-slate-600 hover:bg-slate-50"}`}>{label}</button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2"><Switch id="calendar-show-cancelled" checked={showCancelled} onCheckedChange={setShowCancelled} data-testid="calendar-show-cancelled" /><Label htmlFor="calendar-show-cancelled" className="text-xs font-semibold text-slate-600">Show cancelled</Label></div>
          <Button size="sm" variant="outline" onClick={onReload} aria-label="Refresh"><RefreshCw className="h-4 w-4" /></Button>
        </div>
      </div>
      {error ? <SurfaceError title="The calendar could not be loaded" description={error} onRetry={onReload} />
        : loading ? <div className="space-y-3">{[0, 1, 2].map((n) => <Skeleton key={n} className="h-28 rounded-2xl" />)}</div>
          : (
            <>
              {needOutcome.length > 0 && (
                <section className="cv-card overflow-hidden border-amber-200" data-testid="calendar-needs-outcome">
                  <div className="border-b border-amber-100 bg-amber-50 px-5 py-3">
                    <h2 className="font-display text-base font-bold text-amber-900">Did these happen?</h2>
                    <p className="text-xs text-amber-800">Say whether they came. A no-show goes to lost-revenue recovery so someone follows up.</p>
                  </div>
                  <ul className="divide-y divide-slate-100">{needOutcome.map((a) => <AppointmentCard key={a.id} appointment={a} showHost={showHost} isAdmin={isAdmin} highlighted={a.id === highlightId} onAction={onAction} onApprove={onApprove} />)}</ul>
                </section>
              )}
              {groups.length === 0 ? (
                <SurfaceEmpty icon={CalendarDays} title={items.length ? "Nothing else coming up" : "Nothing booked yet"} testid="calendar-empty"
                  description={hasPages ? "Share your booking page link or put it on your website, and bookings land here." : "Set up your booking pages first — it takes one click."}
                  action={<Button className="cv-action-primary mt-5" onClick={onGoToPages} data-testid="calendar-empty-pages">{hasPages ? "Get my booking links" : "Set up booking pages"}</Button>} />
              ) : groups.map(([key, list]) => {
                const isToday = key === today;
                return (
                  <section key={key} className={`cv-card overflow-hidden ${isToday ? "border-[#4ac4e0] ring-1 ring-[#4ac4e0]" : ""}`} data-testid={`calendar-day-${key}`}>
                    <div className={`flex items-baseline justify-between gap-2 border-b px-5 py-3 ${isToday ? "border-cyan-100 bg-cyan-50" : "border-slate-100"}`}>
                      <h2 className={`font-display text-base font-bold ${isToday ? "text-[#0a6177]" : "text-[#132038]"}`}>
                        {isToday ? "Today" : key === tomorrow ? "Tomorrow" : formatDay(key)}
                        {(isToday || key === tomorrow) && <span className="ml-2 text-sm font-semibold text-slate-500">{formatDay(key, "short")}</span>}
                      </h2>
                      <span className="text-xs font-semibold text-slate-500">{list.length} {list.length === 1 ? "appointment" : "appointments"}</span>
                    </div>
                    <ul className="divide-y divide-slate-100">{list.map((a) => <AppointmentCard key={a.id} appointment={a} showHost={showHost} isAdmin={isAdmin} highlighted={a.id === highlightId} onAction={onAction} onApprove={onApprove} />)}</ul>
                  </section>
                );
              })}
            </>
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
        <div className="space-y-3">
          <CodeBlock title="Link" description="For a button, an email signature, a text message or a social bio." code={links.page} testid="embed-copy-link" />
          <CodeBlock title="Pop-up button" description="A link that opens the booking page over your website." code={links.popup} testid="embed-copy-popup" />
          <CodeBlock title="On the page" description="The booking page inside your page; it grows to fit." code={links.inline} testid="embed-copy-inline" />
          <CodeBlock title="iFrame" description="For builders that only allow iframes." code={links.iframe} testid="embed-copy-iframe" />
          <p className="text-xs leading-5 text-slate-500">On a listing page, add <code>?property_address=…&amp;listing_id=…</code> to the link to fill in the property. A website form can send people here after they submit: set its thank-you redirect (Website forms → Settings) to the link above.</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function BookingPagesTab({ pages, status, catalog, hosts, isAdmin, onChanged, loading }) {
  const [editing, setEditing] = useState(null);
  const [embedding, setEmbedding] = useState(null);
  const [creating, setCreating] = useState(false);
  const [newPage, setNewPage] = useState({ preset: "home_showing", name: "" });
  const [installing, setInstalling] = useState(false);
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
      setCreating(false); setNewPage({ preset: "home_showing", name: "" });
      toast.success("Booking page created");
      await onChanged();
      setEditing(data);
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  };
  const copy = (text, what) => { navigator.clipboard?.writeText(text); toast.success(`${what} copied`); };
  const hostNames = (page) => Object.values(page.host_names || {}).join(", ");

  return (
    <div className="space-y-5">
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="cv-card flex gap-3 p-4 text-sm" data-testid="booking-email-status">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-[#0a6177]" aria-hidden="true" />
          <div>
            <div className="font-semibold text-[#132038]">Emails to the people who book</div>
            <p className="mt-0.5 text-slate-600">
              {status?.email_channel?.authorized
                ? "Each confirmation and reminder is written for you and waits until an admin approves its exact words."
                : "Email isn't connected, so nothing is emailed. People see their confirmation on screen with an add-to-calendar file and their change link."}
              {" "}Only the website-form auto-reply may be approved once for everyone.
            </p>
            {status?.emails_waiting_for_approval > 0 && <p className="mt-1 font-semibold text-amber-700">{status.emails_waiting_for_approval} waiting — approve them on Upcoming or in <Link to="/operations?tab=approvals" className="underline">Approvals</Link>.</p>}
          </div>
        </div>
        <div className="cv-card flex gap-3 p-4 text-sm" data-testid="booking-google-status">
          <CalendarDays className="mt-0.5 h-5 w-5 shrink-0 text-[#0a6177]" aria-hidden="true" />
          <div>
            <div className="font-semibold text-[#132038]">Google Calendar</div>
            <p className="mt-0.5 text-slate-600">{status?.google_calendar?.account
              ? `Busy times on ${status.google_calendar.account}'s Google Calendar are taken off that agent's pages.`
              : "Not connected. Only appointments in ClientVerse block times. Connect it in Registries → Integrations."}</p>
          </div>
        </div>
      </div>

      {loading ? <div className="grid gap-4 lg:grid-cols-2">{[0, 1].map((n) => <Skeleton key={n} className="h-44 rounded-2xl" />)}</div>
        : pages.length === 0 ? (
          <SurfaceEmpty icon={Sparkles} title="Set up your booking pages" testid="booking-pages-empty"
            description="One click makes four real-estate booking pages — home showing (30 min), buyer consultation (45), listing appointment (60) and phone call (15) — using your hours, Monday to Saturday 9 to 6. You can change everything afterwards."
            action={isAdmin ? <Button className="cv-action-primary mt-5" onClick={install} disabled={installing} data-testid="booking-pages-install">{installing ? "Setting up…" : "Create my booking pages"}</Button>
              : <p className="mt-4 text-sm text-slate-500">Ask an admin to set them up.</p>} />
        ) : (
          <>
            {isAdmin && <div className="flex justify-end"><Button className="cv-action-primary" onClick={() => setCreating(true)} data-testid="booking-page-new"><Plus className="mr-1.5 h-4 w-4" />New booking page</Button></div>}
            <div className="grid gap-4 lg:grid-cols-2">
              {pages.map((page) => (
                <article key={page.id} className="cv-card flex min-w-0 flex-col gap-4 p-5" data-testid={`booking-page-${page.id}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h2 className="font-display text-lg font-bold text-[#132038]">{page.name}</h2>
                      <p className="text-xs text-slate-500">{page.duration_minutes} min · {(catalog?.location_kinds || []).find((k) => k.key === page.location?.kind)?.label} · {page.hosts?.mode === "round_robin" ? `Takes turns: ${hostNames(page)}` : hostNames(page)}</p>
                    </div>
                    <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${page.status === "active" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-600"}`}>{page.status === "active" ? "Live" : "Paused"}</span>
                  </div>
                  <div className="flex min-w-0 items-center gap-2 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
                    <span className="min-w-0 flex-1 truncate" data-testid={`booking-page-link-${page.id}`}>{page.links.page}</span>
                    <button type="button" onClick={() => copy(page.links.page, "Link")} className="shrink-0 font-semibold text-[#127b96] hover:underline" data-testid={`booking-page-copy-${page.id}`}>Copy link</button>
                  </div>
                  <p className="text-xs text-slate-500">{page.stats?.bookings || 0} booked · {page.stats?.views || 0} views{page.location?.kind === "office" && !page.location?.text ? " · Add your office address" : ""}</p>
                  <div className="mt-auto flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" asChild><a href={page.links.page} target="_blank" rel="noreferrer" data-testid={`booking-page-open-${page.id}`}><ExternalLink className="mr-1 h-3.5 w-3.5" />Open</a></Button>
                    <Button size="sm" variant="outline" onClick={() => setEmbedding(page)} data-testid={`booking-page-embed-${page.id}`}>Embed code</Button>
                    {isAdmin && <Button size="sm" className="cv-action-primary" onClick={() => setEditing(page)} data-testid={`booking-page-edit-${page.id}`}><Pencil className="mr-1 h-3.5 w-3.5" />Edit</Button>}
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      {editing && <EventTypeEditor eventType={editing} catalog={catalog} hosts={hosts} open onOpenChange={(open) => !open && setEditing(null)} onSaved={() => { setEditing(null); onChanged(); }} />}
      {embedding && <EmbedDialog eventType={embedding} onClose={() => setEmbedding(null)} />}
      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New booking page</DialogTitle><DialogDescription>Start from a real-estate template; change anything afterwards.</DialogDescription></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="new-page-preset">Template</Label>
              <Select value={newPage.preset} onValueChange={(preset) => setNewPage({ ...newPage, preset })}>
                <SelectTrigger id="new-page-preset"><SelectValue /></SelectTrigger>
                <SelectContent>{(catalog?.presets || []).map((preset) => <SelectItem key={preset.key} value={preset.key}>{preset.label} ({preset.duration_minutes} min)</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="new-page-name">Name <span className="font-normal text-slate-500">(optional)</span></Label>
              <Input id="new-page-name" value={newPage.name} onChange={(event) => setNewPage({ ...newPage, name: event.target.value })} placeholder="e.g. Open house tour" />
            </div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setCreating(false)}>Cancel</Button><Button className="cv-action-primary" onClick={create} data-testid="booking-page-create">Create</Button></DialogFooter>
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

  return (
    <div className="cv-page" data-testid="calendar-page">
      <div className="cv-page-header">
        <div>
          <div className="cv-eyebrow">Scheduling</div>
          <h1 className="cv-page-title">Calendar</h1>
          <p className="cv-page-description">Showings, consultations and calls people booked themselves — each one already a lead, a contact and a deal, with reminders on the way.</p>
        </div>
        {myPage && (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => { navigator.clipboard?.writeText(myPage.links.page); toast.success("Booking link copied"); }} data-testid="calendar-copy-my-link"><Copy className="mr-1.5 h-4 w-4" />Copy my link</Button>
            <Button className="cv-action-primary" asChild><a href={myPage.links.page} target="_blank" rel="noreferrer" data-testid="calendar-open-my-page"><ExternalLink className="mr-1.5 h-4 w-4" />Open my booking page</a></Button>
          </div>
        )}
      </div>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="mb-5 flex h-auto w-full flex-wrap justify-start sm:w-auto">
          <TabsTrigger value="upcoming" data-testid="calendar-tab-upcoming">Upcoming</TabsTrigger>
          <TabsTrigger value="pages" data-testid="calendar-tab-pages">Booking pages</TabsTrigger>
          <TabsTrigger value="availability" data-testid="calendar-tab-availability">Availability</TabsTrigger>
        </TabsList>
        <TabsContent value="upcoming">
          <UpcomingTab items={appointments} loading={loading} error={error} onReload={refresh} scope={scope} setScope={setScope}
            isAdmin={isAdmin} highlightId={highlightId} onAction={onAction} onApprove={(appointment, message) => setDialog({ type: "approve", appointment, message })}
            hasPages={pages.length > 0} onGoToPages={() => setTab("pages")} />
        </TabsContent>
        <TabsContent value="pages">
          <BookingPagesTab pages={pages} status={status} catalog={catalog} hosts={hosts} isAdmin={isAdmin} onChanged={loadSetup} loading={pagesLoading} />
        </TabsContent>
        <TabsContent value="availability">
          {availability.items.length
            ? <AvailabilityEditor items={availability.items} hosts={hosts} me={String(user?.email || "").toLowerCase()} isAdmin={isAdmin}
                googleAccount={availability.google_calendar_account} onSaved={() => { loadSetup(); }} />
            : <Skeleton className="h-96 rounded-2xl" />}
        </TabsContent>
      </Tabs>
      {dialog?.type === "reschedule" && <RescheduleDialog appointment={dialog.appointment} onClose={() => setDialog(null)} onDone={() => { setDialog(null); loadAppointments(); }} />}
      {dialog?.type === "cancel" && <CancelDialog appointment={dialog.appointment} onClose={() => setDialog(null)} onDone={() => { setDialog(null); loadAppointments(); }} />}
      {dialog?.type === "approve" && <ApproveDialog appointment={dialog.appointment} message={dialog.message} onClose={() => setDialog(null)} onDone={() => { setDialog(null); refresh(); }} />}
    </div>
  );
}
