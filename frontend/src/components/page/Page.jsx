// Building blocks every in-app screen shares, so pages read as one product:
// a compact header, underline view tabs, a toolbar strip, a stat strip, status dots,
// property lists and titled sections. Layout only: no page logic lives here.

import { cn as cx } from "@/lib/utils";

/** Title row: icon, title, optional count and one line of description; actions on the right. */
export function PageHeader({ icon: Icon, title, count, description, actions, children, className, testid }) {
  return <header className={cx("mb-5", className)} data-testid={testid}>
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <h1 className="flex items-center gap-2 text-xl font-semibold leading-7 tracking-tight text-foreground">
          {Icon && <Icon className="size-[18px] shrink-0 text-muted-foreground" aria-hidden="true" />}
          <span className="truncate">{title}</span>
          {count !== undefined && count !== null && <span className="tabular rounded-md bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground">{count}</span>}
        </h1>
        {description && <p className="mt-0.5 line-clamp-2 max-w-3xl text-[13px] leading-5 text-muted-foreground sm:line-clamp-1">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
    {children && <div className="mt-4">{children}</div>}
  </header>;
}

/**
 * Underline tabs for switching views of one list. `items`: { value, label, count, icon, testid }.
 * Rendered as a tablist of buttons; the caller owns the selected value.
 */
export function ViewTabs({ items, value, onChange, label = "Views", className, trailing }) {
  return <div className={cx("flex items-end justify-between gap-3 border-b border-border", className)}>
    <div role="tablist" aria-label={label} className="-mb-px flex min-w-0 gap-4 overflow-x-auto">
      {items.map(({ value: key, label: text, count, icon: Icon, testid }) => {
        const active = key === value;
        return <button key={key} type="button" role="tab" aria-selected={active} onClick={() => onChange(key)} data-testid={testid}
          className={cx("flex h-9 shrink-0 items-center gap-1.5 border-b-2 px-0.5 text-[13.5px] font-medium transition-colors",
            active ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
          {Icon && <Icon className="size-4" aria-hidden="true" />}
          {text}
          {count !== undefined && count !== null && <span className={cx("tabular rounded px-1 text-xs", active ? "bg-muted text-foreground" : "text-muted-foreground")}>{count}</span>}
        </button>;
      })}
    </div>
    {trailing && <div className="flex shrink-0 items-center gap-2 pb-1.5">{trailing}</div>}
  </div>;
}

/** A row of filters, search and view controls that sits directly above a list or table. */
export function Toolbar({ children, className }) {
  return <div className={cx("flex flex-wrap items-center gap-2 py-3", className)}>{children}</div>;
}

/**
 * Key numbers as one strip divided into cells, rather than a grid of separate cards.
 * `items`: { label, value, detail, tone, onClick, testid }.
 */
export function StatStrip({ items, className }) {
  const toneText = { danger: "text-red-700", warning: "text-amber-700", success: "text-emerald-700", brand: "text-brand" };
  // A <button> may not hold <dt>/<dd>, so a strip with clickable cells is a plain grid of
  // buttons whose text reads "label value detail"; a read-only strip stays a <dl>.
  const clickable = items.some((item) => item.onClick);
  const [Root, Term, Desc] = clickable ? ["div", "span", "span"] : ["dl", "dt", "dd"];
  return <Root className={cx("grid grid-cols-2 overflow-hidden rounded-xl border border-border bg-card sm:grid-cols-4", className)}>
    {items.map(({ label, value, detail, tone, onClick, testid }, index) => {
      const Cell = onClick ? "button" : "div";
      return <Cell key={label} type={onClick ? "button" : undefined} onClick={onClick} data-testid={testid}
        className={cx("flex min-w-0 flex-col items-start gap-1 px-4 py-3.5 text-left",
          index % 2 === 1 && "border-l border-border", index >= 2 && "border-t border-border sm:border-t-0",
          index % 4 !== 0 && "sm:border-l", onClick && "transition-colors hover:bg-muted/50")}>
        <Term className="block text-xs font-medium text-muted-foreground">{label}</Term>
        <Desc className={cx("tabular block max-w-full text-[22px] font-semibold leading-7 tracking-tight [overflow-wrap:anywhere]", toneText[tone] || "text-foreground")}>{value}</Desc>
        {detail && <Desc className="line-clamp-1 block text-xs text-muted-foreground">{detail}</Desc>}
      </Cell>;
    })}
  </Root>;
}

const DOT = { neutral: "bg-muted-foreground/50", brand: "bg-brand", success: "bg-emerald-500", warning: "bg-amber-500", danger: "bg-red-500", info: "bg-sky-500", violet: "bg-violet-500" };

/** Status as a coloured dot and a word: quieter than a filled pill, and readable in both themes. */
export function StatusDot({ tone = "neutral", children, className }) {
  return <span className={cx("inline-flex items-center gap-1.5 whitespace-nowrap text-[13px] text-foreground/80", className)}>
    <span className={cx("size-1.5 shrink-0 rounded-full", DOT[tone] || DOT.neutral)} aria-hidden="true" />{children}
  </span>;
}

/** Label/value rows for a record's details panel. `items`: { label, value, testid }. */
export function PropertyList({ items, className }) {
  return <dl className={cx("divide-y divide-border/70", className)}>
    {items.map(({ label, value, testid }) => <div key={label} className="grid grid-cols-[120px_minmax(0,1fr)] items-start gap-3 py-2 text-[13px]" data-testid={testid}>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words text-foreground">{value ?? <span className="text-muted-foreground">Not set</span>}</dd>
    </div>)}
  </dl>;
}

/** A titled block of a page. Flat by default; `card` gives it a border. */
export function Section({ title, description, actions, children, card = false, className, bodyClassName, testid }) {
  return <section className={cx(card && "rounded-xl border border-border bg-card", className)} data-testid={testid}>
    {(title || actions) && <div className={cx("flex items-center justify-between gap-3", card ? "border-b border-border/80 px-4 py-3" : "mb-3")}>
      <div className="min-w-0">
        {title && <h2 className="text-sm font-semibold tracking-tight text-foreground">{title}</h2>}
        {description && <p className="mt-0.5 line-clamp-1 text-[12.5px] text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>}
    <div className={bodyClassName}>{children}</div>
  </section>;
}

/** Initials in a circle; the colour is stable per name so a person keeps theirs. */
export function Avatar({ name = "", size = "md", className }) {
  const initials = name.split(/\s+/).filter(Boolean).map((part) => part[0]).slice(0, 2).join("").toUpperCase() || "?";
  const palette = ["bg-sky-100 text-sky-800", "bg-violet-100 text-violet-800", "bg-emerald-100 text-emerald-800", "bg-amber-100 text-amber-800", "bg-rose-100 text-rose-800", "bg-indigo-100 text-indigo-800"];
  const hash = [...name].reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const sizes = { sm: "size-6 text-[10px]", md: "size-8 text-xs", lg: "size-11 text-sm" };
  return <span className={cx("inline-flex shrink-0 items-center justify-center rounded-full font-semibold", palette[hash % palette.length], sizes[size] || sizes.md, className)} aria-hidden="true">{initials}</span>;
}
