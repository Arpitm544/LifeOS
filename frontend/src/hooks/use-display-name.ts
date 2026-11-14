"use client";

import { useUser } from "@clerk/nextjs";

/** First name from the Clerk profile, falling back to the username or email. */
export function useDisplayName() {
  const { user } = useUser();
  const full = user?.fullName || user?.username || user?.primaryEmailAddress?.emailAddress?.split("@")[0] || "";
  return { full: full || "Your account", first: user?.firstName || user?.fullName?.split(/\s+/)[0] || "there" };
}
