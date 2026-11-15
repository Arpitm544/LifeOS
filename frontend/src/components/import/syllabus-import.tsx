"use client";

import Link from "next/link";
import { CalendarDays, Camera, ChevronDown, CircleCheck, ClipboardPaste, Clock, FileText, RotateCcw, TriangleAlert, Undo2, Upload, X } from "lucide-react";
import { useEffect, useRef, useState, type ChangeEvent, type DragEvent, type KeyboardEvent } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";
import { bytesToBase64, extractNotes, formatBytes, formatMinutes, MAX_TEXT_CHARS, readingMessage, saveSummary, selectedTasks, selectionSummary, toReviewRows, UNDO_SECONDS, uploadKind, type ExtractResult, type ReviewRow, type SaveResult } from "@/lib/syllabus";
import { formatDeadline } from "@/lib/task-utils";
import { preparePhoto } from "@/lib/photo";
import { categories, type Category } from "@/lib/types";

type Review = { result: ExtractResult; preview?: string };
type Stage = { name: "input" } | ({ name: "review" } & Review) | { name: "saved"; result: SaveResult; savedAt: number; review: Review };
type Source = "upload" | "paste";
type Chosen = { name: string; size: number; pdf?: string; image?: string; preview?: string };

const STEPS = ["Add", "Review", "Planned"] as const;
const DAY_MS = 86_400_000;

