"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { FolderKanban, Plus, Search, SlidersHorizontal, X } from "lucide-react";
import { api } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { formatMoney, relativeTime } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import { loadMyProjects } from "@/lib/queries";
import type { ProjectStatus } from "@/lib/types";
import { ProjectCard } from "@/components/project-card";
import { Button, ButtonLink } from "@/components/ui/button";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/feedback";
import { Input } from "@/components/ui/field";
import { PageHeader, Pager, Tabs } from "@/components/ui/layout";
import { StatusBadge } from "@/components/ui/status-badge";

const PAGE_SIZE = 12;

function useQueryState() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const read = (key: string) => params.get(key) ?? "";
  const update = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    router.replace(`${pathname}${next.size ? `?${next}` : ""}`, { scroll: false });
  };
  return { read, update };
}

/** Student marketplace and admin moderation list: server-side search and paging. */
function ProjectSearch({ admin }: { admin: boolean }) {
  const { read, update } = useQueryState();
  const query = read("query");
  const skill = read("skill");
  const category = read("category");
  const maxBudget = read("max_budget");
  const page = Number(read("page")) || 1;

  const [draft, setDraft] = useState({ query, skill, category, max_budget: maxBudget });
  const [showFilters, setShowFilters] = useState(Boolean(skill || category || maxBudget));
  useEffect(() => setDraft({ query, skill, category, max_budget: maxBudget }), [query, skill, category, maxBudget]);

  const result = useResource(
    () =>
      api.projects.list({
        query,
        skill,
        category,
        max_budget: maxBudget,
        page,
        page_size: PAGE_SIZE,
      }),
    [query, skill, category, maxBudget, page]
  );

  const filtered = Boolean(query || skill || category || maxBudget);
  const apply = (e: React.FormEvent) => {
    e.preventDefault();
    update({ ...draft, page: "" });
  };

  return (
    <>
      <PageHeader
        title={admin ? "Projects" : "Find projects"}
        description={
          admin
            ? "Every project on the platform, including drafts. Open one to close or remove it."
            : "Open projects from clients looking for student talent. Newest first."
        }
      />

      <form onSubmit={apply} className="card p-3 sm:p-4">
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
            <Input
              value={draft.query}
              onChange={(e) => setDraft({ ...draft, query: e.target.value })}
              placeholder="Search by title or description"
              aria-label="Search projects"
              className="pl-9"
            />
          </div>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => setShowFilters((s) => !s)}
              aria-expanded={showFilters}
              aria-controls="project-filters"
            >
              <SlidersHorizontal className="h-4 w-4" aria-hidden />
              Filters
            </Button>
            <Button type="submit" className="flex-1 sm:flex-none">
              Search
            </Button>
          </div>
        </div>
        {showFilters && (
          <div id="project-filters" className="mt-3 grid gap-2 border-t border-line pt-3 sm:grid-cols-3">
            <Input
              value={draft.skill}
              onChange={(e) => setDraft({ ...draft, skill: e.target.value })}
              placeholder="Skill, e.g. React"
              aria-label="Skill"
            />
            <Input
              value={draft.category}
              onChange={(e) => setDraft({ ...draft, category: e.target.value })}
              placeholder="Category, e.g. Web"
              aria-label="Category"
            />
            <Input
              value={draft.max_budget}
              onChange={(e) => setDraft({ ...draft, max_budget: e.target.value.replace(/[^\d.]/g, "") })}
              placeholder="Max budget"
              aria-label="Maximum budget"
              inputMode="decimal"
            />
          </div>
        )}
      </form>

      {filtered && (
        <div className="mt-4 flex flex-wrap items-center gap-2 text-[13px] text-muted">
          <span>
            {result.data ? `${result.data.pagination.total} result${result.data.pagination.total === 1 ? "" : "s"}` : "Searching…"}
          </span>
          <button
            type="button"
            onClick={() => update({ query: "", skill: "", category: "", max_budget: "", page: "" })}
            className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 hover:bg-surface-2 hover:text-fg"
          >
            <X className="h-3.5 w-3.5" aria-hidden /> Clear filters
          </button>
        </div>
      )}

      <div className="mt-6">
        {result.error ? (
          <ErrorState error={result.error} onRetry={result.reload} />
        ) : result.loading ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <SkeletonRows rows={3} className="contents" />
          </div>
        ) : result.data?.data.length ? (
          <>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {result.data.data.map((p) => (
                <ProjectCard key={p.id} project={p} showStatus={admin} />
              ))}
            </div>
            <Pager pagination={result.data.pagination} onPage={(p) => update({ page: String(p) })} />
          </>
        ) : (
          <div className="card">
            <EmptyState
              icon={Search}
              title={filtered ? "No projects match your search" : "No open projects right now"}
              description={filtered ? "Try fewer keywords or remove a filter." : "New projects are posted regularly — check back soon."}
            />
          </div>
        )}
      </div>
    </>
  );
}

