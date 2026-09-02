import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import NotificationBell from "@/components/NotificationBell";
import GlobalCommandDialog from "@/components/GlobalCommandDialog";
import QuickCreateDialog from "@/components/QuickCreateDialog";
import { CLIENTVERSE_MODULES, getModuleByRoute, MODULE_GROUPS, MODULE_STATES } from "@/platform/modules";
import { ChevronRight, CirclePlus, LogOut, Menu, Orbit, PanelLeftClose, Search, X } from "lucide-react";

export default function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [quickCreateOpen, setQuickCreateOpen] = useState(false);
  const activeModule = useMemo(() => getModuleByRoute(location.pathname), [location.pathname]);
  const heading = location.pathname.startsWith("/workspaces/")
    ? ["Client 360", "Account health, outcomes, commitments, and relationship context"]
    : [activeModule?.label || "ClientVerse", activeModule?.description || "Relationship operating system"];

  useEffect(() => { setMobileOpen(false); }, [location.pathname]);
  const doLogout = async () => { await logout(); navigate("/login"); };
  const triggerQuickCreate = () => setQuickCreateOpen(true);

  return <div className="min-h-screen bg-background text-foreground">
    {mobileOpen && <button aria-label="Close navigation" className="fixed inset-0 z-30 bg-foreground/50 lg:hidden" onClick={() => setMobileOpen(false)} />}
    <aside className={`cv-scrollbar fixed inset-y-0 left-0 z-40 flex flex-col overflow-y-auto border-r border-border bg-card text-card-foreground transition-[width,transform] duration-200 lg:translate-x-0 ${collapsed ? "w-[76px]" : "w-[272px]"} ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}>
      <div className={`flex h-[72px] shrink-0 items-center border-b border-border ${collapsed ? "justify-center" : "justify-between px-4"}`}>
        <button className="flex items-center gap-2.5 text-left" onClick={() => navigate("/dashboard")} aria-label="Go to ClientVerse command center">
          <span className="flex size-9 items-center justify-center rounded-xl bg-primary text-primary-foreground"><Orbit className="size-5" /></span>
          {!collapsed && <span><span className="block font-display text-lg font-extrabold tracking-tight text-foreground">ClientVerse</span><span className="block text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Relationship OS</span></span>}
        </button>
        {!collapsed && <button className="rounded-lg p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground lg:hidden" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X className="size-4" /></button>}
      </div>
      <nav aria-label="Primary navigation" className="flex flex-col gap-5 p-3">
        {MODULE_GROUPS.map((group) => {
          const items = CLIENTVERSE_MODULES.filter((item) => item.group === group && (!item.adminOnly || user?.role === "admin"));
          return <section key={group} aria-label={group}>
            {!collapsed && <div className="mb-1 px-3 text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground">{group}</div>}
            <div className="flex flex-col gap-1">{items.map((item) => <SidebarLink key={item.id} item={item} collapsed={collapsed} />)}</div>
          </section>;
        })}
      </nav>
      <div className="mt-auto p-3">
        <div className={`rounded-xl border border-border bg-card p-2.5 ${collapsed ? "text-center" : ""}`}>
          <div className={`flex items-center ${collapsed ? "justify-center" : "gap-2.5"}`}><div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-xs font-bold text-primary-foreground">{user?.name?.split(" ").map((part) => part[0]).slice(0, 2).join("") || "CV"}</div>{!collapsed && <div className="min-w-0 flex-1"><div className="truncate text-xs font-semibold text-foreground">{user?.name}</div><div className="truncate text-[11px] text-muted-foreground">{user?.role === "admin" ? "Workspace admin" : "Team member"}</div></div>}</div>
          {!collapsed && <button onClick={doLogout} className="mt-2 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"><LogOut className="size-3.5" />Sign out</button>}
        </div>
      </div>
    </aside>

    <div className={`min-h-screen transition-[margin] duration-200 ${collapsed ? "lg:ml-[76px]" : "lg:ml-[272px]"}`}>
      <header className="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur-xl">
        <div className="flex h-[72px] items-center gap-3 px-4 sm:px-6 lg:px-8">
          <button onClick={() => setMobileOpen(true)} className="rounded-lg p-2 text-muted-foreground hover:bg-card lg:hidden" aria-label="Open navigation"><Menu className="size-5" /></button>
          <button onClick={() => setCollapsed((value) => !value)} className="hidden rounded-lg p-2 text-muted-foreground hover:bg-card hover:text-foreground lg:inline-flex" aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}>{collapsed ? <ChevronRight className="size-4" /> : <PanelLeftClose className="size-4" />}</button>
          <div className="min-w-0 flex-1"><div className="truncate font-display text-lg font-bold tracking-tight text-foreground">{heading[0]}</div><div className="hidden truncate text-xs text-muted-foreground xl:block">{heading[1]}</div></div>
          <button onClick={() => setCommandOpen(true)} className="hidden w-full max-w-md items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 text-left text-sm text-muted-foreground transition-colors hover:border-ring md:flex" aria-label="Search or jump to a page"><Search className="size-4" /><span className="flex-1">Search modules and actions…</span><kbd className="rounded border border-border bg-secondary px-1.5 py-0.5 text-[10px] font-medium">⌘ K</kbd></button>
          <button onClick={triggerQuickCreate} className="hidden items-center gap-1.5 rounded-xl bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 sm:flex"><CirclePlus className="size-4" />Create</button>
          <button onClick={triggerQuickCreate} className="inline-flex rounded-xl bg-primary p-2 text-primary-foreground sm:hidden" aria-label="Quick create"><CirclePlus className="size-4" /></button>
          <NotificationBell />
        </div>
      </header>
      <main className="py-6 sm:py-8"><Outlet /></main>
    </div>
    <GlobalCommandDialog open={commandOpen} onOpenChange={setCommandOpen} onQuickCreate={triggerQuickCreate} />
    <QuickCreateDialog open={quickCreateOpen} onOpenChange={setQuickCreateOpen} onCreated={(type, data) => { if (type === "workspace" && data?.id) navigate(`/workspaces/${data.id}`); else if (type === "opportunity") navigate("/pipeline"); else if (type === "company" || type === "contact") navigate("/directory"); }} />
  </div>;
}

function SidebarLink({ item, collapsed }) {
  const Icon = item.icon;
  const pending = item.state !== MODULE_STATES.AVAILABLE;
  return <NavLink to={item.route} data-testid={`nav-${item.id}-link`} title={collapsed ? `${item.label}${pending ? " · contract pending" : ""}` : undefined} className={({ isActive }) => `group relative flex items-center rounded-xl py-2 text-sm font-medium transition-colors ${collapsed ? "justify-center px-2" : "gap-3 px-3"} ${isActive ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent hover:text-foreground"}`}><Icon className="size-4 shrink-0" />{!collapsed && <><span className="min-w-0 flex-1 truncate">{item.label}</span>{pending && <span className="size-1.5 shrink-0 rounded-full bg-amber-500" aria-label="Backend contract pending" />}</>}</NavLink>;
}

export function Badge({ children, className = "" }) {
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${className}`}>{children}</span>;
}
