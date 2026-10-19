import { useEffect, useState, useCallback } from "react";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Avatar, PageHeader, Section, StatusDot } from "@/components/page/Page";
import { UserPlus, Copy, RotateCw, Ban, ShieldAlert, Mail, MailCheck, CheckCircle2, KeyRound, MoreHorizontal, Users } from "lucide-react";

const STATUS_TONE = {
  active: "success",
  disabled: "danger",
  pending: "warning",
  accepted: "success",
  expired: "neutral",
  revoked: "danger",
};
const ROLE_HELP = {
  member: "Can use the CRM day to day.",
  admin: "Can also invite people, change roles, and manage settings.",
};
const EMAIL_NOTE = {
  sent: "Emailed",
  failed: "Email didn't send — share the link",
};
const capitalize = (value = "") => value.charAt(0).toUpperCase() + value.slice(1);
const formatDate = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "—");

// What the admin is told after creating or resending an invitation. Only a send the
// server confirmed counts as emailed.
function inviteMessage(invite) {
  if (invite.emailed) return <>Invitation emailed to <span className="font-medium text-foreground">{invite.email}</span>. You can also copy the link:</>;
  if (invite.emailConfigured) return <>We couldn't email <span className="font-medium text-foreground">{invite.email}</span> just now. Copy this link and send it to them:</>;
  return <>Copy this link and send it to <span className="font-medium text-foreground">{invite.email}</span>:</>;
}

