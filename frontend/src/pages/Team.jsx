import { useEffect, useState, useCallback } from "react";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { UserPlus, Copy, RotateCw, Ban, ShieldAlert, Mail, MailCheck, CheckCircle2, KeyRound } from "lucide-react";

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
const ROLE_HELP = {
  member: "Can use the CRM day to day.",
  admin: "Can also invite people, change roles, and manage settings.",
};
const EMAIL_NOTE = {
  sent: "Emailed",
  failed: "Email didn't send — share the link",
};

// What the admin is told after creating or resending an invitation. Only a send the
// server confirmed counts as emailed.
function inviteMessage(invite) {
  if (invite.emailed) return <>Invitation emailed to <span className="font-medium text-[#132038]">{invite.email}</span>. You can also copy the link:</>;
  if (invite.emailConfigured) return <>We couldn't email <span className="font-medium text-[#132038]">{invite.email}</span> just now. Copy this link and send it to them:</>;
  return <>Copy this link and send it to <span className="font-medium text-[#132038]">{invite.email}</span>:</>;
}

export default function Team() {
  const { user } = useAuth();
  const [members, setMembers] = useState(null);
  const [invites, setInvites] = useState([]);
  const [forbidden, setForbidden] = useState(false);
  const [dialog, setDialog] = useState(false);
  const [form, setForm] = useState({ email: "", role: "member" });
  const [lastInvite, setLastInvite] = useState(null);
  const [busy, setBusy] = useState(false);
  // A teammate who forgot their password: confirm, then show the temporary one once.
  const [reset, setReset] = useState(null);

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
      setLastInvite({ email: data.invitation.email, url: data.invite_url, emailed: data.emailed, emailConfigured: data.email_configured });
      setForm({ email: "", role: "member" });
      toast.success(data.emailed ? "Invitation emailed" : "Invitation created");
      load();
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  const resend = async (inv) => {
    try { const { data } = await api.post(`/team/invitations/${inv.id}/resend`); setLastInvite({ email: inv.email, url: data.invite_url, emailed: data.emailed, emailConfigured: data.email_configured, resent: true }); setDialog(true); toast.success(data.emailed ? "Invitation emailed again" : "New invite link ready"); load(); }
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
  const resetPassword = async () => {
    setReset((current) => ({ ...current, busy: true }));
    try {
      const { data } = await api.post(`/team/members/${reset.member.user_id}/reset-password`);
      setReset((current) => ({ ...current, busy: false, temporary: data.temporary_password }));
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); setReset(null); }
  };
  const copyTemporary = async (t) => {
    try { await navigator.clipboard.writeText(t); toast.success("Temporary password copied"); }
    catch { toast.error("Couldn't copy automatically. Select the password and copy it."); }
  };
  const copy = async (t) => {
    try { await navigator.clipboard.writeText(t); toast.success("Invite link copied"); }
    catch { toast.error("Couldn't copy automatically. Select the link and copy it."); }
  };

  if (forbidden) {
    return (
      <div className="cv-page max-w-lg mx-auto mt-20 text-center" data-testid="team-forbidden">
        <ShieldAlert className="w-10 h-10 mx-auto text-red-500 mb-4" />
        <h1 className="font-display text-2xl font-bold">Admins only</h1>
        <p className="text-sm text-gray-500 mt-2">Team management is restricted to workspace administrators.</p>
      </div>
    );
  }
  if (members === null) return <div className="cv-page space-y-4"><Skeleton className="h-10 w-64" /><Skeleton className="h-64 rounded-xl" /></div>;

  const pending = invites.filter((i) => i.status === "pending");
  const past = invites.filter((i) => i.status !== "pending");

  return (
    <div className="cv-page" data-testid="team-page">
      <div className="cv-page-header">
        <div>
          <div className="cv-eyebrow">Your team</div>
          <h1 className="cv-page-title">Team & Access</h1>
          <p className="cv-page-description">Invite an assistant or teammate, choose what they can do, and switch off someone's access when they leave.</p>
        </div>
        <Button onClick={() => { setLastInvite(null); setDialog(true); }} className="cv-action-primary" data-testid="invite-member-button">
          <UserPlus className="w-4 h-4 mr-1" /> Invite teammate
        </Button>
      </div>

      {/* Members */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-x-auto mb-8" data-testid="members-table">
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
                    {!isSelf && m.status === "active" && (
                      <Button size="sm" variant="outline" className="mr-2 h-8" onClick={() => setReset({ member: m })} data-testid={`member-reset-password-${m.user_id}`}>
                        <KeyRound className="w-3.5 h-3.5 mr-1" />Reset password
                      </Button>
                    )}
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
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-x-auto mb-8" data-testid="invitations-table">
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
                  <td className="px-6 py-3 text-xs text-gray-400">
                    <div className="flex flex-wrap items-center gap-x-1.5">
                      {EMAIL_NOTE[inv.email_status] && <span className={`inline-flex items-center gap-1 ${inv.email_status === "sent" ? "text-emerald-700" : "text-amber-700"}`} data-testid={`invite-email-status-${inv.id}`}>{inv.email_status === "sent" && <MailCheck className="w-3.5 h-3.5" />}{EMAIL_NOTE[inv.email_status]} ·</span>}
                      <span>invited by {inv.invited_by}</span>
                    </div>
                  </td>
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

      {/* Reset a teammate's password */}
      <Dialog open={Boolean(reset)} onOpenChange={(open) => !open && setReset(null)}>
        <DialogContent data-testid="reset-password-dialog">
          <DialogHeader>
            <DialogTitle>{reset?.temporary ? "Temporary password ready" : `Reset ${reset?.member?.name || reset?.member?.email}'s password?`}</DialogTitle>
            <DialogDescription>
              {reset?.temporary
                ? <>Send this to <span className="font-medium text-[#132038]">{reset.member.email}</span> by text or phone. When they sign in with it, ClientVerse asks them to choose their own password straight away. It is shown only once.</>
                : "They'll be signed out everywhere and get a temporary password from you. Their leads, tasks and history stay exactly as they are."}
            </DialogDescription>
          </DialogHeader>
          {reset?.temporary ? (
            <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-3">
              <code className="flex-1 select-all font-mono text-base tracking-wide text-[#0a1628]" data-testid="temporary-password">{reset.temporary}</code>
              <Button size="sm" variant="outline" onClick={() => copyTemporary(reset.temporary)}><Copy className="w-3.5 h-3.5 mr-1" />Copy</Button>
            </div>
          ) : null}
          <DialogFooter>
            {reset?.temporary
              ? <Button className="cv-action-primary" onClick={() => setReset(null)}>Done</Button>
              : <><Button variant="outline" onClick={() => setReset(null)}>Cancel</Button><Button className="cv-action-primary" onClick={resetPassword} disabled={reset?.busy} data-testid="reset-password-confirm">{reset?.busy ? "Resetting…" : "Reset password"}</Button></>}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Invite dialog */}
      <Dialog open={dialog} onOpenChange={setDialog}>
        <DialogContent data-testid="invite-dialog">
          <DialogHeader>
            <DialogTitle>{lastInvite ? (lastInvite.emailed ? "Invitation sent" : lastInvite.resent ? "New invitation link" : "Invitation ready") : "Invite a teammate"}</DialogTitle>
            {!lastInvite && <DialogDescription>They'll get a link to create their account and join your workspace.</DialogDescription>}
          </DialogHeader>
          {lastInvite ? (
            <div className="space-y-3 py-2" data-testid="invite-result">
              <p className="text-sm leading-6 text-gray-600" data-testid="invite-result-message">{inviteMessage(lastInvite)}</p>
              <div className="flex gap-2">
                <Input readOnly value={lastInvite.url} onFocus={(e) => e.target.select()} className="font-mono text-xs" data-testid="invite-link-value" aria-label="Invitation link" />
                <Button size="sm" variant="outline" className="h-9 shrink-0" onClick={() => copy(lastInvite.url)} data-testid="copy-invite-link"><Copy className="w-3.5 h-3.5 mr-1" />Copy</Button>
              </div>
              <p className="text-xs leading-5 text-gray-500">The link works once and expires in 7 days.{lastInvite.resent && " Any earlier link for this person no longer works."}</p>
            </div>
          ) : (
            <form id="invite-form" className="space-y-4 py-2" onSubmit={(e) => { e.preventDefault(); invite(); }}>
              <div className="space-y-1.5"><Label htmlFor="invite-email">Their email</Label><Input id="invite-email" type="email" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} placeholder="teammate@company.com" autoComplete="off" data-testid="invite-email-input" /></div>
              <div className="space-y-1.5">
                <Label htmlFor="invite-role">What they can do</Label>
                <Select value={form.role} onValueChange={(v) => setForm((f) => ({ ...f, role: v }))}>
                  <SelectTrigger id="invite-role" data-testid="invite-role-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{["member", "admin"].map((r) => <SelectItem key={r} value={r}>{r === "admin" ? "Admin" : "Member"}</SelectItem>)}</SelectContent>
                </Select>
                <p className="text-xs text-gray-500" data-testid="invite-role-help">{ROLE_HELP[form.role]}</p>
              </div>
            </form>
          )}
          <DialogFooter>
            {lastInvite ? (
              <Button onClick={() => setDialog(false)} className="cv-action-primary" data-testid="invite-done">Done</Button>
            ) : (
              <>
                <Button variant="outline" onClick={() => setDialog(false)}>Cancel</Button>
                <Button type="submit" form="invite-form" disabled={busy} className="cv-action-primary" data-testid="invite-submit">{busy ? "Creating…" : "Create invite"}</Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
