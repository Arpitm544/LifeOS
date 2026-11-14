import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { runInNewContext } from "node:vm";

function setup(fetcher: typeof fetch, extra: Record<string, unknown> = {}) {
  const slots: any[] = [], cleanups: (() => void)[] = [], errors: string[] = [], revoked: string[] = [];
  let index = 0, first = true, paused = 0;
  const useState = (initial: unknown) => { const i = index++; if (first) slots[i] = initial; return [slots[i], (value: unknown) => { slots[i] = value; }]; };
  const useRef = (initial: unknown) => { const i = index++; if (first) slots[i] = { current: initial }; return slots[i]; };
  const useEffect = (effect: () => (() => void)) => { if (first) cleanups.push(effect()); };
  const source = readFileSync(new URL("../src/hooks/use-voice-output.ts", import.meta.url), "utf8").replace(/import .* from "react";/, "").replace("export function useVoiceOutput", "function useVoiceOutput");
  const hook = runInNewContext(stripTypeScriptTypes(source) + "; useVoiceOutput;", {
    useState, useRef, useEffect, AbortController, AbortSignal, fetch: fetcher,
    URL: { createObjectURL: () => "blob:reply", revokeObjectURL: (url: string) => revoked.push(url) }, ...extra,
  });
  const render = () => { index = 0; const value = hook((message: string) => errors.push(message)); first = false; value.element.current = { pause: () => { paused++; } }; return value; };
  return { render, errors, revoked, paused: () => paused, cleanup: () => cleanups.forEach(fn => fn()) };
}

test("spoken audio exposes a playable URL and stop/unmount pause playback and revoke it", async () => {
  const env = setup(async () => new Response("mp3", { headers: { "Content-Type": "audio/mpeg" } }));
  await env.render().read("hello");
  assert.equal(env.render().url, "blob:reply");
  assert.equal(env.render().loading, false);
  env.render().setPlaying(true);
  env.render().stop();
  assert.equal(env.render().url, "");
  assert.deepEqual(env.revoked, ["blob:reply"]);
  await env.render().read("hello"); env.cleanup();
  assert.deepEqual(env.revoked, ["blob:reply", "blob:reply"]);
  assert.ok(env.paused() > 0);
});

test("canceling an in-flight speech request prevents late playback", async () => {
  let resolve!: (response: Response) => void;
  const env = setup(() => new Promise(done => { resolve = done; }));
  const pending = env.render().read("hello");
  assert.equal(env.render().loading, true);
  env.render().stop();
  resolve(new Response("mp3", { headers: { "Content-Type": "audio/mpeg" } })); await pending;
  assert.equal(env.render().url, "");
  assert.equal(env.render().loading, false);
  assert.deepEqual(env.errors, []);
});

test("speech provider errors leave no playable audio and clear loading", async () => {
  const env = setup(async () => Response.json({ error: "Add DEEPGRAM_API_KEY" }, { status: 503 }));
  await env.render().read("hello");
  assert.deepEqual(env.errors, ["Add DEEPGRAM_API_KEY"]);
  assert.equal(env.render().url, "");
  assert.equal(env.render().loading, false);
  env.cleanup();
});

test("non-JSON speech failures show the fallback instead of a parser error", async () => {
  const env = setup(async () => new Response("unavailable", { status: 502 }));
  await env.render().read("hello");
  assert.deepEqual(env.errors, ["Could not generate speech. Please retry."]);
  env.cleanup();
});

test("reading another reply replaces playback and cancels pending audio", async () => {
  let finish!: (response: Response) => void;
  let calls = 0;
  const env = setup(async () => ++calls === 1 ? new Promise<Response>(resolve => { finish = resolve; }) : new Response("second", { headers: { "Content-Type": "audio/mpeg" } }));
  const first = env.render().read("first");
  await env.render().read("second");
  finish(new Response("old", { headers: { "Content-Type": "audio/mpeg" } })); await first;
  assert.equal(env.render().url, "blob:reply");
  assert.equal(env.render().loading, false);
  assert.deepEqual(env.errors, []);
  env.cleanup();
});

function browserSpeech(voices: { lang: string }[]) {
  const spoken: { text: string; lang: string; onstart?: () => void; onend?: () => void }[] = [];
  let cancelled = 0;
  class Utterance { lang = ""; voice: unknown; text: string; onstart?: () => void; onend?: () => void; onerror?: () => void; constructor(text: string) { this.text = text; } }
  const speechSynthesis = { getVoices: () => voices, speak: (u: Utterance) => { spoken.push(u); }, cancel: () => { cancelled++; } };
  return { globals: { speechSynthesis, SpeechSynthesisUtterance: Utterance }, spoken, cancelled: () => cancelled };
}

test("a language with a server voice sends the language to /api/speak", async () => {
  let body: unknown;
  const env = setup(async (_url, init) => { body = JSON.parse(String(init?.body)); return new Response("mp3", { headers: { "Content-Type": "audio/mpeg" } }); });
  await env.render().read("Hola", "es-ES");
  assert.deepEqual(body, { text: "Hola", language: "es-ES" });
  await env.render().read("Hello", "en-US");
  assert.deepEqual(body, { text: "Hello" });
});

test("languages without a server voice are read by the device voice and stop cancels it", async () => {
  const speech = browserSpeech([{ lang: "en-US" }, { lang: "hi-IN" }]);
  const env = setup(async () => Response.json({ error: "No server voice", code: "unsupported_language" }, { status: 422 }), speech.globals);
  await env.render().read("नमस्ते", "hi-IN");
  assert.deepEqual(env.errors, []);
  assert.equal(speech.spoken.length, 1);
  assert.equal(speech.spoken[0].lang, "hi-IN");
  speech.spoken[0].onstart?.();
  assert.equal(env.render().playing, true);
  assert.equal(env.render().loading, false);
  env.render().stop();
  assert.equal(speech.cancelled(), 1);
  assert.equal(env.render().playing, false);
});

test("a missing device voice is explained instead of failing silently", async () => {
  const speech = browserSpeech([{ lang: "en-US" }]);
  const env = setup(async () => Response.json({ code: "unsupported_language" }, { status: 422 }), speech.globals);
  await env.render().read("नमस्ते", "hi-IN");
  assert.match(env.errors[0], /No voice for this language/);
  const none = setup(async () => Response.json({ code: "unsupported_language" }, { status: 422 }));
  await none.render().read("नमस्ते", "hi-IN");
  assert.match(none.errors[0], /not supported in this browser/);
});
