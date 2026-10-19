import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { api, formatErr } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Building2, Flag, Link2, Sparkles, Users } from "lucide-react";

// What would tidy the contact list, and the one-click fix for each: companies people
// typed into a form that were never created, work emails that match a company, people
// entered twice, and people with no lifecycle stage whose history shows one.
// Renders nothing when the list is already clean.
export default function ContactCleanup({ onChanged }) {
  const [scan, setScan] = useState(null);
  const [busy, setBusy] = useState("");
  const [reviewing, setReviewing] = useState(false);

  const load = useCallback(async () => {
    try { const { data } = await api.get("/contacts/cleanup"); setScan(data); } catch { setScan(null); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const apply = async (action, success) => {
    setBusy(action);
    try {
      const { data } = await api.post("/contacts/cleanup/apply", { action });
      toast.success(success(data));
      await load(); onChanged?.();
    } catch (requestError) {
      toast.error("Nothing was changed", { description: formatErr(requestError.response?.data?.detail) });
    } finally { setBusy(""); }
  };

  if (!scan) return null;
  const typed = scan.typed_companies || [];
  const matches = scan.domain_matches || [];
  const twins = scan.duplicates || [];
  const customers = scan.lifecycle?.customer || [];
  const leads = scan.lifecycle?.lead || [];
  const staged = customers.length + leads.length;
  const total = (typed.length ? 1 : 0) + (matches.length ? 1 : 0) + (twins.length ? 1 : 0) + (staged ? 1 : 0);
  if (!total) return null;

  return <section aria-labelledby="cleanup-title" className="rounded-xl border border-brand/30 bg-card p-3 shadow-xs" data-testid="contact-cleanup">
    <div className="mb-2.5 flex items-center gap-2">
      <Sparkles className="size-4 text-brand" aria-hidden="true" />
      <h2 id="cleanup-title" className="text-sm font-semibold">Clean up {total} {total === 1 ? "thing" : "things"}</h2>
      <span className="text-xs text-muted-foreground">Found in your records</span>
    </div>
    <div className={`grid gap-2.5 ${total > 3 ? "md:grid-cols-2 xl:grid-cols-4" : "md:grid-cols-3"}`}>
      {typed.length > 0 && <Fix icon={Building2} testId="cleanup-typed"
        title={`${typed.length} ${typed.length === 1 ? "company" : "companies"} only typed in forms`}
        detail={typed.map((group) => group.name).join(", ")}
        action={<Button size="sm" onClick={() => apply("create_typed_companies", (d) => `Linked ${d.linked} ${d.linked === 1 ? "person" : "people"}; created ${d.created_companies} ${d.created_companies === 1 ? "company" : "companies"}`)} disabled={Boolean(busy)} data-testid="cleanup-create-companies">Create and link</Button>} />}
      {matches.length > 0 && <Fix icon={Link2} testId="cleanup-domain"
        title={matches.length === 1 ? `${matches[0].contact_name}’s email matches ${matches[0].company_name}` : `${matches.length} people’s emails match a company`}
        detail={matches.length === 1 ? matches[0].domain : matches.map((match) => `${match.contact_name} → ${match.company_name}`).join(", ")}
        action={<Button size="sm" variant="outline" onClick={() => apply("link_by_domain", (d) => `Linked ${d.linked} ${d.linked === 1 ? "person" : "people"} to their company`)} disabled={Boolean(busy)} data-testid="cleanup-link-domain">Link to company</Button>} />}
      {twins.length > 0 && <Fix icon={Users} testId="cleanup-duplicates"
        title={twins.length === 1 ? `${twins[0].contacts.length} people named ${twins[0].contacts[0].name}` : `${twins.length} possible duplicates`}
        detail={twins.length === 1 ? twins[0].contacts.map((c) => c.email || "no email").join(" · ") : twins.map((group) => group.contacts[0].name).join(", ")}
        action={<Button size="sm" variant="outline" onClick={() => setReviewing(true)} disabled={Boolean(busy)} data-testid="cleanup-review-duplicates">Review and merge</Button>} />}
      {staged > 0 && <Fix icon={Flag} testId="cleanup-lifecycle"
        title={`${staged} ${staged === 1 ? "person has" : "people have"} no lifecycle stage`}
        detail={[customers.length && `${customers.length} on a won deal or with a client workspace → Customer`, leads.length && `${leads.length} with an open deal or a website request → Lead`].filter(Boolean).join(" · ")}
        action={<Button size="sm" variant="outline" onClick={() => apply("set_lifecycle", (d) => `Set the stage for ${d.linked} ${d.linked === 1 ? "person" : "people"}`)} disabled={Boolean(busy)} data-testid="cleanup-set-lifecycle">Set from history</Button>} />}
    </div>
    {reviewing && <MergeDialog groups={twins} onClose={() => setReviewing(false)} onMerged={async () => { await load(); onChanged?.(); }} />}
  </section>;
}

function Fix({ icon: Icon, title, detail, action, testId }) {
  return <div className="flex min-w-0 items-start gap-2.5 rounded-lg bg-muted/60 p-2.5" data-testid={testId}>
    <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
    <div className="min-w-0 flex-1">
      <div className="text-[13px] font-medium">{title}</div>
      <div className="truncate text-xs text-muted-foreground" title={detail}>{detail}</div>
      <div className="mt-2">{action}</div>
    </div>
  </div>;
}

function MergeDialog({ groups, onClose, onMerged }) {
  // The oldest record is kept by default: it usually carries the most history.
  const [keep, setKeep] = useState(() => Object.fromEntries(groups.map((group, index) => [index, group.contacts[0].id])));
  const [busy, setBusy] = useState(false);

  const mergeGroup = async (index) => {
    const group = groups[index];
    const into = keep[index];
    setBusy(true);
    try {
      for (const contact of group.contacts.filter((c) => c.id !== into)) {
        await api.post(`/contacts/${contact.id}/merge`, { into_id: into });
      }
      toast.success(`Merged into ${group.contacts.find((c) => c.id === into)?.name || "the kept contact"}`);
      await onMerged();
      if (groups.length === 1) onClose();
    } catch (requestError) {
      toast.error("Could not merge", { description: formatErr(requestError.response?.data?.detail) });
    } finally { setBusy(false); }
  };

  return <Dialog open onOpenChange={(value) => !value && onClose()}>
    <DialogContent className="max-w-lg">
      <DialogHeader>
        <DialogTitle>Review possible duplicates</DialogTitle>
        <DialogDescription>Choose the record to keep. Deals, tasks, notes, enquiries and appointments move to it, empty fields are filled from the other, and the other is archived.</DialogDescription>
      </DialogHeader>
      <div className="max-h-[50vh] space-y-3 overflow-y-auto">
        {groups.map((group, index) => <fieldset key={group.contacts.map((c) => c.id).join("-")} className="rounded-lg border border-border p-3">
          <legend className="px-1 text-xs font-medium text-muted-foreground">{group.reason === "same email" ? "Same email" : "Same name"}</legend>
          <div className="space-y-1.5">
            {group.contacts.map((contact) => <label key={contact.id} className="flex cursor-pointer items-center gap-2.5 text-[13px]">
              <input type="radio" name={`keep-${index}`} checked={keep[index] === contact.id} onChange={() => setKeep((current) => ({ ...current, [index]: contact.id }))} />
              <span className="font-medium">{contact.name}</span>
              <span className="text-muted-foreground">{contact.email || "no email"}</span>
              {contact.company_id && <span className="text-xs text-muted-foreground">· has a company</span>}
            </label>)}
          </div>
          <Button size="sm" className="mt-2.5" onClick={() => mergeGroup(index)} disabled={busy} data-testid={`merge-group-${index}`}>Merge into the selected record</Button>
        </fieldset>)}
      </div>
      <DialogFooter><Button variant="outline" onClick={onClose}>Done</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
}
