import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { api, formatErr, money } from "@/lib/api";
import { toast } from "sonner";
import { Avatar, PageHeader, Section, StatStrip, StatusDot } from "@/components/page/Page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CalendarClock, ChevronRight, CircleDollarSign, Handshake, Info, Link2, Loader2, ShieldCheck } from "lucide-react";

const defaultData = { workspaces: [], summary: null, documents: [], estimates: [], invoices: [], referrals: [], appointments: [], rules: [], templates: [], reviews: [], capacity: [], playbooks: [], applications: [], portalLinks: [] };
const STATUS_TONE = { active: "success", approved: "success", accepted: "success", paid: "success", sent: "info", scheduled: "brand", confirmed: "brand", open: "info", in_progress: "info", in_review: "warning", requested: "warning", pending: "warning", awaiting_human_send: "warning", draft: "neutral", revoked: "neutral", expired: "neutral", cancelled: "neutral", canceled: "neutral", rejected: "danger", void: "danger", overdue: "danger", failed: "danger" };
const statusLabel = (status) => String(status || "draft").replaceAll("_", " ");
const dateLabel = (value) => value ? new Date(value).toLocaleString() : "—";
const shortDateTime = (value) => value ? new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "—";
const SECONDARY = ["field", "growth", "automation", "delivery"];
const TAB_LIST = "-mb-px h-auto justify-start gap-4 overflow-x-auto rounded-none bg-transparent p-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden";
const TAB = "group -mb-px h-9 shrink-0 gap-1.5 rounded-none border-b-2 border-transparent bg-transparent px-0.5 text-[13.5px] text-muted-foreground shadow-none data-[state=active]:border-foreground data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none";

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
  const [activeTab, setActiveTab] = useState("overview");
  const [showSecondary, setShowSecondary] = useState(false);

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
  const openTab = (value) => { setActiveTab(value); if (SECONDARY.includes(value)) setShowSecondary(true); };

  if (loading) return <div className="cv-page" aria-busy="true"><span className="sr-only">Loading client operations…</span><div className="mb-5 flex items-center justify-between"><Skeleton className="h-7 w-52" /><Skeleton className="h-8 w-56" /></div><Skeleton className="mb-5 h-[76px] rounded-xl" /><Skeleton className="mb-5 h-9 w-80" /><Skeleton className="h-44 rounded-xl" /></div>;
  const summary = data.summary || {};
  const workspaceLinks = data.portalLinks.filter((item) => item.workspace_id === workspaceId);
  const activeWorkspaceLinks = workspaceLinks.filter((item) => item.status === "active").length;
  const commercialCount = inWorkspace(data.documents).length + inWorkspace(data.estimates).length + inWorkspace(data.invoices).length;
  return <div className="cv-page" data-testid="client-ops-page">
    <PageHeader icon={Handshake} title="Client Operations" description="Portal access, commercial records and safe playbooks for each client workspace."
      actions={<WorkspacePicker workspaces={data.workspaces} value={workspaceId} onChange={setWorkspaceId} />} />
    <StatStrip className="mb-4" items={[
      { label: "Portal links", value: data.portalLinks.filter((item) => item.status === "active").length, detail: "All workspaces", onClick: () => openTab("portal") },
      { label: "Documents", value: summary.documents || 0, detail: "Coordination records", onClick: () => openTab("commercial") },
      { label: "Active estimates", value: summary.active_estimates || 0, detail: `${summary.scheduled_appointments || 0} appointment${summary.scheduled_appointments === 1 ? "" : "s"}`, onClick: () => openTab("commercial") },
      { label: "Reviews to approve", value: summary.reviews_awaiting_human_send || 0, tone: summary.reviews_awaiting_human_send ? "warning" : undefined, detail: "Waiting on a human send", onClick: () => openTab("growth") },
    ]} />
    <div className="mb-5 flex items-start gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-[13px] text-muted-foreground" role="note">
      <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-emerald-600" aria-hidden="true" />
      <p><span className="font-medium text-foreground">Safe by default:</span> payment collection, email/SMS sends and public review requests are never automatic. Their provider connections are visibly configuration-dependent.</p>
    </div>

    <Tabs value={activeTab} onValueChange={(value) => { setActiveTab(value); if (SECONDARY.includes(value)) setShowSecondary(true); }} data-testid="client-ops-tabs">
      <div className="flex items-end justify-between gap-3 border-b border-border">
        <TabsList className={`${TAB_LIST} min-w-0`}>
          <TabsTrigger value="overview" className={TAB} data-testid="tab-overview">Overview</TabsTrigger>
          <TabsTrigger value="portal" className={TAB}>Client portal<TabCount value={activeWorkspaceLinks} /></TabsTrigger>
          <TabsTrigger value="commercial" className={TAB}>Commercial<TabCount value={commercialCount} /></TabsTrigger>
          {(showSecondary || SECONDARY.includes(activeTab)) && (
            <>
              <TabsTrigger value="field" className={TAB}>Appointments<TabCount value={inWorkspace(data.appointments).length} /></TabsTrigger>
              <TabsTrigger value="growth" className={TAB}>Growth<TabCount value={data.referrals.length + inWorkspace(data.reviews).length} /></TabsTrigger>
              <TabsTrigger value="automation" className={TAB}>Safe automation<TabCount value={data.rules.length} /></TabsTrigger>
              <TabsTrigger value="delivery" className={TAB}>Capacity & playbooks</TabsTrigger>
            </>
          )}
        </TabsList>
        {!showSecondary && (
          <div className="shrink-0 pb-1.5"><Button type="button" size="sm" variant="outline" className="h-7" onClick={() => setShowSecondary(true)} aria-label="More workflows" data-testid="client-ops-show-more"><span className="sm:hidden">More</span><span className="hidden sm:inline">More workflows</span></Button></div>
        )}
      </div>

      <TabsContent value="overview" className="mt-5" data-testid="client-ops-overview">
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <QueueRow icon={Link2} title="Portal readiness" detail={`${activeWorkspaceLinks || 0} active link(s) for this workspace.`} action="Open portal tools" onClick={() => setActiveTab("portal")} />
          <QueueRow icon={CircleDollarSign} title="Commercial pulse" detail={`${summary.active_estimates || 0} active estimates · ${summary.documents || 0} documents.`} action="Review commercial" onClick={() => setActiveTab("commercial")} />
          <QueueRow icon={CalendarClock} title="Field & secondary" detail={`${summary.scheduled_appointments || 0} appointments · growth, automation and playbooks under More workflows.`} action="Open appointments" onClick={() => { setShowSecondary(true); setActiveTab("field"); }} />
        </div>
      </TabsContent>

      <TabsContent value="portal" className="mt-5">
        <div className="grid gap-5 lg:grid-cols-2">
          <Section card className="overflow-hidden" title="Secure client portal" description="Share approved records and a request form through an unguessable link.">
            {isAdmin ? <>
              <div className="p-4"><Field label="Client-facing label" id="portal-client-label"><Input id="portal-client-label" value={portalClient} onChange={(event) => setPortalClient(event.target.value)} placeholder={workspace?.name || "Choose a workspace"} /></Field></div>
              <FormFooter><Button size="sm" disabled={busy || !workspaceId} onClick={createPortal}><Link2 className="size-3.5" />Create secure portal link</Button></FormFooter>
            </> : <p className="p-4 text-[13px] text-muted-foreground">Only workspace administrators can issue or revoke client portal links.</p>}
          </Section>
          <Section card className="overflow-hidden" title="Active links" description="Tokens are never shown again after creation.">
            {workspaceLinks.map((item) => <Row key={item.id} title={item.client_label} meta={`Created ${dateLabel(item.created_at)}${item.expires_at ? ` · expires ${dateLabel(item.expires_at)}` : ""}`} right={<StatusDot tone={item.status === "active" ? "success" : "neutral"} className="capitalize">{item.status}</StatusDot>} />)}
            {!workspaceLinks.length && <Empty label="No portal links have been created for this workspace." />}
          </Section>
        </div>
      </TabsContent>

      <TabsContent value="commercial" className="mt-5">
        <div className="grid gap-5 xl:grid-cols-2">
          <RecordForm title="Document & approval coordination" action="Add document" disabled={busy || !workspaceId} busy={busy} onSubmit={createDocument}
            note="Client-visible documents remain hidden until you approve or share them.">
            <Field label="Document title" id="document-title"><Input id="document-title" value={documentForm.title} onChange={(event) => setDocumentForm({ ...documentForm, title: event.target.value })} placeholder="Proposal, scope, or signed file" /></Field>
            <Field label="Secure external document URL (optional)" id="document-url"><Input id="document-url" value={documentForm.external_url} onChange={(event) => setDocumentForm({ ...documentForm, external_url: event.target.value })} placeholder="https://…" /></Field>
          </RecordForm>
          <RecordForm title="Estimate to invoice" action="Create estimate" disabled={busy || !workspaceId} busy={busy} onSubmit={createEstimate} warn
            note="Invoices coordinate local records. Stripe payment collection stays disabled until its lifecycle certification passes.">
            <Field label="Estimate title" id="estimate-title"><Input id="estimate-title" value={estimateForm.title} onChange={(event) => setEstimateForm({ ...estimateForm, title: event.target.value })} placeholder="Monthly service package" /></Field>
            <div className="grid gap-3 sm:grid-cols-2"><Field label="Line item" id="estimate-line"><Input id="estimate-line" value={estimateForm.line} onChange={(event) => setEstimateForm({ ...estimateForm, line: event.target.value })} /></Field><Field label="Amount" id="estimate-amount"><Input id="estimate-amount" inputMode="decimal" value={estimateForm.amount} onChange={(event) => setEstimateForm({ ...estimateForm, amount: event.target.value })} placeholder="1250" /></Field></div>
          </RecordForm>
        </div>
        <div className="mt-5 grid gap-5 xl:grid-cols-2">
          <CommercialList title="Documents" items={inWorkspace(data.documents)} empty="No workspace documents" render={(item) => <Row title={item.title} status={item.status} extra={item.client_visible ? "Client visible" : "Internal"} />} />
          <CommercialList title="Estimates & invoices" items={[...inWorkspace(data.estimates), ...inWorkspace(data.invoices)]} empty="No commercial records" render={(item) => <Row title={item.title} status={item.status} extra={<span className="tabular">{money(item.total)}</span>}
            right={isAdmin && item.id?.startsWith("est_") && ["sent", "approved"].includes(item.status) && <Button size="sm" variant="outline" className="h-7" onClick={() => run(() => api.post(`/estimates/${item.id}/invoice`), "Invoice created from estimate")}>Create invoice</Button>} />} />
        </div>
      </TabsContent>

      <TabsContent value="field" className="mt-5">
        <div className="grid gap-5 xl:grid-cols-2">
          <RecordForm title="Schedule an appointment" action="Schedule" disabled={busy || !workspaceId} busy={busy} onSubmit={createAppointment}
            note="Owner conflicts are rejected before the schedule is saved. Reminders create internal review tasks only.">
            <Field label="Appointment title" id="appointment-title"><Input id="appointment-title" value={appointmentForm.title} onChange={(event) => setAppointmentForm({ ...appointmentForm, title: event.target.value })} placeholder="Client check-in" /></Field>
            <div className="grid gap-3 sm:grid-cols-2"><Field label="Start" id="appointment-start"><Input id="appointment-start" type="datetime-local" value={appointmentForm.start} onChange={(event) => setAppointmentForm({ ...appointmentForm, start: event.target.value })} /></Field><Field label="End" id="appointment-end"><Input id="appointment-end" type="datetime-local" value={appointmentForm.end} onChange={(event) => setAppointmentForm({ ...appointmentForm, end: event.target.value })} /></Field></div>
          </RecordForm>
          <CommercialList title="Workspace appointments" items={inWorkspace(data.appointments)} empty="No appointments" render={(item) => <Row title={item.title} status={item.status} extra={<span className="tabular">{shortDateTime(item.start_at)}</span>}
            right={<Button size="sm" variant="outline" className="h-7" onClick={() => run(() => api.post(`/appointments/${item.id}/reminder`), "Internal reminder task prepared")}>Prepare reminder</Button>} />} />
        </div>
      </TabsContent>

      <TabsContent value="growth" className="mt-5">
        <div className="grid gap-5 xl:grid-cols-2">
          <RecordForm title="Referral attribution" action="Add referral source" disabled={busy} busy={busy} onSubmit={createReferral}>
            <Field label="Source name" id="referral-name"><Input id="referral-name" value={referralForm.name} onChange={(event) => setReferralForm({ ...referralForm, name: event.target.value })} placeholder="Referral partner or campaign" /></Field>
            <Field label="Source type"><Select value={referralForm.source_type} onValueChange={(value) => setReferralForm({ ...referralForm, source_type: value })}><SelectTrigger aria-label="Source type"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="partner">Partner</SelectItem><SelectItem value="customer">Customer referral</SelectItem><SelectItem value="campaign">Campaign</SelectItem><SelectItem value="review">Review</SelectItem></SelectContent></Select></Field>
          </RecordForm>
          <RecordForm title="Review request control" action="Prepare for approval" disabled={busy || !workspaceId} busy={busy} onSubmit={createReview} warn
            note="This creates a governed review request only. It does not post or send anything automatically.">
            <Field label="Draft note (optional)" id="review-note"><Textarea id="review-note" value={reviewMessage} onChange={(event) => setReviewMessage(event.target.value)} placeholder="Thank you for trusting our team…" className="min-h-[72px]" /></Field>
          </RecordForm>
        </div>
        <div className="mt-5 grid gap-5 xl:grid-cols-2">
          <CommercialList title="Referral sources" items={data.referrals} empty="No referral attribution records" render={(item) => <Row title={item.name} status={item.status} extra={<span className="capitalize">{item.source_type}</span>} />} />
          <CommercialList title="Review requests" items={inWorkspace(data.reviews)} empty="No review requests" render={(item) => <Row title="Human review required" status={item.status} extra="Outbound disabled" />} />
        </div>
      </TabsContent>

      <TabsContent value="automation" className="mt-5">
        <div className="grid gap-5 xl:grid-cols-2">
          <RecordForm title="Safe automation controls" action="Enable safe workflow" disabled={busy || !isAdmin || !workspaceId} busy={busy} onSubmit={createRule} warn
            note={<>Rules only create internal tasks and notices. Outbound email, SMS, and webhooks are disabled by this feature.{!isAdmin && <span className="mt-1 block text-muted-foreground">Only administrators can configure automated rules.</span>}</>}>
            <Field label="Template"><Select value={ruleTemplate} onValueChange={setRuleTemplate}><SelectTrigger aria-label="Automation template"><SelectValue /></SelectTrigger><SelectContent>{data.templates.map((item) => <SelectItem key={item.key} value={item.key}>{item.label}</SelectItem>)}</SelectContent></Select></Field>
          </RecordForm>
          <CommercialList title="Enabled task-based workflows" items={data.rules} empty="No safe automation rules" render={(item) => <Row title={data.templates.find((template) => template.key === item.template)?.label || item.template} status={item.enabled ? "approved" : "draft"} statusText={item.enabled ? "Enabled" : "Disabled"} extra="Outbound disabled"
            right={isAdmin && <Button size="sm" variant="outline" className="h-7" onClick={() => run(() => api.post(`/automations/safe-rules/${item.id}/run`), "Safe workflow created an internal task")}>Run safely</Button>} />} />
        </div>
      </TabsContent>

      <TabsContent value="delivery" className="mt-5">
        <div className="grid gap-5 xl:grid-cols-2">
          <Section card className="overflow-hidden" title="Team capacity and SLA context" description="Open and overdue work grouped by owner.">
            {data.capacity.length > 0 && <div className="hidden h-9 grid-cols-[minmax(0,1fr)_90px_90px] items-center gap-3 border-b border-border bg-muted/40 px-4 text-xs font-medium text-muted-foreground sm:grid"><span>Owner</span><span className="text-right">Open tasks</span><span className="text-right">Overdue</span></div>}
            {data.capacity.map((item) => <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border/70 px-4 py-2.5 text-[13px] last:border-0 sm:grid-cols-[minmax(0,1fr)_90px_90px]" key={item.owner}>
              <div className="flex min-w-0 items-center gap-2.5"><Avatar name={item.owner} size="sm" /><div className="min-w-0"><div className="truncate font-medium text-foreground">{item.owner}</div><div className="text-xs text-muted-foreground"><span className="sm:hidden">{item.open_tasks} open tasks · </span>{item.active_workspaces} workspaces</div></div></div>
              <span className="tabular hidden text-right text-foreground/80 sm:block">{item.open_tasks}</span>
              <span className={`tabular text-right ${item.overdue ? "font-medium text-red-600" : "text-muted-foreground"}`}>{item.overdue}<span className="sm:hidden"> overdue</span></span>
            </div>)}
            {!data.capacity.length && <Empty label="No open task workload is currently assigned." />}
          </Section>
          <Section card className="overflow-hidden" title="Vertical playbooks" description="Industry task sequences. Re-applying is idempotent.">
            {data.playbooks.map((item) => <Row key={item.key} title={item.label} meta={`${item.tasks.length} accountable task prompts`} right={isAdmin && <Button size="sm" variant="outline" className="h-7" disabled={busy || !workspaceId} onClick={() => applyPlaybook(item.key)}>Apply</Button>} />)}
          </Section>
        </div>
      </TabsContent>
    </Tabs>
  </div>;
}

