"use client";

import { useEffect, useRef, useState } from "react";
import { PageHeading } from "@/components/layout/page-heading";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { TaskCard } from "@/components/tasks/task-card";
import { TaskForm } from "@/components/tasks/task-form";
import { compareDeadlines, filterTasks, type TaskFilter } from "@/lib/task-utils";
import type { Task } from "@/lib/types";

const filters: [TaskFilter, string][] = [["all", "All tasks"], ["today", "Today"], ["upcoming", "Upcoming"], ["completed", "Completed"]];

export default function TasksPage() {
  const { tasks, preferences, ready, deleteTask } = useWorkspace();
  const [filter, setFilter] = useState<TaskFilter>("all");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Task>();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function shortcut(e: KeyboardEvent) {
      const el = e.target as HTMLElement;
      if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) && !el.isContentEditable) { e.preventDefault(); input.current?.focus(); }
    }
    document.addEventListener("keydown", shortcut);
    return () => document.removeEventListener("keydown", shortcut);
  }, []);

  useEffect(() => { if (editing) dialog.current?.showModal(); }, [editing]);
  function close() { dialog.current?.close(); setEditing(undefined); setConfirmDelete(false); }
  const visible = filterTasks(tasks, filter, query, preferences.timezone);
  const first = visible.filter(t => !!t.deadline).sort(compareDeadlines);
  const later = visible.filter(t => !t.deadline);

  return <>
    <PageHeading eyebrow="One place for everything" title="Big plans. Small next steps." description="Every commitment, with a clear place to start." />
    <div className="task-toolbar"><div className="filter-tabs" role="group" aria-label="Filter tasks">{filters.map(([value, label]) => <button key={value} className={`filter-tab ${filter === value ? "selected" : ""}`} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}<span>{filterTasks(tasks, value, "", preferences.timezone).length}</span></button>)}</div></div>
    <div className="two-columns tasks-columns">
      <section className="panel task-list-panel" aria-label="Your tasks"><label className="search-field"><span aria-hidden="true">⌕</span><input ref={input} type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Find a little thing…" aria-label="Search tasks" /><kbd>/</kbd></label>
        {!ready ? <p className="muted" role="status">Opening your workspace…</p> : visible.length ? <>
          {first.length ? <><h2 className="eyebrow muted">{filter === "completed" ? "A little progress" : "Up next"}</h2><div className="task-list">{first.map(task => <TaskCard key={task.id} task={task} onEdit={setEditing} />)}</div></> : null}
          {later.length ? <><h2 className="eyebrow muted">Room for later</h2><div className="task-list">{later.map(task => <TaskCard key={task.id} task={task} onEdit={setEditing} />)}</div></> : null}
        </> : <div className="empty-state"><span aria-hidden="true">◌</span><h2>A little breathing room.</h2><p>{query ? "No tasks match your search." : "No tasks in this view. Add one whenever you’re ready."}</p>{query ? <button className="button secondary" onClick={() => setQuery("")}>Clear search</button> : null}</div>}
      </section>
      <aside className="panel"><TaskForm /></aside>
    </div>
    <dialog aria-label="Edit task" ref={dialog} className="task-dialog" onCancel={close} onClose={() => { setEditing(undefined); setConfirmDelete(false); }}><button className="dialog-close" onClick={close} aria-label="Close task editor">×</button>
      {editing ? <><TaskForm key={editing.id} task={editing} onDone={close} /><div className="delete-area">{confirmDelete ? <><p>Delete this task? This cannot be undone.</p><button className="button danger" onClick={() => { deleteTask(editing.id); close(); }}>Yes, delete task</button><button className="text-button" onClick={() => setConfirmDelete(false)}>Keep task</button></> : <button className="text-button danger-text" onClick={() => setConfirmDelete(true)}>Delete task</button>}</div></> : null}
    </dialog>
  </>;
}
