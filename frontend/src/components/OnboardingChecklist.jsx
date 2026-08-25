/* ClientVerse Systems Command Center: compact, calm activation guidance on neutral work surfaces. */
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, ChevronDown, ChevronUp, Circle, Sparkles, X } from "lucide-react";
import { Button } from "@/components/ui/button";

const STORAGE_KEY = "clientverse:onboarding-dismissed";

export default function OnboardingChecklist({ dashboard, integrations = [] }) {
  const navigate = useNavigate();
  const [dismissed, setDismissed] = useState(() => localStorage.getItem(STORAGE_KEY) === "true");
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
  const dismiss = () => { localStorage.setItem(STORAGE_KEY, "true"); setDismissed(true); };
  if (dismissed || completed === items.length) return null;
  return <section className="cv-card mt-5 overflow-hidden"><div className="flex items-start justify-between gap-4 border-b border-slate-100 bg-gradient-to-r from-cyan-50/80 to-white px-5 py-4"><div className="flex gap-3"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#1a9fbf] text-white"><Sparkles className="h-4 w-4" /></span><div><h2 className="cv-card-title">Set up your client operations workspace</h2><p className="cv-card-description">{completed} of {items.length} activation steps complete. Finish the essentials, then dismiss this guide.</p></div></div><div className="flex items-center gap-1"><button className="rounded-lg p-2 text-slate-400 hover:bg-white hover:text-slate-700" onClick={() => setExpanded((value) => !value)} aria-label={expanded ? "Collapse onboarding checklist" : "Expand onboarding checklist"}>{expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}</button><button className="rounded-lg p-2 text-slate-400 hover:bg-white hover:text-slate-700" onClick={dismiss} aria-label="Dismiss onboarding checklist"><X className="h-4 w-4" /></button></div></div>{expanded && <div className="grid divide-y divide-slate-100 sm:grid-cols-2 sm:divide-x sm:divide-y-0">{items.map((item) => <div key={item.label} className="flex gap-3 p-4"><span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${item.complete ? "bg-emerald-500 text-white" : "border border-slate-300 text-slate-300"}`}>{item.complete ? <Check className="h-3.5 w-3.5" /> : <Circle className="h-2.5 w-2.5" />}</span><div className="min-w-0 flex-1"><h3 className="text-sm font-semibold text-[#132038]">{item.label}</h3><p className="mt-1 text-xs leading-5 text-slate-500">{item.detail}</p>{!item.complete && <Button size="sm" variant="link" className="mt-1 h-auto px-0 text-[#1a9fbf]" onClick={() => navigate(item.to)}>Complete step</Button>}</div></div>)}</div>}</section>;
}
