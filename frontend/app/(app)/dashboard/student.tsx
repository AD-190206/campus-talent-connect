"use client";

import { Bell, Briefcase, FileText, Search, Star, User, Wallet } from "lucide-react";
import { api } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { eventLabel, formatMoney, relativeTime, splitSkills, sumMoney, tidyMessage } from "@/lib/format";
import { useProjects, useResource } from "@/lib/hooks";
import type { StudentProfile } from "@/lib/types";
import { ListRow, RowList } from "@/components/list-row";
import { ProjectCard } from "@/components/project-card";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { PageHeader, Section, StatCard } from "@/components/ui/layout";
import { StatusBadge } from "@/components/ui/status-badge";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export function StudentDashboard() {
  const user = useUser();
  const profile = useResource(() => api.users.profile<StudentProfile>(user.user_id), [user.user_id]);
  const applications = useResource(() => api.applications.list({ page_size: 5 }), []);
  const shortlisted = useResource(() => api.applications.list({ status: "shortlisted", page_size: 1 }), []);
  const assignments = useResource(() => api.assignments.list({ status: "active", page_size: 5 }), []);
  const payments = useResource(() => api.payments.list({ page_size: 100 }), []);
  const notifications = useResource(() => api.notifications.list({ page_size: 4 }), []);

  const skills = splitSkills(profile.data?.data.skills);
  const recommended = useResource(
    () => api.projects.list({ page_size: 3, skill: skills[0] }),
    [skills[0]],
    !profile.loading
  );

  const projectIds = [
    ...(applications.data?.data.map((a) => a.project_id) ?? []),
    ...(assignments.data?.data.map((a) => a.project_id) ?? []),
  ];
  const projects = useProjects(projectIds);

  const received = (payments.data?.data ?? []).filter((p) => p.payee_id === user.user_id);
  const released = sumMoney(received.filter((p) => p.status === "RELEASED").map((p) => p.net_amount));

  const name = profile.data?.data.name?.split(" ")[0];
  const stat = (loading: boolean, value: React.ReactNode) => (loading ? <Skeleton className="h-7 w-12" /> : value);

  return (
    <>
      <PageHeader
        title={`${greeting()}${name ? `, ${name}` : ""}`}
        description="Here’s where your applications and work stand today."
        actions={
          <ButtonLink href="/projects">
            <Search className="h-4 w-4" aria-hidden />
            Find projects
          </ButtonLink>
        }
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Applications"
          icon={FileText}
          value={stat(applications.loading, applications.data?.pagination.total ?? "—")}
        />
        <StatCard
          label="Shortlisted"
          icon={Star}
          value={stat(shortlisted.loading, shortlisted.data?.pagination.total ?? "—")}
        />
        <StatCard
          label="Active work"
          icon={Briefcase}
          value={stat(assignments.loading, assignments.data?.pagination.total ?? "—")}
        />
        <StatCard
          label="Earned"
          icon={Wallet}
          value={stat(payments.loading, payments.error ? "—" : formatMoney(released))}
          hint="Released payments"
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-6">
          <Section
            title="Active work"
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
                <Skeleton className="h-4 w-1/2" />
              </div>
            ) : assignments.data?.data.length ? (
              <RowList>
                {assignments.data.data.map((a) => (
                  <ListRow
                    key={a.id}
                    href={`/assignments/${a.id}`}
                    title={projects[a.project_id]?.title ?? "Project"}
                    meta={`Assigned ${relativeTime(a.assigned_date)}`}
                    aside={<StatusBadge status={a.status} />}
                  />
                ))}
              </RowList>
            ) : (
              <EmptyState
                icon={Briefcase}
                title="No active work yet"
                description="When a client selects your proposal, the assignment appears here."
              />
            )}
          </Section>

          <Section
            title="Recent applications"
            actions={
              <ButtonLink href="/applications" variant="ghost" size="sm">
                View all
              </ButtonLink>
            }
          >
            {applications.error ? (
              <ErrorState error={applications.error} onRetry={applications.reload} className="m-4 border-0" />
            ) : applications.loading ? (
              <div className="space-y-3 p-5">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            ) : applications.data?.data.length ? (
              <RowList>
                {applications.data.data.map((a) => (
                  <ListRow
                    key={a.id}
                    href={`/projects/${a.project_id}`}
                    title={projects[a.project_id]?.title ?? "Project"}
                    meta={`Applied ${relativeTime(a.created_at)}`}
                    aside={<StatusBadge status={a.status} />}
                  />
                ))}
              </RowList>
            ) : (
              <EmptyState
                icon={FileText}
                title="You haven’t applied yet"
                description="Browse open projects and send your first proposal."
                action={
                  <ButtonLink href="/projects" variant="secondary" size="sm">
                    Browse projects
                  </ButtonLink>
                }
              />
            )}
          </Section>
        </div>

        <div className="space-y-6">
          {!profile.loading && profile.data && (!profile.data.data.skills || !profile.data.data.college) && (
            <div className="card flex gap-4 p-5">
              <User className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
              <div>
                <p className="text-sm font-medium">Complete your profile</p>
                <p className="mt-1 text-[13px] text-muted">
                  Add your college and skills so clients understand your strengths, and to get better recommendations.
                </p>
                <ButtonLink href="/profile" variant="secondary" size="sm" className="mt-3">
                  Edit profile
                </ButtonLink>
              </div>
            </div>
          )}

          <Section
            title="Notifications"
            actions={
              <ButtonLink href="/notifications" variant="ghost" size="sm">
                View all
              </ButtonLink>
            }
          >
            {notifications.loading ? (
              <div className="space-y-3 p-5">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            ) : notifications.data?.data.length ? (
              <ul className="divide-y divide-line">
                {notifications.data.data.map((n) => (
                  <li key={n.id} className="px-5 py-3.5">
                    <p className="text-sm font-medium">{eventLabel(n.event)}</p>
                    <p className="mt-0.5 line-clamp-2 text-[13px] text-muted">{tidyMessage(n.message)}</p>
                    <p className="mt-1 text-xs text-muted">{relativeTime(n.created_at)}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState icon={Bell} title="You’re all caught up" description="Payment updates will appear here." />
            )}
          </Section>
        </div>
      </div>

      {!!recommended.data?.data.length && (
        <section className="mt-10">
          <div className="mb-4 flex items-end justify-between">
            <div>
              <h2 className="text-[15px] font-semibold">{skills[0] ? `Projects matching ${skills[0]}` : "Latest projects"}</h2>
              <p className="mt-0.5 text-[13px] text-muted">Open for applications</p>
            </div>
            <ButtonLink href="/projects" variant="ghost" size="sm">
              Browse all
            </ButtonLink>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {recommended.data.data.map((p) => (
              <ProjectCard key={p.id} project={p} />
            ))}
          </div>
        </section>
      )}
    </>
  );
}
