import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowRight, CheckCircle2, ChevronRight, CircleAlert, Clock, RefreshCw, X } from "lucide-react";

/**
 * Next Best Action queue, served by the backend recommendation service.
 *
 * Recommendations are not manufactured in the browser: the client renders what the
 * service derived, including the reason and the records it was derived from, so a
 * user can check the reasoning instead of trusting a number. Feedback (accept,
 * dismiss, complete, snooze) is persisted server-side.
 *
 * `compact` renders a ranked list in one bordered container (Command Center,
 * Operations); otherwise a sticky horizontal strip for a single workspace.
 */

const PRIORITY_BANDS = [
  { max: 10, label: "Critical", dot: "bg-red-500", text: "text-red-700" },
  { max: 30, label: "High", dot: "bg-amber-500", text: "text-amber-700" },
  { max: 50, label: "Medium", dot: "bg-brand", text: "text-brand" },
  { max: Infinity, label: "Low", dot: "bg-muted-foreground/50", text: "text-muted-foreground" },
];

function band(priority) {
  return PRIORITY_BANDS.find((entry) => priority <= entry.max) || PRIORITY_BANDS[PRIORITY_BANDS.length - 1];
}

function evidenceLine(recommendation) {
  const evidence = recommendation.evidence || {};
  const parts = [];
  if (evidence.due_at) parts.push(`due ${new Date(evidence.due_at).toLocaleDateString()}`);
  if (evidence.overdue_days != null) parts.push(`${evidence.overdue_days}d overdue`);
  if (evidence.idle_days != null) parts.push(`${evidence.idle_days}d idle`);
  if (evidence.owner) parts.push(`owner ${evidence.owner}`);
  if (evidence.status) parts.push(`status ${evidence.status}`);
  if (evidence.band) parts.push(`health ${String(evidence.band).replace("_", " ")}`);
  return parts.join(" · ");
}

const ACTION = "h-7 gap-1 px-2 text-xs [&_svg]:size-3.5";
const TEXT_ACTION = "h-7 gap-1 px-2 text-xs text-muted-foreground hover:text-foreground [&_svg]:size-3.5";
const ICON_ACTION = "size-7 p-0 text-muted-foreground hover:text-foreground [&_svg]:size-3.5";

function Recommendation({ item, busy, onFeedback, onNavigate, layout }) {
  const tone = band(item.priority);
  const evidence = evidenceLine(item);
  const strip = layout === "strip";
  return (
    <div className={strip
      ? "flex min-w-[280px] flex-1 flex-col gap-2 rounded-lg bg-muted/40 p-3"
      : "flex flex-col gap-2 border-b border-border/70 px-4 py-3 last:border-0 sm:flex-row sm:items-start sm:gap-4"}
         data-testid={`nba-action-${item.action_type}`}>
      <div className="flex min-w-0 flex-1 items-start gap-2.5">
        <span className={`mt-[7px] size-1.5 shrink-0 rounded-full ${tone.dot}`} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-[13px] font-medium text-foreground" title={item.title}>{item.title}</span>
            {item.state === "accepted" ? (
              <span className="shrink-0 rounded border border-border bg-muted px-1.5 text-[10px] font-medium leading-4 text-foreground/80">Accepted</span>
            ) : null}
          </div>
          <p className={`mt-0.5 text-xs leading-5 text-muted-foreground ${strip ? "line-clamp-2" : "line-clamp-2 sm:line-clamp-1"}`} title={item.reason}>{item.reason}</p>
          <p className="mt-1 break-words text-[11px] leading-4 text-muted-foreground">
            <span className={`font-medium ${tone.text}`}>{tone.label}</span>
            {evidence ? <>{" · "}<span data-testid="nba-evidence">{evidence}</span></> : null}
            {item.source_refs?.length ? (
              <>{" · "}<span data-testid="nba-source-refs">Derived from {item.source_refs.join(", ")}</span></>
            ) : null}
          </p>
        </div>
      </div>
      <div className={`flex shrink-0 flex-wrap items-center gap-0.5 ${strip ? "pl-4" : "pl-4 sm:pl-0"}`}>
        {item.deep_link ? (
          // Where the work itself is done. Following it records nothing: "Done"
          // below is still the operator's own call.
          <Button asChild size="sm" variant="outline" className={ACTION}>
            <Link to={item.deep_link} data-testid="nba-open">
              {item.action_type === "advance_task" ? "Open task" : "Open"}<ArrowRight className="-mr-0.5" />
            </Link>
          </Button>
        ) : null}
        {item.state !== "accepted" ? (
          <Button size="sm" variant="ghost" className={TEXT_ACTION} disabled={busy}
                  onClick={() => onFeedback(item, "accepted")} data-testid="nba-accept">Accept</Button>
        ) : null}
        <Button size="sm" variant="ghost" className={TEXT_ACTION} disabled={busy}
                onClick={() => onFeedback(item, "completed", { outcome: "done" })} data-testid="nba-complete">
          <CheckCircle2 className="-ml-0.5" />Done
        </Button>
        <Button size="sm" variant="ghost" className={ICON_ACTION} disabled={busy}
                onClick={() => onFeedback(item, "snoozed", { snooze_minutes: 1440 })}
                aria-label="Snooze for a day" title="Snooze for a day" data-testid="nba-snooze">
          <Clock />
        </Button>
        <Button size="sm" variant="ghost" className={ICON_ACTION} disabled={busy}
                onClick={() => onFeedback(item, "dismissed", { outcome: "not_relevant" })}
                aria-label="Not relevant" title="Not relevant" data-testid="nba-dismiss">
          <X />
        </Button>
        {onNavigate && item.workspace_id ? (
          <Button size="sm" variant="ghost" className={ICON_ACTION} onClick={() => onNavigate(item)}
                  aria-label="Open the related workspace" title="Open the related workspace" data-testid="nba-navigate">
            <ChevronRight />
          </Button>
        ) : onNavigate && !strip ? <span className="hidden size-7 sm:block" aria-hidden="true" /> : null}
      </div>
    </div>
  );
}

