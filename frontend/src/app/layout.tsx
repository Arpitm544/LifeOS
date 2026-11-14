import type { Metadata } from "next";
import "@fontsource-variable/manrope";
import "./globals.css";
import { WorkspaceProvider } from "@/components/providers/workspace-provider";
import { AppShell } from "@/components/layout/app-shell";

export const metadata: Metadata = { title: { default: "LifeOS — Your personal orbit", template: "%s · LifeOS" }, description: "Your goals, your pace, your space. A personal planning workspace with tasks, insights, and voice." };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><WorkspaceProvider><AppShell>{children}</AppShell></WorkspaceProvider></body></html>;
}
