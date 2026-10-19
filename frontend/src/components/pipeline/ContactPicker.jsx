/* Search the address book and attach people to a deal. Typing a name nobody has yet
   offers to add them as a new contact, so a buyer who rang in can be put on a deal
   without leaving the pipeline. `compact` gives the smaller control the deal record's
   properties panel uses. */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr } from "@/lib/api";
import { Avatar } from "@/components/page/Page";
import { Input } from "@/components/ui/input";
import { Search, UserPlus, X } from "lucide-react";

export default function ContactPicker({ id, selected, onChange, linkContacts = false, compact = false, testId = "deal-contacts" }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [adding, setAdding] = useState(false);
  const chosen = selected || [];

  useEffect(() => {
    const term = query.trim();
    if (!term) { setResults([]); return undefined; }
    let cancelled = false;
    setSearching(true);
    const timer = setTimeout(async () => {
      try {
        const { data } = await api.get("/contacts", { params: { q: term, limit: 8 } });
        if (!cancelled) setResults(Array.isArray(data) ? data : []);
      } catch {
        if (!cancelled) setResults([]);
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query]);

  const add = (contact) => {
    if (!chosen.some((item) => item.id === contact.id)) onChange([...chosen, { id: contact.id, name: contact.name || contact.email || "Unnamed contact" }]);
    setQuery(""); setResults([]);
  };
  const remove = (contactId) => onChange(chosen.filter((item) => item.id !== contactId));

  const createContact = async () => {
    const name = query.trim();
    if (!name) return;
    setAdding(true);
    try {
      const { data } = await api.post("/contacts", { name });
      add(data);
      toast.success(`${name} added to your contacts`);
    } catch (requestError) {
      toast.error("Could not add that contact", { description: formatErr(requestError.response?.data?.detail) });
    } finally { setAdding(false); }
  };

  const available = results.filter((contact) => !chosen.some((item) => item.id === contact.id));
  const exact = results.some((contact) => (contact.name || "").trim().toLowerCase() === query.trim().toLowerCase());

  return (
    <div className="min-w-0 space-y-1.5" data-testid={testId}>
      {chosen.length > 0 && (
        <ul className="flex flex-wrap gap-1">
          {chosen.map((contact) => (
            <li key={contact.id} className="inline-flex h-6 max-w-full items-center gap-1 rounded-md border border-border bg-muted/50 pl-1 pr-0.5 text-xs font-medium text-foreground">
              <Avatar name={contact.name} size="sm" className="!size-4 !text-[8px]" />
              {linkContacts
                ? <Link to={`/contacts?contact=${encodeURIComponent(contact.id)}`} className="truncate hover:text-brand hover:underline" data-testid={`deal-contact-link-${contact.id}`}>{contact.name}</Link>
                : <span className="truncate">{contact.name}</span>}
              <button type="button" onClick={() => remove(contact.id)} className="flex size-5 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent hover:text-foreground" aria-label={`Remove ${contact.name} from this deal`} data-testid={`deal-contact-remove-${contact.id}`}>
                <X className="size-3" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
        <Input id={id} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search your contacts" className={compact ? "h-8 pl-8 text-[13px] md:text-[13px]" : "h-9 pl-8 text-[13px] md:text-[13px]"} autoComplete="off" data-testid={`${testId}-search`} />
      </div>
      {query.trim() && (
        <div className="overflow-hidden rounded-lg border border-border bg-popover py-1 shadow-xs">
          {available.map((contact) => (
            <button key={contact.id} type="button" onClick={() => add(contact)} className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[13px] transition-colors hover:bg-muted/60" data-testid={`${testId}-option-${contact.id}`}>
              <Avatar name={contact.name || ""} size="sm" className="!size-5 !text-[9px]" />
              <span className="min-w-0 flex-1 truncate font-medium text-foreground">{contact.name || "Unnamed contact"}</span>
              <span className="max-w-[45%] truncate text-xs text-muted-foreground">{contact.email || contact.phone || ""}</span>
            </button>
          ))}
          {!searching && !available.length && !exact && <div className="px-2.5 py-1.5 text-xs text-muted-foreground">No contact matches “{query.trim()}”.</div>}
          {searching && !available.length && <div className="px-2.5 py-1.5 text-xs text-muted-foreground">Searching…</div>}
          {!exact && (
            <button type="button" onClick={createContact} disabled={adding} className="mt-1 flex w-full items-center gap-2 border-t border-border px-2.5 pb-1 pt-2 text-left text-[13px] font-medium text-brand transition-colors hover:bg-brand-soft disabled:opacity-60" data-testid={`${testId}-create`}>
              <UserPlus className="size-3.5 shrink-0" aria-hidden="true" /><span className="truncate">{adding ? "Adding…" : `Add “${query.trim()}” as a new contact`}</span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
