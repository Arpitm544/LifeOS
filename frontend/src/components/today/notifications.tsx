"use client";

import { useCallback, useEffect, useState } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";
import { formatDeadline } from "@/lib/task-utils";
import type { Reminder } from "@/lib/types";

/** Notification centre: reminders that fired or are due in the next 24 hours. */
export function Notifications({ onChanged }: { onChanged?: () => void }) {
  const { api, preferences, reloadTasks } = useWorkspace();
  const [items, setItems] = useState<Reminder[]>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    try { setItems(await api<Reminder[]>("/api/reminders?limit=20")); setError(""); }
    catch (e) { setError(readableError(e, "Could not load notifications.")); }
  }, [api]);
  useEffect(() => { load(); }, [load]);

  async function act(reminder: Reminder, action: "done" | "snooze_15") {
    setBusy(reminder.id); setError("");
    try {
      await api(`/api/reminders/${reminder.id}/action`, { method: "POST", body: { action } });
      await load();
      if (action === "done") { onChanged?.(); await reloadTasks(); }
    } catch (e) { setError(readableError(e)); }
    finally { setBusy(""); }
  }

  const visible = (items ?? []).filter(item => item.status !== "acted" && item.status !== "cancelled").slice(0, 5);
  return <section className="panel notifications" aria-labelledby="notifications-title"><p className="eyebrow muted" id="notifications-title">Notifications</p>
    {error ? <p className="error-message" role="alert">{error} <button className="text-button" onClick={load}>Retry</button></p> : null}
    {!items ? error ? null : <p className="muted" role="status">Loading…</p> : visible.length ? <ul>{visible.map(item => <li key={item.id}>
      <p>{item.message ?? "Reminder"}</p><small className="muted">{formatDeadline(item.fire_at, preferences.timezone)} · {item.status}</small>
      {item.item_type === "task" && item.status !== "missed" ? <div className="button-row"><button className="text-button" disabled={busy === item.id} onClick={() => act(item, "done")}>Done</button><button className="text-button" disabled={busy === item.id} onClick={() => act(item, "snooze_15")}>Snooze 15 min</button></div> : null}
    </li>)}</ul> : <p className="muted">No reminders right now.</p>}
  </section>;
}
