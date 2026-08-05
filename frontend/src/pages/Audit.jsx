import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Activity, Undo2 } from "lucide-react";

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

  const load = () => api.get("/events?limit=200").then((r) => setEvents(r.data));
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

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-display text-3xl font-bold">Automation & Audit</h1>
        <p className="text-sm text-gray-500 mt-1">Normalized domain event feed — every significant state change is recorded. Admins can reverse MCP writes.</p>
      </div>
      {!events ? <Skeleton className="h-64 rounded-xl" /> : (
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
          {events.length === 0 && <div className="px-6 py-8 text-center text-gray-400 text-sm">No events yet.</div>}
        </div>
      )}
    </div>
  );
}
