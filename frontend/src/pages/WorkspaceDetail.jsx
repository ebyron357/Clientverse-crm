import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, formatErr, HEALTH_BAND, STATUS_COLOR } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import OutcomeGraph from "@/components/OutcomeGraph";
import WorkspaceActivity from "@/components/WorkspaceActivity";
import WorkspaceTimeline from "@/components/WorkspaceTimeline";
import { ArrowLeft, Plus, Sparkles, FileText, Mail, ShieldAlert } from "lucide-react";

function dueInfo(due) {
  if (!due) return null;
  const d = new Date(due);
  const ms = d.getTime() - Date.now();
  const days = Math.round(ms / 86400000);
  if (ms < 0) return { label: `overdue ${Math.abs(days)}d`, tone: "text-red-600" };
  if (days <= 2) return { label: `due in ${days}d`, tone: "text-amber-600" };
  return { label: `due ${d.toLocaleDateString()}`, tone: "text-gray-400" };
}

function Health({ health }) {
  return (
    <div className="cv-card p-5 sm:p-6" data-testid="health-panel">
      <div className="flex items-center justify-between mb-4">
        <div><div className="cv-eyebrow">Client health</div><h3 className="mt-1 font-display font-bold text-lg">Explainable Client Health</h3></div>
        <div className="flex items-center gap-2">
          <span className="font-display text-3xl font-bold">{health.score}</span>
          <Badge className={`capitalize ${HEALTH_BAND[health.band]}`}>{health.band.replace("_", " ")}</Badge>
        </div>
      </div>
      <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden mb-4">
        <div className={`h-full ${health.band === "healthy" ? "bg-emerald-500" : health.band === "at_risk" ? "bg-amber-500" : "bg-red-500"}`} style={{ width: `${health.score}%` }} />
      </div>
      <div className="text-xs uppercase tracking-[0.06em] text-gray-500 font-semibold mb-2">Contributing factors</div>
      <div className="space-y-2">
        {health.factors.length === 0 && <div className="text-sm text-gray-400">No penalties. Client is healthy.</div>}
        {health.factors.map((f, i) => (
          <div key={i} className="flex items-center justify-between text-sm border-b border-gray-50 pb-2">
            <div>
              <span className="font-medium">{f.factor}</span>
              <span className="text-gray-400 ml-2">{f.detail}</span>
              <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-slate-50 text-slate-500 border border-slate-200 border-dashed uppercase">{f.type}</span>
            </div>
            <span className={f.impact < 0 ? "text-red-600 font-medium" : "text-emerald-600 font-medium"}>{f.impact > 0 ? "+" : ""}{f.impact}</span>
          </div>
        ))}
      </div>
    </div>
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

  return (
    <div className="cv-card p-5 sm:p-6" data-testid="ai-panel">
      <div className="flex items-center gap-2 mb-1">
        <Sparkles className="w-4 h-4 text-[#1a9fbf]" />
        <h3 className="font-display font-bold text-lg">Evidence-backed AI</h3>
      </div>
      <p className="text-xs text-gray-400 mb-4">Grounded only in workspace records. Fact vs inference is always distinguished.</p>

      <div className="flex gap-2 mb-3">
        <Button variant={mode === "health_summary" ? "default" : "outline"} size="sm" onClick={() => setMode("health_summary")} data-testid="ai-mode-summary" className={mode === "health_summary" ? "cv-action-primary" : ""}><FileText className="w-3.5 h-3.5 mr-1" />Health Summary</Button>
        <Button variant={mode === "draft_message" ? "default" : "outline"} size="sm" onClick={() => setMode("draft_message")} data-testid="ai-mode-draft" className={mode === "draft_message" ? "cv-action-primary" : ""}><Mail className="w-3.5 h-3.5 mr-1" />Draft Message</Button>
      </div>
      {mode === "draft_message" && (
        <Textarea placeholder="What should the message cover?" value={instruction} onChange={(e) => setInstruction(e.target.value)} className="mb-3" data-testid="ai-instruction-input" />
      )}
      <Button onClick={run} disabled={busy} data-testid="ai-generate-button" className="cv-action-primary w-full">
        {busy ? "Generating…" : "Generate with evidence"}
      </Button>

      {result && (
        <div className="mt-5 space-y-4" data-testid="ai-result">
          <div className="bg-white border border-slate-900 rounded-lg p-4">
            <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-2 font-semibold">AI Output · Recommendation</div>
            <p className="text-sm whitespace-pre-wrap leading-relaxed">{result.output}</p>
          </div>

          <div className="flex flex-wrap gap-2 text-xs">
            <span className="px-2 py-1 rounded bg-amber-50 text-amber-800 border border-amber-200">Confidence: {result.confidence}</span>
            <span className="px-2 py-1 rounded bg-slate-50 text-slate-600 border border-slate-200 border-dashed">Model: {result.model_version}</span>
            <span className="px-2 py-1 rounded bg-slate-50 text-slate-600 border border-slate-200 border-dashed">Prompt {result.prompt_version} · Policy {result.policy_version}</span>
            <span className="px-2 py-1 rounded bg-slate-50 text-slate-600 border border-slate-200 border-dashed">Run {result.run_id}</span>
          </div>

          <div>
            <div className="text-xs uppercase tracking-[0.06em] text-gray-500 font-semibold mb-2">Source records ({result.sources.length})</div>
            <div className="space-y-1.5">
              {result.sources.map((s, i) => (
                <div key={i} className="flex items-center gap-2 text-xs bg-slate-50 border border-slate-200 border-dashed rounded px-2.5 py-1.5">
                  <span className="font-mono text-slate-500">{s.type}</span>
                  <span className="text-slate-700 flex-1 truncate">{s.label}</span>
                  <span className="text-slate-400">{s.status}</span>
                </div>
              ))}
              {result.sources.length === 0 && <div className="text-xs text-gray-400">No source records — output is low-confidence.</div>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ListSection({ title, items, columns, actions, onAdd, addLabel, testid }) {
  return (
    <div className="cv-card overflow-hidden" data-testid={testid}>
      <div className="cv-card-header">
        <div><h3 className="cv-card-title">{title}</h3><p className="cv-card-description">Track ownership and progress without losing the account context.</p></div>
        {onAdd && <Button size="sm" variant="outline" onClick={onAdd} data-testid={`add-${testid}`}><Plus className="w-3.5 h-3.5 mr-1" />{addLabel}</Button>}
      </div>
      {items.length === 0 ? <div className="px-5 py-10 text-center text-sm text-slate-500">Nothing here yet. Add the first {addLabel?.toLowerCase() || "record"} to make this account actionable.</div> : (
        <div className="divide-y divide-slate-100">
          {items.map((it) => (
            <div key={it.id} className="cv-data-row flex items-center justify-between gap-3 px-5 py-3.5" data-testid={`row-${it.id}`}>
              <div className="min-w-0">
                <div className="text-sm font-semibold truncate text-[#132038]">{it.title}</div>
                {columns(it)}
              </div>
              <div className="flex items-center gap-2 shrink-0">{actions(it)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function WorkItemDialog({ kind, title, onTitleChange, open, onOpenChange, busy, onSubmit }) {
  const meta = {
    task: { title: "New delivery task", description: "Capture the next accountable action for this client.", action: "Add task" },
    deliverable: { title: "New deliverable", description: "Define an artifact or output the client is expecting.", action: "Add deliverable" },
    request: { title: "New client request", description: "Log a request so it remains visible to the delivery team.", action: "Add request" },
    approval: { title: "New approval", description: "Create a governance request for an accountable decision.", action: "Request approval" },
  }[kind] || {};
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent><DialogHeader><DialogTitle className="font-display text-2xl">{meta.title}</DialogTitle><p className="text-sm leading-6 text-slate-500">{meta.description}</p></DialogHeader><div className="grid gap-1.5 py-3"><Label htmlFor="workspace-item-title">Title <span className="text-red-500">*</span></Label><Input id="workspace-item-title" value={title} onChange={(event) => onTitleChange(event.target.value)} placeholder="Describe the work clearly" autoFocus /></div><DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button disabled={busy} onClick={onSubmit} className="cv-action-primary">{busy ? "Saving…" : meta.action}</Button></DialogFooter></DialogContent></Dialog>;
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

  if (!d) return <div className="cv-page space-y-4"><Skeleton className="h-10 w-64" /><Skeleton className="h-64 rounded-2xl" /></div>;

  const { workspace, company, tasks, deliverables, requests, approvals, commitments, health } = d;

  return (
    <div className="cv-page">
      <button onClick={() => navigate("/workspaces")} className="mb-4 flex items-center text-sm font-medium text-slate-500 hover:text-[#1a9fbf]" data-testid="back-button"><ArrowLeft className="w-4 h-4 mr-1" />All client workspaces</button>
      <div className="cv-page-header mb-6">
        <div>
          <div className="cv-eyebrow">Client 360 workspace</div><h1 className="cv-page-title">{workspace.name}</h1>
          <p className="cv-page-description">{company?.name || "No company linked"} · <span className="capitalize">{workspace.stage}</span> lifecycle stage</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {user?.role === "admin" && (
            <div className="flex items-center gap-1.5" data-testid="undo-window-config">
              <span className="text-xs text-gray-400">Undo window</span>
              <Input type="number" value={undoWin} onChange={(e) => setUndoWin(e.target.value)} className="h-8 w-16 text-xs" data-testid="undo-window-input" />
              <span className="text-xs text-gray-400">min</span>
              <Button size="sm" variant="outline" className="h-8" onClick={saveUndoWin} data-testid="undo-window-save">Save</Button>
            </div>
          )}
          <Badge className={`capitalize ${HEALTH_BAND[health.band]}`}>Health {health.score}</Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div className="lg:col-span-2"><Health health={health} /></div>
        <AIPanel workspaceId={id} />
      </div>

      <Tabs defaultValue="commitments">
        <TabsList className="w-full justify-start overflow-x-auto">
          <TabsTrigger value="commitments" data-testid="tab-commitments">Commitment Ledger</TabsTrigger>
          <TabsTrigger value="outcome" data-testid="tab-outcome">Outcome Graph</TabsTrigger>
          <TabsTrigger value="activity" data-testid="tab-activity">Activity</TabsTrigger>
          <TabsTrigger value="timeline" data-testid="tab-timeline">Timeline</TabsTrigger>
          <TabsTrigger value="tasks" data-testid="tab-tasks">Tasks</TabsTrigger>
          <TabsTrigger value="deliverables" data-testid="tab-deliverables">Deliverables</TabsTrigger>
          <TabsTrigger value="requests" data-testid="tab-requests">Requests</TabsTrigger>
          <TabsTrigger value="approvals" data-testid="tab-approvals">Approvals</TabsTrigger>
        </TabsList>

        <TabsContent value="commitments" className="mt-6">
          <div className="flex justify-end mb-3">
            <Button size="sm" variant="outline" onClick={runSlaCheck} disabled={slaBusy} data-testid="run-sla-check">
              <ShieldAlert className="w-3.5 h-3.5 mr-1" />{slaBusy ? "Checking…" : "Run SLA check"}
            </Button>
          </div>
          <ListSection title="Commitment Ledger" items={commitments} testid="commitments-section" onAdd={() => setCmtDialog(true)} addLabel="Commitment"
            columns={(it) => {
              const di = dueInfo(it.due_date);
              return (
                <div className="text-xs flex items-center gap-2 flex-wrap mt-0.5">
                  <span className="text-gray-400">{it.owner || "unassigned"}</span>
                  {di && <span className={di.tone}>· {di.label}</span>}
                  <Badge className={`capitalize text-[10px] ${STATUS_COLOR[it.status] || STATUS_COLOR.open}`}>{it.status.replace("_", " ")}</Badge>
                </div>
              );
            }}
            actions={(it) => (
              <Select value={it.status} onValueChange={(v) => upd(`/commitments/${it.id}`, { status: v }, "Updated")}>
                <SelectTrigger className="h-8 w-32 text-xs" data-testid={`commitment-status-${it.id}`}><SelectValue /></SelectTrigger>
                <SelectContent>{["open", "at_risk", "breached", "fulfilled"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            )} />
        </TabsContent>

        <TabsContent value="outcome" className="mt-6">
          <OutcomeGraph workspaceId={id} />
        </TabsContent>

        <TabsContent value="activity" className="mt-6">
          <WorkspaceActivity workspaceId={id} />
        </TabsContent>

        <TabsContent value="timeline" className="mt-6">
          <WorkspaceTimeline workspaceId={id} />
        </TabsContent>

        <TabsContent value="tasks" className="mt-6">
          <ListSection title="Delivery Tasks" items={tasks} testid="tasks-section" onAdd={() => setWorkItem({ kind: "task", title: "" })} addLabel="Task"
            columns={(it) => <div className="text-xs text-gray-400">{it.assignee || "unassigned"}</div>}
            actions={(it) => (
              <Select value={it.status} onValueChange={(v) => upd(`/tasks/${it.id}`, { status: v }, "Updated")}>
                <SelectTrigger className="h-8 w-32 text-xs" data-testid={`task-status-${it.id}`}><SelectValue /></SelectTrigger>
                <SelectContent>{["todo", "in_progress", "done"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            )} />
        </TabsContent>

        <TabsContent value="deliverables" className="mt-6">
          <ListSection title="Deliverables" items={deliverables} testid="deliverables-section" onAdd={() => setWorkItem({ kind: "deliverable", title: "" })} addLabel="Deliverable"
            columns={(it) => <div className="text-xs text-gray-400">{it.description || "—"}</div>}
            actions={(it) => (
              <Select value={it.status} onValueChange={(v) => upd(`/deliverables/${it.id}`, { status: v }, "Updated")}>
                <SelectTrigger className="h-8 w-32 text-xs" data-testid={`deliverable-status-${it.id}`}><SelectValue /></SelectTrigger>
                <SelectContent>{["draft", "in_review", "approved"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            )} />
        </TabsContent>

        <TabsContent value="requests" className="mt-6">
          <ListSection title="Client Requests" items={requests} testid="requests-section" onAdd={() => setWorkItem({ kind: "request", title: "" })} addLabel="Request"
            columns={(it) => <div className="text-xs text-gray-400 capitalize">Priority: {it.priority}</div>}
            actions={(it) => (
              <Select value={it.status} onValueChange={(v) => upd(`/client-requests/${it.id}`, { status: v }, "Updated")}>
                <SelectTrigger className="h-8 w-32 text-xs" data-testid={`request-status-${it.id}`}><SelectValue /></SelectTrigger>
                <SelectContent>{["open", "in_progress", "done"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            )} />
        </TabsContent>

        <TabsContent value="approvals" className="mt-6">
          <ListSection title="Approvals (Governance)" items={approvals} testid="approvals-section" onAdd={() => setWorkItem({ kind: "approval", title: "" })} addLabel="Approval"
            columns={(it) => <div className="text-xs text-gray-400 capitalize">{it.kind.replace("_", " ")}{it.decided_by ? ` · by ${it.decided_by}` : ""}</div>}
            actions={(it) => it.status === "requested" ? (
              user?.role === "admin" ? (
              <>
                <Button size="sm" className="h-8 bg-emerald-600 hover:bg-emerald-700" onClick={() => upd(`/approvals/${it.id}`, { status: "approved" }, "Approved")} data-testid={`approve-${it.id}`}>Approve</Button>
                <Button size="sm" variant="outline" className="h-8" onClick={() => upd(`/approvals/${it.id}`, { status: "rejected" }, "Rejected")} data-testid={`reject-${it.id}`}>Reject</Button>
              </>
              ) : <Badge className="bg-amber-50 text-amber-700 border-amber-200">Awaiting admin</Badge>
            ) : <Badge className={`capitalize ${STATUS_COLOR[it.status] || STATUS_COLOR.requested}`}>{it.status}</Badge>} />
        </TabsContent>
      </Tabs>

      <WorkItemDialog kind={workItem.kind} title={workItem.title} onTitleChange={(title) => setWorkItem((current) => ({ ...current, title }))} open={Boolean(workItem.kind)} onOpenChange={(open) => !open && setWorkItem({ kind: null, title: "" })} busy={workItemBusy} onSubmit={submitWorkItem} />

      <Dialog open={cmtDialog} onOpenChange={setCmtDialog}>
        <DialogContent data-testid="commitment-dialog">
          <DialogHeader><DialogTitle>New Commitment</DialogTitle></DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1"><Label>Title</Label><Input value={cmtForm.title} onChange={(e) => setCmtForm((f) => ({ ...f, title: e.target.value }))} placeholder="e.g. Deliver dashboard by Friday" data-testid="commitment-title-input" /></div>
            <div className="space-y-1"><Label>Owner</Label><Input value={cmtForm.owner} onChange={(e) => setCmtForm((f) => ({ ...f, owner: e.target.value }))} placeholder="owner@example.com" data-testid="commitment-owner-input" /></div>
            <div className="space-y-1"><Label>Due date</Label><Input type="date" value={cmtForm.due_date} onChange={(e) => setCmtForm((f) => ({ ...f, due_date: e.target.value }))} data-testid="commitment-due-input" /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCmtDialog(false)}>Cancel</Button>
            <Button className="bg-[#0A0A0A]" onClick={submitCommitment} data-testid="commitment-submit">Add commitment</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
