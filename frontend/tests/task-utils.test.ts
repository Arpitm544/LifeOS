import assert from "node:assert/strict";
import test from "node:test";
import { compareDeadlines, comparePriority, describePreference, describeRule, filterTasks, formatEffort, formatHours, localDateKey, preferencesFromRows, preferenceUpdates, routineRule, validatePreferences, validateTask } from "../src/lib/task-utils.ts";
import type { PreferenceRow, Preferences, Task } from "../src/lib/types.ts";

const task: Task = { id: "1", title: "Study", deadline_at: "2026-11-14T19:00:00Z", effort_est_min: 30, importance: 3, category: "study", status: "open", priority_score: 50, priority_band: "P2", pinned: false };
const input = { title: task.title, deadline_at: task.deadline_at, effort_est_min: task.effort_est_min, importance: task.importance, category: task.category };
const preferences: Preferences = { timezone: "Asia/Kolkata", workStart: "09:00", workEnd: "18:00", quietStart: "22:30", quietEnd: "07:30", focusStart: "09:00", focusEnd: "11:00", reminderLead: 60, estimatePadding: false };
const row = (key: string, value: Record<string, unknown>, extra: Partial<PreferenceRow> = {}): PreferenceRow => ({ id: key, key, value, source: "stated", confidence: 1, status: "active", ...extra });

test("task validation matches the backend limits", () => {
  assert.equal(validateTask(input), null);
  for (const invalid of [{ title: "  " }, { title: "a".repeat(121) }, { deadline_at: "not a date" }, { effort_est_min: 4 }, { effort_est_min: 601 }, { effort_est_min: 10.5 }, { importance: 6 }, { notes: "n".repeat(2001) }]) assert.ok(validateTask({ ...input, ...invalid }));
});

test("deadline validation rejects normalized calendar dates and accepts leap days and offsets", () => {
  for (const deadline_at of ["2026-02-31", "2026-04-31T23:00:00-05:00", "2026-00-01", "2026-13-01", "11/14/2026"]) assert.ok(validateTask({ ...input, deadline_at }), deadline_at);
  for (const deadline_at of [null, "2024-02-29", "2024-02-29T23:00:00-05:00", "2026-11-14T19:00:00.000Z"]) assert.equal(validateTask({ ...input, deadline_at }), null);
});

test("filtering uses the profile timezone, hides dropped tasks and keeps done tasks separate", () => {
  const now = new Date("2026-11-14T20:00:00Z");
  assert.equal(localDateKey(task.deadline_at!, "Asia/Kolkata"), "2026-11-15");
  assert.equal(filterTasks([task], "today", "study", "Asia/Kolkata", now).length, 1);
  assert.equal(filterTasks([task], "today", "missing", "Asia/Kolkata", now).length, 0);
  assert.equal(filterTasks([{ ...task, status: "done" }], "all", "", "UTC", now).length, 0);
  assert.equal(filterTasks([{ ...task, status: "done" }], "completed", "", "UTC", now).length, 1);
  assert.equal(filterTasks([{ ...task, status: "dropped" }], "all", "", "UTC", now).length, 0);
  assert.equal(filterTasks([{ ...task, status: "blocked" }], "all", "", "UTC", now).length, 1);
});

test("upcoming filter respects midnight across timezones", () => {
  const now = new Date("2026-11-14T12:00:00Z");
  assert.equal(filterTasks([task], "upcoming", "", "Asia/Kolkata", now).length, 1);
  assert.equal(filterTasks([task], "upcoming", "", "UTC", now).length, 0);
});

test("ordering: deadlines by instant with undated last; priority puts pinned first then score", () => {
  const early = { ...task, id: "early", deadline_at: "2026-11-15T01:00:00+08:00" };
  const undated = { ...task, id: "undated", deadline_at: null };
  assert.deepEqual([undated, task, early].sort(compareDeadlines).map(t => t.id), ["early", "1", "undated"]);
  const high = { ...task, id: "high", priority_score: 90 };
  const pinned = { ...task, id: "pinned", priority_score: 10, pinned: true };
  assert.deepEqual([task, high, pinned].sort(comparePriority).map(t => t.id), ["pinned", "high", "1"]);
  assert.equal(formatEffort(90), "1h 30m");
});

test("preference rows flatten into the form with backend defaults", () => {
  assert.deepEqual(preferencesFromRows([], "Europe/Berlin"), { ...preferences, timezone: "Europe/Berlin" });
  const rows = [row("timezone", { name: "Asia/Kolkata" }), row("work_hours", { start: "08:00", end: "17:00" }), row("focus_windows", { windows: [["08:00", "10:00"], ["15:00", "17:00"]] }),
    row("reminder_lead", { minutes: 30 }), row("estimate_padding", { enabled: true }), row("quiet_hours", { start: "23:00", end: "06:00" }, { status: "suggested", source: "inferred", confidence: .7 })];
  const flat = preferencesFromRows(rows);
  assert.equal(flat.workStart, "08:00"); assert.equal(flat.focusEnd, "10:00"); assert.equal(flat.reminderLead, 30); assert.equal(flat.estimatePadding, true);
  assert.equal(flat.quietStart, "22:30", "suggested values are not applied until accepted");
});

test("saving preferences sends only changed keys in the backend shape", () => {
  assert.deepEqual(preferenceUpdates(preferences, preferences), [], "untouched defaults are not written");
  assert.deepEqual(preferenceUpdates(preferences, { ...preferences, workEnd: "19:00", focusStart: "10:00" }), [
    { key: "work_hours", value: { start: "09:00", end: "19:00" } },
    { key: "focus_windows", value: { windows: [["10:00", "11:00"]] } },
  ]);
  assert.deepEqual(preferenceUpdates(preferences, { ...preferences, timezone: "UTC" }), [{ key: "timezone", value: { name: "UTC" } }]);
});

test("preference validation allows overnight quiet hours and rejects bad values", () => {
  assert.equal(validatePreferences(preferences), null);
  assert.ok(validatePreferences({ ...preferences, timezone: "not/a/zone" }));
  assert.ok(validatePreferences({ ...preferences, workEnd: "08:00" }));
  assert.ok(validatePreferences({ ...preferences, quietStart: "27:00" }));
  assert.ok(validatePreferences({ ...preferences, reminderLead: 2000 }));
});

test("preference rows and routines read as plain language", () => {
  assert.deepEqual(describePreference(row("work_hours", { start: "09:00", end: "18:00" })), { label: "Working hours", value: "09:00–18:00" });
  assert.equal(describePreference(row("focus_windows", { windows: [["08:00", "10:00"]] })).value, "08:00–10:00");
  assert.equal(describePreference(row("work_hours_overrides", { dates: { "2026-11-18": { start: "09:00", end: "21:00" } } })).value, "2026-11-18 09:00–21:00");
  assert.equal(routineRule([]), "FREQ=DAILY");
  assert.equal(routineRule(["FR", "MO"]), "FREQ=WEEKLY;BYDAY=MO,FR");
  assert.equal(describeRule("FREQ=WEEKLY;BYDAY=MO,WE"), "Mon, Wed");
  assert.equal(describeRule("RRULE:FREQ=DAILY"), "Every day");
});

test("durations read as hours and minutes, never decimal hours", () => {
  assert.equal(formatHours(0), "0 min");
  assert.equal(formatHours(30), "30 min");
  assert.equal(formatHours(60), "1 h");
  assert.equal(formatHours(474), "7 h 54 min");
  assert.equal(formatHours(89.6), "1 h 30 min");
  assert.equal(formatHours(-15), "0 min");
});
