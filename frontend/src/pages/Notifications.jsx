/* Action Center: the open client risks first, then an inbox of recent alert activity grouped
   by day. Preferences (yours, and the team defaults for admins) are separate views. */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader, Section, StatusDot, ViewTabs } from "@/components/page/Page";
import {
  AlertTriangle, Bell, Building2, Check, CheckCheck, CircleAlert, Clock3, Inbox, ListTodo,
  RefreshCw, Send, ShieldAlert, User, UserPlus,
} from "lucide-react";

const TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Asia/Kolkata",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
];
const CATEGORIES = [
  { key: "critical", label: "Critical / client health" },
  { key: "commitments", label: "Commitment SLAs" },
  { key: "billing", label: "Billing & invoices" },
  { key: "integrations", label: "Integration health" },
];
// Categories the feed can be filtered by. Leads and tasks have no preference switch of their
// own -- the server's preferences only know the four alert categories above -- so they are
// filters here, not toggles in the preference editor.
const FEED_CATEGORIES = [
  { key: "leads", label: "Leads" },
  { key: "tasks", label: "Tasks" },
  { key: "critical", label: "Critical" },
  { key: "commitments", label: "Commitments" },
  { key: "billing", label: "Billing" },
  { key: "integrations", label: "Integrations" },
];
const CATEGORY_META = {
  critical: { label: "Needs attention", icon: CircleAlert, tile: "bg-red-50 text-red-700" },
  commitments: { label: "Commitment", icon: ShieldAlert, tile: "bg-amber-50 text-amber-700" },
  billing: { label: "Billing", icon: Clock3, tile: "bg-violet-50 text-violet-700" },
  integrations: { label: "Integration", icon: RefreshCw, tile: "bg-brand-soft text-brand" },
  leads: { label: "Lead", icon: UserPlus, tile: "bg-emerald-50 text-emerald-700" },
  tasks: { label: "Task", icon: ListTodo, tile: "bg-brand-soft text-brand" },
  system: { label: "System", icon: Bell, tile: "bg-muted text-muted-foreground" },
};
const SEVERITY_TONE = { critical: "danger", high: "danger", warning: "warning", medium: "warning", info: "info", low: "neutral" };
const OPEN_LABEL = { leads: "Open lead", tasks: "Open task" };
const feedKey = (notification) => notification.category || notification.kind || "system";

function dayLabel(date) {
  const today = new Date();
  const startOf = (value) => new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
  const days = Math.round((startOf(today) - startOf(date)) / 86400000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  return date.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric", ...(date.getFullYear() !== today.getFullYear() ? { year: "numeric" } : {}) });
}
const timeLabel = (date) => date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });

function groupByDay(notifications) {
  const groups = [];
  notifications.forEach((notification) => {
    const date = notification.created_at ? new Date(notification.created_at) : null;
    const label = date && !Number.isNaN(date.getTime()) ? dayLabel(date) : "Earlier";
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.items.push(notification);
    else groups.push({ label, items: [notification] });
  });
  return groups;
}

function CountChip({ children }) {
  return <span className="tabular rounded-md bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground">{children}</span>;
}

function EmptyBlock({ icon: Icon, title, children }) {
  return <div className="flex flex-col items-center px-6 py-10 text-center">
    <span className="flex size-10 items-center justify-center rounded-full bg-muted"><Icon className="size-[18px] text-muted-foreground" aria-hidden="true" /></span>
    <h3 className="mt-3 text-sm font-medium text-foreground">{title}</h3>
    <p className="mt-1 max-w-sm text-[13px] leading-5 text-muted-foreground">{children}</p>
  </div>;
}

