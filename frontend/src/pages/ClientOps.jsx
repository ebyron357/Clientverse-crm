import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { api, formatErr, money, STATUS_COLOR } from "@/lib/api";
import { toast } from "sonner";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CalendarClock, CircleDollarSign, FileText, Handshake, Link2, Loader2, ShieldCheck, Sparkles, Star, UsersRound } from "lucide-react";

const defaultData = { workspaces: [], summary: null, documents: [], estimates: [], invoices: [], referrals: [], appointments: [], rules: [], templates: [], reviews: [], capacity: [], playbooks: [], applications: [], portalLinks: [] };
const statusClass = (status) => STATUS_COLOR[status] || "bg-slate-100 text-slate-600 border-slate-200";
const dateLabel = (value) => value ? new Date(value).toLocaleString() : "—";

export default function ClientOps() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [data, setData] = useState(defaultData);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [workspaceId, setWorkspaceId] = useState("");
  const [portalClient, setPortalClient] = useState("");
  const [documentForm, setDocumentForm] = useState({ title: "", external_url: "", client_visible: true, requires_approval: true });
  const [estimateForm, setEstimateForm] = useState({ title: "", line: "Service package", amount: "" });
  const [referralForm, setReferralForm] = useState({ name: "", source_type: "partner" });
  const [appointmentForm, setAppointmentForm] = useState({ title: "", start: "", end: "" });
  const [reviewMessage, setReviewMessage] = useState("");
  const [ruleTemplate, setRuleTemplate] = useState("new_lead_follow_up");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const calls = [
        api.get("/workspaces"), api.get("/client-ops/summary"), api.get("/documents"), api.get("/estimates"), api.get("/invoices"),
        api.get("/referrals"), api.get("/appointments"), api.get("/automations/safe-rules"), api.get("/reviews"), api.get("/delivery/capacity"), api.get("/playbooks"),
      ];
      if (isAdmin) calls.push(api.get("/portal-links"));
      const results = await Promise.all(calls);
      const [workspaces, summary, documents, estimates, invoices, referrals, appointments, automations, reviews, capacity, playbooks, portals] = results.map((result) => result.data);
      setData({ workspaces, summary, documents, estimates, invoices, referrals, appointments, rules: automations.rules || [], templates: automations.templates || [], reviews, capacity: capacity.people || [], playbooks: playbooks.templates || [], applications: playbooks.applications || [], portalLinks: portals || [] });
      setWorkspaceId((current) => current || workspaces[0]?.id || "");
    } catch (error) {
      toast.error("Could not load Client Operations", { description: formatErr(error.response?.data?.detail) });
    } finally {
      setLoading(false);
    }
  }, [isAdmin]);

  useEffect(() => { load(); }, [load]);
  const workspace = useMemo(() => data.workspaces.find((item) => item.id === workspaceId), [data.workspaces, workspaceId]);
  const inWorkspace = (items) => items.filter((item) => item.workspace_id === workspaceId);
  const run = async (fn, success) => {
    setBusy(true);
    try { await fn(); toast.success(success); await load(); }
    catch (error) { toast.error("Action could not be completed", { description: formatErr(error.response?.data?.detail) }); }
    finally { setBusy(false); }
  };
  const createPortal = () => run(async () => {
    const { data: result } = await api.post("/portal-links", { workspace_id: workspaceId, client_label: portalClient || workspace?.name || "Client" });
    const url = `${window.location.origin}${result.portal_path}`;
    try { await navigator.clipboard.writeText(url); toast.success("Secure portal URL copied"); } catch { toast.message("Portal URL generated", { description: "Copy it from the new portal link card." }); }
    setPortalClient("");
  }, "Client portal link created");
  const createDocument = () => run(async () => {
    await api.post("/documents", { workspace_id: workspaceId, title: documentForm.title, external_url: documentForm.external_url || null, client_visible: documentForm.client_visible, requires_approval: documentForm.requires_approval });
    setDocumentForm({ title: "", external_url: "", client_visible: true, requires_approval: true });
  }, "Document coordination record created");
  const createEstimate = () => run(async () => {
    await api.post("/estimates", { workspace_id: workspaceId, title: estimateForm.title, lines: [{ label: estimateForm.line || "Service", quantity: 1, unit_price: Number(estimateForm.amount || 0) }] });
    setEstimateForm({ title: "", line: "Service package", amount: "" });
  }, "Estimate drafted");
  const createReferral = () => run(async () => { await api.post("/referrals", { ...referralForm, company_id: workspace?.company_id || null }); setReferralForm({ name: "", source_type: "partner" }); }, "Referral source added");
  const createAppointment = () => run(async () => {
    await api.post("/appointments", { title: appointmentForm.title, workspace_id: workspaceId, company_id: workspace?.company_id || null, owner: user?.email, start_at: new Date(appointmentForm.start).toISOString(), end_at: new Date(appointmentForm.end).toISOString(), appointment_type: "client" });
    setAppointmentForm({ title: "", start: "", end: "" });
  }, "Appointment scheduled");
  const createRule = () => run(async () => { await api.post("/automations/safe-rules", { template: ruleTemplate, workspace_id: workspaceId, owner: user?.email, enabled: true }); }, "Safe automation enabled");
  const createReview = () => run(async () => { await api.post("/reviews", { workspace_id: workspaceId, message: reviewMessage || null }); setReviewMessage(""); }, "Review request prepared for human approval");
  const applyPlaybook = (key) => run(async () => { await api.post(`/playbooks/${key}/apply`, { workspace_id: workspaceId }); }, "Playbook tasks added to the workspace");

  if (loading) return <div className="cv-page"><div className="cv-card animate-pulse p-7 text-slate-400">Loading client operations…</div></div>;
  const summary = data.summary || {};
  return <div className="cv-page space-y-6" data-testid="client-ops-page">
    <header className="cv-page-header">
      <div><div className="cv-eyebrow">Client value layer</div><h1 className="cv-page-title">Client Operations</h1><p className="cv-page-description">Portal access, commercial coordination, field follow-through, and safe operating playbooks in one tenant-scoped workspace.</p></div>
      <WorkspacePicker workspaces={data.workspaces} value={workspaceId} onChange={setWorkspaceId} />
    </header>
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      <Metric icon={Link2} label="Portal links" value={data.portalLinks.filter((item) => item.status === "active").length} tone="cyan" />
      <Metric icon={FileText} label="Documents" value={summary.documents || 0} tone="slate" />
      <Metric icon={CircleDollarSign} label="Active estimates" value={summary.active_estimates || 0} tone="violet" />
      <Metric icon={CalendarClock} label="Appointments" value={summary.scheduled_appointments || 0} tone="amber" />
      <Metric icon={Star} label="Reviews to approve" value={summary.reviews_awaiting_human_send || 0} tone="rose" />
    </div>
    <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"><ShieldCheck className="mr-2 inline h-4 w-4" /><strong>Safe-by-default:</strong> payment collection, email/SMS sends, and public review requests are never automatic. Their provider connections are visibly configuration-dependent.</div>

    <Tabs defaultValue="portal">
      <TabsList className="w-full justify-start overflow-x-auto"><TabsTrigger value="portal">Client portal</TabsTrigger><TabsTrigger value="commercial">Commercial & documents</TabsTrigger><TabsTrigger value="field">Appointments</TabsTrigger><TabsTrigger value="growth">Growth</TabsTrigger><TabsTrigger value="automation">Safe automation</TabsTrigger><TabsTrigger value="delivery">Capacity & playbooks</TabsTrigger></TabsList>
      <TabsContent value="portal" className="mt-5"><div className="grid gap-5 lg:grid-cols-[1.05fr_.95fr]"><section className="cv-card p-5"><div className="flex items-start gap-3"><span className="rounded-xl bg-cyan-50 p-2 text-[#0a6177]"><Link2 className="h-5 w-5" /></span><div><h2 className="cv-card-title">Secure client portal</h2><p className="cv-card-description">Share approved commitments, documents, estimates, invoices, and a request form through an unguessable workspace-specific link.</p></div></div>{isAdmin ? <div className="mt-5 grid gap-3"><div className="grid gap-1.5"><Label>Client-facing label</Label><Input value={portalClient} onChange={(event) => setPortalClient(event.target.value)} placeholder={workspace?.name || "Choose a workspace"} /></div><Button disabled={busy || !workspaceId} onClick={createPortal} className="cv-action-primary"><Link2 className="mr-1.5 h-4 w-4" />Create secure portal link</Button></div> : <div className="mt-5 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">Only workspace administrators can issue or revoke client portal links.</div>}</section><section className="cv-card overflow-hidden"><div className="cv-card-header"><div><h2 className="cv-card-title">Active links</h2><p className="cv-card-description">Tokens are never shown again after creation.</p></div></div><div className="divide-y divide-slate-100">{data.portalLinks.filter((item) => item.workspace_id === workspaceId).map((item) => <div className="px-5 py-3" key={item.id}><div className="flex items-center justify-between gap-3"><span className="font-medium text-slate-800">{item.client_label}</span><Badge className={item.status === "active" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-100 text-slate-600"}>{item.status}</Badge></div><p className="mt-1 text-xs text-slate-500">Created {dateLabel(item.created_at)}{item.expires_at ? ` · expires ${dateLabel(item.expires_at)}` : ""}</p></div>)}{!data.portalLinks.filter((item) => item.workspace_id === workspaceId).length && <Empty label="No portal links have been created for this workspace." />}</div></section></div></TabsContent>
      <TabsContent value="commercial" className="mt-5"><div className="grid gap-5 xl:grid-cols-2"><RecordForm title="Document & approval coordination" icon={FileText} action="Add document" disabled={busy || !workspaceId} onSubmit={createDocument}><Field label="Document title"><Input value={documentForm.title} onChange={(event) => setDocumentForm({ ...documentForm, title: event.target.value })} placeholder="Proposal, scope, or signed file" /></Field><Field label="Secure external document URL (optional)"><Input value={documentForm.external_url} onChange={(event) => setDocumentForm({ ...documentForm, external_url: event.target.value })} placeholder="https://…" /></Field><p className="text-xs text-slate-500">Client-visible documents remain hidden until you approve or share them.</p></RecordForm><RecordForm title="Estimate to invoice" icon={CircleDollarSign} action="Create estimate" disabled={busy || !workspaceId} onSubmit={createEstimate}><Field label="Estimate title"><Input value={estimateForm.title} onChange={(event) => setEstimateForm({ ...estimateForm, title: event.target.value })} placeholder="Monthly service package" /></Field><div className="grid gap-3 sm:grid-cols-2"><Field label="Line item"><Input value={estimateForm.line} onChange={(event) => setEstimateForm({ ...estimateForm, line: event.target.value })} /></Field><Field label="Amount"><Input inputMode="decimal" value={estimateForm.amount} onChange={(event) => setEstimateForm({ ...estimateForm, amount: event.target.value })} placeholder="1250" /></Field></div><p className="text-xs text-amber-700">Invoices coordinate local records. Stripe payment collection stays disabled until its lifecycle certification passes.</p></RecordForm></div><div className="mt-5 grid gap-5 xl:grid-cols-2"><CommercialList title="Documents" items={inWorkspace(data.documents)} empty="No workspace documents" render={(item) => <><strong>{item.title}</strong><Meta status={item.status} extra={item.client_visible ? "Client visible" : "Internal"} /></>} /><CommercialList title="Estimates & invoices" items={[...inWorkspace(data.estimates), ...inWorkspace(data.invoices)]} empty="No commercial records" render={(item) => <div className="flex items-center justify-between gap-3"><div><strong>{item.title}</strong><Meta status={item.status} extra={money(item.total)} /></div>{isAdmin && item.id?.startsWith("est_") && ["sent", "approved"].includes(item.status) && <Button size="sm" variant="outline" onClick={() => run(() => api.post(`/estimates/${item.id}/invoice`), "Invoice created from estimate")}>Create invoice</Button>}</div>} /></div></TabsContent>
      <TabsContent value="field" className="mt-5"><div className="grid gap-5 xl:grid-cols-[.9fr_1.1fr]"><RecordForm title="Schedule an appointment" icon={CalendarClock} action="Schedule" disabled={busy || !workspaceId} onSubmit={createAppointment}><Field label="Appointment title"><Input value={appointmentForm.title} onChange={(event) => setAppointmentForm({ ...appointmentForm, title: event.target.value })} placeholder="Client check-in" /></Field><div className="grid gap-3 sm:grid-cols-2"><Field label="Start"><Input type="datetime-local" value={appointmentForm.start} onChange={(event) => setAppointmentForm({ ...appointmentForm, start: event.target.value })} /></Field><Field label="End"><Input type="datetime-local" value={appointmentForm.end} onChange={(event) => setAppointmentForm({ ...appointmentForm, end: event.target.value })} /></Field></div><p className="text-xs text-slate-500">Owner conflicts are rejected before the schedule is saved. Reminders create internal review tasks only.</p></RecordForm><CommercialList title="Workspace appointments" items={inWorkspace(data.appointments)} empty="No appointments" render={(item) => <div className="flex items-center justify-between gap-3"><div><strong>{item.title}</strong><Meta status={item.status} extra={dateLabel(item.start_at)} /></div><Button size="sm" variant="outline" onClick={() => run(() => api.post(`/appointments/${item.id}/reminder`), "Internal reminder task prepared")}>Prepare reminder</Button></div>} /></div></TabsContent>
      <TabsContent value="growth" className="mt-5"><div className="grid gap-5 xl:grid-cols-2"><RecordForm title="Referral attribution" icon={Handshake} action="Add referral source" disabled={busy} onSubmit={createReferral}><Field label="Source name"><Input value={referralForm.name} onChange={(event) => setReferralForm({ ...referralForm, name: event.target.value })} placeholder="Referral partner or campaign" /></Field><Field label="Source type"><Select value={referralForm.source_type} onValueChange={(value) => setReferralForm({ ...referralForm, source_type: value })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="partner">Partner</SelectItem><SelectItem value="customer">Customer referral</SelectItem><SelectItem value="campaign">Campaign</SelectItem><SelectItem value="review">Review</SelectItem></SelectContent></Select></Field></RecordForm><RecordForm title="Review request control" icon={Star} action="Prepare for approval" disabled={busy || !workspaceId} onSubmit={createReview}><Field label="Draft note (optional)"><Textarea value={reviewMessage} onChange={(event) => setReviewMessage(event.target.value)} placeholder="Thank you for trusting our team…" /></Field><p className="text-xs text-amber-700">This creates a governed review request only. It does not post or send anything automatically.</p></RecordForm></div><div className="mt-5 grid gap-5 xl:grid-cols-2"><CommercialList title="Referral sources" items={data.referrals} empty="No referral attribution records" render={(item) => <><strong>{item.name}</strong><Meta status={item.status} extra={item.source_type} /></>} /><CommercialList title="Review requests" items={inWorkspace(data.reviews)} empty="No review requests" render={(item) => <><strong>Human review required</strong><Meta status={item.status} extra="Outbound disabled" /></>} /></div></TabsContent>
      <TabsContent value="automation" className="mt-5"><div className="grid gap-5 xl:grid-cols-[.85fr_1.15fr]"><RecordForm title="Safe automation controls" icon={ShieldCheck} action="Enable safe workflow" disabled={busy || !isAdmin || !workspaceId} onSubmit={createRule}><Field label="Template"><Select value={ruleTemplate} onValueChange={setRuleTemplate}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{data.templates.map((item) => <SelectItem key={item.key} value={item.key}>{item.label}</SelectItem>)}</SelectContent></Select></Field><p className="text-xs text-amber-700">Rules only create internal tasks and notices. Outbound email, SMS, and webhooks are disabled by this feature.</p>{!isAdmin && <p className="text-xs text-slate-500">Only administrators can configure automated rules.</p>}</RecordForm><CommercialList title="Enabled task-based workflows" items={data.rules} empty="No safe automation rules" render={(item) => <div className="flex items-center justify-between gap-3"><div><strong>{data.templates.find((template) => template.key === item.template)?.label || item.template}</strong><Meta status={item.enabled ? "approved" : "draft"} extra="Outbound disabled" /></div>{isAdmin && <Button size="sm" onClick={() => run(() => api.post(`/automations/safe-rules/${item.id}/run`), "Safe workflow created an internal task")}>Run safely</Button>}</div>} /></div></TabsContent>
      <TabsContent value="delivery" className="mt-5"><div className="grid gap-5 xl:grid-cols-2"><section className="cv-card overflow-hidden"><div className="cv-card-header"><div><h2 className="cv-card-title">Team capacity and SLA context</h2><p className="cv-card-description">Open tasks and overdue work are grouped by owner to make delivery pressure visible.</p></div><UsersRound className="h-5 w-5 text-[#1a9fbf]" /></div><div className="divide-y divide-slate-100">{data.capacity.map((item) => <div className="flex items-center justify-between gap-3 px-5 py-3" key={item.owner}><div><strong>{item.owner}</strong><p className="mt-1 text-xs text-slate-500">{item.open_tasks} open tasks · {item.active_workspaces} workspaces</p></div><Badge className={item.overdue ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}>{item.overdue} overdue</Badge></div>)}{!data.capacity.length && <Empty label="No open task workload is currently assigned." />}</div></section><section className="cv-card overflow-hidden"><div className="cv-card-header"><div><h2 className="cv-card-title">Vertical playbooks</h2><p className="cv-card-description">Apply an industry-specific task sequence to the selected client workspace. Re-applying is safely idempotent.</p></div><Sparkles className="h-5 w-5 text-[#1a9fbf]" /></div><div className="divide-y divide-slate-100">{data.playbooks.map((item) => <div className="flex items-center justify-between gap-3 px-5 py-3" key={item.key}><div><strong>{item.label}</strong><p className="mt-1 text-xs text-slate-500">{item.tasks.length} accountable task prompts</p></div>{isAdmin && <Button size="sm" variant="outline" disabled={busy || !workspaceId} onClick={() => applyPlaybook(item.key)}>Apply</Button>}</div>)}</div></section></div></TabsContent>
    </Tabs>
  </div>;
}

function WorkspacePicker({ workspaces, value, onChange }) { return <div className="min-w-[230px]"><Label className="sr-only">Active client workspace</Label><Select value={value} onValueChange={onChange}><SelectTrigger aria-label="Active client workspace"><SelectValue placeholder="Choose a workspace" /></SelectTrigger><SelectContent>{workspaces.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent></Select></div>; }
function Metric({ icon: Icon, label, value, tone }) { const tones = { cyan: "bg-cyan-50 text-cyan-700", slate: "bg-slate-100 text-slate-600", violet: "bg-violet-50 text-violet-700", amber: "bg-amber-50 text-amber-700", rose: "bg-rose-50 text-rose-700" }; return <div className="cv-card p-4"><div className="flex items-center justify-between"><span className={`rounded-lg p-2 ${tones[tone]}`}><Icon className="h-4 w-4" /></span><span className="font-display text-2xl font-bold">{value}</span></div><p className="mt-3 text-xs font-semibold uppercase tracking-[.08em] text-slate-500">{label}</p></div>; }
function Field({ label, children }) { return <div className="grid gap-1.5"><Label>{label}</Label>{children}</div>; }
function RecordForm({ title, icon: Icon, action, disabled, onSubmit, children }) { return <section className="cv-card p-5"><div className="flex items-start gap-3"><span className="rounded-xl bg-slate-100 p-2 text-slate-600"><Icon className="h-5 w-5" /></span><div><h2 className="cv-card-title">{title}</h2><p className="cv-card-description">All records remain scoped to the selected client workspace.</p></div></div><div className="mt-5 grid gap-3">{children}<Button className="cv-action-primary" disabled={disabled} onClick={onSubmit}>{disabled && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}{action}</Button></div></section>; }
function CommercialList({ title, items, empty, render }) { return <section className="cv-card overflow-hidden"><div className="cv-card-header"><div><h2 className="cv-card-title">{title}</h2></div></div><div className="divide-y divide-slate-100">{items.map((item) => <div className="px-5 py-3" key={item.id}>{render(item)}</div>)}{!items.length && <Empty label={empty} />}</div></section>; }
function Meta({ status, extra }) { return <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500"><Badge className={`text-[10px] ${statusClass(status)}`}>{String(status || "draft").replaceAll("_", " ")}</Badge><span>{extra}</span></p>; }
function Empty({ label }) { return <div className="px-5 py-8 text-center text-sm text-slate-500">{label}</div>; }
