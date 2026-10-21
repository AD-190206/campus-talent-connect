"use client";

import { Briefcase, ClipboardList, FolderKanban, Info, Star } from "lucide-react";
import { api } from "@/lib/api";
import { formatMoney, relativeTime } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import { ListRow, RowList } from "@/components/list-row";
import { ButtonLink } from "@/components/ui/button";
import { Alert, EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { PageHeader, Section, StatCard } from "@/components/ui/layout";
import { StatusBadge } from "@/components/ui/status-badge";

export function AdminDashboard() {
  const projects = useResource(() => api.projects.list({ page_size: 6 }), []);
  const applications = useResource(() => api.applications.list({ page_size: 1 }), []);
  const assignments = useResource(() => api.assignments.list({ page_size: 1 }), []);
  const active = useResource(() => api.assignments.list({ status: "active", page_size: 1 }), []);
  const reviews = useResource(() => api.reviews.list({ page_size: 1 }), []);

  const total = (r: { loading: boolean; data?: { pagination: { total: number } } }) =>
    r.loading ? <Skeleton className="h-7 w-12" /> : (r.data?.pagination.total ?? "—");

  return (
    <>
      <PageHeader title="Platform overview" description="Live totals from the platform’s services." />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Projects" icon={FolderKanban} value={total(projects)} hint="All statuses" />
        <StatCard label="Applications" icon={ClipboardList} value={total(applications)} />
        <StatCard
          label="Assignments"
          icon={Briefcase}
          value={total(assignments)}
          hint={active.data ? `${active.data.pagination.total} active` : undefined}
        />
        <StatCard label="Reviews" icon={Star} value={total(reviews)} />
      </div>

      <Alert tone="info" className="mt-6 flex gap-2">
        <span className="flex gap-2">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>
            User listing, verification, disputes and analytics reports need admin endpoints that the backend does
            not provide yet. Those pages explain what is missing.
          </span>
        </span>
      </Alert>

      <Section
        className="mt-6"
        title="Recently updated projects"
        actions={
          <ButtonLink href="/projects" variant="ghost" size="sm">
            Moderate projects
          </ButtonLink>
        }
      >
        {projects.error ? (
          <ErrorState error={projects.error} onRetry={projects.reload} className="m-4 border-0" />
        ) : projects.loading ? (
          <div className="space-y-3 p-5">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        ) : projects.data?.data.length ? (
          <RowList>
            {projects.data.data.map((p) => (
              <ListRow
                key={p.id}
                href={`/projects/${p.id}`}
                title={p.title}
                meta={`${formatMoney(p.budget)} · created ${relativeTime(p.created_at)}`}
                aside={<StatusBadge status={p.status} />}
              />
            ))}
          </RowList>
        ) : (
          <EmptyState icon={FolderKanban} title="No projects yet" />
        )}
      </Section>
    </>
  );
}
