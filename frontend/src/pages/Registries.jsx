import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import WebhookManager from "@/components/WebhookManager";
import IntegrationsPanel from "@/components/IntegrationsPanel";
import { PageHeader, Section, StatusDot, ViewTabs } from "@/components/page/Page";
import { Boxes, Plug, Server, Puzzle, Webhook } from "lucide-react";

const TABS = [
  { key: "integrations", label: "Integrations", icon: Plug },
  { key: "mcp-servers", label: "MCP Servers", icon: Server },
  { key: "plugins", label: "Plugins", icon: Puzzle },
  { key: "webhooks", label: "Webhooks", icon: Webhook },
];

// Capability status → a dot tone and a readable word (the API speaks in SCREAMING_CASE).
const STATUS_TONE = {
  AVAILABLE: "success",
  BETA: "warning",
  ALPHA: "violet",
  PLANNED: "info",
  REQUIRES_CONFIGURATION: "warning",
  RESEARCHING: "neutral",
  DEPRECATED: "danger",
};
const statusWord = (status = "PLANNED") => status.charAt(0) + status.slice(1).toLowerCase().replaceAll("_", " ");

function Row({ item }) {
  const tags = item.tools || item.scopes || item.permissions || item.events || [];
  return (
    <div className="flex flex-col gap-2 px-4 py-3 transition-colors hover:bg-muted/40 sm:flex-row sm:items-start sm:gap-6" data-testid={`registry-item-${item.id}`}>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-[13px] font-medium text-foreground">{item.name}</span>
          <span className="text-xs text-muted-foreground">
            {item.provider || item.publisher || item.version || item.url}
            {item.level ? ` · Level ${item.level}` : ""}
          </span>
        </div>
        <p className="mt-0.5 text-[12.5px] leading-5 text-muted-foreground">{item.description}</p>
        {tags.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {tags.slice(0, 6).map((t, i) => (
              <code key={i} className="rounded bg-muted px-1.5 py-px font-mono text-[11px] text-muted-foreground">{t}</code>
            ))}
          </div>
        )}
      </div>
      <div className="shrink-0 sm:w-44 sm:pt-0.5 sm:text-right">
        <StatusDot tone={STATUS_TONE[item.status] || "neutral"}>{statusWord(item.status)}</StatusDot>
      </div>
    </div>
  );
}

function RowList({ items }) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="divide-y divide-border/70">{items.map((it) => <Row key={it.id} item={it} />)}</div>
    </div>
  );
}

export default function Registries() {
  const [data, setData] = useState({});
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("integrations");

  useEffect(() => {
    (async () => {
      const res = {};
      for (const t of TABS) {
        const r = await api.get(`/registry/${t.key}`);
        res[t.key] = r.data;
      }
      setData(res); setLoading(false);
    })();
  }, []);

  const items = TABS.map((t) => ({
    value: t.key,
    label: t.label,
    icon: t.icon,
    count: !loading && t.key !== "integrations" && t.key !== "webhooks" ? (data[t.key] || []).length : undefined,
    testid: `tab-${t.key}`,
  }));

  return (
    <div className="cv-page">
      <PageHeader icon={Boxes} title="Registries" description="Governed contracts with capability statuses. External execution is wired later." />

      <ViewTabs items={items} value={tab} onChange={setTab} label="Registry" />
      <div className="mt-5">
        {tab === "webhooks" ? <WebhookManager /> : tab === "integrations" ? (
          <div className="space-y-8">
            <IntegrationsPanel />
            {!loading && (data[tab] || []).length > 0 && (
              <Section title="Governed capability contracts">
                <RowList items={data[tab] || []} />
              </Section>
            )}
          </div>
        ) : loading ? <Skeleton className="h-40 rounded-xl" /> : (data[tab] || []).length === 0 ? (
          <div className="rounded-xl border border-border bg-card px-6 py-10 text-center text-[13px] text-muted-foreground">No entries.</div>
        ) : (
          <RowList items={data[tab] || []} />
        )}
      </div>
    </div>
  );
}
