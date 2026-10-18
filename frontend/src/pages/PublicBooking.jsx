/* The public booking page: /book/<key>.

   Outside the signed-in app and frameable by an agent's website (`?embed=1` drops the
   page background and reports its height to the embed script). Three steps, each with
   its heading focused when it opens: pick a day and a free time in your own time zone,
   leave your details, and see the confirmation with add-to-calendar buttons and the link
   to reschedule or cancel. If someone else takes the time first, the page says so and
   shows the times still open. Links on a listing page can prefill the property:
   ?property_address=...&listing_id=... (and first_name, last_name, email, phone). */
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Clock, Loader2, UserRound } from "lucide-react";
import SlotPicker, { brandStyle } from "@/components/booking/SlotPicker";
import { AddToCalendar, LocationLine, ManageLink, PublicFrame, PublicMessage, SummaryCard } from "@/components/booking/BookingParts";
import { addDays, attribution, browserTimeZone, dayKey, formatRange, newSubmissionId, publicCall, zoneLabel } from "@/lib/booking";

const PREFILL = { first_name: "first_name", last_name: "last_name", email: "email", phone: "phone",
  property_address: "property_address", address: "property_address", listing_id: "listing_id", mls: "listing_id" };

function InfoPanel({ config, compact }) {
  return (
    <div className={compact ? "space-y-3" : "space-y-4"}>
      {config.brand_name && <div className="text-xs font-bold uppercase tracking-[0.14em] text-[var(--brand)]">{config.brand_name}</div>}
      <h1 className="font-display text-2xl font-extrabold tracking-tight text-[#0a1628] sm:text-3xl">{config.name}</h1>
      <div className="space-y-2.5 text-sm">
        <div className="flex items-center gap-2.5"><Clock className="h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" /><span className="font-semibold text-[#0a1628]">{config.duration_minutes} minutes</span></div>
        <LocationLine location={config.location} />
        {config.host_name && <div className="flex items-center gap-2.5"><UserRound className="h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" /><span className="font-semibold text-[#0a1628]">with {config.host_name}</span></div>}
      </div>
      {config.description && !compact && <p className="text-sm leading-6 text-slate-600">{config.description}</p>}
    </div>
  );
}

function FieldInput({ field, value, error, onChange }) {
  const id = `book-${field.key}`;
  const describedBy = error ? `${id}-error` : undefined;
  const base = `w-full rounded-xl border bg-white px-3.5 text-base text-[#0a1628] outline-none transition-shadow motion-reduce:transition-none focus:ring-2 focus:ring-[var(--brand)] focus:ring-offset-1 sm:text-sm ${error ? "border-red-400" : "border-slate-300"}`;
  if (field.type === "checkbox") {
    return (
      <div>
        <label htmlFor={id} className="flex items-start gap-3 text-sm leading-5 text-slate-700">
          <input id={id} type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)}
            aria-invalid={Boolean(error)} aria-describedby={describedBy} data-testid={`book-field-${field.key}`}
            className="mt-0.5 h-5 w-5 shrink-0 rounded border-slate-300 accent-[var(--brand)]" />
          <span>{field.label}{field.required ? " *" : ""}</span>
        </label>
        {error && <p id={`${id}-error`} className="mt-1 text-sm text-red-700">{error}</p>}
      </div>
    );
  }
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-semibold text-[#0a1628]">
        {field.label}{field.required ? <span className="text-red-700" aria-hidden="true"> *</span> : <span className="font-normal text-slate-500"> (optional)</span>}
      </label>
      {field.type === "textarea" ? (
        <textarea id={id} rows={3} value={value || ""} onChange={(event) => onChange(event.target.value)} required={field.required}
          aria-invalid={Boolean(error)} aria-describedby={describedBy} className={`${base} py-2.5`} data-testid={`book-field-${field.key}`} />
      ) : field.type === "select" ? (
        <select id={id} value={value || ""} onChange={(event) => onChange(event.target.value)} required={field.required}
          aria-invalid={Boolean(error)} aria-describedby={describedBy} className={`${base} h-12`} data-testid={`book-field-${field.key}`}>
          <option value="">Choose…</option>
          {(field.options || []).map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      ) : (
        <input id={id} value={value || ""} onChange={(event) => onChange(event.target.value)} required={field.required}
          type={{ email: "email", tel: "tel" }[field.type] || "text"} inputMode={field.type === "number" ? "decimal" : undefined}
          autoComplete={field.autocomplete || undefined} aria-invalid={Boolean(error)} aria-describedby={describedBy}
          className={`${base} h-12`} data-testid={`book-field-${field.key}`} />
      )}
      {error && <p id={`${id}-error`} className="mt-1 text-sm text-red-700">{error}</p>}
    </div>
  );
}

