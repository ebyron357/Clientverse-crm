import { useCallback, useEffect, useState } from "react";
import { api, formatErr, formatMoney } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { PageHeader, PropertyList, Section, StatStrip, StatusDot } from "@/components/page/Page";
import { SurfaceEmpty, SurfaceError, SurfaceLoading } from "@/components/SurfaceState";
import { Link } from "react-router-dom";
import { ArrowDownLeft, ArrowRight, ArrowUpRight, BadgeCheck, ChevronLeft, FileSearch } from "lucide-react";

/**
 * The buyer-facing recovery report.
 *
 * The one rule this page exists to keep: potential value and confirmed recovered value
 * are never shown as one figure, and never next to each other without saying which is
 * which. Everything here is traceable — the numbers link to the cases, and a case opens
 * onto the messages, replies and records behind it.
 */

// Never throws: a malformed currency code on one record must not take the report down.
const money = (value, currency) => formatMoney(value || 0, currency || "USD");

// Why a case closed. A closed case leaves open potential, so "answered elsewhere", "gave
// up" and "test lead" must never look alike.
const CLOSE_REASON_LABEL = {
  not_recoverable: "Not recoverable",
  duplicate: "Duplicate",
  resolved: "Resolved",
  spam: "Spam",
  no_longer_relevant: "No longer relevant",
  source_resolved: "Source resolved",
  source_missing: "Source record removed",
  test_record: "Test record",
  deal_lost: "Deal lost",
  deal_archived: "Deal archived",
  deal_won_before_case: "Deal already won",
  outcome_recorded: "Outcome recorded, not attributed",
  sale_recorded_on_another_case: "Sale counted on another case",
  outcome_refused: "Outcome could not be booked",
  strategy_rejected: "Strategy rejected",
  attribution_window_elapsed: "No outcome within the window",
};
// What went quiet, in the words an agent uses. The raw source stays on the case record.
const SOURCE_LABEL = {
  web_enquiry: "Website lead not answered",
  missed_followup: "Follow-up overdue",
  dormant_deal: "Deal gone quiet",
  missed_call: "Missed call",
  unanswered_quote: "Quote not answered",
  unanswered_estimate: "Estimate not answered",
  no_response: "Client stopped replying",
  appointment_cancelled: "Appointment cancelled",
  appointment_no_show: "No-show",
  external_crm_event: "From another CRM",
};
const sourceLabel = (source) => SOURCE_LABEL[source] || source;

const STATE_LABEL = {
  detected: "Not worked yet",
  planned: "Plan ready",
  awaiting_approval: "Waiting for approval",
  approved: "Approved",
  executing: "In progress",
  engaged: "Client engaged",
  recovered: "Recovered",
  closed: "Closed",
  failed: "Failed",
};
const stateLabel = (state) => STATE_LABEL[state] || state;

// Where the record behind a case lives in the app, from its `kind:id` source reference.
const SOURCE_RECORD_LINK = {
  web_enquiry: { path: (id) => `/leads?lead=${id}`, label: "Open the lead" },
  opportunity: { path: (id) => `/deals?deal=${id}`, label: "Open the deal" },
  task: { path: (id) => `/tasks?task=${id}`, label: "Open the task" },
};
function sourceRecordLink(sourceEventId) {
  const [kind, id] = String(sourceEventId || "").split(":");
  const target = SOURCE_RECORD_LINK[kind];
  return target && id ? { to: target.path(id), label: target.label } : null;
}

const OPERATOR_CLOSE_REASONS = ["not_recoverable", "duplicate", "resolved", "spam", "no_longer_relevant"];
const closeLabel = (reason) => CLOSE_REASON_LABEL[reason] || reason;

const BASIS_LABEL = {
  reply_after_contact: "Client replied after we made contact",
  delivered_contact: "We reached the client; no reply",
  no_contact: "Nothing reached the client",
};


const BASIS_TONE = { reply_after_contact: "success", delivered_contact: "warning", no_contact: "neutral" };

// How a case's state reads as a status dot. Recovered is the only green; closed is quiet.
const STATE_TONE = {
  detected: "neutral",
  planned: "info",
  awaiting_approval: "warning",
  approved: "brand",
  executing: "brand",
  engaged: "violet",
  recovered: "success",
  closed: "neutral",
  failed: "danger",
};

