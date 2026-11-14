"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { EffortPrompt } from "@/components/tasks/effort-prompt";
import { readableError, undoPath } from "@/lib/api";
import { describePreference, formatClock, formatDeadline, formatEffort, formatHours } from "@/lib/task-utils";
import type { ChatAction, ChatTaskCard } from "@/lib/types";

const labels: Record<ChatAction["type"], string> = {
  task_created: "Task added", task_updated: "Task updated", task_completed: "Task completed", task_deleted: "Task deleted",
  event_created: "Event added", preference_set: "Preference saved", schedule: "Your schedule", plan_generated: "Plan ready", capacity_check: "Capacity check",
};

function useSecondsLeft(until?: string) {
  const [now, setNow] = useState(() => Date.now());
  const end = until ? Date.parse(until) : 0;
  useEffect(() => {
    if (!end || end <= Date.now()) return;
    const timer = window.setInterval(() => { setNow(Date.now()); if (Date.now() >= end) window.clearInterval(timer); }, 500);
    return () => window.clearInterval(timer);
  }, [end]);
  return end ? Math.max(0, Math.ceil((end - now) / 1000)) : 0;
}

function TaskSummary({ task }: { task: ChatTaskCard }) {
  const { preferences } = useWorkspace();
  return <div className="action-task">
    <p className="task-title">{task.title}</p>
    <p className="task-meta">{task.deadline_label ?? formatDeadline(task.deadline_at, preferences.timezone)}<span aria-hidden="true">·</span>{formatEffort(task.effort_est_min)}<span aria-hidden="true">·</span>{task.category}
      {task.status !== "done" && task.status !== "dropped" ? <span className={`priority priority-${task.priority_band.toLowerCase()}`}>{task.priority_band}</span> : null}</p>
    {task.why && task.status !== "done" && task.status !== "dropped" ? <p className="task-why">{task.why}</p> : null}
  </div>;
}

type Block = { task_id: string; title?: string | null; start_at: string; end_at: string };
function BlockList({ blocks }: { blocks: Block[] }) {
  const { preferences } = useWorkspace();
  if (!blocks.length) return <p className="muted">Nothing scheduled.</p>;
  return <ul className="block-list">{blocks.map(block => <li key={`${block.task_id}-${block.start_at}`}><span>{formatClock(block.start_at, preferences.timezone)}–{formatClock(block.end_at, preferences.timezone)}</span>{block.title ?? "Task"}</li>)}</ul>;
}

function Body({ action }: { action: ChatAction }) {
  const { preferences } = useWorkspace();
  const result = (action.result ?? {}) as Record<string, unknown>;
  switch (action.type) {
    case "task_created": case "task_updated": case "task_completed": case "task_deleted":
      return action.task ? <TaskSummary task={action.task} /> : <p className="task-title">{action.title}</p>;
    case "event_created":
      return action.event ? <div className="action-task"><p className="task-title">{action.event.title}</p><p className="task-meta">{action.event.label}{action.event.location ? <><span aria-hidden="true">·</span>{action.event.location}</> : null}</p></div> : null;
    case "preference_set": {
      if (!action.preference) return null;
      const { label, value } = describePreference(action.preference);
      return <p><b>{label}:</b> {value}</p>;
    }
    case "plan_generated":
      return <><BlockList blocks={action.plan_blocks ?? []} />{action.unplaced_task_ids?.length ? <p className="muted">{action.unplaced_task_ids.length} task(s) did not fit. Check Today for options.</p> : null}<Link className="text-button" href="/today">Open Today <span aria-hidden="true">↗</span></Link></>;
    case "schedule": {
      const due = (result.due ?? []) as ChatTaskCard[];
      const blocks = (result.plan_blocks ?? []) as Block[];
      const slots = (result.free_slots ?? []) as { start_at: string; end_at: string }[];
      return <>
        {Array.isArray(result.due) ? due.length ? <div className="action-list">{due.map(task => <TaskSummary key={task.id} task={task} />)}</div> : <p className="muted">Nothing due in that range.</p> : null}
        {Array.isArray(result.plan_blocks) ? <BlockList blocks={blocks} /> : null}
        {typeof result.free_min === "number" ? <><p><b>{formatHours(result.free_min)}</b> free</p>{slots.length ? <ul className="block-list">{slots.slice(0, 6).map(slot => <li key={slot.start_at}><span>{formatDeadline(slot.start_at, preferences.timezone)}</span>until {formatClock(slot.end_at, preferences.timezone)}</li>)}</ul> : null}</> : null}
      </>;
    }
    case "capacity_check": {
      const fits = result.fits === true;
      return <p className={fits ? "fits" : "short"}>{fits
        ? `It fits: ${formatHours(Number(result.free_min ?? 0))} free, ${formatHours(Number(result.needed_min ?? 0))} needed.`
        : `${formatHours(Number(result.shortfall_min ?? 0))} short before ${formatDeadline(String(result.deadline_at ?? ""), preferences.timezone)}.`}</p>;
    }
    default:
      return null;
  }
}

export function ActionCard({ action }: { action: ChatAction }) {
  const { api, reloadTasks, reloadPreferences, notify } = useWorkspace();
  const seconds = useSecondsLeft(action.undo_until);
  const [state, setState] = useState<"idle" | "busy" | "undone">("idle");
  const [error, setError] = useState("");
  const path = undoPath(action);

  async function undo() {
    if (!path) return;
    setState("busy"); setError("");
    try { await api(path, { method: "POST" }); }
    catch (e) { setState("idle"); setError(readableError(e, "Could not undo.")); return; }
    setState("undone");
    notify(`Undone: ${labels[action.type].toLowerCase()}.`);
    Promise.all([reloadTasks(), action.type === "preference_set" ? reloadPreferences() : Promise.resolve()]).catch(() => undefined);
  }

  return <article className={`action-card ${state === "undone" ? "undone" : ""}`}>
    <div className="action-head"><p className="eyebrow blue">{labels[action.type] ?? action.type}</p>
      {state === "undone" ? <span className="muted">Undone</span> : path && seconds > 0 ? <button className="text-button" onClick={undo} disabled={state === "busy"}>Undo <span className="muted">{seconds}s</span></button> : null}</div>
    <Body action={action} />
    {error ? <p className="error-message" role="alert">{error}</p> : null}
    {action.type === "task_completed" && action.ask_actual_effort && action.task_id && state !== "undone" ? <EffortPrompt taskId={action.task_id} estimate={action.task?.effort_est_min} /> : null}
  </article>;
}
