/* Automations: when something happens, do these steps, and stop when the person answers.
   Left, the business's automations; centre, the one being edited (its trigger, conditions,
   steps and stop rules) or its run receipts; right, the guardrails and a test run. Admins edit,
   everyone reads. The engine is backend/automations.py. */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { LIFECYCLE, useFieldDefs } from "@/lib/recordFields";
import { AddFilter, FilterChips, useListFields } from "@/components/ListViews";
import { PageHeader, StatusDot, ViewTabs } from "@/components/page/Page";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  ArrowDown, ArrowUp, Bell, CheckCircle2, CircleAlert, CircleSlash, Clock, FlaskConical, ListChecks, ListTodo, Pencil, Plus,
  ShieldCheck, Sparkles, Tag, Trash2, UserRoundCog, Workflow, Zap,
} from "lucide-react";

const ANY = "__any";
const STATUS = { on: { label: "On", tone: "success" }, off: { label: "Off", tone: "neutral" }, draft: { label: "Draft", tone: "warning" } };
const RUN_STATUS = { completed: ["Completed", "success"], waiting: ["Waiting", "info"], running: ["Running", "brand"], stopped: ["Stopped", "neutral"], failed: ["Failed", "danger"] };
const STEP_ICON = { create_task: ListTodo, set_field: Pencil, add_tag: Tag, assign_owner: UserRoundCog, notify: Bell, wait: Clock };
const STEP_TONE = { create_task: "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300", set_field: "bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300", add_tag: "bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300", assign_owner: "bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300", notify: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300", wait: "bg-muted text-muted-foreground" };
const NEW_STEP = {
  create_task: { type: "create_task", title: "Follow up with {{contact.first_name}}", due_in_minutes: 60, priority: "medium", assign: "record_owner" },
  set_field: { type: "set_field", object: "contact", field: "lifecycle", value: "customer" },
  add_tag: { type: "add_tag", tag: "" },
  assign_owner: { type: "assign_owner", mode: "round_robin", only_if_unowned: true },
  notify: { type: "notify", audience: "owner", message: "" },
  wait: { type: "wait", minutes: 60 * 24 },
};
const UNITS = [["minutes", 1], ["hours", 60], ["days", 1440]];
const PLACEHOLDERS = "{{contact.name}}, {{contact.first_name}}, {{contact.email}}, {{deal.name}}, {{company.name}}";
const FIELD = "text-xs font-medium text-muted-foreground";
const INPUT = "h-8 text-[13px] md:text-[13px]";

const editable = (doc) => ({ name: doc.name, description: doc.description || "", trigger: doc.trigger, conditions: doc.conditions || [], steps: doc.steps || [], stop_rules: doc.stop_rules || [], once_per_contact: Boolean(doc.once_per_contact) });
const splitMinutes = (minutes) => { const [unit, size] = [...UNITS].reverse().find(([, n]) => minutes % n === 0) || UNITS[0]; return { amount: minutes / size, unit }; };
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
function duration(minutes) {
  const { amount, unit } = splitMinutes(Number(minutes) || 0);
  return plural(amount, unit.slice(0, -1));
}
function stepSummary(step) {
  if (step.type === "create_task") return { title: `Create a task: ${step.title || "…"}`, detail: [step.due_in_minutes ? `Due in ${duration(step.due_in_minutes)}` : "Due now", `${step.priority || "medium"} priority`, step.assign === "unassigned" ? "Nobody yet" : step.assign === "specific" ? step.email : "The record's owner"].join(" · ") };
  if (step.type === "set_field") return { title: `Set ${step.object} ${String(step.field || "").replace("custom_fields.", "")}`, detail: `To ${step.value ?? "…"}` };
  if (step.type === "add_tag") return { title: "Add a tag", detail: step.tag || "…" };
  if (step.type === "assign_owner") return { title: "Assign an owner", detail: `${step.mode === "specific" ? step.email : "Round robin across the team"}${step.only_if_unowned !== false ? " · only if nobody owns them" : ""}` };
  if (step.type === "notify") return { title: `Notify ${step.audience === "admins" ? "the admins" : step.audience === "everyone" ? "everyone" : "the owner"}`, detail: step.message || "…" };
  if (step.type === "wait") return { title: duration(step.minutes), detail: "Then the stop rules are checked again" };
  return { title: step.type, detail: "" };
}
const when = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "—");

