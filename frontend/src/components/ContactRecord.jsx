/* A contact's record: who they are, how to reach them, what has happened with them, and
   their deals and website requests. Opens as a side panel (full width on a phone) from
   the contact list or straight from a link to /contacts?contact=<id>. */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr, formatMoney } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import {
  ACTIVITY_KINDS, CALL_OUTCOMES, LEAD_STATUS_LABEL, LEAD_STATUS_STYLE, OUTREACH_KINDS,
  agoLabel, fullDateLabel, historyEntries, stageLabel,
} from "@/lib/contactHistory";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Archive, ArchiveRestore, CalendarDays, CircleAlert, Globe, GitBranch, Mail, MessageSquare,
  Pencil, Phone, StickyNote, UserRound,
} from "lucide-react";

const NONE = "none";
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const KIND_ICON = { call: Phone, text: MessageSquare, email: Mail, meeting: CalendarDays, note: StickyNote, request: Globe, event: UserRound };
const KIND_STYLE = {
  call: "bg-emerald-50 text-emerald-700", text: "bg-cyan-50 text-[#127b96]", email: "bg-violet-50 text-violet-700",
  meeting: "bg-amber-50 text-amber-700", note: "bg-slate-100 text-slate-600", request: "bg-cyan-50 text-[#1a9fbf]",
  event: "bg-slate-50 text-slate-400",
};
const INFLUENCE = [["low", "Low"], ["medium", "Medium"], ["high", "High"]];
const RELATIONSHIP = [["positive", "Good"], ["neutral", "Neutral"], ["negative", "At risk"]];

function SectionTitle({ children, count }) {
  return (
    <h3 className="mb-2 text-xs font-bold uppercase tracking-[0.06em] text-slate-500">
      {children}{count != null && <span className="ml-1 font-semibold text-slate-400">{count}</span>}
    </h3>
  );
}

function Row({ label, children }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] gap-3 border-t border-slate-100 py-2 text-sm first:border-t-0">
      <dt className="text-slate-500">{label}</dt>
      <dd className="min-w-0 break-words text-[#132038]">{children}</dd>
    </div>
  );
}

function Chip({ children, className = "border-slate-200 bg-slate-50 text-slate-600" }) {
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${className}`}>{children}</span>;
}

/** A list of history entries (see lib/contactHistory). Shared with the Leads inbox. */
export function ActivityFeed({ entries, empty, limit, testId }) {
  const [showAll, setShowAll] = useState(false);
  if (!entries.length) return <p className="text-sm text-slate-500">{empty}</p>;
  const visible = showAll || !limit ? entries : entries.slice(0, limit);
  return (
    <div>
      <ol className="space-y-3" data-testid={testId}>
        {visible.map((entry) => {
          const Icon = KIND_ICON[entry.kind] || StickyNote;
          return (
            <li key={entry.id} className="flex gap-3">
              <span className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${KIND_STYLE[entry.kind] || KIND_STYLE.note}`}><Icon className="h-4 w-4" /></span>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-[#132038]">{entry.title}</div>
                {entry.subject && <div className="text-sm text-slate-600">{entry.subject}</div>}
                {entry.body && <p className="mt-0.5 whitespace-pre-wrap break-words text-sm leading-6 text-slate-600">{entry.body}</p>}
                <div className="mt-0.5 text-xs text-slate-500" title={fullDateLabel(entry.at)}>
                  {[entry.who, agoLabel(entry.at)].filter(Boolean).join(" · ")}
                  {entry.leadId && <> · <Link className="font-semibold text-[#127b96]" to={`/leads?lead=${entry.leadId}`}>Open request</Link></>}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
      {limit && entries.length > limit && (
        <Button variant="ghost" size="sm" className="mt-2 px-2 text-[#127b96]" onClick={() => setShowAll((value) => !value)}>
          {showAll ? "Show less" : `Show all ${entries.length}`}
        </Button>
      )}
    </div>
  );
}

function formFrom(contact) {
  return {
    name: contact.name || "", phone: contact.phone || "", email: contact.email || "",
    company_id: contact.company_id || NONE, role: contact.role || "", title: contact.title || "",
    owner: contact.owner || NONE, influence: contact.influence || "medium", sentiment: contact.sentiment || "neutral",
  };
}

