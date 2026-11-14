"use client";

import { useClerk, useUser } from "@clerk/nextjs";
import { useState } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";

/** Data export and account deletion. */
export function PrivacyPanel() {
  const { api, notify } = useWorkspace();
  const { user } = useUser();
  const { signOut } = useClerk();
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState("");
  const [dataDeleted, setDataDeleted] = useState(false);

  async function exportData() {
    setBusy("export"); setError("");
    try {
      const data = await api<Record<string, unknown>>("/api/export");
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url; link.download = `lifeos-export-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.append(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      notify("Export downloaded.");
    } catch (e) { setError(readableError(e, "Could not export your data.")); }
    finally { setBusy(""); }
  }

  async function deleteAccount() {
    setBusy("delete"); setError("");
    try {
      // Drop this device's push subscription so a later account here starts clean.
      const registration = "serviceWorker" in navigator ? await navigator.serviceWorker.getRegistration("/sw.js") : undefined;
      await (await registration?.pushManager.getSubscription())?.unsubscribe();
    } catch { /* the server rows are deleted below either way */ }
    if (!dataDeleted) {
      try { await api("/api/account?confirmed=true", { method: "DELETE" }); setDataDeleted(true); }
      catch (e) { setError(readableError(e, "Could not delete your LifeOS data.")); setBusy(""); return; }
    }
    // The backend removes LifeOS data; the sign-in account itself belongs to Clerk.
    if (!user?.deleteSelfEnabled) {
      setError("Your LifeOS data is deleted, but this sign-in account cannot delete itself here. Remove it from Manage account in the account menu.");
      setBusy(""); return;
    }
    try { await user.delete(); }
    catch (e) { setError(`Your LifeOS data is deleted, but the sign-in account was not: ${readableError(e)} Try again.`); setBusy(""); return; }
    await signOut({ redirectUrl: "/sign-in" }).catch(() => undefined);
  }

  return <section className="panel privacy" aria-labelledby="privacy-title"><h2 id="privacy-title">Your data</h2>
    <p className="muted">Download everything LifeOS stores about you as JSON, or delete it.</p>
    <div className="button-row"><button className="button secondary" onClick={exportData} disabled={!!busy}>{busy === "export" ? "Preparing…" : "Export my data"}</button>
      {!confirming ? <button className="text-button danger-text" onClick={() => setConfirming(true)}>Delete account…</button> : null}</div>
    {confirming ? <div className="danger-zone"><p>This permanently deletes your tasks, events, routines, preferences, plans and reminders, then removes your sign-in account. It cannot be undone.</p>
      <label>Type DELETE to confirm<input value={typed} onChange={e => setTyped(e.target.value)} autoComplete="off" /></label>
      <div className="button-row"><button className="button danger" disabled={typed !== "DELETE" || !!busy} onClick={deleteAccount}>{busy === "delete" ? "Deleting…" : "Delete everything"}</button><button className="text-button" onClick={() => { setConfirming(false); setTyped(""); }}>Cancel</button></div></div> : null}
    {error ? <p className="error-message" role="alert">{error}</p> : null}
  </section>;
}
