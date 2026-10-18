/* ClientVerse Systems Command Center: compact, calm activation guidance on neutral work surfaces. */
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, ChevronDown, ChevronRight, X } from "lucide-react";

const STORAGE_KEY = "clientverse:onboarding-dismissed";

function readDismissed() {
  try { return localStorage.getItem(STORAGE_KEY) === "true"; } catch { return false; }
}

export default function OnboardingChecklist({ dashboard, integrations = [] }) {
  const navigate = useNavigate();
  const [dismissed, setDismissed] = useState(readDismissed);
  const [expanded, setExpanded] = useState(true);
  const items = useMemo(() => {
    const providerList = Array.isArray(integrations) ? integrations : (integrations?.providers || []);
    return [
      { label: "Review your command center", detail: "Understand the current revenue, delivery risk, and client-health signals.", complete: true, to: "/dashboard" },
      { label: "Create your first opportunity", detail: "Track a qualified revenue conversation in the pipeline.", complete: Boolean(dashboard?.open_opportunities), to: "/pipeline" },
      { label: "Open a Client 360 workspace", detail: "Bring health, commitments, approvals, and outcomes into one account view.", complete: Boolean(dashboard?.active_workspaces), to: "/workspaces" },
      { label: "Connect a provider", detail: "Bring approved Gmail, Calendar, or Stripe context into the client record.", complete: providerList.some((item) => item.status === "active"), to: "/registries" },
    ];
  }, [dashboard, integrations]);
  const completed = items.filter((item) => item.complete).length;
  const dismiss = () => { try { localStorage.setItem(STORAGE_KEY, "true"); } catch { /* private mode: dismiss for this visit only */ } setDismissed(true); };
  if (dismissed || completed === items.length) return null;
  const percent = Math.round((completed / items.length) * 100);

  return <section className="mt-5 overflow-hidden rounded-xl border border-border bg-card" aria-label="Workspace setup" data-testid="onboarding-checklist">
    <div className="flex items-center gap-3 px-4 py-2.5">
      <div className="flex min-w-0 flex-1 items-baseline gap-2">
        <h2 className="truncate text-sm font-semibold tracking-tight text-foreground">Set up your workspace</h2>
        <span className="tabular shrink-0 text-xs text-muted-foreground">{completed} of {items.length} complete</span>
      </div>
      <div className="hidden h-1 w-32 shrink-0 overflow-hidden rounded-full bg-muted sm:block" role="progressbar" aria-label="Setup progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
        <div className="h-full rounded-full bg-brand" style={{ width: `${percent}%` }} />
      </div>
      <div className="flex shrink-0 items-center">
        <button type="button" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}
          aria-label={expanded ? "Collapse onboarding checklist" : "Expand onboarding checklist"}
          className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
          <ChevronDown className={`size-4 ${expanded ? "rotate-180" : ""}`} aria-hidden="true" />
        </button>
        <button type="button" className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground" onClick={dismiss} aria-label="Dismiss onboarding checklist"><X className="size-4" aria-hidden="true" /></button>
      </div>
    </div>
    {expanded && <ul className="grid grid-cols-1 border-t border-border/70 sm:grid-cols-2">
      {items.map((item, index) => <li key={item.label} className={`flex items-center gap-3 px-4 py-2.5 ${index > 0 ? "border-t border-border/70" : ""} ${index === 1 ? "sm:border-t-0" : ""} sm:odd:border-r`}>
        <span className={`flex size-[18px] shrink-0 items-center justify-center rounded-full ${item.complete ? "border border-emerald-200 bg-emerald-50 text-emerald-700" : "border border-dashed border-input"}`}>
          {item.complete ? <Check className="size-3" strokeWidth={3} aria-hidden="true" /> : null}
          <span className="sr-only">{item.complete ? "Complete:" : "To do:"}</span>
        </span>
        <div className="min-w-0 flex-1">
          <h3 className={`truncate text-[13px] font-medium ${item.complete ? "text-muted-foreground line-through decoration-border" : "text-foreground"}`}>{item.label}</h3>
          <p className="truncate text-xs text-muted-foreground" title={item.detail}>{item.detail}</p>
        </div>
        {!item.complete && <button type="button" onClick={() => navigate(item.to)} className="inline-flex shrink-0 items-center gap-0.5 rounded-md text-xs font-medium text-brand transition-colors hover:text-brand-strong">
          Complete step<ChevronRight className="size-3.5" aria-hidden="true" />
        </button>}
      </li>)}
    </ul>}
  </section>;
}
