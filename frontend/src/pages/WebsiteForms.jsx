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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowDown, ArrowLeft, ArrowUp, CheckCircle2, Copy, ExternalLink, FlaskConical, Globe, Plus, Save, ShieldCheck, Trash2 } from "lucide-react";

const clone = (value) => JSON.parse(JSON.stringify(value));
const slug = (text) => text.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);
const lines = (text) => text.split(/\n|,/).map((item) => item.trim()).filter(Boolean);

function Section({ title, description, children }) {
  return (
    <section className="cv-card p-5">
      <h3 className="cv-card-title">{title}</h3>
      {description && <p className="cv-card-description mb-4">{description}</p>}
      <div className="space-y-4">{children}</div>
    </section>
  );
}

function Field({ label, hint, children }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-sm font-semibold text-[#132038]">{label}</Label>
      {children}
      {hint && <p className="text-xs leading-5 text-slate-500">{hint}</p>}
    </div>
  );
}

function Toggle({ label, hint, checked, onChange, disabled }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <div className="text-sm font-semibold text-[#132038]">{label}</div>
        {hint && <p className="text-xs leading-5 text-slate-500">{hint}</p>}
      </div>
      <Switch checked={Boolean(checked)} onCheckedChange={onChange} disabled={disabled} />
    </div>
  );
}

function CodeBlock({ title, description, code }) {
  const copy = () => { navigator.clipboard?.writeText(code); toast.success(`${title} copied`); };
  return (
    <div className="rounded-xl border border-slate-200">
      <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div>
          <div className="text-sm font-semibold text-[#132038]">{title}</div>
          {description && <p className="text-xs leading-5 text-slate-500">{description}</p>}
        </div>
        <Button size="sm" variant="outline" onClick={copy}><Copy className="mr-1 h-3.5 w-3.5" />Copy</Button>
      </div>
      <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-all bg-slate-50 px-4 py-3 text-xs text-slate-700">{code}</pre>
    </div>
  );
}

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
    <div className="space-y-5">
      <Section title="Fields" description="What the form asks, in order. Real-estate fields are captured as structured data on the lead, the contact and the deal.">
        <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200">
          {draft.fields.map((field, index) => {
            const base = byKey[field.key];
            return (
              <li key={field.key} className="flex flex-col gap-3 p-3 sm:flex-row sm:items-center">
                <div className="flex shrink-0 gap-1">
                  <Button size="icon" variant="ghost" className="h-8 w-8" disabled={readOnly || index === 0} onClick={() => move(index, -1)} aria-label="Move up"><ArrowUp className="h-4 w-4" /></Button>
                  <Button size="icon" variant="ghost" className="h-8 w-8" disabled={readOnly || index === draft.fields.length - 1} onClick={() => move(index, 1)} aria-label="Move down"><ArrowDown className="h-4 w-4" /></Button>
                </div>
                <div className="min-w-0 flex-1">
                  <Input value={field.label ?? ""} placeholder={base?.label || field.key} disabled={readOnly} onChange={(event) => update(index, { label: event.target.value })} className="h-9" />
                  <div className="mt-1 text-[11px] text-slate-400">{field.key} · {field.type || base?.type || "text"}</div>
                </div>
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-600">Required<Switch aria-label={`${field.label || base?.label || field.key} is required`} checked={Boolean(field.required)} disabled={readOnly} onCheckedChange={(value) => update(index, { required: value })} /></div>
                <Button size="icon" variant="ghost" className="h-8 w-8 text-red-600" disabled={readOnly} onClick={() => remove(index)} aria-label="Remove field"><Trash2 className="h-4 w-4" /></Button>
              </li>
            );
          })}
        </ul>
        {!readOnly && (
          <div className="grid gap-4 lg:grid-cols-2">
            <Field label="Add a real-estate field">
              <Select value="" onValueChange={add}>
                <SelectTrigger className="h-9"><SelectValue placeholder="Choose a field…" /></SelectTrigger>
                <SelectContent>{available.map((field) => <SelectItem key={field.key} value={field.key}>{field.label}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Add a custom field" hint="For anything else you want to ask. Options are comma separated for a dropdown.">
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input value={custom.label} onChange={(event) => setCustom({ ...custom, label: event.target.value })} placeholder="e.g. Move-in date" className="h-9" />
                <Select value={custom.type} onValueChange={(type) => setCustom({ ...custom, type })}>
                  <SelectTrigger className="h-9 sm:w-32"><SelectValue /></SelectTrigger>
                  <SelectContent>{catalog.custom_field_types.map((type) => <SelectItem key={type} value={type}>{type}</SelectItem>)}</SelectContent>
                </Select>
                <Button variant="outline" className="h-9" onClick={addCustom}><Plus className="mr-1 h-4 w-4" />Add</Button>
              </div>
              {custom.type === "select" && <Input value={custom.options} onChange={(event) => setCustom({ ...custom, options: event.target.value })} placeholder="Option A, Option B" className="mt-2 h-9" />}
            </Field>
          </div>
        )}
        <p className="text-xs text-slate-500">Always captured as well, without adding fields: page URL, referrer, landing page, UTM tags, gclid and fbclid, and the listing a page is about.</p>
      </Section>
    </div>
  );
}

