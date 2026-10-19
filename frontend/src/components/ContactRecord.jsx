/* A contact's record: who they are, how to reach them, what has happened with them, and
   their deals, tasks and website requests. Opens as a side panel (full width on a phone)
   from the contact list or straight from a link to /contacts?contact=<id>.

   Layout follows the record pattern used across the app: a header (avatar, name, one meta
   line, actions), a main column of tabs, and a details panel on the right. On narrow
   screens the details panel becomes a "Details" tab. RecordLayout is shared with the
   company record in pages/Directory. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr, formatMoney } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import {
  ACTIVITY_KINDS, CALL_OUTCOMES, LEAD_STATUS_LABEL, OUTREACH_KINDS,
  agoLabel, fullDateLabel, historyEntries, stageLabel,
} from "@/lib/contactHistory";
import { lifecycleOf, LIFECYCLE } from "@/lib/recordFields";
import { Avatar, PropertyList, StatusDot } from "@/components/page/Page";
import { CustomFieldsSection } from "@/components/CustomFields";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Archive, ArchiveRestore, CalendarDays, CheckCircle2, Circle, CircleAlert, Globe, GitBranch,
  ListTodo, Mail, MessageSquare, Pencil, Phone, StickyNote, UserRound,
} from "lucide-react";

const NONE = "none";
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const KIND_ICON = { call: Phone, text: MessageSquare, email: Mail, meeting: CalendarDays, note: StickyNote, request: Globe, event: UserRound };
// Timeline markers are neutral circles; only the glyph carries the kind's colour.
const KIND_STYLE = {
  call: "text-emerald-600", text: "text-brand", email: "text-violet-600", meeting: "text-amber-600",
  note: "text-muted-foreground", request: "text-brand", event: "text-muted-foreground",
};
const INFLUENCE = [["low", "Low"], ["medium", "Medium"], ["high", "High"]];
const RELATIONSHIP = [["positive", "Good"], ["neutral", "Neutral"], ["negative", "At risk"]];
const RELATIONSHIP_TONE = { positive: "success", neutral: "neutral", negative: "danger" };
const LEAD_TONE = { new: "warning", responded: "success", closed: "neutral", spam: "danger" };

/* ---------- Shared record layout (also used by the company record) ---------- */

/** The side panel itself: full width on a phone, wide enough for two columns on a laptop. */
export const RECORD_SHEET = "flex w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl lg:max-w-[min(1040px,calc(100vw-4rem))]";
const TAB_LIST = "sticky top-0 z-10 -mx-5 flex h-auto justify-start gap-3 overflow-x-auto rounded-none border-b border-border bg-background p-0 px-5 sm:-mx-6 sm:gap-5 sm:px-6";
const TAB_TRIGGER = "group -mb-px h-10 shrink-0 gap-1 rounded-none border-b-2 border-transparent px-0 text-[13px] sm:gap-1.5 sm:px-0.5 text-muted-foreground data-[state=active]:border-foreground data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none";

const DOT = { neutral: "bg-muted-foreground/50", brand: "bg-brand", success: "bg-emerald-500", warning: "bg-amber-500", danger: "bg-red-500", info: "bg-sky-500", violet: "bg-violet-500" };
/** StatusDot at meta size (12px), for secondary lines and compact rows. */
export function MiniStatus({ tone = "neutral", children, className = "" }) {
  return <span className={`inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-muted-foreground ${className}`}><span className={`size-1.5 shrink-0 rounded-full ${DOT[tone] || DOT.neutral}`} aria-hidden="true" />{children}</span>;
}

/** True on screens wide enough to show the details panel beside the tabs. */
export function useWideLayout(query = "(min-width: 1024px)") {
  const [wide, setWide] = useState(() => typeof window !== "undefined" && !!window.matchMedia?.(query).matches);
  useEffect(() => {
    const media = window.matchMedia?.(query);
    if (!media) return undefined;
    const update = () => setWide(media.matches);
    update();
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, [query]);
  return wide;
}

/** A small, quiet empty state for the inside of a record tab. */
export function RecordEmpty({ icon: Icon = StickyNote, title, children }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-10 text-center">
      <span className="flex size-9 items-center justify-center rounded-full bg-muted text-muted-foreground"><Icon className="size-4" aria-hidden="true" /></span>
      {title && <p className="mt-3 text-[13px] font-medium text-foreground">{title}</p>}
      {children && <p className="mt-1 max-w-xs text-xs leading-5 text-muted-foreground">{children}</p>}
    </div>
  );
}

