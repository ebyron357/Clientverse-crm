import {
  Activity, BarChart3, Bell, BookOpenCheck, Boxes, BriefcaseBusiness, CalendarDays,
  CircleDollarSign, ClipboardCheck, FileInput, GitBranch, Handshake, Headphones,
  Inbox, LayoutDashboard, Mail, MessageSquareText, Phone, Settings, ShieldCheck,
  Sparkles, Terminal, Users, Workflow,
} from "lucide-react";

export const MODULE_STATES = {
  AVAILABLE: "available",
  CONFIGURATION_REQUIRED: "configuration_required",
  CONTRACT_PENDING: "contract_pending",
};

export const CLIENTVERSE_MODULES = [
  { id: "command-center", group: "Command", label: "Command Center", description: "Portfolio priorities and next best actions", route: "/dashboard", icon: LayoutDashboard, state: MODULE_STATES.AVAILABLE, contract: "GET /api/dashboard", actions: ["view", "navigate"] },
  { id: "action-center", group: "Command", label: "Action Center", description: "Alerts, approvals, and owned follow-through", route: "/notifications", icon: Bell, state: MODULE_STATES.AVAILABLE, contract: "GET /api/alerts", actions: ["view", "acknowledge", "resolve"] },
  { id: "contacts", group: "CRM", label: "Contacts", description: "People and relationship context", route: "/contacts", icon: Users, state: MODULE_STATES.AVAILABLE, contract: "GET|POST /api/contacts", actions: ["view", "create"] },
  { id: "companies", group: "CRM", label: "Companies", description: "Account and commercial context", route: "/companies", icon: BriefcaseBusiness, state: MODULE_STATES.AVAILABLE, contract: "GET|POST /api/companies", actions: ["view", "create"] },
  { id: "deals", group: "CRM", label: "Deals", description: "Qualified revenue opportunities", route: "/deals", icon: CircleDollarSign, state: MODULE_STATES.AVAILABLE, contract: "GET|POST /api/opportunities", actions: ["view", "create", "advance"] },
  { id: "pipelines", group: "CRM", label: "Pipelines", description: "Stage-based revenue movement", route: "/pipeline", icon: GitBranch, state: MODULE_STATES.AVAILABLE, contract: "GET /api/opportunities", actions: ["view", "advance"] },
  { id: "email", group: "Communications", label: "Email", description: "Shared email context and drafting", route: "/communications/email", icon: Mail, state: MODULE_STATES.CONTRACT_PENDING, contract: "CommunicationMessage service", actions: [] },
  { id: "inbox", group: "Communications", label: "Unified Inbox", description: "Cross-channel relationship conversations", route: "/communications/inbox", icon: Inbox, state: MODULE_STATES.CONTRACT_PENDING, contract: "Conversation service", actions: [] },
  { id: "sms", group: "Communications", label: "SMS", description: "Consent-aware client messaging", route: "/communications/sms", icon: MessageSquareText, state: MODULE_STATES.CONTRACT_PENDING, contract: "Message delivery service", actions: [] },
  { id: "calling", group: "Communications", label: "Calling", description: "Call activity and outcomes", route: "/communications/calling", icon: Phone, state: MODULE_STATES.CONTRACT_PENDING, contract: "Call activity service", actions: [] },
  { id: "calendar", group: "Scheduling", label: "Calendar", description: "Meetings and relationship moments", route: "/scheduling/calendar", icon: CalendarDays, state: MODULE_STATES.CONTRACT_PENDING, contract: "Calendar event service", actions: [] },
  { id: "client-360", group: "Client Success", label: "Client 360", description: "Health, outcomes, commitments, and delivery", route: "/workspaces", icon: BriefcaseBusiness, state: MODULE_STATES.AVAILABLE, contract: "GET /api/workspaces", actions: ["view", "create", "update"] },
  { id: "client-operations", group: "Client Success", label: "Client Operations", description: "Portal, commercial, and playbook workflows", route: "/client-ops", icon: Handshake, state: MODULE_STATES.AVAILABLE, contract: "Client operations endpoint set", actions: ["view", "manage"] },
  { id: "workflows", group: "Automation", label: "Workflows", description: "Deterministic, auditable orchestration", route: "/automation/workflows", icon: Workflow, state: MODULE_STATES.CONTRACT_PENDING, contract: "Workflow definition and run services", actions: [] },
  { id: "approvals", group: "Automation", label: "Approvals", description: "Human governance for consequential actions", route: "/automation/approvals", icon: ClipboardCheck, state: MODULE_STATES.CONTRACT_PENDING, contract: "Approval queue service", actions: [] },
  { id: "revenue", group: "Revenue", label: "Revenue Operations", description: "Forecasting, billing, and revenue intelligence", route: "/revenue", icon: BarChart3, state: MODULE_STATES.CONTRACT_PENDING, contract: "Revenue ledger and forecast services", actions: [] },
  { id: "support", group: "Support", label: "Support", description: "Cases, SLAs, and resolution context", route: "/support", icon: Headphones, state: MODULE_STATES.CONTRACT_PENDING, contract: "Case and SLA services", actions: [] },
  { id: "reporting", group: "Intelligence", label: "Reporting", description: "Explainable operating performance", route: "/intelligence/reporting", icon: BarChart3, state: MODULE_STATES.CONTRACT_PENDING, contract: "Metric and report services", actions: [] },
  { id: "relationship-intelligence", group: "Intelligence", label: "Relationship Intelligence", description: "Scoring, ranking, and explainable recommendations", route: "/intelligence/relationships", icon: Sparkles, state: MODULE_STATES.CONTRACT_PENDING, contract: "Recommendation service v1", actions: [] },
  { id: "migration", group: "Platform", label: "Migration", description: "Governed imports and reconciliation", route: "/platform/migration", icon: FileInput, state: MODULE_STATES.CONTRACT_PENDING, contract: "Import job and reconciliation services", actions: [] },
  { id: "registries", group: "Platform", label: "Registries", description: "Providers, capabilities, and connected records", route: "/registries", icon: Boxes, state: MODULE_STATES.AVAILABLE, contract: "GET /api/integrations/health", actions: ["view", "configure"] },
  { id: "mcp", group: "Platform", label: "MCP Console", description: "Governed AI tool operations", route: "/mcp", icon: Terminal, state: MODULE_STATES.AVAILABLE, contract: "MCP endpoint set", actions: ["view", "manage"] },
  { id: "audit", group: "Platform", label: "Automation & Audit", description: "Evidence and system activity", route: "/audit", icon: Activity, state: MODULE_STATES.AVAILABLE, contract: "GET /api/audit", actions: ["view"] },
  { id: "team", group: "Platform", label: "Team & Access", description: "Roles and tenant access", route: "/team", icon: ShieldCheck, state: MODULE_STATES.AVAILABLE, contract: "Team endpoint set", actions: ["view", "manage"], adminOnly: true },
  { id: "settings", group: "Platform", label: "Settings", description: "Account and provider configuration", route: "/settings", icon: Settings, state: MODULE_STATES.AVAILABLE, contract: "Settings endpoint set", actions: ["view", "manage"] },
  { id: "knowledge", group: "Platform", label: "Knowledge", description: "Reusable relationship and operating knowledge", route: "/platform/knowledge", icon: BookOpenCheck, state: MODULE_STATES.CONTRACT_PENDING, contract: "Knowledge item service", actions: [] },
];

export const MODULE_GROUPS = [...new Set(CLIENTVERSE_MODULES.map((module) => module.group))];
export const getModule = (id) => CLIENTVERSE_MODULES.find((module) => module.id === id);
export const getModuleByRoute = (pathname) => CLIENTVERSE_MODULES.find((module) => pathname === module.route || pathname.startsWith(`${module.route}/`));
export const isModuleActionable = (module) => module?.state === MODULE_STATES.AVAILABLE;
