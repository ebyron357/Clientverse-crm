/* Settings → Fields: the fields a business adds to contacts, companies and deals.
   An admin adds, renames and archives them; everyone sees the list. Archiving hides a
   field from records and keeps every value already stored, so nothing is lost. */

import { useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { api, formatErr } from "@/lib/api";
import { FIELD_TYPES, fieldTypeLabel, RECORD_OBJECTS, useFieldDefs } from "@/lib/recordFields";
import { PageHeader, StatusDot, ViewTabs } from "@/components/page/Page";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Archive, ArchiveRestore, Pencil, Plus, SlidersHorizontal } from "lucide-react";

const TH = "h-9 whitespace-nowrap px-4 text-left text-xs font-medium text-muted-foreground";
const TD = "px-4 py-2.5 align-top";
const SINGULAR = { contacts: "contact", companies: "company", deals: "deal" };

export default function CustomFieldsSettings() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [object, setObject] = useState("contacts");
  const [showArchived, setShowArchived] = useState(false);
  const { defs, loaded, reload } = useFieldDefs(object, { includeArchived: true });
  const [editing, setEditing] = useState(null);
  const visible = defs.filter((def) => showArchived || !def.archived_at);
  const archivedCount = defs.filter((def) => def.archived_at).length;

  const setArchived = async (def, archived) => {
    try {
      await api.patch(`/custom-fields/${def.id}`, { archived });
      toast.success(archived ? `“${def.label}” archived` : `“${def.label}” restored`, archived ? { description: "Its values are kept. Restore it to show it on records again." } : undefined);
      await reload();
    } catch (requestError) { toast.error("Nothing was changed", { description: formatErr(requestError.response?.data?.detail) }); }
  };

  return <div className="cv-page">
    <PageHeader icon={SlidersHorizontal} title="Fields" description="The details your business tracks on every contact, company and deal. Add a field once and it appears on each record, in filters and as a list column."
      actions={isAdmin && <Button size="sm" className="cv-action-primary" onClick={() => setEditing({ object })} data-testid="field-new"><Plus className="size-3.5" />New {SINGULAR[object]} field</Button>} />
    <ViewTabs label="Record type" value={object} onChange={setObject} items={RECORD_OBJECTS.map((item) => ({ value: item.value, label: item.label, testid: `fields-tab-${item.value}` }))}
      trailing={archivedCount > 0 && <div className="flex items-center gap-2"><Switch id="fields-show-archived" checked={showArchived} onCheckedChange={setShowArchived} /><Label htmlFor="fields-show-archived" className="text-[13px] font-normal text-muted-foreground">Show archived ({archivedCount})</Label></div>} />
    {!isAdmin && <p className="mt-3 text-[13px] text-muted-foreground">Only an admin can add or change fields. You can fill them in on any record.</p>}
    <div className="mt-4 overflow-hidden rounded-xl border border-border bg-card">
      {!loaded ? <div className="space-y-3 p-4">{[0, 1, 2].map((index) => <Skeleton key={index} className="h-5 w-2/3" />)}</div>
        : !visible.length ? <div className="flex flex-col items-center px-6 py-12 text-center" data-testid="fields-empty">
            <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground"><SlidersHorizontal className="size-[18px]" aria-hidden="true" /></span>
            <h2 className="mt-3 text-sm font-medium">No {SINGULAR[object]} fields yet</h2>
            <p className="mt-1 max-w-md text-[13px] leading-5 text-muted-foreground">Add what you need to know about every {SINGULAR[object]}: a budget, a renewal date, a plan, a referral source. Each field can be filled in on the record and used to filter lists.</p>
            {isAdmin && <Button size="sm" className="cv-action-primary mt-4" onClick={() => setEditing({ object })}><Plus className="size-3.5" />Add the first field</Button>}
          </div>
        : <div className="overflow-x-auto"><table className="w-full text-[13px]">
            <caption className="sr-only">{RECORD_OBJECTS.find((item) => item.value === object)?.label} fields</caption>
            <thead><tr className="border-b border-border bg-muted/40"><th scope="col" className={TH}>Field</th><th scope="col" className={TH}>Type</th><th scope="col" className={`${TH} hidden md:table-cell`}>Choices</th><th scope="col" className={`${TH} hidden lg:table-cell`}>API key</th><th scope="col" className={TH}>Status</th>{isAdmin && <th scope="col" className={`${TH} text-right`}><span className="sr-only">Actions</span></th>}</tr></thead>
            <tbody>{visible.map((def) => <tr key={def.id} className="border-b border-border/70 last:border-0" data-testid={`field-row-${def.key}`}>
              <td className={TD}><div className="font-medium text-foreground">{def.label}</div>{def.help_text && <div className="mt-0.5 text-xs text-muted-foreground">{def.help_text}</div>}</td>
              <td className={`${TD} text-foreground/80`}>{fieldTypeLabel(def.type)}</td>
              <td className={`${TD} hidden max-w-[260px] text-foreground/80 md:table-cell`}>{def.options?.length ? <span className="line-clamp-2">{def.options.join(", ")}</span> : <span className="text-muted-foreground">—</span>}</td>
              <td className={`${TD} hidden lg:table-cell`}><code className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">custom_fields.{def.key}</code></td>
              <td className={TD}>{def.archived_at ? <StatusDot tone="neutral">Archived</StatusDot> : <StatusDot tone="success">In use</StatusDot>}</td>
              {isAdmin && <td className={`${TD} whitespace-nowrap text-right`}>
                <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setEditing(def)} aria-label={`Edit ${def.label}`} data-testid={`field-edit-${def.key}`}><Pencil className="size-3.5" /></Button>
                <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setArchived(def, !def.archived_at)} aria-label={def.archived_at ? `Restore ${def.label}` : `Archive ${def.label}`} data-testid={`field-archive-${def.key}`}>{def.archived_at ? <ArchiveRestore className="size-3.5" /> : <Archive className="size-3.5" />}</Button>
              </td>}
            </tr>)}</tbody>
          </table></div>}
    </div>
    {editing && <FieldDialog field={editing} onClose={() => setEditing(null)} onSaved={async () => { setEditing(null); await reload(); }} />}
  </div>;
}

