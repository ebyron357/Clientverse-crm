/** Shown while a page's chunk downloads; the same quiet placeholder the pages use. */
export default function PageLoading() {
  return <div className="mx-auto w-full max-w-6xl px-4 sm:px-6" role="status" aria-live="polite">
    <span className="sr-only">Loading…</span>
    <div className="h-7 w-48 animate-pulse rounded-lg bg-muted" />
    <div className="mt-4 h-24 w-full animate-pulse rounded-xl bg-muted" />
  </div>;
}
