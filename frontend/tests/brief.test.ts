import assert from "node:assert/strict";
import test from "node:test";
import { briefPath, dismiss, visibleNudges, type Brief } from "../src/lib/brief.ts";

const brief: Brief = {
  date: "2026-11-16", timezone: "UTC", headline: "Good morning.", lines: [], spoken: "Good morning.", language: "en", translated: false,
  counts: { due_today: 0, overdue: 1, at_risk: 0, focus_min: 0, events: 0 },
  nudges: [
    { id: "overdue:1", kind: "overdue", tone: "risk", title: "Rent is overdue", detail: "", action: { type: "reschedule", task_id: "1", deadline_at: "2026-11-17T23:59:00Z", label: "Move to tomorrow" } },
    { id: "plan:2026-11-16", kind: "plan", tone: "suggest", title: "Nothing planned", detail: "", action: { type: "plan", label: "Plan my day" } },
  ],
};

test("brief path sends a language and first name only when useful", () => {
  assert.equal(briefPath(null, ""), "/api/brief");
  assert.equal(briefPath("en", "Asha"), "/api/brief?name=Asha");
  assert.equal(briefPath("hi", "Asha R"), "/api/brief?language=hi&name=Asha+R");
});

test("dismissed nudges stay hidden for that day only", () => {
  const hidden = dismiss({}, brief.date, "overdue:1");
  assert.deepEqual(visibleNudges(brief, hidden).map(n => n.id), ["plan:2026-11-16"]);
  assert.equal(visibleNudges({ ...brief, date: "2026-11-17" }, hidden).length, 2);
  // Older days are dropped when a new dismissal is saved.
  assert.deepEqual(dismiss({ "2026-11-15": ["x"] }, brief.date, "a"), { "2026-11-16": ["a"] });
  assert.deepEqual(dismiss(hidden, brief.date, "overdue:1"), hidden);
});
