"use client";

import { useState } from "react";
import { Bell, CircleAlert, CircleCheck, Wallet } from "lucide-react";
import { api } from "@/lib/api";
import { cn, eventLabel, formatDateTime, relativeTime, tidyMessage } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import { RoleGate } from "@/components/role-gate";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/feedback";
import { PageHeader, Pager, Tabs } from "@/components/ui/layout";

function eventIcon(event: string) {
  if (event.endsWith("FAILED")) return { icon: CircleAlert, tone: "bg-danger-soft text-danger" };
  if (event.endsWith("RELEASED")) return { icon: CircleCheck, tone: "bg-success-soft text-success" };
  if (event.startsWith("PAYMENT")) return { icon: Wallet, tone: "bg-accent text-accent-fg" };
  return { icon: Bell, tone: "bg-surface-2 text-muted" };
}

export default function NotificationsPage() {
  const [filter, setFilter] = useState<"" | "true">("");
  const [page, setPage] = useState(1);
  const result = useResource(() => api.notifications.list({ unread: filter || undefined, page, page_size: 20 }), [filter, page]);

  return (
    <RoleGate allow={["STUDENT", "CLIENT"]}>
      <PageHeader title="Notifications" description="Updates about payments on your assignments." />
      <Tabs
        label="Filter notifications"
        value={filter}
        onChange={(v) => {
          setFilter(v);
          setPage(1);
        }}
        options={[
          { value: "", label: "All" },
          { value: "true", label: "Unread" },
        ]}
      />
      <div className="mt-4">
        {result.error ? (
          <ErrorState error={result.error} onRetry={result.reload} />
        ) : result.loading ? (
          <SkeletonRows rows={3} />
        ) : result.data?.data.length ? (
          <>
            <ul className="card divide-y divide-line">
              {result.data.data.map((n) => {
                const { icon: Icon, tone } = eventIcon(n.event);
                return (
                  <li key={n.id} className="flex gap-4 px-5 py-4">
                    <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-full", tone)}>
                      <Icon className="h-4 w-4" aria-hidden />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-medium">{eventLabel(n.event)}</p>
                        {!n.is_read && (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-primary">
                            <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
                            Unread
                          </span>
                        )}
                      </div>
                      <p className="mt-0.5 text-sm text-muted">{tidyMessage(n.message)}</p>
                    </div>
                    <time dateTime={n.created_at} title={formatDateTime(n.created_at)} className="shrink-0 text-xs text-muted">
                      {relativeTime(n.created_at)}
                    </time>
                  </li>
                );
              })}
            </ul>
            <Pager pagination={result.data.pagination} onPage={setPage} />
          </>
        ) : (
          <div className="card">
            <EmptyState
              icon={Bell}
              title={filter ? "No unread notifications" : "No notifications yet"}
              description="You’ll be notified here when payments on your assignments change."
            />
          </div>
        )}
        <p className="mt-4 text-xs text-muted">
          Marking notifications as read isn’t supported by the notification service yet.
        </p>
      </div>
    </RoleGate>
  );
}
