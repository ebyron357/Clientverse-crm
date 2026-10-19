import { useEffect, useState, useCallback } from "react";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { SurfaceError, SurfaceLoading } from "@/components/SurfaceState";
import { StatusDot } from "@/components/page/Page";
import { Mail, Calendar, CreditCard, RefreshCw, Plug, Unplug, AlertTriangle, Clock, ShieldAlert, Info } from "lucide-react";

const META = {
  gmail: { label: "Gmail", icon: Mail, desc: "Read-only message + thread metadata, matched to CRM contacts.", kind: "google" },
  google_calendar: { label: "Google Calendar", icon: Calendar, desc: "Upcoming client meetings with attendee matching.", kind: "google" },
  stripe: { label: "Stripe", icon: CreditCard, desc: "Read-only customers, invoices & subscriptions.", kind: "stripe" },
};

/** Honest operator-facing labels — does not imply live Google/Stripe certification. */
const STATUS = {
  disconnected: { dot: "neutral", t: "Not connected", tone: "idle" },
  connecting: { dot: "info", t: "Connecting…", tone: "pending" },
  active: { dot: "success", t: "Connected", tone: "ok" },
  degraded: { dot: "warning", t: "Degraded", tone: "warn" },
  expired: { dot: "warning", t: "Needs auth", tone: "auth" },
  revoked: { dot: "danger", t: "Needs auth", tone: "auth" },
  error: { dot: "danger", t: "Error", tone: "error" },
};

function stale(conn) {
  if (!conn.last_success_at) return false;
  return Date.now() - new Date(conn.last_success_at).getTime() > 24 * 3600 * 1000;
}

