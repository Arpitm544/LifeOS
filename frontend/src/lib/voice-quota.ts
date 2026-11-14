import { API_URL } from "./api.ts";

// Reserve against the backend's shared PostgreSQL limiter before any paid provider call.
export async function voiceQuota(token: string | null, kind: "transcribe" | "speak", signal: AbortSignal, fetcher: typeof fetch = fetch) {
  const headers = { "Cache-Control": "no-store" };
  if (!token) return Response.json({ error: "Sign in to use voice." }, { status: 401, headers });
  try {
    const response = await fetcher(`${API_URL}/api/voice/${kind}/quota`, {
      method: "POST", headers: { Authorization: `Bearer ${token}` }, cache: "no-store",
      signal: AbortSignal.any([signal, AbortSignal.timeout(5_000)]),
    });
    await response.body?.cancel();
    if (response.status === 204) return null;
    return Response.json({ error: response.status === 429 ? "Voice limit reached. Please wait a minute before trying again." : "Voice is unavailable right now. Please type your message." }, {
      status: response.status === 429 ? 429 : 503,
      headers: { ...headers, ...(response.status === 429 ? { "Retry-After": response.headers.get("Retry-After") || "60" } : {}) },
    });
  } catch {
    return Response.json({ error: "Voice is unavailable right now. Please type your message." }, { status: 503, headers });
  }
}
