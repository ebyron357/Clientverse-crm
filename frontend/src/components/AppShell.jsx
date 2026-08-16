import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import NotificationBell from "@/components/NotificationBell";
import GlobalCommandDialog from "@/components/GlobalCommandDialog";
import QuickCreateDialog from "@/components/QuickCreateDialog";
import {
  Activity, Bell, BriefcaseBusiness, Boxes, ChevronRight, CirclePlus,
  GitBranch, LayoutDashboard, LogOut, Menu, Orbit, PanelLeftClose, Search,
  Settings, ShieldCheck, Terminal, Users, X,
} from "lucide-react";

const NAV_GROUPS = [
  { label: "Command", items: [{ to: "/dashboard", label: "Command Center", icon: LayoutDashboard, id: "dashboard" }, { to: "/notifications", label: "Action Center", icon: Bell, id: "notifications" }] },
  { label: "Revenue", items: [{ to: "/pipeline", label: "Pipeline", icon: GitBranch, id: "pipeline" }, { to: "/directory", label: "Directory", icon: Users, id: "directory" }] },
  { label: "Client success", items: [{ to: "/workspaces", label: "Client Workspaces", icon: BriefcaseBusiness, id: "workspaces" }, { to: "/registries", label: "Registries", icon: Boxes, id: "registries" }] },
  { label: "Platform", items: [{ to: "/mcp", label: "MCP Console", icon: Terminal, id: "mcp" }, { to: "/audit", label: "Automation & Audit", icon: Activity, id: "audit" }, { to: "/team", label: "Team & Access", icon: ShieldCheck, id: "team", adminOnly: true }, { to: "/settings", label: "Settings", icon: Settings, id: "settings" }] },
];

const TITLES = {
  "/dashboard": ["Command Center", "Operational intelligence across your client portfolio"],
  "/pipeline": ["Pipeline", "Move qualified revenue forward with clear next actions"],
  "/directory": ["Directory", "Relationship intelligence for every company and contact"],
  "/workspaces": ["Client Workspaces", "Operate each customer relationship from one command center"],
  "/registries": ["Registries", "Connected records, providers, and operational registries"],
  "/mcp": ["MCP Console", "Governed AI and tool operations"],
  "/audit": ["Automation & Audit", "Evidence, automation, and system activity"],
  "/team": ["Team & Access", "Roles, invitations, and tenant access"],
  "/notifications": ["Action Center", "Notification preferences and operational awareness"],
  "/settings": ["Settings", "Account, notification, provider, and access configuration"],
};

