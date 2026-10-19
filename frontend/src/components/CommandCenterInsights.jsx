import { useEffect, useMemo, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Section, StatusDot } from "@/components/page/Page";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { BellOff, Check, CircleAlert, Lock, Plug, RefreshCw, X } from "lucide-react";

const SEV_DOT = { info: "bg-muted-foreground/50", warning: "bg-amber-500", critical: "bg-red-500" };
const CONN_TONE = { active: "success", degraded: "warning", expired: "warning", revoked: "danger", error: "danger", disconnected: "neutral", connecting: "info" };

const sentence = (value) => { const text = String(value || "").replace(/_/g, " "); return text.charAt(0).toUpperCase() + text.slice(1); };

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

/** Small count chip beside a section title. */
function Count({ children }) {
  return <span className="tabular rounded-md bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">{children}</span>;
}

/** Centred placeholder inside a panel. */
function PanelEmpty({ icon: Icon, title, children, testid }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-8 text-center" data-testid={testid}>
      <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground"><Icon className="size-[18px]" aria-hidden="true" /></span>
      <p className="mt-3 text-sm font-medium text-foreground">{title}</p>
      {children ? <p className="mt-1 max-w-xs text-[13px] leading-5 text-muted-foreground">{children}</p> : null}
    </div>
  );
}

