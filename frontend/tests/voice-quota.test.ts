import test from "node:test";
import assert from "node:assert/strict";
import { voiceQuota } from "../src/lib/voice-quota.ts";
import { API_URL } from "../src/lib/api.ts";

const signal = new AbortController().signal;

test("both voice routes reserve quota using the authenticated backend token", async () => {
  for (const kind of ["speak", "transcribe"] as const) {
    let url: unknown, options: RequestInit | undefined;
    const result = await voiceQuota("session-token", kind, signal, async (input, init) => {
      url = input; options = init;
      return new Response(null, { status: 204 });
    });
    assert.equal(result, null);
    assert.equal(url, `${API_URL}/api/voice/${kind}/quota`);
    assert.equal(options?.method, "POST");
    assert.equal(new Headers(options?.headers).get("Authorization"), "Bearer session-token");
  }
});

test("quota rejection and unavailable backend fail closed", async () => {
  for (const [fetcher, status] of [
    [async () => new Response(null, { status: 429, headers: { "Retry-After": "17" } }), 429],
    [async () => new Response(null, { status: 500 }), 503],
    [async () => new Response("unexpected success", { status: 200 }), 503],
    [async () => { throw new Error("offline"); }, 503],
  ] as const) {
    const response = await voiceQuota("token", "transcribe", signal, fetcher);
    assert.equal(response?.status, status);
    if (status === 429) assert.equal(response?.headers.get("Retry-After"), "17");
  }
  const response = await voiceQuota(null, "speak", signal, async () => { throw new Error("must not run"); });
  assert.equal(response?.status, 401);
});
