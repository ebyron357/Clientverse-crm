import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, money, HEALTH_BAND } from "@/lib/api";
import { Badge } from "@/components/AppShell";
import OnboardingChecklist from "@/components/OnboardingChecklist";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Bar, BarChart, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  AlertTriangle, ArrowRight, BriefcaseBusiness, CheckCircle2, CircleAlert,
  CircleDollarSign, ClipboardCheck, RefreshCw, Sparkles, TrendingUp,
} from "lucide-react";

const STAGE_LABELS = { lead: "Lead", qualified: "Qualified", proposal: "Proposal", negotiation: "Negotiation", closed_won: "Won", closed_lost: "Lost" };

function MetricCard({ icon: Icon, label, value, detail, tone = "cyan", onClick }) {
  const tones = {
    cyan: "bg-cyan-50 text-[#1a9fbf]",
    navy: "bg-[#0a1628]/[0.06] text-[#0a1628]",
    emerald: "bg-emerald-50 text-emerald-600",
    amber: "bg-amber-50 text-amber-600",
  };
  const Component = onClick ? "button" : "div";
  return <Component onClick={onClick} className={`cv-kpi text-left ${onClick ? "w-full cursor-pointer" : ""}`}>
    <div className="flex items-start justify-between gap-3"><span className="text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">{label}</span><span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${tones[tone]}`}><Icon className="h-4 w-4" /></span></div>
    <div className="mt-5 font-display text-3xl font-extrabold tracking-[-0.04em] text-[#0a1628]">{value}</div>
    <div className="mt-1.5 text-xs leading-5 text-slate-500">{detail}</div>
    {onClick && <span className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-[#1a9fbf]">Open view <ArrowRight className="h-3.5 w-3.5" /></span>}
  </Component>;
}

function HealthBar({ score, band }) {
  const color = band === "healthy" ? "bg-emerald-500" : band === "at_risk" ? "bg-amber-500" : "bg-red-500";
  return <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${color}`} style={{ width: `${Math.max(0, Math.min(score, 100))}%` }} /></div>;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [system, setSystem] = useState({ alerts: [], integrations: [] });
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    const [dashboard, alerts, integrations] = await Promise.allSettled([
      api.get("/dashboard"), api.get("/alerts"), api.get("/integrations/health"),
    ]);
    if (dashboard.status !== "fulfilled") { setError("We could not load your command center. Check your connection and try again."); return; }
    setData(dashboard.value.data);
    setSystem({ alerts: alerts.status === "fulfilled" ? alerts.value.data : [], integrations: integrations.status === "fulfilled" ? integrations.value.data : [] });
  }, []);

  useEffect(() => { load(); }, [load]);

  const funnelData = useMemo(() => data ? Object.entries(data.funnel || {}).filter(([key]) => key !== "closed_lost").map(([key, value]) => ({ name: STAGE_LABELS[key] || key, count: value, key })) : [], [data]);
  const priorityItems = useMemo(() => {
    if (!data) return [];
    const items = [];
    if (data.at_risk_commitments) items.push({ icon: AlertTriangle, title: `${data.at_risk_commitments} commitment${data.at_risk_commitments === 1 ? "" : "s"} needs attention`, body: "Review delivery risk before the next client touchpoint.", to: "/workspaces", tone: "amber" });
    const pendingAlerts = Array.isArray(system.alerts) ? system.alerts.filter((alert) => alert.status !== "resolved").length : 0;
    if (pendingAlerts) items.push({ icon: CircleAlert, title: `${pendingAlerts} unresolved risk signal${pendingAlerts === 1 ? "" : "s"}`, body: "Review account alerts and assign ownership.", to: "/workspaces", tone: "red" });
    const degraded = Array.isArray(system.integrations) ? system.integrations.filter((integration) => ["degraded", "expired", "error"].includes(integration.status)).length : 0;
    if (degraded) items.push({ icon: CircleAlert, title: `${degraded} integration health issue${degraded === 1 ? "" : "s"}`, body: "Reconnect or investigate a provider connection.", to: "/registries", tone: "red" });
    if (!items.length) items.push({ icon: CheckCircle2, title: "No immediate risks detected", body: "Your portfolio has no outstanding attention signals right now.", to: "/workspaces", tone: "emerald" });
    return items.slice(0, 3);
  }, [data, system]);

  if (error) return <div className="cv-page"><div className="cv-empty"><CircleAlert className="h-9 w-9 text-red-500" /><h1 className="mt-4 font-display text-xl font-bold text-[#0a1628]">Command Center unavailable</h1><p className="mt-2 max-w-md text-sm leading-6 text-slate-500">{error}</p><Button onClick={load} className="mt-5 cv-action-primary"><RefreshCw className="mr-2 h-4 w-4" />Try again</Button></div></div>;
  if (!data) return <DashboardSkeleton />;

  return <div className="cv-page">
    <div className="cv-page-header">
      <div><div className="cv-eyebrow">Today’s client operations</div><h1 className="cv-page-title">Good to see you</h1><p className="cv-page-description">A concise view of revenue, delivery risk, and the client relationships that need your team next.</p></div>
      <div className="flex flex-wrap items-center gap-2"><Button variant="outline" size="sm" onClick={load}><RefreshCw className="mr-1.5 h-3.5 w-3.5" />Refresh</Button><Button size="sm" className="cv-action-primary" onClick={() => navigate("/pipeline")}>Review pipeline <ArrowRight className="ml-1.5 h-3.5 w-3.5" /></Button></div>
    </div>

    <section aria-label="Key portfolio metrics" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard icon={TrendingUp} label="Open pipeline" value={money(data.pipeline_value)} detail={`${data.open_opportunities} active opportunity${data.open_opportunities === 1 ? "" : "ies"}`} onClick={() => navigate("/pipeline")} />
      <MetricCard icon={CircleDollarSign} label="Won revenue" value={money(data.won_value)} detail="Closed-won opportunities in your portfolio" tone="emerald" onClick={() => navigate("/pipeline")} />
      <MetricCard icon={BriefcaseBusiness} label="Active clients" value={data.active_workspaces} detail="Client workspaces currently in delivery" tone="navy" onClick={() => navigate("/workspaces")} />
      <MetricCard icon={AlertTriangle} label="Delivery risk" value={data.at_risk_commitments} detail="Commitments flagged at risk or overdue" tone="amber" onClick={() => navigate("/workspaces")} />
    </section>

    <OnboardingChecklist dashboard={data} integrations={system.integrations} />

    <section className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-12">
      <div className="cv-card xl:col-span-7"><div className="cv-card-header"><div><h2 className="cv-card-title">Revenue movement</h2><p className="cv-card-description">A stage-by-stage view of qualified client demand.</p></div><button onClick={() => navigate("/pipeline")} className="text-xs font-semibold text-[#1a9fbf] hover:text-[#147f9a]">Open pipeline</button></div><div className="p-5"><div role="img" aria-label="Opportunity count by pipeline stage" className="h-[250px]">{funnelData.length ? <ResponsiveContainer width="100%" height="100%"><BarChart data={funnelData} layout="vertical" margin={{ left: 4, right: 12, top: 4, bottom: 4 }}><XAxis type="number" hide /><YAxis dataKey="name" type="category" width={82} tick={{ fontSize: 12, fill: "#64748b" }} axisLine={false} tickLine={false} /><Tooltip cursor={{ fill: "#f8fafc" }} contentStyle={{ borderRadius: 12, borderColor: "#e2e8f0", boxShadow: "0 8px 24px rgba(10,22,40,.08)" }} /><Bar dataKey="count" radius={[0, 8, 8, 0]}>{funnelData.map((entry) => <Cell key={entry.key} fill={entry.key === "closed_won" ? "#16a34a" : entry.key === "proposal" || entry.key === "negotiation" ? "#1a9fbf" : "#0a1628"} />)}</Bar></BarChart></ResponsiveContainer> : <div className="cv-empty min-h-[250px]"><GitBranch className="h-8 w-8 text-slate-300" /><p className="mt-3 text-sm font-semibold text-slate-700">Your pipeline starts here</p><p className="mt-1 text-xs text-slate-500">Create the first opportunity to begin tracking revenue movement.</p><Button size="sm" className="mt-4 cv-action-primary" onClick={() => navigate("/pipeline")}>Create opportunity</Button></div>}</div></div></div>
      <div className="cv-card xl:col-span-5"><div className="cv-card-header"><div><h2 className="cv-card-title">Priority actions</h2><p className="cv-card-description">Signals worth resolving before they become client problems.</p></div><span className="cv-status-dot bg-[#4ac4e0]" aria-label="Live portfolio signals" /></div><div className="divide-y divide-slate-100">{priorityItems.map((item, index) => { const Icon = item.icon; const tones = { amber: "bg-amber-50 text-amber-600", red: "bg-red-50 text-red-600", emerald: "bg-emerald-50 text-emerald-600" }; return <button key={index} onClick={() => navigate(item.to)} className="cv-data-row flex w-full items-start gap-3 px-5 py-4 text-left"><span className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${tones[item.tone]}`}><Icon className="h-4 w-4" /></span><span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-[#132038]">{item.title}</span><span className="mt-0.5 block text-xs leading-5 text-slate-500">{item.body}</span></span><ArrowRight className="mt-1 h-4 w-4 shrink-0 text-slate-300" /></button>; })}</div></div>
    </section>

    <section className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-12">
      <div className="cv-card xl:col-span-7"><div className="cv-card-header"><div><h2 className="cv-card-title">Client health portfolio</h2><p className="cv-card-description">Explainable account health across active workspaces.</p></div><button onClick={() => navigate("/workspaces")} className="text-xs font-semibold text-[#1a9fbf] hover:text-[#147f9a]">View all clients</button></div>{data.portfolio?.length ? <div className="divide-y divide-slate-100">{data.portfolio.map((portfolio) => <button key={portfolio.id} onClick={() => navigate(`/workspaces/${portfolio.id}`)} className="cv-data-row flex w-full items-center gap-4 px-5 py-4 text-left"><span className={`flex h-9 w-9 items-center justify-center rounded-xl text-sm font-bold ${portfolio.health.band === "healthy" ? "bg-emerald-50 text-emerald-600" : portfolio.health.band === "at_risk" ? "bg-amber-50 text-amber-600" : "bg-red-50 text-red-600"}`}>{portfolio.health.score}</span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold text-[#132038]">{portfolio.name}</span><span className="mt-0.5 block text-xs capitalize text-slate-500">{portfolio.stage} workspace</span></span><span className="hidden items-center gap-2 sm:flex"><HealthBar score={portfolio.health.score} band={portfolio.health.band} /><Badge className={HEALTH_BAND[portfolio.health.band]}>{portfolio.health.band.replace("_", " ")}</Badge></span><ArrowRight className="h-4 w-4 text-slate-300" /></button>)}</div> : <div className="cv-empty m-5"><BriefcaseBusiness className="h-8 w-8 text-slate-300" /><p className="mt-3 text-sm font-semibold text-slate-700">No client workspaces yet</p><p className="mt-1 text-xs text-slate-500">Close an opportunity or create a workspace to begin tracking client health.</p></div>}</div>
      <div className="cv-card xl:col-span-5"><div className="cv-card-header"><div><h2 className="cv-card-title">Outcome momentum</h2><p className="cv-card-description">Portfolio goals that show whether client value is being delivered.</p></div><Sparkles className="h-4 w-4 text-[#1a9fbf]" /></div>{data.goal_rollup?.total_goals > 0 ? <div className="p-5"><div className="mb-5 flex items-end justify-between"><div><div className="font-display text-3xl font-extrabold text-[#0a1628]">{data.goal_rollup.avg_progress}%</div><div className="mt-1 text-xs text-slate-500">average outcome progress</div></div><div className="flex gap-1.5"><Badge className="bg-emerald-50 text-emerald-700 border-emerald-200">{data.goal_rollup.on_track} on track</Badge><Badge className="bg-amber-50 text-amber-700 border-amber-200">{data.goal_rollup.at_risk} at risk</Badge></div></div><div className="space-y-3">{data.goal_rollup.workspaces?.flatMap((workspace) => workspace.goals.map((goal) => ({ ...goal, workspaceName: workspace.name, workspaceId: workspace.id }))).slice(0, 4).map((goal) => <button key={goal.id} onClick={() => navigate(`/workspaces/${goal.workspaceId}`)} className="group block w-full text-left"><div className="flex items-center justify-between gap-3 text-xs"><span className="truncate font-semibold text-slate-700 group-hover:text-[#1a9fbf]">{goal.title}</span><span className="shrink-0 font-bold text-[#0a1628]">{goal.pct ?? "—"}{goal.pct !== null ? "%" : ""}</span></div><div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${goal.pct >= 100 ? "bg-emerald-500" : goal.pct >= 50 ? "bg-[#1a9fbf]" : "bg-amber-500"}`} style={{ width: `${Math.max(0, Math.min(goal.pct || 0, 100))}%` }} /></div><span className="mt-1 block truncate text-[11px] text-slate-400">{goal.workspaceName}</span></button>)}</div></div> : <div className="cv-empty m-5"><ClipboardCheck className="h-8 w-8 text-slate-300" /><p className="mt-3 text-sm font-semibold text-slate-700">No outcome targets yet</p><p className="mt-1 text-xs text-slate-500">Define client outcomes in a workspace to connect delivery activity to value.</p></div>}</div>
    </section>
  </div>;
}

function DashboardSkeleton() {
  return <div className="cv-page"><div className="mb-8 space-y-3"><Skeleton className="h-3 w-32" /><Skeleton className="h-9 w-56" /><Skeleton className="h-4 w-96 max-w-full" /></div><div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-44 rounded-2xl" />)}</div><div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-12"><Skeleton className="h-80 rounded-2xl xl:col-span-7" /><Skeleton className="h-80 rounded-2xl xl:col-span-5" /></div></div>;
}
