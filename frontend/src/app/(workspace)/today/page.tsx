"use client";

import Link from "next/link";
import { PageHeading } from "@/components/layout/page-heading";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { TaskCard } from "@/components/tasks/task-card";
import { compareDeadlines } from "@/lib/task-utils";
import { Orbit } from "@/components/ui/orbit";

export default function TodayPage() {
  const { tasks, preferences } = useWorkspace();
  const name = preferences.name.trim().split(/\s+/)[0];
  const upcoming = tasks.filter(t => !t.completed).sort(compareDeadlines).slice(0, 2);

  return <>
    <PageHeading eyebrow="Made for your rhythm" title="A little clarity. A lot more you." description={`Your day has room to breathe. Let’s keep it that way, ${name}.`} />
    <section className="hero panel pale" aria-labelledby="briefing-title"><div className="hero-copy"><p className="eyebrow blue">Your day, in orbit</p><h2 id="briefing-title">Hello, {name}.</h2><p>Two priorities. One clear plan.<br />You have 3.5 hours of open space today.</p><div className="button-row"><Link href="/chat?prompt=Plan%20my%20day" className="button">Plan my day <span aria-hidden="true">↗</span></Link><Link href="/chat" className="button secondary">Talk to LifeOS</Link></div><small>Preview briefing · Sample availability, not a live calendar.</small></div><Orbit /></section>
    <div className="two-columns today-columns"><section className="panel agenda"><div className="section-heading"><div><h2>Your next moves</h2><p>A plan around your life, with space in between.</p></div><Link href="/tasks" className="text-button">View all <span aria-hidden="true">↗</span></Link></div>
      {upcoming.length ? <div className="task-list"><TaskCard task={upcoming[0]} /><article className="task-card break-card"><div className="task-title-row"><span className="break-symbol" aria-hidden="true">◌</span><h3 className="task-title">A little time for yourself</h3><span className="rest-label">REST</span></div><p className="task-meta">30 minutes · A protected pause, just for you</p></article>{upcoming[1] ? <TaskCard task={upcoming[1]} /> : null}</div> : <div className="empty-state"><h3>Your list is clear.</h3><p>Enjoy the space, or add your next move.</p><Link className="button secondary" href="/tasks">Add a task</Link></div>}
    </section><div className="side-stack"><section className="panel dark capacity"><p className="eyebrow lime">Capacity guard</p><h2>Your week is looking good.</h2><p>18h planned <span>/</span> 24h available</p><div className="progress-track" role="meter" aria-label="Sample weekly capacity" aria-valuenow={18} aria-valuemin={0} aria-valuemax={24}><span /></div><small>Sample week · Calendar not connected</small></section><section className="panel focus-card"><p className="eyebrow muted">Your focus window</p><h2>Mornings are your thing.</h2><p>Your study tasks fit best between {preferences.focusStart} and {preferences.focusEnd}.<br />Save that time for what matters.</p><small>Sample insight · Demo data</small></section></div></div>
  </>;
}
