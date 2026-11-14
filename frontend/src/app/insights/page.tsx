"use client";

import { PageHeading } from "@/components/layout/page-heading";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { completionHistory } from "@/lib/demo-data";

export default function InsightsPage() {
  const { preferences, savePreferences } = useWorkspace();
  return <>
    <PageHeading eyebrow="A clearer picture of you" title="Find your rhythm. Keep it." description="Small patterns that help you build a better week. Sample history." />
    <div className="metrics-grid">{[["Completed", "24", "8 more than last week"], ["Plan adherence", "82%", "Your plans are getting realistic"], ["Estimate factor", "1.6×", "Study takes a little longer"]].map(([label, value, description]) => <section className="panel metric" key={label}><h2>{label}</h2><p className="metric-value">{value}</p><p>{description}</p></section>)}</div>
    <div className="two-columns insights-columns"><section className="panel chart-panel"><h2>Progress, one day at a time.</h2><p>Completed tasks · Last 14 days · Example history</p><div className="bar-chart" role="img" aria-label={`Sample completed tasks for days 1 to 14: ${completionHistory.join(", ")}.`}>
      {completionHistory.map((value, index) => <div className="chart-column" key={index}><div className={`chart-bar ${index === 13 ? "latest" : ""}`} style={{ height: `${value * 12}px` }} title={`Day ${index + 1}: ${value} completed tasks`} /><span>{index + 1}</span></div>)}
    </div></section><section className="panel dark suggestion"><p className="eyebrow lime">A little adjustment</p><h2>Give your study<br />time some space.</h2><p>In this sample history, study tasks take 1.6× the original estimate. Add a little breathing room to your next plan.</p><button className="button" onClick={() => savePreferences({ ...preferences, estimatePadding: !preferences.estimatePadding })}>{preferences.estimatePadding ? "Remove padding" : "Apply padding"}<span aria-hidden="true">{preferences.estimatePadding ? "✓" : "↗"}</span></button><small>{preferences.estimatePadding ? "Preference saved. Future backend plans can use it." : "You can change this any time."}</small></section></div>
    <section className="panel pale sweet-spot"><p className="eyebrow blue">Your sweet spot</p><h2>{preferences.focusStart}–{preferences.focusEnd}. Your clearest hours.</h2><p>Protect this window for your most important work. Leave the lighter things for later.</p></section>
  </>;
}
