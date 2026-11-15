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
import { BarChart3, CalendarDays, CheckSquare, MessageCircle, PanelLeftClose, PanelLeftOpen, Plus, Search, Sun, Upload, UserRound, type LucideIcon } from "lucide-react";
import { isSidebarCollapsed, setSidebarCollapsed } from "@/lib/sidebar";

type NavLink = { label: string; href: string; icon: LucideIcon };
const groups: { title: string; links: NavLink[] }[] = [
  { title: "Plan", links: [{ label: "Today", href: "/today", icon: Sun }, { label: "Tasks", href: "/tasks", icon: CheckSquare }, { label: "Chat", href: "/chat", icon: MessageCircle }, { label: "Insights", href: "/insights", icon: BarChart3 }] },
  { title: "Bring in", links: [{ label: "Import", href: "/import", icon: Upload }, { label: "Calendar", href: "/import/calendar", icon: CalendarDays }] },
  { title: "You", links: [{ label: "Profile", href: "/profile", icon: UserRound }] },
];
const links = groups.flatMap(group => group.links);
// Nested pages belong to their section: /task/:id is Tasks, /conflict/:id is Today.
const aliases: Record<string, string> = { "/task": "/tasks", "/conflict": "/today" };

/** The nav link for a path: the longest matching href, so /import/calendar is Calendar, not Import. */
function activeHref(pathname: string) {
  const path = Object.entries(aliases).reduce((p, [from, to]) => p === from || p.startsWith(`${from}/`) ? to : p, pathname);
  return links.filter(({ href }) => path === href || path.startsWith(`${href}/`)).sort((a, b) => b.href.length - a.href.length)[0]?.href;
}

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
  const [collapsed, setCollapsed] = useState(false);
  // The pre-paint script already set the attribute; mirror it into state for the button's label.
  useEffect(() => { setCollapsed(isSidebarCollapsed()); }, []);
  function toggleSidebar() { setCollapsed(value => { setSidebarCollapsed(!value); return !value; }); }
  useEffect(() => {
    // Cmd/Ctrl + B shrinks or expands the sidebar, except while typing.
    function shortcut(e: KeyboardEvent) {
      const el = e.target as HTMLElement;
      if (!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey || e.key.toLowerCase() !== "b") return;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || el.isContentEditable) return;
      e.preventDefault();
      toggleSidebar();
    }
    document.addEventListener("keydown", shortcut);
    return () => document.removeEventListener("keydown", shortcut);
  }, []);
  const active = activeHref(pathname);
  const current = links.find(link => link.href === active)?.label ?? (pathname === "/onboarding" ? "Setup" : "Not found");
  function openSearch() {
    if (pathname === "/tasks") window.dispatchEvent(new Event("lifeos:focus-search"));
    else router.push("/tasks?search=1");
  }
  useEffect(() => {
    // "/" opens task search from any page; the Tasks page handles it itself.
    if (pathname === "/tasks" || pathname === "/onboarding") return;
    function slash(e: KeyboardEvent) {
      const el = e.target as HTMLElement;
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || el.isContentEditable || document.querySelector("dialog[open]")) return;
      e.preventDefault();
      router.push("/tasks?search=1");
    }
    document.addEventListener("keydown", slash);
    return () => document.removeEventListener("keydown", slash);
  }, [pathname, router]);
  useEffect(() => {
    const formatter = new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: preferences.timezone });
    const update = () => setDate(formatter.format(new Date()));
    update();
    const timer = window.setInterval(update, 60_000);
    document.addEventListener("visibilitychange", update);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", update); };
  }, [preferences.timezone]);

  return <>
    <a className="skip-link" href="#main">Skip to content</a>
    <aside className="sidebar">
      <div className="sidebar-brand"><div className="sidebar-brand-row"><Link href="/today" className="brand" aria-label="LifeOS, go to Today"><span className="landing-logo" aria-hidden="true" /><span className="brand-name">LifeOS</span></Link>
        <button type="button" className="sidebar-toggle" onClick={toggleSidebar} aria-pressed={collapsed} aria-label={collapsed ? "Expand sidebar" : "Shrink sidebar"} data-label={`${collapsed ? "Expand" : "Shrink"} sidebar · ⌘B`}>{collapsed ? <PanelLeftOpen size={17} aria-hidden="true" /> : <PanelLeftClose size={17} aria-hidden="true" />}</button></div>
        <p className="brand-caption">Your personal operating system</p></div>
      <nav aria-label="Main navigation">{groups.map(group => <div className="nav-group" key={group.title}><p className="nav-group-title">{group.title}</p>
        {group.links.map(({ label, href, icon: Icon }) => <Link href={href} key={href} className={`nav-link ${active === href ? "active" : ""}`} data-label={label} aria-current={active === href ? "page" : undefined}><Icon size={17} aria-hidden="true" /><span className="nav-label">{label}</span></Link>)}</div>)}</nav>
      <div className="account-card">
        <div className="account-identity"><UserButton /><Link href="/profile" className="account-name"><strong>{name.full}</strong><small>Personal workspace</small></Link><ThemeToggle /></div>
        <small className="sync-status" title="Synced to your account"><i /><span>Synced to your account</span></small>
      </div>
    </aside>
    <header className="mobile-header"><div className="mobile-header-top"><Link href="/today" className="brand"><span className="landing-logo" aria-hidden="true" /> LifeOS</Link><div className="mobile-header-actions"><ThemeToggle /><UserButton /></div></div><nav className="mobile-nav" aria-label="Main navigation">{links.map(({ label, href }) => <Link key={href} href={href} aria-current={active === href ? "page" : undefined} className={active === href ? "active" : ""}>{label}</Link>)}</nav></header>
    <div className="workspace">
      <header className="topbar">
        <nav className="crumbs" aria-label="Breadcrumb"><span>Workspace</span><span className="slash" aria-hidden="true">/</span><strong aria-current="page">{current}</strong></nav>
        <button type="button" className="search-link" onClick={openSearch}><Search size={15} aria-hidden="true" /><span>Search tasks…</span><kbd>/</kbd></button>
        <div className="topbar-actions">
          <span className="topbar-date" title={preferences.timezone}>{date}<span className="tz-chip">{preferences.timezone.split("/").pop()?.replace(/_/g, " ")}</span></span>
          {pathname !== "/onboarding" ? <button type="button" className="quick-add-button" onClick={() => window.dispatchEvent(new Event("lifeos:quick-add"))}><Plus size={15} aria-hidden="true" /> Quick add <kbd>⌘K</kbd></button> : null}
        </div>
      </header>
      <main id="main" tabIndex={-1}>{children}</main>
      <footer className="workspace-footer"><span>Life, with a little more space.</span></footer>
    </div>
    {pendingEffort ? <aside ref={effortSheet} className="effort-sheet" role="dialog" aria-live="polite" aria-label={`How long did ${pendingEffort.title} take?`}><button className="dialog-close" onClick={() => dismissEffort()} aria-label="Skip this question">×</button><p className="eyebrow blue">Done: {pendingEffort.title}</p><EffortPrompt key={pendingEffort.id} taskId={pendingEffort.id} estimate={pendingEffort.effort_est_min} onDone={() => { const id = pendingEffort.id; window.setTimeout(() => dismissEffort(id), 1200); }} /></aside> : null}
    {pathname !== "/onboarding" ? <QuickAdd /> : null}
    {notice ? <div className="toast" role="status"><span>{notice}</span><button aria-label="Dismiss notification" onClick={() => notify("")}>×</button></div> : null}
  </>;
}
