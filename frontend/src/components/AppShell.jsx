import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  LayoutDashboard, GitBranch, Users, Briefcase, Boxes, Activity, LogOut, Orbit,
} from "lucide-react";

const NAV = [
  { to: "/dashboard", label: "Command Center", icon: LayoutDashboard, id: "dashboard" },
  { to: "/pipeline", label: "Pipeline", icon: GitBranch, id: "pipeline" },
  { to: "/directory", label: "Directory", icon: Users, id: "directory" },
  { to: "/workspaces", label: "Client Workspaces", icon: Briefcase, id: "workspaces" },
  { to: "/registries", label: "Registries", icon: Boxes, id: "registries" },
  { to: "/audit", label: "Automation & Audit", icon: Activity, id: "audit" },
];

export default function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const doLogout = async () => { await logout(); navigate("/login"); };

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <aside className="w-64 fixed left-0 top-0 bottom-0 bg-white border-r border-gray-200 flex flex-col py-6 px-4 z-20">
        <div className="flex items-center gap-2 px-2 mb-8">
          <div className="w-9 h-9 rounded-lg bg-[#0A0A0A] flex items-center justify-center">
            <Orbit className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="font-display font-extrabold text-lg leading-none">ClientVerse</div>
            <div className="text-[10px] uppercase tracking-[0.15em] text-gray-400 mt-0.5">Client Operations</div>
          </div>
        </div>
        <nav className="flex flex-col gap-1">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              data-testid={`nav-${n.id}-link`}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors duration-200 ${
                  isActive ? "bg-[#0A0A0A] text-white" : "text-gray-600 hover:bg-gray-100"
                }`
              }
            >
              <n.icon className="w-4 h-4" />
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto border-t border-gray-200 pt-4">
          <div className="px-2 mb-2">
            <div className="text-sm font-medium truncate" data-testid="current-user-name">{user?.name}</div>
            <div className="text-xs text-gray-400 truncate">{user?.email}</div>
          </div>
          <button
            onClick={doLogout}
            data-testid="logout-button"
            className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-100 transition-colors"
          >
            <LogOut className="w-4 h-4" /> Sign out
          </button>
        </div>
      </aside>
      <main className="ml-64 min-h-screen p-8">
        <Outlet />
      </main>
    </div>
  );
}

export function Badge({ children, className = "" }) {
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${className}`}>
      {children}
    </span>
  );
}
