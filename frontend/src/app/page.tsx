import Link from "next/link";
import { ArrowDown, ArrowRight, BellRing, CalendarDays, Camera, Check, Clock3, LockKeyhole, Mic, MessageCircleMore, Play, ShieldAlert, Sparkles, Sunrise } from "lucide-react";
import { LandingHeader } from "@/components/ui/landing-header";
import { WorkspacePreview } from "@/components/ui/workspace-preview";
import { Canvas } from "@/components/ui/canvas";
import { CinematicFooter } from "@/components/ui/motion-footer";
import "./landing.css";

const faqs = [
  { q: "What happens when my day changes?", a: "Press Replan, or just tell LifeOS what moved. It rebuilds the next seven days around your events and working hours, and tells you if anything no longer fits." },
  { q: "Does it work with my calendar?", a: "Yes. Connect Google Calendar and your events show up in Today and Week, so focus time is only planned in the gaps you actually have." },
  { q: "How do I add tasks quickly?", a: "Type or speak a sentence like “essay due Friday, about 3 hours”, press ⌘K from any screen, or take a photo of a to-do list or syllabus and pick what to import." },
  { q: "Who can see my workspace?", a: "Only you. Your tasks, plans and preferences belong to your signed-in account and aren’t shared with anyone." },
  { q: "Will it remind me?", a: "Turn on notifications and LifeOS nudges you before a focus block or deadline. Mark it done or snooze it right from the notification." },
];

export default function Home() {
  return (
    <div className="landing" id="top">
      <a href="#main-content" className="skip-link">Skip to content</a>
      <div className="landing-surface">
        <LandingHeader />

        <main id="main-content" className="landing-main">
          <section className="landing-hero" aria-labelledby="hero-title">
            <Canvas />
            <div className="landing-hero-copy">
              <p className="hero-overline"><Sparkles size={14} aria-hidden="true" /> Tasks, calendar and focus time, planned for you</p>
              <h1 id="hero-title">A place for your tasks.<br /><span>And room to think.</span></h1>
              <p className="landing-intro">LifeOS turns your deadlines into a realistic plan around your calendar, warns you before something slips, and replans when your day changes.</p>
              <div className="landing-actions"><Link href="/sign-up" className="landing-cta">Create your workspace <ArrowRight size={17} aria-hidden="true" /></Link><a href="#how-it-works" className="hero-secondary">See how it works <ArrowDown size={15} aria-hidden="true" /></a></div>
              <ul className="hero-proof" aria-label="Highlights">
                <li><CalendarDays size={15} aria-hidden="true" /> Syncs with Google Calendar</li>
                <li><Mic size={15} aria-hidden="true" /> Type or talk</li>
                <li><LockKeyhole size={15} aria-hidden="true" /> Private to your account</li>
              </ul>
            </div>
            <WorkspacePreview />
          </section>

          <section id="features" className="landing-bento-section" aria-labelledby="features-title">
            <div className="landing-section-heading"><div><p className="landing-kicker">What LifeOS does</p><h2 id="features-title">Less juggling. More doing.</h2></div><p>The planning work you usually do in your head, done for you, and redone whenever things change.</p></div>
            <div className="bento">
              <article className="bento-card bento-wide">
                <span className="bento-icon"><Clock3 size={20} aria-hidden="true" /></span>
                <h3>Plans your day for you</h3>
                <p>LifeOS places focus blocks for your tasks inside your working hours, around meetings and classes. One click replans the whole week.</p>
                <ol className="mini-timeline" aria-label="Example plan">
                  <li className="is-focus"><time>09:00</time><span>Thesis draft</span><small>Focus</small></li>
                  <li className="is-event"><time>10:30</time><span>Team standup</span><small>Event</small></li>
                  <li className="is-focus"><time>11:00</time><span>Problem set 4</span><small>Focus</small></li>
                </ol>
              </article>
              <article className="bento-card">
                <span className="bento-icon is-risk"><ShieldAlert size={20} aria-hidden="true" /></span>
                <h3>Warns you before a deadline slips</h3>
                <p>The capacity guard checks every change. If something won&rsquo;t fit, you get real options, not guilt.</p>
                <div className="mini-risk"><b>1 h 30 min short</b> before Fri 08:00</div>
                <div className="mini-chips" aria-label="Example options"><span>Extend hours</span><span>Move flexible tasks</span><span>Draft a message</span></div>
              </article>
              <article className="bento-card">
                <span className="bento-icon"><Sunrise size={20} aria-hidden="true" /></span>
                <h3>A morning brief, read aloud</h3>
                <p>Start with what&rsquo;s due, what&rsquo;s next and whether your day fits, in your language.</p>
                <div className="mini-brief"><span className="mini-play" aria-hidden="true"><Play size={12} /></span><span>&ldquo;Good morning. Your day fits. 2 h of focus is planned.&rdquo;</span></div>
              </article>
              <article className="bento-card">
                <span className="bento-icon"><MessageCircleMore size={20} aria-hidden="true" /></span>
                <h3>Just say it</h3>
                <p>Chat or speak in plain words. LifeOS turns it into tasks, routines and preferences you can review.</p>
                <div className="mini-chat"><p className="from-you">Gym every Tue and Thu at 7 pm</p><p className="from-app"><Check size={13} aria-hidden="true" /> Routine added</p></div>
              </article>
              <article className="bento-card">
                <span className="bento-icon"><Camera size={20} aria-hidden="true" /></span>
                <h3>Bring everything in</h3>
                <p>Import Google Calendar events, snap a photo of a to-do list, or drop in a syllabus to pull out every deadline.</p>
                <div className="mini-sources" aria-label="Import sources"><span><CalendarDays size={14} aria-hidden="true" /> Calendar</span><span><Camera size={14} aria-hidden="true" /> Photo</span><span><BellRing size={14} aria-hidden="true" /> Reminders</span></div>
              </article>
            </div>
          </section>

          <section id="how-it-works" className="landing-day" aria-labelledby="day-title">
            <div className="landing-day-heading"><p className="landing-kicker">How it works</p><h2 id="day-title">From a full head to a plan that fits.</h2><p>Three steps, and you can change anything later.</p></div>
            <ol className="landing-day-steps">
              <li><span className="step-number" aria-hidden="true">1</span><h3>Tell it what&rsquo;s on your plate</h3><p>Add tasks by typing, talking or taking a photo. Connect your calendar so LifeOS knows when you&rsquo;re busy.</p></li>
              <li><span className="step-number" aria-hidden="true">2</span><h3>Get a plan that fits</h3><p>LifeOS schedules focus time inside your working hours and flags any deadline that can&rsquo;t be met.</p></li>
              <li><span className="step-number" aria-hidden="true">3</span><h3>Adjust as life happens</h3><p>Drag blocks across the week, snooze a reminder or replan in one click. The plan keeps up with you.</p></li>
            </ol>
            <Link href="/sign-up" className="landing-cta landing-day-cta">Create your workspace <ArrowRight size={16} aria-hidden="true" /></Link>
          </section>

          <section id="faq" className="landing-faq" aria-labelledby="faq-title">
            <div className="landing-faq-heading"><p className="landing-kicker">Questions</p><h2 id="faq-title">Good to know.</h2><p className="landing-faq-privacy"><LockKeyhole size={15} aria-hidden="true" /> Your workspace is private to your signed-in account.</p></div>
            <div className="faq-list">{faqs.map(({ q, a }) => <details key={q}><summary>{q}</summary><p>{a}</p></details>)}</div>
          </section>
        </main>
      </div>
      <CinematicFooter />
    </div>
  );
}
