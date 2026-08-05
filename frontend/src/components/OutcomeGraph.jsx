import { useEffect, useState } from "react";
import { api, HEALTH_BAND } from "@/lib/api";
import { toast } from "sonner";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, ReferenceLine } from "recharts";
import { Target, HandshakeIcon, Activity, Plus, ArrowRight } from "lucide-react";

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

  const load = async () => {
    const { data } = await api.get(`/workspaces/${workspaceId}/outcome-graph`);
    setD(data);
  };
  useEffect(() => { load(); }, [workspaceId]);

  const addGoal = async () => {
    const title = window.prompt("Goal / outcome title");
    if (!title) return;
    await api.post("/outcomes", { workspace_id: workspaceId, title, status: "on_track", linked_commitment_ids: [] });
    toast.success("Outcome added"); load();
  };

  if (!d) return <Skeleton className="h-72 rounded-xl" />;

  const cmtById = Object.fromEntries(d.commitments.map((c) => [c.id, c]));
  const chart = d.health_history.map((h) => ({ at: new Date(h.at).toLocaleDateString(undefined, { month: "short", day: "numeric" }), score: h.score }));

  return (
    <div className="space-y-6" data-testid="outcome-graph">
      {/* Graph: goals -> commitments -> health */}
      <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <h3 className="font-display font-bold text-lg">Client Outcome Graph</h3>
          <Button size="sm" variant="outline" onClick={addGoal} data-testid="add-outcome-button"><Plus className="w-3.5 h-3.5 mr-1" />Add outcome</Button>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto_1fr_auto_auto] gap-4 items-start">
          {/* Goals */}
          <div>
            <div className="text-xs uppercase tracking-[0.06em] text-gray-500 font-semibold mb-2 flex items-center gap-1"><Target className="w-3.5 h-3.5" />Goals</div>
            <div className="space-y-2">
              {d.goals.length === 0 && <div className="text-xs text-gray-400">No goals yet.</div>}
              {d.goals.map((g) => (
                <div key={g.id} className="border border-gray-200 rounded-lg p-3" data-testid={`goal-${g.id}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium">{g.title}</span>
                    <Badge className={`capitalize ${GOAL_STATUS[g.status] || GOAL_STATUS.on_track}`}>{g.status.replace("_", " ")}</Badge>
                  </div>
                  {g.target && <div className="text-xs text-gray-400 mt-1">{g.target}</div>}
                  {(g.linked_commitment_ids || []).length > 0 && (
                    <div className="mt-2 space-y-1">
                      {g.linked_commitment_ids.map((cid) => cmtById[cid] && (
                        <div key={cid} className="text-[11px] text-gray-500 flex items-center gap-1"><ArrowRight className="w-3 h-3 text-gray-300" />{cmtById[cid].title}</div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="hidden lg:flex items-center justify-center pt-8 text-gray-300"><ArrowRight className="w-5 h-5" /></div>

          {/* Commitments */}
          <div>
            <div className="text-xs uppercase tracking-[0.06em] text-gray-500 font-semibold mb-2 flex items-center gap-1"><HandshakeIcon className="w-3.5 h-3.5" />Commitments</div>
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

      {/* Health trend */}
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
