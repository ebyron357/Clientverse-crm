/* Settings → Industry template: a starting setup for the kind of business using ClientVerse.
   A template adds a pipeline, booking pages, a website form, fields and draft automations.
   It only ever adds what is missing, so the preview says exactly what it will add and what it
   will leave alone, and an admin applies it from there. */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { api, formatErr } from "@/lib/api";
import { PageHeader } from "@/components/page/Page";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { BarChart3, Briefcase, Check, ChevronRight, Home, LayoutTemplate, Plus, Sparkles, Users, Wrench } from "lucide-react";

const ICONS = { briefcase: Briefcase, home: Home, wrench: Wrench, sparkles: Sparkles, users: Users, chart: BarChart3 };
const TONES = {
  agency: "bg-brand-soft text-brand-strong",
  real_estate: "bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300",
  home_services: "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
  health_wellness: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  coaching: "bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
  b2b_sales: "bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
};
const KIND = { pipeline: "Pipeline", field: "Field", booking_page: "Booking page", form: "Website form", automation: "Automation" };
const SINGULAR = { contacts: "contact", companies: "company", deals: "deal" };
// Where to go next for each kind of thing a template added.
const NEXT = [
  { kind: "automation", label: "Review the draft automations and turn on the ones you want", to: "/automations" },
  { kind: "form", label: "Put the form on your website", to: "/website-forms" },
  { kind: "booking_page", label: "Share your booking pages", to: "/scheduling/calendar?tab=pages" },
  { kind: "field", label: "See the new fields", to: "/settings/fields" },
];

export default function IndustryTemplates() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [state, setState] = useState({ loaded: false, items: [], inUse: null });
  const [chosen, setChosen] = useState(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/industry-templates");
      setState({ loaded: true, items: data.items || [], inUse: data.in_use || null });
    } catch (requestError) {
      setState((current) => ({ ...current, loaded: true }));
      toast.error("Templates could not be loaded", { description: formatErr(requestError.response?.data?.detail) });
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const inUse = state.items.find((item) => item.key === state.inUse);

  return <div className="cv-page">
    <PageHeader icon={LayoutTemplate} title="Industry template"
      description="A starting setup built for your kind of business. Applying one adds only what is missing; nothing you have is changed." />
    {state.loaded && <p className="mt-3 text-[13px] text-muted-foreground" data-testid="template-in-use">
      {inUse ? <>In use: <span className="font-medium text-foreground">{inUse.label}</span>. You can apply another at any time to add what it brings.</> : "No template applied yet. Preview one to see exactly what it adds."}
      {!isAdmin && " Only an admin can apply a template."}
    </p>}
    <div className="mt-4 grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
      {!state.loaded ? [0, 1, 2, 3].map((index) => <Skeleton key={index} className="h-72 rounded-xl" />)
        : state.items.map((template) => <TemplateCard key={template.key} template={template} current={template.key === state.inUse} onPreview={() => setChosen(template)} />)}
    </div>
    {chosen && <PreviewDialog template={chosen} isAdmin={isAdmin} onClose={() => setChosen(null)} onApplied={load} />}
  </div>;
}

function TemplateCard({ template, current, onPreview }) {
  const Icon = ICONS[template.icon] || LayoutTemplate;
  return <article className={`flex flex-col rounded-xl border bg-card p-4 ${current ? "border-brand/60 ring-2 ring-brand/15" : "border-border"}`} data-testid={`template-${template.key}`}>
    <div className="flex items-center gap-3">
      <span className={`flex size-9 shrink-0 items-center justify-center rounded-lg ${TONES[template.key] || "bg-muted text-muted-foreground"}`}><Icon className="size-[18px]" aria-hidden="true" /></span>
      <h2 className="min-w-0 flex-1 text-[15px] font-semibold tracking-tight">{template.label}</h2>
      {current && <span className="rounded-md bg-brand-soft px-1.5 py-0.5 text-[11px] font-semibold text-brand-strong">In use</span>}
    </div>
    <p className="mt-2 text-[13px] leading-5 text-muted-foreground">{template.description}</p>
    <dl className="mt-3 flex-1 space-y-2.5 text-[13px]">
      <div>
        <dt className="text-xs font-medium text-muted-foreground">Pipeline</dt>
        <dd className="mt-1 flex flex-wrap gap-1">{template.stages.map((stage) => <span key={stage} className="rounded-md bg-muted px-1.5 py-0.5 text-[11.5px] text-foreground/80">{stage}</span>)}</dd>
      </div>
      <Line label="Booking pages" value={template.booking_pages.join(", ")} />
      <Line label={`“${template.form}” form asks for`} value={template.form_asks.join(", ")} />
      <Line label="Fields" value={template.fields.map((field) => `${field.label} (${SINGULAR[field.object] || field.object})`).join(", ")} />
      <Line label="Draft automations" value={template.automations.join(", ")} />
    </dl>
    <Button size="sm" variant="outline" className="mt-4 self-start" onClick={onPreview} data-testid={`template-preview-${template.key}`}>
      {current ? "Check what is missing" : "Preview"}<ChevronRight className="size-3.5" aria-hidden="true" />
    </Button>
  </article>;
}

