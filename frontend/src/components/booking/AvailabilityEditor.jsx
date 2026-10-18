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
import { Avatar } from "@/components/page/Page";
import { CalendarCheck2, CalendarOff, CircleAlert, Globe, Plus, Save, Trash2 } from "lucide-react";
import { browserTimeZone, formatDay, timeZoneOptions, zoneLabel } from "@/lib/booking";

const DAYS = [["mon", "Monday"], ["tue", "Tuesday"], ["wed", "Wednesday"], ["thu", "Thursday"], ["fri", "Friday"], ["sat", "Saturday"], ["sun", "Sunday"]];
const clone = (value) => JSON.parse(JSON.stringify(value));
const cx = (...parts) => parts.filter(Boolean).join(" ");
const FIELD_LABEL = "text-xs font-medium text-foreground/80";

function Hours({ block, onChange, label, testid }) {
  return (
    <div className="flex items-center gap-1.5">
      <Input type="time" value={block.start} aria-label={`${label} from`} className="tabular h-8 w-[6.75rem] px-2 text-[13px] sm:w-[7.25rem] sm:px-2.5 md:text-[13px]" step={900}
        onChange={(event) => onChange({ ...block, start: event.target.value })} data-testid={`${testid}-start`} />
      <span className="text-[13px] text-muted-foreground" aria-hidden="true">–</span>
      <Input type="time" value={block.end === "24:00" ? "23:59" : block.end} aria-label={`${label} until`} className="tabular h-8 w-[6.75rem] px-2 text-[13px] sm:w-[7.25rem] sm:px-2.5 md:text-[13px]" step={900}
        onChange={(event) => onChange({ ...block, end: event.target.value === "23:59" ? "24:00" : event.target.value })} data-testid={`${testid}-end`} />
    </div>
  );
}

