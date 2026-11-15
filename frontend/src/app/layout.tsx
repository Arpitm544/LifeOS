import { ClerkProvider } from "@clerk/nextjs";
import { sidebarInitScript } from "@/lib/sidebar";
import { themeInitScript } from "@/lib/theme";
import type { Metadata } from "next";
import "@fontsource-variable/manrope";
import "./globals.css";

export const metadata: Metadata = { title: { default: "LifeOS — Your personal orbit", template: "%s · LifeOS" }, description: "Your goals, your pace, your space. A personal planning workspace with tasks, chat, a daily plan and insights." };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: themeInitScript + ";" + sidebarInitScript }} /></head><body><ClerkProvider appearance={{ variables: { colorPrimary: "var(--color-blue)", colorPrimaryForeground: "var(--auth-primary-foreground)", colorBackground: "var(--color-paper)", colorForeground: "var(--color-ink)", colorInput: "var(--color-bg)", colorInputForeground: "var(--color-ink)", colorMutedForeground: "var(--color-muted)", colorBorder: "var(--color-line)", colorSuccess: "var(--color-blue)", fontFamily: "inherit" }, /* Temporary: hides the Clerk "Development mode" badge while the site runs on test keys; remove once production Clerk keys are set up on a real domain. */ options: { unsafe_disableDevelopmentModeWarnings: true } }} signInUrl="/sign-in" signUpUrl="/sign-up" signInFallbackRedirectUrl="/today" signUpFallbackRedirectUrl="/today">{children}</ClerkProvider></body></html>;
}