function Line({ label, value }) {
  return <div><dt className="text-xs font-medium text-muted-foreground">{label}</dt><dd className="mt-0.5 text-foreground/80">{value}</dd></div>;
}

function PreviewDialog({ template, isAdmin, onClose, onApplied }) {
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState(null);
  const [applying, setApplying] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    let live = true;
    api.get(`/industry-templates/${template.key}/preview`)
      .then(({ data }) => { if (live) setPlan(data); })
      .catch((requestError) => { if (live) setError(formatErr(requestError.response?.data?.detail)); });
    return () => { live = false; };
  }, [template.key]);

  const apply = async () => {
    setApplying(true);
    try {
      const { data } = await api.post(`/industry-templates/${template.key}/apply`);
      const added = data.items.filter((item) => item.action === "add").length;
      toast.success(`${template.label} applied`, { description: added ? `${added} ${added === 1 ? "thing" : "things"} added. Nothing you had was changed.` : "You already had everything it brings." });
      setResult(data);
      await onApplied();
    } catch (requestError) {
      toast.error("The template was not applied", { description: formatErr(requestError.response?.data?.detail) });
    } finally { setApplying(false); }
  };

  const shown = result || plan;
  const adds = shown?.items.filter((item) => item.action === "add") || [];
  const keeps = shown?.items.filter((item) => item.action === "keep") || [];
  const next = result ? NEXT.filter((step) => adds.some((item) => item.kind === step.kind)) : [];

  return <Dialog open onOpenChange={(value) => !value && onClose()}>
    <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl" data-testid="template-preview-dialog">
      <DialogHeader>
        <DialogTitle>{result ? `${template.label} is set up` : `Apply ${template.label}?`}</DialogTitle>
        <DialogDescription>{result ? "Here is what was added. Automations start as drafts and run only after you turn them on." : "This is exactly what the template will do. It adds only what is missing and changes nothing you already have."}</DialogDescription>
      </DialogHeader>
      {error ? <p className="text-[13px] text-destructive" role="alert">The preview could not be loaded: {error}</p>
        : !shown ? <div className="space-y-2">{[0, 1, 2, 3].map((index) => <Skeleton key={index} className="h-5 w-3/4" />)}</div>
        : <div className="space-y-4">
            {next.length > 0 && <div className="rounded-lg border border-border bg-muted/30 p-3" data-testid="template-next-steps">
              <h3 className="text-xs font-medium text-muted-foreground">Next</h3>
              <ul className="mt-1.5 space-y-1">{next.map((step) => <li key={step.kind}><Link to={step.to} onClick={onClose} className="inline-flex items-center gap-1 text-[13px] font-medium text-brand-strong hover:underline">{step.label}<ChevronRight className="size-3.5" aria-hidden="true" /></Link></li>)}</ul>
            </div>}
            <PlanList title={result ? `Added (${adds.length})` : `Will add (${adds.length})`} items={adds} icon={Plus} tone="text-brand-strong" empty="Nothing: you already have everything this template brings." testid="template-plan-add" />
            {keeps.length > 0 && <PlanList title={`Already there, left as it is (${keeps.length})`} items={keeps} icon={Check} tone="text-muted-foreground" testid="template-plan-keep" />}
          </div>}
      <DialogFooter className="gap-2 sm:gap-2">
        {result ? <Button size="sm" onClick={onClose}>Done</Button> : <>
          <Button size="sm" variant="outline" onClick={onClose} disabled={applying}>Cancel</Button>
          {isAdmin ? <Button size="sm" className="cv-action-primary" onClick={apply} disabled={!plan || applying} data-testid="template-apply">{applying ? "Applying…" : adds.length ? `Add ${adds.length} ${adds.length === 1 ? "thing" : "things"}` : "Mark as in use"}</Button>
            : <span className="self-center text-xs text-muted-foreground">Only an admin can apply a template.</span>}
        </>}
      </DialogFooter>
    </DialogContent>
  </Dialog>;
}

function PlanList({ title, items, icon: Icon, tone, empty, testid }) {
  return <section data-testid={testid}>
    <h3 className="text-xs font-medium text-muted-foreground">{title}</h3>
    {!items.length ? <p className="mt-1.5 text-[13px] text-muted-foreground">{empty}</p>
      : <ul className="mt-1.5 divide-y divide-border/70 rounded-lg border border-border">{items.map((item) => <li key={`${item.kind}-${item.name}`} className="flex items-start gap-2.5 px-3 py-2 text-[13px]">
          <Icon className={`mt-0.5 size-3.5 shrink-0 ${tone}`} aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <div><span className="text-muted-foreground">{KIND[item.kind] || item.kind}:</span> <span className="font-medium text-foreground">{item.name}</span></div>
            {item.detail && <p className="mt-0.5 text-xs text-muted-foreground">{item.detail}</p>}
          </div>
        </li>)}</ul>}
  </section>;
}
