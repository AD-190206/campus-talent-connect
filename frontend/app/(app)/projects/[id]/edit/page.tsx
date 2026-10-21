"use client";

import { useParams, useRouter } from "next/navigation";
import { Lock } from "lucide-react";
import { api } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { invalidateProject, useResource } from "@/lib/hooks";
import { ProjectForm } from "@/components/project-form";
import { RoleGate } from "@/components/role-gate";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/layout";
import { useToast } from "@/components/ui/toast";

export default function EditProjectPage() {
  const { id } = useParams<{ id: string }>();
  const user = useUser();
  const router = useRouter();
  const toast = useToast();
  const project = useResource(() => api.projects.get(id), [id]);
  const p = project.data?.data;

  let body: React.ReactNode;
  if (project.error) body = <ErrorState error={project.error} onRetry={project.reload} />;
  else if (!p) body = <SkeletonRows rows={2} />;
  else if (p.client_id !== user.user_id || !["DRAFT", "PUBLISHED"].includes(p.status))
    body = (
      <div className="card">
        <EmptyState
          icon={Lock}
          title="This project can’t be edited"
          description="Only the owner can edit a project, and only while it is a draft or open. The budget is fixed once work starts."
          action={
            <ButtonLink href={`/projects/${id}`} variant="secondary">
              Back to project
            </ButtonLink>
          }
        />
      </div>
    );
  else
    body = (
      <ProjectForm
        initial={{
          title: p.title,
          description: p.description,
          skills: p.skills,
          category: p.category,
          budget: p.budget,
          deadline: p.deadline,
        }}
        submitLabel="Save changes"
        onSubmit={async (values) => {
          await api.projects.update(id, values);
          invalidateProject(id);
          toast("Project updated.");
          router.push(`/projects/${id}`);
        }}
        onCancel={() => router.push(`/projects/${id}`)}
      />
    );

  return (
    <RoleGate allow={["CLIENT"]}>
      <div className="mx-auto max-w-3xl">
        <PageHeader back={{ href: `/projects/${id}`, label: "Project" }} title="Edit project" />
        {body}
      </div>
    </RoleGate>
  );
}
