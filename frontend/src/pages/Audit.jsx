import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SurfaceError, SurfaceLoading } from "@/components/SurfaceState";
import { PageHeader, StatusDot, Toolbar, ViewTabs } from "@/components/page/Page";
import { Activity, RefreshCw, Search, Undo2 } from "lucide-react";

const CATEGORY_TONE = (t = "") => {
  if (t.includes("undone")) return "neutral";
  if (t.startsWith("agent") || t.startsWith("mcp")) return "violet";
  if (t.includes("failed") || t.includes("at_risk") || t.includes("lost")) return "danger";
  if (t.includes("completed") || t.includes("approved") || t.includes("won") || t.includes("fulfilled")) return "success";
  return "neutral";
};
const isAgentEvent = (e) => String(e.event_type || "").startsWith("agent") || String(e.event_type || "").startsWith("mcp");
const subjectOf = (e) => e.payload?.name || e.payload?.title || e.payload?.restored || "";
const formatTime = (iso) => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
};
const TH_BASE = "h-9 px-4 text-xs font-medium text-muted-foreground";
const TH = `${TH_BASE} text-left`;

function EmptyRow({ title, children, action, testid }) {
  return <div className="flex flex-col items-center px-6 py-12 text-center" data-testid={testid}>
    <span className="flex size-10 items-center justify-center rounded-full bg-muted"><Activity className="size-[18px] text-muted-foreground" aria-hidden="true" /></span>
    <h2 className="mt-3 text-sm font-medium text-foreground">{title}</h2>
    <p className="mt-1 max-w-sm text-[13px] leading-5 text-muted-foreground">{children}</p>
    {action && <div className="mt-4">{action}</div>}
  </div>;
}

