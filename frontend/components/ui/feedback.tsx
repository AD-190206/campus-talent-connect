import { CircleAlert, LoaderCircle, type LucideIcon, RefreshCw, WifiOff } from "lucide-react";
import type { ApiError } from "@/lib/api";
import { cn } from "@/lib/format";
import { Button } from "./button";

export function Spinner({ className, label = "Loading" }: { className?: string; label?: string }) {
  return (
    <span role="status" className={cn("inline-flex items-center gap-2 text-sm text-muted", className)}>
      <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />
      <span>{label}…</span>
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-md bg-surface-2", className)} />;
}

export function SkeletonRows({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div role="status" aria-label="Loading" className={cn("space-y-3", className)}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="card p-5">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="mt-3 h-3 w-2/3" />
          <Skeleton className="mt-2 h-3 w-1/2" />
        </div>
      ))}
    </div>
  );
}

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center px-6 py-12 text-center", className)}>
      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-surface-2 text-muted">
        <Icon className="h-5 w-5" aria-hidden />
      </span>
      <h3 className="mt-4 text-[15px] font-semibold text-fg">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-sm text-muted">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: ApiError | null;
  onRetry?: () => void;
  className?: string;
}) {
  if (!error) return null;
  const network = error.code === "NETWORK_ERROR";
  const upstream = error.status >= 502;
  const Icon = network ? WifiOff : CircleAlert;
  return (
    <div role="alert" className={cn("card flex flex-col items-center px-6 py-10 text-center", className)}>
      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-danger-soft text-danger">
        <Icon className="h-5 w-5" aria-hidden />
      </span>
      <h3 className="mt-4 text-[15px] font-semibold">
        {network ? "Can’t reach the server" : upstream ? "A service is unavailable" : "Something went wrong"}
      </h3>
      <p className="mt-1 max-w-md text-sm text-muted">{error.message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-5" onClick={onRetry}>
          <RefreshCw className="h-3.5 w-3.5" aria-hidden />
          Try again
        </Button>
      )}
    </div>
  );
}

/** Inline alert for forms and panels. */
export function Alert({
  tone = "danger",
  title,
  children,
  className,
}: {
  tone?: "danger" | "info" | "warning" | "success";
  title?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  const tones = {
    danger: "bg-danger-soft text-danger",
    info: "bg-info-soft text-info",
    warning: "bg-warning-soft text-warning",
    success: "bg-success-soft text-success",
  };
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cn("rounded-lg px-3.5 py-3 text-sm", tones[tone], className)}>
      {title && <p className="font-medium">{title}</p>}
      {children && <div className={cn(title && "mt-0.5", "opacity-90")}>{children}</div>}
    </div>
  );
}
