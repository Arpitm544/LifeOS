import test from "node:test";
import assert from "node:assert/strict";
import { parseVoices, speechResponse } from "../src/lib/speech-service.ts";

const request = (value: unknown = { text: "Hello" }) => new Request("http://localhost/api/speak", { method: "POST", body: JSON.stringify(value) });

test("Deepgram Aura returns MP3 speech", async () => {
  let sentUrl: unknown, sentInit: RequestInit | undefined;
  const speech = await speechResponse(request({ text: "What is your priority?" }), "dg-key", "aura-2-thalia-en", async (url, init) => {
    sentUrl = url; sentInit = init;
    return new Response("mp3-audio", { headers: { "Content-Type": "audio/mpeg" } });
  });
  assert.equal(String(sentUrl), "https://api.deepgram.com/v1/speak?model=aura-2-thalia-en&encoding=mp3");
  assert.equal(new Headers(sentInit?.headers).get("Authorization"), "Token dg-key");
  assert.deepEqual(JSON.parse(sentInit?.body as string), { text: "What is your priority?" });
  assert.equal(speech.status, 200);
  assert.equal(speech.headers.get("content-type"), "audio/mpeg");
  assert.equal(speech.headers.get("cache-control"), "no-store");
  assert.equal(await speech.text(), "mp3-audio");
});

test("speech rejects invalid inputs, missing keys and provider failures without exposing details", async () => {
  const unused = async () => { throw new Error("must not run"); };
  for (const value of [null, {}, { text: " " }, { text: "x".repeat(501) }]) assert.equal((await speechResponse(request(value), "key", "model", unused)).status, 400);
  assert.equal((await speechResponse(request(), undefined, "model", unused)).status, 503);
  assert.equal((await speechResponse(request({ text: "x".repeat(4001) }), "key", "model", unused)).status, 413);
  for (const [fetcher, status] of [
    [async () => new Response("secret", { status: 429 }), 429],
    [async () => new Response("secret", { status: 401 }), 502],
    [async () => Response.json({ secret: "secret" }), 502],
    [async () => { throw new Error("secret"); }, 502],
  ] as const) {
    const response = await speechResponse(request(), "key", "model", fetcher);
    assert.equal(response.status, status); assert.doesNotMatch(await response.text(), /secret/);
  }
});

test("speech cancels rejected provider bodies", async () => {
  for (const status of [200, 401, 429]) {
    let canceled = false;
    const response = await speechResponse(request(), "key", "model", async () => new Response(new ReadableStream({ cancel() { canceled = true; } }), { status, headers: { "Content-Type": "text/plain" } }));
    assert.equal(response.status, status === 429 ? 429 : 502);
    assert.equal(canceled, true);
  }
});

test("other languages use their configured voice, or ask the browser to speak", async () => {
  let sentUrl = "";
  const fetcher = async (url: string | URL | Request) => { sentUrl = String(url); return new Response("mp3", { headers: { "Content-Type": "audio/mpeg" } }); };
  const voices = "es:aura-2-celeste-es, bad entry, fr:aura-2-agathe-fr";
  assert.equal((await speechResponse(request({ text: "Hola", language: "es-ES" }), "key", "aura-2-thalia-en", fetcher, voices)).status, 200);
  assert.equal(sentUrl, "https://api.deepgram.com/v1/speak?model=aura-2-celeste-es&encoding=mp3");
  assert.equal((await speechResponse(request({ text: "Hi", language: "en-GB" }), "key", "aura-2-thalia-en", fetcher, voices)).status, 200);
  assert.match(sentUrl, /model=aura-2-thalia-en/);
  const hindi = await speechResponse(request({ text: "नमस्ते", language: "hi-IN" }), "key", "aura-2-thalia-en", fetcher, voices);
  assert.equal(hindi.status, 422);
  assert.equal((await hindi.json()).code, "unsupported_language");
  assert.equal((await speechResponse(request({ text: "x", language: "hi; drop" }), "key", "m", fetcher)).status, 400);
});

test("voice config parsing ignores malformed entries", () => {
  assert.deepEqual({ ...parseVoices("es:aura-2-celeste-es,:x,fr:,de:bad voice,toString:y") }, { es: "aura-2-celeste-es" });
  assert.deepEqual({ ...parseVoices(undefined) }, {});
});
