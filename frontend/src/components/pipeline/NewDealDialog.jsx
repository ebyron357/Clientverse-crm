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
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-lg" data-testid="new-deal-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl">New deal</DialogTitle>
          <DialogDescription>Add what you know now. You can change any of it later from the deal.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-1.5">
            <Label htmlFor="new-deal-name">Deal name <span className="text-red-500">*</span></Label>
            <Input id="new-deal-name" value={form.name} onChange={(event) => setField("name", event.target.value)} placeholder="e.g. Jane Buyer · 77 Bay Rd" data-testid="new-deal-name" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="new-deal-contacts">Who is it with?</Label>
            <ContactPicker id="new-deal-contacts" selected={form.contacts} onChange={(contacts) => setField("contacts", contacts)} testId="new-deal-contacts" />
          </div>
          <div className="grid grid-cols-[minmax(0,1fr)_7.5rem] gap-3 [&>*]:min-w-0">
            <div className="grid gap-1.5">
              <Label htmlFor="new-deal-value">Expected value</Label>
              <Input id="new-deal-value" type="number" inputMode="decimal" min="0" step="any" value={form.value} onChange={(event) => setField("value", event.target.value)} placeholder="e.g. 18000" data-testid="new-deal-value" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="new-deal-currency">Currency</Label>
              <Select value={form.currency} onValueChange={(value) => setField("currency", value)}>
                <SelectTrigger id="new-deal-currency" data-testid="new-deal-currency"><SelectValue /></SelectTrigger>
                <SelectContent>{currencyOptions(defaults.currency).map((code) => <SelectItem key={code} value={code}>{code}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 [&>*]:min-w-0">
            <div className="grid gap-1.5">
              <Label htmlFor="new-deal-stage">Starting stage</Label>
              <Select value={form.stage} onValueChange={(value) => setField("stage", value)}>
                <SelectTrigger id="new-deal-stage" data-testid="new-deal-stage"><SelectValue /></SelectTrigger>
                <SelectContent>{openStages.map((stage) => <SelectItem key={stage.key} value={stage.key}>{stage.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="new-deal-close">Expected close date</Label>
              <Input id="new-deal-close" type="date" value={form.expected_close_date} onChange={(event) => setField("expected_close_date", event.target.value)} data-testid="new-deal-close-date" />
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 [&>*]:min-w-0">
            <div className="grid gap-1.5">
              <Label htmlFor="new-deal-owner">Owner</Label>
              <Select value={form.owner} onValueChange={(value) => setField("owner", value)}>
                <SelectTrigger id="new-deal-owner" data-testid="new-deal-owner"><SelectValue placeholder="Choose who owns it" /></SelectTrigger>
                <SelectContent>{owners.map((owner) => <SelectItem key={owner.email} value={owner.email}>{ownerLabel(owner)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            {companies.length > 0 && (
              <div className="grid gap-1.5">
                <Label htmlFor="new-deal-company">Company <span className="font-normal text-slate-400">(optional)</span></Label>
                <Select value={form.company_id} onValueChange={(value) => setField("company_id", value)}>
                  <SelectTrigger id="new-deal-company" data-testid="new-deal-company"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NO_COMPANY}>No company</SelectItem>
                    {companies.map((company) => <SelectItem key={company.id} value={company.id}>{company.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={saving} onClick={submit} className="cv-action-primary" data-testid="new-deal-submit">{saving ? "Creating…" : "Create deal"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
