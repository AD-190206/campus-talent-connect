"use client";

import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import { PageHeader } from "@/components/ui/layout";
import { ProjectForm } from "@/components/project-form";
import { RoleGate } from "@/components/role-gate";

export default function NewProjectPage() {
  const router = useRouter();
  const toast = useToast();

  return (
    <RoleGate allow={["CLIENT"]}>
      <div className="mx-auto max-w-3xl">
        <PageHeader
          back={{ href: "/projects", label: "My projects" }}
          title="Post a project"
          description="Save it as a draft to review later, or publish it so students can apply right away."
        />
        <ProjectForm
          submitLabel="Publish project"
          onSubmit={async (values) => {
            const { data } = await api.projects.create(values);
            try {
              await api.projects.publish(data.id);
              toast("Project published. Students can now apply.");
            } catch {
              toast("Saved as a draft, but it couldn’t be published yet.", "error");
            }
            router.push(`/projects/${data.id}`);
          }}
          secondary={{
            label: "Save as draft",
            onSubmit: async (values) => {
              const { data } = await api.projects.create(values);
              toast("Draft saved.");
              router.push(`/projects/${data.id}`);
            },
          }}
          onCancel={() => router.push("/projects")}
        />
      </div>
    </RoleGate>
  );
}
