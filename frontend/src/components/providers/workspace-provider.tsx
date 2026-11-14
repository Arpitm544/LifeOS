"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { defaultPreferences, demoTasks } from "@/lib/demo-data";
import { parseWorkspace, validatePreferences, validateTask } from "@/lib/task-utils";
import type { Preferences, Task, TaskInput } from "@/lib/types";

type Workspace = {
  tasks: Task[]; preferences: Preferences; ready: boolean; notice: string;
  notify: (message: string) => void;
  saveTask: (input: TaskInput, id?: string) => Task;
  toggleTask: (id: string) => void;
  deleteTask: (id: string) => void;
  savePreferences: (preferences: Preferences) => void;
};
const Context = createContext<Workspace | null>(null);
const key = "lifeos.workspace.v1";

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [preferences, setPreferences] = useState(defaultPreferences);
  const [ready, setReady] = useState(false);
  const [notice, notify] = useState("");
  const canPersist = useRef(true);
  const lastSaved = useRef<string | null>(null);

  useEffect(() => {
    function load() {
      try {
        const raw = localStorage.getItem(key);
        const saved = raw ? parseWorkspace(raw) : { tasks: demoTasks, preferences: defaultPreferences };
        lastSaved.current = raw;
        canPersist.current = true;
        setTasks(saved.tasks); setPreferences(saved.preferences);
      } catch {
        canPersist.current = false;
        notify("Saved data could not be loaded. The current session is shown; the original data has not been overwritten.");
      }
    }
    load();
    setReady(true);
    function sync(event: StorageEvent) {
      if (event.storageArea === localStorage && (event.key === key || event.key === null)) load();
    }
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  useEffect(() => {
    if (!ready || !canPersist.current) return;
    const raw = JSON.stringify({ version: 1, tasks, preferences });
    if (raw === lastSaved.current) return;
    try { localStorage.setItem(key, raw); lastSaved.current = raw; }
    catch { notify("Browser storage is unavailable. Keep this tab open; changes will not survive a reload."); }
  }, [tasks, preferences, ready]);

  useEffect(() => {
    document.documentElement.dataset.reducedMotion = String(preferences.reducedMotion);
    return () => { delete document.documentElement.dataset.reducedMotion; };
  }, [preferences.reducedMotion]);

  function saveTask(input: TaskInput, id?: string) {
    const error = validateTask(input);
    if (error) throw new Error(error);
    const task: Task = { ...input, title: input.title.trim(), id: id ?? crypto.randomUUID(), completed: tasks.find(t => t.id === id)?.completed ?? false };
    setTasks(current => id ? current.map(t => t.id === id ? task : t) : [...current, task]);
    notify(canPersist.current ? (id ? "Task updated." : "Task added to your workspace.") : "Task changed for this session only; saved data is unavailable.");
    return task;
  }

  function savePreferences(next: Preferences) {
    const error = validatePreferences(next);
    if (error) throw new Error(error);
    setPreferences(next); notify(canPersist.current ? "Preferences saved on this device." : "Preferences changed for this session only; saved data is unavailable.");
  }

  return <Context.Provider value={{ tasks, preferences, ready, notice, notify, saveTask, savePreferences,
    toggleTask: id => setTasks(current => current.map(t => t.id === id ? { ...t, completed: !t.completed } : t)),
    deleteTask: id => { setTasks(current => current.filter(t => t.id !== id)); notify("Task removed from this device."); },
  }}><div data-reduced-motion={preferences.reducedMotion}>{ready ? children : <p role="status">Opening your workspace…</p>}</div></Context.Provider>;
}

export function useWorkspace() {
  const value = useContext(Context);
  if (!value) throw new Error("WorkspaceProvider is missing");
  return value;
}
