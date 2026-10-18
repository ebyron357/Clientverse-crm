/* Booking helpers shared by the public booking page, the manage page and the calendar.

   The public pages talk to `/api/public/booking/...` with `fetch` and `credentials: "omit"`:
   a visitor's browser must never send a signed-in agent's CRM session along with a
   booking, and the booking page may be framed on an agent's website. JSON goes as
   text/plain so a cross-site browser sends it without a preflight. */
import { API } from "@/lib/api";

export async function publicCall(path, { method = "GET", body, params } = {}) {
  const query = params ? `?${new URLSearchParams(params).toString()}` : "";
  const response = await fetch(`${API}/public/booking/${path}${query}`, {
    method,
    credentials: "omit",
    headers: body ? { "Content-Type": "text/plain;charset=UTF-8", Accept: "application/json" } : { Accept: "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try { data = await response.json(); } catch { data = {}; }
  return { ok: response.ok, status: response.status, data };
}

export function browserTimeZone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; } catch { return "UTC"; }
}

const COMMON_ZONES = [
  "America/New_York", "America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles",
  "America/Anchorage", "Pacific/Honolulu", "America/Toronto", "America/Vancouver", "America/Mexico_City",
  "Europe/London", "Europe/Paris", "Europe/Berlin", "Asia/Dubai", "Asia/Kolkata", "Asia/Singapore",
  "Asia/Tokyo", "Australia/Sydney", "UTC",
];

/** Every zone the browser knows, common ones first. */
export function timeZoneOptions(extra = []) {
  let all = [];
  try { all = Intl.supportedValuesOf("timeZone"); } catch { all = []; }
  const seen = new Set();
  return [...extra, ...COMMON_ZONES, ...all].filter((zone) => zone && !seen.has(zone) && seen.add(zone));
}

export function zoneLabel(zone, at = new Date()) {
  try {
    const parts = new Intl.DateTimeFormat("en-US", { timeZone: zone, timeZoneName: "short" }).formatToParts(at);
    const short = parts.find((part) => part.type === "timeZoneName")?.value;
    const city = zone.split("/").pop().replace(/_/g, " ");
    return short ? `${city} (${short})` : city;
  } catch {
    return zone;
  }
}

/** "2026-10-20" for an instant, in a zone. */
export function dayKey(value, zone) {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
  } catch {
    return new Date(value).toISOString().slice(0, 10);
  }
}

export function addDays(key, days) {
  const date = new Date(`${key}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function monthStart(key) { return `${key.slice(0, 7)}-01`; }

export function addMonths(key, months) {
  const date = new Date(`${monthStart(key)}T12:00:00Z`);
  date.setUTCMonth(date.getUTCMonth() + months);
  return date.toISOString().slice(0, 10);
}

export function monthEnd(key) { return addDays(addMonths(key, 1), -1); }

export function weekdayOf(key) { return new Date(`${key}T12:00:00Z`).getUTCDay(); }

export function formatTime(value, zone, hour12 = true) {
  try {
    return new Intl.DateTimeFormat(undefined, { timeZone: zone, hour: "numeric", minute: "2-digit", hour12 }).format(new Date(value));
  } catch {
    return new Date(value).toLocaleTimeString();
  }
}

export function formatDay(key, style = "long") {
  const date = new Date(`${key}T12:00:00Z`);
  const options = style === "long"
    ? { weekday: "long", month: "long", day: "numeric", timeZone: "UTC" }
    : { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" };
  return new Intl.DateTimeFormat(undefined, options).format(date);
}

export function formatMonth(key) {
  return new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${key}T12:00:00Z`));
}

/** "Tuesday, October 20 · 2:00 – 2:30 PM" in the given zone. */
export function formatRange(start, end, zone) {
  const day = formatDay(dayKey(start, zone));
  if (!end) return `${day} · ${formatTime(start, zone)}`;
  return `${day} · ${formatTime(start, zone)} – ${formatTime(end, zone)}`;
}

export function newSubmissionId() {
  try { return window.crypto.randomUUID(); } catch { return `sid-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`; }
}

export const LOCATION_ICONS = { property: "home", office: "building", phone: "phone", video: "video" };

/** What the booking page sends as attribution: the page and any campaign tags on it. */
export function attribution() {
  const out = {};
  try {
    const params = new URLSearchParams(window.location.search);
    ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"].forEach((key) => {
      if (params.get(key)) out[key] = params.get(key).slice(0, 300);
    });
    out.page_url = window.location.href.slice(0, 1000);
    if (document.referrer) out.referrer = document.referrer.slice(0, 1000);
  } catch {
    /* no window: nothing to attribute */
  }
  return out;
}
