// Saved views for a record list: the row of views, the filter builder and its chips, the
// columns menu and the save dialog. Filters run on the server (`?where=`), so a view
// shows every matching record, not just the ones already loaded.

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { cn as cx } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Columns3, Filter, Lock, MoreHorizontal, Plus, Users, X } from "lucide-react";

const OPS = {
  text: ["contains", "is", "is_not", "is_empty", "is_not_empty"],
  select: ["is", "is_not", "is_empty", "is_not_empty"],
  id: ["is", "is_not", "is_empty", "is_not_empty"],
  number: ["gt", "lt", "is", "is_empty", "is_not_empty"],
  date: ["after", "before", "is_empty", "is_not_empty"],
  checkbox: ["is"],
  list: ["contains", "is_empty", "is_not_empty"],
};
const OP_LABEL = { is: "is", is_not: "is not", contains: "contains", is_empty: "is empty", is_not_empty: "is not empty", gt: "more than", lt: "less than", before: "before", after: "after", in: "is any of" };
const NO_VALUE = new Set(["is_empty", "is_not_empty"]);

/** Same filters, same order: what decides whether a view has unsaved changes. */
export const sameFilters = (a = [], b = []) => JSON.stringify(a) === JSON.stringify(b);

/** "Lifecycle is Customer": a filter as a person reads it. */
export function describeFilter(filter, fields) {
  const field = fields.find((item) => item.key === filter.field);
  const label = field?.label || filter.field;
  if (NO_VALUE.has(filter.op)) return `${label} ${OP_LABEL[filter.op]}`;
  let value = filter.value;
  if (field?.kind === "checkbox") value = value ? "Yes" : "No";
  else if (field?.options) value = field.options.find((option) => option.value === value)?.label ?? value;
  return `${label} ${OP_LABEL[filter.op] || filter.op} ${value ?? ""}`.trim();
}

