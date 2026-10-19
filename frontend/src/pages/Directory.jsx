import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, formatErr, money } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { fullDateLabel } from "@/lib/contactHistory";
import ContactRecord, { MiniStatus, RECORD_SHEET, RecordEmpty, RecordLayout, RecordList, useWideLayout } from "@/components/ContactRecord";
import ContactCleanup from "@/components/ContactCleanup";
import { CustomFieldsSection } from "@/components/CustomFields";
import { AddFilter, ColumnsMenu, FilterChips, SaveViewMenu, ViewBar, sameFilters, useListFields } from "@/components/ListViews";
import { formatFieldValue, LIFECYCLE, lifecycleOf, useFieldDefs } from "@/lib/recordFields";
import { Avatar, PageHeader, PropertyList, StatusDot, Toolbar, ViewTabs } from "@/components/page/Page";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { ArrowUpDown, Building2, BriefcaseBusiness, CircleAlert, GitBranch, Phone, Plus, RefreshCw, Search, UserRound, Users } from "lucide-react";

const TIER = { enterprise: { label: "Enterprise", tone: "violet" }, growth: { label: "Growth", tone: "brand" }, standard: { label: "Standard", tone: "neutral" } };
const RELATIONSHIP = { positive: { label: "Good", tone: "success" }, neutral: { label: "Neutral", tone: "neutral" }, negative: { label: "At risk", tone: "danger" } };
const EMPTY_CONTACT = { name: "", phone: "", email: "", role: "", company_id: "", influence: "medium", sentiment: "neutral" };
const ARCHIVED_FLAG = "shrink-0 rounded border border-amber-200 bg-amber-50 px-1.5 py-px text-[11px] font-medium leading-4 text-amber-700";
const ALL = "all";
const NO_COMPANY = "none";
const CONTACT_SORTS = [["recent", "Recently added"], ["updated", "Last updated"], ["name", "Name A–Z"]];
const COMPANY_SORTS = [["recent", "Recently added"], ["name", "Name A–Z"]];
const SELECT_TRIGGER = "h-8 w-auto gap-1.5 text-[13px]";
const TH = "h-9 whitespace-nowrap px-4 text-left text-xs font-medium text-muted-foreground";
const TD = "whitespace-nowrap px-4 py-2.5";
const isOpenDeal = (item) => item.stage !== "closed_won" && item.stage !== "closed_lost";

// Columns a contact list can show, beside the name that is always first. Custom fields join after these.
const CONTACT_COLUMNS = [["email", "Email"], ["phone", "Phone"], ["company_id", "Company"], ["lifecycle", "Lifecycle"], ["owner", "Owner"], ["sentiment", "Relationship"], ["updated_at", "Updated"]].map(([key, label]) => ({ key, label }));
const DEFAULT_CONTACT_COLUMNS = CONTACT_COLUMNS.map((column) => column.key);
// Narrow screens drop the less-used columns first; the mobile list replaces the table below md.
const COLUMN_SCREEN = { email: "hidden xl:table-cell", owner: "hidden xl:table-cell", sentiment: "hidden lg:table-cell", lifecycle: "hidden lg:table-cell" };
// The list order a view stores, and the menu choice it maps to.
const SORT_TO_VIEW = { recent: { field: "created_at", order: "desc" }, updated: { field: "updated_at", order: "desc" }, name: { field: "name", order: "asc" } };
const sortFromView = (sort) => Object.entries(SORT_TO_VIEW).find(([, value]) => value.field === sort?.field)?.[0] || "recent";
const sameList = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/** "Oct 18" this year, "Oct 18, 2025" before it. */
function shortDate(iso) {
  const date = new Date(iso);
  if (!iso || Number.isNaN(date.getTime())) return "—";
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", ...(sameYear ? {} : { year: "numeric" }) });
}

/** A row opens its record when clicked anywhere, except on a link or button inside it (those do their own thing). */
function rowOpener(open) {
  return (event) => {
    if (event.target.closest("a, button, input, label, [role='checkbox']")) return;
    if (window.getSelection?.().toString()) return;
    open();
  };
}

const MARK_TONES = ["bg-sky-100 text-sky-700", "bg-violet-100 text-violet-700", "bg-emerald-100 text-emerald-700", "bg-amber-100 text-amber-700", "bg-rose-100 text-rose-700", "bg-indigo-100 text-indigo-700"];
/** A company's square initial, the counterpart of a person's round avatar. */
function CompanyMark({ name = "", size = "sm" }) {
  const hash = [...name].reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const sizes = { xs: "size-4 rounded text-[9px]", sm: "size-6 rounded-md text-[11px]", md: "size-8 rounded-lg text-xs", lg: "size-11 rounded-xl text-base" };
  return <span className={`inline-flex shrink-0 items-center justify-center font-semibold ${MARK_TONES[hash % MARK_TONES.length]} ${sizes[size] || sizes.sm}`} aria-hidden="true">{name.trim().charAt(0).toUpperCase() || "?"}</span>;
}

