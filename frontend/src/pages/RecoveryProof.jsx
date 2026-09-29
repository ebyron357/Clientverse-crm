import { useCallback, useEffect, useState } from "react";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
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

const money = (value, currency) =>
  new Intl.NumberFormat(undefined, { style: "currency", currency: currency || "USD", maximumFractionDigits: 0 }).format(value || 0);

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

function CurrencyBlock({ title, note, byCurrency, tone }) {
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
    </div>
  );
}

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

const OUTCOME_KINDS = [
  { value: "invoice_paid", label: "Invoice paid", record: "Invoice id" },
  { value: "deal_won", label: "Deal won", record: "Deal id" },
  { value: "operator_confirmed", label: "Confirmed by me", record: "Reference" },
];

/**
 * Record an outcome against a case. The form says what happened and points at the
 * record; it cannot say whether this system caused it. The server derives the claim,
 * its basis and the amount (from the invoice or deal itself) and returns its reasoning,
 * which is shown as-is — including when the answer is "not attributed".
 */
const LINK_FIELDS = [
  { field: "contact_id", label: "Contact", path: "/contacts" },
  { field: "company_id", label: "Company", path: "/companies" },
  { field: "opportunity_id", label: "Deal", path: "/opportunities" },
];

/** Name the client a case is about, where detection only had a number or an address.
 *  Links fill empty fields only; the server refuses to re-point one. */
function LinkCase({ caseId, links, onLinked }) {
  const missing = LINK_FIELDS.filter(({ field }) => !links?.[field]);
  const [options, setOptions] = useState({});
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.allSettled(missing.map(({ path }) => api.get(path))).then((results) => {
      if (!active) return;
      const next = {};
      results.forEach((result, index) => {
        next[missing[index].field] = result.status === "fulfilled" && Array.isArray(result.value.data)
          ? result.value.data : [];
      });
      setOptions(next);
    });
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, missing.length]);

  if (!missing.length) return null;
  const chosen = Object.fromEntries(Object.entries(form).filter(([, value]) => value));

  const submit = async () => {
    setBusy(true);
    try {
      await api.post(`/recovery-cases/${caseId}/link`, chosen);
      toast.success("Case linked");
      setForm({});
      onLinked();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || "The case could not be linked");
    } finally { setBusy(false); }
  };

  return (
    <div className="mt-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm" data-testid="link-case">
      <h3 className="font-display text-lg font-bold text-[#0a1628]">Who is this case about?</h3>
      <p className="mt-1 text-xs leading-5 text-gray-500">
        Link the case to its client so an invoice or deal booked on it can be checked against them. Without a
        link, a booked outcome is recorded on your word alone. A link can be added, not changed.
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        {missing.map(({ field, label }) => (
          <div key={field} className="text-[11px] text-gray-500">
            <label htmlFor={`link-${field}`}>{label}</label>
            <select id={`link-${field}`} data-testid={`link-${field}`}
                    className="mt-1 block h-9 w-56 rounded-md border border-gray-200 bg-white px-2 text-sm"
                    value={form[field] || ""} onChange={(e) => setForm({ ...form, [field]: e.target.value })}>
              <option value="">—</option>
              {(options[field] || []).slice(0, 500).map((record) => (
                <option key={record.id} value={record.id}>{record.name || record.email || record.id}</option>
              ))}
            </select>
          </div>
        ))}
        <Button className="h-9 cv-action-primary" disabled={busy || !Object.keys(chosen).length} onClick={submit}
                data-testid="link-case-submit">Link</Button>
      </div>
    </div>
  );
}

