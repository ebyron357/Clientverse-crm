import { useEffect, useState, useCallback } from "react";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { StatusDot } from "@/components/page/Page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Activity, AlertTriangle, Bell, Calendar, Check, CheckSquare, ChevronLeft, ChevronRight, CreditCard, Handshake, History, Mail, Plug, Search, ShieldCheck, X } from "lucide-react";

const cx = (...parts) => parts.filter(Boolean).join(" ");
const SEV_TONE = { info: "neutral", warning: "warning", critical: "danger" };
const SEV_ICON = { info: "border-border bg-card text-muted-foreground", warning: "border-amber-200 bg-amber-50 text-amber-700", critical: "border-red-200 bg-red-50 text-red-700" };
const SOURCE_ICON = { gmail: Mail, email: Mail, calendar: Calendar, google_calendar: Calendar, stripe: CreditCard, commitment: Handshake, task: CheckSquare, approval: ShieldCheck, alert: Bell, integration: Plug, webhook: Plug };
const EXTERNAL = new Set(["gmail", "calendar", "stripe", "integration", "webhook"]);
const LIMIT = 20;
const when = (value) => value ? new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "—";
const Tag = ({ className, children, ...props }) => <span className={cx("rounded px-1.5 py-px text-[10px] font-medium", className)} {...props}>{children}</span>;

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

  if (!data) return <div className="py-6 text-[13px] text-muted-foreground" data-testid="timeline-loading">Loading timeline…</div>;

  const chip = (active) => cx("inline-flex h-7 items-center gap-1.5 rounded-md border px-2 text-xs transition-colors",
    active ? "border-input bg-muted font-medium text-foreground" : "border-border bg-card text-muted-foreground hover:text-foreground");

  return (
    <div className="space-y-6" data-testid="workspace-timeline">
      {alerts.length > 0 && (
        <section data-testid="workspace-alerts">
          <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-foreground"><Bell className="size-3.5 text-muted-foreground" aria-hidden="true" />Active alerts<span className="tabular rounded bg-muted px-1 text-xs font-medium text-muted-foreground">{alerts.length}</span></h3>
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            {alerts.map((a) => (
              <div key={a.id} className="flex flex-col gap-2 border-b border-border/70 px-4 py-2.5 last:border-0 sm:flex-row sm:items-center sm:justify-between" data-testid={`alert-${a.id}`}>
                <div className="flex min-w-0 items-start gap-2.5">
                  <StatusDot tone={SEV_TONE[a.severity]} className="mt-px w-[68px] shrink-0 capitalize">{a.severity}</StatusDot>
                  <div className="min-w-0">
                    <div className="text-[13px] font-medium text-foreground">{a.summary}</div>
                    <div className="text-xs text-muted-foreground">{a.type} · seen {a.occurrence_count}× · {a.status}</div>
                  </div>
                </div>
                <div className="flex shrink-0 gap-1.5 pl-[78px] sm:pl-0">
                  {a.status === "open" && <Button size="sm" variant="outline" className="h-7 px-2.5" onClick={() => act(a.id, "acknowledge")} data-testid={`ack-${a.id}`}><Check className="size-3.5" />Ack</Button>}
                  <Button size="sm" variant="outline" className="h-7 px-2.5" onClick={() => act(a.id, "resolve")} data-testid={`resolve-${a.id}`}><X className="size-3.5" />Resolve</Button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {signals.length > 0 && (
        <section data-testid="health-signals">
          <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-foreground"><AlertTriangle className="size-3.5 text-muted-foreground" aria-hidden="true" />Health signals</h3>
          <div className="flex flex-wrap gap-1.5">
            {signals.map((s, i) => (
              <span key={i} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-2 py-1 text-xs text-foreground/80" title={`${s.source_ref} · ${s.freshness || ""}`} data-testid={`signal-${i}`}>
                <span className={cx("size-1.5 shrink-0 rounded-full", s.severity === "critical" ? "bg-red-500" : s.severity === "warning" ? "bg-amber-500" : "bg-muted-foreground/50")} aria-hidden="true" />
                {s.signal}{s.detail ? <span className="text-muted-foreground">: {String(s.detail).slice(0, 28)}</span> : ""}
              </span>
            ))}
          </div>
        </section>
      )}

      <div className="space-y-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <div className="relative w-full sm:w-64">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input placeholder="Search timeline…" aria-label="Search timeline" value={q} onChange={(e) => { setOffset(0); setQ(e.target.value); }} className="h-8 pl-8 md:text-[13px]" data-testid="timeline-search" />
          </div>
          <div className="flex flex-wrap items-center gap-1.5" data-testid="timeline-source-filters">
            {(data.sources || []).map((s) => (
              <button key={s} type="button" onClick={() => toggle(setSrcFilter, srcFilter, s)} aria-pressed={srcFilter.has(s)} data-testid={`src-filter-${s}`} className={chip(srcFilter.has(s))}>{s}</button>
            ))}
            {(data.sources || []).length > 0 && <span className="mx-1 h-4 w-px bg-border" aria-hidden="true" />}
            {["info", "warning", "critical"].map((s) => (
              <button key={s} type="button" onClick={() => toggle(setSevFilter, sevFilter, s)} aria-pressed={sevFilter.has(s)} data-testid={`sev-filter-${s}`} className={cx(chip(sevFilter.has(s)), "capitalize")}>
                <span className={cx("size-1.5 rounded-full", s === "critical" ? "bg-red-500" : s === "warning" ? "bg-amber-500" : "bg-muted-foreground/50")} aria-hidden="true" />{s}
              </button>
            ))}
          </div>
        </div>

        {data.items.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border px-6 py-12 text-center" data-testid="timeline-empty">
            <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground"><History className="size-5" aria-hidden="true" /></span>
            <p className="mt-3 text-sm font-medium text-foreground">No events match these filters.</p>
            <p className="mt-1 text-[13px] text-muted-foreground">Clear a filter or search term to see more of the account history.</p>
          </div>
        ) : (
          <ol className="pt-1" data-testid="timeline-feed">
            {data.items.map((it, index) => {
              const Icon = SOURCE_ICON[it.source] || Activity;
              const last = index === data.items.length - 1;
              return (
                <li key={it.id} className="relative flex gap-3" data-testid={`timeline-item-${it.id}`}>
                  {!last && <span className="absolute bottom-0 left-3 top-7 w-px -translate-x-1/2 bg-border" aria-hidden="true" />}
                  <span className={cx("relative flex size-6 shrink-0 items-center justify-center rounded-full border", SEV_ICON[it.severity] || SEV_ICON.info)}><Icon className="size-3" aria-hidden="true" /></span>
                  <div className={cx("min-w-0 flex-1", last ? "pb-1" : "pb-5")}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 flex-wrap items-center gap-1.5 pt-0.5 text-[13px] font-medium text-foreground">
                        <span className="min-w-0">{it.title}</span>
                        {EXTERNAL.has(it.source) && <Tag className="bg-violet-50 text-violet-700" data-testid="timeline-external-badge">External</Tag>}
                        {it.stale && <Tag className="bg-amber-50 text-amber-700">Stale</Tag>}
                        {it.failure && <Tag className="bg-red-50 text-red-700">Failure</Tag>}
                      </div>
                      <time className="tabular shrink-0 pt-0.5 text-xs text-muted-foreground" dateTime={it.occurred_at || undefined} title={it.occurred_at ? new Date(it.occurred_at).toLocaleString() : undefined}>{when(it.occurred_at)}</time>
                    </div>
                    {it.summary && <div className="mt-0.5 line-clamp-2 text-[13px] text-muted-foreground">{it.summary}</div>}
                    <div className="mt-1 flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
                      <span>{it.source}</span>
                      <span aria-hidden="true">·</span><span>{it.actor || "system"}</span>
                      {it.ref?.id && <><span aria-hidden="true">·</span><span className="font-mono text-[11px]">{it.ref.type}:{String(it.ref.id).slice(0, 12)}</span></>}
                      {it.external_ref && <><span aria-hidden="true">·</span><span className="font-mono text-[11px]">ext:{String(it.external_ref).slice(0, 12)}</span></>}
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        )}

        <div className="flex items-center justify-between border-t border-border pt-3 text-xs text-muted-foreground">
          <span className="tabular" data-testid="timeline-total">{data.total} event(s)</span>
          <div className="flex gap-1.5">
            <Button size="sm" variant="outline" className="h-7 px-2" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))} data-testid="timeline-prev"><ChevronLeft className="size-3.5" />Prev</Button>
            <Button size="sm" variant="outline" className="h-7 px-2" disabled={offset + LIMIT >= data.total} onClick={() => setOffset(offset + LIMIT)} data-testid="timeline-next">Next<ChevronRight className="size-3.5" /></Button>
          </div>
        </div>
      </div>
    </div>
  );
}
