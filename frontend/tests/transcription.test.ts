import test from "node:test";
import assert from "node:assert/strict";
import { transcriptionResponse } from "../src/lib/transcription-service.ts";

const provider = (transcript: unknown) => Response.json({ results: { channels: [{ alternatives: [{ transcript }] }] } });

const request = (body: BodyInit = "audio", type = "audio/webm;codecs=opus") => new Request("http://localhost/api/transcribe", { method: "POST", headers: { "Content-Type": type }, body });

test("recorded audio becomes a trimmed transcript for review", async () => {
  const response = await transcriptionResponse(request(), "key", "nova-3", async (url, init) => {
    assert.equal(String(url), "https://api.deepgram.com/v1/listen?model=nova-3&language=multi&smart_format=true");
    assert.equal(new Headers(init?.headers).get("Authorization"), "Token key");
    assert.equal(new Headers(init?.headers).get("Content-Type"), "audio/webm");
    assert.equal(await (init?.body as Blob).text(), "audio");
    return provider(" Help me plan today. ");
  });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store");
  const { text } = await response.json();
  assert.equal(text, "Help me plan today.");
});

test("invalid and oversized audio never reaches the provider, even without content-length", async () => {
  const unused = async () => { throw new Error("provider must not run"); };
  assert.equal((await transcriptionResponse(request(), undefined, "model", unused)).status, 503);
  assert.equal((await transcriptionResponse(request("text", "text/plain"), "key", "model", unused)).status, 415);
  assert.equal((await transcriptionResponse(request(""), "key", "model", unused)).status, 400);
  assert.equal((await transcriptionResponse(request(new Uint8Array(4_000_001)), "key", "model", unused)).status, 413);
  const large = request(); large.headers.set("content-length", "4000001");
  assert.equal((await transcriptionResponse(large, "key", "model", unused)).status, 413);
});

test("silence, long transcripts and provider failures return safe actionable errors", async () => {
  for (const [fetcher, status] of [
    [async () => provider(" "), 422],
    [async () => provider("x".repeat(1001)), 422],
    [async () => Response.json({}), 502],
    [async () => new Response("secret", { status: 429 }), 429],
    [async () => new Response("secret", { status: 401 }), 502],
    [async () => { throw new Error("secret"); }, 502],
  ] as const) {
    const response = await transcriptionResponse(request(), "key", "model", fetcher);
    assert.equal(response.status, status);
    assert.doesNotMatch(await response.text(), /secret/);
  }
});

test("inherited format names are rejected before forwarding audio", async () => {
  for (const type of ["constructor", "__proto__", "toString"]) {
    let forwarded = false;
    const response = await transcriptionResponse(request("audio", type), "key", "model", async () => { forwarded = true; return provider("hello"); });
    assert.equal(response.status, 415);
    assert.equal(forwarded, false);
  }
});
