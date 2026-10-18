/* The deal record: one deal, opened from the board or from a link (`/deals?deal=<id>`).

   Everything an agent changes about a deal happens here -- name, value and currency,
   stage, close date, owner, the people on it and notes -- next to how it got here (stage
   history), what has happened on it (calls, notes, emails, meetings) and where it came
   from. Stage moves go through the board's own move, so the board, its totals and its
   toasts stay in step with the record. */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr, formatMoney } from "@/lib/api";
import { OUTCOME, currencyOptions, dateInputValue, dealCurrency, formatDay, isWebsiteLead, ownerLabel, ownerName, splitStages, stageOutcome } from "@/lib/pipeline";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import ContactPicker from "@/components/pipeline/ContactPicker";
import { Archive, ArrowRight, BriefcaseBusiness, Building2, CalendarDays, Globe, History, Mail, MessageSquareText, Phone, RotateCcw, StickyNote } from "lucide-react";

const NO_OWNER = "__none__";

const ACTIVITY_TYPES = [
  { key: "call", label: "Call", icon: Phone, placeholder: "What did you talk about? Any next step?" },
  { key: "note", label: "Note", icon: StickyNote, placeholder: "Anything worth remembering about this deal" },
  { key: "email", label: "Email", icon: Mail, placeholder: "What the email said (logging it does not send anything)" },
  { key: "meeting", label: "Meeting", icon: CalendarDays, placeholder: "Who was there and what was agreed" },
];
const ACTIVITY_ICON = { call: Phone, note: StickyNote, email: Mail, meeting: CalendarDays };

// Plain words for the fields a "details updated" entry names.
const FIELD_WORDS = { name: "name", value: "value", currency: "currency", owner: "owner", expected_close_date: "close date", contact_ids: "contacts", description: "notes", company_id: "company" };

function formFrom(deal, contacts) {
  return {
    name: deal.name || "",
    value: deal.value == null ? "" : String(deal.value),
    currency: dealCurrency(deal),
    expected_close_date: dateInputValue(deal.expected_close_date),
    owner: deal.owner || NO_OWNER,
    description: deal.description || "",
    contacts: (deal.contact_ids || []).map((id) => {
      const contact = (contacts || []).find((item) => item.id === id);
      return { id, name: contact?.name || contact?.email || "Unnamed contact" };
    }),
  };
}

/** Only the fields that actually changed, in the shape PATCH /opportunities/{id} takes. */
function changesBetween(form, deal) {
  const changes = {};
  if (form.name.trim() !== (deal.name || "")) changes.name = form.name.trim();
  const value = form.value === "" ? 0 : Number(form.value);
  if (value !== Number(deal.value || 0)) changes.value = value;
  if (form.currency !== dealCurrency(deal)) changes.currency = form.currency;
  if (form.expected_close_date !== dateInputValue(deal.expected_close_date)) changes.expected_close_date = form.expected_close_date || null;
  const owner = form.owner === NO_OWNER ? null : form.owner;
  if (owner !== (deal.owner || null)) changes.owner = owner;
  if (form.description !== (deal.description || "")) changes.description = form.description;
  const contactIds = form.contacts.map((contact) => contact.id);
  if (contactIds.join("|") !== (deal.contact_ids || []).join("|")) changes.contact_ids = contactIds;
  return changes;
}

function when(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric", hour: "numeric", minute: "2-digit" });
}

function stageOptionLabel(stage) {
  const outcome = stageOutcome(stage);
  if (outcome === OUTCOME.OPEN || new RegExp(outcome, "i").test(stage.label)) return stage.label;
  return `${stage.label} (${outcome})`;
}

