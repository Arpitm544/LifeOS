"use client";

import { useEffect, useRef, useState } from "react";

export function useVoiceOutput(onError: (message: string) => void) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const element = useRef<HTMLAudioElement>(null);
  const pending = useRef<AbortController | null>(null);
  const objectUrl = useRef("");

  function release() {
    pending.current?.abort(); pending.current = null;
    element.current?.pause();
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = "";
  }
  function stop() {
    release(); setUrl(""); setLoading(false); setPlaying(false);
  }
  useEffect(() => () => release(), []);

  async function read(text: string) {
    stop();
    const controller = new AbortController(); pending.current = controller;
    setLoading(true);
    try {
      const response = await fetch("/api/speak", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30_000)]),
      });
      if (!response.ok) {
        const result = await response.json().catch(() => null);
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
