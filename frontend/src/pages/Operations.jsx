import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { PageHeader, Section, StatStrip, StatusDot, ViewTabs } from "@/components/page/Page";
import { SurfaceEmpty, SurfaceError, SurfaceLoading } from "@/components/SurfaceState";
import NextBestActions from "@/components/NextBestActions";
import {
  Activity, ArrowDownLeft, ArrowUpRight, Check, CircleAlert, ClipboardCheck, Inbox, ListChecks, Lock,
  MessagesSquare, RefreshCw, Route, ShieldCheck, TriangleAlert, Undo2, X,
} from "lucide-react";

/**
 * Operations — operator visibility for the durable work queue, Second Chance recovery
 * candidates, composed recovery strategies, the approval queue, conversations, and the
 * external-component security gate.
 *
 * Every state shown here is read from the server. Nothing on this page implies a
 * capability is live when it is not: the security-gate panel reports scanner
 * configuration honestly rather than presenting the pipeline as operational, and a
 * recovery step whose channel is unauthorised is shown as blocked with the reason,
 * never as an action the operator can take. The conversations panel says plainly that no
 * delivery provider is registered rather than presenting a send button that would fail.
 */

const STATUS_TONE = {
  queued: "neutral",
  claimed: "brand",
  processing: "brand",
  retry_scheduled: "warning",
  completed: "success",
  failed: "danger",
  dead_letter: "danger",
};

const GATE_STATE_TONE = {
  DISCOVERED: "neutral",
  UNDER_REVIEW: "info",
  APPROVED: "success",
  APPROVED_LIMITED: "success",
  QUARANTINED: "warning",
  REJECTED: "danger",
  REVOKED: "danger",
};

const RISK_TONE = { low: "neutral", medium: "info", high: "warning", critical: "danger" };

const CONSENT_TONE = { granted: "success", unknown: "neutral", denied: "danger", withdrawn: "danger" };

const CONVERSATION_TONE = { open: "brand", pending: "warning", snoozed: "neutral", closed: "neutral" };

const cx = (...parts) => parts.filter(Boolean).join(" ");
const sentence = (value) => {
  const text = String(value ?? "").replace(/_/g, " ").toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
};

const RELATIVE = new Intl.RelativeTimeFormat(undefined, { numeric: "auto", style: "short" });
/** "3 min ago" / "in 2 days"; the exact timestamp goes in a title attribute beside it. */
function relativeTime(value) {
  const at = value ? new Date(value).getTime() : NaN;
  if (Number.isNaN(at)) return "";
  const seconds = Math.round((at - Date.now()) / 1000);
  const size = Math.abs(seconds);
  if (size < 45) return "just now";
  const [amount, unit] = size < 3600 ? [seconds / 60, "minute"] : size < 86400 ? [seconds / 3600, "hour"]
    : size < 604800 ? [seconds / 86400, "day"] : size < 2629800 ? [seconds / 604800, "week"]
      : size < 31557600 ? [seconds / 2629800, "month"] : [seconds / 31557600, "year"];
  return RELATIVE.format(Math.round(amount), unit);
}
const exact = (value) => (value ? new Date(value).toLocaleString() : undefined);

function Time({ value, className }) {
  if (!value) return <span className={cx("text-muted-foreground", className)}>—</span>;
  return <time dateTime={value} title={exact(value)} className={cx("tabular whitespace-nowrap text-muted-foreground", className)}>{relativeTime(value)}</time>;
}

/** A thin, soft notice: one icon, a title and a little detail. */
function Notice({ title, children, testid }) {
  return (
    <div className="flex gap-2.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-[13px] leading-5" data-testid={testid}>
      <TriangleAlert className="mt-0.5 size-4 shrink-0 text-amber-700" aria-hidden="true" />
      <div className="min-w-0 text-foreground/80">
        {title ? <div className="font-medium text-amber-700">{title}</div> : null}
        {children}
      </div>
    </div>
  );
}

const CHANNEL_LABEL = { email: "Email", sms: "SMS", phone: "Phone", internal: "Internal" };
const channelLabel = (channel) => CHANNEL_LABEL[channel] || sentence(channel);

