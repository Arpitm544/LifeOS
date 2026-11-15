"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, CalendarDays, CalendarRange, Eye, MapPin, RefreshCw, ShieldCheck } from "lucide-react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";
import { agendaDays, eventTimeText, googleReturnMessage, lastSyncedText, syncSummary, type CalendarEvent, type GoogleStatus, type GoogleSyncResult } from "@/lib/google";

type Tone = "ok" | "warn" | "off";

export function GoogleSync() {
  const { api, reloadTasks, preferences } = useWorkspace();
  const timezone = preferences.timezone;
  const [status, setStatus] = useState<GoogleStatus | null>(null);
  const [events, setEvents] = useState<CalendarEvent[] | null>(null);
  const [busy, setBusy] = useState<"" | "connecting" | "syncing" | "disconnecting">("");
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  const load = useCallback(async () => {
    try { setStatus(await api<GoogleStatus>("/api/google/status")); }
    catch (e) { setMessage({ kind: "error", text: readableError(e, "Could not check Google Calendar.") }); }
  }, [api]);
  const loadEvents = useCallback(async () => {
    try { setEvents(await api<CalendarEvent[]>("/api/events")); }
    catch { setEvents([]); }
  }, [api]);

  useEffect(() => {
    const result = new URLSearchParams(window.location.search).get("google");
    const returned = googleReturnMessage(result);
    if (returned) { setMessage(returned); window.history.replaceState(null, "", window.location.pathname); }
    void load(); void loadEvents();
    const refresh = () => { void loadEvents(); };
    window.addEventListener("lifeos:changed", refresh);
    return () => window.removeEventListener("lifeos:changed", refresh);
  }, [load, loadEvents]);

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
    finally { setBusy(""); await Promise.all([load(), loadEvents()]); }
  }

  async function disconnect() {
    if (!window.confirm("Disconnect Google Calendar and remove the events it synced? Your own LifeOS events stay.")) return;
    setMessage(null); setBusy("disconnecting");
    try {
      await api("/api/google/disconnect?remove_events=true", { method: "DELETE" });
      setMessage({ kind: "success", text: "Google Calendar is disconnected." });
      await reloadTasks().catch(() => undefined);
    } catch (e) { setMessage({ kind: "error", text: readableError(e, "Could not disconnect.") }); }
    finally { setBusy(""); await Promise.all([load(), loadEvents()]); }
  }

  const days = useMemo(() => agendaDays(events ?? [], timezone), [events, timezone]);
  const count = days.reduce((sum, day) => sum + day.events.length, 0);

  // One message at a time: a fresh result replaces the saved error from the last sync.
  const shown = message ?? (status?.connected && status.last_error ? { kind: "error" as const, text: status.last_error } : null);
  const note = shown ? <p className={shown.kind === "error" ? "error-message" : "success-message"} role={shown.kind === "error" ? "alert" : "status"}>{shown.text}</p> : null;

  const [tone, pill]: [Tone, string] = !status ? ["off", "Checking…"]
    : !status.configured ? ["off", "Not set up"]
    : status.needs_reconnect ? ["warn", "Needs reconnecting"]
    : status.connected ? [status.last_error ? "warn" : "ok", `Connected · ${lastSyncedText(status.last_synced_at)}`]
    : ["off", "Not connected"];

  return <div className="gcal">
    <section className="panel gcal-card" aria-label="Google Calendar connection">
      <div className="gcal-head">
        <span className="gcal-mark" aria-hidden="true"><CalendarDays size={22} strokeWidth={1.8} /></span>
        <div className="gcal-title">
          <h2>Google Calendar</h2>
          <span className={`gcal-pill ${tone}`}><i aria-hidden="true" />{pill}</span>
        </div>
        {status?.configured && status.connected ? <div className="gcal-actions">
          <button className="button secondary gcal-sync" onClick={sync} disabled={!!busy}>
            <RefreshCw size={15} className={busy === "syncing" ? "spin" : undefined} aria-hidden="true" />{busy === "syncing" ? "Syncing…" : "Sync now"}
          </button>
          {status.needs_reconnect ? <button className="button" onClick={connect} disabled={!!busy}>Reconnect</button> : null}
          <button className="text-button gcal-disconnect" onClick={disconnect} disabled={!!busy}>{busy === "disconnecting" ? "Disconnecting…" : "Disconnect"}</button>
        </div> : null}
      </div>

      {!status ? <p className="muted">Checking your connection…</p>
        : !status.configured ? <p className="muted">Google Calendar sync isn’t set up on this server yet. Add a Google client ID, client secret and token encryption key to the backend settings (see the README).</p>
        : status.connected ? <p className="muted">Read-only. LifeOS copies the next 60 days of busy time and refreshes it automatically, so focus blocks never land on top of a meeting.</p>
        : <>
          <p className="muted">Connect once and LifeOS plans around your real commitments.</p>
          <ul className="gcal-points">
            <li><Eye size={17} aria-hidden="true" /><span><strong>Read-only</strong>LifeOS never creates or edits Google events.</span></li>
            <li><CalendarRange size={17} aria-hidden="true" /><span><strong>Next 60 days</strong>Busy time is copied into your plan.</span></li>
            <li><ShieldCheck size={17} aria-hidden="true" /><span><strong>Yours to undo</strong>Disconnect any time; synced events go with it.</span></li>
          </ul>
        </>}

      {note}

      {status?.configured && !status.connected ? <button className="button gcal-connect" onClick={connect} disabled={!!busy}>
        {busy === "connecting" ? "Opening Google…" : "Connect Google Calendar"}<ArrowRight size={16} aria-hidden="true" />
      </button> : null}
    </section>

    <section className="panel agenda" aria-labelledby="agenda-heading">
      <div className="agenda-head">
        <div><h2 id="agenda-heading">Coming up</h2><p className="muted">Next 14 days, in {timezone}.</p></div>
        {events && count ? <span className="agenda-count">{count} {count === 1 ? "event" : "events"}</span> : null}
      </div>
      {!events ? <div className="agenda-skeleton" aria-label="Loading events"><span /><span /><span /></div>
        : !days.length ? <div className="agenda-empty">
          <CalendarDays size={26} strokeWidth={1.6} aria-hidden="true" />
          <strong>Nothing scheduled</strong>
          <p className="muted">{status?.connected ? "Your next two weeks are clear. New Google events appear here after the next sync." : "Connect Google Calendar to see your meetings here."}</p>
        </div>
        : <ol className="agenda-days">
          {days.map(day => <li key={day.key} className="agenda-day">
            <div className={`agenda-date${day.label === "Today" ? " today" : ""}`}>
              <span>{day.weekday}</span><strong>{day.day}</strong><span>{day.month}</span>
            </div>
            <div className="agenda-list">
              <h3>{day.label}</h3>
              <ul>
                {day.events.map(event => <li key={event.id} className={`agenda-event ${event.source === "gcal" ? "google" : "local"}`}>
                  <time dateTime={event.start_at}>{eventTimeText(event, timezone)}</time>
                  <div>
                    <strong>{event.title}</strong>
                    {event.location ? <span className="agenda-where"><MapPin size={12} aria-hidden="true" />{event.location}</span> : null}
                  </div>
                  <span className="agenda-source">{event.source === "gcal" ? "Google" : "LifeOS"}</span>
                </li>)}
              </ul>
            </div>
          </li>)}
        </ol>}
    </section>
  </div>;
}
