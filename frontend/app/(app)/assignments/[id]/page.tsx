"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { CircleCheck, ExternalLink, FileUp, Plus, RotateCcw, Send } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { formatDate, formatDateTime, formatMoney, relativeTime, shortId } from "@/lib/format";
import { invalidateAssignment, invalidateProject, useResource } from "@/lib/hooks";
import type { Assignment, Project, Work } from "@/lib/types";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { Alert, EmptyState, ErrorState, Skeleton, SkeletonRows } from "@/components/ui/feedback";
import { Field, Input, Textarea } from "@/components/ui/field";
import { DescriptionList, PageHeader, Section } from "@/components/ui/layout";
import { StatusBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { PaymentPanel } from "./payment-panel";
import { ReviewPanel } from "./review-panel";

interface WorkDraft {
  title: string;
  description: string;
  submission_url: string;
}

function WorkDialog({
  open,
  initial,
  onClose,
  onSave,
}: {
  open: boolean;
  initial?: Work;
  onClose: () => void;
  onSave: (values: WorkDraft, submit: boolean) => Promise<void>;
}) {
  const [values, setValues] = useState<WorkDraft>({ title: "", description: "", submission_url: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState<"draft" | "submit" | null>(null);
  const [lastOpen, setLastOpen] = useState(false);

  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) {
      setValues({
        title: initial?.title ?? "",
        description: initial?.description ?? "",
        submission_url: initial?.submission_url ?? "",
      });
      setErrors({});
      setFormError(null);
    }
  }

  const run = async (submit: boolean) => {
    const next: Record<string, string> = {};
    if (!values.title.trim()) next.title = "Give this deliverable a title.";
    if (values.submission_url && !/^https?:\/\/\S+$/.test(values.submission_url.trim()))
      next.submission_url = "Enter a full URL starting with https://";
    if (submit && !values.submission_url.trim()) next.submission_url = "A link to the work is required to submit.";
    setErrors(next);
    if (Object.keys(next).length) return;
    setPending(submit ? "submit" : "draft");
    setFormError(null);
    try {
      await onSave(
        { title: values.title.trim(), description: values.description.trim(), submission_url: values.submission_url.trim() },
        submit
      );
      onClose();
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length) setErrors(err.fieldErrors);
      setFormError(err instanceof ApiError ? err.message : "The deliverable could not be saved.");
    } finally {
      setPending(null);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={pending ? () => undefined : onClose}
      title={initial ? "Update deliverable" : "New deliverable"}
      description="Share a link to your work (repository, design file, document or demo)."
      className="max-w-lg"
      footer={
        <>
          <Button variant="secondary" onClick={() => run(false)} loading={pending === "draft"} disabled={!!pending}>
            Save draft
          </Button>
          <Button onClick={() => run(true)} loading={pending === "submit"} disabled={!!pending}>
            <Send className="h-4 w-4" aria-hidden />
            Submit for review
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {formError && <Alert>{formError}</Alert>}
        <Field label="Title" error={errors.title}>
          {(id, d) => (
            <Input
              id={id}
              value={values.title}
              onChange={(e) => setValues({ ...values, title: e.target.value })}
              placeholder="e.g. First complete version"
              aria-invalid={!!errors.title}
              aria-describedby={d}
              maxLength={200}
            />
          )}
        </Field>
        <Field label="Link to the work" error={errors.submission_url}>
          {(id, d) => (
            <Input
              id={id}
              type="url"
              value={values.submission_url}
              onChange={(e) => setValues({ ...values, submission_url: e.target.value })}
              placeholder="https://"
              aria-invalid={!!errors.submission_url}
              aria-describedby={d}
            />
          )}
        </Field>
        <Field label="Notes for the client" error={errors.description} optional>
          {(id, d) => (
            <Textarea
              id={id}
              rows={4}
              value={values.description}
              onChange={(e) => setValues({ ...values, description: e.target.value })}
              aria-describedby={d}
            />
          )}
        </Field>
      </div>
    </Dialog>
  );
}

function FeedbackDialog({
  work,
  onClose,
  onSent,
}: {
  work: Work | null;
  onClose: () => void;
  onSent: () => void;
}) {
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const send = async () => {
    if (feedback.trim().length < 10) {
      setError("Explain what needs to change (at least 10 characters).");
      return;
    }
    setPending(true);
    try {
      await api.work.requestRevision(work!.id, feedback.trim());
      setFeedback("");
      onSent();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Feedback could not be sent.");
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog
      open={!!work}
      onClose={pending ? () => undefined : onClose}
      title="Request changes"
      description="The student will see your feedback and can resubmit."
      className="max-w-lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button onClick={send} loading={pending}>
            Send feedback
          </Button>
        </>
      }
    >
      <Field label="Feedback" error={error ?? undefined}>
        {(id, d) => (
          <Textarea id={id} rows={5} value={feedback} onChange={(e) => setFeedback(e.target.value)} aria-describedby={d} />
        )}
      </Field>
    </Dialog>
  );
}

function Deliverable({
  work,
  role,
  active,
  onEdit,
  onSubmit,
  onRequestChanges,
  onApprove,
  submitting,
}: {
  work: Work;
  role: "STUDENT" | "CLIENT";
  active: boolean;
  onEdit: () => void;
  onSubmit: () => void;
  onRequestChanges: () => void;
  onApprove: () => void;
  submitting: boolean;
}) {
  const editable = role === "STUDENT" && active && (work.status === "DRAFT" || work.status === "REVISION_REQUESTED");
  return (
    <li className="px-5 py-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold">{work.title}</p>
          <p className="mt-0.5 text-xs text-muted">
            {work.submitted_at ? `Submitted ${formatDateTime(work.submitted_at)}` : `Created ${relativeTime(work.created_at)}`}
            {work.reviewed_at && ` · reviewed ${relativeTime(work.reviewed_at)}`}
          </p>
        </div>
        <StatusBadge status={work.status} />
      </div>
      {work.description && <p className="mt-3 whitespace-pre-line text-sm text-muted">{work.description}</p>}
      {work.submission_url && (
        <a
          href={work.submission_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 inline-flex max-w-full items-center gap-1.5 truncate text-[13px] font-medium text-primary hover:underline"
        >
          <ExternalLink className="h-3.5 w-3.5 shrink-0" aria-hidden />
          <span className="truncate">{work.submission_url}</span>
        </a>
      )}
      {work.feedback && (
        <div className="mt-4 rounded-lg border-l-2 border-warning bg-warning-soft/60 px-3.5 py-3">
          <p className="text-xs font-medium text-warning">Client feedback</p>
          <p className="mt-1 whitespace-pre-line text-sm text-fg">{work.feedback}</p>
        </div>
      )}
      {editable && (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" onClick={onEdit}>
            Edit
          </Button>
          <Button size="sm" onClick={onSubmit} loading={submitting} disabled={!work.submission_url}>
            <Send className="h-3.5 w-3.5" aria-hidden />
            {work.status === "REVISION_REQUESTED" ? "Resubmit" : "Submit for review"}
          </Button>
        </div>
      )}
      {role === "CLIENT" && work.status === "SUBMITTED" && (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" onClick={onApprove}>
            <CircleCheck className="h-3.5 w-3.5" aria-hidden />
            Approve and release payment
          </Button>
          <Button size="sm" variant="secondary" onClick={onRequestChanges}>
            <RotateCcw className="h-3.5 w-3.5" aria-hidden />
            Request changes
          </Button>
        </div>
      )}
    </li>
  );
}

function Workspace({ assignment, project, reload }: { assignment: Assignment; project: Project | null; reload: () => void }) {
  const user = useUser();
  const toast = useToast();
  const role = user.role as "STUDENT" | "CLIENT";
  const active = assignment.status === "active";
  const work = useResource(() => api.work.list({ assignment_id: assignment.id, page_size: 100 }), [assignment.id]);
  const [dialog, setDialog] = useState<{ work?: Work } | null>(null);
  const [feedbackFor, setFeedbackFor] = useState<Work | null>(null);
  const [approving, setApproving] = useState<Work | null>(null);
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [paymentTick, setPaymentTick] = useState(0);

  const items = work.data?.data ?? [];

  const submit = async (w: Work) => {
    setSubmittingId(w.id);
    try {
      await api.work.submit(w.id);
      toast("Submitted for review. The client has been asked to review it.");
      work.reload();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Could not submit.", "error");
    } finally {
      setSubmittingId(null);
    }
  };

  const save = async (values: WorkDraft, andSubmit: boolean) => {
    let saved: Work;
    if (dialog?.work) {
      saved = (await api.work.update(dialog.work.id, values)).data;
    } else {
      saved = (
        await api.work.create({
          assignment_id: assignment.id,
          project_id: assignment.project_id,
          title: values.title,
          description: values.description,
          ...(values.submission_url ? { submission_url: values.submission_url } : {}),
        })
      ).data;
    }
    if (andSubmit) await api.work.submit(saved.id);
    toast(andSubmit ? "Submitted for review." : "Draft saved.");
    work.reload();
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <div className="min-w-0 space-y-6">
        <Section
          title="Deliverables"
          description={
            role === "STUDENT"
              ? "Submit your work for the client to review."
              : "Review what the student has submitted."
          }
          actions={
            role === "STUDENT" &&
            active && (
              <Button size="sm" onClick={() => setDialog({})}>
                <Plus className="h-3.5 w-3.5" aria-hidden />
                New
              </Button>
            )
          }
        >
          {work.error ? (
            <ErrorState error={work.error} onRetry={work.reload} className="m-4 border-0" />
          ) : work.loading ? (
            <SkeletonRows rows={1} className="p-4" />
          ) : items.length ? (
            <ul className="divide-y divide-line">
              {items.map((w) => (
                <Deliverable
                  key={w.id}
                  work={w}
                  role={role}
                  active={active}
                  submitting={submittingId === w.id}
                  onEdit={() => setDialog({ work: w })}
                  onSubmit={() => submit(w)}
                  onRequestChanges={() => setFeedbackFor(w)}
                  onApprove={() => setApproving(w)}
                />
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={FileUp}
              title="No deliverables yet"
              description={
                role === "STUDENT"
                  ? "Create a deliverable with a link to your work, then submit it for review."
                  : "You’ll be able to review work here once the student submits it."
              }
              action={
                role === "STUDENT" &&
                active && (
                  <Button size="sm" onClick={() => setDialog({})}>
                    Add deliverable
                  </Button>
                )
              }
            />
          )}
        </Section>
        <ReviewPanel assignment={assignment} />
      </div>

      <aside className="space-y-6">
        <section className="card">
          <DescriptionList
            items={[
              ["Project", project ? <Link key="p" href={`/projects/${project.id}`} className="hover:underline">{project.title}</Link> : "—"],
              ["Budget", project ? formatMoney(project.budget) : "—"],
              [role === "STUDENT" ? "Client" : "Student", <span key="c" className="font-mono">#{shortId(role === "STUDENT" ? assignment.client_id : assignment.student_id)}</span>],
              ["Started", formatDate(assignment.assigned_date)],
              ["Completed", formatDate(assignment.completion_date)],
            ]}
          />
        </section>
        <PaymentPanel assignment={assignment} project={project} refreshKey={paymentTick} />
      </aside>

      <WorkDialog open={!!dialog} initial={dialog?.work} onClose={() => setDialog(null)} onSave={save} />
      <FeedbackDialog
        work={feedbackFor}
        onClose={() => setFeedbackFor(null)}
        onSent={() => {
          toast("Feedback sent to the student.");
          work.reload();
        }}
      />
      <ConfirmDialog
        open={!!approving}
        onClose={() => setApproving(null)}
        title="Approve this work?"
        description={
          <>
            Approving releases the payment of{" "}
            <strong className="text-fg">{project ? formatMoney(project.budget) : "the project budget"}</strong> to the
            student through the development mock gateway, then marks the project and assignment complete. If no
            payment exists yet, one is created and processed first. This can’t be undone.
          </>
        }
        confirmLabel="Approve and release"
        onConfirm={async () => {
          const { data } = await api.work.approve(approving!.id);
          toast(`Work approved. Payment ${data.payment.status === "RELEASED" ? "released" : data.payment.status.toLowerCase()}.`);
          invalidateAssignment(assignment.id);
          invalidateProject(assignment.project_id);
          work.reload();
          setPaymentTick((t) => t + 1);
          reload();
        }}
      />
    </div>
  );
}

export default function AssignmentPage() {
  const { id } = useParams<{ id: string }>();
  const assignment = useResource(() => api.assignments.get(id), [id]);
  const a = assignment.data?.data;
  const project = useResource(() => api.projects.get(a!.project_id), [a?.project_id], !!a);

  return (
    <RoleGate allow={["STUDENT", "CLIENT"]}>
      {assignment.error ? (
        <>
          <PageHeader back={{ href: "/assignments", label: "Assignments" }} title="Assignment" />
          <ErrorState error={assignment.error} onRetry={assignment.reload} />
        </>
      ) : !a ? (
        <>
          <Skeleton className="mb-4 h-4 w-24" />
          <Skeleton className="mb-8 h-8 w-2/3" />
          <SkeletonRows rows={2} />
        </>
      ) : (
        <>
          <PageHeader
            back={{ href: "/assignments", label: "Assignments" }}
            title={
              <span className="flex flex-wrap items-center gap-3">
                {project.data?.data.title ?? "Assignment"}
                <StatusBadge status={a.status} />
              </span>
            }
            description={
              a.status === "completed"
                ? "This assignment is complete. Leave a review to finish."
                : "Deliverables, payment and reviews for this assignment."
            }
          />
          <Workspace assignment={a} project={project.data?.data ?? null} reload={assignment.reload} />
        </>
      )}
    </RoleGate>
  );
}