/** The strip between the numbers and the list: when it was read, then the panel's actions. */
function PanelBar({ loadedAt, children }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="text-xs text-muted-foreground">
        {loadedAt ? <>Updated <time className="tabular" dateTime={loadedAt.toISOString()}>{loadedAt.toLocaleTimeString()}</time></> : null}
      </span>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

function RefreshButton({ onClick, testid, label }) {
  return (
    <Button size="sm" variant="outline" onClick={onClick} data-testid={testid} aria-label={label}>
      <RefreshCw aria-hidden="true" />Refresh
    </Button>
  );
}

const listShell = "overflow-hidden rounded-xl border border-border bg-card";
const rowButton = "h-7 px-2.5 text-xs";
const mono = "font-mono text-[11.5px] text-muted-foreground";

// One table per list so columns line up across rows; below `sm` each row stacks into a card.
const T = {
  table: "w-full border-collapse text-[13px]",
  head: "hidden sm:table-header-group",
  headRow: "h-9 border-b border-border bg-muted/40 text-left text-xs text-muted-foreground",
  th: "px-3 font-medium first:pl-4 last:pr-4",
  row: "block space-y-1.5 border-b border-border/70 px-4 py-3 transition-colors last:border-0 hover:bg-muted/40 sm:table-row sm:space-y-0 sm:p-0",
  td: "block sm:table-cell sm:px-3 sm:py-2.5 sm:align-top sm:first:pl-4 sm:last:pr-4",
  wide: "hidden sm:table-cell sm:px-3 sm:py-2.5 sm:align-top sm:first:pl-4 sm:last:pr-4",
};

function WorkQueuePanel({ isAdmin, onCount }) {
  const [items, setItems] = useState(null);
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [loadedAt, setLoadedAt] = useState(null);

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
      setLoadedAt(new Date());
      onCount?.(queueCount(summary.data));
    } catch (e) {
      setItems([]);
      setError(formatErr(e.response?.data?.detail) || "The work queue could not be read.");
    }
  }, [onCount]);

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
    <div className="space-y-4" data-testid="work-queue-panel">
      {stats ? (
        <StatStrip items={[
          { label: "Open", value: stats.open },
          { label: "Retry scheduled", value: stats.retry_scheduled, tone: stats.retry_scheduled ? "warning" : undefined },
          { label: "Dead letter", value: stats.dead_letter, tone: stats.dead_letter ? "danger" : undefined },
          { label: "Needs operator", value: stats.needs_operator, tone: stats.needs_operator ? "danger" : undefined },
        ]} />
      ) : null}

      <PanelBar loadedAt={loadedAt}>
        <RefreshButton onClick={load} testid="work-queue-refresh" label="Refresh work queue" />
        {isAdmin ? (
          <Button size="sm" onClick={detect} disabled={busyId === "detect"} data-testid="run-detection">
            {busyId === "detect" ? "Detecting…" : "Run recovery detection"}
          </Button>
        ) : null}
      </PanelBar>

      {items.length === 0 ? (
        <SurfaceEmpty icon={Inbox} title="No open work"
                      description="Recovery candidates and queued jobs appear here as they are detected."
                      testid="work-queue-empty" />
      ) : (
        <div className={listShell}>
          <table className={T.table}>
            <thead className={T.head}>
              <tr className={T.headRow}>
                <th className={cx(T.th, "w-36")}>Status</th><th className={T.th}>Item</th>
                <th className={cx(T.th, "w-20 text-right")}>Attempts</th><th className={cx(T.th, "w-28 text-right")}>Updated</th>
                <th className={T.th}><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
          {items.map((item) => {
            const title = item.payload?.title;
            return (
              <tr key={item.id} className={T.row} data-testid={`work-item-${item.type}`}>
                <td className={T.td}>
                  <div className="flex items-center gap-2 sm:pt-0.5">
                    <StatusDot tone={STATUS_TONE[item.status] || "neutral"}>{sentence(item.status)}</StatusDot>
                    <span className="tabular text-xs text-muted-foreground sm:hidden">
                      · attempt {item.attempts}/{item.max_attempts} · <Time value={item.updated_at || item.created_at} />
                    </span>
                  </div>
                </td>
                <td className={cx(T.td, "min-w-0")}>
                  <div className={cx("truncate font-medium text-foreground", !title && "font-mono text-[12.5px]")}>
                    {title || item.type}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
                    {title ? <span className={mono}>{item.type}</span> : null}
                    {item.source_ref ? <span>source <span className={mono}>{item.source_ref}</span></span> : null}
                    {item.occurrence_count > 1 ? <span className="tabular">seen {item.occurrence_count}×</span> : null}
                    {item.acknowledged_by ? <span>acknowledged by {item.acknowledged_by}</span> : null}
                  </div>
                  {item.payload?.reason ? (
                    <div className="mt-0.5 text-xs leading-5 text-muted-foreground">{item.payload.reason}</div>
                  ) : null}
                  {item.last_error ? (
                    <div className="mt-1 flex items-start gap-1.5 text-xs leading-5 text-red-700">
                      <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />{item.last_error}
                    </div>
                  ) : null}
                </td>
                <td className={cx(T.wide, "tabular text-right text-xs text-muted-foreground")}>
                  {item.attempts}/{item.max_attempts}
                </td>
                <td className={cx(T.wide, "text-right text-xs")}>
                  <Time value={item.updated_at || item.created_at} />
                </td>
                <td className={T.td}>
                  <div className="flex flex-wrap gap-1.5 pt-1 sm:flex-nowrap sm:justify-end sm:pt-0">
                    {!item.acknowledged_at ? (
                      <Button size="sm" variant="outline" className={rowButton} disabled={busyId === item.id}
                              onClick={() => act(item, "acknowledge", {}, "Acknowledged")}
                              data-testid="work-item-acknowledge">Acknowledge</Button>
                    ) : null}
                    <Button size="sm" variant="outline" className={rowButton} disabled={busyId === item.id}
                            onClick={() => act(item, "resolve", { resolution: "resolved" }, "Resolved")}
                            data-testid="work-item-resolve">Resolve</Button>
                    {isAdmin && (item.status === "dead_letter" || item.status === "failed") ? (
                      <Button size="sm" variant="ghost" className={rowButton} disabled={busyId === item.id}
                              onClick={() => act(item, "replay", {}, "Replayed")}
                              data-testid="work-item-replay">
                        <Undo2 aria-hidden="true" />Replay
                      </Button>
                    ) : null}
                  </div>
                </td>
              </tr>
            );
          })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function StepRow({ step }) {
  const blocked = step.status === "blocked";
  return (
    <li className="flex items-start gap-2.5 py-1.5" data-testid={`strategy-step-${step.status}`}>
      <span className="mt-[3px] flex size-3.5 shrink-0 items-center justify-center" aria-hidden="true">
        {blocked
          ? <Lock className="size-3.5 text-amber-700" />
          : <span className="size-1.5 rounded-full bg-emerald-500" />}
      </span>
      <div className="min-w-0 flex-1 text-[13px] leading-5">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-medium text-foreground">{sentence(step.action)}</span>
          <span className={mono}>{step.channel}</span>
        </div>
        {step.detail ? <div className="text-xs leading-5 text-muted-foreground">{step.detail}</div> : null}
        {blocked ? (
          <div className="text-xs leading-5 text-amber-700">Blocked — {step.blocked_reason}</div>
        ) : null}
      </div>
    </li>
  );
}

function strategyLabel(strategy) {
  // `executable` only means no channel blocks the steps. A proposal still waiting on an
  // administrator is not ready, and saying so would misrepresent the approval gate.
  if (strategy.blocked_reasons?.length) return "Blocked";
  if (strategy.state !== "approved") return "Awaiting approval";
  return "Approved";
}

function strategyTone(strategy) {
  if (strategy.blocked_reasons?.length) return "warning";
  if (strategy.state !== "approved") return "brand";
  return "success";
}

function RecoveryStrategiesPanel({ isAdmin, onCount }) {
  const [strategies, setStrategies] = useState(null);
  const [summary, setSummary] = useState(null);
  const [channels, setChannels] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loadedAt, setLoadedAt] = useState(null);

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
      setLoadedAt(new Date());
      onCount?.(totals.data?.proposed);
    } catch (e) {
      setStrategies([]);
      setError(formatErr(e.response?.data?.detail) || "Recovery strategies could not be read.");
    }
  }, [onCount]);

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

  const verdicts = Object.entries(channels || {});
  const unauthorized = verdicts.filter(([, verdict]) => !verdict.authorized);

  return (
    <div className="space-y-4" data-testid="recovery-strategies-panel">
      {summary ? (
        <StatStrip items={[
          { label: "Proposed", value: summary.proposed },
          { label: "Blocked on a channel", value: summary.proposed_blocked, tone: summary.proposed_blocked ? "warning" : undefined },
          { label: "Lanes in use", value: Object.keys(summary.by_lane || {}).length },
          {
            label: "Channels authorised",
            value: verdicts.length ? `${verdicts.length - unauthorized.length}/${verdicts.length}` : "—",
            detail: unauthorized.length ? `${unauthorized.length} not authorised` : verdicts.length ? "All authorised" : undefined,
            tone: unauthorized.length ? "warning" : undefined,
          },
        ]} />
      ) : null}

      {unauthorized.length ? (
        <Notice title="Outbound channels not authorised" testid="channel-authority">
          <ul className="mt-1 space-y-0.5">
            {unauthorized.map(([channel, verdict]) => (
              <li key={channel} className="text-xs leading-5">
                <span className="font-medium text-foreground">{channelLabel(channel)}</span> — {verdict.reason}
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
            Strategies are composed and queued for approval regardless. Approving one does not
            unblock its outbound steps; the block is re-checked before anything can execute.
          </p>
        </Notice>
      ) : null}

      <PanelBar loadedAt={loadedAt}>
        <RefreshButton onClick={load} testid="recovery-refresh" label="Refresh recovery strategies" />
        {isAdmin ? (
          <Button size="sm" onClick={compose} disabled={busy} data-testid="compose-strategies">
            {busy ? "Composing…" : "Compose strategies"}
          </Button>
        ) : null}
      </PanelBar>

      {strategies.length === 0 ? (
        <SurfaceEmpty icon={Route} title="No proposed strategies"
                      description="Each recovery candidate becomes a recommended motion here, with the rule that selected it and the facts it cites."
                      testid="recovery-empty" />
      ) : (
        <div className={cx(listShell, "divide-y divide-border/70")}>
          {strategies.map((strategy) => (
            <article key={strategy.id} className="px-4 py-3.5" data-testid={`strategy-${strategy.lane}`}>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <StatusDot tone={strategyTone(strategy)}>{strategyLabel(strategy)}</StatusDot>
                <h3 className="min-w-0 text-[13.5px] font-medium text-foreground">{strategy.title}</h3>
                <span className="text-xs text-muted-foreground">{sentence(strategy.lane)}</span>
              </div>
              {strategy.rationale ? (
                <p className="mt-1 max-w-3xl text-[13px] leading-5 text-muted-foreground">{strategy.rationale}</p>
              ) : null}

              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
                  rule: {strategy.rule}
                </span>
                {(strategy.facts || []).map((fact, index) => (
                  <span key={`${strategy.id}-fact-${index}`}
                        className="rounded-md border border-border px-1.5 py-0.5 text-[11.5px] text-muted-foreground"
                        title={fact.source ? `source: ${fact.source}` : undefined}>
                    {fact.label}: <span className="tabular text-foreground/80">{String(fact.value)}</span>
                  </span>
                ))}
              </div>

              {strategy.steps?.length ? (
                <ol className="mt-2.5 border-l border-border pl-3">
                  {strategy.steps.map((step, index) => (
                    <StepRow key={`${strategy.id}-step-${index}`} step={step} />
                  ))}
                </ol>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function ApprovalQueuePanel({ isAdmin, onCount }) {
  const [requests, setRequests] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [loadedAt, setLoadedAt] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [list, totals] = await Promise.all([
        api.get("/approval-queue", { params: { status: "open", limit: 100 } }),
        api.get("/approval-queue/summary"),
      ]);
      setRequests(list.data || []);
      setSummary(totals.data || null);
      setLoadedAt(new Date());
      onCount?.(totals.data?.awaiting_decision);
    } catch (e) {
      setRequests([]);
      setError(formatErr(e.response?.data?.detail) || "The approval queue could not be read.");
    }
  }, [onCount]);

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
    <div className="space-y-4" data-testid="approval-queue-panel">
      {summary ? (
        <StatStrip items={[
          { label: "Awaiting decision", value: summary.awaiting_decision },
          { label: "Blocked on a prerequisite", value: summary.awaiting_decision_blocked, tone: summary.awaiting_decision_blocked ? "warning" : undefined },
          { label: "Approved, not yet executed", value: summary.approved_awaiting_execution },
          {
            label: "High or critical risk",
            value: (summary.by_risk?.high || 0) + (summary.by_risk?.critical || 0),
            tone: summary.by_risk?.critical ? "danger" : summary.by_risk?.high ? "warning" : undefined,
          },
        ]} />
      ) : null}

      <PanelBar loadedAt={loadedAt}>
        <RefreshButton onClick={load} testid="approval-queue-refresh" label="Refresh approval queue" />
      </PanelBar>

      {requests.length === 0 ? (
        <SurfaceEmpty icon={ClipboardCheck} title="Nothing waiting on a decision"
                      description="Actions that need a person appear here, each bound to the exact thing that would run if approved."
                      testid="approval-queue-empty" />
      ) : (
        <div className={listShell}>
          <table className={T.table}>
            <thead className={T.head}>
              <tr className={T.headRow}>
                <th className={cx(T.th, "w-32")}>Risk</th><th className={T.th}>Request</th>
                <th className={cx(T.th, "w-44")}>Raised by</th><th className={cx(T.th, "w-28 text-right")}>Expires</th>
                {isAdmin ? <th className={T.th}><span className="sr-only">Decision</span></th> : null}
              </tr>
            </thead>
            <tbody>
              {requests.map((request) => (
                <tr key={request.id} className={T.row} data-testid={`approval-${request.kind}`}>
                  <td className={T.td}>
                    <div className="sm:pt-0.5">
                      <StatusDot tone={RISK_TONE[request.risk] || RISK_TONE.medium}>
                        {sentence(request.risk || "medium")} risk
                      </StatusDot>
                    </div>
                  </td>
                  <td className={T.td}>
                    <div className="font-medium text-foreground">{request.title}</div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
                      <span className={mono}>{request.kind}</span>
                      <span className="sm:hidden">raised by {request.requester_kind === "agent" ? "an agent" : request.requested_by}</span>
                      {request.expires_at ? <span className="sm:hidden">expires <Time value={request.expires_at} /></span> : null}
                    </div>
                    {request.summary ? (
                      <div className="mt-0.5 text-xs leading-5 text-muted-foreground">{request.summary}</div>
                    ) : null}
                    {request.blocked_reasons?.length ? (
                      <div className="mt-1 flex items-start gap-1.5 text-xs leading-5 text-amber-700">
                        <Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                        <span>Approving this will not unblock it — {request.blocked_reasons.join("; ")}</span>
                      </div>
                    ) : null}
                  </td>
                  <td className={cx(T.wide, "text-xs text-muted-foreground")}>
                    <div className="max-w-44 truncate pt-0.5">
                      {request.requester_kind === "agent" ? "An agent" : request.requested_by || "—"}
                    </div>
                  </td>
                  <td className={cx(T.wide, "text-right text-xs")}>
                    <div className="pt-0.5"><Time value={request.expires_at} /></div>
                  </td>
                  {isAdmin ? (
                    <td className={T.td}>
                      <div className="flex gap-1.5 pt-1 sm:justify-end sm:pt-0">
                        <Button size="sm" variant="outline" className={rowButton} disabled={busyId === request.id}
                                onClick={() => decide(request, "approved")}
                                data-testid="approval-approve">
                          <Check className="text-emerald-600" aria-hidden="true" />Approve
                        </Button>
                        <Button size="sm" variant="outline" className={rowButton}
                                disabled={busyId === request.id}
                                onClick={() => decide(request, "rejected")}
                                data-testid="approval-reject">
                          <X className="text-muted-foreground" aria-hidden="true" />Reject
                        </Button>
                      </div>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ConversationsPanel({ isAdmin, onCount }) {
  const [threads, setThreads] = useState(null);
  const [summary, setSummary] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loadedAt, setLoadedAt] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [list, totals] = await Promise.all([
        api.get("/conversations", { params: { status: "open", limit: 100 } }),
        api.get("/conversations/summary"),
      ]);
      setThreads(list.data || []);
      setSummary(totals.data || null);
      setLoadedAt(new Date());
      onCount?.(totals.data?.open_conversations);
    } catch (e) {
      setThreads([]);
      setError(formatErr(e.response?.data?.detail) || "Conversations could not be read.");
    }
  }, [onCount]);

  useEffect(() => { load(); }, [load]);

  const open = async (thread) => {
    setBusy(true);
    try {
      const { data } = await api.get(`/conversations/${thread.id}`);
      setSelected(data);
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || "That conversation could not be opened");
    } finally { setBusy(false); }
  };

  const act = async (path, body, message) => {
    if (!selected) return;
    setBusy(true);
    try {
      await api.post(`/conversations/${selected.id}/${path}`, body);
      toast.success(message);
      await open(selected);
      await load();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail) || "That action could not be completed");
    } finally { setBusy(false); }
  };

  if (threads === null) return <SurfaceLoading rows={3} testid="conversations-loading" />;
  if (error) return <SurfaceError title="Conversations unavailable" description={error}
                                  onRetry={load} testid="conversations-error" />;

  const providers = summary?.providers || [];
  const registered = providers.filter((p) => p.registered);

  return (
    <div className="space-y-4" data-testid="conversations-panel">
      {summary ? (
        <StatStrip items={[
          { label: "Open threads", value: summary.open_conversations },
          { label: "Agent handled", value: summary.agent_handled_open },
          { label: "Awaiting approval", value: summary.messages_awaiting_approval },
          { label: "Blocked messages", value: summary.messages_blocked, tone: summary.messages_blocked ? "warning" : undefined },
        ]} />
      ) : null}

      {registered.length === 0 ? (
        <Notice title="No delivery provider is registered" testid="no-provider-notice">
          <p className="text-xs leading-5">
            Conversations, drafts, consent and handoff all work. Nothing can be sent: no channel
            adapter has been built or certified, so every outbound attempt is refused and the
            refusal names the precondition that stopped it.
          </p>
        </Notice>
      ) : null}

      <PanelBar loadedAt={loadedAt}>
        <RefreshButton onClick={load} testid="conversations-refresh" label="Refresh conversations" />
      </PanelBar>

      {threads.length === 0 ? (
        <SurfaceEmpty icon={MessagesSquare} title="No open conversations"
                      description="Threads appear here with their channel, who is handling them, and what the counterparty has consented to."
                      testid="conversations-empty" />
      ) : (
        <div className={cx(listShell, "lg:grid lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]")}>
          <div className="divide-y divide-border/70 lg:border-r lg:border-border">
            {threads.map((thread) => {
              const active = selected?.id === thread.id;
              return (
                <button key={thread.id} type="button" onClick={() => open(thread)} aria-current={active ? "true" : undefined}
                        className={cx("relative block w-full px-4 py-3 text-left transition-colors hover:bg-muted/50",
                          active && "bg-muted/60 before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:bg-foreground")}
                        data-testid={`conversation-${thread.channel}`}>
                  <div className="truncate text-[13px] font-medium text-foreground">{thread.subject || "No subject"}</div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5">
                    <StatusDot tone={CONVERSATION_TONE[thread.status] || CONVERSATION_TONE.open} className="text-xs">
                      {sentence(thread.status)}
                    </StatusDot>
                    <span className={mono}>{thread.channel}</span>
                    <StatusDot tone={CONSENT_TONE[thread.consent?.state] || CONSENT_TONE.unknown} className="text-xs">
                      consent {thread.consent?.state}
                    </StatusDot>
                  </div>
                  <div className="mt-1 truncate text-xs text-muted-foreground">
                    handled by {thread.handled_by}
                    {thread.assignee ? ` · ${thread.assignee}` : ""}
                    {` · ${thread.message_count} message(s)`}
                  </div>
                </button>
              );
            })}
          </div>

          <div className="border-t border-border p-4 lg:border-t-0">
            {!selected ? (
              <div className="flex h-full min-h-[160px] items-center justify-center text-[13px] text-muted-foreground">
                Select a conversation to read it.
              </div>
            ) : (
              <div data-testid="conversation-detail">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold text-foreground">{selected.subject || "No subject"}</h3>
                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5">
                      <StatusDot tone={CONSENT_TONE[selected.consent?.state] || CONSENT_TONE.unknown} className="text-xs">
                        consent {selected.consent?.state}
                      </StatusDot>
                      {selected.consent?.basis ? (
                        <span className="text-xs text-muted-foreground">Basis: {selected.consent.basis}</span>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <Button size="sm" variant="outline" className={rowButton} disabled={busy}
                            onClick={() => act("handoff",
                              { to: selected.handled_by === "agent" ? "human" : "agent" },
                              "Handoff recorded")}
                            data-testid="conversation-handoff">
                      Hand to {selected.handled_by === "agent" ? "human" : "agent"}
                    </Button>
                    {selected.status !== "closed" ? (
                      <Button size="sm" variant="ghost" className={rowButton} disabled={busy}
                              onClick={() => act("status", { status: "closed" }, "Closed")}
                              data-testid="conversation-close">Close</Button>
                    ) : null}
                  </div>
                </div>
                {isAdmin && selected.consent?.state !== "granted" ? (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Consent is recorded by an administrator with a stated basis.
                  </p>
                ) : null}

                <ol className="mt-4 space-y-3 border-t border-border pt-4">
                  {(selected.messages || []).length === 0 ? (
                    <li className="text-[13px] text-muted-foreground">No messages yet.</li>
                  ) : (
                    selected.messages.map((message) => {
                      const DirectionIcon = message.direction === "inbound" ? ArrowDownLeft : ArrowUpRight;
                      return (
                        <li key={message.id} className="flex gap-3" data-testid={`message-${message.status}`}>
                          <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground" aria-hidden="true">
                            <DirectionIcon className="size-3.5" />
                          </span>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs">
                              <span className="font-medium capitalize text-foreground">{message.direction}</span>
                              <StatusDot tone={message.status === "blocked" ? "warning" : "neutral"} className="text-xs">
                                {sentence(message.status)}
                              </StatusDot>
                              <Time value={message.sent_at || message.created_at} className="text-xs" />
                            </div>
                            <p className="mt-1 whitespace-pre-wrap text-[13px] leading-5 text-foreground/80">
                              {message.body}
                            </p>
                            {message.blocked_detail ? (
                              <p className="mt-1 text-xs leading-5 text-amber-700">{message.blocked_detail}</p>
                            ) : null}
                          </div>
                        </li>
                      );
                    })
                  )}
                </ol>
              </div>
            )}
          </div>
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

  const scanners = status?.scanners || [];
  const configured = scanners.filter((scanner) => scanner.configured).length;

  return (
    <div className="space-y-5" data-testid="security-gate-panel">
      <Section card
        title={<span className="flex items-center gap-2"><ShieldCheck className="size-4 text-muted-foreground" aria-hidden="true" />Dual gate pipeline</span>}
        actions={(
          <StatusDot tone={status?.operational ? "success" : "warning"}>
            {status?.operational ? "Operational" : "Scanners not configured"}
          </StatusDot>
        )}>
        {status?.note ? <p className="px-4 pt-3 text-[13px] leading-5 text-muted-foreground">{status.note}</p> : null}
        <div className="px-4 pb-4 pt-3">
          <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
            <span className="font-medium">Scanners</span>
            <span className="tabular">{configured} of {scanners.length} configured</span>
          </div>
          <ul className="divide-y divide-border/70 rounded-lg border border-border">
            {scanners.map((scanner) => (
              <li key={scanner.scanner} className="flex items-center justify-between gap-3 px-3 py-2"
                  data-testid={`scanner-${scanner.scanner}`}>
                <span className="truncate font-mono text-xs text-foreground">{scanner.scanner}</span>
                <StatusDot tone={scanner.configured ? "success" : "warning"} className="text-xs">
                  {scanner.configured ? "configured" : "not configured"}
                </StatusDot>
              </li>
            ))}
          </ul>
        </div>
      </Section>

      {components.length === 0 ? (
        <SurfaceEmpty icon={ShieldCheck} title="No external components registered"
                      description="External skills, MCP servers, plugins and packages appear here once registered. Registration alone grants nothing — both gates must pass before anything can execute."
                      testid="security-gate-empty" />
      ) : (
        <div className={cx(listShell, "overflow-x-auto")}>
          <table className={T.table}>
            <thead className={T.head}>
              <tr className={T.headRow}>
                <th className={cx(T.th, "w-36")}>State</th><th className={T.th}>Component</th><th className={T.th}>Source</th>
                <th className={cx(T.th, "w-24")}>Version</th><th className={cx(T.th, "w-28")}>Gate A</th><th className={cx(T.th, "w-28")}>Gate B</th>
              </tr>
            </thead>
            <tbody>
              {components.map((component) => (
                <tr key={component.id} className={T.row} data-testid={`component-${component.kind}`}>
                  <td className={T.td}>
                    <StatusDot tone={GATE_STATE_TONE[component.state] || "neutral"}>{sentence(component.state)}</StatusDot>
                  </td>
                  <td className={T.td}>
                    <div className="font-medium text-foreground">{component.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {component.kind}
                      <span className="sm:hidden"> · version <span className="tabular">{component.version}</span> · gate A {sentence(component.gate_a?.status)} · gate B {sentence(component.gate_b?.status)}</span>
                    </div>
                  </td>
                  <td className={T.td}>
                    <div className="max-w-full truncate font-mono text-[11.5px] text-muted-foreground sm:max-w-[280px]" title={component.source_url}>
                      {component.source_url}
                    </div>
                  </td>
                  <td className={cx(T.wide, "tabular font-mono text-[11.5px] text-muted-foreground")}>{component.version}</td>
                  <td className={cx(T.wide, "text-xs text-muted-foreground")}>{sentence(component.gate_a?.status)}</td>
                  <td className={cx(T.wide, "text-xs text-muted-foreground")}>{sentence(component.gate_b?.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const TABS = ["actions", "queue", "recovery", "approvals", "conversations", "gate"];

const queueCount = (stats) => (stats ? (stats.open || 0) + (stats.failed || 0) + (stats.dead_letter || 0) : undefined);

/**
 * Counts for the view tabs, read from the same summaries each panel shows, so a tab says how
 * much is waiting before it is opened. A panel reports its fresh figure after every reload.
 */
function useTabCounts() {
  const [counts, setCounts] = useState({});
  useEffect(() => {
    let live = true;
    Promise.allSettled([
      api.get("/work-queue/stats"),
      api.get("/recovery-strategies/summary"),
      api.get("/approval-queue/summary"),
      api.get("/conversations/summary"),
    ]).then(([queue, recovery, approvals, conversations]) => {
      if (!live) return;
      const read = (result, pick) => (result.status === "fulfilled" ? pick(result.value.data || {}) : undefined);
      setCounts((current) => ({
        queue: read(queue, queueCount),
        recovery: read(recovery, (data) => data.proposed),
        approvals: read(approvals, (data) => data.awaiting_decision),
        conversations: read(conversations, (data) => data.open_conversations),
        ...current,
      }));
    });
    return () => { live = false; };
  }, []);
  const report = useCallback((key) => (value) => {
    setCounts((current) => (current[key] === value ? current : { ...current, [key]: value }));
  }, []);
  return [counts, report];
}

export default function Operations() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const isAdmin = user?.role === "admin";
  // Several module-registry entries deep-link to a tab of this page, so the tab is part of
  // the URL rather than local state.
  const requested = params.get("tab");
  const tab = TABS.includes(requested) ? requested : "actions";
  const [counts, report] = useTabCounts();
  const onQueue = useMemo(() => report("queue"), [report]);
  const onRecovery = useMemo(() => report("recovery"), [report]);
  const onApprovals = useMemo(() => report("approvals"), [report]);
  const onConversations = useMemo(() => report("conversations"), [report]);

  const views = [
    { value: "actions", label: "Next best actions", icon: ListChecks, testid: "tab-actions" },
    { value: "queue", label: "Work queue", icon: Inbox, count: counts.queue, testid: "tab-queue" },
    { value: "recovery", label: "Recovery strategies", icon: Route, count: counts.recovery, testid: "tab-recovery" },
    { value: "approvals", label: "Approvals", icon: ClipboardCheck, count: counts.approvals, testid: "tab-approvals" },
    { value: "conversations", label: "Conversations", icon: MessagesSquare, count: counts.conversations, testid: "tab-conversations" },
    { value: "gate", label: "Security gate", icon: ShieldCheck, testid: "tab-gate" },
  ];
  const active = views.find((view) => view.value === tab);

  // On a narrow screen the tab strip scrolls sideways; keep the open view's tab in sight,
  // including when the page is opened on a deep link such as ?tab=gate.
  const tabsRef = useRef(null);
  useEffect(() => {
    const node = tabsRef.current?.querySelector(`[data-testid="tab-${tab}"]`);
    const strip = node?.parentElement;
    if (!node || !strip || strip.scrollWidth <= strip.clientWidth) return;
    const offset = node.getBoundingClientRect().left - strip.getBoundingClientRect().left;
    strip.scrollTo({ left: strip.scrollLeft + offset - (strip.clientWidth - node.offsetWidth) / 2 });
  }, [tab, counts]);

  return (
    <div className="cv-page">
      <PageHeader icon={Activity} title="Operations"
                  description="Work queue, recovery strategies, approvals, conversations and the security gate." />

      <div ref={tabsRef}>
        <ViewTabs label="Operations views" items={views} value={tab}
                  onChange={(next) => setParams(next === "actions" ? {} : { tab: next }, { replace: true })} />
      </div>

      <div role="tabpanel" aria-label={active?.label} className="pt-5">
        {tab === "actions" ? (
          <NextBestActions limit={25} compact title="Ranked across all clients"
                           onNavigate={(item) => navigate(`/workspaces/${item.workspace_id}`)} />
        ) : null}
        {tab === "queue" ? <WorkQueuePanel isAdmin={isAdmin} onCount={onQueue} /> : null}
        {tab === "recovery" ? <RecoveryStrategiesPanel isAdmin={isAdmin} onCount={onRecovery} /> : null}
        {tab === "approvals" ? <ApprovalQueuePanel isAdmin={isAdmin} onCount={onApprovals} /> : null}
        {tab === "conversations" ? <ConversationsPanel isAdmin={isAdmin} onCount={onConversations} /> : null}
        {tab === "gate" ? <SecurityGatePanel /> : null}
      </div>
    </div>
  );
}
