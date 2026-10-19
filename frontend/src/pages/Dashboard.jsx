/* Today: the day's work in one place, in the order it should be done.
   The plan and the panels come from GET /api/today, which ranks what is recorded (new leads,
   appointments, tasks, approvals, at-risk commitments, deals with no next step) and gives the
   reason for each item, so the order can be checked. Client health and the next best actions
   come from the existing Command Center reads. */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr, formatMoneyByCurrency } from "@/lib/api";
import { commandCenterService } from "@/lib/services";
import { useAuth } from "@/context/AuthContext";
import OnboardingChecklist from "@/components/OnboardingChecklist";
import CommandCenterInsights from "@/components/CommandCenterInsights";
import NextBestActions from "@/components/NextBestActions";
import { Avatar, StatusDot } from "@/components/page/Page";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  AlertTriangle, CalendarDays, CheckCircle2, ChevronRight, CircleAlert, Clock, GitBranch, Mail,
  MessageSquare, Phone, RefreshCw, ShieldCheck, SquareCheckBig, Zap,
} from "lucide-react";

const TIME_ZONE = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; } catch { return "UTC"; } })();
const KIND = {
  lead: { icon: Zap, tone: "text-red-600" },
  appointment: { icon: CalendarDays, tone: "text-brand" },
  overdue_task: { icon: AlertTriangle, tone: "text-amber-600" },
  approval: { icon: ShieldCheck, tone: "text-violet-600" },
  commitment: { icon: CircleAlert, tone: "text-amber-600" },
  due_today: { icon: SquareCheckBig, tone: "text-muted-foreground" },
  stalled_deal: { icon: GitBranch, tone: "text-muted-foreground" },
};
const BAND_TONE = { healthy: "success", at_risk: "warning", critical: "danger" };
const BAND_BAR = { healthy: "bg-emerald-500", at_risk: "bg-amber-500", critical: "bg-red-500" };

