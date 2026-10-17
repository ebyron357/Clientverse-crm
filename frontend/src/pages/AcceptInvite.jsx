import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatErr, setStoredToken } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { CLIENTVERSE_MODULES, isModuleActionable } from "@/platform/modules";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AlertCircle, ArrowRight, Ban, CheckCircle2, Clock, Link2Off, Loader2, LockKeyhole, Orbit, UserPlus } from "lucide-react";

const MIN_PASSWORD = 8;

// Where a new teammate lands: the Leads page when it is on the menu for their role,
// otherwise the Command Center.
function appHome(role) {
  const leads = CLIENTVERSE_MODULES.find((module) => module.route === "/leads");
  return leads && isModuleActionable(leads) && (!leads.adminOnly || role === "admin") ? "/leads" : "/dashboard";
}

const roleLabel = (role) => (role === "admin" ? "an admin" : "a team member");
const expiryLabel = (iso) => {
  const date = iso ? new Date(iso) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }) : null;
};

function Shell({ children }) {
  return (
    <div className="min-h-screen bg-[#f7fafc] px-4 py-10 sm:flex sm:items-center sm:justify-center sm:px-6">
      <div className="mx-auto w-full max-w-[440px]">
        <div className="mb-7 flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[#4ac4e0] to-[#1a9fbf]"><Orbit className="h-4 w-4 text-white" /></span>
          <span className="font-display text-lg font-extrabold text-[#0a1628]">ClientVerse</span>
        </div>
        <div className="cv-card p-6 sm:p-8" data-testid="accept-invite-card">{children}</div>
      </div>
    </div>
  );
}

