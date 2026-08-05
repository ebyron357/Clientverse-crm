import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/AppShell";
import { Skeleton } from "@/components/ui/skeleton";
import { Activity } from "lucide-react";

const CATEGORY_COLOR = (t) => {
  if (t.startsWith("agent") || t.startsWith("mcp")) return "bg-indigo-50 text-indigo-700 border-indigo-200";
  if (t.includes("failed") || t.includes("at_risk") || t.includes("lost")) return "bg-red-50 text-red-700 border-red-200";
  if (t.includes("completed") || t.includes("approved") || t.includes("won") || t.includes("fulfilled")) return "bg-emerald-50 text-emerald-700 border-emerald-200";
  return "bg-gray-100 text-gray-600 border-gray-200";
};

export default function Audit() {
  const [events, setEvents] = useState(null);
  useEffect(() => { api.get("/events?limit=200").then((r) => setEvents(r.data)); }, []);

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-display text-3xl font-bold">Automation & Audit</h1>
        <p className="text-sm text-gray-500 mt-1">Normalized domain event feed — every significant state change is recorded.</p>
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
                  {e.payload?.name || e.payload?.title ? ` · ${e.payload.name || e.payload.title}` : ""}
                </div>
              </div>
              <span className="text-[10px] font-mono text-gray-300">{e.correlation_id}</span>
            </div>
          ))}
          {events.length === 0 && <div className="px-6 py-8 text-center text-gray-400 text-sm">No events yet.</div>}
        </div>
      )}
    </div>
  );
}