function IconButton({ label, onClick, children }) {
  return (
    <Button type="button" size="icon" variant="ghost" className="size-8 text-muted-foreground hover:text-foreground" onClick={onClick} aria-label={label} title={label}>{children}</Button>
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
  const pickAgent = isAdmin && items.length > 1;

  return (
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]" data-testid="availability-editor">
      <section className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="flex flex-col gap-3 border-b border-border/80 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-2.5">
            <Avatar name={who} size="md" />
            <div className="min-w-0">
              <h2 className="text-sm font-semibold tracking-tight text-foreground">{pickAgent ? "Hours for" : "Your hours"}</h2>
              {pickAgent ? (
                <Select value={draft.user_email} onValueChange={setEmail}>
                  <SelectTrigger className="mt-1 h-8 w-full text-[13px] sm:w-64" aria-label="Agent" data-testid="availability-agent"><SelectValue /></SelectTrigger>
                  <SelectContent>{items.map((item) => <SelectItem key={item.user_email} value={item.user_email}>{item.name || item.user_email}</SelectItem>)}</SelectContent>
                </Select>
              ) : <p className="truncate text-[12.5px] text-muted-foreground">{who}</p>}
            </div>
          </div>
          <div className="min-w-0 sm:w-64">
            <Label htmlFor="availability-zone" className={cx(FIELD_LABEL, "mb-1 flex items-center gap-1.5")}><Globe className="size-3.5 text-muted-foreground" aria-hidden="true" />Time zone</Label>
            <select id="availability-zone" value={draft.timezone} onChange={(event) => setDraft({ ...draft, timezone: event.target.value })} data-testid="availability-zone"
              className="h-8 w-full rounded-md border border-input bg-card px-2.5 text-[13px] text-foreground shadow-xs">
              {zones.map((zone) => <option key={zone} value={zone}>{zoneLabel(zone)}</option>)}
            </select>
          </div>
        </div>

        {!current.saved && (
          <p className="mx-4 mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-700" data-testid="availability-unsaved">
            <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />These are the standard hours (Monday to Saturday, 9 to 6). Save them, or change them first.
          </p>
        )}

        <ul className="px-1 py-1.5">
          {DAYS.map(([day, label]) => {
            const blocks = draft.weekly[day] || [];
            const on = blocks.length > 0;
            return (
              <li key={day} className="flex flex-col gap-2 rounded-lg px-3 py-2 sm:flex-row sm:items-start sm:gap-4" data-testid={`availability-day-${day}`}>
                <div className="flex h-8 w-36 shrink-0 items-center gap-3">
                  <Switch checked={on} onCheckedChange={(value) => setDay(day, value ? [{ start: "09:00", end: "18:00" }] : [])} aria-label={`Available on ${label}`} data-testid={`availability-toggle-${day}`} />
                  <span className={cx("text-[13px] font-medium", on ? "text-foreground" : "text-muted-foreground")}>{label}</span>
                </div>
                <div className="min-w-0 flex-1 space-y-1.5">
                  {on ? blocks.map((block, index) => (
                    <div key={index} className="flex items-center gap-1">
                      <Hours block={block} label={label} testid={`availability-${day}-${index}`}
                        onChange={(next) => setDay(day, blocks.map((b, i) => (i === index ? next : b)))} />
                      <span className="flex items-center sm:ml-1">
                        {index === 0 && blocks.length < 4
                          ? <IconButton label={`Add hours on ${label} (for a break)`} onClick={() => setDay(day, [...blocks, { start: "16:00", end: "18:00" }])}><Plus /></IconButton>
                          : <span className="size-8" aria-hidden="true" />}
                        {blocks.length > 1 && <IconButton label={`Remove ${label} hours`} onClick={() => setDay(day, blocks.filter((_, i) => i !== index))}><Trash2 /></IconButton>}
                      </span>
                    </div>
                  )) : <p className="flex h-8 items-center text-[13px] text-muted-foreground">Not available</p>}
                </div>
              </li>
            );
          })}
        </ul>

        <div className="flex flex-col gap-2 border-t border-border bg-muted/30 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-muted-foreground">Applies to every booking page {pickAgent ? "this agent hosts" : "you host"}, along with the days off.</p>
          <Button size="sm" onClick={save} disabled={saving} className="self-end sm:self-auto" data-testid="availability-save"><Save />{saving ? "Saving…" : "Save hours"}</Button>
        </div>
      </section>

      <div className="space-y-4">
        <section className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="border-b border-border/80 px-4 py-3">
            <h2 className="text-sm font-semibold tracking-tight text-foreground">Days off and special hours</h2>
            <p className="mt-0.5 text-[12.5px] leading-5 text-muted-foreground">Holidays, vacations, or a Sunday open house. These replace the weekly hours on that date.</p>
          </div>
          <div className="space-y-3 px-4 py-4">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
              <div className="space-y-1">
                <Label htmlFor="dayoff-date" className={FIELD_LABEL}>Date</Label>
                <Input id="dayoff-date" type="date" min={today} value={dayOff.date} onChange={(event) => setDayOff({ ...dayOff, date: event.target.value })} className="tabular h-8 text-[13px] md:text-[13px]" data-testid="dayoff-date" />
              </div>
              <div className="space-y-1">
                <Label htmlFor="dayoff-label" className={FIELD_LABEL}>Note <span className="font-normal text-muted-foreground">(optional)</span></Label>
                <Input id="dayoff-label" value={dayOff.label} placeholder="e.g. Thanksgiving" onChange={(event) => setDayOff({ ...dayOff, label: event.target.value })} className="h-8 text-[13px] md:text-[13px]" />
              </div>
            </div>
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor="dayoff-closed" className="text-[13px] font-normal text-foreground">Closed all day</Label>
              <Switch id="dayoff-closed" checked={dayOff.closed} onCheckedChange={(closed) => setDayOff({ ...dayOff, closed })} data-testid="dayoff-closed" />
            </div>
            {!dayOff.closed && <Hours block={dayOff} label="Special" testid="dayoff-hours" onChange={(next) => setDayOff({ ...dayOff, start: next.start, end: next.end })} />}
            <div className="flex justify-end">
              <Button size="sm" variant="outline" onClick={addDayOff} data-testid="dayoff-add"><Plus />Add</Button>
            </div>
          </div>
          <ul className="border-t border-border/80" data-testid="dayoff-list">
            {draft.overrides.length === 0 && (
              <li className="flex items-center gap-2 px-4 py-3 text-[13px] text-muted-foreground"><CalendarOff className="size-3.5" aria-hidden="true" />None yet.</li>
            )}
            {draft.overrides.map((override) => (
              <li key={override.date} className="flex items-center justify-between gap-2 border-b border-border/70 px-4 py-2 last:border-0">
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-medium text-foreground">{formatDay(override.date, "short")}{override.label ? <span className="font-normal text-muted-foreground"> · {override.label}</span> : ""}</div>
                  <div className="tabular text-xs text-muted-foreground">{override.intervals.length ? override.intervals.map((i) => `${i.start}–${i.end}`).join(", ") : "Closed"}</div>
                </div>
                <IconButton label={`Remove ${override.date}`}
                  onClick={() => setDraft((value) => ({ ...value, overrides: value.overrides.filter((o) => o.date !== override.date) }))}><Trash2 /></IconButton>
              </li>
            ))}
          </ul>
          <p className="border-t border-border/80 bg-muted/30 px-4 py-2 text-xs text-muted-foreground">Remember to press “Save hours”.</p>
        </section>
        <div className="flex items-start gap-2 rounded-lg border border-border px-3 py-2.5 text-[13px] leading-5 text-muted-foreground" data-testid="availability-google">
          <CalendarCheck2 className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          {googleAccount === draft.user_email
            ? <p>Busy times on <span className="font-medium text-foreground">{googleAccount}</span>'s Google Calendar are taken off this agent's booking pages.</p>
            : googleAccount
              ? <p>The connected Google Calendar belongs to {googleAccount}, so only appointments in ClientVerse block this agent's times.</p>
              : <p>Google Calendar isn't connected, so only appointments in ClientVerse block these times. Connect it under Registries → Integrations to also skip times you're busy in Google.</p>}
        </div>
      </div>
    </div>
  );
}
