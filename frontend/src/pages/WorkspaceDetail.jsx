import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Avatar, PropertyList, Section, StatStrip, StatusDot } from "@/components/page/Page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";
import OutcomeGraph from "@/components/OutcomeGraph";
import WorkspaceActivity from "@/components/WorkspaceActivity";
import WorkspaceTimeline from "@/components/WorkspaceTimeline";
import NextBestActions from "@/components/NextBestActions";
import { ArrowLeft, ChevronDown, ClipboardList, FileCheck2, FileText, Handshake, Inbox, Mail, Plus, ShieldAlert, ShieldCheck, Sparkles } from "lucide-react";

const cx = (...parts) => parts.filter(Boolean).join(" ");
const HEALTH_TONE = { healthy: "success", at_risk: "warning", critical: "danger" };
const STATUS_TONE = { open: "info", todo: "neutral", in_progress: "info", in_review: "warning", done: "success", approved: "success", draft: "neutral", at_risk: "warning", breached: "danger", fulfilled: "success", requested: "warning", rejected: "danger" };
const PRIORITY_TONE = { urgent: "danger", high: "warning", medium: "info", normal: "info", low: "neutral" };
const STAGE_TONE = { onboard: "violet", serve: "brand", retain: "warning", expand: "success" };
const humanize = (value) => String(value || "").replaceAll("_", " ").replace(/^\w/, (char) => char.toUpperCase());
const shortDate = (value, withYear = false) => value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", ...(withYear ? { year: "numeric" } : {}) }) : null;

function dueInfo(due) {
  if (!due) return null;
  const d = new Date(due);
  const ms = d.getTime() - Date.now();
  const days = Math.round(ms / 86400000);
  if (ms < 0) return { date: shortDate(due), label: `${Math.abs(days)}d overdue`, overdue: true };
  if (days === 0) return { date: shortDate(due), label: "today", overdue: false };
  if (days <= 7) return { date: shortDate(due), label: `in ${days}d`, overdue: false };
  return { date: shortDate(due), label: null, overdue: false };
}

function DueText({ due }) {
  const info = dueInfo(due);
  if (!info) return <span className="text-muted-foreground">—</span>;
  return <span className={cx("tabular whitespace-nowrap", info.overdue ? "text-red-600" : "text-foreground/80")}>{info.date}{info.label && <span className={info.overdue ? "" : "text-muted-foreground"}> · {info.label}</span>}</span>;
}

/** Inline status picker: reads as a status dot until it is opened. */
function StatusSelect({ value, options, onChange, testid, label }) {
  return <Select value={value} onValueChange={onChange}>
    <SelectTrigger aria-label={label} data-testid={testid} className="h-7 w-[136px] gap-1 border-transparent bg-transparent px-2 text-[13px] shadow-none transition-colors hover:bg-muted focus:ring-1 data-[state=open]:bg-muted">
      <SelectValue />
    </SelectTrigger>
    <SelectContent>{options.map((option) => <SelectItem key={option} value={option} className="text-[13px]"><StatusDot tone={STATUS_TONE[option]}>{humanize(option)}</StatusDot></SelectItem>)}</SelectContent>
  </Select>;
}

