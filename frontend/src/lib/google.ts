export type GoogleStatus = { configured: boolean; connected: boolean; last_synced_at: string | null; last_error: string | null; needs_reconnect: boolean };
export type GoogleSyncResult = { created: number; updated: number; removed: number; truncated: boolean; last_synced_at: string; note: string | null };

/** What the page shows after Google sends the browser back with `?google=<result>`. */
export function googleReturnMessage(result: string | null): { kind: "success" | "error"; text: string } | null {
  switch (result) {
    case "connected": return { kind: "success", text: "Google Calendar is connected and your events are synced." };
    case "connected_sync_failed": return { kind: "error", text: "Google Calendar is connected, but the first sync failed. Try Sync now." };
    case "denied": return { kind: "error", text: "Google Calendar was not connected because access was declined." };
    case "expired": return { kind: "error", text: "That Google sign-in link expired. Start the connection again." };
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
