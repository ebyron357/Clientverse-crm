import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { SurfaceEmpty, SurfaceError, SurfaceLoading } from "@/components/SurfaceState";
import NextBestActions from "@/components/NextBestActions";
import { ClipboardCheck, Inbox, ListChecks, Lock, RefreshCw, Route, ShieldCheck, Undo2 } from "lucide-react";

/**
 * Operations — operator visibility for the durable work queue, Second Chance recovery
 * candidates, composed recovery strategies, the approval queue, and the
 * external-component security gate.
 *
 * Every state shown here is read from the server. Nothing on this page implies a
 * capability is live when it is not: the security-gate panel reports scanner
 * configuration honestly rather than presenting the pipeline as operational, and a
 * recovery step whose channel is unauthorised is shown as blocked with the reason,
 * never as an action the operator can take.
 */

const STATUS_TONE = {
  queued: "bg-slate-50 text-slate-700 border-slate-200",
  claimed: "bg-cyan-50 text-cyan-800 border-cyan-200",
  processing: "bg-cyan-50 text-cyan-800 border-cyan-200",
  retry_scheduled: "bg-amber-50 text-amber-900 border-amber-200",
  completed: "bg-emerald-50 text-emerald-700 border-emerald-200",
  failed: "bg-red-50 text-red-700 border-red-200",
  dead_letter: "bg-red-50 text-red-800 border-red-300",
};

const GATE_STATE_TONE = {
  DISCOVERED: "bg-slate-50 text-slate-700 border-slate-200",
  UNDER_REVIEW: "bg-cyan-50 text-cyan-800 border-cyan-200",
  APPROVED: "bg-emerald-50 text-emerald-700 border-emerald-200",
  APPROVED_LIMITED: "bg-emerald-50 text-emerald-700 border-emerald-200",
  QUARANTINED: "bg-amber-50 text-amber-900 border-amber-200",
  REJECTED: "bg-red-50 text-red-700 border-red-200",
  REVOKED: "bg-red-50 text-red-800 border-red-300",
};

function StatTile({ label, value, tone = "text-[#0a1628]" }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
      <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">{label}</div>
      <div className={`mt-1 font-display text-2xl font-extrabold ${tone}`}>{value}</div>
    </div>
  );
}

