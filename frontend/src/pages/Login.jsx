import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { formatErr } from "@/lib/api";
import AuthLayout from "@/components/AuthLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AlertCircle, Eye, EyeOff, Loader2 } from "lucide-react";

const MIN_PASSWORD = 8;

export default function Login() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const params = new URLSearchParams(window.location.search);
  const redirect = params.get("redirect");
  // Coming from an invitation: the new account is created on the invitation page, inside
  // the team that sent it. Self-signup here would create a separate organisation instead.
  const fromInvite = Boolean(redirect?.startsWith("/invite"));
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: params.get("email") || "", password: "", name: "" });
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const signingIn = mode === "login";

  const submit = async (event) => {
    event.preventDefault(); setError(""); setBusy(true);
    try { if (signingIn) await login(form.email, form.password); else await register(form); navigate(redirect || "/dashboard"); }
    catch (requestError) { setError(formatErr(requestError.response?.data?.detail) || requestError.message || "We could not sign you in. Please try again."); }
    finally { setBusy(false); }
  };
  const changeMode = () => { if (fromInvite) { navigate(redirect); return; } setMode((current) => current === "login" ? "register" : "login"); setError(""); };

  return <AuthLayout footer={<>{fromInvite ? "No account yet?" : signingIn ? "New to ClientVerse?" : "Already have a workspace?"} <button type="button" data-testid="toggle-mode-button" onClick={changeMode} className="font-medium text-foreground underline-offset-4 hover:underline">{fromInvite ? "Create it from your invitation" : signingIn ? "Create a workspace" : "Sign in"}</button></>}>
    <h1 className="text-2xl font-semibold tracking-tight text-foreground">{signingIn ? "Sign in to ClientVerse" : "Create your workspace"}</h1>
    <p className="mt-2 text-sm leading-6 text-muted-foreground">{fromInvite ? "Sign in to accept your invitation and join the team." : signingIn ? "Welcome back. Enter your details to continue." : "Set up a secure workspace for your team. It takes a minute."}</p>

    <form onSubmit={submit} className="mt-7 space-y-4" data-testid="auth-form">
      {!signingIn && <div className="grid gap-1.5"><Label htmlFor="name">Your name</Label><Input id="name" data-testid="name-input" className="h-10" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required autoComplete="name" placeholder="Jordan Lee" /></div>}
      <div className="grid gap-1.5"><Label htmlFor="email">Work email</Label><Input id="email" type="email" data-testid="email-input" className="h-10" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required autoComplete="email" placeholder="you@company.com" /></div>
      <div className="grid gap-1.5">
        <Label htmlFor="password">Password</Label>
        <div className="relative">
          <Input id="password" type={showPassword ? "text" : "password"} data-testid="password-input" className="h-10 pr-10" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required minLength={signingIn ? undefined : MIN_PASSWORD} autoComplete={signingIn ? "current-password" : "new-password"} aria-describedby="password-help" />
          <button type="button" onClick={() => setShowPassword((value) => !value)} className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-md text-muted-foreground hover:text-foreground" aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword}>{showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button>
        </div>
        <p id="password-help" className="text-xs leading-5 text-muted-foreground">{signingIn ? "Forgot it? Your workspace admin can reset it from Team & Access." : `At least ${MIN_PASSWORD} characters.`}</p>
      </div>
      {error && <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm leading-5 text-red-700" data-testid="auth-error" role="alert"><AlertCircle className="mt-0.5 size-4 shrink-0" />{error}</div>}
      <Button type="submit" disabled={busy} data-testid="submit-auth-button" className="h-10 w-full cv-action-primary">{busy && <Loader2 className="size-4 animate-spin" />}{busy ? "Please wait…" : signingIn ? "Sign in" : "Create workspace"}</Button>
    </form>
  </AuthLayout>;
}
