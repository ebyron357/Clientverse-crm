/* New deal: the essentials an agent knows when a buyer or seller first gets serious --
   who it is with, what it is worth, when it should close and whose it is. */
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api, formatErr } from "@/lib/api";
import { currencyOptions, ownerLabel } from "@/lib/pipeline";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import ContactPicker from "@/components/pipeline/ContactPicker";

const NO_COMPANY = "__none__";
const MAX_VALUE = 1e10;
const INPUT = "h-9 text-[13px] md:text-[13px]";
const TRIGGER = "h-9 bg-card text-[13px] shadow-xs";

function blankForm(defaults) {
  return { name: "", value: "", currency: defaults.currency, stage: defaults.stage, expected_close_date: "", owner: defaults.owner, company_id: NO_COMPANY, contacts: [] };
}

export default function NewDealDialog({ open, onOpenChange, openStages, companies, owners, defaults, onCreated }) {
  const [form, setForm] = useState(() => blankForm(defaults));
  const [saving, setSaving] = useState(false);
  const setField = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  // A fresh form each time the dialog opens, starting from the board's current defaults.
  // Only on opening: defaults that finish loading later must not wipe what was typed.
  const wasOpen = useRef(false);
  useEffect(() => {
    if (open && !wasOpen.current) setForm(blankForm(defaults));
    wasOpen.current = open;
  }, [open, defaults]);

  const submit = async () => {
    const name = form.name.trim();
    if (!name) { toast.error("Give this deal a name first."); return; }
    const value = form.value === "" ? 0 : Number(form.value);
    if (!Number.isFinite(value) || value < 0 || value > MAX_VALUE) { toast.error("Enter the deal value as a positive number, like 12500."); return; }
    setSaving(true);
    try {
      const { data } = await api.post("/opportunities", {
        name, value, currency: form.currency, stage: form.stage,
        expected_close_date: form.expected_close_date || null,
        owner: form.owner || null,
        company_id: form.company_id === NO_COMPANY ? null : form.company_id,
        contact_ids: form.contacts.map((contact) => contact.id),
      });
      toast.success("Deal created", { description: `${name} is in ${openStages.find((stage) => stage.key === data.stage)?.label || "your pipeline"}.` });
      onOpenChange(false);
      onCreated(data);
    } catch (requestError) {
      toast.error("Could not create the deal", { description: formatErr(requestError.response?.data?.detail) });
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[92vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-lg" data-testid="new-deal-dialog">
        <DialogHeader className="space-y-1 border-b border-border px-5 py-4 pr-12 text-left">
          <DialogTitle className="text-base font-semibold tracking-tight">New deal</DialogTitle>
          <DialogDescription className="text-[13px]">Add what you know now. You can change any of it later from the deal.</DialogDescription>
        </DialogHeader>
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-y-auto px-5 py-4">
          <Field label={<>Deal name <span className="text-red-600" aria-hidden="true">*</span></>} htmlFor="new-deal-name">
            <Input id="new-deal-name" value={form.name} onChange={(event) => setField("name", event.target.value)} placeholder="e.g. Jane Buyer · 77 Bay Rd" aria-required="true" className={INPUT} data-testid="new-deal-name" />
          </Field>
          <Field label="Who is it with?" htmlFor="new-deal-contacts">
            <ContactPicker id="new-deal-contacts" selected={form.contacts} onChange={(contacts) => setField("contacts", contacts)} testId="new-deal-contacts" />
          </Field>
          <div className="grid grid-cols-[minmax(0,1fr)_7.5rem] gap-3 [&>*]:min-w-0">
            <Field label="Expected value" htmlFor="new-deal-value">
              <Input id="new-deal-value" type="number" inputMode="decimal" min="0" step="any" value={form.value} onChange={(event) => setField("value", event.target.value)} placeholder="e.g. 18000" className={`${INPUT} tabular`} data-testid="new-deal-value" />
            </Field>
            <Field label="Currency" htmlFor="new-deal-currency">
              <Select value={form.currency} onValueChange={(value) => setField("currency", value)}>
                <SelectTrigger id="new-deal-currency" aria-label="Currency" className={TRIGGER} data-testid="new-deal-currency"><SelectValue /></SelectTrigger>
                <SelectContent>{currencyOptions(defaults.currency).map((code) => <SelectItem key={code} value={code} className="text-[13px]">{code}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 [&>*]:min-w-0">
            <Field label="Starting stage" htmlFor="new-deal-stage">
              <Select value={form.stage} onValueChange={(value) => setField("stage", value)}>
                <SelectTrigger id="new-deal-stage" aria-label="Starting stage" className={TRIGGER} data-testid="new-deal-stage"><SelectValue /></SelectTrigger>
                <SelectContent>{openStages.map((stage) => <SelectItem key={stage.key} value={stage.key} className="text-[13px]">{stage.label}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Expected close date" htmlFor="new-deal-close">
              <Input id="new-deal-close" type="date" value={form.expected_close_date} onChange={(event) => setField("expected_close_date", event.target.value)} className={INPUT} data-testid="new-deal-close-date" />
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 [&>*]:min-w-0">
            <Field label="Owner" htmlFor="new-deal-owner">
              <Select value={form.owner} onValueChange={(value) => setField("owner", value)}>
                <SelectTrigger id="new-deal-owner" aria-label="Owner" className={TRIGGER} data-testid="new-deal-owner"><SelectValue placeholder="Choose who owns it" /></SelectTrigger>
                <SelectContent>{owners.map((owner) => <SelectItem key={owner.email} value={owner.email} className="text-[13px]">{ownerLabel(owner)}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            {companies.length > 0 && (
              <Field label={<>Company <span className="font-normal text-muted-foreground">(optional)</span></>} htmlFor="new-deal-company">
                <Select value={form.company_id} onValueChange={(value) => setField("company_id", value)}>
                  <SelectTrigger id="new-deal-company" aria-label="Company (optional)" className={TRIGGER} data-testid="new-deal-company"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NO_COMPANY} className="text-[13px]">No company</SelectItem>
                    {companies.map((company) => <SelectItem key={company.id} value={company.id} className="text-[13px]">{company.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </Field>
            )}
          </div>
        </div>
        <DialogFooter className="gap-2 border-t border-border bg-muted/30 px-5 py-3 sm:space-x-0">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button size="sm" disabled={saving} onClick={submit} data-testid="new-deal-submit">{saving ? "Creating…" : "Create deal"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** A label above its control. */
function Field({ label, htmlFor, children }) {
  return <div className="grid min-w-0 grid-cols-1 gap-1.5">
    <Label htmlFor={htmlFor} className="text-[13px] font-medium text-foreground">{label}</Label>
    {children}
  </div>;
}
