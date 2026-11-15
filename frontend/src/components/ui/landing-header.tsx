"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { ArrowRight, Menu, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ThemeToggle } from "@/components/ui/theme-toggle";

const sections = [{ id: "features", label: "Features" }, { id: "how-it-works", label: "How it works" }, { id: "workspace-preview", label: "Preview" }, { id: "faq", label: "FAQ" }];

/** Sticky landing header: shrinks on scroll, highlights the section in view, and folds into a menu on phones. */
export function LandingHeader() {
  const { isSignedIn } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [active, setActive] = useState("");
  const [open, setOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    // The section crossing the upper middle of the screen is the one being read.
    const targets = sections.map(s => document.getElementById(s.id)).filter((el): el is HTMLElement => !!el);
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) setActive(entry.target.id);
    }, { rootMargin: "-35% 0px -60% 0px" });
    targets.forEach(el => observer.observe(el));
    const atTop = () => { if (window.scrollY < 200) setActive(""); };
    window.addEventListener("scroll", atTop, { passive: true });
    return () => { observer.disconnect(); window.removeEventListener("scroll", atTop); };
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); menuButton.current?.focus(); } };
    const onResize = () => { if (window.innerWidth > 860) setOpen(false); };
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", onResize);
    return () => { document.removeEventListener("keydown", onKey); window.removeEventListener("resize", onResize); };
  }, [open]);

  const cta = isSignedIn
    ? <Link href="/today" className="header-cta">Open workspace <ArrowRight size={15} aria-hidden="true" /></Link>
    : <Link href="/sign-up" className="header-cta">Get started <ArrowRight size={15} aria-hidden="true" /></Link>;

  return <header className={`landing-header ${scrolled ? "is-scrolled" : ""} ${open ? "is-open" : ""}`}>
    <div className="landing-header-inner">
      <Link href="/" className="brand" aria-label="LifeOS home"><span className="landing-logo" aria-hidden="true" />LifeOS</Link>
      <nav className="header-nav" aria-label="Main navigation">
        {sections.map(s => <a key={s.id} href={`#${s.id}`} className={active === s.id ? "is-active" : ""} aria-current={active === s.id ? "location" : undefined}>{s.label}</a>)}
      </nav>
      <div className="landing-header-actions">
        <ThemeToggle />
        {isSignedIn ? null : <Link href="/sign-in" className="header-signin">Sign in</Link>}
        {cta}
        <button ref={menuButton} type="button" className="header-menu-button" aria-expanded={open} aria-controls="landing-menu" aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen(v => !v)}>{open ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}</button>
      </div>
    </div>
    <div id="landing-menu" className="header-menu" hidden={!open}>
      <nav aria-label="Main navigation, menu">{sections.map(s => <a key={s.id} href={`#${s.id}`} onClick={() => setOpen(false)}>{s.label}</a>)}</nav>
      <div className="header-menu-actions">{isSignedIn ? null : <Link href="/sign-in" className="header-signin">Sign in</Link>}{cta}</div>
    </div>
  </header>;
}
