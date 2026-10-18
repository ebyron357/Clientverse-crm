/* The person's own booking: /booking/manage/<token>.

   The token in the address is the only key -- it opens this one booking and nothing else.
   From here the person sees their appointment, adds it to their calendar, moves it to
   another free time (their own time stays offered while they choose) or cancels it with a
   reason. Not frameable, and nothing here links into the signed-in app. */
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { CalendarClock, CheckCircle2, Loader2, XCircle } from "lucide-react";
import SlotPicker from "@/components/booking/SlotPicker";
import { AddToCalendar, PublicFrame, PublicMessage, SummaryCard } from "@/components/booking/BookingParts";
import { addDays, browserTimeZone, dayKey, formatRange, publicCall, zoneLabel } from "@/lib/booking";

const STATUS_TEXT = {
  confirmed: null,
  cancelled: "This booking is cancelled.",
  completed: "This appointment has taken place.",
  no_show: "This appointment has passed.",
};

export default function ManageBooking() {
  const { token } = useParams();
  const [booking, setBooking] = useState(null);
  const [missing, setMissing] = useState(false);
  const [mode, setMode] = useState("view"); // view | reschedule | confirm-move | cancel
  const [zone, setZone] = useState(browserTimeZone());
  const [newStart, setNewStart] = useState(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [done, setDone] = useState("");
  const heading = useRef(null);
  const picker = useRef(null);
  const path = `manage/${encodeURIComponent(token)}`;

  useEffect(() => {
    let live = true;
    publicCall(path).then((response) => {
      if (!live) return;
      if (!response.ok) { setMissing(true); return; }
      setBooking(response.data);
      setZone(response.data.timezone || browserTimeZone());
      document.title = `${response.data.title} · Your booking`;
    }).catch(() => live && setMissing(true));
    return () => { live = false; };
  }, [path]);

  useEffect(() => { heading.current?.focus(); }, [mode, done]);

  const loadDays = useCallback(async (first, last, tz) => {
    const response = await publicCall(`${path}/slots`, { params: { start: first, end: last, tz } });
    if (!response.ok) throw new Error(response.data?.detail || "Free times could not be loaded.");
    return response.data.days;
  }, [path]);

  const move = async () => {
    setBusy(true); setNotice("");
    const response = await publicCall(`${path}/reschedule`, { method: "POST", body: { start: newStart, timezone: zone } }).catch(() => null);
    setBusy(false);
    if (response?.ok) { setBooking(response.data.booking); setMode("view"); setDone("moved"); return; }
    if (response?.status === 409 && response.data.days) {
      picker.current?.update(response.data.days);
      setMode("reschedule"); setNewStart(null);
    }
    setNotice(response?.data?.detail || "That didn't work. Please try again.");
  };

  const cancel = async (event) => {
    event.preventDefault();
    setBusy(true); setNotice("");
    const response = await publicCall(`${path}/cancel`, { method: "POST", body: { reason } }).catch(() => null);
    setBusy(false);
    if (response?.ok) { setBooking(response.data.booking); setMode("view"); setDone("cancelled"); return; }
    setNotice(response?.data?.detail || "That didn't work. Please try again.");
  };

  if (missing) {
    return <PublicFrame testid="manage-booking"><PublicMessage title="This link isn't valid" testid="manage-booking-missing">Check that you used the whole link from your confirmation. If it still doesn't work, contact the agent directly.</PublicMessage></PublicFrame>;
  }
  if (!booking) {
    return <PublicFrame testid="manage-booking"><div className="flex min-h-[50vh] items-center justify-center text-slate-500" aria-busy="true"><Loader2 className="h-6 w-6 animate-spin motion-reduce:animate-none" aria-label="Loading" /></div></PublicFrame>;
  }

  const color = booking.page?.color;
  const status = STATUS_TEXT[booking.status];
  const today = dayKey(new Date(), zone);

  return (
    <PublicFrame color={color} testid="manage-booking">
      <div className="mx-auto max-w-3xl overflow-hidden rounded-3xl border border-slate-200/80 bg-white p-5 shadow-[0_1px_2px_rgba(10,22,40,0.04),0_24px_60px_rgba(10,22,40,0.08)] sm:p-8">
        {notice && <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-900" role="alert" data-testid="manage-booking-notice">{notice}</div>}

        {mode === "view" && (
          <div className="space-y-5">
            <div className="flex items-start gap-3">
              {done === "cancelled" || booking.status === "cancelled"
                ? <XCircle className="h-8 w-8 shrink-0 text-slate-400" aria-hidden="true" />
                : <CheckCircle2 className="h-8 w-8 shrink-0 text-emerald-600" aria-hidden="true" />}
              <div>
                <h1 ref={heading} tabIndex={-1} className="font-display text-2xl font-extrabold text-[#0a1628] outline-none" data-testid="manage-booking-title">
                  {done === "moved" ? "Your booking has moved" : done === "cancelled" ? "Your booking is cancelled" : status ? "Your booking" : `See you then${booking.person?.first_name ? `, ${booking.person.first_name}` : ""}`}
                </h1>
                <p className="mt-1 text-sm text-slate-600">{done === "cancelled" ? `We've let ${booking.host_name || "your agent"} know.`
                  : done === "moved" ? `Here's the new time. We've let ${booking.host_name || "your agent"} know.` : status || "Here's your booking."}</p>
              </div>
            </div>
            <SummaryCard booking={booking} zone={zone} testid="manage-booking-summary" />
            {booking.status === "cancelled" ? (
              booking.links?.rebook_url && <a href={booking.links.rebook_url} className="inline-flex h-11 items-center justify-center rounded-xl bg-[var(--brand)] px-5 text-sm font-semibold text-white hover:opacity-90" data-testid="manage-booking-rebook">Book a new time</a>
            ) : (
              <>
                <div>
                  <div className="mb-2 text-sm font-semibold text-[#0a1628]">Add it to your calendar</div>
                  <AddToCalendar links={booking.links} testid="manage-add-to-calendar" />
                </div>
                {booking.can_change && (
                  <div className="flex flex-col gap-2 border-t border-slate-100 pt-5 sm:flex-row">
                    <button type="button" onClick={() => { setMode("reschedule"); setNotice(""); setDone(""); }} data-testid="manage-booking-reschedule"
                      className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-[var(--brand)] px-5 text-sm font-semibold text-white hover:opacity-90">
                      <CalendarClock className="h-4 w-4" aria-hidden="true" />Reschedule
                    </button>
                    <button type="button" onClick={() => { setMode("cancel"); setNotice(""); setDone(""); }} data-testid="manage-booking-cancel"
                      className="inline-flex h-11 items-center justify-center rounded-xl border border-slate-300 bg-white px-5 text-sm font-semibold text-red-700 hover:bg-red-50">
                      Cancel booking
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {mode === "reschedule" && (
          <div>
            <h1 ref={heading} tabIndex={-1} className="font-display text-xl font-bold text-[#0a1628] outline-none">Pick a new time</h1>
            <p className="mb-5 mt-1 text-sm text-slate-600">Now: {formatRange(booking.start_at, booking.end_at, zone)}</p>
            <SlotPicker loadDays={loadDays} zone={zone} onZoneChange={setZone} maxKey={addDays(today, 365)} controlRef={picker}
              selectedStart={newStart} testid="manage-slots" onPick={(value) => { setNewStart(value); setMode("confirm-move"); }} />
            <button type="button" onClick={() => setMode("view")} className="mt-5 text-sm font-semibold text-slate-600 hover:underline" data-testid="manage-reschedule-back">Keep my current time</button>
          </div>
        )}

        {mode === "confirm-move" && newStart && (
          <div className="max-w-lg space-y-4">
            <h1 ref={heading} tabIndex={-1} className="font-display text-xl font-bold text-[#0a1628] outline-none">Move your booking?</h1>
            <div className="rounded-2xl border border-slate-200 p-4 text-sm">
              <div className="text-slate-500 line-through">{formatRange(booking.start_at, booking.end_at, zone)}</div>
              <div className="mt-1 font-semibold text-[#0a1628]">{formatRange(newStart, null, zone)}</div>
              <div className="text-slate-500">{zoneLabel(zone, new Date(newStart))}</div>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <button type="button" onClick={move} disabled={busy} data-testid="manage-confirm-move"
                className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-[var(--brand)] px-5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60">
                {busy && <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}Yes, move it
              </button>
              <button type="button" onClick={() => setMode("reschedule")} className="inline-flex h-11 items-center justify-center rounded-xl border border-slate-300 px-5 text-sm font-semibold text-[#0a1628] hover:bg-slate-50">Choose a different time</button>
            </div>
          </div>
        )}

        {mode === "cancel" && (
          <form onSubmit={cancel} className="max-w-lg space-y-4" data-testid="manage-cancel-form">
            <h1 ref={heading} tabIndex={-1} className="font-display text-xl font-bold text-[#0a1628] outline-none">Cancel your booking?</h1>
            <p className="text-sm text-slate-600">{formatRange(booking.start_at, booking.end_at, zone)}</p>
            <div>
              <label htmlFor="cancel-reason" className="mb-1.5 block text-sm font-semibold text-[#0a1628]">Reason <span className="font-normal text-slate-500">(optional)</span></label>
              <textarea id="cancel-reason" rows={3} value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} data-testid="manage-cancel-reason"
                className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-base outline-none focus:ring-2 focus:ring-[var(--brand)] sm:text-sm" />
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <button type="submit" disabled={busy} data-testid="manage-confirm-cancel"
                className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-red-700 px-5 text-sm font-semibold text-white hover:bg-red-800 disabled:opacity-60">
                {busy && <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}Cancel booking
              </button>
              <button type="button" onClick={() => setMode("view")} className="inline-flex h-11 items-center justify-center rounded-xl border border-slate-300 px-5 text-sm font-semibold text-[#0a1628] hover:bg-slate-50">Keep it</button>
            </div>
          </form>
        )}
      </div>
    </PublicFrame>
  );
}
