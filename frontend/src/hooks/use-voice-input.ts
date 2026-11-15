"use client";

import { useEffect, useRef, useState } from "react";

const silenceAfterSpeechMs = 1200; // stop this long after the last word
const nothingHeardMs = 8000; // give up if nobody speaks at all

/**
 * Watches microphone level so recording ends when the speaker does, instead of waiting for a tap or the 30 s cap.
 * The threshold adapts to the room: it is set from the noise floor in the first half second.
 * Returns a cleanup function; without Web Audio it does nothing and the stop button still works.
 */
function watchForSilence(media: MediaStream, onDone: (heardSpeech: boolean) => void) {
  const Context = (globalThis as { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext }).AudioContext
    ?? (globalThis as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (typeof Context !== "function") return () => {};
  const context = new Context();
  const analyser = context.createAnalyser();
  analyser.fftSize = 1024;
  context.createMediaStreamSource(media).connect(analyser);
  const samples = new Float32Array(analyser.fftSize);
  const started = performance.now();
  let floor = 0, floorReadings = 0, heard = false, quietSince = 0, finished = false;
  const interval = setInterval(() => {
    analyser.getFloatTimeDomainData(samples);
    let sum = 0;
    for (const s of samples) sum += s * s;
    const level = Math.sqrt(sum / samples.length);
    const now = performance.now();
    if (now - started < 500) { floor = (floor * floorReadings + level) / ++floorReadings; return; }
    const threshold = Math.max(0.015, floor * 2.5);
    if (level > threshold) { heard = true; quietSince = 0; return; }
    if (heard) {
      quietSince ||= now;
      if (now - quietSince >= silenceAfterSpeechMs && !finished) { finished = true; onDone(true); }
    } else if (now - started >= nothingHeardMs && !finished) { finished = true; onDone(false); }
  }, 100);
  return () => { clearInterval(interval); void context.close().catch(() => undefined); };
}

/** `language` returns a language the user pinned (e.g. "es"), sent as a hint so Deepgram doesn't have to guess. */
export function useVoiceInput(onTranscript: (text: string, language: string | null) => void, options: { language?: () => string | null } = {}) {
  const pinned = useRef(options.language);
  useEffect(() => { pinned.current = options.language; });
  const [supported, setSupported] = useState<boolean | null>(null);
  const [listening, setListening] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState("");
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const operation = useRef<AbortController | null>(null);
  const callback = useRef(onTranscript);
  const recording = useRef<{ audio: Blob; prefix: string } | null>(null);
  const [canRetry, setCanRetry] = useState(false);
  const stopWatching = useRef<(() => void) | null>(null);

  useEffect(() => { callback.current = onTranscript; }, [onTranscript]);

  function releaseMicrophone() {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    stopWatching.current?.(); stopWatching.current = null;
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
  }

  function cancel() {
    operation.current?.abort(); operation.current = null;
    if (recorder.current) {
      recorder.current.onstop = recorder.current.ondataavailable = recorder.current.onerror = null;
      if (recorder.current.state !== "inactive") recorder.current.stop();
      recorder.current = null;
    }
    releaseMicrophone(); recording.current = null;
    setListening(false); setProcessing(false); setCanRetry(false); setError("");
  }

  useEffect(() => {
    setSupported(window.isSecureContext && typeof navigator.mediaDevices?.getUserMedia === "function" && typeof window.MediaRecorder === "function");
    return () => {
      operation.current?.abort(); operation.current = null;
      if (recorder.current) {
        recorder.current.onstop = recorder.current.ondataavailable = recorder.current.onerror = null;
        if (recorder.current.state !== "inactive") recorder.current.stop();
      }
      releaseMicrophone(); recording.current = null;
    };
  }, []);

  async function transcribe(controller: AbortController) {
    const saved = recording.current;
    if (!saved) return;
    setProcessing(true); setCanRetry(false); setError("");
    let retryable = true;
    try {
      const response = await fetch("/api/transcribe", {
        method: "POST", headers: { "Content-Type": saved.audio.type, ...(pinned.current?.() ? { "X-Transcribe-Language": pinned.current()! } : {}) }, body: saved.audio,
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30_000)]),
      });
      retryable = response.status === 429 || response.status >= 500;
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(typeof result?.error === "string" ? result.error : "Could not transcribe. Please retry.");
      retryable = false;
      if (controller.signal.aborted) return;
      if (typeof result?.text !== "string" || !result.text.trim()) throw new Error("No speech detected. Please record again.");
      const text = [saved.prefix.trim(), result.text.trim()].filter(Boolean).join(" ");
      if (text.length > 1000) throw new Error("Your draft plus recording exceeds 1,000 characters. Shorten the draft or record a shorter message.");
      callback.current(text, typeof result.language === "string" ? result.language : null); recording.current = null;
    } catch (e) {
      if (!controller.signal.aborted) { setError(e instanceof Error ? e.message : "Transcription failed. Please retry."); setCanRetry(retryable); if (!retryable) recording.current = null; }
    } finally {
      if (operation.current === controller) { operation.current = null; setProcessing(false); }
    }
  }

  async function toggle(prefix = "") {
    if (recorder.current) { if (recorder.current.state === "recording") recorder.current.stop(); return; }
    if (operation.current) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder || !window.isSecureContext) {
      setError("Voice needs microphone support and HTTPS or localhost. You can still type your message."); return;
    }
    const controller = new AbortController();
    operation.current = controller;
    setProcessing(true); setError(""); setCanRetry(false); recording.current = null;
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (controller.signal.aborted) { media.getTracks().forEach(track => track.stop()); return; }
      stream.current = media;
      const mimeType = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"].find(type => MediaRecorder.isTypeSupported(type));
      if (!mimeType) throw new Error("This browser cannot record a supported audio format. Please type instead.");
      const instance = new MediaRecorder(media, { mimeType });
      const chunks: Blob[] = [];
      recorder.current = instance;
      instance.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      instance.onerror = () => { cancel(); setError("Recording stopped unexpectedly. Please record again."); };
      instance.onstop = () => {
        recorder.current = null; releaseMicrophone(); setListening(false);
        recording.current = { audio: new Blob(chunks, { type: instance.mimeType }), prefix };
        void transcribe(controller);
      };
      instance.start(); setListening(true); setProcessing(false);
      timer.current = setTimeout(() => { if (instance.state === "recording") instance.stop(); }, 30_000);
      stopWatching.current = watchForSilence(media, heardSpeech => {
        if (instance.state !== "recording") return;
        if (heardSpeech) { instance.stop(); return; }
        // Nothing was said: don't upload silence (it costs quota and only returns "no speech").
        cancel(); setError("Didn’t catch anything. Tap the mic and try again, or type your message.");
      });
    } catch (e) {
      if (controller.signal.aborted) return;
      cancel();
      setError(e instanceof DOMException && e.name === "NotAllowedError" ? "Microphone access was denied. Allow it in browser settings or type your message." : e instanceof DOMException && e.name === "NotFoundError" ? "No microphone found. Connect one or type your message." : e instanceof Error ? e.message : "Could not start recording. Please retry.");
    }
  }

  function retry() {
    if (operation.current || !recording.current) return;
    const controller = new AbortController(); operation.current = controller;
    void transcribe(controller);
  }

  return { supported, listening, processing, error, canRetry, toggle, retry, cancel };
}
