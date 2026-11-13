import { useEffect, useId, useRef, useState } from "react";
import { CheckCircle2, Loader2 } from "lucide-react";
import { formatErr } from "@/lib/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

const actions = [
  { status: "new", label: "Reopen", variant: "ghost" },
  { status: "spam", label: "Spam", variant: "outline" },
  { status: "closed", label: "Close", variant: "outline" },
  { status: "responded", label: "Mark contacted", variant: "default" },
];

export function LeadStatusUpdate({ lead, onStatus, busy = false }) {
  const id = useId();
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(null);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  const errorRef = useRef(null);
  const saving = busy || pending !== null;
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  const submit = async (status) => {
    if (busy || inFlight.current) return;
    inFlight.current = true;
    setPending(status);
    setError("");
    try {
      const saved = await onStatus(lead, status, lead.contact_id ? note : "");
      if (saved === true) setNote("");
      else setError("The update could not be confirmed.");
    } catch (failure) {
      setError(failure?.response?.data?.detail ? formatErr(failure.response.data.detail) : "The server did not confirm this update. Check your connection.");
    } finally {
      inFlight.current = false;
      setPending(null);
    }
  };

  return (
    <section aria-labelledby={`${id}-heading`} className="flex flex-col gap-3" data-testid="lead-update">
      <h3 id={`${id}-heading`} className="text-sm font-medium">Update lead</h3>
      <fieldset disabled={saving} className="min-w-0 flex flex-col gap-3" aria-busy={saving}>
        <legend className="sr-only">Note and status</legend>
        <label htmlFor={`${id}-note`} className="text-sm font-medium">Note (optional)</label>
        <Textarea id={`${id}-note`} value={note} onChange={(event) => setNote(event.target.value)}
          disabled={saving || !lead.contact_id} aria-describedby={`${id}-help`} rows={3}
          placeholder={lead.contact_id ? "What happened in the conversation?" : "No linked contact"}
          data-testid="lead-note" />
        <p id={`${id}-help`} className="text-sm text-muted-foreground">
          {lead.contact_id ? "Saved to the contact’s history with your status update. Drafts are kept only while this lead stays open." : "Notes need a linked contact. You can still change this lead’s status."}
        </p>
        <div className="flex flex-wrap justify-end gap-2">
          {actions.filter((action) => action.status !== lead.status).map((action) => (
            <Button key={action.status} type="button" variant={action.variant} disabled={saving}
              className="min-h-11" data-testid={`lead-status-${action.status}`} onClick={() => submit(action.status)}>
              {pending === action.status ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" data-icon="inline-start" />
                : action.status === "responded" ? <CheckCircle2 aria-hidden="true" data-icon="inline-start" /> : null}
              {pending === action.status ? "Saving…" : action.label}
            </Button>
          ))}
        </div>
      </fieldset>
      <p role="status" className="text-sm text-muted-foreground">{saving ? "Saving update. Please wait before making another change." : note ? "Unsaved note" : ""}</p>
      {error && <Alert ref={errorRef} tabIndex={-1} variant="destructive" data-testid="lead-update-error">
        <AlertTitle role="heading" aria-level={4}>Update not confirmed</AlertTitle>
        <AlertDescription><p>{error}</p><p>{note ? "Your note is still here. " : ""}Check the lead and contact history before retrying; the server may have received the change.</p></AlertDescription>
      </Alert>}
    </section>
  );
}
