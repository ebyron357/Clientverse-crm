/* An agent's bookable hours: a time zone, the hours for each day of the week (with a
   break, if they want one), and days off or special hours. Admins can set anyone's;
   members set their own. Saved hours apply to every booking page the agent hosts. */
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { api, formatErr } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CalendarCheck2, Plus, Save, Trash2 } from "lucide-react";
import { browserTimeZone, formatDay, timeZoneOptions, zoneLabel } from "@/lib/booking";

const DAYS = [["mon", "Monday"], ["tue", "Tuesday"], ["wed", "Wednesday"], ["thu", "Thursday"], ["fri", "Friday"], ["sat", "Saturday"], ["sun", "Sunday"]];
const clone = (value) => JSON.parse(JSON.stringify(value));

function Hours({ block, onChange, onRemove, label, testid }) {
  return (
    <div className="flex items-center gap-2">
      <Input type="time" value={block.start} aria-label={`${label} from`} className="h-10 w-[7.5rem]" step={900}
        onChange={(event) => onChange({ ...block, start: event.target.value })} data-testid={`${testid}-start`} />
      <span className="text-sm text-slate-500">to</span>
      <Input type="time" value={block.end === "24:00" ? "23:59" : block.end} aria-label={`${label} until`} className="h-10 w-[7.5rem]" step={900}
        onChange={(event) => onChange({ ...block, end: event.target.value === "23:59" ? "24:00" : event.target.value })} data-testid={`${testid}-end`} />
      {onRemove && <Button type="button" size="icon" variant="ghost" className="h-9 w-9 text-slate-500" onClick={onRemove} aria-label={`Remove ${label} hours`}><Trash2 className="h-4 w-4" /></Button>}
    </div>
  );
}

