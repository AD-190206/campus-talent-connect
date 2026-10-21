"use client";

import { Briefcase, ClipboardList, FolderKanban, Inbox, Plus, Send } from "lucide-react";
import { api } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { formatMoney, relativeTime } from "@/lib/format";
import { useProjects, useResource } from "@/lib/hooks";
import { loadMyProjects } from "@/lib/queries";
import { ListRow, RowList } from "@/components/list-row";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { PageHeader, Section, StatCard } from "@/components/ui/layout";
import { StatusBadge } from "@/components/ui/status-badge";

export function ClientDashboard() {
  const user = useUser();
  const projects = useResource(() => loadMyProjects(user.user_id), [user.user_id]);
  const assignments = useResource(() => api.assignments.list({ status: "active", page_size: 20 }), []);

  const awaiting = useResource(
    async () => {
      const list = assignments.data?.data ?? [];
      const results = await Promise.all(
        list.map((a) => api.work.list({ assignment_id: a.id, status: "SUBMITTED", page_size: 5 }))
      );
      return results.flatMap((r) => r.data);
    },
    [assignments.data],
    !!assignments.data
  );

  const open = (projects.data ?? []).filter((p) => p.status === "PUBLISHED");
  const pendingApplications = useResource(
    async () => {
      const counts = await Promise.all(
        open.map((p) => api.applications.list({ project_id: p.id, status: "submitted", page_size: 1 }))
      );
      return counts.reduce((sum, r) => sum + r.pagination.total, 0);
    },
    [projects.data],
    !!projects.data
  );

  const titles = useProjects([
    ...(assignments.data?.data.map((a) => a.project_id) ?? []),
    ...(awaiting.data?.map((w) => w.project_id) ?? []),
  ]);

  const stat = (loading: boolean, value: React.ReactNode) => (loading ? <Skeleton className="h-7 w-12" /> : value);

  return (
    <>
      <PageHeader
        title="Overview"
        description="Your projects, applicants and work in progress."
        actions={
          <>
            <ButtonLink href="/applications" variant="secondary">
              Review applications
            </ButtonLink>
            <ButtonLink href="/projects/new">
              <Plus className="h-4 w-4" aria-hidden />
              Post a project
            </ButtonLink>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Open projects"
          icon={FolderKanban}
          value={stat(projects.loading, open.length)}
          hint={projects.data ? `${projects.data.length} total` : undefined}
        />
        <StatCard
          label="New applications"
          icon={ClipboardList}
          value={stat(pendingApplications.loading || projects.loading, pendingApplications.data ?? "—")}
          hint="Awaiting your review"
        />
        <StatCard
          label="Active assignments"
          icon={Briefcase}
          value={stat(assignments.loading, assignments.data?.pagination.total ?? "—")}
        />
        <StatCard
          label="Work to review"
          icon={Send}
          value={stat(awaiting.loading || assignments.loading, awaiting.data?.length ?? "—")}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Section title="Work awaiting your review" description="Approve or request changes.">
          {awaiting.error ? (
            <ErrorState error={awaiting.error} onRetry={awaiting.reload} className="m-4 border-0" />
          ) : awaiting.loading || assignments.loading ? (
            <div className="space-y-3 p-5">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          ) : awaiting.data?.length ? (
            <RowList>
              {awaiting.data.map((w) => (
                <ListRow
                  key={w.id}
                  href={`/assignments/${w.assignment_id}`}
                  title={w.title}
                  meta={`${titles[w.project_id]?.title ?? "Project"} · submitted ${relativeTime(w.submitted_at)}`}
                  aside={<StatusBadge status={w.status} />}
                />
              ))}
            </RowList>
          ) : (
            <EmptyState icon={Inbox} title="Nothing to review" description="Submitted deliverables will show up here." />
          )}
        </Section>

        <Section
          title="Active assignments"
          actions={
            <ButtonLink href="/assignments" variant="ghost" size="sm">
              View all
            </ButtonLink>
          }
        >
          {assignments.error ? (
            <ErrorState error={assignments.error} onRetry={assignments.reload} className="m-4 border-0" />
          ) : assignments.loading ? (
            <div className="space-y-3 p-5">
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : assignments.data?.data.length ? (
            <RowList>
              {assignments.data.data.slice(0, 5).map((a) => (
                <ListRow
                  key={a.id}
                  href={`/assignments/${a.id}`}
                  title={titles[a.project_id]?.title ?? "Project"}
                  meta={`Started ${relativeTime(a.assigned_date)}`}
                  aside={<StatusBadge status={a.status} />}
                />
              ))}
            </RowList>
          ) : (
            <EmptyState
              icon={Briefcase}
              title="No active assignments"
              description="Select an applicant on one of your projects to start an assignment."
            />
          )}
        </Section>
      </div>

      <Section
        className="mt-6"
        title="Your projects"
        actions={
          <ButtonLink href="/projects" variant="ghost" size="sm">
            Manage
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
        ) : projects.data?.length ? (
          <RowList>
            {projects.data.slice(0, 6).map((p) => (
              <ListRow
                key={p.id}
                href={`/projects/${p.id}`}
                title={p.title}
                meta={`${formatMoney(p.budget)} · updated ${relativeTime(p.updated_at)}`}
                aside={<StatusBadge status={p.status} />}
              />
            ))}
          </RowList>
        ) : (
          <EmptyState
            icon={FolderKanban}
            title="Post your first project"
            description="Describe the work, set a budget and deadline, then publish it to students."
            action={
              <ButtonLink href="/projects/new" size="sm">
                Post a project
              </ButtonLink>
            }
          />
        )}
      </Section>
    </>
  );
}
