import { useParams } from "react-router-dom";
import { ArrowRight, Blocks, CheckCircle2, LockKeyhole } from "lucide-react";
import { CLIENTVERSE_MODULES, getModule, MODULE_STATES } from "@/platform/modules";
import { Badge } from "@/components/AppShell";

const STATE_COPY = {
  [MODULE_STATES.CONFIGURATION_REQUIRED]: "Configuration required",
  [MODULE_STATES.CONTRACT_PENDING]: "Backend contract pending",
};

export default function ModuleStatus({ moduleId: moduleIdProp }) {
  const { moduleId: routeModuleId } = useParams();
  const module = getModule(moduleIdProp || routeModuleId);
  if (!module) return null;
  const Icon = module.icon;
  const related = CLIENTVERSE_MODULES.filter((item) => item.group === module.group && item.id !== module.id);

  return <div className="cv-page">
    <div className="cv-page-header">
      <div><div className="cv-eyebrow">Full-platform architecture</div><h1 className="cv-page-title">{module.label}</h1><p className="cv-page-description">{module.description}</p></div>
      <Badge className="border-amber-200 bg-amber-50 text-amber-800">{STATE_COPY[module.state]}</Badge>
    </div>
    <section className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="cv-card overflow-hidden">
        <div className="border-b border-border bg-secondary/50 p-6">
          <span className="flex size-11 items-center justify-center rounded-xl border border-border bg-card text-primary"><Icon className="size-5" /></span>
          <h2 className="mt-5 font-display text-xl font-bold text-foreground">Architectural home established</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">This module is part of the approved ClientVerse product architecture. Its stable route, permissions, navigation identity, and service boundary are reserved now so implementation can activate in place without a shell or information-architecture rewrite.</p>
        </div>
        <div className="flex flex-col gap-4 p-6">
          <ContractRow icon={CheckCircle2} label="Stable module ID" value={module.id} />
          <ContractRow icon={CheckCircle2} label="Route namespace" value={module.route} />
          <ContractRow icon={LockKeyhole} label="Required backend contract" value={module.contract} />
          <div className="rounded-xl border border-dashed border-border bg-secondary/50 p-4 text-sm leading-6 text-muted-foreground">No sample records or simulated writes are shown. This surface becomes operational when its versioned backend contract is implemented and the module state changes to available.</div>
        </div>
      </div>
      <aside className="cv-card p-5">
        <div className="flex items-center gap-2"><Blocks className="size-4 text-primary" /><h2 className="cv-card-title">{module.group} domain</h2></div>
        <p className="cv-card-description">Shared architecture in the same operating domain.</p>
        <div className="mt-4 flex flex-col gap-2">{related.map((item) => <div key={item.id} className="flex items-center gap-3 rounded-xl border border-border p-3"><item.icon className="size-4 shrink-0 text-muted-foreground" /><div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold text-foreground">{item.label}</div><div className="truncate text-xs text-muted-foreground">{item.state.replaceAll("_", " ")}</div></div><ArrowRight className="size-4 text-muted-foreground" /></div>)}</div>
      </aside>
    </section>
  </div>;
}

function ContractRow({ icon: Icon, label, value }) {
  return <div className="flex items-start gap-3"><Icon className="mt-0.5 size-4 shrink-0 text-primary" /><div><div className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{label}</div><div className="mt-1 font-mono text-sm text-foreground">{value}</div></div></div>;
}
