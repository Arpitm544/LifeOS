"use client";

import { useSyncExternalStore } from "react";
import { Moon, Sun } from "lucide-react";
import { getTheme, setTheme, subscribeTheme } from "@/lib/theme";

const getServerTheme = () => "light" as const;

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribeTheme, getTheme, getServerTheme);
  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
  }
  return <button type="button" className="theme-toggle" onClick={toggle} aria-label="Dark mode" aria-pressed={theme === "dark"} title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>
    {theme === "dark" ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}<span className="sr-only">Dark mode</span>
  </button>;
}
