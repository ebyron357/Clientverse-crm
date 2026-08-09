import { useEffect, useState, useCallback } from "react";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AlertTriangle, Search, ChevronLeft, ChevronRight, Check, X, Bell } from "lucide-react";

const SEV = { info: "bg-slate-50 text-slate-600 border-slate-200", warning: "bg-amber-50 text-amber-700 border-amber-200", critical: "bg-red-50 text-red-700 border-red-200" };
const EXTERNAL = new Set(["gmail", "calendar", "stripe", "integration", "webhook"]);
const LIMIT = 20;

export default function WorkspaceTimeline({ workspaceId }) {
  const [data, setData] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [signals, setSignals] = useState([]);
  const [srcFilter, setSrcFilter] = useState(new Set());
  const [sevFilter, setSevFilter] = useState(new Set());
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);

  const load = useCallback(async () => {
    const params = { limit: LIMIT, offset };
    if (srcFilter.size) params.sources = [...srcFilter].join(",");
    if (sevFilter.size) params.severity = [...sevFilter].join(",");
    if (q.trim()) params.q = q.trim();
    try {
      const [t, a, s] = await Promise.all([
        api.get(`/workspaces/${workspaceId}/timeline`, { params }),
        api.get(`/alerts`, { params: { workspace_id: workspaceId } }),
        api.get(`/workspaces/${workspaceId}/health-signals`),
      ]);
      setData(t.data); setAlerts(a.data.alerts.filter((x) => x.status !== "resolved")); setSignals(s.data.signals);
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  }, [workspaceId, offset, srcFilter, sevFilter, q]);
  useEffect(() => { load(); }, [load]);

  const toggle = (setter, set, v) => { const n = new Set(set); n.has(v) ? n.delete(v) : n.add(v); setOffset(0); setter(n); };
  const act = async (id, action) => {
    try { await api.post(`/alerts/${id}/${action}`); toast.success(`Alert ${action}d`); load(); }
    catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  };

  if (!data) return <div className="text-sm text-gray-400 py-6" data-testid="timeline-loading">Loading timeline…</div>;

  return (
    <div className="space-y-6" data-testid="workspace-timeline">
      {alerts.length > 0 && (
        <div className="space-y-2" data-testid="workspace-alerts">
          <h3 className="font-display font-bold text-sm uppercase tracking-[0.06em] text-gray-500 flex items-center gap-2"><Bell className="w-4 h-4" />Active alerts</h3>
          {alerts.map((a) => (
            <div key={a.id} className="flex items-center justify-between bg-white border border-gray-200 rounded-lg p-3" data-testid={`alert-${a.id}`}>
              <div className="flex items-center gap-2">
                <Badge className={SEV[a.severity]}>{a.severity}</Badge>
                <div>
                  <div className="text-sm font-medium">{a.summary}</div>
                  <div className="text-[11px] text-gray-400">{a.type} · seen {a.occurrence_count}× · {a.status}</div>
                </div>
              </div>
              <div className="flex gap-1.5">
                {a.status === "open" && <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => act(a.id, "acknowledge")} data-testid={`ack-${a.id}`}><Check className="w-3 h-3 mr-1" />Ack</Button>}
                <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => act(a.id, "resolve")} data-testid={`resolve-${a.id}`}><X className="w-3 h-3 mr-1" />Resolve</Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {signals.length > 0 && (
        <div data-testid="health-signals">
          <h3 className="font-display font-bold text-sm uppercase tracking-[0.06em] text-gray-500 mb-2 flex items-center gap-2"><AlertTriangle className="w-4 h-4" />Health signals</h3>
          <div className="flex flex-wrap gap-2">
            {signals.map((s, i) => (
              <span key={i} className={`text-xs px-2 py-1 rounded border ${SEV[s.severity]}`} title={`${s.source_ref} · ${s.freshness || ""}`} data-testid={`signal-${i}`}>{s.signal}{s.detail ? `: ${String(s.detail).slice(0, 28)}` : ""}</span>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <Input placeholder="Search timeline…" value={q} onChange={(e) => { setOffset(0); setQ(e.target.value); }} className="pl-9 h-9" data-testid="timeline-search" />
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5" data-testid="timeline-source-filters">
          {(data.sources || []).map((s) => (
            <button key={s} onClick={() => toggle(setSrcFilter, srcFilter, s)} data-testid={`src-filter-${s}`}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${srcFilter.has(s) ? "bg-[#0A0A0A] text-white border-[#0A0A0A]" : "bg-white text-gray-600 border-gray-200 hover:border-gray-400"}`}>{s}</button>
          ))}
          <span className="w-px bg-gray-200 mx-1" />
          {["info", "warning", "critical"].map((s) => (
            <button key={s} onClick={() => toggle(setSevFilter, sevFilter, s)} data-testid={`sev-filter-${s}`}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors capitalize ${sevFilter.has(s) ? SEV[s].replace("bg-", "bg-").concat(" ring-1 ring-offset-1") : "bg-white text-gray-600 border-gray-200 hover:border-gray-400"}`}>{s}</button>
          ))}
        </div>
      </div>

      {/* Feed */}
      {data.items.length === 0 ? (
        <div className="text-sm text-gray-400 py-8 text-center border border-dashed border-gray-300 rounded-xl" data-testid="timeline-empty">No events match these filters.</div>
      ) : (
        <div className="relative pl-4" data-testid="timeline-feed">
          <div className="absolute left-1 top-2 bottom-2 w-px bg-gray-200" />
          {data.items.map((it) => (
            <div key={it.id} className="relative mb-4" data-testid={`timeline-item-${it.id}`}>
              <div className={`absolute -left-3.5 top-1.5 w-2.5 h-2.5 rounded-full border-2 border-white ${it.severity === "critical" ? "bg-red-500" : it.severity === "warning" ? "bg-amber-500" : "bg-gray-400"}`} />
              <div className="bg-white border border-gray-200 rounded-lg p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium flex items-center gap-2 flex-wrap">
                    {it.title}
                    {EXTERNAL.has(it.source) && <Badge className="bg-violet-50 text-violet-700 border-violet-200 text-[10px]" data-testid="timeline-external-badge">External</Badge>}
                    {it.stale && <Badge className="bg-yellow-50 text-yellow-700 border-yellow-200 text-[10px]">Stale</Badge>}
                    {it.failure && <Badge className="bg-red-50 text-red-700 border-red-200 text-[10px]">Failure</Badge>}
                  </div>
                  <span className="text-[11px] text-gray-400 shrink-0">{it.occurred_at ? new Date(it.occurred_at).toLocaleString() : "—"}</span>
                </div>
                {it.summary && <div className="text-xs text-gray-500 mt-1 line-clamp-2">{it.summary}</div>}
                <div className="text-[11px] text-gray-400 mt-1.5 flex items-center gap-2">
                  <span className="uppercase tracking-wide">{it.source}</span>
                  <span>·</span><span>{it.actor || "system"}</span>
                  {it.ref?.id && <><span>·</span><span className="font-mono">{it.ref.type}:{String(it.ref.id).slice(0, 12)}</span></>}
                  {it.external_ref && <><span>·</span><span className="font-mono">ext:{String(it.external_ref).slice(0, 12)}</span></>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span data-testid="timeline-total">{data.total} event(s)</span>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" className="h-8" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))} data-testid="timeline-prev"><ChevronLeft className="w-3.5 h-3.5" />Prev</Button>
          <Button size="sm" variant="outline" className="h-8" disabled={offset + LIMIT >= data.total} onClick={() => setOffset(offset + LIMIT)} data-testid="timeline-next">Next<ChevronRight className="w-3.5 h-3.5" /></Button>
        </div>
      </div>
    </div>
  );
}
