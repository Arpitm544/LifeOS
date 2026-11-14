"use client";

import { useEffect, useRef, useState } from "react";

type RecognitionResult = { isFinal: boolean; 0: { transcript: string } };
type Recognition = {
  lang: string; continuous: boolean; interimResults: boolean;
  onresult: ((event: { results: ArrayLike<RecognitionResult> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null; onstart: (() => void) | null;
  start: () => void; stop: () => void; abort: () => void;
};
type VoiceWindow = Window & { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };

export function useVoiceInput(onTranscript: (text: string) => void) {
  const [supported, setSupported] = useState<boolean | null>(null);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState("");
  const recognition = useRef<Recognition | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const callback = useRef(onTranscript);
  useEffect(() => { callback.current = onTranscript; }, [onTranscript]);

  useEffect(() => {
    const w = window as VoiceWindow;
    setSupported(!!(w.SpeechRecognition || w.webkitSpeechRecognition));
    return () => {
      if (timer.current) clearTimeout(timer.current);
      if (recognition.current) {
        recognition.current.onresult = recognition.current.onerror = recognition.current.onend = recognition.current.onstart = null;
        recognition.current.abort();
      }
    };
  }, []);

  function toggle(prefix = "") {
    if (recognition.current) { recognition.current.stop(); return; }
    const w = window as VoiceWindow;
    const Constructor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Constructor) { setError("Voice input is unavailable in this browser. You can keep typing, or try Chrome or Edge."); return; }
    setError("");
    const instance = new Constructor();
    recognition.current = instance;
    instance.lang = "en-IN"; instance.continuous = true; instance.interimResults = true;
    instance.onstart = () => setListening(true);
    instance.onresult = event => {
      const transcript = Array.from(event.results).map(result => result[0].transcript).join(" ");
      callback.current([prefix.trim(), transcript.trim()].filter(Boolean).join(" ").slice(0, 1000));
    };
    instance.onerror = event => {
      const messages: Record<string, string> = {
        "not-allowed": "Microphone access was denied. Allow it in browser settings, or type your message.",
        "audio-capture": "No microphone was found. Connect one, or use the text input.",
        "no-speech": "I didn’t hear anything. Try again when you’re ready.",
        network: "The browser’s speech service could not connect. Try again, or type instead.",
      };
      if (event.error !== "aborted") setError(messages[event.error] || "Voice input stopped. Please try again.");
    };
    instance.onend = () => {
      if (timer.current) clearTimeout(timer.current);
      recognition.current = null; setListening(false);
    };
    try {
      setListening(true); instance.start();
      timer.current = setTimeout(() => instance.stop(), 30_000);
    } catch {
      recognition.current = null; setListening(false); setError("Could not start voice input. Please try again.");
    }
  }

  return { supported, listening, error, toggle };
}