export default function AvailabilityEditor({ items, hosts, me, isAdmin, googleAccount, onSaved }) {
  const [email, setEmail] = useState(me);
  const current = useMemo(() => items.find((item) => item.user_email === email) || items[0], [items, email]);
  const [draft, setDraft] = useState(() => current && clone(current));
  const [saving, setSaving] = useState(false);
  const [dayOff, setDayOff] = useState({ date: "", closed: true, start: "10:00", end: "14:00", label: "" });
  useEffect(() => {
    if (!current) return;
    const next = clone(current);
    // Never-saved hours start in this browser's zone: almost always the agent's own.
    if (!current.saved) next.timezone = browserTimeZone();
    setDraft(next);
  }, [current]);
  const zones = useMemo(() => timeZoneOptions([draft?.timezone]), [draft?.timezone]);
  if (!draft) return null;

  const setDay = (day, blocks) => setDraft((value) => ({ ...value, weekly: { ...value.weekly, [day]: blocks } }));
  const addDayOff = () => {
    if (!dayOff.date) { toast.error("Choose a date"); return; }
    const intervals = dayOff.closed ? [] : [{ start: dayOff.start, end: dayOff.end }];
    setDraft((value) => ({
      ...value,
      overrides: [...value.overrides.filter((o) => o.date !== dayOff.date), { date: dayOff.date, intervals, label: dayOff.label || null }]
        .sort((a, b) => a.date.localeCompare(b.date)),
    }));
    setDayOff({ date: "", closed: true, start: "10:00", end: "14:00", label: "" });
  };
  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put(`/booking/availability/${encodeURIComponent(draft.user_email)}`,
        { timezone: draft.timezone, weekly: draft.weekly, overrides: draft.overrides });
      toast.success("Hours saved — booking pages now offer these times");
      onSaved(data);
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };
  const today = new Date().toISOString().slice(0, 10);
  const who = hosts.find((host) => host.email === draft.user_email)?.name || draft.name || draft.user_email;

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_24rem]" data-testid="availability-editor">
      <section className="cv-card p-5">
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0">
            <h2 className="cv-card-title">{isAdmin && items.length > 1 ? "Hours for" : "Your hours"}</h2>
            {isAdmin && items.length > 1 ? (
              <Select value={draft.user_email} onValueChange={setEmail}>
                <SelectTrigger className="mt-2 h-10 w-full sm:w-72" aria-label="Agent" data-testid="availability-agent"><SelectValue /></SelectTrigger>
                <SelectContent>{items.map((item) => <SelectItem key={item.user_email} value={item.user_email}>{item.name || item.user_email}</SelectItem>)}</SelectContent>
              </Select>
            ) : <p className="cv-card-description">{who}</p>}
          </div>
          <div className="min-w-0 sm:w-72">
            <Label htmlFor="availability-zone" className="text-xs font-semibold text-slate-600">Time zone</Label>
            <select id="availability-zone" value={draft.timezone} onChange={(event) => setDraft({ ...draft, timezone: event.target.value })} data-testid="availability-zone"
              className="mt-1 h-10 w-full rounded-md border border-input bg-white px-3 text-sm">
              {zones.map((zone) => <option key={zone} value={zone}>{zoneLabel(zone)}</option>)}
            </select>
          </div>
        </div>
        {!current.saved && <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800" data-testid="availability-unsaved">These are the standard hours (Monday to Saturday, 9 to 6). Save them, or change them first.</p>}
        <ul className="divide-y divide-slate-100">
          {DAYS.map(([day, label]) => {
            const blocks = draft.weekly[day] || [];
            const on = blocks.length > 0;
            return (
              <li key={day} className="flex flex-col gap-3 py-3 sm:flex-row sm:items-start" data-testid={`availability-day-${day}`}>
                <div className="flex w-40 shrink-0 items-center gap-3 pt-1.5">
                  <Switch checked={on} onCheckedChange={(value) => setDay(day, value ? [{ start: "09:00", end: "18:00" }] : [])} aria-label={`Available on ${label}`} data-testid={`availability-toggle-${day}`} />
                  <span className={`text-sm font-semibold ${on ? "text-foreground" : "text-slate-400"}`}>{label}</span>
                </div>
                <div className="flex-1 space-y-2">
                  {on ? blocks.map((block, index) => (
                    <Hours key={index} block={block} label={label} testid={`availability-${day}-${index}`}
                      onChange={(next) => setDay(day, blocks.map((b, i) => (i === index ? next : b)))}
                      onRemove={blocks.length > 1 ? () => setDay(day, blocks.filter((_, i) => i !== index)) : null} />
                  )) : <p className="pt-2 text-sm text-slate-400">Not available</p>}
                  {on && blocks.length < 4 && (
                    <button type="button" className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:underline"
                      onClick={() => setDay(day, [...blocks, { start: "16:00", end: "18:00" }])}><Plus className="h-3.5 w-3.5" />Add hours (for a break)</button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
        <div className="mt-5 flex justify-end">
          <Button className="cv-action-primary" onClick={save} disabled={saving} data-testid="availability-save"><Save className="mr-1.5 h-4 w-4" />{saving ? "Saving…" : "Save hours"}</Button>
        </div>
      </section>

      <div className="space-y-5">
        <section className="cv-card p-5">
          <h2 className="cv-card-title">Days off and special hours</h2>
          <p className="cv-card-description mb-4">Holidays, vacations, or a Sunday open house. These replace the weekly hours on that date.</p>
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
              <div>
                <Label htmlFor="dayoff-date" className="text-xs font-semibold text-slate-600">Date</Label>
                <Input id="dayoff-date" type="date" min={today} value={dayOff.date} onChange={(event) => setDayOff({ ...dayOff, date: event.target.value })} className="mt-1 h-10" data-testid="dayoff-date" />
              </div>
              <div>
                <Label htmlFor="dayoff-label" className="text-xs font-semibold text-slate-600">Note (optional)</Label>
                <Input id="dayoff-label" value={dayOff.label} placeholder="e.g. Thanksgiving" onChange={(event) => setDayOff({ ...dayOff, label: event.target.value })} className="mt-1 h-10" />
              </div>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <Switch id="dayoff-closed" checked={dayOff.closed} onCheckedChange={(closed) => setDayOff({ ...dayOff, closed })} data-testid="dayoff-closed" />
              <Label htmlFor="dayoff-closed" className="font-normal">Closed all day</Label>
            </div>
            {!dayOff.closed && <Hours block={dayOff} label="Special" testid="dayoff-hours" onChange={(next) => setDayOff({ ...dayOff, start: next.start, end: next.end })} />}
            <Button variant="outline" onClick={addDayOff} data-testid="dayoff-add"><Plus className="mr-1 h-4 w-4" />Add</Button>
          </div>
          <ul className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200" data-testid="dayoff-list">
            {draft.overrides.length === 0 && <li className="px-3 py-3 text-sm text-slate-500">None yet.</li>}
            {draft.overrides.map((override) => (
              <li key={override.date} className="flex items-center justify-between gap-2 px-3 py-2.5 text-sm">
                <div className="min-w-0">
                  <div className="font-semibold text-foreground">{formatDay(override.date, "short")}{override.label ? ` · ${override.label}` : ""}</div>
                  <div className="text-xs text-slate-500">{override.intervals.length ? override.intervals.map((i) => `${i.start}–${i.end}`).join(", ") : "Closed"}</div>
                </div>
                <Button size="icon" variant="ghost" className="h-8 w-8 text-slate-500" aria-label={`Remove ${override.date}`}
                  onClick={() => setDraft((value) => ({ ...value, overrides: value.overrides.filter((o) => o.date !== override.date) }))}><Trash2 className="h-4 w-4" /></Button>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-slate-500">Remember to press “Save hours”.</p>
        </section>
        <section className="cv-card p-5 text-sm" data-testid="availability-google">
          <div className="flex items-start gap-2.5">
            <CalendarCheck2 className="mt-0.5 h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
            {googleAccount === draft.user_email
              ? <p className="text-slate-600">Busy times on <strong>{googleAccount}</strong>'s Google Calendar are taken off this agent's booking pages.</p>
              : googleAccount
                ? <p className="text-slate-600">The connected Google Calendar belongs to {googleAccount}, so only appointments in ClientVerse block this agent's times.</p>
                : <p className="text-slate-600">Google Calendar isn't connected, so only appointments in ClientVerse block these times. Connect it under Registries → Integrations to also skip times you're busy in Google.</p>}
          </div>
        </section>
      </div>
    </div>
  );
}
