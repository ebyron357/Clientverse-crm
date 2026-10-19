/* Settings → Agency → Client accounts: the client accounts an agency runs.
   An agency admin creates accounts (optionally from a snapshot), opens one to work in it,
   and pushes a snapshot to many at once: previewed per account first, with a result for
   each. Every client account stays separate: its own records, team and connections. */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { api, formatErr } from "@/lib/api";
import { PageHeader } from "@/components/page/Page";
import { STICKY_FOOTER, SetupPlan, countAdds, things } from "@/components/SetupPlan";
import { backToAgency, openClientAccount } from "@/components/AgencySwitcher";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowRight, Building2, ChevronDown, MoreHorizontal, Pencil, Plus, Send } from "lucide-react";

const TH = "h-9 whitespace-nowrap px-4 text-left text-xs font-medium text-muted-foreground";
const TD = "px-4 py-3 align-top";
const BLANK = "__blank";
const reason = (requestError) => formatErr(requestError.response?.data?.detail);
const day = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "");

export default function AgencyAccounts() {
  const { user } = useAuth();
  const isClient = user?.workspace?.kind === "client" && !user?.acting;
  const allowed = user?.role === "admin" && !isClient;
  const [state, setState] = useState({ loaded: false, items: [], agency: null });
  const [snapshots, setSnapshots] = useState([]);
  const [creating, setCreating] = useState(false);
  const [pushing, setPushing] = useState(false);
  const [renaming, setRenaming] = useState(null);

  const load = useCallback(async () => {
    if (!allowed) return;
    try {
      const [accounts, snaps] = await Promise.all([api.get("/agency/accounts"), api.get("/agency/snapshots")]);
      setState({ loaded: true, items: accounts.data.items || [], agency: accounts.data.agency_name });
      setSnapshots(snaps.data.items || []);
    } catch (requestError) {
      setState((current) => ({ ...current, loaded: true }));
      toast.error("Client accounts could not be loaded", { description: reason(requestError) });
    }
  }, [allowed]);
  useEffect(() => { load(); }, [load]);

  return <div className="cv-page">
    <PageHeader icon={Building2} title="Client accounts"
      description="Run every client from one agency. Each client account keeps its own records, team and connections."
      actions={allowed && <>
        <Button size="sm" variant="outline" onClick={() => setPushing(true)} disabled={!state.items.length || !snapshots.length} data-testid="agency-push-open"><Send className="size-3.5" />Push a snapshot</Button>
        <Button size="sm" className="cv-action-primary" onClick={() => setCreating(true)} data-testid="agency-new"><Plus className="size-3.5" />New client account</Button>
      </>} />
    {isClient ? <p className="mt-4 text-[13px] text-muted-foreground" data-testid="agency-client-note">This workspace is a client account{user.workspace.agency_name ? ` of ${user.workspace.agency_name}` : ""}. Client accounts do not have client accounts of their own.</p>
      : !allowed ? <p className="mt-4 text-[13px] text-muted-foreground">Only an admin can manage client accounts.</p>
      : <>
        {user?.acting && <p className="mt-3 text-[13px] text-muted-foreground">These are {user.acting.agency_name}'s client accounts. <button type="button" className="font-medium text-brand-strong hover:underline" onClick={backToAgency}>Back to the agency</button></p>}
        {!snapshots.length && state.loaded && <p className="mt-3 text-[13px] text-muted-foreground">To set up accounts in one step, first save your setup as a <Link to="/settings/snapshots" className="font-medium text-brand-strong hover:underline">snapshot</Link>.</p>}
        <div className="mt-4 overflow-hidden rounded-xl border border-border bg-card">
          {!state.loaded ? <div className="space-y-3 p-4">{[0, 1, 2].map((index) => <Skeleton key={index} className="h-5 w-2/3" />)}</div>
            : !state.items.length ? <div className="flex flex-col items-center px-6 py-12 text-center" data-testid="agency-empty">
                <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground"><Building2 className="size-[18px]" aria-hidden="true" /></span>
                <h2 className="mt-3 text-sm font-medium">No client accounts yet</h2>
                <p className="mt-1 max-w-md text-[13px] leading-5 text-muted-foreground">Give each client their own account, set up from your snapshot in one step. You open any of them from here or from the account switcher at the top of the menu.</p>
                <Button size="sm" className="cv-action-primary mt-4" onClick={() => setCreating(true)}><Plus className="size-3.5" />Add the first client</Button>
              </div>
            : <div className="overflow-x-auto"><table className="w-full text-[13px]">
                <caption className="sr-only">Client accounts</caption>
                <thead><tr className="border-b border-border bg-muted/40"><th scope="col" className={TH}>Account</th><th scope="col" className={`${TH} hidden sm:table-cell`}>Team</th><th scope="col" className={`${TH} hidden md:table-cell`}>Contacts</th><th scope="col" className={`${TH} hidden md:table-cell`}>Open deals</th><th scope="col" className={`${TH} hidden lg:table-cell`}>Last snapshot</th><th scope="col" className={`${TH} text-right`}><span className="sr-only">Actions</span></th></tr></thead>
                <tbody>{state.items.map((account) => {
                  const current = user?.acting?.tenant_id === account.tenant_id;
                  return <tr key={account.tenant_id} className="border-b border-border/70 last:border-0" data-testid={`agency-row-${account.tenant_id}`}>
                    <td className={`${TD} min-w-[160px]`}>
                      <div className="font-medium text-foreground">{account.name}{current && <span className="ml-2 rounded-md bg-brand-soft px-1.5 py-0.5 text-[11px] font-semibold text-brand-strong">Open now</span>}</div>
                      <div className="mt-0.5 text-xs text-muted-foreground">Since {day(account.created_at)}<span className="md:hidden"> · {account.contacts} contacts</span></div>
                    </td>
                    <td className={`${TD} hidden text-foreground/80 sm:table-cell`}>{account.members ? `${account.members} ${account.members === 1 ? "person" : "people"}` : <span className="text-muted-foreground">No one yet</span>}</td>
                    <td className={`${TD} tabular hidden text-foreground/80 md:table-cell`}>{account.contacts}</td>
                    <td className={`${TD} tabular hidden text-foreground/80 md:table-cell`}>{account.open_deals}</td>
                    <td className={`${TD} hidden text-foreground/80 lg:table-cell`}>{account.last_snapshot ? <>{account.last_snapshot.name}<div className="text-xs text-muted-foreground">{day(account.last_snapshot.loaded_at)} · {things(account.last_snapshot.added)} added</div></> : <span className="text-muted-foreground">—</span>}</td>
                    <td className={`${TD} whitespace-nowrap text-right`}>
                      <Button size="sm" variant="outline" className="h-7 px-2 text-xs" disabled={current} onClick={() => openClientAccount(account)} data-testid={`agency-open-${account.tenant_id}`}>Open<ArrowRight className="size-3" /></Button>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild><Button size="sm" variant="ghost" className="ml-1 h-7 px-2" aria-label={`More for ${account.name}`}><MoreHorizontal className="size-4" /></Button></DropdownMenuTrigger>
                        <DropdownMenuContent align="end"><DropdownMenuItem onSelect={() => setRenaming(account)}><Pencil className="size-3.5" />Rename</DropdownMenuItem></DropdownMenuContent>
                      </DropdownMenu>
                    </td>
                  </tr>;
                })}</tbody>
              </table></div>}
        </div>
      </>}
    {creating && <NewAccountDialog snapshots={snapshots} onClose={() => setCreating(false)} onCreated={async () => { setCreating(false); await load(); }} />}
    {pushing && <PushDialog snapshots={snapshots} accounts={state.items} onClose={() => setPushing(false)} onPushed={load} />}
    {renaming && <RenameDialog account={renaming} onClose={() => setRenaming(null)} onSaved={async () => { setRenaming(null); await load(); }} />}
  </div>;
}

function NewAccountDialog({ snapshots, onClose, onCreated }) {
  const [name, setName] = useState("");
  const [snapshotId, setSnapshotId] = useState(snapshots[0]?.id || BLANK);
  const [saving, setSaving] = useState(false);
  const create = async () => {
    setSaving(true);
    try {
      const { data } = await api.post("/agency/accounts", { name: name.trim(), snapshot_id: snapshotId === BLANK ? null : snapshotId });
      const added = countAdds(data.items);
      toast.success(`“${data.account.name}” created`, {
        description: snapshotId === BLANK ? "A blank account, ready to set up." : `${things(added)} added from the snapshot.`,
        action: { label: "Open it", onClick: () => openClientAccount(data.account) },
      });
      await onCreated();
    } catch (requestError) { toast.error("The account was not created", { description: reason(requestError) }); } finally { setSaving(false); }
  };
  return <Dialog open onOpenChange={(value) => !value && onClose()}>
    <DialogContent className="sm:max-w-md" data-testid="agency-new-dialog">
      <DialogHeader><DialogTitle>New client account</DialogTitle><DialogDescription>A separate workspace for one client. You can open it any time; invite the client's own team from its Team page.</DialogDescription></DialogHeader>
      <div className="space-y-4">
        <div className="grid gap-1.5"><Label htmlFor="agency-account-name">Client name</Label><Input id="agency-account-name" value={name} maxLength={120} onChange={(event) => setName(event.target.value)} placeholder="For example: Bright Dental" data-testid="agency-account-name" /></div>
        <div className="grid gap-1.5"><Label htmlFor="agency-account-snapshot">Start from</Label>
          <Select value={snapshotId} onValueChange={setSnapshotId}>
            <SelectTrigger id="agency-account-snapshot" data-testid="agency-account-snapshot"><SelectValue /></SelectTrigger>
            <SelectContent>
              {snapshots.map((snapshot) => <SelectItem key={snapshot.id} value={snapshot.id}>Snapshot: {snapshot.name}</SelectItem>)}
              <SelectItem value={BLANK}>A blank account</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">Its booking pages wait, paused, until someone on the client's team hosts them.</p>
        </div>
      </div>
      <DialogFooter className="gap-2 sm:gap-2">
        <Button size="sm" variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
        <Button size="sm" className="cv-action-primary" onClick={create} disabled={saving || !name.trim()} data-testid="agency-create">{saving ? "Creating…" : "Create account"}</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>;
}

function RenameDialog({ account, onClose, onSaved }) {
  const [name, setName] = useState(account.name);
  const save = async () => {
    try { await api.patch(`/agency/accounts/${account.tenant_id}`, { name: name.trim() }); toast.success("Account renamed"); await onSaved(); } catch (requestError) { toast.error("The name was not changed", { description: reason(requestError) }); }
  };
  return <Dialog open onOpenChange={(value) => !value && onClose()}>
    <DialogContent className="sm:max-w-md">
      <DialogHeader><DialogTitle>Rename “{account.name}”</DialogTitle><DialogDescription>The client's team sees the new name too.</DialogDescription></DialogHeader>
      <div className="grid gap-1.5"><Label htmlFor="agency-rename">Client name</Label><Input id="agency-rename" value={name} maxLength={120} onChange={(event) => setName(event.target.value)} /></div>
      <DialogFooter className="gap-2 sm:gap-2"><Button size="sm" variant="outline" onClick={onClose}>Cancel</Button><Button size="sm" className="cv-action-primary" onClick={save} disabled={!name.trim()}>Save</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
}

function PushDialog({ snapshots, accounts, onClose, onPushed }) {
  const [snapshotId, setSnapshotId] = useState(snapshots[0]?.id);
  const [chosen, setChosen] = useState(accounts.map((account) => account.tenant_id));
  const [plan, setPlan] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const toggle = (id, on) => setChosen((current) => on ? [...current, id] : current.filter((item) => item !== id));
  const body = { snapshot_id: snapshotId, account_ids: chosen };
  const preview = async () => {
    setBusy(true);
    try { const { data } = await api.post("/agency/snapshot-push/preview", body); setPlan(data); } catch (requestError) { toast.error("The preview could not be made", { description: reason(requestError) }); } finally { setBusy(false); }
  };
  const apply = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/agency/snapshot-push/apply", body);
      const added = data.accounts.reduce((sum, account) => sum + account.add, 0);
      toast.success(`“${data.snapshot}” pushed to ${data.accounts.length} ${data.accounts.length === 1 ? "account" : "accounts"}`, { description: `${things(added)} added in all. Nothing a client had was changed.` });
      setResult(data);
      await onPushed();
    } catch (requestError) { toast.error("The snapshot was not pushed", { description: reason(requestError) }); } finally { setBusy(false); }
  };
  const shown = result || plan;
  const toAdd = plan ? plan.accounts.reduce((sum, account) => sum + account.add, 0) : 0;
  return <Dialog open onOpenChange={(value) => !value && onClose()}>
    <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl" data-testid="agency-push-dialog">
      <DialogHeader>
        <DialogTitle>{result ? "Snapshot pushed" : "Push a snapshot to client accounts"}</DialogTitle>
        <DialogDescription>{result ? "Each account got what it was missing. Automations arrive as drafts in each account." : "Each account gets only what it is missing; nothing a client already has is changed. You see the result for every account before anything changes."}</DialogDescription>
      </DialogHeader>
      {!shown ? <div className="space-y-4">
          <div className="grid gap-1.5"><Label htmlFor="agency-push-snapshot">Snapshot</Label>
            <Select value={snapshotId} onValueChange={setSnapshotId}>
              <SelectTrigger id="agency-push-snapshot" data-testid="agency-push-snapshot"><SelectValue /></SelectTrigger>
              <SelectContent>{snapshots.map((snapshot) => <SelectItem key={snapshot.id} value={snapshot.id}>{snapshot.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <fieldset>
            <div className="flex items-center justify-between"><legend className="text-sm font-medium">Accounts ({chosen.length} of {accounts.length})</legend>
              <button type="button" className="text-xs font-medium text-brand-strong hover:underline" onClick={() => setChosen(chosen.length === accounts.length ? [] : accounts.map((account) => account.tenant_id))}>{chosen.length === accounts.length ? "Clear all" : "Choose all"}</button></div>
            <div className="mt-2 max-h-64 divide-y divide-border/70 overflow-y-auto rounded-lg border border-border">{accounts.map((account) => <label key={account.tenant_id} htmlFor={`agency-push-${account.tenant_id}`} className="flex cursor-pointer items-center gap-3 px-3 py-2 text-[13px]">
              <Checkbox id={`agency-push-${account.tenant_id}`} checked={chosen.includes(account.tenant_id)} onCheckedChange={(on) => toggle(account.tenant_id, on === true)} />
              <span className="min-w-0 flex-1 truncate">{account.name}</span>
            </label>)}</div>
          </fieldset>
        </div>
        : <ul className="divide-y divide-border/70 rounded-lg border border-border" data-testid="agency-push-results">{shown.accounts.map((account) => <li key={account.tenant_id}>
            <details className="group">
              <summary className="flex cursor-pointer list-none items-center gap-3 px-3 py-2.5 text-[13px]">
                <span className="min-w-0 flex-1 truncate font-medium">{account.name}</span>
                <span className="shrink-0 text-xs text-muted-foreground">{result ? "Added" : "Adds"} {account.add} · {account.keep} already there{account.skip ? ` · ${account.skip} can't load` : ""}</span>
                <ChevronDown className="size-3.5 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" aria-hidden="true" />
              </summary>
              <div className="border-t border-border/70 px-3 py-3"><SetupPlan items={account.items} applied={Boolean(result)} empty="Nothing: this account already has everything." testid={`agency-push-${account.tenant_id}`} /></div>
            </details>
          </li>)}</ul>}
      <DialogFooter className={STICKY_FOOTER}>
        {result ? <Button size="sm" onClick={onClose}>Done</Button> : plan ? <>
          <Button size="sm" variant="outline" onClick={() => setPlan(null)} disabled={busy}>Back</Button>
          <Button size="sm" className="cv-action-primary" onClick={apply} disabled={busy || !toAdd} data-testid="agency-push-apply">{busy ? "Pushing…" : toAdd ? `Push to ${plan.accounts.length} ${plan.accounts.length === 1 ? "account" : "accounts"}` : "Nothing to add"}</Button>
        </> : <>
          <Button size="sm" variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button size="sm" className="cv-action-primary" onClick={preview} disabled={busy || !snapshotId || !chosen.length} data-testid="agency-push-preview">{busy ? "Checking…" : "Preview"}</Button>
        </>}
      </DialogFooter>
    </DialogContent>
  </Dialog>;
}
