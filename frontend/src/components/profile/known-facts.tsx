"use client";

import { useState } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";
import { describePreference } from "@/lib/task-utils";
import type { PreferenceRow } from "@/lib/types";

const sources: Record<PreferenceRow["source"], string> = { stated: "You told LifeOS", inferred: "Learned from your history", default: "Set automatically" };

/** "What LifeOS knows about you": every stored preference, where it came from, and a way to remove it. */
export function KnownFacts() {
  const { api, preferenceRows, reloadPreferences, notify } = useWorkspace();
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  async function run(row: PreferenceRow, action: "delete" | "accept") {
    setBusy(row.id); setError("");
    try {
      await api(action === "delete" ? `/api/preferences/${row.id}?confirmed=true` : `/api/preferences/${row.id}/accept`, { method: action === "delete" ? "DELETE" : "POST" });
    } catch (e) { setError(readableError(e)); setBusy(""); return; }
    setConfirm(""); setBusy("");
    notify(action === "delete" ? "Removed. LifeOS uses the default again." : "Accepted.");
    await reloadPreferences().catch(() => setError("Saved, but the list could not be refreshed. Reload the page."));
  }

  const rows = [...preferenceRows].sort((a, b) => a.key.localeCompare(b.key));
  return <section className="panel transparency" aria-labelledby="known-title"><h2 id="known-title">What LifeOS knows about you</h2>
    <p>Everything the planner uses about you is listed here. Learned patterns wait for your approval.</p>
    {error ? <p className="error-message" role="alert">{error}</p> : null}
    {rows.length ? <ul className="known-list">{rows.map(row => {
      const { label, value } = describePreference(row);
      return <li key={row.id}><div><b>{label}</b><span>{value}</span><small className="muted">{sources[row.source] ?? row.source}{row.status === "suggested" ? ` · Suggested (${Math.round(row.confidence * 100)}% sure)` : ""}</small></div>
        <span className="button-row">{row.status === "suggested" ? <button className="text-button" disabled={busy === row.id} onClick={() => run(row, "accept")} aria-label={`Accept ${label}`}>Accept</button> : null}
          {row.key === "timezone" ? <small className="muted">Change it in the form above</small> : confirm === row.id ? <><button className="text-button danger-text" disabled={busy === row.id} onClick={() => run(row, "delete")} aria-label={`Confirm deleting ${label}`}>Delete</button><button className="text-button" onClick={() => setConfirm("")}>Keep</button></> : <button className="text-button" onClick={() => setConfirm(row.id)} aria-label={`Delete ${label}`}>Delete</button>}</span></li>;
    })}</ul> : <p className="muted">Nothing stored yet. LifeOS uses its defaults until you save preferences.</p>}
  </section>;
}
