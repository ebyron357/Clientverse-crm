/* Website forms: build the forms an agent's website uses, choose what happens to every
   lead automatically, and copy the embed code. Mirrors the options a GoHighLevel user
   expects: fields and custom fields, thank-you message or redirect, duplicate handling,
   tags, assignment (including round-robin), a deal in the pipeline, speed-to-lead task
   and escalation, alerts, an automatic reply, and inline / pop-up / iframe / hosted /
   HTML / API embeds. */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Avatar, PageHeader, Section, StatusDot, ViewTabs } from "@/components/page/Page";
import {
  ArrowLeft, Check, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Clock, Copy, ExternalLink,
  FileText, FlaskConical, Globe, Inbox, Info, Lock, MoreHorizontal, Pencil, Plus, Save, ShieldCheck, Trash2,
} from "lucide-react";
import { describeLeadStep } from "@/lib/leadSteps";
import { agoLabel, fullDateLabel } from "@/lib/contactHistory";

const cx = (...parts) => parts.filter(Boolean).join(" ");
const clone = (value) => JSON.parse(JSON.stringify(value));
const slug = (text) => text.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);
const lines = (text) => text.split(/\n|,/).map((item) => item.trim()).filter(Boolean);

/** Contrast of the embed's white button text on a #rrggbb colour (WCAG ratio), or null. */
function whiteTextContrast(hex) {
  const match = /^#([0-9a-f]{6})$/i.exec(hex || "");
  if (!match) return null;
  const n = parseInt(match[1], 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
  return 1.05 / (0.2126 * r + 0.7152 * g + 0.0722 * b + 0.05);
}

/* ------------------------------------------------------------------ local primitives */

const NOTICE_TONE = {
  neutral: "border-border bg-muted/40 text-foreground/80",
  warning: "border-amber-200 bg-amber-50 text-amber-700",
  success: "border-emerald-200 bg-emerald-50 text-emerald-700",
};

/** A thin, soft alert: small icon, one or two lines. */
function Notice({ tone = "neutral", icon: Icon = Info, children, className, role }) {
  return (
    <div role={role} className={cx("flex items-start gap-2 rounded-lg border px-3 py-2 text-[13px] leading-5", NOTICE_TONE[tone], className)}>
      <Icon className="mt-[3px] size-3.5 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

/** A label with an optional muted line under the control: for inputs that need the full width. */
function Field({ id, label, hint, children, className }) {
  return (
    <div className={cx("space-y-1.5", className)}>
      <Label htmlFor={id} className="block text-[13px] font-medium leading-5 text-foreground">{label}</Label>
      {children}
      {hint && <p className="text-xs leading-5 text-muted-foreground">{hint}</p>}
    </div>
  );
}

/** A settings row: label and a muted line on the left, the control on the right. */
function Row({ id, label, hint, children, wide }) {
  return (
    <div className="flex flex-col gap-2 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <div className="min-w-0">
        <Label htmlFor={id} className="block text-[13px] font-medium leading-5 text-foreground">{label}</Label>
        {hint && <p className="text-xs leading-5 text-muted-foreground">{hint}</p>}
      </div>
      <div className={cx("w-full shrink-0", wide ? "sm:w-80" : "sm:w-60")}>{children}</div>
    </div>
  );
}

/** A settings row whose control is an on/off switch. */
function ToggleRow({ id, label, hint, checked, onChange, disabled }) {
  return (
    <div className="flex items-start justify-between gap-4 px-4 py-3.5">
      <div className="min-w-0">
        <Label htmlFor={id} className="block text-[13px] font-medium leading-5 text-foreground">{label}</Label>
        {hint && <p className="text-xs leading-5 text-muted-foreground">{hint}</p>}
      </div>
      <Switch id={id} checked={Boolean(checked)} onCheckedChange={onChange} disabled={disabled} className="mt-0.5" />
    </div>
  );
}

/** Footer line of a card: muted, for context that applies to the whole block. */
function CardNote({ children }) {
  return <div className="rounded-b-xl border-t border-border bg-muted/30 px-4 py-2.5 text-xs leading-5 text-muted-foreground">{children}</div>;
}

/** Code in a quiet block with a copy icon button. */
function CodeBlock({ title, code, className }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(code);
    toast.success(`${title} copied`);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className={cx("relative rounded-lg bg-muted", className)}>
      <pre className="whitespace-pre-wrap break-all py-2.5 pl-3 pr-11 font-mono text-xs leading-5 text-foreground/80">{code}</pre>
      <Button type="button" size="icon" variant="ghost" onClick={copy} aria-label={`Copy ${title}`}
        className="absolute right-1.5 top-1.5 size-7 text-muted-foreground hover:bg-background hover:text-foreground [&_svg]:size-3.5">
        {copied ? <Check /> : <Copy />}
      </Button>
    </div>
  );
}

/* ------------------------------------------------------------------ previews */

function PreviewField({ field, base, consent }) {
  const type = field.type || base?.type || "text";
  let label = field.label || base?.label || field.key;
  if (field.key === "consent_sms" && consent?.sms_text) label = consent.sms_text;
  if (field.key === "consent_email" && consent?.email_text) label = consent.email_text;
  const required = field.required ? <span className="text-red-600"> *</span> : null;
  const conditional = field.show_if ? <span className="ml-1 font-normal text-muted-foreground">· conditional</span> : null;
  if (type === "checkbox") {
    return (
      <div className="flex items-start gap-2 text-[11.5px] leading-4 text-foreground/80">
        <span className="mt-px size-3.5 shrink-0 rounded-[4px] border border-input bg-card" />
        <span className="line-clamp-4">{label}{required}{conditional}</span>
      </div>
    );
  }
  const placeholder = type === "select" ? "Select…" : field.placeholder || "";
  return (
    <div className="min-w-0 space-y-1">
      <div className="truncate text-xs font-medium text-foreground">{label}{required}{conditional}</div>
      <div className={cx("flex items-center justify-between rounded-md border border-input bg-card px-2.5 text-xs text-muted-foreground", type === "textarea" ? "h-14 items-start pt-1.5" : "h-8")}>
        <span className="truncate">{placeholder}</span>
        {type === "select" && <ChevronDown className="size-3.5 shrink-0" aria-hidden="true" />}
      </div>
    </div>
  );
}

/** What a visitor sees, built from the unsaved draft so it follows every edit. */
function FormPreview({ draft, catalog }) {
  const [step, setStep] = useState(1);
  const byKey = useMemo(() => Object.fromEntries(catalog.fields.map((field) => [field.key, field])), [catalog]);
  const s = draft.settings;
  const steps = Math.max(1, ...draft.fields.map((field) => field.step || 1));
  const current = Math.min(step, steps);
  const fields = draft.fields.filter((field) => Math.min(steps, Math.max(1, field.step || 1)) === current);
  const color = /^#[0-9a-f]{6}$/i.test(s.theme?.primary_color || "") ? s.theme.primary_color : null;
  const pager = steps > 1 && (
    <div className="flex items-center gap-1">
      <Button type="button" size="icon" variant="ghost" className="size-7" disabled={current === 1} onClick={() => setStep(current - 1)} aria-label="Previous step"><ChevronLeft /></Button>
      <span className="tabular text-xs text-muted-foreground">{current}/{steps}</span>
      <Button type="button" size="icon" variant="ghost" className="size-7" disabled={current === steps} onClick={() => setStep(current + 1)} aria-label="Next step"><ChevronRight /></Button>
    </div>
  );
  return (
    <Section card title="Preview" actions={pager} bodyClassName="p-3" testid="website-form-preview">
      <div className="rounded-lg bg-muted/50 p-3">
        <div className="rounded-lg border border-border bg-card p-4 shadow-xs" aria-hidden="true">
          {steps > 1 && <div className="mb-3 text-xs font-medium text-muted-foreground">Step {current} of {steps}</div>}
          <div className={cx("grid gap-3", s.theme?.layout === "two_column" && "grid-cols-2")}>
            {fields.map((field) => <PreviewField key={field.key} field={field} base={byKey[field.key]} consent={s.consent} />)}
          </div>
          {fields.length === 0 && <p className="text-xs text-muted-foreground">No fields on this step.</p>}
          <div className="mt-4 flex gap-2">
            {current > 1 && <span className="rounded-md border border-input px-3 py-2 text-xs font-medium text-foreground">Back</span>}
            <span className={cx("flex-1 truncate rounded-md px-3 py-2 text-center text-xs font-semibold", !color && "bg-primary text-primary-foreground")}
              style={color ? { backgroundColor: color, color: "white" } : undefined}>
              {current < steps ? "Next" : s.submit_text || "Submit"}
            </span>
          </div>
        </div>
      </div>
      <p className="mt-2.5 px-1 text-xs leading-5 text-muted-foreground">
        After submitting: {s.redirect_url
          ? <>redirects to <span className="break-all font-mono text-foreground/80">{s.redirect_url}</span></>
          : <>shows “{s.success_message}”</>}
      </p>
    </Section>
  );
}

/** Merge fields in the reply stand out so it is clear what gets filled in. */
function withMergeFields(text) {
  return String(text || "").split(/(\{[a-z_]+\})/g).map((part, index) => (/^\{[a-z_]+\}$/.test(part)
    ? <span key={index} className="rounded bg-brand-soft px-1 font-mono text-[12px] text-brand-strong">{part}</span>
    : part));
}

function ReplyPreview({ reply }) {
  return (
    <Section card title="Email preview" actions={!reply.enabled && <span className="text-xs text-muted-foreground">Off</span>} bodyClassName="p-3">
      <div className="rounded-lg border border-border bg-background">
        <div className="border-b border-border px-3 py-2 text-xs">
          <span className="text-muted-foreground">Subject </span>
          <span className="font-medium text-foreground">{withMergeFields(reply.subject)}</span>
        </div>
        <div className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words px-3 py-3 text-[13px] leading-6 text-foreground/90">{withMergeFields(reply.body)}</div>
      </div>
    </Section>
  );
}

/* ------------------------------------------------------------------ editor sections */

function FieldsTab({ draft, setDraft, catalog, readOnly }) {
  const [custom, setCustom] = useState({ label: "", type: "text", options: "" });
  const used = new Set(draft.fields.map((field) => field.key));
  const available = catalog.fields.filter((field) => !used.has(field.key));
  const byKey = Object.fromEntries(catalog.fields.map((field) => [field.key, field]));
  const update = (index, patch) => setDraft((current) => { const next = clone(current); next.fields[index] = { ...next.fields[index], ...patch }; return next; });
  const move = (index, delta) => setDraft((current) => {
    const next = clone(current); const target = index + delta;
    if (target < 0 || target >= next.fields.length) return current;
    [next.fields[index], next.fields[target]] = [next.fields[target], next.fields[index]];
    return next;
  });
  const remove = (index) => setDraft((current) => { const next = clone(current); next.fields.splice(index, 1); return next; });
  const add = (key) => setDraft((current) => ({ ...current, fields: [...current.fields, { key, required: false }] }));
  const addCustom = () => {
    const key = `custom_${slug(custom.label)}`;
    if (!custom.label.trim() || key === "custom_") { toast.error("Give the custom field a name"); return; }
    if (used.has(key)) { toast.error("A field with that name already exists"); return; }
    setDraft((current) => ({ ...current, fields: [...current.fields, { key, label: custom.label.trim(), type: custom.type, required: false, options: custom.type === "select" ? lines(custom.options) : null }] }));
    setCustom({ label: "", type: "text", options: "" });
  };
  return (
    <div className="space-y-3">
      <Section card title="Fields" description="What the form asks, in order."
        actions={<span className="tabular text-xs text-muted-foreground">{draft.fields.length} fields</span>}>
        <ul className="divide-y divide-border/70">
          {draft.fields.map((field, index) => {
            const base = byKey[field.key];
            const label = field.label || base?.label || field.key;
            // A field can depend on any choice-type field above it.
            const sources = draft.fields.slice(0, index).filter((candidate) => {
              const type = candidate.type || byKey[candidate.key]?.type;
              return type === "select" || type === "checkbox";
            });
            const source = field.show_if && draft.fields.find((candidate) => candidate.key === field.show_if.field);
            const sourceType = source && (source.type || byKey[source.key]?.type);
            const sourceOptions = sourceType === "checkbox" ? ["Yes", "No"] : (source?.options || byKey[source?.key]?.options || []);
            const toggleValue = (value) => {
              const values = new Set(field.show_if?.values || []);
              if (values.has(value)) values.delete(value); else values.add(value);
              update(index, { show_if: { field: field.show_if.field, values: [...values] } });
            };
            return (
              <li key={field.key} className="px-3 py-2.5 transition-colors hover:bg-muted/30">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                  <div className="flex shrink-0 flex-col">
                    <Button size="icon" variant="ghost" className="size-6 text-muted-foreground [&_svg]:size-3.5" disabled={readOnly || index === 0} onClick={() => move(index, -1)} aria-label="Move up"><ChevronUp /></Button>
                    <Button size="icon" variant="ghost" className="size-6 text-muted-foreground [&_svg]:size-3.5" disabled={readOnly || index === draft.fields.length - 1} onClick={() => move(index, 1)} aria-label="Move down"><ChevronDown /></Button>
                  </div>
                  <div className="min-w-0 flex-1 basis-48">
                    <Input value={field.label ?? ""} placeholder={base?.label || field.key} disabled={readOnly} aria-label={`${label} label`}
                      onChange={(event) => update(index, { label: event.target.value })} className="h-8 text-[13px] md:text-[13px]" />
                    <div className="mt-1 truncate text-[11px] text-muted-foreground"><span className="font-mono">{field.key}</span> · {field.type || base?.type || "text"}</div>
                  </div>
                  <div className="ml-auto flex items-center gap-4 self-start pt-0.5">
                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      Step
                      <Select value={String(field.step || 1)} onValueChange={(value) => update(index, { step: Number(value) })} disabled={readOnly}>
                        <SelectTrigger className="h-7 w-14 px-2 text-xs" aria-label={`${label} step`}><SelectValue /></SelectTrigger>
                        <SelectContent>{[1, 2, 3, 4, 5].map((n) => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">Required<Switch aria-label={`${label} is required`} checked={Boolean(field.required)} disabled={readOnly} onCheckedChange={(value) => update(index, { required: value })} /></div>
                    <Button size="icon" variant="ghost" className="size-7 text-muted-foreground hover:bg-red-50 hover:text-red-700 [&_svg]:size-3.5" disabled={readOnly} onClick={() => remove(index)} aria-label="Remove field"><Trash2 /></Button>
                  </div>
                </div>
                {(sources.length > 0 || field.show_if) && (
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground sm:pl-9">
                    <span>Show</span>
                    <Select value={field.show_if?.field || "always"} disabled={readOnly}
                      onValueChange={(value) => update(index, { show_if: value === "always" ? null : { field: value, values: [] } })}>
                      <SelectTrigger className="h-7 w-auto max-w-full gap-2 px-2 text-xs sm:max-w-64" aria-label={`When to show ${label}`}><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="always">Always</SelectItem>
                        {sources.map((candidate) => <SelectItem key={candidate.key} value={candidate.key}>Only when “{candidate.label || byKey[candidate.key]?.label || candidate.key}” is…</SelectItem>)}
                      </SelectContent>
                    </Select>
                    {field.show_if && sourceOptions.map((option) => (
                      <label key={option} className="inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-md border border-border bg-card px-2 text-xs text-foreground/80 transition-colors has-[:checked]:border-brand/40 has-[:checked]:bg-brand-soft has-[:checked]:text-brand-strong">
                        <input type="checkbox" className="size-3.5 accent-primary" checked={(field.show_if.values || []).includes(option)} disabled={readOnly} onChange={() => toggleValue(option)} />{option}
                      </label>
                    ))}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
        {!readOnly && (
          <div className="grid gap-4 rounded-b-xl border-t border-border bg-muted/30 px-4 py-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
            <Field id="wf-add-field" label="Add a real-estate field">
              <Select value="" onValueChange={add}>
                <SelectTrigger id="wf-add-field" className="h-9 bg-card" aria-label="Add a real-estate field"><SelectValue placeholder="Choose a field…" /></SelectTrigger>
                <SelectContent>{available.map((field) => <SelectItem key={field.key} value={field.key}>{field.label}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field id="wf-custom-label" label="Add a custom field" hint="For anything else you want to ask. Options are comma separated for a dropdown.">
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input id="wf-custom-label" value={custom.label} onChange={(event) => setCustom({ ...custom, label: event.target.value })} placeholder="e.g. Move-in date" className="h-9" />
                <Select value={custom.type} onValueChange={(type) => setCustom({ ...custom, type })}>
                  <SelectTrigger className="h-9 bg-card sm:w-32" aria-label="Custom field type"><SelectValue /></SelectTrigger>
                  <SelectContent>{catalog.custom_field_types.map((type) => <SelectItem key={type} value={type}>{type}</SelectItem>)}</SelectContent>
                </Select>
                <Button variant="outline" className="h-9" onClick={addCustom}><Plus />Add</Button>
              </div>
              {custom.type === "select" && <Input value={custom.options} aria-label="Dropdown options" onChange={(event) => setCustom({ ...custom, options: event.target.value })} placeholder="Option A, Option B" className="mt-2 h-9" />}
            </Field>
          </div>
        )}
      </Section>
      <p className="flex items-start gap-1.5 px-1 text-xs leading-5 text-muted-foreground">
        <Info className="mt-[3px] size-3.5 shrink-0" aria-hidden="true" />
        <span>Real-estate fields are captured as structured data on the lead, the contact and the deal. Always captured as well, without adding fields: page URL, referrer, landing page, UTM tags, gclid and fbclid, and the listing a page is about.</span>
      </p>
    </div>
  );
}

function SettingsTab({ draft, setDraft, readOnly, captchaSecret, setCaptchaSecret }) {
  const s = draft.settings;
  const set = (patch) => setDraft((current) => ({ ...current, settings: { ...current.settings, ...patch } }));
  const setIn = (group, patch) => setDraft((current) => ({ ...current, settings: { ...current.settings, [group]: { ...current.settings[group], ...patch } } }));
  const contrast = whiteTextContrast(s.theme.primary_color);
  return (
    <div className="space-y-5">
      <Section card title="Form" description="Name, availability and what the visitor sees." bodyClassName="divide-y divide-border/70">
        <Field id="wf-name" label="Form name" className="px-4 py-3.5">
          <Input id="wf-name" value={draft.name} disabled={readOnly} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
        </Field>
        <Row id="wf-status" label="Status" hint="A paused form stops accepting submissions; its embed shows it as unavailable.">
          <Select value={draft.status} onValueChange={(status) => setDraft({ ...draft, status })} disabled={readOnly}>
            <SelectTrigger id="wf-status" aria-label="Status"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="active">Active</SelectItem><SelectItem value="paused">Paused</SelectItem></SelectContent>
          </Select>
        </Row>
        <Row id="wf-submit-text" label="Button text">
          <Input id="wf-submit-text" value={s.submit_text} disabled={readOnly} onChange={(event) => set({ submit_text: event.target.value })} />
        </Row>
        <Row id="wf-color" label="Button colour" hint={contrast !== null && contrast < 4.5 ? `Button text is white: ${contrast.toFixed(1)}:1 contrast on this colour. 4.5:1 or more is easiest to read.` : null}>
          <div className="flex items-center gap-2">
            <Input id="wf-color" type="color" value={s.theme.primary_color} disabled={readOnly} onChange={(event) => setIn("theme", { primary_color: event.target.value })} className="h-9 w-14 shrink-0 cursor-pointer p-1" />
            <span className="font-mono text-xs uppercase text-muted-foreground">{s.theme.primary_color}</span>
          </div>
        </Row>
        <Row id="wf-layout" label="Layout">
          <Select value={s.theme.layout} onValueChange={(layout) => setIn("theme", { layout })} disabled={readOnly}>
            <SelectTrigger id="wf-layout" aria-label="Layout"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="stacked">One column</SelectItem><SelectItem value="two_column">Two columns</SelectItem></SelectContent>
          </Select>
        </Row>
        <Field id="wf-success" label="Thank-you message" className="px-4 py-3.5">
          <Textarea id="wf-success" value={s.success_message} disabled={readOnly} onChange={(event) => set({ success_message: event.target.value })} rows={3} />
        </Field>
        <Field id="wf-redirect" label="Or redirect to a thank-you page" hint="Leave empty to show the message above. Use your own thank-you page to fire ad-conversion pixels." className="px-4 py-3.5">
          <Input id="wf-redirect" value={s.redirect_url || ""} disabled={readOnly} placeholder="https://www.yoursite.com/thank-you" onChange={(event) => set({ redirect_url: event.target.value || null })} />
        </Field>
      </Section>

      <Section card title="Data handling" description="Where leads may come from, and how they join your records." bodyClassName="divide-y divide-border/70">
        <Field id="wf-origins" label="Allowed websites" hint="One per line, e.g. https://www.yoursite.com. Browsers on other sites are refused. Leave empty to allow any site. Zapier and server-side posts are always allowed." className="px-4 py-3.5">
          <Textarea id="wf-origins" value={(s.allowed_origins || []).join("\n")} disabled={readOnly} rows={3} onChange={(event) => set({ allowed_origins: lines(event.target.value) })} />
        </Field>
        <Field id="wf-duplicates" label="When the person is already in the CRM" className="px-4 py-3.5">
          <Select value={s.duplicate_policy} onValueChange={(duplicate_policy) => set({ duplicate_policy })} disabled={readOnly}>
            <SelectTrigger id="wf-duplicates" aria-label="When the person is already in the CRM"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="update_existing">Update the existing contact (match on email or phone)</SelectItem>
              <SelectItem value="always_new">Always create a new contact</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field id="wf-tags" label="Tags added to the contact" hint="Comma separated." className="px-4 py-3.5">
          <Input id="wf-tags" value={(s.tags || []).join(", ")} disabled={readOnly} onChange={(event) => set({ tags: lines(event.target.value) })} />
        </Field>
        <Field id="wf-consent-sms" label="Text-message consent wording" hint="Shown next to the consent checkbox and stored with the lead as evidence." className="px-4 py-3.5">
          <Textarea id="wf-consent-sms" value={s.consent.sms_text} disabled={readOnly} rows={3} onChange={(event) => setIn("consent", { sms_text: event.target.value })} />
        </Field>
        <Field id="wf-consent-email" label="Email consent wording" className="px-4 py-3.5">
          <Textarea id="wf-consent-email" value={s.consent.email_text} disabled={readOnly} rows={2} onChange={(event) => setIn("consent", { email_text: event.target.value })} />
        </Field>
        <ToggleRow id="wf-remember" label="Remember returning visitors" hint="Pre-fills name, email and phone for someone who already submitted a form on your site (stored in their browser). Leave off for open-house kiosks and shared computers." checked={s.remember_visitor} disabled={readOnly} onChange={(value) => set({ remember_visitor: value })} />
      </Section>

      <Section card title="Spam protection" description="Built in on every form: a hidden trap field, a minimum fill time and rate limits." bodyClassName="divide-y divide-border/70">
        <Row id="wf-captcha" label="CAPTCHA" hint="Add Cloudflare Turnstile for a visible challenge.">
          <Select value={s.captcha.provider} onValueChange={(provider) => setIn("captcha", { provider })} disabled={readOnly}>
            <SelectTrigger id="wf-captcha" aria-label="CAPTCHA"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="none">Built-in protection only</SelectItem><SelectItem value="turnstile">Cloudflare Turnstile</SelectItem></SelectContent>
          </Select>
        </Row>
        {s.captcha.provider === "turnstile" && (
          <div className="space-y-4 px-4 py-3.5">
            <Field id="wf-turnstile-site" label="Turnstile site key" hint="From the Cloudflare dashboard → Turnstile. Add your website's domain to the widget there.">
              <Input id="wf-turnstile-site" value={s.captcha.site_key || ""} disabled={readOnly} onChange={(event) => setIn("captcha", { site_key: event.target.value })} />
            </Field>
            <Field id="wf-turnstile-secret" label="Turnstile secret key" hint={s.captcha.secret_configured ? "A secret is saved (encrypted). Enter a new one only to replace it." : "Stored encrypted and never shown again."}>
              <Input id="wf-turnstile-secret" type="password" autoComplete="off" value={captchaSecret} disabled={readOnly} placeholder={s.captcha.secret_configured ? "•••••••• saved" : ""} onChange={(event) => setCaptchaSecret(event.target.value)} />
            </Field>
            <Notice tone="warning">A CAPTCHA form only accepts browser submissions. Use a separate form for Zapier or a form plugin's webhook.</Notice>
          </div>
        )}
      </Section>
    </div>
  );
}

function AutomationTab({ draft, setDraft, members, stages, readOnly }) {
  const s = draft.settings;
  const setIn = (group, patch) => setDraft((current) => ({ ...current, settings: { ...current.settings, [group]: { ...current.settings[group], ...patch } } }));
  const toggleAgent = (email) => {
    const users = new Set(s.assignment.users);
    if (users.has(email)) users.delete(email); else users.add(email);
    setIn("assignment", { users: [...users] });
  };
  const openStages = stages.filter((stage) => !stage.is_closed);
  return (
    <div className="space-y-5">
      <Section card title="Assign the lead" description="Who owns each new lead. Their call-back task and alerts go to them." bodyClassName="divide-y divide-border/70">
        <Row id="wf-assignment" label="Assignment" wide>
          <Select value={s.assignment.mode} onValueChange={(mode) => setIn("assignment", { mode })} disabled={readOnly}>
            <SelectTrigger id="wf-assignment" aria-label="Assignment"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="unassigned">Unassigned — alert every admin</SelectItem>
              <SelectItem value="specific">A specific agent</SelectItem>
              <SelectItem value="round_robin">Round-robin across agents</SelectItem>
            </SelectContent>
          </Select>
        </Row>
        {s.assignment.mode !== "unassigned" && (
          <div className="space-y-1.5 px-4 py-3.5">
            <div className="text-[13px] font-medium leading-5 text-foreground">{s.assignment.mode === "specific" ? "Agent (the first one ticked)" : "Agents in the rotation"}</div>
            <div className="max-h-56 divide-y divide-border/70 overflow-auto rounded-lg border border-border">
              {members.length === 0 && <p className="px-3 py-2.5 text-xs text-muted-foreground">Team members are visible to admins only.</p>}
              {members.filter((member) => member.status === "active").map((member) => (
                <div key={member.email} className="flex items-center justify-between gap-2 px-3 py-2 text-[13px] transition-colors hover:bg-muted/50">
                  <label className="flex min-w-0 cursor-pointer items-center gap-2.5">
                    <input type="checkbox" className="size-3.5 shrink-0 accent-primary" checked={s.assignment.users.includes(member.email)} disabled={readOnly} onChange={() => toggleAgent(member.email)} />
                    <Avatar name={member.name || member.email} size="sm" />
                    <span className="truncate text-foreground">{member.name || member.email}</span>
                    <span className="hidden truncate text-xs text-muted-foreground sm:inline">{member.email}</span>
                  </label>
                  {s.assignment.mode === "round_robin" && s.assignment.users.includes(member.email) && (
                    <Select value={String(s.assignment.weights?.[member.email] || 1)} disabled={readOnly}
                      onValueChange={(value) => setIn("assignment", { weights: { ...(s.assignment.weights || {}), [member.email]: Number(value) } })}>
                      <SelectTrigger className="h-7 w-24 shrink-0 px-2 text-xs" aria-label={`${member.email} share of leads`}><SelectValue /></SelectTrigger>
                      <SelectContent>{[1, 2, 3, 4, 5].map((n) => <SelectItem key={n} value={String(n)}>{n}× share</SelectItem>)}</SelectContent>
                    </Select>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        <ToggleRow id="wf-keep-owner" label="Keep the existing owner" hint="A returning contact stays with the agent who already owns them." checked={s.assignment.keep_existing_owner} disabled={readOnly} onChange={(value) => setIn("assignment", { keep_existing_owner: value })} />
      </Section>

      <Section card title="Speed to lead" description="Leads contacted within five minutes convert far more often." bodyClassName="divide-y divide-border/70">
        <ToggleRow id="wf-task" label="Create a call-back task" checked={s.speed_to_lead.task_enabled} disabled={readOnly} onChange={(value) => setIn("speed_to_lead", { task_enabled: value })} />
        <Row id="wf-due" label="Call within">
          <div className="flex items-center gap-2 sm:justify-end">
            <Input id="wf-due" type="number" min={1} aria-label="Call within (minutes)" value={s.speed_to_lead.due_minutes} disabled={readOnly} onChange={(event) => setIn("speed_to_lead", { due_minutes: Number(event.target.value) })} className="tabular h-9 w-24" />
            <span className="w-14 text-xs text-muted-foreground">minutes</span>
          </div>
        </Row>
        <Row id="wf-escalate" label="Escalate after" hint="Admins and the agent are alerted if nobody has responded.">
          <div className="flex items-center gap-2 sm:justify-end">
            <Input id="wf-escalate" type="number" min={1} aria-label="Escalate after (minutes)" value={s.speed_to_lead.escalate_after_minutes} disabled={readOnly} onChange={(event) => setIn("speed_to_lead", { escalate_after_minutes: Number(event.target.value) })} className="tabular h-9 w-24" />
            <span className="w-14 text-xs text-muted-foreground">minutes</span>
          </div>
        </Row>
        <ToggleRow id="wf-in-app" label="In-app alert" checked={s.notify.in_app} disabled={readOnly} onChange={(value) => setIn("notify", { in_app: value })} />
        <ToggleRow id="wf-email-alert" label="Email alert" hint="Sent when email delivery is configured for this CRM." checked={s.notify.email} disabled={readOnly} onChange={(value) => setIn("notify", { email: value })} />
        <CardNote>Need a text alert or a Slack ping? Add a webhook for the <code className="rounded bg-muted px-1 font-mono text-[11px] text-foreground/80">lead.received</code> event under Registries → Webhooks; it carries the full lead.</CardNote>
      </Section>

      <Section card title="Pipeline" description="Open a deal for each new lead so it shows in your pipeline and lost-revenue tracking." bodyClassName="divide-y divide-border/70">
        <ToggleRow id="wf-deal" label="Create a deal" hint="A returning lead with an open deal from this form within 30 days is linked to it, not doubled." checked={s.opportunity.enabled} disabled={readOnly} onChange={(value) => setIn("opportunity", { enabled: value })} />
        {s.opportunity.enabled && (
          <>
            <Row id="wf-stage" label="Stage">
              <Select value={s.opportunity.stage || openStages[0]?.key || ""} onValueChange={(stage) => setIn("opportunity", { stage })} disabled={readOnly}>
                <SelectTrigger id="wf-stage" aria-label="Stage"><SelectValue placeholder="First stage" /></SelectTrigger>
                <SelectContent>{openStages.map((stage) => <SelectItem key={stage.key} value={stage.key}>{stage.label}</SelectItem>)}</SelectContent>
              </Select>
            </Row>
            <Row id="wf-value-mode" label="Deal value" hint="Expected commission uses the price the visitor gives (max price, home value or min price) × your commission rate, and falls back to the flat value when there's no realistic price.">
              <Select value={s.opportunity.value_mode} onValueChange={(value_mode) => setIn("opportunity", { value_mode })} disabled={readOnly}>
                <SelectTrigger id="wf-value-mode" aria-label="Deal value"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="commission">Expected commission (GCI)</SelectItem><SelectItem value="fixed">Flat value</SelectItem></SelectContent>
              </Select>
            </Row>
            <div className="grid gap-4 px-4 py-3.5 sm:grid-cols-3">
              {s.opportunity.value_mode === "commission" && (
                <Field id="wf-commission" label="Commission %">
                  <Input id="wf-commission" type="number" step="0.1" min={0} value={s.opportunity.commission_rate} disabled={readOnly} onChange={(event) => setIn("opportunity", { commission_rate: Number(event.target.value) })} className="tabular" />
                </Field>
              )}
              <Field id="wf-fixed" label={s.opportunity.value_mode === "commission" ? "Fallback value" : "Value"}>
                <Input id="wf-fixed" type="number" min={0} value={s.opportunity.fixed_value} disabled={readOnly} onChange={(event) => setIn("opportunity", { fixed_value: Number(event.target.value) })} className="tabular" />
              </Field>
              <Field id="wf-currency" label="Currency">
                <Input id="wf-currency" value={s.opportunity.currency} maxLength={3} disabled={readOnly} onChange={(event) => setIn("opportunity", { currency: event.target.value.toUpperCase() })} className="uppercase" />
              </Field>
            </div>
          </>
        )}
      </Section>
    </div>
  );
}

function ReplyTab({ form, draft, setDraft, catalog, readOnly, isAdmin, onApproved }) {
  const reply = draft.settings.auto_reply;
  const setReply = (patch) => setDraft((current) => ({ ...current, settings: { ...current.settings, auto_reply: { ...current.settings.auto_reply, ...patch } } }));
  const state = form.auto_reply_state?.state;
  const changed = reply.subject !== form.settings.auto_reply.subject || reply.body !== form.settings.auto_reply.body || reply.enabled !== form.settings.auto_reply.enabled;
  const approve = async () => {
    try {
      await api.post(`/approval-queue/${form.auto_reply_state.approval_id}/decision`, { decision: "approved", rationale: "Automatic reply wording approved in Website forms" });
      toast.success("Automatic reply approved — it now goes to every new lead");
      onApproved();
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  };
  return (
    <div className="space-y-5">
      <Section card title="Automatic reply to the lead" description="Sent within seconds to every new lead who leaves an email." bodyClassName="divide-y divide-border/70">
        <ToggleRow id="wf-reply-enabled" label="Send an automatic reply" checked={reply.enabled} disabled={readOnly} onChange={(value) => setReply({ enabled: value })} />
        <Field id="wf-reply-subject" label="Subject" className="px-4 py-3.5">
          <Input id="wf-reply-subject" value={reply.subject} disabled={readOnly} onChange={(event) => setReply({ subject: event.target.value })} />
        </Field>
        <div className="space-y-1.5 px-4 py-3.5">
          <Label htmlFor="wf-reply-body" className="block text-[13px] font-medium leading-5 text-foreground">Message</Label>
          <Textarea id="wf-reply-body" value={reply.body} disabled={readOnly} rows={8} onChange={(event) => setReply({ body: event.target.value })} />
          <div className="flex flex-wrap items-center gap-1.5 pt-0.5 text-xs leading-5 text-muted-foreground">
            <span>Merge fields:</span>
            {catalog.merge_fields.map((key) => <code key={key} className="rounded bg-muted px-1.5 font-mono text-[11px] text-foreground/80">{`{${key}}`}</code>)}
            <span>Nothing else is filled in.</span>
          </div>
        </div>
      </Section>
      <Section card title="Approval" description="You approve the exact wording once; each reply is then sent from that approved template.">
        <div className="space-y-3 px-4 py-3.5">
          {!reply.enabled ? <Notice icon={Info}>Turned off. Leads are still contacted by your call-back task.</Notice>
            : changed ? <Notice tone="warning" icon={Clock}>Save your changes to submit this wording for approval.</Notice>
            : state === "approved" ? <Notice tone="success" icon={CheckCircle2}>Approved — replies are going out.</Notice>
            : (
              <>
                <Notice tone="warning" icon={Clock}>Waiting for approval. No reply is sent until this exact wording is approved; editing it later needs a new approval.</Notice>
                <div className="flex flex-wrap items-center gap-3">
                  {isAdmin && form.auto_reply_state?.approval_id && <Button size="sm" onClick={approve}><ShieldCheck />Approve this wording</Button>}
                  <span className="text-xs text-muted-foreground">Also listed under <Link className="font-medium text-brand hover:underline" to="/operations?tab=approvals">Operations → Approvals</Link>.</span>
                </div>
              </>
            )}
        </div>
        <CardNote>Replies are sent from your connected Gmail account. If Gmail isn't connected, each lead shows the reply as blocked with the reason, and nothing is lost.</CardNote>
      </Section>
    </div>
  );
}

function ServerConnection({ form, isAdmin, onChanged }) {
  const [minted, setMinted] = useState(null);
  const [busy, setBusy] = useState(false);
  const status = form.server_key || {};
  const mint = async () => {
    if (status.configured && !window.confirm("Create a new key? The current key stops working immediately, so update your website's settings right after.")) return;
    setBusy(true);
    try { const { data } = await api.post(`/website-forms/${form.id}/server-key`); setMinted(data); onChanged(); }
    catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  const revoke = async () => {
    if (!window.confirm("Revoke the server key? Your website's server will stop delivering leads to this form until it has a new key.")) return;
    setBusy(true);
    try { await api.delete(`/website-forms/${form.id}/server-key`); setMinted(null); toast.success("Server key revoked"); onChanged(); }
    catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  const settings = minted ? `CRM_PROVIDER=clientverse\nCLIENTVERSE_INTAKE_URL=${minted.intake_url}\nCLIENTVERSE_API_KEY=${minted.key}` : "";
  return (
    <Section card title="Server connection" description="Recommended for custom-built websites with their own form backend.">
      <div className="space-y-3 px-4 py-3.5">
        <p className="text-[13px] leading-5 text-muted-foreground">For a Next.js or custom site, or a form plugin that posts from the server. The website keeps its own form design, saves each lead first and delivers it here with this key, retrying until it is accepted — nothing is lost if either side is briefly down.</p>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {status.configured
              ? <StatusDot tone="success">Key active (ends …{status.hint})</StatusDot>
              : <StatusDot>No server key yet</StatusDot>}
            {status.last_used_at && <span className="text-xs text-muted-foreground">Last lead received {new Date(status.last_used_at).toLocaleString()}</span>}
          </div>
          {isAdmin && (
            <div className="flex flex-wrap gap-2">
              {status.configured && <Button size="sm" variant="outline" className="text-red-700 hover:text-red-700" onClick={revoke} disabled={busy}>Revoke</Button>}
              <Button size="sm" variant="outline" onClick={mint} disabled={busy}><ShieldCheck />{status.configured ? "Replace key" : "Create server key"}</Button>
            </div>
          )}
        </div>
        {minted && (
          <div className="space-y-2 pt-1">
            <Notice tone="warning" icon={Lock}><span className="font-medium">Copy these now — the key is shown only once.</span></Notice>
            <div className="text-[13px] font-medium text-foreground">Website environment variables</div>
            <p className="text-xs leading-5 text-muted-foreground">Add to the website's hosting settings (Vercel → Project → Settings → Environment Variables), then redeploy the website.</p>
            <CodeBlock title="Website environment variables" code={settings} />
          </div>
        )}
      </div>
      <CardNote>Leads sent with this key skip browser-only checks (allowed websites, CAPTCHA) because they come from your website's server, and they are filed even if this form marks a field required that your website doesn't collect. They still need an email or a phone number.</CardNote>
    </Section>
  );
}

const embedOptions = (embed) => [
  { key: "inline", nav: "Inline", title: "Inline form", description: "Paste where the form should appear (WordPress Custom HTML block, Squarespace Code block, Webflow Embed, IDX custom HTML).", code: embed.inline },
  { key: "popup", nav: "Pop-up on a button", title: "Pop-up on a button", description: "A button that opens the form in a pop-up.", code: embed.popup },
  { key: "popup_auto", nav: "Pop-up after a delay", title: "Pop-up after a delay", description: "Opens once per visit after 15 seconds. Use data-trigger=\"scroll:50\" for half-way down the page, or \"exit\" for exit intent.", code: embed.popup_auto },
  { key: "slide_in", nav: "Slide-in", title: "Slide-in", description: "A small panel in the corner when the visitor is half-way down the page. Pop-ups never show again to someone who already submitted.", code: embed.slide_in },
  { key: "listing_page", nav: "Listing page", title: "On a listing page", description: "Attaches the listing to every lead from that page. Replace the MLS number and address per listing (most IDX templates have placeholders for these).", code: embed.listing_page },
  { key: "iframe", nav: "iFrame", title: "iFrame", description: "For builders that only allow iframes (Wix, some IDX vendors).", code: embed.iframe },
  { key: "hosted", nav: "Hosted link", title: "Hosted link", description: "Share by text, email, QR code or a social bio link.", code: embed.hosted_url },
  { key: "html_form", nav: "Your own HTML", title: "Your own HTML form", description: "Keep your site's existing form design: point it here and keep the hidden _hp field.", code: embed.html_form },
  { key: "api", nav: "Webhook & Zapier", title: "Zapier, Make or a form plugin's webhook", description: "POST JSON or form data to this URL. Send a unique _sid per submission so retries are never filed twice.", code: `${embed.api.method} ${embed.api.url}\nAccepts: ${embed.api.content_types.join(", ")}\nFields: ${embed.api.fields.join(", ")}` },
];

function EmbedTab({ form, isAdmin, onChanged }) {
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState(null);
  const [kind, setKind] = useState("inline");
  const embed = form.embed;
  const options = embedOptions(embed);
  const active = options.find((option) => option.key === kind) || options[0];
  const runTest = async () => {
    setTesting(true);
    try {
      const { data } = await api.post(`/website-forms/${form.id}/test`, {});
      setResult(data);
      toast.success("Test lead processed end to end");
    } catch (e) { toast.error(formatErr(e.response?.data?.detail?.errors ? Object.values(e.response.data.detail.errors).join(" ") : e.response?.data?.detail)); }
    finally { setTesting(false); }
  };
  return (
    <div className="space-y-5">
      <Section card title="Embed codes" description="Pick how the form appears on your website, then paste the code.">
        <div className="sm:grid sm:grid-cols-[180px_minmax(0,1fr)]">
          <div role="tablist" aria-label="Embed type" aria-orientation="vertical"
            className="flex gap-1 overflow-x-auto border-b border-border p-2 sm:flex-col sm:overflow-visible sm:border-b-0 sm:border-r">
            {options.map((option) => (
              <button key={option.key} type="button" role="tab" aria-selected={option.key === active.key} onClick={() => setKind(option.key)}
                className={cx("shrink-0 rounded-md px-2.5 py-1.5 text-left text-[13px] transition-colors",
                  option.key === active.key ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground")}>
                {option.nav}
              </button>
            ))}
          </div>
          <div role="tabpanel" aria-label={active.title} className="min-w-0 space-y-3 p-4">
            <div>
              <div className="text-[13px] font-medium text-foreground">{active.title}</div>
              <p className="text-xs leading-5 text-muted-foreground">{active.description}</p>
            </div>
            <CodeBlock title={active.title} code={active.code} />
          </div>
        </div>
      </Section>

      <Section card title="Check the whole path" description="Sends a lead marked as a test through the same pipeline a real one takes.">
        <div className="space-y-3 px-4 py-3.5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-[13px] leading-5 text-muted-foreground">Contact, assignment, deal, call-back task and alert. Test leads never count in reporting.</p>
            <div className="flex shrink-0 flex-wrap gap-2">
              <Button size="sm" variant="outline" asChild><a href={embed.hosted_url} target="_blank" rel="noreferrer"><ExternalLink />Open the hosted form</a></Button>
              {isAdmin && <Button size="sm" onClick={runTest} disabled={testing}><FlaskConical />{testing ? "Sending…" : "Send a test lead"}</Button>}
            </div>
          </div>
          {result?.lead && (
            <Notice tone="success" icon={CheckCircle2}>
              <div className="font-medium">Worked end to end.</div>
              <ul className="mt-1.5 space-y-1">
                {(result.lead.automation || []).map((step, index) => (
                  <li key={index} className="flex items-start gap-1.5"><Check className="mt-[3px] size-3.5 shrink-0" aria-hidden="true" /><span>{describeLeadStep(step, { assignee: result.lead.assigned_name })}</span></li>
                ))}
              </ul>
              <Link className="mt-2 inline-block font-medium text-brand hover:underline" to={`/leads?lead=${result.lead.id}`}>Open the test lead</Link>
            </Notice>
          )}
        </div>
      </Section>

      <ServerConnection form={form} isAdmin={isAdmin} onChanged={onChanged} />
    </div>
  );
}

/* ------------------------------------------------------------------ editor */

const EDITOR_TABS = [
  { value: "fields", label: "Fields" },
  { value: "settings", label: "Settings" },
  { value: "automation", label: "Automation" },
  { value: "reply", label: "Auto-reply" },
  { value: "embed", label: "Embed & test" },
];

function FormEditor({ form, catalog, members, stages, isAdmin, onBack, onSaved }) {
  const [draft, setDraft] = useState(() => clone(form));
  const [saving, setSaving] = useState(false);
  const [captchaSecret, setCaptchaSecret] = useState("");
  const [tab, setTab] = useState("fields");
  useEffect(() => { setDraft(clone(form)); }, [form]);
  const dirty = useMemo(() => Boolean(captchaSecret.trim()) || JSON.stringify({ n: draft.name, s: draft.status, f: draft.fields, t: draft.settings }) !== JSON.stringify({ n: form.name, s: form.status, f: form.fields, t: form.settings }), [draft, form, captchaSecret]);
  const readOnly = !isAdmin;
  const save = async () => {
    setSaving(true);
    try {
      const fields = draft.fields.map(({ key, required, label, type, options, placeholder, show_if: showIf, step }) => ({ key, required, label: label || null, type: type || null, options: options || null, placeholder: placeholder || null, show_if: showIf && showIf.values?.length ? showIf : null, step: step || 1 }));
      const unfinished = draft.fields.find((field) => field.show_if && !field.show_if.values?.length);
      if (unfinished) { toast.error(`Choose when "${unfinished.label || unfinished.key}" should show, or set it to Always`); setSaving(false); return; }
      const settings = clone(draft.settings);
      if (captchaSecret.trim()) settings.captcha = { ...settings.captcha, secret: captchaSecret.trim() };
      const { data } = await api.patch(`/website-forms/${form.id}`, { name: draft.name, status: draft.status, fields, settings });
      setCaptchaSecret("");
      toast.success("Form saved");
      onSaved(data);
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };
  const stats = form.stats || {};
  const conversion = stats.views ? ` (${Math.round(((stats.submissions || 0) / stats.views) * 100)}% conversion)` : "";
  const waiting = form.lead_counts?.new || 0;
  const live = form.status === "active";
  const active = EDITOR_TABS.find((item) => item.value === tab) || EDITOR_TABS[0];
  return (
    <div className="cv-page" data-testid="website-form-editor">
      <button type="button" onClick={onBack} className="mb-3 inline-flex items-center gap-1 rounded text-[13px] text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft className="size-3.5" aria-hidden="true" />All forms
      </button>
      <PageHeader
        title={form.name}
        description={<span className="tabular">
          <span className={cx("mr-1.5 inline-block size-1.5 rounded-full align-middle", live ? "bg-emerald-500" : "bg-muted-foreground/50")} aria-hidden="true" />
          <span className="text-foreground/80">{live ? "Live" : "Paused"}</span> · {stats.views || 0} views · {stats.submissions || 0} submissions{conversion} · <span className={waiting ? "text-amber-700" : undefined}>{waiting} waiting for a response</span> · {stats.spam_blocked || 0} spam blocked
        </span>}
        actions={<>
          {isAdmin && dirty && !saving && <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"><span className="size-1.5 rounded-full bg-amber-500" aria-hidden="true" />Unsaved changes</span>}
          {form.embed?.hosted_url && <Button size="sm" variant="outline" asChild><a href={form.embed.hosted_url} target="_blank" rel="noreferrer"><ExternalLink />Open form</a></Button>}
          {isAdmin && <Button size="sm" variant={dirty ? "default" : "outline"} onClick={save} disabled={!dirty || saving}><Save />{saving ? "Saving…" : dirty ? "Save changes" : "Saved"}</Button>}
        </>}
      />
      {!isAdmin && <Notice icon={Lock} className="mb-5">Only workspace admins can change forms. You can copy the embed codes.</Notice>}
      <ViewTabs label="Form editor" value={tab} onChange={setTab} className="mb-5"
        items={EDITOR_TABS.map((item) => ({ ...item, count: item.value === "fields" ? draft.fields.length : undefined, testid: `website-form-tab-${item.value}` }))} />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px] xl:items-start">
        <div role="tabpanel" aria-label={active.label} className="min-w-0">
          {tab === "fields" && <FieldsTab draft={draft} setDraft={setDraft} catalog={catalog} readOnly={readOnly} />}
          {tab === "settings" && <SettingsTab draft={draft} setDraft={setDraft} readOnly={readOnly} captchaSecret={captchaSecret} setCaptchaSecret={setCaptchaSecret} />}
          {tab === "automation" && <AutomationTab draft={draft} setDraft={setDraft} members={members} stages={stages} readOnly={readOnly} />}
          {tab === "reply" && <ReplyTab form={form} draft={draft} setDraft={setDraft} catalog={catalog} readOnly={readOnly} isAdmin={isAdmin} onApproved={() => onSaved(null)} />}
          {tab === "embed" && <EmbedTab form={form} isAdmin={isAdmin} onChanged={() => onSaved(null)} />}
        </div>
        <aside className="min-w-0 space-y-4 xl:sticky xl:top-4" aria-label="Preview">
          {tab === "reply" ? <ReplyPreview reply={draft.settings.auto_reply} /> : <FormPreview draft={draft} catalog={catalog} />}
          {tab !== "embed" && form.embed?.inline && (
            <Section card title="Embed" bodyClassName="p-3"
              actions={<button type="button" onClick={() => setTab("embed")} className="text-xs font-medium text-muted-foreground transition-colors hover:text-foreground">All options</button>}>
              <CodeBlock title="Inline form" code={form.embed.inline} />
            </Section>
          )}
        </aside>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ forms list */

function FormRow({ form, presetLabel, isAdmin, onOpen }) {
  const stats = form.stats || {};
  const waiting = form.lead_counts?.new || 0;
  const live = form.status === "active";
  const last = stats.last_submission_at;
  const copyEmbed = () => { navigator.clipboard?.writeText(form.embed.inline); toast.success("Embed code copied"); };
  return (
    <tr className="relative border-b border-border/70 transition-colors last:border-0 hover:bg-muted/50" data-testid={`website-form-row-${form.id}`}>
      <td className="px-4 py-2.5">
        <button type="button" onClick={onOpen} className="flex w-full min-w-0 items-center gap-3 text-left after:absolute after:inset-0 after:content-['']">
          <span className="hidden size-8 shrink-0 items-center justify-center rounded-lg border border-border bg-muted/50 text-muted-foreground sm:flex"><FileText className="size-4" aria-hidden="true" /></span>
          <span className="min-w-0">
            <span className="block truncate text-[13px] font-medium text-foreground">{form.name}</span>
            <span className="hidden truncate text-xs text-muted-foreground sm:block">{presetLabel} · {form.fields.length} fields</span>
            <span className="block truncate text-xs text-muted-foreground sm:hidden">
              {stats.submissions || 0} submissions{waiting ? ` · ${waiting} waiting` : ""}
            </span>
          </span>
        </button>
      </td>
      <td className="px-4 py-2.5"><StatusDot tone={live ? "success" : "neutral"}>{live ? "Live" : "Paused"}</StatusDot></td>
      <td className="tabular hidden px-4 py-2.5 text-right text-[13px] text-foreground/80 md:table-cell">{stats.views || 0}</td>
      <td className="tabular hidden px-4 py-2.5 text-right text-[13px] text-foreground/80 sm:table-cell">{stats.submissions || 0}</td>
      <td className={cx("tabular hidden px-4 py-2.5 text-right text-[13px] sm:table-cell", waiting ? "font-medium text-amber-700" : "text-foreground/80")}>{waiting}</td>
      <td className="tabular hidden px-4 py-2.5 text-right text-[13px] text-foreground/80 lg:table-cell">{stats.spam_blocked || 0}</td>
      <td className="tabular hidden whitespace-nowrap px-4 py-2.5 text-right text-xs text-muted-foreground sm:table-cell">
        {last ? <time dateTime={last} title={fullDateLabel(last)}>{agoLabel(last)}</time> : "No submissions"}
      </td>
      <td className="relative z-[1] w-12 py-2 pl-1 pr-3 text-right">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="icon" variant="ghost" className="size-8 text-muted-foreground" aria-label={`Actions for ${form.name}`}><MoreHorizontal /></Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem onSelect={onOpen}><Pencil />{isAdmin ? "Edit & embed" : "View & embed"}</DropdownMenuItem>
            <DropdownMenuItem onSelect={copyEmbed}><Copy />Copy embed code</DropdownMenuItem>
            {form.embed?.hosted_url && <DropdownMenuItem asChild><a href={form.embed.hosted_url} target="_blank" rel="noreferrer"><ExternalLink />Open hosted form</a></DropdownMenuItem>}
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild><Link to={`/leads?form=${form.id}`}><Inbox />Leads</Link></DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </td>
    </tr>
  );
}

export default function WebsiteForms() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [searchParams, setSearchParams] = useSearchParams();
  const [forms, setForms] = useState(null);
  const [catalog, setCatalog] = useState(null);
  const [members, setMembers] = useState([]);
  const [stages, setStages] = useState([]);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [newForm, setNewForm] = useState({ name: "", preset: "contact" });
  const selectedId = searchParams.get("form");

  const load = useCallback(async () => {
    try {
      const [formResponse, catalogResponse, pipelineResponse] = await Promise.all([
        api.get("/website-forms"), api.get("/website-forms/catalog"), api.get("/pipelines/default"),
      ]);
      setForms(formResponse.data.items); setCatalog(catalogResponse.data);
      setStages(pipelineResponse.data.stages || []); setError("");
    } catch (e) { setError(formatErr(e.response?.data?.detail) || "Website forms could not be loaded."); setForms((current) => current || []); }
    if (isAdmin) api.get("/team/members").then((response) => setMembers(response.data || [])).catch(() => setMembers([]));
  }, [isAdmin]);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!newForm.name.trim()) { toast.error("Give the form a name"); return; }
    try {
      const { data } = await api.post("/website-forms", newForm);
      setCreating(false); setNewForm({ name: "", preset: "contact" });
      toast.success("Form created — copy its embed code to your website");
      await load();
      setSearchParams({ form: data.id });
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  };

  const selected = (forms || []).find((form) => form.id === selectedId);
  if (selected && catalog) {
    return <FormEditor form={selected} catalog={catalog} members={members} stages={stages} isAdmin={isAdmin}
      onBack={() => setSearchParams({})} onSaved={() => load()} />;
  }

  const presetLabel = (form) => catalog?.presets.find((preset) => preset.key === form.form_type)?.label || form.form_type;

  return (
    <div className="cv-page" data-testid="website-forms-page">
      <PageHeader
        icon={Globe}
        title="Website forms"
        count={forms?.length || undefined}
        description="Every submission becomes a contact, an owner, a deal, a call-back task and an alert."
        actions={<>
          <Button size="sm" variant="outline" asChild><Link to="/leads">Open leads</Link></Button>
          {isAdmin && <Button size="sm" onClick={() => setCreating(true)} data-testid="new-website-form"><Plus />New form</Button>}
        </>}
      />
      {error && <Notice tone="warning" role="status" className="mb-5">{error}</Notice>}
      {forms === null ? (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="h-9 border-b border-border bg-muted/40" />
          {[0, 1].map((i) => (
            <div key={i} className="flex items-center gap-3 border-b border-border/70 px-4 py-3 last:border-0">
              <Skeleton className="size-8 rounded-lg" />
              <div className="flex-1 space-y-1.5"><Skeleton className="h-3.5 w-48" /><Skeleton className="h-3 w-28" /></div>
              <Skeleton className="h-3.5 w-16" />
            </div>
          ))}
        </div>
      ) : forms.length === 0 ? (
        <div className="flex flex-col items-center rounded-xl border border-border bg-card px-6 py-12 text-center">
          <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground"><Globe className="size-5" aria-hidden="true" /></span>
          <h2 className="mt-3 text-sm font-medium text-foreground">No website forms yet</h2>
          <p className="mt-1 max-w-sm text-[13px] leading-5 text-muted-foreground">Start from a real-estate template — contact, showing, valuation, consultation, open house or listing alerts.</p>
          {isAdmin && <Button size="sm" className="mt-4" onClick={() => setCreating(true)}><Plus />Create a form</Button>}
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <table className="w-full table-fixed text-[13px] sm:table-auto">
            <thead>
              <tr className="h-9 whitespace-nowrap border-b border-border bg-muted/40 text-xs text-muted-foreground">
                <th scope="col" className="px-4 text-left font-medium">Form</th>
                <th scope="col" className="w-20 px-4 text-left font-medium sm:w-28">Status</th>
                <th scope="col" className="hidden w-20 px-4 text-right font-medium md:table-cell">Views</th>
                <th scope="col" className="hidden w-28 px-4 text-right font-medium sm:table-cell">Submissions</th>
                <th scope="col" className="hidden w-24 px-4 text-right font-medium sm:table-cell">Waiting</th>
                <th scope="col" className="hidden w-28 px-4 text-right font-medium lg:table-cell">Spam blocked</th>
                <th scope="col" className="hidden w-36 px-4 text-right font-medium sm:table-cell">Last submission</th>
                <th scope="col" className="w-12"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {forms.map((form) => (
                <FormRow key={form.id} form={form} presetLabel={presetLabel(form)} isAdmin={isAdmin} onOpen={() => setSearchParams({ form: form.id })} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New website form</DialogTitle>
            <DialogDescription>Start from a template. You can change fields and automation afterwards.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <Field id="wf-new-name" label="Name">
              <Input id="wf-new-name" value={newForm.name} onChange={(event) => setNewForm({ ...newForm, name: event.target.value })} placeholder="e.g. Listing page — schedule a showing" />
            </Field>
            <fieldset>
              <legend className="mb-1.5 text-[13px] font-medium leading-5 text-foreground">Template</legend>
              <div className="grid max-h-[46vh] gap-2 overflow-auto sm:grid-cols-2">
                {(catalog?.presets || []).map((preset) => (
                  <label key={preset.key} className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-border px-3 py-2.5 transition-colors hover:bg-muted/50 has-[:checked]:border-foreground/30 has-[:checked]:bg-muted/60">
                    <input type="radio" name="wf-new-preset" value={preset.key} checked={newForm.preset === preset.key}
                      onChange={() => setNewForm({ ...newForm, preset: preset.key })} className="mt-[3px] size-3.5 accent-primary" />
                    <span className="min-w-0 text-[13px] font-medium leading-5 text-foreground">
                      {preset.label}
                      <span className="block text-xs font-normal text-muted-foreground">{preset.fields.length} fields</span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          </div>
          <DialogFooter>
            <Button size="sm" variant="outline" onClick={() => setCreating(false)}>Cancel</Button>
            <Button size="sm" onClick={create}>Create form</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
