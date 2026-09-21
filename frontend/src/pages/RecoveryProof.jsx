import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
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

function CaseProof({ caseId, onBack }) {
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