export default function Automations() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [params, setParams] = useSearchParams();
  const selectedId = params.get("automation");
  const [catalog, setCatalog] = useState(null);
  const [items, setItems] = useState(null);
  const [doc, setDoc] = useState(null);
  const [draft, setDraft] = useState(null);
  const [tab, setTab] = useState("steps");
  const [saving, setSaving] = useState(false);
  const [recipes, setRecipes] = useState(false);
  const [refs, setRefs] = useState({ forms: [], stages: [], pages: [], members: [] });

  const select = useCallback((id) => setParams((p) => { if (id) p.set("automation", id); else p.delete("automation"); return p; }), [setParams]);
  const loadList = useCallback(async () => {
    const { data } = await api.get("/automations");
    setItems(data.items);
    return data.items;
  }, []);
  useEffect(() => {
    Promise.all([api.get("/automations/catalog"), loadList()]).then(([c]) => setCatalog(c.data)).catch((e) => toast.error("Automations could not be loaded", { description: formatErr(e.response?.data?.detail) }));
    Promise.allSettled([api.get("/website-forms"), api.get("/pipelines/default"), api.get("/booking/event-types"), isAdmin ? api.get("/team/members") : Promise.resolve({ data: [] })])
      .then(([f, s, b, m]) => setRefs({ forms: f.value?.data?.items || [], stages: s.value?.data?.stages || [], pages: b.value?.data?.items || [], members: (m.value?.data || []).filter((x) => x.status !== "disabled") }));
  }, [loadList, isAdmin]);
  useEffect(() => { if (items && !selectedId && items.length) select(items[0].id); }, [items, selectedId, select]);
  useEffect(() => {
    if (!selectedId) { setDoc(null); setDraft(null); return; }
    api.get(`/automations/${selectedId}`).then(({ data }) => { setDoc(data); setDraft(editable(data)); }).catch(() => { setDoc(null); setDraft(null); });
  }, [selectedId]);

  const dirty = doc && draft && JSON.stringify(editable(doc)) !== JSON.stringify(draft);
  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.patch(`/automations/${doc.id}`, draft);
      setDoc(data); setDraft(editable(data)); await loadList();
      toast.success("Automation saved", { description: doc.status === "on" ? "New runs use these steps. Runs already under way keep the steps they started with." : undefined });
    } catch (e) { toast.error("Nothing was saved", { description: formatErr(e.response?.data?.detail) }); }
    finally { setSaving(false); }
  };
  const setStatus = async (status) => {
    try {
      const { data } = await api.post(`/automations/${doc.id}/status`, { status });
      setDoc((d) => ({ ...d, status })); await loadList();
      toast.success(status === "on" ? "Automation on" : "Automation off", status === "off" && data.stopped_runs ? { description: `${plural(data.stopped_runs, "waiting run")} stopped.` } : undefined);
    } catch (e) { toast.error("Nothing was changed", { description: formatErr(e.response?.data?.detail) }); }
  };
  const create = async (body) => {
    try {
      const { data } = body.recipe ? await api.post("/automations/from-recipe", body) : await api.post("/automations", body);
      await loadList(); select(data.id); setRecipes(false); setTab("steps");
      toast.success(`Created “${data.name}”`, { description: "It is a draft: review the steps, then turn it on." });
    } catch (e) { toast.error("The automation was not created", { description: formatErr(e.response?.data?.detail) }); }
  };
  const archive = async () => {
    try { await api.delete(`/automations/${doc.id}`); toast.success(`Deleted “${doc.name}”`, { description: "Its run receipts are kept." }); select(null); const left = await loadList(); if (left.length) select(left[0].id); }
    catch (e) { toast.error("Nothing was changed", { description: formatErr(e.response?.data?.detail) }); }
  };

  if (!catalog || !items) return <div className="cv-page"><Skeleton className="h-8 w-48" /><div className="mt-5 grid gap-5 lg:grid-cols-[18rem_minmax(0,1fr)]"><Skeleton className="h-96 rounded-xl" /><Skeleton className="h-[32rem] rounded-xl" /></div></div>;

  return <div className="cv-page">
    <PageHeader icon={Workflow} title="Automations" count={items.length} description="When something happens, do these steps, and stop as soon as the person answers. Every run keeps a receipt."
      actions={isAdmin && <DropdownMenu>
        <DropdownMenuTrigger asChild><Button size="sm" className="cv-action-primary" data-testid="automation-new"><Plus className="size-3.5" />New automation</Button></DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem className="text-[13px]" onSelect={() => setRecipes(true)} data-testid="automation-new-recipe"><Sparkles className="size-3.5" />Start from a recipe</DropdownMenuItem>
          <DropdownMenuItem className="text-[13px]" onSelect={() => create({ name: "New automation", trigger: { event: "lead.received" }, steps: [] })} data-testid="automation-new-blank"><Plus className="size-3.5" />Blank automation</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>} />

    <div className="grid grid-cols-1 gap-5 lg:grid-cols-[17rem_minmax(0,1fr)] xl:grid-cols-[17rem_minmax(0,1fr)_18rem]">
      <aside className="cv-card self-start overflow-hidden" aria-label="Your automations">
        {items.length ? <ul className="divide-y divide-border/70">{items.map((item) => <li key={item.id}>
          <button type="button" onClick={() => { select(item.id); setTab("steps"); }} aria-current={item.id === selectedId ? "true" : undefined} data-testid={`automation-item-${item.id}`}
            className={cn("flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/50", item.id === selectedId && "bg-brand/5 shadow-[inset_3px_0_0_hsl(var(--brand))]")}>
            <span className="min-w-0 flex-1"><span className="block truncate text-[13.5px] font-semibold text-foreground">{item.name}</span>
              <span className="block truncate text-xs text-muted-foreground">{item.trigger_label} · {plural(item.steps.length, "step")}{item.active_runs ? ` · ${item.active_runs} running` : ""}</span></span>
            <StatusDot tone={STATUS[item.status]?.tone}>{STATUS[item.status]?.label || item.status}</StatusDot>
          </button>
        </li>)}</ul> : <div className="px-5 py-8 text-center"><Workflow className="mx-auto size-6 text-muted-foreground" aria-hidden="true" /><p className="mt-2 text-[13px] font-medium">No automations yet</p><p className="mt-1 text-xs text-muted-foreground">Start from a recipe: speed to lead, deal-won onboarding, no-show rebooking and more.</p></div>}
        <div className="border-t border-border/70 p-3"><Button size="sm" variant="outline" className="w-full" onClick={() => setRecipes(true)} disabled={!isAdmin} data-testid="automation-browse-recipes"><Sparkles className="size-3.5" />Browse recipes</Button></div>
        <p className="border-t border-border/70 px-4 py-3 text-xs leading-5 text-muted-foreground">Safe rules and client playbooks are in <Link to="/client-ops" className="font-medium text-brand-strong hover:underline">Client Operations</Link>.</p>
      </aside>

      {doc && draft ? <section className="min-w-0" aria-label={doc.name}>
        <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2">
          {isAdmin ? <Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} aria-label="Automation name" className="h-9 w-auto min-w-[16rem] max-w-full border-transparent bg-transparent px-1 text-lg font-bold shadow-none hover:border-input focus-visible:border-input" data-testid="automation-name" />
            : <h2 className="text-lg font-bold">{doc.name}</h2>}
          <StatusDot tone={STATUS[doc.status]?.tone}>{STATUS[doc.status]?.label}</StatusDot>
          <span className="hidden text-[13px] text-muted-foreground 2xl:inline">{doc.trigger_label}</span>
          <div className="ml-auto flex items-center gap-2">
            {isAdmin && dirty && <Button size="sm" className="cv-action-primary" disabled={saving} onClick={save} data-testid="automation-save">{saving ? "Saving…" : "Save changes"}</Button>}
            {isAdmin && !dirty && (doc.status === "on"
              ? <Button size="sm" variant="outline" onClick={() => setStatus("off")} data-testid="automation-off">Turn off</Button>
              : <Button size="sm" className="bg-emerald-700 text-white hover:bg-emerald-800" onClick={() => setStatus("on")} disabled={!doc.steps.length} data-testid="automation-on">Turn on</Button>)}
            {isAdmin && <Button size="sm" variant="ghost" className="size-8 p-0 text-muted-foreground" onClick={archive} aria-label={`Delete ${doc.name}`} data-testid="automation-delete"><Trash2 className="size-4" /></Button>}
          </div>
        </div>
        <ViewTabs label="Automation" value={tab} onChange={setTab} items={[{ value: "steps", label: "Steps", testid: "automation-tab-steps" }, { value: "runs", label: "Runs", count: doc.runs_total || undefined, testid: "automation-tab-runs" }]} />
        {tab === "steps"
          ? <StepsEditor draft={draft} setDraft={setDraft} catalog={catalog} refs={refs} readOnly={!isAdmin} />
          : <Runs automation={doc} isAdmin={isAdmin} />}
      </section> : <section className="cv-card flex flex-col items-center justify-center px-6 py-16 text-center"><Workflow className="size-7 text-muted-foreground" aria-hidden="true" /><p className="mt-3 text-sm font-medium">Choose an automation, or start one from a recipe</p></section>}

      <aside className="min-w-0 space-y-4 lg:col-start-2 xl:col-start-auto" aria-label="Guardrails and test">
        <section className="cv-card overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border/80 px-4 py-3"><h2 className="text-[15px] font-semibold">Guardrails</h2><span className="rounded-md bg-emerald-50 px-1.5 py-0.5 text-[11px] font-semibold text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">Always on</span></div>
          <ul className="divide-y divide-border/70 text-[13px] leading-5">
            {[[ShieldCheck, "Nothing an automation does leaves ClientVerse: it makes tasks, changes fields, tags and owners, and sends in-app notices. Messages to people go through approved templates."],
              [CircleSlash, "Stop rules are checked before every step, so a run ends the moment someone replies, books or the deal closes."],
              [CheckCircle2, "Each event starts an automation once, and a person has one active run of it at a time."],
              [ListChecks, "Every run keeps a receipt: each step, what it did, and links to what it made."]].map(([Icon, text]) => <li key={text} className="flex gap-2.5 px-4 py-2.5"><Icon className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden="true" /><span>{text}</span></li>)}
          </ul>
        </section>
        {doc && isAdmin && <TestRun automation={doc} dirty={dirty} />}
      </aside>
    </div>
    {recipes && <RecipesDialog recipes={catalog.recipes} onClose={() => setRecipes(false)} onUse={(key) => create({ recipe: key })} />}
  </div>;
}

