"use client";

import { useEffect, useRef, useState } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";
import { formatClock, formatDeadline, formatHours } from "@/lib/task-utils";
import type { Conflict, ConflictOptions, ConflictResolution } from "@/lib/types";

const optionTitles: Record<string, string> = { extend_hours: "Extend your hours", move_flexible: "Move something flexible", renegotiate: "Ask for more time" };

/** Capacity Guard sheet: simulated options from the server, applied as one undoable batch. */
export function ConflictSheet({ conflict, onClose, onChanged }: { conflict: Conflict; onClose: () => void; onChanged: () => void }) {
  const { api, preferences, notify, reloadTasks } = useWorkspace();
  const dialog = useRef<HTMLDialogElement>(null);
  const [data, setData] = useState<ConflictOptions>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [applied, setApplied] = useState<ConflictResolution>();
  const [undoUntil, setUndoUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const [copied, setCopied] = useState(false);

  useEffect(() => { if (dialog.current && !dialog.current.open) dialog.current.showModal(); }, []);
  useEffect(() => {
    let live = true;
    api<ConflictOptions>(`/api/conflicts/${conflict.id}/options`).then(result => { if (live) setData(result); }).catch(e => { if (live) setError(readableError(e)); });
    return () => { live = false; };
  }, [api, conflict.id]);
  useEffect(() => {
    if (!undoUntil) return;
    const timer = window.setInterval(() => { setNow(Date.now()); if (Date.now() > undoUntil) window.clearInterval(timer); }, 500);
    return () => window.clearInterval(timer);
  }, [undoUntil]);

  async function apply(type: string) {
    setBusy(type); setError("");
    try {
      const result = await api<ConflictResolution>(`/api/conflicts/${conflict.id}/resolve`, { method: "POST", body: { option_type: type } });
      setApplied(result); setUndoUntil(Date.now() + 10_000); setNow(Date.now());
      notify(result.remaining_conflicts ? `Applied. ${result.remaining_conflicts} conflict(s) still open.` : "Applied. Your plan fits again.");
      onChanged(); reloadTasks().catch(() => undefined);
    } catch (e) { setError(readableError(e, "Could not apply that option.")); }
    finally { setBusy(""); }
  }

  async function undo() {
    if (!applied) return;
    setBusy("undo"); setError("");
    try {
      await api(`/api/actions/batches/${applied.batch_id}/undo`, { method: "POST" });
      setApplied(undefined); setUndoUntil(0);
      notify("Undone. The conflict is open again.");
      onChanged(); reloadTasks().catch(() => undefined);
    } catch (e) { setError(readableError(e, "Could not undo.")); }
    finally { setBusy(""); }
  }

  async function copy(message: string) {
    try { await navigator.clipboard.writeText(message); setCopied(true); window.setTimeout(() => setCopied(false), 2000); }
    catch { setError("Copy is not available here. Select the text and copy it manually."); }
  }

  function close() { dialog.current?.close(); onClose(); }
  const secondsLeft = Math.max(0, Math.ceil((undoUntil - now) / 1000));
  const tasks = data?.conflict.tasks?.filter(task => task.title) ?? [];
  const draft = applied?.draft_message;

  return <dialog ref={dialog} className="task-dialog conflict-sheet" aria-labelledby="conflict-title" onCancel={close} onClose={onClose}>
    <button className="dialog-close" onClick={close} aria-label="Close options">×</button>
    <p className="eyebrow danger-text">Capacity guard</p>
    <h2 id="conflict-title">{formatHours(conflict.shortfall_min)} short before {formatDeadline(conflict.deadline_at, preferences.timezone)}</h2>
    <p className="muted">Needs {formatHours(conflict.needed_min)}, {formatHours(conflict.free_min)} free.{tasks.length ? ` Involves ${tasks.map(t => t.title).join(", ")}.` : ""}</p>
    {error ? <p className="error-message" role="alert">{error}</p> : null}
    {applied ? <div className="success-message" role="status">
      <p>Applied: {optionTitles[applied.applied] ?? applied.applied}.</p>
      {draft ? <div className="draft"><p>{draft}</p><button className="button secondary" onClick={() => copy(draft)}>{copied ? "Copied" : "Copy message"}</button></div> : null}
      <div className="button-row">{secondsLeft > 0 ? <button className="text-button" onClick={undo} disabled={busy === "undo"}>Undo <span className="muted">{secondsLeft}s</span></button> : null}<button className="button" onClick={close}>Done</button></div>
    </div> : !data && !error ? <p role="status" className="muted">Simulating options…</p> : data && !data.options.length ? <p className="muted">No automatic fix is available. Try moving a deadline in Tasks.</p> : <div className="option-list">{data?.options.map(option => <section key={option.type} className="option-card">
      <div className="action-head"><h3>{optionTitles[option.type] ?? option.type}</h3><span className={option.resolves ? "fits" : "short"}>{option.resolves ? "Fixes it" : option.remaining_shortfall_min ? `${formatHours(option.remaining_shortfall_min)} still short` : "Keeps the plan"}</span></div>
      <p>{option.description}</p>
      {option.preview.length ? <details><summary>Preview the plan</summary><ul className="block-list">{option.preview.map(block => <li key={`${block.task_id}-${block.start_at}`}><span>{formatDeadline(block.start_at, preferences.timezone)}–{formatClock(block.end_at, preferences.timezone)}</span>{block.title}</li>)}</ul></details> : null}
      {option.draft_message ? <div className="draft"><p>{option.draft_message}</p><button className="button secondary" onClick={() => copy(option.draft_message!)}>{copied ? "Copied" : "Copy message"}</button></div> : null}
      <button className="button" disabled={!!busy} onClick={() => apply(option.type)}>{busy === option.type ? "Applying…" : option.type === "renegotiate" ? "Keep plan and flag it" : "Apply"}</button>
    </section>)}</div>}
  </dialog>;
}