const cx = (...parts) => parts.filter(Boolean).join(" ");
const when = (value) => (value ? new Date(value).toLocaleString() : "");
const fieldClass = "h-8 w-full rounded-md border border-input bg-background px-2.5 text-[13px] text-foreground shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/**
 * Money figures side by side in one divided strip. Each cell keeps its own label and note,
 * so potential and confirmed value are never read as one number.
 */
function ValueStrip({ items, testid }) {
  return (
    <div className={cx("grid divide-y divide-border overflow-hidden rounded-xl border border-border bg-card",
      items.length === 3 ? "md:grid-cols-3" : "sm:grid-cols-2", items.length === 3 ? "md:divide-x md:divide-y-0" : "sm:divide-x sm:divide-y-0")}
         data-testid={testid}>
      {items.map((item) => <ValueCell key={item.title} {...item} />)}
    </div>
  );
}

function ValueCell({ title, note, byCurrency, tone, footnote }) {
  const entries = Object.entries(byCurrency || {});
  const dot = { confirmed: "bg-emerald-500", potential: "bg-muted-foreground/60", other: "bg-muted-foreground/25" }[tone] || "bg-muted-foreground/25";
  return (
    <div className="flex min-w-0 flex-col px-4 py-3.5">
      <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <span className={cx("size-1.5 rounded-full", dot)} aria-hidden="true" />{title}
      </div>
      <div className={cx("mt-1 space-y-0.5", tone === "confirmed" ? "text-emerald-700" : "text-foreground")}>
        {entries.length === 0 ? (
          <div className="tabular text-[22px] font-semibold leading-7 tracking-tight text-muted-foreground">—</div>
        ) : entries.map(([currency, amount]) => (
          <div key={currency} className="tabular text-[22px] font-semibold leading-7 tracking-tight">{money(amount, currency)}</div>
        ))}
      </div>
      <p className="mt-1.5 text-xs leading-5 text-muted-foreground">{note}</p>
      {footnote ? <p className="mt-1 text-xs leading-5 text-foreground/80" data-testid="proof-potential-footnote">{footnote}</p> : null}
    </div>
  );
}

function openPotentialFootnote(revenue) {
  const parts = [];
  const withoutValue = revenue.open_cases_without_value || 0;
  const collapsed = revenue.open_cases_collapsed || 0;
  if (withoutValue) parts.push(`${withoutValue} open case${withoutValue === 1 ? "" : "s"} with no value yet (a missed call, say) — not in this figure.`);
  if (collapsed) parts.push(`${collapsed} case${collapsed === 1 ? "" : "s"} about an opportunity already counted, so not added again.`);
  if (revenue.potential_truncated) parts.push("Too many open cases to read in full; this figure is partial.");
  return parts.join(" ");
}

