import { useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CheckCircle2, CircleAlert, RefreshCw } from "lucide-react";
import RecommendationCard, { SNOOZE_OPTIONS } from "@/components/RecommendationCard";

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

async function fetchRecommendations([, , , workspaceId, limit]) {
  const params = { state: "open", limit };
  if (workspaceId) params.workspace_id = workspaceId;
  const { data } = await api.get("/next-best-actions", { params });
  if (!Array.isArray(data)) throw new Error("Invalid recommendation response");
  return data;
}

function errorMessage(error, fallback) {
  return error?.response?.data?.detail != null ? formatErr(error.response.data.detail) : fallback;
}

export default function NextBestActions({ workspaceId = null, limit = 5, title = "Next best actions",
                                          onNavigate = null, compact = false }) {
  const { user } = useAuth();
  const identity = user?.user_id || user?.id || user?.email;
  const tenant = user?.tenant_id;
  const { mutate } = useSWRConfig();
  const { data: items, error, mutate: reload, isValidating } = useSWR(
    identity && tenant ? ["next-best-actions", tenant, identity, workspaceId, limit] : null,
    fetchRecommendations,
    { shouldRetryOnError: false },
  );
  const [busyId, setBusyId] = useState(null);
  const pending = useRef(false);

  // Invalidate every mounted queue for this user, including differently scoped workspaces.
  const refreshQueues = () => mutate(
    (key) => Array.isArray(key) && key[0] === "next-best-actions" && key[1] === tenant && key[2] === identity,
    undefined,
    { revalidate: true, throwOnError: false },
  );

  const regenerate = async () => {
    if (pending.current) return;
    pending.current = true;
    setBusyId("generate");
    try {
      await api.post("/next-best-actions/generate");
      await refreshQueues();
      toast.success("Recommendations refreshed");
    } catch (e) {
      toast.error(errorMessage(e, "Could not refresh recommendations"));
    } finally {
      pending.current = false;
      setBusyId(null);
    }
  };

  const feedback = async (recommendation, state, extra = {}, undo = false) => {
    if (pending.current) return false;
    pending.current = true;
    setBusyId(recommendation.id);
    try {
      await api.patch(`/next-best-actions/${recommendation.id}`, { state, ...extra });
      await refreshQueues();
      const duration = SNOOZE_OPTIONS.find((option) => option.minutes === extra.snooze_minutes)?.label;
      const messages = {
        accepted: "Recommendation accepted",
        dismissed: "Recommendation dismissed — linked records unchanged",
        completed: "Recommendation reviewed — linked records unchanged",
        snoozed: `Recommendation snoozed${duration ? ` for ${duration}` : ""}`,
      };
      const notificationId = `nba:${tenant}:${identity}:${recommendation.id}`;
      toast.success(undo ? "Recommendation restored" : messages[state], undo ? { id: notificationId } : {
        id: notificationId,
        duration: 10000,
        action: {
          label: "Undo",
          onClick: () => feedback(recommendation, recommendation.state === "accepted" ? "accepted" : "new", {
            outcome: recommendation.outcome || "",
            note: recommendation.feedback_note || "",
          }, true),
        },
      });
      return true;
    } catch (e) {
      toast.error(errorMessage(e, "Could not record that decision"));
      return false;
    } finally {
      pending.current = false;
      setBusyId(null);
    }
  };

  const refreshing = busyId === "generate";
  const busy = busyId !== null;

  if (error) {
    return (
      <div className={`flex flex-col items-center justify-center rounded-xl border border-border bg-card px-6 py-10 text-center ${compact ? "" : "mb-6"}`}
           data-testid="nba-error" role="alert">
        <span className="flex size-10 items-center justify-center rounded-full bg-destructive/10 text-destructive"><CircleAlert className="size-5" aria-hidden="true" /></span>
        <p className="mt-3 text-base font-medium text-foreground">Next best actions unavailable</p>
        <p className="mt-1 max-w-sm text-sm leading-6 text-muted-foreground">{errorMessage(error, "Recommendations are unavailable right now.")}</p>
        <Button variant="outline" className="mt-4 min-h-11" onClick={() => reload()} disabled={isValidating} data-testid="nba-error-retry">
          <RefreshCw aria-hidden="true" />{isValidating ? "Retrying…" : "Retry"}
        </Button>
      </div>
    );
  }

  if (!items) {
    return (
      <div className={compact ? "overflow-hidden rounded-xl border border-border bg-card" : "mb-6 rounded-xl border border-border bg-card p-2"} data-testid="nba-loading" aria-label="Loading recommendations" role="status">
        {Array.from({ length: compact ? 3 : 1 }).map((_, index) => (
          <div key={index} className={`flex items-start gap-3 px-4 py-3 ${index ? "border-t border-border/70" : ""}`}>
            <Skeleton className="mt-1 size-2 rounded-full" />
            <div className="flex flex-1 flex-col gap-2"><Skeleton className="h-4 w-2/3" /><Skeleton className="h-4 w-1/2" /></div>
          </div>
        ))}
      </div>
    );
  }

  if (!items.length) {
    return (
      <div className={compact ? "" : "mb-6"} data-testid="nba-empty-wrapper">
        <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card px-6 py-10 text-center" data-testid="nba-empty">
          <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground"><CheckCircle2 className="size-5" aria-hidden="true" /></span>
          <h2 className="mt-3 text-base font-medium text-foreground">No recommendations to review right now</h2>
          <p className="mt-1 max-w-md text-sm leading-6 text-muted-foreground">Snoozed recommendations return when their timer ends. Reviewed or dismissed recommendations do not close the underlying work.</p>
          <Button variant="outline" className="mt-4 min-h-11" onClick={regenerate} disabled={busy} data-testid="nba-generate">
            {refreshing ? "Refreshing…" : "Refresh recommendations"}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <section className={compact
      ? "overflow-hidden rounded-xl border border-border bg-card"
      : "mb-6 rounded-xl border border-border bg-card/95 p-2 shadow-xs backdrop-blur md:sticky md:top-[72px] md:z-10"}
      aria-label={title} data-testid="nba-strip">
      <div className={`flex flex-wrap items-center justify-between gap-2 ${compact ? "border-b border-border/70 bg-muted/30 px-4 py-2 text-foreground" : "px-2 py-1"}`}>
        <h2 className="flex min-w-0 items-center gap-2 text-sm font-semibold text-foreground">
          <span>{title}</span><span className="rounded bg-muted px-2 tabular-nums text-muted-foreground">{items.length}</span>
        </h2>
        <Button variant="ghost" className="min-h-11" onClick={regenerate} disabled={busy} data-testid="nba-refresh">
          <RefreshCw className={refreshing ? "animate-spin" : ""} aria-hidden="true" />{refreshing ? "Refreshing…" : "Refresh"}
        </Button>
      </div>
      <p className="px-4 py-3 text-sm leading-6 text-muted-foreground">Review the linked record to do the work. Mark reviewed or dismiss only updates this queue.</p>
      <div className={compact ? "" : "flex flex-col gap-2 md:flex-row md:overflow-x-auto"}>
        {items.map((item) => (
          <RecommendationCard key={item.id} item={item} busy={busy} onFeedback={feedback}
            onNavigate={onNavigate} layout={compact ? "list" : "strip"} />
        ))}
      </div>
    </section>
  );
}
