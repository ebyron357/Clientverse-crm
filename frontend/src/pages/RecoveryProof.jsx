import { useCallback, useEffect, useState } from "react";
import { api, formatErr, formatMoney } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { SurfaceEmpty, SurfaceError, SurfaceLoading } from "@/components/SurfaceState";
import { BadgeCheck, ChevronLeft, FileSearch, Mail, MailCheck, Reply, ShieldQuestion, Timer } from "lucide-react";

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
  strategy_rejected: "Strategy rejected",
  attribution_window_elapsed: "No outcome within the window",
};
const OPERATOR_CLOSE_REASONS = ["not_recoverable", "duplicate", "resolved", "spam", "no_longer_relevant"];
const closeLabel = (reason) => CLOSE_REASON_LABEL[reason] || reason;

const BASIS_LABEL = {
  reply_after_contact: "Client replied after we made contact",
  delivered_contact: "We reached the client; no reply",
  no_contact: "Nothing reached the client",
};

const BASIS_TONE = {
  reply_after_contact: "bg-emerald-50 text-emerald-700 border-emerald-200",
  delivered_contact: "bg-amber-50 text-amber-700 border-amber-200",
  no_contact: "bg-gray-100 text-gray-600 border-gray-200",
};

function CurrencyBlock({ title, note, byCurrency, tone, footnote }) {
  const entries = Object.entries(byCurrency || {});
  return (
    <div className={`rounded-xl border p-4 shadow-sm ${tone}`}>
      <div className="text-xs font-semibold uppercase tracking-[0.06em] opacity-70">{title}</div>
      {entries.length === 0 ? (
        <div className="font-display mt-2 text-2xl font-bold">—</div>
      ) : (
        <div className="mt-2 space-y-1">
          {entries.map(([currency, amount]) => (
            <div key={currency} className="font-display text-2xl font-bold">{money(amount, currency)}</div>
          ))}
        </div>
      )}
      <p className="mt-2 text-xs leading-5 opacity-80">{note}</p>
      {footnote ? <p className="mt-1 text-xs font-medium leading-5 opacity-90" data-testid="proof-potential-footnote">{footnote}</p> : null}
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
    <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-3" data-testid="proof-case-close">
      <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Close this case</div>
      <p className="mt-1 text-xs text-gray-500">
        Takes it out of open potential and withdraws anything still awaiting approval on it. The reason is shown on every report.
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <select
          className="h-9 rounded-md border border-gray-200 bg-white px-2 text-sm"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          aria-label="Reason for closing"
          data-testid="proof-case-close-reason"
        >
          {OPERATOR_CLOSE_REASONS.map((key) => <option key={key} value={key}>{closeLabel(key)}</option>)}
        </select>
        <input
          className="h-9 min-w-[200px] flex-1 rounded-md border border-gray-200 bg-white px-2 text-sm"
          value={note}
          maxLength={500}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Note (optional)"
          aria-label="Note"
        />
        <Button size="sm" variant="outline" onClick={close} disabled={busy} data-testid="proof-case-close-submit">
          {busy ? "Closing…" : "Close case"}
        </Button>
      </div>
      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
    </div>
  );
}

const OPEN_STATES = ["detected", "planned", "awaiting_approval", "approved", "executing", "engaged"];

