/* Pieces the public booking page and the person's manage page share.

   These pages live outside the signed-in app and may be framed on an agent's website, so
   nothing here links into the app: every link is a plain <a> to a public page or file. */
import { useEffect } from "react";
import { Building2, CalendarPlus, Clock, Copy, Download, Home, MapPin, Phone, UserRound, Video } from "lucide-react";
import { toast } from "sonner";
import { brandStyle } from "@/components/booking/SlotPicker";
import { formatRange, zoneLabel } from "@/lib/booking";

const LOCATION_ICON = { property: Home, office: Building2, phone: Phone, video: Video };

export function LocationLine({ location, className = "" }) {
  if (!location?.kind) return null;
  const Icon = LOCATION_ICON[location.kind] || MapPin;
  return (
    <div className={`flex items-start gap-2.5 ${className}`}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />
      <div className="min-w-0">
        <div className="font-semibold text-foreground">{location.label}</div>
        {location.text && <div className="break-words text-slate-600">{location.text}</div>}
      </div>
    </div>
  );
}

/** The page shell: a calm background, or nothing at all when framed (?embed=1), and the
    framed page's height posted to the parent so the embed script can size its iframe. */
export function PublicFrame({ embed, color, children, testid }) {
  useEffect(() => {
    if (!embed) return undefined;
    // Framed on an agent's site: let their page show through around the card.
    document.documentElement.style.background = "transparent";
    document.body.style.background = "transparent";
    return undefined;
  }, [embed]);
  useEffect(() => {
    if (!embed || typeof ResizeObserver === "undefined") return undefined;
    const post = () => {
      try { window.parent.postMessage({ type: "clientverse:booking:height", height: document.documentElement.scrollHeight }, "*"); } catch { /* not framed */ }
    };
    const observer = new ResizeObserver(post);
    observer.observe(document.body);
    post();
    return () => observer.disconnect();
  }, [embed]);
  return (
    <div style={brandStyle(color)} data-testid={testid}
      className={embed ? "min-h-0 bg-transparent px-2 py-2" : "min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--booking-accent-soft),_hsl(var(--canvas))_55%)] px-3 py-6 sm:px-6 sm:py-12"}>
      <main className="mx-auto w-full max-w-5xl">{children}</main>
    </div>
  );
}

export function SummaryCard({ booking, zone, testid = "booking-summary" }) {
  const shownZone = zone || booking.timezone;
  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 text-sm sm:p-5" data-testid={testid}>
      <div className="font-display text-lg font-semibold text-foreground">{booking.title}</div>
      <div className="flex items-start gap-2.5">
        <Clock className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />
        <div>
          <div className="font-semibold text-foreground">{formatRange(booking.start_at, booking.end_at, shownZone)}</div>
          <div className="text-slate-500">{zoneLabel(shownZone, new Date(booking.start_at))}{booking.duration_minutes ? ` · ${booking.duration_minutes} minutes` : ""}</div>
        </div>
      </div>
      <LocationLine location={booking.location} />
      {booking.host_name && (
        <div className="flex items-start gap-2.5"><UserRound className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" /><div><span className="font-semibold text-foreground">{booking.host_name}</span></div></div>
      )}
    </div>
  );
}

export function AddToCalendar({ links, testid = "add-to-calendar" }) {
  if (!links?.google_calendar_url && !links?.ics_url) return null;
  return (
    <div className="flex flex-col gap-2 sm:flex-row" data-testid={testid}>
      {links.google_calendar_url && (
        <a href={links.google_calendar_url} target="_blank" rel="noreferrer" data-testid={`${testid}-google`}
          className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 text-sm font-semibold text-foreground hover:bg-slate-50">
          <CalendarPlus className="h-4 w-4" aria-hidden="true" />Google Calendar
        </a>
      )}
      {links.ics_url && (
        <a href={links.ics_url} download data-testid={`${testid}-ics`}
          className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 text-sm font-semibold text-foreground hover:bg-slate-50">
          <Download className="h-4 w-4" aria-hidden="true" />Apple, Outlook (.ics)
        </a>
      )}
    </div>
  );
}

export function ManageLink({ url, newTab = false, testid = "manage-link" }) {
  if (!url) return null;
  const copy = async () => {
    try { await navigator.clipboard.writeText(url); toast.success("Link copied"); } catch { toast.error("Copy the link from the address shown"); }
  };
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm" data-testid={testid}>
      <div className="font-semibold text-foreground">Need to change it?</div>
      <p className="mt-1 text-slate-600">Keep this link — it's how you reschedule or cancel.</p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        {/* A framed page opens it in a new tab: the manage page itself is never framed. */}
        <a href={url} target={newTab ? "_blank" : undefined} rel={newTab ? "noreferrer" : undefined} className="inline-flex h-11 items-center justify-center rounded-lg bg-[var(--booking-accent)] px-4 text-sm font-semibold text-white hover:opacity-90" data-testid={`${testid}-open`}>Reschedule or cancel</a>
        <button type="button" onClick={copy} className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 text-sm font-semibold text-foreground hover:bg-slate-50" data-testid={`${testid}-copy`}>
          <Copy className="h-4 w-4" aria-hidden="true" />Copy link
        </button>
      </div>
    </div>
  );
}

export function PublicMessage({ title, children, testid = "public-message" }) {
  return (
    <div className="mx-auto max-w-lg rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm" data-testid={testid} role="status">
      <h1 className="font-display text-2xl font-semibold text-foreground">{title}</h1>
      <div className="mt-2 text-sm leading-6 text-slate-600">{children}</div>
    </div>
  );
}
