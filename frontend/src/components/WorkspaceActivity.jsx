import { useCallback, useEffect, useState } from "react";
import { api, formatErr } from "@/lib/api";
import { StatusDot } from "@/components/page/Page";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Mail, Calendar, CreditCard, ExternalLink, AlertTriangle, Plug, MessageSquare, CircleAlert, RefreshCw } from "lucide-react";

const PROVIDER_LABEL = { gmail: "Gmail", google_calendar: "Calendar", stripe: "Stripe" };
const when = (value) => value ? new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "—";
const PAYMENT_TONE = { paid: "success", succeeded: "success", active: "success", open: "info", pending: "warning", past_due: "danger", unpaid: "danger", failed: "danger", canceled: "neutral" };

function ExternalTag() {
  return <span className="rounded bg-violet-50 px-1.5 py-px text-[10px] font-medium text-violet-700" data-testid="external-source-tag">External</span>;
}

function Group({ icon: Icon, title, count, testid, children }) {
  return <section data-testid={testid}>
    <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-foreground">
      <Icon className="size-3.5 text-muted-foreground" aria-hidden="true" />{title}
      {count > 0 && <span className="tabular rounded bg-muted px-1 text-xs font-medium text-muted-foreground">{count}</span>}
    </h3>
    {children}
  </section>;
}

function EmptyLine({ testid, children }) {
  return <p className="rounded-xl border border-dashed border-border px-4 py-5 text-center text-[13px] text-muted-foreground" data-testid={testid}>{children}</p>;
}

