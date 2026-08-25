import { useCallback, useEffect, useMemo, useState } from "react";
import { api, formatErr, money } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/AppShell";
import { CircleDollarSign, Filter, GitBranch, Plus, RefreshCw, Search, Sparkles, X } from "lucide-react";

const STAGES = [
  { key: "lead", label: "Lead", accent: "bg-slate-400" },
  { key: "qualified", label: "Qualified", accent: "bg-[#1a9fbf]" },
  { key: "proposal", label: "Proposal", accent: "bg-violet-500" },
  { key: "negotiation", label: "Negotiation", accent: "bg-amber-500" },
  { key: "closed_won", label: "Won", accent: "bg-emerald-500" },
];

export default function Pipeline() {
  const [opportunities, setOpportunities] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState("");
  const [companyFilter, setCompanyFilter] = useState("all");
  const [form, setForm] = useState({ name: "", value: "", company_id: "", stage: "lead" });

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const [opportunityResponse, companyResponse] = await Promise.all([api.get("/opportunities"), api.get("/companies")]); setOpportunities(opportunityResponse.data); setCompanies(companyResponse.data); }
    catch { setError("The pipeline could not be loaded. Your records are unchanged — try refreshing when the connection is available."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const companyName = useCallback((id) => companies.find((company) => company.id === id)?.name || "Unassigned company", [companies]);
  const filtered = useMemo(() => opportunities.filter((opportunity) => {
    const text = `${opportunity.name || ""} ${companyName(opportunity.company_id)}`.toLowerCase();
    return text.includes(query.toLowerCase()) && (companyFilter === "all" || opportunity.company_id === companyFilter);
  }), [opportunities, query, companyFilter, companyName]);
  const visibleValue = filtered.filter((opportunity) => opportunity.stage !== "closed_lost").reduce((total, opportunity) => total + (Number(opportunity.value) || 0), 0);

  const create = async () => {
    if (!form.name.trim()) { toast.error("Give this opportunity a name first."); return; }
    setSaving(true);
    try { await api.post("/opportunities", { ...form, name: form.name.trim(), value: Number(form.value) || 0, company_id: form.company_id || null }); toast.success("Opportunity created", { description: "It is now visible in the appropriate pipeline stage." }); setOpen(false); setForm({ name: "", value: "", company_id: "", stage: "lead" }); await load(); }
    catch (requestError) { toast.error("Could not create opportunity", { description: formatErr(requestError.response?.data?.detail) }); }
    finally { setSaving(false); }
  };

  const move = async (opportunity, stage) => {
    if (stage === opportunity.stage) return;
    const previous = opportunities;
    setOpportunities((current) => current.map((record) => record.id === opportunity.id ? { ...record, stage } : record));
    try { await api.patch(`/opportunities/${opportunity.id}/stage`, { stage }); toast.success(stage === "closed_won" ? "Opportunity won — Client 360 workspace created" : `Moved to ${STAGES.find((item) => item.key === stage)?.label || stage}`); }
    catch (requestError) { setOpportunities(previous); toast.error("Stage change did not save", { description: formatErr(requestError.response?.data?.detail) }); }
  };

  if (error) return <div className="cv-page"><div className="cv-empty"><GitBranch className="h-9 w-9 text-red-500" /><h1 className="mt-4 font-display text-xl font-bold">Pipeline unavailable</h1><p className="mt-2 max-w-md text-sm leading-6 text-slate-500">{error}</p><Button onClick={load} className="mt-5 cv-action-primary"><RefreshCw className="mr-2 h-4 w-4" />Retry</Button></div></div>;

  return <div className="cv-page">
    <div className="cv-page-header"><div><div className="cv-eyebrow">Revenue operations</div><h1 className="cv-page-title">Pipeline</h1><p className="cv-page-description">Give every opportunity a clear next move — then convert a win into an operating client workspace.</p></div><OpportunityDialog open={open} onOpenChange={setOpen} form={form} setForm={setForm} companies={companies} saving={saving} onSubmit={create} /></div>
    <section className="mb-5 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_auto_auto]"><div className="cv-card flex min-h-[98px] items-center gap-4 p-5"><span className="flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-50 text-[#1a9fbf]"><CircleDollarSign className="h-5 w-5" /></span><div><div className="text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">Visible pipeline value</div><div className="mt-1 font-display text-3xl font-extrabold text-[#0a1628]">{money(visibleValue)}</div><div className="mt-1 text-xs text-slate-500">{filtered.length} opportunity{filtered.length === 1 ? "" : "ies"} match your current view</div></div></div><div className="cv-card flex items-center gap-3 p-4 lg:w-[280px]"><Search className="h-4 w-4 text-slate-400" /><input value={query} onChange={(event) => setQuery(event.target.value)} className="w-full bg-transparent text-sm text-[#0a1628] outline-none placeholder:text-slate-400" placeholder="Search pipeline…" aria-label="Search opportunities" />{query && <button onClick={() => setQuery("")} className="text-slate-400 hover:text-slate-600" aria-label="Clear search"><X className="h-4 w-4" /></button>}</div><div className="cv-card flex items-center gap-2 p-2 lg:w-[230px]"><Filter className="ml-1 h-4 w-4 text-slate-400" /><Select value={companyFilter} onValueChange={setCompanyFilter}><SelectTrigger className="h-9 border-0 bg-transparent text-sm shadow-none focus:ring-0"><SelectValue placeholder="All companies" /></SelectTrigger><SelectContent><SelectItem value="all">All companies</SelectItem>{companies.map((company) => <SelectItem key={company.id} value={company.id}>{company.name}</SelectItem>)}</SelectContent></Select></div></section>
    <section aria-label="Revenue pipeline by stage" className="cv-scrollbar overflow-x-auto pb-2"><div className="grid min-w-[1100px] grid-cols-5 gap-4">{STAGES.map((stage) => <StageColumn key={stage.key} stage={stage} opportunities={filtered.filter((opportunity) => opportunity.stage === stage.key)} companyName={companyName} onMove={move} />)}</div></section>
    {!loading && !filtered.length && <div className="cv-empty mt-5"><Sparkles className="h-9 w-9 text-[#4ac4e0]" /><h2 className="mt-4 font-display text-xl font-bold text-[#0a1628]">No opportunities match this view</h2><p className="mt-2 max-w-md text-sm leading-6 text-slate-500">Adjust your search or filters, or create a qualified opportunity to begin tracking revenue movement.</p><Button onClick={() => { setQuery(""); setCompanyFilter("all"); setOpen(true); }} className="mt-5 cv-action-primary"><Plus className="mr-1.5 h-4 w-4" />Create opportunity</Button></div>}
    {loading && <div className="mt-5 grid min-w-[1100px] grid-cols-5 gap-4">{STAGES.map((stage) => <div key={stage.key} className="h-72 animate-pulse rounded-2xl border border-slate-200 bg-white" />)}</div>}
  </div>;
}

function StageColumn({ stage, opportunities, companyName, onMove }) {
  const total = opportunities.reduce((sum, opportunity) => sum + (Number(opportunity.value) || 0), 0);
  return <section className="rounded-2xl border border-slate-200/90 bg-slate-100/55 p-3"><header className="mb-3 rounded-xl bg-white px-3 py-3 shadow-[0_1px_2px_rgba(10,22,40,.03)]"><div className="flex items-center justify-between"><div className="flex items-center gap-2"><span className={`h-2.5 w-2.5 rounded-full ${stage.accent}`} /><h2 className="text-sm font-bold text-[#132038]">{stage.label}</h2></div><Badge className="border-slate-200 bg-slate-50 text-slate-600">{opportunities.length}</Badge></div><p className="mt-2 font-display text-lg font-bold text-[#0a1628]">{money(total)}</p></header><div className="space-y-3">{opportunities.map((opportunity) => <OpportunityCard key={opportunity.id} opportunity={opportunity} companyName={companyName} onMove={onMove} />)}{!opportunities.length && <div className="rounded-xl border border-dashed border-slate-300 bg-white/60 px-3 py-8 text-center text-xs text-slate-400">No opportunities in {stage.label.toLowerCase()}.</div>}</div></section>;
}

function OpportunityCard({ opportunity, companyName, onMove }) {
  return <article className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-[0_1px_2px_rgba(10,22,40,.03)] transition-shadow hover:shadow-[0_8px_18px_rgba(10,22,40,.08)]"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><h3 className="truncate text-sm font-bold text-[#132038]">{opportunity.name}</h3><p className="mt-1 truncate text-xs text-slate-500">{companyName(opportunity.company_id)}</p></div><span className="shrink-0 font-display text-sm font-bold text-[#0a1628]">{money(opportunity.value)}</span></div><div className="mt-3 border-t border-slate-100 pt-3"><Select value={opportunity.stage} onValueChange={(value) => onMove(opportunity, value)}><SelectTrigger className="h-8 w-full border-slate-200 bg-slate-50 text-xs font-medium text-slate-600"><SelectValue /></SelectTrigger><SelectContent>{STAGES.map((stage) => <SelectItem key={stage.key} value={stage.key}>{stage.label}</SelectItem>)}<SelectItem value="closed_lost">Closed lost</SelectItem></SelectContent></Select></div></article>;
}

function OpportunityDialog({ open, onOpenChange, form, setForm, companies, saving, onSubmit }) {
  const setField = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogTrigger asChild><Button className="cv-action-primary"><Plus className="mr-1.5 h-4 w-4" />New opportunity</Button></DialogTrigger><DialogContent><DialogHeader><DialogTitle className="font-display text-2xl">New opportunity</DialogTitle><DialogDescription>Add the essentials now; ClientVerse will create the operating workspace when the deal is won.</DialogDescription></DialogHeader><div className="grid gap-4 py-2"><div className="grid gap-1.5"><Label htmlFor="opportunity-name">Opportunity name <span className="text-red-500">*</span></Label><Input id="opportunity-name" value={form.name} onChange={(event) => setField("name", event.target.value)} placeholder="e.g. Q3 services expansion" /></div><div className="grid gap-1.5"><Label htmlFor="opportunity-value">Estimated value</Label><Input id="opportunity-value" type="number" min="0" value={form.value} onChange={(event) => setField("value", event.target.value)} placeholder="0" /></div><div className="grid gap-1.5"><Label>Company</Label><Select value={form.company_id} onValueChange={(value) => setField("company_id", value)}><SelectTrigger><SelectValue placeholder="Select company" /></SelectTrigger><SelectContent>{companies.map((company) => <SelectItem key={company.id} value={company.id}>{company.name}</SelectItem>)}</SelectContent></Select></div><div className="grid gap-1.5"><Label>Starting stage</Label><Select value={form.stage} onValueChange={(value) => setField("stage", value)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{STAGES.slice(0, 4).map((stage) => <SelectItem key={stage.key} value={stage.key}>{stage.label}</SelectItem>)}</SelectContent></Select></div></div><DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button disabled={saving} onClick={onSubmit} className="cv-action-primary">{saving ? "Creating…" : "Create opportunity"}</Button></DialogFooter></DialogContent></Dialog>;
}