/* ---------- Steps ---------- */

function Connector({ onAdd, readOnly, catalog, index }) {
  return <div className="flex h-8 items-center justify-center" aria-hidden={readOnly}>
    <span className="h-full w-px bg-border" />
    {!readOnly && <DropdownMenu>
      <DropdownMenuTrigger asChild><button type="button" className="absolute flex size-6 items-center justify-center rounded-full border border-border bg-card text-muted-foreground hover:text-foreground" aria-label={`Add a step after step ${index}`} data-testid={`add-step-${index}`}><Plus className="size-3.5" /></button></DropdownMenuTrigger>
      <DropdownMenuContent align="center">{catalog.steps.map((step) => { const Icon = STEP_ICON[step.type] || Zap; return <DropdownMenuItem key={step.type} className="text-[13px]" onSelect={() => onAdd(step.type)} data-testid={`add-step-${index}-${step.type}`}><Icon className="size-3.5" />{step.label}</DropdownMenuItem>; })}</DropdownMenuContent>
    </DropdownMenu>}
  </div>;
}

function StepsEditor({ draft, setDraft, catalog, refs, readOnly }) {
  const [open, setOpen] = useState(null);
  const { defs } = useFieldDefs("contacts");
  const builtins = useMemo(() => [
    { key: "lifecycle", label: "Lifecycle", kind: "select", options: LIFECYCLE.map((s) => ({ value: s.value, label: s.label })) },
    { key: "email", label: "Email", kind: "text" }, { key: "owner", label: "Owner (email)", kind: "text" },
    { key: "tags", label: "Tags", kind: "list" }, { key: "company_id", label: "Company", kind: "id" },
  ], []);
  const fields = useListFields(builtins, defs);
  const trigger = catalog.triggers.find((t) => t.event === draft.trigger.event);
  const setStep = (index, step) => setDraft({ ...draft, steps: draft.steps.map((s, i) => (i === index ? step : s)) });
  const addStep = (index, type) => { const steps = [...draft.steps]; steps.splice(index, 0, { ...NEW_STEP[type] }); setDraft({ ...draft, steps }); setOpen(index); };
  const move = (index, by) => { const steps = [...draft.steps]; const [s] = steps.splice(index, 1); steps.splice(index + by, 0, s); setDraft({ ...draft, steps }); setOpen(null); };
  const remove = (index) => { setDraft({ ...draft, steps: draft.steps.filter((_, i) => i !== index) }); setOpen(null); };

  return <div className="mt-4 rounded-xl border border-border bg-muted/30 bg-[radial-gradient(hsl(var(--border))_1px,transparent_1px)] p-4 [background-size:16px_16px] sm:p-6" data-testid="automation-steps">
    <div className="mx-auto max-w-2xl">
      <Card icon={Zap} tone="bg-brand/10 text-brand" label="1 · When" title={trigger?.label || "Choose a trigger"} detail={<TriggerDetail trigger={draft.trigger} refs={refs} />} testid="automation-trigger">
        {!readOnly && <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div className="grid gap-1.5"><Label htmlFor="trigger-event" className={FIELD}>What starts it</Label>
            <Select value={draft.trigger.event} onValueChange={(event) => setDraft({ ...draft, trigger: { event } })}><SelectTrigger id="trigger-event" className="h-8 text-[13px]" data-testid="trigger-event"><SelectValue /></SelectTrigger>
              <SelectContent>{catalog.triggers.map((t) => <SelectItem key={t.event} value={t.event}>{t.label}</SelectItem>)}</SelectContent></Select></div>
          {trigger?.subject === "lead" && <RefSelect id="trigger-form" label="From the form" value={draft.trigger.form_id} options={refs.forms.map((f) => [f.id, f.name])} anyLabel="Any form" onChange={(form_id) => setDraft({ ...draft, trigger: { ...draft.trigger, form_id } })} />}
          {draft.trigger.event === "opportunity.stage_changed" && <RefSelect id="trigger-stage" label="Into the stage" value={draft.trigger.stage} options={refs.stages.map((s) => [s.key, s.label])} anyLabel="Any stage" onChange={(stage) => setDraft({ ...draft, trigger: { ...draft.trigger, stage } })} />}
          {trigger?.subject === "appointment" && <RefSelect id="trigger-page" label="On the booking page" value={draft.trigger.booking_page_id} options={refs.pages.map((p) => [p.id, p.name])} anyLabel="Any booking page" onChange={(booking_page_id) => setDraft({ ...draft, trigger: { ...draft.trigger, booking_page_id } })} />}
        </div>}
        <div className="mt-3 border-t border-border/70 pt-3">
          <div className="mb-2 flex items-center gap-2"><span className={FIELD}>Only for people who match</span>{!readOnly && <AddFilter fields={fields} onAdd={(f) => setDraft({ ...draft, conditions: [...draft.conditions, f] })} />}</div>
          {draft.conditions.length ? <FilterChips filters={draft.conditions} fields={fields} onRemove={readOnly ? () => {} : (i) => setDraft({ ...draft, conditions: draft.conditions.filter((_, x) => x !== i) })} onClear={readOnly ? () => {} : () => setDraft({ ...draft, conditions: [] })} />
            : <p className="text-xs text-muted-foreground">Everyone it starts for.</p>}
        </div>
      </Card>

      <div className="relative"><Connector onAdd={(type) => addStep(0, type)} readOnly={readOnly} catalog={catalog} index={0} /></div>
      {draft.steps.map((step, index) => {
        const summary = stepSummary(step);
        const Icon = STEP_ICON[step.type] || Zap;
        return <div key={step.id || index}>
          <Card icon={Icon} tone={STEP_TONE[step.type]} label={`${index + 2} · ${step.type === "wait" ? "Wait" : "Then"}`} title={summary.title} detail={summary.detail}
            onEdit={readOnly ? null : () => setOpen(open === index ? null : index)} editing={open === index} testid={`automation-step-${index}`}
            footer={step.type === "wait" && draft.stop_rules.length > 0 && <span className="mt-2 inline-flex items-center gap-1 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[11.5px] font-semibold text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"><CircleSlash className="size-3" aria-hidden="true" />Stops early if a stop rule is met</span>}>
            {open === index && !readOnly && <StepForm step={step} onChange={(s) => setStep(index, s)} refs={refs} defs={defs} catalog={catalog}
              actions={<div className="flex items-center gap-1">
                <Button size="sm" variant="ghost" className="size-7 p-0" disabled={index === 0} onClick={() => move(index, -1)} aria-label="Move up"><ArrowUp className="size-3.5" /></Button>
                <Button size="sm" variant="ghost" className="size-7 p-0" disabled={index === draft.steps.length - 1} onClick={() => move(index, 1)} aria-label="Move down"><ArrowDown className="size-3.5" /></Button>
                <Button size="sm" variant="ghost" className="h-7 px-2 text-red-700" onClick={() => remove(index)} data-testid={`remove-step-${index}`}><Trash2 className="size-3.5" />Remove</Button>
              </div>} />}
          </Card>
          <div className="relative"><Connector onAdd={(type) => addStep(index + 1, type)} readOnly={readOnly} catalog={catalog} index={index + 1} /></div>
        </div>;
      })}
      {!draft.steps.length && <p className="pb-2 text-center text-[13px] text-muted-foreground">{readOnly ? "No steps yet." : "Add the first step with the + above."}</p>}

      <section className="rounded-xl border border-border bg-card p-4" aria-labelledby="stop-rules-title" data-testid="automation-stop-rules">
        <h3 id="stop-rules-title" className="flex items-center gap-2 text-[14px] font-semibold"><CircleSlash className="size-4 text-emerald-600" aria-hidden="true" />Stop early when</h3>
        <div className="mt-2 grid gap-2">{catalog.stop_rules.map((rule) => <label key={rule.key} className="flex items-start gap-2.5 text-[13px]">
          <Checkbox checked={draft.stop_rules.includes(rule.key)} disabled={readOnly} className="mt-0.5" data-testid={`stop-rule-${rule.key}`}
            onCheckedChange={(on) => setDraft({ ...draft, stop_rules: on ? [...draft.stop_rules, rule.key] : draft.stop_rules.filter((r) => r !== rule.key) })} />
          <span>{rule.label}</span></label>)}</div>
        <p className="mt-2 text-xs text-muted-foreground">A run also stops if the contact is archived or the automation is turned off.</p>
        <div className="mt-3 flex items-center justify-between gap-3 border-t border-border/70 pt-3">
          <Label htmlFor="once-per-contact" className="text-[13px] font-normal">Run once per person, ever <span className="block text-xs text-muted-foreground">Off: again for a later event, once the previous run has ended.</span></Label>
          <Switch id="once-per-contact" checked={draft.once_per_contact} disabled={readOnly} onCheckedChange={(on) => setDraft({ ...draft, once_per_contact: on })} />
        </div>
      </section>
    </div>
  </div>;
}