/** One bordered list of related records (deals, tasks, requests…). */
export function RecordList({ children }) {
  return <ul className="divide-y divide-border/70 overflow-hidden rounded-xl border border-border bg-card">{children}</ul>;
}

/**
 * Header + tabs + details panel. `tabs`: [{ value, label, count, testid, content }]. On
 * wide screens `details` sits in a right-hand panel; otherwise it is the second tab.
 */
export function RecordLayout({ avatar, title, meta, flag, actions, banner, tabs, value, onValueChange, details, detailsTitle = "Details", wide }) {
  const first = tabs[0]?.value;
  const listRef = useRef(null);
  useEffect(() => { if (wide && value === "details" && first) onValueChange(first); }, [wide, value, first, onValueChange]);
  // On a phone the tab row scrolls sideways; keep the selected tab in view when it changes.
  useEffect(() => { listRef.current?.querySelector("[data-state='active']")?.scrollIntoView?.({ block: "nearest", inline: "nearest" }); }, [value]);
  // Without room for a side panel, details become the second tab, right after the first.
  const allTabs = wide ? tabs : [tabs[0], { value: "details", label: "Details", content: details }, ...tabs.slice(1)].filter(Boolean);
  return (
    <>
      <div className="shrink-0 border-b border-border px-5 pb-4 pt-5 sm:px-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:pr-8">
          <div className="flex min-w-0 items-center gap-3 pr-8 sm:pr-0">
            {avatar}
            <SheetHeader className="min-w-0 space-y-0.5 text-left">
              <div className="flex min-w-0 items-center gap-2">
                <SheetTitle className="truncate text-lg font-semibold leading-6 tracking-tight text-foreground">{title}</SheetTitle>
                {flag}
              </div>
              <SheetDescription className="truncate text-[13px] leading-5">{meta}</SheetDescription>
            </SheetHeader>
          </div>
          {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
        </div>
      </div>
      {banner}
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-y-auto px-5 pb-10 sm:px-6">
          <Tabs value={value} onValueChange={onValueChange}>
            <TabsList ref={listRef} className={TAB_LIST}>
              {allTabs.map((tab) => (
                <TabsTrigger key={tab.value} value={tab.value} className={TAB_TRIGGER} data-testid={tab.testid}>
                  {tab.label}
                  {tab.count != null && <span className="tabular rounded px-1 text-xs text-muted-foreground group-data-[state=active]:bg-muted group-data-[state=active]:text-foreground">{tab.count}</span>}
                </TabsTrigger>
              ))}
            </TabsList>
            {allTabs.map((tab) => <TabsContent key={tab.value} value={tab.value} className="mt-4">{tab.content}</TabsContent>)}
          </Tabs>
        </div>
        {wide && (
          <aside className="flex w-80 shrink-0 flex-col border-l border-border" aria-label={detailsTitle}>
            <div className="flex h-10 shrink-0 items-center border-b border-border px-5 text-[13px] font-semibold text-foreground">{detailsTitle}</div>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-6 pt-2">{details}</div>
          </aside>
        )}
      </div>
    </>
  );
}

/** Loading placeholder shaped like the record. */
export function RecordSkeleton({ label = "Loading" }) {
  return (
    <>
      <SheetHeader className="sr-only"><SheetTitle>{label}</SheetTitle><SheetDescription>Loading</SheetDescription></SheetHeader>
      <div className="flex items-center gap-3 border-b border-border px-6 pb-4 pt-5">
        <Skeleton className="size-11 rounded-full" />
        <div className="space-y-2"><Skeleton className="h-5 w-44" /><Skeleton className="h-3.5 w-28" /></div>
      </div>
      <div className="space-y-4 px-6 py-4">
        <div className="flex gap-5 border-b border-border pb-3">{[56, 44, 40, 60].map((width) => <Skeleton key={width} className="h-4" style={{ width }} />)}</div>
        <Skeleton className="h-28 w-full rounded-xl" />
        {Array.from({ length: 4 }).map((_, index) => <div key={index} className="flex gap-3"><Skeleton className="size-6 rounded-full" /><div className="flex-1 space-y-1.5"><Skeleton className="h-3.5 w-48" /><Skeleton className="h-3 w-32" /></div></div>)}
      </div>
    </>
  );
}

/** Centred error for a record that could not be opened. */
export function RecordError({ message, title = "Record", onBack, backLabel }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
      <SheetHeader className="sr-only"><SheetTitle>{title}</SheetTitle><SheetDescription>{message}</SheetDescription></SheetHeader>
      <span className="flex size-10 items-center justify-center rounded-full bg-muted"><CircleAlert className="size-5 text-amber-600" aria-hidden="true" /></span>
      <p className="mt-3 max-w-sm text-[13px] leading-5 text-muted-foreground">{message}</p>
      <Button variant="outline" size="sm" className="mt-4" onClick={onBack}>{backLabel}</Button>
    </div>
  );
}