const STATUS_TABS: Array<{ value: "ALL" | ProjectStatus; label: string }> = [
  { value: "ALL", label: "All" },
  { value: "DRAFT", label: "Drafts" },
  { value: "PUBLISHED", label: "Open" },
  { value: "IN_PROGRESS", label: "In progress" },
  { value: "COMPLETED", label: "Completed" },
  { value: "CLOSED", label: "Closed" },
];

function MyProjects() {
  const user = useUser();
  const [tab, setTab] = useState<"ALL" | ProjectStatus>("ALL");
  const projects = useResource(() => loadMyProjects(user.user_id), [user.user_id]);
  const all = projects.data ?? [];
  const shown = tab === "ALL" ? all : all.filter((p) => p.status === tab);

  return (
    <>
      <PageHeader
        title="My projects"
        description="Drafts, open listings and projects in progress."
        actions={
          <ButtonLink href="/projects/new">
            <Plus className="h-4 w-4" aria-hidden />
            Post a project
          </ButtonLink>
        }
      />
      <Tabs
        label="Filter by status"
        value={tab}
        onChange={setTab}
        options={STATUS_TABS.map((t) => ({
          ...t,
          count: projects.data ? (t.value === "ALL" ? all.length : all.filter((p) => p.status === t.value).length) : undefined,
        }))}
      />
      <div className="mt-4">
        {projects.error ? (
          <ErrorState error={projects.error} onRetry={projects.reload} />
        ) : projects.loading ? (
          <SkeletonRows rows={3} />
        ) : shown.length ? (
          <div className="card overflow-hidden">
            <ul className="divide-y divide-line">
              {shown.map((p) => (
                <li key={p.id}>
                  <Link
                    href={`/projects/${p.id}`}
                    className="flex flex-col gap-2 px-5 py-4 transition-colors hover:bg-surface-2/60 sm:flex-row sm:items-center sm:gap-6"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{p.title}</p>
                      <p className="mt-0.5 text-[13px] text-muted">
                        {p.category || "Uncategorised"} · updated {relativeTime(p.updated_at)}
                      </p>
                    </div>
                    <div className="flex items-center gap-4 text-sm">
                      <span className="font-medium tabular-nums">{formatMoney(p.budget)}</span>
                      <StatusBadge status={p.status} />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="card">
            <EmptyState
              icon={FolderKanban}
              title={tab === "ALL" ? "No projects yet" : "Nothing here"}
              description={tab === "ALL" ? "Post a project to start receiving proposals from students." : "No projects have this status."}
              action={
                tab === "ALL" && (
                  <ButtonLink href="/projects/new" size="sm">
                    Post a project
                  </ButtonLink>
                )
              }
            />
          </div>
        )}
      </div>
    </>
  );
}

function ProjectsPageInner() {
  const user = useUser();
  if (user.role === "CLIENT") return <MyProjects />;
  return <ProjectSearch admin={user.role === "ADMIN"} />;
}

export default function ProjectsPage() {
  return (
    <Suspense>
      <ProjectsPageInner />
    </Suspense>
  );
}
