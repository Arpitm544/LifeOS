"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeading } from "@/components/layout/page-heading";
import { PushToggle } from "@/components/profile/push-toggle";
import { Routines } from "@/components/profile/routines";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";
import { focusPeriods, type FocusPeriod } from "@/lib/task-utils";

const steps = ["Your day", "Focus", "Routines", "Permissions"] as const;

/** First run (PRD 5.1): working and quiet hours, focus time, routines, permissions, then Chat. */
export default function OnboardingPage() {
  const { api, preferences, savePreferences, reloadPreferences } = useWorkspace();
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [day, setDay] = useState({ timezone: preferences.timezone, workStart: preferences.workStart, workEnd: preferences.workEnd, quietStart: preferences.quietStart, quietEnd: preferences.quietEnd });
  const [focus, setFocus] = useState<FocusPeriod>("morning");
  const [mic, setMic] = useState<"idle" | "granted" | "denied" | "unsupported">("idle");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function askMic() {
    if (!navigator.mediaDevices?.getUserMedia) { setMic("unsupported"); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach(track => track.stop()); // permission only: nothing is recorded
      setMic("granted");
    } catch { setMic("denied"); }
  }

  async function saveDay() {
    setError(""); setBusy(true);
    try {
      const [focusStart, focusEnd] = focusPeriods[focus].window;
      await savePreferences({ ...preferences, ...day, focusStart, focusEnd });
      return true;
    } catch (e) { setError(readableError(e, "Could not save your hours.")); return false; }
    finally { setBusy(false); }
  }

  async function next() {
    if (step === 1 && !(await saveDay())) return;
    setStep(value => Math.min(steps.length - 1, value + 1));
  }

  async function finish(skipped = false) {
    setError(""); setBusy(true);
    try {
      await api("/api/preferences", { method: "POST", body: { key: "onboarding", value: { completed: true, ...(skipped ? {} : { focus_period: focus }) } } });
      await reloadPreferences();
      router.replace("/chat?welcome=1");
    } catch (e) { setError(readableError(e, "Could not finish setup.")); setBusy(false); }
  }

  const field = (key: keyof typeof day, label: string, type = "time") => <label className="preference-row"><span className="eyebrow muted">{label}</span>
    <input type={type} required value={day[key]} onChange={e => setDay(current => ({ ...current, [key]: e.target.value }))} /></label>;

  return <>
    <PageHeading eyebrow={`Welcome · Step ${step + 1} of ${steps.length}`} title="Let’s fit LifeOS to your week." description="Four short steps. You can change any of this later in Profile." />
    <ol className="onboarding-steps" aria-label="Setup progress">{steps.map((label, index) => <li key={label} className={index === step ? "current" : index < step ? "done" : ""} aria-current={index === step ? "step" : undefined}>{label}</li>)}</ol>
    <section className="panel onboarding-panel">
      {step === 0 ? <><h2>Your day</h2><p className="muted">LifeOS only plans work inside your working hours and never reminds you during quiet hours.</p>
        <div className="onboarding-grid">{field("workStart", "Work starts")}{field("workEnd", "Work ends")}{field("quietStart", "Quiet from")}{field("quietEnd", "Quiet until")}</div>
        {field("timezone", "Timezone (detected)", "text")}</> : null}
      {step === 1 ? <><h2>When do you focus best?</h2><p className="muted">Demanding tasks go here first. LifeOS replaces this with your real pattern once you have completed 10 tasks.</p>
        <div className="chip-row" role="radiogroup" aria-label="Best focus time">{(Object.keys(focusPeriods) as FocusPeriod[]).map(key => <button key={key} type="button" role="radio" aria-checked={focus === key} className={`chip ${focus === key ? "selected" : ""}`} onClick={() => setFocus(key)}>{focusPeriods[key].label} <small>{focusPeriods[key].window.join("–")}</small></button>)}</div></> : null}
      {step === 2 ? <><h2>Fixed routines <span className="muted">(optional)</span></h2><p className="muted">Classes, gym, shifts: the planner keeps these free. You can also just tell Chat, e.g. “Gym Mon Wed Fri 7–8 am”.</p><Routines /></> : null}
      {step === 3 ? <><h2>Permissions</h2>
        <div className="permission-row"><div><b>Notifications</b><p className="muted">So reminders reach you when LifeOS is closed, with Done and Snooze buttons.</p></div><PushToggle /></div>
        <div className="permission-row"><div><b>Microphone</b><p className="muted">For voice capture. Audio is never stored; only the transcript becomes a message.</p></div>
          <button type="button" className="button secondary" onClick={askMic} disabled={mic === "granted"}>{mic === "granted" ? "Microphone allowed" : mic === "denied" ? "Blocked — allow in browser settings" : mic === "unsupported" ? "Not available in this browser" : "Allow microphone"}</button></div></> : null}
      {error ? <p className="error-message" role="alert">{error}</p> : null}
      <div className="button-row onboarding-nav">
        {step > 0 ? <button type="button" className="text-button" onClick={() => setStep(step - 1)} disabled={busy}>← Back</button> : <button type="button" className="text-button" onClick={() => finish(true)} disabled={busy}>Skip setup</button>}
        {step < steps.length - 1 ? <button type="button" className="button" onClick={next} disabled={busy}>{busy ? "Saving…" : "Continue"} <span aria-hidden="true">→</span></button>
          : <button type="button" className="button" onClick={() => finish()} disabled={busy}>{busy ? "Finishing…" : "Start planning"} <span aria-hidden="true">→</span></button>}
      </div>
    </section>
  </>;
}
