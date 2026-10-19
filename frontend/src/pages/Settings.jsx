/* Settings → General. The Settings menu (SettingsLayout) sits on the left; here a sticky row
   of section links over one card per section, each setting a row (label and one muted line,
   control on the right). */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ChangePasswordDialog } from "@/components/ChangePassword";
import { Avatar, PageHeader, Section, StatusDot } from "@/components/page/Page";
import {
  AlertTriangle, Bell, Building2, Calendar, ChevronRight, CircleUserRound, CreditCard, KeyRound,
  Link2, LogOut, Mail, RefreshCw, Settings as SettingsIcon,
} from "lucide-react";

const PROVIDER_LABELS = { gmail: "Gmail", google_calendar: "Google Calendar", stripe: "Stripe" };
const PROVIDER_META = {
  gmail: { icon: Mail, detail: "Read-only messages matched to CRM contacts" },
  google_calendar: { icon: Calendar, detail: "Upcoming client meetings with attendee matching" },
  stripe: { icon: CreditCard, detail: "Read-only customers, invoices and subscriptions" },
};
const SECTIONS = [
  { id: "profile", label: "Profile", icon: CircleUserRound },
  { id: "security", label: "Security", icon: KeyRound },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "integrations", label: "Integrations", icon: Link2 },
  { id: "organization", label: "Organization", icon: Building2 },
];
const sectionId = (id) => `settings-${id}`;

/** One setting: label and a muted line on the left, the control on the right. */
function SettingRow({ label, detail, children, htmlFor, testid }) {
  const Label = htmlFor ? "label" : "div";
  return <div className="flex flex-col gap-2.5 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:gap-6" data-testid={testid}>
    <div className="min-w-0">
      <Label htmlFor={htmlFor} className="block text-[13px] font-medium text-foreground">{label}</Label>
      {detail && <p className="mt-0.5 text-[12.5px] leading-5 text-muted-foreground">{detail}</p>}
    </div>
    {children && <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">{children}</div>}
  </div>;
}

function SettingsCard({ id, title, description, footer, children, testid }) {
  return <Section card title={title} description={description} testid={testid} className="scroll-mt-32 overflow-hidden" bodyClassName="divide-y divide-border/70">
    <span id={sectionId(id)} hidden />
    {children}
    {footer && <div className="flex flex-col items-start gap-2.5 border-t border-border bg-muted/30 px-4 py-2.5 sm:flex-row sm:items-center sm:justify-between">{footer}</div>}
  </Section>;
}

function FooterNote({ children }) {
  return <p className="text-[12.5px] leading-5 text-muted-foreground">{children}</p>;
}

// A row of the page's sections that stays under the top bar while the cards scroll.
function SettingsNav({ active, onSelect }) {
  return <nav aria-label="General sections" className="sticky top-[60px] z-10 -mx-4 overflow-x-auto bg-canvas/95 px-4 py-2 backdrop-blur lg:mx-0 lg:px-0">
    <ul className="flex gap-1">
      {SECTIONS.map(({ id, label, icon: Icon }) => {
        const current = active === id;
        return <li key={id} className="shrink-0">
          <a href={`#${sectionId(id)}`} onClick={(event) => { event.preventDefault(); onSelect(id); }} aria-current={current ? "true" : undefined}
            className={`flex h-8 items-center gap-2 rounded-md px-2.5 text-[13px] transition-colors ${current ? "bg-card font-semibold text-foreground shadow-xs ring-1 ring-border" : "text-muted-foreground hover:bg-card/70 hover:text-foreground"}`}>
            <Icon className="size-4 shrink-0" aria-hidden="true" />{label}
          </a>
        </li>;
      })}
    </ul>
  </nav>;
}

// The business name invitations show ("Join Parker Homes"). Sign-up names it after the
// first person ("Jasmine Parker's Org"); an admin renames it here.
function BusinessName({ isAdmin }) {
  const [name, setName] = useState(null);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  useEffect(() => { api.get("/organization").then(({ data }) => { setName(data.name); setDraft(data.name); }).catch(() => setName("")); }, []);
  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      const { data } = await api.patch("/organization", { name: draft });
      setName(data.name); setDraft(data.name); setEditing(false);
      toast.success("Business name saved.");
    } catch (error) { toast.error(formatErr(error.response?.data?.detail)); }
    finally { setSaving(false); }
  };
  const detail = "Shown on invitations, e.g. “Join Parker Homes”.";
  if (editing) {
    return <form onSubmit={save} data-testid="business-name-form">
      <SettingRow label="Business name" detail={detail} htmlFor="business-name">
        <Input id="business-name" value={draft} maxLength={80} onChange={(event) => setDraft(event.target.value)} className="h-8 w-full text-[13px] sm:w-56" data-testid="business-name-input" />
        <Button type="submit" size="sm" disabled={saving || !draft.trim()} data-testid="business-name-save">{saving ? "Saving…" : "Save"}</Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => { setDraft(name || ""); setEditing(false); }}>Cancel</Button>
      </SettingRow>
    </form>;
  }
  return <SettingRow label="Business name" detail={detail}>
    <span className="max-w-[16rem] truncate text-[13px] font-medium text-foreground">{name === null ? "Loading…" : name || <span className="text-muted-foreground">Not set</span>}</span>
    {isAdmin && <Button variant="outline" size="sm" onClick={() => setEditing(true)} data-testid="business-name-edit">Rename</Button>}
  </SettingRow>;
}

