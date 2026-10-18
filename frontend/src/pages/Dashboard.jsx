import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { money, formatMoneyByCurrency } from "@/lib/api";
import { commandCenterService } from "@/lib/services";
import OnboardingChecklist from "@/components/OnboardingChecklist";
import CommandCenterInsights from "@/components/CommandCenterInsights";
import NextBestActions from "@/components/NextBestActions";
import { PageHeader, StatStrip, StatusDot, Section, Avatar } from "@/components/page/Page";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertTriangle, ArrowRight, BriefcaseBusiness, CheckCircle2, ChevronRight, CircleAlert,
  ClipboardCheck, GitBranch, LayoutDashboard, RefreshCw, TrendingUp,
} from "lucide-react";

const STAGE_LABELS = { lead: "Lead", qualified: "Qualified", proposal: "Proposal", negotiation: "Negotiation", closed_won: "Won", closed_lost: "Lost" };
const ICON_TONE = { amber: "text-amber-600", red: "text-red-600", emerald: "text-emerald-600", cyan: "text-brand" };
const BAND_TONE = { healthy: "success", at_risk: "warning", critical: "danger" };
const sentence = (value) => { const text = String(value || "").replace(/_/g, " "); return text.charAt(0).toUpperCase() + text.slice(1); };
const BAND_BAR = { healthy: "bg-emerald-500", at_risk: "bg-amber-500", critical: "bg-red-500" };

/** Small count chip that sits beside a section title. */
function Count({ children }) {
  return <span className="tabular rounded-md bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">{children}</span>;
}

/** Quiet text link used as a section action ("Open pipeline"). */
function SectionLink({ onClick, children }) {
  return <button type="button" onClick={onClick} className="inline-flex items-center gap-0.5 rounded-md text-xs font-medium text-muted-foreground transition-colors hover:text-foreground">
    {children}<ChevronRight className="size-3.5" aria-hidden="true" />
  </button>;
}

/** Centred empty state for a list or panel. */
function EmptyState({ icon: Icon, title, description, action, testid, className = "", iconClassName = "bg-muted text-muted-foreground" }) {
  return <div className={`flex flex-col items-center justify-center px-6 py-12 text-center ${className}`} data-testid={testid}>
    <span className={`flex size-10 items-center justify-center rounded-full ${iconClassName}`}><Icon className="size-[18px]" aria-hidden="true" /></span>
    <p className="mt-3 text-sm font-medium text-foreground">{title}</p>
    {description && <p className="mt-1 max-w-sm text-[13px] leading-5 text-muted-foreground">{description}</p>}
    {action && <div className="mt-4">{action}</div>}
  </div>;
}