/** `stacked` places the two panels one above the other on wide screens (a side rail). */
export default function CommandCenterInsights({ stacked = false }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const navigate = useNavigate();
  const [alerts, setAlerts] = useState(null);
  const [health, setHealth] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [healthError, setHealthError] = useState("");

  const load = useCallback(async () => {
    setError("");
    setHealthError("");
    try {
      const a = await api.get("/alerts", { params: { status: "open" } });
      setAlerts(a.data);
      if (isAdmin) {
        try {
          const h = await api.get("/integrations/health");
          setHealth(h.data.providers);
        } catch (e) {
          setHealth(null);
          setHealthError(formatErr(e.response?.data?.detail) || "Connection health could not be loaded.");
        }
      }
    } catch (e) {
      setError(formatErr(e.response?.data?.detail) || "Operational insights could not be loaded.");
      toast.error(formatErr(e.response?.data?.detail));
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

  const open = useMemo(() => alerts?.alerts || [], [alerts]);
  const groups = useMemo(() => groupAlerts(open), [open]);

  if (error) {
    return (
      <div className="rounded-xl border border-border bg-card" data-testid="command-center-insights-error" role="alert">
        <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
          <span className="flex size-10 items-center justify-center rounded-full bg-red-50 text-red-600"><CircleAlert className="size-[18px]" aria-hidden="true" /></span>
          <p className="mt-3 text-sm font-medium text-foreground">Insights unavailable</p>
          <p className="mt-1 max-w-md text-[13px] leading-5 text-muted-foreground">{error}</p>
          <Button size="sm" variant="outline" className="mt-4" onClick={load}><RefreshCw className="size-3.5" />Try again</Button>
        </div>
      </div>
    );
  }

  if (!alerts) {
    return (
      <div className={`grid grid-cols-1 gap-6 lg:grid-cols-2 ${stacked ? "xl:grid-cols-1" : ""}`} data-testid="command-center-insights-skeleton">
        <Skeleton className="h-56 rounded-xl" />
        <Skeleton className="h-56 rounded-xl" />
      </div>
    );
  }

  const openCount = alerts.counts?.open ?? open.length;

  return (
    <div className={`grid grid-cols-1 items-start gap-6 lg:grid-cols-2 ${stacked ? "xl:grid-cols-1" : ""}`} data-testid="command-center-insights">
      <Section testid="cc-alerts" className="min-w-0"
        title={<span className="flex items-center gap-2">Operational alerts<Count>{openCount}</Count></span>}
        actions={<Button size="sm" variant="outline" className="h-7 gap-1.5 px-2.5 text-xs [&_svg]:size-3.5" onClick={evaluate} disabled={busy} data-testid="evaluate-alerts">
          <RefreshCw className={busy ? "animate-spin" : ""} />Scan now
        </Button>}>
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          {groups.length === 0 ? (
            <PanelEmpty icon={BellOff} title="No open alerts" testid="cc-alerts-empty">All clear.</PanelEmpty>
          ) : (
            <div className="cv-scrollbar max-h-[22rem] overflow-auto">
              {groups.slice(0, 8).map((group) => (
                <div key={group.key} className="flex items-start gap-2 border-b border-border/70 px-4 py-2.5 transition-colors last:border-0 hover:bg-muted/50" data-testid={`cc-alert-group-${group.key}`}>
                  <button type="button" className="min-w-0 flex-1 rounded-md text-left" onClick={() => group.workspace_id && navigate(`/workspaces/${group.workspace_id}`)}>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium text-foreground">{group.latest.summary}</span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] leading-4 text-muted-foreground">
                        <span className="inline-flex items-center gap-1 font-medium text-foreground/80"><span className={`size-1.5 rounded-full ${SEV_DOT[group.severity] || SEV_DOT.info}`} aria-hidden="true" />{sentence(group.severity)}</span>
                        <span aria-hidden="true">·</span><span>{group.family}</span>
                        <span aria-hidden="true">·</span><span className="truncate">{group.workspace_label}</span>
                        {group.count > 1 && <><span aria-hidden="true">·</span><span>{group.count} linked</span></>}
                        <span aria-hidden="true">·</span><span className="tabular">{group.occurrence_count}× occurrences</span>
                      </span>
                    </span>
                  </button>
                  <div className="flex shrink-0 items-center gap-0.5">
                    {group.latest.status === "open" && <Button size="sm" variant="ghost" className="size-7 p-0 text-muted-foreground hover:text-foreground [&_svg]:size-3.5" onClick={() => act(group.latest.id, "acknowledge")}
                      aria-label="Acknowledge alert" title="Acknowledge" data-testid={`cc-ack-${group.latest.id}`}><Check /></Button>}
                    <Button size="sm" variant="ghost" className="size-7 p-0 text-muted-foreground hover:text-foreground [&_svg]:size-3.5" onClick={() => act(group.latest.id, "resolve")}
                      aria-label="Resolve alert" title="Resolve" data-testid={`cc-resolve-${group.latest.id}`}><X /></Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Section>

      <Section testid="cc-connection-health" className="min-w-0" title="Connection health">
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          {!isAdmin ? (
            <PanelEmpty icon={Lock} title="Admins only" testid="cc-health-admin-only">Connection health is visible to admins.</PanelEmpty>
          ) : healthError ? (
            <div className="m-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700" data-testid="cc-health-error">
              <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              <span>{healthError} <button type="button" className="ml-1 font-medium underline underline-offset-2" onClick={load}>Try again</button></span>
            </div>
          ) : !health ? (
            <div data-testid="cc-health-loading">{Array.from({ length: 3 }).map((_, i) => <div key={i} className={`flex items-center gap-3 px-4 py-3 ${i ? "border-t border-border/70" : ""}`}><Skeleton className="size-4 rounded" /><Skeleton className="h-3.5 w-32" /></div>)}</div>
          ) : (
            <>
              {health.map((p) => (
                <div key={p.provider} className="flex items-center gap-3 border-b border-border/70 px-4 py-2.5" data-testid={`cc-provider-${p.provider}`}>
                  <span className="flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-background text-muted-foreground"><Plug className="size-3.5" aria-hidden="true" /></span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-medium capitalize text-foreground">{p.provider.replace("_", " ")}</span>
                    <span className="block text-[11px] text-muted-foreground">Synced {p.sync_age_hours != null ? `${p.sync_age_hours}h ago` : "never"}</span>
                  </span>
                  {p.reconnect_required && <span className="rounded border border-orange-200 bg-orange-50 px-1.5 text-[10px] font-medium leading-4 text-orange-700">Reconnect</span>}
                  {p.stale && <span className="rounded border border-yellow-200 bg-yellow-50 px-1.5 text-[10px] font-medium leading-4 text-yellow-700">Stale</span>}
                  <span className="w-24 shrink-0"><StatusDot tone={CONN_TONE[p.status] || "neutral"}>{sentence(p.status)}</StatusDot></span>
                </div>
              ))}
              <p className="bg-muted/30 px-4 py-2 text-[11px] leading-4 text-muted-foreground">API-backed connection status. This does not claim live Google or Stripe certification.</p>
            </>
          )}
        </div>
      </Section>
    </div>
  );
}
