"use client";

import { useState } from "react";
import { ArrowUpRight, Check, Circle, Clock3 } from "lucide-react";

const views = ["Today", "Tasks", "Chat"] as const;
const sampleTasks = ["Make progress on your big idea", "Take a well-earned pause", "Review tomorrow’s priorities"];

export function WorkspacePreview() {
  const [view, setView] = useState<(typeof views)[number]>("Today");
  const [completed, setCompleted] = useState<number[]>([1]);
  const [prompt, setPrompt] = useState("");
  const toggleTask = (index: number) => setCompleted(current => current.includes(index) ? current.filter(id => id !== index) : [...current, index]);

  return <div id="workspace-preview" className="workspace-preview" role="region" aria-label="Interactive sample LifeOS workspace">
    <div className="preview-toolbar"><span className="preview-window-dots" aria-hidden="true"><i /><i /><i /></span><span>YOUR PERSONAL ORBIT</span><span className="preview-demo">INTERACTIVE PREVIEW · SAMPLE DATA</span></div>
    <div className="preview-content">
      <aside className="preview-sidebar"><span className="brand"><span className="landing-logo" aria-hidden="true" /> LifeOS</span><div className="preview-nav" role="group" aria-label="Choose a workspace preview">{views.map(item => <button type="button" key={item} className={view === item ? "preview-active" : ""} aria-pressed={view === item} onClick={() => setView(item)}>{item}<ArrowUpRight size={13} /></button>)}</div><span className="preview-sidebar-bottom">Sample workspace · Not your saved data</span></aside>
      <div key={view} className="preview-main" role="region" aria-label={`${view} preview`}>
        <p className="landing-kicker">{view === "Today" ? "TODAY" : view === "Tasks" ? "YOUR TASKS" : "CHAT PREVIEW"}</p>
        <h2>{view === "Today" ? "Your day at a glance." : view === "Tasks" ? "Your tasks, in one place." : "Capture a thought."}</h2>
        <p className="preview-description">Sample content only. Nothing here changes your workspace.</p>
        {view === "Today" ? <>
          <div className="preview-summary">
            <div><span>Open tasks</span><strong>{sampleTasks.length - completed.length}</strong></div>
            <div><span>Completed</span><strong>{completed.length}</strong></div>
            <div><span>Focus window</span><strong>2 hours</strong></div>
          </div>
          <div className="preview-dashboard-grid">
            <section className="preview-next-moves"><div className="preview-card-heading"><h3>Your next moves</h3><span>3 sample tasks</span></div>
              {sampleTasks.map((title, index) => <button type="button" className={`preview-task ${completed.includes(index) ? "preview-task-done" : ""}`} key={title} aria-pressed={completed.includes(index)} onClick={() => toggleTask(index)}>{completed.includes(index) ? <Check size={16} /> : <Circle size={16} />}<span><strong>{title}</strong><small>{index === 1 ? "A protected pause" : index === 2 ? "Planning" : "Personal · 45 minutes"}</small></span><small className="preview-task-action">{completed.includes(index) ? "Done" : "Open"}</small></button>)}
            </section>
            <section className="preview-focus"><div className="preview-focus-icon"><Clock3 size={17} /></div><p className="landing-kicker">SAMPLE FOCUS WINDOW</p><h3>9:00–11:00</h3><p>Two hours set aside for what matters most.</p><div className="preview-focus-bar"><span /></div><small>Adjust your own hours in Preferences.</small></section>
          </div>
        </> : view === "Tasks" ? <div className="preview-interactive-tasks"><p>Try checking off a sample task.</p>{sampleTasks.map((title, index) => <button type="button" className={`preview-task ${completed.includes(index) ? "preview-task-done" : ""}`} key={title} aria-pressed={completed.includes(index)} onClick={() => toggleTask(index)}>{completed.includes(index) ? <Check size={17} /> : <Circle size={17} />}<span><strong>{title}</strong><small>Sample task · Click to {completed.includes(index) ? "reopen" : "complete"}</small></span></button>)}<p role="status">{completed.length} of {sampleTasks.length} sample tasks completed.</p></div> : <div className="preview-chat"><p>Choose a thought to see the preview.</p><div className="preview-chat-prompts">{["Make room for a little focus", "Capture my next big idea"].map(text => <button type="button" key={text} onClick={() => setPrompt(text)}>{text} →</button>)}</div>{prompt ? <div className="preview-chat-messages" role="status"><p>{prompt}</p><p><strong>LifeOS · Scripted preview</strong>Your thought has a place here. In your own workspace, you can save your words as a task. AI scheduling isn’t connected yet.</p></div> : <div className="preview-chat-empty" aria-hidden="true">✳</div>}</div>}
      </div>
    </div>
  </div>;
}
