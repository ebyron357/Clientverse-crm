import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, HEALTH_BAND, STATUS_COLOR } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import OutcomeGraph from "@/components/OutcomeGraph";
import { ArrowLeft, Plus, Sparkles, FileText, Mail } from "lucide-react";

function Health({ health }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm" data-testid="health-panel">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-display font-bold text-lg">Explainable Client Health</h3>
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
    <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm" data-testid="ai-panel">
      <div className="flex items-center gap-2 mb-1">
        <Sparkles className="w-4 h-4 text-indigo-600" />
        <h3 className="font-display font-bold text-lg">Evidence-backed AI</h3>
      </div>
      <p className="text-xs text-gray-400 mb-4">Grounded only in workspace records. Fact vs inference is always distinguished.</p>

      <div className="flex gap-2 mb-3">
        <Button variant={mode === "health_summary" ? "default" : "outline"} size="sm" onClick={() => setMode("health_summary")} data-testid="ai-mode-summary" className={mode === "health_summary" ? "bg-[#0A0A0A]" : ""}><FileText className="w-3.5 h-3.5 mr-1" />Health Summary</Button>
        <Button variant={mode === "draft_message" ? "default" : "outline"} size="sm" onClick={() => setMode("draft_message")} data-testid="ai-mode-draft" className={mode === "draft_message" ? "bg-[#0A0A0A]" : ""}><Mail className="w-3.5 h-3.5 mr-1" />Draft Message</Button>
      </div>
      {mode === "draft_message" && (
        <Textarea placeholder="What should the message cover?" value={instruction} onChange={(e) => setInstruction(e.target.value)} className="mb-3" data-testid="ai-instruction-input" />
      )}
      <Button onClick={run} disabled={busy} data-testid="ai-generate-button" className="bg-indigo-600 hover:bg-indigo-700 w-full">
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
    <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm" data-testid={testid}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-display font-bold text-lg">{title}</h3>
        {onAdd && <Button size="sm" variant="outline" onClick={onAdd} data-testid={`add-${testid}`}><Plus className="w-3.5 h-3.5 mr-1" />{addLabel}</Button>}
      </div>
      {items.length === 0 ? <div className="text-sm text-gray-400 py-4">Nothing here yet.</div> : (
        <div className="space-y-2">
          {items.map((it) => (
            <div key={it.id} className="flex items-center justify-between border-b border-gray-50 pb-2" data-testid={`row-${it.id}`}>
              <div className="min-w-0">
                <div className="text-sm font-medium truncate">{it.title}</div>
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

export default function WorkspaceDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [d, setD] = useState(null);
  const [undoWin, setUndoWin] = useState("60");
  const [newTitle, setNewTitle] = useState({});

  const load = useCallback(async () => {
    const { data } = await api.get(`/workspaces/${id}`);
    setD(data);
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const quickAdd = (key) => {
    const title = window.prompt(`New ${key}`);
    if (!title) return null;
    return title;
  };

  const addTask = async () => { const t = quickAdd("task"); if (t) { await api.post("/tasks", { workspace_id: id, title: t }); toast.success("Task added"); load(); } };
  const addDeliverable = async () => { const t = quickAdd("deliverable"); if (t) { await api.post("/deliverables", { workspace_id: id, title: t }); toast.success("Added"); load(); } };
  const addRequest = async () => { const t = quickAdd("request"); if (t) { await api.post("/client-requests", { workspace_id: id, title: t }); toast.success("Added"); load(); } };
  const addCommitment = async () => { const t = quickAdd("commitment"); if (t) { await api.post("/commitments", { workspace_id: id, title: t }); toast.success("Added"); load(); } };
  const addApproval = async () => { const t = quickAdd("approval"); if (t) { await api.post("/approvals", { workspace_id: id, title: t }); toast.success("Requested"); load(); } };

  const upd = async (url, body, msg) => { await api.patch(url, body); toast.success(msg); load(); };

  useEffect(() => { if (d?.workspace) setUndoWin(String(d.workspace.undo_window_minutes || 60)); }, [d]);
  const saveUndoWin = async () => {
    await api.patch(`/workspaces/${id}/undo-window`, { minutes: parseInt(undoWin) || 60 });
    toast.success("Undo window updated");
  };

  if (!d) return <div className="space-y-4"><Skeleton className="h-10 w-64" /><Skeleton className="h-64 rounded-xl" /></div>;

  const { workspace, company, tasks, deliverables, requests, approvals, commitments, health } = d;

  return (
    <div>
      <button onClick={() => navigate("/workspaces")} className="flex items-center text-sm text-gray-500 hover:text-black mb-4" data-testid="back-button"><ArrowLeft className="w-4 h-4 mr-1" />Workspaces</button>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-3xl font-bold">{workspace.name}</h1>
          <p className="text-sm text-gray-500 mt-1">{company?.name || "No company"} · <span className="capitalize">{workspace.stage}</span> stage</p>
        </div>
        <div className="flex items-center gap-3">
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
        <TabsList>
          <TabsTrigger value="commitments" data-testid="tab-commitments">Commitment Ledger</TabsTrigger>
          <TabsTrigger value="outcome" data-testid="tab-outcome">Outcome Graph</TabsTrigger>
          <TabsTrigger value="tasks" data-testid="tab-tasks">Tasks</TabsTrigger>
          <TabsTrigger value="deliverables" data-testid="tab-deliverables">Deliverables</TabsTrigger>
          <TabsTrigger value="requests" data-testid="tab-requests">Requests</TabsTrigger>
          <TabsTrigger value="approvals" data-testid="tab-approvals">Approvals</TabsTrigger>
        </TabsList>

        <TabsContent value="commitments" className="mt-6">
          <ListSection title="Commitment Ledger" items={commitments} testid="commitments-section" onAdd={addCommitment} addLabel="Commitment"
            columns={(it) => <div className="text-xs text-gray-400">{it.owner || "unassigned"}{it.due_date ? ` · due ${new Date(it.due_date).toLocaleDateString()}` : ""}</div>}
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

        <TabsContent value="tasks" className="mt-6">
          <ListSection title="Delivery Tasks" items={tasks} testid="tasks-section" onAdd={addTask} addLabel="Task"
            columns={(it) => <div className="text-xs text-gray-400">{it.assignee || "unassigned"}</div>}
            actions={(it) => (
              <Select value={it.status} onValueChange={(v) => upd(`/tasks/${it.id}`, { status: v }, "Updated")}>
                <SelectTrigger className="h-8 w-32 text-xs" data-testid={`task-status-${it.id}`}><SelectValue /></SelectTrigger>
                <SelectContent>{["todo", "in_progress", "done"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            )} />
        </TabsContent>

        <TabsContent value="deliverables" className="mt-6">
          <ListSection title="Deliverables" items={deliverables} testid="deliverables-section" onAdd={addDeliverable} addLabel="Deliverable"
            columns={(it) => <div className="text-xs text-gray-400">{it.description || "—"}</div>}
            actions={(it) => (
              <Select value={it.status} onValueChange={(v) => upd(`/deliverables/${it.id}`, { status: v }, "Updated")}>
                <SelectTrigger className="h-8 w-32 text-xs" data-testid={`deliverable-status-${it.id}`}><SelectValue /></SelectTrigger>
                <SelectContent>{["draft", "in_review", "approved"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            )} />
        </TabsContent>

        <TabsContent value="requests" className="mt-6">
          <ListSection title="Client Requests" items={requests} testid="requests-section" onAdd={addRequest} addLabel="Request"
            columns={(it) => <div className="text-xs text-gray-400 capitalize">Priority: {it.priority}</div>}
            actions={(it) => (
              <Select value={it.status} onValueChange={(v) => upd(`/client-requests/${it.id}`, { status: v }, "Updated")}>
                <SelectTrigger className="h-8 w-32 text-xs" data-testid={`request-status-${it.id}`}><SelectValue /></SelectTrigger>
                <SelectContent>{["open", "in_progress", "done"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            )} />
        </TabsContent>

        <TabsContent value="approvals" className="mt-6">
          <ListSection title="Approvals (Governance)" items={approvals} testid="approvals-section" onAdd={addApproval} addLabel="Approval"
            columns={(it) => <div className="text-xs text-gray-400 capitalize">{it.kind.replace("_", " ")}{it.decided_by ? ` · by ${it.decided_by}` : ""}</div>}
            actions={(it) => it.status === "requested" ? (
              <>
                <Button size="sm" className="h-8 bg-emerald-600 hover:bg-emerald-700" onClick={() => upd(`/approvals/${it.id}`, { status: "approved" }, "Approved")} data-testid={`approve-${it.id}`}>Approve</Button>
                <Button size="sm" variant="outline" className="h-8" onClick={() => upd(`/approvals/${it.id}`, { status: "rejected" }, "Rejected")} data-testid={`reject-${it.id}`}>Reject</Button>
              </>
            ) : <Badge className={`capitalize ${STATUS_COLOR[it.status] || STATUS_COLOR.requested}`}>{it.status}</Badge>} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