function SettingsTab({ draft, setDraft, readOnly }) {
  const s = draft.settings;
  const set = (patch) => setDraft((current) => ({ ...current, settings: { ...current.settings, ...patch } }));
  const setIn = (group, patch) => setDraft((current) => ({ ...current, settings: { ...current.settings, [group]: { ...current.settings[group], ...patch } } }));
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <Section title="Form" description="Name, availability and what the visitor sees.">
        <Field label="Form name"><Input value={draft.name} disabled={readOnly} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></Field>
        <Field label="Status" hint="A paused form stops accepting submissions; its embed shows it as unavailable.">
          <Select value={draft.status} onValueChange={(status) => setDraft({ ...draft, status })} disabled={readOnly}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="active">Active</SelectItem><SelectItem value="paused">Paused</SelectItem></SelectContent>
          </Select>
        </Field>
        <Field label="Button text"><Input value={s.submit_text} disabled={readOnly} onChange={(event) => set({ submit_text: event.target.value })} /></Field>
        <Field label="Thank-you message"><Textarea value={s.success_message} disabled={readOnly} onChange={(event) => set({ success_message: event.target.value })} rows={3} /></Field>
        <Field label="Or redirect to a thank-you page" hint="Leave empty to show the message above. Use your own thank-you page to fire ad-conversion pixels.">
          <Input value={s.redirect_url || ""} disabled={readOnly} placeholder="https://www.yoursite.com/thank-you" onChange={(event) => set({ redirect_url: event.target.value || null })} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Button colour"><Input type="color" value={s.theme.primary_color} disabled={readOnly} onChange={(event) => setIn("theme", { primary_color: event.target.value })} className="h-10 p-1" /></Field>
          <Field label="Layout">
            <Select value={s.theme.layout} onValueChange={(layout) => setIn("theme", { layout })} disabled={readOnly}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="stacked">One column</SelectItem><SelectItem value="two_column">Two columns</SelectItem></SelectContent>
            </Select>
          </Field>
        </div>
      </Section>
      <Section title="Data handling" description="Where leads may come from, and how they join your existing records.">
        <Field label="Allowed websites" hint="One per line, e.g. https://www.yoursite.com. Browsers on other sites are refused. Leave empty to allow any site. Zapier and server-side posts are always allowed.">
          <Textarea value={(s.allowed_origins || []).join("\n")} disabled={readOnly} rows={3} onChange={(event) => set({ allowed_origins: lines(event.target.value) })} />
        </Field>
        <Field label="When the person is already in the CRM">
          <Select value={s.duplicate_policy} onValueChange={(duplicate_policy) => set({ duplicate_policy })} disabled={readOnly}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="update_existing">Update the existing contact (match on email or phone)</SelectItem>
              <SelectItem value="always_new">Always create a new contact</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field label="Tags added to the contact" hint="Comma separated.">
          <Input value={(s.tags || []).join(", ")} disabled={readOnly} onChange={(event) => set({ tags: lines(event.target.value) })} />
        </Field>
        <Field label="Text-message consent wording" hint="Shown next to the consent checkbox and stored with the lead as evidence.">
          <Textarea value={s.consent.sms_text} disabled={readOnly} rows={3} onChange={(event) => setIn("consent", { sms_text: event.target.value })} />
        </Field>
        <Field label="Email consent wording">
          <Textarea value={s.consent.email_text} disabled={readOnly} rows={2} onChange={(event) => setIn("consent", { email_text: event.target.value })} />
        </Field>
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
    <div className="grid gap-5 xl:grid-cols-2">
      <Section title="Assign the lead" description="Who owns each new lead. Their call-back task and alerts go to them.">
        <Field label="Assignment">
          <Select value={s.assignment.mode} onValueChange={(mode) => setIn("assignment", { mode })} disabled={readOnly}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="unassigned">Unassigned — alert every admin</SelectItem>
              <SelectItem value="specific">A specific agent</SelectItem>
              <SelectItem value="round_robin">Round-robin across agents</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        {s.assignment.mode !== "unassigned" && (
          <Field label={s.assignment.mode === "specific" ? "Agent (the first one ticked)" : "Agents in the rotation"}>
            <div className="max-h-48 space-y-1 overflow-auto rounded-xl border border-slate-200 p-2">
              {members.length === 0 && <p className="p-2 text-xs text-slate-500">Team members are visible to admins only.</p>}
              {members.filter((member) => member.status === "active").map((member) => (
                <label key={member.email} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-slate-50">
                  <input type="checkbox" checked={s.assignment.users.includes(member.email)} disabled={readOnly} onChange={() => toggleAgent(member.email)} />
                  <span>{member.name || member.email}</span><span className="text-xs text-slate-400">{member.email}</span>
                </label>
              ))}
            </div>
          </Field>
        )}
        <Toggle label="Keep the existing owner" hint="A returning contact stays with the agent who already owns them." checked={s.assignment.keep_existing_owner} disabled={readOnly} onChange={(value) => setIn("assignment", { keep_existing_owner: value })} />
      </Section>

      <Section title="Speed to lead" description="The call-back task and the escalation clock. Leads contacted within five minutes convert far more often.">
        <Toggle label="Create a call-back task" checked={s.speed_to_lead.task_enabled} disabled={readOnly} onChange={(value) => setIn("speed_to_lead", { task_enabled: value })} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Call within (minutes)"><Input type="number" min={1} value={s.speed_to_lead.due_minutes} disabled={readOnly} onChange={(event) => setIn("speed_to_lead", { due_minutes: Number(event.target.value) })} /></Field>
          <Field label="Escalate after (minutes)" hint="Admins and the agent are alerted if nobody has responded."><Input type="number" min={1} value={s.speed_to_lead.escalate_after_minutes} disabled={readOnly} onChange={(event) => setIn("speed_to_lead", { escalate_after_minutes: Number(event.target.value) })} /></Field>
        </div>
        <Toggle label="In-app alert" checked={s.notify.in_app} disabled={readOnly} onChange={(value) => setIn("notify", { in_app: value })} />
        <Toggle label="Email alert" hint="Sent when email delivery is configured for this CRM." checked={s.notify.email} disabled={readOnly} onChange={(value) => setIn("notify", { email: value })} />
        <p className="text-xs leading-5 text-slate-500">Need a text alert or a Slack ping? Add a webhook for the <code>lead.received</code> event under Registries → Webhooks; it carries the full lead.</p>
      </Section>

      <Section title="Pipeline" description="Open a deal for each new lead so it shows up in your pipeline and in lost-revenue tracking.">
        <Toggle label="Create a deal" hint="A returning lead with an open deal from this form within 30 days is linked to it, not doubled." checked={s.opportunity.enabled} disabled={readOnly} onChange={(value) => setIn("opportunity", { enabled: value })} />
        {s.opportunity.enabled && (
          <>
            <Field label="Stage">
              <Select value={s.opportunity.stage || openStages[0]?.key || ""} onValueChange={(stage) => setIn("opportunity", { stage })} disabled={readOnly}>
                <SelectTrigger><SelectValue placeholder="First stage" /></SelectTrigger>
                <SelectContent>{openStages.map((stage) => <SelectItem key={stage.key} value={stage.key}>{stage.label}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Deal value" hint="Expected commission uses the price the visitor gives (max price, home value or min price) × your commission rate, and falls back to the flat value when there's no realistic price.">
              <Select value={s.opportunity.value_mode} onValueChange={(value_mode) => setIn("opportunity", { value_mode })} disabled={readOnly}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="commission">Expected commission (GCI)</SelectItem><SelectItem value="fixed">Flat value</SelectItem></SelectContent>
              </Select>
            </Field>
            <div className="grid gap-4 sm:grid-cols-3">
              {s.opportunity.value_mode === "commission" && <Field label="Commission %"><Input type="number" step="0.1" min={0} value={s.opportunity.commission_rate} disabled={readOnly} onChange={(event) => setIn("opportunity", { commission_rate: Number(event.target.value) })} /></Field>}
              <Field label={s.opportunity.value_mode === "commission" ? "Fallback value" : "Value"}><Input type="number" min={0} value={s.opportunity.fixed_value} disabled={readOnly} onChange={(event) => setIn("opportunity", { fixed_value: Number(event.target.value) })} /></Field>
              <Field label="Currency"><Input value={s.opportunity.currency} maxLength={3} disabled={readOnly} onChange={(event) => setIn("opportunity", { currency: event.target.value.toUpperCase() })} /></Field>
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
    <div className="grid gap-5 xl:grid-cols-[1fr_22rem]">
      <Section title="Automatic reply to the lead" description="Sent within seconds to every new lead who leaves an email. You approve the exact wording once; each reply is then sent from that approved template.">
        <Toggle label="Send an automatic reply" checked={reply.enabled} disabled={readOnly} onChange={(value) => setReply({ enabled: value })} />
        <Field label="Subject"><Input value={reply.subject} disabled={readOnly} onChange={(event) => setReply({ subject: event.target.value })} /></Field>
        <Field label="Message" hint={`Merge fields: ${catalog.merge_fields.map((key) => `{${key}}`).join(", ")}. Nothing else is filled in.`}>
          <Textarea value={reply.body} disabled={readOnly} rows={8} onChange={(event) => setReply({ body: event.target.value })} />
        </Field>
      </Section>
      <Section title="Approval">
        {!reply.enabled ? <p className="text-sm text-slate-500">Turned off. Leads are still contacted by your call-back task.</p>
          : changed ? <p className="text-sm text-amber-700">Save your changes to submit this wording for approval.</p>
          : state === "approved" ? <p className="flex items-center gap-2 text-sm font-semibold text-emerald-700"><CheckCircle2 className="h-4 w-4" />Approved — replies are going out.</p>
          : (
            <div className="space-y-3">
              <p className="text-sm text-amber-700">Waiting for approval. No reply is sent until this exact wording is approved; editing it later needs a new approval.</p>
              {isAdmin && form.auto_reply_state?.approval_id && <Button className="cv-action-primary" onClick={approve}><ShieldCheck className="mr-1.5 h-4 w-4" />Approve this wording</Button>}
              <p className="text-xs text-slate-500">Also listed under <Link className="font-semibold text-[#127b96]" to="/operations?tab=approvals">Operations → Approvals</Link>.</p>
            </div>
          )}
        <p className="text-xs leading-5 text-slate-500">Replies are sent from your connected Gmail account. If Gmail isn't connected, each lead shows the reply as blocked with the reason, and nothing is lost.</p>
      </Section>
    </div>
  );
}

function EmbedTab({ form, isAdmin }) {
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState(null);
  const embed = form.embed;
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
      <Section title="Check the whole path" description="Sends a lead marked as a test through the same pipeline a real one takes: contact, assignment, deal, call-back task and alert. Test leads never count in reporting.">
        <div className="flex flex-wrap gap-2">
          {isAdmin && <Button className="cv-action-primary" onClick={runTest} disabled={testing}><FlaskConical className="mr-1.5 h-4 w-4" />{testing ? "Sending…" : "Send a test lead"}</Button>}
          <Button variant="outline" asChild><a href={embed.hosted_url} target="_blank" rel="noreferrer"><ExternalLink className="mr-1.5 h-4 w-4" />Open the hosted form</a></Button>
        </div>
        {result?.lead && (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
            <div className="font-semibold">Worked end to end.</div>
            <ul className="mt-2 space-y-1">
              {(result.lead.automation || []).map((step, index) => <li key={index}>{step.step}: {step.result}</li>)}
            </ul>
            <Link className="mt-2 inline-block font-semibold text-[#127b96]" to={`/leads?lead=${result.lead.id}`}>Open the test lead</Link>
          </div>
        )}
      </Section>
      <div className="grid gap-4 xl:grid-cols-2">
        <CodeBlock title="Inline form" description="Paste where the form should appear (WordPress Custom HTML block, Squarespace Code block, Webflow Embed, IDX custom HTML)." code={embed.inline} />
        <CodeBlock title="Pop-up on a button" description="A button that opens the form in a pop-up." code={embed.popup} />
        <CodeBlock title="Pop-up after a delay" description="Opens once per visit after 15 seconds. Use data-trigger=&quot;scroll:50&quot; for half-way down the page, or &quot;exit&quot; for exit intent." code={embed.popup_auto} />
        <CodeBlock title="Slide-in" description="A small panel in the corner when the visitor is half-way down the page. Pop-ups never show again to someone who already submitted." code={embed.slide_in} />
        <CodeBlock title="On a listing page" description="Attaches the listing to every lead from that page. Replace the MLS number and address per listing (most IDX templates have placeholders for these)." code={embed.listing_page} />
        <CodeBlock title="iFrame" description="For builders that only allow iframes (Wix, some IDX vendors)." code={embed.iframe} />
        <CodeBlock title="Hosted link" description="Share by text, email, QR code or a social bio link." code={embed.hosted_url} />
        <CodeBlock title="Your own HTML form" description="Keep your site's existing form design: point it here and keep the hidden _hp field." code={embed.html_form} />
        <CodeBlock title="Zapier, Make or a form plugin's webhook" description="POST JSON or form data to this URL. Send a unique _sid per submission so retries are never filed twice." code={`${embed.api.method} ${embed.api.url}\nAccepts: ${embed.api.content_types.join(", ")}\nFields: ${embed.api.fields.join(", ")}`} />
      </div>
    </div>
  );
}

function FormEditor({ form, catalog, members, stages, isAdmin, onBack, onSaved }) {
  const [draft, setDraft] = useState(() => clone(form));
  const [saving, setSaving] = useState(false);
  useEffect(() => { setDraft(clone(form)); }, [form]);
  const dirty = useMemo(() => JSON.stringify({ n: draft.name, s: draft.status, f: draft.fields, t: draft.settings }) !== JSON.stringify({ n: form.name, s: form.status, f: form.fields, t: form.settings }), [draft, form]);
  const readOnly = !isAdmin;
  const save = async () => {
    setSaving(true);
    try {
      const fields = draft.fields.map(({ key, required, label, type, options, placeholder }) => ({ key, required, label: label || null, type: type || null, options: options || null, placeholder: placeholder || null }));
      const { data } = await api.patch(`/website-forms/${form.id}`, { name: draft.name, status: draft.status, fields, settings: draft.settings });
      toast.success("Form saved");
      onSaved(data);
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };
  return (
    <div className="cv-page" data-testid="website-form-editor">
      <div className="cv-page-header">
        <div>
          <button type="button" onClick={onBack} className="mb-2 inline-flex items-center gap-1 text-sm font-semibold text-[#127b96]"><ArrowLeft className="h-4 w-4" />All forms</button>
          <h1 className="cv-page-title">{form.name}</h1>
          <p className="cv-page-description">{form.stats?.views || 0} views · {form.stats?.submissions || 0} submissions{form.stats?.views ? ` (${Math.round(((form.stats?.submissions || 0) / form.stats.views) * 100)}% conversion)` : ""} · {form.lead_counts?.new || 0} waiting for a response · {form.stats?.spam_blocked || 0} spam blocked</p>
        </div>
        {isAdmin && <Button className="cv-action-primary" onClick={save} disabled={!dirty || saving}><Save className="mr-1.5 h-4 w-4" />{saving ? "Saving…" : dirty ? "Save changes" : "Saved"}</Button>}
      </div>
      {!isAdmin && <div className="mb-5 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">Only workspace admins can change forms. You can copy the embed codes.</div>}
      <Tabs defaultValue="fields">
        <TabsList className="mb-5 flex h-auto flex-wrap justify-start">
          <TabsTrigger value="fields">Fields</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
          <TabsTrigger value="automation">Automation</TabsTrigger>
          <TabsTrigger value="reply">Auto-reply</TabsTrigger>
          <TabsTrigger value="embed">Embed &amp; test</TabsTrigger>
        </TabsList>
        <TabsContent value="fields"><FieldsTab draft={draft} setDraft={setDraft} catalog={catalog} readOnly={readOnly} /></TabsContent>
        <TabsContent value="settings"><SettingsTab draft={draft} setDraft={setDraft} readOnly={readOnly} /></TabsContent>
        <TabsContent value="automation"><AutomationTab draft={draft} setDraft={setDraft} members={members} stages={stages} readOnly={readOnly} /></TabsContent>
        <TabsContent value="reply"><ReplyTab form={form} draft={draft} setDraft={setDraft} catalog={catalog} readOnly={readOnly} isAdmin={isAdmin} onApproved={() => onSaved(null)} /></TabsContent>
        <TabsContent value="embed"><EmbedTab form={form} isAdmin={isAdmin} /></TabsContent>
      </Tabs>
    </div>
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

  return (
    <div className="cv-page" data-testid="website-forms-page">
      <div className="cv-page-header">
        <div>
          <div className="cv-eyebrow">Lead capture</div>
          <h1 className="cv-page-title">Website forms</h1>
          <p className="cv-page-description">Forms for your real-estate website. Every submission becomes a contact, an owner, a deal, a call-back task and an alert within seconds.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild><Link to="/leads">Open leads</Link></Button>
          {isAdmin && <Button className="cv-action-primary" onClick={() => setCreating(true)} data-testid="new-website-form"><Plus className="mr-1.5 h-4 w-4" />New form</Button>}
        </div>
      </div>
      {error && <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800" role="status">{error}</div>}
      {forms === null ? (
        <div className="grid gap-4 lg:grid-cols-2">{[0, 1].map((i) => <Skeleton key={i} className="h-40 rounded-2xl" />)}</div>
      ) : forms.length === 0 ? (
        <div className="cv-card p-10 text-center">
          <Globe className="mx-auto mb-3 h-8 w-8 text-[#1a9fbf]" />
          <h2 className="font-display text-lg font-bold text-[#132038]">No website forms yet</h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">Start from a real-estate template — contact, schedule a showing, home valuation, buyer or seller consultation, open house sign-in or listing alerts.</p>
          {isAdmin && <Button className="cv-action-primary mt-4" onClick={() => setCreating(true)}><Plus className="mr-1.5 h-4 w-4" />Create a form</Button>}
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {forms.map((form) => (
            <article key={form.id} className="cv-card flex flex-col gap-4 p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="font-display text-lg font-bold text-[#132038]">{form.name}</h2>
                  <p className="text-xs text-slate-500">{catalog?.presets.find((preset) => preset.key === form.form_type)?.label || form.form_type} · {form.fields.length} fields</p>
                </div>
                <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${form.status === "active" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-600"}`}>{form.status === "active" ? "Live" : "Paused"}</span>
              </div>
              <dl className="grid grid-cols-2 gap-3 text-center sm:grid-cols-4">
                <div className="rounded-xl bg-slate-50 p-3"><dt className="text-[11px] font-semibold uppercase text-slate-500">Views</dt><dd className="font-display text-xl font-bold">{form.stats?.views || 0}</dd></div>
                <div className="rounded-xl bg-slate-50 p-3"><dt className="text-[11px] font-semibold uppercase text-slate-500">Submissions</dt><dd className="font-display text-xl font-bold">{form.stats?.submissions || 0}</dd></div>
                <div className="rounded-xl bg-amber-50 p-3"><dt className="text-[11px] font-semibold uppercase text-amber-700">Waiting</dt><dd className="font-display text-xl font-bold text-amber-800">{form.lead_counts?.new || 0}</dd></div>
                <div className="rounded-xl bg-slate-50 p-3"><dt className="text-[11px] font-semibold uppercase text-slate-500">Spam blocked</dt><dd className="font-display text-xl font-bold">{form.stats?.spam_blocked || 0}</dd></div>
              </dl>
              <p className="text-xs text-slate-500">{form.stats?.last_submission_at ? `Last lead ${new Date(form.stats.last_submission_at).toLocaleString()}` : "No submissions yet — send a test lead from the editor to check the wiring."}</p>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" className="cv-action-primary" onClick={() => setSearchParams({ form: form.id })}>{isAdmin ? "Edit & embed" : "View & embed"}</Button>
                <Button size="sm" variant="outline" onClick={() => { navigator.clipboard?.writeText(form.embed.inline); toast.success("Embed code copied"); }}><Copy className="mr-1 h-3.5 w-3.5" />Copy embed code</Button>
                <Button size="sm" variant="ghost" asChild><Link to={`/leads?form=${form.id}`}>Leads</Link></Button>
              </div>
            </article>
          ))}
        </div>
      )}

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New website form</DialogTitle>
            <DialogDescription>Start from a template. You can change fields and automation afterwards.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <Field label="Name"><Input value={newForm.name} onChange={(event) => setNewForm({ ...newForm, name: event.target.value })} placeholder="e.g. Listing page — schedule a showing" /></Field>
            <Field label="Template">
              <Select value={newForm.preset} onValueChange={(preset) => setNewForm({ ...newForm, preset })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{(catalog?.presets || []).map((preset) => <SelectItem key={preset.key} value={preset.key}>{preset.label}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreating(false)}>Cancel</Button>
            <Button className="cv-action-primary" onClick={create}>Create form</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
