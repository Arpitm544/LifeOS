"use client";

import { useEffect, useRef, useState } from "react";

export function useVoiceOutput(onError: (message: string) => void) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const element = useRef<HTMLAudioElement>(null);
  const pending = useRef<AbortController | null>(null);
  const objectUrl = useRef("");
  const spoken = useRef<SpeechSynthesisUtterance | null>(null);

  // Languages without a server voice use the device's own voices (Web Speech API).
  function speakInBrowser(text: string, locale: string) {
    const synth = globalThis.speechSynthesis, Utterance = globalThis.SpeechSynthesisUtterance;
    if (!synth || !Utterance) throw new Error("Spoken replies in this language are not supported in this browser.");
    const prefix = locale.split("-")[0].toLowerCase();
    const voice = synth.getVoices().find(v => v.lang.toLowerCase() === locale.toLowerCase()) ?? synth.getVoices().find(v => v.lang.toLowerCase().startsWith(prefix));
    if (!voice) throw new Error("No voice for this language is installed on this device. Add one in your system settings.");
    const utterance = new Utterance(text);
    utterance.lang = voice.lang; utterance.voice = voice;
    utterance.onstart = () => { if (spoken.current === utterance) setPlaying(true); };
    utterance.onend = utterance.onerror = () => { if (spoken.current === utterance) { spoken.current = null; setPlaying(false); } };
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
  useEffect(() => () => release(), []);

  /** `locale` is a BCP 47 tag such as "hi-IN"; omit it for English. */
  async function read(text: string, locale?: string) {
    stop();
    const controller = new AbortController(); pending.current = controller;
    setLoading(true);
    try {
      const language = locale && !locale.toLowerCase().startsWith("en") ? locale : undefined;
      const response = await fetch("/api/speak", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(language ? { text, language } : { text }),
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30_000)]),
      });
      if (!response.ok) {
        const result = await response.json().catch(() => null);
        if (language && result?.code === "unsupported_language") {
          if (controller.signal.aborted) return;
          speakInBrowser(text, language);
          return;
        }
        throw new Error(typeof result?.error === "string" ? result.error : "Could not generate speech. Please retry.");
      }
      if (!response.headers.get("content-type")?.startsWith("audio/")) throw new Error("Could not load spoken reply. Please retry.");
      const audio = await response.blob();
      if (controller.signal.aborted) return;
      if (!audio.size) throw new Error("The spoken reply was empty. Please retry.");
      objectUrl.current = URL.createObjectURL(audio); setUrl(objectUrl.current);
    } catch (e) {
      if (!controller.signal.aborted) onError(e instanceof Error ? e.message : "Could not load spoken reply. Please retry.");
    } finally {
      if (pending.current === controller) { pending.current = null; setLoading(false); }
    }
  }
  return { url, loading, playing, element, read, stop, setPlaying };
}
