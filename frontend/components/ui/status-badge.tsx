import {
  Ban,
  CircleCheck,
  CircleDashed,
  CircleDot,
  CircleX,
  Clock,
  FileEdit,
  type LucideIcon,
  RotateCcw,
  Send,
  Star,
  Undo2,
  Wallet,
} from "lucide-react";
import { cn } from "@/lib/format";

type Tone = "neutral" | "info" | "success" | "warning" | "danger" | "brand";

const tones: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted",
  info: "bg-info-soft text-info",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
  brand: "bg-accent text-accent-fg",
};

// Every status pairs a colour with an icon and a text label, so meaning
// never depends on colour alone.
const STATUSES: Record<string, { label: string; tone: Tone; icon: LucideIcon }> = {
  // projects
  DRAFT: { label: "Draft", tone: "neutral", icon: FileEdit },
  PUBLISHED: { label: "Open", tone: "brand", icon: CircleDot },
  IN_PROGRESS: { label: "In progress", tone: "info", icon: Clock },
  COMPLETED: { label: "Completed", tone: "success", icon: CircleCheck },
  CLOSED: { label: "Closed", tone: "neutral", icon: Ban },
  ARCHIVED: { label: "Archived", tone: "neutral", icon: Ban },
  // applications
  submitted: { label: "Submitted", tone: "info", icon: Send },
  shortlisted: { label: "Shortlisted", tone: "warning", icon: Star },
  selected: { label: "Selected", tone: "success", icon: CircleCheck },
  rejected: { label: "Not selected", tone: "danger", icon: CircleX },
  withdrawn: { label: "Withdrawn", tone: "neutral", icon: Undo2 },
  // assignments
  active: { label: "Active", tone: "info", icon: Clock },
  completed: { label: "Completed", tone: "success", icon: CircleCheck },
  cancelled: { label: "Cancelled", tone: "neutral", icon: Ban },
  // work
  SUBMITTED: { label: "Awaiting review", tone: "warning", icon: Send },
  REVISION_REQUESTED: { label: "Revision requested", tone: "danger", icon: RotateCcw },
  APPROVED: { label: "Approved", tone: "success", icon: CircleCheck },
  // payments
  PENDING: { label: "Pending", tone: "neutral", icon: CircleDashed },
  PROCESSING: { label: "Processing", tone: "info", icon: Clock },
  SUCCESS: { label: "Funded", tone: "brand", icon: Wallet },
  FAILED: { label: "Failed", tone: "danger", icon: CircleX },
  REFUNDED: { label: "Refunded", tone: "neutral", icon: Undo2 },
  RELEASED: { label: "Released", tone: "success", icon: CircleCheck },
};

export function statusLabel(status: string) {
  return STATUSES[status]?.label ?? status;
}

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const meta = STATUSES[status] ?? { label: status, tone: "neutral" as Tone, icon: CircleDot };
  const Icon = meta.icon;
  return (
    <span
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1 rounded-md px-2 text-xs font-medium",
        tones[meta.tone],
        className
      )}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {meta.label}
    </span>
  );
}

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: Tone;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn("inline-flex h-6 items-center gap-1 rounded-md px-2 text-xs font-medium", tones[tone], className)}
    >
      {children}
    </span>
  );
}

export function SkillTag({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex h-6 items-center rounded-md border border-line px-2 text-xs text-muted">
      {children}
    </span>
  );
}
