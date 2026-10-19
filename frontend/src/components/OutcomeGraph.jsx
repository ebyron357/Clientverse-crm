import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Section, StatusDot } from "@/components/page/Page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, ReferenceLine, CartesianGrid } from "recharts";
import { Target, Handshake, Activity, Plus, ArrowRight, Check, CornerDownRight, LineChart as LineChartIcon } from "lucide-react";

const GOAL_TONE = { on_track: "success", at_risk: "warning", off_track: "danger" };
const CMT_TONE = { open: "info", at_risk: "warning", breached: "danger", fulfilled: "success" };
const BAND_TONE = { healthy: "success", at_risk: "warning", critical: "danger" };
const sentence = (value) => { const text = String(value || "").replace(/_/g, " "); return text.charAt(0).toUpperCase() + text.slice(1); };

// Chart ink comes from the theme tokens, so the chart follows light and dark mode.
const INK = {
  line: "hsl(var(--brand))",
  axis: "hsl(var(--muted-foreground))",
  grid: "hsl(var(--border))",
  surface: "hsl(var(--card))",
  healthy: "hsl(var(--chart-3))",
  warning: "hsl(var(--chart-4))",
};

/** Column heading for one node of the graph (Goals, Commitments, Health). */
function NodeHeading({ icon: Icon, children, count }) {
  return <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
    <Icon className="size-3.5" aria-hidden="true" />{children}
    {count !== undefined && <span className="tabular rounded bg-muted px-1 text-[11px]">{count}</span>}
  </div>;
}

function Connector() {
  return <div className="hidden items-start justify-center pt-9 text-muted-foreground/60 lg:flex" aria-hidden="true"><ArrowRight className="size-4" /></div>;
}

function HealthTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return <div className="rounded-lg border border-border bg-popover px-2.5 py-1.5 text-xs shadow-xs">
    <div className="text-muted-foreground">{label}</div>
    <div className="tabular font-medium text-foreground">Health {payload[0].value}</div>
  </div>;
}

