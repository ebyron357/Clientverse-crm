import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { formatErr } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AlertCircle, ArrowRight, CheckCircle2, LockKeyhole, Orbit, ShieldCheck, Sparkles } from "lucide-react";

export default function Login() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", name: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault(); setError(""); setBusy(true);
    try { if (mode === "login") await login(form.email, form.password); else await register(form); const redirect = new URLSearchParams(window.location.search).get("redirect"); navigate(redirect || "/dashboard"); }
    catch (requestError) { setError(formatErr(requestError.response?.data?.detail) || requestError.message || "We could not sign you in. Please try again."); }
    finally { setBusy(false); }
  };
  const googleLogin = () => { const redirectUrl = window.location.origin + "/dashboard"; window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`; };
  const changeMode = () => { setMode((current) => current === "login" ? "register" : "login"); setError(""); };

  return <div className="min-h-screen bg-[#f7fafc] lg:grid lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
    <aside className="relative hidden overflow-hidden bg-[#0a1628] p-12 text-white lg:flex lg:flex-col lg:justify-between">
      <div className="pointer-events-none absolute inset-0 opacity-80" style={{ background: "radial-gradient(circle at 22% 18%, rgba(74,196,224,.24), transparent 32%), radial-gradient(circle at 80% 75%, rgba(26,159,191,.18), transparent 35%)" }} />
      <div className="relative flex items-center gap-2.5"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-[#4ac4e0] to-[#1a9fbf] shadow-[0_10px_28px_rgba(74,196,224,.24)]"><Orbit className="h-5 w-5 text-white" /></span><div><span className="block font-display text-xl font-extrabold tracking-[-0.04em]">ClientVerse</span><span className="block text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8fdfee]">Client operations platform</span></div></div>
      <div className="relative max-w-xl"><div className="mb-6 inline-flex items-center gap-2 rounded-full border border-[#4ac4e0]/25 bg-white/5 px-3 py-1.5 text-xs font-semibold text-[#a7e6f2]"><Sparkles className="h-3.5 w-3.5" />Client intelligence, made operational</div><h1 className="font-display text-5xl font-extrabold leading-[1.02] tracking-[-0.05em]">Every client relationship. <span className="text-[#4ac4e0]">One clear next move.</span></h1><p className="mt-6 max-w-lg text-base leading-7 text-slate-300">Move from revenue to retention with a practical operating system for pipeline, client health, commitments, approvals, and evidence-backed AI.</p><div className="mt-9 grid grid-cols-3 gap-3"><ValueTile label="Revenue" text="Pipeline clarity" /><ValueTile label="Delivery" text="Commitment control" /><ValueTile label="Retention" text="Explainable health" /></div></div>
      <div className="relative flex items-center gap-2 text-xs text-slate-400"><ShieldCheck className="h-4 w-4 text-[#4ac4e0]" />Tenant-aware access · Evidence-first operations · Governed automation</div>
    </aside>
    <main className="flex min-h-screen items-center justify-center px-5 py-10 sm:px-8"><div className="w-full max-w-[420px]"><div className="mb-9 flex items-center gap-2.5 lg:hidden"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[#4ac4e0] to-[#1a9fbf]"><Orbit className="h-4 w-4 text-white" /></span><span className="font-display text-lg font-extrabold text-[#0a1628]">ClientVerse</span></div><div className="cv-card p-6 sm:p-8"><div className="mb-7"><div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-50 text-[#1a9fbf]"><LockKeyhole className="h-5 w-5" /></div><h2 className="font-display text-3xl font-extrabold tracking-[-0.04em] text-[#0a1628]">{mode === "login" ? "Welcome back" : "Create your workspace"}</h2><p className="mt-2 text-sm leading-6 text-slate-500">{mode === "login" ? "Sign in to see the client relationships and operating priorities that need your attention." : "Set up a secure ClientVerse workspace to organize client operations."}</p></div><form onSubmit={submit} className="space-y-4" data-testid="auth-form">{mode === "register" && <div className="grid gap-1.5"><Label htmlFor="name">Your name <span className="text-red-500">*</span></Label><Input id="name" data-testid="name-input" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required autoComplete="name" /></div>}<div className="grid gap-1.5"><Label htmlFor="email">Work email <span className="text-red-500">*</span></Label><Input id="email" type="email" data-testid="email-input" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required autoComplete="email" placeholder="you@company.com" /></div><div className="grid gap-1.5"><Label htmlFor="password">Password <span className="text-red-500">*</span></Label><Input id="password" type="password" data-testid="password-input" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required autoComplete={mode === "login" ? "current-password" : "new-password"} /></div>{error && <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-3 text-sm leading-5 text-red-700" data-testid="auth-error" role="alert"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}<Button type="submit" disabled={busy} data-testid="submit-auth-button" className="h-11 w-full cv-action-primary">{busy ? "Please wait…" : mode === "login" ? "Sign in to ClientVerse" : "Create secure workspace"}<ArrowRight className="ml-2 h-4 w-4" /></Button></form><div className="relative my-6"><div className="border-t border-slate-200" /><span className="absolute left-1/2 top-0 -translate-x-1/2 -translate-y-1/2 bg-white px-2 text-[11px] font-medium uppercase tracking-[0.1em] text-slate-400">or</span></div><Button type="button" variant="outline" onClick={googleLogin} data-testid="google-login-button" className="h-11 w-full border-slate-200 bg-white hover:bg-slate-50">Continue with Google</Button><p className="mt-6 text-center text-sm text-slate-500">{mode === "login" ? "New to ClientVerse?" : "Already have a workspace?"} <button type="button" data-testid="toggle-mode-button" onClick={changeMode} className="font-semibold text-[#1a9fbf] hover:text-[#147f9a]">{mode === "login" ? "Create one" : "Sign in"}</button></p></div><p className="mt-5 flex items-center justify-center gap-1.5 text-center text-xs text-slate-400"><CheckCircle2 className="h-3.5 w-3.5 text-[#1a9fbf]" />ClientVerse uses tenant-aware access and governed operations.</p></div></main>
  </div>;
}

function ValueTile({ label, text }) { return <div className="rounded-xl border border-white/10 bg-white/[0.055] p-3"><div className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#8fdfee]">{label}</div><div className="mt-1 text-xs leading-5 text-slate-200">{text}</div></div>; }
