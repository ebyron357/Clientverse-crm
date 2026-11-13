import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatErr } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";

const CONTACT_MODES = [["brief", "Customer brief"], ["follow_up", "Follow-up draft"], ["tasks", "Task suggestions"]];
const GENERAL_MODES = [["search", "Ask for records"], ["pipeline", "Pipeline review"], ["workflow", "Workflow outline"]];

/** No send/save/merge/activate action: generated text stays a reviewable preview. */
export default function AssistantPanel({ contactId = null }) {
  const [available, setAvailable] = useState(null);
  const [mode, setMode] = useState(contactId ? "brief" : "search");
  const [instruction, setInstruction] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const generation = useRef(0);
  const heading = useRef(null);
  const modes = contactId ? CONTACT_MODES : GENERAL_MODES;
  useEffect(() => {
    let active = true;
    api.get("/assistant/status").then(({ data }) => { if (active) setAvailable(Boolean(data.available)); })
      .catch(() => { if (active) setAvailable(false); });
    return () => { active = false; generation.current += 1; };
  }, [contactId]);

  const generate = async (event) => {
    event.preventDefault();
    if (busy || !consent) return;
    const version = ++generation.current;
    setBusy(true); setError(""); setResult(null);
    try {
      const { data } = await api.post("/assistant/preview", { mode, contact_id: contactId, instruction, allow_provider: true });
      if (version !== generation.current) return;
      setResult(data);
      requestAnimationFrame(() => heading.current?.focus());
    } catch (failure) {
      if (version === generation.current) setError(formatErr(failure.response?.data?.detail) || "Assistance is unavailable. Your records are unchanged.");
    } finally { if (version === generation.current) setBusy(false); }
  };
  const reset = () => { generation.current += 1; setResult(null); setError(""); setBusy(false); };
  return <section className="space-y-5" aria-label="Read-only AI assistance" data-testid="assistant-panel">
    <div><h3 className="text-base font-semibold">Prepare your next action</h3>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">AI can help prepare work, not complete it. Verify every draft against its sources. No message is sent, task created, contact merged, or workflow activated here.</p></div>
    {available === null ? <p role="status">Checking availability…</p> : !available ? <div role="status" className="rounded-lg border border-border p-4 text-sm leading-6">
      AI assistance is not configured on this server. Your existing records, search, duplicate review, and automations still work. No sample AI answer is shown in place of a real response.
    </div> : <form onSubmit={generate} className="space-y-4">
      <div className="grid gap-2"><Label htmlFor={`assistant-mode-${contactId || "general"}`}>Help with</Label>
        <select id={`assistant-mode-${contactId || "general"}`} className="min-h-11 rounded-md border border-input bg-background px-3 text-sm" value={mode}
          onChange={(event) => { reset(); setMode(event.target.value); }} disabled={busy}>
          {modes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></div>
      <div className="grid gap-2"><Label htmlFor={`assistant-instruction-${contactId || "general"}`}>What do you need? {mode === "search" || mode === "workflow" ? "(required)" : "(optional)"}</Label>
        <Textarea id={`assistant-instruction-${contactId || "general"}`} value={instruction} maxLength={1000} disabled={busy} required={mode === "search" || mode === "workflow"}
          onChange={(event) => { setInstruction(event.target.value); setResult(null); }}
          placeholder={mode === "search" ? "Show leads waiting for a reply, my overdue tasks, or deals to review" : mode === "workflow" ? "Describe a workflow you want to review" : "Describe the kind of brief or draft you need"} /></div>
      <label className="flex min-h-11 items-start gap-3 text-sm leading-6"><input type="checkbox" checked={consent} disabled={busy} onChange={(event) => setConsent(event.target.checked)} className="mt-1 size-4" />
        <span>I approve sending this request and {contactId ? "this contact’s selected activities, accessible tasks, deals, website inquiries, and recorded conversation messages" : mode === "pipeline" ? "a limited sample of accessible deal names, stages, owners, and dates" : "the supported feature descriptions"} to the configured AI provider. Do not include credentials or sensitive details in the request.</span></label>
      <Button type="submit" disabled={!consent || busy} className="min-h-11">{busy ? "Preparing preview…" : "Prepare preview"}</Button>
    </form>}
    {error && <p role="alert" className="rounded-lg border border-destructive p-3 text-sm">{error}</p>}
    {result && <div className="space-y-5 border-t border-border pt-5" data-testid="assistant-result">
      <h4 ref={heading} tabIndex={-1} className="text-base font-semibold">Review before using</h4>
      <p className="text-sm leading-6 text-muted-foreground">{result.notice}</p>
      {[["summary", "AI summary to verify"], ["suggestions", mode === "follow_up" ? "Draft wording" : "Suggestions to review"]].map(([key, title]) => result[key]?.length > 0 && <section key={key} aria-label={title}>
        <h5 className="font-medium">{title}</h5><ul className="mt-3 space-y-4">{result[key].map((item, index) => <li key={index} className="space-y-2 rounded-lg border border-border p-4">
          <p className="whitespace-pre-wrap break-words text-sm leading-6">{item.text}</p>
          <div className="flex flex-wrap gap-3">{item.source_refs.map((ref) => {
            const source = result.sources.find((entry) => entry.ref === ref);
            return source ? <Link key={ref} to={source.href} className="inline-flex min-h-11 items-center text-sm underline">{source.label}</Link> : null;
          })}</div>
        </li>)}</ul></section>)}
      {mode === "search" && <div><p className="text-sm">Interpretation: {result.intent?.replaceAll("_", " ") || "none"}. Results are limited to 20 records. For other questions, use the existing record filters.</p>
        <ul>{result.matches?.map((match, index) => <li key={index}><Link to={match.href} className="inline-flex min-h-11 items-center text-sm underline">{match.label}</Link></li>)}</ul></div>}
      <details className="text-sm"><summary className="min-h-11 cursor-pointer py-3 font-medium">Inspect the context used</summary>
        <ul className="space-y-3">{result.sources.map((source) => <li key={source.ref}><Link to={source.href} className="underline">{source.label}</Link><dl>{Object.entries(source.facts).map(([key, value]) => <div key={key} className="mt-1 break-words"><dt className="font-medium">{key}</dt><dd className="whitespace-pre-wrap">{value}</dd></div>)}</dl></li>)}</ul>
      </details>
      {result.as_of && <p className="text-xs text-muted-foreground">Generated {new Date(result.as_of).toLocaleString()} · {result.model} · Sources checked, not a guarantee of factual accuracy</p>}
    </div>}
  </section>;
}
