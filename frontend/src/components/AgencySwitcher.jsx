/* Agency accounts in the app shell: the account switcher at the top of the menu, and the
   banner that says which client account an agency admin is working in. Switching starts a
   new session for the chosen account and reloads, so no page keeps the old account's data. */

import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr, setStoredToken } from "@/lib/api";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { ArrowLeft, Building2, Check, ChevronsUpDown, Settings2 } from "lucide-react";

async function switchTo(request, path, failure) {
  try {
    const { data } = await request();
    setStoredToken(data.token);
    window.location.assign(path);
  } catch (requestError) {
    toast.error(failure, { description: formatErr(requestError.response?.data?.detail) });
  }
}

export const openClientAccount = (account) => switchTo(() => api.post(`/agency/accounts/${account.tenant_id}/enter`), "/dashboard", `“${account.name}” could not be opened`);
export const backToAgency = () => switchTo(() => api.post("/agency/leave"), "/settings/agency", "You could not be switched back");

/** Whether this person runs client accounts: an admin of an agency, in it or in one of its clients. */
export const isAgencyAdmin = (user) => Boolean(user?.acting) || (user?.role === "admin" && user?.workspace?.kind === "agency");

export function AccountSwitcher({ user, collapsed }) {
  const [accounts, setAccounts] = useState(null);
  if (!isAgencyAdmin(user)) return null;
  const acting = user.acting;
  const current = acting ? acting.name : user.workspace?.name;
  const agencyName = acting ? acting.agency_name : user.workspace?.name;
  const load = async (open) => {
    if (!open || accounts) return;
    try { const { data } = await api.get("/agency/accounts"); setAccounts(data.items || []); } catch { setAccounts([]); }
  };
  return <div className={`shrink-0 pb-2 ${collapsed ? "px-2" : "px-3"}`}>
    <DropdownMenu onOpenChange={load}>
      <DropdownMenuTrigger asChild>
        <button type="button" className={`flex w-full items-center gap-2 rounded-lg border border-sidebar-border text-left transition-colors hover:bg-sidebar-hover ${collapsed ? "justify-center p-2" : "px-2.5 py-2"}`}
          aria-label={`Account: ${current}. Switch account`} title={collapsed ? current : undefined} data-testid="account-switcher">
          <Building2 className="size-4 shrink-0 text-sidebar-muted" aria-hidden="true" />
          {!collapsed && <>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-semibold text-sidebar-active-foreground">{current}</span>
              <span className="block truncate text-[11px] text-sidebar-muted">{acting ? "Client account" : "Agency"}</span>
            </span>
            <ChevronsUpDown className="size-3.5 shrink-0 text-sidebar-muted" aria-hidden="true" />
          </>}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel className="text-xs font-medium text-muted-foreground">Agency</DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => { if (acting) backToAgency(); }} data-testid="account-switcher-agency">
          <span className="min-w-0 flex-1 truncate">{agencyName}</span>{!acting && <Check className="size-3.5" aria-hidden="true" />}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-xs font-medium text-muted-foreground">Client accounts</DropdownMenuLabel>
        <div className="max-h-72 overflow-y-auto">
          {accounts === null ? <div className="px-2 py-1.5 text-xs text-muted-foreground">Loading…</div>
            : !accounts.length ? <div className="px-2 py-1.5 text-xs text-muted-foreground">None yet</div>
            : accounts.map((account) => <DropdownMenuItem key={account.tenant_id} onSelect={() => { if (acting?.tenant_id !== account.tenant_id) openClientAccount(account); }} data-testid={`account-switcher-${account.tenant_id}`}>
                <span className="min-w-0 flex-1 truncate">{account.name}</span>{acting?.tenant_id === account.tenant_id && <Check className="size-3.5" aria-hidden="true" />}
              </DropdownMenuItem>)}
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild><Link to="/settings/agency"><Settings2 className="size-3.5" />Manage client accounts</Link></DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  </div>;
}

export function ActingBanner({ user }) {
  if (!user?.acting) return null;
  return <div className="cv-page mb-4 pb-0" role="status" data-testid="acting-banner">
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border border-brand/30 bg-brand-soft px-3 py-2 text-[13px] text-foreground">
      <Building2 className="size-4 shrink-0 text-brand-strong" aria-hidden="true" />
      <span className="min-w-0 flex-1">You are working in <span className="font-semibold">{user.acting.name}</span>, a client account of {user.acting.agency_name}.</span>
      <button type="button" onClick={backToAgency} className="inline-flex items-center gap-1 font-medium text-brand-strong hover:underline" data-testid="acting-banner-leave">
        <ArrowLeft className="size-3.5" aria-hidden="true" />Back to {user.acting.agency_name}
      </button>
    </div>
  </div>;
}