export default function NextBestActions({ workspaceId = null, limit = 5, title = "Next best actions",
                                          onNavigate = null, compact = false }) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const params = { state: "open", limit };
      if (workspaceId) params.workspace_id = workspaceId;
      const { data } = await api.get("/next-best-actions", { params });
      setItems(Array.isArray(data) ? data : []);
    } catch (e) {
      setItems([]);
      setError(formatErr(e.response?.data?.detail) || "Recommendations are unavailable right now.");
    }
  }, [workspaceId, limit]);

  useEffect(() => { load(); }, [load]);

  const regenerate = async () => {
    setBusyId("generate");
    try {
      await api.post("/next-best-actions/generate");
      await load();
      toast.success("Recommendations refreshed");
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || "Could not refresh recommendations");
    } finally { setBusyId(null); }
  };

  const feedback = async (recommendation, state, extra = {}) => {
    setBusyId(recommendation.id);
    try {
      await api.patch(`/next-best-actions/${recommendation.id}`, { state, ...extra });
      await load();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || "Could not record that decision");
    } finally { setBusyId(null); }
  };

  const refreshing = busyId === "generate";

  if (items === null) {
    return (
      <div className={compact ? "overflow-hidden rounded-xl border border-border bg-card" : "mb-6 rounded-xl border border-border bg-card p-2"} data-testid="nba-loading">
        {Array.from({ length: compact ? 3 : 1 }).map((_, index) => (
          <div key={index} className={`flex items-start gap-3 px-4 py-3 ${index ? "border-t border-border/70" : ""}`}>
            <Skeleton className="mt-1 size-2 rounded-full" />
            <div className="flex-1 space-y-2"><Skeleton className="h-3.5 w-2/3" /><Skeleton className="h-3 w-1/2" /></div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className={`flex flex-col items-center justify-center rounded-xl border border-border bg-card px-6 py-10 text-center ${compact ? "" : "mb-6"}`}
           data-testid="nba-error" role="alert">
        <span className="flex size-10 items-center justify-center rounded-full bg-red-50 text-red-600"><CircleAlert className="size-[18px]" aria-hidden="true" /></span>
        <p className="mt-3 text-sm font-medium text-foreground">Next best actions unavailable</p>
        <p className="mt-1 max-w-sm text-[13px] leading-5 text-muted-foreground">{error}</p>
        <Button size="sm" variant="outline" className="mt-4" onClick={load} data-testid="nba-error-retry">
          <RefreshCw className="size-3.5" />Retry
        </Button>
      </div>
    );
  }

  if (!items.length) {
    return (
      <div className={compact ? "" : "mb-6"} data-testid="nba-empty-wrapper">
        <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card px-6 py-10 text-center" data-testid="nba-empty">
          <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground"><CheckCircle2 className="size-[18px]" aria-hidden="true" /></span>
          <h2 className="mt-3 text-sm font-medium text-foreground">Nothing needs a decision right now</h2>
          <p className="mt-1 max-w-md text-[13px] leading-5 text-muted-foreground">No open recommendations. New ones appear as commitments, approvals, delivery work, integrations, or recovery candidates change.</p>
          <Button size="sm" variant="outline" className="mt-4" onClick={regenerate} disabled={refreshing} data-testid="nba-generate">
            {refreshing ? "Refreshing…" : "Refresh recommendations"}
          </Button>
        </div>
      </div>
    );
  }

  const header = (
    <div className={`flex items-center justify-between gap-2 ${compact ? "h-10 border-b border-border/70 bg-muted/30 pl-4 pr-2" : "mb-1.5 h-8 pl-1"}`}>
      <div className="flex min-w-0 items-center gap-2 text-xs font-medium text-muted-foreground">
        <span className="truncate">{title}</span>
        <span className="tabular rounded bg-muted px-1 text-[11px]">{items.length}</span>
      </div>
      <Button size="sm" variant="ghost" className="h-7 gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground [&_svg]:size-3.5" onClick={regenerate}
              disabled={refreshing} data-testid="nba-refresh">
        <RefreshCw className={refreshing ? "animate-spin" : ""} />{refreshing ? "Refreshing…" : "Refresh"}
      </Button>
    </div>
  );

  return (
    <div className={compact
      ? "overflow-hidden rounded-xl border border-border bg-card"
      : "sticky top-[72px] z-10 mb-6 rounded-xl border border-border bg-card/95 p-2 shadow-xs backdrop-blur"}
         data-testid="nba-strip">
      {header}
      <div className={compact ? "" : "flex gap-2 overflow-x-auto"}>
        {items.map((item) => (
          <Recommendation key={item.id} item={item} busy={busyId === item.id} onFeedback={feedback}
                          onNavigate={onNavigate} layout={compact ? "list" : "strip"} />
        ))}
      </div>
    </div>
  );
}
