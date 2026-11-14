import assert from "node:assert/strict";
import test from "node:test";
import { filterTasks, formatEffort, localDateKey, parseWorkspace, validatePreferences, validateTask } from "../src/lib/task-utils.ts";
import type { Preferences, Task } from "../src/lib/types.ts";

const task: Task = { id: "1", title: "Study", deadline: "2026-11-14T19:00:00Z", effort: 30, importance: 3, category: "study", completed: false };
const preferences: Preferences = { name: "Arpit", timezone: "Asia/Kolkata", workStart: "09:00", workEnd: "18:00", quietStart: "22:30", quietEnd: "07:30", focusStart: "09:00", focusEnd: "11:00", protectedEvenings: true, estimatePadding: false, reducedMotion: false };

test("task validation rejects empty titles, invalid dates and out-of-range values", () => {
  assert.equal(validateTask(task), null);
  for (const invalid of [{ title: "  " }, { title: "a".repeat(121) }, { deadline: "not a date" }, { effort: 0 }, { effort: 601 }, { effort: 10.5 }, { importance: 6 }]) assert.ok(validateTask({ ...task, ...invalid }));
});
test("filtering uses the profile timezone and keeps completed tasks separate", () => {
  const now = new Date("2026-11-14T20:00:00Z");
  assert.equal(localDateKey(task.deadline!, "Asia/Kolkata"), "2026-11-15");
  assert.equal(filterTasks([task], "today", "study", "Asia/Kolkata", now).length, 1);
  assert.equal(filterTasks([task], "today", "study", "UTC", now).length, 1);
  assert.equal(filterTasks([task], "today", "missing", "Asia/Kolkata", now).length, 0);
  assert.equal(filterTasks([{ ...task, completed: true }], "all", "", "UTC", now).length, 0);
  assert.equal(filterTasks([{ ...task, completed: true }], "completed", "", "UTC", now).length, 1);
});
test("upcoming filter respects midnight across timezones", () => {
  const now = new Date("2026-11-14T12:00:00Z");
  assert.equal(filterTasks([task], "upcoming", "", "Asia/Kolkata", now).length, 1);
  assert.equal(filterTasks([task], "upcoming", "", "UTC", now).length, 0);
});
test("saved workspace is versioned and rejects corrupted data", () => {
  const data = { version: 1, tasks: [task], preferences };
  assert.deepEqual(parseWorkspace(JSON.stringify(data)), { tasks: [task], preferences });
  assert.throws(() => parseWorkspace("broken"));
  assert.throws(() => parseWorkspace(JSON.stringify({ ...data, version: 2 })));
  assert.throws(() => parseWorkspace(JSON.stringify({ ...data, tasks: [{ ...task, effort: -1 }] })));
  assert.throws(() => parseWorkspace(JSON.stringify({ ...data, tasks: [task, task] })));
  assert.throws(() => parseWorkspace(JSON.stringify({ ...data, tasks: [{ ...task, deadline: 123 }] })));
  assert.throws(() => parseWorkspace(JSON.stringify({ ...data, preferences: { ...preferences, reducedMotion: "false" } })));
});
test("preferences allow overnight quiet hours and validate working and focus times", () => {
  assert.equal(validatePreferences(preferences), null);
  assert.ok(validatePreferences({ ...preferences, timezone: "not/a/zone" }));
  assert.ok(validatePreferences({ ...preferences, workEnd: "08:00" }));
  assert.ok(validatePreferences({ ...preferences, focusEnd: "20:00" }));
  assert.ok(validatePreferences({ ...preferences, quietStart: "27:00" }));
  assert.equal(formatEffort(90), "1h 30m");
});
