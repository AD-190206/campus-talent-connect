"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { FileText, FolderKanban, Pencil, Undo2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { relativeTime } from "@/lib/format";
import { useProjects, useResource } from "@/lib/hooks";
import { loadMyProjects } from "@/lib/queries";
import type { Application } from "@/lib/types";
import { ApplicantList } from "@/components/applicant-list";
import { Button, ButtonLink } from "@/components/ui/button";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { Alert, EmptyState, ErrorState, SkeletonRows } from "@/components/ui/feedback";
import { Field, Select, Textarea } from "@/components/ui/field";
import { PageHeader, Pager, Tabs } from "@/components/ui/layout";
import { StatusBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";

type StatusFilter = "" | "submitted" | "shortlisted" | "selected" | "rejected" | "withdrawn";

const FILTERS: Array<{ value: StatusFilter; label: string }> = [
  { value: "", label: "All" },
  { value: "submitted", label: "Submitted" },
  { value: "shortlisted", label: "Shortlisted" },
  { value: "selected", label: "Selected" },
  { value: "rejected", label: "Not selected" },
  { value: "withdrawn", label: "Withdrawn" },
];

function EditProposalDialog({
  application,
  onClose,
  onSaved,
}: {
  application: Application | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [proposal, setProposal] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (application) {
      setProposal(application.proposal);
      setError(null);
    }
  }, [application]);

  const save = async () => {
    if (proposal.trim().length < 30) {
      setError("Write at least 30 characters.");
      return;
    }
    setPending(true);
    try {
      await api.applications.update(application!.id, { proposal: proposal.trim() });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save your proposal.");
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog
      open={!!application}
      onClose={onClose}
      title="Edit proposal"
      description="You can edit a proposal until the client shortlists it."
      className="max-w-lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button onClick={save} loading={pending}>
            Save proposal
          </Button>
        </>
      }
    >
      <Field label="Proposal" error={error ?? undefined}>
        {(id, d) => (
          <Textarea id={id} rows={8} value={proposal} onChange={(e) => setProposal(e.target.value)} aria-describedby={d} />
        )}
      </Field>
    </Dialog>
  );
}

