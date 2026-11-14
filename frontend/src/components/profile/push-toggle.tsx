"use client";

import { useEffect, useState } from "react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { readableError } from "@/lib/api";

function keyBytes(base64: string) {
  const padded = (base64 + "=".repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

/** Web Push reminders: register /sw.js, subscribe with the server's VAPID key and save the subscription. */
export function PushToggle() {
  const { api, notify } = useWorkspace();
  const [supported, setSupported] = useState<boolean | null>(null);
  const [subscribed, setSubscribed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const ok = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
    setSupported(ok);
    if (ok) navigator.serviceWorker.getRegistration("/sw.js").then(reg => reg?.pushManager.getSubscription()).then(sub => setSubscribed(!!sub)).catch(() => undefined);
  }, []);

  async function enable() {
    setBusy(true); setError("");
    try {
      if (await Notification.requestPermission() !== "granted") throw new Error("Notifications are blocked for this site. Allow them in your browser settings.");
      const { public_key } = await api<{ public_key: string }>("/api/push/public-key");
      const registration = await navigator.serviceWorker.register("/sw.js");
      await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(public_key) });
      const json = subscription.toJSON();
      try {
        await api("/api/push/subscribe", { method: "POST", body: { endpoint: json.endpoint, keys: { p256dh: json.keys?.p256dh, auth: json.keys?.auth } } });
      } catch (saveError) {
        await subscription.unsubscribe().catch(() => undefined); // keep the browser in step with the server
        throw saveError;
      }
      setSubscribed(true); notify("Reminders will arrive as notifications on this device.");
    } catch (e) { setError(readableError(e, "Could not turn on notifications.")); }
    finally { setBusy(false); }
  }

  async function disable() {
    setBusy(true); setError("");
    try {
      const registration = await navigator.serviceWorker.getRegistration("/sw.js");
      const subscription = await registration?.pushManager.getSubscription();
      if (subscription) {
        await api("/api/push/unsubscribe", { method: "POST", body: { endpoint: subscription.endpoint } });
        await subscription.unsubscribe();
      }
      setSubscribed(false); notify("Notifications turned off on this device.");
    } catch (e) { setError(readableError(e, "Could not turn off notifications.")); }
    finally { setBusy(false); }
  }

  return <div className="push-toggle"><p><b>Reminder notifications</b><small className="muted">{supported === false ? "This browser does not support push notifications." : subscribed ? "On for this device." : "Get reminders even when LifeOS is closed."}</small></p>
    {supported ? <button className="button secondary" disabled={busy} onClick={subscribed ? disable : enable}>{busy ? "Working…" : subscribed ? "Turn off" : "Turn on"}</button> : null}
    {error ? <p className="error-message" role="alert">{error}</p> : null}
  </div>;
}
