"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";
import { describeRule, formatEffort, routineRule, weekdays } from "@/lib/task-utils";
import type { Routine } from "@/lib/types";

/** Recurring commitments (class, gym) that the planner keeps free. */
export function Routines() {
  const { api, notify } = useWorkspace();
  const [routines, setRoutines] = useState<Routine[]>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState("");

  const load = useCallback(async () => {
    try { setRoutines(await api<Routine[]>("/api/preferences/routines")); setError(""); }
    catch (e) { setError(readableError(e, "Could not load routines.")); }
  }, [api]);
  useEffect(() => { load(); }, [load]);

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setBusy(true);
    const form = event.currentTarget; const data = new FormData(form);
    try {
      await api("/api/preferences/routines", { method: "POST", body: { title: String(data.get("title")).trim(), rrule: routineRule(data.getAll("days").map(String)),
        start_time: String(data.get("start")), duration_min: Number(data.get("duration")), movable: data.has("movable") } });
      form.reset(); notify("Routine added."); await load();
    } catch (e) { setError(readableError(e, "Could not add the routine.")); }
    finally { setBusy(false); }
  }

  async function remove(id: string) {
    if (busy) return;
    setError(""); setBusy(true);
    try { await api(`/api/preferences/routines/${id}?confirmed=true`, { method: "DELETE" }); }
    catch (e) { setError(readableError(e, "Could not remove the routine.")); setBusy(false); return; }
    setConfirm(""); setBusy(false); notify("Routine removed.");
    await load();
  }

  return <section className="panel routines" aria-labelledby="routines-title"><h2 id="routines-title">Routines</h2><p className="muted">Repeating commitments the planner works around.</p>
    {error ? <p className="error-message" role="alert">{error} <button className="text-button" onClick={load}>Retry</button></p> : null}
    {!routines ? error ? null : <p className="muted" role="status">Loading…</p> : routines.length ? <ul className="known-list">{routines.map(routine => <li key={routine.id}>
      <div><b>{routine.title}</b><small className="muted">{describeRule(routine.rrule)} · {routine.start_time} · {formatEffort(routine.duration_min)}{routine.movable ? " · Movable" : ""}</small></div>
      {confirm === routine.id ? <span className="button-row"><button className="text-button danger-text" disabled={busy} onClick={() => remove(routine.id)} aria-label={`Confirm removing ${routine.title}`}>Remove</button><button className="text-button" onClick={() => setConfirm("")}>Keep</button></span> : <button className="text-button" onClick={() => setConfirm(routine.id)} aria-label={`Remove ${routine.title}`}>Remove</button>}
    </li>)}</ul> : <p className="muted">No routines yet.</p>}
    <form className="routine-form task-form" onSubmit={add}>
      <label>Title<input name="title" required maxLength={120} placeholder="e.g. Gym" /></label>
      <fieldset className="day-picker"><legend>Days <span className="optional">(none = every day)</span></legend>{weekdays.map(([code, label]) => <label key={code} className="chip"><input type="checkbox" name="days" value={code} />{label}</label>)}</fieldset>
      <div className="routine-times"><label>Starts<input name="start" type="time" required defaultValue="18:00" /></label><label>Minutes<input name="duration" type="number" min={5} max={600} step={5} required defaultValue={60} /></label></div>
      <label className="inline-check"><input type="checkbox" name="movable" defaultChecked /> Can be moved when time is short</label>
      <button className="button secondary" disabled={busy}>{busy ? "Adding…" : "Add routine"}</button>
    </form>
  </section>;
}
