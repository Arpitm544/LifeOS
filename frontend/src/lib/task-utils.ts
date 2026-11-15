import { categories } from "./types.ts";
import type { PreferenceRow, Preferences, Task, TaskInput } from "./types.ts";

export function validateTask(task: TaskInput): string | null {
  if (!task.title.trim() || task.title.trim().length > 120) return "Enter a title between 1 and 120 characters.";
  if (!Number.isInteger(task.effort_est_min) || task.effort_est_min < 5 || task.effort_est_min > 600) return "Effort must be 5–600 whole minutes.";
  if (!Number.isInteger(task.importance) || task.importance < 1 || task.importance > 5) return "Importance must be between 1 and 5.";
  if (!categories.includes(task.category)) return "Choose a valid category.";
  if (task.deadline_at !== null) {
    if (typeof task.deadline_at !== "string" || !/^\d{4}-\d{2}-\d{2}(?:T|$)/.test(task.deadline_at) || !Number.isFinite(Date.parse(task.deadline_at))) return "Choose a valid deadline.";
    const date = task.deadline_at.slice(0, 10);
    if (new Date(`${date}T00:00:00Z`).toISOString().slice(0, 10) !== date) return "Choose a valid deadline.";
  }
  if (task.notes && task.notes.length > 2000) return "Notes must be 2000 characters or fewer.";
  return null;
}

export function formatEffort(minutes: number) {
  return minutes >= 60 ? `${Math.floor(minutes / 60)}h${minutes % 60 ? ` ${minutes % 60}m` : ""}` : `${minutes} min`;
}

export function formatHours(minutes: number) {
  const hours = Math.round((minutes / 60) * 10) / 10;
  return `${hours} h`;
}

export function formatDeadline(value: string | null, timezone: string) {
  if (!value) return "No deadline";
  return new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: timezone }).format(new Date(value));
}

export function formatClock(value: string, timezone: string) {
  return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: timezone }).format(new Date(value));
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
  if (!a.deadline_at) return b.deadline_at ? 1 : 0;
  if (!b.deadline_at) return -1;
  return Date.parse(a.deadline_at) - Date.parse(b.deadline_at);
}

/** Pinned first, then the backend priority score, then the deadline. */
export function comparePriority(a: Task, b: Task) {
  if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
  if (b.priority_score !== a.priority_score) return b.priority_score - a.priority_score;
  return compareDeadlines(a, b);
}

export const isActive = (task: Task) => task.status === "open" || task.status === "blocked";

export type TaskFilter = "all" | "today" | "upcoming" | "completed";
export function filterTasks(tasks: Task[], filter: TaskFilter, query: string, timezone: string, now = new Date()) {
  const today = localDateKey(now, timezone);
  return tasks.filter(task => {
    if (task.status === "dropped") return false;
    if (!task.title.toLowerCase().includes(query.trim().toLowerCase())) return false;
    if (filter === "completed") return task.status === "done";
    if (task.status === "done") return false;
    if (filter === "today") return !!task.deadline_at && localDateKey(task.deadline_at, timezone) <= today;
    if (filter === "upcoming") return !!task.deadline_at && localDateKey(task.deadline_at, timezone) > today;
    return true;
  });
}

const timePattern = /^([01]\d|2[0-3]):[0-5]\d$/;

export function validatePreferences(p: Preferences): string | null {
  try { new Intl.DateTimeFormat("en", { timeZone: p.timezone }); } catch { return "Enter a valid IANA timezone, such as Asia/Kolkata."; }
  const times = [p.workStart, p.workEnd, p.quietStart, p.quietEnd, p.focusStart, p.focusEnd];
  if (times.some(t => !timePattern.test(t))) return "Enter valid times for every preference.";
  if (p.workStart >= p.workEnd) return "Working hours must end after they start.";
  if (p.focusStart >= p.focusEnd) return "Focus hours must end after they start.";
  if (p.quietStart === p.quietEnd) return "Quiet hours must have different start and end times.";
  if (!Number.isInteger(p.reminderLead) || p.reminderLead < 0 || p.reminderLead > 1440) return "Reminder lead must be 0–1440 whole minutes.";
  return null;
}

export function browserTimezone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; } catch { return "UTC"; }
}

/** Flatten active preference rows into the Profile form, using the backend defaults where a key is unset. */
export function preferencesFromRows(rows: PreferenceRow[], fallbackTimezone = "UTC"): Preferences {
  const value = (key: string) => rows.find(row => row.key === key && row.status === "active")?.value ?? {};
  const str = (input: unknown, fallback: string) => typeof input === "string" && input ? input : fallback;
  const work = value("work_hours"), quiet = value("quiet_hours"), focus = value("focus_windows");
  const windows = Array.isArray(focus.windows) ? focus.windows as unknown[] : [];
  const first = Array.isArray(windows[0]) ? windows[0] as unknown[] : [];
  const lead = value("reminder_lead").minutes;
  return {
    timezone: str(value("timezone").name, fallbackTimezone),
    workStart: str(work.start, "09:00"), workEnd: str(work.end, "18:00"),
    quietStart: str(quiet.start, "22:30"), quietEnd: str(quiet.end, "07:30"),
    focusStart: str(first[0], "09:00"), focusEnd: str(first[1], "11:00"),
    reminderLead: typeof lead === "number" ? lead : 60,
    estimatePadding: value("estimate_padding").enabled === true,
  };
}

