/* Edit one booking page: what it is, when it can be booked, where it happens, who hosts
   it, what it asks, and what the CRM does after a booking. Admins only; plain words for
   an agent who has never seen a scheduling tool's settings screen. */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, formatErr } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { CircleAlert, Save, ShieldCheck } from "lucide-react";

const clone = (value) => JSON.parse(JSON.stringify(value));
const cx = (...parts) => parts.filter(Boolean).join(" ");
const LOCATION_HINTS = {
  property: "They tell you the property address when they book; it goes on the appointment and in their calendar.",
  office: "Your office address is shown on the booking page.",
  phone: "You call them at the number they give.",
  video: "Your meeting link is shared only with the person who books.",
};
const LEAD_TIMES = [[0, "When it's booked"], [60, "1 hour before"], [120, "2 hours before"], [240, "4 hours before"], [1440, "1 day before"], [2880, "2 days before"]];
const TEXT = "text-[13px] md:text-[13px]";
const CHECKBOX = "size-4 shrink-0 rounded border-input accent-brand";

function Section({ title, description, children }) {
  return (
    <section className="space-y-4 py-5 first:pt-0 last:pb-0">
      <div>
        <h3 className="text-sm font-semibold tracking-tight text-foreground">{title}</h3>
        {description && <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{description}</p>}
      </div>
      {children}
    </section>
  );
}

function Field({ label, hint, htmlFor, children }) {
  return (
    <div className="min-w-0 space-y-1.5">
      <Label htmlFor={htmlFor} className="text-[13px] font-medium text-foreground">{label}</Label>
      {children}
      {hint && <p className="text-xs leading-5 text-muted-foreground">{hint}</p>}
    </div>
  );
}

function Toggle({ id, label, hint, checked, onChange }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <Label htmlFor={id} className="text-[13px] font-medium text-foreground">{label}</Label>
        {hint && <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{hint}</p>}
      </div>
      <Switch id={id} checked={Boolean(checked)} onCheckedChange={onChange} data-testid={id} className="mt-0.5" />
    </div>
  );
}

/** A number with its unit beside it ("30 minutes"). */
function Amount({ id, value, onChange, min = 0, max = 480, step, unit, testid }) {
  return (
    <div className="flex items-center gap-2">
      <Input id={id} type="number" inputMode="numeric" min={min} max={max} step={step} value={value} className={cx("tabular h-9 w-24", TEXT)}
        onChange={(event) => onChange(event.target.value)} data-testid={testid} />
      <span className="text-[13px] text-muted-foreground">{unit}</span>
    </div>
  );
}

function Minutes({ id, value, onChange, min = 0, max = 480 }) {
  return <Amount id={id} value={value} min={min} max={max} unit="minutes" testid={id}
    onChange={(raw) => onChange(raw === "" ? "" : Number(raw))} />;
}

