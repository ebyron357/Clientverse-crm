import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, ChevronRight, Clock, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";

const ACTION_LABELS = {
  resolve_commitment: "Review commitment",
  decide_approval: "Review approval",
  advance_task: "Open task",
  recover_stalled_lead: "Review recovery",
  recover_missed_followup: "Review follow-up",
  repair_integration: "Check integration",
  review_client_health: "Review client health",
};

const PRIORITY_BANDS = [
  { max: 10, label: "Critical", text: "text-foreground font-bold" },
  { max: 30, label: "High", text: "text-foreground" },
  { max: 50, label: "Medium", text: "text-brand" },
  { max: Infinity, label: "Low", text: "text-muted-foreground" },
];

export const SNOOZE_OPTIONS = [
  { label: "1 hour", minutes: 60 },
  { label: "4 hours", minutes: 240 },
  { label: "1 day", minutes: 1440 },
  { label: "3 days", minutes: 4320 },
  { label: "1 week", minutes: 10080 },
];

function evidenceLine(recommendation) {
  const evidence = recommendation.evidence || {};
  const parts = [];
  if (evidence.due_at) {
    const due = new Date(evidence.due_at);
    if (!Number.isNaN(due.getTime())) parts.push(`Due ${due.toLocaleDateString()}`);
  }
  if (evidence.overdue_days != null) parts.push(`${evidence.overdue_days} days overdue`);
  if (evidence.idle_days != null) parts.push(`${evidence.idle_days} days idle`);
  if (evidence.owner) parts.push(`Owner: ${evidence.owner}`);
  if (evidence.status) parts.push(`Status: ${evidence.status}`);
  if (evidence.band) parts.push(`Health: ${String(evidence.band).replaceAll("_", " ")}`);
  return parts.join(" · ");
}

export default function RecommendationCard({ item, busy, onFeedback, onNavigate, layout }) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const tone = PRIORITY_BANDS.find((entry) => item.priority <= entry.max) || PRIORITY_BANDS[3];
  const evidence = evidenceLine(item);
  const strip = layout === "strip";

  const complete = async (event) => {
    event.preventDefault();
    if (await onFeedback(item, "completed", { outcome: "done" })) setConfirmOpen(false);
  };

  return (
    <article className={cn(
      "flex min-w-0 flex-col gap-3",
      strip ? "rounded-lg bg-muted/40 p-4 text-foreground md:min-w-80 md:flex-1" : "border-b border-border/70 p-4 last:border-0",
    )} aria-label={item.title} aria-busy={busy} data-testid={`nba-action-${item.action_type}`}>
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className={cn("font-medium", tone.text)}>{tone.label} priority</span>
          {item.state === "accepted" && <span className="rounded-md bg-muted px-2 py-0.5 text-muted-foreground">Accepted</span>}
        </div>
        <h3 className="break-words text-base font-semibold leading-6 text-foreground">{item.title}</h3>
        <p className="break-words text-sm leading-6 text-muted-foreground">{item.reason}</p>
        {(evidence || item.source_refs?.length > 0) && (
          <details className="text-sm leading-6 text-muted-foreground">
            <summary className="w-fit cursor-pointer rounded-md py-2 font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Why this is recommended</summary>
            <div className="flex flex-col gap-1 break-words">
              {evidence && <p data-testid="nba-evidence">{evidence}</p>}
              {item.source_refs?.length > 0 && <p className="break-all" data-testid="nba-source-refs">Derived from {item.source_refs.join(", ")}</p>}
            </div>
          </details>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {item.deep_link && (
          // Navigation records nothing; source records are changed in their own workspace.
          <Button asChild variant="outline" className="min-h-11">
            <Link to={item.deep_link} data-testid="nba-open">
              {ACTION_LABELS[item.action_type] || "Review details"}<ArrowRight aria-hidden="true" />
            </Link>
          </Button>
        )}
        {item.state !== "accepted" && (
          <Button variant="ghost" className="min-h-11" disabled={busy}
            onClick={() => onFeedback(item, "accepted")} data-testid="nba-accept">Accept</Button>
        )}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="min-h-11" disabled={busy} data-testid="nba-snooze">
              <Clock aria-hidden="true" />Snooze
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuGroup>
              <DropdownMenuLabel>Remind me in</DropdownMenuLabel>
              {SNOOZE_OPTIONS.map(({ label, minutes }) => (
                <DropdownMenuItem key={minutes} className="min-h-11" disabled={busy}
                  onSelect={() => onFeedback(item, "snoozed", { snooze_minutes: minutes })}>{label}</DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        <AlertDialog open={confirmOpen} onOpenChange={(open) => { if (!busy) setConfirmOpen(open); }}>
          <AlertDialogTrigger asChild>
            <Button variant="ghost" className="min-h-11" disabled={busy} data-testid="nba-complete">
              <CheckCircle2 aria-hidden="true" />Mark reviewed
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Finish reviewing this recommendation?</AlertDialogTitle>
              <AlertDialogDescription>
                This removes &ldquo;{item.title}&rdquo; from your recommendation queue. It does not complete a task,
                resolve a commitment, approve a request, or change any linked record. Use the review link to do that work first.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel className="min-h-11" disabled={busy}>Keep in queue</AlertDialogCancel>
              <AlertDialogAction className="min-h-11" disabled={busy} onClick={complete}>
                {busy ? "Saving…" : "Mark reviewed"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
        <Button variant="ghost" className="min-h-11" disabled={busy}
          onClick={() => onFeedback(item, "dismissed", { outcome: "not_relevant" })}
          title="Hide this recommendation as not relevant; linked records are unchanged" data-testid="nba-dismiss">
          <X aria-hidden="true" />Dismiss
        </Button>
        {onNavigate && item.workspace_id && (
          <Button variant="ghost" className="min-h-11" onClick={() => onNavigate(item)} data-testid="nba-navigate">
            Client workspace<ChevronRight aria-hidden="true" />
          </Button>
        )}
      </div>
    </article>
  );
}
