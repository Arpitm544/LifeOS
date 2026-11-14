"use client";

import { useState, type FormEvent } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";

export function PreferencesForm() {
  const { preferences, savePreferences, reducedMotion, setReducedMotion } = useWorkspace();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget); setError(""); setBusy(true);
    try {
      await savePreferences({ timezone: String(data.get("timezone")).trim(), workStart: String(data.get("workStart")), workEnd: String(data.get("workEnd")),
        quietStart: String(data.get("quietStart")), quietEnd: String(data.get("quietEnd")), focusStart: String(data.get("focusStart")), focusEnd: String(data.get("focusEnd")),
        reminderLead: Number(data.get("reminderLead")), estimatePadding: data.has("estimatePadding") });
    } catch (e) { setError(readableError(e, "Could not save preferences.")); }
    finally { setBusy(false); }
  }
  const ranges = [["Working hours", "workStart", "workEnd", "The time LifeOS can plan work into"], ["Quiet hours", "quietStart", "quietEnd", "No reminders in this window · May span midnight"], ["Focus window", "focusStart", "focusEnd", "Your best hours for demanding work"]] as const;
  return <form className="preferences-form" onSubmit={submit}><div><h2>Your rhythm</h2><p>These boundaries shape every plan and reminder.</p></div>
    <label className="preference-row"><span className="eyebrow muted">Timezone</span><input name="timezone" required defaultValue={preferences.timezone} placeholder="Asia/Kolkata" /><small>IANA timezone · Used for Today, deadlines and reminders</small></label>
    {ranges.map(([label, start, end, source]) => <fieldset key={start} className="preference-row"><legend className="eyebrow muted">{label}</legend><div className="time-range"><label className="sr-only" htmlFor={start}>{label} start</label><input id={start} name={start} type="time" required defaultValue={preferences[start]} /><span aria-hidden="true">–</span><label className="sr-only" htmlFor={end}>{label} end</label><input id={end} name={end} type="time" required defaultValue={preferences[end]} /></div><small>{source}</small></fieldset>)}
    <label className="preference-row"><span className="eyebrow muted">Reminder lead (minutes)</span><input name="reminderLead" type="number" min={0} max={1440} step={1} required defaultValue={preferences.reminderLead} /><small>How early to nudge you before the latest time to start</small></label>
    <label className="toggle-row"><span><b>Pad my estimates</b><small>Plan with your measured effort factor per category.</small></span><input type="checkbox" name="estimatePadding" defaultChecked={preferences.estimatePadding} role="switch" /></label>
    <label className="toggle-row"><span><b>Reduce motion</b><small>Keep the orbit and transitions still. Saved on this device.</small></span><input type="checkbox" checked={reducedMotion} onChange={e => setReducedMotion(e.target.checked)} role="switch" /></label>
    {error ? <p role="alert" className="error-message">{error}</p> : null}<button className="button" type="submit" disabled={busy}>{busy ? "Saving…" : "Save preferences"} <span aria-hidden="true">↗</span></button>
  </form>;
}