function Centered({ icon: Icon, tone = "bg-muted text-muted-foreground", title, description, action, testid, role }) {
  return <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border px-6 py-12 text-center" data-testid={testid} role={role}>
    <span className={`flex size-10 items-center justify-center rounded-full ${tone}`}><Icon className="size-5" aria-hidden="true" /></span>
    <h2 className="mt-3 text-sm font-medium text-foreground">{title}</h2>
    {description && <p className="mt-1 max-w-md text-[13px] leading-5 text-muted-foreground">{description}</p>}
    {action}
  </div>;
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
    return <Centered icon={CircleAlert} tone="bg-red-50 text-red-600" title="Client activity unavailable" description={error} testid="activity-error" role="alert"
      action={<Button size="sm" variant="outline" onClick={load} className="mt-4" data-testid="activity-error-retry"><RefreshCw className="size-3.5" />Retry</Button>} />;
  }
  if (!data) return <div className="space-y-3" data-testid="activity-loading">{[0, 1].map((index) => <Skeleton key={index} className="h-20 rounded-xl" />)}</div>;

  const anyActive = (data.connections || []).some((c) => c.status === "active");
  const failing = (data.connections || []).filter((c) => ["degraded", "expired", "revoked", "error"].includes(c.status));
  const { communications = [], meetings = [], billing = [] } = data;

  const allDisconnected = (data.connections || []).every((c) => c.status === "disconnected");

  if (!anyActive && allDisconnected) {
    return <Centered icon={Plug} title="No integrations connected" testid="activity-empty"
      description="Connect Gmail, Calendar or Stripe in Registries → Integrations to see matched client communications here." />;
  }

  const failingList = failing.map((f) => `${PROVIDER_LABEL[f.provider]} (${f.status === "expired" || f.status === "revoked" ? "needs auth" : f.status})`).join(", ");
  const syncWarning = <span data-testid="activity-sync-warning">Some connections need attention: {failingList}</span>;

  return (
    <div className="space-y-6" data-testid="workspace-activity">
      {!anyActive && failing.length > 0 ? (
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800" role="status" data-testid="activity-connections-unavailable">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <div><span className="font-medium">Connected providers need attention.</span> Re-authorize or repair them before workspace activity can sync. <span className="block text-xs">{syncWarning}</span></div>
        </div>
      ) : failing.length > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800" role="status">
          <AlertTriangle className="size-3.5 shrink-0" aria-hidden="true" />{syncWarning}
        </div>
      )}

      <Group icon={Calendar} title="Upcoming meetings" count={meetings.length} testid="activity-meetings">
        {meetings.length === 0 ? (
          <EmptyLine testid="activity-meetings-empty">No upcoming client meetings synced for this workspace.</EmptyLine>
        ) : (
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            {meetings.map((m) => (
              <div key={m.id} className="flex items-center justify-between gap-3 border-b border-border/70 px-4 py-2.5 last:border-0" data-testid={`meeting-${m.id}`}>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5 text-[13px] font-medium text-foreground">{m.title} <ExternalTag /></div>
                  <div className="tabular text-xs text-muted-foreground">{m.start ? new Date(m.start).toLocaleString() : "—"} · {(m.attendees || []).length} attendee(s)</div>
                </div>
                {m.conference_link && <a href={m.conference_link} target="_blank" rel="noreferrer" className="flex shrink-0 items-center gap-1 text-xs font-medium text-brand hover:underline">Join <ExternalLink className="size-3" aria-hidden="true" /></a>}
              </div>
            ))}
          </div>
        )}
      </Group>

      <Group icon={CreditCard} title="Billing & subscriptions" count={billing.length} testid="activity-billing">
        {billing.length === 0 ? (
          <EmptyLine testid="activity-billing-empty">No Stripe records matched to this client yet.</EmptyLine>
        ) : (
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            {billing.map((b) => (
              <div key={b.id} className="flex items-center justify-between gap-3 border-b border-border/70 px-4 py-2.5 last:border-0" data-testid={`billing-${b.id}`}>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5 text-[13px] font-medium capitalize text-foreground">{b.type} <ExternalTag /></div>
                  <div className="truncate font-mono text-[11px] text-muted-foreground">{b.external_id}</div>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-0.5">
                  {b.amount != null && <div className="tabular text-[13px] font-semibold text-foreground">{b.currency ? b.currency.toUpperCase() : ""} {b.amount}</div>}
                  <StatusDot tone={PAYMENT_TONE[b.payment_status || b.status] || "neutral"} className="text-xs capitalize">{String(b.payment_status || b.status || "").replaceAll("_", " ")}</StatusDot>
                </div>
              </div>
            ))}
          </div>
        )}
      </Group>

      <Group icon={Mail} title="Recent email threads" count={communications.length} testid="activity-email">
        {communications.length === 0 ? (
          <EmptyLine testid="activity-email-empty">No matched client email yet. Threads appear after a successful Gmail sync against CRM contacts.</EmptyLine>
        ) : (
          <ol className="pt-1" data-testid="activity-email-threads">
            {communications.map((c, index) => {
              const last = index === communications.length - 1;
              return (
                <li key={c.id} className="relative flex gap-3" data-testid={`comm-${c.id}`}>
                  {!last && <span className="absolute bottom-0 left-3 top-7 w-px -translate-x-1/2 bg-border" aria-hidden="true" />}
                  <span className="relative flex size-6 shrink-0 items-center justify-center rounded-full border border-border bg-card text-muted-foreground"><MessageSquare className="size-3" aria-hidden="true" /></span>
                  <div className={`min-w-0 flex-1 ${last ? "pb-1" : "pb-5"}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 flex-wrap items-center gap-1.5 pt-0.5 text-[13px] font-medium text-foreground">{c.subject || "(No subject)"} <ExternalTag /></div>
                      <time className="tabular shrink-0 pt-0.5 text-xs text-muted-foreground" dateTime={c.ts || undefined}>{when(c.ts)}</time>
                    </div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{c.from_email || "Unknown sender"}{c.thread_id ? ` · thread ${String(c.thread_id).slice(0, 8)}` : ""}</div>
                    {c.snippet && <div className="mt-1 line-clamp-2 text-[13px] leading-5 text-muted-foreground">{c.snippet}</div>}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </Group>
    </div>
  );
}
