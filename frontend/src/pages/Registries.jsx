import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Badge } from "@/components/AppShell";
import { CAP_STATUS } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import WebhookManager from "@/components/WebhookManager";
import { Plug, Server, Puzzle, Webhook, ShieldCheck } from "lucide-react";

const TABS = [
  { key: "integrations", label: "Integrations", icon: Plug },
  { key: "mcp-servers", label: "MCP Servers", icon: Server },
  { key: "plugins", label: "Plugins", icon: Puzzle },
  { key: "webhooks", label: "Webhooks", icon: Webhook },
];

function Row({ item }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm" data-testid={`registry-item-${item.id}`}>
      <div className="flex items-start justify-between">
        <div>
          <div className="font-display font-bold text-base">{item.name}</div>
          <div className="text-xs text-gray-400 mt-0.5">
            {item.provider || item.publisher || item.version || item.url}
            {item.level ? ` · Level ${item.level}` : ""}
          </div>
        </div>
        <Badge className={CAP_STATUS[item.status] || CAP_STATUS.PLANNED}>{item.status}</Badge>
      </div>
      <p className="text-sm text-gray-600 mt-2">{item.description}</p>
      <div className="flex flex-wrap gap-1.5 mt-3">
        {(item.tools || item.scopes || item.permissions || item.events || []).slice(0, 6).map((t, i) => (
          <span key={i} className="text-[11px] font-mono px-2 py-0.5 rounded bg-gray-50 border border-gray-200 text-gray-600">{t}</span>
        ))}
      </div>
    </div>
  );
}

export default function Registries() {
  const [data, setData] = useState({});
  const [loading, setLoading] = useState(true);

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

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-display text-3xl font-bold">Registries</h1>
        <p className="text-sm text-gray-500 mt-1 flex items-center gap-1.5">
          <ShieldCheck className="w-4 h-4 text-emerald-600" />
          Governed contracts with capability statuses. External execution wired later.
        </p>
      </div>

      <Tabs defaultValue="integrations">
        <TabsList>
          {TABS.map((t) => <TabsTrigger key={t.key} value={t.key} data-testid={`tab-${t.key}`}><t.icon className="w-4 h-4 mr-1" />{t.label}</TabsTrigger>)}
        </TabsList>
        {TABS.map((t) => (
          <TabsContent key={t.key} value={t.key} className="mt-6">
            {t.key === "webhooks" ? <WebhookManager /> : loading ? <Skeleton className="h-40 rounded-xl" /> : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {(data[t.key] || []).map((it) => <Row key={it.id} item={it} />)}
                {(data[t.key] || []).length === 0 && <div className="text-sm text-gray-400 py-8">No entries.</div>}
              </div>
            )}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
