import Link from "next/link";
import "./legal-page.css";

/** Contact address shown on the privacy policy and terms. Change it to the address you want users to write to. */
export const CONTACT_EMAIL = "arpitmaurya840@gmail.com";
export const LEGAL_UPDATED = "15 November 2026";

export function LegalPage({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="legal">
      <header className="legal-header">
        <Link href="/" className="brand"><span className="landing-logo" aria-hidden="true" />LifeOS</Link>
        <nav aria-label="Legal"><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></nav>
      </header>
      <main className="legal-main">
        <p className="eyebrow muted">Last updated {LEGAL_UPDATED}</p>
        <h1>{title}</h1>
        {children}
        <p className="legal-contact">Questions? Email <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.</p>
      </main>
    </div>
  );
}