export default function Directory({ initialTab = "companies" }) {
  const { user } = useAuth();
  const [companies, setCompanies] = useState([]); const [contacts, setContacts] = useState([]); const [opportunities, setOpportunities] = useState([]); const [workspaces, setWorkspaces] = useState([]);
  const [activeTab, setActiveTab] = useState(initialTab); const [query, setQuery] = useState(""); const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  const [companyDialog, setCompanyDialog] = useState(false); const [contactDialog, setContactDialog] = useState(false); const [selected, setSelected] = useState(null); const [saving, setSaving] = useState(false);
  const [companyForm, setCompanyForm] = useState({ name: "", industry: "", website: "", tier: "standard" }); const [contactForm, setContactForm] = useState(EMPTY_CONTACT); const [showArchived, setShowArchived] = useState(false);
  // List-only view controls: which company or tier to show and in what order. They never change what is stored.
  const [companyFilter, setCompanyFilter] = useState(ALL); const [tierFilter, setTierFilter] = useState(ALL); const [sort, setSort] = useState("recent");
  // Saved views of the contact list. Filters run on the server, so a view finds every match, not just the loaded page.
  const [savedViews, setSavedViews] = useState([]); const [filters, setFilters] = useState([]); const [columns, setColumns] = useState(DEFAULT_CONTACT_COLUMNS); const [contactsBusy, setContactsBusy] = useState(false);
  const { defs: contactDefs } = useFieldDefs("contacts");
  // The open contact lives in the address (/contacts?contact=<id>) so a link from a lead, a notification or another page opens it directly.
  const [searchParams, setSearchParams] = useSearchParams(); const contactId = searchParams.get("contact");
  const openContact = useCallback((id) => setSearchParams((params) => { params.set("contact", id); return params; }), [setSearchParams]); const closeContact = useCallback(() => setSearchParams((params) => { params.delete("contact"); return params; }), [setSearchParams]);
  // The sidebar's Contacts and Companies links reuse this page, so follow the route's tab; a /companies?company=<id> link (from a deal) opens that company.
  useEffect(() => { setActiveTab(initialTab); }, [initialTab]);
  const companyId = searchParams.get("company");
  const activeViewId = searchParams.get("view") || "all";
  useEffect(() => { if (!companyId) return; const company = companies.find((item) => item.id === companyId); if (company) { setActiveTab("companies"); setSelected({ type: "company", record: company }); } }, [companyId, companies]);
  const closeCompany = useCallback(() => { setSelected(null); setSearchParams((params) => { params.delete("company"); return params; }); }, [setSearchParams]);
  // A quiet reload refreshes the lists behind an open record without flashing the page back to its loading state.
  // Contacts load on their own, so changing a filter refreshes only the list. A ticket drops replies that arrive out of order.
  const whereJson = filters.length ? JSON.stringify(filters) : "";
  const contactTicket = useRef(0);
  const fetchContacts = useCallback(async () => {
    const ticket = ++contactTicket.current;
    const { data } = await api.get("/contacts", { params: { limit: 1000, ...(showArchived ? { include_archived: true } : {}), ...(whereJson ? { where: whereJson } : {}) } });
    if (ticket === contactTicket.current) setContacts(data);
  }, [showArchived, whereJson]);
  const fetchContactsRef = useRef(fetchContacts); fetchContactsRef.current = fetchContacts;
  // A quiet reload refreshes the lists behind an open record without flashing the page back to its loading state.
  const load = useCallback(async ({ quiet = false } = {}) => { if (!quiet) { setLoading(true); setError(""); } try { const [companyResponse, , opportunityResponse, workspaceResponse] = await Promise.all([api.get("/companies"), fetchContactsRef.current(), api.get("/opportunities"), api.get("/workspaces")]); setCompanies(companyResponse.data); setOpportunities(opportunityResponse.data); setWorkspaces(workspaceResponse.data); } catch { if (!quiet) setError("We could not load the directory. The relationship data has not changed — please try again."); } finally { if (!quiet) setLoading(false); } }, []);
  useEffect(() => { load(); }, [load]);
  const firstContactLoad = useRef(true);
  useEffect(() => {
    if (firstContactLoad.current) { firstContactLoad.current = false; return; }
    setContactsBusy(true);
    fetchContacts().catch((requestError) => toast.error("That filter could not be applied", { description: formatErr(requestError.response?.data?.detail) })).finally(() => setContactsBusy(false));
  }, [fetchContacts]);
  const loadViews = useCallback(async () => { try { const { data } = await api.get("/views", { params: { object: "contacts" } }); setSavedViews(data.items || []); } catch { setSavedViews([]); } }, []);
  useEffect(() => { loadViews(); }, [loadViews]);
  const companyName = useCallback((id) => companies.find((company) => company.id === id)?.name || "", [companies]);
  const filteredCompanies = useMemo(() => companies.filter((company) => `${company.name} ${company.industry || ""}`.toLowerCase().includes(query.toLowerCase())), [companies, query]);
  const filteredContacts = useMemo(() => { const term = query.toLowerCase(); const digits = query.replace(/\D/g, ""); return contacts.filter((contact) => `${contact.name} ${contact.email || ""} ${contact.phone || ""} ${companyName(contact.company_id)}`.toLowerCase().includes(term) || (digits.length >= 3 && String(contact.phone || "").replace(/\D/g, "").includes(digits))); }, [contacts, query, companyName]);
  const createCompany = async () => { if (!companyForm.name.trim()) { toast.error("Company name is required."); return; } setSaving(true); try { await api.post("/companies", { ...companyForm, name: companyForm.name.trim() }); toast.success("Company created"); setCompanyDialog(false); setCompanyForm({ name: "", industry: "", website: "", tier: "standard" }); await load(); } catch (requestError) { toast.error("Could not create company", { description: formatErr(requestError.response?.data?.detail) }); } finally { setSaving(false); } };
  // Blank optional fields are sent as nothing: an empty email is not an email address, and the server rightly refuses one.
  const createContact = async () => { if (!contactForm.name.trim()) { toast.error("Contact name is required."); return; } if (contactForm.email.trim() && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(contactForm.email.trim())) { toast.error("That email address doesn't look right."); return; } setSaving(true); try { const { data } = await api.post("/contacts", { ...contactForm, name: contactForm.name.trim(), email: contactForm.email.trim() || null, phone: contactForm.phone.trim() || null, role: contactForm.role.trim() || null, company_id: contactForm.company_id || null }); toast.success("Contact created"); setContactDialog(false); setContactForm(EMPTY_CONTACT); await load({ quiet: true }); openContact(data.id); } catch (requestError) { toast.error("Could not create contact", { description: formatErr(requestError.response?.data?.detail) }); } finally { setSaving(false); } };

  // View controls applied on top of the search, in the order the person picked.
  const visibleContacts = useMemo(() => {
    const list = filteredContacts.filter((contact) => companyFilter === ALL || (companyFilter === NO_COMPANY ? !contact.company_id : contact.company_id === companyFilter));
    if (sort === "name") return [...list].sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    if (sort === "updated") return [...list].sort((a, b) => String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || "")));
    return list;
  }, [filteredContacts, companyFilter, sort]);
  const visibleCompanies = useMemo(() => {
    const list = filteredCompanies.filter((company) => tierFilter === ALL || (company.tier || "standard") === tierFilter);
    return sort === "name" ? [...list].sort((a, b) => (a.name || "").localeCompare(b.name || "")) : list;
  }, [filteredCompanies, tierFilter, sort]);
  const ownerName = useCallback((owner) => (owner && owner === user?.email ? user?.name || owner : owner), [user]);

  // What a contact view can filter on and show: the built-in fields, then the business's own.
  const builtinContactFields = useMemo(() => [
    { key: "name", label: "Name", kind: "text" },
    { key: "email", label: "Email", kind: "text" },
    { key: "phone", label: "Phone", kind: "text" },
    { key: "company_id", label: "Company", kind: "id", options: companies.map((company) => ({ value: company.id, label: company.name })) },
    { key: "lifecycle", label: "Lifecycle", kind: "select", options: LIFECYCLE.map((stage) => ({ value: stage.value, label: stage.label })) },
    { key: "owner", label: "Owner (email)", kind: "text" },
    { key: "sentiment", label: "Relationship", kind: "select", options: Object.entries(RELATIONSHIP).map(([value, item]) => ({ value, label: item.label })) },
    { key: "role", label: "Role", kind: "text" },
    { key: "tags", label: "Tags", kind: "list" },
    { key: "created_at", label: "Added", kind: "date" },
    { key: "updated_at", label: "Updated", kind: "date" },
    { key: "last_inquiry_at", label: "Last website request", kind: "date" },
  ], [companies]);
  const contactFields = useListFields(builtinContactFields, contactDefs);
  const columnOptions = useMemo(() => [...CONTACT_COLUMNS, ...contactDefs.map((def) => ({ key: `custom_fields.${def.key}`, label: def.label }))], [contactDefs]);
  const builtinViews = useMemo(() => [
    { id: "all", name: "All contacts", filters: [] },
    { id: "leads", name: "Leads", filters: [{ field: "lifecycle", op: "is", value: "lead" }] },
    { id: "customers", name: "Customers", filters: [{ field: "lifecycle", op: "is", value: "customer" }] },
    { id: "mine", name: "My contacts", filters: [{ field: "owner", op: "is", value: user?.email || "" }] },
    { id: "no_company", name: "No company", filters: [{ field: "company_id", op: "is_empty", value: null }] },
  ], [user]);
  const allViews = useMemo(() => [...builtinViews, ...savedViews.map((view) => ({ ...view, saved: true }))], [builtinViews, savedViews]);
  const activeView = allViews.find((view) => view.id === activeViewId) || builtinViews[0];
  const applyView = useCallback((view) => { setFilters(view.filters || []); setColumns(view.columns || DEFAULT_CONTACT_COLUMNS); setSort(sortFromView(view.sort)); }, []);
  // A view named in the address (/contacts?view=<id>) opens once the saved views have loaded.
  const appliedView = useRef(null);
  useEffect(() => { const view = allViews.find((item) => item.id === activeViewId); if (view && appliedView.current !== view.id) { appliedView.current = view.id; applyView(view); } }, [allViews, activeViewId, applyView]);
  const selectView = (view) => { appliedView.current = view.id; applyView(view); setSearchParams((params) => { if (view.id === "all") params.delete("view"); else params.set("view", view.id); return params; }); };
  const viewDirty = !sameFilters(filters, activeView.filters) || !sameList(columns, activeView.columns || DEFAULT_CONTACT_COLUMNS) || sort !== sortFromView(activeView.sort);
  const canUpdateView = Boolean(activeView.saved && (activeView.owner === user?.email?.toLowerCase() || user?.role === "admin"));
  const viewBody = () => ({ filters, columns, sort: SORT_TO_VIEW[sort] || SORT_TO_VIEW.recent });
  const saveNewView = async (name, shared) => {
    try {
      const { data } = await api.post("/views", { object: "contacts", name, shared, ...viewBody() });
      await loadViews(); selectView({ ...data, saved: true }); toast.success(`Saved “${data.name}”`); return true;
    } catch (requestError) { toast.error("The view was not saved", { description: formatErr(requestError.response?.data?.detail) }); return false; }
  };
  const updateView = async () => {
    try { await api.patch(`/views/${activeView.id}`, viewBody()); await loadViews(); toast.success(`Updated “${activeView.name}”`); }
    catch (requestError) { toast.error("The view was not updated", { description: formatErr(requestError.response?.data?.detail) }); }
  };
  const deleteView = async () => {
    try { await api.delete(`/views/${activeView.id}`); toast.success(`Deleted “${activeView.name}”`); selectView(builtinViews[0]); await loadViews(); }
    catch (requestError) { toast.error("The view was not deleted", { description: formatErr(requestError.response?.data?.detail) }); }
  };

  if (error) return <div className="cv-page"><div className="flex flex-col items-center justify-center py-24 text-center"><span className="flex size-10 items-center justify-center rounded-full bg-muted"><CircleAlert className="size-5 text-red-600" aria-hidden="true" /></span><h1 className="mt-3 text-sm font-medium text-foreground">Directory unavailable</h1><p className="mt-1 max-w-md text-[13px] leading-5 text-muted-foreground">{error}</p><Button size="sm" onClick={load} className="mt-4 cv-action-primary"><RefreshCw className="size-3.5" />Retry</Button></div></div>;

  const isContacts = activeTab === "contacts";
  const total = isContacts ? contacts.length : companies.length;
  const shown = isContacts ? visibleContacts.length : visibleCompanies.length;
  const filtered = Boolean(query.trim()) || (isContacts ? companyFilter !== ALL || filters.length > 0 : tierFilter !== ALL);
  const clearFilters = () => { setQuery(""); setCompanyFilter(ALL); setTierFilter(ALL); setFilters([]); };
  const sorts = isContacts ? CONTACT_SORTS : COMPANY_SORTS;
  const contactButton = <CreateContactDialog key="contact" primary={isContacts} open={contactDialog} onOpenChange={setContactDialog} form={contactForm} setForm={setContactForm} companies={companies} saving={saving} onSubmit={createContact} />;
  const companyButton = <CreateCompanyDialog key="company" primary={!isContacts} open={companyDialog} onOpenChange={setCompanyDialog} form={companyForm} setForm={setCompanyForm} saving={saving} onSubmit={createCompany} />;

  return <div className="cv-page">
    <PageHeader icon={isContacts ? UserRound : Building2} title={isContacts ? "Contacts" : "Companies"} count={loading ? undefined : total}
      actions={isContacts ? [companyButton, contactButton] : [contactButton, companyButton]} />
    <ViewTabs label="Directory" value={activeTab} onChange={setActiveTab}
      items={[
        { value: "companies", label: "Companies", icon: Building2, count: loading ? undefined : companies.length },
        { value: "contacts", label: "Contacts", icon: UserRound, count: loading ? undefined : contacts.length },
      ]} />
    {isContacts && <ViewBar views={allViews} activeId={activeView.id} onSelect={selectView} label="Contact views"
      trailing={<SaveViewMenu activeView={activeView} dirty={viewDirty} canUpdate={canUpdateView} onSaveNew={saveNewView} onUpdate={updateView} onDelete={deleteView} />} />}
    {isContacts && !loading && <div className="pt-3"><ContactCleanup onChanged={() => load({ quiet: true })} /></div>}
    <Toolbar>
      <div className="relative w-full sm:w-64">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
        <Input value={query} onChange={(event) => setQuery(event.target.value)} className="h-8 pl-8 text-[13px] md:text-[13px]" placeholder={isContacts ? "Search name, phone, email…" : `Search ${activeTab}…`} aria-label={`Search ${activeTab}`} />
      </div>
      {isContacts ? (
        <Select value={companyFilter} onValueChange={setCompanyFilter}>
          <SelectTrigger className={SELECT_TRIGGER} aria-label="Filter by company"><Building2 className="size-3.5 text-muted-foreground" aria-hidden="true" /><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All companies</SelectItem>
            <SelectItem value={NO_COMPANY}>No company</SelectItem>
            {companies.map((company) => <SelectItem key={company.id} value={company.id}>{company.name}</SelectItem>)}
          </SelectContent>
        </Select>
      ) : (
        <Select value={tierFilter} onValueChange={setTierFilter}>
          <SelectTrigger className={SELECT_TRIGGER} aria-label="Filter by tier"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All tiers</SelectItem>
            {Object.entries(TIER).map(([value, tier]) => <SelectItem key={value} value={value}>{tier.label}</SelectItem>)}
          </SelectContent>
        </Select>
      )}
      <Select value={sorts.some(([key]) => key === sort) ? sort : "recent"} onValueChange={setSort}>
        <SelectTrigger className={SELECT_TRIGGER} aria-label="Sort"><ArrowUpDown className="size-3.5 text-muted-foreground" aria-hidden="true" /><SelectValue /></SelectTrigger>
        <SelectContent>{sorts.map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent>
      </Select>
      {isContacts && <AddFilter fields={contactFields} onAdd={(filter) => setFilters((current) => [...current, filter])} />}
      {isContacts && <ColumnsMenu columns={columns} available={columnOptions} onChange={setColumns} manageHref="/settings/fields" />}
      <div className="ml-auto flex items-center gap-4">
        {filtered && !loading && <span className="tabular text-xs text-muted-foreground">{shown} {isContacts && filters.length ? (shown === 1 ? "match" : "matches") : `of ${total}`}</span>}
        {isContacts && <div className="flex items-center gap-2"><Switch id="contacts-show-archived" checked={showArchived} onCheckedChange={setShowArchived} data-testid="contacts-show-archived" /><Label htmlFor="contacts-show-archived" className="text-[13px] font-normal text-muted-foreground">Show archived</Label></div>}
      </div>
    </Toolbar>
    {isContacts && <FilterChips filters={filters} fields={contactFields} onRemove={(index) => setFilters((current) => current.filter((_, i) => i !== index))} onClear={() => setFilters([])} />}
    {loading ? <DirectorySkeleton /> : isContacts
      ? <ContactsTable contacts={visibleContacts} companies={companies} ownerName={ownerName} busy={contactsBusy} columns={columns.filter((key) => columnOptions.some((column) => column.key === key))} columnOptions={columnOptions} defs={contactDefs} onSelect={(contact) => openContact(contact.id)} empty={<EmptyDirectory type="contact" filtered={filtered} onClear={clearFilters} onCreate={() => setContactDialog(true)} />} />
      : <CompaniesTable companies={visibleCompanies} contacts={contacts} opportunities={opportunities} workspaces={workspaces} onSelect={(company) => setSelected({ type: "company", record: company })} empty={<EmptyDirectory type="company" filtered={filtered} onClear={clearFilters} onCreate={() => setCompanyDialog(true)} />} />}
    {selected?.type === "company" && <CompanyRecord company={companies.find((item) => item.id === selected.record.id) || selected.record} contacts={contacts} opportunities={opportunities} workspaces={workspaces} isAdmin={user?.role === "admin"} onChanged={() => load({ quiet: true })} open onOpenChange={(value) => !value && closeCompany()} onOpenContact={(contact) => { closeCompany(); openContact(contact.id); }} />}
    {contactId && <ContactRecord contactId={contactId} open onOpenChange={(value) => !value && closeContact()} companies={companies} workspaces={workspaces} onChanged={() => load({ quiet: true })} />}
  </div>;
}

