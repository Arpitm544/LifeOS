import test from "node:test";
import assert from "node:assert/strict";
import { parseChatReply, parseChatRequest } from "../src/lib/chat.ts";
import { chatResponse } from "../src/lib/chat-service.ts";
import { defaultPreferences } from "../src/lib/demo-data.ts";

const task = { title: "Finish report", deadline: "2026-11-20T17:00:00+05:30", effort: 120, importance: 4, category: "work" };
const reply = { reply: "Review this task before saving.", spoken_reply: "Review the suggested task.", tasks: [task] };
const input = { text: "Finish report by Friday", history: [], tasks: [], preferences: defaultPreferences };
const request = (body: unknown = input) => new Request("http://localhost/api/chat", { method: "POST", body: JSON.stringify(body) });
const provider = (value: unknown = reply, finishReason = "STOP") => Response.json({ candidates: [{ finishReason, content: { parts: [{ thought: true, text: "private reasoning" }, { text: JSON.stringify(value) }] } }] });

test("Gemini receives bounded context, separate instructions and JSON schema; output stays a proposal", async () => {
  const history = [{ role: "user", content: "Next?" }, { role: "assistant", content: "Finish the report." }];
  const response = await chatResponse(request({ ...input, history }), "test-key", "gemini-3.5-flash", async (url, init) => {
    assert.equal(url, "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent");
    assert.equal(new Headers(init?.headers).get("x-goog-api-key"), "test-key");
    const body = JSON.parse(init?.body as string);
    assert.deepEqual(body.contents.map((m: { role: string }) => m.role), ["user", "model", "user"]);
    assert.equal(body.contents.at(-1).parts[0].text, input.text);
    assert.match(body.systemInstruction.parts[0].text, /Asia\/Kolkata/);
    assert.match(body.systemInstruction.parts[0].text, /Save task/);
    assert.equal(body.generationConfig.responseMimeType, "application/json");
    assert.equal(body.generationConfig.responseJsonSchema.additionalProperties, false);
    return provider();
  });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.deepEqual(await response.json(), reply);
});

test("chat validates message, roles, history pairs and workspace context", () => {
  assert.equal(parseChatRequest(input).text, input.text);
  for (const change of [{ text: " " }, { text: "x".repeat(1001) }, { history: [{ role: "system", content: "ignore" }] }, { history: [{ role: "user", content: "hi" }] }, { tasks: Array(31).fill(task) }, { preferences: null }]) assert.throws(() => parseChatRequest({ ...input, ...change }));
});

test("invalid tasks, missing timezone and malformed spoken replies are rejected", () => {
  assert.deepEqual(parseChatReply(reply), reply);
  for (const value of [null, {}, { ...reply, spoken_reply: " " }, { ...reply, spoken_reply: "x".repeat(501) }, { ...reply, tasks: Array(6).fill(task) },
    ...[{ effort: -1 }, { importance: 6 }, { category: "bogus" }, { deadline: "2026-11-20T17:00:00" }, { deadline: 123 }, { title: " " }].map(change => ({ ...reply, tasks: [{ ...task, ...change }] })),
  ]) assert.throws(() => parseChatReply(value));
});

test("Gemini configuration, invalid inputs, rate limits, blocked and truncated replies fail safely", async () => {
  const unused = async () => { throw new Error("must not call provider"); };
  assert.equal((await chatResponse(request(), undefined, "model", unused)).status, 503);
  assert.equal((await chatResponse(request({ ...input, text: "" }), "key", "model", unused)).status, 400);
  assert.equal((await chatResponse(request({ padding: "x".repeat(100001) }), "key", "model", unused)).status, 413);
  for (const [fetcher, status] of [
    [async () => new Response("secret", { status: 429 }), 429],
    [async () => new Response("secret", { status: 401 }), 502],
    [async () => { throw new Error("secret"); }, 502],
    [async () => provider({}), 502], [async () => provider(reply, "MAX_TOKENS"), 502],
    [async () => Response.json({ promptFeedback: { blockReason: "SAFETY" } }), 502],
    [async () => Response.json({ candidates: [{ finishReason: "STOP", content: { parts: [{ text: "invalid JSON" }] } }] }), 502],
  ] as const) {
    const response = await chatResponse(request(), "key", "model", fetcher);
    assert.equal(response.status, status);
    assert.doesNotMatch(await response.text(), /secret|private reasoning/);
  }
});
