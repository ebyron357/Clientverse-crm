// What the app shell shows: the main menu, the Settings menu, and which entry a URL belongs to.
// The module registry (modules.js) stays the list of every module and its route; this file
// decides where each one is reached from, so a page never has to know.

import {
  BriefcaseBusiness, CalendarDays, ChartNoAxesColumn, House, MessageCircle, Settings, ShieldCheck,
  SquareCheckBig, SquareKanban, Users, Workflow, Zap,
} from "lucide-react";
import { CLIENTVERSE_MODULES, getModule, getModuleByRoute, MODULE_STATES } from "@/platform/modules";

const pathOf = (to) => to.split("?")[0];
const tabOf = (search) => new URLSearchParams(search || "").get("tab");
const under = (pathname, path) => pathname === path || pathname.startsWith(`${path}/`);

/**
 * The main menu: the eleven places a customer works from every day, in this order. Each entry
 * opens a module from the registry (its route, state and test id come from there) and owns
 * the paths that light it up. `count` names the badge (see AppShell); `urgent` badges are red.
 * Inbox and Approvals are tabs of /operations, so their `tab` decides, not a path.
 */
const MENU = [
  { module: "command-center", label: "Today", icon: House, paths: ["/dashboard"] },
  { module: "leads", label: "Leads", icon: Zap, paths: ["/leads"], count: "leads", countLabel: "new", urgent: true },
  { module: "inbox", label: "Inbox", icon: MessageCircle, tab: "conversations", count: "inbox", countLabel: "open", urgent: true },
  { module: "contacts", label: "Contacts", icon: Users, paths: ["/contacts", "/companies", "/directory"] },
  { module: "pipelines", label: "Pipeline", icon: SquareKanban, paths: ["/pipeline", "/deals"] },
  { module: "calendar", label: "Calendar", icon: CalendarDays, paths: ["/scheduling/calendar"] },
  { module: "tasks", label: "Tasks", icon: SquareCheckBig, paths: ["/tasks"], count: "tasks", countLabel: "overdue" },
  { module: "approvals", label: "Approvals", icon: ShieldCheck, tab: "approvals", count: "approvals", countLabel: "waiting for a decision" },
  { module: "client-360", label: "Clients", icon: BriefcaseBusiness, paths: ["/workspaces"] },
  { module: "workflows", label: "Automations", icon: Workflow, paths: ["/automations"] },
  { module: "recovery-proof", label: "Reports", icon: ChartNoAxesColumn, paths: ["/proof"] },
];

const isAvailable = (module) => module?.state === MODULE_STATES.AVAILABLE;

/** Main menu entries. A module that is not available (contract pending, configuration required) never shows here. */
export const MAIN_MENU = MENU
  .map((entry) => ({ entry, module: getModule(entry.module) }))
  .filter(({ module }) => isAvailable(module))
  .map(({ entry, module }) => ({ ...entry, id: module.id, route: module.route, adminOnly: Boolean(module.adminOnly), testid: `nav-${module.id}-link` }));

/** Pinned to the bottom of the main menu. */
export const SETTINGS_ENTRY = { id: "settings", label: "Settings", icon: Settings, route: "/settings", testid: "nav-settings-link" };

/** The name a module goes by in the main menu ("Today" for Command Center), or its own. */
export const menuLabel = (module) => MAIN_MENU.find((entry) => entry.id === module?.id)?.label || module?.label;

/**
 * The Settings menu. Items keep the test id the old sidebar gave the same module, so tests
 * written against it still find it. `to` may carry a query; `state.settingsItem` is sent
 * with the link so two items that open the same page each light up when chosen.
 */
