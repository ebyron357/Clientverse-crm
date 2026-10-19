/* The deal record: one deal, opened from the board or from a link (`/deals?deal=<id>`).

   Everything an agent changes about a deal happens here -- name, value and currency,
   stage, close date, owner, the people on it and notes -- next to how it got here (stage
   history), what has happened on it (calls, notes, emails, meetings) and where it came
   from. Stage moves go through the board's own move, so the board, its totals and its
   toasts stay in step with the record.

   Layout: a header (name, value, stage, the stage controls), then the activity and stage
   history in the main column, and the editable details in a properties panel on the
   right (below on narrow screens). */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr, formatMoney } from "@/lib/api";
import { OUTCOME, currencyOptions, dateInputValue, daysInStage, dealCurrency, formatDay, isWebsiteLead, ownerLabel, ownerName, splitStages, stageAccent, stageOutcome } from "@/lib/pipeline";
import { Avatar, PropertyList } from "@/components/page/Page";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import ContactPicker from "@/components/pipeline/ContactPicker";
import { Archive, ArrowRight, BriefcaseBusiness, CalendarDays, FileQuestion, Globe, History, Mail, Phone, RotateCcw, StickyNote } from "lucide-react";

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

// Compact controls for the properties panel.
const FIELD_INPUT = "h-8 text-[13px] md:text-[13px]";
const FIELD_SELECT = "h-8 bg-card text-[13px] shadow-xs";

const cx = (...parts) => parts.filter(Boolean).join(" ");

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

/** A label above its control, for the properties panel. */
function Field({ label, htmlFor, children }) {
  return <div className="grid min-w-0 grid-cols-1 gap-1.5">
    <Label htmlFor={htmlFor} className="text-xs font-medium text-muted-foreground">{label}</Label>
    {children}
  </div>;
}

