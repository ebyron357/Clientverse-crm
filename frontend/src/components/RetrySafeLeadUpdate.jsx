import { useEffect, useId, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { LeadNoteGuard } from "@/components/LeadNoteGuard";
import { formatErr } from "@/lib/api";

const labels = { new: "Reopen", responded: "Mark contacted", closed: "Close", spam: "Spam" };
const statuses = { new: "New", responded: "Contacted", closed: "Closed", spam: "Spam" };
const uncertain = new Set(["unknown", "checking", "saving"]);

export function RetrySafeLeadUpdate({ lead, onStatus, onReload, onReceipt, busy = false }) {
  const id = useId();
  const [note, setNote] = useState("");
  const [baseline, setBaseline] = useState(lead);
  const [intent, setIntent] = useState(null);
  const [phase, setPhase] = useState("idle");
  const [message, setMessage] = useState("");
  const lock = useRef(false);
  const noteRef = useRef(null);
  const alertRef = useRef(null);
  const waiting = busy || ["saving", "checking", "loading"].includes(phase);
  const unresolved = uncertain.has(phase);
  const locked = waiting || unresolved || phase === "conflict" || phase === "review";

  useEffect(() => { if (message) alertRef.current?.focus(); }, [message]);
  useEffect(() => { if (phase === "saved" && !busy) noteRef.current?.focus(); }, [phase, busy]);

  const confirm = (result, operation) => {
    if (result?.state !== "committed" || result.operation_id !== operation.operation_id || result.lead?.id !== lead.id) {
      setPhase("unknown");
      setMessage("The server has not confirmed this operation. It may still be processing. Check its outcome or retry the same update.");
      return;
    }
    setBaseline(result.lead);
    setNote("");
    setIntent(null);
    setPhase("saved");
    setMessage("");
    noteRef.current?.focus();
  };

  const reportFailure = (failure, wasUncertain = false) => {
    const detail = failure?.response?.data?.detail;
    const code = detail?.code;
    if (["version_conflict", "operation_key_reused"].includes(code)) setPhase("conflict");
    else if (!wasUncertain && (["missing_contact", "rollout_not_ready", "transactions_unavailable", "rollout_disabled"].includes(code) || failure?.response?.status === 422)) setPhase("rejected");
    else setPhase("unknown");
    setMessage(detail?.message || (detail ? formatErr(detail) : "Check your connection. The server may have received this update; its outcome is not confirmed."));
  };

  const submit = async (status, retry = false) => {
    if (busy || lock.current) return;
    lock.current = true;
    const operation = retry ? intent : {
      operation_id: crypto.randomUUID(), expected_version: baseline.version ?? 0,
      status, note: baseline.contact_id ? note : "",
    };
    setIntent(operation);
    setPhase("saving");
    setMessage("");
    try { confirm(await onStatus(lead, operation.status, operation.note, operation), operation); }
    catch (failure) { reportFailure(failure, retry); }
    finally { lock.current = false; }
  };

  const check = async () => {
    if (lock.current) return;
    lock.current = true;
    setPhase("checking");
    try { confirm(await onReceipt(lead, intent), intent); }
    catch (failure) { reportFailure(failure, true); }
    finally { lock.current = false; }
  };

  const reload = async () => {
    if (lock.current) return;
    lock.current = true;
    setPhase("loading");
    try {
      const latest = await onReload(lead);
      setBaseline(latest);
      setPhase("review");
      setMessage(`Latest saved status: ${statuses[latest.status] || latest.status}. Review the lead and its history. Your proposed status is ${statuses[intent.status]}; your note is preserved below. Nothing has been reapplied.`);
    } catch {
      setPhase("conflict");
      setMessage("The latest lead could not be loaded. Your draft is still here. Try reloading again before reapplying.");
    } finally { lock.current = false; }
  };

  return <section className="flex flex-col gap-3" aria-labelledby={`${id}-heading`} data-testid="lead-update">
    <LeadNoteGuard dirty={Boolean(note.trim()) || phase === "conflict" || phase === "review"} saving={waiting} unresolved={unresolved} noteRef={noteRef} />
    <h3 id={`${id}-heading`} className="text-sm font-medium">Update lead</h3>
    <p className="text-sm text-muted-foreground">Retry-safe save · changes are checked against the version you reviewed.</p>
    <fieldset disabled={locked} className="flex min-w-0 flex-col gap-3" aria-busy={waiting}>
      <legend className="sr-only">Note and status</legend>
      <label htmlFor={`${id}-note`} className="text-sm font-medium">Note (optional)</label>
      <Textarea id={`${id}-note`} ref={noteRef} className="text-base" value={note} maxLength={2000} rows={3}
        disabled={locked || !baseline.contact_id} onChange={(event) => setNote(event.target.value)}
        aria-describedby={`${id}-help`} data-testid="lead-note" placeholder={baseline.contact_id ? "What happened in the conversation?" : "No linked contact"} />
      <p id={`${id}-help`} className="text-sm text-muted-foreground">{baseline.contact_id ? "Your note and status save together. Drafts stay on this page only; they are not stored on this device." : "Notes need a linked contact. You can still change the status."}</p>
      <div className="flex flex-wrap justify-end gap-2">
        {Object.entries(labels).filter(([status]) => status !== baseline.status).map(([status, label]) => <Button key={status} type="button" className="min-h-11" variant={status === "responded" ? "default" : "outline"}
          disabled={locked} data-testid={`lead-status-${status}`} onClick={() => submit(status)}>{label}</Button>)}
        {note.trim() && <Button type="button" className="min-h-11" variant="secondary" disabled={locked} data-testid="lead-save-note" onClick={() => submit(baseline.status)}>Save note only</Button>}
      </div>
    </fieldset>
    <p role="status" className="text-sm text-muted-foreground">{waiting ? "Saving or checking update. Please wait." : phase === "saved" ? "Saved — confirmed by the server." : note ? "Unsaved note" : ""}</p>
    {message && <Alert ref={alertRef} tabIndex={-1} variant="destructive" data-testid="lead-update-error">
      <AlertTitle role="heading" aria-level={4}>{phase === "conflict" ? "This lead has changed" : phase === "review" ? "Review before reapplying" : phase === "rejected" ? "Update not saved" : "Update not confirmed"}</AlertTitle>
      <AlertDescription className="flex flex-col gap-3">
        <p>{message}</p>
        {note && <p>Your note is still here.</p>}
        <div className="flex flex-wrap gap-2">
          {phase === "unknown" && <>
            <Button type="button" variant="outline" className="min-h-11" data-testid="lead-check-outcome" onClick={check}>Check outcome</Button>
            <Button type="button" variant="outline" className="min-h-11" data-testid="lead-retry" onClick={() => submit(intent.status, true)}>Retry same update</Button>
          </>}
          {phase === "conflict" && <Button type="button" variant="outline" className="min-h-11" data-testid="lead-reload" onClick={reload}>Reload latest and review</Button>}
          {phase === "review" && <>
            <Button type="button" variant="outline" className="min-h-11" data-testid="lead-reapply" onClick={() => submit(intent.status)}>Reapply my update</Button>
            <Button type="button" variant="outline" className="min-h-11" data-testid="lead-review-edit" onClick={() => { setPhase("idle"); setMessage(""); setIntent(null); noteRef.current?.focus(); }}>Edit instead</Button>
          </>}
          {waiting && <Loader2 className="size-5 animate-spin motion-reduce:animate-none" aria-label="Checking update" />}
        </div>
      </AlertDescription>
    </Alert>}
  </section>;
}
