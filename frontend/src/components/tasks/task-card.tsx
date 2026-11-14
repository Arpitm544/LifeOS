"use client";

import { useState } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";
import { formatDeadline, formatEffort } from "@/lib/task-utils";
import type { PriorityBreakdown, Task } from "@/lib/types";

const factors: [keyof PriorityBreakdown, string][] = [["urgency", "Urgency"], ["importance", "Importance"], ["blocking", "Unblocks others"], ["staleness", "Waiting time"]];

export function PriorityDetails({ breakdown, score }: { breakdown: PriorityBreakdown; score: number }) {
  return <dl className="priority-details">
    <div><dt>Score</dt><dd>{Math.round(score)}/100</dd></div>
    {factors.map(([key, label]) => typeof breakdown[key] === "number" ? <div key={key}><dt>{label}{breakdown.weights?.[key] ? ` · ${Math.round(breakdown.weights[key] * 100)}%` : ""}</dt><dd><span className="factor-bar"><span style={{ width: `${Math.round(Math.min(1, Number(breakdown[key])) * 100)}%` }} /></span></dd></div> : null)}
    {typeof breakdown.free_hours_before_deadline === "number" ? <div><dt>Free before deadline</dt><dd>{breakdown.free_hours_before_deadline} h</dd></div> : null}
    {breakdown.calibration_factor && breakdown.calibration_factor !== 1 ? <div><dt>Planned effort</dt><dd>{formatEffort(breakdown.effort_min ?? 0)} ({breakdown.calibration_factor}× estimate)</dd></div> : null}
    {breakdown.blocks_count ? <div><dt>Blocks</dt><dd>{breakdown.blocks_count} task{breakdown.blocks_count === 1 ? "" : "s"}</dd></div> : null}
  </dl>;
}

export function TaskCard({ task, onEdit }: { task: Task; onEdit?: (task: Task) => void }) {
  const { completeTask, preferences, notify } = useWorkspace();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const done = task.status === "done";

  async function complete() {
    if (done || busy) return;
    setBusy(true);
    try { await completeTask(task.id); }
    catch (e) { notify(readableError(e, "Could not complete the task.")); }
    finally { setBusy(false); }
  }

  return <article className={`task-card ${done ? "completed" : ""}`}>
    <div className="task-title-row"><button className="task-check" aria-label={`Complete ${task.title}`} aria-pressed={done} disabled={done || busy} onClick={complete}>{done ? "✓" : ""}</button>
      <h3 className="task-title">{task.title}</h3>
      {onEdit ? <button className="edit-task" onClick={() => onEdit(task)} aria-label={`Edit ${task.title}`}>↗</button> : null}
    </div>
    <p className="task-meta">{formatDeadline(task.deadline_at, preferences.timezone)}<span aria-hidden="true">·</span>{formatEffort(task.effort_est_min)}<span aria-hidden="true">·</span>{task.category}
      {task.status === "blocked" ? <span className="status-label">Blocked</span> : null}
      {task.pinned ? <span className="status-label">Pinned</span> : null}
      {!done ? <button type="button" className={`priority priority-${task.priority_band.toLowerCase()}`} aria-expanded={open} aria-label={`Priority ${task.priority_band}. Show why`} onClick={() => setOpen(value => !value)}>{task.priority_band}</button> : null}
    </p>
    {task.why && !done ? <p className="task-why">{task.why}</p> : null}
    {open && !done ? task.priority_breakdown ? <PriorityDetails breakdown={task.priority_breakdown} score={task.priority_score} /> : <p className="task-why">Score {Math.round(task.priority_score)}/100.</p> : null}
  </article>;
}