function TriggerDetail({ trigger, refs }) {
  const parts = [];
  if (trigger.form_id) parts.push(`Form: ${refs.forms.find((f) => f.id === trigger.form_id)?.name || "a form"}`);
  if (trigger.stage) parts.push(`Stage: ${refs.stages.find((s) => s.key === trigger.stage)?.label || trigger.stage}`);
  if (trigger.booking_page_id) parts.push(`Booking page: ${refs.pages.find((p) => p.id === trigger.booking_page_id)?.name || "a page"}`);
  return parts.join(" · ") || "Every time";
}

function Card({ icon: Icon, tone, label, title, detail, onEdit, editing, children, footer, testid }) {
  return <div className={cn("rounded-xl border bg-card p-4 shadow-xs", editing ? "border-brand/60" : "border-border")} data-testid={testid}>
    <div className="flex items-start gap-3">
      <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-lg", tone)}><Icon className="size-4" aria-hidden="true" /></span>
      <div className="min-w-0 flex-1">
        <div className="text-[11px] font-bold uppercase tracking-[0.06em] text-muted-foreground">{label}</div>
        <div className="text-[14px] font-semibold text-foreground">{title}</div>
        {detail && <div className="mt-0.5 text-[12.5px] text-muted-foreground">{detail}</div>}
        {footer}
      </div>
      {onEdit && <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={onEdit} aria-expanded={editing}>{editing ? "Done" : "Edit"}</Button>}
    </div>
    {children}
  </div>;
}

