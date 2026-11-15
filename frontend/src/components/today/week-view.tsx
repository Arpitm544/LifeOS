"use client";

import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";
import { formatClock, formatHours } from "@/lib/task-utils";
import { addDays, dayLoad, shiftToDay } from "@/lib/week";
import type { PlanBlock, Today } from "@/lib/types";

/** Week view (PRD 6): 7 day columns with events and blocks, a load bar per day, and drag to move a block. */
export function WeekView({ start, timezone, onChanged }: { start: string; timezone: string; onChanged: () => void }) {
  const { api, notify } = useWorkspace();
  const [days, setDays] = useState<Today[]>();
  const [error, setError] = useState("");
  const [moving, setMoving] = useState("");
  const [over, setOver] = useState("");
  const dragged = useRef<PlanBlock | null>(null);
  const latest = useRef(0);

  const load = useCallback(async () => {
    const request = ++latest.current;
    try {
      const rows = await Promise.all(Array.from({ length: 7 }, (_, i) => api<Today>(`/api/today?day=${addDays(start, i)}`)));
      if (request === latest.current) { setDays(rows); setError(""); }
    } catch (e) { if (request === latest.current) setError(readableError(e, "Could not load your week.")); }
  }, [api, start]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const refresh = () => { load(); };
    window.addEventListener("lifeos:changed", refresh);
    return () => window.removeEventListener("lifeos:changed", refresh);
  }, [load]);

  async function move(block: PlanBlock, from: string, to: string) {
    if (from === to || moving) return;
    setMoving(block.id); setError("");
    try {
      await api(`/api/plan-blocks/${block.id}`, { method: "PATCH", body: shiftToDay(block, from, to) });
      notify(`Moved “${block.title ?? "block"}” to ${new Date(`${to}T12:00:00Z`).toLocaleDateString("en-IN", { weekday: "long", timeZone: "UTC" })}.`);
      await load(); onChanged();
    } catch (e) { setError(readableError(e, "Could not move that block.")); }
    finally { setMoving(""); }
  }

  function drop(event: DragEvent, to: string) {
    event.preventDefault(); setOver("");
    const block = dragged.current; dragged.current = null;
    const from = event.dataTransfer.getData("text/x-lifeos-day");
    if (block && from) void move(block, from, to);
  }

  if (error && !days) return <div className="error-message with-action" role="alert"><span>{error}</span><button className="text-button" onClick={load}>Try again</button></div>;
  if (!days) return <p className="muted" role="status">Loading your week…</p>;
  return <>
    {error ? <p className="error-message" role="alert">{error}</p> : null}
    <p className="muted week-hint">Drag a focus block to another day, or use the arrows. LifeOS keeps the same time and refuses overlaps.</p>
    <div className="week-grid" role="list" aria-label="Next 7 days">{days.map((day, index) => {
      const key = String(day.date);
      const usage = dayLoad(day, timezone);
      const label = new Date(`${key}T12:00:00Z`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
      const items = [...day.events.map(e => ({ kind: "event" as const, id: e.id, title: e.title, start_at: e.start_at, end_at: e.end_at })),
        ...day.plan_blocks.map(b => ({ kind: "block" as const, ...b, title: b.title ?? "Task" }))].sort((a, b) => Date.parse(a.start_at) - Date.parse(b.start_at));
      return <section key={key} role="listitem" aria-label={label} className={`week-day ${over === key ? "drop-target" : ""}`}
        onDragOver={event => { if (dragged.current) { event.preventDefault(); setOver(key); } }} onDragLeave={() => setOver(current => current === key ? "" : current)} onDrop={event => drop(event, key)}>
        <header><b>{label}</b>{usage.atRisk ? <span className="status-label overdue">At risk</span> : null}</header>
        <div className={`load-bar ${usage.ratio > 1 ? "over" : ""}`} role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(usage.ratio * 100)} aria-label={`${label}: ${formatHours(usage.plannedMin)} planned of ${formatHours(usage.capacityMin)} working time`}>
          <span style={{ width: `${Math.min(100, Math.round(usage.ratio * 100))}%` }} /></div>
        <small className="muted">{formatHours(usage.plannedMin)} planned · {formatHours(usage.freeMin)} free</small>
        <ol className="week-items">{items.length ? items.map(item => item.kind === "event"
          ? <li key={`e-${item.id}`} className="week-item event"><span aria-hidden="true">🔒</span> {formatClock(item.start_at, timezone)} {item.title}</li>
          : <li key={`b-${item.id}`} className={`week-item block ${item.status !== "planned" ? item.status : ""} ${moving === item.id ? "moving" : ""}`}
            draggable={item.status === "planned" && !moving} onDragStart={event => { dragged.current = item as PlanBlock; event.dataTransfer.setData("text/x-lifeos-day", key); event.dataTransfer.effectAllowed = "move"; }}
            onDragEnd={() => { dragged.current = null; setOver(""); }}>
            <span>{formatClock(item.start_at, timezone)}–{formatClock(item.end_at, timezone)} {item.title}</span>
            {item.status === "planned" ? <span className="week-move">
              <button type="button" className="text-button" disabled={index === 0 || !!moving} aria-label={`Move ${item.title} one day earlier`} onClick={() => move(item as PlanBlock, key, addDays(key, -1))}>‹</button>
              <button type="button" className="text-button" disabled={index === days.length - 1 || !!moving} aria-label={`Move ${item.title} one day later`} onClick={() => move(item as PlanBlock, key, addDays(key, 1))}>›</button>
            </span> : null}
          </li>) : <li className="muted">Free</li>}</ol>
      </section>;
    })}</div>
  </>;
}