export default function OutcomeGraph({ workspaceId }) {
  const [d, setD] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", target: "", target_value: "", unit: "" });
  const [edits, setEdits] = useState({});

  const load = useCallback(async () => {
    const { data } = await api.get(`/workspaces/${workspaceId}/outcome-graph`);
    setD(data);
  }, [workspaceId]);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!form.title) return;
    await api.post("/outcomes", {
      workspace_id: workspaceId, title: form.title, target: form.target || null,
      target_value: form.target_value ? parseFloat(form.target_value) : null, unit: form.unit || null,
      current_value: 0, status: "on_track", linked_commitment_ids: [],
    });
    toast.success("Outcome added"); setOpen(false); setForm({ title: "", target: "", target_value: "", unit: "" }); load();
  };

  const saveProgress = async (g) => {
    const val = edits[g.id];
    if (val === undefined || val === "") return;
    await api.patch(`/outcomes/${g.id}`, { current_value: parseFloat(val) });
    toast.success("Progress updated");
    setEdits((e) => { const n = { ...e }; delete n[g.id]; return n; });
    load();
  };

  if (!d) return <Skeleton className="h-72 rounded-xl" />;

  const cmtById = Object.fromEntries(d.commitments.map((c) => [c.id, c]));
  const chart = d.health_history.map((h) => ({ at: new Date(h.at).toLocaleDateString(undefined, { month: "short", day: "numeric" }), score: h.score }));

  return (
    <div className="space-y-6" data-testid="outcome-graph">
      <Section title="Client outcome graph"
        actions={<Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild><Button size="sm" variant="outline" data-testid="add-outcome-button"><Plus className="size-3.5" />Add outcome</Button></DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>New outcome</DialogTitle><DialogDescription>Define a measurable client outcome and its target.</DialogDescription></DialogHeader>
            <div className="space-y-4">
              <div><Label htmlFor="outcome-title">Title</Label><Input id="outcome-title" data-testid="outcome-title-input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="mt-1" /></div>
              <div><Label htmlFor="outcome-target">Target description</Label><Input id="outcome-target" placeholder="e.g. Production go-live" value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })} className="mt-1" /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label htmlFor="outcome-target-value">Target value</Label><Input id="outcome-target-value" type="number" data-testid="outcome-target-input" placeholder="100" value={form.target_value} onChange={(e) => setForm({ ...form, target_value: e.target.value })} className="mt-1" /></div>
                <div><Label htmlFor="outcome-unit">Unit</Label><Input id="outcome-unit" placeholder="% complete" value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} className="mt-1" /></div>
              </div>
            </div>
            <DialogFooter><Button onClick={create} data-testid="save-outcome-button">Create</Button></DialogFooter>
          </DialogContent>
        </Dialog>}>
        <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto_minmax(0,13rem)] lg:gap-3">
          {/* Goals */}
          <div className="min-w-0">
            <NodeHeading icon={Target} count={d.goals.length}>Goals</NodeHeading>
            <div className="overflow-hidden rounded-xl border border-border bg-card">
              {d.goals.length === 0 && <div className="px-4 py-6 text-center text-[13px] text-muted-foreground">No goals yet.</div>}
              {d.goals.map((g) => {
                const pct = g.target_value ? Math.min(100, Math.round((g.current_value / g.target_value) * 100)) : null;
                return (
                  <div key={g.id} className="border-b border-border/70 px-4 py-3 last:border-0" data-testid={`goal-${g.id}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-[13px] font-medium text-foreground">{g.title}</div>
                        {g.target && <div className="mt-0.5 text-xs text-muted-foreground">{g.target}</div>}
                      </div>
                      <StatusDot tone={GOAL_TONE[g.status] || "success"} className="shrink-0">{sentence(g.status)}</StatusDot>
                    </div>
                    {pct !== null && (
                      <div className="mt-2.5">
                        <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
                          <span className="tabular">{g.current_value} / {g.target_value} {g.unit || ""}</span>
                          <span className="tabular font-medium text-foreground">{pct}%</span>
                        </div>
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                          <div className={`h-full rounded-full ${pct >= 100 ? "bg-emerald-500" : pct >= 50 ? "bg-brand" : "bg-amber-500"}`} style={{ width: `${pct}%` }} data-testid={`goal-progress-${g.id}`} />
                        </div>
                        <div className="mt-2 flex items-center gap-1.5">
                          <Input type="number" className="h-7 w-24 px-2 text-xs md:text-xs" placeholder="Update" aria-label={`Current value for ${g.title}`} value={edits[g.id] ?? ""} onChange={(e) => setEdits({ ...edits, [g.id]: e.target.value })}
                            onKeyDown={(e) => e.key === "Enter" && saveProgress(g)} data-testid={`goal-update-input-${g.id}`} />
                          <Button size="sm" variant="outline" className="size-7 p-0 [&_svg]:size-3.5" onClick={() => saveProgress(g)} aria-label={`Save progress for ${g.title}`} data-testid={`goal-save-${g.id}`}><Check /></Button>
                        </div>
                      </div>
                    )}
                    {(g.linked_commitment_ids || []).length > 0 && (
                      <div className="mt-2 space-y-0.5">
                        {g.linked_commitment_ids.map((cid) => cmtById[cid] && (
                          <div key={cid} className="flex items-center gap-1 text-[11px] text-muted-foreground"><CornerDownRight className="size-3 shrink-0" aria-hidden="true" /><span className="truncate">{cmtById[cid].title}</span></div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <Connector />

          {/* Commitments */}
          <div className="min-w-0">
            <NodeHeading icon={Handshake} count={d.commitments.length}>Commitments</NodeHeading>
            <div className="overflow-hidden rounded-xl border border-border bg-card">
              {d.commitments.length === 0 && <div className="px-4 py-6 text-center text-[13px] text-muted-foreground">No commitments.</div>}
              {d.commitments.map((c) => (
                <div key={c.id} className="flex items-center justify-between gap-3 border-b border-border/70 px-4 py-2.5 last:border-0" data-testid={`graph-commitment-${c.id}`}>
                  <span className="min-w-0 text-[13px] text-foreground">{c.title}</span>
                  <StatusDot tone={CMT_TONE[c.status] || "info"} className="shrink-0">{sentence(c.status)}</StatusDot>
                </div>
              ))}
            </div>
          </div>

          <Connector />

          {/* Health node */}
          <div className="min-w-0">
            <NodeHeading icon={Activity}>Health</NodeHeading>
            <div className="rounded-xl border border-border bg-card px-4 py-4 text-center">
              <div className="tabular text-[28px] font-semibold leading-8 tracking-tight text-foreground">{d.health.score}</div>
              <div className="mt-1.5 flex justify-center"><StatusDot tone={BAND_TONE[d.health.band] || "danger"}>{sentence(d.health.band)}</StatusDot></div>
            </div>
          </div>
        </div>
      </Section>

      <Section title="Health over time" description="Snapshots captured on every outcome-affecting change." card bodyClassName="px-2 pb-3 pt-4 sm:px-4">
        {chart.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground"><LineChartIcon className="size-[18px]" aria-hidden="true" /></span>
            <p className="mt-3 text-sm font-medium text-foreground">No snapshots yet</p>
          </div>
        ) : (
          <div role="img" aria-label={`Client health over time, latest score ${chart[chart.length - 1].score}`}>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chart} margin={{ left: -24, right: 12, top: 8, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke={INK.grid} strokeDasharray="0" />
                <XAxis dataKey="at" tick={{ fontSize: 11, fill: INK.axis }} axisLine={false} tickLine={false} tickMargin={8} minTickGap={16} />
                <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={{ fontSize: 11, fill: INK.axis }} axisLine={false} tickLine={false} />
                <Tooltip content={<HealthTooltip />} cursor={{ stroke: INK.grid, strokeWidth: 1 }} />
                <ReferenceLine y={75} stroke={INK.healthy} strokeOpacity={0.7} strokeDasharray="4 4" label={{ value: "Healthy", position: "insideTopRight", fill: INK.axis, fontSize: 10 }} />
                <ReferenceLine y={50} stroke={INK.warning} strokeOpacity={0.7} strokeDasharray="4 4" label={{ value: "At risk", position: "insideTopRight", fill: INK.axis, fontSize: 10 }} />
                <Line type="monotone" dataKey="score" stroke={INK.line} strokeWidth={2} dot={{ r: 3, fill: INK.line, stroke: INK.surface, strokeWidth: 2 }} activeDot={{ r: 5, fill: INK.line, stroke: INK.surface, strokeWidth: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Section>
    </div>
  );
}