function RecordOutcome({ caseId, sourceRecord, onRecorded }) {
  const defaultDeal = sourceRecord?.collection === "opportunities" ? sourceRecord.id : "";
  const [form, setForm] = useState({ kind: "invoice_paid", record_id: "", amount: "", currency: "USD", note: "" });
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const kind = OUTCOME_KINDS.find((option) => option.value === form.kind);

  const submit = async () => {
    setBusy(true);
    setResult(null);
    try {
      const body = { case_id: caseId, kind: form.kind, record_id: form.record_id.trim(),
                     note: form.note || null };
      if (form.kind === "operator_confirmed") {
        body.amount = Number(form.amount);
        body.currency = form.currency || "USD";
      }
      const { data } = await api.post("/attribution/outcomes", body);
      setResult(data);
      toast.success(data.claim === "attributed" ? "Outcome recorded and attributed" : "Outcome recorded — not attributed");
      onRecorded();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || "The outcome could not be recorded");
    } finally { setBusy(false); }
  };

  return (
    <div className="mt-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm" data-testid="record-outcome">
      <h3 className="font-display text-lg font-bold text-[#0a1628]">Record an outcome</h3>
      <p className="mt-1 text-xs leading-5 text-gray-500">
        Point at the record that shows money arrived. Whether this recovery gets the credit is decided from the
        case&apos;s own messages, not from anything entered here.
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <div className="text-[11px] text-gray-500">
          <label htmlFor="outcome-kind">What happened</label>
          <select id="outcome-kind" data-testid="outcome-kind"
                  className="mt-1 block h-9 rounded-md border border-gray-200 bg-white px-2 text-sm"
                  value={form.kind}
                  onChange={(e) => setForm({ ...form, kind: e.target.value,
                                             record_id: e.target.value === "deal_won" ? defaultDeal : form.record_id })}>
            {OUTCOME_KINDS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </div>
        <div className="text-[11px] text-gray-500">
          <label htmlFor="outcome-record">{kind.record}</label>
          <Input id="outcome-record" data-testid="outcome-record" className="mt-1 h-9 w-56 font-mono text-xs"
                 value={form.record_id} onChange={(e) => setForm({ ...form, record_id: e.target.value })} />
        </div>
        {form.kind === "operator_confirmed" ? (
          <>
            <div className="text-[11px] text-gray-500">
              <label htmlFor="outcome-amount">Amount</label>
              <Input id="outcome-amount" data-testid="outcome-amount" type="number" min="0" step="0.01"
                     className="mt-1 h-9 w-32" value={form.amount}
                     onChange={(e) => setForm({ ...form, amount: e.target.value })} />
            </div>
            <div className="text-[11px] text-gray-500">
              <label htmlFor="outcome-currency">Currency</label>
              <Input id="outcome-currency" className="mt-1 h-9 w-20 uppercase" maxLength={3}
                     value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} />
            </div>
          </>
        ) : null}
        <div className="min-w-[12rem] flex-1 text-[11px] text-gray-500">
          <label htmlFor="outcome-note">Note (optional)</label>
          <Input id="outcome-note" className="mt-1 h-9" value={form.note}
                 onChange={(e) => setForm({ ...form, note: e.target.value })} />
        </div>
        <Button className="h-9 cv-action-primary" disabled={busy || !form.record_id.trim()
                  || (form.kind === "operator_confirmed" && !(Number(form.amount) > 0))}
                onClick={submit} data-testid="outcome-submit">Record</Button>
      </div>
      {result ? (
        <div className="mt-3 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-xs text-gray-600" data-testid="outcome-result">
          <span className="font-semibold">{result.claim === "attributed" ? "Attributed" : "Not attributed"}</span>
          {" — "}{result.reason}
          {result.case_updated === false && result.case_update_error ? (
            <div className="mt-1 text-amber-700">The case was not updated: {result.case_update_error}</div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function CaseProof({ caseId, onBack }) {
  const { user } = useAuth();
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
        </div>
        <dl className="mt-4 grid grid-cols-1 gap-4 text-sm md:grid-cols-3">
          <div><dt className="text-xs uppercase tracking-wide text-gray-400">Detected</dt><dd className="mt-1 text-gray-700">{proof.case.detected_at ? new Date(proof.case.detected_at).toLocaleString() : "—"}</dd></div>
          <div><dt className="text-xs uppercase tracking-wide text-gray-400">Owner</dt><dd className="mt-1 text-gray-700">{proof.case.owner || "Unassigned"}</dd></div>
          <div><dt className="text-xs uppercase tracking-wide text-gray-400">Source record</dt><dd className="mt-1 font-mono text-xs text-gray-600">{proof.source_record ? `${proof.source_record.collection}/${proof.source_record.id}` : proof.case.source_event_id || "—"}</dd></div>
          <div className="md:col-span-3"><dt className="text-xs uppercase tracking-wide text-gray-400">Why it was detected</dt><dd className="mt-1 leading-6 text-gray-700">{proof.case.reason_detected}</dd></div>
        </dl>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
        <CurrencyBlock
          title="Potential value"
          tone="border-slate-200 bg-slate-50 text-slate-800"
          byCurrency={value.potential_value ? { [value.currency]: value.potential_value } : {}}
          note="What this opportunity might be worth. An estimate, not revenue."
        />
        <CurrencyBlock
          title="Confirmed recovered"
          tone="border-emerald-200 bg-emerald-50 text-emerald-900"
          byCurrency={value.confirmed_recovered_value ? { [value.confirmed_currency || value.currency]: value.confirmed_recovered_value } : {}}
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

      {user?.role === "admin" && !proof.outcome.is_terminal ? (
        <>
          <LinkCase caseId={proof.case.id} links={proof.case.links} onLinked={load} />
          <RecordOutcome caseId={proof.case.id} sourceRecord={proof.source_record} onRecorded={load} />
        </>
      ) : null}

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

const BREAKDOWN_VIEWS = [
  { value: "lane", label: "By lane" },
  { value: "source", label: "By source" },
  { value: "period", label: "By month" },
];

function MoneyCell({ byCurrency, tone = "text-gray-700" }) {
  const entries = Object.entries(byCurrency || {});
  if (!entries.length) return <span className="text-gray-300">—</span>;
  return (
    <div className={`space-y-0.5 ${tone}`}>
      {entries.map(([currency, amount]) => <div key={currency}>{money(amount, currency)}</div>)}
    </div>
  );
}

function Breakdown() {
  const [view, setView] = useState("lane");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setError("");
    setData(null);
    api.get("/proof/breakdown", { params: { by: view, period: "month" } })
      .then(({ data: result }) => setData(result))
      .catch((e) => setError(e.response?.data?.detail || "The breakdown could not be loaded."));
  }, [view]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="mt-6 rounded-xl border border-gray-200 bg-white shadow-sm" data-testid="proof-breakdown">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 px-6 py-4">
        <h2 className="font-display text-lg font-bold text-[#0a1628]">Breakdown</h2>
        <div className="flex gap-1.5" role="group" aria-label="Breakdown view">
          {BREAKDOWN_VIEWS.map((option) => (
            <Button key={option.value} size="sm" variant={view === option.value ? "default" : "outline"}
                    className="h-7 text-xs" onClick={() => setView(option.value)}
                    data-testid={`breakdown-${option.value}`}>{option.label}</Button>
          ))}
        </div>
      </div>
      {error ? (
        <div className="p-5"><SurfaceError title="Breakdown unavailable" description={String(error)} onRetry={load} testid="breakdown-error" /></div>
      ) : !data ? (
        <div className="p-5"><SurfaceLoading rows={1} testid="breakdown-loading" /></div>
      ) : data.rows.length === 0 ? (
        <div className="p-5 text-sm text-gray-500">No cases yet.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-[11px] uppercase tracking-[0.06em] text-gray-400">
              <tr>
                <th className="px-6 py-2 font-semibold">{view === "period" ? "Month" : view === "source" ? "Source" : "Lane"}</th>
                <th className="px-3 py-2 font-semibold">Cases</th>
                <th className="px-3 py-2 font-semibold">Recovered</th>
                <th className="px-3 py-2 font-semibold">Attributed recovered</th>
                <th className="px-3 py-2 font-semibold">Unattributed outcomes</th>
                <th className="px-3 py-2 font-semibold">Open potential</th>
                <th className="px-3 py-2 font-semibold">Ended without recovery (potential)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.rows.map((row) => (
                <tr key={row.key} data-testid={`breakdown-row-${row.key}`}>
                  <td className="px-6 py-2.5 font-semibold text-[#0a1628]">{row.key.replace(/_/g, " ")}</td>
                  <td className="px-3 py-2.5 text-gray-600">{row.cases}</td>
                  <td className="px-3 py-2.5 text-gray-600">{row.recovered_cases}</td>
                  <td className="px-3 py-2.5 font-semibold"><MoneyCell byCurrency={row.attributed_recovered_value_by_currency} tone="text-emerald-700" /></td>
                  <td className="px-3 py-2.5"><MoneyCell byCurrency={row.unattributed_outcome_value_by_currency} /></td>
                  <td className="px-3 py-2.5"><MoneyCell byCurrency={row.open_potential_value_by_currency} tone="text-slate-500" /></td>
                  <td className="px-3 py-2.5"><MoneyCell byCurrency={row.ended_without_recovery_potential_by_currency} tone="text-slate-500" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="border-t border-gray-100 px-6 py-3 text-[11px] leading-5 text-gray-500">
        {data?.note}
        {view === "period" ? " Cases and potential are placed by the date the case was detected; recovered and unattributed revenue by the outcome's own date." : ""}
      </p>
    </div>
  );
}

export default function RecoveryProof() {
  const [report, setReport] = useState(null);
  const [cases, setCases] = useState(null);
  const [selected, setSelected] = useState(null);
  const [loadError, setLoadError] = useState("");

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

  if (loadError) {
    return <div className="cv-page"><SurfaceError title="Recovery report unavailable" description={String(loadError)} onRetry={load} testid="proof-error" /></div>;
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-display text-3xl font-bold">Recovery Proof</h1>
        <p className="mt-1 text-sm text-gray-500">
          What was recovered, and the records that say so. Potential value and confirmed recovered value are
          reported as separate figures and are never added together.
        </p>
      </div>

      {!report ? <SurfaceLoading rows={3} testid="proof-loading" /> : selected ? (
        <CaseProof caseId={selected} onBack={() => setSelected(null)} />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3" data-testid="proof-revenue">
            <CurrencyBlock
              title="Open potential"
              tone="border-slate-200 bg-slate-50 text-slate-800"
              byCurrency={report.revenue.potential_value_open_by_currency}
              note="An estimate of what un-recovered cases might be worth. Not revenue."
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

          <Breakdown />

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
                      </div>
                      <div className="mt-1 truncate text-xs text-gray-500">{item.reason}</div>
                    </div>
                    <div className="shrink-0 text-right text-xs">
                      <div className="text-gray-400">potential</div>
                      <div className="font-semibold text-gray-600">{item.potential_value != null ? money(item.potential_value, item.currency) : "—"}</div>
                    </div>
                    <div className="shrink-0 text-right text-xs">
                      <div className="text-gray-400">confirmed</div>
                      <div className="font-semibold text-emerald-700">{item.confirmed_value != null ? money(item.confirmed_value, item.confirmed_currency || item.currency) : "—"}</div>
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
