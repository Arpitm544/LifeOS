import type { Metadata } from "next";
import Link from "next/link";
import { LegalPage } from "@/components/layout/legal-page";

export const metadata: Metadata = { title: "Terms of Service", description: "The terms for using LifeOS." };

export default function TermsPage() {
  return (
    <LegalPage title="Terms of Service">
      <p>These terms apply when you use LifeOS. By creating an account or using the service, you agree to them.</p>

      <h2>Your account</h2>
      <p>You need an account to use LifeOS. Keep your sign-in details safe; you are responsible for what happens in your account. You must be at least 13 years old to use LifeOS.</p>

      <h2>Your content</h2>
      <p>Everything you add to LifeOS, including tasks, notes, plans and imported calendar events, stays yours. You give us permission to store and process it only to run LifeOS for you, as described in the <Link href="/privacy">Privacy Policy</Link>.</p>

      <h2>Acceptable use</h2>
      <ul>
        <li>Don&rsquo;t use LifeOS for anything illegal or to harm others.</li>
        <li>Don&rsquo;t try to break, overload or get around the security or rate limits of the service.</li>
        <li>Don&rsquo;t try to access other people&rsquo;s accounts or data.</li>
      </ul>

      <h2>Connected services</h2>
      <p>If you connect Google Calendar or another service, your use of it is also covered by that service&rsquo;s own terms. You can disconnect it at any time.</p>

      <h2>AI features</h2>
      <p>LifeOS uses AI to plan your time, understand your messages and write summaries. AI output can be wrong, so check important dates and deadlines yourself.</p>

      <h2>The service is provided &ldquo;as is&rdquo;</h2>
      <p>We work to keep LifeOS available and accurate, but we can&rsquo;t promise it will always be available, error-free, or that plans and reminders will always be on time. To the extent the law allows, LifeOS is not liable for missed deadlines, lost data or other indirect losses from using the service.</p>

      <h2>Ending your use</h2>
      <p>You can stop using LifeOS and delete your account at any time from Profile. We may suspend accounts that break these terms.</p>

      <h2>Changes</h2>
      <p>We may update these terms. If we do, we will change the date at the top of this page. Continuing to use LifeOS after a change means you accept the new terms.</p>
    </LegalPage>
  );
}