function Counter({ icon: Icon, label, value, note }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.06em] text-gray-400">
        <Icon className="h-3.5 w-3.5" />{label}
      </div>
      <div className="font-display mt-2 text-2xl font-bold text-[#0a1628]">{value}</div>
      {note ? <p className="mt-1 text-xs text-gray-500">{note}</p> : null}
    </div>
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

  if (loadError) return <SurfaceError title="Case proof unavailable" description={String(loadError)} onRetry={load} testid="proof-case-error" />;
  if (!proof) return <SurfaceLoading rows={3} testid="proof-case-loading" />;

  const { communications: comms, value, attribution } = proof;

  return (
    <div data-testid="proof-case">
      <Button variant="outline" size="sm" className="mb-4" onClick={onBack} data-testid="proof-case-back">
        <ChevronLeft className="mr-1 h-4 w-4" />All cases
      </Button>

      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-display text-2xl font-bold text-[#0a1628]">{proof.case.title || "Recovery case"}</h2>
          <Badge className="bg-gray-100 text-gray-600 border-gray-200">{proof.case.state}</Badge>
          <Badge className="bg-slate-100 text-slate-600 border-slate-200">{proof.case.source}</Badge>
          {proof.case.close_reason ? (
            <Badge className="border-amber-200 bg-amber-50 text-amber-800" data-testid="proof-case-close-reason-badge">
              Closed: {closeLabel(proof.case.close_reason)}
            </Badge>
          ) : null}
        </div>
        {proof.case.close_reason ? (
          <p className="mt-2 text-xs text-gray-500">
            Closed {proof.case.closed_at ? new Date(proof.case.closed_at).toLocaleString() : ""}
            {proof.case.closed_by ? ` by ${proof.case.closed_by}` : ""}{proof.case.close_note ? ` — ${proof.case.close_note}` : ""}
          </p>
        ) : null}
        <dl className="mt-4 grid grid-cols-1 gap-4 text-sm md:grid-cols-3">
          <div><dt className="text-xs uppercase tracking-wide text-gray-400">Detected</dt><dd className="mt-1 text-gray-700">{proof.case.detected_at ? new Date(proof.case.detected_at).toLocaleString() : "—"}</dd></div>
          <div><dt className="text-xs uppercase tracking-wide text-gray-400">Owner</dt><dd className="mt-1 text-gray-700">{proof.case.owner || "Unassigned"}</dd></div>
          <div><dt className="text-xs uppercase tracking-wide text-gray-400">Source record</dt><dd className="mt-1 font-mono text-xs text-gray-600">{proof.source_record ? `${proof.source_record.collection}/${proof.source_record.id}` : proof.case.source_event_id || "—"}</dd></div>
          <div className="md:col-span-3"><dt className="text-xs uppercase tracking-wide text-gray-400">Why it was detected</dt><dd className="mt-1 leading-6 text-gray-700">{proof.case.reason_detected}</dd></div>
        </dl>
        {isAdmin && OPEN_STATES.includes(proof.case.state) ? (
          <CloseCaseControl caseId={caseId} onClosed={() => { load(); if (onChanged) onChanged(); }} />
        ) : null}
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
        <CurrencyBlock
          title="Potential value"
          tone="border-slate-200 bg-slate-50 text-slate-800"
          byCurrency={value.potential_value ? { [value.currency]: value.potential_value } : {}}
          note={`What this opportunity might be worth. An estimate, not revenue.${value.potential_value_basis ? ` Basis: ${value.potential_value_basis}.` : ""}`}
          footnote={value.potential_value_note ? `The source's value was not used: ${value.potential_value_note}.` : ""}
        />
        <CurrencyBlock
          title="Confirmed recovered"
          tone="border-emerald-200 bg-emerald-50 text-emerald-900"
          byCurrency={value.confirmed_recovered_value ? { [value.currency]: value.confirmed_recovered_value } : {}}
          note="Money a record says arrived. Never derived from the figure beside it."
        />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-4">
        <Counter icon={Mail} label="Messages drafted" value={comms.messages_drafted} />
        <Counter icon={MailCheck} label="Actually sent" value={comms.messages_actually_sent} note="Accepted by a provider" />
        <Counter icon={Reply} label="Replies" value={comms.replies_received} />
        <Counter icon={ShieldQuestion} label="Outcome unknown" value={comms.messages_outcome_unknown} note="Never counted as sent" />
      </div>

      <div className="mt-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h3 className="font-display text-lg font-bold text-[#0a1628]">Attribution</h3>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Badge className={BASIS_TONE[attribution.basis] || BASIS_TONE.no_contact}>
            {BASIS_LABEL[attribution.basis] || "No claim"}
          </Badge>
          {attribution.claimed ? <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">Claimed</Badge>
            : <Badge className="border-gray-200 bg-gray-100 text-gray-600">Not claimed</Badge>}
        </div>
        <p className="mt-3 text-sm leading-6 text-gray-600">{attribution.reason}</p>
        {attribution.evidence?.length > 0 && (
          <ul className="mt-4 space-y-2" data-testid="proof-attribution-evidence">
            {attribution.evidence.map((item) => (
              <li key={item.record_id} className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-xs">
                <span className="font-semibold text-gray-700">{item.kind.replace(/_/g, " ")}</span>
                <span className="ml-2 font-mono text-gray-500">{item.record_id}</span>
                {item.at ? <span className="ml-2 text-gray-400">{new Date(item.at).toLocaleString()}</span> : null}
                <div className="mt-1 text-gray-500">{item.detail}</div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {comms.outbound?.length > 0 && (
        <div className="mt-4 rounded-xl border border-gray-200 bg-white shadow-sm">
          <h3 className="font-display border-b border-gray-100 px-6 py-4 text-lg font-bold text-[#0a1628]">Messages</h3>
          <div className="divide-y divide-gray-100">
            {[...comms.outbound, ...comms.inbound].map((message) => (
              <div key={message.id} className="px-6 py-3" data-testid={`proof-message-${message.id}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className={message.direction === "inbound" ? "border-sky-200 bg-sky-50 text-sky-700" : "border-gray-200 bg-gray-100 text-gray-600"}>
                    {message.direction}
                  </Badge>
                  <Badge className="border-gray-200 bg-white text-gray-600">{message.status}</Badge>
                  <span className="text-xs text-gray-400">{message.sent_at || message.created_at ? new Date(message.sent_at || message.created_at).toLocaleString() : ""}</span>
                  {message.provider_message_id ? <span className="font-mono text-[10px] text-gray-300">{message.provider_message_id}</span> : null}
                </div>
                <p className="mt-1 line-clamp-2 text-sm text-gray-600">{message.body}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

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
    <div>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-bold">Recovery Proof</h1>
          <p className="mt-1 text-sm text-gray-500">
            What was recovered, and the records that say so. Potential value and confirmed recovered value are
            reported as separate figures and are never added together.
          </p>
          {recheck.note ? <p className="mt-1 text-xs text-gray-500" data-testid="proof-recheck-note">{recheck.note}</p> : null}
        </div>
        {isAdmin ? (
          <Button size="sm" variant="outline" onClick={recheckSources} disabled={recheck.busy} data-testid="proof-recheck">
            {recheck.busy ? "Re-checking…" : "Re-check sources"}
          </Button>
        ) : null}
      </div>

      {!report ? <SurfaceLoading rows={3} testid="proof-loading" /> : selected ? (
        <CaseProof caseId={selected} onBack={() => setSelected(null)} onChanged={load} />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3" data-testid="proof-revenue">
            <CurrencyBlock
              title="Open potential"
              tone="border-slate-200 bg-slate-50 text-slate-800"
              byCurrency={report.revenue.potential_value_open_by_currency}
              note="An estimate of what un-recovered cases might be worth, each opportunity counted once. Not revenue."
              footnote={openPotentialFootnote(report.revenue)}
            />
            <CurrencyBlock
              title="Attributed recovered"
              tone="border-emerald-200 bg-emerald-50 text-emerald-900"
              byCurrency={report.revenue.attributed_recovered_value_by_currency}
              note="Money a record says arrived, on cases where outreach demonstrably reached the client."
            />
            <CurrencyBlock
              title="Unattributed outcomes"
              tone="border-gray-200 bg-white text-gray-700"
              byCurrency={report.revenue.unattributed_outcome_value_by_currency}
              note="Real revenue this system does not claim to have caused. Shown so the figure beside it has a denominator."
            />
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-4">
            <Counter icon={FileSearch} label="Cases detected" value={report.cases.detected} note={`${report.cases.not_yet_worked} not yet worked`} />
            <Counter icon={BadgeCheck} label="Cases worked" value={report.cases.worked} note={`${report.cases.awaiting_approval} awaiting approval`} />
            <Counter icon={MailCheck} label="Messages sent" value={report.messages.actually_sent} note={`of ${report.messages.drafted} drafted`} />
            <Counter icon={Reply} label="Replies received" value={report.messages.replies_received} />
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
            <Counter icon={ShieldQuestion} label="Outcome unknown" value={report.messages.outcome_unknown} note="Dispatches nobody can confirm; never counted as sent" />
            <Counter icon={Mail} label="Blocked or failed" value={report.messages.blocked_or_failed} note="Proven not to have gone out" />
            <Counter
              icon={Timer}
              label="Median time to recovery"
              value={report.time_to_recovery.median_days != null ? `${report.time_to_recovery.median_days} days` : "—"}
              note={report.time_to_recovery.measured_entries ? `over ${report.time_to_recovery.measured_entries} recovered case(s)` : "Not measurable yet"}
            />
          </div>

          <div className="mt-6 rounded-xl border border-gray-200 bg-white shadow-sm">
            <h2 className="font-display border-b border-gray-100 px-6 py-4 text-lg font-bold text-[#0a1628]">Cases</h2>
            {cases && cases.length > 0 ? (
              <div className="divide-y divide-gray-100">
                {cases.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelected(item.id)}
                    className="flex w-full items-center gap-4 px-6 py-3.5 text-left hover:bg-gray-50"
                    data-testid={`proof-case-row-${item.id}`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="truncate text-sm font-semibold text-[#0a1628]">{item.title || item.reason}</span>
                        <Badge className="border-gray-200 bg-gray-100 text-gray-600">{item.state}</Badge>
                        <Badge className="border-slate-200 bg-slate-50 text-slate-600">{item.source}</Badge>
                        {item.close_reason ? <Badge className="border-amber-200 bg-amber-50 text-amber-800">{closeLabel(item.close_reason)}</Badge> : null}
                      </div>
                      <div className="mt-1 truncate text-xs text-gray-500">{item.reason}</div>
                    </div>
                    <div className="shrink-0 text-right text-xs">
                      <div className="text-gray-400">potential</div>
                      <div className="font-semibold text-gray-600">{item.potential_value != null ? money(item.potential_value, item.currency) : "—"}</div>
                    </div>
                    <div className="shrink-0 text-right text-xs">
                      <div className="text-gray-400">confirmed</div>
                      <div className="font-semibold text-emerald-700">{item.confirmed_value != null ? money(item.confirmed_value, item.currency) : "—"}</div>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="p-5">
                <SurfaceEmpty
                  icon={FileSearch}
                  title="No recovery cases yet"
                  description="Cases appear here once the detectors run. An empty report is the honest state, not a rendering problem."
                  testid="proof-empty"
                />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
