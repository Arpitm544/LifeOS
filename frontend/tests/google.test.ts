import assert from "node:assert/strict";
import test from "node:test";
import { googleReturnMessage, lastSyncedText, syncSummary } from "../src/lib/google.ts";

test("every return result has a plain message and unknown ones are ignored", () => {
  assert.equal(googleReturnMessage("connected")?.kind, "success");
  for (const result of ["connected_sync_failed", "denied", "expired", "error"]) assert.equal(googleReturnMessage(result)?.kind, "error");
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
