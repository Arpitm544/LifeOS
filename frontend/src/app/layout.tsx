import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import "@fontsource-variable/manrope";
import "./globals.css";

export const metadata: Metadata = { title: { default: "LifeOS — Your personal orbit", template: "%s · LifeOS" }, description: "Your goals, your pace, your space. A personal planning workspace with tasks, insights, and voice." };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><ClerkProvider signInUrl="/sign-in" signUpUrl="/sign-up" signInFallbackRedirectUrl="/today" signUpFallbackRedirectUrl="/today">{children}</ClerkProvider></body></html>;
}
