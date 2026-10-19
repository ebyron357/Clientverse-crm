/* Settings → Snapshots: save this workspace's setup and load it into another.
   A snapshot holds pipeline stages, fields, booking pages, forms, automations and shared list
   views, never records, people, links or secrets. It loads from this list, a share code or a
   downloaded file, always through a preview, and only ever adds what is missing. */

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { api, formatErr } from "@/lib/api";
import { PageHeader, StatusDot, ViewTabs } from "@/components/page/Page";
import { STICKY_FOOTER, SetupPlan, countAdds, things } from "@/components/SetupPlan";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Camera, Copy, Download, MoreHorizontal, Plus, Share2, Trash2, Upload } from "lucide-react";

const SECTIONS = [
  { key: "pipeline", count: "stages", label: "Pipeline stages", one: "stage", many: "stages" },
  { key: "fields", count: "fields", label: "Fields", one: "field", many: "fields" },
  { key: "booking_pages", count: "booking_pages", label: "Booking pages", one: "booking page", many: "booking pages" },
  { key: "forms", count: "forms", label: "Website forms", one: "form", many: "forms" },
  { key: "automations", count: "automations", label: "Automations", one: "automation", many: "automations" },
  { key: "views", count: "views", label: "Shared list views", one: "view", many: "views" },
];
const TH = "h-9 whitespace-nowrap px-4 text-left text-xs font-medium text-muted-foreground";
const TD = "px-4 py-3 align-top";
const NEVER = "No contacts, companies, deals, messages, team members, connected accounts or passwords.";

const describeCounts = (counts = {}) => SECTIONS
  .filter((section) => counts[section.count] > 0)
  .map((section) => `${counts[section.count]} ${counts[section.count] === 1 ? section.one : section.many}`)
  .join(" · ") || "Nothing";

const day = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "");
const reason = (requestError) => formatErr(requestError.response?.data?.detail);

