"use client";

import { useWorkspace } from "@/components/providers/workspace-provider";
import { formatDeadline, formatEffort, priorityBand } from "@/lib/task-utils";
import type { Task } from "@/lib/types";

export function TaskCard({ task, onEdit, detail }: { task: Task; onEdit?: (task: Task) => void; detail?: string }) {
  const { toggleTask, preferences } = useWorkspace();
  return <article className={`task-card ${task.completed ? "completed" : ""}`}>
    <div className="task-title-row"><button className="task-check" aria-label={`Complete ${task.title}`} aria-pressed={task.completed} onClick={() => toggleTask(task.id)}>{task.completed ? "✓" : ""}</button>
      <h3 className="task-title">{task.title}</h3>
      {onEdit ? <button className="edit-task" onClick={() => onEdit(task)} aria-label={`Edit ${task.title}`}>↗</button> : null}
    </div>
    <p className="task-meta">{detail ?? `${formatDeadline(task.deadline, preferences.timezone)}  ·  ${formatEffort(task.effort)}  ·  ${task.category}`}<span className={`priority priority-${priorityBand(task.importance).toLowerCase()}`}>{priorityBand(task.importance)}</span></p>
  </article>;
}
