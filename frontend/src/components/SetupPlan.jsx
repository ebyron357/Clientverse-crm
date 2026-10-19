/* What loading a setup (an industry template or a snapshot) adds, keeps and skips, and why.
   The server sends the plan; this lays it out the same way for both, before and after. */

import { Link } from "react-router-dom";
import { AlertTriangle, Check, ChevronRight, Plus } from "lucide-react";

export const KIND = { pipeline: "Pipeline", field: "Field", booking_page: "Booking page", form: "Website form", automation: "Automation", view: "Saved view" };

// Where to go next for each kind of thing that was added.
const NEXT = [
  { kind: "automation", label: "Review the draft automations and turn on the ones you want", to: "/automations" },
  { kind: "form", label: "Put the form on your website", to: "/website-forms" },
  { kind: "booking_page", label: "Share your booking pages", to: "/scheduling/calendar?tab=pages" },
  { kind: "pipeline", label: "See your pipeline", to: "/pipeline" },
  { kind: "field", label: "See the new fields", to: "/settings/fields" },
  { kind: "view", label: "Open the shared views on Contacts", to: "/contacts" },
];

// A plan can run long; its dialog keeps the buttons in view at the bottom of the scroll.
export const STICKY_FOOTER = "sticky -bottom-6 z-10 -mx-6 -mb-6 gap-2 border-t border-border bg-background px-6 py-3 sm:gap-2 sm:rounded-b-lg";

export const countAdds = (items = []) => items.filter((item) => item.action === "add").length;
export const things = (count) => `${count} ${count === 1 ? "thing" : "things"}`;

/**
 * `items` is the plan from the server. `applied` switches the wording from "will" to "did"
 * and shows where to go next. `testid` prefixes each block's test id.
 */
export function SetupPlan({ items = [], applied = false, empty, testid, onNavigate }) {
  const adds = items.filter((item) => item.action === "add");
  const skips = items.filter((item) => item.action === "skip");
  const keeps = items.filter((item) => item.action === "keep");
  const next = applied ? NEXT.filter((step) => adds.some((item) => item.kind === step.kind)) : [];
  return <div className="space-y-4">
    {next.length > 0 && <div className="rounded-lg border border-border bg-muted/30 p-3" data-testid={`${testid}-next-steps`}>
      <h3 className="text-xs font-medium text-muted-foreground">Next</h3>
      <ul className="mt-1.5 space-y-1">{next.map((step) => <li key={step.kind}><Link to={step.to} onClick={onNavigate} className="inline-flex items-center gap-1 text-[13px] font-medium text-brand-strong hover:underline">{step.label}<ChevronRight className="size-3.5" aria-hidden="true" /></Link></li>)}</ul>
    </div>}
    <PlanList title={applied ? `Added (${adds.length})` : `Will add (${adds.length})`} items={adds} icon={Plus} tone="text-brand-strong" empty={empty} testid={`${testid}-plan-add`} />
    {skips.length > 0 && <PlanList title={applied ? `Not loaded (${skips.length})` : `Can't be loaded (${skips.length})`} items={skips} icon={AlertTriangle} tone="text-amber-600 dark:text-amber-400" testid={`${testid}-plan-skip`} />}
    {keeps.length > 0 && <PlanList title={`Already there, left as it is (${keeps.length})`} items={keeps} icon={Check} tone="text-muted-foreground" testid={`${testid}-plan-keep`} />}
  </div>;
}

function PlanList({ title, items, icon: Icon, tone, empty, testid }) {
  return <section data-testid={testid}>
    <h3 className="text-xs font-medium text-muted-foreground">{title}</h3>
    {!items.length ? <p className="mt-1.5 text-[13px] text-muted-foreground">{empty}</p>
      : <ul className="mt-1.5 divide-y divide-border/70 rounded-lg border border-border">{items.map((item, index) => <li key={`${item.kind}-${item.name}-${index}`} className="flex items-start gap-2.5 px-3 py-2 text-[13px]">
          <Icon className={`mt-0.5 size-3.5 shrink-0 ${tone}`} aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <div className="break-words"><span className="text-muted-foreground">{KIND[item.kind] || item.kind}:</span> <span className="font-medium text-foreground">{item.name}</span></div>
            {item.detail && <p className="mt-0.5 break-words text-xs text-muted-foreground">{item.detail}</p>}
          </div>
        </li>)}</ul>}
  </section>;
}
