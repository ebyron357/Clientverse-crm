import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CircleAlert, RefreshCw } from "lucide-react";

/** Shared empty / loading / error shells used across integrations, MCP, and activity surfaces. */
export function SurfaceLoading({ rows = 2, testid = "surface-loading" }) {
  return (
    <div className="space-y-3" data-testid={testid}>
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className="h-16 rounded-lg" />
      ))}
    </div>
  );
}

export function SurfaceEmpty({ icon: Icon, title, description, action, testid = "surface-empty" }) {
  return (
    <div className="cv-empty" data-testid={testid}>
      {Icon ? <span className="flex size-10 items-center justify-center rounded-full bg-muted"><Icon className="size-[18px] text-muted-foreground" aria-hidden="true" /></span> : null}
      <h2 className="mt-3 text-sm font-semibold text-foreground">{title}</h2>
      {description ? <p className="mt-1 max-w-sm text-[13px] leading-5 text-muted-foreground">{description}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function SurfaceError({ title = "Could not load this surface", description, onRetry, testid = "surface-error" }) {
  return (
    <div className="cv-empty" data-testid={testid} role="alert">
      <span className="flex size-10 items-center justify-center rounded-full bg-red-50"><CircleAlert className="size-[18px] text-red-600" aria-hidden="true" /></span>
      <h2 className="mt-3 text-sm font-semibold text-foreground">{title}</h2>
      {description ? <p className="mt-1 max-w-sm text-[13px] leading-5 text-muted-foreground">{description}</p> : null}
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry} className="mt-4" data-testid={`${testid}-retry`}>
          <RefreshCw aria-hidden="true" />Retry
        </Button>
      ) : null}
    </div>
  );
}