function WorkQueuePanel({ isAdmin }) {
  const [items, setItems] = useState(null);
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      // "open" excludes failed and dead-lettered items, so requesting only open work
      // showed a dead-letter count an operator could never act on. Fetch the failure
      // states too, since replay is offered for exactly those.
      const [queue, failed, dead, summary] = await Promise.all([
        api.get("/work-queue", { params: { status: "open", limit: 100 } }),
        api.get("/work-queue", { params: { status: "failed", limit: 50 } }),
        api.get("/work-queue", { params: { status: "dead_letter", limit: 50 } }),
        api.get("/work-queue/stats"),
      ]);
      setItems([...(dead.data || []), ...(failed.data || []), ...(queue.data || [])]);
      setStats(summary.data || null);
    } catch (e) {
      setItems([]);
      setError(formatErr(e.response?.data?.detail) || "The work queue could not be read.");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const act = async (item, path, body, message) => {
    setBusyId(item.id);
    try {
      await api.post(`/work-queue/${item.id}/${path}`, body);
      toast.success(message);
      await load();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || "That action could not be completed");
    } finally { setBusyId(null); }
  };

  const detect = async () => {
    setBusyId("detect");
    try {
      const { data } = await api.post("/second-chance/detect");
      toast.success(`Detection complete · ${data.work_items_created} new, ${data.work_items_deduplicated} already open`);
      await load();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || "Detection could not run");
    } finally { setBusyId(null); }
  };

  if (items === null) return <SurfaceLoading rows={3} testid="work-queue-loading" />;
  if (error) return <SurfaceError title="Work queue unavailable" description={error} onRetry={load}
                                  testid="work-queue-error" />;

  return (
    <div data-testid="work-queue-panel">
      {stats ? (
        <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Open" value={stats.open} />
          <StatTile label="Retry scheduled" value={stats.retry_scheduled}
                    tone={stats.retry_scheduled ? "text-amber-700" : "text-[#0a1628]"} />
          <StatTile label="Dead letter" value={stats.dead_letter}
                    tone={stats.dead_letter ? "text-red-700" : "text-[#0a1628]"} />
          <StatTile label="Needs operator" value={stats.needs_operator}
                    tone={stats.needs_operator ? "text-red-700" : "text-[#0a1628]"} />
        </div>
      ) : null}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {isAdmin ? (
          <Button size="sm" className="cv-action-primary" onClick={detect} disabled={busyId === "detect"}
                  data-testid="run-detection">
            {busyId === "detect" ? "Detecting…" : "Run recovery detection"}
          </Button>
        ) : null}
        <Button size="sm" variant="outline" onClick={load} data-testid="work-queue-refresh">
          <RefreshCw className="mr-2 h-3.5 w-3.5" />Refresh
        </Button>
      </div>

      {items.length === 0 ? (
        <SurfaceEmpty icon={Inbox} title="No open work"
                      description="Recovery candidates and queued jobs appear here as they are detected."
                      testid="work-queue-empty" />
      ) : (
        <div className="divide-y divide-slate-100 rounded-xl border border-slate-200">
          {items.map((item) => (
            <div key={item.id} className="flex flex-wrap items-start gap-3 px-4 py-3"
                 data-testid={`work-item-${item.type}`}>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className={STATUS_TONE[item.status] || STATUS_TONE.queued}>
                    {String(item.status).replace("_", " ")}
                  </Badge>
                  <span className="text-[11px] uppercase tracking-wide text-slate-500">{item.type}</span>
                  {item.occurrence_count > 1 ? (
                    <span className="text-[11px] text-slate-400">seen {item.occurrence_count}×</span>
                  ) : null}
                </div>
                <div className="mt-1 truncate text-sm font-semibold text-[#132038]">
                  {item.payload?.title || item.type}
                </div>
                {item.payload?.reason ? (
                  <div className="mt-0.5 text-xs leading-5 text-slate-500">{item.payload.reason}</div>
                ) : null}
                <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-slate-400">
                  {item.source_ref ? <span>source {item.source_ref}</span> : null}
                  <span>attempt {item.attempts}/{item.max_attempts}</span>
                  {item.last_error ? <span className="text-red-500">{item.last_error}</span> : null}
                  {item.acknowledged_by ? <span>acknowledged by {item.acknowledged_by}</span> : null}
                </div>
              </div>
              <div className="flex shrink-0 flex-wrap gap-1.5">
                {!item.acknowledged_at ? (
                  <Button size="sm" variant="outline" className="h-7 text-xs" disabled={busyId === item.id}
                          onClick={() => act(item, "acknowledge", {}, "Acknowledged")}
                          data-testid="work-item-acknowledge">Acknowledge</Button>
                ) : null}
                <Button size="sm" variant="outline" className="h-7 text-xs" disabled={busyId === item.id}
                        onClick={() => act(item, "resolve", { resolution: "resolved" }, "Resolved")}
                        data-testid="work-item-resolve">Resolve</Button>
                {isAdmin && (item.status === "dead_letter" || item.status === "failed") ? (
                  <Button size="sm" variant="ghost" className="h-7 text-xs" disabled={busyId === item.id}
                          onClick={() => act(item, "replay", {}, "Replayed")}
                          data-testid="work-item-replay">
                    <Undo2 className="mr-1 h-3 w-3" />Replay
                  </Button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const RISK_TONE = {
  low: "bg-slate-50 text-slate-700 border-slate-200",
  medium: "bg-cyan-50 text-cyan-800 border-cyan-200",
  high: "bg-amber-50 text-amber-900 border-amber-200",
  critical: "bg-red-50 text-red-700 border-red-200",
};

function StepRow({ step }) {
  const blocked = step.status === "blocked";
  return (
    <div className="flex flex-wrap items-start gap-2 py-1" data-testid={`strategy-step-${step.status}`}>
      {blocked
        ? <Lock className="mt-0.5 h-3 w-3 shrink-0 text-amber-600" />
        : <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />}
      <div className="min-w-0 flex-1">
        <div className="text-xs font-semibold text-[#132038]">
          {step.action.replace(/_/g, " ")}
          <span className="ml-2 text-[10px] font-normal uppercase tracking-wide text-slate-400">
            {step.channel}
          </span>
        </div>
        <div className="text-[11px] leading-5 text-slate-500">{step.detail}</div>
        {blocked ? (
          <div className="text-[11px] leading-5 text-amber-700">Blocked — {step.blocked_reason}</div>
        ) : null}
      </div>
    </div>
  );
}

function RecoveryStrategiesPanel({ isAdmin }) {
  const [strategies, setStrategies] = useState(null);
  const [summary, setSummary] = useState(null);
  const [channels, setChannels] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [list, totals, authority] = await Promise.all([
        api.get("/recovery-strategies", { params: { state: "proposed", limit: 100 } }),
        api.get("/recovery-strategies/summary"),
        api.get("/recovery-strategies/channel-authority"),
      ]);
      setStrategies(list.data || []);
      setSummary(totals.data || null);
      setChannels(authority.data || null);
    } catch (e) {
      setStrategies([]);
      setError(formatErr(e.response?.data?.detail) || "Recovery strategies could not be read.");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const compose = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/recovery-strategies/compose");
      toast.success(`Composed ${data.strategies_composed} of ${data.candidates_examined} candidates`);
      await load();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || "Composition could not run");
    } finally { setBusy(false); }
  };

  if (strategies === null) return <SurfaceLoading rows={3} testid="recovery-loading" />;
  if (error) return <SurfaceError title="Recovery strategies unavailable" description={error}
                                  onRetry={load} testid="recovery-error" />;

  const unauthorized = Object.entries(channels || {})
    .filter(([, verdict]) => !verdict.authorized);

  return (
    <div data-testid="recovery-strategies-panel">
      {summary ? (
        <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
          <StatTile label="Proposed" value={summary.proposed} />
          <StatTile label="Blocked on a channel" value={summary.proposed_blocked}
                    tone={summary.proposed_blocked ? "text-amber-700" : "text-[#0a1628]"} />
          <StatTile label="Lanes in use" value={Object.keys(summary.by_lane || {}).length} />
        </div>
      ) : null}

      {unauthorized.length ? (
        <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50/60 p-4"
             data-testid="channel-authority">
          <div className="text-xs font-bold uppercase tracking-[0.12em] text-amber-900">
            Outbound channels not authorised
          </div>
          <ul className="mt-2 space-y-1">
            {unauthorized.map(([channel, verdict]) => (
              <li key={channel} className="text-[11px] leading-5 text-amber-900">
                <span className="font-semibold uppercase">{channel}</span> — {verdict.reason}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] leading-5 text-amber-800">
            Strategies are composed and queued for approval regardless. Approving one does not
            unblock its outbound steps; the block is re-checked before anything can execute.
          </p>
        </div>
      ) : null}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {isAdmin ? (
          <Button size="sm" className="cv-action-primary" onClick={compose} disabled={busy}
                  data-testid="compose-strategies">
            {busy ? "Composing…" : "Compose strategies"}
          </Button>
        ) : null}
        <Button size="sm" variant="outline" onClick={load} data-testid="recovery-refresh">
          <RefreshCw className="mr-2 h-3.5 w-3.5" />Refresh
        </Button>
      </div>

      {strategies.length === 0 ? (
        <SurfaceEmpty icon={Route} title="No proposed strategies"
                      description="Recovery candidates are turned into a recommended motion here, each with the rule that selected it and the facts it cites."
                      testid="recovery-empty" />
      ) : (
        <div className="space-y-3">
          {strategies.map((strategy) => (
            <div key={strategy.id} className="rounded-xl border border-slate-200 bg-white p-4"
                 data-testid={`strategy-${strategy.lane}`}>
              <div className="flex flex-wrap items-center gap-2">
                <Badge className={strategy.executable
                  ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                  : "bg-amber-50 text-amber-900 border-amber-200"}>
                  {strategy.executable ? "Ready" : "Blocked"}
                </Badge>
                <span className="text-sm font-semibold text-[#132038]">{strategy.title}</span>
                <span className="text-[11px] uppercase tracking-wide text-slate-500">
                  {strategy.lane.replace(/_/g, " ")}
                </span>
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-600">{strategy.rationale}</p>
              <div className="mt-1 text-[11px] text-slate-400">rule: {strategy.rule}</div>

              {strategy.facts?.length ? (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {strategy.facts.map((fact, index) => (
                    <span key={`${strategy.id}-fact-${index}`}
                          className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-600"
                          title={fact.source ? `source: ${fact.source}` : undefined}>
                      {fact.label}: {String(fact.value)}
                    </span>
                  ))}
                </div>
              ) : null}

              <div className="mt-3 border-t border-slate-100 pt-2">
                {(strategy.steps || []).map((step, index) => (
                  <StepRow key={`${strategy.id}-step-${index}`} step={step} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ApprovalQueuePanel({ isAdmin }) {
  const [requests, setRequests] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [list, totals] = await Promise.all([
        api.get("/approval-queue", { params: { status: "open", limit: 100 } }),
        api.get("/approval-queue/summary"),
      ]);
      setRequests(list.data || []);
      setSummary(totals.data || null);
    } catch (e) {
      setRequests([]);
      setError(formatErr(e.response?.data?.detail) || "The approval queue could not be read.");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const decide = async (request, decision) => {
    setBusyId(request.id);
    try {
      await api.post(`/approval-queue/${request.id}/decision`, { decision });
      toast.success(decision === "approved" ? "Approved" : "Rejected");
      await load();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || "That decision could not be recorded");
    } finally { setBusyId(null); }
  };

  if (requests === null) return <SurfaceLoading rows={3} testid="approval-queue-loading" />;
  if (error) return <SurfaceError title="Approval queue unavailable" description={error}
                                  onRetry={load} testid="approval-queue-error" />;

  return (
    <div data-testid="approval-queue-panel">
      {summary ? (
        <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
          <StatTile label="Awaiting decision" value={summary.awaiting_decision} />
          <StatTile label="Blocked on a prerequisite" value={summary.awaiting_decision_blocked}
                    tone={summary.awaiting_decision_blocked ? "text-amber-700" : "text-[#0a1628]"} />
          <StatTile label="Approved, not yet executed" value={summary.approved_awaiting_execution} />
        </div>
      ) : null}

      <div className="mb-4">
        <Button size="sm" variant="outline" onClick={load} data-testid="approval-queue-refresh">
          <RefreshCw className="mr-2 h-3.5 w-3.5" />Refresh
        </Button>
      </div>

      {requests.length === 0 ? (
        <SurfaceEmpty icon={ClipboardCheck} title="Nothing waiting on a decision"
                      description="Actions that need a person appear here — each one bound to the exact thing that would run if it is approved."
                      testid="approval-queue-empty" />
      ) : (
        <div className="divide-y divide-slate-100 rounded-xl border border-slate-200">
          {requests.map((request) => (
            <div key={request.id} className="flex flex-wrap items-start gap-3 px-4 py-3"
                 data-testid={`approval-${request.kind}`}>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className={RISK_TONE[request.risk] || RISK_TONE.medium}>
                    {request.risk} risk
                  </Badge>
                  <span className="text-[11px] uppercase tracking-wide text-slate-500">
                    {request.kind}
                  </span>
                  <span className="text-[11px] text-slate-400">
                    raised by {request.requester_kind === "agent" ? "an agent" : request.requested_by}
                  </span>
                </div>
                <div className="mt-1 text-sm font-semibold text-[#132038]">{request.title}</div>
                {request.summary ? (
                  <div className="mt-0.5 text-xs leading-5 text-slate-500">{request.summary}</div>
                ) : null}
                {request.blocked_reasons?.length ? (
                  <div className="mt-1 text-[11px] leading-5 text-amber-700">
                    Approving this will not unblock it — {request.blocked_reasons.join("; ")}
                  </div>
                ) : null}
                {request.expires_at ? (
                  <div className="mt-1 text-[11px] text-slate-400">
                    expires {new Date(request.expires_at).toLocaleString()}
                  </div>
                ) : null}
              </div>
              {isAdmin ? (
                <div className="flex shrink-0 flex-wrap gap-1.5">
                  <Button size="sm" className="h-7 bg-emerald-600 text-xs hover:bg-emerald-700"
                          disabled={busyId === request.id}
                          onClick={() => decide(request, "approved")}
                          data-testid="approval-approve">Approve</Button>
                  <Button size="sm" variant="outline" className="h-7 text-xs"
                          disabled={busyId === request.id}
                          onClick={() => decide(request, "rejected")}
                          data-testid="approval-reject">Reject</Button>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SecurityGatePanel() {
  const [status, setStatus] = useState(null);
  const [components, setComponents] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [gate, list] = await Promise.all([
        api.get("/security-gate/status"),
        api.get("/security-gate/components", { params: { limit: 100 } }),
      ]);
      setStatus(gate.data);
      setComponents(list.data || []);
    } catch (e) {
      setComponents([]);
      setError(formatErr(e.response?.data?.detail) || "The security gate could not be read.");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (components === null) return <SurfaceLoading rows={2} testid="security-gate-loading" />;
  if (error) return <SurfaceError title="Security gate unavailable" description={error} onRetry={load}
                                  testid="security-gate-error" />;

  return (
    <div data-testid="security-gate-panel">
      <div className="mb-5 rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-[#1a9fbf]" />
          <span className="text-sm font-semibold text-[#132038]">Dual gate pipeline</span>
          <Badge className={status?.operational
            ? "bg-emerald-50 text-emerald-700 border-emerald-200"
            : "bg-amber-50 text-amber-900 border-amber-200"}>
            {status?.operational ? "Operational" : "Scanners not configured"}
          </Badge>
        </div>
        <p className="mt-2 text-xs leading-5 text-slate-500">{status?.note}</p>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {(status?.scanners || []).map((scanner) => (
            <div key={scanner.scanner} className="rounded-lg border border-slate-200 px-3 py-2"
                 data-testid={`scanner-${scanner.scanner}`}>
              <div className="text-xs font-semibold text-[#132038]">{scanner.scanner}</div>
              <div className={`mt-0.5 text-[11px] ${scanner.configured ? "text-emerald-600" : "text-amber-700"}`}>
                {scanner.configured ? "configured" : "not configured"}
              </div>
            </div>
          ))}
        </div>
      </div>

      {components.length === 0 ? (
        <SurfaceEmpty icon={ShieldCheck} title="No external components registered"
                      description="External skills, MCP servers, plugins and packages appear here once registered. Registration alone grants nothing — both gates must pass before anything can execute."
                      testid="security-gate-empty" />
      ) : (
        <div className="divide-y divide-slate-100 rounded-xl border border-slate-200">
          {components.map((component) => (
            <div key={component.id} className="px-4 py-3" data-testid={`component-${component.kind}`}>
              <div className="flex flex-wrap items-center gap-2">
                <Badge className={GATE_STATE_TONE[component.state] || GATE_STATE_TONE.DISCOVERED}>
                  {component.state}
                </Badge>
                <span className="text-sm font-semibold text-[#132038]">{component.name}</span>
                <span className="text-[11px] uppercase tracking-wide text-slate-500">{component.kind}</span>
              </div>
              <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-slate-400">
                <span className="truncate">{component.source_url}</span>
                <span>version {component.version}</span>
                <span>gate A {component.gate_a?.status}</span>
                <span>gate B {component.gate_b?.status}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Operations() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.role === "admin";

  return (
    <div className="cv-page">
      <div className="cv-page-header mb-6">
        <div>
          <div className="cv-eyebrow">Operations</div>
          <h1 className="cv-page-title">Recovery &amp; automation control</h1>
          <p className="cv-page-description">
            The durable work queue, Second Chance recovery candidates and the strategies
            composed from them, the approvals those strategies wait on, ranked next best
            actions, and the security gate that governs external agent capability.
          </p>
        </div>
      </div>

      <Tabs defaultValue="actions">
        <TabsList className="w-full justify-start overflow-x-auto">
          <TabsTrigger value="actions" data-testid="tab-actions">
            <ListChecks className="mr-2 h-3.5 w-3.5" />Next best actions
          </TabsTrigger>
          <TabsTrigger value="queue" data-testid="tab-queue">
            <Inbox className="mr-2 h-3.5 w-3.5" />Work queue
          </TabsTrigger>
          <TabsTrigger value="recovery" data-testid="tab-recovery">
            <Route className="mr-2 h-3.5 w-3.5" />Recovery strategies
          </TabsTrigger>
          <TabsTrigger value="approvals" data-testid="tab-approvals">
            <ClipboardCheck className="mr-2 h-3.5 w-3.5" />Approvals
          </TabsTrigger>
          <TabsTrigger value="gate" data-testid="tab-gate">
            <ShieldCheck className="mr-2 h-3.5 w-3.5" />Security gate
          </TabsTrigger>
        </TabsList>

        <TabsContent value="actions" className="mt-5">
          <NextBestActions limit={25} compact title="Ranked across all clients"
                           onNavigate={(item) => navigate(`/workspaces/${item.workspace_id}`)} />
        </TabsContent>
        <TabsContent value="queue" className="mt-5"><WorkQueuePanel isAdmin={isAdmin} /></TabsContent>
        <TabsContent value="recovery" className="mt-5">
          <RecoveryStrategiesPanel isAdmin={isAdmin} />
        </TabsContent>
        <TabsContent value="approvals" className="mt-5">
          <ApprovalQueuePanel isAdmin={isAdmin} />
        </TabsContent>
        <TabsContent value="gate" className="mt-5"><SecurityGatePanel /></TabsContent>
      </Tabs>
    </div>
  );
}
