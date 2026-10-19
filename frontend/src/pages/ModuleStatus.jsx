import { Link, useParams } from "react-router-dom";
import { ChevronRight, Info, LockKeyhole } from "lucide-react";
import { CLIENTVERSE_MODULES, getModule, MODULE_STATES } from "@/platform/modules";
import { PageHeader, PropertyList, Section, StatusDot } from "@/components/page/Page";

const STATE_COPY = {
  [MODULE_STATES.AVAILABLE]: "Available",
  [MODULE_STATES.CONFIGURATION_REQUIRED]: "Configuration required",
  [MODULE_STATES.CONTRACT_PENDING]: "Backend contract pending",
};
const STATE_TONE = {
  [MODULE_STATES.AVAILABLE]: "success",
  [MODULE_STATES.CONFIGURATION_REQUIRED]: "warning",
  [MODULE_STATES.CONTRACT_PENDING]: "neutral",
};

function Note({ children, testid, tone = "neutral" }) {
  const tones = {
    neutral: "border-border bg-muted/40 text-muted-foreground",
    brand: "border-brand/20 bg-brand-soft text-brand-strong",
  };
  return <div className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-[13px] leading-5 ${tones[tone]}`} data-testid={testid}>
    <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
    <span>{children}</span>
  </div>;
}

export default function ModuleStatus({ moduleId: moduleIdProp }) {
  const { moduleId: routeModuleId } = useParams();
  const module = getModule(moduleIdProp || routeModuleId);
  if (!module) return null;
  const related = CLIENTVERSE_MODULES.filter((item) => item.group === module.group && item.id !== module.id);

  return (
    <div className="cv-page">
      <PageHeader
        icon={module.icon}
        title={module.label}
        description={module.description}
        actions={<span className="inline-flex h-7 items-center rounded-md border border-amber-200 bg-amber-50 px-2 text-xs font-medium text-amber-800">{STATE_COPY[module.state]}</span>}
      />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-3">
          <Section card title="Module contract" description="Route, permissions and service boundary are reserved; the module activates in place.">
            <PropertyList
              className="px-4"
              items={[
                { label: "Module ID", value: <code className="font-mono text-[12.5px]">{module.id}</code> },
                { label: "Route", value: <code className="font-mono text-[12.5px]">{module.route}</code> },
                { label: "Backend contract", value: <span className="inline-flex items-start gap-1.5"><LockKeyhole className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" /><code className="font-mono text-[12.5px]">{module.contract}</code></span> },
                { label: "State", value: <StatusDot tone={STATE_TONE[module.state] || "neutral"}>{STATE_COPY[module.state] || module.state}</StatusDot> },
              ]}
            />
          </Section>
          <Note testid="module-contract-honesty">
            No sample records or simulated writes are shown. This surface becomes operational when its versioned backend contract is implemented and the module state changes to available.
          </Note>
          {module.group === "Communications" && (
            <Note testid="module-comms-honesty" tone="brand">
              Unified inbox and channel threads are reserved here for architecture honesty. Matched email already surfaces on Client 360 activity when Gmail is connected; a full mocked inbox module is intentionally not fabricated until the Conversation service contract lands.
            </Note>
          )}
          {module.group === "Intelligence" && (
            <Note testid="module-intel-honesty">
              Research and relationship insights keep this route namespace stable. Command Center insights remain the live operating view until recommendation services are available.
            </Note>
          )}
        </div>
        <Section card title={`${module.group} domain`} description="Other modules in the same operating domain." className="self-start overflow-hidden">
          {related.length ? (
            <ul className="divide-y divide-border/70">
              {related.map((item) => (
                <li key={item.id}>
                  <Link to={item.route} className="group flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-muted/50">
                    <item.icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[13px] font-medium text-foreground">{item.label}</div>
                      <StatusDot tone={STATE_TONE[item.state] || "neutral"} className="text-xs text-muted-foreground">{STATE_COPY[item.state] || item.state.replaceAll("_", " ")}</StatusDot>
                    </div>
                    <ChevronRight className="size-4 text-muted-foreground/60 transition-colors group-hover:text-foreground" aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-4 py-3 text-[13px] text-muted-foreground">No other modules in this domain yet.</p>
          )}
        </Section>
      </div>
    </div>
  );
}
