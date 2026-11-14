"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { Orbit } from "@/components/ui/orbit";
import { TaskCard } from "@/components/tasks/task-card";
import { useVoiceInput } from "@/hooks/use-voice-input";

type Message = { id: string; text: string; taskId?: string; undone?: boolean };
const prompts = ["What should I do next?", "Can I fit in a 2-hour project?", "Plan tomorrow around class."];
const previewReply = "This is the frontend preview. AI understanding and scheduling aren’t connected yet. You can save this message as a simple task, or add its details in Tasks.";

export function ChatWorkspace() {
  const { tasks, preferences, saveTask, deleteTask, notify } = useWorkspace();
  const [text, setText] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [speaking, setSpeaking] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const voice = useVoiceInput(setText);
  const sampleTask = tasks.find(task => task.id === "report");
  const name = preferences.name.trim().split(/\s+/)[0];

  useEffect(() => {
    const prompt = new URLSearchParams(window.location.search).get("prompt");
    if (prompt) { setText(prompt.slice(0, 1000)); input.current?.focus(); }
    return () => window.speechSynthesis?.cancel();
  }, []);
  useEffect(() => { if (messages.length) end.current?.scrollIntoView({ behavior: preferences.reducedMotion ? "instant" : "smooth", block: "nearest" }); }, [messages.length, preferences.reducedMotion]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!text.trim() || voice.listening) return;
    setMessages(current => [...current, { id: crypto.randomUUID(), text: text.trim() }]);
    setText(""); input.current?.focus();
  }

  function saveMessage(message: Message) {
    try {
      const task = saveTask({ title: message.text, deadline: null, effort: 30, importance: 3, category: "other" });
      setMessages(current => current.map(m => m.id === message.id ? { ...m, taskId: task.id, undone: false } : m));
    } catch (e) { notify(e instanceof Error ? e.message : "Could not create task."); }
  }

  function readReply() {
    if (!("speechSynthesis" in window)) { notify("Spoken replies are unavailable in this browser."); return; }
    if (speaking) { window.speechSynthesis.cancel(); setSpeaking(false); return; }
    const utterance = new SpeechSynthesisUtterance("This is your LifeOS preview. AI is not connected yet. You can save a simple task or add details in Tasks.");
    utterance.lang = "en-IN"; utterance.onend = utterance.onerror = () => setSpeaking(false);
    window.speechSynthesis.cancel(); setSpeaking(true); window.speechSynthesis.speak(utterance);
  }

  return <div className="two-columns chat-columns"><div className="chat-main">
    <section className="panel conversation" aria-label="Chat conversation"><p className="eyebrow muted">Example conversation · Sample data</p><div className="user-message">Finish my DBMS report by Friday. I think it needs 3 hours. Also, leave my evenings free.</div><div className="assistant-message"><p className="eyebrow blue">LifeOS · Example reply</p><p>Got it, {name}. I’ve added your report and kept your evenings clear. Here’s a comfortable start.</p>{sampleTask ? <TaskCard task={sampleTask} /> : <p className="muted">The sample task has been removed.</p>}<Link href="/tasks" className="text-button">Edit task <span aria-hidden="true">↗</span></Link><p className="muted">You usually focus best in the morning.<br />Keep your focus hours protected in your preferences.</p><Link href="/profile" className="button">Set focus hours</Link></div>
      <div className="message-log" role="log" aria-live="polite" aria-relevant="additions">{messages.map(message => {
        const task = tasks.find(t => t.id === message.taskId);
        return <div key={message.id} className="message-pair"><div className="user-message">{message.text}</div><div className="assistant-message"><p className="eyebrow blue">LifeOS · Demo</p><p>{previewReply}</p>{task ? <><TaskCard task={task} /><button className="text-button" onClick={() => { deleteTask(task.id); setMessages(current => current.map(m => m.id === message.id ? { ...m, taskId: undefined, undone: true } : m)); }}>Undo task creation</button></> : <div className="button-row">{message.text.length <= 120 ? <button className="button secondary" onClick={() => saveMessage(message)}>{message.undone ? "Save as task again" : "Save as simple task"}</button> : <p className="muted">Use a title under 120 characters in the task form.</p>}<Link className="text-button" href="/tasks">Add task details ↗</Link></div>}</div></div>;
      })}</div><div ref={end} />
    </section>
    <form className="panel composer" onSubmit={submit}><label className="sr-only" htmlFor="chat-message">Your message</label><textarea ref={input} id="chat-message" value={text} onChange={e => setText(e.target.value)} maxLength={1000} rows={2} placeholder={voice.listening ? "Listening… your words appear here" : "Tell me what’s on your mind…"} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} /><div className="composer-bottom"><span>{voice.listening ? "Listening · Review before sending" : "Text or voice · You’re in control"}</span><div className="button-row"><button type="button" className={`mic-button ${voice.listening ? "listening" : ""}`} aria-label={voice.listening ? "Stop listening" : "Use voice input"} aria-pressed={voice.listening} onClick={() => voice.toggle(text)}><span aria-hidden="true">{voice.listening ? "■" : "◉"}</span></button><button type="submit" className="button" disabled={!text.trim() || voice.listening}>Send message <span aria-hidden="true">↑</span></button></div></div><small className="composer-note">Demo chat · Messages stay in this tab. Tasks save on this device.</small></form>
    {voice.error ? <p className="error-message" role="alert">{voice.error}</p> : null}
  </div><aside className="side-stack"><section className={`panel dark voice-panel ${voice.listening ? "is-listening" : ""}`}><Orbit variant="voice" /><div className="voice-copy"><p className="eyebrow lime">{voice.listening ? "I’m listening" : "Your personal assistant"}</p><h2>A little help, just a word away.</h2><p>{voice.listening ? "Speak naturally. Tap again to stop." : "Tap to talk. Review before sending."}</p><button className="button" onClick={() => voice.toggle(text)} aria-pressed={voice.listening}>{voice.listening ? "Stop listening" : "Start speaking"}<span aria-hidden="true">{voice.listening ? "■" : "◉"}</span></button><small>{voice.supported === false ? "Voice is unavailable here. The text input still works." : "Up to 30 seconds · Microphone permission required"}</small></div></section>
      <section className="panel prompts"><h2 className="eyebrow muted">Try asking</h2>{prompts.map(prompt => <button key={prompt} onClick={() => { setText(prompt); input.current?.focus(); }}>“{prompt}” <span aria-hidden="true">↗</span></button>)}</section>
      <button className="text-button read-reply" onClick={readReply} aria-pressed={speaking}>{speaking ? "Stop spoken preview ■" : "Listen to a spoken preview ◉"}</button><p className="voice-disclosure">Your browser’s speech service may process microphone audio. LifeOS does not record or store audio.</p>
    </aside></div>;
}
