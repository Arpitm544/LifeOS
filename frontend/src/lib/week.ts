// Pure helpers for the Week view (load bars and moving a block to another day).
import type { PlanBlock, Today } from "./types.ts";
import { localDateKey } from "./task-utils.ts";

/** Add days to a YYYY-MM-DD local date key. */
export function addDays(key: string, days: number) {
  const date = new Date(`${key}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

const minutes = (start: string, end: string) => Math.max(0, (Date.parse(end) - Date.parse(start)) / 60_000);

/** Planned minutes vs working capacity for one day. Capacity = planned + still free; ratio > 1 means overloaded. */
export function dayLoad(day: Pick<Today, "plan_blocks" | "free_min_left" | "conflicts" | "date">, timezone: string) {
  const plannedMin = Math.round(day.plan_blocks.filter(block => block.status === "planned" || block.status === "done").reduce((sum, block) => sum + minutes(block.start_at, block.end_at), 0));
  const freeMin = Math.max(0, day.free_min_left ?? 0);
  const capacityMin = plannedMin + freeMin;
  const dueHere = day.conflicts.filter(conflict => localDateKey(conflict.deadline_at, timezone) === String(day.date));
  // A conflict due this day means demand exceeds supply: show it as over 100%.
  const base = capacityMin ? plannedMin / capacityMin : 0;
  return { plannedMin, freeMin, capacityMin, ratio: dueHere.length ? Math.max(1.01, base) : base, atRisk: dueHere.length > 0 };
}

/** Same local time on another day: the PATCH body for /api/plan-blocks/:id. */
export function shiftToDay(block: Pick<PlanBlock, "start_at" | "end_at">, from: string, to: string) {
  const days = Math.round((Date.parse(`${to}T12:00:00Z`) - Date.parse(`${from}T12:00:00Z`)) / 86_400_000);
  const shift = (value: string) => new Date(Date.parse(value) + days * 86_400_000).toISOString();
  return { start_at: shift(block.start_at), end_at: shift(block.end_at) };
}

/** Same day, shifted by whole minutes: the PATCH body for the Today timeline's earlier/later buttons. */
export function shiftByMinutes(block: Pick<PlanBlock, "start_at" | "end_at">, minutes: number) {
  const shift = (value: string) => new Date(Date.parse(value) + minutes * 60_000).toISOString();
  return { start_at: shift(block.start_at), end_at: shift(block.end_at) };
}

/** Drop a block onto another timeline item: it starts when that item ends and keeps its length. */
export function placeAfter(block: Pick<PlanBlock, "start_at" | "end_at">, target: { end_at: string }) {
  const length = Date.parse(block.end_at) - Date.parse(block.start_at);
  const start = Date.parse(target.end_at);
  return { start_at: new Date(start).toISOString(), end_at: new Date(start + length).toISOString() };
}