function localInput(value: string | null) {
  if (!value) return "";
  const d = new Date(value);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function dueTone(value: string | null): "none" | "soon" | "later" {
  if (!value) return "none";
  return new Date(value).getTime() - Date.now() < 2 * DAY_MS ? "soon" : "later";
}

const capitalise = (value: string) => value[0].toUpperCase() + value.slice(1);

function Stepper({ current }: { current: 0 | 1 | 2 }) {
  return <ol className="import-steps" aria-label="Import progress">
    {STEPS.map((label, index) => <li key={label} className={index < current ? "done" : index === current ? "current" : ""} aria-current={index === current ? "step" : undefined}>
      <span aria-hidden="true">{index < current ? <CircleCheck size={14} /> : index + 1}</span>{label}
    </li>)}
  </ol>;
}

export function SyllabusImport() {
  const { api, preferences, reloadTasks } = useWorkspace();
  const [stage, setStage] = useState<Stage>({ name: "input" });
  const [source, setSource] = useState<Source>("upload");
  const [text, setText] = useState("");
  const [file, setFile] = useState<Chosen | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [rows, setRows] = useState<ReviewRow[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [plan, setPlan] = useState(true);
  const [busy, setBusy] = useState<"" | "reading" | "saving" | "undoing">("");
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const [undoLeft, setUndoLeft] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const cameraInput = useRef<HTMLInputElement>(null);
  const reading = useRef<AbortController | null>(null);

  useEffect(() => {
    if (stage.name !== "saved") return;
    const tick = () => setUndoLeft(Math.max(0, UNDO_SECONDS - Math.floor((Date.now() - stage.savedAt) / 1000)));
    tick();
    const timer = window.setInterval(tick, 500);
    return () => window.clearInterval(timer);
  }, [stage]);

  useEffect(() => {
    if (busy !== "reading") return;
    const started = Date.now();
    setElapsed(0);
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 500);
    return () => window.clearInterval(timer);
  }, [busy]);

  useEffect(() => () => reading.current?.abort(), []);

  async function choose(chosen: File | undefined) {
    setError("");
    if (!chosen) return;
    const kind = uploadKind(chosen);
    if ("error" in kind) { setError(kind.error); return; }
    if (kind.kind === "image") {
      setPreparing(true);
      try {
        const photo = await preparePhoto(chosen);
        setFile({ name: chosen.name || "Photo", size: photo.bytes, image: photo.base64, preview: photo.dataUrl });
        setSource("upload");
      } catch (e) { setError(readableError(e, "That photo could not be opened. Try again or paste the text.")); }
      finally { setPreparing(false); }
      return;
    }
    try {
      if (kind.kind === "pdf") { setFile({ name: chosen.name, size: chosen.size, pdf: bytesToBase64(new Uint8Array(await chosen.arrayBuffer())) }); setSource("upload"); }
      else { setText((await chosen.text()).slice(0, MAX_TEXT_CHARS)); setFile(null); setSource("paste"); }
    } catch { setError("That file could not be opened. Try again or paste the text."); }
  }

  async function extract() {
    setError(""); setBusy("reading");
    const controller = new AbortController();
    reading.current = controller;
    const usingFile = source === "upload" && file;
    try {
      const body = usingFile && file.image ? { image_base64: file.image, client_tz: preferences.timezone }
        : usingFile && file.pdf ? { pdf_base64: file.pdf, client_tz: preferences.timezone }
        : { text, client_tz: preferences.timezone };
      const result = await api<ExtractResult>("/api/import/syllabus/extract", { method: "POST", body, signal: controller.signal });
      setRows(toReviewRows(result.proposals));
      setOpen(null);
      setStage({ name: "review", result, preview: usingFile ? file.preview : undefined });
    } catch (e) {
      if (!controller.signal.aborted) setError(readableError(e, "LifeOS could not read that. Try again or paste the text."));
    } finally {
      if (reading.current === controller) reading.current = null;
      setBusy("");
    }
  }

  function cancelReading() { reading.current?.abort(); }

  async function save(review: Review) {
    const chosen = selectedTasks(rows);
    if ("error" in chosen) { setError(chosen.error); return; }
    setError(""); setBusy("saving");
    try {
      const result = await api<SaveResult>("/api/import/syllabus/save", { method: "POST", body: { tasks: chosen.tasks, plan } });
      setStage({ name: "saved", result, savedAt: Date.now(), review });
      await reloadTasks().catch(() => undefined);
    } catch (e) { setError(readableError(e, "Could not add these tasks.")); }
    finally { setBusy(""); }
  }

  async function undo(result: SaveResult, review: Review) {
    setError(""); setBusy("undoing");
    try {
      await api(`/api/import/syllabus/${encodeURIComponent(result.batch_id)}/undo`, { method: "POST" });
      await reloadTasks().catch(() => undefined);
      setStage({ name: "review", ...review }); // back to the same list, so it can be fixed and added again
    } catch (e) { setError(readableError(e, "Could not undo the import.")); }
    finally { setBusy(""); }
  }

  function update(id: string, change: Partial<ReviewRow>) {
    setRows(current => current.map(row => row.id === id ? { ...row, ...change } : row));
  }

  function selectAll(selected: boolean) { setRows(current => current.map(row => ({ ...row, selected }))); }

  function reset() { setStage({ name: "input" }); setRows([]); setText(""); setFile(null); setError(""); setOpen(null); }

  const errorBox = error ? <p className="error-message import-error" role="alert"><TriangleAlert size={15} aria-hidden="true" />{error}</p> : null;

  if (stage.name === "saved") {
    const { result, review } = stage;
    const tight = result.conflicts.length;
    return <section className="panel import-panel" aria-live="polite">
      <Stepper current={2} />
      <div className="import-done">
        <span className="import-done-icon" aria-hidden="true"><CircleCheck size={28} /></span>
        <div><h2>Your plan is updated.</h2><p className="muted" role="status">{saveSummary(result)}</p></div>
      </div>
      <dl className="import-stats">
        <div><dt>Tasks added</dt><dd>{result.task_ids.length}</dd></div>
        <div><dt>Focus blocks</dt><dd>{result.planned ? result.blocks : "—"}</dd></div>
        <div className={tight ? "warn" : ""}><dt>Tight deadlines</dt><dd>{tight}</dd></div>
      </dl>
      {errorBox}
      <div className="button-row">
        <Link className="button" href="/today">See today’s plan <span aria-hidden="true">→</span></Link>
        <Link className="button secondary" href="/tasks">View tasks</Link>
        <button className="text-button" onClick={reset} disabled={!!busy}><RotateCcw size={14} aria-hidden="true" /> Import another</button>
        {undoLeft > 0 ? <button className="text-button import-undo" onClick={() => undo(result, review)} disabled={!!busy}><Undo2 size={14} aria-hidden="true" />{busy === "undoing" ? "Undoing…" : `Undo (${undoLeft}s)`}</button> : null}
      </div>
    </section>;
  }

  if (stage.name === "review") {
    const { result, preview } = stage;
    const review: Review = { result, preview };
    const { count, minutes } = selectionSummary(rows);
    const allSelected = rows.length > 0 && count === rows.length;
    const label = result.course || (result.source === "photo" ? "From your photo" : "From your syllabus");
    return <section className="panel import-panel" aria-label="Review the tasks LifeOS found">
      <Stepper current={1} />
      <div className="import-head">
        <div>
          <p className="eyebrow blue">{label}</p>
          <h2>{rows.length ? `Found ${rows.length} thing${rows.length === 1 ? "" : "s"} to plan for` : "Nothing to add"}</h2>
          <p className="muted">Nothing is saved yet. Untick anything you don’t need and open a task to fix its details.</p>
        </div>
        {rows.length ? <label className="import-select-all"><input type="checkbox" checked={allSelected} ref={el => { if (el) el.indeterminate = count > 0 && !allSelected; }} onChange={e => selectAll(e.target.checked)} /> Select all</label> : null}
      </div>
      {extractNotes(result).map(note => <p key={note} className="import-note">{note}</p>)}
      <div className={`import-review${preview ? " with-preview" : ""}`}>
        {rows.length ? <ul className="import-list">{rows.map(row => {
          const tone = dueTone(row.deadline_at);
          const editing = open === row.id;
          return <li key={row.id} className={`${row.selected ? "" : "unselected"}${editing ? " editing" : ""}`}>
            <input type="checkbox" checked={row.selected} onChange={e => update(row.id, { selected: e.target.checked })} aria-label={`Add ${row.title || "this task"}`} />
            <div className="import-fields">
              <div className="import-row-top">
                <input className="import-title" value={row.title} maxLength={120} onChange={e => update(row.id, { title: e.target.value })} aria-label="Task title" />
                <button type="button" className="import-edit" aria-expanded={editing} aria-label={`${editing ? "Hide" : "Edit"} details for ${row.title || "this task"}`} onClick={() => setOpen(editing ? null : row.id)}>
                  {editing ? "Done" : "Edit"}<ChevronDown size={14} aria-hidden="true" />
                </button>
              </div>
              <div className="import-tags">
                <span className={`import-tag due ${tone}`}><CalendarDays size={12} aria-hidden="true" />{row.deadline_at ? formatDeadline(row.deadline_at, preferences.timezone) : "No date"}</span>
                <span className="import-tag"><Clock size={12} aria-hidden="true" />{formatMinutes(row.effort_est_min)}</span>
                <span className="import-tag">{capitalise(row.category)}</span>
                {row.kind !== "other" ? <span className="import-tag">{capitalise(row.kind)}</span> : null}
                {row.importance >= 4 ? <span className="import-tag important">Important</span> : null}
              </div>
              {editing ? <div className="import-meta">
                <label>Due<input type="datetime-local" value={localInput(row.deadline_at)} onChange={e => update(row.id, { deadline_at: e.target.value ? new Date(e.target.value).toISOString() : null })} /></label>
                <label>Effort (min)<input type="number" min={5} max={600} value={row.effort_est_min} onChange={e => update(row.id, { effort_est_min: Number(e.target.value) })} /></label>
                <label>Category<select value={row.category} onChange={e => update(row.id, { category: e.target.value as Category })}>{categories.map(c => <option key={c} value={c}>{capitalise(c)}</option>)}</select></label>
                <label>Importance<select value={row.importance} onChange={e => update(row.id, { importance: Number(e.target.value) })}>{[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}{n === 5 ? " (highest)" : n === 1 ? " (lowest)" : ""}</option>)}</select></label>
              </div> : null}
              {row.notes ? <small className="import-source">{row.notes}</small> : null}
            </div>
          </li>;
        })}</ul> : <div className="import-empty">
          <TriangleAlert size={22} aria-hidden="true" />
          <p>{result.source === "photo" ? "No tasks could be read from that photo." : "No dated deadlines were found."}</p>
          <p className="muted">{result.source === "photo" ? "Try a closer, sharper, well-lit photo, or paste the text instead." : "Try pasting just the schedule section of the syllabus."}</p>
        </div>}
        {preview ? <figure className="import-photo"><img src={preview} alt="The photo LifeOS read" /><figcaption>Compare with your photo</figcaption></figure> : null}
      </div>
      {errorBox}
      <div className="import-actions">
        <div className="import-actions-info">
          {rows.length ? <p><b>{count} selected</b>{count ? <span className="muted import-wide"> · about {formatMinutes(minutes)} of work</span> : null}</p> : null}
          {rows.length ? <label className="import-plan"><input type="checkbox" checked={plan} onChange={e => setPlan(e.target.checked)} /> Plan focus time<span className="import-wide"> over the next two weeks</span></label> : null}
        </div>
        <div className="button-row">
          <button className="text-button" onClick={reset} disabled={!!busy}>Start over</button>
          {rows.length ? <button className="button" onClick={() => save(review)} disabled={!!busy || !count}>{busy === "saving" ? "Adding…" : `Add ${count} task${count === 1 ? "" : "s"}${plan ? " and plan" : ""}`} <span aria-hidden="true">→</span></button>
            : <button className="button" onClick={reset}>Try again <span aria-hidden="true">→</span></button>}
        </div>
      </div>
    </section>;
  }

  const kind: "photo" | "pdf" | "text" = source === "upload" && file?.image ? "photo" : source === "upload" && file?.pdf ? "pdf" : "text";
  if (busy === "reading") {
    return <section className="panel import-panel" aria-busy="true">
      <Stepper current={0} />
      <div className="import-reading">
        {kind === "photo" && file?.preview ? <div className="import-scan"><img src={file.preview} alt="" /><span aria-hidden="true" /></div>
          : <div className="import-scan doc" aria-hidden="true">{[80, 62, 90, 54, 72, 40].map((width, i) => <span key={i} className="skeleton" style={{ width: `${width}%` }} />)}</div>}
        <div className="import-reading-copy">
          <p className="import-reading-status" role="status">{readingMessage(elapsed, kind)}</p>
          <p className="muted">{elapsed}s · this usually takes under half a minute.</p>
          <button className="text-button" onClick={cancelReading}><X size={14} aria-hidden="true" /> Cancel</button>
        </div>
      </div>
    </section>;
  }

  const ready = !preparing && (source === "upload" ? !!file : !!text.trim());
  const onDrop = (e: DragEvent) => { e.preventDefault(); setDragging(false); setSource("upload"); void choose(e.dataTransfer.files[0]); };
  const openPicker = () => fileInput.current?.click();
  const onZoneKey = (e: KeyboardEvent) => { if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openPicker(); } };
  return <section className="panel import-panel">
    <Stepper current={0} />
    <div className="import-source-bar">
      <div className="segmented" role="tablist" aria-label="How to add">
        <button role="tab" aria-selected={source === "upload"} className={source === "upload" ? "selected" : ""} onClick={() => setSource("upload")}><Upload size={14} aria-hidden="true" /> Photo or file</button>
        <button role="tab" aria-selected={source === "paste"} className={source === "paste" ? "selected" : ""} onClick={() => setSource("paste")}><ClipboardPaste size={14} aria-hidden="true" /> Paste text</button>
      </div>
      <p className="muted">You review everything before it’s saved.</p>
    </div>

    {source === "upload" ? (file ? <div className="import-file">
      {file.preview ? <img src={file.preview} alt="The photo LifeOS will read" /> : <span className="import-file-icon" aria-hidden="true"><FileText size={26} /></span>}
      <div className="import-file-info">
        <p><b>{file.name}</b></p>
        <p className="muted">{file.image ? "Photo" : "PDF"} · {formatBytes(file.size)} · ready to read</p>
        <div className="button-row">
          <button className="text-button" onClick={openPicker}>Replace</button>
          <button className="text-button" onClick={() => setFile(null)}><X size={14} aria-hidden="true" /> Remove</button>
        </div>
      </div>
    </div> : <div className={`drop-zone${dragging ? " dragging" : ""}`} role="button" tabIndex={0} aria-label="Choose a photo, PDF or text file" onClick={e => { if (e.target === e.currentTarget) openPicker(); }} onKeyDown={onZoneKey}
      onDragOver={(e: DragEvent) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={onDrop}>
      <span className="drop-icon" aria-hidden="true"><Upload size={22} /></span>
      {preparing ? <p className="drop-title" role="status">Preparing your photo…</p> : <>
        <p className="drop-title">{dragging ? "Drop it here" : "Drag a photo, PDF or text file here"}</p>
        <p className="drop-hint">Whiteboards, handwritten lists, notices, syllabi · JPEG, PNG, HEIC, PDF or TXT</p>
        <div className="button-row">
          <button type="button" className="button secondary" onClick={openPicker}><Upload size={16} aria-hidden="true" /> Choose a file</button>
          <button type="button" className="button secondary" onClick={() => cameraInput.current?.click()}><Camera size={16} aria-hidden="true" /> Take a photo</button>
        </div>
      </>}
    </div>) : <label className="import-text">
      <span className="sr-only">Paste your syllabus or list</span>
      <textarea value={text} autoFocus onChange={e => setText(e.target.value.slice(0, MAX_TEXT_CHARS))} rows={10} placeholder={"CS101 — Fall term\nAssignment 1 due Nov 20\nMidterm exam: Dec 3 at 10:00\nFinal project due Dec 12"} />
      <small className="muted">{text.length ? `${text.length.toLocaleString()} characters` : "Paste a syllabus, a schedule or any list of to-dos."}</small>
    </label>}
    <input ref={fileInput} type="file" accept=".pdf,.txt,.md,application/pdf,text/plain,image/jpeg,image/png,image/webp,image/heic,image/heif" hidden onChange={(e: ChangeEvent<HTMLInputElement>) => { void choose(e.target.files?.[0]); e.target.value = ""; }} />
    <input ref={cameraInput} type="file" accept="image/*" capture="environment" hidden onChange={(e: ChangeEvent<HTMLInputElement>) => { void choose(e.target.files?.[0]); e.target.value = ""; }} />
    {errorBox}
    <div className="button-row"><button className="button" onClick={extract} disabled={!ready || !!busy}>{kind === "photo" ? "Find the tasks" : "Find my deadlines"} <span aria-hidden="true">→</span></button></div>
  </section>;
}
