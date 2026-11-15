import assert from "node:assert/strict";
import test from "node:test";
import { addDays, dayLoad, shiftToDay } from "../src/lib/week.ts";
import { focusPeriods, needsOnboarding } from "../src/lib/task-utils.ts";
import type { Conflict, PlanBlock } from "../src/lib/types.ts";

const block = (start: string, end: string, status: PlanBlock["status"] = "planned"): PlanBlock => ({ id: start, task_id: "t", title: "T", start_at: start, end_at: end, status });

test("addDays crosses month and year ends", () => {
  assert.equal(addDays("2026-11-30", 1), "2026-12-01");
  assert.equal(addDays("2026-12-31", 1), "2027-01-01");
  assert.equal(addDays("2026-03-01", -1), "2026-02-28");
});

test("dayLoad compares planned time with planned plus free time", () => {
  const day = { date: "2026-11-16", free_min_left: 120, conflicts: [] as Conflict[], plan_blocks: [block("2026-11-16T04:00:00Z", "2026-11-16T06:00:00Z"), block("2026-11-16T07:00:00Z", "2026-11-16T08:00:00Z", "missed")] };
  const load = dayLoad(day, "Asia/Kolkata");
  assert.equal(load.plannedMin, 120);
  assert.equal(load.capacityMin, 240);
  assert.equal(load.ratio, 0.5);
  assert.equal(load.atRisk, false);
});

test("dayLoad marks a day over 100% when a conflict is due that local day", () => {
  const conflict = { id: "c", deadline_at: "2026-11-16T03:30:00Z", needed_min: 300, free_min: 120, shortfall_min: 180, task_ids: [], options: [] } as Conflict;
  const load = dayLoad({ date: "2026-11-16", free_min_left: 0, conflicts: [conflict], plan_blocks: [] }, "Asia/Kolkata");
  assert.ok(load.ratio > 1);
  assert.equal(load.atRisk, true);
  // The same instant is the previous local day in New York: not at risk there.
  assert.equal(dayLoad({ date: "2026-11-16", free_min_left: 60, conflicts: [conflict], plan_blocks: [] }, "America/New_York").atRisk, false);
});

test("shiftToDay keeps the clock time and moves by whole days", () => {
  assert.deepEqual(shiftToDay(block("2026-11-16T04:00:00.000Z", "2026-11-16T05:30:00.000Z"), "2026-11-16", "2026-11-18"),
    { start_at: "2026-11-18T04:00:00.000Z", end_at: "2026-11-18T05:30:00.000Z" });
  assert.deepEqual(shiftToDay(block("2026-11-16T04:00:00.000Z", "2026-11-16T05:00:00.000Z"), "2026-11-16", "2026-11-15"),
    { start_at: "2026-11-15T04:00:00.000Z", end_at: "2026-11-15T05:00:00.000Z" });
});

test("onboarding opens for new users only", () => {
  assert.equal(needsOnboarding([]), true);
  assert.equal(needsOnboarding([{ key: "timezone", source: "default", value: { name: "UTC" } }]), true);
  assert.equal(needsOnboarding([{ key: "work_hours", source: "stated", value: { start: "09:00", end: "17:00" } }]), false);
  assert.equal(needsOnboarding([{ key: "onboarding", source: "stated", value: { completed: true } }]), false);
  assert.equal(needsOnboarding([{ key: "onboarding", source: "stated", value: { completed: false } }]), true);
});

test("each focus answer seeds a valid two-hour window", () => {
  for (const { window: [start, end] } of Object.values(focusPeriods)) {
    assert.match(start, /^\d{2}:\d{2}$/);
    assert.ok(start < end);
  }
});
