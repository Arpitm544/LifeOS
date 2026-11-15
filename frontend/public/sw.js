// LifeOS service worker: shows Web Push reminders sent by the backend worker, with
// Done / Snooze buttons that act without opening the app (PRD F3.2).
const ACTION_LABELS = { done: "Done", snooze_15: "Snooze 15 min", snooze_60: "Snooze 1 h" };

function sameOriginPath(value, fallback) {
  try {
    const url = new URL(value || fallback, self.location.origin);
    return url.origin === self.location.origin ? url.pathname + url.search : fallback;
  } catch { return fallback; }
}

self.addEventListener("push", event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { body: event.data ? event.data.text() : "" }; }
  const canAct = typeof data.action_url === "string" && typeof data.action_token === "string";
  const limit = typeof Notification !== "undefined" && Notification.maxActions ? Notification.maxActions : 2;
  const actions = canAct && Array.isArray(data.actions)
    ? data.actions.filter(item => item && ACTION_LABELS[item.action]).slice(0, limit).map(item => ({ action: item.action, title: item.title || ACTION_LABELS[item.action] }))
    : [];
  event.waitUntil(self.registration.showNotification(data.title || "LifeOS", {
    body: data.body || "You have a LifeOS reminder.",
    tag: data.reminder_id || undefined,
    actions,
    data: {
      url: sameOriginPath(data.url, "/today"),
      reminderId: data.reminder_id || null,
      actionUrl: canAct ? data.action_url : null,
      actionToken: canAct ? data.action_token : null,
    },
  }));
});

function openApp(path) {
  const url = new URL(path || "/today", self.location.origin).href;
  return self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(clients => {
    const open = clients.find(client => client.url.startsWith(self.location.origin));
    if (open) { return open.navigate(url).then(client => (client || open).focus()).catch(() => open.focus()); }
    return self.clients.openWindow(url);
  });
}

function tellClients(message) {
  return self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(clients => clients.forEach(client => client.postMessage(message)));
}

async function act(data, action) {
  const response = await fetch(data.actionUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Push-Token": data.actionToken },
    body: JSON.stringify({ action }),
  });
  if (!response.ok) throw new Error(`Action failed (${response.status})`);
  await tellClients({ type: "lifeos:reminder-action", reminderId: data.reminderId, action });
  if (action === "done") {
    await self.registration.showNotification("LifeOS", { body: "Marked done.", tag: `done-${data.reminderId}`, silent: true });
  }
}

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const data = event.notification.data || {};
  if (event.action && ACTION_LABELS[event.action] && data.actionUrl && data.actionToken) {
    // On failure (expired token, offline), open the app so the user can act there.
    event.waitUntil(act(data, event.action).catch(() => openApp(data.url)));
    return;
  }
  event.waitUntil(openApp(data.url));
});
