// Client for the CTC API gateway (docs/api/API_CONTRACT.md).
//
// Success bodies are {data, message[, pagination]}; errors are
// {error, code, details}. `request` resolves with the success envelope and
// throws ApiError for the error envelope. An expired access token is
// refreshed once (refresh tokens rotate) before the request is retried; if
// that fails a "ctc:session-expired" event is dispatched.

import type {
  Application,
  Assignment,
  ClientProfile,
  Collection,
  Envelope,
  ErrorEnvelope,
  Notification,
  Payment,
  Profile,
  Project,
  ProjectInput,
  Review,
  SessionUser,
  StudentProfile,
  Tokens,
  UserAccount,
  Work,
} from "./types";

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api"
).replace(/\/$/, "");

const TOKEN_KEY = "ctc.session";
export const SESSION_EXPIRED_EVENT = "ctc:session-expired";

export class ApiError extends Error {
  status: number;
  code: string;
  details: ErrorEnvelope["details"];

  constructor(status: number, body: Partial<ErrorEnvelope> | null) {
    super(body?.error || `Request failed (HTTP ${status}).`);
    this.status = status;
    this.code = body?.code || (status === 0 ? "NETWORK_ERROR" : "REQUEST_ERROR");
    this.details = body?.details || {};
  }

  /** Field errors flattened to one message per field. */
  get fieldErrors(): Record<string, string> {
    const fields = this.details.fields || {};
    return Object.fromEntries(
      Object.entries(fields).map(([k, v]) => [k, Array.isArray(v) ? v.join(" ") : String(v)])
    );
  }
}

export interface StoredSession extends Tokens {
  user: SessionUser;
}

export function getSession(): StoredSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(TOKEN_KEY);
    return raw ? (JSON.parse(raw) as StoredSession) : null;
  } catch {
    return null;
  }
}

export function setSession(session: StoredSession | null) {
  if (typeof window === "undefined") return;
  try {
    if (session) window.localStorage.setItem(TOKEN_KEY, JSON.stringify(session));
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage unavailable (private mode); the session lives for this page only.
  }
}

type Params = Record<string, string | number | boolean | undefined | null>;

function withQuery(path: string, params?: Params) {
  if (!params) return path;
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  const qs = query.toString();
  return qs ? `${path}?${qs}` : path;
}

async function send(method: string, path: string, body: unknown, token?: string) {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, {
      error: "Cannot reach the server. Check your connection and that the API gateway is running.",
      code: "NETWORK_ERROR",
    });
  }

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // Non-JSON body; reported through ApiError.
  }
  return { response, payload };
}

let refreshInFlight: Promise<StoredSession | null> | null = null;

