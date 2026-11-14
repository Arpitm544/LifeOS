"use client";

import { PageHeading } from "@/components/layout/page-heading";
import { KnownFacts } from "@/components/profile/known-facts";
import { PreferencesForm } from "@/components/profile/preferences-form";
import { PrivacyPanel } from "@/components/profile/privacy-panel";
import { PushToggle } from "@/components/profile/push-toggle";
import { Routines } from "@/components/profile/routines";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { useDisplayName } from "@/hooks/use-display-name";
import { Orbit } from "@/components/ui/orbit";

export default function ProfilePage() {
  const { preferences, reducedMotion } = useWorkspace();
  const name = useDisplayName();
  return <><PageHeading eyebrow="Personal, by design" title="A workspace that feels like you." description="Your preferences shape the plan. You can change any of them." />
    <div className="two-columns profile-columns"><div className="side-stack"><section className="panel"><PreferencesForm key={JSON.stringify(preferences)} /></section><Routines /><KnownFacts /></div>
      <aside className="side-stack"><section className="panel pale identity"><Orbit variant="profile" /><h2>{name.first}’s orbit</h2><p>Your goals. Your pace. Your space.</p><p className="blue">{preferences.timezone}</p><small>Motion: {reducedMotion ? "Reduced" : "Gentle"} · Device preference respected</small><PushToggle /></section><PrivacyPanel /></aside></div></>;
}