const SETTINGS_GROUPS = [
  {
    label: "Workspace",
    items: [
      { id: "general", label: "General", to: "/settings" },
      { id: "templates", label: "Industry template", to: "/settings/templates" },
      { id: "snapshots", label: "Snapshots", to: "/settings/snapshots", adminOnly: true },
      { id: "fields", label: "Fields", to: "/settings/fields" },
      { id: "team", label: "Team and roles", to: "/team", adminOnly: true, testid: "nav-team-link" },
      // TODO: a lead routing page of its own. Until then each form's "Assign the lead"
      // section is where routing is set, so this opens Forms.
      { id: "lead-routing", label: "Lead routing", to: "/website-forms" },
      // Safe rules, playbooks, the client portal and commercial records. Its own page,
      // linked from here now that Automations has the main-menu entry.
      { id: "client-operations", label: "Client portal and playbooks", to: "/client-ops", testid: "nav-client-operations-link" },
    ],
  },
  {
    // An agency's client accounts. A client account does not run client accounts of its own.
    label: "Agency",
    adminOnly: true,
    notInClientAccount: true,
    items: [{ id: "agency", label: "Client accounts", to: "/settings/agency" }],
  },
  {
    label: "Capture",
    items: [
      { id: "forms", label: "Forms", to: "/website-forms", testid: "nav-website-forms-link" },
      { id: "booking-pages", label: "Booking pages", to: "/scheduling/calendar?tab=pages" },
    ],
  },
  {
    label: "Connections",
    items: [
      { id: "integrations", label: "Integrations", to: "/registries?tab=integrations" },
      // The sending switch is on the Gmail row of Integrations.
      { id: "email-sending", label: "Email sending", to: "/registries?tab=integrations" },
    ],
  },
  { label: "Compliance", items: [{ id: "audit", label: "Audit log", to: "/audit", testid: "nav-audit-link" }] },
  {
    label: "Developer",
    adminOnly: true,
    items: [
      { id: "mcp", label: "MCP console", to: "/mcp", testid: "nav-mcp-link" },
      { id: "registries", label: "Registries", to: "/registries", testid: "nav-registries-link" },
      { id: "operations", label: "Operations", to: "/operations", testid: "nav-operations-link" },
    ],
  },
  {
    label: "Coming soon",
    soon: true,
    // Every module that is not available yet; each opens its status page.
    items: CLIENTVERSE_MODULES.filter((module) => !isAvailable(module))
      .map((module) => ({ id: `module-${module.id}`, label: module.label, to: module.route, soon: true, testid: `nav-${module.id}-link` })),
  },
].map((group) => ({ ...group, items: group.items.map((item) => ({ testid: `settings-nav-${item.id}`, ...item })) }));

const ALL_SETTINGS_ITEMS = SETTINGS_GROUPS.flatMap((group) => group.items.map((item) => ({ ...item, adminOnly: item.adminOnly || group.adminOnly })));

/** The Settings menu as this person sees it. */
export function settingsMenuFor(user) {
  const isAdmin = user?.role === "admin";
  const inClientAccount = user?.workspace?.kind === "client" && !user?.acting;
  return SETTINGS_GROUPS
    .filter((group) => isAdmin || !group.adminOnly)
    .filter((group) => !(group.notInClientAccount && inClientAccount))
    .map((group) => ({ ...group, items: group.items.filter((item) => isAdmin || !item.adminOnly) }))
    .filter((group) => group.items.length);
}

// Which Settings item a page belongs to when the link that opened it did not say.
const REGISTRY_TABS = ["mcp-servers", "plugins", "webhooks"];
function defaultSettingsItem(pathname, tab) {
  if (pathname === "/settings") return "general";
  if (pathname === "/settings/fields") return "fields";
  if (pathname === "/settings/templates") return "templates";
  if (pathname === "/settings/snapshots") return "snapshots";
  if (pathname === "/settings/agency") return "agency";
  if (pathname === "/team") return "team";
  if (pathname === "/website-forms") return "forms";
  if (pathname === "/audit") return "audit";
  if (pathname === "/mcp") return "mcp";
  if (pathname === "/registries") return REGISTRY_TABS.includes(tab) ? "registries" : "integrations";
  // Inbox and Approvals are tabs of Operations with places of their own in the main menu.
  if (pathname === "/operations") return ["conversations", "approvals"].includes(tab) ? null : "operations";
  const pending = CLIENTVERSE_MODULES.find((module) => !isAvailable(module) && module.route === pathname);
  return pending ? `module-${pending.id}` : null;
}

/**
 * The Settings item a location belongs to, or null when it is not a Settings page. A link
 * from the Settings menu names its item in the location state; that choice holds while the
 * page stays on the path the item opens.
 */
export function settingsItemFor({ pathname, search, state }) {
  const chosen = ALL_SETTINGS_ITEMS.find((item) => item.id === state?.settingsItem);
  if (chosen && pathOf(chosen.to) === pathname) return chosen;
  const id = defaultSettingsItem(pathname, tabOf(search));
  return ALL_SETTINGS_ITEMS.find((item) => item.id === id) || null;
}

/** The main menu entry a location belongs to ("settings" for every Settings page), or null. */
export function menuEntryFor(location) {
  if (settingsItemFor(location)) return SETTINGS_ENTRY;
  const { pathname, search } = location;
  const tab = tabOf(search);
  return MAIN_MENU.find((entry) => (entry.tab
    ? pathname === pathOf(entry.route) && tab === entry.tab
    : entry.paths.some((path) => under(pathname, path)))) || null;
}

/** Top bar breadcrumb: where the page sits in the menus, then the page when it differs. */
export function breadcrumbFor(location) {
  const settingsItem = settingsItemFor(location);
  if (settingsItem) return [SETTINGS_ENTRY.label, settingsItem.label];
  const entry = menuEntryFor(location);
  const { pathname } = location;
  if (entry) {
    if (entry.tab) return [entry.label];
    if (entry.id === "client-360" && pathname.startsWith("/workspaces/")) return [entry.label, "Client 360"];
    const module = getModuleByRoute(pathname);
    return module && module.id !== entry.id ? [entry.label, module.label] : [entry.label];
  }
  const module = getModuleByRoute(pathname);
  return [module ? menuLabel(module) : "ClientVerse"];
}
