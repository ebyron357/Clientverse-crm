/* Pipeline board (/deals and /pipeline).

   Columns are the tenant's own stages from GET /pipelines/default: open stages in order,
   then won, with lost stages behind "Show lost deals". Cards move by drag and drop on a
   computer, and by each card's stage menu everywhere (keyboard and phone). A move shows
   at once and is undone, with a message, if the server refuses it. On a phone the board
   becomes a stage picker over one vertical list instead of a wide board that scrolls
   sideways. `?deal=<id>` opens a deal's record. */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr, formatMoney } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { OUTCOME, daysInStage, dealCurrency, formatDay, isOverdue, isWebsiteLead, ownerName, splitStages, stageAccent, stageOutcome, totalParts, totalsByCurrency, usualCurrency } from "@/lib/pipeline";
import { Avatar, PageHeader, Toolbar } from "@/components/page/Page";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import DealRecord from "@/components/pipeline/DealRecord";
import NewDealDialog from "@/components/pipeline/NewDealDialog";
import StageEditor from "@/components/pipeline/StageEditor";
import { ArrowRight, CalendarDays, Check, GitBranch, Globe, MoreHorizontal, Plus, RefreshCw, Search, Settings2, Sparkles, Upload, Users, X } from "lucide-react";

const PHONE_QUERY = "(max-width: 767px)";
// Deals whose stage the pipeline no longer has. They get a column of their own so they
// can be moved somewhere real, rather than silently vanishing from the board.
const UNSTAGED = { key: "__unstaged__", label: "Needs a stage", is_closed: false, is_won: false, virtual: true };
const UNSTAGED_ACCENT = "bg-muted-foreground/40";

const cx = (...parts) => parts.filter(Boolean).join(" ");