const TH = "h-9 px-3 text-left text-xs font-medium text-muted-foreground sm:px-4";

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
      setMembers(m.data);
      setInvites(i.data);
      setForbidden(false);
    } catch (e) {
      if (e.response?.status === 403) {
        setForbidden(true);
        setMembers([]);
      } else toast.error(formatErr(e.response?.data?.detail));
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const invite = async () => {
    if (!form.email.trim()) {
      toast.error("Email is required");
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.post("/team/invitations", { email: form.email.trim(), role: form.role });
      setLastInvite({ email: data.invitation.email, url: data.invite_url, emailed: data.emailed, emailConfigured: data.email_configured });
      setForm({ email: "", role: "member" });
      toast.success(data.emailed ? "Invitation emailed" : "Invitation created");
      load();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };
  const resend = async (inv) => {
    try {
      const { data } = await api.post(`/team/invitations/${inv.id}/resend`);
      setLastInvite({ email: inv.email, url: data.invite_url, emailed: data.emailed, emailConfigured: data.email_configured, resent: true });
      setDialog(true);
      toast.success(data.emailed ? "Invitation emailed again" : "New invite link ready");
      load();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail));
    }
  };
  const revoke = async (inv) => {
    try {
      await api.post(`/team/invitations/${inv.id}/revoke`);
      toast.success("Invitation revoked");
      load();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail));
    }
  };
  const changeRole = async (m, role) => {
    try {
      await api.patch(`/team/members/${m.user_id}/role`, { role });
      toast.success(`${m.email} is now ${role}`);
      load();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail));
    }
  };
  const toggleStatus = async (m) => {
    const status = m.status === "active" ? "disabled" : "active";
    try {
      await api.patch(`/team/members/${m.user_id}/status`, { status });
      toast.success(status === "disabled" ? "Member disabled" : "Member re-enabled");
      load();
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail));
    }
  };
  const resetPassword = async () => {
    setReset((current) => ({ ...current, busy: true }));
    try {
      const { data } = await api.post(`/team/members/${reset.member.user_id}/reset-password`);
      setReset((current) => ({ ...current, busy: false, temporary: data.temporary_password }));
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail));
      setReset(null);
    }
  };
  const copyTemporary = async (t) => {
    try {
      await navigator.clipboard.writeText(t);
      toast.success("Temporary password copied");
    } catch {
      toast.error("Couldn't copy automatically. Select the password and copy it.");
    }
  };
  const copy = async (t) => {
    try {
      await navigator.clipboard.writeText(t);
      toast.success("Invite link copied");
    } catch {
      toast.error("Couldn't copy automatically. Select the link and copy it.");
    }
  };

  if (forbidden) {
    return (
      <div className="cv-page" data-testid="team-forbidden">
        <div className="mx-auto mt-16 flex max-w-sm flex-col items-center text-center">
          <span className="flex size-10 items-center justify-center rounded-full bg-red-50">
            <ShieldAlert className="size-[18px] text-red-600" aria-hidden="true" />
          </span>
          <h1 className="mt-3 text-sm font-semibold text-foreground">Admins only</h1>
          <p className="mt-1 text-[13px] text-muted-foreground">Team management is restricted to workspace administrators.</p>
        </div>
      </div>
    );
  }
  if (members === null)
    return (
      <div className="cv-page space-y-5">
        <div className="space-y-2"><Skeleton className="h-7 w-48" /><Skeleton className="h-4 w-80 max-w-full" /></div>
        <Skeleton className="h-48 rounded-xl" />
      </div>
    );

  const pending = invites.filter((i) => i.status === "pending");
  const past = invites.filter((i) => i.status !== "pending");

  return (
    <div className="cv-page" data-testid="team-page">
      <PageHeader
        icon={Users}
        title="Team & Access"
        count={members.length}
        description="Invite teammates, choose what they can do, and switch off access when they leave."
        actions={
          <Button size="sm" onClick={() => { setLastInvite(null); setDialog(true); }} data-testid="invite-member-button">
            <UserPlus aria-hidden="true" />Invite
          </Button>
        }
      />

      {/* Members */}
      <div className="overflow-hidden rounded-xl border border-border bg-card" data-testid="members-table">
        <div className="relative overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className={TH}>Member</th>
                <th className={TH}>Role</th>
                <th className={`${TH} hidden sm:table-cell`}>Status</th>
                <th className={`${TH} hidden md:table-cell`}>Joined</th>
                <th className={`${TH} w-12`}><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {members.map((m) => {
                const isSelf = m.user_id === user?.user_id;
                const display = m.name || m.email;
                return (
                  <tr key={m.user_id} className="border-b border-border/70 transition-colors last:border-0 hover:bg-muted/50" data-testid={`member-${m.user_id}`}>
                    <td className="px-3 py-2.5 sm:px-4">
                      <div className="flex min-w-0 items-center gap-2.5">
                        <Avatar name={display} size="sm" />
                        <div className="min-w-0 max-w-[140px] sm:max-w-none">
                          <div className="truncate font-medium text-foreground">
                            {display}
                            {isSelf && <span className="font-normal text-muted-foreground"> (you)</span>}
                          </div>
                          <div className="truncate text-xs text-muted-foreground">{m.email}</div>
                          <div className="mt-0.5 sm:hidden"><StatusDot tone={STATUS_TONE[m.status]} className="text-xs">{capitalize(m.status)}</StatusDot></div>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-2.5 sm:px-4">
                      <Select value={m.role} onValueChange={(v) => changeRole(m, v)} disabled={m.status !== "active"}>
                        <SelectTrigger aria-label={`Role for ${display}`} className="-ml-2 h-7 w-auto gap-1.5 border-transparent bg-transparent px-2 text-[13px] capitalize shadow-none hover:bg-muted focus:ring-1" data-testid={`member-role-${m.user_id}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {["admin", "member"].map((r) => (
                            <SelectItem key={r} value={r} className="capitalize">{r}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className="hidden px-3 py-2.5 sm:px-4 sm:table-cell"><StatusDot tone={STATUS_TONE[m.status]}>{capitalize(m.status)}</StatusDot></td>
                    <td className="tabular hidden px-3 py-2.5 sm:px-4 text-muted-foreground md:table-cell">{formatDate(m.accepted_at || m.created_at)}</td>
                    <td className="px-3 py-2.5 sm:px-4 text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="size-7 text-muted-foreground" aria-label={`Actions for ${display}`} data-testid={`member-actions-${m.user_id}`}>
                            <MoreHorizontal aria-hidden="true" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-48">
                          {!isSelf && m.status === "active" && (
                            <>
                              <DropdownMenuItem onSelect={() => setReset({ member: m })} className="text-[13px]" data-testid={`member-reset-password-${m.user_id}`}>
                                <KeyRound aria-hidden="true" />Reset password
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                            </>
                          )}
                          <DropdownMenuItem onSelect={() => toggleStatus(m)} className={`text-[13px] ${m.status === "active" ? "text-red-700 focus:text-red-700" : ""}`} data-testid={`member-toggle-${m.user_id}`}>
                            {m.status === "active" ? <><Ban aria-hidden="true" />Disable access</> : <><CheckCircle2 aria-hidden="true" />Enable access</>}
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pending invitations */}
      <Section
        className="mt-8"
        title={<span className="flex items-center gap-2">Pending invitations<span className="tabular rounded-md bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground">{pending.length}</span></span>}
      >
        <div className="overflow-hidden rounded-xl border border-border bg-card" data-testid="invitations-table">
          {pending.length === 0 ? (
            <div className="flex flex-col items-center px-6 py-10 text-center" data-testid="invitations-empty">
              <span className="flex size-10 items-center justify-center rounded-full bg-muted"><Mail className="size-[18px] text-muted-foreground" aria-hidden="true" /></span>
              <p className="mt-3 text-sm font-medium text-foreground">No pending invitations</p>
              <p className="mt-1 text-[13px] text-muted-foreground">Invite a teammate to get started.</p>
            </div>
          ) : (
            <div className="relative overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-border bg-muted/40">
                    <th className={TH}>Email</th>
                    <th className={`${TH} hidden sm:table-cell`}>Role</th>
                    <th className={`${TH} hidden md:table-cell`}>Delivery</th>
                    <th className={TH}><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {pending.map((inv) => (
                    <tr key={inv.id} className="border-b border-border/70 transition-colors last:border-0 hover:bg-muted/50" data-testid={`invite-${inv.id}`}>
                      <td className="px-3 py-2.5 sm:px-4">
                        <div className="flex min-w-0 items-center gap-2.5">
                          <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted"><Mail className="size-3.5 text-muted-foreground" aria-hidden="true" /></span>
                          <span className="max-w-[170px] truncate font-medium text-foreground sm:max-w-none">{inv.email}</span>
                        </div>
                      </td>
                      <td className="hidden px-3 py-2.5 sm:px-4 sm:table-cell"><StatusDot tone={inv.role === "admin" ? "brand" : "neutral"}>{capitalize(inv.role)}</StatusDot></td>
                      <td className="hidden px-3 py-2.5 sm:px-4 text-xs text-muted-foreground md:table-cell">
                        <div className="flex flex-wrap items-center gap-x-1.5">
                          {EMAIL_NOTE[inv.email_status] && (
                            <span className={`inline-flex items-center gap-1 ${inv.email_status === "sent" ? "text-emerald-700" : "text-amber-700"}`} data-testid={`invite-email-status-${inv.id}`}>
                              {inv.email_status === "sent" && <MailCheck className="size-3.5" aria-hidden="true" />}
                              {EMAIL_NOTE[inv.email_status]} ·
                            </span>
                          )}
                          <span>invited by {inv.invited_by}</span>
                        </div>
                      </td>
                      <td className="px-3 py-2.5 sm:px-4">
                        <div className="flex justify-end gap-1.5">
                          <Button size="sm" variant="outline" className="h-7 px-2 sm:px-3" onClick={() => resend(inv)} data-testid={`invite-resend-${inv.id}`}>
                            <RotateCw aria-hidden="true" /><span className="sr-only sm:not-sr-only">Resend</span>
                          </Button>
                          <Button size="sm" variant="ghost" className="h-7 px-2 text-muted-foreground sm:px-3" onClick={() => revoke(inv)} data-testid={`invite-revoke-${inv.id}`}>
                            <Ban aria-hidden="true" /><span className="sr-only sm:not-sr-only">Revoke</span>
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Section>

      {/* Invite history */}
      {past.length > 0 && (
        <div className="mt-6" data-testid="invite-history">
          <h2 className="mb-2 text-xs font-medium text-muted-foreground">Invitation history</h2>
          <div className="flex flex-wrap gap-1.5">
            {past.slice(0, 12).map((inv) => (
              <span key={inv.id} className="inline-flex items-center gap-2 rounded-md border border-border/70 bg-card px-2 py-1 text-xs text-foreground/80">
                <span className="max-w-[14rem] truncate">{inv.email}</span>
                <StatusDot tone={STATUS_TONE[inv.status]} className={`text-xs ${inv.status === "revoked" ? "line-through" : ""}`}>{capitalize(inv.status)}</StatusDot>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Reset a teammate's password */}
      <Dialog open={Boolean(reset)} onOpenChange={(open) => !open && setReset(null)}>
        <DialogContent data-testid="reset-password-dialog">
          <DialogHeader>
            <DialogTitle>{reset?.temporary ? "Temporary password ready" : `Reset ${reset?.member?.name || reset?.member?.email}'s password?`}</DialogTitle>
            <DialogDescription>
              {reset?.temporary ? (
                <>
                  Send this to <span className="font-medium text-foreground">{reset.member.email}</span> by text or phone. When they sign in with it,
                  ClientVerse asks them to choose their own password straight away. It is shown only once.
                </>
              ) : (
                "They'll be signed out everywhere and get a temporary password from you. Their leads, tasks and history stay exactly as they are."
              )}
            </DialogDescription>
          </DialogHeader>
          {reset?.temporary ? (
            <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-3 py-2.5">
              <code className="flex-1 select-all font-mono text-base tracking-wide text-foreground" data-testid="temporary-password">{reset.temporary}</code>
              <Button size="sm" variant="outline" onClick={() => copyTemporary(reset.temporary)}>
                <Copy aria-hidden="true" />Copy
              </Button>
            </div>
          ) : null}
          <DialogFooter>
            {reset?.temporary ? (
              <Button size="sm" onClick={() => setReset(null)}>Done</Button>
            ) : (
              <>
                <Button size="sm" variant="outline" onClick={() => setReset(null)}>Cancel</Button>
                <Button size="sm" onClick={resetPassword} disabled={reset?.busy} data-testid="reset-password-confirm">
                  {reset?.busy ? "Resetting…" : "Reset password"}
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Invite dialog */}
      <Dialog open={dialog} onOpenChange={setDialog}>
        <DialogContent data-testid="invite-dialog">
          <DialogHeader>
            <DialogTitle>
              {lastInvite ? (lastInvite.emailed ? "Invitation sent" : lastInvite.resent ? "New invitation link" : "Invitation ready") : "Invite a teammate"}
            </DialogTitle>
            {!lastInvite && <DialogDescription>They'll get a link to create their account and join your workspace.</DialogDescription>}
          </DialogHeader>
          {lastInvite ? (
            <div className="space-y-3 py-1" data-testid="invite-result">
              <p className="text-[13px] leading-6 text-muted-foreground" data-testid="invite-result-message">{inviteMessage(lastInvite)}</p>
              <div className="flex gap-2">
                <Input readOnly value={lastInvite.url} onFocus={(e) => e.target.select()} className="h-9 font-mono text-xs" data-testid="invite-link-value" aria-label="Invitation link" />
                <Button size="sm" variant="outline" className="h-9 shrink-0" onClick={() => copy(lastInvite.url)} data-testid="copy-invite-link">
                  <Copy aria-hidden="true" />Copy
                </Button>
              </div>
              <p className="text-xs leading-5 text-muted-foreground">
                The link works once and expires in 7 days.{lastInvite.resent && " Any earlier link for this person no longer works."}
              </p>
            </div>
          ) : (
            <form id="invite-form" className="space-y-4 py-1" onSubmit={(e) => { e.preventDefault(); invite(); }}>
              <div className="space-y-1.5">
                <Label htmlFor="invite-email">Their email</Label>
                <Input id="invite-email" type="email" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} placeholder="teammate@company.com" autoComplete="off" className="h-9" data-testid="invite-email-input" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="invite-role">What they can do</Label>
                <Select value={form.role} onValueChange={(v) => setForm((f) => ({ ...f, role: v }))}>
                  <SelectTrigger id="invite-role" aria-label="What they can do" data-testid="invite-role-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {["member", "admin"].map((r) => (
                      <SelectItem key={r} value={r}>{r === "admin" ? "Admin" : "Member"}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground" data-testid="invite-role-help">{ROLE_HELP[form.role]}</p>
              </div>
            </form>
          )}
          <DialogFooter>
            {lastInvite ? (
              <Button size="sm" onClick={() => setDialog(false)} data-testid="invite-done">Done</Button>
            ) : (
              <>
                <Button size="sm" variant="outline" onClick={() => setDialog(false)}>Cancel</Button>
                <Button size="sm" type="submit" form="invite-form" disabled={busy} data-testid="invite-submit">
                  {busy ? "Creating…" : "Create invite"}
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
