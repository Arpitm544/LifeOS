"use client";

import { useState, type FormEvent } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";

export function Welcome() {
  const { preferences, completeOnboarding } = useWorkspace();
  const [error, setError] = useState("");
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setError("");
    try {
      completeOnboarding({ ...preferences, name: String(data.get("name") || "").trim(), timezone: String(data.get("timezone") || "").trim(), focusStart: String(data.get("focusStart")), focusEnd: String(data.get("focusEnd")) }, String(data.get("title") || ""));
    } catch (e) { setError(e instanceof Error ? e.message : "Could not set up your workspace."); }
  }
  return <section className="panel welcome" aria-labelledby="welcome-title"><p className="eyebrow blue">A fresh start</p><h1 id="welcome-title">Make a little space for you.</h1><p>A name, a focus window, and one small next step. You can change everything later in Profile.</p>
    <form className="task-form" onSubmit={submit}>
      <label>Your name<input name="name" required maxLength={60} autoComplete="given-name" defaultValue={["Demo User", "You"].includes(preferences.name) ? "" : preferences.name} placeholder="What should we call you?" /></label>
      <label>Your timezone<input name="timezone" required defaultValue={Intl.DateTimeFormat().resolvedOptions().timeZone} placeholder="Asia/Kolkata" /><small>Used to decide what’s due today.</small></label>
      <fieldset className="welcome-focus"><legend>When do you like to focus?</legend><div><label>From<input name="focusStart" type="time" required defaultValue={preferences.focusStart} /></label><label>Until<input name="focusEnd" type="time" required defaultValue={preferences.focusEnd} /></label></div><small>Choose a window within your working hours ({preferences.workStart}–{preferences.workEnd}).</small></fieldset>
      <label>Your first task<input name="title" required maxLength={120} placeholder="One small thing you’d like to do" /><small>No deadline yet · 30-minute estimate, editable in Tasks.</small></label>
      {error ? <p className="error-message" role="alert">{error}</p> : null}
      <div className="button-row"><button className="button" type="submit">Create my workspace →</button><button className="text-button" type="button" onClick={() => completeOnboarding(preferences)}>Skip for now</button></div>
    </form>
  </section>;
}
