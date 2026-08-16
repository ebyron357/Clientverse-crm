import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  LayoutDashboard, GitBranch, Users, BriefcaseBusiness, Boxes, Terminal,
  ShieldCheck, Activity, Bell, CirclePlus, Search, Settings,
} from "lucide-react";
import {
  CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem,
  CommandList, CommandSeparator, CommandShortcut,
} from "@/components/ui/command";

const PAGES = [
  { label: "Command Center", detail: "Portfolio health and priorities", to: "/dashboard", icon: LayoutDashboard },
  { label: "Pipeline", detail: "Revenue opportunities", to: "/pipeline", icon: GitBranch },
  { label: "Directory", detail: "Companies and contacts", to: "/directory", icon: Users },
  { label: "Client Workspaces", detail: "Client 360 operating view", to: "/workspaces", icon: BriefcaseBusiness },
  { label: "Registries", detail: "Connected records and providers", to: "/registries", icon: Boxes },
  { label: "Notifications", detail: "Preferences and digest controls", to: "/notifications", icon: Bell },
  { label: "Settings", detail: "Account, provider, and access configuration", to: "/settings", icon: Settings },
  { label: "Team & Access", detail: "Members, roles, and invitations", to: "/team", icon: ShieldCheck },
  { label: "Automation & Audit", detail: "Events, controls, and evidence", to: "/audit", icon: Activity },
  { label: "MCP Console", detail: "Governed AI and tool operations", to: "/mcp", icon: Terminal },
];

export default function GlobalCommandDialog({ open, onOpenChange, onQuickCreate }) {
  const navigate = useNavigate();

  useEffect(() => {
    const handleKeyDown = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onOpenChange]);

  const go = (to) => {
    onOpenChange(false);
    navigate(to);
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <div className="border-b border-slate-100 bg-gradient-to-r from-[#0a1628] to-[#132038] px-5 py-4 text-white">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Search className="h-4 w-4 text-[#4ac4e0]" />
          Find anything in ClientVerse
        </div>
        <p className="mt-1 text-xs text-slate-300">Jump to a workspace, operating view, or common action.</p>
      </div>
      <CommandInput placeholder="Search pages and actions…" />
      <CommandList className="max-h-[420px] cv-scrollbar">
        <CommandEmpty className="py-10 text-sm text-slate-500">No pages or actions match your search.</CommandEmpty>
        <CommandGroup heading="Create">
          <CommandItem value="create new record quick create" onSelect={() => { onOpenChange(false); onQuickCreate(); }}>
            <CirclePlus className="h-4 w-4 text-[#1a9fbf]" />
            <div className="flex flex-1 flex-col"><span className="font-medium">Quick create</span><span className="text-xs text-slate-500">Company, contact, opportunity, or workspace</span></div>
            <CommandShortcut>Q</CommandShortcut>
          </CommandItem>
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Navigate">
          {PAGES.map(({ label, detail, to, icon: Icon }) => (
            <CommandItem key={to} value={`${label} ${detail}`} onSelect={() => go(to)}>
              <Icon className="h-4 w-4 text-slate-500" />
              <div className="flex flex-1 flex-col"><span className="font-medium">{label}</span><span className="text-xs text-slate-500">{detail}</span></div>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
      <div className="flex items-center justify-between border-t border-slate-100 px-4 py-2 text-[11px] text-slate-400">
        <span>Use ↑ ↓ to navigate · ↵ to open</span>
        <span>Ctrl / ⌘ K to toggle</span>
      </div>
    </CommandDialog>
  );
}
