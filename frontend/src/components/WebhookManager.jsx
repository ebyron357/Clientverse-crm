import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Section, StatusDot } from "@/components/page/Page";
import { Plus, Send, RotateCw, KeyRound, ShieldCheck, Copy, Webhook } from "lucide-react";

const EVENT_OPTIONS = ["commitment.*", "approval.*", "task.*", "deliverable.*", "mcp.*", "commitment.at_risk", "approval.requested", "task.created", "*"];

const DSTATUS = { delivered: "success", failed: "danger", pending: "warning" };

const TH_BASE = "h-9 px-4 text-xs font-medium text-muted-foreground";
const TH = `${TH_BASE} text-left`;
const ROW = "border-b border-border/70 transition-colors last:border-0 hover:bg-muted/50";
const CODE = "rounded bg-muted px-1.5 py-px font-mono text-[11.5px] text-muted-foreground";

const snippet = (secret) => `// Verify a ClientVerse webhook (Node.js / Express)
const crypto = require("crypto");
const SECRET = "${secret}";

app.post("/hooks", express.raw({ type: "*/*" }), (req, res) => {
  const header = req.headers["x-clientverse-signature"] || "";
  const received = header.replace("sha256=", "");
  const expected = crypto.createHmac("sha256", SECRET)
    .update(req.body)            // raw request body bytes
    .digest("hex");
  const ok = crypto.timingSafeEqual(
    Buffer.from(received), Buffer.from(expected)
  );
  if (!ok) return res.status(401).send("bad signature");
  // trusted: JSON.parse(req.body)
  res.sendStatus(200);
});`;

