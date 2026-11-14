import { PageHeading } from "@/components/layout/page-heading";
import { SyllabusImport } from "@/components/import/syllabus-import";

export default function ImportPage() {
  return <><PageHeading eyebrow="Import to plan" title="One upload. Everything planned." description="Turn a syllabus, a PDF or a photo of your notes into tasks with deadlines and focus time on your calendar." /><SyllabusImport /></>;
}
