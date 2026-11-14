"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useApi } from "@/hooks/use-api";
import { API_URL, readableError, type Api } from "@/lib/api";
import { browserTimezone, preferencesFromRows, preferenceUpdates, validatePreferences, validateTask } from "@/lib/task-utils";
import type { EffortAnswer, PreferenceRow, Preferences, Task, TaskInput } from "@/lib/types";

type Workspace = {
  api: Api;
  tasks: Task[]; preferences: Preferences; preferenceRows: PreferenceRow[];
  notice: string; notify: (message: string) => void;
  reloadTasks: () => Promise<void>;
  reloadPreferences: () => Promise<void>;
  createTask: (input: TaskInput) => Promise<Task>;
  updateTask: (id: string, input: Partial<TaskInput> & { pinned?: boolean }) => Promise<Task>;
  completeTask: (id: string, options?: { askEffort?: boolean }) => Promise<Task>;
  pendingEffort: Task | null; dismissEffort: (taskId?: string) => void;
  recordEffort: (id: string, answer: EffortAnswer, minutes?: number) => Promise<Task>;
  deleteTask: (id: string) => Promise<void>;
  savePreferences: (next: Preferences) => Promise<void>;
  reducedMotion: boolean; setReducedMotion: (value: boolean) => void;
};
const Context = createContext<Workspace | null>(null);
const motionKey = "lifeos.reduced-motion";

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const api = useApi();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [preferenceRows, setPreferenceRows] = useState<PreferenceRow[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [loadError, setLoadError] = useState("");
  const [notice, notify] = useState("");
  const [reducedMotion, setMotion] = useState(false);
  const [pendingEffort, setPendingEffort] = useState<Task | null>(null);
  const fallbackTimezone = useMemo(browserTimezone, []);
  const preferences = useMemo(() => preferencesFromRows(preferenceRows, fallbackTimezone), [preferenceRows, fallbackTimezone]);

  const reloadTasks = useCallback(async () => { setTasks(await api<Task[]>("/api/tasks")); }, [api]);
  const reloadPreferences = useCallback(async () => { setPreferenceRows(await api<PreferenceRow[]>("/api/preferences")); }, [api]);

  const load = useCallback(async () => {
    setStatus("loading"); setLoadError("");
    try {
      const [taskRows, rows] = await Promise.all([api<Task[]>("/api/tasks"), api<PreferenceRow[]>("/api/preferences")]);
      // Today and the planner use the saved timezone; seed it from this device once,
      // before the workspace opens, so it cannot overwrite a timezone the user saves.
      let seeded = rows;
      if (!rows.some(row => row.key === "timezone")) {
        try {
          const row = await api<PreferenceRow>("/api/preferences", { method: "POST", body: { key: "timezone", value: { name: fallbackTimezone }, source: "default" } });
          seeded = [...rows, row];
        } catch {
          notify(`Could not save your timezone (${fallbackTimezone}). LifeOS plans in UTC until you save it in Profile.`);
        }
      }
      setTasks(taskRows); setPreferenceRows(seeded);
      setStatus("ready");
    } catch (error) {
      setLoadError(readableError(error)); setStatus("error");
    }
  }, [api, fallbackTimezone]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    try { setMotion(localStorage.getItem(motionKey) === "true"); } catch { /* storage unavailable */ }
  }, []);
  useEffect(() => {
    document.documentElement.dataset.reducedMotion = String(reducedMotion);
    return () => { delete document.documentElement.dataset.reducedMotion; };
  }, [reducedMotion]);

  function setReducedMotion(value: boolean) {
    setMotion(value);
    try { localStorage.setItem(motionKey, String(value)); } catch { /* display setting only */ }
  }

  const replace = (task: Task) => setTasks(current => current.some(t => t.id === task.id) ? current.map(t => t.id === task.id ? task : t) : [task, ...current]);

  async function createTask(input: TaskInput) {
    const error = validateTask(input);
    if (error) throw new Error(error);
    const task = await api<Task>("/api/tasks", { method: "POST", body: { ...input, title: input.title.trim() } });
    replace(task);
    reloadTasks().catch(() => undefined); // other priorities may have been re-scored
    notify("Task added.");
    return task;
  }

  async function updateTask(id: string, input: Partial<TaskInput> & { pinned?: boolean }) {
    const task = await api<Task>(`/api/tasks/${id}`, { method: "PATCH", body: input });
    replace(task);
    reloadTasks().catch(() => undefined);
    notify("Task updated.");
    return task;
  }

  async function completeTask(id: string, { askEffort = true }: { askEffort?: boolean } = {}) {
    const task = await api<Task>(`/api/tasks/${id}/complete`, { method: "POST" });
    replace(task);
    notify(`Completed: ${task.title}`);
    if (askEffort) setPendingEffort(task);
    reloadTasks().catch(() => undefined);
    return task;
  }

  async function recordEffort(id: string, answer: EffortAnswer, minutes?: number) {
    const task = await api<Task>(`/api/tasks/${id}/actual-effort`, { method: "POST", body: answer === "custom" ? { answer, minutes } : { answer } });
    replace(task);
    notify("Thanks. LifeOS will use this to calibrate future estimates.");
    return task;
  }

  async function deleteTask(id: string) {
    await api(`/api/tasks/${id}?confirmed=true`, { method: "DELETE" });
    setTasks(current => current.filter(t => t.id !== id));
    notify("Task deleted.");
  }

  async function savePreferences(next: Preferences) {
    const error = validatePreferences(next);
    if (error) throw new Error(error);
    const updates = preferenceUpdates(preferences, next);
    try {
      for (const update of updates) await api("/api/preferences", { method: "POST", body: update });
    } finally {
      await reloadPreferences().catch(() => undefined);
    }
    notify(updates.length ? "Preferences saved." : "Nothing changed.");
  }

  if (status !== "ready") {
    return <div className="workspace-gate">{status === "loading"
      ? <p role="status">Opening your workspace…</p>
      : <section className="panel empty-state" role="alert"><p className="eyebrow">Connection problem</p><h2>LifeOS could not load your workspace.</h2><p>{loadError}</p><small className="muted">API: {API_URL}</small><button className="button" onClick={load}>Try again</button></section>}</div>;
  }

  return <Context.Provider value={{ api, tasks, preferences, preferenceRows, notice, notify, reloadTasks, reloadPreferences,
    createTask, updateTask, completeTask, pendingEffort, dismissEffort: (taskId?: string) => setPendingEffort(current => !taskId || current?.id === taskId ? null : current), recordEffort, deleteTask, savePreferences, reducedMotion, setReducedMotion }}>
    <div data-reduced-motion={reducedMotion}>{children}</div>
  </Context.Provider>;
}

export function useWorkspace() {
  const value = useContext(Context);
  if (!value) throw new Error("WorkspaceProvider is missing");
  return value;
}
