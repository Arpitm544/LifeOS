import type { Metadata } from "next";
import { CONTACT_EMAIL, LegalPage } from "@/components/layout/legal-page";

export const metadata: Metadata = { title: "Privacy Policy", description: "How LifeOS collects, uses, stores and deletes your data, including Google Calendar data." };

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy">
      <p>LifeOS is a personal planning workspace. This policy explains what data LifeOS collects, how it is used, who it is shared with, and how you can delete it.</p>

      <h2>Data we collect</h2>
      <ul>
        <li><strong>Account details.</strong> Your name, email address and sign-in details, handled by our sign-in provider, Clerk.</li>
        <li><strong>Workspace content.</strong> The tasks, routines, plans, preferences, chat messages and notes you add to LifeOS.</li>
        <li><strong>Google Calendar data</strong>, only if you choose to connect it (see below).</li>
        <li><strong>Voice recordings</strong>, only when you use voice input or read-aloud. Audio is sent for transcription or speech and is not stored by LifeOS.</li>
        <li><strong>Photos and files</strong> you import, such as a photo of a to-do list or a syllabus. They are processed to pull out tasks and are not kept after import.</li>
        <li><strong>Notification subscriptions</strong>, if you turn on browser notifications.</li>
      </ul>

      <h2>Google Calendar data</h2>
      <p>When you connect Google Calendar, LifeOS asks for read-only access (<code>calendar.readonly</code>). LifeOS never creates, edits or deletes anything in your Google account.</p>
      <ul>
        <li><strong>What we read:</strong> events on your primary calendar from one day ago to 60 days ahead.</li>
        <li><strong>What we store:</strong> each event&rsquo;s title, start and end time, and location, so your schedule appears in Today and Week and focus time is planned only around your free time. We also store an encrypted Google refresh token so we can keep your calendar in sync.</li>
        <li><strong>How we use it:</strong> only to show your schedule and plan your time inside LifeOS. When you ask the LifeOS assistant a question, today&rsquo;s event titles and times may be sent to our AI model provider to answer it.</li>
        <li><strong>What we never do:</strong> sell your Google data, use it for advertising, let people read it (except when you ask us to for support or where the law requires it), or use it to train general AI models.</li>
        <li><strong>Disconnecting:</strong> you can disconnect Google Calendar in Profile at any time. LifeOS revokes its access with Google and you can choose to remove the imported events. You can also remove access at <a href="https://myaccount.google.com/permissions">myaccount.google.com/permissions</a>.</li>
      </ul>
      <p>LifeOS&rsquo;s use and transfer of information received from Google APIs follows the <a href="https://developers.google.com/terms/api-services-user-data-policy">Google API Services User Data Policy</a>, including the Limited Use requirements.</p>

      <h2>How we use your data</h2>
      <p>We use your data only to run LifeOS for you: to plan your time, show your schedule, send reminders you turned on, answer your requests to the assistant, and keep the service secure. We do not sell your data or use it for advertising.</p>

      <h2>Service providers</h2>
      <p>LifeOS relies on a small number of providers who process data only to deliver the service:</p>
      <ul>
        <li><strong>Clerk</strong>: sign-in and account management.</li>
        <li><strong>An AI model provider</strong>: to understand chat messages, imports and requests, and to write your daily brief.</li>
        <li><strong>Deepgram</strong>: voice transcription and read-aloud.</li>
        <li><strong>Google</strong>: Calendar data, if you connect it.</li>
        <li><strong>Browser push services</strong> (for example, from Google, Mozilla, Apple or Microsoft): to deliver notifications you turned on.</li>
        <li><strong>Our hosting provider</strong>: to run the servers and the database.</li>
      </ul>

      <h2>Storage and security</h2>
      <p>Data is stored in our database and sent over encrypted HTTPS connections. Google refresh tokens are encrypted at rest. Your workspace is visible only to your signed-in account.</p>

      <h2>Your choices and deletion</h2>
      <ul>
        <li>Export everything in your workspace from <strong>Profile &rarr; Privacy &rarr; Export my data</strong>.</li>
        <li>Delete your workspace data and account from <strong>Profile &rarr; Privacy</strong>. This removes your tasks, plans, calendar copies and Google connection.</li>
        <li>Disconnect Google Calendar from Profile at any time.</li>
        <li>For any other request, email <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.</li>
      </ul>

      <h2>Children</h2>
      <p>LifeOS is not intended for children under 13, and we do not knowingly collect their data.</p>

      <h2>Changes</h2>
      <p>If this policy changes, we will update the date at the top of this page. Significant changes will also be shown in the app.</p>
    </LegalPage>
  );
}
