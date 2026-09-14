import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { SurfaceEmpty, SurfaceError, SurfaceLoading } from "@/components/SurfaceState";
import { Skeleton } from "@/components/ui/skeleton";
import { Bell, Activity, Check, X, RefreshCw, Plug } from "lucide-react";

const SEV = { info: "bg-slate-50 text-slate-600 border-slate-200", warning: "bg-amber-50 text-amber-700 border-amber-200", critical: "bg-red-50 text-red-700 border-red-200" };
const CONN = { active: "bg-emerald-50 text-emerald-700 border-emerald-200", degraded: "bg-amber-50 text-amber-700 border-amber-200", expired: "bg-orange-50 text-orange-700 border-orange-200", revoked: "bg-red-50 text-red-700 border-red-200", error: "bg-red-50 text-red-700 border-red-200", disconnected: "bg-slate-50 text-slate-500 border-slate-200", connecting: "bg-blue-50 text-blue-600 border-blue-200" };
const CONN_LABEL = { active: "Connected", degraded: "Degraded", expired: "Needs auth", revoked: "Needs auth", error: "Error", disconnected: "Not connected", connecting: "Connecting…" };

function groupAlerts(alerts) {
  const groups = new Map();
  for (const alert of alerts) {
    const family = alert.family || alert.type || "general";
    const workspaceKey = alert.workspace_id || "tenant";
    const key = `${family}::${workspaceKey}`;
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        family,
        workspace_id: alert.workspace_id || null,
        workspace_label: alert.workspace_name || (alert.workspace_id ? `Workspace ${String(alert.workspace_id).slice(0, 8)}` : "Tenant-wide"),
        severity: alert.severity,
        count: 0,
        occurrence_count: 0,
        latest: alert,
        alerts: [],
      });
    }
    const group = groups.get(key);
    group.count += 1;
    group.occurrence_count += alert.occurrence_count || 1;
    group.alerts.push(alert);
    const rank = { critical: 3, warning: 2, info: 1 };
    if ((rank[alert.severity] || 0) >= (rank[group.severity] || 0)) {
      group.severity = alert.severity;
      group.latest = alert;
    }
  }
  return [...groups.values()].sort((a, b) => {
    const rank = { critical: 3, warning: 2, info: 1 };
    return (rank[b.severity] || 0) - (rank[a.severity] || 0) || b.occurrence_count - a.occurrence_count;
  });
}

