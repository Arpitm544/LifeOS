"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { ArrowUp, ArrowRight, ArrowUpRight, Leaf, Heart } from "lucide-react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

const marquee = ["Your goals", "Your pace", "Your space", "A little clarity", "Room to breathe"];

export function CinematicFooter() {
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    gsap.registerPlugin(ScrollTrigger);
    const media = gsap.matchMedia();
    media.add("(prefers-reduced-motion: no-preference)", () => {
      const context = gsap.context(() => {
        gsap.fromTo(".footer-giant-text", { y: 70, scale: 0.9 }, {
          y: 0, scale: 1, ease: "none",
          scrollTrigger: { trigger: wrapperRef.current, start: "top bottom", end: "bottom bottom", scrub: 1 },
        });
        gsap.from(".footer-reveal", {
          y: 35, opacity: 0, stagger: 0.12, duration: 0.8,
          scrollTrigger: { trigger: wrapperRef.current, start: "top 65%" },
        });
      }, wrapperRef);
      return () => context.revert();
    });
    media.add("(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)", () => {
      const pills = wrapperRef.current?.querySelectorAll<HTMLElement>(".footer-magnetic") ?? [];
      const cleanups = Array.from(pills, (pill) => {
        const move = (event: MouseEvent) => {
          const rect = pill.getBoundingClientRect();
          gsap.to(pill, { x: (event.clientX - rect.left - rect.width / 2) * 0.2, y: (event.clientY - rect.top - rect.height / 2) * 0.2, duration: 0.3 });
        };
        const leave = () => { gsap.to(pill, { x: 0, y: 0, duration: 0.7, ease: "elastic.out(1, 0.4)" }); };
        pill.addEventListener("mousemove", move);
        pill.addEventListener("mouseleave", leave);
        return () => {
          pill.removeEventListener("mousemove", move);
          pill.removeEventListener("mouseleave", leave);
          gsap.killTweensOf(pill);
          gsap.set(pill, { clearProps: "transform" });
        };
      });
      return () => cleanups.forEach((cleanup) => cleanup());
    });
    return () => media.revert();
  }, []);

  return (
    <div className="cinematic-footer-wrapper" ref={wrapperRef}>
      <footer className="cinematic-footer" aria-labelledby="footer-title">
        <div className="footer-aurora" aria-hidden="true" /><div className="footer-grid" aria-hidden="true" />
        <div className="footer-marquee" aria-hidden="true"><div className="footer-marquee-track">{[0, 1].map((copy) => <div key={copy}>{marquee.map((item) => <span key={item}>{item}<b><Heart size={13} strokeWidth={1.5} /></b></span>)}</div>)}</div></div>
        <div className="footer-center"><p className="landing-kicker footer-reveal">THE NEXT CHAPTER IS YOURS</p><h2 id="footer-title" className="footer-reveal">A little more life.<br /><span>A little less noise.</span></h2><p className="footer-reveal">Your own little corner of clarity is waiting.</p><div className="footer-actions footer-reveal"><Link href="/sign-up" className="footer-pill footer-magnetic footer-primary">Create your workspace <ArrowRight size={19} /></Link><Link href="/sign-in" className="footer-pill footer-magnetic">Back to your workspace <ArrowRight size={17} /></Link></div><nav className="footer-links footer-reveal" aria-label="Footer navigation"><a href="#features">Explore LifeOS</a><a href="#how-it-works">What works now</a></nav></div>
        <div className="footer-giant-text" aria-hidden="true">LifeOS</div>
        <div className="footer-bottom"><span>© {new Date().getFullYear()} LifeOS</span><span><Leaf size={13} /> Made for a more human everyday.</span><a href="#top" className="footer-pill footer-magnetic footer-top" aria-label="Back to top"><ArrowUp size={19} /></a></div>
      </footer>
    </div>
  );
}
