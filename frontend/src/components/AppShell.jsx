import { useEffect, useMemo, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import NotificationBell from "@/components/NotificationBell";
import GlobalCommandDialog from "@/components/GlobalCommandDialog";
import QuickCreateDialog from "@/components/QuickCreateDialog";
import BrandMark from "@/components/BrandMark";
import { AccountSwitcher, ActingBanner } from "@/components/AgencySwitcher";
import { Avatar } from "@/components/page/Page";
import { breadcrumbFor, MAIN_MENU, menuEntryFor, SETTINGS_ENTRY } from "@/platform/navigation";
import { ChevronRight, LogOut, Menu, Monitor, Moon, PanelLeft, Plus, Search, Sun, X } from "lucide-react";

// A per-browser convenience: whether the main menu is shrunk to icons on a wide screen.
const COLLAPSED_KEY = "cv.nav.collapsed";
const readCollapsed = () => {
  try { return window.localStorage.getItem(COLLAPSED_KEY) === "1"; } catch { return false; }
};
const WIDE = "(min-width: 1024px)";
const isWide = () => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(WIDE).matches;
const SHORTCUT = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "") ? "⌘K" : "Ctrl K";

// The counts beside menu items. Each comes from an endpoint a page already reads, so the
// badge agrees with what the page shows. A failed or zero count shows no badge.
const OPEN_TASK_STATUSES = "todo,in_progress,blocked";
const COUNT_SOURCES = {
  leads: () => api.get("/leads/summary").then(({ data }) => data?.open_now),
  inbox: () => api.get("/conversations/summary").then(({ data }) => data?.open_conversations),
  // The Tasks page's Overdue tab in its default view: my open tasks past due, plus unowned ones.
  tasks: () => api.get("/tasks", {
    params: { status: OPEN_TASK_STATUSES, due_before: new Date(Date.now() - 1).toISOString(), mine: true, include_unassigned: true, limit: 1 },
  }).then(({ data }) => data?.total),
  approvals: () => api.get("/approval-queue/summary").then(({ data }) => data?.awaiting_decision),
};

/** Fetches every count when the shell mounts and again whenever the page changes; never blocks rendering. */
function useMenuCounts(locationKey) {
  const [counts, setCounts] = useState({});
  const latest = useRef(0);
  useEffect(() => {
    const run = ++latest.current;
    const keys = Object.keys(COUNT_SOURCES);
    Promise.allSettled(keys.map((key) => COUNT_SOURCES[key]())).then((results) => {
      if (run !== latest.current) return;
      setCounts(Object.fromEntries(keys.map((key, index) => {
        const value = results[index].status === "fulfilled" ? Number(results[index].value) : 0;
        return [key, Number.isFinite(value) && value > 0 ? value : 0];
      })));
    });
  }, [locationKey]);
  return counts;
}

