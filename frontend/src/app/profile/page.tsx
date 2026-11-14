"use client";

import { PageHeading } from "@/components/layout/page-heading";
import { PreferencesForm } from "@/components/profile/preferences-form";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { Orbit } from "@/components/ui/orbit";

export default function ProfilePage() {
  const { preferences, ready } = useWorkspace();
  return <><PageHeading eyebrow="Personal, by design" title="A workspace that feels like you." description="Your preferences shape the plan. You can change any of them." /><div className="two-columns profile-columns"><section className="panel">{ready ? <PreferencesForm key={JSON.stringify(preferences)} /> : <p role="status">Opening your preferences…</p>}</section><aside className="side-stack"><section className="panel pale identity"><Orbit variant="profile" /><h2>{preferences.name.trim().split(/\s+/)[0]}’s orbit</h2><p>Your goals. Your pace. Your space.</p><p className="blue">Appearance: Personal Orbit / Light</p><small>Motion: {preferences.reducedMotion ? "Reduced" : "Gentle"} · Device preference respected</small></section><section className="panel transparency"><h2>Nothing learned in secret.</h2><p>Your preferences stay on this device in this preview. Inferred patterns will need your approval when the backend is connected.</p><p className="blue">LifeOS does not record or store microphone audio.</p><small>Browser speech recognition may use its provider’s servers. No authentication or cloud sync is connected.</small></section></aside></div></>;
}
