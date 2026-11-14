import { PageHeading } from "@/components/layout/page-heading";
import { SyllabusImport } from "@/components/import/syllabus-import";

export default function ImportPage() {
  return <><PageHeading eyebrow="Syllabus to plan" title="One upload. The whole term, planned." description="Turn a course syllabus into tasks with deadlines and focus time on your calendar." /><SyllabusImport /></>;
}
