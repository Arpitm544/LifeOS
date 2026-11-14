"use client";

import { useState, type FormEvent } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";
import { formatEffort } from "@/lib/task-utils";
import type { EffortAnswer } from "@/lib/types";

const answers: [EffortAnswer, string][] = [["less", "Less"], ["about_right", "About right"], ["more", "More"]];

/** One-tap "How long did it take?" after completing a task. */
export function EffortPrompt({ taskId, estimate, onDone }: { taskId: string; estimate?: number; onDone?: () => void }) {
  const { recordEffort } = useWorkspace();
  const [busy, setBusy] = useState(false);
  const [custom, setCustom] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function send(answer: EffortAnswer, minutes?: number) {
    setBusy(true); setError("");
    try { await recordEffort(taskId, answer, minutes); setDone(true); onDone?.(); }
    catch (e) { setError(readableError(e, "Could not save that.")); }
    finally { setBusy(false); }
  }
  function submitCustom(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const minutes = Number(new FormData(event.currentTarget).get("minutes"));
    if (!Number.isInteger(minutes) || minutes < 1 || minutes > 1440) { setError("Enter 1–1440 whole minutes."); return; }
    send("custom", minutes);
  }

  if (done) return <p className="effort-prompt muted" role="status">Saved. Thanks.</p>;
  return <div className="effort-prompt" role="group" aria-label="How long did it take?">
    <p><b>How long did it take?</b>{estimate ? <span className="muted"> Estimate: {formatEffort(estimate)}</span> : null}</p>
    <div className="chip-row">{answers.map(([answer, label]) => <button key={answer} type="button" className="chip" disabled={busy} onClick={() => send(answer)}>{label}</button>)}
      <button type="button" className={`chip ${custom ? "selected" : ""}`} disabled={busy} aria-expanded={custom} onClick={() => setCustom(value => !value)}>Exact minutes</button></div>
    {custom ? <form className="custom-effort" onSubmit={submitCustom}><label className="sr-only" htmlFor={`effort-${taskId}`}>Minutes it took</label><input id={`effort-${taskId}`} name="minutes" type="number" min={1} max={1440} step={1} required placeholder="Minutes" /><button className="button secondary" disabled={busy}>Save</button></form> : null}
    {error ? <p className="error-message" role="alert">{error}</p> : null}
  </div>;
}