function EditForm({ contact, companies, members, isAdmin, saving, onSave, onCancel }) {
  const [form, setForm] = useState(() => formFrom(contact));
  const setField = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const ownerKnown = members.some((member) => member.email === form.owner);
  const submit = () => {
    if (!form.name.trim()) { toast.error("Add a name first."); return; }
    if (form.email.trim() && !EMAIL_PATTERN.test(form.email.trim())) { toast.error("That email address doesn't look right."); return; }
    const payload = {
      name: form.name.trim(), phone: form.phone.trim() || null, email: form.email.trim() || null,
      company_id: form.company_id === NONE ? null : form.company_id,
      role: form.role.trim() || null, title: form.title.trim() || null,
      influence: form.influence, sentiment: form.sentiment,
    };
    if (isAdmin) payload.owner = form.owner === NONE ? null : form.owner;
    onSave(payload);
  };
  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-slate-50/60 p-4" data-testid="contact-edit-form">
      <SectionTitle>Edit details</SectionTitle>
      <div className="grid gap-1.5"><Label htmlFor="contact-name">Name <span className="text-red-500">*</span></Label><Input id="contact-name" value={form.name} onChange={(event) => setField("name", event.target.value)} data-testid="contact-edit-name" /></div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="grid gap-1.5"><Label htmlFor="contact-phone">Phone</Label><Input id="contact-phone" type="tel" inputMode="tel" autoComplete="tel" value={form.phone} onChange={(event) => setField("phone", event.target.value)} placeholder="(555) 010-0100" data-testid="contact-edit-phone" /></div>
        <div className="grid gap-1.5"><Label htmlFor="contact-email">Email</Label><Input id="contact-email" type="email" inputMode="email" value={form.email} onChange={(event) => setField("email", event.target.value)} placeholder="name@example.com" data-testid="contact-edit-email" /></div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="grid gap-1.5"><Label htmlFor="contact-role">Role</Label><Input id="contact-role" value={form.role} onChange={(event) => setField("role", event.target.value)} placeholder="e.g. Buyer, Seller, Lender" data-testid="contact-edit-role" /></div>
        <div className="grid gap-1.5"><Label htmlFor="contact-title">Job title</Label><Input id="contact-title" value={form.title} onChange={(event) => setField("title", event.target.value)} placeholder="Optional" data-testid="contact-edit-title" /></div>
      </div>
      <div className="grid gap-1.5">
        <Label>Company</Label>
        <Select value={form.company_id} onValueChange={(value) => setField("company_id", value)}>
          <SelectTrigger data-testid="contact-edit-company"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={NONE}>No company</SelectItem>
            {companies.map((company) => <SelectItem key={company.id} value={company.id}>{company.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      {isAdmin && (
        <div className="grid gap-1.5">
          <Label>Owner</Label>
          <Select value={form.owner} onValueChange={(value) => setField("owner", value)}>
            <SelectTrigger data-testid="contact-edit-owner"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>Nobody yet</SelectItem>
              {!ownerKnown && form.owner !== NONE && <SelectItem value={form.owner}>{form.owner}</SelectItem>}
              {members.map((member) => <SelectItem key={member.email} value={member.email}>{member.name || member.email}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-1.5">
          <Label>Influence</Label>
          <Select value={form.influence} onValueChange={(value) => setField("influence", value)}>
            <SelectTrigger data-testid="contact-edit-influence"><SelectValue /></SelectTrigger>
            <SelectContent>{INFLUENCE.map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="grid gap-1.5">
          <Label>Relationship</Label>
          <Select value={form.sentiment} onValueChange={(value) => setField("sentiment", value)}>
            <SelectTrigger data-testid="contact-edit-relationship"><SelectValue /></SelectTrigger>
            <SelectContent>{RELATIONSHIP.map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent>
          </Select>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button className="cv-action-primary" disabled={saving} onClick={submit} data-testid="contact-save">{saving ? "Saving…" : "Save changes"}</Button>
        <Button variant="outline" disabled={saving} onClick={onCancel} data-testid="contact-edit-cancel">Cancel</Button>
      </div>
    </section>
  );
}

function LogActivity({ openRequests, saving, onSave }) {
  const [kind, setKind] = useState("call");
  const [outcome, setOutcome] = useState("");
  const [text, setText] = useState("");
  const current = ACTIVITY_KINDS.find((entry) => entry.key === kind) || ACTIVITY_KINDS[0];
  const submit = async () => {
    if (kind === "note" && !text.trim()) { toast.error("Write the note first."); return; }
    const saved = await onSave({ type: kind, body: text.trim() || undefined, outcome: kind === "call" && outcome ? outcome : undefined });
    if (saved) { setText(""); setOutcome(""); }
  };
  return (
    <section data-testid="contact-log">
      <SectionTitle>Log what happened</SectionTitle>
      <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="What kind of activity">
        {ACTIVITY_KINDS.map((entry) => {
          const Icon = KIND_ICON[entry.key];
          const active = entry.key === kind;
          return (
            <button key={entry.key} type="button" role="radio" aria-checked={active} onClick={() => setKind(entry.key)}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-semibold ${active ? "border-[#0a1628] bg-[#0a1628] text-white" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}
              data-testid={`contact-log-type-${entry.key}`}>
              <Icon className="h-3.5 w-3.5" />{entry.label}
            </button>
          );
        })}
      </div>
      {kind === "call" && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5" role="radiogroup" aria-label="How did the call go">
          <span className="mr-1 text-xs font-semibold text-slate-500">How did it go?</span>
          {CALL_OUTCOMES.map((entry) => (
            <button key={entry.key} type="button" role="radio" aria-checked={outcome === entry.key} onClick={() => setOutcome(outcome === entry.key ? "" : entry.key)}
              className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${outcome === entry.key ? "border-emerald-300 bg-emerald-50 text-emerald-800" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}
              data-testid={`contact-log-outcome-${entry.key}`}>
              {entry.label}
            </button>
          ))}
        </div>
      )}
      <Textarea className="mt-3" rows={3} value={text} onChange={(event) => setText(event.target.value)} placeholder={current.placeholder} aria-label="Details" data-testid="contact-log-text" />
      <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-slate-500">
          {OUTREACH_KINDS.has(kind) && openRequests > 0
            ? `Saving this marks their new website request${openRequests === 1 ? "" : "s"} as contacted.`
            : "Saved to their history. Nothing is sent to them."}
        </p>
        <Button size="sm" className="cv-action-primary shrink-0" disabled={saving} onClick={submit} data-testid="contact-log-save">
          {saving ? "Saving…" : `Save ${current.label.toLowerCase()}`}
        </Button>
      </div>
    </section>
  );
}

export default function ContactRecord({ contactId, open, onOpenChange, companies = [], workspaces = [], onChanged }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [detail, setDetail] = useState(null);
  const [requests, setRequests] = useState([]);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [members, setMembers] = useState([]);
  const [saving, setSaving] = useState(false);
  const [logging, setLogging] = useState(false);

  const load = useCallback(async () => {
    if (!contactId) return;
    const [detailResult, requestResult] = await Promise.allSettled([
      api.get(`/contacts/${contactId}`),
      api.get("/leads", { params: { contact_id: contactId, limit: 50 } }),
    ]);
    if (detailResult.status === "rejected") {
      const response = detailResult.reason?.response;
      setError(response?.status === 404
        ? "We couldn't find this contact. The link may be out of date."
        : formatErr(response?.data?.detail) || "This contact could not be loaded. Please try again.");
      return;
    }
    setDetail(detailResult.value.data);
    setRequests(requestResult.status === "fulfilled" ? requestResult.value.data.items || [] : []);
    setError("");
  }, [contactId]);

  useEffect(() => { setDetail(null); setRequests([]); setError(""); setEditing(false); load(); }, [load]);
  useEffect(() => {
    if (editing && isAdmin && !members.length) {
      api.get("/team/members").then((response) => setMembers((response.data || []).filter((member) => member.status !== "disabled"))).catch(() => setMembers([]));
    }
  }, [editing, isAdmin, members.length]);

  const contact = detail?.contact;
  const company = detail?.company || companies.find((item) => item.id === contact?.company_id);
  const workspace = contact?.company_id ? workspaces.find((item) => item.company_id === contact.company_id) : null;
  const openRequests = requests.filter((lead) => lead.status === "new").length;
  const history = useMemo(() => historyEntries(detail?.timeline, requests, contact?.name), [detail, requests, contact?.name]);

  const save = async (payload) => {
    setSaving(true);
    try {
      await api.patch(`/contacts/${contactId}`, payload);
      toast.success("Contact saved");
      setEditing(false);
      await load();
      onChanged?.();
    } catch (e) { toast.error("Could not save the contact", { description: formatErr(e.response?.data?.detail) }); }
    finally { setSaving(false); }
  };

  const logActivity = async ({ type, body, outcome }) => {
    setLogging(true);
    try {
      await api.post("/activities", { type, related_type: "contact", related_id: contactId, body, outcome });
      const label = ACTIVITY_KINDS.find((entry) => entry.key === type)?.label || "Activity";
      toast.success(`${label} saved`, OUTREACH_KINDS.has(type) && openRequests
        ? { description: `Their new website request${openRequests === 1 ? " is" : "s are"} now marked contacted.` } : undefined);
      await load();
      onChanged?.();
      return true;
    } catch (e) {
      toast.error("Could not save that", { description: formatErr(e.response?.data?.detail) });
      return false;
    } finally { setLogging(false); }
  };

  const setArchived = async (archived) => {
    setSaving(true);
    try {
      await api.post(`/contacts/${contactId}/${archived ? "archive" : "restore"}`);
      await load();
      onChanged?.();
      if (archived) toast.success("Contact archived", { description: "They're hidden from your contact list. Nothing was deleted.", action: { label: "Undo", onClick: () => setArchived(false) } });
      else toast.success("Contact restored");
    } catch (e) { toast.error(archived ? "Could not archive the contact" : "Could not restore the contact", { description: formatErr(e.response?.data?.detail) }); }
    finally { setSaving(false); }
  };

  const ownerLabel = detail?.owner_name || contact?.owner || "Nobody yet";
  const source = contact?.source?.kind === "website_form"
    ? `From your website${contact.source.form_name ? ` · ${contact.source.form_name}` : ""}`
    : contact?.lead_source ? `Source: ${contact.lead_source}` : null;
  const tags = (contact?.tags || []).filter((tag) => tag !== "website-lead");

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl" data-testid="contact-record">
        {error ? (
          <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
            <SheetHeader className="sr-only"><SheetTitle>Contact</SheetTitle><SheetDescription>{error}</SheetDescription></SheetHeader>
            <CircleAlert className="h-9 w-9 text-amber-500" />
            <p className="mt-3 max-w-sm text-sm leading-6 text-slate-600">{error}</p>
            <Button variant="outline" className="mt-4" onClick={() => onOpenChange(false)}>Back to contacts</Button>
          </div>
        ) : !contact ? (
          <div className="space-y-4">
            <SheetHeader className="sr-only"><SheetTitle>Loading contact</SheetTitle><SheetDescription>Loading</SheetDescription></SheetHeader>
            <Skeleton className="h-7 w-48" /><Skeleton className="h-4 w-32" /><Skeleton className="h-10 w-full" /><Skeleton className="h-40 w-full" /><Skeleton className="h-40 w-full" />
          </div>
        ) : (
          <div className="space-y-6 pb-10">
            <SheetHeader className="space-y-1 pr-6 text-left">
              <SheetTitle className="font-display text-2xl leading-tight text-[#0a1628]">{contact.name}</SheetTitle>
              <SheetDescription>{[contact.role, contact.title, company?.name].filter(Boolean).join(" · ") || "Contact"}</SheetDescription>
              <div className="flex flex-wrap gap-1.5 pt-1">
                <Chip>Owner: {ownerLabel}</Chip>
                {source && <Chip className="border-cyan-200 bg-cyan-50 text-[#0a6177]">{source}</Chip>}
                {tags.map((tag) => <Chip key={tag}>{tag.replace(/[-_]+/g, " ")}</Chip>)}
                {contact.archived_at && <Chip className="border-amber-200 bg-amber-50 text-amber-800">Archived</Chip>}
              </div>
            </SheetHeader>

            {contact.archived_at && (
              <div className="flex flex-col gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm text-amber-900">This contact is archived, so they're hidden from your contact list.</p>
                <Button size="sm" variant="outline" disabled={saving} onClick={() => setArchived(false)} data-testid="contact-restore"><ArchiveRestore className="mr-1.5 h-4 w-4" />Restore</Button>
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              {contact.phone && <Button asChild size="sm" className="cv-action-primary"><a href={`tel:${contact.phone}`} data-testid="contact-call"><Phone className="mr-1.5 h-4 w-4" />Call {contact.phone}</a></Button>}
              {contact.phone && <Button asChild size="sm" variant="outline"><a href={`sms:${contact.phone}`} data-testid="contact-text"><MessageSquare className="mr-1.5 h-4 w-4" />Text</a></Button>}
              {contact.email && <Button asChild size="sm" variant="outline"><a href={`mailto:${contact.email}`} data-testid="contact-email"><Mail className="mr-1.5 h-4 w-4" />Email</a></Button>}
              {!editing && <Button size="sm" variant="outline" onClick={() => setEditing(true)} data-testid="contact-edit"><Pencil className="mr-1.5 h-4 w-4" />{contact.phone ? "Edit" : "Edit · add phone"}</Button>}
            </div>

            {editing ? (
              <EditForm contact={contact} companies={companies} members={members} isAdmin={isAdmin} saving={saving} onSave={save} onCancel={() => setEditing(false)} />
            ) : (
              <section>
                <SectionTitle>Details</SectionTitle>
                <dl>
                  <Row label="Phone">{contact.phone ? <a className="font-semibold text-[#127b96]" href={`tel:${contact.phone}`}>{contact.phone}</a> : <span className="text-slate-400">Not added yet</span>}</Row>
                  <Row label="Email">{contact.email ? <a className="font-semibold text-[#127b96]" href={`mailto:${contact.email}`}>{contact.email}</a> : <span className="text-slate-400">Not added yet</span>}</Row>
                  {company && <Row label="Company">{company.name}</Row>}
                  {contact.role && <Row label="Role">{contact.role}</Row>}
                  {contact.title && <Row label="Job title">{contact.title}</Row>}
                  <Row label="Owner">{ownerLabel}</Row>
                  {workspace && <Row label="Client workspace"><Link className="font-semibold text-[#127b96]" to={`/workspaces/${workspace.id}`}>{workspace.name}</Link></Row>}
                  <Row label="Added">{fullDateLabel(contact.created_at) || "—"}</Row>
                </dl>
              </section>
            )}

            {!contact.archived_at && <LogActivity openRequests={openRequests} saving={logging} onSave={logActivity} />}

            <section>
              <SectionTitle count={requests.length}>Website requests</SectionTitle>
              {requests.length ? (
                <ul className="space-y-2">
                  {requests.map((lead) => (
                    <li key={lead.id}>
                      <Link to={`/leads?lead=${lead.id}`} className="flex items-start justify-between gap-3 rounded-xl border border-slate-200 px-3 py-2.5 hover:bg-slate-50" data-testid={`contact-request-${lead.id}`}>
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-semibold text-[#132038]">{lead.form_name || "Website form"}</span>
                          <span className="block truncate text-xs text-slate-500">{[lead.property_address, lead.listing_id && `MLS ${lead.listing_id}`, agoLabel(lead.received_at)].filter(Boolean).join(" · ")}</span>
                        </span>
                        <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${LEAD_STATUS_STYLE[lead.status] || LEAD_STATUS_STYLE.closed}`}>{LEAD_STATUS_LABEL[lead.status] || lead.status}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : <p className="text-sm text-slate-500">No website requests from this person yet.</p>}
            </section>

            <section>
              <SectionTitle count={detail.deals.length}>Deals</SectionTitle>
              {detail.deals.length ? (
                <ul className="space-y-2">
                  {detail.deals.map((deal) => (
                    <li key={deal.id}>
                      <Link to={`/deals?deal=${deal.id}`} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 px-3 py-2.5 hover:bg-slate-50" data-testid={`contact-deal-${deal.id}`}>
                        <span className="flex min-w-0 items-center gap-2.5">
                          <GitBranch className="h-4 w-4 shrink-0 text-slate-400" />
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-semibold text-[#132038]">{deal.name}</span>
                            <span className="block text-xs text-slate-500">{stageLabel(deal.stage)}{deal.archived_at ? " · Archived" : ""}</span>
                          </span>
                        </span>
                        <span className="shrink-0 font-display text-sm font-bold text-[#132038]">{formatMoney(deal.value, deal.currency || "USD")}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : <p className="text-sm text-slate-500">No deals with this person yet.</p>}
            </section>

            <section>
              <SectionTitle>History</SectionTitle>
              <ActivityFeed entries={history} limit={15} empty="Nothing has been logged yet. Calls, texts and notes you save appear here." testId="contact-history" />
            </section>

            {!contact.archived_at && (
              <section className="border-t border-slate-100 pt-4">
                <Button variant="outline" size="sm" className="text-red-700" disabled={saving} onClick={() => setArchived(true)} data-testid="contact-archive"><Archive className="mr-1.5 h-4 w-4" />Archive contact</Button>
                <p className="mt-1.5 text-xs text-slate-500">Hides them from your contact list. Nothing is deleted, and you can restore them any time.</p>
              </section>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
