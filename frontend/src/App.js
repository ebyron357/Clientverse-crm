import { useEffect, useRef } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from "react-router-dom";
import "@/App.css";
import { api, setStoredToken } from "@/lib/api";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Toaster } from "@/components/ui/sonner";
import AppErrorBoundary from "@/components/AppErrorBoundary";
import AppShell from "@/components/AppShell";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Pipeline from "@/pages/Pipeline";
import Directory from "@/pages/Directory";
import Workspaces from "@/pages/Workspaces";
import WorkspaceDetail from "@/pages/WorkspaceDetail";
import Registries from "@/pages/Registries";
import Mcp from "@/pages/Mcp";
import Audit from "@/pages/Audit";
import Team from "@/pages/Team";
import Notifications from "@/pages/Notifications";
import AcceptInvite from "@/pages/AcceptInvite";
import Settings from "@/pages/Settings";

function AuthCallback() {
  const navigate = useNavigate();
  const done = useRef(false);
  useEffect(() => {
    if (done.current) return;
    done.current = true;
    const hash = window.location.hash;
    const sid = new URLSearchParams(hash.replace("#", "")).get("session_id");
    (async () => {
      try {
        const { data } = await api.post("/auth/google/session", { session_id: sid });
        if (data?.token) setStoredToken(data.token);
        window.history.replaceState(null, "", "/");
        window.location.href = "/dashboard";
      } catch {
        navigate("/login");
      }
    })();
  }, [navigate]);
  return <div className="min-h-screen flex items-center justify-center text-sm text-gray-500">Signing you in…</div>;
}

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex min-h-screen items-center justify-center bg-[#f7fafc] p-6"><div className="cv-card w-full max-w-sm p-7"><div className="h-2 w-20 animate-pulse rounded-full bg-cyan-100" /><div className="mt-5 h-7 w-44 animate-pulse rounded-lg bg-slate-100" /><div className="mt-3 h-4 w-full animate-pulse rounded-lg bg-slate-100" /><div className="mt-2 h-4 w-4/5 animate-pulse rounded-lg bg-slate-100" /></div></div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/invite" element={<AcceptInvite />} />
      <Route element={<Protected><AppShell /></Protected>}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/directory" element={<Directory />} />
        <Route path="/workspaces" element={<Workspaces />} />
        <Route path="/workspaces/:id" element={<WorkspaceDetail />} />
        <Route path="/registries" element={<Registries />} />
        <Route path="/mcp" element={<Mcp />} />
        <Route path="/team" element={<Team />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/audit" element={<Audit />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AppErrorBoundary>
      <AuthProvider>
        <BrowserRouter>
          <AppRouter />
          <Toaster position="top-right" />
        </BrowserRouter>
      </AuthProvider>
    </AppErrorBoundary>
  );
}