function CloseCaseControl({ caseId, onClosed }) {
  const [reason, setReason] = useState(OPERATOR_CLOSE_REASONS[0]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const close = () => {
    setBusy(true);
    setError("");
    api.post(`/recovery-cases/${caseId}/close`, { reason, note: note.trim() || null })
      .then(() => onClosed())
      .catch((e) => setError(formatErr(e.response?.data?.detail) || "The case could not be closed."))
      .finally(() => setBusy(false));
  };

  return (
    <section className="rounded-xl border border-border bg-card p-4" data-testid="proof-case-close">
      <h3 className="text-sm font-semibold text-foreground">Close this case</h3>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">
        Takes it out of open potential and withdraws anything still awaiting approval on it. The reason is shown on every report.
      </p>
      <div className="mt-3 space-y-2">
        <select
          className={fieldClass}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          aria-label="Reason for closing"
          data-testid="proof-case-close-reason"
        >
          {OPERATOR_CLOSE_REASONS.map((key) => <option key={key} value={key}>{closeLabel(key)}</option>)}
        </select>
        <input
          className={cx(fieldClass, "placeholder:text-muted-foreground")}
          value={note}
          maxLength={500}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Note (optional)"
          aria-label="Note"
        />
        <Button size="sm" variant="outline" className="w-full" onClick={close} disabled={busy} data-testid="proof-case-close-submit">
          {busy ? "Closing…" : "Close case"}
        </Button>
      </div>
      {error ? <p className="mt-2 text-xs text-red-700" role="alert">{error}</p> : null}
    </section>
  );
}

const OPEN_STATES = ["detected", "planned", "awaiting_approval", "approved", "executing", "engaged"];

function CloseReasonBadge({ reason, testid, prefix = "" }) {
  return (
    <span className="inline-flex items-center rounded-md border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[11.5px] font-medium text-amber-700"
          data-testid={testid}>
      {prefix}{closeLabel(reason)}
    </span>
  );
}

function CaseProof({ caseId, onBack, onChanged }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [proof, setProof] = useState(null);
  const [loadError, setLoadError] = useState("");

  const load = useCallback(() => {
    setLoadError("");
    api.get(`/proof/cases/${caseId}`)
      .then((r) => setProof(r.data))
      .catch((e) => { setLoadError(e.response?.data?.detail || "Could not load this case."); setProof(null); });
  }, [caseId]);
  useEffect(() => { load(); }, [load]);

  const back = (
    <Button variant="ghost" size="sm" className="-ml-2.5 mb-3 text-muted-foreground hover:text-foreground" onClick={onBack} data-testid="proof-case-back">
      <ChevronLeft aria-hidden="true" />All cases
    </Button>
  );

  if (loadError) return <div>{back}<SurfaceError title="Case proof unavailable" description={String(loadError)} onRetry={load} testid="proof-case-error" /></div>;
  if (!proof) return <div>{back}<SurfaceLoading rows={3} testid="proof-case-loading" /></div>;

  const { communications: comms, value, attribution } = proof;
  const sourceLink = sourceRecordLink(proof.case.source_event_id);
  const messages = [...(comms.outbound || []), ...(comms.inbound || [])];

  return (
    <div data-testid="proof-case">
      {back}

      <header className="border-b border-border pb-4">
        <h2 className="text-lg font-semibold tracking-tight text-foreground">{proof.case.title || "Recovery case"}</h2>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <StatusDot tone={STATE_TONE[proof.case.state]}>{stateLabel(proof.case.state)}</StatusDot>
          <span className="text-[13px] text-muted-foreground">{sourceLabel(proof.case.source)}</span>
          {proof.case.close_reason ? (
            <CloseReasonBadge reason={proof.case.close_reason} prefix="Closed: " testid="proof-case-close-reason-badge" />
          ) : null}
        </div>
        {proof.case.close_reason ? (
          <p className="mt-1.5 text-xs text-muted-foreground">
            Closed {proof.case.closed_at ? when(proof.case.closed_at) : ""}
            {proof.case.closed_by ? ` by ${proof.case.closed_by}` : ""}{proof.case.close_note ? ` — ${proof.case.close_note}` : ""}
          </p>
        ) : null}
      </header>

      <div className="mt-5 lg:flex">
        <div className="min-w-0 flex-1 space-y-6 lg:pr-6">
          {proof.case.reason_detected ? (
            <Section title="Why it was detected">
              <p className="max-w-3xl text-[13px] leading-6 text-foreground/80">{proof.case.reason_detected}</p>
            </Section>
          ) : null}

          <ValueStrip items={[
            {
              title: "Potential value",
              tone: "potential",
              byCurrency: value.potential_value ? { [value.currency]: value.potential_value } : {},
              note: `What this opportunity might be worth. An estimate, not revenue.${value.potential_value_basis ? ` Basis: ${value.potential_value_basis}.` : ""}`,
              footnote: value.potential_value_note ? `The source's value was not used: ${value.potential_value_note}.` : "",
            },
            {
              title: "Confirmed recovered",
              tone: "confirmed",
              byCurrency: value.confirmed_recovered_value ? { [value.confirmed_currency || value.currency]: value.confirmed_recovered_value } : {},
              note: "Money a record says arrived. Never derived from the figure beside it.",
            },
          ]} />

          <StatStrip items={[
            { label: "Messages drafted", value: comms.messages_drafted },
            { label: "Actually sent", value: comms.messages_actually_sent, detail: "Accepted by a provider" },
            { label: "Replies", value: comms.replies_received },
            { label: "Outcome unknown", value: comms.messages_outcome_unknown, detail: "Never counted as sent" },
          ]} />

          <Section title="Attribution">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              <StatusDot tone={BASIS_TONE[attribution.basis] || "neutral"}>{BASIS_LABEL[attribution.basis] || "No claim"}</StatusDot>
              <StatusDot tone={attribution.claimed ? "success" : "neutral"}>{attribution.claimed ? "Claimed" : "Not claimed"}</StatusDot>
            </div>
            <p className="mt-2 max-w-3xl text-[13px] leading-6 text-muted-foreground">{attribution.reason}</p>
            {attribution.evidence?.length > 0 && (
              <ul className="mt-3 divide-y divide-border/70 overflow-hidden rounded-xl border border-border bg-card" data-testid="proof-attribution-evidence">
                {attribution.evidence.map((item) => (
                  <li key={item.record_id} className="px-4 py-2.5 text-[13px]">
                    <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                      <span className="font-medium text-foreground">{item.kind.replace(/_/g, " ")}</span>
                      <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">{item.record_id}</code>
                      {item.at ? <time className="tabular ml-auto text-xs text-muted-foreground" dateTime={item.at}>{when(item.at)}</time> : null}
                    </div>
                    {item.detail ? <div className="mt-0.5 text-xs leading-5 text-muted-foreground">{item.detail}</div> : null}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          {comms.outbound?.length > 0 && (
            <Section title={<>Messages <span className="tabular ml-1 font-normal text-muted-foreground">{messages.length}</span></>}>
              <ol className="divide-y divide-border/70 overflow-hidden rounded-xl border border-border bg-card">
                {messages.map((message) => {
                  const inbound = message.direction === "inbound";
                  const DirectionIcon = inbound ? ArrowDownLeft : ArrowUpRight;
                  const at = message.sent_at || message.created_at;
                  return (
                    <li key={message.id} className="flex gap-3 px-4 py-3" data-testid={`proof-message-${message.id}`}>
                      <span className={cx("mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full",
                        inbound ? "bg-sky-50 text-sky-700" : "bg-muted text-muted-foreground")} aria-hidden="true">
                        <DirectionIcon className="size-3.5" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs">
                          <span className="font-medium capitalize text-foreground">{message.direction}</span>
                          <StatusDot tone="neutral" className="text-xs">{message.status}</StatusDot>
                          {at ? <time className="tabular text-muted-foreground" dateTime={at}>{when(at)}</time> : null}
                          {message.provider_message_id ? <code className="truncate font-mono text-[11px] text-muted-foreground">{message.provider_message_id}</code> : null}
                        </div>
                        <p className="mt-1 line-clamp-2 text-[13px] leading-5 text-foreground/80">{message.body}</p>
                      </div>
                    </li>
                  );
                })}
              </ol>
            </Section>
          )}
        </div>

        <aside className="mt-6 space-y-5 lg:mt-0 lg:w-80 lg:shrink-0 lg:border-l lg:border-border lg:pl-6">
          <Section title="Details">
            <PropertyList items={[
              { label: "State", value: <StatusDot tone={STATE_TONE[proof.case.state]}>{stateLabel(proof.case.state)}</StatusDot> },
              { label: "Detected", value: proof.case.detected_at ? <span className="tabular">{when(proof.case.detected_at)}</span> : "—" },
              { label: "Owner", value: proof.case.owner_name || proof.case.owner || "Unassigned" },
              {
                label: "Source record",
                value: sourceLink ? (
                  <Link to={sourceLink.to} className="inline-flex items-center gap-1 font-medium text-brand hover:underline" data-testid="proof-case-source-link">
                    {sourceLink.label}<ArrowRight className="size-3.5" aria-hidden="true" />
                  </Link>
                ) : (
                  <code className="break-all font-mono text-xs text-muted-foreground">{proof.source_record ? `${proof.source_record.collection}/${proof.source_record.id}` : proof.case.source_event_id || "—"}</code>
                ),
              },
            ]} />
          </Section>
          {isAdmin && OPEN_STATES.includes(proof.case.state) ? (
            <CloseCaseControl caseId={caseId} onClosed={() => { load(); if (onChanged) onChanged(); }} />
          ) : null}
        </aside>
      </div>
    </div>
  );
}

const caseColumns = "sm:grid-cols-[minmax(0,1fr)_150px_110px_110px] lg:grid-cols-[minmax(0,1fr)_160px_180px_120px_120px]";

export default function RecoveryProof() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [report, setReport] = useState(null);
  const [cases, setCases] = useState(null);
  const [selected, setSelected] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [recheck, setRecheck] = useState({ busy: false, note: "" });

  const load = useCallback(() => {
    setLoadError("");
    Promise.all([api.get("/proof/portfolio"), api.get("/recovery-cases?state=all&limit=100")])
      .then(([portfolio, caseList]) => {
        setReport(portfolio.data);
        setCases(Array.isArray(caseList.data) ? caseList.data : caseList.data?.items || []);
      })
      .catch((e) => { setLoadError(e.response?.data?.detail || "Could not load the recovery report."); setReport(null); });
  }, []);
  useEffect(() => { load(); }, [load]);

  // Re-reads every open case's source and closes what has resolved. The detection sweeps
  // do this on schedule; this is the explicit, on-demand version for an admin.
  const recheckSources = () => {
    setRecheck({ busy: true, note: "" });
    api.post("/recovery-cases/reconcile")
      .then(({ data }) => {
        const closed = Object.values(data.closed || {}).reduce((sum, count) => sum + count, 0);
        const outcomes = (data.outcomes || []).length;
        setRecheck({ busy: false, note: `Checked ${data.examined} open case(s): ${closed} closed, ${outcomes} outcome(s) recorded.` });
        load();
      })
      .catch((e) => setRecheck({ busy: false, note: formatErr(e.response?.data?.detail) || "Sources could not be re-checked." }));
  };

  if (loadError) {
    return <div className="cv-page"><SurfaceError title="Recovery report unavailable" description={String(loadError)} onRetry={load} testid="proof-error" /></div>;
  }

  return (
    <div className="cv-page" data-testid="proof-page">
      <PageHeader
        icon={BadgeCheck}
        title="Recovery Proof"
        description="Potential and confirmed recovered value are reported separately and never added together."
        actions={isAdmin ? (
          <Button size="sm" variant="outline" onClick={recheckSources} disabled={recheck.busy} data-testid="proof-recheck">
            {recheck.busy ? "Re-checking…" : "Re-check sources"}
          </Button>
        ) : null}
      >
        {recheck.note ? (
          <p className="-mt-2 text-xs text-muted-foreground" data-testid="proof-recheck-note" role="status">{recheck.note}</p>
        ) : null}
      </PageHeader>

      {!report ? <SurfaceLoading rows={3} testid="proof-loading" /> : selected ? (
        <CaseProof caseId={selected} onBack={() => setSelected(null)} onChanged={load} />
      ) : (
        <div className="space-y-6">
          <ValueStrip testid="proof-revenue" items={[
            {
              title: "Open potential",
              tone: "potential",
              byCurrency: report.revenue.potential_value_open_by_currency,
              note: "An estimate of what un-recovered cases might be worth, each opportunity counted once. Not revenue.",
              footnote: openPotentialFootnote(report.revenue),
            },
            {
              title: "Attributed recovered",
              tone: "confirmed",
              byCurrency: report.revenue.attributed_recovered_value_by_currency,
              note: "Money a record says arrived, on cases where outreach demonstrably reached the client.",
            },
            {
              title: "Unattributed outcomes",
              tone: "other",
              byCurrency: report.revenue.unattributed_outcome_value_by_currency,
              note: "Real revenue this system does not claim to have caused. Shown so the figure beside it has a denominator.",
            },
          ]} />

          <div className="space-y-3">
            <StatStrip items={[
              { label: "Cases detected", value: report.cases.detected, detail: `${report.cases.not_yet_worked} not yet worked` },
              { label: "Cases worked", value: report.cases.worked, detail: `${report.cases.awaiting_approval} awaiting approval` },
              { label: "Messages sent", value: report.messages.actually_sent, detail: `of ${report.messages.drafted} drafted` },
              { label: "Replies received", value: report.messages.replies_received },
            ]} />
            <StatStrip items={[
              { label: "Outcome unknown", value: report.messages.outcome_unknown, detail: "Never counted as sent" },
              { label: "Blocked or failed", value: report.messages.blocked_or_failed, detail: "Proven not sent" },
              {
                label: "Median time to recovery",
                value: report.time_to_recovery.median_days != null ? `${report.time_to_recovery.median_days} days` : "—",
                detail: report.time_to_recovery.measured_entries ? `over ${report.time_to_recovery.measured_entries} recovered case(s)` : "Not measurable yet",
              },
              { label: "Cases recovered", value: report.cases.recovered ?? "—", tone: report.cases.recovered ? "success" : undefined },
            ]} />
          </div>

          <Section title={<>Cases {cases?.length ? <span className="tabular ml-1 font-normal text-muted-foreground">{cases.length}</span> : null}</>}>
            {cases && cases.length > 0 ? (
              <div className="overflow-hidden rounded-xl border border-border bg-card">
                <div className={cx("hidden h-9 items-center gap-4 border-b border-border bg-muted/40 px-4 text-xs font-medium text-muted-foreground sm:grid", caseColumns)} aria-hidden="true">
                  <span>Case</span><span>State</span><span className="hidden lg:block">Source</span>
                  <span className="text-right">Potential</span><span className="text-right">Confirmed</span>
                </div>
                {cases.map((item) => {
                  const confirmed = item.confirmed_value != null
                    ? money(item.confirmed_value, item.confirmed_currency || item.confirmed_value_evidence?.outcome?.currency || item.currency) : null;
                  const potential = item.potential_value != null ? money(item.potential_value, item.currency) : null;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setSelected(item.id)}
                      className={cx("grid w-full items-center gap-x-4 gap-y-1 border-b border-border/70 px-4 py-2.5 text-left text-[13px] transition-colors last:border-0 hover:bg-muted/50 focus-visible:bg-muted/50", caseColumns)}
                      data-testid={`proof-case-row-${item.id}`}
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-medium text-foreground">{item.title || item.reason}</span>
                        <span className="block truncate text-xs text-muted-foreground">{item.reason}</span>
                        <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs sm:hidden">
                          <StatusDot tone={STATE_TONE[item.state]} className="text-xs">{stateLabel(item.state)}</StatusDot>
                          <span className="text-muted-foreground">{sourceLabel(item.source)}</span>
                          {item.close_reason ? <span className="text-muted-foreground">Closed: {closeLabel(item.close_reason)}</span> : null}
                        </span>
                        <span className="tabular mt-1 flex gap-4 text-xs text-muted-foreground sm:hidden">
                          <span>potential <span className="font-medium text-foreground/80">{potential || "—"}</span></span>
                          <span>confirmed <span className={cx("font-medium", confirmed ? "text-emerald-700" : "")}>{confirmed || "—"}</span></span>
                        </span>
                      </span>
                      <span className="hidden min-w-0 text-[13px] sm:block">
                        <StatusDot tone={STATE_TONE[item.state]}>{stateLabel(item.state)}</StatusDot>
                        {item.close_reason ? <span className="text-muted-foreground"> · {closeLabel(item.close_reason)}</span> : null}
                      </span>
                      <span className="hidden truncate text-muted-foreground lg:block">{sourceLabel(item.source)}</span>
                      <span className={cx("tabular hidden text-right sm:block", potential ? "text-foreground/80" : "text-muted-foreground")}>{potential || "—"}</span>
                      <span className={cx("tabular hidden text-right sm:block", confirmed ? "font-medium text-emerald-700" : "text-muted-foreground")}>{confirmed || "—"}</span>
                    </button>
                  );
                })}
              </div>
            ) : (
              <SurfaceEmpty
                icon={FileSearch}
                title="No recovery cases yet"
                description="Cases appear here once the detectors run. An empty report is the honest state, not a rendering problem."
                testid="proof-empty"
              />
            )}
          </Section>
        </div>
      )}
    </div>
  );
}
