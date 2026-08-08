import { useEffect, useState } from "react";
import { api, formatErr } from "@/lib/api";
import { Badge } from "@/components/AppShell";
import { Skeleton } from "@/components/ui/skeleton";
import { Mail, Calendar, CreditCard, ExternalLink, AlertTriangle } from "lucide-react";

const PROVIDER_LABEL = { gmail: "Gmail", google_calendar: "Calendar", stripe: "Stripe" };

function ExternalTag() {
  return <Badge className="bg-violet-50 text-violet-700 border-violet-200 text-[10px]" data-testid="external-source-tag">External</Badge>;
}

export default function WorkspaceActivity({ workspaceId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try { const res = await api.get(`/integrations/workspaces/${workspaceId}/activity`); setData(res.data); }
      catch (e) { setError(formatErr(e.response?.data?.detail)); }
    })();
  }, [workspaceId]);

  if (error) return <div className="text-sm text-red-600" data-testid="activity-error">{error}</div>;
  if (!data) return <div className="space-y-3"><Skeleton className="h-24 rounded-xl" /><Skeleton className="h-24 rounded-xl" /></div>;

  const anyActive = (data.connections || []).some((c) => c.status === "active");
  const failing = (data.connections || []).filter((c) => ["degraded", "expired", "revoked", "error"].includes(c.status));
  const { communications = [], meetings = [], billing = [] } = data;

  if (!anyActive) {
    return (
      <div className="bg-white border border-dashed border-gray-300 rounded-xl p-8 text-center" data-testid="activity-empty">
        <p className="text-sm font-medium text-gray-700">No integrations connected</p>
        <p className="text-xs text-gray-400 mt-1">Connect Gmail, Calendar or Stripe from Registries → Integrations to surface live client activity here.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="workspace-activity">
      {failing.length > 0 && (
        <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 flex items-center gap-2" data-testid="activity-sync-warning">
          <AlertTriangle className="w-3.5 h-3.5" />Some connections need attention: {failing.map((f) => `${PROVIDER_LABEL[f.provider]} (${f.status})`).join(", ")}
        </div>
      )}

      {/* Meetings */}
      <section data-testid="activity-meetings">
        <h3 className="font-display font-bold text-sm uppercase tracking-[0.06em] text-gray-500 flex items-center gap-2 mb-3"><Calendar className="w-4 h-4" />Upcoming meetings</h3>
        {meetings.length === 0 ? <p className="text-xs text-gray-400">No upcoming client meetings synced.</p> : (
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

      {/* Billing */}
      <section data-testid="activity-billing">
        <h3 className="font-display font-bold text-sm uppercase tracking-[0.06em] text-gray-500 flex items-center gap-2 mb-3"><CreditCard className="w-4 h-4" />Billing & subscriptions</h3>
        {billing.length === 0 ? <p className="text-xs text-gray-400">No Stripe records matched to this client.</p> : (
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

      {/* Email */}
      <section data-testid="activity-email">
        <h3 className="font-display font-bold text-sm uppercase tracking-[0.06em] text-gray-500 flex items-center gap-2 mb-3"><Mail className="w-4 h-4" />Recent email</h3>
        {communications.length === 0 ? <p className="text-xs text-gray-400">No client email matched yet.</p> : (
          <div className="space-y-2">
            {communications.map((c) => (
              <div key={c.id} className="bg-white border border-gray-200 rounded-lg p-3" data-testid={`comm-${c.id}`}>
                <div className="text-sm font-medium flex items-center gap-2">{c.subject} <ExternalTag /></div>
                <div className="text-xs text-gray-400">{c.from_email} · {c.ts ? new Date(c.ts).toLocaleString() : "—"}</div>
                {c.snippet && <div className="text-xs text-gray-500 mt-1 line-clamp-2">{c.snippet}</div>}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