export default function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsedPreference, setCollapsedPreference] = useState(readCollapsed);
  const [wide, setWide] = useState(isWide);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [quickCreateOpen, setQuickCreateOpen] = useState(false);
  // The drawer on a narrow screen always shows labels; only a wide screen shrinks to icons.
  const collapsed = collapsedPreference && wide;
  const activeEntry = useMemo(() => menuEntryFor(location), [location]);
  const crumbs = useMemo(() => breadcrumbFor(location), [location]);
  const counts = useMenuCounts(`${location.pathname}${location.search}`);
  const isAdmin = user?.role === "admin";
  const menu = MAIN_MENU.filter((entry) => !entry.adminOnly || isAdmin);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const query = window.matchMedia(WIDE);
    const update = () => setWide(query.matches);
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);
  useEffect(() => { setMobileOpen(false); }, [location.pathname, location.search]);
  const setCollapsed = (value) => {
    setCollapsedPreference(value);
    try { window.localStorage.setItem(COLLAPSED_KEY, value ? "1" : "0"); } catch { /* storage unavailable */ }
  };
  const doLogout = async () => { await logout(); navigate("/login"); };
  const triggerQuickCreate = () => setQuickCreateOpen(true);

  return <div className="min-h-screen bg-canvas text-foreground">
    {mobileOpen && <button aria-label="Close navigation" className="fixed inset-0 z-30 bg-sidebar/60 backdrop-blur-[1px] lg:hidden" onClick={() => setMobileOpen(false)} />}
    <aside className={`fixed inset-y-0 left-0 z-40 flex w-[260px] flex-col overflow-hidden border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width,transform] duration-200 lg:translate-x-0 ${collapsed ? "lg:w-[68px]" : "lg:w-[228px]"} ${mobileOpen ? "translate-x-0 max-lg:shadow-2xl" : "-translate-x-full"}`} data-testid="app-sidebar">
      <div className={`flex h-[60px] shrink-0 items-center ${collapsed ? "justify-center" : "justify-between pl-4 pr-2"}`}>
        <button className="flex min-w-0 items-center gap-2.5 rounded-lg text-left" onClick={() => navigate("/dashboard")} aria-label="Go to Today">
          <BrandMark className="size-[30px]" />
          {!collapsed && <span className="truncate text-[15px] font-bold tracking-tight text-sidebar-active-foreground">ClientVerse</span>}
        </button>
        {!collapsed && <>
          <button className="hidden rounded-md p-1.5 text-sidebar-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-active-foreground lg:inline-flex" onClick={() => setCollapsed(true)} aria-label="Collapse navigation" title="Collapse navigation"><PanelLeft className="size-4" /></button>
          <button className="rounded-md p-1.5 text-sidebar-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-active-foreground lg:hidden" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X className="size-4" /></button>
        </>}
      </div>
      {collapsed && <div className="flex justify-center pb-2">
        <button className="rounded-md p-2 text-sidebar-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-active-foreground" onClick={() => setCollapsed(false)} aria-label="Expand navigation" title="Expand navigation"><PanelLeft className="size-4" /></button>
      </div>}
      <AccountSwitcher user={user} collapsed={collapsed} />

      <nav aria-label="Main" className="flex min-h-0 flex-1 flex-col">
        <ul className={`cv-scrollbar cv-sidebar-scroll flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto pb-3 pt-1 ${collapsed ? "px-2" : "px-3"}`}>
          {menu.map((entry) => <li key={entry.id}><MenuLink entry={entry} to={entry.route} collapsed={collapsed} active={activeEntry?.id === entry.id} count={entry.count ? counts[entry.count] : 0} /></li>)}
        </ul>
        {/* Pinned to the bottom, below the scrolling list. */}
        <div className={`shrink-0 pb-1 ${collapsed ? "px-2" : "px-3"}`}>
          <MenuLink entry={SETTINGS_ENTRY} to={SETTINGS_ENTRY.route} collapsed={collapsed} active={activeEntry?.id === SETTINGS_ENTRY.id} />
        </div>
      </nav>
      <div className={`shrink-0 border-t border-sidebar-border ${collapsed ? "px-2 py-3" : "p-3"}`}>
        <div className={`flex items-center ${collapsed ? "flex-col gap-2" : "gap-2"}`}>
          <span className="flex" title={collapsed ? user?.name : undefined}><Avatar name={user?.name || user?.email || "ClientVerse"} /></span>
          {!collapsed && <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] font-semibold text-sidebar-active-foreground">{user?.name}</div>
            <div className="truncate text-xs text-sidebar-muted">{user?.acting ? "Agency admin" : isAdmin ? "Workspace admin" : "Team member"}</div>
          </div>}
          <div className={`flex shrink-0 items-center ${collapsed ? "flex-col gap-1" : "-mr-1"}`}>
            <ThemeButton />
            <button onClick={doLogout} className="rounded-md p-1.5 text-sidebar-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-active-foreground" aria-label="Sign out" title="Sign out" data-testid="sign-out-button"><LogOut className="size-4" /></button>
          </div>
        </div>
      </div>
    </aside>

    <div className={`flex min-h-screen flex-col transition-[margin] duration-200 ${collapsed ? "lg:ml-[68px]" : "lg:ml-[228px]"}`}>
      <header className="sticky top-0 z-20 border-b border-border bg-card/95 backdrop-blur-xl">
        <div className="flex h-[60px] items-center gap-2 px-4 sm:gap-3 sm:px-6">
          <button onClick={() => setMobileOpen(true)} className="-ml-1 rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground lg:hidden" aria-label="Open navigation" aria-expanded={mobileOpen}><Menu className="size-5" /></button>
          <nav aria-label="Breadcrumb" className="flex min-w-0 flex-1 items-center gap-1.5 text-sm">
            {crumbs.map((crumb, index) => <span key={`${index}-${crumb}`} className="flex min-w-0 items-center gap-1.5">
              {index > 0 && <ChevronRight className="hidden size-3.5 shrink-0 text-muted-foreground/70 sm:block" aria-hidden="true" />}
              <span className={`truncate ${index === crumbs.length - 1 ? "text-[15px] font-bold tracking-tight text-foreground" : "hidden font-medium text-muted-foreground sm:inline"}`} aria-current={index === crumbs.length - 1 ? "page" : undefined}>{crumb}</span>
            </span>)}
          </nav>
          <button onClick={() => setCommandOpen(true)} className="hidden h-9 w-60 items-center gap-2 rounded-lg border border-border bg-canvas px-3 text-[13px] text-muted-foreground transition-colors hover:border-input hover:text-foreground md:flex lg:w-72 xl:w-[400px]" aria-label="Search or jump to a page" data-testid="global-search-button">
            <Search className="size-4 shrink-0" aria-hidden="true" />
            <span className="flex-1 truncate text-left">Search or jump to…</span>
            <kbd className="cv-kbd">{SHORTCUT}</kbd>
          </button>
          <button onClick={() => setCommandOpen(true)} className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground md:hidden" aria-label="Search"><Search className="size-[18px]" /></button>
          {/* The dark theme's brand blue is light, so the label turns dark on it (as Calendar's today does). */}
          <button onClick={triggerQuickCreate} className="hidden h-9 items-center gap-1.5 rounded-lg bg-brand px-3.5 text-[13px] font-semibold text-brand-foreground shadow-xs transition-colors hover:bg-brand/90 dark:text-background sm:flex" data-testid="quick-create-button"><Plus className="size-4" aria-hidden="true" />Create</button>
          <button onClick={triggerQuickCreate} className="inline-flex rounded-lg bg-brand p-2 text-brand-foreground dark:text-background sm:hidden" aria-label="Quick create"><Plus className="size-4" /></button>
          <NotificationBell />
        </div>
      </header>
      <main className="flex-1 py-5 sm:py-6"><ActingBanner user={user} /><Outlet /></main>
    </div>
    <GlobalCommandDialog open={commandOpen} onOpenChange={setCommandOpen} onQuickCreate={triggerQuickCreate} />
    <QuickCreateDialog open={quickCreateOpen} onOpenChange={setQuickCreateOpen} onCreated={(type, data) => { if (type === "workspace" && data?.id) navigate(`/workspaces/${data.id}`); else if (type === "opportunity") navigate("/pipeline"); else if (type === "company" || type === "contact") navigate("/directory"); }} />
  </div>;
}

