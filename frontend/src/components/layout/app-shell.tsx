"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { EffortPrompt } from "@/components/tasks/effort-prompt";
import { QuickAdd } from "@/components/layout/quick-add";
import { needsOnboarding } from "@/lib/task-utils";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { useDisplayName } from "@/hooks/use-display-name";
import { UserButton } from "@clerk/nextjs";

const links = [["Today", "/today"], ["Chat", "/chat"], ["Tasks", "/tasks"], ["Import", "/import"], ["Calendar", "/import/calendar"], ["Insights", "/insights"], ["Profile", "/profile"]] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { preferences, preferenceRows, notice, notify, pendingEffort, dismissEffort, reloadTasks } = useWorkspace();
  const router = useRouter();
  const onboarding = needsOnboarding(preferenceRows);
  useEffect(() => { if (onboarding && pathname !== "/onboarding") router.replace("/onboarding"); }, [onboarding, pathname, router]);
  useEffect(() => {
    // Done / Snooze tapped on a push notification: refresh so the open app shows it at once.
    if (!("serviceWorker" in navigator)) return;
    function message(event: MessageEvent) {
      if (event.data?.type !== "lifeos:reminder-action") return;
      reloadTasks().catch(() => undefined);
      window.dispatchEvent(new Event("lifeos:changed"));
      notify(event.data.action === "done" ? "Marked done from the notification." : "Snoozed from the notification.");
    }
    navigator.serviceWorker.addEventListener("message", message);
    return () => navigator.serviceWorker.removeEventListener("message", message);
  }, [reloadTasks, notify]);
  const name = useDisplayName();
  const [date, setDate] = useState("");
  const effortSheet = useRef<HTMLElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const effortOpen = !!pendingEffort;
  useEffect(() => {
    if (effortOpen) {
      returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      effortSheet.current?.querySelector<HTMLButtonElement>(".chip")?.focus();
      return;
    }
    // Give focus back to where it was (the task's button usually), or to the page content if that is gone.
    const target = returnFocus.current;
    returnFocus.current = null;
    if (target?.isConnected && !(target as HTMLButtonElement).disabled) target.focus();
    else if (target) document.getElementById("main")?.focus();
  }, [effortOpen]);
  const current = links.find(([, href]) => pathname === href)?.[0] ?? (pathname === "/onboarding" ? "Setup" : "Not found");
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
      <Link href="/today" className="brand"><span className="landing-logo" aria-hidden="true" /> LifeOS</Link>
      <p className="brand-caption">Your personal operating system</p>
      <nav aria-label="Main navigation">{links.map(([label, href]) => <Link href={href} key={href} className={`nav-link ${pathname === href ? "active" : ""}`} aria-current={pathname === href ? "page" : undefined}>{label}</Link>)}</nav>
      <div className="account-card"><div className="account-identity"><UserButton /><ThemeToggle /><Link href="/profile"><strong>{name.full}</strong></Link></div><small>Personal workspace</small><small className="sync-status"><i /> Synced to your account</small></div>
    </aside>
    <header className="mobile-header"><div className="mobile-header-top"><Link href="/today" className="brand"><span className="landing-logo" aria-hidden="true" /> LifeOS</Link><div className="mobile-header-actions"><ThemeToggle /><UserButton /></div></div><nav className="mobile-nav" aria-label="Main navigation">{links.map(([label, href]) => <Link key={href} href={href} aria-current={pathname === href ? "page" : undefined} className={pathname === href ? "active" : ""}>{label}</Link>)}</nav></header>
    <div className="workspace">
      <header className="topbar"><span>Workspace <span className="slash">/</span> {current}</span><span>{date} <span className="slash">·</span> {preferences.timezone}</span><Link href="/tasks" className="search-link"><span aria-hidden="true">⌕</span> Search tasks</Link><span className="shortcut-hint"><kbd>⌘K</kbd> Quick add</span></header>
      <main id="main" tabIndex={-1}>{children}</main>
      <footer className="workspace-footer"><span>Life, with a little more space.</span></footer>
    </div>
    {pendingEffort ? <aside ref={effortSheet} className="effort-sheet" role="dialog" aria-live="polite" aria-label={`How long did ${pendingEffort.title} take?`}><button className="dialog-close" onClick={() => dismissEffort()} aria-label="Skip this question">×</button><p className="eyebrow blue">Done: {pendingEffort.title}</p><EffortPrompt key={pendingEffort.id} taskId={pendingEffort.id} estimate={pendingEffort.effort_est_min} onDone={() => { const id = pendingEffort.id; window.setTimeout(() => dismissEffort(id), 1200); }} /></aside> : null}
    {pathname !== "/onboarding" ? <QuickAdd /> : null}
    {notice ? <div className="toast" role="status"><span>{notice}</span><button aria-label="Dismiss notification" onClick={() => notify("")}>×</button></div> : null}
  </>;
}
