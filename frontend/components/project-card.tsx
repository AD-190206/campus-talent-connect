import Link from "next/link";
import { CalendarDays, Tag } from "lucide-react";
import type { Project } from "@/lib/types";
import { deadlineLabel, formatMoney } from "@/lib/format";
import { SkillTag, StatusBadge } from "./ui/status-badge";

export function ProjectCard({ project, showStatus = false }: { project: Project; showStatus?: boolean }) {
  const skills = project.skills.slice(0, 4);
  const extra = project.skills.length - skills.length;
  return (
    <article className="card group relative flex flex-col p-5 transition-colors hover:border-line-strong">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-[15px] font-semibold leading-snug">
          <Link
            href={`/projects/${project.id}`}
            className="after:absolute after:inset-0 after:rounded-xl focus-visible:outline-none group-focus-within:underline"
          >
            {project.title}
          </Link>
        </h3>
        {showStatus && <StatusBadge status={project.status} />}
      </div>
      {project.category && (
        <p className="mt-1 inline-flex items-center gap-1 text-xs text-muted">
          <Tag className="h-3 w-3" aria-hidden />
          {project.category}
        </p>
      )}
      <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-muted">{project.description}</p>
      {skills.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {skills.map((s) => (
            <SkillTag key={s}>{s}</SkillTag>
          ))}
          {extra > 0 && <SkillTag>+{extra}</SkillTag>}
        </div>
      )}
      <div className="flex-1" />
      <div className="mt-5 flex items-center justify-between gap-3 border-t border-line pt-4 text-sm">
        <span className="font-semibold tabular-nums">{formatMoney(project.budget)}</span>
        <span className="inline-flex items-center gap-1.5 text-[13px] text-muted">
          <CalendarDays className="h-3.5 w-3.5" aria-hidden />
          {deadlineLabel(project.deadline)}
        </span>
      </div>
    </article>
  );
}