function StatusPanel({ icon: Icon, tone = "slate", title, children, action, testid }) {
  const tones = { slate: "bg-slate-100 text-slate-500", red: "bg-red-50 text-red-500", emerald: "bg-emerald-50 text-emerald-600" };
  return (
    <div data-testid={testid}>
      <div className={`mb-4 flex h-10 w-10 items-center justify-center rounded-xl ${tones[tone]}`}><Icon className="h-5 w-5" /></div>
      <h1 className="font-display text-2xl font-extrabold tracking-[-0.03em] text-[#0a1628]">{title}</h1>
      <div className="mt-2 text-sm leading-6 text-slate-500">{children}</div>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

function ErrorNote({ children, testid }) {
  return <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-3 text-sm leading-5 text-red-700" role="alert" data-testid={testid}><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /><span>{children}</span></div>;
}

export default function AcceptInvite() {
  const { user, setUser, loading, checkAuth, logout } = useAuth();
  const navigate = useNavigate();
  const token = new URLSearchParams(window.location.search).get("token") || "";
  const [inv, setInv] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [existingAccount, setExistingAccount] = useState(false);
  const [form, setForm] = useState({ name: "", password: "", confirm: "" });

  const lookup = useCallback(async () => {
    if (!token) { setLoadError("missing"); return; }
    try { const { data } = await api.get("/team/invitations/lookup", { params: { token } }); setInv(data); }
    catch (e) { setLoadError(e.response?.status === 404 ? "missing" : formatErr(e.response?.data?.detail)); }
  }, [token]);
  useEffect(() => { lookup(); }, [lookup]);

  const loginHref = inv
    ? `/login?redirect=${encodeURIComponent(`/invite?token=${token}`)}&email=${encodeURIComponent(inv.email)}`
    : "/login";
  const inviter = inv?.invited_by_name || inv?.invited_by;

  // The invitation can change underneath an open page (revoked, resent, used elsewhere).
  // Re-read it so the page shows what is true now rather than a stale form.
  const refuse = async (e) => {
    setError(formatErr(e.response?.data?.detail));
    if (e.response?.status === 400 || e.response?.status === 404) await lookup();
  };

  const createAccount = async (event) => {
    event.preventDefault(); setError("");
    if (!form.name.trim()) { setError("Please enter your name."); return; }
    if (form.password.length < MIN_PASSWORD) { setError(`Your password needs at least ${MIN_PASSWORD} characters.`); return; }
    if (form.password !== form.confirm) { setError("The two passwords don't match. Please type them again."); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/team/invitations/accept-new", { token, name: form.name.trim(), password: form.password });
      if (data?.token) setStoredToken(data.token);
      setUser(data.user);
      navigate(appHome(data.role), { replace: true });
    } catch (e) {
      if (e.response?.status === 409) { setExistingAccount(true); setError(""); }
      else await refuse(e);
    } finally { setBusy(false); }
  };

  const accept = async () => {
    setBusy(true); setError("");
    try {
      const { data } = await api.post("/team/invitations/accept", { token });
      await checkAuth();
      navigate(appHome(data.role), { replace: true });
    } catch (e) { await refuse(e); }
    finally { setBusy(false); }
  };

  const switchAccount = async () => { setError(""); await logout(); };

  if (loadError) {
    return <Shell><StatusPanel icon={Link2Off} tone="red" title="This invitation link doesn't work" testid="invite-error" action={<Button variant="outline" className="h-11 w-full" onClick={() => navigate(user ? "/dashboard" : "/login")}>{user ? "Go to ClientVerse" : "Go to sign in"}</Button>}>
      {loadError === "missing"
        ? "It may be incomplete, already used, or replaced by a newer invitation. If you've already joined, just sign in. Otherwise, ask the person who invited you to send a new one."
        : loadError}
    </StatusPanel></Shell>;
  }
  if (!inv || loading) return <Shell><div className="flex items-center gap-2 text-sm text-slate-500" data-testid="invite-loading"><Loader2 className="h-4 w-4 animate-spin" />Opening your invitation…</div></Shell>;

  if (inv.status === "expired") {
    return <Shell><StatusPanel icon={Clock} title="This invitation has expired" testid="invite-expired">
      Invitations to join <span className="font-medium text-[#132038]">{inv.tenant_name}</span> last 7 days. Ask {inviter ? <span className="font-medium text-[#132038]">{inviter}</span> : "the person who invited you"} to send you a new one.
    </StatusPanel></Shell>;
  }
  if (inv.status === "revoked") {
    return <Shell><StatusPanel icon={Ban} tone="red" title="This invitation was cancelled" testid="invite-revoked">
      It can no longer be used. If you still need access to <span className="font-medium text-[#132038]">{inv.tenant_name}</span>, ask {inviter ? <span className="font-medium text-[#132038]">{inviter}</span> : "the person who invited you"} to invite you again.
    </StatusPanel></Shell>;
  }
  if (inv.status === "accepted") {
    const mine = user && user.email?.toLowerCase() === inv.email.toLowerCase();
    return <Shell><StatusPanel icon={CheckCircle2} tone="emerald" title={mine ? "You've already joined" : "This invitation has already been used"} testid="invite-already"
      action={mine
        ? <Button className="h-11 w-full cv-action-primary" onClick={() => navigate(appHome(user.role))}>Go to ClientVerse<ArrowRight className="ml-2 h-4 w-4" /></Button>
        : <Button variant="outline" className="h-11 w-full" onClick={() => navigate(`/login?email=${encodeURIComponent(inv.email)}`)}>Sign in</Button>}>
      {mine ? <>You're a member of <span className="font-medium text-[#132038]">{inv.tenant_name}</span>.</> : <>The account for <span className="font-medium text-[#132038]">{inv.email}</span> has been set up. Sign in to continue.</>}
    </StatusPanel></Shell>;
  }

  // pending
  const signedInAsInvitee = user && user.email?.toLowerCase() === inv.email.toLowerCase();
  return (
    <Shell>
      <div data-testid="invite-pending">
        <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-50 text-[#1a9fbf]"><UserPlus className="h-5 w-5" /></div>
        <div className="cv-eyebrow">You're invited</div>
        <h1 className="font-display text-3xl font-extrabold tracking-[-0.04em] text-[#0a1628]">Join {inv.tenant_name}</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500" data-testid="invite-summary">
          {inviter ? <><span className="font-medium text-[#132038]">{inviter}</span> invited you</> : "You've been invited"} to join as {roleLabel(inv.role)}.
        </p>

        {!user ? (
          existingAccount ? (
            <div className="mt-6 space-y-4" data-testid="invite-existing-account">
              <div className="rounded-xl border border-cyan-200 bg-cyan-50 px-4 py-3 text-sm leading-6 text-[#0f5f73]">You already have a ClientVerse account with <span className="font-semibold">{inv.email}</span>. Sign in and you'll come straight back here to join {inv.tenant_name}.</div>
              <Button className="h-11 w-full cv-action-primary" onClick={() => navigate(loginHref)} data-testid="invite-existing-signin">Sign in to accept<ArrowRight className="ml-2 h-4 w-4" /></Button>
              <button type="button" className="w-full text-center text-sm font-medium text-slate-500 hover:text-slate-700" onClick={() => setExistingAccount(false)}>Back</button>
            </div>
          ) : (
            <>
              <h2 className="mt-7 font-display text-lg font-bold text-[#0a1628]">Create your account</h2>
              <form onSubmit={createAccount} className="mt-4 space-y-4" data-testid="invite-signup-form" noValidate>
                <div className="grid gap-1.5"><Label htmlFor="invite-name">Your name</Label><Input id="invite-name" data-testid="invite-name-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoComplete="name" placeholder="First and last name" required /></div>
                <div className="grid gap-1.5">
                  <Label htmlFor="invite-email">Email</Label>
                  <div className="relative"><Input id="invite-email" data-testid="invite-email-input" value={inv.email} readOnly aria-readonly="true" autoComplete="username" className="bg-slate-50 pr-9 text-slate-600" /><LockKeyhole className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /></div>
                  <p className="text-xs text-slate-500">This is the address your invitation was sent to.</p>
                </div>
                <div className="grid gap-1.5"><Label htmlFor="invite-password">Create a password</Label><Input id="invite-password" type="password" data-testid="invite-password-input" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} autoComplete="new-password" required /><p className="text-xs text-slate-500">At least {MIN_PASSWORD} characters.</p></div>
                <div className="grid gap-1.5"><Label htmlFor="invite-password-confirm">Confirm password</Label><Input id="invite-password-confirm" type="password" data-testid="invite-password-confirm-input" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} autoComplete="new-password" required /></div>
                {error && <ErrorNote testid="invite-action-error">{error}</ErrorNote>}
                <Button type="submit" disabled={busy} className="h-11 w-full cv-action-primary" data-testid="invite-create-account">{busy ? "Creating your account…" : `Create account and join`}{!busy && <ArrowRight className="ml-2 h-4 w-4" />}</Button>
              </form>
              <p className="mt-6 text-center text-sm text-slate-500">Already have a ClientVerse account? <button type="button" onClick={() => navigate(loginHref)} className="font-semibold text-[#1a9fbf] hover:text-[#147f9a]" data-testid="invite-signin">Sign in</button></p>
            </>
          )
        ) : !signedInAsInvitee ? (
          <div className="mt-6 space-y-4" data-testid="invite-wrong-account">
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">You're signed in as <span className="font-semibold">{user.email}</span>, but this invitation is for <span className="font-semibold">{inv.email}</span>. Sign out to create that account or sign in with it.</div>
            <Button variant="outline" className="h-11 w-full" onClick={switchAccount} data-testid="invite-switch-account">Sign out and continue</Button>
          </div>
        ) : (
          <div className="mt-6 space-y-4">
            <p className="text-sm leading-6 text-slate-500">You're signed in as <span className="font-medium text-[#132038]">{user.email}</span>.</p>
            {error && <ErrorNote testid="invite-action-error">{error}</ErrorNote>}
            <Button className="h-11 w-full cv-action-primary" onClick={accept} disabled={busy} data-testid="invite-accept-button">{busy ? "Joining…" : `Accept and join ${inv.tenant_name}`}</Button>
          </div>
        )}

        {expiryLabel(inv.expires_at) && <p className="mt-6 border-t border-slate-100 pt-4 text-xs leading-5 text-slate-400">This invitation can be used once and expires on {expiryLabel(inv.expires_at)}.</p>}
      </div>
    </Shell>
  );
}