export default function EventTypeEditor({ eventType, catalog, hosts, open, onOpenChange, onSaved }) {
  const [draft, setDraft] = useState(() => clone(eventType));
  const [saving, setSaving] = useState(false);
  useEffect(() => { setDraft(clone(eventType)); }, [eventType]);
  const set = (patch) => setDraft((current) => ({ ...current, ...patch }));
  const setIn = (group, patch) => setDraft((current) => ({ ...current, [group]: { ...current[group], ...patch } }));
  const asked = Object.fromEntries((draft.questions || []).map((q) => [q.key, q]));
  const toggleQuestion = (key, on) => setDraft((current) => ({
    ...current,
    questions: on ? [...current.questions, { key, required: false }] : current.questions.filter((q) => q.key !== key),
  }));
  const requireQuestion = (key, required) => setDraft((current) => ({
    ...current, questions: current.questions.map((q) => (q.key === key ? { ...q, required } : q)),
  }));
  const toggleHost = (email) => setDraft((current) => {
    const users = new Set(current.hosts.users);
    if (users.has(email)) users.delete(email); else users.add(email);
    return { ...current, hosts: { ...current.hosts, users: [...users] } };
  });
  const toggleReminder = (hours) => setDraft((current) => {
    const list = new Set(current.reminders?.hours || []);
    if (list.has(hours)) list.delete(hours); else list.add(hours);
    return { ...current, reminders: { hours: [...list].sort((a, b) => b - a) } };
  });

  const save = async () => {
    setSaving(true);
    try {
      const keys = ["name", "public_key", "description", "brand_name", "duration_minutes", "buffer_before_minutes",
        "buffer_after_minutes", "min_notice_hours", "max_days_ahead", "slot_interval_minutes", "location", "hosts",
        "questions", "confirmation_message", "opportunity", "prep_task", "reminders", "notify_person", "status"];
      const body = Object.fromEntries(keys.map((key) => [key, draft[key] ?? null]).filter(([, value]) => value !== null));
      const { data } = await api.patch(`/booking/event-types/${eventType.id}`, body);
      toast.success("Booking page saved");
      onSaved(data);
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const base = (eventType.links?.page || "").replace(/[^/]+$/, "");
  const officeMissing = draft.location?.kind === "office" && !String(draft.location?.text || "").trim();

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-xl" data-testid="event-type-editor">
        <SheetHeader className="space-y-0.5 border-b border-border px-5 py-4 pr-12 text-left">
          <SheetTitle className="text-base font-semibold tracking-tight">Edit “{eventType.name}”</SheetTitle>
          <SheetDescription className="text-[13px]">Changes apply to new bookings. People who already booked keep their time.</SheetDescription>
        </SheetHeader>
        <div className="cv-scrollbar min-h-0 flex-1 divide-y divide-border/70 overflow-y-auto overflow-x-hidden px-5 py-5">
          <Section title="The page">
            <Field label="Name" htmlFor="et-name"><Input id="et-name" value={draft.name} className={TEXT} onChange={(event) => set({ name: event.target.value })} data-testid="et-name" /></Field>
            <Field label="Link" htmlFor="et-key" hint="Lowercase letters, numbers and dashes. Changing it breaks links you already shared.">
              <div className="flex h-9 min-w-0 items-center overflow-hidden rounded-md border border-input bg-muted/40 shadow-xs focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/15">
                <span className="min-w-0 max-w-[55%] shrink truncate pl-3 pr-1 text-[13px] text-muted-foreground" title={base}>{base}</span>
                <Input id="et-key" value={draft.public_key} className={cx("h-full min-w-0 flex-1 rounded-none border-0 border-l border-input bg-card shadow-none focus-visible:ring-0", TEXT)} onChange={(event) => set({ public_key: event.target.value.toLowerCase() })} data-testid="et-key" />
              </div>
            </Field>
            <Field label="What to expect" htmlFor="et-description"><Textarea id="et-description" rows={3} className={TEXT} value={draft.description || ""} onChange={(event) => set({ description: event.target.value })} /></Field>
            <Field label="Name shown at the top" htmlFor="et-brand" hint="Your name or your brokerage's. Leave empty to show the agent's name."><Input id="et-brand" className={TEXT} value={draft.brand_name || ""} onChange={(event) => set({ brand_name: event.target.value })} /></Field>
            <Toggle id="et-live" label="Taking bookings" hint="Turn off to pause the page; it shows as unavailable." checked={draft.status === "active"} onChange={(on) => set({ status: on ? "active" : "paused" })} />
          </Section>

          <Section title="When people can book" description="Only free times inside the agent's hours are offered.">
            <div className="grid gap-x-4 gap-y-4 sm:grid-cols-2">
              <Field label="Length" htmlFor="et-duration"><Minutes id="et-duration" value={draft.duration_minutes} min={5} onChange={(value) => set({ duration_minutes: value })} /></Field>
              <Field label="Start times every" htmlFor="et-interval"><Minutes id="et-interval" value={draft.slot_interval_minutes} min={5} max={240} onChange={(value) => set({ slot_interval_minutes: value })} /></Field>
              <Field label="Free time before" htmlFor="et-before" hint="Travel or prep. Nothing else is booked here."><Minutes id="et-before" value={draft.buffer_before_minutes} max={240} onChange={(value) => set({ buffer_before_minutes: value })} /></Field>
              <Field label="Free time after" htmlFor="et-after"><Minutes id="et-after" value={draft.buffer_after_minutes} max={240} onChange={(value) => set({ buffer_after_minutes: value })} /></Field>
              <Field label="Book at least" htmlFor="et-notice" hint="How much warning you need.">
                <Amount id="et-notice" value={draft.min_notice_hours} max={720} step="0.5" unit="hours ahead" testid="et-notice" onChange={(raw) => set({ min_notice_hours: Number(raw) })} />
              </Field>
              <Field label="Book up to" htmlFor="et-horizon">
                <Amount id="et-horizon" value={draft.max_days_ahead} min={1} max={365} unit="days ahead" onChange={(raw) => set({ max_days_ahead: Number(raw) })} />
              </Field>
            </div>
          </Section>

          <Section title="Where it happens">
            <Field label="Location" htmlFor="et-location" hint={LOCATION_HINTS[draft.location?.kind]}>
              <Select value={draft.location?.kind} onValueChange={(kind) => setIn("location", { kind })}>
                <SelectTrigger id="et-location" className="text-[13px]" data-testid="et-location"><SelectValue /></SelectTrigger>
                <SelectContent>{(catalog?.location_kinds || []).map((kind) => <SelectItem key={kind.key} value={kind.key}>{kind.label}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            {["office", "video"].includes(draft.location?.kind) && (
              <Field label={draft.location.kind === "office" ? "Office address" : "Meeting link"} htmlFor="et-location-text">
                <Input id="et-location-text" className={TEXT} value={draft.location.text || ""} placeholder={draft.location.kind === "office" ? "100 Main St, Suite 200, Springfield" : "https://zoom.us/j/…"} onChange={(event) => setIn("location", { text: event.target.value })} data-testid="et-location-text" />
              </Field>
            )}
            {officeMissing && (
              <p className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-700">
                <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />Add your office address so people know where to go.
              </p>
            )}
          </Section>

          <Section title="Who hosts it" description="Bookings land on the host's calendar, and the host gets the alerts.">
            <Field label="Host" htmlFor="et-host-mode">
              <Select value={draft.hosts.mode} onValueChange={(mode) => setIn("hosts", { mode, users: mode === "specific" ? draft.hosts.users.slice(0, 1) : draft.hosts.users })}>
                <SelectTrigger id="et-host-mode" className="text-[13px]" data-testid="et-host-mode"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="specific">One agent</SelectItem>
                  <SelectItem value="round_robin">Take turns (round-robin) — a returning client keeps their agent</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            {draft.hosts.mode === "specific" ? (
              <Select value={draft.hosts.users[0] || ""} onValueChange={(email) => setIn("hosts", { users: [email] })}>
                <SelectTrigger aria-label="Agent" className="text-[13px]" data-testid="et-host"><SelectValue placeholder="Choose an agent" /></SelectTrigger>
                <SelectContent>{hosts.map((host) => <SelectItem key={host.email} value={host.email}>{host.name}</SelectItem>)}</SelectContent>
              </Select>
            ) : (
              <div className="divide-y divide-border/70 overflow-hidden rounded-lg border border-border">
                {hosts.map((host) => (
                  <label key={host.email} className="flex cursor-pointer items-center gap-2.5 px-3 py-2 text-[13px] transition-colors hover:bg-muted/50">
                    <input type="checkbox" className={CHECKBOX} checked={draft.hosts.users.includes(host.email)} onChange={() => toggleHost(host.email)} data-testid={`et-host-${host.email}`} />
                    <span className="font-medium text-foreground">{host.name}</span><span className="min-w-0 truncate text-xs text-muted-foreground">{host.email}</span>
                  </label>
                ))}
              </div>
            )}
          </Section>

          <Section title="What it asks" description="Name and email are always asked.">
            <ul className="divide-y divide-border/70 overflow-hidden rounded-lg border border-border">
              {(catalog?.questions || []).map((question) => (
                <li key={question.key} className="flex min-h-10 items-center justify-between gap-3 px-3 py-1.5">
                  <label className="flex min-w-0 cursor-pointer items-center gap-2.5 text-[13px] text-foreground">
                    <input type="checkbox" className={CHECKBOX} checked={Boolean(asked[question.key])} onChange={(event) => toggleQuestion(question.key, event.target.checked)} data-testid={`et-q-${question.key}`} />
                    <span className="truncate">{question.label}</span>
                  </label>
                  {asked[question.key] && (
                    <div className="flex shrink-0 items-center gap-2">
                      <Label htmlFor={`et-req-${question.key}`} className="text-xs font-normal text-muted-foreground">Required</Label>
                      <Switch id={`et-req-${question.key}`} checked={Boolean(asked[question.key].required)} onCheckedChange={(value) => requireQuestion(question.key, value)} data-testid={`et-req-${question.key}`} />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </Section>

          <Section title="After someone books" description="The person becomes a lead and a contact either way.">
            <Toggle id="et-deal" label="Open a deal" hint="Valued at your expected commission when they give a price, or a flat value." checked={draft.opportunity?.enabled} onChange={(enabled) => setIn("opportunity", { enabled })} />
            {draft.opportunity?.enabled && (
              <div className="grid gap-4 rounded-lg border border-border bg-muted/30 p-3 sm:grid-cols-3">
                <Field label="Value" htmlFor="et-value-mode">
                  <Select value={draft.opportunity.value_mode} onValueChange={(value_mode) => setIn("opportunity", { value_mode })}>
                    <SelectTrigger id="et-value-mode" className="bg-card text-[13px]"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="commission">Commission</SelectItem><SelectItem value="fixed">Flat value</SelectItem></SelectContent>
                  </Select>
                </Field>
                {draft.opportunity.value_mode === "commission" && <Field label="Commission %" htmlFor="et-rate"><Input id="et-rate" type="number" step="0.1" min={0} className={cx("tabular", TEXT)} value={draft.opportunity.commission_rate} onChange={(event) => setIn("opportunity", { commission_rate: Number(event.target.value) })} /></Field>}
                <Field label={draft.opportunity.value_mode === "commission" ? "If no price" : "Value"} htmlFor="et-fixed"><Input id="et-fixed" type="number" min={0} className={cx("tabular", TEXT)} value={draft.opportunity.fixed_value} onChange={(event) => setIn("opportunity", { fixed_value: Number(event.target.value) })} /></Field>
              </div>
            )}
            <Toggle id="et-task" label="Give the host a preparation task" hint="For example arranging access for a showing. Use {name}, {address} and {type} in the wording." checked={draft.prep_task?.enabled} onChange={(enabled) => setIn("prep_task", { enabled })} />
            {draft.prep_task?.enabled && (
              <div className="grid gap-4 rounded-lg border border-border bg-muted/30 p-3 sm:grid-cols-[1fr_11rem]">
                <Field label="Task" htmlFor="et-task-title"><Input id="et-task-title" className={TEXT} value={draft.prep_task.title} onChange={(event) => setIn("prep_task", { title: event.target.value })} data-testid="et-task-title" /></Field>
                <Field label="Due" htmlFor="et-task-due">
                  <Select value={String(draft.prep_task.lead_minutes || 0)} onValueChange={(value) => setIn("prep_task", { lead_minutes: Number(value) })}>
                    <SelectTrigger id="et-task-due" className="bg-card text-[13px]"><SelectValue /></SelectTrigger>
                    <SelectContent>{LEAD_TIMES.map(([minutes, label]) => <SelectItem key={minutes} value={String(minutes)}>{label}</SelectItem>)}</SelectContent>
                  </Select>
                </Field>
              </div>
            )}
          </Section>

          <Section title="Confirmation and reminders">
            <Field label="Message on the confirmation" htmlFor="et-confirmation"><Textarea id="et-confirmation" rows={3} className={TEXT} value={draft.confirmation_message || ""} onChange={(event) => set({ confirmation_message: event.target.value })} /></Field>
            <div className="space-y-2">
              <div className="text-[13px] font-medium text-foreground" id="et-reminders-label">Remind before the appointment</div>
              <div className="flex flex-wrap gap-1.5" role="group" aria-labelledby="et-reminders-label">
                {(catalog?.reminder_hours || []).slice().reverse().map((hours) => {
                  const on = (draft.reminders?.hours || []).includes(hours);
                  return (
                    <button key={hours} type="button" onClick={() => toggleReminder(hours)} aria-pressed={on} data-testid={`et-reminder-${hours}`}
                      className={cx("tabular inline-flex h-7 items-center rounded-md border px-2.5 text-xs font-medium transition-colors",
                        on ? "border-brand/40 bg-brand-soft text-brand-strong" : "border-input bg-card text-muted-foreground hover:bg-muted/50 hover:text-foreground")}>
                      {hours >= 24 ? `${hours / 24} day${hours > 24 ? "s" : ""}` : `${hours} hour${hours > 1 ? "s" : ""}`}
                    </button>
                  );
                })}
              </div>
              <p className="text-xs leading-5 text-muted-foreground">The host always gets an in-app reminder. Up to three.</p>
            </div>
            <Toggle id="et-email-person" label="Email the person their confirmation and reminders" checked={draft.notify_person?.email} onChange={(email) => set({ notify_person: { email } })} />
            <p className="flex gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs leading-5 text-muted-foreground">
              <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
              Each email is written for you and waits until an admin approves its exact words — on the Calendar or in Approvals. Only the website-form auto-reply may be approved once for every lead. Emails go from your connected Gmail.
            </p>
          </Section>
        </div>
        <div className="flex shrink-0 justify-end gap-2 border-t border-border bg-muted/30 px-5 py-3">
          <Button size="sm" variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
          <Button size="sm" onClick={save} disabled={saving} data-testid="et-save"><Save />{saving ? "Saving…" : "Save"}</Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