function refreshSession(): Promise<StoredSession | null> {
  // Refresh tokens rotate, so concurrent 401s must share one refresh call.
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const session = getSession();
      if (!session?.refresh_token) return null;
      const { response, payload } = await send("POST", "/auth/refresh/", {
        refresh_token: session.refresh_token,
      });
      if (!response.ok) return null;
      const next = { ...session, ...(payload as Envelope<Tokens>).data, user: session.user };
      setSession(next);
      return next;
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

interface RequestOptions {
  body?: unknown;
  params?: Params;
  auth?: boolean;
}

export async function request<T>(
  method: string,
  path: string,
  { body, params, auth = true }: RequestOptions = {}
): Promise<T> {
  const url = withQuery(path, params);
  let session = auth ? getSession() : null;
  let { response, payload } = await send(method, url, body, session?.access_token);

  if (response.status === 401 && auth && session) {
    session = await refreshSession();
    if (session) {
      ({ response, payload } = await send(method, url, body, session.access_token));
    } else {
      setSession(null);
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
  }

  if (!response.ok) throw new ApiError(response.status, payload as ErrorEnvelope | null);
  return payload as T;
}

const get = <T>(path: string, params?: Params) => request<T>("GET", path, { params });
const post = <T>(path: string, body: unknown = {}) => request<T>("POST", path, { body });
const patch = <T>(path: string, body: unknown) => request<T>("PATCH", path, { body });

export interface PageParams extends Params {
  page?: number;
  page_size?: number;
}

export interface RegisterInput {
  email: string;
  password: string;
  role: "STUDENT" | "CLIENT";
  name?: string;
  college?: string;
  skills?: string;
  portfolio_url?: string;
  phone?: string;
  company_name?: string;
  contact_person?: string;
}

export const api = {
  auth: {
    register: (body: RegisterInput) =>
      request<Envelope<SessionUser>>("POST", "/auth/register/", { body, auth: false }),
    login: (email: string, password: string) =>
      request<Envelope<Tokens & { user: SessionUser }>>("POST", "/auth/login/", {
        body: { email, password },
        auth: false,
      }),
    logout: (refreshToken: string) =>
      request<Envelope<object>>("POST", "/auth/logout/", {
        body: { refresh_token: refreshToken },
        auth: false,
      }),
    me: () => get<Envelope<SessionUser>>("/auth/me/"),
  },
  users: {
    get: (id: string) => get<Envelope<UserAccount>>(`/users/${id}/`),
    update: (id: string, body: { email: string }) => patch<Envelope<SessionUser>>(`/users/${id}/`, body),
    profile: <P extends Profile = Profile>(id: string) => get<Envelope<P>>(`/users/${id}/profile/`),
    updateProfile: <P extends Profile = Profile>(
      id: string,
      body: Partial<StudentProfile> | Partial<ClientProfile>
    ) => patch<Envelope<P>>(`/users/${id}/profile/`, body),
    deactivate: (id: string) => post<Envelope<{ user_id: string; is_active: boolean }>>(`/users/${id}/deactivate/`),
  },
  projects: {
    list: (params?: PageParams & { query?: string; skill?: string; category?: string; max_budget?: string }) =>
      get<Collection<Project>>("/projects/", params),
    create: (body: ProjectInput) => post<Envelope<Project>>("/projects/", body),
    get: (id: string) => get<Envelope<Project>>(`/projects/${id}/`),
    update: (id: string, body: Partial<ProjectInput>) => patch<Envelope<Project>>(`/projects/${id}/`, body),
    remove: (id: string) => request<Envelope<{ id: string }>>("DELETE", `/projects/${id}/`),
    publish: (id: string) => post<Envelope<Project>>(`/projects/${id}/publish/`),
    close: (id: string) => post<Envelope<Project>>(`/projects/${id}/close/`),
  },
  applications: {
    list: (params?: PageParams & { project_id?: string; student_id?: string; status?: string }) =>
      get<Collection<Application>>("/applications/", params),
    create: (body: { project_id: string; proposal: string; resume_url?: string }) =>
      post<Envelope<Application>>("/applications/", body),
    get: (id: string) => get<Envelope<Application>>(`/applications/${id}/`),
    update: (id: string, body: { proposal?: string; resume_url?: string }) =>
      patch<Envelope<Application>>(`/applications/${id}/`, body),
    shortlist: (id: string) => post<Envelope<Application>>(`/applications/${id}/shortlist/`),
    reject: (id: string) => post<Envelope<Application>>(`/applications/${id}/reject/`),
    withdraw: (id: string) => post<Envelope<Application>>(`/applications/${id}/withdraw/`),
    select: (id: string) =>
      post<Envelope<{ application: Application; assignment: Assignment }>>(`/applications/${id}/select/`),
  },
  assignments: {
    list: (params?: PageParams & { project_id?: string; status?: string }) =>
      get<Collection<Assignment>>("/assignments/", params),
    get: (id: string) => get<Envelope<Assignment>>(`/assignments/${id}/`),
  },
  work: {
    list: (params?: PageParams & { assignment_id?: string; status?: string }) =>
      get<Collection<Work>>("/work/", params),
    create: (body: {
      assignment_id: string;
      project_id: string;
      title: string;
      description?: string;
      submission_url?: string;
    }) => post<Envelope<Work>>("/work/", body),
    update: (id: string, body: Partial<Pick<Work, "title" | "description" | "submission_url">>) =>
      patch<Envelope<Work>>(`/work/${id}/`, body),
    submit: (id: string) => post<Envelope<Work>>(`/work/${id}/submit/`),
    requestRevision: (id: string, feedback: string) =>
      post<Envelope<Work>>(`/work/${id}/reject/`, { feedback }),
    approve: (id: string) =>
      post<Envelope<Work & { payment: { id: string; status: string } }>>(`/work/${id}/approve/`),
  },
  reviews: {
    list: (params?: PageParams & { assignment_id?: string }) => get<Collection<Review>>("/reviews/", params),
    create: (body: { assignment_id: string; reviewee_id: string; rating: number; comment?: string }) =>
      post<Envelope<Review>>("/reviews/", body),
  },
  payments: {
    list: (params?: PageParams & { assignment_id?: string; status?: string }) =>
      get<Collection<Payment>>("/payments/", params),
    create: (body: { assignment_id: string; payee_id: string; idempotency_key: string }) =>
      post<Envelope<Payment>>("/payments/", body),
    process: (id: string) => post<Envelope<Payment>>(`/payments/${id}/process/`),
  },
  notifications: {
    list: (params?: PageParams & { unread?: "true" | "false" }) =>
      get<Collection<Notification>>("/notifications/", params),
  },
};
