import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CircleAlert, RefreshCw } from "lucide-react";

/** Shared empty / loading / error shells used across integrations, MCP, and activity surfaces. */
export function SurfaceLoading({ rows = 2, testid = "surface-loading" }) {
  return (
    <div className="space-y-3" data-testid={testid}>
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className="h-24 rounded-xl" />
      ))}
    </div>
  );
}

export function SurfaceEmpty({ icon: Icon, title, description, action, testid = "surface-empty" }) {
  return (
    <div className="cv-empty" data-testid={testid}>
      {Icon ? <Icon className="h-9 w-9 text-[#4ac4e0]" /> : null}
      <h2 className="mt-4 font-display text-xl font-bold text-[#0a1628]">{title}</h2>
      {description ? <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">{description}</p> : null}
      {action || null}
    </div>
  );
}

export function SurfaceError({ title = "Could not load this surface", description, onRetry, testid = "surface-error" }) {
  return (
    <div className="cv-empty" data-testid={testid} role="alert">
      <CircleAlert className="h-9 w-9 text-red-500" />
      <h2 className="mt-4 font-display text-xl font-bold text-[#0a1628]">{title}</h2>
      {description ? <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">{description}</p> : null}
      {onRetry ? (
        <Button onClick={onRetry} className="mt-5 cv-action-primary" data-testid={`${testid}-retry`}>
          <RefreshCw className="mr-2 h-4 w-4" />Retry
        </Button>
      ) : null}
    </div>
  );
}