function FieldDialog({ field, onClose, onSaved }) {
  const isNew = !field.id;
  const [label, setLabel] = useState(field.label || "");
  const [type, setType] = useState(field.type || "text");
  const [options, setOptions] = useState((field.options || []).join("\n"));
  const [help, setHelp] = useState(field.help_text || "");
  const [saving, setSaving] = useState(false);
  const optionList = options.split("\n").map((option) => option.trim()).filter(Boolean);
  const submit = async () => {
    if (!label.trim()) { toast.error("Give the field a name."); return; }
    if (type === "select" && !optionList.length) { toast.error("A choice field needs at least one choice."); return; }
    setSaving(true);
    try {
      const body = { label: label.trim(), help_text: help.trim(), ...(type === "select" ? { options: optionList } : {}) };
      if (isNew) await api.post("/custom-fields", { ...body, object: field.object, type });
      else await api.patch(`/custom-fields/${field.id}`, body);
      toast.success(isNew ? `Added “${label.trim()}”` : "Field saved");
      await onSaved();
    } catch (requestError) { toast.error("The field was not saved", { description: formatErr(requestError.response?.data?.detail) }); }
    finally { setSaving(false); }
  };
  return <Dialog open onOpenChange={(value) => !value && onClose()}>
    <DialogContent className="sm:max-w-[460px]">
      <DialogHeader><DialogTitle>{isNew ? `New ${SINGULAR[field.object]} field` : `Edit “${field.label}”`}</DialogTitle>
        <DialogDescription>{isNew ? "The type decides what the field accepts. It cannot be changed later, so stored values always fit it." : "Renaming keeps every value already stored."}</DialogDescription></DialogHeader>
      <div className="space-y-3.5">
        <div className="grid gap-1.5"><Label htmlFor="field-label" className="text-[13px] font-medium">Name</Label><Input id="field-label" value={label} maxLength={80} onChange={(event) => setLabel(event.target.value)} placeholder="e.g. Budget" data-testid="field-label" /></div>
        <div className="grid gap-1.5"><Label htmlFor="field-type" className="text-[13px] font-medium">Type</Label>
          <Select value={type} onValueChange={setType} disabled={!isNew}>
            <SelectTrigger id="field-type" data-testid="field-type"><SelectValue /></SelectTrigger>
            <SelectContent>{FIELD_TYPES.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        {type === "select" && <div className="grid gap-1.5"><Label htmlFor="field-options" className="text-[13px] font-medium">Choices, one per line</Label><Textarea id="field-options" rows={4} value={options} onChange={(event) => setOptions(event.target.value)} placeholder={"Starter\nGrowth\nEnterprise"} data-testid="field-options" /></div>}
        <div className="grid gap-1.5"><Label htmlFor="field-help" className="text-[13px] font-medium">Help text <span className="font-normal text-muted-foreground">(optional)</span></Label><Input id="field-help" value={help} maxLength={200} onChange={(event) => setHelp(event.target.value)} placeholder="Shown under the field when someone fills it in" /></div>
      </div>
      <DialogFooter><Button size="sm" variant="outline" onClick={onClose}>Cancel</Button><Button size="sm" className="cv-action-primary" disabled={saving} onClick={submit} data-testid="field-save">{saving ? "Saving…" : isNew ? "Add field" : "Save"}</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
}
