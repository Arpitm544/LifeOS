"use client";

import { useEffect, useRef, useState } from "react";

export function useVoiceInput(onTranscript: (text: string) => void) {
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

  useEffect(() => { callback.current = onTranscript; }, [onTranscript]);

  function releaseMicrophone() {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
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
        method: "POST", headers: { "Content-Type": saved.audio.type }, body: saved.audio,
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
      callback.current(text); recording.current = null;
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
