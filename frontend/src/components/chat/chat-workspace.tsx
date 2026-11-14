"use client";

import Link from "next/link";
import { Mic, Square, Volume2, VolumeX } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ActionCard } from "@/components/chat/action-card";
import { AgentSteps } from "@/components/chat/agent-steps";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { useDisplayName } from "@/hooks/use-display-name";
import { useVoiceInput } from "@/hooks/use-voice-input";
import { useVoiceOutput } from "@/hooks/use-voice-output";
import { readableError } from "@/lib/api";
import { languages, readLanguageSetting, replyLanguage, saveLanguageSetting, scriptLanguage, speechLocale, type LanguageSetting } from "@/lib/language";
import { formatDeadline, formatHours } from "@/lib/task-utils";
import type { ChatResponse } from "@/lib/types";

type Message = { id: string; key: string; text: string; language: string | null; status: "sending" | "done" | "error"; response?: ChatResponse; error?: string };
const prompts = ["What should I do next?", "Can I fit in a 2-hour project by Friday?", "Plan my day.", "I never work after 9 pm."];

export function ChatWorkspace() {
  const { api, preferences, reloadTasks, reloadPreferences, reducedMotion } = useWorkspace();
  const name = useDisplayName();
  const [text, setText] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const [voiceError, setVoiceError] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const sending = messages.some(message => message.status === "sending");
  const [language, setLanguage] = useState<LanguageSetting>("auto");
  const heard = useRef<string | null>(null);
  const voiceInput = useVoiceInput((value, spoken) => { setText(value); heard.current = spoken; input.current?.focus(); });
  const voiceOutput = useVoiceOutput(setVoiceError);

  useEffect(() => { setLanguage(readLanguageSetting()); }, []);
  useEffect(() => {
    const prompt = new URLSearchParams(window.location.search).get("prompt");
    if (prompt) { setText(prompt.slice(0, 1000)); input.current?.focus(); }
  }, []);
  useEffect(() => { if (messages.length) end.current?.scrollIntoView({ behavior: reducedMotion ? "instant" : "smooth", block: "nearest" }); }, [messages, reducedMotion]);

  async function deliver(message: Message) {
    setMessages(current => current.map(m => m.id === message.id ? { ...message, status: "sending", error: undefined } : m));
    try {
      // The same Idempotency-Key is reused on retry, so a request that reached the server is not applied twice.
      const response = await api<ChatResponse>("/api/chat", { method: "POST", headers: { "Idempotency-Key": message.key }, body: { text: message.text, client_tz: preferences.timezone, ...(message.language ? { language: message.language } : {}) } });
      setMessages(current => current.map(m => m.id === message.id ? { ...m, status: "done", response } : m));
      if (response.actions.length) {
        await Promise.all([reloadTasks(), response.actions.some(a => a.type === "preference_set") ? reloadPreferences() : Promise.resolve()]).catch(() => undefined);
      }
    } catch (e) {
      setMessages(current => current.map(m => m.id === message.id ? { ...m, status: "error", error: readableError(e, "LifeOS could not answer.") } : m));
    }
  }

  function send(value: string) {
    const clean = value.trim().slice(0, 1000);
    if (!clean || sending) return;
    const message: Message = { id: crypto.randomUUID(), key: crypto.randomUUID(), text: clean, language: replyLanguage(language, heard.current, clean), status: "sending" };
    heard.current = null;
    setMessages(current => [...current, message]);
    deliver(message);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!text.trim() || sending || voiceInput.listening || voiceInput.processing) return;
    send(text); setText(""); input.current?.focus();
  }

  const last = messages.at(-1);
  return <div className="two-columns chat-columns"><div className="chat-main">
    <section className="panel conversation" aria-label="Chat conversation">
      {messages.length === 0 ? <div className="chat-empty"><p className="eyebrow blue">LifeOS</p><h2>Hi {name.first}. What’s on your mind?</h2><p className="muted">Add tasks and events, ask what’s next, check if something fits, or set your working hours. Every change can be undone for a few seconds.</p></div> : null}
      <div className="message-log" role="log" aria-live="polite" aria-relevant="additions">{messages.map(message => {
        const response = message.response;
        const choice = response?.confirmation ? { label: response.confirmation.prompt, options: response.confirmation.options } : response?.clarification ? { label: response.clarification.question, options: response.clarification.options } : null;
        const isLast = message.id === last?.id;
        const speaking = speakingId === message.id;
        return <div key={message.id} className="message-pair"><div className="user-message">{message.text}</div><div className="assistant-message">
          <p className="eyebrow blue">LifeOS</p>
          {message.status === "sending" ? <p className="muted" role="status">Thinking…</p> : null}
          {message.status === "error" ? <><p className="error-message" role="alert">{message.error}</p><button className="button secondary" onClick={() => deliver(message)} disabled={sending}>Try again</button></> : null}
          {response ? <>
            <p>{response.reply}</p>
            {response.fallback ? <p className="muted fallback-note">The assistant is unavailable right now, so this was handled by quick add.</p> : null}
            {response.actions.map((action, index) => <ActionCard key={action.action_id ?? `${message.id}-${index}`} action={action} />)}
            {response.steps?.length ? <AgentSteps steps={response.steps} open={isLast} /> : null}
            <button className="text-button voice-reply" type="button" onClick={() => { setVoiceError(""); if (speaking && (voiceOutput.loading || voiceOutput.playing || voiceOutput.url)) { voiceOutput.stop(); setSpeakingId(null); } else { setSpeakingId(message.id); void voiceOutput.read(response.reply.slice(0, 500), speechLocale(message.language ?? scriptLanguage(response.reply))); } }}>{speaking && voiceOutput.playing ? <VolumeX size={16} aria-hidden="true" /> : <Volume2 size={16} aria-hidden="true" />} {speaking && voiceOutput.loading ? "Preparing audio… (click to cancel)" : speaking && voiceOutput.playing ? "Stop reading" : response.reply.length > 500 ? "Listen to first 500 characters" : "Listen"}</button>
            {response.conflicts.length ? <div className="conflict-banner compact" role="alert"><b>Heads up:</b> {response.conflicts.map(c => `${formatHours(c.shortfall_min)} short before ${formatDeadline(c.deadline_at, preferences.timezone)}`).join("; ")}.<Link className="text-button" href="/today">See options <span aria-hidden="true">→</span></Link></div> : null}
            {choice?.options.length ? <div className="chip-row" role="group" aria-label={choice.label || "Choose an answer"}>{choice.options.map(option => <button key={option} className="chip" disabled={!isLast || sending} onClick={() => send(option)}>{option}</button>)}</div> : null}
          </> : null}
        </div></div>;
      })}</div><div ref={end} />
    </section>
    <form className="panel composer" onSubmit={submit}><label className="sr-only" htmlFor="chat-message">Your message</label><textarea ref={input} id="chat-message" value={text} onChange={e => setText(e.target.value)} readOnly={voiceInput.listening || voiceInput.processing} maxLength={1000} rows={2} placeholder="Tell me what’s on your mind…" onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if (!voiceInput.listening && !voiceInput.processing) e.currentTarget.form?.requestSubmit(); } }} /><div className="composer-bottom"><span>{text.length}/1000 · Enter to send, Shift+Enter for a new line</span><div className="button-row">{voiceInput.supported !== false ? <button type="button" className={`mic-button${voiceInput.listening ? " listening" : ""}`} onClick={() => voiceInput.toggle(text)} disabled={voiceInput.processing || sending} aria-label={voiceInput.listening ? "Stop recording" : "Add message with your voice"} title={voiceInput.listening ? "Stop recording" : "Use voice input"}>{voiceInput.listening ? <Square size={16} /> : <Mic size={18} />}</button> : null}<button type="submit" className="button" disabled={!text.trim() || sending || voiceInput.listening || voiceInput.processing}>{sending ? "Sending…" : "Send message"} <span aria-hidden="true">↑</span></button></div></div>{voiceInput.listening ? <span className="composer-note" role="status">Listening… Select stop when you’re finished. Recording stops automatically after 30 seconds.</span> : voiceInput.processing ? <span className="composer-note" role="status">Turning your recording into text…</span> : null}{voiceInput.error ? <span className="composer-note error-message" role="alert">{voiceInput.error} {voiceInput.canRetry ? <button type="button" className="text-button" onClick={voiceInput.retry}>Retry transcription</button> : null}</span> : null}{voiceError ? <span className="composer-note error-message" role="alert">{voiceError}</span> : null}</form>
    {voiceOutput.url ? <audio ref={voiceOutput.element} src={voiceOutput.url} autoPlay onPlay={() => voiceOutput.setPlaying(true)} onEnded={voiceOutput.stop} onError={() => { voiceOutput.stop(); setVoiceError("Could not play the spoken reply."); }} /> : null}
  </div><aside className="side-stack">
      <section className="panel prompts"><h2 className="eyebrow muted">Try asking</h2>{prompts.map(prompt => <button key={prompt} disabled={sending || voiceInput.listening || voiceInput.processing} onClick={() => { setText(prompt); input.current?.focus(); }}>“{prompt}” <span aria-hidden="true">→</span></button>)}</section>
      <section className="panel chat-language"><h2 className="eyebrow muted">Language</h2><label className="sr-only" htmlFor="chat-language">Reply language</label><select id="chat-language" value={language} onChange={e => { const value = e.target.value as LanguageSetting; setLanguage(value); saveLanguageSetting(value); }}><option value="auto">Auto — match how I speak or type</option>{languages.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}</select><p>Speak or type in any of these. LifeOS replies in the same language and reads replies aloud with a matching voice.</p></section>
      <section className="panel chat-help"><h2 className="eyebrow muted">Have a syllabus?</h2><p>Upload it and LifeOS adds every deadline and plans the time. <Link className="text-button" href="/import">Import a syllabus <span aria-hidden="true">→</span></Link></p></section>
      <section className="panel chat-help"><h2 className="eyebrow muted">Good to know</h2><p>Deletes and changes to more than three items ask you first. Reply with the buttons or type “yes” or “no”.</p><p>Messages on this screen clear when you leave it. Your tasks, events and preferences are saved to your account.</p></section>
    </aside></div>;
}