function LinkButton({ children, onClick, testid }) {
  return <Button variant="outline" size="sm" onClick={onClick} data-testid={testid}>{children}<ChevronRight className="-mr-1 text-muted-foreground" aria-hidden="true" /></Button>;
}

export default function Settings() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [prefs, setPrefs] = useState(null);
  const [connections, setConnections] = useState(null);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [active, setActive] = useState(SECTIONS[0].id);

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

  const ready = Boolean(prefs && connections);
  // Highlight the section being read as the page scrolls: the last card whose top has passed
  // the sticky top bar and section row, or the last card once the page cannot scroll any
  // further. A click on the row pins its choice while the smooth scroll runs.
  const pinnedUntil = useRef(0);
  useEffect(() => {
    if (!ready) return undefined;
    let frame = 0;
    const update = () => {
      frame = 0;
      if (Date.now() < pinnedUntil.current) return;
      const cards = SECTIONS.map(({ id }) => ({ id, card: document.getElementById(sectionId(id))?.closest("section") })).filter((entry) => entry.card);
      if (!cards.length) return;
      const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4;
      let current = cards[0].id;
      cards.forEach(({ id, card }) => { if (card.getBoundingClientRect().top <= 140) current = id; });
      setActive(atBottom && window.scrollY > 0 ? cards[cards.length - 1].id : current);
    };
    const onScroll = () => { if (!frame) frame = window.requestAnimationFrame(update); };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => { window.removeEventListener("scroll", onScroll); if (frame) window.cancelAnimationFrame(frame); };
  }, [ready]);

  const selectSection = (id) => {
    setActive(id);
    pinnedUntil.current = Date.now() + 900;
    document.getElementById(sectionId(id))?.closest("section")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const isAdmin = user?.role === "admin";
  const providers = useMemo(() => {
    const byProvider = new Map((connections || []).map((connection) => [connection.provider, connection]));
    return Object.keys(PROVIDER_LABELS).map((provider) => ({ provider, label: PROVIDER_LABELS[provider], status: byProvider.get(provider)?.status || "disconnected" }));
  }, [connections]);
  const activeProviders = providers.filter((provider) => provider.status === "active").length;
  const statusLabel = (status) => ({
    active: "Connected",
    degraded: "Needs attention",
    expired: "Needs auth",
    revoked: "Needs auth",
    error: "Error",
    connecting: "Connecting…",
    disconnected: "Not connected",
  }[status] || status);
  const statusTone = (status) => ({
    active: "success",
    degraded: "warning",
    expired: "warning",
    revoked: "warning",
    error: "danger",
    connecting: "info",
    disconnected: "neutral",
  }[status] || "neutral");
  const signOut = async () => { await logout(); navigate("/login"); };

  if (!ready) return <div className="cv-page" data-testid="settings-loading">
    <div className="mb-5 space-y-2"><Skeleton className="h-7 w-32" /><Skeleton className="h-4 w-72 max-w-full" /></div>
    <div className="max-w-3xl space-y-5">
      <div className="flex gap-1">{SECTIONS.map(({ id }) => <Skeleton key={id} className="h-8 w-24 rounded-md" />)}</div>
      <Skeleton className="h-56 rounded-xl" /><Skeleton className="h-40 rounded-xl" />
    </div>
  </div>;

  const emailConfigured = Boolean(prefs.email_configured);
  const inApp = Boolean(prefs.effective?.channels?.in_app);
  return <div className="cv-page" data-testid="settings-page">
    <PageHeader icon={SettingsIcon} title="General" description="Your account, security, notifications, connected providers and organization."
      actions={<Button variant="outline" size="sm" onClick={load} data-testid="settings-refresh"><RefreshCw aria-hidden="true" />Refresh</Button>} />

    <div className="max-w-3xl">
      <SettingsNav active={active} onSelect={selectSection} />

      <div className="mt-3 space-y-5">
        {loadError && <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800" role="status">
          <AlertTriangle className="size-4 shrink-0" aria-hidden="true" />Some status information could not be refreshed. Settings controls remain available.
        </div>}

        <SettingsCard id="profile" title="Profile" description="Your signed-in identity and role." testid="settings-profile-card">
          <SettingRow label="Name"><span className="flex min-w-0 items-center gap-2 text-[13px] font-medium text-foreground"><Avatar name={user?.name || user?.email || ""} size="sm" /><span className="truncate">{user?.name || "Current user"}</span></span></SettingRow>
          <SettingRow label="Email"><span className="truncate text-[13px] text-foreground">{user?.email || "Not available"}</span></SettingRow>
          <SettingRow label="Access level" detail={isAdmin ? "Can invite people, change roles and manage settings." : "Uses the CRM day to day. A workspace admin manages access."}>
            <StatusDot tone={isAdmin ? "brand" : "neutral"}>{isAdmin ? "Workspace admin" : "Team member"}</StatusDot>
          </SettingRow>
        </SettingsCard>

        <SettingsCard id="security" title="Security" description="Password and this browser session." testid="settings-security-card">
          <SettingRow label="Password" detail="Change your password, e.g. to replace a temporary one. Other devices are signed out.">
            <Button variant="outline" size="sm" onClick={() => setPasswordOpen(true)} data-testid="settings-change-password"><KeyRound aria-hidden="true" />Change password</Button>
          </SettingRow>
          <SettingRow label="Session" detail="End this browser session when you are finished.">
            <Button variant="outline" size="sm" onClick={signOut} data-testid="settings-signout"><LogOut aria-hidden="true" />Sign out</Button>
          </SettingRow>
          <ChangePasswordDialog open={passwordOpen} onOpenChange={setPasswordOpen} />
        </SettingsCard>

        <SettingsCard id="notifications" title="Notifications" description="Your effective alert channels." testid="settings-notifications-card"
          footer={<><FooterNote>Channels, categories and the daily digest are managed in Action Center.</FooterNote><LinkButton onClick={() => navigate("/notifications")} testid="settings-notifications-link">Manage preferences</LinkButton></>}>
          <SettingRow label="In-app alerts" detail={inApp ? "Enabled for your effective preference set." : "Disabled for your effective preference set."}>
            <StatusDot tone={inApp ? "success" : "neutral"}>{inApp ? "Enabled" : "Disabled"}</StatusDot>
          </SettingRow>
          <SettingRow label="Email delivery" detail={emailConfigured ? "Configured for this environment." : "Not configured; in-app alerts remain available."}>
            <StatusDot tone={emailConfigured ? "success" : "warning"}>{emailConfigured ? "Configured" : "Not configured"}</StatusDot>
          </SettingRow>
        </SettingsCard>

        <SettingsCard id="integrations" title="Integrations" description="Connection status only. Credentials and tokens are never displayed." testid="settings-integrations-card"
          footer={<><FooterNote>{isAdmin ? `${activeProviders} of ${providers.length} connected. Labels reflect API connection state, not live Google/Stripe certification.` : "Connection and sync actions are restricted to workspace admins. Labels reflect API connection state only."}</FooterNote><LinkButton onClick={() => navigate("/registries")} testid="settings-integrations-link">View integrations</LinkButton></>}>
          <div className="divide-y divide-border/70" data-testid="settings-provider-status-list">
            {providers.map((provider) => {
              const meta = PROVIDER_META[provider.provider];
              const Icon = meta.icon;
              return <div key={provider.provider} className="flex items-center gap-3 px-4 py-3" data-testid={`settings-provider-${provider.provider}`}>
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-muted text-foreground/80"><Icon className="size-4" aria-hidden="true" /></span>
                <div className="min-w-0 flex-1">
                  <div className="text-[13px] font-medium text-foreground">{provider.label}</div>
                  <div className="truncate text-[12.5px] text-muted-foreground">{meta.detail}</div>
                </div>
                <StatusDot tone={statusTone(provider.status)} className="hidden sm:inline-flex">{statusLabel(provider.status)}</StatusDot>
                <StatusDot tone={statusTone(provider.status)} className="sm:hidden"><span className="sr-only">{statusLabel(provider.status)}</span></StatusDot>
                {isAdmin && <Button variant="outline" size="sm" className="ml-1" onClick={() => navigate("/registries")} aria-label={`${provider.status === "disconnected" ? "Connect" : "Manage"} ${provider.label}`}>{provider.status === "disconnected" ? "Connect" : "Manage"}</Button>}
              </div>;
            })}
          </div>
        </SettingsCard>

        <SettingsCard id="organization" title="Organization" description="Your business name, your team and the audit trail." testid="settings-organization-card">
          <BusinessName isAdmin={isAdmin} />
          {isAdmin
            ? <SettingRow label="Team & invitations" detail="Membership, roles, account status and invitations.">
              <LinkButton onClick={() => navigate("/team")} testid="settings-team-link">Open Team & Access</LinkButton>
            </SettingRow>
            : <SettingRow label="Workspace governance" detail="Team, invitations, provider connections and defaults are managed by a workspace admin.">
              <StatusDot tone="brand">Admin managed</StatusDot>
            </SettingRow>}
          <SettingRow label="Operational evidence" detail="Notifications, integration state and audit activity.">
            <LinkButton onClick={() => navigate("/audit")} testid="settings-audit-link">Open audit</LinkButton>
          </SettingRow>
        </SettingsCard>
      </div>
    </div>
  </div>;
}
