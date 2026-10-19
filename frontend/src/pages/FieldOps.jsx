import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PageHeader, Section } from "@/components/page/Page";
import { BellPlus, CalendarCheck2, CheckCircle2, Clock3, MapPin, Smartphone } from "lucide-react";

// Field work happens on a phone: every control is a 44px tap target below `sm`, inputs keep a
// 16px font so iOS does not zoom on focus, and the save action stays reachable when the
// on-screen keyboard shortens the viewport.

const RELATIVE = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
function relativeTime(value) {
  const at = value ? new Date(value).getTime() : NaN;
  if (Number.isNaN(at)) return "";
  const minutes = Math.round((at - Date.now()) / 60000);
  const size = Math.abs(minutes);
  if (size < 1) return "just now";
  if (size < 60) return RELATIVE.format(minutes, "minute");
  if (size < 60 * 24) return RELATIVE.format(Math.round(minutes / 60), "hour");
  return RELATIVE.format(Math.round(minutes / (60 * 24)), "day");
}
const timeOfDay = (value) => new Date(value).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });

function DateTile({ value }) {
  const date = new Date(value);
  return (
    <span className="flex size-11 shrink-0 flex-col items-center justify-center rounded-lg border border-border bg-background leading-none" aria-hidden="true">
      <span className="text-[10px] font-medium uppercase text-muted-foreground">{date.toLocaleDateString(undefined, { weekday: "short" })}</span>
      <span className="tabular mt-0.5 text-[15px] font-semibold text-foreground">{date.getDate()}</span>
    </span>
  );
}

function EmptyRow({ icon: Icon, children }) {
  return (
    <div className="flex flex-col items-center px-4 py-10 text-center">
      <span className="flex size-10 items-center justify-center rounded-full bg-muted">
        <Icon className="size-[18px] text-muted-foreground" aria-hidden="true" />
      </span>
      <p className="mt-3 text-[13px] text-muted-foreground">{children}</p>
    </div>
  );
}

const control = "h-11 text-base sm:h-9 sm:text-sm";

