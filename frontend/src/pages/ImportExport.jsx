/* Settings → Import and export: bring contacts, companies and deals in from a spreadsheet,
   and take a copy of the records out. An import is always previewed first: the server matches
   each column of the file to a field, the admin adjusts the matches, sees what will happen to
   every row, and only then imports the same file. */

import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { api, formatErr } from "@/lib/api";
import { PageHeader, Section, StatStrip, StatusDot } from "@/components/page/Page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { ArrowDownUp, Download, FileSpreadsheet, RotateCcw, Upload } from "lucide-react";

const TYPES = [
  { value: "contacts", label: "Contacts", one: "contact", many: "contacts", open: "/contacts",
    match: "A contact already in ClientVerse is recognised by email, or by phone when the row has no email.",
    template: ["First name", "Last name", "Email", "Phone", "Company", "Job title", "Lifecycle stage", "Owner"] },
  { value: "companies", label: "Companies", one: "company", many: "companies", open: "/companies",
    match: "A company already in ClientVerse is recognised by its name, or by its website.",
    template: ["Company name", "Industry", "Website", "Client tier", "Owner"] },
  { value: "deals", label: "Deals", one: "deal", many: "deals", open: "/pipeline",
    match: "A deal already in ClientVerse is recognised by its name and company.",
    template: ["Deal name", "Value", "Currency", "Stage", "Expected close date", "Company", "Contact email", "Owner"] },
];
const EXPORTS = [
  { value: "contacts", label: "Contacts", detail: "With company, lifecycle stage and your own fields" },
  { value: "companies", label: "Companies", detail: "With website, tier and your own fields" },
  { value: "deals", label: "Deals", detail: "With stage, company and the people on each deal" },
  { value: "tasks", label: "Tasks", detail: "Every task, open and done" },
];
const DUPLICATES = [
  { value: "skip", label: "Leave it as it is", detail: "The row is skipped." },
  { value: "update", label: "Update it from the file", detail: "Filled-in cells replace what is stored. Empty cells change nothing." },
  { value: "create", label: "Add it as a new record", detail: "The record will then be in ClientVerse twice." },
];
const ACTIONS = {
  create: { tone: "success", plan: "Will be added", done: "Added" },
  update: { tone: "info", plan: "Will update", done: "Updated" },
  skip: { tone: "neutral", plan: "Skipped", done: "Skipped" },
  reject: { tone: "danger", plan: "Can't import", done: "Not imported" },
};
const SKIP_COLUMN = "__skip";
const MAX_BYTES = 5_000_000;
const TH = "h-9 whitespace-nowrap px-4 text-left text-xs font-medium text-muted-foreground";
const TD = "px-4 py-2.5 align-top";

const typeOf = (value) => TYPES.find((type) => type.value === value) || TYPES[0];
const plural = (count, type) => `${count.toLocaleString()} ${count === 1 ? type.one : type.many}`;
const reason = (requestError) => formatErr(requestError.response?.data?.detail);
const when = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "");

function download(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = name; link.click();
  URL.revokeObjectURL(url);
}

/** A spreadsheet's text: UTF-8 when it is, else the Windows encoding older Excel saves in. */
async function readText(file) {
  const buffer = await file.arrayBuffer();
  try { return new TextDecoder("utf-8", { fatal: true }).decode(buffer); } catch { return new TextDecoder("windows-1252").decode(buffer); }
}

export default function ImportExport() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  return <div className="cv-page">
    <PageHeader icon={ArrowDownUp} title="Import and export"
      description="Bring contacts, companies and deals in from a spreadsheet, and take a copy of your records out." />
    <div className="space-y-8">
      {isAdmin ? <ImportPanel /> : <Section title="Import" testid="import-admin-only">
        <p className="text-[13px] text-muted-foreground">Only an admin can import: an import adds and changes records for the whole team.</p>
      </Section>}
      <ExportPanel />
    </div>
  </div>;
}

