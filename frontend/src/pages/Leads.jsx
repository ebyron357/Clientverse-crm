/* Leads inbox: every website lead with its speed-to-lead clock, what the automation did,
   and one-click follow-through. A lead that arrives while this page is open appears on
   the next refresh (every 30 seconds) and its clock ticks without a reload. */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr } from "@/lib/api";
import { activityEntries } from "@/lib/contactHistory";
import { ActivityFeed } from "@/components/ContactRecord";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { AlarmClock, CheckCircle2, Clock3, Download, Globe, Mail, Phone, RefreshCw, Search, ShieldAlert, Timer, Zap } from "lucide-react";
import { describeLeadStep } from "@/lib/leadSteps";

const STATUS_TABS = [
  { key: "new", label: "New" },
  { key: "responded", label: "Contacted" },
  { key: "closed", label: "Closed" },
  { key: "spam", label: "Spam" },
  { key: "all", label: "All" },
];

const STATUS_STYLE = {
  new: "border-amber-200 bg-amber-50 text-amber-700",
  responded: "border-emerald-200 bg-emerald-50 text-emerald-700",
  closed: "border-slate-200 bg-slate-50 text-slate-600",
  spam: "border-red-200 bg-red-50 text-red-700",
};
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

function SlaBadge({ lead }) {
  const sla = lead.sla || {};
  if (lead.status === "responded" && sla.response_minutes != null) {
    const fast = sla.response_minutes <= 5;
    return <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${fast ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-600"}`}><CheckCircle2 className="h-3 w-3" />Responded in {duration(sla.response_minutes)}</span>;
  }
  if (lead.status !== "new" || !sla.due_at) return null;
  if (sla.escalated_at) {
    return <span className="inline-flex items-center gap-1 rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-700"><ShieldAlert className="h-3 w-3" />Escalated · waiting {duration(minutesBetween(lead.received_at))}</span>;
  }
  const remaining = -minutesBetween(sla.due_at);
  if (remaining >= 0) {
    return <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700"><Timer className="h-3 w-3" />Call within {duration(remaining)}</span>;
  }
  return <span className="inline-flex items-center gap-1 rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-700"><AlarmClock className="h-3 w-3" />Overdue {duration(-remaining)}</span>;
}

function Tile({ icon: Icon, label, value, hint, tone = "slate" }) {
  const tones = { slate: "bg-slate-50 text-slate-600", amber: "bg-amber-50 text-amber-700", emerald: "bg-emerald-50 text-emerald-700", red: "bg-red-50 text-red-700", cyan: "bg-brand-soft text-brand" };
  return (
    <div className="cv-card flex items-start gap-3 p-4">
      <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${tones[tone]}`}><Icon className="h-4 w-4" /></span>
      <div className="min-w-0">
        <div className="text-xs font-semibold text-slate-500">{label}</div>
        <div className="mt-1 font-display text-2xl font-semibold text-foreground">{value}</div>
        {hint && <div className="mt-0.5 text-xs text-slate-500">{hint}</div>}
      </div>
    </div>
  );
}

function Row({ label, children }) {
  if (children == null || children === "" || children === false) return null;
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-3 border-t border-slate-100 py-2 text-sm first:border-t-0">
      <dt className="text-slate-500">{label}</dt>
      <dd className="min-w-0 break-words text-foreground">{children}</dd>
    </div>
  );
}

function LeadDetail({ lead, onStatus, busy, refreshKey }) {
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
  const setStatus = async (status) => { await onStatus(lead, status, note); setNote(""); };
  return (
    <div className="space-y-6 pb-10">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${STATUS_STYLE[lead.status]}`}>{STATUS_LABEL[lead.status]}</span>
        <SlaBadge lead={lead} />
        {lead.is_test && <span className="rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-[11px] font-semibold text-violet-700">Test lead</span>}
      </div>

      <div className="flex flex-wrap gap-2">
        {lead.phone && <Button asChild size="sm" className="cv-action-primary"><a href={`tel:${lead.phone}`}><Phone className="mr-1.5 h-4 w-4" />Call {lead.phone}</a></Button>}
        {lead.phone && <Button asChild size="sm" variant="outline"><a href={`sms:${lead.phone}`}>Text</a></Button>}
        {lead.email && <Button asChild size="sm" variant="outline"><a href={`mailto:${lead.email}`}><Mail className="mr-1.5 h-4 w-4" />Email</a></Button>}
      </div>

      <section>
        <h3 className="mb-1 text-xs font-medium text-slate-500">Request</h3>
        <dl>
          <Row label="Form">{lead.form_name}</Row>
          <Row label="Email">{lead.email}</Row>
          <Row label="Phone">{lead.phone}</Row>
          <Row label="Message">{lead.message && <span className="whitespace-pre-wrap">{lead.message}</span>}</Row>
          {Object.entries(fields).filter(([key]) => !SKIP_FIELDS.has(key)).map(([key, value]) => (
            <Row key={key} label={FIELD_LABELS[key] || key.replace(/^custom_/, "").replace(/_/g, " ")}>{value === true ? "Yes" : value === false ? "No" : MONEY_FIELDS.has(key) && value !== "" && !Number.isNaN(Number(value)) ? formatMoney(value) : String(value)}</Row>
          ))}
          {Object.entries(extra).map(([key, value]) => <Row key={`x-${key}`} label={key}>{String(value)}</Row>)}
          <Row label="Received">{lead.received_at && new Date(lead.received_at).toLocaleString()}</Row>
        </dl>
      </section>

      <section>
        <h3 className="mb-1 text-xs font-medium text-slate-500">What happened automatically</h3>
        <dl>
          <Row label="Assigned to">{lead.assigned_name || lead.assigned_to || "Unassigned — all admins alerted"}</Row>
          <Row label="Contact">{lead.contact_id && <><Link className="font-semibold text-brand" to={`/contacts?contact=${lead.contact_id}`} data-testid="lead-contact-link">{contactName || "Open contact"}</Link><span className="text-slate-500"> · {lead.created_contact ? "new contact" : "already in your contacts"}</span></>}</Row>
          <Row label="Deal">{lead.opportunity_id && (deal
            ? <><Link className="font-semibold text-brand" to={`/deals?deal=${lead.opportunity_id}`} data-testid="lead-deal-link">{deal.name}</Link><span className="text-slate-500"> · {dealValue}</span></>
            : <Link className="font-semibold text-brand" to={`/deals?deal=${lead.opportunity_id}`} data-testid="lead-deal-link">Deal · {dealValue}</Link>)}</Row>
          <Row label="Call-back task">{lead.task_id && `Due ${lead.sla?.due_at ? new Date(lead.sla.due_at).toLocaleTimeString() : "now"}`}</Row>
          <Row label="Auto-reply">{lead.auto_reply?.status && lead.auto_reply.status !== "off" ? `${lead.auto_reply.status.replace(/_/g, " ")}${lead.auto_reply.detail ? ` — ${lead.auto_reply.detail}` : ""}` : null}</Row>
        </dl>
        {lead.automation?.length > 0 && (
          <ol className="mt-3 space-y-1 text-xs text-slate-500">
            {lead.automation.map((step, index) => <li key={index} className="flex gap-1.5">{step.result === "failed" ? <ShieldAlert className="mt-0.5 h-3 w-3 shrink-0 text-red-500" /> : <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-slate-400" />}{describeLeadStep(step, { assignee: lead.assigned_name || lead.assigned_to })}</li>)}
          </ol>
        )}
      </section>

      {(Object.keys(attribution).length > 0 || lead.origin) && (
        <section>
          <h3 className="mb-1 text-xs font-medium text-slate-500">Source</h3>
          <dl>
            <Row label="Website">{lead.origin}</Row>
            {Object.entries(attribution).map(([key, value]) => <Row key={key} label={key.replace(/_/g, " ")}>{value}</Row>)}
          </dl>
        </section>
      )}

      {consent && (
        <section>
          <h3 className="mb-1 text-xs font-medium text-slate-500">Consent record</h3>
          <dl>
            <Row label="Text messages">{consent.sms ? "Granted" : "Not given"}</Row>
            <Row label="Email">{consent.email ? "Granted" : "Not given"}</Row>
            <Row label="Wording shown">{consent.sms_text || consent.email_text}</Row>
            <Row label="Recorded">{consent.recorded_at && new Date(consent.recorded_at).toLocaleString()}</Row>
            <Row label="From">{[consent.ip, consent.page_url].filter(Boolean).join(" · ")}</Row>
          </dl>
        </section>
      )}

      {lead.contact_id && (
        <section>
          <div className="mb-2 flex items-center justify-between gap-3">
            <h3 className="text-xs font-medium text-slate-500">Notes and calls</h3>
            <Link className="text-xs font-semibold text-brand" to={`/contacts?contact=${lead.contact_id}`}>Open contact to log a call</Link>
          </div>
          {contact
            ? <ActivityFeed entries={notes} limit={5} empty="Nothing logged yet. A note you add below is saved here." testId="lead-notes" />
            : <Skeleton className="h-12 rounded-lg" />}
        </section>
      )}

      <section className="space-y-2">
        <h3 className="text-xs font-medium text-slate-500">Update</h3>
        <Textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Optional note — saved to the contact's history" rows={3} data-testid="lead-note" />
        <div className="flex flex-wrap gap-2">
          {lead.status !== "responded" && <Button size="sm" className="cv-action-primary" disabled={busy} onClick={() => setStatus("responded")}><CheckCircle2 className="mr-1.5 h-4 w-4" />Mark contacted</Button>}
          {lead.status !== "closed" && <Button size="sm" variant="outline" disabled={busy} onClick={() => setStatus("closed")}>Close</Button>}
          {lead.status !== "spam" && <Button size="sm" variant="outline" className="text-red-700" disabled={busy} onClick={() => setStatus("spam")}>Spam</Button>}
          {lead.status !== "new" && <Button size="sm" variant="ghost" disabled={busy} onClick={() => setStatus("new")}>Reopen</Button>}
        </div>
      </section>
    </div>
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

  return (
    <div className="cv-page" data-testid="leads-page">
      <div className="cv-page-header">
        <div>
          <div className="cv-eyebrow">Lead capture</div>
          <h1 className="cv-page-title">Leads</h1>
          <p className="cv-page-description">Every lead from your website forms, the speed-to-lead clock on each one, and what the CRM already did with it.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" asChild><Link to="/website-forms"><Globe className="mr-1.5 h-4 w-4" />Website forms</Link></Button>
          <Button variant="outline" onClick={exportCsv}><Download className="mr-1.5 h-4 w-4" />Export CSV</Button>
          <Button variant="outline" onClick={load} data-testid="leads-refresh"><RefreshCw className="mr-1.5 h-4 w-4" />Refresh</Button>
        </div>
      </div>

      {summary ? (
        <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Tile icon={Zap} tone={summary.open_now ? "amber" : "emerald"} label="Waiting for a response" value={summary.open_now} hint={summary.open_now ? "New leads nobody has contacted" : "Every lead has been contacted"} />
          <Tile icon={Clock3} tone="cyan" label="Median response" value={summary.median_response_minutes == null ? "—" : duration(summary.median_response_minutes)} hint={responseHint} />
          <Tile icon={ShieldAlert} tone={summary.sla_breaches ? "red" : "slate"} label="Escalated" value={summary.sla_breaches} hint={`Last ${summary.window_days} days`} />
          <Tile icon={Globe} tone="slate" label="Leads" value={summary.total} hint={`Last ${summary.window_days} days, test leads excluded`} />
        </div>
      ) : <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}</div>}

      <div className="cv-card">
        <div className="flex flex-col gap-3 border-b border-slate-100 p-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-1" role="tablist">
            {STATUS_TABS.map((tab) => (
              <button key={tab.key} type="button" role="tab" aria-selected={status === tab.key} onClick={() => setStatus(tab.key)}
                className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${status === tab.key ? "bg-foreground text-white" : "text-slate-600 hover:bg-slate-100"}`}>
                {tab.label}{tab.key === "new" && summary?.open_now ? ` (${summary.open_now})` : ""}
              </button>
            ))}
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Select value={formId} onValueChange={setFormId}>
              <SelectTrigger className="h-9 w-full sm:w-52"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All forms</SelectItem>
                {forms.map((form) => <SelectItem key={form.id} value={form.id}>{form.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
              <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name, email, phone, address, MLS #" className="h-9 pl-8 sm:w-72" />
            </div>
          </div>
        </div>

        {error && <div className="m-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800" role="status">{error}</div>}
        {leads === null ? (
          <div className="space-y-2 p-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-14 rounded-lg" />)}</div>
        ) : leads.length === 0 ? (
          <div className="p-10 text-center text-sm text-slate-500">
            {status === "new" ? "No leads are waiting. New website leads appear here within seconds." : "No leads match these filters."}
            {forms.length === 0 && <div className="mt-3"><Button asChild className="cv-action-primary"><Link to="/website-forms">Create your first website form</Link></Button></div>}
          </div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {leads.map((lead) => (
              <li key={lead.id}>
                <button type="button" onClick={() => open(lead)} className="flex w-full flex-col gap-2 px-5 py-4 text-left hover:bg-slate-50 sm:flex-row sm:items-center sm:justify-between" data-testid={`lead-${lead.id}`}>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-foreground">{lead.name || lead.email || lead.phone || "Website visitor"}</span>
                      <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${STATUS_STYLE[lead.status]}`}>{STATUS_LABEL[lead.status]}</span>
                      {lead.is_test && <span className="rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[11px] font-semibold text-violet-700">Test</span>}
                    </div>
                    <div className="mt-1 truncate text-sm text-slate-500">
                      {[lead.form_name, lead.property_address, lead.listing_id && `MLS ${lead.listing_id}`, lead.phone, lead.email].filter(Boolean).join(" · ")}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-3 text-xs text-slate-500">
                    <SlaBadge lead={lead} />
                    <span>{lead.assigned_name || lead.assigned_to || "Unassigned"}</span>
                    <span>{ago(lead.received_at)}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
        {leads && total > leads.length && <div className="border-t border-slate-100 px-5 py-3 text-xs text-slate-500">Showing the newest {leads.length} of {total}. Narrow the filters to find older leads.</div>}
      </div>

      <Sheet open={Boolean(selected)} onOpenChange={(value) => { if (!value) close(); }}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          {selected && (
            <>
              <SheetHeader className="mb-4">
                <SheetTitle>{selected.name || selected.email || selected.phone || "Website visitor"}</SheetTitle>
                <SheetDescription>{selected.form_name} · {ago(selected.received_at)}</SheetDescription>
              </SheetHeader>
              <LeadDetail lead={selected} onStatus={changeStatus} busy={busy} refreshKey={refreshKey} />
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
