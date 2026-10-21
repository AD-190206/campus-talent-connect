"use client";

import { ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useResource } from "@/lib/hooks";
import { ButtonLink } from "@/components/ui/button";
import { ProjectCard } from "@/components/project-card";

export function LandingAuthActions() {
  const { status } = useAuth();
  if (status === "authenticated") {
    return (
      <ButtonLink href="/dashboard" size="sm">
        Open dashboard
      </ButtonLink>
    );
  }
  return (
    <>
      <ButtonLink href="/login" size="sm" variant="ghost">
        Sign in
      </ButtonLink>
      <ButtonLink href="/register" size="sm">
        Get started
      </ButtonLink>
    </>
  );
}

/** Real listings for signed-in users; the projects API requires a session. */
export function LatestProjects() {
  const { status } = useAuth();
  const enabled = status === "authenticated";
  const { data } = useResource(() => api.projects.list({ page_size: 3 }), [], enabled);
  const projects = (data?.data ?? []).filter((p) => p.status === "PUBLISHED");

  if (!enabled || !projects.length) return null;

  return (
    <section className="mx-auto max-w-6xl px-4 pb-20 sm:px-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="label-caps">Open now</p>
          <h2 className="mt-2 text-xl font-semibold tracking-tight">Latest projects</h2>
        </div>
        <ButtonLink href="/projects" variant="ghost" size="sm">
          View all <ArrowRight className="h-3.5 w-3.5" aria-hidden />
        </ButtonLink>
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-3">
        {projects.map((p) => (
          <ProjectCard key={p.id} project={p} />
        ))}
      </div>
    </section>
  );
}
