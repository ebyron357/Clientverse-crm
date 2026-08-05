import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, HEALTH_BAND } from "@/lib/api";
import { toast } from "sonner";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, ArrowRight } from "lucide-react";

const LIFECYCLE = ["onboard", "serve", "retain", "expand"];

export default function Workspaces() {
  const [rows, setRows] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", company_id: "", stage: "onboard" });
  const navigate = useNavigate();

  const load = async () => {
    const [w, c, d] = await Promise.all([api.get("/workspaces"), api.get("/companies"), api.get("/dashboard")]);
    const healthMap = Object.fromEntries((d.data.portfolio || []).map((p) => [p.id, p.health]));
    setRows(w.data.map((x) => ({ ...x, health: healthMap[x.id] })));
    setCompanies(c.data);
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.name) return;
    await api.post("/workspaces", { ...form, company_id: form.company_id || null });
    toast.success("Workspace created"); setOpen(false); setForm({ name: "", company_id: "", stage: "onboard" }); load();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-display text-3xl font-bold">Client Workspaces</h1>
          <p className="text-sm text-gray-500 mt-1">ONBOARD → SERVE → RETAIN → EXPAND execution hubs.</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild><Button data-testid="new-workspace-button" className="bg-[#0A0A0A] hover:bg-[#262626]"><Plus className="w-4 h-4 mr-1" />New Workspace</Button></DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>New Client Workspace</DialogTitle></DialogHeader>
            <div className="space-y-4">
              <div><Label>Name</Label><Input data-testid="workspace-name-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="mt-1" /></div>
              <div><Label>Company</Label>
                <Select value={form.company_id} onValueChange={(v) => setForm({ ...form, company_id: v })}>
                  <SelectTrigger className="mt-1" data-testid="workspace-company-select"><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>{companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div><Label>Lifecycle stage</Label>
                <Select value={form.stage} onValueChange={(v) => setForm({ ...form, stage: v })}>
                  <SelectTrigger className="mt-1" data-testid="workspace-stage-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{LIFECYCLE.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter><Button onClick={create} data-testid="save-workspace-button" className="bg-[#0A0A0A] hover:bg-[#262626]">Create</Button></DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {rows.map((w) => (
          <button key={w.id} onClick={() => navigate(`/workspaces/${w.id}`)} data-testid={`workspace-card-${w.id}`}
            className="text-left bg-white border border-gray-200 rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow">
            <div className="flex items-start justify-between">
              <div>
                <div className="font-display font-bold text-lg">{w.name}</div>
                <Badge className="mt-1 bg-gray-100 text-gray-600 border-gray-200 capitalize">{w.stage}</Badge>
              </div>
              {w.health && <Badge className={HEALTH_BAND[w.health.band]}>{w.health.score}</Badge>}
            </div>
            <div className="flex items-center text-xs text-[#2563EB] font-medium mt-4">Open workspace <ArrowRight className="w-3 h-3 ml-1" /></div>
          </button>
        ))}
        {rows.length === 0 && <div className="text-sm text-gray-400 col-span-3 text-center py-12">No workspaces yet. Win an opportunity to auto-create one.</div>}
      </div>
    </div>
  );
}
