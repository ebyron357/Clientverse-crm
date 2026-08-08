import { useEffect, useState, useCallback } from "react";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { UserPlus, Copy, RotateCw, Ban, ShieldAlert, Mail, CheckCircle2 } from "lucide-react";

const ROLE_BADGE = {
  admin: "bg-indigo-50 text-indigo-700 border-indigo-200",
  member: "bg-slate-50 text-slate-600 border-slate-200",
};
const STATUS_BADGE = {
  active: "bg-emerald-50 text-emerald-700 border-emerald-200",
  disabled: "bg-red-50 text-red-700 border-red-200",
  pending: "bg-amber-50 text-amber-700 border-amber-200",
  accepted: "bg-emerald-50 text-emerald-700 border-emerald-200",
  expired: "bg-gray-100 text-gray-500 border-gray-200",
  revoked: "bg-red-50 text-red-700 border-red-200 line-through",
};

export default function Team() {
  const { user } = useAuth();
  const [members, setMembers] = useState(null);
  const [invites, setInvites] = useState([]);
  const [forbidden, setForbidden] = useState(false);
  const [dialog, setDialog] = useState(false);
  const [form, setForm] = useState({ email: "", role: "member" });
  const [lastInvite, setLastInvite] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [m, i] = await Promise.all([api.get("/team/members"), api.get("/team/invitations")]);
      setMembers(m.data); setInvites(i.data); setForbidden(false);
    } catch (e) {
      if (e.response?.status === 403) { setForbidden(true); setMembers([]); }
      else toast.error(formatErr(e.response?.data?.detail));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const invite = async () => {
    if (!form.email.trim()) { toast.error("Email is required"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/team/invitations", { email: form.email.trim(), role: form.role });
      setLastInvite({ email: data.invitation.email, url: data.invite_url });
      setForm({ email: "", role: "member" });
      toast.success("Invitation created");
      load();
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  const resend = async (inv) => {
    try { const { data } = await api.post(`/team/invitations/${inv.id}/resend`); setLastInvite({ email: inv.email, url: data.invite_url }); setDialog(true); toast.success("New invite link generated"); load(); }
    catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  };
  const revoke = async (inv) => {
    try { await api.post(`/team/invitations/${inv.id}/revoke`); toast.success("Invitation revoked"); load(); }
    catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  };
  const changeRole = async (m, role) => {
    try { await api.patch(`/team/members/${m.user_id}/role`, { role }); toast.success(`${m.email} is now ${role}`); load(); }
    catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  };
  const toggleStatus = async (m) => {
    const status = m.status === "active" ? "disabled" : "active";
    try { await api.patch(`/team/members/${m.user_id}/status`, { status }); toast.success(status === "disabled" ? "Member disabled" : "Member re-enabled"); load(); }
    catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  };
  const copy = (t) => { navigator.clipboard?.writeText(t); toast.success("Invite link copied"); };

  if (forbidden) {
    return (
      <div className="max-w-lg mx-auto mt-20 text-center" data-testid="team-forbidden">
        <ShieldAlert className="w-10 h-10 mx-auto text-red-500 mb-4" />
        <h1 className="font-display text-2xl font-bold">Admins only</h1>
        <p className="text-sm text-gray-500 mt-2">Team management is restricted to workspace administrators.</p>
      </div>
    );
  }
  if (members === null) return <div className="space-y-4"><Skeleton className="h-10 w-64" /><Skeleton className="h-64 rounded-xl" /></div>;

  const pending = invites.filter((i) => i.status === "pending");
  const past = invites.filter((i) => i.status !== "pending");

  return (
    <div data-testid="team-page">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-display text-3xl font-bold">Team & Access</h1>
          <p className="text-sm text-gray-500 mt-1">Manage members, roles, and invitations for your tenant.</p>
        </div>
        <Button onClick={() => { setLastInvite(null); setDialog(true); }} className="bg-[#0A0A0A] hover:bg-[#262626]" data-testid="invite-member-button">
          <UserPlus className="w-4 h-4 mr-1" /> Invite member
        </Button>
      </div>

      {/* Members */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden mb-8" data-testid="members-table">
        <div className="px-6 py-4 border-b border-gray-100"><h3 className="font-display font-bold text-lg">Members ({members.length})</h3></div>
        <table className="w-full text-sm text-left">
          <thead><tr className="border-b border-gray-100 text-xs uppercase tracking-[0.05em] text-gray-500">
            <th className="px-6 py-3 font-semibold">Member</th><th className="px-6 py-3 font-semibold">Role</th><th className="px-6 py-3 font-semibold">Status</th><th className="px-6 py-3 font-semibold text-right">Actions</th></tr></thead>
          <tbody>
            {members.map((m) => {
              const isSelf = m.user_id === user?.user_id;
              return (
                <tr key={m.user_id} className="border-b border-gray-50" data-testid={`member-${m.user_id}`}>
                  <td className="px-6 py-3">
                    <div className="font-medium">{m.name || m.email}{isSelf && <span className="text-gray-400 font-normal"> (you)</span>}</div>
                    <div className="text-xs text-gray-400">{m.email}</div>
                  </td>
                  <td className="px-6 py-3">
                    <Select value={m.role} onValueChange={(v) => changeRole(m, v)} disabled={m.status !== "active"}>
                      <SelectTrigger className="h-8 w-28 text-xs" data-testid={`member-role-${m.user_id}`}><SelectValue /></SelectTrigger>
                      <SelectContent>{["admin", "member"].map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                    </Select>
                  </td>
                  <td className="px-6 py-3"><Badge className={`capitalize ${STATUS_BADGE[m.status]}`}>{m.status}</Badge></td>
                  <td className="px-6 py-3 text-right">
                    <Button size="sm" variant="outline" className="h-8" onClick={() => toggleStatus(m)} data-testid={`member-toggle-${m.user_id}`}>
                      {m.status === "active" ? <><Ban className="w-3.5 h-3.5 mr-1" />Disable</> : <><CheckCircle2 className="w-3.5 h-3.5 mr-1" />Enable</>}
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pending invitations */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden mb-8" data-testid="invitations-table">
        <div className="px-6 py-4 border-b border-gray-100"><h3 className="font-display font-bold text-lg">Pending invitations ({pending.length})</h3></div>
        {pending.length === 0 ? (
          <div className="px-6 py-10 text-center text-sm text-gray-400" data-testid="invitations-empty">No pending invitations. Invite a teammate to get started.</div>
        ) : (
          <table className="w-full text-sm text-left">
            <tbody>
              {pending.map((inv) => (
                <tr key={inv.id} className="border-b border-gray-50" data-testid={`invite-${inv.id}`}>
                  <td className="px-6 py-3"><div className="font-medium flex items-center gap-2"><Mail className="w-3.5 h-3.5 text-gray-400" />{inv.email}</div></td>
                  <td className="px-6 py-3"><Badge className={`capitalize ${ROLE_BADGE[inv.role]}`}>{inv.role}</Badge></td>
                  <td className="px-6 py-3 text-xs text-gray-400">invited by {inv.invited_by}</td>
                  <td className="px-6 py-3 text-right space-x-2">
                    <Button size="sm" variant="outline" className="h-8" onClick={() => resend(inv)} data-testid={`invite-resend-${inv.id}`}><RotateCw className="w-3.5 h-3.5 mr-1" />Resend</Button>
                    <Button size="sm" variant="outline" className="h-8" onClick={() => revoke(inv)} data-testid={`invite-revoke-${inv.id}`}><Ban className="w-3.5 h-3.5 mr-1" />Revoke</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Invite history */}
      {past.length > 0 && (
        <div className="text-xs text-gray-400" data-testid="invite-history">
          <span className="uppercase tracking-[0.06em] font-semibold text-gray-500">History: </span>
          {past.slice(0, 12).map((inv) => (
            <span key={inv.id} className="inline-flex items-center gap-1 mr-3">{inv.email} <Badge className={`capitalize text-[10px] ${STATUS_BADGE[inv.status]}`}>{inv.status}</Badge></span>
          ))}
        </div>
      )}

      {/* Invite dialog */}
      <Dialog open={dialog} onOpenChange={setDialog}>
        <DialogContent data-testid="invite-dialog">
          <DialogHeader><DialogTitle>{lastInvite ? "Invitation ready" : "Invite a member"}</DialogTitle></DialogHeader>
          {lastInvite ? (
            <div className="space-y-3 py-2">
              <p className="text-sm text-gray-600">Share this secure single-use link with <span className="font-medium">{lastInvite.email}</span>. They must sign in with that email to accept. The link expires in 7 days.</p>
              <div className="flex gap-2">
                <Input readOnly value={lastInvite.url} className="font-mono text-xs" data-testid="invite-link-value" />
                <Button size="sm" variant="outline" onClick={() => copy(lastInvite.url)} data-testid="copy-invite-link"><Copy className="w-3.5 h-3.5" /></Button>
              </div>
            </div>
          ) : (
            <div className="space-y-3 py-2">
              <div className="space-y-1"><Label>Email</Label><Input type="email" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} placeholder="teammate@company.com" data-testid="invite-email-input" /></div>
              <div className="space-y-1">
                <Label>Role</Label>
                <Select value={form.role} onValueChange={(v) => setForm((f) => ({ ...f, role: v }))}>
                  <SelectTrigger data-testid="invite-role-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{["member", "admin"].map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
          )}
          <DialogFooter>
            {lastInvite ? (
              <Button onClick={() => setDialog(false)} className="bg-[#0A0A0A]" data-testid="invite-done">Done</Button>
            ) : (
              <>
                <Button variant="outline" onClick={() => setDialog(false)}>Cancel</Button>
                <Button onClick={invite} disabled={busy} className="bg-[#0A0A0A]" data-testid="invite-submit">{busy ? "Sending…" : "Create invite"}</Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
