import { categories } from "./types.ts";
import type { Preferences, Task, TaskInput } from "./types.ts";

export function validateTask(task: TaskInput): string | null {
  if (!task.title.trim() || task.title.trim().length > 120) return "Enter a title between 1 and 120 characters.";
  if (!Number.isInteger(task.effort) || task.effort < 5 || task.effort > 600) return "Effort must be 5–600 whole minutes.";
  if (!Number.isInteger(task.importance) || task.importance < 1 || task.importance > 5) return "Importance must be between 1 and 5.";
  if (!categories.includes(task.category)) return "Choose a valid category.";
  if (task.deadline !== null) {
    if (typeof task.deadline !== "string" || !/^\d{4}-\d{2}-\d{2}(?:T|$)/.test(task.deadline) || !Number.isFinite(Date.parse(task.deadline))) return "Choose a valid deadline.";
    const date = task.deadline.slice(0, 10);
    if (new Date(`${date}T00:00:00Z`).toISOString().slice(0, 10) !== date) return "Choose a valid deadline.";
  }
  return null;
}

export function priorityBand(importance: number) { return importance >= 4 ? "P1" : importance >= 3 ? "P2" : "P3"; }

export function formatEffort(minutes: number) {
  return minutes >= 60 ? `${Math.floor(minutes / 60)}h${minutes % 60 ? ` ${minutes % 60}m` : ""}` : `${minutes} min`;
}

export function formatDeadline(value: string | null, timezone: string) {
  if (!value) return "No deadline";
  return new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: timezone }).format(new Date(value));
}

const dateFormatters = new Map<string, Intl.DateTimeFormat>();
export function localDateKey(value: string | Date, timezone: string) {
  let formatter = dateFormatters.get(timezone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: timezone });
    dateFormatters.set(timezone, formatter);
  }
  return formatter.format(new Date(value));
}

export function compareDeadlines(a: Task, b: Task) {
  if (!a.deadline) return b.deadline ? 1 : 0;
  if (!b.deadline) return -1;
  return Date.parse(a.deadline) - Date.parse(b.deadline);
}

export type TaskFilter = "all" | "today" | "upcoming" | "completed";
export function filterTasks(tasks: Task[], filter: TaskFilter, query: string, timezone: string, now = new Date()) {
  const today = localDateKey(now, timezone);
  return tasks.filter(task => {
    if (!task.title.toLowerCase().includes(query.trim().toLowerCase())) return false;
    if (filter === "completed") return task.completed;
    if (task.completed) return false;
    if (filter === "today") return !!task.deadline && localDateKey(task.deadline, timezone) <= today;
    if (filter === "upcoming") return !!task.deadline && localDateKey(task.deadline, timezone) > today;
    return true;
  });
}

export function validatePreferences(p: Preferences): string | null {
  if (!p.name.trim() || p.name.length > 60) return "Enter a name between 1 and 60 characters.";
  try { new Intl.DateTimeFormat("en", { timeZone: p.timezone }); } catch { return "Enter a valid IANA timezone, such as Asia/Kolkata."; }
  const times = [p.workStart, p.workEnd, p.quietStart, p.quietEnd, p.focusStart, p.focusEnd];
  if (times.some(t => !/^([01]\d|2[0-3]):[0-5]\d$/.test(t))) return "Enter valid times for every preference.";
  if (p.workStart >= p.workEnd) return "Working hours must end after they start.";
  if (p.focusStart >= p.focusEnd) return "Focus hours must end after they start.";
  if (p.focusStart < p.workStart || p.focusEnd > p.workEnd) return "Focus hours must fit within working hours.";
  if (p.quietStart === p.quietEnd) return "Quiet hours must have different start and end times.";
  return null;
}

export function parseWorkspace(raw: string): { tasks: Task[]; preferences: Preferences } {
  const data = JSON.parse(raw);
  if (data.version !== 1 || !Array.isArray(data.tasks) || data.tasks.some((t: Task) => !t || typeof t.title !== "string" || typeof t.id !== "string" || typeof t.completed !== "boolean" || validateTask(t))) throw new Error("Invalid saved tasks");
  if (data.tasks.some((t: Task) => !t.id) || new Set(data.tasks.map((t: Task) => t.id)).size !== data.tasks.length) throw new Error("Invalid saved task identities");
  const p = data.preferences;
  if (!p || typeof p.name !== "string" || typeof p.timezone !== "string" || [p.workStart, p.workEnd, p.quietStart, p.quietEnd, p.focusStart, p.focusEnd].some(t => typeof t !== "string") || [p.protectedEvenings, p.estimatePadding, p.reducedMotion].some(b => typeof b !== "boolean") || validatePreferences(p)) throw new Error("Invalid saved preferences");
  return { tasks: data.tasks, preferences: p };
}
