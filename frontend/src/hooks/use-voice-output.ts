"use client";

import { useEffect, useRef, useState } from "react";

// Recently spoken replies, so pressing "Read" again plays at once without another provider call.
const recent = new Map<string, Blob>();
function remember(key: string, audio: Blob) {
  recent.delete(key); recent.set(key, audio);
  while (recent.size > 6) recent.delete(recent.keys().next().value as string);
}

// Streaming playback starts on the first audio chunk (~1 s) instead of after the whole MP3 (~6 s for a brief).
function canStream() {
  const Source = (globalThis as { MediaSource?: typeof MediaSource }).MediaSource;
  return typeof Source === "function" && typeof Source.isTypeSupported === "function" && Source.isTypeSupported("audio/mpeg");
}

/** `onFinished` runs when a reply plays to its end (not when it is stopped), so a conversation can take its next turn. */
export function useVoiceOutput(onError: (message: string) => void, onFinished?: () => void) {
  const finished = useRef(onFinished);
  useEffect(() => { finished.current = onFinished; });
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const element = useRef<HTMLAudioElement>(null);
  const pending = useRef<AbortController | null>(null);
  const objectUrl = useRef("");
  const spoken = useRef<SpeechSynthesisUtterance | null>(null);

  // Languages without a server voice use the device's own voices (Web Speech API).
  async function speakInBrowser(text: string, locale: string, signal?: AbortSignal) {
    const synth = globalThis.speechSynthesis, Utterance = globalThis.SpeechSynthesisUtterance;
    if (!synth || !Utterance) throw new Error("Spoken replies in this language are not supported in this browser.");
    // Chrome fills the voice list asynchronously: the first call usually returns none.
    if (!synth.getVoices().length && typeof synth.addEventListener === "function") {
      await new Promise<void>(resolve => {
        const timer = setTimeout(resolve, 1500);
        synth.addEventListener("voiceschanged", () => { clearTimeout(timer); resolve(); }, { once: true });
      });
    }
    if (signal?.aborted) return;
    const prefix = locale.split("-")[0].toLowerCase();
    const voice = synth.getVoices().find(v => v.lang.toLowerCase() === locale.toLowerCase()) ?? synth.getVoices().find(v => v.lang.toLowerCase().startsWith(prefix));
    if (!voice) throw new Error("No voice for this language is installed on this device. Add one in your system settings.");
    const utterance = new Utterance(text);
    utterance.lang = voice.lang; utterance.voice = voice;
    utterance.onstart = () => { if (spoken.current === utterance) setPlaying(true); };
    utterance.onend = utterance.onerror = () => { if (spoken.current === utterance) { spoken.current = null; setPlaying(false); finished.current?.(); } };
    spoken.current = utterance;
    synth.speak(utterance);
  }

  function release() {
    pending.current?.abort(); pending.current = null;
    if (spoken.current) { spoken.current = null; globalThis.speechSynthesis?.cancel(); }
    element.current?.pause();
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = "";
  }
  function stop() {
    release(); setUrl(""); setLoading(false); setPlaying(false);
  }
  /** For the audio element's `onEnded`: clean up, then tell the caller the reply finished. */
  function finish() {
    stop(); finished.current?.();
  }
  useEffect(() => () => release(), []);

  function play(audio: Blob) {
    objectUrl.current = URL.createObjectURL(audio); setUrl(objectUrl.current);
  }

  /** Feeds the MP3 stream into a MediaSource so the audio element plays while the rest downloads. */
  async function stream(body: ReadableStream<Uint8Array>, controller: AbortController, key: string) {
    const source = new MediaSource();
    objectUrl.current = URL.createObjectURL(source); setUrl(objectUrl.current);
    await new Promise<void>((resolve, reject) => {
      source.addEventListener("sourceopen", () => resolve(), { once: true });
      controller.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
    });
    const buffer = source.addSourceBuffer("audio/mpeg");
    const append = (chunk: Uint8Array) => new Promise<void>((resolve, reject) => {
      buffer.addEventListener("updateend", () => resolve(), { once: true });
      buffer.addEventListener("error", () => reject(new Error("Could not play the spoken reply. Please retry.")), { once: true });
      buffer.appendBuffer(chunk as Uint8Array<ArrayBuffer>);
    });
    const reader = body.getReader();
    const parts: Uint8Array[] = [];
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (controller.signal.aborted) return;
        parts.push(value);
        await append(value);
        // The first chunk is enough for the element to start; the button can show "Stop" now.
        if (parts.length === 1 && pending.current === controller) setLoading(false);
      }
    } finally { reader.releaseLock(); }
    if (controller.signal.aborted) return;
    if (!parts.length) throw new Error("The spoken reply was empty. Please retry.");
    if (source.readyState === "open") source.endOfStream();
    remember(key, new Blob(parts as BlobPart[], { type: "audio/mpeg" }));
  }

  /** `locale` is a BCP 47 tag such as "hi-IN"; omit it for English. */
  async function read(text: string, locale?: string) {
    stop();
    const language = locale && !locale.toLowerCase().startsWith("en") ? locale : undefined;
    const key = `${language ?? "en"}\u0000${text}`;
    const cached = recent.get(key);
    if (cached) { remember(key, cached); play(cached); return; }
    const controller = new AbortController(); pending.current = controller;
    setLoading(true);
    try {
      const response = await fetch("/api/speak", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(language ? { text, language } : { text }),
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30_000)]),
      });
      if (!response.ok) {
        const result = await response.json().catch(() => null);
        if (language && result?.code === "unsupported_language") {
          if (controller.signal.aborted) return;
          await speakInBrowser(text, language, controller.signal);
          return;
        }
        // Over the per-minute voice limit: keep talking with the device's voice rather than going silent.
        if (response.status === 429 && globalThis.speechSynthesis) {
          if (controller.signal.aborted) return;
          try { await speakInBrowser(text, language ?? "en-US", controller.signal); return; } catch { /* no device voice: report the limit below */ }
        }
        throw new Error(typeof result?.error === "string" ? result.error : "Could not generate speech. Please retry.");
      }
      if (!response.headers.get("content-type")?.startsWith("audio/")) throw new Error("Could not load spoken reply. Please retry.");
      if (controller.signal.aborted) return;
      if (response.body && canStream()) { await stream(response.body, controller, key); return; }
      const audio = await response.blob();
      if (controller.signal.aborted) return;
      if (!audio.size) throw new Error("The spoken reply was empty. Please retry.");
      remember(key, audio);
      play(audio);
    } catch (e) {
      if (!controller.signal.aborted) {
        // A stream that fails midway leaves partial audio attached; clear it so the button resets.
        if (objectUrl.current) { element.current?.pause(); URL.revokeObjectURL(objectUrl.current); objectUrl.current = ""; setUrl(""); setPlaying(false); }
        onError(e instanceof Error ? e.message : "Could not load spoken reply. Please retry.");
      }
    } finally {
      if (pending.current === controller) { pending.current = null; setLoading(false); }
    }
  }
  return { url, loading, playing, element, read, stop, finish, setPlaying };
}
