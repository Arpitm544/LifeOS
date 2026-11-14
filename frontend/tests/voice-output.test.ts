import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { runInNewContext } from "node:vm";

function setup(fetcher: typeof fetch) {
  const slots: any[] = [], cleanups: (() => void)[] = [], errors: string[] = [], revoked: string[] = [];
  let index = 0, first = true, paused = 0;
  const useState = (initial: unknown) => { const i = index++; if (first) slots[i] = initial; return [slots[i], (value: unknown) => { slots[i] = value; }]; };
  const useRef = (initial: unknown) => { const i = index++; if (first) slots[i] = { current: initial }; return slots[i]; };
  const useEffect = (effect: () => (() => void)) => { if (first) cleanups.push(effect()); };
  const source = readFileSync(new URL("../src/hooks/use-voice-output.ts", import.meta.url), "utf8").replace(/import .* from "react";/, "").replace("export function useVoiceOutput", "function useVoiceOutput");
  const hook = runInNewContext(stripTypeScriptTypes(source) + "; useVoiceOutput;", {
    useState, useRef, useEffect, AbortController, AbortSignal, fetch: fetcher,
    URL: { createObjectURL: () => "blob:reply", revokeObjectURL: (url: string) => revoked.push(url) },
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
  await env.render().read("hello");
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