function RefSelect({ id, label, value, options, anyLabel, onChange }) {
  return <div className="grid gap-1.5"><Label htmlFor={id} className={FIELD}>{label}</Label>
    <Select value={value || ANY} onValueChange={(v) => onChange(v === ANY ? null : v)}><SelectTrigger id={id} className="h-8 text-[13px]"><SelectValue /></SelectTrigger>
      <SelectContent><SelectItem value={ANY}>{anyLabel}</SelectItem>{options.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent></Select></div>;
}

function MinutesInput({ id, label, value, onChange, allowZero }) {
  const { amount, unit } = splitMinutes(Number(value) || 0);
  const size = UNITS.find(([u]) => u === unit)[1];
  return <div className="grid gap-1.5"><Label htmlFor={id} className={FIELD}>{label}</Label>
    <div className="flex gap-2"><Input id={id} type="number" min={allowZero ? 0 : 1} className={`${INPUT} w-24`} value={amount} onChange={(e) => onChange(Math.max(allowZero ? 0 : 1, Math.round(Number(e.target.value) || 0)) * size)} />
      <Select value={unit} onValueChange={(u) => onChange(amount * UNITS.find(([x]) => x === u)[1])}><SelectTrigger className="h-8 w-28 text-[13px]" aria-label={`${label} unit`}><SelectValue /></SelectTrigger>
        <SelectContent>{UNITS.map(([u]) => <SelectItem key={u} value={u}>{u}</SelectItem>)}</SelectContent></Select></div></div>;
}

function StepForm({ step, onChange, refs, defs, catalog, actions }) {
  const set = (patch) => onChange({ ...step, ...patch });
  const members = refs.members.map((m) => [m.email, m.name || m.email]);
  const settable = catalog.settable.contact;
  const customField = String(step.field || "").startsWith("custom_fields.") ? defs.find((d) => `custom_fields.${d.key}` === step.field) : null;
  return <div className="mt-3 space-y-3 border-t border-border/70 pt-3">
    {step.type === "create_task" && <>
      <div className="grid gap-1.5"><Label htmlFor={`title-${step.id}`} className={FIELD}>Task</Label><Input id={`title-${step.id}`} className={INPUT} value={step.title} onChange={(e) => set({ title: e.target.value })} data-testid="step-task-title" /><p className="text-[11.5px] text-muted-foreground">You can use {PLACEHOLDERS}.</p></div>
      <div className="grid gap-3 sm:grid-cols-2">
        <MinutesInput id={`due-${step.id}`} label="Due after" value={step.due_in_minutes} onChange={(due_in_minutes) => set({ due_in_minutes })} allowZero />
        <div className="grid gap-1.5"><Label htmlFor={`prio-${step.id}`} className={FIELD}>Priority</Label><Select value={step.priority} onValueChange={(priority) => set({ priority })}><SelectTrigger id={`prio-${step.id}`} className="h-8 text-[13px]"><SelectValue /></SelectTrigger><SelectContent>{["low", "medium", "high"].map((p) => <SelectItem key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</SelectItem>)}</SelectContent></Select></div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="grid gap-1.5"><Label htmlFor={`assign-${step.id}`} className={FIELD}>For</Label><Select value={step.assign} onValueChange={(assign) => set({ assign, email: assign === "specific" ? members[0]?.[0] : undefined })}><SelectTrigger id={`assign-${step.id}`} className="h-8 text-[13px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="record_owner">The record's owner</SelectItem><SelectItem value="unassigned">Nobody yet (everyone sees it)</SelectItem><SelectItem value="specific">A specific person</SelectItem></SelectContent></Select></div>
        {step.assign === "specific" && <RefSelect id={`assignee-${step.id}`} label="Person" value={step.email} options={members} anyLabel="Choose" onChange={(email) => set({ email })} />}
      </div>
    </>}
    {step.type === "set_field" && <div className="grid gap-3 sm:grid-cols-2">
      <div className="grid gap-1.5"><Label htmlFor={`field-${step.id}`} className={FIELD}>Contact field</Label><Select value={step.field} onValueChange={(field) => set({ field, value: field === "lifecycle" ? "customer" : settable[field]?.[0] ?? "" })}><SelectTrigger id={`field-${step.id}`} className="h-8 text-[13px]"><SelectValue /></SelectTrigger>
        <SelectContent>{Object.keys(settable).map((f) => <SelectItem key={f} value={f}>{f === "sentiment" ? "Relationship" : f[0].toUpperCase() + f.slice(1)}</SelectItem>)}{defs.map((d) => <SelectItem key={d.key} value={`custom_fields.${d.key}`}>{d.label}</SelectItem>)}</SelectContent></Select></div>
      {settable[step.field] ? <RefSelect id={`value-${step.id}`} label="Value" value={step.value} options={settable[step.field].map((v) => [v, LIFECYCLE.find((s) => s.value === v)?.label || v])} anyLabel="Choose" onChange={(value) => set({ value })} />
        : customField?.type === "select" ? <RefSelect id={`value-${step.id}`} label="Value" value={step.value} options={(customField.options || []).map((o) => [o, o])} anyLabel="Choose" onChange={(value) => set({ value })} />
          : <div className="grid gap-1.5"><Label htmlFor={`value-${step.id}`} className={FIELD}>Value</Label><Input id={`value-${step.id}`} className={INPUT} value={step.value ?? ""} onChange={(e) => set({ value: e.target.value })} /></div>}
    </div>}
    {step.type === "add_tag" && <div className="grid gap-1.5"><Label htmlFor={`tag-${step.id}`} className={FIELD}>Tag</Label><Input id={`tag-${step.id}`} className={INPUT} value={step.tag} onChange={(e) => set({ tag: e.target.value })} placeholder="e.g. vip" /></div>}
    {step.type === "assign_owner" && <div className="grid gap-3 sm:grid-cols-2">
      <div className="grid gap-1.5"><Label htmlFor={`mode-${step.id}`} className={FIELD}>Who</Label><Select value={step.mode} onValueChange={(mode) => set({ mode, email: mode === "specific" ? members[0]?.[0] : undefined })}><SelectTrigger id={`mode-${step.id}`} className="h-8 text-[13px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="round_robin">Round robin across the team</SelectItem><SelectItem value="specific">A specific person</SelectItem></SelectContent></Select></div>
      {step.mode === "specific" && <RefSelect id={`owner-${step.id}`} label="Person" value={step.email} options={members} anyLabel="Choose" onChange={(email) => set({ email })} />}
      <div className="flex items-center gap-2 sm:col-span-2"><Checkbox id={`unowned-${step.id}`} checked={step.only_if_unowned !== false} onCheckedChange={(on) => set({ only_if_unowned: on === true })} /><Label htmlFor={`unowned-${step.id}`} className="text-[13px] font-normal">Only if nobody owns them yet</Label></div>
    </div>}
    {step.type === "notify" && <>
      <div className="grid gap-1.5 sm:w-1/2"><Label htmlFor={`aud-${step.id}`} className={FIELD}>Who</Label><Select value={step.audience} onValueChange={(audience) => set({ audience })}><SelectTrigger id={`aud-${step.id}`} className="h-8 text-[13px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="owner">The record's owner</SelectItem><SelectItem value="admins">The admins</SelectItem><SelectItem value="everyone">Everyone on the team</SelectItem></SelectContent></Select></div>
      <div className="grid gap-1.5"><Label htmlFor={`msg-${step.id}`} className={FIELD}>Message</Label><Textarea id={`msg-${step.id}`} rows={2} className="text-[13px]" value={step.message} onChange={(e) => set({ message: e.target.value })} /><p className="text-[11.5px] text-muted-foreground">An in-app notice. You can use {PLACEHOLDERS}.</p></div>
    </>}
    {step.type === "wait" && <MinutesInput id={`wait-${step.id}`} label="Wait for" value={step.minutes} onChange={(minutes) => set({ minutes })} />}
    <div className="flex justify-end">{actions}</div>
  </div>;
}

/* ---------- Runs ---------- */

function Runs({ automation, isAdmin }) {
  const [data, setData] = useState(null);
  const [openRun, setOpenRun] = useState(null);
  const load = useCallback(() => api.get(`/automations/${automation.id}/runs`).then(({ data: d }) => setData(d)).catch(() => setData({ items: [], counts: {} })), [automation.id]);
  useEffect(() => { load(); }, [load]);
  const stop = async (run) => {
    try { await api.post(`/automation-runs/${run.id}/stop`); toast.success("Run stopped"); load(); }
    catch (e) { toast.error("The run was not stopped", { description: formatErr(e.response?.data?.detail) }); }
  };
  if (!data) return <Skeleton className="mt-4 h-64 rounded-xl" />;
  const counts = Object.entries(data.counts || {}).map(([k, n]) => `${n} ${RUN_STATUS[k]?.[0].toLowerCase() || k}`).join(" · ");
  return <div className="mt-4" data-testid="automation-runs">
    {counts && <p className="mb-2 text-xs text-muted-foreground">{counts}</p>}
    {data.items.length ? <ul className="cv-card divide-y divide-border/70 overflow-hidden">{data.items.map((run) => {
      const [label, tone] = RUN_STATUS[run.status] || [run.status, "neutral"];
      const expanded = openRun === run.id;
      return <li key={run.id}>
        <button type="button" onClick={() => setOpenRun(expanded ? null : run.id)} aria-expanded={expanded} className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-muted/50" data-testid={`run-${run.id}`}>
          <StatusDot tone={tone} className="w-24 shrink-0">{label}</StatusDot>
          <span className="min-w-0 flex-1"><span className="block truncate text-[13px] font-semibold">{run.contact_name || "No contact"}</span>
            <span className="block truncate text-xs text-muted-foreground">{run.stop_reason ? `Stopped: ${run.stop_reason}` : run.error ? `Failed: ${run.error}` : run.status === "waiting" ? `Next step ${when(run.resume_at)}` : `${plural(run.receipt.length, "step")}`}</span></span>
          <span className="tabular shrink-0 text-xs text-muted-foreground">{when(run.created_at)}</span>
        </button>
        {expanded && <div className="border-t border-border/70 bg-muted/20 px-4 py-3">
          <ol className="space-y-2" aria-label="Receipt">{run.receipt.map((entry) => <li key={`${entry.index}-${entry.status}`} className="flex gap-2.5 text-[13px]">
            {entry.status === "failed" ? <CircleAlert className="mt-0.5 size-4 shrink-0 text-red-600" aria-hidden="true" /> : entry.status === "waiting" ? <Clock className="mt-0.5 size-4 shrink-0 text-sky-600" aria-hidden="true" /> : entry.status === "skipped" ? <CircleSlash className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" /> : <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden="true" />}
            <span className="min-w-0 flex-1"><span className="font-medium">{entry.label}</span><span className="block text-xs text-muted-foreground">{entry.detail} · {when(entry.at)}</span>
              {entry.links?.task_id && <Link to={`/tasks?task=${entry.links.task_id}`} className="text-xs font-medium text-brand-strong hover:underline">Open the task</Link>}</span>
          </li>)}</ol>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            <span>Trigger: {run.trigger_label} · version {run.automation_version}</span>
            {run.contact_id && <Link to={`/contacts?contact=${run.contact_id}`} className="font-medium text-brand-strong hover:underline">Open the contact</Link>}
            {run.deal_id && <Link to={`/deals?deal=${run.deal_id}`} className="font-medium text-brand-strong hover:underline">Open the deal</Link>}
            {isAdmin && ["running", "waiting"].includes(run.status) && <Button size="sm" variant="outline" className="ml-auto h-7" onClick={() => stop(run)} data-testid={`run-stop-${run.id}`}>Stop this run</Button>}
          </div>
        </div>}
      </li>;
    })}</ul> : <div className="cv-card px-6 py-10 text-center text-[13px] text-muted-foreground"><ListChecks className="mx-auto mb-2 size-5" aria-hidden="true" />No runs yet. {automation.status === "on" ? "The next matching event starts one." : "Turn the automation on to start runs."}</div>}
  </div>;
}

/* ---------- Test run and recipes ---------- */

function TestRun({ automation, dirty }) {
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (query.trim().length < 2) { setMatches([]); return undefined; }
    const timer = setTimeout(() => api.get("/contacts", { params: { q: query.trim(), limit: 6 } }).then(({ data }) => setMatches(data)).catch(() => setMatches([])), 250);
    return () => clearTimeout(timer);
  }, [query]);
  const run = async (contact) => {
    setBusy(true); setMatches([]); setQuery(contact.name);
    try { const { data } = await api.post(`/automations/${automation.id}/test`, { record_type: "contact", record_id: contact.id }); setResult(data); }
    catch (e) { toast.error("The test did not run", { description: formatErr(e.response?.data?.detail) }); }
    finally { setBusy(false); }
  };
  return <section className="cv-card overflow-hidden" data-testid="automation-test">
    <div className="border-b border-border/80 px-4 py-3"><h2 className="flex items-center gap-2 text-[15px] font-semibold"><FlaskConical className="size-4 text-brand" aria-hidden="true" />Test with a contact</h2>
      <p className="mt-0.5 text-xs text-muted-foreground">Shows what each step would do. Nothing is changed.{dirty ? " Uses the saved steps: save first to test your changes." : ""}</p></div>
    <div className="relative p-4">
      <Input value={query} onChange={(e) => { setQuery(e.target.value); setResult(null); }} placeholder="Search contacts…" aria-label="Search contacts to test with" className={INPUT} data-testid="automation-test-search" />
      {matches.length > 0 && <ul className="absolute inset-x-4 top-[3.25rem] z-10 rounded-lg border border-border bg-popover py-1 shadow-md">{matches.map((c) => <li key={c.id}><button type="button" onClick={() => run(c)} className="w-full px-3 py-1.5 text-left text-[13px] hover:bg-muted" data-testid={`automation-test-pick-${c.id}`}>{c.name}<span className="ml-1.5 text-xs text-muted-foreground">{c.email}</span></button></li>)}</ul>}
      {busy && <p className="mt-3 text-xs text-muted-foreground">Testing…</p>}
      {result && <div className="mt-3" data-testid="automation-test-result">{result.matches
        ? <ol className="space-y-2">{result.steps.map((s) => <li key={s.index} className="text-[13px]"><span className="font-medium">{s.index + 2}. {s.label}</span><span className="block text-xs text-muted-foreground">{s.detail}</span></li>)}</ol>
        : <p className="text-[13px] text-muted-foreground">{result.reason}</p>}</div>}
    </div>
  </section>;
}

function RecipesDialog({ recipes, onClose, onUse }) {
  return <Dialog open onOpenChange={(value) => !value && onClose()}>
    <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
      <DialogHeader><DialogTitle>Start from a recipe</DialogTitle><DialogDescription>Each becomes a draft you can change before turning it on.</DialogDescription></DialogHeader>
      <div className="grid gap-3 sm:grid-cols-2">{recipes.map((r) => <div key={r.key} className="flex flex-col rounded-xl border border-border p-4" data-testid={`recipe-${r.key}`}>
        <h3 className="text-[14px] font-semibold">{r.name}</h3>
        <p className="mt-1 text-[12.5px] text-muted-foreground">{r.description}</p>
        <ol className="mt-2 flex-1 space-y-0.5 text-xs text-foreground/80"><li className="font-medium">When: {r.trigger}</li>{r.steps.map((s, i) => <li key={`${r.key}-${i}`}>{i + 1}. {s}</li>)}</ol>
        <Button size="sm" variant="outline" className="mt-3 self-start" onClick={() => onUse(r.key)} data-testid={`recipe-use-${r.key}`}>Use this</Button>
      </div>)}</div>
    </DialogContent>
  </Dialog>;
}
