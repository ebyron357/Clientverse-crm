import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, formatErr } from "@/lib/api";

export default function InviteAccept() {
  const { token } = useParams(); const navigate = useNavigate();
  const [state, setState] = useState({ loading: true, message: "Accepting invitation…", kind: "loading" });
  useEffect(() => { let live = true; (async()=>{ try { await api.post(`/team/invitations/accept/${token}`); if (live) setState({loading:false,message:"Invitation accepted. Your tenant membership is active.",kind:"success"}); } catch(e) { const detail = formatErr(e.response?.data?.detail); const kind = detail.toLowerCase().includes("expired") ? "expired" : detail.toLowerCase().includes("revoked") ? "revoked" : e.response?.status===403 ? "unauthorized" : "error"; if(live) setState({loading:false,message:detail,kind}); } })(); return()=>{live=false}; }, [token]);
  return <div className="min-h-screen bg-[#FAFAFA] flex items-center justify-center p-6"><div className="bg-white border rounded-xl p-8 max-w-lg w-full"><h1 className="text-2xl font-bold">Team invitation</h1><p className={`mt-3 text-sm ${state.kind==="success"?"text-emerald-700":state.kind==="loading"?"text-gray-500":"text-red-700"}`}>{state.message}</p>{state.kind==="success"&&<button onClick={()=>{window.location.href="/team"}} className="mt-5 bg-black text-white rounded-lg px-4 py-2">Open Team</button>}{!state.loading&&state.kind!=="success"&&<button onClick={()=>navigate("/dashboard")} className="mt-5 border rounded-lg px-4 py-2">Back to dashboard</button>}</div></div>;
}