function useIsPhone() {
  const [phone, setPhone] = useState(() => typeof window !== "undefined" && Boolean(window.matchMedia?.(PHONE_QUERY).matches));
  useEffect(() => {
    const media = window.matchMedia?.(PHONE_QUERY);
    if (!media) return undefined;
    const update = () => setPhone(media.matches);
    update();
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);
  return phone;
}

export default function Pipeline() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const isPhone = useIsPhone();
  const [searchParams, setSearchParams] = useSearchParams();
  const openDealId = searchParams.get("deal");

  const [deals, setDeals] = useState([]);
  const [stages, setStages] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [workspaces, setWorkspaces] = useState([]);
  const [owners, setOwners] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [ownerFilter, setOwnerFilter] = useState("all");
  const [showLost, setShowLost] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const [stagesOpen, setStagesOpen] = useState(false);
  const [dragId, setDragId] = useState(null);
  const [dropTarget, setDropTarget] = useState(null);
  const [phoneStage, setPhoneStage] = useState(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const [dealResponse, pipelineResponse, companyResponse, workspaceResponse] = await Promise.all([
        api.get("/opportunities", { params: { limit: 1000, expand: "contacts" } }), api.get("/pipelines/default"), api.get("/companies"), api.get("/workspaces"),
      ]);
      setDeals(dealResponse.data || []); setStages(pipelineResponse.data.stages || []);
      setCompanies(companyResponse.data || []); setWorkspaces(workspaceResponse.data || []);
    } catch {
      setError("The pipeline could not be loaded. Your deals are unchanged — try again when the connection is back.");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get("/opportunities/owner-options").then((response) => setOwners(response.data?.items || []))
      .catch(() => setOwners(user?.email ? [{ email: user.email, name: user.name || null }] : []));
  }, [user]);

  const groups = useMemo(() => splitStages(stages), [stages]);
  const orderedStages = useMemo(() => [...groups.open, ...groups.won, ...groups.lost], [groups]);
  const stageByKey = useMemo(() => Object.fromEntries(stages.map((stage) => [stage.key, stage])), [stages]);
  const accentByKey = useMemo(() => Object.fromEntries(stages.map((stage) => [stage.key, stageAccent(stage, groups.open.indexOf(stage))])), [stages, groups]);
  const labelOf = useCallback((key) => stageByKey[key]?.label || UNSTAGED.label, [stageByKey]);
  const companyName = useCallback((id) => companies.find((company) => company.id === id)?.name || "", [companies]);
  const defaultCurrency = useMemo(() => usualCurrency(deals), [deals]);

  const live = useMemo(() => deals.filter((deal) => !deal.archived_at), [deals]);
  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    return live.filter((deal) => {
      if (ownerFilter === "mine" && deal.owner !== user?.email) return false;
      if (ownerFilter !== "all" && ownerFilter !== "mine" && deal.owner !== ownerFilter) return false;
      if (!term) return true;
      const text = [deal.name, companyName(deal.company_id), deal.owner, ...(deal.contacts || []).map((contact) => contact.name)].join(" ").toLowerCase();
      return text.includes(term);
    });
  }, [live, query, ownerFilter, user, companyName]);

  const dealsIn = useCallback((stage) => filtered.filter((deal) => (stage.virtual ? !stageByKey[deal.stage] : deal.stage === stage.key)), [filtered, stageByKey]);
  const unstaged = useMemo(() => filtered.filter((deal) => !stageByKey[deal.stage]), [filtered, stageByKey]);
  const lostCount = useMemo(() => filtered.filter((deal) => stageOutcome(stageByKey[deal.stage]) === OUTCOME.LOST).length, [filtered, stageByKey]);
  const columns = useMemo(() => [...(unstaged.length ? [UNSTAGED] : []), ...groups.open, ...groups.won, ...(showLost ? groups.lost : [])], [unstaged, groups, showLost]);
  const openDeals = filtered.filter((deal) => stageByKey[deal.stage] && stageOutcome(stageByKey[deal.stage]) === OUTCOME.OPEN);
  const wonDeals = filtered.filter((deal) => stageOutcome(stageByKey[deal.stage]) === OUTCOME.WON);

  const nextStageFor = useCallback((deal) => {
    const stage = stageByKey[deal.stage];
    if (!stage) return groups.open[0] || null;
    if (stageOutcome(stage) !== OUTCOME.OPEN) return null;
    const index = groups.open.indexOf(stage);
    return groups.open[index + 1] || groups.won[0] || null;
  }, [stageByKey, groups]);

  /** Move a deal: on the board at once, undone with a message if the server refuses. */
  const move = useCallback(async (deal, stageKey) => {
    if (!stageKey || stageKey === deal.stage) return false;
    const target = stageByKey[stageKey];
    const at = new Date().toISOString();
    setDeals((current) => current.map((item) => item.id === deal.id ? { ...item, stage: stageKey, stage_history: [...(item.stage_history || []), { from: item.stage, to: stageKey, at }] } : item));
    try {
      const { data } = await api.patch(`/opportunities/${deal.id}/stage`, { stage: stageKey });
      const label = target?.label || stageKey;
      if (data.outcome === OUTCOME.WON) {
        if (data.workspace_created) {
          toast.success("Deal won — client workspace created", { description: `${deal.name} is in ${label}.`, action: { label: "Open workspace", onClick: () => navigate(`/workspaces/${data.workspace_id}`) } });
          api.get("/workspaces").then((response) => setWorkspaces(response.data || [])).catch(() => {});
        } else {
          toast.success("Deal marked as won", { description: `${deal.name} is in ${label}.` });
        }
      } else if (data.outcome === OUTCOME.LOST) {
        toast("Deal marked as lost", { description: `${deal.name} is in ${label}.`, action: showLost ? undefined : { label: "Show lost deals", onClick: () => setShowLost(true) } });
      } else {
        toast.success(`Moved to ${label}`, { description: deal.name });
      }
      return true;
    } catch (requestError) {
      // Put back exactly what was there; other deals moved meanwhile are left alone.
      setDeals((current) => current.map((item) => item.id === deal.id ? { ...item, stage: deal.stage, stage_history: deal.stage_history } : item));
      toast.error("That move did not save", { description: `${deal.name} is back in ${labelOf(deal.stage)}. ${formatErr(requestError.response?.data?.detail)}` });
      return false;
    }
  }, [stageByKey, labelOf, navigate, showLost]);

  const openDeal = (deal) => setSearchParams((params) => { params.set("deal", deal.id); return params; });
  const closeDeal = () => setSearchParams((params) => { params.delete("deal"); return params; });
  const mergeDeal = useCallback((updated) => setDeals((current) => {
    const exists = current.some((item) => item.id === updated.id);
    return exists ? current.map((item) => item.id === updated.id ? { ...item, ...updated } : item) : [updated, ...current];
  }), []);

  const dropOn = (stage) => (event) => {
    event.preventDefault();
    const id = event.dataTransfer.getData("text/plain") || dragId;
    setDragId(null); setDropTarget(null);
    const deal = deals.find((item) => item.id === id);
    if (deal && !stage.virtual) move(deal, stage.key);
  };
  const dragProps = (stage) => stage.virtual ? {} : {
    onDragOver: (event) => { if (!dragId) return; event.preventDefault(); event.dataTransfer.dropEffect = "move"; if (dropTarget !== stage.key) setDropTarget(stage.key); },
    onDragLeave: (event) => { if (!event.currentTarget.contains(event.relatedTarget)) setDropTarget((current) => (current === stage.key ? null : current)); },
    onDrop: dropOn(stage),
  };
  const cardDrag = {
    start: (deal) => (event) => { event.dataTransfer.setData("text/plain", deal.id); event.dataTransfer.effectAllowed = "move"; setDragId(deal.id); },
    end: () => { setDragId(null); setDropTarget(null); },
  };

  const newDealDefaults = useMemo(() => ({ currency: defaultCurrency, stage: groups.open[0]?.key || "", owner: user?.email || "" }), [defaultCurrency, groups, user]);
  const phoneColumns = columns;
  const activePhoneStage = phoneColumns.find((stage) => stage.key === phoneStage) || phoneColumns.find((stage) => dealsIn(stage).length) || phoneColumns.find((stage) => !stage.virtual) || phoneColumns[0];
  const accentOf = (stage) => (stage.virtual ? UNSTAGED_ACCENT : accentByKey[stage.key]);

  if (error) {
    return <div className="cv-page" data-testid="pipeline-page">
      <PageHeader icon={GitBranch} title="Pipeline" />
      <EmptyState icon={GitBranch} tone="danger" title="Pipeline unavailable" text={error} action={<Button size="sm" variant="outline" onClick={load}><RefreshCw />Try again</Button>} />
    </div>;
  }

  const cardProps = { stages: orderedStages, accentByKey, labelOf, nextStageFor, onMove: move, onOpen: openDeal, owners, companyName, draggable: !isPhone, touch: isPhone, cardDrag, draggingId: dragId };
  const filteredView = filtered.length !== live.length;

  return (
    <div className="cv-page" data-testid="pipeline-page">
      <PageHeader icon={GitBranch} title="Pipeline" count={loading ? undefined : live.length}
        description={isPhone ? "Tap a deal to update it, or use its menu to move it to another stage." : "Drag a card between stages, or open it to update the details and log what happened."}
        actions={<>
          {isAdmin && <Button variant="outline" size="sm" asChild><Link to="/settings/import?type=deals" data-testid="pipeline-import"><Upload />Import</Link></Button>}
          {isAdmin && <Button variant="outline" size="sm" onClick={() => setStagesOpen(true)} data-testid="customize-stages"><Settings2 />Customize stages</Button>}
          <Button size="sm" onClick={() => setNewOpen(true)} disabled={!groups.open.length} data-testid="new-deal"><Plus />New deal</Button>
        </>} />

      <Toolbar className="pt-0 pb-4">
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input value={query} onChange={(event) => setQuery(event.target.value)} className="h-8 pl-8 pr-8 text-[13px] md:text-[13px]" placeholder="Search deals, people or companies" aria-label="Search deals" data-testid="pipeline-search" />
          {query && <button type="button" onClick={() => setQuery("")} className="absolute right-1.5 top-1/2 flex size-5 -translate-y-1/2 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground" aria-label="Clear search"><X className="size-3.5" /></button>}
        </div>
        <Select value={ownerFilter} onValueChange={setOwnerFilter}>
          <SelectTrigger className="h-8 w-auto max-w-[14rem] justify-start gap-1.5 bg-card text-[13px] shadow-xs" aria-label="Whose deals to show" data-testid="pipeline-owner-filter">
            <Users className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" /><SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Everyone's deals</SelectItem>
            <SelectItem value="mine">My deals</SelectItem>
            {owners.filter((owner) => owner.email !== user?.email).map((owner) => <SelectItem key={owner.email} value={owner.email}>{owner.name || owner.email}</SelectItem>)}
          </SelectContent>
        </Select>
        {groups.lost.length > 0 && (
          <div className="flex h-8 items-center gap-2 px-1">
            <Switch id="show-lost" checked={showLost} onCheckedChange={setShowLost} data-testid="toggle-lost" />
            <Label htmlFor="show-lost" className="cursor-pointer text-[13px] font-normal text-muted-foreground">Show lost deals{lostCount ? ` (${lostCount})` : ""}</Label>
          </div>
        )}
        <dl className="flex w-full items-center gap-4 text-[13px] sm:ml-auto sm:w-auto" aria-label="Pipeline summary">
          <SummaryFigure label="Open" testid="pipeline-open-total" totals={totalsByCurrency(openDeals)} currency={defaultCurrency} count={openDeals.length} />
          <span className="h-4 w-px bg-border" aria-hidden="true" />
          <SummaryFigure label="Won" testid="pipeline-won-total" totals={totalsByCurrency(wonDeals)} currency={defaultCurrency} count={wonDeals.length} won />
        </dl>
      </Toolbar>

      {loading ? (
        <div className="flex gap-3 overflow-hidden" aria-busy="true" aria-label="Loading the pipeline">
          {[0, 1, 2, 3, 4].map((index) => <div key={index} className="w-[17rem] shrink-0">
            <div className="flex h-9 items-center gap-2 px-1.5"><span className="h-3 w-24 animate-pulse rounded bg-muted" /></div>
            <div className="h-80 animate-pulse rounded-xl bg-muted/40" />
          </div>)}
        </div>
      ) : !live.length ? (
        <EmptyState icon={Sparkles} title="No deals yet" text="Deals appear here when a website form brings in a lead, or when you add one yourself."
          action={<Button size="sm" onClick={() => setNewOpen(true)} disabled={!groups.open.length}><Plus />Create your first deal</Button>} />
      ) : isPhone ? (
        <section aria-label="Deals by stage" data-testid="pipeline-phone">
          <div className="cv-scrollbar -mx-4 mb-3 flex gap-4 overflow-x-auto border-b border-border px-4" role="tablist" aria-label="Stages">
            {phoneColumns.map((stage) => {
              const count = dealsIn(stage).length;
              const active = activePhoneStage?.key === stage.key;
              return <button key={stage.key} type="button" role="tab" aria-selected={active} onClick={() => setPhoneStage(stage.key)}
                className={cx("-mb-px flex h-9 shrink-0 items-center gap-1.5 border-b-2 px-0.5 text-[13.5px] font-medium transition-colors", active ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}
                data-testid={`phone-stage-${stage.key}`}>
                <span className={cx("size-2 shrink-0 rounded-full", accentOf(stage))} aria-hidden="true" />{stage.label}
                <span className={cx("tabular rounded px-1 text-xs", active ? "bg-muted text-foreground" : "text-muted-foreground")}>{count}</span>
              </button>;
            })}
          </div>
          {activePhoneStage && (
            <div role="tabpanel" aria-label={activePhoneStage.label}>
              <div className="mb-2 flex items-baseline justify-between gap-3 px-1">
                <h2 className="text-[13px] font-medium text-foreground">{activePhoneStage.label}</h2>
                <span className="tabular text-right text-xs text-muted-foreground"><MoneyTotals totals={totalsByCurrency(dealsIn(activePhoneStage))} preferred={defaultCurrency} /></span>
              </div>
              <div className="space-y-1.5 rounded-xl bg-muted/40 p-1.5">
                {dealsIn(activePhoneStage).map((deal) => <DealCard key={deal.id} deal={deal} {...cardProps} />)}
                {!dealsIn(activePhoneStage).length && <EmptyColumn stage={activePhoneStage} filtered={filteredView} />}
              </div>
            </div>
          )}
        </section>
      ) : (
        <section aria-label="Deals by stage" className="cv-scrollbar -mx-4 overflow-x-auto px-4 pb-4 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8" data-testid="pipeline-board">
          <div className="flex w-max gap-3">
            {columns.map((stage) => (
              <StageColumn key={stage.key} stage={stage} accent={accentOf(stage)} deals={dealsIn(stage)} currency={defaultCurrency} isDropTarget={dropTarget === stage.key} dragging={Boolean(dragId)} dragProps={dragProps(stage)} filteredView={filteredView} cardProps={cardProps} />
            ))}
            {dragId && !showLost && groups.lost.map((stage) => (
              <div key={stage.key} {...dragProps(stage)}
                className={cx("mt-9 flex w-40 shrink-0 flex-col items-center justify-center gap-2 rounded-xl border border-dashed p-3 text-center text-xs font-medium transition-colors", dropTarget === stage.key ? "border-rose-200 bg-rose-50 text-rose-700" : "border-input text-muted-foreground")}
                data-testid={`drop-lost-${stage.key}`}>
                <X className="size-4" aria-hidden="true" />
                Drop here to mark as {stage.label.toLowerCase()}
              </div>
            ))}
          </div>
        </section>
      )}

      <NewDealDialog open={newOpen} onOpenChange={setNewOpen} openStages={groups.open} companies={companies} owners={owners} defaults={newDealDefaults} onCreated={(deal) => { load(); openDeal(deal); }} />
      {isAdmin && <StageEditor open={stagesOpen} onOpenChange={setStagesOpen} stages={stages} onSaved={(saved) => { setStages(saved); load(); }} />}

      <Sheet open={Boolean(openDealId)} onOpenChange={(value) => { if (!value) closeDeal(); }}>
        <SheetContent className="w-full overflow-y-auto p-0 sm:max-w-2xl lg:max-w-5xl" data-testid="deal-sheet">
          {openDealId && <DealRecord key={openDealId} dealId={openDealId} stages={stages} owners={owners} workspaces={workspaces} currentUser={user} onMove={move} onChanged={mergeDeal} />}
        </SheetContent>
      </Sheet>
    </div>
  );
}