/** The row of views above a list: built-in ones first, then the saved ones. */
export function ViewBar({ views, activeId, onSelect, trailing, label = "Saved views" }) {
  return <div className="flex flex-wrap items-center gap-1.5 pt-3" role="group" aria-label={label}>
    {views.map((view) => {
      const active = view.id === activeId;
      return <button key={view.id} type="button" onClick={() => onSelect(view)} aria-pressed={active} data-testid={`view-${view.id}`}
        className={cx("inline-flex h-7 items-center gap-1.5 rounded-full border px-3 text-[13px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          active ? "border-foreground/80 bg-foreground text-background" : "border-border bg-card text-foreground/80 hover:bg-muted")}>
        {view.saved && !view.shared && <Lock className="size-3" aria-label="Only you" />}
        {view.name}
      </button>;
    })}
    {trailing}
  </div>;
}

/** "+ Filter": pick a field, a comparison and a value. */
export function AddFilter({ fields, onAdd }) {
  const [open, setOpen] = useState(false);
  const [fieldKey, setFieldKey] = useState("");
  const [op, setOp] = useState("");
  const [value, setValue] = useState("");
  const field = fields.find((item) => item.key === fieldKey);
  const ops = field ? OPS[field.kind] || OPS.text : [];
  useEffect(() => { if (!open) { setFieldKey(""); setOp(""); setValue(""); } }, [open]);
  const pickField = (key) => {
    const next = fields.find((item) => item.key === key);
    setFieldKey(key); setOp((OPS[next?.kind] || OPS.text)[0]); setValue(next?.kind === "checkbox" ? "true" : "");
  };
  const needsValue = op && !NO_VALUE.has(op);
  const ready = field && op && (!needsValue || String(value).trim() !== "");
  const add = () => {
    if (!ready) return;
    let stored = needsValue ? value : null;
    if (field.kind === "checkbox") stored = value === "true";
    else if (field.kind === "number" && needsValue) stored = Number(value);
    onAdd({ field: field.key, op, value: stored });
    setOpen(false);
  };
  return <Popover open={open} onOpenChange={setOpen}>
    <PopoverTrigger asChild><Button size="sm" variant="outline" className="h-8 gap-1.5 text-[13px]" data-testid="add-filter"><Filter className="size-3.5" />Filter</Button></PopoverTrigger>
    <PopoverContent align="start" className="w-72 space-y-3 p-3">
      <div className="grid gap-1.5">
        <Label htmlFor="filter-field" className="text-xs text-muted-foreground">Field</Label>
        <Select value={fieldKey} onValueChange={pickField}>
          <SelectTrigger id="filter-field" className="h-8 text-[13px]" data-testid="filter-field"><SelectValue placeholder="Choose a field" /></SelectTrigger>
          <SelectContent>{fields.map((item) => <SelectItem key={item.key} value={item.key}>{item.label}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      {field && <div className="grid gap-1.5">
        <Label htmlFor="filter-op" className="text-xs text-muted-foreground">Condition</Label>
        <Select value={op} onValueChange={setOp}>
          <SelectTrigger id="filter-op" className="h-8 text-[13px]" data-testid="filter-op"><SelectValue /></SelectTrigger>
          <SelectContent>{ops.map((item) => <SelectItem key={item} value={item}>{OP_LABEL[item]}</SelectItem>)}</SelectContent>
        </Select>
      </div>}
      {field && needsValue && <div className="grid gap-1.5">
        <Label htmlFor="filter-value" className="text-xs text-muted-foreground">Value</Label>
        {field.options || field.kind === "checkbox"
          ? <Select value={value} onValueChange={setValue}>
              <SelectTrigger id="filter-value" className="h-8 text-[13px]" data-testid="filter-value"><SelectValue placeholder="Choose" /></SelectTrigger>
              <SelectContent>{(field.kind === "checkbox" ? [{ value: "true", label: "Yes" }, { value: "false", label: "No" }] : field.options).map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}</SelectContent>
            </Select>
          : <Input id="filter-value" className="h-8 text-[13px] md:text-[13px]" type={{ number: "number", date: "date" }[field.kind] || "text"} value={value}
              onChange={(event) => setValue(event.target.value)} onKeyDown={(event) => event.key === "Enter" && add()} data-testid="filter-value" />}
      </div>}
      <div className="flex justify-end gap-2 pt-1">
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
        <Button size="sm" className="cv-action-primary" disabled={!ready} onClick={add} data-testid="filter-apply">Apply</Button>
      </div>
    </PopoverContent>
  </Popover>;
}

/** The active filters as removable chips. */
export function FilterChips({ filters, fields, onRemove, onClear }) {
  if (!filters.length) return null;
  return <div className="flex flex-wrap items-center gap-1.5 pb-3" data-testid="filter-chips">
    {filters.map((filter, index) => <span key={`${filter.field}-${index}`} className="inline-flex h-7 items-center gap-1 rounded-md border border-brand/30 bg-brand/5 pl-2.5 pr-1 text-[12.5px] text-foreground">
      {describeFilter(filter, fields)}
      <button type="button" onClick={() => onRemove(index)} className="flex size-5 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground" aria-label={`Remove filter: ${describeFilter(filter, fields)}`}><X className="size-3" /></button>
    </span>)}
    <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-muted-foreground" onClick={onClear}>Clear filters</Button>
  </div>;
}

/** Which columns the list shows. The first (the name) is always on. */
export function ColumnsMenu({ columns, available, onChange, manageHref }) {
  const toggle = (key, on) => onChange(on ? available.map((item) => item.key).filter((k) => k === key || columns.includes(k)) : columns.filter((k) => k !== key));
  return <DropdownMenu>
    <DropdownMenuTrigger asChild><Button size="sm" variant="outline" className="h-8 gap-1.5 text-[13px]" data-testid="columns-menu"><Columns3 className="size-3.5" />Columns</Button></DropdownMenuTrigger>
    <DropdownMenuContent align="end" className="max-h-80 w-56 overflow-y-auto">
      <DropdownMenuLabel className="text-xs font-medium text-muted-foreground">Show columns</DropdownMenuLabel>
      <DropdownMenuSeparator />
      {available.map((item) => <DropdownMenuCheckboxItem key={item.key} checked={columns.includes(item.key)} onCheckedChange={(on) => toggle(item.key, on)} onSelect={(event) => event.preventDefault()} className="text-[13px]">{item.label}</DropdownMenuCheckboxItem>)}
      {manageHref && <><DropdownMenuSeparator /><DropdownMenuItem asChild className="text-[13px]"><Link to={manageHref} data-testid="manage-fields">Manage fields…</Link></DropdownMenuItem></>}
    </DropdownMenuContent>
  </DropdownMenu>;
}

/** Save the current filters, columns and order as a view: a new one, or over the open one. */
export function SaveViewMenu({ activeView, dirty, canUpdate, onSaveNew, onUpdate, onDelete }) {
  const [dialog, setDialog] = useState(false);
  const showUpdate = activeView?.saved && dirty && canUpdate;
  return <>
    {showUpdate && <Button size="sm" variant="outline" className="h-7 rounded-full text-[13px]" onClick={onUpdate} data-testid="view-update">Save changes</Button>}
    {(dirty || !activeView?.saved) && <Button size="sm" variant="ghost" className="h-7 gap-1 rounded-full px-2.5 text-[13px] text-muted-foreground" onClick={() => setDialog(true)} data-testid="view-save-new"><Plus className="size-3.5" />Save view</Button>}
    {activeView?.saved && canUpdate && <DropdownMenu>
      <DropdownMenuTrigger asChild><Button size="sm" variant="ghost" className="size-7 rounded-full p-0" aria-label={`More for ${activeView.name}`} data-testid="view-more"><MoreHorizontal className="size-4" /></Button></DropdownMenuTrigger>
      <DropdownMenuContent align="start"><DropdownMenuItem className="text-[13px] text-red-700" onSelect={onDelete} data-testid="view-delete">Delete “{activeView.name}”</DropdownMenuItem></DropdownMenuContent>
    </DropdownMenu>}
    {dialog && <SaveViewDialog onClose={() => setDialog(false)} onSave={async (name, shared) => { const ok = await onSaveNew(name, shared); if (ok) setDialog(false); }} />}
  </>;
}

function SaveViewDialog({ onClose, onSave }) {
  const [name, setName] = useState("");
  const [shared, setShared] = useState(true);
  const [saving, setSaving] = useState(false);
  const submit = async () => { if (!name.trim()) return; setSaving(true); await onSave(name.trim(), shared); setSaving(false); };
  return <Dialog open onOpenChange={(value) => !value && onClose()}>
    <DialogContent className="sm:max-w-[420px]">
      <DialogHeader><DialogTitle>Save this view</DialogTitle><DialogDescription>Keeps the filters, columns and order, so the list is one click away.</DialogDescription></DialogHeader>
      <div className="space-y-4">
        <div className="grid gap-1.5"><Label htmlFor="view-name" className="text-[13px] font-medium">Name</Label><Input id="view-name" value={name} maxLength={60} onChange={(event) => setName(event.target.value)} onKeyDown={(event) => event.key === "Enter" && submit()} placeholder="e.g. Customers in Austin" data-testid="view-name" /></div>
        <div className="flex items-center justify-between gap-3 rounded-lg border border-border p-3">
          <div><Label htmlFor="view-shared" className="flex items-center gap-1.5 text-[13px] font-medium"><Users className="size-3.5" aria-hidden="true" />Share with the team</Label><p className="mt-0.5 text-xs text-muted-foreground">Off: only you see it.</p></div>
          <Switch id="view-shared" checked={shared} onCheckedChange={setShared} data-testid="view-shared" />
        </div>
      </div>
      <DialogFooter><Button variant="outline" size="sm" onClick={onClose}>Cancel</Button><Button size="sm" className="cv-action-primary" disabled={!name.trim() || saving} onClick={submit} data-testid="view-save">{saving ? "Saving…" : "Save view"}</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
}

/** Built-in plus custom fields, in the shape the filter builder and columns menu read. */
export function useListFields(builtins, defs) {
  return useMemo(() => [
    ...builtins,
    ...defs.map((def) => ({
      key: `custom_fields.${def.key}`, label: def.label, custom: true, def,
      kind: { long_text: "text", url: "text", email: "text", phone: "text" }[def.type] || def.type,
      options: def.type === "select" ? (def.options || []).map((option) => ({ value: option, label: option })) : undefined,
    })),
  ], [builtins, defs]);
}
