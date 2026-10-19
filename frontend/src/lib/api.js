import axios from "axios";

// A blank base URL is deliberate for single-container production deployments:
// the React app and FastAPI API share one HTTPS origin at /api.
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
export const API = `${BACKEND_URL}/api`;

const TOKEN_KEY = "cv_access_token";

export function getStoredToken() {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore storage failures (private mode) */
  }
}

export function clearStoredToken() {
  setStoredToken(null);
}

export const api = axios.create({ baseURL: API, withCredentials: true });

api.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token) {
    config.headers = config.headers || {};
    if (!config.headers.Authorization) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

export const CAP_STATUS = {
  RESEARCHING: "bg-muted text-muted-foreground border-border",
  REQUIRES_CONFIGURATION: "bg-amber-50 text-amber-800 border-amber-200",
  PLANNED: "bg-blue-50 text-blue-700 border-blue-200",
  ALPHA: "bg-purple-50 text-purple-700 border-purple-200",
  BETA: "bg-orange-50 text-orange-700 border-orange-200",
  AVAILABLE: "bg-emerald-50 text-emerald-700 border-emerald-200",
  DEPRECATED: "bg-red-50 text-red-700 border-red-200 line-through",
};

export const HEALTH_BAND = {
  healthy: "text-emerald-700 bg-emerald-50 border-emerald-200",
  at_risk: "text-amber-700 bg-amber-50 border-amber-200",
  critical: "text-red-700 bg-red-50 border-red-200",
};

export const STATUS_COLOR = {
  open: "bg-blue-50 text-blue-700 border-blue-200",
  todo: "bg-muted text-muted-foreground border-border",
  in_progress: "bg-blue-50 text-blue-700 border-blue-200",
  in_review: "bg-amber-50 text-amber-700 border-amber-200",
  done: "bg-emerald-50 text-emerald-700 border-emerald-200",
  approved: "bg-emerald-50 text-emerald-700 border-emerald-200",
  draft: "bg-muted text-muted-foreground border-border",
  at_risk: "bg-amber-50 text-amber-700 border-amber-200",
  breached: "bg-red-50 text-red-700 border-red-200",
  fulfilled: "bg-emerald-50 text-emerald-700 border-emerald-200",
  requested: "bg-amber-50 text-amber-700 border-amber-200",
  approved_: "bg-emerald-50 text-emerald-700 border-emerald-200",
  rejected: "bg-red-50 text-red-700 border-red-200",
};

export function formatErr(detail) {
  if (detail == null) return "Something went wrong.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e) => e?.msg || JSON.stringify(e)).join(" ");
  return String(detail);
}

export const money = (n) => "$" + (n || 0).toLocaleString();

/**
 * Format an amount in its own currency, and never throw.
 *
 * `Intl.NumberFormat` raises a RangeError for a currency code it does not recognise, and a
 * render that throws takes the whole page down. A record carrying "usd ", "$" or "" must
 * cost one label, not the report: an unusable code falls back to the plain number with the
 * code beside it, and a non-finite amount shows as a dash.
 */
export function formatMoney(amount, currency) {
  const value = Number(amount);
  if (amount == null || !Number.isFinite(value)) return "—";
  const code = String(currency || "").trim().toUpperCase();
  if (/^[A-Z]{3}$/.test(code)) {
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency: code, maximumFractionDigits: 0 }).format(value);
    } catch {
      // An unrecognised code: fall through to the plain form below.
    }
  }
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}${code ? ` ${code}` : ""}`;
}

/** Amounts grouped by currency, one per currency, never added together. */
export function formatMoneyByCurrency(byCurrency) {
  const entries = Object.entries(byCurrency || {});
  if (!entries.length) return formatMoney(0, "USD");
  return entries.map(([code, amount]) => formatMoney(amount, code)).join(" · ");
}