export default function Snapshots() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [state, setState] = useState({ loaded: false, items: [] });
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(null);
  const [sharing, setSharing] = useState(null);
  const [deleting, setDeleting] = useState(null);

  const load = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const { data } = await api.get("/snapshots");
      setState({ loaded: true, items: data.items || [] });
    } catch (requestError) {
      setState((current) => ({ ...current, loaded: true }));
      toast.error("Snapshots could not be loaded", { description: reason(requestError) });
    }
  }, [isAdmin]);
  useEffect(() => { load(); }, [load]);

  const download = async (snapshot) => {
    try {
      const { data } = await api.get(`/snapshots/${snapshot.id}/file`);
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `${snapshot.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "snapshot"}.clientverse-snapshot.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (requestError) { toast.error("The file could not be made", { description: reason(requestError) }); }
  };

  const remove = async () => {
    try {
      await api.delete(`/snapshots/${deleting.id}`);
      toast.success(`“${deleting.name}” deleted`);
      setDeleting(null);
      await load();
    } catch (requestError) { toast.error("Nothing was deleted", { description: reason(requestError) }); }
  };

  return <div className="cv-page">
    <PageHeader icon={Camera} title="Snapshots"
      description="Save this workspace's setup and load it into another workspace. Loading adds only what is missing."
      actions={isAdmin && <>
        <Button size="sm" variant="outline" onClick={() => setLoading({})} data-testid="snapshot-load-open"><Upload className="size-3.5" />Load a snapshot</Button>
        <Button size="sm" className="cv-action-primary" onClick={() => setCreating(true)} data-testid="snapshot-new"><Plus className="size-3.5" />New snapshot</Button>
      </>} />
    {!isAdmin ? <p className="mt-4 text-[13px] text-muted-foreground" data-testid="snapshots-admin-only">Only an admin can save or load snapshots: they read and change the whole workspace setup.</p>
      : <>
        <p className="mt-3 text-[13px] text-muted-foreground">A snapshot holds pipeline stages, fields, booking pages, website forms, automations and shared list views. {NEVER}</p>
        <div className="mt-4 overflow-hidden rounded-xl border border-border bg-card">
          {!state.loaded ? <div className="space-y-3 p-4">{[0, 1, 2].map((index) => <Skeleton key={index} className="h-5 w-2/3" />)}</div>
            : !state.items.length ? <div className="flex flex-col items-center px-6 py-12 text-center" data-testid="snapshots-empty">
                <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground"><Camera className="size-[18px]" aria-hidden="true" /></span>
                <h2 className="mt-3 text-sm font-medium">No snapshots yet</h2>
                <p className="mt-1 max-w-md text-[13px] leading-5 text-muted-foreground">Build your setup once, save it, and load it into every new client or location. Share it with a code, or download it as a file.</p>
                <Button size="sm" className="cv-action-primary mt-4" onClick={() => setCreating(true)}><Plus className="size-3.5" />Save this setup</Button>
              </div>
            : <div className="overflow-x-auto"><table className="w-full text-[13px]">
                <caption className="sr-only">Snapshots</caption>
                <thead><tr className="border-b border-border bg-muted/40"><th scope="col" className={TH}>Snapshot</th><th scope="col" className={`${TH} hidden lg:table-cell`}>Contains</th><th scope="col" className={`${TH} hidden md:table-cell`}>Saved</th><th scope="col" className={`${TH} hidden sm:table-cell`}>Sharing</th><th scope="col" className={`${TH} text-right`}><span className="sr-only">Actions</span></th></tr></thead>
                <tbody>{state.items.map((snapshot) => <tr key={snapshot.id} className="border-b border-border/70 last:border-0" data-testid={`snapshot-row-${snapshot.id}`}>
                  <td className={`${TD} min-w-[160px] max-w-[320px]`}>
                    <div className="font-medium text-foreground">{snapshot.name}</div>
                    {snapshot.description && <div className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{snapshot.description}</div>}
                    <div className="mt-0.5 text-xs text-muted-foreground lg:hidden">{describeCounts(snapshot.counts)}</div>
                    <div className="mt-1 sm:hidden"><Sharing snapshot={snapshot} /></div>
                  </td>
                  <td className={`${TD} hidden max-w-[360px] text-foreground/80 lg:table-cell`}>{describeCounts(snapshot.counts)}</td>
                  <td className={`${TD} hidden whitespace-nowrap text-foreground/80 md:table-cell`}>{day(snapshot.created_at)}<div className="text-xs text-muted-foreground">{snapshot.created_by}</div></td>
                  <td className={`${TD} hidden sm:table-cell`}><Sharing snapshot={snapshot} /></td>
                  <td className={`${TD} whitespace-nowrap text-right`}>
                    <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={() => setLoading({ snapshot })} data-testid={`snapshot-load-${snapshot.id}`}>Load here</Button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild><Button size="sm" variant="ghost" className="ml-1 h-7 px-2" aria-label={`More for ${snapshot.name}`} data-testid={`snapshot-menu-${snapshot.id}`}><MoreHorizontal className="size-4" /></Button></DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onSelect={() => setSharing(snapshot)} data-testid={`snapshot-share-${snapshot.id}`}><Share2 className="size-3.5" />Share…</DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => download(snapshot)} data-testid={`snapshot-download-${snapshot.id}`}><Download className="size-3.5" />Download file</DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onSelect={() => setDeleting(snapshot)} className="text-destructive focus:text-destructive" data-testid={`snapshot-delete-${snapshot.id}`}><Trash2 className="size-3.5" />Delete</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </td>
                </tr>)}</tbody>
              </table></div>}
        </div>
      </>}
    {creating && <NewSnapshotDialog onClose={() => setCreating(false)} onSaved={async () => { setCreating(false); await load(); }} />}
    {loading && <LoadDialog snapshot={loading.snapshot} onClose={() => setLoading(null)} />}
    {sharing && <ShareDialog snapshot={sharing} onClose={() => setSharing(null)} onChanged={load} />}
    <AlertDialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(null)}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete “{deleting?.name}”?</AlertDialogTitle>
          <AlertDialogDescription>The snapshot and its share code go. Nothing in this workspace changes, and whatever was already loaded from it stays where it is.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={remove} data-testid="snapshot-delete-confirm">Delete</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>;
}

function Sharing({ snapshot }) {
  return snapshot.shared ? <StatusDot tone="success">Shared{snapshot.loads ? ` · loaded ${snapshot.loads}×` : ""}</StatusDot> : <StatusDot tone="neutral">Not shared</StatusDot>;
}

function NewSnapshotDialog({ onClose, onSaved }) {
  const [name, setName] = useState(`Setup ${new Date().toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`);
  const [description, setDescription] = useState("");
  const [include, setInclude] = useState(SECTIONS.map((section) => section.key));
  const [counts, setCounts] = useState(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    api.get("/snapshots/current-setup").then(({ data }) => setCounts(data.counts)).catch(() => setCounts({}));
  }, []);
  const toggle = (key, on) => setInclude((current) => on ? [...current, key] : current.filter((item) => item !== key));
  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.post("/snapshots", { name: name.trim(), description: description.trim() || null, include });
      toast.success(`“${data.name}” saved`, { description: describeCounts(data.counts) });
      await onSaved();
    } catch (requestError) { toast.error("The snapshot was not saved", { description: reason(requestError) }); } finally { setSaving(false); }
  };
  return <Dialog open onOpenChange={(value) => !value && onClose()}>
    <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg" data-testid="snapshot-new-dialog">
      <DialogHeader><DialogTitle>Save a snapshot</DialogTitle><DialogDescription>A copy of this workspace's setup as it is now. Changing the workspace later does not change the snapshot.</DialogDescription></DialogHeader>
      <div className="space-y-4">
        <div className="grid gap-1.5"><Label htmlFor="snapshot-name">Name</Label><Input id="snapshot-name" value={name} maxLength={80} onChange={(event) => setName(event.target.value)} data-testid="snapshot-name" /></div>
        <div className="grid gap-1.5"><Label htmlFor="snapshot-description">Description <span className="font-normal text-muted-foreground">(optional)</span></Label><Textarea id="snapshot-description" rows={2} maxLength={300} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="For example: dental clinics, two locations" /></div>
        <fieldset>
          <legend className="text-sm font-medium">What it holds</legend>
          <div className="mt-2 divide-y divide-border/70 rounded-lg border border-border">{SECTIONS.map((section) => <label key={section.key} htmlFor={`snapshot-include-${section.key}`} className="flex cursor-pointer items-center gap-3 px-3 py-2 text-[13px]">
            <Checkbox id={`snapshot-include-${section.key}`} checked={include.includes(section.key)} onCheckedChange={(on) => toggle(section.key, on === true)} data-testid={`snapshot-include-${section.key}`} />
            <span className="flex-1">{section.label}</span>
            <span className="tabular text-xs text-muted-foreground">{counts ? counts[section.count] ?? 0 : "…"}</span>
          </label>)}</div>
          <p className="mt-2 text-xs text-muted-foreground">{NEVER} Booking pages leave their host behind, forms their website addresses and lead assignment, and automations anyone they named.</p>
        </fieldset>
      </div>
      <DialogFooter className="gap-2 sm:gap-2">
        <Button size="sm" variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
        <Button size="sm" className="cv-action-primary" onClick={save} disabled={saving || !name.trim() || !include.length} data-testid="snapshot-save">{saving ? "Saving…" : "Save snapshot"}</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>;
}

function ShareDialog({ snapshot, onClose, onChanged }) {
  const [current, setCurrent] = useState(snapshot);
  const [code, setCode] = useState(null);
  const [busy, setBusy] = useState(false);
  const makeCode = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/snapshots/${snapshot.id}/share`);
      setCode(data.code);
      setCurrent(data);
      await onChanged();
    } catch (requestError) { toast.error("Sharing was not turned on", { description: reason(requestError) }); } finally { setBusy(false); }
  };
  const stop = async () => {
    setBusy(true);
    try {
      const { data } = await api.delete(`/snapshots/${snapshot.id}/share`);
      setCode(null);
      setCurrent(data);
      toast.success("Sharing stopped", { description: "The code no longer works." });
      await onChanged();
    } catch (requestError) { toast.error("Sharing was not stopped", { description: reason(requestError) }); } finally { setBusy(false); }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(code); toast.success("Code copied"); } catch { toast.error("Copy it by hand: select the code and copy it."); }
  };
  return <Dialog open onOpenChange={(value) => !value && onClose()}>
    <DialogContent className="sm:max-w-lg" data-testid="snapshot-share-dialog">
      <DialogHeader><DialogTitle>Share “{snapshot.name}”</DialogTitle><DialogDescription>An admin of another ClientVerse workspace can load this snapshot with its share code.</DialogDescription></DialogHeader>
      <div className="space-y-3 text-[13px]">
        {code ? <div className="space-y-2" data-testid="snapshot-share-code">
            <Label htmlFor="snapshot-code">Share code</Label>
            <div className="flex gap-2"><Input id="snapshot-code" readOnly value={code} className="font-mono text-xs" onFocus={(event) => event.target.select()} /><Button size="sm" variant="outline" onClick={copy}><Copy className="size-3.5" />Copy</Button></div>
            <p className="text-xs text-muted-foreground">Copy it now: it is not shown again. Anyone who has it can load this snapshot until you stop sharing or make a new code.</p>
          </div>
          : current.shared ? <p className="text-muted-foreground">Sharing is on{current.loads ? `, and the snapshot has been loaded ${current.loads} ${current.loads === 1 ? "time" : "times"}` : ""}. The code was shown when it was made. Make a new code to see one again; the old code then stops working.</p>
          : <p className="text-muted-foreground">Sharing is off. Turning it on makes a code you can send to a client or another location.</p>}
        <div className="rounded-lg border border-border bg-muted/30 p-3 text-xs text-muted-foreground">{NEVER} It does carry the wording you wrote, such as confirmation messages, auto-reply text, task titles and a meeting location, so check those before you share.</div>
      </div>
      <DialogFooter className="gap-2 sm:gap-2">
        {current.shared && <Button size="sm" variant="outline" onClick={stop} disabled={busy} data-testid="snapshot-share-stop">Stop sharing</Button>}
        <Button size="sm" className="cv-action-primary" onClick={makeCode} disabled={busy} data-testid="snapshot-share-make">{current.shared ? "Make a new code" : "Turn on sharing"}</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>;
}

