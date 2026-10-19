import { useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Boxes, BriefcaseBusiness, CirclePlus, GitBranch, Search, Settings2 } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { CLIENTVERSE_MODULES, MODULE_STATES } from "@/platform/modules";
import { MAIN_MENU, SETTINGS_ENTRY, settingsMenuFor } from "@/platform/navigation";
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator, CommandShortcut } from "@/components/ui/command";
import { DialogDescription, DialogTitle } from "@/components/ui/dialog";

const pathOf = (to) => to.split("?")[0];

/** The palette lists what the menus list, in the same words: main menu, Settings, then the rest. */
export default function GlobalCommandDialog({ open, onOpenChange, onQuickCreate }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  useEffect(() => {
    const handleKeyDown = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); onOpenChange(!open); }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "q") { event.preventDefault(); onOpenChange(false); onQuickCreate(); }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onOpenChange, onQuickCreate]);
  const go = (to, state) => { onOpenChange(false); navigate(to, state ? { state } : undefined); };

  const { menu, settings, more, soon } = useMemo(() => {
    const byId = Object.fromEntries(CLIENTVERSE_MODULES.map((module) => [module.id, module]));
    const mainMenu = MAIN_MENU.filter((entry) => !entry.adminOnly || isAdmin);
    const settingsItems = settingsMenuFor(user).filter((group) => !group.soon).flatMap((group) => group.items.map((item) => ({ ...item, group: group.label })));
    // Available pages neither menu lists (Action Center, Companies, Deals).
    const listed = new Set([...mainMenu.map((entry) => pathOf(entry.route)), ...settingsItems.map((item) => pathOf(item.to))]);
    const morePages = CLIENTVERSE_MODULES.filter((module) => module.state === MODULE_STATES.AVAILABLE && (!module.adminOnly || isAdmin) && !listed.has(pathOf(module.route)));
    const pending = CLIENTVERSE_MODULES.filter((module) => module.state !== MODULE_STATES.AVAILABLE);
    return { menu: mainMenu.map((entry) => ({ ...entry, module: byId[entry.id] })), settings: settingsItems, more: morePages, soon: pending };
  }, [isAdmin, user]);

  return <CommandDialog open={open} onOpenChange={onOpenChange}>
    <div className="border-b border-border bg-foreground px-5 py-4 text-background"><DialogTitle className="flex items-center gap-2 text-sm font-semibold leading-5 tracking-normal"><Search className="size-4" aria-hidden="true" />Find anything in ClientVerse</DialogTitle><DialogDescription className="mt-1 text-xs text-background/70">Jump to any page or start something new.</DialogDescription></div>
    <CommandInput placeholder="Search pages and actions…" />
    <CommandList className="cv-scrollbar max-h-[460px]">
      <CommandEmpty className="py-10 text-sm text-muted-foreground">No pages or actions match your search.</CommandEmpty>
      <CommandGroup heading="Top actions">
        <CommandItem value="create opportunity pipeline deal" onSelect={() => go("/pipeline")} data-testid="cmd-create-opportunity">
          <GitBranch className="size-4 text-primary" />
          <div className="flex flex-1 flex-col"><span className="font-medium">Create opportunity</span><span className="text-xs text-muted-foreground">Open pipeline and start a new deal</span></div>
        </CommandItem>
        <CommandItem value="workspaces clients client 360" onSelect={() => go("/workspaces")} data-testid="cmd-workspaces">
          <BriefcaseBusiness className="size-4 text-primary" />
          <div className="flex flex-1 flex-col"><span className="font-medium">Workspaces</span><span className="text-xs text-muted-foreground">Jump to your clients (Client 360)</span></div>
        </CommandItem>
        <CommandItem value="integrations registries providers settings connections" onSelect={() => go("/registries?tab=integrations", { settingsItem: "integrations" })} data-testid="cmd-integrations">
          <Boxes className="size-4 text-primary" />
          <div className="flex flex-1 flex-col"><span className="font-medium">Integrations</span><span className="text-xs text-muted-foreground">Provider connections and their health</span></div>
        </CommandItem>
        <CommandItem value="create new record quick create" onSelect={() => { onOpenChange(false); onQuickCreate(); }}>
          <CirclePlus className="size-4 text-primary" />
          <div className="flex flex-1 flex-col"><span className="font-medium">Quick create</span><span className="text-xs text-muted-foreground">Company, contact, opportunity, or workspace</span></div>
          <CommandShortcut>⌘Q</CommandShortcut>
        </CommandItem>
      </CommandGroup>
      <CommandSeparator />
      <CommandGroup heading="Main menu">
        {[...menu, { ...SETTINGS_ENTRY, module: { description: "Your account, team, forms, connections and audit log" } }].map((entry) => {
          const Icon = entry.icon;
          return <CommandItem key={entry.id} value={`${entry.label} ${entry.module?.label || ""} ${entry.module?.description || ""}`} onSelect={() => go(entry.route)}>
            <Icon className="size-4 text-muted-foreground" />
            <div className="flex flex-1 flex-col"><span className="font-medium">{entry.label}</span><span className="text-xs text-muted-foreground">{entry.module?.description}</span></div>
          </CommandItem>;
        })}
      </CommandGroup>
      <CommandGroup heading="Settings">
        {settings.map((item) => <CommandItem key={item.id} value={`settings ${item.label} ${item.group}`} onSelect={() => go(item.to, { settingsItem: item.id })}>
          <Settings2 className="size-4 text-muted-foreground" />
          <div className="flex flex-1 flex-col"><span className="font-medium">{item.label}</span><span className="text-xs text-muted-foreground">Settings · {item.group}</span></div>
        </CommandItem>)}
      </CommandGroup>
      {more.length > 0 && <CommandGroup heading="More pages">
        {more.map((module) => { const Icon = module.icon; return <CommandItem key={module.id} value={`${module.label} ${module.description}`} onSelect={() => go(module.route)}>
          <Icon className="size-4 text-muted-foreground" />
          <div className="flex flex-1 flex-col"><span className="font-medium">{module.label}</span><span className="text-xs text-muted-foreground">{module.description}</span></div>
        </CommandItem>; })}
      </CommandGroup>}
      <CommandGroup heading="Coming soon">
        {soon.map((module) => { const Icon = module.icon; return <CommandItem key={module.id} value={`${module.label} ${module.description} coming soon`} onSelect={() => go(module.route, { settingsItem: `module-${module.id}` })}>
          <Icon className="size-4 text-muted-foreground" />
          <div className="flex flex-1 flex-col"><span className="flex items-center gap-2 font-medium">{module.label}<span className="rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[9px] font-bold uppercase text-amber-800">{module.state === MODULE_STATES.CONFIGURATION_REQUIRED ? "Configuration required" : "Contract pending"}</span></span><span className="text-xs text-muted-foreground">{module.description}</span></div>
        </CommandItem>; })}
      </CommandGroup>
    </CommandList>
    <div className="flex items-center justify-between border-t border-border px-4 py-2 text-[11px] text-muted-foreground"><span>Use ↑ ↓ to navigate · ↵ to open</span><span>Ctrl / ⌘ K</span></div>
  </CommandDialog>;
}
