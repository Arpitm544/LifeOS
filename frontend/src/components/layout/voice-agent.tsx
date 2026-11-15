"use client";

import { Check, Mic, Square, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { useDisplayName } from "@/hooks/use-display-name";
import { useVoiceInput } from "@/hooks/use-voice-input";
import { useVoiceOutput } from "@/hooks/use-voice-output";
import { readableError } from "@/lib/api";
import { baseLanguage, languages, pinnedLanguage, readLanguageSetting, replyLanguage, scriptLanguage, speechLocale } from "@/lib/language";
import type { ChatResponse } from "@/lib/types";
import { actionLabels, asksQuestion, farewell, greeting, isGoodbye, spokenText } from "@/lib/voice-agent";

type Phase = "speaking" | "listening" | "transcribing" | "thinking" | "paused";
type Turn = { id: string; who: "you" | "agent"; text: string; done?: string[] };

const status: Record<Phase, string> = {
  speaking: "Speaking… tap to interrupt",
  listening: "Listening… I’ll reply when you pause",
  transcribing: "Got it…",
  thinking: "Working on it…",
  paused: "Tap the mic to talk",
};

/**
 * A spoken conversation: the agent greets, listens until the user pauses, sends the words through the same
 * chat pipeline as Chat (so tasks and events are created on the server), says the answer, and listens again.
 * The panel doesn't block the page, so Today and Week update behind it as changes land.
 */
export function VoiceAgent({ onClose }: { onClose: () => void }) {
  const { api, preferences, reloadTasks, reloadPreferences } = useWorkspace();
  const name = useDisplayName();
  const [phase, setPhase] = useState<Phase>("speaking");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [note, setNote] = useState("");
  const awaitingAnswer = useRef(false);
  const closing = useRef(false);
  const active = useRef(true);
  const started = useRef(false);
  const wasListening = useRef(false);
  const retried = useRef(false);
  const retryTimer = useRef(0);
  const log = useRef<HTMLOListElement>(null);
  // The conversation's language: the chat setting if one is chosen, else the browser's language, then whatever the user speaks.
  const conversationLanguage = useRef<string | null>(null);

  const output = useVoiceOutput(message => { setNote(message); afterSpeaking(); }, () => afterSpeaking());
  const input = useVoiceInput((text, language) => { void respond(text, language); }, { language: pinnedLanguage });

  function addTurn(turn: Omit<Turn, "id">) { setTurns(list => [...list, { ...turn, id: crypto.randomUUID() }].slice(-12)); }

  function say(text: string, locale?: string, thenClose = false) {
    closing.current = thenClose;
    setPhase("speaking");
    void output.read(text, locale);
  }

  function listen() {
    if (!active.current) return;
    setNote(""); wasListening.current = false;
    setPhase("listening");
    void input.toggle("");
  }

  function afterSpeaking() {
    if (!active.current) return;
    if (closing.current) { end(); return; }
    listen();
  }

  async function respond(text: string, heard: string | null) {
    if (!active.current) return;
    addTurn({ who: "you", text });
    // An utterance whose language wasn't detected keeps the conversation's language instead of falling back to English.
    const language = replyLanguage(readLanguageSetting(), heard, text) ?? conversationLanguage.current;
    if (language) conversationLanguage.current = language;
    if (isGoodbye(text, awaitingAnswer.current)) {
      const bye = farewell(conversationLanguage.current);
      addTurn({ who: "agent", text: bye }); say(bye, speechLocale(conversationLanguage.current), true); return;
    }
    setPhase("thinking");
    try {
      const result = await api<ChatResponse>("/api/chat", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: { text, client_tz: preferences.timezone, ...(language ? { language } : {}) } });
      if (!active.current) return;
      awaitingAnswer.current = asksQuestion(result);
      addTurn({ who: "agent", text: result.reply, done: actionLabels(result.actions) });
      if (result.actions.length) {
        // Changes are already saved; refresh the rest of the app in the background while the agent talks.
        void Promise.all([reloadTasks(), result.actions.some(a => a.type === "preference_set") ? reloadPreferences() : Promise.resolve()])
          .catch(() => undefined).finally(() => window.dispatchEvent(new Event("lifeos:changed")));
      }
      say(spokenText(result), speechLocale(language ?? scriptLanguage(result.reply)));
    } catch (e) {
      if (!active.current) return;
      const message = readableError(e, "LifeOS could not answer.");
      setNote(message);
      addTurn({ who: "agent", text: "Sorry, I couldn’t do that. Please try again." });
      say("Sorry, I couldn’t do that. Please try again.");
    }
  }

  function end() {
    active.current = false;
    window.clearTimeout(retryTimer.current); retryTimer.current = 0;
    input.cancel(); output.stop();
    onClose();
  }

  // Open with a greeting. In development React mounts twice: the first cleanup cancels the request, so the
  // second mount re-arms and greets again, but the greeting is only added to the transcript once.
  useEffect(() => {
    active.current = true;
    if (!started.current) {
      const setting = readLanguageSetting();
      const browser = baseLanguage(typeof navigator === "undefined" ? null : navigator.language);
      conversationLanguage.current = setting !== "auto" ? setting : languages.some(l => l.code === browser) ? browser : null;
    }
    const hello = greeting(name.first, conversationLanguage.current);
    if (!started.current) { started.current = true; addTurn({ who: "agent", text: hello }); }
    say(hello, speechLocale(conversationLanguage.current));
    return () => { active.current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Follow the microphone: once a recording ends it is being transcribed; an empty or failed turn pauses.
  // A temporary failure (busy service or voice limit) keeps the recording, so retry it once before pausing.
  useEffect(() => {
    if (phase !== "listening" && phase !== "transcribing") return;
    if (input.listening) { wasListening.current = true; retried.current = false; return; }
    if (input.processing && wasListening.current) { setPhase("transcribing"); return; }
    if (input.processing || !input.error || retryTimer.current) return;
    if (input.canRetry && !retried.current) {
      retried.current = true;
      setNote("Voice is busy right now. I’ll try again in a moment…");
      setPhase("transcribing");
      retryTimer.current = window.setTimeout(() => { retryTimer.current = 0; if (active.current) { setNote(""); input.retry(); } }, 4000);
      return;
    }
    setNote(input.error); setPhase("paused");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input.listening, input.processing, input.error, input.canRetry, phase]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") end(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" }); }, [turns]);

  function tapOrb() {
    if (phase === "speaking") { output.stop(); if (closing.current) end(); else listen(); }
    else if (phase === "listening" && input.listening) void input.toggle(); // done talking: send now
    else if (phase === "paused") listen();
  }

  const busy = phase === "thinking" || phase === "transcribing";
  return <section className="voice-agent" role="dialog" aria-modal="false" aria-label="LifeOS voice assistant">
    <header className="voice-agent-head">
      <span className="voice-agent-title"><span className={`voice-agent-dot is-${phase}`} aria-hidden="true" /> LifeOS voice</span>
      <button type="button" className="voice-agent-close" onClick={end} aria-label="End conversation"><X size={18} aria-hidden="true" /></button>
    </header>
    <ol className="voice-agent-log" ref={log} aria-live="polite">
      {turns.map(turn => <li key={turn.id} className={`is-${turn.who}`}>
        <p>{turn.text}</p>
        {turn.done?.length ? <span className="voice-agent-done">{turn.done.map(label => <span key={label}><Check size={12} aria-hidden="true" /> {label}</span>)}</span> : null}
      </li>)}
    </ol>
    <div className="voice-agent-controls">
      <button type="button" className={`voice-orb is-${phase}`} onClick={tapOrb} disabled={busy}
        aria-label={phase === "speaking" ? "Interrupt and talk" : phase === "listening" ? "Done talking" : phase === "paused" ? "Start talking" : "Working"}>
        <span className="voice-orb-ring" aria-hidden="true" />
        {phase === "listening" ? <Square size={18} aria-hidden="true" /> : busy ? <span className="voice-orb-dots" aria-hidden="true"><i /><i /><i /></span> : <Mic size={22} aria-hidden="true" />}
      </button>
      <div className="voice-agent-status">
        <p role="status">{status[phase]}</p>
        {note ? <small className="voice-agent-note">{note}</small> : <small>Say “bye” when you’re done.</small>}
      </div>
      <button type="button" className="voice-agent-end" onClick={end}>End</button>
    </div>
    {output.url ? <audio ref={output.element} src={output.url} autoPlay onPlay={() => output.setPlaying(true)} onEnded={output.finish} onError={() => { output.stop(); afterSpeaking(); }} /> : null}
  </section>;
}
