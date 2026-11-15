import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { runInNewContext } from "node:vm";

// Run the hook with browser/React fakes to check lifecycle without microphone hardware.
function setup(fetcher: typeof fetch, getMedia?: () => Promise<unknown>, extra: Record<string, unknown> = {}) {
  const slots: any[] = [], cleanups: (() => void)[] = [];
  let index = 0, first = true, stopped = 0, transcript = "", timeout: (() => void) | undefined;
  const useState = (initial: unknown) => { const i = index++; if (first) slots[i] = initial; return [slots[i], (value: unknown) => { slots[i] = value; }]; };
  const useRef = (initial: unknown) => { const i = index++; if (first) slots[i] = { current: initial }; return slots[i]; };
  const useEffect = (effect: () => unknown) => { if (first) { const cleanup = effect(); if (typeof cleanup === "function") cleanups.push(cleanup as () => void); } };
  const media = { getTracks: () => [{ stop: () => { stopped++; } }] };
  class Recorder {
    static isTypeSupported() { return true; }
    state = "inactive"; mimeType = "audio/webm;codecs=opus";
    ondataavailable?: (event: { data: Blob }) => void;
    onstop?: () => void;
    start() { this.state = "recording"; }
    stop() { this.state = "inactive"; this.ondataavailable?.({ data: new Blob(["audio"]) }); this.onstop?.(); }
  }
  const source = readFileSync(new URL("../src/hooks/use-voice-input.ts", import.meta.url), "utf8").replace(/import .* from "react";/, "").replace("export function useVoiceInput", "function useVoiceInput");
  const hook = runInNewContext(stripTypeScriptTypes(source) + "; useVoiceInput;", {
    useState, useRef, useEffect, MediaRecorder: Recorder, Blob, AbortController, AbortSignal, DOMException,
    navigator: { mediaDevices: { getUserMedia: getMedia || (async () => media) } },
    window: { isSecureContext: true, MediaRecorder: Recorder, speechSynthesis: { cancel() {} } },
    fetch: fetcher, setTimeout: (fn: () => void) => { timeout = fn; return 1; }, clearTimeout: () => { timeout = undefined; }, ...extra,
  });
  const render = () => { index = 0; const value = hook((text: string) => { transcript = text; }); first = false; return value; };
  return { render, cleanup: () => cleanups.forEach(fn => fn()), stopped: () => stopped, transcript: () => transcript, expire: () => timeout?.() };
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test("voice recording stops tracks, transcribes, preserves draft and supports retry", async () => {
  let calls = 0;
  const env = setup(async () => ++calls === 1 ? Response.json({ error: "Busy" }, { status: 429 }) : Response.json({ text: "plan today" }));
  await env.render().toggle("Please");
  assert.equal(env.render().listening, true);
  await env.render().toggle();
  await settle();
  assert.equal(env.stopped(), 1);
  assert.equal(env.render().canRetry, true);
  assert.equal(env.transcript(), "");
  env.render().retry(); await settle();
  assert.equal(env.transcript(), "Please plan today");
  assert.equal(env.render().processing, false);
  assert.equal(env.render().canRetry, false);
  env.cleanup();
});

test("automatic stop transcribes; leaving Chat stops capture without uploading", async () => {
  let uploads = 0;
  const env = setup(async () => { uploads++; return Response.json({ text: "hello" }); });
  await env.render().toggle(); env.expire(); await settle();
  assert.equal(env.transcript(), "hello");
  assert.equal(env.stopped(), 1);
  await env.render().toggle(); env.cleanup();
  assert.equal(env.stopped(), 2);
  assert.equal(uploads, 1);
});

test("microphone permission failures leave draft alone and reset busy state", async () => {
  const env = setup(async () => { throw new Error("must not upload"); }, async () => { throw new DOMException("denied", "NotAllowedError"); });
  await env.render().toggle("draft");
  assert.match(env.render().error, /denied/);
  assert.equal(env.render().processing, false);
  assert.equal(env.transcript(), "");
  env.cleanup();
});

test("canceling pending microphone permission releases late streams without recording", async () => {
  let resolve!: (value: unknown) => void, stopped = false;
  const env = setup(async () => { throw new Error("must not upload"); }, () => new Promise(done => { resolve = done; }));
  const start = env.render().toggle();
  env.render().cancel();
  resolve({ getTracks: () => [{ stop: () => { stopped = true; } }] });
  await start;
  assert.equal(stopped, true);
  assert.equal(env.render().listening, false);
  env.cleanup();
});

test("deterministic transcript failures discard audio and cannot retry", async () => {
  for (const [response, prefix] of [
    [Response.json({ error: "No audio" }, { status: 400 }), ""],
    [Response.json({ error: "No speech" }, { status: 422 }), ""],
    [Response.json({ text: "" }), ""],
    [Response.json({ text: "hello" }), "x".repeat(1000)],
  ] as const) {
    let uploads = 0;
    const env = setup(async () => { uploads++; return response; });
    await env.render().toggle(prefix); await env.render().toggle(); await settle();
    assert.equal(env.render().canRetry, false);
    assert.ok(env.render().error);
    env.render().retry(); await settle();
    assert.equal(uploads, 1);
    assert.equal(env.transcript(), "");
    env.cleanup();
  }
});

test("network and server failures retain audio for retry", async () => {
  for (const fetcher of [
    async () => { throw new TypeError("Network error"); },
    async () => { throw new DOMException("Timed out", "TimeoutError"); },
    async () => new Response("unavailable", { status: 502 }),
  ]) {
    const env = setup(fetcher);
    await env.render().toggle(); await env.render().toggle(); await settle();
    assert.equal(env.render().canRetry, true);
    env.cleanup();
  }
});

// A fake Web Audio meter: `speak(ms, level)` feeds that microphone level for `ms` of 100 ms ticks.
function fakeMeter() {
  let level = 0, now = 0, closed = 0, tick: (() => void) | undefined;
  class Context {
    createAnalyser() { return { fftSize: 0, getFloatTimeDomainData: (samples: Float32Array) => samples.fill(level) }; }
    createMediaStreamSource() { return { connect() {} }; }
    close() { closed++; return Promise.resolve(); }
  }
  return {
    globals: { AudioContext: Context, performance: { now: () => now }, setInterval: (fn: () => void) => { tick = fn; return 2; }, clearInterval: () => { tick = undefined; } },
    speak(ms: number, value: number) { level = value; for (let t = 0; t < ms; t += 100) { now += 100; tick?.(); } },
    closed: () => closed,
  };
}

test("recording stops by itself after the speaker goes quiet, then transcribes", async () => {
  let uploads = 0;
  const meter = fakeMeter();
  const env = setup(async () => { uploads++; return Response.json({ text: "essay due friday" }); }, undefined, meter.globals);
  await env.render().toggle();
  meter.speak(500, 0.005); // room noise while the meter calibrates
  meter.speak(1500, 0.2); // talking
  meter.speak(800, 0.005); // a short pause is not the end
  assert.equal(env.render().listening, true);
  meter.speak(600, 0.005); // 1.4 s of quiet in total: done
  await settle();
  assert.equal(env.render().listening, false);
  assert.equal(uploads, 1);
  assert.equal(env.transcript(), "essay due friday");
  assert.equal(meter.closed(), 1);
  env.cleanup();
});

test("if nobody speaks, recording is cancelled without uploading silence", async () => {
  let uploads = 0;
  const meter = fakeMeter();
  const env = setup(async () => { uploads++; return Response.json({ text: "" }); }, undefined, meter.globals);
  await env.render().toggle();
  meter.speak(8500, 0.004);
  await settle();
  assert.equal(uploads, 0);
  assert.equal(env.render().listening, false);
  assert.equal(env.stopped(), 1);
  assert.match(env.render().error, /catch anything/);
  env.cleanup();
});