export default function DealRecord({ dealId, stages, owners, workspaces, currentUser, onMove, onChanged }) {
  const [detail, setDetail] = useState(null);
  const [missing, setMissing] = useState(false);
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [moving, setMoving] = useState(false);
  const [forms, setForms] = useState([]);
  const [activity, setActivity] = useState({ type: "call", subject: "", body: "" });
  const [logging, setLogging] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/opportunities/${dealId}`);
      setDetail(data); setMissing(false);
      return data;
    } catch (requestError) {
      if (requestError.response?.status === 404) setMissing(true);
      else toast.error("This deal could not be loaded", { description: formatErr(requestError.response?.data?.detail) });
      return null;
    }
  }, [dealId]);

  useEffect(() => {
    setDetail(null); setForm(null); setMissing(false);
    load().then((data) => { if (data) setForm(formFrom(data.deal, data.contacts)); });
  }, [load]);

  const deal = detail?.deal;
  const website = isWebsiteLead(deal);
  useEffect(() => {
    if (!website) return;
    api.get("/website-forms").then((response) => setForms(response.data?.items || [])).catch(() => setForms([]));
  }, [website]);

  const allStages = useMemo(() => {
    const groups = splitStages(detail?.stages || stages);
    return [...groups.open, ...groups.won, ...groups.lost];
  }, [detail, stages]);
  const labelOf = useCallback((key) => allStages.find((stage) => stage.key === key)?.label || "a stage that no longer exists", [allStages]);
  const changes = useMemo(() => (form && deal ? changesBetween(form, deal) : {}), [form, deal]);
  const dirty = Object.keys(changes).length > 0;
  const setField = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const actorName = (actor) => {
    if (!actor) return "";
    if (actor === currentUser?.email) return "you";
    if (String(actor).startsWith("website_form:") || String(actor).startsWith("system:website")) return "your website";
    if (String(actor).startsWith("system")) return "ClientVerse";
    return ownerName(actor, owners);
  };

  if (missing) {
    return <div className="py-10 text-center"><SheetHeader className="items-center"><SheetTitle className="font-display text-lg font-semibold text-foreground">This deal could not be found</SheetTitle><SheetDescription>It may have been removed, or the link may be for a different account.</SheetDescription></SheetHeader></div>;
  }
  if (!detail || !form) {
    return <div className="space-y-4 py-2" aria-busy="true"><SheetHeader className="sr-only"><SheetTitle>Deal</SheetTitle><SheetDescription>Loading this deal</SheetDescription></SheetHeader><Skeleton className="h-8 w-2/3" /><Skeleton className="h-24 w-full" /><Skeleton className="h-48 w-full" /></div>;
  }

  const outcome = stageOutcome(detail.stage || {});
  const groups = splitStages(allStages);
  const openIndex = groups.open.findIndex((stage) => stage.key === deal.stage);
  const nextStage = outcome === OUTCOME.OPEN ? (openIndex >= 0 && openIndex < groups.open.length - 1 ? groups.open[openIndex + 1] : groups.won[0]) : null;
  const workspace = (workspaces || []).find((item) => item.opportunity_id === deal.id);
  const sourceForm = forms.find((item) => item.id === deal.source?.form_id);
  const basis = deal.value_basis;
  const ownerChoices = [...owners];
  if (deal.owner && !ownerChoices.some((owner) => owner.email === deal.owner)) ownerChoices.push({ email: deal.owner, name: null });
  const timeline = (detail.timeline || []).filter((entry) => !(entry.kind === "event" && String(entry.type || "").startsWith("activity.")));

  const save = async () => {
    if (!form.name.trim()) { toast.error("A deal needs a name."); return; }
    if ("value" in changes && (!Number.isFinite(changes.value) || changes.value < 0 || changes.value > 1e10)) { toast.error("Enter the value as a positive number, like 12500."); return; }
    setSaving(true);
    try {
      const { data } = await api.patch(`/opportunities/${deal.id}`, changes);
      const fresh = await load();
      if (fresh) setForm(formFrom(fresh.deal, fresh.contacts));
      onChanged({ ...data, contacts: form.contacts });
      toast.success("Deal saved");
    } catch (requestError) {
      toast.error("Your changes were not saved", { description: formatErr(requestError.response?.data?.detail) });
    } finally { setSaving(false); }
  };

  const moveTo = async (stageKey) => {
    if (!stageKey || stageKey === deal.stage) return;
    setMoving(true);
    const moved = await onMove(deal, stageKey);
    if (moved) await load();
    setMoving(false);
  };

  const logActivity = async () => {
    if (!activity.subject.trim() && !activity.body.trim()) { toast.error("Write a line about what happened first."); return; }
    setLogging(true);
    try {
      await api.post("/activities", { type: activity.type, related_type: "deal", related_id: deal.id, subject: activity.subject.trim() || null, body: activity.body.trim() || null });
      setActivity((current) => ({ ...current, subject: "", body: "" }));
      await load();
      toast.success(`${ACTIVITY_TYPES.find((item) => item.key === activity.type)?.label || "Activity"} logged`);
    } catch (requestError) {
      toast.error("That was not logged", { description: formatErr(requestError.response?.data?.detail) });
    } finally { setLogging(false); }
  };

  const setArchived = async (archive) => {
    try {
      const { data } = await api.post(`/opportunities/${deal.id}/${archive ? "archive" : "restore"}`, {});
      await load();
      onChanged({ ...data, contacts: form.contacts });
      toast.success(archive ? "Deal archived" : "Deal restored", { description: archive ? "It is off the board. You can restore it from this page." : "It is back on the board." });
    } catch (requestError) {
      toast.error(archive ? "The deal was not archived" : "The deal was not restored", { description: formatErr(requestError.response?.data?.detail) });
    }
  };

  const describeEvent = (entry) => {
    const payload = entry.payload || {};
    switch (entry.type) {
      case "opportunity.created": return "Deal created";
      case "opportunity.stage_changed":
      case "opportunity.closed_won":
      case "opportunity.closed_lost": return `Moved from ${labelOf(payload.from)} to ${labelOf(payload.to)}`;
      case "opportunity.updated": {
        const fields = (payload.changed || []).map((field) => FIELD_WORDS[field]).filter(Boolean);
        return fields.length ? `Changed the ${fields.join(", ")}` : "Details updated";
      }
      case "opportunity.archived": return "Archived";
      case "opportunity.restored": return "Restored";
      default: {
        const words = String(entry.type || "").split(".").pop().replace(/_/g, " ");
        return words ? words.charAt(0).toUpperCase() + words.slice(1) : "Updated";
      }
    }
  };

  return (
    <div className="space-y-6 pb-10" data-testid="deal-record">
      <SheetHeader className="space-y-1 pr-6">
        <SheetTitle className="font-display text-2xl leading-tight text-foreground" data-testid="deal-record-title">{deal.name}</SheetTitle>
        <SheetDescription className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-foreground">{formatMoney(deal.value, dealCurrency(deal))}</span>
          <span aria-hidden="true">·</span>
          <span>{labelOf(deal.stage)}</span>
          {website && <span className="inline-flex items-center gap-1 rounded-full border border-brand/20 bg-brand-soft px-2 py-0.5 text-[11px] font-semibold text-brand"><Globe className="h-3 w-3" />Website lead</span>}
          {deal.archived_at && <span className="rounded-full border border-slate-300 bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">Archived</span>}
        </SheetDescription>
      </SheetHeader>

      {deal.archived_at && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
          <span>Archived on {formatDay(deal.archived_at)}. It is not on the board or in your totals.</span>
          <Button size="sm" variant="outline" onClick={() => setArchived(false)} data-testid="deal-restore"><RotateCcw className="mr-1.5 h-4 w-4" />Restore</Button>
        </div>
      )}

      <section className="rounded-lg border border-slate-200 bg-slate-50/60 p-3" aria-label="Stage">
        <div className="flex flex-wrap items-end gap-2">
          <div className="grid min-w-[12rem] flex-1 gap-1.5">
            <Label htmlFor="deal-stage">Stage</Label>
            <Select value={deal.stage} onValueChange={moveTo} disabled={moving}>
              <SelectTrigger id="deal-stage" className="bg-white" data-testid="deal-stage-select"><SelectValue>{labelOf(deal.stage)}</SelectValue></SelectTrigger>
              <SelectContent>{allStages.map((stage) => <SelectItem key={stage.key} value={stage.key}>{stageOptionLabel(stage)}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          {nextStage && (
            <Button className="cv-action-primary" disabled={moving} onClick={() => moveTo(nextStage.key)} data-testid="deal-next-stage">
              {stageOutcome(nextStage) === OUTCOME.WON ? "Mark as won" : `Move to ${nextStage.label}`}<ArrowRight className="ml-1.5 h-4 w-4" />
            </Button>
          )}
        </div>
        {workspace && <Link to={`/workspaces/${workspace.id}`} className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-brand hover:underline" data-testid="deal-workspace-link"><BriefcaseBusiness className="h-4 w-4" />Open the client workspace</Link>}
      </section>

      {website && (
        <section className="rounded-lg border border-brand-soft bg-brand-soft/50 p-3 text-sm" aria-label="Where this deal came from">
          <div className="flex items-start gap-2">
            <Globe className="mt-0.5 h-4 w-4 shrink-0 text-brand" />
            <div className="min-w-0 space-y-1">
              <p className="font-semibold text-foreground">Came in through your website{sourceForm ? ` — “${sourceForm.name}”` : ""}</p>
              {basis?.method === "commission" && basis.price != null && <p className="text-slate-600">Value worked out as {basis.commission_rate}% commission on {formatMoney(basis.price, dealCurrency(deal))}, the price the visitor gave.</p>}
              {deal.source?.enquiry_id && <Link to={`/leads?lead=${encodeURIComponent(deal.source.enquiry_id)}`} className="inline-flex items-center gap-1 font-semibold text-brand hover:underline" data-testid="deal-lead-link">See the original enquiry<ArrowRight className="h-3.5 w-3.5" /></Link>}
            </div>
          </div>
        </section>
      )}

      <section className="space-y-4" aria-label="Deal details">
        <div className="grid gap-1.5">
          <Label htmlFor="deal-name">Deal name</Label>
          <Input id="deal-name" value={form.name} onChange={(event) => setField("name", event.target.value)} maxLength={200} data-testid="deal-name" />
        </div>
        <div className="grid grid-cols-[minmax(0,1fr)_7.5rem] gap-3 [&>*]:min-w-0">
          <div className="grid gap-1.5">
            <Label htmlFor="deal-value">Expected value</Label>
            <Input id="deal-value" type="number" inputMode="decimal" min="0" step="any" value={form.value} onChange={(event) => setField("value", event.target.value)} data-testid="deal-value" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="deal-currency">Currency</Label>
            <Select value={form.currency} onValueChange={(value) => setField("currency", value)}>
              <SelectTrigger id="deal-currency" data-testid="deal-currency"><SelectValue /></SelectTrigger>
              <SelectContent>{currencyOptions(dealCurrency(deal)).map((code) => <SelectItem key={code} value={code}>{code}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 [&>*]:min-w-0">
          <div className="grid gap-1.5">
            <Label htmlFor="deal-close-date">Expected close date</Label>
            <Input id="deal-close-date" type="date" value={form.expected_close_date} onChange={(event) => setField("expected_close_date", event.target.value)} data-testid="deal-close-date" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="deal-owner">Owner</Label>
            <Select value={form.owner} onValueChange={(value) => setField("owner", value)}>
              <SelectTrigger id="deal-owner" data-testid="deal-owner"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_OWNER}>No owner</SelectItem>
                {ownerChoices.map((owner) => <SelectItem key={owner.email} value={owner.email}>{ownerLabel(owner)}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="deal-contacts">People on this deal</Label>
          <ContactPicker id="deal-contacts" selected={form.contacts} onChange={(contacts) => setField("contacts", contacts)} linkContacts testId="deal-contacts" />
        </div>
        {detail.company && (
          <p className="flex items-center gap-1.5 text-sm text-slate-600"><Building2 className="h-4 w-4 text-slate-400" />Company: <Link to={`/companies?company=${encodeURIComponent(detail.company.id)}`} className="font-semibold text-brand hover:underline">{detail.company.name}</Link></p>
        )}
        <div className="grid gap-1.5">
          <Label htmlFor="deal-notes">Notes</Label>
          <Textarea id="deal-notes" value={form.description} onChange={(event) => setField("description", event.target.value)} rows={3} maxLength={4000} placeholder="Anything about this deal you want in front of you next time" data-testid="deal-notes" />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button className="cv-action-primary" disabled={!dirty || saving} onClick={save} data-testid="deal-save">{saving ? "Saving…" : "Save changes"}</Button>
          {dirty && <Button variant="ghost" onClick={() => setForm(formFrom(deal, detail.contacts))} data-testid="deal-discard">Discard</Button>}
          {dirty && <span className="text-xs text-amber-700">You have unsaved changes.</span>}
        </div>
      </section>

      <section className="space-y-3" aria-label="Log activity">
        <h3 className="flex items-center gap-1.5 text-xs font-medium text-slate-500"><MessageSquareText className="h-3.5 w-3.5" />Log activity</h3>
        <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="What kind of activity">
          {ACTIVITY_TYPES.map((item) => {
            const Icon = item.icon;
            const active = activity.type === item.key;
            return <button key={item.key} type="button" role="radio" aria-checked={active} onClick={() => setActivity((current) => ({ ...current, type: item.key }))} className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-semibold ${active ? "border-brand bg-brand text-white" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"}`} data-testid={`deal-activity-type-${item.key}`}><Icon className="h-3.5 w-3.5" />{item.label}</button>;
          })}
        </div>
        <Input value={activity.subject} onChange={(event) => setActivity((current) => ({ ...current, subject: event.target.value }))} placeholder="Summary, e.g. Called about the inspection" aria-label="Activity summary" maxLength={300} data-testid="deal-activity-subject" />
        <Textarea value={activity.body} onChange={(event) => setActivity((current) => ({ ...current, body: event.target.value }))} placeholder={ACTIVITY_TYPES.find((item) => item.key === activity.type)?.placeholder} aria-label="Activity details" rows={3} maxLength={8000} data-testid="deal-activity-body" />
        <Button variant="outline" disabled={logging} onClick={logActivity} data-testid="deal-activity-log">{logging ? "Logging…" : `Log ${ACTIVITY_TYPES.find((item) => item.key === activity.type)?.label.toLowerCase()}`}</Button>
      </section>

      <section className="space-y-2" aria-label="Activity">
        <h3 className="text-xs font-medium text-slate-500">Activity</h3>
        {timeline.length === 0 ? <p className="text-sm text-slate-500">Nothing logged yet.</p> : (
          <ol className="space-y-2" data-testid="deal-timeline">
            {timeline.map((entry, index) => {
              const Icon = entry.kind === "activity" ? (ACTIVITY_ICON[entry.type] || StickyNote) : History;
              return (
                <li key={entry.id || `${entry.at}-${index}`} className="flex gap-3 rounded-lg border border-slate-100 bg-white px-3 py-2.5">
                  <span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${entry.kind === "activity" ? "bg-brand-soft text-brand" : "bg-slate-100 text-slate-500"}`}><Icon className="h-3.5 w-3.5" /></span>
                  <div className="min-w-0 flex-1 text-sm">
                    <p className="font-semibold text-foreground">{entry.kind === "activity" ? (entry.subject || ACTIVITY_TYPES.find((item) => item.key === entry.type)?.label || "Activity") : describeEvent(entry)}</p>
                    {entry.kind === "activity" && entry.body && <p className="mt-0.5 whitespace-pre-line break-words text-slate-600">{entry.body}</p>}
                    <p className="mt-0.5 text-xs text-slate-400">{[entry.kind === "activity" ? ACTIVITY_TYPES.find((item) => item.key === entry.type)?.label : null, when(entry.at), actorName(entry.actor) && `by ${actorName(entry.actor)}`].filter(Boolean).join(" · ")}</p>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <section className="space-y-2" aria-label="Stage history">
        <h3 className="text-xs font-medium text-slate-500">Stage history</h3>
        <ol className="space-y-1.5 text-sm" data-testid="deal-stage-history">
          {[...(detail.stage_history || [])].reverse().map((step, index) => (
            <li key={`${step.at}-${index}`} className="flex flex-wrap items-baseline justify-between gap-x-3 border-b border-slate-100 pb-1.5 last:border-b-0">
              <span className="text-foreground">{step.from ? <>{labelOf(step.from)} <ArrowRight className="inline h-3 w-3 text-slate-400" /> <strong>{labelOf(step.to)}</strong></> : <>Started in <strong>{labelOf(step.to)}</strong></>}</span>
              <span className="text-xs text-slate-400">{[when(step.at), actorName(step.actor) && `by ${actorName(step.actor)}`].filter(Boolean).join(" · ")}</span>
            </li>
          ))}
        </ol>
      </section>

      {!deal.archived_at && (
        <section className="border-t border-slate-100 pt-4">
          <Button variant="outline" className="text-slate-600" onClick={() => setConfirmArchive(true)} data-testid="deal-archive"><Archive className="mr-1.5 h-4 w-4" />Archive this deal</Button>
          <p className="mt-2 text-xs text-slate-500">Archiving takes it off the board without deleting its history. You can restore it at any time.</p>
        </section>
      )}

      <AlertDialog open={confirmArchive} onOpenChange={setConfirmArchive}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Archive “{deal.name}”?</AlertDialogTitle>
            <AlertDialogDescription>It leaves the board and your pipeline totals. Its history, contacts and activity stay, and you can restore it from this page.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it</AlertDialogCancel>
            <AlertDialogAction onClick={() => setArchived(true)} data-testid="deal-archive-confirm">Archive</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
