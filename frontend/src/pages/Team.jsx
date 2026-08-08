import { useCallback, useEffect, useState } from "react";
import { api, formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

export default function Team() {
  const { user } = useAuth();
  const admin = user?.role === "admin";
  const [members, setMembers] = useState([]);
  const [invites, setInvites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [inviteLink, setInviteLink] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [m, i] = await Promise.all([
        api.get("/team/members"),
        admin ? api.get("/team/invitations") : Promise.resolve({ data: [] }),
      ]);
      setMembers(m.data); setInvites(i.data);
    } catch (e) {
      if (e.response?.status === 403) setError("Unauthorized: your membership does not allow team access.");
      else setError(formatErr(e.response?.data?.detail));
    } finally { setLoading(false); }
  }, [admin]);

  useEffect(() => { load(); }, [load]);

  const invite = async (e) => {
    e.preventDefault(); setSubmitting(true); setError(""); setInviteLink("");
    try {
      const { data } = await api.post("/team/invitations", { email, role });
      const link = `${window.location.origin}${data.accept_path}`;
      setInviteLink(link); setEmail(""); toast.success("Invitation created"); await load();
    } catch (e2) { setError(formatErr(e2.response?.data?.detail)); }
    finally { setSubmitting(false); }
  };

  const resend = async (id) => {
    try { const { data } = await api.post(`/team/invitations/${id}/resend`); setInviteLink(`${window.location.origin}${data.accept_path}`); toast.success("Invitation resent"); await load(); }
    catch (e) { setError(formatErr(e.response?.data?.detail)); }
  };
  const revoke = async (id) => {
    try { await api.post(`/team/invitations/${id}/revoke`); toast.success("Invitation revoked"); await load(); }
    catch (e) { setError(formatErr(e.response?.data?.detail)); }
  };
  const changeRole = async (id, nextRole) => {
    try { await api.patch(`/team/members/${id}/role`, { role: nextRole }); toast.success("Role updated"); await load(); }
    catch (e) { setError(formatErr(e.response?.data?.detail)); }
  };
  const disable = async (id) => {
    try { await api.delete(`/team/members/${id}`); toast.success("Member disabled"); await load(); }
    catch (e) { setError(formatErr(e.response?.data?.detail)); }
  };

  if (loading) return <div className="text-sm text-gray-500">Loading team…</div>;
  return <div className="max-w-6xl mx-auto space-y-8" data-testid="team-page">
    <div><h1 className="text-3xl font-bold">Team / Members</h1><p className="text-sm text-gray-500 mt-1">Tenant-scoped access, roles, invitations, and membership status.</p></div>
    {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">{error}</div>}
    {admin && <section className="bg-white border rounded-xl p-5 space-y-4">
      <h2 className="font-semibold">Invite a teammate</h2>
      <form onSubmit={invite} className="flex flex-wrap gap-3">
        <input required type="email" value={email} onChange={(e)=>setEmail(e.target.value)} placeholder="name@example.com" className="border rounded-lg px-3 py-2 min-w-72" />
        <select value={role} onChange={(e)=>setRole(e.target.value)} className="border rounded-lg px-3 py-2"><option value="member">Member</option><option value="admin">Admin</option></select>
        <button disabled={submitting} className="bg-black text-white rounded-lg px-4 py-2 disabled:opacity-50">{submitting ? "Inviting…" : "Invite"}</button>
      </form>
      {inviteLink && <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-3 text-sm"><div className="font-medium">Invitation ready</div><div className="break-all text-emerald-800 mt-1">{inviteLink}</div></div>}
    </section>}
    <section className="bg-white border rounded-xl overflow-hidden">
      <div className="p-5 border-b"><h2 className="font-semibold">Members</h2></div>
      {members.length === 0 ? <div className="p-8 text-sm text-gray-500">No team members yet.</div> : <div className="divide-y">{members.map((m)=><div key={m.id} className="p-4 flex items-center justify-between gap-4">
        <div><div className="font-medium">{m.user?.name || m.user?.email || m.user_id}</div><div className="text-xs text-gray-500">{m.user?.email} · {m.status === "disabled" ? "Disabled member" : m.status}</div></div>
        <div className="flex items-center gap-2">{admin && m.status === "active" ? <select value={m.role} onChange={(e)=>changeRole(m.id,e.target.value)} className="border rounded px-2 py-1 text-sm"><option value="member">member</option><option value="admin">admin</option></select> : <span className="text-sm">{m.role}</span>}{admin && m.status === "active" && <button onClick={()=>disable(m.id)} className="text-sm border rounded px-2 py-1">Disable</button>}</div>
      </div>)}</div>}
    </section>
    {admin && <section className="bg-white border rounded-xl overflow-hidden"><div className="p-5 border-b"><h2 className="font-semibold">Invitations</h2></div>{invites.filter(i=>i.status==="pending").length===0 ? <div className="p-8 text-sm text-gray-500">No pending invitations.</div> : <div className="divide-y">{invites.filter(i=>i.status==="pending").map((i)=><div key={i.id} className="p-4 flex justify-between gap-4"><div><div className="font-medium">{i.email}</div><div className="text-xs text-gray-500">{i.role} · expires {new Date(i.expires_at).toLocaleString()}</div></div><div className="flex gap-2"><button onClick={()=>resend(i.id)} className="text-sm border rounded px-2 py-1">Resend</button><button onClick={()=>revoke(i.id)} className="text-sm border rounded px-2 py-1">Revoke</button></div></div>)}</div>}</section>}
  </div>;
}