/** One figure of the toolbar summary: "Open $185,000 · 7". */
function SummaryFigure({ label, totals, currency, count, testid, won = false }) {
  return <div className="flex min-w-0 items-baseline gap-1.5">
    <dt className="text-muted-foreground">{label}</dt>
    <dd className={cx("tabular font-semibold", won && count ? "text-emerald-700" : "text-foreground")} data-testid={testid}><MoneyTotals totals={totals} preferred={currency} /></dd>
    <dd className="tabular text-xs text-muted-foreground">· {count} deal{count === 1 ? "" : "s"}</dd>
  </div>;
}

function EmptyState({ icon: Icon, title, text, action, tone }) {
  return <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border px-6 py-12 text-center">
    <span className={cx("flex size-10 items-center justify-center rounded-full bg-muted", tone === "danger" ? "text-red-600" : "text-muted-foreground")}><Icon className="size-[18px]" aria-hidden="true" /></span>
    <h2 className="mt-3 text-sm font-medium text-foreground">{title}</h2>
    <p className="mt-1 max-w-sm text-[13px] leading-5 text-muted-foreground">{text}</p>
    {action && <div className="mt-4">{action}</div>}
  </div>;
}

function StageColumn({ stage, accent, deals, currency, isDropTarget, dragging, dragProps, filteredView, cardProps }) {
  const outcome = stage.virtual ? null : stageOutcome(stage);
  return (
    <section aria-label={`${stage.label}: ${deals.length} deal${deals.length === 1 ? "" : "s"}`} {...dragProps} className="flex w-[17rem] shrink-0 flex-col" data-testid={`stage-column-${stage.key}`}>
      <header className="flex h-9 items-center gap-2 px-1.5">
        <span className={cx("size-2 shrink-0 rounded-full", accent)} aria-hidden="true" />
        <h2 className="truncate text-[13px] font-medium text-foreground">{stage.label}</h2>
        <span className="tabular rounded-md bg-muted px-1.5 py-0.5 text-[11px] font-medium leading-none text-muted-foreground" data-testid={`stage-count-${stage.key}`}>{deals.length}</span>
        <span className={cx("tabular ml-auto truncate text-xs", outcome === OUTCOME.WON && deals.length ? "text-emerald-700" : "text-muted-foreground")} data-testid={`stage-total-${stage.key}`}><MoneyTotals totals={totalsByCurrency(deals)} preferred={currency} /></span>
      </header>
      <div className={cx("flex min-h-[max(20rem,calc(100vh-18rem))] flex-1 flex-col gap-1.5 rounded-xl p-1.5 transition-colors", isDropTarget ? "bg-brand-soft ring-1 ring-inset ring-brand/40" : "bg-muted/40")}>
        {deals.map((deal) => <DealCard key={deal.id} deal={deal} {...cardProps} />)}
        {!deals.length && <EmptyColumn stage={stage} dragging={dragging} filtered={filteredView} />}
      </div>
    </section>
  );
}

