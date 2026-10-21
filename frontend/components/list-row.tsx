import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/format";

/** A clickable row used inside Section cards. */
export function ListRow({
  href,
  title,
  meta,
  aside,
  className,
}: {
  href: string;
  title: React.ReactNode;
  meta?: React.ReactNode;
  aside?: React.ReactNode;
  className?: string;
}) {
  return (
    <li>
      <Link
        href={href}
        className={cn(
          "flex items-center gap-4 px-5 py-3.5 transition-colors hover:bg-surface-2/60 focus-visible:-outline-offset-2",
          className
        )}
      >
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-fg">{title}</p>
          {meta && <p className="mt-0.5 truncate text-[13px] text-muted">{meta}</p>}
        </div>
        {aside}
        <ChevronRight className="h-4 w-4 shrink-0 text-muted" aria-hidden />
      </Link>
    </li>
  );
}

export function RowList({ children }: { children: React.ReactNode }) {
  return <ul className="divide-y divide-line">{children}</ul>;
}
