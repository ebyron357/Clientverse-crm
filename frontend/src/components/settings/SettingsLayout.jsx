// The Settings hub: the Settings menu on the left, the chosen page on the right. App.js puts
// every page that lives only under Settings inside it; pages that are also reached from the
// main menu (Calendar, Operations) are linked from the menu and keep their own layout.

import { useEffect, useMemo, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { ChevronDown } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { settingsItemFor, settingsMenuFor } from "@/platform/navigation";
import { cn } from "@/lib/utils";

export function SettingsMenu({ className }) {
  const { user } = useAuth();
  const location = useLocation();
  const groups = useMemo(() => settingsMenuFor(user), [user]);
  const current = settingsItemFor(location);
  // On a narrow screen the menu folds into one button naming the current item.
  const [open, setOpen] = useState(false);
  useEffect(() => { setOpen(false); }, [location.pathname, location.search]);

  return <div className={cn("lg:sticky lg:top-[84px] lg:w-[220px] lg:shrink-0", className)}>
    <button type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-controls="settings-menu"
      className="flex h-10 w-full items-center gap-2 rounded-lg border border-border bg-card px-3 text-left text-[13px] lg:hidden" data-testid="settings-menu-toggle">
      <span className="font-semibold text-foreground">Settings</span>
      {current && <span className="min-w-0 flex-1 truncate text-muted-foreground">{current.label}</span>}
      <ChevronDown className={cn("ml-auto size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} aria-hidden="true" />
    </button>
    <nav id="settings-menu" aria-label="Settings" data-testid="settings-menu"
      className={cn("cv-card cv-scrollbar mt-2 px-2 pb-3 pt-1 lg:mt-0 lg:block lg:max-h-[calc(100vh-108px)] lg:overflow-y-auto", open ? "block" : "hidden")}>
      {groups.map((group) => <div key={group.label}>
        <div className="px-2.5 pb-1 pt-3 text-[11px] font-bold uppercase tracking-[0.06em] text-muted-foreground">{group.label}</div>
        <ul className="flex flex-col gap-px">
          {group.items.map((item) => {
            const active = current?.id === item.id;
            return <li key={item.id}>
              <Link to={item.to} state={{ settingsItem: item.id }} aria-current={active ? "page" : undefined} data-testid={item.testid}
                className={cn("flex h-8 items-center rounded-lg px-2.5 text-[13.5px] transition-colors",
                  active ? "bg-brand-soft font-bold text-brand-strong"
                    : item.soon ? "font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
                      : "font-semibold text-foreground/80 hover:bg-muted hover:text-foreground")}>
                <span className="truncate">{item.label}</span>
              </Link>
            </li>;
          })}
        </ul>
      </div>)}
    </nav>
  </div>;
}

export default function SettingsLayout() {
  return <div className="cv-page" data-testid="settings-layout">
    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:gap-6">
      <SettingsMenu />
      <div className="cv-settings-content min-w-0 flex-1"><Outlet /></div>
    </div>
  </div>;
}
