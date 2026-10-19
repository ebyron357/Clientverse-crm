/* Customize stages (admins only). Rename, add, reorder and remove the pipeline's stages,
   and say which of them mean won or lost.

   The server refuses any change that would alter deals nobody moved: removing a stage
   that still has deals, switching such a stage between open, won and lost, or removing
   or closing the stage a website form starts its leads in. This editor shows those limits
   up front, from the pipeline's `in_use` report, and still shows the server's own words if
   it refuses something. */
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { api, formatErr } from "@/lib/api";
import { OUTCOME, stageAccent, stageKeyFor, stageOutcome } from "@/lib/pipeline";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AlertTriangle, ChevronDown, ChevronUp, Globe, Plus, Trash2 } from "lucide-react";

const OUTCOME_LABEL = { [OUTCOME.OPEN]: "Still open", [OUTCOME.WON]: "Won", [OUTCOME.LOST]: "Lost" };

function flagsFor(outcome) {
  if (outcome === OUTCOME.WON) return { is_closed: true, is_won: true };
  if (outcome === OUTCOME.LOST) return { is_closed: true, is_won: false };
  return { is_closed: false, is_won: false };
}

function rowsFrom(stages) {
  return (stages || []).map((stage) => ({ key: stage.key, label: stage.label, probability: stage.probability ?? 0, is_closed: Boolean(stage.is_closed), is_won: Boolean(stage.is_won), isNew: false }));
}

function dealsText(usage) {
  if (!usage?.deals) return "";
  const archived = usage.archived_deals ? ` (${usage.archived_deals} archived)` : "";
  return `${usage.deals} deal${usage.deals === 1 ? "" : "s"}${archived}`;
}

