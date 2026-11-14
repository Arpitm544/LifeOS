"use client";

import { useState, type FormEvent } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";

export function PreferencesForm() {
  const { preferences, savePreferences } = useWorkspace();
  const [error, setError] = useState("");
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget); setError("");
    try {
      savePreferences({ ...preferences, name: String(data.get("name")).trim(), timezone: String(data.get("timezone")).trim(), workStart: String(data.get("workStart")), workEnd: String(data.get("workEnd")), quietStart: String(data.get("quietStart")), quietEnd: String(data.get("quietEnd")), focusStart: String(data.get("focusStart")), focusEnd: String(data.get("focusEnd")), protectedEvenings: data.has("protectedEvenings"), reducedMotion: data.has("reducedMotion") });
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save preferences."); }
  }
  const ranges = [["Working hours", "workStart", "workEnd", "Same-day window; overnight shifts are not supported yet"], ["Quiet hours", "quietStart", "quietEnd", "You chose this · May span midnight"], ["Focus window", "focusStart", "focusEnd", "Same-day window within working hours; saved with preferences"]] as const;
  return <form className="preferences-form" onSubmit={submit}><div><h2>Your rhythm</h2><p>Save these boundaries for future planning.</p></div>
    <label className="preference-row"><span className="eyebrow muted">Your name</span><input name="name" required maxLength={60} defaultValue={preferences.name} /><small>Personalization on this device</small></label>
    <label className="preference-row"><span className="eyebrow muted">Timezone</span><input name="timezone" required defaultValue={preferences.timezone} placeholder="Asia/Kolkata" /><small>IANA timezone · Used to display your deadlines</small></label>
    {ranges.map(([label, start, end, source]) => <fieldset key={start} className="preference-row"><legend className="eyebrow muted">{label}</legend><div className="time-range"><label className="sr-only" htmlFor={start}>{label} start</label><input id={start} name={start} type="time" required defaultValue={preferences[start]} /><span aria-hidden="true">–</span><label className="sr-only" htmlFor={end}>{label} end</label><input id={end} name={end} type="time" required defaultValue={preferences[end]} /></div><small>{source}</small></fieldset>)}
    <label className="toggle-row"><span><b>Protected evenings</b><small>Saved for future planning; scheduling is not connected yet.</small></span><input type="checkbox" name="protectedEvenings" defaultChecked={preferences.protectedEvenings} role="switch" /></label>
    <label className="toggle-row"><span><b>Reduce motion</b><small>Keep the orbit and transitions still.</small></span><input type="checkbox" name="reducedMotion" defaultChecked={preferences.reducedMotion} role="switch" /></label>
    {error ? <p role="alert" className="error-message">{error}</p> : null}<button className="button" type="submit">Save preferences <span aria-hidden="true">↗</span></button>
  </form>;
}
