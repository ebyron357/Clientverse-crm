/* Leads inbox: every website lead with its speed-to-lead clock, what the automation did,
   and one-click follow-through. A lead that arrives while this page is open appears on
   the next refresh (every 30 seconds) and its clock ticks without a reload. */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr } from "@/lib/api";
import { activityEntries } from "@/lib/contactHistory";
import { ActivityFeed } from "@/components/ContactRecord";
import { Avatar, PageHeader, PropertyList, StatStrip, StatusDot, Toolbar, ViewTabs } from "@/components/page/Page";
import { SurfaceEmpty } from "@/components/SurfaceState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { AlarmClock, CheckCircle2, CircleAlert, Download, Globe, Inbox, Mail, MessageSquare, Phone, RefreshCw, Search, ShieldAlert, Timer, UserPlus, Zap } from "lucide-react";
import { describeLeadStep } from "@/lib/leadSteps";

const STATUS_TABS = [
  { key: "new", label: "New" },
  { key: "responded", label: "Contacted" },
  { key: "closed", label: "Closed" },
  { key: "spam", label: "Spam" },
  { key: "all", label: "All" },
];

const STATUS_TONE = { new: "warning", responded: "success", closed: "neutral", spam: "danger" };
const STATUS_LABEL = { new: "New", responded: "Contacted", closed: "Closed", spam: "Spam" };

const FIELD_LABELS = {
  lead_type: "Interested in", property_address: "Property", listing_id: "MLS / listing #",
  price_min: "Min price", price_max: "Max price", estimated_home_value: "Home value",
  bedrooms: "Bedrooms", bathrooms: "Bathrooms", preferred_areas: "Areas",
  property_condition: "Condition", timeline: "Timeline", pre_approved: "Pre-approved",
  working_with_agent: "Has an agent", preferred_date: "Preferred date",
  preferred_time: "Preferred time", preferred_contact: "Best contact", consent_sms: "Text consent",
  consent_email: "Email consent",
};
const SKIP_FIELDS = new Set(["first_name", "last_name", "name", "email", "phone", "message"]);

export function formatMoney(value, currency = "USD") {
  if (value == null || Number.isNaN(Number(value))) return "—";
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(value));
  } catch {
    return `${currency} ${Math.round(Number(value)).toLocaleString()}`;
  }
}

function minutesBetween(fromIso, to = Date.now()) {
  return Math.round((to - new Date(fromIso).getTime()) / 60000);
}

