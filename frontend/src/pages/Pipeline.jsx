/* Pipeline board (/deals and /pipeline).

   Columns are the tenant's own stages from GET /pipelines/default: open stages in order,
   then won, with lost stages behind "Show lost deals". Cards move by drag and drop on a
   computer, and by each card's stage menu or "Next" button everywhere (keyboard and
   phone). A move shows at once and is undone, with a message, if the server refuses it.
   On a phone the board becomes a stage picker over one vertical list instead of a wide
   board that scrolls sideways. `?deal=<id>` opens a deal's record. */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr, formatMoney } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { OUTCOME, daysInStage, dealCurrency, formatDay, initials, isOverdue, isWebsiteLead, ownerName, splitStages, stageAccent, stageOutcome, totalParts, totalsByCurrency, usualCurrency } from "@/lib/pipeline";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import DealRecord from "@/components/pipeline/DealRecord";
import NewDealDialog from "@/components/pipeline/NewDealDialog";
import StageEditor from "@/components/pipeline/StageEditor";
import { ArrowRight, CalendarDays, CircleDollarSign, Filter, GitBranch, Globe, Plus, RefreshCw, Search, Settings2, Sparkles, Trophy, Users, X } from "lucide-react";

const PHONE_QUERY = "(max-width: 767px)";
// Deals whose stage the pipeline no longer has. They get a column of their own so they
// can be moved somewhere real, rather than silently vanishing from the board.
const UNSTAGED = { key: "__unstaged__", label: "Needs a stage", is_closed: false, is_won: false, virtual: true };

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

  if (error) return <div className="cv-page"><div className="cv-empty"><GitBranch className="h-9 w-9 text-red-500" /><h1 className="mt-4 font-display text-xl font-bold">Pipeline unavailable</h1><p className="mt-2 max-w-md text-sm leading-6 text-slate-500">{error}</p><Button onClick={load} className="mt-5 cv-action-primary"><RefreshCw className="mr-2 h-4 w-4" />Try again</Button></div></div>;

  const cardProps = { stages, groups, labelOf, nextStageFor, onMove: move, onOpen: openDeal, owners, companyName, draggable: !isPhone, compact: !isPhone, cardDrag, draggingId: dragId };

  return (
    <div className="cv-page" data-testid="pipeline-page">
      <div className="cv-page-header">
        <div>
          <div className="cv-eyebrow">Sales pipeline</div>
          <h1 className="cv-page-title">Pipeline</h1>
          <p className="cv-page-description">{isPhone ? "Every deal from first enquiry to closing. Tap a deal to update it, or use Next to move it along." : "Every deal from first enquiry to closing. Drag a card to move it, or open it to update the details and log what happened."}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {isAdmin && <Button variant="outline" onClick={() => setStagesOpen(true)} data-testid="customize-stages"><Settings2 className="mr-1.5 h-4 w-4" />Customize stages</Button>}
          <Button className="cv-action-primary" onClick={() => setNewOpen(true)} disabled={!groups.open.length} data-testid="new-deal"><Plus className="mr-1.5 h-4 w-4" />New deal</Button>
        </div>
      </div>

      <section className="mb-5 grid grid-cols-2 gap-3 xl:grid-cols-[1fr_1fr_minmax(0,1.4fr)]" aria-label="Pipeline summary and filters">
        <div className="cv-card flex min-w-0 items-center gap-4 p-3 sm:p-4">
          <span className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-cyan-50 text-[#1a9fbf] sm:flex"><CircleDollarSign className="h-5 w-5" /></span>
          <div className="min-w-0">
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">Open deals</div>
            <div className="mt-0.5 font-display text-xl font-extrabold text-[#0a1628] sm:text-2xl" data-testid="pipeline-open-total"><MoneyTotals totals={totalsByCurrency(openDeals)} preferred={defaultCurrency} /></div>
            <div className="text-xs text-slate-500">{openDeals.length} deal{openDeals.length === 1 ? "" : "s"} still in play</div>
          </div>
        </div>
        <div className="cv-card flex min-w-0 items-center gap-4 p-3 sm:p-4">
          <span className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600 sm:flex"><Trophy className="h-5 w-5" /></span>
          <div className="min-w-0">
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">Won</div>
            <div className="mt-0.5 font-display text-xl font-extrabold text-[#0a1628] sm:text-2xl" data-testid="pipeline-won-total"><MoneyTotals totals={totalsByCurrency(wonDeals)} preferred={defaultCurrency} /></div>
            <div className="text-xs text-slate-500">{wonDeals.length} deal{wonDeals.length === 1 ? "" : "s"} closed and won</div>
          </div>
        </div>
        <div className="cv-card col-span-2 flex flex-col gap-2 p-3 xl:col-span-1">
          <div className="flex items-center gap-2 rounded-lg border border-slate-200 px-3">
            <Search className="h-4 w-4 shrink-0 text-slate-400" />
            <input value={query} onChange={(event) => setQuery(event.target.value)} className="h-9 w-full min-w-0 bg-transparent text-sm text-[#0a1628] outline-none placeholder:text-slate-400" placeholder="Search deals, people or companies" aria-label="Search deals" data-testid="pipeline-search" />
            {query && <button type="button" onClick={() => setQuery("")} className="text-slate-400 hover:text-slate-600" aria-label="Clear search"><X className="h-4 w-4" /></button>}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex min-w-0 flex-1 items-center gap-1.5">
              <Filter className="h-4 w-4 shrink-0 text-slate-400" />
              <Select value={ownerFilter} onValueChange={setOwnerFilter}>
                <SelectTrigger className="h-8 min-w-0 border-0 bg-transparent px-1 text-sm shadow-none focus:ring-0" aria-label="Whose deals to show" data-testid="pipeline-owner-filter"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Everyone's deals</SelectItem>
                  <SelectItem value="mine">My deals</SelectItem>
                  {owners.filter((owner) => owner.email !== user?.email).map((owner) => <SelectItem key={owner.email} value={owner.email}>{owner.name || owner.email}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {groups.lost.length > 0 && (
              <div className="flex items-center gap-2">
                <Switch id="show-lost" checked={showLost} onCheckedChange={setShowLost} data-testid="toggle-lost" />
                <Label htmlFor="show-lost" className="cursor-pointer text-sm font-medium text-slate-600">Show lost deals{lostCount ? ` (${lostCount})` : ""}</Label>
              </div>
            )}
          </div>
        </div>
      </section>

      {loading ? (
        <div className="flex gap-4 overflow-hidden">{[0, 1, 2, 3].map((index) => <div key={index} className="h-72 min-w-[240px] flex-1 animate-pulse rounded-2xl border border-slate-200 bg-white" />)}</div>
      ) : !live.length ? (
        <div className="cv-empty"><Sparkles className="h-9 w-9 text-[#4ac4e0]" /><h2 className="mt-4 font-display text-xl font-bold text-[#0a1628]">No deals yet</h2><p className="mt-2 max-w-md text-sm leading-6 text-slate-500">Deals appear here when a website form brings in a lead, or when you add one yourself.</p><Button onClick={() => setNewOpen(true)} className="mt-5 cv-action-primary" disabled={!groups.open.length}><Plus className="mr-1.5 h-4 w-4" />Create your first deal</Button></div>
      ) : isPhone ? (
        <section aria-label="Deals by stage" data-testid="pipeline-phone">
          <div className="mb-3 flex flex-wrap gap-1.5" role="tablist" aria-label="Stages">
            {phoneColumns.map((stage) => {
              const count = dealsIn(stage).length;
              const active = activePhoneStage?.key === stage.key;
              return <button key={stage.key} type="button" role="tab" aria-selected={active} onClick={() => setPhoneStage(stage.key)} className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-semibold ${active ? "border-[#0a1628] bg-[#0a1628] text-white" : "border-slate-200 bg-white text-slate-600"}`} data-testid={`phone-stage-${stage.key}`}><span className={`h-2 w-2 rounded-full ${stage.virtual ? "bg-slate-300" : accentByKey[stage.key]}`} />{stage.label}<span className={active ? "text-white/70" : "text-slate-400"}>{count}</span></button>;
            })}
          </div>
          {activePhoneStage && (
            <div role="tabpanel" aria-label={activePhoneStage.label}>
              <div className="mb-3 flex items-baseline justify-between gap-3 px-1">
                <h2 className="text-sm font-bold text-[#132038]">{activePhoneStage.label}</h2>
                <span className="text-right font-display text-base font-bold text-[#0a1628]"><MoneyTotals totals={totalsByCurrency(dealsIn(activePhoneStage))} preferred={defaultCurrency} /></span>
              </div>
              <div className="space-y-3">
                {dealsIn(activePhoneStage).map((deal) => <DealCard key={deal.id} deal={deal} {...cardProps} />)}
                {!dealsIn(activePhoneStage).length && <EmptyColumn stage={activePhoneStage} filtered={filtered.length !== live.length} />}
              </div>
            </div>
          )}
        </section>
      ) : (
        <section aria-label="Deals by stage" className="cv-scrollbar overflow-x-auto pb-3" data-testid="pipeline-board">
          <div className="flex min-w-max gap-3 lg:min-w-0">
            {columns.map((stage) => (
              <StageColumn key={stage.key} stage={stage} accent={stage.virtual ? "bg-slate-300" : accentByKey[stage.key]} deals={dealsIn(stage)} currency={defaultCurrency} isDropTarget={dropTarget === stage.key} dragging={Boolean(dragId)} dragProps={dragProps(stage)} filteredView={filtered.length !== live.length} cardProps={cardProps} />
            ))}
            {dragId && !showLost && groups.lost.map((stage) => (
              <div key={stage.key} {...dragProps(stage)} className={`flex w-[150px] shrink-0 flex-col items-center justify-center rounded-2xl border-2 border-dashed p-3 text-center text-xs font-semibold transition-colors ${dropTarget === stage.key ? "border-rose-400 bg-rose-50 text-rose-700" : "border-slate-300 bg-white/70 text-slate-500"}`} data-testid={`drop-lost-${stage.key}`}>
                Drop here to mark as {stage.label.toLowerCase()}
              </div>
            ))}
          </div>
        </section>
      )}

      <NewDealDialog open={newOpen} onOpenChange={setNewOpen} openStages={groups.open} companies={companies} owners={owners} defaults={newDealDefaults} onCreated={(deal) => { load(); openDeal(deal); }} />
      {isAdmin && <StageEditor open={stagesOpen} onOpenChange={setStagesOpen} stages={stages} onSaved={(saved) => { setStages(saved); load(); }} />}

      <Sheet open={Boolean(openDealId)} onOpenChange={(value) => { if (!value) closeDeal(); }}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl" data-testid="deal-sheet">
          {openDealId && <DealRecord key={openDealId} dealId={openDealId} stages={stages} owners={owners} workspaces={workspaces} currentUser={user} onMove={move} onChanged={mergeDeal} />}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function StageColumn({ stage, accent, deals, currency, isDropTarget, dragging, dragProps, filteredView, cardProps }) {
  const outcome = stage.virtual ? null : stageOutcome(stage);
  return (
    <section aria-label={`${stage.label}: ${deals.length} deal${deals.length === 1 ? "" : "s"}`} {...dragProps}
      className={`flex w-[264px] shrink-0 flex-col rounded-2xl border p-2 transition-colors lg:w-auto lg:min-w-[196px] lg:flex-1 lg:basis-0 ${isDropTarget ? "border-[#1a9fbf] bg-cyan-50/70" : outcome === OUTCOME.WON ? "border-emerald-200/80 bg-emerald-50/40" : outcome === OUTCOME.LOST ? "border-rose-200/80 bg-rose-50/40" : "border-slate-200/90 bg-slate-100/55"}`}
      data-testid={`stage-column-${stage.key}`}>
      <header className="mb-2.5 rounded-xl bg-white px-3 py-2.5 shadow-[0_1px_2px_rgba(10,22,40,.03)]">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2"><span className={`h-2.5 w-2.5 shrink-0 rounded-full ${accent}`} /><h2 className="truncate text-sm font-bold text-[#132038]">{stage.label}</h2></div>
          <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs font-semibold text-slate-600" data-testid={`stage-count-${stage.key}`}>{deals.length}</span>
        </div>
        <p className="mt-1 break-words font-display text-base font-bold text-[#0a1628]" data-testid={`stage-total-${stage.key}`}><MoneyTotals totals={totalsByCurrency(deals)} preferred={currency} /></p>
      </header>
      <div className="flex-1 space-y-2.5">
        {deals.map((deal) => <DealCard key={deal.id} deal={deal} {...cardProps} />)}
        {!deals.length && <EmptyColumn stage={stage} dragging={dragging} filtered={filteredView} />}
      </div>
    </section>
  );
}

function EmptyColumn({ stage, dragging, filtered }) {
  const text = dragging ? `Drop here to move to ${stage.label}` : filtered ? "Nothing here matches your search" : `No deals in ${stage.label}`;
  return <div className="rounded-xl border border-dashed border-slate-300 bg-white/60 px-3 py-7 text-center text-xs text-slate-400">{text}</div>;
}

/** Totals per currency, each kept on one line so "CA$21,000" never splits from its digits. */
function MoneyTotals({ totals, preferred }) {
  const parts = totalParts(totals, preferred);
  return parts.map((part, index) => <span key={`${index}-${part}`}>{index > 0 && <span className="text-slate-400"> · </span>}<span className="whitespace-nowrap">{part}</span></span>);
}

function DealCard({ deal, stages, labelOf, nextStageFor, onMove, onOpen, owners, companyName, draggable, cardDrag, draggingId, compact }) {
  const next = nextStageFor(deal);
  const days = daysInStage(deal);
  const contacts = deal.contacts || [];
  const people = contacts.length > 2 ? `${contacts.slice(0, 2).map((contact) => contact.name).join(", ")} +${contacts.length - 2}` : contacts.map((contact) => contact.name).join(", ");
  const company = companyName(deal.company_id);
  const owner = ownerName(deal.owner, owners);
  const closed = stageOutcome(stages.find((stage) => stage.key === deal.stage)) !== OUTCOME.OPEN;
  const overdue = !closed && isOverdue(deal.expected_close_date);
  const elsewhere = stages.filter((stage) => stage.key !== deal.stage);
  return (
    <article draggable={draggable} onDragStart={draggable ? cardDrag.start(deal) : undefined} onDragEnd={draggable ? cardDrag.end : undefined}
      className={`rounded-xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(10,22,40,.03)] transition-shadow hover:shadow-[0_8px_18px_rgba(10,22,40,.08)] ${draggable ? "cursor-grab active:cursor-grabbing" : ""} ${draggingId === deal.id ? "opacity-50" : ""}`}
      data-testid={`opportunity-card-${deal.id}`}>
      <button type="button" onClick={() => onOpen(deal)} className="block w-full rounded-t-xl p-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#4ac4e0]" data-testid={`open-deal-${deal.id}`}>
        <h3 className="line-clamp-2 text-sm font-bold leading-5 text-[#132038]">{deal.name}</h3>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
          <span className="font-display text-[15px] font-bold text-[#0a1628]">{formatMoney(deal.value, dealCurrency(deal))}</span>
          {isWebsiteLead(deal) && <span className="inline-flex items-center gap-1 rounded-full bg-cyan-50 px-1.5 py-0.5 text-[11px] font-semibold text-[#0a6177]"><Globe className="h-3 w-3" />Website lead</span>}
        </div>
        {(people || company) && <p className="mt-1.5 flex items-center gap-1 text-xs text-slate-600"><Users className="h-3 w-3 shrink-0 text-slate-400" /><span className="truncate">{people || company}</span></p>}
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-slate-500">
          {deal.expected_close_date && <span className={`inline-flex items-center gap-1 ${overdue ? "font-semibold text-red-600" : ""}`} title={overdue ? "The expected close date has passed" : "Expected close date"}><CalendarDays className="h-3 w-3" />{overdue ? "Was due " : "Closes "}{formatDay(deal.expected_close_date, { month: "short", day: "numeric" })}</span>}
          {days != null && !closed && <span title="Days in this stage">{days === 0 ? "New in stage" : `${days} day${days === 1 ? "" : "s"} in stage`}</span>}
        </div>
        {owner && <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-slate-500" title={`Owner: ${deal.owner}`}><span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[9px] font-bold text-slate-600">{initials(owner)}</span><span className="truncate">{owner}</span></div>}
      </button>
      <div className="flex items-center gap-1.5 border-t border-slate-100 px-2.5 py-2">
        {/* The keyboard and phone way to move a deal: a menu of the other stages. */}
        <Select value="" onValueChange={(value) => onMove(deal, value)}>
          <SelectTrigger className="h-8 min-w-0 flex-1 border-slate-200 bg-slate-50 px-2.5 text-xs font-medium text-slate-600" aria-label={`Move ${deal.name} from ${labelOf(deal.stage)} to another stage`} data-testid={`stage-select-${deal.id}`}><SelectValue placeholder="Move to…" /></SelectTrigger>
          <SelectContent>{elsewhere.map((stage) => <SelectItem key={stage.key} value={stage.key}>{stage.label}</SelectItem>)}</SelectContent>
        </Select>
        {next && (
          <Button size="sm" className={`h-8 shrink-0 cv-action-primary text-xs ${compact ? "w-8 px-0" : "px-2.5"}`} onClick={() => onMove(deal, next.key)} aria-label={`Move ${deal.name} to ${next.label}`} title={`Move to ${next.label}`} data-testid={`advance-${deal.id}`}>
            {/* Board columns are narrow, so the board shows the arrow alone; its tooltip names the stage. */}
            {!compact && "Next"}<ArrowRight className={compact ? "h-3.5 w-3.5" : "ml-1 h-3 w-3"} />
          </Button>
        )}
      </div>
    </article>
  );
}
