import { redirect } from "next/navigation";

/** Deep link from a reminder notification: open the task in the Tasks editor. */
export default async function TaskLink({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/tasks?task=${encodeURIComponent(id)}`);
}
