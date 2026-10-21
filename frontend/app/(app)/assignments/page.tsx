"use client";

import Link from "next/link";
import { useState } from "react";
import { Briefcase } from "lucide-react";
import { api } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { formatDate, formatMoney, shortId } from "@/lib/format";
import { useProjects, useResource } from "@/lib/hooks";
import { RoleGate } from "@/components/role-gate";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/feedback";
import { PageHeader, Pager, Tabs } from "@/components/ui/layout";
import { StatusBadge } from "@/components/ui/status-badge";

export default function AssignmentsPage() {
  const user = useUser();
  const student = user.role === "STUDENT";
  const [status, setStatus] = useState<"" | "active" | "completed">("active");
  const [page, setPage] = useState(1);
  const result = useResource(() => api.assignments.list({ status, page, page_size: 20 }), [status, page]);
  const projects = useProjects(result.data?.data.map((a) => a.project_id) ?? []);

  return (
    <RoleGate allow={["STUDENT", "CLIENT"]}>
      <PageHeader
        title={student ? "My work" : "Assignments"}
        description={
          student
            ? "Projects you’ve been selected for. Submit deliverables and track approval."
            : "Students you’ve hired. Review deliverables and release payment."
        }
      />
      <Tabs
        label="Filter by status"
        value={status}
        onChange={(v) => {
          setStatus(v);
          setPage(1);
        }}
        options={[
          { value: "active", label: "Active" },
          { value: "completed", label: "Completed" },
          { value: "", label: "All" },
        ]}
      />
      <div className="mt-4">
        {result.error ? (
          <ErrorState error={result.error} onRetry={result.reload} />
        ) : result.loading ? (
          <SkeletonRows rows={3} />
        ) : result.data?.data.length ? (
          <>
            <ul className="grid gap-3 md:grid-cols-2">
              {result.data.data.map((a) => {
                const project = projects[a.project_id];
                return (
                  <li key={a.id}>
                    <Link
                      href={`/assignments/${a.id}`}
                      className="card block p-5 transition-colors hover:border-line-strong"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <p className="text-[15px] font-semibold leading-snug">{project?.title ?? "Project"}</p>
                        <StatusBadge status={a.status} />
                      </div>
                      <p className="mt-1 text-[13px] text-muted">
                        {student ? "Client" : "Student"}{" "}
                        <span className="font-mono">#{shortId(student ? a.client_id : a.student_id)}</span>
                      </p>
                      <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-4 text-[13px]">
                        <div>
                          <dt className="text-muted">Budget</dt>
                          <dd className="mt-0.5 font-medium tabular-nums">{project ? formatMoney(project.budget) : "—"}</dd>
                        </div>
                        <div>
                          <dt className="text-muted">{a.completion_date ? "Completed" : "Started"}</dt>
                          <dd className="mt-0.5 font-medium">{formatDate(a.completion_date ?? a.assigned_date)}</dd>
                        </div>
                      </dl>
                    </Link>
                  </li>
                );
              })}
            </ul>
            <Pager pagination={result.data.pagination} onPage={setPage} />
          </>
        ) : (
          <div className="card">
            <EmptyState
              icon={Briefcase}
              title={status === "completed" ? "No completed work yet" : "No assignments here"}
              description={
                student
                  ? "When a client selects your proposal, the assignment appears here."
                  : "Select a shortlisted applicant on one of your projects to start an assignment."
              }
              action={
                <ButtonLink href={student ? "/projects" : "/applications"} variant="secondary" size="sm">
                  {student ? "Find projects" : "Review applications"}
                </ButtonLink>
              }
            />
          </div>
        )}
      </div>
    </RoleGate>
  );
}
