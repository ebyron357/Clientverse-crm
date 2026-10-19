import {
  Activity, BadgeCheck, BarChart3, Bell, BookOpenCheck, Boxes, BriefcaseBusiness, CalendarDays,
  CircleDollarSign, ClipboardCheck, FileInput, GitBranch, Globe, Handshake, Headphones,
  Inbox, LayoutDashboard, ListTodo, Mail, MessageSquareText, Phone, Settings, ShieldCheck,
  Sparkles, Terminal, UserPlus, Users, Workflow,
} from "lucide-react";

export const MODULE_STATES = {
  AVAILABLE: "available",
  CONFIGURATION_REQUIRED: "configuration_required",
  CONTRACT_PENDING: "contract_pending",
};

export const CLIENTVERSE_MODULES = [
  { id: "command-center", group: "Command", label: "Command Center", description: "Portfolio metrics, alerts, and priority follow-ups", route: "/dashboard", icon: LayoutDashboard, state: MODULE_STATES.AVAILABLE, contract: "GET /api/dashboard", actions: ["view", "navigate"] },
  { id: "action-center", group: "Command", label: "Action Center", description: "Alerts, approvals, and owned follow-through", route: "/notifications", icon: Bell, state: MODULE_STATES.AVAILABLE, contract: "GET /api/alerts", actions: ["view", "acknowledge", "resolve"] },
  { id: "leads", group: "CRM", label: "Leads", description: "Website leads with their speed-to-lead clock and follow-through", route: "/leads", icon: UserPlus, state: MODULE_STATES.AVAILABLE, contract: "GET /api/leads | GET /api/leads/summary | PATCH /api/leads/{id}", actions: ["view", "respond", "close", "spam"] },
  { id: "tasks", group: "CRM", label: "Tasks", description: "Call-backs and follow-ups: what is overdue, due today and coming up", route: "/tasks", icon: ListTodo, state: MODULE_STATES.AVAILABLE, contract: "GET /api/tasks | GET|PATCH /api/crm/tasks/{id} | POST /api/crm/tasks", actions: ["view", "create", "complete", "reopen", "reschedule", "reassign"] },
  { id: "website-forms", group: "CRM", label: "Website Forms", description: "Real-estate website forms, embed codes and lead automation", route: "/website-forms", icon: Globe, state: MODULE_STATES.AVAILABLE, contract: "GET|POST|PATCH /api/website-forms | POST /api/public/forms/{key}/submit", actions: ["view", "create", "configure", "embed", "test"] },
  { id: "contacts", group: "CRM", label: "Contacts", description: "People and relationship context", route: "/contacts", icon: Users, state: MODULE_STATES.AVAILABLE, contract: "GET|POST /api/contacts", actions: ["view", "create"] },
  { id: "companies", group: "CRM", label: "Companies", description: "Account and commercial context", route: "/companies", icon: BriefcaseBusiness, state: MODULE_STATES.AVAILABLE, contract: "GET|POST /api/companies", actions: ["view", "create"] },
  { id: "deals", group: "CRM", label: "Deals", description: "Qualified revenue opportunities", route: "/deals", icon: CircleDollarSign, state: MODULE_STATES.AVAILABLE, contract: "GET|POST /api/opportunities", actions: ["view", "create", "advance"] },
  { id: "pipelines", group: "CRM", label: "Pipelines", description: "Stage-based revenue movement", route: "/pipeline", icon: GitBranch, state: MODULE_STATES.AVAILABLE, contract: "GET /api/opportunities", actions: ["view", "advance"] },
  { id: "email", group: "Communications", label: "Email", description: "Shared email context and drafting", route: "/communications/email", icon: Mail, state: MODULE_STATES.CONFIGURATION_REQUIRED, contract: "CommunicationMessage service (delivered) + an authorised email provider", actions: [] },
  { id: "inbox", group: "Communications", label: "Unified Inbox", description: "Cross-channel relationship conversations, assignment, and the agent/human boundary", route: "/operations?tab=conversations", icon: Inbox, state: MODULE_STATES.AVAILABLE, contract: "GET|POST /api/conversations", actions: ["view", "create", "assign", "handoff", "consent", "draft", "close"] },
  { id: "sms", group: "Communications", label: "SMS", description: "Consent-aware client messaging", route: "/communications/sms", icon: MessageSquareText, state: MODULE_STATES.CONFIGURATION_REQUIRED, contract: "CommunicationMessage service (delivered) + an authorised SMS provider", actions: [] },
  { id: "calling", group: "Communications", label: "Calling", description: "Call activity and outcomes", route: "/communications/calling", icon: Phone, state: MODULE_STATES.CONTRACT_PENDING, contract: "Call activity service", actions: [] },
  { id: "calendar", group: "Scheduling", label: "Calendar", description: "Booked showings, consultations and calls; booking pages and agents' hours", route: "/scheduling/calendar", icon: CalendarDays, state: MODULE_STATES.AVAILABLE, contract: "GET /api/booking/appointments | GET|POST|PATCH /api/booking/event-types | PUT /api/booking/availability/{email} | POST /api/public/booking/{key}/book", actions: ["view", "book", "reschedule", "cancel", "attended", "no-show", "configure", "embed"] },
  { id: "client-360", group: "Client Success", label: "Client 360", description: "Health, outcomes, commitments, and delivery", route: "/workspaces", icon: BriefcaseBusiness, state: MODULE_STATES.AVAILABLE, contract: "GET /api/workspaces", actions: ["view", "create", "update"] },
  { id: "client-operations", group: "Client Success", label: "Client Operations", description: "Portal, commercial, and playbook workflows", route: "/client-ops", icon: Handshake, state: MODULE_STATES.AVAILABLE, contract: "Client operations endpoint set", actions: ["view", "manage"] },
  { id: "workflows", group: "Automation", label: "Automations", description: "When something happens, do these steps, and stop when the person answers; a receipt for every run", route: "/automations", icon: Workflow, state: MODULE_STATES.AVAILABLE, contract: "GET|POST|PATCH|DELETE /api/automations | POST /api/automations/{id}/status|test | GET /api/automations/{id}/runs", actions: ["view", "create", "configure", "test", "turn on", "turn off", "stop run"] },
  { id: "approvals", group: "Automation", label: "Approvals", description: "Human governance for consequential actions", route: "/operations?tab=approvals", icon: ClipboardCheck, state: MODULE_STATES.AVAILABLE, contract: "GET|POST /api/approval-queue", actions: ["view", "request", "approve", "reject", "cancel"] },
  { id: "revenue", group: "Revenue", label: "Revenue Operations", description: "Forecasting, billing, and revenue intelligence", route: "/revenue", icon: BarChart3, state: MODULE_STATES.CONTRACT_PENDING, contract: "Revenue ledger and forecast services", actions: [] },
  { id: "support", group: "Support", label: "Support", description: "Cases, SLAs, and resolution context", route: "/support", icon: Headphones, state: MODULE_STATES.CONTRACT_PENDING, contract: "Case and SLA services", actions: [] },
  { id: "recovery-proof", group: "Revenue", label: "Recovery Proof", description: "What was recovered, and the records that say so — potential and confirmed reported separately", route: "/proof", icon: BadgeCheck, state: MODULE_STATES.AVAILABLE, contract: "GET /api/proof/portfolio | GET /api/proof/cases/{id} | GET /api/attribution/totals", actions: ["view", "drill-down"] },
  { id: "reporting", group: "Intelligence", label: "Reporting", description: "Explainable operating performance", route: "/intelligence/reporting", icon: BarChart3, state: MODULE_STATES.CONTRACT_PENDING, contract: "Metric and report services", actions: [] },
  { id: "relationship-intelligence", group: "Intelligence", label: "Relationship Intelligence", description: "Scoring, ranking, and explainable recommendations", route: "/intelligence/relationships", icon: Sparkles, state: MODULE_STATES.CONTRACT_PENDING, contract: "Recommendation service v1", actions: [] },
  { id: "migration", group: "Platform", label: "Migration", description: "Governed imports and reconciliation", route: "/platform/migration", icon: FileInput, state: MODULE_STATES.CONTRACT_PENDING, contract: "Import job and reconciliation services", actions: [] },
  { id: "operations", group: "Automation", label: "Operations", description: "Durable work queue, recovery candidates and composed strategies, approvals, conversations, and the external-capability security gate", route: "/operations", icon: Workflow, state: MODULE_STATES.AVAILABLE, contract: "GET /api/work-queue | GET /api/recovery-strategies | GET /api/approval-queue | GET /api/conversations | GET /api/next-best-actions | GET /api/security-gate/status", actions: ["view", "acknowledge", "resolve", "replay", "compose", "approve"] },
  { id: "registries", group: "Platform", label: "Registries", description: "Providers, capabilities, and connected records", route: "/registries", icon: Boxes, state: MODULE_STATES.AVAILABLE, contract: "GET /api/integrations/health", actions: ["view", "configure"] },
  { id: "mcp", group: "Platform", label: "MCP Console", description: "Governed AI tool operations", route: "/mcp", icon: Terminal, state: MODULE_STATES.AVAILABLE, contract: "MCP endpoint set", actions: ["view", "manage"] },
  { id: "audit", group: "Platform", label: "Automation & Audit", description: "Evidence and system activity", route: "/audit", icon: Activity, state: MODULE_STATES.AVAILABLE, contract: "GET /api/audit", actions: ["view"] },
  { id: "team", group: "Platform", label: "Team & Access", description: "Roles and tenant access", route: "/team", icon: ShieldCheck, state: MODULE_STATES.AVAILABLE, contract: "Team endpoint set", actions: ["view", "manage"], adminOnly: true },
  { id: "settings", group: "Platform", label: "Settings", description: "Account and provider configuration", route: "/settings", icon: Settings, state: MODULE_STATES.AVAILABLE, contract: "Settings endpoint set", actions: ["view", "manage"] },
  { id: "knowledge", group: "Platform", label: "Knowledge", description: "Reusable relationship and operating knowledge", route: "/platform/knowledge", icon: BookOpenCheck, state: MODULE_STATES.CONTRACT_PENDING, contract: "Knowledge item service", actions: [] },
];

// Where each module is reached from (the main menu, Settings, or Settings → Coming soon) is
// decided in navigation.js. `group` is the module's operating domain, shown on status pages.
export const getModule = (id) => CLIENTVERSE_MODULES.find((module) => module.id === id);
// Several modules are tabs of a shared page and carry a query string in their route so the
// sidebar can deep-link to them. A pathname never equals such a route, so those entries
// only ever match an exact full-route lookup: a page resolves to the module that owns it
// rather than to whichever of its tabs happens to be listed first.
export const getModuleByRoute = (pathname) =>
  CLIENTVERSE_MODULES.find((module) => module.route === pathname)
  || CLIENTVERSE_MODULES.find((module) => !module.route.includes("?")
    && (pathname === module.route || pathname.startsWith(`${module.route}/`)));
export const isModuleActionable = (module) => module?.state === MODULE_STATES.AVAILABLE;