export default function WebhookManager() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [hooks, setHooks] = useState([]);
  const [deliveries, setDeliveries] = useState([]);
  const [open, setOpen] = useState(false);
  const [verify, setVerify] = useState(null);
  const [form, setForm] = useState({ name: "", url: "", events: [] });
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    if (!open || form.events.length === 0) { setPreview(null); return; }
    let active = true;
    api.post("/webhooks/match-preview", { patterns: form.events }).then((r) => active && setPreview(r.data)).catch(() => {});
    return () => { active = false; };
  }, [form.events, open]);

  const load = async () => {
    const [h, d] = await Promise.all([api.get("/webhooks"), api.get("/webhook-deliveries?limit=60")]);
    setHooks(h.data); setDeliveries(d.data);
  };
  useEffect(() => { load(); }, []);

  const toggle = async (wh, enabled) => { await api.patch(`/webhooks/${wh.id}`, { enabled }); toast.success(enabled ? "Endpoint enabled" : "Endpoint disabled"); load(); };
  const rotate = async (wh) => { await api.patch(`/webhooks/${wh.id}`, { rotate_secret: true }); toast.success("Secret rotated"); load(); };
  const test = async (wh) => { const { data } = await api.post(`/webhooks/${wh.id}/test`); toast[data.status === "delivered" ? "success" : "error"](`Test event → ${data.status}`); load(); };
  const replay = async (d) => { const { data } = await api.post(`/webhook-deliveries/${d.id}/replay`); toast[data.status === "delivered" ? "success" : "error"](`Replay → ${data.status}`); load(); };
  const openVerify = async (wh) => {
    try { const { data } = await api.get(`/webhooks/${wh.id}/secret`); setVerify({ ...wh, secret: data.secret }); }
    catch { toast.error("Only admins can reveal signing secrets"); }
  };
  const create = async () => {
    if (!form.name || !form.url) return;
    await api.post("/webhooks", form);
    toast.success("Webhook created"); setOpen(false); setForm({ name: "", url: "", events: [] }); load();
  };
  const toggleEvent = (ev) => setForm((f) => ({ ...f, events: f.events.includes(ev) ? f.events.filter((x) => x !== ev) : [...f.events, ev] }));
  const copy = (text, label) => { navigator.clipboard?.writeText(text); toast.success(`${label} copied`); };

  const newEndpoint = isAdmin && (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button size="sm" data-testid="new-webhook-button"><Plus aria-hidden="true" />New endpoint</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>New webhook endpoint</DialogTitle><DialogDescription>Signed HMAC-SHA256 delivery with retries and dead-letter.</DialogDescription></DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5"><Label htmlFor="webhook-name">Name</Label><Input id="webhook-name" data-testid="webhook-name-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="h-9" /></div>
          <div className="space-y-1.5"><Label htmlFor="webhook-url">URL</Label><Input id="webhook-url" data-testid="webhook-url-input" placeholder="https://your-app.com/hooks" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} className="h-9 font-mono text-[13px]" /></div>
          <div>
            <Label>Subscribed events</Label>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {EVENT_OPTIONS.map((ev) => {
                const on = form.events.includes(ev);
                return <button key={ev} type="button" onClick={() => toggleEvent(ev)} aria-pressed={on} data-testid={`webhook-event-${ev}`}
                  className={`rounded-md border px-2 py-1 font-mono text-[11px] transition-colors ${on ? "border-primary bg-primary text-primary-foreground" : "border-border bg-muted/50 text-muted-foreground hover:text-foreground"}`}>{ev}</button>;
              })}
            </div>
            {preview && (
              <div className="mt-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground" data-testid="pattern-preview">
                <span className="font-medium text-foreground">{preview.matched}</span> of last {preview.scanned} events match this subscription.
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {preview.by_type.map((b) => <span key={b.event_type} className="rounded border border-border bg-card px-1.5 py-0.5 font-mono">{b.event_type} ×{b.count}</span>)}
                  {preview.by_type.length === 0 && <span>No recent matches.</span>}
                </div>
              </div>
            )}
          </div>
        </div>
        <DialogFooter><Button size="sm" onClick={create} data-testid="save-webhook-button">Create</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );

  return (
    <div className="space-y-8">
      {/* Endpoints */}
      <Section title="Endpoints" actions={newEndpoint}>
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          {hooks.length === 0 ? (
            <div className="flex flex-col items-center px-6 py-10 text-center">
              <span className="flex size-10 items-center justify-center rounded-full bg-muted"><Webhook className="size-[18px] text-muted-foreground" aria-hidden="true" /></span>
              <p className="mt-3 text-sm font-medium text-foreground">No endpoints yet</p>
              <p className="mt-1 text-[13px] text-muted-foreground">Add an HTTPS endpoint to receive signed events.</p>
            </div>
          ) : (
            <div className="relative overflow-x-auto">
              <table className="block w-full text-[13px] sm:table">
                <thead className="hidden sm:table-header-group">
                  <tr className="border-b border-border bg-muted/40">
                    <th className={TH}>Endpoint</th>
                    <th className={`${TH} hidden md:table-cell`}>Events</th>
                    <th className={TH}>Enabled</th>
                    <th className={TH}><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody className="block sm:table-row-group">
                  {hooks.map((wh) => (
                    // Below the sm breakpoint a row wraps: the endpoint on one line, its controls on the next.
                    <tr key={wh.id} className={`${ROW} flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 sm:table-row sm:p-0`} data-testid={`webhook-${wh.id}`}>
                      <td className="w-full min-w-0 sm:w-auto sm:max-w-[22rem] sm:px-4 sm:py-2.5">
                        <div className="truncate font-medium text-foreground">{wh.name}</div>
                        <div className="mt-0.5 flex min-w-0">{wh.url ? <code className={`${CODE} truncate`}>{wh.url}</code> : <span className="text-xs text-muted-foreground">No URL set</span>}</div>
                      </td>
                      <td className="hidden px-4 py-2.5 md:table-cell">
                        <div className="flex flex-wrap items-center gap-1">
                          {(wh.events || []).slice(0, 3).map((e) => <code key={e} className={CODE}>{e}</code>)}
                          {(wh.events || []).length > 3 && <span className="text-[11px] text-muted-foreground">+{wh.events.length - 3}</span>}
                        </div>
                      </td>
                      <td className="flex items-center sm:table-cell sm:px-4 sm:py-2.5">
                        <Switch checked={wh.enabled} onCheckedChange={(v) => toggle(wh, v)} aria-label={`Enable ${wh.name}`} data-testid={`webhook-toggle-${wh.id}`} />
                      </td>
                      <td className="ml-auto sm:ml-0 sm:px-4 sm:py-2.5">
                        <div className="flex justify-end gap-1">
                          <Button size="sm" variant="outline" className="h-7" onClick={() => test(wh)} data-testid={`webhook-test-${wh.id}`}><Send aria-hidden="true" />Send test</Button>
                          {isAdmin && <Button size="sm" variant="ghost" className="h-7 px-2 text-muted-foreground sm:px-3" onClick={() => openVerify(wh)} data-testid={`webhook-verify-${wh.id}`}><ShieldCheck aria-hidden="true" /><span className="sr-only sm:not-sr-only">Verify</span></Button>}
                          {isAdmin && <Button size="sm" variant="ghost" className="h-7 px-2 text-muted-foreground sm:px-3" onClick={() => rotate(wh)} data-testid={`webhook-rotate-${wh.id}`}><KeyRound aria-hidden="true" /><span className="sr-only sm:not-sr-only">Rotate</span></Button>}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Section>

      {/* Signature docs dialog */}
      <Dialog open={!!verify} onOpenChange={(o) => !o && setVerify(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>Verify webhook signatures</DialogTitle><DialogDescription>{verify?.name} — payloads are signed with HMAC-SHA256 in the <code className="font-mono">X-ClientVerse-Signature</code> header.</DialogDescription></DialogHeader>
          {verify && (
            <div className="space-y-4" data-testid="webhook-verify-dialog">
              <div>
                <Label htmlFor="webhook-secret" className="text-xs">Signing secret</Label>
                <div className="mt-1 flex gap-2">
                  <Input id="webhook-secret" readOnly value={verify.secret} className="h-9 font-mono text-xs" data-testid="webhook-secret-value" />
                  <Button size="sm" variant="outline" className="h-9" onClick={() => copy(verify.secret, "Secret")} aria-label="Copy signing secret" data-testid="copy-secret-button"><Copy aria-hidden="true" /></Button>
                </div>
              </div>
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <Label className="text-xs">Verification snippet (Node.js)</Label>
                  <Button size="sm" variant="ghost" className="h-7" onClick={() => copy(snippet(verify.secret), "Snippet")} data-testid="copy-snippet-button"><Copy aria-hidden="true" />Copy</Button>
                </div>
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-muted/50 p-4 font-mono text-xs leading-5 text-foreground/90">{snippet(verify.secret)}</pre>
              </div>
              <div className="text-xs leading-5 text-muted-foreground">
                Headers sent with every delivery: <code className="font-mono">X-ClientVerse-Signature</code>, <code className="font-mono">X-ClientVerse-Delivery</code>, <code className="font-mono">X-ClientVerse-Event</code>, <code className="font-mono">X-ClientVerse-Timestamp</code>.
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Delivery log */}
      <Section title="Delivery log">
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="relative overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border bg-muted/40">
                  <th className={`${TH} hidden sm:table-cell`}>Endpoint</th>
                  <th className={TH}>Event</th>
                  <th className={TH}>Status</th>
                  <th className={`${TH_BASE} hidden text-right sm:table-cell`}>Attempts</th>
                  <th className={TH}><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {deliveries.map((d) => (
                  <tr key={d.id} className={ROW} data-testid={`delivery-${d.id}`}>
                    <td className="hidden px-4 py-2.5 text-foreground sm:table-cell">{d.webhook_name}</td>
                    <td className="px-4 py-2.5"><code className="font-mono text-xs text-foreground/80">{d.event_type}</code></td>
                    <td className="px-4 py-2.5">
                      <span className="inline-flex items-center gap-2">
                        <StatusDot tone={DSTATUS[d.status] || "warning"} className="capitalize">{d.status}</StatusDot>
                        {d.dlq && <span className="rounded border border-red-200 bg-red-50 px-1 py-px text-[10.5px] font-medium text-red-700">DLQ</span>}
                      </span>
                    </td>
                    <td className="tabular hidden px-4 py-2.5 text-right text-muted-foreground sm:table-cell">{(d.attempts || []).length}</td>
                    <td className="px-4 py-2.5 text-right">
                      <Button size="sm" variant="ghost" className="h-7 px-2 text-muted-foreground sm:px-3" onClick={() => replay(d)} data-testid={`delivery-replay-${d.id}`}><RotateCw aria-hidden="true" /><span className="sr-only sm:not-sr-only">Replay</span></Button>
                    </td>
                  </tr>
                ))}
                {deliveries.length === 0 && <tr><td colSpan={5} className="px-4 py-10 text-center text-[13px] text-muted-foreground">No deliveries yet. Send a test event or trigger a subscribed event.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </Section>
    </div>
  );
}
