"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight, Briefcase, CircleCheck, Pencil, Send, Trash2, XCircle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { deadlineLabel, formatDate, formatMoney, relativeTime } from "@/lib/format";
import { invalidateProject, useResource } from "@/lib/hooks";
import type { Project } from "@/lib/types";
import { ApplicantList } from "@/components/applicant-list";
import { Button, ButtonLink } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Alert, ErrorState, Skeleton, SkeletonRows } from "@/components/ui/feedback";
import { Field, Input, Textarea } from "@/components/ui/field";
import { DescriptionList, PageHeader, Section } from "@/components/ui/layout";
import { SkillTag, StatusBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";

function ApplyPanel({ project }: { project: Project }) {
  const toast = useToast();
  const existing = useResource(() => api.applications.list({ project_id: project.id, page_size: 1 }), [project.id]);
  const [proposal, setProposal] = useState("");
  const [resumeUrl, setResumeUrl] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const mine = existing.data?.data[0];

  if (existing.loading)
    return (
      <div className="space-y-3 p-5">
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-20 w-full" />
      </div>
    );

  if (mine)
    return (
      <div className="p-5">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-muted">Applied {relativeTime(mine.created_at)}</p>
          <StatusBadge status={mine.status} />
        </div>
        <p className="mt-3 line-clamp-4 whitespace-pre-line text-sm text-fg">{mine.proposal}</p>
        <ButtonLink href="/applications" variant="secondary" size="sm" className="mt-4 w-full">
          Manage application
        </ButtonLink>
      </div>
    );

  if (project.status !== "PUBLISHED")
    return <p className="p-5 text-sm text-muted">This project isn’t accepting applications.</p>;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const next: Record<string, string> = {};
    if (proposal.trim().length < 30) next.proposal = "Write at least 30 characters about your approach.";
    if (resumeUrl && !/^https?:\/\/\S+$/.test(resumeUrl.trim())) next.resume_url = "Enter a full URL starting with https://";
    setErrors(next);
    if (Object.keys(next).length) return;
    setPending(true);
    setFormError(null);
    try {
      await api.applications.create({
        project_id: project.id,
        proposal: proposal.trim(),
        ...(resumeUrl.trim() ? { resume_url: resumeUrl.trim() } : {}),
      });
      toast("Proposal sent. You’ll see status updates under My Applications.");
      existing.reload();
    } catch (err) {
      if (err instanceof ApiError && err.code === "DUPLICATE_APPLICATION") existing.reload();
      else if (err instanceof ApiError && Object.keys(err.fieldErrors).length) setErrors(err.fieldErrors);
      else setFormError(err instanceof ApiError ? err.message : "Your proposal could not be sent.");
    } finally {
      setPending(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate className="space-y-4 p-5">
      {formError && <Alert>{formError}</Alert>}
      <Field label="Your proposal" error={errors.proposal} hint="How you’d approach the work and relevant experience.">
        {(id, d) => (
          <Textarea
            id={id}
            rows={6}
            value={proposal}
            onChange={(e) => setProposal(e.target.value)}
            aria-invalid={!!errors.proposal}
            aria-describedby={d}
          />
        )}
      </Field>
      <Field label="Résumé or portfolio link" error={errors.resume_url} optional>
        {(id, d) => (
          <Input
            id={id}
            type="url"
            value={resumeUrl}
            onChange={(e) => setResumeUrl(e.target.value)}
            placeholder="https://"
            aria-invalid={!!errors.resume_url}
            aria-describedby={d}
          />
        )}
      </Field>
      <Button type="submit" className="w-full" loading={pending}>
        <Send className="h-4 w-4" aria-hidden />
        Send proposal
      </Button>
    </form>
  );
}

function AssignmentLink({ projectId }: { projectId: string }) {
  const assignments = useResource(() => api.assignments.list({ project_id: projectId, page_size: 1 }), [projectId]);
  const assignment = assignments.data?.data[0];
  if (!assignment) return null;
  return (
    <Link
      href={`/assignments/${assignment.id}`}
      className="card flex items-center gap-4 p-4 transition-colors hover:border-line-strong"
    >
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-accent-fg">
        <Briefcase className="h-4 w-4" aria-hidden />
      </span>
      <div className="flex-1">
        <p className="text-sm font-medium">Assignment</p>
        <p className="text-[13px] text-muted">Deliverables, payment and reviews</p>
      </div>
      <StatusBadge status={assignment.status} />
      <ArrowRight className="h-4 w-4 text-muted" aria-hidden />
    </Link>
  );
}

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const user = useUser();
  const router = useRouter();
  const toast = useToast();
  const project = useResource(() => api.projects.get(id), [id]);
  const [confirm, setConfirm] = useState<"publish" | "close" | "delete" | null>(null);

  if (project.error)
    return (
      <>
        <PageHeader back={{ href: "/projects", label: "Projects" }} title="Project" />
        <ErrorState error={project.error} onRetry={project.error.status === 404 ? undefined : project.reload} />
      </>
    );

  const p = project.data?.data;
  if (!p)
    return (
      <>
        <Skeleton className="mb-4 h-4 w-24" />
        <Skeleton className="mb-8 h-8 w-2/3" />
        <SkeletonRows rows={2} />
      </>
    );

  const owner = user.role === "CLIENT" && p.client_id === user.user_id;
  const admin = user.role === "ADMIN";
  const editable = owner && (p.status === "DRAFT" || p.status === "PUBLISHED");
  const closable = (owner || admin) && ["DRAFT", "PUBLISHED", "IN_PROGRESS"].includes(p.status);
  const deletable = (owner || admin) && ["DRAFT", "CLOSED", "ARCHIVED"].includes(p.status);

  const refresh = () => {
    invalidateProject(id);
    project.reload();
  };

  return (
    <>
      <PageHeader
        back={{ href: "/projects", label: user.role === "CLIENT" ? "My projects" : "Projects" }}
        title={
          <span className="flex flex-wrap items-center gap-3">
            {p.title}
            <StatusBadge status={p.status} />
          </span>
        }
        description={`${p.category || "Uncategorised"} · posted ${formatDate(p.created_at)}`}
        actions={
          (owner || admin) && (
            <>
              {editable && (
                <ButtonLink href={`/projects/${id}/edit`} variant="secondary">
                  <Pencil className="h-4 w-4" aria-hidden />
                  Edit
                </ButtonLink>
              )}
              {owner && p.status === "DRAFT" && (
                <Button onClick={() => setConfirm("publish")}>
                  <CircleCheck className="h-4 w-4" aria-hidden />
                  Publish
                </Button>
              )}
              {closable && (
                <Button variant="secondary" onClick={() => setConfirm("close")}>
                  <XCircle className="h-4 w-4" aria-hidden />
                  Close
                </Button>
              )}
              {deletable && (
                <Button variant="danger" onClick={() => setConfirm("delete")}>
                  <Trash2 className="h-4 w-4" aria-hidden />
                  Delete
                </Button>
              )}
            </>
          )
        }
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="min-w-0 space-y-6">
          <section className="card p-5 sm:p-6">
            <h2 className="label-caps">About the project</h2>
            <p className="mt-3 whitespace-pre-line text-[15px] leading-relaxed text-fg">{p.description}</p>
            {p.skills.length > 0 && (
              <>
                <h2 className="label-caps mt-6">Skills</h2>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {p.skills.map((s) => (
                    <SkillTag key={s}>{s}</SkillTag>
                  ))}
                </div>
              </>
            )}
          </section>

          {(owner || admin) && p.status !== "DRAFT" && (
            <Section
              title="Applicants"
              description={
                owner
                  ? "Shortlist promising proposals, then select one student to start the assignment."
                  : "Read-only view for administrators."
              }
            >
              <ApplicantList projectId={p.id} canAct={owner && p.status === "PUBLISHED"} />
            </Section>
          )}
          {owner && p.status === "DRAFT" && (
            <Alert tone="info">This project is a draft. Publish it to start receiving applications.</Alert>
          )}
        </div>

        <aside className="space-y-6">
          <section className="card">
            <DescriptionList
              items={[
                ["Budget", <span key="b" className="tabular-nums">{formatMoney(p.budget)}</span>],
                ["Deadline", deadlineLabel(p.deadline)],
                ["Category", p.category || "—"],
                ["Last updated", relativeTime(p.updated_at)],
              ]}
            />
          </section>

          {user.role === "STUDENT" && (
            <Section title="Apply">
              <ApplyPanel project={p} />
            </Section>
          )}

          {(owner || admin || user.role === "STUDENT") &&
            ["IN_PROGRESS", "COMPLETED"].includes(p.status) && <AssignmentLink projectId={p.id} />}
        </aside>
      </div>

      <ConfirmDialog
        open={confirm === "publish"}
        onClose={() => setConfirm(null)}
        title="Publish this project?"
        description="Students will be able to find it and send proposals."
        confirmLabel="Publish"
        onConfirm={async () => {
          await api.projects.publish(id);
          toast("Project published.");
          refresh();
        }}
      />
      <ConfirmDialog
        open={confirm === "close"}
        onClose={() => setConfirm(null)}
        title="Close this project?"
        description="It will stop accepting applications and can’t be reopened."
        confirmLabel="Close project"
        tone="danger"
        onConfirm={async () => {
          await api.projects.close(id);
          toast("Project closed.");
          refresh();
        }}
      />
      <ConfirmDialog
        open={confirm === "delete"}
        onClose={() => setConfirm(null)}
        title="Delete this project?"
        description="The project will be permanently removed. This can’t be undone."
        confirmLabel="Delete"
        tone="danger"
        onConfirm={async () => {
          await api.projects.remove(id);
          invalidateProject(id);
          toast("Project deleted.");
          router.push("/projects");
        }}
      />
    </>
  );
}
