"use client";

import { useState } from "react";
import { CalendarDays, Check, CheckCircle2, Clock3, ListChecks, MessageCircle, Play, RefreshCw, ShieldAlert, ShieldCheck, Sun, Target } from "lucide-react";

/** A miniature, scripted LifeOS for the landing page. Sample data only; nothing is saved. */
const views = [{ id: "Today", icon: Sun }, { id: "Week", icon: CalendarDays }, { id: "Chat", icon: MessageCircle }] as const;
type View = (typeof views)[number]["id"];

type Block = { id: string; time: string; end: string; title: string; kind: "focus" | "event" };
const schedule: Block[] = [
  { id: "thesis", time: "09:00", end: "10:30", title: "Thesis draft", kind: "focus" },
  { id: "standup", time: "10:30", end: "10:45", title: "Team standup", kind: "event" },
  { id: "problems", time: "11:00", end: "12:00", title: "Problem set 4", kind: "focus" },
  { id: "review", time: "16:00", end: "16:30", title: "Review tomorrow’s priorities", kind: "focus" },
];
const focusIds = schedule.filter(b => b.kind === "focus").map(b => b.id);
// The sample "now" sits between standup and the problem set.
const nowAfter = 1;

const week = [
  { day: "Mon", load: 0.55, items: ["Thesis draft", "Standup"] },
  { day: "Tue", load: 0.7, items: ["Problem set 4", "Gym"] },
  { day: "Wed", load: 0.4, items: ["Reading notes"] },
  { day: "Thu", load: 1.15, items: ["Lab report", "Essay draft", "Gym"], over: true },
  { day: "Fri", load: 0.6, items: ["Essay draft", "Review"] },
];

const prompts = [
  { ask: "Essay due Friday, about 3 hours", reply: "Added “Essay draft”, due Fri 17:00, 3 h. I planned two focus blocks for it on Wed and Thu.", card: { title: "Essay draft", meta: "Due Fri 17:00 · 3 h · P1" } },
  { ask: "Gym every Tue and Thu at 7 pm", reply: "Routine added. I’ll keep 19:00–20:00 free on Tuesdays and Thursdays.", card: { title: "Gym", meta: "Tue and Thu · 19:00–20:00" } },
  { ask: "Can I fit a 2-hour project by Friday?", reply: "Yes, it fits. You have 6 h 20 min of open time before Friday. Want me to plan it?", card: null },
];

