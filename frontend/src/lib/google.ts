import { formatClock, localDateKey } from "./task-utils.ts";

export type GoogleStatus = { configured: boolean; connected: boolean; last_synced_at: string | null; last_error: string | null; needs_reconnect: boolean };
export type GoogleSyncResult = { created: number; updated: number; removed: number; truncated: boolean; last_synced_at: string; note: string | null };

/** What the page shows after Google sends the browser back with `?google=<result>`. */
export function googleReturnMessage(result: string | null): { kind: "success" | "error"; text: string } | null {
  switch (result) {
    case "connected": return { kind: "success", text: "Google Calendar is connected and your events are synced." };
    case "connected_sync_failed": return { kind: "error", text: "Google Calendar is connected, but the first sync failed. Try Sync now." };
    case "denied": return { kind: "error", text: "Google Calendar was not connected because access was declined." };
    case "expired": return { kind: "error", text: "That Google sign-in link expired. Start the connection again." };
    case "no_scope": return { kind: "error", text: "Calendar access wasn't granted. Connect again and tick \"See and download any calendar you can access\" on Google's screen." };
    case "not_configured": return { kind: "error", text: "Google rejected this server's client ID or secret. Check the backend's Google settings." };
    case "error": return { kind: "error", text: "Google Calendar could not be connected. Please try again." };
    default: return null;
  }
}

export function syncSummary(result: Pick<GoogleSyncResult, "created" | "updated" | "removed" | "truncated" | "note">): string {
  const parts: string[] = [];
  if (result.created) parts.push(`${result.created} added`);
  if (result.updated) parts.push(`${result.updated} updated`);
  if (result.removed) parts.push(`${result.removed} removed`);
  let text = parts.length ? `Synced: ${parts.join(", ")}.` : "Already up to date.";
  if (result.truncated) text += " Only the first 1,000 events were read.";
  if (result.note) text += ` ${result.note}`;
  return text;
}

export function lastSyncedText(value: string | null, now = Date.now()): string {
  if (!value) return "Not synced yet";
  const minutes = Math.max(0, Math.round((now - new Date(value).getTime()) / 60000));
  if (minutes < 1) return "Synced just now";
  if (minutes < 60) return `Synced ${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `Synced ${hours} h ago`;
  return `Synced ${Math.round(hours / 24)} d ago`;
}

export type CalendarEvent = { id: string; title: string; start_at: string; end_at: string; location: string | null; source: string };
export type AgendaDay = { key: string; label: string; weekday: string; day: string; month: string; events: CalendarEvent[] };

const DAY_MS = 86_400_000;

/** Upcoming events grouped by local day: anything still running now through `horizonDays` ahead. */
export function agendaDays(events: CalendarEvent[], timezone: string, now = Date.now(), horizonDays = 14): AgendaDay[] {
  const todayKey = localDateKey(new Date(now), timezone);
  const tomorrowKey = localDateKey(new Date(now + DAY_MS), timezone);
  const until = now + horizonDays * DAY_MS;
  const parts = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "short", timeZone: timezone });
  const days = new Map<string, AgendaDay>();
  const upcoming = events
    .filter(event => Date.parse(event.end_at) > now && Date.parse(event.start_at) < until)
    .sort((a, b) => Date.parse(a.start_at) - Date.parse(b.start_at));
  for (const event of upcoming) {
    // An event already under way (e.g. started yesterday) is shown under today.
    const startKey = localDateKey(event.start_at, timezone);
    const key = startKey < todayKey ? todayKey : startKey;
    let day = days.get(key);
    if (!day) {
      const bits = Object.fromEntries(parts.formatToParts(new Date(`${key}T12:00:00Z`)).map(part => [part.type, part.value]));
      const label = key === todayKey ? "Today" : key === tomorrowKey ? "Tomorrow" : bits.weekday;
      day = { key, label, weekday: String(bits.weekday).slice(0, 3), day: bits.day, month: bits.month, events: [] };
      days.set(key, day);
    }
    day.events.push(event);
  }
  return [...days.values()];
}

/** "09:30–10:15", or "All day" for events that run whole local days. */
export function eventTimeText(event: Pick<CalendarEvent, "start_at" | "end_at">, timezone: string): string {
  const start = formatClock(event.start_at, timezone);
  const length = Date.parse(event.end_at) - Date.parse(event.start_at);
  if (start === "00:00" && length >= DAY_MS && length % DAY_MS === 0) return length === DAY_MS ? "All day" : `${length / DAY_MS} days`;
  return `${start}–${formatClock(event.end_at, timezone)}`;
}
