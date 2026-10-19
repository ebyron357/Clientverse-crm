// The ClientVerse mark: an orbit around a client, drawn so it stays crisp at any size.
export default function BrandMark({ className = "size-8" }) {
  return <span className={`inline-flex shrink-0 items-center justify-center rounded-lg bg-brand text-brand-foreground shadow-xs ${className}`} aria-hidden="true">
    <svg viewBox="0 0 24 24" fill="none" className="size-[62%]">
      <circle cx="12" cy="12" r="7.25" stroke="currentColor" strokeOpacity="0.55" strokeWidth="1.75" />
      <circle cx="12" cy="12" r="3" fill="currentColor" />
      <circle cx="18.2" cy="8.4" r="1.9" fill="currentColor" />
    </svg>
  </span>;
}
