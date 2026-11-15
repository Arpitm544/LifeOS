import { PageHeading } from "@/components/layout/page-heading";
import { GoogleSync } from "@/components/import/google-sync";

export default function CalendarPage() {
  return <><PageHeading eyebrow="Calendar sync" title="Bring your calendar in. Plan around it." description="Connect Google Calendar so LifeOS never schedules focus time on top of your real commitments." /><GoogleSync /></>;
}
