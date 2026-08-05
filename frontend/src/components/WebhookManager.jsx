import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Plus, Send, RotateCw, KeyRound, CheckCircle2, XCircle, Clock, ShieldCheck, Copy } from "lucide-react";

const EVENT_OPTIONS = ["commitment.*", "approval.*", "task.*", "deliverable.*", "mcp.*", "commitment.at_risk", "approval.requested", "task.created", "*"];

const DSTATUS = {
  delivered: "bg-emerald-50 text-emerald-700 border-emerald-200",
  failed: "bg-red-50 text-red-700 border-red-200",
  pending: "bg-amber-50 text-amber-700 border-amber-200",
};

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
  const [hooks, setHooks] = useState([]);
  const [deliveries, setDeliveries] = useState([]);
  const [open, setOpen] = useState(false);
  const [verify, setVerify] = useState(null);
  const [form, setForm] = useState({ name: "", url: "", events: [] });

  const load = async () => {
    const [h, d] = await Promise.all([api.get("/webhooks"), api.get("/webhook-deliveries?limit=60")]);
    setHooks(h.data); setDeliveries(d.data);
  };
  useEffect(() => { load(); }, []);

  const toggle = async (wh, enabled) => { await api.patch(`/webhooks/${wh.id}`, { enabled }); toast.success(enabled ? "Endpoint enabled" : "Endpoint disabled"); load(); };
  const rotate = async (wh) => { const { data } = await api.patch(`/webhooks/${wh.id}`, { rotate_secret: true }); toast.success("Secret rotated"); load(); };
  const test = async (wh) => { const { data } = await api.post(`/webhooks/${wh.id}/test`); toast[data.status === "delivered" ? "success" : "error"](`Test event → ${data.status}`); load(); };
  const replay = async (d) => { const { data } = await api.post(`/webhook-deliveries/${d.id}/replay`); toast[data.status === "delivered" ? "success" : "error"](`Replay → ${data.status}`); load(); };
  const create = async () => {
    if (!form.name || !form.url) return;
    await api.post("/webhooks", form);
    toast.success("Webhook created"); setOpen(false); setForm({ name: "", url: "", events: [] }); load();
  };
  const toggleEvent = (ev) => setForm((f) => ({ ...f, events: f.events.includes(ev) ? f.events.filter((x) => x !== ev) : [...f.events, ev] }));
  const copy = (text, label) => { navigator.clipboard?.writeText(text); toast.success(`${label} copied`); };

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild><Button data-testid="new-webhook-button" className="bg-[#0A0A0A] hover:bg-[#262626]"><Plus className="w-4 h-4 mr-1" />New Endpoint</Button></DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>New Webhook Endpoint</DialogTitle><DialogDescription>Signed HMAC-SHA256 delivery with retries and dead-letter.</DialogDescription></DialogHeader>
            <div className="space-y-4">
              <div><Label>Name</Label><Input data-testid="webhook-name-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="mt-1" /></div>
              <div><Label>URL</Label><Input data-testid="webhook-url-input" placeholder="https://your-app.com/hooks" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} className="mt-1" /></div>
              <div>
                <Label>Subscribed events</Label>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {EVENT_OPTIONS.map((ev) => (
                    <button key={ev} type="button" onClick={() => toggleEvent(ev)} data-testid={`webhook-event-${ev}`}
                      className={`text-[11px] font-mono px-2 py-1 rounded border transition-colors ${form.events.includes(ev) ? "bg-[#0A0A0A] text-white border-black" : "bg-gray-50 text-gray-600 border-gray-200"}`}>{ev}</button>
                  ))}
                </div>
              </div>
            </div>
            <DialogFooter><Button onClick={create} data-testid="save-webhook-button" className="bg-[#0A0A0A] hover:bg-[#262626]">Create</Button></DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Endpoints */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {hooks.map((wh) => (
          <div key={wh.id} className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm" data-testid={`webhook-${wh.id}`}>
            <div className="flex items-start justify-between">
              <div className="min-w-0">
                <div className="font-display font-bold">{wh.name}</div>
                <div className="text-xs text-gray-400 font-mono truncate">{wh.url}</div>
              </div>
              <Switch checked={wh.enabled} onCheckedChange={(v) => toggle(wh, v)} data-testid={`webhook-toggle-${wh.id}`} />
            </div>
            <div className="flex flex-wrap gap-1 mt-2">
              {(wh.events || []).slice(0, 4).map((e) => <span key={e} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-50 border border-gray-200 text-gray-500">{e}</span>)}
              {(wh.events || []).length > 4 && <span className="text-[10px] text-gray-400">+{wh.events.length - 4}</span>}
            </div>
            <div className="flex flex-wrap gap-2 mt-4">
              <Button size="sm" variant="outline" className="h-8" onClick={() => test(wh)} data-testid={`webhook-test-${wh.id}`}><Send className="w-3 h-3 mr-1" />Send test</Button>
              <Button size="sm" variant="outline" className="h-8" onClick={() => setVerify(wh)} data-testid={`webhook-verify-${wh.id}`}><ShieldCheck className="w-3 h-3 mr-1" />Verify</Button>
              <Button size="sm" variant="outline" className="h-8" onClick={() => rotate(wh)} data-testid={`webhook-rotate-${wh.id}`}><KeyRound className="w-3 h-3 mr-1" />Rotate</Button>
            </div>
          </div>
        ))}
      </div>

      {/* Signature docs dialog */}
      <Dialog open={!!verify} onOpenChange={(o) => !o && setVerify(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>Verify webhook signatures</DialogTitle><DialogDescription>{verify?.name} — payloads are signed with HMAC-SHA256 in the <code className="font-mono">X-ClientVerse-Signature</code> header.</DialogDescription></DialogHeader>
          {verify && (
            <div className="space-y-4" data-testid="webhook-verify-dialog">
              <div>
                <Label className="text-xs">Signing secret</Label>
                <div className="flex gap-2 mt-1">
                  <Input readOnly value={verify.secret} className="font-mono text-xs" data-testid="webhook-secret-value" />
                  <Button size="sm" variant="outline" onClick={() => copy(verify.secret, "Secret")} data-testid="copy-secret-button"><Copy className="w-3.5 h-3.5" /></Button>
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <Label className="text-xs">Verification snippet (Node.js)</Label>
                  <Button size="sm" variant="outline" className="h-7" onClick={() => copy(snippet(verify.secret), "Snippet")} data-testid="copy-snippet-button"><Copy className="w-3 h-3 mr-1" />Copy</Button>
                </div>
                <pre className="bg-slate-900 text-slate-100 rounded-lg p-4 text-xs font-mono overflow-auto max-h-72 whitespace-pre-wrap">{snippet(verify.secret)}</pre>
              </div>
              <div className="text-xs text-gray-500">
                Headers sent with every delivery: <code className="font-mono">X-ClientVerse-Signature</code>, <code className="font-mono">X-ClientVerse-Delivery</code>, <code className="font-mono">X-ClientVerse-Event</code>, <code className="font-mono">X-ClientVerse-Timestamp</code>.
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Delivery log */}
      <div>
        <div className="text-xs uppercase tracking-[0.06em] text-gray-500 font-semibold mb-3">Delivery Log</div>
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm text-left">
            <thead><tr className="border-b border-gray-200 text-xs uppercase tracking-[0.05em] text-gray-500">
              <th className="px-5 py-3 font-semibold">Endpoint</th><th className="px-5 py-3 font-semibold">Event</th><th className="px-5 py-3 font-semibold">Status</th><th className="px-5 py-3 font-semibold">Attempts</th><th className="px-5 py-3 font-semibold"></th></tr></thead>
            <tbody>
              {deliveries.map((d) => (
                <tr key={d.id} className="border-b border-gray-100 hover:bg-gray-50" data-testid={`delivery-${d.id}`}>
                  <td className="px-5 py-3">{d.webhook_name}</td>
                  <td className="px-5 py-3 font-mono text-xs">{d.event_type}</td>
                  <td className="px-5 py-3">
                    <Badge className={DSTATUS[d.status] || DSTATUS.pending}>
                      {d.status === "delivered" ? <CheckCircle2 className="w-3 h-3 mr-1" /> : d.status === "failed" ? <XCircle className="w-3 h-3 mr-1" /> : <Clock className="w-3 h-3 mr-1" />}
                      {d.status}{d.dlq ? " · DLQ" : ""}
                    </Badge>
                  </td>
                  <td className="px-5 py-3 text-gray-500">{(d.attempts || []).length}</td>
                  <td className="px-5 py-3">
                    <Button size="sm" variant="outline" className="h-7" onClick={() => replay(d)} data-testid={`delivery-replay-${d.id}`}><RotateCw className="w-3 h-3 mr-1" />Replay</Button>
                  </td>
                </tr>
              ))}
              {deliveries.length === 0 && <tr><td colSpan={5} className="px-5 py-8 text-center text-gray-400">No deliveries yet. Send a test event or trigger a subscribed event.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