/* ---------- Lists ---------- */

function ContactsTable({ contacts, companies, ownerName, onSelect, empty, columns = DEFAULT_CONTACT_COLUMNS, columnOptions = CONTACT_COLUMNS, defs = [], busy = false }) {
  const coName = (id) => companies.find((company) => company.id === id)?.name || "";
  if (!contacts.length) return <div className={`rounded-xl border border-border bg-card transition-opacity ${busy ? "opacity-60" : ""}`}>{empty}</div>;
  const dash = <span className="text-muted-foreground">—</span>;
  const label = (key) => columnOptions.find((column) => column.key === key)?.label || key;
  const screen = (key) => COLUMN_SCREEN[key] || (key.startsWith("custom_fields.") ? "hidden lg:table-cell" : "");
  const cell = (key, contact) => {
    if (key === "email") return <span className="block max-w-[240px] truncate text-foreground/80">{contact.email || dash}</span>;
    if (key === "phone") return contact.phone ? <a href={`tel:${contact.phone}`} className="tabular text-foreground/80 hover:text-brand-strong hover:underline">{contact.phone}</a> : dash;
    if (key === "company_id") { const company = coName(contact.company_id); return company ? <span className="flex max-w-[200px] items-center gap-2 text-foreground/80"><CompanyMark name={company} size="xs" /><span className="truncate">{company}</span></span> : dash; }
    if (key === "lifecycle") { const stage = lifecycleOf(contact.lifecycle); return stage ? <StatusDot tone={stage.tone}>{stage.label}</StatusDot> : dash; }
    if (key === "owner") { const owner = ownerName(contact.owner); return owner ? <span className="flex max-w-[180px] items-center gap-2 text-foreground/80"><Avatar name={owner} size="sm" /><span className="truncate">{owner}</span></span> : dash; }
    if (key === "sentiment") { const relationship = RELATIONSHIP[contact.sentiment] || RELATIONSHIP.neutral; return <StatusDot tone={relationship.tone}>{relationship.label}</StatusDot>; }
    if (key === "updated_at") { const updated = contact.updated_at || contact.created_at; return <span className="tabular text-muted-foreground" title={fullDateLabel(updated)}>{shortDate(updated)}</span>; }
    const def = defs.find((item) => `custom_fields.${item.key}` === key);
    const shown = def && formatFieldValue(def, contact.custom_fields?.[def.key]);
    return shown ? <span className="block max-w-[200px] truncate text-foreground/80" title={shown}>{shown}</span> : dash;
  };
  return <div className={`overflow-hidden rounded-xl border border-border bg-card transition-opacity ${busy ? "opacity-60" : ""}`} aria-busy={busy}>
    <div className="hidden overflow-x-auto md:block">
      <table className="w-full text-left text-[13px]">
        <caption className="sr-only">Contacts</caption>
        <thead><tr className="border-b border-border bg-muted/40">
          <th scope="col" className={TH}>Name</th>
          {columns.map((key) => <th key={key} scope="col" className={`${TH} ${screen(key)} ${key === "updated_at" ? "text-right" : ""}`}>{label(key)}</th>)}
        </tr></thead>
        <tbody>{contacts.map((contact) => {
          const roleLine = [contact.role, contact.title].filter(Boolean).join(" · ");
          return (
            // Mouse users can click anywhere on the row; keyboard users reach the same action through the name button.
            <tr key={contact.id} onClick={rowOpener(() => onSelect(contact))} className="cursor-pointer border-b border-border/70 transition-colors last:border-0 hover:bg-muted/50" data-testid={`contact-row-${contact.id}`}>
              <td className="px-4 py-1.5">
                <button type="button" onClick={() => onSelect(contact)} className="flex min-h-8 min-w-[200px] items-center gap-2.5 rounded-md text-left" data-testid={`contact-open-${contact.id}`}>
                  <Avatar name={contact.name} size="sm" />
                  <span className="min-w-0">
                    <span className="flex items-center gap-1.5"><span className="truncate font-medium text-foreground">{contact.name}</span>{contact.archived_at && <span className={ARCHIVED_FLAG}>Archived</span>}</span>
                    {roleLine ? <span className="block truncate text-xs text-muted-foreground">{roleLine}</span> : contact.email && <span className="block truncate text-xs text-muted-foreground xl:hidden">{contact.email}</span>}
                  </span>
                </button>
              </td>
              {columns.map((key) => <td key={key} className={`${TD} ${screen(key)} ${key === "updated_at" ? "text-right" : ""}`}>{cell(key, contact)}</td>)}
            </tr>
          );
        })}</tbody>
      </table>
    </div>
    <ul className="divide-y divide-border/70 md:hidden">{contacts.map((contact) => {
      const relationship = RELATIONSHIP[contact.sentiment] || RELATIONSHIP.neutral;
      return <li key={contact.id} className="flex items-center gap-2 pr-3 transition-colors hover:bg-muted/50">
        <button type="button" onClick={() => onSelect(contact)} className="flex min-w-0 flex-1 items-center gap-3 py-3 pl-4 text-left" data-testid={`contact-card-${contact.id}`}>
          <Avatar name={contact.name} size="md" />
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-1.5"><span className="truncate text-[13px] font-medium text-foreground">{contact.name}</span>{contact.archived_at && <span className={ARCHIVED_FLAG}>Archived</span>}</span>
            <span className="mt-0.5 block truncate text-xs text-muted-foreground">{[contact.phone || contact.email || "No phone yet", contact.company_id ? coName(contact.company_id) || "—" : contact.role].filter(Boolean).join(" · ")}</span>
          </span>
        </button>
        {contact.phone
          ? <a href={`tel:${contact.phone}`} aria-label={`Call ${contact.name}`} className="flex size-9 shrink-0 items-center justify-center rounded-full border border-emerald-200 bg-emerald-50 text-emerald-700 transition-colors" data-testid={`contact-card-call-${contact.id}`}><Phone className="size-4" aria-hidden="true" /></a>
          : <MiniStatus tone={relationship.tone} className="shrink-0">{relationship.label}</MiniStatus>}
      </li>;
    })}</ul>
  </div>;
}

