import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { CirclePlus, Search } from "lucide-react";
import { CLIENTVERSE_MODULES, MODULE_GROUPS, MODULE_STATES } from "@/platform/modules";
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator, CommandShortcut } from "@/components/ui/command";

export default function GlobalCommandDialog({ open, onOpenChange, onQuickCreate }) {
  const navigate = useNavigate();
  useEffect(() => {
    const handleKeyDown = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); onOpenChange(!open); }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "q") { event.preventDefault(); onOpenChange(false); onQuickCreate(); }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onOpenChange, onQuickCreate]);
  const go = (to) => { onOpenChange(false); navigate(to); };

  return <CommandDialog open={open} onOpenChange={onOpenChange}>
    <div className="border-b border-border bg-foreground px-5 py-4 text-background"><div className="flex items-center gap-2 text-sm font-semibold"><Search className="size-4" />Find anything in ClientVerse</div><p className="mt-1 text-xs text-background/70">Navigate the complete relationship operating system architecture.</p></div>
    <CommandInput placeholder="Search modules and actions…" />
    <CommandList className="cv-scrollbar max-h-[460px]">
      <CommandEmpty className="py-10 text-sm text-muted-foreground">No modules or actions match your search.</CommandEmpty>
      <CommandGroup heading="Create"><CommandItem value="create new record quick create" onSelect={() => { onOpenChange(false); onQuickCreate(); }}><CirclePlus className="size-4 text-primary" /><div className="flex flex-1 flex-col"><span className="font-medium">Quick create</span><span className="text-xs text-muted-foreground">Company, contact, opportunity, or workspace</span></div><CommandShortcut>⌘Q</CommandShortcut></CommandItem></CommandGroup>
      <CommandSeparator />
      {MODULE_GROUPS.map((group) => <CommandGroup key={group} heading={group}>{CLIENTVERSE_MODULES.filter((module) => module.group === group).map((module) => { const Icon = module.icon; const pending = module.state !== MODULE_STATES.AVAILABLE; return <CommandItem key={module.id} value={`${module.label} ${module.description} ${group}`} onSelect={() => go(module.route)}><Icon className="size-4 text-muted-foreground" /><div className="flex flex-1 flex-col"><span className="flex items-center gap-2 font-medium">{module.label}{pending && <span className="rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[9px] font-bold uppercase text-amber-800">Contract pending</span>}</span><span className="text-xs text-muted-foreground">{module.description}</span></div></CommandItem>; })}</CommandGroup>)}
    </CommandList>
    <div className="flex items-center justify-between border-t border-border px-4 py-2 text-[11px] text-muted-foreground"><span>Use ↑ ↓ to navigate · ↵ to open</span><span>Ctrl / ⌘ K</span></div>
  </CommandDialog>;
}
