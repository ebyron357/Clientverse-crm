import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { formatErr } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Orbit } from "lucide-react";

export default function Login() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", name: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setBusy(true);
    try {
      if (mode === "login") await login(form.email, form.password);
      else await register(form);
      const redirect = new URLSearchParams(window.location.search).get("redirect");
      navigate(redirect || "/dashboard");
    } catch (err) {
      setError(formatErr(err.response?.data?.detail) || err.message);
    } finally { setBusy(false); }
  };

  const googleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      <div className="hidden lg:flex flex-col justify-between bg-[#0A0A0A] text-white p-12">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-lg bg-white flex items-center justify-center">
            <Orbit className="w-5 h-5 text-black" />
          </div>
          <span className="font-display font-extrabold text-xl">ClientVerse</span>
        </div>
        <div>
          <h1 className="font-display text-4xl lg:text-5xl font-extrabold leading-tight tracking-tight">
            The AI-native Client Operations Platform.
          </h1>
          <p className="mt-6 text-gray-400 text-base max-w-md">
            Manage the full client lifecycle — WIN → ONBOARD → SERVE → RETAIN → EXPAND — with evidence-backed AI and governed automation.
          </p>
          <div className="mt-8 flex gap-2 text-xs">
            {["Commitment Ledger", "Explainable Health", "Governed Agents"].map((t) => (
              <span key={t} className="px-3 py-1 rounded-full border border-white/20 text-gray-300">{t}</span>
            ))}
          </div>
        </div>
        <div className="text-xs text-gray-500">Proof before promise. Evidence-driven by design.</div>
      </div>

      <div className="flex items-center justify-center p-8">
        <form onSubmit={submit} className="w-full max-w-sm" data-testid="auth-form">
          <h2 className="font-display text-2xl font-bold">{mode === "login" ? "Welcome back" : "Create your workspace"}</h2>
          <p className="text-sm text-gray-500 mt-1 mb-6">{mode === "login" ? "Sign in to your operations console." : "Start managing clients in minutes."}</p>

          {mode === "register" && (
            <div className="mb-4">
              <Label htmlFor="name">Name</Label>
              <Input id="name" data-testid="name-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required className="mt-1" />
            </div>
          )}
          <div className="mb-4">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" data-testid="email-input" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required className="mt-1" />
          </div>
          <div className="mb-4">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" data-testid="password-input" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required className="mt-1" />
          </div>

          {error && <div className="text-sm text-red-600 mb-3" data-testid="auth-error">{error}</div>}

          <Button type="submit" disabled={busy} data-testid="submit-auth-button" className="w-full bg-[#0A0A0A] hover:bg-[#262626]">
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </Button>

          <div className="relative my-4 text-center">
            <span className="text-xs text-gray-400 bg-[#FAFAFA] px-2 relative z-10">or</span>
            <div className="absolute inset-x-0 top-1/2 border-t border-gray-200" />
          </div>

          <Button type="button" variant="outline" onClick={googleLogin} data-testid="google-login-button" className="w-full">
            Continue with Google
          </Button>

          <p className="text-sm text-gray-500 mt-6 text-center">
            {mode === "login" ? "No account?" : "Already have one?"}{" "}
            <button type="button" data-testid="toggle-mode-button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }} className="text-[#2563EB] font-medium">
              {mode === "login" ? "Create one" : "Sign in"}
            </button>
          </p>
        </form>
      </div>
    </div>
  );
}
