"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { PageHeading } from "@/components/layout/page-heading";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { ConflictSheet } from "@/components/today/conflict-sheet";
import { Notifications } from "@/components/today/notifications";
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

  const latestLoad = useRef(0);
  const load = useCallback(async () => {
    // Only the newest request may update the page, so a slow earlier load cannot overwrite fresher data.
    const request = ++latestLoad.current;
    try { const data = await api<Today>("/api/today"); if (request === latestLoad.current) { setToday(data); setError(""); } }
    catch (e) { if (request === latestLoad.current) setError(readableError(e, "Could not load today.")); }
  }, [api]);
  useEffect(() => { load(); }, [load]);

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
  const summary = today ? `${due.length ? `${due.length} task${due.length === 1 ? "" : "s"} due` : "Nothing due"} today. You have ${formatHours(today.free_min_left)} of open time left.` : "";

  return <>
    <PageHeading eyebrow="Today · Your workspace" title="Your day at a glance." description="Your tasks, schedule and available time in one place." />
    {today?.conflicts.length ? <div className="conflict-banner" role="alert">{today.conflicts.map(c => <button key={c.id} onClick={() => setConflict(c)}><span><b>{formatHours(c.shortfall_min)} short</b> before {formatDeadline(c.deadline_at, tz)}. Needs {formatHours(c.needed_min)}, {formatHours(c.free_min)} free.</span><span className="banner-cta">See options →</span></button>)}</div> : null}
    <section className="hero panel pale" aria-labelledby="briefing-title"><div className="hero-copy"><p className="eyebrow blue">Your day, in orbit</p><h2 id="briefing-title">Hello, {name.first}.</h2>
      <p>{today ? summary : error ? "Your day could not be loaded." : "Loading your day…"}{today?.next ? <><br />Next up: {today.next.title ?? "Task"} at {formatClock(today.next.start_at, tz)}.</> : null}</p>
      <div className="button-row"><button className="button" onClick={plan} disabled={planning}>{planning ? "Planning…" : planned ? "Replan" : "Plan my day"} <span aria-hidden="true">→</span></button><Link href="/chat" className="button secondary">Talk to LifeOS</Link></div>
      {planNote ? <small role="status">{planNote}</small> : <small>Plans the next 7 days around your events, routines and working hours.</small>}</div><Orbit /></section>
    {error ? <div className="error-message with-action" role="alert"><span>{error}</span><button className="text-button" onClick={load}>Try again</button></div> : null}
    <div className="two-columns today-columns"><section className="panel agenda"><div className="section-heading"><div><h2>Your schedule</h2><p>Events and focus blocks for today, in {tz}.</p></div><Link href="/tasks" className="text-button">All tasks <span aria-hidden="true">→</span></Link></div>
      {!today && !error ? <p className="muted" role="status">Loading…</p> : items.length ? <ol className="timeline">{items.map(item => <li key={`${item.kind}-${item.id}`} className={`timeline-item ${item.kind} ${today?.next?.id === item.id ? "next" : ""} ${item.status && item.status !== "planned" ? item.status : ""}`}>
        <span className="timeline-time">{formatClock(item.start_at, tz)}<small>{formatClock(item.end_at, tz)}</small></span>
        <div><p className="task-title">{item.title}</p><p className="task-meta">{item.kind === "event" ? `Event${item.location ? ` · ${item.location}` : ""}` : today?.next?.id === item.id ? "Next focus block" : item.status === "planned" ? "Focus block" : item.status}</p></div>
      </li>)}</ol> : today ? <div className="empty-state"><h3>Nothing scheduled yet.</h3><p>Plan your day to turn your tasks into focus blocks.</p><button className="button secondary" onClick={plan} disabled={planning}>Plan my day</button></div> : null}
      <div className="section-heading due-heading"><div><h2>Due today</h2><p>Including anything overdue.</p></div></div>
      {today ? due.length ? <div className="task-list">{due.map(task => <article key={task.id} className="task-card"><div className="task-title-row"><button className="task-check" aria-label={`Complete ${task.title}`} disabled={!!completing} onClick={() => complete(task.id)} /><h3 className="task-title">{task.title}</h3></div>
        <p className="task-meta">{task.overdue ? <span className="status-label overdue">Overdue</span> : null}{formatDeadline(task.deadline_at, tz)}{task.status === "blocked" ? <span className="status-label">Blocked</span> : null}<span className={`priority priority-${task.priority_band.toLowerCase()}`}>{task.priority_band}</span></p>
        {task.why ? <p className="task-why">{task.why}</p> : null}</article>)}</div> : <p className="muted">Nothing due today.</p> : null}
    </section><div className="side-stack">
      <section className="panel dark capacity"><p className="eyebrow accent">Capacity guard</p><h2>{today ? today.conflicts.length ? `${today.conflicts.length} deadline${today.conflicts.length === 1 ? "" : "s"} at risk.` : "Your deadlines fit." : "Checking your week…"}</h2>
        {today ? <><p>{formatHours(today.free_min_left)} free today <span>/</span> {planned} block{planned === 1 ? "" : "s"} planned</p><small>Checked after every change to your tasks or plan.</small></> : null}</section>
      <section className="panel focus-card"><p className="eyebrow muted">Your focus window</p><h2>{preferences.focusStart}–{preferences.focusEnd}</h2><p>LifeOS plans demanding work inside your working hours, {preferences.workStart}–{preferences.workEnd}.</p><Link className="text-button" href="/profile">Change in Profile <span aria-hidden="true">→</span></Link></section>
      <Notifications onChanged={load} />
    </div></div>
    {conflict ? <ConflictSheet key={conflict.id} conflict={conflict} onClose={() => setConflict(undefined)} onChanged={load} /> : null}
  </>;
}
