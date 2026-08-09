import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Bell, Activity, Check, X, RefreshCw, Plug } from "lucide-react";

const SEV = { info: "bg-slate-50 text-slate-600 border-slate-200", warning: "bg-amber-50 text-amber-700 border-amber-200", critical: "bg-red-50 text-red-700 border-red-200" };
const CONN = { active: "bg-emerald-50 text-emerald-700 border-emerald-200", degraded: "bg-amber-50 text-amber-700 border-amber-200", expired: "bg-orange-50 text-orange-700 border-orange-200", revoked: "bg-red-50 text-red-700 border-red-200", error: "bg-red-50 text-red-700 border-red-200", disconnected: "bg-slate-50 text-slate-500 border-slate-200", connecting: "bg-blue-50 text-blue-600 border-blue-200" };

export default function CommandCenterInsights() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const navigate = useNavigate();
  const [alerts, setAlerts] = useState(null);
  const [health, setHealth] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const a = await api.get("/alerts", { params: { status: "open" } });
      setAlerts(a.data);
      if (isAdmin) { const h = await api.get("/integrations/health"); setHealth(h.data.providers); }
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
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

  if (!alerts) return null;
  const open = alerts.alerts || [];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-6" data-testid="command-center-insights">
      <div className="lg:col-span-7 bg-white border border-gray-200 rounded-xl p-6 shadow-sm" data-testid="cc-alerts">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="font-display font-bold text-lg flex items-center gap-2"><Bell className="w-4 h-4" />Operational Alerts</h3>
            <p className="text-xs text-gray-400">Deduplicated across integrations, commitments & health · {alerts.counts.open} open</p>
          </div>
          <Button size="sm" variant="outline" className="h-8" onClick={evaluate} disabled={busy} data-testid="evaluate-alerts"><RefreshCw className={`w-3.5 h-3.5 mr-1 ${busy ? "animate-spin" : ""}`} />Scan now</Button>
        </div>
        {open.length === 0 ? (
          <div className="text-sm text-gray-400 py-6 text-center" data-testid="cc-alerts-empty">No open alerts. All clear.</div>
        ) : (
          <div className="space-y-2 max-h-72 overflow-auto">
            {open.slice(0, 10).map((a) => (
              <div key={a.id} className="flex items-center justify-between p-2.5 rounded-lg border border-gray-100 hover:bg-gray-50" data-testid={`cc-alert-${a.id}`}>
                <button className="flex items-center gap-2 text-left" onClick={() => a.workspace_id && navigate(`/workspaces/${a.workspace_id}`)}>
                  <Badge className={SEV[a.severity]}>{a.severity}</Badge>
                  <div>
                    <div className="text-sm font-medium">{a.summary}</div>
                    <div className="text-[11px] text-gray-400">{a.type} · {a.occurrence_count}×</div>
                  </div>
                </button>
                <div className="flex gap-1.5 shrink-0">
                  {a.status === "open" && <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => act(a.id, "acknowledge")} data-testid={`cc-ack-${a.id}`}><Check className="w-3 h-3" /></Button>}
                  <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => act(a.id, "resolve")} data-testid={`cc-resolve-${a.id}`}><X className="w-3 h-3" /></Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="lg:col-span-5 bg-white border border-gray-200 rounded-xl p-6 shadow-sm" data-testid="cc-connection-health">
        <h3 className="font-display font-bold text-lg flex items-center gap-2 mb-1"><Activity className="w-4 h-4" />Connection Health</h3>
        <p className="text-xs text-gray-400 mb-4">Provider sync status across your tenant</p>
        {!isAdmin ? (
          <div className="text-sm text-gray-400 py-6 text-center" data-testid="cc-health-admin-only">Connection health is visible to admins.</div>
        ) : !health ? (
          <div className="text-sm text-gray-400 py-6 text-center">Loading…</div>
        ) : (
          <div className="space-y-2">
            {health.map((p) => (
              <div key={p.provider} className="flex items-center justify-between p-2.5 rounded-lg border border-gray-100" data-testid={`cc-provider-${p.provider}`}>
                <div className="flex items-center gap-2">
                  <Plug className="w-3.5 h-3.5 text-gray-400" />
                  <span className="text-sm font-medium capitalize">{p.provider.replace("_", " ")}</span>
                </div>
                <div className="flex items-center gap-2">
                  {p.reconnect_required && <Badge className="bg-orange-50 text-orange-700 border-orange-200 text-[10px]">Reconnect</Badge>}
                  {p.stale && <Badge className="bg-yellow-50 text-yellow-700 border-yellow-200 text-[10px]">Stale</Badge>}
                  <span className="text-[11px] text-gray-400">{p.sync_age_hours != null ? `${p.sync_age_hours}h ago` : "never"}</span>
                  <Badge className={CONN[p.status]}>{p.status}</Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
