import Link from "next/link";
import type { ReactNode } from "react";

export function AuthShell({ children }: { children: ReactNode }) {
  return <main className="auth-page"><Link className="brand" href="/">◉ LifeOS</Link><p className="eyebrow blue">Your goals. Your pace. Your space.</p>{children}<Link className="text-button" href="/sign-in">Already have an account? Sign in</Link><Link className="text-button" href="/sign-up">New to LifeOS? Create an account</Link></main>;
}
