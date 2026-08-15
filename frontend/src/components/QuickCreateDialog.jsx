import { useEffect, useState } from "react";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { CirclePlus, Building2, UserRound, GitBranch, BriefcaseBusiness } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const TYPES = [
  { value: "company", label: "Company", icon: Building2, hint: "Create a company record for a prospect or client." },
  { value: "contact", label: "Contact", icon: UserRound, hint: "Add a relationship to an existing company." },
  { value: "opportunity", label: "Opportunity", icon: GitBranch, hint: "Put a qualified revenue opportunity into the pipeline." },
  { value: "workspace", label: "Client workspace", icon: BriefcaseBusiness, hint: "Set up a Client 360 operating workspace." },
];

const INITIAL = {
  company: { name: "", industry: "", tier: "standard" },
  contact: { name: "", email: "", company_id: "" },
  opportunity: { name: "", value: "", company_id: "", stage: "lead" },
  workspace: { name: "", company_id: "", stage: "onboarding" },
};

export default function QuickCreateDialog({ open, onOpenChange, onCreated }) {
  const [type, setType] = useState("company");
  const [form, setForm] = useState(INITIAL.company);
  const [companies, setCompanies] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get("/companies").then((response) => setCompanies(response.data)).catch(() => setCompanies([]));
  }, [open]);

  const changeType = (value) => { setType(value); setForm(INITIAL[value]); };
  const setField = (field, value) => setForm((previous) => ({ ...previous, [field]: value }));
  const selected = TYPES.find((item) => item.value === type);

  const submit = async () => {
    if (!form.name?.trim()) { toast.error("A name is required before creating this record."); return; }
    setSaving(true);
    try {
      const endpoint = type === "company" ? "/companies" : type === "contact" ? "/contacts" : type === "opportunity" ? "/opportunities" : "/workspaces";
      const payload = type === "opportunity" ? { ...form, name: form.name.trim(), value: Number(form.value) || 0, company_id: form.company_id || null } : { ...form, name: form.name.trim(), company_id: form.company_id || null };
      const { data } = await api.post(endpoint, payload);
      toast.success(`${selected.label} created`, { description: `${data.name || form.name} is now available in ClientVerse.` });
      setForm(INITIAL[type]);
      onOpenChange(false);
      onCreated?.(type, data);
    } catch (error) {
      toast.error(`Could not create ${selected.label.toLowerCase()}`, { description: formatErr(error.response?.data?.detail) });
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-50 text-[#1a9fbf]"><CirclePlus className="h-5 w-5" /></div>
          <DialogTitle className="font-display text-2xl">Create a record</DialogTitle>
          <DialogDescription>Capture the essential information now; enrich the record as work progresses.</DialogDescription>
        </DialogHeader>
        <div className="space-y-5 py-2">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {TYPES.map((item) => {
              const Icon = item.icon;
              const active = type === item.value;
              return <button key={item.value} type="button" onClick={() => changeType(item.value)} className={`rounded-xl border p-3 text-left transition-colors ${active ? "border-[#1a9fbf] bg-cyan-50 text-[#0a6177]" : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50"}`}>
                <Icon className="mb-2 h-4 w-4" />
                <span className="block text-xs font-semibold leading-4">{item.label}</span>
              </button>;
            })}
          </div>
          <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-500">{selected.hint}</p>
          <div className="grid gap-4">
            <div className="grid gap-1.5"><Label htmlFor="quick-create-name">Name <span className="text-red-500">*</span></Label><Input id="quick-create-name" value={form.name} onChange={(event) => setField("name", event.target.value)} placeholder={type === "company" ? "e.g. Acme Partners" : type === "contact" ? "e.g. Jordan Lee" : type === "opportunity" ? "e.g. Renewal — Acme Partners" : "e.g. Acme Partners — Client 360"} autoFocus /></div>
            {type === "company" && <><div className="grid gap-1.5"><Label htmlFor="quick-create-industry">Industry</Label><Input id="quick-create-industry" value={form.industry} onChange={(event) => setField("industry", event.target.value)} placeholder="e.g. Professional services" /></div><div className="grid gap-1.5"><Label>Client tier</Label><Select value={form.tier} onValueChange={(value) => setField("tier", value)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="standard">Standard</SelectItem><SelectItem value="growth">Growth</SelectItem><SelectItem value="enterprise">Enterprise</SelectItem></SelectContent></Select></div></>}
            {type === "contact" && <><div className="grid gap-1.5"><Label htmlFor="quick-create-email">Email</Label><Input id="quick-create-email" type="email" value={form.email} onChange={(event) => setField("email", event.target.value)} placeholder="name@company.com" /></div><CompanySelect companies={companies} value={form.company_id} onValueChange={(value) => setField("company_id", value)} /></>}
            {type === "opportunity" && <><div className="grid gap-1.5"><Label htmlFor="quick-create-value">Estimated value</Label><Input id="quick-create-value" type="number" min="0" value={form.value} onChange={(event) => setField("value", event.target.value)} placeholder="0" /></div><CompanySelect companies={companies} value={form.company_id} onValueChange={(value) => setField("company_id", value)} /></>}
            {type === "workspace" && <CompanySelect companies={companies} value={form.company_id} onValueChange={(value) => setField("company_id", value)} />}
          </div>
        </div>
        <DialogFooter><Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button type="button" disabled={saving} onClick={submit} className="cv-action-primary">{saving ? "Creating…" : `Create ${selected.label}`}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CompanySelect({ companies, value, onValueChange }) {
  return <div className="grid gap-1.5"><Label>Company</Label><Select value={value} onValueChange={onValueChange}><SelectTrigger><SelectValue placeholder="Select a company (optional)" /></SelectTrigger><SelectContent>{companies.map((company) => <SelectItem key={company.id} value={company.id}>{company.name}</SelectItem>)}</SelectContent></Select></div>;
}
