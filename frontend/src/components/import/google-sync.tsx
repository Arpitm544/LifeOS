"use client";

import { useCallback, useEffect, useState } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";
import { googleReturnMessage, lastSyncedText, syncSummary, type GoogleStatus, type GoogleSyncResult } from "@/lib/google";

export function GoogleSync() {
  const { api, reloadTasks } = useWorkspace();
  const [status, setStatus] = useState<GoogleStatus | null>(null);
  const [busy, setBusy] = useState<"" | "connecting" | "syncing" | "disconnecting">("");
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  const load = useCallback(async () => {
    try { setStatus(await api<GoogleStatus>("/api/google/status")); }
    catch (e) { setMessage({ kind: "error", text: readableError(e, "Could not check Google Calendar.") }); }
  }, [api]);

  useEffect(() => {
    const result = new URLSearchParams(window.location.search).get("google");
    const returned = googleReturnMessage(result);
    if (returned) { setMessage(returned); window.history.replaceState(null, "", window.location.pathname); }
    void load();
  }, [load]);

  async function connect() {
    setMessage(null); setBusy("connecting");
    try {
      const { url } = await api<{ url: string }>("/api/google/connect", { method: "POST" });
      window.location.assign(url);
    } catch (e) { setMessage({ kind: "error", text: readableError(e, "Could not start the Google connection.") }); setBusy(""); }
  }

  async function sync() {
    setMessage(null); setBusy("syncing");
    try {
      const result = await api<GoogleSyncResult>("/api/google/sync", { method: "POST" });
      setMessage({ kind: "success", text: syncSummary(result) });
      await reloadTasks().catch(() => undefined);
    } catch (e) { setMessage({ kind: "error", text: readableError(e, "Could not sync Google Calendar.") }); }
    finally { setBusy(""); await load(); }
  }

  async function disconnect() {
    if (!window.confirm("Disconnect Google Calendar and remove the events it synced? Your own LifeOS events stay.")) return;
    setMessage(null); setBusy("disconnecting");
    try {
      await api("/api/google/disconnect?remove_events=true", { method: "DELETE" });
      setMessage({ kind: "success", text: "Google Calendar is disconnected." });
      await reloadTasks().catch(() => undefined);
    } catch (e) { setMessage({ kind: "error", text: readableError(e, "Could not disconnect.") }); }
    finally { setBusy(""); await load(); }
  }

  const note = message ? <p className={message.kind === "error" ? "error-message" : "success-message"} role={message.kind === "error" ? "alert" : "status"}>{message.text}</p> : null;

  return <section className="panel import-panel" aria-label="Google Calendar sync">
    <h2>Sync with Google Calendar.</h2>
    {!status ? <p className="muted">Checking…</p> : !status.configured ? <>
      <p className="muted">Google Calendar sync isn’t set up on this server yet. Add a Google client ID, client secret and token encryption key to the backend settings (see the README).</p>
    </> : status.connected ? <>
      <p className="muted">Connected, read-only. LifeOS copies the next 60 days of busy time and refreshes it automatically. {lastSyncedText(status.last_synced_at)}.</p>
      {/* One message at a time: a fresh result replaces the saved error from the last sync. */}
      {note ?? (status.last_error ? <p className="error-message" role="alert">{status.last_error}</p> : null)}
      <div className="button-row">
        <button className="button" onClick={sync} disabled={!!busy}>{busy === "syncing" ? "Syncing…" : "Sync now"}</button>
        {status.needs_reconnect ? <button className="button secondary" onClick={connect} disabled={!!busy}>Reconnect</button> : null}
        <button className="text-button" onClick={disconnect} disabled={!!busy}>{busy === "disconnecting" ? "Disconnecting…" : "Disconnect"}</button>
      </div>
    </> : <>
      <p className="muted">Connect once and LifeOS keeps your real commitments in its plan. It only reads your calendar, never changes it, and you can disconnect any time.</p>
      {note}
      <div className="button-row"><button className="button" onClick={connect} disabled={!!busy}>{busy === "connecting" ? "Opening Google…" : "Connect Google Calendar"} <span aria-hidden="true">→</span></button></div>
    </>}
  </section>;
}
