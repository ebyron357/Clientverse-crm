import { useEffect, useState } from "react";
import useSWR, { SWRConfig, useSWRConfig } from "swr";
import { api } from "@/lib/api";

export const SHARED_READ_INTERVAL = 30000;
export const OVERDUE_COUNT = "/tasks/overdue-count";
const PREFIX = "shared-read";
const LEADS = ["/leads", "/leads/summary"];
const TASKS = [OVERDUE_COUNT];
const APPROVALS = ["/approval-queue", "/approval-queue/summary"];
const CONVERSATIONS = ["/conversations", "/conversations/summary"];

export function affectedReads(config = {}) {
  if (!["post", "put", "patch", "delete"].includes(config.method?.toLowerCase())) return [];
  const path = (config.url || "").split("?")[0];
  if (/^\/(?:crm\/)?tasks(?:\/|$)/.test(path)) return [...TASKS, ...LEADS];
  if (/^\/leads(?:\/|$)/.test(path)) return [...LEADS, ...TASKS];
  if (/^\/approval-queue(?:\/|$)/.test(path)) return [...APPROVALS, ...CONVERSATIONS];
  if (/^\/conversations(?:\/|$)/.test(path)) return [...CONVERSATIONS, ...APPROVALS];
  // These operations can create follow-ups, approvals or conversations as side effects.
  if (/^\/(?:website-forms|calendar|bookings|playbooks|work-queue|recovery-strategies|second-chance|workspaces)(?:\/|$)/.test(path)) {
    return [...LEADS, ...TASKS, ...APPROVALS, ...CONVERSATIONS, "/website-forms"];
  }
  return [];
}

function RefreshAfterWrites({ children }) {
  const { mutate } = useSWRConfig();
  useEffect(() => {
    let active = true;
    const interceptor = api.interceptors.response.use((response) => {
      const paths = affectedReads(response.config);
      if (active && paths.length) {
        // Keep the last confirmed data while refetching; failures must not reject a saved write.
        void mutate(
          (key) => Array.isArray(key) && key[0] === PREFIX && paths.includes(key[1]),
          (current) => current,
          { revalidate: true, throwOnError: false },
        ).catch(() => {});
      }
      return response;
    });
    return () => { active = false; api.interceptors.response.eject(interceptor); };
  }, [mutate]);
  return children;
}

function SessionCache({ children }) {
  const [cache] = useState(() => new Map());
  return <SWRConfig value={{ provider: () => cache }}><RefreshAfterWrites>{children}</RefreshAfterWrites></SWRConfig>;
}

export function SharedReadsProvider({ user, children }) {
  // Remount the cache and its consumers together; late replies cannot enter another session.
  const scope = JSON.stringify([user?.tenant_id, user?.user_id || user?.id || user?.email, user?.role, user?.acting || null]);
  return <SessionCache key={scope}>{children}</SessionCache>;
}

async function fetchRead([, path, params]) {
  const overdue = path === OVERDUE_COUNT;
  const { data } = await api.get(overdue ? "/tasks" : path, {
    params: overdue ? {
      status: "todo,in_progress,blocked", due_before: new Date(Date.now() - 1).toISOString(),
      mine: true, include_unassigned: true, limit: 1,
    } : params,
  });
  return { payload: data, updatedAt: new Date() };
}

export function useSharedRead(path, params = null) {
  const result = useSWR(path ? [PREFIX, path, params] : null, fetchRead, {
    // Expire deduplication before the polling timer, so the first poll is not skipped.
    dedupingInterval: SHARED_READ_INTERVAL - 1000,
    refreshInterval: SHARED_READ_INTERVAL,
    focusThrottleInterval: SHARED_READ_INTERVAL,
    errorRetryInterval: SHARED_READ_INTERVAL,
    errorRetryCount: 2,
  });
  return { ...result, data: result.data?.payload, updatedAt: result.data?.updatedAt };
}

export function useMenuCounts() {
  const leads = useSharedRead("/leads/summary");
  const inbox = useSharedRead("/conversations/summary");
  const tasks = useSharedRead(OVERDUE_COUNT);
  const approvals = useSharedRead("/approval-queue/summary");
  const positive = (value) => Number.isFinite(Number(value)) && Number(value) > 0 ? Number(value) : 0;
  return {
    leads: positive(leads.data?.open_now), inbox: positive(inbox.data?.open_conversations),
    tasks: positive(tasks.data?.total), approvals: positive(approvals.data?.awaiting_decision),
  };
}
