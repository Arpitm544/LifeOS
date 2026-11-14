import Link from "next/link";
import { ArrowDown, ArrowRight, ArrowUpRight, AudioLines, Check, Clock3, ListChecks, LockKeyhole, MessageCircleMore, Sparkles } from "lucide-react";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { WorkspacePreview } from "@/components/ui/workspace-preview";
import { Canvas } from "@/components/ui/canvas";
import { CinematicFooter } from "@/components/ui/motion-footer";
import "./landing.css";

export default function Home() {
  return (
    <div className="landing" id="top">
      <a href="#main-content" className="skip-link">Skip to content</a>
      <div className="landing-surface">
        <header className="landing-header">
          <Link href="/" className="brand" aria-label="LifeOS home"><span className="landing-logo" aria-hidden="true" />LifeOS</Link>
          <nav aria-label="Main navigation"><a href="#features">The little things</a><a href="#workspace-preview">Workspace preview</a><a href="#how-it-works">What works now</a></nav>
          <div className="landing-header-actions"><ThemeToggle /><Link href="/sign-in" className="landing-login">Your workspace <ArrowUpRight size={16} /></Link></div>
        </header>

        <main id="main-content" className="landing-main">
          <section className="landing-hero" aria-labelledby="hero-title">
            <Canvas />
            <div className="landing-hero-copy">
              <p className="hero-overline">Tasks and focus time, in one place</p>
              <h1 id="hero-title">A place for your tasks.<br /><span>And room to think.</span></h1>
              <p className="landing-intro">Keep priorities, due dates, and focus hours together. Change the plan whenever your day changes.</p>
              <div className="landing-actions"><Link href="/sign-up" className="landing-cta">Create your workspace <ArrowRight size={17} /></Link><a href="#workspace-preview" className="hero-secondary">See the preview <ArrowDown size={15} /></a></div>
              <p className="landing-footnote"><LockKeyhole size={13} /> Your workspace is private to your signed-in account.</p>
            </div>
            <WorkspacePreview />
          </section>

          <section id="features" className="landing-features" aria-labelledby="features-title">
            <div className="landing-section-heading"><div><p className="landing-kicker">LESS JUGGLING. MORE LIVING.</p><h2 id="features-title">A home for your everyday.</h2></div><p>One calm place for tasks, focus time,<br />and the plans that make life yours.</p></div>
            <div className="landing-feature-grid">
              <article><span className="feature-icon"><Check size={23} /></span><span className="feature-index">01 / TASKS THAT STAY YOURS</span><h3>See the next thing clearly.</h3><p>Add priorities, effort, and due dates. Your list stays saved in this browser, ready to adjust as your day changes.</p><Link href="/tasks">Explore your tasks <ArrowUpRight size={17} /></Link></article>
              <article><span className="feature-icon"><AudioLines size={23} /></span><span className="feature-index">02 / AI CHAT</span><h3>Get the thought out first.</h3><p>Think out loud with voice or text. Review suggested tasks and save them when you choose.</p><Link href="/chat">Explore chat <ArrowUpRight size={17} /></Link></article>
              <article><span className="feature-icon"><Sparkles size={23} /></span><span className="feature-index">03 / YOUR PREFERENCES</span><h3>Plan around your real life.</h3><p>Set focus hours and quiet time, then shape a workspace that leaves room for the rest of your day.</p><Link href="/profile">Set your preferences <ArrowUpRight size={17} /></Link></article>
            </div>
          </section>

          <section className="landing-day" aria-labelledby="day-title">
            <div className="landing-day-heading"><p className="landing-kicker">A GENTLER WAY TO PLAN</p><h2 id="day-title">Make room for what matters today.</h2><p>Turn a busy day into a plan that fits your time and energy.</p></div>
            <div className="landing-day-steps">
              <article><span><ListChecks size={19} /></span><small>01 · SEE YOUR TASKS</small><h3>Know what needs attention.</h3><p>Bring due dates, priorities, and effort into one clear list.</p></article>
              <article><span><Clock3 size={19} /></span><small>02 · SET YOUR FOCUS</small><h3>Plan for the time you have.</h3><p>Choose your focus hours and keep your day realistic.</p></article>
              <article><span><ArrowRight size={19} /></span><small>03 · TAKE A NEXT STEP</small><h3>Start small. Adjust anytime.</h3><p>Make progress one task at a time, then reshape the plan as life changes.</p></article>
            </div>
            <Link href="/sign-up" className="landing-day-cta">Build your personal plan <ArrowRight size={16} /></Link>
          </section>

          <section id="how-it-works" className="landing-status" aria-labelledby="status-title">
            <div className="landing-status-copy"><p className="landing-kicker">A PERSONAL SPACE, AT YOUR PACE</p><h2 id="status-title">Your space.<br />Your way of doing life.</h2><p className="landing-status-intro">Start with the tools that are ready today. Add a little structure, keep what works, and adjust the rest as you go.</p><p className="landing-status-privacy"><LockKeyhole size={15} /> Your workspace is tied to your signed-in account.</p></div>
            <div className="landing-status-grid"><article><span className="status-icon is-live"><Check size={17} /></span><div><small>READY FOR YOUR DAY</small><h3>Tools you can use now</h3><p>Organize tasks, set focus hours and quiet time, and make the workspace feel like yours.</p></div></article><article><span className="status-icon is-preview"><MessageCircleMore size={17} /></span><div><small>A LOOK AT WHAT’S NEXT</small><h3>Chat and sample insights</h3><p>Chat connects to Gemini when configured. Insights show sample content, not patterns learned about you.</p></div></article></div>
            <Link href="/sign-up" className="landing-status-cta">Create your workspace <ArrowRight size={16} /></Link>
          </section>
        </main>
      </div>
      <CinematicFooter />
    </div>
  );
}
