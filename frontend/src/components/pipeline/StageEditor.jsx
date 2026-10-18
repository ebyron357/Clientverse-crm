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
import { OUTCOME, stageKeyFor, stageOutcome } from "@/lib/pipeline";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ArrowDown, ArrowUp, Globe, Plus, Trash2 } from "lucide-react";

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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl" data-testid="stage-editor">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl">Customize stages</DialogTitle>
          <DialogDescription>Rename, reorder, add or remove the steps your deals move through. Renaming a stage keeps its deals and website forms pointing at it.</DialogDescription>
        </DialogHeader>
        <div className="hidden items-center gap-2 px-3 text-[11px] font-bold uppercase tracking-[0.06em] text-slate-500 sm:flex" aria-hidden="true">
          <span className="flex-1 pl-7">Stage</span><span className="w-[8.5rem]">Reaching it means</span><span className="w-[5.5rem]">Chance</span><span className="w-9" />
        </div>
        <ol className="space-y-2" aria-busy={checking}>
          {rows.map((row, index) => {
            const usage = row.isNew ? null : inUse?.[row.key];
            const forms = usage?.website_forms || [];
            const hasDeals = Boolean(usage?.deals);
            const outcome = stageOutcome(row);
            // What the server would refuse, said before anyone tries it.
            const lockOutcome = hasDeals || (forms.length > 0 && originalOutcome[row.key] === OUTCOME.OPEN);
            const removeBlocked = hasDeals ? `Move its ${dealsText(usage)} to another stage first` : forms.length ? `Website form “${forms[0].name}” starts new leads here` : "";
            return (
              <li key={row.key} className="rounded-xl border border-slate-200 bg-white p-3" data-testid={`stage-row-${row.key}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="flex flex-col">
                    <button type="button" onClick={() => move(index, -1)} disabled={checking || index === 0} className="rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-30" aria-label={`Move ${row.label || "this stage"} up`} data-testid={`stage-up-${row.key}`}><ArrowUp className="h-3.5 w-3.5" /></button>
                    <button type="button" onClick={() => move(index, 1)} disabled={checking || index === rows.length - 1} className="rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-30" aria-label={`Move ${row.label || "this stage"} down`} data-testid={`stage-down-${row.key}`}><ArrowDown className="h-3.5 w-3.5" /></button>
                  </div>
                  <Input value={row.label} onChange={(event) => update(index, { label: event.target.value })} aria-label="Stage name" className="h-9 min-w-[10rem] flex-1" maxLength={80} disabled={checking} data-testid={`stage-label-${row.key}`} />
                  <Select value={outcome} onValueChange={(value) => update(index, { ...flagsFor(value), probability: value === OUTCOME.WON ? 100 : value === OUTCOME.LOST ? 0 : row.probability })} disabled={checking || lockOutcome}>
                    <SelectTrigger className="h-9 w-[8.5rem]" aria-label={`What reaching ${row.label || "this stage"} means`} data-testid={`stage-outcome-${row.key}`}><SelectValue /></SelectTrigger>
                    <SelectContent>{Object.values(OUTCOME).map((value) => <SelectItem key={value} value={value}>{OUTCOME_LABEL[value]}</SelectItem>)}</SelectContent>
                  </Select>
                  <div className="flex items-center gap-1">
                    <Input type="number" min="0" max="100" value={row.probability} onChange={(event) => update(index, { probability: event.target.value })} aria-label={`Chance a deal in ${row.label || "this stage"} closes, in percent`} className="h-9 w-[4.5rem]" disabled={checking || outcome !== OUTCOME.OPEN} data-testid={`stage-probability-${row.key}`} />
                    <span className="text-xs text-slate-500">%</span>
                  </div>
                  <Button type="button" variant="ghost" size="sm" onClick={() => remove(index)} disabled={checking || Boolean(removeBlocked)} title={removeBlocked || "Remove this stage"} aria-label={`Remove ${row.label || "this stage"}`} className="h-9 px-2 text-slate-500 hover:text-red-700" data-testid={`stage-remove-${row.key}`}><Trash2 className="h-4 w-4" /></Button>
                </div>
                {(hasDeals || forms.length > 0 || row.isNew) && (
                  <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 pl-7 text-xs text-slate-500">
                    {row.isNew && <span className="font-semibold text-[#0a6177]">New stage</span>}
                    {hasDeals && <span>{dealsText(usage)} here — move them out to remove this stage or change what it means.</span>}
                    {forms.map((form) => <span key={form.id} className="inline-flex items-center gap-1"><Globe className="h-3 w-3" />Website form “{form.name}” starts new leads here</span>)}
                  </p>
                )}
              </li>
            );
          })}
        </ol>
        <div className="flex gap-2">
          <Input value={newLabel} onChange={(event) => setNewLabel(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); addStage(); } }} placeholder="New stage, e.g. Showing booked" aria-label="New stage name" maxLength={80} disabled={checking} data-testid="stage-new-label" />
          <Button type="button" variant="outline" onClick={addStage} disabled={checking} data-testid="stage-add"><Plus className="mr-1.5 h-4 w-4" />Add stage</Button>
        </div>
        <p className="text-xs leading-5 text-slate-500">“Chance” is how likely a deal at that stage is to close. It only feeds the weighted estimate; it never changes a deal's value.</p>
        {problem && <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="alert" data-testid="stage-editor-problem">{problem}</div>}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={saving || checking} onClick={save} className="cv-action-primary" data-testid="stage-editor-save">{saving ? "Saving…" : "Save stages"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
