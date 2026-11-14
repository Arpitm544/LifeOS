"use client";

import Link from "next/link";
import { Camera, FileUp } from "lucide-react";
import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";
import { bytesToBase64, extractNotes, MAX_TEXT_CHARS, saveSummary, selectedTasks, toReviewRows, UNDO_SECONDS, uploadKind, type ExtractResult, type ReviewRow, type SaveResult } from "@/lib/syllabus";
import { formatDeadline } from "@/lib/task-utils";
import { preparePhoto } from "@/lib/photo";
import { categories, type Category } from "@/lib/types";

type Stage = { name: "input" } | { name: "review"; result: ExtractResult } | { name: "saved"; result: SaveResult; savedAt: number };

function localInput(value: string | null) {
  if (!value) return "";
  const d = new Date(value);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function SyllabusImport() {
  const { api, preferences, reloadTasks } = useWorkspace();
  const [stage, setStage] = useState<Stage>({ name: "input" });
  const [text, setText] = useState("");
  const [file, setFile] = useState<{ name: string; pdf?: string; image?: string; preview?: string } | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [rows, setRows] = useState<ReviewRow[]>([]);
  const [plan, setPlan] = useState(true);
  const [busy, setBusy] = useState<"" | "reading" | "saving" | "undoing">("");
  const [error, setError] = useState("");
  const [undoLeft, setUndoLeft] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const cameraInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (stage.name !== "saved") return;
    const tick = () => setUndoLeft(Math.max(0, UNDO_SECONDS - Math.floor((Date.now() - stage.savedAt) / 1000)));
    tick();
    const timer = window.setInterval(tick, 500);
    return () => window.clearInterval(timer);
  }, [stage]);

  async function choose(chosen: File | undefined) {
    setError("");
    if (!chosen) return;
    const kind = uploadKind(chosen);
    if ("error" in kind) { setError(kind.error); return; }
    if (kind.kind === "image") {
      setPreparing(true);
      try {
        const photo = await preparePhoto(chosen);
        setFile({ name: chosen.name || "Photo", image: photo.base64, preview: photo.dataUrl });
      } catch (e) { setError(readableError(e, "That photo could not be opened. Try again or paste the text.")); }
      finally { setPreparing(false); }
      return;
    }
    try {
      if (kind.kind === "pdf") setFile({ name: chosen.name, pdf: bytesToBase64(new Uint8Array(await chosen.arrayBuffer())) });
      else { setText((await chosen.text()).slice(0, MAX_TEXT_CHARS)); setFile(null); }
    } catch { setError("That file could not be opened. Try again or paste the text."); }
  }

  async function extract() {
    setError(""); setBusy("reading");
    try {
      const body = file?.image ? { image_base64: file.image, client_tz: preferences.timezone } : file?.pdf ? { pdf_base64: file.pdf, client_tz: preferences.timezone } : { text, client_tz: preferences.timezone };
      const result = await api<ExtractResult>("/api/import/syllabus/extract", { method: "POST", body });
      setRows(toReviewRows(result.proposals));
      setStage({ name: "review", result });
    } catch (e) { setError(readableError(e, "LifeOS could not read that syllabus.")); }
    finally { setBusy(""); }
  }

  async function save() {
    const chosen = selectedTasks(rows);
    if ("error" in chosen) { setError(chosen.error); return; }
    setError(""); setBusy("saving");
    try {
      const result = await api<SaveResult>("/api/import/syllabus/save", { method: "POST", body: { tasks: chosen.tasks, plan } });
      setStage({ name: "saved", result, savedAt: Date.now() });
      await reloadTasks().catch(() => undefined);
    } catch (e) { setError(readableError(e, "Could not add these tasks.")); }
    finally { setBusy(""); }
  }

  async function undo(result: SaveResult) {
    setError(""); setBusy("undoing");
    try {
      await api(`/api/import/syllabus/${encodeURIComponent(result.batch_id)}/undo`, { method: "POST" });
      await reloadTasks().catch(() => undefined);
      setStage({ name: "review", result: { course: "", proposals: [], skipped_past: 0, skipped_invalid: 0, capped: false, truncated: false, fallback: false, source_chars: 0, timezone: preferences.timezone } });
    } catch (e) { setError(readableError(e, "Could not undo the import.")); }
    finally { setBusy(""); }
  }

  function update(id: string, change: Partial<ReviewRow>) {
    setRows(current => current.map(row => row.id === id ? { ...row, ...change } : row));
  }

  function reset() { setStage({ name: "input" }); setRows([]); setText(""); setFile(null); setError(""); }

  const errorBox = error ? <p className="error-message" role="alert">{error}</p> : null;

  if (stage.name === "saved") {
    const { result } = stage;
    return <section className="panel import-panel" aria-live="polite">
      <p className="eyebrow blue">Done</p>
      <h2>Your term is on the map.</h2>
      <p className="success-message" role="status">{saveSummary(result)}</p>
      {errorBox}
      <div className="button-row">
        <Link className="button" href="/today">See today’s plan <span aria-hidden="true">→</span></Link>
        <Link className="button secondary" href="/tasks">View tasks</Link>
        {undoLeft > 0 ? <button className="text-button" onClick={() => undo(result)} disabled={!!busy}>{busy === "undoing" ? "Undoing…" : `Undo import (${undoLeft}s)`}</button> : null}
        <button className="text-button" onClick={reset} disabled={!!busy}>Import another</button>
      </div>
    </section>;
  }

  if (stage.name === "review") {
    const { result } = stage;
    const count = rows.filter(row => row.selected).length;
    return <section className="panel import-panel" aria-label="Review tasks from your syllabus">
      <div className="import-head"><div><p className="eyebrow blue">{result.course || (result.source === "photo" ? "Your photo" : "Your syllabus")}</p><h2>{rows.length ? `Found ${rows.length} thing${rows.length === 1 ? "" : "s"} to plan for.` : "Nothing to add."}</h2><p className="muted">Nothing is saved yet. Untick what you don’t need and fix anything that looks off.</p></div></div>
      {extractNotes(result).map(note => <p key={note} className="muted import-note">{note}</p>)}
      {rows.length ? <ul className="import-list">{rows.map(row => <li key={row.id} className={row.selected ? "" : "unselected"}>
        <input type="checkbox" checked={row.selected} onChange={e => update(row.id, { selected: e.target.checked })} aria-label={`Add ${row.title || "this task"}`} />
        <div className="import-fields">
          <input className="import-title" value={row.title} maxLength={120} onChange={e => update(row.id, { title: e.target.value })} aria-label="Task title" />
          <div className="import-meta">
            <span className="chip">{row.kind}</span>
            <label>Due<input type="datetime-local" value={localInput(row.deadline_at)} onChange={e => update(row.id, { deadline_at: e.target.value ? new Date(e.target.value).toISOString() : null })} /></label>
            <label>Effort (min)<input type="number" min={5} max={600} value={row.effort_est_min} onChange={e => update(row.id, { effort_est_min: Number(e.target.value) })} /></label>
            <label>Category<select value={row.category} onChange={e => update(row.id, { category: e.target.value as Category })}>{categories.map(c => <option key={c} value={c}>{c[0].toUpperCase() + c.slice(1)}</option>)}</select></label>
            <label>Importance<select value={row.importance} onChange={e => update(row.id, { importance: Number(e.target.value) })}>{[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}</option>)}</select></label>
          </div>
          {row.notes ? <small className="muted import-source">{row.notes}</small> : null}
          {row.deadline_at ? <small className="muted">{formatDeadline(row.deadline_at, preferences.timezone)}</small> : <small className="muted">No date found — it will be added without a deadline.</small>}
        </div>
      </li>)}</ul> : <p className="muted">{result.source === "photo" ? "No tasks could be read from that photo. Try a closer, well-lit photo, or paste the text." : "No dated deadlines were found. Try pasting the schedule section of the syllabus."}</p>}
      {errorBox}
      <div className="import-actions">
        <label className="import-plan"><input type="checkbox" checked={plan} onChange={e => setPlan(e.target.checked)} /> Plan focus time for these over the next two weeks</label>
        <div className="button-row">
          <button className="text-button" onClick={reset} disabled={!!busy}>Start over</button>
          {rows.length ? <button className="button" onClick={save} disabled={!!busy || !count}>{busy === "saving" ? "Adding…" : `Add ${count} task${count === 1 ? "" : "s"}${plan ? " and plan" : ""}`} <span aria-hidden="true">→</span></button> : null}
        </div>
      </div>
    </section>;
  }

  const ready = !preparing && (!!file?.pdf || !!file?.image || !!text.trim());
  const reading = file?.image ? "Reading your photo…" : "Reading your syllabus…";
  return <section className="panel import-panel">
    <h2>Drop in a syllabus, a list or a photo.</h2>
    <p className="muted">LifeOS finds the deadlines and to-dos in a syllabus, a PDF or a photo of a whiteboard or handwritten list, then plans time for them. You review everything before it’s saved.</p>
    <div className={`drop-zone${file ? " has-file" : ""}`} onDragOver={(e: DragEvent) => e.preventDefault()} onDrop={(e: DragEvent) => { e.preventDefault(); void choose(e.dataTransfer.files[0]); }}>
      {file?.preview ? <img className="photo-preview" src={file.preview} alt="The photo LifeOS will read" /> : <FileUp size={22} aria-hidden="true" />}
      {preparing ? <p role="status">Preparing your photo…</p> : file ? <p><b>{file.name}</b> is ready. <button className="text-button" onClick={() => setFile(null)}>Remove</button></p> : <p>Drag a photo, PDF or text file here, or <button className="text-button" onClick={() => fileInput.current?.click()}>choose a file</button>.</p>}
      {!file && !preparing ? <button type="button" className="button secondary" onClick={() => cameraInput.current?.click()}><Camera size={16} aria-hidden="true" /> Take a photo</button> : null}
      <input ref={fileInput} type="file" accept=".pdf,.txt,.md,application/pdf,text/plain,image/jpeg,image/png,image/webp,image/heic,image/heif" hidden onChange={(e: ChangeEvent<HTMLInputElement>) => { void choose(e.target.files?.[0]); e.target.value = ""; }} />
      <input ref={cameraInput} type="file" accept="image/*" capture="environment" hidden onChange={(e: ChangeEvent<HTMLInputElement>) => { void choose(e.target.files?.[0]); e.target.value = ""; }} />
    </div>
    {!file ? <label className="import-text">Or paste it here<textarea value={text} onChange={e => setText(e.target.value.slice(0, MAX_TEXT_CHARS))} rows={9} placeholder={"CS101 — Fall term\nAssignment 1 due Nov 20\nMidterm exam: Dec 3 at 10:00\nFinal project due Dec 12"} /></label> : null}
    {errorBox}
    <div className="button-row"><button className="button" onClick={extract} disabled={!ready || !!busy}>{busy === "reading" ? reading : file?.image ? "Find the tasks" : "Find my deadlines"} <span aria-hidden="true">→</span></button></div>
  </section>;
}
