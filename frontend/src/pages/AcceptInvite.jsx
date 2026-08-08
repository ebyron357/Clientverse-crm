import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Orbit, ShieldAlert, CheckCircle2, Clock, Ban, Loader2 } from "lucide-react";

function Shell({ children }) {
  return (
    <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center p-6">
      <div className="w-full max-w-md bg-white rounded-2xl p-8 shadow-xl" data-testid="accept-invite-card">
        <div className="flex items-center gap-2 mb-6">
          <div className="w-8 h-8 rounded-lg bg-[#0A0A0A] flex items-center justify-center"><Orbit className="w-4 h-4 text-white" /></div>
          <span className="font-display font-extrabold text-lg">ClientVerse</span>
        </div>
        {children}
      </div>
    </div>
  );
}

export default function AcceptInvite() {
  const { user, loading, checkAuth } = useAuth();
  const navigate = useNavigate();
  const token = new URLSearchParams(window.location.search).get("token") || "";
  const [inv, setInv] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const lookup = useCallback(async () => {
    if (!token) { setError("This invitation link is invalid."); return; }
    try { const { data } = await api.get("/team/invitations/lookup", { params: { token } }); setInv(data); }
    catch (e) { setError(e.response?.status === 404 ? "This invitation could not be found." : formatErr(e.response?.data?.detail)); }
  }, [token]);
  useEffect(() => { lookup(); }, [lookup]);

  const accept = async () => {
    setBusy(true);
    try {
      await api.post("/team/invitations/accept", { token });
      await checkAuth();
      setDone(true);
    } catch (e) { setError(formatErr(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  const loginHref = `/login?redirect=${encodeURIComponent(`/invite?token=${token}`)}`;

  if (error && !inv) return <Shell><div data-testid="invite-error"><ShieldAlert className="w-8 h-8 text-red-500 mb-3" /><h1 className="font-display text-xl font-bold">Invitation unavailable</h1><p className="text-sm text-gray-500 mt-2">{error}</p><Button className="mt-6 bg-[#0A0A0A]" onClick={() => navigate("/dashboard")}>Go to app</Button></div></Shell>;
  if (!inv || loading) return <Shell><div className="flex items-center gap-2 text-sm text-gray-500" data-testid="invite-loading"><Loader2 className="w-4 h-4 animate-spin" />Loading invitation…</div></Shell>;

  if (done) return <Shell><div data-testid="invite-accepted-success"><CheckCircle2 className="w-8 h-8 text-emerald-500 mb-3" /><h1 className="font-display text-xl font-bold">You're in!</h1><p className="text-sm text-gray-500 mt-2">You joined <span className="font-medium">{inv.tenant_name}</span> as a {inv.role}.</p><Button className="mt-6 bg-[#0A0A0A]" onClick={() => navigate("/dashboard")} data-testid="invite-continue">Continue to workspace</Button></div></Shell>;

  if (inv.status === "expired") return <Shell><div data-testid="invite-expired"><Clock className="w-8 h-8 text-gray-400 mb-3" /><h1 className="font-display text-xl font-bold">Invitation expired</h1><p className="text-sm text-gray-500 mt-2">This invitation to join <span className="font-medium">{inv.tenant_name}</span> has expired. Ask an admin to resend it.</p></div></Shell>;
  if (inv.status === "revoked") return <Shell><div data-testid="invite-revoked"><Ban className="w-8 h-8 text-red-500 mb-3" /><h1 className="font-display text-xl font-bold">Invitation revoked</h1><p className="text-sm text-gray-500 mt-2">This invitation is no longer valid.</p></div></Shell>;
  if (inv.status === "accepted") return <Shell><div data-testid="invite-already"><CheckCircle2 className="w-8 h-8 text-emerald-500 mb-3" /><h1 className="font-display text-xl font-bold">Already accepted</h1><p className="text-sm text-gray-500 mt-2">This invitation has already been used.</p><Button className="mt-6 bg-[#0A0A0A]" onClick={() => navigate("/dashboard")}>Go to app</Button></div></Shell>;

  // pending
  return (
    <Shell>
      <div data-testid="invite-pending">
        <h1 className="font-display text-2xl font-bold">Join {inv.tenant_name}</h1>
        <p className="text-sm text-gray-500 mt-2">You've been invited to join as a <span className="font-medium capitalize">{inv.role}</span>. This invitation was sent to <span className="font-medium">{inv.email}</span>.</p>
        {error && <div className="text-sm text-red-600 mt-4" data-testid="invite-action-error">{error}</div>}
        {!user ? (
          <div className="mt-6">
            <p className="text-sm text-gray-500 mb-3">Sign in or create an account with <span className="font-medium">{inv.email}</span> to accept.</p>
            <Button className="w-full bg-[#0A0A0A]" onClick={() => navigate(loginHref)} data-testid="invite-signin">Sign in to accept</Button>
          </div>
        ) : user.email?.toLowerCase() !== inv.email.toLowerCase() ? (
          <div className="mt-6" data-testid="invite-wrong-account">
            <div className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3">You're signed in as <span className="font-medium">{user.email}</span>, but this invite is for <span className="font-medium">{inv.email}</span>. Sign in with the invited email to accept.</div>
            <Button variant="outline" className="w-full mt-4" onClick={() => navigate(loginHref)}>Switch account</Button>
          </div>
        ) : (
          <Button className="w-full bg-[#0A0A0A] mt-6" onClick={accept} disabled={busy} data-testid="invite-accept-button">{busy ? "Joining…" : `Accept & join ${inv.tenant_name}`}</Button>
        )}
      </div>
    </Shell>
  );
}
