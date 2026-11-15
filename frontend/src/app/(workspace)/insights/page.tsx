"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHeading } from "@/components/layout/page-heading";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { Sparkline } from "@/components/ui/sparkline";
import { readableError } from "@/lib/api";
import type { Insights, Suggestion } from "@/lib/types";

const hour = (value: number) => `${String(value).padStart(2, "0")}:00`;

export default function InsightsPage() {
  const { api, reloadPreferences, notify } = useWorkspace();
  const [data, setData] = useState<Insights>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    try { setData(await api<Insights>("/api/insights")); setError(""); }
    catch (e) { setError(readableError(e, "Could not load insights.")); }
  }, [api]);
  useEffect(() => { load(); }, [load]);

  async function decide(suggestion: Suggestion, choice: "apply" | "dismiss") {
    if (busy) return;
    setBusy(suggestion.id);
    try {
      await api(`/api/insights/suggestions/${suggestion.id}/${choice}`, { method: "POST" });
    } catch (e) { notify(readableError(e)); setBusy(""); return; }
    setBusy("");
    setData(current => current ? { ...current, suggestions: current.suggestions.filter(s => s.id !== suggestion.id) } : current);
    if (choice === "apply") { notify("Applied. Your next plan will use it."); reloadPreferences().catch(() => undefined); }
  }

  if (!data) return <>
    <PageHeading eyebrow="A clearer picture of you" title="Find a pace that works." description="Patterns from your own tasks and plans." />
    {error ? <div className="panel empty-state" role="alert"><h2>Insights are unavailable.</h2><p>{error}</p><button className="button" onClick={load}>Try again</button></div> : <p className="muted" role="status">Loading insights…</p>}
  </>;

  const chart = data.completion_chart;
  const thisWeek = chart.slice(-7).reduce((sum, day) => sum + day.completed, 0);
  const lastWeek = chart.slice(-14, -7).reduce((sum, day) => sum + day.completed, 0);
  const change = thisWeek - lastWeek;
  const peak = Math.max(1, ...chart.map(day => day.completed));
  const factors = Object.entries(data.calibration_factors).sort((a, b) => b[1] - a[1]);
  const [topCategory, topFactor] = factors[0] ?? [];
  const adherence = data.planned_blocks_14d ? `${Math.round(data.plan_adherence * 100)}%` : "—";
  const focus = data.focus_windows[0];
  const dayLabel = (date: string) => new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(`${date}T00:00:00Z`));

  return <>
    <PageHeading eyebrow="A clearer picture of you" title="Find a pace that works." description={data.cold_start ? `Learning from your history: ${data.samples} of 10 completed tasks with timing so far.` : "Patterns from your last 14 days of tasks and plans."} />
    <div className="metrics-grid">
      <section className="panel metric"><h2>Completed this week</h2><p className="metric-value">{thisWeek}</p><Sparkline values={chart.map(day => day.completed)} label={`Completed per day, last 14 days: ${chart.map(day => day.completed).join(", ")}`} /><p>{change === 0 ? "Same as last week" : `${Math.abs(change)} ${change < 0 ? "fewer" : "more"} than last week`}{data.completion_rate !== null ? ` · ${Math.round(data.completion_rate * 100)}% on time` : ""}</p></section>
      <section className="panel metric"><h2>Plan adherence</h2><p className="metric-value">{adherence}</p>{data.planned_blocks_14d && data.adherence_chart?.length ? <Sparkline values={data.adherence_chart.map(day => day.rate)} max={1} label={`Share of planned blocks done per day, last 14 days: ${data.adherence_chart.map(day => day.rate === null ? "none planned" : `${Math.round(day.rate * 100)}%`).join(", ")}`} /> : null}<p>{data.planned_blocks_14d ? `Of ${data.planned_blocks_14d} planned blocks in 14 days` : "No planned blocks yet"}</p></section>
      <section className="panel metric"><h2>Estimate factor</h2><p className="metric-value">{topFactor ? `${topFactor}×` : "—"}</p><p>{topCategory ? `${topCategory[0].toUpperCase()}${topCategory.slice(1)} tasks vs. your estimates` : "Needs more completed tasks"}</p></section>
    </div>
    <div className="two-columns insights-columns"><section className="panel chart-panel"><h2>Progress, one day at a time.</h2><p>Completed tasks · Last 14 days</p>
      {chart.length ? <div className="bar-chart" role="img" aria-label={`Completed tasks per day: ${chart.map(day => `${dayLabel(day.date)} ${day.completed}`).join(", ")}.`}>
        {chart.map((day, index) => <div className="chart-column" key={day.date}><div className={`chart-bar ${index === chart.length - 1 ? "latest" : ""}`} style={{ height: `${Math.max(4, (day.completed / peak) * 150)}px` }} title={`${dayLabel(day.date)}: ${day.completed} completed`} /><span>{new Date(`${day.date}T00:00:00Z`).getUTCDate()}</span></div>)}
      </div> : <p className="muted">No history yet.</p>}
    </section><section className="panel dark suggestion"><p className="eyebrow accent">A little adjustment</p>
      {data.suggestions.length ? data.suggestions.map(suggestion => <div key={suggestion.id} className="suggestion-item"><p>{suggestion.text}</p><div className="button-row"><button className="button" disabled={!!busy} onClick={() => decide(suggestion, "apply")}>Apply <span aria-hidden="true">→</span></button><button className="text-button light" disabled={!!busy} onClick={() => decide(suggestion, "dismiss")}>Dismiss</button></div></div>)
        : <><h2>Nothing to change right now.</h2><p>Suggestions appear once LifeOS sees a clear pattern in your history.</p></>}
      <small>Applying a suggestion saves a preference you can change in Profile.</small>
    </section></div>
    <section className="panel pale sweet-spot"><p className="eyebrow blue">Your sweet spot</p>{focus ? <><h2>{hour(focus[0])}–{hour(focus[1])}. Your clearest hours.</h2><p>Protect this window for your most important work.{data.focus_windows.length > 1 ? ` Also strong: ${data.focus_windows.slice(1).map(([s, e]) => `${hour(s)}–${hour(e)}`).join(", ")}.` : ""}</p></> : <><h2>Still learning your best pace.</h2><p>Complete a few more tasks and LifeOS will show when you focus best.</p></>}</section>
  </>;
}
