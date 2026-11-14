import { PageHeading } from "@/components/layout/page-heading";
import { CalendarImport } from "@/components/import/calendar-import";

export default function CalendarImportPage() {
  return <><PageHeading eyebrow="Calendar import" title="Bring your calendar in. Plan around it." description="Upload an .ics file from Google, Apple or Outlook so LifeOS never schedules focus time on top of your real commitments." /><CalendarImport /></>;
}
