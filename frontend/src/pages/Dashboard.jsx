import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, money, HEALTH_BAND } from "@/lib/api";
import { Badge } from "@/components/AppShell";
import { Skeleton } from "@/components/ui/skeleton";
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell, Tooltip } from "recharts";
import { TrendingUp, Trophy, Briefcase, AlertTriangle } from "lucide-react";

const STAGE_LABELS = { lead: "Lead", qualified: "Qualified", proposal: "Proposal", negotiation: "Negotiation", closed_won: "Won", closed_lost: "Lost" };

function Stat({ icon: Icon, label, value, sub }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-[0.08em] text-gray-500 font-semibold">{label}</span>
        <Icon className="w-4 h-4 text-gray-400" />
      </div>
      <div className="font-display text-3xl font-bold mt-3">{value}</div>
      {sub && <div className="text-xs text-gray-400 mt-1">{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const navigate = useNavigate();

  useEffect(() => { api.get("/dashboard").then((r) => setData(r.data)); }, []);

  if (!data) return <div className="grid grid-cols-4 gap-6">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-32 rounded-xl" />)}</div>;

  const funnelData = Object.entries(data.funnel).filter(([k]) => k !== "closed_lost").map(([k, v]) => ({ name: STAGE_LABELS[k], count: v, key: k }));

  return (
    <div>
      <div className="mb-8">
        <h1 className="font-display text-3xl font-bold">Command Center</h1>
        <p className="text-sm text-gray-500 mt-1">Portfolio overview across the full client lifecycle.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
        <Stat icon={TrendingUp} label="Open Pipeline" value={money(data.pipeline_value)} sub={`${data.open_opportunities} active opportunities`} />
        <Stat icon={Trophy} label="Won Value" value={money(data.won_value)} sub="Closed won" />
        <Stat icon={Briefcase} label="Active Workspaces" value={data.active_workspaces} sub="In delivery" />
        <Stat icon={AlertTriangle} label="At-risk Commitments" value={data.at_risk_commitments} sub="Needs attention" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-5 bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
          <h3 className="font-display font-bold text-lg mb-1">Pipeline Funnel</h3>
          <p className="text-xs text-gray-400 mb-4">Opportunities by stage (WIN)</p>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={funnelData} layout="vertical" margin={{ left: 10 }}>
              <XAxis type="number" hide />
              <YAxis dataKey="name" type="category" width={80} tick={{ fontSize: 12, fill: "#525252" }} axisLine={false} tickLine={false} />
              <Tooltip cursor={{ fill: "#F5F5F5" }} />
              <Bar dataKey="count" radius={[0, 6, 6, 0]}>
                {funnelData.map((e, i) => <Cell key={i} fill={e.key === "closed_won" ? "#059669" : "#0A0A0A"} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="lg:col-span-7 bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
          <h3 className="font-display font-bold text-lg mb-1">Client Health Portfolio</h3>
          <p className="text-xs text-gray-400 mb-4">Explainable health across active workspaces</p>
          {data.portfolio.length === 0 ? (
            <div className="text-sm text-gray-400 py-8 text-center">No active workspaces yet.</div>
          ) : (
            <div className="space-y-2">
              {data.portfolio.map((p) => (
                <button key={p.id} onClick={() => navigate(`/workspaces/${p.id}`)} data-testid={`portfolio-row-${p.id}`}
                  className="w-full flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 transition-colors text-left">
                  <div>
                    <div className="font-medium text-sm">{p.name}</div>
                    <div className="text-xs text-gray-400 capitalize">{p.stage}</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="w-32 h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div className={`h-full ${p.health.band === "healthy" ? "bg-emerald-500" : p.health.band === "at_risk" ? "bg-amber-500" : "bg-red-500"}`} style={{ width: `${p.health.score}%` }} />
                    </div>
                    <Badge className={HEALTH_BAND[p.health.band]}>{p.health.score}</Badge>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