// Light, dark, or follow the device. One button cycles through them.
const THEMES = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "Match device", icon: Monitor },
];
function ThemeButton() {
  const { theme = "light", setTheme } = useTheme();
  const index = Math.max(0, THEMES.findIndex((option) => option.value === theme));
  const current = THEMES[index];
  const next = THEMES[(index + 1) % THEMES.length];
  const Icon = current.icon;
  return <button type="button" onClick={() => setTheme(next.value)} className="rounded-md p-1.5 text-sidebar-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-active-foreground" aria-label={`Theme: ${current.label}. Switch to ${next.label}`} title={`Theme: ${current.label}`} data-testid="theme-toggle"><Icon className="size-4" /></button>;
}

const countText = (count) => (count > 99 ? "99+" : String(count));

/** One main menu link, with its count. Which link is current is decided by the shell (path plus query). */
function MenuLink({ entry, to, collapsed, active, count = 0 }) {
  const Icon = entry.icon;
  const tone = entry.urgent ? "bg-sidebar-urgent text-sidebar-active-foreground" : "bg-sidebar-pill text-sidebar-foreground";
  const summary = count > 0 ? `${countText(count)} ${entry.countLabel}` : "";
  return <Link to={to} aria-current={active ? "page" : undefined} data-testid={entry.testid} title={collapsed ? [entry.label, summary].filter(Boolean).join(" · ") : undefined}
    className={`group relative flex h-9 items-center rounded-[9px] text-[13.5px] font-semibold transition-colors ${collapsed ? "justify-center px-2" : "gap-2.5 px-2.5"} ${active ? "bg-sidebar-accent text-sidebar-active-foreground" : "text-sidebar-foreground hover:bg-sidebar-hover hover:text-sidebar-active-foreground"}`}>
    <Icon className={`size-[18px] shrink-0 ${active ? "text-sidebar-active-foreground" : "text-sidebar-muted group-hover:text-sidebar-foreground"}`} strokeWidth={1.85} aria-hidden="true" />
    {collapsed ? <span className="sr-only">{entry.label}</span> : <span className="min-w-0 flex-1 truncate">{entry.label}</span>}
    {count > 0 && <>
      <span className="sr-only">{`, ${summary}`}</span>
      <span aria-hidden="true" data-testid={`nav-${entry.id}-count`} className={`tabular flex items-center justify-center rounded-full font-bold leading-none ${tone} ${collapsed ? "absolute right-0.5 top-0.5 h-4 min-w-4 px-1 text-[10px] ring-2 ring-sidebar" : "h-5 min-w-5 px-1.5 text-[11px]"}`}>{countText(count)}</span>
    </>}
  </Link>;
}

export function Badge({ children, className = "" }) {
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${className}`}>{children}</span>;
}
