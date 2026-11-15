"use client";

import { MoonStar } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";
import { formatClock } from "@/lib/task-utils";
import type { Checkin, CheckinResult } from "@/lib/types";

const DISMISS_KEY = "lifeos:checkin-dismissed";

/** End-of-day check-in (PRD 5.6): from 21:00, unfinished blocks with "Move to tomorrow" (all at once) or "Drop". */
export function EveningCheckin({ timezone }: { timezone: string }) {
  const { api, notify, reloadTasks } = useWorkspace();
  const [data, setData] = useState<Checkin>();
  const [busy, setBusy] = useState("");
  const [confirmDrop, setConfirmDrop] = useState("");
  const [error, setError] = useState("");
  const [dismissed, setDismissed] = useState("");
  useEffect(() => { try { setDismissed(window.sessionStorage.getItem(DISMISS_KEY) ?? ""); } catch { /* storage blocked */ } }, []);

  const load = useCallback(async () => {
    try { setData(await api<Checkin>("/api/today/checkin")); } catch { setData(undefined); }  // optional: Today works without it
  }, [api]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const refresh = () => { load(); };
    window.addEventListener("lifeos:changed", refresh);
    return () => window.removeEventListener("lifeos:changed", refresh);
  }, [load]);

  async function run(action: "move_to_tomorrow" | "drop", blockIds: string[]) {
    if (busy) return;
    setBusy(action === "drop" ? blockIds[0] : action); setError("");
    try {
      const result = await api<CheckinResult>("/api/today/checkin", { method: "POST", body: { action, block_ids: blockIds } });
      if (result.action === "move_to_tomorrow") {
        notify(result.unplaced_task_ids.length ? `Moved. ${result.unplaced_task_ids.length} task(s) did not fit tomorrow; check Capacity Guard.` : `Moved ${result.moved} block${result.moved === 1 ? "" : "s"} to tomorrow.`);
      } else notify("Dropped. It is off your list and your plan.");
      setConfirmDrop("");
      reloadTasks().catch(() => undefined);  // statuses and priorities changed
      // Today, the Week view and this card all refresh on this event.
      window.dispatchEvent(new Event("lifeos:changed"));
    } catch (e) { setError(readableError(e, "Could not update your plan.")); }
    finally { setBusy(""); }
  }

  function later() {
    if (!data) return;
    setDismissed(data.date);
    try { window.sessionStorage.setItem(DISMISS_KEY, data.date); } catch { /* storage blocked */ }
  }

  if (!data?.due || dismissed === data.date) return null;
  return <section className="panel checkin" aria-labelledby="checkin-title">
    <div className="section-heading"><div><h2 id="checkin-title"><MoonStar size={18} aria-hidden="true" /> Wrapping up today</h2>
      <p>{data.blocks.length} focus block{data.blocks.length === 1 ? "" : "s"} did not get done. Move them to tomorrow, or drop what no longer matters.</p></div></div>
    <ul className="checkin-list">{data.blocks.map(block => <li key={block.id}>
      <span><b>{block.title}</b> <small className="muted">{formatClock(block.start_at, timezone)}–{formatClock(block.end_at, timezone)}</small></span>
      {confirmDrop === block.id
        ? <span className="button-row"><button className="text-button danger-text" disabled={!!busy} onClick={() => run("drop", [block.id])} aria-label={`Confirm dropping ${block.title}`}>Drop task</button><button className="text-button" onClick={() => setConfirmDrop("")}>Keep</button></span>
        : <button className="text-button" disabled={!!busy} onClick={() => setConfirmDrop(block.id)} aria-label={`Drop ${block.title}`}>Drop</button>}
    </li>)}</ul>
    {error ? <p className="error-message" role="alert">{error}</p> : null}
    <div className="button-row"><button className="button" disabled={!!busy} onClick={() => run("move_to_tomorrow", data.blocks.map(block => block.id))}>{busy === "move_to_tomorrow" ? "Moving…" : "Move all to tomorrow"} <span aria-hidden="true">→</span></button>
      <button className="text-button" onClick={later}>Not now</button></div>
  </section>;
}
