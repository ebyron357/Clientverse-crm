/* The date-and-time picker every booking surface shares: the public booking page, the
   person's manage page and the agent's reschedule dialog.

   A month of days (arrow keys move a day or a week, Page Up/Down a month, Home/End the
   week's ends; days with no free time stay focusable but say so), the free times of the
   chosen day in the visitor's time zone (shown, and changeable), and a 12/24-hour toggle.
   `loadDays(first, last, zone)` returns the server's `days` for a range; the picker asks
   for one month at a time and remembers what it was told. A parent that learns of fresh
   times (a 409 "just taken") hands them over through `controlRef.current.update(days)`. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Globe2 } from "lucide-react";
import {
  addDays, addMonths, dayKey, formatDay, formatMonth, formatTime, monthEnd, monthStart,
  timeZoneOptions, weekdayOf, zoneLabel,
} from "@/lib/booking";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const KEYS = {
  ArrowLeft: { days: -1 }, ArrowRight: { days: 1 }, ArrowUp: { days: -7 }, ArrowDown: { days: 7 },
  PageUp: { months: -1 }, PageDown: { months: 1 },
};

function MonthGrid({ month, selected, counts, floorKey, maxKey, onSelect, onMonth, todayKey, testid }) {
  const [focusKey, setFocusKey] = useState(null);
  const wantFocus = useRef(false);
  const refs = useRef({});
  const first = monthStart(month);
  const last = monthEnd(month);
  const cells = [];
  for (let key = addDays(first, -weekdayOf(first)); cells.length < 42; key = addDays(key, 1)) cells.push(key);
  const weeks = [0, 1, 2, 3, 4, 5].map((row) => cells.slice(row * 7, row * 7 + 7))
    .filter((week) => week.some((key) => key >= first && key <= last));
  const inMonth = (key) => key && key >= first && key <= last;
  const tabStop = inMonth(focusKey) ? focusKey : inMonth(selected) ? selected
    : (cells.find((key) => inMonth(key) && counts[key]) || first);

  useEffect(() => {
    if (wantFocus.current && focusKey && refs.current[focusKey]) {
      wantFocus.current = false;
      refs.current[focusKey].focus();
    }
  });

  const onKeyDown = (event, key) => {
    let delta = KEYS[event.key];
    if (event.key === "Home") delta = { days: -weekdayOf(key) };
    if (event.key === "End") delta = { days: 6 - weekdayOf(key) };
    if (!delta) return;
    event.preventDefault();
    const next = delta.months ? addMonths(key, delta.months) : addDays(key, delta.days);
    if (next < monthStart(floorKey) || (maxKey && next > monthEnd(maxKey))) return;
    wantFocus.current = true;
    setFocusKey(next);
    if (!inMonth(next)) onMonth(monthStart(next));
  };

  return (
    <div data-testid={testid}>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-display text-base font-semibold text-foreground" aria-live="polite">{formatMonth(month)}</h3>
        <div className="flex gap-1">
          <button type="button" className="flex h-10 w-10 items-center justify-center rounded-full text-slate-600 hover:bg-slate-100 disabled:opacity-30"
            onClick={() => onMonth(addMonths(month, -1))} disabled={month <= monthStart(floorKey)}
            aria-label="Previous month" data-testid={`${testid}-prev`}><ChevronLeft className="h-5 w-5" /></button>
          <button type="button" className="flex h-10 w-10 items-center justify-center rounded-full text-slate-600 hover:bg-slate-100 disabled:opacity-30"
            onClick={() => onMonth(addMonths(month, 1))} disabled={Boolean(maxKey) && month >= monthStart(maxKey)}
            aria-label="Next month" data-testid={`${testid}-next`}><ChevronRight className="h-5 w-5" /></button>
        </div>
      </div>
      <table className="w-full table-fixed border-collapse" role="grid" aria-label={formatMonth(month)}>
        <thead>
          <tr>{WEEKDAYS.map((day) => <th key={day} scope="col" className="pb-2 text-center text-xs font-semibold text-slate-500">{day}</th>)}</tr>
        </thead>
        <tbody>
          {weeks.map((week) => (
            <tr key={week[0]}>
              {week.map((key) => {
                if (!inMonth(key)) return <td key={key} className="p-0.5" />;
                const count = counts[key] || 0;
                const isSelected = key === selected;
                const isToday = key === todayKey;
                const label = `${formatDay(key)}${isToday ? " (today)" : ""}, ${count ? `${count} time${count === 1 ? "" : "s"} free` : "no times free"}`;
                const tone = isSelected ? "bg-[var(--booking-accent)] font-bold text-white shadow-sm"
                  : count ? "bg-[var(--booking-accent-soft)] font-bold text-foreground hover:bg-[var(--booking-accent-hover)]"
                    : "cursor-default text-slate-400";
                return (
                  <td key={key} className="p-0.5 text-center">
                    <button type="button" ref={(node) => { refs.current[key] = node; }}
                      tabIndex={key === tabStop ? 0 : -1} aria-label={label} aria-pressed={isSelected} aria-disabled={!count}
                      onKeyDown={(event) => onKeyDown(event, key)} onFocus={() => setFocusKey(key)}
                      onClick={() => count && onSelect(key)} data-testid={`${testid}-day-${key}`}
                      className={`relative mx-auto flex h-11 w-11 items-center justify-center rounded-full text-sm transition-colors motion-reduce:transition-none sm:h-12 sm:w-12 ${tone} ${isToday && !isSelected ? "ring-1 ring-inset ring-slate-300" : ""}`}>
                      {Number(key.slice(8))}
                      {count > 0 && !isSelected && <span className="absolute bottom-1.5 h-1 w-1 rounded-full bg-[var(--booking-accent)]" aria-hidden="true" />}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ZoneSelect({ value, onChange, testid = "zone-select", id = "booking-zone" }) {
  const options = useMemo(() => timeZoneOptions([value]), [value]);
  return (
    <div className="flex items-center gap-2 text-sm text-slate-600">
      <Globe2 className="h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />
      <label htmlFor={id} className="sr-only">Time zone</label>
      <select id={id} value={value} onChange={(event) => onChange(event.target.value)} data-testid={testid}
        className="min-w-0 max-w-full flex-1 truncate rounded-lg border border-transparent bg-transparent py-1.5 pr-6 text-sm font-semibold text-foreground hover:border-slate-200 focus:border-slate-300">
        {options.map((zone) => <option key={zone} value={zone}>{zoneLabel(zone)}</option>)}
      </select>
    </div>
  );
}

/** The brand colour as the CSS variables the picker's classes read. */
export function brandStyle(color = "#0a6177") {
  const hex = /^#[0-9a-fA-F]{6}$/.test(color || "") ? color : "#0a6177";
  return { "--booking-accent": hex, "--booking-accent-soft": `${hex}14`, "--booking-accent-hover": `${hex}29` };
}

