"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import type { Assignment, Project } from "./types";

export interface Resource<T> {
  data: T | undefined;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
}

/** Run an async loader and track loading/error state. Re-runs when deps change. */
export function useResource<T>(loader: () => Promise<T>, deps: unknown[], enabled = true): Resource<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [tick, setTick] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    loaderRef
      .current()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err : new ApiError(500, { error: String(err) }));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, enabled]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}

// Small per-page-load caches so lists can show project titles without
// refetching the same project for every row.
const projectCache = new Map<string, Promise<Project | null>>();
const assignmentCache = new Map<string, Promise<Assignment | null>>();

export function fetchProject(id: string) {
  if (!projectCache.has(id)) {
    projectCache.set(
      id,
      api.projects
        .get(id)
        .then((r) => r.data)
        .catch(() => null)
    );
  }
  return projectCache.get(id)!;
}

export function fetchAssignment(id: string) {
  if (!assignmentCache.has(id)) {
    assignmentCache.set(
      id,
      api.assignments
        .get(id)
        .then((r) => r.data)
        .catch(() => null)
    );
  }
  return assignmentCache.get(id)!;
}

export function invalidateProject(id?: string) {
  if (id) projectCache.delete(id);
  else projectCache.clear();
}

export function invalidateAssignment(id?: string) {
  if (id) assignmentCache.delete(id);
  else assignmentCache.clear();
}

/** Resolve project records for a set of IDs (missing/forbidden → null). */
export function useProjects(ids: string[]) {
  const key = Array.from(new Set(ids)).sort().join(",");
  const [map, setMap] = useState<Record<string, Project | null>>({});

  useEffect(() => {
    let cancelled = false;
    const unique = key ? key.split(",") : [];
    Promise.all(unique.map(async (id) => [id, await fetchProject(id)] as const)).then((entries) => {
      if (!cancelled) setMap(Object.fromEntries(entries));
    });
    return () => {
      cancelled = true;
    };
  }, [key]);

  return map;
}
