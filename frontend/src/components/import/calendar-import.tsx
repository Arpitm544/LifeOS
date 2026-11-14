"use client";

import Link from "next/link";
import { FileUp } from "lucide-react";
import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";
import { calendarNotes, calendarSaveSummary, ICS_UNDO_SECONDS, icsFileError, selectedEvents, toCalendarRows, type CalendarParseResult, type CalendarRow, type CalendarSaveResult } from "@/lib/ics";

type Stage = { name: "input" } | { name: "review"; result: CalendarParseResult } | { name: "saved"; result: CalendarSaveResult; savedAt: number };

function when(row: CalendarRow, timezone: string) {
  const options: Intl.DateTimeFormatOptions = row.all_day ? { weekday: "short", month: "short", day: "numeric", timeZone: timezone } : { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: timezone };
  return new Date(row.start_at).toLocaleString(undefined, options) + (row.all_day ? " · all day" : "") + (row.rrule ? " · repeats" : "");
}

export function CalendarImport() {
  const { api, preferences, reloadTasks } = useWorkspace();
  const [stage, setStage] = useState<Stage>({ name: "input" });
  const [file, setFile] = useState<{ name: string; text: string } | null>(null);
  const [rows, setRows] = useState<CalendarRow[]>([]);
  const [busy, setBusy] = useState<"" | "reading" | "saving" | "undoing">("");
  const [error, setError] = useState("");
  const [undoLeft, setUndoLeft] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (stage.name !== "saved") return;
    const tick = () => setUndoLeft(Math.max(0, ICS_UNDO_SECONDS - Math.floor((Date.now() - stage.savedAt) / 1000)));
    tick();
    const timer = window.setInterval(tick, 500);
    return () => window.clearInterval(timer);
  }, [stage]);

  async function choose(chosen: File | undefined) {
    setError("");
    if (!chosen) return;
    const problem = icsFileError(chosen);
    if (problem) { setError(problem); return; }
    try { setFile({ name: chosen.name, text: await chosen.text() }); }
    catch { setError("That file could not be opened. Try exporting it again."); }
  }

  async function parse() {
    if (!file) return;
    setError(""); setBusy("reading");
    try {
      const result = await api<CalendarParseResult>("/api/import/calendar/parse", { method: "POST", body: { text: file.text, client_tz: preferences.timezone } });
      setRows(toCalendarRows(result.proposals));
      setStage({ name: "review", result });
    } catch (e) { setError(readableError(e, "LifeOS could not read that calendar.")); }
    finally { setBusy(""); }
  }

  async function save() {
    const chosen = selectedEvents(rows);
    if ("error" in chosen) { setError(chosen.error); return; }
    setError(""); setBusy("saving");
    try {
      const result = await api<CalendarSaveResult>("/api/import/calendar/save", { method: "POST", body: { events: chosen.events } });
      setStage({ name: "saved", result, savedAt: Date.now() });
      await reloadTasks().catch(() => undefined);
    } catch (e) { setError(readableError(e, "Could not add these events.")); }
    finally { setBusy(""); }
  }

  async function undo(result: CalendarSaveResult) {
    setError(""); setBusy("undoing");
    try {
      await api(`/api/import/calendar/${encodeURIComponent(result.batch_id)}/undo`, { method: "POST" });
      await reloadTasks().catch(() => undefined);
      reset();
    } catch (e) { setError(readableError(e, "Could not undo the import.")); }
    finally { setBusy(""); }
  }

  function update(id: string, change: Partial<CalendarRow>) { setRows(current => current.map(row => row.id === id ? { ...row, ...change } : row)); }
  function reset() { setStage({ name: "input" }); setRows([]); setFile(null); setError(""); }

  const errorBox = error ? <p className="error-message" role="alert">{error}</p> : null;

  if (stage.name === "saved") {
    const { result } = stage;
    return <section className="panel import-panel" aria-live="polite">
      <p className="eyebrow blue">Done</p>
      <h2>Your calendar is in.</h2>
      <p className="success-message" role="status">{calendarSaveSummary(result)}</p>
      {errorBox}
      <div className="button-row">
        <Link className="button" href="/today">See today’s plan <span aria-hidden="true">→</span></Link>
        {undoLeft > 0 && result.created > 0 ? <button className="text-button" onClick={() => undo(result)} disabled={!!busy}>{busy === "undoing" ? "Undoing…" : `Undo import (${undoLeft}s)`}</button> : null}
        <button className="text-button" onClick={reset} disabled={!!busy}>Import another</button>
      </div>
    </section>;
  }

  if (stage.name === "review") {
    const { result } = stage;
    const count = rows.filter(row => row.selected).length;
    return <section className="panel import-panel" aria-label="Review events from your calendar">
      <div className="import-head"><div><p className="eyebrow blue">Your calendar</p><h2>{rows.length ? `Found ${rows.length} event${rows.length === 1 ? "" : "s"}.` : "Nothing to add."}</h2><p className="muted">Nothing is saved yet. Untick anything you don’t want LifeOS to plan around.</p></div></div>
      {calendarNotes(result).map(note => <p key={note} className="muted import-note">{note}</p>)}
      {rows.length ? <ul className="import-list">{rows.map(row => <li key={row.id} className={row.selected ? "" : "unselected"}>
        <input type="checkbox" checked={row.selected} onChange={e => update(row.id, { selected: e.target.checked })} aria-label={`Add ${row.title || "this event"}`} />
        <div className="import-fields">
          <input className="import-title" value={row.title} maxLength={120} onChange={e => update(row.id, { title: e.target.value })} aria-label="Event title" />
          <small className="muted">{when(row, result.timezone)}{row.location ? ` · ${row.location}` : ""}</small>
        </div>
      </li>)}</ul> : <p className="muted">No upcoming events were found in that file.</p>}
      {errorBox}
      <div className="import-actions"><div className="button-row">
        <button className="text-button" onClick={reset} disabled={!!busy}>Start over</button>
        {rows.length ? <button className="button" onClick={save} disabled={!!busy || !count}>{busy === "saving" ? "Adding…" : `Add ${count} event${count === 1 ? "" : "s"}`} <span aria-hidden="true">→</span></button> : null}
      </div></div>
    </section>;
  }

  return <section className="panel import-panel">
    <h2>Drop in a calendar file.</h2>
    <p className="muted">Export from Google Calendar (Settings → Import &amp; export), Apple Calendar or Outlook, then upload the .ics file. Events you import again are never duplicated. Your file is read once and only the events you approve are saved.</p>
    <div className={`drop-zone${file ? " has-file" : ""}`} onDragOver={(e: DragEvent) => e.preventDefault()} onDrop={(e: DragEvent) => { e.preventDefault(); void choose(e.dataTransfer.files[0]); }}>
      <FileUp size={22} aria-hidden="true" />
      {file ? <p><b>{file.name}</b> is ready. <button className="text-button" onClick={() => setFile(null)}>Remove</button></p> : <p>Drag an .ics file here, or <button className="text-button" onClick={() => fileInput.current?.click()}>choose a file</button>.</p>}
      <input ref={fileInput} type="file" accept=".ics,text/calendar" hidden onChange={(e: ChangeEvent<HTMLInputElement>) => { void choose(e.target.files?.[0]); e.target.value = ""; }} />
    </div>
    {errorBox}
    <div className="button-row"><button className="button" onClick={parse} disabled={!file || !!busy}>{busy === "reading" ? "Reading your calendar…" : "Find my events"} <span aria-hidden="true">→</span></button></div>
  </section>;
}
