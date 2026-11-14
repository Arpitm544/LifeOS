"use client";

import { useState, type FormEvent } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";
import { categories, type Category, type Task, type TaskInput } from "@/lib/types";

function dateInput(value: string | null) {
  if (!value) return "";
  const d = new Date(value);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function TaskForm({ task, onDone }: { task?: Task; onDone?: () => void }) {
  const { createTask, updateTask } = useWorkspace();
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setSaved(false);
    const form = event.currentTarget;
    const data = new FormData(form);
    const deadline = String(data.get("deadline") || "");
    const notes = String(data.get("notes") || "").trim();
    const input: TaskInput = { title: String(data.get("title") || "").trim(), deadline_at: deadline ? new Date(deadline).toISOString() : null,
      effort_est_min: Number(data.get("effort")), importance: Number(data.get("importance")), category: String(data.get("category")) as Category, notes: notes || null };
    setBusy(true);
    try {
      if (task) await updateTask(task.id, input);
      else { await createTask(input); form.reset(); setSaved(true); }
      onDone?.();
    } catch (e) { setError(readableError(e, "Could not save this task.")); }
    finally { setBusy(false); }
  }

  return <form className="task-form" onSubmit={submit}>
    <div><h2>{task ? "A little adjustment." : "Make room for something."}</h2><p className="eyebrow muted form-kicker">{task ? "Edit task" : "Quick add"}</p></div>
    <label>Task title<input name="title" required maxLength={120} placeholder="e.g. Finish the report" defaultValue={task?.title} /></label>
    <label>Deadline <span className="optional">(optional)</span><input type="datetime-local" name="deadline" defaultValue={dateInput(task?.deadline_at ?? null)} /><small>Entered in your device’s local timezone.</small></label>
    <label>Estimated effort <span className="optional">(minutes)</span><input type="number" name="effort" required min={5} max={600} step={1} defaultValue={task?.effort_est_min ?? 30} /></label>
    <label>Category<select name="category" defaultValue={task?.category ?? "study"}>{categories.map(c => <option key={c} value={c}>{c[0].toUpperCase() + c.slice(1)}</option>)}</select></label>
    <label>Importance<select name="importance" defaultValue={task?.importance ?? 3}>{[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n} · {["Low", "Flexible", "Normal", "Important", "Highest"][n - 1]}</option>)}</select></label>
    <label>Notes <span className="optional">(optional)</span><textarea name="notes" maxLength={2000} rows={2} defaultValue={task?.notes ?? ""} /></label>
    {error ? <p role="alert" className="error-message">{error}</p> : null}
    {saved && !task ? <p role="status" className="success-message">Added. A little less to keep in your head.</p> : null}
    <button type="submit" className="button" disabled={busy}>{busy ? "Saving…" : task ? "Save changes" : "Create task"}<span aria-hidden="true">↗</span></button>
  </form>;
}
