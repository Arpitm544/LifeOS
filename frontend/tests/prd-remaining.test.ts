import assert from "node:assert/strict";
import test from "node:test";
import { adherenceCaption, sparklinePoints } from "../src/lib/sparkline.ts";
import { blockersOf, dependencyChoices, describePreference, preferencesFromRows, type DependencyLink } from "../src/lib/task-utils.ts";
import { placeAfter, shiftByMinutes } from "../src/lib/week.ts";
import type { PreferenceRow, Task } from "../src/lib/types.ts";

const task = (id: string, status: Task["status"] = "open"): Task => ({ id, title: id.toUpperCase(), deadline_at: null, effort_est_min: 30, importance: 3, category: "study", status, priority_score: 10, priority_band: "P3", pinned: false });
const link = (taskId: string, dependsOn: string): DependencyLink => ({ task_id: taskId, depends_on_task_id: dependsOn });

// ---------- Today timeline: drag and nudge ----------

test("shiftByMinutes moves both ends and keeps the length", () => {
  assert.deepEqual(shiftByMinutes({ start_at: "2026-11-16T04:00:00.000Z", end_at: "2026-11-16T05:30:00.000Z" }, 30),
    { start_at: "2026-11-16T04:30:00.000Z", end_at: "2026-11-16T06:00:00.000Z" });
  assert.deepEqual(shiftByMinutes({ start_at: "2026-11-16T00:10:00.000Z", end_at: "2026-11-16T00:40:00.000Z" }, -30),
    { start_at: "2026-11-15T23:40:00.000Z", end_at: "2026-11-16T00:10:00.000Z" });
});

test("placeAfter starts the block when the target ends", () => {
  const block = { start_at: "2026-11-16T09:00:00Z", end_at: "2026-11-16T10:30:00Z" };
  assert.deepEqual(placeAfter(block, { end_at: "2026-11-16T05:15:00Z" }),
    { start_at: "2026-11-16T05:15:00.000Z", end_at: "2026-11-16T06:45:00.000Z" });
  // Works with offsets from the API, too.
  assert.deepEqual(placeAfter(block, { end_at: "2026-11-16T12:00:00+05:30" }),
    { start_at: "2026-11-16T06:30:00.000Z", end_at: "2026-11-16T08:00:00.000Z" });
});

// ---------- Insights sparklines ----------

test("sparklinePoints spreads days across the width and scales to the maximum", () => {
  assert.equal(sparklinePoints([0, 2, 4], 100, 22), "0,21 50,11 100,1");
});

test("sparklinePoints honours a fixed maximum, clamps, and skips missing days", () => {
  assert.equal(sparklinePoints([1, null, 0.5, 2], 30, 12, 1), "0,1 20,6 30,1");
  assert.equal(sparklinePoints([-3], 40, 12), "20,11");
});

test("sparklinePoints returns nothing to draw for an empty or all-missing series", () => {
  assert.equal(sparklinePoints([], 100, 20), "");
  assert.equal(sparklinePoints([null, null], 100, 20), "");
  assert.equal(sparklinePoints([Number.NaN], 100, 20), "");
  assert.equal(sparklinePoints([0, 0], 10, 12), "0,11 10,11");  // flat zero line, no division by zero
});

// ---------- Dependencies ----------

test("blockersOf lists only unfinished prerequisites", () => {
  const tasks = [task("a"), task("b", "done"), task("c", "dropped"), task("d", "blocked")];
  const links = [link("d", "a"), link("d", "b"), link("d", "c"), link("a", "b")];
  assert.deepEqual(blockersOf("d", links, tasks).map(item => item.id), ["a"]);
  assert.deepEqual(blockersOf("a", links, tasks), []);
  assert.deepEqual(blockersOf("d", [link("d", "missing")], tasks), []);
});

test("dependencyChoices excludes itself, finished tasks and anything that would create a loop", () => {
  const tasks = [task("a"), task("b"), task("c"), task("d", "done"), task("e", "blocked")];
  // c waits for b, b waits for a: a may not wait for b or c.
  const links = [link("b", "a"), link("c", "b")];
  assert.deepEqual(dependencyChoices("a", links, tasks).map(item => item.id), ["e"]);
  assert.deepEqual(dependencyChoices("c", links, tasks).map(item => item.id), ["a", "b", "e"]);
  assert.deepEqual(dependencyChoices("x", [], tasks).map(item => item.id), ["a", "b", "c", "e"]);
});

// ---------- Learned preferences on the Profile screen ----------

const row = (key: string, value: Record<string, unknown>, extra: Partial<PreferenceRow> = {}): PreferenceRow => ({ id: key, key, value, source: "stated", confidence: 1, status: "active", ...extra });

test("an inferred proposal reads like the preference it would change", () => {
  assert.deepEqual(describePreference({ key: "inferred.reminder_lead", value: { minutes: 45 } }),
    { label: "Reminder lead (suggested change)", value: "45 min before the latest start" });
  assert.deepEqual(describePreference({ key: "inferred.focus_windows", value: { windows: [["15:00", "17:00"]] } }),
    { label: "Focus windows (suggested change)", value: "15:00–17:00" });
});

test("a pending proposal never changes the settings the planner form shows", () => {
  const rows = [row("reminder_lead", { minutes: 60 }), row("inferred.reminder_lead", { minutes: 45 }, { source: "inferred", status: "suggested", confidence: 0.8 })];
  assert.equal(preferencesFromRows(rows).reminderLead, 60);
});

test("plan adherence explains that only ended blocks count", () => {
  assert.equal(adherenceCaption(0), "Shows once a planned block has ended");
  assert.equal(adherenceCaption(1), "Of 1 planned block that ended in the last 14 days");
  assert.equal(adherenceCaption(6), "Of 6 planned blocks that ended in the last 14 days");
});
