"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ExternalLink, Inbox, Star, UserCheck, X } from "lucide-react";
import { api } from "@/lib/api";
import { formatDate, initials, relativeTime, shortId } from "@/lib/format";
import { invalidateProject, useResource } from "@/lib/hooks";
import type { Application, ApplicationStatus } from "@/lib/types";
import { Button } from "./ui/button";
import { ConfirmDialog } from "./ui/dialog";
import { EmptyState, ErrorState, SkeletonRows } from "./ui/feedback";
import { Tabs } from "./ui/layout";
import { StatusBadge } from "./ui/status-badge";
import { useToast } from "./ui/toast";

type Filter = "open" | ApplicationStatus | "all";

function ApplicantCard({
  application,
  canAct,
  onShortlist,
  onReject,
  onSelect,
  busy,
}: {
  application: Application;
  canAct: boolean;
  onShortlist: () => void;
  onReject: () => void;
  onSelect: () => void;
  busy: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const long = application.proposal.length > 280;
  const open = application.status === "submitted" || application.status === "shortlisted";

  return (
    <li className="px-5 py-5">
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-surface-2 text-xs font-semibold text-muted"
        >
          {initials(shortId(application.student_id))}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-sm font-medium">
                Applicant <span className="font-mono text-[13px] text-muted">#{shortId(application.student_id)}</span>
              </p>
              <p className="text-xs text-muted" title={formatDate(application.created_at)}>
                Applied {relativeTime(application.created_at)}
              </p>
            </div>
            <StatusBadge status={application.status} />
          </div>
          <p className={`mt-3 whitespace-pre-line text-sm leading-relaxed text-fg ${!expanded && long ? "line-clamp-4" : ""}`}>
            {application.proposal}
          </p>
          {long && (
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              className="mt-1 text-[13px] font-medium text-primary hover:underline"
            >
              {expanded ? "Show less" : "Read full proposal"}
            </button>
          )}
          {application.resume_url && (
            <a
              href={application.resume_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 inline-flex items-center gap-1.5 text-[13px] font-medium text-primary hover:underline"
            >
              Résumé / portfolio <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            </a>
          )}
          {canAct && open && (
            <div className="mt-4 flex flex-wrap gap-2">
              {application.status === "submitted" && (
                <Button size="sm" variant="secondary" onClick={onShortlist} loading={busy}>
                  <Star className="h-3.5 w-3.5" aria-hidden />
                  Shortlist
                </Button>
              )}
              {application.status === "shortlisted" && (
                <Button size="sm" onClick={onSelect} disabled={busy}>
                  <UserCheck className="h-3.5 w-3.5" aria-hidden />
                  Select student
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={onReject} disabled={busy}>
                <X className="h-3.5 w-3.5" aria-hidden />
                Decline
              </Button>
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

/** Applicants for one project. `canAct` is true for the owning client. */
export function ApplicantList({ projectId, canAct }: { projectId: string; canAct: boolean }) {
  const router = useRouter();
  const toast = useToast();
  const [filter, setFilter] = useState<Filter>("open");
  const [busy, setBusy] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<{ type: "reject" | "select"; application: Application } | null>(null);
  const result = useResource(() => api.applications.list({ project_id: projectId, page_size: 100 }), [projectId]);

  const all = result.data?.data ?? [];
  const isOpen = (a: Application) => a.status === "submitted" || a.status === "shortlisted";
  const shown = all.filter((a) => (filter === "all" ? true : filter === "open" ? isOpen(a) : a.status === filter));

  const shortlist = async (application: Application) => {
    setBusy(application.id);
    try {
      await api.applications.shortlist(application.id);
      toast("Applicant shortlisted.");
      result.reload();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Could not shortlist.", "error");
    } finally {
      setBusy(null);
    }
  };

  if (result.error) return <ErrorState error={result.error} onRetry={result.reload} className="m-4 border-0" />;
  if (result.loading) return <SkeletonRows rows={2} className="p-4" />;

  return (
    <>
      {all.length > 0 && (
        <div className="border-b border-line px-4 py-3">
          <Tabs
            label="Filter applicants"
            value={filter}
            onChange={setFilter}
            options={[
              { value: "open", label: "Open", count: all.filter(isOpen).length },
              { value: "shortlisted", label: "Shortlisted", count: all.filter((a) => a.status === "shortlisted").length },
              { value: "selected", label: "Selected", count: all.filter((a) => a.status === "selected").length },
              { value: "all", label: "All", count: all.length },
            ]}
          />
        </div>
      )}
      {shown.length ? (
        <ul className="divide-y divide-line">
          {shown.map((a) => (
            <ApplicantCard
              key={a.id}
              application={a}
              canAct={canAct}
              busy={busy === a.id}
              onShortlist={() => shortlist(a)}
              onReject={() => setConfirm({ type: "reject", application: a })}
              onSelect={() => setConfirm({ type: "select", application: a })}
            />
          ))}
        </ul>
      ) : (
        <EmptyState
          icon={Inbox}
          title={all.length ? "No applicants in this view" : "No applications yet"}
          description={all.length ? "Try another filter." : "Proposals from students will appear here once the project is open."}
        />
      )}

      <ConfirmDialog
        open={confirm?.type === "reject"}
        onClose={() => setConfirm(null)}
        title="Decline this applicant?"
        description="The student will see their application as not selected. This can’t be undone."
        confirmLabel="Decline"
        tone="danger"
        onConfirm={async () => {
          await api.applications.reject(confirm!.application.id);
          toast("Applicant declined.");
          result.reload();
        }}
      />
      <ConfirmDialog
        open={confirm?.type === "select"}
        onClose={() => setConfirm(null)}
        title="Select this student?"
        description={
          <>
            This creates the assignment and moves the project to <strong>In progress</strong>. All other open
            applications for this project will be declined. This can’t be undone.
          </>
        }
        confirmLabel="Select and start"
        onConfirm={async () => {
          const { data } = await api.applications.select(confirm!.application.id);
          invalidateProject(projectId);
          toast("Student selected. The assignment has started.");
          router.push(`/assignments/${data.assignment.id}`);
        }}
      />
    </>
  );
}