export default function PublicBooking() {
  const { key } = useParams();
  const [params] = useSearchParams();
  const embed = params.get("embed") === "1";
  const [config, setConfig] = useState(null);
  const [missing, setMissing] = useState(false);
  const [zone, setZone] = useState(browserTimeZone());
  const [step, setStep] = useState("pick");
  const [start, setStart] = useState(null);
  const [values, setValues] = useState(() => {
    const out = {};
    Object.entries(PREFILL).forEach(([param, field]) => { if (params.get(param)) out[field] = params.get(param).slice(0, 300); });
    return out;
  });
  const [errors, setErrors] = useState({});
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [booked, setBooked] = useState(null);
  const sid = useRef(newSubmissionId());
  // Time on the page, for the server's too-fast-to-be-a-person check. Counted from opening
  // the page and never reset: after a refused time the details are still filled in, so a
  // visitor who picks another time can rightly send them again within seconds.
  const pageOpenedAt = useRef(Date.now());
  const honeypot = useRef(null);
  const heading = useRef(null);
  const picker = useRef(null);

  useEffect(() => {
    let live = true;
    publicCall(`${encodeURIComponent(key)}/config`).then((response) => {
      if (!live) return;
      if (!response.ok) { setMissing(true); return; }
      setConfig(response.data);
      document.title = `${response.data.name} · Book a time`;
    }).catch(() => live && setMissing(true));
    return () => { live = false; };
  }, [key]);

  useEffect(() => {
    if (step !== "pick") heading.current?.focus();
  }, [step]);

  const loadDays = useCallback(async (first, last, tz) => {
    const response = await publicCall(`${encodeURIComponent(key)}/slots`, { params: { start: first, end: last, tz } });
    if (!response.ok) throw new Error(response.data?.detail || "Free times could not be loaded.");
    return response.data.days;
  }, [key]);

  const submit = async (event) => {
    event.preventDefault();
    setErrors({}); setNotice("");
    setBusy(true);
    const body = { ...attribution(), ...values, start, timezone: zone, _sid: sid.current,
      _elapsed_ms: Date.now() - pageOpenedAt.current, _hp: honeypot.current?.value || "" };
    try {
      const response = await publicCall(`${encodeURIComponent(key)}/book`, { method: "POST", body });
      if (response.ok) {
        setBooked(response.data.booking);
        sid.current = newSubmissionId();
        setStep("done");
      } else if (response.status === 409) {
        picker.current?.update(response.data.days);
        setStart(null);
        setStep("pick");
        setNotice(response.data.detail || "That time was just taken. Please pick another.");
      } else if (response.status === 422 && response.data.errors) {
        setErrors(response.data.errors);
        setNotice(response.data.detail || "Please check the highlighted fields.");
        if (response.data.errors.start) setStep("pick");
      } else {
        setNotice(response.data.detail || "Something went wrong. Please try again.");
      }
    } catch {
      setNotice("We couldn't reach the calendar. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  };

  if (missing) {
    return <PublicFrame embed={embed} testid="public-booking"><PublicMessage title="This booking page isn't available" testid="public-booking-missing">It may have been paused or the link mistyped. Please contact the agent directly.</PublicMessage></PublicFrame>;
  }
  if (!config) {
    return (
      <PublicFrame embed={embed} testid="public-booking">
        <div className="flex min-h-[50vh] items-center justify-center text-slate-500" aria-busy="true"><Loader2 className="h-6 w-6 animate-spin motion-reduce:animate-none" aria-label="Loading" /></div>
      </PublicFrame>
    );
  }

  const today = dayKey(new Date(), zone);
  const maxKey = addDays(today, config.max_days_ahead);
  const fields = config.questions || [];

  return (
    <PublicFrame embed={embed} color={config.color} testid="public-booking">
      <div className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-[0_1px_2px_rgba(10,22,40,0.04),0_24px_60px_rgba(10,22,40,0.08)]" style={brandStyle(config.color)}>
        <div className="grid lg:grid-cols-[19rem_minmax(0,1fr)]">
          <aside className="border-b border-slate-100 bg-slate-50/60 p-5 sm:p-7 lg:border-b-0 lg:border-r" data-testid="public-booking-info">
            <InfoPanel config={config} compact={step !== "pick"} />
            {start && step === "details" && (
              <div className="mt-5 rounded-2xl border border-[var(--brand)] bg-white p-3.5 text-sm" data-testid="public-booking-chosen">
                <div className="font-semibold text-[#0a1628]">{formatRange(start, null, zone)}</div>
                <div className="text-slate-500">{zoneLabel(zone, new Date(start))}</div>
              </div>
            )}
          </aside>

          <section className="min-w-0 p-5 sm:p-7" aria-live="polite">
            {notice && <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-900" role="alert" data-testid="public-booking-notice">{notice}</div>}

            {step === "pick" && (
              <>
                <h2 className="mb-5 font-display text-xl font-bold text-[#0a1628]">Pick a day and time</h2>
                {!config.available
                  ? <p className="rounded-xl bg-slate-50 p-6 text-center text-sm text-slate-600">No times are open right now. Please contact the agent directly.</p>
                  : <SlotPicker loadDays={loadDays} zone={zone} onZoneChange={setZone} maxKey={maxKey} controlRef={picker}
                      selectedStart={start} testid="public-slots"
                      onPick={(value) => { setStart(value); setNotice(""); setStep("details"); }} />}
              </>
            )}

            {step === "details" && (
              <form onSubmit={submit} noValidate data-testid="public-booking-form" className="max-w-xl">
                <button type="button" onClick={() => setStep("pick")} className="mb-4 inline-flex items-center gap-1.5 rounded-lg px-1 py-1 text-sm font-semibold text-[var(--brand)] hover:underline" data-testid="public-booking-back">
                  <ArrowLeft className="h-4 w-4" aria-hidden="true" />Choose another time
                </button>
                <h2 ref={heading} tabIndex={-1} className="mb-5 font-display text-xl font-bold text-[#0a1628] outline-none">Your details</h2>
                <div className="grid gap-4 sm:grid-cols-2">
                  {fields.map((field) => (
                    <div key={field.key} className={["first_name", "last_name"].includes(field.key) ? "" : "sm:col-span-2"}>
                      <FieldInput field={field} value={values[field.key]} error={errors[field.key]}
                        onChange={(value) => setValues((current) => ({ ...current, [field.key]: value }))} />
                    </div>
                  ))}
                </div>
                <div className="absolute -left-[10000px] h-px w-px overflow-hidden" aria-hidden="true">
                  <label>Leave this field empty<input ref={honeypot} type="text" name="_hp" tabIndex={-1} autoComplete="off" /></label>
                </div>
                <button type="submit" disabled={busy} data-testid="public-booking-submit"
                  className="mt-6 inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-[var(--brand)] px-6 text-base font-bold text-white shadow-sm hover:opacity-90 disabled:opacity-60 sm:w-auto">
                  {busy && <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}{busy ? "Booking…" : "Confirm booking"}
                </button>
              </form>
            )}

            {step === "done" && booked && (
              <div className="max-w-xl space-y-5" data-testid="public-booking-done">
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="h-9 w-9 shrink-0 text-emerald-600" aria-hidden="true" />
                  <div>
                    <h2 ref={heading} tabIndex={-1} className="font-display text-2xl font-extrabold text-[#0a1628] outline-none">You're booked{values.first_name ? `, ${values.first_name}` : ""}!</h2>
                    {booked.confirmation_message && <p className="mt-1 text-sm leading-6 text-slate-600">{booked.confirmation_message}</p>}
                  </div>
                </div>
                <SummaryCard booking={booked} zone={zone} />
                <div>
                  <div className="mb-2 text-sm font-semibold text-[#0a1628]">Add it to your calendar</div>
                  <AddToCalendar links={booked.links} />
                </div>
                <ManageLink url={booked.links?.manage_url} newTab={embed} />
              </div>
            )}
          </section>
        </div>
      </div>
      {!embed && <p className="mt-4 text-center text-xs text-slate-500">Times are shown in {zoneLabel(zone)}. Your details go only to {config.host_name || "the agent"}.</p>}
    </PublicFrame>
  );
}
