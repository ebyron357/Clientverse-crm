import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr } from "@/lib/api";
import { formatFieldValue, useFieldDefs } from "@/lib/recordFields";
import { PropertyList } from "@/components/page/Page";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Pencil, SlidersHorizontal } from "lucide-react";

const NONE = "__none";
const INPUT = "h-8 text-[13px] md:text-[13px]";

/** One input for one field, shaped by its type. `value` is what the record stores. */
export function FieldInput({ def, value, onChange, id }) {
  if (def.type === "checkbox") {
    return <div className="flex h-8 items-center gap-2"><Checkbox id={id} checked={Boolean(value)} onCheckedChange={(checked) => onChange(checked === true)} /><Label htmlFor={id} className="text-[13px] font-normal">{value ? "Yes" : "No"}</Label></div>;
  }
  if (def.type === "select") {
    return <Select value={value || NONE} onValueChange={(next) => onChange(next === NONE ? null : next)}>
      <SelectTrigger id={id} className="h-8 text-[13px]"><SelectValue /></SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>Not set</SelectItem>
        {(def.options || []).map((option) => <SelectItem key={option} value={option}>{option}</SelectItem>)}
      </SelectContent>
    </Select>;
  }
  if (def.type === "long_text") {
    return <Textarea id={id} rows={3} className="text-[13px]" value={value ?? ""} onChange={(event) => onChange(event.target.value)} />;
  }
  const inputType = { number: "number", date: "date", email: "email", phone: "tel", url: "url" }[def.type] || "text";
  return <Input id={id} type={inputType} className={INPUT} value={value ?? ""} onChange={(event) => onChange(event.target.value)}
    placeholder={def.type === "url" ? "https://" : undefined} inputMode={def.type === "number" ? "decimal" : undefined} />;
}

/**
 * The admin-defined fields of one record, read and edited in place.
 * `endpoint` is the record's PATCH address; only changed values are sent, and the server
 * checks each against its field's type. Renders nothing when the record type has no fields,
 * except for an admin, who is pointed at where to add them.
 */
export function CustomFieldsSection({ object, endpoint, values = {}, onSaved, isAdmin, disabled, testid = "custom-fields" }) {
  const { defs, loaded } = useFieldDefs(object);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState(false);
  useEffect(() => { setEditing(false); }, [endpoint]);

  if (!loaded) return null;
  if (!defs.length) {
    return isAdmin ? <p className="mt-4 flex items-center gap-1.5 text-xs text-muted-foreground" data-testid={`${testid}-empty`}>
      <SlidersHorizontal className="size-3.5" aria-hidden="true" />Track more about every record: <Link to="/settings/fields" className="font-medium text-brand-strong hover:underline">add fields</Link>
    </p> : null;
  }

  const start = () => { setDraft(Object.fromEntries(defs.map((def) => [def.key, values?.[def.key] ?? (def.type === "checkbox" ? false : "")]))); setEditing(true); };
  const save = async () => {
    const changed = Object.fromEntries(defs
      .filter((def) => (draft[def.key] ?? "") !== (values?.[def.key] ?? (def.type === "checkbox" ? false : "")))
      .map((def) => [def.key, draft[def.key] === "" ? null : draft[def.key]]));
    if (!Object.keys(changed).length) { setEditing(false); return; }
    setSaving(true);
    try {
      await api.patch(endpoint, { custom_fields: changed });
      toast.success("Fields saved");
      setEditing(false);
      await onSaved?.();
    } catch (requestError) {
      toast.error("Nothing was saved", { description: formatErr(requestError.response?.data?.detail) });
    } finally { setSaving(false); }
  };

  return <section className="mt-5 border-t border-border pt-4" aria-labelledby={`${testid}-title`} data-testid={testid}>
    <div className="mb-1 flex items-center justify-between gap-2">
      <h3 id={`${testid}-title`} className="text-xs font-medium text-muted-foreground">More fields</h3>
      {!editing && !disabled && <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={start} data-testid={`${testid}-edit`}><Pencil className="size-3" />Edit</Button>}
    </div>
    {editing ? <div className="space-y-3 pt-1">
      {defs.map((def) => <div key={def.key} className="grid gap-1.5">
        <Label htmlFor={`${testid}-${def.key}`} className="text-xs font-medium text-muted-foreground">{def.label}</Label>
        <FieldInput id={`${testid}-${def.key}`} def={def} value={draft[def.key]} onChange={(value) => setDraft((current) => ({ ...current, [def.key]: value }))} />
        {def.help_text && <p className="text-xs text-muted-foreground">{def.help_text}</p>}
      </div>)}
      <div className="flex justify-end gap-2 border-t border-border pt-3">
        <Button size="sm" variant="outline" disabled={saving} onClick={() => setEditing(false)}>Cancel</Button>
        <Button size="sm" className="cv-action-primary" disabled={saving} onClick={save} data-testid={`${testid}-save`}>{saving ? "Saving…" : "Save fields"}</Button>
      </div>
    </div> : <PropertyList items={defs.map((def) => ({ label: def.label, value: formatFieldValue(def, values?.[def.key]), testid: `${testid}-${def.key}` }))} />}
  </section>;
}
