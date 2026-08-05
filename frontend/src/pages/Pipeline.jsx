import { useEffect, useState } from "react";
import { api, money } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus } from "lucide-react";

const STAGES = [
  { key: "lead", label: "Lead" },
  { key: "qualified", label: "Qualified" },
  { key: "proposal", label: "Proposal" },
  { key: "negotiation", label: "Negotiation" },
  { key: "closed_won", label: "Closed Won" },
];

export default function Pipeline() {
  const [opps, setOpps] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", value: "", company_id: "", stage: "lead" });

  const load = async () => {
    const [o, c] = await Promise.all([api.get("/opportunities"), api.get("/companies")]);
    setOpps(o.data); setCompanies(c.data);
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.name) return;
    await api.post("/opportunities", { ...form, value: parseFloat(form.value) || 0, company_id: form.company_id || null });
    toast.success("Opportunity created");
    setOpen(false); setForm({ name: "", value: "", company_id: "", stage: "lead" });
    load();
  };

  const move = async (opp, stage) => {
    await api.patch(`/opportunities/${opp.id}/stage`, { stage });
    if (stage === "closed_won") toast.success("Won! Client workspace created automatically.");
    else toast.success("Stage updated");
    load();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-display text-3xl font-bold">Pipeline</h1>
          <p className="text-sm text-gray-500 mt-1">WIN stage — drag opportunities toward closed won.</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button data-testid="new-opportunity-button" className="bg-[#0A0A0A] hover:bg-[#262626]"><Plus className="w-4 h-4 mr-1" /> New Opportunity</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>New Opportunity</DialogTitle></DialogHeader>
            <div className="space-y-4">
              <div><Label>Name</Label><Input data-testid="opp-name-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="mt-1" /></div>
              <div><Label>Value ($)</Label><Input type="number" data-testid="opp-value-input" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} className="mt-1" /></div>
              <div>
                <Label>Company</Label>
                <Select value={form.company_id} onValueChange={(v) => setForm({ ...form, company_id: v })}>
                  <SelectTrigger className="mt-1" data-testid="opp-company-select"><SelectValue placeholder="Select company" /></SelectTrigger>
                  <SelectContent>{companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter><Button onClick={create} data-testid="save-opp-button" className="bg-[#0A0A0A] hover:bg-[#262626]">Create</Button></DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        {STAGES.map((s) => {
          const items = opps.filter((o) => o.stage === s.key);
          const total = items.reduce((a, b) => a + (b.value || 0), 0);
          return (
            <div key={s.key} className="bg-white border border-gray-200 rounded-xl p-3" data-testid={`stage-column-${s.key}`}>
              <div className="flex items-center justify-between mb-3 px-1">
                <span className="text-xs uppercase tracking-[0.06em] font-semibold text-gray-500">{s.label}</span>
                <span className="text-xs text-gray-400">{items.length}</span>
              </div>
              <div className="text-xs text-gray-400 px-1 mb-2">{money(total)}</div>
              <div className="space-y-2 min-h-[100px]">
                {items.map((o) => (
                  <div key={o.id} className="border border-gray-200 rounded-lg p-3 hover:shadow-sm transition-shadow bg-white" data-testid={`opp-card-${o.id}`}>
                    <div className="font-medium text-sm">{o.name}</div>
                    <div className="text-xs text-gray-400 mt-0.5">{money(o.value)}</div>
                    <Select value={o.stage} onValueChange={(v) => move(o, v)}>
                      <SelectTrigger className="mt-2 h-7 text-xs" data-testid={`opp-stage-select-${o.id}`}><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {STAGES.map((st) => <SelectItem key={st.key} value={st.key}>{st.label}</SelectItem>)}
                        <SelectItem value="closed_lost">Closed Lost</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
