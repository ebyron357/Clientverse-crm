import { useCallback, useEffect, useState } from "react";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { SurfaceEmpty, SurfaceError, SurfaceLoading } from "@/components/SurfaceState";
import { AlertTriangle, ArrowRight, CheckCircle2, ClipboardCheck, Clock, X } from "lucide-react";

/**
 * Next Best Action queue, served by the backend recommendation service.
 *
 * Recommendations are not manufactured in the browser: the client renders what the
 * service derived, including the reason and the records it was derived from, so a
 * user can check the reasoning instead of trusting a number. Feedback (accept,
 * dismiss, complete, snooze) is persisted server-side.
 */

const PRIORITY_BANDS = [
  { max: 10, label: "Critical", className: "border-red-200 bg-red-50 text-red-800" },
  { max: 30, label: "High", className: "border-amber-200 bg-amber-50 text-amber-900" },
  { max: 50, label: "Medium", className: "border-cyan-200 bg-cyan-50 text-cyan-900" },
  { max: Infinity, label: "Low", className: "border-slate-200 bg-slate-50 text-slate-700" },
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

  if (items === null) return <SurfaceLoading rows={compact ? 1 : 2} testid="nba-loading" />;

  if (error) {
    return <SurfaceError title="Next best actions unavailable" description={error} onRetry={load}
                         testid="nba-error" />;
  }

  if (!items.length) {
    return (
      <div className="mb-6" data-testid="nba-empty-wrapper">
        <SurfaceEmpty
          icon={CheckCircle2}
          title="Nothing needs a decision right now"
          description="No open recommendations. New ones appear as commitments, approvals, delivery work, integrations, or recovery candidates change."
          action={<Button variant="outline" className="mt-5" onClick={regenerate}
                          disabled={busyId === "generate"} data-testid="nba-generate">
                    {busyId === "generate" ? "Refreshing…" : "Refresh recommendations"}
                  </Button>}
          testid="nba-empty"
        />
      </div>
    );
  }

  return (
    <div className={compact ? "" : "sticky top-[72px] z-10 mb-6 rounded-xl border border-slate-200 bg-white/95 p-3 shadow-sm backdrop-blur"}
         data-testid="nba-strip">
      <div className="mb-2 flex items-center justify-between gap-2 px-1">
        <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">
          <ClipboardCheck className="h-3.5 w-3.5" />{title}
        </div>
        <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={regenerate}
                disabled={busyId === "generate"} data-testid="nba-refresh">
          {busyId === "generate" ? "Refreshing…" : "Refresh"}
        </Button>
      </div>
      <div className={compact ? "space-y-2" : "flex gap-2 overflow-x-auto pb-1"}>
        {items.map((item) => {
          const tone = band(item.priority);
          const evidence = evidenceLine(item);
          return (
            <div key={item.id}
                 className={`rounded-lg border px-3 py-2 ${tone.className} ${compact ? "" : "min-w-[280px] flex-1"}`}
                 data-testid={`nba-action-${item.action_type}`}>
              <div className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-70" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold uppercase tracking-wide opacity-70">{tone.label}</span>
                    {item.state === "accepted" ? (
                      <span className="text-[10px] font-semibold uppercase opacity-70">Accepted</span>
                    ) : null}
                  </div>
                  <div className="truncate text-sm font-semibold" title={item.title}>{item.title}</div>
                  <div className="mt-0.5 text-[11px] leading-4 opacity-80">{item.reason}</div>
                  {evidence ? (
                    <div className="mt-1 text-[10px] uppercase tracking-wide opacity-60"
                         data-testid="nba-evidence">{evidence}</div>
                  ) : null}
                  {item.source_refs?.length ? (
                    <div className="mt-1 text-[10px] opacity-55" data-testid="nba-source-refs">
                      Derived from {item.source_refs.join(", ")}
                    </div>
                  ) : null}
                </div>
                {onNavigate && item.workspace_id ? (
                  <button type="button" onClick={() => onNavigate(item)}
                          className="ml-auto shrink-0 opacity-60 hover:opacity-100"
                          aria-label="Open the related workspace" data-testid="nba-navigate">
                    <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                ) : null}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {item.state !== "accepted" ? (
                  <Button size="sm" variant="outline" className="h-6 px-2 text-[11px]"
                          disabled={busyId === item.id}
                          onClick={() => feedback(item, "accepted")}
                          data-testid="nba-accept">Accept</Button>
                ) : null}
                <Button size="sm" variant="outline" className="h-6 px-2 text-[11px]"
                        disabled={busyId === item.id}
                        onClick={() => feedback(item, "completed", { outcome: "done" })}
                        data-testid="nba-complete">
                  <CheckCircle2 className="mr-1 h-3 w-3" />Done
                </Button>
                <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]"
                        disabled={busyId === item.id}
                        onClick={() => feedback(item, "snoozed", { snooze_minutes: 1440 })}
                        data-testid="nba-snooze">
                  <Clock className="mr-1 h-3 w-3" />Snooze
                </Button>
                <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]"
                        disabled={busyId === item.id}
                        onClick={() => feedback(item, "dismissed", { outcome: "not_relevant" })}
                        data-testid="nba-dismiss">
                  <X className="mr-1 h-3 w-3" />Not relevant
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
