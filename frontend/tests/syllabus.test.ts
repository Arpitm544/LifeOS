import assert from "node:assert/strict";
import test from "node:test";
import { bytesToBase64, extractNotes, saveSummary, selectedTasks, toReviewRows, uploadKind, type ExtractResult, type SyllabusProposal } from "../src/lib/syllabus.ts";

const proposal: SyllabusProposal = { title: "Prepare for Midterm", kind: "exam", deadline_at: "2026-12-01T09:00:00+00:00", effort_est_min: 360, importance: 5, category: "study", notes: "From syllabus: \"Midterm Dec 1\"" };

test("upload kind accepts PDFs and text files under 8 MB", () => {
  assert.deepEqual(uploadKind({ name: "CS101.PDF", type: "", size: 1000 }), { kind: "pdf" });
  assert.deepEqual(uploadKind({ name: "notes.txt", type: "text/plain", size: 10 }), { kind: "text" });
  assert.ok("error" in uploadKind({ name: "a.pdf", type: "application/pdf", size: 9 * 1024 * 1024 }));
  assert.ok("error" in uploadKind({ name: "photo.png", type: "image/png", size: 10 }));
});

test("bytes become base64, including large inputs", () => {
  assert.equal(bytesToBase64(new TextEncoder().encode("%PDF-1.7")), "JVBERi0xLjc=");
  const big = new Uint8Array(100_000).fill(65);
  assert.equal(atob(bytesToBase64(big)).length, 100_000);
});

test("selected rows become task payloads without the kind", () => {
  const rows = toReviewRows([proposal, { ...proposal, title: "Lab 3" }]);
  rows[1].selected = false;
  const result = selectedTasks(rows);
  assert.ok("tasks" in result);
  assert.deepEqual(result.tasks, [{ title: "Prepare for Midterm", deadline_at: proposal.deadline_at, effort_est_min: 360, importance: 5, category: "study", notes: proposal.notes }]);
});

test("selection problems are reported", () => {
  const rows = toReviewRows([proposal]);
  assert.deepEqual(selectedTasks(rows.map(r => ({ ...r, selected: false }))), { error: "Select at least one task to add." });
  assert.deepEqual(selectedTasks(rows.map(r => ({ ...r, title: "  " }))), { error: "Every selected task needs a title." });
  assert.ok("error" in selectedTasks(rows.map(r => ({ ...r, effort_est_min: 4 }))));
});

test("notes and summary explain what happened", () => {
  const result: ExtractResult = { course: "", proposals: [], skipped_past: 2, skipped_invalid: 0, capped: false, truncated: true, fallback: true, source_chars: 1, timezone: "UTC" };
  assert.equal(extractNotes(result).length, 3);
  assert.equal(saveSummary({ batch_id: "b", task_ids: ["1", "2"], planned: true, blocks: 3, unplaced: 0, conflicts: [] }), "Added 2 tasks, planned 3 focus blocks over the next two weeks.");
  assert.match(saveSummary({ batch_id: "b", task_ids: ["1"], planned: true, blocks: 0, unplaced: 1, conflicts: [{ deadline_at: "x", shortfall_min: 60 }] }), /1 deadline is tight/);
});