function ImportPanel() {
  const [params] = useSearchParams();
  const [type, setType] = useState(typeOf(params.get("type")).value);
  const [file, setFile] = useState(null);
  const [fileError, setFileError] = useState(null);
  const [mapping, setMapping] = useState(null);
  const [onDuplicate, setOnDuplicate] = useState("skip");
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState(null);
  const [checking, setChecking] = useState(false);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState(null);
  const [recent, setRecent] = useState(null);
  const inputRef = useRef(null);
  const asked = useRef(0);
  const kind = typeOf(type);

  const loadRecent = useCallback(async () => {
    try { const { data } = await api.get("/imports"); setRecent(data.items || []); } catch { setRecent([]); }
  }, []);
  useEffect(() => { loadRecent(); }, [loadRecent]);

  // Every change to the file, the matches or the duplicate choice asks the server again;
  // only the newest answer is shown.
  const check = useCallback(async (body) => {
    const ticket = ++asked.current;
    setChecking(true); setError(null);
    try {
      const { data } = await api.post(`/import/${type}/preview`, body);
      if (ticket !== asked.current) return;
      setPreview(data);
      if (!body.mapping) setMapping(Object.fromEntries(data.columns.map((column) => [column.header, column.field])));
    } catch (requestError) {
      if (ticket !== asked.current) return;
      setPreview(null); setError(reason(requestError));
    } finally { if (ticket === asked.current) setChecking(false); }
  }, [type]);

  useEffect(() => {
    if (!file || !mapping) return undefined;
    // The answer on screen already describes these choices (the first one after a file is chosen).
    if (preview && preview.on_duplicate === onDuplicate && preview.columns.every((column) => (mapping[column.header] || "") === column.field)) return undefined;
    const timer = setTimeout(() => check({ csv: file.text, file_name: file.name, mapping, on_duplicate: onDuplicate }), 300);
    return () => clearTimeout(timer);
  }, [file, mapping, onDuplicate, preview, check]);

  const reset = () => {
    asked.current += 1;
    setFile(null); setMapping(null); setPreview(null); setError(null); setResult(null); setFileError(null); setChecking(false);
    if (inputRef.current) inputRef.current.value = "";
  };
  const chooseType = (value) => { reset(); setType(value); };

  const pickFile = async (event) => {
    const chosen = event.target.files?.[0];
    setFileError(null); setMapping(null); setPreview(null); setResult(null); setError(null);
    if (!chosen) return;
    if (chosen.size > MAX_BYTES) { setFile(null); setFileError("This file is larger than 5 MB. Split it and import each part."); return; }
    const picked = { name: chosen.name, text: await readText(chosen) };
    setFile(picked);
    check({ csv: picked.text, file_name: picked.name, on_duplicate: onDuplicate });
  };

  const runImport = async () => {
    setImporting(true);
    try {
      const { data } = await api.post(`/import/${type}`, { csv: file.text, file_name: file.name, mapping, on_duplicate: onDuplicate });
      setResult(data);
      const changed = data.created + data.updated;
      toast.success(changed ? `${plural(changed, kind)} imported` : "Nothing was imported",
        { description: [data.created && `${data.created} added`, data.updated && `${data.updated} updated`, data.skipped && `${data.skipped} skipped`, data.rejected && `${data.rejected} not imported`].filter(Boolean).join(" · ") });
      await loadRecent();
    } catch (requestError) {
      toast.error("Nothing was imported", { description: reason(requestError) });
    } finally { setImporting(false); }
  };

  const templateCsv = () => download(new Blob([`${kind.template.join(",")}\n`], { type: "text/csv" }), `clientverse-${type}-template.csv`);
  const shown = result || preview;
  const ready = shown && !result && preview && !preview.missing?.length && preview.created + preview.updated > 0;

  return <Section title="Import" description="From a spreadsheet or another CRM's export, saved as CSV." testid="import-panel">
    <div className="rounded-xl border border-border bg-card">
      <div className="border-b border-border/80 p-4">
        <p className="text-[13px] font-medium" id="import-type-label">1. What is in the file?</p>
        <div role="radiogroup" aria-labelledby="import-type-label" className="mt-2 flex flex-wrap gap-2">
          {TYPES.map((option) => <button key={option.value} type="button" role="radio" aria-checked={type === option.value}
            onClick={() => chooseType(option.value)} disabled={importing}
            className={`h-8 rounded-md border px-3 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${type === option.value ? "border-foreground bg-foreground text-background" : "border-border bg-background text-foreground hover:bg-muted"}`}
            data-testid={`import-type-${option.value}`}>{option.label}</button>)}
        </div>
        <p className="mt-2 text-xs text-muted-foreground">{kind.match}</p>
      </div>

      <div className="border-b border-border/80 p-4">
        <Label htmlFor="import-file" className="text-[13px]">2. Choose the file</Label>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Input ref={inputRef} id="import-file" type="file" accept=".csv,text/csv" onChange={pickFile} disabled={importing} className="max-w-sm" data-testid="import-file" />
          {file && <Button size="sm" variant="ghost" onClick={reset} disabled={importing} data-testid="import-reset"><RotateCcw className="size-3.5" />Start again</Button>}
        </div>
        {fileError && <p className="mt-2 text-xs text-destructive" role="alert">{fileError}</p>}
        <p className="mt-2 text-xs text-muted-foreground">
          CSV, up to 5,000 rows and 5 MB. The first row names the columns. <button type="button" onClick={templateCsv} className="font-medium text-foreground underline underline-offset-2" data-testid="import-template">Download a {kind.one} template</button>
        </p>
      </div>

      {error && <p className="border-b border-border/80 p-4 text-[13px] text-destructive" role="alert" data-testid="import-error">{error}</p>}
      {file && !shown && !error && <div className="space-y-2 p-4">{[0, 1, 2].map((index) => <Skeleton key={index} className="h-5 w-2/3" />)}</div>}

      {shown && !result && mapping && <>
        <div className="border-b border-border/80 p-4" data-testid="import-mapping">
          <p className="text-[13px] font-medium">3. Match each column to a field</p>
          <p className="mt-0.5 text-xs text-muted-foreground">Columns ClientVerse recognised are matched already. Choose “Don't import” for any you do not want.</p>
          {preview.missing?.length > 0 && <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-900" role="alert" data-testid="import-missing">Match a column to {preview.missing.join(", ")}: no {kind.one} can be imported without it.</p>}
          <ColumnMatches columns={preview.columns} fields={preview.fields} mapping={mapping} disabled={importing}
            onChange={(header, field) => setMapping((current) => ({ ...current, [header]: field }))} />
          <div className="mt-4 grid gap-1.5 sm:max-w-md">
            <Label htmlFor="import-duplicates" className="text-[13px]">When a {kind.one} is already in ClientVerse</Label>
            <Select value={onDuplicate} onValueChange={setOnDuplicate} disabled={importing}>
              <SelectTrigger id="import-duplicates" data-testid="import-duplicates"><SelectValue /></SelectTrigger>
              <SelectContent>{DUPLICATES.map((choice) => <SelectItem key={choice.value} value={choice.value}>{choice.label}</SelectItem>)}</SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">{DUPLICATES.find((choice) => choice.value === onDuplicate)?.detail} Archived records are not matched.</p>
          </div>
        </div>
      </>}

      {shown && <Outcome shown={shown} kind={kind} done={Boolean(result)} checking={checking && !result} />}

      {shown && <div className="flex flex-wrap items-center justify-between gap-2 p-4">
        <p className="text-xs text-muted-foreground">{result ? "The import is in Recent imports below." : "Imported records start no automations, and nothing is sent to anyone."}</p>
        <div className="flex gap-2">
          {result ? <>
            <Button size="sm" variant="outline" onClick={reset} data-testid="import-another">Import another file</Button>
            <Button size="sm" asChild><Link to={kind.open}>Open {kind.label.toLowerCase()}</Link></Button>
          </> : <Button size="sm" className="cv-action-primary" onClick={runImport} disabled={!ready || importing || checking} data-testid="import-run">
            <Upload className="size-3.5" />{importing ? "Importing…" : preview ? `Import ${plural(preview.created + preview.updated, kind)}` : "Import"}
          </Button>}
        </div>
      </div>}
    </div>
    <RecentImports items={recent} />
  </Section>;
}

function ColumnMatches({ columns, fields, mapping, onChange, disabled }) {
  const builtIn = fields.filter((field) => !field.custom);
  const custom = fields.filter((field) => field.custom);
  const label = (key) => fields.find((field) => field.key === key)?.label;
  return <div className="mt-3 divide-y divide-border/70 rounded-lg border border-border">
    {columns.map((column) => {
      const value = mapping[column.header] || SKIP_COLUMN;
      const takenElsewhere = new Set(Object.entries(mapping).filter(([header, key]) => header !== column.header && key).map(([, key]) => key));
      return <div key={column.header} className="grid gap-2 px-3 py-2.5 sm:grid-cols-[minmax(0,1fr)_240px] sm:items-center" data-testid={`import-column-${column.header}`}>
        <div className="min-w-0">
          <div className="truncate text-[13px] font-medium text-foreground">{column.header}</div>
          <div className="truncate text-xs text-muted-foreground">{column.samples.length ? column.samples.join(" · ") : "Empty in every row"}</div>
        </div>
        <Select value={value} onValueChange={(next) => onChange(column.header, next === SKIP_COLUMN ? "" : next)} disabled={disabled}>
          <SelectTrigger aria-label={`Field for the column ${column.header}`} className={value === SKIP_COLUMN ? "text-muted-foreground" : ""}>
            <SelectValue>{value === SKIP_COLUMN ? "Don't import" : label(value)}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={SKIP_COLUMN}>Don't import</SelectItem>
            <SelectSeparator />
            <SelectGroup>
              <SelectLabel>Fields</SelectLabel>
              {builtIn.map((field) => <SelectItem key={field.key} value={field.key} disabled={takenElsewhere.has(field.key)}>{field.label}{field.required ? " (required)" : ""}</SelectItem>)}
            </SelectGroup>
            {custom.length > 0 && <SelectGroup>
              <SelectLabel>Your fields</SelectLabel>
              {custom.map((field) => <SelectItem key={field.key} value={field.key} disabled={takenElsewhere.has(field.key)}>{field.label}</SelectItem>)}
            </SelectGroup>}
          </SelectContent>
        </Select>
      </div>;
    })}
  </div>;
}

function Outcome({ shown, kind, done, checking }) {
  const word = (action) => ACTIONS[action][done ? "done" : "plan"];
  const problems = shown.errors || [];
  const notes = shown.warnings || [];
  return <div className="border-b border-border/80 p-4" aria-busy={checking} data-testid={done ? "import-result" : "import-preview"}>
    <p className="text-[13px] font-medium">{done ? "Imported" : "4. Check what will happen"}{checking && <span className="ml-2 font-normal text-muted-foreground">Checking…</span>}</p>
    <StatStrip className="mt-3" items={[
      { label: word("create"), value: shown.created.toLocaleString(), tone: shown.created ? "success" : undefined, testid: "import-count-create" },
      { label: word("update"), value: shown.updated.toLocaleString(), testid: "import-count-update" },
      { label: word("skip"), value: shown.skipped.toLocaleString(), testid: "import-count-skip" },
      { label: word("reject"), value: shown.rejected.toLocaleString(), tone: shown.rejected ? "danger" : undefined, testid: "import-count-reject" },
    ]} />
    {shown.companies_created > 0 && <p className="mt-2 text-xs text-muted-foreground" data-testid="import-new-companies">{shown.companies_created.toLocaleString()} {shown.companies_created === 1 ? "company" : "companies"} {done ? "were" : "will be"} made from the Company column.</p>}
    {problems.length > 0 && <Issues title={done ? "Rows that were not imported" : "Rows that can't be imported"} rows={problems.map((item) => ({ ...item, text: item.error }))} total={shown.rejected} testid="import-problems" />}
    {notes.length > 0 && <Issues title="Notes" rows={notes.map((item) => ({ ...item, text: item.warning }))} total={shown.warning_count} testid="import-notes" />}
    {shown.plan?.length > 0 && <div className="mt-4 overflow-hidden rounded-lg border border-border">
      <div className="overflow-x-auto"><table className="w-full text-[13px]">
        <caption className="sr-only">{done ? "What happened to each row" : "What will happen to each row"}</caption>
        <thead><tr className="border-b border-border bg-muted/40"><th scope="col" className={`${TH} w-16`}>Row</th><th scope="col" className={TH}>{kind.one.charAt(0).toUpperCase() + kind.one.slice(1)}</th><th scope="col" className={TH}>{done ? "What happened" : "What happens"}</th><th scope="col" className={`${TH} hidden md:table-cell`}>Why</th></tr></thead>
        <tbody>{shown.plan.map((row) => <tr key={row.row} className="border-b border-border/70 last:border-0">
          <td className={`${TD} tabular text-muted-foreground`}>{row.row}</td>
          <td className={`${TD} max-w-[260px]`}><div className="truncate text-foreground">{row.label || <span className="text-muted-foreground">No name</span>}</div>{row.reason && <div className="mt-0.5 text-xs text-muted-foreground md:hidden">{row.reason}</div>}</td>
          <td className={`${TD} whitespace-nowrap`}><StatusDot tone={ACTIONS[row.action].tone}>{word(row.action)}</StatusDot></td>
          <td className={`${TD} hidden text-muted-foreground md:table-cell`}>{row.reason || (row.warnings?.length ? row.warnings.join(" ") : "—")}</td>
        </tr>)}</tbody>
      </table></div>
      {shown.plan.length < shown.created + shown.updated + shown.skipped + shown.rejected && <p className="border-t border-border px-4 py-2 text-xs text-muted-foreground">The first {shown.plan.length} rows are shown; the counts above cover the whole file.</p>}
    </div>}
  </div>;
}

function Issues({ title, rows, total, testid }) {
  return <div className="mt-4" data-testid={testid}>
    <p className="text-xs font-medium text-foreground">{title}{total > rows.length ? ` (first ${rows.length} of ${total.toLocaleString()})` : ""}</p>
    <ul className="mt-1.5 space-y-1 text-[13px]">{rows.map((item) => <li key={`${item.row}-${item.text}`} className="flex gap-2">
      <span className="tabular w-14 shrink-0 text-muted-foreground">Row {item.row}</span>
      <span className="min-w-0 text-foreground/90">{item.label ? <span className="font-medium">{item.label}: </span> : null}{item.text}</span>
    </li>)}</ul>
  </div>;
}

function RecentImports({ items }) {
  if (items && !items.length) return null;
  return <div className="mt-6" data-testid="import-recent">
    <h3 className="text-[13px] font-semibold text-foreground">Recent imports</h3>
    <div className="mt-2 overflow-hidden rounded-xl border border-border bg-card">
      {!items ? <div className="space-y-2 p-4"><Skeleton className="h-5 w-1/2" /><Skeleton className="h-5 w-1/3" /></div>
        : <div className="overflow-x-auto"><table className="w-full text-[13px]">
            <caption className="sr-only">Recent imports</caption>
            <thead><tr className="border-b border-border bg-muted/40"><th scope="col" className={TH}>File</th><th scope="col" className={TH}>Result</th><th scope="col" className={`${TH} hidden sm:table-cell`}>When</th></tr></thead>
            <tbody>{items.map((item) => <tr key={item.id} className="border-b border-border/70 last:border-0">
              <td className={`${TD} max-w-[260px]`}><div className="flex items-center gap-1.5 truncate font-medium text-foreground"><FileSpreadsheet className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />{item.file_name || "Pasted file"}</div><div className="mt-0.5 text-xs capitalize text-muted-foreground">{item.entity}<span className="sm:hidden"> · {when(item.created_at)}</span></div></td>
              <td className={`${TD} text-foreground/80`}>{[`${item.created} added`, item.updated && `${item.updated} updated`, item.skipped && `${item.skipped} skipped`, item.rejected && `${item.rejected} not imported`].filter(Boolean).join(" · ")}</td>
              <td className={`${TD} hidden whitespace-nowrap text-foreground/80 sm:table-cell`}>{when(item.created_at)}<div className="text-xs text-muted-foreground">{item.actor}</div></td>
            </tr>)}</tbody>
          </table></div>}
    </div>
  </div>;
}

function ExportPanel() {
  const [includeArchived, setIncludeArchived] = useState(false);
  const [busy, setBusy] = useState(null);
  const exportCsv = async (entity) => {
    setBusy(entity);
    try {
      const response = await api.get(`/export/${entity}`, { params: includeArchived ? { include_archived: true } : {}, responseType: "blob" });
      download(response.data, `${entity}.csv`);
    } catch { toast.error("The export could not be downloaded."); } finally { setBusy(null); }
  };
  return <Section title="Export" description="A complete copy of one record type, as CSV. It imports straight back." testid="export-panel">
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <ul className="divide-y divide-border/70">{EXPORTS.map((item) => <li key={item.value} className="flex items-center justify-between gap-3 px-4 py-3">
        <div className="min-w-0"><div className="text-[13px] font-medium text-foreground">{item.label}</div><div className="text-xs text-muted-foreground">{item.detail}</div></div>
        <Button size="sm" variant="outline" onClick={() => exportCsv(item.value)} disabled={busy !== null} data-testid={`export-${item.value}`}><Download className="size-3.5" />{busy === item.value ? "Preparing…" : "Download CSV"}</Button>
      </li>)}</ul>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-muted/30 px-4 py-3">
        <div className="flex items-center gap-2"><Switch id="export-archived" checked={includeArchived} onCheckedChange={setIncludeArchived} data-testid="export-archived" /><Label htmlFor="export-archived" className="text-[13px] font-normal text-muted-foreground">Include archived records</Label></div>
        <p className="text-xs text-muted-foreground">Leads are exported from <Link to="/leads" className="font-medium text-foreground underline underline-offset-2">Leads</Link> → Export CSV.</p>
      </div>
    </div>
  </Section>;
}