function Health({ health }) {
  const fill = health.band === "healthy" ? "bg-emerald-500" : health.band === "at_risk" ? "bg-amber-500" : "bg-red-500";
  return (
    <Section card title="Health breakdown" testid="health-panel"
      actions={<span className="flex items-center gap-2"><StatusDot tone={HEALTH_TONE[health.band]}>{humanize(health.band)}</StatusDot><span className="tabular text-[13px] font-semibold text-foreground">{health.score}<span className="font-normal text-muted-foreground">/100</span></span></span>}>
      <div className="px-4 pb-1 pt-3">
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted" role="img" aria-label={`Health score ${health.score} of 100`}>
          <div className={cx("h-full rounded-full", fill)} style={{ width: `${health.score}%` }} />
        </div>
      </div>
      <div className="divide-y divide-border/70 px-4">
        {health.factors.length === 0 && <div className="py-3 text-[13px] text-muted-foreground">No penalties. Client is healthy.</div>}
        {health.factors.map((f, i) => (
          <div key={i} className="flex items-center justify-between gap-3 py-2.5 text-[13px]">
            <div className="min-w-0">
              <span className="font-medium text-foreground">{f.factor}</span>
              <span className="ml-2 text-muted-foreground">{f.detail}</span>
              <span className="ml-2 rounded border border-border px-1 py-px text-[10px] text-muted-foreground">{f.type}</span>
            </div>
            <span className={cx("tabular shrink-0 font-medium", f.impact < 0 ? "text-red-600" : "text-emerald-600")}>{f.impact > 0 ? "+" : ""}{f.impact}</span>
          </div>
        ))}
      </div>
    </Section>
  );
}

function AIPanel({ workspaceId }) {
  const [mode, setMode] = useState("health_summary");
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const run = async () => {
    setBusy(true); setResult(null);
    try {
      const { data } = await api.post("/ai/generate", { workspace_id: workspaceId, mode, instruction });
      setResult(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "AI generation failed");
    } finally { setBusy(false); }
  };

  const modeButton = (value, Icon, text, testid) => <button type="button" onClick={() => setMode(value)} aria-pressed={mode === value} data-testid={testid}
    className={cx("flex h-7 flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-1.5 text-xs font-medium transition-colors", mode === value ? "bg-card text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground")}>
    <Icon className="size-3.5" aria-hidden="true" />{text}
  </button>;

  return (
    <Section testid="ai-panel" title={<span className="flex items-center gap-1.5"><Sparkles className="size-3.5 text-brand" aria-hidden="true" />Evidence-backed AI</span>} description="Grounded only in workspace records.">
      <div className="flex rounded-lg bg-muted p-0.5" role="group" aria-label="AI output type">
        {modeButton("health_summary", FileText, "Health summary", "ai-mode-summary")}
        {modeButton("draft_message", Mail, "Draft message", "ai-mode-draft")}
      </div>
      {mode === "draft_message" && (
        <Textarea placeholder="What should the message cover?" aria-label="What should the message cover?" value={instruction} onChange={(e) => setInstruction(e.target.value)} className="mt-2 min-h-[72px] text-[13px]" data-testid="ai-instruction-input" />
      )}
      <Button size="sm" onClick={run} disabled={busy} data-testid="ai-generate-button" className="mt-2 w-full">
        {busy ? "Generating…" : "Generate with evidence"}
      </Button>

      {result && (
        <div className="mt-4 space-y-3" data-testid="ai-result">
          <div className="rounded-lg border border-border bg-muted/30 p-3">
            <div className="mb-1.5 text-xs font-medium text-muted-foreground">AI output · Recommendation</div>
            <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-foreground">{result.output}</p>
          </div>
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
            <dt className="text-muted-foreground">Confidence</dt><dd className="text-amber-700">{result.confidence}</dd>
            <dt className="text-muted-foreground">Model</dt><dd className="truncate text-foreground/80">{result.model_version}</dd>
            <dt className="text-muted-foreground">Versions</dt><dd className="truncate text-foreground/80">Prompt {result.prompt_version} · Policy {result.policy_version}</dd>
            <dt className="text-muted-foreground">Run</dt><dd className="truncate font-mono text-foreground/80">{result.run_id}</dd>
          </dl>
          <div>
            <div className="mb-1 text-xs font-medium text-muted-foreground">Source records ({result.sources.length})</div>
            <div className="divide-y divide-border/70 rounded-lg border border-border">
              {result.sources.map((s, i) => (
                <div key={i} className="flex items-center gap-2 px-2.5 py-1.5 text-xs">
                  <span className="font-mono text-muted-foreground">{s.type}</span>
                  <span className="flex-1 truncate text-foreground/80">{s.label}</span>
                  <span className="text-muted-foreground">{s.status}</span>
                </div>
              ))}
              {result.sources.length === 0 && <div className="px-2.5 py-1.5 text-xs text-muted-foreground">No source records — output is low-confidence.</div>}
            </div>
          </div>
        </div>
      )}
    </Section>
  );
}

