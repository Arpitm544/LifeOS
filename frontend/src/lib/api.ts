// Thin client for the LifeOS FastAPI backend. Token acquisition stays with the caller
// (Clerk `useAuth().getToken()` in src/hooks/use-api.ts) so this module has no React or Clerk imports.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

const statusText: Record<number, string> = {
  400: "The request was not accepted.",
  401: "Your session has expired. Sign in again.",
  403: "You do not have access to that.",
  404: "That item no longer exists.",
  409: "That change conflicts with the current state. Refresh and try again.",
  422: "Some details are not valid.",
  429: "Too many requests. Wait a moment and try again.",
  503: "That service is not available on this server.",
};

type ValidationIssue = { loc?: (string | number)[]; msg?: string };

function describeIssue(issue: ValidationIssue) {
  const field = (issue.loc ?? []).filter(part => part !== "body" && part !== "query" && part !== "path").join(".");
  const message = (issue.msg ?? "is not valid").replace(/^Value error, /, "");
  return field ? `${field.replace(/_/g, " ")}: ${message}` : message;
}

/** Turn a FastAPI error body (`{detail}` or `{code, message}`) into one readable sentence. */
export function errorMessage(status: number, body: unknown): string {
  if (body && typeof body === "object") {
    const data = body as Record<string, unknown>;
    if (typeof data.message === "string" && data.message) return data.message;
    const detail = data.detail;
    if (typeof detail === "string" && detail) return detail;
    if (Array.isArray(detail) && detail.length) return detail.slice(0, 3).map(item => describeIssue(item as ValidationIssue)).join("; ");
    if (detail && typeof detail === "object") {
      const nested = detail as Record<string, unknown>;
      if (typeof nested.message === "string") return nested.message;
      if (nested.confirmation_required) return `This changes ${nested.count ?? "several"} items and needs confirmation.`;
    }
  }
  if (typeof body === "string" && body.trim() && body.length < 200) return body.trim();
  return statusText[status] ?? `The server returned an error (${status}).`;
}

export type GetToken = () => Promise<string | null>;
export type RequestOptions = { method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE"; body?: unknown; headers?: Record<string, string>; signal?: AbortSignal };

export function createApi(getToken: GetToken, baseUrl = API_URL, fetcher: typeof fetch = (...args) => fetch(...args)) {
  return async function request<T = unknown>(path: string, options: RequestOptions = {}): Promise<T> {
    const token = await getToken();
    if (!token) throw new ApiError("You are signed out. Sign in again to continue.", 401);
    const headers: Record<string, string> = { Accept: "application/json", Authorization: `Bearer ${token}`, ...options.headers };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    let response: Response;
    try {
      response = await fetcher(`${baseUrl}${path}`, { method: options.method ?? "GET", headers, signal: options.signal,
        body: options.body === undefined ? undefined : JSON.stringify(options.body) });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new ApiError(`Could not reach the LifeOS API at ${baseUrl}. Check that it is running.`, 0, "network");
    }
    if (response.status === 204) return undefined as T;
    const text = await response.text();
    let data: unknown = text;
    try { data = text ? JSON.parse(text) : undefined; } catch { /* keep the raw text */ }
    if (!response.ok) {
      const code = data && typeof data === "object" && typeof (data as { code?: unknown }).code === "string" ? (data as { code: string }).code : undefined;
      throw new ApiError(errorMessage(response.status, data), response.status, code);
    }
    return data as T;
  };
}

export type Api = ReturnType<typeof createApi>;

export function readableError(error: unknown, fallback = "Something went wrong. Please try again.") {
  return error instanceof Error && error.message ? error.message : fallback;
}

/** Which endpoint undoes a chat action card: deletes come back as a batch. */
export function undoPath(action: { action_id: string | null; batch_id?: string }) {
  if (action.batch_id) return `/api/actions/batches/${encodeURIComponent(action.batch_id)}/undo`;
  if (action.action_id) return `/api/actions/${encodeURIComponent(action.action_id)}/undo`;
  return null;
}