function EmptyColumn({ stage, dragging, filtered }) {
  const text = dragging ? `Drop here to move to ${stage.label}` : filtered ? "Nothing here matches your search" : `No deals in ${stage.label}`;
  return <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">{text}</div>;
}

/** Totals per currency, each kept on one line so "CA$21,000" never splits from its digits. */
function MoneyTotals({ totals, preferred }) {
  const parts = totalParts(totals, preferred);
  return parts.map((part, index) => <span key={`${index}-${part}`}>{index > 0 && <span className="text-muted-foreground"> · </span>}<span className="whitespace-nowrap">{part}</span></span>);
}

function DealCard({ deal, stages, accentByKey, labelOf, nextStageFor, onMove, onOpen, owners, companyName, draggable, touch, cardDrag, draggingId }) {
  const next = nextStageFor(deal);
  const days = daysInStage(deal);
  const contacts = deal.contacts || [];
  const people = contacts.length > 2 ? `${contacts.slice(0, 2).map((contact) => contact.name).join(", ")} +${contacts.length - 2}` : contacts.map((contact) => contact.name).join(", ");
  const company = companyName(deal.company_id);
  const owner = ownerName(deal.owner, owners);
  const closed = stageOutcome(stages.find((stage) => stage.key === deal.stage)) !== OUTCOME.OPEN;
  const overdue = !closed && isOverdue(deal.expected_close_date);
  return (
    <article draggable={draggable} onDragStart={draggable ? cardDrag.start(deal) : undefined} onDragEnd={draggable ? cardDrag.end : undefined}
      className={cx("group relative rounded-lg border border-border bg-card shadow-xs transition-colors hover:border-input", draggable && "cursor-grab active:cursor-grabbing", draggingId === deal.id && "opacity-50")}
      data-testid={`opportunity-card-${deal.id}`}>
      <button type="button" onClick={() => onOpen(deal)} className="block w-full rounded-lg p-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" data-testid={`open-deal-${deal.id}`}>
        <h3 className="line-clamp-2 pr-6 text-[13px] font-medium leading-5 text-foreground">{deal.name}</h3>
        <div className="mt-1 flex items-center gap-2">
          <span className="tabular text-[13px] font-semibold text-foreground">{formatMoney(deal.value, dealCurrency(deal))}</span>
          {isWebsiteLead(deal) && <span className="inline-flex items-center gap-1 text-[11px] font-medium text-brand"><Globe className="size-3" aria-hidden="true" />Website lead</span>}
        </div>
        {(people || company) && <p className="mt-0.5 truncate text-xs text-muted-foreground">{people || company}</p>}
        <div className="mt-2.5 flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
          {owner ? <span className="flex min-w-0 items-center gap-1.5" title={`Owner: ${deal.owner}`}><Avatar name={owner} size="sm" className="!size-5 !text-[9px]" /><span className="truncate">{owner}</span></span> : <span>No owner</span>}
          {days != null && !closed && <span className="tabular shrink-0" title="Days in this stage"><span aria-hidden="true">· </span>{days === 0 ? "New in stage" : `${days}d in stage`}</span>}
          {deal.expected_close_date && (
            <span className={cx("tabular ml-auto inline-flex shrink-0 items-center gap-1", overdue && "font-medium text-red-600")} title={overdue ? "The expected close date has passed" : "Expected close date"}>
              <CalendarDays className="size-3" aria-hidden="true" />{overdue ? "Was due " : ""}{formatDay(deal.expected_close_date, { month: "short", day: "numeric" })}
            </span>
          )}
        </div>
      </button>
      <MoveMenu deal={deal} stages={stages} accentByKey={accentByKey} labelOf={labelOf} next={next} onMove={onMove} touch={touch} />
    </article>
  );
}