export default function Audit() {
  const { user } = useAuth();
  const [events, setEvents] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [scope, setScope] = useState("all");
  const [query, setQuery] = useState("");
  const [resource, setResource] = useState("all");

  const load = () => {
    setLoadError("");
    api
      .get("/events?limit=200")
      .then((r) => setEvents(r.data || []))
      .catch((e) => {
        setLoadError(e.response?.data?.detail || "Could not load audit events.");
        setEvents(null);
      });
  };
  useEffect(() => {
    load();
  }, []);

  const undo = async (invId) => {
    const reason = window.prompt("Reason for reversing this action (required):");
    if (reason === null) return;
    if (!reason.trim()) return toast.error("A reason is required");
    try {
      const { data } = await api.post(`/mcp/invocations/${invId}/undo`, { reason });
      toast.success(data.restored || "Reversed");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Undo failed");
    }
  };

  const canUndo = (e) =>
    user?.role === "admin" && e.event_type === "agent.run_completed" && e.payload?.executed_after_approval && e.payload?.invocation_id;

  const agentEvents = (events || []).filter(isAgentEvent);
  const otherCount = events ? Math.max(0, events.length - agentEvents.length) : 0;
  const resources = useMemo(() => [...new Set((events || []).map((e) => e.resource_type).filter(Boolean))].sort(), [events]);
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (events || []).filter((e) => {
      if (scope === "agent" && !isAgentEvent(e)) return false;
      if (scope === "domain" && isAgentEvent(e)) return false;
      if (resource !== "all" && e.resource_type !== resource) return false;
      if (!needle) return true;
      return [e.event_type, e.actor, e.resource_type, subjectOf(e), e.correlation_id].some((value) => String(value || "").toLowerCase().includes(needle));
    });
  }, [events, scope, resource, query]);
  const filtered = scope !== "all" || resource !== "all" || query.trim();

  const header = (
    <PageHeader
      icon={Activity}
      title="Automation & Audit"
      count={events ? events.length : undefined}
      description="Every significant state change is recorded. Admins can reverse MCP writes."
      actions={<Button variant="outline" size="sm" onClick={load}><RefreshCw aria-hidden="true" />Refresh</Button>}
    />
  );

  if (loadError) {
    return (
      <div className="cv-page">
        {header}
        <SurfaceError
          title="Audit feed unavailable"
          description={typeof loadError === "string" ? loadError : "Could not load audit events."}
          onRetry={load}
          testid="audit-error"
        />
      </div>
    );
  }

  const agentActive = scope === "agent";
  const tabs = [
    { value: "all", label: "All events", count: events ? events.length : undefined },
    {
      value: "agent",
      label: <>Agent &amp; MCP<span className={`tabular rounded px-1 text-xs ${agentActive ? "bg-muted text-foreground" : "text-muted-foreground"}`} data-testid="audit-agent-count">{agentEvents.length}</span></>,
    },
    { value: "domain", label: "Domain", count: otherCount },
  ];

  return (
    <div className="cv-page">
      {header}
      {!events ? (
        <SurfaceLoading rows={2} testid="audit-loading" />
      ) : (
        <>
          <div data-testid="audit-status-cards">
            <ViewTabs items={tabs} value={scope} onChange={setScope} label="Event scope"
              trailing={<span className="hidden text-xs text-muted-foreground md:inline">Counts reflect recorded events only.</span>} />
          </div>
          <Toolbar>
            <div className="relative w-full sm:w-64">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter by event, actor or record" aria-label="Filter audit events" className="h-8 pl-8 text-[13px]" />
            </div>
            <Select value={resource} onValueChange={setResource}>
              <SelectTrigger aria-label="Filter by resource" className="h-8 w-[170px] text-[13px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All resources</SelectItem>
                {resources.map((type) => <SelectItem key={type} value={type}>{type}</SelectItem>)}
              </SelectContent>
            </Select>
            {filtered && <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => { setScope("all"); setResource("all"); setQuery(""); }}>Clear</Button>}
            <span className="tabular ml-auto hidden text-xs text-muted-foreground sm:inline">{visible.length} shown</span>
          </Toolbar>
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            {events.length === 0 ? (
              <EmptyRow title="No audit events yet" testid="audit-empty">
                Domain, agent, and MCP events appear here after significant state changes.
              </EmptyRow>
            ) : visible.length === 0 ? (
              <EmptyRow title={agentActive && agentEvents.length === 0 ? "No agent or MCP activity" : "No events match these filters"}
                action={<Button variant="outline" size="sm" onClick={() => { setScope("all"); setResource("all"); setQuery(""); }}>Clear filters</Button>}>
                {agentActive && agentEvents.length === 0 ? "No governed tool runs have been audited yet." : "Try a different search or resource."}
              </EmptyRow>
            ) : (
              <div className="relative overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="border-b border-border bg-muted/40">
                      <th className={TH}>Event</th>
                      <th className={`${TH} hidden sm:table-cell`}>Record</th>
                      <th className={`${TH} hidden md:table-cell`}>Actor</th>
                      <th className={`${TH_BASE} hidden text-right sm:table-cell`}>Time</th>
                      <th className={`${TH} hidden xl:table-cell`}>Correlation</th>
                      <th className={`${TH} w-0`}><span className="sr-only">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((e) => {
                      const subject = subjectOf(e);
                      return (
                        <tr key={e.id} className="border-b border-border/70 transition-colors last:border-0 hover:bg-muted/50" data-testid={`event-${e.id}`}>
                          <td className="px-4 py-2.5">
                            <div className="max-w-[240px] sm:max-w-[18rem]">
                              <StatusDot tone={CATEGORY_TONE(e.event_type)} className="flex min-w-0"><code className="min-w-0 truncate font-mono text-xs text-foreground">{e.event_type}</code></StatusDot>
                              <div className="truncate pl-3 text-xs text-muted-foreground sm:hidden">{subject || e.resource_type} · {e.actor}</div>
                              <div className="tabular truncate pl-3 text-xs text-muted-foreground sm:hidden">{formatTime(e.timestamp)}</div>
                            </div>
                          </td>
                          <td className="hidden max-w-[20rem] px-4 py-2.5 sm:table-cell">
                            <div className="truncate">
                              {subject && <span className="text-foreground">{subject}</span>}
                              <span className="text-xs text-muted-foreground">{subject ? " · " : ""}{e.resource_type}</span>
                            </div>
                          </td>
                          <td className="hidden max-w-[14rem] px-4 py-2.5 md:table-cell"><span className="block truncate font-mono text-xs text-muted-foreground">{e.actor}</span></td>
                          <td className="tabular hidden whitespace-nowrap px-4 py-2.5 text-right text-xs text-muted-foreground sm:table-cell">{formatTime(e.timestamp)}</td>
                          <td className="hidden px-4 py-2.5 xl:table-cell"><span className="font-mono text-[11px] text-muted-foreground">{e.correlation_id}</span></td>
                          <td className="px-4 py-2.5 text-right">
                            {canUndo(e) && (
                              <Button size="sm" variant="outline" className="h-7 border-red-200 text-red-700 hover:bg-red-50 hover:text-red-700" onClick={() => undo(e.payload.invocation_id)} data-testid={`audit-undo-${e.id}`}>
                                <Undo2 aria-hidden="true" />
                                Undo
                              </Button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