/** The `POST /api/preferences {key, value}` calls needed to go from `before` to `after`. */
export function preferenceUpdates(before: Preferences, after: Preferences) {
  const updates: { key: string; value: Record<string, unknown> }[] = [];
  const add = (key: string, changed: boolean, value: Record<string, unknown>) => { if (changed) updates.push({ key, value }); };
  add("timezone", before.timezone !== after.timezone, { name: after.timezone });
  add("work_hours", before.workStart !== after.workStart || before.workEnd !== after.workEnd, { start: after.workStart, end: after.workEnd });
  add("quiet_hours", before.quietStart !== after.quietStart || before.quietEnd !== after.quietEnd, { start: after.quietStart, end: after.quietEnd });
  add("focus_windows", before.focusStart !== after.focusStart || before.focusEnd !== after.focusEnd, { windows: [[after.focusStart, after.focusEnd]] });
  add("reminder_lead", before.reminderLead !== after.reminderLead, { minutes: after.reminderLead });
  add("estimate_padding", before.estimatePadding !== after.estimatePadding, { enabled: after.estimatePadding });
  return updates;
}

const preferenceLabels: Record<string, string> = {
  timezone: "Timezone", work_hours: "Working hours", quiet_hours: "Quiet hours", focus_windows: "Focus windows",
  reminder_lead: "Reminder lead", estimate_padding: "Estimate padding", work_hours_overrides: "Extended working days",
  onboarding: "First-run setup",
};

/** Human label and value for one preference row ("What LifeOS knows about you"). */
export function describePreference(row: Pick<PreferenceRow, "key" | "value">): { label: string; value: string } {
  const v = row.value as Record<string, unknown>;
  const label = preferenceLabels[row.key] ?? row.key.replace(/_/g, " ");
  if (row.key === "timezone") return { label, value: String(v.name ?? "") };
  if (row.key === "work_hours" || row.key === "quiet_hours") return { label, value: `${v.start}–${v.end}` };
  if (row.key === "focus_windows" && Array.isArray(v.windows)) return { label, value: (v.windows as string[][]).map(([s, e]) => `${s}–${e}`).join(", ") || "None" };
  if (row.key === "reminder_lead") return { label, value: `${v.minutes} min before the latest start` };
  if (row.key === "estimate_padding") return { label, value: v.enabled ? "On" : "Off" };
  if (row.key === "onboarding") return { label, value: v.completed ? `Done${typeof v.focus_period === "string" ? ` · focuses best in the ${v.focus_period}` : ""}` : "Not finished" };
  if (row.key === "work_hours_overrides" && v.dates && typeof v.dates === "object") {
    const entries = Object.entries(v.dates as Record<string, { start: string; end: string }>);
    return { label, value: entries.length ? entries.map(([day, h]) => `${day} ${h.start}–${h.end}`).join(", ") : "None" };
  }
  return { label, value: JSON.stringify(row.value) };
}

export const weekdays = [["MO", "Mon"], ["TU", "Tue"], ["WE", "Wed"], ["TH", "Thu"], ["FR", "Fri"], ["SA", "Sat"], ["SU", "Sun"]] as const;

/** Build an RFC 5545 rule for a routine: every day, or weekly on the chosen days. */
export function routineRule(days: string[]) {
  const order = weekdays.map(([code]) => code as string);
  const picked = order.filter(code => days.includes(code));
  return picked.length === 0 || picked.length === 7 ? "FREQ=DAILY" : `FREQ=WEEKLY;BYDAY=${picked.join(",")}`;
}

export function describeRule(rule: string) {
  const parts = Object.fromEntries(rule.replace(/^RRULE:/, "").split(";").map(part => part.split("=")));
  if (parts.FREQ === "DAILY") return "Every day";
  if (parts.FREQ === "WEEKLY" && parts.BYDAY) {
    const names = String(parts.BYDAY).split(",").map(code => weekdays.find(([c]) => c === code)?.[1] ?? code);
    return names.join(", ");
  }
  return String(parts.FREQ ?? rule).toLowerCase().replace(/^\w/, c => c.toUpperCase());
}

export type FocusPeriod = "morning" | "afternoon" | "evening" | "night";
/** Seed focus window for the onboarding answer "When do you focus best?" (PRD 5.1), until real data exists. */
export const focusPeriods: Record<FocusPeriod, { label: string; window: [string, string] }> = {
  morning: { label: "Morning", window: ["08:00", "10:00"] },
  afternoon: { label: "Afternoon", window: ["13:00", "15:00"] },
  evening: { label: "Evening", window: ["17:00", "19:00"] },
  night: { label: "Night", window: ["20:00", "22:00"] },
};

/** Whether first-run onboarding should open: never finished, and the user has not set their own working hours. */
export function needsOnboarding(rows: Pick<PreferenceRow, "key" | "source" | "value">[]) {
  const done = rows.find(row => row.key === "onboarding");
  if (done) return done.value?.completed !== true;
  return !rows.some(row => row.key === "work_hours" && row.source === "stated");
}
