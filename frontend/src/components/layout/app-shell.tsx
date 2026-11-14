"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";

const links = [["Today", "/today"], ["Chat", "/chat"], ["Tasks", "/tasks"], ["Insights", "/insights"], ["Profile", "/profile"]] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { preferences, notice, notify } = useWorkspace();
  const [date, setDate] = useState("");
  const current = links.find(([, href]) => pathname === href)?.[0] ?? "Today";
  useEffect(() => { setDate(new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "short", year: "numeric", timeZone: preferences.timezone }).format(new Date())); }, [preferences.timezone]);
  const initials = preferences.name.trim().split(/\s+/).slice(0, 2).map(n => n[0]).join("");

  return <>
    <a className="skip-link" href="#main">Skip to content</a>
    <aside className="sidebar">
      <Link href="/today" className="brand"><span className="brand-mark" aria-hidden="true">◉</span> LifeOS</Link>
      <p className="brand-caption">Your personal operating system</p>
      <nav aria-label="Main navigation">{links.map(([label, href]) => <Link href={href} key={href} className={`nav-link ${pathname === href ? "active" : ""}`} aria-current={pathname === href ? "page" : undefined}>{label}</Link>)}</nav>
      <Link href="/profile" className="account-card"><span><b className="avatar">{initials}</b><strong>{preferences.name}</strong></span><small>Personal workspace</small><small className="sync-status"><i /> Demo · Saved on this device</small></Link>
    </aside>
    <header className="mobile-header"><Link href="/today" className="brand">◉ LifeOS</Link><Link href="/profile" className="avatar" aria-label="Your profile">{initials}</Link></header>
    <div className="workspace">
      <header className="topbar"><span>Workspace <span className="slash">/</span> {current}</span><span>{date} <span className="slash">·</span> {preferences.timezone}</span><Link href="/tasks" className="search-link"><span aria-hidden="true">⌕</span> Search tasks <kbd>/</kbd></Link></header>
      <main id="main">{children}</main>
      <footer className="workspace-footer"><span>Life, with a little more space.</span><span className="demo-label"><i /> Frontend preview · Sample data</span></footer>
    </div>
    <nav className="mobile-nav" aria-label="Mobile navigation">{links.map(([label, href]) => <Link key={href} href={href} aria-current={pathname === href ? "page" : undefined} className={pathname === href ? "active" : ""}>{label}</Link>)}</nav>
    {notice ? <div className="toast" role="status"><span>{notice}</span><button aria-label="Dismiss notification" onClick={() => notify("")}>×</button></div> : null}
  </>;
}
