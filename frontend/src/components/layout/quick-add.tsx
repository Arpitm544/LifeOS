"use client";

import { Mic, Square } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ActionCard } from "@/components/chat/action-card";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { useVoiceInput } from "@/hooks/use-voice-input";
import { readableError } from "@/lib/api";
import type { ChatResponse } from "@/lib/types";

/** Ctrl/Cmd + K quick add and the floating mic (PRD 6): the same chat pipeline from any screen. */
export function QuickAdd() {
  const { api, preferences, reloadTasks, reloadPreferences } = useWorkspace();
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [response, setResponse] = useState<ChatResponse>();
  const [error, setError] = useState("");
  const voice = useVoiceInput(value => { setText(value); input.current?.focus(); });

  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && !event.altKey && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(true);
      }
    }
    document.addEventListener("keydown", shortcut);
    return () => document.removeEventListener("keydown", shortcut);
  }, []);
  useEffect(() => {
    if (open && dialog.current && !dialog.current.open) { dialog.current.showModal(); input.current?.focus(); }
  }, [open]);

  function close() {
    voice.cancel();
    dialog.current?.close();
    setOpen(false); setResponse(undefined); setError(""); setText("");
  }

  async function send(value: string) {
    const clean = value.trim().slice(0, 1000);
    if (!clean || sending) return;
    setSending(true); setError("");
    try {
      const result = await api<ChatResponse>("/api/chat", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: { text: clean, client_tz: preferences.timezone } });
      setResponse(result); setText("");
      if (result.actions.length) {
        await Promise.all([reloadTasks(), result.actions.some(a => a.type === "preference_set") ? reloadPreferences() : Promise.resolve()]).catch(() => undefined);
        window.dispatchEvent(new Event("lifeos:changed"));
      }
    } catch (e) { setError(readableError(e, "LifeOS could not answer.")); }
    finally { setSending(false); }
  }

  function submit(event: FormEvent) { event.preventDefault(); if (!voice.listening && !voice.processing) void send(text); }

  const choice = response?.confirmation ? response.confirmation.options : response?.clarification ? response.clarification.options : [];
  return <>
    <button type="button" className={`floating-mic${voice.listening ? " listening" : ""}`} aria-label="Quick add with voice or text (Ctrl or Cmd + K)" title="Quick add (Ctrl/Cmd + K)"
      onClick={() => { setOpen(true); if (voice.supported !== false && !voice.listening) window.setTimeout(() => voice.toggle(""), 0); }}><Mic size={22} aria-hidden="true" /></button>
    {open ? <dialog ref={dialog} className="task-dialog quick-add" aria-labelledby="quick-add-title" onCancel={close} onClose={() => setOpen(false)}>
      <button className="dialog-close" onClick={close} aria-label="Close quick add">×</button>
      <p className="eyebrow blue" id="quick-add-title">Quick add</p>
      <form onSubmit={submit}>
        <label className="sr-only" htmlFor="quick-add-text">What do you need to do?</label>
        <textarea ref={input} id="quick-add-text" rows={2} maxLength={1000} value={text} readOnly={voice.listening || voice.processing} onChange={e => setText(e.target.value)}
          placeholder="Finish the DBMS report by Friday, about 3 hours" onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} />
        <div className="button-row">
          {voice.supported !== false ? <button type="button" className={`mic-button${voice.listening ? " listening" : ""}`} onClick={() => voice.toggle(text)} disabled={voice.processing || sending} aria-label={voice.listening ? "Stop recording" : "Speak instead"}>{voice.listening ? <Square size={16} /> : <Mic size={18} />}</button> : null}
          <button type="submit" className="button" disabled={!text.trim() || sending || voice.listening || voice.processing}>{sending ? "Sending…" : "Add"}</button>
        </div>
        {voice.listening ? <small role="status">Listening… press stop when you’re finished.</small> : voice.processing ? <small role="status">Turning your recording into text…</small> : null}
        {voice.error ? <small className="error-message" role="alert">{voice.error}</small> : null}
      </form>
      {error ? <p className="error-message" role="alert">{error}</p> : null}
      {response ? <div className="quick-add-result" aria-live="polite"><p>{response.reply}</p>
        {response.actions.map((action, index) => <ActionCard key={action.action_id ?? index} action={action} />)}
        {choice.length ? <div className="chip-row">{choice.map(option => <button key={option} className="chip" disabled={sending} onClick={() => send(option)}>{option}</button>)}</div> : null}
      </div> : null}
    </dialog> : null}
  </>;
}
