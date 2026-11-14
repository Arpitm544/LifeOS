import { ThemeToggle } from "@/components/ui/theme-toggle";
import { Canvas } from "@/components/ui/canvas";
import Link from "next/link";
import type { ReactNode } from "react";

export function AuthShell({ children }: { children: ReactNode }) {
  return <main className="auth-layout">
    <Canvas />
    <section className="auth-story" aria-label="Welcome to LifeOS">
      <Link className="auth-brand" href="/"><span className="landing-logo" aria-hidden="true" /> LifeOS</Link>
      <div className="auth-story-copy"><span className="auth-story-kicker"><i /> YOUR PERSONAL ORBIT</span><h1>Your life,<br />with a little<br /><em>more space.</em></h1><p>Bring your tasks, thoughts, and next steps into one calm place. Move at your pace, and leave room for the rest of life.</p></div>
      <div className="auth-story-bottom"><span>YOUR GOALS. YOUR PACE. YOUR SPACE.</span><span>© {new Date().getFullYear()} LIFEOS</span></div>
    </section>
    <section className="auth-panel" aria-label="Account access">
      <div className="auth-panel-top"><Link className="auth-mobile-brand" href="/"><span className="landing-logo" aria-hidden="true" /> LifeOS</Link><ThemeToggle /></div>
      <div className="auth-form-content"><p className="auth-form-kicker">A LITTLE CLARITY STARTS HERE</p>{children}</div>
      <footer className="auth-form-footer"><span>By continuing, you agree to LifeOS’s account terms.</span><Link href="/">Back to LifeOS home</Link></footer>
    </section>
  </main>;
}
