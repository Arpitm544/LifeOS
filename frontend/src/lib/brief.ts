export type NudgeAction =
  | { type: "open_conflict"; conflict_id: string; label: string }
  | { type: "reschedule"; task_id: string; deadline_at: string; label: string }
  | { type: "plan"; label: string };
export type Nudge = { id: string; kind: "conflict" | "overdue" | "unplanned" | "plan"; tone: "risk" | "suggest"; title: string; detail: string; action: NudgeAction };
export type Brief = {
  date: string; timezone: string; headline: string; lines: string[]; spoken: string; nudges: Nudge[];
  language: string; translated: boolean;
  counts: { due_today: number; overdue: number; at_risk: number; focus_min: number; events: number };
};

const storageKey = "lifeos.dismissed-nudges";

export function briefPath(language: string | null, firstName: string) {
  const query = new URLSearchParams();
  if (language && language !== "en") query.set("language", language);
  const name = firstName.trim().slice(0, 40);
  if (name) query.set("name", name);
  const text = query.toString();
  return `/api/brief${text ? `?${text}` : ""}`;
}

/** Dismissals last for the brief's day only, so tomorrow's nudges always show. */
export function visibleNudges(brief: Brief, dismissed: Record<string, string[]>) {
  const hidden = new Set(dismissed[brief.date] ?? []);
  return brief.nudges.filter(nudge => !hidden.has(nudge.id));
}

export function dismiss(dismissed: Record<string, string[]>, date: string, id: string): Record<string, string[]> {
  return { [date]: [...new Set([...(dismissed[date] ?? []), id])] };
}

export function readDismissed(): Record<string, string[]> {
  try {
    const value = JSON.parse(window.localStorage.getItem(storageKey) ?? "{}");
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  } catch { return {}; }
}

export function saveDismissed(value: Record<string, string[]>) {
  try { window.localStorage.setItem(storageKey, JSON.stringify(value)); } catch { /* per-device convenience only */ }
}
