"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { EffortPrompt } from "@/components/tasks/effort-prompt";
import { useDisplayName } from "@/hooks/use-display-name";
import { UserButton } from "@clerk/nextjs";

const links = [["Today", "/today"], ["Chat", "/chat"], ["Tasks", "/tasks"], ["Insights", "/insights"], ["Profile", "/profile"]] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { preferences, notice, notify, pendingEffort, dismissEffort } = useWorkspace();
  const name = useDisplayName();
  const [date, setDate] = useState("");
  const effortSheet = useRef<HTMLElement>(null);
  useEffect(() => { if (pendingEffort) effortSheet.current?.querySelector<HTMLButtonElement>(".chip")?.focus(); }, [pendingEffort]);
  const current = links.find(([, href]) => pathname === href)?.[0] ?? "Not found";
  useEffect(() => {
    const formatter = new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "short", year: "numeric", timeZone: preferences.timezone });
    const update = () => setDate(formatter.format(new Date()));
    update();
    const timer = window.setInterval(update, 60_000);
    document.addEventListener("visibilitychange", update);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", update); };
  }, [preferences.timezone]);

  return <>
    <a className="skip-link" href="#main">Skip to content</a>
    <aside className="sidebar">
      <Link href="/today" className="brand"><span className="brand-mark" aria-hidden="true">◉</span> LifeOS</Link>
      <p className="brand-caption">Your personal operating system</p>
      <nav aria-label="Main navigation">{links.map(([label, href]) => <Link href={href} key={href} className={`nav-link ${pathname === href ? "active" : ""}`} aria-current={pathname === href ? "page" : undefined}>{label}</Link>)}</nav>
      <div className="account-card"><div className="account-identity"><UserButton /><Link href="/profile"><strong>{name.full}</strong></Link></div><small>Personal workspace</small><small className="sync-status"><i /> Synced to your account</small></div>
    </aside>
    <header className="mobile-header"><Link href="/today" className="brand">◉ LifeOS</Link><UserButton /></header>
    <div className="workspace">
      <header className="topbar"><span>Workspace <span className="slash">/</span> {current}</span><span>{date} <span className="slash">·</span> {preferences.timezone}</span><Link href="/tasks" className="search-link"><span aria-hidden="true">⌕</span> Search tasks</Link></header>
      <main id="main">{children}</main>
      <footer className="workspace-footer"><span>Life, with a little more space.</span></footer>
    </div>
    <nav className="mobile-nav" aria-label="Mobile navigation">{links.map(([label, href]) => <Link key={href} href={href} aria-current={pathname === href ? "page" : undefined} className={pathname === href ? "active" : ""}>{label}</Link>)}</nav>
    {pendingEffort ? <aside ref={effortSheet} className="effort-sheet" role="dialog" aria-live="polite" aria-label={`How long did ${pendingEffort.title} take?`}><button className="dialog-close" onClick={() => dismissEffort()} aria-label="Skip this question">×</button><p className="eyebrow blue">Done: {pendingEffort.title}</p><EffortPrompt key={pendingEffort.id} taskId={pendingEffort.id} estimate={pendingEffort.effort_est_min} onDone={() => { const id = pendingEffort.id; window.setTimeout(() => dismissEffort(id), 1200); }} /></aside> : null}
    {notice ? <div className="toast" role="status"><span>{notice}</span><button aria-label="Dismiss notification" onClick={() => notify("")}>×</button></div> : null}
  </>;
}