/** "12 min", "3 h 5 min", "4 days": a wait or response time in words people read at a glance. */
export function duration(minutes) {
  const m = Math.max(0, Math.round(minutes));
  if (m < 60) return `${m} min`;
  if (m < 60 * 24) return m % 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m / 60} h`;
  const days = Math.floor(m / (60 * 24));
  return `${days} day${days === 1 ? "" : "s"}`;
}

const MONEY_FIELDS = new Set(["price_min", "price_max", "estimated_home_value"]);

function ago(iso) {
  if (!iso) return "—";
  const minutes = minutesBetween(iso);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 24) return `${Math.floor(minutes / 60)} h ago`;
  return new Date(iso).toLocaleDateString();
}

const fullDate = (iso) => (iso ? new Date(iso).toLocaleString() : "");
const shortDate = (iso) => (iso ? new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : null);
/** Narrower labels than the default so values like an email fit the side column on one line. */
const PROPS = "[&>div]:grid-cols-[96px_minmax(0,1fr)]";
const leadName = (lead) => lead.name || lead.email || lead.phone || "Website visitor";

/** Only the rows that have something to say; a lead form leaves most fields empty. */
const present = (items) => items.filter(({ value }) => value != null && value !== "" && value !== false);

const FLAG = "inline-flex items-center gap-1 whitespace-nowrap rounded-md border border-red-200 bg-red-50 px-1.5 py-0.5 text-[11px] font-medium text-red-700";

/** The speed-to-lead clock: a soft red flag once it has run out, quiet text before that. */
function speedFlag(lead) {
  const sla = lead.sla || {};
  if (lead.status === "responded" && sla.response_minutes != null) {
    const fast = sla.response_minutes <= 5;
    return <span className="inline-flex items-center gap-1 whitespace-nowrap text-xs text-muted-foreground"><CheckCircle2 className={`size-3.5 ${fast ? "text-emerald-600" : ""}`} aria-hidden="true" />Responded in {duration(sla.response_minutes)}</span>;
  }
  if (lead.status !== "new" || !sla.due_at) return null;
  if (sla.escalated_at) {
    return <span className={FLAG}><ShieldAlert className="size-3" aria-hidden="true" />Escalated · waiting {duration(minutesBetween(lead.received_at))}</span>;
  }
  const remaining = -minutesBetween(sla.due_at);
  if (remaining >= 0) {
    return <span className="inline-flex items-center gap-1 whitespace-nowrap text-xs font-medium text-amber-700"><Timer className="size-3.5" aria-hidden="true" />Call within {duration(remaining)}</span>;
  }
  return <span className={FLAG}><AlarmClock className="size-3" aria-hidden="true" />Overdue {duration(-remaining)}</span>;
}

function TestFlag({ children = "Test" }) {
  return <span className="rounded-md border border-violet-200 bg-violet-50 px-1.5 py-0.5 text-[11px] font-medium text-violet-700">{children}</span>;
}

function PanelHeading({ children, action }) {
  return <div className="mb-1.5 flex items-center justify-between gap-3">
    <h3 className="text-xs font-medium text-muted-foreground">{children}</h3>
    {action}
  </div>;
}

/** What happened to the lead, in order: it arrived, the automation ran, the clock ran out, someone answered. */
function leadHistory(lead) {
  const sla = lead.sla || {};
  const assignee = lead.assigned_name || lead.assigned_to;
  const events = [];
  if (lead.received_at) events.push({ key: "received", at: lead.received_at, icon: Inbox, text: `Came in through ${lead.form_name || "your website"}` });
  (lead.automation || []).forEach((step, index) => {
    const failed = step.result === "failed";
    events.push({ key: `step-${index}`, at: step.at, icon: failed ? ShieldAlert : Zap, tone: failed ? "danger" : null, text: describeLeadStep(step, { assignee }) });
  });
  if (sla.escalated_at) events.push({ key: "escalated", at: sla.escalated_at, icon: ShieldAlert, tone: "danger", text: "Escalated: nobody had responded, so the team was alerted" });
  if (sla.first_response_at) events.push({ key: "responded", at: sla.first_response_at, icon: CheckCircle2, tone: "success", text: sla.response_minutes != null ? `Contacted after ${duration(sla.response_minutes)}` : "Marked as contacted" });
  return events.sort((first, second) => new Date(first.at || 0) - new Date(second.at || 0));
}

function Timeline({ events }) {
  const tones = { danger: "text-red-600", success: "text-emerald-600" };
  return <ol className="space-y-0">
    {events.map(({ key, at, icon: Icon, tone, text }) => <li key={key} className="relative flex gap-3 pb-4 before:absolute before:bottom-0 before:left-[11px] before:top-7 before:w-px before:bg-border last:pb-0 last:before:hidden">
      <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border border-border bg-card"><Icon className={`size-3.5 ${tones[tone] || "text-muted-foreground"}`} aria-hidden="true" /></span>
      <div className="min-w-0 pt-0.5 text-[13px] leading-5">
        <span className="text-foreground/90">{text}</span>
        {at && <time dateTime={at} title={fullDate(at)} className="ml-1.5 whitespace-nowrap text-xs text-muted-foreground">{ago(at)}</time>}
      </div>
    </li>)}
  </ol>;
}

function LeadPanel({ lead, onStatus, busy, refreshKey }) {
  const [note, setNote] = useState("");
  // The contact this lead became: its name, its deals and what has been logged on it.
  // Read again after every update so a note saved below appears straight away.
  const [loaded, setLoaded] = useState(null);
  useEffect(() => {
    if (!lead.contact_id) return undefined;
    let current = true;
    api.get(`/contacts/${lead.contact_id}`)
      .then((response) => { if (current) setLoaded(response.data); })
      .catch(() => { if (current) setLoaded(null); });
    return () => { current = false; };
  }, [lead.contact_id, refreshKey]);
  // Kept while a refresh is in flight so the list does not flicker; never shown for a different lead.
  const contact = loaded?.contact?.id === lead.contact_id ? loaded : null;
  const fields = lead.fields || {};
  const attribution = lead.attribution || {};
  const extra = lead.extra || {};
  const consent = lead.consent;
  const contactName = contact?.contact?.name || lead.name || lead.email || lead.phone;
  const deal = (contact?.deals || []).find((item) => item.id === lead.opportunity_id);
  const dealValue = formatMoney(deal ? deal.value : lead.estimated_value, (deal && deal.currency) || lead.currency);
  const notes = useMemo(() => activityEntries(contact?.timeline, contactName), [contact, contactName]);
  const history = useMemo(() => leadHistory(lead), [lead]);
  const setStatus = async (status) => { await onStatus(lead, status, note); setNote(""); };

  const details = present([
    { label: "Form", value: lead.form_name },
    ...(lead.existing_client ? [{ label: "Relationship", value: "Existing client · no new deal opened" }] : []),
    { label: "Email", value: lead.email },
    { label: "Phone", value: lead.phone },
    ...Object.entries(fields).filter(([key]) => !SKIP_FIELDS.has(key)).map(([key, value]) => ({
      label: FIELD_LABELS[key] || key.replace(/^custom_/, "").replace(/_/g, " "),
      value: value === true ? "Yes" : value === false ? "No" : MONEY_FIELDS.has(key) && value !== "" && !Number.isNaN(Number(value)) ? formatMoney(value) : value == null ? null : String(value),
    })),
    ...Object.entries(extra).map(([key, value]) => ({ label: key, value: value == null ? null : String(value) })),
    { label: "Received", value: shortDate(lead.received_at) },
  ]);
  const followThrough = present([
    { label: "Assigned to", value: lead.assigned_name || lead.assigned_to || "Unassigned — all admins alerted" },
    { label: "Contact", value: lead.contact_id && <><Link className="font-medium text-brand hover:underline" to={`/contacts?contact=${lead.contact_id}`} data-testid="lead-contact-link">{contactName || "Open contact"}</Link><span className="block text-xs text-muted-foreground">{lead.created_contact ? "New contact" : "Already in your contacts"}</span></> },
    { label: "Deal", value: lead.opportunity_id && (deal
      ? <><Link className="font-medium text-brand hover:underline" to={`/deals?deal=${lead.opportunity_id}`} data-testid="lead-deal-link">{deal.name}</Link><span className="block text-xs text-muted-foreground tabular">{dealValue}</span></>
      : <Link className="font-medium text-brand hover:underline" to={`/deals?deal=${lead.opportunity_id}`} data-testid="lead-deal-link">Deal · {dealValue}</Link>) },
    { label: "Call-back task", value: lead.task_id && `Due ${lead.sla?.due_at ? new Date(lead.sla.due_at).toLocaleTimeString() : "now"}` },
    { label: "Auto-reply", value: lead.auto_reply?.status && lead.auto_reply.status !== "off" ? `${lead.auto_reply.status.replace(/_/g, " ")}${lead.auto_reply.detail ? ` — ${lead.auto_reply.detail}` : ""}` : null },
  ]);
  const source = present([
    { label: "Website", value: lead.origin },
    ...Object.entries(attribution).map(([key, value]) => ({ label: key.replace(/_/g, " "), value })),
  ]);
  const consentRows = consent ? present([
    { label: "Text messages", value: consent.sms ? "Granted" : "Not given" },
    { label: "Email", value: consent.email ? "Granted" : "Not given" },
    { label: "Wording shown", value: consent.sms_text || consent.email_text },
    { label: "Recorded", value: shortDate(consent.recorded_at) },
    { label: "From", value: [consent.ip, consent.page_url].filter(Boolean).join(" · ") },
  ]) : [];

  return (
    <div className="flex min-h-full flex-col" data-testid="lead-detail">
      <header className="border-b border-border px-5 pb-5 pt-6 sm:px-6">
        <div className="flex items-start gap-3.5 pr-8">
          <Avatar name={leadName(lead)} size="lg" />
          <div className="min-w-0 flex-1">
            <SheetTitle className="break-words text-lg font-semibold leading-7 tracking-tight">{leadName(lead)}</SheetTitle>
            <SheetDescription className="text-[13px]">{lead.form_name} · {ago(lead.received_at)}</SheetDescription>
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <StatusDot tone={STATUS_TONE[lead.status]}>{STATUS_LABEL[lead.status]}</StatusDot>
              {speedFlag(lead)}
              {lead.is_test && <TestFlag>Test lead</TestFlag>}
            </div>
          </div>
        </div>
        {(lead.phone || lead.email) && (
          <div className="mt-4 flex flex-wrap gap-2">
            {lead.phone && <Button asChild size="sm"><a href={`tel:${lead.phone}`}><Phone aria-hidden="true" />Call {lead.phone}</a></Button>}
            {lead.phone && <Button asChild size="sm" variant="outline"><a href={`sms:${lead.phone}`}><MessageSquare aria-hidden="true" />Text</a></Button>}
            {lead.email && <Button asChild size="sm" variant="outline"><a href={`mailto:${lead.email}`}><Mail aria-hidden="true" />Email</a></Button>}
          </div>
        )}
      </header>

      <div className="flex-1 lg:grid lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-7 px-5 pb-10 pt-5 sm:px-6">
          {lead.message && (
            <section>
              <PanelHeading>Message</PanelHeading>
              <blockquote className="whitespace-pre-wrap break-words border-l-2 border-border pl-3 text-sm leading-6 text-foreground">{lead.message}</blockquote>
            </section>
          )}

          <section>
            <PanelHeading>Update</PanelHeading>
            <div className="overflow-hidden rounded-xl border border-border bg-card transition-colors focus-within:border-ring">
              <Textarea value={note} onChange={(event) => setNote(event.target.value)} aria-label="Note" placeholder="Optional note — saved to the contact's history" rows={3}
                className="min-h-[76px] resize-none rounded-none border-0 bg-transparent text-[13px] shadow-none focus-visible:ring-0 focus-visible:ring-offset-0" data-testid="lead-note" />
              <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border bg-muted/30 px-2.5 py-2">
                {lead.status !== "new" && <Button size="sm" variant="ghost" disabled={busy} onClick={() => setStatus("new")}>Reopen</Button>}
                {lead.status !== "spam" && <Button size="sm" variant="outline" className="text-red-700" disabled={busy} onClick={() => setStatus("spam")}>Spam</Button>}
                {lead.status !== "closed" && <Button size="sm" variant="outline" disabled={busy} onClick={() => setStatus("closed")}>Close</Button>}
                {lead.status !== "responded" && <Button size="sm" disabled={busy} onClick={() => setStatus("responded")}><CheckCircle2 aria-hidden="true" />Mark contacted</Button>}
              </div>
            </div>
          </section>

          {lead.contact_id && (
            <section>
              <PanelHeading action={<Link className="text-xs font-medium text-brand hover:underline" to={`/contacts?contact=${lead.contact_id}`}>Open contact to log a call</Link>}>Notes and calls</PanelHeading>
              <div className="pt-1">
                {contact
                  ? <ActivityFeed entries={notes} limit={5} empty="Nothing logged yet. A note you add above is saved here." testId="lead-notes" />
                  : <Skeleton className="h-12 rounded-lg" />}
              </div>
            </section>
          )}

          {history.length > 0 && (
            <section>
              <PanelHeading>History</PanelHeading>
              <div className="pt-1.5"><Timeline events={history} /></div>
            </section>
          )}
        </div>

        <aside className="space-y-6 border-t border-border bg-muted/20 px-5 pb-10 pt-5 sm:px-6 lg:border-l lg:border-t-0 lg:px-5">
          <section>
            <PanelHeading>Details</PanelHeading>
            <PropertyList className={PROPS} items={details} />
          </section>
          <section>
            <PanelHeading>What happened automatically</PanelHeading>
            <PropertyList className={PROPS} items={followThrough} />
          </section>
          {source.length > 0 && (
            <section>
              <PanelHeading>Source</PanelHeading>
              <PropertyList className={PROPS} items={source} />
            </section>
          )}
          {consentRows.length > 0 && (
            <section>
              <PanelHeading>Consent record</PanelHeading>
              <PropertyList className={PROPS} items={consentRows} />
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}

function LeadRow({ lead, showStatus, onOpen }) {
  const flag = speedFlag(lead);
  const meta = [lead.form_name, lead.property_address, lead.listing_id && `MLS ${lead.listing_id}`, lead.phone, lead.email].filter(Boolean).join(" · ");
  return (
    <li className="border-b border-border/70 last:border-0">
      <button type="button" onClick={() => onOpen(lead)} data-testid={`lead-${lead.id}`}
        className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
        <Avatar name={leadName(lead)} size="sm" />
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-[13px] font-medium text-foreground">{leadName(lead)}</span>
            {lead.is_test && <TestFlag />}
            {lead.existing_client && <StatusDot tone="success" className="text-xs text-muted-foreground">Existing client</StatusDot>}
            {showStatus && <StatusDot tone={STATUS_TONE[lead.status]} className="text-xs text-muted-foreground">{STATUS_LABEL[lead.status]}</StatusDot>}
          </div>
          <div className="truncate text-xs text-muted-foreground">{meta}</div>
          {flag && <div className="mt-1 sm:hidden">{flag}</div>}
        </div>
        <div className="flex shrink-0 items-center gap-4 text-xs text-muted-foreground">
          <span className="hidden w-44 justify-end sm:flex">{flag}</span>
          <span className="hidden w-28 truncate text-right md:block">{lead.assigned_name || lead.assigned_to || "Unassigned"}</span>
          <time dateTime={lead.received_at} title={fullDate(lead.received_at)} className="tabular w-[4.5rem] text-right">{ago(lead.received_at)}</time>
        </div>
      </button>
    </li>
  );
}

export default function Leads() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [status, setStatus] = useState(searchParams.get("form") ? "all" : "new");
  const [formId, setFormId] = useState(searchParams.get("form") || "all");
  const [query, setQuery] = useState("");
  const [leads, setLeads] = useState(null);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState(null);
  const [forms, setForms] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [, setTick] = useState(0);
  const selectedId = searchParams.get("lead");

  const load = useCallback(async () => {
    const params = { limit: 100 };
    if (status !== "all") params.status = status;
    if (formId !== "all") params.form_id = formId;
    if (query.trim()) params.q = query.trim();
    try {
      const [leadResponse, summaryResponse, formResponse] = await Promise.all([
        api.get("/leads", { params }), api.get("/leads/summary"), api.get("/website-forms"),
      ]);
      setLeads(leadResponse.data.items); setTotal(leadResponse.data.total);
      setSummary(summaryResponse.data); setForms(formResponse.data.items || []); setError("");
    } catch (e) {
      setError(formatErr(e.response?.data?.detail) || "Leads could not be loaded.");
      setLeads((current) => current || []);
    }
  }, [status, formId, query]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const refresh = setInterval(load, 30000);
    const tick = setInterval(() => setTick((value) => value + 1), 15000);
    return () => { clearInterval(refresh); clearInterval(tick); };
  }, [load]);
  useEffect(() => {
    if (!selectedId) { setSelected(null); return; }
    const inList = (leads || []).find((item) => item.id === selectedId);
    if (inList) { setSelected(inList); return; }
    api.get(`/leads/${selectedId}`).then((response) => setSelected(response.data)).catch(() => setSelected(null));
  }, [selectedId, leads]);

  const open = (lead) => setSearchParams((params) => { params.set("lead", lead.id); return params; });
  const close = () => setSearchParams((params) => { params.delete("lead"); return params; });

  const changeStatus = async (lead, next, note) => {
    setBusy(true);
    try {
      const { data } = await api.patch(`/leads/${lead.id}`, { status: next, note: note || undefined });
      setSelected(data);
      setRefreshKey((value) => value + 1);
      toast.success(next === "responded" ? "Marked as contacted" : `Lead marked ${STATUS_LABEL[next].toLowerCase()}`);
      load();
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  const exportCsv = async () => {
    try {
      const params = {};
      if (status !== "all") params.status = status;
      if (formId !== "all") params.form_id = formId;
      const response = await api.get("/leads/export", { params, responseType: "blob" });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = url; link.download = "leads.csv"; link.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("The export could not be downloaded."); }
  };

  const responseHint = useMemo(() => {
    if (!summary?.responded) return "No responses recorded yet";
    return `${summary.within_5_minutes} of ${summary.responded} within 5 min`;
  }, [summary]);

  // The New tab always carries the number waiting; the open tab carries what it holds.
  const tabs = STATUS_TABS.map(({ key, label }) => ({
    value: key, label, testid: `leads-tab-${key}`,
    count: key === "new" ? summary?.open_now : key === status && leads ? total : undefined,
  }));

  return (
    <div className="cv-page" data-testid="leads-page">
      <PageHeader icon={UserPlus} title="Leads"
        description="Every website lead, its speed-to-lead clock, and what the CRM already did with it."
        actions={<>
          <Button variant="outline" size="sm" asChild><Link to="/website-forms"><Globe aria-hidden="true" />Website forms</Link></Button>
          <Button variant="outline" size="sm" onClick={exportCsv}><Download aria-hidden="true" />Export CSV</Button>
          <Button variant="outline" size="sm" className="w-8 px-0" onClick={load} aria-label="Refresh leads" title="Refresh" data-testid="leads-refresh"><RefreshCw aria-hidden="true" /></Button>
        </>} />

      {summary ? (
        <StatStrip className="mb-5" items={[
          { label: "Waiting for a response", value: summary.open_now, tone: summary.open_now ? "warning" : undefined, detail: summary.open_now ? "New leads nobody has contacted" : "Every lead has been contacted", testid: "leads-stat-waiting" },
          { label: "Median response", value: summary.median_response_minutes == null ? "—" : duration(summary.median_response_minutes), detail: responseHint, testid: "leads-stat-median" },
          { label: "Escalated", value: summary.sla_breaches, tone: summary.sla_breaches ? "danger" : undefined, detail: `Last ${summary.window_days} days`, testid: "leads-stat-escalated" },
          { label: "Leads", value: summary.total, detail: `Last ${summary.window_days} days, test leads excluded`, testid: "leads-stat-total" },
        ]} />
      ) : <Skeleton className="mb-5 h-[94px] rounded-xl" />}

      <ViewTabs label="Leads by status" items={tabs} value={status} onChange={setStatus} />
      <Toolbar>
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Search leads" placeholder="Name, email, phone, address, MLS #" className="h-8 pl-8 text-[13px]" />
        </div>
        <Select value={formId} onValueChange={setFormId}>
          <SelectTrigger className="h-8 w-full text-[13px] sm:w-48" aria-label="Form"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All forms</SelectItem>
            {forms.map((form) => <SelectItem key={form.id} value={form.id}>{form.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </Toolbar>

      {error && <div className="mb-3 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-700" role="status"><CircleAlert className="size-4 shrink-0" aria-hidden="true" />{error}</div>}

      <div className="overflow-hidden rounded-xl border border-border bg-card">
        {leads === null ? (
          <div className="space-y-2 p-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-11 rounded-lg" />)}</div>
        ) : leads.length === 0 ? (
          <div className="[&>.cv-empty]:rounded-none [&>.cv-empty]:border-0">
            <SurfaceEmpty icon={Inbox}
              title={status === "new" ? "No leads are waiting" : "No leads match these filters"}
              description={status === "new" ? "New website leads appear here within seconds." : "Try another status, form or search."}
              action={forms.length === 0 ? <Button asChild size="sm"><Link to="/website-forms">Create your first website form</Link></Button> : null}
              testid="leads-empty" />
          </div>
        ) : (
          <>
            <div className="hidden h-9 items-center gap-3 border-b border-border bg-muted/40 px-4 text-xs font-medium text-muted-foreground sm:flex" aria-hidden="true">
              <span className="flex-1 pl-9">Lead</span>
              <span className="flex shrink-0 gap-4">
                <span className="w-44 text-right">Speed to lead</span>
                <span className="hidden w-28 text-right md:block">Owner</span>
                <span className="w-[4.5rem] text-right">Received</span>
              </span>
            </div>
            <ul aria-label="Leads">
              {leads.map((lead) => <LeadRow key={lead.id} lead={lead} showStatus={status === "all"} onOpen={open} />)}
            </ul>
          </>
        )}
        {leads && total > leads.length && <div className="border-t border-border bg-muted/30 px-4 py-2.5 text-xs text-muted-foreground">Showing the newest {leads.length} of {total}. Narrow the filters to find older leads.</div>}
      </div>

      <Sheet open={Boolean(selected)} onOpenChange={(value) => { if (!value) close(); }}>
        <SheetContent className="w-full overflow-y-auto p-0 sm:max-w-[840px]">
          {selected && <LeadPanel lead={selected} onStatus={changeStatus} busy={busy} refreshKey={refreshKey} />}
        </SheetContent>
      </Sheet>
    </div>
  );
}
