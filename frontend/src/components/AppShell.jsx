import { useEffect, useMemo, useState } from "react";
import { useTheme } from "next-themes";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import NotificationBell from "@/components/NotificationBell";
import GlobalCommandDialog from "@/components/GlobalCommandDialog";
import QuickCreateDialog from "@/components/QuickCreateDialog";
import BrandMark from "@/components/BrandMark";
import { CLIENTVERSE_MODULES, getModuleByRoute, MODULE_GROUPS, MODULE_STATES, PINNED_GROUPS } from "@/platform/modules";
import { ChevronDown, ChevronRight, LogOut, Menu, Monitor, Moon, PanelLeft, Plus, Search, Sun, X } from "lucide-react";

// Which optional navigation groups a person has opened. Pinned groups are always open.
const OPEN_GROUPS_KEY = "cv.nav.open-groups";
const readOpenGroups = () => {
  try { return new Set(JSON.parse(window.localStorage.getItem(OPEN_GROUPS_KEY) || "[]")); }
  catch { return new Set(); }
};

export default function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [quickCreateOpen, setQuickCreateOpen] = useState(false);
  const [openGroups, setOpenGroups] = useState(readOpenGroups);
  const activeModule = useMemo(() => getModuleByRoute(location.pathname), [location.pathname]);
  // A tab of a shared page (Unified Inbox is /operations?tab=conversations) belongs to its
  // own group, so the full route decides which group opens; the page decides the heading.
  const navModule = useMemo(() => getModuleByRoute(`${location.pathname}${location.search}`) || activeModule,
    [location.pathname, location.search, activeModule]);
  // Top bar breadcrumb: the section, then the page. The page itself carries the detail.
  const crumbs = location.pathname.startsWith("/workspaces/")
    ? ["Client Success", "Client 360"]
    : activeModule ? [activeModule.group, activeModule.label] : ["ClientVerse"];

  useEffect(() => { setMobileOpen(false); }, [location.pathname]);
  const doLogout = async () => { await logout(); navigate("/login"); };
  const triggerQuickCreate = () => setQuickCreateOpen(true);
  const toggleGroup = (group) => setOpenGroups((current) => {
    const next = new Set(current);
    if (next.has(group)) next.delete(group); else next.add(group);
    try { window.localStorage.setItem(OPEN_GROUPS_KEY, JSON.stringify([...next])); } catch { /* storage unavailable */ }
    return next;
  });
  const initials = user?.name?.split(" ").map((part) => part[0]).slice(0, 2).join("").toUpperCase() || "CV";

  return <div className="min-h-screen bg-canvas text-foreground">
    {mobileOpen && <button aria-label="Close navigation" className="fixed inset-0 z-30 bg-foreground/40 backdrop-blur-[1px] lg:hidden" onClick={() => setMobileOpen(false)} />}
    <aside className={`fixed inset-y-0 left-0 z-40 flex flex-col overflow-hidden bg-canvas transition-[width,transform] duration-200 max-lg:border-r max-lg:border-border max-lg:shadow-xl lg:translate-x-0 ${collapsed ? "w-[68px]" : "w-[252px]"} ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}>
      <div className={`flex h-14 shrink-0 items-center ${collapsed ? "justify-center" : "justify-between pl-4 pr-2"}`}>
        <button className="flex min-w-0 items-center gap-2.5 rounded-md text-left" onClick={() => navigate("/dashboard")} aria-label="Go to ClientVerse command center">
          <BrandMark className="size-7" />
          {!collapsed && <span className="truncate text-[15px] font-semibold tracking-tight text-foreground">ClientVerse</span>}
        </button>
        {!collapsed && <>
          <button className="hidden rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground lg:inline-flex" onClick={() => setCollapsed(true)} aria-label="Collapse navigation"><PanelLeft className="size-4" /></button>
          <button className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground lg:hidden" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X className="size-4" /></button>
        </>}
      </div>
      <div className={collapsed ? "flex flex-col items-center gap-1 px-2 pb-2" : "px-3 pb-2"}>
        {collapsed && <button className="mb-1 rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground" onClick={() => setCollapsed(false)} aria-label="Expand navigation"><PanelLeft className="size-4" /></button>}
        <button onClick={() => setCommandOpen(true)} className={`flex items-center rounded-md border border-border bg-card text-[13px] text-muted-foreground shadow-xs transition-colors hover:border-input hover:text-foreground ${collapsed ? "size-9 justify-center" : "h-8 w-full gap-2 px-2.5"}`} aria-label="Search or jump to a page">
          <Search className="size-3.5 shrink-0" />
          {!collapsed && <><span className="flex-1 text-left">Search</span><kbd className="cv-kbd">⌘K</kbd></>}
        </button>
      </div>
      <nav aria-label="Primary navigation" className={`cv-scrollbar flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pb-4 ${collapsed ? "px-2" : "px-3"}`}>
        {MODULE_GROUPS.map((group) => {
          const items = CLIENTVERSE_MODULES.filter((item) => item.group === group && (!item.adminOnly || user?.role === "admin"));
          if (!items.length) return null;
          const pinned = PINNED_GROUPS.includes(group);
          const containsActive = items.some((item) => item.id === navModule?.id);
          const open = collapsed || pinned || containsActive || openGroups.has(group);
          const listId = `nav-group-${group.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
          return <section key={group} aria-label={group}>
            {!collapsed && (pinned
              ? <div className="mb-0.5 px-2 py-1 text-xs font-medium text-muted-foreground">{group}</div>
              : <button type="button" onClick={() => toggleGroup(group)} aria-expanded={open} aria-controls={listId} className="group mb-0.5 flex w-full items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:text-foreground">
                  <span className="flex-1 text-left">{group}</span>
                  <ChevronDown className={`size-3.5 transition-transform ${open ? "" : "-rotate-90"}`} aria-hidden="true" />
                </button>)}
            {open && <div id={listId} className="flex flex-col gap-px">{items.map((item) => <SidebarLink key={item.id} item={item} collapsed={collapsed} active={item.id === navModule?.id} />)}</div>}
          </section>;
        })}
      </nav>
      <div className={`shrink-0 border-t border-border/70 ${collapsed ? "p-2" : "p-3"}`}>
        <div className={`flex items-center ${collapsed ? "flex-col gap-2" : "gap-2.5"}`}>
          <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-brand-soft text-xs font-semibold text-brand-strong" title={collapsed ? user?.name : undefined}>{initials}</div>
          {!collapsed && <div className="min-w-0 flex-1"><div className="truncate text-[13px] font-medium text-foreground">{user?.name}</div><div className="truncate text-xs text-muted-foreground">{user?.role === "admin" ? "Workspace admin" : "Team member"}</div></div>}
          <ThemeButton />
          <button onClick={doLogout} className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground" aria-label="Sign out" title="Sign out"><LogOut className="size-4" /></button>
        </div>
      </div>
    </aside>

    <div className={`min-h-screen transition-[margin] duration-200 lg:py-2 lg:pr-2 ${collapsed ? "lg:ml-[68px]" : "lg:ml-[252px]"}`}>
      <div className="flex min-h-screen flex-col bg-background lg:min-h-[calc(100vh-1rem)] lg:rounded-xl lg:shadow-panel">
        <header className="sticky top-0 z-20 border-b border-border/80 bg-background/85 backdrop-blur-xl lg:rounded-t-xl">
          <div className="flex h-14 items-center gap-2 px-4 sm:px-6 lg:px-8">
            <button onClick={() => setMobileOpen(true)} className="-ml-1 rounded-md p-2 text-muted-foreground hover:bg-accent lg:hidden" aria-label="Open navigation"><Menu className="size-5" /></button>
            <nav aria-label="Breadcrumb" className="flex min-w-0 flex-1 items-center gap-1.5 text-[13.5px]">
              {crumbs.map((crumb, index) => <span key={crumb} className="flex min-w-0 items-center gap-1.5">
                {index > 0 && <ChevronRight className="size-3.5 shrink-0 text-muted-foreground/70" aria-hidden="true" />}
                <span className={`truncate ${index === crumbs.length - 1 ? "font-medium text-foreground" : "hidden text-muted-foreground sm:inline"}`} aria-current={index === crumbs.length - 1 ? "page" : undefined}>{crumb}</span>
              </span>)}
            </nav>
            <button onClick={() => setCommandOpen(true)} className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground lg:hidden" aria-label="Search"><Search className="size-[18px]" /></button>
            <button onClick={triggerQuickCreate} className="hidden h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-[13px] font-medium text-primary-foreground shadow-xs hover:bg-primary/90 sm:flex"><Plus className="size-4" />Create</button>
            <button onClick={triggerQuickCreate} className="inline-flex rounded-md bg-primary p-2 text-primary-foreground sm:hidden" aria-label="Quick create"><Plus className="size-4" /></button>
            <NotificationBell />
          </div>
        </header>
        <main className="flex-1 py-6 sm:py-8"><Outlet /></main>
      </div>
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
  return <button type="button" onClick={() => setTheme(next.value)} className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground" aria-label={`Theme: ${current.label}. Switch to ${next.label}`} title={`Theme: ${current.label}`} data-testid="theme-toggle"><Icon className="size-4" /></button>;
}

/** One module link. Active is decided by the shell (path plus query), so two links that share a path never light up together. */
function SidebarLink({ item, collapsed, active }) {
  const Icon = item.icon;
  const pending = item.state !== MODULE_STATES.AVAILABLE;
  return <Link to={item.route} aria-current={active ? "page" : undefined} data-testid={`nav-${item.id}-link`} title={collapsed ? `${item.label}${pending ? " · contract pending" : ""}` : undefined} className={`group relative flex h-8 items-center rounded-md text-[13.5px] font-medium transition-colors ${collapsed ? "justify-center px-2" : "gap-2.5 px-2"} ${active ? "bg-card text-foreground shadow-xs ring-1 ring-border" : "text-foreground/70 hover:bg-accent hover:text-foreground"}`}>
    <>
      <Icon className={`size-4 shrink-0 ${active ? "text-brand" : "text-muted-foreground group-hover:text-foreground"}`} />
      {!collapsed && <><span className="min-w-0 flex-1 truncate">{item.label}</span>{pending && <span className="size-1.5 shrink-0 rounded-full bg-amber-500" title="Contract pending" aria-label="Backend contract pending" />}</>}
    </>
  </Link>;
}

export function Badge({ children, className = "" }) {
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${className}`}>{children}</span>;
}