export function WorkspacePreview() {
  const [view, setView] = useState<View>("Today");
  const [done, setDone] = useState<string[]>(["thesis"]);
  const [planning, setPlanning] = useState(false);
  const [resolved, setResolved] = useState(false);
  const [asked, setAsked] = useState<number | null>(null);
  const toggle = (id: string) => setDone(current => current.includes(id) ? current.filter(x => x !== id) : [...current, id]);
  const replan = () => { setPlanning(true); window.setTimeout(() => setPlanning(false), 900); };
  const doneCount = focusIds.filter(id => done.includes(id)).length;
  const next = schedule.slice(nowAfter + 1).find(b => !done.includes(b.id));

  return <div id="workspace-preview" className="workspace-preview" role="region" aria-label="Interactive sample LifeOS workspace">
    <div className="wp-chrome"><span className="wp-dots" aria-hidden="true"><i /><i /><i /></span><span className="wp-title">LifeOS · {view}</span><span className="wp-badge">Interactive preview · sample data</span></div>
    <div className="wp-body">
      <aside className="wp-sidebar">
        <span className="wp-brand"><span className="landing-logo" aria-hidden="true" /> LifeOS</span>
        <div className="wp-nav" role="group" aria-label="Choose a preview screen">
          {views.map(({ id, icon: Icon }) => <button type="button" key={id} className={view === id ? "is-active" : ""} aria-pressed={view === id} onClick={() => setView(id)}><Icon size={15} aria-hidden="true" /><span>{id}</span></button>)}
        </div>
        <p className="wp-sidebar-note">Sample workspace. Nothing here is saved.</p>
      </aside>

      <div key={view} className="wp-main" role="region" aria-label={`${view} preview`}>
        {view === "Today" ? <>
          <section className="wp-hero">
            <div><p className="wp-eyebrow">Monday 16 November</p><h3>Hello, Sam.</h3><p className="wp-brief">Good morning. Your day fits. {3 - doneCount ? `${3 - doneCount} focus block${3 - doneCount === 1 ? "" : "s"} still to go.` : "Every focus block is done."}</p></div>
            <div className="wp-hero-actions"><button type="button" className="wp-button" onClick={replan} disabled={planning}><RefreshCw size={13} aria-hidden="true" className={planning ? "wp-spin" : ""} /> {planning ? "Planning…" : "Replan"}</button><span className="wp-ghost"><Play size={12} aria-hidden="true" /> Read my brief</span></div>
          </section>
          <div className="wp-stats">
            <div className="wp-stat"><span className="wp-stat-label"><Clock3 size={13} aria-hidden="true" /> Open time left</span><strong>4 h 10 min</strong><span className="wp-meter"><span style={{ width: "52%" }} /></span></div>
            <div className="wp-stat"><span className="wp-stat-label"><Target size={13} aria-hidden="true" /> Focus blocks done</span><strong>{doneCount}<small> of 3</small></strong><span className="wp-meter"><span style={{ width: `${(doneCount / 3) * 100}%` }} /></span></div>
            <div className="wp-stat"><span className="wp-stat-label"><ListChecks size={13} aria-hidden="true" /> Due today</span><strong>{3 - doneCount}</strong><span className="wp-stat-note">{3 - doneCount ? "None overdue" : "All clear"}</span></div>
            <div className="wp-stat is-ok"><span className="wp-stat-label"><ShieldCheck size={13} aria-hidden="true" /> Capacity guard</span><strong>All fit</strong><span className="wp-stat-note">Deadlines fit your week</span></div>
          </div>
          <div className="wp-columns">
            <section className="wp-card">
              <div className="wp-card-head"><h4>Your schedule</h4><span>Tap a focus block to complete it</span></div>
              <ol className="wp-timeline">
                {schedule.flatMap((block, index) => {
                  const isDone = done.includes(block.id);
                  const row = <li key={block.id} className={`wp-item is-${block.kind} ${isDone ? "is-done" : ""} ${next?.id === block.id ? "is-next" : ""}`}>
                    <time>{block.time}<small>{block.end}</small></time>
                    <span className="wp-dot" aria-hidden="true" />
                    {block.kind === "focus"
                      ? <button type="button" className="wp-item-body" aria-pressed={isDone} onClick={() => toggle(block.id)}><span className="wp-item-title">{block.title}</span><span className="wp-item-meta"><span className="wp-chip">Focus</span>{isDone ? <><Check size={12} aria-hidden="true" /> Done</> : next?.id === block.id ? "Up next" : null}</span></button>
                      : <div className="wp-item-body"><span className="wp-item-title">{block.title}</span><span className="wp-item-meta"><span className="wp-chip is-event">Event</span>Room 2</span></div>}
                  </li>;
                  return index === nowAfter ? [row, <li key="now" className="wp-now" aria-label="Now, 10:50"><span>Now · 10:50</span></li>] : [row];
                })}
              </ol>
            </section>
            <section className="wp-card wp-now-card" aria-label="Now and next">
              <p className="wp-eyebrow is-light">Now</p><h4>Free time</h4><p className="wp-now-sub">10 min until your next block</p>
              <hr />
              <p className="wp-eyebrow is-light">Next</p><h4>{next ? next.title : "Nothing else planned"}</h4><p className="wp-now-sub">{next ? `Focus block at ${next.time}` : "Enjoy the rest of your day."}</p>
            </section>
          </div>
        </> : view === "Week" ? <>
          <div className="wp-view-head"><div><p className="wp-eyebrow">This week</p><h3>Planned vs. free time</h3></div><button type="button" className="wp-button" onClick={replan} disabled={planning}><RefreshCw size={13} aria-hidden="true" className={planning ? "wp-spin" : ""} /> {planning ? "Planning…" : "Replan week"}</button></div>
          {resolved
            ? <p className="wp-banner is-ok" role="status"><CheckCircle2 size={15} aria-hidden="true" /> Moved “Gym” to Saturday. Every deadline fits now.</p>
            : <p className="wp-banner is-risk"><ShieldAlert size={15} aria-hidden="true" /><span><b>1 h 30 min short</b> before Fri 08:00</span><button type="button" onClick={() => setResolved(true)}>See options →</button></p>}
          <div className="wp-week">
            {week.map(({ day, load, items, over }) => {
              const isOver = over && !resolved;
              const shown = over && resolved ? items.filter(i => i !== "Gym") : items;
              return <div key={day} className={`wp-day ${isOver ? "is-over" : ""}`}>
                <div className="wp-day-head"><b>{day}</b><span>{Math.round((over && resolved ? 0.85 : load) * 100)}%</span></div>
                <span className="wp-meter"><span style={{ width: `${Math.min(1, over && resolved ? 0.85 : load) * 100}%` }} /></span>
                <ul>{shown.map(item => <li key={item} className={item === "Standup" ? "is-event" : ""}>{item}</li>)}</ul>
              </div>;
            })}
          </div>
        </> : <>
          <div className="wp-view-head"><div><p className="wp-eyebrow">Chat</p><h3>Say it the way you&rsquo;d say it to a friend.</h3></div></div>
          <div className="wp-prompts">{prompts.map((p, index) => <button type="button" key={p.ask} className={asked === index ? "is-active" : ""} aria-pressed={asked === index} onClick={() => setAsked(index)}>{p.ask}</button>)}</div>
          {asked === null ? <p className="wp-chat-empty">Pick a message above to see how LifeOS replies.</p> : <div className="wp-chat" role="status" key={asked}>
            <p className="wp-bubble is-you">{prompts[asked].ask}</p>
            <div className="wp-bubble is-app"><span className="wp-chat-from">LifeOS · scripted example</span>{prompts[asked].reply}
              {prompts[asked].card ? <span className="wp-action"><CheckCircle2 size={14} aria-hidden="true" /><span><b>{prompts[asked].card!.title}</b><small>{prompts[asked].card!.meta}</small></span></span> : null}
            </div>
          </div>}
        </>}
      </div>
    </div>
  </div>;
}
