import { useCallback, useEffect, useState } from "react";
import { api, formatErr } from "@/lib/api";
import { Badge } from "@/components/AppShell";
import { SurfaceEmpty, SurfaceError, SurfaceLoading } from "@/components/SurfaceState";
import { Mail, Calendar, CreditCard, ExternalLink, AlertTriangle, Plug, MessageSquare } from "lucide-react";

const PROVIDER_LABEL = { gmail: "Gmail", google_calendar: "Calendar", stripe: "Stripe" };

function ExternalTag() {
  return <Badge className="bg-violet-50 text-violet-700 border-violet-200 text-[10px]" data-testid="external-source-tag">External</Badge>;
}

export default function WorkspaceActivity({ workspaceId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    setData(null);
    try {
      const res = await api.get(`/integrations/workspaces/${workspaceId}/activity`);
      setData(res.data);
    } catch (e) {
      setError(formatErr(e.response?.data?.detail) || "Could not load workspace activity.");
    }
  }, [workspaceId]);

  useEffect(() => { load(); }, [load]);

  if (error) {
    return <SurfaceError title="Client activity unavailable" description={error} onRetry={load} testid="activity-error" />;
  }
  if (!data) return <SurfaceLoading rows={2} testid="activity-loading" />;

  const anyActive = (data.connections || []).some((c) => c.status === "active");
  const failing = (data.connections || []).filter((c) => ["degraded", "expired", "revoked", "error"].includes(c.status));
  const { communications = [], meetings = [], billing = [] } = data;

  const allDisconnected = (data.connections || []).every((c) => c.status === "disconnected");

  if (!anyActive && allDisconnected) {
    return (
      <SurfaceEmpty
        icon={Plug}
        title="No integrations connected"
        description="Connect Gmail, Calendar, or Stripe from Registries → Integrations to surface matched client communications here. Empty state is intentional until a provider is connected."
        testid="activity-empty"
      />
    );
  }

  return (
    <div className="space-y-6" data-testid="workspace-activity">
      {!anyActive && failing.length > 0 && (
        <SurfaceEmpty
          icon={AlertTriangle}
          title="Connected providers need attention"
          description="Re-authorize or repair the listed connections before workspace activity can sync."
          testid="activity-connections-unavailable"
        />
      )}
      {failing.length > 0 && (
        <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 flex items-center gap-2" data-testid="activity-sync-warning">
          <AlertTriangle className="w-3.5 h-3.5" />Some connections need attention: {failing.map((f) => `${PROVIDER_LABEL[f.provider]} (${f.status === "expired" || f.status === "revoked" ? "needs auth" : f.status})`).join(", ")}
        </div>
      )}

      <section data-testid="activity-meetings">
        <h3 className="font-display font-bold text-sm uppercase tracking-[0.06em] text-gray-500 flex items-center gap-2 mb-3"><Calendar className="w-4 h-4" />Upcoming meetings</h3>
        {meetings.length === 0 ? (
          <p className="text-xs text-gray-500 rounded-lg border border-dashed border-gray-200 bg-slate-50/60 px-3 py-4" data-testid="activity-meetings-empty">No upcoming client meetings synced for this workspace.</p>
        ) : (
          <div className="space-y-2">
            {meetings.map((m) => (
              <div key={m.id} className="bg-white border border-gray-200 rounded-lg p-3 flex items-center justify-between" data-testid={`meeting-${m.id}`}>
                <div>
                  <div className="text-sm font-medium">{m.title} <ExternalTag /></div>
                  <div className="text-xs text-gray-400">{m.start ? new Date(m.start).toLocaleString() : "—"} · {(m.attendees || []).length} attendee(s)</div>
                </div>
                {m.conference_link && <a href={m.conference_link} target="_blank" rel="noreferrer" className="text-xs text-blue-600 flex items-center gap-1">Join <ExternalLink className="w-3 h-3" /></a>}
              </div>
            ))}
          </div>
        )}
      </section>

      <section data-testid="activity-billing">
        <h3 className="font-display font-bold text-sm uppercase tracking-[0.06em] text-gray-500 flex items-center gap-2 mb-3"><CreditCard className="w-4 h-4" />Billing & subscriptions</h3>
        {billing.length === 0 ? (
          <p className="text-xs text-gray-500 rounded-lg border border-dashed border-gray-200 bg-slate-50/60 px-3 py-4" data-testid="activity-billing-empty">No Stripe records matched to this client yet.</p>
        ) : (
          <div className="space-y-2">
            {billing.map((b) => (
              <div key={b.id} className="bg-white border border-gray-200 rounded-lg p-3 flex items-center justify-between" data-testid={`billing-${b.id}`}>
                <div>
                  <div className="text-sm font-medium capitalize">{b.type} <ExternalTag /></div>
                  <div className="text-xs text-gray-400 font-mono">{b.external_id}</div>
                </div>
                <div className="text-right">
                  {b.amount != null && <div className="text-sm font-semibold">{b.currency ? b.currency.toUpperCase() : ""} {b.amount}</div>}
                  <Badge className="bg-slate-50 text-slate-600 border-slate-200 capitalize text-[10px]">{b.payment_status || b.status}</Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section data-testid="activity-email">
        <h3 className="font-display font-bold text-sm uppercase tracking-[0.06em] text-gray-500 flex items-center gap-2 mb-3"><Mail className="w-4 h-4" />Recent email threads</h3>
        {communications.length === 0 ? (
          <p className="text-xs text-gray-500 rounded-lg border border-dashed border-gray-200 bg-slate-50/60 px-3 py-4" data-testid="activity-email-empty">No matched client email yet. Threads appear after a successful Gmail sync against CRM contacts.</p>
        ) : (
          <div className="space-y-2" data-testid="activity-email-threads">
            {communications.map((c) => (
              <div key={c.id} className="bg-white border border-gray-200 rounded-lg p-3" data-testid={`comm-${c.id}`}>
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-cyan-50 text-[#0a6177]"><MessageSquare className="h-3.5 w-3.5" /></span>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium flex items-center gap-2 flex-wrap">{c.subject || "(No subject)"} <ExternalTag /></div>
                    <div className="text-xs text-gray-400 mt-0.5">{c.from_email || "Unknown sender"} · {c.ts ? new Date(c.ts).toLocaleString() : "—"}{c.thread_id ? ` · thread ${String(c.thread_id).slice(0, 8)}` : ""}</div>
                    {c.snippet && <div className="text-xs text-gray-500 mt-1.5 line-clamp-2 leading-5">{c.snippet}</div>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
