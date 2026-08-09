import { useEffect, useState, useCallback } from "react";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Bell, Mail, Building2, User, Send, AlertTriangle } from "lucide-react";

const TIMEZONES = ["UTC", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "Europe/London", "Europe/Paris", "Europe/Berlin", "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo", "Australia/Sydney"];
const CATEGORIES = [
  { key: "critical", label: "Critical / client health" },
  { key: "commitments", label: "Commitment SLAs" },
  { key: "billing", label: "Billing & invoices" },
  { key: "integrations", label: "Integration health" },
];

function PrefEditor({ prefs, onChange, testidPrefix }) {
  const set = (k, v) => onChange({ ...prefs, [k]: v });
  const setChannel = (k, v) => onChange({ ...prefs, channels: { ...prefs.channels, [k]: v } });
  return (
    <div className="space-y-6">
      <div>
        <div className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-3">Channels</div>
        <div className="space-y-3">
          <Row icon={Bell} label="In-app notifications">
            <Switch data-testid={`${testidPrefix}-channel-in_app`} checked={!!prefs.channels?.in_app} onCheckedChange={(v) => setChannel("in_app", v)} />
          </Row>
          <Row icon={Mail} label="Email notifications">
            <Switch data-testid={`${testidPrefix}-channel-email`} checked={!!prefs.channels?.email} onCheckedChange={(v) => setChannel("email", v)} />
          </Row>
        </div>
      </div>
      <div>
        <div className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-3">Alert categories</div>
        <div className="space-y-3">
          {CATEGORIES.map((c) => (
            <Row key={c.key} label={c.label}>
              <Switch data-testid={`${testidPrefix}-cat-${c.key}`} checked={prefs[c.key] !== false} onCheckedChange={(v) => set(c.key, v)} />
            </Row>
          ))}
        </div>
      </div>
      <div>
        <div className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-3">Daily digest & escalation</div>
        <div className="space-y-4">
          <Row label="Send daily digest">
            <Switch data-testid={`${testidPrefix}-daily_digest`} checked={prefs.daily_digest !== false} onCheckedChange={(v) => set("daily_digest", v)} />
          </Row>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs text-gray-500">Digest hour (local)</Label>
              <Input type="time" data-testid={`${testidPrefix}-digest_time`} value={prefs.digest_time || "08:00"} onChange={(e) => set("digest_time", e.target.value)} className="mt-1" />
            </div>
            <div>
              <Label className="text-xs text-gray-500">Timezone</Label>
              <Select value={prefs.timezone || "UTC"} onValueChange={(v) => set("timezone", v)}>
                <SelectTrigger data-testid={`${testidPrefix}-timezone`} className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>{TIMEZONES.map((tz) => <SelectItem key={tz} value={tz}>{tz}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs text-gray-500">Escalate after (minutes)</Label>
              <Input type="number" min="5" data-testid={`${testidPrefix}-escalation_minutes`} value={prefs.escalation_minutes ?? 60} onChange={(e) => set("escalation_minutes", parseInt(e.target.value || "0", 10))} className="mt-1" />
            </div>
            <div>
              <Label className="text-xs text-gray-500">Max escalation level</Label>
              <Input type="number" min="1" data-testid={`${testidPrefix}-escalation_max_level`} value={prefs.escalation_max_level ?? 3} onChange={(e) => set("escalation_max_level", parseInt(e.target.value || "1", 10))} className="mt-1" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ icon: Icon, label, children }) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2 text-sm text-gray-700">
        {Icon && <Icon className="w-4 h-4 text-gray-400" />} {label}
      </div>
      {children}
    </div>
  );
}

export default function Notifications() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [mine, setMine] = useState(null);
  const [tenant, setTenant] = useState(null);
  const [savingMine, setSavingMine] = useState(false);
  const [savingTenant, setSavingTenant] = useState(false);
  const [digestBusy, setDigestBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/notifications/preferences");
      setData(data);
      setMine({ ...data.effective });
      setTenant({ ...(data.tenant_default || {}) });
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const saveMine = async () => {
    setSavingMine(true);
    try { await api.put("/notifications/preferences/me", { prefs: mine }); toast.success("Your preferences saved"); load(); }
    catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
    finally { setSavingMine(false); }
  };
  const saveTenant = async () => {
    setSavingTenant(true);
    try { await api.put("/notifications/preferences/tenant", { prefs: tenant }); toast.success("Team defaults saved"); load(); }
    catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
    finally { setSavingTenant(false); }
  };
  const runDigest = async () => {
    setDigestBusy(true);
    try { const { data } = await api.post("/digest/run"); toast.success(`Digest ${data.status}${data.recipients ? ` · ${data.recipients} sent` : ""}`); }
    catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
    finally { setDigestBusy(false); }
  };

  if (!data || !mine) return <div className="max-w-3xl space-y-4"><Skeleton className="h-8 w-56" /><Skeleton className="h-64 w-full" /></div>;
  const isAdmin = data.is_admin;

  return (
    <div className="max-w-3xl" data-testid="notifications-page">
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="font-display font-extrabold text-4xl">Notifications</h1>
          <p className="text-gray-500 text-sm mt-1">Control how and when ClientVerse alerts you about client health, SLAs and integrations.</p>
        </div>
        {isAdmin && (
          <Button variant="outline" onClick={runDigest} disabled={digestBusy} data-testid="run-digest-button">
            <Send className="w-4 h-4 mr-2" /> {digestBusy ? "Sending…" : "Send digest now"}
          </Button>
        )}
      </div>

      {!data.email_configured && (
        <div className="mb-6 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800" data-testid="email-not-configured-banner">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          Email delivery isn't configured yet — in-app notifications still work; email alerts will be skipped.
        </div>
      )}

      <Tabs defaultValue="mine">
        <TabsList data-testid="notifications-tabs">
          <TabsTrigger value="mine" data-testid="tab-mine"><User className="w-4 h-4 mr-2" /> My preferences</TabsTrigger>
          {isAdmin && <TabsTrigger value="tenant" data-testid="tab-tenant"><Building2 className="w-4 h-4 mr-2" /> Team defaults</TabsTrigger>}
        </TabsList>
        <TabsContent value="mine">
          <div className="rounded-xl border border-gray-200 bg-white p-6 mt-4">
            <PrefEditor prefs={mine} onChange={setMine} testidPrefix="mine" />
            <div className="mt-6 flex justify-end">
              <Button onClick={saveMine} disabled={savingMine} data-testid="save-mine-button">{savingMine ? "Saving…" : "Save my preferences"}</Button>
            </div>
          </div>
        </TabsContent>
        {isAdmin && (
          <TabsContent value="tenant">
            <div className="rounded-xl border border-gray-200 bg-white p-6 mt-4">
              <p className="text-xs text-gray-400 mb-4">These defaults apply to everyone on your team unless they set their own preferences.</p>
              <PrefEditor prefs={tenant} onChange={setTenant} testidPrefix="tenant" />
              <div className="mt-6 flex justify-end">
                <Button onClick={saveTenant} disabled={savingTenant} data-testid="save-tenant-button">{savingTenant ? "Saving…" : "Save team defaults"}</Button>
              </div>
            </div>
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
