/* Search the address book and attach people to a deal. Typing a name nobody has yet
   offers to add them as a new contact, so a buyer who rang in can be put on a deal
   without leaving the pipeline. */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, formatErr } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Search, UserPlus, X } from "lucide-react";

export default function ContactPicker({ id, selected, onChange, linkContacts = false, testId = "deal-contacts" }) {
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
    <div className="space-y-2" data-testid={testId}>
      {chosen.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {chosen.map((contact) => (
            <li key={contact.id} className="inline-flex max-w-full items-center gap-1 rounded-full border border-slate-200 bg-slate-50 py-0.5 pl-2.5 pr-1 text-xs font-semibold text-foreground">
              {linkContacts
                ? <Link to={`/contacts?contact=${encodeURIComponent(contact.id)}`} className="truncate text-brand hover:underline" data-testid={`deal-contact-link-${contact.id}`}>{contact.name}</Link>
                : <span className="truncate">{contact.name}</span>}
              <button type="button" onClick={() => remove(contact.id)} className="rounded-full p-0.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700" aria-label={`Remove ${contact.name} from this deal`} data-testid={`deal-contact-remove-${contact.id}`}>
                <X className="h-3 w-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
        <Input id={id} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search your contacts" className="pl-8" autoComplete="off" data-testid={`${testId}-search`} />
      </div>
      {query.trim() && (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          {available.map((contact) => (
            <button key={contact.id} type="button" onClick={() => add(contact)} className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-slate-50" data-testid={`${testId}-option-${contact.id}`}>
              <span className="truncate font-medium text-foreground">{contact.name || "Unnamed contact"}</span>
              <span className="truncate text-xs text-slate-500">{contact.email || contact.phone || ""}</span>
            </button>
          ))}
          {!searching && !available.length && !exact && <div className="px-3 py-2 text-xs text-slate-500">No contact matches “{query.trim()}”.</div>}
          {searching && !available.length && <div className="px-3 py-2 text-xs text-slate-500">Searching…</div>}
          {!exact && (
            <button type="button" onClick={createContact} disabled={adding} className="flex w-full items-center gap-2 border-t border-slate-100 px-3 py-2 text-left text-sm font-semibold text-brand hover:bg-brand-soft disabled:opacity-60" data-testid={`${testId}-create`}>
              <UserPlus className="h-4 w-4" />{adding ? "Adding…" : `Add “${query.trim()}” as a new contact`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
