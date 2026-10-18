import { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Bell, CheckCheck, AlertTriangle, AlertCircle, Info, Settings, Inbox, ArrowRight } from "lucide-react";

const SEV_ICON = {
  critical: { Icon: AlertCircle, cls: "text-red-600" },
  warning: { Icon: AlertTriangle, cls: "text-amber-600" },
  info: { Icon: Info, cls: "text-sky-600" },
};

function timeAgo(iso) {
  if (!iso) return "";
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

export default function NotificationBell() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const timer = useRef(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/notifications");
      setItems(data.notifications || []);
      setUnread(data.unread || 0);
    } catch { /* silent poll */ }
  }, []);

  useEffect(() => {
    load();
    timer.current = setInterval(load, 30000);
    return () => clearInterval(timer.current);
  }, [load]);

  const markRead = async (n) => {
    if (!n.read) {
      try {
        await api.post(`/notifications/${n.id}/read`);
        setUnread((u) => Math.max(0, u - 1));
        setItems((arr) => arr.map((x) => (x.id === n.id ? { ...x, read: true } : x)));
      } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
    }
    if (n.deep_link) { setOpen(false); navigate(n.deep_link); }
  };

  const readAll = async () => {
    try {
      await api.post("/notifications/read-all");
      setUnread(0);
      setItems((arr) => arr.map((x) => ({ ...x, read: true })));
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  };

  const viewAll = () => { setOpen(false); navigate("/notifications"); };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          data-testid="notification-bell-button"
          className="relative inline-flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground data-[state=open]:bg-accent data-[state=open]:text-foreground"
          aria-label={unread > 0 ? `Notifications, ${unread} unread` : "Notifications"}
        >
          <Bell className="size-[18px]" aria-hidden="true" />
          {unread > 0 && (
            <span
              data-testid="notification-unread-badge"
              className="tabular absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold leading-none text-white ring-2 ring-background"
            >
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={8} className="w-[min(380px,calc(100vw-1.5rem))] overflow-hidden rounded-xl p-0" data-testid="notification-panel">
        <div className="flex h-11 items-center justify-between gap-2 border-b border-border px-3">
          <div className="flex items-center gap-2 pl-1 text-[13px] font-semibold text-foreground">
            Notifications
            {unread > 0 && <span className="tabular rounded-md bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">{unread} new</span>}
          </div>
          <div className="flex items-center gap-0.5">
            <button
              type="button"
              onClick={readAll}
              disabled={unread === 0}
              data-testid="notification-read-all"
              className="flex h-7 items-center gap-1 rounded-md px-2 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
            >
              <CheckCheck className="size-3.5" aria-hidden="true" /> Mark all read
            </button>
            <button
              type="button"
              onClick={viewAll}
              data-testid="notification-settings-link"
              className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              aria-label="Notification settings"
            >
              <Settings className="size-4" aria-hidden="true" />
            </button>
          </div>
        </div>
        <ScrollArea className="[&>[data-radix-scroll-area-viewport]]:max-h-[420px]">
          {items.length === 0 ? (
            <div className="flex flex-col items-center px-6 py-10 text-center" data-testid="notification-empty">
              <span className="flex size-10 items-center justify-center rounded-full bg-muted"><Inbox className="size-[18px] text-muted-foreground" aria-hidden="true" /></span>
              <div className="mt-3 text-sm font-medium text-foreground">You're all caught up</div>
              <div className="mt-1 text-[13px] text-muted-foreground">New alerts and lead activity show up here.</div>
            </div>
          ) : (
            <div className="divide-y divide-border/60">
              {items.map((n) => {
                const { Icon, cls } = SEV_ICON[n.severity] || SEV_ICON.info;
                return (
                  <button
                    type="button"
                    key={n.id}
                    onClick={() => markRead(n)}
                    data-testid={`notification-item-${n.id}`}
                    className="flex w-full gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-muted/60 focus-visible:bg-muted/60"
                  >
                    <span className={`mt-[7px] size-1.5 shrink-0 rounded-full ${n.read ? "bg-transparent" : "bg-brand"}`} aria-hidden="true" />
                    <Icon className={`mt-0.5 size-4 shrink-0 ${cls}`} aria-hidden="true" />
                    <div className="min-w-0 flex-1">
                      {/* Wrapped, not truncated: one-line truncation inside the scroll area widened the row
                          past the panel and cut titles off mid-word ("…no response: Dana Brook"). */}
                      <div className={`line-clamp-2 break-words text-[13px] leading-5 ${n.read ? "text-muted-foreground" : "font-medium text-foreground"}`}>
                        {!n.read && <span className="sr-only">Unread: </span>}{n.title}
                      </div>
                      {n.body && <div className="mt-0.5 line-clamp-1 break-words text-xs text-muted-foreground">{n.body}</div>}
                    </div>
                    <time className="tabular shrink-0 pt-0.5 text-[11px] text-muted-foreground" dateTime={n.created_at || undefined}>{timeAgo(n.created_at)}</time>
                  </button>
                );
              })}
            </div>
          )}
        </ScrollArea>
        <div className="border-t border-border bg-muted/30">
          <button
            type="button"
            onClick={viewAll}
            data-testid="notification-view-all"
            className="flex h-10 w-full items-center justify-center gap-1.5 text-[13px] font-medium text-foreground/80 transition-colors hover:bg-muted hover:text-foreground"
          >
            View all in Action Center<ArrowRight className="size-3.5" aria-hidden="true" />
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
