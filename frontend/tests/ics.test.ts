import assert from "node:assert/strict";
import test from "node:test";
import { calendarNotes, calendarSaveSummary, icsFileError, selectedEvents, toCalendarRows, type CalendarProposal } from "../src/lib/ics.ts";

const proposal = (over: Partial<CalendarProposal> = {}): CalendarProposal => ({ title: "Standup", start_at: "2026-11-20T10:00:00+00:00", end_at: "2026-11-20T10:15:00+00:00", location: null, rrule: null, external_id: "u1", all_day: false, ...over });

test("only small .ics files are accepted", () => {
  assert.equal(icsFileError({ name: "cal.ics", type: "text/calendar", size: 100 }), null);
  assert.equal(icsFileError({ name: "CAL.ICS", type: "", size: 100 }), null);
  assert.match(icsFileError({ name: "notes.pdf", type: "application/pdf", size: 100 })!, /\.ics/);
  assert.match(icsFileError({ name: "cal.ics", type: "", size: 3 * 1024 * 1024 })!, /2 MB/);
});

test("rows start selected and strip UI fields when saving", () => {
  const rows = toCalendarRows([proposal(), proposal({ external_id: "u2", title: "  Lab  " })]);
  assert.equal(rows.length, 2);
  rows[0].selected = false;
  const result = selectedEvents(rows);
  assert.ok("events" in result);
  assert.deepEqual(result.events.map(event => event.title), ["Lab"]);
  assert.ok(!("selected" in result.events[0]) && !("id" in result.events[0]));
});

test("nothing selected or a blank title is rejected", () => {
  const rows = toCalendarRows([proposal()]);
  rows[0].selected = false;
  assert.deepEqual(selectedEvents(rows), { error: "Select at least one event to add." });
  rows[0].selected = true; rows[0].title = "   ";
  assert.deepEqual(selectedEvents(rows), { error: "Every event needs a title." });
});

test("notes and summary use plain, correctly pluralised wording", () => {
  assert.deepEqual(calendarNotes({ capped: false, skipped_past: 1, skipped_cancelled: 2, skipped_invalid: 0, skipped_duplicate: 0 }), ["1 past event was left out.", "2 cancelled events were left out."]);
  assert.equal(calendarSaveSummary({ batch_id: "b", event_ids: [], created: 1, skipped_existing: 2, note: null }), "Added 1 event to your calendar. 2 were already imported.");
});
