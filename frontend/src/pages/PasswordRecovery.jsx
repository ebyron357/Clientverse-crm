import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api, clearStoredToken, formatErr } from "@/lib/api";
import AuthLayout from "@/components/AuthLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function PasswordRecovery({ reset = false }) {
  const { setUser } = useAuth();
  const { hash, pathname } = useLocation();
  // Keep the capability in component memory only, never storage or query strings.
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => {
    if (reset) {
      const incoming = new URLSearchParams(hash.slice(1)).get("token");
      if (incoming) {
        setToken(incoming); setMessage(""); setError(""); setPassword(""); setConfirmation("");
      }
      window.history.replaceState(window.history.state, "", pathname);
    }
  }, [reset, hash, pathname]);

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    if (reset && password !== confirmation) { setError("The passwords do not match."); return; }
    setBusy(true);
    try {
      const { data } = await api.post(reset ? "/auth/reset-password" : "/auth/forgot-password",
        reset ? { token, new_password: password } : { email });
      setMessage(data.message);
      if (reset) {
        setPassword(""); setConfirmation(""); setToken("");
        clearStoredToken(); setUser(false);
      }
    } catch (err) {
      setError(err.response ? formatErr(err.response.data?.detail) : "We could not connect. Please try again.");
    } finally { setBusy(false); }
  };

  const missing = reset && !token && !message;
  return <AuthLayout footer={<Link to="/login" className="font-medium underline underline-offset-4">Back to sign in</Link>}>
    <h1 className="text-2xl font-semibold tracking-tight text-foreground">{reset ? "Choose a new password" : "Reset your password"}</h1>
    <p className="mt-2 text-sm leading-6 text-muted-foreground">{reset ? "Choose a password with at least 8 characters. Your previous sessions will end." : "Enter your account email. You can recover access without signing in or asking an administrator."}</p>
    {message ? <div role="status" className="mt-6 space-y-3 text-sm"><p>{message}</p>{!reset && <p className="text-muted-foreground">Check your inbox and spam folder. Links expire after 20 minutes. If nothing arrives, wait before trying again or contact support.</p>}</div> : missing ?
      <p role="alert" className="mt-6 text-sm">This reset link is missing. <Link to="/forgot-password" className="underline">Request a new link</Link>.</p> :
      <form onSubmit={submit} className="mt-7 space-y-4">
        {reset ? <>
          <div className="grid gap-1.5"><Label htmlFor="new-password">New password</Label><Input id="new-password" type="password" autoComplete="new-password" required minLength={8} maxLength={72} value={password} onChange={(e) => setPassword(e.target.value)} /></div>
          <div className="grid gap-1.5"><Label htmlFor="confirm-password">Confirm new password</Label><Input id="confirm-password" type="password" autoComplete="new-password" required minLength={8} maxLength={72} value={confirmation} onChange={(e) => setConfirmation(e.target.value)} /></div>
        </> : <div className="grid gap-1.5"><Label htmlFor="recovery-email">Account email</Label><Input id="recovery-email" type="email" autoComplete="email" required maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} /></div>}
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <Button type="submit" disabled={busy} className="h-10 w-full cv-action-primary">{busy ? "Please wait…" : reset ? "Save new password" : "Send reset link"}</Button>
        {reset && <p className="text-sm"><Link to="/forgot-password" className="underline">Request a new link</Link></p>}
      </form>}
  </AuthLayout>;
}