function HealthBar({ score, band }) {
  return <div className="h-1 w-20 overflow-hidden rounded-full bg-muted"><div className={`h-full rounded-full ${BAND_BAR[band] || BAND_BAR.critical}`} style={{ width: `${Math.max(0, Math.min(score, 100))}%` }} /></div>;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [system, setSystem] = useState({ alerts: [], integrations: [] });
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    const [dashboard, alerts, integrations] = await Promise.allSettled([
      commandCenterService.getPortfolio(), commandCenterService.getAlerts(), commandCenterService.getIntegrationHealth(),
    ]);
    if (dashboard.status !== "fulfilled") { setError("We could not load your command center. Check your connection and try again."); return; }
    setData(dashboard.value);
    setSystem({ alerts: alerts.status === "fulfilled" ? alerts.value : [], integrations: integrations.status === "fulfilled" ? integrations.value : [] });
  }, []);

  useEffect(() => { load(); }, [load]);

  const funnelData = useMemo(() => data ? Object.entries(data.funnel || {}).filter(([key]) => key !== "closed_lost").map(([key, value]) => ({ name: STAGE_LABELS[key] || key, count: value, key })) : [], [data]);
  const priorityItems = useMemo(() => {
    if (!data) return [];
    const items = [];
    const alertList = Array.isArray(system.alerts) ? system.alerts : (system.alerts?.alerts || []);
    const openAlerts = alertList.filter((alert) => alert.status !== "resolved" && alert.status !== "acknowledged");
    const workspaceAlerts = openAlerts.filter((alert) => alert.workspace_id);
    if (data.at_risk_commitments) items.push({ rank: 1, icon: AlertTriangle, title: `Review ${data.at_risk_commitments} at-risk commitment${data.at_risk_commitments === 1 ? "" : "s"}`, body: "Confirm an owner, due date, or recovery step before the next touchpoint.", source: "Commitment status is at risk or breached", to: "/workspaces", tone: "amber" });
    if (workspaceAlerts.length) {
      const first = workspaceAlerts[0];
      items.push({ rank: 2, icon: CircleAlert, title: first.summary || `Triage ${workspaceAlerts.length} workspace risk signal${workspaceAlerts.length === 1 ? "" : "s"}`, body: "Open the linked Client 360 and resolve the underlying evidence.", source: first.type || "Open operational alert", to: first.workspace_id ? `/workspaces/${first.workspace_id}` : "/notifications", tone: "red" });
    } else if (openAlerts.length) {
      items.push({ rank: 2, icon: CircleAlert, title: `Resolve ${openAlerts.length} open risk signal${openAlerts.length === 1 ? "" : "s"}`, body: "Acknowledge the signal and assign follow-through in Action Center.", source: "Open operational alerts require a human decision", to: "/notifications", tone: "red" });
    }
    const integrationList = Array.isArray(system.integrations) ? system.integrations : (system.integrations?.providers || []);
    const degraded = integrationList.filter((integration) => ["degraded", "expired", "error"].includes(integration.status));
    if (degraded.length) items.push({ rank: 3, icon: CircleAlert, title: `Restore ${degraded.length} provider connection${degraded.length === 1 ? "" : "s"}`, body: "Reconnect or investigate before relationship context becomes stale.", source: "Provider health is degraded, expired, or in error", to: "/registries", tone: "red" });
    if ((data.open_opportunities || 0) > 0) items.push({ rank: 4, icon: TrendingUp, title: `Advance ${data.open_opportunities} open opportunit${data.open_opportunities === 1 ? "y" : "ies"}`, body: "Move staged deals forward or close stale opportunities.", source: "Open pipeline opportunities", to: "/pipeline", tone: "cyan" });
    const atRiskHealth = (data.portfolio || []).filter((row) => row.health?.band && row.health.band !== "healthy").slice(0, 1);
    if (atRiskHealth.length) {
      const row = atRiskHealth[0];
      items.push({ rank: 5, icon: BriefcaseBusiness, title: `Stabilize ${row.name}`, body: `Health band is ${row.health.band.replace("_", " ")} — review factors and commitments.`, source: "Explainable client health", to: `/workspaces/${row.id}`, tone: "amber" });
    }
    return items.slice(0, 5);
  }, [data, system]);

  if (error) return <div className="cv-page">
    <PageHeader icon={LayoutDashboard} title="Command Center" />
    <div className="rounded-xl border border-border bg-card" role="alert"><EmptyState icon={CircleAlert} title="Command Center unavailable" description={error} iconClassName="bg-red-50 text-red-600"
      action={<Button size="sm" onClick={load}><RefreshCw className="size-3.5" />Try again</Button>} /></div>
  </div>;
  if (!data) return <DashboardSkeleton />;

  const wonPositive = (data.won_value_by_currency ? Object.values(data.won_value_by_currency).some((value) => value > 0) : (data.won_value || 0) > 0);
  const funnelMax = Math.max(1, ...funnelData.map((row) => row.count || 0));
  const goals = (data.goal_rollup?.workspaces || []).flatMap((workspace) => workspace.goals.map((goal) => ({ ...goal, workspaceName: workspace.name, workspaceId: workspace.id }))).slice(0, 4);

  return <div className="cv-page">
    <PageHeader icon={LayoutDashboard} title="Command Center" testid="dashboard-header"
      description="Revenue, delivery risk and the client relationships that need your team next."
      actions={<>
        <Button variant="outline" size="sm" onClick={load}><RefreshCw className="size-3.5" />Refresh</Button>
        <Button size="sm" onClick={() => navigate("/pipeline")}>Review pipeline<ArrowRight className="size-3.5" /></Button>
      </>} />

    <section aria-label="Key portfolio metrics">
      {/* Per currency, never summed across currencies; the scalar is only a fallback for an older API. */}
      <StatStrip items={[
        { label: "Open pipeline", value: data.pipeline_value_by_currency ? formatMoneyByCurrency(data.pipeline_value_by_currency) : money(data.pipeline_value), detail: `${data.open_opportunities} active opportunit${data.open_opportunities === 1 ? "y" : "ies"}${(data.currencies || []).length > 1 ? " · shown per currency" : ""}`, onClick: () => navigate("/pipeline"), testid: "metric-open-pipeline" },
        { label: "Won revenue", value: data.won_value_by_currency ? formatMoneyByCurrency(data.won_value_by_currency) : money(data.won_value), detail: "Closed-won deals", tone: wonPositive ? "success" : undefined, onClick: () => navigate("/pipeline"), testid: "metric-won-revenue" },
        { label: "Active clients", value: data.active_workspaces, detail: "Workspaces in delivery", onClick: () => navigate("/workspaces"), testid: "metric-active-clients" },
        { label: "Delivery risk", value: data.at_risk_commitments, detail: "At risk or overdue", tone: data.at_risk_commitments ? "warning" : undefined, onClick: () => navigate("/workspaces"), testid: "metric-delivery-risk" },
      ]} />
    </section>

    <OnboardingChecklist dashboard={data} integrations={system.integrations} />

    <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
      <div className="min-w-0 space-y-6 xl:col-span-2">
        <Section title={<span className="flex items-center gap-2">Next actions{priorityItems.length > 0 && <Count>{priorityItems.length}</Count>}</span>}
          testid="dashboard-priority-panel" className="min-w-0">
          <div className="overflow-hidden rounded-xl border border-border bg-card" aria-label="Priority next actions" role="region">
            {priorityItems.length ? priorityItems.map((item, index) => {
              const Icon = item.icon;
              return <button key={index} type="button" onClick={() => navigate(item.to)} data-testid={`priority-action-${index}`}
                className="group flex w-full items-center gap-3 border-b border-border/70 px-4 py-2.5 text-left transition-colors last:border-0 hover:bg-muted/50">
                <span className="tabular w-3 shrink-0 text-center text-xs font-medium text-muted-foreground">{index + 1}</span>
                <span className="flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-background"><Icon className={`size-3.5 ${ICON_TONE[item.tone] || ICON_TONE.cyan}`} aria-hidden="true" /></span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium text-foreground">{item.title}</span>
                  <span className="block truncate text-xs text-muted-foreground">{item.body}</span>
                  <span className="mt-0.5 block truncate text-[11px] text-muted-foreground md:hidden">Source: {item.source}</span>
                </span>
                <span className="hidden max-w-[15rem] shrink-0 truncate text-[11px] text-muted-foreground md:block" title={item.source}>{item.source}</span>
                <ChevronRight className="size-4 shrink-0 text-muted-foreground/70 transition-colors group-hover:text-foreground" aria-hidden="true" />
              </button>;
            }) : <EmptyState icon={CheckCircle2} title="All clear for now" testid="priority-empty"
              description="No urgent commitment, alert, or integration risks."
              action={<Button size="sm" variant="outline" onClick={() => navigate("/workspaces")}>Browse workspaces</Button>} />}
          </div>
        </Section>

        <Section title="Next best actions" testid="command-center-nba" className="min-w-0"
          actions={<SectionLink onClick={() => navigate("/operations")}>Open operations</SectionLink>}>
          <NextBestActions limit={8} compact title="Ranked across all clients"
            onNavigate={(item) => navigate(`/workspaces/${item.workspace_id}`)} />
        </Section>

        <Section title={<span className="flex items-center gap-2">Client health{data.portfolio?.length > 0 && <Count>{data.portfolio.length}</Count>}</span>} className="min-w-0"
          actions={<SectionLink onClick={() => navigate("/workspaces")}>View all clients</SectionLink>}>
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            {data.portfolio?.length ? data.portfolio.map((portfolio) => <button key={portfolio.id} type="button" onClick={() => navigate(`/workspaces/${portfolio.id}`)}
              className="group flex w-full items-center gap-3 border-b border-border/70 px-4 py-2.5 text-left transition-colors last:border-0 hover:bg-muted/50">
              <Avatar name={portfolio.name} size="sm" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-medium text-foreground">{portfolio.name}</span>
                <span className="block truncate text-xs capitalize text-muted-foreground">{portfolio.stage} workspace</span>
              </span>
              <span className="hidden items-center gap-2.5 sm:flex"><HealthBar score={portfolio.health.score} band={portfolio.health.band} /><span className="tabular w-6 text-right text-[13px] font-medium text-foreground">{portfolio.health.score}</span></span>
              <span className="w-20 shrink-0"><StatusDot tone={BAND_TONE[portfolio.health.band] || "danger"}>{sentence(portfolio.health.band)}</StatusDot></span>
              <ChevronRight className="size-4 shrink-0 text-muted-foreground/70 transition-colors group-hover:text-foreground" aria-hidden="true" />
            </button>) : <EmptyState icon={BriefcaseBusiness} title="No client workspaces yet" description="Close an opportunity or create a workspace to begin tracking client health." />}
          </div>
        </Section>
      </div>

      <div className="min-w-0 space-y-6">
        <div className="grid grid-cols-1 items-start gap-6 md:grid-cols-2 xl:grid-cols-1">
          <Section title="Pipeline by stage" actions={<SectionLink onClick={() => navigate("/pipeline")}>Open pipeline</SectionLink>}>
            <div className="rounded-xl border border-border bg-card px-4 py-3">
              {funnelData.length ? <ul aria-label="Opportunity count by pipeline stage" className="space-y-1">
                {funnelData.map((row) => <li key={row.key} className="grid h-7 grid-cols-[5.5rem_minmax(0,1fr)_2rem] items-center gap-3 text-[13px]" title={`${row.name}: ${row.count}`}>
                  <span className="truncate text-muted-foreground">{row.name}</span>
                  <span className="h-2 overflow-hidden rounded-full bg-muted/70" aria-hidden="true">
                    <span className={`block h-full rounded-full ${row.key === "closed_won" ? "bg-emerald-500" : "bg-brand"}`} style={{ width: `${((row.count || 0) / funnelMax) * 100}%` }} />
                  </span>
                  <span className="tabular text-right font-medium text-foreground">{row.count}</span>
                </li>)}
              </ul> : <EmptyState icon={GitBranch} title="Your pipeline starts here" description="Create the first opportunity to begin tracking revenue movement." className="py-8"
                action={<Button size="sm" variant="outline" onClick={() => navigate("/pipeline")}>Create opportunity</Button>} />}
            </div>
          </Section>

          <Section title="Outcome momentum">
            <div className="rounded-xl border border-border bg-card">
              {data.goal_rollup?.total_goals > 0 ? <>
                <div className="flex items-end justify-between gap-3 border-b border-border/70 px-4 py-3">
                  <div>
                    <div className="tabular text-[22px] font-semibold leading-7 tracking-tight text-foreground">{data.goal_rollup.avg_progress}%</div>
                    <div className="text-xs text-muted-foreground">Average outcome progress</div>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <StatusDot tone="success">{data.goal_rollup.on_track} on track</StatusDot>
                    <StatusDot tone="warning">{data.goal_rollup.at_risk} at risk</StatusDot>
                  </div>
                </div>
                <div className="p-1.5">
                  {goals.map((goal) => <button key={goal.id} type="button" onClick={() => navigate(`/workspaces/${goal.workspaceId}`)} className="block w-full rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-muted/50">
                    <span className="flex items-center justify-between gap-3 text-[13px]">
                      <span className="truncate font-medium text-foreground">{goal.title}</span>
                      <span className="tabular shrink-0 text-xs font-medium text-foreground">{goal.pct ?? "—"}{goal.pct !== null ? "%" : ""}</span>
                    </span>
                    <span className="mt-1.5 block h-1 overflow-hidden rounded-full bg-muted"><span className={`block h-full rounded-full ${goal.pct >= 100 ? "bg-emerald-500" : goal.pct >= 50 ? "bg-brand" : "bg-amber-500"}`} style={{ width: `${Math.max(0, Math.min(goal.pct || 0, 100))}%` }} /></span>
                    <span className="mt-1 block truncate text-[11px] text-muted-foreground">{goal.workspaceName}</span>
                  </button>)}
                </div>
              </> : <EmptyState icon={ClipboardCheck} title="No outcome targets yet" description="Define client outcomes in a workspace to connect delivery activity to value." className="py-8" />}
            </div>
          </Section>
        </div>
        <CommandCenterInsights stacked />
      </div>
    </div>

  </div>;
}

function DashboardSkeleton() {
  return <div className="cv-page" data-testid="dashboard-skeleton">
    <div className="mb-5 space-y-2"><Skeleton className="h-7 w-48" /><Skeleton className="h-4 w-96 max-w-full" /></div>
    <Skeleton className="h-[88px] rounded-xl" />
    <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
      <div className="space-y-6 xl:col-span-2"><Skeleton className="h-40 rounded-xl" /><Skeleton className="h-72 rounded-xl" /></div>
      <div className="space-y-6"><Skeleton className="h-56 rounded-xl" /><Skeleton className="h-56 rounded-xl" /></div>
    </div>
  </div>;
}
