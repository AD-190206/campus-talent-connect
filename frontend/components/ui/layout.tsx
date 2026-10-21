"use client";

import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { Pagination as PaginationMeta } from "@/lib/types";
import { cn } from "@/lib/format";
import { Button } from "./button";

export function PageHeader({
  title,
  description,
  actions,
  back,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  back?: { href: string; label: string };
}) {
  return (
    <header className="mb-6 sm:mb-8">
      {back && (
        <Link
          href={back.href}
          className="mb-3 inline-flex items-center gap-1 text-[13px] text-muted hover:text-fg"
        >
          <ChevronLeft className="h-3.5 w-3.5" aria-hidden />
          {back.label}
        </Link>
      )}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight text-fg">{title}</h1>
          {description && <p className="mt-1.5 max-w-2xl text-sm text-muted">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </div>
    </header>
  );
}

export function Section({
  title,
  description,
  actions,
  children,
  className,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("card", className)}>
      <div className="flex min-h-[61px] items-center justify-between gap-4 border-b border-line px-5 py-3.5">
        <div>
          <h2 className="text-[15px] font-semibold">{title}</h2>
          {description && <p className="mt-0.5 text-[13px] text-muted">{description}</p>}
        </div>
        {actions}
      </div>
      <div>{children}</div>
    </section>
  );
}

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between">
        <p className="text-[13px] text-muted">{label}</p>
        {Icon && <Icon className="h-4 w-4 text-muted" />}
      </div>
      <div className="mt-2 text-2xl font-semibold tracking-tight tabular-nums">{value}</div>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

export function Tabs<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (value: T) => void;
  options: Array<{ value: T; label: string; count?: number }>;
  label: string;
}) {
  return (
    <div
      role="tablist"
      aria-label={label}
      className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1 [scrollbar-width:none]"
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            role="tab"
            type="button"
            aria-selected={selected}
            onClick={() => onChange(option.value)}
            className={cn(
              "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg px-3 text-[13px] font-medium transition-colors",
              selected ? "bg-surface text-fg shadow-soft ring-1 ring-line" : "text-muted hover:text-fg"
            )}
          >
            {option.label}
            {option.count !== undefined && (
              <span className={cn("tabular-nums text-xs", selected ? "text-muted" : "text-muted/80")}>
                {option.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function Pager({ pagination, onPage }: { pagination?: PaginationMeta; onPage: (page: number) => void }) {
  if (!pagination || pagination.total_pages <= 1) return null;
  const { page, total_pages, total, page_size } = pagination;
  const from = (page - 1) * page_size + 1;
  const to = Math.min(page * page_size, total);
  return (
    <nav aria-label="Pagination" className="mt-6 flex items-center justify-between gap-4">
      <p className="text-[13px] text-muted">
        <span className="tabular-nums">
          {from}–{to}
        </span>{" "}
        of <span className="tabular-nums">{total}</span>
      </p>
      <div className="flex gap-2">
        <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          <ChevronLeft className="h-3.5 w-3.5" aria-hidden />
          Previous
        </Button>
        <Button variant="secondary" size="sm" disabled={page >= total_pages} onClick={() => onPage(page + 1)}>
          Next
          <ChevronRight className="h-3.5 w-3.5" aria-hidden />
        </Button>
      </div>
    </nav>
  );
}

export function DescriptionList({ items }: { items: Array<[string, React.ReactNode]> }) {
  return (
    <dl className="divide-y divide-line">
      {items.map(([term, detail]) => (
        <div key={term} className="flex items-center justify-between gap-4 px-5 py-3 text-sm">
          <dt className="text-muted">{term}</dt>
          <dd className="min-w-0 truncate text-right font-medium text-fg">{detail}</dd>
        </div>
      ))}
    </dl>
  );
}
