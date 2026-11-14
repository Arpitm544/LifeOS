import assert from "node:assert/strict";
import test from "node:test";
import { ApiError, createApi, errorMessage, undoPath } from "../src/lib/api.ts";

test("FastAPI error bodies become readable sentences", () => {
  assert.equal(errorMessage(404, { detail: "Task not found" }), "Task not found");
  assert.equal(errorMessage(429, { code: "rate_limited", message: "Too many requests" }), "Too many requests");
  assert.equal(errorMessage(422, { detail: [{ loc: ["body", "effort_est_min"], msg: "Input should be less than or equal to 600" }] }), "effort est min: Input should be less than or equal to 600");
  assert.equal(errorMessage(422, { detail: [{ loc: ["body"], msg: "Value error, Invalid preference value: 'start'" }] }), "Invalid preference value: 'start'");
  assert.equal(errorMessage(409, { detail: { confirmation_required: true, count: 5 } }), "This changes 5 items and needs confirmation.");
  assert.equal(errorMessage(500, "<html>"), "<html>");
  assert.equal(errorMessage(500, undefined), "The server returned an error (500).");
  assert.equal(errorMessage(401, {}), "Your session has expired. Sign in again.");
});

test("requests send the Clerk token, JSON body and extra headers", async () => {
  const calls: { url: string; init: RequestInit }[] = [];
  const fakeFetch = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as unknown as typeof fetch;
  const api = createApi(async () => "token-123", "http://api.test", fakeFetch);
  assert.deepEqual(await api("/api/chat", { method: "POST", body: { text: "hi" }, headers: { "Idempotency-Key": "k1" } }), { ok: true });
  const headers = calls[0].init.headers as Record<string, string>;
  assert.equal(calls[0].url, "http://api.test/api/chat");
  assert.equal(headers.Authorization, "Bearer token-123");
  assert.equal(headers["Content-Type"], "application/json");
  assert.equal(headers["Idempotency-Key"], "k1");
  assert.equal(calls[0].init.body, JSON.stringify({ text: "hi" }));
});

test("errors carry status and code; 204 returns nothing; no token fails before fetching", async () => {
  let fetched = 0;
  const respond = (status: number, body?: unknown) => (async () => { fetched += 1; return new Response(body === undefined ? null : JSON.stringify(body), { status }); }) as unknown as typeof fetch;
  await assert.rejects(createApi(async () => "t", "http://x", respond(429, { code: "rate_limited", message: "Too many requests" }))("/a"),
    (error: unknown) => error instanceof ApiError && error.status === 429 && error.code === "rate_limited" && error.message === "Too many requests");
  assert.equal(await createApi(async () => "t", "http://x", respond(204))("/a", { method: "DELETE" }), undefined);
  fetched = 0;
  await assert.rejects(createApi(async () => null, "http://x", respond(200, {}))("/a"), (error: unknown) => error instanceof ApiError && error.status === 401);
  assert.equal(fetched, 0);
  const offline = (async () => { throw new TypeError("Failed to fetch"); }) as unknown as typeof fetch;
  await assert.rejects(createApi(async () => "t", "http://x", offline)("/a"), (error: unknown) => error instanceof ApiError && error.code === "network");
});

test("deleted tasks undo as a batch; other actions by id", () => {
  assert.equal(undoPath({ action_id: "a1", batch_id: "b1" }), "/api/actions/batches/b1/undo");
  assert.equal(undoPath({ action_id: "a1" }), "/api/actions/a1/undo");
  assert.equal(undoPath({ action_id: null }), null);
});
