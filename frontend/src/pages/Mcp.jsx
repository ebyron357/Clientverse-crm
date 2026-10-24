import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SurfaceError, SurfaceLoading } from "@/components/SurfaceState";
import { PageHeader, Section, StatusDot } from "@/components/page/Page";
import { Terminal, Zap, Clock, CheckCircle2, XCircle, RotateCw, Undo2, Info } from "lucide-react";

const LEVEL_TONE = { 1: "success", 2: "info", 3: "warning", 4: "danger" };
const SERVER_TONE = { AVAILABLE: "success", BETA: "warning", ALPHA: "violet", PLANNED: "info", REQUIRES_CONFIGURATION: "warning", RESEARCHING: "neutral", DEPRECATED: "danger" };
const humanize = (value = "") => { const text = String(value).replaceAll("_", " ").toLowerCase(); return text.charAt(0).toUpperCase() + text.slice(1); };
const INVOCATION_TONE = { success: "success", pending_approval: "warning", rejected: "neutral" };
const TH_BASE = "h-9 px-4 text-xs font-medium text-muted-foreground";
const TH = `${TH_BASE} text-left`;

function Empty({ title, children, testid }) {
  return <div className="flex flex-col items-center px-6 py-10 text-center" data-testid={testid}>
    <span className="flex size-10 items-center justify-center rounded-full bg-muted"><Terminal className="size-[18px] text-muted-foreground" aria-hidden="true" /></span>
    <h3 className="mt-3 text-sm font-medium text-foreground">{title}</h3>
    {children && <p className="mt-1 max-w-sm text-[13px] leading-5 text-muted-foreground">{children}</p>}
  </div>;
}

function Metric({ value, label, className = "text-foreground" }) {
  return <div>
    <div className={`tabular text-[22px] font-semibold leading-7 tracking-tight ${className}`}>{value}</div>
    <div className="text-xs text-muted-foreground">{label}</div>
  </div>;
}

