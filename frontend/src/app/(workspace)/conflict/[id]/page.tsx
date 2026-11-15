import { redirect } from "next/navigation";

/** Deep link to a Capacity Guard conflict: open its sheet on Today. */
export default async function ConflictLink({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/today?conflict=${encodeURIComponent(id)}`);
}
