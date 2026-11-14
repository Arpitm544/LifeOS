"use client";

import { AlertTriangle, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";
import { dismiss, readDismissed, saveDismissed, visibleNudges, type Brief, type Nudge } from "@/lib/brief";

/** Proactive suggestions from the morning brief, each with one action LifeOS can take for you. */
export function Nudges({ brief, onOpenConflict, onChanged }: { brief: Brief; onOpenConflict: (id: string) => void; onChanged: () => Promise<void> | void }) {
  const { api, reloadTasks, notify } = useWorkspace();
  const [dismissed, setDismissed] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { setDismissed(readDismissed()); }, []);

  function hide(nudge: Nudge) {
    const next = dismiss(dismissed, brief.date, nudge.id);
    setDismissed(next); saveDismissed(next);
  }

  async function act(nudge: Nudge) {
    const action = nudge.action;
    if (action.type === "open_conflict") { onOpenConflict(action.conflict_id); return; }
    setBusy(nudge.id); setError("");
    try {
      if (action.type === "reschedule") {
        await api(`/api/tasks/${encodeURIComponent(action.task_id)}`, { method: "PATCH", body: { deadline_at: action.deadline_at } });
      }
      const result = await api<{ blocks: unknown[] }>("/api/plan/rebuild?days=7", { method: "POST" });
      notify(action.type === "reschedule" ? `Moved to tomorrow and replanned (${result.blocks.length} blocks).` : `Planned ${result.blocks.length} focus block${result.blocks.length === 1 ? "" : "s"}.`);
      await Promise.all([reloadTasks().catch(() => undefined), onChanged()]);
    } catch (e) { setError(readableError(e, "LifeOS could not do that. Please try again.")); }
    finally { setBusy(""); }
  }

  const items = visibleNudges(brief, dismissed);
  if (!items.length && !error) return null;
  return <section className="panel nudges" aria-labelledby="nudges-title">
    <div className="section-heading"><div><h2 id="nudges-title">LifeOS suggests</h2><p>Spotted while checking your plan. One tap and it’s handled.</p></div></div>
    {error ? <p className="error-message" role="alert">{error}</p> : null}
    <ul>{items.map(nudge => <li key={nudge.id} className={`nudge ${nudge.tone}`}>
      <span className="nudge-icon" aria-hidden="true">{nudge.tone === "risk" ? <AlertTriangle size={18} /> : <Sparkles size={18} />}</span>
      <div><p className="nudge-title">{nudge.title}</p><p className="nudge-detail">{nudge.detail}</p>
        <div className="button-row"><button className={nudge.tone === "risk" ? "button" : "button secondary"} onClick={() => act(nudge)} disabled={!!busy}>{busy === nudge.id ? "Working…" : nudge.action.label}</button></div></div>
      <button className="nudge-dismiss" onClick={() => hide(nudge)} aria-label={`Dismiss: ${nudge.title}`} disabled={busy === nudge.id}><X size={16} /></button>
    </li>)}</ul>
  </section>;
}
