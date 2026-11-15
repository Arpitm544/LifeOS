import { request, type APIRequestContext } from "@playwright/test";

export const API_URL = (process.env.E2E_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
export const USER = process.env.E2E_DEMO_USER_ID || `user_e2e_${Date.now()}`;

/** API client authenticated with the development-only demo header (never accepted in production). */
export async function api(): Promise<APIRequestContext> {
  return request.newContext({ baseURL: API_URL, extraHTTPHeaders: { "X-Demo-User-Id": USER, "Content-Type": "application/json" } });
}

export const inHours = (hours: number) => new Date(Date.now() + hours * 3_600_000).toISOString();
