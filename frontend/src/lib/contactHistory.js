/* A contact's history in plain words: what happened, who did it and when.

   The API keeps activities (calls, texts, notes a person logged), system events about
   the record, and website requests in separate places. This turns all three into one
   newest-first list of entries a person can read without knowing how the CRM stores
   them. Nothing here talks to the server. */

export const ACTIVITY_KINDS = [
  { key: "call", label: "Call", verb: "Called", placeholder: "What did you talk about?" },
  { key: "text", label: "Text", verb: "Texted", placeholder: "What did you send?" },
  { key: "email", label: "Email", verb: "Emailed", placeholder: "What was the email about?" },
  { key: "meeting", label: "Meeting", verb: "Met", placeholder: "Where did you meet, and what came of it?" },
  { key: "note", label: "Note", verb: "Note", placeholder: "Write a note…" },
];

// What can come of a phone call. Stored as the key; shown as the label.
export const CALL_OUTCOMES = [
  { key: "talked", label: "Talked" },
  { key: "left_voicemail", label: "Left voicemail" },
  { key: "no_answer", label: "No answer" },
];

const OUTCOME_LABELS = {
  ...Object.fromEntries(CALL_OUTCOMES.map((outcome) => [outcome.key, outcome.label])),
  reply_received: "They replied",
};

// Kinds that count as reaching the person: logging one marks their new website
// requests as contacted. A note does not.
export const OUTREACH_KINDS = new Set(["call", "text", "email", "meeting"]);

export const LEAD_STATUS_LABEL = { new: "New", responded: "Contacted", closed: "Closed", spam: "Spam" };
export const LEAD_STATUS_STYLE = {
  new: "border-amber-200 bg-amber-50 text-amber-700",
  responded: "border-emerald-200 bg-emerald-50 text-emerald-700",
  closed: "border-slate-200 bg-slate-50 text-slate-600",
  spam: "border-red-200 bg-red-50 text-red-700",
};

const FIELD_LABELS = {
  name: "name", email: "email", phone: "phone", role: "role", title: "job title",
  company_id: "company", owner: "owner", influence: "influence", sentiment: "relationship",
};

// The note the Leads inbox saves alongside a status change ("Lead responded").
const LEAD_NOTE_SUBJECT = /^Lead (new|responded|closed|spam)$/;

function humanise(value) {
  const text = String(value || "").replace(/[._]+/g, " ").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
}

export function outcomeLabel(outcome) {
  if (!outcome) return "";
  return OUTCOME_LABELS[outcome] || humanise(outcome);
}

export function stageLabel(stage) {
  return humanise(stage) || "Lead";
}

/** Who did it, as a person reads it. */
export function whoLabel(actor, actorName, contactName) {
  if (actorName) return actorName;
  const value = String(actor || "");
  if (!value) return "";
  if (value.startsWith("website_form:") || value === "system:website-forms") return "Your website";
  if (value === "inbound" || value.startsWith("provider:")) return contactName || "They";
  if (value === "system" || value.startsWith("system:") || value.startsWith("standing-approval:")) return "Automatic";
  return value;
}

/** "just now", "12 min ago", "3 h ago", then a date. */
export function agoLabel(iso) {
  if (!iso) return "";
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "";
  const minutes = Math.round((Date.now() - then.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 24) return `${Math.floor(minutes / 60)} h ago`;
  return then.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function fullDateLabel(iso) {
  if (!iso) return "";
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "";
  return then.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function activityEntry(item, contactName) {
  const kind = ACTIVITY_KINDS.find((entry) => entry.key === item.type);
  const inbound = item.direction === "inbound";
  let title = kind ? kind.verb : humanise(item.type);
  if (item.type === "email" && inbound) title = `${contactName || "They"} emailed you`;
  if (item.type === "status_change") title = "Status changed";
  const outcome = outcomeLabel(item.outcome);
  if (outcome && !(inbound && item.outcome === "reply_received")) title = `${title} · ${outcome}`;
  let subject = item.subject || "";
  if (item.type === "note" && LEAD_NOTE_SUBJECT.test(subject)) {
    title = "Note on a website request";
    subject = "";
  }
  return {
    id: `activity-${item.id}`, at: item.at, kind: item.type || "note", title,
    subject, body: item.body || "",
    who: whoLabel(item.actor, item.actor_name, contactName),
  };
}

function eventEntry(item, contactName) {
  const type = item.type || "";
  // Logging an activity also records an event naming it; the activity itself is
  // already in the list, so the event would only repeat it.
  if (/^activity\..+_logged$/.test(type)) return null;
  const who = whoLabel(item.actor, item.actor_name, contactName);
  const payload = item.payload || {};
  let title = humanise(type);
  let body = "";
  if (type === "contact.created") {
    title = payload.source === "website_form" ? "Added from your website" : "Added to contacts";
  } else if (type === "contact.updated") {
    const changed = (payload.changed || []).map((field) => FIELD_LABELS[field]).filter(Boolean);
    title = "Details changed";
    body = changed.length ? `Changed ${changed.join(", ")}` : "";
  } else if (type === "contact.archived") {
    title = "Archived";
  } else if (type === "contact.restored") {
    title = "Restored";
  }
  return { id: `event-${item.id}`, at: item.at, kind: "event", title, subject: "", body, who };
}

function requestEntry(lead) {
  const detail = [lead.property_address, lead.listing_id && `MLS ${lead.listing_id}`].filter(Boolean).join(" · ");
  return {
    id: `request-${lead.id}`, at: lead.received_at, kind: "request",
    title: `Sent a website request${lead.form_name ? ` · ${lead.form_name}` : ""}`,
    subject: detail, body: lead.message || "", who: "Your website", leadId: lead.id,
  };
}

/** One newest-first history from the contact's timeline and its website requests. */
export function historyEntries(timeline, requests, contactName) {
  const entries = [];
  for (const item of timeline || []) {
    const entry = item.kind === "activity" ? activityEntry(item, contactName) : eventEntry(item, contactName);
    if (entry) entries.push(entry);
  }
  for (const lead of requests || []) entries.push(requestEntry(lead));
  const time = (entry) => Date.parse(entry.at || "") || 0;
  return entries.sort((a, b) => time(b) - time(a));
}

/** Only what people did: calls, texts, emails, meetings and notes, newest first. */
export function activityEntries(timeline, contactName) {
  return (timeline || [])
    .filter((item) => item.kind === "activity")
    .map((item) => activityEntry(item, contactName));
}
