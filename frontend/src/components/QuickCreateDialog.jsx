import { useEffect, useState } from "react";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { Building2, UserRound, GitBranch, BriefcaseBusiness } from "lucide-react";
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

const FIELD_LABEL = "text-[13px] font-medium";

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

  const companySelect = <CompanySelect companies={companies} value={form.company_id} onValueChange={(value) => setField("company_id", value)} />;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="gap-0 overflow-hidden p-0 sm:max-w-[520px]">
        <DialogHeader className="space-y-1 px-5 pb-4 pr-12 pt-5 text-left">
          <DialogTitle className="text-base font-semibold">Create a record</DialogTitle>
          <DialogDescription className="text-[13px]">{selected.hint}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 px-5 pb-5">
          <div className="grid grid-cols-2 gap-0.5 rounded-lg bg-muted p-0.5 sm:grid-cols-4" role="group" aria-label="Record type">
            {TYPES.map((item) => {
              const Icon = item.icon;
              const active = type === item.value;
              return <button key={item.value} type="button" aria-pressed={active} onClick={() => changeType(item.value)}
                className={`flex h-8 min-w-0 items-center justify-center gap-1.5 rounded-md px-2 text-[13px] font-medium transition-colors ${active ? "bg-card text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"}`}>
                <Icon className={`size-3.5 shrink-0 ${active ? "text-brand" : ""}`} aria-hidden="true" />
                <span className="truncate">{item.value === "workspace" ? <><span className="sm:hidden">Client workspace</span><span className="hidden sm:inline">Workspace</span></> : item.label}</span>
              </button>;
            })}
          </div>
          <div className="grid gap-3.5">
            <div className="grid gap-1.5"><Label htmlFor="quick-create-name" className={FIELD_LABEL}>Name <span className="text-red-600">*</span></Label><Input id="quick-create-name" value={form.name} onChange={(event) => setField("name", event.target.value)} placeholder={type === "company" ? "e.g. Acme Partners" : type === "contact" ? "e.g. Jordan Lee" : type === "opportunity" ? "e.g. Renewal — Acme Partners" : "e.g. Acme Partners — Client 360"} /></div>
            {type === "company" && <div className="grid gap-3.5 sm:grid-cols-2">
              <div className="grid gap-1.5"><Label htmlFor="quick-create-industry" className={FIELD_LABEL}>Industry</Label><Input id="quick-create-industry" value={form.industry} onChange={(event) => setField("industry", event.target.value)} placeholder="e.g. Professional services" /></div>
              <div className="grid gap-1.5"><Label htmlFor="quick-create-tier" className={FIELD_LABEL}>Client tier</Label><Select value={form.tier} onValueChange={(value) => setField("tier", value)}><SelectTrigger id="quick-create-tier"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="standard">Standard</SelectItem><SelectItem value="growth">Growth</SelectItem><SelectItem value="enterprise">Enterprise</SelectItem></SelectContent></Select></div>
            </div>}
            {type === "contact" && <div className="grid gap-3.5 sm:grid-cols-2">
              <div className="grid gap-1.5"><Label htmlFor="quick-create-email" className={FIELD_LABEL}>Email</Label><Input id="quick-create-email" type="email" value={form.email} onChange={(event) => setField("email", event.target.value)} placeholder="name@company.com" /></div>
              {companySelect}
            </div>}
            {type === "opportunity" && <div className="grid gap-3.5 sm:grid-cols-2">
              <div className="grid gap-1.5"><Label htmlFor="quick-create-value" className={FIELD_LABEL}>Estimated value</Label><Input id="quick-create-value" type="number" min="0" value={form.value} onChange={(event) => setField("value", event.target.value)} placeholder="0" className="tabular" /></div>
              {companySelect}
            </div>}
            {type === "workspace" && companySelect}
          </div>
        </div>
        <DialogFooter className="gap-2 border-t border-border bg-muted/30 px-5 py-3 sm:space-x-0">
          <Button type="button" size="sm" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="button" size="sm" disabled={saving} onClick={submit} className="cv-action-primary">{saving ? "Creating…" : `Create ${selected.label}`}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CompanySelect({ companies, value, onValueChange }) {
  return <div className="grid gap-1.5"><Label htmlFor="quick-create-company" className={FIELD_LABEL}>Company</Label><Select value={value} onValueChange={onValueChange}><SelectTrigger id="quick-create-company"><SelectValue placeholder="Select a company (optional)" /></SelectTrigger><SelectContent>{companies.map((company) => <SelectItem key={company.id} value={company.id}>{company.name}</SelectItem>)}</SelectContent></Select></div>;
}