function TabCount({ value }) { return <span className="tabular rounded px-1 text-xs text-muted-foreground group-data-[state=active]:bg-muted group-data-[state=active]:text-foreground">{value}</span>; }
function WorkspacePicker({ workspaces, value, onChange }) { return <div className="w-full sm:w-60"><Label className="sr-only">Active client workspace</Label><Select value={value} onValueChange={onChange}><SelectTrigger aria-label="Active client workspace" className="h-8 text-[13px]"><SelectValue placeholder="Choose a workspace" /></SelectTrigger><SelectContent>{workspaces.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent></Select></div>; }
function QueueRow({ icon: Icon, title, detail, action, onClick }) {
  return <button type="button" onClick={onClick} className="group flex w-full items-center gap-3 border-b border-border/70 px-4 py-3 text-left transition-colors last:border-0 hover:bg-muted/50">
    <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground"><Icon className="size-4" aria-hidden="true" /></span>
    <span className="min-w-0 flex-1"><span className="block text-[13px] font-medium text-foreground">{title}</span><span className="block text-xs text-muted-foreground">{detail}</span></span>
    <span className="hidden shrink-0 text-xs text-muted-foreground transition-colors group-hover:text-foreground sm:inline">{action}</span>
    <ChevronRight className="size-4 shrink-0 text-muted-foreground/60 transition-colors group-hover:text-foreground" aria-hidden="true" />
  </button>;
}
function Field({ label, id, children }) { return <div className="grid gap-1.5"><Label htmlFor={id} className="text-[13px]">{label}</Label>{children}</div>; }
function FormFooter({ children }) { return <div className="flex items-center justify-end gap-2 border-t border-border bg-muted/30 px-4 py-2.5">{children}</div>; }
function RecordForm({ title, action, disabled, busy, onSubmit, note, warn = false, children }) {
  return <Section card title={title} className="flex flex-col overflow-hidden" bodyClassName="flex flex-1 flex-col">
    <div className="grid flex-1 content-start gap-3 p-4">
      {children}
      {note && <p className="flex items-start gap-1.5 text-xs leading-5 text-muted-foreground">{warn ? <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-amber-600" aria-hidden="true" /> : <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />}<span>{note}</span></p>}
    </div>
    <FormFooter><Button size="sm" disabled={disabled} onClick={onSubmit}>{busy && <Loader2 className="size-3.5 animate-spin" />}{action}</Button></FormFooter>
  </Section>;
}
function CommercialList({ title, items, empty, render }) { return <Section card className="overflow-hidden" title={title} actions={<span className="tabular text-xs text-muted-foreground">{items.length}</span>}>{items.map((item) => <Fragment key={item.id}>{render(item)}</Fragment>)}{!items.length && <Empty label={empty} />}</Section>; }
function Row({ title, meta, status, statusText, extra, right }) {
  return <div className="flex items-center justify-between gap-3 border-b border-border/70 px-4 py-2.5 transition-colors last:border-0 hover:bg-muted/40">
    <div className="min-w-0">
      <div className="truncate text-[13px] font-medium text-foreground">{title}</div>
      {(meta || status || extra) && <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
        {status !== undefined && <StatusDot tone={STATUS_TONE[status] || "neutral"} className="text-xs capitalize">{statusText || statusLabel(status)}</StatusDot>}
        {status !== undefined && extra && <span aria-hidden="true">·</span>}
        {extra && <span>{extra}</span>}
        {meta && <span>{meta}</span>}
      </div>}
    </div>
    {right && <div className="shrink-0">{right}</div>}
  </div>;
}
function Empty({ label }) { return <div className="px-4 py-8 text-center text-[13px] text-muted-foreground">{label}</div>; }