export default function CommandCenterInsights() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const navigate = useNavigate();
  const [alerts, setAlerts] = useState(null);
  const [health, setHealth] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState("");

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const a = await api.get("/alerts", { params: { status: "open" } });
      setAlerts(a.data);
      if (isAdmin) {
        try {
          const h = await api.get("/integrations/health");
          setHealth(h.data.providers);
        } catch {
          setHealth([]);
        }
      }
    } catch (e) {
      const message = formatErr(e.response?.data?.detail) || "Could not load command-center insights.";
      setLoadError(message);
      setAlerts(null);
      toast.error(message);
    }
  }, [isAdmin]);
  useEffect(() => { load(); }, [load]);

  const evaluate = async () => {
    setBusy(true);
    try { const { data } = await api.post("/alerts/evaluate"); toast.success(`Alert scan complete (${data.created} new)`); load(); }
    catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  const act = async (id, action) => {
    try { await api.post(`/alerts/${id}/${action}`); load(); }
    catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  };

  if (loadError) {
    return <SurfaceError title="Insights unavailable" description={loadError} onRetry={load} testid="cc-insights-error" />;
  }
  if (!alerts) return <SurfaceLoading rows={2} testid="cc-insights-loading" />;
  const open = alerts.alerts || [];
  const groups = groupAlerts(open);

  return (
    <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-12" data-testid="command-center-insights">
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm lg:col-span-7" data-testid="cc-alerts">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h3 className="font-display flex items-center gap-2 text-lg font-bold"><Bell className="h-4 w-4" />Operational Alerts</h3>
            <p className="text-xs text-gray-400">Grouped by family & workspace · {alerts.counts?.open ?? open.length} open</p>
          </div>
          <Button size="sm" variant="outline" className="h-8" onClick={evaluate} disabled={busy} data-testid="evaluate-alerts"><RefreshCw className={`mr-1 h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} />Scan now</Button>
        </div>
        {groups.length === 0 ? (
          <SurfaceEmpty icon={Bell} title="No open alerts" description="Operational alerts appear here when integrations, commitments, or health checks need follow-through." testid="cc-alerts-empty" />
        ) : (
          <div className="max-h-80 space-y-3 overflow-auto">
            {groups.slice(0, 8).map((group) => (
              <div key={group.key} className="rounded-lg border border-gray-100 p-3 hover:bg-gray-50" data-testid={`cc-alert-group-${group.key}`}>
                <div className="flex items-start justify-between gap-3">
                  <button className="min-w-0 flex-1 text-left" onClick={() => group.workspace_id && navigate(`/workspaces/${group.workspace_id}`)}>
                    <div className="mb-1 flex flex-wrap items-center gap-1.5">
                      <Badge className={SEV[group.severity] || SEV.info}>{group.severity}</Badge>
                      <Badge className="border-slate-200 bg-slate-50 text-[10px] text-slate-600">{group.family}</Badge>
                      <span className="text-[11px] text-gray-400">{group.workspace_label}</span>
                      {group.count > 1 && <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">{group.count} linked</span>}
                    </div>
                    <div className="truncate text-sm font-medium">{group.latest.summary}</div>
                    <div className="text-[11px] text-gray-400">{group.occurrence_count}× occurrences</div>
                  </button>
                  <div className="flex shrink-0 gap-1.5">
                    {group.latest.status === "open" && <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => act(group.latest.id, "acknowledge")} data-testid={`cc-ack-${group.latest.id}`}><Check className="h-3 w-3" /></Button>}
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => act(group.latest.id, "resolve")} data-testid={`cc-resolve-${group.latest.id}`}><X className="h-3 w-3" /></Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="lg:col-span-5 bg-white border border-gray-200 rounded-xl p-6 shadow-sm" data-testid="cc-connection-health">
        <h3 className="font-display font-bold text-lg flex items-center gap-2 mb-1"><Activity className="w-4 h-4" />Connection Health</h3>
        <p className="text-xs text-gray-400 mb-4">API-backed connection status (connected / needs auth / error). Does not claim live Google or Stripe certification.</p>
        {!isAdmin ? (
          <div className="py-6 text-center text-sm text-gray-400" data-testid="cc-health-admin-only">Connection health is visible to admins.</div>
        ) : !health ? (
          <div className="space-y-2" data-testid="cc-health-loading">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-12 rounded-lg" />)}</div>
        ) : (
          <div className="space-y-2">
            {health.map((p) => (
              <div key={p.provider} className="flex items-center justify-between rounded-lg border border-gray-100 p-2.5" data-testid={`cc-provider-${p.provider}`}>
                <div className="flex items-center gap-2">
                  <Plug className="h-3.5 w-3.5 text-gray-400" />
                  <span className="text-sm font-medium capitalize">{p.provider.replace("_", " ")}</span>
                </div>
                <div className="flex items-center gap-2">
                  {p.reconnect_required && <Badge className="border-orange-200 bg-orange-50 text-[10px] text-orange-700">Reconnect</Badge>}
                  {p.stale && <Badge className="border-yellow-200 bg-yellow-50 text-[10px] text-yellow-700">Stale</Badge>}
                  <span className="text-[11px] text-gray-400">{p.sync_age_hours != null ? `${p.sync_age_hours}h ago` : "never"}</span>
                  <Badge className={CONN[p.status] || CONN.disconnected} data-testid={`cc-provider-status-${p.provider}`}>{CONN_LABEL[p.status] || p.status}</Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
