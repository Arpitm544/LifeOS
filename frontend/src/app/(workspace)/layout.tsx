import { auth } from "@clerk/nextjs/server";
import { AppShell } from "@/components/layout/app-shell";
import { WorkspaceProvider } from "@/components/providers/workspace-provider";

export default async function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const { userId } = await auth.protect();
  return <WorkspaceProvider key={userId}><AppShell>{children}</AppShell></WorkspaceProvider>;
}
