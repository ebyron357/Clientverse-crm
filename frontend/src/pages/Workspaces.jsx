import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { Avatar, PageHeader, StatusDot, Toolbar, ViewTabs } from "@/components/page/Page";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { BriefcaseBusiness, ChevronRight, CircleAlert, Plus, RefreshCw, Search } from "lucide-react";

const LIFECYCLE = ["onboard", "serve", "retain", "expand"];
const STAGE_META = { onboard: { label: "Onboard", tone: "violet" }, serve: { label: "Serve", tone: "brand" }, retain: { label: "Retain", tone: "warning" }, expand: { label: "Expand", tone: "success" } };
const HEALTH_TONE = { healthy: "success", at_risk: "warning", critical: "danger" };
const bandLabel = (band) => String(band || "").replace("_", " ").replace(/^\w/, (char) => char.toUpperCase());
const shortDate = (value) => value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : null;

export default function Workspaces() {
  const navigate = useNavigate(); const [rows, setRows] = useState([]); const [companies, setCompanies] = useState([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [open, setOpen] = useState(false); const [saving, setSaving] = useState(false); const [query, setQuery] = useState(""); const [stage, setStage] = useState("all"); const [form, setForm] = useState({ name: "", company_id: "", stage: "onboard" });
  const load = useCallback(async () => { setLoading(true); setError(""); const [workspaceResponse, companyResponse, dashboardResponse] = await Promise.allSettled([api.get("/workspaces"), api.get("/companies"), api.get("/dashboard")]); if (workspaceResponse.status !== "fulfilled") { setError("Client workspaces could not be loaded. Your portfolio data is unchanged — try again when the connection is available."); setLoading(false); return; } const portfolio = dashboardResponse.status === "fulfilled" ? (dashboardResponse.value.data.portfolio || []) : []; const healthMap = Object.fromEntries(portfolio.map((item) => [item.id, item.health])); const commitmentMap = Object.fromEntries(portfolio.map((item) => [item.id, item.top_commitment || item.next_commitment || null])); setRows(workspaceResponse.value.data.map((workspace) => ({ ...workspace, health: healthMap[workspace.id] || workspace.health, top_commitment: commitmentMap[workspace.id] || workspace.top_commitment || workspace.next_commitment_due || null }))); if (companyResponse.status === "fulfilled") setCompanies(companyResponse.value.data); setLoading(false); }, []);
  useEffect(() => { load(); }, [load]);
  const filtered = useMemo(() => rows.filter((workspace) => `${workspace.name} ${companies.find((company) => company.id === workspace.company_id)?.name || ""}`.toLowerCase().includes(query.toLowerCase()) && (stage === "all" || workspace.stage === stage)), [rows, companies, query, stage]);
  const counts = useMemo(() => Object.fromEntries(LIFECYCLE.map((key) => [key, rows.filter((workspace) => workspace.stage === key).length])), [rows]);
  const create = async () => { if (!form.name.trim()) { toast.error("Workspace name is required."); return; } setSaving(true); try { const { data } = await api.post("/workspaces", { ...form, name: form.name.trim(), company_id: form.company_id || null }); toast.success("Client workspace created", { description: "Start with the health, commitments, and outcomes that matter to this account." }); setOpen(false); setForm({ name: "", company_id: "", stage: "onboard" }); navigate(`/workspaces/${data.id}`); } catch (requestError) { toast.error("Could not create client workspace", { description: formatErr(requestError.response?.data?.detail) }); } finally { setSaving(false); } };

  if (error) return <div className="cv-page"><div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card px-6 py-12 text-center" role="alert"><span className="flex size-10 items-center justify-center rounded-full bg-red-50 text-red-600"><CircleAlert className="size-5" aria-hidden="true" /></span><h1 className="mt-3 text-sm font-medium text-foreground">Client workspaces unavailable</h1><p className="mt-1 max-w-md text-[13px] leading-5 text-muted-foreground">{error}</p><Button size="sm" variant="outline" onClick={load} className="mt-4"><RefreshCw className="size-3.5" />Retry</Button></div></div>;

  const tabs = [{ value: "all", label: "All", count: rows.length }, ...LIFECYCLE.map((key) => ({ value: key, label: STAGE_META[key].label, count: counts[key] }))];
  return <div className="cv-page">
    <PageHeader icon={BriefcaseBusiness} title="Client workspaces" count={loading ? undefined : rows.length} description="Health, commitments and lifecycle for every client account."
      actions={<WorkspaceDialog open={open} onOpenChange={setOpen} form={form} setForm={setForm} companies={companies} saving={saving} onSubmit={create} />} />
    <ViewTabs label="Lifecycle stage" items={tabs} value={stage} onChange={setStage} />
    <Toolbar>
      <div className="relative w-full sm:w-64">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
        <Input value={query} onChange={(event) => setQuery(event.target.value)} className="h-8 pl-8 md:text-[13px]" placeholder="Search clients…" aria-label="Search client workspaces" />
      </div>
      {!loading && (query || stage !== "all") && <span className="tabular text-xs text-muted-foreground">{filtered.length} of {rows.length}</span>}
    </Toolbar>
    <div className="relative overflow-x-auto rounded-xl border border-border bg-card">
      {loading ? <WorkspaceSkeleton /> : filtered.length ? <table className="w-full text-[13px]">
        <thead><tr className="h-9 border-b border-border bg-muted/40 text-left text-xs font-medium text-muted-foreground">
          <th scope="col" className="w-full px-4 font-medium sm:w-[36%] lg:w-[28%]">Client</th>
          <th scope="col" className="hidden px-4 font-medium sm:table-cell">Stage</th>
          <th scope="col" className="px-4 font-medium">Health</th>
          <th scope="col" className="hidden px-4 font-medium lg:table-cell">Risk factors</th>
          <th scope="col" className="hidden px-4 font-medium md:table-cell">Next commitment</th>
          <th scope="col" className="hidden px-4 text-right font-medium md:table-cell">Created</th>
          <th scope="col" className="w-8 px-2"><span className="sr-only">Open</span></th>
        </tr></thead>
        <tbody>{filtered.map((workspace) => <WorkspaceRow key={workspace.id} workspace={workspace} company={companies.find((record) => record.id === workspace.company_id)} onClick={() => navigate(`/workspaces/${workspace.id}`)} />)}</tbody>
      </table> : <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
        <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground"><BriefcaseBusiness className="size-5" aria-hidden="true" /></span>
        <h2 className="mt-3 text-sm font-medium text-foreground">No workspaces match your view</h2>
        <p className="mt-1 max-w-sm text-[13px] text-muted-foreground">Adjust the search or stage, or create a workspace for an account.</p>
        <Button size="sm" onClick={() => setOpen(true)} className="mt-4"><Plus className="size-3.5" />New workspace</Button>
      </div>}
    </div>
  </div>;
}

function commitmentDue(commitment) {
  if (!commitment) return null;
  const title = commitment.title || commitment.name || "Commitment";
  const due = commitment.due_date || commitment.due || null;
  if (!due) return { title, label: null, overdue: false };
  const ms = new Date(due).getTime() - Date.now();
  const days = Math.round(ms / 86400000);
  if (ms < 0) return { title, label: `overdue ${Math.abs(days)}d`, overdue: true };
  if (days === 0) return { title, label: "due today", overdue: false };
  if (days <= 7) return { title, label: `due in ${days}d`, overdue: false };
  return { title, label: `due ${new Date(due).toLocaleDateString()}`, overdue: false };
}

function WorkspaceRow({ workspace, company, onClick }) {
  const health = workspace.health;
  const stageMeta = STAGE_META[workspace.stage] || STAGE_META.onboard;
  const due = commitmentDue(workspace.top_commitment);
  const risks = (health?.factors || []).filter((factor) => factor.impact < 0);
  return <tr onClick={onClick} className="group cursor-pointer border-b border-border/70 transition-colors last:border-0 hover:bg-muted/50">
    <td className="max-w-0 px-4 py-2.5">
      <button type="button" onClick={(event) => { event.stopPropagation(); onClick(); }} className="flex w-full min-w-0 items-center gap-2.5 rounded-md text-left" data-testid={`workspace-card-${workspace.id}`}>
        <Avatar name={workspace.name} size="sm" />
        <span className="min-w-0">
          <span className="block truncate font-medium text-foreground">{workspace.name}</span>
          <span className="block truncate text-xs text-muted-foreground">{company?.name || "No company linked"}<span className="sm:hidden"> · {stageMeta.label}</span></span>
        </span>
      </button>
    </td>
    <td className="hidden whitespace-nowrap px-4 py-2.5 sm:table-cell"><StatusDot tone={stageMeta.tone}>{stageMeta.label}</StatusDot></td>
    <td className="whitespace-nowrap px-4 py-2.5">{health ? <span className="inline-flex items-center gap-2"><StatusDot tone={HEALTH_TONE[health.band]}>{bandLabel(health.band)}</StatusDot><span className="tabular text-xs font-medium text-muted-foreground">{health.score}</span></span> : <span className="text-muted-foreground">—</span>}</td>
    <td className="hidden max-w-[220px] px-4 py-2.5 lg:table-cell">{risks.length ? <span className="block truncate text-foreground/80" title={risks.map((factor) => factor.detail || factor.factor).join(" · ")}>{risks[0].factor}{risks.length > 1 && <span className="text-muted-foreground"> +{risks.length - 1}</span>}</span> : <span className="text-muted-foreground">{health ? "None" : "—"}</span>}</td>
    <td className="hidden max-w-[240px] px-4 py-2.5 md:table-cell">{due ? <span className="block truncate" data-testid={`workspace-top-commitment-${workspace.id}`}><span className="text-foreground/80">{due.title}</span>{due.label && <span className={due.overdue ? "text-red-600" : "text-muted-foreground"}> · {due.label}</span>}</span> : <span className="text-muted-foreground">—</span>}</td>
    <td className="tabular hidden whitespace-nowrap px-4 py-2.5 text-right text-xs text-muted-foreground md:table-cell">{shortDate(workspace.created_at) || "—"}</td>
    <td className="w-8 px-2 py-2.5 text-muted-foreground/60"><ChevronRight className="size-4 transition-colors group-hover:text-foreground" aria-hidden="true" /></td>
  </tr>;
}

function WorkspaceDialog({ open, onOpenChange, form, setForm, companies, saving, onSubmit }) { const setField = (key, value) => setForm((current) => ({ ...current, [key]: value })); return <Dialog open={open} onOpenChange={onOpenChange}><DialogTrigger asChild><Button size="sm"><Plus className="size-3.5" />New workspace</Button></DialogTrigger><DialogContent><DialogHeader><DialogTitle>New client workspace</DialogTitle><DialogDescription>A Client 360 view for one relationship and its delivery commitments.</DialogDescription></DialogHeader><div className="grid gap-4 py-2"><div className="grid gap-1.5"><Label htmlFor="workspace-name">Workspace name <span className="text-red-600">*</span></Label><Input id="workspace-name" value={form.name} onChange={(event) => setField("name", event.target.value)} placeholder="e.g. Northstar — Client 360" /></div><div className="grid gap-1.5"><Label>Company</Label><Select value={form.company_id} onValueChange={(value) => setField("company_id", value)}><SelectTrigger aria-label="Company for the new workspace"><SelectValue placeholder="Select a company" /></SelectTrigger><SelectContent>{companies.map((company) => <SelectItem key={company.id} value={company.id}>{company.name}</SelectItem>)}</SelectContent></Select></div><div className="grid gap-1.5"><Label>Lifecycle stage</Label><Select value={form.stage} onValueChange={(value) => setField("stage", value)}><SelectTrigger aria-label="Lifecycle stage for the new workspace"><SelectValue /></SelectTrigger><SelectContent>{LIFECYCLE.map((key) => <SelectItem key={key} value={key}>{STAGE_META[key].label}</SelectItem>)}</SelectContent></Select></div></div><DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button disabled={saving} onClick={onSubmit}>{saving ? "Creating…" : "Create workspace"}</Button></DialogFooter></DialogContent></Dialog>; }
function WorkspaceSkeleton() { return <div className="divide-y divide-border/70"><div className="h-9 bg-muted/40" />{Array.from({ length: 4 }).map((_, index) => <div key={index} className="flex items-center gap-3 px-4 py-3"><Skeleton className="size-6 rounded-full" /><div className="flex-1"><Skeleton className="h-3.5 w-40" /><Skeleton className="mt-1.5 h-3 w-24" /></div><Skeleton className="h-3.5 w-20" /><Skeleton className="hidden h-3.5 w-24 sm:block" /></div>)}</div>; }
