"use client";

import Link from "next/link";
import { CalendarPlus, CheckCircle2, Clock3, ListChecks, ShieldAlert, ShieldCheck, Target, Volume2, VolumeX } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { ConflictSheet } from "@/components/today/conflict-sheet";
import { Notifications } from "@/components/today/notifications";
import { Nudges } from "@/components/today/nudges";
import { WeekView } from "@/components/today/week-view";
import { useVoiceOutput } from "@/hooks/use-voice-output";
import { briefPath, type Brief } from "@/lib/brief";
import { readLanguageSetting, speechLocale } from "@/lib/language";
import { useDisplayName } from "@/hooks/use-display-name";
import { readableError } from "@/lib/api";
import { formatClock, formatDeadline, formatHours } from "@/lib/task-utils";
import type { Conflict, Today } from "@/lib/types";
import { Orbit } from "@/components/ui/orbit";

type Item = { id: string; kind: "event" | "block"; title: string; start_at: string; end_at: string; status?: string; location?: string | null };

export default function TodayPage() {
  const { api, preferences, completeTask } = useWorkspace();
  const name = useDisplayName();
  const [today, setToday] = useState<Today>();
  const [error, setError] = useState("");
  const [planning, setPlanning] = useState(false);
  const [planNote, setPlanNote] = useState("");
  const [conflict, setConflict] = useState<Conflict>();
  const [completing, setCompleting] = useState("");
  const [brief, setBrief] = useState<Brief>();
  const [voiceError, setVoiceError] = useState("");
  const voice = useVoiceOutput(setVoiceError);
  const [view, setView] = useState<"day" | "week">("day");
  const [clock, setClock] = useState(() => Date.now());
  useEffect(() => { const timer = window.setInterval(() => setClock(Date.now()), 60_000); return () => window.clearInterval(timer); }, []);

  const latestLoad = useRef(0);
  const load = useCallback(async () => {
    // Only the newest request may update the page, so a slow earlier load cannot overwrite fresher data.
    const request = ++latestLoad.current;
    const setting = readLanguageSetting();
    // The brief is extra: if it fails, Today still loads with its plain summary.
    const briefing = api<Brief>(briefPath(setting === "auto" ? null : setting, name.first)).then(data => { if (request === latestLoad.current) setBrief(data); }, () => undefined);
    try { const data = await api<Today>("/api/today"); if (request === latestLoad.current) { setToday(data); setError(""); } }
    catch (e) { if (request === latestLoad.current) setError(readableError(e, "Could not load today.")); }
    await briefing;
  }, [api, name.first]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    // Quick add, notification actions and the Week view announce changes; keep Today current (PRD 6, F3.5).
    const refresh = () => { load(); };
    window.addEventListener("lifeos:changed", refresh);
    const poll = window.setInterval(() => { if (document.visibilityState === "visible") load(); }, 60_000);
    return () => { window.removeEventListener("lifeos:changed", refresh); window.clearInterval(poll); };
  }, [load]);
  // Deep links: /today?replan=1 runs the planner once; /conflict/:id lands here with ?conflict=<id>.
  const linked = useRef(false);
  useEffect(() => {
    if (linked.current || !today) return;
    linked.current = true;
    const params = new URLSearchParams(window.location.search);
    const conflictId = params.get("conflict");
    if (conflictId) { const match = today.conflicts.find(c => c.id === conflictId); if (match) setConflict(match); }
    if (params.get("view") === "week") setView("week");
    if (params.get("replan") === "1") void plan();
    if (params.toString()) window.history.replaceState(null, "", "/today");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [today]);

  async function plan() {
    setPlanning(true); setPlanNote("");
    try {
      const result = await api<{ blocks: unknown[]; unplaced_task_ids: string[]; conflicts: unknown[] }>("/api/plan/rebuild?days=7", { method: "POST" });
      setPlanNote(`Planned ${result.blocks.length} block${result.blocks.length === 1 ? "" : "s"} over the next 7 days${result.unplaced_task_ids.length ? `; ${result.unplaced_task_ids.length} task(s) did not fit` : ""}.`);
      await load();
    } catch (e) { setPlanNote(readableError(e, "Could not plan your days.")); }
    finally { setPlanning(false); }
  }

  async function complete(id: string) {
    if (completing) return;
    setCompleting(id);
    try { await completeTask(id); await load(); } catch (e) { setError(readableError(e, "Could not complete the task.")); }
    finally { setCompleting(""); }
  }

  const tz = today?.timezone ?? preferences.timezone;
  const items: Item[] = today ? [
    ...today.events.map(e => ({ id: e.id, kind: "event" as const, title: e.title, start_at: e.start_at, end_at: e.end_at, location: e.location })),
    ...today.plan_blocks.map(b => ({ id: b.id, kind: "block" as const, title: b.title ?? "Task", start_at: b.start_at, end_at: b.end_at, status: b.status })),
  ].sort((a, b) => Date.parse(a.start_at) - Date.parse(b.start_at)) : [];
  const due = today?.due_tasks ?? [];
  const planned = today?.plan_blocks.filter(b => b.status === "planned").length ?? 0;
  const nowBlock = today?.plan_blocks.find(b => b.status === "planned" && Date.parse(b.start_at) <= clock && Date.parse(b.end_at) > clock);
  const nextBlock = today?.plan_blocks.find(b => b.status === "planned" && Date.parse(b.start_at) > clock);
  const nextEvent = today?.events.find(e => Date.parse(e.start_at) > clock);
  const upcoming = nextEvent && (!nextBlock || Date.parse(nextEvent.start_at) < Date.parse(nextBlock.start_at)) ? { title: nextEvent.title, start_at: nextEvent.start_at, event: true } : nextBlock ? { title: nextBlock.title ?? "Task", start_at: nextBlock.start_at, event: false } : null;
  const summary = today ? `${due.length ? `${due.length} task${due.length === 1 ? "" : "s"} due` : "Nothing due"} today. You have ${formatHours(today.free_min_left)} of open time left.` : "";
  const overdue = due.filter(t => t.overdue).length;
  const doneBlocks = today?.plan_blocks.filter(b => b.status === "done").length ?? 0;
  const totalBlocks = today?.plan_blocks.length ?? 0;
  const atRisk = today?.conflicts.length ?? 0;
  // Share of the working day that is still open, for the "Open time" meter.
  const workMin = Math.max(1, minutesOf(preferences.workEnd) - minutesOf(preferences.workStart));
  const openShare = today ? Math.min(1, Math.max(0, today.free_min_left / workMin)) : 0;
  const nowProgress = nowBlock ? Math.min(1, Math.max(0, (clock - Date.parse(nowBlock.start_at)) / (Date.parse(nowBlock.end_at) - Date.parse(nowBlock.start_at)))) : 0;
  // Where the "now" marker sits in today's timeline: before the first item that has not started yet.
  const nowIndex = items.findIndex(item => Date.parse(item.start_at) > clock);
  const markerAt = nowIndex === -1 ? items.length : nowIndex;
  const dateLabel = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: tz }).format(clock);

  const viewToggle = <div className="segmented" role="group" aria-label="Schedule view">
    <button type="button" className={view === "day" ? "selected" : ""} aria-pressed={view === "day"} onClick={() => setView("day")}>Day</button>
    <button type="button" className={view === "week" ? "selected" : ""} aria-pressed={view === "week"} onClick={() => setView("week")}>Week</button>
  </div>;

  return <>
    {today?.conflicts.length ? <div className="conflict-banner" role="alert">{today.conflicts.map(c => <button key={c.id} onClick={() => setConflict(c)}><span><b>{formatHours(c.shortfall_min)} short</b> before {formatDeadline(c.deadline_at, tz)}. Needs {formatHours(c.needed_min)}, {formatHours(c.free_min)} free.</span><span className="banner-cta">See options →</span></button>)}</div> : null}
    <section className="hero panel pale today-hero" aria-labelledby="briefing-title"><div className="hero-copy"><p className="eyebrow blue">{dateLabel}</p><h1 id="briefing-title">Hello, {name.first}.</h1>
      {brief ? <div className="brief" lang={brief.language}><p className="brief-headline">{brief.headline}</p>{brief.lines.length ? <ul className="brief-lines">{brief.lines.map(line => <li key={line}>{line}</li>)}</ul> : null}</div>
        : <p>{today ? summary : error ? "Your day could not be loaded." : "Loading your day…"}{today?.next ? <><br />Next up: {today.next.title ?? "Task"} at {formatClock(today.next.start_at, tz)}.</> : null}</p>}
      <div className="button-row"><button className="button" onClick={plan} disabled={planning}>{planning ? "Planning…" : planned ? "Replan" : "Plan my day"} <span aria-hidden="true">→</span></button><Link href="/chat" className="button secondary">Talk to LifeOS</Link>
        {brief ? <button type="button" className="text-button" onClick={() => { setVoiceError(""); if (voice.loading || voice.playing || voice.url) voice.stop(); else void voice.read(brief.spoken, speechLocale(brief.language)); }}>{voice.playing ? <VolumeX size={16} aria-hidden="true" /> : <Volume2 size={16} aria-hidden="true" />} {voice.loading ? "Preparing audio… (click to cancel)" : voice.playing ? "Stop" : "Read my brief"}</button> : null}</div>
      {voiceError ? <small className="error-message" role="alert">{voiceError}</small> : null}
      {planNote ? <small role="status">{planNote}</small> : <small>Plans the next 7 days around your events, routines and working hours.</small>}</div><Orbit /></section>
    {error ? <div className="error-message with-action" role="alert"><span>{error}</span><button className="text-button" onClick={load}>Try again</button></div> : null}
    {today ? <section className="stat-row" aria-label="Today in numbers">
      <div className="stat"><span className="stat-label"><Clock3 size={15} aria-hidden="true" /> Open time left</span><span className="stat-value">{formatHours(today.free_min_left)}</span><div className="meter" role="meter" aria-label="Share of your working day still open" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(openShare * 100)}><span style={{ width: `${openShare * 100}%` }} /></div><span className="stat-note">of your {preferences.workStart}–{preferences.workEnd} working day</span></div>
      <div className="stat"><span className="stat-label"><Target size={15} aria-hidden="true" /> Focus blocks done</span><span className="stat-value">{doneBlocks}<span> of {totalBlocks}</span></span><div className="meter" role="meter" aria-label="Focus blocks done" aria-valuemin={0} aria-valuemax={totalBlocks || 1} aria-valuenow={doneBlocks}><span style={{ width: `${totalBlocks ? (doneBlocks / totalBlocks) * 100 : 0}%` }} /></div><span className="stat-note">{totalBlocks ? `${planned} still to do` : "None planned yet"}</span></div>
      <a href="#due-today" className={`stat stat-link ${overdue ? "warn" : ""}`}><span className="stat-label"><ListChecks size={15} aria-hidden="true" /> Due today</span><span className="stat-value">{due.length}</span><span className="stat-note">{overdue ? `${overdue} overdue` : due.length ? "None overdue" : "You're all clear"}</span></a>
      {atRisk ? <button type="button" className="stat stat-link risk" onClick={() => setConflict(today.conflicts[0])}><span className="stat-label"><ShieldAlert size={15} aria-hidden="true" /> Capacity guard</span><span className="stat-value">{atRisk} at risk</span><span className="stat-note">See your options <span aria-hidden="true">→</span></span></button>
        : <div className="stat ok"><span className="stat-label"><ShieldCheck size={15} aria-hidden="true" /> Capacity guard</span><span className="stat-value">All fit</span><span className="stat-note">Every deadline fits your week</span></div>}
    </section> : !error ? <section className="stat-row" aria-busy="true" aria-label="Loading today in numbers">{[0, 1, 2, 3].map(i => <div key={i} className="stat"><span className="skeleton" style={{ width: "55%" }} /><span className="skeleton tall" style={{ width: "40%" }} /><span className="skeleton" style={{ width: "75%" }} /></div>)}</section> : null}
    {brief ? <Nudges brief={brief} onChanged={load} onOpenConflict={id => { const match = today?.conflicts.find(c => c.id === id); if (match) setConflict(match); }} /> : null}
    {view === "week" && today ? <section className="panel week-panel"><div className="section-heading"><div><h2>Your week</h2><p>Planned vs free working time per day, in {tz}. Red means the day cannot hold what is due.</p></div>{viewToggle}</div><WeekView start={String(today.date)} timezone={tz} onChanged={load} /></section> : null}
    <div className="two-columns today-columns" hidden={view === "week"}><div className="main-stack">
      <section className="panel agenda"><div className="section-heading"><div><h2>Your schedule</h2><p>Events and focus blocks for today, in {tz}.</p></div>{viewToggle}</div>
      {!today && !error ? <div className="timeline-skeleton" role="status" aria-label="Loading your schedule">{[0, 1, 2].map(i => <div key={i}><span className="skeleton" /><span className="skeleton block" /></div>)}</div> : items.length ? <ol className="timeline">{items.flatMap((item, index) => {
        const past = Date.parse(item.end_at) <= clock;
        const live = !past && Date.parse(item.start_at) <= clock;
        const row = <li key={`${item.kind}-${item.id}`} className={`timeline-item ${item.kind} ${today?.next?.id === item.id ? "next" : ""} ${live ? "live" : ""} ${past ? "past" : ""} ${item.status && item.status !== "planned" ? item.status : ""}`}>
          <span className="timeline-time">{formatClock(item.start_at, tz)}<small>{formatClock(item.end_at, tz)}</small></span>
          <span className="timeline-dot" aria-hidden="true" />
          <div className="timeline-body"><p className="task-title">{item.title}</p><p className="task-meta"><span className={`kind-chip ${item.kind}`}>{item.kind === "event" ? "Event" : "Focus"}</span>{item.kind === "event" ? item.location ?? null : live ? "In progress" : today?.next?.id === item.id ? "Up next" : item.status === "planned" ? null : item.status}</p></div>
        </li>;
        return index === markerAt ? [<li key="now" className="timeline-now" aria-label={`Now, ${formatClock(new Date(clock).toISOString(), tz)}`}><span>Now · {formatClock(new Date(clock).toISOString(), tz)}</span></li>, row] : [row];
      }).concat(markerAt === items.length ? [<li key="now" className="timeline-now" aria-label={`Now, ${formatClock(new Date(clock).toISOString(), tz)}`}><span>Now · {formatClock(new Date(clock).toISOString(), tz)}</span></li>] : [])}</ol> : today ? <div className="empty-state"><CalendarPlus size={32} aria-hidden="true" /><h3>Nothing scheduled yet.</h3><p>Plan your day to turn your tasks into focus blocks.</p><button className="button secondary" onClick={plan} disabled={planning}>Plan my day</button></div> : null}
      </section>
      <section className="panel" id="due-today" aria-labelledby="due-title"><div className="section-heading"><div><h2 id="due-title">Due today</h2><p>Including anything overdue.</p></div><Link href="/tasks" className="text-button">All tasks <span aria-hidden="true">→</span></Link></div>
      {today ? due.length ? <div className="task-list">{due.map(task => <article key={task.id} className={`task-card ${task.overdue ? "task-overdue" : ""}`}><div className="task-title-row"><button className="task-check" aria-label={`Complete ${task.title}`} disabled={!!completing} onClick={() => complete(task.id)} /><h3 className="task-title">{task.title}</h3></div>
        <p className="task-meta">{task.overdue ? <span className="status-label overdue">Overdue</span> : null}{formatDeadline(task.deadline_at, tz)}{task.status === "blocked" ? <span className="status-label">Blocked</span> : null}<span className={`priority priority-${task.priority_band.toLowerCase()}`}>{task.priority_band}</span></p>
        {task.why ? <p className="task-why">{task.why}</p> : null}</article>)}</div> : <div className="empty-inline"><CheckCircle2 size={18} aria-hidden="true" /> Nothing due today. Enjoy the room to breathe.</div> : null}
      </section>
    </div><div className="side-stack">
      <section className="panel dark now-card" aria-label="Now and next">
        <div><p className="eyebrow accent">Now</p><h2>{nowBlock ? nowBlock.title ?? "Focus block" : "Free time"}</h2><p className="now-sub">{nowBlock ? `Until ${formatClock(nowBlock.end_at, tz)}` : today ? `${formatHours(today.free_min_left ?? 0)} of open time left today` : "…"}</p>
          {nowBlock ? <div className="meter light" aria-hidden="true"><span style={{ width: `${nowProgress * 100}%` }} /></div> : null}</div>
        <div className="now-next-divider" />
        <div><p className="eyebrow accent">Next{upcoming ? ` · ${untilLabel(Date.parse(upcoming.start_at) - clock)}` : ""}</p><h3>{upcoming ? upcoming.title : "Nothing else planned"}</h3><p className="now-sub">{upcoming ? `${upcoming.event ? "Event" : "Focus block"} at ${formatClock(upcoming.start_at, tz)}` : "Plan your day to fill open time."}</p></div>
      </section>
      <section className="panel focus-card"><p className="eyebrow muted">Your focus window</p><h2>{preferences.focusStart}–{preferences.focusEnd}</h2><p>LifeOS plans demanding work inside your working hours, {preferences.workStart}–{preferences.workEnd}.</p><Link className="text-button" href="/profile">Change in Profile <span aria-hidden="true">→</span></Link></section>
      <Notifications onChanged={load} />
    </div></div>
    {voice.url ? <audio ref={voice.element} src={voice.url} autoPlay onPlay={() => voice.setPlaying(true)} onEnded={voice.stop} onError={() => { voice.stop(); setVoiceError("Could not play the brief."); }} /> : null}
    {conflict ? <ConflictSheet key={conflict.id} conflict={conflict} onClose={() => setConflict(undefined)} onChanged={load} /> : null}
  </>;
}

function minutesOf(hhmm: string) {
  const [h, m] = hhmm.split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

function untilLabel(ms: number) {
  const min = Math.max(0, Math.round(ms / 60_000));
  if (min < 1) return "now";
  if (min < 60) return `in ${min} min`;
  const h = Math.floor(min / 60), m = min % 60;
  return `in ${h} h${m ? ` ${m} min` : ""}`;
}