/* ---------- Activity ---------- */

/** A list of history entries (see lib/contactHistory), drawn as a timeline. Shared with the Leads inbox. */
export function ActivityFeed({ entries, empty, limit, testId }) {
  const [showAll, setShowAll] = useState(false);
  if (!entries.length) return <p className="text-[13px] text-muted-foreground">{empty}</p>;
  const visible = showAll || !limit ? entries : entries.slice(0, limit);
  return (
    <div>
      <ol data-testid={testId}>
        {visible.map((entry, index) => {
          const Icon = KIND_ICON[entry.kind] || StickyNote;
          const last = index === visible.length - 1;
          return (
            <li key={entry.id} className={`relative flex gap-3 ${last ? "" : "pb-5"}`}>
              {!last && <span className="absolute bottom-0 left-3 top-7 w-px bg-border" aria-hidden="true" />}
              <span className={`relative flex size-6 shrink-0 items-center justify-center rounded-full border border-border bg-card ${KIND_STYLE[entry.kind] || KIND_STYLE.note}`}><Icon className="size-3.5" aria-hidden="true" /></span>
              <div className="min-w-0 flex-1 pt-0.5">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <span className="text-[13px] font-medium leading-5 text-foreground">{entry.title}</span>
                  <span className="tabular shrink-0 text-xs text-muted-foreground" title={fullDateLabel(entry.at)}>{agoLabel(entry.at)}</span>
                </div>
                {entry.subject && <div className="text-[13px] leading-5 text-foreground/80">{entry.subject}</div>}
                {entry.body && <p className="mt-0.5 whitespace-pre-wrap break-words text-[13px] leading-5 text-muted-foreground">{entry.body}</p>}
                {(entry.who || entry.leadId) && (
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    {entry.who}
                    {entry.leadId && <>{entry.who ? " · " : ""}<Link className="font-medium text-brand-strong hover:underline" to={`/leads?lead=${entry.leadId}`}>Open request</Link></>}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {limit && entries.length > limit && (
        <Button variant="ghost" size="sm" className="ml-7 mt-2 px-2 text-[13px] text-brand-strong" onClick={() => setShowAll((value) => !value)}>
          {showAll ? "Show less" : `Show all ${entries.length}`}
        </Button>
      )}
    </div>
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
    <section data-testid="contact-log" aria-labelledby="contact-log-title">
      <h3 id="contact-log-title" className="mb-2 text-xs font-medium text-muted-foreground">Log what happened</h3>
      <div className="rounded-xl border border-border bg-card shadow-xs transition-colors focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/15">
        <div className="flex flex-wrap items-center gap-1 border-b border-border/70 px-2 py-1.5" role="radiogroup" aria-label="What kind of activity">
          {ACTIVITY_KINDS.map((entry) => {
            const Icon = KIND_ICON[entry.key];
            const active = entry.key === kind;
            return (
              <button key={entry.key} type="button" role="radio" aria-checked={active} onClick={() => setKind(entry.key)}
                className={`inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-[13px] font-medium transition-colors ${active ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"}`}
                data-testid={`contact-log-type-${entry.key}`}>
                <Icon className="hidden size-3.5 sm:block" aria-hidden="true" />{entry.label}
              </button>
            );
          })}
        </div>
        {kind === "call" && (
          <div className="flex flex-wrap items-center gap-1.5 px-3 pt-2.5" role="radiogroup" aria-label="How did the call go">
            <span className="mr-1 text-xs text-muted-foreground">How did it go?</span>
            {CALL_OUTCOMES.map((entry) => (
              <button key={entry.key} type="button" role="radio" aria-checked={outcome === entry.key} onClick={() => setOutcome(outcome === entry.key ? "" : entry.key)}
                className={`h-6 rounded-full border px-2.5 text-xs font-medium transition-colors ${outcome === entry.key ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-border text-muted-foreground hover:bg-muted/50 hover:text-foreground"}`}
                data-testid={`contact-log-outcome-${entry.key}`}>
                {entry.label}
              </button>
            ))}
          </div>
        )}
        <Textarea rows={3} value={text} onChange={(event) => setText(event.target.value)} placeholder={current.placeholder} aria-label="Details"
          className="min-h-[76px] resize-none border-0 bg-transparent px-3 py-2.5 text-[13px] shadow-none focus-visible:ring-0 md:text-[13px]" data-testid="contact-log-text" />
        <div className="flex flex-col gap-2 border-t border-border/70 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-muted-foreground">
            {OUTREACH_KINDS.has(kind) && openRequests > 0
              ? `Saving this marks their new website request${openRequests === 1 ? "" : "s"} as contacted.`
              : "Saved to their history. Nothing is sent to them."}
          </p>
          <Button size="sm" className="cv-action-primary shrink-0 self-end sm:self-auto" disabled={saving} onClick={submit} data-testid="contact-log-save">
            {saving ? "Saving…" : `Save ${current.label.toLowerCase()}`}
          </Button>
        </div>
      </div>
    </section>
  );
}

/* ---------- Details ---------- */

function formFrom(contact) {
  return {
    name: contact.name || "", phone: contact.phone || "", email: contact.email || "",
    company_id: contact.company_id || NONE, role: contact.role || "", title: contact.title || "",
    owner: contact.owner || NONE, influence: contact.influence || "medium", sentiment: contact.sentiment || "neutral",
    lifecycle: contact.lifecycle || NONE,
  };
}

const FIELD_INPUT = "h-8 text-[13px] md:text-[13px]";
const FIELD_LABEL = "text-xs font-medium text-muted-foreground";

function EditForm({ contact, companies, members, isAdmin, saving, onSave, onCancel }) {
  const [form, setForm] = useState(() => formFrom(contact));
  // The Edit button disappears while editing, so move focus into the form rather than losing it.
  const nameRef = useRef(null);
  useEffect(() => { nameRef.current?.focus(); }, []);
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
      lifecycle: form.lifecycle === NONE ? null : form.lifecycle,
    };
    if (isAdmin) payload.owner = form.owner === NONE ? null : form.owner;
    onSave(payload);
  };
  return (
    <section className="space-y-3" data-testid="contact-edit-form" aria-labelledby="contact-edit-title">
      <h3 id="contact-edit-title" className="sr-only">Edit details</h3>
      <div className="grid gap-1.5"><Label htmlFor="contact-name" className={FIELD_LABEL}>Name <span className="text-red-600">*</span></Label><Input ref={nameRef} id="contact-name" className={FIELD_INPUT} value={form.name} onChange={(event) => setField("name", event.target.value)} data-testid="contact-edit-name" /></div>
      <div className="grid gap-1.5"><Label htmlFor="contact-phone" className={FIELD_LABEL}>Phone</Label><Input id="contact-phone" className={FIELD_INPUT} type="tel" inputMode="tel" autoComplete="tel" value={form.phone} onChange={(event) => setField("phone", event.target.value)} placeholder="(555) 010-0100" data-testid="contact-edit-phone" /></div>
      <div className="grid gap-1.5"><Label htmlFor="contact-email" className={FIELD_LABEL}>Email</Label><Input id="contact-email" className={FIELD_INPUT} type="email" inputMode="email" value={form.email} onChange={(event) => setField("email", event.target.value)} placeholder="name@example.com" data-testid="contact-edit-email" /></div>
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-1.5"><Label htmlFor="contact-role" className={FIELD_LABEL}>Role</Label><Input id="contact-role" className={FIELD_INPUT} value={form.role} onChange={(event) => setField("role", event.target.value)} placeholder="e.g. Buyer" data-testid="contact-edit-role" /></div>
        <div className="grid gap-1.5"><Label htmlFor="contact-title" className={FIELD_LABEL}>Job title</Label><Input id="contact-title" className={FIELD_INPUT} value={form.title} onChange={(event) => setField("title", event.target.value)} placeholder="Optional" data-testid="contact-edit-title" /></div>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="contact-lifecycle" className={FIELD_LABEL}>Lifecycle stage</Label>
        <Select value={form.lifecycle} onValueChange={(value) => setField("lifecycle", value)}>
          <SelectTrigger id="contact-lifecycle" className="h-8 text-[13px]" data-testid="contact-edit-lifecycle"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={NONE}>Not set</SelectItem>
            {LIFECYCLE.map((stage) => <SelectItem key={stage.value} value={stage.value}>{stage.label}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="contact-company" className={FIELD_LABEL}>Company</Label>
        <Select value={form.company_id} onValueChange={(value) => setField("company_id", value)}>
          <SelectTrigger id="contact-company" className="h-8 text-[13px]" data-testid="contact-edit-company"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={NONE}>No company</SelectItem>
            {companies.map((company) => <SelectItem key={company.id} value={company.id}>{company.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      {isAdmin && (
        <div className="grid gap-1.5">
          <Label htmlFor="contact-owner" className={FIELD_LABEL}>Owner</Label>
          <Select value={form.owner} onValueChange={(value) => setField("owner", value)}>
            <SelectTrigger id="contact-owner" className="h-8 text-[13px]" data-testid="contact-edit-owner"><SelectValue /></SelectTrigger>
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
          <Label htmlFor="contact-influence" className={FIELD_LABEL}>Influence</Label>
          <Select value={form.influence} onValueChange={(value) => setField("influence", value)}>
            <SelectTrigger id="contact-influence" className="h-8 text-[13px]" data-testid="contact-edit-influence"><SelectValue /></SelectTrigger>
            <SelectContent>{INFLUENCE.map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="contact-relationship" className={FIELD_LABEL}>Relationship</Label>
          <Select value={form.sentiment} onValueChange={(value) => setField("sentiment", value)}>
            <SelectTrigger id="contact-relationship" className="h-8 text-[13px]" data-testid="contact-edit-relationship"><SelectValue /></SelectTrigger>
            <SelectContent>{RELATIONSHIP.map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent>
          </Select>
        </div>
      </div>
      <div className="flex justify-end gap-2 border-t border-border pt-3">
        <Button size="sm" variant="outline" disabled={saving} onClick={onCancel} data-testid="contact-edit-cancel">Cancel</Button>
        <Button size="sm" className="cv-action-primary" disabled={saving} onClick={submit} data-testid="contact-save">{saving ? "Saving…" : "Save changes"}</Button>
      </div>
    </section>
  );
}

// brand-strong rather than brand: small link text needs 4.5:1 on the dark background too.
const linkClass = "font-medium text-brand-strong hover:underline";
// Long addresses are cut short in the narrow details panel; the full value is in the tooltip and the link.
const longLinkClass = `${linkClass} block truncate`;
const notSet = (text = "Not added yet") => <span className="text-muted-foreground">{text}</span>;

/* ---------- Related lists ---------- */

function dueLabel(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", ...(sameYear ? {} : { year: "numeric" }) });
}

function stageTone(stage) {
  const key = String(stage || "");
  if (/won/.test(key)) return "success";
  if (/lost/.test(key)) return "danger";
  return key === "lead" ? "neutral" : "brand";
}

function DealsList({ deals }) {
  if (!deals.length) return <RecordEmpty icon={GitBranch} title="No deals yet">No deals with this person yet.</RecordEmpty>;
  return (
    <RecordList>
      {deals.map((deal) => (
        <li key={deal.id}>
          <Link to={`/deals?deal=${deal.id}`} className="flex items-center gap-3 px-3 py-2.5 transition-colors hover:bg-muted/50" data-testid={`contact-deal-${deal.id}`}>
            <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground"><GitBranch className="size-3.5" aria-hidden="true" /></span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-medium text-foreground">{deal.name}</span>
              <MiniStatus tone={stageTone(deal.stage)}>{stageLabel(deal.stage)}{deal.archived_at ? " · Archived" : ""}</MiniStatus>
            </span>
            <span className="tabular shrink-0 text-[13px] font-semibold text-foreground">{formatMoney(deal.value, deal.currency || "USD")}</span>
          </Link>
        </li>
      ))}
    </RecordList>
  );
}

function TasksList({ tasks }) {
  if (!tasks.length) return <RecordEmpty icon={ListTodo} title="No tasks">No tasks about this person yet.</RecordEmpty>;
  return (
    <RecordList>
      {tasks.map((task) => {
        const done = task.status === "done";
        const overdue = !done && task.status !== "cancelled" && task.due_date && new Date(task.due_date).getTime() < Date.now();
        const meta = [task.due_date ? `Due ${dueLabel(task.due_date)}` : "No due date", task.priority === "high" ? "High priority" : null, task.status === "cancelled" ? "Cancelled" : null].filter(Boolean).join(" · ");
        return (
          <li key={task.id}>
            <Link to={`/tasks?task=${task.id}`} className="flex items-center gap-3 px-3 py-2.5 transition-colors hover:bg-muted/50" data-testid={`contact-task-${task.id}`}>
              {done ? <CheckCircle2 className="size-4 shrink-0 text-emerald-600" aria-label="Done" /> : <Circle className="size-4 shrink-0 text-muted-foreground" aria-label="To do" />}
              <span className="min-w-0 flex-1">
                <span className={`block truncate text-[13px] font-medium ${done ? "text-muted-foreground line-through" : "text-foreground"}`}>{task.title}</span>
                <span className="block truncate text-xs text-muted-foreground">{meta}</span>
              </span>
              {overdue && <span className="shrink-0 rounded border border-red-200 bg-red-50 px-1.5 py-px text-[11px] font-medium text-red-700">Overdue</span>}
            </Link>
          </li>
        );
      })}
    </RecordList>
  );
}

function RequestsList({ requests }) {
  if (!requests.length) return <RecordEmpty icon={Globe} title="No website requests">No website requests from this person yet.</RecordEmpty>;
  return (
    <RecordList>
      {requests.map((lead) => (
        <li key={lead.id}>
          <Link to={`/leads?lead=${lead.id}`} className="flex items-center justify-between gap-3 px-3 py-2.5 transition-colors hover:bg-muted/50" data-testid={`contact-request-${lead.id}`}>
            <span className="flex min-w-0 items-center gap-3">
              <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground"><Globe className="size-3.5" aria-hidden="true" /></span>
              <span className="min-w-0">
                <span className="block truncate text-[13px] font-medium text-foreground">{lead.form_name || "Website form"}</span>
                <span className="block truncate text-xs text-muted-foreground">{[lead.property_address, lead.listing_id && `MLS ${lead.listing_id}`, agoLabel(lead.received_at)].filter(Boolean).join(" · ")}</span>
              </span>
            </span>
            <StatusDot tone={LEAD_TONE[lead.status] || "neutral"} className="shrink-0">{LEAD_STATUS_LABEL[lead.status] || lead.status}</StatusDot>
          </Link>
        </li>
      ))}
    </RecordList>
  );
}

/* ---------- The record ---------- */

export default function ContactRecord({ contactId, open, onOpenChange, companies = [], workspaces = [], onChanged }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const wide = useWideLayout();
  const [detail, setDetail] = useState(null);
  const [requests, setRequests] = useState([]);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [members, setMembers] = useState([]);
  const [saving, setSaving] = useState(false);
  const [logging, setLogging] = useState(false);
  const [tab, setTab] = useState("activity");

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

  useEffect(() => { setDetail(null); setRequests([]); setError(""); setEditing(false); setTab("activity"); load(); }, [load]);
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

  const startEditing = () => { setEditing(true); if (!wide) setTab("details"); };

  const ownerLabel = detail?.owner_name || contact?.owner || "Nobody yet";
  const source = contact?.source?.kind === "website_form"
    ? `From your website${contact.source.form_name ? ` · ${contact.source.form_name}` : ""}`
    : contact?.lead_source ? contact.lead_source.charAt(0).toUpperCase() + contact.lead_source.slice(1) : null;
  const tags = (contact?.tags || []).filter((tag) => tag !== "website-lead");
  const relationship = RELATIONSHIP.find(([value]) => value === (contact?.sentiment || "neutral"));
  const influence = INFLUENCE.find(([value]) => value === (contact?.influence || "medium"));
  const lifecycle = lifecycleOf(contact?.lifecycle);

  const details = contact && (editing ? (
    <EditForm contact={contact} companies={companies} members={members} isAdmin={isAdmin} saving={saving} onSave={save} onCancel={() => setEditing(false)} />
  ) : (
    <div>
      <section aria-labelledby="contact-details-title">
        <h3 id="contact-details-title" className="sr-only">Details</h3>
        <PropertyList items={[
          { label: "Phone", value: contact.phone ? <a className={linkClass} href={`tel:${contact.phone}`}>{contact.phone}</a> : notSet() },
          { label: "Email", value: contact.email ? <a className={longLinkClass} href={`mailto:${contact.email}`} title={contact.email}>{contact.email}</a> : notSet() },
          { label: "Lifecycle", value: lifecycle ? <StatusDot tone={lifecycle.tone}>{lifecycle.label}</StatusDot> : notSet("Not set"), testid: "contact-lifecycle" },
          company && { label: "Company", value: company.name },
          contact.role && { label: "Role", value: contact.role },
          contact.title && { label: "Job title", value: contact.title },
          { label: "Owner", value: ownerLabel },
          { label: "Relationship", value: <StatusDot tone={RELATIONSHIP_TONE[contact.sentiment] || "neutral"}>{relationship?.[1] || "Neutral"}</StatusDot> },
          { label: "Influence", value: influence?.[1] || "Medium" },
          source && { label: "Source", value: source },
          tags.length > 0 && { label: "Tags", value: <span className="flex flex-wrap gap-1">{tags.map((tag) => <span key={tag} className="rounded-md bg-muted px-1.5 py-0.5 text-xs text-foreground/80">{tag.replace(/[-_]+/g, " ")}</span>)}</span> },
          workspace && { label: "Client workspace", value: <Link className={linkClass} to={`/workspaces/${workspace.id}`}>{workspace.name}</Link> },
          { label: "Added", value: fullDateLabel(contact.created_at) || "—" },
        ].filter(Boolean)} />
      </section>
      <CustomFieldsSection object="contacts" endpoint={`/contacts/${contact.id}`} values={contact.custom_fields} isAdmin={isAdmin} disabled={Boolean(contact.archived_at)}
        onSaved={async () => { await load(); onChanged?.(); }} testid="contact-fields" />
      {!contact.archived_at && (
        <section className="mt-6 border-t border-border pt-4">
          <Button variant="outline" size="sm" className="text-red-700" disabled={saving} onClick={() => setArchived(true)} data-testid="contact-archive"><Archive className="size-3.5" />Archive contact</Button>
          <p className="mt-1.5 text-xs leading-5 text-muted-foreground">Hides them from your contact list. Nothing is deleted, and you can restore them any time.</p>
        </section>
      )}
    </div>
  ));

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className={RECORD_SHEET} data-testid="contact-record">
        {error ? (
          <RecordError title="Contact" message={error} onBack={() => onOpenChange(false)} backLabel="Back to contacts" />
        ) : !contact ? (
          <RecordSkeleton label="Loading contact" />
        ) : (
          <RecordLayout
            wide={wide}
            avatar={<Avatar name={contact.name} size="lg" />}
            title={contact.name}
            meta={[contact.role, contact.title, company?.name].filter(Boolean).join(" · ") || "Contact"}
            flag={contact.archived_at && <span className="shrink-0 rounded border border-amber-200 bg-amber-50 px-1.5 py-px text-[11px] font-medium text-amber-700">Archived</span>}
            actions={<>
              {contact.phone && <Button asChild size="sm" className="cv-action-primary"><a href={`tel:${contact.phone}`} data-testid="contact-call"><Phone className="size-3.5" />Call {contact.phone}</a></Button>}
              {contact.phone && <Button asChild size="sm" variant="outline"><a href={`sms:${contact.phone}`} aria-label="Text" data-testid="contact-text"><MessageSquare className="size-3.5" /><span className="hidden sm:inline">Text</span></a></Button>}
              {contact.email && <Button asChild size="sm" variant="outline"><a href={`mailto:${contact.email}`} aria-label="Email" data-testid="contact-email"><Mail className="size-3.5" /><span className="hidden sm:inline">Email</span></a></Button>}
              {!editing && <Button size="sm" variant="outline" onClick={startEditing} data-testid="contact-edit"><Pencil className="size-3.5" />{contact.phone ? "Edit" : "Edit · add phone"}</Button>}
            </>}
            banner={contact.archived_at && (
              <div className="mx-5 mb-2 mt-4 flex flex-col gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-700 sm:mx-6 sm:flex-row sm:items-center sm:justify-between">
                <span className="flex items-center gap-2"><Archive className="size-4 shrink-0" aria-hidden="true" />This contact is archived, so they're hidden from your contact list.</span>
                <Button size="sm" variant="outline" className="h-7 shrink-0 self-start sm:self-auto" disabled={saving} onClick={() => setArchived(false)} data-testid="contact-restore"><ArchiveRestore className="size-3.5" />Restore</Button>
              </div>
            )}
            value={tab}
            onValueChange={setTab}
            details={details}
            detailsTitle={editing ? "Edit details" : "Details"}
            tabs={[
              {
                value: "activity", label: "Activity", count: history.length, testid: "contact-tab-activity",
                content: (
                  <div className="space-y-6">
                    {!contact.archived_at && <LogActivity openRequests={openRequests} saving={logging} onSave={logActivity} />}
                    <section aria-labelledby="contact-history-title">
                      <h3 id="contact-history-title" className="mb-3 text-xs font-medium text-muted-foreground">History</h3>
                      {history.length
                        ? <ActivityFeed entries={history} limit={15} empty="Nothing has been logged yet. Calls, texts and notes you save appear here." testId="contact-history" />
                        : <RecordEmpty icon={CalendarDays} title="No history yet">Nothing has been logged yet. Calls, texts and notes you save appear here.</RecordEmpty>}
                    </section>
                  </div>
                ),
              },
              { value: "deals", label: "Deals", count: detail.deals.length, testid: "contact-tab-deals", content: <DealsList deals={detail.deals} /> },
              { value: "tasks", label: "Tasks", count: (detail.tasks || []).length, testid: "contact-tab-tasks", content: <TasksList tasks={detail.tasks || []} /> },
              {
                value: "requests", count: requests.length, testid: "contact-tab-requests",
                label: <><span className="sm:hidden">Requests</span><span className="hidden sm:inline">Website requests</span></>,
                content: <RequestsList requests={requests} />,
              },
            ]}
          />
        )}
      </SheetContent>
    </Sheet>
  );
}
