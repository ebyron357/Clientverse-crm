import { useEffect, useLayoutEffect, useRef } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from "react-router-dom";
import "@/App.css";
import { api, setStoredToken } from "@/lib/api";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { ThemeProvider } from "next-themes";
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
import Operations from "@/pages/Operations";
import Audit from "@/pages/Audit";
import Team from "@/pages/Team";
import Notifications from "@/pages/Notifications";
import AcceptInvite from "@/pages/AcceptInvite";
import Settings from "@/pages/Settings";
import ClientOps from "@/pages/ClientOps";
import FieldOps from "@/pages/FieldOps";
import ClientPortal from "@/pages/ClientPortal";
import ModuleStatus from "@/pages/ModuleStatus";
import RecoveryProof from "@/pages/RecoveryProof";
import Leads from "@/pages/Leads";
import Tasks, { TaskRedirect } from "@/pages/Tasks";
import WebsiteForms from "@/pages/WebsiteForms";
import CalendarPage from "@/pages/Calendar";
import PublicBooking from "@/pages/PublicBooking";
import ManageBooking from "@/pages/ManageBooking";
import { CLIENTVERSE_MODULES, MODULE_STATES } from "@/platform/modules";
import { ChooseOwnPassword } from "@/components/ChangePassword";

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
  return <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">Signing you in…</div>;
}

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex min-h-screen items-center justify-center bg-canvas p-6"><div className="cv-card w-full max-w-sm p-7"><div className="h-2 w-20 animate-pulse rounded-full bg-brand-soft" /><div className="mt-5 h-7 w-44 animate-pulse rounded-lg bg-muted" /><div className="mt-3 h-4 w-full animate-pulse rounded-lg bg-muted" /><div className="mt-2 h-4 w-4/5 animate-pulse rounded-lg bg-muted" /></div></div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.must_change_password) return <ChooseOwnPassword />;
  return children;
}

function AppRouter() {
  const location = useLocation();
  // Google sign-in returns to /dashboard (see Login), which no other site may frame. Only
  // there, and only in the browser's own window: /book/:key can sit in another site's frame,
  // and a frame must never be able to sign this app into a session someone else picked.
  const signInReturn = location.pathname === "/dashboard" && location.hash?.includes("session_id=") && window.top === window.self;
  if (signInReturn) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/invite" element={<AcceptInvite />} />
      <Route path="/portal/:token" element={<ClientPortal />} />
      {/* Public booking pages: outside the signed-in app, and /book/:key may be framed. */}
      <Route path="/book/:key" element={<PublicBooking />} />
      <Route path="/booking/manage/:token" element={<ManageBooking />} />
      <Route element={<Protected><AppShell /></Protected>}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/deals" element={<Pipeline />} />
        <Route path="/directory" element={<Directory />} />
        <Route path="/contacts" element={<Directory initialTab="contacts" />} />
        <Route path="/companies" element={<Directory initialTab="companies" />} />
        <Route path="/workspaces" element={<Workspaces />} />
        <Route path="/workspaces/:id" element={<WorkspaceDetail />} />
        <Route path="/registries" element={<Registries />} />
        <Route path="/mcp" element={<Mcp />} />
        <Route path="/operations" element={<Operations />} />
        <Route path="/team" element={<Team />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="/client-ops" element={<ClientOps />} />
        <Route path="/proof" element={<RecoveryProof />} />
        <Route path="/leads" element={<Leads />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/tasks/:taskId" element={<TaskRedirect />} />
        <Route path="/website-forms" element={<WebsiteForms />} />
        <Route path="/scheduling/calendar" element={<CalendarPage />} />
        <Route path="/field" element={<FieldOps />} />
        {CLIENTVERSE_MODULES.filter((module) => module.state !== MODULE_STATES.AVAILABLE).map((module) => <Route key={module.id} path={module.route} element={<ModuleStatus moduleId={module.id} />} />)}
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

// Pages a client or a website visitor sees (booking, manage-booking, the client portal) stay
// light: they are often embedded in someone else's site, which sets its own colours.
const PUBLIC_PREFIXES = ["/book/", "/booking/", "/portal/"];

function ThemedApp() {
  const { pathname } = useLocation();
  const isPublic = PUBLIC_PREFIXES.some((prefix) => pathname.startsWith(prefix));
  const forcedTheme = isPublic ? "light" : undefined;
  // They keep their own typeface too (index.css). On <body>, so dialogs rendered there match.
  useLayoutEffect(() => {
    document.body.classList.toggle("cv-public", isPublic);
  }, [isPublic]);
  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem disableTransitionOnChange storageKey="cv-theme" forcedTheme={forcedTheme}>
      <AppRouter />
      <Toaster position="top-right" />
    </ThemeProvider>
  );
}

export default function App() {
  return (
    <AppErrorBoundary>
      <AuthProvider>
        <BrowserRouter>
          <ThemedApp />
        </BrowserRouter>
      </AuthProvider>
    </AppErrorBoundary>
  );
}
