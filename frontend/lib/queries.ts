import { api } from "./api";
import type { Project } from "./types";

/**
 * A client's own projects. The projects API has no owner filter: for a client
 * it returns published projects plus their own, so this filters by client_id.
 * Covers the first 100 visible projects, which is ample for the prototype.
 */
export async function loadMyProjects(clientId: string): Promise<Project[]> {
  const { data } = await api.projects.list({ page_size: 100 });
  return data.filter((p) => p.client_id === clientId);
}
