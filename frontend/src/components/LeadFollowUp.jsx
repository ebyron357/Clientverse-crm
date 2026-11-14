import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { leadFollowUp } from "@/lib/leadFollowUp";

export function LeadFollowUp({ lead }) {
  const next = leadFollowUp(lead);
  return (
    <section aria-label="Next step" data-testid="lead-next-step">
      <h3 className="mb-2 text-sm font-medium text-muted-foreground">Next step</h3>
      <Alert role="note" aria-label="Lead follow-up guidance">
        <AlertTitle role="heading" aria-level={4}>{next.title}</AlertTitle>
        <AlertDescription>
          <div className="flex flex-col gap-3">
            <p>{next.reason}</p>
            <p className="break-words text-muted-foreground">Owner: {next.owner}</p>
            {next.action && <Button asChild variant="outline" className="min-h-11 w-full sm:w-auto sm:self-start">
              <Link to={next.action.to} data-testid="lead-next-step-link"><ArrowUpRight data-icon="inline-start" aria-hidden="true" />{next.action.label}</Link>
            </Button>}
            {lead.status === "new" && !lead.is_test && <p className="text-muted-foreground">An automatic reply is not a personal response. Mark contacted only after reaching out.</p>}
          </div>
        </AlertDescription>
      </Alert>
    </section>
  );
}
