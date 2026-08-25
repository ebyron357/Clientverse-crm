import { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatErr } from "@/lib/api";
import { toast } from "sonner";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Bell, CheckCheck, AlertTriangle, AlertCircle, Info, Settings, Inbox } from "lucide-react";

const SEV_ICON = {
  critical: { Icon: AlertCircle, cls: "text-red-600" },
  warning: { Icon: AlertTriangle, cls: "text-amber-600" },
  info: { Icon: Info, cls: "text-blue-600" },
};

function timeAgo(iso) {
  if (!iso) return "";
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
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

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          data-testid="notification-bell-button"
          className="relative w-10 h-10 rounded-lg bg-white border border-gray-200 flex items-center justify-center text-gray-600 hover:bg-gray-100 transition-colors"
          aria-label="Notifications"
        >
          <Bell className="w-5 h-5" />
          {unread > 0 && (
            <span
              data-testid="notification-unread-badge"
              className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full bg-red-600 text-white text-[10px] font-bold flex items-center justify-center"
            >
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 p-0" data-testid="notification-panel">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <div className="font-semibold text-sm">Notifications</div>
          <div className="flex items-center gap-1">
            <button
              onClick={readAll}
              disabled={unread === 0}
              data-testid="notification-read-all"
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-900 disabled:opacity-40 px-2 py-1 rounded transition-colors"
            >
              <CheckCheck className="w-3.5 h-3.5" /> Mark all read
            </button>
            <button
              onClick={() => { setOpen(false); navigate("/notifications"); }}
              data-testid="notification-settings-link"
              className="w-7 h-7 rounded flex items-center justify-center text-gray-500 hover:bg-gray-100 transition-colors"
              aria-label="Notification settings"
            >
              <Settings className="w-4 h-4" />
            </button>
          </div>
        </div>
        <ScrollArea className="max-h-96">
          {items.length === 0 ? (
            <div className="py-12 flex flex-col items-center text-gray-400" data-testid="notification-empty">
              <Inbox className="w-8 h-8 mb-2" />
              <div className="text-sm">You're all caught up</div>
            </div>
          ) : (
            <div className="divide-y divide-gray-50">
              {items.map((n) => {
                const { Icon, cls } = SEV_ICON[n.severity] || SEV_ICON.info;
                return (
                  <button
                    key={n.id}
                    onClick={() => markRead(n)}
                    data-testid={`notification-item-${n.id}`}
                    className={`w-full text-left px-4 py-3 flex gap-3 hover:bg-gray-50 transition-colors ${n.read ? "" : "bg-indigo-50/40"}`}
                  >
                    <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${cls}`} />
                    <div className="min-w-0 flex-1">
                      <div className={`text-sm truncate ${n.read ? "text-gray-600" : "text-gray-900 font-medium"}`}>{n.title}</div>
                      {n.body && <div className="text-xs text-gray-400 truncate mt-0.5">{n.body}</div>}
                      <div className="text-[10px] text-gray-300 mt-1">{timeAgo(n.created_at)}</div>
                    </div>
                    {!n.read && <span className="w-2 h-2 rounded-full bg-indigo-500 mt-1.5 shrink-0" />}
                  </button>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}
