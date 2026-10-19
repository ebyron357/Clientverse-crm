/* Pipeline helpers shared by the board, the deal record and the stage editor.

   Stages come from the tenant's own pipeline (GET /pipelines/default). Whether a stage is
   open, won or lost is read from its `is_closed` / `is_won` flags -- the same rule the
   server applies -- never from its name, because a tenant can rename "Closed won". */
import { formatMoney } from "@/lib/api";

export const OUTCOME = { OPEN: "open", WON: "won", LOST: "lost" };

export function stageOutcome(stage) {
  if (!stage?.is_closed) return OUTCOME.OPEN;
  return stage.is_won ? OUTCOME.WON : OUTCOME.LOST;
}

/** The board's columns: open stages in pipeline order, then won, then lost. */
export function splitStages(stages) {
  const list = stages || [];
  return {
    open: list.filter((stage) => stageOutcome(stage) === OUTCOME.OPEN),
    won: list.filter((stage) => stageOutcome(stage) === OUTCOME.WON),
    lost: list.filter((stage) => stageOutcome(stage) === OUTCOME.LOST),
  };
}

// Open stages cycle through these; won and lost always look like won and lost.
const OPEN_ACCENTS = ["bg-muted-foreground/60", "bg-brand", "bg-violet-500", "bg-amber-500", "bg-sky-600", "bg-fuchsia-500", "bg-teal-500"];

export function stageAccent(stage, index) {
  const outcome = stageOutcome(stage);
  if (outcome === OUTCOME.WON) return "bg-emerald-500";
  if (outcome === OUTCOME.LOST) return "bg-rose-400";
  return OPEN_ACCENTS[index % OPEN_ACCENTS.length];
}

export function dealCurrency(deal, fallback = "USD") {
  const code = String(deal?.currency || "").trim().toUpperCase();
  return /^[A-Z]{3}$/.test(code) ? code : fallback;
}

/** Deal values grouped by currency. Pounds and dollars are never added together. */
export function totalsByCurrency(deals) {
  const totals = {};
  for (const deal of deals || []) {
    const value = Number(deal.value);
    if (!Number.isFinite(value)) continue;
    const code = dealCurrency(deal);
    totals[code] = (totals[code] || 0) + value;
  }
  return totals;
}

/** One formatted amount per currency, the usual currency first; a zero when empty. */
export function totalParts(totals, preferred = "USD") {
  const entries = Object.entries(totals || {});
  if (!entries.length) return [formatMoney(0, preferred)];
  const rank = (code) => (code === preferred ? "" : code);
  return entries.sort(([a], [b]) => rank(a).localeCompare(rank(b))).map(([code, amount]) => formatMoney(amount, code));
}

/** "$12,000" or "$12,000 · CA$4,000". */
export function formatTotals(totals, preferred = "USD") {
  return totalParts(totals, preferred).join(" · ");
}

/** The currency most of this tenant's deals are in, so a new deal starts in it. */
export function usualCurrency(deals) {
  const counts = {};
  for (const deal of deals || []) {
    const code = dealCurrency(deal);
    counts[code] = (counts[code] || 0) + 1;
  }
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] || "USD";
}

export const CURRENCIES = ["USD", "CAD", "GBP", "EUR", "AUD", "NZD", "MXN", "ZAR", "INR", "AED"];

export function currencyOptions(...extra) {
  return Array.from(new Set([...CURRENCIES, ...extra.filter(Boolean).map((code) => String(code).toUpperCase())]));
}

/** When the deal entered the stage it is in now: its last move there, else its creation. */
export function enteredStageAt(deal) {
  const history = deal?.stage_history || [];
  for (let index = history.length - 1; index >= 0; index -= 1) {
    if (history[index]?.to === deal.stage && history[index]?.at) return history[index].at;
  }
  return deal?.created_at || null;
}

export function daysInStage(deal, now = Date.now()) {
  const since = enteredStageAt(deal);
  const time = since ? new Date(since).getTime() : NaN;
  if (!Number.isFinite(time)) return null;
  return Math.max(0, Math.floor((now - time) / 86400000));
}

export function isWebsiteLead(deal) {
  return deal?.lead_source === "website" || deal?.source?.kind === "website_form";
}

/** "2027-06-30T00:00:00+00:00" -> "2027-06-30", for a date input. */
export function dateInputValue(iso) {
  if (!iso) return "";
  return String(iso).slice(0, 10);
}

/** A close date as people say it ("Jun 30, 2027"), read as a calendar day, not an instant. */
export function formatDay(iso, options = { month: "short", day: "numeric", year: "numeric" }) {
  const day = dateInputValue(iso);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return "";
  const [year, month, date] = day.split("-").map(Number);
  return new Date(year, month - 1, date).toLocaleDateString(undefined, options);
}

export function isOverdue(iso, now = new Date()) {
  const day = dateInputValue(iso);
  if (!day) return false;
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  return day < today;
}

/** How a person appears in an owner menu: their name, or their email when it is unknown. */
export function ownerLabel(owner) {
  return owner?.name || owner?.email || "";
}

/** A short display name for an owner email, using the team list when it has one. */
export function ownerName(email, owners) {
  if (!email) return "";
  const match = (owners || []).find((owner) => owner.email === email);
  if (match?.name) return match.name;
  return String(email).split("@")[0];
}

export function initials(text) {
  const parts = String(text || "").replace(/@.*/, "").split(/[\s._-]+/).filter(Boolean);
  return (parts[0]?.[0] || "?").toUpperCase() + (parts[1]?.[0] || "").toUpperCase();
}

/** A stage key the server accepts (`^[a-z0-9_]+$`), unique among `taken`. */
export function stageKeyFor(label, taken) {
  const base = String(label || "").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 48) || "stage";
  let key = base;
  let suffix = 2;
  while (taken.has(key)) { key = `${base}_${suffix}`; suffix += 1; }
  return key;
}