/**
 * One list per record type: a summary + add row, then a single bordered list.
 * `columns[0]` is the primary cell; the last column is the status/action cell; columns in
 * between are hidden on phones (their content is repeated in the primary cell's meta line).
 */
function ListSection({ items, columns, grid, summary, extra, onAdd, addLabel, emptyIcon: EmptyIcon = ClipboardList, testid }) {
  const addButton = onAdd && <Button size="sm" variant="outline" onClick={onAdd} data-testid={`add-${testid}`}><Plus className="size-3.5" />{addLabel}</Button>;
  return (
    <div data-testid={testid}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="tabular text-[13px] text-muted-foreground">{summary}</p>
        <div className="flex items-center gap-2">{extra}{items.length > 0 && addButton}</div>
      </div>
      <div className="overflow-hidden rounded-xl border border-border bg-card">
        {items.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
            <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground"><EmptyIcon className="size-5" aria-hidden="true" /></span>
            <p className="mt-3 text-sm font-medium text-foreground">No {addLabel?.toLowerCase() || "record"}s yet</p>
            <p className="mt-1 text-[13px] text-muted-foreground">Add the first one to make this account actionable.</p>
            {addButton && <div className="mt-4">{addButton}</div>}
          </div>
        ) : (
          <>
            <div className={cx("hidden h-9 items-center gap-3 border-b border-border bg-muted/40 px-4 text-xs font-medium text-muted-foreground sm:grid", grid)}>
              {columns.map((column) => <div key={column.label} className={column.align === "right" ? "text-right" : ""}>{column.label}</div>)}
            </div>
            {items.map((it) => (
              <div key={it.id} className={cx("grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border/70 px-4 py-2 text-[13px] transition-colors last:border-0 hover:bg-muted/50", grid)} data-testid={`row-${it.id}`}>
                {columns.map((column, index) => <div key={column.label} className={cx("min-w-0", index > 0 && index < columns.length - 1 && "hidden sm:block", column.align === "right" && "text-right")}>{column.render(it)}</div>)}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

function PrimaryCell({ title, meta, mobileMeta }) {
  return <div className="min-w-0 py-0.5">
    <div className="truncate font-medium text-foreground" title={title}>{title}</div>
    {meta && <div className="truncate text-xs text-muted-foreground">{meta}</div>}
    {mobileMeta && <div className="truncate text-xs text-muted-foreground sm:hidden">{mobileMeta}</div>}
  </div>;
}

function Person({ value, fallback = "Unassigned" }) {
  if (!value) return <span className="text-muted-foreground">{fallback}</span>;
  return <span className="flex min-w-0 items-center gap-2"><Avatar name={value} size="sm" /><span className="truncate text-foreground/80">{value}</span></span>;
}

function WorkItemDialog({ kind, title, onTitleChange, open, onOpenChange, busy, onSubmit }) {
  const meta = {
    task: { title: "New delivery task", description: "Capture the next accountable action for this client.", action: "Add task" },
    deliverable: { title: "New deliverable", description: "Define an artifact or output the client is expecting.", action: "Add deliverable" },
    request: { title: "New client request", description: "Log a request so it remains visible to the delivery team.", action: "Add request" },
    approval: { title: "New approval", description: "Create a governance request for an accountable decision.", action: "Request approval" },
  }[kind] || {};
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent><DialogHeader><DialogTitle>{meta.title}</DialogTitle><DialogDescription>{meta.description}</DialogDescription></DialogHeader><div className="grid gap-1.5 py-3"><Label htmlFor="workspace-item-title">Title <span className="text-red-600">*</span></Label><Input id="workspace-item-title" value={title} onChange={(event) => onTitleChange(event.target.value)} placeholder="Describe the work clearly" /></div><DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button disabled={busy} onClick={onSubmit}>{busy ? "Saving…" : meta.action}</Button></DialogFooter></DialogContent></Dialog>;
}

const TAB_LIST = "-mb-px h-auto w-full justify-start gap-4 overflow-x-auto rounded-none bg-transparent p-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden";
const TAB = "group -mb-px h-9 shrink-0 gap-1.5 rounded-none border-b-2 border-transparent bg-transparent px-0 text-[13px] text-muted-foreground shadow-none data-[state=active]:border-foreground data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none";
function TabCount({ value }) {
  return <span className="tabular rounded px-1 text-xs text-muted-foreground group-data-[state=active]:bg-muted group-data-[state=active]:text-foreground">{value}</span>;
}

export default function WorkspaceDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [d, setD] = useState(null);
  const [undoWin, setUndoWin] = useState("60");
  const [workItem, setWorkItem] = useState({ kind: null, title: "" });
  const [workItemBusy, setWorkItemBusy] = useState(false);
  const [cmtDialog, setCmtDialog] = useState(false);
  const [cmtForm, setCmtForm] = useState({ title: "", owner: "", due_date: "" });
  const [slaBusy, setSlaBusy] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");

  const load = useCallback(async () => {
    const { data } = await api.get(`/workspaces/${id}`);
    setD(data);
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const submitWorkItem = async () => {
    const { kind, title } = workItem;
    if (!title.trim()) { toast.error("A clear title is required."); return; }
    const endpoint = { task: "/tasks", deliverable: "/deliverables", request: "/client-requests", approval: "/approvals" }[kind];
    setWorkItemBusy(true);
    try {
      await api.post(endpoint, { workspace_id: id, title: title.trim() });
      toast.success(kind === "approval" ? "Approval requested" : `${kind.charAt(0).toUpperCase() + kind.slice(1)} added`);
      setWorkItem({ kind: null, title: "" });
      load();
    } catch (error) { toast.error(`Could not add ${kind}`, { description: formatErr(error.response?.data?.detail) }); }
    finally { setWorkItemBusy(false); }
  };
  const submitCommitment = async () => {
    if (!cmtForm.title.trim()) { toast.error("Title is required"); return; }
    await api.post("/commitments", {
      workspace_id: id, title: cmtForm.title.trim(), owner: cmtForm.owner || null,
      due_date: cmtForm.due_date ? new Date(cmtForm.due_date).toISOString() : null,
    });
    toast.success("Commitment added"); setCmtDialog(false); setCmtForm({ title: "", owner: "", due_date: "" }); load();
  };
  const runSlaCheck = async () => {
    setSlaBusy(true);
    try {
      const { data } = await api.post("/commitments/evaluate-risk");
      toast.success(`SLA check complete · ${data.flagged_at_risk} at-risk, ${data.flagged_breached} breached`);
      load();
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
    finally { setSlaBusy(false); }
  };
  const upd = async (url, body, msg) => { await api.patch(url, body); toast.success(msg); load(); };

  useEffect(() => { if (d?.workspace) setUndoWin(String(d.workspace.undo_window_minutes || 60)); }, [d]);
  const saveUndoWin = async () => {
    await api.patch(`/workspaces/${id}/undo-window`, { minutes: parseInt(undoWin) || 60 });
    toast.success("Undo window updated");
  };

  if (!d) return <div className="cv-page">
    <Skeleton className="mb-5 h-4 w-40" />
    <div className="mb-5 flex items-center gap-3"><Skeleton className="size-11 rounded-full" /><div className="space-y-2"><Skeleton className="h-6 w-56" /><Skeleton className="h-3.5 w-72" /></div></div>
    <Skeleton className="mb-6 h-[88px] rounded-xl" />
    <div className="flex flex-col gap-6 lg:flex-row"><Skeleton className="h-72 flex-1 rounded-xl" /><Skeleton className="h-72 rounded-xl lg:w-80" /></div>
  </div>;

  const { workspace, company, tasks, deliverables, requests, approvals, commitments, health } = d;
  const openCommitments = commitments.filter((it) => it.status !== "fulfilled");
  const atRisk = commitments.filter((it) => it.status === "at_risk").length;
  const breached = commitments.filter((it) => it.status === "breached").length;
  const openTasks = tasks.filter((it) => it.status !== "done");
  const overdueTasks = openTasks.filter((it) => it.due_date && new Date(it.due_date).getTime() < Date.now()).length;
  const pendingApprovals = approvals.filter((it) => it.status === "requested").length;
  const openRequests = requests.filter((it) => it.status !== "done").length;
  const riskFactors = health.factors.filter((f) => f.impact < 0).length;
  const isAdmin = user?.role === "admin";
  const addItem = (kind) => setWorkItem({ kind, title: "" });

  return (
    <div className="cv-page">
      <button onClick={() => navigate("/workspaces")} className="mb-4 inline-flex items-center gap-1 rounded-md text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground" data-testid="back-button"><ArrowLeft className="size-3.5" />All client workspaces</button>

      <header className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <Avatar name={workspace.name} size="lg" />
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold leading-7 tracking-tight text-foreground">{workspace.name}</h1>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-muted-foreground">
              <StatusDot tone={HEALTH_TONE[health.band]}>{humanize(health.band)} <span className="tabular text-muted-foreground">{health.score}</span></StatusDot>
              <span aria-hidden="true">·</span><span className="truncate">{company?.name || "No company linked"}</span>
              <span aria-hidden="true">·</span><span><span className="capitalize">{workspace.stage}</span> lifecycle stage</span>
              {workspace.created_at && <><span aria-hidden="true" className="hidden sm:inline">·</span><span className="hidden sm:inline">Since {shortDate(workspace.created_at, true)}</span></>}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button size="sm"><Plus className="size-3.5" />New<ChevronDown className="size-3.5 opacity-70" /></Button></DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuItem onSelect={() => setCmtDialog(true)}><Handshake className="size-4" />Commitment</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => addItem("task")}><ClipboardList className="size-4" />Task</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => addItem("deliverable")}><FileCheck2 className="size-4" />Deliverable</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => addItem("request")}><Inbox className="size-4" />Client request</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => addItem("approval")}><ShieldCheck className="size-4" />Approval</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      <StatStrip className="mb-6" items={[
        { label: "Health score", value: health.score, tone: health.band === "healthy" ? "success" : health.band === "at_risk" ? "warning" : "danger", detail: riskFactors ? `${riskFactors} risk factor${riskFactors === 1 ? "" : "s"}` : "No penalties", onClick: () => setActiveTab("overview") },
        { label: "Open commitments", value: openCommitments.length, detail: breached || atRisk ? <span className={breached ? "text-red-600" : "text-amber-700"}>{[atRisk && `${atRisk} at risk`, breached && `${breached} breached`].filter(Boolean).join(" · ")}</span> : "None at risk", onClick: () => setActiveTab("commitments") },
        { label: "Open tasks", value: openTasks.length, detail: overdueTasks ? <span className="text-red-600">{overdueTasks} overdue</span> : "None overdue", onClick: () => setActiveTab("tasks") },
        { label: "Pending approvals", value: pendingApprovals, detail: pendingApprovals ? <span className="text-amber-700">Awaiting a decision</span> : `${openRequests} open client request${openRequests === 1 ? "" : "s"}`, onClick: () => setActiveTab("approvals") },
      ]} />

      <div className="flex flex-col gap-8 lg:flex-row lg:gap-0">
        <div className="min-w-0 flex-1 lg:pr-6">
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <div className="border-b border-border">
              <TabsList className={TAB_LIST}>
                <TabsTrigger value="overview" className={TAB} data-testid="tab-overview">Overview</TabsTrigger>
                <TabsTrigger value="commitments" className={TAB} data-testid="tab-commitments">Commitments<TabCount value={commitments.length} /></TabsTrigger>
                <TabsTrigger value="tasks" className={TAB} data-testid="tab-tasks">Tasks<TabCount value={tasks.length} /></TabsTrigger>
                <TabsTrigger value="deliverables" className={TAB} data-testid="tab-deliverables">Deliverables<TabCount value={deliverables.length} /></TabsTrigger>
                <TabsTrigger value="requests" className={TAB} data-testid="tab-requests">Requests<TabCount value={requests.length} /></TabsTrigger>
                <TabsTrigger value="approvals" className={TAB} data-testid="tab-approvals">Approvals<TabCount value={approvals.length} /></TabsTrigger>
                <TabsTrigger value="outcome" className={TAB} data-testid="tab-outcome">Outcomes</TabsTrigger>
                <TabsTrigger value="timeline" className={TAB} data-testid="tab-timeline">Timeline</TabsTrigger>
                <TabsTrigger value="activity" className={TAB} data-testid="tab-activity">Activity</TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="overview" className="mt-5 space-y-6">
              <NextBestActions workspaceId={id} limit={5} compact />
              <Health health={health} />
            </TabsContent>

            <TabsContent value="commitments" className="mt-5">
              <ListSection items={commitments} testid="commitments-section" onAdd={() => setCmtDialog(true)} addLabel="Commitment" emptyIcon={Handshake}
                summary={`${commitments.length} commitment${commitments.length === 1 ? "" : "s"}${atRisk ? ` · ${atRisk} at risk` : ""}${breached ? ` · ${breached} breached` : ""}`}
                extra={<Button size="sm" variant="outline" onClick={runSlaCheck} disabled={slaBusy} data-testid="run-sla-check"><ShieldAlert className="size-3.5" />{slaBusy ? "Checking…" : "Run SLA check"}</Button>}
                grid="sm:grid-cols-[minmax(0,1fr)_minmax(0,200px)_150px_140px]"
                columns={[
                  { label: "Commitment", render: (it) => <PrimaryCell title={it.title} mobileMeta={<>{it.due_date && <><DueText due={it.due_date} /> · </>}{it.owner || "unassigned"}</>} /> },
                  { label: "Owner", render: (it) => <Person value={it.owner} fallback="unassigned" /> },
                  { label: "Due", render: (it) => <DueText due={it.due_date} /> },
                  { label: "Status", render: (it) => <StatusSelect value={it.status} options={["open", "at_risk", "breached", "fulfilled"]} label={`Status of ${it.title}`} testid={`commitment-status-${it.id}`} onChange={(v) => upd(`/commitments/${it.id}`, { status: v }, "Updated")} /> },
                ]} />
            </TabsContent>

            <TabsContent value="tasks" className="mt-5">
              <ListSection items={tasks} testid="tasks-section" onAdd={() => addItem("task")} addLabel="Task"
                summary={`${openTasks.length} open of ${tasks.length}${overdueTasks ? ` · ${overdueTasks} overdue` : ""}`}
                grid="sm:grid-cols-[minmax(0,1fr)_minmax(0,200px)_150px_140px]"
                columns={[
                  { label: "Task", render: (it) => <PrimaryCell title={it.title} mobileMeta={<>{it.due_date && it.status !== "done" && <><DueText due={it.due_date} /> · </>}{it.assignee || "unassigned"}</>} /> },
                  { label: "Assignee", render: (it) => <Person value={it.assignee} fallback="unassigned" /> },
                  { label: "Due", render: (it) => it.status === "done" ? <span className="tabular text-muted-foreground">{shortDate(it.due_date) || "—"}</span> : <DueText due={it.due_date} /> },
                  { label: "Status", render: (it) => <StatusSelect value={it.status} options={["todo", "in_progress", "done"]} label={`Status of ${it.title}`} testid={`task-status-${it.id}`} onChange={(v) => upd(`/tasks/${it.id}`, { status: v }, "Updated")} /> },
                ]} />
            </TabsContent>

            <TabsContent value="deliverables" className="mt-5">
              <ListSection items={deliverables} testid="deliverables-section" onAdd={() => addItem("deliverable")} addLabel="Deliverable" emptyIcon={FileCheck2}
                summary={`${deliverables.length} deliverable${deliverables.length === 1 ? "" : "s"} · ${deliverables.filter((it) => it.status === "approved").length} approved`}
                grid="sm:grid-cols-[minmax(0,1fr)_140px]"
                columns={[
                  { label: "Deliverable", render: (it) => <PrimaryCell title={it.title} meta={it.description || "—"} /> },
                  { label: "Status", render: (it) => <StatusSelect value={it.status} options={["draft", "in_review", "approved"]} label={`Status of ${it.title}`} testid={`deliverable-status-${it.id}`} onChange={(v) => upd(`/deliverables/${it.id}`, { status: v }, "Updated")} /> },
                ]} />
            </TabsContent>

            <TabsContent value="requests" className="mt-5">
              <ListSection items={requests} testid="requests-section" onAdd={() => addItem("request")} addLabel="Request" emptyIcon={Inbox}
                summary={`${openRequests} open of ${requests.length}`}
                grid="sm:grid-cols-[minmax(0,1fr)_120px_110px_140px]"
                columns={[
                  { label: "Request", render: (it) => <PrimaryCell title={it.title} mobileMeta={<span className="capitalize">Priority: {it.priority}</span>} /> },
                  { label: "Priority", render: (it) => <StatusDot tone={PRIORITY_TONE[it.priority] || "neutral"}><span className="capitalize">{it.priority || "—"}</span></StatusDot> },
                  { label: "Created", render: (it) => <span className="tabular text-muted-foreground">{shortDate(it.created_at) || "—"}</span> },
                  { label: "Status", render: (it) => <StatusSelect value={it.status} options={["open", "in_progress", "done"]} label={`Status of ${it.title}`} testid={`request-status-${it.id}`} onChange={(v) => upd(`/client-requests/${it.id}`, { status: v }, "Updated")} /> },
                ]} />
            </TabsContent>

            <TabsContent value="approvals" className="mt-5">
              <ListSection items={approvals} testid="approvals-section" onAdd={() => addItem("approval")} addLabel="Approval" emptyIcon={ShieldCheck}
                summary={`${pendingApprovals} awaiting decision of ${approvals.length}`}
                grid="sm:grid-cols-[minmax(0,1fr)_minmax(0,180px)_auto]"
                columns={[
                  { label: "Approval", render: (it) => <PrimaryCell title={it.title} meta={<span className="capitalize">{it.kind.replace("_", " ")}<span className="sm:hidden">{it.decided_by ? ` · by ${it.decided_by}` : ""}</span></span>} /> },
                  { label: "Decided by", render: (it) => it.decided_by ? <Person value={it.decided_by} /> : <span className="text-muted-foreground">—</span> },
                  { label: "Decision", align: "right", render: (it) => it.status === "requested" ? (
                    isAdmin ? (
                      <div className="flex items-center justify-end gap-1.5">
                        <Button size="sm" className="h-7" onClick={() => upd(`/approvals/${it.id}`, { status: "approved" }, "Approved")} data-testid={`approve-${it.id}`}>Approve</Button>
                        <Button size="sm" variant="outline" className="h-7" onClick={() => upd(`/approvals/${it.id}`, { status: "rejected" }, "Rejected")} data-testid={`reject-${it.id}`}>Reject</Button>
                      </div>
                    ) : <StatusDot tone="warning">Awaiting admin</StatusDot>
                  ) : <StatusDot tone={STATUS_TONE[it.status] || "neutral"}>{humanize(it.status)}</StatusDot> },
                ]} />
            </TabsContent>

            <TabsContent value="outcome" className="mt-5">
              <OutcomeGraph workspaceId={id} />
            </TabsContent>

            <TabsContent value="timeline" className="mt-5">
              <WorkspaceTimeline workspaceId={id} />
            </TabsContent>

            <TabsContent value="activity" className="mt-5">
              <WorkspaceActivity workspaceId={id} />
            </TabsContent>
          </Tabs>
        </div>

        <aside className="space-y-8 border-t border-border pt-6 lg:w-72 lg:shrink-0 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-1">
          <Section title="Details">
            <PropertyList items={[
              { label: "Company", value: company?.name },
              { label: "Industry", value: company?.industry },
              { label: "Tier", value: company?.tier ? <span className="capitalize">{company.tier}</span> : null },
              { label: "Website", value: company?.website },
              { label: "Lifecycle", value: <StatusDot tone={STAGE_TONE[workspace.stage] || "neutral"}><span className="capitalize">{workspace.stage}</span></StatusDot> },
              { label: "Health", value: <StatusDot tone={HEALTH_TONE[health.band]}>{humanize(health.band)} · <span className="tabular">{health.score}</span></StatusDot> },
              { label: "Created", value: shortDate(workspace.created_at, true) },
              { label: "Undo window", value: isAdmin ? (
                <div className="-my-1 flex items-center gap-1.5" data-testid="undo-window-config">
                  <Input type="number" value={undoWin} onChange={(e) => setUndoWin(e.target.value)} aria-label="Undo window in minutes" className="h-7 w-12 px-2 md:text-[13px]" data-testid="undo-window-input" />
                  <span className="text-xs text-muted-foreground">min</span>
                  <Button size="sm" variant="outline" className="ml-auto h-7 px-2" onClick={saveUndoWin} data-testid="undo-window-save">Save</Button>
                </div>
              ) : <span className="tabular">{undoWin} min</span> },
            ]} />
          </Section>
          <AIPanel workspaceId={id} />
        </aside>
      </div>

      <WorkItemDialog kind={workItem.kind} title={workItem.title} onTitleChange={(title) => setWorkItem((current) => ({ ...current, title }))} open={Boolean(workItem.kind)} onOpenChange={(open) => !open && setWorkItem({ kind: null, title: "" })} busy={workItemBusy} onSubmit={submitWorkItem} />

      <Dialog open={cmtDialog} onOpenChange={setCmtDialog}>
        <DialogContent data-testid="commitment-dialog">
          <DialogHeader><DialogTitle>New commitment</DialogTitle><DialogDescription>A promise to this client, with an owner and a due date.</DialogDescription></DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5"><Label htmlFor="commitment-title">Title</Label><Input id="commitment-title" value={cmtForm.title} onChange={(e) => setCmtForm((f) => ({ ...f, title: e.target.value }))} placeholder="e.g. Deliver dashboard by Friday" data-testid="commitment-title-input" /></div>
            <div className="space-y-1.5"><Label htmlFor="commitment-owner">Owner</Label><Input id="commitment-owner" value={cmtForm.owner} onChange={(e) => setCmtForm((f) => ({ ...f, owner: e.target.value }))} placeholder="owner@example.com" data-testid="commitment-owner-input" /></div>
            <div className="space-y-1.5"><Label htmlFor="commitment-due">Due date</Label><Input id="commitment-due" type="date" value={cmtForm.due_date} onChange={(e) => setCmtForm((f) => ({ ...f, due_date: e.target.value }))} data-testid="commitment-due-input" /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCmtDialog(false)}>Cancel</Button>
            <Button onClick={submitCommitment} data-testid="commitment-submit">Add commitment</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
