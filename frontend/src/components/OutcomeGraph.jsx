import { useEffect, useState } from "react";
import { api, HEALTH_BAND } from "@/lib/api";
import { toast } from "sonner";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, ReferenceLine } from "recharts";
import { Target, Handshake, Activity, Plus, ArrowRight, Check } from "lucide-react";

const GOAL_STATUS = {
  on_track: "bg-emerald-50 text-emerald-700 border-emerald-200",
  at_risk: "bg-amber-50 text-amber-700 border-amber-200",
  off_track: "bg-red-50 text-red-700 border-red-200",
};
const CMT_STATUS = {
  open: "bg-blue-50 text-blue-700 border-blue-200",
  at_risk: "bg-amber-50 text-amber-700 border-amber-200",
  breached: "bg-red-50 text-red-700 border-red-200",
  fulfilled: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

export default function OutcomeGraph({ workspaceId }) {
  const [d, setD] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", target: "", target_value: "", unit: "" });
  const [edits, setEdits] = useState({});

  const load = async () => {
    const { data } = await api.get(`/workspaces/${workspaceId}/outcome-graph`);
    setD(data);
  };
  useEffect(() => { load(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

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
      <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <h3 className="font-display font-bold text-lg">Client Outcome Graph</h3>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button size="sm" variant="outline" data-testid="add-outcome-button"><Plus className="w-3.5 h-3.5 mr-1" />Add outcome</Button></DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>New Outcome</DialogTitle><DialogDescription>Define a measurable client outcome and its target.</DialogDescription></DialogHeader>
              <div className="space-y-4">
                <div><Label>Title</Label><Input data-testid="outcome-title-input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="mt-1" /></div>
                <div><Label>Target description</Label><Input placeholder="e.g. Production go-live" value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })} className="mt-1" /></div>
                <div className="grid grid-cols-2 gap-3">
                  <div><Label>Target value</Label><Input type="number" data-testid="outcome-target-input" placeholder="100" value={form.target_value} onChange={(e) => setForm({ ...form, target_value: e.target.value })} className="mt-1" /></div>
                  <div><Label>Unit</Label><Input placeholder="% complete" value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} className="mt-1" /></div>
                </div>
              </div>
              <DialogFooter><Button onClick={create} data-testid="save-outcome-button" className="bg-[#0A0A0A] hover:bg-[#262626]">Create</Button></DialogFooter>
            </DialogContent>
          </Dialog>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto_1fr_auto_auto] gap-4 items-start">
          {/* Goals */}
          <div>
            <div className="text-xs uppercase tracking-[0.06em] text-gray-500 font-semibold mb-2 flex items-center gap-1"><Target className="w-3.5 h-3.5" />Goals</div>
            <div className="space-y-2">
              {d.goals.length === 0 && <div className="text-xs text-gray-400">No goals yet.</div>}
              {d.goals.map((g) => {
                const pct = g.target_value ? Math.min(100, Math.round((g.current_value / g.target_value) * 100)) : null;
                return (
                  <div key={g.id} className="border border-gray-200 rounded-lg p-3" data-testid={`goal-${g.id}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium">{g.title}</span>
                      <Badge className={`capitalize ${GOAL_STATUS[g.status] || GOAL_STATUS.on_track}`}>{g.status.replace("_", " ")}</Badge>
                    </div>
                    {g.target && <div className="text-xs text-gray-400 mt-0.5">{g.target}</div>}
                    {pct !== null && (
                      <div className="mt-2">
                        <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
                          <span>{g.current_value} / {g.target_value} {g.unit || ""}</span>
                          <span className="font-medium">{pct}%</span>
                        </div>
                        <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                          <div className={`h-full ${pct >= 100 ? "bg-emerald-500" : pct >= 50 ? "bg-blue-500" : "bg-amber-500"}`} style={{ width: `${pct}%` }} data-testid={`goal-progress-${g.id}`} />
                        </div>
                        <div className="flex items-center gap-1.5 mt-2">
                          <Input type="number" className="h-7 text-xs w-24" placeholder="Update" value={edits[g.id] ?? ""} onChange={(e) => setEdits({ ...edits, [g.id]: e.target.value })}
                            onKeyDown={(e) => e.key === "Enter" && saveProgress(g)} data-testid={`goal-update-input-${g.id}`} />
                          <Button size="sm" variant="outline" className="h-7 px-2" onClick={() => saveProgress(g)} data-testid={`goal-save-${g.id}`}><Check className="w-3 h-3" /></Button>
                        </div>
                      </div>
                    )}
                    {(g.linked_commitment_ids || []).length > 0 && (
                      <div className="mt-2 space-y-1">
                        {g.linked_commitment_ids.map((cid) => cmtById[cid] && (
                          <div key={cid} className="text-[11px] text-gray-500 flex items-center gap-1"><ArrowRight className="w-3 h-3 text-gray-300" />{cmtById[cid].title}</div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="hidden lg:flex items-center justify-center pt-8 text-gray-300"><ArrowRight className="w-5 h-5" /></div>

          {/* Commitments */}
          <div>
            <div className="text-xs uppercase tracking-[0.06em] text-gray-500 font-semibold mb-2 flex items-center gap-1"><Handshake className="w-3.5 h-3.5" />Commitments</div>
            <div className="space-y-2">
              {d.commitments.length === 0 && <div className="text-xs text-gray-400">No commitments.</div>}
              {d.commitments.map((c) => (
                <div key={c.id} className="border border-gray-200 rounded-lg p-3 flex items-center justify-between gap-2" data-testid={`graph-commitment-${c.id}`}>
                  <span className="text-sm">{c.title}</span>
                  <Badge className={`capitalize ${CMT_STATUS[c.status] || CMT_STATUS.open}`}>{c.status.replace("_", " ")}</Badge>
                </div>
              ))}
            </div>
          </div>

          <div className="hidden lg:flex items-center justify-center pt-8 text-gray-300"><ArrowRight className="w-5 h-5" /></div>

          {/* Health node */}
          <div>
            <div className="text-xs uppercase tracking-[0.06em] text-gray-500 font-semibold mb-2 flex items-center gap-1"><Activity className="w-3.5 h-3.5" />Health</div>
            <div className={`border rounded-lg p-4 text-center ${HEALTH_BAND[d.health.band]}`}>
              <div className="font-display text-4xl font-bold">{d.health.score}</div>
              <div className="text-xs capitalize mt-1">{d.health.band.replace("_", " ")}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
        <h3 className="font-display font-bold text-lg mb-1">Health Over Time</h3>
        <p className="text-xs text-gray-400 mb-4">Snapshots captured on every outcome-affecting change.</p>
        {chart.length === 0 ? <div className="text-sm text-gray-400 py-8 text-center">No snapshots yet.</div> : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={chart} margin={{ left: -20, right: 10, top: 10 }}>
              <XAxis dataKey="at" tick={{ fontSize: 11, fill: "#525252" }} axisLine={false} tickLine={false} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: "#525252" }} axisLine={false} tickLine={false} />
              <Tooltip />
              <ReferenceLine y={75} stroke="#10b981" strokeDasharray="3 3" />
              <ReferenceLine y={50} stroke="#f59e0b" strokeDasharray="3 3" />
              <Line type="monotone" dataKey="score" stroke="#0A0A0A" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
