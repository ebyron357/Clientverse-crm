import BrandMark from "@/components/BrandMark";
import { CalendarCheck2, CircleCheck, Globe, PhoneCall } from "lucide-react";

// The frame every signed-out screen shares: the form on the left, and on wide screens a
// quiet illustration of what ClientVerse does on the right. The illustration uses
// capabilities the product has (website forms, booking, tasks); it shows no figures.
export default function AuthLayout({ children, footer }) {
  return <div className="min-h-screen bg-background lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.08fr)]">
    <div className="flex min-h-screen flex-col px-5 py-6 sm:px-10">
      <a href="/login" className="inline-flex w-fit items-center gap-2.5 rounded-md" aria-label="ClientVerse">
        <BrandMark className="size-8" />
        <span className="text-[15px] font-semibold tracking-tight text-foreground">ClientVerse</span>
      </a>
      <main className="flex flex-1 items-center justify-center py-10">
        <div className="w-full max-w-[380px]">{children}</div>
      </main>
      {footer && <div className="text-center text-xs text-muted-foreground">{footer}</div>}
    </div>
    <aside className="relative hidden p-3 lg:block" aria-hidden="true">
      <div className="relative flex h-full flex-col justify-center overflow-hidden rounded-2xl bg-canvas px-12 py-14 xl:px-16">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_50%_at_75%_15%,hsl(var(--brand)/0.14),transparent_70%),radial-gradient(45%_40%_at_10%_95%,hsl(var(--brand)/0.10),transparent_70%)]" />
        <div className="relative max-w-[520px]">
          <p className="text-[13px] font-medium text-brand">Lead follow-through</p>
          <h2 className="mt-3 text-[34px] font-semibold leading-[1.15] tracking-tight text-foreground">Every enquiry answered. Every next step on the calendar.</h2>
          <p className="mt-4 text-[15px] leading-7 text-muted-foreground">Website forms, bookings and follow-ups land in one place, so your team always knows who to call next.</p>
          <ProductPreview />
        </div>
      </div>
    </aside>
  </div>;
}

function ProductPreview() {
  const rows = [
    { icon: Globe, tone: "bg-brand-soft text-brand", title: "New website enquiry", detail: "Viewing request · Contact form", tag: "Lead" },
    { icon: CalendarCheck2, tone: "bg-emerald-50 text-emerald-700", title: "Showing booked", detail: "Thursday, 10:30 · Online booking", tag: "Calendar" },
    { icon: PhoneCall, tone: "bg-amber-50 text-amber-700", title: "Call back due today", detail: "Assigned to you", tag: "Task" },
  ];
  const stages = ["Lead", "Qualified", "Proposal", "Won"];
  return <div className="mt-10 rounded-xl border border-border bg-card p-1.5 shadow-[0_24px_48px_-24px_rgb(16_24_40/0.25)]">
    <div className="flex items-center justify-between px-3 py-2.5">
      <span className="text-[13px] font-semibold text-foreground">Today</span>
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground"><CircleCheck className="size-3.5 text-emerald-600" />Up to date</span>
    </div>
    <ul className="divide-y divide-border/70 rounded-lg border border-border/70">
      {rows.map(({ icon: Icon, tone, title, detail, tag }) => <li key={title} className="flex items-center gap-3 px-3 py-3">
        <span className={`flex size-8 shrink-0 items-center justify-center rounded-md ${tone}`}><Icon className="size-4" /></span>
        <span className="min-w-0 flex-1"><span className="block truncate text-[13px] font-medium text-foreground">{title}</span><span className="block truncate text-xs text-muted-foreground">{detail}</span></span>
        <span className="rounded-full border border-border px-2 py-0.5 text-[11px] font-medium text-muted-foreground">{tag}</span>
      </li>)}
    </ul>
    <div className="grid grid-cols-4 gap-1.5 p-1.5 pt-3">
      {stages.map((stage, index) => <div key={stage} className="rounded-md bg-muted/70 px-2.5 py-2">
        <div className="text-[11px] font-medium text-muted-foreground">{stage}</div>
        <div className={`mt-2 h-1.5 rounded-full ${index === 3 ? "bg-emerald-500/70" : "bg-brand/70"}`} style={{ width: `${88 - index * 18}%` }} />
      </div>)}
    </div>
  </div>;
}
