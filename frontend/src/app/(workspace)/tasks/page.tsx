"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { PageHeading } from "@/components/layout/page-heading";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { TaskCard } from "@/components/tasks/task-card";
import { TaskForm } from "@/components/tasks/task-form";
import { readableError } from "@/lib/api";
import { blockersOf, comparePriority, filterTasks, type DependencyLink, type TaskFilter } from "@/lib/task-utils";
import type { Task } from "@/lib/types";

const filters: [TaskFilter, string][] = [["all", "All tasks"], ["today", "Today"], ["upcoming", "Upcoming"], ["completed", "Completed"]];
const byCompletion = (a: Task, b: Task) => Date.parse(b.completed_at ?? "") - Date.parse(a.completed_at ?? "");

export default function TasksPage() {
  const { api, tasks, preferences, deleteTask } = useWorkspace();
  const [links, setLinks] = useState<DependencyLink[]>([]);
  const loadLinks = useCallback(async () => { try { setLinks(await api<DependencyLink[]>("/api/tasks/dependencies")); } catch { /* the list still works without links */ } }, [api]);
  // Reload when the task list changes: completing a task can unblock others.
  useEffect(() => { loadLinks(); }, [loadLinks, tasks]);
  const [filter, setFilter] = useState<TaskFilter>("all");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Task>();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function shortcut(e: KeyboardEvent) {
      const el = e.target as HTMLElement;
      if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) && !el.isContentEditable) { e.preventDefault(); input.current?.focus(); }
    }
    // The top bar's search button lands here with ?search=1, or sends an event when Tasks is already open.
    const focusSearch = () => input.current?.focus();
    const params = new URLSearchParams(window.location.search);
    if (params.get("search") === "1") {
      focusSearch();
      params.delete("search");
      window.history.replaceState(null, "", `/tasks${params.toString() ? `?${params}` : ""}`);
    }
    document.addEventListener("keydown", shortcut);
    window.addEventListener("lifeos:focus-search", focusSearch);
    return () => { document.removeEventListener("keydown", shortcut); window.removeEventListener("lifeos:focus-search", focusSearch); };
  }, []);

  useEffect(() => { if (editing) dialog.current?.showModal(); }, [editing]);
  // Deep link /task/:id (from a reminder notification) opens that task's editor.
  const linked = useRef(false);
  useEffect(() => {
    if (linked.current) return;
    const id = new URLSearchParams(window.location.search).get("task");
    if (!id) { linked.current = true; return; }
    const match = tasks.find(task => task.id === id);
    if (match) { linked.current = true; setEditing(match); window.history.replaceState(null, "", "/tasks"); }
  }, [tasks]);
  function close() { dialog.current?.close(); setEditing(undefined); setConfirmDelete(false); setDeleteError(""); }
  async function remove(task: Task) {
    setDeleteError("");
    try { await deleteTask(task.id); close(); } catch (e) { setDeleteError(readableError(e, "Could not delete the task.")); }
  }
  const visible = filterTasks(tasks, filter, query, preferences.timezone);
  const grouped = filter !== "completed";
  const first = grouped ? visible.filter(t => t.status !== "blocked" && (t.pinned || !!t.deadline_at)).sort(comparePriority) : [...visible].sort(byCompletion);
  const later = grouped ? visible.filter(t => t.status !== "blocked" && !t.pinned && !t.deadline_at).sort(comparePriority) : [];
  const blocked = grouped ? visible.filter(t => t.status === "blocked").sort(comparePriority) : [];
  const waits = (task: Task) => blockersOf(task.id, links, tasks).map(item => item.title);
  const card = (task: Task) => <TaskCard key={task.id} task={task} onEdit={setEditing} waitsFor={waits(task)} />;

  return <>
    <PageHeading eyebrow="One place for everything" title="Big plans. Small next steps." description="Every commitment, ranked by what matters most right now." />
    <div className="task-toolbar"><div className="filter-tabs" role="group" aria-label="Filter tasks">{filters.map(([value, label]) => <button key={value} className={`filter-tab ${filter === value ? "selected" : ""}`} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}<span>{filterTasks(tasks, value, "", preferences.timezone).length}</span></button>)}</div></div>
    <div className="two-columns tasks-columns">
      <section className="panel task-list-panel" aria-label="Your tasks"><label className="search-field"><span aria-hidden="true">⌕</span><input ref={input} type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Find a little thing…" aria-label="Search tasks" /><kbd>/</kbd></label>
        {visible.length ? <>
          {first.length ? <><h2 className="eyebrow muted">{filter === "completed" ? "A little progress" : "Up next"}</h2><div className="task-list">{first.map(card)}</div></> : null}
          {later.length ? <><h2 className="eyebrow muted">Room for later</h2><div className="task-list">{later.map(card)}</div></> : null}
          {blocked.length ? <><h2 className="eyebrow muted">Waiting on something</h2><div className="task-list">{blocked.map(card)}</div></> : null}
        </> : <div className="empty-state"><span aria-hidden="true">◌</span><h2>{tasks.length ? "A little breathing room." : "No tasks yet."}</h2><p>{query ? "No tasks match your search." : tasks.length ? "No tasks in this view." : "Add one here, or tell LifeOS in Chat."}</p>{query ? <button className="button secondary" onClick={() => setQuery("")}>Clear search</button> : null}</div>}
      </section>
      <aside className="panel"><TaskForm /></aside>
    </div>
    <dialog aria-label="Edit task" ref={dialog} className="task-dialog" onCancel={close} onClose={() => { setEditing(undefined); setConfirmDelete(false); }}><button className="dialog-close" onClick={close} aria-label="Close task editor">×</button>
      {editing ? <><TaskForm key={editing.id} task={editing} onDone={close} links={links} onLinksChanged={loadLinks} /><div className="delete-area">{confirmDelete ? <><p>Delete this task? It is removed from your lists and your plan.</p><button className="button danger" onClick={() => remove(editing)}>Yes, delete task</button><button className="text-button" onClick={() => setConfirmDelete(false)}>Keep task</button></> : <button className="text-button danger-text" onClick={() => setConfirmDelete(true)}>Delete task</button>}{deleteError ? <p className="error-message" role="alert">{deleteError}</p> : null}</div></> : null}
    </dialog>
  </>;
}