function waited(minutes) {
  const m = Math.max(0, Math.floor(minutes || 0));
  if (m < 60) return `${m}m`;
  if (m < 60 * 24) return `${Math.floor(m / 60)}h ${m % 60}m`;
  const days = Math.floor(m / (60 * 24));
  return `${days} day${days === 1 ? "" : "s"}`;
}
const timeOf = (iso) => new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
const dayOf = (iso) => new Date(iso).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
const shortDay = (iso) => new Date(iso).toLocaleDateString(undefined, { weekday: "short" });
function greeting() {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

/** A panel with a title row: the Today screen's one card shape. */
function Panel({ title, count, countTone, detail, action, children, className, testid }) {
  return <section className={cn("cv-card min-w-0 overflow-hidden", className)} data-testid={testid} aria-label={typeof title === "string" ? title : undefined}>
    <div className="flex items-center gap-2 border-b border-border/80 px-4 py-3">
      <h2 className="text-[15px] font-semibold tracking-tight text-foreground">{title}</h2>
      {count !== undefined && count !== null && <span className={cn("tabular rounded-md px-1.5 py-0.5 text-[11px] font-semibold", countTone || "bg-muted text-muted-foreground")}>{count}</span>}
      {detail && <span className="hidden truncate text-[12.5px] text-muted-foreground sm:inline">{detail}</span>}
      {action && <div className="ml-auto shrink-0">{action}</div>}
    </div>
    {children}
  </section>;
}

function PanelLink({ to, children }) {
  return <Link to={to} className="inline-flex items-center gap-0.5 text-[13px] font-semibold text-brand-strong hover:underline">{children}</Link>;
}

function Empty({ icon: Icon, title, children }) {
  return <div className="flex flex-col items-center px-6 py-8 text-center">
    <span className="flex size-9 items-center justify-center rounded-full bg-muted text-muted-foreground"><Icon className="size-4" aria-hidden="true" /></span>
    <p className="mt-2.5 text-[13px] font-medium text-foreground">{title}</p>
    {children && <p className="mt-1 max-w-xs text-xs leading-5 text-muted-foreground">{children}</p>}
  </div>;
}

function Stat({ label, value, detail, tone, to, testid }) {
  const body = <>
    <span className="block text-[13px] font-medium text-muted-foreground">{label}</span>
    <span className={cn("tabular mt-1.5 block text-[26px] font-bold leading-8 tracking-tight [overflow-wrap:anywhere]", tone || "text-foreground")}>{value}</span>
    {detail && <span className="mt-1 block truncate text-xs text-muted-foreground" title={detail}>{detail}</span>}
  </>;
  return to
    ? <Link to={to} className="cv-card block min-w-0 px-4 py-3.5 transition-colors hover:border-input" data-testid={testid}>{body}</Link>
    : <div className="cv-card min-w-0 px-4 py-3.5" data-testid={testid}>{body}</div>;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [day, setDay] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [integrations, setIntegrations] = useState([]);
  const [error, setError] = useState("");
  const [range, setRange] = useState("today");
  const [showAll, setShowAll] = useState(false);
  const [closing, setClosing] = useState("");

  const load = useCallback(async () => {
    setError("");
    const [todayResult, dashboardResult, integrationResult] = await Promise.allSettled([
      api.get("/today", { params: { tz: TIME_ZONE } }), commandCenterService.getPortfolio(), commandCenterService.getIntegrationHealth(),
    ]);
    if (todayResult.status !== "fulfilled") { setError(formatErr(todayResult.reason?.response?.data?.detail) || "Today could not be loaded. Check your connection and try again."); return; }
    setDay(todayResult.value.data);
    setPortfolio(dashboardResult.status === "fulfilled" ? dashboardResult.value : null);
    setIntegrations(integrationResult.status === "fulfilled" ? integrationResult.value : []);
  }, []);
  useEffect(() => { load(); }, [load]);

  const appointmentsByDay = useMemo(() => {
    const list = (day?.appointments || []).filter((item) => range === "week" || item.today);
    const groups = [];
    for (const item of list) {
      const key = new Date(item.start_at).toDateString();
      const group = groups.find((entry) => entry.key === key);
      if (group) group.items.push(item); else groups.push({ key, label: dayOf(item.start_at), items: [item] });
    }
    return groups;
  }, [day, range]);

  const completeTask = async (task) => {
    setClosing(task.id);
    try {
      await api.patch(`/crm/tasks/${task.id}`, { status: "done" });
      toast.success("Task done", { description: task.title });
      await load();
    } catch (requestError) { toast.error("The task was not updated", { description: formatErr(requestError.response?.data?.detail) }); }
    finally { setClosing(""); }
  };

  if (error) return <div className="cv-page">
    <div className="cv-card flex flex-col items-center px-6 py-16 text-center" role="alert">
      <span className="flex size-10 items-center justify-center rounded-full bg-red-50 text-red-600"><CircleAlert className="size-5" aria-hidden="true" /></span>
      <h1 className="mt-3 text-sm font-semibold">Today is unavailable</h1>
      <p className="mt-1 max-w-md text-[13px] text-muted-foreground">{error}</p>
      <Button size="sm" className="mt-4" onClick={load}><RefreshCw className="size-3.5" />Try again</Button>
    </div>
  </div>;
  if (!day) return <TodaySkeleton />;

  const stats = day.stats;
  const firstName = (user?.name || "").split(/\s+/)[0];
  const plan = showAll ? day.plan : day.plan.slice(0, 6);
  const booked = Object.entries(stats.booked_by_type || {}).map(([name, count]) => `${count} ${name.toLowerCase()}`).join(" · ");
  const weighted = Object.keys(stats.weighted_by_currency || {}).length ? `${formatMoneyByCurrency(stats.weighted_by_currency)} weighted` : null;
  const waitingDetail = [stats.approvals_waiting && `${stats.approvals_waiting} approval${stats.approvals_waiting === 1 ? "" : "s"}`, stats.commitments_at_risk && `${stats.commitments_at_risk} commitment${stats.commitments_at_risk === 1 ? "" : "s"} at risk`].filter(Boolean).join(" · ");
  const leadsToCall = day.leads.filter((lead) => lead.phone).length;
  const openStages = day.pipeline.filter((stage) => !stage.is_closed || stage.is_won);
  const stageMax = Math.max(1, ...openStages.map((stage) => stage.count));
  const clients = (portfolio?.portfolio || []).slice(0, 3);

  return <div className="cv-page">
    <header className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between" data-testid="dashboard-header">
      <div className="min-w-0">
        <h1 className="text-[22px] font-bold leading-8 tracking-tight text-foreground">{greeting()}{firstName ? `, ${firstName}` : ""}</h1>
        <p className="text-[13px] text-muted-foreground">{new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })} · {day.plan_total ? `${day.plan_total} thing${day.plan_total === 1 ? "" : "s"} on your plan` : "Nothing urgent on your plan"}</p>
      </div>
      <Button variant="outline" size="sm" onClick={load} className="self-start sm:self-auto"><RefreshCw className="size-3.5" />Refresh</Button>
    </header>

    <section aria-label="Today in numbers" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Stat label="Leads not acted on" value={stats.leads_waiting} tone={stats.leads_waiting ? "text-red-600" : undefined} to="/leads" testid="stat-leads-waiting"
        detail={stats.leads_waiting ? `Oldest waiting ${waited(stats.oldest_lead_minutes)}` : "Every lead has had a reply"} />
      <Stat label="Booked this week" value={stats.booked_this_week} to="/scheduling/calendar" testid="stat-booked" detail={booked || "Nothing booked yet"} />
      <Stat label="Open pipeline" value={formatMoneyByCurrency(stats.open_by_currency)} to="/pipeline" testid="metric-open-pipeline"
        detail={[`${stats.open_deals} deal${stats.open_deals === 1 ? "" : "s"}`, weighted].filter(Boolean).join(" · ")} />
      <Stat label="Waiting on you" value={stats.approvals_waiting + stats.commitments_at_risk} tone={stats.approvals_waiting + stats.commitments_at_risk ? "text-amber-600" : undefined}
        to="/operations?tab=approvals" testid="stat-waiting" detail={waitingDetail || "No approvals or risks"} />
    </section>

    {portfolio && <OnboardingChecklist dashboard={portfolio} integrations={integrations} />}

    {/* The plan comes first on a phone; on a wide screen it heads the right-hand column. */}
    <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-3 xl:grid-rows-[auto_1fr] xl:items-start">
      <div className="min-w-0 xl:col-start-3 xl:row-start-1">
        <Panel title="Your plan" count={day.plan_total || undefined} detail={day.plan_total ? "In order, with the reason" : undefined} testid="dashboard-priority-panel">
          {day.plan.length ? <>
            <ol className="divide-y divide-border/70">{plan.map((item, index) => {
              const kind = KIND[item.kind] || KIND.due_today;
              const Icon = kind.icon;
              return <li key={`${item.kind}-${item.id}`}>
                <Link to={item.link} className="group flex items-start gap-3 px-4 py-2.5 transition-colors hover:bg-muted/50" data-testid={`priority-action-${index}`}>
                  <span className="tabular mt-0.5 w-4 shrink-0 text-center text-xs font-semibold text-muted-foreground">{index + 1}</span>
                  <Icon className={cn("mt-0.5 size-4 shrink-0", kind.tone)} aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-semibold text-foreground">{item.title}</span>
                    <span className="block text-xs leading-5 text-muted-foreground">{[item.detail, item.reason].filter(Boolean).join(" · ")}</span>
                  </span>
                  <ChevronRight className="mt-0.5 size-4 shrink-0 text-muted-foreground/60 group-hover:text-foreground" aria-hidden="true" />
                </Link>
              </li>;
            })}</ol>
            {day.plan.length > 6 && <button type="button" onClick={() => setShowAll((value) => !value)} className="w-full border-t border-border/70 py-2 text-[13px] font-semibold text-brand-strong hover:bg-muted/50">{showAll ? "Show less" : `Show all ${day.plan.length}`}</button>}
          </> : <Empty icon={CheckCircle2} title="You're clear">No lead waiting, nothing overdue, no decision pending.</Empty>}
        </Panel>
      </div>
      <div className="min-w-0 space-y-5 xl:col-span-2 xl:col-start-1 xl:row-span-2 xl:row-start-1">
        <Panel title={<span className="flex items-center gap-2"><Zap className="size-4 text-amber-500" aria-hidden="true" />New leads waiting</span>} testid="today-leads"
          count={day.leads.length || undefined} countTone="bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-300"
          detail={day.leads.length ? "Oldest first · reply fast: it is the biggest lever on winning them" : undefined} action={<PanelLink to="/leads">All leads</PanelLink>}>
          {day.leads.length ? <ul className="divide-y divide-border/70">{day.leads.map((lead) => <li key={lead.id} className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center" data-testid={`today-lead-${lead.id}`}>
            <div className="flex min-w-0 flex-1 gap-3">
              <Avatar name={lead.name} size="md" className="mt-0.5" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <Link to={`/leads?lead=${lead.id}`} className="text-[14px] font-semibold text-foreground hover:underline">{lead.name}</Link>
                  {lead.company && <span className="text-[13px] text-muted-foreground">{lead.company}</span>}
                  {lead.topic && <span className="rounded-md bg-muted px-1.5 py-0.5 text-[11.5px] font-semibold text-foreground/80">{lead.topic}</span>}
                  {lead.existing_client && <StatusDot tone="success">Existing client</StatusDot>}
                  {lead.next_appointment && <span className="inline-flex items-center gap-1 rounded-md bg-brand/10 px-1.5 py-0.5 text-[11.5px] font-semibold text-brand-strong"><CalendarDays className="size-3" aria-hidden="true" />{lead.next_appointment.title} · {shortDay(lead.next_appointment.start_at)} {timeOf(lead.next_appointment.start_at)}</span>}
                </div>
                <p className="mt-1 truncate text-[13px] text-muted-foreground" title={lead.message}>{lead.message ? `“${lead.message}”` : "No message"}{lead.form_name ? ` · ${lead.form_name}` : ""}</p>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2 pl-11 sm:pl-0">
              <span className={cn("tabular inline-flex items-center gap-1 text-[13px] font-semibold", lead.overdue ? "text-red-600" : "text-muted-foreground")} title={lead.goal_minutes ? `Goal: a reply within ${lead.goal_minutes} minutes` : undefined}>
                <Clock className="size-3.5" aria-hidden="true" />{waited(lead.waiting_minutes)}
              </span>
              {lead.phone && <Button asChild size="sm" className="h-8 bg-emerald-600 text-white hover:bg-emerald-700"><a href={`tel:${lead.phone}`} aria-label={`Call ${lead.name}`}><Phone className="size-3.5" />Call</a></Button>}
              {lead.phone && <Button asChild size="sm" variant="outline" className="size-8 p-0"><a href={`sms:${lead.phone}`} aria-label={`Text ${lead.name}`}><MessageSquare className="size-3.5" /></a></Button>}
              {lead.email && <Button asChild size="sm" variant="outline" className="size-8 p-0"><a href={`mailto:${lead.email}`} aria-label={`Email ${lead.name}`}><Mail className="size-3.5" /></a></Button>}
            </div>
          </li>)}</ul> : <Empty icon={CheckCircle2} title="No lead is waiting">New website and booking leads appear here, oldest first, until someone replies.</Empty>}
        </Panel>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <Panel title="Pipeline" detail={weighted || undefined} action={<PanelLink to="/pipeline">Open board</PanelLink>} testid="today-pipeline">
            {day.pipeline.some((stage) => stage.count) ? <ul className="space-y-1 px-4 py-3" aria-label="Deals by stage">{openStages.map((stage) => <li key={stage.key} className="grid h-8 grid-cols-[6.5rem_minmax(0,1fr)_1.75rem_5.5rem] items-center gap-3 text-[13px]">
              <span className="truncate font-medium text-foreground">{stage.label}</span>
              <span className="h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden="true"><span className={cn("block h-full rounded-full", stage.is_won ? "bg-emerald-500" : "bg-brand")} style={{ width: `${(stage.count / stageMax) * 100}%` }} /></span>
              <span className="tabular text-right font-semibold">{stage.count}</span>
              <span className="tabular truncate text-right text-muted-foreground">{Object.keys(stage.value_by_currency).length ? formatMoneyByCurrency(stage.value_by_currency) : "No value yet"}</span>
            </li>)}</ul> : <Empty icon={GitBranch} title="Your pipeline starts here">Deals appear here by stage, with their value.</Empty>}
          </Panel>

          <Panel title="Clients" detail="After the sale" action={<PanelLink to="/workspaces">All clients</PanelLink>} testid="today-clients">
            {clients.length || day.commitments.length ? <div className="divide-y divide-border/70">
              {clients.map((client) => <button key={client.id} type="button" onClick={() => navigate(`/workspaces/${client.id}`)} className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-muted/50">
                <Avatar name={client.name} size="sm" />
                <span className="min-w-0 flex-1"><span className="block truncate text-[13px] font-semibold">{client.name}</span>
                  <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-muted"><span className={cn("block h-full rounded-full", BAND_BAR[client.health.band] || BAND_BAR.critical)} style={{ width: `${Math.max(0, Math.min(client.health.score, 100))}%` }} /></span></span>
                <span className="tabular w-9 text-right text-[13px] font-semibold">{client.health.score}</span>
                <StatusDot tone={BAND_TONE[client.health.band] || "danger"} className="w-16 shrink-0">{client.health.band === "healthy" ? "Healthy" : client.health.band === "at_risk" ? "At risk" : "Critical"}</StatusDot>
              </button>)}
              {day.commitments.map((commitment) => <Link key={commitment.id} to={`/workspaces/${commitment.workspace_id}`} className="flex items-start gap-2.5 px-4 py-2.5 transition-colors hover:bg-muted/50">
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden="true" />
                <span className="min-w-0"><span className="block truncate text-[13px] font-semibold">{commitment.status === "breached" ? "Breached" : "At risk"}: {commitment.title}</span>
                  <span className="block truncate text-xs text-muted-foreground">{[commitment.workspace_name, commitment.due_date && `due ${dayOf(commitment.due_date)}`].filter(Boolean).join(" · ")}</span></span>
              </Link>)}
            </div> : <Empty icon={ShieldCheck} title="No client workspaces yet">Winning a deal with a company opens one.</Empty>}
          </Panel>
        </div>

        <div data-testid="command-center-nba">
          <NextBestActions limit={6} compact title="Next best actions" onNavigate={(item) => navigate(`/workspaces/${item.workspace_id}`)} />
        </div>
      </div>

      <div className="min-w-0 space-y-5 xl:col-start-3 xl:row-start-2">
        <Panel title="Appointments" testid="today-appointments"
          action={<div className="flex rounded-lg bg-muted p-0.5" role="group" aria-label="Appointments range">{[["today", "Today"], ["week", "Week"]].map(([value, label]) => <button key={value} type="button" onClick={() => setRange(value)} aria-pressed={range === value}
            className={cn("h-7 rounded-md px-2.5 text-[12.5px] font-semibold transition-colors", range === value ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}>{label}</button>)}</div>}>
          {appointmentsByDay.length ? <div className="divide-y divide-border/70">{appointmentsByDay.map((group) => <div key={group.key} className="px-4 py-2.5">
            <div className="mb-1 text-xs font-semibold text-foreground">{group.label}</div>
            <ul className="space-y-1.5">{group.items.map((item) => <li key={item.id} className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-3 text-[13px]">
              <span className="tabular font-semibold text-foreground">{timeOf(item.start_at)}</span>
              <span className="min-w-0"><span className="block truncate font-semibold">{item.title}</span><span className="block truncate text-xs text-muted-foreground">{[item.contact_name, item.company].filter(Boolean).join(" · ") || "No contact linked"}</span></span>
            </li>)}</ul>
          </div>)}</div> : <Empty icon={CalendarDays} title={range === "today" ? "Nothing booked today" : "Nothing booked this week"}><Link to="/scheduling/calendar" className="font-semibold text-brand-strong hover:underline">Share a booking link</Link> so people can pick a time.</Empty>}
        </Panel>

        <Panel title="Tasks" count={stats.overdue_tasks ? `${stats.overdue_tasks} overdue` : undefined} countTone="bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-300" action={<PanelLink to="/tasks">All tasks</PanelLink>} testid="today-tasks">
          {leadsToCall > 0 && <div className="flex items-center gap-2 border-b border-border/70 bg-red-50/70 px-4 py-2 dark:bg-red-500/10">
            <Phone className="size-4 shrink-0 text-red-600" aria-hidden="true" />
            <span className="min-w-0 flex-1 text-[13px] font-semibold text-red-700 dark:text-red-300">Call {leadsToCall} new lead{leadsToCall === 1 ? "" : "s"} now</span>
            <Button asChild size="sm" className="h-7 bg-emerald-600 text-white hover:bg-emerald-700"><Link to="/leads">Start</Link></Button>
          </div>}
          {day.tasks.length ? <ul className="divide-y divide-border/70">{day.tasks.map((task) => <li key={task.id} className="flex items-center gap-3 px-4 py-2">
            <Checkbox checked={closing === task.id} disabled={Boolean(closing)} onCheckedChange={() => completeTask(task)} aria-label={`Mark “${task.title}” done`} data-testid={`today-task-done-${task.id}`} />
            <Link to={`/tasks?task=${task.id}`} className="min-w-0 flex-1 truncate text-[13px] text-foreground hover:underline">{task.title}</Link>
            <span className={cn("tabular shrink-0 text-xs", task.overdue ? "font-semibold text-red-600" : "text-muted-foreground")}>{task.overdue ? `Since ${dayOf(task.due_date)}` : timeOf(task.due_date)}</span>
          </li>)}</ul> : <Empty icon={SquareCheckBig} title="Nothing due today">Tasks due today and anything overdue land here.</Empty>}
        </Panel>

        <CommandCenterInsights stacked />
      </div>
    </div>
    {Object.keys(stats.open_by_currency || {}).length > 1 && <p className="mt-4 text-xs text-muted-foreground">Amounts are shown per currency and never added across currencies.</p>}
  </div>;
}

function TodaySkeleton() {
  return <div className="cv-page" data-testid="dashboard-skeleton">
    <div className="mb-5 space-y-2"><Skeleton className="h-7 w-64" /><Skeleton className="h-4 w-80 max-w-full" /></div>
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{[0, 1, 2, 3].map((index) => <Skeleton key={index} className="h-[104px] rounded-xl" />)}</div>
    <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-3">
      <div className="space-y-5 xl:col-span-2"><Skeleton className="h-72 rounded-xl" /><Skeleton className="h-56 rounded-xl" /></div>
      <div className="space-y-5"><Skeleton className="h-64 rounded-xl" /><Skeleton className="h-56 rounded-xl" /></div>
    </div>
  </div>;
}
