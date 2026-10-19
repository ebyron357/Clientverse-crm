import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, formatErr, money } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { StatusDot } from "@/components/page/Page";
import { CheckCircle2, ExternalLink, FileText, Info, Link2Off, Loader2, MessageSquarePlus, ReceiptText, ShieldCheck } from "lucide-react";

// A client opens this page from a link, so it is always light (App.js forces the theme on
// /portal/*) and carries no app chrome: one calm column of what the client may see.

const COMMITMENT_TONE = { done: "success", completed: "success", met: "success", at_risk: "warning", blocked: "danger", missed: "danger", in_progress: "brand" };
const label = (value) => { const text = String(value ?? "").replaceAll("_", " "); return text.charAt(0).toUpperCase() + text.slice(1); };

export default function ClientPortal() {
  const { token } = useParams(); const [data, setData] = useState(null); const [error, setError] = useState(""); const [title, setTitle] = useState(""); const [priority, setPriority] = useState("medium"); const [busy, setBusy] = useState(false); const [sent, setSent] = useState(false);
  const load = useCallback(async () => { try { const result = await api.get(`/portal/${token}`); setData(result.data); } catch (requestError) { setError(formatErr(requestError.response?.data?.detail)); } }, [token]);
  useEffect(() => { load(); }, [load]);
  const submit = async () => { if (!title.trim()) return; setBusy(true); try { await api.post(`/portal/${token}/requests`, { title: title.trim(), priority }); setTitle(""); setSent(true); } catch (requestError) { setError(formatErr(requestError.response?.data?.detail)); } finally { setBusy(false); } };

  if (error) {
    return <PortalFrame><StateCard><span className="mb-3 flex size-10 items-center justify-center rounded-full bg-muted"><Link2Off className="size-[18px] text-muted-foreground" aria-hidden="true" /></span><h1 className="text-lg font-semibold tracking-tight text-foreground">This portal link is unavailable</h1><p className="mt-1.5 text-[13px] leading-5 text-muted-foreground">{error}</p></StateCard></PortalFrame>;
  }
  if (!data) {
    return <PortalFrame><StateCard><Loader2 className="size-5 animate-spin text-brand" aria-hidden="true" /><p className="mt-3 text-[13px] text-muted-foreground" role="status">Opening secure client workspace…</p></StateCard></PortalFrame>;
  }

  return (
    <PortalFrame>
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground">ClientVerse client portal</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-foreground">{data.workspace.name}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 text-[13px] text-muted-foreground">
            <span>{data.client_label}</span><span aria-hidden="true">·</span>
            <span>{data.company?.name || "Client workspace"}</span><span aria-hidden="true">·</span>
            <span className="capitalize">{data.workspace.stage}</span>
          </p>
        </div>
        <span className="inline-flex shrink-0 items-center gap-1.5 self-start rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 sm:self-auto">
          <ShieldCheck className="size-3.5" aria-hidden="true" />Secure shared view
        </span>
      </header>

      <p className="mt-5 flex gap-2 rounded-lg border border-border bg-card px-3 py-2 text-[13px] leading-5 text-muted-foreground">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />{data.capability_note}
      </p>

      <div className="mt-6 grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-5">
          <PortalList icon={CheckCircle2} title="Commitments" items={data.commitments} empty="No shared commitments" render={(item) => <>
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-medium text-foreground">{item.title}</div>
              <div className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                <StatusDot tone={COMMITMENT_TONE[item.status] || "neutral"} className="text-xs">{label(item.status)}</StatusDot>
                <span aria-hidden="true">·</span>
                <span className="tabular">due {item.due_date ? new Date(item.due_date).toLocaleDateString() : "not scheduled"}</span>
              </div>
            </div>
          </>} />
          <PortalList icon={FileText} title="Shared documents" items={data.documents} empty="No approved shared documents" render={(item) => <>
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-medium text-foreground">{item.title}</div>
              <div className="mt-1 text-xs text-muted-foreground first-letter:uppercase">{item.kind} · {item.status}</div>
            </div>
            {item.external_url && <a className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-brand hover:underline" href={item.external_url} target="_blank" rel="noreferrer">Open document<ExternalLink className="size-3" aria-hidden="true" /></a>}
          </>} />
          <PortalList icon={ReceiptText} title="Estimates & invoices" items={[...data.estimates, ...data.invoices]} empty="No shared commercial records" render={(item) => <>
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-medium text-foreground">{item.title}</div>
              <div className="mt-1 text-xs text-muted-foreground first-letter:uppercase">{item.status} · {item.payment_status || "payment provider status unavailable"}</div>
            </div>
            <div className="tabular shrink-0 text-[13px] font-semibold text-foreground">{money(item.total)}</div>
          </>} />
        </div>

        <section className="rounded-xl border border-border bg-card lg:sticky lg:top-6" aria-labelledby="portal-request-title">
          <div className="border-b border-border/80 px-4 py-3">
            <h2 id="portal-request-title" className="flex items-center gap-2 text-sm font-semibold tracking-tight text-foreground">
              <MessageSquarePlus className="size-4 text-muted-foreground" aria-hidden="true" />Send a workspace request
            </h2>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">Your request is recorded for the delivery team. This portal never sends messages on your behalf.</p>
          </div>
          <div className="space-y-3 p-4">
            {sent && <p className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[13px] text-emerald-700" role="status"><CheckCircle2 className="size-4 shrink-0" aria-hidden="true" />Your request has been added to the workspace.</p>}
            <div className="grid gap-1.5">
              <Label htmlFor="portal-request" className="text-[13px]">Request</Label>
              <Textarea id="portal-request" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="What do you need help with?" className="min-h-[96px] bg-card" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="portal-priority" className="text-[13px]">Priority</Label>
              <select id="portal-priority" className="h-10 rounded-md border border-input bg-card px-3 text-base text-foreground shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:h-9 sm:text-sm" value={priority} onChange={(event) => setPriority(event.target.value)}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select>
            </div>
            <Button onClick={submit} disabled={busy} className="h-10 w-full sm:h-9">{busy ? "Sending…" : "Submit request"}</Button>
          </div>
        </section>
      </div>
    </PortalFrame>
  );
}

function PortalFrame({ children }) { return <main className="min-h-screen bg-muted/40 px-4 py-8 sm:px-6 sm:py-12"><div className="mx-auto max-w-5xl">{children}</div></main>; }
function StateCard({ children }) { return <div className="mx-auto mt-16 flex max-w-md flex-col items-center rounded-xl border border-border bg-card px-6 py-10 text-center">{children}</div>; }
function PortalList({ icon: Icon, title, items, empty, render }) {
  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card">
      <h2 className="flex items-center gap-2 border-b border-border/80 px-4 py-3 text-sm font-semibold tracking-tight text-foreground">
        <Icon className="size-4 text-muted-foreground" aria-hidden="true" />{title}
        {items.length ? <span className="tabular text-xs font-normal text-muted-foreground">{items.length}</span> : null}
      </h2>
      {items.length ? (
        <ul className="divide-y divide-border/70">{items.map((item) => <li key={item.id} className="flex items-start gap-3 px-4 py-3">{render(item)}</li>)}</ul>
      ) : <p className="px-4 py-6 text-center text-[13px] text-muted-foreground">{empty}</p>}
    </section>
  );
}