function LoadDialog({ snapshot, onClose }) {
  const [tab, setTab] = useState("code");
  const [code, setCode] = useState("");
  const [file, setFile] = useState(null);
  const [fileError, setFileError] = useState(null);
  const [plan, setPlan] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const scroller = useRef(null);
  useEffect(() => { if (result) scroller.current?.scrollTo({ top: 0 }); }, [result]);

  const source = snapshot ? { snapshot_id: snapshot.id } : tab === "code" ? (code.trim() ? { code: code.trim() } : null) : (file ? { file: file.body } : null);
  const preview = useCallback(async (body) => {
    setBusy(true); setError(null); setPlan(null);
    try { const { data } = await api.post("/snapshot-loads/preview", body); setPlan(data); } catch (requestError) { setError(reason(requestError)); } finally { setBusy(false); }
  }, []);
  useEffect(() => { if (snapshot) preview({ snapshot_id: snapshot.id }); }, [snapshot, preview]);

  const pickFile = async (event) => {
    const chosen = event.target.files?.[0];
    setPlan(null); setError(null); setFile(null); setFileError(null);
    if (!chosen) return;
    if (chosen.size > 1_000_000) { setFileError("This file is larger than a snapshot can be (1 MB)."); return; }
    try { setFile({ name: chosen.name, body: JSON.parse(await chosen.text()) }); } catch { setFileError("This file is not a ClientVerse snapshot."); }
  };
  const apply = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/snapshot-loads/apply", source);
      const added = countAdds(data.items);
      toast.success(`“${data.name}” loaded`, { description: added ? `${things(added)} added. Nothing you had was changed.` : "You already had everything it holds." });
      setResult(data);
    } catch (requestError) { toast.error("The snapshot was not loaded", { description: reason(requestError) }); } finally { setBusy(false); }
  };

  const shown = result || plan;
  const adds = countAdds(shown?.items);
  return <Dialog open onOpenChange={(value) => !value && onClose()}>
    <DialogContent ref={scroller} className="max-h-[85vh] overflow-y-auto sm:max-w-xl" data-testid="snapshot-load-dialog">
      <DialogHeader>
        <DialogTitle>{result ? `“${result.name}” is loaded` : snapshot ? `Load “${snapshot.name}” here?` : "Load a snapshot"}</DialogTitle>
        <DialogDescription>{result ? "Automations arrive as drafts and run only after you turn them on. Form auto-replies stay off until approved." : "You see exactly what will be added before anything changes. Nothing you already have is changed or removed."}</DialogDescription>
      </DialogHeader>
      {!snapshot && !shown && <div className="space-y-3">
        <ViewTabs label="Load from" value={tab} onChange={(value) => { setTab(value); setPlan(null); setError(null); }}
          items={[{ value: "code", label: "Share code", testid: "snapshot-load-tab-code" }, { value: "file", label: "File", testid: "snapshot-load-tab-file" }]} />
        {tab === "code" ? <div key="code" className="grid gap-1.5"><Label htmlFor="snapshot-load-code">Share code</Label><Input id="snapshot-load-code" value={code} onChange={(event) => setCode(event.target.value)} placeholder="cvs_…" className="font-mono text-xs" autoComplete="off" data-testid="snapshot-load-code" /></div>
          : <div key="file" className="grid gap-1.5"><Label htmlFor="snapshot-load-file">Snapshot file (.json)</Label><Input id="snapshot-load-file" type="file" accept=".json,application/json" onChange={pickFile} data-testid="snapshot-load-file" />
              {fileError && <p className="text-xs text-destructive" role="alert">{fileError}</p>}
              {file && <p className="text-xs text-muted-foreground">{file.body?.name ? `“${file.body.name}”` : file.name}</p>}</div>}
      </div>}
      {error && <p className="text-[13px] text-destructive" role="alert" data-testid="snapshot-load-error">{error}</p>}
      {busy && !shown && <div className="space-y-2">{[0, 1, 2].map((index) => <Skeleton key={index} className="h-5 w-3/4" />)}</div>}
      {shown && <SetupPlan items={shown.items} applied={Boolean(result)} empty="Nothing: you already have everything this snapshot holds." testid="snapshot" onNavigate={onClose} />}
      <DialogFooter className={STICKY_FOOTER}>
        {result ? <Button size="sm" onClick={onClose}>Done</Button> : <>
          <Button size="sm" variant="outline" onClick={plan && !snapshot ? () => setPlan(null) : onClose} disabled={busy}>{plan && !snapshot ? "Back" : "Cancel"}</Button>
          {plan ? <Button size="sm" className="cv-action-primary" onClick={apply} disabled={busy || !adds} data-testid="snapshot-load-apply">{busy ? "Loading…" : adds ? `Add ${things(adds)}` : "Nothing to add"}</Button>
            : !snapshot && <Button size="sm" className="cv-action-primary" onClick={() => preview(source)} disabled={busy || !source} data-testid="snapshot-load-preview">{busy ? "Checking…" : "Preview"}</Button>}
        </>}
      </DialogFooter>
    </DialogContent>
  </Dialog>;
}
