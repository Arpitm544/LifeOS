export type CalendarProposal = { title: string; start_at: string; end_at: string; location: string | null; rrule: string | null; external_id: string; all_day: boolean };
export type CalendarParseResult = { proposals: CalendarProposal[]; capped: boolean; skipped_past: number; skipped_cancelled: number; skipped_invalid: number; skipped_duplicate: number; timezone: string };
export type CalendarSaveResult = { batch_id: string; event_ids: string[]; created: number; skipped_existing: number; note: string | null };
export type CalendarRow = CalendarProposal & { id: string; selected: boolean };

export const MAX_ICS_BYTES = 2 * 1024 * 1024;
export const ICS_UNDO_SECONDS = 10;

/** Only .ics / text/calendar files under the server limit are accepted. */
export function icsFileError(file: { name: string; type: string; size: number }): string | null {
  const isIcs = /\.ics$/i.test(file.name) || file.type === "text/calendar";
  if (!isIcs) return "Choose an .ics calendar file. In Google Calendar: Settings → Import & export → Export.";
  if (file.size > MAX_ICS_BYTES) return "That calendar file is larger than 2 MB. Export a smaller range or fewer calendars.";
  return null;
}

export function toCalendarRows(proposals: CalendarProposal[]): CalendarRow[] {
  return proposals.map((proposal, index) => ({ ...proposal, id: `${index}-${proposal.external_id}`, selected: true }));
}

/** The reviewed events to send to the server, without the UI-only fields. */
export function selectedEvents(rows: CalendarRow[]): { events: CalendarProposal[] } | { error: string } {
  const chosen = rows.filter(row => row.selected);
  if (!chosen.length) return { error: "Select at least one event to add." };
  const events = chosen.map(({ id: _id, selected: _selected, ...rest }) => ({ ...rest, title: rest.title.trim() }));
  if (events.some(event => !event.title)) return { error: "Every event needs a title." };
  return { events };
}

export function calendarNotes(result: Pick<CalendarParseResult, "capped" | "skipped_past" | "skipped_cancelled" | "skipped_invalid" | "skipped_duplicate">): string[] {
  const notes: string[] = [];
  if (result.skipped_past) notes.push(`${result.skipped_past} past event${result.skipped_past === 1 ? " was" : "s were"} left out.`);
  if (result.skipped_cancelled) notes.push(`${result.skipped_cancelled} cancelled event${result.skipped_cancelled === 1 ? " was" : "s were"} left out.`);
  if (result.skipped_duplicate) notes.push(`${result.skipped_duplicate} duplicate${result.skipped_duplicate === 1 ? " was" : "s were"} merged.`);
  if (result.skipped_invalid) notes.push(`${result.skipped_invalid} event${result.skipped_invalid === 1 ? " couldn’t" : "s couldn’t"} be read and ${result.skipped_invalid === 1 ? "was" : "were"} skipped.`);
  if (result.capped) notes.push("Only the first 500 events are shown.");
  return notes;
}

export function calendarSaveSummary(result: CalendarSaveResult): string {
  const added = `Added ${result.created} event${result.created === 1 ? "" : "s"} to your calendar.`;
  const already = result.skipped_existing ? ` ${result.skipped_existing} ${result.skipped_existing === 1 ? "was" : "were"} already imported.` : "";
  return added + already + (result.note ? ` ${result.note}` : "");
}