export default function StageEditor({ open, onOpenChange, stages: boardStages, onSaved }) {
  const [saved, setSaved] = useState({ stages: boardStages || [], inUse: {} });
  const [rows, setRows] = useState(() => rowsFrom(boardStages));
  const [newLabel, setNewLabel] = useState("");
  const [saving, setSaving] = useState(false);
  const [checking, setChecking] = useState(false);
  const [problem, setProblem] = useState("");
  const stages = saved.stages;
  const inUse = saved.inUse;

  // Start from the saved stages each time the dialog opens -- and only then, so a board
  // refresh in the background cannot wipe edits in progress. What each stage holds is
  // re-read on opening: deals may have moved since the board loaded. Editing waits for that
  // answer, which replaces the rows, and an answer meant for an earlier opening (closed and
  // reopened before it came back) is ignored.
  const wasOpen = useRef(false);
  const opening = useRef(0);
  useEffect(() => {
    if (open && !wasOpen.current) {
      const current = ++opening.current;
      const stillCurrent = () => current === opening.current;
      setRows(rowsFrom(boardStages)); setSaved({ stages: boardStages || [], inUse: {} }); setNewLabel(""); setProblem(""); setChecking(true);
      api.get("/pipelines/default").then(({ data }) => {
        if (!stillCurrent()) return;
        setSaved({ stages: data.stages || [], inUse: data.in_use || {} });
        setRows(rowsFrom(data.stages));
      }).catch(() => stillCurrent() && setProblem("Could not check which stages are in use. Saving still checks it for you.")).finally(() => stillCurrent() && setChecking(false));
    }
    if (!open && wasOpen.current) opening.current += 1;
    wasOpen.current = open;
  }, [open, boardStages]);

  const originalOutcome = useMemo(() => Object.fromEntries((stages || []).map((stage) => [stage.key, stageOutcome(stage)])), [stages]);
  const update = (index, changes) => setRows((current) => current.map((row, position) => position === index ? { ...row, ...changes } : row));
  const move = (index, step) => setRows((current) => {
    const next = [...current];
    const target = index + step;
    if (target < 0 || target >= next.length) return current;
    [next[index], next[target]] = [next[target], next[index]];
    return next;
  });
  const remove = (index) => setRows((current) => current.filter((_, position) => position !== index));

  const addStage = () => {
    const label = newLabel.trim();
    if (!label) { toast.error("Type a name for the new stage first."); return; }
    setRows((current) => {
      const key = stageKeyFor(label, new Set(current.map((row) => row.key)));
      const row = { key, label, probability: 50, is_closed: false, is_won: false, isNew: true };
      // New stages are open, so they go after the last open stage and before won and lost.
      let lastOpen = -1;
      current.forEach((item, position) => { if (!item.is_closed) lastOpen = position; });
      const next = [...current];
      next.splice(lastOpen + 1, 0, row);
      return next;
    });
    setNewLabel("");
  };

  const save = async () => {
    setProblem("");
    if (rows.some((row) => !row.label.trim())) { setProblem("Every stage needs a name."); return; }
    if (!rows.some((row) => stageOutcome(row) === OUTCOME.WON)) { setProblem("Keep at least one stage that counts as won."); return; }
    if (!rows.some((row) => stageOutcome(row) === OUTCOME.OPEN)) { setProblem("Keep at least one open stage — new deals and website leads start there."); return; }
    setSaving(true);
    try {
      const payload = rows.map((row) => ({ key: row.key, label: row.label.trim(), probability: Math.max(0, Math.min(100, Math.round(Number(row.probability) || 0))), is_closed: row.is_closed, is_won: row.is_won }));
      const { data } = await api.put("/pipelines/default", { stages: payload });
      toast.success("Stages saved", { description: "The board now shows your new stages." });
      onSaved(data.stages);
      onOpenChange(false);
    } catch (requestError) {
      const detail = formatErr(requestError.response?.data?.detail);
      setProblem(detail);
      toast.error("Stages were not saved", { description: detail });
    } finally { setSaving(false); }
  };

  // Dots match the board's: open stages take their colour from their place among open stages.
  const openKeys = rows.filter((row) => stageOutcome(row) === OUTCOME.OPEN).map((row) => row.key);
  const accentOf = (row) => stageAccent(row, openKeys.indexOf(row.key));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[92vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl" data-testid="stage-editor">
        <DialogHeader className="space-y-1 border-b border-border px-5 py-4 pr-12 text-left">
          <DialogTitle className="text-base font-semibold tracking-tight">Customize stages</DialogTitle>
          <DialogDescription className="text-[13px] leading-5">Rename, reorder, add or remove the steps your deals move through. Renaming a stage keeps its deals and website forms pointing at it.</DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4">
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            <div className="hidden h-8 items-center gap-2 border-b border-border bg-muted/40 px-3 text-xs font-medium text-muted-foreground sm:flex" aria-hidden="true">
              <span className="w-[2.125rem] shrink-0" /><span className="flex-1">Stage</span><span className="w-[8.5rem] shrink-0">Reaching it means</span><span className="w-[5.5rem] shrink-0">Chance</span><span className="w-8 shrink-0" />
            </div>
            <ol className="divide-y divide-border/70" aria-busy={checking}>
              {rows.map((row, index) => {
                const usage = row.isNew ? null : inUse?.[row.key];
                const forms = usage?.website_forms || [];
                const hasDeals = Boolean(usage?.deals);
                const outcome = stageOutcome(row);
                // What the server would refuse, said before anyone tries it.
                const lockOutcome = hasDeals || (forms.length > 0 && originalOutcome[row.key] === OUTCOME.OPEN);
                const removeBlocked = hasDeals ? `Move its ${dealsText(usage)} to another stage first` : forms.length ? `Website form “${forms[0].name}” starts new leads here` : "";
                return (
                  <li key={row.key} className="px-3 py-2" data-testid={`stage-row-${row.key}`}>
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="flex shrink-0 items-center gap-1.5">
                        <div className="flex flex-col">
                          <button type="button" onClick={() => move(index, -1)} disabled={checking || index === 0} className="flex h-4 w-5 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-30" aria-label={`Move ${row.label || "this stage"} up`} data-testid={`stage-up-${row.key}`}><ChevronUp className="size-3.5" aria-hidden="true" /></button>
                          <button type="button" onClick={() => move(index, 1)} disabled={checking || index === rows.length - 1} className="flex h-4 w-5 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-30" aria-label={`Move ${row.label || "this stage"} down`} data-testid={`stage-down-${row.key}`}><ChevronDown className="size-3.5" aria-hidden="true" /></button>
                        </div>
                        <span className={`size-2 shrink-0 rounded-full ${accentOf(row)}`} aria-hidden="true" />
                      </div>
                      <Input value={row.label} onChange={(event) => update(index, { label: event.target.value })} aria-label="Stage name" className="h-8 min-w-[9rem] flex-1 text-[13px] md:text-[13px]" maxLength={80} disabled={checking} data-testid={`stage-label-${row.key}`} />
                      <div className="flex w-full flex-wrap items-center gap-2 pl-[2.625rem] sm:w-auto sm:flex-nowrap sm:pl-0">
                        <Select value={outcome} onValueChange={(value) => update(index, { ...flagsFor(value), probability: value === OUTCOME.WON ? 100 : value === OUTCOME.LOST ? 0 : row.probability })} disabled={checking || lockOutcome}>
                          <SelectTrigger className="h-8 w-[8.5rem] shrink-0 bg-card text-[13px] shadow-xs" aria-label={`What reaching ${row.label || "this stage"} means`} data-testid={`stage-outcome-${row.key}`}><SelectValue /></SelectTrigger>
                          <SelectContent>{Object.values(OUTCOME).map((value) => <SelectItem key={value} value={value} className="text-[13px]">{OUTCOME_LABEL[value]}</SelectItem>)}</SelectContent>
                        </Select>
                        <div className="flex w-[5.5rem] shrink-0 items-center gap-1">
                          <Input type="number" min="0" max="100" value={row.probability} onChange={(event) => update(index, { probability: event.target.value })} aria-label={`Chance a deal in ${row.label || "this stage"} closes, in percent`} className="tabular h-8 w-[4.5rem] px-2.5 text-[13px] md:text-[13px]" disabled={checking || outcome !== OUTCOME.OPEN} data-testid={`stage-probability-${row.key}`} />
                          <span className="text-xs text-muted-foreground">%</span>
                        </div>
                        <Button type="button" variant="ghost" size="sm" onClick={() => remove(index)} disabled={checking || Boolean(removeBlocked)} title={removeBlocked || "Remove this stage"} aria-label={`Remove ${row.label || "this stage"}`} className="size-8 shrink-0 px-0 text-muted-foreground hover:text-red-700" data-testid={`stage-remove-${row.key}`}><Trash2 aria-hidden="true" /></Button>
                      </div>
                    </div>
                    {(hasDeals || forms.length > 0 || row.isNew) && (
                      <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 pl-[2.625rem] text-xs text-muted-foreground">
                        {row.isNew && <span className="font-medium text-brand">New stage</span>}
                        {hasDeals && <span>{dealsText(usage)} here — move them out to remove this stage or change what it means.</span>}
                        {forms.map((form) => <span key={form.id} className="inline-flex items-center gap-1"><Globe className="size-3" aria-hidden="true" />Website form “{form.name}” starts new leads here</span>)}
                      </p>
                    )}
                  </li>
                );
              })}
            </ol>
            <div className="flex gap-2 border-t border-border bg-muted/30 px-3 py-2">
              <div className="relative min-w-0 flex-1">
                <Plus className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
                <Input value={newLabel} onChange={(event) => setNewLabel(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); addStage(); } }} placeholder="New stage, e.g. Showing booked" aria-label="New stage name" maxLength={80} disabled={checking} className="h-8 pl-8 text-[13px] md:text-[13px]" data-testid="stage-new-label" />
              </div>
              <Button type="button" variant="outline" size="sm" onClick={addStage} disabled={checking} data-testid="stage-add">Add stage</Button>
            </div>
          </div>
          <p className="text-xs leading-5 text-muted-foreground">“Chance” is how likely a deal at that stage is to close. It only feeds the weighted estimate; it never changes a deal's value.</p>
          {problem && <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-700" role="alert" data-testid="stage-editor-problem"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />{problem}</div>}
        </div>

        <DialogFooter className="gap-2 border-t border-border bg-muted/30 px-5 py-3 sm:space-x-0">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button size="sm" disabled={saving || checking} onClick={save} data-testid="stage-editor-save">{saving ? "Saving…" : "Save stages"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