export default function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [quickCreateOpen, setQuickCreateOpen] = useState(false);
  const heading = useMemo(() => {
    if (location.pathname.startsWith("/workspaces/")) return ["Client 360", "Account operations, health, outcomes, and delivery context"];
    return TITLES[location.pathname] || ["ClientVerse", "Client operations command center"];
  }, [location.pathname]);

  useEffect(() => { setMobileOpen(false); }, [location.pathname]);
  const doLogout = async () => { await logout(); navigate("/login"); };
  const triggerQuickCreate = () => setQuickCreateOpen(true);

  return (
    <div className="min-h-screen bg-[#f7fafc] text-[#0a1628]">
      {mobileOpen && <button aria-label="Close navigation" className="fixed inset-0 z-30 bg-[#0a1628]/50 lg:hidden" onClick={() => setMobileOpen(false)} />}
      <aside className={`cv-scrollbar fixed inset-y-0 left-0 z-40 flex flex-col overflow-y-auto bg-[#0a1628] p-3 text-slate-300 transition-[width,transform] duration-200 lg:translate-x-0 ${collapsed ? "w-[76px]" : "w-[268px]"} ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className={`flex h-14 items-center ${collapsed ? "justify-center" : "justify-between px-2"}`}>
          <button className="flex items-center gap-2.5 text-left" onClick={() => navigate("/dashboard")} aria-label="Go to ClientVerse command center">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[#4ac4e0] to-[#1a9fbf] shadow-[0_8px_20px_rgba(74,196,224,0.2)]"><Orbit className="h-5 w-5 text-white" /></span>
            {!collapsed && <span><span className="block font-display text-lg font-extrabold tracking-[-0.035em] text-white">ClientVerse</span><span className="block text-[10px] font-semibold uppercase tracking-[0.12em] text-[#8fdfee]">Client operations</span></span>}
          </button>
          {!collapsed && <button className="rounded-lg p-1.5 text-slate-400 hover:bg-white/10 hover:text-white lg:hidden" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X className="h-4 w-4" /></button>}
        </div>
        <div className="my-4 border-t border-white/10" />
        <nav aria-label="Primary navigation" className="space-y-5">
          {NAV_GROUPS.map((group) => {
            const visibleItems = group.items.filter((item) => !item.adminOnly || user?.role === "admin");
            if (!visibleItems.length) return null;
            return <section key={group.label} aria-label={group.label}>
              {!collapsed && <div className="mb-1 px-3 text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500">{group.label}</div>}
              <div className="space-y-1">{visibleItems.map((item) => <SidebarLink key={item.to} item={item} collapsed={collapsed} />)}</div>
            </section>;
          })}
        </nav>
        <div className="mt-auto pt-6">
          <div className={`rounded-xl border border-white/10 bg-white/[0.045] p-2.5 ${collapsed ? "text-center" : ""}`}>
            <div className={`flex items-center ${collapsed ? "justify-center" : "gap-2.5"}`}>
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#1a9fbf] text-xs font-bold text-white">{user?.name?.split(" ").map((part) => part[0]).slice(0, 2).join("") || "CV"}</div>
              {!collapsed && <div className="min-w-0 flex-1"><div className="truncate text-xs font-semibold text-white">{user?.name}</div><div className="truncate text-[11px] text-slate-400">{user?.role === "admin" ? "Workspace admin" : "Team member"}</div></div>}
            </div>
            {!collapsed && <button onClick={doLogout} className="mt-2 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-slate-400 transition-colors hover:bg-white/10 hover:text-white"><LogOut className="h-3.5 w-3.5" />Sign out</button>}
          </div>
        </div>
      </aside>

      <div className={`min-h-screen transition-[margin] duration-200 ${collapsed ? "lg:ml-[76px]" : "lg:ml-[268px]"}`}>
        <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-[#f7fafc]/90 backdrop-blur-xl">
          <div className="flex h-[72px] items-center gap-3 px-4 sm:px-6 lg:px-8">
            <button onClick={() => setMobileOpen(true)} className="rounded-lg p-2 text-slate-600 hover:bg-white lg:hidden" aria-label="Open navigation"><Menu className="h-5 w-5" /></button>
            <button onClick={() => setCollapsed((value) => !value)} className="hidden rounded-lg p-2 text-slate-500 hover:bg-white hover:text-[#0a1628] lg:inline-flex" aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}>{collapsed ? <ChevronRight className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}</button>
            <div className="min-w-0 flex-1"><div className="truncate font-display text-lg font-bold tracking-[-0.02em] text-[#0a1628]">{heading[0]}</div><div className="hidden truncate text-xs text-slate-500 xl:block">{heading[1]}</div></div>
            <button onClick={() => setCommandOpen(true)} className="hidden w-full max-w-md items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-left text-sm text-slate-400 shadow-sm transition-colors hover:border-slate-300 hover:text-slate-600 md:flex" aria-label="Search or jump to a page"><Search className="h-4 w-4" /><span className="flex-1">Search or jump to…</span><kbd className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">⌘ K</kbd></button>
            <button onClick={triggerQuickCreate} className="hidden items-center gap-1.5 rounded-xl bg-[#1a9fbf] px-3 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-[#147f9a] sm:flex"><CirclePlus className="h-4 w-4" />Create</button>
            <button onClick={triggerQuickCreate} className="inline-flex rounded-xl bg-[#1a9fbf] p-2 text-white sm:hidden" aria-label="Quick create"><CirclePlus className="h-4 w-4" /></button>
            <NotificationBell />
          </div>
        </header>
        <main className="py-6 sm:py-8"><Outlet /></main>
      </div>
      <GlobalCommandDialog open={commandOpen} onOpenChange={setCommandOpen} onQuickCreate={triggerQuickCreate} />
      <QuickCreateDialog open={quickCreateOpen} onOpenChange={setQuickCreateOpen} onCreated={(type, data) => { if (type === "workspace" && data?.id) navigate(`/workspaces/${data.id}`); else if (type === "opportunity") navigate("/pipeline"); else if (type === "company" || type === "contact") navigate("/directory"); }} />
    </div>
  );
}

function SidebarLink({ item, collapsed }) {
  const Icon = item.icon;
  return <NavLink to={item.to} data-testid={`nav-${item.id}-link`} title={collapsed ? item.label : undefined} className={({ isActive }) => `group relative flex items-center rounded-xl py-2.5 text-sm font-medium transition-colors ${collapsed ? "justify-center px-2" : "gap-3 px-3"} ${isActive ? "bg-[#1a9fbf] text-white shadow-[0_4px_14px_rgba(26,159,191,0.22)]" : "text-slate-300 hover:bg-white/[0.075] hover:text-white"}`}><Icon className="h-4 w-4 shrink-0" />{!collapsed && <span className="truncate">{item.label}</span>}</NavLink>;
}

export function Badge({ children, className = "" }) {
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${className}`}>{children}</span>;
}
