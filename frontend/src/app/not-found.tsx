import Link from "next/link";
export default function NotFound() { return <section className="panel empty-state"><p className="eyebrow">A little detour</p><h1>This page is outside your orbit.</h1><Link className="button" href="/today">Back to Today</Link></section>; }
