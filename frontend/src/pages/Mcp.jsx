import { useEffect, useState } from "react";
import { api, CAP_STATUS } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Terminal, ShieldAlert, Zap, Clock, CheckCircle2, XCircle, RotateCw, Undo2 } from "lucide-react";

const LEVEL_COLOR = {
  1: "bg-emerald-50 text-emerald-700 border-emerald-200",
  2: "bg-blue-50 text-blue-700 border-blue-200",
  3: "bg-orange-50 text-orange-700 border-orange-200",
  4: "bg-red-50 text-red-700 border-red-200",
};

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

  const loadHistory = async () => {
    const r = await api.get("/mcp/invocations?limit=50");
    setInvocations(r.data);
  };
  const load = async () => {
    const [t, w] = await Promise.all([api.get("/mcp/tools"), api.get("/workspaces")]);
    setData(t.data.tools); setServer(t.data.server); setWorkspaces(w.data);
    loadHistory();
  };
  useEffect(() => { load(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleKill = async (enabled) => {
    try {
      await api.patch("/mcp/server/kill", { enabled });
      setServer({ ...server, kill_switch: enabled });
      toast.success(enabled ? "Kill switch ON — tools disabled" : "Kill switch OFF — tools live");
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const pick = (tool) => { setSelected(tool); setArgs({}); setResult(null); };

  const invoke = async (tool, useArgs) => {
    setBusy(true); setResult(null);
    try {
      const { data } = await api.post("/mcp/invoke", { tool: tool.name, args: useArgs || args, idempotency_key: null });
      setResult(data);
      toast.success(`${tool.name} → ${data.status}`);
      loadHistory();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Invocation failed");
      loadHistory();
    } finally { setBusy(false); }
  };

  const retry = async (inv) => {
    const tool = data.find((t) => t.name === inv.tool);
    if (!tool) return toast.error("Tool no longer available");
    pick(tool); setArgs(inv.args || {});
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
    } catch (e) { toast.error(e.response?.data?.detail || "Undo failed"); }
  };

  if (!data) return <div className="space-y-4"><Skeleton className="h-10 w-64" /><Skeleton className="h-64 rounded-xl" /></div>;

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-display text-3xl font-bold flex items-center gap-2"><Terminal className="w-6 h-6" />MCP Console</h1>
        <p className="text-sm text-gray-500 mt-1">Governed MCP server — Level 1 read tools execute live through the ClientVerse policy wrapper.</p>
      </div>

      {/* Kill switch */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm mb-6 flex items-center justify-between" data-testid="mcp-server-card">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${server.kill_switch ? "bg-red-50" : "bg-emerald-50"}`}>
            <ShieldAlert className={`w-5 h-5 ${server.kill_switch ? "text-red-600" : "text-emerald-600"}`} />
          </div>
          <div>
            <div className="font-display font-bold">{server.name} <span className="text-xs text-gray-400 font-normal">v{server.version}</span></div>
            <div className="text-xs text-gray-500">Level 1 · {server.allowlist?.length} tools allowlisted · <Badge className={CAP_STATUS[server.status]}>{server.status}</Badge></div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-500">{server.kill_switch ? "Disabled" : "Live"}</span>
          <Switch checked={server.kill_switch} onCheckedChange={toggleKill} data-testid="mcp-kill-switch" />
          <span className="text-xs text-gray-400">Kill switch</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Tool catalog */}
        <div>
          <div className="text-xs uppercase tracking-[0.06em] text-gray-500 font-semibold mb-3">Tool Catalog</div>
          <div className="space-y-3">
            {data.map((tool) => (
              <div key={tool.name} className={`bg-white border rounded-xl p-4 shadow-sm cursor-pointer transition-colors ${selected?.name === tool.name ? "border-black" : "border-gray-200 hover:border-gray-300"}`}
                onClick={() => pick(tool)} data-testid={`mcp-tool-${tool.name}`}>
                <div className="flex items-center justify-between">
                  <span className="font-mono text-sm font-medium">{tool.name}</span>
                  <Badge className={LEVEL_COLOR[tool.level]}>Level {tool.level}</Badge>
                </div>
                <p className="text-xs text-gray-500 mt-1">{tool.description}</p>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {tool.scopes.map((s) => <span key={s} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-50 border border-gray-200 text-gray-500">{s}</span>)}
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-50 border border-slate-200 border-dashed text-slate-500 flex items-center gap-1"><Clock className="w-2.5 h-2.5" />{tool.timeout_seconds}s</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-50 border border-slate-200 border-dashed text-slate-500 flex items-center gap-1"><Zap className="w-2.5 h-2.5" />{tool.rate_limit_per_min}/min</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Run panel */}
        <div>
          <div className="text-xs uppercase tracking-[0.06em] text-gray-500 font-semibold mb-3">Invoke</div>
          <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm" data-testid="mcp-run-panel">
            {!selected ? (
              <div className="text-sm text-gray-400 py-8 text-center">Select a tool to invoke.</div>
            ) : (
              <>
                <div className="font-mono text-sm font-medium mb-3">{selected.name}</div>
                <div className="space-y-3">
                  {Object.keys(selected.input_schema).length === 0 && <div className="text-xs text-gray-400">No arguments required.</div>}
                  {Object.entries(selected.input_schema).map(([field, spec]) => (
                    <div key={field}>
                      <Label className="text-xs">{field}{spec.required ? " *" : ""}</Label>
                      {spec.type === "workspace" ? (
                        <Select value={args[field] || ""} onValueChange={(v) => setArgs({ ...args, [field]: v })}>
                          <SelectTrigger className="mt-1" data-testid={`mcp-arg-${field}`}><SelectValue placeholder="Select workspace" /></SelectTrigger>
                          <SelectContent>{workspaces.map((w) => <SelectItem key={w.id} value={w.id}>{w.name}</SelectItem>)}</SelectContent>
                        </Select>
                      ) : (
                        <Input className="mt-1" placeholder={spec.placeholder || ""} value={args[field] || ""} onChange={(e) => setArgs({ ...args, [field]: e.target.value })} data-testid={`mcp-arg-${field}`} />
                      )}
                    </div>
                  ))}
                </div>
                <Button onClick={() => invoke(selected)} disabled={busy || server.kill_switch} className="w-full mt-4 bg-[#0A0A0A] hover:bg-[#262626]" data-testid="mcp-invoke-button">
                  {busy ? "Invoking…" : server.kill_switch ? "Disabled by kill switch" : "Invoke tool"}
                </Button>

                {result && (
                  <div className="mt-4" data-testid="mcp-result">
                    {result.status === "pending_approval" ? (
                      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                        <div className="text-xs uppercase tracking-wide text-amber-700 font-semibold mb-1">Approval required (Level 2)</div>
                        <p className="text-sm text-amber-800">{result.message}</p>
                        <p className="text-xs text-amber-600 mt-2 font-mono">approval: {result.approval_id}</p>
                      </div>
                    ) : (
                      <>
                        <div className="flex flex-wrap gap-2 text-xs mb-2">
                          <span className={`px-2 py-1 rounded border flex items-center gap-1 ${result.status === "success" ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-red-50 text-red-700 border-red-200"}`}>
                            {result.status === "success" ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}{result.status}
                          </span>
                          <span className="px-2 py-1 rounded bg-slate-50 text-slate-600 border border-slate-200 border-dashed">{result.latency_ms}ms</span>
                          <span className="px-2 py-1 rounded bg-slate-50 text-slate-600 border border-slate-200 border-dashed">{result.id}</span>
                        </div>
                        <div className="bg-slate-50 border border-slate-200 border-dashed rounded-lg p-3 max-h-72 overflow-auto">
                          <pre className="text-xs font-mono text-slate-700 whitespace-pre-wrap">{JSON.stringify(result.result, null, 2)}</pre>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Execution history */}
      <div className="mt-8">
        <div className="text-xs uppercase tracking-[0.06em] text-gray-500 font-semibold mb-3">Execution History</div>
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm text-left">
            <thead><tr className="border-b border-gray-200 text-xs uppercase tracking-[0.05em] text-gray-500">
              <th className="px-5 py-3 font-semibold">Tool</th><th className="px-5 py-3 font-semibold">Status</th><th className="px-5 py-3 font-semibold">Latency</th><th className="px-5 py-3 font-semibold">When</th><th className="px-5 py-3 font-semibold"></th></tr></thead>
            <tbody>
              {invocations.map((inv) => (
                <tr key={inv.id} className="border-b border-gray-100 hover:bg-gray-50" data-testid={`mcp-invocation-${inv.id}`}>
                  <td className="px-5 py-3 font-mono text-xs">{inv.tool}</td>
                  <td className="px-5 py-3">
                    <Badge className={inv.status === "success" ? "bg-emerald-50 text-emerald-700 border-emerald-200" : inv.status === "pending_approval" ? "bg-amber-50 text-amber-700 border-amber-200" : inv.status === "rejected" ? "bg-gray-100 text-gray-600 border-gray-200" : "bg-red-50 text-red-700 border-red-200"}>{inv.status}</Badge>
                    {inv.error && <span className="text-xs text-red-500 ml-2">{inv.error}</span>}
                  </td>
                  <td className="px-5 py-3 text-gray-500">{inv.latency_ms}ms</td>
                  <td className="px-5 py-3 text-gray-400 text-xs">{new Date(inv.timestamp).toLocaleTimeString()}</td>
                  <td className="px-5 py-3">
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" className="h-7" onClick={() => retry(inv)} data-testid={`mcp-retry-${inv.id}`}><RotateCw className="w-3 h-3 mr-1" />Retry</Button>
                      {user?.role === "admin" && inv.level === 2 && inv.status === "success" && (
                        <Button size="sm" variant="outline" className="h-7 text-red-600 border-red-200 hover:bg-red-50" onClick={() => undo(inv)} data-testid={`mcp-undo-${inv.id}`}><Undo2 className="w-3 h-3 mr-1" />Undo</Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {invocations.length === 0 && <tr><td colSpan={5} className="px-5 py-8 text-center text-gray-400">No invocations yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
