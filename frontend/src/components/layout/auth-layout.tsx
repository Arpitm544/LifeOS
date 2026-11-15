import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowLeft, CalendarDays, Check, Clock3, LockKeyhole, Mic, ShieldCheck } from "lucide-react";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { Canvas } from "@/components/ui/canvas";

const copy = {
  "sign-in": { title: "Welcome back.", lead: "Pick up where you left off. Your plan is waiting." },
  "sign-up": { title: "Make room for what matters.", lead: "Create your workspace and get a plan that fits your real day." },
} as const;

const benefits = [
  { icon: Clock3, text: "Plans focus time around your calendar" },
  { icon: ShieldCheck, text: "Warns you before a deadline slips" },
  { icon: Mic, text: "Add tasks by typing, talking or a photo" },
];

/** Two-panel auth page: the product story on the left, the Clerk form on the right. Phones show only the form panel. */
export function AuthShell({ mode, children }: { mode: keyof typeof copy; children: ReactNode }) {
  const text = copy[mode];
  return <main className="auth-layout">
    <section className="auth-story" aria-label="About LifeOS">
      <Canvas />
      <Link className="auth-brand" href="/"><span className="landing-logo" aria-hidden="true" /> LifeOS</Link>
      <div className="auth-story-copy">
        <p className="auth-story-kicker"><span aria-hidden="true" /> Your personal orbit</p>
        <h2>Your life,<br />with a little <em>more space.</em></h2>
        <ul className="auth-benefits">{benefits.map(({ icon: Icon, text: line }) => <li key={line}><span><Icon size={16} aria-hidden="true" /></span>{line}</li>)}</ul>
        <div className="auth-sample" aria-hidden="true">
          <div className="auth-sample-head"><span>Today</span><span className="auth-sample-ok"><Check size={13} /> All deadlines fit</span></div>
          <div className="auth-sample-row is-focus"><time>09:00</time><b>Thesis draft</b><small>Focus</small></div>
          <div className="auth-sample-row"><time>10:30</time><b>Team standup</b><small><CalendarDays size={12} /> Event</small></div>
          <div className="auth-sample-row is-focus is-next"><time>11:00</time><b>Problem set 4</b><small>Up next</small></div>
        </div>
      </div>
      <div className="auth-story-bottom"><span><LockKeyhole size={13} aria-hidden="true" /> Private to your account</span><span>© {new Date().getFullYear()} LifeOS</span></div>
    </section>
    <section className="auth-panel" aria-labelledby="auth-title">
      <div className="auth-panel-top">
        <Link className="auth-mobile-brand" href="/"><span className="landing-logo" aria-hidden="true" /> LifeOS</Link>
        <div className="auth-panel-actions"><Link href="/" className="auth-back"><ArrowLeft size={15} aria-hidden="true" /> Home</Link><ThemeToggle /></div>
      </div>
      <div className="auth-form-content">
        <header className="auth-form-heading"><h1 id="auth-title">{text.title}</h1><p>{text.lead}</p></header>
        {children}
      </div>
      <footer className="auth-form-footer"><span><LockKeyhole size={13} aria-hidden="true" /> Your workspace is private to your signed-in account.</span></footer>
    </section>
  </main>;
}