export default function FieldOps() {
  const { user } = useAuth();
  const [workspaces, setWorkspaces] = useState([]); const [appointments, setAppointments] = useState([]); const [checkins, setCheckins] = useState([]); const [workspaceId, setWorkspaceId] = useState(""); const [note, setNote] = useState(""); const [location, setLocation] = useState(""); const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false);
  const load = useCallback(async () => { setLoading(true); try { const [ws, appts, visits] = await Promise.all([api.get("/workspaces"), api.get("/appointments"), api.get("/field/check-ins")]); setWorkspaces(ws.data); setAppointments(appts.data); setCheckins(visits.data); setWorkspaceId((current) => current || ws.data[0]?.id || ""); } catch (error) { toast.error("Could not load Field Ops", { description: formatErr(error.response?.data?.detail) }); } finally { setLoading(false); } }, []);
  useEffect(() => { load(); }, [load]);
  const submit = async () => { if (!workspaceId) return; setBusy(true); try { await api.post("/field/check-ins", { workspace_id: workspaceId, note: note || null, location_label: location || null }); toast.success("Field check-in saved"); setNote(""); setLocation(""); load(); } catch (error) { toast.error("Could not save check-in", { description: formatErr(error.response?.data?.detail) }); } finally { setBusy(false); } };
  const prepareReminder = async (item) => { try { await api.post(`/appointments/${item.id}/reminder`); toast.success("Internal reminder task prepared"); load(); } catch (error) { toast.error(formatErr(error.response?.data?.detail)); } };

  if (loading) {
    return (
      <div className="cv-page mx-auto max-w-2xl">
        <div className="animate-pulse rounded-xl border border-border bg-card p-6 text-[13px] text-muted-foreground" role="status">Loading mobile field workspace…</div>
      </div>
    );
  }

  const upcoming = appointments.filter((item) => ["scheduled", "confirmed"].includes(item.status)).slice(0, 8);
  const recent = checkins.slice(0, 6);

  return (
    <div className="cv-page mx-auto max-w-2xl" data-testid="field-ops-page">
      <PageHeader icon={Smartphone} title="Field Ops"
                  description="Onsite check-ins and upcoming visits. Photo uploads need a configured storage provider." />

      <div className="space-y-7">
        <section className="rounded-xl border border-border bg-card" aria-labelledby="field-check-in-title">
          <div className="flex items-center gap-2 border-b border-border/80 px-4 py-3">
            <MapPin className="size-4 text-muted-foreground" aria-hidden="true" />
            <h2 id="field-check-in-title" className="text-sm font-semibold tracking-tight text-foreground">Check in to a client workspace</h2>
          </div>
          <div className="space-y-4 p-4">
            <div className="grid gap-1.5">
              <Label htmlFor="field-workspace" className="text-[13px]">Workspace</Label>
              <Select value={workspaceId} onValueChange={setWorkspaceId}>
                <SelectTrigger id="field-workspace" aria-label="Workspace for field check-in" className={control}><SelectValue /></SelectTrigger>
                <SelectContent>{workspaces.map((workspace) => <SelectItem key={workspace.id} value={workspace.id} className="py-2.5 sm:py-1.5">{workspace.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="field-location" className="text-[13px]">Location label</Label>
              <div className="relative">
                <MapPin className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
                <Input id="field-location" value={location} onChange={(event) => setLocation(event.target.value)} placeholder="e.g. 214 West Trade Street"
                       className={`${control} pl-9`} autoComplete="street-address" enterKeyHint="next" />
              </div>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="field-note" className="text-[13px]">Onsite note</Label>
              <Textarea id="field-note" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Arrival, completion, access, or customer notes"
                        className="min-h-[104px] bg-card text-base sm:min-h-[80px] sm:text-sm" />
            </div>
          </div>
          {/* Sticks to the bottom of the screen while the form runs past it (a phone with the
              keyboard open); on a wider screen it is the card's footer. */}
          <div className="sticky bottom-0 z-10 rounded-b-xl border-t border-border bg-card/95 px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 backdrop-blur sm:static sm:flex sm:items-center sm:justify-between sm:bg-muted/30 sm:pb-3">
            <p className="hidden text-xs text-muted-foreground sm:block">Recorded under your account, with the time.</p>
            <Button onClick={submit} disabled={busy || !workspaceId} className="h-11 w-full text-[15px] sm:h-8 sm:w-auto sm:text-xs">
              <CheckCircle2 aria-hidden="true" />{busy ? "Saving…" : "Save check-in"}
            </Button>
          </div>
        </section>

        <Section title={<span className="flex items-center gap-2">Upcoming appointments{upcoming.length ? <span className="tabular font-normal text-muted-foreground">{upcoming.length}</span> : null}</span>}>
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            {upcoming.length ? (
              <ul className="divide-y divide-border/70">
                {upcoming.map((item) => (
                  <li className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:gap-3" key={item.id}>
                    <div className="flex min-w-0 flex-1 items-center gap-3">
                      <DateTile value={item.start_at} />
                      <div className="min-w-0">
                        <div className="line-clamp-2 text-[14px] font-medium leading-5 text-foreground sm:text-[13px]">{item.title}</div>
                        <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                          <Clock3 className="size-3.5 shrink-0" aria-hidden="true" />
                          <time className="tabular" dateTime={item.start_at} title={new Date(item.start_at).toLocaleString()}>
                            {timeOfDay(item.start_at)} · {relativeTime(item.start_at)}
                          </time>
                        </div>
                      </div>
                    </div>
                    <Button size="sm" variant="outline" className="ml-14 h-11 self-start px-4 text-sm sm:ml-0 sm:h-8 sm:self-auto sm:px-3 sm:text-xs" onClick={() => prepareReminder(item)}>
                      <BellPlus aria-hidden="true" />Prepare reminder
                    </Button>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyRow icon={CalendarCheck2}>No upcoming appointments are assigned in this tenant.</EmptyRow>
            )}
          </div>
        </Section>

        <Section title="Recent field activity">
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            {recent.length ? (
              <ol className="divide-y divide-border/70">
                {recent.map((item) => (
                  <li className="flex gap-3 px-4 py-3" key={item.id}>
                    <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground" aria-hidden="true">
                      <MapPin className="size-3.5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="truncate text-[13px] font-medium text-foreground">{item.location_label || "Client workspace check-in"}</span>
                        <time className="tabular shrink-0 text-xs text-muted-foreground" dateTime={item.created_at} title={new Date(item.created_at).toLocaleString()}>
                          {relativeTime(item.created_at)}
                        </time>
                      </div>
                      <p className="mt-0.5 text-[13px] leading-5 text-foreground/80">{item.note || <span className="text-muted-foreground">No note provided</span>}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {new Date(item.created_at).toLocaleString()} · {item.actor === user?.email ? "You" : "Team member"}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <EmptyRow icon={MapPin}>No field check-ins yet.</EmptyRow>
            )}
          </div>
        </Section>
      </div>
    </div>
  );
}