export default function Notifications() {
  const [data, setData] = useState(null);
  const [feed, setFeed] = useState([]);
  const [actionItems, setActionItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [mine, setMine] = useState(null);
  const [tenant, setTenant] = useState(null);
  const [savingMine, setSavingMine] = useState(false);
  const [savingTenant, setSavingTenant] = useState(false);
  const [digestBusy, setDigestBusy] = useState(false);
  const [feedFilter, setFeedFilter] = useState("all");
  const [feedBusy, setFeedBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState(null);
  const [view, setView] = useState("inbox");
  const load = useCallback(async () => {
    const [preferences, notifications] = await Promise.allSettled([api.get("/notifications/preferences"), api.get("/notifications")]);
    if (preferences.status === "fulfilled") {
      setData(preferences.value.data);
      setMine({ ...preferences.value.data.effective });
      setTenant({ ...(preferences.value.data.tenant_default || {}) });
    } else toast.error("Could not load notification preferences");
    if (notifications.status === "fulfilled") {
      setFeed(notifications.value.data.notifications || []);
      setActionItems(notifications.value.data.action_items || []);
      setUnread(notifications.value.data.unread || 0);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  const saveMine = async () => {
    setSavingMine(true);
    try {
      await api.put("/notifications/preferences/me", { prefs: mine });
      toast.success("Your notification preferences were saved");
      load();
    } catch (error) {
      toast.error(formatErr(error.response?.data?.detail));
    } finally {
      setSavingMine(false);
    }
  };
  const saveTenant = async () => {
    setSavingTenant(true);
    try {
      await api.put("/notifications/preferences/tenant", { prefs: tenant });
      toast.success("Team notification defaults were saved");
      load();
    } catch (error) {
      toast.error(formatErr(error.response?.data?.detail));
    } finally {
      setSavingTenant(false);
    }
  };
  const runDigest = async () => {
    setDigestBusy(true);
    try {
      const { data: result } = await api.post("/digest/run");
      toast.success(`Digest ${result.status}${result.recipients ? ` · ${result.recipients} sent` : ""}`);
    } catch (error) {
      toast.error(formatErr(error.response?.data?.detail));
    } finally {
      setDigestBusy(false);
    }
  };
  const markRead = async (id) => {
    try {
      await api.post(`/notifications/${id}/read`);
      setFeed((current) => current.map((notification) => (notification.id === id ? { ...notification, read: true } : notification)));
      setUnread((current) => Math.max(0, current - 1));
    } catch {
      toast.error("Could not update this notification");
    }
  };
  const markAllRead = async () => {
    setFeedBusy(true);
    try {
      await api.post("/notifications/read-all");
      setFeed((current) => current.map((notification) => ({ ...notification, read: true })));
      setUnread(0);
      toast.success("All notifications marked as read");
    } catch {
      toast.error("Could not mark all notifications as read");
    } finally {
      setFeedBusy(false);
    }
  };
  const updateAlert = async (alertId, action) => {
    setActionBusy(`${alertId}:${action}`);
    try {
      await api.post(`/alerts/${alertId}/${action}`);
      toast.success(action === "acknowledge" ? "Alert acknowledged" : "Alert resolved");
      await load();
    } catch (error) {
      toast.error(formatErr(error.response?.data?.detail) || "Could not update this alert");
    } finally {
      setActionBusy(null);
    }
  };
  const visibleFeed = useMemo(
    () => feed.filter((notification) => feedFilter === "all" || feedKey(notification) === feedFilter),
    [feed, feedFilter],
  );
  const feedCounts = useMemo(() => feed.reduce((counts, notification) => {
    const key = feedKey(notification);
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {}), [feed]);
  const groups = useMemo(() => groupByDay(visibleFeed), [visibleFeed]);

  if (!data || !mine)
    return (
      <div className="cv-page">
        <div className="mb-5 space-y-2"><Skeleton className="h-7 w-44" /><Skeleton className="h-4 w-96 max-w-full" /></div>
        <Skeleton className="mb-5 h-9 w-full rounded-none" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  const isAdmin = data.is_admin;
  const viewItems = [
    { value: "inbox", label: "Inbox", icon: Inbox, count: actionItems.length > 0 ? actionItems.length : undefined, testid: "tab-inbox" },
    { value: "mine", label: "My preferences", icon: User, testid: "tab-mine" },
    ...(isAdmin ? [{ value: "tenant", label: "Team defaults", icon: Building2, testid: "tab-tenant" }] : []),
  ];
  const filterItems = [
    { value: "all", label: "All", count: feed.length },
    ...FEED_CATEGORIES.map((category) => ({ value: category.key, label: category.label, count: feedCounts[category.key] || undefined })),
  ];
  return (
    <div className="cv-page" data-testid="notifications-page">
      <PageHeader
        icon={Bell}
        title="Action Center"
        description="Resolve the client risks that matter first, then review recent alert activity."
        actions={<>
          {isAdmin && (
            <Button variant="outline" size="sm" onClick={runDigest} disabled={digestBusy} data-testid="run-digest-button">
              <Send aria-hidden="true" />
              {digestBusy ? "Sending…" : "Send digest"}
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw aria-hidden="true" />
            Refresh
          </Button>
        </>}
      />
      {!data.email_configured && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] leading-5 text-amber-800" data-testid="email-not-configured-banner">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span><strong className="font-medium">Email delivery is not configured.</strong> In-app notifications remain available; email alerts are skipped until a delivery provider is configured.</span>
        </div>
      )}
      <div data-testid="notifications-tabs">
        <ViewTabs items={viewItems} value={view} onChange={setView} label="Action Center views" />
      </div>

      {view === "inbox" && (
        <div className="mt-5 space-y-6">
          <Section title={<span className="flex items-center gap-2">Needs action{actionItems.length > 0 && <CountChip>{actionItems.length}</CountChip>}</span>}>
            <div className="overflow-hidden rounded-xl border border-border bg-card">
              {actionItems.length ? (
                <div className="divide-y divide-border/70">
                  {actionItems.map((item) => (
                    <ActionItemRow
                      key={item.alert_id}
                      item={item}
                      busy={actionBusy?.startsWith(`${item.alert_id}:`)}
                      onAcknowledge={() => updateAlert(item.alert_id, "acknowledge")}
                      onResolve={() => updateAlert(item.alert_id, "resolve")}
                    />
                  ))}
                </div>
              ) : (
                <div className="flex items-center gap-3 px-4 py-3.5">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted"><CheckCheck className="size-4 text-muted-foreground" aria-hidden="true" /></span>
                  <div className="min-w-0">
                    <h3 className="text-[13px] font-medium text-foreground">No open action items</h3>
                    <p className="text-[12.5px] leading-5 text-muted-foreground">Client risks, due commitments, billing issues and integration failures appear here only when follow-through is needed.</p>
                  </div>
                </div>
              )}
            </div>
          </Section>

          <Section
            title={<span className="flex items-center gap-2">Recent activity{unread > 0 && <span className="text-xs font-normal text-muted-foreground">{unread} unread</span>}</span>}
            actions={unread > 0 && (
              <Button variant="ghost" size="sm" className="h-7 text-muted-foreground" disabled={feedBusy} onClick={markAllRead}>
                <CheckCheck aria-hidden="true" />
                Mark all read
              </Button>
            )}
          >
            <div className="overflow-hidden rounded-xl border border-border bg-card">
              <ViewTabs items={filterItems} value={feedFilter} onChange={setFeedFilter} label="Filter notification category" className="px-4" />
              {visibleFeed.length ? (
                groups.map((group, index) => (
                  <div key={group.label}>
                    <div className={`border-b border-border/70 bg-muted/30 px-4 py-1.5 text-xs font-medium text-muted-foreground ${index > 0 ? "border-t" : ""}`}>{group.label}</div>
                    <div className="divide-y divide-border/70">
                      {group.items.map((notification) => (
                        <NotificationRow key={notification.id} notification={notification} onRead={() => markRead(notification.id)} />
                      ))}
                    </div>
                  </div>
                ))
              ) : (
                <EmptyBlock icon={Bell} title={feedFilter === "all" ? "Your recent activity is clear" : "Nothing in this category"}>
                  New meaningful alert transitions will appear here when they occur.
                </EmptyBlock>
              )}
            </div>
          </Section>
        </div>
      )}

      {view === "mine" && (
        <PreferenceCard
          title="Your delivery preferences"
          description="Choose the channels and categories that should interrupt your work."
          note="Applies to you only."
          footer={<Button size="sm" onClick={saveMine} disabled={savingMine} data-testid="save-mine-button">{savingMine ? "Saving…" : "Save my preferences"}</Button>}
        >
          <PrefEditor prefs={mine} onChange={setMine} testidPrefix="mine" emailConfigured={data.email_configured} />
        </PreferenceCard>
      )}
      {isAdmin && view === "tenant" && (
        <PreferenceCard
          title="Team notification defaults"
          description="These defaults apply to team members unless they choose personal preferences."
          note="Members with their own preferences keep them."
          footer={<Button size="sm" onClick={saveTenant} disabled={savingTenant} data-testid="save-tenant-button">{savingTenant ? "Saving…" : "Save team defaults"}</Button>}
        >
          <PrefEditor prefs={tenant} onChange={setTenant} testidPrefix="tenant" emailConfigured={data.email_configured} />
        </PreferenceCard>
      )}
    </div>
  );
}

function ActionItemRow({ item, busy, onAcknowledge, onResolve }) {
  const meta = CATEGORY_META[item.category] || CATEGORY_META.system;
  const Icon = meta.icon;
  const occurred = item.last_seen_at ? new Date(item.last_seen_at).toLocaleString() : "Recent";
  return (
    <article className="cv-data-row flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center">
      <div className="flex min-w-0 flex-1 gap-3">
        <span className={`mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md ${meta.tile}`}>
          <Icon className="size-3.5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h3 className="text-[13px] font-medium text-foreground">{item.summary || "Client action required"}</h3>
            <StatusDot tone={SEVERITY_TONE[item.severity] || "warning"} className="text-xs capitalize">{item.severity || "attention"}</StatusDot>
            {item.status === "acknowledged" && <StatusDot tone="neutral" className="text-xs">Acknowledged</StatusDot>}
          </div>
          <p className="mt-0.5 text-[12.5px] leading-5 text-muted-foreground">
            {item.workspace_name ? `${item.workspace_name} · ` : ""}
            {item.occurrence_count > 1 ? `Repeated ${item.occurrence_count} times · ` : ""}Last seen {occurred}
            {item.acknowledged_by ? ` · Acknowledged by ${item.acknowledged_by}` : ""}
          </p>
        </div>
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-1.5 pl-10 sm:justify-end sm:pl-0">
        <Button asChild variant="ghost" size="sm" className="h-7 text-brand hover:text-brand">
          <a href={item.deep_link}>Open client</a>
        </Button>
        {item.status === "open" && (
          <Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={onAcknowledge}>
            Acknowledge
          </Button>
        )}
        <Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={onResolve}>
          <Check aria-hidden="true" />
          {busy ? "Saving…" : "Resolve"}
        </Button>
      </div>
    </article>
  );
}

function NotificationRow({ notification, onRead }) {
  const key = feedKey(notification);
  const meta = CATEGORY_META[key] || CATEGORY_META.system;
  const Icon = meta.icon;
  const title = notification.title || notification.subject || notification.event_type || "ClientVerse update";
  const body = notification.body || notification.message || notification.detail || "A client operations event needs review.";
  const date = notification.created_at ? new Date(notification.created_at) : null;
  const unread = !notification.read;
  return (
    <article className="group flex flex-wrap items-start gap-x-3 px-4 py-2.5 transition-colors hover:bg-muted/40 sm:flex-nowrap sm:items-center">
      <span className={`mt-2 size-1.5 shrink-0 rounded-full sm:mt-0 ${unread ? "bg-brand" : "bg-transparent"}`} aria-hidden="true" />
      <span className={`flex size-7 shrink-0 items-center justify-center rounded-md ${meta.tile}`}>
        <Icon className="size-3.5" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <h3 className={`truncate text-[13px] ${unread ? "font-medium text-foreground" : "text-foreground/80"}`}>
          {unread && <span className="sr-only">Unread: </span>}
          {title}
        </h3>
        <p className="truncate text-[12.5px] leading-5 text-muted-foreground">
          <span className="text-foreground/70">{meta.label}</span> · {body}
        </p>
      </div>
      <div className="order-last mt-1.5 flex basis-full items-center gap-1 pl-[52px] sm:order-none sm:mt-0 sm:basis-auto sm:pl-0 sm:opacity-0 sm:transition-opacity sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
        {notification.deep_link && (
          <Button asChild variant="ghost" size="sm" className="h-7 px-2 text-brand hover:text-brand">
            <Link
              to={notification.deep_link}
              onClick={() => {
                if (!notification.read) onRead();
              }}
              data-testid={`notification-open-${notification.id}`}
            >
              {OPEN_LABEL[key] || "Open"}
            </Link>
          </Button>
        )}
        {unread && (
          <Button size="sm" variant="ghost" className="h-7 px-2 text-muted-foreground" onClick={onRead}>
            <Check aria-hidden="true" />
            Mark read
          </Button>
        )}
      </div>
      <time className="tabular shrink-0 pt-0.5 text-right text-xs text-muted-foreground sm:w-16 sm:pt-0" dateTime={notification.created_at || undefined}>
        {date && !Number.isNaN(date.getTime()) ? timeLabel(date) : "Recent"}
      </time>
    </article>
  );
}

function PreferenceCard({ title, description, note, footer, children }) {
  return (
    <Section card title={title} description={description} className="mt-5 max-w-3xl overflow-hidden">
      {children}
      <div className="flex flex-col items-start gap-2.5 border-t border-border bg-muted/30 px-4 py-2.5 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-[12.5px] text-muted-foreground">{note}</p>
        {footer}
      </div>
    </Section>
  );
}

function PrefEditor({ prefs, onChange, testidPrefix, emailConfigured }) {
  const set = (key, value) => onChange({ ...prefs, [key]: value });
  const setChannel = (key, value) => onChange({ ...prefs, channels: { ...prefs.channels, [key]: value } });
  return (
    <div>
      <GroupLabel>Channels</GroupLabel>
      <div className="divide-y divide-border/70">
        <Row label="In-app notifications" detail="The bell in the top bar and this Action Center.">
          <Switch aria-label="Enable in-app notifications" data-testid={`${testidPrefix}-channel-in_app`} checked={!!prefs.channels?.in_app} onCheckedChange={(value) => setChannel("in_app", value)} />
        </Row>
        <Row label="Email notifications" detail={emailConfigured ? "Sent by email as well as in the app." : "Skipped until email delivery is configured."}>
          <Switch aria-label="Enable email notifications" data-testid={`${testidPrefix}-channel-email`} checked={!!prefs.channels?.email} onCheckedChange={(value) => setChannel("email", value)} />
        </Row>
      </div>
      <GroupLabel>Alert categories</GroupLabel>
      <div className="divide-y divide-border/70">
        {CATEGORIES.map((category) => (
          <Row key={category.key} label={category.label}>
            <Switch aria-label={`Enable ${category.label} notifications`} data-testid={`${testidPrefix}-cat-${category.key}`} checked={prefs[category.key] !== false} onCheckedChange={(value) => set(category.key, value)} />
          </Row>
        ))}
      </div>
      <GroupLabel>Daily digest & escalation</GroupLabel>
      <div className="divide-y divide-border/70">
        <Row label="Send daily digest" detail="A once-a-day summary.">
          <Switch aria-label="Enable daily digest" data-testid={`${testidPrefix}-daily_digest`} checked={prefs.daily_digest !== false} onCheckedChange={(value) => set("daily_digest", value)} />
        </Row>
        <Row label="Digest hour" detail="Local time in the chosen timezone.">
          <Input type="time" aria-label="Digest hour (local)" className="h-8 w-[118px] text-[13px]" data-testid={`${testidPrefix}-digest_time`} value={prefs.digest_time || "08:00"} onChange={(event) => set("digest_time", event.target.value)} />
          <Select value={prefs.timezone || "UTC"} onValueChange={(value) => set("timezone", value)}>
            <SelectTrigger aria-label="Digest timezone" className="h-8 w-[190px] text-[13px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TIMEZONES.map((timezone) => (
                <SelectItem key={timezone} value={timezone}>{timezone}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Row>
        <Row label="Escalate after" detail="Minutes before an unresolved alert escalates.">
          <Input type="number" min="5" aria-label="Escalate after (minutes)" className="tabular h-8 w-20 text-[13px]" data-testid={`${testidPrefix}-escalation_minutes`} value={prefs.escalation_minutes ?? 60} onChange={(event) => set("escalation_minutes", parseInt(event.target.value || "0", 10))} />
          <span className="text-[13px] text-muted-foreground">min</span>
        </Row>
        <Row label="Maximum escalation level">
          <Input type="number" min="1" aria-label="Maximum escalation level" className="tabular h-8 w-20 text-[13px]" data-testid={`${testidPrefix}-escalation_max_level`} value={prefs.escalation_max_level ?? 3} onChange={(event) => set("escalation_max_level", parseInt(event.target.value || "1", 10))} />
        </Row>
      </div>
    </div>
  );
}

function GroupLabel({ children }) {
  return <div className="border-y border-border/70 bg-muted/30 px-4 py-1.5 text-xs font-medium text-muted-foreground first:border-t-0">{children}</div>;
}

function Row({ label, detail, children }) {
  return (
    <div className="flex flex-col gap-2.5 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <div className="min-w-0">
        <div className="text-[13px] font-medium text-foreground">{label}</div>
        {detail && <p className="mt-0.5 text-[12.5px] leading-5 text-muted-foreground">{detail}</p>}
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}