function CompaniesTable({ companies, contacts, opportunities, workspaces, onSelect, empty }) {
  if (!companies.length) return <div className="rounded-xl border border-border bg-card">{empty}</div>;
  const related = (company) => ({
    people: contacts.filter((contact) => contact.company_id === company.id).length,
    deals: opportunities.filter((opportunity) => opportunity.company_id === company.id),
    workspace: workspaces.find((record) => record.company_id === company.id),
  });
  return <div className="overflow-hidden rounded-xl border border-border bg-card">
    <div className="hidden overflow-x-auto md:block">
      <table className="w-full text-left text-[13px]">
        <caption className="sr-only">Companies</caption>
        <thead><tr className="border-b border-border bg-muted/40">
          <th scope="col" className={TH}>Company</th>
          <th scope="col" className={TH}>Industry</th>
          <th scope="col" className={TH}>Tier</th>
          <th scope="col" className={`${TH} hidden text-right lg:table-cell`}>Contacts</th>
          <th scope="col" className={`${TH} hidden text-right lg:table-cell`}>Deals</th>
          <th scope="col" className={`${TH} hidden xl:table-cell`}>Client workspace</th>
          <th scope="col" className={`${TH} text-right`}>Added</th>
        </tr></thead>
        <tbody>{companies.map((company) => {
          const { people, deals, workspace } = related(company);
          const tier = TIER[company.tier] || TIER.standard;
          return (
            // Mouse users can click anywhere on the row; keyboard users reach the same action through the name button.
            <tr key={company.id} onClick={rowOpener(() => onSelect(company))} className="cursor-pointer border-b border-border/70 transition-colors last:border-0 hover:bg-muted/50">
              <td className="px-4 py-1.5">
                <button type="button" onClick={() => onSelect(company)} className="flex min-h-8 min-w-[200px] items-center gap-2.5 rounded-md text-left">
                  <CompanyMark name={company.name} size="sm" />
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-foreground">{company.name}</span>
                    {company.website && <span className="block truncate text-xs text-muted-foreground">{company.website.replace(/^https?:\/\//, "")}</span>}
                  </span>
                </button>
              </td>
              <td className={`${TD} text-foreground/80`}>{company.industry || <span className="text-muted-foreground">—</span>}</td>
              <td className={TD}><StatusDot tone={tier.tone}>{tier.label}</StatusDot></td>
              <td className={`${TD} tabular hidden text-right text-foreground/80 lg:table-cell`}>{people}</td>
              <td className={`${TD} tabular hidden text-right text-foreground/80 lg:table-cell`}>{deals.length}</td>
              <td className={`${TD} hidden xl:table-cell`}>{workspace ? <StatusDot tone="success">Active</StatusDot> : <span className="text-muted-foreground">No workspace yet</span>}</td>
              <td className={`${TD} tabular text-right text-muted-foreground`} title={fullDateLabel(company.created_at)}>{shortDate(company.created_at)}</td>
            </tr>
          );
        })}</tbody>
      </table>
    </div>
    <ul className="divide-y divide-border/70 md:hidden">{companies.map((company) => {
      const { people } = related(company);
      const tier = TIER[company.tier] || TIER.standard;
      return <li key={company.id}>
        <button type="button" onClick={() => onSelect(company)} className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/50">
          <CompanyMark name={company.name} size="md" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13px] font-medium text-foreground">{company.name}</span>
            <span className="mt-0.5 block truncate text-xs text-muted-foreground">{company.industry || "No industry"} · {people} contact{people === 1 ? "" : "s"}</span>
          </span>
          <MiniStatus tone={tier.tone} className="shrink-0">{tier.label}</MiniStatus>
        </button>
      </li>;
    })}</ul>
  </div>;
}

function EmptyDirectory({ type, filtered, onClear, onCreate }) {
  const company = type === "company";
  const Icon = filtered ? Search : company ? Building2 : UserRound;
  return <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
    <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground"><Icon className="size-[18px]" aria-hidden="true" /></span>
    <h3 className="mt-3 text-sm font-medium text-foreground">{filtered ? `No ${company ? "companies" : "contacts"} match` : `No ${company ? "companies" : "contacts"} found`}</h3>
    <p className="mt-1 max-w-sm text-[13px] leading-5 text-muted-foreground">{filtered ? "Try another search, or clear the filters." : company ? "Create a company to connect revenue, client workspace, and relationship activity." : "Add a contact to give your team the person-level context behind each client relationship."}</p>
    <div className="mt-4">{filtered
      ? <Button size="sm" variant="outline" onClick={onClear}>Clear filters</Button>
      : <Button size="sm" className="cv-action-primary" onClick={onCreate}><Plus className="size-3.5" />{company ? "New company" : "New contact"}</Button>}</div>
  </div>;
}

function DirectorySkeleton() {
  return <div className="overflow-hidden rounded-xl border border-border bg-card" aria-busy="true">
    <div className="flex h-9 items-center gap-6 border-b border-border bg-muted/40 px-4"><Skeleton className="h-3 w-16" /><Skeleton className="hidden h-3 w-14 md:block" /><Skeleton className="hidden h-3 w-16 md:block" /><Skeleton className="ml-auto h-3 w-12" /></div>
    {Array.from({ length: 6 }).map((_, index) => <div key={index} className="flex items-center gap-3 border-b border-border/70 px-4 py-3 last:border-0"><Skeleton className="size-6 rounded-full" /><div className="flex-1 space-y-1.5"><Skeleton className="h-3.5 w-40" /><Skeleton className="h-3 w-24" /></div><Skeleton className="hidden h-3.5 w-24 md:block" /><Skeleton className="hidden h-3.5 w-28 md:block" /><Skeleton className="h-3.5 w-12" /></div>)}
  </div>;
}

/* ---------- Create dialogs ---------- */

const FIELD_LABEL = "text-[13px] font-medium";
const DIALOG = "gap-0 overflow-hidden p-0 sm:max-w-[480px]";
const DIALOG_HEADER = "space-y-1 px-5 pb-4 pr-12 pt-5 text-left";
const DIALOG_FOOTER = "gap-2 border-t border-border bg-muted/30 px-5 py-3 sm:space-x-0";

function CreateCompanyDialog({ open, onOpenChange, form, setForm, saving, onSubmit, primary }) {
  const setField = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogTrigger asChild><Button size="sm" variant={primary ? "default" : "outline"} className={primary ? "cv-action-primary" : ""}>{primary ? <Plus className="size-3.5" /> : <Building2 className="size-3.5" />}New company</Button></DialogTrigger>
    <DialogContent className={DIALOG}>
      <DialogHeader className={DIALOG_HEADER}><DialogTitle className="text-base font-semibold">New company</DialogTitle><DialogDescription className="text-[13px]">Add a business you work with. Only the name is required.</DialogDescription></DialogHeader>
      <div className="grid gap-3.5 px-5 pb-5">
        <div className="grid gap-1.5"><Label htmlFor="new-company-name" className={FIELD_LABEL}>Company name <span className="text-red-600">*</span></Label><Input id="new-company-name" value={form.name} onChange={(event) => setField("name", event.target.value)} /></div>
        <div className="grid gap-3.5 sm:grid-cols-2">
          <div className="grid gap-1.5"><Label htmlFor="new-company-industry" className={FIELD_LABEL}>Industry</Label><Input id="new-company-industry" value={form.industry} onChange={(event) => setField("industry", event.target.value)} placeholder="e.g. Healthcare" /></div>
          <div className="grid gap-1.5"><Label htmlFor="new-company-tier" className={FIELD_LABEL}>Client tier</Label><Select value={form.tier} onValueChange={(value) => setField("tier", value)}><SelectTrigger id="new-company-tier"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="standard">Standard</SelectItem><SelectItem value="growth">Growth</SelectItem><SelectItem value="enterprise">Enterprise</SelectItem></SelectContent></Select></div>
        </div>
        <div className="grid gap-1.5"><Label htmlFor="new-company-website" className={FIELD_LABEL}>Website</Label><Input id="new-company-website" value={form.website} onChange={(event) => setField("website", event.target.value)} placeholder="https://example.com" /></div>
      </div>
      <DialogFooter className={DIALOG_FOOTER}><Button size="sm" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button size="sm" disabled={saving} onClick={onSubmit} className="cv-action-primary">{saving ? "Creating…" : "Create company"}</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
}

function CreateContactDialog({ open, onOpenChange, form, setForm, companies, saving, onSubmit, primary }) {
  const setField = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogTrigger asChild><Button size="sm" variant={primary ? "default" : "outline"} className={primary ? "cv-action-primary" : ""}>{primary ? <Plus className="size-3.5" /> : <UserRound className="size-3.5" />}New contact</Button></DialogTrigger>
    <DialogContent className={DIALOG}>
      <DialogHeader className={DIALOG_HEADER}><DialogTitle className="text-base font-semibold">New contact</DialogTitle><DialogDescription className="text-[13px]">Add a person you work with. Only the name is required.</DialogDescription></DialogHeader>
      <div className="grid gap-3.5 px-5 pb-5">
        <div className="grid gap-1.5"><Label htmlFor="new-contact-name" className={FIELD_LABEL}>Name <span className="text-red-600">*</span></Label><Input id="new-contact-name" value={form.name} onChange={(event) => setField("name", event.target.value)} data-testid="new-contact-name" /></div>
        <div className="grid gap-3.5 sm:grid-cols-2">
          <div className="grid gap-1.5"><Label htmlFor="new-contact-phone" className={FIELD_LABEL}>Phone</Label><Input id="new-contact-phone" type="tel" inputMode="tel" autoComplete="tel" value={form.phone} onChange={(event) => setField("phone", event.target.value)} placeholder="(555) 010-0100" data-testid="new-contact-phone" /></div>
          <div className="grid gap-1.5"><Label htmlFor="new-contact-email" className={FIELD_LABEL}>Email</Label><Input id="new-contact-email" type="email" inputMode="email" value={form.email} onChange={(event) => setField("email", event.target.value)} placeholder="name@example.com" data-testid="new-contact-email" /></div>
        </div>
        <div className="grid gap-1.5"><Label htmlFor="new-contact-company" className={FIELD_LABEL}>Company</Label><Select value={form.company_id} onValueChange={(value) => setField("company_id", value)}><SelectTrigger id="new-contact-company"><SelectValue placeholder="Select company" /></SelectTrigger><SelectContent>{companies.map((company) => <SelectItem key={company.id} value={company.id}>{company.name}</SelectItem>)}</SelectContent></Select></div>
        <div className="grid grid-cols-2 gap-3.5">
          <div className="grid gap-1.5"><Label htmlFor="new-contact-role" className={FIELD_LABEL}>Role</Label><Input id="new-contact-role" value={form.role} onChange={(event) => setField("role", event.target.value)} placeholder="e.g. VP Operations" /></div>
          <div className="grid gap-1.5"><Label htmlFor="new-contact-influence" className={FIELD_LABEL}>Influence</Label><Select value={form.influence} onValueChange={(value) => setField("influence", value)}><SelectTrigger id="new-contact-influence"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="low">Low</SelectItem><SelectItem value="medium">Medium</SelectItem><SelectItem value="high">High</SelectItem></SelectContent></Select></div>
        </div>
      </div>
      <DialogFooter className={DIALOG_FOOTER}><Button size="sm" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button size="sm" disabled={saving} onClick={onSubmit} className="cv-action-primary" data-testid="new-contact-save">{saving ? "Creating…" : "Create contact"}</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
}

/* ---------- Company record ---------- */

function CompanyRecord({ company, contacts, opportunities, workspaces, isAdmin, onChanged, open, onOpenChange, onOpenContact }) {
  const relatedContacts = contacts.filter((contact) => contact.company_id === company.id);
  const relatedOpps = opportunities.filter((opportunity) => opportunity.company_id === company.id);
  const workspace = workspaces.find((record) => record.company_id === company.id);
  const openOpps = relatedOpps.filter(isOpenDeal);
  const tier = TIER[company.tier] || TIER.standard;
  const wide = useWideLayout();
  const [tab, setTab] = useState("contacts");
  useEffect(() => { setTab("contacts"); }, [company.id]);
  const website = company.website?.replace(/^https?:\/\//, "");

  const details = <section aria-labelledby="company-details-title">
    <h3 id="company-details-title" className="sr-only">Details</h3>
    <PropertyList items={[
      { label: "Industry", value: company.industry || <span className="text-muted-foreground">Not set</span> },
      { label: "Website", value: website || <span className="text-muted-foreground">Not set</span> },
      { label: "Tier", value: <StatusDot tone={tier.tone}>{tier.label}</StatusDot> },
      { label: "Primary contacts", value: <span className="tabular">{relatedContacts.length}</span> },
      { label: "Open opportunities", value: <span className="tabular">{openOpps.length}</span> },
      { label: "Client workspace", value: workspace ? <Link className="font-medium text-brand-strong hover:underline" to={`/workspaces/${workspace.id}`}>{workspace.name}</Link> : <span className="text-muted-foreground">Not created</span> },
      { label: "Added", value: fullDateLabel(company.created_at) || "—" },
    ]} />
    <CustomFieldsSection object="companies" endpoint={`/companies/${company.id}`} values={company.custom_fields} isAdmin={isAdmin} disabled={Boolean(company.archived_at)} onSaved={onChanged} testid="company-fields" />
  </section>;

  return <Sheet open={open} onOpenChange={onOpenChange}>
    <SheetContent className={RECORD_SHEET} data-testid="company-record">
      <RecordLayout
        wide={wide}
        avatar={<CompanyMark name={company.name} size="lg" />}
        title={company.name}
        meta={[company.industry, website].filter(Boolean).join(" · ") || "Company relationship record"}
        flag={<MiniStatus tone={tier.tone} className="shrink-0">{tier.label}</MiniStatus>}
        value={tab}
        onValueChange={setTab}
        details={details}
        tabs={[
          {
            value: "contacts", label: "Contacts", count: relatedContacts.length,
            content: relatedContacts.length ? <RecordList>{relatedContacts.map((contact) => {
              const relationship = RELATIONSHIP[contact.sentiment] || RELATIONSHIP.neutral;
              return <li key={contact.id}><button type="button" onClick={() => onOpenContact(contact)} className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-muted/50">
                <Avatar name={contact.name} size="sm" />
                <span className="min-w-0 flex-1"><span className="block truncate text-[13px] font-medium text-foreground">{contact.name}</span><span className="block truncate text-xs text-muted-foreground">{contact.role || "No role"} · {contact.email || "No email"}</span></span>
                <StatusDot tone={relationship.tone} className="shrink-0">{relationship.label}</StatusDot>
              </button></li>;
            })}</RecordList> : <RecordEmpty icon={Users} title="No contacts">No contacts are linked to this company.</RecordEmpty>,
          },
          {
            value: "deals", label: "Deals", count: relatedOpps.length,
            content: relatedOpps.length ? <RecordList>{relatedOpps.map((opportunity) => <li key={opportunity.id}><Link to={`/deals?deal=${opportunity.id}`} className="flex items-center gap-3 px-3 py-2.5 transition-colors hover:bg-muted/50">
              <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground"><GitBranch className="size-3.5" aria-hidden="true" /></span>
              <span className="min-w-0 flex-1"><span className="block truncate text-[13px] font-medium text-foreground">{opportunity.name}</span><span className="block text-xs capitalize text-muted-foreground">{opportunity.stage?.replace("_", " ") || "Lead"}</span></span>
              <span className="tabular shrink-0 text-[13px] font-semibold text-foreground">{money(opportunity.value)}</span>
            </Link></li>)}</RecordList> : <RecordEmpty icon={GitBranch} title="No deals">No opportunities are linked to this company.</RecordEmpty>,
          },
          {
            value: "workspace", label: "Client 360",
            content: workspace
              ? <div className="rounded-xl border border-border bg-card p-4">
                  <div className="flex items-center gap-2 text-[13px] font-semibold text-foreground"><BriefcaseBusiness className="size-4 text-brand" aria-hidden="true" />{workspace.name}<MiniStatus tone="success" className="ml-1 font-normal">Active</MiniStatus></div>
                  <p className="mt-1.5 text-[13px] leading-5 text-muted-foreground">A Client 360 workspace is active for this company, with health, outcomes, commitments, approvals and timeline evidence.</p>
                  <Button asChild size="sm" variant="outline" className="mt-3"><Link to={`/workspaces/${workspace.id}`}>Open workspace</Link></Button>
                </div>
              : <RecordEmpty icon={BriefcaseBusiness} title="No Client 360 workspace yet">A workspace is created automatically when an opportunity is won, or can be created from the global Create menu.</RecordEmpty>,
          },
        ]}
      />
    </SheetContent>
  </Sheet>;
}
