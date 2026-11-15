import assert from "node:assert/strict";
import test from "node:test";
import { agendaDays, eventTimeText, googleReturnMessage, lastSyncedText, syncSummary } from "../src/lib/google.ts";

test("every return result has a plain message and unknown ones are ignored", () => {
  assert.equal(googleReturnMessage("connected")?.kind, "success");
  for (const result of ["connected_sync_failed", "denied", "expired", "no_scope", "not_configured", "error"]) assert.equal(googleReturnMessage(result)?.kind, "error");
  assert.equal(googleReturnMessage(null), null);
  assert.equal(googleReturnMessage("<script>"), null);
});

test("sync summary lists only what changed", () => {
  assert.equal(syncSummary({ created: 2, updated: 0, removed: 1, truncated: false, note: null }), "Synced: 2 added, 1 removed.");
  assert.equal(syncSummary({ created: 0, updated: 0, removed: 0, truncated: false, note: null }), "Already up to date.");
  assert.match(syncSummary({ created: 1, updated: 0, removed: 0, truncated: true, note: "Plan pending." }), /1,000 events.*Plan pending\./);
});

test("last synced wording", () => {
  const now = Date.parse("2026-11-15T12:00:00Z");
  assert.equal(lastSyncedText(null, now), "Not synced yet");
  assert.equal(lastSyncedText("2026-11-15T11:59:40Z", now), "Synced just now");
  assert.equal(lastSyncedText("2026-11-15T11:30:00Z", now), "Synced 30 min ago");
  assert.equal(lastSyncedText("2026-11-15T09:00:00Z", now), "Synced 3 h ago");
  assert.equal(lastSyncedText("2026-11-12T12:00:00Z", now), "Synced 3 d ago");
});

test("agenda groups upcoming events by local day and labels today and tomorrow", () => {
  const now = Date.parse("2026-11-15T06:30:00Z"); // 12:00 in Kolkata
  const ev = (id: string, start: string, end: string, source = "gcal") => ({ id, title: id, start_at: start, end_at: end, location: null, source });
  const days = agendaDays([
    ev("past", "2026-11-14T03:00:00Z", "2026-11-14T04:00:00Z"),
    ev("ongoing", "2026-11-14T17:00:00Z", "2026-11-15T08:00:00Z"),
    ev("later", "2026-11-15T10:00:00Z", "2026-11-15T11:00:00Z", "manual"),
    ev("tomorrow", "2026-11-16T04:00:00Z", "2026-11-16T05:00:00Z"),
    ev("far", "2026-12-20T04:00:00Z", "2026-12-20T05:00:00Z"),
  ], "Asia/Kolkata", now);
  assert.deepEqual(days.map(day => [day.label, day.events.map(e => e.id)]), [["Today", ["ongoing", "later"]], ["Tomorrow", ["tomorrow"]]]);
  assert.equal(days[0].day, "15");
});

test("event time text shows a range, or all day for whole local days", () => {
  assert.equal(eventTimeText({ start_at: "2026-11-15T04:00:00Z", end_at: "2026-11-15T05:15:00Z" }, "Asia/Kolkata"), "09:30–10:45");
  assert.equal(eventTimeText({ start_at: "2026-11-14T18:30:00Z", end_at: "2026-11-15T18:30:00Z" }, "Asia/Kolkata"), "All day");
  assert.equal(eventTimeText({ start_at: "2026-11-14T18:30:00Z", end_at: "2026-11-16T18:30:00Z" }, "Asia/Kolkata"), "2 days");
});