export default function Mcp() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [server, setServer] = useState(null);
  const [workspaces, setWorkspaces] = useState([]);
  const [invocations, setInvocations] = useState([]);
  const [selected, setSelected] = useState(null);
  const [args, setArgs] = useState({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState("");

  const loadHistory = useCallback(async () => {
    const r = await api.get("/mcp/invocations?limit=50");
    setInvocations(r.data || []);
  }, []);
  const load = useCallback(async () => {
    setLoadError("");
    try {
      const [t, w] = await Promise.all([api.get("/mcp/tools"), api.get("/workspaces")]);
      setData(t.data.tools);
      setServer(t.data.server);
      setWorkspaces(w.data);
      await loadHistory();
    } catch (e) {
      setLoadError(e.response?.data?.detail || "Could not load MCP console.");
      setData(null);
    }
  }, [loadHistory]);
  useEffect(() => {
    load();
  }, [load]);

  const toggleKill = async (enabled) => {
    try {
      await api.patch("/mcp/server/kill", { enabled });
      setServer({ ...server, kill_switch: enabled });
      toast.success(enabled ? "Kill switch ON — tools disabled" : "Kill switch OFF — tools live");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const pick = (tool) => {
    setSelected(tool);
    setArgs({});
    setResult(null);
  };

  const invoke = async (tool, useArgs) => {
    setBusy(true);
    setResult(null);
    try {
      const { data } = await api.post("/mcp/invoke", { tool: tool.name, args: useArgs || args, idempotency_key: null });
      setResult(data);
      toast.success(`${tool.name} → ${data.status}`);
      loadHistory();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Invocation failed");
      loadHistory();
    } finally {
      setBusy(false);
    }
  };

  const retry = async (inv) => {
    const tool = data.find((t) => t.name === inv.tool);
    if (!tool) return toast.error("Tool no longer available");
    pick(tool);
    setArgs(inv.args || {});
    invoke(tool, inv.args || {});
  };

  const undo = async (inv) => {
    const reason = window.prompt("Reason for reversing this action (required):");
    if (reason === null) return;
    if (!reason.trim()) return toast.error("A reason is required");
    try {
      const { data: res } = await api.post(`/mcp/invocations/${inv.id}/undo`, { reason });
      toast.success(res.restored || "Reversed");
      loadHistory();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Undo failed");
    }
  };

  const header = <PageHeader icon={Terminal} title="MCP Console" description="Governed MCP server — Level 1 read tools execute live through the ClientVerse policy wrapper." />;

  if (loadError) {
    return (
      <div className="cv-page">
        {header}
        <SurfaceError
          title="MCP console unavailable"
          description={typeof loadError === "string" ? loadError : "Could not load MCP console."}
          onRetry={load}
          testid="mcp-error"
        />
      </div>
    );
  }
  if (!data || !server)
    return (
      <div className="cv-page space-y-4">
        {header}
        <SurfaceLoading rows={3} testid="mcp-loading" />
      </div>
    );

  const serverLive = !server.kill_switch && server.status === "available";
  const recentFailures = invocations.filter((inv) => inv.status && inv.status !== "success" && inv.status !== "pending_approval").length;
  const recentSuccess = invocations.filter((inv) => inv.status === "success").length;

  return (
    <div className="cv-page">
      {header}

      {/* Server, runtime and activity as one strip */}
      <div className="grid overflow-hidden rounded-xl border border-border bg-card lg:grid-cols-3" data-testid="mcp-status-cards">
        <div className="grid divide-y divide-border sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:col-span-2" data-testid="mcp-server-card">
          <div className="min-w-0 px-4 py-3.5">
            <div className="text-xs font-medium text-muted-foreground">Server</div>
            <div className="mt-1 flex min-w-0 items-center gap-2">
              <span className="truncate text-sm font-semibold text-foreground">{server.name}</span>
              <span className="shrink-0 text-xs text-muted-foreground">v{server.version}</span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
              <span data-testid="mcp-server-status"><StatusDot tone={SERVER_TONE[String(server.status).toUpperCase()] || "neutral"}>{humanize(server.status)}</StatusDot></span>
              <span className="text-xs text-muted-foreground">Level 1 · {server.allowlist?.length || 0} tools allowlisted</span>
            </div>
          </div>
          <div className="flex items-start justify-between gap-4 px-4 py-3.5">
            <div className="min-w-0">
              <div className="text-xs font-medium text-muted-foreground">Runtime</div>
              <StatusDot tone={server.kill_switch ? "danger" : serverLive ? "success" : "neutral"} className="mt-1">
                <span className="text-sm font-semibold text-foreground" data-testid="mcp-runtime-label">{server.kill_switch ? "Disabled by kill switch" : serverLive ? "Live (governed)" : "Not live"}</span>
              </StatusDot>
            </div>
            <div className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
              <Switch id="mcp-kill-switch" checked={server.kill_switch} onCheckedChange={toggleKill} disabled={user?.role !== "admin"} title={user?.role !== "admin" ? "Only an admin can use the kill switch" : undefined} data-testid="mcp-kill-switch" />
              <Label htmlFor="mcp-kill-switch" className="text-xs font-normal text-muted-foreground">Kill switch</Label>
            </div>
          </div>
        </div>
        <div className="border-t border-border px-4 py-3.5 lg:border-l lg:border-t-0" data-testid="mcp-activity-card">
          <div className="text-xs font-medium text-muted-foreground">Recent activity</div>
          <div className="mt-1 flex items-end gap-6">
            <Metric value={recentSuccess} label="Succeeded" className="text-emerald-700" />
            <Metric value={recentFailures} label="Failed / rejected" className={recentFailures ? "text-red-700" : "text-foreground"} />
            <Metric value={invocations.length} label="In history" />
          </div>
        </div>
      </div>
      <p className="mt-2.5 flex items-start gap-1.5 text-xs leading-5 text-muted-foreground" data-testid="mcp-policy-card">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        Invocations are policy-wrapped. History below is operator evidence — not a claim that external agents are running outside this console.
      </p>

      <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_400px]">
        {/* Tool catalog */}
        <Section title={<span className="flex items-center gap-2">Tool catalog<span className="tabular rounded-md bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground">{data.length}</span></span>}>
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            {data.length === 0 && (
              <Empty title="No tools allowlisted" testid="mcp-tools-empty">The MCP server returned an empty catalog. Check server configuration or kill-switch policy.</Empty>
            )}
            <div className="divide-y divide-border/70">
              {data.map((tool) => {
                const active = selected?.name === tool.name;
                return (
                  <button
                    key={tool.name}
                    type="button"
                    aria-pressed={active}
                    className={`relative block w-full px-4 py-3 text-left transition-colors before:absolute before:inset-y-0 before:left-0 before:w-0.5 ${active ? "bg-muted/60 before:bg-foreground" : "before:bg-transparent hover:bg-muted/40"}`}
                    onClick={() => pick(tool)}
                    data-testid={`mcp-tool-${tool.name}`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <code className="truncate font-mono text-[13px] font-medium text-foreground">{tool.name}</code>
                      <StatusDot tone={LEVEL_TONE[tool.level] || "neutral"} className="shrink-0 text-xs">Level {tool.level}</StatusDot>
                    </div>
                    <p className="mt-0.5 text-[12.5px] leading-5 text-muted-foreground">{tool.description}</p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                      <span className="flex flex-wrap gap-1">
                        {tool.scopes.map((s) => <code key={s} className="rounded bg-muted px-1.5 py-px font-mono text-[10.5px]">{s}</code>)}
                      </span>
                      <span className="tabular inline-flex items-center gap-1"><Clock className="size-3" aria-hidden="true" />{tool.timeout_seconds}s</span>
                      <span className="tabular inline-flex items-center gap-1"><Zap className="size-3" aria-hidden="true" />{tool.rate_limit_per_min}/min</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </Section>

        {/* Run panel */}
        <Section title="Invoke" className="lg:sticky lg:top-20 lg:self-start">
          <div className="rounded-xl border border-border bg-card" data-testid="mcp-run-panel">
            {!selected ? (
              <Empty title="Select a tool to invoke.">Its arguments and result appear here.</Empty>
            ) : (
              <>
                <div className="flex items-center justify-between gap-3 border-b border-border/80 px-4 py-3">
                  <code className="truncate font-mono text-[13px] font-semibold text-foreground">{selected.name}</code>
                  <StatusDot tone={LEVEL_TONE[selected.level] || "neutral"} className="text-xs">Level {selected.level}</StatusDot>
                </div>
                <div className="space-y-3 p-4">
                  {Object.keys(selected.input_schema).length === 0 && <div className="text-[13px] text-muted-foreground">No arguments required.</div>}
                  {Object.entries(selected.input_schema).map(([field, spec]) => (
                    <div key={field} className="space-y-1">
                      <Label htmlFor={`mcp-arg-${field}`} className="font-mono text-xs">
                        {field}
                        {spec.required ? " *" : ""}
                      </Label>
                      {spec.type === "workspace" ? (
                        <Select value={args[field] || ""} onValueChange={(v) => setArgs({ ...args, [field]: v })}>
                          <SelectTrigger id={`mcp-arg-${field}`} aria-label={field} className="h-9 text-[13px]" data-testid={`mcp-arg-${field}`}>
                            <SelectValue placeholder="Select workspace" />
                          </SelectTrigger>
                          <SelectContent>
                            {workspaces.map((w) => (
                              <SelectItem key={w.id} value={w.id}>{w.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <Input
                          id={`mcp-arg-${field}`}
                          className="h-9 text-[13px]"
                          placeholder={spec.placeholder || ""}
                          value={args[field] || ""}
                          onChange={(e) => setArgs({ ...args, [field]: e.target.value })}
                          data-testid={`mcp-arg-${field}`}
                        />
                      )}
                    </div>
                  ))}
                  <Button onClick={() => invoke(selected)} disabled={busy || server.kill_switch} className="w-full" data-testid="mcp-invoke-button">
                    {busy ? "Invoking…" : server.kill_switch ? "Disabled by kill switch" : "Invoke tool"}
                  </Button>

                  {result && (
                    <div className="pt-1" data-testid="mcp-result">
                      {result.status === "pending_approval" ? (
                        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800">
                          <div className="text-xs font-medium text-amber-700">Approval required (Level 2)</div>
                          <p className="mt-0.5">{result.message}</p>
                          <p className="mt-1 font-mono text-xs text-amber-700">approval: {result.approval_id}</p>
                        </div>
                      ) : (
                        <>
                          <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                            <span className={`inline-flex items-center gap-1 font-medium ${result.status === "success" ? "text-emerald-700" : "text-red-700"}`}>
                              {result.status === "success" ? <CheckCircle2 className="size-3.5" aria-hidden="true" /> : <XCircle className="size-3.5" aria-hidden="true" />}
                              {result.status}
                            </span>
                            <span className="tabular">{result.latency_ms}ms</span>
                            <code className="font-mono">{result.id}</code>
                          </div>
                          <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-muted/50 p-3 font-mono text-xs leading-5 text-foreground/80">
                            {JSON.stringify(result.result, null, 2)}
                          </pre>
                        </>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </Section>
      </div>

      {/* Execution history */}
      <Section title="Execution history" className="mt-8">
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="relative overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border bg-muted/40">
                  <th className={TH}>Tool</th>
                  <th className={`${TH} hidden sm:table-cell`}>Status</th>
                  <th className={`${TH_BASE} hidden text-right sm:table-cell`}>Latency</th>
                  <th className={`${TH_BASE} hidden text-right sm:table-cell`}>When</th>
                  <th className={TH}><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {invocations.map((inv) => (
                  <tr key={inv.id} className="border-b border-border/70 transition-colors last:border-0 hover:bg-muted/50" data-testid={`mcp-invocation-${inv.id}`}>
                    <td className="px-4 py-2.5">
                      <code className="font-mono text-xs text-foreground">{inv.tool}</code>
                      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 sm:hidden">
                        <StatusDot tone={INVOCATION_TONE[inv.status] || "danger"} className="text-xs">{inv.status}</StatusDot>
                        {inv.error && <span className="text-xs text-red-700">{inv.error}</span>}
                      </div>
                    </td>
                    <td className="hidden px-4 py-2.5 sm:table-cell">
                      <div className="flex flex-wrap items-center gap-x-2">
                        <StatusDot tone={INVOCATION_TONE[inv.status] || "danger"}>{inv.status}</StatusDot>
                        {inv.error && <span className="text-xs text-red-700">{inv.error}</span>}
                      </div>
                    </td>
                    <td className="tabular hidden px-4 py-2.5 text-right text-muted-foreground sm:table-cell">{inv.latency_ms}ms</td>
                    <td className="tabular hidden whitespace-nowrap px-4 py-2.5 text-right text-xs text-muted-foreground sm:table-cell">{new Date(inv.timestamp).toLocaleTimeString()}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="ghost" className="h-7 px-2 text-muted-foreground sm:px-3" onClick={() => retry(inv)} data-testid={`mcp-retry-${inv.id}`}>
                          <RotateCw aria-hidden="true" />
                          <span className="sr-only sm:not-sr-only">Retry</span>
                        </Button>
                        {user?.role === "admin" && inv.level === 2 && inv.status === "success" && (
                          <Button size="sm" variant="outline" className="h-7 border-red-200 px-2 text-red-700 hover:bg-red-50 hover:text-red-700 sm:px-3" onClick={() => undo(inv)} data-testid={`mcp-undo-${inv.id}`}>
                            <Undo2 aria-hidden="true" />
                            <span className="sr-only sm:not-sr-only">Undo</span>
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {invocations.length === 0 && (
                  <tr>
                    <td colSpan={5} className="p-0">
                      <Empty title="No MCP invocations yet" testid="mcp-history-empty">
                        Successful and failed tool runs appear here after an invoke. Empty history means nothing has been executed in this tenant.
                      </Empty>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </Section>
    </div>
  );
}
