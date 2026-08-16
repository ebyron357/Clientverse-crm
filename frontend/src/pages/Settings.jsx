/* ClientVerse Systems Command Center: a compact settings index that preserves existing navy/cyan hierarchy and routes users to governed controls. */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Badge } from "@/components/AppShell";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Bell, Building2, ChevronRight, CircleUserRound, KeyRound, Link2,
  LogOut, Mail, ShieldCheck, SlidersHorizontal, Users,
} from "lucide-react";

const PROVIDER_LABELS = { gmail: "Gmail", google_calendar: "Google Calendar", stripe: "Stripe" };

function StatusPill({ children, tone = "slate" }) {
  const tones = {
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-700",
    amber: "border-amber-200 bg-amber-50 text-amber-700",
    cyan: "border-cyan-200 bg-cyan-50 text-cyan-700",
    slate: "border-slate-200 bg-slate-50 text-slate-600",
  };
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold ${tones[tone]}`}>{children}</span>;
}

function SettingRow({ icon: Icon, title, detail, action, testid }) {
  return <div className="flex flex-col gap-3 border-t border-slate-100 py-4 first:border-t-0 sm:flex-row sm:items-center sm:justify-between"><div className="flex min-w-0 gap-3"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-cyan-50 text-[#1a9fbf]"><Icon className="h-4 w-4" /></span><div className="min-w-0"><h3 className="text-sm font-semibold text-[#132038]">{title}</h3><p className="mt-1 text-sm leading-5 text-slate-500">{detail}</p></div></div>{action && <div className="shrink-0">{typeof action === "string" ? <StatusPill>{action}</StatusPill> : action?.onClick ? <Button variant="outline" size="sm" data-testid={testid} onClick={action.onClick}>{action.label}<ChevronRight className="ml-1 h-3.5 w-3.5" /></Button> : action}</div>}</div>;
}

export default function Settings() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [prefs, setPrefs] = useState(null);
  const [connections, setConnections] = useState(null);
  const [loadError, setLoadError] = useState(false);

  const load = useCallback(async () => {
    setLoadError(false);
    const [preferenceResponse, connectionResponse] = await Promise.allSettled([
      api.get("/notifications/preferences"),
      api.get("/integrations/connections"),
    ]);
    if (preferenceResponse.status === "fulfilled") setPrefs(preferenceResponse.value.data);
    if (connectionResponse.status === "fulfilled") setConnections(connectionResponse.value.data || []);
    if (preferenceResponse.status === "rejected" || connectionResponse.status === "rejected") setLoadError(true);
  }, []);

  useEffect(() => { load(); }, [load]);

  const isAdmin = user?.role === "admin";
  const providers = useMemo(() => {
    const byProvider = new Map((connections || []).map((connection) => [connection.provider, connection]));
    return Object.keys(PROVIDER_LABELS).map((provider) => ({ provider, label: PROVIDER_LABELS[provider], status: byProvider.get(provider)?.status || "disconnected" }));
  }, [connections]);
  const activeProviders = providers.filter((provider) => provider.status === "active").length;
  const signOut = async () => { await logout(); navigate("/login"); };

  if (!prefs || !connections) return <div className="cv-page" data-testid="settings-loading"><div className="mb-7 space-y-3"><Skeleton className="h-3 w-28" /><Skeleton className="h-9 w-40" /><Skeleton className="h-4 w-[28rem] max-w-full" /></div><div className="grid gap-5 xl:grid-cols-2"><Skeleton className="h-72 rounded-2xl" /><Skeleton className="h-72 rounded-2xl" /></div></div>;

  const emailConfigured = Boolean(prefs.email_configured);
  return <div className="cv-page" data-testid="settings-page"><div className="cv-page-header"><div><div className="cv-eyebrow">Workspace controls</div><h1 className="cv-page-title">Settings</h1><p className="cv-page-description">Review your account and operating configuration, then use the purpose-built controls for preferences, access, and connected providers.</p></div><Button variant="outline" onClick={load} data-testid="settings-refresh"><SlidersHorizontal className="mr-1.5 h-4 w-4" />Refresh status</Button></div>{loadError && <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800" role="status">Some status information could not be refreshed. Existing settings controls remain available.</div>}<div className="grid gap-5 xl:grid-cols-2"><section className="cv-card p-5 sm:p-6" data-testid="settings-profile-card"><div className="mb-5 flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#0a1628] text-white"><CircleUserRound className="h-5 w-5" /></span><div><h2 className="cv-card-title">Profile & account</h2><p className="cv-card-description">Authenticated identity and account role.</p></div></div><dl className="grid gap-4 text-sm"><div className="flex items-center justify-between gap-4"><dt className="text-slate-500">Name</dt><dd className="truncate font-medium text-[#132038]">{user?.name || "Current user"}</dd></div><div className="flex items-center justify-between gap-4"><dt className="text-slate-500">Email</dt><dd className="truncate font-medium text-[#132038]">{user?.email || "Not available"}</dd></div><div className="flex items-center justify-between gap-4"><dt className="text-slate-500">Access level</dt><dd><Badge className={isAdmin ? "border-cyan-200 bg-cyan-50 text-cyan-700" : "border-slate-200 bg-slate-50 text-slate-600"}>{isAdmin ? "Workspace admin" : "Team member"}</Badge></dd></div></dl><div className="mt-5 border-t border-slate-100 pt-4"><SettingRow icon={KeyRound} title="Session security" detail="End this browser session when you are finished. Profile and password edits are not exposed by the current CRM API." action={{ label: "Sign out", onClick: signOut }} testid="settings-signout" /></div></section><section className="cv-card p-5 sm:p-6" data-testid="settings-notifications-card"><div className="mb-5 flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-50 text-[#1a9fbf]"><Bell className="h-5 w-5" /></span><div><h2 className="cv-card-title">Notification preferences</h2><p className="cv-card-description">Personal alerts are configurable for every authenticated user.</p></div></div><SettingRow icon={Bell} title="In-app alerts" detail={prefs.effective?.channels?.in_app ? "Enabled for your effective preference set." : "Disabled for your effective preference set."} action={prefs.effective?.channels?.in_app ? <StatusPill tone="emerald">Enabled</StatusPill> : <StatusPill>Disabled</StatusPill>} /><SettingRow icon={Mail} title="Email delivery" detail={emailConfigured ? "Email delivery is configured for this environment; preferences are managed in Action Center." : "Email delivery is not configured; in-app alerts remain available."} action={emailConfigured ? <StatusPill tone="emerald">Configured</StatusPill> : <StatusPill tone="amber">Not configured</StatusPill>} /><div className="mt-5 flex justify-end"><Button className="cv-action-primary" onClick={() => navigate("/notifications")} data-testid="settings-notifications-link">Manage notification preferences<ChevronRight className="ml-1.5 h-4 w-4" /></Button></div></section><section className="cv-card p-5 sm:p-6" data-testid="settings-integrations-card"><div className="mb-5 flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-50 text-[#1a9fbf]"><Link2 className="h-5 w-5" /></span><div><h2 className="cv-card-title">Connected providers</h2><p className="cv-card-description">Only safe provider status is shown here. Credentials and tokens are never displayed.</p></div></div><div className="space-y-3">{providers.map((provider) => { const active = provider.status === "active"; return <div key={provider.provider} className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50/70 px-4 py-3"><span className="text-sm font-medium text-[#132038]">{provider.label}</span><StatusPill tone={active ? "emerald" : provider.status === "degraded" ? "amber" : "slate"}>{active ? "Connected" : provider.status === "degraded" ? "Needs attention" : "Not connected"}</StatusPill></div>; })}</div><p className="mt-4 text-xs leading-5 text-slate-500">{isAdmin ? `${activeProviders} of ${providers.length} providers are connected. Connection and sync actions are available in Registries.` : "Connection and sync actions are restricted to workspace admins."}</p><div className="mt-5 flex justify-end"><Button variant="outline" onClick={() => navigate("/registries")} data-testid="settings-integrations-link">View integrations<ChevronRight className="ml-1 h-3.5 w-3.5" /></Button></div></section><section className="cv-card p-5 sm:p-6" data-testid="settings-organization-card"><div className="mb-5 flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-50 text-[#1a9fbf]"><Building2 className="h-5 w-5" /></span><div><h2 className="cv-card-title">Organization & access</h2><p className="cv-card-description">Membership and governance remain in their dedicated, server-protected workflow.</p></div></div>{isAdmin ? <SettingRow icon={Users} title="Team & invitations" detail="Manage membership, roles, account status, and invitations using the protected Team & Access screen." action={{ label: "Open Team & Access", onClick: () => navigate("/team") }} testid="settings-team-link" /> : <SettingRow icon={ShieldCheck} title="Workspace governance" detail="Team membership, invitations, provider connections, and tenant defaults are managed by a workspace admin." action={<StatusPill tone="cyan">Admin managed</StatusPill>} />}<SettingRow icon={ShieldCheck} title="Operational evidence" detail="Review current notifications, integration state, and audit activity in their existing purpose-built screens." action={{ label: "Open audit", onClick: () => navigate("/audit") }} testid="settings-audit-link" /></section></div></div>;
}
