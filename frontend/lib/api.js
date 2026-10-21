// Thin client for the CTC API gateway (docs/api/API_CONTRACT.md).
//
// Every success response is {data, message[, pagination]} and every error is
// {error, code, details}. `request` returns the full success envelope and
// throws an ApiError carrying the error envelope, so pages can do:
//
//   const { data, pagination } = await api.projects.list({ query: "react" });
//
// Tokens live in localStorage; an expired access token is refreshed once
// (refresh tokens rotate on every use) before the request is retried.

const BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api"
).replace(/\/$/, "");

const TOKEN_KEY = "ctc.tokens";

export class ApiError extends Error {
  constructor(status, body) {
    super(body?.error || `Request failed with HTTP ${status}`);
    this.status = status;
    this.code = body?.code || "REQUEST_ERROR";
    this.details = body?.details || {};
  }
}

export function getTokens() {
  if (typeof window === "undefined") return null;
  try {
    return JSON.parse(window.localStorage.getItem(TOKEN_KEY));
  } catch {
    return null;
  }
}

export function setTokens(tokens) {
  if (typeof window === "undefined") return;
  if (tokens) window.localStorage.setItem(TOKEN_KEY, JSON.stringify(tokens));
  else window.localStorage.removeItem(TOKEN_KEY);
}

function withQuery(path, params) {
  if (!params) return path;
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")
  ).toString();
  return query ? `${path}?${query}` : path;
}

async function send(method, path, body, accessToken) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    // Non-JSON bodies are reported through ApiError below.
  }
  return { response, payload };
}

async function refreshTokens() {
  const tokens = getTokens();
  if (!tokens?.refresh_token) return null;

  const { response, payload } = await send("POST", "/auth/refresh/", {
    refresh_token: tokens.refresh_token,
  });
  if (!response.ok) {
    setTokens(null);
    return null;
  }
  const next = { ...tokens, ...payload.data };
  setTokens(next);
  return next;
}

export async function request(method, path, { body, params, auth = true } = {}) {
  const url = withQuery(path, params);
  let tokens = auth ? getTokens() : null;
  let { response, payload } = await send(method, url, body, tokens?.access_token);

  if (response.status === 401 && auth && tokens?.refresh_token) {
    tokens = await refreshTokens();
    if (tokens) {
      ({ response, payload } = await send(method, url, body, tokens.access_token));
    }
  }

  if (!response.ok) throw new ApiError(response.status, payload);
  return payload;
}

export const api = {
  auth: {
    register: (body) => request("POST", "/auth/register/", { body, auth: false }),
    async login(email, password) {
      const result = await request("POST", "/auth/login/", {
        body: { email, password },
        auth: false,
      });
      setTokens(result.data);
      return result;
    },
    async logout() {
      const tokens = getTokens();
      setTokens(null);
      if (tokens?.refresh_token) {
        await request("POST", "/auth/logout/", {
          body: { refresh_token: tokens.refresh_token },
          auth: false,
        }).catch(() => {});
      }
    },
    me: () => request("GET", "/auth/me/"),
  },
  users: {
    get: (userId) => request("GET", `/users/${userId}/`),
    update: (userId, body) => request("PATCH", `/users/${userId}/`, { body }),
    profile: (userId) => request("GET", `/users/${userId}/profile/`),
    updateProfile: (userId, body) => request("PATCH", `/users/${userId}/profile/`, { body }),
    deactivate: (userId) => request("POST", `/users/${userId}/deactivate/`),
  },
  projects: {
    // params: query, skill, category, max_budget, page, page_size
    list: (params) => request("GET", "/projects/", { params }),
    create: (body) => request("POST", "/projects/", { body }),
    get: (id) => request("GET", `/projects/${id}/`),
    update: (id, body) => request("PATCH", `/projects/${id}/`, { body }),
    remove: (id) => request("DELETE", `/projects/${id}/`),
    publish: (id) => request("POST", `/projects/${id}/publish/`),
    close: (id) => request("POST", `/projects/${id}/close/`),
    status: (id) => request("GET", `/projects/${id}/status/`),
  },
  applications: {
    // params: project_id (required for clients), student_id, status, page, page_size
    list: (params) => request("GET", "/applications/", { params }),
    apply: (projectId, proposal, resumeUrl) =>
      request("POST", "/applications/", {
        body: { project_id: projectId, proposal, ...(resumeUrl ? { resume_url: resumeUrl } : {}) },
      }),
    get: (id) => request("GET", `/applications/${id}/`),
    update: (id, body) => request("PATCH", `/applications/${id}/`, { body }),
    shortlist: (id) => request("POST", `/applications/${id}/shortlist/`),
    select: (id) => request("POST", `/applications/${id}/select/`),
    reject: (id) => request("POST", `/applications/${id}/reject/`),
    withdraw: (id) => request("POST", `/applications/${id}/withdraw/`),
  },
  assignments: {
    // params: project_id, status, page, page_size
    list: (params) => request("GET", "/assignments/", { params }),
    get: (id) => request("GET", `/assignments/${id}/`),
  },
  work: {
    // params: assignment_id (required for clients), status, page, page_size
    list: (params) => request("GET", "/work/", { params }),
    create: (body) => request("POST", "/work/", { body }),
    get: (id) => request("GET", `/work/${id}/`),
    update: (id, body) => request("PATCH", `/work/${id}/`, { body }),
    submit: (id) => request("POST", `/work/${id}/submit/`, { body: {} }),
    requestRevision: (id, feedback) =>
      request("POST", `/work/${id}/reject/`, { body: { feedback } }),
    approve: (id) => request("POST", `/work/${id}/approve/`, { body: {} }),
  },
  reviews: {
    list: (params) => request("GET", "/reviews/", { params }),
    create: (body) => request("POST", "/reviews/", { body }),
    get: (id) => request("GET", `/reviews/${id}/`),
  },
  payments: {
    // params: assignment_id, status, page, page_size
    list: (params) => request("GET", "/payments/", { params }),
    history: (params) => request("GET", "/payments/history/", { params }),
    create: (assignmentId, payeeId, idempotencyKey) =>
      request("POST", "/payments/", {
        body: { assignment_id: assignmentId, payee_id: payeeId, idempotency_key: idempotencyKey },
      }),
    get: (id) => request("GET", `/payments/${id}/`),
    process: (id) => request("POST", `/payments/${id}/process/`, { body: {} }),
    release: (id) => request("POST", `/payments/${id}/release/`, { body: {} }),
  },
  notifications: {
    // params: unread ("true" | "false"), page, page_size
    list: (params) => request("GET", "/notifications/", { params }),
  },
};

export default api;