/** The keyboard and phone way to move a deal: a menu of stages behind the card's "⋯". */
function MoveMenu({ deal, stages, accentByKey, labelOf, next, onMove, touch }) {
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <button type="button" aria-label={`Move ${deal.name} from ${labelOf(deal.stage)} to another stage`} data-testid={`stage-select-${deal.id}`}
          className={cx("absolute right-1.5 top-1.5 flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:opacity-100 data-[state=open]:bg-muted data-[state=open]:text-foreground data-[state=open]:opacity-100",
            touch ? "opacity-100" : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100")}>
          <MoreHorizontal className="size-4" aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        {next && <>
          <DropdownMenuItem onSelect={() => onMove(deal, next.key)} className="text-[13px]" data-testid={`advance-${deal.id}`}>
            <ArrowRight className="text-muted-foreground" aria-hidden="true" />Move to {next.label}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
        </>}
        <DropdownMenuLabel className="py-1 text-xs font-medium text-muted-foreground">Move to stage</DropdownMenuLabel>
        {stages.map((stage) => {
          const current = stage.key === deal.stage;
          return <DropdownMenuItem key={stage.key} disabled={current} onSelect={() => onMove(deal, stage.key)} className="text-[13px]" data-testid={`stage-option-${deal.id}-${stage.key}`}>
            <span className={cx("ml-1 mr-0.5 size-2 shrink-0 rounded-full", accentByKey[stage.key])} aria-hidden="true" />
            <span className="truncate">{stage.label}</span>
            {current && <Check className="ml-auto text-muted-foreground" aria-label="Current stage" />}
          </DropdownMenuItem>;
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
