import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { SurfaceEmpty, SurfaceError, SurfaceLoading } from "@/components/SurfaceState";
import { Activity, Undo2, Bot, Terminal } from "lucide-react";

const CATEGORY_COLOR = (t) => {
  if (t.includes("undone")) return "bg-gray-200 text-gray-700 border-gray-300";
  if (t.startsWith("agent") || t.startsWith("mcp")) return "bg-indigo-50 text-indigo-700 border-indigo-200";
  if (t.includes("failed") || t.includes("at_risk") || t.includes("lost")) return "bg-red-50 text-red-700 border-red-200";
  if (t.includes("completed") || t.includes("approved") || t.includes("won") || t.includes("fulfilled")) return "bg-emerald-50 text-emerald-700 border-emerald-200";
  return "bg-gray-100 text-gray-600 border-gray-200";
};

export default function Audit() {
  const { user } = useAuth();
  const [events, setEvents] = useState(null);
  const [loadError, setLoadError] = useState("");

  const load = () => {
    setLoadError("");
    api.get("/events?limit=200")
      .then((r) => setEvents(r.data || []))
      .catch((e) => {
        setLoadError(e.response?.data?.detail || "Could not load audit events.");
        setEvents(null);
      });
  };
  useEffect(() => { load(); }, []);

  const undo = async (invId) => {
    const reason = window.prompt("Reason for reversing this action (required):");
    if (reason === null) return;
    if (!reason.trim()) return toast.error("A reason is required");
    try {
      const { data } = await api.post(`/mcp/invocations/${invId}/undo`, { reason });
      toast.success(data.restored || "Reversed");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Undo failed"); }
  };

  const canUndo = (e) => user?.role === "admin" && e.event_type === "agent.run_completed" && e.payload?.executed_after_approval && e.payload?.invocation_id;

  const agentEvents = (events || []).filter((e) => String(e.event_type || "").startsWith("agent") || String(e.event_type || "").startsWith("mcp"));
  const otherCount = events ? Math.max(0, events.length - agentEvents.length) : 0;

  if (loadError) {
    return <div className="cv-page"><SurfaceError title="Audit feed unavailable" description={typeof loadError === "string" ? loadError : "Could not load audit events."} onRetry={load} testid="audit-error" /></div>;
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-display text-3xl font-bold">Automation & Audit</h1>
        <p className="text-sm text-gray-500 mt-1">Normalized domain event feed — every significant state change is recorded. Admins can reverse MCP writes.</p>
      </div>
      {!events ? <SurfaceLoading rows={2} testid="audit-loading" /> : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6" data-testid="audit-status-cards">
            <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.06em] text-gray-400 font-semibold"><Bot className="w-3.5 h-3.5" />Agent / MCP activity</div>
              <div className="font-display text-2xl font-bold mt-2 text-[#0a1628]" data-testid="audit-agent-count">{agentEvents.length}</div>
              <p className="text-xs text-gray-500 mt-1">Events tagged agent.* or mcp.* in this feed</p>
            </div>
            <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.06em] text-gray-400 font-semibold"><Activity className="w-3.5 h-3.5" />Domain events</div>
              <div className="font-display text-2xl font-bold mt-2 text-[#0a1628]">{otherCount}</div>
              <p className="text-xs text-gray-500 mt-1">CRM and workflow state changes</p>
            </div>
            <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.06em] text-gray-400 font-semibold"><Terminal className="w-3.5 h-3.5" />Observability</div>
              <p className="text-sm text-gray-600 mt-2 leading-5">Counts reflect recorded events only. Empty agent activity means no governed tool runs have been audited yet.</p>
            </div>
          </div>
          <div className="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100">
            {events.map((e) => (
              <div key={e.id} className="flex items-start gap-4 px-6 py-3.5 hover:bg-gray-50" data-testid={`event-${e.id}`}>
                <Activity className="w-4 h-4 text-gray-300 mt-1 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge className={CATEGORY_COLOR(e.event_type)}>{e.event_type}</Badge>
                    <span className="text-xs text-gray-400">{e.resource_type}</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1 truncate">
                    by {e.actor} · {new Date(e.timestamp).toLocaleString()}
                    {e.payload?.name || e.payload?.title || e.payload?.restored ? ` · ${e.payload.name || e.payload.title || e.payload.restored}` : ""}
                  </div>
                </div>
                {canUndo(e) && (
                  <Button size="sm" variant="outline" className="h-7 text-red-600 border-red-200 hover:bg-red-50 shrink-0" onClick={() => undo(e.payload.invocation_id)} data-testid={`audit-undo-${e.id}`}>
                    <Undo2 className="w-3 h-3 mr-1" />Undo
                  </Button>
                )}
                <span className="text-[10px] font-mono text-gray-300 shrink-0">{e.correlation_id}</span>
              </div>
            ))}
            {events.length === 0 && <div className="p-5"><SurfaceEmpty icon={Activity} title="No audit events yet" description="Domain, agent, and MCP events appear here after significant state changes. This empty state is intentional." testid="audit-empty" /></div>}
          </div>
        </>
      )}
    </div>
  );
}