export default function SlotPicker({ loadDays, zone, onZoneChange, minKey, maxKey, onPick, selectedStart,
  controlRef, testid = "slot-picker", emptyHint = "No times are open in the next few weeks." }) {
  const todayKey = dayKey(new Date(), zone);
  const floorKey = minKey && minKey > todayKey ? minKey : todayKey;
  const [month, setMonth] = useState(monthStart(floorKey));
  const [selected, setSelected] = useState(null);
  const [byMonth, setByMonth] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hour12, setHour12] = useState(() => {
    try { return new Intl.DateTimeFormat(undefined, { hour: "numeric" }).resolvedOptions().hour12 !== false; } catch { return true; }
  });
  const searched = useRef(0);
  const timesRef = useRef(null);
  const cacheKey = `${zone}|${month}`;

  const fetchMonth = useCallback(async (monthKey) => {
    const firstKey = monthKey < floorKey ? floorKey : monthKey;
    const lastKey = maxKey && monthEnd(monthKey) > maxKey ? maxKey : monthEnd(monthKey);
    const key = `${zone}|${monthKey}`;
    if (lastKey < firstKey) { setByMonth((current) => ({ ...current, [key]: {} })); return; }
    setLoading(true);
    try {
      const days = await loadDays(firstKey, lastKey, zone);
      setByMonth((current) => ({ ...current, [key]: Object.fromEntries((days || []).map((day) => [day.date, day.slots])) }));
      setError("");
    } catch (exc) {
      setError(exc?.message || "Free times could not be loaded. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [zone, floorKey, maxKey, loadDays]);

  useEffect(() => { if (!byMonth[cacheKey]) fetchMonth(month); }, [cacheKey, month, byMonth, fetchMonth]);

  // On first load (and after a zone change) open the first day that has a free time,
  // looking a couple of months ahead before saying there is nothing.
  useEffect(() => {
    const map = byMonth[cacheKey];
    if (!map || selected) return;
    const firstDay = Object.keys(map).sort().find((key) => (map[key] || []).length);
    if (firstDay) { setSelected(firstDay); searched.current = 3; return; }
    if (searched.current < 2 && (!maxKey || addMonths(month, 1) <= monthStart(maxKey))) {
      searched.current += 1;
      setMonth(addMonths(month, 1));
    }
  }, [byMonth, cacheKey, month, maxKey, selected]);

  const changeZone = (next) => { searched.current = 0; setSelected(null); setMonth(monthStart(floorKey)); onZoneChange(next); };

  useEffect(() => {
    if (!controlRef) return;
    controlRef.current = {
      update: (days) => setByMonth((current) => {
        const target = { ...(current[cacheKey] || {}) };
        (days || []).forEach((day) => { target[day.date] = day.slots; });
        return { ...current, [cacheKey]: target };
      }),
      reload: () => setByMonth({}),
    };
  }, [controlRef, cacheKey]);

  const map = byMonth[cacheKey] || {};
  const counts = Object.fromEntries(Object.entries(map).map(([key, list]) => [key, list.length]));
  const times = (selected && map[selected]) || [];

  const pickDay = (key) => {
    setSelected(key);
    requestAnimationFrame(() => {
      if (window.matchMedia?.("(max-width: 639px)").matches) {
        const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        timesRef.current?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
      }
    });
  };

  return (
    <div className="grid gap-6 sm:grid-cols-[minmax(0,1fr)_13.5rem]" data-testid={testid}>
      <div className="min-w-0">
        <MonthGrid month={month} selected={selected} counts={counts} floorKey={floorKey} maxKey={maxKey}
          onSelect={pickDay} onMonth={setMonth} todayKey={todayKey} testid={`${testid}-month`} />
        <div className="mt-4 border-t border-slate-100 pt-3">
          <ZoneSelect value={zone} onChange={changeZone} testid={`${testid}-zone`} id={`${testid}-zone-select`} />
        </div>
        {error && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{error}</p>}
      </div>
      <div ref={timesRef} className="min-w-0 scroll-mt-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 className="font-display text-base font-semibold text-foreground">{selected ? formatDay(selected, "short") : "Pick a day"}</h3>
          <button type="button" onClick={() => setHour12((value) => !value)}
            className="rounded-full border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50"
            aria-label={hour12 ? "Show 24-hour times" : "Show 12-hour times"} data-testid={`${testid}-clock`}>{hour12 ? "24h" : "12h"}</button>
        </div>
        {loading && !times.length ? (
          <div className="space-y-2" aria-busy="true">{[0, 1, 2, 3].map((n) => <div key={n} className="h-12 animate-pulse rounded-lg bg-slate-100 motion-reduce:animate-none" />)}</div>
        ) : selected && times.length ? (
          <ul className="grid grid-cols-2 gap-2 p-0.5 sm:max-h-[26rem] sm:grid-cols-1 sm:overflow-y-auto" aria-label={`Free times on ${formatDay(selected)}`}>
            {times.map((start) => {
              const active = start === selectedStart;
              return (
                <li key={start}>
                  <button type="button" onClick={() => onPick(start)} aria-pressed={active} data-testid={`${testid}-time`}
                    data-start={start}
                    className={`h-12 w-full rounded-lg border-2 border-[var(--booking-accent)] text-sm font-bold transition-colors motion-reduce:transition-none ${active
                      ? "bg-[var(--booking-accent)] text-white"
                      : "text-[var(--booking-accent)] hover:bg-[var(--booking-accent)] hover:text-white focus-visible:bg-[var(--booking-accent)] focus-visible:text-white"}`}>
                    {formatTime(start, zone, hour12)}
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="rounded-lg bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
            {Object.values(counts).some(Boolean) ? "Choose a highlighted day to see its times." : emptyHint}
          </p>
        )}
      </div>
    </div>
  );
}