function Flag({ icon: Icon, children, className }) {
  return <span className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-px text-[11px] font-medium ${className}`}><Icon className="size-3" aria-hidden="true" />{children}</span>;
}

export default function IntegrationsPanel() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [conns, setConns] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const { data } = await api.get("/integrations/connections");
      setConns(data);
    } catch (e) {
      const message = formatErr(e.response?.data?.detail) || "Could not load provider connections.";
      setLoadError(message);
      setConns(null);
      toast.error(message);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("oauth");
    if (p === "connected") toast.success("Google connected");
    else if (p === "expired") toast.error("Authorization link expired — try again");
    else if (p === "error") toast.error("Google authorization failed");
    if (p) window.history.replaceState({}, "", window.location.pathname + "?tab=integrations");
  }, []);

  const connect = async (provider) => {
    setBusy(provider);
    try {
      if (META[provider].kind === "google") {
        const { data } = await api.post("/integrations/google/connect");
        window.location.href = data.authorization_url;
        return;
      }
      const { data } = await api.post(`/integrations/${provider}/connect`);
      toast.success(`Connected ${META[provider].label} (${data.account})`);
      load();
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
    finally { setBusy(""); }
  };
  const disconnect = async (provider) => {
    setBusy(provider);
    try { await api.post(`/integrations/${provider}/disconnect`); toast.success(`Disconnected ${META[provider].label}`); load(); }
    catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
    finally { setBusy(""); }
  };
  const sync = async (provider) => {
    setBusy(provider);
    try {
      const { data } = await api.post(`/integrations/${provider}/sync`);
      if (data.status === "completed") toast.success(`Synced ${META[provider].label}: ${data.matched} record(s) matched`);
      else toast.error(`Sync failed: ${data.error || "unknown"}`);
      load();
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
    finally { setBusy(""); }
  };

  if (loadError) {
    return <SurfaceError title="Integration center unavailable" description={loadError} onRetry={load} testid="integrations-error" />;
  }
  if (!conns) return <SurfaceLoading rows={3} testid="integrations-loading" />;

  const noneConnected = conns.length > 0 && conns.every((c) => c.status === "disconnected");
  return (
    <div className="space-y-3" data-testid="integrations-panel">
      <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-[13px] leading-5 text-muted-foreground" data-testid="integrations-honesty-banner">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span><span className="font-medium text-foreground">Status honesty:</span> rows reflect tenant connection state from the CRM API. They do not claim live Google or Stripe provider certification.</span>
      </div>
      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="divide-y divide-border/70">
          {conns.map((c) => {
            const m = META[c.provider]; const st = STATUS[c.status] || STATUS.disconnected;
            const needsReconnect = ["expired", "revoked", "error"].includes(c.status);
            const needsAuth = st.tone === "auth";
            const rowBusy = busy === c.provider;
            return (
              <div key={c.provider} className="px-4 py-3.5" data-testid={`integration-${c.provider}`}>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <div className="flex min-w-0 flex-1 items-start gap-3">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-muted text-foreground/80"><m.icon className="size-4" aria-hidden="true" /></span>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                        <span className="text-[13px] font-semibold text-foreground">{m.label}</span>
                        <span data-testid={`integration-status-${c.provider}`}><StatusDot tone={st.dot}>{st.t}</StatusDot></span>
                        {needsAuth && <Flag icon={ShieldAlert} className="border-orange-200 bg-orange-50 text-orange-700">Re-authorize</Flag>}
                        {stale(c) && c.status === "active" && <Flag icon={Clock} className="border-amber-200 bg-amber-50 text-amber-700">Stale</Flag>}
                      </div>
                      <p className="mt-0.5 text-[12.5px] leading-5 text-muted-foreground">{m.desc}</p>
                      {(c.account_identity || (c.scopes || []).length > 0 || c.last_success_at) && (
                        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                          {c.account_identity && <span className="font-mono text-[11.5px] text-foreground/80">{c.account_identity}</span>}
                          {(c.scopes || []).length > 0 && (
                            <span className="flex flex-wrap gap-1">
                              {(c.scopes || []).slice(0, 4).map((s, i) => <code key={i} className="rounded bg-muted px-1.5 py-px font-mono text-[10.5px] text-muted-foreground">{s.replace("https://www.googleapis.com/auth/", "")}</code>)}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-col items-start gap-1.5 pl-12 sm:items-end sm:pl-0">
                    {isAdmin ? (
                      <div className="flex flex-wrap gap-1.5">
                        {c.status === "disconnected" ? (
                          <Button size="sm" variant="outline" disabled={rowBusy} onClick={() => connect(c.provider)} data-testid={`connect-${c.provider}`}><Plug aria-hidden="true" />Connect</Button>
                        ) : (
                          <>
                            {needsReconnect && <Button size="sm" variant="outline" className="border-amber-200 text-amber-700 hover:bg-amber-50 hover:text-amber-700" disabled={rowBusy} onClick={() => connect(c.provider)} data-testid={`reconnect-${c.provider}`}>{needsAuth ? "Re-authorize" : "Reconnect"}</Button>}
                            <Button size="sm" variant="outline" disabled={rowBusy} onClick={() => sync(c.provider)} data-testid={`sync-${c.provider}`}><RefreshCw className={rowBusy ? "animate-spin" : ""} aria-hidden="true" />Sync</Button>
                            <Button size="sm" variant="ghost" className="text-muted-foreground" disabled={rowBusy} onClick={() => disconnect(c.provider)} data-testid={`disconnect-${c.provider}`}><Unplug aria-hidden="true" />Disconnect</Button>
                          </>
                        )}
                      </div>
                    ) : <span className="text-xs text-muted-foreground">Admin manages</span>}
                    <div className="tabular text-[11px] text-muted-foreground">
                      {c.last_success_at ? `Last sync ${new Date(c.last_success_at).toLocaleString()}` : "No successful sync yet"}
                    </div>
                  </div>
                </div>
                {c.last_error && <div className="ml-12 mt-2.5 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs text-red-700" data-testid={`integration-error-${c.provider}`}><AlertTriangle className="size-3.5 shrink-0" aria-hidden="true" />{c.last_error}</div>}
              </div>
            );
          })}
        </div>
        {noneConnected && (
          <div className="flex items-start gap-2 border-t border-border bg-muted/30 px-4 py-2.5 text-[12.5px] leading-5 text-muted-foreground" data-testid="integrations-none-connected">
            <Plug className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            <span><span className="font-medium text-foreground">No providers connected.</span> Connect Gmail, Calendar or Stripe to surface matched client email, meetings and billing inside workspaces. Live provider certification remains a separate owner-controlled gate.</span>
          </div>
        )}
      </div>
    </div>
  );
}
