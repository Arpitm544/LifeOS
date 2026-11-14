import type { Category, TaskInput } from "./types.ts";

export type ProposalKind = "exam" | "project" | "assignment" | "quiz" | "lab" | "reading" | "presentation" | "other";
export type SyllabusProposal = { title: string; kind: ProposalKind; deadline_at: string | null; effort_est_min: number; importance: number; category: Category; notes: string | null };
export type ExtractResult = { course: string; proposals: SyllabusProposal[]; skipped_past: number; skipped_invalid: number; capped: boolean; truncated: boolean; fallback: boolean; source_chars: number; timezone: string };
export type SaveResult = { batch_id: string; task_ids: string[]; planned: boolean; blocks: number; unplaced: number; conflicts: { deadline_at: string; shortfall_min: number }[] };
export type ReviewRow = SyllabusProposal & { id: string; selected: boolean };

export const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;
export const MAX_TEXT_CHARS = 200_000;
export const UNDO_SECONDS = 10;

/** PDFs go to the server as base64; plain-text files are read in the browser. */
export function uploadKind(file: { name: string; type: string; size: number }): { kind: "pdf" | "text" } | { error: string } {
  if (file.size > MAX_UPLOAD_BYTES) return { error: "That file is larger than 8 MB. Upload a smaller file or paste the text." };
  const name = file.name.toLowerCase();
  if (file.type === "application/pdf" || name.endsWith(".pdf")) return { kind: "pdf" };
  if (file.type.startsWith("text/") || /\.(txt|md|csv)$/.test(name)) return { kind: "text" };
  return { error: "Upload a PDF or a text file, or paste the syllabus." };
}

export function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

export function toReviewRows(proposals: SyllabusProposal[]): ReviewRow[] {
  return proposals.map((proposal, index) => ({ ...proposal, id: `p${index}`, selected: true }));
}

export function toTaskInput(row: ReviewRow): TaskInput {
  return { title: row.title.trim(), deadline_at: row.deadline_at, effort_est_min: row.effort_est_min, importance: row.importance, category: row.category, notes: row.notes };
}

/** Rows that will be saved, or the first problem to fix before saving. */
export function selectedTasks(rows: ReviewRow[]): { tasks: TaskInput[] } | { error: string } {
  const chosen = rows.filter(row => row.selected);
  if (!chosen.length) return { error: "Select at least one task to add." };
  const blank = chosen.find(row => !row.title.trim());
  if (blank) return { error: "Every selected task needs a title." };
  const effort = chosen.find(row => !Number.isInteger(row.effort_est_min) || row.effort_est_min < 5 || row.effort_est_min > 600);
  if (effort) return { error: `Effort for “${effort.title.trim()}” must be 5–600 minutes.` };
  return { tasks: chosen.map(toTaskInput) };
}

export function extractNotes(result: ExtractResult): string[] {
  const notes: string[] = [];
  if (result.fallback) notes.push("The AI model was unavailable, so LifeOS used a simpler date finder. Check each item carefully.");
  if (result.skipped_past) notes.push(`${result.skipped_past} item${result.skipped_past === 1 ? " is" : "s are"} already past and left out.`);
  if (result.truncated) notes.push("The syllabus was long, so only the first part was read.");
  if (result.capped) notes.push("Only the first 40 items are shown.");
  return notes;
}

export function saveSummary(result: SaveResult): string {
  const count = result.task_ids.length;
  const added = `Added ${count} task${count === 1 ? "" : "s"}`;
  if (!result.planned) return `${added}.`;
  const blocks = result.blocks ? `, planned ${result.blocks} focus block${result.blocks === 1 ? "" : "s"} over the next two weeks` : "";
  const short = result.conflicts.length ? ` ${result.conflicts.length} deadline${result.conflicts.length === 1 ? " is" : "s are"} tight — see Today for options.` : "";
  return `${added}${blocks}.${short}`;
}