function ApplicationsList({ admin }: { admin: boolean }) {
  const toast = useToast();
  const [status, setStatus] = useState<StatusFilter>("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Application | null>(null);
  const [withdrawing, setWithdrawing] = useState<Application | null>(null);
  const result = useResource(() => api.applications.list({ status, page, page_size: 20 }), [status, page]);
  const projects = useProjects(result.data?.data.map((a) => a.project_id) ?? []);

  return (
    <>
      <PageHeader
        title={admin ? "Applications" : "My applications"}
        description={admin ? "All applications across the platform." : "Track every proposal you’ve sent."}
        actions={
          !admin && (
            <ButtonLink href="/projects" variant="secondary">
              Find more projects
            </ButtonLink>
          )
        }
      />
      <Tabs
        label="Filter by status"
        value={status}
        onChange={(v) => {
          setStatus(v);
          setPage(1);
        }}
        options={FILTERS}
      />
      <div className="mt-4">
        {result.error ? (
          <ErrorState error={result.error} onRetry={result.reload} />
        ) : result.loading ? (
          <SkeletonRows rows={3} />
        ) : result.data?.data.length ? (
          <>
            <ul className="space-y-3">
              {result.data.data.map((a) => {
                const project = projects[a.project_id];
                return (
                  <li key={a.id} className="card p-5">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0">
                        <Link href={`/projects/${a.project_id}`} className="text-[15px] font-semibold hover:underline">
                          {project?.title ?? (project === null ? "Project unavailable" : "Loading project…")}
                        </Link>
                        <p className="mt-0.5 text-[13px] text-muted">
                          Applied {relativeTime(a.created_at)}
                          {a.updated_at !== a.created_at && ` · updated ${relativeTime(a.updated_at)}`}
                        </p>
                      </div>
                      <StatusBadge status={a.status} />
                    </div>
                    <p className="mt-3 line-clamp-3 whitespace-pre-line text-sm text-muted">{a.proposal}</p>
                    {a.status === "selected" && (
                      <Alert tone="success" className="mt-4">
                        You were selected. Open <Link href="/assignments" className="font-medium underline">My Work</Link> to
                        start delivering.
                      </Alert>
                    )}
                    {!admin && (a.status === "submitted" || a.status === "shortlisted") && (
                      <div className="mt-4 flex flex-wrap gap-2">
                        {a.status === "submitted" && (
                          <Button size="sm" variant="secondary" onClick={() => setEditing(a)}>
                            <Pencil className="h-3.5 w-3.5" aria-hidden />
                            Edit proposal
                          </Button>
                        )}
                        <Button size="sm" variant="ghost" onClick={() => setWithdrawing(a)}>
                          <Undo2 className="h-3.5 w-3.5" aria-hidden />
                          Withdraw
                        </Button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
            <Pager pagination={result.data.pagination} onPage={setPage} />
          </>
        ) : (
          <div className="card">
            <EmptyState
              icon={FileText}
              title={status ? "No applications with this status" : "No applications yet"}
              description={status ? "Try another filter." : "Find a project that fits your skills and send a proposal."}
              action={
                !status &&
                !admin && (
                  <ButtonLink href="/projects" size="sm">
                    Browse projects
                  </ButtonLink>
                )
              }
            />
          </div>
        )}
      </div>

      <EditProposalDialog
        application={editing}
        onClose={() => setEditing(null)}
        onSaved={() => {
          toast("Proposal updated.");
          result.reload();
        }}
      />
      <ConfirmDialog
        open={!!withdrawing}
        onClose={() => setWithdrawing(null)}
        title="Withdraw this application?"
        description="The client will no longer consider your proposal, and you can’t reapply to this project."
        confirmLabel="Withdraw"
        tone="danger"
        onConfirm={async () => {
          await api.applications.withdraw(withdrawing!.id);
          toast("Application withdrawn.");
          result.reload();
        }}
      />
    </>
  );
}

function ClientApplications() {
  const user = useUser();
  const projects = useResource(() => loadMyProjects(user.user_id), [user.user_id]);
  const reviewable = (projects.data ?? []).filter((p) => p.status !== "DRAFT");
  const [selected, setSelected] = useState("");

  useEffect(() => {
    if (!selected && reviewable.length) {
      setSelected((reviewable.find((p) => p.status === "PUBLISHED") ?? reviewable[0]).id);
    }
  }, [reviewable, selected]);

  const project = reviewable.find((p) => p.id === selected);

  return (
    <>
      <PageHeader title="Applications" description="Review proposals project by project." />
      {projects.error ? (
        <ErrorState error={projects.error} onRetry={projects.reload} />
      ) : projects.loading ? (
        <SkeletonRows rows={2} />
      ) : !reviewable.length ? (
        <div className="card">
          <EmptyState
            icon={FolderKanban}
            title="No published projects"
            description="Publish a project to start receiving applications."
            action={
              <ButtonLink href="/projects" size="sm">
                Go to my projects
              </ButtonLink>
            }
          />
        </div>
      ) : (
        <section className="card">
          <div className="flex flex-col gap-3 border-b border-line px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
            <Field label="Project" className="w-full sm:max-w-md">
              {(id) => (
                <Select id={id} value={selected} onChange={(e) => setSelected(e.target.value)}>
                  {reviewable.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            {project && (
              <div className="flex items-center gap-3">
                <StatusBadge status={project.status} />
                <ButtonLink href={`/projects/${project.id}`} variant="ghost" size="sm">
                  View project
                </ButtonLink>
              </div>
            )}
          </div>
          {project && project.status !== "PUBLISHED" && (
            <Alert tone="info" className="m-4">
              This project is no longer open, so applications are read-only.
            </Alert>
          )}
          {project && <ApplicantList key={project.id} projectId={project.id} canAct={project.status === "PUBLISHED"} />}
        </section>
      )}
    </>
  );
}

export default function ApplicationsPage() {
  const user = useUser();
  if (user.role === "CLIENT") return <ClientApplications />;
  return <ApplicationsList admin={user.role === "ADMIN"} />;
}