function Count({ children }) {
  return <span className="tabular rounded bg-muted px-1 text-xs font-medium text-muted-foreground">{children}</span>;
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
    return <div className="flex min-h-full flex-col items-center justify-center px-6 py-16 text-center">
      <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground"><FileQuestion className="size-[18px]" aria-hidden="true" /></span>
      <SheetHeader className="mt-3 items-center space-y-1 text-center sm:text-center">
        <SheetTitle className="text-sm font-medium text-foreground">This deal could not be found</SheetTitle>
        <SheetDescription className="text-[13px]">It may have been removed, or the link may be for a different account.</SheetDescription>
      </SheetHeader>
    </div>;
  }
  if (!detail || !form) {
    return <div aria-busy="true">
      <SheetHeader className="sr-only"><SheetTitle>Deal</SheetTitle><SheetDescription>Loading this deal</SheetDescription></SheetHeader>
      <div className="flex items-start gap-3 border-b border-border px-6 pb-5 pt-6">
        <Skeleton className="size-11 rounded-lg" />
        <div className="flex-1 space-y-2"><Skeleton className="h-5 w-2/3" /><Skeleton className="h-4 w-1/3" /></div>
      </div>
      <div className="flex">
        <div className="flex-1 space-y-3 p-6"><Skeleton className="h-8 w-48" /><Skeleton className="h-28 w-full" /><Skeleton className="h-14 w-full" /><Skeleton className="h-14 w-full" /></div>
        <div className="hidden w-80 space-y-3 border-l border-border p-5 lg:block"><Skeleton className="h-8 w-full" /><Skeleton className="h-8 w-full" /><Skeleton className="h-8 w-full" /><Skeleton className="h-20 w-full" /></div>
      </div>
    </div>;
  }

  const outcome = stageOutcome(detail.stage || {});
  const groups = splitStages(allStages);
  const accentOf = (key) => {
    const stage = allStages.find((item) => item.key === key);
    return stage ? stageAccent(stage, groups.open.indexOf(stage)) : "bg-muted-foreground/40";
  };
  const openIndex = groups.open.findIndex((stage) => stage.key === deal.stage);
  const nextStage = outcome === OUTCOME.OPEN ? (openIndex >= 0 && openIndex < groups.open.length - 1 ? groups.open[openIndex + 1] : groups.won[0]) : null;
  const workspace = (workspaces || []).find((item) => item.opportunity_id === deal.id);
  const sourceForm = forms.find((item) => item.id === deal.source?.form_id);
  const basis = deal.value_basis;
  const ownerChoices = [...owners];
  if (deal.owner && !ownerChoices.some((owner) => owner.email === deal.owner)) ownerChoices.push({ email: deal.owner, name: null });
  const timeline = (detail.timeline || []).filter((entry) => !(entry.kind === "event" && String(entry.type || "").startsWith("activity.")));
  const stageHistory = [...(detail.stage_history || [])].reverse();
  const days = daysInStage(deal);
  const activityType = ACTIVITY_TYPES.find((item) => item.key === activity.type);

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

  const stageName = (stageKey, strong = false) => <span className="inline-flex items-center gap-1.5">
    <span className={cx("size-1.5 shrink-0 rounded-full", accentOf(stageKey))} aria-hidden="true" />
    <span className={strong ? "font-medium text-foreground" : undefined}>{labelOf(stageKey)}</span>
  </span>;

  const about = [
    detail.company && { label: "Company", value: <Link to={`/companies?company=${encodeURIComponent(detail.company.id)}`} className="font-medium text-brand hover:underline">{detail.company.name}</Link> },
    days != null && outcome === OUTCOME.OPEN && { label: "In this stage", value: <span className="tabular">{days === 0 ? "Since today" : `${days} day${days === 1 ? "" : "s"}`}</span> },
    deal.created_at && { label: "Created", value: <span className="tabular">{formatDay(deal.created_at)}</span> },
  ].filter(Boolean);

  return (
    <div className="flex min-h-full flex-col" data-testid="deal-record">
      <SheetHeader className="space-y-4 border-b border-border px-5 pb-4 pt-5 text-left sm:px-6">
        <div className="flex items-start gap-3 pr-8">
          <Avatar name={deal.name} size="lg" className="!rounded-lg" />
          <div className="min-w-0 flex-1">
            <SheetTitle className="line-clamp-2 text-lg font-semibold leading-6 tracking-tight text-foreground" data-testid="deal-record-title">{deal.name}</SheetTitle>
            <SheetDescription className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-muted-foreground">
              <span className="tabular font-medium text-foreground">{formatMoney(deal.value, dealCurrency(deal))}</span>
              <span aria-hidden="true">·</span>
              {stageName(deal.stage)}
              {website && <><span aria-hidden="true">·</span><span className="inline-flex items-center gap-1 font-medium text-brand"><Globe className="size-3.5" aria-hidden="true" />Website lead</span></>}
              {deal.archived_at && <span className="rounded-md border border-border bg-muted px-1.5 py-0.5 text-[11px] font-medium leading-4 text-muted-foreground">Archived</span>}
            </SheetDescription>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Stage">
          <Label htmlFor="deal-stage" className="sr-only">Stage</Label>
          <Select value={deal.stage} onValueChange={moveTo} disabled={moving}>
            <SelectTrigger id="deal-stage" aria-label="Stage" className="h-8 w-auto min-w-[10rem] gap-2 bg-card text-[13px] shadow-xs" data-testid="deal-stage-select">
              <SelectValue>{stageName(deal.stage, true)}</SelectValue>
            </SelectTrigger>
            <SelectContent>{allStages.map((stage) => <SelectItem key={stage.key} value={stage.key} className="text-[13px]">
              <span className="inline-flex items-center gap-2"><span className={cx("size-1.5 shrink-0 rounded-full", accentOf(stage.key))} aria-hidden="true" />{stageOptionLabel(stage)}</span>
            </SelectItem>)}</SelectContent>
          </Select>
          {nextStage && (
            <Button size="sm" disabled={moving} onClick={() => moveTo(nextStage.key)} data-testid="deal-next-stage">
              {stageOutcome(nextStage) === OUTCOME.WON ? "Mark as won" : `Move to ${nextStage.label}`}<ArrowRight />
            </Button>
          )}
          {workspace && <Button asChild variant="outline" size="sm"><Link to={`/workspaces/${workspace.id}`} data-testid="deal-workspace-link"><BriefcaseBusiness />Open the client workspace</Link></Button>}
        </div>
      </SheetHeader>

      {deal.archived_at && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-muted/40 px-5 py-2 text-[13px] text-muted-foreground sm:px-6">
          <span className="flex items-center gap-2"><Archive className="size-3.5 shrink-0" aria-hidden="true" />Archived on {formatDay(deal.archived_at)}. It is not on the board or in your totals.</span>
          <Button size="sm" variant="outline" className="h-7" onClick={() => setArchived(false)} data-testid="deal-restore"><RotateCcw />Restore</Button>
        </div>
      )}

      <div className="flex flex-1 flex-col lg:flex-row">
        <div className="min-w-0 flex-1 px-5 py-5 sm:px-6">
          {website && (
            <section className="mb-5 flex items-start gap-2.5 rounded-lg border border-brand/20 bg-brand-soft/60 px-3 py-2.5 text-[13px] leading-5" aria-label="Where this deal came from">
              <Globe className="mt-0.5 size-3.5 shrink-0 text-brand" aria-hidden="true" />
              <div className="min-w-0 space-y-0.5">
                <p className="font-medium text-foreground">Came in through your website{sourceForm ? ` — “${sourceForm.name}”` : ""}</p>
                {basis?.method === "commission" && basis.price != null && <p className="text-muted-foreground">Value worked out as {basis.commission_rate}% commission on {formatMoney(basis.price, dealCurrency(deal))}, the price the visitor gave.</p>}
                {deal.source?.enquiry_id && <Link to={`/leads?lead=${encodeURIComponent(deal.source.enquiry_id)}`} className="inline-flex items-center gap-1 font-medium text-brand hover:underline" data-testid="deal-lead-link">See the original enquiry<ArrowRight className="size-3.5" aria-hidden="true" /></Link>}
              </div>
            </section>
          )}

          <Tabs defaultValue="activity">
            <TabsList className="h-auto w-full justify-start gap-5 rounded-none border-b border-border bg-transparent p-0">
              <TabsTrigger value="activity" className="-mb-px h-9 rounded-none border-b-2 border-transparent px-0.5 text-[13.5px] data-[state=active]:border-foreground data-[state=active]:bg-transparent data-[state=active]:shadow-none" data-testid="deal-tab-activity">Activity <Count>{timeline.length}</Count></TabsTrigger>
              <TabsTrigger value="history" className="-mb-px h-9 rounded-none border-b-2 border-transparent px-0.5 text-[13.5px] data-[state=active]:border-foreground data-[state=active]:bg-transparent data-[state=active]:shadow-none" data-testid="deal-tab-history">Stage history <Count>{stageHistory.length}</Count></TabsTrigger>
            </TabsList>

            <TabsContent value="activity" forceMount className="mt-4 data-[state=inactive]:hidden">
              <section aria-label="Log activity" className="rounded-xl border border-border bg-card shadow-xs transition-colors focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/15">
                <div className="flex flex-wrap items-center gap-0.5 border-b border-border/70 p-1.5" role="radiogroup" aria-label="What kind of activity">
                  {ACTIVITY_TYPES.map((item) => {
                    const Icon = item.icon;
                    const active = activity.type === item.key;
                    return <button key={item.key} type="button" role="radio" aria-checked={active} onClick={() => setActivity((current) => ({ ...current, type: item.key }))}
                      className={cx("inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-[13px] font-medium transition-colors", active ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground")}
                      data-testid={`deal-activity-type-${item.key}`}><Icon className="size-3.5" aria-hidden="true" />{item.label}</button>;
                  })}
                </div>
                <Input value={activity.subject} onChange={(event) => setActivity((current) => ({ ...current, subject: event.target.value }))} placeholder="Summary, e.g. Called about the inspection" aria-label="Activity summary" maxLength={300}
                  className="h-10 rounded-none border-0 bg-transparent px-3 text-[13px] font-medium shadow-none focus-visible:ring-0 md:text-[13px]" data-testid="deal-activity-subject" />
                <Textarea value={activity.body} onChange={(event) => setActivity((current) => ({ ...current, body: event.target.value }))} placeholder={activityType?.placeholder} aria-label="Activity details" rows={3} maxLength={8000}
                  className="min-h-[64px] rounded-none border-0 px-3 pt-0 text-[13px] shadow-none focus-visible:ring-0 md:text-[13px]" data-testid="deal-activity-body" />
                <div className="flex justify-end px-2 pb-2">
                  <Button size="sm" variant="outline" disabled={logging} onClick={logActivity} data-testid="deal-activity-log">{logging ? "Logging…" : `Log ${activityType?.label.toLowerCase()}`}</Button>
                </div>
              </section>

              <section aria-label="Activity" className="mt-6">
                {timeline.length === 0 ? <p className="py-6 text-center text-[13px] text-muted-foreground">Nothing logged yet.</p> : (
                  <ol data-testid="deal-timeline">
                    {timeline.map((entry, index) => {
                      const isActivity = entry.kind === "activity";
                      const Icon = isActivity ? (ACTIVITY_ICON[entry.type] || StickyNote) : History;
                      const kindLabel = isActivity ? ACTIVITY_TYPES.find((item) => item.key === entry.type)?.label : null;
                      const meta = [kindLabel, when(entry.at), actorName(entry.actor) && `by ${actorName(entry.actor)}`].filter(Boolean).join(" · ");
                      return (
                        <li key={entry.id || `${entry.at}-${index}`} className="relative flex gap-3 pb-5 last:pb-0">
                          {index < timeline.length - 1 && <span className="absolute bottom-0 left-3 top-7 w-px bg-border" aria-hidden="true" />}
                          <span className={cx("relative flex size-6 shrink-0 items-center justify-center rounded-full", isActivity ? "bg-brand-soft text-brand" : "border border-border bg-card text-muted-foreground")}><Icon className="size-3" aria-hidden="true" /></span>
                          <div className="min-w-0 flex-1 pt-0.5 text-[13px] leading-5">
                            <p className="flex flex-wrap items-baseline gap-x-2">
                              <span className="font-medium text-foreground">{isActivity ? (entry.subject || kindLabel || "Activity") : describeEvent(entry)}</span>
                              <span className="tabular text-xs text-muted-foreground">{meta}</span>
                            </p>
                            {isActivity && entry.body && <p className="mt-1.5 whitespace-pre-line break-words rounded-lg border border-border/70 bg-muted/30 px-3 py-2 text-foreground/80">{entry.body}</p>}
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                )}
              </section>
            </TabsContent>

            <TabsContent value="history" forceMount className="mt-2 data-[state=inactive]:hidden">
              <section aria-label="Stage history">
                <ol className="divide-y divide-border/70 text-[13px]" data-testid="deal-stage-history">
                  {stageHistory.map((step, index) => (
                    <li key={`${step.at}-${index}`} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-0.5 py-2.5">
                      <span className="inline-flex flex-wrap items-center gap-1.5 text-muted-foreground">
                        {step.from ? <>{stageName(step.from)}<ArrowRight className="size-3" aria-hidden="true" />{stageName(step.to, true)}</> : <>Started in {stageName(step.to, true)}</>}
                      </span>
                      <span className="tabular text-xs text-muted-foreground">{[when(step.at), actorName(step.actor) && `by ${actorName(step.actor)}`].filter(Boolean).join(" · ")}</span>
                    </li>
                  ))}
                </ol>
              </section>
            </TabsContent>
          </Tabs>
        </div>

        <aside className="border-t border-border px-5 py-5 sm:px-6 lg:w-80 lg:shrink-0 lg:border-l lg:border-t-0 lg:px-5" aria-label="Deal details">
          <h2 className="mb-3 text-sm font-semibold text-foreground">Details</h2>
          <div className="space-y-3">
            <Field label="Deal name" htmlFor="deal-name">
              <Input id="deal-name" value={form.name} onChange={(event) => setField("name", event.target.value)} maxLength={200} className={FIELD_INPUT} data-testid="deal-name" />
            </Field>
            <div className="grid grid-cols-[minmax(0,1fr)_5.5rem] gap-2 [&>*]:min-w-0">
              <Field label="Expected value" htmlFor="deal-value">
                <Input id="deal-value" type="number" inputMode="decimal" min="0" step="any" value={form.value} onChange={(event) => setField("value", event.target.value)} className={cx(FIELD_INPUT, "tabular")} data-testid="deal-value" />
              </Field>
              <Field label="Currency" htmlFor="deal-currency">
                <Select value={form.currency} onValueChange={(value) => setField("currency", value)}>
                  <SelectTrigger id="deal-currency" aria-label="Currency" className={FIELD_SELECT} data-testid="deal-currency"><SelectValue /></SelectTrigger>
                  <SelectContent>{currencyOptions(dealCurrency(deal)).map((code) => <SelectItem key={code} value={code} className="text-[13px]">{code}</SelectItem>)}</SelectContent>
                </Select>
              </Field>
            </div>
            <Field label="Expected close date" htmlFor="deal-close-date">
              <Input id="deal-close-date" type="date" value={form.expected_close_date} onChange={(event) => setField("expected_close_date", event.target.value)} className={FIELD_INPUT} data-testid="deal-close-date" />
            </Field>
            <Field label="Owner" htmlFor="deal-owner">
              <Select value={form.owner} onValueChange={(value) => setField("owner", value)}>
                <SelectTrigger id="deal-owner" aria-label="Owner" className={FIELD_SELECT} data-testid="deal-owner"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_OWNER} className="text-[13px]">No owner</SelectItem>
                  {ownerChoices.map((owner) => <SelectItem key={owner.email} value={owner.email} className="text-[13px]">{ownerLabel(owner)}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <Field label="People on this deal" htmlFor="deal-contacts">
              <ContactPicker id="deal-contacts" selected={form.contacts} onChange={(contacts) => setField("contacts", contacts)} linkContacts compact testId="deal-contacts" />
            </Field>
            <Field label="Notes" htmlFor="deal-notes">
              <Textarea id="deal-notes" value={form.description} onChange={(event) => setField("description", event.target.value)} rows={3} maxLength={4000} placeholder="Anything about this deal you want in front of you next time" className="text-[13px] md:text-[13px]" data-testid="deal-notes" />
            </Field>
            <div className="flex flex-wrap items-center gap-2 pt-0.5">
              <Button size="sm" disabled={!dirty || saving} onClick={save} data-testid="deal-save">{saving ? "Saving…" : "Save changes"}</Button>
              {dirty && <Button size="sm" variant="ghost" onClick={() => setForm(formFrom(deal, detail.contacts))} data-testid="deal-discard">Discard</Button>}
              {dirty && <span className="text-xs text-amber-700">You have unsaved changes.</span>}
            </div>
          </div>

          {about.length > 0 && <PropertyList items={about} className="mt-5 border-t border-border pt-1" />}

          {!deal.archived_at && (
            <div className="mt-5 border-t border-border pt-4">
              <Button variant="ghost" size="sm" className="-ml-2 text-muted-foreground hover:text-foreground" onClick={() => setConfirmArchive(true)} data-testid="deal-archive"><Archive />Archive this deal</Button>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">Archiving takes it off the board without deleting its history. You can restore it at any time.</p>
            </div>
          )}
        </aside>
      </div>

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
