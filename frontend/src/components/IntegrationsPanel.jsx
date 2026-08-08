import { useEffect, useState, useCallback } from "react";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Mail, Calendar, CreditCard, RefreshCw, Plug, Unplug, AlertTriangle, CheckCircle2, Clock } from "lucide-react";

const META = {
  gmail: { label: "Gmail", icon: Mail, desc: "Read-only message + thread metadata, matched to CRM contacts.", kind: "google" },
  google_calendar: { label: "Google Calendar", icon: Calendar, desc: "Upcoming client meetings with attendee matching.", kind: "google" },
  stripe: { label: "Stripe", icon: CreditCard, desc: "Read-only customers, invoices & subscriptions.", kind: "stripe" },
};
const STATUS = {
  disconnected: { c: "bg-slate-50 text-slate-500 border-slate-200", t: "Not connected" },
  connecting: { c: "bg-blue-50 text-blue-600 border-blue-200", t: "Connecting…" },
  active: { c: "bg-emerald-50 text-emerald-700 border-emerald-200", t: "Connected" },
  degraded: { c: "bg-amber-50 text-amber-700 border-amber-200", t: "Degraded" },
  expired: { c: "bg-orange-50 text-orange-700 border-orange-200", t: "Token expired" },
  revoked: { c: "bg-red-50 text-red-700 border-red-200", t: "Authorization revoked" },
  error: { c: "bg-red-50 text-red-700 border-red-200", t: "Error" },
};

function stale(conn) {
  if (!conn.last_success_at) return false;
  return Date.now() - new Date(conn.last_success_at).getTime() > 24 * 3600 * 1000;
}

export default function IntegrationsPanel() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [conns, setConns] = useState(null);
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    try { const { data } = await api.get("/integrations/connections"); setConns(data); }
    catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
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

  if (!conns) return <div className="text-sm text-gray-400 py-6" data-testid="integrations-loading">Loading connections…</div>;

  return (
    <div className="space-y-4" data-testid="integrations-panel">
      {conns.map((c) => {
        const m = META[c.provider]; const st = STATUS[c.status] || STATUS.disconnected;
        const needsReconnect = ["expired", "revoked", "error"].includes(c.status);
        return (
          <div key={c.provider} className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm" data-testid={`integration-${c.provider}`}>
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-lg bg-gray-50 border border-gray-200 flex items-center justify-center"><m.icon className="w-4 h-4 text-gray-700" /></div>
                <div>
                  <div className="font-display font-bold text-base flex items-center gap-2">{m.label}
                    <Badge className={st.c} data-testid={`integration-status-${c.provider}`}>{st.t}</Badge>
                    {stale(c) && c.status === "active" && <Badge className="bg-yellow-50 text-yellow-700 border-yellow-200"><Clock className="w-3 h-3 mr-1" />Stale</Badge>}
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">{m.desc}</div>
                  {c.account_identity && <div className="text-xs text-gray-400 mt-1">Account: <span className="font-mono">{c.account_identity}</span></div>}
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {(c.scopes || []).slice(0, 4).map((s, i) => <span key={i} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-50 border border-gray-200 text-gray-500">{s.replace("https://www.googleapis.com/auth/", "")}</span>)}
                  </div>
                </div>
              </div>
              <div className="flex flex-col items-end gap-2 shrink-0">
                {isAdmin ? (
                  <div className="flex gap-2">
                    {c.status === "disconnected" ? (
                      <Button size="sm" className="h-8 bg-[#0A0A0A]" disabled={busy === c.provider} onClick={() => connect(c.provider)} data-testid={`connect-${c.provider}`}><Plug className="w-3.5 h-3.5 mr-1" />Connect</Button>
                    ) : (
                      <>
                        {needsReconnect && <Button size="sm" className="h-8 bg-orange-600 hover:bg-orange-700" disabled={busy === c.provider} onClick={() => connect(c.provider)} data-testid={`reconnect-${c.provider}`}>Reconnect</Button>}
                        <Button size="sm" variant="outline" className="h-8" disabled={busy === c.provider} onClick={() => sync(c.provider)} data-testid={`sync-${c.provider}`}><RefreshCw className={`w-3.5 h-3.5 mr-1 ${busy === c.provider ? "animate-spin" : ""}`} />Sync</Button>
                        <Button size="sm" variant="outline" className="h-8" disabled={busy === c.provider} onClick={() => disconnect(c.provider)} data-testid={`disconnect-${c.provider}`}><Unplug className="w-3.5 h-3.5 mr-1" />Disconnect</Button>
                      </>
                    )}
                  </div>
                ) : <Badge className="bg-slate-50 text-slate-500 border-slate-200">Admin manages</Badge>}
                <div className="text-[11px] text-gray-400 text-right">
                  {c.last_success_at ? <span className="flex items-center gap-1 justify-end"><CheckCircle2 className="w-3 h-3 text-emerald-500" />Last sync {new Date(c.last_success_at).toLocaleString()}</span> : <span>No successful sync yet</span>}
                </div>
              </div>
            </div>
            {c.last_error && <div className="mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 flex items-center gap-2" data-testid={`integration-error-${c.provider}`}><AlertTriangle className="w-3.5 h-3.5" />{c.last_error}</div>}
          </div>
        );
      })}
      {!conns.some((c) => c.status === "active") && (
        <div className="text-xs text-gray-400 flex items-center gap-1.5"><Plug className="w-3.5 h-3.5" />Connect a provider to surface live client email, meetings and billing inside workspaces.</div>
      )}
    </div>
  );
}
