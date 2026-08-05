import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Building2, User } from "lucide-react";

export default function Directory() {
  const [companies, setCompanies] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [coOpen, setCoOpen] = useState(false);
  const [ctOpen, setCtOpen] = useState(false);
  const [co, setCo] = useState({ name: "", industry: "", website: "", tier: "standard" });
  const [ct, setCt] = useState({ name: "", email: "", role: "", company_id: "", influence: "medium", sentiment: "neutral" });

  const load = async () => {
    const [c, p] = await Promise.all([api.get("/companies"), api.get("/contacts")]);
    setCompanies(c.data); setContacts(p.data);
  };
  useEffect(() => { load(); }, []);

  const createCo = async () => {
    if (!co.name) return;
    await api.post("/companies", co); toast.success("Company added");
    setCoOpen(false); setCo({ name: "", industry: "", website: "", tier: "standard" }); load();
  };
  const createCt = async () => {
    if (!ct.name) return;
    await api.post("/contacts", { ...ct, company_id: ct.company_id || null }); toast.success("Contact added");
    setCtOpen(false); setCt({ name: "", email: "", role: "", company_id: "", influence: "medium", sentiment: "neutral" }); load();
  };
  const coName = (id) => companies.find((c) => c.id === id)?.name || "—";

  const SENT = { positive: "bg-emerald-50 text-emerald-700 border-emerald-200", neutral: "bg-gray-100 text-gray-600 border-gray-200", negative: "bg-red-50 text-red-700 border-red-200" };

  return (
    <div>
      <div className="mb-8">
        <h1 className="font-display text-3xl font-bold">Directory</h1>
        <p className="text-sm text-gray-500 mt-1">Companies and stakeholder relationship intelligence.</p>
      </div>

      <Tabs defaultValue="companies">
        <TabsList>
          <TabsTrigger value="companies" data-testid="tab-companies"><Building2 className="w-4 h-4 mr-1" />Companies</TabsTrigger>
          <TabsTrigger value="contacts" data-testid="tab-contacts"><User className="w-4 h-4 mr-1" />Contacts</TabsTrigger>
        </TabsList>

        <TabsContent value="companies" className="mt-6">
          <div className="flex justify-end mb-4">
            <Dialog open={coOpen} onOpenChange={setCoOpen}>
              <DialogTrigger asChild><Button data-testid="new-company-button" className="bg-[#0A0A0A] hover:bg-[#262626]"><Plus className="w-4 h-4 mr-1" />New Company</Button></DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>New Company</DialogTitle></DialogHeader>
                <div className="space-y-4">
                  <div><Label>Name</Label><Input data-testid="company-name-input" value={co.name} onChange={(e) => setCo({ ...co, name: e.target.value })} className="mt-1" /></div>
                  <div><Label>Industry</Label><Input value={co.industry} onChange={(e) => setCo({ ...co, industry: e.target.value })} className="mt-1" /></div>
                  <div><Label>Tier</Label>
                    <Select value={co.tier} onValueChange={(v) => setCo({ ...co, tier: v })}>
                      <SelectTrigger className="mt-1" data-testid="company-tier-select"><SelectValue /></SelectTrigger>
                      <SelectContent>{["standard", "growth", "enterprise"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                </div>
                <DialogFooter><Button onClick={createCo} data-testid="save-company-button" className="bg-[#0A0A0A] hover:bg-[#262626]">Create</Button></DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm text-left">
              <thead><tr className="border-b border-gray-200 text-xs uppercase tracking-[0.05em] text-gray-500">
                <th className="px-6 py-3 font-semibold">Company</th><th className="px-6 py-3 font-semibold">Industry</th><th className="px-6 py-3 font-semibold">Tier</th></tr></thead>
              <tbody>
                {companies.map((c) => (
                  <tr key={c.id} className="border-b border-gray-100 hover:bg-gray-50" data-testid={`company-row-${c.id}`}>
                    <td className="px-6 py-3 font-medium">{c.name}</td>
                    <td className="px-6 py-3 text-gray-500">{c.industry || "—"}</td>
                    <td className="px-6 py-3"><Badge className="bg-gray-100 text-gray-600 border-gray-200 capitalize">{c.tier}</Badge></td>
                  </tr>
                ))}
                {companies.length === 0 && <tr><td colSpan={3} className="px-6 py-8 text-center text-gray-400">No companies yet.</td></tr>}
              </tbody>
            </table>
          </div>
        </TabsContent>

        <TabsContent value="contacts" className="mt-6">
          <div className="flex justify-end mb-4">
            <Dialog open={ctOpen} onOpenChange={setCtOpen}>
              <DialogTrigger asChild><Button data-testid="new-contact-button" className="bg-[#0A0A0A] hover:bg-[#262626]"><Plus className="w-4 h-4 mr-1" />New Contact</Button></DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>New Contact</DialogTitle></DialogHeader>
                <div className="space-y-4">
                  <div><Label>Name</Label><Input data-testid="contact-name-input" value={ct.name} onChange={(e) => setCt({ ...ct, name: e.target.value })} className="mt-1" /></div>
                  <div><Label>Email</Label><Input value={ct.email} onChange={(e) => setCt({ ...ct, email: e.target.value })} className="mt-1" /></div>
                  <div><Label>Role</Label><Input value={ct.role} onChange={(e) => setCt({ ...ct, role: e.target.value })} className="mt-1" /></div>
                  <div><Label>Company</Label>
                    <Select value={ct.company_id} onValueChange={(v) => setCt({ ...ct, company_id: v })}>
                      <SelectTrigger className="mt-1" data-testid="contact-company-select"><SelectValue placeholder="Select" /></SelectTrigger>
                      <SelectContent>{companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div><Label>Influence</Label>
                    <Select value={ct.influence} onValueChange={(v) => setCt({ ...ct, influence: v })}>
                      <SelectTrigger className="mt-1" data-testid="contact-influence-select"><SelectValue /></SelectTrigger>
                      <SelectContent>{["low", "medium", "high"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                </div>
                <DialogFooter><Button onClick={createCt} data-testid="save-contact-button" className="bg-[#0A0A0A] hover:bg-[#262626]">Create</Button></DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm text-left">
              <thead><tr className="border-b border-gray-200 text-xs uppercase tracking-[0.05em] text-gray-500">
                <th className="px-6 py-3 font-semibold">Name</th><th className="px-6 py-3 font-semibold">Company</th><th className="px-6 py-3 font-semibold">Role</th><th className="px-6 py-3 font-semibold">Influence</th><th className="px-6 py-3 font-semibold">Sentiment</th></tr></thead>
              <tbody>
                {contacts.map((c) => (
                  <tr key={c.id} className="border-b border-gray-100 hover:bg-gray-50" data-testid={`contact-row-${c.id}`}>
                    <td className="px-6 py-3 font-medium">{c.name}</td>
                    <td className="px-6 py-3 text-gray-500">{coName(c.company_id)}</td>
                    <td className="px-6 py-3 text-gray-500">{c.role || "—"}</td>
                    <td className="px-6 py-3"><Badge className="bg-gray-100 text-gray-600 border-gray-200 capitalize">{c.influence}</Badge></td>
                    <td className="px-6 py-3"><Badge className={`capitalize ${SENT[c.sentiment] || SENT.neutral}`}>{c.sentiment}</Badge></td>
                  </tr>
                ))}
                {contacts.length === 0 && <tr><td colSpan={5} className="px-6 py-8 text-center text-gray-400">No contacts yet.</td></tr>}
              </tbody>
            </table>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
